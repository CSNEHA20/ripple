import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any
from fastapi import Header, HTTPException, Request, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from app.config import settings
from app.tenancy import sanitize_tenant_id, TenantGraph

logger = logging.getLogger("ripple.security")

api_key_header_scheme = APIKeyHeader(name=settings.api_key_header, auto_error=False)

DEDUPE_WINDOW_SECONDS = 300.0  # 5 minutes
DEDUPE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "alert_dedupe.json",
)

# Role hierarchy: admin > responder > viewer
ROLE_LEVELS = {
    "viewer": 1,
    "responder": 2,
    "admin": 3,
}

# Pre-registered API keys hashed with SHA-256 (key_hash -> {tenant_id, role, name})
# Standard dev keys provided:
# key_storefront_admin_secret
# key_storefront_responder_secret
# key_storefront_viewer_secret
# key_payments_admin_secret
# key_payments_responder_secret
# key_payments_viewer_secret

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()

_INITIAL_KEYS = {
    _hash_key("key_storefront_admin_secret"): {"tenant_id": "storefront", "role": "admin", "name": "Storefront Admin"},
    _hash_key("key_storefront_responder_secret"): {"tenant_id": "storefront", "role": "responder", "name": "Storefront Responder"},
    _hash_key("key_storefront_viewer_secret"): {"tenant_id": "storefront", "role": "viewer", "name": "Storefront Viewer"},
    _hash_key("key_payments_admin_secret"): {"tenant_id": "payments", "role": "admin", "name": "Payments Admin"},
    _hash_key("key_payments_responder_secret"): {"tenant_id": "payments", "role": "responder", "name": "Payments Responder"},
    _hash_key("key_payments_viewer_secret"): {"tenant_id": "payments", "role": "viewer", "name": "Payments Viewer"},
}

_DYNAMIC_API_KEYS: dict[str, dict[str, Any]] = dict(_INITIAL_KEYS)


def register_api_key(raw_key: str, tenant_id: str, role: str, name: str = "") -> dict[str, Any]:
    """Register and store a hashed API key."""
    h = _hash_key(raw_key)
    rec = {
        "tenant_id": sanitize_tenant_id(tenant_id),
        "role": role if role in ROLE_LEVELS else "responder",
        "name": name or f"{tenant_id} {role}",
        "created_at": time.time(),
    }
    _DYNAMIC_API_KEYS[h] = rec
    return rec


def lookup_api_key(raw_key: str) -> dict[str, Any] | None:
    """Look up key record from hashed key store."""
    if not raw_key:
        return None
    h = _hash_key(raw_key)
    return _DYNAMIC_API_KEYS.get(h)


def _load_dedupe_cache() -> dict[str, float]:
    """Load persistent deduplication cache from disk."""
    if os.path.exists(DEDUPE_FILE):
        try:
            with open(DEDUPE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_dedupe_cache(cache: dict[str, float]) -> None:
    """Save persistent deduplication cache to disk."""
    try:
        os.makedirs(os.path.dirname(DEDUPE_FILE), exist_ok=True)
        with open(DEDUPE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.debug(f"Failed to persist dedupe cache: {e}")


def verify_webhook_signature(
    payload_bytes: bytes, signature_header: str | None, secret: str | None = None
) -> bool:
    """Verify HMAC SHA-256 signature on incoming alert webhook.
    Fails closed in production if secret is not configured or signature is invalid.
    """
    effective_secret = secret if secret is not None else settings.webhook_secret

    # Production fail-closed check
    if settings.environment == "production":
        if not effective_secret:
            logger.error("FATAL: Webhook secret must be configured in production environment.")
            raise HTTPException(status_code=500, detail="Webhook security misconfigured in production")
        if not signature_header:
            logger.warning("Rejecting alert webhook: missing X-Ripple-Signature header in production.")
            return False

    if not effective_secret:
        return True

    if not signature_header:
        logger.warning("Rejecting alert webhook: missing X-Ripple-Signature header while secret is active.")
        return False

    raw_sig = signature_header.strip()
    if raw_sig.startswith("sha256="):
        raw_sig = raw_sig.replace("sha256=", "")

    expected = hmac.new(
        effective_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(raw_sig, expected)


def check_alert_dedupe(fingerprint: str, window_seconds: float = DEDUPE_WINDOW_SECONDS) -> bool:
    """Check alert deduplication with disk persistence across server restarts."""
    now = time.time()
    cache = _load_dedupe_cache()

    # Clean up stale items outside the window
    cleaned = {k: ts for k, ts in cache.items() if (now - ts) <= window_seconds}

    if fingerprint in cleaned:
        logger.info(f"Duplicate alert suppressed for fingerprint '{fingerprint}' within {window_seconds}s.")
        return True

    cleaned[fingerprint] = now
    _save_dedupe_cache(cleaned)
    return False


def authenticate_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header_scheme),
) -> dict[str, Any]:
    """Strictly authenticate API key, enforce tenancy isolation, and return credentials."""
    # Also check Bearer Authorization or stream query param (?api_key= or ?token=)
    token = api_key
    if not token:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("api_key") or request.query_params.get("token")

    requested_tenant = request.headers.get("x-tenant") or request.query_params.get("tenant")
    if requested_tenant:
        requested_tenant = sanitize_tenant_id(requested_tenant)

    # 1. Key is provided -> must be verified against store
    if token:
        key_record = lookup_api_key(token)
        if not key_record:
            raise HTTPException(status_code=401, detail="Invalid API key")

        key_tenant = key_record["tenant_id"]
        key_role = key_record["role"]

        # Enforce cross-tenant isolation: non-admin keys CANNOT access other tenants!
        if key_role != "admin" and requested_tenant and requested_tenant != key_tenant:
            logger.warning(f"Forbidden cross-tenant access attempt: key tenant '{key_tenant}' requested '{requested_tenant}'")
            raise HTTPException(status_code=403, detail=f"Forbidden: API key for tenant '{key_tenant}' cannot access tenant '{requested_tenant}'")

        effective_tenant = requested_tenant if (key_role == "admin" and requested_tenant) else key_tenant
        return {
            "tenant_id": effective_tenant,
            "role": key_role,
            "name": key_record.get("name", ""),
            "authenticated": True,
        }

    # 2. No key provided
    if settings.environment == "production":
        raise HTTPException(status_code=401, detail="Authentication required: missing API key in production")

    # Local development fallback
    fallback_tenant = requested_tenant or "storefront"
    return {
        "tenant_id": fallback_tenant,
        "role": "admin",
        "name": "Dev Fallback",
        "authenticated": False,
    }


def require_role(min_role: str):
    """Factory dependency to enforce minimum role level: viewer < responder < admin."""
    min_level = ROLE_LEVELS.get(min_role, 1)

    def _role_checker(auth: dict[str, Any] = Depends(authenticate_api_key)) -> dict[str, Any]:
        user_role = auth.get("role", "viewer")
        user_level = ROLE_LEVELS.get(user_role, 1)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: action requires '{min_role}' role or higher (caller has '{user_role}')",
            )
        return auth

    return _role_checker


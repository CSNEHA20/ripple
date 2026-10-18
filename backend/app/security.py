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

API_KEYS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "api_keys.json",
)

# Hashes of default insecure keys that were previously published in example configs / docs.
# In production, Ripple strictly refuses to start if any of these default keys are registered.
DEFAULT_INSECURE_KEY_HASHES: set[str] = {
    "daa2942b5ba828c80bbf79de5dd291df8fcefea24cf660fcfc5509ae2b92b9b2",
    "345e2f8c6b8bb51f4c1e8e513d710a479034f6343e8f13acc1a84bc7b295678b",
    "b6462a02d7b3b78f6212f5b7a446147a1705cd8219b456defd2b280f89d46418",
    "0cd58869e31c629bf3ca0222834196afc464bafac9767160e60aba2d411d2d44",
    "f45a4c42c740c0b37dce3200f78241c4565d6417dad49d981eec18857972c11d",
    "a71973e3967370d7f423f612d51a6f9619419875626f00f6ca4f4c34b92668c2",
}

# Initial dev seed records (hashed only, no plaintext keys in source).
# Strictly ignored when ENVIRONMENT=production.
_DEV_SEED_KEYS: dict[str, dict[str, Any]] = {
    "daa2942b5ba828c80bbf79de5dd291df8fcefea24cf660fcfc5509ae2b92b9b2": {
        "tenant_id": "storefront",
        "role": "admin",
        "name": "Storefront Admin",
        "created_at": 1700000000.0,
        "revoked": False,
        "revoked_at": None,
    },
    "345e2f8c6b8bb51f4c1e8e513d710a479034f6343e8f13acc1a84bc7b295678b": {
        "tenant_id": "storefront",
        "role": "responder",
        "name": "Storefront Responder",
        "created_at": 1700000000.0,
        "revoked": False,
        "revoked_at": None,
    },
    "b6462a02d7b3b78f6212f5b7a446147a1705cd8219b456defd2b280f89d46418": {
        "tenant_id": "storefront",
        "role": "viewer",
        "name": "Storefront Viewer",
        "created_at": 1700000000.0,
        "revoked": False,
        "revoked_at": None,
    },
    "0cd58869e31c629bf3ca0222834196afc464bafac9767160e60aba2d411d2d44": {
        "tenant_id": "payments",
        "role": "admin",
        "name": "Payments Admin",
        "created_at": 1700000000.0,
        "revoked": False,
        "revoked_at": None,
    },
    "f45a4c42c740c0b37dce3200f78241c4565d6417dad49d981eec18857972c11d": {
        "tenant_id": "payments",
        "role": "responder",
        "name": "Payments Responder",
        "created_at": 1700000000.0,
        "revoked": False,
        "revoked_at": None,
    },
    "a71973e3967370d7f423f612d51a6f9619419875626f00f6ca4f4c34b92668c2": {
        "tenant_id": "payments",
        "role": "viewer",
        "name": "Payments Viewer",
        "created_at": 1700000000.0,
        "revoked": False,
        "revoked_at": None,
    },
}


def _hash_key(key: str) -> str:
    if not isinstance(key, str):
        return ""
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def _save_keys_store(store: dict[str, dict[str, Any]]) -> None:
    """Save persistent API key store to disk."""
    try:
        os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)
        with open(API_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist API keys to {API_KEYS_FILE}: {e}")


def _load_keys_store() -> dict[str, dict[str, Any]]:
    """Load API key records from persistent disk store, seed file, or environment."""
    store: dict[str, dict[str, Any]] = {}

    # 1. Primary disk storage
    if os.path.exists(API_KEYS_FILE):
        try:
            with open(API_KEYS_FILE, "r", encoding="utf-8") as f:
                store = json.load(f)
                return store
        except Exception as e:
            logger.warning(f"Failed to read API keys from {API_KEYS_FILE}: {e}")

    # 2. Seed file (if configured and exists)
    seed_path = getattr(settings, "api_keys_seed_file", "data/api_keys_seed.json")
    if seed_path:
        if not os.path.isabs(seed_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cand1 = os.path.join(base_dir, seed_path)
            cand2 = os.path.join(os.path.dirname(base_dir), seed_path)
            seed_path = cand1 if os.path.exists(cand1) else cand2
        if os.path.exists(seed_path):
            try:
                with open(seed_path, "r", encoding="utf-8") as f:
                    seed_data = json.load(f)
                    if isinstance(seed_data, dict):
                        for k, v in seed_data.items():
                            store[k] = v
                    elif isinstance(seed_data, list):
                        for item in seed_data:
                            if "key" in item:
                                h = _hash_key(item["key"])
                                store[h] = {
                                    "tenant_id": sanitize_tenant_id(item.get("tenant_id", "storefront")),
                                    "role": item.get("role", "responder"),
                                    "name": item.get("name", ""),
                                    "created_at": time.time(),
                                    "revoked": item.get("revoked", False),
                                    "revoked_at": None,
                                }
                            elif "key_hash" in item:
                                store[item["key_hash"]] = item
            except Exception as e:
                logger.warning(f"Failed to load API keys seed file from {seed_path}: {e}")

    # 3. Environment variable (e.g. RIPPLE_INITIAL_KEYS or API_KEYS)
    env_keys = os.environ.get("RIPPLE_INITIAL_KEYS") or os.environ.get("API_KEYS")
    if env_keys:
        try:
            parsed = json.loads(env_keys)
            if isinstance(parsed, list):
                for item in parsed:
                    if "key" in item:
                        h = _hash_key(item["key"])
                        store[h] = {
                            "tenant_id": sanitize_tenant_id(item.get("tenant_id", "storefront")),
                            "role": item.get("role", "responder"),
                            "name": item.get("name", ""),
                            "created_at": time.time(),
                            "revoked": False,
                            "revoked_at": None,
                        }
                    elif "key_hash" in item:
                        store[item["key_hash"]] = item
            elif isinstance(parsed, dict):
                for k, v in parsed.items():
                    store[k] = v
        except Exception as e:
            logger.warning(f"Failed to parse API_KEYS environment variable: {e}")

    # 4. In development only, if store is still empty, seed initial dev keys
    if not store and settings.environment != "production":
        store = {k: dict(v) for k, v in _DEV_SEED_KEYS.items()}
        _save_keys_store(store)

    return store


_DYNAMIC_API_KEYS: dict[str, dict[str, Any]] = _load_keys_store()


def register_api_key(
    raw_key: str,
    tenant_id: str,
    role: str,
    name: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    """Register and store a hashed API key, optionally persisting to disk."""
    h = _hash_key(raw_key)
    rec = {
        "key_hash": h,
        "tenant_id": sanitize_tenant_id(tenant_id),
        "role": role if role in ROLE_LEVELS else "responder",
        "name": name or f"{tenant_id} {role}",
        "created_at": time.time(),
        "revoked": False,
        "revoked_at": None,
    }
    _DYNAMIC_API_KEYS[h] = rec
    if persist:
        _save_keys_store(_DYNAMIC_API_KEYS)
    return rec


def revoke_api_key(
    key_hash: str | None = None,
    raw_key: str | None = None,
) -> bool:
    """Revoke an API key by hash or raw key, persisting changes to disk."""
    if raw_key and not key_hash:
        key_hash = _hash_key(raw_key)
    if key_hash and key_hash in _DYNAMIC_API_KEYS:
        _DYNAMIC_API_KEYS[key_hash]["revoked"] = True
        _DYNAMIC_API_KEYS[key_hash]["revoked_at"] = time.time()
        _save_keys_store(_DYNAMIC_API_KEYS)
        return True
    return False


def list_api_keys(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List hashed API key records (never exposes plaintext keys)."""
    keys = []
    for h, rec in _DYNAMIC_API_KEYS.items():
        if tenant_id and rec.get("tenant_id") != sanitize_tenant_id(tenant_id):
            continue
        item = dict(rec)
        item["key_hash"] = h
        keys.append(item)
    return keys


def lookup_api_key(raw_key: str) -> dict[str, Any] | None:
    """Look up key record from hashed key store with revocation and production security checks."""
    if not raw_key or not isinstance(raw_key, str):
        return None
    h = _hash_key(raw_key)
    rec = _DYNAMIC_API_KEYS.get(h)
    if not rec:
        return None
    if rec.get("revoked", False):
        raise HTTPException(status_code=401, detail="API key has been revoked")
    if settings.environment == "production" and h in DEFAULT_INSECURE_KEY_HASHES:
        logger.critical("Rejecting authentication attempt with default insecure key in production.")
        raise HTTPException(status_code=401, detail="Default insecure API keys are prohibited in production")
    return rec


def check_default_keys_in_production() -> None:
    """In production, refuse to start if any default insecure key is registered."""
    if settings.environment == "production":
        for h, rec in _DYNAMIC_API_KEYS.items():
            if not rec.get("revoked", False) and h in DEFAULT_INSECURE_KEY_HASHES:
                logger.critical("FATAL: Default insecure API key is registered in production! Refusing to start.")
                raise RuntimeError("FATAL: Default insecure API key is registered in production! Refusing to start.")


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
    payload_bytes: bytes,
    signature_header: str | None = None,
    secret: str | None = None,
    auth_header: str | None = None,
    token: str | None = None,
) -> bool:
    """Verify incoming alert webhook using either:
    1. HMAC SHA-256 signature (for systems that can sign payloads, e.g. GitHub, custom webhooks).
    2. Shared Bearer token (for Prometheus Alertmanager or systems sending Authorization: Bearer <token>).

    Both checks use constant-time comparison (hmac.compare_digest).
    Fails closed in production if neither secret nor token is configured, or credentials are invalid.
    """
    effective_secret = secret if secret is not None else settings.webhook_secret
    if secret == "" and token is None:
        effective_token = ""
    else:
        effective_token = token if token is not None else settings.webhook_token

    # Production fail-closed check
    if settings.environment == "production":
        if not effective_secret and not effective_token:
            logger.error("FATAL: Webhook secret or token must be configured in production environment.")
            raise HTTPException(status_code=500, detail="Webhook security misconfigured in production")
        if not signature_header and not auth_header:
            logger.warning("Rejecting alert webhook: missing authentication credentials in production.")
            return False

    # If neither secret nor token is configured, allow bypass for local dev
    if not effective_secret and not effective_token:
        return True

    # Mode 1: Shared Bearer Token (Alertmanager / Token mode)
    if auth_header:
        raw_token = auth_header.strip()
        if raw_token.lower().startswith("bearer "):
            raw_token = raw_token[7:].strip()

        expected_token = effective_token or effective_secret
        if expected_token and hmac.compare_digest(raw_token, expected_token):
            return True

    # Mode 2: HMAC SHA-256 Signature (GitHub / HMAC mode)
    if signature_header:
        raw_sig = signature_header.strip()
        if raw_sig.startswith("sha256="):
            raw_sig = raw_sig.replace("sha256=", "")

        expected_secret = effective_secret or effective_token
        if expected_secret:
            expected_hmac = hmac.new(
                expected_secret.encode("utf-8"),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            if hmac.compare_digest(raw_sig, expected_hmac):
                return True

    logger.warning("Rejecting alert webhook: authentication credentials invalid or missing.")
    return False


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
    token = api_key if isinstance(api_key, str) else None
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

    if not getattr(settings, "auth_dev_mode", False):
        raise HTTPException(status_code=401, detail="Authentication required: missing API key (auth_dev_mode is disabled)")

    # Local development fallback (strictly requires auth_dev_mode=True and non-production)
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


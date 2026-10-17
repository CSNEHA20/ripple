import hashlib
import hmac
import logging
import time
from typing import Any
from fastapi import Header, HTTPException, Request, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from app.config import settings
from app.tenancy import sanitize_tenant_id, TenantGraph

logger = logging.getLogger("ripple.security")

# API key header
api_key_header_scheme = APIKeyHeader(name=settings.api_key_header, auto_error=False)

# In-memory sliding window for alert deduplication: fingerprint -> timestamp
_ALERT_DEDUPE_CACHE: dict[str, float] = {}
DEDUPE_WINDOW_SECONDS = 300.0  # 5 minutes


def verify_webhook_signature(
    payload_bytes: bytes, signature_header: str | None, secret: str | None = None
) -> bool:
    """Verify HMAC SHA-256 signature on incoming alert webhook.
    If no webhook_secret is configured and no secret passed, signature check is waived.
    """
    effective_secret = secret if secret is not None else settings.webhook_secret
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
    """Return True if alert is a duplicate within dedupe window (should be suppressed).
    Return False if alert is new and should be processed.
    """
    now = time.time()
    # Clean up stale items
    expired = [k for k, ts in _ALERT_DEDUPE_CACHE.items() if (now - ts) > window_seconds]
    for k in expired:
        del _ALERT_DEDUPE_CACHE[k]

    if fingerprint in _ALERT_DEDUPE_CACHE:
        logger.info(f"Duplicate alert suppressed for fingerprint '{fingerprint}' within {window_seconds}s.")
        return True

    _ALERT_DEDUPE_CACHE[fingerprint] = now
    return False


def authenticate_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header_scheme),
) -> dict[str, Any]:
    """Extract and validate tenant and roles from API key or headers.
    Enforces security while maintaining graceful default for local development.
    """
    # Check if explicit API key is provided
    tenant_id = request.headers.get("x-tenant") or request.query_params.get("tenant") or "storefront"
    tenant_id = sanitize_tenant_id(tenant_id)

    role = "admin"
    if api_key:
        # Key format: key_<tenant>_<role>_<secret> or raw string
        if api_key.startswith("key_"):
            parts = api_key.split("_")
            if len(parts) >= 3:
                tenant_id = sanitize_tenant_id(parts[1])
                role = parts[2] if parts[2] in ("viewer", "responder", "admin") else "responder"
    
    return {
        "tenant_id": tenant_id,
        "role": role,
        "authenticated": bool(api_key),
    }

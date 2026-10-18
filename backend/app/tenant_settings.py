import base64
import hashlib
import json
import logging
import os
from typing import Any
from cryptography.fernet import Fernet
from app.config import settings

logger = logging.getLogger("ripple.tenant_settings")

# Default service path mappings and keyword hints
DEFAULT_PATH_TO_SERVICE: dict[str, str] = {
    "src/paymentservice/": "paymentservice",
    "src/cartservice/": "cartservice",
    "src/checkoutservice/": "checkoutservice",
    "src/currencyservice/": "currencyservice",
    "src/productcatalogservice/": "productcatalogservice",
    "src/shippingservice/": "shippingservice",
    "src/emailservice/": "emailservice",
    "src/recommendationservice/": "recommendationservice",
    "src/adservice/": "adservice",
    "src/frontend/": "frontend",
    "src/loadgenerator/": "loadgenerator",
}

DEFAULT_KEYWORD_HINTS: dict[str, list[str]] = {
    "paymentservice": ["payment", "payments", "billing", "credit"],
    "cartservice": ["cart", "redis-cart"],
    "checkoutservice": ["checkout", "order"],
    "currencyservice": ["currency", "exchange"],
    "productcatalogservice": ["catalog", "productcatalog"],
    "shippingservice": ["shipping", "freight"],
    "emailservice": ["email", "smtp"],
    "recommendationservice": ["recommendation", "recommendations"],
    "adservice": ["advertisement", "ad", "ads"],
    "frontend": ["frontend", "ui", "layout"],
    "loadgenerator": ["loadgenerator", "locust"],
}

# Tenant-scoped in-memory integration configuration store
_TENANT_INTEGRATIONS: dict[str, dict[str, Any]] = {}

def _get_data_dirs() -> list[str]:
    dirs = []
    if os.environ.get("DATA_DIR"):
        dirs.append(os.environ["DATA_DIR"])
    if os.path.exists("/app/data") and "/app/data" not in dirs:
        dirs.append("/app/data")
    backend_app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(backend_app_dir)
    repo_data = os.path.join(repo_root, "data")
    if os.path.exists(repo_data) and repo_data not in dirs:
        dirs.append(repo_data)
    backend_data = os.path.join(backend_app_dir, "data")
    if os.path.exists(backend_data) and backend_data not in dirs:
        dirs.append(backend_data)
    if not dirs:
        dirs.append(os.path.join(backend_app_dir, "data"))
    return dirs

ENCRYPTION_KEY_FILE = os.path.join(_get_data_dirs()[0], "settings_encryption.key")


def _resolve_active_key_bytes() -> bytes:
    """Resolve dedicated encryption key bytes.
    In production: strictly requires SETTINGS_ENCRYPTION_KEY to be configured.
    In development: reads from data/settings_encryption.key or generates and persists a new Fernet key.
    """
    configured = getattr(settings, "settings_encryption_key", None) or os.environ.get("SETTINGS_ENCRYPTION_KEY")
    if configured and configured.strip():
        raw = configured.strip()
        # If it's a standard Fernet key (32 url-safe base64 bytes)
        try:
            return raw.encode("utf-8")
        except Exception:
            return base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())

    if settings.environment == "production":
        logger.critical("FATAL: SETTINGS_ENCRYPTION_KEY must be configured in production environment.")
        raise RuntimeError("FATAL: SETTINGS_ENCRYPTION_KEY must be configured when ENVIRONMENT=production.")

    # Development / Test auto-provisioning outside of source tree
    try:
        for d in _get_data_dirs():
            cand = os.path.join(d, "settings_encryption.key")
            if os.path.exists(cand):
                with open(cand, "r", encoding="utf-8") as f:
                    k = f.read().strip()
                    if k:
                        return k.encode("utf-8")

        # Generate and persist new development key across all candidate data dirs
        new_key = Fernet.generate_key().decode("utf-8")
        for d in _get_data_dirs():
            try:
                os.makedirs(d, exist_ok=True)
                cand = os.path.join(d, "settings_encryption.key")
                with open(cand, "w", encoding="utf-8") as f:
                    f.write(new_key)
            except Exception:
                pass
        return new_key.encode("utf-8")
    except Exception as e:
        logger.debug(f"Could not load/save dev key: {e}")
        # Deterministic fallback for dev memory without hardcoded production salts
        seed = "ripple_development_local_secrets_key_2026".encode("utf-8")
        return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


def _get_active_cipher() -> Fernet:
    """Returns active v2 Fernet cipher using dedicated SETTINGS_ENCRYPTION_KEY."""
    return Fernet(_resolve_active_key_bytes())


def _get_legacy_v1_cipher() -> Fernet:
    """Returns v1 legacy cipher for migrating secrets previously encrypted under older keys."""
    prev = getattr(settings, "settings_encryption_key_previous", None) or os.environ.get("SETTINGS_ENCRYPTION_KEY_PREVIOUS")
    if prev and prev.strip():
        try:
            return Fernet(prev.strip().encode("utf-8"))
        except Exception:
            return Fernet(base64.urlsafe_b64encode(hashlib.sha256(prev.strip().encode("utf-8")).digest()))
    # Legacy fallback: earlier versions derived from webhook_secret or salt
    seed = (settings.webhook_secret or "ripple_default_encryption_salt_2026").encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed).digest()))


def encrypt_secret(val: str | None) -> str | None:
    """Encrypt secret string at rest using active cipher with enc:v2: prefix.
    If given an enc:v1: secret, decrypts and upgrades to enc:v2: for key rotation.
    """
    if not val:
        return None
    if val.startswith("enc:v2:"):
        return val
    if val.startswith("enc:v1:"):
        # Re-encrypt rotation: decrypt v1 and encrypt as v2
        decrypted = decrypt_secret(val)
        if decrypted:
            val = decrypted
    try:
        cipher = _get_active_cipher()
        encrypted = cipher.encrypt(val.encode("utf-8")).decode("utf-8")
        return f"enc:v2:{encrypted}"
    except Exception as e:
        logger.debug(f"Failed to encrypt secret: {e}")
        return val


def decrypt_secret(val: str | None) -> str | None:
    """Decrypt secret string supporting version prefixes (enc:v2:, enc:v1:), else return as-is."""
    if not val:
        return None
    if val.startswith("enc:v2:"):
        try:
            cipher = _get_active_cipher()
            token = val[len("enc:v2:"):]
            return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.debug(f"Failed to decrypt v2 secret: {e}")
            return val
    if val.startswith("enc:v1:"):
        try:
            cipher = _get_legacy_v1_cipher()
            token = val[len("enc:v1:"):]
            return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.debug(f"Failed to decrypt v1 secret: {e}")
            return val
    return val


def mask_secret(val: str | None) -> str | None:
    """Mask secret value for safe logging and API presentation."""
    if not val:
        return None
    raw = decrypt_secret(val) if (val.startswith("enc:v1:") or val.startswith("enc:v2:") or val.startswith("enc:")) else val
    if len(raw) <= 6:
        return "******"
    if raw.startswith("https://hooks.slack.com/"):
        return f"https://hooks.slack.com/***{raw[-4:]}"
    if raw.startswith("ghp_") or raw.startswith("github_pat_"):
        return f"{raw[:4]}***{raw[-3:]}"
    return f"{raw[:3]}***{raw[-3:]}"


def get_tenant_settings(
    tenant_id: str | None,
    graph: Any = None,
    mask_secrets: bool = False,
) -> dict[str, Any]:
    """Retrieve integration settings for active tenant.
    Guarantees tenant isolation: unconfigured tenants do not inherit foreign or global credentials.
    """
    tenant = tenant_id or "storefront"
    stored = _TENANT_INTEGRATIONS.get(tenant)
    if stored is None:
        stored = {}
        if graph and hasattr(graph, "query"):
            try:
                res = graph.query(
                    """
                    MATCH (ts:TenantSettings {tenant_id: $t})
                    RETURN ts.telemetry_source, ts.prometheus_url, ts.github_repo, ts.slack_webhook_url,
                           ts.dry_run_default, ts.path_to_service_json, ts.keyword_hints_json, ts.github_token,
                           ts.github_workflow, ts.github_ref
                    """,
                    {"t": tenant},
                )
                if res and res.result_set:
                    row = res.result_set[0]
                    p_to_s = json.loads(row[5]) if row[5] else None
                    kw_hints = json.loads(row[6]) if row[6] else None
                    stored = {
                        "telemetry_source": row[0],
                        "prometheus_url": row[1],
                        "github_repo": row[2],
                        "slack_webhook_url": decrypt_secret(row[3]),
                        "dry_run_default": bool(row[4]) if row[4] is not None else False,
                        "path_to_service": p_to_s,
                        "keyword_hints": kw_hints,
                        "github_token": decrypt_secret(row[7]) if len(row) > 7 else None,
                        "github_workflow": row[8] if len(row) > 8 and row[8] else "rollback.yml",
                        "github_ref": row[9] if len(row) > 9 and row[9] else "main",
                    }
            except Exception as e:
                logger.debug(f"Failed to query TenantSettings from graph for '{tenant}': {e}")
        _TENANT_INTEGRATIONS[tenant] = stored

    # Only storefront (the primary demo tenant) falls back to global environment settings
    if tenant == "storefront":
        effective_token = stored.get("github_token") or settings.github_token
        effective_repo = stored.get("github_repo") or settings.github_repo
        effective_slack = stored.get("slack_webhook_url") or settings.slack_webhook_url
    else:
        effective_token = stored.get("github_token")
        effective_repo = stored.get("github_repo")
        effective_slack = stored.get("slack_webhook_url")

    effective_workflow = stored.get("github_workflow") or "rollback.yml"
    effective_ref = stored.get("github_ref") or "main"
    effective_prom = stored.get("prometheus_url") or (settings.prometheus_url if tenant == "storefront" else None)
    effective_source = stored.get("telemetry_source") or (settings.telemetry_source if tenant == "storefront" else "simulator")

    res = {
        "tenant_id": tenant,
        "github_repo": effective_repo,
        "github_workflow": effective_workflow,
        "github_ref": effective_ref,
        "github_token": mask_secret(effective_token) if mask_secrets else effective_token,
        "github_configured": bool(effective_token and effective_repo),
        "slack_webhook_url": mask_secret(effective_slack) if mask_secrets else effective_slack,
        "slack_configured": bool(effective_slack),
        "prometheus_url": effective_prom,
        "telemetry_source": effective_source,
        "dry_run_default": stored.get("dry_run_default", False),
        "verification_window_seconds": stored.get("verification_window_seconds", settings.verification_window_seconds),
        "path_to_service": stored.get("path_to_service") or dict(DEFAULT_PATH_TO_SERVICE),
        "keyword_hints": stored.get("keyword_hints") or dict(DEFAULT_KEYWORD_HINTS),
        "k8s_cluster": stored.get("k8s_cluster") or "sandbox-cluster",
        "k8s_namespace": stored.get("k8s_namespace") or "default",
        "webhook_secret": mask_secret(stored.get("webhook_secret")) if mask_secrets else stored.get("webhook_secret"),
    }

    if mask_secrets:
        res["github_token_masked"] = mask_secret(effective_token)
        res["slack_webhook_url_masked"] = mask_secret(effective_slack)
        res["webhook_secret_masked"] = mask_secret(stored.get("webhook_secret"))

    return res


def update_tenant_settings(
    tenant_id: str,
    updates: dict[str, Any],
    graph: Any = None,
) -> dict[str, Any]:
    """Update integration settings for a given tenant."""
    tenant = tenant_id or "storefront"
    if tenant not in _TENANT_INTEGRATIONS:
        _TENANT_INTEGRATIONS[tenant] = {}

    for k, v in updates.items():
        if v is not None:
            # Normalize alias fields
            if k == "workflow_file":
                _TENANT_INTEGRATIONS[tenant]["github_workflow"] = v
            elif k == "ref":
                _TENANT_INTEGRATIONS[tenant]["github_ref"] = v
            else:
                _TENANT_INTEGRATIONS[tenant][k] = v

    if graph and hasattr(graph, "query"):
        try:
            curr = _TENANT_INTEGRATIONS[tenant]
            p_to_s_json = json.dumps(curr.get("path_to_service")) if curr.get("path_to_service") is not None else None
            kw_hints_json = json.dumps(curr.get("keyword_hints")) if curr.get("keyword_hints") is not None else None
            enc_slack = encrypt_secret(curr.get("slack_webhook_url"))
            enc_token = encrypt_secret(curr.get("github_token"))

            graph.query(
                """
                MERGE (ts:TenantSettings {tenant_id: $t})
                SET ts.telemetry_source = $source,
                    ts.prometheus_url = $prom_url,
                    ts.github_repo = $repo,
                    ts.github_workflow = $workflow,
                    ts.github_ref = $ref,
                    ts.github_token = $gh_token,
                    ts.slack_webhook_url = $slack,
                    ts.dry_run_default = $dry_run,
                    ts.path_to_service_json = $p_json,
                    ts.keyword_hints_json = $kw_json
                """,
                {
                    "t": tenant,
                    "source": curr.get("telemetry_source") or settings.telemetry_source,
                    "prom_url": curr.get("prometheus_url") or settings.prometheus_url,
                    "repo": curr.get("github_repo") or "",
                    "workflow": curr.get("github_workflow") or "rollback.yml",
                    "ref": curr.get("github_ref") or "main",
                    "gh_token": enc_token or "",
                    "slack": enc_slack or "",
                    "dry_run": bool(curr.get("dry_run_default", False)),
                    "p_json": p_to_s_json,
                    "kw_json": kw_hints_json,
                },
            )
        except Exception as e:
            logger.debug(f"Failed to persist TenantSettings node for '{tenant}': {e}")

    return get_tenant_settings(tenant, graph=graph)


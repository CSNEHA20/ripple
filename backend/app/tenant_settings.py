import json
import logging
from typing import Any
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


def get_tenant_settings(tenant_id: str | None, graph: Any = None) -> dict[str, Any]:
    """Retrieve integration settings for active tenant with global settings as fallback.
    Checks in-memory cache and FalkorDB TenantSettings node if present.
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
                           ts.dry_run_default, ts.path_to_service_json, ts.keyword_hints_json, ts.github_token
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
                        "slack_webhook_url": row[3],
                        "dry_run_default": bool(row[4]) if row[4] is not None else False,
                        "path_to_service": p_to_s,
                        "keyword_hints": kw_hints,
                        "github_token": row[7] if len(row) > 7 else None,
                    }
            except Exception as e:
                logger.debug(f"Failed to query TenantSettings from graph for '{tenant}': {e}")
        _TENANT_INTEGRATIONS[tenant] = stored

    effective_token = stored.get("github_token") or settings.github_token
    effective_repo = stored.get("github_repo") or settings.github_repo

    return {
        "tenant_id": tenant,
        "github_repo": effective_repo,
        "github_token": effective_token,
        "github_configured": bool(effective_token and effective_repo),
        "slack_configured": bool(stored.get("slack_webhook_url") or settings.slack_webhook_url),
        "slack_webhook_url": stored.get("slack_webhook_url") or settings.slack_webhook_url,
        "prometheus_url": stored.get("prometheus_url") or settings.prometheus_url,
        "telemetry_source": stored.get("telemetry_source") or settings.telemetry_source,
        "dry_run_default": stored.get("dry_run_default", False),
        "verification_window_seconds": stored.get("verification_window_seconds", settings.verification_window_seconds),
        "verification_poll_step_seconds": stored.get("verification_poll_step_seconds", settings.verification_poll_step_seconds),
        "path_to_service": stored.get("path_to_service") or dict(DEFAULT_PATH_TO_SERVICE),
        "keyword_hints": stored.get("keyword_hints") or dict(DEFAULT_KEYWORD_HINTS),
    }


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
            _TENANT_INTEGRATIONS[tenant][k] = v

    if graph and hasattr(graph, "query"):
        try:
            curr = _TENANT_INTEGRATIONS[tenant]
            p_to_s_json = json.dumps(curr.get("path_to_service")) if curr.get("path_to_service") is not None else None
            kw_hints_json = json.dumps(curr.get("keyword_hints")) if curr.get("keyword_hints") is not None else None
            graph.query(
                """
                MERGE (ts:TenantSettings {tenant_id: $t})
                SET ts.telemetry_source = $source,
                    ts.prometheus_url = $prom_url,
                    ts.github_repo = $repo,
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
                    "repo": curr.get("github_repo") or settings.github_repo or "",
                    "gh_token": curr.get("github_token") or settings.github_token or "",
                    "slack": curr.get("slack_webhook_url") or settings.slack_webhook_url or "",
                    "dry_run": bool(curr.get("dry_run_default", False)),
                    "p_json": p_to_s_json,
                    "kw_json": kw_hints_json,
                },
            )
        except Exception as e:
            logger.debug(f"Failed to persist TenantSettings node for '{tenant}': {e}")

    return get_tenant_settings(tenant, graph=graph)

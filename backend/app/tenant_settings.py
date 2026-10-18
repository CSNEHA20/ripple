import logging
from typing import Any
from app.config import settings

logger = logging.getLogger("ripple.tenant_settings")

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
                    RETURN ts.telemetry_source, ts.prometheus_url, ts.github_repo, ts.slack_webhook_url, ts.dry_run_default
                    """,
                    {"t": tenant},
                )
                if res and res.result_set:
                    row = res.result_set[0]
                    stored = {
                        "telemetry_source": row[0],
                        "prometheus_url": row[1],
                        "github_repo": row[2],
                        "slack_webhook_url": row[3],
                        "dry_run_default": bool(row[4]) if row[4] is not None else False,
                    }
            except Exception as e:
                logger.debug(f"Failed to query TenantSettings from graph for '{tenant}': {e}")
        _TENANT_INTEGRATIONS[tenant] = stored

    return {
        "tenant_id": tenant,
        "github_repo": stored.get("github_repo") or settings.github_repo,
        "github_configured": bool(settings.github_token and (stored.get("github_repo") or settings.github_repo)),
        "slack_configured": bool(stored.get("slack_webhook_url") or settings.slack_webhook_url),
        "slack_webhook_url": stored.get("slack_webhook_url") or settings.slack_webhook_url,
        "prometheus_url": stored.get("prometheus_url") or settings.prometheus_url,
        "telemetry_source": stored.get("telemetry_source") or settings.telemetry_source,
        "dry_run_default": stored.get("dry_run_default", False),
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
            graph.query(
                """
                MERGE (ts:TenantSettings {tenant_id: $t})
                SET ts.telemetry_source = $source,
                    ts.prometheus_url = $prom_url,
                    ts.github_repo = $repo,
                    ts.slack_webhook_url = $slack,
                    ts.dry_run_default = $dry_run
                """,
                {
                    "t": tenant,
                    "source": curr.get("telemetry_source") or settings.telemetry_source,
                    "prom_url": curr.get("prometheus_url") or settings.prometheus_url,
                    "repo": curr.get("github_repo") or settings.github_repo or "",
                    "slack": curr.get("slack_webhook_url") or settings.slack_webhook_url or "",
                    "dry_run": bool(curr.get("dry_run_default", False)),
                },
            )
        except Exception as e:
            logger.debug(f"Failed to persist TenantSettings node for '{tenant}': {e}")

    return get_tenant_settings(tenant, graph=graph)

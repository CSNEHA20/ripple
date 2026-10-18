import logging
from typing import Any
from app.config import settings
from app.adapters.base import BaseTelemetryAdapter, SimulatorTelemetryAdapter
from app.adapters.prometheus import PrometheusAdapter
from app.adapters.demo_target import DemoTargetAdapter
from app.adapters.deployments import DeploymentAdapter
from app.tenant_settings import get_tenant_settings

logger = logging.getLogger("ripple.adapters.resolver")


def get_adapter(tenant_id: str | None = None) -> BaseTelemetryAdapter:
    """Resolve active telemetry adapter for a given tenant.
    Reads tenant-specific settings with global configuration fallback.
    Distinct adapters:
      - 'prometheus': PrometheusAdapter querying external Prometheus API
      - 'demo_target': DemoTargetAdapter querying in-process live demo target
      - 'simulator': SimulatorTelemetryAdapter providing seeded data
    """
    tenant_cfg = get_tenant_settings(tenant_id)
    source = (tenant_cfg.get("telemetry_source") or settings.telemetry_source or "simulator").lower().strip()
    prom_url = tenant_cfg.get("prometheus_url") or settings.prometheus_url

    if source == "prometheus":
        return PrometheusAdapter(prometheus_url=prom_url, fallback_to_demo=False)
    elif source == "demo_target":
        return DemoTargetAdapter()
    else:
        return SimulatorTelemetryAdapter(source_label="seeded")


def get_telemetry_adapter(tenant_id: str | None = None) -> BaseTelemetryAdapter:
    return get_adapter(tenant_id)


def get_deployment_adapter(tenant_id: str | None = None, repo: str | None = None) -> DeploymentAdapter:
    """Resolve deployment adapter for tenant."""
    if repo is None and tenant_id:
        cfg = get_tenant_settings(tenant_id)
        repo = cfg.get("github_repo")
    return DeploymentAdapter(repo=repo)

import logging
from typing import Any
from app.config import settings
from app.adapters.base import BaseTelemetryAdapter, SimulatorTelemetryAdapter
from app.adapters.prometheus import PrometheusAdapter
from app.adapters.deployments import DeploymentAdapter

logger = logging.getLogger("ripple.adapters.resolver")


def get_adapter(tenant_id: str | None = None) -> BaseTelemetryAdapter:
    """Resolve active telemetry adapter for a given tenant based on telemetry_source setting."""
    source = (settings.telemetry_source or "simulator").lower().strip()

    if source == "prometheus":
        return PrometheusAdapter()
    elif source == "demo_target":
        return PrometheusAdapter()  # Uses demo target fallback honestly tagged demo_target
    else:
        return SimulatorTelemetryAdapter(source_label="seeded")


def get_telemetry_adapter(tenant_id: str | None = None) -> BaseTelemetryAdapter:
    return get_adapter(tenant_id)


def get_deployment_adapter(tenant_id: str | None = None, repo: str | None = None) -> DeploymentAdapter:
    """Resolve deployment adapter for tenant."""
    return DeploymentAdapter(repo=repo)

from app.adapters.base import (
    BaseTelemetryAdapter,
    MetricRecord,
    DeploymentRecord,
    TopologyEdgeRecord,
)
from app.adapters.prometheus import PrometheusAdapter
from app.adapters.deployments import DeploymentAdapter
from app.adapters.topology import discover_topology_from_environment, apply_discovered_topology
from app.adapters.demo_target import (
    break_service,
    restore_service,
    get_demo_target_state,
    generate_prometheus_metrics_text,
)

from app.adapters.resolver import (
    get_adapter,
    get_telemetry_adapter,
    get_deployment_adapter,
)

__all__ = [
    "BaseTelemetryAdapter",
    "MetricRecord",
    "DeploymentRecord",
    "TopologyEdgeRecord",
    "PrometheusAdapter",
    "DeploymentAdapter",
    "discover_topology_from_environment",
    "apply_discovered_topology",
    "break_service",
    "restore_service",
    "get_demo_target_state",
    "generate_prometheus_metrics_text",
    "get_adapter",
    "get_telemetry_adapter",
    "get_deployment_adapter",
]


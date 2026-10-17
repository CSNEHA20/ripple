import abc
from typing import Any
from pydantic import BaseModel


class MetricRecord(BaseModel):
    service: str
    ts: float
    latency_p95_ms: float
    error_rate: float
    status: str  # "normal", "degraded", "failing"
    source: str = "real"


class DeploymentRecord(BaseModel):
    service: str
    version: str
    ts: float
    source: str = "real"
    author: str = ""
    commit_sha: str = ""


class TopologyEdgeRecord(BaseModel):
    caller: str
    callee: str
    protocol: str = "gRPC"
    criticality: str = "high"
    verified: bool = True
    source: str = "real"


class BaseTelemetryAdapter(abc.ABC):
    """Abstract interface for metrics and telemetry adapters."""

    @abc.abstractmethod
    def fetch_metrics(
        self,
        services: list[str],
        window_minutes: float = 30.0,
        ref_ts: float | None = None,
    ) -> list[MetricRecord]:
        pass

    @abc.abstractmethod
    def check_health(
        self,
        service: str,
        ref_ts: float | None = None,
    ) -> MetricRecord:
        pass

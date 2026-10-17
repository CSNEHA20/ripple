import abc
from typing import Any
from pydantic import BaseModel


class MetricRecord(BaseModel):
    service: str
    ts: float
    latency_p95_ms: float
    error_rate: float
    status: str  # "normal", "degraded", "failing"
    source: str = "real"  # "real", "demo_target", "seeded", "synthetic"
    scrape_ts: float | None = None


class DeploymentRecord(BaseModel):
    service: str
    version: str
    ts: float
    source: str = "real"  # "real", "synthetic"
    author: str = ""
    commit_sha: str = ""


class TopologyEdgeRecord(BaseModel):
    caller: str
    callee: str
    protocol: str = "gRPC"
    criticality: str = "high"
    verified: bool = True
    source: str = "real"  # "real", "discovered", "synthetic"


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


class SimulatorTelemetryAdapter(BaseTelemetryAdapter):
    """Telemetry adapter providing simulated/seeded metrics when external telemetry is unconfigured."""

    def __init__(self, source_label: str = "seeded"):
        self.source_label = source_label

    def fetch_metrics(
        self,
        services: list[str],
        window_minutes: float = 30.0,
        ref_ts: float | None = None,
    ) -> list[MetricRecord]:
        import time
        now_ts = ref_ts if ref_ts is not None else time.time()
        records = []
        for svc in services:
            base_lat = 20.0 + (hash(svc) % 15)
            records.append(
                MetricRecord(
                    service=svc,
                    ts=now_ts,
                    latency_p95_ms=float(base_lat),
                    error_rate=0.0,
                    status="normal",
                    source=self.source_label,
                    scrape_ts=now_ts,
                )
            )
        return records

    def check_health(
        self,
        service: str,
        ref_ts: float | None = None,
    ) -> MetricRecord:
        import time
        now_ts = ref_ts if ref_ts is not None else time.time()
        base_lat = 20.0 + (hash(service) % 15)
        return MetricRecord(
            service=service,
            ts=now_ts,
            latency_p95_ms=float(base_lat),
            error_rate=0.0,
            status="normal",
            source=self.source_label,
            scrape_ts=now_ts,
        )


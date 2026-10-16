import logging
import random
from typing import Any
from app.tenancy import TenantGraph

logger = logging.getLogger(__name__)


def create_metric_snapshot(
    graph: TenantGraph,
    service_name: str,
    ts: float,
    latency_p95_ms: float,
    error_rate: float,
    status: str,
    snapshot_id: str | None = None,
    source: str = "seeded",
) -> dict[str, Any]:
    """Create a MetricSnapshot node and link (Service)-[:HAD_METRIC]->(MetricSnapshot).
    Every generated snapshot is flagged with source='seeded'.
    """
    sid = snapshot_id or f"metric_{service_name}_{int(ts)}_{random.randint(100, 999)}"
    cypher = """
    MATCH (s:Service {name: $service})
    MERGE (m:MetricSnapshot {id: $id})
    SET m.service = $service,
        m.ts = $ts,
        m.latency_p95_ms = $latency,
        m.error_rate = $error_rate,
        m.status = $status,
        m.source = $source
    MERGE (s)-[:HAD_METRIC]->(m)
    RETURN m.id AS id, m.service AS service, m.status AS status,
           m.latency_p95_ms AS latency, m.error_rate AS error_rate, m.ts AS ts
    """
    params = {
        "id": sid,
        "service": service_name,
        "ts": float(ts),
        "latency": float(latency_p95_ms),
        "error_rate": float(error_rate),
        "status": status,
        "source": source,
    }
    res = graph.query(cypher, params)
    if res and res.result_set:
        row = res.result_set[0]
        return {
            "id": row[0],
            "service": row[1],
            "status": row[2],
            "latency_p95_ms": row[3],
            "error_rate": row[4],
            "ts": row[5],
        }
    return {
        "id": sid,
        "service": service_name,
        "status": status,
        "latency_p95_ms": latency_p95_ms,
        "error_rate": error_rate,
        "ts": ts,
    }


def seed_scenario_metrics(
    graph: TenantGraph,
    metrics_specs: list[dict[str, Any]],
    alert_ts: float,
    include_baseline_for_unlisted: bool = True,
) -> list[dict[str, Any]]:
    """Seed metrics for a scenario into the graph.
    Services explicitly declared get their scenario-specified values (failing, degraded, normal).
    Unlisted services automatically receive healthy 'normal' baselines to provide real
    contradicting evidence during graph-guided investigation.
    """
    recorded: list[dict[str, Any]] = []
    specified_services = set()

    for spec in metrics_specs:
        svc = spec["service"]
        specified_services.add(svc)
        snap = create_metric_snapshot(
            graph=graph,
            service_name=svc,
            ts=alert_ts,
            latency_p95_ms=spec.get("latency_p95_ms", 30.0),
            error_rate=spec.get("error_rate", 0.0),
            status=spec.get("status", "normal"),
            source="seeded",
        )
        recorded.append(snap)

    if include_baseline_for_unlisted:
        # Fetch all other existing services in the graph
        res = graph.query("MATCH (s:Service) RETURN s.name")
        all_services = [row[0] for row in res.result_set] if res else []
        for svc in all_services:
            if svc not in specified_services:
                # Deterministic normal baseline metrics
                base_latency = 15.0 + (hash(svc) % 25)
                snap = create_metric_snapshot(
                    graph=graph,
                    service_name=svc,
                    ts=alert_ts,
                    latency_p95_ms=base_latency,
                    error_rate=0.0,
                    status="normal",
                    source="seeded",
                )
                recorded.append(snap)

    logger.info("Seeded %d metric snapshots into tenant %s", len(recorded), graph.tenant_id)
    return recorded

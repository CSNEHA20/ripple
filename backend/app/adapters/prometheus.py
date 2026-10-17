import logging
import time
from typing import Any
import httpx
from app.config import settings
from app.adapters.base import BaseTelemetryAdapter, MetricRecord

logger = logging.getLogger("ripple.adapters.prometheus")


class PrometheusAdapter(BaseTelemetryAdapter):
    """Fetches real metrics from a Prometheus endpoint via HTTP API."""

    def __init__(self, prometheus_url: str | None = None):
        self.prometheus_url = (prometheus_url or settings.prometheus_url).rstrip("/")

    def _query_instant(self, query: str) -> list[dict[str, Any]]:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.prometheus_url}/api/v1/query", params={"query": query})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data.get("data", {}).get("result", [])
        except Exception as e:
            logger.debug(f"Prometheus query failed for '{query}': {e}")
        return []

    def _query_range(self, query: str, start: float, end: float, step: str = "15s") -> list[dict[str, Any]]:
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(
                    f"{self.prometheus_url}/api/v1/query_range",
                    params={"query": query, "start": str(start), "end": str(end), "step": step},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data.get("data", {}).get("result", [])
        except Exception as e:
            logger.debug(f"Prometheus query_range failed for '{query}': {e}")
        return []

    def fetch_metrics(
        self,
        services: list[str],
        window_minutes: float = 30.0,
        ref_ts: float | None = None,
    ) -> list[MetricRecord]:
        now_ts = ref_ts if ref_ts is not None else time.time()
        start_ts = now_ts - (window_minutes * 60.0)
        records: list[MetricRecord] = []

        # 1. Attempt live query to real Prometheus server using range query or instant fallback
        # Query latency p95: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (service, le))
        latency_query = 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (service, le))'
        latency_results = self._query_range(latency_query, start=start_ts, end=now_ts, step="15s")
        if not latency_results:
            latency_results = self._query_instant(latency_query)

        latency_map: dict[str, float] = {}
        for r in latency_results:
            svc = r.get("metric", {}).get("service")
            val = None
            if "values" in r and r["values"]:
                val = r["values"][-1][1]
            elif "value" in r and r["value"]:
                val = r["value"][1]
            if svc and val is not None:
                try:
                    latency_map[svc.lower()] = float(val) * 1000.0  # to ms
                except (ValueError, TypeError):
                    pass

        # Query error rate: sum(rate(http_requests_total{status=~"5.."}[5m])) by (service) / sum(rate(http_requests_total[5m])) by (service)
        error_query = 'sum(rate(http_requests_total{status=~"5.."}[5m])) by (service) / sum(rate(http_requests_total[5m])) by (service)'
        error_results = self._query_range(error_query, start=start_ts, end=now_ts, step="15s")
        if not error_results:
            error_results = self._query_instant(error_query)

        error_map: dict[str, float] = {}
        for r in error_results:
            svc = r.get("metric", {}).get("service")
            val = None
            if "values" in r and r["values"]:
                val = r["values"][-1][1]
            elif "value" in r and r["value"]:
                val = r["value"][1]
            if svc and val is not None:
                try:
                    error_map[svc.lower()] = float(val)
                except (ValueError, TypeError):
                    pass

        for svc in services:
            svc_clean = svc.lower()
            if svc_clean in latency_map or svc_clean in error_map:
                lat = latency_map.get(svc_clean, 25.0)
                err = error_map.get(svc_clean, 0.0)
                status = "failing" if err > 0.15 or lat > 1500.0 else ("degraded" if err > 0.02 or lat > 500.0 else "normal")
                records.append(
                    MetricRecord(
                        service=svc,
                        ts=now_ts,
                        latency_p95_ms=round(lat, 2),
                        error_rate=round(err, 4),
                        status=status,
                        source="real",
                        scrape_ts=now_ts,
                    )
                )

        # 2. If external Prometheus server is not responding, fall back to in-process live demo target
        # Honest labeling: source is 'demo_target', NEVER 'real'
        if not records:
            from app.adapters.demo_target import DEMO_TARGET_STATE
            for svc in services:
                st = DEMO_TARGET_STATE.get(svc.lower(), {})
                if not st:
                    continue
                lat = float(st.get("latency_ms", 25.0))
                err = float(st.get("error_rate", 0.0))
                status = "failing" if err > 0.15 or lat > 1500.0 else ("degraded" if err > 0.02 or lat > 500.0 else "normal")
                records.append(
                    MetricRecord(
                        service=svc,
                        ts=now_ts,
                        latency_p95_ms=round(lat, 2),
                        error_rate=round(err, 4),
                        status=status,
                        source="demo_target",
                        scrape_ts=now_ts,
                    )
                )

        return records

    def check_health(
        self,
        service: str,
        ref_ts: float | None = None,
    ) -> MetricRecord:
        metrics = self.fetch_metrics([service], ref_ts=ref_ts)
        if metrics:
            return metrics[0]
        # Honest fallback baseline if Prometheus returns no data
        from app.adapters.demo_target import DEMO_TARGET_STATE
        now_ts = ref_ts if ref_ts is not None else time.time()
        source = "demo_target" if service.lower() in DEMO_TARGET_STATE else "synthetic"
        return MetricRecord(
            service=service,
            ts=now_ts,
            latency_p95_ms=22.0,
            error_rate=0.0,
            status="normal",
            source=source,
            scrape_ts=now_ts,
        )


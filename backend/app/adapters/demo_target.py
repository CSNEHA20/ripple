import logging
import random
import threading
import time
from typing import Any
from app.adapters.base import BaseTelemetryAdapter, MetricRecord

logger = logging.getLogger("ripple.adapters.demo_target")

# In-memory target service health state
# service -> {"broken": bool, "error_rate": float, "latency_ms": float, "break_reason": str}
DEMO_TARGET_STATE: dict[str, dict[str, Any]] = {
    "paymentservice": {"broken": False, "error_rate": 0.0, "latency_ms": 24.0, "break_reason": ""},
    "cartservice": {"broken": False, "error_rate": 0.0, "latency_ms": 18.0, "break_reason": ""},
    "checkoutservice": {"broken": False, "error_rate": 0.0, "latency_ms": 35.0, "break_reason": ""},
    "frontend": {"broken": False, "error_rate": 0.0, "latency_ms": 45.0, "break_reason": ""},
    "currencyservice": {"broken": False, "error_rate": 0.0, "latency_ms": 12.0, "break_reason": ""},
    "productcatalogservice": {"broken": False, "error_rate": 0.0, "latency_ms": 15.0, "break_reason": ""},
    "shippingservice": {"broken": False, "error_rate": 0.0, "latency_ms": 28.0, "break_reason": ""},
    "emailservice": {"broken": False, "error_rate": 0.0, "latency_ms": 14.0, "break_reason": ""},
    "recommendationservice": {"broken": False, "error_rate": 0.0, "latency_ms": 22.0, "break_reason": ""},
    "adservice": {"broken": False, "error_rate": 0.0, "latency_ms": 10.0, "break_reason": ""},
}

HISTOGRAM_BUCKETS = ["0.05", "0.1", "0.25", "0.5", "1.0", "2.0", "2.5", "5.0", "+Inf"]

# Live traffic simulator counters
# svc -> {"requests_200": int, "requests_500": int, "duration_sum": float, "duration_count": int, "buckets": dict[str, int]}
_METRICS_COUNTERS: dict[str, dict[str, Any]] = {}
_METRICS_LOCK = threading.Lock()
_SIMULATOR_THREAD: threading.Thread | None = None
_SIMULATOR_RUNNING = False


def _init_service_counters(svc: str, st: dict[str, Any]) -> None:
    lat_sec = float(st.get("latency_ms", 25.0)) / 1000.0
    buckets: dict[str, int] = {}
    for b_le in HISTOGRAM_BUCKETS:
        if b_le == "+Inf" or float(b_le) >= lat_sec:
            buckets[b_le] = 1000
        else:
            buckets[b_le] = 0

    _METRICS_COUNTERS[svc] = {
        "requests_200": 1000,
        "requests_500": 0,
        "duration_sum": round(1000.0 * lat_sec, 4),
        "duration_count": 1000,
        "buckets": buckets,
    }


def _ensure_initialized() -> None:
    with _METRICS_LOCK:
        for svc, st in DEMO_TARGET_STATE.items():
            if svc not in _METRICS_COUNTERS:
                _init_service_counters(svc, st)


def simulate_traffic_tick(delta_seconds: float = 1.0) -> None:
    """Increment counters and histogram buckets over time, driven by service broken/healthy state.
    This guarantees that rate() and histogram_quantile() compute genuine, non-zero values.
    """
    with _METRICS_LOCK:
        for svc, st in DEMO_TARGET_STATE.items():
            if svc not in _METRICS_COUNTERS:
                _init_service_counters(svc, st)

            c = _METRICS_COUNTERS[svc]
            is_broken = st.get("broken", False)
            err_rate = float(st.get("error_rate", 0.0))
            lat_ms = float(st.get("latency_ms", 25.0))
            lat_sec = lat_ms / 1000.0

            # Base traffic: ~20 requests per second
            num_reqs = max(1, int(round(20.0 * delta_seconds)))
            num_500 = int(round(num_reqs * err_rate))
            num_200 = num_reqs - num_500

            c["requests_200"] += num_200
            c["requests_500"] += num_500
            c["duration_count"] += num_reqs
            c["duration_sum"] += round(num_reqs * lat_sec, 4)

            for b_le in HISTOGRAM_BUCKETS:
                if b_le == "+Inf" or float(b_le) >= lat_sec:
                    c["buckets"][b_le] += num_reqs


def _simulator_worker(interval: float = 1.0) -> None:
    global _SIMULATOR_RUNNING
    while _SIMULATOR_RUNNING:
        try:
            simulate_traffic_tick(interval)
        except Exception as e:
            logger.debug(f"Traffic simulator tick error: {e}")
        time.sleep(interval)


def start_traffic_simulator(interval: float = 1.0) -> None:
    """Start daemon background thread incrementing demo target metrics continuously."""
    global _SIMULATOR_THREAD, _SIMULATOR_RUNNING
    _ensure_initialized()
    with _METRICS_LOCK:
        if _SIMULATOR_RUNNING and _SIMULATOR_THREAD and _SIMULATOR_THREAD.is_alive():
            return
        _SIMULATOR_RUNNING = True
        _SIMULATOR_THREAD = threading.Thread(
            target=_simulator_worker,
            args=(interval,),
            name="RippleTrafficSimulator",
            daemon=True,
        )
        _SIMULATOR_THREAD.start()
        logger.info("[DemoTarget] Live traffic simulator background thread started.")


def stop_traffic_simulator() -> None:
    """Stop the background traffic simulator thread."""
    global _SIMULATOR_RUNNING, _SIMULATOR_THREAD
    _SIMULATOR_RUNNING = False
    if _SIMULATOR_THREAD and _SIMULATOR_THREAD.is_alive():
        _SIMULATOR_THREAD.join(timeout=1.0)
    _SIMULATOR_THREAD = None


def reset_metrics() -> None:
    """Reset counters to initial state (useful for tests)."""
    with _METRICS_LOCK:
        _METRICS_COUNTERS.clear()
        for svc, st in DEMO_TARGET_STATE.items():
            _init_service_counters(svc, st)


def break_service(service: str, reason: str = "Connection pool exhaustion") -> dict[str, Any]:
    """Inject failure into demo target service."""
    svc = service.lower().strip()
    if svc not in DEMO_TARGET_STATE:
        DEMO_TARGET_STATE[svc] = {}

    err_rate = 0.68
    lat_ms = 2450.0
    if reason == "error_rate":
        err_rate = 0.68
        lat_ms = 45.0
    elif reason == "latency_p95":
        err_rate = 0.05
        lat_ms = 2450.0

    DEMO_TARGET_STATE[svc] = {
        "broken": True,
        "error_rate": err_rate,
        "latency_ms": lat_ms,
        "break_reason": reason,
        "broken_at": time.time(),
    }
    logger.info(f"[DemoTarget] Service '{svc}' BROKEN: {reason} (error_rate={err_rate}, latency={lat_ms}ms)")
    return {"service": svc, "state": DEMO_TARGET_STATE[svc]}


def restore_service(service: str) -> dict[str, Any]:
    """Restore demo target service to healthy state."""
    svc = service.lower().strip()
    base_lat = 15.0 + (hash(svc) % 20)
    DEMO_TARGET_STATE[svc] = {
        "broken": False,
        "error_rate": 0.0,
        "latency_ms": float(base_lat),
        "break_reason": "",
        "restored_at": time.time(),
    }
    logger.info(f"[DemoTarget] Service '{svc}' RESTORED to normal.")
    return {"service": svc, "state": DEMO_TARGET_STATE[svc]}


def get_demo_target_state() -> dict[str, Any]:
    return DEMO_TARGET_STATE


def get_service_state(service: str | None = None) -> dict[str, Any]:
    if service:
        svc = service.lower().strip()
        return {svc: DEMO_TARGET_STATE.get(svc, {})}
    return DEMO_TARGET_STATE


def generate_prometheus_metrics_text() -> str:
    """Generate authentic Prometheus text format metrics for all services.
    Uses monotonically increasing counters and histogram buckets from the traffic simulator.
    """
    _ensure_initialized()
    lines = [
        "# HELP http_requests_total Total number of HTTP requests made.",
        "# TYPE http_requests_total counter",
    ]
    with _METRICS_LOCK:
        for svc in sorted(DEMO_TARGET_STATE.keys()):
            c = _METRICS_COUNTERS.get(svc)
            if not c:
                continue
            lines.append(f'http_requests_total{{service="{svc}",status="200"}} {c["requests_200"]}')
            lines.append(f'http_requests_total{{service="{svc}",status="500"}} {c["requests_500"]}')

        lines.append("# HELP http_request_duration_seconds HTTP request latency in seconds.")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for svc in sorted(DEMO_TARGET_STATE.keys()):
            c = _METRICS_COUNTERS.get(svc)
            if not c:
                continue
            for b_le in HISTOGRAM_BUCKETS:
                b_val = c["buckets"].get(b_le, 0)
                lines.append(f'http_request_duration_seconds_bucket{{service="{svc}",le="{b_le}"}} {b_val}')
            lines.append(f'http_request_duration_seconds_sum{{service="{svc}"}} {c["duration_sum"]:.3f}')
            lines.append(f'http_request_duration_seconds_count{{service="{svc}"}} {c["duration_count"]}')

    return "\n".join(lines) + "\n"


class DemoTargetAdapter(BaseTelemetryAdapter):
    """Telemetry adapter querying the in-process live demo target.
    Honest labeling: source is ALWAYS 'demo_target'.
    """
    source_name: str = "demo_target"

    def fetch_metrics(
        self,
        services: list[str],
        window_minutes: float = 30.0,
        ref_ts: float | None = None,
    ) -> list[MetricRecord]:
        now_ts = ref_ts if ref_ts is not None else time.time()
        records: list[MetricRecord] = []
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
        now_ts = ref_ts if ref_ts is not None else time.time()
        return MetricRecord(
            service=service,
            ts=now_ts,
            latency_p95_ms=22.0,
            error_rate=0.0,
            status="normal",
            source="demo_target",
            scrape_ts=now_ts,
        )


# Start the background traffic simulator on module load
_ensure_initialized()
start_traffic_simulator(1.0)

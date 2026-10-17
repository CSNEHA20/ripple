import logging
import random
import time
from typing import Any

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


def break_service(service: str, reason: str = "Connection pool exhaustion") -> dict[str, Any]:
    """Inject failure into demo target service."""
    svc = service.lower().strip()
    if svc not in DEMO_TARGET_STATE:
        DEMO_TARGET_STATE[svc] = {}
    DEMO_TARGET_STATE[svc] = {
        "broken": True,
        "error_rate": 0.68,
        "latency_ms": 2450.0,
        "break_reason": reason,
        "broken_at": time.time(),
    }
    logger.info(f"[DemoTarget] Service '{svc}' BROKEN: {reason}")
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
    """Generate authentic Prometheus text format metrics for all services."""
    lines = [
        "# HELP http_requests_total Total number of HTTP requests made.",
        "# TYPE http_requests_total counter",
    ]
    for svc, st in DEMO_TARGET_STATE.items():
        is_broken = st.get("broken", False)
        err_rate = st.get("error_rate", 0.0)
        total_200 = 1000 if not is_broken else 320
        total_500 = int(total_200 * (err_rate / (1.0 - err_rate + 0.0001))) if is_broken else 0

        lines.append(f'http_requests_total{{service="{svc}",status="200"}} {total_200}')
        if total_500 > 0:
            lines.append(f'http_requests_total{{service="{svc}",status="500"}} {total_500}')

    lines.append("# HELP http_request_duration_seconds HTTP request latency in seconds.")
    lines.append("# TYPE http_request_duration_seconds histogram")
    for svc, st in DEMO_TARGET_STATE.items():
        lat_sec = st.get("latency_ms", 25.0) / 1000.0
        lines.append(f'http_request_duration_seconds_bucket{{service="{svc}",le="0.05"}} {1000 if lat_sec <= 0.05 else 100}')
        lines.append(f'http_request_duration_seconds_bucket{{service="{svc}",le="0.5"}} {1000 if lat_sec <= 0.5 else 200}')
        lines.append(f'http_request_duration_seconds_bucket{{service="{svc}",le="2.0"}} {1000 if lat_sec <= 2.0 else 400}')
        lines.append(f'http_request_duration_seconds_bucket{{service="{svc}",le="+Inf"}} 1000')
        lines.append(f'http_request_duration_seconds_sum{{service="{svc}"}} {round(lat_sec * 1000.0, 3)}')
        lines.append(f'http_request_duration_seconds_count{{service="{svc}"}} 1000')

    return "\n".join(lines) + "\n"

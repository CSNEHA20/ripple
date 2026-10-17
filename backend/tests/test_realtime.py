import time
import pytest
from app.config import settings
from app.security import verify_webhook_signature, check_alert_dedupe, authenticate_api_key
from app.agents.orchestrator import IncidentEventBus
from app.actions.executors.sandbox import SandboxActionExecutor
from app.adapters.demo_target import (
    break_service,
    restore_service,
    get_service_state,
    generate_prometheus_metrics_text,
)
from app.adapters.prometheus import PrometheusAdapter


def test_webhook_hmac_signature_verification():
    import hmac
    import hashlib

    secret = "test-secret-key-12345"
    payload = b'{"service":"paymentservice","alert":"latency_spike"}'

    # Compute valid signature
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(payload, valid_sig, secret) is True

    # Bad signature
    assert verify_webhook_signature(payload, "sha256=badbadbadbad", secret) is False

    # Empty signature when secret configured
    assert verify_webhook_signature(payload, None, secret) is False

    # No secret configured allows bypass for local dev
    assert verify_webhook_signature(payload, None, "") is True


def test_alert_deduplication_window():
    key = f"test_alert_{time.time()}"
    # First arrival must pass (not deduplicated)
    assert check_alert_dedupe(key, window_seconds=5) is False
    # Second arrival within window must be deduplicated
    assert check_alert_dedupe(key, window_seconds=5) is True


def test_event_bus_monotonic_sequence_and_resume():
    import asyncio
    bus = IncidentEventBus()
    inc_id = "test_inc_seq_01"

    e1 = bus.publish(inc_id, "incident_opened", {"service": "checkout"})
    e2 = bus.publish(inc_id, "agent_started", {"agent": "triage"})
    e3 = bus.publish(inc_id, "tool_called", {"tool": "blast_radius"})

    assert e1["seq"] == 1
    assert e1["id"] == f"{inc_id}_1"
    assert e2["seq"] == 2
    assert e2["id"] == f"{inc_id}_2"
    assert e3["seq"] == 3
    assert e3["id"] == f"{inc_id}_3"

    async def _test_subscribe():
        events_received = []
        # Resume starting AFTER event 1
        async for ev in bus.subscribe(inc_id, last_event_id=f"{inc_id}_1"):
            events_received.append(ev)
            if ev.get("seq") == 3:
                break
        return events_received

    received = asyncio.run(_test_subscribe())
    assert len(received) == 2
    assert received[0]["seq"] == 2
    assert received[1]["seq"] == 3


def test_demo_target_fault_injection_and_metrics():
    # 1. Break paymentservice
    break_service("paymentservice", reason="Out of database connections")
    state = get_service_state("paymentservice")
    assert state["paymentservice"]["broken"] is True
    assert state["paymentservice"]["error_rate"] > 0.5

    # 2. Prometheus exposition format text
    metrics_text = generate_prometheus_metrics_text()
    assert "http_requests_total" in metrics_text
    assert "http_request_duration_seconds" in metrics_text
    assert 'service="paymentservice"' in metrics_text

    # 3. Prometheus adapter query
    adapter = PrometheusAdapter()
    metrics = adapter.fetch_metrics(["paymentservice"], window_minutes=5.0)
    assert metrics[0].latency_p95_ms > 1000.0
    assert metrics[0].error_rate > 0.5
    assert metrics[0].source == "real"

    # 4. Restore service
    restore_service("paymentservice")
    state_restored = get_service_state("paymentservice")
    assert state_restored["paymentservice"]["broken"] is False
    assert state_restored["paymentservice"]["error_rate"] == 0.0


def test_sandbox_action_executor_idempotency():
    executor = SandboxActionExecutor()
    receipt1 = executor.execute(
        graph=None,
        incident_id="inc_sandbox_test",
        action_id="act_restart_01",
        action_kind="restart_service",
        payload={"service": "paymentservice"},
        approver="test_operator",
        idempotency_key="restart_paymentservice_attempt_1",
    )
    assert receipt1.status == "executed"
    assert receipt1.idempotency_key == "restart_paymentservice_attempt_1"

    # Re-executing with identical idempotency key returns idempotent cached execution
    receipt2 = executor.execute(
        graph=None,
        incident_id="inc_sandbox_test",
        action_id="act_restart_01",
        action_kind="restart_service",
        payload={"service": "paymentservice"},
        approver="test_operator",
        idempotency_key="restart_paymentservice_attempt_1",
    )
    assert receipt2.status == "idempotent_skip"

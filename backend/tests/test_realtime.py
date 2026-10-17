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

    # 3. Prometheus adapter query (fallback to demo target is honestly tagged 'demo_target')
    adapter = PrometheusAdapter()
    metrics = adapter.fetch_metrics(["paymentservice"], window_minutes=5.0)
    assert metrics[0].latency_p95_ms > 1000.0
    assert metrics[0].error_rate > 0.5
    assert metrics[0].source == "demo_target"

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


def test_tenancy_isolation_and_roles():
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.security import authenticate_api_key, register_api_key, require_role

    # Pre-register keys for isolated tenants
    register_api_key("key_alpha_viewer_test", tenant_id="tenant_alpha", role="viewer")
    register_api_key("key_alpha_responder_test", tenant_id="tenant_alpha", role="responder")
    register_api_key("key_beta_admin_test", tenant_id="tenant_beta", role="admin")

    # 1. Matching tenant and role succeeds
    req1 = Request({"type": "http", "headers": [(b"x-api-key", b"key_alpha_viewer_test"), (b"x-tenant", b"tenant_alpha")], "query_string": b""})
    auth1 = authenticate_api_key(req1, api_key="key_alpha_viewer_test")
    assert auth1["tenant_id"] == "tenant_alpha"
    assert auth1["role"] == "viewer"

    # 2. Cross-tenant access is rejected with 403 Forbidden
    req2 = Request({"type": "http", "headers": [(b"x-api-key", b"key_alpha_viewer_test"), (b"x-tenant", b"tenant_beta")], "query_string": b""})
    with pytest.raises(HTTPException) as exc_cross:
        authenticate_api_key(req2, api_key="key_alpha_viewer_test")
    assert exc_cross.value.status_code == 403
    assert "cannot access tenant 'tenant_beta'" in exc_cross.value.detail

    # 3. Role enforcement: viewer cannot execute responder action
    checker = require_role("responder")
    with pytest.raises(HTTPException) as exc_role:
        checker(auth1)
    assert exc_role.value.status_code == 403
    assert "requires 'responder' role" in exc_role.value.detail

    # 4. Responder can execute responder action
    req4 = Request({"type": "http", "headers": [(b"x-api-key", b"key_alpha_responder_test"), (b"x-tenant", b"tenant_alpha")], "query_string": b""})
    auth4 = authenticate_api_key(req4, api_key="key_alpha_responder_test")
    assert checker(auth4)["role"] == "responder"

    # 5. Admin key can access across tenants
    req5 = Request({"type": "http", "headers": [(b"x-api-key", b"key_beta_admin_test"), (b"x-tenant", b"tenant_alpha")], "query_string": b""})
    auth5 = authenticate_api_key(req5, api_key="key_beta_admin_test")
    assert auth5["tenant_id"] == "tenant_alpha"
    assert auth5["role"] == "admin"


def test_target_topology_discovery():
    from app.adapters.topology import discover_topology_from_environment

    edges = discover_topology_from_environment()
    assert len(edges) > 0
    # Every discovered edge must have honest labels
    for e in edges:
        assert e.source == "discovered"
        assert e.verified is True
        assert e.caller
        assert e.callee
    callers = {e.caller for e in edges}
    assert "frontend" in callers or "checkoutservice" in callers


def test_slack_and_github_executor_idempotency():
    from app.actions.executors.slack import SlackActionExecutor
    from app.actions.executors.github_dispatch import GitHubDispatchExecutor

    # Slack idempotency
    slack_exec = SlackActionExecutor()
    r1 = slack_exec.execute(
        graph=None,
        incident_id="inc_slack_01",
        action_id="act_slack_01",
        action_kind="notify_slack",
        payload={"text": "Alert test message"},
        approver="test_op",
    )
    assert r1.status in ("dry_run", "executed (simulated: no SLACK_WEBHOOK_URL)", "executed")

    # Duplicate call with identical payload / idempotency key
    r2 = slack_exec.execute(
        graph=None,
        incident_id="inc_slack_01",
        action_id="act_slack_01",
        action_kind="notify_slack",
        payload={"text": "Alert test message"},
        approver="test_op",
    )
    assert r2.status == "idempotent_skip"

    # GitHub dispatch refusal without configured repo
    gh_exec = GitHubDispatchExecutor(repo=None)
    gh_r1 = gh_exec.execute(
        graph=None,
        incident_id="inc_gh_01",
        action_id="act_gh_01",
        action_kind="rollback",
        payload={"service": "paymentservice"},
        approver="test_op",
    )
    assert gh_r1.status == "refused"
    assert "No GitHub repository configured" in gh_r1.details["error"]


def test_github_path_mapping_no_frontend_bias():
    from app.ingest.github import infer_service_from_path, _infer_service_from_text

    # File path mapping
    assert infer_service_from_path("src/paymentservice/main.go") == "paymentservice"
    assert infer_service_from_path("src/cartservice/src/CartService.cs") == "cartservice"
    assert infer_service_from_path("src/currencyservice/server.js") == "currencyservice"

    # Unmapped text should return 'shared' instead of defaulting to 'frontend'
    assert _infer_service_from_text("Bump general dependencies", "Updated alpine base image") == "shared"


def test_integration_settings_and_system_status():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. System status
    status_resp = client.get("/api/system/status")
    assert status_resp.status_code == 200
    st_data = status_resp.json()
    assert st_data["status"] == "ok"
    assert "telemetry_source" in st_data
    assert "llm_status" in st_data

    # 2. Integration settings
    settings_resp = client.get("/api/integrations/settings?tenant=storefront")
    assert settings_resp.status_code == 200
    s_data = settings_resp.json()
    assert s_data["tenant_id"] == "storefront"
    assert "prometheus_url" in s_data


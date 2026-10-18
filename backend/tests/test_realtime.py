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
    DemoTargetAdapter,
    simulate_traffic_tick,
)
from app.adapters.prometheus import PrometheusAdapter, PrometheusConnectionError


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

    # 3. DemoTargetAdapter query (honestly tagged 'demo_target')
    demo_adapter = DemoTargetAdapter()
    metrics = demo_adapter.fetch_metrics(["paymentservice"], window_minutes=5.0)
    assert metrics[0].latency_p95_ms > 1000.0
    assert metrics[0].error_rate > 0.5
    assert metrics[0].source == "demo_target"

    # Prometheus adapter with fallback_to_demo returns demo_target
    prom_fb = PrometheusAdapter(fallback_to_demo=True)
    m_fb = prom_fb.fetch_metrics(["paymentservice"], window_minutes=5.0)
    assert m_fb[0].latency_p95_ms > 1000.0
    assert m_fb[0].error_rate > 0.5
    assert m_fb[0].source == "demo_target"

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


def test_demo_target_traffic_simulator_monotonic_increment():
    from app.adapters.demo_target import (
        _METRICS_COUNTERS,
        simulate_traffic_tick,
        break_service,
        restore_service,
        generate_prometheus_metrics_text,
    )

    # 1. Service healthy: tick increments requests_200 and buckets
    restore_service("cartservice")
    initial_200 = _METRICS_COUNTERS["cartservice"]["requests_200"]
    initial_count = _METRICS_COUNTERS["cartservice"]["duration_count"]

    simulate_traffic_tick(delta_seconds=1.0)
    after_healthy_200 = _METRICS_COUNTERS["cartservice"]["requests_200"]
    after_healthy_count = _METRICS_COUNTERS["cartservice"]["duration_count"]

    assert after_healthy_200 > initial_200
    assert after_healthy_count > initial_count

    # 2. Break service: tick increments requests_500
    break_service("cartservice", reason="error_rate")
    healthy_500 = _METRICS_COUNTERS["cartservice"]["requests_500"]
    simulate_traffic_tick(delta_seconds=1.0)
    after_broken_500 = _METRICS_COUNTERS["cartservice"]["requests_500"]
    assert after_broken_500 > healthy_500

    # 3. Format text validation
    text = generate_prometheus_metrics_text()
    assert 'http_requests_total{service="cartservice",status="500"}' in text
    assert 'http_request_duration_seconds_bucket{service="cartservice",le="+Inf"}' in text

    restore_service("cartservice")


def test_prometheus_adapter_up_returns_real_metrics(monkeypatch):
    import httpx
    from app.adapters.prometheus import PrometheusAdapter

    def mock_get(url, params=None, **kwargs):
        class MockResponse:
            status_code = 200
            text = "ok"
            def json(self):
                q = (params or {}).get("query", "")
                if "http_request_duration_seconds" in q:
                    return {
                        "status": "success",
                        "data": {
                            "result": [
                                {
                                    "metric": {"service": "paymentservice"},
                                    "value": [1700000000, "1.850"],
                                }
                            ]
                        },
                    }
                elif "http_requests_total" in q:
                    return {
                        "status": "success",
                        "data": {
                            "result": [
                                {
                                    "metric": {"service": "paymentservice"},
                                    "value": [1700000000, "0.420"],
                                }
                            ]
                        },
                    }
                return {"status": "success", "data": {"result": []}}

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, params=None, **kw: mock_get(url, params))

    adapter = PrometheusAdapter(prometheus_url="http://prometheus:9090")
    metrics = adapter.fetch_metrics(["paymentservice"])
    assert len(metrics) == 1
    assert metrics[0].service == "paymentservice"
    assert metrics[0].source == "real"
    assert metrics[0].latency_p95_ms == 1850.0
    assert metrics[0].error_rate == 0.42
    assert metrics[0].status == "failing"


def test_prometheus_adapter_down_raises_connection_error():
    from app.adapters.prometheus import PrometheusAdapter, PrometheusConnectionError

    # Non-existent local port
    adapter = PrometheusAdapter(prometheus_url="http://127.0.0.1:59999", fallback_to_demo=False)
    with pytest.raises(PrometheusConnectionError):
        adapter.fetch_metrics(["paymentservice"])


def test_evidence_gathering_prometheus_down_telemetry_degraded(monkeypatch):
    from unittest.mock import MagicMock
    from app.hypotheses.evidence import gather_evidence_for_hypotheses
    from app.agents.orchestrator import event_bus
    from app.tenant_settings import update_tenant_settings

    # Configure tenant to use prometheus pointing to an invalid url
    update_tenant_settings("tenant_down_test", {"telemetry_source": "prometheus", "prometheus_url": "http://127.0.0.1:59998"})

    mock_graph = MagicMock()
    mock_graph.tenant_id = "tenant_down_test"
    mock_graph.query.return_value = None

    captured_events = []
    original_publish = event_bus.publish

    def mock_publish(inc_id, event_type, data):
        captured_events.append((event_type, data))
        return original_publish(inc_id, event_type, data)

    monkeypatch.setattr(event_bus, "publish", mock_publish)

    hypotheses = [{"id": "hyp_01", "service": "paymentservice", "hops": 1}]
    evidence_by_hyp, trace = gather_evidence_for_hypotheses(
        graph=mock_graph,
        hypotheses=hypotheses,
        alerting_service="paymentservice",
        incident_id="inc_test_degraded",
    )

    # 1. telemetry_degraded event MUST be published
    event_types = [e[0] for e in captured_events]
    assert "telemetry_degraded" in event_types

    # 2. Graph node updated with telemetry_degraded = true
    query_calls = [str(call) for call in mock_graph.query.call_args_list]
    assert any("telemetry_degraded = true" in q for q in query_calls)

    # 3. Evidence reflects honest fallback (demo_target or no data)
    ev_list = evidence_by_hyp["hyp_01"]["supporting"] + evidence_by_hyp["hyp_01"]["contradicting"]
    metric_ev = [ev for ev in ev_list if ev["type"] == "metric"]
    assert len(metric_ev) > 0
    assert metric_ev[0]["source"] in ("demo_target", "no data")


def test_per_tenant_telemetry_adapter_resolution():
    from app.adapters.resolver import get_adapter
    from app.adapters.prometheus import PrometheusAdapter
    from app.adapters.demo_target import DemoTargetAdapter
    from app.tenant_settings import update_tenant_settings

    update_tenant_settings("tenant_alpha_prom", {"telemetry_source": "prometheus", "prometheus_url": "http://prom.internal:9090"})
    update_tenant_settings("tenant_beta_demo", {"telemetry_source": "demo_target"})

    adapter_prom = get_adapter("tenant_alpha_prom")
    adapter_demo = get_adapter("tenant_beta_demo")

    assert isinstance(adapter_prom, PrometheusAdapter)
    assert adapter_prom.prometheus_url == "http://prom.internal:9090"
    assert isinstance(adapter_demo, DemoTargetAdapter)


def test_webhook_bearer_token_verification():
    payload = b'{"alerts":[{"labels":{"service":"paymentservice"}}]}'
    token = "test-token-bearer-xyz"

    # 1. Valid Authorization: Bearer <token>
    assert verify_webhook_signature(payload, auth_header=f"Bearer {token}", token=token) is True

    # 2. Case-insensitive 'bearer' prefix
    assert verify_webhook_signature(payload, auth_header=f"bearer {token}", token=token) is True

    # 3. Direct raw token in auth_header
    assert verify_webhook_signature(payload, auth_header=token, token=token) is True

    # 4. Invalid bearer token rejected
    assert verify_webhook_signature(payload, auth_header="Bearer wrong_token", token=token) is False

    # 5. Missing auth header when token configured rejected
    assert verify_webhook_signature(payload, auth_header=None, token=token) is False


def test_alertmanager_webhook_endpoint_security_modes(monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    test_token = "alertmanager_token_12345"
    test_secret = "hmac_secret_67890"

    alert_payload = {
        "receiver": "ripple-webhook",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "ServiceHighLatency",
                    "service": "paymentservice",
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "High p95 latency on paymentservice",
                    "description": "p95 latency exceeding 1000ms",
                },
                "fingerprint": f"fp_{time.time()}_{hash('test')}",
            }
        ],
    }

    # Set webhook_token and webhook_secret
    monkeypatch.setattr(settings, "webhook_token", test_token)
    monkeypatch.setattr(settings, "webhook_secret", test_secret)

    # 1. Missing credentials returns 401
    resp_no_auth = client.post("/webhooks/alert", json=alert_payload)
    assert resp_no_auth.status_code == 401

    # 2. Wrong token returns 401
    resp_bad_token = client.post(
        "/webhooks/alert",
        json=alert_payload,
        headers={"Authorization": "Bearer bad_token"},
    )
    assert resp_bad_token.status_code == 401

    # 3. Valid Bearer token from Alertmanager accepted and opens incident (200 or 202)
    resp_valid_token = client.post(
        "/webhooks/alert",
        json=alert_payload,
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp_valid_token.status_code in (200, 202)
    data = resp_valid_token.json()
    assert data["status"] in ("accepted", "created", "deduplicated")

    # 4. Valid HMAC signature in X-Ripple-Signature accepted
    import hmac, hashlib
    payload_bytes = json.dumps(alert_payload).encode("utf-8")
    valid_hmac = "sha256=" + hmac.new(test_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    resp_valid_hmac = client.post(
        "/webhooks/alert",
        content=payload_bytes,
        headers={"X-Ripple-Signature": valid_hmac, "Content-Type": "application/json"},
    )
    assert resp_valid_hmac.status_code in (200, 202)

    # 5. Invalid HMAC signature rejected with 401
    resp_bad_hmac = client.post(
        "/webhooks/alert",
        content=payload_bytes,
        headers={"X-Ripple-Signature": "sha256=invalid", "Content-Type": "application/json"},
    )
    assert resp_bad_hmac.status_code == 401


def test_webhook_production_startup_fail_closed(monkeypatch):
    from app.main import validate_security_configuration

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "webhook_secret", None)
    monkeypatch.setattr(settings, "webhook_token", None)

    # Refuse to start without secret or token in production
    with pytest.raises(RuntimeError) as exc_info:
        validate_security_configuration()
    assert "webhook_secret or webhook_token must be configured" in str(exc_info.value)

    # Allowed with token configured
    monkeypatch.setattr(settings, "webhook_token", "prod_token_abc")
    validate_security_configuration()  # Should not raise




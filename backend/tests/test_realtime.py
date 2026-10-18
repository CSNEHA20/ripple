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

    # 2. Integration settings (requires authentication)
    from app.security import register_api_key
    register_api_key("key_integration_test_secret", tenant_id="storefront", role="responder")
    settings_resp = client.get(
        "/api/integrations/settings?tenant=storefront",
        headers={"Authorization": "Bearer key_integration_test_secret"},
    )
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

    # Allowed with token configured and non-default API keys
    monkeypatch.setattr(settings, "webhook_token", "prod_token_abc")
    monkeypatch.setattr("app.security._DYNAMIC_API_KEYS", {})
    validate_security_configuration()  # Should not raise


def test_stream_cross_tenant_isolation_blocked_403():
    """T3 Acceptance: Verify incident SSE stream authentication and cross-tenant blocking with 403 Forbidden."""
    from app.agents.orchestrator import event_bus
    from app.security import register_api_key
    from fastapi.testclient import TestClient
    from app.main import app

    register_api_key("key_stream_alpha_token", tenant_id="tenant_alpha", role="responder")
    register_api_key("key_stream_beta_token", tenant_id="tenant_beta", role="responder")
    register_api_key("key_stream_admin_token", tenant_id="tenant_alpha", role="admin")

    inc_alpha = "inc_alpha_stream_01"
    event_bus.set_incident_tenant(inc_alpha, "tenant_alpha")
    event_bus.publish(inc_alpha, "incident_opened", {"incident_id": inc_alpha, "tenant_id": "tenant_alpha"})
    event_bus.publish(inc_alpha, "agent_started", {"agent": "Triage"})
    event_bus.publish(inc_alpha, "incident_closed", {"incident_id": inc_alpha})

    inc_beta = "inc_beta_stream_02"
    event_bus.set_incident_tenant(inc_beta, "tenant_beta")
    event_bus.publish(inc_beta, "incident_opened", {"incident_id": inc_beta, "tenant_id": "tenant_beta"})
    event_bus.publish(inc_beta, "agent_started", {"agent": "Triage"})
    event_bus.publish(inc_beta, "incident_closed", {"incident_id": inc_beta})

    client = TestClient(app)

    # 1. Unauthenticated stream request returns 401
    resp_no_auth = client.get(f"/api/incidents/{inc_alpha}/stream")
    assert resp_no_auth.status_code == 401

    # 2. Cross-tenant attempt: Tenant Alpha caller trying to stream Tenant Beta incident returns 403 Forbidden
    resp_cross = client.get(f"/api/incidents/{inc_beta}/stream?token=key_stream_alpha_token")
    assert resp_cross.status_code == 403
    assert "cannot access incident belonging to 'tenant_beta'" in resp_cross.json()["detail"]

    # 3. Cross-tenant attempt in reverse: Tenant Beta caller trying to stream Tenant Alpha incident returns 403
    resp_cross_rev = client.get(f"/api/incidents/{inc_alpha}/stream?token=key_stream_beta_token")
    assert resp_cross_rev.status_code == 403

    # 4. Valid tenant caller streaming their own incident succeeds (status 200, text/event-stream)
    with client.stream("GET", f"/api/incidents/{inc_alpha}/stream?token=key_stream_alpha_token") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        for line in resp.iter_lines():
            if line:
                assert "id:" in line or "event:" in line or "data:" in line
                break

    # 5. Last-Event-ID resume support
    with client.stream("GET", f"/api/incidents/{inc_alpha}/stream?token=key_stream_alpha_token", headers={"Last-Event-ID": f"{inc_alpha}_1"}) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line and "data:" in line:
                assert "agent_started" in line or "ping" in line
                break

    # 6. Admin key can stream any tenant's incident
    with client.stream("GET", f"/api/incidents/{inc_beta}/stream?token=key_stream_admin_token") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line:
                break


def test_api_key_persistence_and_revocation():
    """T3 Acceptance: Verify registered keys survive restarts and revocation takes immediate effect."""
    import hashlib
    from app.security import (
        register_api_key,
        lookup_api_key,
        revoke_api_key,
        _load_keys_store,
    )
    from fastapi import HTTPException

    test_raw = "key_restart_survivor_secret"
    register_api_key(test_raw, tenant_id="storefront", role="responder", name="Survivor Key")

    # 1. Lookup in memory succeeds
    rec = lookup_api_key(test_raw)
    assert rec is not None
    assert rec["name"] == "Survivor Key"

    # 2. Reload store from disk (simulating server restart)
    reloaded_store = _load_keys_store()
    h = hashlib.sha256(test_raw.encode("utf-8")).hexdigest()
    assert h in reloaded_store
    assert reloaded_store[h]["name"] == "Survivor Key"

    # 3. Revoke key
    revoked = revoke_api_key(raw_key=test_raw)
    assert revoked is True

    # 4. Lookup after revocation raises 401
    with pytest.raises(HTTPException) as exc_revoked:
        lookup_api_key(test_raw)
    assert exc_revoked.value.status_code == 401
    assert "revoked" in exc_revoked.value.detail.lower()

    # 5. Disk reload confirms key remains revoked across restart
    reloaded_store_after = _load_keys_store()
    assert reloaded_store_after[h]["revoked"] is True


def test_auth_dev_mode_and_production_rejection(monkeypatch):
    """T3 Acceptance: AUTH_DEV_MODE=false blocks requests without key; production strictly refuses default keys."""
    from app.security import authenticate_api_key, check_default_keys_in_production, _DYNAMIC_API_KEYS, DEFAULT_INSECURE_KEY_HASHES
    from starlette.requests import Request
    from app.main import validate_security_configuration
    from fastapi import HTTPException

    dummy_req = Request({"type": "http", "headers": [], "query_string": b""})

    # 1. When auth_dev_mode is False (default) and non-production: no key -> 401 Unauthorized
    monkeypatch.setattr(settings, "auth_dev_mode", False)
    monkeypatch.setattr(settings, "environment", "development")
    with pytest.raises(HTTPException) as exc1:
        authenticate_api_key(dummy_req)
    assert exc1.value.status_code == 401
    assert "auth_dev_mode is disabled" in exc1.value.detail

    # 2. When auth_dev_mode is True and non-production: no key -> dev fallback
    monkeypatch.setattr(settings, "auth_dev_mode", True)
    auth2 = authenticate_api_key(dummy_req)
    assert auth2["role"] == "admin"
    assert auth2["authenticated"] is False

    # 3. When environment is production: even with auth_dev_mode=True, missing key returns 401
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(HTTPException) as exc3:
        authenticate_api_key(dummy_req)
    assert exc3.value.status_code == 401

    # 4. Production refuses to start if default insecure keys are registered
    monkeypatch.setattr(settings, "webhook_token", "valid_prod_token")
    default_hash = next(iter(DEFAULT_INSECURE_KEY_HASHES))
    _DYNAMIC_API_KEYS[default_hash] = {
        "tenant_id": "storefront",
        "role": "admin",
        "name": "Default Dev Key",
        "revoked": False,
    }
    with pytest.raises(RuntimeError) as exc_prod:
        validate_security_configuration()
    assert "Default insecure API key is registered in production" in str(exc_prod.value)

    # When all default insecure keys are revoked or removed, validation passes in production
    saved_keys = dict(_DYNAMIC_API_KEYS)
    try:
        for dh in DEFAULT_INSECURE_KEY_HASHES:
            _DYNAMIC_API_KEYS.pop(dh, None)
        validate_security_configuration()  # Should not raise!
    finally:
        _DYNAMIC_API_KEYS.update(saved_keys)


def test_key_management_api_endpoints():
    """Verify admin API key management endpoints (GET /api/keys, POST /api/keys, DELETE /api/keys/{key_hash})."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.security import register_api_key

    register_api_key("key_admin_manager", tenant_id="storefront", role="admin")
    register_api_key("key_viewer_guest", tenant_id="storefront", role="viewer")
    client = TestClient(app)

    # 1. Viewer role cannot access key management (403)
    r_view = client.get("/api/keys", headers={"Authorization": "Bearer key_viewer_guest"})
    assert r_view.status_code == 403

    # 2. Admin can list keys
    r_list = client.get("/api/keys", headers={"Authorization": "Bearer key_admin_manager"})
    assert r_list.status_code == 200
    assert "keys" in r_list.json()

    # 3. Admin can create new key
    r_create = client.post(
        "/api/keys",
        headers={"Authorization": "Bearer key_admin_manager"},
        json={"tenant_id": "payments", "role": "responder", "name": "Created Key"},
    )
    assert r_create.status_code == 201
    created_data = r_create.json()
    assert "raw_key" in created_data
    new_raw_key = created_data["raw_key"]
    key_hash = created_data["key_record"]["key_hash"]

    # 4. Admin can revoke key by hash
    r_revoke = client.delete(f"/api/keys/{key_hash}", headers={"Authorization": "Bearer key_admin_manager"})
    assert r_revoke.status_code == 200
    assert r_revoke.json()["status"] == "revoked"

    # Revoked key cannot authenticate
    r_fail = client.get(f"/api/incidents/inc_test/stream?token={new_raw_key}")
    assert r_fail.status_code == 401


# ==============================================================================
# T4: Verification you can trust tests
# ==============================================================================


class MockGraphResult:
    def __init__(self, result_set):
        self.result_set = result_set


class MockVerifierTenantGraph:
    def __init__(self, tenant_id: str = "storefront", base_lat: float = 25.0, base_err: float = 0.0):
        self.tenant_id = tenant_id
        self.base_lat = base_lat
        self.base_err = base_err
        self.runbook_counts = {"rb_rollback": {"success": 5.0, "fail": 1.0}}
        self.closed = False
        self.incident_status = "investigating"
        self.queries = []

    def query(self, cypher: str, params=None):
        params = params or {}
        self.queries.append((cypher, params))
        clean = " ".join(cypher.split())

        if "RETURN i.baseline_latency_p95_ms, i.baseline_error_rate" in clean:
            return MockGraphResult([[self.base_lat, self.base_err]])
        elif "HAD_METRIC" in clean:
            return MockGraphResult([[self.base_lat, self.base_err]])
        elif "MATCH (intv:Intervention {id: $id})" in clean:
            return MockGraphResult([["intv_01", "rb_rollback", "resolved", "inc_01"]])
        elif "MATCH (rb:Runbook {id: $id})" in clean:
            rb_id = params.get("id", "rb_rollback")
            counts = self.runbook_counts.get(rb_id, {"success": 0.0, "fail": 0.0})
            return MockGraphResult([[rb_id, rb_id, counts["success"], counts["fail"]]])
        elif "MERGE (rb:Runbook {id: $id})" in clean and "SET rb.title" in clean:
            rb_id = params.get("id", "rb_rollback")
            if rb_id not in self.runbook_counts:
                self.runbook_counts[rb_id] = {"success": 0.0, "fail": 0.0}
            self.runbook_counts[rb_id]["success"] = float(params.get("success_count", self.runbook_counts[rb_id]["success"]))
            self.runbook_counts[rb_id]["fail"] = float(params.get("fail_count", self.runbook_counts[rb_id]["fail"]))
            return MockGraphResult([])
        elif "HAS_HYPOTHESIS" in clean:
            return MockGraphResult([["hyp_paymentservice"]])
        elif "MATCH (h:Hypothesis {id: $hyp_id})" in clean:
            return MockGraphResult([["hyp_paymentservice", "Bad deployment on paymentservice", "paymentservice"]])
        elif "SET i.status = 'closed'" in clean:
            self.closed = True
            self.incident_status = "closed"
            return MockGraphResult([])
        elif "SET i.status = $status" in clean:
            self.incident_status = params.get("status", self.incident_status)
            return MockGraphResult([])
        return MockGraphResult([])


def test_t4_real_window_publishing_and_correct_fix_resolves():
    """T4 Acceptance: A correct fix on the demo target resolves after the verification window,
    publishes verification_sample events as they arrive, updates procedural memory,
    and closes the incident in episodic memory.
    """
    from app.agents.verifier import VerifierAgent
    from app.agents.orchestrator import event_bus
    from app.adapters.demo_target import break_service, restore_service

    graph = MockVerifierTenantGraph(tenant_id="storefront_t4_pass", base_lat=25.0, base_err=0.0)

    # 1. Break demo target service
    break_service("paymentservice", latency_ms=1750.0, error_rate=0.45)
    # 2. Simulate correct fix: service is restored
    restore_service("paymentservice")

    published_samples = []
    original_publish = event_bus.publish

    def spy_publish(inc_id, event_type, data):
        if event_type == "verification_sample":
            published_samples.append(data)
        return original_publish(inc_id, event_type, data)

    event_bus.publish = spy_publish

    try:
        verifier = VerifierAgent(mode="replay")
        verify_task = {
            "id": "task_v_01",
            "payload": {
                "intervention_id": "intv_01",
                "runbook_id": "rb_rollback",
                "target_service": "paymentservice",
            },
        }

        # Run with window of 0.15s and step of 0.03s -> 5 samples
        result, trace = verifier.run(
            graph=graph,
            incident_id="inc_t4_01",
            verify_task=verify_task,
            window_seconds=0.15,
            poll_step_seconds=0.03,
        )

        # Assertions
        assert result["observed_outcome"] == "resolved"
        assert result["status"] == "resolved"
        assert result["closed_incident"] is not None
        assert graph.closed is True
        # Procedural memory updated: success count incremented from 5.0 to 6.0
        assert graph.runbook_counts["rb_rollback"]["success"] == 6.0
        assert graph.runbook_counts["rb_rollback"]["fail"] == 1.0

        # Samples published to event_bus in real-time
        assert len(published_samples) == 5
        for s in published_samples:
            assert s["service"] == "paymentservice"
            assert s["source"] == "demo_target"
            assert s["error_rate"] <= 0.02
            assert s["latency_p95_ms"] <= 200.0
    finally:
        event_bus.publish = original_publish
        restore_service("paymentservice")


def test_t4_wrong_fix_fails_after_window_and_updates_fail_count():
    """T4 Acceptance: A wrong fix on the demo target fails after the window,
    updates procedural memory with failure, and does NOT close the incident.
    """
    from app.agents.verifier import VerifierAgent
    from app.adapters.demo_target import break_service, restore_service

    graph = MockVerifierTenantGraph(tenant_id="storefront_t4_fail", base_lat=25.0, base_err=0.0)

    # 1. Break demo target service and do NOT heal (wrong fix applied)
    break_service("paymentservice", latency_ms=1850.0, error_rate=0.42)

    try:
        verifier = VerifierAgent(mode="replay")
        verify_task = {
            "id": "task_v_02",
            "payload": {
                "intervention_id": "intv_01",
                "runbook_id": "rb_rollback",
                "target_service": "paymentservice",
            },
        }

        result, trace = verifier.run(
            graph=graph,
            incident_id="inc_t4_02",
            verify_task=verify_task,
            window_seconds=0.15,
            poll_step_seconds=0.03,
        )

        # Assertions
        assert result["observed_outcome"] == "failed"
        assert result["status"] == "failed"
        assert result["closed_incident"] is None
        assert graph.closed is False
        # Procedural memory: fail count incremented from 1.0 to 2.0; success count unchanged
        assert graph.runbook_counts["rb_rollback"]["fail"] == 2.0
        assert graph.runbook_counts["rb_rollback"]["success"] == 5.0
    finally:
        restore_service("paymentservice")


def test_t4_prometheus_down_inconclusive_and_memory_unchanged():
    """T4 Acceptance: With Prometheus down or unreachable, the outcome is inconclusive,
    the incident is NOT closed, and procedural memory counters are unchanged.
    """
    from app.agents.verifier import VerifierAgent
    from app.tenant_settings import update_tenant_settings
    from app.adapters.demo_target import restore_service

    # Ensure demo target is clean
    restore_service("paymentservice")

    tenant_id = "tenant_prom_unreachable"
    # Point tenant to unreachable port
    update_tenant_settings(tenant_id, {"telemetry_source": "prometheus", "prometheus_url": "http://127.0.0.1:59997"})

    graph = MockVerifierTenantGraph(tenant_id=tenant_id, base_lat=25.0, base_err=0.0)
    init_success = graph.runbook_counts["rb_rollback"]["success"]
    init_fail = graph.runbook_counts["rb_rollback"]["fail"]

    verifier = VerifierAgent(mode="replay")
    verify_task = {
        "id": "task_v_03",
        "payload": {
            "intervention_id": "intv_01",
            "runbook_id": "rb_rollback",
            "target_service": "paymentservice",
        },
    }

    result, trace = verifier.run(
        graph=graph,
        incident_id="inc_t4_03",
        verify_task=verify_task,
        window_seconds=0.10,
        poll_step_seconds=0.02,
    )

    # Assertions
    assert result["observed_outcome"] == "inconclusive"
    assert result["status"] == "inconclusive"
    assert "telemetry source unreachable" in result["metrics_summary"] or "inconclusive" in result["metrics_summary"].lower()
    assert result["closed_incident"] is None
    assert graph.closed is False

    # Procedural memory counters are COMPLETELY UNCHANGED
    assert graph.runbook_counts["rb_rollback"]["success"] == init_success
    assert graph.runbook_counts["rb_rollback"]["fail"] == init_fail


def test_t4_relative_baseline_comparison_with_floors():
    """T4: Ensure baseline comparison enforces +20% relative tolerance with absolute floors."""
    from app.agents.verifier import VerifierAgent
    from app.adapters.demo_target import restore_service

    # Test case A: High-baseline service (baseline latency 250ms, baseline error 0.05)
    # resolved floors: max(200.0, 250*1.20) = 300.0ms; max(0.02, 0.05*1.20) = 0.06
    # An observed error of 0.0 and latency ~20ms qualifies as resolved
    graph_high = MockVerifierTenantGraph(tenant_id="storefront_high_base", base_lat=250.0, base_err=0.05)
    restore_service("paymentservice")

    verifier = VerifierAgent(mode="replay")
    verify_task = {
        "id": "task_v_high",
        "payload": {
            "intervention_id": "intv_01",
            "runbook_id": "rb_rollback",
            "target_service": "paymentservice",
        },
    }

    res_high, _ = verifier.run(
        graph=graph_high,
        incident_id="inc_t4_high",
        verify_task=verify_task,
        window_seconds=0.05,
        poll_step_seconds=0.01,
    )
    assert res_high["observed_outcome"] == "resolved"

    # Test case B: Zero baseline service (0ms, 0% error)
    # Absolute floors must apply (latency_floor=200ms, error_floor=0.02)
    # instead of dividing by zero or requiring impossible 0.000ms
    graph_zero = MockVerifierTenantGraph(tenant_id="storefront_zero_base", base_lat=0.0, base_err=0.0)
    res_zero, _ = verifier.run(
        graph=graph_zero,
        incident_id="inc_t4_zero",
        verify_task=verify_task,
        window_seconds=0.05,
        poll_step_seconds=0.01,
    )
    assert res_zero["observed_outcome"] == "resolved"






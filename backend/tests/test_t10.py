import base64
import json
import time
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tenancy import TenantGraph
from app.actions.executors import (
    get_executor_for_action,
    clean_action_is_destructive,
    execute_action,
    KubernetesRolloutExecutor,
)
from app.adapters.topology import (
    parse_manifest_content,
    discover_topology_from_environment,
    fetch_topology_from_monitored_repo,
    apply_discovered_topology,
    ingest_opentelemetry_traces,
)


class MockT10GraphResult:
    def __init__(self, result_set: list[list[Any]] | None = None):
        self.result_set = result_set or []


class MockT10TenantGraph:
    """In-memory mock graph for T10 tests supporting edges, audit logs, and settings."""
    def __init__(self, tenant_id: str = "tenant_t10"):
        self.tenant_id = tenant_id
        self.edges: dict[tuple[str, str], dict[str, Any]] = {}
        self.audit_logs: list[dict[str, Any]] = []
        self.queries: list[tuple[str, dict]] = []

    def ping(self) -> bool:
        return True

    def query(self, cypher: str, params: dict | None = None):
        params = params or {}
        self.queries.append((cypher, params))
        clean = " ".join(cypher.split())

        # 1. Edge creation and property update
        if "MERGE (caller:Service" in clean and "DEPENDS_ON" in clean:
            caller = params.get("caller")
            callee = params.get("callee")
            if caller and callee:
                key = (caller, callee)
                if key not in self.edges:
                    self.edges[key] = {
                        "caller": caller,
                        "callee": callee,
                        "protocol": params.get("protocol", "HTTP"),
                        "criticality": params.get("criticality", "high"),
                        "verified": params.get("verified", False),
                        "source": params.get("source", "manifest"),
                    }
                # Check for OTel updates
                if "SET r.verified = true" in clean:
                    self.edges[key]["verified"] = True
                    self.edges[key]["source"] = "otel_trace"
                    self.edges[key]["last_observed_ts"] = params.get("ts", time.time())
                return MockT10GraphResult([[caller, callee]])

        # 2. AuditLog query
        if "MERGE (audit:AuditLog" in clean:
            self.audit_logs.append(dict(params))
            return MockT10GraphResult([[params.get("key")]])

        if "MATCH (audit:AuditLog {idempotency_key: $key})" in clean:
            key = params.get("key")
            for log in self.audit_logs:
                if log.get("key") == key:
                    return MockT10GraphResult([[
                        log.get("key"),
                        log.get("aid"),
                        log.get("iid"),
                        log.get("kind"),
                        log.get("approver"),
                        log.get("ts"),
                        log.get("status"),
                        log.get("hash"),
                        log.get("details"),
                    ]])
            return MockT10GraphResult([])

        return MockT10GraphResult([])


from app.security import register_api_key

ADMIN_API_KEY = "admin_key_t10_test_9999"


@pytest.fixture(autouse=True)
def setup_api_keys():
    register_api_key(raw_key=ADMIN_API_KEY, tenant_id="acme_retail", role="admin", persist=False)
    register_api_key(raw_key=ADMIN_API_KEY, tenant_id="sandbox_tenant", role="admin", persist=False)
    register_api_key(raw_key=ADMIN_API_KEY, tenant_id="storefront", role="admin", persist=False)


@pytest.fixture
def client():
    return TestClient(app)


def test_kubernetes_rollout_executor_resolution_and_execution():
    """Verify Kubernetes executor routing, simulated execution, and action destructiveness."""
    # 1. Routing resolution
    for kind in ("k8s_rollback", "kubernetes_rollout_undo", "rollout_undo", "kubectl_undo", "k8s_rollout_undo"):
        executor = get_executor_for_action(kind)
        assert isinstance(executor, KubernetesRolloutExecutor), f"Action '{kind}' must route to KubernetesRolloutExecutor"
        assert clean_action_is_destructive(kind) is True, f"Action '{kind}' must be marked destructive"

    # 2. Dry run execution
    k8s_exec = KubernetesRolloutExecutor()
    dry_receipt = k8s_exec.execute(
        graph=None,
        incident_id="inc_k8s_01",
        action_id="act_k8s_dry",
        action_kind="k8s_rollback",
        payload={"target_service": "paymentservice", "namespace": "staging"},
        approver="operator_bob",
        dry_run=True,
    )
    assert dry_receipt.status == "dry_run"
    assert dry_receipt.details.get("dry_run") is True
    assert "kubectl rollout undo deployment/paymentservice -n staging" in dry_receipt.details["command"]

    # 3. Live/Simulated execution
    receipt = k8s_exec.execute(
        graph=None,
        incident_id="inc_k8s_01",
        action_id="act_k8s_live",
        action_kind="kubernetes_rollout_undo",
        payload={"target_service": "paymentservice", "namespace": "prod", "cluster": "us-east1-cluster"},
        approver="operator_alice",
        dry_run=False,
    )
    assert receipt.status == "executed"
    assert receipt.details.get("healed") is True
    assert receipt.details.get("target_service") == "paymentservice"
    assert receipt.details.get("namespace") == "prod"
    assert receipt.audit_hash is not None
    assert len(receipt.audit_hash) == 64  # sha256 hex


def test_kubernetes_executor_idempotency_and_audit():
    """Verify that multiple executions with the same idempotency key are skipped and audited."""
    graph = MockT10TenantGraph("storefront_k8s_test")
    k8s_exec = KubernetesRolloutExecutor()
    custom_key = f"k8s:test:idempotency:{time.time()}"

    r1 = k8s_exec.execute(
        graph=graph,
        incident_id="inc_k8s_idem",
        action_id="act_k8s_01",
        action_kind="k8s_rollback",
        payload={"target_service": "cartservice", "namespace": "default"},
        approver="sre_lead",
        dry_run=False,
        idempotency_key=custom_key,
    )
    assert r1.status == "executed"
    assert r1.idempotency_key == custom_key
    assert len(graph.audit_logs) == 1

    # Second execution must skip idempotently
    r2 = k8s_exec.execute(
        graph=graph,
        incident_id="inc_k8s_idem",
        action_id="act_k8s_01",
        action_kind="k8s_rollback",
        payload={"target_service": "cartservice", "namespace": "default"},
        approver="sre_lead",
        dry_run=False,
        idempotency_key=custom_key,
    )
    assert r2.status == "idempotent_skip"
    assert r2.idempotency_key == custom_key


def test_parse_manifest_content_and_dynamic_manifests():
    """Verify dynamic manifests parsing from Docker Compose or Kubernetes configurations."""
    sample_compose = """
version: '3.8'
services:
  frontend:
    image: frontend:v1
    environment:
      - CHECKOUTSERVICE_ADDR=checkoutservice:5050
      - PRODUCTCATALOGSERVICE_ADDR=productcatalogservice:3550
  checkoutservice:
    image: checkoutservice:v1
    environment:
      - PAYMENTSERVICE_ADDR=paymentservice:50051
      - EMAILSERVICE_HOST=emailservice
  paymentservice:
    image: paymentservice:v1
"""
    # 1. Manifest parsing: edges default to unverified until actual traces observe them
    edges = parse_manifest_content(sample_compose, verified=False, source="manifest")
    assert len(edges) == 4
    edge_map = {(e.caller, e.callee): e for e in edges}
    assert ("frontend", "checkoutservice") in edge_map
    assert ("frontend", "productcatalogservice") in edge_map
    assert ("checkoutservice", "paymentservice") in edge_map
    assert ("checkoutservice", "emailservice") in edge_map

    for e in edges:
        assert e.verified is False
        assert e.source == "manifest"

    # 2. Dynamic fetch from monitored repo with fallback
    fallback_edges, meta = fetch_topology_from_monitored_repo(
        repo="my-org/my-service-repo",
        token=None,  # No token forces fallback to local target manifest
        branch="main",
    )
    assert len(fallback_edges) > 0
    assert meta["source"] == "local_target_manifest"
    assert meta["status"] == "fallback_local"


def test_fetch_topology_from_github_api(monkeypatch):
    """Verify fetching manifests dynamically through GitHub API when token is provided."""
    sample_remote_yaml = """
services:
  gateway:
    environment:
      - AUTH_ADDR=auth-service
  auth-service:
    environment:
      - DATABASE_HOST=db-service
"""
    b64_content = base64.b64encode(sample_remote_yaml.encode("utf-8")).decode("utf-8")

    class MockRemoteResponse:
        status_code = 200
        def json(self):
            return {
                "encoding": "base64",
                "content": b64_content,
                "name": "target_compose.yml",
                "path": "data/target_compose.yml",
            }

    import httpx
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kwargs: MockRemoteResponse())

    edges, meta = fetch_topology_from_monitored_repo(
        repo="org/monitored-microservices",
        token="ghp_test_token_123456",
        branch="develop",
        candidate_paths=["data/target_compose.yml"],
        verified=False,
    )
    assert meta["status"] == "success"
    assert meta["source"] == "github_api"
    assert len(edges) == 2
    pairs = {(e.caller, e.callee) for e in edges}
    assert ("gateway", "auth-service") in pairs
    assert ("auth-service", "db-service") in pairs


def test_opentelemetry_trace_edge_verification():
    """Verify that only edges crossed by actual OpenTelemetry traces are marked verified=True."""
    graph = MockT10TenantGraph("storefront_otel_test")

    # 1. Populate unverified manifest edges
    edges = [
        parse_manifest_content("""
services:
  frontend:
    environment:
      - CHECKOUT_ADDR=checkoutservice
      - CATALOG_ADDR=productcatalogservice
  checkoutservice:
    environment:
      - PAYMENT_ADDR=paymentservice
""", verified=False, source="manifest")
    ]
    flat_edges = [e for sublist in edges for e in sublist]
    apply_discovered_topology(graph, flat_edges)

    assert len(graph.edges) == 3
    for edge in graph.edges.values():
        assert edge["verified"] is False
        assert edge["source"] == "manifest"

    # 2. Ingest OpenTelemetry spans: frontend -> checkoutservice AND checkoutservice -> paymentservice
    # Note: productcatalogservice receives no traces
    sample_spans = [
        # Flat format
        {"caller": "frontend", "callee": "checkoutservice", "timestamp": time.time()},
        # Standard OTel attributes format
        {
            "name": "HTTP POST /process_payment",
            "attributes": [
                {"key": "service.name", "value": {"stringValue": "checkoutservice"}},
                {"key": "peer.service", "value": {"stringValue": "paymentservice"}},
                {"key": "http.status_code", "value": {"intValue": 200}},
            ],
        },
    ]

    result = ingest_opentelemetry_traces(graph, sample_spans)
    assert result["status"] == "success"
    assert result["processed_spans"] == 2
    assert result["verified_edges_count"] == 2

    # Check that observed edges are now verified=True with source='otel_trace'
    assert graph.edges[("frontend", "checkoutservice")]["verified"] is True
    assert graph.edges[("frontend", "checkoutservice")]["source"] == "otel_trace"

    assert graph.edges[("checkoutservice", "paymentservice")]["verified"] is True
    assert graph.edges[("checkoutservice", "paymentservice")]["source"] == "otel_trace"

    # Unobserved edge remains verified=False with source='manifest'
    assert graph.edges[("frontend", "productcatalogservice")]["verified"] is False
    assert graph.edges[("frontend", "productcatalogservice")]["source"] == "manifest"


def test_telemetry_trace_ingest_api_endpoint(client):
    """Verify POST /api/telemetry/traces/ingest endpoint."""
    payload = {
        "spans": [
            {"caller": "frontend", "callee": "cartservice"},
            {"caller": "cartservice", "callee": "redis-cart"},
        ]
    }
    resp = client.post("/api/telemetry/traces/ingest?tenant=storefront", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["processed_spans"] == 2
    assert data["verified_edges_count"] == 2
    verified_pairs = {(e["caller"], e["callee"]) for e in data["verified_edges"]}
    assert ("frontend", "cartservice") in verified_pairs
    assert ("cartservice", "redis-cart") in verified_pairs


def test_tenant_onboarding_api_full_flow(client, monkeypatch):
    """Verify POST /api/tenants/{tenant_id}/onboard with GitHub, Prometheus, and Real vs Seeded audit report."""
    import httpx

    # Mock external GitHub and Prometheus calls as live
    class MockGitHubResponse:
        status_code = 200
        def json(self):
            return {"name": "monitored-repo", "permissions": {"admin": True, "push": True}}

    class MockPromResponse:
        status_code = 200
        def json(self):
            return {"status": "success", "data": {"resultType": "vector", "result": []}}

    def mock_get(self, url, *args, **kwargs):
        if "api.github.com" in url:
            return MockGitHubResponse()
        elif "api/v1/query" in url:
            return MockPromResponse()
        return MockPromResponse()

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    onboard_payload = {
        "tenant_name": "Acme Retail",
        "github_repo": "acme/retail-store",
        "github_token": "ghp_acme_token_secret_123",
        "github_workflow": "remediate.yml",
        "github_ref": "main",
        "path_to_service": {
            "services/payment/": "paymentservice",
            "services/cart/": "cartservice",
        },
        "webhook_secret": "whsec_acme_retail_secure_99",
        "slack_webhook_url": "https://hooks.slack.com/services/T00/B00/acme",
        "prometheus_url": "http://prometheus.acme.internal:9090",
        "k8s_cluster": "acme-k8s-prod",
        "k8s_namespace": "production",
        "run_test_alert": True,
        "dry_run_default": False,
    }

    # Execute onboarding request with admin authorization
    headers = {"X-API-Key": ADMIN_API_KEY}
    resp = client.post("/api/tenants/acme_retail/onboard", json=onboard_payload, headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "success"
    assert body["tenant_id"] == "acme_retail"

    # Verify audit report breakdown
    audit = body["audit_report"]
    assert audit["tenant_id"] == "acme_retail"
    assert "provenance_breakdown" in audit

    breakdown = audit["provenance_breakdown"]
    # GitHub must be classified as real
    assert breakdown["github"]["classification"] == "real"
    assert breakdown["github"]["real_percentage"] == 100.0

    # Telemetry must be classified as live_prometheus
    assert breakdown["telemetry"]["classification"] == "live_prometheus"
    assert breakdown["telemetry"]["real_percentage"] == 100.0

    # Alerting must be live_configured with test alert executed
    assert breakdown["alerting_and_webhooks"]["classification"] == "live_configured"
    assert breakdown["alerting_and_webhooks"]["real_percentage"] == 100.0
    assert breakdown["alerting_and_webhooks"]["details"]["test_alert_executed"] is True

    # Real vs seeded percentages must sum to 100%
    assert audit["overall_real_percentage"] + audit["overall_seeded_percentage"] == 100.0
    assert audit["overall_real_percentage"] >= 75.0

    # Settings returned must have masked secrets
    settings = body["settings"]
    assert settings["github_token"].startswith("ghp_***") or settings["github_token"].startswith("ghp_")
    assert "acme" in settings["k8s_cluster"]
    assert settings["k8s_namespace"] == "production"


def test_tenant_onboarding_fallback_unconfigured(client):
    """Verify onboarding an unconfigured/mock tenant produces honest seeded accounting."""
    onboard_payload = {
        "tenant_name": "Sandbox Tenant",
        "github_repo": None,
        "github_token": None,
        "prometheus_url": None,
        "webhook_secret": None,
        "run_test_alert": True,
    }

    headers = {"X-API-Key": ADMIN_API_KEY}
    resp = client.post("/api/tenants/sandbox_tenant/onboard", json=onboard_payload, headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    audit = body["audit_report"]
    breakdown = audit["provenance_breakdown"]

    # GitHub and Telemetry must reflect seeded/mock fallback
    assert breakdown["github"]["classification"] == "seeded_mock"
    assert breakdown["github"]["real_percentage"] == 0.0

    assert breakdown["telemetry"]["classification"] == "seeded_simulator"
    assert breakdown["telemetry"]["real_percentage"] == 0.0

    # Real percentage should reflect only local synthetic resources
    assert audit["overall_real_percentage"] < 50.0
    assert audit["overall_seeded_percentage"] > 50.0

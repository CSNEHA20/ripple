import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import load_scenario, seed_historical_incidents
from app.mcp_server import mcp_server


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant for M11 tests."""
    tenant = "m11_test_tenant"
    bootstrap_tenant_all(tenant)
    graph = TenantGraph(tenant)
    seed_historical_incidents(graph)
    return tenant


def test_tenant_middleware_header_and_isolation(client, seeded_tenant):
    """M11 TenantMiddleware:
    1. Extracts X-Tenant header, passes it to request state, and returns X-Tenant in response headers.
    2. Fallback to query param or default storefront if header not supplied.
    """
    # 1. Custom tenant header
    resp = client.get("/health", headers={"X-Tenant": "payments"})
    assert resp.status_code == 200
    assert resp.headers.get("x-tenant") == "payments"

    # 2. Query param fallback
    resp2 = client.get("/health?tenant=alpha_tenant")
    assert resp2.status_code == 200
    assert resp2.headers.get("x-tenant") == "alpha_tenant"

    # 3. Default fallback
    resp3 = client.get("/health")
    assert resp3.status_code == 200
    assert resp3.headers.get("x-tenant") == "storefront"


def test_m11_api_routes(client, seeded_tenant):
    """Test standard M11 API routes: bootstrap, load scenario, run crew, list incidents, get incident, close."""
    headers = {"X-Tenant": seeded_tenant}

    # 1. Bootstrap tenant
    b_resp = client.post(f"/tenants/{seeded_tenant}/bootstrap")
    assert b_resp.status_code == 200

    # 2. Load scenario
    load_resp = client.post("/scenarios/sc_repeated_01/load", headers=headers)
    assert load_resp.status_code == 200
    assert load_resp.json().get("scenario_id") == "sc_repeated_01"

    # 3. Run incident crew
    crew_resp = client.post(
        "/incidents",
        json={
            "alert": {"service": "paymentservice", "text": "High HTTP 500 error rate on checkout payment authorize"},
            "scenario_id": "sc_repeated_01",
            "auto_approve": True,
        },
        headers=headers,
    )
    assert crew_resp.status_code == 200
    crew_data = crew_resp.json()
    assert crew_data["status"] == "success"
    inc_id = crew_data["data"]["incident_id"]
    trace = crew_data.get("trace", {})
    assert "steps" in trace

    # 4. List incidents
    list_resp = client.get("/incidents", headers=headers)
    assert list_resp.status_code == 200
    inc_list = list_resp.json().get("incidents", [])
    assert any(i["id"] == inc_id for i in inc_list)

    # 5. Get incident blackboard
    get_resp = client.get(f"/incidents/{inc_id}", headers=headers)
    assert get_resp.status_code == 200
    bb = get_resp.json().get("blackboard", {})
    assert "tasks" in bb
    assert "agent_runs" in bb

    # 6. Close incident direct
    close_resp = client.post(
        f"/incidents/{inc_id}/close",
        json={"observed_outcome": "resolved", "handled_by": "test_operator"},
        headers=headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json().get("status") == "closed"


def test_m11_memory_stats(client, seeded_tenant):
    """Test GET /memory/stats compiles counts, runbook procedural rates, and learning curve."""
    headers = {"X-Tenant": seeded_tenant}
    resp = client.get("/memory/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json().get("data", {})

    # Check counts
    counts = data.get("counts", {})
    assert "incidents" in counts
    assert "observations" in counts
    assert "hypotheses" in counts
    assert "evidence" in counts
    assert "interventions" in counts
    assert "outcomes" in counts

    # Check runbooks procedural memory
    runbooks = data.get("runbooks", [])
    assert len(runbooks) > 0
    assert all("historical_success_rate" in rb for rb in runbooks)

    # Check learning curve
    learning_curve = data.get("learning_curve", [])
    assert isinstance(learning_curve, list)


def test_m11_benchmark_api(client):
    """Test POST /benchmark/run and GET /benchmark/report."""
    # 1. Run quick benchmark on 2 scenarios
    run_resp = client.post(
        "/benchmark/run",
        json={
            "scenarios": ["sc_repeated_01", "sc_stale_trap_01"],
            "modes": ["memory_on", "memory_off"],
            "mode": "replay",
        },
    )
    assert run_resp.status_code == 200
    bench_data = run_resp.json().get("data", {})
    assert "summary" in bench_data
    assert "runs" in bench_data
    assert "calibration_status" in bench_data

    # 2. Get benchmark report
    rep_resp = client.get("/benchmark/report")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert rep_data["status"] == "success"
    assert "markdown_report" in rep_data
    assert "# Ripple Benchmark Evaluation Report" in rep_data["markdown_report"]


def test_mcp_server_tools_and_execution(seeded_tenant):
    """Test MCP Server:
    1. Tool registry exposes all 12 tools (8 M4 tools + recall, rank_hypotheses, counterfactual_blast, ask).
    2. Simulated MCP client invokes tools and receives structured JSON responses.
    """
    import anyio

    async def _run():
        tools = await mcp_server.list_tools()
        tool_names = [t.name for t in tools]

        expected_tools = [
            "blast_radius",
            "upstream_suspects",
            "recent_changes",
            "service_health",
            "who_knows",
            "similar_incidents",
            "criticality_ranking",
            "path_between",
            "recall",
            "rank_hypotheses",
            "counterfactual_blast",
            "ask",
        ]
        for exp in expected_tools:
            assert exp in tool_names, f"Expected MCP tool '{exp}' not found in registered tools: {tool_names}"

        # 1. Test blast_radius
        res_blast = await mcp_server.call_tool(
            "blast_radius",
            {"service": "paymentservice", "tenant": seeded_tenant},
        )
        assert not res_blast.is_error
        payload_blast = json.loads(res_blast.content[0].text)
        blast_data = payload_blast.get("data", payload_blast)
        assert "service" in blast_data
        assert "affected_services" in blast_data

        # 2. Test recall
        res_recall = await mcp_server.call_tool(
            "recall",
            {"alert_text": "Payment authorization timeout", "tenant": seeded_tenant},
        )
        assert not res_recall.is_error
        payload_recall = json.loads(res_recall.content[0].text)
        assert "data" in payload_recall
        assert "similar_incidents" in payload_recall["data"]

        # 3. Test rank_hypotheses
        res_hyp = await mcp_server.call_tool(
            "rank_hypotheses",
            {"alerting_service": "paymentservice", "alert_text": "Payment error", "tenant": seeded_tenant},
        )
        assert not res_hyp.is_error
        payload_hyp = json.loads(res_hyp.content[0].text)
        assert "hypotheses" in payload_hyp["data"]

        # 4. Test ask (Company-brain Q&A)
        res_ask = await mcp_server.call_tool(
            "ask",
            {"question": "Who knows the payment service?", "tenant": seeded_tenant},
        )
        assert not res_ask.is_error
        payload_ask = json.loads(res_ask.content[0].text)
        assert "answer" in payload_ask["data"]
        assert "sources" in payload_ask["data"]

    anyio.run(_run)

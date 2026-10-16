import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import load_scenario, seed_historical_incidents
from app.tools.registry import (
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    get_tool_schemas,
    execute_tool,
)
from app.tools.blast_radius import blast_radius
from app.tools.root_cause import upstream_suspects
from app.tools.paths import path_between
from app.tools.criticality import criticality_ranking
from app.tools.people import who_knows
from app.tools.changes import recent_changes
from app.tools.incidents import (
    service_health,
    similar_incidents,
    rank_runbooks,
    check_applicability,
    counterfactual_blast,
)


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant with services, dependencies, and seed historical incidents."""
    tenant_id = "storefront_m4_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def test_tool_schemas_and_registry():
    """Verify all 11 M4 tools are registered with complete JSON schemas."""
    expected_tools = {
        "blast_radius",
        "upstream_suspects",
        "path_between",
        "criticality_ranking",
        "who_knows",
        "recent_changes",
        "service_health",
        "similar_incidents",
        "rank_runbooks",
        "check_applicability",
        "counterfactual_blast",
    }
    assert expected_tools.issubset(set(TOOL_FUNCTIONS.keys()))

    schemas = get_tool_schemas()
    assert len(schemas) >= 11
    schema_names = {s["name"] for s in schemas}
    assert expected_tools.issubset(schema_names)

    for s in schemas:
        assert "name" in s
        assert "description" in s
        assert "parameters" in s
        assert s["parameters"]["type"] == "object"


def test_blast_radius(seeded_tenant: TenantGraph):
    """Verify blast_radius finds all downstream services affected if paymentservice fails."""
    res = blast_radius(seeded_tenant, "paymentservice", max_depth=4)
    data = res.data
    trace = res.trace

    assert data["service"] == "paymentservice"
    assert data["total_affected"] >= 2

    # Checkoutservice calls paymentservice (hop 1)
    # Frontend calls checkoutservice (hop 2)
    aff_map = {item["service"]: item for item in data["affected_services"]}
    assert "checkoutservice" in aff_map
    assert aff_map["checkoutservice"]["hops"] == 1
    assert "frontend" in aff_map
    assert aff_map["frontend"]["hops"] == 2

    # Verify trace provenance
    assert len(trace.steps) == 1
    step = trace.steps[0]
    assert step.tool == "blast_radius"
    assert "paymentservice" in step.node_ids
    assert "checkoutservice" in step.node_ids
    assert "frontend" in step.node_ids
    assert "checkoutservice->paymentservice" in step.edge_ids
    assert "MATCH" in step.cypher


def test_upstream_suspects(seeded_tenant: TenantGraph):
    """Verify upstream_suspects finds all dependencies reachable from frontend."""
    res = upstream_suspects(seeded_tenant, "frontend", max_depth=3)
    data = res.data
    trace = res.trace

    assert data["alerting_service"] == "frontend"
    suspect_names = {item["service"] for item in data["suspects"]}

    # Hop 0: frontend itself
    assert "frontend" in suspect_names

    # Hop 1 dependencies of frontend:
    assert "checkoutservice" in suspect_names
    assert "cartservice" in suspect_names
    assert "productcatalogservice" in suspect_names

    # Hop 2 transitive dependencies:
    assert "paymentservice" in suspect_names
    assert "redis-cart" in suspect_names

    # Verify trace
    assert len(trace.steps) == 1
    step = trace.steps[0]
    assert step.tool == "upstream_suspects"
    assert "paymentservice" in step.node_ids
    assert "frontend->checkoutservice" in step.edge_ids


def test_path_between(seeded_tenant: TenantGraph):
    """Verify path_between finds shortest dependency path between frontend and paymentservice."""
    res = path_between(seeded_tenant, "frontend", "paymentservice")
    data = res.data
    trace = res.trace

    assert data["path_exists"] is True
    assert data["hops"] == 2
    assert data["path_nodes"] == ["frontend", "checkoutservice", "paymentservice"]
    assert len(data["path_edges"]) == 2

    # Verify reverse path does NOT exist (paymentservice does not call frontend)
    rev_res = path_between(seeded_tenant, "paymentservice", "frontend")
    assert rev_res.data["path_exists"] is False
    assert rev_res.data["hops"] == -1

    # Verify identity path (0 hops)
    self_res = path_between(seeded_tenant, "frontend", "frontend")
    assert self_res.data["path_exists"] is True
    assert self_res.data["hops"] == 0

    assert len(trace.steps) == 1
    step = trace.steps[0]
    assert step.node_ids == ["frontend", "checkoutservice", "paymentservice"]


def test_criticality_ranking(seeded_tenant: TenantGraph):
    """Verify PageRank criticality ranking ranks services by dependency fan-in."""
    res = criticality_ranking(seeded_tenant)
    data = res.data
    trace = res.trace

    assert data["total_services"] >= 11
    ranked = data["ranked_services"]
    assert len(ranked) >= 11

    # Check top tier services
    top_services = [item["service"] for item in ranked[:6]]
    # productcatalogservice, checkoutservice, paymentservice, cartservice have high in-degree
    assert any(s in top_services for s in ["productcatalogservice", "checkoutservice", "paymentservice", "cartservice"])

    # Sum of scores should be normalized to ~1.0
    total_score = sum(item["score"] for item in ranked)
    assert 0.95 <= total_score <= 1.05

    assert len(trace.steps) == 1
    assert trace.steps[0].tool == "criticality_ranking"


def test_who_knows(seeded_tenant: TenantGraph):
    """Verify who_knows identifies ianlewis as top owner/expert of paymentservice."""
    res = who_knows(seeded_tenant, "paymentservice", k=3)
    data = res.data
    trace = res.trace

    assert data["service"] == "paymentservice"
    experts = data["experts"]
    assert len(experts) >= 1

    top_expert = experts[0]
    assert top_expert["person"] == "ianlewis"
    assert top_expert["is_owner"] is True
    assert top_expert["commits"] >= 40
    assert top_expert["recency_score"] > 0.0

    assert len(trace.steps) == 1
    assert "ianlewis" in trace.steps[0].node_ids


def test_recent_changes(seeded_tenant: TenantGraph):
    """Verify recent_changes retrieves deployments from window."""
    alert_ts = 1700000000.0
    load_scenario(seeded_tenant, "sc_repeated_01", alert_ts=alert_ts)

    res = recent_changes(seeded_tenant, "paymentservice", hours=24.0, as_of=alert_ts)
    data = res.data
    trace = res.trace

    assert data["service"] == "paymentservice"
    assert len(data["deployments"]) >= 1
    versions = [d["version"] for d in data["deployments"]]
    assert "v1.5.0" in versions

    assert len(trace.steps) == 1
    assert any("dep_" in nid for nid in trace.steps[0].node_ids)


def test_service_health(seeded_tenant: TenantGraph):
    """Verify service_health separates failing, degraded, and normal contradicting evidence."""
    alert_ts = 1700000000.0
    load_scenario(seeded_tenant, "sc_repeated_01", alert_ts=alert_ts)

    services_to_check = ["paymentservice", "checkoutservice", "cartservice", "currencyservice"]
    res = service_health(seeded_tenant, services_to_check, ts=alert_ts)
    data = res.data
    trace = res.trace

    assert "paymentservice" in data["failing_services"]
    assert "checkoutservice" in data["degraded_services"]

    # Cart and Currency services are healthy (authentic contradicting evidence!)
    assert "cartservice" in data["healthy_services"]
    assert "currencyservice" in data["healthy_services"]

    assert len(trace.steps) == 1
    step = trace.steps[0]
    assert "paymentservice" in step.node_ids


def test_similar_incidents_and_runbooks(seeded_tenant: TenantGraph):
    """Verify similar_incidents recalls past historical incidents and rank_runbooks scores them."""
    # 1. Similar incidents
    res = similar_incidents(
        seeded_tenant,
        alert_text="paymentservice credit card authorization latency high",
        services=["paymentservice", "checkoutservice"],
        k=3,
    )
    assert len(res.data["matches"]) >= 1
    top_match = res.data["matches"][0]
    assert top_match["similarity_score"] > 0.4
    assert top_match["resolved_runbook"] is not None

    # 2. Rank runbooks
    rb_res = rank_runbooks(seeded_tenant)
    rbs = rb_res.data["runbooks"]
    assert len(rbs) >= 5
    for rb in rbs:
        assert 0.0 <= rb["historical_success_rate"] <= 1.0


def test_check_applicability(seeded_tenant: TenantGraph):
    """Verify check_applicability blocks stale fixes after an ArchitectureChange."""
    alert_ts = 1700100000.0
    load_scenario(seeded_tenant, "sc_stale_trap_01", alert_ts=alert_ts)

    # 1. Clean runbook with no closed dependencies
    clean_res = check_applicability(seeded_tenant, "rb_rollback")
    assert clean_res.data["applicable"] is True

    # 2. Stale runbook assuming cartservice->redis-cart (closed by ac_cart_redis_decouple)
    stale_res = check_applicability(seeded_tenant, "rb_cache_flush")
    assert stale_res.data["applicable"] is False
    assert len(stale_res.data["rejection_reasons"]) >= 1
    why_not = stale_res.data["why_not_recommended"]
    assert why_not is not None
    assert why_not["closed_edge"] == "cartservice->redis-cart"
    assert "ac_cart_redis_decouple" in why_not["architecture_change_id"]


def test_counterfactual_blast(seeded_tenant: TenantGraph):
    """Verify counterfactual_blast computes set difference between observed and hypothetical blast."""
    res = counterfactual_blast(
        seeded_tenant,
        observed_incident_id="inc_sc_hist_payment_bad_deploy",
        hypothetical_service="currencyservice",
    )
    data = res.data
    trace = res.trace

    assert data["hypothetical_service"] == "currencyservice"
    diff = data["diff"]
    assert "only_observed" in diff
    assert "only_hypothetical" in diff
    assert "both" in diff

    # Trace merges steps from blast_radius
    assert len(trace.steps) >= 2


def test_api_tools_endpoints():
    """Verify FastAPI routes for listing tools and executing tools with trace."""
    client = TestClient(app)

    # 1. List tools
    res = client.get("/api/tools")
    assert res.status_code == 200
    tools = res.json()["tools"]
    assert len(tools) >= 11

    # 2. Execute blast_radius tool
    exec_res = client.post(
        "/api/tools/blast_radius/execute",
        headers={"X-Tenant": "storefront"},
        json={"arguments": {"service": "paymentservice", "max_depth": 3}},
    )
    assert exec_res.status_code == 200
    data = exec_res.json()
    assert "data" in data
    assert "trace" in data
    assert data["data"]["service"] == "paymentservice"
    assert len(data["trace"]["steps"]) >= 1
    assert data["trace"]["steps"][0]["tool"] == "blast_radius"

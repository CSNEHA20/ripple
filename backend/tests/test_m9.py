import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import load_scenario, seed_historical_incidents
from app.counterfactual.uncertainty import assess_uncertainty
from app.counterfactual.engine import (
    compute_counterfactual,
    resolve_as_of_timestamp,
    get_observed_affected_services,
)
from app.tools.incidents import counterfactual_blast


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant with services, dependencies, and historical incidents."""
    tenant_id = "storefront_m9_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def clean_transient_nodes(graph: TenantGraph) -> None:
    """Clear transient test nodes while preserving base services and people."""
    graph.query(
        "MATCH (n) WHERE n:MetricSnapshot OR n:Deployment OR n:ArchitectureChange "
        "OR n:Alert OR n:Hypothesis OR n:Evidence OR n:Task OR n:Conflict "
        "OR n:Action OR n:AgentRun DETACH DELETE n"
    )


def test_uncertainty_fully_verified_subgraph(seeded_tenant):
    """Verify uncertainty evaluation on fully verified microservice topology.
    When all dependencies have verified=true and deps_known=true,
    no lower bound warning is raised and is_lower_bound is False.
    """
    clean_transient_nodes(seeded_tenant)
    services = ["frontend", "checkoutservice", "paymentservice", "productcatalogservice"]

    data, trace = assess_uncertainty(seeded_tenant, services=services, as_of=None)

    assert data["has_uncertainty"] is False
    assert data["is_lower_bound"] is False
    assert data["unverified_edges_count"] == 0
    assert data["unknown_deps_count"] == 0
    assert data["lower_bound_warning"] == ""
    assert "exact topological bound" in data["explanation"]
    assert len(trace.steps) == 1
    assert trace.steps[0].tool == "counterfactual_uncertainty"


def test_uncertainty_with_unverified_edges_and_unknown_deps(seeded_tenant):
    """Verify uncertainty engine identifies unverified edges and incomplete dependency catalogs,
    flagging the hypothetical blast radius as a lower bound.
    """
    clean_transient_nodes(seeded_tenant)

    # 1. Inject an unverified edge
    seeded_tenant.query(
        """
        MATCH (a:Service {name: 'frontend'})
        MATCH (b:Service {name: 'shippingservice'})
        CREATE (a)-[r:DEPENDS_ON {
            protocol: 'gRPC',
            criticality: 'medium',
            valid_from: 0.0,
            verified: false,
            source: 'inferred_doc'
        }]->(b)
        """
    )

    # 2. Inject a service with deps_known = false
    seeded_tenant.query(
        """
        MERGE (s:Service {name: 'legacy-analytics'})
        SET s.tier = 'tier-3',
            s.deps_known = false,
            s.description = 'Uncataloged legacy analytics pipeline'
        """
    )

    services = ["frontend", "shippingservice", "legacy-analytics"]
    data, trace = assess_uncertainty(seeded_tenant, services=services, as_of=None)

    assert data["has_uncertainty"] is True
    assert data["is_lower_bound"] is True
    assert data["unverified_edges_count"] >= 1
    assert any(e["edge"] == "frontend->shippingservice" for e in data["unverified_edges"])
    assert data["unknown_deps_count"] >= 1
    assert "legacy-analytics" in data["unknown_deps_services"]
    assert "LOWER BOUND" in data["lower_bound_warning"]

    # Cleanup injected nodes/edges
    seeded_tenant.query(
        "MATCH (:Service {name: 'frontend'})-[r:DEPENDS_ON {source: 'inferred_doc'}]->(:Service) DELETE r"
    )
    seeded_tenant.query("MATCH (s:Service {name: 'legacy-analytics'}) DETACH DELETE s")


def test_counterfactual_engine_diff_and_paths(seeded_tenant):
    """Verify compute_counterfactual computes set difference (only_observed, only_hypothetical, both),
    multi-hop paths to hypothetical failing service, and structured trace.
    """
    clean_transient_nodes(seeded_tenant)
    inc_id = "inc_inc_hist_01"

    # Actual incident: payment failed -> affected checkoutservice, frontend
    # Hypothetical question: What if currencyservice failed instead?
    data, trace = compute_counterfactual(
        graph=seeded_tenant,
        observed_incident_id=inc_id,
        hypothetical_service="currencyservice",
        as_of="incident_time",
        compare_with_now=False,
    )

    assert data["observed_incident_id"] == inc_id
    assert data["hypothetical_service"] == "currencyservice"
    assert "paymentservice" in data["observed_services"]
    assert "currencyservice" in data["hypothetical_services"]

    diff = data["diff"]
    assert "paymentservice" in diff["only_observed"]
    assert "currencyservice" in diff["only_hypothetical"]
    # Both checkoutservice and frontend call both paymentservice and currencyservice
    assert "checkoutservice" in diff["both"] or "frontend" in diff["both"]
    assert diff["overlap_count"] == len(diff["both"])
    assert diff["overlap_percentage"] > 0.0

    # Paths: verify every hypothetical affected service has a shortest path to currencyservice
    assert len(data["paths"]) >= 1
    for p in data["paths"]:
        assert p["impacted_service"] != "currencyservice"
        assert p["hops"] >= 1
        assert p["path_nodes"][-1] == "currencyservice"
        assert len(p["path_nodes"]) == p["hops"] + 1

    # Trace merges multiple steps
    tool_names = [s.tool for s in trace.steps]
    assert "blast_radius" in tool_names
    assert "path_between" in tool_names
    assert "criticality_ranking" in tool_names
    assert "who_knows" in tool_names
    assert "compute_counterfactual" in tool_names


def test_counterfactual_critical_owners(seeded_tenant):
    """Verify PageRank criticality ranking and recency-weighted ownership attribution
    for services in the counterfactual affected region.
    """
    clean_transient_nodes(seeded_tenant)
    inc_id = "inc_inc_hist_01"

    data, _ = compute_counterfactual(
        graph=seeded_tenant,
        observed_incident_id=inc_id,
        hypothetical_service="currencyservice",
        as_of="incident_time",
        compare_with_now=False,
    )

    critical_owners = data["critical_owners"]
    assert len(critical_owners) >= 1

    # Verify each critical owner contains structured metrics
    top_owner = critical_owners[0]
    assert "service" in top_owner
    assert "tier" in top_owner
    assert "criticality_rank" in top_owner
    assert "pagerank_score" in top_owner
    assert "primary_owner" in top_owner
    assert "experts" in top_owner
    assert isinstance(top_owner["in_hypothetical"], bool)
    assert isinstance(top_owner["in_observed"], bool)


def test_time_travel_incident_time_vs_now_architecture_change(seeded_tenant):
    """Verify the core differentiator:
    The same what-if produces DIFFERENT, EXPLAINABLE results for incident_time vs now!

    Scenario: sc_stale_trap_01 has architecture change 'ac_cart_redis_decouple'
    which closed the cartservice->redis-cart dependency 24h before alert.
    What if: hypothetical failure of 'redis-cart'.
    - At incident_time BEFORE decouple: cartservice & frontend are in blast radius.
    - At now (AFTER decouple): cartservice is decoupled, so blast radius shrinks to redis-cart alone.
    """
    clean_transient_nodes(seeded_tenant)
    sc_id = "sc_stale_trap_01"
    base_ts = 1700500000.0
    load_scenario(seeded_tenant, sc_id, alert_ts=base_ts)

    # Find the alert node created
    res = seeded_tenant.query("MATCH (a:Alert {scenario_id: $sid}) RETURN a.id LIMIT 1", {"sid": sc_id})
    alert_id = res.result_set[0][0]

    # Create dummy Incident node linked to alert and affected cartservice
    inc_id = "inc_test_time_travel_01"
    seeded_tenant.query(
        """
        MERGE (inc:Incident {id: $id})
        SET inc.title = 'Cart Redis Incident',
            inc.opened_ts = $opened_ts,
            inc.scenario_id = $sc_id
        WITH inc
        MATCH (a:Alert {id: $aid})
        MERGE (inc)-[:TRIGGERED_BY]->(a)
        WITH inc
        MATCH (c:Service {name: 'cartservice'})
        MERGE (inc)-[:AFFECTED {role: 'root'}]->(c)
        """,
        {
            "id": inc_id,
            "opened_ts": base_ts - (30.0 * 3600.0),  # 30 hours before alert (BEFORE ac_cart_redis_decouple)
            "sc_id": sc_id,
            "aid": alert_id,
        },
    )

    # 1. Run counterfactual as-of incident_time (BEFORE the decouple)
    data_hist, _ = compute_counterfactual(
        graph=seeded_tenant,
        observed_incident_id=inc_id,
        hypothetical_service="redis-cart",
        as_of="incident_time",
        compare_with_now=True,
    )

    hist_svcs = set(data_hist["hypothetical_services"])
    # Before the decouple, cartservice depended on redis-cart, so cartservice was impacted
    assert "redis-cart" in hist_svcs
    assert "cartservice" in hist_svcs

    # 2. Check time_travel_comparison
    tt = data_hist["time_travel_comparison"]
    assert tt is not None
    now_svcs = set(tt["now_services"])

    # Now (after decouple), cartservice no longer depends on redis-cart
    assert "cartservice" not in now_svcs
    assert "cartservice" in tt["removed_in_now"]
    assert any(ac["id"] == "ac_cart_redis_decouple" for ac in tt["architecture_changes"])
    assert "ac_cart_redis_decouple" in tt["explanation"]
    assert "NO LONGER impacted" in tt["explanation"]


def test_api_counterfactual_endpoints(seeded_tenant):
    """Test FastAPI routes: POST /counterfactual, POST /api/counterfactual, and GET /counterfactual/uncertainty."""
    clean_transient_nodes(seeded_tenant)
    client = TestClient(app)
    headers = {"X-Tenant": seeded_tenant.tenant_id}
    inc_id = "inc_inc_hist_01"

    # 1. POST /counterfactual
    resp1 = client.post(
        "/counterfactual",
        json={
            "observed_incident_id": inc_id,
            "hypothetical_service": "currencyservice",
            "as_of": "incident_time",
            "compare_with_now": True,
        },
        headers=headers,
    )
    assert resp1.status_code == 200
    res1_json = resp1.json()
    assert res1_json["status"] == "success"
    data1 = res1_json["data"]
    assert data1["hypothetical_service"] == "currencyservice"
    assert "diff" in data1
    assert "paths" in data1
    assert "critical_owners" in data1
    assert "uncertainty" in data1
    assert "trace" in res1_json

    # 2. POST /api/counterfactual (alias)
    resp2 = client.post(
        "/api/counterfactual",
        json={
            "observed_incident_id": inc_id,
            "hypothetical_service": "currencyservice",
            "as_of": "now",
            "compare_with_now": False,
        },
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "success"

    # 3. GET /counterfactual/uncertainty
    resp3 = client.get(
        "/counterfactual/uncertainty?services=frontend,paymentservice,checkoutservice",
        headers=headers,
    )
    assert resp3.status_code == 200
    u_data = resp3.json()["data"]
    assert u_data["has_uncertainty"] is False
    assert u_data["unverified_edges_count"] == 0


def test_counterfactual_blast_tool_wrapper(seeded_tenant):
    """Verify tool wrapper counterfactual_blast returns ToolResult with enriched M9 data."""
    clean_transient_nodes(seeded_tenant)
    res = counterfactual_blast(
        graph=seeded_tenant,
        observed_incident_id="inc_inc_hist_01",
        hypothetical_service="currencyservice",
        as_of=None,
    )

    assert res.data["hypothetical_service"] == "currencyservice"
    assert "diff" in res.data
    assert "only_observed" in res.data["diff"]
    assert "only_hypothetical" in res.data["diff"]
    assert "both" in res.data["diff"]
    assert "paths" in res.data
    assert "critical_owners" in res.data
    assert "uncertainty" in res.data
    assert len(res.trace.steps) >= 3

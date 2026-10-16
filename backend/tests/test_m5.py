import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import load_scenario, seed_historical_incidents
from app.hypotheses.generate import generate_candidate_hypotheses
from app.hypotheses.evidence import gather_evidence_for_hypotheses
from app.hypotheses.score import score_hypotheses
from app.hypotheses.sufficiency import check_sufficiency
from app.hypotheses.engine import run_investigation


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant with services, dependencies, and seed historical incidents."""
    tenant_id = "storefront_m5_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def clean_scenario_nodes(graph: TenantGraph) -> None:
    """Clear transient scenario nodes between test runs to ensure isolation."""
    graph.query(
        "MATCH (n) WHERE n:MetricSnapshot OR n:Deployment OR n:ArchitectureChange OR n:Alert OR n:Hypothesis OR n:Evidence OR n:Task "
        "DETACH DELETE n"
    )


def test_candidate_hypothesis_generation(seeded_tenant):
    """Verify candidate hypotheses are derived strictly from graph facts:
    alerting service, upstream dependencies, deployments, architecture changes, and past incidents.
    """
    candidates, trace = generate_candidate_hypotheses(
        graph=seeded_tenant,
        alerting_service="checkoutservice",
        alert_text="checkout authorization failure with high latency",
        as_of=1700005000.0,
        incident_id="inc_test_gen_01",
    )

    assert len(candidates) > 0
    candidate_services = {c["service"] for c in candidates}

    # Alerting service itself must always be included at hop 0
    assert "checkoutservice" in candidate_services
    cs_cand = next(c for c in candidates if c["service"] == "checkoutservice")
    assert cs_cand["hops"] == 0
    assert cs_cand["kind"] == "inferred"
    assert "alerting_service" in cs_cand["candidate_sources"]

    # Upstream dependencies must be present (e.g. paymentservice, emailservice)
    assert "paymentservice" in candidate_services
    ps_cand = next(c for c in candidates if c["service"] == "paymentservice")
    assert ps_cand["hops"] >= 1
    assert "upstream_dependency" in ps_cand["candidate_sources"]

    # Verify Trace object details
    assert trace.steps
    assert any(s.tool == "generate_candidates" for s in trace.steps)


def test_evidence_gathering_support_and_contradiction(seeded_tenant):
    """Verify that both supporting and contradicting evidence items are gathered
    across dependency paths, deployments, metric snapshots, and past incidents.
    """
    clean_scenario_nodes(seeded_tenant)
    # Load scenario with realistic metric snapshots and deployments
    sc_data = load_scenario(graph=seeded_tenant, scenario_id="sc_repeated_01", alert_ts=1700010000.0)
    alert_ts = sc_data["alert"]["ts"]

    candidates, _ = generate_candidate_hypotheses(
        graph=seeded_tenant,
        alerting_service="paymentservice",
        alert_text="paymentservice authorization latency > 2200ms",
        as_of=alert_ts,
        incident_id="inc_test_ev_01",
    )

    evidence_by_hyp, ev_trace = gather_evidence_for_hypotheses(
        graph=seeded_tenant,
        hypotheses=candidates,
        alerting_service="paymentservice",
        alert_text="paymentservice authorization latency > 2200ms",
        as_of=alert_ts,
    )

    # Check evidence structure
    assert len(evidence_by_hyp) == len(candidates)

    found_supporting = False
    found_contradicting = False

    for hyp in candidates:
        ev_group = evidence_by_hyp[hyp["id"]]
        supp = ev_group["supporting"]
        contra = ev_group["contradicting"]

        if supp:
            found_supporting = True
        if contra:
            found_contradicting = True

        for ev in supp + contra:
            assert ev["kind"] in ("observed", "inferred")
            assert ev["polarity"] in ("support", "contradict")
            assert ev["type"] in (
                "dependency_path",
                "recent_deploy",
                "metric",
                "past_incident",
                "architecture_change",
                "decision",
                "doc",
            )
            assert 0.0 <= ev["freshness"] <= 1.0
            assert ev["weight"] > 0

    assert found_supporting, "Evidence engine must gather supporting evidence"
    assert found_contradicting, "Evidence engine must gather authentic contradicting evidence"


def test_scoring_and_ranking(seeded_tenant):
    """Verify ranking mathematics:
    support_total - contra_total, margin calculation, and freshness decay.
    """
    alert_ts = 1700010000.0
    candidates, _ = generate_candidate_hypotheses(
        graph=seeded_tenant,
        alerting_service="paymentservice",
        alert_text="paymentservice authorization latency > 2200ms",
        as_of=alert_ts,
        incident_id="inc_test_score_01",
    )

    evidence_by_hyp, _ = gather_evidence_for_hypotheses(
        graph=seeded_tenant,
        hypotheses=candidates,
        alerting_service="paymentservice",
        alert_text="paymentservice authorization latency > 2200ms",
        as_of=alert_ts,
    )

    scored, score_trace = score_hypotheses(
        hypotheses=candidates,
        evidence_by_hyp=evidence_by_hyp,
        as_of=alert_ts,
    )

    assert len(scored) == len(candidates)

    # Ranked descending by evidence_score
    for i in range(len(scored) - 1):
        assert scored[i]["evidence_score"] >= scored[i + 1]["evidence_score"]

    top = scored[0]
    expected_score = round(top["support_total"] - top["contra_total"], 2)
    assert top["evidence_score"] == expected_score

    if len(scored) >= 2:
        second = scored[1]
        expected_margin = round(top["evidence_score"] - second["evidence_score"], 2)
        assert top["margin"] == expected_margin


def test_sufficiency_check_pass(seeded_tenant):
    """Verify sufficiency check passes when evidence is robust and margin is clear."""
    clean_scenario_nodes(seeded_tenant)
    load_scenario(graph=seeded_tenant, scenario_id="sc_repeated_01", alert_ts=1700010000.0)

    result, trace = run_investigation(
        graph=seeded_tenant,
        alerting_service="paymentservice",
        alert_text="paymentservice authorization latency > 2200ms",
        as_of=1700010000.0,
        incident_id="inc_test_suff_pass",
        persist=True,
    )

    assert result["is_sufficient"] is True
    assert result["status"] == "sufficient"
    assert result["top_hypothesis"] is not None
    assert result["top_hypothesis"]["service"] == "paymentservice"
    assert result["top_hypothesis"]["status"] == "leading"
    assert result["top_hypothesis"]["supporting_count"] >= 2
    assert result["confidence_policy"]["is_calibrated"] is False
    assert result["confidence_policy"]["confidence_percent"] is None  # Gated by M13
    assert result["confidence_policy"]["score_label"] == "evidence score"


def test_sufficiency_check_fail_sparse_data(seeded_tenant):
    """Verify sufficiency check declares 'insufficient_evidence' and produces an evidence_request Task
    when faced with sparse data (e.g. no deployments, zero error rates).
    """
    clean_scenario_nodes(seeded_tenant)
    load_scenario(graph=seeded_tenant, scenario_id="sc_sparse_01", alert_ts=1700020000.0)

    result, trace = run_investigation(
        graph=seeded_tenant,
        alerting_service="frontend",
        alert_text="frontend transient alert: latency jitter without error spike",
        as_of=1700020000.0,
        incident_id="inc_test_sparse_01",
        persist=True,
    )

    assert result["is_sufficient"] is False
    assert result["status"] == "insufficient_evidence"
    assert "insufficient" in result["reason"].lower()

    # Must generate an evidence_request Task
    ev_req = result["evidence_request"]
    assert ev_req is not None
    assert ev_req["kind"] == "evidence_request"
    assert ev_req["status"] == "open"
    assert len(ev_req["required_probes"]) > 0
    assert len(ev_req["competing_services"]) > 0


def test_graph_persistence(seeded_tenant):
    """Verify that Hypothesis and Evidence nodes, and SUPPORTED_BY, CONTRADICTED_BY,
    ABOUT, and HAS_HYPOTHESIS relationships are correctly written to FalkorDB.
    """
    clean_scenario_nodes(seeded_tenant)
    load_scenario(graph=seeded_tenant, scenario_id="sc_variant_01", alert_ts=1700030000.0)

    inc_id = "inc_test_persist_01"
    result, trace = run_investigation(
        graph=seeded_tenant,
        alerting_service="productcatalogservice",
        alert_text="productcatalogservice latency > 3000ms",
        as_of=1700030000.0,
        incident_id=inc_id,
        persist=True,
    )

    # Check Hypothesis nodes in FalkorDB
    hyp_res = seeded_tenant.query(
        "MATCH (i:Incident {id: $inc_id})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:ABOUT]->(s:Service) "
        "RETURN h.id, h.statement, h.evidence_score, h.status, s.name",
        {"inc_id": inc_id},
    )
    assert hyp_res and len(hyp_res.result_set) > 0

    # Check Evidence nodes in FalkorDB
    ev_res = seeded_tenant.query(
        "MATCH (h:Hypothesis {incident_id: $inc_id})-[r:SUPPORTED_BY|CONTRADICTED_BY]->(e:Evidence) "
        "RETURN type(r) AS rel, e.id AS ev_id, e.type AS type, e.kind AS kind, r.weight AS weight",
        {"inc_id": inc_id},
    )
    assert ev_res and len(ev_res.result_set) > 0
    rel_types = {row[0] for row in ev_res.result_set}
    assert "SUPPORTED_BY" in rel_types


def test_api_endpoints(seeded_tenant):
    """Verify FastAPI REST endpoints for M5 investigation and incident inspection."""
    clean_scenario_nodes(seeded_tenant)
    client = TestClient(app)

    # 1. POST /api/hypotheses/investigate
    load_scenario(graph=seeded_tenant, scenario_id="sc_repeated_01", alert_ts=1700040000.0)
    resp = client.post(
        "/api/hypotheses/investigate?tenant=storefront_m5_test",
        json={
            "alerting_service": "paymentservice",
            "alert_text": "paymentservice authorization latency > 2200ms",
            "as_of": 1700040000.0,
            "incident_id": "inc_api_test_01",
            "persist": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "trace" in data
    inv_data = data["data"]
    assert inv_data["incident_id"] == "inc_api_test_01"
    assert inv_data["status"] == "sufficient"
    assert inv_data["top_hypothesis"]["service"] == "paymentservice"

    # 2. GET /api/incidents/{incident_id}/hypotheses
    resp_get = client.get("/api/incidents/inc_api_test_01/hypotheses?tenant=storefront_m5_test")
    assert resp_get.status_code == 200
    get_data = resp_get.json()
    assert get_data["incident_id"] == "inc_api_test_01"
    assert get_data["count"] > 0
    top_hyp = get_data["hypotheses"][0]
    assert len(top_hyp["supporting_evidence"]) > 0

    # 3. POST /api/scenarios/{scenario_id}/investigate
    resp_sc = client.post("/api/scenarios/sc_repeated_01/investigate?tenant=storefront_m5_test")
    assert resp_sc.status_code == 200
    sc_res = resp_sc.json()
    assert sc_res["scenario_id"] == "sc_repeated_01"
    assert sc_res["data"]["status"] == "sufficient"


def test_across_multiple_seeded_scenarios(seeded_tenant):
    """Verify engine runs robustly across different scenario families (repeated, variant, stale_trap, misleading)."""
    test_scenarios = [
        ("sc_repeated_01", "paymentservice", True),
        ("sc_variant_01", "productcatalogservice", True),
        ("sc_stale_trap_01", "cartservice", True),
        ("sc_misleading_01", "frontend", True),
        ("sc_sparse_01", "frontend", False),
    ]

    for sc_id, alert_svc, expected_sufficiency in test_scenarios:
        clean_scenario_nodes(seeded_tenant)
        sc_data = load_scenario(graph=seeded_tenant, scenario_id=sc_id, alert_ts=1700050000.0)
        res, trace = run_investigation(
            graph=seeded_tenant,
            alerting_service=alert_svc,
            alert_text=sc_data["alert"]["text"],
            as_of=sc_data["alert"]["ts"],
            incident_id=f"inc_multi_{sc_id}",
            persist=True,
        )

        assert res["is_sufficient"] == expected_sufficiency
        assert len(res["hypotheses"]) > 0

        # Verify evidence was gathered for hypotheses
        top = res["top_hypothesis"]
        assert top is not None
        assert "evidence_score" in top
        assert "margin" in top
        assert "confidence_basis" in top

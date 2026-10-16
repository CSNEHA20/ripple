import pytest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import load_scenario, seed_historical_incidents
from app.memory.decay import calculate_decay, decay_weight_days
from app.memory.applicability import check_applicability
from app.memory.procedural import (
    compute_laplace_rate,
    record_runbook_outcome,
    rank_runbooks,
)
from app.memory.outcomes import (
    propose_intervention,
    record_observed_outcome,
    get_incident_interventions,
)
from app.memory.semantic import (
    record_observation,
    supersede_observation,
    get_known_facts,
)
from app.memory.episodic import close_incident
from app.memory.recall import recall


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant for M6 memory tests."""
    tenant_id = "storefront_m6_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def clean_scenario_nodes(graph: TenantGraph) -> None:
    """Clear transient scenario and memory nodes between test runs."""
    graph.query(
        "MATCH (n) WHERE n:MetricSnapshot OR n:Deployment OR n:ArchitectureChange "
        "OR n:Alert OR n:Hypothesis OR n:Evidence OR n:Task "
        "DETACH DELETE n"
    )


def test_decay_mathematics():
    """Verify exponential half-life decay function."""
    base_wt = 2.0
    # At age = 0, weight is base_weight
    assert calculate_decay(base_wt, age_seconds=0, half_life_seconds=3600) == 2.0
    # At age = 1 half-life, weight is 50%
    assert calculate_decay(base_wt, age_seconds=3600, half_life_seconds=3600) == 1.0
    # At age = 2 half-lives, weight is 25%
    assert calculate_decay(base_wt, age_seconds=7200, half_life_seconds=3600) == 0.5
    # If half_life is None or 0, no decay
    assert calculate_decay(base_wt, age_seconds=99999, half_life_seconds=None) == 2.0

    # Days decay
    assert decay_weight_days(4.0, age_days=30.0, half_life_days=30.0) == 2.0


def test_procedural_memory_laplace_counters(seeded_tenant):
    """Verify Runbook procedural memory updates ONLY from observed outcomes and recomputes Laplace smoothing."""
    rb_id = "rb_test_proc_01"
    seeded_tenant.query(
        "MERGE (rb:Runbook {id: $id}) SET rb.title = 'Test Rollback', rb.success_count = 0.0, rb.fail_count = 0.0, rb.historical_success_rate = 0.5",
        {"id": rb_id},
    )

    # Initial Laplace: (0 + 1) / (0 + 0 + 2) = 0.5
    assert compute_laplace_rate(0, 0) == 0.5

    # 1. Resolved: +1.0 success
    res1 = record_runbook_outcome(seeded_tenant, rb_id, "resolved")
    assert res1["success_count"] == 1.0
    assert res1["fail_count"] == 0.0
    # (1 + 1) / (1 + 0 + 2) = 2/3 = 0.6667
    assert res1["historical_success_rate"] == 0.6667

    # 2. Failed: +1.0 fail
    res2 = record_runbook_outcome(seeded_tenant, rb_id, "failed")
    assert res2["success_count"] == 1.0
    assert res2["fail_count"] == 1.0
    # (1 + 1) / (1 + 1 + 2) = 2/4 = 0.5
    assert res2["historical_success_rate"] == 0.5

    # 3. Partial: +0.5 success, +0.5 fail
    res3 = record_runbook_outcome(seeded_tenant, rb_id, "partial")
    assert res3["success_count"] == 1.5
    assert res3["fail_count"] == 1.5
    # (1.5 + 1) / (1.5 + 1.5 + 2) = 2.5/5.0 = 0.5
    assert res3["historical_success_rate"] == 0.5


def test_outcome_driven_memory_prediction_error(seeded_tenant):
    """Verify that interventions store predicted_outcome separately from observed outcome,
    record prediction error, and persist failed fixes as first-class memory.
    """
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_outcome_01"
    rb_id = "rb_restart"

    # Propose intervention with predicted outcome 'resolved'
    intv = propose_intervention(
        graph=seeded_tenant,
        incident_id=inc_id,
        runbook_id=rb_id,
        description="Attempt pod restart to clear stuck goroutines",
        predicted_outcome="resolved",
        action_class="reversible",
    )
    assert intv["status"] == "proposed"
    assert intv["predicted_outcome"] == "resolved"

    # Observe that the intervention failed in reality
    out = record_observed_outcome(
        graph=seeded_tenant,
        intervention_id=intv["id"],
        observed="failed",
        metrics_after={"latency_p95_ms": 3200.0, "error_rate": 0.25},
    )

    assert out["observed_outcome"] == "failed"
    assert out["predicted_outcome"] == "resolved"
    assert out["validation_result"] == "rejects"
    assert out["prediction_error"] is True

    # Verify retrieval
    intvs = get_incident_interventions(seeded_tenant, inc_id)
    assert len(intvs) == 1
    stored = intvs[0]
    assert stored["intervention_id"] == intv["id"]
    assert stored["status"] == "executed"
    assert stored["observed_outcome"] == "failed"
    assert stored["validation_result"] == "rejects"
    assert stored["prediction_error"] is True


def test_semantic_memory_supersedes(seeded_tenant):
    """Verify that when new evidence contradicts an old fact, a new Observation is created,
    the SUPERSEDES edge is established, and the old fact is marked inactive (never deleted).
    """
    svc = "cartservice"

    # 1. Record original observation
    obs1 = record_observation(
        graph=seeded_tenant,
        service=svc,
        text="cartservice uses local in-memory redis container",
        kind="observed",
        confidence_basis="2026-Q1 architecture manifest",
        weight=1.0,
    )
    assert obs1["active"] is True

    # Verify active facts
    facts1 = get_known_facts(seeded_tenant, service=svc)
    assert any(f["id"] == obs1["id"] for f in facts1)

    # 2. Supersede with updated architecture fact
    sup_res = supersede_observation(
        graph=seeded_tenant,
        old_observation_id=obs1["id"],
        service=svc,
        new_text="cartservice migrated to distributed clustered Redis on Spanner",
        kind="observed",
        confidence_basis="PR #42 architecture overhaul",
        weight=1.0,
    )
    new_obs = sup_res["new_observation"]

    # Verify in FalkorDB: old is inactive, new is active, SUPERSEDES relationship exists
    check_cypher = """
    MATCH (n:Observation {id: $new_id})-[r:SUPERSEDES]->(o:Observation {id: $old_id})
    RETURN n.active AS new_active, o.active AS old_active, type(r) AS rel
    """
    res = seeded_tenant.query(check_cypher, {"new_id": new_obs["id"], "old_id": obs1["id"]})
    assert res and len(res.result_set) == 1
    new_act, old_act, rel = res.result_set[0]
    assert new_act is True
    assert old_act is False
    assert rel == "SUPERSEDES"

    # Verify get_known_facts only surfaces the active superseded fact
    facts2 = get_known_facts(seeded_tenant, service=svc)
    fact_ids = {f["id"] for f in facts2}
    assert new_obs["id"] in fact_ids
    assert obs1["id"] not in fact_ids, "Inactive superseded observation must not be returned in active facts"


def test_applicability_check_blocks_stale_fix(seeded_tenant):
    """The killer moment of Ripple's outcome memory:
    Verify that an ArchitectureChange closing an assumed dependency edge causes check_applicability
    to declare the runbook NOT APPLICABLE, providing a clear 'Why not recommended' diagnostic card.
    """
    clean_scenario_nodes(seeded_tenant)

    # Load stale_fix trap scenario where an ArchitectureChange closed cartservice->redis-cart
    load_scenario(graph=seeded_tenant, scenario_id="sc_stale_trap_01", alert_ts=1700010000.0)

    # rb_db_reconnect assumes cartservice->redis-cart
    result, trace = check_applicability(
        graph=seeded_tenant,
        runbook_id="rb_db_reconnect",
        as_of=1700010000.0,
    )

    assert result["applicable"] is False
    assert len(result["broken_assumptions"]) > 0

    broken = result["broken_assumptions"][0]
    assert broken["edge"] == "cartservice->redis-cart"
    assert "ac_" in broken["closed_by_change_id"]

    why = result["why_not_recommended"]
    assert why is not None
    assert why["broken_edge"] == "cartservice->redis-cart"
    assert why["architecture_change_id"] == broken["closed_by_change_id"]
    assert "closed" in result["reason"].lower() or "removed" in result["reason"].lower()


def test_closing_incident_updates_recall_and_rejects_failed_fix(seeded_tenant):
    """Verify that closing incident #1 updates recall() for subsequent incident #2,
    surfacing the verified root cause and rejecting failed fixes.
    """
    clean_scenario_nodes(seeded_tenant)

    inc1_id = "inc_test_mem_flow_01"
    alert_txt = "cartservice Redis connection pool exhausted - 500 internal errors"

    # 1. Form winning hypothesis & test interventions on Incident 1
    hyp_id = f"hyp_{inc1_id}_cartservice"
    seeded_tenant.query(
        "MERGE (h:Hypothesis {id: $id}) "
        "SET h.statement = 'Connection pool leak in cartservice', h.service = 'cartservice', h.kind = 'inferred', h.status = 'open'",
        {"id": hyp_id},
    )

    # Intervention 1: rb_restart (failed)
    intv_fail = propose_intervention(
        graph=seeded_tenant,
        incident_id=inc1_id,
        runbook_id="rb_restart",
        description="Restart cartservice",
        hypothesis_id=hyp_id,
    )
    record_observed_outcome(seeded_tenant, intv_fail["id"], "failed")

    # Intervention 2: rb_db_reconnect (resolved)
    intv_ok = propose_intervention(
        graph=seeded_tenant,
        incident_id=inc1_id,
        runbook_id="rb_db_reconnect",
        description="Flush and reconnect pool",
        hypothesis_id=hyp_id,
    )
    record_observed_outcome(seeded_tenant, intv_ok["id"], "resolved")

    # Close incident 1
    close_res = close_incident(
        graph=seeded_tenant,
        incident_id=inc1_id,
        winning_hypothesis_id=hyp_id,
        steps_taken=["triaged alert", "attempted restart (failed)", "applied reconnect (resolved)"],
        handled_by="alice",
        signature_text=alert_txt,
    )
    assert close_res["status"] == "closed"

    # 2. Query recall() for Incident 2 with identical alert text
    rec_data, rec_trace = recall(
        graph=seeded_tenant,
        alert_text=alert_txt,
        services=["cartservice"],
    )

    # Incident 1 must be recalled as similar
    sim_ids = [m["incident_id"] for m in rec_data["similar_incidents"]]
    assert inc1_id in sim_ids

    # The failed fix (rb_restart) must be surfaced as rejected
    rej_rbs = {r["runbook_id"]: r for r in rec_data["rejected_runbooks"]}
    assert "rb_restart" in rej_rbs
    assert "failed" in rej_rbs["rb_restart"]["rejection_reason"].lower()


def test_concurrency_and_idempotent_writes(seeded_tenant):
    """Verify that multiple concurrent memory writes (observations and runbook outcomes)
    are strictly idempotent and do not corrupt counters or generate duplicate nodes.
    """
    svc = "checkoutservice"

    def write_fact(idx: int):
        t_graph = TenantGraph("storefront_m6_test")
        return record_observation(
            graph=t_graph,
            service=svc,
            text="Checkout uses client-side load balancing with retry backoff",
            observation_id=f"obs_concurrent_{idx % 3}",
            kind="observed",
        )

    # Run 12 concurrent writes with 3 colliding observation IDs
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(write_fact, range(12)))

    assert len(results) == 12

    # Query FalkorDB to verify deduplication
    res = seeded_tenant.query(
        "MATCH (obs:Observation) WHERE obs.id STARTS WITH 'obs_concurrent_' RETURN count(obs)"
    )
    count = int(res.result_set[0][0])
    assert count <= 3, f"Expected at most 3 distinct observation nodes due to MERGE idempotency, got {count}"


def test_api_endpoints_m6(seeded_tenant):
    """Verify FastAPI REST routes for the M6 Memory Layer."""
    client = TestClient(app)

    # 1. POST /api/memory/observations
    obs_resp = client.post(
        "/api/memory/observations?tenant=storefront_m6_test",
        json={
            "service": "emailservice",
            "text": "Email service sends asynchronously via worker threads",
            "kind": "observed",
            "confidence_basis": "architecture doc v1",
            "weight": 1.5,
        },
    )
    assert obs_resp.status_code == 200
    obs_data = obs_resp.json()
    obs_id = obs_data["id"]

    # 2. GET /api/memory/facts
    facts_resp = client.get("/api/memory/facts?tenant=storefront_m6_test&service=emailservice")
    assert facts_resp.status_code == 200
    facts_data = facts_resp.json()
    assert facts_data["count"] > 0

    # 3. POST /api/memory/observations/{obs_id}/supersede
    sup_resp = client.post(
        f"/api/memory/observations/{obs_id}/supersede?tenant=storefront_m6_test",
        json={
            "service": "emailservice",
            "new_text": "Email service updated to use Kafka consumer pipeline",
            "kind": "observed",
            "confidence_basis": "PR #88 migration",
        },
    )
    assert sup_resp.status_code == 200

    # 4. POST /api/memory/interventions & outcome
    intv_resp = client.post(
        "/api/memory/interventions?tenant=storefront_m6_test",
        json={
            "incident_id": "inc_api_m6_01",
            "runbook_id": "rb_rollback",
            "description": "Rollback bad release",
            "predicted_outcome": "resolved",
            "action_class": "needs_approval",
        },
    )
    assert intv_resp.status_code == 200
    intv_id = intv_resp.json()["id"]

    out_resp = client.post(
        f"/api/memory/interventions/{intv_id}/outcome?tenant=storefront_m6_test",
        json={
            "observed": "resolved",
            "metrics_after": {"latency_p95_ms": 45.0, "error_rate": 0.0},
        },
    )
    assert out_resp.status_code == 200
    assert out_resp.json()["validation_result"] == "validates"

    # 5. GET /api/memory/incidents/{incident_id}/interventions
    intvs_list_resp = client.get("/api/memory/incidents/inc_api_m6_01/interventions?tenant=storefront_m6_test")
    assert intvs_list_resp.status_code == 200
    assert intvs_list_resp.json()["count"] == 1

    # 6. GET /api/memory/applicability/{runbook_id}
    app_resp = client.get("/api/memory/applicability/rb_rollback?tenant=storefront_m6_test")
    assert app_resp.status_code == 200
    assert "data" in app_resp.json()
    assert app_resp.json()["data"]["runbook_id"] == "rb_rollback"

    # 7. POST /api/memory/recall
    rec_resp = client.post(
        "/api/memory/recall?tenant=storefront_m6_test",
        json={
            "alert_text": "paymentservice authorization latency > 2200ms",
            "services": ["paymentservice"],
        },
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()["data"]
    assert "similar_incidents" in rec_data
    assert "rejected_runbooks" in rec_data
    assert "known_facts" in rec_data

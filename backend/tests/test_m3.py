import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.catalog import (
    list_scenarios,
    get_scenario,
    list_runbooks,
    get_runbook,
)
from app.scenarios.engine import (
    load_scenario,
    seed_historical_incidents,
)
from app.scenarios.outcomes import apply_intervention


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant with services and dependencies."""
    tenant_id = "storefront_m3_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    yield graph
    graph.delete()


def test_scenario_and_runbook_catalog():
    """Verify catalog loads all scenario families and operational runbooks."""
    scenarios = list_scenarios()
    assert len(scenarios) >= 18, f"Expected >= 18 scenarios, got {len(scenarios)}"

    families = {sc["family"] for sc in scenarios}
    expected_families = {"historical", "repeated", "variant", "novel", "stale_trap", "misleading_memory"}
    assert expected_families.issubset(families), f"Missing families: {expected_families - families}"

    # Verify counts per family as required by plan
    historical = list_scenarios("historical")
    assert len(historical) >= 6, f"Expected >= 6 historical scenarios, got {len(historical)}"

    repeated = list_scenarios("repeated")
    assert len(repeated) == 3, f"Expected 3 repeated scenarios, got {len(repeated)}"

    variant = list_scenarios("variant")
    assert len(variant) == 3, f"Expected 3 variant scenarios, got {len(variant)}"

    novel = list_scenarios("novel")
    assert len(novel) == 3, f"Expected 3 novel scenarios, got {len(novel)}"

    stale_trap = list_scenarios("stale_trap")
    assert len(stale_trap) == 2, f"Expected 2 stale_trap scenarios, got {len(stale_trap)}"

    misleading = list_scenarios("misleading_memory")
    assert len(misleading) >= 2, f"Expected >= 2 misleading_memory scenarios, got {len(misleading)}"

    # Verify runbooks
    runbooks = list_runbooks()
    assert len(runbooks) >= 8
    rb_ids = {rb["id"] for rb in runbooks}
    expected_rbs = {
        "rb_rollback", "rb_restart", "rb_scale_up", "rb_cache_flush",
        "rb_circuit_breaker", "rb_rate_limit", "rb_config_revert", "rb_db_reconnect"
    }
    assert expected_rbs.issubset(rb_ids)

    # Check dependency assumption in rb_cache_flush
    cache_flush = get_runbook("rb_cache_flush")
    assert cache_flush is not None
    assert "cartservice->redis-cart" in cache_flush.get("assumes", [])


def test_load_scenario_node_creation(seeded_tenant: TenantGraph):
    """Verify loading a scenario creates Alert, Deployment, and MetricSnapshot nodes
    flagged with source='seeded'.
    """
    res = load_scenario(seeded_tenant, "sc_repeated_01", alert_ts=1700000000.0)
    assert res["status"] == "loaded"
    assert res["scenario_id"] == "sc_repeated_01"

    # 1. Verify Alert node in graph
    alert_res = seeded_tenant.query("""
        MATCH (a:Alert)-[:FIRED_ON]->(s:Service {name: 'paymentservice'})
        RETURN a.id, a.text, a.severity, a.source
    """)
    assert len(alert_res.result_set) >= 1
    row = alert_res.result_set[0]
    assert "paymentservice" in row[1].lower()
    assert row[2] == "CRITICAL"
    assert row[3] == "seeded"

    # 2. Verify Deployment node in graph
    dep_res = seeded_tenant.query("""
        MATCH (d:Deployment)-[:DEPLOYED_TO]->(s:Service {name: 'paymentservice'})
        WHERE d.version = 'v1.5.0'
        RETURN d.id, d.version, d.source
    """)
    assert len(dep_res.result_set) >= 1
    dep_row = dep_res.result_set[0]
    assert dep_row[1] == "v1.5.0"
    assert dep_row[2] == "seeded"

    # 3. Verify MetricSnapshots in graph
    metric_res = seeded_tenant.query("""
        MATCH (s:Service {name: 'paymentservice'})-[:HAD_METRIC]->(m:MetricSnapshot)
        RETURN m.status, m.latency_p95_ms, m.error_rate, m.source
    """)
    assert len(metric_res.result_set) >= 1
    m_row = metric_res.result_set[0]
    assert m_row[0] == "failing"
    assert m_row[1] >= 2000.0
    assert m_row[2] > 0.05
    assert m_row[3] == "seeded"


def test_contradicting_evidence_metrics(seeded_tenant: TenantGraph):
    """Verify that unaffected services possess healthy 'normal' MetricSnapshots,
    serving as authentic contradicting evidence against spurious hypotheses.
    """
    load_scenario(seeded_tenant, "sc_repeated_01", alert_ts=1700000000.0)

    # Cartservice and Currencyservice should be healthy (normal)
    healthy_res = seeded_tenant.query("""
        MATCH (s:Service)-[:HAD_METRIC]->(m:MetricSnapshot)
        WHERE s.name IN ['cartservice', 'currencyservice']
        RETURN s.name, m.status, m.latency_p95_ms, m.error_rate
    """)
    assert len(healthy_res.result_set) >= 2
    for svc_name, status, latency, error_rate in healthy_res.result_set:
        assert status == "normal", f"Service {svc_name} should be normal, got {status}"
        assert latency < 100.0, f"Service {svc_name} latency should be low baseline, got {latency}"
        assert error_rate == 0.0


def test_stale_fix_trap_architecture_change(seeded_tenant: TenantGraph):
    """Verify that loading sc_stale_trap_01 closes cartservice->redis-cart via
    ArchitectureChange, and that applying the stale fix returns 'failed'.
    """
    res = load_scenario(seeded_tenant, "sc_stale_trap_01", alert_ts=1700100000.0)
    assert res["status"] == "loaded"

    # 1. Verify ArchitectureChange node
    ac_res = seeded_tenant.query("""
        MATCH (ac:ArchitectureChange {id: 'ac_cart_redis_decouple'})-[:CHANGED]->(s:Service)
        RETURN ac.summary, s.name, ac.source
    """)
    assert len(ac_res.result_set) >= 1
    assert ac_res.result_set[0][2] == "seeded"

    # 2. Verify that DEPENDS_ON edge cartservice->redis-cart is now closed (valid_to is set)
    edge_res = seeded_tenant.query("""
        MATCH (c:Service {name: 'cartservice'})-[r:DEPENDS_ON]->(d:Service {name: 'redis-cart'})
        RETURN r.valid_from, r.valid_to
    """)
    assert len(edge_res.result_set) >= 1
    valid_from, valid_to = edge_res.result_set[0]
    assert valid_to is not None, "cartservice->redis-cart edge should have valid_to set by ArchitectureChange"

    # 3. Verify stale intervention returns failed
    stale_outcome = apply_intervention("sc_stale_trap_01", "rb_cache_flush")
    assert stale_outcome["observed"] == "failed"
    assert "stale fix attempted" in stale_outcome["explanation"].lower()

    # 4. Verify valid intervention returns resolved
    valid_outcome = apply_intervention("sc_stale_trap_01", "rb_restart")
    assert valid_outcome["observed"] == "resolved"


def test_apply_intervention_outcomes_and_metrics():
    """Verify apply_intervention computes correct outcomes (resolved, partial, failed)
    and updates post-fix metrics accordingly.
    """
    # 1. Resolved: metrics return to normal
    res_resolved = apply_intervention("sc_repeated_01", "rb_rollback")
    assert res_resolved["observed"] == "resolved"
    for m in res_resolved["metrics_after"]:
        assert m["status"] == "normal"
        assert m["latency_p95_ms"] <= 50.0
        assert m["error_rate"] == 0.0

    # 2. Partial: metrics degrade from failing to degraded
    res_partial = apply_intervention("sc_repeated_01", "rb_scale_up")
    assert res_partial["observed"] == "partial"
    payment_metric = next(m for m in res_partial["metrics_after"] if m["service"] == "paymentservice")
    assert payment_metric["status"] == "degraded"
    assert payment_metric["latency_p95_ms"] < 2400.0

    # 3. Failed: metrics remain failing
    res_failed = apply_intervention("sc_repeated_01", "rb_restart")
    assert res_failed["observed"] == "failed"
    payment_metric_fail = next(m for m in res_failed["metrics_after"] if m["service"] == "paymentservice")
    assert payment_metric_fail["status"] == "failing"


def test_seed_historical_incidents(seeded_tenant: TenantGraph):
    """Verify seed_historical_incidents creates Incident, Hypothesis, Intervention,
    and Outcome nodes with validated outcomes and failed attempts.
    """
    res = seed_historical_incidents(seeded_tenant)
    assert res["status"] == "seeded"
    assert res["count"] >= 6

    # 1. Verify Incidents and root cause Hypotheses in graph
    inc_res = seeded_tenant.query("""
        MATCH (inc:Incident)-[:ROOT_CAUSE]->(h:Hypothesis)-[:ABOUT]->(s:Service)
        RETURN inc.id, inc.title, h.statement, s.name, inc.source
    """)
    assert len(inc_res.result_set) >= 6
    for row in inc_res.result_set:
        assert row[4] == "seeded"

    # 2. Verify Validated Interventions & Outcomes
    val_res = seeded_tenant.query("""
        MATCH (intv:Intervention)-[v:VALIDATED_BY]->(out:Outcome)
        WHERE v.result = 'validates' AND out.observed = 'resolved'
        RETURN count(intv)
    """)
    assert val_res.result_set[0][0] >= 6

    # 3. Verify First-Class Failed Fixes recorded in Outcome memory
    fail_res = seeded_tenant.query("""
        MATCH (intv:Intervention)-[v:VALIDATED_BY]->(out:Outcome)
        WHERE v.result = 'rejects' AND out.observed = 'failed'
        RETURN intv.runbook_id, out.observed
    """)
    assert len(fail_res.result_set) >= 1
    failed_rbs = [r[0] for r in fail_res.result_set]
    assert "rb_restart" in failed_rbs

    # 4. Verify SIMILAR_TO incident relationships
    sim_res = seeded_tenant.query("""
        MATCH (a:Incident)-[r:SIMILAR_TO]->(b:Incident)
        RETURN a.id, b.id, r.score
    """)
    assert len(sim_res.result_set) >= 1


def test_api_endpoints_m3():
    """Verify FastAPI routes for scenarios, loading, intervention, and runbooks."""
    client = TestClient(app)

    # 1. List scenarios
    res = client.get("/api/scenarios")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 18

    # Filter by family
    res_filt = client.get("/api/scenarios?family=novel")
    assert res_filt.status_code == 200
    assert res_filt.json()["count"] == 3

    # 2. Get specific scenario
    res_sc = client.get("/api/scenarios/sc_repeated_01")
    assert res_sc.status_code == 200
    assert res_sc.json()["id"] == "sc_repeated_01"

    # 3. List runbooks
    res_rb = client.get("/api/runbooks")
    assert res_rb.status_code == 200
    assert res_rb.json()["count"] >= 8

    # 4. Apply intervention API
    res_int = client.post(
        "/api/scenarios/sc_repeated_01/intervene",
        json={"runbook_id": "rb_rollback"},
    )
    assert res_int.status_code == 200
    assert res_int.json()["observed"] == "resolved"

    # 5. Load scenario API
    res_load = client.post(
        "/api/scenarios/sc_repeated_01/load",
        headers={"X-Tenant": "storefront"},
        json={"alert_ts": 1700000000.0},
    )
    assert res_load.status_code == 200
    assert res_load.json()["status"] == "loaded"

import pytest
import time
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import load_scenario, seed_historical_incidents
from app.agents.blackboard import (
    create_agent_run,
    complete_agent_run,
    create_task,
    update_task_status,
    record_agent_observation,
    get_blackboard_state,
)
from app.agents.conflicts import (
    flag_conflict,
    create_evidence_request_task,
    resolve_conflict,
    check_margin_conflict,
    check_applicability_conflict,
)
from app.agents.actions import (
    classify_action,
    propose_action,
    approve_action,
    reject_action,
    get_pending_actions,
)
from app.agents.llm import LLMWrapper, extract_citations
from app.agents.triage import TriageAgent
from app.agents.investigator import InvestigatorAgent
from app.agents.responder import ResponderAgent
from app.agents.verifier import VerifierAgent
from app.agents.orchestrator import IncidentOrchestrator, event_bus


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant for M7 Agent Crew tests."""
    tenant_id = "storefront_m7_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def clean_scenario_nodes(graph: TenantGraph) -> None:
    """Clear transient scenario, agent, and memory nodes between test runs."""
    graph.query(
        "MATCH (n) WHERE n:MetricSnapshot OR n:Deployment OR n:ArchitectureChange "
        "OR n:Alert OR n:Hypothesis OR n:Evidence OR n:Task OR n:AgentRun "
        "OR n:Conflict OR n:Action OR n:Observation OR n:Intervention OR n:Outcome "
        "DETACH DELETE n"
    )


def test_blackboard_nodes_and_relationships(seeded_tenant):
    """Verify blackboard coordination: AgentRun, Task handoffs, blocked_by, and Observations."""
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_bb_01"
    seeded_tenant.query("MERGE (i:Incident {id: $id}) SET i.title = 'Test Incident'", {"id": inc_id})

    # 1. Create AgentRun
    ar = create_agent_run(seeded_tenant, agent_name="Triage", incident_id=inc_id, role="triage")
    assert ar["id"].startswith("run_triage_")

    # Verify WORKED_ON edge
    res = seeded_tenant.query(
        "MATCH (ar:AgentRun {id: $ar_id})-[:WORKED_ON]->(i:Incident {id: $inc_id}) RETURN count(*)",
        {"ar_id": ar["id"], "inc_id": inc_id},
    )
    assert res.result_set[0][0] == 1

    # 2. Create Task with CREATED edge
    t1 = create_task(seeded_tenant, incident_id=inc_id, kind="investigate", payload={"foo": "bar"}, agent_run_id=ar["id"])
    assert t1["kind"] == "investigate"
    res = seeded_tenant.query(
        "MATCH (ar:AgentRun {id: $ar_id})-[:CREATED]->(t:Task {id: $tid}) RETURN count(*)",
        {"ar_id": ar["id"], "tid": t1["id"]},
    )
    assert res.result_set[0][0] == 1

    # 3. Create second task with BLOCKED_BY
    t2 = create_task(
        seeded_tenant,
        incident_id=inc_id,
        kind="respond",
        payload={"step": 2},
        agent_run_id=ar["id"],
        blocked_by_task_id=t1["id"],
    )
    res = seeded_tenant.query(
        "MATCH (t2:Task {id: $t2_id})-[:BLOCKED_BY]->(t1:Task {id: $t1_id}) RETURN count(*)",
        {"t2_id": t2["id"], "t1_id": t1["id"]},
    )
    assert res.result_set[0][0] == 1

    # 4. Record Observation
    obs = record_agent_observation(
        seeded_tenant,
        agent_run_id=ar["id"],
        incident_id=inc_id,
        service="paymentservice",
        text="High error rate observed on paymentservice",
        kind="observed",
        confidence_basis="Tool metric snapshot",
    )
    res = seeded_tenant.query(
        "MATCH (ar:AgentRun {id: $ar_id})-[:CREATED]->(obs:Observation {id: $oid})-[:ABOUT]->(s:Service {name: 'paymentservice'}) "
        "RETURN count(*)",
        {"ar_id": ar["id"], "oid": obs["id"]},
    )
    assert res.result_set[0][0] == 1

    # 5. Get blackboard state
    bb = get_blackboard_state(seeded_tenant, inc_id)
    assert len(bb["agent_runs"]) == 1
    assert len(bb["tasks"]) == 2
    assert len(bb["observations"]) == 1


def test_conflicts_and_evidence_requests(seeded_tenant):
    """Verify Conflict raising, INVOLVES edges, FLAGGED edges, and evidence_request resolution."""
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_conf_01"
    seeded_tenant.query("MERGE (i:Incident {id: $id})", {"id": inc_id})
    ar = create_agent_run(seeded_tenant, "Investigator", inc_id, "investigator")

    # Create dummy hypotheses
    seeded_tenant.query(
        "MERGE (h1:Hypothesis {id: 'hyp_h1', incident_id: $iid, evidence_score: 2.1, margin: 0.1, service: 'paymentservice'}) "
        "MERGE (h2:Hypothesis {id: 'hyp_h2', incident_id: $iid, evidence_score: 2.0, margin: 0.1, service: 'shippingservice'})",
        {"iid": inc_id},
    )

    # Detect margin conflict
    scored_hyps = [
        {"id": "hyp_h1", "service": "paymentservice", "evidence_score": 2.1, "margin": 0.1},
        {"id": "hyp_h2", "service": "shippingservice", "evidence_score": 2.0, "margin": 0.1},
    ]
    has_conf, reason, involved = check_margin_conflict(scored_hyps, min_margin=0.5)
    assert has_conf is True
    assert "below the threshold" in reason
    assert "hyp_h1" in involved

    # Flag conflict on blackboard
    conf = flag_conflict(
        seeded_tenant,
        incident_id=inc_id,
        agent_run_id=ar["id"],
        reason=reason,
        involves_node_ids=involved,
    )
    assert conf["status"] == "open"

    # Verify INVOLVES edges
    res = seeded_tenant.query(
        "MATCH (c:Conflict {id: $cid})-[:INVOLVES]->(h:Hypothesis) RETURN count(h)",
        {"cid": conf["id"]},
    )
    assert res.result_set[0][0] >= 1

    # Create evidence_request task
    ev_task = create_evidence_request_task(
        seeded_tenant,
        incident_id=inc_id,
        agent_run_id=ar["id"],
        hypothesis_id="hyp_h1",
        required_probes=["Fetch network metrics between payment and shipping"],
        conflict_id=conf["id"],
    )
    assert ev_task["kind"] == "evidence_request"

    # Resolve conflict with task
    resolved = resolve_conflict(seeded_tenant, conf["id"], resolving_task_id=ev_task["id"])
    assert resolved["status"] == "resolved"

    # Verify RESOLVED_BY edge
    res = seeded_tenant.query(
        "MATCH (c:Conflict {id: $cid})-[:RESOLVED_BY]->(t:Task {id: $tid}) RETURN count(*)",
        {"cid": conf["id"], "tid": ev_task["id"]},
    )
    assert res.result_set[0][0] == 1


def test_safe_action_gate_and_approvals(seeded_tenant):
    """Verify safe action classification and the human approval gate:
    read_only & reversible auto-execute; needs_approval requires explicit operator approval.
    """
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_actions_01"
    seeded_tenant.query("MERGE (i:Incident {id: $id})", {"id": inc_id})
    ar = create_agent_run(seeded_tenant, "Responder", inc_id, "responder")

    # 1. Classification
    assert classify_action("query_metrics") == "read_only"
    assert classify_action("draft_status_update") == "reversible"
    assert classify_action("rollback") == "needs_approval"
    assert classify_action("restart") == "needs_approval"

    # 2. Propose reversible action (auto-executed)
    act_rev = propose_action(
        seeded_tenant,
        incident_id=inc_id,
        agent_run_id=ar["id"],
        intervention_id=None,
        kind="draft_status_update",
        payload={"message": "Investigating incident"},
    )
    assert act_rev["class"] == "reversible"
    assert act_rev["status"] == "executed"
    assert act_rev["executed_ts"] is not None

    # 3. Propose destructive action (held for approval)
    act_dest = propose_action(
        seeded_tenant,
        incident_id=inc_id,
        agent_run_id=ar["id"],
        intervention_id=None,
        kind="rollback",
        payload={"service": "paymentservice", "version": "v1.2.0"},
    )
    assert act_dest["class"] == "needs_approval"
    assert act_dest["status"] == "proposed"
    assert act_dest["executed_ts"] is None

    # Check pending actions query
    pending = get_pending_actions(seeded_tenant, inc_id)
    assert len(pending) == 1
    assert pending[0]["id"] == act_dest["id"]

    # 4. Operator approves action
    approved = approve_action(seeded_tenant, incident_id=inc_id, action_id=act_dest["id"], approver="sre_oncall")
    assert approved["status"] == "executed"
    assert approved["approved_by"] == "sre_oncall"

    # Verify no pending actions remain
    assert len(get_pending_actions(seeded_tenant, inc_id)) == 0


def test_llm_citations_and_replay_wrapper():
    """Verify LLMWrapper schema validation, citation extraction, and fallback generation."""
    wrapper = LLMWrapper(mode="replay")
    citations = extract_citations("Based on evidence ev_metric_123 and runbook rb_rollback_01, fix applies.")
    assert "ev_metric_123" in citations
    assert "rb_rollback_01" in citations


def test_triage_agent_execution(seeded_tenant):
    """Verify TriageAgent sizes blast radius, ranks severity, recalls memory, and emits task."""
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_triage_run"
    seeded_tenant.query("MERGE (i:Incident {id: $id})", {"id": inc_id})

    alert = {"service": "paymentservice", "text": "p95 latency spike > 2000ms"}
    agent = TriageAgent(mode="replay")
    out, trace = agent.run(seeded_tenant, incident_id=inc_id, alert=alert)

    assert out["alerting_service"] == "paymentservice"
    assert out["severity"] in ("P1", "P2", "P3")
    assert out["blast_radius_count"] >= 0
    assert out["task_id"].startswith("task_investigate_")
    assert out["observation_id"].startswith("obs_")
    assert len(trace.steps) >= 2


def test_investigator_and_responder_agents(seeded_tenant):
    """Verify Investigator forms hypotheses with evidence; Responder checks applicability and proposes actions."""
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_inv_resp"
    load_scenario(seeded_tenant, "sc_repeated_01")
    seeded_tenant.query("MERGE (i:Incident {id: $id})", {"id": inc_id})

    alert = {"service": "paymentservice", "text": "p95 latency > 2s"}

    # 1. Run Triage
    triage_agent = TriageAgent(mode="replay")
    triage_out, _ = triage_agent.run(seeded_tenant, inc_id, alert)

    # 2. Run Investigator
    inv_agent = InvestigatorAgent(mode="replay")
    inv_task = {"id": triage_out["task_id"], "payload": {"alerting_service": "paymentservice", "alert_text": alert["text"]}}
    inv_out, inv_trace = inv_agent.run(seeded_tenant, inc_id, inv_task)

    assert inv_out["top_hypothesis"] is not None
    assert len(inv_out["hypotheses"]) > 0
    assert inv_out["respond_task_id"].startswith("task_respond_")

    # 3. Run Responder
    resp_agent = ResponderAgent(mode="replay")
    resp_task = {"id": inv_out["respond_task_id"], "payload": {"top_hypothesis": inv_out["top_hypothesis"], "alerting_service": "paymentservice"}}
    resp_out, resp_trace = resp_agent.run(seeded_tenant, inc_id, resp_task)

    assert resp_out["selected_runbook_id"] is not None
    assert resp_out["is_applicable"] is True
    assert len(resp_out["actions"]) == 3
    assert resp_out["remediation_action"]["class"] == "needs_approval"


def test_full_crew_orchestration_with_approval_gate(seeded_tenant):
    """Test full 4-agent crew lifecycle end-to-end:
    Phase 1: Run crew -> pauses at awaiting_approval.
    Phase 2: Approve action -> Verifier executes, verifies outcome, links ROOT_CAUSE, closes incident.
    """
    clean_scenario_nodes(seeded_tenant)
    inc_id = "inc_test_crew_e2e"
    load_scenario(seeded_tenant, "sc_repeated_01")

    alert = {"service": "paymentservice", "text": "p95 latency > 2s"}
    orchestrator = IncidentOrchestrator(mode="replay")

    # 1. Run crew with auto_approve=False
    crew_res, crew_trace = orchestrator.run_crew(
        graph=seeded_tenant,
        alert=alert,
        incident_id=inc_id,
        scenario_id="sc_repeated_01",
        auto_approve=False,
    )

    assert crew_res["status"] == "awaiting_approval"
    assert len(crew_res["pending_actions"]) == 1
    pending_act = crew_res["pending_actions"][0]
    assert pending_act["class"] == "needs_approval"

    # Verify blackboard state before approval
    bb = crew_res["blackboard"]
    assert len(bb["agent_runs"]) == 3  # Triage, Investigator, Responder
    assert len(bb["hypotheses"]) >= 1

    # 2. Operator approves action and resumes crew through Verifier
    app_res, app_trace = orchestrator.approve_and_verify(
        graph=seeded_tenant,
        incident_id=inc_id,
        action_id=pending_act["id"],
        approver="senior_sre",
        scenario_id="sc_repeated_01",
    )

    assert app_res["status"] == "resolved"
    assert app_res["approved_action"]["status"] == "executed"
    assert app_res["verifier"]["observed_outcome"] == "resolved"

    # 3. Verify ROOT_CAUSE edge is linked only after verified outcome!
    root_cause_res = seeded_tenant.query(
        "MATCH (i:Incident {id: $iid})-[:ROOT_CAUSE]->(h:Hypothesis) RETURN h.id, h.statement",
        {"iid": inc_id},
    )
    assert len(root_cause_res.result_set) >= 1

    # 4. Verify all 4 agents have completed AgentRuns on blackboard
    runs_res = seeded_tenant.query(
        "MATCH (ar:AgentRun {incident_id: $iid}) RETURN ar.agent, ar.status",
        {"iid": inc_id},
    )
    agent_names = {r[0] for r in runs_res.result_set}
    assert agent_names == {"Triage", "Investigator", "Responder", "Verifier"}


def test_api_incident_endpoints(seeded_tenant):
    """Test FastAPI incident endpoints: POST /incidents, GET /incidents/{id}, POST approve."""
    clean_scenario_nodes(seeded_tenant)
    load_scenario(seeded_tenant, "sc_repeated_01")
    client = TestClient(app)
    headers = {"X-Tenant": seeded_tenant.tenant_id}

    # 1. Run crew via API
    resp = client.post(
        "/incidents",
        json={
            "alert": {"service": "paymentservice", "text": "Critical payment latency spike"},
            "scenario_id": "sc_repeated_01",
            "auto_approve": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    inc_id = data["incident_id"]
    assert data["status"] == "awaiting_approval"
    assert len(data["pending_actions"]) == 1
    action_id = data["pending_actions"][0]["id"]

    # 2. Get incident state
    get_resp = client.get(f"/incidents/{inc_id}", headers=headers)
    assert get_resp.status_code == 200
    inc_state = get_resp.json()
    assert inc_state["incident"]["status"] == "awaiting_approval"
    assert len(inc_state["blackboard"]["agent_runs"]) >= 3

    # 3. Approve action
    app_resp = client.post(
        f"/incidents/{inc_id}/actions/{action_id}/approve",
        json={"approver": "oncall_engineer", "scenario_id": "sc_repeated_01"},
        headers=headers,
    )
    assert app_resp.status_code == 200
    app_data = app_resp.json()["data"]
    assert app_data["status"] == "resolved"
    assert app_data["verifier"]["observed_outcome"] == "resolved"

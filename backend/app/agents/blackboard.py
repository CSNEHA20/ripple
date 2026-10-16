import json
import logging
import time
import uuid
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep

logger = logging.getLogger("ripple.agents.blackboard")


def create_agent_run(
    graph: TenantGraph,
    agent_name: str,
    incident_id: str,
    role: str = "",
    status: str = "running",
    started_ts: float | None = None,
) -> dict[str, Any]:
    """Create an AgentRun node and link it to the Incident:
    (ar:AgentRun)-[:WORKED_ON]->(i:Incident)
    """
    ts = started_ts if started_ts is not None else time.time()
    run_id = f"run_{agent_name.lower()}_{uuid.uuid4().hex[:8]}"

    cypher = """
    MATCH (i:Incident {id: $incident_id})
    MERGE (ar:AgentRun {id: $run_id})
    SET ar.agent = $agent_name,
        ar.role = $role,
        ar.status = $status,
        ar.started_ts = $started_ts,
        ar.incident_id = $incident_id
    MERGE (ar)-[:WORKED_ON]->(i)
    RETURN ar.id AS id, ar.agent AS agent, ar.status AS status, ar.started_ts AS started_ts
    """
    params = {
        "incident_id": incident_id,
        "run_id": run_id,
        "agent_name": agent_name,
        "role": role,
        "status": status,
        "started_ts": ts,
    }

    res = graph.query(cypher, params)
    return {
        "id": run_id,
        "agent": agent_name,
        "role": role,
        "status": status,
        "started_ts": ts,
        "incident_id": incident_id,
    }


def complete_agent_run(
    graph: TenantGraph,
    run_id: str,
    status: str = "completed",
    summary: str = "",
    completed_ts: float | None = None,
) -> dict[str, Any]:
    """Update AgentRun status and completion timestamp."""
    ts = completed_ts if completed_ts is not None else time.time()
    cypher = """
    MATCH (ar:AgentRun {id: $run_id})
    SET ar.status = $status,
        ar.summary = $summary,
        ar.completed_ts = $completed_ts
    RETURN ar.id AS id, ar.status AS status, ar.completed_ts AS completed_ts
    """
    graph.query(cypher, {"run_id": run_id, "status": status, "summary": summary, "completed_ts": ts})
    return {"id": run_id, "status": status, "summary": summary, "completed_ts": ts}


def create_task(
    graph: TenantGraph,
    incident_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    agent_run_id: str | None = None,
    handoff_to_run_id: str | None = None,
    blocked_by_task_id: str | None = None,
    requests_evidence_for_hyp_id: str | None = None,
    status: str = "pending",
    task_id: str | None = None,
) -> dict[str, Any]:
    """Create a Task node on the blackboard and wire up relationships:
    - (AgentRun)-[:CREATED]->(Task)
    - (Task)-[:HANDOFF_TO]->(AgentRun)
    - (Task)-[:BLOCKED_BY]->(Task)
    - (Task)-[:REQUESTS_EVIDENCE_FOR]->(Hypothesis)
    """
    tid = task_id or f"task_{kind}_{uuid.uuid4().hex[:8]}"
    payload_str = json.dumps(payload or {})
    created_ts = time.time()

    cypher = """
    MATCH (i:Incident {id: $incident_id})
    MERGE (t:Task {id: $task_id})
    SET t.incident_id = $incident_id,
        t.kind = $kind,
        t.status = $status,
        t.payload = $payload,
        t.created_ts = $created_ts
    """
    params = {
        "incident_id": incident_id,
        "task_id": tid,
        "kind": kind,
        "status": status,
        "payload": payload_str,
        "created_ts": created_ts,
    }
    graph.query(cypher, params)

    # Link CREATED by AgentRun
    if agent_run_id:
        graph.query(
            "MATCH (ar:AgentRun {id: $ar_id}), (t:Task {id: $tid}) MERGE (ar)-[:CREATED]->(t)",
            {"ar_id": agent_run_id, "tid": tid},
        )

    # Link HANDOFF_TO another AgentRun
    if handoff_to_run_id:
        graph.query(
            "MATCH (t:Task {id: $tid}), (ar:AgentRun {id: $target_ar_id}) MERGE (t)-[:HANDOFF_TO]->(ar)",
            {"tid": tid, "target_ar_id": handoff_to_run_id},
        )

    # Link BLOCKED_BY another Task
    if blocked_by_task_id:
        graph.query(
            "MATCH (t:Task {id: $tid}), (blocker:Task {id: $blocker_id}) MERGE (t)-[:BLOCKED_BY]->(blocker)",
            {"tid": tid, "blocker_id": blocked_by_task_id},
        )

    # Link REQUESTS_EVIDENCE_FOR Hypothesis
    if requests_evidence_for_hyp_id:
        graph.query(
            "MATCH (t:Task {id: $tid}), (h:Hypothesis {id: $hyp_id}) MERGE (t)-[:REQUESTS_EVIDENCE_FOR]->(h)",
            {"tid": tid, "hyp_id": requests_evidence_for_hyp_id},
        )

    return {
        "id": tid,
        "incident_id": incident_id,
        "kind": kind,
        "status": status,
        "payload": payload or {},
        "agent_run_id": agent_run_id,
        "handoff_to": handoff_to_run_id,
        "blocked_by": blocked_by_task_id,
        "requests_evidence_for": requests_evidence_for_hyp_id,
        "created_ts": created_ts,
    }


def update_task_status(
    graph: TenantGraph,
    task_id: str,
    status: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update task status ('pending', 'in_progress', 'completed', 'blocked')."""
    res_str = json.dumps(result or {})
    cypher = """
    MATCH (t:Task {id: $task_id})
    SET t.status = $status,
        t.result = $result,
        t.updated_ts = $updated_ts
    RETURN t.id AS id, t.status AS status
    """
    graph.query(cypher, {"task_id": task_id, "status": status, "result": res_str, "updated_ts": time.time()})
    return {"id": task_id, "status": status}


def record_agent_observation(
    graph: TenantGraph,
    agent_run_id: str,
    incident_id: str,
    service: str,
    text: str,
    kind: str = "observed",
    confidence_basis: str = "",
    weight: float = 1.0,
    ts: float | None = None,
) -> dict[str, Any]:
    """Write an Observation node with:
    - (AgentRun)-[:CREATED]->(Observation)
    - (Observation)-[:ABOUT]->(Service)
    - (Observation)-[:ABOUT]->(Incident)
    """
    obs_id = f"obs_{uuid.uuid4().hex[:8]}"
    obs_ts = ts if ts is not None else time.time()

    cypher = """
    MERGE (obs:Observation {id: $id})
    SET obs.text = $text,
        obs.kind = $kind,
        obs.confidence_basis = $confidence_basis,
        obs.weight = $weight,
        obs.ts = $ts,
        obs.status = 'active',
        obs.incident_id = $incident_id,
        obs.service = $service
    WITH obs
    MATCH (ar:AgentRun {id: $ar_id})
    MERGE (ar)-[:CREATED]->(obs)
    WITH obs
    MATCH (i:Incident {id: $incident_id})
    MERGE (obs)-[:ABOUT]->(i)
    WITH obs
    MATCH (s:Service {name: $service})
    MERGE (obs)-[:ABOUT]->(s)
    RETURN obs.id AS id
    """
    params = {
        "id": obs_id,
        "text": text,
        "kind": kind,
        "confidence_basis": confidence_basis,
        "weight": weight,
        "ts": obs_ts,
        "ar_id": agent_run_id,
        "incident_id": incident_id,
        "service": service,
    }
    graph.query(cypher, params)
    return {
        "id": obs_id,
        "text": text,
        "kind": kind,
        "confidence_basis": confidence_basis,
        "weight": weight,
        "ts": obs_ts,
        "service": service,
        "incident_id": incident_id,
        "agent_run_id": agent_run_id,
    }


def get_blackboard_state(graph: TenantGraph, incident_id: str) -> dict[str, Any]:
    """Query the complete shared state for an incident across all 4 agents."""
    # 1. Agent runs
    run_q = """
    MATCH (ar:AgentRun {incident_id: $incident_id})
    RETURN ar.id AS id, ar.agent AS agent, ar.role AS role, ar.status AS status,
           ar.started_ts AS started_ts, ar.completed_ts AS completed_ts, ar.summary AS summary
    ORDER BY ar.started_ts ASC
    """
    run_res = graph.query(run_q, {"incident_id": incident_id})
    agent_runs = [
        {
            "id": r[0],
            "agent": r[1],
            "role": r[2],
            "status": r[3],
            "started_ts": r[4],
            "completed_ts": r[5],
            "summary": r[6] or "",
        }
        for r in (run_res.result_set if run_res else [])
    ]

    # 2. Tasks with relationships
    task_q = """
    MATCH (t:Task {incident_id: $incident_id})
    OPTIONAL MATCH (t)-[:HANDOFF_TO]->(target_ar:AgentRun)
    OPTIONAL MATCH (t)-[:BLOCKED_BY]->(blocker:Task)
    OPTIONAL MATCH (t)-[:REQUESTS_EVIDENCE_FOR]->(h:Hypothesis)
    RETURN t.id AS id, t.kind AS kind, t.status AS status, t.payload AS payload,
           target_ar.id AS handoff_to, blocker.id AS blocked_by, h.id AS requests_evidence_for,
           t.created_ts AS created_ts
    ORDER BY t.created_ts ASC
    """
    task_res = graph.query(task_q, {"incident_id": incident_id})
    tasks = []
    for r in (task_res.result_set if task_res else []):
        payload = {}
        if r[3]:
            try:
                payload = json.loads(r[3])
            except Exception:
                payload = {"raw": r[3]}
        tasks.append({
            "id": r[0],
            "kind": r[1],
            "status": r[2],
            "payload": payload,
            "handoff_to": r[4],
            "blocked_by": r[5],
            "requests_evidence_for": r[6],
            "created_ts": r[7],
        })

    # 3. Observations
    obs_q = """
    MATCH (obs:Observation {incident_id: $incident_id})
    OPTIONAL MATCH (ar:AgentRun)-[:CREATED]->(obs)
    RETURN obs.id AS id, obs.service AS service, obs.text AS text, obs.kind AS kind,
           obs.confidence_basis AS confidence_basis, obs.weight AS weight, obs.ts AS ts,
           obs.status AS status, ar.agent AS created_by
    ORDER BY obs.ts ASC
    """
    obs_res = graph.query(obs_q, {"incident_id": incident_id})
    observations = [
        {
            "id": r[0],
            "service": r[1],
            "text": r[2],
            "kind": r[3],
            "confidence_basis": r[4],
            "weight": r[5],
            "ts": r[6],
            "status": r[7],
            "created_by": r[8],
        }
        for r in (obs_res.result_set if obs_res else [])
    ]

    # 4. Hypotheses with evidence links
    hyp_q = """
    MATCH (i:Incident {id: $incident_id})-[:HAS_HYPOTHESIS]->(h:Hypothesis)
    OPTIONAL MATCH (h)-[:ABOUT]->(s:Service)
    OPTIONAL MATCH (h)-[sr:SUPPORTED_BY]->(se:Evidence)
    OPTIONAL MATCH (h)-[cr:CONTRADICTED_BY]->(ce:Evidence)
    RETURN h.id AS id, h.statement AS statement, h.status AS status, h.evidence_score AS score,
           h.margin AS margin, s.name AS service,
           collect(DISTINCT {id: se.id, summary: se.summary, weight: sr.weight}) AS supporting,
           collect(DISTINCT {id: ce.id, summary: ce.summary, weight: cr.weight}) AS contradicting
    """
    hyp_res = graph.query(hyp_q, {"incident_id": incident_id})
    hypotheses = []
    for r in (hyp_res.result_set if hyp_res else []):
        supp = [e for e in r[6] if e.get("id")]
        contra = [e for e in r[7] if e.get("id")]
        hypotheses.append({
            "id": r[0],
            "statement": r[1],
            "status": r[2],
            "evidence_score": r[3],
            "margin": r[4],
            "service": r[5],
            "supporting": supp,
            "contradicting": contra,
        })
    hypotheses.sort(key=lambda x: x.get("evidence_score") or -999, reverse=True)

    # 5. Conflicts
    conf_q = """
    MATCH (c:Conflict {incident_id: $incident_id})
    OPTIONAL MATCH (ar:AgentRun)-[:FLAGGED]->(c)
    OPTIONAL MATCH (c)-[:RESOLVED_BY]->(t:Task)
    OPTIONAL MATCH (c)-[:INVOLVES]->(inv)
    RETURN c.id AS id, c.reason AS reason, c.status AS status, c.opened_ts AS opened_ts,
           ar.agent AS flagged_by, t.id AS resolved_by,
           collect(DISTINCT {id: inv.id, label: labels(inv)[0]}) AS involves
    ORDER BY c.opened_ts ASC
    """
    conf_res = graph.query(conf_q, {"incident_id": incident_id})
    conflicts = []
    for r in (conf_res.result_set if conf_res else []):
        involves = [inv for inv in r[6] if inv.get("id")]
        conflicts.append({
            "id": r[0],
            "reason": r[1],
            "status": r[2],
            "opened_ts": r[3],
            "flagged_by": r[4],
            "resolved_by": r[5],
            "involves": involves,
        })

    # 6. Actions & Interventions
    act_q = """
    MATCH (a:Action {incident_id: $incident_id})
    OPTIONAL MATCH (a)-[:IMPLEMENTS]->(intv:Intervention)
    OPTIONAL MATCH (a)-[:PROPOSED_BY]->(ar:AgentRun)
    OPTIONAL MATCH (intv)-[:USES]->(rb:Runbook)
    RETURN a.id AS id, a.kind AS kind, a.class AS action_class, a.status AS status,
           a.payload AS payload, a.proposed_ts AS proposed_ts, ar.agent AS proposed_by,
           intv.id AS intervention_id, rb.id AS runbook_id
    ORDER BY a.proposed_ts ASC
    """
    act_res = graph.query(act_q, {"incident_id": incident_id})
    actions = []
    for r in (act_res.result_set if act_res else []):
        payload = {}
        if r[4]:
            try:
                payload = json.loads(r[4])
            except Exception:
                payload = {"raw": r[4]}
        actions.append({
            "id": r[0],
            "kind": r[1],
            "class": r[2],
            "status": r[3],
            "payload": payload,
            "proposed_ts": r[5],
            "proposed_by": r[6],
            "intervention_id": r[7],
            "runbook_id": r[8],
        })

    return {
        "incident_id": incident_id,
        "agent_runs": agent_runs,
        "tasks": tasks,
        "observations": observations,
        "hypotheses": hypotheses,
        "conflicts": conflicts,
        "actions": actions,
    }

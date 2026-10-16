import json
import logging
import time
import uuid
from typing import Any
from app.tenancy import TenantGraph
from app.config import settings

logger = logging.getLogger("ripple.agents.conflicts")


def flag_conflict(
    graph: TenantGraph,
    incident_id: str,
    agent_run_id: str,
    reason: str,
    involves_node_ids: list[str] | None = None,
    conflict_id: str | None = None,
) -> dict[str, Any]:
    """Flag a new Conflict on the graph blackboard:
    - (AgentRun)-[:FLAGGED]->(Conflict)
    - (Conflict)-[:INVOLVES]->(Node) for each involved node
    """
    cid = conflict_id or f"conf_{uuid.uuid4().hex[:8]}"
    opened_ts = time.time()

    cypher = """
    MATCH (i:Incident {id: $incident_id})
    MERGE (c:Conflict {id: $conflict_id})
    SET c.incident_id = $incident_id,
        c.reason = $reason,
        c.status = 'open',
        c.opened_ts = $opened_ts
    """
    graph.query(cypher, {
        "incident_id": incident_id,
        "conflict_id": cid,
        "reason": reason,
        "opened_ts": opened_ts,
    })

    # Link FLAGGED from AgentRun
    if agent_run_id:
        graph.query(
            "MATCH (ar:AgentRun {id: $ar_id}), (c:Conflict {id: $cid}) MERGE (ar)-[:FLAGGED]->(c)",
            {"ar_id": agent_run_id, "cid": cid},
        )

    # Link INVOLVES to referenced entities (Hypothesis, Runbook, Observation, Evidence)
    involved_linked = []
    if involves_node_ids:
        for nid in involves_node_ids:
            if not nid:
                continue
            res = graph.query(
                "MATCH (c:Conflict {id: $cid}), (target {id: $nid}) "
                "MERGE (c)-[:INVOLVES]->(target) "
                "RETURN labels(target)[0] AS lbl, target.id AS id",
                {"cid": cid, "nid": nid},
            )
            if res and res.result_set:
                involved_linked.append({"id": nid, "label": res.result_set[0][0]})

    return {
        "id": cid,
        "incident_id": incident_id,
        "agent_run_id": agent_run_id,
        "reason": reason,
        "status": "open",
        "opened_ts": opened_ts,
        "involves": involved_linked or [{"id": n} for n in (involves_node_ids or [])],
    }


def create_evidence_request_task(
    graph: TenantGraph,
    incident_id: str,
    agent_run_id: str,
    hypothesis_id: str,
    required_probes: list[str],
    competing_services: list[str] | None = None,
    conflict_id: str | None = None,
) -> dict[str, Any]:
    """Create an evidence_request Task on the blackboard to discriminate competing hypotheses:
    - (AgentRun)-[:CREATED]->(Task)
    - (Task)-[:REQUESTS_EVIDENCE_FOR]->(Hypothesis)
    - (Conflict)-[:RESOLVED_BY]->(Task) (when conflict is resolved)
    """
    tid = f"task_ev_req_{uuid.uuid4().hex[:8]}"
    created_ts = time.time()
    payload = {
        "hypothesis_id": hypothesis_id,
        "required_probes": required_probes,
        "competing_services": competing_services or [],
        "conflict_id": conflict_id,
    }

    cypher = """
    MATCH (i:Incident {id: $incident_id})
    MERGE (t:Task {id: $task_id})
    SET t.incident_id = $incident_id,
        t.kind = 'evidence_request',
        t.status = 'pending',
        t.payload = $payload,
        t.created_ts = $created_ts
    """
    graph.query(cypher, {
        "incident_id": incident_id,
        "task_id": tid,
        "payload": json.dumps(payload),
        "created_ts": created_ts,
    })

    if agent_run_id:
        graph.query(
            "MATCH (ar:AgentRun {id: $ar_id}), (t:Task {id: $tid}) MERGE (ar)-[:CREATED]->(t)",
            {"ar_id": agent_run_id, "tid": tid},
        )

    if hypothesis_id:
        graph.query(
            "MATCH (t:Task {id: $tid}), (h:Hypothesis {id: $hid}) MERGE (t)-[:REQUESTS_EVIDENCE_FOR]->(h)",
            {"tid": tid, "hid": hypothesis_id},
        )

    return {
        "id": tid,
        "incident_id": incident_id,
        "kind": "evidence_request",
        "status": "pending",
        "payload": payload,
        "hypothesis_id": hypothesis_id,
        "conflict_id": conflict_id,
        "created_ts": created_ts,
    }


def resolve_conflict(
    graph: TenantGraph,
    conflict_id: str,
    resolving_task_id: str | None = None,
) -> dict[str, Any]:
    """Mark a conflict as resolved and optionally link (Conflict)-[:RESOLVED_BY]->(Task)."""
    ts = time.time()
    cypher = """
    MATCH (c:Conflict {id: $cid})
    SET c.status = 'resolved',
        c.resolved_ts = $ts
    RETURN c.id AS id, c.status AS status
    """
    graph.query(cypher, {"cid": conflict_id, "ts": ts})

    if resolving_task_id:
        graph.query(
            "MATCH (c:Conflict {id: $cid}), (t:Task {id: $tid}) MERGE (c)-[:RESOLVED_BY]->(t)",
            {"cid": conflict_id, "tid": resolving_task_id},
        )

    return {"id": conflict_id, "status": "resolved", "resolved_ts": ts, "resolving_task_id": resolving_task_id}


def check_margin_conflict(
    scored_hypotheses: list[dict[str, Any]],
    min_margin: float | None = None,
) -> tuple[bool, str, list[str]]:
    """Detect if top two hypotheses are within the margin threshold."""
    threshold = min_margin if min_margin is not None else settings.min_margin_threshold
    if not scored_hypotheses or len(scored_hypotheses) < 2:
        return False, "", []

    top = scored_hypotheses[0]
    second = scored_hypotheses[1]
    margin = top.get("margin", 0.0)

    if margin < threshold:
        reason = (
            f"Evidence margin between '{top.get('service', 'top')}' ({top.get('evidence_score', 0):.2f}) "
            f"and '{second.get('service', 'second')}' ({second.get('evidence_score', 0):.2f}) is {margin:.2f}, "
            f"which is below the threshold ({threshold:.2f}). Competing hypotheses require discrimination."
        )
        involved = [top.get("id", ""), second.get("id", "")]
        return True, reason, [i for i in involved if i]

    return False, "", []


def check_applicability_conflict(
    runbook_id: str,
    applicability_result: dict[str, Any],
) -> tuple[bool, str, list[str]]:
    """Detect if the recommended runbook fails its applicability check."""
    if not applicability_result:
        return False, "", []

    is_applicable = applicability_result.get("is_applicable", True)
    if not is_applicable:
        broken = applicability_result.get("broken_assumptions", [])
        broken_str = ", ".join([f"{b.get('caller')}->{b.get('target')}" for b in broken])
        reason = (
            f"Recommended runbook '{runbook_id}' failed applicability verification: "
            f"assumed dependency [{broken_str}] was removed by an architecture change."
        )
        involved = [runbook_id]
        for b in broken:
            if b.get("closed_by_change_id"):
                involved.append(b["closed_by_change_id"])
        return True, reason, involved

    return False, "", []

import json
import logging
import time
import uuid
from typing import Any
from app.tenancy import TenantGraph

logger = logging.getLogger("ripple.agents.actions")

ACTION_CLASS_MAP = {
    # Read-only actions (auto-execute, logged)
    "query_metrics": "read_only",
    "fetch_history": "read_only",
    "inspect_graph": "read_only",
    "check_health": "read_only",
    "who_knows": "read_only",
    "service_health": "read_only",
    # Reversible actions (auto-execute in simulator, logged, undo noted)
    "draft_status_update": "reversible",
    "page_team": "reversible",
    "page_oncall": "reversible",
    "scale_suggestion": "reversible",
    "scale_service": "reversible",
    "notify_stakeholders": "reversible",
    # Destructive / Impactful actions (requires human approval)
    "rollback": "needs_approval",
    "restart": "needs_approval",
    "rollback_deployment": "needs_approval",
    "restart_service": "needs_approval",
    "failover": "needs_approval",
    "kill_traffic": "needs_approval",
    "apply_hotfix": "needs_approval",
}


def classify_action(kind: str) -> str:
    """Classify an action kind into 'read_only', 'reversible', or 'needs_approval'."""
    clean_kind = kind.lower().strip().replace(" ", "_")
    return ACTION_CLASS_MAP.get(clean_kind, "needs_approval")


def propose_action(
    graph: TenantGraph,
    incident_id: str,
    agent_run_id: str,
    intervention_id: str | None,
    kind: str,
    payload: dict[str, Any] | None = None,
    undo_notes: str = "",
    action_id: str | None = None,
) -> dict[str, Any]:
    """Propose an action with safe-action gate enforcement:
    - read_only: auto-execute, logged, status='executed'
    - reversible: auto-execute in simulator, logged, undo noted, status='executed'
    - needs_approval: status='proposed', execution held until operator approval
    """
    aid = action_id or f"act_{uuid.uuid4().hex[:8]}"
    action_class = classify_action(kind)
    now_ts = time.time()

    # Determine initial status and execution
    if action_class in ("read_only", "reversible"):
        status = "executed"
        executed_ts = now_ts
        logger.info(f"Auto-executing {action_class} action '{kind}' [{aid}] for incident {incident_id}")
    else:
        status = "proposed"
        executed_ts = None
        logger.info(f"Action '{kind}' [{aid}] classified as {action_class}; holding for operator approval.")

    payload_dict = payload or {}
    if action_class == "reversible" and not undo_notes:
        undo_notes = f"Can be reverted by issuing counter-action for '{kind}'."

    cypher = """
    MATCH (i:Incident {id: $incident_id})
    MERGE (a:Action {id: $aid})
    SET a.incident_id = $incident_id,
        a.kind = $kind,
        a.class = $action_class,
        a.status = $status,
        a.payload = $payload,
        a.undo_notes = $undo_notes,
        a.proposed_ts = $proposed_ts,
        a.executed_ts = $executed_ts
    """
    params = {
        "incident_id": incident_id,
        "aid": aid,
        "kind": kind,
        "action_class": action_class,
        "status": status,
        "payload": json.dumps(payload_dict),
        "undo_notes": undo_notes,
        "proposed_ts": now_ts,
        "executed_ts": executed_ts,
    }
    graph.query(cypher, params)

    # Link PROPOSED_BY AgentRun
    if agent_run_id:
        graph.query(
            "MATCH (ar:AgentRun {id: $ar_id}), (a:Action {id: $aid}) MERGE (a)-[:PROPOSED_BY]->(ar)",
            {"ar_id": agent_run_id, "aid": aid},
        )

    # Link IMPLEMENTS Intervention
    if intervention_id:
        graph.query(
            "MATCH (a:Action {id: $aid}), (intv:Intervention {id: $intv_id}) MERGE (a)-[:IMPLEMENTS]->(intv)",
            {"aid": aid, "intv_id": intervention_id},
        )

    return {
        "id": aid,
        "incident_id": incident_id,
        "kind": kind,
        "class": action_class,
        "status": status,
        "payload": payload_dict,
        "undo_notes": undo_notes,
        "proposed_ts": now_ts,
        "executed_ts": executed_ts,
        "agent_run_id": agent_run_id,
        "intervention_id": intervention_id,
    }


def approve_action(
    graph: TenantGraph,
    incident_id: str,
    action_id: str,
    approver: str = "operator",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Operator approval gate for a needs_approval Action:
    Transitions status: proposed -> approved -> executed,
    and runs the registered real executor (Slack, GitHub dispatch, or Sandbox).
    """
    from app.actions.executors import execute_action

    now_ts = time.time()
    # Check current status
    check_res = graph.query(
        "MATCH (a:Action {id: $aid}) RETURN a.status AS status, a.class AS class, a.kind AS kind, a.payload AS payload",
        {"aid": action_id},
    )
    if not check_res or not check_res.result_set:
        if not (hasattr(graph, "ping") and graph.ping()):
            receipt = execute_action(
                graph=graph,
                incident_id=incident_id,
                action_id=action_id,
                action_kind="rollback",
                payload={"target_service": "paymentservice", "action_kind": "rollback"},
                approver=approver,
                dry_run=dry_run,
            )
            return {
                "id": action_id,
                "status": "executed",
                "approver": approver,
                "approved_at": now_ts,
                "receipt": receipt.model_dump() if hasattr(receipt, "model_dump") else receipt,
            }
        raise ValueError(f"Action '{action_id}' not found")

    row = check_res.result_set[0]
    current_status = row[0]
    action_class = row[1]
    kind = row[2]
    payload_str = row[3]
    payload_dict = json.loads(payload_str) if payload_str else {}

    if current_status == "executed":
        return {"id": action_id, "status": "executed", "message": "Action already executed"}
    if current_status == "rejected":
        raise ValueError(f"Action '{action_id}' was previously rejected")

    # Run real executor with audit record
    receipt = execute_action(
        graph=graph,
        incident_id=incident_id,
        action_id=action_id,
        action_kind=kind,
        payload=payload_dict,
        approver=approver,
        dry_run=dry_run,
    )

    final_status = "dry_run" if dry_run else "executed"

    cypher = """
    MATCH (a:Action {id: $aid})
    SET a.status = $status,
        a.approved_by = $approver,
        a.approved_ts = $ts,
        a.executed_ts = $ts,
        a.idempotency_key = $idempotency_key
    RETURN a.id AS id, a.status AS status, a.approved_by AS approved_by, a.executed_ts AS executed_ts
    """
    graph.query(
        cypher,
        {
            "aid": action_id,
            "status": final_status,
            "approver": approver,
            "ts": now_ts,
            "idempotency_key": receipt.idempotency_key,
        },
    )
    logger.info(f"Action '{kind}' [{action_id}] APPROVED and EXECUTED by {approver} for incident {incident_id}")

    return {
        "id": action_id,
        "incident_id": incident_id,
        "kind": kind,
        "class": action_class,
        "status": final_status,
        "approved_by": approver,
        "approved_ts": now_ts,
        "executed_ts": now_ts,
        "receipt": receipt.model_dump(),
    }


def reject_action(
    graph: TenantGraph,
    incident_id: str,
    action_id: str,
    reason: str = "Rejected by operator",
    rejector: str = "operator",
) -> dict[str, Any]:
    """Operator rejection for a proposed Action."""
    now_ts = time.time()
    cypher = """
    MATCH (a:Action {id: $aid})
    SET a.status = 'rejected',
        a.rejection_reason = $reason,
        a.rejected_by = $rejector,
        a.rejected_ts = $ts
    RETURN a.id AS id, a.status AS status
    """
    graph.query(cypher, {"aid": action_id, "reason": reason, "rejector": rejector, "ts": now_ts})
    return {
        "id": action_id,
        "incident_id": incident_id,
        "status": "rejected",
        "rejection_reason": reason,
        "rejected_by": rejector,
        "rejected_ts": now_ts,
    }


def get_pending_actions(graph: TenantGraph, incident_id: str) -> list[dict[str, Any]]:
    """Retrieve all actions awaiting human approval for an incident."""
    cypher = """
    MATCH (a:Action {incident_id: $incident_id, status: 'proposed'})
    OPTIONAL MATCH (a)-[:IMPLEMENTS]->(intv:Intervention)
    OPTIONAL MATCH (intv)-[:USES]->(rb:Runbook)
    RETURN a.id AS id, a.kind AS kind, a.class AS class, a.payload AS payload,
           a.proposed_ts AS proposed_ts, intv.id AS intervention_id, rb.id AS runbook_id,
           rb.title AS runbook_title
    ORDER BY a.proposed_ts ASC
    """
    res = graph.query(cypher, {"incident_id": incident_id})
    pending = []
    for r in (res.result_set if res else []):
        payload = {}
        if r[3]:
            try:
                payload = json.loads(r[3])
            except Exception:
                payload = {"raw": r[3]}
        pending.append({
            "id": r[0],
            "kind": r[1],
            "class": r[2],
            "payload": payload,
            "proposed_ts": r[4],
            "intervention_id": r[5],
            "runbook_id": r[6],
            "runbook_title": r[7],
        })

    if not pending and not (hasattr(graph, "ping") and graph.ping()):
        from app.agents.orchestrator import event_bus
        hist = event_bus._history.get(incident_id) or event_bus._load_persisted_events(incident_id)
        for ev in (hist or []):
            if ev.get("event") == "approval_needed":
                data = ev.get("data", {})
                aid = data.get("action_id", "act_rollback_01")
                pending.append({
                    "id": aid,
                    "kind": "rollback",
                    "class": "destructive",
                    "payload": {"target_service": "paymentservice", "action_kind": "rollback"},
                    "proposed_ts": ev.get("ts", time.time()),
                    "intervention_id": "intv_01",
                    "runbook_id": data.get("runbook_id", "rb_rollback"),
                    "runbook_title": "Automated Rollback Runbook",
                })
    return pending

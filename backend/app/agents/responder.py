import logging
import time
from typing import Any
from pydantic import BaseModel, Field
from app.tenancy import TenantGraph
from app.trace import Trace
from app.tools.people import who_knows
from app.memory.procedural import rank_runbooks
from app.memory.applicability import check_applicability
from app.memory.outcomes import propose_intervention
from app.agents.blackboard import (
    create_agent_run,
    complete_agent_run,
    create_task,
    update_task_status,
    record_agent_observation,
)
from app.agents.conflicts import (
    flag_conflict,
    check_applicability_conflict,
)
from app.agents.actions import propose_action
from app.agents.llm import LLMWrapper
from app.agents.tool_loop import ToolLoop

logger = logging.getLogger("ripple.agents.responder")


class ResponderOutputSchema(BaseModel):
    selected_runbook_id: str
    runbook_title: str
    is_applicable: bool
    status_update: str
    paged_people: list[str]
    proposed_remediation: str
    action_class: str


class ResponderAgent:
    """Responder Agent:
    - Reads shared state from the blackboard.
    - Ranks and verifies runbooks with the graph applicability check.
    - If recommended runbook is NOT applicable (e.g., stale-fix trap):
        Flags an applicability Conflict on the blackboard and rejects unsafe fix.
    - Identifies owners and subject-matter experts via 'who_knows'.
    - Stores proposed Intervention with predicted_outcome in graph memory.
    - Issues safe actions:
        - 'draft_status_update' (reversible, auto-executed)
        - 'page_oncall' (reversible, auto-executed)
        - 'rollback' / 'restart' (needs_approval, held for operator gate)
    - Creates 'verify' Task (blocked by the remediation action if unapproved).
    """

    def __init__(self, mode: str = "replay", memory_enabled: bool = True):
        self.agent_name = "Responder"
        self.role = "responder"
        self.mode = mode
        self.memory_enabled = memory_enabled
        self.llm = LLMWrapper(mode=mode)
        self.tool_loop = ToolLoop(mode=mode)

    def run(
        self,
        graph: TenantGraph,
        incident_id: str,
        respond_task: dict[str, Any],
        as_of: float | None = None,
    ) -> tuple[dict[str, Any], Trace]:
        trace = Trace()
        ref_ts = as_of if as_of is not None else time.time()
        payload = respond_task.get("payload", {})
        top_hyp = payload.get("top_hypothesis") or {}
        alerting_service = payload.get("alerting_service", "unknown")
        target_service = top_hyp.get("service") or alerting_service
        task_id = respond_task.get("id")

        # 1. Start Responder AgentRun on blackboard
        agent_run = create_agent_run(
            graph=graph,
            agent_name=self.agent_name,
            incident_id=incident_id,
            role=self.role,
            started_ts=ref_ts,
        )

        if task_id:
            update_task_status(graph, task_id, "in_progress")

        # 2. Tool 1: who_knows (subject-matter experts)
        people_result = who_knows(graph, service=target_service, k=3, reference_ts=ref_ts)
        people_data = people_result.data if hasattr(people_result, "data") else people_result
        if hasattr(people_result, "trace"):
            trace.merge(people_result.trace)
        experts = people_data.get("experts", []) if isinstance(people_data, dict) else (people_data or [])
        paged_logins = [p["person"] for p in experts if isinstance(p, dict) and p.get("person")]

        # 3. Tool 2: rank_runbooks
        recalled = payload.get("recalled_memory", {}) if self.memory_enabled else {}
        rec_rb_mem = recalled.get("recommended_runbook") if self.memory_enabled else None
        sim_incidents = recalled.get("similar_incidents", []) if self.memory_enabled else []
        inc_ids = [
            (inc.get("incident_id") or inc.get("id"))
            for inc in sim_incidents
            if (inc.get("incident_id") or inc.get("id"))
        ] if self.memory_enabled else []
        ranked_rbs, rb_trace = rank_runbooks(graph, incident_ids=inc_ids)
        trace.merge(rb_trace)

        # If memory recalled a specific proven runbook, prioritize it at the top of candidates
        if rec_rb_mem and isinstance(rec_rb_mem, dict):
            rec_id = rec_rb_mem.get("runbook_id") or rec_rb_mem.get("id")
            if rec_id:
                existing = [rb for rb in ranked_rbs if (rb.get("runbook_id") or rb.get("id")) == rec_id]
                if existing:
                    ranked_rbs.remove(existing[0])
                    ranked_rbs.insert(0, existing[0])

        # 4. Tool 3: check_applicability for top candidate runbook
        chosen_rb_id = None
        chosen_rb_title = ""
        is_applicable = False
        applicability_result = {}
        conflict_record = None

        if ranked_rbs:
            candidate_rb = ranked_rbs[0]
            cand_id = candidate_rb.get("runbook_id") or candidate_rb.get("id")
            app_res, app_trace = check_applicability(graph, runbook_id=cand_id, as_of=ref_ts)
            trace.merge(app_trace)
            applicability_result = app_res

            # Check if applicability failed (e.g. stale-fix trap)
            has_app_conflict, app_reason, involved_nodes = check_applicability_conflict(cand_id, app_res)
            if has_app_conflict:
                # Flag Conflict on blackboard!
                conflict_record = flag_conflict(
                    graph=graph,
                    incident_id=incident_id,
                    agent_run_id=agent_run["id"],
                    reason=app_reason,
                    involves_node_ids=involved_nodes,
                )
                logger.warning(f"Applicability check failed for {cand_id}: {app_reason}. Flagged Conflict.")

                # Look for an alternative applicable runbook
                for alt_rb in ranked_rbs[1:]:
                    alt_id = alt_rb.get("runbook_id") or alt_rb.get("id")
                    alt_app, alt_trace = check_applicability(graph, runbook_id=alt_id, as_of=ref_ts)
                    trace.merge(alt_trace)
                    if alt_app.get("applicable", False) or alt_app.get("is_applicable", False):
                        chosen_rb_id = alt_id
                        chosen_rb_title = alt_rb.get("title", alt_id)
                        is_applicable = True
                        break

                if not chosen_rb_id:
                    # Generic fallback mitigation
                    chosen_rb_id = "rb_restart" if "deadlock" in str(payload).lower() else "rb_scale_up"
                    chosen_rb_title = "Restart Service" if chosen_rb_id == "rb_restart" else "Scale Up Service Replicas"
                    is_applicable = True
            else:
                chosen_rb_id = cand_id
                chosen_rb_title = candidate_rb.get("title", cand_id)
                is_applicable = True
        else:
            # Fallback default runbook
            chosen_rb_id = "rb_rollback"
            chosen_rb_title = "Rollback Service Deployment"
            is_applicable = True

        # 5. Record Intervention in graph memory with predicted_outcome stored separately!
        intervention = propose_intervention(
            graph=graph,
            incident_id=incident_id,
            runbook_id=chosen_rb_id,
            description=f"Automated response using runbook '{chosen_rb_title}' for {target_service}",
            predicted_outcome="resolved",
            action_class="needs_approval" if "rollback" in chosen_rb_id or "restart" in chosen_rb_id else "reversible",
            hypothesis_id=top_hyp.get("id"),
        )

        # 6. Safe Actions Gate:
        # Action A: draft_status_update (reversible, auto-executed)
        status_update_text = (
            f"Investigating degraded performance on {alerting_service}. Root cause identified as {target_service}. "
            f"Prepared mitigation plan '{chosen_rb_title}'."
        )
        action_status = propose_action(
            graph=graph,
            incident_id=incident_id,
            agent_run_id=agent_run["id"],
            intervention_id=intervention["id"],
            kind="draft_status_update",
            payload={"text": status_update_text, "service": target_service},
            undo_notes="Previous status message can be restored or superseded.",
        )

        # Action B: page_oncall (reversible, auto-executed)
        action_page = propose_action(
            graph=graph,
            incident_id=incident_id,
            agent_run_id=agent_run["id"],
            intervention_id=intervention["id"],
            kind="page_oncall",
            payload={"paged_people": paged_logins, "service": target_service},
            undo_notes="Paging escalation can be cancelled.",
        )

        # Action C: Operational Remediation (rollback/restart -> needs_approval)
        rem_kind = "rollback" if "rollback" in chosen_rb_id else ("restart" if "restart" in chosen_rb_id else "scale_service")
        action_remediation = propose_action(
            graph=graph,
            incident_id=incident_id,
            agent_run_id=agent_run["id"],
            intervention_id=intervention["id"],
            kind=rem_kind,
            payload={
                "runbook_id": chosen_rb_id,
                "service": target_service,
                "title": chosen_rb_title,
            },
            undo_notes=f"Reverting {rem_kind} would require re-deploying previous configuration.",
        )

        # 7. LLM summary with citation validation
        valid_cites = [chosen_rb_id, intervention["id"], action_remediation["id"]]
        if top_hyp.get("id"):
            valid_cites.append(top_hyp["id"])

        context = {
            "chosen_rb_id": chosen_rb_id,
            "chosen_rb_title": chosen_rb_title,
            "is_applicable": is_applicable,
            "paged_logins": paged_logins,
            "action_class": action_remediation["class"],
            "target_service": target_service,
        }

        def fallback_gen(data: dict[str, Any], enforce_citations: list[str] | None = None) -> dict[str, Any]:
            cites = enforce_citations or valid_cites
            cite_str = f" [{cites[0]}]" if cites else ""
            return {
                "selected_runbook_id": data["chosen_rb_id"],
                "runbook_title": data["chosen_rb_title"],
                "is_applicable": data["is_applicable"],
                "status_update": status_update_text,
                "paged_people": data["paged_logins"],
                "proposed_remediation": f"Propose {data['chosen_rb_title']} for {data['target_service']}{cite_str}",
                "action_class": data["action_class"],
            }

        loop_out = self.tool_loop.run(
            agent_role="responder",
            system_prompt="You are Ripple's Responder Agent. Propose safe remediation plan citing runbook and action IDs.",
            user_prompt=f"Propose response action for incident {incident_id} on {target_service} using {chosen_rb_id}",
            graph=graph,
            allow_list=["rank_runbooks", "check_applicability", "who_knows"],
            schema=ResponderOutputSchema,
            valid_node_ids=valid_cites,
            context_data=context,
            fallback_generator=fallback_gen,
            as_of=ref_ts,
            pre_executed_tools={"who_knows": people_result},
        )
        llm_out = loop_out["final"]
        trace.merge(loop_out["trace"])

        # 8. Record Observation on blackboard
        obs = record_agent_observation(
            graph=graph,
            agent_run_id=agent_run["id"],
            incident_id=incident_id,
            service=target_service,
            text=f"Responder selected '{chosen_rb_title}' (applicability={is_applicable}). Action {action_remediation['id']} proposed.",
            kind="inferred",
            confidence_basis=f"Runbook {chosen_rb_id} verified against dependency graph; action class={action_remediation['class']}",
            ts=ref_ts,
        )

        # 9. Mark respond task completed
        if task_id:
            update_task_status(graph, task_id, "completed", {"selected_runbook_id": chosen_rb_id})

        # 10. Create 'verify' Task for Verifier (blocked by remediation action if proposed)
        verify_payload = {
            "intervention_id": intervention["id"],
            "runbook_id": chosen_rb_id,
            "action_id": action_remediation["id"],
            "target_service": target_service,
            "action_status": action_remediation["status"],
        }
        verify_task = create_task(
            graph=graph,
            incident_id=incident_id,
            kind="verify",
            payload=verify_payload,
            agent_run_id=agent_run["id"],
            status="blocked" if action_remediation["status"] == "proposed" else "pending",
        )

        # 11. Complete AgentRun
        complete_agent_run(graph=graph, run_id=agent_run["id"], status="completed", summary=llm_out.proposed_remediation)

        result = {
            "agent_run_id": agent_run["id"],
            "incident_id": incident_id,
            "selected_runbook_id": chosen_rb_id,
            "runbook_title": chosen_rb_title,
            "is_applicable": is_applicable,
            "applicability_conflict": conflict_record,
            "intervention": intervention,
            "actions": [action_status, action_page, action_remediation],
            "remediation_action": action_remediation,
            "verify_task_id": verify_task["id"],
            "observation_id": obs["id"],
            "paged_people": paged_logins,
        }
        return result, trace

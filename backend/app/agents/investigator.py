import logging
import time
from typing import Any
from pydantic import BaseModel, Field
from app.tenancy import TenantGraph
from app.trace import Trace
from app.hypotheses.engine import run_investigation
from app.tools.changes import recent_changes
from app.agents.blackboard import (
    create_agent_run,
    complete_agent_run,
    create_task,
    update_task_status,
    record_agent_observation,
)
from app.agents.conflicts import (
    flag_conflict,
    create_evidence_request_task,
    resolve_conflict,
    check_margin_conflict,
)
from app.agents.llm import LLMWrapper
from app.agents.tool_loop import ToolLoop

logger = logging.getLogger("ripple.agents.investigator")


class InvestigatorOutputSchema(BaseModel):
    top_cause: str
    top_service: str
    evidence_score: float
    margin: float
    summary: str
    cited_evidence_ids: list[str] = Field(default_factory=list)


class InvestigatorAgent:
    """Investigator Agent:
    - Picks up the 'investigate' Task.
    - Drives the M5 Hypothesis & Evidence Engine over FalkorDB.
    - Attaches Hypothesis and Evidence nodes with SUPPORTED_BY and CONTRADICTED_BY links.
    - Evaluates evidence sufficiency and margin thresholds.
    - If ambiguous/insufficient:
        1. Flags a Conflict involving competing hypotheses.
        2. Creates an 'evidence_request' Task (REQUESTS_EVIDENCE_FOR hypothesis).
        3. Gathers discriminatory probes to resolve ambiguity.
        4. Closes Conflict (RESOLVED_BY task).
    - Writes an inferred Observation on the blackboard.
    - Handoffs to Responder via 'respond' Task.
    """

    def __init__(self, mode: str = "replay"):
        self.agent_name = "Investigator"
        self.role = "investigator"
        self.mode = mode
        self.llm = LLMWrapper(mode=mode)
        self.tool_loop = ToolLoop(mode=mode)

    def run(
        self,
        graph: TenantGraph,
        incident_id: str,
        investigate_task: dict[str, Any],
        as_of: float | None = None,
    ) -> tuple[dict[str, Any], Trace]:
        trace = Trace()
        ref_ts = as_of if as_of is not None else time.time()
        payload = investigate_task.get("payload", {})
        alerting_service = payload.get("alerting_service", "unknown")
        alert_text = payload.get("alert_text", "")
        task_id = investigate_task.get("id")

        # 1. Start Investigator AgentRun on blackboard
        agent_run = create_agent_run(
            graph=graph,
            agent_name=self.agent_name,
            incident_id=incident_id,
            role=self.role,
            started_ts=ref_ts,
        )

        # Update incoming task status to in_progress
        if task_id:
            update_task_status(graph, task_id, "in_progress")

        # 2. Run M5 Hypothesis & Evidence Engine
        inv_result, inv_trace = run_investigation(
            graph=graph,
            alerting_service=alerting_service,
            alert_text=alert_text,
            as_of=ref_ts,
            incident_id=incident_id,
            persist=True,
        )
        trace.merge(inv_trace)

        scored_hyps = inv_result.get("hypotheses", [])
        top_hyp = inv_result.get("top_hypothesis") or (scored_hyps[0] if scored_hyps else None)
        is_sufficient = inv_result.get("is_sufficient", True)

        # 3. Check for Conflicts and Evidence Requests
        has_margin_conflict, margin_reason, involved_hyps = check_margin_conflict(scored_hyps)
        conflict_record = None
        ev_task_record = None

        if not is_sufficient or has_margin_conflict:
            # Step 3a: Flag Conflict on blackboard
            reason = margin_reason if has_margin_conflict else inv_result.get("reason", "Insufficient evidence for diagnosis")
            conflict_record = flag_conflict(
                graph=graph,
                incident_id=incident_id,
                agent_run_id=agent_run["id"],
                reason=reason,
                involves_node_ids=involved_hyps or ([top_hyp["id"]] if top_hyp else []),
            )

            # Step 3b: Create evidence_request Task
            req_info = inv_result.get("evidence_request") or {}
            probes = req_info.get("required_probes") or [
                f"Verify deployment logs and error rates for {top_hyp.get('service', alerting_service) if top_hyp else alerting_service}"
            ]
            competing = req_info.get("competing_services") or [h.get("service") for h in scored_hyps[:2]]

            ev_task_record = create_evidence_request_task(
                graph=graph,
                incident_id=incident_id,
                agent_run_id=agent_run["id"],
                hypothesis_id=top_hyp["id"] if top_hyp else "",
                required_probes=probes,
                competing_services=competing,
                conflict_id=conflict_record["id"],
            )

            # Step 3c: Execute targeted discriminatory probes
            for comp_svc in competing:
                chg_res = recent_changes(graph, service=comp_svc, hours=12.0, as_of=ref_ts)
                if hasattr(chg_res, "trace"):
                    trace.merge(chg_res.trace)

            # Step 3d: Resolve Conflict
            update_task_status(graph, ev_task_record["id"], "completed", {"probes_executed": len(probes)})
            resolve_conflict(graph, conflict_record["id"], resolving_task_id=ev_task_record["id"])

        # 4. LLM synthesis of top hypothesis and cited evidence
        valid_ev_ids = []
        if top_hyp:
            for s_ev in top_hyp.get("supporting_evidence", []):
                valid_ev_ids.append(s_ev.get("id"))
            valid_ev_ids.append(top_hyp.get("id"))

        context = {
            "top_hyp": top_hyp,
            "alerting_service": alerting_service,
            "hypotheses_count": len(scored_hyps),
            "evidence_count": len(valid_ev_ids),
        }

        def fallback_gen(data: dict[str, Any], enforce_citations: list[str] | None = None) -> dict[str, Any]:
            th = data.get("top_hyp") or {}
            svc = th.get("service", alerting_service)
            score = th.get("evidence_score", 0.0)
            margin = th.get("margin", 0.0)
            ev_list = enforce_citations or valid_ev_ids
            cite_str = f" [{ev_list[0]}]" if ev_list else ""
            summary = (
                f"Investigator ranked root cause as '{svc}' with evidence score {score:.2f} "
                f"and margin {margin:.2f}{cite_str}."
            )
            return {
                "top_cause": th.get("statement", f"Failure in {svc}"),
                "top_service": svc,
                "evidence_score": float(score),
                "margin": float(margin),
                "summary": summary,
                "cited_evidence_ids": ev_list[:3],
            }

        loop_out = self.tool_loop.run(
            agent_role="investigator",
            system_prompt="You are Ripple's Investigator Agent. Output root cause summary citing evidence IDs.",
            user_prompt=f"Summarize root cause for incident {incident_id} with top candidate {top_hyp.get('service') if top_hyp else 'none'}",
            graph=graph,
            allow_list=["upstream_suspects", "recent_changes", "service_health", "path_between"],
            schema=InvestigatorOutputSchema,
            valid_node_ids=valid_ev_ids,
            context_data=context,
            fallback_generator=fallback_gen,
            as_of=ref_ts,
        )
        llm_out = loop_out["final"]
        trace.merge(loop_out["trace"])

        # Convert tool execution findings into Evidence and re-score hypotheses
        tool_ev_added = False
        evidence_by_hyp_id: dict[str, dict[str, list[dict[str, Any]]]] = {
            h["id"]: {
                "supporting": list(h.get("supporting_evidence", [])),
                "contradicting": list(h.get("contradicting_evidence", [])),
            }
            for h in scored_hyps
        }

        for tc in loop_out.get("tool_calls", []):
            t_name = tc.get("tool")
            t_res = tc.get("result", {})
            if t_name == "service_health" and isinstance(t_res, dict):
                for m in t_res.get("metrics", []):
                    svc = m.get("service")
                    st = m.get("status", "normal")
                    m_src = m.get("source", "demo_target")
                    for h in scored_hyps:
                        if h.get("service") == svc:
                            polarity = "support" if st in ("failing", "degraded") else "contradict"
                            ev_id = f"ev_tool_{h['id']}_metric_{len(evidence_by_hyp_id[h['id']]['supporting'])+1}"
                            new_ev = {
                                "id": ev_id,
                                "hypothesis_id": h["id"],
                                "service": svc,
                                "type": "metric",
                                "kind": "observed",
                                "polarity": polarity,
                                "summary": f"Live tool verification: '{svc}' is {st} (error_rate={m.get('error_rate', 0):.2%}, latency={m.get('latency_p95_ms', 0)}ms).",
                                "source_ref": m.get("snapshot_id", "live_tool"),
                                "observed_ts": float(m.get("ts", ref_ts)),
                                "freshness": 1.0,
                                "weight": 3.0,
                                "source": m_src,
                            }
                            if polarity == "support":
                                evidence_by_hyp_id[h["id"]]["supporting"].append(new_ev)
                            else:
                                evidence_by_hyp_id[h["id"]]["contradicting"].append(new_ev)
                            tool_ev_added = True
            elif t_name == "recent_changes" and isinstance(t_res, dict):
                svc = t_res.get("service")
                deploys = t_res.get("deployments", [])
                for h in scored_hyps:
                    if h.get("service") == svc and deploys:
                        dep = deploys[0]
                        dep_src = dep.get("source", "synthetic")
                        ev_id = f"ev_tool_{h['id']}_dep_{len(evidence_by_hyp_id[h['id']]['supporting'])+1}"
                        new_ev = {
                            "id": ev_id,
                            "hypothesis_id": h["id"],
                            "service": svc,
                            "type": "recent_deploy",
                            "kind": "observed",
                            "polarity": "support",
                            "summary": f"Live tool verified deployment {dep.get('version')} on '{svc}' ({dep.get('hours_before_ref', 0)}h ago).",
                            "source_ref": dep.get("id", "live_deploy"),
                            "observed_ts": float(dep.get("ts", ref_ts)),
                            "freshness": 1.0,
                            "weight": 2.5,
                            "source": dep_src,
                        }
                        evidence_by_hyp_id[h["id"]]["supporting"].append(new_ev)
                        tool_ev_added = True
            elif t_name == "path_between" and isinstance(t_res, dict):
                if t_res.get("path_exists"):
                    callee = t_res.get("callee")
                    for h in scored_hyps:
                        if h.get("service") == callee:
                            topo_source = t_res.get("source") or ("discovered" if t_res.get("unverified_count", 0) == 0 else "seeded")
                            ev_id = f"ev_tool_{h['id']}_path_{len(evidence_by_hyp_id[h['id']]['supporting'])+1}"
                            new_ev = {
                                "id": ev_id,
                                "hypothesis_id": h["id"],
                                "service": callee,
                                "type": "dependency_path",
                                "kind": "observed",
                                "polarity": "support",
                                "summary": f"Graph verified active dependency path from alert origin to '{callee}'.",
                                "source_ref": "path_between_tool",
                                "observed_ts": ref_ts,
                                "freshness": 1.0,
                                "weight": 1.5,
                                "source": topo_source,
                            }
                            evidence_by_hyp_id[h["id"]]["supporting"].append(new_ev)
                            tool_ev_added = True
            elif t_name == "upstream_suspects" and isinstance(t_res, dict):
                suspects = t_res.get("suspects", [])
                for s in suspects:
                    s_name = s.get("service")
                    for h in scored_hyps:
                        if h.get("service") == s_name:
                            topo_source = s.get("source") or "discovered"
                            ev_id = f"ev_tool_{h['id']}_upstream_{len(evidence_by_hyp_id[h['id']]['supporting'])+1}"
                            new_ev = {
                                "id": ev_id,
                                "hypothesis_id": h["id"],
                                "service": s_name,
                                "type": "dependency_path",
                                "kind": "observed",
                                "polarity": "support",
                                "summary": f"Topological upstream suspect '{s_name}' identified at depth {s.get('depth', 1)}.",
                                "source_ref": "upstream_suspects_tool",
                                "observed_ts": ref_ts,
                                "freshness": 1.0,
                                "weight": 1.5,
                                "source": topo_source,
                            }
                            evidence_by_hyp_id[h["id"]]["supporting"].append(new_ev)
                            tool_ev_added = True
            elif t_name == "similar_incidents" and isinstance(t_res, dict):
                matches = t_res.get("matches", [])
                for m in matches:
                    if m.get("similarity_score", 0) >= 0.4:
                        for h in scored_hyps:
                            if h.get("service") in str(m.get("affected_services", [])):
                                ev_id = f"ev_tool_{h['id']}_sim_{len(evidence_by_hyp_id[h['id']]['supporting'])+1}"
                                new_ev = {
                                    "id": ev_id,
                                    "hypothesis_id": h["id"],
                                    "service": h.get("service"),
                                    "type": "past_incident",
                                    "kind": "inferred",
                                    "polarity": "support",
                                    "summary": f"Corroborated by similar past incident {m.get('incident_id')} ({m.get('similarity_score', 0):.2f} similarity).",
                                    "source_ref": m.get("incident_id", "sim_inc"),
                                    "observed_ts": ref_ts,
                                    "freshness": 1.0,
                                    "weight": 2.0,
                                    "source": m.get("source", "seeded"),
                                }
                                evidence_by_hyp_id[h["id"]]["supporting"].append(new_ev)
                                tool_ev_added = True

        if tool_ev_added:
            from app.hypotheses.score import score_hypotheses
            scored_hyps, re_trace = score_hypotheses(scored_hyps, evidence_by_hyp_id, as_of=ref_ts)
            trace.merge(re_trace)
            top_hyp = scored_hyps[0] if scored_hyps else None


        # 5. Record Observation on blackboard
        obs = record_agent_observation(
            graph=graph,
            agent_run_id=agent_run["id"],
            incident_id=incident_id,
            service=top_hyp["service"] if top_hyp else alerting_service,
            text=llm_out.summary,
            kind="inferred",
            confidence_basis=(
                f"Evidence score: {llm_out.evidence_score:.2f}, margin: {llm_out.margin:.2f}, "
                f"supporting: {top_hyp.get('supporting_count', 0) if top_hyp else 0}, "
                f"contradicting: {top_hyp.get('contra_count', 0) if top_hyp else 0}"
            ),
            ts=ref_ts,
        )

        # 6. Mark investigate task completed
        if task_id:
            update_task_status(graph, task_id, "completed", {"top_hypothesis_id": top_hyp["id"] if top_hyp else None})

        # 7. Create 'respond' Task on blackboard for Responder
        resp_payload = {
            "top_hypothesis": top_hyp,
            "alerting_service": alerting_service,
            "investigation_summary": llm_out.summary,
            "recalled_memory": payload.get("recalled_memory", {}),
            "evidence_score": llm_out.evidence_score,
            "margin": llm_out.margin,
        }
        resp_task = create_task(
            graph=graph,
            incident_id=incident_id,
            kind="respond",
            payload=resp_payload,
            agent_run_id=agent_run["id"],
            status="pending",
        )

        # 8. Complete AgentRun
        complete_agent_run(graph=graph, run_id=agent_run["id"], status="completed", summary=llm_out.summary)

        result = {
            "agent_run_id": agent_run["id"],
            "incident_id": incident_id,
            "top_hypothesis": top_hyp,
            "hypotheses": scored_hyps,
            "is_sufficient": is_sufficient,
            "conflict": conflict_record,
            "evidence_request_task": ev_task_record,
            "respond_task_id": resp_task["id"],
            "observation_id": obs["id"],
            "summary": llm_out.summary,
        }
        return result, trace

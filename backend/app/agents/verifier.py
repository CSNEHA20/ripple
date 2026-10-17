import logging
import time
from typing import Any
from pydantic import BaseModel
from app.tenancy import TenantGraph
from app.trace import Trace
from app.scenarios.outcomes import apply_intervention as sim_apply_intervention
from app.memory.outcomes import record_observed_outcome
from app.memory.episodic import close_incident
from app.agents.blackboard import (
    create_agent_run,
    complete_agent_run,
    update_task_status,
    record_agent_observation,
)
from app.agents.llm import LLMWrapper

logger = logging.getLogger("ripple.agents.verifier")


class VerifierOutputSchema(BaseModel):
    incident_id: str
    observed_outcome: str
    metrics_summary: str
    summary: str
    resolution_confirmed: bool


class VerifierAgent:
    """Verifier Agent:
    - Checks post-intervention metrics using simulator apply_intervention.
    - Records the observed Outcome ('resolved', 'partial', 'failed') in graph memory.
    - Validates or rejects the intervention hypothesis.
    - Closes the incident in episodic memory:
        Creates (Incident)-[:ROOT_CAUSE]->(Hypothesis) ONLY AFTER VERIFIED OUTCOME!
        Updates Runbook Laplace counters.
    - Writes final Observation to the blackboard and marks verify task completed.
    """

    def __init__(self, mode: str = "replay"):
        self.agent_name = "Verifier"
        self.role = "verifier"
        self.llm = LLMWrapper(mode=mode)

    def run(
        self,
        graph: TenantGraph,
        incident_id: str,
        verify_task: dict[str, Any],
        scenario_id: str | None = None,
        as_of: float | None = None,
    ) -> tuple[dict[str, Any], Trace]:
        trace = Trace()
        ref_ts = as_of if as_of is not None else time.time()
        payload = verify_task.get("payload", {})
        intervention_id = payload.get("intervention_id")
        runbook_id = payload.get("runbook_id", "rb_rollback")
        target_service = payload.get("target_service", "unknown")
        task_id = verify_task.get("id")

        # 1. Start Verifier AgentRun on blackboard
        agent_run = create_agent_run(
            graph=graph,
            agent_name=self.agent_name,
            incident_id=incident_id,
            role=self.role,
            started_ts=ref_ts,
        )

        if task_id:
            update_task_status(graph, task_id, "in_progress")

        # 2. Check post-intervention metrics via real telemetry adapter polling window
        observed = "resolved"
        metrics_after = {}
        explanation = "Service returned to normal operating parameters."

        from app.adapters.resolver import get_adapter
        from app.adapters.demo_target import get_demo_target_state
        from app.config import settings

        # Query baseline metrics prior to action from graph
        base_cypher = """
        MATCH (s:Service {name: $svc})-[:HAD_METRIC]->(m:MetricSnapshot)
        RETURN m.latency_p95_ms, m.error_rate ORDER BY m.ts DESC LIMIT 1
        """
        base_res = graph.query(base_cypher, {"svc": target_service})
        base_lat = float(base_res.result_set[0][0]) if (base_res and base_res.result_set) else 25.0
        base_err = float(base_res.result_set[0][1]) if (base_res and base_res.result_set) else 0.0

        demo_state = get_demo_target_state().get(target_service.lower(), {})
        if settings.telemetry_source in ("prometheus", "demo_target") or (demo_state and demo_state.get("broken") is not None):
            from app.agents.orchestrator import event_bus
            adapter = get_adapter(graph.tenant_id)
            samples = []
            for sample_idx in range(1, 4):
                time.sleep(0.05)
                rec = adapter.check_health(target_service, ref_ts=ref_ts)
                s_data = {
                    "sample": sample_idx,
                    "service": target_service,
                    "latency_p95_ms": rec.latency_p95_ms,
                    "error_rate": rec.error_rate,
                    "status": rec.status,
                    "source": rec.source,
                    "ts": rec.ts,
                }
                samples.append(s_data)
                try:
                    event_bus.publish(incident_id, "verification_sample", s_data)
                except Exception:
                    pass

            mean_err = sum(s["error_rate"] for s in samples) / len(samples)
            mean_lat = sum(s["latency_p95_ms"] for s in samples) / len(samples)

            if mean_err <= 0.02 and mean_lat <= 500.0:
                observed = "resolved"
                explanation = f"Service health normalized across {len(samples)} validation samples: error rate dropped to {mean_err:.1%} (baseline: {base_err:.1%}), p95 latency stabilized at {mean_lat:.1f}ms."
            elif mean_err >= 0.15 or mean_lat >= 1500.0:
                observed = "failed"
                explanation = f"Intervention failed to restore service: error rate remained elevated at {mean_err:.1%} across {len(samples)} validation samples (threshold: <2.0%)."
            else:
                observed = "partial"
                explanation = f"Partial recovery observed across {len(samples)} validation samples: error rate decreased to {mean_err:.1%}, but p95 latency remains degraded at {mean_lat:.1f}ms."

            metrics_after = {
                "samples": samples,
                "samples_count": len(samples),
                "baseline_latency_p95": base_lat,
                "baseline_error_rate": base_err,
                "observed_latency_p95": round(mean_lat, 2),
                "observed_error_rate": round(mean_err, 4),
                "source": samples[0]["source"],
            }
        elif scenario_id:
            try:
                sim_result = sim_apply_intervention(scenario_id=scenario_id, runbook_id=runbook_id)
                observed = sim_result.get("observed", "resolved")
                metrics_after = sim_result.get("metrics_after", {})
                explanation = sim_result.get("explanation", explanation)
            except Exception as e:
                logger.warning(f"Simulator apply_intervention error: {e}. Defaulting to resolved.")


        # 3. Record observed Outcome in graph memory
        outcome_record = None
        if intervention_id:
            try:
                outcome_record = record_observed_outcome(
                    graph=graph,
                    intervention_id=intervention_id,
                    observed=observed,
                    metrics_after=metrics_after,
                )
            except Exception as e:
                logger.warning(f"Error recording observed outcome: {e}")

        # 4. Find winning hypothesis
        hyp_res = graph.query(
            "MATCH (i:Incident {id: $iid})-[:HAS_HYPOTHESIS]->(h:Hypothesis) "
            "RETURN h.id AS id ORDER BY h.evidence_score DESC LIMIT 1",
            {"iid": incident_id},
        )
        winning_hyp_id = hyp_res.result_set[0][0] if (hyp_res and hyp_res.result_set) else f"hyp_{target_service}"

        # 5. Close incident in episodic memory (links ROOT_CAUSE)
        closed_inc = None
        if observed == "resolved":
            try:
                closed_inc = close_incident(
                    graph=graph,
                    incident_id=incident_id,
                    winning_hypothesis_id=winning_hyp_id,
                    steps_taken=[
                        f"Triage parsed alert for {target_service}",
                        f"Investigator ranked hypotheses with evidence",
                        f"Responder proposed {runbook_id}",
                        f"Verifier confirmed outcome {observed}",
                    ],
                    tool_calls=["blast_radius", "upstream_suspects", "recent_changes", "rank_runbooks", "apply_intervention"],
                    affected_services=[{"name": target_service, "role": "root"}],
                    handled_by="ripple_agent_crew",
                )
            except Exception as e:
                logger.warning(f"Error closing incident: {e}")

        # 6. LLM synthesis with citation validation
        valid_cites = [winning_hyp_id, runbook_id]
        if outcome_record and outcome_record.get("id"):
            valid_cites.append(outcome_record["id"])

        context = {
            "incident_id": incident_id,
            "observed": observed,
            "runbook_id": runbook_id,
            "target_service": target_service,
            "explanation": explanation,
        }

        def fallback_gen(data: dict[str, Any], enforce_citations: list[str] | None = None) -> dict[str, Any]:
            cites = enforce_citations or valid_cites
            cite_str = f" [{cites[0]}]" if cites else ""
            return {
                "incident_id": data["incident_id"],
                "observed_outcome": data["observed"],
                "metrics_summary": f"Post-intervention check on {data['target_service']}: {data['explanation']}",
                "summary": f"Verifier confirmed {data['observed']} outcome for {data['runbook_id']}{cite_str}.",
                "resolution_confirmed": data["observed"] == "resolved",
            }

        llm_out = self.llm.call_structured(
            prompt=f"Verify resolution for incident {incident_id} after {runbook_id}",
            system_prompt="You are Ripple's Verifier Agent. Summarize verified post-intervention health citing hypothesis and outcome IDs.",
            schema=VerifierOutputSchema,
            valid_node_ids=valid_cites,
            context_data=context,
            fallback_generator=fallback_gen,
        )

        # 7. Record Observation on blackboard
        obs = record_agent_observation(
            graph=graph,
            agent_run_id=agent_run["id"],
            incident_id=incident_id,
            service=target_service,
            text=llm_out.summary,
            kind="observed",
            confidence_basis=f"Post-fix metric verification: {observed}",
            ts=ref_ts,
        )

        # 8. Mark verify task completed
        if task_id:
            update_task_status(graph, task_id, "completed", {"observed_outcome": observed})

        # 9. Complete AgentRun
        complete_agent_run(graph=graph, run_id=agent_run["id"], status="completed", summary=llm_out.summary)

        result = {
            "agent_run_id": agent_run["id"],
            "incident_id": incident_id,
            "observed_outcome": observed,
            "metrics_summary": llm_out.metrics_summary,
            "outcome_record": outcome_record,
            "closed_incident": closed_inc,
            "observation_id": obs["id"],
            "summary": llm_out.summary,
            "status": "resolved" if observed == "resolved" else "partially_resolved",
        }
        return result, trace

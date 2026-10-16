import logging
import time
from typing import Any
from pydantic import BaseModel, Field
from app.tenancy import TenantGraph
from app.trace import Trace
from app.tools.blast_radius import blast_radius
from app.tools.criticality import criticality_ranking
from app.tools.incidents import similar_incidents
from app.memory.recall import recall
from app.agents.blackboard import (
    create_agent_run,
    complete_agent_run,
    create_task,
    record_agent_observation,
)
from app.agents.llm import LLMWrapper

logger = logging.getLogger("ripple.agents.triage")


class TriageOutputSchema(BaseModel):
    alerting_service: str
    severity: str
    blast_radius_count: int
    impacted_services: list[str]
    summary: str
    suggested_focus: str


class TriageAgent:
    """Triage Agent:
    - Parses incoming alert & locates the alerting service.
    - Sizes downstream blast radius via graph traversal.
    - Ranks incident severity based on graph criticality & blast radius.
    - Recalls relevant past incidents & active semantic facts from graph memory.
    - Writes an Observation node to the incident blackboard.
    - Creates an 'investigate' Task in the graph with handoff to the Investigator.
    """

    def __init__(self, mode: str = "replay"):
        self.agent_name = "Triage"
        self.role = "triage"
        self.llm = LLMWrapper(mode=mode)

    def run(
        self,
        graph: TenantGraph,
        incident_id: str,
        alert: dict[str, Any],
        as_of: float | None = None,
    ) -> tuple[dict[str, Any], Trace]:
        trace = Trace()
        ref_ts = as_of if as_of is not None else time.time()
        service_name = alert.get("service") or alert.get("service_name", "unknown")
        alert_text = alert.get("text", "")

        # 1. Start AgentRun on blackboard
        agent_run = create_agent_run(
            graph=graph,
            agent_name=self.agent_name,
            incident_id=incident_id,
            role=self.role,
            started_ts=ref_ts,
        )

        # 2. Tool 1: blast_radius
        blast_result = blast_radius(graph, service=service_name, max_depth=4, as_of=ref_ts)
        blast_data = blast_result.data if hasattr(blast_result, "data") else blast_result
        if hasattr(blast_result, "trace"):
            trace.merge(blast_result.trace)
        affected = blast_data.get("affected_services", []) if isinstance(blast_data, dict) else (blast_data or [])
        impacted_svcs = [b["service"] for b in affected if isinstance(b, dict) and b.get("service") != service_name]
        blast_count = len(impacted_svcs)

        # 3. Tool 2: criticality_ranking
        crit_result = criticality_ranking(graph)
        crit_data = crit_result.data if hasattr(crit_result, "data") else crit_result
        if hasattr(crit_result, "trace"):
            trace.merge(crit_result.trace)
        ranked = crit_data.get("ranked_services", []) if isinstance(crit_data, dict) else (crit_data or [])
        crit_map = {c["service"]: c.get("score", c.get("criticality_score", 0.0)) for c in ranked if isinstance(c, dict)}
        service_crit = crit_map.get(service_name, 0.0)

        # 4. Determine severity
        if service_crit > 0.15 or blast_count >= 3:
            severity = "P1"
        elif blast_count >= 1:
            severity = "P2"
        else:
            severity = "P3"

        # 5. Tool 3: memory recall
        recall_res, recall_trace = recall(graph, alert_text=alert_text, services=[service_name] + impacted_svcs, as_of=ref_ts)
        trace.merge(recall_trace)

        # 6. LLM synthesis with citation validation
        context = {
            "service": service_name,
            "alert_text": alert_text,
            "severity": severity,
            "blast_count": blast_count,
            "impacted": impacted_svcs,
            "similar_incidents": [
                (inc.get("incident_id") or inc.get("id"))
                for inc in recall_res.get("similar_incidents", [])[:2]
                if (inc.get("incident_id") or inc.get("id"))
            ],
        }

        def fallback_gen(data: dict[str, Any], enforce_citations: list[str] | None = None) -> dict[str, Any]:
            svcs = ", ".join(data.get("impacted", [])[:3]) or "none directly downstream"
            sim_inc = data.get("similar_incidents", [])
            inc_note = f" (recalled {sim_inc[0]})" if sim_inc else ""
            summary = (
                f"Triage assessed alert on '{data['service']}'. Blast radius: {data['blast_count']} downstream "
                f"service(s) [{svcs}]. Assigned severity {data['severity']}{inc_note}."
            )
            return {
                "alerting_service": data["service"],
                "severity": data["severity"],
                "blast_radius_count": data["blast_count"],
                "impacted_services": data.get("impacted", []),
                "summary": summary,
                "suggested_focus": f"Investigate upstream dependencies and recent changes affecting '{data['service']}'.",
            }

        valid_cites = [f"inc_{service_name}"] + [
            (inc.get("incident_id") or inc.get("id"))
            for inc in recall_res.get("similar_incidents", [])
            if (inc.get("incident_id") or inc.get("id"))
        ]
        llm_out = self.llm.call_structured(
            prompt=f"Triage incident {incident_id} for alert on {service_name}: {alert_text}",
            system_prompt="You are Ripple's Triage Agent. Analyze alert and blast radius.",
            schema=TriageOutputSchema,
            valid_node_ids=valid_cites,
            context_data=context,
            fallback_generator=fallback_gen,
        )

        # 7. Record Observation on blackboard
        obs = record_agent_observation(
            graph=graph,
            agent_run_id=agent_run["id"],
            incident_id=incident_id,
            service=service_name,
            text=llm_out.summary,
            kind="observed",
            confidence_basis=f"Blast radius traversal ({blast_count} hops) and criticality score {service_crit:.2f}",
            ts=ref_ts,
        )

        # 8. Create 'investigate' Task on blackboard for Investigator
        task_payload = {
            "alerting_service": service_name,
            "alert_text": alert_text,
            "severity": severity,
            "blast_radius": blast_data,
            "impacted_services": impacted_svcs,
            "recalled_memory": {
                "similar_incidents": recall_res.get("similar_incidents", []),
                "recommended_runbook": recall_res.get("recommended_runbook"),
            },
            "observation_id": obs["id"],
        }
        task = create_task(
            graph=graph,
            incident_id=incident_id,
            kind="investigate",
            payload=task_payload,
            agent_run_id=agent_run["id"],
            status="pending",
        )

        # 9. Complete AgentRun
        complete_agent_run(graph=graph, run_id=agent_run["id"], status="completed", summary=llm_out.summary)

        result = {
            "agent_run_id": agent_run["id"],
            "incident_id": incident_id,
            "severity": severity,
            "alerting_service": service_name,
            "blast_radius_count": blast_count,
            "impacted_services": impacted_svcs,
            "task_id": task["id"],
            "observation_id": obs["id"],
            "summary": llm_out.summary,
            "recalled_memory": recall_res,
        }
        return result, trace

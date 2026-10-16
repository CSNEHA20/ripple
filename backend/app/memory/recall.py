import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.tools.incidents import similar_incidents
from app.memory.procedural import rank_runbooks
from app.memory.applicability import check_applicability
from app.memory.semantic import get_known_facts


def recall(
    graph: TenantGraph,
    alert_text: str,
    services: list[str],
    as_of: float | None = None,
    k: int = 5,
) -> tuple[dict[str, Any], Trace]:
    """Ripple Unified Memory Recall API.
    Synthesizes episodic, semantic, procedural, and outcome memory:
      1. Recalls similar past incidents (with semantic embeddings, outcomes, and recorded failed fixes).
      2. Ranks operational runbooks by Laplace-smoothed historical success rate.
      3. Performs the applicability check on candidates: verifies dependency assumptions in the active graph.
      4. Identifies the recommended runbook and rejects broken or previously failed fixes with explanations.
      5. Gathers active semantic facts with exponential decay weighting.
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()

    # 1. Episodic recall: similar past incidents
    sim_res = similar_incidents(
        graph=graph,
        alert_text=alert_text,
        services=services,
        k=k,
    )
    trace.merge(sim_res.trace)
    matched_incidents = sim_res.data.get("matches", [])

    # Compile failed fixes from recalled similar incidents
    failed_fixes_in_history: dict[str, list[str]] = {}
    for inc in matched_incidents:
        if inc.get("similarity_score", 0.0) >= 0.35:
            for f_rb in inc.get("failed_runbooks", []):
                if f_rb not in failed_fixes_in_history:
                    failed_fixes_in_history[f_rb] = []
                failed_fixes_in_history[f_rb].append(inc["incident_id"])

    # 2. Procedural recall: rank candidate runbooks
    candidate_rbs, rb_trace = rank_runbooks(
        graph=graph,
        candidate_services=services,
    )
    trace.merge(rb_trace)

    # 3. Applicability check & Outcome gating
    recommended_runbook: dict[str, Any] | None = None
    rejected_runbooks: list[dict[str, Any]] = []

    for rb in candidate_rbs:
        rb_id = rb["runbook_id"]
        app_result, app_trace = check_applicability(
            graph=graph,
            runbook_id=rb_id,
            as_of=ref_ts,
            current_conditions={"affected_services": services},
        )
        trace.merge(app_trace)

        failed_past_incs = failed_fixes_in_history.get(rb_id, [])
        is_applicable = app_result["applicable"]
        has_failed_before = len(failed_past_incs) > 0

        rb_entry = dict(rb)
        rb_entry.update({
            "applicable": is_applicable,
            "applicability_details": app_result,
            "failed_before": has_failed_before,
            "failed_in_incidents": failed_past_incs,
        })

        if not is_applicable:
            rb_entry["rejection_reason"] = f"Not applicable: {app_result['reason']}"
            rb_entry["why_not_recommended"] = app_result.get("why_not_recommended")
            rejected_runbooks.append(rb_entry)
        elif has_failed_before:
            rb_entry["rejection_reason"] = f"Fix failed in past incident(s): {', '.join(failed_past_incs)}."
            rb_entry["why_not_recommended"] = {
                "runbook_id": rb_id,
                "reason": f"Runbook '{rb_id}' previously failed during incident(s) {', '.join(failed_past_incs)}.",
            }
            rejected_runbooks.append(rb_entry)
        else:
            # Eligible runbook
            if recommended_runbook is None:
                recommended_runbook = rb_entry

    # 4. Semantic recall: active facts for services
    facts: list[dict[str, Any]] = []
    for svc in services:
        svc_facts = get_known_facts(graph=graph, service=svc, as_of=ref_ts)
        facts.extend(svc_facts)

    duration_ms = (time.time() - start_time) * 1000.0

    step = TraceStep(
        tool="recall",
        cypher="Unified memory recall across Incident (episodic), Runbook (procedural), Observation (semantic), and Outcome validation",
        params={"alert_text": alert_text, "services": services, "as_of": ref_ts},
        node_ids=[inc["incident_id"] for inc in matched_incidents] + [f["id"] for f in facts],
        edge_ids=[],
        summary=(
            f"Recalled {len(matched_incidents)} past incidents, {len(facts)} active facts. "
            f"Recommended runbook: '{recommended_runbook['runbook_id'] if recommended_runbook else 'None'}', "
            f"{len(rejected_runbooks)} runbooks rejected by applicability or past failure."
        ),
        rows_count=len(matched_incidents),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    result = {
        "alert_text": alert_text,
        "services": services,
        "as_of": ref_ts,
        "similar_incidents": matched_incidents,
        "recommended_runbook": recommended_runbook,
        "rejected_runbooks": rejected_runbooks,
        "known_facts": facts,
    }

    return result, trace

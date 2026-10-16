import time
import uuid
from typing import Any
from app.config import settings
from app.trace import Trace, TraceStep


def check_sufficiency(
    scored_hypotheses: list[dict[str, Any]],
    alerting_service: str,
    as_of: float | None = None,
) -> tuple[dict[str, Any], Trace]:
    """Evaluate whether gathered evidence is sufficient to make a sound diagnosis.
    Enforces the 'safe, grounded investigation' rules from Implementation Plan v2:

    A diagnosis is declared 'insufficient_evidence' if:
      1. The top hypothesis has fewer than 2 supporting evidence items.
      2. The evidence margin between top and second hypothesis is below threshold (e.g. < 0.5).
      3. A strong contradiction on the top candidate is unresolved (e.g. contra_total >= 2.0).

    When insufficient:
      - States plainly that evidence is insufficient.
      - Produces an 'evidence_request' Task with specific discrimination queries.
      - Enforces calibration-gated confidence policy (no raw confidence % before M13).
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()

    if not scored_hypotheses:
        result = {
            "is_sufficient": False,
            "status": "insufficient_evidence",
            "reason": "No candidate hypotheses could be derived from graph topology.",
            "top_hypothesis": None,
            "evidence_request": None,
            "confidence_policy": {
                "is_calibrated": False,
                "score_label": "evidence score",
                "display_value": "0.0",
                "confidence_percent": None,
                "basis": "No candidates found",
                "runbook_rate_label": "historical success rate (observed outcomes)",
            },
        }
        return result, trace

    top = scored_hypotheses[0]
    second = scored_hypotheses[1] if len(scored_hypotheses) > 1 else None

    insufficient_reasons: list[str] = []

    # Rule 1: Minimum supporting evidence items
    supp_count = top.get("supporting_count", 0)
    if supp_count < settings.min_supporting_evidence_count:
        insufficient_reasons.append(
            f"Top hypothesis '{top['service']}' has only {supp_count} supporting evidence item(s) "
            f"(minimum required: {settings.min_supporting_evidence_count})."
        )

    # Rule 2: Margin threshold between #1 and #2
    margin = top.get("margin", 0.0)
    if second and margin < settings.min_margin_threshold:
        insufficient_reasons.append(
            f"Evidence margin between '{top['service']}' ({top['evidence_score']}) and "
            f"'{second['service']}' ({second['evidence_score']}) is {margin:.2f}, which is below "
            f"the ambiguity threshold ({settings.min_margin_threshold:.2f})."
        )
    elif top.get("evidence_score", 0.0) <= 0.0:
        insufficient_reasons.append(
            f"Top hypothesis '{top['service']}' has a non-positive evidence score ({top['evidence_score']})."
        )

    # Rule 3: Unresolved strong contradiction
    contra_total = top.get("contra_total", 0.0)
    if contra_total >= settings.max_unresolved_contradiction and contra_total >= top.get("support_total", 0.0) * 0.7:
        insufficient_reasons.append(
            f"Top hypothesis '{top['service']}' carries unresolved strong contradictions "
            f"(contra_total={contra_total:.2f} vs support_total={top.get('support_total', 0.0):.2f})."
        )

    is_sufficient = len(insufficient_reasons) == 0

    if not is_sufficient:
        # Mark hypothesis statuses as insufficient
        for h in scored_hypotheses:
            h["status"] = "insufficient"

        # Build discriminatory evidence request Task
        competing = [h["service"] for h in scored_hypotheses[:3]]
        task_id = f"task_ev_req_{top['id']}"

        required_probes: list[str] = []
        if supp_count < settings.min_supporting_evidence_count:
            required_probes.append(f"Fetch real-time metric snapshots and error logs for '{top['service']}'.")
            required_probes.append(f"Verify deployment and commit history for '{top['service']}'.")
        if second and margin < settings.min_margin_threshold:
            required_probes.append(
                f"Compare network error rates and RPC latency between '{alerting_service}' -> '{top['service']}' "
                f"and '{alerting_service}' -> '{second['service']}'."
            )
        if contra_total > 0:
            required_probes.append(f"Investigate healthy metric snapshots or conflicting past incident outcomes on '{top['service']}'.")

        evidence_request = {
            "id": task_id,
            "kind": "evidence_request",
            "status": "open",
            "created_ts": ref_ts,
            "target_hypothesis_id": top["id"],
            "competing_services": competing,
            "required_probes": required_probes,
            "statement": (
                f"Evidence is insufficient to isolate root cause between {', '.join(competing)}. "
                f"Additional evidence requested to discriminate competing hypotheses."
            ),
        }

        verdict = {
            "is_sufficient": False,
            "status": "insufficient_evidence",
            "reason": f"Evidence is insufficient to diagnose root cause: {' '.join(insufficient_reasons)}",
            "top_hypothesis": top,
            "evidence_request": evidence_request,
            "confidence_policy": {
                "is_calibrated": False,
                "score_label": "evidence score",
                "display_value": str(top["evidence_score"]),
                "confidence_percent": None,  # Calibration-gated
                "basis": top.get("confidence_basis", ""),
                "runbook_rate_label": "historical success rate (observed outcomes)",
            },
        }
    else:
        # Mark leading vs competing
        top["status"] = "leading"
        for h in scored_hypotheses[1:]:
            h["status"] = "competing"

        verdict = {
            "is_sufficient": True,
            "status": "sufficient",
            "reason": (
                f"Sufficient evidence collected: top hypothesis '{top['service']}' is supported by "
                f"{top['supporting_count']} items with score {top['evidence_score']} and margin {top['margin']}."
            ),
            "top_hypothesis": top,
            "evidence_request": None,
            "confidence_policy": {
                "is_calibrated": False,
                "score_label": "evidence score",
                "display_value": str(top["evidence_score"]),
                "confidence_percent": None,  # Calibration-gated
                "basis": top.get("confidence_basis", ""),
                "runbook_rate_label": "historical success rate (observed outcomes)",
            },
        }

    step = TraceStep(
        tool="check_sufficiency",
        cypher="Evaluated sufficiency against min_supporting_count, min_margin_threshold, and max_unresolved_contradiction",
        params={
            "is_sufficient": is_sufficient,
            "insufficient_reasons": insufficient_reasons,
            "top_service": top["service"],
            "margin": top["margin"],
        },
        node_ids=[top["service"]],
        edge_ids=[],
        summary=(
            f"Sufficiency check PASSED for '{top['service']}' (score={top['evidence_score']}, margin={top['margin']})."
            if is_sufficient
            else f"Sufficiency check FAILED: {verdict['reason']} Created evidence_request."
        ),
        rows_count=1 if is_sufficient else len(required_probes),
        duration_ms=(time.time() - start_time) * 1000.0,
    )
    trace.add_step(step)

    return verdict, trace

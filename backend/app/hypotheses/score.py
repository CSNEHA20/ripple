import time
from typing import Any
from app.trace import Trace, TraceStep


def score_hypotheses(
    hypotheses: list[dict[str, Any]],
    evidence_by_hyp: dict[str, dict[str, list[dict[str, Any]]]],
    as_of: float | None = None,
) -> tuple[list[dict[str, Any]], Trace]:
    """Score and rank hypotheses using pre-registered weights and exponential decay half-lives.

    Mathematical formulation (from Implementation Plan v2):
      freshness(e)    = 0.5 ^ (age_hours / half_life_for_type)
      support_total   = Σ weight_by_type × freshness(e)   over SUPPORTED_BY
      contra_total    = Σ weight_by_type × freshness(e)   over CONTRADICTED_BY
      evidence_score  = support_total − contra_total
      margin          = evidence_score(top) − evidence_score(second)
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()

    scored_hypotheses: list[dict[str, Any]] = []

    for hyp in hypotheses:
        hyp_id = hyp["id"]
        ev_group = evidence_by_hyp.get(hyp_id, {"supporting": [], "contradicting": []})
        supporting = ev_group.get("supporting", [])
        contradicting = ev_group.get("contradicting", [])

        support_total = sum(float(e.get("weight", 1.0)) * float(e.get("freshness", 1.0)) for e in supporting)
        contra_total = sum(float(e.get("weight", 1.0)) * float(e.get("freshness", 1.0)) for e in contradicting)
        support_total_r = round(support_total, 2)
        contra_total_r = round(contra_total, 2)
        evidence_score = round(support_total_r - contra_total_r, 2)

        # Determine freshest evidence age in hours
        all_ev = supporting + contradicting
        if all_ev:
            freshest_ts = max(float(e.get("observed_ts", ref_ts)) for e in all_ev)
            freshest_age_hours = max(0.0, (ref_ts - freshest_ts) / 3600.0)
        else:
            freshest_age_hours = 0.0

        scored = dict(hyp)
        scored.update({
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "supporting_count": len(supporting),
            "contradicting_count": len(contradicting),
            "support_total": support_total_r,
            "contra_total": contra_total_r,
            "evidence_score": evidence_score,
            "margin": 0.0,
            "freshest_age_hours": round(freshest_age_hours, 2),
            "confidence_basis": (
                f"{len(supporting)} supporting, {len(contradicting)} contradicting, "
                f"freshest evidence {freshest_age_hours:.1f}h old"
            ),
        })
        scored_hypotheses.append(scored)

    # Rank hypotheses descending by evidence_score, then support_total, then hops
    scored_hypotheses.sort(
        key=lambda h: (
            h["evidence_score"],
            h["support_total"],
            -h.get("hops", 99),
        ),
        reverse=True,
    )

    # Compute margin between #1 and #2
    if len(scored_hypotheses) >= 2:
        top_margin = round(
            scored_hypotheses[0]["evidence_score"] - scored_hypotheses[1]["evidence_score"],
            2,
        )
    elif len(scored_hypotheses) == 1:
        top_margin = round(scored_hypotheses[0]["evidence_score"], 2)
    else:
        top_margin = 0.0

    for idx, h in enumerate(scored_hypotheses):
        if idx == 0:
            h["margin"] = top_margin
        elif idx < len(scored_hypotheses) - 1:
            h["margin"] = round(h["evidence_score"] - scored_hypotheses[idx + 1]["evidence_score"], 2)
        else:
            h["margin"] = round(h["evidence_score"], 2)

    step = TraceStep(
        tool="score_hypotheses",
        cypher="support_total = Σ(weight × freshness); contra_total = Σ(weight × freshness); evidence_score = support - contra",
        params={"hypotheses_scored": len(scored_hypotheses), "top_margin": top_margin},
        node_ids=[h["service"] for h in scored_hypotheses],
        edge_ids=[],
        summary=(
            f"Ranked {len(scored_hypotheses)} hypotheses. Leading hypothesis: '{scored_hypotheses[0]['service']}' "
            f"(evidence_score={scored_hypotheses[0]['evidence_score']}, margin={top_margin})."
            if scored_hypotheses
            else "No hypotheses to score."
        ),
        rows_count=len(scored_hypotheses),
        duration_ms=(time.time() - start_time) * 1000.0,
    )
    trace.add_step(step)

    return scored_hypotheses, trace

import json
import logging
import time
from typing import Any
from app.tenancy import TenantGraph
from app.memory.procedural import compute_laplace_rate

logger = logging.getLogger(__name__)


def get_memory_stats(graph: TenantGraph) -> dict[str, Any]:
    """Compile comprehensive memory statistics from the graph:
    1. Counts: incidents (total, closed, open), observations (active, superseded),
       hypotheses, evidence, interventions, outcomes.
    2. Runbook procedural stats: success_count, fail_count, smoothed historical success rates.
    3. Outcome stats: validated, rejected, partial, and prediction errors.
    4. Learning curve data: progression of resolved incidents and cumulative success rate over time.
    """
    # 1. Incident counts
    inc_query = """
    MATCH (i:Incident)
    RETURN count(i) AS total,
           count(CASE WHEN i.status = 'closed' OR i.status = 'resolved' THEN 1 END) AS closed,
           count(CASE WHEN i.status <> 'closed' AND i.status <> 'resolved' THEN 1 END) AS open
    """
    inc_res = graph.query(inc_query)
    total_inc = 0
    closed_inc = 0
    open_inc = 0
    if inc_res and inc_res.result_set:
        total_inc = int(inc_res.result_set[0][0] or 0)
        closed_inc = int(inc_res.result_set[0][1] or 0)
        open_inc = int(inc_res.result_set[0][2] or 0)

    # 2. Observation counts (Semantic)
    obs_query = """
    MATCH (o:Observation)
    RETURN count(o) AS total,
           count(CASE WHEN o.inactive = true THEN 1 END) AS superseded,
           count(CASE WHEN o.inactive IS NULL OR o.inactive = false THEN 1 END) AS active
    """
    obs_res = graph.query(obs_query)
    total_obs = 0
    superseded_obs = 0
    active_obs = 0
    if obs_res and obs_res.result_set:
        total_obs = int(obs_res.result_set[0][0] or 0)
        superseded_obs = int(obs_res.result_set[0][1] or 0)
        active_obs = int(obs_res.result_set[0][2] or 0)

    # 3. Hypotheses and Evidence counts
    hyp_query = "MATCH (h:Hypothesis) RETURN count(h)"
    hyp_res = graph.query(hyp_query)
    total_hyp = int(hyp_res.result_set[0][0] or 0) if hyp_res and hyp_res.result_set else 0

    evi_query = "MATCH (e:Evidence) RETURN count(e)"
    evi_res = graph.query(evi_query)
    total_evi = int(evi_res.result_set[0][0] or 0) if evi_res and evi_res.result_set else 0

    # 4. Interventions & Outcomes
    intv_query = """
    MATCH (intv:Intervention)
    OPTIONAL MATCH (intv)-[val:VALIDATED_BY]->(out:Outcome)
    RETURN count(DISTINCT intv) AS total_interventions,
           count(DISTINCT out) AS total_outcomes,
           count(CASE WHEN val.result = 'validates' OR out.observed = 'resolved' THEN 1 END) AS validated,
           count(CASE WHEN val.result = 'rejects' OR out.observed = 'failed' THEN 1 END) AS rejected,
           count(CASE WHEN val.result = 'partial' OR out.observed = 'partial' THEN 1 END) AS partial
    """
    intv_res = graph.query(intv_query)
    total_intv = 0
    total_out = 0
    val_count = 0
    rej_count = 0
    part_count = 0
    if intv_res and intv_res.result_set:
        row = intv_res.result_set[0]
        total_intv = int(row[0] or 0)
        total_out = int(row[1] or 0)
        val_count = int(row[2] or 0)
        rej_count = int(row[3] or 0)
        part_count = int(row[4] or 0)

    # Prediction error count: interventions where predicted != observed
    pred_err_query = """
    MATCH (intv:Intervention)-[:VALIDATED_BY]->(out:Outcome)
    WHERE intv.predicted_outcome <> out.observed
    RETURN count(intv) AS prediction_errors
    """
    pred_res = graph.query(pred_err_query)
    pred_errors = int(pred_res.result_set[0][0] or 0) if pred_res and pred_res.result_set else 0

    # 5. Runbooks procedural rates
    rb_query = """
    MATCH (rb:Runbook)
    RETURN rb.id AS id,
           rb.title AS title,
           rb.success_count AS s,
           rb.fail_count AS f,
           rb.historical_success_rate AS rate,
           rb.assumes AS assumes
    ORDER BY rb.id
    """
    rb_res = graph.query(rb_query)
    runbooks_list = []
    if rb_res and rb_res.result_set:
        for row in rb_res.result_set:
            rb_id, title, s, f, rate, assumes = row
            s_val = float(s or 0.0)
            f_val = float(f or 0.0)
            rate_val = float(rate) if rate is not None else compute_laplace_rate(s_val, f_val)
            assumes_parsed = []
            if assumes:
                try:
                    assumes_parsed = json.loads(assumes) if isinstance(assumes, str) else assumes
                except Exception:
                    assumes_parsed = [str(assumes)]
            runbooks_list.append({
                "id": rb_id,
                "title": title or rb_id,
                "success_count": s_val,
                "fail_count": f_val,
                "historical_success_rate": rate_val,
                "assumes": assumes_parsed,
            })

    # 6. Learning curve data (chronological closed incidents)
    curve_query = """
    MATCH (i:Incident)
    WHERE i.status = 'closed' OR i.status = 'resolved'
    OPTIONAL MATCH (i)-[:ROOT_CAUSE]->(h:Hypothesis)
    OPTIONAL MATCH (i)-[:HAS_INTERVENTION]->(intv:Intervention)
    OPTIONAL MATCH (intv)-[:VALIDATED_BY]->(out:Outcome)
    RETURN i.id AS id,
           COALESCE(i.resolved_ts, i.opened_ts, 0.0) AS ts,
           h.statement AS winning_hypothesis,
           intv.runbook_id AS runbook_id,
           out.observed AS outcome
    ORDER BY ts ASC
    """
    curve_res = graph.query(curve_query)
    learning_curve = []
    cumulative_resolved = 0
    total_processed = 0
    if curve_res and curve_res.result_set:
        for row in curve_res.result_set:
            iid, ts, win_hyp, rb_id, out_obs = row
            total_processed += 1
            if out_obs == "resolved" or not out_obs:
                cumulative_resolved += 1
            cum_rate = round(cumulative_resolved / max(1, total_processed), 4)
            learning_curve.append({
                "incident_id": iid,
                "timestamp": float(ts or 0.0),
                "winning_hypothesis": win_hyp,
                "runbook_id": rb_id,
                "outcome": out_obs or "resolved",
                "cumulative_success_rate": cum_rate,
                "incident_index": total_processed,
            })

    return {
        "tenant_id": graph.tenant_id,
        "counts": {
            "incidents": {
                "total": total_inc,
                "closed": closed_inc,
                "open": open_inc,
            },
            "observations": {
                "total": total_obs,
                "active": active_obs,
                "superseded": superseded_obs,
            },
            "hypotheses": total_hyp,
            "evidence": total_evi,
            "interventions": total_intv,
            "outcomes": {
                "total": total_out,
                "validated": val_count,
                "rejected": rej_count,
                "partial": part_count,
            },
            "prediction_errors": pred_errors,
        },
        "runbooks": runbooks_list,
        "learning_curve": learning_curve,
    }

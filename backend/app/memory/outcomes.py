import json
import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.memory.procedural import record_runbook_outcome


def propose_intervention(
    graph: TenantGraph,
    incident_id: str,
    runbook_id: str,
    description: str,
    predicted_outcome: str = "resolved",
    action_class: str = "needs_approval",
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Record a proposed operational intervention with its predicted outcome stored separately
    from the observed outcome.
    """
    ts = time.time()
    intv_id = f"intv_{incident_id}_{runbook_id}_{int(ts * 1000)}"

    cypher = """
    MERGE (intv:Intervention {id: $id})
    SET intv.incident_id = $incident_id,
        intv.runbook_id = $runbook_id,
        intv.description = $description,
        intv.predicted_outcome = $predicted_outcome,
        intv.action_class = $action_class,
        intv.status = 'proposed',
        intv.created_ts = $ts
    """
    params = {
        "id": intv_id,
        "incident_id": incident_id,
        "runbook_id": runbook_id,
        "description": description,
        "predicted_outcome": predicted_outcome.lower(),
        "action_class": action_class,
        "ts": ts,
    }
    graph.query(cypher, params)

    # Link to Runbook
    link_rb_cypher = """
    MATCH (intv:Intervention {id: $intv_id})
    MERGE (rb:Runbook {id: $rb_id})
    MERGE (intv)-[:USES]->(rb)
    """
    graph.query(link_rb_cypher, {"intv_id": intv_id, "rb_id": runbook_id})

    # Link to Hypothesis if provided
    if hypothesis_id:
        link_hyp_cypher = """
        MATCH (h:Hypothesis {id: $hyp_id}), (intv:Intervention {id: $intv_id})
        MERGE (h)-[:ADDRESSED_BY]->(intv)
        """
        graph.query(link_hyp_cypher, {"hyp_id": hypothesis_id, "intv_id": intv_id})

    return {
        "id": intv_id,
        "incident_id": incident_id,
        "runbook_id": runbook_id,
        "description": description,
        "predicted_outcome": predicted_outcome.lower(),
        "action_class": action_class,
        "status": "proposed",
        "created_ts": ts,
    }


def record_observed_outcome(
    graph: TenantGraph,
    intervention_id: str,
    observed: str,
    metrics_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record the empirical outcome of an intervention and update runbook procedural memory.
    Links: (Intervention)-[:VALIDATED_BY {result, prediction_error}]->(Outcome).
    Result values:
      - 'validates': observed matches predicted
      - 'rejects': predicted 'resolved' but observed 'failed'
      - 'partial': partial resolution
    Failed fixes become permanent first-class memories that will be recalled by future agents.
    """
    clean_obs = observed.strip().lower()
    if clean_obs not in ("resolved", "failed", "partial", "inconclusive"):
        raise ValueError(f"Invalid outcome '{observed}'. Must be 'resolved', 'failed', 'partial', or 'inconclusive'.")

    # Fetch intervention metadata
    fetch_cypher = """
    MATCH (intv:Intervention {id: $id})
    RETURN intv.id AS id, intv.runbook_id AS runbook_id,
           intv.predicted_outcome AS predicted, intv.incident_id AS incident_id
    """
    res = graph.query(fetch_cypher, {"id": intervention_id})
    if not res or not res.result_set:
        raise ValueError(f"Intervention '{intervention_id}' not found in graph.")

    _, rb_id, predicted_outcome, inc_id = res.result_set[0]
    predicted = (predicted_outcome or "resolved").lower()

    # Determine validation result and prediction error
    if clean_obs == "inconclusive":
        result = "inconclusive"
        prediction_error = False
    elif clean_obs == predicted:
        result = "validates"
        prediction_error = False
    elif predicted == "resolved" and clean_obs == "failed":
        result = "rejects"
        prediction_error = True
    elif clean_obs == "partial":
        result = "partial"
        prediction_error = (predicted != "partial")
    else:
        result = "rejects"
        prediction_error = True

    ts = time.time()
    out_id = f"out_{intervention_id}"
    metrics_json = json.dumps(metrics_after or {})

    # Create Outcome node
    out_cypher = """
    MERGE (out:Outcome {id: $id})
    SET out.intervention_id = $intervention_id,
        out.observed = $observed,
        out.metrics_after = $metrics_json,
        out.ts = $ts
    """
    graph.query(out_cypher, {
        "id": out_id,
        "intervention_id": intervention_id,
        "observed": clean_obs,
        "metrics_json": metrics_json,
        "ts": ts,
    })

    # Link Intervention -> Outcome with validation result
    link_cypher = """
    MATCH (intv:Intervention {id: $intv_id}), (out:Outcome {id: $out_id})
    SET intv.status = 'executed'
    MERGE (intv)-[r:VALIDATED_BY]->(out)
    SET r.result = $result,
        r.prediction_error = $pred_error,
        r.ts = $ts
    """
    graph.query(link_cypher, {
        "intv_id": intervention_id,
        "out_id": out_id,
        "result": result,
        "pred_error": prediction_error,
        "ts": ts,
    })

    # Update runbook procedural counters ONLY for conclusive outcomes (resolved, partial, failed)
    procedural_update = None
    if clean_obs in ("resolved", "failed", "partial"):
        procedural_update = record_runbook_outcome(graph=graph, runbook_id=rb_id, outcome=clean_obs)

    return {
        "outcome_id": out_id,
        "intervention_id": intervention_id,
        "runbook_id": rb_id,
        "predicted_outcome": predicted,
        "observed_outcome": clean_obs,
        "validation_result": result,
        "prediction_error": prediction_error,
        "metrics_after": metrics_after or {},
        "procedural_update": procedural_update,
        "ts": ts,
    }


def get_incident_interventions(
    graph: TenantGraph,
    incident_id: str,
) -> list[dict[str, Any]]:
    """Retrieve all interventions and observed outcomes for an incident."""
    cypher = """
    MATCH (intv:Intervention {incident_id: $incident_id})
    OPTIONAL MATCH (intv)-[:USES]->(rb:Runbook)
    OPTIONAL MATCH (intv)-[v:VALIDATED_BY]->(out:Outcome)
    RETURN intv.id AS id,
           intv.runbook_id AS runbook_id,
           rb.title AS runbook_title,
           intv.description AS description,
           intv.predicted_outcome AS predicted,
           intv.action_class AS action_class,
           intv.status AS status,
           intv.created_ts AS created_ts,
           out.observed AS observed,
           v.result AS validation_result,
           v.prediction_error AS prediction_error,
           out.ts AS outcome_ts
    ORDER BY intv.created_ts ASC
    """
    res = graph.query(cypher, {"incident_id": incident_id})
    interventions: list[dict[str, Any]] = []

    if res and res.result_set:
        for row in res.result_set:
            intv_id, r_id, r_title, desc, pred, a_cls, status, c_ts, obs, v_res, p_err, o_ts = row
            interventions.append({
                "intervention_id": intv_id,
                "runbook_id": r_id,
                "runbook_title": r_title or r_id,
                "description": desc or "",
                "predicted_outcome": pred,
                "action_class": a_cls or "needs_approval",
                "status": status,
                "created_ts": float(c_ts or 0.0),
                "observed_outcome": obs,
                "validation_result": v_res,
                "prediction_error": bool(p_err) if p_err is not None else None,
                "outcome_ts": float(o_ts) if o_ts else None,
            })

    return interventions

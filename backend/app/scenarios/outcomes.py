import logging
import time
from typing import Any
from app.scenarios.catalog import get_scenario, get_runbook

logger = logging.getLogger(__name__)


def compute_post_fix_metrics(
    pre_metrics: list[dict[str, Any]],
    result: str,
) -> list[dict[str, Any]]:
    """Compute realistic simulated post-fix metrics given an intervention result
    ('resolved', 'partial', 'failed').
    """
    post_metrics: list[dict[str, Any]] = []

    for m in pre_metrics:
        svc = m["service"]
        old_status = m.get("status", "normal")
        old_latency = float(m.get("latency_p95_ms", 30.0))
        old_err = float(m.get("error_rate", 0.0))

        if result == "resolved":
            post_metrics.append({
                "service": svc,
                "status": "normal",
                "latency_p95_ms": round(min(old_latency * 0.15, 35.0) + (hash(svc) % 10), 1),
                "error_rate": 0.0,
            })
        elif result == "partial":
            if old_status == "failing":
                new_status = "degraded"
                new_latency = round(old_latency * 0.55, 1)
                new_err = round(old_err * 0.45, 3)
            elif old_status == "degraded":
                new_status = "normal"
                new_latency = round(old_latency * 0.4, 1)
                new_err = 0.0
            else:
                new_status = "normal"
                new_latency = old_latency
                new_err = 0.0

            post_metrics.append({
                "service": svc,
                "status": new_status,
                "latency_p95_ms": new_latency,
                "error_rate": new_err,
            })
        else:  # "failed"
            post_metrics.append({
                "service": svc,
                "status": old_status,
                "latency_p95_ms": old_latency,
                "error_rate": old_err,
            })

    return post_metrics


def apply_intervention(
    scenario_id: str,
    runbook_id: str,
    current_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a simulated runbook intervention against a scenario.
    Returns:
      - scenario_id: ID of scenario
      - runbook_id: ID of applied runbook
      - observed: 'resolved' | 'partial' | 'failed'
      - explanation: Contextual outcome explanation
      - metrics_after: Updated simulated service metric snapshots
      - ts: Timestamp of outcome verification
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise ValueError(f"Scenario '{scenario_id}' not found in catalog")

    runbook = get_runbook(runbook_id)
    rb_title = runbook.get("title", runbook_id) if runbook else runbook_id

    # Check scripted interventions defined for the scenario
    interventions_map = scenario.get("interventions", {})
    observed_result = interventions_map.get(runbook_id, "failed")

    # If scenario specifies ground truth correct runbook and it matches, ensure resolved
    gt = scenario.get("ground_truth", {})
    correct_rb = gt.get("correct_runbook")
    if runbook_id == correct_rb and observed_result != "resolved":
        observed_result = "resolved"

    # Contextual explanations
    if observed_result == "resolved":
        explanation = (
            f"Intervention '{rb_title}' succeeded. Target service stabilized, p95 latency "
            f"and error rate returned to healthy baseline across all dependent callers."
        )
    elif observed_result == "partial":
        explanation = (
            f"Intervention '{rb_title}' provided partial relief. Replica capacity increased "
            f"or error frequency reduced, but root bottleneck remains active."
        )
    else:
        stale_rb = gt.get("stale_runbook")
        if runbook_id == stale_rb:
            explanation = (
                f"Intervention '{rb_title}' FAILED. Stale fix attempted: assumed dependency "
                f"'{gt.get('closed_edge')}' was removed by an architecture change."
            )
        else:
            explanation = (
                f"Intervention '{rb_title}' FAILED to resolve the incident. Underlying root cause "
                f"'{gt.get('root_cause_type')}' on '{gt.get('root_cause_service')}' was not addressed."
            )

    pre_metrics = current_metrics if current_metrics is not None else scenario.get("metrics", [])
    post_metrics = compute_post_fix_metrics(pre_metrics, observed_result)

    outcome_data = {
        "scenario_id": scenario_id,
        "runbook_id": runbook_id,
        "runbook_title": rb_title,
        "observed": observed_result,
        "explanation": explanation,
        "metrics_after": post_metrics,
        "ts": time.time(),
        "source": "seeded",
    }

    logger.info(
        "Applied intervention %s on scenario %s -> observed=%s",
        runbook_id,
        scenario_id,
        observed_result,
    )
    return outcome_data

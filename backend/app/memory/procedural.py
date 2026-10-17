import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep


def compute_laplace_rate(successes: float, failures: float) -> float:
    """Laplace-smoothed historical success rate:
    (successes + 1) / (successes + failures + 2).
    """
    s = max(0.0, float(successes))
    f = max(0.0, float(failures))
    return round((s + 1.0) / (s + f + 2.0), 4)


def record_runbook_outcome(
    graph: TenantGraph,
    runbook_id: str,
    outcome: str,
) -> dict[str, Any]:
    """Update a runbook's procedural memory exclusively from observed outcomes:
      - 'resolved': adds 1.0 to success_count
      - 'failed': adds 1.0 to fail_count
      - 'partial': adds 0.5 to success_count and 0.5 to fail_count
    Recomputes and stores Laplace-smoothed historical_success_rate on the Runbook node.
    """
    clean_outcome = outcome.strip().lower()
    if clean_outcome == "resolved":
        delta_success = 1.0
        delta_fail = 0.0
    elif clean_outcome == "failed":
        delta_success = 0.0
        delta_fail = 1.0
    elif clean_outcome == "partial":
        delta_success = 0.5
        delta_fail = 0.5
    else:
        raise ValueError(f"Unknown outcome '{outcome}'. Expected 'resolved', 'failed', or 'partial'.")

    # Fetch existing counters or default to 0
    fetch_cypher = """
    MATCH (rb:Runbook {id: $id})
    RETURN rb.id AS id, rb.title AS title, rb.success_count AS s, rb.fail_count AS f
    """
    res = graph.query(fetch_cypher, {"id": runbook_id})

    if not res or not res.result_set:
        title = runbook_id
        current_s = 0.0
        current_f = 0.0
    else:
        _, title, s, f = res.result_set[0]
        current_s = float(s or 0.0)
        current_f = float(f or 0.0)

    new_s = current_s + delta_success
    new_f = current_f + delta_fail
    new_rate = compute_laplace_rate(new_s, new_f)

    # Idempotent write to Runbook node
    update_cypher = """
    MERGE (rb:Runbook {id: $id})
    SET rb.title = coalesce(rb.title, $title),
        rb.success_count = $success_count,
        rb.fail_count = $fail_count,
        rb.historical_success_rate = $rate,
        rb.last_updated_ts = $ts
    RETURN rb.id, rb.success_count, rb.fail_count, rb.historical_success_rate
    """
    graph.query(update_cypher, {
        "id": runbook_id,
        "title": title,
        "success_count": new_s,
        "fail_count": new_f,
        "rate": new_rate,
        "ts": time.time(),
    })

    return {
        "runbook_id": runbook_id,
        "title": title,
        "outcome": clean_outcome,
        "success_count": new_s,
        "fail_count": new_f,
        "historical_success_rate": new_rate,
    }


def rank_runbooks(
    graph: TenantGraph,
    incident_ids: list[str] | None = None,
    candidate_services: list[str] | None = None,
) -> tuple[list[dict[str, Any]], Trace]:
    """Retrieve operational runbooks scored by procedural success rate and relevance.
    Emits a provenance trace.
    """
    start_time = time.time()
    trace = Trace()

    inc_list = list(incident_ids or [])
    if inc_list:
        cypher = """
        MATCH (rb:Runbook)
        OPTIONAL MATCH (rb)-[:ASSUMES]->(s:Service)
        OPTIONAL MATCH (inc:Incident)-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:ADDRESSED_BY]->(intv:Intervention)-[:USES]->(rb)
        WHERE inc.id IN $incident_ids
        OPTIONAL MATCH (intv)-[:VALIDATED_BY]->(out:Outcome)
        RETURN rb.id AS id,
               rb.title AS title,
               rb.description AS description,
               rb.action_class AS action_class,
               rb.assumes AS assumes,
               collect(DISTINCT s.name) AS assumed_services,
               rb.success_count AS success_count,
               rb.fail_count AS fail_count,
               rb.historical_success_rate AS rate,
               collect(DISTINCT out.observed) AS recalled_outcomes
        """
        params = {"incident_ids": inc_list}
    else:
        cypher = """
        MATCH (rb:Runbook)
        OPTIONAL MATCH (rb)-[:ASSUMES]->(s:Service)
        RETURN rb.id AS id,
               rb.title AS title,
               rb.description AS description,
               rb.action_class AS action_class,
               rb.assumes AS assumes,
               collect(DISTINCT s.name) AS assumed_services,
               rb.success_count AS success_count,
               rb.fail_count AS fail_count,
               rb.historical_success_rate AS rate,
               [] AS recalled_outcomes
        """
        params = {}

    res = graph.query(cypher, params)
    duration_ms = (time.time() - start_time) * 1000.0

    visited_nodes: set[str] = set()
    ranked_rbs: list[dict[str, Any]] = []

    target_services = set(candidate_services or [])

    if res and res.result_set:
        for row in res.result_set:
            rb_id, title, desc, action_class, assumes_pairs, assumed_svcs, s_cnt, f_cnt, rate, recalled_outcomes = row
            visited_nodes.add(rb_id)

            successes = float(s_cnt or 0.0)
            failures = float(f_cnt or 0.0)
            laplace_rate = compute_laplace_rate(successes, failures)

            assumed_svcs_set = set(assumed_svcs or [])
            if target_services and assumed_svcs_set:
                overlap = len(target_services.intersection(assumed_svcs_set)) > 0
                service_relevance = 1.0 if overlap else 0.5
            else:
                service_relevance = 1.0

            # Procedural memory boost from recalled incident outcomes
            recalled_bonus = 0.0
            recalled_set = set(recalled_outcomes or [])
            if "resolved" in recalled_set:
                recalled_bonus += 2.0  # Proven resolution in similar past incident
            if "failed" in recalled_set:
                recalled_bonus -= 3.0  # Known failed fix for similar fault

            # Composite ranking score: 75% Laplace rate + 25% target service overlap + empirical recalled outcome bonus
            composite_score = round((0.75 * laplace_rate) + (0.25 * service_relevance) + recalled_bonus, 4)

            ranked_rbs.append({
                "runbook_id": rb_id,
                "title": title or rb_id,
                "description": desc or "",
                "action_class": action_class or "needs_approval",
                "assumes": assumes_pairs or [],
                "assumed_services": list(assumed_svcs_set),
                "success_count": successes,
                "fail_count": failures,
                "historical_success_rate": laplace_rate,
                "ranking_score": composite_score,
                "recalled_outcomes": list(recalled_set),
            })

    ranked_rbs.sort(key=lambda x: (x["ranking_score"], x["historical_success_rate"]), reverse=True)


    summary = (
        f"Ranked {len(ranked_rbs)} runbooks by observed procedural success rate. "
        f"Leading fix: '{ranked_rbs[0]['runbook_id']}' (rate={ranked_rbs[0]['historical_success_rate']:.1%})."
        if ranked_rbs
        else "No runbooks registered in graph."
    )

    step = TraceStep(
        tool="rank_runbooks",
        cypher=cypher.strip(),
        params={"incident_ids": incident_ids or [], "candidate_services": candidate_services or []},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=[],
        summary=summary,
        rows_count=len(ranked_rbs),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    return ranked_rbs, trace

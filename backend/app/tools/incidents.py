import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult
from app.ingest.embed import embed_text, cosine_similarity
from app.tools.blast_radius import blast_radius


def service_health(
    graph: TenantGraph,
    services: list[str],
    ts: float | None = None,
) -> ToolResult:
    """Retrieve the latest metric snapshot health for a list of services.
    Categorizes services into failing, degraded, and normal health states.
    Normal metrics provide authentic contradicting evidence against false hypotheses.

    Graph technique:
      HAD_METRIC lookup with timestamp filter.
    """
    start_time = time.time()
    trace = Trace()

    ref_ts = float(ts) if ts is not None else time.time()

    cypher = """
    MATCH (s:Service)-[:HAD_METRIC]->(m:MetricSnapshot)
    WHERE s.name IN $services AND m.ts <= $ref_ts
    WITH s, m ORDER BY m.ts DESC
    WITH s.name AS service_name, collect(m)[0] AS latest_m
    RETURN service_name,
           latest_m.id AS snapshot_id,
           latest_m.status AS status,
           latest_m.latency_p95_ms AS latency,
           latest_m.error_rate AS error_rate,
           latest_m.ts AS snapshot_ts,
           latest_m.source AS source
    """
    params = {"services": services, "ref_ts": ref_ts}
    res = graph.query(cypher, params)
    duration_ms = (time.time() - start_time) * 1000.0

    health_records: list[dict[str, Any]] = []
    failing: list[str] = []
    degraded: list[str] = []
    healthy_contradicting: list[str] = []
    visited_nodes = set(services)
    visited_edges = set()

    if res and res.result_set:
        for row in res.result_set:
            svc, snap_id, status, latency, error_rate, snap_ts, src = row
            visited_nodes.add(snap_id)
            visited_edges.add(f"{svc}->{snap_id}")

            status_str = status or "normal"
            lat_float = float(latency or 0.0)
            err_float = float(error_rate or 0.0)

            rec = {
                "service": svc,
                "snapshot_id": snap_id,
                "status": status_str,
                "latency_p95_ms": lat_float,
                "error_rate": err_float,
                "ts": float(snap_ts or ref_ts),
                "source": src or "seeded",
            }
            health_records.append(rec)

            if status_str == "failing":
                failing.append(svc)
            elif status_str == "degraded":
                degraded.append(svc)
            else:
                healthy_contradicting.append(svc)

    summary = (
        f"Health check across {len(services)} services: {len(failing)} failing, "
        f"{len(degraded)} degraded, {len(healthy_contradicting)} healthy."
    )

    step = TraceStep(
        tool="service_health",
        cypher=cypher.strip(),
        params=params,
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=summary,
        rows_count=len(health_records),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "services_queried": services,
        "as_of": ts,
        "failing_services": failing,
        "degraded_services": degraded,
        "healthy_services": healthy_contradicting,
        "metrics": health_records,
    }

    return ToolResult(data=data, trace=trace)


def similar_incidents(
    graph: TenantGraph,
    alert_text: str,
    services: list[str] | None = None,
    k: int = 5,
) -> ToolResult:
    """Find past historical incidents matching the alert symptoms and service context.
    Uses semantic vector similarity re-ranked by service overlap.

    Graph technique:
      Vector similarity over signature_embedding re-ranked by AFFECTED service overlap.
    """
    start_time = time.time()
    trace = Trace()

    query_emb = embed_text(alert_text)

    cypher = """
    MATCH (inc:Incident)
    OPTIONAL MATCH (inc)-[:TRIGGERED_BY]->(a:Alert)
    OPTIONAL MATCH (inc)-[aff:AFFECTED]->(s:Service)
    OPTIONAL MATCH (inc)-[:ROOT_CAUSE]->(h:Hypothesis)
    OPTIONAL MATCH (h)-[:ADDRESSED_BY]->(intv:Intervention)-[v:VALIDATED_BY]->(out:Outcome)
    OPTIONAL MATCH (intv)-[:USES]->(rb:Runbook)
    RETURN inc.id AS id,
           inc.title AS title,
           inc.signature_embedding AS emb,
           inc.severity AS severity,
           inc.opened_ts AS opened_ts,
           inc.resolved_ts AS resolved_ts,
           a.text AS alert_text,
           collect(DISTINCT {service: s.name, role: aff.role}) AS affected,
           h.statement AS root_cause_statement,
           collect(DISTINCT {runbook_id: rb.id, title: rb.title, outcome: out.observed, result: v.result}) AS interventions
    """
    res = graph.query(cypher)
    duration_ms = (time.time() - start_time) * 1000.0

    target_services = set(services or [])
    matches: list[dict[str, Any]] = []
    visited_nodes = set()
    visited_edges = set()

    if res and res.result_set:
        for row in res.result_set:
            inc_id, title, raw_emb, sev, opened, resolved, a_text, aff_list, root_stmt, intv_list = row
            visited_nodes.add(inc_id)

            # Cosine similarity
            cos_sim = 0.0
            if raw_emb:
                cos_sim = cosine_similarity(query_emb, raw_emb)

            # Service overlap score
            affected_services = {item["service"] for item in (aff_list or []) if item.get("service")}
            if target_services and affected_services:
                overlap_ratio = len(target_services.intersection(affected_services)) / len(target_services)
            else:
                overlap_ratio = 0.0

            # Re-ranked composite score: 70% semantic embedding + 30% service overlap
            composite_score = (0.7 * cos_sim) + (0.3 * overlap_ratio)

            # Clean intervention history (including failed fixes!)
            resolved_runbook = None
            failed_runbooks = []
            for item in (intv_list or []):
                rb_id = item.get("runbook_id")
                if item.get("outcome") == "resolved":
                    resolved_runbook = rb_id
                elif item.get("outcome") == "failed":
                    failed_runbooks.append(rb_id)

            matches.append({
                "incident_id": inc_id,
                "title": title,
                "similarity_score": round(composite_score, 4),
                "cosine_similarity": round(cos_sim, 4),
                "service_overlap": round(overlap_ratio, 2),
                "severity": sev,
                "alert_text": a_text,
                "root_cause_statement": root_stmt,
                "affected_services": list(affected_services),
                "resolved_runbook": resolved_runbook,
                "failed_runbooks": failed_runbooks,
                "opened_ts": float(opened or 0.0),
                "resolved_ts": float(resolved or 0.0),
            })

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_matches = matches[:k]

    summary = (
        f"Similar incidents recall: top match is {top_matches[0]['incident_id']} ('{top_matches[0]['title']}') "
        f"with score {top_matches[0]['similarity_score']}."
        if top_matches
        else "No past incidents matched."
    )

    step = TraceStep(
        tool="similar_incidents",
        cypher=cypher.strip(),
        params={"alert_text": alert_text, "services": services, "k": k},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=summary,
        rows_count=len(top_matches),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "alert_text": alert_text,
        "k": k,
        "matches": top_matches,
    }

    return ToolResult(data=data, trace=trace)


def rank_runbooks(
    graph: TenantGraph,
    incident_ids: list[str] | None = None,
) -> ToolResult:
    """Rank available operational runbooks based on historical observed outcome success rate:
      success_rate = (success + 1) / (success + fail + 2)  [Laplace smoothing]

    Graph technique:
      USES and VALIDATED_BY traversal over Intervention and Outcome nodes.
    """
    start_time = time.time()
    trace = Trace()

    cypher = """
    MATCH (rb:Runbook)
    OPTIONAL MATCH (intv:Intervention)-[:USES]->(rb)
    OPTIONAL MATCH (intv)-[v:VALIDATED_BY]->(out:Outcome)
    RETURN rb.id AS id,
           rb.title AS title,
           rb.description AS description,
           rb.action_class AS action_class,
           rb.assumes AS assumes,
           rb.success_count AS base_success,
           rb.fail_count AS base_fail,
           collect(DISTINCT {
               incident_id: intv.incident_id,
               observed: out.observed,
               result: v.result
           }) AS historical_outcomes
    """
    res = graph.query(cypher)
    duration_ms = (time.time() - start_time) * 1000.0

    target_incidents = set(incident_ids or [])
    ranked_rbs: list[dict[str, Any]] = []
    visited_nodes = set()

    if res and res.result_set:
        for row in res.result_set:
            rb_id, title, desc, action_class, assumes, base_s, base_f, outcomes = row
            visited_nodes.add(rb_id)

            successes = int(base_s or 0)
            failures = int(base_f or 0)
            incident_match_bonus = 0.0

            for out in outcomes or []:
                inc = out.get("incident_id")
                obs = out.get("observed")
                if obs == "resolved":
                    successes += 1
                    if inc in target_incidents:
                        incident_match_bonus += 0.5
                elif obs == "failed":
                    failures += 1

            # Laplace smoothing: (success + 1) / (success + fail + 2)
            smoothed_rate = (successes + 1.0) / (successes + failures + 2.0)
            final_score = smoothed_rate + incident_match_bonus

            ranked_rbs.append({
                "runbook_id": rb_id,
                "title": title,
                "description": desc,
                "action_class": action_class or "needs_approval",
                "assumes": assumes or [],
                "success_count": successes,
                "fail_count": failures,
                "historical_success_rate": round(smoothed_rate, 3),
                "score": round(final_score, 3),
            })

    ranked_rbs.sort(key=lambda x: (x["score"], x["historical_success_rate"]), reverse=True)

    step = TraceStep(
        tool="rank_runbooks",
        cypher=cypher.strip(),
        params={"incident_ids": incident_ids or []},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=[],
        summary=f"Ranked {len(ranked_rbs)} runbooks by observed success rate. Top runbook: '{ranked_rbs[0]['runbook_id']}' ({ranked_rbs[0]['historical_success_rate'] * 100}%).",
        rows_count=len(ranked_rbs),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "incident_filter": incident_ids,
        "runbooks": ranked_rbs,
    }

    return ToolResult(data=data, trace=trace)


def check_applicability(
    graph: TenantGraph,
    runbook_id: str,
) -> ToolResult:
    """Verify whether a runbook's assumed dependency pairs still exist in the current graph.
    If an assumption no longer holds (closed by an ArchitectureChange), the fix is NOT recommended.
    Populates the 'Why not recommended' diagnostic explanation card.

    Graph technique:
      ASSUMES vs current DEPENDS_ON (valid_to IS NULL) and ArchitectureChange lineage.
    """
    start_time = time.time()
    trace = Trace()

    # 1. Fetch runbook and its assumptions
    rb_cypher = "MATCH (rb:Runbook {id: $id}) RETURN rb.id, rb.title, rb.assumes, rb.action_class"
    rb_res = graph.query(rb_cypher, {"id": runbook_id})

    if not rb_res or not rb_res.result_set:
        duration_ms = (time.time() - start_time) * 1000.0
        step = TraceStep(
            tool="check_applicability",
            cypher=rb_cypher,
            params={"id": runbook_id},
            node_ids=[],
            edge_ids=[],
            summary=f"Runbook '{runbook_id}' not found.",
            duration_ms=duration_ms,
        )
        trace.add_step(step)
        return ToolResult(
            data={"runbook_id": runbook_id, "applicable": False, "reason": "Runbook not found"},
            trace=trace,
        )

    _, title, assumes_list, action_class = rb_res.result_set[0]
    assumes = assumes_list or []

    visited_nodes = {runbook_id}
    visited_edges = set()
    checked_assumptions: list[dict[str, Any]] = []
    applicable = True
    rejection_reasons: list[str] = []
    why_not_recommended: dict[str, Any] | None = None

    for pair in assumes:
        if "->" not in pair:
            continue
        caller, callee = pair.split("->", 1)
        caller = caller.strip()
        callee = callee.strip()
        visited_nodes.add(caller)
        visited_nodes.add(callee)
        visited_edges.add(f"{caller}->{callee}")

        # Check if caller->callee is currently valid
        check_cypher = """
        MATCH (a:Service {name: $caller})-[r:DEPENDS_ON]->(b:Service {name: $callee})
        WHERE r.valid_to IS NULL
        RETURN count(r) AS active_count
        """
        chk_res = graph.query(check_cypher, {"caller": caller, "callee": callee})
        active_count = int(chk_res.result_set[0][0]) if chk_res and chk_res.result_set else 0

        is_valid = active_count > 0
        assumption_info = {
            "pair": pair,
            "caller": caller,
            "callee": callee,
            "active": is_valid,
        }

        if not is_valid:
            applicable = False
            # Find the architecture change that closed this edge
            ac_cypher = """
            MATCH (ac:ArchitectureChange)
            WHERE any(edge IN ac.closes_edges WHERE edge = $pair)
            RETURN ac.id AS change_id, ac.summary AS summary, ac.ts AS ts, ac.source AS source
            ORDER BY ac.ts DESC LIMIT 1
            """
            ac_res = graph.query(ac_cypher, {"pair": pair})
            if ac_res and ac_res.result_set:
                change_id, summary_text, change_ts, src = ac_res.result_set[0]
                visited_nodes.add(change_id)
                rejection_reasons.append(
                    f"Assumed dependency '{pair}' was closed by architecture change '{change_id}' ({summary_text})."
                )
                why_not_recommended = {
                    "runbook_id": runbook_id,
                    "runbook_title": title,
                    "closed_edge": pair,
                    "architecture_change_id": change_id,
                    "architecture_change_summary": summary_text,
                    "source": src or "seeded",
                    "explanation": (
                        f"This runbook assumes '{pair}', but that dependency was permanently decoupled "
                        f"in '{summary_text}' ({change_id}). Executing this fix will fail."
                    ),
                }
            else:
                rejection_reasons.append(f"Assumed dependency '{pair}' is no longer active in the current topology.")
                why_not_recommended = {
                    "runbook_id": runbook_id,
                    "runbook_title": title,
                    "closed_edge": pair,
                    "explanation": f"Assumed dependency '{pair}' is no longer valid in current graph.",
                }

        checked_assumptions.append(assumption_info)

    duration_ms = (time.time() - start_time) * 1000.0

    step_summary = (
        f"Applicability check for '{title}': PASSED (all {len(checked_assumptions)} assumptions valid)."
        if applicable
        else f"Applicability check for '{title}': FAILED ({'; '.join(rejection_reasons)})."
    )

    step = TraceStep(
        tool="check_applicability",
        cypher="MATCH (a:Service)-[r:DEPENDS_ON]->(b:Service) WHERE r.valid_to IS NULL",
        params={"runbook_id": runbook_id, "assumes": assumes},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=step_summary,
        rows_count=len(checked_assumptions),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "runbook_id": runbook_id,
        "title": title,
        "action_class": action_class,
        "applicable": applicable,
        "rejection_reasons": rejection_reasons,
        "why_not_recommended": why_not_recommended,
        "assumptions_checked": checked_assumptions,
    }

    return ToolResult(data=data, trace=trace)


def counterfactual_blast(
    graph: TenantGraph,
    observed_incident_id: str,
    hypothetical_service: str,
    as_of: float | None = None,
) -> ToolResult:
    """Compute what-if differential analysis comparing actual incident blast radius
    against what would have happened if a different service had failed instead.

    Graph technique:
      Set differential (observed AFFECTED vs hypothetical blast_radius) with temporal as_of,
      dependency paths, PageRank critical ownership, and uncertainty bounds.
    """
    from app.counterfactual.engine import compute_counterfactual

    data, trace = compute_counterfactual(
        graph=graph,
        observed_incident_id=observed_incident_id,
        hypothetical_service=hypothetical_service,
        as_of=as_of,
        compare_with_now=bool(as_of is not None),
    )

    return ToolResult(data=data, trace=trace)


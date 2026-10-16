import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep


def check_applicability(
    graph: TenantGraph,
    runbook_id: str,
    as_of: float | None = None,
    current_conditions: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Trace]:
    """Verify whether a runbook's assumed dependency pairs still hold in the active graph.
    The 'killer moment' of Ripple's outcome memory:
      - Checks every assumed pair (e.g. 'cartservice->redis-cart') against active DEPENDS_ON edges.
      - If an edge was removed by an ArchitectureChange, the fix is declared NOT recommended.
      - Returns a visible 'Why not recommended' diagnostic payload citing the exact broken edge,
        the ArchitectureChange that closed it, and its source.
      - Compares current conditions (affected services, tier) and outputs condition warnings.
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()

    visited_nodes: set[str] = {runbook_id}
    visited_edges: set[str] = set()

    # 1. Fetch Runbook details & assumed dependencies
    rb_cypher = """
    MATCH (rb:Runbook {id: $id})
    RETURN rb.id AS id, rb.title AS title, rb.assumes AS assumes,
           rb.action_class AS action_class, rb.success_count AS success_count,
           rb.fail_count AS fail_count, rb.historical_success_rate AS rate
    """
    rb_res = graph.query(rb_cypher, {"id": runbook_id})

    if not rb_res or not rb_res.result_set:
        duration_ms = (time.time() - start_time) * 1000.0
        step = TraceStep(
            tool="check_applicability",
            cypher=rb_cypher,
            params={"id": runbook_id},
            node_ids=[runbook_id],
            edge_ids=[],
            summary=f"Runbook '{runbook_id}' not found in graph.",
            duration_ms=duration_ms,
        )
        trace.add_step(step)
        return {
            "runbook_id": runbook_id,
            "title": runbook_id,
            "applicable": False,
            "action_class": "needs_approval",
            "historical_success_rate": 0.5,
            "assumed_edges": [],
            "broken_assumptions": [],
            "why_not_recommended": {
                "runbook_id": runbook_id,
                "reason": f"Runbook '{runbook_id}' is not registered in graph memory.",
            },
            "condition_warnings": [],
            "reason": f"Runbook '{runbook_id}' not found",
        }, trace

    _, title, assumes_list, action_class, s_count, f_count, hist_rate = rb_res.result_set[0]
    assumes = assumes_list or []

    broken_assumptions: list[dict[str, Any]] = []
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

        # Check if caller->callee is active as of ref_ts
        check_cypher = """
        MATCH (a:Service {name: $caller})-[r:DEPENDS_ON]->(b:Service {name: $callee})
        WHERE r.valid_from <= $ref_ts AND (r.valid_to IS NULL OR r.valid_to > $ref_ts)
        RETURN count(r) AS active_count
        """
        chk_res = graph.query(check_cypher, {"caller": caller, "callee": callee, "ref_ts": ref_ts})
        active_count = int(chk_res.result_set[0][0]) if chk_res and chk_res.result_set else 0

        is_valid = active_count > 0

        if not is_valid:
            applicable = False
            # Find the architecture change that closed this assumed edge
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
                broken_item = {
                    "edge": pair,
                    "caller": caller,
                    "callee": callee,
                    "closed_by_change_id": change_id,
                    "change_summary": summary_text,
                    "closed_ts": float(change_ts or 0.0),
                    "source": src or "seeded",
                }
                broken_assumptions.append(broken_item)
                rejection_reasons.append(
                    f"Assumed dependency '{pair}' was closed by ArchitectureChange '{change_id}' ({summary_text})."
                )
                if not why_not_recommended:
                    why_not_recommended = {
                        "runbook_id": runbook_id,
                        "runbook_title": title,
                        "broken_edge": pair,
                        "architecture_change_id": change_id,
                        "architecture_change_summary": summary_text,
                        "source": src or "seeded",
                        "reason": f"Runbook assumes '{pair}', but this dependency was removed by {change_id} ({summary_text}).",
                    }
            else:
                broken_item = {
                    "edge": pair,
                    "caller": caller,
                    "callee": callee,
                    "closed_by_change_id": "unknown",
                    "change_summary": "Dependency edge is missing from current service graph.",
                    "closed_ts": ref_ts,
                    "source": "topology",
                }
                broken_assumptions.append(broken_item)
                rejection_reasons.append(f"Assumed dependency '{pair}' does not exist in active service topology.")
                if not why_not_recommended:
                    why_not_recommended = {
                        "runbook_id": runbook_id,
                        "runbook_title": title,
                        "broken_edge": pair,
                        "architecture_change_id": None,
                        "architecture_change_summary": None,
                        "source": "topology",
                        "reason": f"Assumed dependency '{pair}' does not exist in active service topology.",
                    }

    # Condition checks (e.g. service mismatch, tier mismatch)
    condition_warnings: list[str] = []
    if current_conditions:
        curr_affected = set(current_conditions.get("affected_services", []))
        if curr_affected:
            # Check if runbook targets any of the affected services
            rb_services_cypher = """
            MATCH (rb:Runbook {id: $id})-[:ASSUMES]->(s:Service)
            RETURN collect(s.name) AS assumes_services
            """
            rb_svc_res = graph.query(rb_services_cypher, {"id": runbook_id})
            if rb_svc_res and rb_svc_res.result_set:
                assumed_svcs = set(rb_svc_res.result_set[0][0] or [])
                if assumed_svcs and not curr_affected.intersection(assumed_svcs):
                    condition_warnings.append(
                        f"Runbook '{runbook_id}' assumes services {list(assumed_svcs)}, "
                        f"which do not overlap with current affected set {list(curr_affected)}."
                    )

    duration_ms = (time.time() - start_time) * 1000.0

    summary = (
        f"Applicability check for '{runbook_id}': APPLICABLE (all {len(assumes)} assumed dependencies valid)."
        if applicable
        else f"Applicability check for '{runbook_id}': NOT APPLICABLE ({len(broken_assumptions)} broken assumptions). {'; '.join(rejection_reasons)}"
    )

    step = TraceStep(
        tool="check_applicability",
        cypher=f"Checked {len(assumes)} assumed dependency pairs against current DEPENDS_ON and ArchitectureChange nodes.",
        params={"runbook_id": runbook_id, "assumes": assumes, "as_of": ref_ts},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=summary,
        rows_count=len(broken_assumptions),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    result = {
        "runbook_id": runbook_id,
        "title": title,
        "applicable": applicable,
        "action_class": action_class or "needs_approval",
        "historical_success_rate": float(hist_rate) if hist_rate is not None else 0.5,
        "assumed_edges": assumes,
        "broken_assumptions": broken_assumptions,
        "why_not_recommended": why_not_recommended,
        "condition_warnings": condition_warnings,
        "reason": "; ".join(rejection_reasons) if not applicable else "All dependency assumptions hold in active graph.",
    }

    return result, trace

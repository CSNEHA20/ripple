import time
import json
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult
from app.tools.blast_radius import blast_radius
from app.tools.paths import path_between
from app.tools.criticality import criticality_ranking
from app.tools.people import who_knows
from app.counterfactual.uncertainty import assess_uncertainty


def resolve_as_of_timestamp(
    graph: TenantGraph,
    incident_id: str,
    as_of: str | float | None,
) -> tuple[float | None, str, dict[str, Any]]:
    """Resolve the reference timestamp for temporal evaluation.

    Supports:
    - "incident_time" (or None default): uses the incident's opened_ts
    - "now": uses None (current active graph where valid_to IS NULL)
    - float/numeric: custom epoch timestamp
    """
    inc_cypher = """
    MATCH (inc:Incident)
    WHERE inc.id = $id OR inc.scenario_id = $id OR inc.id = 'inc_' + $id
    RETURN inc.id AS id,
           inc.title AS title,
           inc.opened_ts AS opened_ts,
           inc.resolved_ts AS resolved_ts,
           inc.scenario_id AS scenario_id
    LIMIT 1
    """
    res = graph.query(inc_cypher, {"id": incident_id})
    incident_meta: dict[str, Any] = {}
    incident_opened_ts: float | None = None

    if res and res.result_set:
        row = res.result_set[0]
        incident_meta = {
            "id": row[0],
            "title": row[1] or "Incident",
            "opened_ts": float(row[2]) if row[2] is not None else None,
            "resolved_ts": float(row[3]) if row[3] is not None else None,
            "scenario_id": row[4],
        }
        incident_opened_ts = incident_meta["opened_ts"]

    # Resolve mode and numeric timestamp
    if as_of is None or as_of == "incident_time":
        if incident_opened_ts is not None:
            return incident_opened_ts, f"incident_time ({incident_opened_ts})", incident_meta
        return None, "now (current topology)", incident_meta

    if as_of == "now":
        return None, "now (current topology)", incident_meta

    try:
        ts_val = float(as_of)
        return ts_val, f"as_of ({ts_val})", incident_meta
    except (ValueError, TypeError):
        return None, "now (current topology)", incident_meta


def get_observed_affected_services(
    graph: TenantGraph,
    incident_id: str,
) -> tuple[dict[str, str], list[str], Trace]:
    """Retrieve the set of services observed as affected during the actual incident.
    Reads from (Incident)-[:AFFECTED {role}]->(Service) edges.
    """
    trace = Trace()
    start_time = time.time()

    cypher = """
    MATCH (inc:Incident)
    WHERE inc.id = $id OR inc.scenario_id = $id OR inc.id = 'inc_' + $id
    OPTIONAL MATCH (inc)-[r:AFFECTED]->(s:Service)
    RETURN inc.id AS inc_id, s.name AS service, r.role AS role
    """
    res = graph.query(cypher, {"id": incident_id})
    duration_ms = (time.time() - start_time) * 1000.0

    observed_roles: dict[str, str] = {}
    visited_nodes = {incident_id}
    visited_edges = set()

    if res and res.result_set:
        for row in res.result_set:
            actual_inc_id, svc_name, role = row
            visited_nodes.add(actual_inc_id)
            if svc_name:
                observed_roles[svc_name] = role or "impacted"
                visited_nodes.add(svc_name)
                visited_edges.add(f"{actual_inc_id}->{svc_name}")

    # Fallback: if no AFFECTED edges exist on Incident node, check triggering Alert
    if not observed_roles:
        alt_cypher = """
        MATCH (inc:Incident {id: $id})-[:TRIGGERED_BY]->(a:Alert)-[:FIRED_ON]->(s:Service)
        RETURN s.name AS service
        """
        alt_res = graph.query(alt_cypher, {"id": incident_id})
        if alt_res and alt_res.result_set:
            for row in alt_res.result_set:
                svc_name = row[0]
                if svc_name:
                    observed_roles[svc_name] = "root"
                    visited_nodes.add(svc_name)

    observed_services = sorted(list(observed_roles.keys()))

    step = TraceStep(
        tool="get_observed_affected",
        cypher=cypher.strip(),
        params={"incident_id": incident_id},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=f"Retrieved {len(observed_services)} observed affected service(s) for incident '{incident_id}'.",
        rows_count=len(observed_services),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    return observed_roles, observed_services, trace


def compute_counterfactual(
    graph: TenantGraph,
    observed_incident_id: str,
    hypothetical_service: str,
    as_of: str | float | None = "incident_time",
    compare_with_now: bool = True,
) -> tuple[dict[str, Any], Trace]:
    """Compute what-if differential analysis comparing the actual incident blast radius
    against what would have happened if a hypothetical service had failed instead.

    Algorithm:
      1. Observed set: services in incident AFFECTED edges.
      2. Hypothetical set: blast_radius(hypothetical_service) on graph as of chosen time.
      3. Diff: only_observed, only_hypothetical, both.
      4. Paths: path_between for every affected service to the hypothetical failing service.
      5. Critical owners: PageRank criticality + recency-weighted who_knows for top services.
      6. Uncertainty: inspect unverified edges & unknown dependencies via uncertainty.py.
      7. Time travel: compare incident_time vs now to show architecture changes impact.
    """
    master_trace = Trace()
    overall_start = time.time()

    # 1. Resolve temporal timestamp
    target_as_of, as_of_label, inc_meta = resolve_as_of_timestamp(
        graph=graph,
        incident_id=observed_incident_id,
        as_of=as_of,
    )

    # 2. Step 1: Observed set
    observed_roles, observed_services, obs_trace = get_observed_affected_services(
        graph=graph,
        incident_id=observed_incident_id,
    )
    master_trace.merge(obs_trace)
    observed_set = set(observed_services)

    # 3. Step 2: Hypothetical set via blast_radius
    hypo_res = blast_radius(
        graph=graph,
        service=hypothetical_service,
        max_depth=4,
        as_of=target_as_of,
    )
    master_trace.merge(hypo_res.trace)

    hypo_affected_items = hypo_res.data.get("affected_services", [])
    hypothetical_set = {item["service"] for item in hypo_affected_items}
    # Include the failing service itself (root failure, 0 hops)
    hypothetical_set.add(hypothetical_service)

    # 4. Step 3: Diff
    only_observed = sorted(list(observed_set - hypothetical_set))
    only_hypothetical = sorted(list(hypothetical_set - observed_set))
    both = sorted(list(observed_set.intersection(hypothetical_set)))
    total_union = observed_set.union(hypothetical_set)

    overlap_percentage = round(
        (len(both) / max(1, len(total_union))) * 100.0,
        1,
    )

    # 5. Step 4: Shortest paths for all hypothetical affected services
    paths: list[dict[str, Any]] = []
    for svc in sorted(list(hypothetical_set)):
        if svc == hypothetical_service:
            continue
        p_res = path_between(
            graph=graph,
            caller=svc,
            callee=hypothetical_service,
            as_of=target_as_of,
        )
        master_trace.merge(p_res.trace)
        p_data = p_res.data
        paths.append({
            "impacted_service": svc,
            "hops": p_data.get("hops", 1),
            "path_nodes": p_data.get("path_nodes", [svc, hypothetical_service]),
            "path_edges": p_data.get("path_edges", []),
            "protocols": [
                e.get("protocol") for e in p_data.get("path_edges", []) if e.get("protocol")
            ],
            "verified": p_data.get("unverified_count", 0) == 0,
        })
    paths = sorted(paths, key=lambda x: (x["hops"], x["impacted_service"]))

    # 6. Step 5: Critical owners (PageRank within affected set + who_knows)
    critical_owners: list[dict[str, Any]] = []
    crit_res = criticality_ranking(graph)
    master_trace.merge(crit_res.trace)
    all_ranked = crit_res.data.get("ranked_services", [])

    # Filter to services in the combined affected set
    affected_ranked = [
        item for item in all_ranked if item["service"] in total_union
    ]
    # If any affected service was not in PageRank list, append it
    ranked_names = {item["service"] for item in affected_ranked}
    for svc in sorted(list(total_union)):
        if svc not in ranked_names:
            affected_ranked.append({
                "service": svc,
                "rank": len(affected_ranked) + 1,
                "tier": "tier-2",
                "pagerank_score": 0.05,
            })

    # Pick top services (up to 5) for ownership mapping
    top_critical_svcs = affected_ranked[:5]
    for item in top_critical_svcs:
        svc_name = item["service"]
        who_res = who_knows(
            graph=graph,
            service=svc_name,
            k=3,
            reference_ts=target_as_of,
        )
        master_trace.merge(who_res.trace)
        who_data = who_res.data

        critical_owners.append({
            "service": svc_name,
            "tier": item.get("tier", "tier-2"),
            "criticality_rank": item.get("rank", 99),
            "pagerank_score": item.get("pagerank_score", 0.0),
            "primary_owner": who_data.get("primary_owner"),
            "experts": who_data.get("experts", []),
            "in_hypothetical": svc_name in hypothetical_set,
            "in_observed": svc_name in observed_set,
        })

    # 7. Step 6: Uncertainty analysis
    uncertainty_data, unc_trace = assess_uncertainty(
        graph=graph,
        services=sorted(list(total_union)),
        as_of=target_as_of,
    )
    master_trace.merge(unc_trace)

    # 8. Step 7: Time-Travel Analysis (incident_time vs now)
    time_travel_data: dict[str, Any] | None = None
    if compare_with_now and target_as_of is not None:
        now_res = blast_radius(
            graph=graph,
            service=hypothetical_service,
            max_depth=4,
            as_of=None,
        )
        master_trace.merge(now_res.trace)
        now_affected_set = {
            item["service"] for item in now_res.data.get("affected_services", [])
        }
        now_affected_set.add(hypothetical_service)

        added_now = sorted(list(now_affected_set - hypothetical_set))
        removed_now = sorted(list(hypothetical_set - now_affected_set))
        stable_both = sorted(list(hypothetical_set.intersection(now_affected_set)))

        # Find architecture changes between incident_time and now
        ac_cypher = """
        MATCH (ac:ArchitectureChange)
        WHERE ac.ts >= $incident_ts
        RETURN ac.id AS id,
               ac.summary AS summary,
               ac.ts AS ts,
               ac.closes_edges AS closes,
               ac.opens_edges AS opens
        ORDER BY ac.ts ASC
        """
        ac_res = graph.query(ac_cypher, {"incident_ts": float(target_as_of)})
        arch_changes: list[dict[str, Any]] = []
        if ac_res and ac_res.result_set:
            for row in ac_res.result_set:
                arch_changes.append({
                    "id": row[0],
                    "summary": row[1],
                    "ts": float(row[2]),
                    "closes_edges": json.loads(row[3]) if isinstance(row[3], str) else (row[3] or []),
                    "opens_edges": json.loads(row[4]) if isinstance(row[4], str) else (row[4] or []),
                })

        # Formulate human-readable time-travel explanation
        if removed_now or added_now:
            change_summaries = (
                "; ".join(f"{c['summary']} ({c['id']})" for c in arch_changes)
                if arch_changes
                else "topological migration"
            )
            tt_explanation = (
                f"Time-travel differential for '{hypothetical_service}': "
                f"At incident time ({as_of_label}), failure would impact {len(hypothetical_set)} services {sorted(list(hypothetical_set))}. "
                f"Under the current active topology ('now'), failure impacts {len(now_affected_set)} services {sorted(list(now_affected_set))}. "
            )
            if removed_now:
                tt_explanation += f"{len(removed_now)} service(s) ({', '.join(removed_now)}) are NO LONGER impacted now due to: {change_summaries}. "
            if added_now:
                tt_explanation += f"{len(added_now)} new service(s) ({', '.join(added_now)}) are newly exposed in current topology."
        else:

            tt_explanation = (
                f"Topology around '{hypothetical_service}' is identical between incident time and now. "
                f"Blast radius remains unchanged ({len(hypothetical_set)} services)."
            )

        time_travel_data = {
            "incident_time_as_of": target_as_of,
            "incident_time_services": sorted(list(hypothetical_set)),
            "now_services": sorted(list(now_affected_set)),
            "added_in_now": added_now,
            "removed_in_now": removed_now,
            "unchanged_services": stable_both,
            "architecture_changes": arch_changes,
            "explanation": tt_explanation,
        }

    duration_ms = (time.time() - overall_start) * 1000.0

    # Summary Trace Step
    summary_step = TraceStep(
        tool="compute_counterfactual",
        cypher="// Multi-step counterfactual what-if synthesis",
        params={
            "observed_incident_id": observed_incident_id,
            "hypothetical_service": hypothetical_service,
            "as_of": as_of_label,
        },
        node_ids=sorted(list(total_union)),
        edge_ids=master_trace.edges,
        summary=(
            f"Counterfactual simulation for hypothetical '{hypothetical_service}' failure vs "
            f"observed incident '{observed_incident_id}': "
            f"{len(only_observed)} observed only, {len(only_hypothetical)} hypothetical only, "
            f"{len(both)} overlapping ({overlap_percentage}% overlap). "
            f"{uncertainty_data.get('lower_bound_warning', '')}"
        ),
        rows_count=len(total_union),
        duration_ms=duration_ms,
    )
    master_trace.add_step(summary_step)

    data = {
        "observed_incident_id": observed_incident_id,
        "incident_title": inc_meta.get("title", "Incident"),
        "hypothetical_service": hypothetical_service,
        "as_of": as_of_label,
        "as_of_timestamp": target_as_of,
        "observed_services": sorted(list(observed_set)),
        "hypothetical_services": sorted(list(hypothetical_set)),
        "diff": {
            "only_observed": only_observed,
            "only_hypothetical": only_hypothetical,
            "both": both,
            "observed_count": len(observed_set),
            "hypothetical_count": len(hypothetical_set),
            "overlap_count": len(both),
            "overlap_percentage": overlap_percentage,
        },
        "paths": paths,
        "critical_owners": critical_owners,
        "uncertainty": uncertainty_data,
        "uncertainty_note": uncertainty_data.get("lower_bound_warning") or uncertainty_data.get("explanation", ""),
        "time_travel_comparison": time_travel_data,
    }

    return data, master_trace

import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep


def assess_uncertainty(
    graph: TenantGraph,
    services: list[str],
    as_of: float | None = None,
) -> tuple[dict[str, Any], Trace]:
    """Inspect the affected services and their connecting edges for verification status and unknown deps.

    Returns structured uncertainty metrics, lower-bound indicators, and explainable guidance:
    - has_uncertainty: bool
    - is_lower_bound: bool
    - unverified_edges: list of unverified edge details
    - unverified_edges_count: int
    - unknown_deps_services: list of services where deps_known is false
    - unknown_deps_count: int
    - lower_bound_warning: str
    - explanation: str
    """
    start_time = time.time()
    trace = Trace()

    if not services:
        return {
            "has_uncertainty": False,
            "is_lower_bound": False,
            "unverified_edges": [],
            "unverified_edges_count": 0,
            "unknown_deps_services": [],
            "unknown_deps_count": 0,
            "lower_bound_warning": "",
            "explanation": "No services provided for uncertainty assessment.",
        }, trace

    # Temporal edge filter
    if as_of is not None:
        temporal_filter = (
            "r.valid_from <= $as_of AND (r.valid_to IS NULL OR r.valid_to > $as_of)"
        )
    else:
        temporal_filter = "r.valid_to IS NULL"

    # Query 1: Unverified DEPENDS_ON edges touching the affected region
    unverified_cypher = f"""
    MATCH (caller:Service)-[r:DEPENDS_ON]->(callee:Service)
    WHERE (caller.name IN $services OR callee.name IN $services)
      AND {temporal_filter}
      AND (r.verified = false OR r.verified IS NULL)
    RETURN DISTINCT caller.name AS caller,
                    callee.name AS callee,
                    r.protocol AS protocol,
                    r.criticality AS criticality,
                    r.source AS source,
                    r.verified AS verified
    """
    params: dict[str, Any] = {"services": services}
    if as_of is not None:
        params["as_of"] = float(as_of)

    res_unv = graph.query(unverified_cypher, params)

    unverified_edges = []
    visited_nodes = set(services)
    visited_edges = set()

    if res_unv and res_unv.result_set:
        for row in res_unv.result_set:
            caller, callee, proto, crit, src, v_flag = row
            edge_str = f"{caller}->{callee}"
            visited_nodes.add(caller)
            visited_nodes.add(callee)
            visited_edges.add(edge_str)
            unverified_edges.append({
                "caller": caller,
                "callee": callee,
                "edge": edge_str,
                "protocol": proto or "unknown",
                "criticality": crit or "medium",
                "source": src or "inferred",
                "verified": False,
            })

    # Query 2: Services in the affected region with deps_known = false
    deps_cypher = """
    MATCH (s:Service)
    WHERE s.name IN $services AND (s.deps_known = false OR s.deps_known IS NULL)
    RETURN s.name AS service, s.tier AS tier, s.deps_known AS deps_known
    """
    res_deps = graph.query(deps_cypher, {"services": services})
    unknown_deps_services = []

    if res_deps and res_deps.result_set:
        for row in res_deps.result_set:
            svc_name, tier, dk = row
            visited_nodes.add(svc_name)
            unknown_deps_services.append(svc_name)

    unv_count = len(unverified_edges)
    unk_count = len(unknown_deps_services)
    has_uncertainty = (unv_count > 0 or unk_count > 0)
    is_lower_bound = has_uncertainty

    if has_uncertainty:
        parts = []
        if unv_count > 0:
            edge_list_str = ", ".join(f"'{e['edge']}'" for e in unverified_edges[:3])
            if unv_count > 3:
                edge_list_str += f" (+{unv_count - 3} more)"
            parts.append(f"{unv_count} unverified dependency edge(s) ({edge_list_str})")
        if unk_count > 0:
            svc_list_str = ", ".join(f"'{s}'" for s in unknown_deps_services[:3])
            if unk_count > 3:
                svc_list_str += f" (+{unk_count - 3} more)"
            parts.append(f"{unk_count} service(s) with incomplete dependency catalogs ({svc_list_str})")

        lower_bound_warning = (
            f"Hypothetical blast radius is a LOWER BOUND because {' and '.join(parts)} "
            f"touch the affected subgraph. The actual downstream cascade could be wider."
        )
        explanation = (
            f"Uncertainty detected in what-if analysis: {lower_bound_warning} "
            f"To increase confidence, verify Kubernetes manifest environment variables "
            f"and configure explicit service address contracts for unverified edges."
        )
    else:
        lower_bound_warning = ""
        explanation = (
            f"All {len(services)} services in the evaluated subgraph have verified dependency manifests "
            f"(deps_known=true, verified=true). The computed blast radius is an exact topological bound."
        )

    duration_ms = (time.time() - start_time) * 1000.0

    step = TraceStep(
        tool="counterfactual_uncertainty",
        cypher=unverified_cypher.strip(),
        params=params,
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=(
            f"Uncertainty assessment across {len(services)} services: "
            f"{unv_count} unverified edge(s), {unk_count} unknown-dep service(s). "
            f"{'Flagged as lower bound.' if is_lower_bound else 'Fully verified.'}"
        ),
        rows_count=unv_count + unk_count,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "has_uncertainty": has_uncertainty,
        "is_lower_bound": is_lower_bound,
        "unverified_edges": unverified_edges,
        "unverified_edges_count": unv_count,
        "unknown_deps_services": unknown_deps_services,
        "unknown_deps_count": unk_count,
        "lower_bound_warning": lower_bound_warning,
        "explanation": explanation,
    }

    return data, trace

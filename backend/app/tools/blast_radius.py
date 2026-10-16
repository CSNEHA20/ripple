import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult


def blast_radius(
    graph: TenantGraph,
    service: str,
    max_depth: int = 4,
    as_of: float | None = None,
) -> ToolResult:
    """Compute downstream services affected if the target service fails.
    Traverses reverse DEPENDS_ON edges with temporal filtering.

    Graph technique:
      Reverse variable-length traversal on DEPENDS_ON.
    """
    start_time = time.time()
    trace = Trace()

    # Temporal filter Cypher fragment
    if as_of is not None:
        temporal_filter = (
            "all(r IN relationships(p) WHERE r.valid_from <= $as_of "
            "AND (r.valid_to IS NULL OR r.valid_to > $as_of))"
        )
    else:
        temporal_filter = "all(r IN relationships(p) WHERE r.valid_to IS NULL)"

    cypher = f"""
    MATCH (failed:Service {{name: $service}})
    OPTIONAL MATCH p = (impacted:Service)-[:DEPENDS_ON*1..{max_depth}]->(failed)
    WHERE {temporal_filter}
    WITH failed, impacted, p,
         [r IN relationships(p) | r.verified] AS verified_flags,
         [r IN relationships(p) | startNode(r).name + '->' + endNode(r).name] AS edge_pairs
    RETURN failed.name AS failed_service,
           failed.tier AS failed_tier,
           impacted.name AS impacted_service,
           impacted.tier AS impacted_tier,
           length(p) AS hops,
           verified_flags,
           edge_pairs
    ORDER BY hops ASC
    """
    params = {"service": service}
    if as_of is not None:
        params["as_of"] = float(as_of)

    res = graph.query(cypher, params)
    duration_ms = (time.time() - start_time) * 1000.0

    impacted_services: dict[str, dict[str, Any]] = {}
    visited_nodes = {service}
    visited_edges = set()
    unverified_edges_count = 0

    if res and res.result_set:
        for row in res.result_set:
            failed_name, failed_tier, imp_name, imp_tier, hops, v_flags, edges = row
            if imp_name and imp_name != service:
                visited_nodes.add(imp_name)
                # Keep shortest hops if visited via multiple paths
                if imp_name not in impacted_services or hops < impacted_services[imp_name]["hops"]:
                    impacted_services[imp_name] = {
                        "service": imp_name,
                        "hops": hops,
                        "tier": imp_tier or "tier-2",
                    }
            if edges:
                for edge_str in edges:
                    visited_edges.add(edge_str)
            if v_flags:
                for v in v_flags:
                    if v is False:
                        unverified_edges_count += 1

    sorted_impacted = sorted(impacted_services.values(), key=lambda x: (x["hops"], x["service"]))

    step = TraceStep(
        tool="blast_radius",
        cypher=cypher.strip(),
        params=params,
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=f"Blast radius of '{service}': {len(sorted_impacted)} downstream services affected up to {max_depth} hops.",
        rows_count=len(res.result_set) if res else 0,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "service": service,
        "max_depth": max_depth,
        "as_of": as_of,
        "total_affected": len(sorted_impacted),
        "affected_services": sorted_impacted,
        "unverified_edges_count": unverified_edges_count,
        "uncertainty_note": (
            f"{unverified_edges_count} unverified edge(s) found in dependency path. "
            "Blast radius represents a lower bound."
            if unverified_edges_count > 0
            else "All path dependencies verified from architecture manifests."
        ),
    }

    return ToolResult(data=data, trace=trace)

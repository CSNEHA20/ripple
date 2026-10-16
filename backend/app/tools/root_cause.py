import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult


def upstream_suspects(
    graph: TenantGraph,
    service: str,
    max_depth: int = 3,
    as_of: float | None = None,
) -> ToolResult:
    """Find all upstream dependencies that could be causing an alert on the target service.
    Traverses forward DEPENDS_ON edges with temporal filtering.

    Graph technique:
      Forward variable-length traversal on DEPENDS_ON.
    """
    start_time = time.time()
    trace = Trace()

    if as_of is not None:
        temporal_filter = (
            "all(r IN relationships(p) WHERE r.valid_from <= $as_of "
            "AND (r.valid_to IS NULL OR r.valid_to > $as_of))"
        )
    else:
        temporal_filter = "all(r IN relationships(p) WHERE r.valid_to IS NULL)"

    cypher = f"""
    MATCH (alerting:Service {{name: $service}})
    OPTIONAL MATCH p = (alerting)-[:DEPENDS_ON*1..{max_depth}]->(suspect:Service)
    WHERE {temporal_filter}
    WITH alerting, suspect, p,
         [r IN relationships(p) | startNode(r).name + '->' + endNode(r).name] AS edge_pairs
    RETURN alerting.name AS alerting_service,
           suspect.name AS suspect_service,
           suspect.tier AS suspect_tier,
           suspect.deps_known AS deps_known,
           length(p) AS hops,
           edge_pairs
    ORDER BY hops ASC
    """
    params = {"service": service}
    if as_of is not None:
        params["as_of"] = float(as_of)

    res = graph.query(cypher, params)
    duration_ms = (time.time() - start_time) * 1000.0

    suspects_map: dict[str, dict[str, Any]] = {
        # Target service is always candidate cause at hop 0 (internal bug/deploy)
        service: {
            "service": service,
            "hops": 0,
            "tier": "tier-1",
            "deps_known": True,
        }
    }
    visited_nodes = {service}
    visited_edges = set()

    if res and res.result_set:
        for row in res.result_set:
            alert_name, susp_name, susp_tier, deps_known, hops, edges = row
            if susp_name:
                visited_nodes.add(susp_name)
                if susp_name not in suspects_map or hops < suspects_map[susp_name]["hops"]:
                    suspects_map[susp_name] = {
                        "service": susp_name,
                        "hops": hops,
                        "tier": susp_tier or "tier-2",
                        "deps_known": deps_known if deps_known is not None else True,
                    }
            if edges:
                for edge_str in edges:
                    visited_edges.add(edge_str)

    sorted_suspects = sorted(suspects_map.values(), key=lambda x: (x["hops"], x["service"]))

    step = TraceStep(
        tool="upstream_suspects",
        cypher=cypher.strip(),
        params=params,
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=f"Found {len(sorted_suspects)} upstream suspect services for alerting service '{service}' up to {max_depth} hops.",
        rows_count=len(res.result_set) if res else 0,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "alerting_service": service,
        "max_depth": max_depth,
        "as_of": as_of,
        "total_suspects": len(sorted_suspects),
        "suspects": sorted_suspects,
    }

    return ToolResult(data=data, trace=trace)

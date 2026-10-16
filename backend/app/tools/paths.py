import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult


def path_between(
    graph: TenantGraph,
    caller: str,
    callee: str,
    as_of: float | None = None,
) -> ToolResult:
    """Find the shortest dependency path explaining why service A depends on service B.
    
    Graph technique:
      shortestPath over temporal DEPENDS_ON edges.
    """
    start_time = time.time()
    trace = Trace()

    if caller == callee:
        step = TraceStep(
            tool="path_between",
            cypher="// Identity path",
            params={"caller": caller, "callee": callee},
            node_ids=[caller],
            edge_ids=[],
            summary=f"Path between '{caller}' and itself is 0 hops.",
            rows_count=1,
            duration_ms=0.1,
        )
        trace.add_step(step)
        return ToolResult(
            data={
                "caller": caller,
                "callee": callee,
                "path_exists": True,
                "hops": 0,
                "path_nodes": [caller],
                "path_edges": [],
                "unverified_count": 0,
            },
            trace=trace,
        )

    if as_of is not None:
        temporal_filter = (
            "all(r IN relationships(p) WHERE r.valid_from <= $as_of "
            "AND (r.valid_to IS NULL OR r.valid_to > $as_of))"
        )
    else:
        temporal_filter = "all(r IN relationships(p) WHERE r.valid_to IS NULL)"

    cypher = f"""
    MATCH (a:Service {{name: $caller}}), (b:Service {{name: $callee}})
    WITH shortestPath((a)-[:DEPENDS_ON*..8]->(b)) AS p
    WHERE p IS NOT NULL AND {temporal_filter}
    RETURN [n IN nodes(p) | n.name] AS path_nodes,
           [r IN relationships(p) | startNode(r).name + '->' + endNode(r).name] AS edge_pairs,
           [r IN relationships(p) | r.verified] AS verified_flags,
           [r IN relationships(p) | r.protocol] AS protocols,
           [r IN relationships(p) | r.criticality] AS criticalities
    """
    params = {"caller": caller, "callee": callee}
    if as_of is not None:
        params["as_of"] = float(as_of)

    try:
        res = graph.query(cypher, params)
    except Exception as e:
        # Fallback if shortestPath syntax has version quirks
        cypher_fallback = f"""
        MATCH p = (a:Service {{name: $caller}})-[:DEPENDS_ON*1..6]->(b:Service {{name: $callee}})
        WHERE {temporal_filter}
        RETURN [n IN nodes(p) | n.name] AS path_nodes,
               [r IN relationships(p) | startNode(r).name + '->' + endNode(r).name] AS edge_pairs,
               [r IN relationships(p) | r.verified] AS verified_flags,
               [r IN relationships(p) | r.protocol] AS protocols,
               [r IN relationships(p) | r.criticality] AS criticalities
        ORDER BY length(p) ASC LIMIT 1
        """
        res = graph.query(cypher_fallback, params)
        cypher = cypher_fallback

    duration_ms = (time.time() - start_time) * 1000.0

    path_exists = False
    path_nodes: list[str] = []
    path_edges: list[dict[str, Any]] = []
    edge_pairs_list: list[str] = []
    unverified_count = 0

    if res and res.result_set:
        row = res.result_set[0]
        nodes, edges, v_flags, protos, crits = row
        if nodes:
            path_exists = True
            path_nodes = list(nodes)
            edge_pairs_list = list(edges) if edges else []
            for i in range(len(edge_pairs_list)):
                pair = edge_pairs_list[i]
                c_start, c_end = pair.split("->", 1)
                v_flag = v_flags[i] if v_flags and i < len(v_flags) else True
                if v_flag is False:
                    unverified_count += 1
                path_edges.append({
                    "from": c_start,
                    "to": c_end,
                    "protocol": protos[i] if protos and i < len(protos) else "unknown",
                    "criticality": crits[i] if crits and i < len(crits) else "high",
                    "verified": v_flag,
                })

    summary = (
        f"Path from '{caller}' to '{callee}': {' -> '.join(path_nodes)} ({len(path_edges)} hops)."
        if path_exists
        else f"No active dependency path found from '{caller}' to '{callee}'."
    )

    step = TraceStep(
        tool="path_between",
        cypher=cypher.strip(),
        params=params,
        node_ids=path_nodes,
        edge_ids=edge_pairs_list,
        summary=summary,
        rows_count=len(res.result_set) if res else 0,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "caller": caller,
        "callee": callee,
        "path_exists": path_exists,
        "hops": len(path_edges) if path_exists else -1,
        "path_nodes": path_nodes,
        "path_edges": path_edges,
        "unverified_count": unverified_count,
        "as_of": as_of,
    }

    return ToolResult(data=data, trace=trace)

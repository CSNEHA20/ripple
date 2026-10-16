import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult


def recent_changes(
    graph: TenantGraph,
    service: str,
    hours: float = 24.0,
    as_of: float | None = None,
) -> ToolResult:
    """Retrieve recent deployments, architecture changes, and pull requests touching
    the target service within a defined time window.

    Graph technique:
      Time-filtered traversal over DEPLOYED_TO, CHANGED, and TOUCHES edges.
    """
    start_time = time.time()
    trace = Trace()

    ref_ts = float(as_of) if as_of is not None else time.time()
    window_sec = float(hours) * 3600.0
    start_window_ts = ref_ts - window_sec

    visited_nodes = {service}
    visited_edges = set()

    # 1. Recent Deployments
    dep_cypher = """
    MATCH (d:Deployment)-[:DEPLOYED_TO]->(s:Service {name: $service})
    WHERE d.ts <= $ref_ts AND d.ts >= $start_window_ts
    RETURN d.id AS id, d.version AS version, d.ts AS ts, d.source AS source
    ORDER BY d.ts DESC
    """
    dep_params = {
        "service": service,
        "ref_ts": ref_ts,
        "start_window_ts": start_window_ts,
    }
    dep_res = graph.query(dep_cypher, dep_params)

    deployments: list[dict[str, Any]] = []
    if dep_res and dep_res.result_set:
        for row in dep_res.result_set:
            dep_id, version, ts, src = row
            visited_nodes.add(dep_id)
            visited_edges.add(f"{dep_id}->{service}")
            deployments.append({
                "id": dep_id,
                "version": version,
                "ts": float(ts),
                "hours_before_ref": round((ref_ts - float(ts)) / 3600.0, 2),
                "source": src or "seeded",
            })

    # 2. Recent Architecture Changes
    ac_cypher = """
    MATCH (ac:ArchitectureChange)-[:CHANGED]->(s:Service {name: $service})
    WHERE ac.ts <= $ref_ts AND ac.ts >= $start_window_ts
    RETURN ac.id AS id, ac.summary AS summary, ac.ts AS ts, ac.closes_edges AS closes, ac.opens_edges AS opens, ac.source AS source
    ORDER BY ac.ts DESC
    """
    ac_res = graph.query(ac_cypher, dep_params)

    architecture_changes: list[dict[str, Any]] = []
    if ac_res and ac_res.result_set:
        for row in ac_res.result_set:
            ac_id, summary, ts, closes, opens, src = row
            visited_nodes.add(ac_id)
            visited_edges.add(f"{ac_id}->{service}")
            architecture_changes.append({
                "id": ac_id,
                "summary": summary,
                "ts": float(ts),
                "closes_edges": closes or [],
                "opens_edges": opens or [],
                "source": src or "seeded",
            })

    # 3. Recent Merged Pull Requests
    pr_cypher = """
    MATCH (pr:PullRequest)-[:TOUCHES]->(s:Service {name: $service})
    RETURN pr.number AS number, pr.title AS title, pr.merged_at AS merged_at, pr.url AS url
    ORDER BY pr.merged_at DESC LIMIT 5
    """
    pr_res = graph.query(pr_cypher, {"service": service})

    pull_requests: list[dict[str, Any]] = []
    if pr_res and pr_res.result_set:
        for row in pr_res.result_set:
            num, title, merged_at, url = row
            pr_node_id = f"pr_{num}"
            visited_nodes.add(pr_node_id)
            visited_edges.add(f"{pr_node_id}->{service}")
            pull_requests.append({
                "number": num,
                "title": title,
                "merged_at": merged_at,
                "url": url,
            })

    duration_ms = (time.time() - start_time) * 1000.0

    total_changes = len(deployments) + len(architecture_changes) + len(pull_requests)
    summary_text = (
        f"Found {len(deployments)} deployment(s), {len(architecture_changes)} architecture change(s), "
        f"and {len(pull_requests)} recent PR(s) for '{service}' in the last {hours}h."
    )

    step = TraceStep(
        tool="recent_changes",
        cypher=dep_cypher.strip(),
        params={"service": service, "hours": hours, "as_of": as_of},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=summary_text,
        rows_count=total_changes,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "service": service,
        "hours": hours,
        "as_of": as_of,
        "total_changes": total_changes,
        "deployments": deployments,
        "architecture_changes": architecture_changes,
        "pull_requests": pull_requests,
    }

    return ToolResult(data=data, trace=trace)

import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult


def who_knows(
    graph: TenantGraph,
    service: str,
    k: int = 5,
    reference_ts: float | None = None,
) -> ToolResult:
    """Identify the top subject matter experts and on-call owners for a service.
    Ranks contributors using a recency-weighted commit and PR authorship score:
      score = commits * 0.5^(days_since_last / 90)

    Graph technique:
      Weighted COMMITTED + OWNS + AUTHORED recency traversal.
    """
    start_time = time.time()
    trace = Trace()

    cypher = """
    MATCH (s:Service {name: $service})
    MATCH (p:Person)-[c:COMMITTED]->(s)
    OPTIONAL MATCH (p)-[o:OWNS]->(s)
    OPTIONAL MATCH (p)-[:AUTHORED]->(pr:PullRequest)-[:TOUCHES]->(s)
    WITH p, s, c, o, count(DISTINCT pr) AS prs_authored
    RETURN p.login AS login,
           p.name AS name,
           c.n AS commits,
           c.last_ts AS last_active,
           (o IS NOT NULL) AS is_owner,
           prs_authored
    ORDER BY c.n DESC
    """
    params = {"service": service}
    res = graph.query(cypher, params)
    duration_ms = (time.time() - start_time) * 1000.0

    ref_time = reference_ts if reference_ts is not None else time.time()

    candidates: list[dict[str, Any]] = []
    visited_nodes = {service}
    visited_edges = set()

    if res and res.result_set:
        for row in res.result_set:
            login, name, commits, last_active, is_owner, prs_authored = row
            visited_nodes.add(login)
            visited_edges.add(f"{login}->{service}")

            # Recency calculation
            last_ts = float(last_active or 0.0)
            if last_ts > 0.0 and ref_time > last_ts:
                days_since = (ref_time - last_ts) / 86400.0
            else:
                days_since = 0.0

            # Plan formula: score = commits * 0.5^(days_since / 90)
            decay_factor = 0.5 ** (days_since / 90.0)
            base_score = float(commits or 1) * decay_factor
            # Owner and PR bonus
            if is_owner:
                base_score *= 1.25

            candidates.append({
                "person": login,
                "name": name or login,
                "commits": int(commits or 0),
                "prs_authored": int(prs_authored or 0),
                "is_owner": bool(is_owner),
                "last_active": last_ts,
                "days_since_active": round(days_since, 1),
                "recency_score": round(base_score, 2),
            })

    # Sort descending by recency_score
    candidates.sort(key=lambda x: (x["recency_score"], x["commits"]), reverse=True)
    top_k = candidates[:k]

    summary = (
        f"Top expert for '{service}' is {top_k[0]['person']} (recency score {top_k[0]['recency_score']})."
        if top_k
        else f"No committers found for service '{service}'."
    )

    step = TraceStep(
        tool="who_knows",
        cypher=cypher.strip(),
        params=params,
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=summary,
        rows_count=len(res.result_set) if res else 0,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "service": service,
        "k": k,
        "total_contributors": len(candidates),
        "experts": top_k,
    }

    return ToolResult(data=data, trace=trace)

import logging
import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep

logger = logging.getLogger("ripple.brain.freshness")


def check_docs_freshness(
    graph: TenantGraph,
    service: str | None = None,
) -> tuple[list[dict[str, Any]], Trace]:
    """Inspect documentation freshness against subsequent merged pull requests.
    Identifies documentation that has fallen out of sync with active codebase changes:
    (d:Doc)-[:DESCRIBES]->(s:Service)<-[:TOUCHES]-(pr:PullRequest)
    WHERE pr.merged_at > d.last_verified_ts
    """
    start_time = time.time()
    trace = Trace()

    service_filter = "WHERE s.name = $service AND pr.merged_at > d.last_verified_ts" if service else "WHERE pr.merged_at > d.last_verified_ts"

    cypher = f"""
    MATCH (d:Doc)-[:DESCRIBES]->(s:Service)<-[:TOUCHES]-(pr:PullRequest)
    {service_filter}
    WITH d, s, count(DISTINCT pr) AS changes_since, collect(DISTINCT pr.number)[..5] AS pr_numbers
    RETURN d.id AS doc_id,
           d.title AS title,
           d.url AS url,
           d.last_verified_ts AS last_verified_ts,
           s.name AS service,
           changes_since,
           pr_numbers
    ORDER BY changes_since DESC
    """
    params = {"service": service} if service else {}
    res = graph.query(cypher, params)
    duration_ms = (time.time() - start_time) * 1000.0

    visited_nodes: list[str] = []
    stale_docs: list[dict[str, Any]] = []

    if res and res.result_set:
        for row in res.result_set:
            doc_id, title, url, last_ver, svc_name, changes_cnt, pr_nums = row
            visited_nodes.extend([doc_id, svc_name])
            stale_docs.append({
                "doc_id": doc_id,
                "title": title,
                "url": url,
                "last_verified_ts": float(last_ver or 0.0),
                "service": svc_name,
                "changes_since": int(changes_cnt or 0),
                "pr_numbers": pr_nums or [],
                "is_stale": True,
                "freshness_badge": f"stale ({changes_cnt} merged PRs since verification)",
            })

    summary = (
        f"Found {len(stale_docs)} documentation file(s) with merged changes post-verification."
        if stale_docs
        else "All documentation is fresh and verified against merged pull requests."
    )

    step = TraceStep(
        tool="check_docs_freshness",
        cypher=cypher.strip(),
        params=params,
        node_ids=visited_nodes,
        edge_ids=[],
        summary=summary,
        rows_count=len(stale_docs),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    return stale_docs, trace

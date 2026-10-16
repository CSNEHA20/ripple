import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep, ToolResult


def criticality_ranking(
    graph: TenantGraph,
    damping_factor: float = 0.85,
    max_iterations: int = 30,
) -> ToolResult:
    """Rank system services by architectural criticality using PageRank over DEPENDS_ON.
    Services with high incoming dependency fan-in (e.g. paymentservice, redis-cart,
    productcatalogservice) receive higher criticality scores because failures on them
    cascade broadly across the microservice topology.

    Graph technique:
      PageRank algorithm over temporal DEPENDS_ON edges (Cypher + power iteration).
    """
    start_time = time.time()
    trace = Trace()

    # 1. Fetch all services
    svc_cypher = "MATCH (s:Service) RETURN s.name, s.tier"
    svc_res = graph.query(svc_cypher)

    services_meta: dict[str, str] = {}
    if svc_res and svc_res.result_set:
        for row in svc_res.result_set:
            services_meta[row[0]] = row[1] or "tier-2"

    service_names = list(services_meta.keys())
    N = len(service_names)

    if N == 0:
        return ToolResult(
            data={"ranked_services": [], "total_services": 0},
            trace=trace,
        )

    # 2. Fetch all currently active DEPENDS_ON edges
    dep_cypher = """
    MATCH (caller:Service)-[r:DEPENDS_ON]->(callee:Service)
    WHERE r.valid_to IS NULL
    RETURN caller.name AS caller, callee.name AS callee, r.criticality AS criticality
    """
    dep_res = graph.query(dep_cypher)

    in_callers: dict[str, list[str]] = {s: [] for s in service_names}
    out_callees: dict[str, list[str]] = {s: [] for s in service_names}
    visited_edges: list[str] = []

    if dep_res and dep_res.result_set:
        for row in dep_res.result_set:
            caller, callee, crit = row
            visited_edges.append(f"{caller}->{callee}")
            if caller in out_callees and callee in in_callers:
                out_callees[caller].append(callee)
                in_callers[callee].append(caller)

    # 3. Power-iteration PageRank
    scores: dict[str, float] = {s: 1.0 / N for s in service_names}
    dangling_nodes = [s for s in service_names if len(out_callees[s]) == 0]

    for _ in range(max_iterations):
        dangling_sum = sum(scores[d] for d in dangling_nodes)
        new_scores: dict[str, float] = {}
        for s in service_names:
            in_sum = sum(
                scores[c] / len(out_callees[c])
                for c in in_callers[s]
                if len(out_callees[c]) > 0
            )
            new_scores[s] = (1.0 - damping_factor) / N + damping_factor * (
                in_sum + dangling_sum / N
            )
        scores = new_scores

    # Normalize scores so sum is 1.0
    total_score = sum(scores.values()) or 1.0
    normalized_scores = {s: sc / total_score for s, sc in scores.items()}

    # Sort descending
    sorted_services = sorted(
        service_names,
        key=lambda s: (normalized_scores[s], len(in_callers[s])),
        reverse=True,
    )

    ranked_list = []
    for rank, s in enumerate(sorted_services, 1):
        ranked_list.append({
            "rank": rank,
            "service": s,
            "score": round(normalized_scores[s], 4),
            "tier": services_meta.get(s, "tier-2"),
            "in_degree": len(in_callers[s]),
            "out_degree": len(out_callees[s]),
            "callers": in_callers[s],
        })

    duration_ms = (time.time() - start_time) * 1000.0

    step = TraceStep(
        tool="criticality_ranking",
        cypher=dep_cypher.strip(),
        params={"damping_factor": damping_factor, "max_iterations": max_iterations},
        node_ids=sorted_services,
        edge_ids=visited_edges,
        summary=f"PageRank over DEPENDS_ON: top critical service is '{sorted_services[0]}' (score {round(normalized_scores[sorted_services[0]], 4)}).",
        rows_count=len(dep_res.result_set) if dep_res else 0,
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "algorithm": "PageRank",
        "damping_factor": damping_factor,
        "total_services": N,
        "ranked_services": ranked_list,
    }

    return ToolResult(data=data, trace=trace)

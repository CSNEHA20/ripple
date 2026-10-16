import time
import uuid
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.tools.root_cause import upstream_suspects
from app.tools.changes import recent_changes
from app.tools.incidents import similar_incidents


def generate_candidate_hypotheses(
    graph: TenantGraph,
    alerting_service: str,
    alert_text: str = "",
    as_of: float | None = None,
    incident_id: str | None = None,
    window_hours: float = 24.0,
) -> tuple[list[dict[str, Any]], Trace]:
    """Derive candidate root-cause hypotheses strictly from graph facts.
    Ensures that the LLM/agent only reasons over candidates grounded in graph topology:
      1. Alerting service itself (internal defect or local regression)
      2. Upstream dependencies (via forward DEPENDS_ON traversal)
      3. Services with deployments inside the incident window
      4. Services modified by recent ArchitectureChange events
      5. Services identified as root cause in similar past incidents

    Every hypothesis has kind='inferred', status='open', and an ABOUT edge to its service.
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()
    inc_id = incident_id or f"inc_{int(ref_ts)}"

    candidate_map: dict[str, dict[str, Any]] = {}

    def ensure_candidate(svc: str, source_tag: str, hops: int | None = None) -> dict[str, Any]:
        if svc not in candidate_map:
            candidate_map[svc] = {
                "service": svc,
                "hops": hops if hops is not None else 99,
                "sources": set(),
            }
        candidate_map[svc]["sources"].add(source_tag)
        if hops is not None and hops < candidate_map[svc]["hops"]:
            candidate_map[svc]["hops"] = hops
        return candidate_map[svc]

    # 1. Alerting service (hop 0)
    ensure_candidate(alerting_service, "alerting_service", hops=0)

    # 2. Upstream dependencies via upstream_suspects tool
    suspects_res = upstream_suspects(graph, service=alerting_service, max_depth=4, as_of=ref_ts)
    trace.merge(suspects_res.trace)
    for susp in suspects_res.data.get("suspects", []):
        s_name = susp["service"]
        hops = susp.get("hops", 1)
        tag = "alerting_service" if hops == 0 else "upstream_dependency"
        ensure_candidate(s_name, tag, hops=hops)

    # 3. Query all recent deployments in window
    window_sec = float(window_hours) * 3600.0
    dep_cypher = """
    MATCH (d:Deployment)-[:DEPLOYED_TO]->(s:Service)
    WHERE d.ts <= $ref_ts AND d.ts >= $start_window
    RETURN s.name AS service, d.id AS dep_id, d.version AS version, d.ts AS dep_ts
    """
    dep_params = {"ref_ts": ref_ts, "start_window": ref_ts - window_sec}
    dep_res = graph.query(dep_cypher, dep_params)
    if dep_res and dep_res.result_set:
        for row in dep_res.result_set:
            svc_name, dep_id, ver, dep_ts = row
            ensure_candidate(svc_name, "recent_deployment")

    # 4. Query recent architecture changes in window
    ac_cypher = """
    MATCH (ac:ArchitectureChange)-[:CHANGED]->(s:Service)
    WHERE ac.ts <= $ref_ts AND ac.ts >= $start_window
    RETURN s.name AS service, ac.id AS ac_id, ac.summary AS summary
    """
    ac_res = graph.query(ac_cypher, dep_params)
    if ac_res and ac_res.result_set:
        for row in ac_res.result_set:
            svc_name, ac_id, summary = row
            ensure_candidate(svc_name, "architecture_change")

    # 5. Similar past incidents recall
    if alert_text:
        sim_res = similar_incidents(
            graph,
            alert_text=alert_text,
            services=[alerting_service],
            k=3,
        )
        trace.merge(sim_res.trace)
        for inc_match in sim_res.data.get("matches", []):
            if inc_match.get("similarity_score", 0.0) >= 0.4:
                for aff_svc in inc_match.get("affected_services", []):
                    ensure_candidate(aff_svc, "past_incident_affected")

    # Construct formatted hypothesis objects
    candidates: list[dict[str, Any]] = []
    # Sort candidates by hop distance, then by number of corroborating candidate sources
    sorted_candidate_svcs = sorted(
        candidate_map.values(),
        key=lambda c: (c["hops"], -len(c["sources"]), c["service"]),
    )

    for idx, c_info in enumerate(sorted_candidate_svcs):
        svc = c_info["service"]
        hops = c_info["hops"]
        sources = sorted(list(c_info["sources"]))
        hyp_id = f"hyp_{inc_id}_{svc}"

        # Deterministic human-readable statement grounded in graph topology
        if svc == alerting_service:
            statement = f"Internal defect or regression in alerting service '{svc}' ({', '.join(sources)})."
        elif hops < 99:
            statement = f"Upstream dependency failure in '{svc}' ({hops} hop(s) upstream; {', '.join(sources)})."
        else:
            statement = f"Correlated subsystem anomaly in '{svc}' ({', '.join(sources)})."

        hyp = {
            "id": hyp_id,
            "incident_id": inc_id,
            "service": svc,
            "statement": statement,
            "kind": "inferred",
            "formed_ts": ref_ts,
            "status": "open",
            "hops": hops,
            "candidate_sources": sources,
            "evidence_score": 0.0,
            "margin": 0.0,
        }
        candidates.append(hyp)

    gen_step = TraceStep(
        tool="generate_candidates",
        cypher="Graph-guided hypothesis generation from upstream dependencies, recent deployments, architecture changes, and past incidents",
        params={
            "alerting_service": alerting_service,
            "alert_text": alert_text,
            "as_of": ref_ts,
            "window_hours": window_hours,
        },
        node_ids=[c["service"] for c in candidates],
        edge_ids=[],
        summary=f"Generated {len(candidates)} candidate hypotheses grounded in graph topology for alert on '{alerting_service}'.",
        rows_count=len(candidates),
        duration_ms=(time.time() - start_time) * 1000.0,
    )
    trace.add_step(gen_step)

    return candidates, trace

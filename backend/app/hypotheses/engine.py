import json
import logging
import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.hypotheses.generate import generate_candidate_hypotheses
from app.hypotheses.evidence import gather_evidence_for_hypotheses
from app.hypotheses.score import score_hypotheses
from app.hypotheses.sufficiency import check_sufficiency

logger = logging.getLogger("ripple.hypotheses.engine")


def run_investigation(
    graph: TenantGraph,
    alerting_service: str,
    alert_text: str = "",
    as_of: float | None = None,
    incident_id: str | None = None,
    window_hours: float = 24.0,
    persist: bool = True,
) -> tuple[dict[str, Any], Trace]:
    """Execute the end-to-end M5 Hypothesis & Evidence Engine investigation pipeline:
      1. Generate candidate hypotheses from graph topology (generate.py)
      2. Gather supporting and contradicting evidence for each candidate (evidence.py)
      3. Compute decay, support, contra totals, score, and margin (score.py)
      4. Run sufficiency check & confidence policy check (sufficiency.py)
      5. Persist Hypothesis and Evidence nodes and relationships to FalkorDB (if persist=True)
      6. Return structured diagnosis object with comprehensive provenance Trace
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()
    inc_id = incident_id or f"inc_{int(ref_ts)}"

    # Step 1: Candidate Generation
    candidates, gen_trace = generate_candidate_hypotheses(
        graph=graph,
        alerting_service=alerting_service,
        alert_text=alert_text,
        as_of=ref_ts,
        incident_id=inc_id,
        window_hours=window_hours,
    )
    trace.merge(gen_trace)

    # Step 2: Evidence Gathering
    evidence_by_hyp, ev_trace = gather_evidence_for_hypotheses(
        graph=graph,
        hypotheses=candidates,
        alerting_service=alerting_service,
        alert_text=alert_text,
        as_of=ref_ts,
        incident_id=inc_id,
    )
    trace.merge(ev_trace)

    # Step 3: Scoring & Margin Ranking
    scored_hypotheses, score_trace = score_hypotheses(
        hypotheses=candidates,
        evidence_by_hyp=evidence_by_hyp,
        as_of=ref_ts,
    )
    trace.merge(score_trace)

    # Step 4: Sufficiency Check
    verdict, suff_trace = check_sufficiency(
        scored_hypotheses=scored_hypotheses,
        alerting_service=alerting_service,
        as_of=ref_ts,
    )
    trace.merge(suff_trace)

    # Step 5: Optional Graph Persistence
    if persist and scored_hypotheses:
        persist_trace = persist_hypotheses_and_evidence(
            graph=graph,
            incident_id=inc_id,
            alerting_service=alerting_service,
            scored_hypotheses=scored_hypotheses,
            verdict=verdict,
        )
        trace.merge(persist_trace)

    duration_ms = (time.time() - start_time) * 1000.0

    result = {
        "incident_id": inc_id,
        "alerting_service": alerting_service,
        "alert_text": alert_text,
        "as_of": ref_ts,
        "is_sufficient": verdict["is_sufficient"],
        "status": verdict["status"],
        "reason": verdict["reason"],
        "top_hypothesis": verdict["top_hypothesis"],
        "hypotheses": scored_hypotheses,
        "evidence_request": verdict.get("evidence_request"),
        "confidence_policy": verdict["confidence_policy"],
        "duration_ms": round(duration_ms, 2),
    }

    return result, trace


def persist_hypotheses_and_evidence(
    graph: TenantGraph,
    incident_id: str,
    alerting_service: str,
    scored_hypotheses: list[dict[str, Any]],
    verdict: dict[str, Any],
) -> Trace:
    """Persist generated Hypothesis, Evidence, and Task nodes into the FalkorDB tenant graph."""
    start_time = time.time()
    trace = Trace()
    visited_nodes: set[str] = set()
    visited_edges: set[str] = set()

    # Ensure Incident node exists
    inc_cypher = """
    MERGE (i:Incident {id: $incident_id})
    ON CREATE SET i.opened_ts = $ts, i.title = $title, i.severity = 'CRITICAL'
    """
    graph.query(inc_cypher, {
        "incident_id": incident_id,
        "ts": time.time(),
        "title": f"Incident {incident_id} on {alerting_service}",
    })
    visited_nodes.add(incident_id)

    for hyp in scored_hypotheses:
        hyp_id = hyp["id"]
        svc = hyp["service"]
        visited_nodes.add(hyp_id)
        visited_nodes.add(svc)

        # Merge Hypothesis node
        hyp_cypher = """
        MERGE (h:Hypothesis {id: $id})
        SET h.incident_id = $incident_id,
            h.statement = $statement,
            h.kind = $kind,
            h.service = $service,
            h.formed_ts = $formed_ts,
            h.status = $status,
            h.evidence_score = $evidence_score,
            h.margin = $margin
        """
        graph.query(hyp_cypher, {
            "id": hyp_id,
            "incident_id": incident_id,
            "statement": hyp["statement"],
            "kind": hyp["kind"],
            "service": svc,
            "formed_ts": hyp["formed_ts"],
            "status": hyp["status"],
            "evidence_score": float(hyp["evidence_score"]),
            "margin": float(hyp["margin"]),
        })

        # Relate Incident -> Hypothesis
        rel_inc_cypher = """
        MATCH (i:Incident {id: $incident_id}), (h:Hypothesis {id: $hyp_id})
        MERGE (i)-[:HAS_HYPOTHESIS]->(h)
        """
        graph.query(rel_inc_cypher, {"incident_id": incident_id, "hyp_id": hyp_id})
        visited_edges.add(f"{incident_id}->{hyp_id}")

        # Relate Hypothesis -> Service
        rel_svc_cypher = """
        MATCH (h:Hypothesis {id: $hyp_id}), (s:Service {name: $service})
        MERGE (h)-[:ABOUT]->(s)
        """
        graph.query(rel_svc_cypher, {"hyp_id": hyp_id, "service": svc})
        visited_edges.add(f"{hyp_id}->{svc}")

        # Persist supporting evidence
        for ev in hyp.get("supporting_evidence", []):
            ev_id = ev["id"]
            visited_nodes.add(ev_id)
            ev_cypher = """
            MERGE (e:Evidence {id: $id})
            SET e.kind = $kind,
                e.type = $type,
                e.summary = $summary,
                e.source_ref = $source_ref,
                e.observed_ts = $observed_ts,
                e.freshness = $freshness,
                e.weight = $weight
            """
            graph.query(ev_cypher, {
                "id": ev_id,
                "kind": ev["kind"],
                "type": ev["type"],
                "summary": ev["summary"],
                "source_ref": ev["source_ref"],
                "observed_ts": float(ev["observed_ts"]),
                "freshness": float(ev["freshness"]),
                "weight": float(ev["weight"]),
            })

            # (Hypothesis)-[:SUPPORTED_BY {weight}]->(Evidence)
            link_cypher = """
            MATCH (h:Hypothesis {id: $hyp_id}), (e:Evidence {id: $ev_id})
            MERGE (h)-[r:SUPPORTED_BY]->(e)
            SET r.weight = $weight
            """
            graph.query(link_cypher, {
                "hyp_id": hyp_id,
                "ev_id": ev_id,
                "weight": float(ev["weight"]),
            })
            visited_edges.add(f"{hyp_id}->{ev_id}")

        # Persist contradicting evidence
        for ev in hyp.get("contradicting_evidence", []):
            ev_id = ev["id"]
            visited_nodes.add(ev_id)
            ev_cypher = """
            MERGE (e:Evidence {id: $id})
            SET e.kind = $kind,
                e.type = $type,
                e.summary = $summary,
                e.source_ref = $source_ref,
                e.observed_ts = $observed_ts,
                e.freshness = $freshness,
                e.weight = $weight
            """
            graph.query(ev_cypher, {
                "id": ev_id,
                "kind": ev["kind"],
                "type": ev["type"],
                "summary": ev["summary"],
                "source_ref": ev["source_ref"],
                "observed_ts": float(ev["observed_ts"]),
                "freshness": float(ev["freshness"]),
                "weight": float(ev["weight"]),
            })

            # (Hypothesis)-[:CONTRADICTED_BY {weight}]->(Evidence)
            link_cypher = """
            MATCH (h:Hypothesis {id: $hyp_id}), (e:Evidence {id: $ev_id})
            MERGE (h)-[r:CONTRADICTED_BY]->(e)
            SET r.weight = $weight
            """
            graph.query(link_cypher, {
                "hyp_id": hyp_id,
                "ev_id": ev_id,
                "weight": float(ev["weight"]),
            })
            visited_edges.add(f"{hyp_id}->{ev_id}")

    # Persist evidence_request Task if generated
    ev_req = verdict.get("evidence_request")
    if ev_req:
        task_id = ev_req["id"]
        target_hyp_id = ev_req["target_hypothesis_id"]
        visited_nodes.add(task_id)

        task_cypher = """
        MERGE (t:Task {id: $id})
        SET t.kind = 'evidence_request',
            t.status = 'open',
            t.created_ts = $ts,
            t.statement = $statement,
            t.payload = $payload
        """
        graph.query(task_cypher, {
            "id": task_id,
            "ts": float(ev_req["created_ts"]),
            "statement": ev_req["statement"],
            "payload": json.dumps({
                "competing_services": ev_req["competing_services"],
                "required_probes": ev_req["required_probes"],
            }),
        })

        link_task_cypher = """
        MATCH (t:Task {id: $task_id}), (h:Hypothesis {id: $hyp_id})
        MERGE (t)-[:REQUESTS_EVIDENCE_FOR]->(h)
        """
        graph.query(link_task_cypher, {"task_id": task_id, "hyp_id": target_hyp_id})
        visited_edges.add(f"{task_id}->{target_hyp_id}")

    step = TraceStep(
        tool="persist_hypotheses",
        cypher="MERGE (h:Hypothesis); MERGE (e:Evidence); MERGE (h)-[:SUPPORTED_BY|CONTRADICTED_BY]->(e)",
        params={"incident_id": incident_id, "hypotheses_persisted": len(scored_hypotheses)},
        node_ids=sorted(list(visited_nodes)),
        edge_ids=sorted(list(visited_edges)),
        summary=f"Persisted {len(scored_hypotheses)} hypotheses and their evidence nodes to FalkorDB for incident '{incident_id}'.",
        rows_count=len(scored_hypotheses),
        duration_ms=(time.time() - start_time) * 1000.0,
    )
    trace.add_step(step)

    return trace

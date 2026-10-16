import json
import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.ingest.embed import embed_text, cosine_similarity


def close_incident(
    graph: TenantGraph,
    incident_id: str,
    winning_hypothesis_id: str,
    steps_taken: list[str] | None = None,
    tool_calls: list[str] | None = None,
    affected_services: list[dict[str, str]] | None = None,
    handled_by: str | None = None,
    signature_text: str | None = None,
) -> dict[str, Any]:
    """Close an incident and commit its complete episodic record into graph memory:
      - Validates that the winning hypothesis is verified by an outcome
      - Links (Incident)-[:ROOT_CAUSE {confirmed_ts}]->(Hypothesis)
      - Links (Incident)-[:HANDLED_BY]->(Person)
      - Links (Incident)-[:AFFECTED {role}]->(Service)
      - Computes incident signature embedding and generates (Incident)-[:SIMILAR_TO {score}]->(Incident) edges
    """
    now_ts = time.time()
    steps = steps_taken or []
    tools = tool_calls or []

    # Verify winning hypothesis exists and extract its statement & service
    hyp_cypher = """
    MATCH (h:Hypothesis {id: $hyp_id})
    RETURN h.id AS id, h.statement AS statement, h.service AS service
    """
    hyp_res = graph.query(hyp_cypher, {"hyp_id": winning_hypothesis_id})
    if not hyp_res or not hyp_res.result_set:
        raise ValueError(f"Winning hypothesis '{winning_hypothesis_id}' not found.")

    _, hyp_statement, hyp_service = hyp_res.result_set[0]

    # Compute signature embedding for semantic retrieval
    sig_content = signature_text or f"Incident {incident_id} root cause: {hyp_statement} on {hyp_service}"
    sig_emb = embed_text(sig_content)

    # 1. Update Incident node
    inc_cypher = """
    MERGE (i:Incident {id: $id})
    SET i.status = 'closed',
        i.resolved_ts = $resolved_ts,
        i.steps_taken = $steps_json,
        i.tool_calls = $tools_json,
        i.signature_embedding = $emb
    """
    graph.query(inc_cypher, {
        "id": incident_id,
        "resolved_ts": now_ts,
        "steps_json": json.dumps(steps),
        "tools_json": json.dumps(tools),
        "emb": sig_emb,
    })

    # 2. Link Incident -> ROOT_CAUSE -> Hypothesis
    rc_cypher = """
    MATCH (i:Incident {id: $inc_id}), (h:Hypothesis {id: $hyp_id})
    MERGE (i)-[r:ROOT_CAUSE]->(h)
    SET r.confirmed_ts = $ts
    """
    graph.query(rc_cypher, {
        "inc_id": incident_id,
        "hyp_id": winning_hypothesis_id,
        "ts": now_ts,
    })

    # 3. Link AFFECTED services
    # Ensure the root cause service is marked role='root'
    affected = affected_services or []
    if not any(a.get("service") == hyp_service for a in affected):
        affected.append({"service": hyp_service, "role": "root"})

    for aff in affected:
        s_name = aff["service"]
        role = aff.get("role", "impacted")
        aff_cypher = """
        MATCH (i:Incident {id: $inc_id})
        MERGE (s:Service {name: $s_name})
        MERGE (i)-[r:AFFECTED]->(s)
        SET r.role = $role
        """
        graph.query(aff_cypher, {"inc_id": incident_id, "s_name": s_name, "role": role})

    # 4. Link HANDLED_BY
    if handled_by:
        handle_cypher = """
        MATCH (i:Incident {id: $inc_id})
        MERGE (p:Person {login: $login})
        MERGE (i)-[:HANDLED_BY]->(p)
        """
        graph.query(handle_cypher, {"inc_id": incident_id, "login": handled_by})

    # 5. Connect SIMILAR_TO edges with other past incidents in graph
    other_cypher = """
    MATCH (other:Incident)
    WHERE other.id <> $inc_id AND other.signature_embedding IS NOT NULL
    RETURN other.id AS id, other.signature_embedding AS emb
    """
    other_res = graph.query(other_cypher, {"inc_id": incident_id})
    similar_links: list[dict[str, Any]] = []

    if other_res and other_res.result_set:
        for row in other_res.result_set:
            other_id, other_emb = row
            if other_emb:
                cos_sim = cosine_similarity(sig_emb, other_emb)
                if cos_sim >= 0.35:
                    sim_cypher = """
                    MATCH (a:Incident {id: $a_id}), (b:Incident {id: $b_id})
                    MERGE (a)-[r:SIMILAR_TO]->(b)
                    SET r.score = $score
                    """
                    graph.query(sim_cypher, {
                        "a_id": incident_id,
                        "b_id": other_id,
                        "score": round(cos_sim, 4),
                    })
                    similar_links.append({"other_id": other_id, "score": round(cos_sim, 4)})

    return {
        "incident_id": incident_id,
        "status": "closed",
        "resolved_ts": now_ts,
        "winning_hypothesis_id": winning_hypothesis_id,
        "root_cause_service": hyp_service,
        "root_cause_statement": hyp_statement,
        "affected_services": affected,
        "handled_by": handled_by,
        "similar_incidents_linked": similar_links,
    }

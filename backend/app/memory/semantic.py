import time
from typing import Any
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.memory.decay import decay_weight_days


def record_observation(
    graph: TenantGraph,
    service: str,
    text: str,
    kind: str = "observed",
    confidence_basis: str = "",
    incident_id: str | None = None,
    weight: float = 1.0,
    observation_id: str | None = None,
    ts: float | None = None,
) -> dict[str, Any]:
    """Record a semantic observation node in the graph:
      - kind: 'observed' (direct reading) or 'inferred' (reasoned fact)
      - active: true (initially active until superseded)
      - linked via ABOUT to the service (and optionally incident)
    """
    now_ts = float(ts) if ts is not None else time.time()
    obs_id = observation_id or f"obs_{service}_{int(now_ts * 1000)}"

    cypher = """
    MERGE (obs:Observation {id: $id})
    SET obs.text = $text,
        obs.kind = $kind,
        obs.confidence_basis = $confidence_basis,
        obs.active = true,
        obs.weight = $weight,
        obs.service = $service,
        obs.incident_id = $incident_id,
        obs.ts = $ts
    """
    params = {
        "id": obs_id,
        "text": text,
        "kind": kind,
        "confidence_basis": confidence_basis,
        "weight": float(weight),
        "service": service,
        "incident_id": incident_id,
        "ts": now_ts,
    }
    graph.query(cypher, params)

    # Link ABOUT to Service
    link_svc_cypher = """
    MATCH (obs:Observation {id: $obs_id})
    MERGE (s:Service {name: $service})
    MERGE (obs)-[:ABOUT]->(s)
    """
    graph.query(link_svc_cypher, {"obs_id": obs_id, "service": service})

    if incident_id:
        link_inc_cypher = """
        MATCH (obs:Observation {id: $obs_id})
        MERGE (i:Incident {id: $incident_id})
        MERGE (obs)-[:ABOUT]->(i)
        """
        graph.query(link_inc_cypher, {"obs_id": obs_id, "incident_id": incident_id})

    return {
        "id": obs_id,
        "service": service,
        "text": text,
        "kind": kind,
        "confidence_basis": confidence_basis,
        "active": True,
        "weight": float(weight),
        "incident_id": incident_id,
        "ts": now_ts,
    }


def supersede_observation(
    graph: TenantGraph,
    old_observation_id: str,
    service: str,
    new_text: str,
    kind: str = "observed",
    confidence_basis: str = "",
    weight: float = 1.0,
    incident_id: str | None = None,
) -> dict[str, Any]:
    """When new evidence contradicts an old fact:
      1. Create the new Observation node with active=true.
      2. Link (new_obs)-[:SUPERSEDES]->(old_obs).
      3. Mark old_obs.active = false.
    Never delete historical knowledge.
    """
    ts = time.time()
    new_obs_id = f"obs_{service}_{int(ts * 1000)}"

    # 1. Create new observation
    new_obs = record_observation(
        graph=graph,
        service=service,
        text=new_text,
        kind=kind,
        confidence_basis=confidence_basis,
        incident_id=incident_id,
        weight=weight,
        observation_id=new_obs_id,
        ts=ts,
    )

    # 2. Link SUPERSEDES and deactivate old observation
    supersede_cypher = """
    MATCH (new_obs:Observation {id: $new_id})
    MATCH (old_obs:Observation {id: $old_id})
    SET old_obs.active = false,
        old_obs.superseded_ts = $ts
    MERGE (new_obs)-[:SUPERSEDES]->(old_obs)
    """
    graph.query(supersede_cypher, {
        "new_id": new_obs_id,
        "old_id": old_observation_id,
        "ts": ts,
    })

    return {
        "new_observation": new_obs,
        "superseded_observation_id": old_observation_id,
        "status": "superseded",
        "ts": ts,
    }


def get_known_facts(
    graph: TenantGraph,
    service: str | None = None,
    as_of: float | None = None,
    half_life_days: float = 30.0,
) -> list[dict[str, Any]]:
    """Retrieve all active semantic observations, weighting them by exponential decay."""
    ref_ts = float(as_of) if as_of is not None else time.time()

    if service:
        cypher = """
        MATCH (obs:Observation)-[:ABOUT]->(s:Service {name: $service})
        WHERE obs.active = true AND obs.ts <= $ref_ts
        RETURN obs.id AS id, obs.text AS text, obs.kind AS kind,
               obs.confidence_basis AS basis, obs.weight AS weight,
               obs.ts AS ts, s.name AS service
        ORDER BY obs.ts DESC
        """
        params = {"service": service, "ref_ts": ref_ts}
    else:
        cypher = """
        MATCH (obs:Observation)
        WHERE obs.active = true AND obs.ts <= $ref_ts
        OPTIONAL MATCH (obs)-[:ABOUT]->(s:Service)
        RETURN obs.id AS id, obs.text AS text, obs.kind AS kind,
               obs.confidence_basis AS basis, obs.weight AS weight,
               obs.ts AS ts, s.name AS service
        ORDER BY obs.ts DESC
        """
        params = {"ref_ts": ref_ts}

    res = graph.query(cypher, params)
    facts: list[dict[str, Any]] = []

    if res and res.result_set:
        for row in res.result_set:
            oid, text, kind, basis, base_wt, obs_ts, svc_name = row
            o_timestamp = float(obs_ts or ref_ts)
            age_days = max(0.0, (ref_ts - o_timestamp) / 86400.0)
            effective_wt = decay_weight_days(float(base_wt or 1.0), age_days, half_life_days)

            facts.append({
                "id": oid,
                "service": svc_name or service or "global",
                "text": text,
                "kind": kind or "observed",
                "confidence_basis": basis or "",
                "base_weight": float(base_wt or 1.0),
                "effective_weight": effective_wt,
                "age_days": round(age_days, 1),
                "ts": o_timestamp,
            })

    return facts

import logging
from typing import Any
from app.tenancy import TenantGraph

logger = logging.getLogger(__name__)


def current_edges(rel_var: str = "r") -> str:
    """Cypher filter fragment matching currently valid temporal edges.
    Example: WHERE ({current_edges('r')})
    """
    return f"({rel_var}.valid_to IS NULL)"


def edges_as_of(ts: float | int | str, rel_var: str = "r") -> str:
    """Cypher filter fragment matching temporal edges that were active at timestamp ts.
    Edge is valid if valid_from <= ts AND (valid_to IS NULL OR valid_to > ts).
    Example: WHERE ({edges_as_of(1600000000, 'r')})
    """
    return f"({rel_var}.valid_from <= {ts} AND ({rel_var}.valid_to IS NULL OR {rel_var}.valid_to > {ts}))"


def temporal_edge_filter(as_of: float | int | str | None = None, rel_var: str = "r") -> str:
    """Convenience helper returning either edges_as_of(ts) or current_edges()."""
    if as_of is None:
        return current_edges(rel_var)
    return edges_as_of(as_of, rel_var)


def add_dependency_edge(
    graph: TenantGraph,
    caller: str,
    callee: str,
    valid_from: float = 0.0,
    valid_to: float | None = None,
    protocol: str = "http",
    criticality: str = "high",
    verified: bool = True,
    source: str = "seeded",
) -> dict[str, Any]:
    """Create or merge services and create a temporal DEPENDS_ON edge."""
    query = """
    MERGE (caller:Service {name: $caller})
    MERGE (callee:Service {name: $callee})
    CREATE (caller)-[r:DEPENDS_ON {
        protocol: $protocol,
        criticality: $criticality,
        valid_from: $valid_from,
        valid_to: $valid_to,
        verified: $verified,
        source: $source
    }]->(callee)
    RETURN caller.name AS caller, callee.name AS callee, r.valid_from AS valid_from, r.valid_to AS valid_to
    """
    params = {
        "caller": caller,
        "callee": callee,
        "valid_from": float(valid_from),
        "valid_to": float(valid_to) if valid_to is not None else None,
        "protocol": protocol,
        "criticality": criticality,
        "verified": bool(verified),
        "source": source,
    }
    res = graph.query(query, params)
    return {
        "caller": caller,
        "callee": callee,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "created": len(res.result_set) > 0,
    }


def close_dependency_edge(
    graph: TenantGraph,
    caller: str,
    callee: str,
    closed_at: float,
) -> int:
    """Close any currently active DEPENDS_ON edge between caller and callee."""
    query = """
    MATCH (caller:Service {name: $caller})-[r:DEPENDS_ON]->(callee:Service {name: $callee})
    WHERE r.valid_to IS NULL
    SET r.valid_to = $closed_at
    RETURN count(r) AS closed_count
    """
    params = {
        "caller": caller,
        "callee": callee,
        "closed_at": float(closed_at),
    }
    res = graph.query(query, params)
    if res and res.result_set:
        return int(res.result_set[0][0])
    return 0


def apply_architecture_change(
    graph: TenantGraph,
    change_id: str,
    summary: str,
    ts: float,
    closes_edges: list[dict[str, str] | tuple[str, str]] | None = None,
    opens_edges: list[dict[str, Any]] | None = None,
    source: str = "seeded",
) -> dict[str, Any]:
    """Applies an architecture change:
    1. Creates the ArchitectureChange node.
    2. Closes the specified edges (valid_to = ts).
    3. Opens new edges (valid_from = ts, valid_to = null).
    4. Links ArchitectureChange -[:CHANGED]-> Service for all touched services.
    """
    closes = closes_edges or []
    opens = opens_edges or []

    # Format closes list into clean strings for storage
    closes_repr = []
    for item in closes:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            closes_repr.append(f"{item[0]}->{item[1]}")
        elif isinstance(item, dict):
            closes_repr.append(f"{item.get('caller')}->{item.get('callee')}")

    opens_repr = []
    for item in opens:
        if isinstance(item, dict):
            opens_repr.append(f"{item.get('caller')}->{item.get('callee')}")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            opens_repr.append(f"{item[0]}->{item[1]}")

    # 1. Create ArchitectureChange node
    change_query = """
    MERGE (ac:ArchitectureChange {id: $id})
    SET ac.summary = $summary,
        ac.ts = $ts,
        ac.closes_edges = $closes_edges,
        ac.opens_edges = $opens_edges,
        ac.source = $source
    RETURN ac.id AS id
    """
    graph.query(
        change_query,
        {
            "id": change_id,
            "summary": summary,
            "ts": float(ts),
            "closes_edges": closes_repr,
            "opens_edges": opens_repr,
            "source": source,
        },
    )

    touched_services = set()

    # 2. Close edges
    closed_count = 0
    for edge in closes:
        if isinstance(edge, (list, tuple)):
            caller, callee = edge[0], edge[1]
        elif isinstance(edge, dict):
            caller, callee = edge["caller"], edge["callee"]
        else:
            continue

        touched_services.add(caller)
        touched_services.add(callee)
        closed_count += close_dependency_edge(graph, caller, callee, closed_at=ts)

    # 3. Open new edges
    opened_count = 0
    for edge in opens:
        if isinstance(edge, dict):
            caller = edge["caller"]
            callee = edge["callee"]
            protocol = edge.get("protocol", "http")
            criticality = edge.get("criticality", "high")
            verified = edge.get("verified", True)
            edge_src = edge.get("source", source)
        elif isinstance(edge, (list, tuple)):
            caller, callee = edge[0], edge[1]
            protocol = "http"
            criticality = "high"
            verified = True
            edge_src = source
        else:
            continue

        touched_services.add(caller)
        touched_services.add(callee)
        add_dependency_edge(
            graph=graph,
            caller=caller,
            callee=callee,
            valid_from=ts,
            valid_to=None,
            protocol=protocol,
            criticality=criticality,
            verified=verified,
            source=edge_src,
        )
        opened_count += 1

    # 4. Connect ArchitectureChange -[:CHANGED]-> Service
    for svc in touched_services:
        link_query = """
        MATCH (ac:ArchitectureChange {id: $change_id})
        MATCH (s:Service {name: $svc})
        MERGE (ac)-[:CHANGED]->(s)
        """
        graph.query(link_query, {"change_id": change_id, "svc": svc})

    return {
        "change_id": change_id,
        "summary": summary,
        "ts": ts,
        "closed_count": closed_count,
        "opened_count": opened_count,
        "touched_services": list(touched_services),
    }


def get_dependencies(
    graph: TenantGraph,
    as_of: float | int | str | None = None,
    caller: str | None = None,
    callee: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve DEPENDS_ON relationships matching temporal constraints and optional service filters."""
    filter_expr = temporal_edge_filter(as_of, rel_var="r")
    clauses = [filter_expr]
    params: dict[str, Any] = {}

    if caller:
        clauses.append("caller.name = $caller")
        params["caller"] = caller
    if callee:
        clauses.append("callee.name = $callee")
        params["callee"] = callee

    where_stmt = " AND ".join(clauses)

    query = f"""
    MATCH (caller:Service)-[r:DEPENDS_ON]->(callee:Service)
    WHERE {where_stmt}
    RETURN caller.name AS caller, callee.name AS callee,
           r.protocol AS protocol, r.criticality AS criticality,
           r.valid_from AS valid_from, r.valid_to AS valid_to,
           r.verified AS verified, r.source AS source
    ORDER BY caller.name, callee.name
    """
    res = graph.query(query, params)
    results = []
    if res and res.result_set:
        for row in res.result_set:
            results.append({
                "caller": row[0],
                "callee": row[1],
                "protocol": row[2],
                "criticality": row[3],
                "valid_from": row[4],
                "valid_to": row[5],
                "verified": row[6],
                "source": row[7],
            })
    return results

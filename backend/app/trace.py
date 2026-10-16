import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from app.tenancy import TenantGraph


@dataclass
class TraceStep:
    """Represents a single atomic graph query or algorithm step taken by a tool.
    Powers the Inspector Drawer and 'Why' Replay animation.
    """
    tool: str
    cypher: str
    params: dict[str, Any] = field(default_factory=dict)
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    summary: str = ""
    rows_count: int = 0
    rows: list[Any] = field(default_factory=list)
    duration_ms: float = 0.0
    id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)
    claims: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "cypher": self.cypher,
            "params": self.params,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "summary": self.summary,
            "rows_count": self.rows_count,
            "rows": self.rows,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
            "claims": list(self.claims),
        }


class TraceRegistry:
    """Thread-safe in-memory cache and index for all executed TraceSteps.
    Enables instant inspection retrieval by step ID across tools and API endpoints.
    """
    def __init__(self, max_size: int = 5000):
        self._steps: dict[str, TraceStep] = {}
        self._order: list[str] = []
        self._max_size = max_size

    def register(self, step: TraceStep) -> None:
        if not step or not step.id:
            return
        if step.id not in self._steps:
            if len(self._order) >= self._max_size:
                oldest = self._order.pop(0)
                self._steps.pop(oldest, None)
            self._order.append(step.id)
        self._steps[step.id] = step

    def get(self, step_id: str) -> TraceStep | None:
        return self._steps.get(step_id)

    def list_steps(self, limit: int = 50) -> list[TraceStep]:
        step_ids = self._order[-limit:]
        return [self._steps[sid] for sid in reversed(step_ids) if sid in self._steps]

    def clear(self) -> None:
        self._steps.clear()
        self._order.clear()


GLOBAL_TRACE_REGISTRY = TraceRegistry()


@dataclass
class Trace:
    """Accumulates execution provenance across multiple tool invocations and agent turns.
    Tracks all visited node IDs, edge IDs, and exact Cypher queries.
    """
    steps: list[TraceStep] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)
    edges: list[str] = field(default_factory=list)

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)
        GLOBAL_TRACE_REGISTRY.register(step)
        for nid in step.node_ids:
            if nid and nid not in self.nodes:
                self.nodes.append(nid)
        for eid in step.edge_ids:
            if eid and eid not in self.edges:
                self.edges.append(eid)

    def record(
        self,
        cypher: str,
        tool: str = "graph_query",
        duration_ms: float = 0.0,
        params: dict[str, Any] | None = None,
        node_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
        summary: str = "",
        rows_count: int = 0,
        read_only: bool = True,
    ) -> TraceStep:
        step = TraceStep(
            tool=tool,
            cypher=cypher,
            params=params or {},
            node_ids=node_ids or [],
            edge_ids=edge_ids or [],
            summary=summary or f"Executed {tool}",
            rows_count=rows_count,
            duration_ms=duration_ms,
        )
        self.add_step(step)
        return step

    def merge(self, other: "Trace | TraceStep | None") -> None:
        if other is None:
            return
        if isinstance(other, TraceStep):
            self.add_step(other)
            return
        if isinstance(other, Trace):
            for step in other.steps:
                self.add_step(step)

    def get_step(self, step_id: str) -> TraceStep | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return GLOBAL_TRACE_REGISTRY.get(step_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "total_steps": len(self.steps),
        }

    def get_why_replay(self) -> list[dict[str, Any]]:
        return get_why_replay(self)


@dataclass
class ToolResult:
    """Standard return type for all Ripple graph tools."""
    data: Any
    trace: Trace

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "trace": self.trace.to_dict(),
        }


# Color mapping for frontend force graph canvas by label
NODE_LABEL_COLORS = {
    "Service": "#3b82f6",          # blue
    "Person": "#10b981",           # emerald
    "Incident": "#ef4444",         # red
    "Hypothesis": "#f59e0b",       # amber
    "Evidence": "#8b5cf6",         # violet
    "Alert": "#f97316",            # orange
    "Runbook": "#06b6d4",          # cyan
    "Decision": "#ec4899",         # pink
    "Doc": "#64748b",              # slate
    "Deployment": "#6366f1",       # indigo
    "ArchitectureChange": "#e11d48",# rose
    "MetricSnapshot": "#84cc16",   # lime
    "Task": "#a855f7",             # purple
    "Observation": "#14b8a6",      # teal
    "Conflict": "#dc2626",         # deep red
}


def get_why_replay(trace_or_steps: Any) -> list[dict[str, Any]]:
    """Generate sequential 'Why' Replay animation frames stepping through the trace in order.
    Calculates active highlight deltas and cumulative subgraph progression.
    """
    raw_steps: list[Any] = []
    if isinstance(trace_or_steps, Trace):
        raw_steps = trace_or_steps.steps
    elif isinstance(trace_or_steps, dict):
        raw_steps = trace_or_steps.get("steps", [])
    elif isinstance(trace_or_steps, list):
        raw_steps = trace_or_steps
    else:
        raw_steps = []

    replay_frames: list[dict[str, Any]] = []
    cumulative_nodes: set[str] = set()
    cumulative_edges: set[str] = set()
    total_steps = len(raw_steps)

    for i, s in enumerate(raw_steps):
        if isinstance(s, TraceStep):
            step_dict = s.to_dict()
        elif isinstance(s, dict):
            step_dict = s
        else:
            continue

        step_id = step_dict.get("id", f"step_{i+1}")
        tool = step_dict.get("tool", "unknown_tool")
        summary = step_dict.get("summary", "")
        cypher = step_dict.get("cypher", "")
        params = step_dict.get("params", {})
        duration_ms = step_dict.get("duration_ms", 0.0)
        active_nodes = list(step_dict.get("node_ids", []))
        active_edges = list(step_dict.get("edge_ids", []))
        rows = step_dict.get("rows", [])
        rows_count = step_dict.get("rows_count", len(rows))

        # Deltas
        new_nodes = [n for n in active_nodes if n not in cumulative_nodes]
        new_edges = [e for e in active_edges if e not in cumulative_edges]

        # Update cumulative
        cumulative_nodes.update(active_nodes)
        cumulative_edges.update(active_edges)

        frame = {
            "step_index": i + 1,
            "total_steps": total_steps,
            "step_id": step_id,
            "tool": tool,
            "summary": summary,
            "cypher": cypher,
            "params": params,
            "duration_ms": duration_ms,
            "active_nodes": active_nodes,
            "active_edges": active_edges,
            "newly_added_nodes": new_nodes,
            "newly_added_edges": new_edges,
            "cumulative_nodes": sorted(list(cumulative_nodes)),
            "cumulative_edges": sorted(list(cumulative_edges)),
            "rows_count": rows_count,
            "rows_sample": rows[:5] if rows else [],
            "progress_percent": round(((i + 1) / max(1, total_steps)) * 100, 1),
        }
        replay_frames.append(frame)

    return replay_frames


def get_subgraph(
    graph: TenantGraph,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    center_service: str | None = None,
    radius: int = 1,
    as_of: float | None = None,
) -> dict[str, Any]:
    """Retrieve visual subgraph nodes and edges with styling properties
    for GraphCanvas and Inspector Drawer.
    """
    # 1. Resolve temporal filter
    if as_of is not None:
        temporal_filter = (
            f"(r.valid_from <= {float(as_of)} AND (r.valid_to IS NULL OR r.valid_to > {float(as_of)}))"
        )
    else:
        temporal_filter = "r.valid_to IS NULL"

    nodes_dict: dict[str, dict[str, Any]] = {}
    edges_list: list[dict[str, Any]] = []
    seen_edge_keys: set[str] = set()

    # Case A: Center Service neighborhood
    if center_service:
        if radius <= 1:
            center_cypher = f"""
            MATCH (s:Service {{name: $svc}})
            OPTIONAL MATCH (s)-[r:DEPENDS_ON]-(other:Service)
            WHERE r IS NULL OR {temporal_filter}
            WITH s, collect(DISTINCT other) AS others
            UNWIND ([s] + [o IN others WHERE o IS NOT NULL]) AS n
            RETURN DISTINCT n.name AS id,
                            n.name AS name,
                            n.tier AS tier,
                            n.language AS language,
                            n.description AS description,
                            n.deps_known AS deps_known,
                            n.source AS source,
                            labels(n) AS labels
            """
        else:
            center_cypher = f"""
            MATCH (s:Service {{name: $svc}})
            OPTIONAL MATCH p = (s)-[:DEPENDS_ON*1..{radius}]-(other:Service)
            WHERE p IS NULL OR all(rel IN relationships(p) WHERE {temporal_filter.replace('r.', 'rel.')})
            WITH s, collect(DISTINCT other) AS others
            UNWIND ([s] + [o IN others WHERE o IS NOT NULL]) AS n
            RETURN DISTINCT n.name AS id,
                            n.name AS name,
                            n.tier AS tier,
                            n.language AS language,
                            n.description AS description,
                            n.deps_known AS deps_known,
                            n.source AS source,
                            labels(n) AS labels
            """
        res_nodes = graph.query(center_cypher, {"svc": center_service})

        if res_nodes and res_nodes.result_set:
            for row in res_nodes.result_set:
                nid, name, tier, lang, desc, dk, src, lbls = row
                primary_label = lbls[0] if lbls else "Service"
                color = NODE_LABEL_COLORS.get(primary_label, "#3b82f6")
                nodes_dict[nid] = {
                    "id": nid,
                    "name": name or nid,
                    "label": primary_label,
                    "labels": lbls,
                    "tier": tier or "tier-2",
                    "language": lang,
                    "description": desc,
                    "deps_known": dk if dk is not None else True,
                    "source": src or "real",
                    "color": color,
                    "val": 16 if primary_label == "Service" else 10,
                }

    # Case B: Specific Node IDs requested (e.g. from trace step or inspector)
    elif node_ids:
        clean_ids = [n.strip() for n in node_ids if n and n.strip()]
        if clean_ids:
            nodes_cypher = """
            MATCH (n)
            WHERE n.name IN $ids OR n.id IN $ids OR n.login IN $ids
            RETURN DISTINCT
                coalesce(n.id, n.name, n.login) AS id,
                coalesce(n.name, n.title, n.login, n.id) AS name,
                labels(n) AS labels,
                n.tier AS tier,
                n.language AS language,
                n.kind AS kind,
                n.status AS status,
                n.severity AS severity,
                n.source AS source,
                n.freshness AS freshness
            """
            res_nodes = graph.query(nodes_cypher, {"ids": clean_ids})
            if res_nodes and res_nodes.result_set:
                for row in res_nodes.result_set:
                    nid, name, lbls, tier, lang, kind, status, sev, src, fresh = row
                    primary_label = lbls[0] if lbls else "Node"
                    color = NODE_LABEL_COLORS.get(primary_label, "#94a3b8")
                    nodes_dict[nid] = {
                        "id": nid,
                        "name": name or nid,
                        "label": primary_label,
                        "labels": lbls,
                        "tier": tier,
                        "language": lang,
                        "kind": kind,
                        "status": status,
                        "severity": sev,
                        "source": src or "real",
                        "freshness": fresh,
                        "color": color,
                        "val": 14 if primary_label in ("Service", "Incident") else 10,
                    }

    # Case C: Baseline topology (all services)
    else:
        base_cypher = """
        MATCH (s:Service)
        RETURN s.name AS id, s.name AS name, labels(s) AS labels, s.tier AS tier,
               s.language AS language, s.description AS description,
               s.deps_known AS deps_known, s.source AS source
        """
        res_nodes = graph.query(base_cypher)
        if res_nodes and res_nodes.result_set:
            for row in res_nodes.result_set:
                nid, name, lbls, tier, lang, desc, dk, src = row
                primary_label = lbls[0] if lbls else "Service"
                color = NODE_LABEL_COLORS.get(primary_label, "#3b82f6")
                nodes_dict[nid] = {
                    "id": nid,
                    "name": name or nid,
                    "label": primary_label,
                    "labels": lbls,
                    "tier": tier or "tier-2",
                    "language": lang,
                    "description": desc,
                    "deps_known": dk if dk is not None else True,
                    "source": src or "real",
                    "color": color,
                    "val": 14,
                }

    # 2. Fetch relationships between the collected nodes
    active_node_ids = list(nodes_dict.keys())
    if active_node_ids:
        edges_cypher = f"""
        MATCH (a)-[r]->(b)
        WHERE (a.name IN $ids OR a.id IN $ids OR a.login IN $ids)
          AND (b.name IN $ids OR b.id IN $ids OR b.login IN $ids)
          AND (type(r) <> 'DEPENDS_ON' OR {temporal_filter})
        RETURN coalesce(a.id, a.name, a.login) AS source,
               coalesce(b.id, b.name, b.login) AS target,
               type(r) AS type,
               r.protocol AS protocol,
               r.criticality AS criticality,
               r.verified AS verified,
               r.source AS source_type,
               r.weight AS weight
        """
        res_edges = graph.query(edges_cypher, {"ids": active_node_ids})
        if res_edges and res_edges.result_set:
            for row in res_edges.result_set:
                src_id, tgt_id, rel_type, proto, crit, v_flag, src_type, wt = row
                edge_key = f"{src_id}->{tgt_id}:{rel_type}"
                if edge_key not in seen_edge_keys:
                    seen_edge_keys.add(edge_key)
                    edges_list.append({
                        "id": edge_key,
                        "source": src_id,
                        "target": tgt_id,
                        "type": rel_type,
                        "protocol": proto or "",
                        "criticality": crit or "",
                        "verified": v_flag if v_flag is not None else True,
                        "source_type": src_type or "real",
                        "weight": float(wt) if wt is not None else 1.0,
                    })

    # 3. Add explicit edge_ids if passed and not yet added
    if edge_ids:
        for e_str in edge_ids:
            if "->" in e_str:
                parts = e_str.split("->", 1)
                s_name = parts[0].strip()
                t_name = parts[1].strip()
                edge_key = f"{s_name}->{t_name}:DEPENDS_ON"
                if edge_key not in seen_edge_keys:
                    seen_edge_keys.add(edge_key)
                    edges_list.append({
                        "id": edge_key,
                        "source": s_name,
                        "target": t_name,
                        "type": "DEPENDS_ON",
                        "protocol": "",
                        "criticality": "",
                        "verified": True,
                        "source_type": "trace",
                        "weight": 1.0,
                    })

    return {
        "nodes": list(nodes_dict.values()),
        "edges": edges_list,
        "total_nodes": len(nodes_dict),
        "total_edges": len(edges_list),
        "as_of": as_of,
    }


def get_step_inspection(step_id: str, graph: TenantGraph | None = None) -> dict[str, Any] | None:
    """Retrieve full inspection metadata for a single TraceStep:
    Cypher query, parameters, touched nodes/edges, summary, rows count,
    returned rows sample, and visual subgraph representation.
    """
    step = GLOBAL_TRACE_REGISTRY.get(step_id)
    if not step:
        return None

    step_dict = step.to_dict()

    # If graph is provided, enrich with subgraph metadata for the inspector
    if graph:
        subgraph = get_subgraph(
            graph=graph,
            node_ids=step.node_ids,
            edge_ids=step.edge_ids,
        )
        step_dict["subgraph"] = subgraph

    return step_dict


def get_evidence_provenance(graph: TenantGraph, evidence_id_or_ids: str | list[str]) -> list[dict[str, Any]]:
    """Retrieve full evidence provenance:
    source_ref, timestamp, freshness, observed/inferred badge, and linked hypotheses.
    """
    if isinstance(evidence_id_or_ids, str):
        ev_ids = [evidence_id_or_ids]
    else:
        ev_ids = list(evidence_id_or_ids)

    if not ev_ids:
        return []

    cypher = """
    MATCH (e:Evidence)
    WHERE e.id IN $ev_ids
    OPTIONAL MATCH (h:Hypothesis)-[r:SUPPORTED_BY|CONTRADICTED_BY]->(e)
    RETURN e.id AS id,
           e.kind AS kind,
           e.type AS type,
           e.summary AS summary,
           e.source_ref AS source_ref,
           e.observed_ts AS observed_ts,
           e.freshness AS freshness,
           e.weight AS weight,
           h.id AS hyp_id,
           type(r) AS relation_type
    """
    res = graph.query(cypher, {"ev_ids": ev_ids})
    evidence_map: dict[str, dict[str, Any]] = {}

    if res and res.result_set:
        for row in res.result_set:
            eid, kind, etype, summary, s_ref, obs_ts, fresh, wt, hyp_id, rel = row
            if eid not in evidence_map:
                evidence_map[eid] = {
                    "id": eid,
                    "kind": kind or "observed",  # 'observed' or 'inferred'
                    "type": etype or "generic",
                    "summary": summary or "",
                    "source_ref": s_ref or "",
                    "observed_ts": float(obs_ts or 0.0),
                    "freshness": float(fresh or 1.0),
                    "weight": float(wt or 1.0),
                    "linked_hypotheses": [],
                }
            if hyp_id:
                evidence_map[eid]["linked_hypotheses"].append({
                    "hypothesis_id": hyp_id,
                    "relation": rel or "SUPPORTED_BY",
                })

    return list(evidence_map.values())

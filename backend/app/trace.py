import time
from dataclasses import dataclass, field, asdict
from typing import Any


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
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "cypher": self.cypher,
            "params": self.params,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "summary": self.summary,
            "rows_count": self.rows_count,
            "duration_ms": round(self.duration_ms, 2),
        }


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
        for nid in step.node_ids:
            if nid and nid not in self.nodes:
                self.nodes.append(nid)
        for eid in step.edge_ids:
            if eid and eid not in self.edges:
                self.edges.append(eid)

    def merge(self, other: "Trace | TraceStep | None") -> None:
        if other is None:
            return
        if isinstance(other, TraceStep):
            self.add_step(other)
            return
        if isinstance(other, Trace):
            for step in other.steps:
                self.add_step(step)

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "nodes": list(self.nodes),
            "edges": list(self.edges),
            "total_steps": len(self.steps),
        }


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

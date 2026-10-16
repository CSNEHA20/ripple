"""Ripple Graph Tool Library (M4).
Exposes graph traversal, pathfinding, PageRank, recency-weighted ownership,
change detection, metrics inspection, and incident recall tools.
Every tool call returns structured data plus an explainable provenance Trace.
"""

from app.tools.blast_radius import blast_radius
from app.tools.root_cause import upstream_suspects
from app.tools.paths import path_between
from app.tools.criticality import criticality_ranking
from app.tools.people import who_knows
from app.tools.changes import recent_changes
from app.tools.incidents import (
    service_health,
    similar_incidents,
    rank_runbooks,
    check_applicability,
    counterfactual_blast,
)
from app.tools.registry import (
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    get_tool_schemas,
    execute_tool,
)

__all__ = [
    "blast_radius",
    "upstream_suspects",
    "path_between",
    "criticality_ranking",
    "who_knows",
    "recent_changes",
    "service_health",
    "similar_incidents",
    "rank_runbooks",
    "check_applicability",
    "counterfactual_blast",
    "TOOL_FUNCTIONS",
    "TOOL_SCHEMAS",
    "get_tool_schemas",
    "execute_tool",
]

from typing import Any, Callable
from app.tenancy import TenantGraph
from app.trace import ToolResult
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

# Registry of callable tool functions
TOOL_FUNCTIONS: dict[str, Callable[..., ToolResult]] = {
    "blast_radius": blast_radius,
    "upstream_suspects": upstream_suspects,
    "path_between": path_between,
    "criticality_ranking": criticality_ranking,
    "who_knows": who_knows,
    "recent_changes": recent_changes,
    "service_health": service_health,
    "similar_incidents": similar_incidents,
    "rank_runbooks": rank_runbooks,
    "check_applicability": check_applicability,
    "counterfactual_blast": counterfactual_blast,
}

# Standardized JSON Schemas for LLM function calling and MCP tool server
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "blast_radius",
        "description": "Calculate all downstream services that would be impacted if a given service degrades or fails.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the target microservice (e.g. 'paymentservice', 'cartservice').",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum dependency traversal hops (default 4).",
                    "default": 4,
                },
                "as_of": {
                    "type": "number",
                    "description": "Optional historical Unix timestamp to evaluate temporal graph state as-of that time.",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "upstream_suspects",
        "description": "Identify all upstream dependencies that could be causing an alert on the specified service.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the alerting microservice.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum forward dependency search hops (default 3).",
                    "default": 3,
                },
                "as_of": {
                    "type": "number",
                    "description": "Optional historical Unix timestamp for as-of evaluation.",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "path_between",
        "description": "Find the shortest active dependency path explaining why service A depends on service B.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller": {
                    "type": "string",
                    "description": "Starting caller service name.",
                },
                "callee": {
                    "type": "string",
                    "description": "Target callee dependency name.",
                },
                "as_of": {
                    "type": "number",
                    "description": "Optional historical Unix timestamp.",
                },
            },
            "required": ["caller", "callee"],
        },
    },
    {
        "name": "criticality_ranking",
        "description": "Rank all services in the system by architectural criticality using PageRank over DEPENDS_ON.",
        "parameters": {
            "type": "object",
            "properties": {
                "damping_factor": {
                    "type": "number",
                    "description": "PageRank damping factor (default 0.85).",
                    "default": 0.85,
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Power iteration steps (default 30).",
                    "default": 30,
                },
            },
        },
    },
    {
        "name": "who_knows",
        "description": "Find the best code owners and subject matter experts for a service ranked by recency-weighted commits and PRs.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the microservice.",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of top experts to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "recent_changes",
        "description": "Retrieve recent deployments, PRs, and architecture changes touching a service near the alert window.",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the microservice.",
                },
                "hours": {
                    "type": "number",
                    "description": "Time window in hours before the alert (default 24.0).",
                    "default": 24.0,
                },
                "as_of": {
                    "type": "number",
                    "description": "Optional reference timestamp (defaults to current time).",
                },
            },
            "required": ["service"],
        },
    },
    {
        "name": "service_health",
        "description": "Retrieve metric snapshot health (latency, error rate, status) across suspect services. Identifies failing, degraded, and normal services.",
        "parameters": {
            "type": "object",
            "properties": {
                "services": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of service names to inspect.",
                },
                "ts": {
                    "type": "number",
                    "description": "Optional reference timestamp.",
                },
            },
            "required": ["services"],
        },
    },
    {
        "name": "similar_incidents",
        "description": "Recall past resolved and failed incidents matching the alert text and affected service set.",
        "parameters": {
            "type": "object",
            "properties": {
                "alert_text": {
                    "type": "string",
                    "description": "Alert text or symptom description.",
                },
                "services": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of affected service names.",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of similar incidents to retrieve (default 5).",
                    "default": 5,
                },
            },
            "required": ["alert_text"],
        },
    },
    {
        "name": "rank_runbooks",
        "description": "Rank operational runbooks based on historical observed outcome success rate with Laplace smoothing.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of similar incident IDs to prioritize matching runbooks.",
                },
            },
        },
    },
    {
        "name": "check_applicability",
        "description": "Verify whether a past runbook fix is still applicable against the current graph topology or if an architecture change invalidated it.",
        "parameters": {
            "type": "object",
            "properties": {
                "runbook_id": {
                    "type": "string",
                    "description": "ID of the runbook to check (e.g. 'rb_rollback', 'rb_cache_flush').",
                },
            },
            "required": ["runbook_id"],
        },
    },
    {
        "name": "counterfactual_blast",
        "description": "Perform what-if diff comparing observed incident blast radius against what would have happened if a different service failed.",
        "parameters": {
            "type": "object",
            "properties": {
                "observed_incident_id": {
                    "type": "string",
                    "description": "ID of the real or simulated incident.",
                },
                "hypothetical_service": {
                    "type": "string",
                    "description": "Alternative service to simulate failure for.",
                },
                "as_of": {
                    "type": "number",
                    "description": "Optional historical Unix timestamp.",
                },
            },
            "required": ["observed_incident_id", "hypothetical_service"],
        },
    },
]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return all available tool JSON schemas."""
    return TOOL_SCHEMAS


def execute_tool(
    name: str,
    graph: TenantGraph,
    arguments: dict[str, Any] | None = None,
) -> ToolResult:
    """Execute a tool by name with arguments against the given TenantGraph."""
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        raise ValueError(f"Unknown tool '{name}'. Available: {list(TOOL_FUNCTIONS.keys())}")
    args = arguments or {}
    return func(graph=graph, **args)

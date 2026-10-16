"""Ripple MCP Server (M11).
Exposes Ripple's graph intelligence tools via Model Context Protocol (MCP):
  - M4 graph tools: blast_radius, upstream_suspects, recent_changes, service_health,
    who_knows, similar_incidents, criticality_ranking, path_between.
  - Core engine tools: recall, rank_hypotheses, counterfactual_blast, ask.

Any MCP-capable agent or LLM client can attach and interrogate Ripple's graph directly.
"""

import json
import logging
from typing import Any
from mcp.server.mcpserver import MCPServer
from app.tenancy import TenantGraph, sanitize_tenant_id
from app.tools.registry import execute_tool
from app.memory.recall import recall as memory_recall
from app.hypotheses.engine import run_investigation
from app.counterfactual.engine import compute_counterfactual
from app.brain import ask_brain

logger = logging.getLogger("ripple.mcp")

# Initialize MCP Server
mcp_server = MCPServer(
    name="ripple-graph",
    version="0.1.0",
    description="Ripple graph intelligence tools for on-call SRE incident triage and root cause investigation.",
)


@mcp_server.tool()
def blast_radius(
    service: str,
    max_depth: int = 4,
    as_of: float | None = None,
    tenant: str = "storefront",
) -> str:
    """Calculate all downstream services that would be impacted if a given service degrades or fails."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res = execute_tool(
        "blast_radius",
        graph=graph,
        arguments={"service": service, "max_depth": max_depth, "as_of": as_of},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def upstream_suspects(
    service: str,
    max_depth: int = 3,
    as_of: float | None = None,
    tenant: str = "storefront",
) -> str:
    """Identify all upstream dependencies that could be causing an alert on the specified service."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res = execute_tool(
        "upstream_suspects",
        graph=graph,
        arguments={"service": service, "max_depth": max_depth, "as_of": as_of},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def recent_changes(
    service: str,
    hours: float = 24.0,
    as_of: float | None = None,
    tenant: str = "storefront",
) -> str:
    """Retrieve recent deployments, PRs, and architecture changes touching a service near the alert window."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res = execute_tool(
        "recent_changes",
        graph=graph,
        arguments={"service": service, "hours": hours, "as_of": as_of},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def service_health(
    services: list[str] | str,
    ts: float | None = None,
    tenant: str = "storefront",
) -> str:
    """Retrieve metric snapshot health (latency, error rate, status) across suspect services."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    svc_list = [services] if isinstance(services, str) else services
    res = execute_tool(
        "service_health",
        graph=graph,
        arguments={"services": svc_list, "ts": ts},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def who_knows(
    service: str,
    k: int = 5,
    tenant: str = "storefront",
) -> str:
    """Find the best code owners and subject matter experts for a service ranked by recency-weighted commits and PRs."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res = execute_tool(
        "who_knows",
        graph=graph,
        arguments={"service": service, "k": k},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def similar_incidents(
    alert_text: str,
    services: list[str] | None = None,
    k: int = 3,
    tenant: str = "storefront",
) -> str:
    """Recall past resolved and failed incidents matching the alert text and affected service set."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    args: dict[str, Any] = {"alert_text": alert_text, "k": k}
    if services:
        args["services"] = services
    res = execute_tool(
        "similar_incidents",
        graph=graph,
        arguments=args,
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def criticality_ranking(
    damping_factor: float = 0.85,
    max_iterations: int = 30,
    tenant: str = "storefront",
) -> str:
    """Rank all services in the system by architectural criticality using PageRank over DEPENDS_ON."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res = execute_tool(
        "criticality_ranking",
        graph=graph,
        arguments={"damping_factor": damping_factor, "max_iterations": max_iterations},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def path_between(
    caller: str,
    callee: str,
    as_of: float | None = None,
    tenant: str = "storefront",
) -> str:
    """Find the shortest active dependency path explaining why service A depends on service B."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res = execute_tool(
        "path_between",
        graph=graph,
        arguments={"caller": caller, "callee": callee, "as_of": as_of},
    )
    return json.dumps(res.to_dict())


@mcp_server.tool()
def recall(
    alert_text: str,
    services: list[str] | None = None,
    as_of: float | None = None,
    k: int = 5,
    tenant: str = "storefront",
) -> str:
    """Synthesize episodic, semantic, procedural, and outcome memory: similar incidents, runbooks, and active facts."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    svc_list = services or []
    res, trace = memory_recall(
        graph=graph,
        alert_text=alert_text,
        services=svc_list,
        as_of=as_of,
        k=k,
    )
    return json.dumps({
        "data": res,
        "trace": trace.to_dict(),
    })


@mcp_server.tool()
def rank_hypotheses(
    alerting_service: str,
    alert_text: str = "",
    as_of: float | None = None,
    tenant: str = "storefront",
) -> str:
    """Execute graph-guided hypothesis and evidence engine: rank root cause candidates with freshness decay."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res, trace = run_investigation(
        graph=graph,
        alerting_service=alerting_service,
        alert_text=alert_text,
        as_of=as_of,
        persist=False,
    )
    return json.dumps({
        "data": res,
        "trace": trace.to_dict(),
    })


@mcp_server.tool()
def counterfactual_blast(
    observed_incident_id: str,
    hypothetical_service: str,
    as_of: str = "incident_time",
    compare_with_now: bool = True,
    tenant: str = "storefront",
) -> str:
    """Run what-if counterfactual blast radius analysis comparing actual incident against hypothetical failure."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res, trace = compute_counterfactual(
        graph=graph,
        observed_incident_id=observed_incident_id,
        hypothetical_service=hypothetical_service,
        as_of=as_of,
        compare_with_now=compare_with_now,
    )
    return json.dumps({
        "data": res,
        "trace": trace.to_dict(),
    })


@mcp_server.tool()
def ask(
    question: str,
    mode: str = "replay",
    tenant: str = "storefront",
) -> str:
    """Query company-brain knowledge graph: answer questions strictly cited from graph facts with staleness checks."""
    graph = TenantGraph(tenant_id=sanitize_tenant_id(tenant))
    res, trace = ask_brain(
        graph=graph,
        question=question,
        tenant_id=graph.tenant_id,
        mode=mode,
    )
    return json.dumps({
        "data": res,
        "trace": trace.to_dict(),
    })


def create_mcp_app():
    """Return an SSE Starlette application for serving MCP over HTTP/SSE."""
    return mcp_server.sse_app()


def run_stdio():
    """Run MCP server in standard I/O mode for integration with Claude Desktop, Cursor, or CLI clients."""
    import asyncio
    asyncio.run(mcp_server.run_stdio_async())


if __name__ == "__main__":
    run_stdio()

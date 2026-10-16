import logging
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.tenancy import TenantGraph, ensure_tenant, get_falkordb_client, sanitize_tenant_id
from app.schema import ensure_tenant_schema
from app.ingest.bootstrap import bootstrap_tenant_all, bootstrap_second_tenant

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ripple.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ripple backend starting up. Checking FalkorDB connection...")
    try:
        client = get_falkordb_client()
        # Initialize and ingest default tenants
        bootstrap_tenant_all("storefront")
        bootstrap_second_tenant("payments")
        logger.info("FalkorDB connected: storefront and payments tenants bootstrapped.")
    except Exception as e:
        logger.warning(f"FalkorDB bootstrap on startup could not be completed: {e}")
    yield
    logger.info("Ripple backend shutting down.")


app = FastAPI(
    title="Ripple API",
    description="On-call agent crew using FalkorDB as its brain",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_tenant(
    x_tenant: Annotated[str | None, Header(description="Tenant ID header")] = None,
    tenant: Annotated[str | None, Query(description="Tenant ID query param fallback")] = None,
) -> TenantGraph:
    """Dependency to extract tenant from header or query param and return an isolated TenantGraph."""
    target_tenant = x_tenant or tenant or "storefront"
    return TenantGraph(tenant_id=target_tenant)


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint required by M0."""
    falkor_status = "disconnected"
    try:
        client = get_falkordb_client()
        demo_graph = TenantGraph("storefront", db=client)
        if demo_graph.ping():
            falkor_status = "connected"
    except Exception as e:
        falkor_status = f"unreachable: {str(e)}"

    return {
        "status": "ok",
        "service": "ripple-backend",
        "version": "0.1.0",
        "falkordb": falkor_status,
        "falkordb_host": settings.falkordb_host,
        "falkordb_port": settings.falkordb_port,
    }


@app.post("/tenants/{tenant_id}/bootstrap")
@app.post("/api/tenants/{tenant_id}/bootstrap")
def bootstrap_tenant(tenant_id: str):
    """Idempotently bootstrap a tenant graph, ensure its schema indexes, and ingest baseline data."""
    try:
        clean_id = sanitize_tenant_id(tenant_id)
        if clean_id == "payments":
            data = bootstrap_second_tenant("payments")
            graph = TenantGraph(clean_id)
            schema_indexes = ensure_tenant_schema(graph)
        elif clean_id == "storefront" or clean_id == "default":
            data = bootstrap_tenant_all(clean_id)
            graph = TenantGraph(clean_id)
            schema_indexes = ensure_tenant_schema(graph)
        else:
            graph = ensure_tenant(clean_id)
            schema_indexes = ensure_tenant_schema(graph)
            data = {
                "tenant_id": graph.tenant_id,
                "graph_name": graph.graph_name,
                "schema_indexes": schema_indexes,
            }

        return {
            "status": "success",
            "tenant_id": clean_id,
            "graph_name": f"tenant_{clean_id}",
            "schema_indexes": schema_indexes,
            "data": data,
            "message": f"Tenant '{clean_id}' successfully bootstrapped and ready.",
        }
    except Exception as e:
        logger.error(f"Failed to bootstrap tenant '{tenant_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to bootstrap tenant: {str(e)}")


@app.post("/tenants/{tenant_id}/ingest")
@app.post("/api/tenants/{tenant_id}/ingest")
def ingest_tenant(tenant_id: str):
    """Trigger full data ingestion for the specified tenant."""
    return bootstrap_tenant(tenant_id)


@app.get("/tenants/{tenant_id}/stats")
@app.get("/api/tenants/{tenant_id}/stats")
def tenant_stats(tenant_id: str):
    """Get node and relationship statistics for a tenant graph."""
    clean_id = sanitize_tenant_id(tenant_id)
    graph = TenantGraph(tenant_id=clean_id)
    try:
        node_res = graph.query("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY count DESC")
        rel_res = graph.query("MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count ORDER BY count DESC")

        nodes = {row[0]: row[1] for row in (node_res.result_set if node_res else [])}
        relationships = {row[0]: row[1] for row in (rel_res.result_set if rel_res else [])}

        return {
            "tenant_id": clean_id,
            "graph_name": graph.graph_name,
            "nodes": nodes,
            "total_nodes": sum(nodes.values()),
            "relationships": relationships,
            "total_relationships": sum(relationships.values()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats for tenant {tenant_id}: {str(e)}")


@app.get("/api/smoke")
def smoke_test(tenant: str = Query(default="smoke", description="Tenant graph to test")):
    """Smoke test: connect, create a node & dependency edge, query it, and return result."""
    try:
        graph = TenantGraph(tenant_id=tenant)
        # Idempotent write
        create_cypher = """
        MERGE (a:Service {name: 'frontend'})
        MERGE (b:Service {name: 'checkout'})
        MERGE (a)-[r:DEPENDS_ON {protocol: 'gRPC', source: 'smoke_test', valid_from: 0.0}]->(b)
        RETURN a.name AS source, type(r) AS rel, b.name AS target
        """
        create_res = graph.query(create_cypher)

        # Query verification
        verify_cypher = """
        MATCH (a:Service {name: 'frontend'})-[r:DEPENDS_ON]->(b:Service {name: 'checkout'})
        RETURN a.name AS caller, b.name AS callee, r.protocol AS protocol
        """
        verify_res = graph.query(verify_cypher)

        records = [
            {"caller": row[0], "callee": row[1], "protocol": row[2]}
            for row in verify_res.result_set
        ]

        return {
            "success": True,
            "tenant": tenant,
            "created": [row for row in create_res.result_set],
            "verified": records,
            "message": "FalkorDB smoke test succeeded! Graph node and edge verified.",
        }
    except Exception as e:
        logger.error(f"Smoke test failed: {e}")
        raise HTTPException(status_code=500, detail=f"FalkorDB smoke test failed: {str(e)}")

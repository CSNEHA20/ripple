import logging
import uuid
import json
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any
from fastapi import FastAPI, Header, HTTPException, Query, Depends, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.security import verify_webhook_signature, check_alert_dedupe
from app.tenancy import TenantGraph, ensure_tenant, get_falkordb_client, sanitize_tenant_id
from app.schema import ensure_tenant_schema
from app.ingest.bootstrap import bootstrap_tenant_all, bootstrap_second_tenant
from app.ingest.embed import embed_text

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


class TenantMiddleware(BaseHTTPMiddleware):
    """M11 Tenant Middleware:
    Resolves tenant from X-Tenant header (or query param fallback),
    builds the isolated TenantGraph, stores on request.state,
    and reflects X-Tenant in response headers.
    """
    async def dispatch(self, request: Request, call_next):
        tenant_header = request.headers.get("x-tenant") or request.headers.get("X-Tenant")
        tenant_query = request.query_params.get("tenant")
        target_tenant = sanitize_tenant_id(tenant_header or tenant_query or "storefront")

        request.state.tenant_id = target_tenant
        try:
            request.state.tenant_graph = TenantGraph(tenant_id=target_tenant)
        except Exception:
            request.state.tenant_graph = None

        response = await call_next(request)
        response.headers["X-Tenant"] = target_tenant
        return response


app.add_middleware(TenantMiddleware)


def get_current_tenant(
    request: Request,
    x_tenant: Annotated[str | None, Header(description="Tenant ID header")] = None,
    tenant: Annotated[str | None, Query(description="Tenant ID query param fallback")] = None,
) -> TenantGraph:
    """Dependency to extract tenant from request state (populated by TenantMiddleware) or header/query fallback."""
    if hasattr(request.state, "tenant_graph") and request.state.tenant_graph is not None:
        return request.state.tenant_graph
    target_tenant = sanitize_tenant_id(x_tenant or tenant or getattr(request.state, "tenant_id", "storefront"))
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


@app.post("/tenants/{tenant_id}/reembed")
@app.post("/api/tenants/{tenant_id}/reembed")
def reembed_tenant(tenant_id: str):
    """Recompute all Incident and Decision embeddings for the tenant graph with the active backend."""
    try:
        clean_id = sanitize_tenant_id(tenant_id)
        graph = TenantGraph(clean_id)

        # 1. Re-embed Incidents with parameterized Cypher (Fix I8)
        inc_res = graph.query("MATCH (i:Incident) RETURN i.id, i.title, i.summary")
        inc_count = 0
        if inc_res and inc_res.result_set:
            for row in inc_res.result_set:
                iid, title, summary = row[0], row[1] or "", row[2] or ""
                vec = embed_text(f"{title} {summary}")
                try:
                    graph.query("MATCH (i:Incident {id: $iid}) SET i.signature_embedding = vecf32($vec)", {"iid": str(iid), "vec": vec})
                except Exception:
                    vals_str = ",".join(str(round(x, 6)) for x in vec)
                    graph.query(f"MATCH (i:Incident {{id: $iid}}) SET i.signature_embedding = vecf32([{vals_str}])", {"iid": str(iid)})
                inc_count += 1

        # 2. Re-embed Decisions with parameterized Cypher (Fix I8)
        dec_res = graph.query("MATCH (d:Decision) RETURN d.id, d.summary")
        dec_count = 0
        if dec_res and dec_res.result_set:
            for row in dec_res.result_set:
                did, summary = row[0], row[1] or ""
                vec = embed_text(summary)
                try:
                    graph.query("MATCH (d:Decision {id: $did}) SET d.embedding = vecf32($vec)", {"did": str(did), "vec": vec})
                except Exception:
                    vals_str = ",".join(str(round(x, 6)) for x in vec)
                    graph.query(f"MATCH (d:Decision {{id: $did}}) SET d.embedding = vecf32([{vals_str}])", {"did": str(did)})
                dec_count += 1

        return {
            "status": "success",
            "tenant_id": clean_id,
            "reembedded_incidents": inc_count,
            "reembedded_decisions": dec_count,
            "message": f"Successfully re-embedded {inc_count} incidents and {dec_count} decisions.",
        }
    except Exception as e:
        logger.error(f"Re-embed failed for tenant '{tenant_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Re-embed failed: {str(e)}")


@app.post("/webhooks/alert")
@app.post("/api/webhooks/alert")
async def alert_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    sync: bool = Query(default=False, description="Execute synchronously if true"),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Alert Intake Webhook:
    Accepts generic JSON alerts and Prometheus Alertmanager payloads,
    verifies HMAC signature, deduplicates, and launches the 4-agent crew asynchronously.
    """
    try:
        body_bytes = await request.body()
        sig = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Signature")
        if not verify_webhook_signature(body_bytes, sig, settings.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        service = "unknown"
        alert_text = "System alert received"
        severity = "P2"
        scenario_id = None

        # Check Prometheus Alertmanager format
        if "alerts" in payload and isinstance(payload["alerts"], list) and len(payload["alerts"]) > 0:
            first_alert = payload["alerts"][0]
            labels = first_alert.get("labels", {})
            annotations = first_alert.get("annotations", {})
            service = labels.get("service") or labels.get("job") or labels.get("alertname", "unknown")
            alert_text = annotations.get("description") or annotations.get("summary") or first_alert.get("fingerprint", "")
            severity = labels.get("severity", "P2").upper()
            if severity not in ("P1", "P2", "P3"):
                severity = "P1" if "critical" in severity.lower() else "P2"
        elif "service" in payload:
            service = payload["service"]
            alert_text = payload.get("text") or payload.get("description") or f"Degraded service alert on {service}"
            severity = payload.get("severity", "P2")
            scenario_id = payload.get("scenario_id")

        # Deduplicate alert
        dedupe_key = f"{service}:{alert_text}"
        if check_alert_dedupe(dedupe_key):
            return {
                "status": "deduplicated",
                "message": "Alert deduplicated within window",
                "service": service,
            }

        # Multi-provider selection (Fix I6)
        has_live_llm = bool(settings.openai_api_key or settings.gemini_api_key or settings.anthropic_api_key or settings.nvidia_api_key)
        mode = "live" if has_live_llm else "replay"

        if sync:
            orchestrator = IncidentOrchestrator(mode=mode)
            crew_res, trace = orchestrator.run_crew(
                graph=graph,
                alert={"service": service, "text": alert_text, "severity": severity},
                scenario_id=scenario_id,
                auto_approve=False,
            )
            return {
                "status": "created",
                "incident_id": crew_res.get("incident_id"),
                "service": service,
                "crew_result": crew_res,
            }

        # Asynchronous 202 execution (R2)
        inc_id = f"inc_{uuid.uuid4().hex[:8]}"

        def _run_bg():
            orch = IncidentOrchestrator(mode=mode)
            orch.run_crew(
                graph=graph,
                alert={"service": service, "text": alert_text, "severity": severity},
                incident_id=inc_id,
                scenario_id=scenario_id,
                auto_approve=False,
            )

        background_tasks.add_task(_run_bg)
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "incident_id": inc_id,
                "service": service,
                "stream_url": f"/api/incidents/{inc_id}/stream",
                "message": f"Incident crew started for '{inc_id}' in background.",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook alert processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook alert processing failed: {str(e)}")


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


# ============================================================================
# M3: Scenario Simulator & Runbooks Endpoints
# ============================================================================

from pydantic import BaseModel
from fastapi import Depends
from app.scenarios.catalog import (
    list_scenarios,
    get_scenario,
    list_runbooks,
    get_runbook,
)
from app.scenarios.engine import (
    load_scenario,
    seed_historical_incidents,
)
from app.scenarios.outcomes import apply_intervention


class InterveneRequest(BaseModel):
    runbook_id: str


class LoadScenarioRequest(BaseModel):
    alert_ts: float | None = None


@app.get("/scenarios")
@app.get("/api/scenarios")
def api_list_scenarios(family: str | None = Query(default=None, description="Filter by scenario family")):
    """List available scenarios in the simulator catalog."""
    scenarios = list_scenarios(family=family)
    return {
        "count": len(scenarios),
        "family_filter": family,
        "scenarios": scenarios,
    }


@app.get("/scenarios/{scenario_id}")
@app.get("/api/scenarios/{scenario_id}")
def api_get_scenario(scenario_id: str):
    """Retrieve details for a specific scenario by ID."""
    sc = get_scenario(scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    return sc


@app.post("/scenarios/{scenario_id}/load")
@app.post("/api/scenarios/{scenario_id}/load")
def api_load_scenario(
    scenario_id: str,
    body: LoadScenarioRequest | None = None,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Load a simulated scenario into the active tenant graph.
    Creates Alert, MetricSnapshots, Deployments, and ArchitectureChanges flagged source='seeded'.
    """
    sc = get_scenario(scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    alert_ts = body.alert_ts if body else None
    try:
        result = load_scenario(graph=graph, scenario_id=scenario_id, alert_ts=alert_ts)
        return result
    except Exception as e:
        logger.error(f"Failed to load scenario '{scenario_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load scenario: {str(e)}")


@app.post("/scenarios/{scenario_id}/intervene")
@app.post("/api/scenarios/{scenario_id}/intervene")
def api_apply_intervention(
    scenario_id: str,
    req: InterveneRequest,
):
    """Execute a simulated runbook intervention against a scenario and return post-fix metrics."""
    try:
        outcome = apply_intervention(scenario_id=scenario_id, runbook_id=req.runbook_id)
        return outcome
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to apply intervention: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runbooks")
@app.get("/api/runbooks")
def api_list_runbooks():
    """List all available operational runbooks with dependency assumptions."""
    rbs = list_runbooks()
    return {
        "count": len(rbs),
        "runbooks": rbs,
    }


@app.post("/scenarios/seed-historical")
@app.post("/api/scenarios/seed-historical")
def api_seed_historical(
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Seed historical incidents into the tenant graph for episodic and outcome memory."""
    try:
        res = seed_historical_incidents(graph=graph)
        return res
    except Exception as e:
        logger.error(f"Failed to seed historical incidents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to seed historical incidents: {str(e)}")


# ============================================================================
# M4: Graph Tools & Execution Endpoints
# ============================================================================

from app.tools.registry import get_tool_schemas, execute_tool


class ToolExecuteRequest(BaseModel):
    arguments: dict[str, Any] = {}


@app.get("/tools")
@app.get("/api/tools")
def api_list_tools():
    """List all available M4 graph tools and their JSON schemas."""
    schemas = get_tool_schemas()
    return {
        "count": len(schemas),
        "tools": schemas,
    }


@app.post("/tools/{tool_name}/execute")
@app.post("/api/tools/{tool_name}/execute")
def api_execute_tool(
    tool_name: str,
    req: ToolExecuteRequest | None = None,
    graph: TenantGraph = Depends(get_current_tenant),
):
    args = req.arguments if req else {}
    try:
        result = execute_tool(name=tool_name, graph=graph, arguments=args)
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")


# ============================================================================
# M5: Hypothesis & Evidence Engine Endpoints
# ============================================================================

from app.hypotheses.engine import run_investigation


class InvestigateRequest(BaseModel):
    alerting_service: str
    alert_text: str = ""
    as_of: float | None = None
    incident_id: str | None = None
    persist: bool = True


@app.post("/hypotheses/investigate")
@app.post("/api/hypotheses/investigate")
def api_investigate_hypotheses(
    req: InvestigateRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Run the M5 graph-guided hypothesis & evidence engine pipeline.
    Generates competing hypotheses, gathers supporting and contradicting evidence,
    ranks with exponential decay, and evaluates sufficiency.
    """
    try:
        result, trace = run_investigation(
            graph=graph,
            alerting_service=req.alerting_service,
            alert_text=req.alert_text,
            as_of=req.as_of,
            incident_id=req.incident_id,
            persist=req.persist,
        )
        return {
            "data": result,
            "trace": trace.to_dict(),
        }
    except Exception as e:
        logger.error(f"Investigation failed for service '{req.alerting_service}': {e}")
        raise HTTPException(status_code=500, detail=f"Investigation failed: {str(e)}")


@app.post("/scenarios/{scenario_id}/investigate")
@app.post("/api/scenarios/{scenario_id}/investigate")
def api_investigate_scenario(
    scenario_id: str,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Run M5 hypothesis investigation against a loaded scenario."""
    sc = get_scenario(scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    alert = sc.get("alert", {})
    alert_svc = alert.get("service")
    if not alert_svc:
        raise HTTPException(status_code=400, detail="Scenario missing alert.service")

    alert_text = alert.get("text", "")
    try:
        result, trace = run_investigation(
            graph=graph,
            alerting_service=alert_svc,
            alert_text=alert_text,
            incident_id=f"inc_{scenario_id}",
            persist=True,
        )
        return {
            "scenario_id": scenario_id,
            "ground_truth": sc.get("ground_truth"),
            "data": result,
            "trace": trace.to_dict(),
        }
    except Exception as e:
        logger.error(f"Scenario investigation failed for '{scenario_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Scenario investigation failed: {str(e)}")


@app.get("/incidents/{incident_id}/hypotheses")
@app.get("/api/incidents/{incident_id}/hypotheses")
def api_get_incident_hypotheses(
    incident_id: str,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve persisted hypotheses and linked evidence for an incident from the graph."""
    cypher = """
    MATCH (i:Incident {id: $incident_id})-[:HAS_HYPOTHESIS]->(h:Hypothesis)
    OPTIONAL MATCH (h)-[:ABOUT]->(s:Service)
    OPTIONAL MATCH (h)-[r_sup:SUPPORTED_BY]->(e_sup:Evidence)
    OPTIONAL MATCH (h)-[r_con:CONTRADICTED_BY]->(e_con:Evidence)
    RETURN h.id AS id,
           h.statement AS statement,
           h.kind AS kind,
           h.service AS service,
           h.status AS status,
           h.evidence_score AS evidence_score,
           h.margin AS margin,
           h.formed_ts AS formed_ts,
           collect(DISTINCT {
               id: e_sup.id,
               type: e_sup.type,
               kind: e_sup.kind,
               summary: e_sup.summary,
               source_ref: e_sup.source_ref,
               observed_ts: e_sup.observed_ts,
               freshness: e_sup.freshness,
               weight: r_sup.weight
           }) AS supporting,
           collect(DISTINCT {
               id: e_con.id,
               type: e_con.type,
               kind: e_con.kind,
               summary: e_con.summary,
               source_ref: e_con.source_ref,
               observed_ts: e_con.observed_ts,
               freshness: e_con.freshness,
               weight: r_con.weight
           }) AS contradicting
    ORDER BY h.evidence_score DESC
    """
    res = graph.query(cypher, {"incident_id": incident_id})
    records = []
    if res and res.result_set:
        for row in res.result_set:
            hid, stmt, kind, svc, status, score, margin, formed, supp, con = row
            # Filter out null collect entries
            supp_clean = [e for e in (supp or []) if e.get("id")]
            con_clean = [e for e in (con or []) if e.get("id")]
            records.append({
                "id": hid,
                "statement": stmt,
                "kind": kind,
                "service": svc,
                "status": status,
                "evidence_score": float(score or 0.0),
                "margin": float(margin or 0.0),
                "formed_ts": float(formed or 0.0),
                "supporting_evidence": supp_clean,
                "contradicting_evidence": con_clean,
            })

    return {
        "incident_id": incident_id,
        "count": len(records),
        "hypotheses": records,
    }


# ============================================================================
# M6: Memory Layer Endpoints (Episodic, Semantic, Procedural, Outcomes, Recall)
# ============================================================================

from app.memory import (
    recall as memory_recall,
    record_observation,
    supersede_observation,
    get_known_facts,
    propose_intervention,
    record_observed_outcome,
    get_incident_interventions,
    check_applicability as check_runbook_applicability,
    close_incident,
)


class RecallRequest(BaseModel):
    alert_text: str
    services: list[str] = []
    as_of: float | None = None
    k: int = 5


class ObservationRequest(BaseModel):
    service: str
    text: str
    kind: str = "observed"
    confidence_basis: str = ""
    weight: float = 1.0
    incident_id: str | None = None


class SupersedeObservationRequest(BaseModel):
    service: str
    new_text: str
    kind: str = "observed"
    confidence_basis: str = ""
    weight: float = 1.0
    incident_id: str | None = None


class ProposeInterventionRequest(BaseModel):
    incident_id: str
    runbook_id: str
    description: str = ""
    predicted_outcome: str = "resolved"
    action_class: str = "needs_approval"
    hypothesis_id: str | None = None


class RecordOutcomeRequest(BaseModel):
    observed: str
    metrics_after: dict[str, Any] | None = None


class CloseIncidentRequest(BaseModel):
    winning_hypothesis_id: str
    steps_taken: list[str] = []
    tool_calls: list[str] = []
    affected_services: list[dict[str, str]] = []
    handled_by: str | None = None
    signature_text: str | None = None


@app.post("/memory/recall")
@app.post("/api/memory/recall")
def api_memory_recall(
    req: RecallRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Unified Memory Recall API.
    Synthesizes episodic, semantic, procedural, and outcome memory:
    returns similar incidents, recommended and rejected runbooks with applicability reasoning,
    and active semantic facts.
    """
    try:
        result, trace = memory_recall(
            graph=graph,
            alert_text=req.alert_text,
            services=req.services,
            as_of=req.as_of,
            k=req.k,
        )
        return {
            "data": result,
            "trace": trace.to_dict(),
        }
    except Exception as e:
        logger.error(f"Memory recall failed: {e}")
        raise HTTPException(status_code=500, detail=f"Memory recall failed: {str(e)}")


@app.post("/memory/observations")
@app.post("/api/memory/observations")
def api_record_observation(
    req: ObservationRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Record a semantic fact / observation about a service or incident."""
    try:
        obs = record_observation(
            graph=graph,
            service=req.service,
            text=req.text,
            kind=req.kind,
            confidence_basis=req.confidence_basis,
            incident_id=req.incident_id,
            weight=req.weight,
        )
        return obs
    except Exception as e:
        logger.error(f"Failed to record observation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record observation: {str(e)}")


@app.post("/memory/observations/{observation_id}/supersede")
@app.post("/api/memory/observations/{observation_id}/supersede")
def api_supersede_observation(
    observation_id: str,
    req: SupersedeObservationRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Contradict an old fact by superseding it with a new observation. Never deletes history."""
    try:
        result = supersede_observation(
            graph=graph,
            old_observation_id=observation_id,
            service=req.service,
            new_text=req.new_text,
            kind=req.kind,
            confidence_basis=req.confidence_basis,
            weight=req.weight,
            incident_id=req.incident_id,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to supersede observation '{observation_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to supersede observation: {str(e)}")


@app.get("/memory/facts")
@app.get("/api/memory/facts")
def api_get_known_facts(
    service: str | None = Query(default=None, description="Optional service filter"),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve active semantic facts with decay-weighted confidence."""
    facts = get_known_facts(graph=graph, service=service)
    return {
        "service_filter": service,
        "count": len(facts),
        "facts": facts,
    }


@app.post("/memory/interventions")
@app.post("/api/memory/interventions")
def api_propose_intervention(
    req: ProposeInterventionRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Propose an operational fix / intervention with predicted outcome stored separately."""
    try:
        intv = propose_intervention(
            graph=graph,
            incident_id=req.incident_id,
            runbook_id=req.runbook_id,
            description=req.description,
            predicted_outcome=req.predicted_outcome,
            action_class=req.action_class,
            hypothesis_id=req.hypothesis_id,
        )
        return intv
    except Exception as e:
        logger.error(f"Failed to propose intervention: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to propose intervention: {str(e)}")


@app.post("/memory/interventions/{intervention_id}/outcome")
@app.post("/api/memory/interventions/{intervention_id}/outcome")
def api_record_outcome(
    intervention_id: str,
    req: RecordOutcomeRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Record the observed outcome of an intervention and update runbook procedural memory."""
    try:
        out = record_observed_outcome(
            graph=graph,
            intervention_id=intervention_id,
            observed=req.observed,
            metrics_after=req.metrics_after,
        )
        return out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to record outcome for '{intervention_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record outcome: {str(e)}")


@app.get("/memory/incidents/{incident_id}/interventions")
@app.get("/api/memory/incidents/{incident_id}/interventions")
def api_get_incident_interventions(
    incident_id: str,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Get all proposed interventions, observed outcomes, and prediction errors for an incident."""
    intvs = get_incident_interventions(graph=graph, incident_id=incident_id)
    return {
        "incident_id": incident_id,
        "count": len(intvs),
        "interventions": intvs,
    }


@app.get("/memory/applicability/{runbook_id}")
@app.get("/api/memory/applicability/{runbook_id}")
def api_check_applicability(
    runbook_id: str,
    as_of: float | None = Query(default=None, description="Optional temporal timestamp"),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Check whether a runbook's assumed dependency pairs still hold in the current graph."""
    res, trace = check_runbook_applicability(graph=graph, runbook_id=runbook_id, as_of=as_of)
    return {
        "data": res,
        "trace": trace.to_dict(),
    }


@app.post("/memory/incidents/{incident_id}/close")
@app.post("/api/memory/incidents/{incident_id}/close")
def api_close_incident(
    incident_id: str,
    req: CloseIncidentRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Close an incident and commit its complete episodic record and similarity links to graph memory."""
    try:
        closed = close_incident(
            graph=graph,
            incident_id=incident_id,
            winning_hypothesis_id=req.winning_hypothesis_id,
            steps_taken=req.steps_taken,
            tool_calls=req.tool_calls,
            affected_services=req.affected_services,
            handled_by=req.handled_by,
            signature_text=req.signature_text,
        )
        return closed
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to close incident '{incident_id}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to close incident: {str(e)}")


# ============================================================================
# M7: Agents and Graph-Native Collaboration API
# ============================================================================

from app.agents import (
    IncidentOrchestrator,
    event_bus,
    get_blackboard_state,
    approve_action as approve_agent_action,
    reject_action as reject_agent_action,
    get_pending_actions,
)


class IncidentRunRequest(BaseModel):
    alert: dict[str, Any]
    incident_id: str | None = None
    scenario_id: str | None = None
    as_of: float | None = None
    mode: str = "replay"
    auto_approve: bool = False
    sync: bool | None = None


class ActionApprovalRequest(BaseModel):
    approver: str = "operator"
    scenario_id: str | None = None
    as_of: float | None = None


class ActionRejectionRequest(BaseModel):
    reason: str = "Rejected by operator"
    rejector: str = "operator"


@app.get("/incidents")
@app.get("/api/incidents")
def api_list_incidents(
    limit: int = Query(default=20, ge=1, le=100),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """List recent incidents for the current tenant."""
    cypher = """
    MATCH (i:Incident)
    RETURN i.id AS id, i.title AS title, i.status AS status, i.service_name AS service, i.opened_ts AS opened_ts, i.resolved_ts AS resolved_ts
    ORDER BY COALESCE(i.opened_ts, 0.0) DESC
    LIMIT $limit
    """
    res = graph.query(cypher, {"limit": limit})
    incidents = []
    if res and res.result_set:
        for r in res.result_set:
            incidents.append({
                "id": r[0],
                "title": r[1] or r[0],
                "status": r[2] or "unknown",
                "service": r[3] or "",
                "opened_ts": float(r[4] or 0.0),
                "resolved_ts": float(r[5]) if r[5] is not None else None,
            })
    return {
        "tenant_id": graph.tenant_id,
        "count": len(incidents),
        "incidents": incidents,
    }


@app.post("/incidents")
@app.post("/api/incidents")
def api_run_incident_crew(
    req: IncidentRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Run the 4-agent Ripple crew (Triage, Investigator, Responder, Verifier) over the graph blackboard."""
    try:
        is_async = (
            req.sync is False
            or request.query_params.get("async") == "true"
            or request.headers.get("x-async") == "true"
        )
        inc_id = req.incident_id or f"inc_{uuid.uuid4().hex[:8]}"

        if is_async:
            def _run_bg():
                orchestrator = IncidentOrchestrator(mode=req.mode)
                orchestrator.run_crew(
                    graph=graph,
                    alert=req.alert,
                    incident_id=inc_id,
                    scenario_id=req.scenario_id,
                    as_of=req.as_of,
                    auto_approve=req.auto_approve,
                )

            background_tasks.add_task(_run_bg)
            return JSONResponse(
                status_code=202,
                content={
                    "status": "accepted",
                    "incident_id": inc_id,
                    "stream_url": f"/api/incidents/{inc_id}/stream",
                    "message": f"Incident crew started for '{inc_id}' in background.",
                },
            )

        orchestrator = IncidentOrchestrator(mode=req.mode)
        result, trace = orchestrator.run_crew(
            graph=graph,
            alert=req.alert,
            incident_id=inc_id,
            scenario_id=req.scenario_id,
            as_of=req.as_of,
            auto_approve=req.auto_approve,
        )
        return {
            "status": "success",
            "data": result,
            "trace": trace.to_dict(),
        }
    except Exception as e:
        logger.error(f"Incident crew execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Incident crew execution failed: {str(e)}")


@app.get("/incidents/{incident_id}")
@app.get("/api/incidents/{incident_id}")
def api_get_incident(
    incident_id: str,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve complete incident state and blackboard (tasks, runs, hypotheses, evidence, conflicts, actions)."""
    bb_state = get_blackboard_state(graph, incident_id)
    pending_actions = get_pending_actions(graph, incident_id)

    # Incident header info
    inc_res = graph.query(
        "MATCH (i:Incident {id: $iid}) RETURN i.id AS id, i.title AS title, i.status AS status, i.opened_ts AS opened_ts, i.resolved_ts AS resolved_ts",
        {"iid": incident_id},
    )
    inc_info = {}
    if inc_res and inc_res.result_set:
        r = inc_res.result_set[0]
        inc_info = {"id": r[0], "title": r[1], "status": r[2], "opened_ts": r[3], "resolved_ts": r[4]}

    return {
        "incident": inc_info,
        "blackboard": bb_state,
        "pending_actions": pending_actions,
    }


@app.get("/incidents/{incident_id}/stream")
@app.get("/api/incidents/{incident_id}/stream")
async def api_stream_incident_events(
    incident_id: str,
    tenant: str = Query(default="storefront", description="Tenant graph ID"),
    last_event_id: str | None = Query(default=None, description="Last-Event-ID query fallback"),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """Server-Sent Events (SSE) stream of live agent timeline events."""
    effective_last_id = last_event_id_header or last_event_id

    async def sse_generator():
        async for ev in event_bus.subscribe(incident_id, last_event_id=effective_last_id):
            ev_id = ev.get("id", "")
            ev_type = ev.get("event", "message")
            yield f"id: {ev_id}\nevent: {ev_type}\ndata: {json.dumps(ev)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Tenant": tenant,
        },
    )


@app.post("/incidents/{incident_id}/actions/{action_id}/approve")
@app.post("/api/incidents/{incident_id}/actions/{action_id}/approve")
def api_approve_incident_action(
    incident_id: str,
    action_id: str,
    req: ActionApprovalRequest = ActionApprovalRequest(),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Approve a proposed action awaiting human approval and resume the crew by running the Verifier Agent."""
    try:
        orchestrator = IncidentOrchestrator(mode="replay")
        result, trace = orchestrator.approve_and_verify(
            graph=graph,
            incident_id=incident_id,
            action_id=action_id,
            approver=req.approver,
            scenario_id=req.scenario_id,
            as_of=req.as_of,
        )
        return {
            "status": "success",
            "data": result,
            "trace": trace.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Action approval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Action approval failed: {str(e)}")


@app.post("/incidents/{incident_id}/actions/{action_id}/reject")
@app.post("/api/incidents/{incident_id}/actions/{action_id}/reject")
def api_reject_incident_action(
    incident_id: str,
    action_id: str,
    req: ActionRejectionRequest = ActionRejectionRequest(),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Reject a proposed action awaiting human approval."""
    try:
        res = reject_agent_action(
            graph=graph,
            incident_id=incident_id,
            action_id=action_id,
            reason=req.reason,
            rejector=req.rejector,
        )
        return {
            "status": "success",
            "data": res,
        }
    except Exception as e:
        logger.error(f"Action rejection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Action rejection failed: {str(e)}")


class DirectCloseIncidentRequest(BaseModel):
    winning_hypothesis_id: str | None = None
    steps_taken: list[str] = []
    tool_calls: list[str] = []
    affected_services: list[dict[str, str]] = []
    handled_by: str | None = None
    signature_text: str | None = None
    observed_outcome: str = "resolved"


@app.post("/incidents/{incident_id}/close")
@app.post("/api/incidents/{incident_id}/close")
def api_close_incident_direct(
    incident_id: str,
    req: DirectCloseIncidentRequest = DirectCloseIncidentRequest(),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Close incident, verify outcome of any unclosed interventions, and write episodic memory."""
    # Find winning hypothesis if not explicitly supplied
    winning_id = req.winning_hypothesis_id
    if not winning_id:
        hyp_res = graph.query(
            "MATCH (i:Incident {id: $iid})-[:HAS_HYPOTHESIS]->(h:Hypothesis) RETURN h.id ORDER BY h.evidence_score DESC LIMIT 1",
            {"iid": incident_id},
        )
        if hyp_res and hyp_res.result_set:
            winning_id = hyp_res.result_set[0][0]
        else:
            any_hyp = graph.query("MATCH (h:Hypothesis) RETURN h.id ORDER BY h.evidence_score DESC LIMIT 1")
            if any_hyp and any_hyp.result_set:
                winning_id = any_hyp.result_set[0][0]
            else:
                graph.query("MERGE (h:Hypothesis {id: $hid}) SET h.statement = 'Direct incident resolution', h.service = 'unknown', h.evidence_score = 1.0", {"hid": f"hyp_{incident_id}"})
                winning_id = f"hyp_{incident_id}"

    # Verify and close any unverified interventions
    unverified_res = graph.query(
        "MATCH (i:Incident {id: $iid})-[:HAS_INTERVENTION]->(intv:Intervention) WHERE NOT (intv)-[:VALIDATED_BY]->(:Outcome) RETURN intv.id",
        {"iid": incident_id},
    )
    if unverified_res and unverified_res.result_set:
        for u_row in unverified_res.result_set:
            intv_id = u_row[0]
            record_observed_outcome(graph=graph, intervention_id=intv_id, observed=req.observed_outcome)

    res = close_incident(
        graph=graph,
        incident_id=incident_id,
        winning_hypothesis_id=winning_id,
        steps_taken=req.steps_taken,
        tool_calls=req.tool_calls,
        affected_services=req.affected_services,
        handled_by=req.handled_by or "responder_agent",
        signature_text=req.signature_text,
    )
    return res


# ============================================================================
# M8: Company-Brain Q&A API
# ============================================================================

from app.brain import (
    ask_brain,
    get_qa_history,
    check_docs_freshness,
)


class AskBrainRequest(BaseModel):
    question: str
    mode: str = "replay"


@app.post("/ask")
@app.post("/api/ask")
def api_ask_brain(
    req: AskBrainRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Company-Brain Q&A: Natural language questions answered from the graph with sources."""
    try:
        result, trace = ask_brain(
            graph=graph,
            question=req.question,
            tenant_id=graph.tenant_id,
            mode=req.mode,
        )
        return {
            "status": "success",
            "data": result,
            "trace": trace.to_dict(),
        }
    except Exception as e:
        logger.error(f"Company-brain Q&A query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Company-brain Q&A query failed: {str(e)}")


@app.get("/ask/history")
@app.get("/api/ask/history")
def api_get_brain_history(
    limit: int = Query(default=20, ge=1, le=100),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve persistent conversation history for this tenant."""
    history = get_qa_history(graph=graph, tenant_id=graph.tenant_id, limit=limit)
    return {
        "tenant_id": graph.tenant_id,
        "count": len(history),
        "history": history,
    }


@app.get("/brain/freshness")
@app.get("/api/brain/freshness")
def api_check_brain_freshness(
    service: str | None = Query(default=None, description="Optional service filter"),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Check documentation freshness against subsequent merged pull requests."""
    stale_docs, trace = check_docs_freshness(graph=graph, service=service)
    return {
        "count": len(stale_docs),
        "stale_docs": stale_docs,
        "trace": trace.to_dict(),
    }


# ============================================================================
# M9: Counterfactual Engine API
# ============================================================================

from app.counterfactual import compute_counterfactual, assess_uncertainty


class CounterfactualRequest(BaseModel):
    observed_incident_id: str
    hypothetical_service: str
    as_of: str | float | None = "incident_time"
    compare_with_now: bool = True


@app.post("/counterfactual")
@app.post("/api/counterfactual")
def api_counterfactual(
    req: CounterfactualRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Compute what-if differential analysis comparing actual incident blast radius
    against what would have happened if a hypothetical service had failed instead.
    Returns structured diff (only_observed, only_hypothetical, both), paths,
    PageRank critical owners, uncertainty bounds, and time-travel comparison.
    """
    try:
        data, trace = compute_counterfactual(
            graph=graph,
            observed_incident_id=req.observed_incident_id,
            hypothetical_service=req.hypothetical_service,
            as_of=req.as_of,
            compare_with_now=req.compare_with_now,
        )
        return {
            "status": "success",
            "data": data,
            "trace": trace.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Counterfactual simulation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Counterfactual simulation failed: {str(e)}")


@app.get("/counterfactual/uncertainty")
@app.get("/api/counterfactual/uncertainty")
def api_counterfactual_uncertainty(
    services: str = Query(description="Comma-separated list of service names"),
    as_of: float | None = Query(default=None, description="Optional timestamp for as-of evaluation"),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Assess uncertainty, unverified edges, and lower-bound warnings for a set of services."""
    try:
        svc_list = [s.strip() for s in services.split(",") if s.strip()]
        data, trace = assess_uncertainty(graph=graph, services=svc_list, as_of=as_of)
        return {
            "status": "success",
            "data": data,
            "trace": trace.to_dict(),
        }
    except Exception as e:
        logger.error(f"Uncertainty assessment failed: {e}")
        raise HTTPException(status_code=500, detail=f"Uncertainty assessment failed: {str(e)}")


# ============================================================================
# M10: Provenance, Explainability, Inspector, and Replay API
# ============================================================================

from app.trace import (
    get_step_inspection,
    get_why_replay,
    get_subgraph,
    get_evidence_provenance,
    GLOBAL_TRACE_REGISTRY,
)


class WhyReplayRequest(BaseModel):
    trace: dict[str, Any] | None = None
    steps: list[dict[str, Any]] | None = None
    step_ids: list[str] | None = None


@app.get("/inspect/{trace_step_id}")
@app.get("/api/inspect/{trace_step_id}")
def api_inspect_step(
    trace_step_id: str,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve full provenance for a single trace step:
    Exact Cypher, parameters, returned rows, and touched subgraph for Inspector Drawer.
    """
    inspection = get_step_inspection(step_id=trace_step_id, graph=graph)
    if not inspection:
        raise HTTPException(
            status_code=404,
            detail=f"Trace step '{trace_step_id}' not found in active session registry.",
        )
    return {
        "status": "success",
        "data": inspection,
    }


@app.post("/inspect/replay")
@app.post("/api/inspect/replay")
def api_inspect_replay(
    req: WhyReplayRequest,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Generate sequential 'Why' Replay animation stepping through the trace in order.
    Returns active highlights, delta additions, and cumulative subgraphs at each step.
    """
    steps_payload = []
    if req.trace and "steps" in req.trace:
        steps_payload = req.trace["steps"]
    elif req.steps:
        steps_payload = req.steps
    elif req.step_ids:
        for sid in req.step_ids:
            s = GLOBAL_TRACE_REGISTRY.get(sid)
            if s:
                steps_payload.append(s.to_dict())

    replay_frames = get_why_replay(steps_payload)
    return {
        "status": "success",
        "total_steps": len(replay_frames),
        "frames": replay_frames,
    }


@app.get("/graph/subgraph")
@app.get("/api/graph/subgraph")
def api_get_subgraph(
    nodes: str | None = Query(default=None, description="Comma-separated list of node IDs to focus on"),
    service: str | None = Query(default=None, description="Center service name for neighborhood"),
    radius: int = Query(default=1, ge=1, le=4, description="Neighborhood traversal radius"),
    as_of: float | None = Query(default=None, description="Optional timestamp for temporal graph state"),
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve styled nodes and edges for GraphCanvas and Inspector Drawer."""
    node_ids = [n.strip() for n in nodes.split(",") if n.strip()] if nodes else None
    data = get_subgraph(
        graph=graph,
        node_ids=node_ids,
        center_service=service,
        radius=radius,
        as_of=as_of,
    )
    return {
        "status": "success",
        "data": data,
    }


@app.get("/inspect/evidence/{evidence_id}")
@app.get("/api/inspect/evidence/{evidence_id}")
def api_inspect_evidence(
    evidence_id: str,
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve evidence provenance: source, timestamp, freshness, and observed/inferred badge."""
    records = get_evidence_provenance(graph=graph, evidence_id_or_ids=evidence_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"Evidence '{evidence_id}' not found.")
    return {
        "status": "success",
        "data": records[0],
    }


# ============================================================================
# M11: Backend API & Benchmark Evaluation Endpoints
# ============================================================================

from app.memory.stats import get_memory_stats
from app.benchmark import run_benchmark, get_latest_benchmark_report


class BenchmarkRunApiRequest(BaseModel):
    scenarios: list[str] | None = None
    modes: list[str] | None = None
    mode: str = "replay"


@app.get("/memory/stats")
@app.get("/api/memory/stats")
def api_get_memory_stats(
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Retrieve episodic counts, semantic facts status, runbook procedural success rates, and learning curve progression."""
    try:
        stats = get_memory_stats(graph)
        return {
            "status": "success",
            "data": stats,
        }
    except Exception as e:
        logger.error(f"Failed to compile memory stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compile memory stats: {str(e)}")


@app.post("/benchmark/run")
@app.post("/api/benchmark/run")
def api_run_benchmark(
    req: BenchmarkRunApiRequest = BenchmarkRunApiRequest(),
):
    """Execute pre-registered memory-on vs memory-off benchmark across scenarios."""
    try:
        results = run_benchmark(
            scenarios=req.scenarios,
            modes=req.modes,
            mode=req.mode,
        )
        return {
            "status": "success",
            "data": results,
        }
    except Exception as e:
        logger.error(f"Benchmark run failed: {e}")
        raise HTTPException(status_code=500, detail=f"Benchmark run failed: {str(e)}")


@app.get("/benchmark/report")
@app.get("/api/benchmark/report")
def api_get_benchmark_report():
    """Retrieve latest pre-registered benchmark results and formatted Markdown report."""
    try:
        report = get_latest_benchmark_report()
        return report
    except Exception as e:
        logger.error(f"Failed to fetch benchmark report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch benchmark report: {str(e)}")


# ============================================================================
# Live Telemetry, Target Fault Injection, GitHub Sync, & Topology Discovery
# ============================================================================

from app.adapters.demo_target import (
    break_service,
    restore_service,
    get_service_state,
    generate_prometheus_metrics_text,
)
from app.ingest.github import load_github_data, fetch_real_github_api
from app.adapters.topology import discover_topology_from_environment, apply_discovered_topology


@app.get("/metrics")
def api_prometheus_metrics():
    """Prometheus exposition format endpoint exposing live metrics for all services."""
    text = generate_prometheus_metrics_text()
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/api/telemetry/demo/break")
def api_break_demo_service(
    service: str = Query(..., description="Target service name"),
    error_type: str = Query(default="latency_p95", description="Error type: latency_p95 or error_rate"),
):
    """Fault injection switch for live demo target."""
    break_service(service, error_type)
    return {"status": "broken", "service": service, "error_type": error_type}


@app.post("/api/telemetry/demo/restore")
def api_restore_demo_service(
    service: str = Query(..., description="Target service name"),
):
    """Restore service health in live demo target."""
    restore_service(service)
    return {"status": "restored", "service": service}


@app.get("/api/telemetry/demo/state")
def api_get_demo_service_state(
    service: str | None = Query(default=None, description="Optional service name"),
):
    """Retrieve current fault injection state for demo services."""
    return {"states": get_service_state(service)}


@app.post("/api/github/sync")
def api_github_sync(
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Trigger live GitHub repository synchronization."""
    repo = settings.github_repo
    token = settings.github_token
    real_data = fetch_real_github_api(repo=repo, token=token) if token else None
    res = load_github_data(graph=graph)
    return {
        "status": "success",
        "repo": repo,
        "is_real": real_data is not None and real_data.get("source") == "real",
        "synced": res,
    }


@app.post("/api/topology/discover")
def api_discover_topology(
    graph: TenantGraph = Depends(get_current_tenant),
):
    """Discover topology from environment and container declarations, updating tenant graph."""
    edges = discover_topology_from_environment()
    apply_discovered_topology(graph, edges)
    return {
        "status": "success",
        "discovered_edges_count": len(edges),
        "edges": [
            {"source": e.source_service, "target": e.target_service, "protocol": e.protocol}
            for e in edges
        ],
    }


@app.get("/api/system/status")
def api_system_status():
    """System status and LLM provider health check."""
    llm_status = "live" if settings.openai_api_key or settings.gemini_api_key or settings.anthropic_api_key else "degraded"
    return {
        "llm_provider": settings.llm_provider,
        "llm_status": llm_status,
        "telemetry_source": settings.telemetry_source,
        "embeddings_backend": settings.embeddings_backend,
        "github_repo": settings.github_repo,
    }











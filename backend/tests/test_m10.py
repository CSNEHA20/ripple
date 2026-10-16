import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.trace import (
    TraceStep,
    Trace,
    GLOBAL_TRACE_REGISTRY,
    get_step_inspection,
    get_why_replay,
    get_subgraph,
    get_evidence_provenance,
)
from app.tools.blast_radius import blast_radius
from app.tools.paths import path_between
from app.scenarios.engine import seed_historical_incidents


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant for M10 Provenance & Inspector tests."""
    tenant_id = "storefront_m10_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def test_trace_step_creation_and_registration():
    """Verify TraceStep creation with auto-generated unique ID, params, rows,
    and automatic registration in GLOBAL_TRACE_REGISTRY.
    """
    step = TraceStep(
        tool="test_tool",
        cypher="MATCH (s:Service {name: $name}) RETURN s",
        params={"name": "paymentservice"},
        node_ids=["paymentservice", "checkoutservice"],
        edge_ids=["checkoutservice->paymentservice"],
        summary="Found 1 service",
        rows_count=1,
        rows=[["paymentservice", "tier-1"]],
        duration_ms=4.2,
    )

    assert step.id.startswith("step_")
    assert step.rows_count == 1
    assert step.rows == [["paymentservice", "tier-1"]]

    # Adding step to a Trace automatically registers it in the registry
    trace = Trace()
    trace.add_step(step)

    registered = GLOBAL_TRACE_REGISTRY.get(step.id)
    assert registered is not None
    assert registered.id == step.id
    assert registered.tool == "test_tool"
    assert registered.cypher == "MATCH (s:Service {name: $name}) RETURN s"
    assert registered.params == {"name": "paymentservice"}


def test_trace_merge_and_node_edge_tracking():
    """Verify Trace accumulates steps and maintains unique set of visited nodes and edges."""
    step1 = TraceStep(
        tool="tool1",
        cypher="MATCH (a) RETURN a",
        node_ids=["node_a", "node_b"],
        edge_ids=["node_a->node_b"],
    )
    step2 = TraceStep(
        tool="tool2",
        cypher="MATCH (b)->(c) RETURN b, c",
        node_ids=["node_b", "node_c"],
        edge_ids=["node_b->node_c"],
    )

    trace1 = Trace()
    trace1.add_step(step1)

    trace2 = Trace()
    trace2.add_step(step2)

    trace1.merge(trace2)

    assert len(trace1.steps) == 2
    # Verify node and edge uniqueness
    assert trace1.nodes == ["node_a", "node_b", "node_c"]
    assert trace1.edges == ["node_a->node_b", "node_b->node_c"]

    d = trace1.to_dict()
    assert d["total_steps"] == 2
    assert len(d["steps"]) == 2
    assert "node_a" in d["nodes"]


def test_step_inspector_and_query_retrieval(seeded_tenant):
    """Verify get_step_inspection returns exact Cypher, parameters, returned rows,
    and visual subgraph representation for the Inspector Drawer.
    """
    # Run a real tool
    res = blast_radius(seeded_tenant, "paymentservice", max_depth=2)
    assert len(res.trace.steps) >= 1
    target_step = res.trace.steps[0]

    # Inspect step
    inspection = get_step_inspection(target_step.id, graph=seeded_tenant)
    assert inspection is not None
    assert inspection["id"] == target_step.id
    assert inspection["tool"] == "blast_radius"
    assert "MATCH (failed:Service" in inspection["cypher"]
    assert inspection["params"]["service"] == "paymentservice"
    assert len(inspection["rows"]) > 0
    assert "subgraph" in inspection

    subgraph = inspection["subgraph"]
    assert "nodes" in subgraph
    assert "edges" in subgraph
    node_ids = {n["id"] for n in subgraph["nodes"]}
    assert "paymentservice" in node_ids
    # Verify node visual styling
    payment_node = next(n for n in subgraph["nodes"] if n["id"] == "paymentservice")
    assert "color" in payment_node
    assert payment_node["label"] == "Service"


def test_why_replay_frame_sequencing(seeded_tenant):
    """Verify get_why_replay creates an ordered progression of replay frames
    with active highlights, delta additions, and cumulative subgraphs.
    """
    t1 = blast_radius(seeded_tenant, "paymentservice", max_depth=2).trace
    t2 = path_between(seeded_tenant, "frontend", "paymentservice").trace

    master_trace = Trace()
    master_trace.merge(t1)
    master_trace.merge(t2)
    assert len(master_trace.steps) >= 2

    frames = get_why_replay(master_trace)
    assert len(frames) == len(master_trace.steps)

    for i, frame in enumerate(frames):
        assert frame["step_index"] == i + 1
        assert frame["total_steps"] == len(frames)
        assert len(frame["active_nodes"]) > 0
        assert len(frame["cumulative_nodes"]) >= len(frame["active_nodes"])
        assert 0.0 < frame["progress_percent"] <= 100.0

    # Frame 1 cumulative nodes must be a subset of the final frame's cumulative nodes
    first_cum = set(frames[0]["cumulative_nodes"])
    last_cum = set(frames[-1]["cumulative_nodes"])
    assert first_cum.issubset(last_cum)


def test_subgraph_extraction_by_nodes_and_center(seeded_tenant):
    """Verify get_subgraph extracts styled visual topology by node IDs, center service, and baseline."""
    # 1. By node IDs
    sub_nodes = get_subgraph(seeded_tenant, node_ids=["frontend", "paymentservice", "checkoutservice"])
    assert len(sub_nodes["nodes"]) >= 3
    node_map = {n["id"]: n for n in sub_nodes["nodes"]}
    assert "frontend" in node_map
    assert "paymentservice" in node_map
    assert node_map["frontend"]["color"] == "#3b82f6"  # Blue for service

    # 2. By center service with radius
    sub_center = get_subgraph(seeded_tenant, center_service="cartservice", radius=1)
    assert len(sub_center["nodes"]) >= 2
    c_ids = {n["id"] for n in sub_center["nodes"]}
    assert "cartservice" in c_ids

    # 3. Baseline topology
    sub_base = get_subgraph(seeded_tenant)
    assert len(sub_base["nodes"]) >= 10
    assert len(sub_base["edges"]) >= 10


def test_evidence_provenance_retrieval(seeded_tenant):
    """Verify get_evidence_provenance retrieves complete source lineage, timestamps,
    freshness, and observed/inferred badge for evidence items.
    """
    ev_id = "ev_test_metric_p95_01"
    hyp_id = "hyp_test_m10_01"

    # Create test Evidence and Hypothesis
    seeded_tenant.query(
        """
        MERGE (h:Hypothesis {id: $hyp_id, statement: 'Test Hypothesis'})
        MERGE (e:Evidence {id: $ev_id})
        SET e.kind = 'observed',
            e.type = 'metric',
            e.summary = 'Latency exceeded 2500ms on paymentservice',
            e.source_ref = 'snap_metric_pay_01',
            e.observed_ts = 1700001000.0,
            e.freshness = 0.92,
            e.weight = 2.5
        MERGE (h)-[r:SUPPORTED_BY {weight: 2.5}]->(e)
        """,
        {"ev_id": ev_id, "hyp_id": hyp_id},
    )

    records = get_evidence_provenance(seeded_tenant, [ev_id])
    assert len(records) == 1
    rec = records[0]

    assert rec["id"] == ev_id
    assert rec["kind"] == "observed"
    assert rec["type"] == "metric"
    assert rec["source_ref"] == "snap_metric_pay_01"
    assert rec["observed_ts"] == 1700001000.0
    assert rec["freshness"] == 0.92
    assert rec["weight"] == 2.5
    assert len(rec["linked_hypotheses"]) == 1
    assert rec["linked_hypotheses"][0]["hypothesis_id"] == hyp_id


def test_api_m10_endpoints(seeded_tenant):
    """Test FastAPI inspector, replay, subgraph, and evidence provenance API endpoints."""
    client = TestClient(app)
    headers = {"X-Tenant": seeded_tenant.tenant_id}

    # 1. Generate a real trace step via tool call
    res = blast_radius(seeded_tenant, "cartservice", max_depth=2)
    step_id = res.trace.steps[0].id

    # 2. GET /inspect/{trace_step_id}
    resp1 = client.get(f"/inspect/{step_id}", headers=headers)
    assert resp1.status_code == 200
    inspect_data = resp1.json()["data"]
    assert inspect_data["id"] == step_id
    assert inspect_data["tool"] == "blast_radius"
    assert "cypher" in inspect_data
    assert "params" in inspect_data
    assert "rows" in inspect_data
    assert "subgraph" in inspect_data

    # 3. GET /inspect/nonexistent -> 404
    resp_404 = client.get("/inspect/step_nonexistent_xyz", headers=headers)
    assert resp_404.status_code == 404

    # 4. POST /inspect/replay
    resp2 = client.post(
        "/inspect/replay",
        json={"trace": res.trace.to_dict()},
        headers=headers,
    )
    assert resp2.status_code == 200
    replay_json = resp2.json()
    assert replay_json["status"] == "success"
    assert replay_json["total_steps"] >= 1
    assert len(replay_json["frames"]) >= 1

    # 5. GET /graph/subgraph
    resp3 = client.get("/graph/subgraph?nodes=frontend,cartservice", headers=headers)
    assert resp3.status_code == 200
    sub_json = resp3.json()["data"]
    assert "nodes" in sub_json
    assert "edges" in sub_json
    assert sub_json["total_nodes"] >= 2

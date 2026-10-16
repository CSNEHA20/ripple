import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all
from app.scenarios.engine import seed_historical_incidents
from app.brain.ask import (
    ask_brain,
    get_qa_history,
    classify_intent,
    check_read_only_cypher,
)
from app.brain.freshness import check_docs_freshness


@pytest.fixture(scope="module")
def seeded_tenant():
    """Setup a dedicated test tenant with full docs, decisions, and historical incidents."""
    tenant_id = "storefront_m8_test"
    graph = TenantGraph(tenant_id)
    graph.clear()
    bootstrap_tenant_all(tenant_id)
    seed_historical_incidents(graph, base_ts=1700000000.0)
    yield graph
    graph.delete()


def test_intent_classification():
    """Verify natural language question intent classifier."""
    assert classify_intent("Who owns the payment service and who actually knows it?") == "ownership"
    assert classify_intent("Why did we choose Valkey instead of Redis?") == "lineage"
    assert classify_intent("What breaks if currency service goes down?") == "impact"
    assert classify_intent("Which docs describing checkout might be out of date?") == "freshness"
    assert classify_intent("Has rb_restart ever failed, and when?") == "outcome_history"
    assert classify_intent("Tell me about system deployment procedures") == "free_form"


def test_read_only_cypher_guardrail():
    """Verify guardrail rejects mutating Cypher and accepts read-only queries."""
    assert check_read_only_cypher("MATCH (s:Service) RETURN s.name") is True
    assert check_read_only_cypher("MATCH (s:Service)-[:DEPENDS_ON]->(d) RETURN s, d") is True
    assert check_read_only_cypher("MATCH (s:Service) CREATE (s)-[:TEST]->(x)") is False
    assert check_read_only_cypher("MATCH (s:Service) DELETE s") is False
    assert check_read_only_cypher("MATCH (s:Service) SET s.name = 'hacked'") is False
    assert check_read_only_cypher("MERGE (s:Service {name: 'fake'})") is False
    assert check_read_only_cypher("DROP INDEX ON :Service(name)") is False


def test_ownership_and_who_knows(seeded_tenant):
    """Target 1: 'Who owns the payment service and who actually knows it?'"""
    res, trace = ask_brain(
        graph=seeded_tenant,
        question="Who owns the payment service and who actually knows it?",
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    assert res["intent"] == "ownership"
    assert "paymentservice" in res["answer"].lower()
    assert len(res["sources"]) >= 1

    # Check sources contain Service or Person
    source_types = {s.get("type") for s in res["sources"]}
    assert "Service" in source_types or "Person" in source_types
    assert len(trace.steps) >= 1


def test_decision_lineage_and_supersedes(seeded_tenant):
    """Target 2: 'Why did we choose Valkey?' and supersedes verification.
    Superseded decisions must be surfaced as superseded, never silently used.
    """
    # 1. Active decision query
    res_valkey, trace1 = ask_brain(
        graph=seeded_tenant,
        question="Why did we choose Valkey for cart session storage?",
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    assert res_valkey["intent"] == "lineage"
    assert len(res_valkey["sources"]) >= 1
    source_ids = [s["id"] for s in res_valkey["sources"]]
    assert any("valkey" in sid.lower() for sid in source_ids)

    # 2. Superseded decision query: MUST be surfaced as superseded!
    res_redis, trace2 = ask_brain(
        graph=seeded_tenant,
        question="Why did we choose standalone Redis for cart storage?",
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    assert res_redis["intent"] == "lineage"
    assert res_redis["is_superseded"] is True
    assert "superseded" in res_redis["answer"].lower()


def test_impact_blast_radius(seeded_tenant):
    """Target 3: 'What breaks if currency service goes down?'"""
    res, trace = ask_brain(
        graph=seeded_tenant,
        question="What breaks if currency service goes down?",
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    assert res["intent"] == "impact"
    assert res["raw_data"]["failing_service"] == "currencyservice"
    assert res["raw_data"]["total_impacted"] >= 1
    assert "currencyservice" in res["answer"].lower()
    assert len(res["sources"]) >= 1


def test_documentation_freshness(seeded_tenant):
    """Target 4: 'Which docs describing checkout might be out of date?'"""
    # Direct tool test
    stale_docs, f_trace = check_docs_freshness(seeded_tenant, service="checkoutservice")
    assert len(stale_docs) >= 1
    assert stale_docs[0]["service"] == "checkoutservice"
    assert stale_docs[0]["is_stale"] is True
    assert stale_docs[0]["changes_since"] > 0

    # Natural language Q&A test
    res, trace = ask_brain(
        graph=seeded_tenant,
        question="Which docs describing checkout might be out of date?",
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    assert res["intent"] == "freshness"
    assert res["is_stale"] is True
    assert len(res["sources"]) >= 1
    assert any(s.get("type") == "Doc" for s in res["sources"])


def test_outcome_history(seeded_tenant):
    """Target 5: 'Has fix F ever failed, and when?'"""
    res, trace = ask_brain(
        graph=seeded_tenant,
        question="Has fix rb_restart ever failed, and when?",
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    assert res["intent"] == "outcome_history"
    assert len(res["sources"]) >= 1
    assert any("restart" in s.get("id", "").lower() for s in res["sources"])
    assert "rb_restart" in res["answer"].lower()


def test_persistent_conversation_history(seeded_tenant):
    """Verify that every Q&A turn creates Question and Answer nodes linked via CITES."""
    q_text = "Who owns the frontend service?"
    res, _ = ask_brain(
        graph=seeded_tenant,
        question=q_text,
        tenant_id=seeded_tenant.tenant_id,
        mode="replay",
    )
    qid = res["question_id"]
    aid = res["answer_id"]

    # Verify nodes and ANSWERED_BY in FalkorDB
    check_q = seeded_tenant.query(
        "MATCH (q:Question {id: $qid})-[:ANSWERED_BY]->(ans:Answer {id: $aid}) RETURN q.text, ans.text",
        {"qid": qid, "aid": aid},
    )
    assert len(check_q.result_set) == 1
    assert check_q.result_set[0][0] == q_text

    # Verify CITES relationships
    cites_res = seeded_tenant.query(
        "MATCH (ans:Answer {id: $aid})-[:CITES]->(src) RETURN count(src)",
        {"aid": aid},
    )
    assert cites_res.result_set[0][0] >= 1

    # Test history retrieval function
    history = get_qa_history(seeded_tenant, tenant_id=seeded_tenant.tenant_id)
    assert len(history) >= 1
    latest = history[0]
    assert latest["question_id"] == qid
    assert len(latest["cited_sources"]) >= 1


def test_api_ask_endpoints(seeded_tenant):
    """Test FastAPI /ask, /ask/history, and /brain/freshness routes."""
    client = TestClient(app)
    headers = {"X-Tenant": seeded_tenant.tenant_id}

    # 1. Ask question via API
    post_res = client.post(
        "/ask",
        json={"question": "What breaks if currency service goes down?", "mode": "replay"},
        headers=headers,
    )
    assert post_res.status_code == 200
    body = post_res.json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["intent"] == "impact"
    assert len(data["sources"]) >= 1
    assert "trace" in body

    # 2. Retrieve Q&A history via API
    hist_res = client.get("/ask/history?limit=10", headers=headers)
    assert hist_res.status_code == 200
    hist_body = hist_res.json()
    assert hist_body["count"] >= 1
    assert len(hist_body["history"]) >= 1

    # 3. Retrieve documentation freshness via API
    fresh_res = client.get("/brain/freshness?service=checkoutservice", headers=headers)
    assert fresh_res.status_code == 200
    fresh_body = fresh_res.json()
    assert fresh_body["count"] >= 1
    assert fresh_body["stale_docs"][0]["service"] == "checkoutservice"

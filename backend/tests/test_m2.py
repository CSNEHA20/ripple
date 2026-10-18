import pytest
from app.tenancy import TenantGraph
from app.ingest.bootstrap import bootstrap_tenant_all, bootstrap_second_tenant
from app.ingest.embed import embed_text, cosine_similarity


@pytest.fixture(scope="module")
def seeded_storefront():
    """Bootstrap storefront tenant once for module tests."""
    graph = TenantGraph("storefront_test")
    graph.clear()
    bootstrap_tenant_all("storefront_test")
    yield graph
    graph.delete()


@pytest.fixture(scope="module")
def seeded_payments():
    """Bootstrap second tenant once for module tests."""
    graph = TenantGraph("payments_test")
    graph.clear()
    bootstrap_second_tenant("payments_test")
    yield graph
    graph.delete()


def test_embedding_generator():
    """Verify deterministic 384-dimensional unit vector generation and cosine similarity."""
    v1 = embed_text("paymentservice credit card charge failure")
    v2 = embed_text("paymentservice credit card processing error")
    v3 = embed_text("kubernetes cluster autoscaler node pool scaling")

    assert len(v1) == 384
    assert len(v2) == 384
    assert len(v3) == 384

    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_related > sim_unrelated, f"Expected {sim_related} > {sim_unrelated}"
    assert sim_related > 0.5


def test_services_and_dependencies(seeded_storefront: TenantGraph):
    """Verify ~11 microservices (+ datastore) and manifest-verified DEPENDS_ON edges."""
    svc_res = seeded_storefront.query("MATCH (s:Service) RETURN s.name, s.language, s.tier, s.embedding")
    assert len(svc_res.result_set) >= 11

    svc_names = {row[0] for row in svc_res.result_set}
    expected = {
        "frontend", "cartservice", "productcatalogservice", "currencyservice",
        "paymentservice", "shippingservice", "emailservice", "checkoutservice",
        "recommendationservice", "adservice", "loadgenerator", "redis-cart"
    }
    assert expected.issubset(svc_names)

    # Check dependencies with valid_from=0 and verified=True
    dep_res = seeded_storefront.query("""
        MATCH (a:Service)-[r:DEPENDS_ON]->(b:Service)
        RETURN a.name, b.name, r.protocol, r.verified, r.valid_from, r.valid_to
    """)
    assert len(dep_res.result_set) >= 15
    for row in dep_res.result_set:
        assert row[3] is True, f"Dependency {row[0]} -> {row[1]} should be verified=True"
        assert row[4] == 0.0
        assert row[5] is None  # Active currently


def test_github_people_and_ownership(seeded_storefront: TenantGraph):
    """Verify 30+ people, COMMITTED edges with n and last_ts, and sensible ownership."""
    people_res = seeded_storefront.query("MATCH (p:Person) RETURN p.login, p.name")
    assert len(people_res.result_set) >= 30, f"Expected 30+ people, got {len(people_res.result_set)}"

    # Check COMMITTED edges
    comm_res = seeded_storefront.query("MATCH (p:Person)-[c:COMMITTED]->(s:Service) RETURN count(c)")
    assert comm_res.result_set[0][0] >= 25

    # Check top owner of paymentservice
    owner_res = seeded_storefront.query("""
        MATCH (p:Person)-[c:COMMITTED]->(s:Service {name: 'paymentservice'})
        RETURN p.login, c.n
        ORDER BY c.n DESC LIMIT 1
    """)
    assert len(owner_res.result_set) == 1
    top_person, commits = owner_res.result_set[0]
    assert top_person == "ianlewis"
    assert commits >= 40

    # Check OWNS relationship
    owns_res = seeded_storefront.query("""
        MATCH (p:Person)-[:OWNS]->(s:Service {name: 'paymentservice'})
        RETURN p.login
    """)
    assert owns_res.result_set[0][0] == "ianlewis"


def test_prs_and_issues_volume(seeded_storefront: TenantGraph):
    """Verify 100+ PRs and Issues in total, with Deployments flagged source='seeded'."""
    pr_res = seeded_storefront.query("MATCH (pr:PullRequest) RETURN count(pr)")
    pr_count = pr_res.result_set[0][0]

    issue_res = seeded_storefront.query("MATCH (iss:Issue) RETURN count(iss)")
    issue_count = issue_res.result_set[0][0]

    total = pr_count + issue_count
    assert total >= 100, f"Expected 100+ PRs/Issues, got {total}"

    # Verify deployments linked to PRs
    dep_res = seeded_storefront.query("""
        MATCH (pr:PullRequest)-[:SHIPPED_IN]->(d:Deployment)-[:DEPLOYED_TO]->(s:Service)
        RETURN count(d), d.source
        LIMIT 1
    """)
    assert dep_res.result_set[0][0] >= 1
    assert dep_res.result_set[0][1] in ("seeded", "synthetic")


def test_docs_and_decisions_with_supersedes(seeded_storefront: TenantGraph):
    """Verify 15-25 decisions, source links to PRs, and at least 2 SUPERSEDES pairs."""
    dec_res = seeded_storefront.query("MATCH (d:Decision) RETURN count(d)")
    dec_count = dec_res.result_set[0][0]
    assert 15 <= dec_count <= 25, f"Expected 15-25 decisions, got {dec_count}"

    # Check SUPERSEDES pairs
    sup_res = seeded_storefront.query("""
        MATCH (newer:Decision)-[:SUPERSEDES]->(older:Decision)
        RETURN newer.id, older.id
    """)
    assert len(sup_res.result_set) >= 2
    pairs = {(r[0], r[1]) for r in sup_res.result_set}
    assert ("dec_cart_valkey", "dec_cart_redis") in pairs
    assert ("dec_currency_distributed", "dec_currency_inmem") in pairs

    # Check DERIVED_FROM PR links
    derived_res = seeded_storefront.query("""
        MATCH (d:Decision)-[:DERIVED_FROM]->(pr:PullRequest)
        RETURN count(d)
    """)
    assert derived_res.result_set[0][0] >= 10

    # Check stale docs for Track 3
    stale_docs_res = seeded_storefront.query("""
        MATCH (d:Doc)-[:DESCRIBES]->(s:Service)<-[:TOUCHES]-(pr:PullRequest)
        WHERE pr.merged_at > d.last_verified_ts
        RETURN d.title, s.name, count(pr) AS changes_since
        ORDER BY changes_since DESC
    """)
    assert len(stale_docs_res.result_set) >= 2, "Expected at least 2 stale docs vs later PRs"


def test_second_tenant_isolation(seeded_storefront: TenantGraph, seeded_payments: TenantGraph):
    """Verify second tenant has completely distinct services, people, and zero leakage."""
    # Payments tenant check
    pay_svcs = seeded_payments.query("MATCH (s:Service) RETURN s.name")
    pay_names = {r[0] for r in pay_svcs.result_set}
    assert "payment-gateway" in pay_names
    assert "ledger-service" in pay_names
    assert "frontend" not in pay_names, "Storefront frontend leaked into payments tenant!"

    # Storefront tenant check
    store_svcs = seeded_storefront.query("MATCH (s:Service) RETURN s.name")
    store_names = {r[0] for r in store_svcs.result_set}
    assert "frontend" in store_names
    assert "payment-gateway" not in store_names, "Payments service leaked into storefront tenant!"

    # Person isolation check
    pay_people = seeded_payments.query("MATCH (p:Person) RETURN p.login")
    pay_logins = {r[0] for r in pay_people.result_set}
    assert "sarah-fintech" in pay_logins
    assert "ianlewis" not in pay_logins

    store_people = seeded_storefront.query("MATCH (p:Person) RETURN p.login")
    store_logins = {r[0] for r in store_people.result_set}
    assert "ianlewis" in store_logins
    assert "sarah-fintech" not in store_logins

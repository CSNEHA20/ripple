import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.tenancy import TenantGraph, ensure_tenant, sanitize_tenant_id
from app.schema import ensure_tenant_schema
from app.temporal import (
    add_dependency_edge,
    apply_architecture_change,
    current_edges,
    edges_as_of,
    get_dependencies,
    temporal_edge_filter,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_test_tenants():
    """Cleanup test tenants after tests."""
    yield
    for t_id in ["tenant_alpha", "tenant_beta", "idempotency_test", "temporal_test", "bootstrap_test"]:
        try:
            tg = TenantGraph(t_id)
            tg.delete()
        except Exception:
            pass


def test_sanitize_tenant_id():
    assert sanitize_tenant_id("Storefront-App") == "storefront_app"
    assert sanitize_tenant_id("   org--name__123  ") == "org_name_123"
    assert sanitize_tenant_id("") == "default"


def test_tenant_isolation():
    """Verify complete isolation between tenants in FalkorDB:
    A write to tenant_alpha must be invisible from tenant_beta.
    """
    alpha = ensure_tenant("tenant_alpha")
    beta = ensure_tenant("tenant_beta")

    # Clear any previous residual data
    alpha.clear()
    beta.clear()

    # Write distinct nodes to alpha
    alpha.query("CREATE (:Service {name: 'auth-service', tier: 'tier-1', token: 'alpha-secret'})")
    alpha.query("CREATE (:Person {login: 'alice', name: 'Alice Alpha'})")

    # Write distinct nodes to beta
    beta.query("CREATE (:Service {name: 'billing-service', tier: 'tier-2', token: 'beta-secret'})")
    beta.query("CREATE (:Person {login: 'bob', name: 'Bob Beta'})")

    # Alpha checks
    res_alpha_auth = alpha.query("MATCH (s:Service {name: 'auth-service'}) RETURN s.token AS token")
    assert len(res_alpha_auth.result_set) == 1
    assert res_alpha_auth.result_set[0][0] == "alpha-secret"

    res_alpha_billing = alpha.query("MATCH (s:Service {name: 'billing-service'}) RETURN s")
    assert len(res_alpha_billing.result_set) == 0, "Beta service leaked into Alpha graph!"

    res_alpha_bob = alpha.query("MATCH (p:Person {login: 'bob'}) RETURN p")
    assert len(res_alpha_bob.result_set) == 0, "Beta person leaked into Alpha graph!"

    # Beta checks
    res_beta_billing = beta.query("MATCH (s:Service {name: 'billing-service'}) RETURN s.token AS token")
    assert len(res_beta_billing.result_set) == 1
    assert res_beta_billing.result_set[0][0] == "beta-secret"

    res_beta_auth = beta.query("MATCH (s:Service {name: 'auth-service'}) RETURN s")
    assert len(res_beta_auth.result_set) == 0, "Alpha service leaked into Beta graph!"

    res_beta_alice = beta.query("MATCH (p:Person {login: 'alice'}) RETURN p")
    assert len(res_beta_alice.result_set) == 0, "Alpha person leaked into Beta graph!"


def test_ensure_tenant_idempotency():
    """Verify that calling ensure_tenant multiple times is idempotent."""
    graph = ensure_tenant("idempotency_test")
    assert graph.ping() is True

    # Call a second time - should not raise errors even though indexes already exist
    graph2 = ensure_tenant("idempotency_test")
    assert graph2.tenant_id == "idempotency_test"

    results = ensure_tenant_schema(graph2)
    assert isinstance(results, dict)
    assert len(results) > 0


def test_temporal_edges_and_architecture_change():
    """Verify temporal edges, current_edges(), edges_as_of(ts), and ArchitectureChange handling:
    1. Initially cartservice -> redis-cart exists from ts=100.0.
    2. At ts=200.0, ArchitectureChange closes cartservice -> redis-cart and opens cartservice -> valkey-cart.
    3. as_of(150.0) returns cartservice -> redis-cart.
    4. as_of(250.0) returns cartservice -> valkey-cart.
    5. current_edges() returns cartservice -> valkey-cart.
    6. Historical records are preserved.
    """
    graph = ensure_tenant("temporal_test")
    graph.clear()

    # Step 1: Initial topology at ts=100.0
    add_dependency_edge(
        graph=graph,
        caller="cartservice",
        callee="redis-cart",
        valid_from=100.0,
        valid_to=None,
        protocol="redis",
        criticality="high",
        verified=True,
        source="manifest",
    )

    # Verify query before ts=100.0 returns nothing
    deps_at_50 = get_dependencies(graph, as_of=50.0)
    assert len(deps_at_50) == 0

    # Verify query at ts=150.0 returns redis-cart
    deps_at_150 = get_dependencies(graph, as_of=150.0)
    assert len(deps_at_150) == 1
    assert deps_at_150[0]["caller"] == "cartservice"
    assert deps_at_150[0]["callee"] == "redis-cart"
    assert deps_at_150[0]["valid_to"] is None

    # Step 2: Apply ArchitectureChange at ts=200.0
    change_res = apply_architecture_change(
        graph=graph,
        change_id="arch_mig_01",
        summary="Migrate cart cache from redis-cart to valkey-cart",
        ts=200.0,
        closes_edges=[("cartservice", "redis-cart")],
        opens_edges=[{
            "caller": "cartservice",
            "callee": "valkey-cart",
            "protocol": "valkey",
            "criticality": "high",
            "verified": True,
            "source": "seeded",
        }],
    )
    assert change_res["closed_count"] == 1
    assert change_res["opened_count"] == 1
    assert "cartservice" in change_res["touched_services"]

    # Step 3: Historical queries as_of
    # Past: at ts=150.0, redis-cart was active
    history_deps = get_dependencies(graph, as_of=150.0)
    assert len(history_deps) == 1
    assert history_deps[0]["caller"] == "cartservice"
    assert history_deps[0]["callee"] == "redis-cart"

    # Future: at ts=250.0, valkey-cart is active
    future_deps = get_dependencies(graph, as_of=250.0)
    assert len(future_deps) == 1
    assert future_deps[0]["caller"] == "cartservice"
    assert future_deps[0]["callee"] == "valkey-cart"

    # Current: current_edges() (valid_to IS NULL) returns valkey-cart
    current_deps = get_dependencies(graph, as_of=None)
    assert len(current_deps) == 1
    assert current_deps[0]["caller"] == "cartservice"
    assert current_deps[0]["callee"] == "valkey-cart"

    # Step 4: Verify total edges in database - both still exist!
    all_edges_query = """
    MATCH (caller:Service)-[r:DEPENDS_ON]->(callee:Service)
    RETURN caller.name, callee.name, r.valid_from, r.valid_to
    ORDER BY r.valid_from
    """
    all_res = graph.query(all_edges_query)
    assert len(all_res.result_set) == 2
    row0 = all_res.result_set[0]
    row1 = all_res.result_set[1]

    # First edge: cartservice -> redis-cart, valid_from=100.0, valid_to=200.0
    assert row0[0] == "cartservice"
    assert row0[1] == "redis-cart"
    assert row0[2] == 100.0
    assert row0[3] == 200.0

    # Second edge: cartservice -> valkey-cart, valid_from=200.0, valid_to=None
    assert row1[0] == "cartservice"
    assert row1[1] == "valkey-cart"
    assert row1[2] == 200.0
    assert row1[3] is None

    # Step 5: Verify ArchitectureChange node and CHANGED relationships
    arch_query = """
    MATCH (ac:ArchitectureChange {id: 'arch_mig_01'})-[:CHANGED]->(s:Service)
    RETURN s.name ORDER BY s.name
    """
    arch_res = graph.query(arch_query)
    services_changed = [r[0] for r in arch_res.result_set]
    assert "cartservice" in services_changed
    assert "redis-cart" in services_changed
    assert "valkey-cart" in services_changed


def test_bootstrap_tenant_api():
    """Verify tenant bootstrap API endpoint."""
    response = client.post("/api/tenants/bootstrap_test/bootstrap")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["tenant_id"] == "bootstrap_test"
    assert "schema_indexes" in data

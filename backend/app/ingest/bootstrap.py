import logging
from typing import Any
from app.tenancy import ensure_tenant, TenantGraph
from app.ingest.embed import embed_text
from app.ingest.services import load_services, export_services_json
from app.ingest.github import load_github_data
from app.ingest.docs import load_docs_and_decisions

logger = logging.getLogger(__name__)


def bootstrap_tenant_all(tenant_id: str = "storefront") -> dict[str, Any]:
    """Bootstrap primary tenant (e.g. storefront) with full real-world dataset."""
    logger.info("Starting complete bootstrap for tenant '%s'...", tenant_id)
    graph = ensure_tenant(tenant_id)

    # 1. Export services.json to data directory
    try:
        export_services_json()
    except Exception as e:
        logger.warning("Could not export services.json: %s", e)

    # 2. Services & dependencies
    svc_res = load_services(graph)

    # 3. People, Commits, PRs, Issues, Deployments
    gh_res = load_github_data(graph)

    # 4. Docs, Decisions, Supersedes
    docs_res = load_docs_and_decisions(graph)

    logger.info("Complete bootstrap for tenant '%s' succeeded.", tenant_id)

    return {
        "tenant_id": graph.tenant_id,
        "graph_name": graph.graph_name,
        "services": svc_res,
        "github": gh_res,
        "docs_and_decisions": docs_res,
    }


def bootstrap_second_tenant(tenant_id: str = "payments") -> dict[str, Any]:
    """Bootstrap a secondary isolated tenant organization (e.g. payments/fintech)
    with completely disjoint services, people, dependencies, and decisions.
    """
    logger.info("Bootstrapping second tenant '%s' for isolation demos...", tenant_id)
    graph = ensure_tenant(tenant_id)

    # 1. Services in second tenant
    services = [
        {"name": "payment-gateway", "lang": "Go", "tier": "tier-1", "desc": "Handles external card processing and API webhooks."},
        {"name": "fraud-detector", "lang": "Python", "tier": "tier-1", "desc": "ML risk scoring engine for transaction authorization."},
        {"name": "ledger-service", "lang": "Java", "tier": "tier-1", "desc": "Double-entry distributed immutable financial ledger."},
        {"name": "payout-engine", "lang": "Go", "tier": "tier-2", "desc": "Batches ACH and SEPA outgoing merchant settlement disbursements."},
        {"name": "compliance-service", "lang": "Rust", "tier": "tier-2", "desc": "Real-time AML sanctions screening and reporting."},
    ]

    for s in services:
        emb = embed_text(f"{s['name']} {s['desc']}")
        graph.query(
            """
            MERGE (svc:Service {name: $name})
            SET svc.language = $lang,
                svc.tier = $tier,
                svc.description = $desc,
                svc.deps_known = true,
                svc.embedding = $emb
            """,
            {"name": s["name"], "lang": s["lang"], "tier": s["tier"], "desc": s["desc"], "emb": emb},
        )

    # 2. Dependencies in second tenant
    deps = [
        ("payment-gateway", "fraud-detector", "gRPC", "critical"),
        ("payment-gateway", "ledger-service", "gRPC", "critical"),
        ("payout-engine", "ledger-service", "gRPC", "high"),
        ("ledger-service", "compliance-service", "gRPC", "high"),
    ]
    for caller, callee, proto, crit in deps:
        graph.query(
            """
            MATCH (caller:Service {name: $caller})
            MATCH (callee:Service {name: $callee})
            MERGE (caller)-[r:DEPENDS_ON {
                protocol: $proto,
                criticality: $crit,
                valid_from: 0.0,
                verified: true,
                source: 'manifest'
            }]->(callee)
            SET r.valid_to = null
            """,
            {"caller": caller, "callee": callee, "proto": proto, "crit": crit},
        )

    # 3. Disjoint people in second tenant
    people = [
        ("sarah-fintech", "Sarah Fintech Lead", "payment-gateway", 40),
        ("marcus-risk", "Marcus Risk Scientist", "fraud-detector", 35),
        ("elena-audit", "Elena Audit Architect", "ledger-service", 45),
        ("dave-core", "Dave Core Engineer", "payout-engine", 30),
    ]
    for login, name, owned_svc, n_commits in people:
        graph.query(
            """
            MERGE (p:Person {login: $login})
            SET p.name = $name
            WITH p
            MATCH (s:Service {name: $owned_svc})
            MERGE (p)-[:OWNS]->(s)
            MERGE (p)-[c:COMMITTED]->(s)
            SET c.n = $n_commits, c.last_ts = 1775000000.0
            """,
            {"login": login, "name": name, "owned_svc": owned_svc, "n_commits": n_commits},
        )

    # 4. PRs & Decisions in second tenant
    graph.query(
        """
        MATCH (s:Service {name: 'ledger-service'})
        MERGE (d:Decision {id: 'dec_immutability_append_only'})
        SET d.summary = 'Enforce strictly append-only write logs in ledger service for audit compliance.',
            d.ts = 1772000000.0,
            d.status = 'active',
            d.embedding = $emb
        MERGE (d)-[:CONCERNS]->(s)
        """,
        {"emb": embed_text("append only ledger audit compliance")},
    )

    return {
        "tenant_id": graph.tenant_id,
        "graph_name": graph.graph_name,
        "services_count": len(services),
        "dependencies_count": len(deps),
        "people_count": len(people),
        "message": f"Second tenant '{tenant_id}' successfully bootstrapped with isolated financial services.",
    }

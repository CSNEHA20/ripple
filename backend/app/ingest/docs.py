import logging
from typing import Any
from app.ingest.embed import embed_text
from app.tenancy import TenantGraph

logger = logging.getLogger(__name__)

# Curated documentation nodes from repository READMEs
# Stale test: doc_paymentservice & doc_checkoutservice have last_verified_ts set in early 2026 (1765000000.0)
# while subsequent PRs merged at 1770000000+ -> allows Track 3 freshness detection!
DOCS_DATA: list[dict[str, Any]] = [
    {
        "id": "doc_frontend",
        "service": "frontend",
        "title": "Frontend Service Architecture & Templates",
        "text": "The frontend is written in Go and renders HTML templates using Go html/template package. It calls upstream services via gRPC.",
        "last_verified_ts": 1776500000.0,  # FRESH
        "url": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/master/src/frontend/README.md",
    },
    {
        "id": "doc_paymentservice",
        "service": "paymentservice",
        "title": "Payment Service Integration & Encryption",
        "text": "Processes credit card payments. Uses mock tokenization and charges dummy cards via charge API. Assumes direct synchronous debit.",
        "last_verified_ts": 1765000000.0,  # DELIBERATELY STALE vs later PRs
        "url": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/master/src/paymentservice/README.md",
    },
    {
        "id": "doc_checkoutservice",
        "service": "checkoutservice",
        "title": "Checkout Orchestrator Specification",
        "text": "Coordinates checkout workflow: charges paymentservice, empties cartservice, orders shippingservice, and sends email confirmation.",
        "last_verified_ts": 1765000000.0,  # DELIBERATELY STALE vs later PRs
        "url": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/master/src/checkoutservice/README.md",
    },
    {
        "id": "doc_cartservice",
        "service": "cartservice",
        "title": "Cart Service State Persistence",
        "text": "Cart state is stored in an external Redis instance using the ASP.NET Core stack. Implements AddItem, GetCart, and EmptyCart endpoints.",
        "last_verified_ts": 1776500000.0,  # FRESH
        "url": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/master/src/cartservice/README.md",
    },
    {
        "id": "doc_currencyservice",
        "service": "currencyservice",
        "title": "Currency Service Rate Calculation",
        "text": "Provides currency conversion using static exchange rates for 33 global fiat currencies loaded at service start.",
        "last_verified_ts": 1766000000.0,  # DELIBERATELY STALE
        "url": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/master/src/currencyservice/README.md",
    },
    {
        "id": "doc_productcatalogservice",
        "service": "productcatalogservice",
        "title": "Product Catalog Service Read-Only Store",
        "text": "Parses a read-only JSON products database into memory at initialization and provides lookup by product ID.",
        "last_verified_ts": 1776500000.0,  # FRESH
        "url": "https://github.com/GoogleCloudPlatform/microservices-demo/blob/master/src/productcatalogservice/README.md",
    },
]

# 18 Curated architectural decisions with source links to PRs / Issues
# Includes 2 explicit SUPERSEDES pairs:
# Pair 1: dec_cart_valkey SUPERSEDES dec_cart_redis
# Pair 2: dec_currency_distributed SUPERSEDES dec_currency_inmem
DECISIONS_DATA: list[dict[str, Any]] = [
    # Pair 1 (SUPERSEDES pair)
    {
        "id": "dec_cart_redis",
        "summary": "Use standalone Redis instance for cart session storage to minimize memory footprint.",
        "ts": 1760000000.0,
        "status": "superseded",
        "service": "cartservice",
        "derived_from_pr": 1102,
        "superseded_by": "dec_cart_valkey",
    },
    {
        "id": "dec_cart_valkey",
        "summary": "Migrate cart session storage from single Redis to Valkey cluster for zero-downtime failover and licensing compliance.",
        "ts": 1774000000.0,
        "status": "active",
        "service": "cartservice",
        "derived_from_pr": 1113,
        "supersedes": "dec_cart_redis",
    },

    # Pair 2 (SUPERSEDES pair)
    {
        "id": "dec_currency_inmem",
        "summary": "Cache currency conversion exchange rates purely in Node.js process memory with periodic hourly refresh.",
        "ts": 1761000000.0,
        "status": "superseded",
        "service": "currencyservice",
        "derived_from_pr": 1105,
        "superseded_by": "dec_currency_distributed",
    },
    {
        "id": "dec_currency_distributed",
        "summary": "Adopt distributed caching for exchange rate data to support horizontal scaling across currencyservice replicas.",
        "ts": 1775000000.0,
        "status": "active",
        "service": "currencyservice",
        "derived_from_pr": 1116,
        "supersedes": "dec_currency_inmem",
    },

    # General active decisions linked to services and PRs/Issues
    {
        "id": "dec_grpc_standard",
        "summary": "Standardize all inter-service communications on gRPC with proto3 and keep-alive pings enabled.",
        "ts": 1762000000.0,
        "status": "active",
        "service": "frontend",
        "derived_from_pr": 1104,
    },
    {
        "id": "dec_payment_circuit_breaker",
        "summary": "Introduce 2.5-second client timeout and circuit breaking on paymentservice calls from checkoutservice.",
        "ts": 1772000000.0,
        "status": "active",
        "service": "paymentservice",
        "derived_from_pr": 1101,
    },
    {
        "id": "dec_catalog_inmem_json",
        "summary": "Load catalog items into memory from local JSON file to eliminate external database latency for product queries.",
        "ts": 1763000000.0,
        "status": "active",
        "service": "productcatalogservice",
        "derived_from_pr": 1106,
    },
    {
        "id": "dec_shipping_stateless",
        "summary": "Keep shippingservice strictly stateless by computing shipping fee algorithmically from item counts without database lookup.",
        "ts": 1764000000.0,
        "status": "active",
        "service": "shippingservice",
        "derived_from_pr": 1107,
    },
    {
        "id": "dec_email_async_queue",
        "summary": "Make email confirmation order notifications non-blocking and fire-and-forget during checkout completion.",
        "ts": 1765000000.0,
        "status": "active",
        "service": "emailservice",
        "derived_from_pr": 1108,
    },
    {
        "id": "dec_recommendation_vector_rank",
        "summary": "Rank recommendation candidates using product tag cosine similarity rather than random sampling.",
        "ts": 1771000000.0,
        "status": "active",
        "service": "recommendationservice",
        "derived_from_pr": 1109,
    },
    {
        "id": "dec_ad_contextual_category",
        "summary": "Filter contextual ads based on current shopping category cookies passed through frontend request headers.",
        "ts": 1768000000.0,
        "status": "active",
        "service": "adservice",
        "derived_from_pr": 1110,
    },
    {
        "id": "dec_loadgen_locust_headless",
        "summary": "Run loadgenerator in headless Locust mode with synthetic user persona distributions.",
        "ts": 1767000000.0,
        "status": "active",
        "service": "loadgenerator",
        "derived_from_pr": 1111,
    },
    {
        "id": "dec_tracing_opentelemetry",
        "summary": "Export OpenTelemetry distributed trace context in W3C TraceContext headers on all gRPC and HTTP calls.",
        "ts": 1770000000.0,
        "status": "active",
        "service": "frontend",
        "derived_from_pr": 1114,
    },
    {
        "id": "dec_health_probes_standard",
        "summary": "Require standard grpc.health.v1.Health service implementation on all backends for Kubernetes liveness/readiness.",
        "ts": 1773000000.0,
        "status": "active",
        "service": "checkoutservice",
        "derived_from_pr": 1115,
    },
    {
        "id": "dec_tls_mutual_auth",
        "summary": "Enable mTLS service mesh authentication with SPIFFE workload identities across all inter-service mesh hops.",
        "ts": 1775500000.0,
        "status": "active",
        "service": "paymentservice",
        "derived_from_pr": 1123,
    },
    {
        "id": "dec_redis_connection_pool",
        "summary": "Cap cartservice Redis client connection pool to 20 sockets with keepalive heartbeats every 30 seconds.",
        "ts": 1772500000.0,
        "status": "active",
        "service": "cartservice",
        "derived_from_pr": 1124,
    },
    {
        "id": "dec_retry_jitter_backoff",
        "summary": "Enforce truncated exponential backoff with full jitter on all transient gRPC client retries.",
        "ts": 1774500000.0,
        "status": "active",
        "service": "checkoutservice",
        "derived_from_pr": 1125,
    },
    {
        "id": "dec_graceful_shutdown_sigterm",
        "summary": "Configure 15-second graceful drain timeout on SIGTERM before forceful termination in container runtime.",
        "ts": 1773500000.0,
        "status": "active",
        "service": "frontend",
        "derived_from_pr": 1126,
    },
]


def load_docs_and_decisions(graph: TenantGraph) -> dict[str, int]:
    """Load curated docs and decisions with source links and SUPERSEDES relationships."""
    doc_count = 0
    dec_count = 0
    supersedes_count = 0

    # 1. Ingest Docs
    for doc in DOCS_DATA:
        cypher_doc = """
        MATCH (s:Service {name: $service})
        MERGE (d:Doc {id: $id})
        SET d.title = $title,
            d.text = $text,
            d.last_verified_ts = $last_verified_ts,
            d.url = $url
        MERGE (d)-[:DESCRIBES]->(s)
        RETURN d.id
        """
        graph.query(
            cypher_doc,
            {
                "service": doc["service"],
                "id": doc["id"],
                "title": doc["title"],
                "text": doc["text"],
                "last_verified_ts": float(doc["last_verified_ts"]),
                "url": doc["url"],
            },
        )
        doc_count += 1

    # 2. Ingest Decisions
    for dec in DECISIONS_DATA:
        embedding = embed_text(dec["summary"])
        cypher_dec = """
        MATCH (s:Service {name: $service})
        MERGE (d:Decision {id: $id})
        SET d.summary = $summary,
            d.ts = $ts,
            d.status = $status,
            d.embedding = $embedding
        MERGE (d)-[:CONCERNS]->(s)
        RETURN d.id
        """
        graph.query(
            cypher_dec,
            {
                "service": dec["service"],
                "id": dec["id"],
                "summary": dec["summary"],
                "ts": float(dec["ts"]),
                "status": dec["status"],
                "embedding": embedding,
            },
        )
        dec_count += 1

        # Link DERIVED_FROM to PullRequest if exists
        pr_num = dec.get("derived_from_pr")
        if pr_num:
            cypher_link = """
            MATCH (d:Decision {id: $id})
            MATCH (pr:PullRequest {number: $pr_num})
            MERGE (d)-[:DERIVED_FROM]->(pr)
            """
            graph.query(cypher_link, {"id": dec["id"], "pr_num": pr_num})

    # 3. Create SUPERSEDES links between decisions
    for dec in DECISIONS_DATA:
        superseded_id = dec.get("supersedes")
        if superseded_id:
            cypher_sup = """
            MATCH (newer:Decision {id: $newer_id})
            MATCH (older:Decision {id: $older_id})
            MERGE (newer)-[:SUPERSEDES]->(older)
            RETURN newer.id, older.id
            """
            graph.query(cypher_sup, {"newer_id": dec["id"], "older_id": superseded_id})
            supersedes_count += 1

    logger.info("Ingested into %s: %d docs, %d decisions, %d supersedes links", graph.graph_name, doc_count, dec_count, supersedes_count)
    return {"docs": doc_count, "decisions": dec_count, "supersedes_links": supersedes_count}

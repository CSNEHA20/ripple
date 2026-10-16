import json
import logging
import os
from typing import Any
from app.config import settings
from app.ingest.embed import embed_text
from app.tenancy import TenantGraph

logger = logging.getLogger(__name__)

# Real microservices from GoogleCloudPlatform/microservices-demo architecture
SERVICES_DATA: list[dict[str, Any]] = [
    {
        "name": "frontend",
        "language": "Go",
        "tier": "tier-1",
        "description": "Exposes HTTP server serving the website and reverse-proxies gRPC calls to internal services.",
        "deps_known": True,
    },
    {
        "name": "cartservice",
        "language": "C#",
        "tier": "tier-1",
        "description": "Stores user shopping cart items in Redis datastore and provides cart modification APIs.",
        "deps_known": True,
    },
    {
        "name": "productcatalogservice",
        "language": "Go",
        "tier": "tier-1",
        "description": "Provides product search, details, and list APIs reading from catalog JSON.",
        "deps_known": True,
    },
    {
        "name": "currencyservice",
        "language": "Node.js",
        "tier": "tier-2",
        "description": "Converts currency amounts between different international currencies based on current exchange rates.",
        "deps_known": True,
    },
    {
        "name": "paymentservice",
        "language": "Node.js",
        "tier": "tier-1",
        "description": "Charges customer credit cards and processes payment authorization with mock merchant provider.",
        "deps_known": True,
    },
    {
        "name": "shippingservice",
        "language": "Go",
        "tier": "tier-2",
        "description": "Gives shipping quotes and ships orders based on mock address and items count.",
        "deps_known": True,
    },
    {
        "name": "emailservice",
        "language": "Python",
        "tier": "tier-3",
        "description": "Sends customer confirmation emails upon successful order placement.",
        "deps_known": True,
    },
    {
        "name": "checkoutservice",
        "language": "Go",
        "tier": "tier-1",
        "description": "Coordinates cart retrieval, payment processing, shipping quote, order preparation, and notification.",
        "deps_known": True,
    },
    {
        "name": "recommendationservice",
        "language": "Python",
        "tier": "tier-2",
        "description": "Recommends other products to browse based on current cart contents.",
        "deps_known": True,
    },
    {
        "name": "adservice",
        "language": "Java",
        "tier": "tier-3",
        "description": "Serves targeted contextual advertisements based on current browsing category.",
        "deps_known": True,
    },
    {
        "name": "loadgenerator",
        "language": "Python",
        "tier": "tier-3",
        "description": "Continuously generates synthetic realistic traffic against frontend web service.",
        "deps_known": True,
    },
    {
        "name": "redis-cart",
        "language": "C",
        "tier": "tier-1",
        "description": "In-memory key-value cache datastore storing persistent session carts for cartservice.",
        "deps_known": True,
    },
]

# Verified dependencies extracted from Kubernetes manifests (*_SERVICE_ADDR environment variables)
DEPENDENCIES_DATA: list[dict[str, Any]] = [
    # Frontend dependencies
    {"caller": "frontend", "callee": "checkoutservice", "protocol": "gRPC", "criticality": "high", "verified": True},
    {"caller": "frontend", "callee": "recommendationservice", "protocol": "gRPC", "criticality": "medium", "verified": True},
    {"caller": "frontend", "callee": "productcatalogservice", "protocol": "gRPC", "criticality": "high", "verified": True},
    {"caller": "frontend", "callee": "cartservice", "protocol": "gRPC", "criticality": "high", "verified": True},
    {"caller": "frontend", "callee": "shippingservice", "protocol": "gRPC", "criticality": "medium", "verified": True},
    {"caller": "frontend", "callee": "currencyservice", "protocol": "gRPC", "criticality": "medium", "verified": True},
    {"caller": "frontend", "callee": "adservice", "protocol": "gRPC", "criticality": "low", "verified": True},

    # Checkoutservice dependencies
    {"caller": "checkoutservice", "callee": "productcatalogservice", "protocol": "gRPC", "criticality": "high", "verified": True},
    {"caller": "checkoutservice", "callee": "shippingservice", "protocol": "gRPC", "criticality": "high", "verified": True},
    {"caller": "checkoutservice", "callee": "paymentservice", "protocol": "gRPC", "criticality": "critical", "verified": True},
    {"caller": "checkoutservice", "callee": "emailservice", "protocol": "gRPC", "criticality": "low", "verified": True},
    {"caller": "checkoutservice", "callee": "currencyservice", "protocol": "gRPC", "criticality": "medium", "verified": True},
    {"caller": "checkoutservice", "callee": "cartservice", "protocol": "gRPC", "criticality": "high", "verified": True},

    # Recommendationservice dependencies
    {"caller": "recommendationservice", "callee": "productcatalogservice", "protocol": "gRPC", "criticality": "medium", "verified": True},

    # Cartservice dependencies
    {"caller": "cartservice", "callee": "redis-cart", "protocol": "redis", "criticality": "critical", "verified": True},

    # Loadgenerator dependencies
    {"caller": "loadgenerator", "callee": "frontend", "protocol": "HTTP", "criticality": "low", "verified": True},
]


def export_services_json(dest_dir: str | None = None) -> str:
    """Save services definition to data/services.json."""
    target_dir = dest_dir or settings.data_dir
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, "services.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"services": SERVICES_DATA, "dependencies": DEPENDENCIES_DATA}, f, indent=2)
    return filepath


def load_services(graph: TenantGraph) -> dict[str, int]:
    """Load services and temporal DEPENDS_ON edges into the specified tenant graph."""
    svc_count = 0
    dep_count = 0

    # Ingest services
    for svc in SERVICES_DATA:
        embedding = embed_text(f"{svc['name']} {svc['language']} {svc['description']}")
        cypher = """
        MERGE (s:Service {name: $name})
        SET s.language = $language,
            s.tier = $tier,
            s.description = $description,
            s.deps_known = $deps_known,
            s.embedding = $embedding
        RETURN s.name
        """
        graph.query(
            cypher,
            {
                "name": svc["name"],
                "language": svc["language"],
                "tier": svc["tier"],
                "description": svc["description"],
                "deps_known": svc["deps_known"],
                "embedding": embedding,
            },
        )
        svc_count += 1

    # Ingest dependencies with valid_from=0.0 and valid_to=None
    for dep in DEPENDENCIES_DATA:
        cypher = """
        MATCH (caller:Service {name: $caller})
        MATCH (callee:Service {name: $callee})
        MERGE (caller)-[r:DEPENDS_ON {
            protocol: $protocol,
            criticality: $criticality,
            valid_from: 0.0,
            verified: $verified,
            source: 'manifest'
        }]->(callee)
        SET r.valid_to = null
        RETURN caller.name, callee.name
        """
        graph.query(
            cypher,
            {
                "caller": dep["caller"],
                "callee": dep["callee"],
                "protocol": dep["protocol"],
                "criticality": dep["criticality"],
                "verified": dep["verified"],
            },
        )
        dep_count += 1

    logger.info("Loaded %d services and %d dependencies into %s", svc_count, dep_count, graph.graph_name)
    return {"services": svc_count, "dependencies": dep_count}

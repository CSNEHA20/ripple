import logging
import os
import re
from typing import Any
from app.tenancy import TenantGraph
from app.adapters.base import TopologyEdgeRecord

logger = logging.getLogger("ripple.adapters.topology")


def discover_topology_from_environment(compose_file_path: str = "docker-compose.yml") -> list[TopologyEdgeRecord]:
    """Parse docker-compose or container definitions for environment variables ending in _ADDR or _HOST."""
    edges: list[TopologyEdgeRecord] = []
    if not os.path.exists(compose_file_path):
        return edges

    try:
        with open(compose_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Simple regex matcher for service blocks and env vars
        current_service = None
        for line in content.splitlines():
            svc_match = re.match(r"^\s{2}([a-zA-Z0-9_\-]+):", line)
            if svc_match:
                current_service = svc_match.group(1)
            elif current_service:
                addr_match = re.search(r"([A-Z0-9_]+)_(?:ADDR|HOST)[:=]\s*([a-zA-Z0-9_\-]+)", line)
                if addr_match:
                    target_svc = addr_match.group(2)
                    if target_svc != current_service:
                        edges.append(
                            TopologyEdgeRecord(
                                caller=current_service,
                                callee=target_svc,
                                protocol="gRPC" if "grpc" in line.lower() else "HTTP",
                                criticality="high",
                                verified=True,
                                source="discovered",
                            )
                        )
    except Exception as e:
        logger.warning(f"Error discovering topology from {compose_file_path}: {e}")

    return edges


def apply_discovered_topology(graph: TenantGraph, edges: list[TopologyEdgeRecord]) -> int:
    """Commit discovered topology edges to FalkorDB tenant graph with source='discovered'."""
    count = 0
    cypher = """
    MERGE (caller:Service {name: $caller})
    MERGE (callee:Service {name: $callee})
    MERGE (caller)-[r:DEPENDS_ON {
        protocol: $protocol,
        criticality: $criticality,
        valid_from: 0.0,
        verified: true,
        source: 'discovered'
    }]->(callee)
    SET r.valid_to = null
    RETURN caller.name, callee.name
    """
    for edge in edges:
        try:
            graph.query(
                cypher,
                {
                    "caller": edge.caller,
                    "callee": edge.callee,
                    "protocol": edge.protocol,
                    "criticality": edge.criticality,
                },
            )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to persist discovered edge {edge.caller}->{edge.callee}: {e}")

    logger.info(f"Committed {count} discovered topology edges to tenant {graph.tenant_id}")
    return count

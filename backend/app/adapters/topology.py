import logging
import os
import re
from typing import Any
from app.tenancy import TenantGraph
from app.adapters.base import TopologyEdgeRecord

logger = logging.getLogger("ripple.adapters.topology")


TARGET_COMPOSE_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "target_compose.yml"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "target_compose.yml"),
    os.path.abspath("data/target_compose.yml"),
    os.path.abspath("../data/target_compose.yml"),
    "data/target_compose.yml",
    "target_compose.yml",
]


def discover_topology_from_environment(compose_file_path: str | None = None) -> list[TopologyEdgeRecord]:
    """Parse docker-compose or container definitions from the monitored target system.
    Avoids reading Ripple's own operational docker-compose.yml.
    """
    edges: list[TopologyEdgeRecord] = []

    # Resolve target file path
    target_path = compose_file_path
    if not target_path or target_path in ("docker-compose.yml", "./docker-compose.yml"):
        for cand in TARGET_COMPOSE_CANDIDATES:
            if os.path.exists(cand):
                target_path = cand
                break

    if not target_path or not os.path.exists(target_path):
        logger.warning(f"Target compose definition not found: {target_path}")
        return edges

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        current_service = None
        for line in content.splitlines():
            svc_match = re.match(r"^\s{2}([a-zA-Z0-9_\-]+):", line)
            if svc_match:
                current_service = svc_match.group(1).lower().strip()
            elif current_service:
                addr_match = re.search(r"([A-Z0-9_]+)_(?:ADDR|HOST)[:=]\s*([a-zA-Z0-9_\-]+)", line)
                if addr_match:
                    target_svc = addr_match.group(2).lower().strip()
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
        logger.warning(f"Error discovering topology from {target_path}: {e}")

    logger.info(f"Discovered {len(edges)} topology edges from monitored target manifest {target_path}")
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

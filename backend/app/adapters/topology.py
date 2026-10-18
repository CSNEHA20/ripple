import base64
import logging
import os
import re
import time
from typing import Any
import httpx
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


def parse_manifest_content(
    content: str,
    verified: bool = False,
    source: str = "manifest",
) -> list[TopologyEdgeRecord]:
    """Parse docker-compose, Kubernetes manifests, or container configurations into TopologyEdgeRecords.
    Infers edges between services based on environment variables (ADDR/HOST) and service references.
    """
    edges: list[TopologyEdgeRecord] = []
    seen: set[tuple[str, str]] = set()

    current_service = None
    for line in content.splitlines():
        # Compose service definition match
        svc_match = re.match(r"^\s{2}([a-zA-Z0-9_\-]+):", line)
        if svc_match:
            candidate = svc_match.group(1).lower().strip()
            if candidate not in ("version", "services", "networks", "volumes"):
                current_service = candidate
        # Kubernetes Deployment / Service match
        k8s_match = re.match(r"^\s*name:\s*([a-zA-Z0-9_\-]+)", line)
        if k8s_match and not current_service:
            current_service = k8s_match.group(1).lower().strip()

        if current_service:
            addr_match = re.search(r"([A-Z0-9_]+)_(?:ADDR|HOST)[:=]\s*([a-zA-Z0-9_\-]+)", line)
            if addr_match:
                target_svc = addr_match.group(2).lower().strip()
                if target_svc != current_service and (current_service, target_svc) not in seen:
                    seen.add((current_service, target_svc))
                    edges.append(
                        TopologyEdgeRecord(
                            caller=current_service,
                            callee=target_svc,
                            protocol="gRPC" if "grpc" in line.lower() else "HTTP",
                            criticality="high",
                            verified=verified,
                            source=source,
                        )
                    )

    return edges


def discover_topology_from_environment(
    compose_file_path: str | None = None,
    verified: bool = True,
    source: str = "discovered",
) -> list[TopologyEdgeRecord]:
    """Parse docker-compose or container definitions from the local target system.
    Avoids reading Ripple's own operational docker-compose.yml.
    """
    # Resolve target file path
    target_path = compose_file_path
    if not target_path or target_path in ("docker-compose.yml", "./docker-compose.yml"):
        for cand in TARGET_COMPOSE_CANDIDATES:
            if os.path.exists(cand):
                target_path = cand
                break

    if not target_path or not os.path.exists(target_path):
        logger.warning(f"Target compose definition not found: {target_path}")
        return []

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        edges = parse_manifest_content(content, verified=verified, source=source)
        logger.info(f"Discovered {len(edges)} topology edges from monitored target manifest {target_path}")
        return edges
    except Exception as e:
        logger.warning(f"Error discovering topology from {target_path}: {e}")
        return []


def fetch_topology_from_monitored_repo(
    repo: str,
    token: str | None = None,
    branch: str = "main",
    candidate_paths: list[str] | None = None,
    verified: bool = False,
    source: str = "monitored_repo_manifest",
) -> tuple[list[TopologyEdgeRecord], dict[str, Any]]:
    """Dynamically fetch manifests from the monitored GitHub repository rather than only bundled static files.
    Queries the GitHub Contents API for candidate files; falls back to local candidates if offline or unauthenticated.
    """
    candidates = candidate_paths or [
        "data/target_compose.yml",
        "target_compose.yml",
        "docker-compose.yml",
        "deployments/docker-compose.yml",
        "k8s/manifests.yaml",
    ]

    details: dict[str, Any] = {
        "repo": repo,
        "branch": branch,
        "source": "github_api",
        "retrieved_from": None,
        "status": "pending",
    }

    if repo and token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Ripple-Topology-Adapter",
        }
        for path in candidates:
            url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_content = ""
                        if data.get("encoding") == "base64" and data.get("content"):
                            raw_content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                        elif "download_url" in data and data["download_url"]:
                            dl_resp = client.get(data["download_url"])
                            if dl_resp.status_code == 200:
                                raw_content = dl_resp.text

                        if raw_content:
                            edges = parse_manifest_content(raw_content, verified=verified, source=source)
                            details["status"] = "success"
                            details["retrieved_from"] = f"https://github.com/{repo}/blob/{branch}/{path}"
                            details["edge_count"] = len(edges)
                            logger.info(f"Fetched {len(edges)} topology edges from remote GitHub repo {repo}/{path}")
                            return edges, details
            except Exception as e:
                logger.debug(f"GitHub manifest fetch failed for {path}: {e}")

    # Fallback to local discovered environment
    edges = discover_topology_from_environment(verified=verified, source="local_fallback_manifest")
    details["status"] = "fallback_local"
    details["source"] = "local_target_manifest"
    details["retrieved_from"] = "data/target_compose.yml"
    details["edge_count"] = len(edges)
    return edges, details


def apply_discovered_topology(graph: TenantGraph, edges: list[TopologyEdgeRecord]) -> int:
    """Commit discovered or manifest-inferred topology edges to FalkorDB tenant graph."""
    if not edges:
        return 0

    count = 0
    cypher = """
    MERGE (caller:Service {name: $caller})
    MERGE (callee:Service {name: $callee})
    MERGE (caller)-[r:DEPENDS_ON]->(callee)
    SET r.protocol = $protocol,
        r.criticality = $criticality,
        r.verified = $verified,
        r.source = $source,
        r.valid_from = coalesce(r.valid_from, 0.0)
    RETURN caller.name, callee.name
    """
    for edge in edges:
        try:
            if hasattr(graph, "query"):
                graph.query(
                    cypher,
                    {
                        "caller": edge.caller,
                        "callee": edge.callee,
                        "protocol": edge.protocol,
                        "criticality": edge.criticality,
                        "verified": bool(edge.verified),
                        "source": str(edge.source),
                    },
                )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to persist edge {edge.caller}->{edge.callee}: {e}")

    logger.info(f"Committed {count} topology edges to tenant {getattr(graph, 'tenant_id', 'unknown')}")
    return count


def _extract_caller_callee_from_span(span: dict[str, Any]) -> tuple[str | None, str | None]:
    """Helper to extract caller service and callee service from arbitrary OpenTelemetry span structures."""
    caller = None
    callee = None

    # 1. Flat format
    if "caller" in span and "callee" in span:
        return str(span["caller"]).lower().strip(), str(span["callee"]).lower().strip()

    # 2. Service names and peers
    if "service" in span:
        caller = str(span["service"]).lower().strip()
    if "peer_service" in span:
        callee = str(span["peer_service"]).lower().strip()

    # 3. Attributes dictionary / list
    attrs = span.get("attributes", {})
    if isinstance(attrs, list):
        # OTLP list of key-value pairs
        attr_dict = {}
        for item in attrs:
            k = item.get("key")
            v = item.get("value", {})
            if isinstance(v, dict):
                val = v.get("stringValue") or v.get("intValue") or v.get("doubleValue")
            else:
                val = v
            attr_dict[k] = val
        attrs = attr_dict

    if isinstance(attrs, dict):
        if not caller:
            caller = (
                attrs.get("service.name")
                or attrs.get("service")
                or attrs.get("app")
                or attrs.get("caller")
            )
        if not callee:
            callee = (
                attrs.get("peer.service")
                or attrs.get("rpc.service")
                or attrs.get("callee")
                or attrs.get("target.service")
                or attrs.get("net.peer.name")
            )
            # Check http.url / http.host for host:port format
            if not callee and "http.host" in attrs:
                callee = str(attrs["http.host"]).split(":")[0]

    if caller:
        caller = str(caller).lower().strip()
    if callee:
        callee = str(callee).lower().strip()

    if caller and callee and caller != callee:
        return caller, callee
    return None, None


def ingest_opentelemetry_traces(
    graph: TenantGraph,
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ingest OpenTelemetry spans and verify observed dependencies:
    Only marks an edge as 'verified: True' and source='otel_trace' when an actual trace has crossed it.
    Unobserved edges remain manifest-inferred.
    """
    now_ts = time.time()
    verified_edges: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Process all spans to extract caller-callee pairs
    for span in spans:
        caller, callee = _extract_caller_callee_from_span(span)
        if caller and callee and (caller, callee) not in seen_pairs:
            seen_pairs.add((caller, callee))
            verified_edges.append({
                "caller": caller,
                "callee": callee,
                "verified": True,
                "source": "otel_trace",
                "observed_ts": now_ts,
            })

    # Update graph edges
    update_cypher = """
    MERGE (caller:Service {name: $caller})
    MERGE (callee:Service {name: $callee})
    MERGE (caller)-[r:DEPENDS_ON]->(callee)
    SET r.verified = true,
        r.source = 'otel_trace',
        r.last_observed_ts = $ts,
        r.trace_count = coalesce(r.trace_count, 0) + 1
    RETURN caller.name, callee.name
    """
    committed = 0
    if hasattr(graph, "query"):
        for edge in verified_edges:
            try:
                graph.query(
                    update_cypher,
                    {
                        "caller": edge["caller"],
                        "callee": edge["callee"],
                        "ts": now_ts,
                    },
                )
                committed += 1
            except Exception as e:
                logger.warning(f"Failed to record OTel verified edge {edge['caller']}->{edge['callee']}: {e}")

    logger.info(
        f"Ingested {len(spans)} OTel spans into tenant {getattr(graph, 'tenant_id', 'unknown')}: "
        f"{len(verified_edges)} edges verified ({committed} persisted)."
    )

    return {
        "status": "success",
        "processed_spans": len(spans),
        "verified_edges_count": len(verified_edges),
        "verified_edges": verified_edges,
    }

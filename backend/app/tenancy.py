import logging
import re
from typing import Any
from falkordb import FalkorDB
from app.config import settings

logger = logging.getLogger(__name__)

_falkor_client: FalkorDB | None = None


def get_falkordb_client() -> FalkorDB:
    global _falkor_client
    if _falkor_client is None:
        _falkor_client = FalkorDB(host=settings.falkordb_host, port=settings.falkordb_port)
    return _falkor_client


def sanitize_tenant_id(tenant_id: str) -> str:
    """Sanitize tenant identifier into a valid safe name."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", tenant_id.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "default"


class TenantGraph:
    """Isolation boundary for tenant data in FalkorDB.
    Every tenant gets its own dedicated graph: tenant_<id>.
    No tool or agent receives a raw un-isolated client.
    """

    def __init__(self, tenant_id: str, db: FalkorDB | None = None):
        self.tenant_id = sanitize_tenant_id(tenant_id)
        self.graph_name = f"tenant_{self.tenant_id}"
        self._db = db or get_falkordb_client()
        self._g = self._db.select_graph(self.graph_name)

    def query(self, cypher: str, params: dict[str, Any] | None = None):
        """Execute a parameterized Cypher query against this tenant's graph."""
        return self._g.query(cypher, params or {})

    def ping(self) -> bool:
        """Verify graph is accessible."""
        res = self._g.query("RETURN 1 AS alive")
        return bool(res and len(res.result_set) > 0)

    def delete(self) -> bool:
        """Delete this tenant's graph from FalkorDB."""
        try:
            self._g.delete()
            return True
        except Exception as e:
            logger.warning("Failed to delete graph %s: %s", self.graph_name, e)
            return False

    def clear(self) -> None:
        """Clear all nodes and relationships in this tenant's graph, then reselect."""
        self.delete()
        self._g = self._db.select_graph(self.graph_name)


def get_tenant_graph(tenant_id: str = "storefront", db: FalkorDB | None = None) -> TenantGraph:
    """Obtain a TenantGraph handle for the specified tenant."""
    return TenantGraph(tenant_id=tenant_id, db=db)


def ensure_tenant(tenant_id: str = "storefront", db: FalkorDB | None = None) -> TenantGraph:
    """Ensure a tenant graph exists and has its schema indexes configured.
    Guaranteed to be idempotent.
    """
    from app.schema import ensure_tenant_schema

    graph = get_tenant_graph(tenant_id=tenant_id, db=db)
    graph.ping()
    ensure_tenant_schema(graph)
    return graph

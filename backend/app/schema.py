import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tenancy import TenantGraph

logger = logging.getLogger(__name__)

STANDARD_INDEXES = [
    "CREATE INDEX FOR (s:Service) ON (s.name)",
    "CREATE INDEX FOR (p:Person) ON (p.login)",
    "CREATE INDEX FOR (i:Incident) ON (i.id)",
    "CREATE INDEX FOR (h:Hypothesis) ON (h.incident_id)",
    "CREATE INDEX FOR (m:MetricSnapshot) ON (m.service)",
    "CREATE INDEX FOR (pr:PullRequest) ON (pr.number)",
    "CREATE INDEX FOR (iss:Issue) ON (iss.number)",
    "CREATE INDEX FOR (d:Decision) ON (d.id)",
    "CREATE INDEX FOR (doc:Doc) ON (doc.id)",
    "CREATE INDEX FOR (dep:Deployment) ON (dep.id)",
    "CREATE INDEX FOR (ac:ArchitectureChange) ON (ac.id)",
    "CREATE INDEX FOR (rb:Runbook) ON (rb.id)",
    "CREATE INDEX FOR (t:Task) ON (t.id)",
    "CREATE INDEX FOR (a:Action) ON (a.id)",
    "CREATE INDEX FOR (obs:Observation) ON (obs.id)",
    "CREATE INDEX FOR (intv:Intervention) ON (intv.id)",
    "CREATE INDEX FOR (out:Outcome) ON (out.id)",
]

VECTOR_INDEXES = [
    "CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature_embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'}",
    "CREATE VECTOR INDEX FOR (d:Decision) ON (d.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'}",
]


def ensure_tenant_schema(graph: "TenantGraph") -> dict[str, str]:
    """Ensure standard indexes and vector indexes exist on the tenant graph.
    Catches errors if indexes already exist to remain strictly idempotent.
    """
    results: dict[str, str] = {}

    for idx_query in STANDARD_INDEXES:
        try:
            graph.query(idx_query)
            results[idx_query] = "created"
        except Exception as e:
            err_msg = str(e)
            if "already indexed" in err_msg.lower() or "equivalent index already exists" in err_msg.lower():
                results[idx_query] = "exists"
            else:
                logger.warning("Index creation note for '%s': %s", idx_query, err_msg)
                results[idx_query] = f"ignored ({err_msg})"

    for vec_query in VECTOR_INDEXES:
        try:
            graph.query(vec_query)
            results[vec_query] = "created"
        except Exception as e:
            err_msg = str(e)
            if "already indexed" in err_msg.lower() or "equivalent index already exists" in err_msg.lower():
                results[vec_query] = "exists"
            else:
                logger.warning("Vector index note for '%s': %s", vec_query, err_msg)
                results[vec_query] = f"ignored ({err_msg})"

    return results

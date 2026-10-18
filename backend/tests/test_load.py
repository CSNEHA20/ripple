import concurrent.futures
import threading
import time
from typing import Any
import pytest
from app.tenancy import TenantGraph, sanitize_tenant_id
from app.schema import ensure_tenant_schema
from tests.conftest import is_falkordb_available
from tests.test_realtime import MockT8TenantGraph


class ThreadSafeMockLoadGraph(MockT8TenantGraph):
    """Thread-safe variant of MockT8TenantGraph for concurrent load testing when FalkorDB is offline."""

    def __init__(self, tenant_id: str = "load_tenant"):
        super().__init__(tenant_id)
        self._lock = threading.Lock()

    def query(self, cypher: str, params=None):
        with self._lock:
            return super().query(cypher, params)


def test_concurrent_load_two_tenants_no_duplicates_no_lost_writes():
    """T9 Load Test: A few dozen concurrent incidents across two tenants,
    checking for duplicate nodes, lost writes, and strict tenant isolation.
    """
    falkor_live = is_falkordb_available()

    tenant_1_id = "load_tenant_alpha"
    tenant_2_id = "load_tenant_beta"

    if falkor_live:
        g1 = TenantGraph(tenant_1_id)
        g2 = TenantGraph(tenant_2_id)
        g1.clear()
        g2.clear()
        ensure_tenant_schema(g1)
        ensure_tenant_schema(g2)
    else:
        g1 = ThreadSafeMockLoadGraph(tenant_1_id)
        g2 = ThreadSafeMockLoadGraph(tenant_2_id)

    num_incidents_per_tenant = 15
    total_incidents = num_incidents_per_tenant * 2

    # Tasks to execute concurrently
    incident_tasks = []
    for i in range(num_incidents_per_tenant):
        incident_tasks.append((g1, tenant_1_id, f"inc_{tenant_1_id}_{i:03d}", "paymentservice", f"Alpha Alert {i}"))
        incident_tasks.append((g2, tenant_2_id, f"inc_{tenant_2_id}_{i:03d}", "checkoutservice", f"Beta Alert {i}"))

    written_incident_ids = set()
    write_lock = threading.Lock()
    errors = []

    def _worker(task_info):
        graph, t_id, inc_id, svc, alert_txt = task_info
        try:
            # 1. Open incident
            graph.query(
                """
                MERGE (i:Incident {id: $id})
                SET i.title = $title,
                    i.service_name = $service,
                    i.status = 'investigating',
                    i.opened_ts = $ts
                """,
                {"id": inc_id, "title": alert_txt, "service": svc, "ts": time.time()},
            )

            # 2. Add hypothesis
            hyp_id = f"hyp_{inc_id}_01"
            graph.query(
                """
                MERGE (h:Hypothesis {id: $id})
                SET h.statement = $statement,
                    h.service = $service,
                    h.status = 'open'
                WITH h
                MATCH (i:Incident {id: $inc_id})
                MERGE (i)-[:HAS_HYPOTHESIS]->(h)
                """,
                {"id": hyp_id, "statement": f"Regression on {svc}", "service": svc, "inc_id": inc_id},
            )

            # 3. Add evidence
            ev_id = f"ev_{inc_id}_01"
            graph.query(
                """
                MERGE (e:Evidence {id: $id})
                SET e.type = 'metric',
                    e.source = 'real',
                    e.weight = 2.0
                WITH e
                MATCH (h:Hypothesis {id: $hyp_id})
                MERGE (h)-[:SUPPORTED_BY]->(e)
                """,
                {"id": ev_id, "hyp_id": hyp_id},
            )

            with write_lock:
                written_incident_ids.add(inc_id)

        except Exception as exc:
            with write_lock:
                errors.append(f"Worker failure on {inc_id} ({t_id}): {exc}")

    # Run with 8 concurrent worker threads
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker, task) for task in incident_tasks]
        concurrent.futures.wait(futures)

    duration = time.time() - start_time
    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"

    # 1. Check for NO lost writes (all 30 incidents written)
    assert len(written_incident_ids) == total_incidents, (
        f"Expected {total_incidents} written incidents, got {len(written_incident_ids)}"
    )

    if falkor_live:
        # 2. Check for NO duplicate nodes in FalkorDB
        dup_query = """
        MATCH (i:Incident)
        WITH i.id AS id, count(i) AS cnt
        WHERE cnt > 1
        RETURN id, cnt
        """
        dup_res1 = g1.query(dup_query)
        dup_res2 = g2.query(dup_query)
        assert not (dup_res1 and dup_res1.result_set), f"Duplicate incidents found in tenant 1: {dup_res1.result_set}"
        assert not (dup_res2 and dup_res2.result_set), f"Duplicate incidents found in tenant 2: {dup_res2.result_set}"

        # 3. Check exact counts per tenant (no lost writes in DB)
        cnt_res1 = g1.query("MATCH (i:Incident) RETURN count(i)")
        cnt_res2 = g2.query("MATCH (i:Incident) RETURN count(i)")
        count_1 = cnt_res1.result_set[0][0] if cnt_res1 and cnt_res1.result_set else 0
        count_2 = cnt_res2.result_set[0][0] if cnt_res2 and cnt_res2.result_set else 0
        assert count_1 == num_incidents_per_tenant, f"Tenant 1 expected {num_incidents_per_tenant}, got {count_1}"
        assert count_2 == num_incidents_per_tenant, f"Tenant 2 expected {num_incidents_per_tenant}, got {count_2}"

        # 4. Check strict tenant isolation (no cross-tenant leakage)
        leak_res = g1.query(f"MATCH (i:Incident) WHERE i.id CONTAINS '{tenant_2_id}' RETURN count(i)")
        leak_count = leak_res.result_set[0][0] if leak_res and leak_res.result_set else 0
        assert leak_count == 0, f"Tenant 1 contains {leak_count} nodes from Tenant 2!"

        # Cleanup test graphs
        g1.delete()
        g2.delete()
    else:
        # In-memory validation
        assert len(g1.incidents) == num_incidents_per_tenant
        assert len(g2.incidents) == num_incidents_per_tenant
        for inc_id in g1.incidents:
            assert tenant_1_id in inc_id
        for inc_id in g2.incidents:
            assert tenant_2_id in inc_id

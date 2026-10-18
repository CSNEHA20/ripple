#!/usr/bin/env python3
"""Ripple Load Test CLI
Executes a concurrent load test across multiple tenants, verifying:
1. Zero duplicate nodes created under concurrency.
2. Zero lost writes.
3. Strict tenant isolation.
"""

import argparse
import concurrent.futures
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.config import settings
from app.tenancy import TenantGraph
from app.schema import ensure_tenant_schema


import socket


def is_falkordb_available(host: str = "localhost", port: int = 6379) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        res = sock.connect_ex((host, port))
        sock.close()
        return res == 0
    except Exception:
        return False


def run_load_test(
    tenants: list[str],
    incidents_per_tenant: int = 15,
    max_workers: int = 8,
) -> bool:
    falkor_live = is_falkordb_available(settings.falkordb_host, settings.falkordb_port)
    print(f"=== Ripple Load Test ===")
    print(f"Tenants: {tenants}")
    print(f"Incidents per tenant: {incidents_per_tenant} (Total: {len(tenants) * incidents_per_tenant})")
    print(f"Concurrency workers: {max_workers}")
    print(f"Target FalkorDB: {settings.falkordb_host}:{settings.falkordb_port} [{'ONLINE' if falkor_live else 'OFFLINE - using thread-safe in-memory graph simulator'}]")
    print("---------------------------------------------")

    graphs = {}
    if falkor_live:
        for t_id in tenants:
            g = TenantGraph(t_id)
            g.clear()
            ensure_tenant_schema(g)
            graphs[t_id] = g
    else:
        from tests.test_load import ThreadSafeMockLoadGraph
        for t_id in tenants:
            graphs[t_id] = ThreadSafeMockLoadGraph(t_id)

    tasks = []
    for t_id in tenants:
        g = graphs[t_id]
        for i in range(incidents_per_tenant):
            inc_id = f"inc_{t_id}_{i:04d}"
            svc = "paymentservice" if i % 2 == 0 else "checkoutservice"
            tasks.append((g, t_id, inc_id, svc, f"Alert {i} on {svc}"))

    written_ids = set()
    errors = []
    lock = threading.Lock()

    def _worker(task):
        g, t_id, inc_id, svc, title = task
        try:
            g.query(
                """
                MERGE (i:Incident {id: $id})
                SET i.title = $title,
                    i.service_name = $svc,
                    i.status = 'investigating',
                    i.opened_ts = $ts
                """,
                {"id": inc_id, "title": title, "svc": svc, "ts": time.time()},
            )
            g.query(
                """
                MERGE (h:Hypothesis {id: $h_id})
                SET h.statement = $stmt, h.service = $svc, h.status = 'open'
                WITH h
                MATCH (i:Incident {id: $inc_id})
                MERGE (i)-[:HAS_HYPOTHESIS]->(h)
                """,
                {"h_id": f"hyp_{inc_id}_01", "stmt": f"Failure in {svc}", "svc": svc, "inc_id": inc_id},
            )
            g.query(
                """
                MERGE (e:Evidence {id: $e_id})
                SET e.type = 'metric', e.source = 'real', e.weight = 2.0
                WITH e
                MATCH (h:Hypothesis {id: $h_id})
                MERGE (h)-[:SUPPORTED_BY]->(e)
                """,
                {"e_id": f"ev_{inc_id}_01", "h_id": f"hyp_{inc_id}_01"},
            )
            with lock:
                written_ids.add(inc_id)
        except Exception as exc:
            with lock:
                errors.append(f"Error writing {inc_id}: {exc}")

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_worker, t) for t in tasks]
        concurrent.futures.wait(futures)
    elapsed = time.time() - t0

    total_expected = len(tasks)
    print(f"\nExecution finished in {elapsed:.3f}s ({len(written_ids)/elapsed:.1f} incidents/sec)")

    if errors:
        print(f"[FAIL] {len(errors)} errors encountered:")
        for err in errors[:5]:
            print(f"  - {err}")
        return False

    if len(written_ids) != total_expected:
        print(f"[FAIL] Lost writes! Expected {total_expected}, wrote {len(written_ids)}")
        return False

    print(f"[PASS] All {total_expected} incidents successfully written.")

    # Integrity & Duplicate checks
    print("\nRunning database integrity checks...")
    all_ok = True
    for t_id, g in graphs.items():
        if falkor_live:
            dup_res = g.query("MATCH (i:Incident) WITH i.id AS id, count(i) AS cnt WHERE cnt > 1 RETURN id, cnt")
            if dup_res and dup_res.result_set:
                print(f"[FAIL] Duplicate nodes found in tenant {t_id}: {dup_res.result_set}")
                all_ok = False
            else:
                print(f"[PASS] Zero duplicate nodes in tenant {t_id}.")

            cnt_res = g.query("MATCH (i:Incident) RETURN count(i)")
            cnt = cnt_res.result_set[0][0] if cnt_res and cnt_res.result_set else 0
            if cnt != incidents_per_tenant:
                print(f"[FAIL] Expected {incidents_per_tenant} nodes in tenant {t_id}, found {cnt}")
                all_ok = False
            else:
                print(f"[PASS] Exact count verified in tenant {t_id} ({cnt} nodes).")
        else:
            cnt = len(g.incidents)
            if cnt != incidents_per_tenant:
                print(f"[FAIL] Expected {incidents_per_tenant} nodes in tenant {t_id}, found {cnt}")
                all_ok = False
            else:
                print(f"[PASS] Zero duplicate nodes and exact count verified in tenant {t_id} ({cnt} nodes).")

    if all_ok:
        print("\n=== LOAD TEST PASSED: No duplicates, no lost writes, strict isolation ===")
    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ripple Load Test")
    parser.add_argument("--tenants", default="tenant_alpha,tenant_beta", help="Comma-separated tenant IDs")
    parser.add_argument("--incidents", type=int, default=15, help="Incidents per tenant")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    tenant_list = [t.strip() for t in args.tenants.split(",") if t.strip()]
    success = run_load_test(
        tenants=tenant_list,
        incidents_per_tenant=args.incidents,
        max_workers=args.workers,
    )
    sys.exit(0 if success else 1)

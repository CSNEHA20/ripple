import json
import logging
import time
from typing import Any
from app.tenancy import TenantGraph
from app.temporal import apply_architecture_change
from app.ingest.embed import embed_text, cosine_similarity
from app.scenarios.catalog import (
    get_scenario,
    list_scenarios,
    list_runbooks,
    get_runbook,
)
from app.scenarios.metrics import seed_scenario_metrics

logger = logging.getLogger(__name__)


def seed_runbooks_to_graph(graph: TenantGraph) -> int:
    """Idempotently seed all runbooks from catalog into the graph as Runbook nodes.
    Links (Runbook)-[:ASSUMES]->(Service) for assumed services.
    """
    runbooks = list_runbooks()
    seeded = 0

    for rb in runbooks:
        rb_id = rb["id"]
        title = rb.get("title", "")
        desc = rb.get("description", "")
        action_class = rb.get("action_class", "needs_approval")
        steps = json.dumps(rb.get("steps", []))
        assumes = rb.get("assumes", [])
        success_count = rb.get("success_count", 0)
        fail_count = rb.get("fail_count", 0)

        cypher = """
        MERGE (rb:Runbook {id: $id})
        SET rb.title = $title,
            rb.description = $desc,
            rb.action_class = $action_class,
            rb.steps = $steps,
            rb.assumes = $assumes,
            rb.success_count = $success_count,
            rb.fail_count = $fail_count,
            rb.source = 'seeded'
        RETURN rb.id
        """
        graph.query(
            cypher,
            {
                "id": rb_id,
                "title": title,
                "desc": desc,
                "action_class": action_class,
                "steps": steps,
                "assumes": assumes,
                "success_count": success_count,
                "fail_count": fail_count,
            },
        )

        # Link (Runbook)-[:ASSUMES]->(Service)
        for pair in assumes:
            if "->" in pair:
                caller, callee = pair.split("->", 1)
                graph.query(
                    """
                    MATCH (rb:Runbook {id: $rb_id})
                    MATCH (caller:Service {name: $caller})
                    MATCH (callee:Service {name: $callee})
                    MERGE (rb)-[:ASSUMES]->(caller)
                    MERGE (rb)-[:ASSUMES]->(callee)
                    """,
                    {"rb_id": rb_id, "caller": caller.strip(), "callee": callee.strip()},
                )

        seeded += 1

    logger.info("Seeded %d runbooks into tenant %s", seeded, graph.tenant_id)
    return seeded


def load_scenario(
    graph: TenantGraph,
    scenario_id: str,
    alert_ts: float | None = None,
) -> dict[str, Any]:
    """Load a simulated scenario environment into the tenant graph.
    All created nodes and properties are tagged source='seeded'.

    Actions:
    1. Ensures runbooks exist in the tenant graph.
    2. Writes the Alert node linked to the alerting Service.
    3. Writes Deployment nodes (relative to alert time).
    4. Applies ArchitectureChange nodes (closing/opening edges via temporal module).
    5. Writes MetricSnapshot nodes (failing, degraded, and normal baselines).
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise ValueError(f"Scenario '{scenario_id}' does not exist in catalog")

    base_ts = alert_ts if alert_ts is not None else time.time()

    # 1. Ensure runbooks are available in the graph
    seed_runbooks_to_graph(graph)

    # 2. Write Alert node
    alert_info = scenario.get("alert", {})
    alert_svc = alert_info.get("service", "frontend")
    alert_text = alert_info.get("text", "Service degradation detected")
    severity = alert_info.get("severity", "CRITICAL")
    alert_id = f"alert_{scenario_id}_{int(base_ts)}"

    alert_cypher = """
    MATCH (s:Service {name: $svc})
    MERGE (a:Alert {id: $id})
    SET a.text = $text,
        a.ts = $ts,
        a.service_name = $svc,
        a.severity = $severity,
        a.scenario_id = $scenario_id,
        a.source = 'seeded'
    MERGE (a)-[:FIRED_ON]->(s)
    RETURN a.id, a.text, a.ts, a.severity
    """
    graph.query(
        alert_cypher,
        {
            "id": alert_id,
            "text": alert_text,
            "ts": float(base_ts),
            "svc": alert_svc,
            "severity": severity,
            "scenario_id": scenario_id,
        },
    )

    # 3. Write Deployment nodes
    created_deploys = []
    for dep in scenario.get("deployments", []):
        dep_svc = dep["service"]
        hours_before = float(dep.get("hours_before_alert", 1.0))
        dep_ts = base_ts - (hours_before * 3600.0)
        version = dep.get("version", "v1.0.0")
        dep_id = f"dep_{scenario_id}_{dep_svc}_{version}"

        dep_cypher = """
        MATCH (s:Service {name: $svc})
        MERGE (d:Deployment {id: $id})
        SET d.service = $svc,
            d.version = $version,
            d.ts = $ts,
            d.source = 'seeded'
        MERGE (d)-[:DEPLOYED_TO]->(s)
        RETURN d.id
        """
        graph.query(
            dep_cypher,
            {
                "id": dep_id,
                "svc": dep_svc,
                "version": version,
                "ts": float(dep_ts),
            },
        )
        created_deploys.append({"id": dep_id, "service": dep_svc, "version": version, "ts": dep_ts})

    # 4. Apply Architecture Changes
    created_arch_changes = []
    for ac in scenario.get("architecture_changes", []):
        ac_id = ac["id"]
        ac_summary = ac.get("summary", "")
        hours_before = float(ac.get("hours_before_alert", 24.0))
        ac_ts = base_ts - (hours_before * 3600.0)
        closes = ac.get("closes_edges", [])
        opens = ac.get("opens_edges", [])

        res = apply_architecture_change(
            graph=graph,
            change_id=ac_id,
            summary=ac_summary,
            ts=ac_ts,
            closes_edges=closes,
            opens_edges=opens,
            source="seeded",
        )
        created_arch_changes.append(res)

    # 5. Write MetricSnapshots (including healthy baseline for unlisted services)
    metrics_list = scenario.get("metrics", [])
    seeded_metrics = seed_scenario_metrics(
        graph=graph,
        metrics_specs=metrics_list,
        alert_ts=base_ts,
        include_baseline_for_unlisted=True,
    )

    logger.info("Successfully loaded scenario '%s' into tenant '%s'", scenario_id, graph.tenant_id)

    return {
        "status": "loaded",
        "tenant_id": graph.tenant_id,
        "scenario_id": scenario_id,
        "family": scenario.get("family"),
        "alert": {
            "id": alert_id,
            "service": alert_svc,
            "text": alert_text,
            "severity": severity,
            "ts": base_ts,
        },
        "ground_truth": scenario.get("ground_truth"),
        "deployments_created": len(created_deploys),
        "architecture_changes_applied": len(created_arch_changes),
        "metric_snapshots_created": len(seeded_metrics),
        "source": "seeded",
    }


def seed_historical_incidents(
    graph: TenantGraph,
    base_ts: float | None = None,
) -> dict[str, Any]:
    """Seed historical incidents into the graph to populate episodic and outcome memory.
    Creates Incident, Hypothesis, Intervention, Outcome nodes with real verified linkages.
    """
    now = base_ts if base_ts is not None else time.time()
    historical_scenarios = list_scenarios(family="historical")

    # Ensure runbooks exist
    seed_runbooks_to_graph(graph)

    seeded_incidents: list[dict[str, Any]] = []

    for idx, sc in enumerate(historical_scenarios):
        sc_id = sc["id"]
        # Space historical incidents out in time (7 to 45 days ago)
        days_ago = 7.0 + (idx * 5.5)
        inc_opened_ts = now - (days_ago * 86400.0)
        inc_resolved_ts = inc_opened_ts + 1800.0  # 30 mins to resolve

        alert_info = sc.get("alert", {})
        alert_svc = alert_info.get("service", "paymentservice")
        alert_text = alert_info.get("text", "")
        severity = alert_info.get("severity", "CRITICAL")
        title = sc.get("title", f"Historical Incident {sc_id}")

        gt = sc.get("ground_truth", {})
        root_svc = gt.get("root_cause_service", alert_svc)
        root_type = gt.get("root_cause_type", "bad_deploy")
        correct_rb = gt.get("correct_runbook", "rb_rollback")

        # 384-dimensional unit vector embedding for incident semantic recall
        embedding_text = f"{title} {alert_text} root_cause:{root_svc} {root_type}"
        sig_emb = embed_text(embedding_text)

        inc_id = f"inc_{sc_id}"
        alert_id = f"alert_{inc_id}"
        hypo_id = f"hypo_{inc_id}"
        interv_id = f"interv_{inc_id}_{correct_rb}"
        outcome_id = f"outcome_{inc_id}_{correct_rb}"

        # 1. Create Alert
        graph.query(
            """
            MATCH (s:Service {name: $svc})
            MERGE (a:Alert {id: $id})
            SET a.text = $text,
                a.ts = $ts,
                a.service_name = $svc,
                a.severity = $severity,
                a.source = 'seeded'
            MERGE (a)-[:FIRED_ON]->(s)
            """,
            {"id": alert_id, "text": alert_text, "ts": inc_opened_ts, "svc": alert_svc, "severity": severity},
        )

        # 2. Create Incident
        steps_taken = [
            f"Triaged {alert_svc} alert.",
            f"Traced upstream dependencies and health metrics to {root_svc}.",
            f"Identified root cause {root_type}.",
            f"Executed runbook {correct_rb}.",
            "Verified post-fix metric recovery.",
        ]
        tool_calls = ["blast_radius", "upstream_suspects", "service_health", "recent_changes", "rank_runbooks"]

        graph.query(
            """
            MERGE (inc:Incident {id: $id})
            SET inc.title = $title,
                inc.signature_embedding = $emb,
                inc.severity = $severity,
                inc.opened_ts = $opened_ts,
                inc.resolved_ts = $resolved_ts,
                inc.steps_taken = $steps,
                inc.tool_calls = $tools,
                inc.scenario_id = $scenario_id,
                inc.source = 'seeded'
            WITH inc
            MATCH (a:Alert {id: $alert_id})
            MERGE (inc)-[:TRIGGERED_BY]->(a)
            WITH inc
            MATCH (root:Service {name: $root_svc})
            MERGE (inc)-[:AFFECTED {role: 'root'}]->(root)
            """,
            {
                "id": inc_id,
                "title": title,
                "emb": sig_emb,
                "severity": severity,
                "opened_ts": inc_opened_ts,
                "resolved_ts": inc_resolved_ts,
                "steps": json.dumps(steps_taken),
                "tools": json.dumps(tool_calls),
                "scenario_id": sc_id,
                "alert_id": alert_id,
                "root_svc": root_svc,
            },
        )

        # Link impacted services
        for m in sc.get("metrics", []):
            imp_svc = m["service"]
            if imp_svc != root_svc and m.get("status") in ("failing", "degraded"):
                graph.query(
                    """
                    MATCH (inc:Incident {id: $inc_id})
                    MATCH (s:Service {name: $imp_svc})
                    MERGE (inc)-[:AFFECTED {role: 'impacted'}]->(s)
                    """,
                    {"inc_id": inc_id, "imp_svc": imp_svc},
                )

        # 3. Create winning Hypothesis (confirmed root cause)
        hypo_statement = f"{root_svc} experienced {root_type} causing system failure"
        graph.query(
            """
            MATCH (inc:Incident {id: $inc_id})
            MATCH (s:Service {name: $root_svc})
            MERGE (h:Hypothesis {id: $hypo_id})
            SET h.incident_id = $inc_id,
                h.statement = $statement,
                h.kind = 'inferred',
                h.status = 'confirmed',
                h.formed_ts = $ts,
                h.evidence_score = 9.2,
                h.margin = 5.4,
                h.source = 'seeded'
            MERGE (inc)-[:HAS_HYPOTHESIS]->(h)
            MERGE (inc)-[:ROOT_CAUSE {confirmed_ts: $resolved_ts}]->(h)
            MERGE (h)-[:ABOUT]->(s)
            """,
            {
                "inc_id": inc_id,
                "root_svc": root_svc,
                "hypo_id": hypo_id,
                "statement": hypo_statement,
                "ts": inc_opened_ts + 300.0,
                "resolved_ts": inc_resolved_ts,
            },
        )

        # 4. Create successful Intervention & Outcome (Outcome-Driven Memory)
        rb_obj = get_runbook(correct_rb)
        action_class = rb_obj.get("action_class", "needs_approval") if rb_obj else "needs_approval"

        graph.query(
            """
            MATCH (inc:Incident {id: $inc_id})
            MATCH (h:Hypothesis {id: $hypo_id})
            MATCH (rb:Runbook {id: $rb_id})
            MERGE (intv:Intervention {id: $intv_id})
            SET intv.incident_id = $inc_id,
                intv.description = $intv_desc,
                intv.runbook_id = $rb_id,
                intv.predicted_outcome = 'resolved',
                intv.action_class = $action_class,
                intv.status = 'executed',
                intv.source = 'seeded'
            MERGE (h)-[:ADDRESSED_BY]->(intv)
            MERGE (intv)-[:USES]->(rb)
            WITH intv
            MERGE (out:Outcome {id: $outcome_id})
            SET out.intervention_id = $intv_id,
                out.observed = 'resolved',
                out.ts = $resolved_ts,
                out.source = 'seeded'
            MERGE (intv)-[:VALIDATED_BY {result: 'validates'}]->(out)
            """,
            {
                "inc_id": inc_id,
                "hypo_id": hypo_id,
                "rb_id": correct_rb,
                "intv_id": interv_id,
                "intv_desc": f"Applied {correct_rb} to fix {root_type}",
                "action_class": action_class,
                "outcome_id": outcome_id,
                "resolved_ts": inc_resolved_ts,
            },
        )

        # 5. Record first-class failed fix in memory if applicable (e.g. inc_hist_01 where restart failed)
        interventions_map = sc.get("interventions", {})
        for failed_rb, outcome_status in interventions_map.items():
            if failed_rb != correct_rb and outcome_status == "failed":
                failed_intv_id = f"interv_{inc_id}_{failed_rb}_failed"
                failed_outcome_id = f"outcome_{inc_id}_{failed_rb}_failed"
                failed_rb_obj = get_runbook(failed_rb)
                failed_action_class = (
                    failed_rb_obj.get("action_class", "needs_approval") if failed_rb_obj else "needs_approval"
                )

                graph.query(
                    """
                    MATCH (h:Hypothesis {id: $hypo_id})
                    MATCH (rb:Runbook {id: $rb_id})
                    MERGE (intv:Intervention {id: $intv_id})
                    SET intv.incident_id = $inc_id,
                        intv.description = $intv_desc,
                        intv.runbook_id = $rb_id,
                        intv.predicted_outcome = 'resolved',
                        intv.action_class = $action_class,
                        intv.status = 'executed',
                        intv.source = 'seeded'
                    MERGE (h)-[:ADDRESSED_BY]->(intv)
                    MERGE (intv)-[:USES]->(rb)
                    WITH intv
                    MERGE (out:Outcome {id: $outcome_id})
                    SET out.intervention_id = $intv_id,
                        out.observed = 'failed',
                        out.ts = $failed_ts,
                        out.source = 'seeded'
                    MERGE (intv)-[:VALIDATED_BY {result: 'rejects'}]->(out)
                    """,
                    {
                        "hypo_id": hypo_id,
                        "inc_id": inc_id,
                        "rb_id": failed_rb,
                        "intv_id": failed_intv_id,
                        "intv_desc": f"Attempted {failed_rb} prior to resolution (failed)",
                        "action_class": failed_action_class,
                        "outcome_id": failed_outcome_id,
                        "failed_ts": inc_opened_ts + 600.0,
                    },
                )

        # 6. Link to top owner of root service via HANDLED_BY
        owner_res = graph.query(
            """
            MATCH (p:Person)-[c:COMMITTED]->(s:Service {name: $svc})
            RETURN p.login
            ORDER BY c.n DESC LIMIT 1
            """,
            {"svc": root_svc},
        )
        if owner_res and owner_res.result_set:
            top_login = owner_res.result_set[0][0]
            graph.query(
                """
                MATCH (inc:Incident {id: $inc_id})
                MATCH (p:Person {login: $login})
                MERGE (inc)-[:HANDLED_BY]->(p)
                """,
                {"inc_id": inc_id, "login": top_login},
            )

        seeded_incidents.append({
            "id": inc_id,
            "title": title,
            "root_service": root_svc,
            "correct_runbook": correct_rb,
            "embedding": sig_emb,
        })

    # 7. Create SIMILAR_TO edges between historical incidents based on semantic embedding similarity
    for i in range(len(seeded_incidents)):
        for j in range(i + 1, len(seeded_incidents)):
            inc_a = seeded_incidents[i]
            inc_b = seeded_incidents[j]
            sim = cosine_similarity(inc_a["embedding"], inc_b["embedding"])
            if sim > 0.4:
                graph.query(
                    """
                    MATCH (a:Incident {id: $id_a})
                    MATCH (b:Incident {id: $id_b})
                    MERGE (a)-[r:SIMILAR_TO]->(b)
                    SET r.score = $score
                    MERGE (b)-[r2:SIMILAR_TO]->(a)
                    SET r2.score = $score
                    """,
                    {"id_a": inc_a["id"], "id_b": inc_b["id"], "score": round(sim, 4)},
                )

    logger.info("Successfully seeded %d historical incidents into tenant %s", len(seeded_incidents), graph.tenant_id)

    return {
        "status": "seeded",
        "tenant_id": graph.tenant_id,
        "count": len(seeded_incidents),
        "incidents": [inc["id"] for inc in seeded_incidents],
    }

import time
from typing import Any
from app.config import settings
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.tools.changes import recent_changes
from app.tools.incidents import service_health, similar_incidents
from app.tools.paths import path_between


def gather_evidence_for_hypotheses(
    graph: TenantGraph,
    hypotheses: list[dict[str, Any]],
    alerting_service: str,
    alert_text: str = "",
    as_of: float | None = None,
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], Trace]:
    """Gather supporting and contradicting evidence for each candidate hypothesis.
    Generates Evidence items with:
      - kind: 'observed' (direct graph reading) or 'inferred' (reasoning/similarity)
      - polarity: 'support' vs 'contradict'
      - type: dependency_path, recent_deploy, metric, past_incident, architecture_change, decision, doc
      - freshness & weight

    Returns:
      evidence_by_hyp_id: {
        hyp_id: {
          "supporting": [EvidenceDict, ...],
          "contradicting": [EvidenceDict, ...]
        }
      }
      trace: Trace object containing all queries and reasoning steps
    """
    start_time = time.time()
    trace = Trace()
    ref_ts = float(as_of) if as_of is not None else time.time()

    # Pre-fetch candidate service health metrics in one call
    candidate_services = list({h["service"] for h in hypotheses})
    health_res = service_health(graph, services=candidate_services, ts=ref_ts)
    trace.merge(health_res.trace)
    health_map: dict[str, dict[str, Any]] = {
        item["service"]: item for item in health_res.data.get("health", [])
    }

    # Pre-fetch similar incidents if alert text is present
    sim_incidents: list[dict[str, Any]] = []
    if alert_text:
        sim_res = similar_incidents(
            graph,
            alert_text=alert_text,
            services=[alerting_service],
            k=5,
        )
        trace.merge(sim_res.trace)
        sim_incidents = sim_res.data.get("matches", [])

    # Check which candidate services had deployments in the entire graph
    # to recognize if another service deployed while this one didn't
    all_deployments: dict[str, list[dict[str, Any]]] = {}
    for svc in candidate_services:
        rc_res = recent_changes(graph, service=svc, hours=48.0, as_of=ref_ts)
        trace.merge(rc_res.trace)
        all_deployments[svc] = rc_res.data.get("deployments", [])

    has_any_fresh_deploy = any(
        any(d.get("hours_before_ref", 99) <= 6.0 for d in deps)
        for deps in all_deployments.values()
    )

    evidence_by_hyp: dict[str, dict[str, list[dict[str, Any]]]] = {}
    total_evidence_count = 0

    for hyp in hypotheses:
        hyp_id = hyp["id"]
        svc = hyp["service"]
        hops = hyp.get("hops", 99)

        supporting: list[dict[str, Any]] = []
        contradicting: list[dict[str, Any]] = []

        def add_ev(
            ev_type: str,
            polarity: str,
            summary: str,
            source_ref: str,
            observed_ts: float,
            kind: str = "observed",
        ) -> None:
            nonlocal total_evidence_count
            total_evidence_count += 1
            ev_id = f"ev_{hyp_id}_{ev_type}_{polarity}_{len(supporting) + len(contradicting) + 1}"
            base_wt = settings.evidence_weights.get(ev_type, 1.0)

            # Freshness decay calculation
            half_life = settings.evidence_half_lives_hours.get(ev_type)
            if half_life is None or half_life <= 0:
                freshness = 1.0
            else:
                age_hours = max(0.0, (ref_ts - observed_ts) / 3600.0)
                freshness = round(0.5 ** (age_hours / half_life), 4)

            ev = {
                "id": ev_id,
                "hypothesis_id": hyp_id,
                "service": svc,
                "type": ev_type,
                "kind": kind,
                "polarity": polarity,
                "summary": summary,
                "source_ref": source_ref,
                "observed_ts": observed_ts,
                "freshness": freshness,
                "weight": base_wt,
            }
            if polarity == "support":
                supporting.append(ev)
            else:
                contradicting.append(ev)

        # -------------------------------------------------------------
        # 1. Dependency Path Evidence
        # -------------------------------------------------------------
        if svc == alerting_service:
            add_ev(
                ev_type="dependency_path",
                polarity="support",
                summary=f"Alert origin: '{svc}' is the directly alerting service.",
                source_ref=svc,
                observed_ts=ref_ts,
                kind="observed",
            )
        elif hops < 99:
            add_ev(
                ev_type="dependency_path",
                polarity="support",
                summary=f"Active dependency path: '{alerting_service}' depends on '{svc}' ({hops} hop(s) upstream).",
                source_ref=f"{alerting_service}->{svc}",
                observed_ts=ref_ts,
                kind="observed",
            )
        else:
            # Check via path_between tool if any path exists
            p_res = path_between(graph, caller=alerting_service, callee=svc, as_of=ref_ts)
            trace.merge(p_res.trace)
            if p_res.data.get("path_exists"):
                p_len = len(p_res.data.get("path_edges", []))
                add_ev(
                    ev_type="dependency_path",
                    polarity="support",
                    summary=f"Active dependency path: '{alerting_service}' connects to '{svc}' ({p_len} hop(s)).",
                    source_ref=f"{alerting_service}->{svc}",
                    observed_ts=ref_ts,
                    kind="observed",
                )
            else:
                add_ev(
                    ev_type="dependency_path",
                    polarity="contradict",
                    summary=f"No active dependency path from alerting service '{alerting_service}' to '{svc}' in current graph.",
                    source_ref=f"{alerting_service}->{svc}",
                    observed_ts=ref_ts,
                    kind="observed",
                )

        # -------------------------------------------------------------
        # 2. Recent Deployment Evidence
        # -------------------------------------------------------------
        svc_deploys = all_deployments.get(svc, [])
        if svc_deploys:
            # Find closest deployment
            closest_deploy = min(svc_deploys, key=lambda d: d.get("hours_before_ref", 999))
            hours_ago = closest_deploy.get("hours_before_ref", 0.0)
            dep_id = closest_deploy.get("id", f"dep_{svc}")
            dep_ver = closest_deploy.get("version", "latest")
            dep_ts = closest_deploy.get("ts", ref_ts)

            if hours_ago <= 6.0:
                add_ev(
                    ev_type="recent_deploy",
                    polarity="support",
                    summary=f"Recent deployment {dep_ver} on '{svc}' shipped {hours_ago:.1f}h before the alert.",
                    source_ref=dep_id,
                    observed_ts=dep_ts,
                    kind="observed",
                )
            else:
                add_ev(
                    ev_type="recent_deploy",
                    polarity="contradict",
                    summary=f"Deployment {dep_ver} on '{svc}' is {hours_ago:.1f}h old (outside the immediate regression window).",
                    source_ref=dep_id,
                    observed_ts=dep_ts,
                    kind="observed",
                )
        else:
            if has_any_fresh_deploy:
                add_ev(
                    ev_type="recent_deploy",
                    polarity="contradict",
                    summary=f"No recent deployments on '{svc}' in the change window, while competing suspects had fresh releases.",
                    source_ref=svc,
                    observed_ts=ref_ts,
                    kind="observed",
                )

        # -------------------------------------------------------------
        # 3. Metric Snapshot Evidence
        # -------------------------------------------------------------
        if svc in health_map:
            snap = health_map[svc]
            status = snap.get("status", "normal")
            snap_id = snap.get("snapshot_id", f"metric_{svc}")
            snap_ts = snap.get("ts", ref_ts)
            latency = snap.get("latency_p95_ms", 0.0)
            err_rate = snap.get("error_rate", 0.0)

            if status in ("failing", "degraded"):
                add_ev(
                    ev_type="metric",
                    polarity="support",
                    summary=f"MetricSnapshot shows '{svc}' is {status} (p95 latency: {latency}ms, error rate: {err_rate:.1%}).",
                    source_ref=snap_id,
                    observed_ts=snap_ts,
                    kind="observed",
                )
            else:
                add_ev(
                    ev_type="metric",
                    polarity="contradict",
                    summary=f"MetricSnapshot shows '{svc}' is healthy/normal (p95 latency: {latency}ms, error rate: {err_rate:.1%}).",
                    source_ref=snap_id,
                    observed_ts=snap_ts,
                    kind="observed",
                )

        # -------------------------------------------------------------
        # 4. Past Incident Memory Evidence
        # -------------------------------------------------------------
        if sim_incidents:
            for inc in sim_incidents:
                sim_score = inc.get("similarity_score", 0.0)
                if sim_score < 0.35:
                    continue
                inc_id = inc["incident_id"]
                inc_title = inc.get("title", "")
                inc_opened = inc.get("opened_ts", ref_ts)
                root_stmt = (inc.get("root_cause_statement") or "").lower()
                aff_svcs = inc.get("affected_services", [])
                resolved_rb = inc.get("resolved_runbook")
                failed_rbs = inc.get("failed_runbooks", [])

                # Check if this incident specifically implicates service `svc`
                if svc.lower() in root_stmt or (svc in aff_svcs and "root" in str(aff_svcs)):
                    if resolved_rb:
                        add_ev(
                            ev_type="past_incident",
                            polarity="support",
                            summary=f"Past incident {inc_id} ('{inc_title}') had root cause '{svc}' and verified fix '{resolved_rb}' (similarity {sim_score:.2f}).",
                            source_ref=inc_id,
                            observed_ts=inc_opened,
                            kind="inferred",
                        )
                    if failed_rbs:
                        add_ev(
                            ev_type="past_incident",
                            polarity="contradict",
                            summary=f"Past incident {inc_id} recorded failed fixes on '{svc}': {', '.join(failed_rbs)}.",
                            source_ref=inc_id,
                            observed_ts=inc_opened,
                            kind="inferred",
                        )
                elif sim_score >= 0.65 and aff_svcs and svc not in aff_svcs:
                    # High similarity incident pointing to a completely different subsystem contradicts `svc`
                    add_ev(
                        ev_type="past_incident",
                        polarity="contradict",
                        summary=f"High-similarity incident {inc_id} ({sim_score:.2f}) pointed to alternate services: {', '.join(aff_svcs)}.",
                        source_ref=inc_id,
                        observed_ts=inc_opened,
                        kind="inferred",
                    )

        # -------------------------------------------------------------
        # 5. Architecture Changes & Decisions/Docs
        # -------------------------------------------------------------
        # 5. Architecture Decisions & Docs (Relevant to incident behavior)
        # -------------------------------------------------------------
        alert_terms = {t.lower() for t in (alert_text or "").replace(":", " ").replace("-", " ").replace(">", " ").split() if len(t) >= 4}
        incident_keywords = {"latency", "timeout", "error", "down", "fail", "leak", "pool", "exhaust", "memory", "deadlock", "spike", "drop", "overflow", "buffer", "crypto", "auth"}

        cypher_dec = """
        MATCH (d:Decision)-[:CONCERNS]->(s:Service {name: $svc})
        RETURN d.id AS id, d.summary AS summary, d.status AS status, d.ts AS ts
        LIMIT 3
        """
        dec_res = graph.query(cypher_dec, {"svc": svc})
        if dec_res and dec_res.result_set:
            for d_row in dec_res.result_set:
                d_id, d_summary, d_status, d_ts = d_row
                d_timestamp = float(d_ts or ref_ts)
                summary_lower = (d_summary or "").lower()
                is_relevant = any(term in summary_lower for term in alert_terms.union(incident_keywords))

                if str(d_status).lower() == "superseded":
                    add_ev(
                        ev_type="decision",
                        polarity="contradict",
                        summary=f"Decision {d_id} ('{d_summary}') concerning '{svc}' is superseded and inactive.",
                        source_ref=d_id,
                        observed_ts=d_timestamp,
                        kind="observed",
                    )
                elif is_relevant:
                    add_ev(
                        ev_type="decision",
                        polarity="support",
                        summary=f"Active Decision {d_id} ('{d_summary}') explains configuration behavior of '{svc}'.",
                        source_ref=d_id,
                        observed_ts=d_timestamp,
                        kind="observed",
                    )

        # Stale doc check
        cypher_doc = """
        MATCH (doc:Doc)-[:DESCRIBES]->(s:Service {name: $svc})
        RETURN doc.id AS id, doc.title AS title, doc.last_verified_ts AS verified_ts
        LIMIT 2
        """
        doc_res = graph.query(cypher_doc, {"svc": svc})
        if doc_res and doc_res.result_set:
            for doc_row in doc_res.result_set:
                doc_id, doc_title, doc_ver_ts = doc_row
                v_ts = float(doc_ver_ts or ref_ts)
                # Stale if verified > 60 days ago
                if (ref_ts - v_ts) > 60.0 * 86400.0:
                    add_ev(
                        ev_type="doc",
                        polarity="contradict",
                        summary=f"Documentation '{doc_title}' ({doc_id}) for '{svc}' is stale and unverified (>60 days old).",
                        source_ref=doc_id,
                        observed_ts=v_ts,
                        kind="observed",
                    )
                else:
                    title_lower = (doc_title or "").lower()
                    if any(term in title_lower for term in alert_terms.union(incident_keywords)):
                        add_ev(
                            ev_type="doc",
                            polarity="support",
                            summary=f"Verified documentation '{doc_title}' ({doc_id}) explains behavior of '{svc}'.",
                            source_ref=doc_id,
                            observed_ts=v_ts,
                            kind="observed",
                        )

        evidence_by_hyp[hyp_id] = {
            "supporting": supporting,
            "contradicting": contradicting,
        }

    step = TraceStep(
        tool="gather_evidence",
        cypher="Evaluated dependency paths, deployments, metric health, past incidents, decisions, and documentation across candidate services",
        params={"alerting_service": alerting_service, "hypotheses_count": len(hypotheses)},
        node_ids=[h["service"] for h in hypotheses],
        edge_ids=[],
        summary=f"Gathered {total_evidence_count} evidence items (both supporting and contradicting) for {len(hypotheses)} hypotheses.",
        rows_count=total_evidence_count,
        duration_ms=(time.time() - start_time) * 1000.0,
    )
    trace.add_step(step)

    return evidence_by_hyp, trace

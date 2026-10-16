import json
import logging
import re
import time
import uuid
from typing import Any
from pydantic import BaseModel, Field
from app.tenancy import TenantGraph
from app.trace import Trace, TraceStep
from app.ingest.embed import embed_text, cosine_similarity, query_vector_index
from app.tools.blast_radius import blast_radius
from app.tools.people import who_knows
from app.brain.freshness import check_docs_freshness
from app.agents.llm import LLMWrapper

logger = logging.getLogger("ripple.brain.ask")

KNOWN_SERVICES = [
    "frontend",
    "paymentservice",
    "checkoutservice",
    "cartservice",
    "currencyservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
    "emailservice",
    "adservice",
    "redis-cart",
]


class BrainAnswerSchema(BaseModel):
    intent: str
    summary_answer: str
    detailed_answer: str
    cited_node_ids: list[str] = Field(default_factory=list)
    is_superseded: bool = False
    is_stale: bool = False


def extract_service_name(query: str) -> str | None:
    """Extract known service name from natural language query."""
    q_lower = query.lower()
    for svc in KNOWN_SERVICES:
        if svc in q_lower:
            return svc
    # Match service without 'service' suffix (e.g. 'payment' -> 'paymentservice')
    for svc in KNOWN_SERVICES:
        short = svc.replace("service", "")
        if len(short) > 3 and short in q_lower:
            return svc
    return None


def extract_runbook_id(query: str) -> str:
    """Extract runbook keyword or ID from query."""
    q_lower = query.lower()
    match = re.search(r"\b(rb_[a-zA-Z0-9_\-]+)\b", q_lower)
    if match:
        return match.group(1)
    for kw in ["rollback", "restart", "scale_up", "cache_flush", "db_reconnect", "circuit_breaker", "rate_limit"]:
        if kw in q_lower or kw.replace("_", " ") in q_lower:
            return f"rb_{kw}"
    return "rb_rollback"


def classify_intent(query: str) -> str:
    """Classify user question into one of the 6 target intents:
    - 'ownership': who owns, who knows, committers, maintainers
    - 'lineage': why did we choose X, decisions, architecture choices, supersedes
    - 'impact': what breaks, what fails, blast radius, cascade
    - 'freshness': stale docs, outdated, out of date, doc verification
    - 'outcome_history': has fix failed, has runbook failed, success rate, ever failed
    - 'free_form': default general inquiry
    """
    q_lower = query.lower()

    # Freshness
    if any(k in q_lower for k in ["out of date", "stale", "freshness", "outdated", "docs describing", "which docs"]):
        return "freshness"

    # Outcome history
    if any(k in q_lower for k in ["ever fail", "failed, and when", "has fix", "has rollback", "has restart", "success rate"]):
        return "outcome_history"

    # Lineage
    if any(k in q_lower for k in ["why did we", "why do we", "decision", "choose", "chose", "lineage", "adrs", "supersede"]):
        return "lineage"

    # Impact
    if any(k in q_lower for k in ["what breaks", "goes down", "fails instead", "what happens if", "blast radius", "impact if"]):
        return "impact"

    # Ownership
    if any(k in q_lower for k in ["who owns", "who know", "who actually knows", "maintainer", "committers", "author"]):
        return "ownership"

    return "free_form"


def check_read_only_cypher(cypher: str) -> bool:
    """Guardrail: Ensure Cypher queries executed via brain are strictly read-only."""
    clean = cypher.strip().upper()
    disallowed = ["CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP", "DETACH"]
    for word in disallowed:
        # Match whole keyword
        if re.search(rf"\b{word}\b", clean):
            return False
    return clean.startswith("MATCH") or clean.startswith("WITH") or clean.startswith("RETURN")


# ============================================================================
# Intent Query Handlers
# ============================================================================

def handle_ownership(graph: TenantGraph, query: str, service: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], Trace]:
    """Answer who owns and who actually knows a service."""
    trace = Trace()
    target_svc = service or extract_service_name(query) or "paymentservice"

    # 1. Formal Owner
    owner_cypher = """
    MATCH (s:Service {name: $service})
    OPTIONAL MATCH (p:Person)-[:OWNS]->(s)
    RETURN p.login AS owner_login, p.name AS owner_name, s.name AS service, s.tier AS tier
    """
    res = graph.query(owner_cypher, {"service": target_svc})
    formal_owner = None
    service_tier = "tier-2"
    if res and res.result_set and res.result_set[0][0]:
        r = res.result_set[0]
        formal_owner = {"login": r[0], "name": r[1]}
        service_tier = r[3] or "tier-2"

    # 2. Recency-weighted expertise from who_knows tool
    wk_res = who_knows(graph, service=target_svc, k=3)
    trace.merge(wk_res.trace)
    experts = wk_res.data.get("experts", []) if isinstance(wk_res.data, dict) else []

    sources = [{"id": target_svc, "type": "Service", "title": f"Service: {target_svc}"}]
    if formal_owner:
        sources.append({"id": formal_owner["login"], "type": "Person", "title": f"Owner: {formal_owner['name']}"})
    for exp in experts:
        sources.append({"id": exp["person"], "type": "Person", "title": f"Committer: {exp['name']}"})

    data = {
        "service": target_svc,
        "tier": service_tier,
        "formal_owner": formal_owner,
        "top_experts": experts,
    }
    return data, sources, trace


def handle_lineage(graph: TenantGraph, query: str) -> tuple[dict[str, Any], list[dict[str, Any]], Trace]:
    """Answer architectural decision lineage questions with full supersedes lineage."""
    start_time = time.time()
    trace = Trace()

    # Search decisions by vector similarity or keywords
    q_emb = embed_text(query)
    vec_hits = query_vector_index(graph, "Decision", "embedding", q_emb, k=5)
    matched_vec_ids = set()
    if vec_hits:
        for hit in vec_hits:
            d_node = hit["node"]
            did = getattr(d_node, "properties", {}).get("id") or getattr(d_node, "id", None)
            if did:
                matched_vec_ids.add(did)

    q_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query.lower()) if w not in ("why", "did", "the", "for", "and", "our", "what")]
    params: dict[str, Any] = {}

    cypher = """
    MATCH (d:Decision)
    OPTIONAL MATCH (d)-[:CONCERNS]->(s:Service)
    OPTIONAL MATCH (d)-[:DERIVED_FROM]->(src)
    OPTIONAL MATCH (d)-[:SUPERSEDES]->(old_d:Decision)
    OPTIONAL MATCH (new_d:Decision)-[:SUPERSEDES]->(d)
    RETURN d.id AS id,
           d.summary AS summary,
           d.status AS status,
           d.ts AS ts,
           s.name AS service,
           labels(src)[0] AS src_type,
           src.id AS src_id,
           src.number AS src_num,
           src.url AS src_url,
           old_d.id AS supersedes_id,
           old_d.summary AS supersedes_summary,
           new_d.id AS superseded_by_id,
           new_d.summary AS superseded_by_summary
    """
    res = graph.query(cypher)
    duration_ms = (time.time() - start_time) * 1000.0

    decisions: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    has_superseded = False

    if res and res.result_set:
        for r in res.result_set:
            d_id, summary, status, ts, svc, src_type, src_id, src_num, src_url, old_id, old_sum, new_id, new_sum = r
            # Check keyword relevance
            text_to_search = f"{d_id} {summary} {svc}".lower()
            matches = (d_id in matched_vec_ids) or (any(word in text_to_search for word in q_words) if q_words else True)
            if matches:
                is_sup = (status == "superseded") or (new_id is not None)
                if is_sup:
                    has_superseded = True
                dec_entry = {
                    "id": d_id,
                    "summary": summary,
                    "status": "superseded" if is_sup else "active",
                    "ts": ts,
                    "service": svc,
                    "source": {"type": src_type, "number": src_num, "url": src_url},
                    "supersedes": {"id": old_id, "summary": old_sum} if old_id else None,
                    "superseded_by": {"id": new_id, "summary": new_sum} if new_id else None,
                }
                decisions.append(dec_entry)
                sources.append({"id": d_id, "type": "Decision", "title": summary, "url": src_url})

    step = TraceStep(
        tool="decision_lineage",
        cypher=cypher.strip(),
        params=params,
        node_ids=[d["id"] for d in decisions],
        edge_ids=[],
        summary=f"Found {len(decisions)} architectural decisions matching query.",
        rows_count=len(decisions),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "decisions": decisions,
        "has_superseded": has_superseded,
        "query_keywords": q_words,
    }
    return data, sources, trace


def handle_impact(graph: TenantGraph, query: str, service: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], Trace]:
    """Answer what breaks if a service goes down using blast radius traversal."""
    trace = Trace()
    target_svc = service or extract_service_name(query) or "currencyservice"

    blast_res = blast_radius(graph, service=target_svc, max_depth=4)
    trace.merge(blast_res.trace)

    blast_data = blast_res.data if hasattr(blast_res, "data") else blast_res
    affected = blast_data.get("affected_services", []) if isinstance(blast_data, dict) else (blast_data or [])
    impacted_svcs = [b["service"] for b in affected if isinstance(b, dict) and b.get("service") != target_svc]

    sources = [{"id": target_svc, "type": "Service", "title": f"Failing Service: {target_svc}"}]
    for b in affected:
        sources.append({"id": b["service"], "type": "Service", "title": f"Affected ({b.get('hops', 1)} hops): {b['service']}"})

    data = {
        "failing_service": target_svc,
        "total_impacted": len(impacted_svcs),
        "impacted_services": impacted_svcs,
        "details": affected,
        "uncertainty_note": blast_data.get("uncertainty_note", "") if isinstance(blast_data, dict) else "",
    }
    return data, sources, trace


def handle_freshness(graph: TenantGraph, query: str, service: str | None) -> tuple[dict[str, Any], list[dict[str, Any]], Trace]:
    """Answer which documentation files describing a service might be out of date."""
    target_svc = service or extract_service_name(query)
    stale_docs, trace = check_docs_freshness(graph, service=target_svc)

    sources = []
    for d in stale_docs:
        sources.append({
            "id": d["doc_id"],
            "type": "Doc",
            "title": f"Doc: {d['title']}",
            "url": d.get("url"),
            "badge": d.get("freshness_badge"),
        })

    data = {
        "target_service": target_svc,
        "stale_docs": stale_docs,
        "total_stale": len(stale_docs),
        "is_stale": len(stale_docs) > 0,
    }
    return data, sources, trace


def handle_outcome_history(graph: TenantGraph, query: str) -> tuple[dict[str, Any], list[dict[str, Any]], Trace]:
    """Answer if and when a specific operational fix has failed in past incidents."""
    start_time = time.time()
    trace = Trace()
    target_rb = extract_runbook_id(query)

    cypher = """
    MATCH (rb:Runbook)
    WHERE toLower(rb.id) CONTAINS toLower($target_rb) OR toLower(rb.title) CONTAINS toLower($target_rb)
    OPTIONAL MATCH (intv:Intervention)-[:USES]->(rb)
    OPTIONAL MATCH (intv)-[val:VALIDATED_BY]->(out:Outcome)
    OPTIONAL MATCH (ar:AgentRun)-[:WORKED_ON]->(i:Incident)
    WHERE (intv)-[:IMPLEMENTS|PROPOSED_FOR|ABOUT*1..2]-(ar) OR (i)-[:AFFECTED|HAS_HYPOTHESIS*1..3]-(intv)
    RETURN rb.id AS runbook_id,
           rb.title AS title,
           rb.success_count AS successes,
           rb.fail_count AS failures,
           rb.historical_success_rate AS rate,
           collect(DISTINCT {
               outcome_id: out.id,
               observed: out.observed,
               ts: out.ts,
               incident_id: i.id
           }) AS raw_outcomes
    """
    res = graph.query(cypher, {"target_rb": target_rb.replace("rb_", "")})
    duration_ms = (time.time() - start_time) * 1000.0

    runbooks_found: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    has_failed_records = False

    if res and res.result_set:
        for r in res.result_set:
            rb_id, title, s_cnt, f_cnt, rate, raw_outs = r
            failures = [o for o in raw_outs if o and o.get("observed") == "failed"]
            if failures:
                has_failed_records = True

            rb_entry = {
                "runbook_id": rb_id,
                "title": title,
                "success_count": float(s_cnt or 0.0),
                "fail_count": float(f_cnt or 0.0),
                "historical_success_rate": float(rate or 0.5),
                "has_failed_before": len(failures) > 0,
                "failed_occurrences": failures,
                "all_recorded_outcomes": [o for o in raw_outs if o and o.get("observed")],
            }
            runbooks_found.append(rb_entry)
            sources.append({"id": rb_id, "type": "Runbook", "title": f"Runbook: {title}"})
            for fail in failures:
                if fail.get("outcome_id"):
                    sources.append({"id": fail["outcome_id"], "type": "Outcome", "title": f"Failed outcome in {fail.get('incident_id', 'incident')}"})

    step = TraceStep(
        tool="outcome_history",
        cypher=cypher.strip(),
        params={"target_rb": target_rb},
        node_ids=[rb["runbook_id"] for rb in runbooks_found],
        edge_ids=[],
        summary=f"Outcome memory for '{target_rb}': recorded {len(runbooks_found)} matching runbook(s). Has failed: {has_failed_records}.",
        rows_count=len(runbooks_found),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {
        "queried_runbook": target_rb,
        "runbooks": runbooks_found,
        "has_failed_before": has_failed_records,
    }
    return data, sources, trace


def handle_free_form(graph: TenantGraph, query: str) -> tuple[dict[str, Any], list[dict[str, Any]], Trace]:
    """Free-form knowledge search over Decisions, Docs, and PRs."""
    start_time = time.time()
    trace = Trace()

    # Search decisions and docs via text matching
    q_words = [w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query.lower()) if w not in ("what", "how", "the", "our", "why", "who", "when")]
    primary_word = q_words[0] if q_words else "service"

    cypher = """
    MATCH (n)
    WHERE (n:Decision OR n:Doc OR n:PullRequest)
      AND (toLower(n.summary) CONTAINS $term OR toLower(n.title) CONTAINS $term OR toLower(n.text) CONTAINS $term)
    RETURN labels(n)[0] AS type, n.id AS id, n.title AS title, n.summary AS summary, n.url AS url
    LIMIT 5
    """
    res = graph.query(cypher, {"term": primary_word})
    duration_ms = (time.time() - start_time) * 1000.0

    matches: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    if res and res.result_set:
        for r in res.result_set:
            lbl, nid, title, summary, url = r
            name = title or summary or nid
            matches.append({"type": lbl, "id": nid, "title": name, "url": url})
            sources.append({"id": nid, "type": lbl, "title": name, "url": url})

    step = TraceStep(
        tool="free_form_search",
        cypher=cypher.strip(),
        params={"term": primary_word},
        node_ids=[m["id"] for m in matches],
        edge_ids=[],
        summary=f"Free-form search on '{primary_word}': returned {len(matches)} graph nodes.",
        rows_count=len(matches),
        duration_ms=duration_ms,
    )
    trace.add_step(step)

    data = {"query": query, "matches": matches}
    return data, sources, trace


# ============================================================================
# Main Ask Brain Entrypoint
# ============================================================================

def ask_brain(
    graph: TenantGraph,
    question: str,
    tenant_id: str = "storefront",
    mode: str = "replay",
) -> tuple[dict[str, Any], Trace]:
    """Ask the Company-Brain a natural language question with strict graph citations,
    supersedes tracking, and documentation freshness checks.
    Persists Question and Answer nodes linked via [:ANSWERED_BY] and [:CITES] to sources.
    """
    trace = Trace()
    intent = classify_intent(question)
    svc_name = extract_service_name(question)

    # 1. Route to parameterized handler based on classified intent
    is_superseded = False
    is_stale = False

    if intent == "ownership":
        data, sources, sub_trace = handle_ownership(graph, question, svc_name)
    elif intent == "lineage":
        data, sources, sub_trace = handle_lineage(graph, question)
        is_superseded = data.get("has_superseded", False)
    elif intent == "impact":
        data, sources, sub_trace = handle_impact(graph, question, svc_name)
    elif intent == "freshness":
        data, sources, sub_trace = handle_freshness(graph, question, svc_name)
        is_stale = data.get("is_stale", False)
    elif intent == "outcome_history":
        data, sources, sub_trace = handle_outcome_history(graph, question)
    else:
        data, sources, sub_trace = handle_free_form(graph, question)

    trace.merge(sub_trace)

    # 2. Compose grounded answer using LLMWrapper
    valid_ids = [s["id"] for s in sources if s.get("id")]
    llm = LLMWrapper(mode=mode)

    def fallback_gen(ctx: dict[str, Any], enforce_citations: list[str] | None = None) -> dict[str, Any]:
        cites = enforce_citations or valid_ids
        cite_str = f" [{cites[0]}]" if cites else ""

        if intent == "ownership":
            formal = data.get("formal_owner")
            owner_str = f"{formal['name']} ({formal['login']})" if formal else "No direct code owner configured"
            experts = [f"{e['person']} ({e['commits']} commits, recency {e['recency_score']})" for e in data.get("top_experts", [])]
            exp_str = ", ".join(experts) if experts else "None"
            ans = f"Formal owner for {data['service']}: {owner_str}. Top active maintainers by commit recency: {exp_str}{cite_str}."
        elif intent == "lineage":
            decs = data.get("decisions", [])
            lines = []
            for d in decs[:2]:
                sup_note = f" (SUPERSEDED by {d['superseded_by']['id']})" if d.get("superseded_by") else ""
                lines.append(f"{d['id']}: {d['summary']}{sup_note}")
            ans = "Found architectural decisions: " + " | ".join(lines) + f"{cite_str}."
        elif intent == "impact":
            impacted = ", ".join(data.get("impacted_services", [])[:4]) or "none"
            ans = f"If {data['failing_service']} fails, blast radius impacts {data['total_impacted']} downstream service(s): [{impacted}]{cite_str}."
        elif intent == "freshness":
            stale = data.get("stale_docs", [])
            lines = [f"{d['title']} ({d['freshness_badge']})" for d in stale]
            ans = f"Documentation freshness check: {len(stale)} out-of-date doc(s) found: " + "; ".join(lines) + f"{cite_str}."
        elif intent == "outcome_history":
            rbs = data.get("runbooks", [])
            if rbs and data.get("has_failed_before"):
                rb = rbs[0]
                ans = f"Fix '{rb['runbook_id']}' HAS previously failed in recorded incidents (fail count: {rb['fail_count']}, historical success rate: {rb['historical_success_rate']:.1%}){cite_str}."
            elif rbs:
                rb = rbs[0]
                ans = f"Fix '{rb['runbook_id']}' has no recorded failures in graph memory (success rate: {rb['historical_success_rate']:.1%}){cite_str}."
            else:
                ans = f"No prior outcome memory found for requested runbook{cite_str}."
        else:
            ans = f"Graph Q&A retrieved {len(sources)} related item(s){cite_str}."

        return {
            "intent": intent,
            "summary_answer": ans,
            "detailed_answer": ans,
            "cited_node_ids": cites[:4],
            "is_superseded": is_superseded,
            "is_stale": is_stale,
        }

    llm_out = llm.call_structured(
        prompt=f"Answer company brain question: '{question}'. Ground your response ONLY in retrieved facts.",
        system_prompt="You are Ripple Company-Brain Q&A. Cite node IDs for all claims.",
        schema=BrainAnswerSchema,
        valid_node_ids=valid_ids,
        context_data=data,
        fallback_generator=fallback_gen,
    )

    # 3. Persistent Conversation History: Store Question & Answer in FalkorDB
    now_ts = time.time()
    qid = f"q_{uuid.uuid4().hex[:8]}"
    aid = f"ans_{uuid.uuid4().hex[:8]}"

    history_cypher = """
    MERGE (q:Question {id: $qid})
    SET q.text = $q_text,
        q.intent = $intent,
        q.ts = $ts,
        q.tenant_id = $tenant_id
    MERGE (ans:Answer {id: $aid})
    SET ans.text = $ans_text,
        ans.intent = $intent,
        ans.ts = $ts,
        ans.is_stale = $is_stale,
        ans.is_superseded = $is_superseded,
        ans.tenant_id = $tenant_id
    MERGE (q)-[:ANSWERED_BY]->(ans)
    """
    graph.query(history_cypher, {
        "qid": qid,
        "q_text": question,
        "intent": intent,
        "ts": now_ts,
        "tenant_id": tenant_id,
        "aid": aid,
        "ans_text": llm_out.summary_answer,
        "is_stale": is_stale,
        "is_superseded": is_superseded,
    })

    # Link Answer CITES to retrieved sources
    for src in sources[:5]:
        sid = src.get("id")
        if sid:
            graph.query(
                """
                MATCH (ans:Answer {id: $aid})
                MATCH (target)
                WHERE target.id = $sid OR target.name = $sid OR target.login = $sid
                MERGE (ans)-[:CITES]->(target)
                """,
                {"aid": aid, "sid": sid},
            )

    result = {
        "question_id": qid,
        "answer_id": aid,
        "question": question,
        "intent": intent,
        "answer": llm_out.summary_answer,
        "detailed_answer": llm_out.detailed_answer,
        "sources": sources,
        "is_superseded": is_superseded,
        "is_stale": is_stale,
        "raw_data": data,
    }
    return result, trace


def get_qa_history(graph: TenantGraph, tenant_id: str = "storefront", limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve persistent conversation history for a tenant."""
    cypher = """
    MATCH (q:Question)-[:ANSWERED_BY]->(ans:Answer)
    WHERE q.tenant_id = $tenant_id OR ans.tenant_id = $tenant_id
    OPTIONAL MATCH (ans)-[:CITES]->(src)
    RETURN q.id AS qid, q.text AS question, q.intent AS intent, q.ts AS q_ts,
           ans.id AS aid, ans.text AS answer, ans.is_stale AS is_stale,
           ans.is_superseded AS is_superseded,
           collect(DISTINCT {
               id: coalesce(src.id, src.name, src.login, toString(src.number)),
               type: labels(src)[0]
           }) AS cited_sources
    ORDER BY q.ts DESC
    LIMIT $limit
    """
    res = graph.query(cypher, {"tenant_id": tenant_id, "limit": limit})
    history = []
    if res and res.result_set:
        for r in res.result_set:
            qid, q_text, intent, q_ts, aid, a_text, is_stale, is_sup, cited = r
            history.append({
                "question_id": qid,
                "question": q_text,
                "intent": intent,
                "timestamp": q_ts,
                "answer_id": aid,
                "answer": a_text,
                "is_stale": bool(is_stale),
                "is_superseded": bool(is_sup),
                "cited_sources": [c for c in cited if c.get("id")],
            })
    return history

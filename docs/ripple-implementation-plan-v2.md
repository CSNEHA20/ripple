# Ripple: Full Implementation Plan (v2)

**Graph Hacks: Context for AI Agents** (WeMakeDevs x FalkorDB) · Oct 15-18, 2026 · Solo build

> **One-liner:** Ripple is an on-call agent crew that uses FalkorDB as its brain. It follows real service dependencies to find the blast radius, forms competing hypotheses and ranks them with supporting and contradicting evidence, remembers every incident *and whether the fix actually worked*, coordinates through a shared graph, answers "what if X had failed instead?", and shows the exact subgraph path, nodes, and Cypher behind every answer. Its learning is proven with a measured memory-on vs memory-off benchmark.

**What changed from v1:** nothing was removed. v2 adds six upgrades on top of the full v1 scope:

1. Graph-guided investigation (hypotheses with supporting and contradicting evidence)
2. Outcome-driven memory (failed fixes recorded, applicability check against the current system state)
3. Evidence and uncertainty engine (facts vs inferences, freshness, contradictions, inspectable queries)
4. Graph-native agent collaboration (tasks, evidence requests, conflict flags, safe-action gate)
5. Scientific proof of improvement (pre-registered benchmark, repeated and unseen scenarios, failure reporting)
6. Counterfactual engine (observed incident vs hypothetical failure, with time-travel and uncertainty)

---

## 0. Ground rules for a solo, 2.5-day build

1. **Vertical slice first.** By the end of Day 1: alert in → graph tools run → ranked hypotheses with evidence → one answer with a highlighted path.
2. **The graph must drive behavior.** Candidates, evidence, scores, and rankings are computed from Cypher results by code. The LLM selects tools, phrases hypotheses, and summarizes. It never invents evidence.
3. **Be honest about data.** Services, people, PRs, issues, and commits are real (public repo). Scenarios, deployments, metric snapshots, historical incidents, and architecture-change events are seeded and labelled as such in the UI and README.
4. **Demo reliability beats polish.** Build a deterministic replay mode (cached LLM outputs) so the demo never depends on live API latency.
5. **Pre-register the benchmark.** Ground-truth labels for every benchmark scenario are written and committed *before* any benchmark run.
6. **All scope stays in.** Nothing is cut up front. Section 16 defines an emergency fallback order that applies only if a daily gate is missed.

---

## 1. Requirements traceability

| Brief requirement | Where Ripple satisfies it | Modules |
|---|---|---|
| Follow connections across data | Blast radius, upstream tracing, path queries, temporal (as-of) traversal | M4, M9 |
| Remember across sessions | Episodic, semantic, procedural and outcome memory persisted in graph | M6 |
| Share state between agents | Blackboard: Task, Hypothesis, Observation, Conflict, Handoff nodes | M7 |
| Connect people, projects, decisions | Ownership, expertise, decision lineage, critical owners | M4, M8, M9 |
| Show the path behind an answer | Provenance trace, node/edge/Cypher inspector, "why" replay | M10, M12 |
| Track 1: multi-hop reasoning | Hypothesis generation by traversal, blast radius, counterfactual diff | M4, M5, M9 |
| Track 1: graph queries/algorithms as tools | Tool library (traversal, shortest path, PageRank) | M4 |
| Track 1: tool selection through MCP | MCP server over the tool library | M11 |
| Track 1: actions based on what the graph shows | Responder actions gated by applicability and evidence | M7 |
| Track 1: explainable results | Evidence trail, trace, inspector | M5, M10 |
| Track 2: episodic, semantic, procedural memory | Memory layer with all three plus outcome memory | M6 |
| Track 2: persistent conversation history | Incident and Q&A history stored per tenant | M6, M8 |
| Track 2: shared state and handoffs | Blackboard coordination | M7 |
| Track 2: high-concurrency reads and writes | Concurrency test and idempotent `MERGE` writes | M6, M13 |
| Track 2: separate memory per user or tenant | One graph per tenant plus isolation test | M1, M13 |
| Track 3: knowledge from docs, tickets, chats in one graph | Docs, PRs, issues, decisions linked to services and people | M2, M8 |
| Track 3: who owns what, who knows what | Ownership and recency-weighted expertise | M4, M8 |
| Track 3: tracing decisions to source | `Decision -DERIVED_FROM-> PR/Issue/Doc`, citations | M8 |
| Track 3: keeping knowledge current | `SUPERSEDES`, freshness checks, stale flags, temporal edges | M6, M8 |
| Track 3: answers with clear sources | Every answer cites node IDs and URLs | M8, M10 |

---

## 2. Architecture

```
                 ┌────────────────────────────────────────────┐
                 │  React UI (Vite)                           │
                 │  alert console · agent timeline · graph    │
                 │  hypothesis board · memory panel ·         │
                 │  counterfactual overlay · benchmark tab ·  │
                 │  ask-brain · inspector drawer              │
                 └──────────────────┬─────────────────────────┘
                                    │ REST + SSE (live agent events)
                 ┌──────────────────▼─────────────────────────┐
                 │  FastAPI backend · tenant middleware        │
                 └──┬───────┬────────┬────────┬────────┬──────┘
                    │       │        │        │        │
          ┌─────────▼──┐ ┌──▼─────┐ ┌▼───────┐ ┌▼──────┐ ┌▼────────────┐
          │Orchestrator│ │Hypothe-│ │Brain   │ │Counter│ │Scenario     │
          │+ 3 agents  │ │sis &   │ │Q&A     │ │factual│ │simulator +  │
          │+ blackboard│ │evidence│ │(Trk 3) │ │engine │ │ingestion    │
          └─────┬──────┘ └──┬─────┘ └┬───────┘ └┬──────┘ └┬────────────┘
                │ tool calls│        │          │         │
          ┌─────▼───────────▼────────▼──────────▼─────────▼──────┐
          │  Graph tool library + Memory layer                    │
          │  (every call emits a provenance trace)                │
          └───────────────────────────┬───────────────────────────┘
                                      │ Cypher
                 ┌────────────────────▼───────────────────┐
                 │  FalkorDB (Docker) · graph per tenant   │
                 │  tenant_storefront · tenant_payments    │
                 └─────────────────────────────────────────┘
```

**Stack**

| Layer | Choice | Why |
|---|---|---|
| Graph DB | FalkorDB via Docker | Required sponsor tech; multigraph for tenants |
| Backend | Python 3.11 + FastAPI | Official `falkordb` Python client, fast to build |
| LLM | Any tool-calling LLM (function calling, JSON-schema outputs) | Agents choose graph tools; outputs are validated |
| Embeddings | `sentence-transformers` all-MiniLM-L6-v2 (384-dim, local) | No API dependency, fast on CPU |
| Frontend | React + Vite + `react-force-graph-2d` + a small chart lib | Interactive graph with highlight and overlay support |
| Streaming | Server-Sent Events | Live agent timeline without websocket overhead |
| MCP | Python MCP SDK wrapper over tools | Delivers "tool selection through MCP" |

```bash
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
# 6379 = database, 3000 = FalkorDB Browser (debugging and screenshots)
```

---

## 3. Repository structure

```
ripple/
├── README.md
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, routes, SSE
│   │   ├── config.py                # weights, thresholds, half-lives
│   │   ├── tenancy.py               # TenantGraph (isolation boundary)
│   │   ├── schema.py                # indexes, labels, constraints
│   │   ├── ingest/
│   │   │   ├── services.py          # service dependency loader (with valid_from/valid_to)
│   │   │   ├── github.py            # people, PRs, issues, commits
│   │   │   ├── docs.py              # docs and decisions
│   │   │   └── embed.py
│   │   ├── scenarios/               # M3 simulator
│   │   │   ├── engine.py            # replays a scenario into the graph/environment
│   │   │   ├── catalog.py           # scenario definitions (seeded)
│   │   │   ├── metrics.py           # MetricSnapshot generation
│   │   │   └── outcomes.py          # how interventions change post-fix metrics
│   │   ├── tools/                   # M4 graph tool library
│   │   │   ├── blast_radius.py
│   │   │   ├── root_cause.py
│   │   │   ├── paths.py
│   │   │   ├── criticality.py
│   │   │   ├── people.py
│   │   │   ├── changes.py           # deployments, PRs, architecture changes
│   │   │   ├── incidents.py
│   │   │   └── registry.py          # JSON schemas for function calling and MCP
│   │   ├── hypotheses/              # M5
│   │   │   ├── generate.py
│   │   │   ├── evidence.py
│   │   │   ├── score.py
│   │   │   └── sufficiency.py
│   │   ├── memory/                  # M6
│   │   │   ├── episodic.py
│   │   │   ├── semantic.py
│   │   │   ├── procedural.py
│   │   │   ├── outcomes.py
│   │   │   ├── applicability.py
│   │   │   └── decay.py
│   │   ├── agents/                  # M7
│   │   │   ├── orchestrator.py
│   │   │   ├── triage.py
│   │   │   ├── investigator.py
│   │   │   ├── responder.py
│   │   │   ├── verifier.py
│   │   │   ├── blackboard.py
│   │   │   ├── conflicts.py
│   │   │   ├── actions.py           # safe-action classes and approval gate
│   │   │   └── llm.py               # LLM wrapper + replay cache + schema validation
│   │   ├── brain/                   # M8
│   │   │   ├── ask.py
│   │   │   └── freshness.py
│   │   ├── counterfactual/          # M9
│   │   │   ├── engine.py
│   │   │   └── uncertainty.py
│   │   ├── trace.py                 # M10 provenance trace
│   │   └── mcp_server.py            # M11 MCP wrapper
│   ├── eval/                        # M13
│   │   ├── benchmark.py
│   │   ├── labels.json              # pre-registered ground truth (commit before running)
│   │   ├── report.py
│   │   ├── isolation_test.py
│   │   └── concurrency_test.py
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── AlertConsole.tsx
│       │   ├── AgentTimeline.tsx
│       │   ├── GraphCanvas.tsx
│       │   ├── HypothesisBoard.tsx
│       │   ├── MemoryPanel.tsx
│       │   ├── CounterfactualPanel.tsx
│       │   ├── BenchmarkTab.tsx
│       │   ├── AskBrain.tsx
│       │   ├── Inspector.tsx
│       │   └── TenantSwitcher.tsx
│       └── api.ts
├── data/
│   ├── services.json
│   ├── scenarios.json
│   ├── runbooks.json
│   ├── docs/
│   └── replay_cache/
└── docs/
    ├── architecture.png
    ├── demo-script.md
    ├── track-mapping.md
    └── benchmark-report.md
```

---

## 4. Graph data model (M1)

### 4.1 Node labels

| Label | Key properties |
|---|---|
| `Service` | `name` (unique), `language`, `tier`, `description`, `deps_known` (bool), `embedding` |
| `Person` | `login` (unique), `name` |
| `Team` | `name` |
| `Commit` | `sha`, `message`, `ts` |
| `PullRequest` | `number`, `title`, `body`, `merged_at`, `url`, `embedding` |
| `Issue` | `number`, `title`, `body`, `state`, `url`, `embedding` |
| `Deployment` | `id`, `service`, `version`, `ts`, `source` (`real`/`seeded`) |
| `ArchitectureChange` | `id`, `summary`, `ts`, `closes_edges[]`, `opens_edges[]`, `source` |
| `MetricSnapshot` | `id`, `service`, `ts`, `latency_p95_ms`, `error_rate`, `status` (`normal`/`degraded`/`failing`), `source` |
| `Decision` | `id`, `summary`, `ts`, `status` (`active`/`superseded`), `embedding` |
| `Doc` | `id`, `title`, `text`, `last_verified_ts`, `url` |
| `Alert` | `id`, `text`, `ts`, `service_name` |
| `Incident` | `id`, `title`, `signature_embedding`, `severity`, `opened_ts`, `resolved_ts`, `steps_taken`, `tool_calls`, `scenario_id` |
| `Hypothesis` | `id`, `incident_id`, `statement`, `kind` (`inferred`), `formed_ts`, `status` (`open`/`confirmed`/`rejected`/`insufficient`), `evidence_score`, `margin` |
| `Evidence` | `id`, `kind` (`observed`/`inferred`), `type` (`dependency_path`, `recent_deploy`, `metric`, `past_incident`, `architecture_change`, `decision`, `doc`), `summary`, `source_ref`, `observed_ts`, `freshness`, `weight` |
| `Runbook` | `id`, `title`, `steps`, `success_count`, `fail_count`, `assumes[]` (list of `A->B` dependency pairs it relies on) |
| `Intervention` | `id`, `incident_id`, `description`, `runbook_id`, `predicted_outcome`, `action_class`, `status` |
| `Outcome` | `id`, `intervention_id`, `observed` (`resolved`/`partial`/`failed`), `metrics_after`, `ts` |
| `Action` | `id`, `kind`, `class` (`read_only`/`reversible`/`needs_approval`), `status` (`proposed`/`approved`/`executed`/`rejected`), `payload` |
| `AgentRun` | `id`, `agent`, `started_ts` |
| `Task` | `id`, `kind` (`triage`/`investigate`/`evidence_request`/`respond`/`verify`), `status`, `payload` |
| `Observation` | `id`, `text`, `kind` (`observed`/`inferred`), `confidence_basis`, `ts` |
| `Conflict` | `id`, `reason`, `status` (`open`/`resolved`), `opened_ts` |

### 4.2 Relationships

```
(Service)-[:DEPENDS_ON {protocol, criticality, valid_from, valid_to, verified, source}]->(Service)
(Person)-[:OWNS]->(Service)
(Person)-[:AUTHORED]->(PullRequest)-[:TOUCHES]->(Service)
(Person)-[:COMMITTED {n, last_ts}]->(Service)
(Issue)-[:ABOUT]->(Service)
(PullRequest)-[:SHIPPED_IN]->(Deployment)-[:DEPLOYED_TO]->(Service)
(ArchitectureChange)-[:CHANGED]->(Service)
(Service)-[:HAD_METRIC]->(MetricSnapshot)
(Decision)-[:DERIVED_FROM]->(PullRequest|Issue|Doc)
(Decision)-[:SUPERSEDES]->(Decision)
(Decision)-[:CONCERNS]->(Service)
(Doc)-[:DESCRIBES]->(Service)
(Alert)-[:FIRED_ON]->(Service)
(Incident)-[:TRIGGERED_BY]->(Alert)
(Incident)-[:AFFECTED {role}]->(Service)                     // role: root | impacted
(Incident)-[:HANDLED_BY]->(Person)
(Incident)-[:SIMILAR_TO {score}]->(Incident)
(Incident)-[:HAS_HYPOTHESIS]->(Hypothesis)
(Hypothesis)-[:ABOUT]->(Service)
(Hypothesis)-[:SUPPORTED_BY {weight}]->(Evidence)
(Hypothesis)-[:CONTRADICTED_BY {weight}]->(Evidence)
(Evidence)-[:SOURCED_FROM]->(Deployment|PullRequest|Issue|MetricSnapshot|Incident|ArchitectureChange|Decision|Doc)
(Incident)-[:ROOT_CAUSE {confirmed_ts}]->(Hypothesis)       // only after verified outcome
(Hypothesis)-[:ADDRESSED_BY]->(Intervention)
(Intervention)-[:USES]->(Runbook)
(Intervention)-[:VALIDATED_BY {result}]->(Outcome)          // result: validates | rejects | partial
(Runbook)-[:ASSUMES]->(Service)
(Action)-[:IMPLEMENTS]->(Intervention)
(Action)-[:PROPOSED_BY]->(AgentRun)
(AgentRun)-[:WORKED_ON]->(Incident)
(AgentRun)-[:CREATED]->(Task|Observation|Hypothesis|Evidence|Conflict)
(Observation)-[:ABOUT]->(Service|Incident)
(Task)-[:HANDOFF_TO]->(AgentRun)
(Task)-[:BLOCKED_BY]->(Task)
(Task)-[:REQUESTS_EVIDENCE_FOR]->(Hypothesis)
(Conflict)-[:INVOLVES]->(Hypothesis|Observation|Runbook|Evidence)
(AgentRun)-[:FLAGGED]->(Conflict)
(Conflict)-[:RESOLVED_BY]->(Task)
```

### 4.3 Indexes

```cypher
CREATE INDEX FOR (s:Service) ON (s.name)
CREATE INDEX FOR (p:Person) ON (p.login)
CREATE INDEX FOR (i:Incident) ON (i.id)
CREATE INDEX FOR (h:Hypothesis) ON (h.incident_id)
CREATE INDEX FOR (m:MetricSnapshot) ON (m.service)

CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature_embedding)
  OPTIONS {dimension: 384, similarityFunction: 'cosine'}
CREATE VECTOR INDEX FOR (d:Decision) ON (d.embedding)
  OPTIONS {dimension: 384, similarityFunction: 'cosine'}
```

> Check the current FalkorDB docs for exact index, vector, and algorithm-procedure syntax for your Docker image version in the first hour of Day 1. Syntax has evolved across releases. Fallback: store embeddings as properties and compute cosine similarity in Python.

### 4.4 Temporal edges

`DEPENDS_ON` carries `valid_from` and `valid_to` (null means currently valid). The current graph is `WHERE d.valid_to IS NULL`. The graph "as of time T" is `WHERE d.valid_from <= T AND (d.valid_to IS NULL OR d.valid_to > T)`. An `ArchitectureChange` node closes and opens edges, so history is never overwritten. Used by the applicability check (M6) and the counterfactual engine (M9).

### 4.5 Tenancy (isolation boundary)

Each tenant gets its own graph: `tenant_<id>`. All DB access goes through `TenantGraph`, constructed with a tenant ID, able to select only `tenant_<id>`. No tool, agent, or route receives a raw client.

```python
class TenantGraph:
    def __init__(self, db: FalkorDB, tenant_id: str):
        self._g = db.select_graph(f"tenant_{tenant_id}")
        self.tenant_id = tenant_id

    def query(self, cypher: str, params: dict | None = None):
        return self._g.query(cypher, params or {})
```

---

## 5. Module breakdown

### M0: Project setup (1 hr)
- Repo, `docker-compose.yml` (FalkorDB + backend + frontend), env config, lint basics.
- Smoke test: connect, create a node, query it, open FalkorDB Browser on port 3000.
- **Done when:** `docker compose up` brings up all three services and `/health` returns OK.

### M1: Graph layer, schema, temporal edges, tenancy (2 hrs)
- `tenancy.py` (TenantGraph), `schema.py` (indexes per tenant), `ensure_tenant(tenant_id)` idempotent.
- Temporal helpers: `current_edges()` and `edges_as_of(ts)` Cypher fragments reused by tools.
- **Done when:** two tenants exist, a write to one is invisible from the other, and an `as_of` query returns the right edge set around an `ArchitectureChange`.

### M2: Data ingestion, real data (3.5 hrs)

| Data | Source | Notes |
|---|---|---|
| Services and dependencies | Hand-encode from the repo's architecture docs and Kubernetes manifests (env vars like `*_SERVICE_ADDR` show who calls whom) | ~11 services; mark each edge `verified=true` only if confirmed in manifests |
| People, commits, PRs, issues | GitHub REST API on the public repo | Cache raw JSON to disk to avoid rate limits |
| Ownership | Map file paths (`src/<service>/`) in commits and PRs to services | Weight by recency and count |
| Decisions | LLM-assisted extraction from PR descriptions and issue threads, then human review | Keep ~15-25 good ones; include at least 2 `SUPERSEDES` pairs |
| Docs | Short service descriptions written from repo READMEs | Set `last_verified_ts`; deliberately leave 2-3 docs stale vs later PRs |
| Deployments | Real PR merge times mapped to deployment nodes | Flag `source='seeded'` because real deploy logs do not exist |

**Tasks**
1. `services.py`: load services and `DEPENDS_ON` edges with `valid_from`, `valid_to`, `verified`.
2. `github.py`: fetch and cache contributors, commits, PRs, issues; create `Person`, `PullRequest`, `Issue`, and aggregated `COMMITTED` edges.
3. `docs.py`: docs and decisions with source links.
4. `embed.py`: embed PR/issue/decision text and incident signatures locally.
5. Second tenant: a small separate org (different services, people, history) used for isolation demos.

**Done when:** Cypher in FalkorDB Browser shows ~11 services, 30+ people, 100+ PRs/issues, decisions with source links, and `MATCH (p:Person)-[:COMMITTED]->(s:Service)` gives sensible owners.

### M3: Scenario simulator (seeded) (2.5 hrs)

The simulator produces the environment Ripple investigates. Everything it generates is flagged `source='seeded'`.

**Scenario definition (`scenarios.json`)**
```json
{
  "id": "sc_payment_latency_01",
  "alert": {"service": "paymentservice", "text": "p95 latency > 2s"},
  "ground_truth": {"root_cause_service": "...", "root_cause_type": "bad_deploy", "correct_runbook": "rb_rollback"},
  "metrics": [{"service": "...", "status": "failing|degraded|normal", "latency_p95_ms": 0, "error_rate": 0.0}],
  "deployments": [{"service": "...", "hours_before_alert": 2, "version": "..."}],
  "architecture_changes": [],
  "interventions": {"rb_rollback": "resolved", "rb_restart": "failed", "rb_scale_up": "partial"}
}
```

**Scenario families (needed for the benchmark)**

| Family | Count | Purpose |
|---|---|---|
| Historical (seeded into memory) | 6-8 | Past incidents with root cause, runbook, and outcome |
| Repeated | 3 | Same root cause as history; memory should help |
| Variant | 3 | Same runbook family, different service; tests generalization |
| Novel | 3 | No matching history; memory should neither help nor mislead |
| Stale-fix trap | 2 | A past fix whose assumed dependency was removed by an `ArchitectureChange`; memory must *not* recommend it |
| Misleading-memory | 1-2 | Symptoms resemble a past incident but root cause differs; memory can hurt |

**Simulator functions**
- `load_scenario(id)`: writes alert, `MetricSnapshot` nodes, `Deployment` nodes, `ArchitectureChange` nodes into the tenant graph with timestamps relative to the alert time.
- `apply_intervention(scenario_id, runbook_id)`: returns the scripted observed result (`resolved`/`partial`/`failed`) and post-fix metrics. This is how outcomes are verified without a real cluster. Say so in the README.
- Contradicting evidence is built in: healthy upstream metrics, old deployments, and non-applicable past fixes exist so contradiction is real, not decorative.

**Done when:** loading a scenario creates the expected nodes and `apply_intervention` returns consistent outcomes for every scenario.

### M4: Graph tool library (Track 1) (3 hrs)

Each tool is a plain Python function with a JSON schema, returning **data plus a trace** (M10). Agents reach the database only through these tools.

| Tool | Purpose | Graph technique |
|---|---|---|
| `blast_radius(service, max_depth, as_of?)` | Downstream services affected if this one fails | Reverse variable-length traversal on `DEPENDS_ON` (temporal) |
| `upstream_suspects(service, max_depth, as_of?)` | Dependencies that could be causing this service's alert | Forward traversal |
| `path_between(a, b, as_of?)` | Why A depends on B | `shortestPath` |
| `criticality_ranking()` | Which services matter most | PageRank over `DEPENDS_ON` |
| `who_knows(service, k)` | Best people to involve | Weighted `COMMITTED` + `AUTHORED` recency score |
| `recent_changes(service, hours)` | Deployments, PRs, architecture changes near the alert | Traversal + time filter |
| `service_health(services, ts)` | Metric snapshots, used for supporting/contradicting evidence | `HAD_METRIC` lookup |
| `similar_incidents(alert_text, services, k)` | Past incidents like this one | Vector search re-ranked by service overlap |
| `rank_runbooks(incident_ids)` | Best known fix | Runbook success rate via `USES` and `VALIDATED_BY` |
| `check_applicability(runbook_id)` | Whether a past fix still fits the current graph | `ASSUMES` vs current `DEPENDS_ON` (M6) |
| `counterfactual_blast(observed_incident_id, hypothetical_service)` | What-if diff | M9 |

Example Cypher (blast radius, current graph):

```cypher
MATCH p = (impacted:Service)-[:DEPENDS_ON*1..4]->(failed:Service {name: $service})
WHERE all(r IN relationships(p) WHERE r.valid_to IS NULL)
RETURN impacted.name AS service, min(length(p)) AS hops
ORDER BY hops
```

Example Cypher (who knows this system):

```cypher
MATCH (p:Person)-[c:COMMITTED]->(s:Service {name: $service})
RETURN p.login AS person, c.n AS commits, c.last_ts AS last_active
ORDER BY c.n DESC LIMIT $k
```

Recency-weighted `who_knows` score: `score = commits * 0.5^(days_since_last / 90)`.

Use FalkorDB's built-in algorithm procedures (e.g. PageRank) where available; confirm names in the docs. Fall back to Cypher plus Python if one is missing.

**Done when:** each tool has a unit test against the seeded graph and returns a trace object.

### M5: Hypothesis and evidence engine (Track 1 core) (3.5 hrs)

This is the "graph-guided investigation" upgrade. The LLM does not decide the root cause on a plausible story. Candidates and evidence come from graph tools; ranking is computed by code.

**Step 1: Generate candidates (`generate.py`)**
Candidate hypotheses come from graph facts, never free imagination:
- Each upstream dependency of the alerting service (via `upstream_suspects`).
- Each recent deployment on the service or its dependencies (via `recent_changes`).
- Each `ArchitectureChange` in the window.
- Root causes of similar past incidents (via memory recall).

Each candidate becomes a `Hypothesis` node with `kind='inferred'`, `formed_ts`, and an `ABOUT` edge to its service. The LLM may phrase the `statement` from structured fields but cannot add candidates outside the set.

**Step 2: Gather evidence (`evidence.py`)**
For each hypothesis, run tools to create `Evidence` nodes linked via `SOURCED_FROM`, then attach with `SUPPORTED_BY` or `CONTRADICTED_BY`:

| Evidence type | Supports when | Contradicts when |
|---|---|---|
| `dependency_path` | A path exists from the hypothesized service to the alerting one | No path exists in the current graph |
| `recent_deploy` | Deployment shortly before the alert on that service | Deployment is old relative to a defined window, or on an unrelated branch |
| `metric` | Hypothesized service is `degraded`/`failing` | Hypothesized service is `normal` |
| `past_incident` | A similar past incident had this root cause and the fix validated | The fix failed before, or the past case differs on key conditions |
| `architecture_change` | A change near the alert touches this service | The change predates the symptoms by more than the window |
| `decision`/`doc` | A relevant active decision explains the behavior | The decision is superseded, or the doc is stale |

**Observed vs inferred (`kind`)**
- `observed`: directly read from data (a metric snapshot, a deployment timestamp, a path that exists).
- `inferred`: derived by reasoning (a hypothesis, a similarity judgement).
- The UI badges every item. Hypotheses are always `inferred`.

**Step 3: Score (`score.py`)**
```
freshness(e)    = 0.5 ^ (age_hours / half_life_for_type)
support_total   = Σ weight_by_type × freshness(e)   over SUPPORTED_BY
contra_total    = Σ weight_by_type × freshness(e)   over CONTRADICTED_BY
evidence_score  = support_total − contra_total
margin          = evidence_score(top) − evidence_score(second)
```
Weights and half-lives live in `config.py`, are documented in the README, and are the same for every scenario.

**Step 4: Sufficiency check (`sufficiency.py`)**
A diagnosis is `insufficient_evidence` if any of: the top hypothesis has fewer than 2 supporting evidence items, margin is below a threshold, or a strong contradiction is unresolved. In that case the agent:
1. States plainly that the evidence is insufficient.
2. Creates an `evidence_request` Task listing which extra evidence would discriminate the top hypotheses (e.g. "metrics for service X", "deploy history for Y").
3. Hands that task back to the investigator (M7).

**Confidence policy (calibration-gated)**
- Always shown: `evidence_score`, `margin`, and the supporting/contradicting lists.
- A probability-style confidence is shown **only if** the benchmark calibration check passes (M13): scores must rank-correlate with correctness across enough scenarios. Until then the UI labels it "evidence score," never "confidence %," and shows the basis ("2 supporting, 1 contradicting, freshest evidence 2h old").
- Runbook numbers are labelled "historical success rate (observed outcomes)," not probabilities.

**Done when:** for each seeded scenario the engine produces ranked hypotheses with both supporting and contradicting evidence, and returns `insufficient_evidence` for a scenario deliberately built with sparse data.

### M6: Memory layer (Track 2) (4.5 hrs)

Memory is stored in the graph so any agent can read it. It records not just what happened, but whether the fix worked and under what conditions.

**Episodic (what happened)**
- On incident close, write the `Incident` with `steps_taken`, `tool_calls`, `AFFECTED` edges, `HANDLED_BY`, the winning `Hypothesis` via `ROOT_CAUSE` (only after verified outcome), and linked `Intervention`/`Outcome`.
- Create `SIMILAR_TO` edges to the top-k nearest past incidents.

**Semantic (what is true)**
- Service facts and `Observation` nodes with `kind` and `confidence_basis`.
- When new evidence contradicts an old fact: create the new `Observation`, link `SUPERSEDES`, mark the old one inactive. Never delete.

**Procedural (what works)**
- `Runbook` nodes carry `success_count` and `fail_count`, updated **only from observed outcomes**: `resolved` adds 1 success; `failed` adds 1 failure; `partial` adds 0.5 to each.
- Rate: `historical_success_rate = (success + 1) / (success + fail + 2)` (Laplace smoothing).

**Outcome-driven memory (new)**
- Every proposed fix becomes an `Intervention` with a `predicted_outcome` stored **separately** from the observed `Outcome`.
- `Intervention -VALIDATED_BY {result}-> Outcome` records `validates`, `rejects`, or `partial`.
- Failed fixes are first-class memory. Recall surfaces them: "restart was tried in INC-3 and failed."
- Prediction error (predicted vs observed) is stored and feeds the benchmark.

**Applicability check (`applicability.py`) (new, the "killer moment")**
- Each runbook declares `assumes[]` (e.g. `cartservice->redis-cart`) and `ASSUMES` edges to services.
- Before recommending any remembered fix, `check_applicability(runbook_id)` verifies every assumed dependency pair exists in the **current** graph (`valid_to IS NULL`).
- If an assumption no longer holds (closed by an `ArchitectureChange`), the fix is **not recommended**. The UI shows a "Why not recommended" card naming the changed edge, the change that closed it, and its source.
- Also compare the past incident's conditions (affected set, tier) with the current ones; report mismatches as warnings.

**Decay**
- Effective weight for old observations and evidence: `weight * 0.5^(age_days / half_life)`.

**Recall API**
```python
recall(alert_text, services) -> {
  "similar_incidents": [...],        # with scores and outcomes (including failures)
  "recommended_runbook": {...},      # historical success rate + applicability result
  "rejected_runbooks": [...],        # with reasons (failed before, not applicable)
  "known_facts": [...],              # active observations
  "trace": Trace
}
```

**Concurrency**
- Idempotent writes via `MERGE` on stable IDs; optimistic checks so two agents writing observations at once do not duplicate nodes. A load-test script (M13) fires parallel writes.

**Done when:** closing incident #1 changes `recall()` for a similar incident #2; a failed fix shows up as rejected; a stale-fix scenario is blocked by the applicability check with a visible reason; a contradicting observation correctly supersedes an old one.

### M7: Agents and graph-native collaboration (4.5 hrs)

**Roles**

| Agent | Responsibility | Main tools |
|---|---|---|
| **Triage** | Parse alert, locate service, size blast radius, rank severity, recall past incidents, **create investigation Tasks in the graph** | `blast_radius`, `criticality_ranking`, `similar_incidents`, `recall` |
| **Investigator** | Generate hypotheses, **attach evidence and competing hypotheses**, rank them, answer evidence requests | M5 engine, `upstream_suspects`, `recent_changes`, `service_health`, `path_between`, brain Q&A |
| **Responder** | **Read shared state**, choose a runbook (after applicability check), **propose a safe action**, draft the incident update, identify people to page | `rank_runbooks`, `check_applicability`, `who_knows`, memory writes |
| **Verifier** | Check post-intervention metrics, record the observed `Outcome`, close the loop | `service_health`, simulator `apply_intervention`, memory writes |

**Blackboard coordination (the graph is the shared state)**
- Orchestrator creates a `Task` per phase and an `AgentRun` per agent.
- Triage creates `investigate` Tasks; the investigator attaches `Hypothesis` + `Evidence` nodes and links them to the incident; the responder reads that subgraph, not a text summary.
- Handoffs are edges: `(Task)-[:HANDOFF_TO]->(AgentRun)`. `BLOCKED_BY` edges let the responder wait on the investigator.
- Agents write `Observation` nodes (with `kind`) linked to incident and service.

**Conflicts and evidence requests (new)**
- An agent can raise a `Conflict` when: the top two hypotheses are within the margin threshold; the responder finds the recommended runbook fails its applicability check; evidence contradicts a prior observation.
- `Conflict` links to the involved nodes via `INVOLVES` and is flagged by the agent via `FLAGGED`.
- The responder (or investigator) can create an `evidence_request` Task (`REQUESTS_EVIDENCE_FOR` a hypothesis). The investigator picks it up, attaches new evidence, and the conflict closes via `RESOLVED_BY` that task.
- All of this is visible as nodes and edges and as events on the agent timeline.

**Safe actions (`actions.py`)**

| Class | Examples | Behavior |
|---|---|---|
| `read_only` | query metrics, fetch history | auto-execute, logged |
| `reversible` | draft status update, create page request, scale suggestion | auto-execute in the simulator, logged, undo noted |
| `needs_approval` | rollback, restart | proposed as an `Action` with status `proposed`; UI shows an Approve button; execution only after approval |

Every `Action` links to its `Intervention` and `AgentRun`.

**Loop design**
1. Orchestrator opens the incident and Task graph.
2. Each agent runs a bounded tool-calling loop (max ~6 tool calls per agent step).
3. Outputs are JSON-schema validated. Any claim must cite `Evidence`/`Observation` IDs. Uncited claims are rejected and re-prompted once.
4. Investigator output may be `insufficient_evidence`, which triggers the evidence-request path.
5. Responder proposes an action; approval gate applies.
6. Verifier records the observed outcome; memory updates (M6).

**LLM wrapper (`llm.py`)**
- `mode = live | replay`. In replay, responses are keyed by a hash of the prompt and read from `data/replay_cache/`. Record the cache during Day 2 rehearsals.
- Schema validation and one-retry policy live here.

**Done when:** `POST /incidents` runs all four agents end to end; the full handoff chain, hypotheses with evidence, any conflicts, and the approval step are visible as nodes and edges in FalkorDB Browser.

### M8: Company-brain Q&A (Track 3) (3 hrs)

Natural-language questions answered from the graph with sources.

Target question types:
- "Who owns the payment service and who actually knows it?"
- "Why did we choose X?" (decision lineage)
- "What breaks if currency service goes down?"
- "Which docs describing checkout might be out of date?"
- "Has fix F ever failed, and when?" (outcome memory)

**Pipeline**
1. Classify intent (ownership, lineage, impact, freshness, outcome-history, free-form).
2. Known intents map to parameterized Cypher templates (safe, fast, reliable).
3. Free-form falls back to vector search over Decisions/PRs/Issues plus 1-2 hop expansion.
4. The LLM composes the answer **only from retrieved nodes**; each claim references node IDs.
5. Return `answer`, `sources[]` (node IDs, URLs), `trace`.

**Guardrail:** if LLM-generated Cypher is ever used, restrict to read-only (`MATCH`/`RETURN`), reject writes, cap results and depth.

**Freshness (`freshness.py`)**
```cypher
MATCH (d:Doc)-[:DESCRIBES]->(s:Service)<-[:TOUCHES]-(pr:PullRequest)
WHERE pr.merged_at > d.last_verified_ts
RETURN d.title, s.name, count(pr) AS changes_since
ORDER BY changes_since DESC
```
Flag stale answers in the UI ("based on a doc not verified since 3 merged changes"). Superseded decisions are surfaced as superseded, never silently used.

**Conversation history:** each Q&A turn is stored per tenant (`Question` and `Answer` nodes linked to cited sources) to satisfy persistent conversation history.

**Done when:** each question type returns a correct, cited answer, and a superseded decision is shown as superseded.

### M9: Counterfactual engine (new) (2 hrs)

A what-if reliability simulator built on the same graph.

**Question:** "What would have happened if the database service failed instead of the payment service?"

**Inputs:** `observed_incident_id`, `hypothetical_service`, optional `as_of` (`incident_time` | `now`).

**Algorithm (`engine.py`)**
1. **Observed set:** services in the incident's `AFFECTED` edges.
2. **Hypothetical set:** `blast_radius(hypothetical_service)` on the graph as of the chosen time.
3. **Diff:** `only_observed`, `only_hypothetical`, `both`.
4. **Paths:** `path_between` for every affected service to the failing one.
5. **Critical owners:** `OWNS` + `who_knows` for the top services ranked by PageRank within the affected set.
6. **Uncertainty (`uncertainty.py`):** list `DEPENDS_ON` edges with `verified=false`, and services with `deps_known=false`, that touch the affected region. State that the hypothetical set is a **lower bound** when unverified edges exist, and report how many.
7. **Time travel:** using `as_of=incident_time` vs `now` shows how architecture changes would alter the blast radius.

**Output:** a structured diff plus a trace; the UI overlays three colors (observed only, hypothetical only, both) and lists paths, owners, and uncertainty.

**Done when:** the same what-if produces different, explainable results for `incident_time` vs `now` in at least one scenario, and uncertainty notes appear when unverified edges are involved.

### M10: Provenance and explainability (2.5 hrs)

The central differentiator. Every tool call appends a `TraceStep`:

```python
@dataclass
class TraceStep:
    tool: str
    cypher: str
    params: dict
    node_ids: list[str]
    edge_ids: list[str]
    summary: str
```

- `trace.py` merges steps into `{nodes, edges, steps}` returned with every API response.
- The final answer lists which trace steps and evidence IDs back each claim.
- The UI highlights these nodes and edges and dims everything else.
- **Inspector drawer:** click any answer, hypothesis, or evidence item to see the exact nodes, edges, Cypher, parameters, and returned rows behind it.
- **"Why" replay:** steps through the trace in order while the highlight moves across the graph.
- Each evidence item shows source, timestamp, freshness, and `observed`/`inferred` badge.

**Done when:** for any incident, hypothesis, or question, the response includes a trace whose nodes/edges are exactly the ones queried, and the inspector shows the real Cypher that ran.

### M11: Backend API and MCP (3 hrs)

| Method | Route | Purpose |
|---|---|---|
| POST | `/tenants/{id}/bootstrap` | Create graph, indexes, ingest and seed |
| POST | `/scenarios/{id}/load` | Load a simulated scenario into the tenant |
| POST | `/incidents` | Submit an alert, run the crew |
| GET | `/incidents/{id}/stream` | SSE stream of agent events |
| GET | `/incidents/{id}` | Final state, hypotheses, evidence, trace |
| POST | `/incidents/{id}/actions/{aid}/approve` | Approve a `needs_approval` action |
| POST | `/incidents/{id}/close` | Verify outcome, write memory |
| POST | `/counterfactual` | What-if diff |
| POST | `/ask` | Company-brain Q&A |
| GET | `/graph/subgraph` | Nodes/edges for UI (by trace or by service, with `as_of`) |
| GET | `/memory/stats` | Counts, runbook rates, learning-curve data |
| POST | `/benchmark/run` | Run memory on/off benchmark |
| GET | `/benchmark/report` | Latest results |
| GET | `/inspect/{trace_step_id}` | Cypher, params, rows for the inspector |
| GET | `/health` | Liveness |

- Tenant comes from the `X-Tenant` header via middleware and builds the `TenantGraph`.
- **MCP server (`mcp_server.py`):** expose the M4 tools plus `recall`, `rank_hypotheses`, `counterfactual_blast`, and `ask` as MCP tools so any MCP-capable agent can use Ripple's graph. Demo it with a second client calling a tool.

### M12: Frontend (6 hrs)

Single-page dashboard, dark theme.

1. **Alert console:** pick a scenario or paste an alert, tenant switcher, "Run crew" button, replay/live toggle.
2. **Agent timeline:** live SSE events (agent started, tool called, evidence attached, conflict flagged, evidence requested, handoff, approval needed, outcome verified).
3. **Graph canvas:** `react-force-graph-2d`; nodes colored by label; trace highlighting; counterfactual overlay (observed / hypothetical / both); "as of incident time / now" toggle; click a node for properties and source link; "why" replay.
4. **Hypothesis board:** ranked hypothesis cards with supporting and contradicting evidence lists, `observed`/`inferred` badges, source, timestamp, freshness, evidence score and margin, and a clear "insufficient evidence" state with the pending evidence request.
5. **Memory panel:** similar past incidents (including failed fixes), recommended runbook with historical success rate and applicability result, and the **"Why not recommended"** card for stale or failed fixes.
6. **Counterfactual panel:** pick a service, run what-if, see diff, paths, critical owners, uncertainty notes.
7. **Benchmark tab:** memory on vs off charts (correctness, tool calls, time to recommendation), per-scenario table including cases where memory hurt, calibration status.
8. **Ask-the-brain drawer:** citations click through to graph nodes; stale and superseded badges.
9. **Inspector drawer:** nodes, edges, Cypher, rows behind any answer.
10. **Approval gate:** Approve/Reject buttons for `needs_approval` actions.

Build order: graph canvas with static data → trace highlighting → timeline → hypothesis board → memory panel → inspector → ask drawer → counterfactual overlay → benchmark tab → polish.

### M13: Evaluation, proof, and testing (3.5 hrs)

**Pre-registration**
- `eval/labels.json` holds ground truth per scenario (root cause service/type, correct runbook, whether memory should help). **Commit it before the first benchmark run** and say so in the report.

**Benchmark (`benchmark.py`)**
- Run the same scenario set in two modes: memory **ON** and memory **OFF**. Order scenarios identically; for ON, memory accumulates only from the historical seeds plus earlier benchmark runs that are part of the stated protocol.
- Scenario mix: repeated (3), variant (3), novel (3), stale-fix trap (2), misleading-memory (1-2).
- Run each scenario multiple times in live mode (e.g. 3) to capture LLM variance; report mean and range.

**Metrics**

| Metric | Definition |
|---|---|
| Diagnosis correctness | Top hypothesis matches ground-truth root cause |
| Recommendation correctness | Recommended runbook matches the labelled correct one (or correctly abstains) |
| Tool calls | Count per incident |
| Time to recommendation | Wall-clock in live mode; step count in replay mode |
| Unsafe recommendation rate | A stale or previously failed fix recommended |
| Prediction error | Predicted vs observed outcome of interventions |

**Reporting rules**
- Report every scenario, including **cases where memory made performance worse** (the misleading-memory family) and any errors.
- State the sample size; do not claim statistical significance with a small set. Call it a small, pre-registered benchmark.
- `report.py` generates `docs/benchmark-report.md` and the data the Benchmark tab renders.

**Calibration check**
- Bin `evidence_score` and compare against correctness. Pass only if scores rank-correlate with correctness across enough scenarios. If it passes, the UI may show a probability-style confidence labelled with its basis; if not, it stays "evidence score."

**Other tests**
- **Isolation test:** tenant B cannot read tenant A's incidents, runbooks, hypotheses, or memory, even by guessing IDs.
- **Concurrency test:** parallel agent writes (e.g. 50 observations from 5 workers) with no duplicates and no lost writes; also parallel reads during writes.
- **Unit and integration tests:** each tool; hypothesis generation, scoring, and sufficiency rules; applicability check blocking a stale fix; recall before/after closing; supersede logic; counterfactual diff with `as_of`; read-only Cypher guard; safe-action gate (no `needs_approval` action executes unapproved).

**Demo hardening**
- Record the replay cache, rehearse the demo 3 times offline, keep a backup screen recording.

### M14: Submission package (2 hrs)

- README: problem, architecture diagram, track mapping table, setup in 3 commands, data honesty note (real vs seeded), benchmark results and protocol.
- 3-4 minute demo video (script in Section 8).
- Submission form text (Section 13).
- Public GitHub repo, clean commit history, license.

---

## 6. Build timeline

Submissions open Oct 17 (~1 AM IST); the event closes Oct 18, 11:59 PM IST. Treat Oct 18 afternoon as the real deadline.

**Honest effort estimate:** the modules above add up to roughly **40+ hours of work** for one person. Estimates assume heavy AI-assisted coding. The schedule below is dense on purpose; the daily gates tell you early if you are behind.

### Today, Oct 16 (Day 1): foundation and vertical slice
| Block | Work |
|---|---|
| 1 hr | M0 setup |
| 2 hrs | M1 tenancy, schema, temporal edges |
| 3.5 hrs | M2 real-data ingestion |
| 2.5 hrs | M3 scenario simulator and first scenarios |
| 3 hrs | M4 tools (first six: `blast_radius`, `upstream_suspects`, `recent_changes`, `service_health`, `who_knows`, `similar_incidents`) |
| 1 hr | M10 trace skeleton wired into tools |
| **Gate 1** | One scenario alert returns blast radius, suspects, owners, and a trace in JSON |

### Oct 17 (Day 2): intelligence, memory, coordination
| Block | Work |
|---|---|
| 3.5 hrs | M5 hypothesis and evidence engine |
| 4.5 hrs | M6 memory (episodic, procedural, outcome, applicability, recall) |
| 4.5 hrs | M7 agents, blackboard, conflicts, safe actions, replay-mode LLM wrapper |
| 2 hrs | M8 brain Q&A (templates first, free-form second) |
| 1.5 hrs | M11 API and SSE |
| **Gate 2** | Full crew run via API with ranked hypotheses; closing incident #1 changes incident #2; a stale fix is blocked by the applicability check |

### Oct 18 (Day 3): proof, UI, ship
| Block | Work |
|---|---|
| 2 hrs | M9 counterfactual engine |
| 6 hrs | M12 frontend (build order in M12; start with graph canvas early in the day) |
| 3.5 hrs | M13 benchmark, calibration, isolation and concurrency tests |
| 1.5 hrs | M11 remainder: MCP server and benchmark endpoints |
| 2 hrs | M14 README, diagram, video, submission text |
| Buffer | 2+ hrs before the deadline. **Submit by early evening.** |

**Gate 3 (Oct 18, ~2 PM):** UI shows hypothesis board, memory panel with "why not recommended," trace highlighting, and benchmark results. If Gate 3 is missed, apply Section 16.

---

## 7. Demo script (about 3.5 minutes)

**Act 1: The failure (45s)**
A payment service starts experiencing high latency. Ripple's triage agent computes the blast radius and the investigator surfaces three candidate causes with evidence for each. Point to supporting and contradicting evidence on the hypothesis board and the "observed vs inferred" badges.

**Act 2: The investigation (60s)**
Ripple finds the recent deployment, checks the database dependency, and ranks the strongest-supported hypothesis. Click "Why?" and the highlight walks the exact evidence path; open the inspector to show the real Cypher. Show an agent raising a conflict and an evidence request that gets resolved. Show the responder's rollback proposal waiting for approval.

**Act 3: The memory (45s)**
Close the incident (the verifier records the observed outcome). Trigger a similar alert: Ripple recalls the previous outcome, verifies the conditions still match, and prioritizes accordingly. Then trigger the stale-fix trap: a previously successful fix is **not** recommended because the dependency it assumed was removed, and the "Why not recommended" card names the architecture change.

**Act 4: The proof (30s)**
Show the Benchmark tab: memory on vs off for correctness, tool calls, and time to recommendation, including the scenario where memory did worse. State the sample size and that labels were committed before the run. Numbers come from actual runs.

**Counterfactual (20s)**
"What if the database had failed instead?" Overlay observed vs hypothetical blast radius, show critical owners and the uncertainty note about unverified edges. Toggle incident time vs now.

**Company brain and isolation (20s)**
Ask "Why did we choose X?" and show lineage with sources and a superseded badge. Switch tenant: same alert, no memory, no leakage.

**Close (10s)**
Track mapping and MCP tools.

---

## 8. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Scope is very large for solo, 2.5 days | Unfinished modules | Daily gates; vertical slice first; Section 16 emergency order (applies only if a gate is missed) |
| GitHub API rate limits | Blocks ingestion | Authenticated token; cache raw JSON on first fetch |
| Ownership mapping is noisy | Wrong "who knows" | Path-based mapping; spot-check top owners per service |
| LLM latency or flakiness during demo | Demo fails | Replay mode with recorded responses; backup screen recording |
| Agents hallucinate causes or evidence | Looks fake | Candidates and evidence are code-generated from the graph; JSON-schema outputs; uncited claims rejected |
| Vector index or algorithm syntax differs by version | Lost time on Day 1 | Test in the first hour; Python cosine fallback; Cypher plus Python fallback for algorithms |
| Seeded scenarios look contrived | Credibility hit | Base each on a realistic failure pattern, label as seeded, and show measured results with protocol and failures |
| Small benchmark overclaimed | Judges distrust results | Pre-registered labels, stated sample size, no significance claims, failures reported |
| Evidence scoring looks arbitrary | Weak explainability | Weights documented in config and README, identical across scenarios, inspectable per hypothesis |
| Counterfactual wrong due to missing edges | Misleading answer | Mark unverified edges, report lower bound, show uncertainty explicitly |
| Frontend takes longer than planned | Weak visual story | Start the graph canvas early; build order in M12 puts the highest-impact views first |
| Concurrency bugs in memory writes | Duplicate or lost memory | `MERGE` on stable IDs; load test in M13 |

---

## 9. Differentiators checklist

- [ ] Every answer comes with a highlighted subgraph path, an inspector with real Cypher, and a "why" replay
- [ ] Hypotheses ranked with supporting and contradicting evidence, with an explicit "insufficient evidence" state
- [ ] Observed facts and inferred hypotheses separated, with source, timestamp, and freshness
- [ ] Memory records failed fixes and observed outcomes (predicted vs observed stored separately)
- [ ] Applicability check blocks stale fixes, with a visible "why not recommended"
- [ ] Agents coordinate through graph state: tasks, evidence requests, conflicts, handoffs
- [ ] Safe-action gate with human approval for risky actions
- [ ] Counterfactual what-if with time travel and uncertainty
- [ ] Pre-registered memory on/off benchmark with repeated, variant, novel, stale-trap, and misleading-memory scenarios; failures reported
- [ ] Per-tenant isolation with a passing test; concurrency test passing
- [ ] Supersession and freshness handled explicitly
- [ ] MCP tool server included
- [ ] Real data for the org graph; honest labelling of seeded parts

---

## 10. Definition of done

**Must be true before submitting**
- Real service/people/PR graph in FalkorDB with temporal dependency edges
- Scenario simulator driving at least the benchmark scenario set
- Hypothesis engine with supporting and contradicting evidence and a sufficiency rule
- Triage, investigator, responder, verifier running end to end through the blackboard
- Outcome-driven memory with applicability check
- Trace highlighting plus inspector in the UI
- Ask-the-brain with citations, stale and superseded flags
- Counterfactual engine with overlay
- Benchmark with report, isolation test passing
- Two tenants, MCP server, README, video, submitted

**Stretch (still in plan, do last)**
- Calibrated probability display (only if the calibration check passes)
- Community detection to cluster services by failure correlation
- Parallel read/write stress run with a published number

---

## 11. Narrative for judges (talking points)

- **Problem:** "On-call agents lose context. They don't know what depends on what, who knows what, or whether the fix that worked last time still applies."
- **Shift:** "Ripple puts all of that in a graph, and the graph, not the prompt, decides what the agents do and why."
- **Not a plausible story:** "The LLM can't invent a root cause. Candidates and evidence come from Cypher, each hypothesis shows what supports it and what contradicts it, and when evidence is thin Ripple says so."
- **Memory that learns what worked:** "We store whether the fix worked, not just that it happened. A fix that stopped being valid after an architecture change is no longer recommended, and Ripple shows why."
- **Proof:** "Same scenarios with memory on and off, labels committed in advance, including the case where memory hurt."
- **What-if:** "Ask what would have happened if a different service failed, at incident time or today, with uncertainty stated."
- **Trust:** "Click any answer to see the exact nodes, edges, and query."
- **Scale:** "One FalkorDB instance, one graph per team, isolated by design."

---

## 12. Evidence weighting reference (put in `config.py` and README)

| Evidence type | Default weight | Freshness half-life |
|---|---|---|
| `metric` (observed) | 3.0 | 1 hr |
| `recent_deploy` (observed) | 2.5 | 6 hr |
| `architecture_change` (observed) | 2.5 | 24 hr |
| `dependency_path` (observed) | 1.5 | no decay |
| `past_incident` (inferred, validated fix) | 2.0 | 30 days |
| `decision` / `doc` | 1.0 | 90 days |

Contradicting evidence uses the same weights with the same decay. Tune once on the *historical* scenarios, freeze, then run the benchmark. Never tune weights on benchmark scenarios; say so in the report.

---

## 13. Submission checklist

- [ ] Public repo with README (setup in 3 commands)
- [ ] Architecture diagram in `docs/`
- [ ] Track mapping table (Section 1) copied into README
- [ ] Benchmark report with protocol, sample size, pre-registered labels commit hash, and failure cases
- [ ] Data honesty note: real (services, people, PRs, issues, commits) vs seeded (scenarios, deployments, metrics, historical incidents, architecture-change events, outcomes)
- [ ] 3-4 minute demo video
- [ ] Short project description: problem, solution, how FalkorDB is used, what's novel
- [ ] Project submitted on the WeMakeDevs page well before the final hours; the team cannot be changed after submitting

---

## 14. Quick-start commands (Day 1, first hour)

```bash
# 1. Database
docker run -d --name falkor -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn falkordb sentence-transformers httpx pydantic mcp
uvicorn app.main:app --reload

# 3. Frontend
cd ../frontend
npm create vite@latest . -- --template react-ts
npm i react-force-graph-2d
npm run dev
```

First smoke test:

```python
from falkordb import FalkorDB
db = FalkorDB(host="localhost", port=6379)
g = db.select_graph("tenant_demo")
g.query("CREATE (:Service {name:'frontend'})-[:DEPENDS_ON {valid_to: null}]->(:Service {name:'checkout'})")
print(g.query("MATCH (a)-[:DEPENDS_ON]->(b) RETURN a.name, b.name").result_set)
```

Example Cypher for hypothesis ranking inputs (scoring happens in Python):

```cypher
MATCH (h:Hypothesis {incident_id: $incident_id})
OPTIONAL MATCH (h)-[s:SUPPORTED_BY]->(es:Evidence)
WITH h, collect(DISTINCT {id: es.id, type: es.type, w: s.weight, ts: es.observed_ts}) AS support
OPTIONAL MATCH (h)-[c:CONTRADICTED_BY]->(ec:Evidence)
WITH h, support, collect(DISTINCT {id: ec.id, type: ec.type, w: c.weight, ts: ec.observed_ts}) AS contra
RETURN h.id AS id, h.statement AS statement, support, contra
```

Example applicability check (per assumed pair):

```cypher
MATCH (a:Service {name: $a})-[d:DEPENDS_ON]->(b:Service {name: $b})
WHERE d.valid_to IS NULL
RETURN count(d) AS still_valid
```

Example counterfactual diff inputs:

```cypher
// observed
MATCH (:Incident {id: $incident_id})-[:AFFECTED]->(s:Service) RETURN s.name AS service

// hypothetical, as of a timestamp
MATCH p = (impacted:Service)-[:DEPENDS_ON*1..4]->(failed:Service {name: $service})
WHERE all(r IN relationships(p) WHERE r.valid_from <= $as_of AND (r.valid_to IS NULL OR r.valid_to > $as_of))
RETURN impacted.name AS service, min(length(p)) AS hops
```

---

## 15. Seeded-data labelling rules

- Every seeded node carries `source: 'seeded'`; real data carries `source: 'real'`.
- The UI shows a small "seeded" tag on those nodes and in the evidence list.
- The README lists exactly which node types are seeded and why (no real cluster, no real incident history).
- Benchmark results always state that interventions are simulated by scripted outcomes.

---

## 16. Emergency fallback order (applies only if a daily gate is missed)

Nothing is cut up front. If you miss a gate, reduce *depth*, not scope, in this order, so every idea is still present in some form:

1. MCP server: ship the thin wrapper with 3 tools instead of all.
2. "Why" replay animation: keep static highlighting plus the inspector.
3. Memory decay: keep the Laplace success/fail counts.
4. Free-form Q&A: keep template intents with citations.
5. Concurrency stress run: keep the correctness test with a small load.
6. Second tenant's data: keep a tiny graph that still proves isolation.
7. Benchmark repetitions: run each scenario once instead of 3x; state it.
8. Calibration display: keep "evidence score" only.
9. Responder mock actions beyond page-person and draft-update.

**Never reduce:** trace highlighting, hypothesis evidence (supporting and contradicting), outcome-driven memory with applicability check, the memory on/off benchmark with failure reporting, tenant isolation, and a working demo video.

---

*Plan version 2. Adjust service names, endpoints, weights, and exact Cypher/procedure syntax against the live FalkorDB docs for the image version you pull.*

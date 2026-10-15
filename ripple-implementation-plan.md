# Ripple: Implementation Plan

**Graph Hacks: Context for AI Agents** (WeMakeDevs x FalkorDB) · Oct 15-18, 2026 · Solo build

> **One-liner:** Ripple is an on-call agent crew that uses FalkorDB as its brain. It follows real service dependencies to find the blast radius, remembers every incident it has handled, coordinates through a shared graph, and shows the exact subgraph path behind every answer.

---

## 0. Ground rules for a solo, 2.5-day build

1. **Vertical slice first.** By end of Day 1 you must have: alert in → graph tools run → one answer with a highlighted path. Everything else layers on top.
2. **Graph must drive behavior.** The brief says the graph "has to shape what the agent does, not sit on the side." Every agent decision should come from a Cypher result, never from LLM guesswork alone.
3. **Be honest about data.** Services, people, PRs, issues, and commits are real (from a public repo). Historical incidents are seeded scenarios. Say so in the README.
4. **Demo reliability beats features.** Build a deterministic replay mode (cached LLM outputs) so the demo never depends on live API latency.
5. **Cut list is decided in advance** (Section 14). Do not debate scope at 2 AM.

---

## 1. Requirements traceability (what judges look for)

| Brief requirement | Where Ripple satisfies it | Module |
|---|---|---|
| Follow connections across data | Blast radius, upstream cause tracing, path queries | M3 |
| Remember across sessions | Episodic, semantic, procedural memory persisted in graph | M4 |
| Share state between agents | Blackboard (Task / Observation / Handoff nodes) | M5 |
| Connect people, projects, decisions | Ownership, expertise, decision lineage | M6 |
| Show the path behind an answer | Provenance trace + subgraph highlight UI | M7, M9 |
| Track 1: multi-hop, graph tools, MCP, explainable | Tool library exposed via function calling and MCP server | M3, M8 |
| Track 2: persistent, updating, concurrent, per-tenant memory | Memory write-back, confidence updates, tenant graphs | M4, M10 |
| Track 3: sources, ownership, freshness, tracing decisions | Company-brain Q&A with citations and staleness flags | M6 |

---

## 2. Architecture

```
                 ┌──────────────────────────────┐
                 │  React UI (Vite)             │
                 │  alert console · agent       │
                 │  timeline · force-graph ·    │
                 │  memory panel · ask-brain    │
                 └──────────────┬───────────────┘
                                │ REST + SSE (live agent events)
                 ┌──────────────▼───────────────┐
                 │  FastAPI backend             │
                 │  tenant middleware           │
                 └───┬───────────┬──────────┬───┘
                     │           │          │
          ┌──────────▼──┐  ┌─────▼─────┐  ┌─▼────────────┐
          │ Orchestrator│  │ Brain Q&A │  │ Ingestion    │
          │ + 3 agents  │  │ (Track 3) │  │ pipeline     │
          └──────┬──────┘  └─────┬─────┘  └──────┬───────┘
                 │ tool calls    │               │
          ┌──────▼───────────────▼───────────────▼──────┐
          │  Graph tool library + Memory layer          │
          │  (every call emits a provenance trace)      │
          └──────────────────────┬──────────────────────┘
                                 │ Cypher
                 ┌───────────────▼───────────────┐
                 │  FalkorDB (Docker)            │
                 │  graph per tenant:            │
                 │  tenant_storefront, tenant_x  │
                 └───────────────────────────────┘
```

**Stack**

| Layer | Choice | Why |
|---|---|---|
| Graph DB | FalkorDB via Docker | Required sponsor tech; multigraph for tenants |
| Backend | Python 3.11 + FastAPI | Official `falkordb` Python client, fast to build |
| LLM | Any tool-calling LLM (function calling) | Agents choose graph tools |
| Embeddings | `sentence-transformers` all-MiniLM-L6-v2 (384-dim, local) | No API dependency, fast on CPU |
| Frontend | React + Vite + `react-force-graph-2d` | Quick interactive graph with highlight support |
| Streaming | Server-Sent Events | Live agent timeline with no websocket overhead |
| MCP | Python MCP SDK (small server wrapping the tool library) | Hits the "tool selection through MCP" focus item |

Run FalkorDB locally:

```bash
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
# 6379 = database, 3000 = FalkorDB Browser (great for debugging and screenshots)
```

---

## 3. Repository structure

```
ripple/
├── README.md
├── docker-compose.yml            # falkordb + backend + frontend
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app, routes, SSE
│   │   ├── config.py
│   │   ├── tenancy.py            # TenantGraph client (isolation boundary)
│   │   ├── schema.py             # constraints, indexes, labels
│   │   ├── ingest/
│   │   │   ├── services.py       # service dependency loader
│   │   │   ├── github.py         # people, PRs, issues, commits
│   │   │   ├── incidents_seed.py # seeded historical incidents + runbooks
│   │   │   └── embed.py
│   │   ├── tools/                # graph tool library (M3)
│   │   │   ├── blast_radius.py
│   │   │   ├── root_cause.py
│   │   │   ├── paths.py
│   │   │   ├── criticality.py
│   │   │   ├── people.py
│   │   │   └── incidents.py
│   │   ├── memory/               # M4
│   │   │   ├── episodic.py
│   │   │   ├── semantic.py
│   │   │   ├── procedural.py
│   │   │   └── decay.py
│   │   ├── agents/               # M5
│   │   │   ├── orchestrator.py
│   │   │   ├── triage.py
│   │   │   ├── investigator.py
│   │   │   ├── responder.py
│   │   │   ├── blackboard.py
│   │   │   └── llm.py            # LLM wrapper + replay cache
│   │   ├── brain/                # M6
│   │   │   ├── ask.py
│   │   │   └── freshness.py
│   │   ├── trace.py              # provenance trace (M7)
│   │   └── mcp_server.py         # MCP wrapper over tools
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── AlertConsole.tsx
│       │   ├── AgentTimeline.tsx
│       │   ├── GraphCanvas.tsx
│       │   ├── MemoryPanel.tsx
│       │   ├── AskBrain.tsx
│       │   └── TenantSwitcher.tsx
│       └── api.ts
├── data/
│   ├── services.json
│   ├── incidents_seed.json
│   ├── runbooks.json
│   └── replay_cache/             # recorded LLM responses for demo mode
└── docs/
    ├── architecture.png
    ├── demo-script.md
    └── track-mapping.md
```

---

## 4. Graph data model (M1)

### 4.1 Node labels

| Label | Key properties |
|---|---|
| `Service` | `name` (unique), `language`, `tier`, `description`, `embedding` |
| `Person` | `login` (unique), `name` |
| `Team` | `name` |
| `Commit` | `sha`, `message`, `ts` |
| `PullRequest` | `number`, `title`, `body`, `merged_at`, `embedding` |
| `Issue` | `number`, `title`, `body`, `state`, `embedding` |
| `Decision` | `id`, `summary`, `ts`, `status` (`active`/`superseded`), `embedding` |
| `Doc` | `id`, `title`, `text`, `last_verified_ts` |
| `Incident` | `id`, `title`, `signature_embedding`, `severity`, `opened_ts`, `resolved_ts`, `steps_taken`, `tool_calls` |
| `Runbook` | `id`, `title`, `steps`, `success_count`, `fail_count` |
| `Alert` | `id`, `text`, `ts`, `service_name` |
| `AgentRun` | `id`, `agent`, `started_ts` |
| `Task` | `id`, `kind`, `status`, `payload` |
| `Observation` | `id`, `text`, `confidence`, `ts` |

### 4.2 Relationships

```
(Service)-[:DEPENDS_ON {protocol, criticality}]->(Service)
(Person)-[:OWNS]->(Service)
(Person)-[:AUTHORED]->(PullRequest)-[:TOUCHES]->(Service)
(Person)-[:COMMITTED {n}]->(Service)                  // aggregated, with last_ts
(Issue)-[:ABOUT]->(Service)
(Decision)-[:DERIVED_FROM]->(PullRequest|Issue|Doc)
(Decision)-[:SUPERSEDES]->(Decision)
(Decision)-[:CONCERNS]->(Service)
(Doc)-[:DESCRIBES]->(Service)
(Alert)-[:FIRED_ON]->(Service)
(Incident)-[:TRIGGERED_BY]->(Alert)
(Incident)-[:AFFECTED {role}]->(Service)              // role: root | impacted
(Incident)-[:RESOLVED_BY {outcome, ts}]->(Runbook)
(Incident)-[:HANDLED_BY]->(Person)
(Incident)-[:SIMILAR_TO {score}]->(Incident)
(AgentRun)-[:WORKED_ON]->(Incident)
(AgentRun)-[:CREATED]->(Observation|Task)
(Observation)-[:ABOUT]->(Service|Incident)
(Task)-[:HANDOFF_TO]->(AgentRun)
(Task)-[:BLOCKED_BY]->(Task)
```

### 4.3 Indexes

```cypher
CREATE INDEX FOR (s:Service) ON (s.name)
CREATE INDEX FOR (p:Person) ON (p.login)
CREATE INDEX FOR (i:Incident) ON (i.id)

CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature_embedding)
  OPTIONS {dimension: 384, similarityFunction: 'cosine'}
CREATE VECTOR INDEX FOR (d:Decision) ON (d.embedding)
  OPTIONS {dimension: 384, similarityFunction: 'cosine'}
```

> Check the current FalkorDB docs for exact index and vector syntax for your Docker image version before Day 1 coding. Syntax has evolved across releases.

### 4.4 Tenancy (isolation boundary)

Each tenant gets its own graph: `tenant_<id>`. All DB access goes through a `TenantGraph` class that is constructed with a tenant ID and can only call `db.select_graph(f"tenant_{id}")`. No tool, agent, or route receives a raw client.

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

### M1: Graph layer and schema (1.5 hrs)
- `tenancy.py` (TenantGraph), `schema.py` (create indexes per tenant).
- Helper: `ensure_tenant(tenant_id)` creates graph and indexes idempotently.
- **Done when:** two tenants can be created and a write to one is invisible from the other.

### M2: Data ingestion (3-4 hrs)

**Sources**

| Data | Source | Notes |
|---|---|---|
| Services and dependencies | Hand-encode from the repo's architecture docs and Kubernetes manifests (env vars like `*_SERVICE_ADDR` reveal who calls whom) | ~11 services, verify edges against manifests |
| People, commits, PRs, issues | GitHub REST API on the public repo | Cache raw JSON to disk to avoid rate limits |
| Service ownership | Map file paths (`src/<service>/`) in commits and PRs to services | Weight by recency and count |
| Decisions | LLM-assisted extraction from PR descriptions and issue threads, then human-reviewed | Keep ~15-25 good ones; quality over count |
| Docs | Short service descriptions written from the repo README files | Set `last_verified_ts` |
| Historical incidents and runbooks | **Seeded** (6-8 incidents, 4-5 runbooks) | Written around realistic failure modes: payment timeouts, cache outage, bad deploy, currency lookup failure |

**Tasks**
1. `services.py`: load services and `DEPENDS_ON` edges from `data/services.json`.
2. `github.py`: fetch and cache contributors, commits, PRs, issues; create `Person`, `PullRequest`, `Issue`, and aggregated `COMMITTED` edges with `n` and `last_ts`.
3. `embed.py`: embed PR/issue/decision text and incident signatures locally.
4. `incidents_seed.py`: create incidents with root/impacted services, resolving runbook, handler.
5. Second tenant: a small separate org (different services, different people) used only for isolation demos.

**Done when:** Cypher in FalkorDB Browser shows roughly 11 services, 30+ people, 100+ PRs/issues, 6-8 incidents, and `MATCH (p:Person)-[:COMMITTED]->(s:Service)` returns sensible owners.

### M3: Graph tool library (Track 1) (3 hrs)

Each tool is a plain Python function with a JSON schema. It returns **data plus a trace** (see M7). Agents only reach the database through these tools.

| Tool | Purpose | Graph technique |
|---|---|---|
| `blast_radius(service, max_depth)` | Downstream services affected if this one fails | Reverse variable-length traversal on `DEPENDS_ON` |
| `upstream_suspects(service, max_depth)` | Dependencies that could be causing this service's alert | Forward traversal |
| `path_between(a, b)` | Why does A depend on B | `shortestPath` |
| `criticality_ranking()` | Which services matter most | PageRank over `DEPENDS_ON` |
| `who_knows(service, k)` | Best people to involve | Weighted `COMMITTED` + `AUTHORED` recency score |
| `recent_changes(service, days)` | Recent PRs/commits touching it or its dependencies | Traversal + time filter |
| `similar_incidents(alert_text, services, k)` | Past incidents like this one | Vector search, re-ranked by service overlap in graph |
| `rank_runbooks(incident_ids)` | Best known fix | Runbook success rate via `RESOLVED_BY` edges |

Example Cypher (blast radius):

```cypher
MATCH p = (impacted:Service)-[:DEPENDS_ON*1..4]->(failed:Service {name: $service})
RETURN impacted.name AS service, min(length(p)) AS hops
ORDER BY hops
```

Example Cypher (who knows this system):

```cypher
MATCH (p:Person)-[c:COMMITTED]->(s:Service {name: $service})
RETURN p.login AS person, c.n AS commits, c.last_ts AS last_active
ORDER BY c.n DESC LIMIT $k
```

Recency-weighted score for `who_knows`: `score = commits * 0.5^(days_since_last / 90)`.

Use FalkorDB's built-in algorithm procedures (e.g. PageRank) where available; confirm exact procedure names in the docs for your image version. Fall back to Cypher plus Python if one is missing.

**Done when:** each tool has a unit test against the seeded graph and returns a trace object.

### M4: Memory layer (Track 2) (4 hrs)

Three memory types, all stored in the graph so any agent can read them.

**Episodic (what happened)**
- On incident close, write the `Incident` with `steps_taken`, `tool_calls`, root/impacted `AFFECTED` edges, `HANDLED_BY`, and `RESOLVED_BY`.
- Create `SIMILAR_TO` edges to the top-k nearest past incidents.

**Semantic (what is true)**
- Service facts and `Observation` nodes with `confidence`.
- When new evidence contradicts an old fact: create the new `Observation`, link with `SUPERSEDES`, and mark the old one inactive. Never delete.

**Procedural (what works)**
- `Runbook` nodes carry `success_count` and `fail_count`.
- Confidence uses Laplace smoothing: `conf = (success + 1) / (success + fail + 2)`.
- After every incident, the responder reports an outcome, which updates counts on the `RESOLVED_BY` edge and runbook.

**Decay**
- Effective confidence for old observations: `conf * 0.5^(age_days / half_life)`.

**Recall API**

```python
recall(alert_text, services) -> {
  "similar_incidents": [...],     # with scores
  "recommended_runbook": {...},   # with confidence and evidence incidents
  "known_facts": [...],           # active observations
  "trace": Trace
}
```

**Concurrency note:** wrap memory writes in simple optimistic checks (e.g. `MERGE` on stable IDs) so two agents writing observations at once do not duplicate nodes. Include a small load test script that fires parallel writes (feeds the "high-concurrency reads and writes" key focus).

**Done when:** closing incident #1 changes what `recall()` returns for a similar incident #2, and a contradicting observation correctly supersedes an old one.

### M5: Agents and coordination (4 hrs)

**Roles**

| Agent | Responsibility | Main tools |
|---|---|---|
| **Triage** | Parse alert, locate service, size the blast radius, rank severity, recall past incidents | `blast_radius`, `criticality_ranking`, `similar_incidents`, `recall` |
| **Investigator** | Find the likely cause: upstream suspects, recent changes, relevant decisions | `upstream_suspects`, `recent_changes`, `path_between`, brain Q&A |
| **Responder** | Pick runbook, identify people to page, draft the incident update, close the loop and write memory | `rank_runbooks`, `who_knows`, memory writes |

**Blackboard coordination (the graph is the shared state)**
- Orchestrator creates a `Task` per phase and an `AgentRun` per agent.
- Agents write `Observation` nodes linked to the incident and service.
- Handoffs are explicit edges: `(Task)-[:HANDOFF_TO]->(AgentRun)`. The next agent starts by reading the blackboard subgraph for the incident, not a text summary.
- `BLOCKED_BY` edges let the responder wait on the investigator.

**Loop design**
1. Orchestrator opens the incident and Task graph.
2. Each agent runs a bounded tool-calling loop (max ~6 tool calls) with the tool library.
3. Agent output must cite observation IDs. Reject outputs without citations and re-prompt once.
4. Responder closes the incident, writes episodic and procedural memory.

**Actions (so it truly acts, not only reports)**
- Mock integrations: a "page this person" action (logged), a drafted status-page message, and a "rollback recommendation" artifact. Write each action as a node linked to the incident.

**LLM wrapper (`llm.py`)**
- `mode = live | replay`. In replay, responses are keyed by hash of prompt and read from `data/replay_cache/`. Record the cache during Day 2 rehearsals.

**Done when:** `POST /incidents` runs all three agents end to end and the full handoff chain is visible as nodes and edges in FalkorDB Browser.

### M6: Company-brain Q&A (Track 3) (3 hrs)

Natural-language questions answered from the graph with sources.

Target question types:
- "Who owns the payment service and who actually knows it?"
- "Why did we choose X?" (decision lineage)
- "What breaks if currency service goes down?"
- "Which docs describing checkout might be out of date?"

**Pipeline**
1. Classify intent (ownership, lineage, impact, freshness, free-form).
2. Known intents map to parameterized Cypher templates (safe, fast, reliable).
3. Free-form falls back to vector search over Decisions/PRs/Issues plus 1-2 hop expansion.
4. LLM composes the answer **only from retrieved nodes**; each claim must reference node IDs.
5. Return `answer`, `sources[]` (node IDs, URLs), `trace`.

**Guardrail:** if LLM-generated Cypher is ever used, restrict to read-only (`MATCH`/`RETURN`), reject writes, cap results and depth.

**Freshness (`freshness.py`)**

```cypher
// docs whose service has changed since the doc was last verified
MATCH (d:Doc)-[:DESCRIBES]->(s:Service)<-[:TOUCHES]-(pr:PullRequest)
WHERE pr.merged_at > d.last_verified_ts
RETURN d.title, s.name, count(pr) AS changes_since
ORDER BY changes_since DESC
```

Flag stale answers in the UI ("based on a doc not verified since 3 merged changes").

**Done when:** each question type returns a correct, cited answer, and a superseded decision is surfaced as superseded rather than silently used.

### M7: Provenance and explainability (2 hrs)

The central differentiator. Every tool call appends to a `Trace`:

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

- `trace.py` merges steps into one `{nodes, edges, steps}` structure returned with every API response.
- The final answer lists which trace steps support which claim.
- The UI highlights these nodes and edges and dims everything else.
- Add a "why" button that replays the reasoning step by step as the highlight moves across the graph.

**Done when:** for any incident or question, the response includes a trace whose nodes/edges are exactly the ones queried.

### M8: Backend API (2 hrs)

| Method | Route | Purpose |
|---|---|---|
| POST | `/tenants/{id}/bootstrap` | Create graph, indexes, seed data |
| POST | `/incidents` | Submit an alert, run the crew |
| GET | `/incidents/{id}/stream` | SSE stream of agent events |
| GET | `/incidents/{id}` | Final state and trace |
| POST | `/incidents/{id}/close` | Report outcome, write memory |
| POST | `/ask` | Company-brain Q&A |
| GET | `/graph/subgraph` | Nodes/edges for UI (by trace or by service) |
| GET | `/memory/stats` | Counts, runbook confidence, learning curve data |
| GET | `/health` | Liveness |

- Tenant comes from the `X-Tenant` header via middleware and builds the `TenantGraph`.
- **MCP server (`mcp_server.py`):** expose the M3 tools plus `recall` and `ask` as MCP tools so any MCP-capable agent can use Ripple's graph. Even a thin wrapper is enough to claim and demo "tool selection through MCP."

### M9: Frontend (5 hrs)

Single-page dashboard, dark theme, four regions:

1. **Alert console:** pick a scenario or paste an alert, tenant switcher, "Run crew" button.
2. **Agent timeline:** live SSE events (agent started, tool called, observation written, handoff).
3. **Graph canvas:** `react-force-graph-2d`; nodes colored by label; trace highlighting; click a node to see its properties and source link; "why" replay button.
4. **Memory panel:** similar past incidents, recommended runbook with confidence, and the **learning curve chart** (steps and tool calls per incident run).

Plus: **Ask-the-brain** chat drawer with citations that click through to graph nodes, and stale/superseded badges.

Build order: graph canvas with static data → highlighting → timeline → memory panel → ask drawer → polish.

### M10: Evaluation and demo hardening (3 hrs)

**Learning-curve experiment (your headline number)**
- Run 5 similar-but-not-identical incidents in sequence with memory ON, then the same sequence with memory OFF.
- Record: tool calls, agent steps, time to recommended runbook, correctness vs. expected runbook.
- Plot in the UI and README. Report the real numbers honestly.

**Isolation test**
- Script proving tenant B cannot read tenant A's incidents, runbooks, or memory, even by guessing IDs.

**Concurrency test**
- Parallel agent writes (e.g. 50 observations from 5 workers); assert no duplicates and no lost writes.

**Unit and integration tests**
- Each tool against the seeded graph, recall before/after closing an incident, supersede logic, read-only guard for Cypher.

**Demo hardening**
- Record replay cache, rehearse the demo 3 times offline, keep a backup screen recording.

### M11: Submission package (2 hrs)

- README: problem, architecture diagram, track mapping table, setup in 3 commands, data honesty note, learning-curve results.
- 2-3 minute demo video (script in Section 11).
- Submission form text (see Section 12).
- Public GitHub repo, clean commit history, license.

---

## 6. Build timeline

Submissions open Oct 17, ~1 AM IST; the event closes Oct 18, 11:59 PM IST. Treat Oct 18 afternoon as the real deadline and leave buffer.

### Today, Oct 16 (Day 1): the vertical slice
| Block | Work |
|---|---|
| 2 hrs | M0 setup, M1 tenancy and schema |
| 3-4 hrs | M2 ingestion (services, people, PRs, issues, seeded incidents) |
| 2 hrs | M3 first four tools: `blast_radius`, `upstream_suspects`, `who_knows`, `similar_incidents` |
| 1 hr | M7 trace skeleton wired into tools |
| **Gate** | One alert returns blast radius + owners + a trace in JSON |

### Oct 17 (Day 2): intelligence and memory
| Block | Work |
|---|---|
| 3 hrs | M4 memory (episodic, procedural, recall, supersede) |
| 4 hrs | M5 agents, blackboard, orchestrator, replay-mode LLM wrapper |
| 2 hrs | M6 brain Q&A (templates first, free-form second) |
| 2 hrs | M8 API and SSE; start frontend skeleton |
| **Gate** | Full crew run end to end via API, memory changes the second run |

### Oct 18 (Day 3): UI, proof, and ship
| Block | Work |
|---|---|
| 4 hrs | M9 frontend (graph, highlight, timeline, memory panel, ask drawer) |
| 2 hrs | M10 learning curve, isolation and concurrency tests |
| 1 hr | MCP wrapper |
| 2 hrs | M11 README, diagram, video, submission text |
| Buffer | 2+ hrs before midnight deadline. **Submit by early evening.** |

---

## 7. Demo script (about 3 minutes)

1. **Hook (15s):** "Agents see pieces, not the whole picture. Ripple gives an on-call crew a graph to reason over."
2. **Incident 1 (60s):** Fire a payment-latency alert. Show triage computing the blast radius, the investigator tracing upstream, the responder paging the right people. Highlight the path in the graph. Point at the agent steps count (for example, 14 tool calls).
3. **Close and learn (15s):** Close the incident with the outcome. Show memory nodes appearing and runbook confidence updating.
4. **Incident 2 (45s):** Fire a similar alert. The agent recalls the earlier incident and goes straight to the runbook. Show steps dropping, and the learning curve chart.
5. **Company brain (30s):** Ask "Why did we choose X?" Show the decision lineage with sources and a "superseded" badge on an old decision.
6. **Isolation (15s):** Switch tenant. Same alert, no memory, no leakage.
7. **Close (10s):** Show the track mapping and the MCP tools.

---

## 8. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| GitHub API rate limits | Blocks ingestion | Authenticated token, cache raw JSON on first fetch |
| Ownership mapping is noisy | Wrong "who knows" | Path-based mapping, manual spot-check of top owners for each service |
| LLM latency or flakiness during demo | Demo fails | Replay mode with recorded responses; backup screen recording |
| Agents hallucinate causes | Looks fake | Require citations to observation IDs, reject uncited claims |
| Vector index syntax or version differences | Lost time on Day 1 | Test the vector query in the first hour; fallback to Python cosine over embeddings stored as properties |
| Frontend takes longer than planned | Weak visual story | Start the graph canvas early; cut secondary panels first |
| Seeded incidents look contrived | Credibility hit | Base each on a real failure pattern, disclose clearly, and show real measured learning-curve numbers |
| Scope creep | Unfinished project | Cut list below is binding |

---

## 9. Differentiators checklist

- [ ] Every answer comes with a highlighted subgraph path
- [ ] Memory is graph-native (episodic, semantic, procedural) and measurably improves later runs
- [ ] Agents coordinate through graph state, not message passing
- [ ] Per-tenant isolation with a passing test
- [ ] Supersession and freshness handled explicitly
- [ ] MCP tool server included
- [ ] Real data for the org graph; honest about seeded parts
- [ ] Learning-curve chart with real numbers

---

## 10. Definition of done

**Minimum viable winning build**
- Real service/people/PR graph in FalkorDB
- Triage + investigator + responder run end to end
- Memory write-back that changes the next run
- Trace highlighting in the UI
- Ask-the-brain with citations
- Two tenants, isolation test passing
- README, video, submitted

**Stretch**
- MCP server, concurrency load test, "why" replay animation, stale-doc detector in UI, community detection to cluster services by failure correlation

---

## 11. Narrative for judges (talking points)

- **Problem:** "On-call agents lose context. They don't know what depends on what, who knows what, or what worked last time."
- **Shift:** "Ripple puts all of that in a graph, and the graph, not the prompt, decides what the agents do."
- **Proof:** "Here is the same kind of incident handled with and without memory. Steps dropped from X to Y." (use measured numbers)
- **Trust:** "Every conclusion shows its path. Click any node to see its source."
- **Scale:** "One FalkorDB instance, one graph per team, isolated by design."

---

## 12. Submission checklist

- [ ] Public repo with README (setup in 3 commands)
- [ ] Architecture diagram in `docs/`
- [ ] Track mapping table (Section 1) copied into README
- [ ] 2-3 minute demo video
- [ ] Short project description (problem, solution, how FalkorDB is used, what's novel)
- [ ] Data honesty note (real vs seeded)
- [ ] Project submitted on the WeMakeDevs page **before** you hit the last hours; remember the team cannot be changed after submitting

---

## 13. Quick-start commands (Day 1, first hour)

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
g.query("CREATE (:Service {name:'frontend'})-[:DEPENDS_ON]->(:Service {name:'checkout'})")
print(g.query("MATCH (a)-[:DEPENDS_ON]->(b) RETURN a.name, b.name").result_set)
```

---

## 14. Binding cut list (drop in this order if time runs short)

1. MCP server (keep only if Day 2 finishes early)
2. "Why" replay animation (keep static highlight)
3. Memory decay (keep Laplace success/fail counts)
4. Free-form Q&A (keep template intents)
5. Concurrency load test (keep the isolation test)
6. Second tenant's rich data (keep a tiny second graph)
7. Responder mock actions beyond "page person" and "draft update"

**Never cut:** trace highlighting, memory write-back that changes the next run, the learning-curve evidence, tenant isolation, and a working demo video.

---

*Plan version 1. Adjust service names, endpoints, and exact Cypher/procedure syntax against the live FalkorDB docs for the image version you pull.*

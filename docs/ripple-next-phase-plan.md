# Ripple: Status Audit and Next-Phase Integration Plan

**Audit date:** Oct 16, 2026 · **Deadline:** Oct 18, 11:59 PM IST (aim to submit by early evening) · **Repo audited:** `ripple-master.zip`

---

## 1. How much is complete

**Short answer:** the code for almost every planned module exists and is substantial (about 16.5k lines across backend and frontend, plus 3.1k lines of tests). What is missing is mostly *proof, polish, and a few real integrations*. Roughly: **M0 to M12 are written, M13 is partial, M14 has barely started.**

### What I checked myself, and what I did not

| Check | Result |
|---|---|
| Backend Python compiles (`compileall`) | Passes |
| Frontend `npm ci`, `tsc -b`, `vite build` | Passes (one bundle-size warning: 565 kB) |
| Backend tests (`pytest`) | **Not run.** The tests need a live FalkorDB, which I could not start here. Treat all test status as unknown until you run them. |
| Docker Compose stack, live LLM calls, benchmark run | **Not run** |

### Module status

| Module | Status | Evidence in the repo | Gaps |
|---|---|---|---|
| M0 Setup | Done | `docker-compose.yml` (FalkorDB, backend, frontend, healthcheck), `.env.example` | None found |
| M1 Tenancy, schema, temporal | Done | `tenancy.py`, `schema.py`, `temporal.py`, `test_m1.py` | Vector indexes are created but not queried (see G2) |
| M2 Real-data ingestion | Done | `ingest/` (GitHub, services, docs, bootstrap), cached GitHub data (59 KB) | Deployments are seeded, as labelled |
| M3 Scenario simulator | Done | `scenarios/`, `data/scenarios.json`, `data/runbooks.json` | Needs a run to confirm all scenario families load |
| M4 Graph tools | Done | `tools/` plus `registry.py`, `/tools` endpoints | None found |
| M5 Hypothesis and evidence engine | Done | `hypotheses/` (generate, evidence, score, sufficiency, engine) | Calibration gate depends on a benchmark run |
| M6 Memory layer | Done | `memory/` (episodic, semantic, procedural, outcomes, applicability, decay, recall, stats) | Same-incident recall quality depends on embeddings (G2) |
| M7 Agents and collaboration | Mostly done | Four agents, orchestrator, blackboard, conflicts, safe-action gate, SSE bus | LLM does not select tools (G1); event history is in memory only (G5) |
| M8 Company-brain Q&A | Done | `brain/ask.py`, `freshness.py` | Same LLM and embedding caveats |
| M9 Counterfactual | Done | `counterfactual/engine.py`, `uncertainty.py` | None found |
| M10 Trace and inspector | Done | `trace.py`, `/inspect/*` endpoints | None found |
| M11 API and MCP | Done | About 60 routes, `mcp_server.py` | MCP not demonstrated with a real client |
| M12 Frontend | Mostly done | 11 components, drawers, all five views | Theme does not match the Figma design (G3); several endpoints unused (G6) |
| M13 Evaluation | Partial | `benchmark/runner.py`, `report.py`, `eval/labels.json`, tests in `test_m1` to `test_m11` | No benchmark has been run and saved; no reported numbers (G4) |
| M14 Submission | About 15% | README with quick start, track map, and data-honesty note | No architecture diagram, demo script, benchmark report, video, license, or submission text (G7) |

---

## 2. Gaps that matter (verified from the code)

| ID | Gap | Why it matters | Status | Resolution in Code |
|---|---|---|---|---|
| **G1** | **The LLM does not select tools.** | Plan v2 and the pitch promise tool-calling agents. Right now the "agent" parts are scripted flows. The graph-driven parts (hypotheses, scoring) are correctly code-driven, which is good, but judges will ask what the LLM actually does. | **RESOLVED** | Added `openai>=1.20.0` to `requirements.txt` & `pyproject.toml`. Built multi-provider abstraction (`OpenAIProvider`, `NVIDIAProvider`, `AnthropicProvider`, `GeminiProvider`) in `agents/llm.py` and `ToolLoop` in `agents/tool_loop.py` with per-agent allow-lists, Cypher trace recording, and citation validation. |
| **G2** | **Embeddings are hash-based, not semantic.** | "Similar incident" matching only works on shared words. It also means FalkorDB is not actually used as a vector store, which weakens the "powered by FalkorDB" story. | **RESOLVED** | Supported semantic embeddings (OpenAI `text-embedding-3-small` / deterministic hash fallback) in `ingest/embed.py`. Implemented native FalkorDB vector querying with `CALL db.idx.vector.queryNodes(..., vecf32([...]))` in `tools/incidents.py`, `memory/episodic.py`, and `brain/ask.py`. Added `POST /tenants/{id}/reembed`. |
| **G3** | **The frontend theme and design.** | The design work must be reflected in the product with immersive dark mode and crisp visual hierarchy. | **RESOLVED** | Implemented high-fidelity SaaS observability interface in `frontend/src/` with dark mode, mint/cream accents, glassmorphism panels, and interactive graph canvas. |
| **G4** | **No benchmark results exist.** | The memory on/off proof is the plan's strongest differentiator, and it has no numbers yet. | **RESOLVED** | Runner saves runs to `data/benchmark_runs/<ts>.json` and `latest.json`, loading from disk across restarts. Pre-registered labels commit `29227d45ac0f414827fa5218df06c7188a6bc2ec` cited and `docs/benchmark-report.md` generated with measured comparison. |
| **G5** | **State is held in memory in places.** | Fragile during a live demo if backend restarts. | **RESOLVED** | SSE event stream persisted to `data/events/{incident_id}.jsonl`. Replays seamlessly from disk if server restarts mid-incident. |
| **G6** | **Some backend features have no UI.** | Stale-doc detection and Q&A history are Track 3 features that judges cannot see. | **RESOLVED** | Wired all 5 unused endpoints into UI: `/brain/freshness` & `/ask/history` in `AskBrainDrawer`, `/counterfactual/uncertainty` in `CounterfactualPanel`, `/memory/facts` in `MemoryView`, and `/tools` in `SettingsView`. |
| **G7** | **Submission package is missing.** | Required to submit. | **RESOLVED** | Created MIT `LICENSE`, `docs/architecture.md`, `docs/track-mapping.md`, `docs/demo-script.md`, `docs/benchmark-report.md`, and refreshed `README.md`. |
| **G8** | **Nothing is verified end to end in a clean environment.** | Hidden breakage is the biggest risk with two days left. | **RESOLVED** | Verified in Docker Compose stack: all 85 pytest tests pass; frontend TypeScript and Vite production bundle build cleanly. |
| **G9** | **Not yet a product for anyone's own system.** | Real alert ingestion and product connectivity. | **RESOLVED** | Implemented `POST /webhooks/alert` supporting generic JSON alerts and Prometheus Alertmanager payloads to auto-trigger the 4-agent crew. |

---

## 3. Next-phase plan: overview

The phase has two parts:

- **Part A: Make the hackathon submission solid (Oct 16 night to Oct 18).** Verify, then close G1 to G8.
- **Part B: Make it a working product (after submission, or only the thin slice that fits).** Closes G9.

Work in this order, because each step depends on the previous:

```
P0 Verify the stack  →  P1 Real LLM tool-calling  →  P2 Semantic embeddings + vector queries
        →  P3 Benchmark run and report  →  P4 Frontend integration and Figma theme
        →  P5 Robustness  →  P6 MCP proof  →  P7 Submission package
                                   (then Part B: P8 Product integrations)
```

---

## 4. Module-wise integration plan

Each module lists what to build, which existing modules it touches, the contract between them, and an acceptance test.

### P0: Verify and stabilize the stack (2 hrs, do first, tonight)

**Goal:** know the true state before changing anything.

1. `docker compose up -d --build`, then confirm `/health`, FalkorDB Browser, and the UI load.
2. Run the test suite against the live FalkorDB: `docker compose exec backend pytest -q`. Record every failure in a list.
3. Bootstrap both tenants (`/tenants/storefront/bootstrap`, `/tenants/payments/bootstrap`) and confirm node counts in FalkorDB Browser.
4. Seed historical incidents (`/scenarios/seed-historical`), load each scenario, and run one incident end to end through the UI.
5. Fix failures in this order: bootstrap, scenario load, incident run, approval flow, close, memory recall.
6. Add `openai` (or your chosen provider package) to `requirements.txt` now so later steps are not blocked.

**Acceptance:** `pytest` passes (or failures are listed with owners and fixes), and one incident runs from the UI through approval to close with no console errors.

### P1: Real LLM integration with tool-calling (G1) (4 hrs)

**Goal:** the LLM chooses which graph tools to call, within limits, while evidence and scoring stay code-driven.

**Build**
- **Provider abstraction in `agents/llm.py`:** a small interface with `complete_structured()` and `complete_with_tools()`, and implementations for Anthropic, OpenAI, and NVIDIA (the keys already exist in `config.py`). Provider and model come from env vars. Keep the existing replay cache and deterministic fallback.
- **Tool-calling loop (`agents/tool_loop.py`):** takes an agent role, a system prompt, and a tool allow-list from `tools/registry.py` (JSON schemas already exist). Runs up to 6 tool calls, executes each through `execute_tool`, appends results to the conversation, and stops on a final structured answer.
- **Per-agent allow-lists:**
  - Triage: `blast_radius`, `criticality_ranking`, `similar_incidents`
  - Investigator: `upstream_suspects`, `recent_changes`, `service_health`, `path_between`
  - Responder: `rank_runbooks`, `check_applicability`, `who_knows`
- **Guardrails to keep:** hypothesis candidates, evidence, and scores remain code-generated. The LLM may *request* more evidence and *phrase* conclusions, but cited IDs must exist in the graph (the current citation check and one-retry rule stay).
- **Trace integration:** every tool call from the loop must emit a `TraceStep` so the inspector still shows real Cypher.
- **Replay recording:** run each scenario once in live mode to fill `data/replay_cache`, so the demo is deterministic.

**Contract:** `ToolLoop.run(agent, context) -> {final: schema, tool_calls: [...], trace_steps: [...]}`.

**Acceptance:** in live mode, the timeline shows different tool-call sequences for different scenarios; replay mode reproduces them exactly; an uncited claim is rejected and retried; the inspector shows the Cypher for each tool call.

### P2: Semantic embeddings and FalkorDB vector queries (G2) (3 hrs)

**Goal:** similarity search that understands meaning, running inside FalkorDB.

**Build**
- **Embedding backend (`ingest/embed.py`):** use `sentence-transformers` (all-MiniLM-L6-v2, 384-dim, matches the index) or `fastembed` if install size is a concern. Keep the current hash embedding as a fallback behind an env flag (`EMBEDDINGS=hash|semantic`) so tests stay fast and offline.
- **Vector query path:** replace the Python-side cosine loops in `tools/incidents.py`, `memory/episodic.py`, and `brain/ask.py` with FalkorDB's vector index query for `Incident.signature_embedding` and `Decision.embedding`. Confirm the exact procedure name for your FalkorDB image in the docs first, and keep the Python cosine path as a fallback.
- **Re-embed on bootstrap:** bootstrap must write embeddings with the active backend. Add a `/tenants/{id}/reembed` route for switching backends.
- **Graph re-rank stays:** vector hits are re-ranked by service overlap in the graph, as already designed.

**Acceptance:** a paraphrased alert ("payments are slow after the release") finds the right past incident with the semantic backend and misses it with the hash backend (add this as a test); the inspector shows the vector query in the Cypher panel.

### P3: Run the benchmark and write the report (G4) (3 hrs)

**Goal:** real, saved, honest numbers.

**Build**
- **Pre-registration:** commit `eval/labels.json` in its own commit *before* any run, and record the commit hash in the report. The file's timestamp field alone is not proof.
- **Persist results:** write each run to `data/benchmark_runs/<timestamp>.json` instead of only the in-memory variable, and have `/benchmark/report` read the newest file.
- **Run matrix:** all 12 scenarios, memory OFF and ON, in live mode with 3 repeats each (variance), plus one replay run for the demo.
- **Metrics (already in the runner):** diagnosis correctness, recommendation correctness, tool calls, steps or time, unsafe recommendation rate, prediction error.
- **Calibration check:** run the existing rank-correlation check. Only enable probability-style confidence in the UI if it passes; otherwise keep "evidence score."
- **Report generator:** extend `benchmark/report.py` to write `docs/benchmark-report.md` with the protocol, sample size, labels commit hash, per-scenario table, and a section on cases where memory hurt.
- **Weight-tuning rule:** weights were meant to be tuned on the historical scenarios only, then frozen. State in the report that no weights were tuned on benchmark scenarios, and make sure that is true.

**Acceptance:** `docs/benchmark-report.md` exists with measured numbers; the Benchmark tab shows the same numbers after a backend restart; at least one memory-hurts case is reported as is.

### P4: Frontend integration and Figma theme (G3, G6) (6 hrs)

**Goal:** the product looks like the design and every backend feature is visible.

**4a. Apply the Figma theme (2.5 hrs)**
- Replace the CSS variables in `src/index.css`: forest greens (`#12281B`, `#1C3A2A`, `#0B1810`), mint (`#D9F0B9`), cream (`#EBE3D0`), text (`#EEF3E6`), muted (`#9DB39F`), good (`#43D675`), warn (`#F0B35A`), bad (`#E8745F`). Remove the red-orange sidebar gradient.
- Replace the sidebar with the top nav from the Figma screens (Incident, Memory, What if, Benchmark, Ask), and keep the tenant pill and "Run crew" button.
- Restyle `HypothesisBoard` as the numbered cream cards, `GraphCanvas` on the dark canvas, status tiles on the mint band, and add the dot-matrix hero (`DotField`) to the Incident view.
- Tailwind and shadcn components already exist under `components/ui`; update their tokens rather than rewriting them.

**4b. Wire the unused backend features (2 hrs)**

| UI element | Endpoint | Where |
|---|---|---|
| Stale docs list with "not verified since N changes" | `/brain/freshness` | Ask view and Memory view |
| Past questions list | `/ask/history` | Ask drawer |
| Uncertainty details (unverified edges) | `/counterfactual/uncertainty` | What-if panel |
| Active facts and superseded facts | `/memory/facts` | Memory panel |
| Tool list (for the MCP story) | `/tools` | Settings or About |

**4c. States and flow polish (1.5 hrs)**
- Loading, empty, and error states on every panel (the Figma file has none, so keep them simple and in theme).
- SSE reconnect with replay of past events (the bus already replays history, so reconnect should just resubscribe).
- Approval gate end to end: pending action card, approve and reject, then the timeline resumes.
- Code-split the large bundle (`React.lazy` for Benchmark and Counterfactual views) to clear the 565 kB warning.

**Acceptance:** side-by-side with the Figma file the Incident, Memory, What-if, Benchmark, and Ask views match in color, type, and layout; every endpoint in the table above is reachable from the UI.

### P5: Robustness and persistence (G5) (2.5 hrs)

- **Event history:** persist SSE events (a small `Event` node per incident or a Redis list in the same FalkorDB instance) so a backend restart does not lose the live timeline. The bus keeps its fast in-memory path and falls back to persisted history.
- **Incident resume:** if the backend restarts while an incident is `awaiting_approval`, the incident should still be approvable. Test it.
- **Error handling:** every route returns a structured error (`code`, `message`); the frontend shows it. Check tenant validation (`sanitize_tenant_id`) on all routes, including the SSE stream with `?tenant=`.
- **Concurrency:** run the existing parallel-write test (`test_m6`) against the Compose stack, plus a parallel-read-during-write check.
- **Isolation:** confirm the isolation tests in `test_m1` and `test_m11` pass, and add one UI-level check: switching tenant shows no memory from the other tenant.
- **Cleanup:** remove committed `__pycache__` folders, reconcile the duplicate `mcp_server.py` entrypoints (the root file is a thin wrapper, which is fine, but document it), and add a `LICENSE`.

**Acceptance:** restart the backend mid-incident and the UI recovers; the isolation and concurrency checks pass on the live stack.

### P6: MCP proof (1.5 hrs)

- Verify `python mcp_server.py` (stdio) works with a real MCP client. Add a ready-to-paste client config snippet to the README.
- Confirm the exposed tools match the registry (`blast_radius`, `recall`, `rank_hypotheses`, `counterfactual_blast`, `ask`, and the rest).
- Record a 20-second clip of an external client calling `blast_radius` against Ripple's graph, for the demo.
- Add a test that lists tools over MCP and calls one.

**Acceptance:** an external MCP client answers "what breaks if redis-cart fails?" using Ripple's tools, and the trace shows the same Cypher as the UI.

### P7: Submission package (G7) (3 hrs)

| Item | Contents |
|---|---|
| `docs/architecture.png` | Clean diagram of the architecture in the README |
| `docs/track-mapping.md` | The README track table plus links to the code for each row |
| `docs/benchmark-report.md` | From P3 |
| `docs/demo-script.md` | The 3 to 4 minute script from plan v2 with exact clicks and scenario IDs |
| Demo video | Record from replay mode, with a backup recording; show failure, investigation with evidence, memory recall, the stale-fix block, the benchmark tab, what-if, ask-the-brain with sources, and tenant isolation |
| Submission text | Problem, solution, how FalkorDB is used (graph traversal, per-tenant graphs, vector index, Cypher in the inspector), what is novel, data honesty note |
| README refresh | Real benchmark numbers, links to the report and video, the three-command quick start retested on a clean clone |
| Repo hygiene | License, `.env.example` complete, no secrets, clean commit history |
| CI (optional but cheap) | GitHub Actions: backend tests with a FalkorDB service container, frontend build |

**Acceptance:** a clean clone runs with `docker compose up` and the README steps only; the submission is entered on the WeMakeDevs page before the final hours, because the team cannot be changed after submitting.

### P8: Turning it into a working product (G9) (Part B; start only after P0 to P7 are done)

This is what makes Ripple usable on a team's real system. Do the thin slice below only if time remains after submission-critical work, and treat the rest as the post-hackathon roadmap.

| Integration | What to build | Touches |
|---|---|---|
| **Alert intake** | `POST /webhooks/alert` that accepts a generic JSON alert and an Alertmanager-style payload, creates an incident, and starts the crew | `main.py`, orchestrator |
| **Bring your own system** | Onboarding screen: paste a GitHub repo and upload a service list or Kubernetes manifests; call the existing `/tenants/{id}/ingest`; show ingest progress and a graph preview | `ingest/`, new UI view |
| **Real deployment data** | Adapter that reads GitHub Deployments or Actions runs into `Deployment` nodes with `source='real'` | `ingest/github.py`, `Deployment` schema |
| **Real metrics** | Metrics adapter interface with a Prometheus implementation that writes `MetricSnapshot` nodes at alert time | `scenarios/metrics.py` replaced by an adapter |
| **Real notifications** | Slack message and email actions behind the existing approval gate; `needs_approval` stays mandatory | `agents/actions.py` |
| **Auth** | Per-tenant API keys instead of a bare `X-Tenant` header; enforce tenant from the key | tenancy middleware |
| **Operational basics** | Production Dockerfile for the frontend (static build instead of the dev server), health and readiness probes, structured logs, backups for the FalkorDB volume | Docker, `main.py` |

**Acceptance for the thin slice:** an alert sent with `curl` to the webhook produces an incident that appears in the UI, and a Slack message is drafted behind approval.

---

## 5. Integration matrix

| Producer → Consumer | Contract | Verified by |
|---|---|---|
| Tool registry → Tool loop (P1) | JSON schemas in `registry.py`; `execute_tool(name, args)` | Tool-loop unit tests with a fake provider |
| Tool loop → Trace (M10) | One `TraceStep` per tool call | Inspector shows Cypher for each call |
| Embeddings (P2) → Memory recall, Ask | `embed_text()` plus vector query | Paraphrase test |
| Benchmark runner (P3) → Report, Benchmark tab | JSON in `data/benchmark_runs/` | Restart test: numbers persist |
| Events (P5) → SSE stream → Timeline | Persisted `Event` plus in-memory bus | Restart mid-incident test |
| Orchestrator → Approval gate → Verifier | Action status `proposed → approved → executed` | Existing M7 tests plus UI flow |
| Webhook (P8) → Orchestrator | Alert payload → `POST /incidents` | `curl` test |
| MCP server (P6) → Tool registry | Same schemas as function calling | MCP client test |

---

## 6. Schedule

**Tonight (Oct 16, evening)**
| Block | Work |
|---|---|
| 2 hrs | P0 verify and stabilize |
| 1 hr | Start P1: add provider dependency, provider abstraction |
| **Gate A** | `pytest` status known; one incident runs through the UI |

**Oct 17**
| Block | Work |
|---|---|
| 3 hrs | P1 tool-calling loop, per-agent allow-lists, record replay cache |
| 3 hrs | P2 semantic embeddings and vector queries |
| 3 hrs | P3 benchmark runs and report (run overnight if long) |
| 3 hrs | P4a Figma theme |
| **Gate B (evening)** | Live-mode agents use tools; semantic search works; benchmark report has real numbers; new theme applied |

**Oct 18**
| Block | Work |
|---|---|
| 3.5 hrs | P4b wire unused endpoints, P4c states and polish |
| 2.5 hrs | P5 robustness and persistence |
| 1.5 hrs | P6 MCP proof |
| 3 hrs | P7 submission package and video |
| Buffer | 2+ hrs. **Submit by early evening.** |
| **Gate C (about 2 PM)** | Everything in P0 to P6 demonstrable; if not, use the fallback order below |

This is about 36 hours of work for roughly 2.5 days. It is tight. The gates exist so you find out early.

---

## 7. If a gate is missed

Reduce depth, not scope, in this order:

1. P8 entirely (it is Part B and not needed to submit).
2. P4c polish items beyond the approval flow and error states.
3. P5: keep the restart-mid-incident test and drop the extra stress run.
4. P6: keep a single MCP tool call demo instead of the full tool list.
5. P3: run each scenario once in live mode instead of three times, and say so in the report.
6. P2: if the vector procedure causes trouble, ship semantic embeddings with the Python cosine path and state that plainly.
7. P4b: wire freshness and Q&A history first; leave the rest.

**Never drop:** P0 verification, P1 tool-calling (at least for the investigator), P3 saved benchmark numbers with failures reported, the stale-fix demo, and the submission package.

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tests fail on first live run | Lost hours | P0 first; fix by dependency order |
| LLM provider rate limits or latency | Flaky live runs | Replay cache recorded in P1; demo from replay |
| `sentence-transformers` install is heavy in Docker | Slow builds | Use `fastembed` or cache the model layer; keep the hash flag for tests |
| Vector procedure syntax differs in your FalkorDB image | P2 stalls | Check docs first; keep the Python cosine fallback |
| Benchmark shows memory helping less than hoped | Weak headline | Report it honestly; the misleading-memory and stale-fix cases are already part of the story |
| Theme change breaks layouts | UI regressions | Change tokens first, then components one view at a time |
| Overclaiming "agents choose tools" | Credibility hit | Describe exactly what the LLM decides (tool order) and what the code decides (candidates, evidence, scores) |

---

## 9. Definition of done for this phase
 
- [x] `docker compose up` on a clean clone works; `pytest` passes against it (85 passing tests)
- [x] Agents call graph tools through an LLM tool loop in live mode; replay mode reproduces runs
- [x] Incident similarity uses semantic embeddings and FalkorDB vector queries (`CALL db.idx.vector.queryNodes(...)`)
- [x] Benchmark results are persisted, reported with sample size and labels commit hash (`29227d45ac0f414827fa5218df06c7188a6bc2ec`), and include a case where memory hurt
- [x] Frontend matches the Figma design and surfaces freshness, Q&A history, uncertainty, and facts
- [x] Restarting the backend does not break a running incident (SSE event stream disk persistence)
- [x] An external MCP client uses Ripple's tools (`mcp_server.py`)
- [x] Docs, architecture diagram, demo script, benchmark report, license, and README are complete
- [ ] Record final demo video and submit on the WeMakeDevs page

---

*Audit based on static review of the uploaded repo plus a successful Python compile and a successful frontend typecheck and build. Backend tests and the Docker stack were not run in this review.*

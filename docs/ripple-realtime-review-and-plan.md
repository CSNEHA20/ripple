# Ripple: Code Review, Real-vs-Mock Audit, and Real-Time Implementation Plan

**Review date:** Oct 17, 2026 · **Hackathon deadline:** Oct 18, 11:59 PM IST · **Repo reviewed:** `ripple-master (1).zip` (1,340 files; about 13.3k lines of backend, 8.0k lines of frontend, 3.2k lines of tests)

**Main motto:** *Ripple must work in real time.* Everything below is judged against that.

---

## 0. The short version

Ripple has a lot built, and the graph-reasoning core is real code. But **the product is not yet real-time, and several things the README and report present as real are simulated or synthetic.** The most important findings:

1. **The UI is not live.** The browser sends one blocking request, waits for the whole crew to finish, then *builds the timeline itself* from the response, with made-up timestamps. The backend has a streaming endpoint, but the frontend never uses it.
2. **The "real" GitHub data is generated.** Pull requests and issues come from templates in `ingest/github.py` (numbers 1101+ and 1000+, with real-looking URLs under `GoogleCloudPlatform/microservices-demo`). Those URLs do not match real PRs. Only the contributor list looks like real people.
3. **The LLM does not change any decision.** The new tool loop runs tools in live mode, but their results only go into the trace. Diagnosis, hypotheses, and runbook choice are computed by deterministic code. The LLM writes the summary.
4. **The benchmark does not show memory helping.** The saved report covers 5 scenarios (10 runs). Memory ON and OFF give identical diagnosis and recommendation scores, and one scenario is flagged unsafe in both modes. It also says "Calibration PASSED" on that tiny sample.
5. **Everything the system "observes" is seeded.** Metrics, deployments, incidents, and fix outcomes come from the scenario simulator. There is no real telemetry, no real action execution, and no notifications.
6. **A fake graph is shown when the API returns nothing.** `GraphCanvas.tsx` falls back to hard-coded nodes and edges, and `App.tsx` invents a random incident ID if one is missing.

None of this means the work is wasted. The schema, hypothesis engine, memory model, counterfactual engine, trace/inspector, tenancy, and API are solid foundations. The plan below connects them to live inputs, live outputs, and a UI that shows what is actually happening.

> **What I did and did not do.** I read the code (agents, tool loop, LLM wrapper, ingestion, scenarios, memory, API routes, frontend wiring, benchmark data and report). I compared it with the previous version you sent. I did **not** run the backend, the tests, or Docker. I did not call any live LLM. Where I say something "works", I mean the code path exists and reads as correct, not that I ran it.

---

## 1. What changed since the last version

| Area | Change |
|---|---|
| Agents | New `agents/tool_loop.py` (multi-turn tool calling, 6-step cap, allow-lists) used by triage, investigator, responder |
| LLM | `llm.py` now has OpenAI, NVIDIA, Anthropic, and Gemini providers behind one interface; `openai` added to requirements |
| Embeddings | `embed.py` now tries OpenAI embeddings first, then falls back to the hash vector |
| Memory / tools | `similar_incidents` now calls a FalkorDB vector query helper before re-ranking |
| Benchmark | Results are saved to `data/benchmark_runs/` (10 files) and a report is written to `docs/benchmark-report.md` |
| Events | Per-incident event logs are written to `data/events/*.jsonl` |
| Docs / repo | `LICENSE`, `docs/architecture.md`, `demo-script.md`, `track-mapping.md`, `benchmark-report.md` added |
| Frontend | New `SystemScene3D` (a 1,484-line three.js service map), `IncidentFlowPanel`, `IncidentHeader`, `TracePanel`, `RippleFooter`; `react-router-dom` and `three` added |

---

## 2. Feature inventory: present, partial, missing

**Present** means the code exists and appears complete. **Partial** means it exists but has a gap that matters. **Missing** means I found no implementation.

| # | Feature | Status | Notes |
|---|---|---|---|
| 1 | Per-tenant isolated graphs, tenant sanitizing | Present | `tenancy.py`; tenant comes from a bare header, no auth (see 29) |
| 2 | Temporal dependency edges (`valid_from`/`valid_to`) and as-of queries | Present | `temporal.py`, used by blast radius and counterfactual |
| 3 | Graph tool library (blast radius, upstream, paths, criticality, who-knows, changes, health, similar incidents, runbooks, applicability) | Present | `tools/`, schemas in `registry.py` |
| 4 | Hypothesis generation, evidence, scoring, sufficiency rule | Present | `hypotheses/`; evidence inputs are seeded (see section 3) |
| 5 | Supporting vs contradicting evidence, observed vs inferred labels | Present | |
| 6 | Episodic, semantic, procedural, outcome memory; applicability check; decay | Present | `memory/` |
| 7 | Predicted vs observed outcome stored separately | Present | |
| 8 | Four agents with blackboard coordination (tasks, handoffs, conflicts, evidence requests) | Present | `agents/blackboard.py`, `conflicts.py` |
| 9 | Safe-action classes with approval gate | Present | `actions.py`; "execution" only changes graph state (see 27) |
| 10 | Counterfactual engine with as-of toggle and uncertainty | Present | `counterfactual/` |
| 11 | Company-brain Q&A with citations, freshness, history | Present | `brain/ask.py` |
| 12 | Provenance trace and Cypher inspector | Present | `trace.py`, `/inspect/*` |
| 13 | MCP server over the tool library | Present | Not demonstrated against a real MCP client |
| 14 | Alert webhook (generic JSON and Alertmanager payload) | Partial | `main.py:192`; no auth, no dedupe, no grouping, runs the whole crew inside the request |
| 15 | Streaming endpoint (`/incidents/{id}/stream`) | Partial | Exists in the backend; the frontend never connects to it |
| 16 | Event persistence (`data/events/*.jsonl`) | Partial | Written, but no resume or `Last-Event-ID` support seen in the UI |
| 17 | LLM tool-calling loop | Partial | Runs in live mode but results do not affect decisions |
| 18 | Multi-provider LLM | Partial | Providers exist; the webhook only goes "live" if an OpenAI key is set; failures fall back silently |
| 19 | Semantic embeddings | Partial | OpenAI embeddings only, then silent fall back to hash; no local model |
| 20 | FalkorDB vector queries | Partial | Code path exists; needs verification against a live FalkorDB |
| 21 | Memory on/off benchmark with saved runs and report | Partial | Only 5 scenarios, memory shows no benefit, small-sample calibration claim |
| 22 | Frontend views (Incident, Memory, What-if, Benchmark, Ask, Inspector, Scenario drawer) | Partial | Built, but driven by one blocking response, with fake fallbacks |
| 23 | 3D service-map scene | Partial | Built; not tied to live events; performance and fallback need work |
| 24 | Real GitHub ingestion | **Missing** | Ingestion reads a local cache or generates synthetic PRs/issues; the `github_token` setting is never used to call GitHub |
| 25 | Live metrics (Prometheus or similar) | **Missing** | `MetricSnapshot` is created only by the scenario simulator |
| 26 | Real deployment events | **Missing** | Deployments are seeded |
| 27 | Real action execution (rollback, restart, scale) | **Missing** | No integration; "executed" is a graph status |
| 28 | Notifications (Slack, email, PagerDuty) | **Missing** | No code found |
| 29 | Authentication, per-tenant API keys, webhook signing | **Missing** | Tenant is trusted from a header; webhook is open |
| 30 | Topology discovery from live sources | **Missing** | Dependencies are hand-encoded |
| 31 | Background job execution with queue/retry | **Missing** | The crew runs inside the HTTP request |
| 32 | Production frontend build | **Missing** | Docker runs the Vite dev server |
| 33 | CI pipeline and end-to-end browser tests | **Missing** | |
| 34 | Onboarding flow for a team's own system | **Missing** | `/tenants/{id}/ingest` only re-runs the bundled bootstrap |

---

## 3. Real vs demo audit: what actually works in real time

Four categories:

- **A. Real and live:** works on real inputs as they arrive.
- **B. Real logic, simulated input:** the code is genuine, but what it reasons over is seeded.
- **C. Mock or synthetic:** shown to the user as real but generated.
- **D. Cosmetic:** looks live but is not driven by live data.

| Feature | Category | Evidence | What makes it real |
|---|---|---|---|
| Graph traversal, blast radius, path queries over FalkorDB | **A** | Cypher executed at request time | Already real for whatever is in the graph; the graph contents are the issue |
| Hypothesis scoring and ranking | **B** | Scores computed from graph evidence in code | Feed it real metrics, deployments, topology (R4, R5) |
| Evidence: metrics, deployments, architecture changes | **C** | Created by `scenarios/metrics.py` and `scenarios/engine.py` | Replace with adapters (R4) |
| Historical incidents and fix outcomes | **C** | Seeded; verifier uses scripted `apply_intervention` | Verify outcomes from post-fix metrics (R6) |
| Pull requests, issues, commits | **C** | Templates in `ingest/github.py`; PR 1101+, issue 1000+ | Real GitHub sync (R5) |
| Contributor list and ownership | **B/C** | Logins look real; counts are generated | Real commit history (R5) |
| Service dependency graph | **B** | Hand-encoded from the sample app | Discover from manifests or traces (R4) |
| Alert intake | **B** | Webhook parses Alertmanager JSON correctly, but it is open and runs the crew synchronously | Harden and make asynchronous (R2, R8) |
| Agent summaries (LLM) | **B** | One structured call; deterministic fallback; no effect on decisions | Make the loop decision-bearing (R3) |
| LLM tool calling | **B/D** | Tools run in live mode, results only recorded in trace | R3 |
| Agent timeline in the UI | **D** | `App.tsx` builds events from the response with `Date.now()/1000 - 4` style timestamps | Stream real events (R2) |
| Incident ID in the UI | **D** | Falls back to `INC-<random>` | Use server ID only (R1) |
| Graph canvas | **C when empty** | `FALLBACK_NODES/EDGES/BLAST` shown if API returns nothing | Remove fallback, show empty state (R1) |
| Elapsed timer | **D** | Client clock only | Show server timestamps (R2) |
| Trace replay | **A** | Steps come from the real trace; replay speed is a fixed 1.2 s | Fine, label as replay |
| Approval gate | **A (state), B (effect)** | Approve/reject change the action status in the graph | Wire to real executors (R6) |
| Memory recall | **B** | Works on seeded history | Needs real incidents accumulating |
| Counterfactual engine | **A** | Pure graph computation | Real once topology is real |
| Company-brain Q&A | **B** | Retrieves from graph; sources are synthetic PRs/issues | R5 |
| Semantic similarity | **B** | OpenAI embeddings if a key exists, else hash | R7 |
| Benchmark | **B** | Runs the deterministic pipeline in about 0.3 s per scenario | Run with live LLM, more scenarios (R7) |
| Tenant isolation | **A** | Separate graphs | Add auth (R8) |
| MCP server | **B** | Same tool functions | Prove with a real client (R9) |

**Bottom line:** the reasoning engine is real; its *inputs* (telemetry, history, outcomes, code activity) and the UI's *live feel* are simulated or synthetic. Real-time means closing exactly those gaps.

---

## 4. Integrity corrections to make before claiming anything

These should be fixed first, because judges and users will test them.

| ID | Issue | Fix |
|---|---|---|
| I1 | README and docs say services, people, and PRs are real. PRs and issues are generated templates with URLs that point to PR/issue numbers that are not those items. | Either implement real sync (R5), or relabel as "synthetic dataset modelled on the sample repo" and remove the GitHub links from synthetic items. |
| I2 | `docs/benchmark-report.md` shows 5 scenarios; the plan promised 12. Memory ON equals OFF on every score, but the report is framed around memory benefit. | State plainly that memory showed no measurable benefit in this run. Re-run with more scenarios (R7). |
| I3 | Report says "Calibration check: PASSED" on 10 runs. | Remove or downgrade; a rank correlation on that sample is not evidence. |
| I4 | Report row says the applicability filter blocks stale traps, but the stale-trap scenario shows recommendation FAIL in both modes, and the misleading-memory scenario is marked UNSAFE in both. | Check the labels and what "FAIL" means (abstain vs wrong), then explain or fix. |
| I5 | Benchmark durations of about 0.3 s per scenario show no live LLM call was involved. Report presents average tool calls (37) as agent behavior. | Say which parts are deterministic. |
| I6 | Webhook picks live mode only when an OpenAI key exists (`main.py:225`), even if Anthropic, Gemini, or NVIDIA keys are set. | Use the configured provider (R3). |
| I7 | LLM failures fall back silently to deterministic output. | Show a visible "degraded: no LLM" state in the UI and logs (R3). |
| I8 | `main.py` builds some Cypher with f-strings around IDs (e.g. the re-embed route). | Use parameters. |

---

## 5. What "working in real time" requires

A real-time Ripple needs four live loops. Today none is complete.

```
 LIVE INPUT                      LIVE REASONING                  LIVE OUTPUT              LIVE FEEDBACK
 alerts (webhook)   ──►  queue ──► agents (async, streamed) ──► UI stream + Slack/page ──► outcome from metrics
 metrics (Prometheus)           ▲   graph reads/writes                 approvals                │
 deploys (GitHub/K8s)           │                                                               ▼
 topology (manifests/traces)    └──────────── memory updated from observed outcome ─────────────┘
```

| Loop | What must be true | Status |
|---|---|---|
| **Input** | Alerts arrive by webhook; metrics, deployments, and topology are pulled from real systems into the graph | Webhook partial; the rest missing |
| **Reasoning** | The crew runs in the background, emits events as it works, and the LLM's tool use can change the outcome | Runs synchronously; LLM cosmetic |
| **Output** | The UI shows events within about a second; approved actions really execute; people are notified | UI not streaming; no executors or notifications |
| **Feedback** | After an action, real metrics decide if it worked, and memory updates from that | Scripted outcomes |

**Acceptance bar for "real time":**
1. Send an Alertmanager payload with `curl`. The incident appears in the UI within 2 seconds, and each agent step shows up as it happens (not after the run).
2. Kill the backend mid-incident and restart it. The UI reconnects and resumes from the stored events.
3. Approve an action. A Slack message is sent (test workspace), the action executes against a real or sandbox target, and post-fix metrics are polled.
4. The outcome is recorded from those metrics, and a similar incident later is handled differently because of it.

---

## 6. Implementation plan

Order matters: each step depends on the one before. Time estimates assume heavy AI-assisted coding.

### R1: Truthful baseline (2 hrs, do first)

**Goal:** nothing on screen or in docs claims more than is true.

- **UI fakes:** in `App.tsx`, delete the `INC-<random>` fallback (show an error instead). In `GraphCanvas.tsx`, delete `FALLBACK_NODES`, `FALLBACK_EDGES`, `FALLBACK_BLAST` and render an empty state with "No graph data yet".
- **Data labels:** add `source: 'real' | 'seeded' | 'synthetic'` to nodes and show a small "seeded" tag in the inspector and evidence rows (the plan already called for this; confirm it is implemented end to end).
- **Docs:** fix I1 to I5 in `README.md`, `docs/benchmark-report.md`, `docs/track-mapping.md`.
- **Degraded-mode banner:** surface when the LLM provider is missing or a call failed (I7).

**Acceptance:** no hard-coded graph or incident data remains in the frontend; README and report statements match the code.

### R2: Asynchronous execution and live streaming (6 hrs, the core of "real time")

**Backend**
- `POST /incidents` and `POST /webhooks/alert` return **202** with `incident_id` immediately and run the crew in a background worker (start with FastAPI `BackgroundTasks` or an `asyncio` task; move to a queue such as RQ or Arq if time allows).
- The orchestrator publishes an event at every real step (`incident_opened`, `agent_started`, `tool_called`, `observation_created`, `hypotheses_ranked`, `conflict_flagged`, `approval_needed`, `outcome_verified`, `incident_closed`). Most already exist in the event names; make sure each is emitted when it happens and carries a real timestamp and sequence number.
- Persist every event (already writing JSONL) and make `/incidents/{id}/stream` support `Last-Event-ID` so clients can resume.
- Accept `?tenant=` on the stream route because `EventSource` cannot send headers.
- Move run state (`running`, `awaiting_approval`, `closed`, `failed`) into the graph so a restart does not lose it.

**Frontend**
- Replace the "await the whole response" flow in `App.tsx` with: start incident, open `EventSource`, feed events into a reducer that updates the timeline, hypothesis board, graph highlights, and phase indicator as they arrive.
- Reconnect with backoff; on reconnect, resume from the last event ID.
- Drop the synthesized events and fake timestamps.

**Acceptance:** acceptance items 1 and 2 in section 5 pass. Timeline entries show server timestamps and appear one by one during a run.

### R3: Make the LLM decision-bearing (4 hrs)

**Goal:** the LLM chooses tools and its findings change the investigation, while evidence and scoring stay code-driven.

- **Merge tool results into the investigation.** When the loop calls `service_health`, `recent_changes`, or `path_between`, convert each result into an `Evidence` node (observed) attached to the relevant hypothesis, then re-run scoring. Today results only enter the trace.
- **Let the LLM request more evidence.** Allow a structured action "request_evidence(hypothesis_id, type)" that creates the existing `evidence_request` task; the investigator fulfils it with a tool call and re-ranks.
- **Provider selection:** one `LLM_PROVIDER` setting controls every code path (webhook, incidents, ask). Remove the OpenAI-key check at `main.py:225`. Update default model IDs to current ones via env vars.
- **No silent fallback:** if the provider fails, mark the run `degraded`, continue deterministically, and tell the UI (I7).
- **Guardrails to keep:** the LLM cannot invent hypotheses outside the code-generated set; cited IDs must exist; tool allow-lists per agent; max steps and a timeout per call.
- **Record and replay:** keep the replay cache for demos, but record from real live runs.

**Acceptance:** in live mode, two different alerts lead to different tool sequences, and at least one run's top hypothesis or evidence list differs because of an LLM-chosen tool call. The trace shows the Cypher for each.

### R4: Live telemetry and topology adapters (8 hrs)

**Goal:** the graph reflects reality, not scenarios.

- **Adapter interface** (`adapters/base.py`): `fetch_metrics(service, window)`, `fetch_deployments(service, window)`, `fetch_topology()`, each returning typed records tagged `source='real'`.
- **Prometheus adapter:** on alert intake, run `query_range` for latency p95 and error rate for the alerting service and its upstream suspects, and write `MetricSnapshot` nodes. Keep the scenario simulator as a separate adapter selectable per tenant (`SOURCE=simulator|prometheus`).
- **Deployment adapter:** read GitHub Deployments or Actions runs (and optionally Kubernetes rollout history) into `Deployment` nodes with real timestamps and versions.
- **Topology discovery:** parse Kubernetes manifests or Docker Compose `*_ADDR` environment variables; optionally accept OpenTelemetry trace edges. Write `DEPENDS_ON` edges with `source` and `verified=true` only when observed in manifests or traces.
- **Webhook hardening:** shared-secret or HMAC verification, dedupe by Alertmanager `fingerprint`, group alerts into one incident within a time window, map `service` labels to graph services with a clear "unmapped service" response.
- **Live demo target (so you can show this without a cluster):** a small service that exposes Prometheus-format metrics for the demo services and has a "break this service" switch. Honest framing: real telemetry pipeline, simulated target.

**Acceptance:** break a service in the demo target, an alert fires, Ripple pulls the metrics itself, and the hypothesis evidence cites those metrics with real timestamps.

### R5: Real GitHub ingestion (5 hrs)

- Use `github_token` to call the GitHub API for contributors, commits per path, PRs, issues, releases/deployments, and `CODEOWNERS`. Handle pagination, ETags, and rate limits; cache raw responses.
- Replace the template generators in `ingest/github.py` with real fetchers. Keep the synthetic generator behind `DEMO_DATA=true` and label every node it makes `source='synthetic'`.
- Incremental sync endpoint and a scheduled refresh; a "last synced" indicator in the UI.
- Map file paths to services with a configurable path-to-service table instead of hard-coded `src/<service>/`.
- Re-extract decisions from real PR descriptions and issue threads, then human-review.

**Acceptance:** every PR/issue link in the UI opens the real item; ownership numbers match `git shortlog` for a service path.

### R6: Real actions, notifications, and verified outcomes (6 hrs)

- **Executors** (`actions/executors/`): start with two that can be demonstrated safely: a Slack message (test workspace) and a GitHub Actions `workflow_dispatch` that runs a rollback workflow in a sandbox repo. Optional: Kubernetes `kubectl rollout undo` against a local kind cluster.
- **Approval stays mandatory** for `needs_approval` actions; add an audit record (who approved, when, payload hash) and idempotency keys so a retry does not run the action twice. Add a dry-run mode.
- **Notifications:** Slack and email for incident opened, approval needed, incident closed. Page an on-call person through a webhook-based provider as a stretch.
- **Verification from reality:** after execution, the verifier polls post-fix metrics (via the R4 adapter) for a configurable window, then records `Outcome` as resolved, partial, or failed from those numbers. Keep the scripted simulator only for the simulator adapter.
- **Memory from real outcomes:** runbook success and failure counts update only from these observed results.

**Acceptance:** acceptance item 3 and 4 in section 5.

### R7: Make memory demonstrably useful, and benchmark honestly (5 hrs)

- **Find out why memory shows no effect.** In the saved runs, memory ON and OFF give identical scores. Check whether memory-off truly disables recall, whether the seeded history is reached by the vector query, and whether the scenarios are designed so memory can help (the repeated and variant families should).
- **Embeddings:** add a local embedding option (for example `fastembed` or `sentence-transformers`) so semantic search works without an API key; keep OpenAI as an option; log which backend is active; fail loudly rather than silently falling back to hash.
- **Verify the FalkorDB vector query** on a live instance, with a paraphrase test (hash backend misses it, semantic finds it).
- **Benchmark:** 12 or more scenarios in the five families, 3 repeats each in live mode, memory ON and OFF, saved with the labels commit hash. Report per-family results, variance, and every case where memory hurt. Drop the calibration claim unless there are enough samples to support it.
- **Fix the misleading-memory scenario** that shows as unsafe in both modes, or explain it in the report.

**Acceptance:** the report shows at least one family where memory helps with a stated margin, or states honestly that it did not, with the analysis of why.

### R8: Security and multi-tenancy (4 hrs)

- Per-tenant API keys (hashed in the graph or a small table); tenant derived from the key, never from a header. Separate keys for the webhook (signed) and the UI/API.
- CORS locked to known origins, request size limits, basic rate limiting, input validation on all routes, and parameterized Cypher everywhere (I8).
- Secrets only from environment; confirm nothing sensitive is in `.env.example`, logs, or traces. (I found no committed keys in this zip.)
- Role split: viewer, responder (can approve), admin. Audit log screen.

**Acceptance:** a request with tenant A's key cannot read or approve anything in tenant B; unsigned webhook calls are rejected.

### R9: Reliability, testing, and operations (5 hrs)

- **Production frontend:** multi-stage Dockerfile that builds the Vite app and serves static files (nginx or the backend), instead of `npm run dev`.
- **Run the tests against a live FalkorDB** in CI (GitHub Actions service container), plus a frontend typecheck and build.
- **End-to-end test** (Playwright): webhook in, stream events seen in the UI, approve, outcome recorded.
- **Load test:** a few dozen concurrent incidents across two tenants; check for duplicate nodes and lost writes.
- **Observability:** structured logs with incident and tenant IDs, a `/metrics` endpoint for Ripple's own health, and readiness probes.
- **MCP proof:** connect a real MCP client and record the demo; add a test that lists and calls a tool.
- **Backups:** FalkorDB volume snapshot instructions.

**Acceptance:** CI is green on a clean clone; the end-to-end test passes; the stack restarts cleanly mid-incident.

### R10: Premium SaaS interface (see section 7)

### R11: Onboarding for a team's own system (5 hrs, after R4 to R6)

- A guided flow: connect GitHub (token or app), choose repo and path-to-service mapping, add an alert source (copyable webhook URL and secret), add Prometheus URL, connect Slack, then run a test alert.
- Show ingestion progress, a graph preview, and a checklist of what is connected, with "seeded" data clearly marked until real sources are connected.

**Acceptance:** a new tenant goes from empty to a real alert handled end to end in under 15 minutes without editing code.

---

## 7. Making the UI a premium SaaS application

### 7.1 Where the UI stands

- Strengths: a complete set of views and drawers, a design token file, shadcn and Tailwind in place, Geist font, a 3D service scene, a trace panel.
- Gaps: cream background with a red-orange sidebar (different from the green Figma design), a blocking request flow, hard-coded fallbacks, only 39 `aria-` attributes in components and 2 `prefers-reduced-motion` rules, the 1,484-line 3D component and large bundle loaded up front, no login, no settings, no onboarding, no notification center, no empty/loading/error system.

### 7.2 Design direction

Pick one direction and apply it everywhere. Recommendation: **the forest-green, mint, and cream system from your Figma file**, because it is distinctive and already designed.

- **Tokens:** forest `#12281B`, `#1C3A2A`, `#0B1810`; mint `#D9F0B9`; cream `#EBE3D0`; text `#EEF3E6`; muted `#9DB39F`; good `#43D675`; warn `#F0B35A`; bad `#E8745F`. Add a light theme variant for printed postmortems.
- **Type:** Geist (already installed) for UI, a mono face for IDs, Cypher, and timestamps; tight headlines, restrained weights, a clear type scale.
- **Components:** build on shadcn primitives; one button, input, tab, table, dialog, toast, badge, and card style used everywhere; consistent 4/8 px spacing and radii.
- **Motion:** purposeful only (stream entries sliding in, graph highlights); respect `prefers-reduced-motion`; no motion on data updates that would distract during an incident.

### 7.3 Information architecture

| Area | Purpose |
|---|---|
| **Overview** | Open incidents, recent outcomes, system health, integrations status |
| **Incident war room** | The live view: streaming timeline, hypothesis board with evidence, graph, memory recall, approval card, notes. This is the hero screen |
| **Services** | Graph explorer with ownership, health, recent changes, as-of slider |
| **Memory** | Past incidents, runbooks with success rates, "why not recommended", facts and superseded facts |
| **What if** | Counterfactual comparison with uncertainty |
| **Benchmark** | Results with sample size and method, honest failure cases |
| **Ask** | Company-brain chat with sources, history, freshness warnings |
| **Integrations** | GitHub, alert sources, Prometheus, Slack, API keys, webhook URL and test button |
| **Settings** | Workspace, members and roles, audit log, notification rules |

Global: workspace/tenant switcher, command palette (Cmd/Ctrl+K), notification center, status pill showing backend, FalkorDB, LLM provider, and data-source health.

### 7.4 The incident war room (highest-impact screen)

- A header with severity, service, elapsed server time, current phase, and live connection state.
- A **streaming timeline** where each event appears as it happens, with agent, tool, and a link to the Cypher in the inspector.
- A **hypothesis board** that re-ranks live as evidence arrives, with supporting and contradicting evidence, observed and inferred labels, source tags (real, seeded), and the insufficient-evidence state.
- A **graph** (2D by default) that highlights the path the agent is currently exploring; the 3D system view as an optional mode.
- A **memory panel** with "why not recommended."
- An **approval card** with payload preview, dry-run result, and approve/reject; after approval, a live "verifying fix" progress state driven by post-fix metrics.
- A **postmortem export** (Markdown or PDF) generated from the trace and outcome.

### 7.5 Polish and quality bar

- **States:** skeletons while loading, meaningful empty states with a next action, plain-language errors with retry, offline/reconnecting banner.
- **Accessibility:** keyboard navigation for every control, visible focus, labelled controls, color contrast checks, `aria-live` for streaming events, reduced-motion support. Target WCAG AA.
- **Performance:** lazy-load the 3D scene and heavy views, split the bundle, cap pixel ratio on the 3D canvas, pause rendering when hidden, a 2D fallback when WebGL is unavailable, Lighthouse performance above 85.
- **Responsive:** usable on a laptop and a tablet; mobile shows the war room in a single column with the approval card pinned.
- **Trust cues:** every number links to its source; seeded and synthetic data are always tagged; last-synced times on integrations.
- **Account basics:** login, workspace switcher, roles, and an audit log page (R8).
- **Crew visualization:** the existing 3D service map already communicates "what is happening"; a second option is a pipeline view of the five stages (alert, triage, investigate, respond, verify) with packets moving between them as events stream in, driven by real events.

### 7.6 UI work breakdown

| Step | Work | Effort |
|---|---|---|
| U1 | Apply token set and Figma theme, remove the red-orange sidebar | 3 hrs |
| U2 | New app shell: top nav, workspace switcher, command palette, notification center, status pill | 4 hrs |
| U3 | War room rebuild on the event stream (depends on R2) | 6 hrs |
| U4 | State system: skeletons, empty, error, reconnect | 2 hrs |
| U5 | Accessibility and reduced-motion pass | 2 hrs |
| U6 | Performance: lazy loading, bundle split, 3D guard and fallback | 2 hrs |
| U7 | Integrations and onboarding screens (depends on R4 to R6, R11) | 5 hrs |
| U8 | Settings, roles, audit log, postmortem export | 4 hrs |

---

## 8. Schedule against the deadline

There are roughly 36 hours left. The full plan is larger than that, so it is split into a hackathon cut and a product roadmap. The hackathon cut is built around the motto: a live path that can be shown end to end.

### Hackathon cut (must be done before submitting)

| Order | Work | Hours | Gate |
|---|---|---|---|
| 1 | R1 truthful baseline | 2 | No fakes in UI; docs corrected |
| 2 | R2 async run and live stream, with the UI wired to it | 6 | `curl` webhook, events appear live in UI; resume after backend restart |
| 3 | R3 LLM results feed evidence; provider fix; degraded banner | 4 | Live mode run differs by alert and shows tool-driven evidence |
| 4 | R4 Prometheus adapter plus the live demo target, webhook secret and dedupe | 6 | Break a service, alert fires, real metrics become evidence |
| 5 | R6 minimum: Slack message plus verification by post-fix metrics | 4 | Approve, notify, verify, record outcome |
| 6 | R7 honest benchmark re-run and report fix | 3 | Report matches the data, memory result stated honestly |
| 7 | U1 to U4, U6 (theme, shell, war room, states, performance) | 12 | Matches the Figma look; war room streams |
| 8 | Submission package: demo video, README, architecture | 3 | Submitted early on Oct 18 |

That totals about 40 hours. If time is short, reduce depth in this order: U7/U8 first, then the Slack executor (keep metrics verification), then extra benchmark repeats. Do not drop R1, R2, the Prometheus path, or the honest report.

### Product roadmap (after the hackathon)

R5 real GitHub ingestion, remaining R6 executors, R8 security, R9 CI and end-to-end tests, R11 onboarding, U7 and U8.

---

## 9. Definition of done for "real-time working"

- [ ] A signed alert webhook creates an incident and returns immediately
- [ ] The UI shows each agent step within about a second, with server timestamps, and resumes after a reconnect or backend restart
- [ ] Evidence for hypotheses comes from live metrics and deployment data, tagged real
- [ ] In live mode, an LLM-chosen tool call changes the evidence or ranking
- [ ] An approved action executes or notifies for real, and the outcome comes from post-fix metrics
- [ ] A later similar incident is handled differently because of that recorded outcome
- [ ] No hard-coded graph, incident ID, or synthesized timeline remains in the frontend
- [ ] Every README and report claim about data and results matches what the code does
- [ ] The UI matches the chosen design system and passes basic accessibility and performance checks

---

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Async refactor breaks existing tests | Lost hours | Keep the synchronous path behind a flag; update tests per route |
| No real telemetry source available at demo time | R4 stalls | Build the live demo target first; it exercises the full pipeline honestly |
| LLM latency makes live runs slow | Flat demo | Stream events as they happen; keep a recorded replay as backup, labelled as replay |
| Slack or GitHub credentials issues | R6 stalls | Use a throwaway workspace and sandbox repo; dry-run mode as fallback |
| Memory still shows no benefit | Weak story | Report it honestly; lean on the stale-fix block and unsafe-recommendation avoidance as the value |
| Scope too large | Unfinished | Follow the gates in section 8; reduce depth in the stated order |
| Over-claiming | Credibility | Fix I1 to I8 first; label seeded and synthetic data everywhere |

---

*This review is based on reading the uploaded code and its saved benchmark data. The backend, tests, and Docker stack were not run, and no live LLM calls were made.*

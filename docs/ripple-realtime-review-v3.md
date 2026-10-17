# Ripple: Code Review v3, Real-vs-Mock Audit, and Plan to Finish Real-Time

**Review date:** Oct 17, 2026 · **Hackathon deadline:** Oct 18, 11:59 PM IST · **Repo reviewed:** `ripple-master (2).zip` (1,370 files; about 14.8k lines of backend, 8.1k lines of frontend, 3.3k lines of tests)

**Main motto:** *Ripple must work in real time.*

> **How I reviewed.** I read the code: the new modules (`security.py`, `adapters/`, `actions/executors/`, `notifications/`), the changed files (`main.py`, `orchestrator.py`, `investigator.py`, `verifier.py`, `ingest/github.py`, `config.py`, `App.tsx`, `api.ts`, `GraphCanvas.tsx`), the new tests, and the README and benchmark report. I compared everything with the previous version. I did **not** run the backend, tests, Docker, or any live LLM or Slack call. "Works" below means the code path exists and reads as correct.

---

## 0. The short version

This version closes real gaps from the last review. **The streaming path is now genuinely built, the UI fakes are gone, and the README and benchmark report are honest.** There are also real executors, webhook signing, deduplication, a Prometheus adapter, and tool results that now change the evidence.

But the loop is **not closed yet**. Most of the new pieces exist next to the main flow instead of inside it:

1. **Live metrics only reach the verifier.** Prometheus is queried after a fix, but the investigation still reasons over seeded metrics. `DeploymentAdapter` is never called anywhere.
2. **Rollback does not heal the demo target.** Approving a rollback runs the sandbox executor, which only records an idempotency key. The broken demo service stays broken until someone calls `/demo/restore`, so verification reads "failed".
3. **Authentication is not enforced.** `authenticate_api_key` exists, but no route uses it. Tenant and role still come from a header the caller controls.
4. **Some data is mislabeled "real".** The Prometheus adapter falls back to the in-process demo target and tags those records `source="real"`. Tool-derived evidence is also tagged `real` regardless of origin.
5. **Real GitHub sync produces wrong data.** Every PR is assigned to the `frontend` service, and every `merged_at` is set to the current time, which corrupts "recent deploy" evidence.
6. **The GitHub rollback executor defaults to Google's sample repo** (`GoogleCloudPlatform/microservices-demo`, workflow `rollback.yml`, ref `main`). With a token set, it would try to dispatch there.
7. **Topology discovery reads Ripple's own `docker-compose.yml`,** so it finds Ripple's own services (backend, FalkorDB), not the monitored system.
8. **Memory is still unproven.** The honest benchmark report shows memory ON and OFF identical on 5 scenarios, with recommendation correctness at 40%.

The good news: most of the remaining work is **wiring and hardening**, not new architecture.

---

## 1. What changed since the last version

| Area | Change | Verdict |
|---|---|---|
| Async execution | Webhook returns **202** and runs the crew with `BackgroundTasks` | Done |
| Streaming | `/incidents/{id}/stream` supports `Last-Event-ID` (header and query); frontend uses `EventSource`, subscribes with `?tenant=`, listens to 13 event types | Done |
| UI fakes | `FALLBACK_NODES/EDGES/BLAST`, random incident ID, synthesized timeline removed | Done |
| Tool results to evidence | Investigator converts `service_health` and `recent_changes` tool results into evidence and re-scores | Partly done (two tools only) |
| Webhook security | HMAC check (`X-Ripple-Signature`), alert dedupe by fingerprint (5-minute window) | Done, with caveats (section 3) |
| Telemetry adapters | `PrometheusAdapter`, `DeploymentAdapter`, topology discovery, in-process demo target with break and restore routes | Partly wired |
| Executors | Slack webhook, GitHub `workflow_dispatch`, sandbox; dry-run and audit hash | Partly done |
| Notifications | Slack messages on incident opened, approval needed, incident closed | Done (needs a webhook URL) |
| Verifier | Reads post-fix metrics from the adapter when Prometheus is configured or the demo target is broken | Partly done |
| GitHub ingestion | Real REST fetch added | Has serious defects (section 3) |
| Honesty | README has a "Real vs Synthetic vs Seeded" section; benchmark report no longer claims calibration | Done |
| Tests | `test_realtime.py` (5 tests: HMAC, dedupe, event-bus resume, demo-target faults, sandbox idempotency) | Good unit coverage, no end-to-end |
| Not changed | `index.css` (theme), `docker-compose.yml`, frontend `Dockerfile` (still the dev server), no CI | Open |

---

## 2. Status of the previous review's findings

| ID | Finding | Status now |
|---|---|---|
| I1 | README claimed real GitHub data | **Fixed** (honest labelling section). Real fetch exists but is defective (N5) |
| I2/I3 | Benchmark overclaimed, calibration "PASSED" on tiny sample | **Fixed** (report says insufficient sample) |
| I5 | Benchmark durations imply no live LLM | **Fixed** (report states the pipeline is deterministic) |
| I6 | Webhook went live only with an OpenAI key | Partly fixed (`llm_provider` setting added; verify it is used on every route, including approve) |
| I7 | Silent LLM fallback | Partly fixed (a `degraded` marker exists in several modules; verify it reaches the UI) |
| I8 | f-string Cypher in re-embed route | Not checked again |
| R1 | Remove UI fakes | **Done** |
| R2 | Async execution and live streaming | **Done** (verify end to end) |
| R3 | LLM results change decisions | Partly done |
| R4 | Live telemetry adapters | **Partly done** (verifier only) |
| R5 | Real GitHub ingestion | Partly done, defective |
| R6 | Real actions and verified outcomes | Partly done |
| R7 | Memory useful, honest benchmark | **Not done** (still 5 scenarios, no memory effect) |
| R8 | Security and tenancy | **Barely started** (functions exist, not enforced) |
| R9 | CI, E2E tests, production Docker | Not done |
| R10/R11 | Premium UI and onboarding | Not done |

---

## 3. New findings in the new code

Ordered by how much they hurt the real-time claim.

| ID | Finding | Where | Impact | Fix |
|---|---|---|---|---|
| **N1** | **Authentication is not enforced.** `authenticate_api_key` is defined but no route depends on it. `get_current_tenant` and `TenantMiddleware` trust `X-Tenant` or `?tenant=`. The key parser accepts any string shaped like `key_<tenant>_<role>_<secret>` without checking a store, and the default role is `admin`. | `security.py`, `main.py:54-88` | Any caller can read, approve, and act on any tenant | S3 |
| **N2** | **Simulated data labelled `source="real"`.** When Prometheus is unreachable, `PrometheusAdapter.fetch_metrics` returns the in-process demo target's numbers tagged `real`. `check_health` falls back to a hard-coded 22 ms / 0% baseline. Tool-derived evidence in the investigator is also tagged `real`. | `adapters/prometheus.py`, `agents/investigator.py:226,252` | Judges and users cannot trust the badges | S1 |
| **N3** | **Live metrics are not used for the investigation.** `PrometheusAdapter` is used only in `verifier.py`. `DeploymentAdapter` is referenced nowhere. `telemetry_source` defaults to `simulator`. Triage and evidence generation still read seeded `MetricSnapshot` nodes. | `agents/*`, `hypotheses/evidence.py` | The core promise (reason over what is happening now) is not met | S1 |
| **N4** | **Rollback does not change the demo target.** The sandbox executor adds a key to an in-memory set and returns a receipt. Nothing calls `restore_service`; only the manual `/api/telemetry/demo/restore` route does. | `actions/executors/sandbox.py`, `main.py:1570` | Verification will read "failed" for a correct fix unless you restore by hand | S2 |
| **N5** | **Real GitHub fetch is wrong.** Every PR gets `service: "frontend"` and `merged_at: time.time()`. Contributors cap at 30, PRs at 40, issues at 40, with no pagination. No CODEOWNERS, no file-to-service mapping, no deployments. If the call fails it falls back to the cache or synthetic data without saying so. | `ingest/github.py` | Evidence timing and ownership are wrong | S6 |
| **N6** | **GitHub rollback executor has a dangerous default.** Repo defaults to `GoogleCloudPlatform/microservices-demo`, workflow is hard-coded `rollback.yml`, ref `main`. | `executors/github_dispatch.py`, `config.py` | A token in the environment would target a repo you do not own | S5 |
| **N7** | **Idempotency is partial and in memory.** Only the sandbox executor checks `_EXECUTED_KEYS` (lost on restart). Slack and GitHub executors compute a key but I found no duplicate check. | `executors/*` | A retry could send a duplicate message or dispatch twice | S5 |
| **N8** | **Verification is a single instant query.** No polling window or baseline comparison. The success message is hard-coded ("normalized... 0% errors"). `ref_ts` and `window_minutes` are accepted but unused in the queries. | `agents/verifier.py`, `adapters/prometheus.py` | An outcome can be recorded on one noisy sample | S4 |
| **N9** | **Approval runs synchronously in replay mode.** `/approve` constructs `IncidentOrchestrator(mode="replay")` and blocks the request while verifying. | `main.py:1118` | Verification cannot stream, and approval ignores the configured provider | S4 |
| **N10** | **Webhook signing and dedupe are weaker than they look.** The signature check is skipped when `webhook_secret` is unset (the default). The dedupe cache is in-process memory (lost on restart, not shared across workers). | `security.py` | An open webhook by default; duplicates after restart | S3 |
| **N11** | **Topology discovery reads the wrong file.** It parses `docker-compose.yml` in the backend's working directory, which describes Ripple itself. | `adapters/topology.py` | "Discovered" edges are Ripple's services, not the monitored system | S7 |
| **N12** | **Memory still unproven.** Report shows ON equals OFF on diagnosis (80%) and recommendation (40%), with 20% unsafe in both. | `docs/benchmark-report.md` | The learning claim has no evidence | S9 |
| **N13** | **Ops gaps.** The frontend image runs `npm run dev`; there is no CI; no end-to-end test; the UI theme file is unchanged. | repo root | Not shippable as a product | S10, S11 |

**What is good and should be kept:** HMAC verification (constant-time compare), the event bus with monotonic sequence and resume, the tool-result-to-evidence merge, the executor receipt and audit-hash design, Slack notifications, the honest README and report. The five new tests cover pieces correctly in isolation.

---

## 4. Feature inventory (updated)

| # | Feature | Status | Notes |
|---|---|---|---|
| 1 | Tenant graphs, temporal edges, tool library, hypothesis engine, memory model, counterfactual, Q&A, trace, MCP | Present | Unchanged from last review |
| 2 | Asynchronous incident execution (202 plus background task) | Present | Webhook confirmed; verify the manual `/incidents` route |
| 3 | Live event stream with resume | Present | Backend and frontend both implemented |
| 4 | Webhook signing and dedupe | Partial | Waived by default; in-memory cache (N10) |
| 5 | Tool results change evidence | Partial | `service_health` and `recent_changes` only |
| 6 | Prometheus adapter | Partial | Verifier only; mislabels fallback (N2, N3) |
| 7 | Deployment adapter | **Wired nowhere** | Defined, not called |
| 8 | Demo target (fault injection) | Partial | Break and restore are manual routes; not scrapeable by a real Prometheus; not healed by executors |
| 9 | Executors (Slack, GitHub dispatch, sandbox) | Partial | Dry-run by default when unconfigured; N6, N7 |
| 10 | Slack notifications | Present | Needs a webhook URL |
| 11 | Audit receipts | Partial | Hash and key exist; check that receipts are persisted in the graph |
| 12 | Outcome verification from metrics | Partial | Single sample (N8) |
| 13 | Real GitHub ingestion | Partial, defective | N5 |
| 14 | Topology discovery | Partial, wrong source | N11 |
| 15 | Authentication and roles | **Not enforced** | N1 |
| 16 | Honest data labelling | Present in docs; incorrect in two code paths | N2 |
| 17 | Benchmark with saved runs and honest report | Present | Still 5 scenarios (N12) |
| 18 | Production frontend build, CI, end-to-end tests | **Missing** | N13 |
| 19 | Onboarding for a team's own system | **Missing** | |
| 20 | Premium UI | **Missing** | Theme and shell unchanged |

---

## 5. Real vs demo audit (updated)

**A** = real and live. **B** = real logic, simulated or demo input. **C** = synthetic. **D** = cosmetic.

| Feature | Category | Evidence | To make it real |
|---|---|---|---|
| Alert intake via webhook | **A/B** | 202, signed (if secret set), deduped | Enforce secret; persist dedupe |
| Event streaming to UI | **A** | `EventSource`, resume support | Test end to end |
| Agent steps and timeline | **A** | Events come from the orchestrator as they happen | |
| Graph reasoning | **A** | Cypher at request time | Needs real data in the graph |
| Metrics used in investigation | **B** | Seeded `MetricSnapshot` | S1 |
| Metrics used in verification | **B/A** | Prometheus if configured, else demo target tagged `real` | S1, S2 |
| Deployments | **C** | Seeded; adapter unused | S1 |
| Topology | **B** | Hand-encoded; discovery reads wrong file | S7 |
| PRs, issues, owners | **C**, or **A** with a token | Synthetic by default; real fetch defective | S6 |
| Slack notifications | **A** | Real webhook call when URL set | |
| Rollback execution | **B** | Sandbox only changes nothing; GitHub dispatch is real but misconfigured by default | S2, S5 |
| Outcome recording | **B** | Single metric sample | S4 |
| Tool-calling LLM | **B** | Two tool types feed evidence | S8 |
| Memory recall | **B** | Works on seeded history | Needs accumulating real incidents |
| Benchmark | **B** | Deterministic pipeline | S9 |
| Auth and tenant isolation | **B** | Isolation by graph, trust by header | S3 |

---

## 6. What "real time" still needs

```
 Prometheus ◄── scrape ── demo target (real /metrics endpoint)
     │                         ▲
     │ rules                   │ restore on rollback
     ▼                         │
 Alertmanager ──signed webhook──► Ripple (202) ──► agents read LIVE metrics + deployments
                                       │                      │
                                       ▼                      ▼
                                 SSE to UI              hypotheses with real evidence
                                                              │
                                  approve ──► executor acts ──┘
                                                │
                                   poll post-fix metrics (window) ──► Outcome ──► memory
```

**End-to-end acceptance (the real-time bar):**
1. Break a service in the demo target. Prometheus scrapes it and Alertmanager fires.
2. The signed webhook creates an incident and the UI shows it within 2 seconds. Each agent step appears as it happens.
3. The investigation's evidence cites metrics pulled from Prometheus at alert time, tagged with their real source.
4. Approve the rollback. The executor acts on the target (it recovers), Slack gets a message, and verification polls metrics over a window.
5. The outcome is recorded from those metrics, and a later similar alert is handled differently because of it.
6. Kill and restart the backend mid-incident: the UI resumes from the stored events.

---

## 7. Implementation plan

Estimates assume heavy AI-assisted coding. Order matters.

### S1: Put live evidence into the investigation (5 hrs)
- Add one telemetry resolver (`adapters/get_adapter(tenant)`) that returns a Prometheus, deployment, or simulator adapter based on `telemetry_source` per tenant.
- Use it in triage and evidence generation: at alert time pull metrics for the alerting service and its upstream suspects and write `MetricSnapshot` nodes (`source` set honestly), then score as before.
- Wire `DeploymentAdapter` into `recent_changes` and evidence generation. Use real timestamps.
- **Honest labels:** introduce four values: `real`, `demo_target`, `seeded`, `synthetic`. When Prometheus is unreachable, return an **explicit "no data"** result (or tag the demo target as `demo_target`), never `real`. Fix N2 in `prometheus.py` and `investigator.py`.
- Use `query_range` with the requested window and `ref_ts`, not instant queries.
- **Acceptance:** with Prometheus down, evidence rows show `demo_target` or "no data"; with it up, they show `real` with scrape timestamps. A test covers each case.

### S2: Close the loop on the demo target (4 hrs)
- Expose the demo target as a real scrapeable endpoint (`/api/telemetry/demo/metrics` already generates Prometheus text; serve it with the correct content type under a stable path).
- Add Prometheus and Alertmanager to `docker-compose.yml` with a scrape config and two alert rules (latency, error rate). Alertmanager posts to Ripple's webhook with the signing secret.
- Make the sandbox executor call `restore_service` on `rollback` and `restart` for the target service, so a correct fix actually heals it. Keep a "wrong fix does nothing" path so failures are possible.
- **Acceptance:** break, alert, approve rollback, target recovers, verification reads normal. Also: approve the wrong runbook and verification reads failed.

### S3: Enforce authentication and tenancy (4 hrs)
- Store API keys hashed (a small `ApiKey` node set or table) with tenant and role. Remove the `key_<tenant>_<role>_<secret>` format check; look keys up.
- Make `authenticate_api_key` a dependency on every route except `/health`, the signed webhook, and the demo routes. Derive tenant from the key. Ignore `X-Tenant` unless the key is an admin key.
- Enforce roles: viewer reads, responder approves, admin changes integrations.
- **Fail closed in production:** if `ENV=production` and `webhook_secret` is unset, refuse to start. Persist the dedupe cache in the graph or Redis with a TTL.
- SSE auth: accept a short-lived signed stream token (query param) because `EventSource` cannot send headers.
- **Acceptance:** a tenant-A key cannot read or approve tenant B; an unsigned webhook is rejected in production mode; role tests pass.

### S4: Real verification and asynchronous approval (4 hrs)
- Verification polls the adapter every N seconds for a configurable window (for example 2 minutes), compares against the pre-incident baseline, and stores the metric series on the `Outcome`.
- Decide `resolved`, `partial`, `failed` from thresholds relative to baseline, not hard-coded text. Generate the explanation from actual numbers.
- Make `/approve` return 202 and run execution plus verification in the background, publishing `action_executed` and `outcome_verified` events as they happen. Use the configured LLM provider, not a hard-coded replay mode.
- **Acceptance:** after approval the UI shows a live "verifying" state with real samples, then the outcome; memory counts update from that outcome.

### S5: Harden executors and integrations (4 hrs)
- Move repo, workflow name, ref, and Slack URL into **per-tenant integration settings** with no default repo. If unset, the executor refuses and says what to configure (fixes N6).
- Enforce idempotency in **every** executor using a persisted `ExecutionReceipt` node keyed by idempotency key, so retries and restarts cannot repeat an action (N7).
- Timeouts, bounded retries, and clear error receipts. Dry-run on by default for new tenants, with an explicit switch to live.
- Persist receipts (who approved, payload hash, result) in the graph and show them in an audit view.
- **Acceptance:** a duplicate approval is a no-op after a restart; an unconfigured GitHub executor refuses cleanly.

### S6: Fix real GitHub ingestion (5 hrs)
- Paginate contributors, commits, PRs, issues; use ETags and respect rate limits.
- Take `merged_at` from the API. Map PRs to services using the PR's changed files and a configurable path-to-service table (no hard-coded `frontend`). Read `CODEOWNERS` for ownership.
- Pull deployments or Actions runs for real deployment evidence (feeds S1).
- If a live fetch fails, **say so** and mark data as `synthetic` or stale; never silently fall back.
- Incremental sync with a last-synced time shown in the UI.
- **Acceptance:** every PR link opens the real PR; ownership matches `git shortlog` on a service path; evidence times match real merge times.

### S7: Topology from the monitored system (3 hrs)
- Fetch the **target repo's** manifests or compose file (from GitHub or an uploaded file) instead of reading Ripple's own file. Make the path configurable.
- Write edges with `source='discovered'` and `verified=true` only when found in those files; keep hand-encoded edges `verified=false` until confirmed.
- **Acceptance:** discovery on the sample repo yields the app's services, not Ripple's.

### S8: LLM live-mode correctness (3 hrs)
- Use `llm_provider` on every route (incident, webhook, approve, ask). Show the active provider and a visible **degraded** banner in the UI when it fails (verify the flag reaches the frontend).
- Extend tool-to-evidence conversion beyond two tools (`path_between`, `upstream_suspects`, `similar_incidents`), and tag each evidence row with where it came from.
- Record replay cache entries from real live runs so demos are repeatable and labelled "replay".
- **Acceptance:** two different alerts produce different tool sequences and different evidence in live mode.

### S9: Benchmark v3 that can show memory helping (4 hrs)
- Investigate why memory ON equals OFF: confirm memory-off truly disables recall, and that recall is reached by the vector query.
- Fix the recommendation correctness (40%) and the 20% unsafe case, or explain them with the labels.
- Run 12 or more scenarios in the five families, 3 repeats in live mode, memory ON and OFF. Report variance, per-family results, and every case where memory hurt.
- **Acceptance:** report states a measured memory effect with margin, or states plainly that none was found and why.

### S10: Operations and quality (5 hrs)
- Production frontend image (multi-stage build, static serving).
- GitHub Actions CI: backend tests with a FalkorDB service container, frontend typecheck and build.
- Playwright end-to-end test that runs the acceptance flow in section 6.
- Load test with parallel incidents across two tenants; check for duplicates and lost writes.
- Structured logs with incident and tenant IDs; confirm `/metrics` exposes Ripple's own health.
- **Acceptance:** CI green on a clean clone; the end-to-end test passes.

### S11: Premium SaaS interface (see section 8)

---

## 8. Making the UI premium

The frontend theme, shell, and layout are unchanged since the last review, so this plan still applies. Use the **forest, mint, and cream system from your Figma file**.

**Foundation**
- Replace the cream and red-orange tokens in `index.css` with the Figma tokens (forest `#12281B`, `#1C3A2A`, `#0B1810`; mint `#D9F0B9`; cream `#EBE3D0`; good `#43D675`; warn `#F0B35A`; bad `#E8745F`).
- One component set built on the existing shadcn primitives: buttons, inputs, tabs, tables, dialogs, toasts, badges.
- Purposeful motion only; respect `prefers-reduced-motion`.

**Truthful trust cues (new, because of N2)**
- A **source badge on every number and evidence row**: real, demo target, seeded, synthetic. Colors and tooltips explain each.
- A **data-health pill** in the header: backend, FalkorDB, LLM provider (with degraded state), Prometheus, GitHub last-synced, Slack.
- Show live connection state (connected, reconnecting) for the stream.

**Screens**
- Overview (open incidents, recent outcomes, health), Incident war room, Services graph, Memory, What if, Benchmark, Ask, Integrations, Settings and audit log.
- **War room (hero):** streaming timeline with server timestamps; hypothesis board that re-ranks live; graph highlighting the path being explored; memory recall with "why not recommended"; approval card with payload preview and dry-run; live **verification** progress with real samples; postmortem export.
- **Integrations and onboarding:** connect GitHub, alert source (copyable webhook URL and secret with a test button), Prometheus, Slack; run a test alert; checklist of what is real vs seeded for this tenant.

**Quality bar**
- Skeletons, empty states with a next step, plain-language errors with retry.
- Accessibility: keyboard navigation, visible focus, `aria-live` for streaming events, contrast checks (target WCAG AA).
- Performance: lazy-load the 3D scene and heavy views, split the bundle, pause rendering when hidden, 2D fallback without WebGL.
- Responsive for laptop and tablet; war room collapses to one column with the approval card pinned.

| Step | Work | Effort |
|---|---|---|
| U1 | Tokens and theme, remove old sidebar | 3 hrs |
| U2 | App shell: top nav, workspace switcher, command palette, health pill | 4 hrs |
| U3 | War room on the live stream, with source badges and live verification | 6 hrs |
| U4 | Loading, empty, error, reconnect states | 2 hrs |
| U5 | Accessibility and reduced motion | 2 hrs |
| U6 | Performance: lazy loading, bundle split, 3D guard | 2 hrs |
| U7 | Integrations and onboarding screens (after S3 to S7) | 5 hrs |
| U8 | Settings, roles, audit log, postmortem export | 4 hrs |

---

## 9. Schedule

Roughly 36 hours remain. Everything is about 55 hours, so this is split into a hackathon cut and a product roadmap.

### Hackathon cut (before submitting)

| Order | Work | Hours | Gate |
|---|---|---|---|
| 1 | S1 live evidence plus honest labels | 5 | Evidence shows `real` / `demo_target` correctly |
| 2 | S2 closed loop with Prometheus and Alertmanager in Compose, rollback heals target | 4 | Steps 1 to 4 of the acceptance flow pass |
| 3 | S4 polled verification and async approve | 4 | Outcome comes from real samples; UI streams it |
| 4 | S3 minimum: enforce API-key dependency, fail-closed webhook secret in production mode | 2 | Cross-tenant request rejected |
| 5 | S5 minimum: no default repo, persisted idempotency | 2 | Duplicate approval is a no-op |
| 6 | S9 benchmark honesty re-run | 3 | Report matches the data |
| 7 | U1, U2, U3, U4, U6 | 17 | Matches the Figma look; war room streams |
| 8 | Demo video, README, submission | 3 | Submitted early on Oct 18 |

That is about 40 hours. If short, reduce depth in this order: U7 and U8, then S6 and S7 (keep the sample dataset labelled), then extra benchmark repeats. **Do not drop** S1, S2, S4, the source badges, or the honest report.

### Product roadmap (after the hackathon)
S6 real GitHub sync, S7 topology from real systems, full S3 and S5, S8, S10 CI and end-to-end tests, U7 and U8, onboarding.

---

## 10. Definition of done

- [ ] Break the demo target; Alertmanager fires; the signed webhook opens an incident in under 2 seconds
- [ ] The investigation's evidence comes from live Prometheus data and is labelled `real`; simulated data is labelled `demo_target`, `seeded`, or `synthetic`
- [ ] Approving a rollback executes, the target recovers, and verification polls real samples before recording the outcome
- [ ] A wrong fix produces a recorded **failed** outcome, and memory changes the next recommendation
- [ ] Every route except health and the signed webhook requires a valid key; cross-tenant access is rejected
- [ ] Duplicate approvals do nothing, even after a restart
- [ ] No executor has a default repo or destination
- [ ] The UI shows source badges, live connection state, and a degraded-LLM banner
- [ ] The benchmark report states a measured memory effect or says none was found
- [ ] CI is green and an end-to-end test covers the flow above

---

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Prometheus and Alertmanager setup eats time | S2 stalls | Start from a minimal config with two rules; keep the in-process demo target as an honestly labelled fallback |
| Alertmanager label names differ from graph service names | Alerts rejected as unmapped | Add a label-to-service mapping and a clear "unmapped service" response |
| Real LLM latency slows the demo | Flat video | Events stream as they happen; keep a recorded, labelled replay |
| Auth change breaks the UI | Locked out mid-demo | Ship a dev key in `.env.example` and a dev-mode switch that is off in production |
| Mislabelled data discovered by a judge | Credibility | Fix N2 first; add tests that assert labels in both Prometheus-up and Prometheus-down cases |
| Scope too large | Unfinished | Follow the gates in section 9 |

---

*This review is based on reading the uploaded code. The backend, tests, and Docker stack were not run, and no live LLM, Slack, GitHub, or Prometheus calls were made.*

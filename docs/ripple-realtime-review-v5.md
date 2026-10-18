# Ripple: Code Review v5 (Functionality Focus)

**Review date:** Oct 17, 2026 · **Hackathon deadline:** Oct 18, 11:59 PM IST · **Repo reviewed:** `ripple-master (4).zip` (1,400 files; about 19.1k lines of backend, 6.4k lines of tests)

**Scope:** backend functionality and real-time behavior only. The frontend is out of scope, as you asked.

> **How I reviewed.** I read the code for every item in the v4 findings, compared this version with the last, and checked that the backend, tests, and scripts compile (they do). I did **not** run the backend, tests, Docker, Prometheus, Alertmanager, or any live LLM, Slack, GitHub, or Kubernetes call. "Fixed" means the code now does the right thing when read. Nothing here has been proven by running the full stack.

---

## 0. The short version

**Almost every finding from the last review is now fixed in the code.** That includes the Alertmanager signature problem, the unauthenticated stream, the fake verification, the silent failures, the published API keys, and the overstated benchmark. This is a substantially more trustworthy system than the one I reviewed before.

What is left is smaller and different in kind:

1. **The "end-to-end" test does not exercise the real chain.** It runs in-process with a test client and falls back to that automatically if the live backend is unreachable. Prometheus, Alertmanager, and the real webhook-to-stream path over HTTP have still not been proven together.
2. **A published default webhook token passes the production check.** `ripple_alertmanager_token_secret` is the Compose default, the `.env.example` value, the Alertmanager config, and the e2e script default. The production check only requires *some* token to be set.
3. **The benchmark's "n=78" overstates the evidence.** The runs are deterministic repeats of 13 scenarios, so the effective sample is 13. The only measured benefit comes from two stale-trap scenarios and is produced by a rule-based applicability filter, not by learning from past incidents.
4. **Integration secrets are encrypted with a weak key.** The key is derived from the webhook secret, or from a hard-coded salt when none is set.
5. **A few smaller correctness gaps** (section 2).

None of these is large. The most valuable remaining work is **proving the real chain once, end to end, with the real containers**, and then cleaning up the credibility issues around defaults and the benchmark.

---

## 1. Status of the v4 findings

| ID | Finding in v4 | Status | Evidence in the code |
|---|---|---|---|
| V3 | Alertmanager used a fake fixed signature | **Fixed** | `alertmanager.yml` now uses `authorization: Bearer`; `WEBHOOK_TOKEN` is checked in `security.py`; production startup requires a secret or token |
| V4 | Demo target counters were constant, so `rate()` was empty | **Fixed** | `demo_target.py` has a traffic-simulator thread that increments counters and histogram buckets; alert rules use `histogram_quantile(0.95, rate(..._bucket[1m]))` and a `rate()` error ratio |
| V2 | Event stream unauthenticated | **Fixed** | Stream route depends on `authenticate_api_key` and checks the incident belongs to the caller's tenant (403 otherwise) |
| V5 | Verification could report unobserved success | **Fixed** | 60 s window with 10 s steps (per-tenant configurable), baseline captured pre-incident in the orchestrator, outcome defaults to `inconclusive`, memory counters update only for resolved/partial/failed |
| V6 | Silent failure on live metrics | **Fixed** | Failure now logs, sets `telemetry_degraded` on the incident, and publishes a `telemetry_degraded` event |
| V1 | Dev auth fallback and published keys | **Fixed** | No plaintext keys in source; hashed keys persisted to a file; revoke added; default-key hashes make production refuse to start; dev fallback needs `AUTH_DEV_MODE=true` (default false) |
| V10 | Benchmark overclaimed | **Mostly fixed** | Formal retraction of the earlier claims; 13 scenarios x 3 repeats; calibration reported as NOT MET; see W4 for what remains |
| V7 | Telemetry source global and off by default | **Fixed** | `get_adapter(tenant_id)` reads per-tenant settings; `prometheus`, `demo_target`, and `simulator` are distinct adapters; Prometheus no longer falls back silently |
| V8 | GitHub ingestion defects | **Fixed** | Link-header pagination, ETag caching, rate-limit handling (403/429), whole-word keyword matching, per-tenant path-to-service mapping |
| V9 | Integration settings global | **Fixed** | `tenant_settings.py` stores per-tenant Slack URL, repo, workflow, ref, Prometheus URL, persisted in the graph with encrypted secrets; executors and notifications read them |
| V11 | CI covered 2 of 14 test files | **Fixed** | CI runs the full suite, a multi-tenant load test, and the e2e script |
| V12 | Frontend image ran the dev server | **Fixed** | Multi-stage Dockerfile builds static assets and serves them with nginx; CI has a docker-build job |
| V13 | Topology from a bundled static file | **Mostly fixed** | Manifests from the GitHub API, OpenTelemetry trace edges with verification, a tenant onboarding API, and tests |
| (new) | Kubernetes executor | **Added** | `kubernetes.py` for rollout undo with idempotency and audit; uses an in-memory key set plus the graph audit log |

---

## 2. Remaining findings

Ordered by how much they affect the real-time claim and credibility.

| ID | Finding | Where | Impact | Fix |
|---|---|---|---|---|
| **W1** | **The e2e test never leaves the process.** `test_e2e.py` calls `run_e2e(use_testclient=True)`, and the script sends the webhook with `?sync=true`. If the live backend is unreachable, the script prints a warning and **falls back to the in-process client**, so it can pass with no stack running. CI runs `--testclient`. Prometheus scraping, Alertmanager grouping and delivery, and SSE over real HTTP are not covered. | `backend/tests/test_e2e.py`, `scripts/e2e_realtime_test.py`, `ci.yml` | The core real-time claim is unproven | Z1 |
| **W2** | **A published default webhook token is accepted in production.** `ripple_alertmanager_token_secret` appears in `docker-compose.yml` (as a default), `.env.example`, `alertmanager.yml` (plaintext, not substituted from the environment), and the e2e script. Production checks only that a token or secret exists. | `main.py:115`, `docker-compose.yml`, `deploy/alertmanager/alertmanager.yml` | Anyone who reads the repo can post alerts to a "production" instance that kept the default | Z2 |
| **W3** | **Integration secrets use a weak encryption key.** The Fernet key is derived from `webhook_secret`, or from a hard-coded salt (`ripple_default_encryption_salt_2026`) when none is set. Rotating the webhook secret makes stored Slack and GitHub secrets undecryptable. | `tenant_settings.py` | Dev data is encrypted with a public key; rotation silently breaks integrations | Z5 |
| **W4** | **Benchmark evidence is thinner than it reads.** (a) The 78 runs are deterministic: three repeats of the same scenario add no information, so the effective sample is 13 scenarios. (b) Diagnosis is 100% in both modes with zero variance, so the scenarios do not discriminate. (c) The +15.4% recommendation gain is 36 of 39 vs 30 of 39 runs, which is exactly the two stale-trap scenarios x 3 repeats. It comes from the rule-based applicability filter, not from learning from outcomes. (d) The report says unsafe rate is 0% "after telemetric discriminatory probes", which suggests scenarios or logic were adjusted after seeing results. (e) The labels commit hash changed again (`465982d...`); the zip has no git history to confirm it predates the runs. (f) No live-LLM runs. | `docs/benchmark-report.md`, `benchmark/runner.py` | A sharp judge will say memory was not shown to learn anything | Z3 |
| **W5** | **No test shows learning from experience.** Nothing demonstrates that a recorded outcome (a fix that failed or succeeded) changes a later recommendation beyond the applicability rule. | `memory/`, `agents/responder.py` | The headline "memory improves with use" has no direct evidence | Z3 |
| **W6** | **Stream credentials travel in the URL.** `EventSource` cannot set headers, so the stream accepts `?token=` or `?api_key=` carrying the long-lived API key. The incident-tenant lookup also scans a hard-coded list `["storefront", "payments"]`, so new tenants may not resolve. | `main.py` (stream route), `security.py` | Keys end up in logs and browser history; new tenants cannot stream | Z4 |
| **W7** | **Real components still not proven together.** The Prometheus adapter now uses `fallback_to_demo=False`, so with `telemetry_source=prometheus` it depends on Prometheus returning real `rate()` results from the traffic simulator, and the verifier depends on the same path. I read this as correct but it has never been run against the container. | `adapters/prometheus.py`, `agents/verifier.py` | Possible silent mismatch between metric names or labels and the queries | Z1 |
| **W8** | **Live LLM influence is still narrow.** Tool results become evidence for a small set of tools, and there are no live-LLM benchmark runs, so the "LLM chooses tools" claim has no measured support. | `agents/investigator.py`, `agents/tool_loop.py` | The pitch cannot point at evidence of LLM-driven investigation | Z6 |
| **W9** | **Kubernetes executor idempotency is partly in memory.** It keeps `_EXECUTED_K8S_KEYS` in a set, plus the graph audit check. After a restart it relies only on the graph record, which is fine, but a failed audit write could allow a repeat. | `executors/kubernetes.py` | Low risk, worth a test | Z2 (small) |

**What is good and should be kept:** the `inconclusive` outcome and the rule that memory updates only from conclusive outcomes, the pre-incident baseline captured at open, per-tenant adapters and settings, the `telemetry_degraded` event, key persistence and revocation, the production fail-closed behavior, the formal retraction in the benchmark report, and the broad test additions (`test_e2e`, `test_load`, `test_t10`, `conftest`).

---

## 3. Real-time flow: current status

| Step | What must happen | Status |
|---|---|---|
| 1 | Break a service; Prometheus scrapes it; an alert fires | **Built.** Traffic simulator, scrape config, and corrected rules exist. Unverified in containers |
| 2 | Alertmanager delivers to the webhook with auth on | **Built.** Bearer token path exists. Default token is public (W2) |
| 3 | Incident opens quickly; SSE streams events with auth | **Built.** In-process test only (W1) |
| 4 | Evidence cites live Prometheus metrics; failures are visible | **Built.** Degraded event on failure. Unproven against the real container (W7) |
| 5 | Approve; executor acts; target recovers; Slack notified | **Built.** Sandbox restores the demo target; Slack, GitHub dispatch, and Kubernetes need per-tenant configuration |
| 6 | Verification polls a real window against the baseline | **Built.** 60 s window; `inconclusive` when data is missing |
| 7 | Outcome recorded; later alerts handled differently | **Partly proven.** Applicability rule shown on 2 scenarios; no learning-curve evidence (W4, W5) |
| 8 | Restart mid-incident; stream resumes | **Built.** Persisted events with `Last-Event-ID`; persisted dedupe and keys. Tested in-process only |

---

## 4. Real vs demo audit (functionality)

**A** = real and live when configured. **B** = real logic on demo or simulated input. **C** = synthetic.

| Capability | Category | Notes |
|---|---|---|
| Alert intake (bearer or HMAC), dedupe, async run | **A** | Default token is public (W2) |
| Event streaming with resume and tenant check | **A** | Key in URL (W6) |
| Telemetry via Prometheus (per tenant) | **A (when configured)** | Not yet run against the container (W7) |
| Telemetry via demo target | **B** | Real counters from a simulated target, labelled `demo_target` |
| Deployments and PRs via GitHub | **A (when a repo and token are set)**, else **C** | Pagination, ETags, rate-limit handling |
| Topology via manifests or traces | **A (when configured)**, else **B** | |
| Actions: Slack, GitHub dispatch, Kubernetes | **A (when configured)** | Persisted idempotency and audit |
| Actions: sandbox | **B** | Heals the demo target |
| Verification | **A/B** | Windowed, baseline-relative, `inconclusive` when unsure |
| Memory | **B** | Mechanism present; benefit shown only by the applicability rule (W4, W5) |
| LLM tool use | **B** | Narrow influence (W8) |
| Auth, tenancy, roles | **A** | Solid; defaults to fail closed |

---

## 5. Plan to finish

Estimates assume heavy AI-assisted coding. Order matters.

### Z1: Prove the real chain with the real containers (4 hrs, do first)
- Make the e2e script **fail** instead of falling back when the live stack is unreachable. Add an explicit `--testclient` flag for the in-process variant, and keep both as separate CI jobs.
- Add a live job: `docker compose up`, break the demo target through the API, wait for Prometheus to scrape and Alertmanager to deliver, assert the incident opens, assert SSE events arrive in order over real HTTP with auth, approve, assert the target recovers, assert verification reads recovered metrics from Prometheus, restart the backend container mid-run and assert resume.
- Check that the queries in `prometheus.py` match the metric and label names the simulator emits (`service` label, bucket series) by running them against the container and recording the output.
- **Acceptance:** one live run passes in CI or locally; a log shows real Prometheus query results being used as evidence and for verification.

### Z2: Remove published defaults (2 hrs)
- Refuse to start in production if `WEBHOOK_TOKEN` or `WEBHOOK_SECRET` equals a known default (add the default values to a deny list, like the API-key hash list).
- Substitute the token in `alertmanager.yml` from the environment (for example by templating the file at container start) instead of hard-coding it.
- Remove the default token from the e2e script; read it from the environment.
- Add a test that production mode rejects each default.
- Add a restart-safety test for the Kubernetes executor's idempotency path.
- **Acceptance:** production mode refuses the default token; the Alertmanager config has no plaintext secret.

### Z3: A benchmark that shows learning (5 hrs)
- **State the real sample.** Report effective n as the number of distinct scenarios (13), and describe repeats as determinism checks, not extra evidence.
- **Add scenarios that discriminate.** Diagnosis at 100% in both modes means the scenarios are too easy. Add cases with ambiguous or conflicting evidence so correctness can vary.
- **Add a learning-curve experiment** (W5): a sequence of related incidents where the first recommended fix fails; show that after the recorded failure, the next similar incident recommends a different fix or abstains, and that without memory it repeats the failed fix. Report the result per step.
- **Freeze before measuring.** Commit scenarios and labels, record the commit hash and a SHA-256 in the report, and do not change scenarios or logic after the run. If something must change, re-register and rerun, and say so.
- **Add live-LLM runs** for the investigator and responder, kept in a separate section with the provider and model named.
- **Acceptance:** the report separates effective sample from repeats, includes the learning-curve table, names the commit that predates the run, and makes no claim beyond the data.

### Z4: Stream authentication without long-lived keys in URLs (2 hrs)
- Add `POST /incidents/{id}/stream-token` (authenticated) returning a short-lived token (for example 5 minutes) scoped to that incident and tenant. Accept it on the stream route in place of `?token=` or `?api_key=`, and stop accepting long-lived keys in the query string.
- Replace the hard-coded `["storefront", "payments"]` incident-tenant scan with a stored incident-to-tenant mapping set when the incident is created.
- **Acceptance:** a stream token for tenant A cannot open tenant B's incident; a newly created tenant can stream its own incidents; long-lived keys in the URL are rejected.

### Z5: Proper secrets encryption (1.5 hrs)
- Use a dedicated `SETTINGS_ENCRYPTION_KEY` (required in production, generated and stored outside source in development), not a key derived from the webhook secret or a hard-coded salt.
- Support key rotation: store a key version in the `enc:` prefix and re-encrypt on write.
- **Acceptance:** rotating the webhook secret does not break stored integrations; production refuses to start without the encryption key.

### Z6: Measurable LLM influence (3 hrs)
- Convert more tool results into evidence (`path_between`, `upstream_suspects`, `similar_incidents`), each tagged with its true source.
- Record from live runs which tool calls the LLM made, and whether the top hypothesis or evidence differed from the deterministic run.
- Add an `llm_degraded` event and field when a provider call fails, matching `telemetry_degraded`, and make `/approve` and `/ask` use the configured provider.
- Record replay-cache entries from real live runs, labelled "replay".
- **Acceptance:** a table of live runs showing LLM-chosen tool calls and the effect on evidence or ranking, with at least one case where it changed the outcome and one where it did not.

### Z7: Operations (2 hrs)
- Confirm `/metrics` exposes Ripple's own health (events processed, incident durations, verification outcomes, telemetry degraded count) and add those series to the Prometheus config.
- Structured logs with incident and tenant IDs; a documented backup and restore step for the FalkorDB volume and the persisted key and event files.
- A short runbook: how to rotate keys, tokens, and the encryption key.
- **Acceptance:** after a run, `/metrics` shows the incident and verification counters.

### Z8: Submission package (3 hrs)
- README with the exact three-command start, the real-vs-demo table above, and links to the benchmark report.
- Demo script for the live chain (break, alert, stream, evidence from Prometheus, approve, recovery, verified outcome, restart resume).
- A clean-clone test of the quick start; confirm no secrets in the repository or in `.env.example` beyond clearly marked development values.

---

## 6. Schedule

About 36 hours remain. This plan is about 22 hours, which leaves room to rest and fix surprises.

| Order | Work | Hours | Gate |
|---|---|---|---|
| 1 | Z1 live end-to-end with real containers | 4 | One live run passes; Prometheus queries return data |
| 2 | Z2 remove published defaults | 2 | Production refuses defaults |
| 3 | Z4 stream tokens and tenant mapping | 2 | Cross-tenant stream blocked; new tenant streams |
| 4 | Z3 benchmark with learning curve | 5 | Report is reproducible and honest |
| 5 | Z5 encryption key | 1.5 | Rotation test passes |
| 6 | Z6 LLM influence evidence | 3 | Live-run table produced |
| 7 | Z7 operations | 2 | `/metrics` shows counters |
| 8 | Z8 submission package | 3 | Clean-clone start works; submitted early on Oct 18 |

If time is short, reduce depth in this order: Z6, then Z7, then the live-LLM benchmark section. **Do not drop:** Z1, Z2, or the honest benchmark and learning-curve work in Z3.

---

## 7. Definition of done

- [ ] One live run over real containers passes: break, Prometheus alert, Alertmanager delivery with a bearer token, authenticated SSE, evidence from Prometheus, approval, recovery, windowed verification, restart resume
- [ ] The e2e script fails (not falls back) when the live stack is unreachable
- [ ] Production refuses default API keys, default webhook token, and a missing settings encryption key
- [ ] Alertmanager config contains no plaintext secret
- [ ] Stream access uses short-lived, incident-scoped tokens; no long-lived keys in URLs
- [ ] The benchmark reports effective sample size, includes a learning-curve result, and names a commit that predates the run
- [ ] A fix that failed once is not recommended again for a similar incident, shown by test and by the report
- [ ] A table shows where live LLM tool calls changed evidence or ranking
- [ ] `/metrics` exposes incident, verification, and degraded-telemetry counters

---

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The live chain reveals a metric or label mismatch | Z1 takes longer | Run the PromQL queries by hand first and compare to the simulator output |
| New scenarios still produce 100% diagnosis | Benchmark does not discriminate | Add genuinely ambiguous cases, and report honestly if diagnosis stays at ceiling |
| Learning-curve experiment shows no change in recommendations | Memory claim fails | Fix the responder's use of recorded failures, or report it as a known limitation |
| Alertmanager templating complicates startup | Z2 stalls | Use an entrypoint script that renders the config from environment variables |
| Time pressure | Unfinished | Follow the schedule gates and the stated drop order |

---

*This review is based on reading the uploaded code. The backend, tests, Docker stack, Prometheus, Alertmanager, and all external integrations were not run in this review.*

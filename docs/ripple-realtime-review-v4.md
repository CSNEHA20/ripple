# Ripple: Code Review v4 (Real-Time Backend Focus)

**Review date:** Oct 17, 2026 · **Hackathon deadline:** Oct 18, 11:59 PM IST · **Repo reviewed:** `ripple-master (3).zip` (1,382 files; about 15.8k lines of backend, 3.4k lines of tests)

**Scope:** backend, integrations, and real-time behavior only. **UI changes are out of scope**, as you asked. The frontend is unchanged in this version, so I did not re-review it.

**Main motto:** *Ripple must work in real time.*

> **How I reviewed.** I read the code (new `resolver.py`, `deploy/` configs, `security.py`, executors, adapters, verifier, evidence generation, GitHub ingestion, topology, CI, tests, benchmark report) and compared it with the previous version. I did **not** run the backend, tests, Docker, Prometheus, Alertmanager, or any live LLM, Slack, or GitHub call. "Works" means the code path exists and reads as correct.

---

## 0. The short version

**This is the biggest step forward so far.** Most of the gaps from the last review are now closed in code:

- Live metrics feed the investigation, with honest `demo_target` labels.
- Rollback now heals the demo target.
- Prometheus and Alertmanager run in Docker Compose with alert rules.
- Authentication and roles are enforced on most routes.
- Approval is asynchronous.
- All three executors use persisted, graph-backed idempotency.
- GitHub ingestion is much less wrong.
- CI exists.

**What still stops it from being truly real-time and trustworthy:**

1. **Alertmanager cannot talk to Ripple once a secret is set.** It sends a fixed header (`sha256=alerts_dev_signature`), but Ripple expects a real HMAC. The demo works only because the secret is unset by default. In production mode, every alert would be rejected.
2. **The "live Prometheus" path does not really work against the demo target.** The demo target emits constant counters, so PromQL `rate()` returns nothing useful, and the adapter quietly falls back to the in-process demo values.
3. **The event stream has no authentication.** `/incidents/{id}/stream` has no auth dependency, so anyone who knows an incident ID can watch any tenant's events.
4. **Verification can report success it did not observe.** It takes 3 samples over about 0.15 seconds, never compares to the baseline, and defaults to "resolved" when nothing matches or the simulator errors.
5. **The benchmark report regressed.** It says "Calibration PASSED" again and claims a +20% memory benefit on the same 5 scenarios. That difference is one scenario.
6. **Failures are swallowed.** The live metrics pull is wrapped in `except Exception: pass`, so a Prometheus outage silently falls back to seeded data.

The remaining work is mostly **correctness and trust**, not new features.

---

## 1. Status of the previous review's findings

| ID | Finding in v3 | Status now | Evidence |
|---|---|---|---|
| N1 | Auth not enforced | **Mostly fixed** | `get_current_tenant` depends on `authenticate_api_key`; `require_role` on approve and admin routes; non-admin keys blocked from other tenants. Open gaps in section 2 (V1, V2) |
| N2 | Simulated data labelled `real` | **Fixed** | Fallback records are tagged `source="demo_target"`; range queries added |
| N3 | Live metrics not used in investigation | **Fixed (with caveat)** | `evidence.py` pulls adapter metrics and writes `MetricSnapshot` nodes; `recent_changes` uses the deployment adapter. Caveat: default `telemetry_source` is still `simulator` |
| N4 | Rollback did not heal the target | **Fixed** | `sandbox.py` calls `restore_service` for the target |
| N5 | GitHub fetch mapped everything to `frontend` with `merged_at=now` | **Mostly fixed** | ISO timestamps parsed, CODEOWNERS read, PR files used for service mapping, deployments fetched. Remaining defects in V8 |
| N6 | GitHub executor targeted Google's repo | **Fixed** | Refuses cleanly if repo is unset or is the sample repo (global setting, not yet per tenant; V9) |
| N7 | Idempotency only in sandbox, in memory | **Fixed** | All three executors check a persisted `AuditLog` node and record receipts |
| N8 | Verification was one instant query | **Partly fixed** | Now 3 samples, streamed as `verification_sample` events; window is only about 0.15 s (V5) |
| N9 | Approval ran synchronously in replay mode | **Fixed** | Approval returns 202 and runs in the background; uses live mode when any LLM key is set; `sync=true` kept for tests |
| N10 | Webhook secret optional, dedupe in memory | **Partly fixed** | Dedupe persisted to `data/alert_dedupe.json`; production fails closed at startup without a secret. Alertmanager integration breaks under a secret (V3) |
| N11 | Topology read Ripple's own compose file | **Fixed for the demo** | Reads a bundled `data/target_compose.yml` for the sample app; not yet fetched from a real target (V13) |
| N12 | Memory benefit unproven | **Regressed in honesty** | See V10 |
| N13 | No CI or end-to-end test | **Partly fixed** | `.github/workflows/ci.yml` runs backend and frontend jobs. It runs only 2 of 14 test files (V11); no end-to-end test |

---

## 2. Findings in this version

Ordered by impact on real-time correctness and trust.

| ID | Finding | Where | Impact | Fix |
|---|---|---|---|---|
| **V3** | **Alertmanager config uses a fixed fake signature.** `deploy/alertmanager/alertmanager.yml` sets `X-Ripple-Signature: sha256=alerts_dev_signature`. `verify_webhook_signature` computes a real HMAC of the body. It passes today only because `webhook_secret` is unset (verification is skipped). Setting a secret, which production requires, rejects every alert from Alertmanager. | `deploy/alertmanager/alertmanager.yml`, `security.py` | The real-time entry point breaks the moment security is switched on | T2 |
| **V4** | **Demo target metrics are static, so PromQL cannot use them.** Counters are constants (1000, 320, and so on) and never increase. `rate(...[5m])` of a constant is 0, so `histogram_quantile(rate(bucket))` and the error-rate ratio return NaN or nothing. The adapter then falls back to the in-process demo values. The alert rules happen to work because they use `sum/count` and a plain ratio. | `adapters/demo_target.py`, `adapters/prometheus.py`, `deploy/prometheus/alert.rules.yml` | "Live Prometheus evidence" is not actually exercised; the first rule also says "p95" but computes a mean | T1 |
| **V2** | **SSE stream is unauthenticated.** `api_stream_incident_events` has no auth dependency; the tenant is only a query parameter, and the event bus is not checked against the caller's tenant. | `main.py` (stream route) | Anyone with an incident ID can read any tenant's events | T3 |
| **V5** | **Verification can fabricate success.** (a) The "window" is 3 samples with `sleep(0.05)`, about 0.15 s. (b) Baseline is read from the graph but never compared. (c) `observed` starts as `"resolved"` and stays that way if no telemetry branch matches or the simulator raises (the code logs "Defaulting to resolved"). (d) Thresholds are fixed numbers (2% / 500 ms / 15% / 1500 ms). A wrongly recorded success also feeds memory. | `agents/verifier.py` | Outcomes, and therefore learning, can be wrong | T4 |
| **V6** | **Silent failure on live metrics.** The adapter call in `evidence.py` is wrapped in `except Exception: pass`. | `hypotheses/evidence.py` | If Prometheus is down, the investigation quietly uses seeded data with no log and no degraded marker | T1 |
| **V1** | **Development auth fallback and published dev keys.** With no key and `ENVIRONMENT != production`, any caller becomes `admin`. Six keys (`key_<tenant>_<role>_secret`) are hard-coded in source and written out in comments. The key store is an in-memory dict, so `register_api_key` entries vanish on restart. Production mode rejects missing keys but still accepts the published ones. | `security.py` | Default admin access in dev; guessable keys if not removed in production | T3 |
| **V10** | **Benchmark integrity regressed.** The report says "Calibration Check: PASSED" again, and claims "+20.0% recommendation correctness" for memory. It is still 5 scenarios and 10 runs. The delta is 3 of 5 vs 2 of 5, which is one scenario. The runner and responder logic changed (a `memory_enabled` switch), but the "pre-registered labels commit" hash is unchanged. "Unsafe 20%" is the same in both modes while the note says the filter blocks stale traps. No live-LLM runs. | `docs/benchmark-report.md`, `benchmark/runner.py` | A judge can discredit the strongest claim | T7 |
| **V7** | **Telemetry source is global, and off by default.** `get_adapter(tenant_id)` ignores its argument and reads one global `telemetry_source`; `demo_target` and `prometheus` both return `PrometheusAdapter`. Default is `simulator`, so by default nothing is live. | `adapters/resolver.py`, `config.py` | Cannot run different tenants on different sources; demo needs an env var to be live | T1, T6 |
| **V8** | **GitHub ingestion still has defects.** Only the first page of 100 items is fetched (no `Link` pagination). PR files use `per_page=10` and one extra request per PR (rate-limit risk). Service inference falls back to keyword substring matching on title and body, hard-coded to the sample app, and the keyword `"ad"` matches common words like "add", "load", and "read". `merged_at` falls back to now when parsing fails. The real fetch is skipped for the default sample repo. | `ingest/github.py` | Wrong service ownership and timing in some cases | T5 |
| **V9** | **Integration settings are global, not per tenant.** GitHub repo is `settings.github_repo`; workflow name `rollback.yml` and ref `main` are hard-coded; one Slack webhook serves all tenants. The "refuse" check compares against Google's repo by string. | `executors/*`, `config.py` | Tenants cannot have separate destinations | T6 |
| **V11** | **CI covers little.** The workflow runs only `tests/test_smoke.py` and `tests/test_realtime.py`, not `test_m1` to `test_m11`. There is no end-to-end job. | `.github/workflows/ci.yml` | Regressions in 12 test files go unnoticed | T9 |
| **V12** | **Frontend Docker image is unchanged** and still runs the dev server. | `frontend/Dockerfile` | Not deployable as is (ops only; UI itself is out of scope) | T9 |
| **V13** | **Topology "discovery" reads a bundled static file** (`data/target_compose.yml`), not the monitored system. | `adapters/topology.py` | Fine for the demo; not discovery of a real target | T10 |

**What is good and should be kept:** persisted `AuditLog` idempotency, the `ExecutionReceipt` and audit hash, the refuse-cleanly pattern for unconfigured executors, async approval with streamed verification samples, the resolver abstraction, honest `demo_target` labelling, constant-time HMAC compare, persisted dedupe, role hierarchy, and the 10 tests in `test_realtime.py` (HMAC, dedupe, event-bus resume, fault injection, idempotency, tenancy and roles, topology, GitHub mapping).

---

## 3. Real-time readiness against the acceptance flow

| Step | What must happen | Status | Why |
|---|---|---|---|
| 1 | Break a service; Prometheus scrapes it; an alert fires | **Built, unverified** | Compose, scrape config, and rules exist. Rule 1 labelled "p95" is a mean |
| 2 | Signed webhook opens an incident; UI streams events in under 2 s | **Built, breaks under a secret** | 202 plus SSE exist; Alertmanager cannot sign (V3); stream is unauthenticated (V2) |
| 3 | Evidence cites metrics pulled from Prometheus at alert time | **Partial** | Adapter wired into evidence; PromQL returns nothing for the demo target, so it falls back to `demo_target` values (V4); failures are silent (V6) |
| 4 | Approve; executor acts; target recovers; Slack notified | **Built** | Sandbox restores the target; Slack and GitHub need per-tenant config (V9) |
| 5 | Verification polls real samples over a window | **Partial** | 3 samples in about 0.15 s; default-resolved paths (V5) |
| 6 | Outcome recorded from observation; a later alert is handled differently | **Unproven** | Mechanism exists; benchmark claim is on n=5 (V10) |
| 7 | Restart mid-incident; UI resumes | **Built, unverified** | Events persisted with `Last-Event-ID`; dedupe persisted; confirm run state survives a restart |

---

## 4. Feature inventory (updated)

| # | Feature | Status |
|---|---|---|
| 1 | Tenant graphs, temporal edges, tools, hypotheses, memory, counterfactual, Q&A, trace, MCP | Present |
| 2 | Async incident execution (202 plus background) and async approval | Present |
| 3 | Live event stream with resume | Present (unauthenticated, V2) |
| 4 | Webhook HMAC, persisted dedupe, production fail-closed | Partial (Alertmanager cannot sign, V3) |
| 5 | API keys, roles, cross-tenant block | Present (dev fallback and published keys, V1) |
| 6 | Telemetry resolver, Prometheus adapter with range queries, honest labels | Present (global, off by default, V7) |
| 7 | Live metrics feeding evidence | Partial (V4, V6) |
| 8 | Deployment adapter feeding `recent_changes` | Present |
| 9 | Prometheus plus Alertmanager in Compose with rules | Present (V3, V4) |
| 10 | Executors: Slack, GitHub dispatch, sandbox, with persisted idempotency and audit | Present (global settings, V9) |
| 11 | Rollback heals demo target | Present |
| 12 | Verification from metrics | Partial (V5) |
| 13 | Real GitHub ingestion with CODEOWNERS, PR files, deployments | Partial (V8) |
| 14 | Topology from a target manifest | Partial (V13) |
| 15 | LLM tool results change evidence | Partial (two tool types) |
| 16 | CI | Partial (2 of 14 test files, V11) |
| 17 | Benchmark with honest, sufficient sample | **Missing** (V10) |
| 18 | End-to-end test of the full flow | **Missing** |
| 19 | Per-tenant integration settings | **Missing** (V9) |

---

## 5. Real vs demo audit (updated)

**A** = real and live. **B** = real logic on simulated or demo input. **C** = synthetic.

| Feature | Category | Notes |
|---|---|---|
| Alert intake | **A/B** | Works with an unset secret; breaks under a secret (V3) |
| Event streaming | **A** | No auth (V2) |
| Agent steps | **A** | |
| Graph reasoning | **A** | |
| Metrics in investigation | **B** | Adapter wired; demo target path falls back (V4); `simulator` by default |
| Deployments | **B/A** | Adapter wired; real only with GitHub config |
| Rollback on demo target | **B** | Real state change on a simulated target |
| Rollback on real systems | **A (when configured)** | GitHub dispatch to a configured repo and workflow |
| Slack | **A (when configured)** | Global webhook |
| Verification | **B** | Quick samples, default-resolved risk |
| PRs and issues | **C** by default, **A/B** with a repo configured | V8 |
| Topology | **B** | Static target file |
| Memory benefit | **B, unproven** | n=5 |
| Auth and tenancy | **A/B** | Dev fallback; published keys |

---

## 6. Plan to finish (backend and integrations only)

Estimates assume heavy AI-assisted coding. Order matters.

### T1: Make live metrics truly live, and never silent (4 hrs)
- **Make the demo target scrapeable by PromQL.** Run a small traffic simulator thread that **increments** counters and histogram buckets over time, with latency and error behavior driven by the `broken` state. Then `rate()` and `histogram_quantile()` return real values.
- **Fix the alert rules.** Use real p95 (`histogram_quantile(0.95, sum(rate(..._bucket[1m])) by (service, le))`) and the error ratio from `rate()`, so the rule names match what they compute.
- **No silent failures.** Replace `except Exception: pass` in `evidence.py` with a logged warning, a `telemetry_degraded` flag on the incident, and an event (`telemetry_degraded`) so consumers see it. When live data is unavailable, say so in the evidence rather than quietly using seeded rows.
- **Per-tenant telemetry config.** Store `telemetry_source` per tenant (graph node or settings table). Make `get_adapter(tenant_id)` use it. Make `demo_target` and `prometheus` distinct adapters.
- **Acceptance:** with Prometheus up, evidence rows show `real` and values match `curl` against the Prometheus API; with it down, rows say `demo_target` or "no data" and a `telemetry_degraded` event appears. A test covers each case.

### T2: Make the webhook work with Alertmanager and security on (2 hrs)
- Alertmanager cannot HMAC a body. Add a second accepted mode: a shared bearer token (`http_config.authorization.credentials` in `alertmanager.yml`) checked in constant time. Keep HMAC for senders that can sign.
- Put the token in an environment variable referenced by both the Compose file and Ripple. Remove the fixed `alerts_dev_signature` header.
- Keep the production rule: refuse to start without a secret or token.
- **Acceptance:** with `WEBHOOK_SECRET` or `WEBHOOK_TOKEN` set, a real Alertmanager alert opens an incident; a request without the credential gets 401. Test with the actual Alertmanager container.

### T3: Close the remaining auth gaps (3 hrs)
- **Protect the stream.** Require a key or a short-lived signed stream token (query parameter, since `EventSource` cannot set headers) and check that the incident belongs to the caller's tenant before subscribing. Keep `Last-Event-ID` resume.
- **Remove published keys.** Load initial keys from environment variables or a seed file outside source control; delete the plaintext key comments. In production, refuse to start if any default key is still registered.
- **Persist keys.** Store hashed keys in the graph (or a small file or table) so `register_api_key` survives restarts. Add revoke.
- **Tighten dev mode.** Make the no-key admin fallback an explicit `AUTH_DEV_MODE=true`, off by default.
- **Acceptance:** a tenant-A token cannot stream tenant B's incident (403); a restart keeps registered keys; production refuses default keys.

### T4: Verification you can trust (3 hrs)
- **Real window.** Poll for a configurable window (for example 60 to 120 seconds, step 10 seconds), publishing each `verification_sample` as it arrives. Run it in the background task, not a blocking call.
- **Compare to baseline.** Use the pre-incident baseline stored on the incident and require recovery relative to it (for example, within 20% of baseline error rate and latency), with absolute floors.
- **Remove the default-resolved paths.** If no telemetry branch matches, or the simulator raises, set `observed="inconclusive"`, record that, and do **not** close the incident as resolved or update runbook counts.
- **Memory updates only from conclusive outcomes** (`resolved`, `partial`, `failed`).
- **Acceptance:** a correct fix on the demo target resolves after the window; a wrong fix fails; with Prometheus down the outcome is `inconclusive` and memory is unchanged.

### T5: Finish GitHub ingestion correctness (4 hrs)
- Follow `Link` header pagination for contributors, PRs, issues, and deployments, with ETags and rate-limit handling (back off on 403 and 429).
- Put the path-to-service table and keyword hints in **configuration per tenant**, not in source. Prefer changed-file paths first; use keyword matching only as a last resort, with **whole-word** matching (this fixes the `"ad"` problem) and an `unmapped` label rather than guessing.
- Cache PR file lists so one sync does not make one request per PR every time; cap and report if limits are hit.
- Do not fall back to "now" for `merged_at`; skip or mark the record if the date is missing.
- Mark each record `source='real'` and show a last-synced time; report clearly when a fetch fails.
- **Acceptance:** counts match the repository; a PR touching `src/paymentservice/` maps to `paymentservice`; a PR titled "add loading spinner" does not map to `adservice`.

### T6: Per-tenant integration settings (3 hrs)
- Store per tenant: Slack webhook URL, GitHub repo, workflow file, ref, telemetry source and Prometheus URL, GitHub token reference. Keep secrets out of logs; store references or encrypt at rest.
- Admin-only endpoints to set them and a **test-connection** endpoint for each (Slack test message, GitHub API ping, Prometheus query).
- Executors and notifications read these settings instead of global ones; `workflow` and `ref` are no longer hard-coded.
- **Acceptance:** two tenants send Slack messages to different webhooks and dispatch to different repos; an unconfigured tenant gets a clean refusal.

### T7: Benchmark you can defend (4 hrs)
- **Revert the claims.** Remove "Calibration PASSED" and the "+20%" headline until the sample supports them. Say the sample is 5 scenarios and one scenario differs.
- **Re-register labels.** The runner and responder changed after the labels commit. Commit labels **before** any new run and record that hash.
- **Grow the sample.** At least 12 scenarios across the five families, 3 repeats each, memory ON and OFF. Add live-LLM runs for the investigator and responder, kept separate from the deterministic pipeline and labelled.
- **Calibration check only with enough data** (state the minimum, for example 30 runs).
- **Explain the unsafe cases.** Show which scenario is unsafe in both modes, why, and what was changed.
- **Acceptance:** the report states a measured effect with sample size, or says plainly that no effect was found; every number is reproducible from the saved run files.

### T8: LLM live mode consistency (3 hrs)
- Use `llm_provider` on every route (incident, webhook, approve, ask) instead of "any key present".
- Convert more tool results into evidence (`path_between`, `upstream_suspects`, `similar_incidents`), each tagged with its true source.
- Surface a `llm_degraded` event and field when a provider call fails, matching `telemetry_degraded`.
- Record the replay cache from real live runs, labelled "replay".
- **Acceptance:** two different alerts give different tool sequences and different evidence in live mode.

### T9: Tests, CI, and an end-to-end script (4 hrs)
- Run **all** test files in CI (`pytest` over `tests/`), against the FalkorDB service container.
- Add an end-to-end script (usable locally and in CI) that: starts Compose, breaks the demo target, waits for the Alertmanager alert, asserts the incident opens, asserts SSE events arrive in order with timestamps, approves, asserts the target recovers, asserts the outcome is recorded, restarts the backend mid-run, and asserts resume.
- Production images: serve the built frontend as static files instead of `npm run dev` (deployment only, no UI changes).
- Load test: a few dozen concurrent incidents across two tenants, checking for duplicate nodes and lost writes.
- **Acceptance:** CI green on a clean clone, including the end-to-end job.

### T10: Beyond the demo target (post-hackathon)
- Fetch manifests or compose files from the **monitored repo** (via GitHub) instead of the bundled static file; optionally accept OpenTelemetry trace edges. Mark edges `verified` only when observed.
- A tenant onboarding API: connect GitHub, set path-to-service mapping, add the webhook, point at a Prometheus, run a test alert, and report what is real vs seeded.
- Real executors beyond GitHub dispatch (Kubernetes rollout undo against a sandbox cluster).

---

## 7. Schedule

About 36 hours remain. The backend plan above is about 34 hours; the hackathon cut is about 21 hours, leaving time for the submission package.

### Hackathon cut

| Order | Work | Hours | Gate |
|---|---|---|---|
| 1 | T1 live metrics and no silent failures | 4 | Prometheus-up and Prometheus-down tests pass |
| 2 | T2 Alertmanager works under a secret or token | 2 | Real Alertmanager alert opens an incident with security on |
| 3 | T4 verification window and no default-resolved | 3 | Correct fix resolves, wrong fix fails, no data is inconclusive |
| 4 | T3 minimum: authenticate the stream, remove published keys, persist keys | 2 | Cross-tenant stream returns 403 |
| 5 | T7 benchmark honesty (revert claims, re-register labels, rerun) | 3 | Report matches the data |
| 6 | T9 end-to-end script and full-suite CI | 4 | End-to-end passes locally |
| 7 | T6 minimum: per-tenant Slack URL and GitHub repo/workflow | 1.5 | Two tenants, two destinations |
| 8 | Demo video, README, submission | 3 | Submitted early on Oct 18 |

If time is short, reduce depth in this order: T8, then T5 (keep the labelled sample dataset), then extra benchmark repeats. **Do not drop:** T1, T2, T4, the stream auth fix, or the honest benchmark report.

### After the hackathon
T5 in full, T6 in full, T8, the load test, T10.

---

## 8. Definition of done

- [ ] With a webhook secret or token set, a real Alertmanager alert opens an incident in under 2 seconds
- [ ] The event stream requires authorization and rejects cross-tenant access
- [ ] Evidence for hypotheses comes from live Prometheus data and is labelled `real`; fallbacks are labelled `demo_target` or "no data" and raise a degraded event, never a silent swap
- [ ] The demo target emits counters that increase, and the alert rules compute what they claim
- [ ] A rollback heals the target; verification polls a real window against a baseline
- [ ] Missing or failing telemetry yields `inconclusive`, never `resolved`, and memory is untouched
- [ ] Executors and notifications use per-tenant settings; unconfigured tenants are refused cleanly
- [ ] No default or published API keys work in production mode
- [ ] The benchmark report states sample size, uses labels committed before the run, and makes no claim the data cannot support
- [ ] CI runs the full test suite and an end-to-end flow that includes a mid-incident restart

---

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Traffic simulator and PromQL tuning take longer than planned | T1 slips | Keep the labelled `demo_target` fallback; add a unit test for the query shapes first |
| Alertmanager config differences between versions | T2 stalls | Pin the image tag; test against the container, not by reading docs |
| Removing the dev auth fallback breaks local runs | Slow development | `AUTH_DEV_MODE=true` for local only; documented in `.env.example` |
| Longer verification windows slow the demo | Flat video | Make the window configurable; use a short window for the demo and state it |
| Rerunning the benchmark shows no memory benefit | Weak headline | Report it honestly and lead with the stale-fix block and safe recommendations |
| Scope too large | Unfinished | Follow the hackathon cut and the stated drop order |

---

*This review is based on reading the uploaded code. The backend, tests, Docker stack, Prometheus, Alertmanager, and all external integrations were not run in this review.*

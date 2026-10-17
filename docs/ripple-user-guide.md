# Ripple Complete User & Operator Guide

> **Autonomous SRE Incident Response Platform with FalkorDB Graph Memory**  
> Complete operational manual for setting up, configuring, running, and mastering Ripple in real time.

---

## Table of Contents

1. [Introduction & Core Concept](#1-introduction--core-concept)
2. [System Architecture](#2-system-architecture)
3. [Prerequisites & Quickstart](#3-prerequisites--quickstart)
4. [Configuration & Multitenant Security](#4-configuration--multitenant-security)
5. [End-to-End Operational Walkthrough](#5-end-to-end-operational-walkthrough)
   - [Phase 1: Topology Exploration](#phase-1-topology-exploration)
   - [Phase 2: Triggering Alerts & Fault Injection](#phase-2-triggering-alerts--fault-injection)
   - [Phase 3: Live Incident War Room & Streaming SSE](#phase-3-live-incident-war-room--streaming-sse)
   - [Phase 4: Action Safety Gate & Approval](#phase-4-action-safety-gate--approval)
   - [Phase 5: Closed-Loop Metric Verification](#phase-5-closed-loop-metric-verification)
   - [Phase 6: Unified Graph Memory & Lifelong Learning](#phase-6-unified-graph-memory--lifelong-learning)
   - [Phase 7: Company Brain Q&A & Counterfactual What-If](#phase-7-company-brain-qa--counterfactual-what-if)
   - [Phase 8: Benchmarking & Scientific Evaluation](#phase-8-benchmarking--scientific-evaluation)
6. [API Endpoint Reference](#6-api-endpoint-reference)
7. [Telemetry & Honest Source Attribution](#7-telemetry--honest-source-attribution)
8. [Troubleshooting & FAQ](#8-troubleshooting--faq)

---

## 1. Introduction & Core Concept

**Ripple** is an autonomous SRE on-call agent platform designed to triage, investigate, remediate, and verify production incidents in real time. Unlike traditional LLM chatbots that hallucinate root causes from raw logs, Ripple anchors all reasoning in a high-speed **FalkorDB** graph.

### Why Graph-Powered SRE?
- **Topology-Grounded Traversal:** Real microservices fail along causal dependency paths (`CALLS`, `OWNS`, `DEPENDS_ON`). Ripple walks these edges to determine the exact blast radius.
- **Evidence-Weighted Hypotheses:** Competing hypotheses are generated and scored against live metrics, recent deployments, and architecture changes.
- **Unified Memory with Stale-Fix Protection:** Remembers every past incident, whether the applied fix actually worked, and automatically rejects stale runbooks if the underlying architecture has changed.
- **Closed-Loop Verification:** Executes remediation actions through hardened, idempotent executors and continuously polls live metrics to verify recovery before closing an incident.

### The 4-Agent Crew

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             THE 4-AGENT CREW                                │
├───────────────┬───────────────────┬────────────────────┬────────────────────┤
│ 1. TRIAGE     │ 2. INVESTIGATOR   │ 3. RESPONDER       │ 4. VERIFIER        │
├───────────────┼───────────────────┼────────────────────┼────────────────────┤
│ • Ingests alert│ • Traverses graph │ • Recalls runbooks │ • Polls post-fix   │
│ • Maps target │ • Collects live   │ • Checks topology  │   metrics          │
│   service     │   metrics/deploys │   applicability    │ • Compares against │
│ • Computes    │ • Ranks competing │ • Dispatches to    │   baseline         │
│   blast radius│   hypotheses      │   Slack/GitHub     │ • Decides outcome  │
│ • Detects     │ • Flags margin    │ • Waits for human  │ • Updates Laplace  │
│   symptom type│   conflicts       │   gate approval    │   outcome priors   │
└───────────────┴───────────────────┴────────────────────┴────────────────────┘
```

---

## 2. System Architecture

```
                  ┌────────────────────────────────────────────┐
                  │          React UI (Port 5173)              │
                  │  Live War Room · Graph Canvas · Hypotheses │
                  │  Memory Panel · What-If · Benchmark Tab    │
                  └──────────────────────┬─────────────────────┘
                                         │ REST + SSE (13 Event Types)
                  ┌──────────────────────▼─────────────────────┐
                  │        FastAPI Backend (Port 8000)         │
                  │  Auth & Tenancy · Event Bus · Orchestrator │
                  └───────┬──────────────┬──────────────┬──────┘
                          │              │              │
           ┌──────────────▼───┐  ┌───────▼──────┐  ┌────▼──────────────┐
           │ Telemetry        │  │ Action       │  │ FalkorDB Brain    │
           │ Adapters         │  │ Executors    │  │ (Port 6379)       │
           ├──────────────────┤  ├──────────────┤  ├───────────────────┤
           │ • Prometheus     │  │ • Sandbox    │  │ • Tenant Graphs   │
           │ • Demo Target    │  │ • Slack      │  │ • Temporal Edges  │
           │ • Deployments    │  │ • GitHub     │  │ • Memory Pointers │
           │ • Topology       │  │   Dispatch   │  │ • Audit Receipts  │
           └──────────────────┘  └──────────────┘  └───────────────────┘
```

---

## 3. Prerequisites & Quickstart

### Prerequisites
- **Docker & Docker Compose** (v2.20+) OR
- **Python 3.11+** with `uv` package manager and **Node.js 20+** with `npm`

### Option A: Running with Docker Compose (Recommended)

Start the complete stack including FalkorDB, Backend, Frontend, Prometheus, and Alertmanager:

```bash
# 1. Clone the repository
git clone https://github.com/Vishallakshmikanthan/ripple.git
cd ripple

# 2. Start all containers
docker compose up -d --build

# 3. Verify services are healthy
docker compose ps
```

**Service URL Directory:**
| Service | URL | Purpose |
|---|---|---|
| **Web Console** | `http://localhost:5173` | Interactive SRE War Room & Graph Visualizer |
| **Backend API** | `http://localhost:8000` | REST API, SSE streaming, webhook intake |
| **API Docs (Swagger)** | `http://localhost:8000/docs` | Interactive OpenAPI documentation |
| **FalkorDB Browser** | `http://localhost:3000` | Redis/Cypher graph management console |
| **Prometheus** | `http://localhost:9090` | Metrics scraping and query engine |
| **Alertmanager** | `http://localhost:9093` | Alert routing and webhook dispatch |

### Option B: Local Development Setup

If running natively on your workstation:

```bash
# 1. Start FalkorDB in Docker
docker run -d --name ripple-falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest

# 2. Start Backend (in backend/)
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start Frontend (in frontend/)
cd ../frontend
npm install
npm run dev
```

---

## 4. Configuration & Multitenant Security

### Environment Variables (`.env`)

Configure the backend via environment variables or a `.env` file in `backend/`:

```bash
# Environment Mode: 'development' or 'production'
ENVIRONMENT=development

# FalkorDB Connection
FALKORDB_HOST=localhost
FALKORDB_PORT=6379

# Webhook Security (Mandatory in production)
WEBHOOK_SECRET=alerts_dev_signature

# LLM Provider Configuration ('openai', 'anthropic', or 'mock')
LLM_PROVIDER=mock
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Telemetry & Monitoring Integrations
PROMETHEUS_URL=http://localhost:9090
TELEMETRY_SOURCE=demo_target

# Remediation & Notification Integrations
SLACK_WEBHOOK_URL=
GITHUB_TOKEN=
GITHUB_REPO=
```

### Multitenant Isolation & RBAC Roles

Every tenant in Ripple operates within its own completely isolated FalkorDB graph (`tenant_<tenant_id>`). Cross-tenant access is strictly blocked at the security layer (HTTP 403 Forbidden).

#### Role Hierarchy:
1. **`viewer`**: Read-only access. Can inspect service graphs, view open incidents, read hypotheses, and query the Company Brain.
2. **`responder`**: Operational access. Can approve or reject remediation actions, inject demo faults, and trigger incident triage.
3. **`admin`**: Full management access. Can register integrations, trigger repository sync, run graph re-embeddings, and bootstrap new tenant graphs.

#### Passing Authentication Credentials:
- **HTTP Headers:**
  ```http
  X-API-Key: your_api_key_here
  X-Tenant: storefront
  ```
- **SSE Stream Token (Query Param):** Because browser `EventSource` cannot pass custom request headers, supply the stream token as a query parameter:
  ```
  GET /api/incidents/inc_12345/stream?tenant=storefront&token=your_stream_token
  ```

---

## 5. End-to-End Operational Walkthrough

### Phase 1: Topology Exploration
Before handling alerts, explore your system's architecture in the Ripple UI:
1. Open `http://localhost:5173`.
2. Navigate to the **Services Graph** tab.
3. Inspect nodes representing services (`frontend`, `checkoutservice`, `paymentservice`, `cartservice`), databases (`redis-cart`), and external payment gateways.
4. Click on any service node to view:
   - **Active blast radius:** Downstream services that fail if this node goes down.
   - **Upstream suspects:** Upstream dependencies that could be starving this service.
   - **Assigned CODEOWNERS:** Engineers responsible for this service.
   - **Associated Runbooks:** Approved mitigation playbooks with historical success rates.

### Phase 2: Triggering Alerts & Fault Injection

Ripple supports three methods of alert intake:

#### Method A: Breaking the In-Process Demo Target (Interactive Testing)
Simulate a production outage on `paymentservice` with a single API call:
```bash
curl -X POST "http://localhost:8000/api/telemetry/demo/break?service=paymentservice&reason=connection_pool_exhausted"
```
This immediately:
- Drives `paymentservice` p95 latency to **1850ms** and HTTP 500 error rate to **85%**.
- Exposes Prometheus-compatible metrics at `/api/telemetry/demo/metrics`.

#### Method B: Alertmanager Signed Webhook
Prometheus scrapes the demo target, evaluates rules in `alert.rules.yml`, and triggers Alertmanager. Alertmanager delivers an HMAC-signed alert payload:
```bash
curl -X POST "http://localhost:8000/webhooks/alert" \
  -H "Content-Type: application/json" \
  -H "X-Ripple-Signature: sha256=alerts_dev_signature" \
  -d '{
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "ServiceHighLatency",
          "service": "paymentservice",
          "severity": "critical"
        },
        "annotations": {
          "summary": "High p95 latency on paymentservice (> 1000ms)"
        }
      }
    ]
  }'
```
*The endpoint returns `202 Accepted` and immediately dispatches the agent crew asynchronously.*

#### Method C: Replaying a Pre-Registered Scenario
Run a standardized incident scenario from the benchmark catalog:
```bash
curl -X POST "http://localhost:8000/api/scenarios/run?scenario_id=sc_repeated_01&tenant=storefront"
```

### Phase 3: Live Incident War Room & Streaming SSE

When an incident is opened, navigate to the **War Room** in the UI. Ripple streams all agent deliberations over Server-Sent Events (`/api/incidents/{incident_id}/stream`):

#### The 13 Streaming Event Types:
1. `incident_opened`: Alert ingested, incident ID assigned.
2. `agent_started`: Active agent takes the blackboard (`triage`, `investigator`, `responder`, `verifier`).
3. `tool_called`: Agent invokes a graph tool (e.g. `service_health`, `recent_changes`, `path_between`).
4. `tool_result`: Output received with cryptographic provenance trace.
5. `hypotheses_updated`: Candidates ranked with supporting and contradicting evidence.
6. `conflict_detected`: Margin between top hypotheses is < 0.10, triggering tie-breaking investigation.
7. `action_recommended`: Responder identifies optimal runbook and tests topology applicability.
8. `action_executed`: Approved action executed via Sandbox, Slack, or GitHub Dispatch.
9. `verification_sample`: Real-time post-mitigation metric sample polled.
10. `outcome_verified`: Final verdict (`resolved`, `partial`, `failed`) and baseline comparison.
11. `memory_updated`: Laplace outcome prior updated in FalkorDB.
12. `agent_completed`: Agent finishes turn.
13. `incident_closed`: Incident resolved and postmortem receipt generated.

#### Monotonic Sequence & Reconnect Resilience:
If your browser loses connection or the backend restarts mid-incident, the client automatically sends:
```http
Last-Event-ID: inc_12345_7
```
Ripple replays all events monotonically starting from sequence 8, ensuring zero lost updates.

### Phase 4: Action Safety Gate & Approval

Ripple enforces human-in-the-loop control for destructive production interventions.
1. The **Responder Agent** evaluates candidate runbooks against live graph topology.
2. In the War Room, an **Approval Card** appears detailing:
   - **Recommended Runbook:** e.g., `rb_rollback` (Rollback bad deployment) or `rb_restart` (Restart container).
   - **Target Service:** e.g., `paymentservice`.
   - **Safety Mode:** `dry_run` (simulated execution) or `live`.
   - **Idempotency Key:** SHA-256 fingerprint preventing duplicate executions.
3. Click **Approve** (or call `/approve` via API with `responder` role):
```bash
curl -X POST "http://localhost:8000/api/incidents/inc_12345/actions/act_001/approve" \
  -H "X-API-Key: your_responder_key" \
  -H "Content-Type: application/json" \
  -d '{"approver": "sre_alice", "dry_run": false}'
```

#### What Happens on Approval:
- **Sandbox Executor:** Calls `restore_service("paymentservice")` on the demo target, restoring normal latency and 0% errors.
- **Slack Executor:** Posts an incident notification and action receipt to your configured Slack channel.
- **GitHub Dispatch Executor:** Dispatches `workflow_dispatch` to your repository's rollback action.
- **Idempotency Check:** Re-submitting the same approval instantly returns `idempotent_skip`, guaranteeing safe retries.

### Phase 5: Closed-Loop Metric Verification

Unlike systems that assume a command succeeded because it returned HTTP 200, Ripple's **Verifier Agent** validates recovery over time:
1. Samples post-mitigation metrics over a configurable window.
2. Compares live metrics against the pre-incident baseline:
   - Target Latency: $\le 120\%$ of baseline.
   - Target Error Rate: $< 1.0\%$.
3. When metrics normalize, the Verifier emits `outcome_verified` with status `resolved`.
4. If an incorrect runbook was approved, metrics remain degraded, recording status `failed` and training Ripple's memory to avoid that mistake in the future.

### Phase 6: Unified Graph Memory & Lifelong Learning

Ripple maintains three distinct memory layers in FalkorDB:

1. **Episodic Memory:**
   - Stores raw incident trajectories, symptoms, and resolution paths.
   - Vector-indexed in FalkorDB for similarity recall during new incidents.
2. **Semantic Memory:**
   - Stores architectural facts, service ownership, and communication contracts.
   - Automatically updated when architecture changes occur (e.g. cache decouplings).
3. **Procedural Memory with Laplace Smoothing:**
   - Tracks how often each runbook succeeded for specific root causes:
     $$\hat{p} = \frac{\text{successes} + 1}{\text{trials} + 2}$$
   - When a runbook succeeds, its prior increases; when it fails, its prior drops.

#### Stale-Fix Protection (The Stale-Trap Test)
Suppose `cartservice` previously solved deadlocks via `rb_cache_flush` on Redis. If the architecture is updated to decouple Redis from `cartservice`, applying `rb_cache_flush` would be useless or dangerous. Ripple's **Applicability Filter** checks the live graph, detects that the dependency edge no longer exists, rejects `rb_cache_flush`, and selects `rb_restart` instead!

### Phase 7: Company Brain Q&A & Counterfactual What-If

#### Asking Architectural Questions (`/ask`)
Query your organization's collective engineering knowledge:
```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Why did paymentservice fail last Tuesday and who owns it?"}'
```
*Ripple traverses historical incident nodes, commit records, and CODEOWNERS, citing exact node IDs and timestamps in its response.*

#### Counterfactual What-If Simulation
Simulate cascading failures before they happen in production:
```bash
curl -X POST "http://localhost:8000/api/counterfactual" \
  -H "Content-Type: application/json" \
  -d '{
    "hypothetical_failure_service": "redis-cart",
    "traffic_multiplier": 2.5
  }'
```
*Returns the predicted failure cascade, impacted upstream services, and suggested preemptive runbooks.*

### Phase 8: Benchmarking & Scientific Evaluation

Ripple includes a pre-registered benchmark runner comparing **Memory ON vs Memory OFF** across 5 scenario families:

```bash
# Execute benchmark suite
curl -X POST "http://localhost:8000/api/benchmark/run"

# Retrieve latest evaluation report
curl "http://localhost:8000/api/benchmark/report"
```

The benchmark evaluates:
- `repeated`: Incidents with identical historical counterparts (Memory recalls proven fixes).
- `variant`: Cross-service pattern variants (testing cross-service generalization).
- `novel`: Unseen failure modes (relying on raw graph traversal).
- `stale_trap`: Architecture changes where historical fixes are now obsolete.
- `misleading_memory`: Incidents where surface symptoms resemble unrelated past outages.

---

## 6. API Endpoint Reference

### System & Health
| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/health` | `GET` | Public | Backend liveness and Redis connection check |
| `/api/system/status` | `GET` | Viewer | Active telemetry source, LLM status, and adapter states |
| `/metrics` | `GET` | Public | Prometheus exposition format metrics for Ripple |

### Incidents & Live Streaming
| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/webhooks/alert` | `POST` | Public (Signed) | Alertmanager HMAC-signed webhook receiver (Returns 202) |
| `/api/incidents` | `POST` | Responder | Manually open an incident from an alert payload |
| `/api/incidents/{id}/stream` | `GET` | Viewer | Monotonic SSE stream supporting `Last-Event-ID` resume |
| `/api/incidents/{id}/actions/{act_id}/approve` | `POST` | Responder | Asynchronously approve and execute a remediation action |
| `/api/incidents/{id}/actions/{act_id}/reject` | `POST` | Responder | Reject a proposed remediation action |

### Telemetry & Demo Target
| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/telemetry/demo/break` | `POST` | Responder | Inject high latency and 5xx errors into a demo service |
| `/api/telemetry/demo/restore` | `POST` | Responder | Manually restore healthy state on a demo service |
| `/api/telemetry/demo/metrics` | `GET` | Public | Scrapeable Prometheus text format metrics for demo target |

### Memory, Knowledge & What-If
| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/ask` | `POST` | Viewer | Natural language Company Brain Q&A with graph provenance |
| `/api/counterfactual` | `POST` | Viewer | Simulate hypothetical cascading failures and blast radius |
| `/api/benchmark/run` | `POST` | Admin | Execute Memory-ON vs Memory-OFF evaluation suite |
| `/api/benchmark/report` | `GET` | Viewer | Get latest benchmark results and Markdown report |

### Integrations & Admin
| Endpoint | Method | Role | Description |
|---|---|---|---|
| `/api/integrations/settings` | `GET/POST` | Admin | Read or update tenant Slack, GitHub, and Prometheus configs |
| `/api/audit/logs` | `GET` | Viewer | Query immutable execution audit receipts |
| `/api/topology/discover` | `POST` | Admin | Discover services and dependencies from target compose files |

---

## 7. Telemetry & Honest Source Attribution

To ensure complete transparency and scientific rigor, every metric, deployment, and evidence item in Ripple carries an authentic source attribution badge:

| Badge | Meaning | Origin |
|---|---|---|
| `source="real"` | Authentic Live Data | Queried from an external Prometheus server, real GitHub REST API, or live container runtime. |
| `source="demo_target"` | In-Process Fault Simulator | Generated by Ripple's simulated microservice target during interactive demo scenarios. |
| `source="discovered"` | Topology Discovery | Discovered by parsing target environment manifests and container configurations. |
| `source="seeded"` | Seeded Ground-Truth | Pre-registered benchmark test fixtures and historical seed incidents. |
| `source="synthetic"` | Offline Fallback | Generated synthetically when operating without external credentials or offline. |

---

## 8. Troubleshooting & FAQ

### 1. FalkorDB connection fails on startup
- **Symptom:** Logs show `ConnectionRefusedError: [Errno 111] Connect call failed ('localhost', 6379)`.
- **Solution:** Verify the FalkorDB container is running:
  ```bash
  docker ps | grep falkordb
  docker compose up -d falkordb
  ```
  *Note: Ripple includes a built-in offline graph fallback that allows unit tests and demo runs to operate gracefully even if FalkorDB is offline.*

### 2. Webhook returns 401 Unauthorized
- **Symptom:** Alertmanager alerts are rejected with `Invalid or missing webhook signature`.
- **Solution:** In production mode, requests must supply the HMAC SHA-256 signature in the `X-Ripple-Signature` header matching `WEBHOOK_SECRET`. For local testing, ensure `WEBHOOK_SECRET` is unset or matches your test header.

### 3. Cross-Tenant 403 Forbidden
- **Symptom:** Request returns `API key for tenant 'X' cannot access tenant 'Y'`.
- **Solution:** Supply an API key belonging to tenant `Y`, or use a master `admin` role key that has global cross-tenant authorization.

### 4. GitHub dispatch returns "refused"
- **Symptom:** Action execution receipt has status `refused` and notes `No GitHub repository configured`.
- **Solution:** Configure your tenant's GitHub repository and token via `POST /api/integrations/settings`:
  ```json
  {
    "github_repo": "your-org/your-service-repo",
    "github_token": "ghp_xxxxxxxxxxxx"
  }
  ```

---

*Ripple — Graph Hacks: Context for AI Agents (WeMakeDevs x FalkorDB)*

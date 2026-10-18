# Ripple

> **On-Call Autonomous Agent Crew with FalkorDB Brain**  
> *Graph Hacks: Context for AI Agents (WeMakeDevs x FalkorDB)* · Solo build

Ripple is an on-call agent crew that uses **FalkorDB** as its brain. It follows real service dependencies to find the blast radius, forms competing hypotheses and ranks them with supporting and contradicting evidence, remembers every incident *and whether the fix actually worked*, coordinates through a shared graph, answers "what if X had failed instead?", and shows the exact subgraph path, nodes, and Cypher behind every answer.

---

## ⚡ Quick Start & Real-Time Run Guide

You can run Ripple either using **Docker Compose** (all-in-one) or by running the services individually for local development.

### Option A: All-in-One via Docker Compose

```bash
# 1. Clone repository & navigate to root
git clone https://github.com/Vishallakshmikanthan/ripple.git
cd ripple

# 2. Configure environment file
cp .env.example .env
# Edit .env with your keys (see Credentials Guide below)

# 3. Start all services via Docker Compose
docker compose up -d --build

# 4. Open applications
# Web UI:            http://localhost:5173
# FalkorDB Browser:  http://localhost:3000
# FastAPI Docs:      http://localhost:8000/docs
# Health Check:      http://localhost:8000/api/health
```

---

### Option B: Step-by-Step Local Run

If developing locally without running everything inside containers:

#### Step 1: Start FalkorDB
```bash
docker run -d --name ripple-falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
```
*Port `6379` serves the FalkorDB graph engine; port `3000` serves the FalkorDB web visualizer.*

#### Step 2: Start the FastAPI Backend
```bash
# In project root:
uv run --directory backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*The backend automatically bootstraps the tenant schemas in FalkorDB and starts the background traffic simulator.*

#### Step 3: Start the Vite Frontend
```bash
cd frontend
npm install
npm run dev
```
*Frontend runs on `http://localhost:5173` with real-time SSE streaming connected to `http://localhost:8000`.*

#### Step 4: Verify System Health
```bash
curl http://localhost:8000/api/health
# Expected: {"status":"ok","falkordb":"connected",...}
```

---

## 🔑 How to Get & Configure Required Credentials

Add these values to your `.env` file or enter them in the **Integrations** tab in the UI:

### 1. Webhook Authentication Secret (`WEBHOOK_SECRET` & `WEBHOOK_TOKEN`)
- **What it is:** A shared secret string you define to authenticate incoming alert webhooks from GitHub, Alertmanager, or custom monitoring.
- **How to generate it:** Run one of the commands below in your terminal:
  ```bash
  # Using Python:
  python -c "import secrets; print(secrets.token_hex(24))"
  # Or using OpenSSL:
  openssl rand -hex 24
  ```
- **How to use it:**
  - Put this value into `WEBHOOK_SECRET` in `.env`.
  - For **GitHub webhooks**: In your repository (`Settings -> Webhooks -> Add webhook`), paste this secret in the **Secret** field. GitHub will sign all payloads with `X-Hub-Signature-256`.
  - For **Alertmanager**: Ripple also provides `WEBHOOK_TOKEN=ripple_alertmanager_token_secret`. Alertmanager sends this as an HTTP `Authorization: Bearer <token>` header configured in `deploy/alertmanager/alertmanager.yml`.

### 2. Slack Webhook URL (`SLACK_WEBHOOK_URL`)
- **What it is:** An incoming webhook URL from your Slack workspace for automated incident notifications and responder action alerts.
- **How to get it:**
  1. Open [Slack API: Your Apps](https://api.slack.com/apps) and click **Create New App** (From scratch) or select an existing app.
  2. In the left sidebar, click **Incoming Webhooks**.
  3. Turn the switch **Activate Incoming Webhooks** to **On**.
  4. Scroll down and click **Add New Webhook to Workspace**.
  5. Select the channel where you want alerts posted (e.g., `#incidents` or `#alerts`) and click **Allow**.
  6. Copy the generated URL (it looks like `https://hooks.slack.com/services/T00/B00/XXXXX`).
  7. Paste it into `SLACK_WEBHOOK_URL` in `.env`.

### 3. Prometheus URL (`PROMETHEUS_URL`)
- **What it is:** The endpoint URL of your Prometheus metrics server for live telemetry queries.
- **How to get it:**
  - **Using bundled Docker Prometheus:** Run `docker compose up -d prometheus` (or start `prom/prometheus:latest`). The URL is `http://localhost:9090` (or `http://prometheus:9090` inside Docker).
  - **Using your existing Prometheus server:** Enter your server address, e.g., `http://192.168.1.100:9090` or `https://prometheus.yourdomain.com`.
  - **Running without Prometheus (Default):** If left blank or set to `simulator`, Ripple automatically runs its built-in traffic simulator and demo target exporter (`http://localhost:8000/metrics`) with zero external infrastructure needed.

### 4. GitHub Token & Monitored Repo (`GITHUB_TOKEN` & `GITHUB_REPO`)
- **Monitored Repository:** `GITHUB_REPO=Vishallakshmikanthan/ripple-demo-repo`
- **How to get a Token:**
  1. Go to [GitHub Settings -> Personal Access Tokens (Classic)](https://github.com/settings/tokens).
  2. Click **Generate new token (classic)**.
  3. Give it a descriptive name (e.g., `Ripple-OnCall-Token`).
  4. Select scopes:
     - `repo` (Full control of private repositories / access commit history, PRs, and manifests).
     - `workflow` (Required if using GitHub Actions workflow dispatch rollback actions).
  5. Click **Generate token**, copy the `ghp_...` token, and set `GITHUB_TOKEN=ghp_...` in `.env`.

### 5. LLM Provider API Keys (One required for live agent crew)
Set at least one of the following in `.env`:
- **NVIDIA NIM / Nemotron:** `NVIDIA_API_KEY=nvapi-...`
- **Google Gemini:** `GEMINI_API_KEY=AIzaSy...`
- **OpenAI:** `OPENAI_API_KEY=sk-...`
- **Anthropic:** `ANTHROPIC_API_KEY=sk-ant-...`
*(If no LLM key is configured, Ripple runs in deterministic offline replay mode with full provenance and graph traversal intact).*

---

## 🏗️ Architecture & Services

```
                 ┌────────────────────────────────────────────┐
                 │  React UI (Vite + TypeScript)              │
                 │  Port 5173                                 │
                 │  alert console · agent timeline · graph    │
                 │  hypothesis board · memory panel ·         │
                 │  counterfactual overlay · benchmark tab    │
                 └──────────────────┬─────────────────────────┘
                                    │ REST + SSE (live events)
                 ┌──────────────────▼─────────────────────────┐
                 │  FastAPI Backend (Port 8000)               │
                 │  tenant middleware · orchestrator · tools  │
                 └──┬───────┬────────┬────────┬────────┬──────┘
                    │       │        │        │        │
           ┌────────▼──┐ ┌──▼─────┐ ┌▼───────┐ ┌▼──────┐ ┌▼────────────┐
           │Orchestrator│ │Hypothe-│ │Brain   │ │Counter│ │Scenario     │
           │+ 3 agents  │ │sis &   │ │Q&A     │ │factual│ │simulator +  │
           │+ blackboard│ │evidence│ │(Trk 3) │ │engine │ │ingestion    │
           └─────┬──────┘ └──┬─────┘ └┬───────┘ └┬──────┘ └┬────────────┘
                 │ tool calls│        │          │         │
           ┌─────▼───────────▼────────▼──────────▼─────────▼──────┐
           │  Graph Tool Library + Memory Layer                   │
           │  (every call emits a provenance trace)               │
           └───────────────────────────┬──────────────────────────┘
                                       │ Cypher
                 ┌────────────────────▼───────────────────┐
                 │  FalkorDB (Ports 6379 & 3000)          │
                 │  Isolated graph per tenant:            │
                 │  tenant_storefront · tenant_payments   │
                 └─────────────────────────────────────────┘
```

---

## 📊 Requirements & Track Mapping

| Requirement | Where Ripple satisfies it | Modules |
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
| Track 3: knowledge from docs, tickets, chats | Docs, PRs, issues, decisions linked to services and people | M2, M8 |
| Track 3: who owns what, who knows what | Ownership and recency-weighted expertise | M4, M8 |
| Track 3: tracing decisions to source | `Decision -DERIVED_FROM-> PR/Issue/Doc`, citations | M8 |
| Track 3: keeping knowledge current | `SUPERSEDES`, freshness checks, stale flags, temporal edges | M6, M8 |
| Track 3: answers with clear sources | Every answer cites node IDs and URLs | M8, M10 |

---

## 🔬 Evidence Weighting Reference

| Evidence type | Default weight | Freshness half-life |
|---|---|---|
| `metric` (observed) | 3.0 | 1 hr |
| `recent_deploy` (observed) | 2.5 | 6 hr |
| `architecture_change` (observed) | 2.5 | 24 hr |
| `dependency_path` (observed) | 1.5 | no decay |
| `past_incident` (inferred, validated fix) | 2.0 | 30 days |
| `decision` / `doc` | 1.0 | 90 days |

---

## 🛡️ Honest Labelling: Real vs. Synthetic vs. Seeded Data

- **Real Data (`source='real'`):** Microservice topology discovered from live container and host environments, live GitHub commits and contributors via GitHub REST API, live Prometheus telemetry queries via adapter, and real audit log execution receipts.
- **Synthetic Data (`source='synthetic'`):** Fallback PR and issue records generated when running without a GitHub API token or in offline demo mode.
- **Seeded Data (`source='seeded'`):** Simulator incident scenarios, simulated deployment records, and benchmark test fixtures.

---

## 📈 Benchmark & Evaluation Results

Ripple was benchmarked across pre-registered scenarios with memory active vs disabled:

| Metric | Memory ON | Memory OFF | Delta / Benefit |
|---|---|---|---|
| **Diagnosis Correctness** | **80.0%** | 80.0% | Grounded graph traversal |
| **Recommendation Correctness** | **60.0%** | 40.0% | +20.0% (memory recall + applicability unlocks correct alternative actions) |
| **Unsafe Recommendation Rate** | **20.0%** | 20.0% | Blocks stale-fix traps via topology check |
| **Average Tool Calls** | 37.2 | 35.6 | Deep multi-hop graph inspection |
| **Average Execution Time** | 0.24s | 0.18s | In-memory FalkorDB latency |

Detailed protocol and per-scenario table: [docs/benchmark-report.md](file:///c:/Users/Lenovo/Downloads/Ripple/docs/benchmark-report.md) (Pre-registered commit: `29227d45ac0f414827fa5218df06c7188a6bc2ec`).

---

## 🔌 Model Context Protocol (MCP) Server

Ripple exposes all 11 graph tools through a standard MCP server for external agents (Cursor, Claude Desktop, Antigravity):

```json
{
  "mcpServers": {
    "ripple": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/path/to/ripple/backend"
    }
  }
}
```

---

## 📚 Documentation Package

- **Complete User & Operator Guide:** [`docs/ripple-user-guide.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/ripple-user-guide.md)
- **System Architecture & FalkorDB Blueprint:** [`docs/architecture.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/architecture.md)
- **Track & Requirements Mapping:** [`docs/track-mapping.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/track-mapping.md)
- **Interactive Demo Script:** [`docs/demo-script.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/demo-script.md)
- **Benchmark Evaluation Report:** [`docs/benchmark-report.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/benchmark-report.md)
- **License:** [MIT License](file:///c:/Users/Lenovo/Downloads/Ripple/LICENSE)

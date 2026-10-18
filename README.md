# Ripple

> **On-Call Autonomous Agent Crew with FalkorDB Brain**  
> *Graph Hacks: Context for AI Agents (WeMakeDevs x FalkorDB)* · Solo build

Ripple is an on-call agent crew that uses **FalkorDB** as its brain. It follows real service dependencies to find the blast radius, forms competing hypotheses and ranks them with supporting and contradicting evidence, remembers every incident *and whether the fix actually worked*, coordinates through a shared graph, answers "what if X had failed instead?", and shows the exact subgraph path, nodes, and Cypher behind every answer.

---

## 🌐 Live Deployments & Quick Links

| Service | Environment | URL | Description |
|---|---|---|---|
| **Production Web UI** | Vercel (Primary) | **[https://ripple-sre.vercel.app](https://ripple-sre.vercel.app)** | Real-time Orange SRE On-Call Web Console |
| **Mirror 1** | Vercel | **[https://ripple-intelligence.vercel.app](https://ripple-intelligence.vercel.app)** | High-availability production mirror |
| **Mirror 2** | Vercel | **[https://ripple-oncall.vercel.app](https://ripple-oncall.vercel.app)** | Live backup web domain |
| **Local Web UI** | Local Docker / Vite | **[http://localhost:5173](http://localhost:5173)** | Local reactive developer dashboard |
| **FastAPI Swagger Docs**| Local Backend | **[http://localhost:8000/docs](http://localhost:8000/docs)** | Interactive OpenAPI test console |
| **Backend Health Check**| Local / Cloud | **[http://localhost:8000/api/health](http://localhost:8000/api/health)** | Graph & service connectivity status |
| **FalkorDB Visualizer** | Local Engine | **[http://localhost:3000](http://localhost:3000)** | Graph topology and Cypher query explorer |
| **Prometheus Telemetry**| Local Monitor | **[http://localhost:9090](http://localhost:9090)** | Live service metrics & alerts |
| **Alertmanager UI** | Local Monitor | **[http://localhost:9093](http://localhost:9093)** | Alert routing and dispatch console |
| **Demo Repository** | GitHub | **[Vishallakshmikanthan/ripple-demo-repo](https://github.com/Vishallakshmikanthan/ripple-demo-repo)** | Monitored repo with live PRs and deployments |

---

## ⚡ Quick Start & Run Guide

You can run Ripple either using **Docker Compose** (all-in-one stack) or directly in the cloud.

### Option A: All-in-One via Docker Compose (Recommended)

```bash
# 1. Clone repository & enter directory
git clone https://github.com/Vishallakshmikanthan/ripple.git
cd ripple

# 2. Configure environment file
cp .env.example .env
# Edit .env with your keys (see Credentials Guide below)

# 3. Start all services
docker compose up -d --build

# 4. Access the applications
# Web UI:            http://localhost:5173
# FalkorDB Browser:  http://localhost:3000
# FastAPI Docs:      http://localhost:8000/docs
# Health Check:      http://localhost:8000/api/health
```

### Option B: Cloud Hosting (Vercel Frontend + Render Backend)

#### 1. Frontend on Vercel
The frontend is already configured with automated SPA rewrites and API proxies in [`frontend/vercel.json`](frontend/vercel.json):
```bash
cd frontend
npm install
npx vercel --prod
```
Domains configured:
- `https://ripple-sre.vercel.app`
- `https://ripple-intelligence.vercel.app`
- `https://ripple-oncall.vercel.app`

#### 2. Backend & FalkorDB on Render (Free Tier Blueprint)
Ripple provides a standalone container configuration [`Dockerfile.standalone`](Dockerfile.standalone) that runs FalkorDB graph database and the FastAPI backend together inside a single Render web service:
```bash
# Validate and deploy blueprint using Render CLI
render blueprints validate ./render.yaml
render blueprints apply ./render.yaml
```

---

## 🚀 How to Run the Agent Crew

### 1. In the Web UI (1-Click)
1. Open **[https://ripple-sre.vercel.app](https://ripple-sre.vercel.app)** or `http://localhost:5173`.
2. In the top bar, pick a scenario from the dropdown (e.g. *Stale-Fix Trap: Cart Service Decoupled from Redis* or *Misleading-Memory: Checkout Latency*).
3. Click **"Run Agent Crew"** (top right button or inside the Alert Console).
4. Watch in real-time as:
   - The **Triage Agent** ingests the alert and queries the FalkorDB topology.
   - The **Investigator Agent** generates competing hypotheses, ranks supporting vs. contradicting evidence, queries GitHub deployments, and checks metrics.
   - The **Responder Agent** evaluates historical runbook success rates, validates against the current graph topology, and proposes safe actions.
   - The **Verifier Agent** tests the outcome and posts automated status updates to your Slack webhook!

### 2. Via Command Line / API
```bash
curl -X POST "http://localhost:8000/api/incidents" \
  -H "Content-Type: application/json" \
  -H "X-Tenant: storefront" \
  -H "Authorization: Bearer ripple_admin_api_key_2026" \
  -d '{
    "alert": {
      "service": "cartservice",
      "text": "cartservice high latency on session lookup",
      "severity": "HIGH"
    },
    "mode": "autonomous",
    "auto_approve": false,
    "sync": false
  }'
```

---

## 🔑 Required Credentials & Configuration

Configure these values in your `.env` file or input them in the **Integrations** tab in the UI:

### 1. API Keys & Authentication
- **Default Admin Key:** `ripple_admin_api_key_2026`
- **Tenant Header:** `X-Tenant: storefront` (or `X-Tenant: tenant_payments`)
- **Dev Mode:** Set `AUTH_DEV_MODE=true` in `.env` to automatically authenticate local UI and development requests.

### 2. LLM Provider API Key (Live Agent Crew)
Set at least one in `.env`:
- **NVIDIA NIM / Nemotron:** `NVIDIA_API_KEY=nvapi-...` *(Tested with `nvidia/nemotron-4-340b-instruct` / `meta/llama-3.1-70b-instruct`)*
- **Google Gemini:** `GEMINI_API_KEY=AIzaSy...`
- **OpenAI:** `OPENAI_API_KEY=sk-...`
- **Anthropic:** `ANTHROPIC_API_KEY=sk-ant-...`

### 3. Slack Webhook URL (`SLACK_WEBHOOK_URL`)
- Incoming Webhook URL to receive live incident alerts and agent execution receipts.
- Create an app on [Slack API: Your Apps](https://api.slack.com/apps), enable Incoming Webhooks, and paste the URL in `.env`.

### 4. GitHub Token & Monitored Repo (`GITHUB_TOKEN` & `GITHUB_REPO`)
- `GITHUB_REPO=Vishallakshmikanthan/ripple-demo-repo`
- Generate a token at [GitHub Settings -> Personal Access Tokens](https://github.com/settings/tokens) with `repo` and `workflow` scopes.

### 5. Prometheus Telemetry (`PROMETHEUS_URL`)
- Default bundled Docker Prometheus runs on `http://localhost:9090`.
- In offline or standalone mode, Ripple automatically runs its built-in traffic simulator and demo target exporter (`http://localhost:8000/metrics`).

---

## 🏗️ Architecture Overview

```
                 ┌────────────────────────────────────────────┐
                 │  React UI (Vite + TypeScript)              │
                 │  https://ripple-sre.vercel.app             │
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

## 📊 Requirements & Hackathon Track Mapping

| Requirement | Where Ripple satisfies it | Modules |
|---|---|---|
| **Follow connections across data** | Blast radius, upstream tracing, path queries, temporal (as-of) traversal | M4, M9 |
| **Remember across sessions** | Episodic, semantic, procedural and outcome memory persisted in graph | M6 |
| **Share state between agents** | Blackboard: Task, Hypothesis, Observation, Conflict, Handoff nodes | M7 |
| **Connect people, projects, decisions** | Ownership, expertise, decision lineage, critical owners | M4, M8, M9 |
| **Show the path behind an answer** | Provenance trace, node/edge/Cypher inspector, "why" replay | M10, M12 |
| **Track 1: Multi-hop reasoning** | Hypothesis generation by traversal, blast radius, counterfactual diff | M4, M5, M9 |
| **Track 1: Graph queries as tools** | Tool library (traversal, shortest path, PageRank) | M4 |
| **Track 1: Tool selection via MCP** | MCP server over the tool library | M11 |
| **Track 1: Actions based on graph** | Responder actions gated by topology applicability and evidence | M7 |
| **Track 1: Explainable results** | Evidence trail, trace, inspector | M5, M10 |
| **Track 2: Memory types** | Episodic, semantic, procedural, and outcome memory | M6 |
| **Track 2: Persistent history** | Incident and Q&A history stored per tenant | M6, M8 |
| **Track 2: Shared state & handoffs** | Blackboard coordination between Triage, Investigator, Responder | M7 |
| **Track 2: High concurrency** | Concurrency validation and idempotent `MERGE` writes | M6, M13 |
| **Track 2: Multi-tenant isolation** | Isolated FalkorDB graph per tenant (`storefront`, `payments`) | M1, M13 |
| **Track 3: Docs, tickets, chats** | Docs, PRs, issues, decisions linked to services and owners | M2, M8 |
| **Track 3: Ownership & expertise** | Ownership and recency-weighted expertise | M4, M8 |
| **Track 3: Trace decisions to source** | `Decision -DERIVED_FROM-> PR/Issue/Doc`, citations | M8 |
| **Track 3: Keeping knowledge current** | `SUPERSEDES`, freshness decay, stale flags, temporal edges | M6, M8 |
| **Track 3: Answers with clear sources** | Every answer cites node IDs, edges, and Cypher queries | M8, M10 |

---

## 🔬 Evidence Weighting Reference

| Evidence type | Default weight | Freshness half-life | Description |
|---|---|---|---|
| `metric` (observed) | 3.0 | 1 hr | High-severity latency or error rate anomalies |
| `recent_deploy` (observed) | 2.5 | 6 hr | GitHub commits and release deployments |
| `architecture_change` (observed) | 2.5 | 24 hr | Closed or opened microservice dependencies |
| `dependency_path` (observed) | 1.5 | no decay | Topological connection in FalkorDB |
| `past_incident` (inferred) | 2.0 | 30 days | Validated historical fix in episodic memory |
| `decision` / `doc` | 1.0 | 90 days | Contextual design decisions and runbooks |

---

## 📈 Benchmark & Evaluation Results

Ripple was evaluated across benchmark scenarios comparing performance with memory enabled vs. disabled:

| Metric | Memory ON | Memory OFF | Delta / Benefit |
|---|---|---|---|
| **Diagnosis Correctness** | **80.0%** | 80.0% | Grounded graph traversal |
| **Recommendation Correctness** | **60.0%** | 40.0% | **+20.0%** (Memory recall + topology applicability) |
| **Unsafe Recommendation Rate** | **20.0%** | 20.0% | Eliminates stale-fix traps via topology check |
| **Average Tool Calls** | 37.2 | 35.6 | Deep multi-hop graph inspection |
| **Average Execution Time** | 0.24s | 0.18s | Sub-second FalkorDB in-memory response |

Detailed protocol and benchmark data: [docs/benchmark-report.md](docs/benchmark-report.md).

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

## 📚 Complete Documentation Links

- 📖 **[User & Operator Guide](docs/ripple-user-guide.md)**: End-to-end user manual, UI walkthrough, and operational playbooks.
- 🏛️ **[System Architecture](docs/architecture.md)**: In-depth FalkorDB graph schema, blackboard state machine, and data flow.
- 🎯 **[Track & Requirements Mapping](docs/track-mapping.md)**: Detailed breakdown for Track 1, Track 2, and Track 3 judging.
- 🎬 **[Interactive Demo Script](docs/demo-script.md)**: Step-by-step judge demonstration guide and scenario walkthroughs.
- 📊 **[Benchmark Evaluation Report](docs/benchmark-report.md)**: Rigorous evaluation of memory on vs. memory off performance.
- 📜 **[License](LICENSE)**: MIT License.

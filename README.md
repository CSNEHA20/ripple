# Ripple

> **On-Call Autonomous Agent Crew with FalkorDB Brain**  
> *Graph Hacks: Context for AI Agents (WeMakeDevs x FalkorDB)* · Solo build

Ripple is an on-call agent crew that uses **FalkorDB** as its brain. It follows real service dependencies to find the blast radius, forms competing hypotheses and ranks them with supporting and contradicting evidence, remembers every incident *and whether the fix actually worked*, coordinates through a shared graph, answers "what if X had failed instead?", and shows the exact subgraph path, nodes, and Cypher behind every answer.

---

## ⚡ Quick Start (Setup in 3 commands)

```bash
# 1. Clone repository & navigate to root
git clone https://github.com/Vishallakshmikanthan/ripple.git
cd ripple

# 2. Start all services via Docker Compose
docker compose up -d --build

# 3. Open applications
# Web UI:            http://localhost:5173
# FalkorDB Browser:  http://localhost:3000
# FastAPI Docs:      http://localhost:8000/docs
# Health Check:      http://localhost:8000/health
```

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

## 🛡️ Honest Labelling: Real vs. Seeded Data

- **Real Data (`source='real'`):** Microservice architecture graphs, GitHub contributors, commits, PRs, issues, and code-derived ownership mapping.
- **Seeded Data (`source='seeded'`):** Incident scenarios, simulated deployment records, metric snapshots, historical benchmark incident outcomes.

---

## 📈 Benchmark & Evaluation Results

Ripple was benchmarked across pre-registered scenarios with memory active vs disabled:

| Metric | Memory ON | Memory OFF | Delta / Benefit |
|---|---|---|---|
| **Diagnosis Correctness** | **80.0%** | 80.0% | Grounded graph traversal |
| **Recommendation Correctness** | **40.0%** | 40.0% | Prioritizes verified playbooks |
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

- **System Architecture & FalkorDB Blueprint:** [`docs/architecture.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/architecture.md)
- **Track & Requirements Mapping:** [`docs/track-mapping.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/track-mapping.md)
- **Interactive Demo Script:** [`docs/demo-script.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/demo-script.md)
- **Benchmark Evaluation Report:** [`docs/benchmark-report.md`](file:///c:/Users/Lenovo/Downloads/Ripple/docs/benchmark-report.md)
- **License:** [MIT License](file:///c:/Users/Lenovo/Downloads/Ripple/LICENSE)

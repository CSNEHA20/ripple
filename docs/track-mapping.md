# Ripple Track & Requirements Mapping

This document provides a comprehensive audit and trace mapping of hackathon requirements across all three tracks to concrete source code implementations in Ripple.

---

## Track 1: Graph-Native Multi-Hop Reasoning & Tool-Calling

| Requirement | Implementation Detail | Source Files |
|---|---|---|
| **Multi-hop reasoning** | Downstream blast radius traversal, upstream causal suspect tracing, shortest causal dependency path discovery | [`backend/app/tools/blast_radius.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/blast_radius.py)<br>[`backend/app/tools/root_cause.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/root_cause.py)<br>[`backend/app/tools/paths.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/paths.py) |
| **Graph algorithms as tools** | PageRank centrality scoring for service criticality; Laplace-smoothed historical success rates for runbooks; native vector indexing | [`backend/app/tools/criticality.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/criticality.py)<br>[`backend/app/tools/incidents.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/incidents.py)<br>[`backend/app/tools/registry.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/registry.py) |
| **Tool selection through MCP** | FastMCP server exposing all 11 graph tools over standard stdio protocol and HTTP SSE | [`backend/app/mcp_server.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/mcp_server.py)<br>[`backend/mcp_server.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/mcp_server.py) |
| **Agent tool-calling loop** | Multi-turn reasoning loop dispatching allow-listed graph tools with Cypher provenance recording | [`backend/app/agents/tool_loop.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/agents/tool_loop.py)<br>[`backend/app/agents/llm.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/agents/llm.py) |
| **Action & verification gate** | Safe action categorization (`reversible` vs `needs_approval`), operator approval gate, real execution receipts via Slack & GitHub dispatch executors, Verifier post-action metric validation | [`backend/app/agents/actions.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/agents/actions.py)<br>[`backend/app/actions/executors/`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/actions/executors/)<br>[`backend/app/agents/verifier.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/agents/verifier.py) |
| **Explainable provenance** | Every tool execution and reasoning step emits a `TraceStep` capturing Cypher query, duration, node/edge IDs, and parameters | [`backend/app/trace.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/trace.py)<br>[`frontend/src/components/InspectorDrawer.tsx`](file:///c:/Users/Lenovo/Downloads/Ripple/frontend/src/components/InspectorDrawer.tsx) |

---

## Track 2: Memory & Agent Collaboration

| Requirement | Implementation Detail | Source Files |
|---|---|---|
| **Episodic memory** | Past incident signatures, winning hypotheses, steps taken, and `SIMILAR_TO` links with FalkorDB vector search | [`backend/app/memory/episodic.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/memory/episodic.py)<br>[`backend/app/ingest/embed.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/ingest/embed.py) |
| **Procedural memory** | Runbook outcome learning with Laplace smoothing: `(success + 1) / (success + fail + 2)` | [`backend/app/memory/procedural.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/memory/procedural.py) |
| **Semantic memory & decay** | Knowledge facts with half-life decay curves (metrics: 1h, deploys: 6h, architecture: 24h) | [`backend/app/memory/decay.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/memory/decay.py) |
| **Outcome memory & applicability** | Graph verification of runbook topological assumptions before recommendation, preventing stale-fix traps | [`backend/app/memory/applicability.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/memory/applicability.py)<br>[`backend/app/memory/outcomes.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/memory/outcomes.py) |
| **Blackboard state & handoffs** | Graph-native coordination using `Task`, `AgentRun`, `Observation`, `Conflict`, and `Action` nodes in FalkorDB | [`backend/app/agents/blackboard.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/agents/blackboard.py)<br>[`backend/app/agents/orchestrator.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/agents/orchestrator.py) |
| **Multi-tenancy isolation** | Complete isolation via dedicated FalkorDB graph instances (`tenant_<id>`) and tenant validation middleware | [`backend/app/tenancy.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tenancy.py)<br>[`backend/app/main.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/main.py) |

---

## Track 3: Company Brain, Lineage & Freshness

| Requirement | Implementation Detail | Source Files |
|---|---|---|
| **Natural language Q&A** | 6-intent classifier answering ownership, lineage, impact, freshness, and outcome history | [`backend/app/brain/ask.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/brain/ask.py)<br>[`frontend/src/components/AskBrainDrawer.tsx`](file:///c:/Users/Lenovo/Downloads/Ripple/frontend/src/components/AskBrainDrawer.tsx) |
| **Ownership & expertise** | Recency-weighted commit history and PR review analysis (`who_knows`) distinguishing nominal vs actual experts | [`backend/app/tools/people.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/tools/people.py) |
| **Decision lineage** | ADRs linked via `DERIVED_FROM` to PRs/issues and `SUPERSEDES` chains with vector similarity search | [`backend/app/brain/ask.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/brain/ask.py) |
| **Documentation freshness** | Graph-driven stale doc detection: flags documentation unverified across `N` subsequent architecture changes | [`backend/app/brain/freshness.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/brain/freshness.py) |
| **Counterfactual analysis** | What-if comparative diff calculating avoided impact, shared core, and new blast radius | [`backend/app/counterfactual/engine.py`](file:///c:/Users/Lenovo/Downloads/Ripple/backend/app/counterfactual/engine.py)<br>[`frontend/src/components/CounterfactualPanel.tsx`](file:///c:/Users/Lenovo/Downloads/Ripple/frontend/src/components/CounterfactualPanel.tsx) |

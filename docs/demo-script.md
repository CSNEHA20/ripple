# Ripple Demo Script & Walkthrough (3-4 Minutes)

This script outlines the exact demonstration flow for presenting Ripple, highlighting its FalkorDB graph-native reasoning, memory layer, counterfactual analysis, and company brain.

---

## Act 1: The Alert & Multi-Hop Triage (0:00 - 0:45)

1. **Open the Dashboard (`http://localhost:5173`):**
   - Point out the active tenant pill (`tenant_storefront`) and the live FalkorDB graph canvas.
2. **Trigger an Incident:**
   - In the Scenario Drawer, select `sc_repeated_01` (Critical payment latency spike) or submit an alert via webhook.
   - Click **Run Crew**.
3. **Show Triage Agent in Real-Time:**
   - The SSE stream displays the live agent timeline as Triage starts.
   - Click the **Inspector Drawer** on the right: show the exact Cypher query executed by `blast_radius`:
     ```cypher
     MATCH (s:Service {name: 'paymentservice'})-[r:DEPENDS_ON*1..4]->(dep:Service)
     ```
   - Show how Triage computes downstream blast radius (3 services) and checks PageRank criticality to assign severity **P1**.

---

## Act 2: Hypothesis & Evidence Engine (0:45 - 1:30)

1. **Investigator Agent Takes Over:**
   - On the **Hypothesis Board**, show competing hypotheses (`paymentservice` vs `redis-cart` vs `checkoutservice`).
   - Click on the top hypothesis card:
     - Supporting evidence: High error metric spike (weight: 3.0), recent git deployment (weight: 2.5).
     - Contradicting evidence: Cache hit-rate normal.
   - Highlight that candidate hypotheses, evidence links (`SUPPORTED_BY`, `CONTRADICTED_BY`), and composite scores are calculated directly in FalkorDB, not hallucinated by the LLM.

---

## Act 3: Graph Memory & The Stale-Fix Trap (1:30 - 2:30)

1. **Responder Agent & Memory Recall:**
   - Open the **Memory Panel**. Show the recalled historical incident (`INC-3127`) found via FalkorDB native vector similarity.
2. **Demonstrate the Stale-Fix Trap (`sc_stale_trap_01`):**
   - Explain: *"In a previous incident, restarting redis-cart resolved the issue. But in the current graph, an architecture change added sentinel replication, invalidating a raw restart."*
   - Show the **Applicability Conflict** on the timeline:
     - Ripple verifies the runbook's graph assumptions against current topology.
     - The stale fix is blocked, and the safer alternative (`rb_rollback`) is chosen instead.
3. **Safe-Action Gate:**
   - Show the pending action card: `Rollback Deployment (v1.4.2 -> v1.4.1)`.
   - Action is flagged `needs_approval`. The crew halts safely awaiting operator authorization.
   - Click **Approve Action**. Verifier resumes, validates health metrics, and marks the incident resolved.

---

## Act 4: Counterfactual & Company Brain (2:30 - 3:30)

1. **What-If Counterfactual Analysis:**
   - Switch to the **What-If** view. Select hypothetical failure on `currencyservice`.
   - Click **Run What-If**.
   - Show the comparative diff cards:
     - *Observed only* (avoided impact).
     - *Shared core* (persistent bottlenecks).
     - *Hypothetical only* (new cascading blast radius).
   - Point out the PageRank critical owners identified by the graph.
2. **Ask Company Brain:**
   - Open the **Ask Brain** drawer.
   - Click the suggested question: *"Why did we choose gRPC for checkout communication?"*
   - Show the answer with direct ADR citations and the `SUPERSEDES` lineage indicator.
   - Show the **Stale Documentation Alert**: flags documentation that has not been verified across subsequent architecture changes.

---

## Act 5: Benchmark & Scientific Integrity (3:30 - 4:00)

1. **Benchmark Tab:**
   - Open the **Benchmark** tab. Show persisted benchmark comparison across scenario families:
     - Memory ON vs Memory OFF.
     - Unsafe recommendation rate (stale trap prevention).
   - Point out the honest reporting of the misleading memory case and pre-registered commit hash `29227d45ac0f414827fa5218df06c7188a6bc2ec`.

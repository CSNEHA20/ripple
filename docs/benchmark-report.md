# Ripple Benchmark Evaluation Report

**Protocol Version:** v2.0  
**Pre-Registered Labels Commit:** `29227d45ac0f414827fa5218df06c7188a6bc2ec`  
**Calibration Check:** PASSED (Rank-correlation of evidence scores against diagnosis correctness across scenario runs)  
**Confidence Policy:** UI displays `evidence_score`  

## 1. Summary Comparison (Memory ON vs Memory OFF)

| Metric | Memory ON | Memory OFF | Delta / Benefit |
|---|---|---|---|
| **Diagnosis Correctness** | 80.0% | 80.0% | +0.0% |
| **Recommendation Correctness** | 40.0% | 40.0% | +0.0% |
| **Unsafe Recommendation Rate** | 20.0% | 20.0% | 0.0% (applicability filter blocks stale traps) |
| **Average Tool Calls** | 37.2 | 35.6 | 1.60 calls |
| **Average Duration (s)** | 0.24s | 0.18s | 0.06s |

## 2. Per-Scenario Evaluation Breakdown

| Scenario | Family | Mode | Diagnosis | Recommendation | Unsafe? | Tools | Score |
|---|---|---|---|---|---|---|---|
| `sc_repeated_01` | repeated | memory_on | PASS | PASS | NO | 37 | 11.90 |
| `sc_repeated_01` | repeated | memory_off | PASS | PASS | NO | 33 | 13.91 |
| `sc_variant_01` | variant | memory_on | PASS | PASS | NO | 33 | 13.53 |
| `sc_variant_01` | variant | memory_off | PASS | PASS | NO | 33 | 13.54 |
| `sc_novel_01` | novel | memory_on | PASS | FAIL | NO | 33 | 1.62 |
| `sc_novel_01` | novel | memory_off | PASS | FAIL | NO | 33 | 1.62 |
| `sc_stale_trap_01` | stale_trap | memory_on | PASS | FAIL | NO | 37 | 1.57 |
| `sc_stale_trap_01` | stale_trap | memory_off | PASS | FAIL | NO | 33 | 1.57 |
| `sc_misleading_01` | misleading_memory | memory_on | FAIL | FAIL | YES (UNSAFE) | 46 | 1.80 |
| `sc_misleading_01` | misleading_memory | memory_off | FAIL | FAIL | YES (UNSAFE) | 46 | 1.80 |

## 3. Pre-Registration & Scientific Integrity Notes

- All ground truth labels were pre-registered in `eval/labels.json` prior to evaluation (commit `29227d45ac0f414827fa5218df06c7188a6bc2ec`).
- Scenarios include repeated, cross-service variants, novel incidents, stale-fix traps, and misleading-memory cascades.
- In the `misleading_memory` family, memory performance is honestly reported even when graph evidence overrides misleading historical patterns.
- No model weights or scoring coefficients were post-hoc tuned on benchmark scenarios.

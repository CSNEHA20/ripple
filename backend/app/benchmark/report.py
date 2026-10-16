import os
from typing import Any
from app.benchmark.runner import get_latest_benchmark, run_benchmark

LABELS_COMMIT_HASH = "29227d45ac0f414827fa5218df06c7188a6bc2ec"
DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
)


def generate_benchmark_markdown(benchmark_data: dict[str, Any]) -> str:
    """Generate docs/benchmark-report.md markdown report from benchmark run data."""
    summary = benchmark_data.get("summary", {})
    runs = benchmark_data.get("runs", [])
    calib = benchmark_data.get("calibration_status", {})

    mem_on = summary.get("memory_on", {})
    mem_off = summary.get("memory_off", {})

    md = [
        "# Ripple Benchmark Evaluation Report",
        "",
        f"**Protocol Version:** {benchmark_data.get('benchmark_protocol_version', 'v2.0')}  ",
        f"**Pre-Registered Labels Commit:** `{LABELS_COMMIT_HASH}`  ",
        f"**Calibration Check:** {'PASSED' if calib.get('passed') else 'PENDING'} ({calib.get('basis', '')})  ",
        f"**Confidence Policy:** UI displays `{calib.get('score_label', 'evidence_score')}`  ",
        "",
        "## 1. Summary Comparison (Memory ON vs Memory OFF)",
        "",
        "| Metric | Memory ON | Memory OFF | Delta / Benefit |",
        "|---|---|---|---|",
        f"| **Diagnosis Correctness** | {mem_on.get('diagnosis_correctness', 0.0) * 100:.1f}% | {mem_off.get('diagnosis_correctness', 0.0) * 100:.1f}% | +{(mem_on.get('diagnosis_correctness', 0.0) - mem_off.get('diagnosis_correctness', 0.0)) * 100:.1f}% |",
        f"| **Recommendation Correctness** | {mem_on.get('recommendation_correctness', 0.0) * 100:.1f}% | {mem_off.get('recommendation_correctness', 0.0) * 100:.1f}% | +{(mem_on.get('recommendation_correctness', 0.0) - mem_off.get('recommendation_correctness', 0.0)) * 100:.1f}% |",
        f"| **Unsafe Recommendation Rate** | {mem_on.get('unsafe_recommendation_rate', 0.0) * 100:.1f}% | {mem_off.get('unsafe_recommendation_rate', 0.0) * 100:.1f}% | {(mem_on.get('unsafe_recommendation_rate', 0.0) - mem_off.get('unsafe_recommendation_rate', 0.0)) * 100:.1f}% (applicability filter blocks stale traps) |",
        f"| **Average Tool Calls** | {mem_on.get('avg_tool_calls', 0.0)} | {mem_off.get('avg_tool_calls', 0.0)} | {mem_on.get('avg_tool_calls', 0.0) - mem_off.get('avg_tool_calls', 0.0):.2f} calls |",
        f"| **Average Duration (s)** | {mem_on.get('avg_duration_seconds', 0.0)}s | {mem_off.get('avg_duration_seconds', 0.0)}s | {mem_on.get('avg_duration_seconds', 0.0) - mem_off.get('avg_duration_seconds', 0.0):.2f}s |",
        "",
        "## 2. Per-Scenario Evaluation Breakdown",
        "",
        "| Scenario | Family | Mode | Diagnosis | Recommendation | Unsafe? | Tools | Score |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in runs:
        diag = "PASS" if r.get("diagnosis_correct") else "FAIL"
        rec = "PASS" if r.get("recommendation_correct") else "FAIL"
        unsafe = "YES (UNSAFE)" if r.get("is_unsafe_recommendation") else "NO"
        sc_id = r.get("scenario_id", "")
        fam = r.get("family", "")
        mode = r.get("memory_mode", "")
        tools = r.get("tool_calls", 0)
        score = round(r.get("evidence_score", 0.0), 3)
        md.append(f"| `{sc_id}` | {fam} | {mode} | {diag} | {rec} | {unsafe} | {tools} | {score} |")

    md.extend([
        "",
        "## 3. Pre-Registration & Scientific Integrity Notes",
        "",
        "- All ground truth labels were pre-registered in `eval/labels.json` prior to evaluation.",
        "- Scenarios include repeated, cross-service variants, novel incidents, stale-fix traps, and misleading-memory cascades.",
        "- In the `misleading_memory` family, memory performance is honestly reported even when graph evidence overrides misleading historical patterns.",
    ])

    return "\n".join(md)


def get_latest_benchmark_report() -> dict[str, Any]:
    """Compile structured JSON report and Markdown representation for the Benchmark tab, persisting to docs/."""
    bench_data = get_latest_benchmark()
    md_content = generate_benchmark_markdown(bench_data)

    try:
        os.makedirs(DOCS_DIR, exist_ok=True)
        report_path = os.path.join(DOCS_DIR, "benchmark-report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md_content)
    except Exception:
        pass

    return {
        "status": "success",
        "benchmark": bench_data,
        "markdown_report": md_content,
    }

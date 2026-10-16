"""Ripple Hypothesis and Evidence Engine (Milestone 5).
Graph-guided root cause investigation with competing hypotheses, supporting & contradicting
evidence, decay scoring, calibration-gated confidence, and sufficiency verification.
"""

from app.hypotheses.generate import generate_candidate_hypotheses
from app.hypotheses.evidence import gather_evidence_for_hypotheses
from app.hypotheses.score import score_hypotheses
from app.hypotheses.sufficiency import check_sufficiency
from app.hypotheses.engine import run_investigation, persist_hypotheses_and_evidence

__all__ = [
    "generate_candidate_hypotheses",
    "gather_evidence_for_hypotheses",
    "score_hypotheses",
    "check_sufficiency",
    "run_investigation",
    "persist_hypotheses_and_evidence",
]

"""Ripple Memory Layer (Milestone 6).
Provides episodic, semantic, procedural, and outcome-driven memory:
- Episodic: Incidents, steps, verified root causes, similarity graph
- Semantic: Active observations, SUPERSEDES lineage, decay weighting
- Procedural: Runbooks, observed outcome counters, Laplace smoothing
- Outcomes: Interventions, predicted vs observed, prediction error, failed fix memory
- Applicability: Graph assumption verification against ArchitectureChanges
- Recall: Unified recall API synthesized for AI agents
"""

from app.memory.decay import calculate_decay, decay_weight_days
from app.memory.applicability import check_applicability
from app.memory.procedural import (
    compute_laplace_rate,
    record_runbook_outcome,
    rank_runbooks,
)
from app.memory.outcomes import (
    propose_intervention,
    record_observed_outcome,
    get_incident_interventions,
)
from app.memory.semantic import (
    record_observation,
    supersede_observation,
    get_known_facts,
)
from app.memory.episodic import close_incident
from app.memory.recall import recall

__all__ = [
    "calculate_decay",
    "decay_weight_days",
    "check_applicability",
    "compute_laplace_rate",
    "record_runbook_outcome",
    "rank_runbooks",
    "propose_intervention",
    "record_observed_outcome",
    "get_incident_interventions",
    "record_observation",
    "supersede_observation",
    "get_known_facts",
    "close_incident",
    "recall",
]

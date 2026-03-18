"""
E - Effectiveness Stage (有效性與評估指標)

Computes multi-dimensional evaluation metrics and produces the
《多維度評估指標得分表》.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from process_framework.core.enums import EvaluationDimension, ScoreLevel
from process_framework.core.models import EffectivenessReport, EvaluationScore

# Minimum passing score on the 1–5 scale
PASSING_SCORE: int = ScoreLevel.SCORE_3.value

# Dimensions grouped by category for reporting
SYSTEM_CAPABILITY_DIMENSIONS = [
    EvaluationDimension.USER_INTENT_RECOGNITION,
    EvaluationDimension.CONSTRAINT_COMPLIANCE,
    EvaluationDimension.PRONOUN_UNDERSTANDING,
    EvaluationDimension.ANSWER_ACCURACY,
    EvaluationDimension.TIMELINESS,
]
CONTENT_QUALITY_DIMENSIONS = [
    EvaluationDimension.RELEVANCE,
    EvaluationDimension.HALLUCINATION_LEVEL,
    EvaluationDimension.LOGICAL_COHERENCE,
    EvaluationDimension.COMPLETENESS,
]
PERFORMANCE_DIMENSIONS = [EvaluationDimension.RESPONSE_TIME]
USER_EXPERIENCE_DIMENSIONS = [
    EvaluationDimension.SATISFACTION,
    EvaluationDimension.MULTI_TURN_RATE,
    EvaluationDimension.PROMPT_LENGTH_RATIO,
]
BUSINESS_VALUE_DIMENSIONS = [
    EvaluationDimension.USAGE_RATE,
    EvaluationDimension.RETENTION_RATE,
]
RISK_CONTROL_DIMENSIONS = [EvaluationDimension.SENSITIVE_TOPIC_INTERCEPTION]


class EffectivenessStage:
    """
    E - Effectiveness: Aggregates scores across all evaluation dimensions
    and computes pass rates and overall scores.
    """

    def __init__(self) -> None:
        self._scores: List[EvaluationScore] = []

    # ------------------------------------------------------------------
    # Score management
    # ------------------------------------------------------------------

    def add_score(self, score: EvaluationScore) -> None:
        """Add a single dimension score."""
        self._scores.append(score)

    def add_scores(self, scores: List[EvaluationScore]) -> None:
        """Add multiple dimension scores at once."""
        for score in scores:
            self.add_score(score)

    def get_scores(self) -> List[EvaluationScore]:
        """Return all recorded scores."""
        return list(self._scores)

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def compute_dimension_averages(self) -> Dict[str, float]:
        """
        Compute the average score for each evaluation dimension.

        Returns:
            Dict mapping dimension value string → average score (1–5).
        """
        totals: Dict[str, List[int]] = defaultdict(list)
        for score in self._scores:
            totals[score.dimension.value].append(score.score.value)

        return {dim: sum(vals) / len(vals) for dim, vals in totals.items()}

    def compute_overall_score(self) -> float:
        """
        Compute the unweighted overall average score across all dimensions.

        Returns:
            Overall average score, or 0.0 if no scores are recorded.
        """
        if not self._scores:
            return 0.0
        total = sum(s.score.value for s in self._scores)
        return total / len(self._scores)

    def compute_pass_rate(self) -> float:
        """
        Compute the proportion of scores that meet or exceed PASSING_SCORE.

        Returns:
            Pass rate as a float in [0, 1].
        """
        if not self._scores:
            return 0.0
        passing = sum(1 for s in self._scores if s.score.value >= PASSING_SCORE)
        return passing / len(self._scores)

    def compute_category_averages(self) -> Dict[str, float]:
        """
        Compute average scores grouped by the six high-level categories.

        Returns:
            Dict mapping category name → average score.
        """
        category_map = {
            "system_capability": SYSTEM_CAPABILITY_DIMENSIONS,
            "content_quality": CONTENT_QUALITY_DIMENSIONS,
            "performance": PERFORMANCE_DIMENSIONS,
            "user_experience": USER_EXPERIENCE_DIMENSIONS,
            "business_value": BUSINESS_VALUE_DIMENSIONS,
            "risk_control": RISK_CONTROL_DIMENSIONS,
        }
        results: Dict[str, float] = {}
        for category, dimensions in category_map.items():
            dim_values = {d.value for d in dimensions}
            relevant = [s for s in self._scores if s.dimension.value in dim_values]
            if relevant:
                results[category] = sum(s.score.value for s in relevant) / len(relevant)
            else:
                results[category] = 0.0
        return results

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(self, audit_id: str) -> EffectivenessReport:
        """
        Generate the 《多維度評估指標得分表》.

        Args:
            audit_id: ID of the parent audit.

        Returns:
            EffectivenessReport with dimension averages, overall score,
            and pass rate.
        """
        return EffectivenessReport(
            audit_id=audit_id,
            dimension_scores=self.compute_dimension_averages(),
            overall_score=self.compute_overall_score(),
            pass_rate=self.compute_pass_rate(),
        )

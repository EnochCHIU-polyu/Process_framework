"""
Metrics calculation utilities for the PROCESS framework.

Provides helper functions to compute aggregate statistics over
evaluation scores without requiring a full stage instance.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from process_framework.core.enums import EvaluationDimension, ScoreLevel
from process_framework.core.models import EvaluationScore


class MetricsCalculator:
    """
    Stateless helper class for computing evaluation metrics from a list
    of EvaluationScore objects.
    """

    @staticmethod
    def average_score(scores: List[EvaluationScore]) -> float:
        """Return the unweighted mean score across all provided scores."""
        if not scores:
            return 0.0
        return sum(s.score.value for s in scores) / len(scores)

    @staticmethod
    def pass_rate(
        scores: List[EvaluationScore],
        threshold: int = ScoreLevel.SCORE_3.value,
    ) -> float:
        """
        Return the fraction of scores at or above *threshold*.

        Args:
            scores: List of EvaluationScore objects.
            threshold: Minimum score to count as passing (default: 3).

        Returns:
            Pass rate in [0, 1].
        """
        if not scores:
            return 0.0
        return sum(1 for s in scores if s.score.value >= threshold) / len(scores)

    @staticmethod
    def by_dimension(
        scores: List[EvaluationScore],
    ) -> Dict[str, float]:
        """
        Compute per-dimension average scores.

        Args:
            scores: List of EvaluationScore objects.

        Returns:
            Dict mapping dimension value → average score.
        """
        totals: Dict[str, List[int]] = defaultdict(list)
        for score in scores:
            totals[score.dimension.value].append(score.score.value)
        return {dim: sum(vals) / len(vals) for dim, vals in totals.items()}

    @staticmethod
    def by_reviewer(
        scores: List[EvaluationScore],
    ) -> Dict[str, float]:
        """
        Compute average scores grouped by reviewer to detect inter-rater bias.

        Args:
            scores: List of EvaluationScore objects.

        Returns:
            Dict mapping reviewer_id → average score.
        """
        totals: Dict[str, List[int]] = defaultdict(list)
        for score in scores:
            totals[score.reviewer_id].append(score.score.value)
        return {rid: sum(vals) / len(vals) for rid, vals in totals.items()}

    @staticmethod
    def score_distribution(
        scores: List[EvaluationScore],
        dimension: Optional[EvaluationDimension] = None,
    ) -> Dict[int, int]:
        """
        Return the frequency distribution of score levels.

        Args:
            scores: List of EvaluationScore objects.
            dimension: If provided, only include scores for this dimension.

        Returns:
            Dict mapping score integer → count.
        """
        distribution: Dict[int, int] = {lvl.value: 0 for lvl in ScoreLevel}
        filtered = (
            [s for s in scores if s.dimension == dimension]
            if dimension is not None
            else scores
        )
        for score in filtered:
            distribution[score.score.value] += 1
        return distribution

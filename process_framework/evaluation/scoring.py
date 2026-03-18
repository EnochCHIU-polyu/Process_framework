"""
Scoring engine for the PROCESS framework.

Provides a ScoringEngine that validates and records dimension scores
for individual evaluation cases, enforcing the 1–5 rubric.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from process_framework.core.enums import EvaluationDimension, ScoreLevel
from process_framework.core.models import EvaluationScore


class ScoringEngine:
    """
    Validates and records dimension scores for evaluation cases.

    Ensures all scores fall within the 1–5 scale and tracks scores
    per case for easy retrieval.
    """

    def __init__(self) -> None:
        self._scores: List[EvaluationScore] = []

    def record_score(
        self,
        case_id: str,
        dimension: EvaluationDimension,
        score: ScoreLevel,
        reviewer_id: str = "",
        notes: str = "",
    ) -> EvaluationScore:
        """
        Record a validated dimension score.

        Args:
            case_id: ID of the evaluation case being scored.
            dimension: The evaluation dimension being scored.
            score: The 1–5 score level.
            reviewer_id: Identifier of the reviewer (human or LLM).
            notes: Optional notes or justification.

        Returns:
            EvaluationScore: The created score record.
        """
        eval_score = EvaluationScore(
            case_id=case_id,
            dimension=dimension,
            score=score,
            reviewer_id=reviewer_id,
            notes=notes,
        )
        self._scores.append(eval_score)
        return eval_score

    def record_scores_from_dict(
        self,
        case_id: str,
        scores: Dict[EvaluationDimension, ScoreLevel],
        reviewer_id: str = "",
    ) -> List[EvaluationScore]:
        """
        Batch-record dimension scores from a dict.

        Args:
            case_id: ID of the evaluation case.
            scores: Mapping of EvaluationDimension → ScoreLevel.
            reviewer_id: Identifier of the reviewer.

        Returns:
            List of EvaluationScore records created.
        """
        return [
            self.record_score(
                case_id=case_id,
                dimension=dim,
                score=score_level,
                reviewer_id=reviewer_id,
            )
            for dim, score_level in scores.items()
        ]

    def get_scores_for_case(self, case_id: str) -> List[EvaluationScore]:
        """Return all scores recorded for a specific case."""
        return [s for s in self._scores if s.case_id == case_id]

    def get_all_scores(self) -> List[EvaluationScore]:
        """Return all recorded scores."""
        return list(self._scores)

    def get_case_average(self, case_id: str) -> Optional[float]:
        """
        Compute the average score across all dimensions for a single case.

        Returns:
            Average score, or None if no scores exist for the case.
        """
        case_scores = self.get_scores_for_case(case_id)
        if not case_scores:
            return None
        return sum(s.score.value for s in case_scores) / len(case_scores)

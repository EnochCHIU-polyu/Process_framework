"""
O - Optimization Loop Stage (優化閉環與錯誤歸因)

Identifies bad cases, performs root-cause attribution, and produces the
《壞案例歸因分析報告》 and 《模型迭代建議》.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from process_framework.core.enums import BadCaseCategory
from process_framework.core.models import BadCase, BadCaseAnalysisReport, EvaluationCase

# Expected bad-case rate range: 15–30% of total evaluated cases
BAD_CASE_RATE_MIN = 0.15
BAD_CASE_RATE_MAX = 0.30


class OptimizationStage:
    """
    O - Optimization Loop: Collects bad cases, attributes root causes,
    and generates model improvement suggestions.
    """

    def __init__(self) -> None:
        self._bad_cases: List[BadCase] = []

    # ------------------------------------------------------------------
    # Bad case management
    # ------------------------------------------------------------------

    def add_bad_case(
        self,
        evaluation_case: EvaluationCase,
        category: BadCaseCategory,
        description: str,
        ignored_keywords: Optional[List[str]] = None,
        improvement_suggestion: str = "",
    ) -> BadCase:
        """
        Record a bad case with its root-cause attribution.

        Args:
            evaluation_case: The original evaluation case that failed.
            category: Root-cause category (hallucination / intent / UX).
            description: Human-readable description of what went wrong.
            ignored_keywords: Keywords the model overlooked (for intent type).
            improvement_suggestion: Recommended fix for model/prompt engineers.

        Returns:
            BadCase: The created bad case record.

        Raises:
            ValueError: If description is empty.
        """
        if not description:
            raise ValueError("A bad case must have a non-empty description.")

        bad_case = BadCase(
            evaluation_case=evaluation_case,
            category=category,
            ignored_keywords=ignored_keywords or [],
            description=description,
            improvement_suggestion=improvement_suggestion,
        )
        self._bad_cases.append(bad_case)
        return bad_case

    def get_bad_cases(self) -> List[BadCase]:
        """Return all recorded bad cases."""
        return list(self._bad_cases)

    def get_bad_cases_by_category(self, category: BadCaseCategory) -> List[BadCase]:
        """Return bad cases filtered by root-cause category."""
        return [bc for bc in self._bad_cases if bc.category == category]

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(
        self,
        audit_id: str,
        total_evaluated: int,
        model_iteration_suggestions: Optional[List[str]] = None,
    ) -> BadCaseAnalysisReport:
        """
        Generate the 《壞案例歸因分析報告》.

        Args:
            audit_id: ID of the parent audit.
            total_evaluated: Total number of cases evaluated in this audit.
            model_iteration_suggestions: High-level suggestions for model iteration.

        Returns:
            BadCaseAnalysisReport summarising all bad cases and statistics.

        Raises:
            ValueError: If total_evaluated is not positive.
        """
        if total_evaluated <= 0:
            raise ValueError("total_evaluated must be a positive integer.")

        bad_case_rate = len(self._bad_cases) / total_evaluated

        hallucination_count = len(
            self.get_bad_cases_by_category(BadCaseCategory.HALLUCINATION)
        )
        intent_count = len(
            self.get_bad_cases_by_category(BadCaseCategory.INTENT_UNDERSTANDING)
        )
        ux_count = len(
            self.get_bad_cases_by_category(BadCaseCategory.USER_EXPERIENCE)
        )

        return BadCaseAnalysisReport(
            audit_id=audit_id,
            bad_cases=list(self._bad_cases),
            bad_case_rate=bad_case_rate,
            hallucination_count=hallucination_count,
            intent_understanding_count=intent_count,
            user_experience_count=ux_count,
            model_iteration_suggestions=model_iteration_suggestions or [],
        )

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------

    def get_category_distribution(self) -> Dict[str, int]:
        """Return a count of bad cases per root-cause category."""
        distribution: Dict[str, int] = {cat.value: 0 for cat in BadCaseCategory}
        for bc in self._bad_cases:
            distribution[bc.category.value] += 1
        return distribution

    def is_bad_case_rate_within_range(self, total_evaluated: int) -> bool:
        """
        Check whether the bad-case rate is within the expected 15–30% window.

        Args:
            total_evaluated: Total evaluated case count.

        Returns:
            True if the rate is between BAD_CASE_RATE_MIN and BAD_CASE_RATE_MAX.
        """
        if total_evaluated <= 0:
            return False
        rate = len(self._bad_cases) / total_evaluated
        return BAD_CASE_RATE_MIN <= rate <= BAD_CASE_RATE_MAX

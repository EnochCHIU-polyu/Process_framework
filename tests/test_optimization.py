"""Tests for the O - Optimization Loop stage."""

import pytest

from process_framework.core.enums import BadCaseCategory, ScenarioType
from process_framework.core.models import EvaluationCase
from process_framework.stages.optimization import (
    BAD_CASE_RATE_MAX,
    BAD_CASE_RATE_MIN,
    OptimizationStage,
)


def _make_case() -> EvaluationCase:
    return EvaluationCase(
        scenario_type=ScenarioType.QA,
        user_input="Show me summer slim-fit options.",
        expected_output="Here are summer slim-fit dresses...",
        actual_output="Here are all our dresses...",
    )


class TestOptimizationStage:
    def setup_method(self):
        self.stage = OptimizationStage()

    def test_add_bad_case(self):
        case = _make_case()
        bc = self.stage.add_bad_case(
            evaluation_case=case,
            category=BadCaseCategory.INTENT_UNDERSTANDING,
            description="Ignored '夏季' and '顯瘦' keywords.",
            ignored_keywords=["夏季", "顯瘦"],
            improvement_suggestion="Add constraint-word training samples.",
        )
        assert bc.category == BadCaseCategory.INTENT_UNDERSTANDING
        assert "夏季" in bc.ignored_keywords
        assert len(self.stage.get_bad_cases()) == 1

    def test_add_bad_case_empty_description_raises(self):
        case = _make_case()
        with pytest.raises(ValueError, match="description"):
            self.stage.add_bad_case(
                evaluation_case=case,
                category=BadCaseCategory.HALLUCINATION,
                description="",
            )

    def test_get_bad_cases_by_category(self):
        case = _make_case()
        self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "Hallucination.")
        self.stage.add_bad_case(case, BadCaseCategory.USER_EXPERIENCE, "Too verbose.")
        self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "Another hallucination.")

        hallucinations = self.stage.get_bad_cases_by_category(BadCaseCategory.HALLUCINATION)
        assert len(hallucinations) == 2

    def test_generate_report(self):
        case = _make_case()
        self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "Hallucinated fact.")
        self.stage.add_bad_case(case, BadCaseCategory.INTENT_UNDERSTANDING, "Missed keyword.")

        report = self.stage.generate_report(
            audit_id="audit-001",
            total_evaluated=10,
            model_iteration_suggestions=["Add RAG."],
        )
        assert report.audit_id == "audit-001"
        assert report.bad_case_rate == pytest.approx(0.2)
        assert report.hallucination_count == 1
        assert report.intent_understanding_count == 1
        assert report.user_experience_count == 0
        assert "Add RAG." in report.model_iteration_suggestions

    def test_generate_report_zero_total_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            self.stage.generate_report(audit_id="x", total_evaluated=0)

    def test_category_distribution(self):
        case = _make_case()
        self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "H1")
        self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "H2")
        self.stage.add_bad_case(case, BadCaseCategory.USER_EXPERIENCE, "UX1")
        dist = self.stage.get_category_distribution()
        assert dist[BadCaseCategory.HALLUCINATION.value] == 2
        assert dist[BadCaseCategory.USER_EXPERIENCE.value] == 1

    def test_bad_case_rate_within_range(self):
        case = _make_case()
        # Add 20 bad cases out of 100 total → 20% rate, within 15–30%
        for _ in range(20):
            self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "desc")
        assert self.stage.is_bad_case_rate_within_range(total_evaluated=100) is True

    def test_bad_case_rate_outside_range(self):
        case = _make_case()
        # 1 bad case out of 100 → 1%, below 15%
        self.stage.add_bad_case(case, BadCaseCategory.HALLUCINATION, "desc")
        assert self.stage.is_bad_case_rate_within_range(total_evaluated=100) is False

"""Tests for the R - Resources stage."""

import pytest

from process_framework.core.enums import ScenarioType
from process_framework.core.models import EvaluationCase
from process_framework.stages.resources import ResourcesStage


def _make_case(scenario: ScenarioType = ScenarioType.QA) -> EvaluationCase:
    return EvaluationCase(
        scenario_type=scenario,
        user_input="What is the return policy?",
        expected_output="You can return items within 30 days.",
        actual_output="Returns accepted within 30 days.",
    )


class TestResourcesStage:
    def setup_method(self):
        self.stage = ResourcesStage()

    def test_add_case(self):
        case = _make_case()
        self.stage.add_case(case)
        assert len(self.stage.get_cases()) == 1

    def test_add_case_missing_input_raises(self):
        case = EvaluationCase(
            user_input="",
            expected_output="answer",
        )
        with pytest.raises(ValueError, match="user_input"):
            self.stage.add_case(case)

    def test_add_case_missing_expected_output_raises(self):
        case = EvaluationCase(
            user_input="question",
            expected_output="",
        )
        with pytest.raises(ValueError, match="expected_output"):
            self.stage.add_case(case)

    def test_add_multiple_cases(self):
        cases = [_make_case() for _ in range(5)]
        self.stage.add_cases(cases)
        assert len(self.stage.get_cases()) == 5

    def test_get_cases_by_scenario(self):
        self.stage.add_case(_make_case(ScenarioType.QA))
        self.stage.add_case(_make_case(ScenarioType.CASUAL_CHAT))
        self.stage.add_case(_make_case(ScenarioType.QA))
        qa_cases = self.stage.get_cases_by_scenario(ScenarioType.QA)
        assert len(qa_cases) == 2

    def test_validate_dataset_warns_low_count(self):
        # Add only 5 QA cases — below the 100 minimum
        for _ in range(5):
            self.stage.add_case(_make_case(ScenarioType.QA))
        result = self.stage.validate_dataset()
        assert not result["is_valid"]
        assert any("qa" in w for w in result["warnings"])

    def test_generate_report(self):
        for _ in range(3):
            self.stage.add_case(_make_case(ScenarioType.QA))
        report = self.stage.generate_report(audit_id="test-audit-001")
        assert report.total_cases == 3
        assert report.audit_id == "test-audit-001"
        assert report.cases_by_scenario["qa"] == 3

    def test_generate_report_missing_answers(self):
        case = EvaluationCase(
            user_input="question",
            expected_output="answer",
        )
        self.stage.add_case(case)
        report = self.stage.generate_report(audit_id="test-002")
        assert report.has_standard_answers is True

    def test_dataset_report_to_dict(self):
        self.stage.add_case(_make_case())
        report = self.stage.generate_report(audit_id="test-003")
        d = report.to_dict()
        assert "total_cases" in d
        assert "cases_by_scenario" in d

"""Tests for the S - Scrutiny stage."""

import pytest

from process_framework.core.enums import EvaluationDimension, ReviewMethod, ScoreLevel, ScenarioType
from process_framework.core.models import EvaluationCase
from process_framework.stages.scrutiny import ScrutinyStage


def _make_case(case_id: str = "case-001") -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        scenario_type=ScenarioType.QA,
        user_input="What is the return policy?",
        expected_output="30 days.",
        actual_output="30 days return window.",
    )


class TestScrutinyStage:
    def setup_method(self):
        self.stage = ScrutinyStage()

    def test_human_review_only_pass(self):
        case = _make_case()
        record = self.stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="reviewer-1",
            human_scores={
                EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_4,
                EvaluationDimension.USER_INTENT_RECOGNITION: ScoreLevel.SCORE_5,
            },
        )
        assert record.overall_verdict == "pass"
        assert record.case_id == "case-001"

    def test_human_review_fail_when_low_scores(self):
        case = _make_case()
        record = self.stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="reviewer-1",
            human_scores={
                EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_1,
                EvaluationDimension.USER_INTENT_RECOGNITION: ScoreLevel.SCORE_2,
            },
        )
        assert record.overall_verdict == "fail"

    def test_automated_filter_clear_pass(self):
        stage = ScrutinyStage(automated_filter=lambda c: True)
        case = _make_case()
        record = stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="r1",
        )
        assert record.overall_verdict == "pass"

    def test_automated_filter_clear_fail(self):
        stage = ScrutinyStage(automated_filter=lambda c: False)
        case = _make_case()
        record = stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="r1",
        )
        assert record.overall_verdict == "fail"

    def test_llm_judge_scores_recorded(self):
        def mock_llm(c):
            return {
                EvaluationDimension.ANSWER_ACCURACY.value: 4,
                EvaluationDimension.RELEVANCE.value: 5,
            }

        stage = ScrutinyStage(llm_judge=mock_llm)
        case = _make_case()
        record = stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="r1",
        )
        llm_scores = [s for s in record.scores if s.reviewer_id == "llm_judge"]
        assert len(llm_scores) == 2

    def test_force_human_review_skips_automation(self):
        # Even with a clear-pass filter, force_human_review should use human scores
        stage = ScrutinyStage(automated_filter=lambda c: True)
        case = _make_case()
        record = stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="r1",
            human_scores={
                EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_1,
            },
            force_human_review=True,
        )
        assert record.overall_verdict == "fail"

    def test_review_must_pass_set(self):
        cases = [_make_case(f"case-{i}") for i in range(3)]
        scores_per_case = {
            f"case-{i}": {EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_4}
            for i in range(3)
        }
        records = self.stage.review_must_pass_set(
            audit_id="audit-001",
            cases=cases,
            reviewer_id="r1",
            scores_per_case=scores_per_case,
        )
        assert len(records) == 3
        assert all(r.overall_verdict == "pass" for r in records)

    def test_get_review_summary(self):
        case = _make_case()
        self.stage.review_case(
            audit_id="audit-001",
            case=case,
            reviewer_id="r1",
            human_scores={EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_5},
        )
        summary = self.stage.get_review_summary()
        assert summary["total"] == 1
        assert summary["passed"] == 1
        assert summary["pass_rate"] == pytest.approx(1.0)
        assert ReviewMethod.HUMAN_REVIEW.value in summary["methods_used"]

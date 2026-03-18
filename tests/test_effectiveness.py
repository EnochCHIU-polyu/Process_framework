"""Tests for the E - Effectiveness stage."""

import pytest

from process_framework.core.enums import EvaluationDimension, ScoreLevel
from process_framework.core.models import EvaluationScore
from process_framework.stages.effectiveness import PASSING_SCORE, EffectivenessStage


def _make_score(
    dimension: EvaluationDimension = EvaluationDimension.ANSWER_ACCURACY,
    score: ScoreLevel = ScoreLevel.SCORE_4,
    case_id: str = "case-001",
) -> EvaluationScore:
    return EvaluationScore(
        case_id=case_id,
        dimension=dimension,
        score=score,
        reviewer_id="reviewer-1",
    )


class TestEffectivenessStage:
    def setup_method(self):
        self.stage = EffectivenessStage()

    def test_add_score(self):
        self.stage.add_score(_make_score())
        assert len(self.stage.get_scores()) == 1

    def test_add_multiple_scores(self):
        scores = [_make_score() for _ in range(5)]
        self.stage.add_scores(scores)
        assert len(self.stage.get_scores()) == 5

    def test_compute_overall_score_empty(self):
        assert self.stage.compute_overall_score() == 0.0

    def test_compute_overall_score(self):
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_4))
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_2))
        # Average of 4 and 2 = 3.0
        assert self.stage.compute_overall_score() == pytest.approx(3.0)

    def test_compute_pass_rate_empty(self):
        assert self.stage.compute_pass_rate() == 0.0

    def test_compute_pass_rate(self):
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_5))  # pass
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_3))  # pass
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_2))  # fail
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_1))  # fail
        assert self.stage.compute_pass_rate() == pytest.approx(0.5)

    def test_compute_dimension_averages(self):
        self.stage.add_score(
            _make_score(dimension=EvaluationDimension.ANSWER_ACCURACY, score=ScoreLevel.SCORE_4)
        )
        self.stage.add_score(
            _make_score(dimension=EvaluationDimension.ANSWER_ACCURACY, score=ScoreLevel.SCORE_2)
        )
        avgs = self.stage.compute_dimension_averages()
        assert avgs[EvaluationDimension.ANSWER_ACCURACY.value] == pytest.approx(3.0)

    def test_compute_category_averages(self):
        # Add scores for system capability dimensions
        self.stage.add_score(
            _make_score(dimension=EvaluationDimension.ANSWER_ACCURACY, score=ScoreLevel.SCORE_4)
        )
        self.stage.add_score(
            _make_score(dimension=EvaluationDimension.USER_INTENT_RECOGNITION, score=ScoreLevel.SCORE_4)
        )
        cat_avgs = self.stage.compute_category_averages()
        assert cat_avgs["system_capability"] == pytest.approx(4.0)

    def test_generate_report(self):
        self.stage.add_score(_make_score(score=ScoreLevel.SCORE_4))
        report = self.stage.generate_report(audit_id="audit-001")
        assert report.audit_id == "audit-001"
        assert report.overall_score == pytest.approx(4.0)
        assert report.pass_rate == pytest.approx(1.0)

    def test_report_to_dict(self):
        self.stage.add_score(_make_score())
        report = self.stage.generate_report(audit_id="audit-002")
        d = report.to_dict()
        assert "overall_score" in d
        assert "pass_rate" in d
        assert "dimension_scores" in d

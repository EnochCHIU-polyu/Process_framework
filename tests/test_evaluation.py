"""Tests for the evaluation utilities (metrics, scoring, bad case analyzer)."""

import pytest

from process_framework.core.enums import (
    BadCaseCategory,
    EvaluationDimension,
    ScenarioType,
    ScoreLevel,
)
from process_framework.core.models import BadCase, EvaluationCase, EvaluationScore
from process_framework.evaluation.bad_cases import BadCaseAnalyzer
from process_framework.evaluation.metrics import MetricsCalculator
from process_framework.evaluation.scoring import ScoringEngine


def _make_score(
    dimension: EvaluationDimension = EvaluationDimension.ANSWER_ACCURACY,
    score: ScoreLevel = ScoreLevel.SCORE_4,
    case_id: str = "case-001",
    reviewer_id: str = "r1",
) -> EvaluationScore:
    return EvaluationScore(
        case_id=case_id,
        dimension=dimension,
        score=score,
        reviewer_id=reviewer_id,
    )


def _make_bad_case(
    category: BadCaseCategory = BadCaseCategory.HALLUCINATION,
    ignored_keywords: list = None,
) -> BadCase:
    case = EvaluationCase(
        scenario_type=ScenarioType.QA,
        user_input="question",
        expected_output="expected",
        actual_output="actual",
    )
    return BadCase(
        evaluation_case=case,
        category=category,
        ignored_keywords=ignored_keywords or [],
        description="A bad case.",
    )


class TestMetricsCalculator:
    def test_average_score_empty(self):
        assert MetricsCalculator.average_score([]) == 0.0

    def test_average_score(self):
        scores = [_make_score(score=ScoreLevel.SCORE_4), _make_score(score=ScoreLevel.SCORE_2)]
        assert MetricsCalculator.average_score(scores) == pytest.approx(3.0)

    def test_pass_rate_empty(self):
        assert MetricsCalculator.pass_rate([]) == 0.0

    def test_pass_rate(self):
        scores = [
            _make_score(score=ScoreLevel.SCORE_5),
            _make_score(score=ScoreLevel.SCORE_3),
            _make_score(score=ScoreLevel.SCORE_2),
        ]
        assert MetricsCalculator.pass_rate(scores) == pytest.approx(2 / 3)

    def test_by_dimension(self):
        scores = [
            _make_score(dimension=EvaluationDimension.ANSWER_ACCURACY, score=ScoreLevel.SCORE_4),
            _make_score(dimension=EvaluationDimension.ANSWER_ACCURACY, score=ScoreLevel.SCORE_2),
            _make_score(dimension=EvaluationDimension.RELEVANCE, score=ScoreLevel.SCORE_5),
        ]
        result = MetricsCalculator.by_dimension(scores)
        assert result[EvaluationDimension.ANSWER_ACCURACY.value] == pytest.approx(3.0)
        assert result[EvaluationDimension.RELEVANCE.value] == pytest.approx(5.0)

    def test_by_reviewer(self):
        scores = [
            _make_score(reviewer_id="r1", score=ScoreLevel.SCORE_5),
            _make_score(reviewer_id="r1", score=ScoreLevel.SCORE_3),
            _make_score(reviewer_id="r2", score=ScoreLevel.SCORE_2),
        ]
        result = MetricsCalculator.by_reviewer(scores)
        assert result["r1"] == pytest.approx(4.0)
        assert result["r2"] == pytest.approx(2.0)

    def test_score_distribution(self):
        scores = [
            _make_score(score=ScoreLevel.SCORE_5),
            _make_score(score=ScoreLevel.SCORE_5),
            _make_score(score=ScoreLevel.SCORE_3),
        ]
        dist = MetricsCalculator.score_distribution(scores)
        assert dist[5] == 2
        assert dist[3] == 1
        assert dist[1] == 0

    def test_score_distribution_by_dimension(self):
        scores = [
            _make_score(dimension=EvaluationDimension.ANSWER_ACCURACY, score=ScoreLevel.SCORE_4),
            _make_score(dimension=EvaluationDimension.RELEVANCE, score=ScoreLevel.SCORE_5),
        ]
        dist = MetricsCalculator.score_distribution(
            scores, dimension=EvaluationDimension.ANSWER_ACCURACY
        )
        assert dist[4] == 1
        assert dist[5] == 0


class TestScoringEngine:
    def setup_method(self):
        self.engine = ScoringEngine()

    def test_record_score(self):
        score = self.engine.record_score(
            case_id="c1",
            dimension=EvaluationDimension.ANSWER_ACCURACY,
            score=ScoreLevel.SCORE_4,
            reviewer_id="r1",
        )
        assert score.case_id == "c1"
        assert score.score == ScoreLevel.SCORE_4

    def test_record_scores_from_dict(self):
        scores = self.engine.record_scores_from_dict(
            case_id="c1",
            scores={
                EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_4,
                EvaluationDimension.RELEVANCE: ScoreLevel.SCORE_3,
            },
            reviewer_id="r1",
        )
        assert len(scores) == 2

    def test_get_scores_for_case(self):
        self.engine.record_score("c1", EvaluationDimension.ANSWER_ACCURACY, ScoreLevel.SCORE_4, "r1")
        self.engine.record_score("c2", EvaluationDimension.RELEVANCE, ScoreLevel.SCORE_5, "r1")
        assert len(self.engine.get_scores_for_case("c1")) == 1

    def test_get_case_average(self):
        self.engine.record_score("c1", EvaluationDimension.ANSWER_ACCURACY, ScoreLevel.SCORE_4, "r1")
        self.engine.record_score("c1", EvaluationDimension.RELEVANCE, ScoreLevel.SCORE_2, "r1")
        avg = self.engine.get_case_average("c1")
        assert avg == pytest.approx(3.0)

    def test_get_case_average_none_for_missing(self):
        assert self.engine.get_case_average("nonexistent") is None


class TestBadCaseAnalyzer:
    def setup_method(self):
        self.analyzer = BadCaseAnalyzer()

    def test_summarize(self):
        bad_cases = [
            _make_bad_case(BadCaseCategory.HALLUCINATION),
            _make_bad_case(BadCaseCategory.INTENT_UNDERSTANDING, ["夏季", "顯瘦"]),
            _make_bad_case(BadCaseCategory.INTENT_UNDERSTANDING, ["夏季"]),
        ]
        summary = self.analyzer.summarize(bad_cases)
        assert summary["total"] == 3
        assert summary["by_category"][BadCaseCategory.HALLUCINATION.value] == 1
        assert summary["by_category"][BadCaseCategory.INTENT_UNDERSTANDING.value] == 2
        # "夏季" appeared twice — should be the top keyword
        top_kw = dict(summary["top_ignored_keywords"])
        assert top_kw.get("夏季", 0) == 2

    def test_get_suggestions_for_category(self):
        suggestion = self.analyzer.get_suggestions_for_category(BadCaseCategory.HALLUCINATION)
        assert len(suggestion) > 0

    def test_filter_by_keyword(self):
        bad_cases = [
            _make_bad_case(BadCaseCategory.INTENT_UNDERSTANDING, ["夏季"]),
            _make_bad_case(BadCaseCategory.INTENT_UNDERSTANDING, ["顯瘦"]),
            _make_bad_case(BadCaseCategory.HALLUCINATION),
        ]
        filtered = self.analyzer.filter_by_keyword(bad_cases, "夏季")
        assert len(filtered) == 1

    def test_prioritise_categories(self):
        bad_cases = [
            _make_bad_case(BadCaseCategory.HALLUCINATION),
            _make_bad_case(BadCaseCategory.HALLUCINATION),
            _make_bad_case(BadCaseCategory.USER_EXPERIENCE),
        ]
        priority = self.analyzer.prioritise_categories(bad_cases)
        assert priority[0] == BadCaseCategory.HALLUCINATION.value

"""Tests for the S - Standards stage."""

import pytest

from process_framework.core.enums import EvaluationDimension, ScoreLevel
from process_framework.stages.standards import (
    DEFAULT_RUBRIC,
    DIMENSION_SCORE_1_DESCRIPTIONS,
    StandardsStage,
)


class TestStandardsStage:
    def setup_method(self):
        self.stage = StandardsStage()

    def test_get_rubric_default(self):
        rubric = self.stage.get_rubric(EvaluationDimension.ANSWER_ACCURACY)
        # Should have entries for all five levels
        assert set(rubric.keys()) == {1, 2, 3, 4, 5}

    def test_get_rubric_uses_dimension_score1_override(self):
        rubric = self.stage.get_rubric(EvaluationDimension.ANSWER_ACCURACY)
        # Score 1 for ANSWER_ACCURACY should use the dimension-specific text
        assert rubric[1] == DIMENSION_SCORE_1_DESCRIPTIONS[EvaluationDimension.ANSWER_ACCURACY.value]

    def test_get_rubric_fallback_to_default_for_no_override(self):
        rubric = self.stage.get_rubric(EvaluationDimension.COMPLETENESS)
        # COMPLETENESS has no dimension-specific score-1; should use default
        assert rubric[1] == DEFAULT_RUBRIC[1]

    def test_set_custom_rubric(self):
        self.stage.set_custom_rubric(
            EvaluationDimension.ANSWER_ACCURACY,
            ScoreLevel.SCORE_5,
            "Custom: Perfectly correct and concise.",
        )
        desc = self.stage.get_score_description(
            EvaluationDimension.ANSWER_ACCURACY, ScoreLevel.SCORE_5
        )
        assert desc == "Custom: Perfectly correct and concise."

    def test_set_custom_rubric_empty_description_raises(self):
        with pytest.raises(ValueError, match="empty"):
            self.stage.set_custom_rubric(
                EvaluationDimension.ANSWER_ACCURACY,
                ScoreLevel.SCORE_3,
                "",
            )

    def test_export_handbook_contains_all_dimensions(self):
        handbook = self.stage.export_handbook()
        for dim in EvaluationDimension:
            assert dim.value in handbook
            assert set(handbook[dim.value].keys()) == {1, 2, 3, 4, 5}

    def test_validate_score_valid(self):
        for score in range(1, 6):
            assert self.stage.validate_score(score) is True

    def test_validate_score_out_of_range(self):
        assert self.stage.validate_score(0) is False
        assert self.stage.validate_score(6) is False
        assert self.stage.validate_score(-1) is False

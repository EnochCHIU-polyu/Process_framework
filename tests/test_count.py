"""Tests for the C - Count stage."""

import pytest

from process_framework.core.enums import AuditType, ScenarioType
from process_framework.stages.count import (
    DEFAULT_CASES_PER_SCENARIO,
    MIN_HIGH_FREQUENCY_COUNT,
    MIN_MUST_PASS_COUNT,
    CountStage,
)


class TestCountStage:
    def setup_method(self):
        self.stage = CountStage()

    def test_plan_count_new_product_defaults(self):
        plan = self.stage.plan_count(
            audit_id="audit-001",
            audit_type=AuditType.NEW_PRODUCT,
        )
        assert plan.audit_type == AuditType.NEW_PRODUCT
        assert plan.must_pass_count == MIN_MUST_PASS_COUNT
        assert plan.high_frequency_count == MIN_HIGH_FREQUENCY_COUNT
        assert plan.scenario_counts[ScenarioType.QA.value] == DEFAULT_CASES_PER_SCENARIO

    def test_plan_count_optimization_uses_lower_must_pass(self):
        plan = self.stage.plan_count(
            audit_id="audit-002",
            audit_type=AuditType.OPTIMIZATION,
        )
        min_opt = self.stage.minimum_must_pass_count(AuditType.OPTIMIZATION)
        assert plan.must_pass_count == min_opt
        assert plan.must_pass_count < MIN_MUST_PASS_COUNT

    def test_plan_count_custom_cases_per_scenario(self):
        plan = self.stage.plan_count(
            audit_id="audit-003",
            audit_type=AuditType.NEW_PRODUCT,
            cases_per_scenario=120,
        )
        for count in plan.scenario_counts.values():
            assert count == 120

    def test_plan_count_negative_must_pass_raises(self):
        with pytest.raises(ValueError, match="negative"):
            self.stage.plan_count(
                audit_id="x",
                audit_type=AuditType.NEW_PRODUCT,
                must_pass_count=-1,
            )

    def test_plan_count_negative_high_frequency_raises(self):
        with pytest.raises(ValueError, match="negative"):
            self.stage.plan_count(
                audit_id="x",
                audit_type=AuditType.NEW_PRODUCT,
                high_frequency_count=-1,
            )

    def test_total_count_is_sum_of_parts(self):
        plan = self.stage.plan_count(
            audit_id="audit-004",
            audit_type=AuditType.NEW_PRODUCT,
            cases_per_scenario=100,
        )
        expected = sum(plan.scenario_counts.values()) + plan.must_pass_count + plan.high_frequency_count
        assert plan.total_count == expected

    def test_count_plan_to_dict(self):
        plan = self.stage.plan_count(
            audit_id="audit-005",
            audit_type=AuditType.OPTIMIZATION,
        )
        d = plan.to_dict()
        assert d["audit_type"] == "optimization"
        assert "total_count" in d
        assert "scenario_counts" in d

    def test_minimum_must_pass_count_new_product(self):
        assert self.stage.minimum_must_pass_count(AuditType.NEW_PRODUCT) == MIN_MUST_PASS_COUNT

    def test_minimum_must_pass_count_optimization(self):
        opt_min = self.stage.minimum_must_pass_count(AuditType.OPTIMIZATION)
        assert opt_min < MIN_MUST_PASS_COUNT
        assert opt_min > 0

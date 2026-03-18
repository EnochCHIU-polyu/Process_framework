"""Tests for the P - Purpose stage."""

import pytest

from process_framework.core.enums import AuditType
from process_framework.stages.purpose import PurposeStage


class TestPurposeStage:
    def setup_method(self):
        self.stage = PurposeStage()

    def test_define_scope_new_product(self):
        scope = self.stage.define_scope(
            audit_type=AuditType.NEW_PRODUCT,
            description="Launch chatbot v1",
            must_pass_set=["greeting", "product_query"],
            high_frequency_issues=["refund", "delivery"],
            hallucination_mitigation_kpi=0.99,
        )
        assert scope.audit_type == AuditType.NEW_PRODUCT
        assert scope.description == "Launch chatbot v1"
        assert "greeting" in scope.must_pass_set
        assert scope.hallucination_mitigation_kpi == 0.99

    def test_define_scope_optimization(self):
        scope = self.stage.define_scope(
            audit_type=AuditType.OPTIMIZATION,
            description="Improve seasonal query handling",
            hallucination_mitigation_kpi=0.90,
        )
        assert scope.audit_type == AuditType.OPTIMIZATION

    def test_new_product_kpi_below_minimum_raises(self):
        with pytest.raises(ValueError, match="hallucination mitigation KPI"):
            self.stage.define_scope(
                audit_type=AuditType.NEW_PRODUCT,
                description="Bad KPI",
                hallucination_mitigation_kpi=0.95,
            )

    def test_optimization_allows_lower_kpi(self):
        # Should not raise for optimization audits
        scope = self.stage.define_scope(
            audit_type=AuditType.OPTIMIZATION,
            description="Optimise",
            hallucination_mitigation_kpi=0.85,
        )
        assert scope.hallucination_mitigation_kpi == 0.85

    def test_create_audit_plan(self):
        scope = self.stage.define_scope(
            audit_type=AuditType.NEW_PRODUCT,
            description="Plan test",
        )
        plan = self.stage.create_audit_plan(
            scope=scope,
            total_sample_size=500,
            must_pass_sample_size=50,
            high_frequency_sample_size=30,
        )
        assert plan.total_sample_size == 500
        assert plan.must_pass_sample_size == 50
        assert plan.high_frequency_sample_size == 30
        assert plan.scope is scope

    def test_create_audit_plan_zero_total_raises(self):
        scope = self.stage.define_scope(
            audit_type=AuditType.NEW_PRODUCT,
            description="test",
        )
        with pytest.raises(ValueError, match="positive integer"):
            self.stage.create_audit_plan(
                scope=scope,
                total_sample_size=0,
                must_pass_sample_size=0,
                high_frequency_sample_size=0,
            )

    def test_create_audit_plan_excess_subset_raises(self):
        scope = self.stage.define_scope(
            audit_type=AuditType.NEW_PRODUCT,
            description="test",
        )
        with pytest.raises(ValueError, match="cannot exceed"):
            self.stage.create_audit_plan(
                scope=scope,
                total_sample_size=50,
                must_pass_sample_size=40,
                high_frequency_sample_size=20,
            )

    def test_scope_to_dict(self):
        scope = self.stage.define_scope(
            audit_type=AuditType.NEW_PRODUCT,
            description="Dict test",
        )
        d = scope.to_dict()
        assert d["audit_type"] == "new_product"
        assert "audit_id" in d
        assert "created_at" in d

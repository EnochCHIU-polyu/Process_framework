"""Integration tests for the full PROCESS framework orchestrator."""

import pytest

from process_framework.core.enums import (
    AuditType,
    BadCaseCategory,
    EvaluationDimension,
    ScenarioType,
    ScoreLevel,
)
from process_framework.core.models import EvaluationCase, EvaluationScore
from process_framework.framework import ProcessFramework


def _make_case(i: int = 0) -> EvaluationCase:
    return EvaluationCase(
        scenario_type=ScenarioType.QA,
        user_input=f"Question {i}",
        expected_output=f"Answer {i}",
        actual_output=f"Response {i}",
    )


class TestProcessFramework:
    def setup_method(self):
        self.fw = ProcessFramework(audit_type=AuditType.NEW_PRODUCT)

    def test_setup_purpose(self):
        plan = self.fw.setup_purpose(
            description="New chatbot launch",
            must_pass_set=["greeting", "order_query"],
            high_frequency_issues=["refund", "shipping"],
        )
        assert plan.scope.audit_type == AuditType.NEW_PRODUCT
        assert plan.total_sample_size == 500

    def test_add_evaluation_cases_and_dataset_report(self):
        self.fw.setup_purpose(description="Test")
        cases = [_make_case(i) for i in range(5)]
        self.fw.add_evaluation_cases(cases)
        report = self.fw.build_dataset_report(representativeness_notes="Test dataset.")
        assert report.total_cases == 5

    def test_record_bad_case_and_report(self):
        self.fw.setup_purpose(description="Test")
        case = _make_case()
        self.fw.record_bad_case(
            evaluation_case=case,
            category=BadCaseCategory.HALLUCINATION,
            description="Model hallucinated a product.",
            ignored_keywords=[],
            improvement_suggestion="Add RAG.",
        )
        report = self.fw.build_bad_case_report(
            total_evaluated=10,
            model_iteration_suggestions=["Prioritise hallucination reduction."],
        )
        assert report.hallucination_count == 1
        assert "Prioritise hallucination reduction." in report.model_iteration_suggestions

    def test_plan_evaluation_count(self):
        self.fw.setup_purpose(description="Test")
        count_plan = self.fw.plan_evaluation_count()
        assert count_plan.total_count > 0

    def test_add_scores_and_effectiveness_report(self):
        self.fw.setup_purpose(description="Test")
        scores = [
            EvaluationScore(
                case_id="c1",
                dimension=EvaluationDimension.ANSWER_ACCURACY,
                score=ScoreLevel.SCORE_4,
                reviewer_id="r1",
            )
        ]
        self.fw.add_evaluation_scores(scores)
        report = self.fw.build_effectiveness_report()
        assert report.overall_score == pytest.approx(4.0)

    def test_get_scoring_handbook(self):
        handbook = self.fw.get_scoring_handbook()
        assert EvaluationDimension.ANSWER_ACCURACY.value in handbook

    def test_review_case(self):
        self.fw.setup_purpose(description="Test")
        case = _make_case()
        record = self.fw.review_case(
            case=case,
            reviewer_id="r1",
            human_scores={EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_5},
        )
        assert record.overall_verdict == "pass"

    def test_generate_full_report(self):
        plan = self.fw.setup_purpose(description="Full report test")
        cases = [_make_case(i) for i in range(3)]
        self.fw.add_evaluation_cases(cases)
        self.fw.build_dataset_report()
        self.fw.record_bad_case(cases[0], BadCaseCategory.HALLUCINATION, "Hallucination.")
        self.fw.build_bad_case_report(total_evaluated=3)
        self.fw.plan_evaluation_count()
        self.fw.add_evaluation_scores([
            EvaluationScore(
                case_id=cases[0].case_id,
                dimension=EvaluationDimension.ANSWER_ACCURACY,
                score=ScoreLevel.SCORE_4,
                reviewer_id="r1",
            )
        ])
        self.fw.build_effectiveness_report()
        self.fw.review_case(
            case=cases[0],
            reviewer_id="r1",
            human_scores={EvaluationDimension.ANSWER_ACCURACY: ScoreLevel.SCORE_4},
        )

        full_report = self.fw.generate_full_report()
        assert full_report["title"] == "PROCESS AI 審核完整報告"
        assert full_report["sections"]["P_Purpose"] is not None
        assert full_report["sections"]["R_Resources"] is not None
        assert full_report["sections"]["O_Optimization"] is not None
        assert full_report["sections"]["C_Count"] is not None
        assert full_report["sections"]["E_Effectiveness"] is not None
        assert full_report["sections"]["S_Scrutiny"] is not None
        assert "overall_risk_level" in full_report

    def test_framework_without_purpose_gives_empty_audit_id(self):
        # Should not crash when generating a report without setup_purpose
        report = self.fw.generate_full_report()
        assert report["audit_id"] == ""

    def test_optimization_audit_type_allows_lower_kpi(self):
        fw = ProcessFramework(audit_type=AuditType.OPTIMIZATION)
        plan = fw.setup_purpose(
            description="Optimization run",
            hallucination_mitigation_kpi=0.90,
        )
        assert plan.scope.hallucination_mitigation_kpi == pytest.approx(0.90)

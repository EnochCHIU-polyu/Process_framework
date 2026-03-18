"""
ProcessFramework — top-level orchestrator for the PROCESS AI Review Framework.

Provides a single entry point that wires all seven stages together and
exposes convenience methods for running a complete end-to-end audit.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from process_framework.core.enums import AuditType, BadCaseCategory, EvaluationDimension, ScoreLevel
from process_framework.core.models import (
    AuditPlan,
    BadCaseAnalysisReport,
    CountPlan,
    DatasetReport,
    EffectivenessReport,
    EvaluationCase,
    EvaluationScore,
    ManualEvaluationRecord,
)
from process_framework.evaluation.bad_cases import BadCaseAnalyzer
from process_framework.evaluation.metrics import MetricsCalculator
from process_framework.evaluation.scoring import ScoringEngine
from process_framework.reporting.reports import ReportGenerator
from process_framework.stages.count import CountStage
from process_framework.stages.effectiveness import EffectivenessStage
from process_framework.stages.optimization import OptimizationStage
from process_framework.stages.purpose import PurposeStage
from process_framework.stages.resources import ResourcesStage
from process_framework.stages.scrutiny import ScrutinyStage
from process_framework.stages.standards import StandardsStage


class ProcessFramework:
    """
    Orchestrates all seven PROCESS stages for an AI system audit.

    Usage::

        framework = ProcessFramework(audit_type=AuditType.NEW_PRODUCT)
        framework.setup_purpose(description="Launch chatbot v2")
        framework.add_evaluation_cases(cases)
        # ... add scores, bad cases, etc.
        report = framework.generate_full_report()
    """

    def __init__(
        self,
        audit_type: AuditType = AuditType.NEW_PRODUCT,
        automated_filter: Optional[Callable] = None,
        llm_judge: Optional[Callable] = None,
    ) -> None:
        self.audit_type = audit_type

        # Initialise all stages
        self.purpose = PurposeStage()
        self.resources = ResourcesStage()
        self.optimization = OptimizationStage()
        self.count = CountStage()
        self.effectiveness = EffectivenessStage()
        self.standards = StandardsStage()
        self.scrutiny = ScrutinyStage(
            automated_filter=automated_filter,
            llm_judge=llm_judge,
        )

        # Utility components
        self.scoring_engine = ScoringEngine()
        self.metrics = MetricsCalculator()
        self.bad_case_analyzer = BadCaseAnalyzer()
        self.reporter = ReportGenerator()

        # Persisted stage outputs
        self._audit_plan: Optional[AuditPlan] = None
        self._dataset_report: Optional[DatasetReport] = None
        self._bad_case_report: Optional[BadCaseAnalysisReport] = None
        self._count_plan: Optional[CountPlan] = None
        self._effectiveness_report: Optional[EffectivenessReport] = None
        self._audit_id: str = ""

    # ------------------------------------------------------------------
    # P - Purpose
    # ------------------------------------------------------------------

    def setup_purpose(
        self,
        description: str,
        must_pass_set: Optional[List[str]] = None,
        high_frequency_issues: Optional[List[str]] = None,
        hallucination_mitigation_kpi: float = 0.99,
        total_sample_size: int = 500,
        must_pass_sample_size: int = 50,
        high_frequency_sample_size: int = 30,
    ) -> AuditPlan:
        """
        P stage: Define the audit scope and create the master AuditPlan.

        Args:
            description: Human-readable description of the audit goals.
            must_pass_set: Critical scenarios that must pass.
            high_frequency_issues: High-frequency topics to cover.
            hallucination_mitigation_kpi: Target KPI for hallucination reduction.
            total_sample_size: Total evaluation cases planned.
            must_pass_sample_size: Must-pass set size.
            high_frequency_sample_size: High-frequency set size.

        Returns:
            AuditPlan — the master planning document.
        """
        scope = self.purpose.define_scope(
            audit_type=self.audit_type,
            description=description,
            must_pass_set=must_pass_set,
            high_frequency_issues=high_frequency_issues,
            hallucination_mitigation_kpi=hallucination_mitigation_kpi,
        )
        self._audit_plan = self.purpose.create_audit_plan(
            scope=scope,
            total_sample_size=total_sample_size,
            must_pass_sample_size=must_pass_sample_size,
            high_frequency_sample_size=high_frequency_sample_size,
        )
        self._audit_id = self._audit_plan.plan_id
        return self._audit_plan

    # ------------------------------------------------------------------
    # R - Resources
    # ------------------------------------------------------------------

    def add_evaluation_cases(self, cases: List[EvaluationCase]) -> None:
        """R stage: Add evaluation cases to the working dataset."""
        self.resources.add_cases(cases)

    def build_dataset_report(
        self, representativeness_notes: Optional[str] = None
    ) -> DatasetReport:
        """R stage: Generate the 《評估數據集報告》."""
        self._dataset_report = self.resources.generate_report(
            audit_id=self._audit_id,
            representativeness_notes=representativeness_notes,
        )
        return self._dataset_report

    # ------------------------------------------------------------------
    # O - Optimization
    # ------------------------------------------------------------------

    def record_bad_case(
        self,
        evaluation_case: EvaluationCase,
        category: BadCaseCategory,
        description: str,
        ignored_keywords: Optional[List[str]] = None,
        improvement_suggestion: str = "",
    ) -> None:
        """O stage: Record a bad case with root-cause attribution."""
        self.optimization.add_bad_case(
            evaluation_case=evaluation_case,
            category=category,
            description=description,
            ignored_keywords=ignored_keywords,
            improvement_suggestion=improvement_suggestion,
        )

    def build_bad_case_report(
        self,
        total_evaluated: int,
        model_iteration_suggestions: Optional[List[str]] = None,
    ) -> BadCaseAnalysisReport:
        """O stage: Generate the 《壞案例歸因分析報告》."""
        self._bad_case_report = self.optimization.generate_report(
            audit_id=self._audit_id,
            total_evaluated=total_evaluated,
            model_iteration_suggestions=model_iteration_suggestions,
        )
        return self._bad_case_report

    # ------------------------------------------------------------------
    # C - Count
    # ------------------------------------------------------------------

    def plan_evaluation_count(
        self,
        cases_per_scenario: Optional[int] = None,
        statistical_notes: str = "",
    ) -> CountPlan:
        """C stage: Generate the 《評估數量規劃表》."""
        self._count_plan = self.count.plan_count(
            audit_id=self._audit_id,
            audit_type=self.audit_type,
            cases_per_scenario=cases_per_scenario,
            statistical_notes=statistical_notes,
        )
        return self._count_plan

    # ------------------------------------------------------------------
    # E - Effectiveness
    # ------------------------------------------------------------------

    def add_evaluation_scores(self, scores: List[EvaluationScore]) -> None:
        """E stage: Add evaluation dimension scores."""
        self.effectiveness.add_scores(scores)

    def build_effectiveness_report(self) -> EffectivenessReport:
        """E stage: Generate the 《多維度評估指標得分表》."""
        self._effectiveness_report = self.effectiveness.generate_report(
            audit_id=self._audit_id
        )
        return self._effectiveness_report

    # ------------------------------------------------------------------
    # S - Standards (access the rubric handbook)
    # ------------------------------------------------------------------

    def get_scoring_handbook(self) -> Dict:
        """S stage: Export the complete 《評分標準手冊》."""
        return self.standards.export_handbook()

    # ------------------------------------------------------------------
    # S - Scrutiny
    # ------------------------------------------------------------------

    def review_case(
        self,
        case: EvaluationCase,
        reviewer_id: str,
        human_scores: Optional[Dict[EvaluationDimension, ScoreLevel]] = None,
        annotation: str = "",
        force_human_review: bool = False,
    ) -> ManualEvaluationRecord:
        """S stage: Review a single case through the three-tier pipeline."""
        return self.scrutiny.review_case(
            audit_id=self._audit_id,
            case=case,
            reviewer_id=reviewer_id,
            human_scores=human_scores,
            annotation=annotation,
            force_human_review=force_human_review,
        )

    # ------------------------------------------------------------------
    # Full report
    # ------------------------------------------------------------------

    def generate_full_report(self) -> Dict:
        """
        Aggregate all stage outputs into the complete PROCESS audit report.

        Returns:
            Full PROCESS report dict with all stage sections.
        """
        return self.reporter.full_process_report(
            audit_plan=self._audit_plan,
            dataset_report=self._dataset_report,
            bad_case_report=self._bad_case_report,
            count_plan=self._count_plan,
            effectiveness_report=self._effectiveness_report,
            evaluation_records=self.scrutiny.get_records(),
            audit_id=self._audit_id,
        )

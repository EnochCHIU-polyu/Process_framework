"""Core data models for the PROCESS AI Review Framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from process_framework.core.enums import (
    AuditType,
    BadCaseCategory,
    EvaluationDimension,
    ScoreLevel,
    ScenarioType,
)


@dataclass
class AuditScope:
    """
    Defines the scope and objectives of a PROCESS audit.
    Output of the P (Purpose) stage — 《審核範圍與目標文件》.
    """

    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_type: AuditType = AuditType.NEW_PRODUCT
    description: str = ""
    must_pass_set: List[str] = field(default_factory=list)       # 必須通過集
    high_frequency_issues: List[str] = field(default_factory=list)  # 高頻問題集
    hallucination_mitigation_kpi: float = 0.99                   # 幻覺緩解KPI
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "audit_id": self.audit_id,
            "audit_type": self.audit_type.value,
            "description": self.description,
            "must_pass_set": self.must_pass_set,
            "high_frequency_issues": self.high_frequency_issues,
            "hallucination_mitigation_kpi": self.hallucination_mitigation_kpi,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvaluationCase:
    """
    A single evaluation case with input, expected output, and actual output.
    Used across R, O, and S stages.
    """

    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_type: ScenarioType = ScenarioType.QA
    user_input: str = ""
    expected_output: str = ""
    actual_output: str = ""
    metadata: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id,
            "scenario_type": self.scenario_type.value,
            "user_input": self.user_input,
            "expected_output": self.expected_output,
            "actual_output": self.actual_output,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BadCase:
    """
    A bad case with root-cause attribution.
    Output of the O (Optimization Loop) stage.
    """

    bad_case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evaluation_case: Optional[EvaluationCase] = None
    category: BadCaseCategory = BadCaseCategory.HALLUCINATION
    ignored_keywords: List[str] = field(default_factory=list)    # 被忽略的關鍵詞
    description: str = ""
    improvement_suggestion: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "bad_case_id": self.bad_case_id,
            "evaluation_case": self.evaluation_case.to_dict() if self.evaluation_case else None,
            "category": self.category.value,
            "ignored_keywords": self.ignored_keywords,
            "description": self.description,
            "improvement_suggestion": self.improvement_suggestion,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvaluationScore:
    """
    A single dimension score for an evaluation case.
    Used in E (Effectiveness) and S (Standards) stages.
    """

    score_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str = ""
    dimension: EvaluationDimension = EvaluationDimension.ANSWER_ACCURACY
    score: ScoreLevel = ScoreLevel.SCORE_3
    reviewer_id: str = ""
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "score_id": self.score_id,
            "case_id": self.case_id,
            "dimension": self.dimension.value,
            "score": self.score.value,
            "reviewer_id": self.reviewer_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AuditPlan:
    """
    PROCESS Audit Plan — the master planning document.
    Aggregates outputs from P, C stages.
    """

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scope: Optional[AuditScope] = None
    total_sample_size: int = 0
    must_pass_sample_size: int = 0
    high_frequency_sample_size: int = 0
    must_pass_threshold: float = 0.99          # 99% 正確率
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "plan_id": self.plan_id,
            "scope": self.scope.to_dict() if self.scope else None,
            "total_sample_size": self.total_sample_size,
            "must_pass_sample_size": self.must_pass_sample_size,
            "high_frequency_sample_size": self.high_frequency_sample_size,
            "must_pass_threshold": self.must_pass_threshold,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class DatasetReport:
    """
    Evaluation Dataset Report — output of the R (Resources) stage.
    《評估數據集報告》
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str = ""
    cases_by_scenario: Dict[str, int] = field(default_factory=dict)
    total_cases: int = 0
    has_standard_answers: bool = True
    representativeness_notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "audit_id": self.audit_id,
            "cases_by_scenario": self.cases_by_scenario,
            "total_cases": self.total_cases,
            "has_standard_answers": self.has_standard_answers,
            "representativeness_notes": self.representativeness_notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class BadCaseAnalysisReport:
    """
    Bad Case Root-Cause Analysis Report — output of the O (Optimization) stage.
    《壞案例歸因分析報告》與《模型迭代建議》
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str = ""
    bad_cases: List[BadCase] = field(default_factory=list)
    bad_case_rate: float = 0.0               # 壞案例佔比 (15-30% expected)
    hallucination_count: int = 0
    intent_understanding_count: int = 0
    user_experience_count: int = 0
    model_iteration_suggestions: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "audit_id": self.audit_id,
            "bad_cases": [bc.to_dict() for bc in self.bad_cases],
            "bad_case_rate": self.bad_case_rate,
            "hallucination_count": self.hallucination_count,
            "intent_understanding_count": self.intent_understanding_count,
            "user_experience_count": self.user_experience_count,
            "model_iteration_suggestions": self.model_iteration_suggestions,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CountPlan:
    """
    Evaluation Count Planning Table — output of the C (Count) stage.
    《評估數量規劃表》
    """

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str = ""
    audit_type: AuditType = AuditType.NEW_PRODUCT
    must_pass_count: int = 0
    high_frequency_count: int = 0
    scenario_counts: Dict[str, int] = field(default_factory=dict)
    total_count: int = 0
    statistical_notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "plan_id": self.plan_id,
            "audit_id": self.audit_id,
            "audit_type": self.audit_type.value,
            "must_pass_count": self.must_pass_count,
            "high_frequency_count": self.high_frequency_count,
            "scenario_counts": self.scenario_counts,
            "total_count": self.total_count,
            "statistical_notes": self.statistical_notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EffectivenessReport:
    """
    Multi-dimensional Evaluation Score Report — output of the E (Effectiveness) stage.
    《多維度評估指標得分表》
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str = ""
    dimension_scores: Dict[str, float] = field(default_factory=dict)  # dimension -> avg score
    overall_score: float = 0.0
    pass_rate: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "audit_id": self.audit_id,
            "dimension_scores": self.dimension_scores,
            "overall_score": self.overall_score,
            "pass_rate": self.pass_rate,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ManualEvaluationRecord:
    """
    Manual Evaluation Record — output of the S (Scrutiny) stage.
    《人工評估記錄》
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    audit_id: str = ""
    case_id: str = ""
    reviewer_id: str = ""
    scores: List[EvaluationScore] = field(default_factory=list)
    overall_verdict: str = ""              # pass / fail / uncertain
    annotation: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "record_id": self.record_id,
            "audit_id": self.audit_id,
            "case_id": self.case_id,
            "reviewer_id": self.reviewer_id,
            "scores": [s.to_dict() for s in self.scores],
            "overall_verdict": self.overall_verdict,
            "annotation": self.annotation,
            "created_at": self.created_at.isoformat(),
        }

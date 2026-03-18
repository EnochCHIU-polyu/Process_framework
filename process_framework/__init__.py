"""
PROCESS AI Review Framework
============================

A seven-stage AI system evaluation and audit framework:

  P - Purpose         (目標與需求評估)
  R - Resources       (資源與評估材料準備)
  O - Optimization    (優化閉環與錯誤歸因)
  C - Count           (評估數量定義)
  E - Effectiveness   (有效性與評估指標)
  S - Standards       (評分標準)
  S - Scrutiny        (審核方法)
"""

from process_framework.framework import ProcessFramework
from process_framework.core import (
    AuditType,
    BadCaseCategory,
    EvaluationDimension,
    ScoreLevel,
    ReviewMethod,
    AuditScope,
    EvaluationCase,
    BadCase,
    EvaluationScore,
    AuditPlan,
    DatasetReport,
    BadCaseAnalysisReport,
    CountPlan,
    EffectivenessReport,
    ManualEvaluationRecord,
)
from process_framework.stages import (
    PurposeStage,
    ResourcesStage,
    OptimizationStage,
    CountStage,
    EffectivenessStage,
    StandardsStage,
    ScrutinyStage,
)
from process_framework.evaluation import MetricsCalculator, ScoringEngine, BadCaseAnalyzer
from process_framework.reporting import ReportGenerator

__all__ = [
    # Main orchestrator
    "ProcessFramework",
    # Core enums
    "AuditType",
    "BadCaseCategory",
    "EvaluationDimension",
    "ScoreLevel",
    "ReviewMethod",
    # Core models
    "AuditScope",
    "EvaluationCase",
    "BadCase",
    "EvaluationScore",
    "AuditPlan",
    "DatasetReport",
    "BadCaseAnalysisReport",
    "CountPlan",
    "EffectivenessReport",
    "ManualEvaluationRecord",
    # Stages
    "PurposeStage",
    "ResourcesStage",
    "OptimizationStage",
    "CountStage",
    "EffectivenessStage",
    "StandardsStage",
    "ScrutinyStage",
    # Evaluation utilities
    "MetricsCalculator",
    "ScoringEngine",
    "BadCaseAnalyzer",
    # Reporting
    "ReportGenerator",
]

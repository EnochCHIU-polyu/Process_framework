"""
Report generation utilities for the PROCESS AI Review Framework.

Produces standardised, human-readable summaries from stage outputs.
Each report includes a summary, data tables, risk level, and
recommended improvement actions.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from process_framework.core.models import (
    AuditPlan,
    BadCaseAnalysisReport,
    CountPlan,
    DatasetReport,
    EffectivenessReport,
    ManualEvaluationRecord,
)

# Risk level thresholds (based on overall pass rate)
RISK_LEVEL_HIGH = 0.70
RISK_LEVEL_MEDIUM = 0.85


def _risk_level(pass_rate: float) -> str:
    """Translate a pass rate into a risk level string."""
    if pass_rate < RISK_LEVEL_HIGH:
        return "HIGH"
    if pass_rate < RISK_LEVEL_MEDIUM:
        return "MEDIUM"
    return "LOW"


class ReportGenerator:
    """
    Generates standardised PROCESS audit reports from stage outputs.

    All report methods return a dict that can be serialised to JSON or
    rendered into a document template.  Each report includes the sections:
      - summary
      - data
      - risk_level
      - improvement_actions
    """

    # ------------------------------------------------------------------
    # P stage
    # ------------------------------------------------------------------

    def audit_plan_report(self, plan: AuditPlan) -> Dict:
        """
        Generate a report for the PROCESS Audit Plan (P + C stages).

        Args:
            plan: The AuditPlan produced by the PurposeStage.

        Returns:
            Standardised report dict.
        """
        scope = plan.scope
        return {
            "title": "PROCESS 審核計畫報告",
            "summary": (
                f"審核類型: {scope.audit_type.value if scope else 'N/A'} | "
                f"總樣本量: {plan.total_sample_size} | "
                f"必須通過集: {plan.must_pass_sample_size} | "
                f"幻覺緩解KPI: {plan.must_pass_threshold:.0%}"
            ),
            "data": plan.to_dict(),
            "risk_level": "N/A",
            "improvement_actions": [
                "確認必須通過集案例已全面覆蓋核心業務場景。",
                "與產品和工程團隊對齊幻覺緩解 KPI 目標。",
            ],
        }

    # ------------------------------------------------------------------
    # R stage
    # ------------------------------------------------------------------

    def dataset_report(self, report: DatasetReport) -> Dict:
        """
        Generate the 《評估數據集報告》 summary.

        Args:
            report: DatasetReport from the ResourcesStage.

        Returns:
            Standardised report dict.
        """
        warnings = []
        if not report.has_standard_answers:
            warnings.append("部分案例缺少標準答案，可能影響評分一致性。")

        for scenario, count in report.cases_by_scenario.items():
            if 0 < count < 100:
                warnings.append(
                    f"場景「{scenario}」只有 {count} 條案例，建議補充至 100–200 條。"
                )

        return {
            "title": "評估數據集報告",
            "summary": (
                f"總案例數: {report.total_cases} | "
                f"場景分佈: {json.dumps(report.cases_by_scenario, ensure_ascii=False)} | "
                f"含標準答案: {'是' if report.has_standard_answers else '否'}"
            ),
            "data": report.to_dict(),
            "risk_level": "HIGH" if warnings else "LOW",
            "improvement_actions": warnings or ["數據集品質達標，可繼續進行評估。"],
        }

    # ------------------------------------------------------------------
    # O stage
    # ------------------------------------------------------------------

    def bad_case_analysis_report(self, report: BadCaseAnalysisReport) -> Dict:
        """
        Generate the 《壞案例歸因分析報告》 summary.

        Args:
            report: BadCaseAnalysisReport from the OptimizationStage.

        Returns:
            Standardised report dict.
        """
        risk = "LOW"
        actions = list(report.model_iteration_suggestions)

        if report.hallucination_count > 0:
            actions.append(
                f"幻覺型壞案例 {report.hallucination_count} 條：建議引入 RAG 或加強事實核查。"
            )
            risk = "MEDIUM"
        if report.intent_understanding_count > 0:
            actions.append(
                f"意圖理解型壞案例 {report.intent_understanding_count} 條："
                "加入對抗性限制詞訓練數據。"
            )
            risk = "MEDIUM"
        if report.user_experience_count > 0:
            actions.append(
                f"用戶體驗型壞案例 {report.user_experience_count} 條："
                "使用 RLHF 優化輸出格式。"
            )

        return {
            "title": "壞案例歸因分析報告",
            "summary": (
                f"壞案例率: {report.bad_case_rate:.1%} | "
                f"幻覺: {report.hallucination_count} | "
                f"意圖理解: {report.intent_understanding_count} | "
                f"用戶體驗: {report.user_experience_count}"
            ),
            "data": report.to_dict(),
            "risk_level": risk,
            "improvement_actions": actions or ["未發現重大壞案例類型。"],
        }

    # ------------------------------------------------------------------
    # C stage
    # ------------------------------------------------------------------

    def count_plan_report(self, plan: CountPlan) -> Dict:
        """
        Generate the 《評估數量規劃表》 summary.

        Args:
            plan: CountPlan from the CountStage.

        Returns:
            Standardised report dict.
        """
        return {
            "title": "評估數量規劃表",
            "summary": (
                f"審核類型: {plan.audit_type.value} | "
                f"總評估量: {plan.total_count} | "
                f"必須通過集: {plan.must_pass_count} | "
                f"高頻問題集: {plan.high_frequency_count}"
            ),
            "data": plan.to_dict(),
            "risk_level": "LOW",
            "improvement_actions": [
                "確保樣本具備統計顯著性，隨機抽樣且涵蓋多樣場景。",
            ],
        }

    # ------------------------------------------------------------------
    # E stage
    # ------------------------------------------------------------------

    def effectiveness_report(self, report: EffectivenessReport) -> Dict:
        """
        Generate the 《多維度評估指標得分表》 summary.

        Args:
            report: EffectivenessReport from the EffectivenessStage.

        Returns:
            Standardised report dict.
        """
        risk = _risk_level(report.pass_rate)
        actions: List[str] = []

        low_dims = [
            dim for dim, avg in report.dimension_scores.items() if avg < 3.0
        ]
        for dim in low_dims:
            actions.append(f"維度「{dim}」平均分低於3分，需重點改善。")

        if not actions:
            actions.append("各維度得分均達基準，繼續監控趨勢。")

        return {
            "title": "多維度評估指標得分表",
            "summary": (
                f"整體平均分: {report.overall_score:.2f} / 5.00 | "
                f"通過率: {report.pass_rate:.1%} | "
                f"風險等級: {risk}"
            ),
            "data": report.to_dict(),
            "risk_level": risk,
            "improvement_actions": actions,
        }

    # ------------------------------------------------------------------
    # S stage (Scrutiny)
    # ------------------------------------------------------------------

    def manual_evaluation_summary(
        self,
        audit_id: str,
        records: List[ManualEvaluationRecord],
    ) -> Dict:
        """
        Generate a summary of 《人工評估記錄》.

        Args:
            audit_id: The parent audit ID.
            records: List of ManualEvaluationRecord from the ScrutinyStage.

        Returns:
            Standardised report dict.
        """
        total = len(records)
        passed = sum(1 for r in records if r.overall_verdict == "pass")
        failed = sum(1 for r in records if r.overall_verdict == "fail")
        uncertain = total - passed - failed
        pass_rate = passed / total if total > 0 else 0.0
        risk = _risk_level(pass_rate)

        actions: List[str] = []
        if failed > 0:
            actions.append(f"{failed} 條案例未通過，需進行壞案例歸因分析後改善。")
        if uncertain > 0:
            actions.append(f"{uncertain} 條案例評分不確定，建議增加評審輪次。")
        if not actions:
            actions.append("所有案例均通過人工審核。")

        return {
            "title": "人工評估記錄摘要",
            "summary": (
                f"審核ID: {audit_id} | 總計: {total} | "
                f"通過: {passed} | 失敗: {failed} | "
                f"不確定: {uncertain} | 通過率: {pass_rate:.1%}"
            ),
            "data": {
                "audit_id": audit_id,
                "total": total,
                "passed": passed,
                "failed": failed,
                "uncertain": uncertain,
                "pass_rate": pass_rate,
                "records": [r.to_dict() for r in records],
            },
            "risk_level": risk,
            "improvement_actions": actions,
        }

    # ------------------------------------------------------------------
    # Full framework report
    # ------------------------------------------------------------------

    def full_process_report(
        self,
        audit_plan: Optional[AuditPlan] = None,
        dataset_report: Optional[DatasetReport] = None,
        bad_case_report: Optional[BadCaseAnalysisReport] = None,
        count_plan: Optional[CountPlan] = None,
        effectiveness_report: Optional[EffectivenessReport] = None,
        evaluation_records: Optional[List[ManualEvaluationRecord]] = None,
        audit_id: str = "",
    ) -> Dict:
        """
        Aggregate all stage reports into a single PROCESS framework report.

        Args:
            audit_plan: Output of PurposeStage.
            dataset_report: Output of ResourcesStage.
            bad_case_report: Output of OptimizationStage.
            count_plan: Output of CountStage.
            effectiveness_report: Output of EffectivenessStage.
            evaluation_records: Output of ScrutinyStage.
            audit_id: Audit ID for the manual evaluation summary.

        Returns:
            Complete PROCESS audit report dict.
        """
        sections: Dict[str, Optional[Dict]] = {
            "P_Purpose": self.audit_plan_report(audit_plan) if audit_plan else None,
            "R_Resources": self.dataset_report(dataset_report) if dataset_report else None,
            "O_Optimization": (
                self.bad_case_analysis_report(bad_case_report) if bad_case_report else None
            ),
            "C_Count": self.count_plan_report(count_plan) if count_plan else None,
            "E_Effectiveness": (
                self.effectiveness_report(effectiveness_report)
                if effectiveness_report
                else None
            ),
            "S_Scrutiny": (
                self.manual_evaluation_summary(audit_id, evaluation_records)
                if evaluation_records is not None
                else None
            ),
        }

        # Determine overall risk from non-null sections
        risk_priority = {"HIGH": 2, "MEDIUM": 1, "LOW": 0, "N/A": -1}
        overall_risk = "LOW"
        for section in sections.values():
            if section and "risk_level" in section:
                if risk_priority.get(section["risk_level"], -1) > risk_priority.get(overall_risk, 0):
                    overall_risk = section["risk_level"]

        return {
            "title": "PROCESS AI 審核完整報告",
            "audit_id": audit_id,
            "overall_risk_level": overall_risk,
            "sections": sections,
        }

"""
S - Scrutiny Stage (審核方法)

Orchestrates the three-tier review pipeline:
  1. Automated filtering (自動化初步篩選)
  2. LLM-as-a-Judge intermediate scoring (LLM 中間篩選)
  3. Human fine-grained review (人工精細篩選)

Produces the 《人工評估記錄》 and 《自動化評估輔助報告》.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from process_framework.core.enums import EvaluationDimension, ReviewMethod, ScoreLevel
from process_framework.core.models import (
    EvaluationCase,
    EvaluationScore,
    ManualEvaluationRecord,
)

AutomatedFilterFn = Callable[[EvaluationCase], Optional[bool]]
"""
A callable that takes an EvaluationCase and returns:
  - True  → clearly good (skip to pass)
  - False → clearly bad (escalate immediately)
  - None  → uncertain (needs further review)
"""

LLMJudgeFn = Callable[[EvaluationCase], Dict[str, int]]
"""
A callable that takes an EvaluationCase and returns a dict mapping
EvaluationDimension value strings to integer scores (1–5).
"""


class ScrutinyStage:
    """
    S - Scrutiny: Implements the three-tier review pipeline and maintains
    manual evaluation records for all reviewed cases.
    """

    def __init__(
        self,
        automated_filter: Optional[AutomatedFilterFn] = None,
        llm_judge: Optional[LLMJudgeFn] = None,
    ) -> None:
        """
        Args:
            automated_filter: Optional function for automated preliminary filtering.
            llm_judge: Optional function that acts as LLM-as-a-Judge.
        """
        self._automated_filter = automated_filter
        self._llm_judge = llm_judge
        self._records: List[ManualEvaluationRecord] = []

    # ------------------------------------------------------------------
    # Three-tier review pipeline
    # ------------------------------------------------------------------

    def review_case(
        self,
        audit_id: str,
        case: EvaluationCase,
        reviewer_id: str,
        human_scores: Optional[Dict[EvaluationDimension, ScoreLevel]] = None,
        annotation: str = "",
        force_human_review: bool = False,
    ) -> ManualEvaluationRecord:
        """
        Process a single case through the three-tier review pipeline and
        record the outcome.

        Pipeline:
          1. **Automated filter** (if configured): quickly classify clear
             pass/fail cases.
          2. **LLM-as-a-Judge** (if configured): score uncertain cases.
          3. **Human review**: evaluates must-pass cases and any case that
             the automated/LLM tiers left uncertain.

        Args:
            audit_id: Parent audit ID.
            case: The EvaluationCase to review.
            reviewer_id: ID of the human reviewer.
            human_scores: Human-assigned dimension scores; required when the
                          case reaches the human review tier.
            annotation: Reviewer's free-text notes.
            force_human_review: If True, skip tiers 1–2 and go directly to
                                human review (used for must-pass set cases).

        Returns:
            ManualEvaluationRecord capturing the complete review result.
        """
        verdict = "uncertain"
        scores: List[EvaluationScore] = []

        if not force_human_review:
            # Tier 1: automated filter
            if self._automated_filter is not None:
                filter_result = self._automated_filter(case)
                if filter_result is True:
                    verdict = "pass"
                elif filter_result is False:
                    verdict = "fail"
                # None → proceed to next tier

            # Tier 2: LLM-as-a-Judge (only when still uncertain)
            if verdict == "uncertain" and self._llm_judge is not None:
                llm_scores_raw = self._llm_judge(case)
                for dim_value, score_int in llm_scores_raw.items():
                    try:
                        dimension = EvaluationDimension(dim_value)
                        score_level = ScoreLevel(score_int)
                        scores.append(
                            EvaluationScore(
                                case_id=case.case_id,
                                dimension=dimension,
                                score=score_level,
                                reviewer_id="llm_judge",
                            )
                        )
                    except ValueError:
                        pass  # skip unrecognised dimensions/scores

        # Tier 3: human review (for uncertain cases, must-pass set, or forced)
        if verdict == "uncertain" or force_human_review:
            if human_scores:
                for dimension, score_level in human_scores.items():
                    scores.append(
                        EvaluationScore(
                            case_id=case.case_id,
                            dimension=dimension,
                            score=score_level,
                            reviewer_id=reviewer_id,
                        )
                    )
                # Derive verdict from human scores
                if scores:
                    human_only = [
                        s for s in scores if s.reviewer_id == reviewer_id
                    ]
                    avg = sum(s.score.value for s in human_only) / len(human_only)
                    verdict = "pass" if avg >= ScoreLevel.SCORE_3.value else "fail"

        record = ManualEvaluationRecord(
            audit_id=audit_id,
            case_id=case.case_id,
            reviewer_id=reviewer_id,
            scores=scores,
            overall_verdict=verdict,
            annotation=annotation,
        )
        self._records.append(record)
        return record

    # ------------------------------------------------------------------
    # Batch review
    # ------------------------------------------------------------------

    def review_must_pass_set(
        self,
        audit_id: str,
        cases: List[EvaluationCase],
        reviewer_id: str,
        scores_per_case: Optional[Dict[str, Dict[EvaluationDimension, ScoreLevel]]] = None,
        annotations: Optional[Dict[str, str]] = None,
    ) -> List[ManualEvaluationRecord]:
        """
        Review a batch of must-pass set cases, always forcing human review.

        Args:
            audit_id: Parent audit ID.
            cases: List of must-pass EvaluationCase objects.
            reviewer_id: ID of the human reviewer.
            scores_per_case: Mapping of case_id → dimension scores.
            annotations: Mapping of case_id → annotation.

        Returns:
            List of ManualEvaluationRecord, one per case.
        """
        records: List[ManualEvaluationRecord] = []
        for case in cases:
            human_scores = (scores_per_case or {}).get(case.case_id)
            annotation = (annotations or {}).get(case.case_id, "")
            record = self.review_case(
                audit_id=audit_id,
                case=case,
                reviewer_id=reviewer_id,
                human_scores=human_scores,
                annotation=annotation,
                force_human_review=True,
            )
            records.append(record)
        return records

    # ------------------------------------------------------------------
    # Record access and statistics
    # ------------------------------------------------------------------

    def get_records(self) -> List[ManualEvaluationRecord]:
        """Return all manual evaluation records."""
        return list(self._records)

    def get_review_summary(self) -> Dict[str, object]:
        """
        Return a summary of review outcomes across all records.

        Returns:
            Dict with keys: total, passed, failed, uncertain, pass_rate,
            methods_used.
        """
        total = len(self._records)
        passed = sum(1 for r in self._records if r.overall_verdict == "pass")
        failed = sum(1 for r in self._records if r.overall_verdict == "fail")
        uncertain = total - passed - failed

        methods_used: List[str] = [ReviewMethod.HUMAN_REVIEW.value]
        if self._automated_filter is not None:
            methods_used.insert(0, ReviewMethod.AUTOMATED_FILTERING.value)
        if self._llm_judge is not None:
            methods_used.insert(
                1 if self._automated_filter else 0,
                ReviewMethod.LLM_AS_JUDGE.value,
            )

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "uncertain": uncertain,
            "pass_rate": passed / total if total > 0 else 0.0,
            "methods_used": methods_used,
        }

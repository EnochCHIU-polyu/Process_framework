"""
Bad case analysis utilities for the PROCESS framework.

Provides a BadCaseAnalyzer that derives actionable improvement suggestions
from a collection of bad cases across root-cause categories.
"""

from __future__ import annotations

from typing import Dict, List

from process_framework.core.enums import BadCaseCategory
from process_framework.core.models import BadCase

# Generic improvement templates keyed by category
IMPROVEMENT_TEMPLATES: Dict[BadCaseCategory, str] = {
    BadCaseCategory.HALLUCINATION: (
        "強化事實驗證機制：加入 retrieval-augmented generation (RAG) 或增加訓練數據中"
        "的事實核查樣本，以降低幻覺率。"
    ),
    BadCaseCategory.INTENT_UNDERSTANDING: (
        "改善意圖識別模組：收集被忽略的限制詞案例，加入對抗性訓練數據，確保模型"
        "識別並遵守「夏季」、「顯瘦」等場景限制詞。"
    ),
    BadCaseCategory.USER_EXPERIENCE: (
        "優化回覆格式與長度：使用 RLHF 或偏好數據微調，鼓勵模型輸出更簡潔、"
        "結構清晰的回覆。"
    ),
    # LENS-aligned subcategories (LENS Framework — DiaHalu, EMNLP 2024)
    BadCaseCategory.FACTUAL: (
        "修正事實幻覺（LENS Layer 1）：引入實體一致性檢查和 RAG 機制，確保實體名稱、"
        "日期和數字等事實資訊準確無誤。"
    ),
    BadCaseCategory.LOGICAL: (
        "修正邏輯推理錯誤（LENS Layer 2）：增加邏輯一致性訓練數據和推理鏈驗證，"
        "確保模型推理步驟前後連貫。"
    ),
    BadCaseCategory.REFERENTIAL: (
        "修正引用歸因錯誤（LENS Layer 3）：加強來源引用核查，避免錯誤歸屬聲明，"
        "並在輸出中明確標示不確定的引用。"
    ),
}


class BadCaseAnalyzer:
    """
    Analyses a collection of bad cases to produce structured root-cause
    summaries and prioritised improvement suggestions.
    """

    def summarize(self, bad_cases: List[BadCase]) -> Dict[str, object]:
        """
        Produce a category-level summary of bad cases.

        Args:
            bad_cases: List of BadCase objects to analyse.

        Returns:
            Dict with keys:
              - total: int
              - by_category: {category_value: count}
              - top_ignored_keywords: list of (keyword, count) sorted by frequency
              - suggestions: {category_value: improvement_template}
        """
        by_category: Dict[str, int] = {cat.value: 0 for cat in BadCaseCategory}
        keyword_frequency: Dict[str, int] = {}

        for bc in bad_cases:
            by_category[bc.category.value] += 1
            for kw in bc.ignored_keywords:
                keyword_frequency[kw] = keyword_frequency.get(kw, 0) + 1

        top_keywords = sorted(
            keyword_frequency.items(), key=lambda x: x[1], reverse=True
        )

        return {
            "total": len(bad_cases),
            "by_category": by_category,
            "top_ignored_keywords": top_keywords,
            "suggestions": {
                cat.value: IMPROVEMENT_TEMPLATES[cat] for cat in BadCaseCategory
            },
        }

    def get_suggestions_for_category(self, category: BadCaseCategory) -> str:
        """
        Return the improvement suggestion template for a specific category.

        Args:
            category: The bad case root-cause category.

        Returns:
            Improvement suggestion string.
        """
        return IMPROVEMENT_TEMPLATES[category]

    def filter_by_keyword(
        self, bad_cases: List[BadCase], keyword: str
    ) -> List[BadCase]:
        """
        Filter bad cases that ignored a specific keyword.

        Args:
            bad_cases: List of BadCase objects.
            keyword: The keyword to filter by.

        Returns:
            Subset of bad_cases where keyword appears in ignored_keywords.
        """
        return [bc for bc in bad_cases if keyword in bc.ignored_keywords]

    def prioritise_categories(
        self, bad_cases: List[BadCase]
    ) -> List[str]:
        """
        Return bad-case categories sorted by descending frequency.

        Args:
            bad_cases: List of BadCase objects.

        Returns:
            List of category value strings, most frequent first.
        """
        by_category: Dict[str, int] = {cat.value: 0 for cat in BadCaseCategory}
        for bc in bad_cases:
            by_category[bc.category.value] += 1
        return sorted(by_category, key=lambda c: by_category[c], reverse=True)

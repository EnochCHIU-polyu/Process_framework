"""
C - Count Stage (評估數量定義)

Defines statistically significant sample sizes for each audit type and
scenario category, producing the 《評估數量規劃表》.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

from process_framework.core.enums import AuditType, ScenarioType
from process_framework.core.models import CountPlan

# Default cases per scenario (can be overridden)
DEFAULT_CASES_PER_SCENARIO: int = 150   # midpoint of the 100–200 recommendation

# Minimum sample counts
MIN_MUST_PASS_COUNT: int = 50
MIN_HIGH_FREQUENCY_COUNT: int = 30


class CountStage:
    """
    C - Count: Determines the evaluation sample sizes required to achieve
    statistical significance, distinguishing between new-product launches
    and optimization reviews.
    """

    def plan_count(
        self,
        audit_id: str,
        audit_type: AuditType,
        must_pass_count: Optional[int] = None,
        high_frequency_count: Optional[int] = None,
        cases_per_scenario: Optional[int] = None,
        statistical_notes: str = "",
    ) -> CountPlan:
        """
        Generate a 《評估數量規劃表》 for the given audit.

        Rules applied:
        - New product launches require a higher must-pass count
          (at least ``MIN_MUST_PASS_COUNT``).
        - Every scenario type receives at least ``cases_per_scenario``
          evaluation cases (default: 150).

        Args:
            audit_id: ID of the parent audit.
            audit_type: New product launch or optimization.
            must_pass_count: Override the must-pass set size.
            high_frequency_count: Override the high-frequency set size.
            cases_per_scenario: Override the per-scenario case count.
            statistical_notes: Free-text notes on sampling methodology.

        Returns:
            CountPlan with all counts populated.

        Raises:
            ValueError: If any provided count is below the required minimum.
        """
        effective_per_scenario = cases_per_scenario or DEFAULT_CASES_PER_SCENARIO

        # Build per-scenario counts
        scenario_counts: Dict[str, int] = {
            st.value: effective_per_scenario for st in ScenarioType
        }

        # Determine must-pass and high-frequency counts
        effective_must_pass = must_pass_count if must_pass_count is not None else (
            MIN_MUST_PASS_COUNT if audit_type == AuditType.NEW_PRODUCT
            else math.ceil(MIN_MUST_PASS_COUNT * 0.5)
        )
        effective_high_frequency = high_frequency_count if high_frequency_count is not None else (
            MIN_HIGH_FREQUENCY_COUNT
        )

        if effective_must_pass < 0:
            raise ValueError("must_pass_count cannot be negative.")
        if effective_high_frequency < 0:
            raise ValueError("high_frequency_count cannot be negative.")

        total = sum(scenario_counts.values()) + effective_must_pass + effective_high_frequency

        return CountPlan(
            audit_id=audit_id,
            audit_type=audit_type,
            must_pass_count=effective_must_pass,
            high_frequency_count=effective_high_frequency,
            scenario_counts=scenario_counts,
            total_count=total,
            statistical_notes=statistical_notes,
        )

    def minimum_must_pass_count(self, audit_type: AuditType) -> int:
        """
        Return the minimum must-pass count required for the given audit type.

        New product launches require at least MIN_MUST_PASS_COUNT cases;
        optimization audits may use half that.
        """
        if audit_type == AuditType.NEW_PRODUCT:
            return MIN_MUST_PASS_COUNT
        return math.ceil(MIN_MUST_PASS_COUNT * 0.5)

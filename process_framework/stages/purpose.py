"""
P - Purpose Stage (目標與需求評估)

Defines the audit scope and objectives, producing the
《審核範圍與目標文件》.
"""

from __future__ import annotations

from typing import List, Optional

from process_framework.core.enums import AuditType
from process_framework.core.models import AuditPlan, AuditScope


class PurposeStage:
    """
    P - Purpose: Clarifies whether the audit targets a new product launch
    or system optimization, and defines the must-pass set, high-frequency
    issue set, and hallucination-mitigation KPI.
    """

    # Minimum acceptable hallucination-mitigation KPI for new product launches
    MIN_HALLUCINATION_KPI_NEW_PRODUCT: float = 0.99

    def define_scope(
        self,
        audit_type: AuditType,
        description: str,
        must_pass_set: Optional[List[str]] = None,
        high_frequency_issues: Optional[List[str]] = None,
        hallucination_mitigation_kpi: float = 0.99,
    ) -> AuditScope:
        """
        Define the audit scope and return an AuditScope document.

        Args:
            audit_type: Whether this is a new product launch or optimization.
            description: Free-text description of the audit goals.
            must_pass_set: Critical scenarios that must achieve ≥99% accuracy.
            high_frequency_issues: Topics that must be fully covered.
            hallucination_mitigation_kpi: Target accuracy for hallucination reduction.

        Returns:
            AuditScope: The completed scope document.

        Raises:
            ValueError: If the hallucination KPI is below the minimum for
                        new product launches.
        """
        if (
            audit_type == AuditType.NEW_PRODUCT
            and hallucination_mitigation_kpi < self.MIN_HALLUCINATION_KPI_NEW_PRODUCT
        ):
            raise ValueError(
                f"New product launches require a hallucination mitigation KPI of at least "
                f"{self.MIN_HALLUCINATION_KPI_NEW_PRODUCT:.0%}. "
                f"Provided: {hallucination_mitigation_kpi:.0%}."
            )

        scope = AuditScope(
            audit_type=audit_type,
            description=description,
            must_pass_set=must_pass_set or [],
            high_frequency_issues=high_frequency_issues or [],
            hallucination_mitigation_kpi=hallucination_mitigation_kpi,
        )
        return scope

    def create_audit_plan(
        self,
        scope: AuditScope,
        total_sample_size: int,
        must_pass_sample_size: int,
        high_frequency_sample_size: int,
    ) -> AuditPlan:
        """
        Create an AuditPlan based on the defined scope and sampling parameters.

        Args:
            scope: The AuditScope produced by define_scope().
            total_sample_size: Total number of evaluation cases planned.
            must_pass_sample_size: Number of must-pass cases.
            high_frequency_sample_size: Number of high-frequency issue cases.

        Returns:
            AuditPlan: The master audit plan document.

        Raises:
            ValueError: If sample sizes are non-positive or inconsistent.
        """
        if total_sample_size <= 0:
            raise ValueError("total_sample_size must be a positive integer.")
        if must_pass_sample_size < 0 or high_frequency_sample_size < 0:
            raise ValueError("Sample sizes cannot be negative.")
        if must_pass_sample_size + high_frequency_sample_size > total_sample_size:
            raise ValueError(
                "must_pass_sample_size + high_frequency_sample_size cannot exceed total_sample_size."
            )

        return AuditPlan(
            scope=scope,
            total_sample_size=total_sample_size,
            must_pass_sample_size=must_pass_sample_size,
            high_frequency_sample_size=high_frequency_sample_size,
            must_pass_threshold=scope.hallucination_mitigation_kpi,
        )

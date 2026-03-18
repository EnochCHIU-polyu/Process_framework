"""
R - Resources Stage (資源與評估材料準備)

Manages collection and validation of historical logs and the construction
of the scenario-based evaluation dataset, producing the
《評估數據集報告》.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from process_framework.core.enums import ScenarioType
from process_framework.core.models import DatasetReport, EvaluationCase


# Recommended per-scenario case counts (100–200 cases each)
RECOMMENDED_MIN_CASES_PER_SCENARIO = 100
RECOMMENDED_MAX_CASES_PER_SCENARIO = 200


class ResourcesStage:
    """
    R - Resources: Collects historical conversation logs, builds
    scenario-based evaluation datasets, and validates data quality.
    """

    def __init__(self) -> None:
        self._cases: List[EvaluationCase] = []

    # ------------------------------------------------------------------
    # Case management
    # ------------------------------------------------------------------

    def add_case(self, case: EvaluationCase) -> None:
        """Add a single evaluation case to the working dataset."""
        if not case.user_input:
            raise ValueError("EvaluationCase must have a non-empty user_input.")
        if not case.expected_output:
            raise ValueError("EvaluationCase must have a non-empty expected_output.")
        self._cases.append(case)

    def add_cases(self, cases: List[EvaluationCase]) -> None:
        """Add multiple evaluation cases at once."""
        for case in cases:
            self.add_case(case)

    def get_cases(self) -> List[EvaluationCase]:
        """Return all added evaluation cases."""
        return list(self._cases)

    def get_cases_by_scenario(self, scenario_type: ScenarioType) -> List[EvaluationCase]:
        """Return cases filtered by scenario type."""
        return [c for c in self._cases if c.scenario_type == scenario_type]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def validate_dataset(self) -> Dict[str, object]:
        """
        Validate whether the current dataset meets recommendations.

        Returns a dict with:
          - ``is_valid``: bool
          - ``scenario_counts``: counts per scenario
          - ``warnings``: list of warning strings
        """
        warnings: List[str] = []
        scenario_counts: Dict[str, int] = {}

        for scenario_type in ScenarioType:
            count = len(self.get_cases_by_scenario(scenario_type))
            scenario_counts[scenario_type.value] = count

            if 0 < count < RECOMMENDED_MIN_CASES_PER_SCENARIO:
                warnings.append(
                    f"Scenario '{scenario_type.value}' has only {count} cases "
                    f"(recommended: {RECOMMENDED_MIN_CASES_PER_SCENARIO}–"
                    f"{RECOMMENDED_MAX_CASES_PER_SCENARIO})."
                )

        cases_without_answers = [c for c in self._cases if not c.expected_output]
        if cases_without_answers:
            warnings.append(
                f"{len(cases_without_answers)} case(s) are missing expected_output."
            )

        return {
            "is_valid": len(warnings) == 0,
            "scenario_counts": scenario_counts,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(
        self,
        audit_id: str,
        representativeness_notes: Optional[str] = None,
    ) -> DatasetReport:
        """
        Generate the 《評估數據集報告》 for the current dataset.

        Args:
            audit_id: ID of the parent audit.
            representativeness_notes: Free-text notes on data representativeness.

        Returns:
            DatasetReport with counts and quality metadata.
        """
        validation = self.validate_dataset()
        cases_by_scenario: Dict[str, int] = validation["scenario_counts"]  # type: ignore[assignment]
        has_standard_answers = all(c.expected_output for c in self._cases)

        return DatasetReport(
            audit_id=audit_id,
            cases_by_scenario=cases_by_scenario,
            total_cases=len(self._cases),
            has_standard_answers=has_standard_answers,
            representativeness_notes=representativeness_notes or "",
        )

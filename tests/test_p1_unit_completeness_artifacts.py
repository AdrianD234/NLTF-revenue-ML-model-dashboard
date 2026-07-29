"""The committed P1.1 evidence stays complete, closed and honest.

These gates run against the committed artifacts so a regeneration that starts
hiding a residual, loses unit coverage, or lets the known macro drift grow
fails in CI rather than in review.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "p1_unit_completeness"
TOL = 1e-6
FYS = {2026, 2027, 2028, 2029, 2030}
MACRO_DRIFT_STATUS = "known_macro_cross_row_inconsistency_pending_p1_2"
# Measured 1.706% at FY2030. Pinned just above so numerical noise does not
# false-alarm, far below anything that would let the drift double.
MACRO_DRIFT_CEILING_PCT = 1.8


def test_every_expected_artifact_is_committed() -> None:
    expected = {
        "unit_registry.csv",
        "unit_alias_audit.csv",
        "unit_conversion_audit.csv",
        "implicit_unit_logic_scan.csv",
        "completeness_matrix.csv",
        "missing_data_fail_closed_audit.csv",
        "ped_cross_row_identity.csv",
        "fy2026_population_lineage.csv",
        "allocation_residual_audit.csv",
        "formula_residual_audit.csv",
        "production_value_stability.csv",
        "p1_1_report.md",
    }
    assert expected <= {path.name for path in OUT.iterdir()}


def test_implicit_unit_scan_reports_zero_defects() -> None:
    scan = pd.read_csv(OUT / "implicit_unit_logic_scan.csv")
    defects = scan[scan["classification"].eq("defect_requiring_correction")]
    assert defects.empty, defects.to_dict("records")
    assert set(scan["classification"]) <= {
        "governed_unit_conversion",
        "legitimate_economic_formula",
        "display_formatting_only",
        "test_only",
        "defect_requiring_correction",
    }


def test_completeness_matrix_has_no_fail_closed_findings() -> None:
    matrix = pd.read_csv(OUT / "completeness_matrix.csv")
    failures = matrix[
        matrix["status"].isin(
            [
                "missing_source_input",
                "missing_derived_output",
                "duplicate_or_ambiguous",
                "non_numeric",
                "non_finite",
                "unit_invalid",
                "formula_invalid",
            ]
        )
    ]
    assert failures.empty, failures.head(10).to_dict("records")
    assert set(matrix["fy"].astype(int)) == FYS if "fy" in matrix.columns else True
    available = matrix[matrix["status"].eq("required_and_available")]
    assert len(available) / len(matrix) > 0.95


def test_ped_identity_closes_before_macro_and_drift_is_enumerated() -> None:
    identity = pd.read_csv(OUT / "ped_cross_row_identity.csv")
    evaluable = identity[identity["contract_status"].ne("not_evaluable_missing_governed_population")]
    assert len(evaluable) > 0

    pre_macro = evaluable[evaluable["stage"].eq("S0")]
    assert len(pre_macro) == len(FYS)
    assert pre_macro["residual_pct"].abs().max() <= 1e-3, "pre-macro identity must close"
    assert pre_macro["contract_status"].eq("identity_closes").all()

    drifted = evaluable[evaluable["contract_status"].eq(MACRO_DRIFT_STATUS)]
    assert len(drifted) > 0, "the known macro drift must stay enumerated, not silently fixed"
    assert drifted["residual_pct"].abs().max() <= MACRO_DRIFT_CEILING_PCT
    # It must never migrate earlier than the macro stage.
    assert not drifted["stage"].eq("S0").any()
    assert set(drifted["stage"]) <= {"S1", "S2", "S3", "S4"}
    assert drifted["first_divergent_stage"].eq("S1").all()


def test_no_population_is_inferred_to_force_the_identity_to_close() -> None:
    identity = pd.read_csv(OUT / "ped_cross_row_identity.csv")
    assert "direct_population_mean" in identity.columns
    # An output-implied population would make every stage close by
    # construction; the drift proves the direct input is being used.
    drifted = identity[identity["contract_status"].eq(MACRO_DRIFT_STATUS)]
    assert drifted["residual_pct"].abs().min() > 0.0


def test_fy2026_population_lineage_is_complete_and_mixed() -> None:
    lineage = pd.read_csv(OUT / "fy2026_population_lineage.csv")
    assert set(lineage["quarter"]) == {"2025Q3", "2025Q4", "2026Q1", "2026Q2"}
    assert lineage["status"].eq("available").all(), (
        "FY2026 must not be declared unavailable merely because one source "
        "table does not span all four quarters"
    )
    assert set(lineage["lineage"]) == {"historical_actual", "scenario_forecast"}
    assert lineage["source_path"].str.len().gt(0).all()
    assert lineage["unit"].eq("persons").all()


def test_allocation_residuals_do_not_hide_in_conventional_activity() -> None:
    allocation = pd.read_csv(OUT / "allocation_residual_audit.csv")
    assert len(allocation) == 2 * len(FYS)
    for column in ("anchor_preserved_residual", "share_sum_residual", "pool_identity_residual", "class_sum_residual"):
        assert allocation[column].abs().max() <= TOL, column
    assert allocation["residual_assigned_to_conventional"].abs().max() == 0.0


def test_current_formulas_close_and_official_source_residuals_stay_visible() -> None:
    formula = pd.read_csv(OUT / "formula_residual_audit.csv")
    current = formula[formula["role"].isin(["basecase", "comparison"])]
    assert not current.empty
    assert current["residual"].abs().max() <= TOL
    assert current["status"].eq("closes").all()
    assert not formula["allocated_to_current_class"].any()
    official = formula[formula["role"].eq("official_comparator")]
    reported = official[official["status"].eq("published_source_residual_reported")]
    if len(reported):
        assert reported["residual"].abs().max() > TOL


def test_production_values_are_stable() -> None:
    stability = pd.read_csv(OUT / "production_value_stability.csv")
    assert stability["max_abs_delta"].max() == 0.0, (
        "P1.1 is value-neutral; a changed production value must be explained, not repinned"
    )
    assert stability["rows_before"].equals(stability["rows_after"])

"""Design invariants for the candidate Light RUC anchor architecture.

These pin the Checkpoint 3.1 design decisions so a later implementation cannot
drift from them silently:

  * the raw Light RUC model forecast is preserved exactly as the conventional
    class under every seam method;
  * the class share vector always closes to one;
  * uptake presets reallocate the Base pool, never resize it;
  * no lambda-derived level enters any candidate path;
  * unrestricted share expansion is NOT safe beyond FY2030, so the H21+ policy
    is asserted rather than assumed;
  * the PED COVID sensitivity uses the specification window 2020Q1-2021Q4.

See artifacts/fleet_allocation_semantics/checkpoint_3_final_design_verdict.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "fleet_allocation_semantics"
PACK = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
TOL = 1e-6
ANCHOR_FY = 2025
DECISION_GRADE_MAX_FY = 2030


def _artifact(name: str) -> pd.DataFrame:
    path = ARTIFACTS / name
    if not path.exists():
        pytest.skip(f"{name} has not been generated")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def seam_paths() -> pd.DataFrame:
    return _artifact("light_ruc_seam_method_paths.csv")


@pytest.fixture(scope="module")
def guard() -> pd.DataFrame:
    return _artifact("light_ruc_long_horizon_guard.csv")


def test_raw_conventional_is_preserved_under_every_seam_method(seam_paths) -> None:
    split = pd.read_csv(PACK / "ev_phev_split_assumptions.csv")
    split = split[split["scenario_name"].eq("current_basecase")].set_index("FY")
    raw = split["current_light_total_modelled_km"].astype(float)
    forecast = seam_paths[seam_paths["june_year"].gt(ANCHOR_FY)]
    assert not forecast.empty
    for method, rows in forecast.groupby("method"):
        for record in rows.itertuples():
            assert float(record.conventional) == pytest.approx(
                float(raw.loc[int(record.june_year)]), abs=TOL
            ), f"{method} altered the conventional anchor at FY{record.june_year}"


# The artifacts are written rounded to 6 decimal places, so a three-term sum
# can differ from its exact value by up to 1.5e-6. The exact closures are
# asserted at 1e-6 inside the generating script's own gates; these read-back
# checks use the rounding-aware bound.
CSV_ROUNDING_TOL = 5e-6


def test_share_vector_closes_to_one(seam_paths) -> None:
    total = seam_paths["conventional_share"] + seam_paths["bev_share"] + seam_paths["phev_share"]
    assert float((total - 1.0).abs().max()) <= CSV_ROUNDING_TOL


def test_pool_equals_the_class_sum(seam_paths) -> None:
    residual = seam_paths["pool"] - (
        seam_paths["conventional"] + seam_paths["bev"] + seam_paths["phev"]
    )
    assert float(residual.abs().max()) <= CSV_ROUNDING_TOL


def test_fy2025_classes_are_the_actuals_in_every_method(seam_paths) -> None:
    split = pd.read_csv(PACK / "ev_phev_split_assumptions.csv")
    split = split[split["scenario_name"].eq("current_basecase")].set_index("FY")
    anchor = seam_paths[seam_paths["june_year"].eq(ANCHOR_FY)]
    assert not anchor.empty
    for record in anchor.itertuples():
        assert float(record.conventional) == pytest.approx(
            float(split.loc[ANCHOR_FY, "current_conventional_light_km"]), abs=TOL
        )
        assert float(record.bev) == pytest.approx(
            float(split.loc[ANCHOR_FY, "current_light_bev_km"]), abs=TOL
        )
        assert float(record.phev) == pytest.approx(
            float(split.loc[ANCHOR_FY, "current_phev_km"]), abs=TOL
        )


def test_no_lambda_level_enters_any_candidate_path(seam_paths) -> None:
    """No candidate conventional level may equal raw - lambda * migration."""
    split = pd.read_csv(PACK / "ev_phev_split_assumptions.csv")
    split = split[split["scenario_name"].eq("current_basecase")].set_index("FY")
    raw = split["current_light_total_modelled_km"].astype(float)
    drift = pd.read_csv(PACK / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq("current_basecase")
        & drift["lambda_mode"].astype(str).eq("optimized")
    ].set_index("FY")

    forecast = seam_paths[seam_paths["june_year"].gt(ANCHOR_FY)]
    for record in forecast.itertuples():
        fy = int(record.june_year)
        if fy not in drift.index:
            continue
        migration = float(drift.loc[fy, "current_BEV_km"]) + float(drift.loc[fy, "current_PHEV_km"])
        lambda_level = float(raw.loc[fy]) - float(drift.loc[fy, "lambda_value"]) * migration
        assert abs(float(record.conventional) - lambda_level) > TOL, (
            f"{record.method} reproduced the lambda-reduced level at FY{fy}"
        )


def test_unrestricted_share_expansion_is_not_safe_beyond_fy2030(guard) -> None:
    """The H21+ boundary is asserted, not assumed.

    Dividing a growing conventional anchor by a falling conventional share
    compounds. This test pins that the share-anchor methods fail the long
    horizon guard while remaining acceptable through the decision-grade window,
    which is the evidence behind the FY2030 publication boundary.
    """
    share_methods = ["A_immediate", "B_two_year", "C_three_year"]
    present = [m for m in share_methods if m in set(guard["method"])]
    assert present, "no share-anchor method present in the guard"

    for method in present:
        rows = guard[guard["method"].eq(method)].set_index("june_year")
        # The far horizon must fail, otherwise the FY2030 boundary is unjustified.
        far = rows.loc[[fy for fy in rows.index if fy >= 2040]]
        assert (far["worst_flag"] == "FAIL").any(), (
            f"{method} no longer fails at H21+, so the FY2030 boundary needs re-deriving"
        )
        assert float(rows.loc[2050, "pool_vs_vfm_base_ratio"]) > 2.0


def test_the_recommended_seam_method_is_clean_inside_the_decision_window(guard) -> None:
    rows = guard[guard["method"].eq("A_immediate")].set_index("june_year")
    window = rows.loc[[fy for fy in rows.index if ANCHOR_FY < fy <= DECISION_GRADE_MAX_FY]]
    assert not (window["worst_flag"] == "FAIL").any()


def test_longer_share_transitions_defer_and_concentrate_the_adjustment(guard) -> None:
    """Why B and C are rejected: the catch-up lands inside the decision window.

    A multi-year share blend does not smooth the adjustment; it postpones it
    and then delivers it in one step when the blend weight reaches 1. For the
    three-year transition that step falls at FY2028, inside the backtest
    supported zone, and trips the pool-growth threshold.
    """
    rows = guard[guard["method"].eq("C_three_year")].set_index("june_year")
    window = rows.loc[[fy for fy in rows.index if ANCHOR_FY < fy <= DECISION_GRADE_MAX_FY]]
    assert (window["worst_flag"] == "FAIL").any(), (
        "the three-year transition no longer concentrates its adjustment inside "
        "the decision window; the seam recommendation should be re-derived"
    )
    assert float(rows.loc[2028, "pool_yoy_pct"]) > float(rows.loc[2027, "pool_yoy_pct"])


def test_the_decision_grade_boundary_is_recorded(guard) -> None:
    states = set(guard[guard["june_year"].gt(DECISION_GRADE_MAX_FY)]["horizon_state"])
    assert states == {"unvalidated_extrapolation_h21_plus"}


def test_ped_covid_sensitivity_uses_the_specification_window() -> None:
    """The COVID exclusion must be 2020Q1-2021Q4, not June years FY2020-21."""
    summary = _artifact("ped_retention_band_summary.csv")
    cohorts = set(summary["cohort"])
    assert any("ex_covid_2020Q1_2021Q4" in c for c in cohorts), (
        "the specification COVID window is not among the reported cohorts"
    )
    # The June-year variant must remain, clearly relabelled, so the two are
    # never conflated again.
    assert any("ex_covid_june_years_fy2020_fy2021" in c for c in cohorts)

    primary = summary[
        summary["source"].eq("ar1_production_h1_h12")
        & summary["cohort"].eq("balanced_ex_covid_2020Q1_2021Q4")
        & summary["horizon_band"].eq("h1_h12")
    ]
    assert not primary.empty
    row = primary.iloc[0]
    # P1 must be worse on the primary window; if this ever flips, the PED
    # verdict has to be re-derived rather than silently retained.
    assert float(row["wape_improvement_pct"]) < 0.0
    assert float(row["P1_wape"]) > float(row["P0_wape"])


def test_the_covid_calendar_definitions_agree() -> None:
    """2020Q1-2021Q4 and calendar years 2020-2021 are the same set."""
    summary = _artifact("ped_retention_band_summary.csv")
    quarter = summary[summary["cohort"].str.contains("ex_covid_2020Q1_2021Q4")].sort_values(
        ["source", "horizon_band"]
    )
    calendar = summary[summary["cohort"].str.contains("ex_covid_calendar_2020_2021")].sort_values(
        ["source", "horizon_band"]
    )
    assert len(quarter) == len(calendar) and len(quarter) > 0
    for left, right in zip(quarter["P0_wape"], calendar["P0_wape"], strict=True):
        assert float(left) == pytest.approx(float(right), abs=1e-12)


def test_checkpoint_31_scripts_write_only_to_their_artifact_directory() -> None:
    for name in [
        "checkpoint31_seam_and_long_horizon.py",
        "checkpoint3a_ped_retention_falsification.py",
        "checkpoint3bc_light_fleet_and_phev.py",
    ]:
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert 'OUT = ROOT / "artifacts" / "fleet_allocation_semantics"' in source
        for line in source.splitlines():
            if ".to_csv(" in line and "read_csv" not in line:
                assert "OUT /" in line, f"{name} writes outside the artifact dir: {line.strip()}"


def test_the_seam_and_guard_scripts_reproduce_their_artifacts() -> None:
    """Regenerating must not change the committed evidence."""
    before = (ARTIFACTS / "light_ruc_seam_method_paths.csv").read_bytes()
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "checkpoint31_seam_and_long_horizon.py")],
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")[-2000:]
    assert (ARTIFACTS / "light_ruc_seam_method_paths.csv").read_bytes() == before

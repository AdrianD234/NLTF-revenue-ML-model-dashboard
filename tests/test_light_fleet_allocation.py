"""Contract tests for the canonical light-fleet allocation engine.

These are the invariants the production correction rests on. They must fail
loudly rather than be relaxed: a tolerance widened here would re-admit the
retired lambda transfer or the divergent long-horizon pool.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.light_fleet_allocation import (
    ALLOCATION_BASIS_ID,
    AVAILABILITY_AVAILABLE,
    AVAILABILITY_UNAVAILABLE,
    CONVENTIONAL_ANCHOR_SERIES_ID,
    LAST_DECISION_GRADE_ANNUAL_FY,
    UNAVAILABLE_REASON,
    allocate_light_fleet,
    annual_availability,
    composition_shares,
    june_year_quarters,
    quarter_horizon,
    quarterly_availability,
    vfm_share_table,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
TOL = 1e-9
LAST_ACTUAL_FY = 2025


@pytest.fixture(scope="module")
def anchors() -> pd.DataFrame:
    path = PACK / "ev_phev_split_assumptions.csv"
    if not path.exists():
        pytest.skip("AR(1) pack is unavailable")
    frame = pd.read_csv(path)
    return frame[frame["scenario_name"].eq("current_basecase")].set_index("FY").sort_index()


def _actuals(anchors: pd.DataFrame) -> dict[str, float]:
    return {
        "conventional": float(anchors.loc[LAST_ACTUAL_FY, "current_conventional_light_km"]),
        "bev": float(anchors.loc[LAST_ACTUAL_FY, "current_light_bev_km"]),
        "phev": float(anchors.loc[LAST_ACTUAL_FY, "current_phev_km"]),
    }


def _allocate(anchors: pd.DataFrame, fy: int, **kwargs):
    return allocate_light_fleet(
        fy,
        float(anchors.loc[fy, "current_light_total_modelled_km"]),
        repo_root=ROOT,
        scenario_name="current_basecase",
        uptake_basis=kwargs.pop("uptake_basis", "MoT VFM base"),
        actual_classes=_actuals(anchors) if fy == LAST_ACTUAL_FY else None,
        last_actual_fy=LAST_ACTUAL_FY,
        **kwargs,
    )


# ----------------------------------------------------------- horizon policy


def test_horizon_arithmetic_places_h20_at_2030q4() -> None:
    assert quarter_horizon("2026Q1") == 1
    assert quarter_horizon("2030Q2") == 18
    assert quarter_horizon("2030Q3") == 19
    assert quarter_horizon("2030Q4") == 20
    assert quarter_horizon("2031Q1") == 21


def test_quarterly_values_remain_available_through_h20() -> None:
    for period in ["2026Q1", "2029Q4", "2030Q3", "2030Q4"]:
        assert quarterly_availability(period)[0] == AVAILABILITY_AVAILABLE, period


def test_quarterly_values_are_unavailable_from_h21() -> None:
    for period in ["2031Q1", "2031Q2", "2040Q1"]:
        status, reason = quarterly_availability(period)
        assert status == AVAILABILITY_UNAVAILABLE, period
        assert reason == UNAVAILABLE_REASON


def test_fy2030_is_the_last_fully_available_june_year() -> None:
    assert june_year_quarters(2030) == ("2029Q3", "2029Q4", "2030Q1", "2030Q2")
    assert annual_availability(2030)[0] == AVAILABILITY_AVAILABLE
    assert LAST_DECISION_GRADE_ANNUAL_FY == 2030


def test_fy2031_is_withheld_even_though_two_quarters_sit_inside_h20() -> None:
    """FY2031 straddles H19-H22, so the annual total must not publish."""
    quarters = june_year_quarters(2031)
    assert quarter_horizon(quarters[0]) == 19
    assert quarter_horizon(quarters[1]) == 20
    assert quarter_horizon(quarters[2]) == 21
    status, reason = annual_availability(2031)
    assert status == AVAILABILITY_UNAVAILABLE
    assert reason == UNAVAILABLE_REASON


# --------------------------------------------------------------- allocation


def test_fy2025_actual_classes_pass_through_untouched(anchors) -> None:
    actual = _actuals(anchors)
    result = _allocate(anchors, LAST_ACTUAL_FY)
    assert result.is_actual_anchor is True
    assert result.conventional_km == pytest.approx(actual["conventional"], abs=TOL)
    assert result.light_bev_km == pytest.approx(actual["bev"], abs=TOL)
    assert result.phev_km == pytest.approx(actual["phev"], abs=TOL)
    assert result.vfm_scenario == "actual_anchor"


def test_the_raw_conventional_anchor_is_preserved_exactly_under_the_base_basis(anchors) -> None:
    for fy in range(2026, LAST_DECISION_GRADE_ANNUAL_FY + 1):
        result = _allocate(anchors, fy)
        expected = float(anchors.loc[fy, "current_light_total_modelled_km"])
        assert result.conventional_km == pytest.approx(expected, abs=1e-6), fy
        assert result.conventional_anchor_km == pytest.approx(expected, abs=TOL)


def test_vfm_base_shares_apply_immediately_with_no_seam_blend(anchors) -> None:
    """The first forecast year carries VFM Base shares, not blended ones.

    The vendored share table is stored to six decimal places, so its vector
    sums to 1 only to within rounding. The engine normalises, which is what
    makes the class sum close exactly; the comparison here therefore uses the
    normalised vector, and separately pins that the correction really is only
    rounding rather than a reweighting.
    """
    table = vfm_share_table(ROOT, "Base_EV")
    for fy in [2026, 2027]:
        raw = table.loc[fy]
        raw_total = float(raw.sum())
        assert raw_total == pytest.approx(1.0, abs=5e-6), "VFM shares are not a rounded split"
        result = _allocate(anchors, fy)
        assert result.conventional_share == pytest.approx(float(raw["conventional"]) / raw_total, abs=1e-12)
        assert result.light_bev_share == pytest.approx(float(raw["bev"]) / raw_total, abs=1e-12)
        # and the stored value is still what a reader would recognise
        assert result.conventional_share == pytest.approx(float(raw["conventional"]), abs=5e-6)


def test_classes_sum_to_the_pool_and_shares_close_to_one(anchors) -> None:
    for fy in range(2026, LAST_DECISION_GRADE_ANNUAL_FY + 1):
        result = _allocate(anchors, fy)
        total = result.conventional_km + result.light_bev_km + result.phev_km
        assert total == pytest.approx(result.base_pool_km, abs=1e-6)
        assert abs(result.closure_residual_km) <= 1e-6
        shares = result.conventional_share + result.light_bev_share + result.phev_share
        assert shares == pytest.approx(1.0, abs=1e-12)


def test_alternative_presets_reallocate_the_base_pool_without_resizing_it(anchors) -> None:
    """A composition control must never act as a travel-demand control."""
    for fy in range(2026, LAST_DECISION_GRADE_ANNUAL_FY + 1):
        base = _allocate(anchors, fy, uptake_basis="MoT VFM base")
        for basis in ["MoT VFM fast", "MoT VFM slow"]:
            other = _allocate(anchors, fy, uptake_basis=basis)
            assert other.base_pool_km == pytest.approx(base.base_pool_km, abs=1e-6), (fy, basis)
            total = other.conventional_km + other.light_bev_km + other.phev_km
            assert total == pytest.approx(base.base_pool_km, abs=1e-6), (fy, basis)
            # and the composition genuinely differs
            assert other.light_bev_share != pytest.approx(base.light_bev_share, abs=1e-6)


def test_custom_shares_also_preserve_the_base_pool(anchors) -> None:
    custom = {"conventional": 0.5, "bev": 0.3, "phev": 0.2}
    base = _allocate(anchors, 2028, uptake_basis="MoT VFM base")
    result = _allocate(anchors, 2028, uptake_basis="custom", custom_shares=custom)
    assert result.base_pool_km == pytest.approx(base.base_pool_km, abs=1e-6)
    assert result.conventional_share == pytest.approx(0.5, abs=1e-12)
    assert result.vfm_scenario == "custom_uptake_levers"


def test_each_scenario_derives_its_own_pool_from_its_own_anchor() -> None:
    a = allocate_light_fleet(
        2030, 14000.0, repo_root=ROOT, scenario_name="a", uptake_basis="MoT VFM base"
    )
    b = allocate_light_fleet(
        2030, 15000.0, repo_root=ROOT, scenario_name="b", uptake_basis="MoT VFM base"
    )
    assert b.base_pool_km > a.base_pool_km
    assert b.base_pool_km / a.base_pool_km == pytest.approx(15000.0 / 14000.0, abs=1e-12)


# ------------------------------------------------------------ lambda is gone


def test_no_allocation_reproduces_the_retired_lambda_level(anchors) -> None:
    drift = pd.read_csv(PACK / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq("current_basecase")
        & drift["lambda_mode"].astype(str).eq("optimized")
    ].set_index("FY")
    for fy in range(2026, LAST_DECISION_GRADE_ANNUAL_FY + 1):
        if fy not in drift.index:
            continue
        migration = float(drift.loc[fy, "current_BEV_km"]) + float(drift.loc[fy, "current_PHEV_km"])
        lam = float(drift.loc[fy, "lambda_value"])
        retired_level = float(anchors.loc[fy, "current_light_total_modelled_km"]) - lam * migration
        result = _allocate(anchors, fy)
        assert abs(result.conventional_km - retired_level) > 1.0, (
            f"FY{fy} reproduced the retired lambda-reduced conventional level"
        )


# ---------------------------------------------------------------- fail-closed


def test_beyond_h20_the_allocator_fails_closed_rather_than_extrapolating(anchors) -> None:
    for fy in [2031, 2035, 2050]:
        result = allocate_light_fleet(
            fy,
            float(anchors.loc[fy, "current_light_total_modelled_km"]),
            repo_root=ROOT,
            uptake_basis="MoT VFM base",
            last_actual_fy=LAST_ACTUAL_FY,
        )
        assert result.availability_status == AVAILABILITY_UNAVAILABLE
        assert result.unavailable_reason == UNAVAILABLE_REASON
        assert result.horizon_state == "unvalidated_extrapolation_h21_plus"
        for value in [result.base_pool_km, result.conventional_km, result.light_bev_km, result.phev_km]:
            assert pd.isna(value), f"FY{fy} published a value beyond H20"


def test_a_missing_anchor_fails_closed(anchors) -> None:
    result = allocate_light_fleet(
        2028, None, repo_root=ROOT, uptake_basis="MoT VFM base", last_actual_fy=LAST_ACTUAL_FY
    )
    assert result.availability_status != AVAILABILITY_AVAILABLE
    assert pd.isna(result.conventional_km)


def test_a_non_positive_anchor_is_refused() -> None:
    with pytest.raises(ValueError, match="not positive"):
        allocate_light_fleet(2028, 0.0, repo_root=ROOT, uptake_basis="MoT VFM base")


def test_a_degenerate_custom_share_vector_is_refused() -> None:
    with pytest.raises(ValueError, match="not a valid split"):
        composition_shares(
            2028, repo_root=ROOT, custom_shares={"conventional": 0.0, "bev": 0.0, "phev": 0.0}
        )


# ------------------------------------------------------------ reproducibility


def test_the_engine_reproduces_the_audited_checkpoint_3_candidate(anchors) -> None:
    """The implemented Base path must match the audited P0/L1 candidate."""
    audited = ROOT / "artifacts" / "fleet_allocation_semantics" / "combined_light_fleet_paths.csv"
    if not audited.exists():
        pytest.skip("Checkpoint 3 candidate artifact is unavailable")
    frame = pd.read_csv(audited)
    frame = frame[frame["variant"].eq("P0/L1")].set_index("june_year")
    for fy in range(2026, LAST_DECISION_GRADE_ANNUAL_FY + 1):
        result = _allocate(anchors, fy)
        assert result.conventional_km == pytest.approx(float(frame.loc[fy, "conventional_light_ruc"]), abs=1e-4)
        assert result.light_bev_km == pytest.approx(float(frame.loc[fy, "light_bev"]), abs=1e-4)
        assert result.phev_km == pytest.approx(float(frame.loc[fy, "phev"]), abs=1e-4)
        assert result.base_pool_km == pytest.approx(float(frame.loc[fy, "light_ruc_pool"]), abs=1e-4)


def test_the_series_identifier_names_the_conventional_class() -> None:
    assert CONVENTIONAL_ANCHOR_SERIES_ID == "current_light_ruc_conventional_modelled_km"
    assert "total" not in CONVENTIONAL_ANCHOR_SERIES_ID
    assert ALLOCATION_BASIS_ID == "conventional_anchor_vfm_composition_v1"

"""Fleet efficiency and PT mode shift are continuous through FY2050.

Owner-approved mathematical contract (2026-08):

* both levers compound as ``(1 - r)^n`` with ``n(FY) = max(FY - 2025, 0)``,
  implemented as ``exp(n * log1p(-r))``;
* PT mode shift starts at ``REVENUE_FIRST_FORECAST_FY`` (2026), no longer
  FY2030;
* the FY2030/FY2031 econometric/post-model seam carries the factor through:
  ``factor(2031) == factor(2030) * (1 - r)``;
* Fleet efficiency owns litres-per-100km only; PT mode shift scales the four
  light powertrain activity families equally and preserves their shares;
* PED volume and revenue are reconstructed from that FY's own baseline and
  the cumulative factor - never recursively from the previous adjusted year.

Tolerance regimes (handoff section 7):

* EXACT - Off vs baseline, unaffected series, official rows;
* GOVERNED ACCOUNTING - formula closure keeps the repository's tight bounds;
* PRESENTATION PARITY - independently reconstructed paths compare at
  1e-4 in published display units.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.engine import engine_revenue_outlook_dir
from model_dashboard.revenue_outlook import (
    CURRENT_LIGHT_TOTAL_SERIES_ID,
    FLEET_EFFICIENCY_LEVELS,
    PT_MODE_SHIFT_LEVELS,
    REVENUE_FIRST_FORECAST_FY,
    SENSITIVITY_FLEET_START_FY,
    SENSITIVITY_PT_START_FY,
    apply_revenue_sensitivity_layer,
    load_revenue_outlook_pack,
    revenue_sensitivity_impact_audit_frame,
    sensitivity_config_frame,
)

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ("vnext", "ar1")
KEY_FYS = (2026, 2030, 2031, 2040, 2050)
LAST_LONG_RUN_FY = 2050
BASE_PATH = "Current finalist Base case"
COMPARISON_PATH = "Current finalist High population/comparison"
DISPLAY_UNIT_ATOL = 1e-4  # presentation parity: 1e-4 in published units

LIGHT_ACTIVITY_FAMILIES = (
    "light_petrol_vkt",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
)
UNTOUCHED_BY_BOTH_LEVERS = (
    "heavy_bev_ruc_net_km",
    "heavy_bev_ruc_net_revenue",
    "gross_mvr_revenue",
    "net_mvr_revenue",
    "mvr_admin_revenue",
    "mvr_refunds",
)


def _factor(rate: float, fy: int, start_fy: int) -> float:
    exponent = max(fy - start_fy + 1, 0)
    return (1.0 - rate) ** exponent


@lru_cache(maxsize=None)
def _pack(engine: str):
    pack = load_revenue_outlook_pack(ROOT / engine_revenue_outlook_dir(engine), repo_root=ROOT)
    assert pack is not None, f"promoted Revenue Outlook pack missing for engine {engine}"
    return pack


@lru_cache(maxsize=None)
def _audit(engine: str, fleet: str, pt: str, custom_fleet_pct: float | None = None) -> pd.DataFrame:
    pack = _pack(engine)
    audit = revenue_sensitivity_impact_audit_frame(
        pack.revenue_line_reconciliation,
        pack.ped_revenue_bridge_audit,
        pack.sensitivity_config if isinstance(pack.sensitivity_config, pd.DataFrame) else sensitivity_config_frame(),
        fleet_efficiency=fleet,
        pt_mode_shift=pt,
        custom_fleet_efficiency_pct=custom_fleet_pct,
    )
    audit = audit.copy()
    audit["FY_numeric"] = pd.to_numeric(audit["FY"], errors="coerce")
    return audit


@lru_cache(maxsize=None)
def _layer(engine: str, fleet: str, pt: str, custom_fleet_pct: float | None = None):
    pack = _pack(engine)
    return apply_revenue_sensitivity_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        sensitivity_config=pack.sensitivity_config,
        fleet_efficiency=fleet,
        pt_mode_shift=pt,
        custom_fleet_efficiency_pct=custom_fleet_pct,
    )


def _ratio(audit: pd.DataFrame, series_id: str, fy: int, source_path: str = BASE_PATH) -> float:
    rows = audit[
        audit["series_id"].astype(str).eq(series_id)
        & audit["FY_numeric"].eq(fy)
        & audit["source_path"].astype(str).eq(source_path)
    ]
    if rows.empty:
        return np.nan
    baseline = float(rows["baseline"].iloc[0])
    adjusted = float(rows["adjusted"].iloc[0])
    return adjusted / baseline if baseline != 0 else np.nan


def _series_row(audit: pd.DataFrame, series_id: str, fy: int, source_path: str = BASE_PATH) -> pd.Series:
    rows = audit[
        audit["series_id"].astype(str).eq(series_id)
        & audit["FY_numeric"].eq(fy)
        & audit["source_path"].astype(str).eq(source_path)
    ]
    assert not rows.empty, f"no audit row for {series_id} FY{fy} on {source_path}"
    return rows.iloc[0]


# ---------------------------------------------------------------------------
# governance constants
# ---------------------------------------------------------------------------


def test_pt_mode_shift_starts_at_first_forecast_fy() -> None:
    assert SENSITIVITY_PT_START_FY == REVENUE_FIRST_FORECAST_FY == 2026
    assert SENSITIVITY_FLEET_START_FY == REVENUE_FIRST_FORECAST_FY


# ---------------------------------------------------------------------------
# fleet efficiency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_off_equals_baseline_exactly_through_fy2050(engine: str) -> None:
    pack = _pack(engine)
    off = _layer(engine, "Off", "Off")
    assert pd.to_numeric(off["chart_rows"]["value"], errors="coerce").equals(
        pd.to_numeric(pack.revenue_chart_rows["value"], errors="coerce")
    )
    assert pd.to_numeric(off["line_reconciliation"]["value"], errors="coerce").equals(
        pd.to_numeric(pack.revenue_line_reconciliation["value"], errors="coerce")
    )
    audit = off["sensitivity_impact_audit"]
    assert pd.to_numeric(audit["delta"], errors="coerce").abs().max() == pytest.approx(0.0, abs=0)


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_only_leaves_all_activity_unchanged(engine: str) -> None:
    audit = _audit(engine, "Med", "Off")
    activity = [
        "light_petrol_vkt",
        "ped_vkt_per_capita",
        "light_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "heavy_ruc_net_km",
        CURRENT_LIGHT_TOTAL_SERIES_ID,
    ]
    rows = audit[audit["series_id"].astype(str).isin(activity)]
    assert not rows.empty
    assert int(rows["FY_numeric"].max()) == LAST_LONG_RUN_FY
    assert (
        pd.to_numeric(rows["adjusted"], errors="coerce").to_numpy()
        == pd.to_numeric(rows["baseline"], errors="coerce").to_numpy()
    ).all()


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("level", ["Low", "Med", "High"])
def test_fleet_preset_factors_follow_compound_formula(engine: str, level: str) -> None:
    rate = FLEET_EFFICIENCY_LEVELS[level]
    audit = _audit(engine, level, "Off")
    for fy in KEY_FYS:
        expected = _factor(rate, fy, SENSITIVITY_FLEET_START_FY)
        for series_id in ("ped_volume", "gross_ped_revenue"):
            assert _ratio(audit, series_id, fy) == pytest.approx(expected, rel=1e-9), (
                f"{series_id} FY{fy} {level}"
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_custom_ten_percent_follows_same_formula(engine: str) -> None:
    audit = _audit(engine, "Custom", "Off", 10.0)
    for fy in KEY_FYS:
        expected = _factor(0.10, fy, SENSITIVITY_FLEET_START_FY)
        assert _ratio(audit, "ped_volume", fy) == pytest.approx(expected, rel=1e-9)
    # The extreme stress keeps declining after FY2030 rather than flattening
    # or being capped back to a preset.
    assert _ratio(audit, "ped_volume", 2050) < _ratio(audit, "ped_volume", 2040) < _ratio(audit, "ped_volume", 2031) < 1.0


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_ratio_does_not_reset_at_fy2031(engine: str) -> None:
    rate = FLEET_EFFICIENCY_LEVELS["Med"]
    audit = _audit(engine, "Med", "Off")
    r_2030 = _ratio(audit, "ped_volume", 2030)
    r_2031 = _ratio(audit, "ped_volume", 2031)
    assert r_2031 != pytest.approx(1.0, abs=1e-12)
    # Seam relationship: factor_FY2031 == factor_FY2030 * (1 - e).
    assert r_2031 == pytest.approx(r_2030 * (1.0 - rate), rel=1e-9)
    ratios = [_ratio(audit, "ped_volume", fy) for fy in range(2026, LAST_LONG_RUN_FY + 1)]
    assert all(np.isfinite(r) for r in ratios)
    assert all(later < earlier for earlier, later in zip(ratios, ratios[1:]))


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_ped_revenue_reconstructed_from_selected_rate(engine: str) -> None:
    audit = _audit(engine, "Med", "Off")
    for fy in KEY_FYS:
        volume = _series_row(audit, "ped_volume", fy)
        revenue = _series_row(audit, "gross_ped_revenue", fy)
        rate = float(pd.to_numeric(revenue.get("ped_rate_nzd_per_litre"), errors="coerce"))
        assert np.isfinite(rate) and rate > 0
        assert float(revenue["adjusted"]) == pytest.approx(float(volume["adjusted"]) * rate, rel=1e-9)
        # The stamped rate is the FY's own effective PED rate, so the selected
        # rate path (published / delayed / no-uplift timing enters upstream)
        # is preserved rather than replaced by a constant.
        assert rate == pytest.approx(float(revenue["baseline"]) / float(volume["baseline"]), rel=1e-9)


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_formula_rollups_close(engine: str) -> None:
    result = _layer(engine, "Med", "Off")
    residuals = result["revenue_formula_residuals"]
    current = residuals[residuals["source_path"].astype(str).str.startswith("Current finalist")]
    assert not current.empty
    assert set(current["status"].dropna().astype(str)) == {"reconciled"}
    audit = result["sensitivity_impact_audit"]
    audit = audit.copy()
    audit["FY_numeric"] = pd.to_numeric(audit["FY"], errors="coerce")
    for fy in KEY_FYS:
        ped_delta = float(_series_row(audit, "gross_ped_revenue", fy)["delta"])
        for rollup in ("gross_fed_revenue", "net_fed_revenue", "total_nltf_net_revenue"):
            row = _series_row(audit, rollup, fy)
            assert float(row["delta"]) == pytest.approx(ped_delta, rel=1e-9, abs=DISPLAY_UNIT_ATOL)


@pytest.mark.parametrize("engine", ENGINES)
def test_fleet_effect_ordering_high_med_low(engine: str) -> None:
    deltas = {}
    for level in ("Low", "Med", "High"):
        audit = _audit(engine, level, "Off")
        deltas[level] = abs(float(_series_row(audit, "ped_volume", 2050)["delta"]))
    assert deltas["High"] > deltas["Med"] > deltas["Low"] > 0


# ---------------------------------------------------------------------------
# PT mode shift
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_begins_in_fy2026(engine: str) -> None:
    rate = PT_MODE_SHIFT_LEVELS["Med"]
    audit = _audit(engine, "Off", "Med")
    assert _ratio(audit, "light_petrol_vkt", 2026) == pytest.approx(1.0 - rate, rel=1e-9)
    assert _ratio(audit, "light_petrol_vkt", 2026) != pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("level", ["Low", "Med", "High"])
def test_pt_factor_follows_compound_formula_through_fy2050(engine: str, level: str) -> None:
    rate = PT_MODE_SHIFT_LEVELS[level]
    audit = _audit(engine, "Off", level)
    for fy in KEY_FYS:
        expected = _factor(rate, fy, SENSITIVITY_PT_START_FY)
        assert _ratio(audit, "light_petrol_vkt", fy) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_applies_one_factor_to_all_light_families_and_total(engine: str) -> None:
    rate = PT_MODE_SHIFT_LEVELS["Med"]
    audit = _audit(engine, "Off", "Med")
    for fy in KEY_FYS:
        expected = _factor(rate, fy, SENSITIVITY_PT_START_FY)
        for series_id in LIGHT_ACTIVITY_FAMILIES + (CURRENT_LIGHT_TOTAL_SERIES_ID, "ped_vkt_per_capita"):
            assert _ratio(audit, series_id, fy) == pytest.approx(expected, rel=1e-9), (
                f"{series_id} FY{fy}"
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_preserves_light_powertrain_shares(engine: str) -> None:
    audit = _audit(engine, "Off", "Med")
    for fy in KEY_FYS:
        rows = {series_id: _series_row(audit, series_id, fy) for series_id in LIGHT_ACTIVITY_FAMILIES}
        base_total = sum(float(row["baseline"]) for row in rows.values())
        adj_total = sum(float(row["adjusted"]) for row in rows.values())
        for series_id, row in rows.items():
            assert float(row["adjusted"]) / adj_total == pytest.approx(
                float(row["baseline"]) / base_total, rel=1e-9
            ), f"{series_id} share moved at FY{fy}"


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_leaves_heavy_and_mvr_exactly_unchanged(engine: str) -> None:
    pack = _pack(engine)
    result = _layer(engine, "Off", "Med")
    audit = result["sensitivity_impact_audit"].copy()
    audit["FY_numeric"] = pd.to_numeric(audit["FY"], errors="coerce")
    heavy = audit[audit["series_id"].astype(str).isin(["heavy_ruc_net_km", "heavy_ruc_net_revenue"])]
    assert (
        pd.to_numeric(heavy["adjusted"], errors="coerce").to_numpy()
        == pd.to_numeric(heavy["baseline"], errors="coerce").to_numpy()
    ).all()
    original = pack.revenue_line_reconciliation
    adjusted = result["line_reconciliation"]
    untouched_mask = original["series_id"].astype(str).isin(UNTOUCHED_BY_BOTH_LEVERS)
    assert (
        pd.to_numeric(adjusted.loc[untouched_mask, "value"], errors="coerce").to_numpy()
        == pd.to_numeric(original.loc[untouched_mask, "value"], errors="coerce").to_numpy()
    ).all()


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_ratio_does_not_reset_at_fy2031(engine: str) -> None:
    rate = PT_MODE_SHIFT_LEVELS["Med"]
    audit = _audit(engine, "Off", "Med")
    for series_id in ("light_petrol_vkt", "ped_volume"):
        r_2030 = _ratio(audit, series_id, 2030)
        r_2031 = _ratio(audit, series_id, 2031)
        assert r_2031 == pytest.approx(r_2030 * (1.0 - rate), rel=1e-9), series_id
        assert r_2031 < r_2030 < 1.0


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_revenue_recomputed_from_adjusted_activity_and_existing_rates(engine: str) -> None:
    audit = _audit(engine, "Off", "Med")
    for fy in KEY_FYS:
        for km_id, revenue_id in (
            ("light_ruc_net_km", "light_ruc_net_revenue"),
            ("light_bev_ruc_net_km", "light_bev_ruc_net_revenue"),
            ("phev_ruc_net_km", "phev_ruc_net_revenue"),
        ):
            km = _series_row(audit, km_id, fy)
            revenue = _series_row(audit, revenue_id, fy)
            effective_rate = float(revenue["baseline"]) / float(km["baseline"])
            assert float(revenue["adjusted"]) == pytest.approx(
                float(km["adjusted"]) * effective_rate, rel=1e-9
            ), f"{revenue_id} FY{fy}"


@pytest.mark.parametrize("engine", ENGINES)
def test_pt_leaves_official_rows_unchanged(engine: str) -> None:
    pack = _pack(engine)
    result = _layer(engine, "Off", "Med")
    original = pack.revenue_chart_rows
    adjusted = result["chart_rows"]
    official_mask = original["trace_role"].astype(str).eq("official_external_comparator")
    assert official_mask.any()
    assert (
        pd.to_numeric(adjusted.loc[official_mask, "value"], errors="coerce").to_numpy()
        == pd.to_numeric(original.loc[official_mask, "value"], errors="coerce").to_numpy()
    ).all()


# ---------------------------------------------------------------------------
# combined levers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES)
def test_combined_ped_volume_is_product_of_both_factors(engine: str) -> None:
    fleet_rate = FLEET_EFFICIENCY_LEVELS["Med"]
    pt_rate = PT_MODE_SHIFT_LEVELS["Med"]
    audit = _audit(engine, "Med", "Med")
    for fy in KEY_FYS:
        pt_factor = _factor(pt_rate, fy, SENSITIVITY_PT_START_FY)
        fleet_factor = _factor(fleet_rate, fy, SENSITIVITY_FLEET_START_FY)
        assert _ratio(audit, "ped_volume", fy) == pytest.approx(pt_factor * fleet_factor, rel=1e-9)
        # Neither lever is applied twice: activity carries ONLY the PT factor
        # and intensity ONLY the fleet factor.
        assert _ratio(audit, "light_petrol_vkt", fy) == pytest.approx(pt_factor, rel=1e-9)
        row = _series_row(audit, "ped_volume", fy)
        litres_ratio = float(
            pd.to_numeric(row.get("adjusted_litres_per_100km"), errors="coerce")
        ) / float(pd.to_numeric(row.get("base_litres_per_100km"), errors="coerce"))
        assert litres_ratio == pytest.approx(fleet_factor, rel=1e-9)


@pytest.mark.parametrize("engine", ENGINES)
def test_combined_preserves_ev_phev_composition(engine: str) -> None:
    audit = _audit(engine, "Med", "Med")
    for fy in KEY_FYS:
        rows = {series_id: _series_row(audit, series_id, fy) for series_id in LIGHT_ACTIVITY_FAMILIES}
        base_total = sum(float(row["baseline"]) for row in rows.values())
        adj_total = sum(float(row["adjusted"]) for row in rows.values())
        for series_id, row in rows.items():
            assert float(row["adjusted"]) / adj_total == pytest.approx(
                float(row["baseline"]) / base_total, rel=1e-9
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_both_current_source_paths_follow_the_same_contract(engine: str) -> None:
    fleet_rate = FLEET_EFFICIENCY_LEVELS["Med"]
    audit = _audit(engine, "Med", "Off")
    for source_path in (BASE_PATH, COMPARISON_PATH):
        for fy in KEY_FYS:
            expected = _factor(fleet_rate, fy, SENSITIVITY_FLEET_START_FY)
            assert _ratio(audit, "ped_volume", fy, source_path) == pytest.approx(
                expected, rel=1e-9
            ), f"{source_path} FY{fy}"


@pytest.mark.parametrize("engine", ENGINES)
def test_every_fed_path_group_is_sensitised(engine: str) -> None:
    """All policy-state rate paths present in the pack inherit the lever.

    The published / delayed_6m / no-uplift states select their rates upstream
    of this layer; each fed_path group in the audit must carry the same
    proportional contract so no policy state serves an unsensitised long run.
    """
    audit = _audit(engine, "Med", "Off")
    fed_paths = sorted(set(audit["fed_path"].dropna().astype(str)))
    assert fed_paths
    rate = FLEET_EFFICIENCY_LEVELS["Med"]
    for fed_path in fed_paths:
        subset = audit[audit["fed_path"].astype(str).eq(fed_path)]
        rows = subset[
            subset["series_id"].astype(str).eq("ped_volume")
            & subset["FY_numeric"].eq(LAST_LONG_RUN_FY)
        ]
        if rows.empty:
            continue
        ratio = float(rows["adjusted"].iloc[0]) / float(rows["baseline"].iloc[0])
        assert ratio == pytest.approx(_factor(rate, LAST_LONG_RUN_FY, SENSITIVITY_FLEET_START_FY), rel=1e-9)


# ---------------------------------------------------------------------------
# horizon, chart rows and quarterly grain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ENGINES)
def test_every_adjusted_series_reaches_fy2050(engine: str) -> None:
    audit = _audit(engine, "Med", "Med")
    moved = audit[
        pd.to_numeric(audit["adjusted"], errors="coerce")
        != pd.to_numeric(audit["baseline"], errors="coerce")
    ]
    coverage = moved.groupby(moved["series_id"].astype(str))["FY_numeric"].max()
    for series_id in ("ped_volume", "gross_ped_revenue", "light_petrol_vkt", "total_nltf_net_revenue"):
        assert int(coverage.loc[series_id]) == LAST_LONG_RUN_FY, series_id


@pytest.mark.parametrize("engine", ENGINES)
def test_post_model_rows_carry_provenance_stamps(engine: str) -> None:
    audit = _audit(engine, "Med", "Med")
    post_model = audit[audit["forecast_segment"].astype(str).eq("post_model_extrapolation")]
    assert not post_model.empty
    assert int(post_model["FY_numeric"].min()) == 2031
    assert int(post_model["FY_numeric"].max()) == LAST_LONG_RUN_FY
    assert post_model["computation_key"].astype(str).str.contains("fleet=Med").all()
    assert post_model["computation_key"].astype(str).str.contains("pt=Med").all()
    exponents = pd.to_numeric(post_model["fleet_exponent"], errors="coerce")
    assert (exponents == post_model["FY_numeric"] - 2025).all()
    factors = pd.to_numeric(post_model["fleet_factor"], errors="coerce")
    expected = np.power(1.0 - FLEET_EFFICIENCY_LEVELS["Med"], exponents.astype(float))
    assert factors.to_numpy() == pytest.approx(expected.to_numpy(), rel=1e-9)


@pytest.mark.parametrize("engine", ENGINES)
def test_chart_rows_inherit_the_full_horizon_adjustment(engine: str) -> None:
    pack = _pack(engine)
    result = _layer(engine, "Med", "Off")
    original = pack.revenue_chart_rows
    adjusted = result["chart_rows"]
    fleet_rate = FLEET_EFFICIENCY_LEVELS["Med"]
    mask = (
        original["trace_role"].astype(str).eq("in_house_current_finalist")
        & original["series_id"].astype(str).eq("ped_volume")
        & original["time_grain"].astype(str).eq("june_year")
        & original["trace_name"].astype(str).eq(BASE_PATH)
    )
    subset_original = original[mask]
    subset_adjusted = adjusted.loc[subset_original.index]
    fys = pd.to_numeric(subset_original["june_year"], errors="coerce")
    for fy in KEY_FYS:
        rows = fys.eq(fy)
        if not rows.any():
            continue
        baseline_value = float(pd.to_numeric(subset_original.loc[rows, "value"], errors="coerce").iloc[0])
        adjusted_value = float(pd.to_numeric(subset_adjusted.loc[rows, "value"], errors="coerce").iloc[0])
        assert adjusted_value == pytest.approx(
            baseline_value * _factor(fleet_rate, fy, SENSITIVITY_FLEET_START_FY), rel=1e-9
        ), f"chart FY{fy}"


@pytest.mark.parametrize("engine", ENGINES)
def test_native_quarters_scale_by_their_annual_ratio_not_twice(engine: str) -> None:
    pack = _pack(engine)
    result = _layer(engine, "Off", "Med")
    original = pack.revenue_chart_rows
    adjusted = result["chart_rows"]
    pt_rate = PT_MODE_SHIFT_LEVELS["Med"]
    mask = (
        original["time_grain"].astype(str).eq("quarterly")
        & original["trace_role"].astype(str).eq("in_house_current_finalist")
        & original["series_id"].astype(str).isin(["light_ruc_net_km", "ped_vkt_per_capita"])
        & original["trace_name"].astype(str).eq(BASE_PATH)
    )
    subset_original = original[mask]
    assert not subset_original.empty
    subset_adjusted = adjusted.loc[subset_original.index]
    fys = pd.to_numeric(subset_original["june_year"], errors="coerce")
    for index in subset_original.index:
        fy = int(fys.loc[index])
        expected = _factor(pt_rate, fy, SENSITIVITY_PT_START_FY)
        baseline_value = float(pd.to_numeric(subset_original.loc[index, "value"], errors="coerce"))
        adjusted_value = float(pd.to_numeric(subset_adjusted.loc[index, "value"], errors="coerce"))
        # One annual ratio per June year - a second quarterly compounding
        # would show up as expected**2 here.
        assert adjusted_value == pytest.approx(baseline_value * expected, rel=1e-9)


@pytest.mark.parametrize("engine", ENGINES)
def test_no_public_quarter_beyond_2050q2(engine: str) -> None:
    result = _layer(engine, "Med", "Med")
    adjusted = result["chart_rows"]
    quarters = adjusted[adjusted["time_grain"].astype(str).eq("quarterly")]["period"].astype(str)
    assert not quarters.isin(["2050Q3", "2050Q4"]).any()


# ---------------------------------------------------------------------------
# uncertainty bands
# ---------------------------------------------------------------------------


def test_uncertainty_bands_withheld_while_either_lever_is_active() -> None:
    import app

    default_key = ("Off", "Off", "Off", "", "", "", "", "", "", "Off", "")
    assert app._uncertainty_bands_withheld_for_sensitivity(default_key) is False
    fleet_key = ("Med",) + default_key[1:]
    assert app._uncertainty_bands_withheld_for_sensitivity(fleet_key) is True
    pt_key = ("Off", "Med") + default_key[2:]
    assert app._uncertainty_bands_withheld_for_sensitivity(pt_key) is True
    custom_key = ("Custom", "Off") + default_key[2:]
    assert app._uncertainty_bands_withheld_for_sensitivity(custom_key) is True
    # Freight / demand levers are outside this contract and keep bands.
    freight_key = ("Off", "Off", "Off", "", "", "", "", "", "", "Med", "")
    assert app._uncertainty_bands_withheld_for_sensitivity(freight_key) is False
    assert "withheld" in app.SENSITIVITY_UNCERTAINTY_WITHHELD_NOTE

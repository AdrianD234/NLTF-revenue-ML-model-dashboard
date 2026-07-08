from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.ev_uptake_levers import (
    EV_UPTAKE_PRESETS,
    UptakeLevers,
    apply_uptake_levers_to_chart_rows,
    heavy_bev_share_curve,
    lever_share_curves,
    ped_retention_curve,
    solve_logistic_from_levers,
)

ROOT = Path(__file__).resolve().parents[1]
VFM_SHARES = ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv"

PRESET_TO_VFM_SCENARIO = {
    "MoT VFM base": "Base_EV",
    "MoT VFM fast": "Fast_EV",
    "MoT VFM slow": "Slow_EV",
}


def test_logistic_solver_honours_levers() -> None:
    smax, k = solve_logistic_from_levers(0.045, 2038.0, 0.82)
    # 2050 share reproduced
    assert abs(smax / (1 + np.exp(-k * (2050 - 2038))) - 0.82) < 1e-4
    # peak slope equals the speed lever
    assert abs(smax * k / 4 - 0.045) < 1e-6


def test_share_curves_sum_to_one_and_stay_positive() -> None:
    for levers in EV_UPTAKE_PRESETS.values():
        curves = lever_share_curves(range(2025, 2051), levers)
        total = curves["bev"] + curves["phev"] + curves["conventional"]
        assert np.allclose(total, 1.0, atol=1e-9)
        assert (curves[["bev", "phev", "conventional"]] >= 0).all().all()


def test_extreme_levers_never_overflow_the_pool() -> None:
    aggressive = UptakeLevers(0.09, 2030.0, 0.99, 0.05, 0.03, 0.30, 0.01, 0.10, 2032.0, 0.95, 0.06, 2040.0, 0.75)
    curves = lever_share_curves(range(2025, 2051), aggressive)
    assert (curves["conventional"] >= 0.005 - 1e-9).all()
    retention = ped_retention_curve(range(2025, 2051), aggressive)
    assert (retention >= 0).all() and (retention <= 1).all()
    share = heavy_bev_share_curve(range(2025, 2051), aggressive)
    assert (share <= 0.995).all()


def test_vfm_presets_reproduce_official_scenarios() -> None:
    shares = pd.read_csv(VFM_SHARES)
    for preset_name, scenario in PRESET_TO_VFM_SCENARIO.items():
        official = shares[shares["scenario"].eq(scenario)].set_index("june_year")
        curves = lever_share_curves(official.index, EV_UPTAKE_PRESETS[preset_name]).set_index("june_year")
        bev_err = (curves["bev"] - official["light_ruc_bev_share"]).abs().max()
        phev_err = (curves["phev"] - official["light_ruc_phev_share"]).abs().max()
        assert bev_err < 0.016, f"{preset_name}: BEV share max error {bev_err:.4f}"
        assert phev_err < 0.016, f"{preset_name}: PHEV share max error {phev_err:.4f}"


def test_vfm_presets_reproduce_official_ped_retention_and_heavy_share() -> None:
    shares = pd.read_csv(VFM_SHARES)
    for preset_name, scenario in PRESET_TO_VFM_SCENARIO.items():
        official = shares[shares["scenario"].eq(scenario)].set_index("june_year")
        levers = EV_UPTAKE_PRESETS[preset_name]
        retention_official = official["light_petrol_share_of_light_vkt"] / official["light_petrol_share_of_light_vkt"].loc[2025]
        retention = ped_retention_curve(official.index, levers)
        ped_err = (retention - retention_official).abs().max()
        assert ped_err < 0.03, f"{preset_name}: PED retention max error {ped_err:.4f}"
        heavy = heavy_bev_share_curve(official.index, levers)
        heavy_err = (heavy - official["heavy_bev_vkt_share"]).abs().max()
        assert heavy_err < 0.02, f"{preset_name}: heavy BEV share max error {heavy_err:.4f}"


def test_mbu26_preset_ped_retention_is_activity_only() -> None:
    """MBU26 PED levers track the petrol *share* of the light universe.

    Intensity (litres/100km) belongs to the Fleet efficiency sensitivity, so
    the preset must reproduce the share-retention path, not the volume path.
    """
    mbu = pd.read_csv(ROOT / "data" / "revenue_model_source_pack" / "mbu26_annual_spine" / "mbu26_official_annual.csv")
    piv = (
        mbu.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first")
        .loc[2025:2050]
        .apply(pd.to_numeric, errors="coerce")
    )
    universe = (
        piv["light_petrol_vkt"]
        + piv["light_ruc_net_km"]
        + piv["light_bev_ruc_net_km"]
        + piv["phev_ruc_net_km"]
    )
    share = piv["light_petrol_vkt"] / universe
    target = share / share.loc[2025]
    retention = ped_retention_curve(target.index, EV_UPTAKE_PRESETS["MBU26 official shape"])
    err = (retention - target).abs().max()
    assert err < 0.025, f"MBU26 PED share-retention max error {err:.4f}"


def test_ped_retention_starts_at_one_and_declines() -> None:
    for levers in EV_UPTAKE_PRESETS.values():
        retention = ped_retention_curve(range(2025, 2051), levers)
        assert abs(retention.loc[2025] - 1.0) < 1e-9
        assert retention.is_monotonic_decreasing
        assert retention.loc[2050] < 0.5


def test_heavy_share_starts_at_zero_and_rises() -> None:
    for levers in EV_UPTAKE_PRESETS.values():
        share = heavy_bev_share_curve(range(2025, 2051), levers)
        assert abs(share.loc[2025]) < 1e-9
        assert share.is_monotonic_increasing
        assert 0.05 < share.loc[2050] < 0.5


def _fixture_chart_rows_and_drift() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    drift = []
    for scenario, pool_2049, pool_2050 in [
        ("current_basecase", 49000.0, 49300.0),
        ("current_comparison_1", 55800.0, 56100.0),
    ]:
        for fy, pool in [(2049, pool_2049), (2050, pool_2050)]:
            drift.append(
                {
                    "lambda_mode": "optimized",
                    "scenario_name": scenario,
                    "FY": fy,
                    "current_L_t_total_light_ruc_km": pool,
                    "conventional_light_rate": 0.09,
                    "light_bev_rate": 0.08,
                    "phev_rate": 0.05,
                }
            )
            for series_id, value in [
                ("light_ruc_net_km", pool * 0.12),
                ("light_bev_ruc_net_km", pool * 0.82),
                ("phev_ruc_net_km", pool * 0.06),
                ("light_ruc_net_revenue", pool * 0.12 * 0.09),
                ("light_bev_ruc_net_revenue", pool * 0.82 * 0.08),
                ("phev_ruc_net_revenue", pool * 0.06 * 0.05),
                ("ped_vkt_per_capita", 1500.0),
                ("ped_volume", 2800.0),
                ("gross_ped_revenue", 1960.0),
                ("gross_fed_revenue", 2100.0),
                ("net_fed_revenue", 2000.0),
                ("heavy_ruc_net_km", 4700.0),
                ("heavy_ruc_net_revenue", 3000.0),
                ("total_nltf_net_revenue", 8000.0),
            ]:
                rows.append(
                    {
                        "series_id": series_id,
                        "scenario_name": scenario,
                        "june_year": fy,
                        "time_grain": "june_year",
                        "row_type": "current_forecast",
                        "value": value,
                        "value_status": "",
                        "data_scope": "",
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(drift)


def test_overlay_preserves_pool_identity_and_prevents_crossing() -> None:
    chart_rows, drift = _fixture_chart_rows_and_drift()
    levers = EV_UPTAKE_PRESETS["MoT VFM base"]
    adjusted, audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers)
    assert not audit.empty
    for scenario, fy in [("current_basecase", 2050), ("current_comparison_1", 2050)]:
        sel = adjusted[adjusted["scenario_name"].eq(scenario) & adjusted["june_year"].eq(fy)]
        km = {row["series_id"]: row["value"] for _, row in sel.iterrows()}
        pool = drift[(drift["scenario_name"].eq(scenario)) & (drift["FY"].eq(fy))]["current_L_t_total_light_ruc_km"].iloc[0]
        total = km["light_ruc_net_km"] + km["light_bev_ruc_net_km"] + km["phev_ruc_net_km"]
        assert abs(total - pool) < 1e-6
    # conventional light RUC preserves the scenario ordering (no crossing)
    conv = {
        scenario: float(
            adjusted[
                adjusted["scenario_name"].eq(scenario)
                & adjusted["june_year"].eq(2050)
                & adjusted["series_id"].eq("light_ruc_net_km")
            ]["value"].iloc[0]
        )
        for scenario in ["current_basecase", "current_comparison_1"]
    }
    assert conv["current_comparison_1"] > conv["current_basecase"]


def test_overlay_cascades_revenue_delta_to_aggregates_and_tags_rows() -> None:
    chart_rows, drift = _fixture_chart_rows_and_drift()
    levers = EV_UPTAKE_PRESETS["MoT VFM base"]
    adjusted, audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers)
    sel_old = chart_rows[chart_rows["scenario_name"].eq("current_basecase") & chart_rows["june_year"].eq(2050)]
    sel_new = adjusted[adjusted["scenario_name"].eq("current_basecase") & adjusted["june_year"].eq(2050)]
    old = {row["series_id"]: row["value"] for _, row in sel_old.iterrows()}
    new = {row["series_id"]: row["value"] for _, row in sel_new.iterrows()}
    light_delta = sum(
        new[s] - old[s]
        for s in ["light_ruc_net_revenue", "light_bev_ruc_net_revenue", "phev_ruc_net_revenue"]
    )
    ped_delta = new["gross_ped_revenue"] - old["gross_ped_revenue"]
    # heavy split is rollup-neutral (same per-km rate for heavy BEVs in MBU26)
    aggregate_delta = new["total_nltf_net_revenue"] - old["total_nltf_net_revenue"]
    assert abs((light_delta + ped_delta) - aggregate_delta) < 1e-9
    fed_delta = new["gross_fed_revenue"] - old["gross_fed_revenue"]
    assert abs(fed_delta - ped_delta) < 1e-9
    assert set(sel_new["value_status"]) == {"lever_adjusted"}
    assert set(sel_new["data_scope"]) == {"ev_uptake_lever_overlay"}


def test_ped_displacement_scales_family_and_respects_bridge_gate() -> None:
    chart_rows, drift = _fixture_chart_rows_and_drift()
    levers = EV_UPTAKE_PRESETS["MoT VFM base"]
    adjusted, audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers, adjust_ped=True)
    retention_2050 = float(audit[audit["june_year"].eq(2050)]["ped_retention"].iloc[0])
    assert retention_2050 < 0.35
    sel = adjusted[adjusted["scenario_name"].eq("current_basecase") & adjusted["june_year"].eq(2050)]
    values = {row["series_id"]: row["value"] for _, row in sel.iterrows()}
    assert values["ped_volume"] == pytest.approx(2800.0 * retention_2050)
    assert values["ped_vkt_per_capita"] == pytest.approx(1500.0 * retention_2050)
    assert values["gross_ped_revenue"] == pytest.approx(1960.0 * retention_2050)
    # optimized-migration bridge already displaces petrol: gate must skip PED
    gated, gated_audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers, adjust_ped=False)
    gsel = gated[gated["scenario_name"].eq("current_basecase") & gated["june_year"].eq(2050)]
    gvalues = {row["series_id"]: row["value"] for _, row in gsel.iterrows()}
    assert gvalues["ped_volume"] == pytest.approx(2800.0)
    assert set(gated_audit["ped_retention"]) == {1.0}


def test_heavy_split_moves_km_but_is_rollup_neutral() -> None:
    chart_rows, drift = _fixture_chart_rows_and_drift()
    levers = EV_UPTAKE_PRESETS["MoT VFM base"]
    adjusted, audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers, adjust_ped=False)
    share_2050 = float(audit[audit["june_year"].eq(2050)]["heavy_bev_share"].iloc[0])
    assert 0.15 < share_2050 < 0.30
    sel = adjusted[adjusted["scenario_name"].eq("current_basecase") & adjusted["june_year"].eq(2050)]
    values = {row["series_id"]: row["value"] for _, row in sel.iterrows()}
    assert values["heavy_ruc_net_km"] == pytest.approx(4700.0 * (1 - share_2050))
    assert values["heavy_ruc_net_revenue"] == pytest.approx(3000.0 * (1 - share_2050))
    reallocated = float(audit[audit["june_year"].eq(2050)]["heavy_revenue_reallocated_to_bev"].iloc[0])
    assert reallocated == pytest.approx(3000.0 * share_2050)


def test_historical_and_quarterly_rows_are_untouched() -> None:
    chart_rows, drift = _fixture_chart_rows_and_drift()
    extra = pd.DataFrame(
        [
            {
                "series_id": "light_ruc_net_km",
                "scenario_name": "",
                "june_year": 2024,
                "time_grain": "june_year",
                "row_type": "historical_actual",
                "value": 12000.0,
                "value_status": "",
                "data_scope": "",
            },
            {
                "series_id": "light_ruc_net_km",
                "scenario_name": "current_basecase",
                "june_year": 2050,
                "time_grain": "quarterly",
                "row_type": "current_forecast",
                "value": 3100.0,
                "value_status": "",
                "data_scope": "",
            },
        ]
    )
    combined = pd.concat([chart_rows, extra], ignore_index=True)
    adjusted, _ = apply_uptake_levers_to_chart_rows(combined, drift, EV_UPTAKE_PRESETS["MoT VFM fast"])
    actual_row = adjusted[adjusted["row_type"].eq("historical_actual")]
    quarterly_row = adjusted[adjusted["time_grain"].eq("quarterly")]
    assert float(actual_row["value"].iloc[0]) == 12000.0
    assert float(quarterly_row["value"].iloc[0]) == 3100.0

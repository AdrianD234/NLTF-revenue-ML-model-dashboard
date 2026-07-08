from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from model_dashboard.ev_uptake_levers import (
    EV_UPTAKE_PRESETS,
    UptakeLevers,
    apply_uptake_levers_to_chart_rows,
    lever_share_curves,
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
    aggressive = UptakeLevers(0.09, 2030.0, 0.99, 0.05, 0.03, 0.30, 0.01)
    curves = lever_share_curves(range(2025, 2051), aggressive)
    assert (curves["conventional"] >= 0.005 - 1e-9).all()


def test_vfm_presets_reproduce_official_scenarios() -> None:
    shares = pd.read_csv(VFM_SHARES)
    for preset_name, scenario in PRESET_TO_VFM_SCENARIO.items():
        official = shares[shares["scenario"].eq(scenario)].set_index("june_year")
        curves = lever_share_curves(official.index, EV_UPTAKE_PRESETS[preset_name]).set_index("june_year")
        bev_err = (curves["bev"] - official["light_ruc_bev_share"]).abs().max()
        phev_err = (curves["phev"] - official["light_ruc_phev_share"]).abs().max()
        assert bev_err < 0.016, f"{preset_name}: BEV share max error {bev_err:.4f}"
        assert phev_err < 0.016, f"{preset_name}: PHEV share max error {phev_err:.4f}"


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
    component_delta = sum(
        new[s] - old[s]
        for s in ["light_ruc_net_revenue", "light_bev_ruc_net_revenue", "phev_ruc_net_revenue"]
    )
    aggregate_delta = new["total_nltf_net_revenue"] - old["total_nltf_net_revenue"]
    assert abs(component_delta - aggregate_delta) < 1e-9
    assert set(sel_new["value_status"]) == {"lever_adjusted"}
    assert set(sel_new["data_scope"]) == {"ev_uptake_lever_overlay"}


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

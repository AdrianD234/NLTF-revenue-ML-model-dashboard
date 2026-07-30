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


def test_default_preset_tracks_mbu26_official_ped_share_retention() -> None:
    """The base preset doubles as the MBU26 official-shape anchor.

    MBU26's proportions are the VFM base scenario, so the 'MoT VFM base'
    preset must reproduce MBU26's petrol share-retention path (activity-only:
    intensity belongs to the Fleet efficiency sensitivity).
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
    retention = ped_retention_curve(target.index, EV_UPTAKE_PRESETS["MoT VFM base"])
    err = (retention - target).abs().max()
    assert err < 0.04, f"base preset vs MBU26 share-retention max error {err:.4f}"


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
                ("light_petrol_vkt", 32000.0),
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
    assert values["light_petrol_vkt"] == pytest.approx(32000.0 * retention_2050)
    assert values["ped_volume"] == pytest.approx(2800.0 * retention_2050)
    assert values["ped_vkt_per_capita"] == pytest.approx(1500.0 * retention_2050)
    assert values["gross_ped_revenue"] == pytest.approx(1960.0 * retention_2050)
    assert values["ped_volume"] / values["light_petrol_vkt"] == pytest.approx(
        2800.0 / 32000.0
    )
    # optimized-migration bridge already displaces petrol: gate must skip PED
    gated, gated_audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers, adjust_ped=False)
    gsel = gated[gated["scenario_name"].eq("current_basecase") & gated["june_year"].eq(2050)]
    gvalues = {row["series_id"]: row["value"] for _, row in gsel.iterrows()}
    assert gvalues["light_petrol_vkt"] == pytest.approx(32000.0)
    assert gvalues["ped_volume"] == pytest.approx(2800.0)
    assert set(gated_audit["ped_retention"]) == {1.0}


def test_heavy_split_moves_km_but_is_rollup_neutral() -> None:
    chart_rows, drift = _fixture_chart_rows_and_drift()
    levers = EV_UPTAKE_PRESETS["MoT VFM base"]
    # The heavy split is now an explicit sensitivity, Off by default: a LIGHT
    # composition choice must not reclassify Heavy RUC. Its mechanics are
    # unchanged, so the test asks for it directly.
    adjusted, audit = apply_uptake_levers_to_chart_rows(
        chart_rows, drift, levers, adjust_ped=False, heavy_bev_transition=True
    )
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


def _to_base_units(value: float, unit: str) -> float:
    text = str(unit).lower()
    if "million" in text:
        return float(value) * 1_000_000.0
    return float(value)


def _fy_periods(fy: int) -> set[str]:
    return {f"{fy - 1}Q3", f"{fy - 1}Q4", f"{fy}Q1", f"{fy}Q2"}


def test_default_uptake_reconciles_native_quarters_to_adjusted_annual_activity() -> None:
    chart = pd.read_parquet(ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.parquet")
    drift = pd.read_parquet(
        ROOT / "data" / "current_revenue_outlook" / "ev_phev_ped_light_drift_assumptions.parquet"
    )
    adjusted, _ = apply_uptake_levers_to_chart_rows(
        chart,
        drift,
        EV_UPTAKE_PRESETS["MoT VFM base"],
        adjust_ped=True,
        uptake_basis="MoT VFM base",
        repo_root=ROOT,
    )

    native_series = ("light_ruc_net_km", "heavy_ruc_net_km", "ped_vkt_per_capita")
    # FY2050 was inside the current horizon before the H20 policy. Quarterly
    # and annual availability are independent contracts now, so reconcile only
    # the June years that actually publish an annual result.
    def _published_fys(scenario: str) -> list[int]:
        # Quarter-to-annual reconciliation applies to the ECONOMETRIC years
        # only. The post-model extrapolation is annual by construction -
        # H21+ quarterly emission stays withheld - so its June years have no
        # quarters to reconcile against and requiring four would contradict
        # the horizon contract.
        selected = adjusted[
            adjusted["time_grain"].astype(str).eq("june_year")
            & adjusted["scenario_name"].astype(str).eq(scenario)
            & adjusted["series_id"].astype(str).eq("light_ruc_net_km")
        ]
        if "forecast_segment" in selected.columns:
            selected = selected[
                ~selected["forecast_segment"].fillna("").astype(str).eq("post_model_extrapolation")
            ]
        years = pd.to_numeric(selected["june_year"], errors="coerce").dropna()
        return sorted(int(value) for value in years.unique() if int(value) >= 2026)

    for scenario in ("current_basecase", "current_comparison_1"):
        published_fys = _published_fys(scenario)
        assert published_fys, f"{scenario} publishes no current annual result"
        for fy in published_fys:
            for series_id in native_series:
                annual = adjusted[
                    adjusted["scenario_name"].astype(str).eq(scenario)
                    & adjusted["series_id"].astype(str).eq(series_id)
                    & adjusted["time_grain"].astype(str).eq("june_year")
                    & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(fy)
                ]
                forecast_quarters = adjusted[
                    adjusted["scenario_name"].astype(str).eq(scenario)
                    & adjusted["series_id"].astype(str).eq(series_id)
                    & adjusted["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(fy)
                ]
                actual_quarters = adjusted[
                    adjusted["row_type"].astype(str).eq("historical_actual")
                    & adjusted["series_id"].astype(str).eq(series_id)
                    & adjusted["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(fy)
                ]
                quarters = pd.concat([actual_quarters, forecast_quarters], ignore_index=True)
                assert len(annual) == 1
                assert set(quarters["period"].astype(str)) == _fy_periods(fy)
                assert not quarters["period"].astype(str).duplicated().any()

                annual_total = _to_base_units(float(annual.iloc[0]["value"]), str(annual.iloc[0]["value_unit"]))
                quarterly_total = sum(
                    _to_base_units(float(row.value), str(row.value_unit)) for row in quarters.itertuples()
                )
                assert quarterly_total == pytest.approx(annual_total, rel=0.0, abs=1e-5)
                assert set(forecast_quarters["value_status"].astype(str)) == {
                    "lever_adjusted_quarterly_reconciled"
                }
                assert set(forecast_quarters["data_scope"].astype(str)) == {
                    "ev_uptake_quarterly_annual_reconciliation"
                }
                if series_id.endswith("ruc_net_km"):
                    assert set(quarters["value_unit"].astype(str)) == {"million km"}

    # For a complete forecast FY, the bridge changes only the level: the
    # original within-year shape remains exactly proportional.
    original = chart[
        chart["scenario_name"].astype(str).eq("current_basecase")
        & chart["series_id"].astype(str).eq("light_ruc_net_km")
        & chart["time_grain"].astype(str).eq("quarterly")
        & pd.to_numeric(chart["june_year"], errors="coerce").eq(2030)
    ].sort_values("period")
    rebased = adjusted[
        adjusted["scenario_name"].astype(str).eq("current_basecase")
        & adjusted["series_id"].astype(str).eq("light_ruc_net_km")
        & adjusted["time_grain"].astype(str).eq("quarterly")
        & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(2030)
    ].sort_values("period")
    original_share = pd.to_numeric(original["value"], errors="coerce").to_numpy(dtype=float)
    rebased_share = pd.to_numeric(rebased["value"], errors="coerce").to_numpy(dtype=float)
    np.testing.assert_allclose(
        rebased_share / rebased_share.sum(),
        original_share / original_share.sum(),
        rtol=1e-12,
        atol=1e-12,
    )

    # MBU26 remains a governed annual comparator; the current-scenario bridge
    # must not mutate any of its source rows.
    original_mbu = chart[chart["scenario_name"].astype(str).eq("mbu26_official")].reset_index(drop=True)
    adjusted_mbu = adjusted[adjusted["scenario_name"].astype(str).eq("mbu26_official")].reset_index(drop=True)
    pd.testing.assert_frame_equal(adjusted_mbu[original_mbu.columns], original_mbu, check_dtype=False)


def test_heavy_bev_transition_is_off_by_default_in_the_overlay() -> None:
    """A LIGHT composition choice must not reclassify Heavy RUC.

    Settled contract: HEAVY_RUC = not_reclassified. Heavy BEV is a fixed MBU26
    component of the current-finalist path, so the heavy split only runs when
    its own sensitivity is selected.
    """
    chart_rows, drift = _fixture_chart_rows_and_drift()
    levers = EV_UPTAKE_PRESETS["MoT VFM base"]
    adjusted, audit = apply_uptake_levers_to_chart_rows(chart_rows, drift, levers, adjust_ped=False)

    before = chart_rows[
        chart_rows["scenario_name"].eq("current_basecase") & chart_rows["june_year"].eq(2050)
    ].set_index("series_id")["value"]
    after = adjusted[
        adjusted["scenario_name"].eq("current_basecase") & adjusted["june_year"].eq(2050)
    ].set_index("series_id")["value"]
    for series_id in ("heavy_ruc_net_km", "heavy_ruc_net_revenue"):
        assert float(after[series_id]) == pytest.approx(float(before[series_id]), abs=1e-9)
    assert set(audit["heavy_bev_share"]) == {0.0}
    assert not audit["heavy_bev_transition_enabled"].any()

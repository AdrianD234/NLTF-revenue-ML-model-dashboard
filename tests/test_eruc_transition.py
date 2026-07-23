from __future__ import annotations

import pandas as pd
import pytest

from model_dashboard.eruc_transition import (
    ErucTransitionLevers,
    apply_eruc_transition_to_chart_rows,
    migrated_demand_factor,
    migration_share,
)


def test_migration_share_ramps_linearly_and_saturates() -> None:
    levers = ErucTransitionLevers(start_fy=2027, phase_in_years=3)
    assert migration_share(2026, levers) == 0.0
    assert migration_share(2027, levers) == pytest.approx(1 / 3)
    assert migration_share(2028, levers) == pytest.approx(2 / 3)
    assert migration_share(2029, levers) == 1.0
    assert migration_share(2050, levers) == 1.0


def test_demand_factor_responds_to_net_cost_change_with_correct_sign() -> None:
    levers = ErucTransitionLevers(vkt_elasticity=-0.15, pump_price_nzd_per_litre=2.70)
    # e-RUC cheaper than the removed excise -> running cost falls -> demand up
    cheap = migrated_demand_factor(levers, excise_per_litre=0.76, litres_per_100km=9.0, eruc_rate_per_km=0.03)
    assert cheap > 1.0
    # e-RUC dearer than the removed excise -> running cost rises -> demand down
    dear = migrated_demand_factor(levers, excise_per_litre=0.76, litres_per_100km=9.0, eruc_rate_per_km=0.12)
    assert dear < 1.0
    # zero elasticity -> no response either way
    flat = ErucTransitionLevers(vkt_elasticity=0.0)
    assert migrated_demand_factor(flat, excise_per_litre=0.76, litres_per_100km=9.0, eruc_rate_per_km=0.12) == 1.0


def _fixture(litres_per_100km: float = 9.0, excise: float = 0.76, light_rate: float = 0.09):
    drift = pd.DataFrame(
        [
            {
                "lambda_mode": "optimized",
                "scenario_name": "current_basecase",
                "FY": fy,
                "ped_rate": excise,
                "ped_litres_per_100km": litres_per_100km,
                "conventional_light_rate": light_rate,
            }
            for fy in (2027, 2030)
        ]
    )
    rows = []
    for fy in (2026, 2027, 2030):
        petrol_km = 30000.0
        for series_id, value in [
            ("ped_vkt_per_capita", 6000.0),
            ("ped_volume", petrol_km * litres_per_100km / 100.0),
            ("gross_ped_revenue", petrol_km * litres_per_100km / 100.0 * excise),
            ("light_ruc_net_km", 12000.0),
            ("light_ruc_net_revenue", 12000.0 * light_rate),
            ("gross_fed_revenue", 2300.0),
            ("total_nltf_net_revenue", 8000.0),
        ]:
            rows.append(
                {
                    "series_id": series_id,
                    "scenario_name": "current_basecase",
                    "june_year": fy,
                    "time_grain": "june_year",
                    "row_type": "future_forecast",
                    "value": value,
                    "value_status": "",
                    "data_scope": "",
                }
            )
    return pd.DataFrame(rows), drift


def test_revenue_neutral_when_eruc_rate_matches_excise_per_km_and_no_elasticity() -> None:
    litres_per_100km, excise = 9.0, 0.76
    excise_per_km = excise * litres_per_100km / 100.0
    chart, drift = _fixture(litres_per_100km, excise, light_rate=excise_per_km)
    levers = ErucTransitionLevers(start_fy=2027, phase_in_years=1, eruc_rate_ratio=1.0, vkt_elasticity=0.0)
    adjusted, audit = apply_eruc_transition_to_chart_rows(chart, drift, levers)
    for fy in (2027, 2030):
        sel_new = adjusted[adjusted["june_year"].eq(fy)].set_index("series_id")["value"]
        sel_old = chart[chart["june_year"].eq(fy)].set_index("series_id")["value"]
        assert sel_new["total_nltf_net_revenue"] == pytest.approx(sel_old["total_nltf_net_revenue"])
        # full migration: entire excise base moved onto e-RUC
        assert sel_new["gross_ped_revenue"] == pytest.approx(0.0)
        assert sel_new["light_ruc_net_km"] == pytest.approx(12000.0 + 30000.0)
    row = audit[audit["june_year"].eq(2027)].iloc[0]
    assert row["net_nltf_delta"] == pytest.approx(0.0)
    assert row["excise_c_per_km"] == pytest.approx(row["eruc_c_per_km"])


def test_partial_migration_moves_fed_to_ruc_and_cascades_consistently() -> None:
    chart, drift = _fixture()
    levers = ErucTransitionLevers(start_fy=2027, phase_in_years=3, vkt_elasticity=-0.15)
    adjusted, audit = apply_eruc_transition_to_chart_rows(chart, drift, levers)
    old = chart[chart["june_year"].eq(2027)].set_index("series_id")["value"]
    new = adjusted[adjusted["june_year"].eq(2027)].set_index("series_id")["value"]
    fed_delta = new["gross_ped_revenue"] - old["gross_ped_revenue"]
    ruc_gain = new["light_ruc_net_revenue"] - old["light_ruc_net_revenue"]
    assert fed_delta < 0 and ruc_gain > 0
    assert new["gross_fed_revenue"] - old["gross_fed_revenue"] == pytest.approx(fed_delta)
    assert new["total_nltf_net_revenue"] - old["total_nltf_net_revenue"] == pytest.approx(fed_delta + ruc_gain)
    # pre-transition years untouched
    before = adjusted[adjusted["june_year"].eq(2026)].set_index("series_id")["value"]
    assert before["gross_ped_revenue"] == pytest.approx(old["gross_ped_revenue"])
    # rows are tagged for audit
    tagged = adjusted[adjusted["june_year"].eq(2027)]
    assert set(tagged["value_status"]) == {"eruc_transition"}


def test_eruc_view_footprint_and_cascade_on_real_pack() -> None:
    from pathlib import Path

    import app
    from model_dashboard.revenue_outlook import (
        CURRENT_REVENUE_OUTLOOK_DIR,
        PED_BRIDGE_DEFAULT_MODE,
        load_revenue_outlook_pack,
        revenue_outlook_signature,
    )

    root = Path(__file__).resolve().parents[1]
    pack = load_revenue_outlook_pack(root / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=root)
    assert pack is not None
    sig = revenue_outlook_signature(root / CURRENT_REVENUE_OUTLOOK_DIR, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    skey = app.selected_sensitivity_key("Off", "Off", "Off")
    eruc = (2027.0, 3.0, 1.0, -0.15, 2.70)

    def view(series: str, key):
        v = app.cached_revenue_outlook_view(
            sig, series, "june_year", "Current planned path", traces, skey,
            PED_BRIDGE_DEFAULT_MODE, key, pack,
        )
        frame = v["filtered_rows"][["trace_name", "period", "value", "row_type"]].copy()
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        return frame.sort_values(["trace_name", "period"]).reset_index(drop=True), v

    key_off = (app.DEFAULT_EV_UPTAKE_MODE, ())
    key_on = (app.DEFAULT_EV_UPTAKE_MODE, (), eruc)

    # footprint: heavy RUC (untouched stream) must be identical under e-RUC
    heavy_off, _ = view("Heavy RUC net km", key_off)
    heavy_on, _ = view("Heavy RUC net km", key_on)
    pd.testing.assert_frame_equal(heavy_off, heavy_on)

    # actuals immutable on an affected series
    ped_off, _ = view("PED revenue", key_off)
    ped_on, v_on = view("PED revenue", key_on)
    act_off = ped_off[ped_off["row_type"].eq("historical_actual")]
    act_on = ped_on[ped_on["row_type"].eq("historical_actual")]
    pd.testing.assert_frame_equal(act_off.reset_index(drop=True), act_on.reset_index(drop=True))

    # Audit cascade: the raw e-RUC deltas compose with the downstream
    # PED/RUC policy replay factors before reaching the displayed NLTF total.
    audit = v_on["eruc_audit"]
    row = audit[audit["june_year"].eq(2031) & audit["scenario_name"].eq("current_basecase")].iloc[0]
    policy_audit = v_on["fed_uplift_audit"]
    policy_factors = policy_audit[
        policy_audit["june_year"].eq(2031)
        & policy_audit["scenario_name"].eq("current_basecase")
        & policy_audit["series_id"].isin(["gross_ped_revenue", "total_ruc_net_revenue"])
    ].set_index("series_id")["combined_model_and_rate_factor"]
    ped_factor = float(policy_factors.get("gross_ped_revenue", 1.0))
    ruc_factor = float(policy_factors.get("total_ruc_net_revenue", 1.0))
    expected_policy_composed_delta = (
        float(row["excise_revenue_delta"]) * ped_factor
        + float(row["eruc_revenue_gained"]) * ruc_factor
    )
    total_off, _ = view("Total NLTF revenue", key_off)
    total_on, _ = view("Total NLTF revenue", key_on)
    base_off = total_off[total_off["trace_name"].eq("Current finalist Base case") & total_off["period"].eq("FY2031")]["value"].iloc[0]
    base_on = total_on[total_on["trace_name"].eq("Current finalist Base case") & total_on["period"].eq("FY2031")]["value"].iloc[0]
    assert base_on - base_off == pytest.approx(expected_policy_composed_delta, rel=1e-9)


def test_vkt_per_capita_and_volume_follow_the_demand_response() -> None:
    chart, drift = _fixture()
    boost = ErucTransitionLevers(start_fy=2027, phase_in_years=1, eruc_rate_ratio=0.3, vkt_elasticity=-0.3)
    adjusted, audit = apply_eruc_transition_to_chart_rows(chart, drift, boost)
    row = audit[audit["june_year"].eq(2027)].iloc[0]
    assert row["migrated_demand_factor"] > 1.0
    old = chart[chart["june_year"].eq(2027)].set_index("series_id")["value"]
    new = adjusted[adjusted["june_year"].eq(2027)].set_index("series_id")["value"]
    assert new["ped_vkt_per_capita"] > old["ped_vkt_per_capita"]
    assert new["ped_volume"] > old["ped_volume"]
    # but the excise base is gone entirely under full migration
    assert new["gross_ped_revenue"] == pytest.approx(0.0)

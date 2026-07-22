"""Performance-cache architecture: staged caches must not change results.

The view pipeline (bridge -> sensitivity -> lever overlays -> filter/cone)
is cached at three grains: the sensitivity stage, the series-agnostic
scenario overlay rows, and the full view. These tests pin the equivalences
that make those caches safe and the warmer targets that keep first-touch
interactions warm.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.fuel_price_scenario import FUEL_PRICE_SCENARIO_NAME, FUEL_PRICE_SCENARIO_TRACE_NAME
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

ROOT = Path(__file__).resolve().parents[1]
FED = "Current planned path"
TRACES = ("Current finalist Base case", "Actual")


@pytest.fixture(scope="module")
def context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


def _default_keys():
    sens = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    uptake = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0)
    return sens, uptake


def test_view_returns_fresh_copies_across_calls(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    first = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    # Poison the returned frame; a second retrieval must be unaffected.
    first["filtered_rows"].loc[:, "value"] = -1.0
    second = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    assert not second["filtered_rows"]["value"].eq(-1.0).all()
    assert (pd.to_numeric(second["filtered_rows"]["value"], errors="coerce") > 0).any()


def test_overlay_rows_match_view_chart_rows(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    view = app.cached_revenue_outlook_view(
        signature, "Total NLTF revenue", "june_year", FED, TRACES, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    rows, _, _, _, _ = app.cached_scenario_overlay_rows(signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack)
    pd.testing.assert_frame_equal(view["chart_rows"].reset_index(drop=True), rows.reset_index(drop=True))


def test_policy_and_fuel_totals_reconcile_across_chart_line_and_stack(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    uptake = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)
    rows, _, _, _, fuel_audit = app.cached_scenario_overlay_rows(
        signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )
    line, _, stack, _ = app.cached_aligned_scenario_detail_frames(
        signature, sens, PED_BRIDGE_DEFAULT_MODE, uptake, pack
    )

    chart = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2027)
        & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
    ].set_index("scenario_name")["value"].map(float)
    line_total = line[
        pd.to_numeric(line["FY"], errors="coerce").eq(2027)
        & line["series_id"].astype(str).eq("total_nltf_net_revenue")
    ].set_index("scenario_name")["value"].map(float)
    stack_total = stack[
        pd.to_numeric(stack["FY"], errors="coerce").eq(2027)
        & stack["series_id"].astype(str).eq("total_nltf_net_revenue")
        & stack["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
    ].set_index("scenario_name")["value"].map(float)

    expected_scenarios = {
        "current_basecase",
        "current_comparison_1",
        "mbu26_official",
        "current_iran_war_fuel_15pct_ruc_20pct_6q",
    }
    assert expected_scenarios <= set(chart.index)
    assert not fuel_audit.empty
    for scenario in expected_scenarios:
        assert line_total.loc[scenario] == pytest.approx(chart.loc[scenario], abs=1e-9)
        assert stack_total.loc[scenario] == pytest.approx(chart.loc[scenario], abs=1e-9)


def test_current_and_mbu_policy_four_state_matrix_keeps_fuel_on_current_scope(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    states: dict[tuple[int, int], pd.DataFrame] = {}
    for current_off in (0, 1):
        for mbu_off in (0, 1):
            rows, _, _, _, _ = app.cached_scenario_overlay_rows(
                signature,
                sens,
                PED_BRIDGE_DEFAULT_MODE,
                (app.DEFAULT_EV_UPTAKE_MODE, (), (), current_off, mbu_off),
                pack,
            )
            states[(current_off, mbu_off)] = rows

    scenarios = {
        "base": "current_basecase",
        "high": "current_comparison_1",
        "fuel": "current_iran_war_fuel_15pct_ruc_20pct_6q",
        "mbu": "mbu26_official",
    }

    def total(state: tuple[int, int], scenario: str, fy: int) -> float:
        rows = states[state]
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["scenario_name"].astype(str).eq(scenario)
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        ]
        assert len(selected) == 1
        return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])

    # Moving only the MBU26 switch cannot alter any Current trace, including
    # the runtime Iran-war scenario cloned from Current Base after policy overlay.
    for current_off in (0, 1):
        for scenario in (scenarios["base"], scenarios["high"], scenarios["fuel"]):
            for fy in (2027, 2028):
                assert total((current_off, 0), scenario, fy) == pytest.approx(
                    total((current_off, 1), scenario, fy), abs=1e-9
                )

    # Moving only the Current switch cannot alter MBU26.
    for mbu_off in (0, 1):
        for fy in (2027, 2028):
            assert total((0, mbu_off), scenarios["mbu"], fy) == pytest.approx(
                total((1, mbu_off), scenarios["mbu"], fy), abs=1e-9
            )

    # Delayed and OFF are equal in FY2027 because both remove the original
    # 2027Q1-Q2 step. From FY2028, only OFF remains below the planned path.
    for mbu_off in (0, 1):
        for scenario in (scenarios["base"], scenarios["high"], scenarios["fuel"]):
            assert total((0, mbu_off), scenario, 2027) == pytest.approx(
                total((1, mbu_off), scenario, 2027), abs=1e-9
            )
            assert total((1, mbu_off), scenario, 2028) < total((0, mbu_off), scenario, 2028)
    for current_off in (0, 1):
        assert total((current_off, 0), scenarios["mbu"], 2027) == pytest.approx(
            total((current_off, 1), scenarios["mbu"], 2027), abs=1e-9
        )
        assert total((current_off, 1), scenarios["mbu"], 2028) < total(
            (current_off, 0), scenarios["mbu"], 2028
        )

    # Quarterly scenario timing stays correct under both Current 12c states:
    # no pre-shock leakage and exact reconciliation back to the selected
    # delayed/off annual path.
    for current_off in (0, 1):
        rows = states[(current_off, 0)]
        annual_pair = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["scenario_name"].astype(str).isin([scenarios["base"], scenarios["fuel"]])
            & pd.to_numeric(rows["june_year"], errors="coerce").isin([2026, 2027, 2028])
        ].copy()
        derived = {
            scenario: app._disaggregate_annual_rows_to_quarterly(
                annual_pair[annual_pair["scenario_name"].astype(str).eq(scenario)], rows
            )
            for scenario in (scenarios["base"], scenarios["fuel"])
        }
        base_quarters = derived[scenarios["base"]].set_index("period")["value"].map(float)
        iran_quarters = derived[scenarios["fuel"]].set_index("period")["value"].map(float)
        for period in ("2025Q3", "2025Q4"):
            assert iran_quarters.loc[period] == pytest.approx(base_quarters.loc[period], abs=1e-9)
        for scenario in (scenarios["base"], scenarios["fuel"]):
            annual_values = annual_pair[
                annual_pair["scenario_name"].astype(str).eq(scenario)
            ].set_index("june_year")["value"].map(float)
            quarterly_sums = derived[scenario].groupby("june_year")["value"].sum()
            for fy in (2026, 2027, 2028):
                assert float(quarterly_sums.loc[fy]) == pytest.approx(float(annual_values.loc[fy]), abs=1e-6)


def test_iran_war_default_display_checkpoints_and_quarter_timing(context) -> None:
    pack, signature = context
    sens, uptake = _default_keys()
    traces = ("Current finalist Base case", FUEL_PRICE_SCENARIO_TRACE_NAME)
    annual_view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        FED,
        traces,
        sens,
        PED_BRIDGE_DEFAULT_MODE,
        uptake,
        pack,
    )
    quarterly_view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "quarterly",
        FED,
        traces,
        sens,
        PED_BRIDGE_DEFAULT_MODE,
        uptake,
        pack,
    )
    annual = annual_view["filtered_rows"].pivot_table(
        index="june_year", columns="scenario_name", values="value", aggfunc="first"
    )
    expected = {
        2026: (4579.772378, 4484.197097),
        2027: (4743.873445, 4596.313769),
        2028: (5494.738904, 5518.450250),
    }
    for fy, (base_value, scenario_value) in expected.items():
        assert float(annual.at[fy, "current_basecase"]) == pytest.approx(base_value, abs=1e-6)
        assert float(annual.at[fy, FUEL_PRICE_SCENARIO_NAME]) == pytest.approx(scenario_value, abs=1e-6)
    assert annual.at[2026, FUEL_PRICE_SCENARIO_NAME] < annual.at[2026, "current_basecase"]
    assert annual.at[2027, FUEL_PRICE_SCENARIO_NAME] < annual.at[2027, "current_basecase"]
    assert annual.at[2028, FUEL_PRICE_SCENARIO_NAME] > annual.at[2028, "current_basecase"]

    assert quarterly_view["quarterly_disaggregated"] is True
    quarterly = quarterly_view["filtered_rows"].pivot_table(
        index="period", columns="scenario_name", values="value", aggfunc="first"
    )
    for period in ("2025Q3", "2025Q4"):
        assert float(quarterly.at[period, FUEL_PRICE_SCENARIO_NAME]) == pytest.approx(
            float(quarterly.at[period, "current_basecase"]), abs=1e-9
        )
    for period in ("2026Q1", "2026Q2", "2026Q3", "2026Q4", "2027Q1", "2027Q2"):
        assert float(quarterly.at[period, FUEL_PRICE_SCENARIO_NAME]) < float(
            quarterly.at[period, "current_basecase"]
        )
    for scenario_name in ("current_basecase", FUEL_PRICE_SCENARIO_NAME):
        sums = quarterly_view["filtered_rows"][
            quarterly_view["filtered_rows"]["scenario_name"].astype(str).eq(scenario_name)
            & pd.to_numeric(quarterly_view["filtered_rows"]["june_year"], errors="coerce").isin(expected)
        ].groupby("june_year")["value"].sum()
        for fy in expected:
            assert float(sums.loc[fy]) == pytest.approx(float(annual.at[fy, scenario_name]), abs=1e-6)


def test_cone_band_is_uptake_key_invariant(context) -> None:
    pack, signature = context
    sens, _ = _default_keys()
    bands = {}
    for mode in ("MoT VFM base", "MoT VFM fast"):
        view = app.cached_revenue_outlook_view(
            signature, "Total NLTF revenue", "june_year", FED, TRACES, sens,
            PED_BRIDGE_DEFAULT_MODE, (mode, (), (), 0), pack,
        )
        bands[mode] = view["cone_band"]
    pd.testing.assert_frame_equal(
        bands["MoT VFM base"].reset_index(drop=True),
        bands["MoT VFM fast"].reset_index(drop=True),
    )
    assert not bands["MoT VFM base"].empty


def test_warm_targets_cover_single_family_sensitivities() -> None:
    keys = app._revenue_outlook_warm_sensitivity_keys()
    assert len(keys) == 9
    assert all(len(key) == 11 for key in keys)
    assert app.selected_sensitivity_key("Med", "Off", "Off", freight_rail_shift="Off") in keys
    assert app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="High") in keys


def test_warmer_respects_disable_flag(monkeypatch) -> None:
    monkeypatch.setenv("REVENUE_OUTLOOK_CACHE_WARMER", "0")
    app._REVENUE_OUTLOOK_WARMER_STARTED.clear()
    app._start_revenue_outlook_cache_warmer()
    assert not app._REVENUE_OUTLOOK_WARMER_STARTED.is_set()

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

ROOT = Path(__file__).resolve().parents[1]
FED_PATH = "Current planned path"


@pytest.fixture(scope="module")
def comparison_context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


def _keys(fleet="Off", freight="Off", uptake=None, eruc=(), fed_on=True):
    sensitivity = app.selected_sensitivity_key(fleet, "Off", "Off", freight_rail_shift=freight)
    uptake_key = (uptake or app.DEFAULT_EV_UPTAKE_MODE, (), eruc, 0 if fed_on else 1)
    return sensitivity, uptake_key


def _paths(comparison_context, series, keys_a, keys_b):
    pack, signature = comparison_context
    return app.cached_scenario_comparison_paths(
        signature, series, FED_PATH,
        keys_a[0], keys_a[1], keys_b[0], keys_b[1],
        PED_BRIDGE_DEFAULT_MODE, pack,
    )


def test_identical_scenarios_give_identical_paths(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys())
    pd.testing.assert_series_equal(result["a"], result["b"])
    assert result["metric_type"] == "revenue"
    assert not result["history"].empty


def test_fleet_efficiency_high_lowers_revenue_npv(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fleet="High"))
    npv_a = app.npv_to_horizon(result["a"])
    npv_b = app.npv_to_horizon(result["b"])
    assert npv_b < npv_a


def test_fed_uplift_off_lowers_scenario_b_from_fy2027(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fed_on=False))
    a, b = result["a"], result["b"]
    assert b.loc[2026] == pytest.approx(a.loc[2026])
    for fy in (2027, 2031, 2040):
        assert b.loc[fy] < a.loc[fy]


def test_revenue_cards_use_npv_language_and_activity_cards_do_not(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fleet="High"))
    revenue_cards = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", result["a"], result["b"], result["value_unit"], None
    )
    revenue_text = " ".join(str(part) for card in revenue_cards for part in card)
    assert "NPV to FY2050" in revenue_text
    assert "Cumulative nominal delta" in revenue_text

    activity = _paths(comparison_context, "Light RUC net km", _keys(), _keys(uptake="MoT VFM fast"))
    activity_cards = app._scenario_comparison_cards(
        "Light RUC net km", activity["metric_type"], activity["a"], activity["b"], activity["value_unit"], None
    )
    activity_text = " ".join(str(part) for card in activity_cards for part in card)
    assert "NPV" not in activity_text
    assert "discount" not in activity_text.lower()
    assert "Cumulative" in activity_text


def test_vkt_per_capita_uses_intensity_card_variant(comparison_context) -> None:
    result = _paths(comparison_context, "PED VKT per capita", _keys(), _keys(uptake="MoT VFM fast"))
    cards = app._scenario_comparison_cards(
        "PED VKT per capita", result["metric_type"], result["a"], result["b"], result["value_unit"], None
    )
    text = " ".join(str(part) for card in cards for part in card)
    assert "average annual level" in text.lower()
    assert "FY2050 delta" in text
    assert "NPV" not in text


def test_mot_official_scenario_plots_the_mbu26_official_trace(comparison_context) -> None:
    pack, _ = comparison_context
    governed_keys = _keys(uptake=app.EV_UPTAKE_GOVERNED_OPTION)
    result = _paths(comparison_context, "Total NLTF revenue", governed_keys, governed_keys)
    assert not result["a"].empty
    assert result["metric_type"] == "revenue"
    pd.testing.assert_series_equal(result["a"], result["b"])
    # It must be the MBU26 official trace itself - NOT the finalist base case
    # with lever overlays switched off (the raw petrol bridge keeps all petrol
    # activity to 2050, which is exactly what the displacement lever corrects).
    rows = pack.revenue_chart_rows
    label_col = "series_label" if "series_label" in rows.columns else "stream_label"
    mbu = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows[label_col].astype(str).eq("Total NLTF revenue")
        & rows["trace_name"].astype(str).eq("MBU26 official")
    ]
    expected = pd.Series(
        pd.to_numeric(mbu["value"], errors="coerce").to_numpy(),
        index=pd.to_numeric(mbu["june_year"], errors="coerce").to_numpy(),
    ).dropna().sort_index()
    pd.testing.assert_series_equal(result["a"], expected, check_index_type=False)
    # And it differs from the VFM base preset overlay path.
    vs_base = _paths(comparison_context, "Total NLTF revenue", governed_keys, _keys())
    assert not vs_base["a"].equals(vs_base["b"])


def test_delta_tone_flips_with_sign() -> None:
    up = pd.Series([100.0, 100.0], index=[2026, 2027])
    down = pd.Series([90.0, 90.0], index=[2026, 2027])
    cards_negative = app._scenario_comparison_cards("Total NLTF revenue", "revenue", up, down, "$m nominal ex GST", None)
    cards_positive = app._scenario_comparison_cards("Total NLTF revenue", "revenue", down, up, "$m nominal ex GST", None)
    assert cards_negative[2][4] == "bad"
    assert cards_positive[2][4] == "good"


def test_npv_waterfall_bridges_a_to_b() -> None:
    figure = app._scenario_npv_waterfall_figure(1000.0, 900.0, "$m nominal ex GST")
    trace = figure.data[0]
    values = list(trace.y)
    assert values[0] + values[1] == pytest.approx(values[2])
    assert list(trace.measure) == ["absolute", "relative", "total"]


def _component_breakdown(comparison_context, keys_a, keys_b, rate=None):
    total = _paths(comparison_context, "Total NLTF revenue", keys_a, keys_b)
    npv_a = app.npv_to_horizon(total["a"], rate=rate)
    npv_b = app.npv_to_horizon(total["b"], rate=rate)
    component_npvs = {
        series: app._scenario_component_npv(
            _paths(comparison_context, series, keys_a, keys_b), rate
        )
        for series in app._SCENARIO_COMPONENT_FETCH_SERIES
    }
    return app._scenario_npv_component_breakdown(component_npvs, npv_a, npv_b), npv_a, npv_b


def test_component_breakdown_closes_total_npv_exactly(comparison_context) -> None:
    components, npv_a, npv_b = _component_breakdown(
        comparison_context, _keys(), _keys(uptake="MoT VFM fast")
    )
    assert sum(a for _, a, _ in components) == pytest.approx(npv_a, abs=1e-6)
    assert sum(b for _, _, b in components) == pytest.approx(npv_b, abs=1e-6)
    delta_sum = sum(b - a for _, a, b in components)
    assert delta_sum == pytest.approx(npv_b - npv_a, abs=1e-6)


def test_uptake_delta_stays_out_of_heavy_and_mvr(comparison_context) -> None:
    # Heavy BEV reallocation is rollup-neutral, so a pure light-uptake change
    # must leave the heavy block and MVR untouched in the bridge.
    components, _, _ = _component_breakdown(
        comparison_context, _keys(), _keys(uptake="MoT VFM fast")
    )
    by_label = {label: b - a for label, a, b in components}
    assert abs(by_label["Heavy & other RUC"]) < 1.0
    assert by_label["Net MVR"] == pytest.approx(0.0, abs=1e-9)
    assert by_label["PED / FED (net)"] < 0
    assert by_label["Light RUC (conventional)"] < 0
    assert by_label["Light BEV RUC"] > 0


def test_freight_shift_lands_in_heavy_component(comparison_context) -> None:
    components, npv_a, npv_b = _component_breakdown(
        comparison_context, _keys(), _keys(freight="High")
    )
    by_label = {label: b - a for label, a, b in components}
    assert by_label["Heavy & other RUC"] == pytest.approx(npv_b - npv_a, abs=1e-6)
    assert by_label["PED / FED (net)"] == pytest.approx(0.0, abs=1e-9)
    assert by_label["Light RUC (conventional)"] == pytest.approx(0.0, abs=1e-9)


def test_component_bridge_figure_accumulates_to_total_delta() -> None:
    components = [
        ("PED / FED (net)", 40000.0, 38000.0),
        ("Light RUC (conventional)", 22000.0, 21000.0),
        ("Light BEV RUC", 39000.0, 41500.0),
        ("Net MVR", 9000.0, 9000.0),  # immaterial delta, must be dropped
    ]
    npv_a = sum(a for _, a, _ in components)
    npv_b = sum(b for _, _, b in components)
    figure = app._scenario_npv_component_bridge_figure(npv_a, npv_b, components, "$m nominal ex GST")
    trace = figure.data[0]
    measures = list(trace.measure)
    assert measures == ["relative", "relative", "relative", "total"]
    assert "Net MVR" not in list(trace.x)
    assert sum(list(trace.y)[:-1]) == pytest.approx((npv_b - npv_a) / 1000.0)


def test_comparison_hovers_carry_units() -> None:
    # A bare "-3.61" hover is meaningless; currency charts hover in $b.
    components = [("PED / FED (net)", 40000.0, 38000.0)]
    currency = "$m nominal ex GST"
    bridge = app._scenario_npv_component_bridge_figure(80000.0, 78000.0, components, currency)
    composition = app._scenario_npv_composition_figure(components, currency)
    simple = app._scenario_npv_waterfall_figure(1000.0, 900.0, currency)
    for figure in (bridge, composition, simple):
        assert "%{y:$,.2f}b" in str(figure.data[0].hovertemplate)

    paths = app._scenario_comparison_figure(
        pd.Series(dtype=float),
        pd.Series([100.0], index=[2026]),
        pd.Series([90.0], index=[2026]),
        "million km",
    )
    assert "million km" in str(paths.data[0].hovertemplate)


def test_composition_figure_stacks_sum_to_totals() -> None:
    components = [
        ("PED / FED (net)", 40000.0, 38000.0),
        ("Heavy & other RUC", 39000.0, 39000.0),
        ("TUC & other", 350.0, 350.0),
    ]
    figure = app._scenario_npv_composition_figure(components, "$m nominal ex GST")
    stack_a = sum(trace.y[0] for trace in figure.data)
    stack_b = sum(trace.y[1] for trace in figure.data)
    assert stack_a == pytest.approx(sum(a for _, a, _ in components) / 1000.0)
    assert stack_b == pytest.approx(sum(b for _, _, b in components) / 1000.0)
    assert figure.layout.barmode == "stack"

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

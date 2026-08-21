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


def _keys(
    fleet="Off",
    freight="Off",
    uptake=None,
    eruc=(),
    fed_on=True,
    mbu_fed_on=True,
    vintage=None,
):
    """Build a (sensitivity, uptake) key pair.

    ``vintage`` selects the official comparator vintage (uptake-key slot 6,
    with the overlay flag in slot 7). Passing it is required for assertions
    about a NON-default vintage such as MBU26, whose rows the view layer
    filters out while BEFU26 is the selected comparator.
    """
    sensitivity = app.selected_sensitivity_key(fleet, "Off", "Off", freight_rail_shift=freight)
    uptake_key = (uptake or app.DEFAULT_EV_UPTAKE_MODE, (), eruc, 0 if fed_on else 1, 0 if mbu_fed_on else 1)
    if vintage is not None:
        uptake_key = (*uptake_key, False, str(vintage), False)
    return sensitivity, uptake_key


def _paths(comparison_context, series, keys_a, keys_b):
    pack, signature = comparison_context
    return app.cached_scenario_comparison_paths(
        signature, series, FED_PATH,
        keys_a[0], keys_a[1], keys_b[0], keys_b[1],
        PED_BRIDGE_DEFAULT_MODE, pack,
    )


def _scenario_rows(comparison_context, keys):
    """Raw overlay rows for one scenario key, for series-level assertions."""
    pack, signature = comparison_context
    rows, *_ = app.cached_scenario_overlay_rows(
        signature, keys[0], PED_BRIDGE_DEFAULT_MODE, keys[1], pack
    )
    return rows


def _annual(rows, series_id: str, fy: int, role: str = "basecase") -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series_id)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


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


def test_fed_uplift_off_matches_delayed_fy2027_then_lowers_path(comparison_context) -> None:
    # BEFU26 selected explicitly: this test asserts FY2026 behaviour, and the
    # default PREBU26 comparator masks the Current FY2026 point (its actuals
    # run through FY2026), so the FY2026 assertion needs the BEFU26 seam.
    result = _paths(
        comparison_context,
        "Total NLTF revenue",
        _keys(vintage="BEFU26"),
        _keys(fed_on=False, vintage="BEFU26"),
    )
    a, b = result["a"], result["b"]
    assert b.loc[2026] == pytest.approx(a.loc[2026])
    assert b.loc[2027] == pytest.approx(a.loc[2027])
    # FY2031 and FY2040 were current June years before the H20 policy. The
    # no-uplift path is lower for every year that publishes, so assert the
    # property over the published index rather than pinned far years.
    later = [fy for fy in a.index if int(fy) >= 2028]
    assert later, "no June year past the legislated step publishes"
    for fy in later:
        assert b.loc[fy] < a.loc[fy], f"no-uplift is not below published in FY{fy}"


def test_current_and_mbu26_uplift_switches_are_independent(comparison_context) -> None:
    current_on = _keys()
    current_mbu_switch_off = _keys(mbu_fed_on=False)
    current_result = _paths(comparison_context, "Total NLTF revenue", current_on, current_mbu_switch_off)
    pd.testing.assert_series_equal(current_result["a"], current_result["b"])

    # The synthetic rate-only counterfactual is defined for MBU26 only, so
    # these legs explicitly select the MBU26 comparator vintage.
    mbu_on = _keys(uptake=app.EV_UPTAKE_GOVERNED_OPTION, vintage="MBU26")
    mbu_current_switch_off = _keys(
        uptake=app.EV_UPTAKE_GOVERNED_OPTION, fed_on=False, vintage="MBU26"
    )
    mbu_result = _paths(comparison_context, "Total NLTF revenue", mbu_on, mbu_current_switch_off)
    pd.testing.assert_series_equal(mbu_result["a"], mbu_result["b"])

    mbu_off = _keys(uptake=app.EV_UPTAKE_GOVERNED_OPTION, mbu_fed_on=False, vintage="MBU26")
    toggled = _paths(comparison_context, "Total NLTF revenue", mbu_on, mbu_off)
    # Source-derived official no-uplift, not the current-model factor map.
    # Evidence: artifacts/p0_light_fleet_fix/official_policy_audit.csv,
    # FY2030 no_uplift total_nltf_net_revenue.
    assert toggled["b"].loc[2030] == pytest.approx(5663.618433259718, rel=1e-12)
    assert toggled["b"].loc[2030] < toggled["a"].loc[2030]

    # The governed proportional policy reprices RUC alongside PED/FED. Both
    # component paths must move, and together they must explain the total.
    fed_toggled = _paths(comparison_context, "Net FED revenue", mbu_on, mbu_off)
    ruc_toggled = _paths(comparison_context, "Total RUC all classes", mbu_on, mbu_off)
    assert fed_toggled["b"].loc[2030] < fed_toggled["a"].loc[2030]
    assert ruc_toggled["b"].loc[2030] < ruc_toggled["a"].loc[2030]
    assert toggled["b"].loc[2030] - toggled["a"].loc[2030] == pytest.approx(
        (fed_toggled["b"].loc[2030] - fed_toggled["a"].loc[2030])
        + (ruc_toggled["b"].loc[2030] - ruc_toggled["a"].loc[2030]),
        abs=1e-9,
    )


def test_revenue_cards_use_npv_language_and_activity_cards_do_not(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fleet="High"))
    revenue_cards = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", result["a"], result["b"], result["value_unit"], None
    )
    revenue_text = " ".join(str(part) for card in revenue_cards for part in card)
    assert "Cumulative nominal to FY2050" in revenue_text
    assert "Cumulative nominal delta" in revenue_text
    assert "NPV delta" in revenue_text
    # nominal level cards lead; the discounted delta card comes last
    assert revenue_cards[2][0].startswith("Cumulative nominal delta")
    assert revenue_cards[3][0].startswith("NPV delta")

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
    # Explicitly select MBU26: the A/B "MoT official" option follows the page's
    # selected comparator vintage, and BEFU26 is the default.
    governed_keys = _keys(uptake=app.EV_UPTAKE_GOVERNED_OPTION, vintage="MBU26")
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
    # The comparison reads the canonical final view, which applies the FY2050
    # presentation horizon once for every decision-facing row; the raw pack
    # trace runs to FY2055, so the expectation is clipped to the same horizon.
    expected = expected[expected.index <= 2050]
    pd.testing.assert_series_equal(
        result["a"].drop(index=2027),
        expected.drop(index=2027),
        check_index_type=False,
    )
    # Source-derived official delayed wedge (0.059969 NZD/L, direct_source),
    # replacing 4649.868613 which came from the current-model factor map.
    # Evidence: official_policy_audit.csv FY2027 delay_6m.
    assert result["a"].loc[2027] == pytest.approx(4647.671040768058, rel=1e-12)
    assert result["a"].loc[2027] < expected.loc[2027]
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


def test_uptake_delta_stays_out_of_heavy_ped_and_mvr(comparison_context) -> None:
    """A light-uptake change reallocates the Light pool and nothing else.

    Two expectations here are obsolete. PED used to fall because the retired
    lambda transfer coupled uptake to petrol displacement; lambda is gone and
    the VFM petrol-retention overlay is Off by default, so PED is now exactly
    unchanged. Heavy used to drift within a 1.0 tolerance because the heavy BEV
    curve rode along with the light selector; that is now Off by default, so
    Heavy is exactly unchanged rather than approximately so.
    """
    components, _, _ = _component_breakdown(
        comparison_context, _keys(), _keys(uptake="MoT VFM fast")
    )
    by_label = {label: b - a for label, a, b in components}

    assert by_label["Net MVR"] == pytest.approx(0.0, abs=1e-9)
    assert by_label["PED / FED (net)"] == pytest.approx(0.0, abs=1e-9)

    # The reallocation itself still happens, inside the Light classes.
    assert by_label["Light RUC (conventional)"] < 0
    assert by_label["Light BEV RUC"] > 0

    # "Heavy & other RUC" is the RUC rollup LESS the light classes, so it is
    # not a pure Heavy line. In the policy year the rollup carries a
    # second-order policy-by-composition term: the delayed policy reprices each
    # leaf proportionally, and the light classes carry different effective
    # per-km rates, so changing the mix changes what the policy acts on. Both
    # scenarios stay internally consistent (formula residuals ~1e-12), so this
    # is not an identity break, and it sits far below the chart's own
    # materiality floor.
    assert abs(by_label["Heavy & other RUC"]) < app._SCENARIO_COMPONENT_MATERIALITY

    # The contract that actually matters is asserted directly on the series:
    # a light uptake choice must not move Heavy RUC at all.
    base_rows = _scenario_rows(comparison_context, _keys())
    fast_rows = _scenario_rows(comparison_context, _keys(uptake="MoT VFM fast"))
    for series_id in ("heavy_ruc_net_km", "heavy_ruc_net_revenue"):
        for fy in (2026, 2027, 2030):
            assert _annual(fast_rows, series_id, fy) == pytest.approx(
                _annual(base_rows, series_id, fy), abs=1e-9
            ), f"light uptake moved {series_id} in FY{fy}"


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
    simple = app._scenario_npv_waterfall_figure(1000.0, 900.0, currency)
    for figure in (bridge, simple):
        assert "%{y:$,.2f}b" in str(figure.data[0].hovertemplate)
    # the by-stream chart is horizontal, so the value lives on the x axis
    composition = app._scenario_npv_composition_figure(components, currency)
    assert "%{x:$,.2f}b" in str(composition.data[0].hovertemplate)

    paths = app._scenario_comparison_figure(
        pd.Series(dtype=float),
        pd.Series([100.0], index=[2026]),
        pd.Series([90.0], index=[2026]),
        "million km",
    )
    assert "million km" in str(paths.data[0].hovertemplate)


# ===================== single-engine parity: the comparison page is a thin
# consumer of the SAME canonical final view the Single scenario chart plots.
# These tests pin that contract: a comparison side must equal the equivalent
# Single scenario final path exactly, for every governed trace/policy pairing.

BASE_TRACE = "Current finalist Base case"
HIGH_TRACE = "Current finalist High population/comparison"


def _typed_keys(policy=None, fleet="Off", vintage=None):
    """A (sensitivity, typed uptake) pair like the production page builds."""
    sensitivity = app.selected_sensitivity_key(fleet, "Off", "Off", freight_rail_shift="Off")
    uptake = app.RevenueScenarioComputationKey(
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=policy or app.FED_POLICY_PUBLISHED,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id=vintage,
    )
    return sensitivity, uptake


def _comparison(comparison_context, series, keys_a, keys_b, trace_a, trace_b):
    pack, signature = comparison_context
    return app.cached_scenario_comparison_paths(
        signature, series, FED_PATH,
        keys_a[0], keys_a[1], keys_b[0], keys_b[1],
        PED_BRIDGE_DEFAULT_MODE, pack,
        trace_a=trace_a, trace_b=trace_b,
    )


def _single_view_forecast(comparison_context, series, keys, trace):
    """The final path exactly as the Single scenario view would plot it."""
    pack, signature = comparison_context
    view = app.cached_revenue_outlook_view(
        signature, series, "june_year", FED_PATH, ("Actual", trace),
        keys[0], PED_BRIDGE_DEFAULT_MODE, keys[1], pack,
    )
    rows = view["filtered_rows"]
    fy = pd.to_numeric(rows["june_year"], errors="coerce")
    values = pd.to_numeric(rows["value"], errors="coerce")
    is_actual = rows["row_type"].astype(str).eq("historical_actual")
    is_trace = rows["trace_name"].astype(str).eq(trace)
    selected = is_trace & ~is_actual
    return (
        pd.Series(values[selected].to_numpy(), index=fy[selected].to_numpy())
        .dropna()
        .sort_index()
    )


@pytest.mark.parametrize(
    "trace,policy",
    [
        (BASE_TRACE, app.FED_POLICY_PUBLISHED),
        (BASE_TRACE, app.FED_POLICY_DELAYED_6M),
        (BASE_TRACE, app.FED_POLICY_OFF),
        (HIGH_TRACE, app.FED_POLICY_DELAYED_6M),
        (app.CONFLICT_TRACE_NAMES[len(app.CONFLICT_TRACE_NAMES) // 2], app.FED_POLICY_DELAYED_6M),
    ],
)
def test_comparison_side_equals_the_single_scenario_final_path(
    comparison_context, trace, policy
) -> None:
    keys = _typed_keys(policy=policy)
    result = _comparison(
        comparison_context, "Total NLTF revenue", keys, keys, trace, trace
    )
    expected = _single_view_forecast(comparison_context, "Total NLTF revenue", keys, trace)
    assert not expected.empty
    pd.testing.assert_series_equal(result["a"], expected)
    pd.testing.assert_series_equal(result["b"], expected)


def test_identical_a_and_b_yield_zero_delta_cards(comparison_context) -> None:
    keys = _typed_keys(policy=app.FED_POLICY_DELAYED_6M)
    result = _comparison(
        comparison_context, "Total NLTF revenue", keys, keys, BASE_TRACE, BASE_TRACE
    )
    pd.testing.assert_series_equal(result["a"], result["b"])
    cards = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", result["a"], result["b"], result["value_unit"], None
    )
    assert cards[2][1] == "+$0m"
    assert cards[3][1] == "+$0m"
    assert cards[2][4] == "mixed"
    assert cards[3][4] == "mixed"


def test_changing_b_leaves_a_exactly_unchanged(comparison_context) -> None:
    keys_a = _typed_keys(policy=app.FED_POLICY_DELAYED_6M)
    first = _comparison(
        comparison_context, "Total NLTF revenue",
        keys_a, _typed_keys(policy=app.FED_POLICY_DELAYED_6M, fleet="High"),
        BASE_TRACE, HIGH_TRACE,
    )
    second = _comparison(
        comparison_context, "Total NLTF revenue",
        keys_a, _typed_keys(policy=app.FED_POLICY_OFF),
        BASE_TRACE, BASE_TRACE,
    )
    pd.testing.assert_series_equal(first["a"], second["a"])


def test_a_and_b_share_the_fy2026_fy2050_horizon(comparison_context) -> None:
    # Under BEFU26 (actuals to FY2025) the comparison window is FY2026-FY2050.
    keys = _typed_keys(policy=app.FED_POLICY_DELAYED_6M, vintage="BEFU26")
    result = _comparison(
        comparison_context, "Total NLTF revenue", keys, keys, BASE_TRACE, HIGH_TRACE
    )
    for side in ("a", "b"):
        years = sorted(int(year) for year in result[side].index if int(year) >= 2026)
        assert years == list(range(2026, 2051)), side
    assert app._comparison_alignment_gate(result["a"], result["b"]) == ""


def test_a_and_b_share_the_seam_derived_horizon_under_prebu26(comparison_context) -> None:
    """PREBU26 publishes FY2026 as actual, so the shared window is FY2027+."""
    keys = _typed_keys(policy=app.FED_POLICY_DELAYED_6M)
    result = _comparison(
        comparison_context, "Total NLTF revenue", keys, keys, BASE_TRACE, HIGH_TRACE
    )
    for side in ("a", "b"):
        years = sorted(int(year) for year in result[side].index if int(year) >= 2026)
        assert years == list(range(2027, 2051)), side
    start = app._comparison_horizon_start_fy(keys[1])
    assert start == 2027
    assert app._comparison_alignment_gate(result["a"], result["b"], horizon_start_fy=start) == ""


def test_alignment_gate_blocks_mismatched_horizons() -> None:
    full = pd.Series(1.0, index=list(range(2026, 2051)))
    short = pd.Series(1.0, index=list(range(2026, 2031)))
    assert app._comparison_alignment_gate(full, full.copy()) == ""
    message = app._comparison_alignment_gate(full, short)
    assert "suppressed" in message
    assert app._comparison_alignment_gate(full, pd.Series(dtype=float)) != ""


_PAGE_KEY_FIELDS = dict(
    engine="engine-x",
    uptake_basis=None,  # filled per test
    current_fed_policy_state=None,
    official_fed_policy_state=None,
    ped_retention_sensitivity=True,
    official_comparator_vintage_id="BEFU26",
    official_comparator_overlay=True,
    ped_bridge_mode="mode-y",
    bridge_vintage_id="H25",
    long_run_shape_vintage_id="shape-z",
    long_run_transition_schedule_id="sched-w",
)


def _page_key():
    fields = dict(_PAGE_KEY_FIELDS)
    fields["uptake_basis"] = app.DEFAULT_EV_UPTAKE_MODE
    fields["current_fed_policy_state"] = app.FED_POLICY_DELAYED_6M
    fields["official_fed_policy_state"] = app.FED_POLICY_PUBLISHED
    return app.RevenueScenarioComputationKey(**fields)


def test_scenario_b_key_clones_the_page_key_and_overrides_only_its_controls() -> None:
    page_sens = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    page_key = _page_key()
    sens_b, key_b = app._comparison_scenario_b_keys(
        page_sens, page_key,
        fleet="High", pt_shift="Off", freight="Off",
        eruc_values=(), fed_policy_state=app.FED_POLICY_OFF,
    )
    assert sens_b[0] == "High"
    assert key_b.current_fed_policy_state == app.FED_POLICY_OFF
    # Every field the B column does not expose inherits from the page key -
    # this is exactly the drift the old fresh-key construction allowed.
    for field, value in [
        ("engine", "engine-x"),
        ("ped_bridge_mode", "mode-y"),
        ("bridge_vintage_id", "H25"),
        ("long_run_shape_vintage_id", "shape-z"),
        ("long_run_transition_schedule_id", "sched-w"),
        ("official_comparator_vintage_id", "BEFU26"),
        ("official_comparator_overlay", True),
        ("ped_retention_sensitivity", True),
    ]:
        assert getattr(key_b, field) == value, field
    # Identical controls reproduce the page key exactly, so "B configured
    # like A" is byte-identical by construction.
    sens_same, key_same = app._comparison_scenario_b_keys(
        page_sens, page_key,
        fleet="Off", pt_shift="Off", freight="Off",
        eruc_values=(), fed_policy_state=app.FED_POLICY_DELAYED_6M,
    )
    assert sens_same == page_sens
    assert key_same == page_key


def test_official_comparator_keys_inherit_the_page_identity() -> None:
    sens, key, trace = app._comparison_official_scenario_keys(
        _page_key(),
        official_policy_state=app.FED_POLICY_PUBLISHED,
        selected_vid="MBU26",
    )
    assert key.uptake_basis == app.EV_UPTAKE_GOVERNED_OPTION
    assert key.current_fed_policy_state == app.FED_POLICY_PUBLISHED
    assert key.official_comparator_vintage_id == "MBU26"
    assert key.custom_ev_levers == () and key.eruc_levers == ()
    # Identity fields still come from the page, not module defaults.
    assert key.engine == "engine-x"
    assert key.bridge_vintage_id == "H25"
    assert key.long_run_transition_schedule_id == "sched-w"
    assert sens == app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    assert trace == app.official_comparator_trace_name("MBU26")


# ===================== comparison window: a presentation-side June-year
# filter applied to already-computed annual rows before aggregation. The
# window is deliberately NOT part of any scenario or cache identity.


def test_window_bounds_derive_from_the_common_horizon() -> None:
    full = pd.Series(1.0, index=list(range(2025, 2051)))  # FY2025 nowcast anchor included
    short = pd.Series(1.0, index=list(range(2026, 2041)))
    assert app._comparison_fy_window_bounds(full, full) == (2026, 2050)
    assert app._comparison_fy_window_bounds(full, short) == (2026, 2040)
    assert app._comparison_fy_window_bounds(full, pd.Series(dtype=float)) is None
    # The selected vintage's presentation seam floors the offered range, so
    # under PREBU26 (actuals through FY2026) the window starts at FY2027.
    assert app._comparison_fy_window_bounds(full, full, start_floor_fy=2027) == (2027, 2050)
    assert app._comparison_fy_window_bounds(full, short, start_floor_fy=2027) == (2027, 2040)


def test_window_clamp_never_raises() -> None:
    bounds = (2026, 2050)
    assert app._clamp_comparison_fy_window((2030, 2040), bounds) == (2030, 2040)
    assert app._clamp_comparison_fy_window((1990, 2100), bounds) == (2026, 2050)
    assert app._clamp_comparison_fy_window((2040, 2030), bounds) == (2030, 2040)
    assert app._clamp_comparison_fy_window((2035, 2035), bounds) == (2035, 2035)
    # a window with no overlap at all falls back to the full range
    assert app._clamp_comparison_fy_window((2051, 2060), bounds) == (2026, 2050)
    assert app._clamp_comparison_fy_window((1990, 2000), bounds) == (2026, 2050)
    # malformed persisted state is repaired, never fatal
    assert app._clamp_comparison_fy_window(None, bounds) == (2026, 2050)
    assert app._clamp_comparison_fy_window("junk", bounds) == (2026, 2050)
    assert app._clamp_comparison_fy_window((), bounds) == (2026, 2050)
    # a shrunken horizon (e.g. a future presentation seam moving the first
    # forecast year) clamps the old full-range selection into the new bounds
    assert app._clamp_comparison_fy_window((2026, 2050), (2027, 2050)) == (2027, 2050)


def test_full_default_window_reproduces_the_previous_totals_exactly(comparison_context) -> None:
    keys_a, keys_b = _keys(), _keys(fleet="High")
    result = _paths(comparison_context, "Total NLTF revenue", keys_a, keys_b)
    a, b = result["a"], result["b"]
    # The default comparator is PREBU26: its actuals run through FY2026, so
    # the forecast window proper - and therefore the full default window -
    # begins FY2027.
    seam_fy = app._comparison_horizon_start_fy(keys_a[1])
    assert seam_fy == 2027
    bounds = app._comparison_fy_window_bounds(a, b, start_floor_fy=seam_fy)
    assert bounds == (2027, 2050)
    a_win = app._comparison_fy_window_slice(a, *bounds)
    b_win = app._comparison_fy_window_slice(b, *bounds)
    # The full-window cards are byte-identical to the unwindowed seam-aware
    # call the panel makes on main - values, subtitles, tones, everything.
    windowed = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", a_win, b_win, result["value_unit"], None,
        horizon_start_fy=seam_fy,
    )
    previous = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", a, b, result["value_unit"], None,
        horizon_start_fy=seam_fy,
    )
    assert windowed == previous
    assert windowed[0][0] == "Scenario A - Cumulative nominal to FY2050"
    # And the underlying aggregates are exactly equal, not approximately.
    assert app.cumulative_total(a_win) == app.cumulative_total(a[a.index >= seam_fy])
    assert app.npv_to_horizon(a_win) == app.npv_to_horizon(a)
    assert app.npv_to_horizon(b_win, rate=0.0) == app.npv_to_horizon(b, rate=0.0)


def test_history_extends_to_the_published_fy2026_actual(comparison_context) -> None:
    """PREBU26 publishes FY2026 as an ACTUAL; the grey history line carries it.

    The forecast sides still start at FY2027, so the FY2026 point is display
    history only - it can never reach a delta, NPV or window aggregate - and
    its value is the published official actual byte-for-byte.
    """
    pack, _ = comparison_context
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys())
    history = result["history"]
    years = sorted(int(fy) for fy in history.index)
    assert years[-1] == 2026
    assert min(int(fy) for fy in result["a"].index) == 2027
    rows = pack.revenue_chart_rows
    label_col = "series_label" if "series_label" in rows.columns else "stream_label"
    official = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows[label_col].astype(str).eq("Total NLTF revenue")
        & rows["trace_name"].astype(str).eq("PREBU26 official")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2026)
    ]
    if "value_status" in official.columns:
        official = official[official["value_status"].astype(str).eq("actual")]
    expected = float(pd.to_numeric(official["value"], errors="coerce").dropna().iloc[0])
    assert float(history.loc[2026]) == pytest.approx(expected, rel=1e-12)
    # A published historical actual still wins where both exist: every
    # pre-2026 history year is the grey spine's own value ordering-wise.
    assert years == sorted(set(years)), "duplicate June years in history"


def test_comparison_figure_bridges_the_actual_seam_visually() -> None:
    """A connector joins the last actual to each side's first forecast year.

    Display-only: it is legend-less, hover-less and drawn only when the
    forecast starts the very next June year, so a narrowed window (or a
    non-contiguous horizon) draws no bridge.
    """
    history = pd.Series([90.0, 95.0], index=[2025, 2026])
    a = pd.Series([100.0, 101.0], index=[2027, 2028])
    b = pd.Series([102.0, 103.0], index=[2027, 2028])
    figure = app._scenario_comparison_figure(history, a, b, "$m nominal ex GST")
    connectors = [
        trace for trace in figure.data
        if trace.showlegend is False and trace.mode == "lines"
    ]
    assert len(connectors) == 2
    for trace in connectors:
        assert [int(x) for x in trace.x] == [2026, 2027]
        assert trace.y[0] == pytest.approx(95.0 / 1000.0)
    # Aggregate series are untouched: the scenario traces still start at 2027.
    scenario_traces = [t for t in figure.data if t.name in ("Scenario A", "Scenario B")]
    for trace in scenario_traces:
        assert min(int(x) for x in trace.x) == 2027
    # A window that no longer starts right after the actuals draws no bridge.
    narrowed = pd.Series([100.0], index=[2030])
    figure_narrowed = app._scenario_comparison_figure(history, narrowed, narrowed, "$m nominal ex GST")
    assert not [
        trace for trace in figure_narrowed.data
        if trace.showlegend is False and trace.mode == "lines"
    ]


def test_narrowed_window_zooms_the_paths_chart_to_selected_years() -> None:
    """A narrowed window shows ONLY the selected June years on the paths chart.

    History (and with it the seam bridge) is dropped and the x-axis clamps to
    the window, with year-level ticks for short spans; the full-window call is
    byte-identical to the pre-window chart with history and auto-ranging.
    """
    history = pd.Series([90.0, 95.0], index=[2025, 2026])
    a = pd.Series([100.0 + i for i in range(7)], index=list(range(2027, 2034)))
    figure = app._scenario_comparison_figure(
        history, a, a, "$m nominal ex GST", x_window=(2027, 2033)
    )
    assert "Actual" not in [str(trace.name) for trace in figure.data]
    assert tuple(figure.layout.xaxis.range) == (2026.5, 2033.5)
    assert figure.layout.xaxis.dtick == 1
    figure_full = app._scenario_comparison_figure(history, a, a, "$m nominal ex GST")
    assert "Actual" in [str(trace.name) for trace in figure_full.data]
    assert figure_full.layout.xaxis.range is None
    assert figure_full.layout.xaxis.dtick == 5


def test_prebu26_seam_keeps_fy2026_out_of_the_window_and_aggregates(comparison_context) -> None:
    """The window floor follows the selected vintage's presentation seam.

    Under the default PREBU26 comparator the Current FY2026 point is a
    published actual on the official side and masked on the Current side, so
    it must be unselectable and unable to enter any A/B aggregate - while the
    prior BEFU26 seam still starts at FY2026 when that vintage is selected.
    """
    keys = _keys()
    result = _paths(comparison_context, "Total NLTF revenue", keys, keys)
    a = result["a"]
    # The governed comparison path itself publishes no pre-seam June year, so
    # no hidden FY2026 Current annual point can reach the aggregates.
    assert min(int(fy) for fy in a.index) == 2027
    # Defence in depth: even a series that DID carry a pre-seam anchor point
    # could not offer or include it once the seam floors the bounds.
    with_anchor = pd.Series(
        [999.0, *a.to_numpy(dtype=float)], index=[2026, *a.index]
    )
    bounds = app._comparison_fy_window_bounds(with_anchor, with_anchor, start_floor_fy=2027)
    assert bounds == (2027, 2050)
    sliced = app._comparison_fy_window_slice(with_anchor, *bounds)
    assert 2026 not in {int(fy) for fy in sliced.index}
    assert app.cumulative_total(sliced) == app.cumulative_total(a)
    # And the seam-aware cards exclude the anchor even if it were fed through.
    cards_anchor = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", with_anchor, with_anchor,
        result["value_unit"], None, horizon_start_fy=2027,
    )
    cards_clean = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", a, a, result["value_unit"], None,
        horizon_start_fy=2027,
    )
    assert cards_anchor == cards_clean
    # The prior-vintage seam is untouched: BEFU26 still starts at FY2026.
    befu_keys = _keys(vintage="BEFU26")
    assert app._comparison_horizon_start_fy(befu_keys[1]) == 2026


def test_selected_subrange_recalculates_a_b_and_delta_exactly(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fleet="High"))
    a, b = result["a"], result["b"]
    a_win = app._comparison_fy_window_slice(a, 2030, 2040)
    b_win = app._comparison_fy_window_slice(b, 2030, 2040)
    assert sorted(int(fy) for fy in a_win.index) == list(range(2030, 2041))
    assert app.cumulative_total(a_win) == pytest.approx(
        float(sum(a.loc[fy] for fy in range(2030, 2041))), rel=1e-12
    )
    cum_delta = app.cumulative_total(b_win) - app.cumulative_total(a_win)
    assert cum_delta == pytest.approx(
        float(sum(b.loc[fy] - a.loc[fy] for fy in range(2030, 2041))), rel=1e-9
    )
    # Every surviving year is byte-identical to the unwindowed path: the
    # window filters, it never recomputes.
    for fy in (2030, 2035, 2040):
        assert a_win.loc[fy] == a.loc[fy]
        assert b_win.loc[fy] == b.loc[fy]
    # And slicing left the source series untouched (PREBU26 seam: the
    # forecast series publishes FY2027-FY2050).
    assert sorted(int(fy) for fy in a.index if int(fy) >= 2026) == list(range(2027, 2051))


def test_window_npv_keeps_the_fy2026_discount_base(comparison_context) -> None:
    from model_dashboard.npv import mbcm_discount_factors

    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys())
    a = result["a"]
    a_win = app._comparison_fy_window_slice(a, 2030, 2040)
    # Only FY2030-FY2040 cash flows enter, but each keeps its factor relative
    # to the existing FY2026 anchor - factors are NOT rebased to FY2030.
    factors = mbcm_discount_factors(2040 - 2026 + 1)
    expected = sum(float(a.loc[fy]) * factors[fy - 2026] for fy in range(2030, 2041))
    assert app.npv_to_horizon(a_win) == pytest.approx(expected, rel=1e-12)
    rebased = sum(
        float(a.loc[fy]) * mbcm_discount_factors(2040 - 2030 + 1)[fy - 2030]
        for fy in range(2030, 2041)
    )
    assert app.npv_to_horizon(a_win) < rebased


def test_windowed_stream_deltas_sum_to_the_windowed_headline_delta(comparison_context) -> None:
    window = (2030, 2040)
    keys_a, keys_b = _keys(), _keys(uptake="MoT VFM fast")
    total = _paths(comparison_context, "Total NLTF revenue", keys_a, keys_b)
    nominal_a = app.npv_to_horizon(app._comparison_fy_window_slice(total["a"], *window), rate=0.0)
    nominal_b = app.npv_to_horizon(app._comparison_fy_window_slice(total["b"], *window), rate=0.0)
    component_npvs = {
        series: app._scenario_component_npv(
            _paths(comparison_context, series, keys_a, keys_b), 0.0, window=window
        )
        for series in app._SCENARIO_COMPONENT_FETCH_SERIES
    }
    components = app._scenario_npv_component_breakdown(component_npvs, nominal_a, nominal_b)
    assert sum(a for _, a, _ in components) == pytest.approx(nominal_a, abs=1e-6)
    assert sum(b for _, _, b in components) == pytest.approx(nominal_b, abs=1e-6)
    assert sum(b - a for _, a, b in components) == pytest.approx(
        nominal_b - nominal_a, abs=1e-6
    )
    # The waterfall built from those windowed deltas closes to the windowed
    # headline delta (immaterial <$1m bars may be dropped, hence the floor).
    figure = app._scenario_npv_component_bridge_figure(
        nominal_a, nominal_b, components, total["value_unit"]
    )
    trace = figure.data[0]
    dropped_budget = app._SCENARIO_COMPONENT_MATERIALITY * len(components) / 1000.0
    assert sum(list(trace.y)[:-1]) == pytest.approx(
        (nominal_b - nominal_a) / 1000.0, abs=dropped_budget
    )


def test_one_year_window_works(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fleet="High"))
    a, b = result["a"], result["b"]
    a_win = app._comparison_fy_window_slice(a, 2035, 2035)
    b_win = app._comparison_fy_window_slice(b, 2035, 2035)
    assert list(int(fy) for fy in a_win.index) == [2035]
    assert app.cumulative_total(a_win) == pytest.approx(float(a.loc[2035]), rel=1e-12)
    cards = app._scenario_comparison_cards(
        "Total NLTF revenue", "revenue", a_win, b_win, result["value_unit"], None
    )
    assert cards[0][0] == "Scenario A - Cumulative nominal to FY2035"
    assert cards[3][2].startswith("FY2035, ")
    assert app._comparison_fy_window_label(2035, 2035) == "FY2035"


def test_identical_scenarios_give_zero_delta_in_any_window(comparison_context) -> None:
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys())
    for window in ((2026, 2050), (2030, 2040), (2035, 2035)):
        a_win = app._comparison_fy_window_slice(result["a"], *window)
        b_win = app._comparison_fy_window_slice(result["b"], *window)
        cards = app._scenario_comparison_cards(
            "Total NLTF revenue", "revenue", a_win, b_win, result["value_unit"], None
        )
        assert cards[2][1] == "+$0m", window
        assert cards[3][1] == "+$0m", window
        assert cards[2][4] == "mixed" and cards[3][4] == "mixed", window


def test_the_window_is_not_part_of_any_scenario_identity() -> None:
    import dataclasses
    import inspect

    field_names = [field.name for field in dataclasses.fields(app.RevenueScenarioComputationKey)]
    assert not any("window" in name.lower() for name in field_names)
    # The cached fetch takes no window: filtering happens strictly AFTER the
    # governed computation, so the window can never invalidate a cache entry
    # or change an underlying annual value.
    fetch_source = inspect.getsource(app.cached_scenario_comparison_paths)
    assert "window" not in fetch_source
    assert app._COMPARISON_WINDOW_STATE_KEY not in fetch_source
    panel_source = inspect.getsource(app._render_scenario_comparison_panel)
    assert "_render_comparison_window_control(" in panel_source
    assert panel_source.index("cached_scenario_comparison_paths(") < panel_source.index(
        "_render_comparison_window_control("
    )


def test_composition_figure_groups_by_stream() -> None:
    components = [
        ("TUC & other", 350.0, 350.0),
        ("PED / FED (net)", 40000.0, 38000.0),
        ("Heavy & other RUC", 39000.0, 39000.0),
        ("Net MVR", 0.2, 0.4),  # immaterial in both scenarios -> dropped
    ]
    figure = app._scenario_npv_composition_figure(components, "$m nominal ex GST")
    assert figure.layout.barmode == "group"
    by_name = {trace.name: trace for trace in figure.data}
    assert set(by_name) == {"Scenario A", "Scenario B"}
    # per-scenario bars cover every material stream and sum to the totals
    for trace, key in ((by_name["Scenario A"], 1), (by_name["Scenario B"], 2)):
        assert sum(trace.x) == pytest.approx(sum(row[key] for row in components[:3]) / 1000.0)
        assert "Net MVR" not in list(trace.y)
    # streams read largest first (top of a reversed y axis)
    assert list(by_name["Scenario A"].y) == ["PED / FED (net)", "Heavy & other RUC", "TUC & other"]
    assert figure.layout.yaxis.autorange == "reversed"

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
    result = _paths(comparison_context, "Total NLTF revenue", _keys(), _keys(fed_on=False))
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


def _typed_keys(policy=None, fleet="Off"):
    """A (sensitivity, typed uptake) pair like the production page builds."""
    sensitivity = app.selected_sensitivity_key(fleet, "Off", "Off", freight_rail_shift="Off")
    uptake = app.RevenueScenarioComputationKey(
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=policy or app.FED_POLICY_PUBLISHED,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
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
    keys = _typed_keys(policy=app.FED_POLICY_DELAYED_6M)
    result = _comparison(
        comparison_context, "Total NLTF revenue", keys, keys, BASE_TRACE, HIGH_TRACE
    )
    for side in ("a", "b"):
        years = sorted(int(year) for year in result[side].index if int(year) >= 2026)
        assert years == list(range(2026, 2051)), side
    assert app._comparison_alignment_gate(result["a"], result["b"]) == ""


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

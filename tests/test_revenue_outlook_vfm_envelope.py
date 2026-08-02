"""Integrated VFM Scenario Envelope: the blue range on the Total path chart.

The band is the pair of governed MoT VFM fleet-composition scenarios (Fast and
Slow) run through the same engine, vintages, schedule, policy and macro
settings as the Current path it wraps.  It is a STRUCTURAL SCENARIO ENVELOPE:
not a confidence, credible or prediction interval, and carrying no probability.
The grey empirical 50%/80% forecast-error fan is a separate concept with its
own supported horizon; these tests keep the two apart.

Every expected bound here is recomputed from the exact VFM overlay rows, never
from the band constructor under test.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import app
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE
from model_dashboard.revenue_chart_layers import VFM_ENVELOPE_LAYER_ID
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    FAN_SEGMENT_EMPIRICAL,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

ROOT = Path(__file__).resolve().parents[1]
AR1_REVENUE_OUTLOOK_DIR = Path("data") / "engine_ar1" / "current_revenue_outlook"
FED = "Current planned path"
ANCHOR_FY = 2030
DEFAULT_SERIES = "Total NLTF revenue"
TRACES = (
    "Actual",
    "Current finalist Base case",
    "Current finalist High population/comparison",
    "BEFU26 official",
)
BASE_TRACE = "Current finalist Base case"


@pytest.fixture(scope="module", autouse=True)
def _vfm_analyst_layers_enabled():
    """Run this module with the paused analyst surface deliberately switched on.

    The public dashboard hides the MoT VFM Fast/Slow layers
    (``REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = False``), and hiding them
    also stops their calculations running - that is the point of the pause.
    The calculation chain, its governance identities and its evidence are all
    RETAINED so the feature can be restored by flipping that one constant, so
    these tests keep protecting it with the gate held open. Without this the
    suite would quietly stop covering the restore path.

    The view cache is cleared on the way in and out: entries computed under the
    other setting carry a different cone band and must not leak either way.
    """
    import model_dashboard.revenue_outlook_presentation_policy as policy

    previous_policy = policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
    previous_app = app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
    policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = True
    app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = True
    app.cached_revenue_outlook_view.clear()
    try:
        yield
    finally:
        policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = previous_policy
        app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = previous_app
        app.cached_revenue_outlook_view.clear()
COMPARISON_TRACE = "Current finalist High population/comparison"

# Series the VFM light-fleet composition genuinely reallocates, and series it
# provably does not touch while the PED retention sensitivity is off.
APPLICABLE_SERIES = (
    "Total NLTF revenue",
    "Light RUC revenue",
    "Light RUC net km",
    "Total RUC all classes",
    "Total RUC+PED revenue",
)
INAPPLICABLE_SERIES = ("Net MVR revenue",)


# --------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def pack():
    loaded = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert loaded is not None
    return loaded


@pytest.fixture(scope="module")
def signature():
    return revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)


@pytest.fixture(scope="module")
def ar1_context():
    directory = ROOT / AR1_REVENUE_OUTLOOK_DIR
    if not directory.exists():
        pytest.skip("the AR(1) engine pack is not present in this checkout")
    loaded = load_revenue_outlook_pack(directory, repo_root=ROOT)
    assert loaded is not None
    return loaded, revenue_outlook_signature(directory, ROOT)


def sensitivity_key() -> tuple[str, ...]:
    return app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")


def uptake_key(
    mode: str = DEFAULT_EV_UPTAKE_MODE,
    *,
    ped_retention: bool = False,
    vintage: str = "BEFU26",
    overlay: bool = False,
    schedule: str = "balanced_structural",
    shape_vintage: str = "BEFU26",
    current_policy: str = app.FED_POLICY_PUBLISHED,
    eruc: tuple[float, ...] = (),
) -> tuple[Any, ...]:
    """The production key shape built by ``render_revenue_outlook_page``."""
    return (
        mode, (), eruc, current_policy, app.FED_POLICY_PUBLISHED,
        ped_retention, vintage, overlay, schedule, shape_vintage,
    )


def view_for(
    pack,
    signature,
    series: str = DEFAULT_SERIES,
    key: tuple[Any, ...] | None = None,
    *,
    traces: tuple[str, ...] = TRACES,
    time_grain: str = "june_year",
) -> dict[str, Any]:
    return app.cached_revenue_outlook_view(
        signature, series, time_grain, FED, traces, sensitivity_key(),
        PED_BRIDGE_DEFAULT_MODE, key or uptake_key(), pack,
    )


def independent_bounds(
    pack,
    signature,
    series: str,
    key: tuple[Any, ...],
    *,
    trace: str = BASE_TRACE,
) -> pd.DataFrame:
    """Recompute the Fast/Slow bounds WITHOUT the band constructor.

    Filters the exact VFM overlay rows directly, so a defect inside
    ``cached_view_cone_band`` cannot make its own expectation agree with it.
    """
    collected: dict[str, pd.Series] = {}
    for name in ("MoT VFM fast", "MoT VFM slow"):
        rows, *_ = app.cached_scenario_overlay_rows(
            signature, sensitivity_key(), PED_BRIDGE_DEFAULT_MODE,
            (name, *tuple(key[1:])), pack,
        )
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["trace_name"].astype(str).eq(trace)
            & ~rows["row_type"].astype(str).eq("historical_actual")
            & rows["series_label"].astype(str).eq(series)
            & rows["fed_path"].astype(str).eq(FED)
        ]
        collected[name] = pd.Series(
            pd.to_numeric(selected["value"], errors="coerce").to_numpy(),
            index=selected["period"].astype(str),
        )
    merged = pd.DataFrame(collected).dropna()
    return pd.DataFrame(
        {
            "period": merged.index.astype(str),
            "lower": merged.min(axis=1).to_numpy(),
            "upper": merged.max(axis=1).to_numpy(),
        }
    ).reset_index(drop=True)


def figure_for(view: dict[str, Any], series: str = DEFAULT_SERIES):
    """The envelope is now an OPT-IN chart layer, so ask for it explicitly.

    It used to be drawn whenever a band existed. Under the layered contract a
    reader chooses it from the single "Show on chart" control, so a figure
    built without that layer id correctly has no envelope.
    """
    return app.revenue_outlook_total_path_figure(
        view["filtered_rows"],
        selected_series=series,
        selected_fy="FY2030",
        cone_band=view.get("cone_band"),
        selected_official_trace="BEFU26 official",
        selected_band_layers=(VFM_ENVELOPE_LAYER_ID,),
    )


def test_the_envelope_is_absent_unless_its_layer_is_selected(pack, signature) -> None:
    view = view_for(pack, signature)
    without = app.revenue_outlook_total_path_figure(
        view["filtered_rows"],
        selected_series=DEFAULT_SERIES,
        selected_fy="FY2030",
        cone_band=view.get("cone_band"),
        selected_official_trace="BEFU26 official",
        selected_band_layers=(),
    )
    assert not any("MoT VFM" in str(trace.name) for trace in without.data)
    assert not view["cone_band"].empty, "the band data must still be available"


# ---------------------------------------------------- 1. the band exists
def test_the_default_total_path_series_has_a_non_empty_vfm_band(pack, signature) -> None:
    band = view_for(pack, signature)["cone_band"]
    assert not band.empty, "the decision-facing default series lost its VFM range"
    assert list(band.columns) == ["period", "lower", "upper"]
    assert band["period"].is_unique


@pytest.mark.parametrize("series", APPLICABLE_SERIES)
def test_every_vfm_affected_series_receives_a_band(pack, signature, series) -> None:
    assert not view_for(pack, signature, series)["cone_band"].empty, series


# --------------------------------- 2, 4. bounds equal an independent Fast/Slow
@pytest.mark.parametrize("series", APPLICABLE_SERIES)
def test_each_bound_equals_an_independently_calculated_fast_slow_extreme(
    pack, signature, series
) -> None:
    key = uptake_key()
    band = view_for(pack, signature, series)["cone_band"].reset_index(drop=True)
    expected = independent_bounds(pack, signature, series, key)
    expected = expected[expected["period"].isin(set(band["period"]))].reset_index(drop=True)

    # 4. the join must not be vacuous.
    assert len(band) > 0, series
    assert len(expected) == len(band), f"{series}: parity join dropped rows"
    assert list(band["period"]) == list(expected["period"])

    pd.testing.assert_series_equal(
        band["lower"], expected["lower"], check_names=False, rtol=0, atol=1e-9
    )
    pd.testing.assert_series_equal(
        band["upper"], expected["upper"], check_names=False, rtol=0, atol=1e-9
    )


# ------------------------------------------------------------ 3. ordering
@pytest.mark.parametrize("series", APPLICABLE_SERIES)
def test_upper_is_never_below_lower(pack, signature, series) -> None:
    band = view_for(pack, signature, series)["cone_band"]
    assert (band["upper"] >= band["lower"] - 1e-12).all(), series


# ------------------------------------------- 5, 6, 7. the figure contract
def test_the_figure_has_two_boundary_traces_and_one_filled_legend_entry(
    pack, signature
) -> None:
    figure = figure_for(view_for(pack, signature))
    band_traces = [trace for trace in figure.data if "MoT VFM" in str(trace.name)]
    assert len(band_traces) == 2, [trace.name for trace in band_traces]
    dotted = [trace for trace in band_traces if trace.line.dash == "dot"]
    assert len(dotted) == 2, "both boundaries must be dotted"
    assert all(trace.mode == "lines" for trace in band_traces), "no point markers"
    filled = [trace for trace in band_traces if trace.fill == "tonexty"]
    assert len(filled) == 1
    assert filled[0].fillcolor.startswith("rgba(0,111,173")
    legend_entries = [trace for trace in band_traces if trace.showlegend]
    assert len(legend_entries) == 1, "the envelope is one legend item, not two"


def test_the_legend_reads_the_governed_historical_wording(pack, signature) -> None:
    figure = figure_for(view_for(pack, signature))
    legend = [
        str(trace.name) for trace in figure.data
        if trace.showlegend and "MoT VFM" in str(trace.name)
    ]
    assert legend == ["MoT VFM fast–slow range"]
    assert app.VFM_ENVELOPE_LEGEND_LABEL == "MoT VFM fast–slow range"


def test_the_band_is_drawn_behind_every_current_and_official_line(pack, signature) -> None:
    figure = figure_for(view_for(pack, signature))
    band_positions = [
        index for index, trace in enumerate(figure.data) if "MoT VFM" in str(trace.name)
    ]
    line_positions = [
        index for index, trace in enumerate(figure.data) if "MoT VFM" not in str(trace.name)
    ]
    assert band_positions and line_positions
    assert max(band_positions) < min(line_positions), (
        "a line trace was drawn under the shading"
    )
    plotted = {str(trace.name) for trace in figure.data}
    assert BASE_TRACE in plotted and "BEFU26 official" in plotted, (
        "the ordering check must not pass on a chart with no lines"
    )


# --------------------------------------- 8. the comparator is display-only
def test_the_selected_official_comparator_cannot_alter_the_current_vfm_band(
    pack, signature
) -> None:
    befu = view_for(pack, signature, key=uptake_key(vintage="BEFU26"))["cone_band"]
    mbu = view_for(pack, signature, key=uptake_key(vintage="MBU26"))["cone_band"]
    overlaid = view_for(
        pack, signature, key=uptake_key(vintage="BEFU26", overlay=True)
    )["cone_band"]
    assert not befu.empty
    pd.testing.assert_frame_equal(befu.reset_index(drop=True), mbu.reset_index(drop=True))
    pd.testing.assert_frame_equal(
        befu.reset_index(drop=True), overlaid.reset_index(drop=True)
    )


# ------------------------------ 9. no borrowing between scenario roles
def test_base_and_comparison_scenarios_do_not_borrow_one_anothers_band(
    pack, signature
) -> None:
    """The band bounds the BASE case; the comparison path has its own spread."""
    key = uptake_key()
    band = view_for(pack, signature)["cone_band"].reset_index(drop=True)
    base = independent_bounds(pack, signature, DEFAULT_SERIES, key, trace=BASE_TRACE)
    comparison = independent_bounds(
        pack, signature, DEFAULT_SERIES, key, trace=COMPARISON_TRACE
    )
    shared = sorted(set(band["period"]) & set(comparison["period"]))
    assert shared, "the comparison trace must overlap the band periods"

    base_rows = base.set_index("period").loc[shared]
    comparison_rows = comparison.set_index("period").loc[shared]
    band_rows = band.set_index("period").loc[shared]

    pd.testing.assert_frame_equal(band_rows, base_rows, rtol=0, atol=1e-9)
    assert not band_rows.equals(comparison_rows), (
        "the base-case band must not equal the comparison scenario's spread"
    )


# ----------------------------- 10, 11. schedule and policy enter the band
def test_the_selected_long_run_schedule_enters_the_band_identity(pack, signature) -> None:
    """The schedule/shape selection is carried into the Fast/Slow runs.

    The band VALUES are equal across schedules here, and correctly so: the
    transition schedule only reshapes FY2031-FY2050, which is exactly the
    composition-invariant window the envelope is clipped away from.  What must
    be proven is that the selection reaches the constructor at all, so a future
    schedule that does move the econometric window cannot be ignored.
    """
    balanced = uptake_key(schedule="balanced_structural", shape_vintage="BEFU26")
    unblended = uptake_key(schedule=app.UNBLENDED_SCHEDULE_ID, shape_vintage="")
    balanced_preset = app._cone_preset_key("MoT VFM fast", app._cone_band_controls(balanced))
    unblended_preset = app._cone_preset_key("MoT VFM fast", app._cone_band_controls(unblended))
    assert balanced_preset.uptake_basis == "MoT VFM fast"
    assert app._long_run_shape_scope(balanced_preset) == ("balanced_structural", "BEFU26")
    assert app._long_run_shape_scope(unblended_preset) == (app.UNBLENDED_SCHEDULE_ID, "")
    assert app._long_run_shape_scope(
        app._cone_preset_key("MoT VFM slow", app._cone_band_controls(balanced))
    ) == ("balanced_structural", "BEFU26")
    # The band's cache identity must exclude the displayed basis and nothing else.
    assert app._cone_band_controls(uptake_key("MoT VFM fast")) == app._cone_band_controls(
        uptake_key("MoT VFM slow")
    )
    assert app._cone_band_controls(balanced) != app._cone_band_controls(unblended)
    # And the band still computes under both selections.
    assert not view_for(pack, signature, key=balanced)["cone_band"].empty
    assert not view_for(pack, signature, key=unblended)["cone_band"].empty


def test_the_current_policy_selection_moves_the_band_and_is_applied_once(
    pack, signature
) -> None:
    published = view_for(
        pack, signature, key=uptake_key(current_policy=app.FED_POLICY_PUBLISHED)
    )["cone_band"]
    no_uplift = view_for(
        pack, signature, key=uptake_key(current_policy=app.FED_POLICY_OFF)
    )["cone_band"]
    assert not published.empty and not no_uplift.empty
    assert not published.reset_index(drop=True).equals(no_uplift.reset_index(drop=True)), (
        "the Current 12c policy must reach the envelope"
    )
    # Applied ONCE: the band still equals an independent single-pass Fast/Slow
    # run under the same policy, so no second application has crept in.
    key = uptake_key(current_policy=app.FED_POLICY_OFF)
    expected = independent_bounds(pack, signature, DEFAULT_SERIES, key)
    expected = expected[expected["period"].isin(set(no_uplift["period"]))].reset_index(
        drop=True
    )
    assert len(expected) == len(no_uplift) > 0
    pd.testing.assert_frame_equal(
        no_uplift.reset_index(drop=True), expected, rtol=0, atol=1e-9
    )


def test_returning_to_the_original_controls_returns_the_original_band(
    pack, signature
) -> None:
    original = view_for(pack, signature)["cone_band"].copy()
    for key in (
        uptake_key("MoT VFM fast"),
        uptake_key(current_policy=app.FED_POLICY_OFF),
        uptake_key(ped_retention=True),
        uptake_key(vintage="MBU26"),
    ):
        view_for(pack, signature, key=key)
    returned = view_for(pack, signature)["cone_band"]
    pd.testing.assert_frame_equal(
        original.reset_index(drop=True), returned.reset_index(drop=True)
    )


def test_value_changing_controls_invalidate_the_band(pack, signature) -> None:
    original = view_for(pack, signature)["cone_band"].reset_index(drop=True)
    ped_on = view_for(pack, signature, key=uptake_key(ped_retention=True))[
        "cone_band"
    ].reset_index(drop=True)
    assert not original.equals(ped_on), "the PED retention sensitivity must reach the band"
    # The displayed uptake basis is NOT one of them: the envelope always
    # evaluates the Fast and Slow presets, so it is basis-invariant by design.
    for mode in ("MoT VFM fast", "MoT VFM slow"):
        pd.testing.assert_frame_equal(
            original,
            view_for(pack, signature, key=uptake_key(mode))["cone_band"].reset_index(
                drop=True
            ),
        )


# -------------------------- 12, 13, 14, 15, 16. nothing governed moved
def test_published_official_vintage_rows_are_unchanged(pack) -> None:
    """The published comparator rows are read straight from the committed pack."""
    rows = pack.revenue_chart_rows
    for vintage, expected_trace in (("BEFU26", "BEFU26 official"), ("MBU26", "MBU26 official")):
        published = rows[rows["trace_name"].astype(str).eq(expected_trace)]
        assert not published.empty, vintage
        committed = pd.read_csv(
            ROOT / CURRENT_REVENUE_OUTLOOK_DIR / "revenue_chart_rows.csv"
        )
        committed = committed[committed["trace_name"].astype(str).eq(expected_trace)]
        assert len(published) == len(committed), vintage
        assert pd.to_numeric(published["value"], errors="coerce").sum() == pytest.approx(
            pd.to_numeric(committed["value"], errors="coerce").sum(), rel=0, abs=1e-6
        ), vintage


def test_the_band_is_display_only_and_moves_no_chart_value(pack, signature) -> None:
    """Passing the band must not perturb a single plotted line point."""
    view = view_for(pack, signature)
    with_band = figure_for(view)
    without_band = app.revenue_outlook_total_path_figure(
        view["filtered_rows"],
        selected_series=DEFAULT_SERIES,
        selected_fy="FY2030",
        cone_band=None,
        selected_official_trace="BEFU26 official",
    )
    lines_with = {
        str(trace.name): list(trace.y)
        for trace in with_band.data
        if "MoT VFM" not in str(trace.name)
    }
    lines_without = {str(trace.name): list(trace.y) for trace in without_band.data}
    assert lines_with and lines_with.keys() == lines_without.keys()
    for name, values in lines_with.items():
        assert values == lines_without[name], name


def test_the_empirical_fan_data_is_untouched_and_still_stops_at_fy2030(pack) -> None:
    bands = pack.fan_band_rows
    assert not bands.empty
    for column in ("central", "lower50", "upper50", "lower80", "upper80", "interpretation"):
        assert column in bands.columns, column
    committed = pd.read_csv(ROOT / CURRENT_REVENUE_OUTLOOK_DIR / "fan_band_rows.csv")
    assert len(bands) == len(committed)
    for column in ("lower50", "upper50", "lower80", "upper80"):
        assert pd.to_numeric(bands[column], errors="coerce").sum() == pytest.approx(
            pd.to_numeric(committed[column], errors="coerce").sum(), rel=0, abs=1e-6
        ), column
    fy = pd.to_numeric(bands["FY"], errors="coerce")
    empirical = bands["fan_segment"].astype(str).eq(FAN_SEGMENT_EMPIRICAL)
    assert empirical.any(), "the empirical/long-run split must not be vacuous"
    assert not (empirical & fy.gt(ANCHOR_FY)).any(), "an empirical band ran past FY2030"


def test_long_run_fan_rows_are_still_labelled_non_probabilistic(pack) -> None:
    bands = pack.fan_band_rows
    fy = pd.to_numeric(bands["FY"], errors="coerce")
    long_run = bands[fy.gt(ANCHOR_FY)]
    if long_run.empty:
        pytest.skip("no long-run scenario rows materialised in this pack")
    text = " ".join(long_run["interpretation"].dropna().astype(str)).lower()
    assert "not probabilistic" in text
    for banned in ("confidence interval", "credible interval", "prediction interval"):
        assert banned not in text, banned


# -------------------------------------- 17, 18. the page presentation contract
def test_the_default_page_does_not_render_the_fan_card_in_its_primary_layout() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    primary, _, remainder = source.partition("revenue_outlook_show_fan_detail")
    assert remainder, "the fan request gate is missing"
    assert "_render_revenue_outlook_fan_card(" not in primary, (
        "the fan card is back in the eagerly rendered primary layout"
    )
    assert "cached_revenue_outlook_fan_figure(" not in primary, (
        "the fan figure must not be constructed before it is requested"
    )
    assert "_render_revenue_outlook_fan_card(" in remainder


def test_the_total_path_chart_renders_full_width() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "st.columns([0.64, 0.36])" not in source, "the 64/36 split is back"
    assert "primary_cols" not in source, "the Total path chart is inside a column again"
    marker = '"Total path chart"'
    assert source.count(marker) == 1, "expected exactly one Total path chart card"
    # The card must be a bare call, not the body of a `with <column>:` block.
    chart_call = source.rindex("chart_card(", 0, source.index(marker))
    line_start = source.rindex("\n", 0, chart_call) + 1
    indent = len(source[line_start:chart_call])
    assert indent == 8, (
        f"the Total path chart card is indented {indent} spaces; anything deeper "
        "than the compare-mode else-branch means it is nested in a layout block"
    )


def test_the_fan_figure_is_only_built_behind_the_request_gate() -> None:
    """No eager construction or serialisation of the removed card."""
    source = inspect.getsource(app.render_revenue_outlook_page)
    gate = source.index("revenue_outlook_show_fan_detail")
    for marker in ("_render_revenue_outlook_fan_card(", "timer.start(\"fan figure\")"):
        assert source.index(marker) > gate, marker


# ----------------------------------- 19. no fabricated width
@pytest.mark.parametrize("series", INAPPLICABLE_SERIES)
def test_series_the_vfm_assumption_does_not_move_get_no_band(pack, signature, series) -> None:
    view = view_for(pack, signature, series)
    assert view["cone_band"].empty, f"{series} received a fabricated VFM range"
    audit = view["cone_band_audit"]
    assert not bool(audit.iloc[0]["band_available"])
    assert "never fabricated" in str(audit.iloc[0]["reason"])


def test_the_band_carries_no_zero_width_tail(pack, signature) -> None:
    """Both ends carry real width; flat runs are cut, not drawn.

    The envelope now runs to FY2050: Base/Fast/Slow share one governed Light
    pool and the exact VFM202405 shares allocate it differently the whole way.
    """
    band = view_for(pack, signature)["cone_band"]
    width = (band["upper"] - band["lower"]).abs()
    level = (band["upper"].abs() + band["lower"].abs()) / 2.0
    assert (width / level > app.CONE_MIN_RELATIVE_WIDTH).iloc[0]
    assert (width / level > app.CONE_MIN_RELATIVE_WIDTH).iloc[-1]
    last_fy = int(str(band["period"].iloc[-1]).replace("FY", ""))
    assert last_fy == 2050, f"the envelope stops at FY{last_fy}"


def test_the_applicability_audit_reports_every_required_field(pack, signature) -> None:
    audit = view_for(pack, signature)["cone_band_audit"]
    assert len(audit) == 1
    row = audit.iloc[0]
    for column in (
        "method", "selected_series", "band_available", "lower_source_scenario",
        "upper_source_scenario", "first_valid_period", "last_valid_period",
        "max_width", "max_width_pct_of_level", "probabilistic", "reason",
    ):
        assert column in audit.columns, column
    assert row["method"] == "Integrated VFM Scenario Envelope"
    assert bool(row["band_available"]) is True
    assert bool(row["probabilistic"]) is False
    assert row["first_valid_period"] == "FY2025"
    assert row["last_valid_period"] == "FY2050"
    assert float(row["max_width"]) > 0


# ------------------------------------------- 20. both engines, one contract
def test_both_engines_produce_the_same_presentation_contract(
    pack, signature, ar1_context
) -> None:
    ar1_pack, ar1_signature = ar1_context
    ensemble_view = view_for(pack, signature)
    ar1_view = view_for(ar1_pack, ar1_signature)
    for view in (ensemble_view, ar1_view):
        band = view["cone_band"]
        assert not band.empty
        assert list(band.columns) == ["period", "lower", "upper"]
        assert (band["upper"] >= band["lower"] - 1e-12).all()
        assert int(str(band["period"].iloc[-1]).replace("FY", "")) == 2050
        figure = figure_for(view)
        band_traces = [trace for trace in figure.data if "MoT VFM" in str(trace.name)]
        assert len(band_traces) == 2
        assert [trace.name for trace in band_traces if trace.showlegend] == [
            "MoT VFM fast–slow range"
        ]
        assert bool(view["cone_band_audit"].iloc[0]["band_available"]) is True
        assert bool(view["cone_band_audit"].iloc[0]["probabilistic"]) is False


def test_each_engine_bounds_its_own_band(pack, signature, ar1_context) -> None:
    """The contract is shared; the numbers must not be borrowed across engines."""
    ar1_pack, ar1_signature = ar1_context
    key = uptake_key()
    for target_pack, target_signature in ((pack, signature), (ar1_pack, ar1_signature)):
        band = view_for(target_pack, target_signature)["cone_band"].reset_index(drop=True)
        expected = independent_bounds(target_pack, target_signature, DEFAULT_SERIES, key)
        expected = expected[expected["period"].isin(set(band["period"]))].reset_index(
            drop=True
        )
        assert len(expected) == len(band) > 0
        pd.testing.assert_frame_equal(band, expected, rtol=0, atol=1e-9)

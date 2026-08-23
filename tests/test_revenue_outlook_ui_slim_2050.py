"""The workshop Revenue Outlook build: fewer controls, horizon capped at FY2050.

Four presentation changes, none of which may move a modelled value:

A  the VFM petrol-retention sensitivity is no longer a reader control;
B  the MoT VFM Fast/Slow analyst layers are paused - and, crucially, their
   calculations no longer RUN, not merely no longer show;
C  nothing decision-facing displays a fiscal year after FY2050;
D  the Total path chart has an in-app expanded workspace.

The tests that matter most here are the negative ones: hiding a layer while
still paying for it would satisfy a screenshot and none of the intent, so the
paused functions are monkeypatched to raise and the default page is required to
render anyway.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import app
import model_dashboard.ev_uptake_levers as ev_uptake_levers
from model_dashboard.revenue_chart_layers import (
    BAND_50_LAYER_ID,
    BAND_80_LAYER_ID,
    VFM_ENVELOPE_LAYER_ID,
    VFM_FAST_TRACE_NAME,
    VFM_SLOW_TRACE_NAME,
)
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_outlook_presentation_policy import (
    REVENUE_OUTLOOK_DISPLAY_END_FY,
    REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL,
    REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS,
    clip_frame_to_display_horizon,
    fiscal_quarters_of_june_year,
    fiscal_year_of_quarter,
    period_within_horizon,
    terminal_display_quarter,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey

ROOT = Path(__file__).resolve().parents[1]
FED = "Current planned path"
SERIES = "Total NLTF revenue"
RETENTION_STATE_KEY = "revenue_outlook_ped_retention_sensitivity"


def production_key(**overrides) -> RevenueScenarioComputationKey:
    """The key the page builds on a default first render."""
    base = dict(
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        heavy_bev_transition=app.HEAVY_BEV_DEFAULT,
    )
    base.update(overrides)
    return RevenueScenarioComputationKey(**base)


@pytest.fixture(scope="module")
def context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


@pytest.fixture(scope="module")
def default_traces(context):
    pack, signature = context
    options = app.cached_revenue_outlook_selectors(signature, pack)["trace_options"]
    return tuple(
        app._revenue_outlook_default_traces(options, selected_official_trace="BEFU26 official")
    )


@pytest.fixture(scope="module")
def default_view(context, default_traces):
    pack, signature = context
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    return app.cached_revenue_outlook_view(
        signature, SERIES, "june_year", FED, default_traces, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, production_key(), pack,
    )


@pytest.fixture(scope="module")
def quarterly_view(context, default_traces):
    pack, signature = context
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    return app.cached_revenue_outlook_view(
        signature, SERIES, "quarterly", FED, default_traces, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, production_key(), pack,
    )


@pytest.fixture(scope="module")
def rendered_page():
    """One default Revenue Outlook render, shared by the widget-absence tests."""
    from streamlit.testing.v1 import AppTest

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception

    # Positive control. Every widget test below asserts that something is
    # ABSENT, and all of them would pass trivially against a page that failed
    # to render. Prove the page is really here before trusting an absence.
    labels = {str(element.label or "") for element in harness.get("selectbox")}
    assert "Series" in labels and "Selected FY" in labels, labels
    assert [key for key in harness.session_state.filtered_state
            if str(key).startswith(app._LAYER_PICKER_KEY_PREFIX)], "no layer picker rendered"
    assert harness.get("plotly_chart"), "no chart rendered"
    return harness


def _plotly_specs(harness) -> list[dict]:
    """Every rendered Plotly figure, read from the element proto.

    ``element.value`` on a keyed plotly chart returns its SELECTION state, not
    the figure, so the spec is parsed from the proto instead.
    """
    specs = []
    for element in harness.get("plotly_chart"):
        spec = getattr(element.proto, "spec", "")
        if spec:
            specs.append(json.loads(spec))
    return specs


def _total_path_traces(harness) -> dict[str, list] | None:
    """The Total path chart's plotted y-values, keyed by trace name."""
    for spec in _plotly_specs(harness):
        traces = spec.get("data", [])
        names = [str(trace.get("name", "")) for trace in traces]
        if not any("Base case" in name for name in names):
            continue
        return {
            f"{index}:{name}": list(trace.get("y", []) or [])
            for index, (name, trace) in enumerate(zip(names, traces))
        }
    return None


def _all_widget_text(harness) -> str:
    """Every label, help string and caption the render produced."""
    parts: list[str] = []
    for element in harness.get("checkbox") + harness.get("toggle"):
        parts.extend([str(element.label or ""), str(getattr(element, "help", "") or "")])
    for element in harness.get("multiselect") + harness.get("selectbox") + harness.get("radio"):
        parts.append(str(element.label or ""))
        parts.append(str(getattr(element, "help", "") or ""))
        for option in getattr(element, "options", None) or []:
            parts.append(str(option))
    for element in harness.get("markdown") + harness.get("caption"):
        parts.append(str(getattr(element, "value", "") or ""))
    return "\n".join(parts)


# ============================================================ A. petrol retention
def test_the_retention_control_is_switched_off_by_policy() -> None:
    assert REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL is False


def test_no_petrol_retention_widget_is_rendered(rendered_page) -> None:
    """The label must be gone from every control on the page."""
    for element in rendered_page.get("checkbox") + rendered_page.get("toggle"):
        label = str(element.label or "")
        assert "petrol-retention" not in label.casefold(), label
        assert app.PED_RETENTION_SENSITIVITY_LABEL not in label, label
    assert RETENTION_STATE_KEY not in rendered_page.session_state


def test_no_petrol_retention_copy_survives_anywhere_on_the_page(rendered_page) -> None:
    """Captions, help text and audit summaries too - not just the widget."""
    text = _all_widget_text(rendered_page).casefold()
    assert "petrol-retention sensitivity" not in text
    assert "retention curve is a structural sensitivity" not in text


def test_production_keys_always_carry_retention_false() -> None:
    assert app._production_ped_retention_sensitivity() is False
    assert production_key().ped_retention_sensitivity is False
    assert app._ped_retention_enabled(production_key()) is False


def test_a_stale_true_session_value_cannot_reactivate_the_overlay() -> None:
    """A browser that persisted True before the control was withdrawn.

    The resolver must not consult session state at all while the control is
    off, and the entry-point cleanup must drop the key outright.
    """
    import streamlit as st

    st.session_state[RETENTION_STATE_KEY] = True
    try:
        assert app._production_ped_retention_sensitivity() is False, (
            "a stale True session value reactivated the retention sensitivity"
        )
        app._discard_withdrawn_revenue_outlook_state()
        assert RETENTION_STATE_KEY not in st.session_state
    finally:
        st.session_state.pop(RETENTION_STATE_KEY, None)


def test_a_stale_true_session_value_is_cleared_by_a_real_render() -> None:
    """End to end: the withdrawn key does not survive a page render."""
    from streamlit.testing.v1 import AppTest

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    harness.session_state[RETENTION_STATE_KEY] = True
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception
    assert RETENTION_STATE_KEY not in harness.session_state


def test_the_retention_transformation_never_runs_on_a_production_render(monkeypatch) -> None:
    """Spy on the overlay entry point: every call must pass adjust_ped=False."""
    from streamlit.testing.v1 import AppTest

    seen: list[bool] = []
    original = ev_uptake_levers.apply_uptake_levers_to_chart_rows

    def recording(*args, **kwargs):
        seen.append(bool(kwargs.get("adjust_ped", True)))
        return original(*args, **kwargs)

    monkeypatch.setattr(ev_uptake_levers, "apply_uptake_levers_to_chart_rows", recording)
    monkeypatch.setattr(app, "apply_uptake_levers_to_chart_rows", recording, raising=False)

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    harness.session_state[RETENTION_STATE_KEY] = True
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception
    assert not any(seen), (
        f"the petrol-retention transformation ran on a production render: {seen}"
    )


def test_the_retention_audit_reports_a_neutral_factor(default_view) -> None:
    """Whatever the audit says, it must say the overlay did nothing."""
    audit = default_view.get("ev_uptake_audit")
    if not isinstance(audit, pd.DataFrame) or audit.empty or "ped_retention" not in audit:
        pytest.skip("this pack's uptake audit carries no ped_retention column")
    factors = pd.to_numeric(audit["ped_retention"], errors="coerce").dropna()
    assert (factors == 1.0).all(), "a production render applied a retention factor"


# ================================================== B. VFM analyst layers paused
def test_the_analyst_layers_are_switched_off_by_policy() -> None:
    assert REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS is False


def test_the_catalogue_offers_no_vfm_fast_slow_layer(context) -> None:
    pack, signature = context
    options = app.cached_revenue_outlook_selectors(signature, pack)["trace_options"]
    catalogue = app._revenue_outlook_layer_catalogue(options, list(options[:1]))
    labels = {spec.label for spec in catalogue}
    ids = {spec.layer_id for spec in catalogue}
    for banned in (VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME):
        assert not any(banned in label for label in labels), banned
    assert VFM_ENVELOPE_LAYER_ID not in ids
    assert not any("fast" in label.casefold() and "vfm" in label.casefold() for label in labels)


def test_the_uncertainty_bands_are_still_offered(context) -> None:
    """The pause removes the structural range, NOT the 50%/80% bands."""
    pack, signature = context
    options = app.cached_revenue_outlook_selectors(signature, pack)["trace_options"]
    ids = {spec.layer_id for spec in app._revenue_outlook_layer_catalogue(options, list(options))}
    assert BAND_50_LAYER_ID in ids
    assert BAND_80_LAYER_ID in ids


def test_no_vfm_layer_option_reaches_the_show_on_chart_control(rendered_page) -> None:
    # The picker offers one tick box per catalogue layer; a paused VFM layer
    # must appear neither as a tick box label nor as a picker session key.
    for element in rendered_page.get("checkbox"):
        text = str(element.label or "").casefold()
        assert not ("vfm" in text and ("fast" in text or "slow" in text)), element.label
    for key in rendered_page.session_state.filtered_state:
        text = str(key).casefold()
        if text.startswith(app._LAYER_PICKER_KEY_PREFIX):
            assert not ("vfm" in text and ("fast" in text or "slow" in text)), key


def test_layer_picker_toggles_visibility_and_bulk_actions() -> None:
    """The compact picker's full behaviour contract, on one live render.

    Toggling a path or band changes only that layer's visibility; the bulk
    actions and the empty-selection default fallback behave exactly like the
    multiselect they replaced.
    """
    from streamlit.testing.v1 import AppTest

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception

    def picker_state() -> dict[str, bool]:
        return {
            str(key): bool(value)
            for key, value in harness.session_state.filtered_state.items()
            if str(key).startswith(app._LAYER_PICKER_KEY_PREFIX)
        }

    initial = picker_state()
    assert initial, "picker rendered no tick boxes"
    default_on = {key for key, ticked in initial.items() if ticked}
    # Defaults are the catalogue's own: both uncertainty bands ticked.
    assert f"{app._LAYER_PICKER_KEY_PREFIX}{BAND_50_LAYER_ID}" in default_on
    assert f"{app._LAYER_PICKER_KEY_PREFIX}{BAND_80_LAYER_ID}" in default_on

    baseline = _total_path_traces(harness)
    assert baseline is not None
    assert any("High population" in name for name in baseline)
    assert any("50% conditional" in name for name in baseline)

    # Unticking a path hides that path and nothing else.
    high_box = next(
        element for element in harness.get("checkbox")
        if str(element.label) == "Current finalist High population/comparison"
    )
    assert bool(high_box.value) is True
    high_box.set_value(False)
    harness.run()
    assert not harness.exception
    after_path = _total_path_traces(harness)
    assert not any("High population" in name for name in after_path)
    assert any("Base case" in name for name in after_path)
    assert any("50% conditional" in name for name in after_path)

    # Unticking a band hides that band and leaves the paths alone.
    band_box = next(
        element for element in harness.get("checkbox")
        if str(element.label) == "50% conditional modelled uncertainty"
    )
    band_box.set_value(False)
    harness.run()
    assert not harness.exception
    after_band = _total_path_traces(harness)
    assert not any("50% conditional" in name for name in after_band)
    assert any("80% conditional" in name for name in after_band)
    assert any("Base case" in name for name in after_band)

    # Bulk actions: all, none (falls back to the defaults with the same
    # caption the multiselect used), then restore defaults.
    next(b for b in harness.button if b.key == "ro_layer_picker_all").click()
    harness.run()
    assert not harness.exception
    assert all(picker_state().values())
    next(b for b in harness.button if b.key == "ro_layer_picker_none").click()
    harness.run()
    assert not harness.exception
    assert not any(picker_state().values())
    captions = "\n".join(str(caption.value) for caption in harness.get("caption"))
    assert "Using the default chart layers." in captions
    next(b for b in harness.button if b.key == "ro_layer_picker_defaults").click()
    harness.run()
    assert not harness.exception
    assert {key for key, ticked in picker_state().items() if ticked} == default_on
    restored = _total_path_traces(harness)
    assert any("High population" in name for name in restored)
    assert any("50% conditional" in name for name in restored)


def test_a_persisted_vfm_selection_is_filtered_not_fatal() -> None:
    """A returning reader's saved layer list must keep working."""
    import streamlit as st

    stale = [
        f"Path · {VFM_FAST_TRACE_NAME}",
        "Band · MoT VFM fast–slow range",
        "Band · 50% conditional modelled uncertainty",
    ]
    st.session_state["revenue_outlook_chart_layers"] = list(stale)
    try:
        app._discard_withdrawn_revenue_outlook_state()
        kept = st.session_state["revenue_outlook_chart_layers"]
        assert kept == ["Band · 50% conditional modelled uncertainty"], kept
    finally:
        st.session_state.pop("revenue_outlook_chart_layers", None)


def test_the_default_view_builds_no_cone_band(default_view) -> None:
    band = default_view.get("cone_band")
    assert band is None or band.empty, "a paused layer was still computed"
    audit = default_view.get("cone_band_audit")
    assert audit is None or audit.empty


def test_the_paused_vfm_calculations_are_never_called(monkeypatch) -> None:
    """The load-bearing test: make them explode, and require a clean render.

    Hiding a layer while still paying for its two extra scenario-overlay
    passes would pass a visual check and miss the entire point.
    """
    from streamlit.testing.v1 import AppTest

    def forbidden(name):
        def _raise(*args, **kwargs):
            raise AssertionError(f"{name} ran during a default Revenue Outlook render")

        _raise.clear = lambda: None
        return _raise

    for name in ("cached_vfm_scenario_paths", "cached_view_cone_band"):
        monkeypatch.setattr(app, name, forbidden(name))
    monkeypatch.setattr(
        app, "_vfm_envelope_applicability_audit", forbidden("_vfm_envelope_applicability_audit")
    )
    monkeypatch.setattr(app, "_cone_preset_key", forbidden("_cone_preset_key"))

    # A stale selection must not be able to reach them either.
    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    harness.session_state["revenue_outlook_chart_layers"] = [
        f"Path · {VFM_FAST_TRACE_NAME}",
        "Band · MoT VFM fast–slow range",
    ]
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception


def test_no_vfm_range_audit_or_download_is_offered(rendered_page) -> None:
    for element in rendered_page.get("toggle") + rendered_page.get("checkbox"):
        label = str(element.label or "").casefold()
        assert "fast–slow range audit" not in label
        assert "fast-slow range audit" not in label
    for element in rendered_page.get("download_button"):
        label = str(getattr(element, "label", "") or "").casefold()
        assert "vfm" not in label or "range" not in label, label


def test_current_base_still_uses_the_exact_vfm_base_composition(default_view) -> None:
    """The pause must not touch what Current Base IS."""
    assert app.DEFAULT_EV_UPTAKE_MODE == "MoT VFM base"
    assert production_key().uptake_basis == "MoT VFM base"
    assert default_view.get("ev_uptake_applied") is True
    audit = default_view.get("ev_uptake_audit")
    assert isinstance(audit, pd.DataFrame) and not audit.empty
    if "share_source" in audit.columns:
        sources = set(audit["share_source"].dropna().astype(str))
        assert sources <= {"exact_vendored_vfm_table"}, sources


# ================================================ C. FY2050 presentation horizon
def test_the_horizon_constant_is_fy2050() -> None:
    assert REVENUE_OUTLOOK_DISPLAY_END_FY == 2050


def test_the_terminal_quarter_is_derived_from_the_june_year_convention() -> None:
    """Not a hardcoded guess: it follows the constant and the fiscal calendar."""
    assert fiscal_quarters_of_june_year(2050) == ("2049Q3", "2049Q4", "2050Q1", "2050Q2")
    assert terminal_display_quarter() == "2050Q2"
    assert fiscal_year_of_quarter("2049Q3") == 2050
    assert fiscal_year_of_quarter("2050Q2") == 2050
    assert fiscal_year_of_quarter("2050Q3") == 2051
    assert fiscal_year_of_quarter("FY2050") is None


def test_period_membership_agrees_across_both_grains() -> None:
    assert period_within_horizon("FY2050") is True
    assert period_within_horizon("FY2051") is False
    assert period_within_horizon("2050Q2") is True
    assert period_within_horizon("2050Q3") is False, "2050Q3 belongs to FY2051"


def test_no_displayed_annual_row_exceeds_fy2050(default_view) -> None:
    rows = default_view["filtered_rows"]
    years = pd.to_numeric(rows.get("june_year"), errors="coerce").dropna()
    assert not years.empty
    assert int(years.max()) <= REVENUE_OUTLOOK_DISPLAY_END_FY, int(years.max())


def test_no_displayed_quarterly_row_exceeds_fy2050(quarterly_view) -> None:
    rows = quarterly_view["filtered_rows"]
    periods = rows.get("period", pd.Series(dtype=str)).astype(str)
    if periods.empty:
        pytest.skip("no quarterly rows for this series in the committed pack")
    breaches = [p for p in set(periods) if not period_within_horizon(p)]
    assert not breaches, sorted(breaches)[:8]


def test_annual_and_quarterly_horizons_agree(default_view, quarterly_view) -> None:
    """The same rule drives both, so the two must land on the same fiscal year."""
    annual = pd.to_numeric(default_view["filtered_rows"].get("june_year"), errors="coerce").dropna()
    periods = quarterly_view["filtered_rows"].get("period", pd.Series(dtype=str)).astype(str)
    quarter_years = [fiscal_year_of_quarter(p) for p in set(periods)]
    quarter_years = [year for year in quarter_years if year is not None]
    if not quarter_years:
        pytest.skip("no quarterly rows for this series in the committed pack")
    assert max(quarter_years) <= int(annual.max())


def test_no_fy_selector_option_exceeds_fy2050(context) -> None:
    pack, signature = context
    options = app.cached_revenue_outlook_selectors(signature, pack)["fy_options"]
    assert options, "the FY marker offered nothing at all"
    beyond = [option for option in options if not period_within_horizon(option)]
    assert not beyond, beyond
    assert options[-1] == f"FY{REVENUE_OUTLOOK_DISPLAY_END_FY}"


def test_the_uncertainty_bands_stop_at_fy2050() -> None:
    rows = app.cached_uncertainty_band_rows("total_nltf_net_revenue", "horizon-test")
    if rows is None or rows.empty:
        pytest.skip("no committed uncertainty rows for this series")
    breaches = [
        str(period)
        for period in rows.get("period", pd.Series(dtype=str)).astype(str)
        if not period_within_horizon(period)
    ]
    assert not breaches, breaches[:8]


def test_the_selected_view_download_stops_at_fy2050(default_view) -> None:
    """What a reader exports must match what a reader saw."""
    rows = default_view["filtered_rows"]
    csv = rows.to_csv(index=False)
    for year in range(REVENUE_OUTLOOK_DISPLAY_END_FY + 1, 2056):
        assert f"FY{year}" not in csv, f"FY{year} reached the selected-view download"


def test_the_governed_source_pack_is_not_truncated(context) -> None:
    """The cap is presentation-only: the audit material must still be there."""
    pack, _ = context
    chart_rows = app._pack_table(pack, "revenue_chart_rows")
    years = pd.to_numeric(chart_rows.get("june_year"), errors="coerce").dropna()
    assert int(years.max()) > REVENUE_OUTLOOK_DISPLAY_END_FY, (
        "the source pack itself was truncated; this branch must only clip the view"
    )


def test_clipping_leaves_fy2050_values_untouched(context, default_traces) -> None:
    """The last displayed year must be the pack's FY2050, not a recomputation."""
    pack, _ = context
    chart_rows = app._pack_table(pack, "revenue_chart_rows")
    raw = chart_rows[
        chart_rows["series_label"].astype(str).eq(SERIES)
        & pd.to_numeric(chart_rows["june_year"], errors="coerce").eq(REVENUE_OUTLOOK_DISPLAY_END_FY)
        & chart_rows["trace_name"].astype(str).eq("Current finalist Base case")
    ]
    clipped = clip_frame_to_display_horizon(raw)
    assert len(clipped) == len(raw), "FY2050 rows were dropped by the horizon clip"
    pd.testing.assert_frame_equal(
        clipped.reset_index(drop=True), raw.reset_index(drop=True), check_like=True
    )


def test_the_clip_helper_drops_only_years_past_the_horizon() -> None:
    frame = pd.DataFrame(
        {
            "june_year": [2049, 2050, 2051, 2055],
            "period": ["FY2049", "FY2050", "FY2051", "FY2055"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    kept = clip_frame_to_display_horizon(frame)
    assert kept["june_year"].tolist() == [2049, 2050]
    assert kept["value"].tolist() == [1.0, 2.0]


# ==================================================== D. expanded chart focus mode
def test_the_expand_control_is_not_part_of_the_figure_identity(context, default_traces) -> None:
    """Expanding must not change the calculation key, and so must not
    invalidate the cached figure or reset Plotly's view revision."""
    pack, signature = context
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    key = production_key()
    revision_args = (
        signature, SERIES, "june_year", FED, default_traces, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, key, (BAND_50_LAYER_ID, BAND_80_LAYER_ID),
    )
    first = app._revenue_outlook_figure_revision(*revision_args)
    second = app._revenue_outlook_figure_revision(*revision_args)
    assert first == second
    # A control that DOES change the numbers must change the revision.
    changed = app._revenue_outlook_figure_revision(
        signature, SERIES, "june_year", FED, default_traces, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, key.replace(uptake_basis="MoT VFM fast"),
        (BAND_50_LAYER_ID, BAND_80_LAYER_ID),
    )
    assert changed != first


def test_the_figure_carries_a_stable_ui_revision(context, default_view, default_traces) -> None:
    pack, signature = context
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    bands = app.cached_uncertainty_band_rows("total_nltf_net_revenue", "expand-test")
    figure = app.cached_revenue_outlook_total_path_figure(
        signature, SERIES, "FY2030", "june_year", FED, default_traces, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, production_key(), default_view["filtered_rows"],
        None, bands, (BAND_50_LAYER_ID, BAND_80_LAYER_ID),
    )
    assert figure.layout.uirevision, "no uirevision: zoom would reset on every rerun"
    assert figure.layout.selectionrevision == figure.layout.uirevision


def test_expanding_does_not_alter_a_single_plotted_value(rendered_page) -> None:
    """Same numbers collapsed and expanded - the mode is layout only."""
    before = _total_path_traces(rendered_page)
    assert before, "no Total path chart was rendered"

    rendered_page.session_state[app.REVENUE_OUTLOOK_EXPAND_CHART_KEY] = True
    rendered_page.run()
    assert not rendered_page.exception, rendered_page.exception
    after = _total_path_traces(rendered_page)
    assert after == before, "expanding the chart changed the plotted values"

    rendered_page.session_state[app.REVENUE_OUTLOOK_EXPAND_CHART_KEY] = False
    rendered_page.run()


def test_the_expand_control_exists_and_defaults_to_collapsed(rendered_page) -> None:
    labels = [str(element.label or "") for element in rendered_page.get("toggle")]
    assert any("Expand chart" in label for label in labels), labels


def test_expanding_keeps_the_same_plotly_key_and_ui_revision(rendered_page) -> None:
    """The two conditions Plotly needs to preserve a reader's zoom.

    Measured rather than assumed: the chart must come back under the SAME
    element key with the SAME uirevision after the layout size changes.
    """
    def identity(harness):
        for element in harness.get("plotly_chart"):
            spec = json.loads(element.proto.spec)
            names = [str(trace.get("name", "")) for trace in spec.get("data", [])]
            if any("Base case" in name for name in names):
                return element.key, spec.get("layout", {}).get("uirevision")
        return None, None

    key_before, revision_before = identity(rendered_page)
    assert revision_before, "the Total path chart carries no uirevision"

    rendered_page.session_state[app.REVENUE_OUTLOOK_EXPAND_CHART_KEY] = True
    rendered_page.run()
    assert not rendered_page.exception, rendered_page.exception
    key_after, revision_after = identity(rendered_page)

    rendered_page.session_state[app.REVENUE_OUTLOOK_EXPAND_CHART_KEY] = False
    rendered_page.run()

    assert key_after == key_before, (key_before, key_after)
    assert revision_after == revision_before, (revision_before, revision_after)


def test_the_rendered_chart_carries_bands_but_no_vfm_traces(rendered_page) -> None:
    """What actually reached the browser, not just what the catalogue offered."""
    traces = _total_path_traces(rendered_page)
    assert traces, "no Total path chart was rendered"
    names = " ".join(traces).casefold()
    assert "conditional modelled uncertainty" in names, names
    assert "vfm" not in names, names


# ============================ E. the uptake basis is gated with its layers
# The uptake basis is a whole-SCENARIO input, not a chart layer. Leaving VFM
# Fast/Slow selectable while their layers were hidden still let a reader run
# those compositions through the entire engine, so the pause has to cover the
# basis selector too.
PAUSED_BASES = ("MoT VFM fast", "MoT VFM slow")
# The single-view basis selector still exists, so its stale value is RESET to
# the governed default; the A/B columns select scenario traces now, so their
# old uptake keys are WITHDRAWN controls and are dropped entirely on entry.
UPTAKE_RESET_STATE_KEYS = ("revenue_outlook_ev_uptake_basis_v2",)
WITHDRAWN_UPTAKE_STATE_KEYS = ("ro_cmp_a_uptake", "ro_cmp_b_uptake")
UPTAKE_STATE_KEYS = (*UPTAKE_RESET_STATE_KEYS, *WITHDRAWN_UPTAKE_STATE_KEYS)


def test_the_public_uptake_options_exclude_fast_and_slow() -> None:
    options = app._public_uptake_basis_options()
    assert app.DEFAULT_EV_UPTAKE_MODE in options
    for basis in PAUSED_BASES:
        assert basis not in options, basis
    # The pause is narrow: the parametric approximation to VFM BASE, the custom
    # levers and the governed default all survive it.
    assert app.EV_UPTAKE_CUSTOM_OPTION in options
    assert any("parametric" in option.casefold() for option in options), options


def test_the_paused_bases_are_recognised_but_vfm_base_is_not() -> None:
    for basis in PAUSED_BASES:
        assert app.is_paused_vfm_uptake_basis(basis) is True, basis
    assert app.is_paused_vfm_uptake_basis(app.DEFAULT_EV_UPTAKE_MODE) is False
    assert (
        app.is_paused_vfm_uptake_basis(
            "Parametric approximation to VFM Base (audit sensitivity)"
        )
        is False
    )


def test_the_single_view_uptake_selector_offers_no_paused_basis(rendered_page) -> None:
    """No uptake-BASIS control may offer a paused composition.

    Scoped to the uptake-basis selectors on purpose. The Fleet Mix Explorer has
    its own "Source" control that lists MoT's published VFM 202405 Fast and
    Slow scenarios; that one is reference material - see
    test_the_fleet_mix_vfm_reference_is_display_only.
    """
    boxes = [
        element
        for element in rendered_page.get("selectbox")
        if str(element.label) == "Uptake basis"
    ]
    assert boxes, "the single view rendered no uptake-basis selector"
    for element in boxes:
        for option in getattr(element, "options", None) or []:
            assert not app.is_paused_vfm_uptake_basis(option), option
        assert not app.is_paused_vfm_uptake_basis(element.value), element.value


def test_the_fleet_mix_vfm_reference_is_display_only() -> None:
    """The Fleet Mix Explorer keeps MoT's published Fast/Slow columns.

    They are the vendored VFM 202405 extract shown side by side with the
    dashboard path, not a composition the engine runs: the dashboard column is
    always built with the governed default basis. Withdrawing them would drop
    published source material the pause was never about, so this test pins the
    distinction rather than the absence.
    """
    import inspect

    from model_dashboard import fleet_mix

    source = inspect.getsource(fleet_mix.load_dashboard_frame)
    assert "EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]" in source, (
        "the fleet-mix dashboard path no longer pins the governed default basis"
    )
    assert "VFM 202405 - Fast scenario" in fleet_mix.VFM_SOURCES


def test_compare_mode_offers_no_paused_basis_and_opens_on_base() -> None:
    """No A/B control can run a paused composition.

    Scenario B used to OPEN on VFM Fast. The comparison now selects governed
    scenario TRACES (Scenario A is the live Single scenario configuration and
    renders no selector at all), so the assertion is that the B trace selector
    offers no paused uptake basis anywhere.
    """
    from streamlit.testing.v1 import AppTest

    assert not app.is_paused_vfm_uptake_basis(
        app._comparison_scenario_defaults("b")["trace"]
    )

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    view_mode = next(
        radio for radio in harness.get("radio") if str(radio.label) == "View"
    )
    view_mode.set_value(app.REVENUE_OUTLOOK_VIEW_COMPARE)
    harness.run()
    assert not harness.exception, harness.exception

    trace_box = next(
        (
            element
            for element in harness.get("selectbox")
            if str(element.key) == "ro_cmp_b_trace"
        ),
        None,
    )
    assert trace_box is not None, "compare mode rendered no Scenario B trace selector"
    for option in getattr(trace_box, "options", None) or []:
        assert not app.is_paused_vfm_uptake_basis(option), option
    assert not app.is_paused_vfm_uptake_basis(trace_box.value), trace_box.value


@pytest.mark.parametrize("state_key", UPTAKE_RESET_STATE_KEYS)
def test_a_stale_paused_basis_is_reset_to_vfm_base(state_key: str) -> None:
    """Session state outlives a deployment; a stored Fast must not persist."""
    import streamlit as st

    st.session_state[state_key] = "MoT VFM fast"
    try:
        app._discard_withdrawn_revenue_outlook_state()
        assert st.session_state[state_key] == app.DEFAULT_EV_UPTAKE_MODE
    finally:
        st.session_state.pop(state_key, None)


@pytest.mark.parametrize("state_key", WITHDRAWN_UPTAKE_STATE_KEYS)
def test_a_stale_withdrawn_comparison_basis_is_dropped(state_key: str) -> None:
    """The A/B uptake selectors no longer exist, so their keys are removed."""
    import streamlit as st

    st.session_state[state_key] = "MoT VFM fast"
    try:
        app._discard_withdrawn_revenue_outlook_state()
        assert state_key not in st.session_state
    finally:
        st.session_state.pop(state_key, None)


def test_a_stale_paused_basis_does_not_survive_a_real_render() -> None:
    from streamlit.testing.v1 import AppTest

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    for key in UPTAKE_STATE_KEYS:
        harness.session_state[key] = "MoT VFM slow"
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception
    for key in UPTAKE_RESET_STATE_KEYS:
        assert harness.session_state[key] == app.DEFAULT_EV_UPTAKE_MODE, key
    for key in WITHDRAWN_UPTAKE_STATE_KEYS:
        with pytest.raises(KeyError):
            harness.session_state[key]


def test_no_fast_or_slow_overlay_is_computed_on_a_production_render(monkeypatch) -> None:
    """The point of the amendment: the COMPOSITION must not run either.

    Any scenario-overlay pass carrying a paused basis raises, and a default
    render - seeded with a stale Fast selection - has to complete anyway.
    """
    from streamlit.testing.v1 import AppTest

    original = app.cached_scenario_overlay_rows

    def guarded(signature, sensitivity_key, bridge_mode, ev_uptake_key, pack):
        basis = app._scenario_key(ev_uptake_key).uptake_basis
        if app.is_paused_vfm_uptake_basis(basis):
            raise AssertionError(f"a paused composition was computed: {basis!r}")
        return original(signature, sensitivity_key, bridge_mode, ev_uptake_key, pack)

    guarded.clear = getattr(original, "clear", lambda: None)
    monkeypatch.setattr(app, "cached_scenario_overlay_rows", guarded)

    harness = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    for key in UPTAKE_STATE_KEYS:
        harness.session_state[key] = "MoT VFM fast"
    harness.run()
    harness.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    harness.run()
    assert not harness.exception, harness.exception


def test_current_base_is_unmoved_by_the_uptake_gate(context, default_traces) -> None:
    """Gating the selector must not touch a single Current Base value.

    Computed with the gate closed (production) and open (the pre-amendment
    surface) under the same production key, which has always been VFM Base.
    """
    import model_dashboard.revenue_outlook_presentation_policy as policy

    pack, signature = context
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")

    def current_base() -> pd.Series:
        view = app.cached_revenue_outlook_view(
            signature, SERIES, "june_year", FED, default_traces, sensitivity,
            PED_BRIDGE_DEFAULT_MODE, production_key(), pack,
        )
        rows = view["filtered_rows"]
        base = rows[
            rows["trace_name"].astype(str).eq("Current finalist Base case")
            & ~rows.get("row_type", pd.Series("", index=rows.index))
            .astype(str)
            .eq("historical_actual")
        ].copy()
        base["_fy"] = pd.to_numeric(base["june_year"], errors="coerce")
        base = base.dropna(subset=["_fy"]).sort_values("_fy")
        return pd.Series(
            pd.to_numeric(base["value"], errors="coerce").to_numpy(),
            index=base["_fy"].astype(int).to_numpy(),
        )

    gated = current_base()
    assert not gated.empty

    previous = policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
    previous_app = app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
    policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = True
    app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = True
    app.cached_revenue_outlook_view.clear()
    try:
        ungated = current_base()
    finally:
        policy.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = previous
        app.REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = previous_app
        app.cached_revenue_outlook_view.clear()

    pd.testing.assert_series_equal(gated, ungated)


def test_the_fast_slow_backend_still_works_when_the_gate_is_open(
    context, default_traces, vfm_analyst_layers_enabled
) -> None:
    """The retained composition must still run on demand, so it can be restored."""
    pack, signature = context
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")

    assert "MoT VFM fast" in app._public_uptake_basis_options()
    paths = app.cached_vfm_scenario_paths(
        signature, SERIES, "june_year", FED, default_traces, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, app._cone_band_controls(production_key()), pack,
    )
    assert isinstance(paths, pd.DataFrame) and not paths.empty
    assert set(paths["trace_name"].astype(str)) == {
        VFM_FAST_TRACE_NAME,
        VFM_SLOW_TRACE_NAME,
    }

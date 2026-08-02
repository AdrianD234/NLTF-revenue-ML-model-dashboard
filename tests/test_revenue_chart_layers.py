"""The unified chart-layer registry and the layered Total path figure.

Three concepts share one chart and must never blur into each other:
deterministic paths, the non-probabilistic VFM structural range, and the
conditional modelled-uncertainty bands.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.revenue_chart_layers import (
    BAND_50_LAYER_ID,
    BAND_80_LAYER_ID,
    BAND_GROUP,
    LAYER_KIND_BAND,
    LAYER_KIND_ENVELOPE,
    LAYER_KIND_PATH,
    PATH_GROUP,
    VFM_ENVELOPE_LAYER_ID,
    VFM_FAST_TRACE_NAME,
    VFM_SLOW_TRACE_NAME,
    band_layer_ids,
    build_layer_catalogue,
    catalogue_frame,
    default_layer_ids,
    path_trace_names,
)
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey

ROOT = Path(__file__).resolve().parents[1]
FED = "Current planned path"
SERIES = "Total NLTF revenue"
TRACES = (
    "Actual",
    "Current finalist Base case",
    "Current finalist High population/comparison",
    "BEFU26 official",
)
ALL_BANDS = (BAND_80_LAYER_ID, VFM_ENVELOPE_LAYER_ID, BAND_50_LAYER_ID)


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


def production_key() -> RevenueScenarioComputationKey:
    return RevenueScenarioComputationKey(
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id="BEFU26",
        long_run_transition_schedule_id="balanced_structural",
        long_run_shape_vintage_id="BEFU26",
    )


@pytest.fixture(scope="module")
def context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


@pytest.fixture(scope="module")
def catalogue():
    return build_layer_catalogue(
        [*TRACES, VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME],
        default_trace_names=list(TRACES),
        uncertainty_available=True,
        envelope_available=True,
    )


@pytest.fixture(scope="module")
def figure(context):
    pack, signature = context
    key = production_key()
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    view = app.cached_revenue_outlook_view(
        signature, SERIES, "june_year", FED, TRACES, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, key, pack,
    )
    vfm = app.cached_vfm_scenario_paths(
        signature, SERIES, "june_year", FED, TRACES, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, app._cone_band_controls(key), pack,
    )
    rows = pd.concat([view["filtered_rows"], vfm], ignore_index=True, sort=False)
    bands = app.cached_uncertainty_band_rows("total_nltf_net_revenue", "test")
    return app.revenue_outlook_total_path_figure(
        rows, selected_series=SERIES, selected_fy="FY2030",
        cone_band=view["cone_band"], selected_official_trace="BEFU26 official",
        uncertainty_rows=bands, selected_band_layers=ALL_BANDS,
    )


# ---------------------------------------------------------------- registry
def test_every_required_layer_is_offered(catalogue) -> None:
    labels = {spec.label for spec in catalogue}
    for expected in (
        f"{PATH_GROUP} · Actual",
        f"{PATH_GROUP} · Current finalist Base case",
        f"{PATH_GROUP} · Current finalist High population/comparison",
        f"{PATH_GROUP} · {VFM_FAST_TRACE_NAME}",
        f"{PATH_GROUP} · {VFM_SLOW_TRACE_NAME}",
        f"{PATH_GROUP} · BEFU26 official",
        f"{BAND_GROUP} · 50% conditional modelled uncertainty",
        f"{BAND_GROUP} · 80% conditional modelled uncertainty",
        f"{BAND_GROUP} · MoT VFM fast–slow range",
    ):
        assert expected in labels, expected


def test_layer_ids_are_unique(catalogue) -> None:
    ids = [spec.layer_id for spec in catalogue]
    assert len(ids) == len(set(ids))


def test_the_draw_order_is_the_governed_z_order(catalogue) -> None:
    ranks = {spec.layer_id: spec.draw_rank for spec in catalogue}
    assert ranks[BAND_80_LAYER_ID] < ranks[VFM_ENVELOPE_LAYER_ID]
    assert ranks[VFM_ENVELOPE_LAYER_ID] < ranks[BAND_50_LAYER_ID]
    paths = [spec.draw_rank for spec in catalogue if spec.layer_kind == LAYER_KIND_PATH]
    assert min(paths) > ranks[BAND_50_LAYER_ID]


def test_only_the_uncertainty_bands_are_probabilistic(catalogue) -> None:
    for spec in catalogue:
        if spec.layer_kind == LAYER_KIND_BAND:
            assert spec.probabilistic is True, spec.layer_id
            assert "conditional" in spec.interpretation.lower()
            assert "excludes treasury-driver" in spec.interpretation.lower()
        else:
            assert spec.probabilistic is False, spec.layer_id
    envelope = next(s for s in catalogue if s.layer_kind == LAYER_KIND_ENVELOPE)
    assert "not probabilistic" in envelope.interpretation.lower()
    for banned in ("confidence interval", "credible interval"):
        assert banned not in envelope.interpretation.lower().replace(
            "not a confidence, credible or prediction interval", ""
        )


def test_layers_are_independently_selectable(catalogue) -> None:
    every = [spec.layer_id for spec in catalogue]
    for spec in catalogue:
        alone = [spec.layer_id]
        if spec.layer_kind == LAYER_KIND_PATH:
            assert path_trace_names(catalogue, alone) == [spec.trace_name]
            assert band_layer_ids(catalogue, alone) == []
        else:
            assert band_layer_ids(catalogue, alone) == [spec.layer_id]
            assert path_trace_names(catalogue, alone) == []
    # And all together.
    assert len(path_trace_names(catalogue, every)) + len(band_layer_ids(catalogue, every)) == len(every)


def test_the_defaults_are_the_agreed_opening_view(catalogue) -> None:
    defaults = set(default_layer_ids(catalogue))
    assert BAND_50_LAYER_ID in defaults and BAND_80_LAYER_ID in defaults
    # The VFM layers stay one click away rather than on by default.
    assert VFM_ENVELOPE_LAYER_ID not in defaults
    assert f"path_{VFM_FAST_TRACE_NAME}" not in defaults


def test_the_catalogue_audit_frame_is_complete(catalogue) -> None:
    frame = pd.DataFrame(catalogue_frame(catalogue))
    assert len(frame) == len(catalogue)
    for column in ("layer_id", "layer_kind", "draw_rank", "probabilistic", "interpretation"):
        assert column in frame.columns
    assert frame["interpretation"].str.len().gt(10).all()


def test_bands_are_dropped_when_the_pack_is_absent() -> None:
    catalogue = build_layer_catalogue(
        list(TRACES), default_trace_names=list(TRACES),
        uncertainty_available=False, envelope_available=True,
    )
    ids = {spec.layer_id for spec in catalogue}
    assert BAND_50_LAYER_ID not in ids and BAND_80_LAYER_ID not in ids
    assert VFM_ENVELOPE_LAYER_ID in ids


# ------------------------------------------------------------------ figure
def test_the_figure_draws_bands_beneath_every_line(figure) -> None:
    names = [str(trace.name) for trace in figure.data]
    band_positions = [
        index for index, name in enumerate(names)
        if "conditional" in name or "MoT VFM fast" in name
    ]
    line_positions = [
        index for index, name in enumerate(names)
        if index not in band_positions
    ]
    assert band_positions and line_positions
    assert max(band_positions) < min(line_positions)


def test_the_figure_z_order_matches_the_registry(figure) -> None:
    names = [str(trace.name) for trace in figure.data]
    eighty = names.index("80% conditional modelled uncertainty")
    envelope = next(i for i, n in enumerate(names) if "fast–slow range" in n)
    fifty = names.index("50% conditional modelled uncertainty")
    assert eighty < envelope < fifty


def test_each_band_contributes_exactly_one_legend_entry(figure) -> None:
    legend = [str(t.name) for t in figure.data if t.showlegend]
    for expected in (
        "80% conditional modelled uncertainty",
        "50% conditional modelled uncertainty",
        "MoT VFM fast–slow range",
    ):
        assert legend.count(expected) == 1, (expected, legend)


def test_the_bands_use_visually_distinct_fills(figure) -> None:
    fills = {
        str(t.name): t.fillcolor for t in figure.data if t.fill == "tonexty"
    }
    modelled = {k: v for k, v in fills.items() if "conditional" in k}
    envelope = {k: v for k, v in fills.items() if "fast–slow" in k}
    assert len(modelled) == 2 and len(envelope) == 1
    # One hue for the nested modelled bands, a different hue for the envelope.
    assert len({v.split(",")[0] for v in modelled.values()}) == 1
    assert set(envelope.values()).isdisjoint(set(modelled.values()))


def test_the_fifty_band_is_nested_inside_the_eighty_band_on_the_chart(figure) -> None:
    by_name = {str(t.name): t for t in figure.data}
    lower80 = list(by_name["80% conditional modelled uncertainty"].y)
    lower50 = list(by_name["50% conditional modelled uncertainty"].y)
    upper80 = list(by_name["80% conditional band upper"].y)
    upper50 = list(by_name["50% conditional band upper"].y)
    assert len(lower80) == len(lower50) > 0
    for index in range(len(lower80)):
        assert lower80[index] <= lower50[index] + 1e-9
        assert upper50[index] <= upper80[index] + 1e-9


def test_a_band_layer_can_be_switched_off_independently(context) -> None:
    pack, signature = context
    key = production_key()
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    view = app.cached_revenue_outlook_view(
        signature, SERIES, "june_year", FED, TRACES, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, key, pack,
    )
    bands = app.cached_uncertainty_band_rows("total_nltf_net_revenue", "test")
    only_fifty = app.revenue_outlook_total_path_figure(
        view["filtered_rows"], selected_series=SERIES, selected_fy="FY2030",
        cone_band=view["cone_band"], selected_official_trace="BEFU26 official",
        uncertainty_rows=bands, selected_band_layers=(BAND_50_LAYER_ID,),
    )
    names = [str(t.name) for t in only_fifty.data]
    assert "50% conditional modelled uncertainty" in names
    assert "80% conditional modelled uncertainty" not in names
    assert not any("fast–slow range" in n for n in names)

    none_selected = app.revenue_outlook_total_path_figure(
        view["filtered_rows"], selected_series=SERIES, selected_fy="FY2030",
        cone_band=view["cone_band"], selected_official_trace="BEFU26 official",
        uncertainty_rows=bands, selected_band_layers=(),
    )
    assert not any(
        "conditional" in str(t.name) or "fast–slow" in str(t.name)
        for t in none_selected.data
    )


# ------------------------------------------------------- VFM scenario paths
def test_vfm_fast_and_slow_run_through_fy2050(context) -> None:
    pack, signature = context
    key = production_key()
    paths = app.cached_vfm_scenario_paths(
        signature, SERIES, "june_year", FED, TRACES,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE, app._cone_band_controls(key), pack,
    )
    assert not paths.empty
    assert set(paths["trace_name"]) == {VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME}
    for trace, cell in paths.groupby("trace_name"):
        fy = pd.to_numeric(cell["june_year"], errors="coerce")
        assert int(fy.max()) == 2050, trace
        assert int(fy.min()) <= 2026, trace


def test_the_vfm_paths_differ_from_base_inside_the_model_window(context) -> None:
    pack, signature = context
    key = production_key()
    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    view = app.cached_revenue_outlook_view(
        signature, SERIES, "june_year", FED, TRACES, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, key, pack,
    )
    paths = app.cached_vfm_scenario_paths(
        signature, SERIES, "june_year", FED, TRACES, sensitivity,
        PED_BRIDGE_DEFAULT_MODE, app._cone_band_controls(key), pack,
    )

    def at(frame, trace, fy):
        cell = frame[
            frame["trace_name"].astype(str).eq(trace)
            & pd.to_numeric(frame["june_year"], errors="coerce").eq(fy)
        ]
        return float(pd.to_numeric(cell["value"], errors="coerce").dropna().iloc[0])

    base_2030 = at(view["filtered_rows"], "Current finalist Base case", 2030)
    fast_2030 = at(paths, VFM_FAST_TRACE_NAME, 2030)
    slow_2030 = at(paths, VFM_SLOW_TRACE_NAME, 2030)
    assert fast_2030 != pytest.approx(slow_2030), "the two VFM paths coincide at FY2030"
    assert min(fast_2030, slow_2030) <= base_2030 <= max(fast_2030, slow_2030)

    # And they stay distinct to FY2050: the common governed Light pool is
    # allocated by different exact VFM202405 shares the whole way.
    fast_2050 = at(paths, VFM_FAST_TRACE_NAME, 2050)
    slow_2050 = at(paths, VFM_SLOW_TRACE_NAME, 2050)
    assert fast_2050 != pytest.approx(slow_2050), "the VFM paths merged at FY2050"


# ------------------------------------------------------------ page contract
def test_one_multiselect_drives_every_layer() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert 'st.multiselect(\n                    "Show on chart"' in source
    assert "revenue_outlook_chart_layers" in source
    # The old per-trace checkbox popover must be gone.
    assert 'st.popover("Select legend items"' not in source
    assert "revenue_outlook_legend_item_" not in source


def test_the_runtime_never_simulates() -> None:
    """Band lookup is a filter; the pack is built offline."""
    source = inspect.getsource(app)
    for banned in ("generate_parent_factor_draws", "quantile_mapped_sample", "DRAW_COUNT"):
        assert banned not in source, banned
    assert "load_uncertainty_pack" in source


def test_the_separate_fan_card_stays_off_the_default_layout() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    primary, _, remainder = source.partition("revenue_outlook_show_fan_detail")
    assert remainder
    assert "_render_revenue_outlook_fan_card(" not in primary
    assert "st.columns([0.64, 0.36])" not in source

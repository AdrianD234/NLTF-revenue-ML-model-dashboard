from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd

from model_dashboard.light_fleet_allocation import EXTENDED_EVIDENCE_MAX_HORIZON
import pytest
from streamlit.testing.v1 import AppTest

import app
import model_dashboard.revenue_outlook as revenue_outlook_module
from model_dashboard.conflict_fuel_paths import (
    CONFLICT_FUEL_SCENARIO_LEVELS,
    conflict_scenario_name,
    conflict_trace_name,
)
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    apply_ped_bridge_mode_layer,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)

CONFLICT_SCENARIO_NAMES = tuple(
    conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)
CONFLICT_TRACE_NAMES = tuple(
    conflict_trace_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)


def _clear_governance_visibility_env(monkeypatch) -> None:
    monkeypatch.delenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, raising=False)
    for name in app.STREAMLIT_CLOUD_ENV_MARKERS:
        monkeypatch.delenv(name, raising=False)


def test_app_smoke_loads_without_exception(monkeypatch) -> None:
    """Executive mode is the default presentation profile: same pages,
    plain-English navigation titles."""
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")
    monkeypatch.delenv("NLTF_DASHBOARD_MODE", raising=False)
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    at = AppTest.from_file(str(app_path), default_timeout=60)
    at.run()

    assert not at.exception
    assert len(at.radio) >= 1
    assert at.radio[0].options == [
        "Executive Summary",
        "Model Confidence",
        "Scenario Forecasts",
        "Revenue Outlook",
        "Governance & Reproducibility",
    ]


def test_app_smoke_analyst_mode_keeps_technical_titles(monkeypatch) -> None:
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")
    monkeypatch.setenv("NLTF_DASHBOARD_MODE", "analyst")
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    at = AppTest.from_file(str(app_path), default_timeout=60)
    at.run()

    assert not at.exception
    assert at.radio[0].options == [
        "Overview",
        "Diagnostics",
        "Scenario Comparison",
        "Revenue Outlook",
        "Governance & Reproducibility",
    ]


def test_governance_page_is_visible_for_local_runs_by_default(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)

    assert app.REPRODUCIBILITY_PAGE in app.dashboard_pages()


def test_governance_page_is_hidden_for_streamlit_cloud_by_default(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")

    assert app.REPRODUCIBILITY_PAGE not in app.dashboard_pages()
    assert app.dashboard_pages() == ["Overview", "Diagnostics", "Scenario Comparison", "Revenue Outlook"]


def test_local_audit_controls_are_hidden_for_streamlit_cloud(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    assert app.should_show_local_audit_controls()

    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    assert not app.should_show_local_audit_controls()


def test_revenue_outlook_sensitivity_labels_show_actual_assumptions() -> None:
    assert app.sensitivity_option_label("fleet_efficiency", "Off") == "Off (0.0% p.a.)"
    assert app.sensitivity_option_label("fleet_efficiency", "Low") == "Low (0.5% p.a.)"
    assert app.sensitivity_option_label("fleet_efficiency", "Med") == "Med (1.0% p.a.)"
    assert app.sensitivity_option_label("fleet_efficiency", "High") == "High (1.5% p.a.)"
    assert app.sensitivity_option_label("pt_mode_shift", "Low") == "Low (0.25% p.a. from FY2030)"
    assert app.sensitivity_option_label("pt_mode_shift", "Med") == "Med (0.5% p.a. from FY2030)"
    assert app.sensitivity_option_label("pt_mode_shift", "High") == "High (1.0% p.a. from FY2030)"
    assert app.sensitivity_option_label("freight_rail_shift", "Off") == "Off (0.0% p.a.)"
    assert app.sensitivity_option_label("freight_rail_shift", "Low") == "Low (0.25% p.a. from FY2030)"
    assert app.sensitivity_option_label("freight_rail_shift", "Med") == "Med (0.5% p.a. from FY2030)"
    assert app.sensitivity_option_label("freight_rail_shift", "High") == "High (1.0% p.a. from FY2030)"
    assert app.sensitivity_option_label("demand_elasticity", "Low") == "Low: PED -0.100 / Light RUC -0.080 / Heavy RUC -0.050"
    assert app.sensitivity_option_label("demand_elasticity", "Med") == "Med: PED -0.144 / Light RUC -0.120 / Heavy RUC -0.100"
    assert app.sensitivity_option_label("demand_elasticity", "High") == "High: PED -0.240 / Light RUC -0.200 / Heavy RUC -0.200"


def test_revenue_outlook_lazy_table_uses_explicit_toggle(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    calls: list[tuple[str, bool, str]] = []
    captions: list[str] = []

    def fake_toggle(label: str, *, value: bool, key: str) -> bool:
        calls.append((label, value, key))
        return value

    monkeypatch.setattr(app.st, "toggle", fake_toggle)
    monkeypatch.setattr(app.st, "caption", lambda text: captions.append(str(text)))

    assert not app.revenue_outlook_lazy_table("Show expensive audit", "lazy_key", caption="not yet")
    assert app.revenue_outlook_lazy_table("Show expensive audit", "lazy_key_open", default=True)
    assert calls == [("Show expensive audit", False, "lazy_key"), ("Show expensive audit", True, "lazy_key_open")]
    assert captions == ["not yet"]


def test_revenue_outlook_lazy_table_is_hidden_on_streamlit_cloud(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    calls: list[str] = []
    captions: list[str] = []

    monkeypatch.setattr(app.st, "toggle", lambda *args, **kwargs: calls.append("toggle"))
    monkeypatch.setattr(app.st, "caption", lambda text: captions.append(str(text)))

    assert not app.revenue_outlook_lazy_table("Show expensive audit", "cloud_lazy_key", caption="hidden caption")
    assert app.revenue_outlook_lazy_table("Show default-on audit", "cloud_default_key", default=True, caption="hidden caption")
    assert calls == []
    assert captions == []


def test_revenue_outlook_heavy_sections_are_lazy_guarded_in_renderer() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    guarded_markers = {
        "revenue_outlook_show_scenario_role_contract": 'scenario_role_contract = _pack_table(pack, "scenario_role_contract")',
        "revenue_outlook_show_runtime_cutoff_audit": 'runtime_cutoff_audit = _pack_table(pack, "runtime_cutoff_audit")',
        "revenue_outlook_show_sensitivity_impact_audit": "cached_revenue_outlook_sensitivity_audit(",
        "revenue_outlook_show_ped_bridge_diagnostics": 'ped_bridge_shape_fit_metrics = _pack_table(pack, "ped_bridge_shape_fit_metrics")',
        "revenue_outlook_show_ev_phev_drift_audit": 'ev_phev_ped_light_drift_assumptions = _pack_table(pack, "ev_phev_ped_light_drift_assumptions")',
        "revenue_outlook_show_ev_phev_split_audit": 'ev_phev_split_assumptions = _pack_table(pack, "ev_phev_split_assumptions")',
        "revenue_outlook_show_line_reconciliation": "cached_revenue_line_reconciliation_view(",
    }
    for lazy_key, marker in guarded_markers.items():
        marker_index = source.index(marker)
        assert source.rfind(lazy_key, 0, marker_index) >= 0, f"{marker} is not guarded by {lazy_key}"


def test_revenue_outlook_selector_metadata_is_precomputed() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)

    selectors = app.cached_revenue_outlook_selectors(signature, pack)

    assert "Total NLTF revenue" in selectors["stream_options"]
    assert "Light petrol VKT" in selectors["stream_options"]
    assert (
        app._revenue_outlook_series_metric_type(
            pack.revenue_chart_rows,
            "Light petrol VKT",
        )
        == "activity"
    )
    assert "Current planned path" in selectors["fed_path_options"]
    assert "FY2031" in selectors["fy_options"]
    assert selectors["stack_fy_bounds"][0] <= 2025 <= selectors["stack_fy_bounds"][1]
    assert selectors["sensitivity_labels"]["fleet_efficiency"]["High"] == "High (1.5% p.a.)"
    assert selectors["sensitivity_labels"]["pt_mode_shift"]["High"] == "High (1.0% p.a. from FY2030)"
    assert selectors["sensitivity_labels"]["freight_rail_shift"]["High"] == "High (1.0% p.a. from FY2030)"
    assert selectors["sensitivity_labels"]["demand_elasticity"]["Med"] == "Med: PED -0.144 / Light RUC -0.120 / Heavy RUC -0.100"
    assert set(CONFLICT_TRACE_NAMES) <= set(selectors["trace_options"])
    default_traces = app._revenue_outlook_default_traces(selectors["trace_options"])
    assert conflict_trace_name("medium") in default_traces
    assert conflict_trace_name("low") not in default_traces
    assert conflict_trace_name("high") not in default_traces


def test_revenue_outlook_default_sensitivity_view_uses_fast_path_and_preserves_values() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")

    if hasattr(app.cached_revenue_outlook_view, "clear"):
        app.cached_revenue_outlook_view.clear()
    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )

    expected = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
    )
    assert view["sensitivity_fast_path"] is True
    assert view["sensitivity_impact_audit"].empty
    assert view["line_reconciliation"].empty
    assert view["revenue_formula_residuals"].empty
    assert view["revenue_stack_components"].empty
    non_fuel = view["chart_rows"][
        ~view["chart_rows"]["scenario_name"].astype(str).isin(CONFLICT_SCENARIO_NAMES)
    ]
    # The view applies the governed official-vintage filter (uptake-key slots
    # 6/7); with no selection supplied it falls back to the pack's default
    # comparator, so the raw pack must be filtered the same way to compare.
    official_scenario, official_overlay = app._official_vintage_filter_for_key(
        (app.EV_UPTAKE_GOVERNED_OPTION, ())
    )
    expected_chart_rows = app._filter_official_vintage_rows(
        expected["chart_rows"], official_scenario, official_overlay
    )
    assert len(non_fuel) == len(expected_chart_rows)
    assert set(view["chart_rows"]["trace_name"].astype(str)) >= set(CONFLICT_TRACE_NAMES)
    conflict_input_audit = view["conflict_fuel_input_audit"]
    assert set(conflict_input_audit["scenario_name"].astype(str)) == set(
        CONFLICT_SCENARIO_NAMES
    )
    assert set(conflict_input_audit["severity"].astype(str)) == set(
        CONFLICT_FUEL_SCENARIO_LEVELS
    )
    assert set(conflict_input_audit["stream"].astype(str)) == {
        "PED",
        "LIGHT_RUC",
        "HEAVY_RUC",
    }
    assert (
        conflict_input_audit.groupby(["scenario_name", "stream"])[
            "canonical_period"
        ].nunique()
        == 20
    ).all()
    assert not conflict_input_audit["fed_12c_embedded"].fillna(True).astype(bool).any()
    for key, value_column in [
        ("revenue_bridge_components", "component_value"),
        ("future_revenue_forecasts", "revenue_forecast_nzd"),
    ]:
        assert pd.to_numeric(view[key][value_column], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(expected[key][value_column], errors="coerce").to_numpy(),
            abs=0,
        )

    detail = app.cached_revenue_outlook_detail_frames(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )
    for key, value_column in [
        ("line_reconciliation", "value"),
        ("revenue_stack_components", "value"),
    ]:
        assert not detail[key].empty
        assert pd.to_numeric(detail[key][value_column], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(expected[key][value_column], errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )


def test_revenue_outlook_default_primary_view_does_not_build_derived_frames(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")

    def fail_derived_frame(*args, **kwargs):
        raise AssertionError("default primary Revenue Outlook view should not build derived audit frames")

    monkeypatch.setattr(revenue_outlook_module, "revenue_formula_residual_frame", fail_derived_frame)
    monkeypatch.setattr(revenue_outlook_module, "revenue_stack_components_frame", fail_derived_frame)
    if hasattr(app.cached_revenue_outlook_view, "clear"):
        app.cached_revenue_outlook_view.clear()

    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )

    assert view["sensitivity_fast_path"] is True
    assert view["line_reconciliation"].empty
    assert view["revenue_formula_residuals"].empty
    assert view["revenue_stack_components"].empty


def test_revenue_outlook_ped_bridge_detail_does_not_build_stack_or_formula(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)

    def fail_derived_frame(*args, **kwargs):
        raise AssertionError("PED bridge diagnostics should not build formula or stack detail frames")

    monkeypatch.setattr(revenue_outlook_module, "revenue_formula_residual_frame", fail_derived_frame)
    monkeypatch.setattr(revenue_outlook_module, "revenue_stack_components_frame", fail_derived_frame)
    if hasattr(app.cached_revenue_outlook_ped_bridge_detail, "clear"):
        app.cached_revenue_outlook_ped_bridge_detail.clear()

    detail = app.cached_revenue_outlook_ped_bridge_detail(
        signature,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )

    assert not detail["ped_revenue_bridge_audit"].empty
    assert not detail["ped_bridge_mode_impact_audit"].empty


def test_revenue_outlook_line_detail_default_does_not_build_stack(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")

    def fail_stack_frame(*args, **kwargs):
        raise AssertionError("Line reconciliation detail should not build stack components")

    monkeypatch.setattr(revenue_outlook_module, "revenue_stack_components_frame", fail_stack_frame)
    if hasattr(app.cached_revenue_outlook_line_detail_frames, "clear"):
        app.cached_revenue_outlook_line_detail_frames.clear()

    detail = app.cached_revenue_outlook_line_detail_frames(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )

    assert not detail["line_reconciliation"].empty
    assert not detail["revenue_formula_residuals"].empty
    assert "revenue_stack_components" not in detail


def test_revenue_line_reconciliation_view_cache_matches_direct_table() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    selectors = app.cached_revenue_outlook_selectors(signature, pack)
    detail = app.cached_revenue_outlook_line_detail_frames(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )
    source_paths = tuple(str(value) for value in selectors["line_source_options"][:2])
    sections = tuple(str(value) for value in selectors["line_section_options"])
    fy_min, fy_max = selectors["line_fy_bounds"]
    fy_range = (max(fy_min, 2025), min(fy_max, 2035))

    if hasattr(app.cached_revenue_line_reconciliation_view, "clear"):
        app.cached_revenue_line_reconciliation_view.clear()
    cached_filtered, cached_display = app.cached_revenue_line_reconciliation_view(
        signature,
        source_paths,
        sections,
        fy_range,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        detail["line_reconciliation"],
    )
    direct_filtered = app._filter_revenue_line_reconciliation(
        detail["line_reconciliation"],
        source_paths=list(source_paths),
        sections=list(sections),
        fy_range=fy_range,
    )
    direct_display = app._revenue_line_reconciliation_display_table(direct_filtered)

    pd.testing.assert_frame_equal(cached_filtered.reset_index(drop=True), direct_filtered.reset_index(drop=True))
    pd.testing.assert_frame_equal(cached_display.reset_index(drop=True), direct_display.reset_index(drop=True))


def test_revenue_outlook_default_sensitivity_audit_materializes_lazily() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")

    if hasattr(app.cached_revenue_outlook_sensitivity_audit, "clear"):
        app.cached_revenue_outlook_sensitivity_audit.clear()
    audit = app.cached_revenue_outlook_sensitivity_audit(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )

    assert not audit.empty
    assert audit["selected_fleet_efficiency"].astype(str).eq("Off").all()
    assert audit["selected_pt_mode_shift"].astype(str).eq("Off").all()
    assert audit["selected_freight_rail_shift"].astype(str).eq("Off").all()
    assert audit["selected_demand_elasticity"].astype(str).eq("Off").all()


def test_revenue_outlook_freight_rail_shift_key_reaches_sensitivity_layer() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Med")
    assert not app._is_default_sensitivity_key(sensitivity_key)

    if hasattr(app.cached_revenue_outlook_sensitivity_audit, "clear"):
        app.cached_revenue_outlook_sensitivity_audit.clear()
    audit = app.cached_revenue_outlook_sensitivity_audit(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )

    assert not audit.empty
    assert audit["selected_freight_rail_shift"].astype(str).eq("Med").all()
    assert audit["selected_pt_mode_shift"].astype(str).eq("Off").all()
    heavy_km = audit[
        audit["series_id"].astype(str).eq("heavy_ruc_net_km")
        & pd.to_numeric(audit["FY"], errors="coerce").ge(2030)
    ]
    assert not heavy_km.empty
    assert pd.to_numeric(heavy_km["delta"], errors="coerce").lt(0).all()
    light_km = audit[audit["series_id"].astype(str).eq("light_ruc_net_km")]
    assert pd.to_numeric(light_km["delta"], errors="coerce").abs().max() == pytest.approx(0.0, abs=0)


def test_revenue_outlook_sensitivity_audit_does_not_build_residual_or_stack(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Med", "Med", "Med")

    def fail_derived_frame(*args, **kwargs):
        raise AssertionError("Sensitivity audit should not build formula or stack detail frames")

    monkeypatch.setattr(revenue_outlook_module, "revenue_formula_residual_frame", fail_derived_frame)
    monkeypatch.setattr(revenue_outlook_module, "revenue_stack_components_frame", fail_derived_frame)
    if hasattr(app.cached_revenue_outlook_sensitivity_audit, "clear"):
        app.cached_revenue_outlook_sensitivity_audit.clear()

    audit = app.cached_revenue_outlook_sensitivity_audit(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    )

    assert not audit.empty
    assert audit["selected_fleet_efficiency"].astype(str).eq("Med").all()
    assert audit["selected_pt_mode_shift"].astype(str).eq("Med").all()
    assert audit["selected_demand_elasticity"].astype(str).eq("Med").all()


def test_revenue_outlook_sensitivity_audit_matches_full_layer() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Med", "Med", "Med")

    bridge_frames = app._bridge_mode_frames_for_pack(
        pack,
        PED_BRIDGE_DEFAULT_MODE,
        include_derived_frames=True,
    )
    expected = app._apply_sensitivity_for_key(
        bridge_frames,
        app._pack_table(pack, "sensitivity_config", revenue_outlook_module.sensitivity_config_frame()),
        sensitivity_key,
    )["sensitivity_impact_audit"].reset_index(drop=True)
    if hasattr(app.cached_revenue_outlook_sensitivity_audit, "clear"):
        app.cached_revenue_outlook_sensitivity_audit.clear()
    actual = app.cached_revenue_outlook_sensitivity_audit(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        pack,
    ).reset_index(drop=True)

    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=1e-9, rtol=1e-12)


def test_revenue_outlook_default_figure_matches_uncached_path() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")

    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )
    overlay_rows, _, _, _, _ = app.cached_scenario_overlay_rows(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )
    # The cached view applies the governed official-vintage filter before
    # filtering rows; the hand-rolled uncached path must mirror that step or it
    # compares a single-vintage figure against an all-vintage one.
    official_scenario, official_overlay = app._official_vintage_filter_for_key(
        (app.EV_UPTAKE_GOVERNED_OPTION, ())
    )
    overlay_rows = app._filter_official_vintage_rows(
        overlay_rows, official_scenario, official_overlay
    )
    expected_rows = app._filter_revenue_outlook_rows(
        overlay_rows,
        time_grain="june_year",
        stream_labels=["Total NLTF revenue"],
        fed_paths=["Current planned path"],
        trace_names=list(traces),
    )

    cached_fig = app.revenue_outlook_total_path_figure(
        view["filtered_rows"], selected_series="Total NLTF revenue", selected_fy="FY2031"
    )
    expected_fig = app.revenue_outlook_total_path_figure(
        expected_rows, selected_series="Total NLTF revenue", selected_fy="FY2031"
    )

    assert [trace.name for trace in cached_fig.data] == [trace.name for trace in expected_fig.data]
    for cached_trace, expected_trace in zip(cached_fig.data, expected_fig.data):
        assert list(cached_trace.x) == list(expected_trace.x)
        assert pd.to_numeric(pd.Series(cached_trace.y), errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(pd.Series(expected_trace.y), errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )


def test_revenue_outlook_primary_hover_is_compact_and_billion_scaled() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )
    fig = app.revenue_outlook_total_path_figure(view["filtered_rows"], selected_series="Total NLTF revenue", selected_fy="FY2031")
    assert fig.layout.yaxis.title.text == "$b nominal ex GST"
    by_name = {trace.name: trace for trace in fig.data}
    base_trace = by_name["Current finalist Base case"]
    assert max(float(value) for value in base_trace.y) < 20
    assert str(base_trace.customdata[0][0]) == "$b"
    hovertemplate = str(base_trace.hovertemplate)
    assert "%{x}" not in hovertemplate
    for forbidden in ["Bridge status", "forecast:", "actual:", "PED bridge", "forecast_quarters"]:
        assert forbidden not in hovertemplate
    marker_shapes = {(str(shape.x0), str(shape.line.dash)) for shape in fig.layout.shapes or []}
    # The history/forecast boundary sits on the seam between the last actual
    # (FY2025) and the first forecast category, expressed as a numeric
    # category coordinate ending in .5.
    dash_x = [float(x) for x, dash in marker_shapes if dash == "dash"]
    assert len(dash_x) == 1 and dash_x[0] % 1 == 0.5
    assert ("FY2031", "dot") in marker_shapes


def test_revenue_outlook_composition_axis_is_bounded_to_displayed_years() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    selectors = app.cached_revenue_outlook_selectors(signature, pack)
    source = selectors["stack_source_options"][0]
    mode = selectors["stack_mode_options"][0]
    sections = tuple(section for section in ["RUC", "FED", "MVR", "TUC"] if section in selectors["stack_section_options"])
    fy_range = tuple(selectors["stack_fy_bounds"])
    overlays = tuple(app._revenue_stack_default_overlays(mode, selectors["stack_overlay_options"]))
    chart_stack = app.cached_revenue_outlook_composition_stack(
        signature,
        source,
        mode,
        sections,
        fy_range,
        overlays,
        tuple(selectors["stack_section_options"]),
        app.selected_sensitivity_key("Off", "Off", "Off"),
        PED_BRIDGE_DEFAULT_MODE,
        pack.revenue_stack_components,
    )
    fig = app.revenue_outlook_composition_figure(
        chart_stack,
        source_path=source,
        composition_mode=mode,
        detail_level=list(app.REVENUE_STACK_DETAIL_LEVELS)[0],
        overlays=list(overlays),
    )
    years = pd.to_numeric(chart_stack["FY"], errors="coerce").dropna()
    assert fig.layout.xaxis.range == (int(years.min()) - 0.5, int(years.max()) + 0.5)
    assert fig.layout.xaxis.tick0 == int(years.min())
    assert fig.layout.yaxis.title.text == "$b nominal ex GST"


def test_revenue_outlook_visible_figures_materialize_through_cache() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )
    if hasattr(app.cached_revenue_outlook_total_path_figure, "clear"):
        app.cached_revenue_outlook_total_path_figure.clear()
    if hasattr(app.cached_revenue_outlook_fan_figure, "clear"):
        app.cached_revenue_outlook_fan_figure.clear()

    cached_total = app.cached_revenue_outlook_total_path_figure(
        signature,
        "Total NLTF revenue",
        "FY2031",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        view["filtered_rows"],
    )
    direct_total = app.revenue_outlook_total_path_figure(
        view["filtered_rows"], selected_series="Total NLTF revenue", selected_fy="FY2031"
    )
    cached_fan, cached_caption = app.cached_revenue_outlook_fan_figure(
        signature,
        "Total NLTF revenue",
        "Current planned path",
        app.FAN_SOURCE_AUTO,
        pack.fan_band_rows,
        pack.fan_availability,
    )
    direct_fan = app.revenue_outlook_uncertainty_fan_figure(
        pack.fan_band_rows,
        fan_availability=pack.fan_availability,
        selected_series="Total NLTF revenue",
        fan_source=app.FAN_SOURCE_AUTO,
        selected_fed_path="Current planned path",
    )

    assert [trace.name for trace in cached_total.data] == [trace.name for trace in direct_total.data]
    assert [trace.name for trace in cached_fan.data] == [trace.name for trace in direct_fan.data]
    assert cached_caption == app._revenue_outlook_fan_caption(pack.fan_availability, "Total NLTF revenue", app.FAN_SOURCE_AUTO)[:220]


def test_revenue_outlook_selected_fy_figures_materialize_through_cache() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )
    if hasattr(app.cached_revenue_outlook_selected_fy_figures, "clear"):
        app.cached_revenue_outlook_selected_fy_figures.clear()

    cached_component, cached_split = app.cached_revenue_outlook_selected_fy_figures(
        signature,
        "FY2031",
        "Current planned path",
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        view["revenue_bridge_components"],
    )
    direct_component = app.revenue_outlook_component_figure(
        view["revenue_bridge_components"],
        selected_fy="FY2031",
        selected_fed_path="Current planned path",
    )
    direct_split = app.revenue_outlook_split_figure(
        view["revenue_bridge_components"],
        selected_fy="FY2031",
        selected_fed_path="Current planned path",
    )

    assert [trace.type for trace in cached_component.data] == [trace.type for trace in direct_component.data]
    assert [trace.type for trace in cached_split.data] == [trace.type for trace in direct_split.data]
    assert [tuple(trace.x) for trace in cached_component.data] == [tuple(trace.x) for trace in direct_component.data]
    for cached_trace, direct_trace in zip(cached_component.data, direct_component.data, strict=True):
        assert pd.to_numeric(pd.Series(cached_trace.y), errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(pd.Series(direct_trace.y), errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )
    assert [tuple(trace.labels) for trace in cached_split.data] == [tuple(trace.labels) for trace in direct_split.data]
    for cached_trace, direct_trace in zip(cached_split.data, direct_split.data, strict=True):
        assert pd.to_numeric(pd.Series(cached_trace.values), errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(pd.Series(direct_trace.values), errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )


def test_revenue_outlook_composition_stack_and_figure_cache_match_direct_builder() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    selectors = app.cached_revenue_outlook_selectors(signature, pack)
    detail = app.cached_revenue_outlook_detail_frames(signature, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, pack)
    stack_components = detail["revenue_stack_components"]
    stack_source = selectors["stack_source_options"][0]
    stack_mode = selectors["stack_mode_options"][0]
    stack_section_options = tuple(str(value) for value in selectors["stack_section_options"])
    stack_sections = tuple(section for section in ("RUC", "FED", "MVR", "TUC") if section in stack_section_options)
    if not stack_sections:
        stack_sections = stack_section_options
    fy_range = (2025, 2035)
    overlays = tuple(app._revenue_stack_default_overlays(stack_mode, selectors["stack_overlay_options"]))

    direct_filtered = app._filter_revenue_stack_components(
        stack_components,
        source_path=stack_source,
        composition_mode=stack_mode,
        sections=list(stack_sections),
        fy_range=fy_range,
    )
    direct_chart_stack = direct_filtered
    if overlays:
        direct_overlay = app._filter_revenue_stack_components(
            stack_components,
            source_path=stack_source,
            composition_mode=stack_mode,
            sections=list(stack_section_options),
            fy_range=fy_range,
        )
        direct_overlay = direct_overlay[
            direct_overlay.get("stack_role", pd.Series("", index=direct_overlay.index)).astype(str).eq("aggregate_overlay")
            & direct_overlay.get("line_label", pd.Series("", index=direct_overlay.index)).astype(str).isin(overlays)
        ].copy()
        if not direct_overlay.empty:
            direct_chart_stack = pd.concat([direct_filtered, direct_overlay], ignore_index=True, sort=False)

    if hasattr(app.cached_revenue_outlook_composition_stack, "clear"):
        app.cached_revenue_outlook_composition_stack.clear()
    if hasattr(app.cached_revenue_outlook_composition_figure, "clear"):
        app.cached_revenue_outlook_composition_figure.clear()
    if hasattr(app.cached_revenue_outlook_composition_table_view, "clear"):
        app.cached_revenue_outlook_composition_table_view.clear()
    cached_stack = app.cached_revenue_outlook_composition_stack(
        signature,
        stack_source,
        stack_mode,
        stack_sections,
        fy_range,
        overlays,
        stack_section_options,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        stack_components,
    )
    pd.testing.assert_frame_equal(
        cached_stack.reset_index(drop=True),
        direct_chart_stack.reset_index(drop=True),
        check_dtype=False,
    )

    cached_fig = app.cached_revenue_outlook_composition_figure(
        signature,
        stack_source,
        stack_mode,
        app.REVENUE_STACK_DETAIL_CLEAN,
        stack_sections,
        fy_range,
        overlays,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        cached_stack,
    )
    direct_fig = app.revenue_outlook_composition_figure(
        direct_chart_stack,
        source_path=stack_source,
        composition_mode=stack_mode,
        detail_level=app.REVENUE_STACK_DETAIL_CLEAN,
        overlays=list(overlays),
    )

    assert [trace.name for trace in cached_fig.data] == [trace.name for trace in direct_fig.data]
    assert [tuple(trace.x) for trace in cached_fig.data] == [tuple(trace.x) for trace in direct_fig.data]
    for cached_trace, direct_trace in zip(cached_fig.data, direct_fig.data, strict=True):
        assert pd.to_numeric(pd.Series(cached_trace.y), errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(pd.Series(direct_trace.y), errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )

    cached_gap, cached_table = app.cached_revenue_outlook_composition_table_view(
        signature,
        stack_source,
        stack_mode,
        stack_sections,
        fy_range,
        overlays,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        cached_stack,
    )
    assert cached_gap == app._revenue_stack_gap_banner(direct_chart_stack)
    pd.testing.assert_frame_equal(
        cached_table.reset_index(drop=True),
        app._revenue_stack_components_display_table(direct_chart_stack).reset_index(drop=True),
        check_dtype=False,
    )


def test_revenue_outlook_ev_phev_audit_views_cache_match_direct_builders() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    manifest = pack.manifest if isinstance(pack.manifest, dict) else {}

    drift = app._pack_table(pack, "ev_phev_ped_light_drift_assumptions")
    drift_manifest = manifest.get("ev_phev_ped_light_drift_assumptions") or {}
    mode_values = drift.get("lambda_mode", pd.Series(dtype=str)).dropna().astype(str).drop_duplicates().tolist()
    ordered_modes = [mode for mode in ["optimized", "fixed_light_only", "fixed_ped_only", "mbu_ratio"] if mode in mode_values]
    default_mode = str(drift_manifest.get("default_lambda_mode") or "optimized")
    selected_mode = default_mode if default_mode in (ordered_modes or mode_values) else (ordered_modes or mode_values)[0]

    if hasattr(app.cached_revenue_outlook_ev_phev_drift_view, "clear"):
        app.cached_revenue_outlook_ev_phev_drift_view.clear()
    if hasattr(app.cached_revenue_outlook_ev_phev_split_display, "clear"):
        app.cached_revenue_outlook_ev_phev_split_display.clear()

    cached_drift, cached_drift_display = app.cached_revenue_outlook_ev_phev_drift_view(
        signature,
        selected_mode,
        drift,
    )
    direct_drift = drift[
        drift.get("lambda_mode", pd.Series("", index=drift.index)).astype(str).eq(str(selected_mode))
    ].copy()
    direct_drift_display = app._ev_phev_ped_light_drift_display_table(direct_drift)
    pd.testing.assert_frame_equal(cached_drift.reset_index(drop=True), direct_drift.reset_index(drop=True), check_dtype=False)
    pd.testing.assert_frame_equal(
        cached_drift_display.reset_index(drop=True),
        direct_drift_display.reset_index(drop=True),
        check_dtype=False,
    )

    split = app._pack_table(pack, "ev_phev_split_assumptions")
    cached_split_display = app.cached_revenue_outlook_ev_phev_split_display(signature, split)
    direct_split_display = app._ev_phev_split_assumptions_display_table(split)
    pd.testing.assert_frame_equal(
        cached_split_display.reset_index(drop=True),
        direct_split_display.reset_index(drop=True),
        check_dtype=False,
    )


def test_revenue_outlook_activity_figure_cache_matches_direct_builder() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=root)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, root)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    selectors = app.cached_revenue_outlook_selectors(signature, pack)
    traces = tuple(
        trace
        for trace in selectors["trace_options"]
        if trace in ("Actual", "MBU26 official", "Current finalist Base case", "Current finalist High population/comparison")
    )
    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        (app.EV_UPTAKE_GOVERNED_OPTION, ()),
        pack,
    )

    if hasattr(app.cached_revenue_outlook_activity_figure, "clear"):
        app.cached_revenue_outlook_activity_figure.clear()
    cached_fig = app.cached_revenue_outlook_activity_figure(
        signature,
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        view["chart_rows"],
    )
    direct_frames = []
    for series_label in (
        "Light petrol VKT",
        "PED VKT per capita",
        "PED volume",
        "Light RUC net km",
        "Heavy RUC net km",
    ):
        selected, _ = app._filter_series_rows_with_fallback(
            view["chart_rows"],
            series_label,
            "june_year",
            "Current planned path",
            traces,
        )
        if not selected.empty:
            direct_frames.append(selected)
    direct_rows = pd.concat(direct_frames, ignore_index=True, sort=False)
    direct_fig = app.revenue_outlook_figure(direct_rows, metric_type="activity")

    assert [trace.name for trace in cached_fig.data] == [trace.name for trace in direct_fig.data]
    assert [tuple(trace.x) for trace in cached_fig.data] == [tuple(trace.x) for trace in direct_fig.data]
    for cached_trace, direct_trace in zip(cached_fig.data, direct_fig.data, strict=True):
        assert pd.to_numeric(pd.Series(cached_trace.y), errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(pd.Series(direct_trace.y), errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )

    quarterly_petrol, used_fallback = app._filter_series_rows_with_fallback(
        view["chart_rows"],
        "Light petrol VKT",
        "quarterly",
        "Current planned path",
        traces,
    )
    assert used_fallback
    base_petrol = quarterly_petrol[
        quarterly_petrol["trace_name"].astype(str).eq("Current finalist Base case")
    ]
    # 100 quarters was the pre-policy full source horizon. The decision-facing
    # path now stops at H20; the 100-quarter source horizon is retained as
    # non-decision-facing evidence in raw_quarterly_forecast_audit.
    assert len(base_petrol) == EXTENDED_EVIDENCE_MAX_HORIZON
    assert set(base_petrol["series_id"].astype(str)) == {"light_petrol_vkt"}
    assert set(base_petrol["data_scope"].astype(str)).issubset(
        {
            "quarterly_disaggregated_from_annual",
            "quarterly_disaggregated_from_annual_fed_policy",
        }
    )
    annual_petrol = view["chart_rows"][
        view["chart_rows"]["trace_name"].astype(str).eq("Current finalist Base case")
        & view["chart_rows"]["series_id"].astype(str).eq("light_petrol_vkt")
        & view["chart_rows"]["time_grain"].astype(str).eq("june_year")
    ].set_index("june_year")["value"]
    for fy in range(2026, 2031):
        quarter_total = pd.to_numeric(
            base_petrol.loc[
                pd.to_numeric(base_petrol["june_year"], errors="coerce").eq(fy),
                "value",
            ],
            errors="coerce",
        ).sum()
        assert quarter_total == pytest.approx(float(annual_petrol.at[fy]), abs=1e-8)


def test_revenue_outlook_activity_branch_uses_cached_figure() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    start = source.index('"Show Activity and volume outlook"')
    end = source.index('"Show Revenue bridge detail"')
    activity_branch = source[start:end]
    assert "cached_revenue_outlook_activity_figure(" in activity_branch
    assert "revenue_outlook_figure(activity_rows" not in activity_branch
    cached_source = inspect.getsource(app.cached_revenue_outlook_activity_figure)
    assert "_filter_series_rows_with_fallback(" in cached_source


def test_revenue_outlook_composition_branch_uses_cached_stack_for_table() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    start = source.index('st.markdown("<div class=\'page5-panel-title\'>Revenue composition over time</div>"')
    end = source.index('"Show EV/PHEV PED-Light migration audit"')
    composition_branch = source[start:end]
    assert "Show Revenue composition over time" not in source
    assert "revenue_outlook_show_composition" not in source
    assert "filtered_stack" not in composition_branch
    assert "dataframe_download(chart_stack" in composition_branch
    assert "cached_revenue_outlook_composition_table_view(" in composition_branch
    assert "_revenue_stack_components_display_table(chart_stack)" not in composition_branch
    assert "cached_revenue_outlook_composition_stack(" in composition_branch
    # Source-specific FY bounds: derived AFTER the source selectbox, with
    # session-state clamping on source change, so MBU26 can never inherit
    # the Current FY2030 cutoff.
    assert "_revenue_line_fy_bounds(" in composition_branch
    assert 'selector_options["stack_fy_bounds"]' not in composition_branch
    assert "revenue_stack_fy_range_source" in composition_branch
    assert "stack_fy_default_end = min(int(stack_fy_max), 2050)" in composition_branch


def test_revenue_outlook_page_does_not_render_summary_kpi_cards() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "_revenue_outlook_summary_cards(" not in source
    assert "kpi_grid(revenue_kpis)" not in source
    # The fan card is still reachable, but behind an explicit request: the
    # Total path chart now carries the MoT VFM Fast-Slow range full width.
    assert "_render_revenue_outlook_fan_card(" in source
    assert "revenue_outlook_show_fan_detail" in source
    assert "st.columns([0.64, 0.36])" not in source
    assert "revenue_outlook_sensitivity_demand_elasticity" not in source
    assert "revenue_outlook_sensitivity_cost_ratio" not in source
    assert '"Traces"' not in source
    assert "revenue_outlook_traces" not in source
    # One unified "Show on chart" multiselect replaced the per-trace popover.
    assert "Show on chart" in source
    assert "revenue_outlook_chart_layers" in source
    assert 'st.popover("Select legend items"' not in source


def test_revenue_outlook_cloud_hides_debug_toggles_and_shows_full_composition(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    pack_dir = Path(__file__).resolve().parents[1] / CURRENT_REVENUE_OUTLOOK_DIR
    pack = load_revenue_outlook_pack(pack_dir, repo_root=Path(__file__).resolve().parents[1])
    assert pack is not None
    selectors = app.cached_revenue_outlook_selectors(revenue_outlook_signature(pack_dir, Path(__file__).resolve().parents[1]), pack)

    # 120s matches _run_revenue_outlook_page, the module's own convention for
    # this page. A cold-cache Revenue Outlook render measures ~103s, so the 90s
    # this test uniquely used was below the page's actual cost and passed only
    # on a warm cache. Measured identically at the pre-closure commit, so this
    # is a pre-existing marginal timeout, not a regression: no governed value
    # tolerance is involved.
    at = AppTest.from_file(str(app_path), default_timeout=120)
    at.run()
    at.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    at.run()

    assert not at.exception
    # Debug toggles stay hidden on cloud. The two 12c controls are explicit
    # three-state selectors rather than ambiguous ON/OFF toggles.
    #
    # "Expand chart" is a presentation control: it gives the total path chart a
    # near-full-height workspace and changes no plotted value.
    #
    # The last two are governance detail surfaces, not debug controls, and are
    # deliberately available on cloud: they are how the empirical fan's source
    # data stays reachable now that the separate fan card no longer renders by
    # default. Both default to off, so neither is constructed unless a reader
    # asks for it. The MoT VFM Fast-Slow range audit is absent because that
    # analyst layer is paused - see REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS.
    assert [(toggle.label, toggle.key) for toggle in at.toggle] == [
        ("Freight rail shift", "revenue_outlook_sensitivity_freight_rail_toggle"),
        ("Move petrol fleet to e-RUC", "revenue_outlook_eruc_toggle"),
        ("Expand chart", "revenue_outlook_expand_chart"),
        ("Show forecast-uncertainty fan detail", "revenue_outlook_show_fan_detail"),
        ("Show modelled-uncertainty audit", "revenue_outlook_show_uncertainty_audit"),
    ]
    assert not any(toggle.value for toggle in at.toggle[2:]), (
        "the detail surfaces must default to off"
    )
    policy_selectors = {
        selectbox.key: selectbox
        for selectbox in at.selectbox
        if selectbox.key
        in {
            "revenue_outlook_fed_policy_state",
            "revenue_outlook_mbu_fed_policy_state",
            "revenue_outlook_official_vintage",
        }
    }
    # Official-vintage governance: the default comparator is BEFU26, so the
    # MBU26-only synthetic rate-only counterfactual control is NOT rendered.
    # It appears only when MBU26 is displayed (selected, or overlaid), and it
    # defaults to published rather than to a deferred counterfactual.
    assert set(policy_selectors) == {
        "revenue_outlook_fed_policy_state",
        "revenue_outlook_official_vintage",
    }
    assert str(policy_selectors["revenue_outlook_fed_policy_state"].value) == app.FED_POLICY_DELAYED_6M
    assert str(policy_selectors["revenue_outlook_official_vintage"].value) == "BEFU26 official"
    assert any("Revenue composition over time" in str(markdown.value) for markdown in at.markdown)
    rendered_text = "\n".join([*(str(markdown.value) for markdown in at.markdown), *(str(caption.value) for caption in at.caption)])
    for forbidden in [
        "Single selected series from the committed current runtime pack",
        "Actuals, current finalist base/comparison and official comparator traces",
        "PED bridge mode: Raw model bridge",
        "Post-model overlays; default Off preserves model forecast",
        "Clean bridge mode hides internal add-back rows",
        "Line-item contributions from revenue_stack_components",
        "Showing first",
    ]:
        assert forbidden not in rendered_text
    fy_sliders = [slider for slider in at.slider if slider.label == "FY range / horizon"]
    assert len(fy_sliders) == 1
    # Per-source bounds: the default source opens from its own first FY to
    # FY2050 (long-run sources default to 2050 even where, like MBU26, the
    # slider can be extended to the FY2055 source horizon).
    slider_value = tuple(int(v) for v in fy_sliders[0].value)
    assert slider_value[0] == int(selectors["stack_fy_bounds"][0])
    assert slider_value[1] == 2050
    # The section/overlay multiselects duplicated their defaults for everyone;
    # they are local-audit-only now.
    multiselect_labels = {str(widget.label) for widget in at.multiselect}
    assert "Section filter" not in multiselect_labels
    assert "Aggregate overlays" not in multiselect_labels


def _run_revenue_outlook_page() -> AppTest:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=120)
    at.run()
    at.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    at.run()
    assert not at.exception
    return at


def _view_mode_radio(at: AppTest):
    return next(radio for radio in at.radio if radio.key == "revenue_outlook_view_mode")


def test_revenue_outlook_defaults_to_single_scenario_view() -> None:
    at = _run_revenue_outlook_page()
    assert _view_mode_radio(at).value == app.REVENUE_OUTLOOK_VIEW_SINGLE
    rendered = "\n".join(str(markdown.value) for markdown in at.markdown)
    assert "Total path chart" in rendered
    assert "page5-panel-title'>Scenario comparison (A vs B)" not in rendered
    # The advanced levers live in one accordion; the old bordered panels are gone.
    expander_labels = [str(expander.label) for expander in at.expander]
    assert "Advanced scenario levers" in expander_labels


def test_revenue_outlook_activity_opens_policy_levers() -> None:
    at = _run_revenue_outlook_page()
    series = next(
        selectbox for selectbox in at.selectbox if selectbox.key == "revenue_outlook_stream"
    )
    series.set_value("PED VKT per capita")
    at.run()

    assert not at.exception
    lever_expander = next(
        expander for expander in at.expander if expander.label == "Advanced scenario levers"
    )
    assert lever_expander.proto.expanded is True
    selectbox_keys = {selectbox.key for selectbox in at.selectbox}
    # The Current policy control is always available. The MBU26-only synthetic
    # rate-only counterfactual is not, while BEFU26 is the selected comparator:
    # a published official vintage is never given a policy overlay by default.
    assert "revenue_outlook_fed_policy_state" in selectbox_keys
    assert "revenue_outlook_official_vintage" in selectbox_keys
    assert "revenue_outlook_mbu_fed_policy_state" not in selectbox_keys

    # Selecting the MBU26 prior vintage brings the counterfactual back, and it
    # opens on the published state rather than on a deferred counterfactual.
    vintage = next(
        selectbox for selectbox in at.selectbox if selectbox.key == "revenue_outlook_official_vintage"
    )
    vintage.set_value("MBU26 official (prior vintage)")
    at.run()
    assert not at.exception
    counterfactual = next(
        selectbox
        for selectbox in at.selectbox
        if selectbox.key == "revenue_outlook_mbu_fed_policy_state"
    )
    assert str(counterfactual.value) == app.FED_POLICY_PUBLISHED
    assert "not a published forecast" in str(counterfactual.label)


def test_revenue_outlook_compare_mode_swaps_total_path_for_comparison() -> None:
    at = _run_revenue_outlook_page()
    _view_mode_radio(at).set_value(app.REVENUE_OUTLOOK_VIEW_COMPARE)
    at.run()
    assert not at.exception
    rendered = "\n".join(str(markdown.value) for markdown in at.markdown)
    assert "page5-panel-title'>Scenario comparison (A vs B)" in rendered
    assert "Total path chart" not in rendered
    expander_labels = [str(expander.label) for expander in at.expander]
    assert "Configure scenarios A and B" in expander_labels
    # The lever accordion disappears in compare mode (the A/B columns own the
    # levers); its persisted selections still drive the sections below.
    assert "Advanced scenario levers" not in expander_labels
    # Default B (MoT VFM fast) differs from A, so NPV cards render immediately.
    assert "NPV to FY2050" in rendered


def test_revenue_outlook_compare_mode_keeps_lever_state_for_downstream() -> None:
    at = _run_revenue_outlook_page()
    freight = next(t for t in at.toggle if t.key == "revenue_outlook_sensitivity_freight_rail_toggle")
    freight.set_value(True)
    at.run()
    _view_mode_radio(at).set_value(app.REVENUE_OUTLOOK_VIEW_COMPARE)
    at.run()
    assert not at.exception
    captions = "\n".join(str(caption.value) for caption in at.caption)
    assert "Single-view levers" in captions
    assert "Freight rail Med" in captions
    _view_mode_radio(at).set_value(app.REVENUE_OUTLOOK_VIEW_SINGLE)
    at.run()
    assert not at.exception
    freight_after = next(t for t in at.toggle if t.key == "revenue_outlook_sensitivity_freight_rail_toggle")
    assert freight_after.value is True


def test_revenue_outlook_comparison_offers_mot_official_locked_scenario() -> None:
    at = _run_revenue_outlook_page()
    _view_mode_radio(at).set_value(app.REVENUE_OUTLOOK_VIEW_COMPARE)
    at.run()
    uptake_b = next(s for s in at.selectbox if s.key == "ro_cmp_b_uptake")
    assert app.COMPARISON_MOT_OFFICIAL_OPTION in uptake_b.options
    uptake_b.set_value(app.COMPARISON_MOT_OFFICIAL_OPTION)
    at.run()
    assert not at.exception
    rendered = "\n".join(str(markdown.value) for markdown in at.markdown)
    assert app.COMPARISON_MOT_OFFICIAL_OPTION in rendered
    captions = "\n".join(str(caption.value) for caption in at.caption)
    assert "levers locked" in captions


def test_revenue_outlook_fleet_mix_is_always_visible_and_precedes_rates() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    # The explorer now takes the pack's bridge vintage so its data and label
    # follow the vintage actually in use.
    fleet_index = source.index("_render_fleet_mix_explorer(bridge_vintage_id)")
    rates_index = source.index("Effective rates per 1,000 km")
    assert rates_index > source.index("Total path chart")
    assert rates_index > source.index("Show Revenue bridge detail")
    assert fleet_index < rates_index
    assert rates_index < source.index("Show Manifest, Source policy and downloads")

    fleet_source = inspect.getsource(app._render_fleet_mix_explorer)
    assert "st.expander" not in fleet_source
    assert "st.container(border=True)" in fleet_source
    # The panel title names the bridge vintage rather than a hard-coded
    # release, so a future default vintage renames itself.
    assert "Fleet mix explorer - MoT's six volume rows across " in fleet_source
    assert "{bridge_vintage_id}, the VFM and this dashboard</div>" in fleet_source


def test_governance_page_cloud_visibility_can_be_overridden(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")

    assert app.REPRODUCIBILITY_PAGE in app.dashboard_pages()

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app
import model_dashboard.revenue_outlook as revenue_outlook_module
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    apply_ped_bridge_mode_layer,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
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
        "Benchmark Comparison",
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
        "Schiff Benchmark",
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
    assert app.dashboard_pages() == ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark", "Revenue Outlook"]


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
    assert app.sensitivity_option_label("demand_elasticity", "Low") == "Low: PED -0.100 / Light RUC -0.080 / Heavy RUC -0.050"
    assert app.sensitivity_option_label("demand_elasticity", "Med") == "Med: PED -0.144 / Light RUC -0.120 / Heavy RUC -0.100"
    assert app.sensitivity_option_label("demand_elasticity", "High") == "High: PED -0.240 / Light RUC -0.200 / Heavy RUC -0.200"


def test_revenue_outlook_lazy_table_uses_explicit_toggle(monkeypatch) -> None:
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


def test_revenue_outlook_heavy_sections_are_lazy_guarded_in_renderer() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    guarded_markers = {
        "revenue_outlook_show_scenario_role_contract": 'scenario_role_contract = _pack_table(pack, "scenario_role_contract")',
        "revenue_outlook_show_runtime_cutoff_audit": 'runtime_cutoff_audit = _pack_table(pack, "runtime_cutoff_audit")',
        "revenue_outlook_show_sensitivity_impact_audit": "cached_revenue_outlook_sensitivity_audit(",
        "revenue_outlook_show_ped_bridge_diagnostics": 'ped_bridge_shape_fit_metrics = _pack_table(pack, "ped_bridge_shape_fit_metrics")',
        "revenue_outlook_show_composition": "cached_revenue_outlook_composition_stack(",
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
    assert "Current planned path" in selectors["fed_path_options"]
    assert "FY2031" in selectors["fy_options"]
    assert selectors["stack_fy_bounds"][0] <= 2025 <= selectors["stack_fy_bounds"][1]
    assert selectors["sensitivity_labels"]["fleet_efficiency"]["High"] == "High (1.5% p.a.)"
    assert selectors["sensitivity_labels"]["pt_mode_shift"]["High"] == "High (1.0% p.a. from FY2030)"
    assert selectors["sensitivity_labels"]["demand_elasticity"]["Med"] == "Med: PED -0.144 / Light RUC -0.120 / Heavy RUC -0.100"


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
    for key, value_column in [
        ("chart_rows", "value"),
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
    assert audit["selected_demand_elasticity"].astype(str).eq("Off").all()


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
        pack,
    )
    uncached = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
    )
    expected_rows = app._filter_revenue_outlook_rows(
        uncached["chart_rows"],
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


def test_revenue_outlook_primary_hover_customdata_matches_row_helpers() -> None:
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
        pack,
    )
    rows = app._selected_revenue_outlook_series_rows(view["filtered_rows"], "Total NLTF revenue")
    for column in [
        "horizon",
        "horizon_scope",
        "bridge_status",
        "gap_reason",
        "data_scope",
        "value_status",
        "actual_quarters",
        "forecast_quarters",
        "ped_bridge_mode_label",
        "revenue_sensitivity_label",
    ]:
        if column not in rows.columns:
            rows[column] = ""

    actual = pd.DataFrame(
        app._revenue_path_hover_customdata(rows),
        columns=["horizon_hover", "bridge_hover", "scope_hover", "efficiency_hover"],
    )
    expected = pd.DataFrame(
        {
            "horizon_hover": rows.apply(app._revenue_horizon_hover_label, axis=1).to_list(),
            "bridge_hover": rows.apply(app._revenue_bridge_hover_label, axis=1).to_list(),
            "scope_hover": rows.apply(app._revenue_scope_hover_label, axis=1).to_list(),
            "efficiency_hover": rows.apply(app._revenue_efficiency_hover_label, axis=1).to_list(),
        }
    )

    pd.testing.assert_frame_equal(actual, expected)
    fig = app.revenue_outlook_total_path_figure(view["filtered_rows"], selected_series="Total NLTF revenue", selected_fy="FY2031")
    marker_shapes = {(str(shape.x0), str(shape.line.dash)) for shape in fig.layout.shapes or []}
    assert ("FY2026", "dash") in marker_shapes
    assert ("FY2031", "dot") in marker_shapes


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
    direct_rows = app._filter_revenue_outlook_rows(
        view["chart_rows"],
        time_grain="june_year",
        stream_labels=["PED VKT per capita", "PED volume", "Light RUC net km", "Heavy RUC net km"],
        fed_paths=["Current planned path"],
        trace_names=list(traces),
    )
    direct_fig = app.revenue_outlook_figure(direct_rows, metric_type="activity")

    assert [trace.name for trace in cached_fig.data] == [trace.name for trace in direct_fig.data]
    assert [tuple(trace.x) for trace in cached_fig.data] == [tuple(trace.x) for trace in direct_fig.data]
    for cached_trace, direct_trace in zip(cached_fig.data, direct_fig.data, strict=True):
        assert pd.to_numeric(pd.Series(cached_trace.y), errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(pd.Series(direct_trace.y), errors="coerce").to_numpy(),
            abs=0,
            nan_ok=True,
        )


def test_revenue_outlook_activity_branch_uses_cached_figure() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    start = source.index('"Show Activity and volume outlook"')
    end = source.index('"Show Revenue bridge detail"')
    activity_branch = source[start:end]
    assert "cached_revenue_outlook_activity_figure(" in activity_branch
    assert "revenue_outlook_figure(activity_rows" not in activity_branch


def test_revenue_outlook_composition_branch_uses_cached_stack_for_table() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    start = source.index('"Show Revenue composition over time"')
    end = source.index('"Show EV/PHEV PED-Light migration audit"')
    composition_branch = source[start:end]
    assert "filtered_stack" not in composition_branch
    assert "dataframe_download(chart_stack" in composition_branch
    assert "cached_revenue_outlook_composition_table_view(" in composition_branch
    assert "_revenue_stack_components_display_table(chart_stack)" not in composition_branch


def test_governance_page_cloud_visibility_can_be_overridden(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")

    assert app.REPRODUCIBILITY_PAGE in app.dashboard_pages()

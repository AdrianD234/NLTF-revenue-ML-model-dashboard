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
        "revenue_outlook_show_composition": "_filter_revenue_stack_components(",
        "revenue_outlook_show_ev_phev_drift_audit": 'ev_phev_ped_light_drift_assumptions = _pack_table(pack, "ev_phev_ped_light_drift_assumptions")',
        "revenue_outlook_show_ev_phev_split_audit": 'ev_phev_split_assumptions = _pack_table(pack, "ev_phev_split_assumptions")',
        "revenue_outlook_show_line_reconciliation": "_filter_revenue_line_reconciliation(",
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


def test_governance_page_cloud_visibility_can_be_overridden(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")

    assert app.REPRODUCIBILITY_PAGE in app.dashboard_pages()

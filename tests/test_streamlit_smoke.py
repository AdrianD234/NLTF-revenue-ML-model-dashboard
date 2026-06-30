from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app
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
    assert app.sensitivity_option_label("pt_mode_shift", "High") == "High (1% p.a. from FY2030)"
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
    for key, value_column in [
        ("chart_rows", "value"),
        ("line_reconciliation", "value"),
        ("revenue_bridge_components", "component_value"),
        ("future_revenue_forecasts", "revenue_forecast_nzd"),
    ]:
        assert pd.to_numeric(view[key][value_column], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(expected[key][value_column], errors="coerce").to_numpy(),
            abs=0,
        )


def test_governance_page_cloud_visibility_can_be_overridden(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")

    assert app.REPRODUCIBILITY_PAGE in app.dashboard_pages()

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

import app


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


def test_governance_page_cloud_visibility_can_be_overridden(monkeypatch) -> None:
    _clear_governance_visibility_env(monkeypatch)
    monkeypatch.setenv("STREAMLIT_SHARING_MODE", "streamlit_cloud")
    monkeypatch.setenv(app.SHOW_GOVERNANCE_PAGE_ENV_VAR, "1")

    assert app.REPRODUCIBILITY_PAGE in app.dashboard_pages()

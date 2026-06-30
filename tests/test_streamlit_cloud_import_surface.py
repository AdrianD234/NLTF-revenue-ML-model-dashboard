from __future__ import annotations

import importlib
import sys

import pandas as pd
import pytest

from scripts.check_streamlit_deploy_readiness import (
    REQUIRED_FORECAST_IMPORT_EXPORTS,
    REQUIRED_REPRODUCIBILITY_IMPORT_EXPORTS,
    REQUIRED_UI_EXPORTS,
    assert_app_uses_cloud_safe_forecast_wrapper,
    assert_app_uses_cloud_safe_reproducibility_wrapper,
    assert_current_revenue_outlook_cloud_runtime_subprocess,
    assert_current_revenue_outlook_pack_shape,
    assert_import_surface,
    assert_r2_ladder_direct_import_subprocess,
    assert_startup_import_subprocess,
)


def test_app_imports_cloud_ui_surface() -> None:
    assert_import_surface()


def test_app_uses_cloud_safe_reproducibility_wrapper() -> None:
    assert_app_uses_cloud_safe_reproducibility_wrapper()


def test_app_uses_cloud_safe_forecast_wrapper() -> None:
    assert_app_uses_cloud_safe_forecast_wrapper()


def test_r2_ladder_exports_cloud_reported_import_surface() -> None:
    ladder = importlib.import_module("model_dashboard.r2_ladder")
    missing = [
        name
        for name in [
            "R2_LADDER_NOTE",
            "R2_LADDER_TITLE",
            "R2_TRAINING_FIT_NOTE",
            "r2_ladder_summary_frame",
        ]
        if not hasattr(ladder, name)
    ]
    assert missing == []


def test_r2_ladder_direct_import_survives_dependency_fallback() -> None:
    assert_r2_ladder_direct_import_subprocess(force_dependency_fallback=True)


def test_streamlit_cloud_style_subprocess_imports_app() -> None:
    assert_startup_import_subprocess(force_optional_fallback=False)


def test_streamlit_cloud_style_subprocess_imports_app_without_local_pyarrow24() -> None:
    assert_startup_import_subprocess(disable_runtime_pyarrow24=True)


def test_revenue_outlook_committed_runtime_pack_is_cloud_ready() -> None:
    assert_current_revenue_outlook_pack_shape()


def test_revenue_outlook_cloud_runtime_load_does_not_require_local_pyarrow24() -> None:
    assert_current_revenue_outlook_cloud_runtime_subprocess()


def test_app_imports_when_optional_reproducibility_imports_fallback() -> None:
    assert_startup_import_subprocess(force_optional_fallback=True)


def test_app_imports_when_optional_forecast_runner_import_fallback() -> None:
    assert_startup_import_subprocess(force_forecast_fallback=True)


def test_model_dashboard_ui_exports_app_helpers() -> None:
    ui = importlib.import_module("model_dashboard.ui")
    missing = sorted(name for name in REQUIRED_UI_EXPORTS if not hasattr(ui, name))
    assert missing == []


def test_reproducibility_import_wrapper_exports_all_app_symbols() -> None:
    wrapper = importlib.import_module("model_dashboard.reproducibility_imports")
    missing = sorted(name for name in REQUIRED_REPRODUCIBILITY_IMPORT_EXPORTS if not hasattr(wrapper, name))
    assert missing == []


def test_forecast_import_wrapper_exports_all_app_symbols() -> None:
    wrapper = importlib.import_module("model_dashboard.forecast_imports")
    missing = sorted(name for name in REQUIRED_FORECAST_IMPORT_EXPORTS if not hasattr(wrapper, name))
    assert missing == []


def test_forecast_import_wrapper_fallbacks_keep_app_importable(monkeypatch) -> None:
    monkeypatch.setenv("NLTF_FORCE_FORECAST_RUNNER_IMPORT_FALLBACK", "1")
    sys.modules.pop("model_dashboard.forecast_imports", None)
    wrapper = importlib.import_module("model_dashboard.forecast_imports")

    try:
        assert wrapper.FORECAST_RUNNER_IMPORT_ERROR
        assert wrapper.quarter_sort_key("2026Q1") < wrapper.quarter_sort_key("2026Q2")
        assert wrapper.scenario_name_from_filename("NLTF_forecast_input_template_basecase.xlsx") == "basecase"
        assert wrapper.sanitize_scenario_name("High pop!") == "high_pop"
        with pytest.raises(wrapper.ForecastRunnerUnavailable):
            wrapper.build_forecast_input_template_bytes()
    finally:
        monkeypatch.delenv("NLTF_FORCE_FORECAST_RUNNER_IMPORT_FALLBACK", raising=False)
        sys.modules.pop("model_dashboard.forecast_imports", None)
        importlib.import_module("model_dashboard.forecast_imports")


def test_reproducibility_import_wrapper_fallbacks_return_missing_data(monkeypatch) -> None:
    monkeypatch.setenv("NLTF_FORCE_REPRODUCIBILITY_IMPORT_FALLBACK", "1")
    sys.modules.pop("model_dashboard.reproducibility_imports", None)
    wrapper = importlib.import_module("model_dashboard.reproducibility_imports")

    try:
        assert wrapper.REPRODUCIBILITY_IMPORT_ERROR
        assert wrapper.R2_IMPORT_ERROR
        assert wrapper.reproducibility_stream_labels() == [
            "PED VKT per capita",
            "Light RUC volume",
            "Heavy RUC volume",
        ]
        pack = wrapper.load_reproducibility_pack("Light RUC volume")
        assert pack.available is False
        assert pack.missing_files
        assert wrapper.reproducibility_registry_view(pack).empty
        assert wrapper.diagnostics_r2_summary_frame(pd.DataFrame()).empty
        assert wrapper.reproducibility_component_r2_frame().empty
        assert wrapper.format_r2(0.1234) == "0.123"
    finally:
        monkeypatch.delenv("NLTF_FORCE_REPRODUCIBILITY_IMPORT_FALLBACK", raising=False)
        sys.modules.pop("model_dashboard.reproducibility_imports", None)
        importlib.import_module("model_dashboard.reproducibility_imports")

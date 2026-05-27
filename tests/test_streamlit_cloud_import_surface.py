from __future__ import annotations

import importlib

from scripts.check_streamlit_deploy_readiness import REQUIRED_UI_EXPORTS, assert_import_surface


def test_app_imports_cloud_ui_surface() -> None:
    assert_import_surface()


def test_model_dashboard_ui_exports_app_helpers() -> None:
    ui = importlib.import_module("model_dashboard.ui")
    missing = sorted(name for name in REQUIRED_UI_EXPORTS if not hasattr(ui, name))
    assert missing == []

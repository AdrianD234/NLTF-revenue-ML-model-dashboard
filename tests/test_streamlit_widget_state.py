from __future__ import annotations

import ast
from pathlib import Path


ADVANCED_WIDGET_KEYS = {
    "advanced_top_n",
    "advanced_show_schiff",
    "advanced_show_finalists",
    "advanced_show_screen",
    "advanced_show_final",
    "advanced_show_static",
    "advanced_show_prequential",
    "advanced_hide_outliers",
}


def test_seeded_advanced_widgets_do_not_pass_duplicate_defaults() -> None:
    """Streamlit warns if a keyed widget is seeded via session_state and value=."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        widget_key = None
        keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg}
        for keyword in node.keywords:
            if keyword.arg == "key" and isinstance(keyword.value, ast.Constant):
                widget_key = str(keyword.value.value)
                break
        if widget_key in ADVANCED_WIDGET_KEYS and {"value", "index", "default"} & keyword_names:
            violations.append(widget_key)

    assert violations == []

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_smoke_loads_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    at = AppTest.from_file(str(app_path), default_timeout=60)
    at.run()

    assert not at.exception
    assert len(at.radio) >= 1
    assert at.radio[0].options == [
        "Overview",
        "Diagnostics",
        "Scenario Comparison",
        "Schiff Benchmark",
        "Governance & Reproducibility",
    ]

"""Executive presentation mode: same governed data, plain-English surface.

Guarantees:
- every model identifier that can surface in the dashboard has a curated
  plain-English label (no raw IDs, no snake_case leaking into executive view);
- score-basis and capability codes translate to decision language;
- the mode machinery defaults to executive and respects the env override;
- the executive stream cards carry only display-language values and the
  governed pack numbers (presentation only - nothing recomputed).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "dashboard_evidence_pack" / "data"

RAW_ID_PATTERN = re.compile(r"__|_[a-z0-9]+_|\bn\d+\b|lr0|alpha\d|w\d{2}\b")


def _all_surfaced_model_ids() -> set[str]:
    ids: set[str] = set()
    for table, col in [("finalists.parquet", "model"),
                       ("schiff_benchmark.parquet", "model"),
                       ("ensemble_components.parquet", "component_model"),
                       ("scorecard_predictions.parquet", "model"),
                       ("diagnostic_tests.parquet", "model")]:
        df = pd.read_parquet(DATA / table)
        if col in df.columns:
            ids |= set(df[col].dropna().astype(str).unique())
    from model_dashboard.governance_constants import ARCHIVED_FINALISTS

    ids |= set(ARCHIVED_FINALISTS.values())
    return {i for i in ids if i.strip()}


def test_every_surfaced_model_id_has_curated_label() -> None:
    from model_dashboard.presentation import MODEL_DISPLAY, missing_model_labels

    missing = missing_model_labels(_all_surfaced_model_ids())
    assert not missing, f"add curated labels for: {missing}"
    for raw, label in MODEL_DISPLAY.items():
        assert not RAW_ID_PATTERN.search(label), f"label for {raw} leaks technical tokens: {label}"
        assert len(label) <= 84


def test_display_model_never_returns_raw_ids() -> None:
    from model_dashboard.presentation import display_model

    for model_id in sorted(_all_surfaced_model_ids()):
        label = display_model(model_id)
        assert "__" not in label, f"{model_id} -> {label}"
        assert not label.startswith(("PED__", "HEAVY_RUC__", "LIGHT_RUC__", "dynamic_"))
    # unknown identifiers fall back to a family title, never the raw string
    assert "__" not in display_model("HEAVY_RUC__SOME_FUTURE_gbr_n500__w40")


def test_score_basis_and_capability_language() -> None:
    from model_dashboard.presentation import (CAPABILITY_DISPLAY, SCORE_BASIS_DISPLAY,
                                              display_capability, display_score_basis)

    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    for basis in sp["score_basis"].dropna().astype(str).unique():
        assert basis in SCORE_BASIS_DISPLAY, f"missing score-basis label: {basis}"
        assert "_" not in display_score_basis(basis)
    for code, label in CAPABILITY_DISPLAY.items():
        assert "_" not in label, f"capability label for {code} leaks snake_case"
    assert "gap" in display_capability("governed_gap").lower()
    assert "_" not in display_capability("some_unmapped_future_code")


def test_mode_defaults_to_executive_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from model_dashboard import presentation

    monkeypatch.delenv(presentation.MODE_ENV_VAR, raising=False)
    assert presentation.default_mode() == presentation.EXECUTIVE
    monkeypatch.setenv(presentation.MODE_ENV_VAR, "analyst")
    assert presentation.default_mode() == presentation.ANALYST
    monkeypatch.setenv(presentation.MODE_ENV_VAR, "EXECUTIVE")
    assert presentation.default_mode() == presentation.EXECUTIVE


def test_executive_page_titles_cover_all_pages() -> None:
    import app
    from model_dashboard.presentation import EXECUTIVE_PAGE_TITLES

    for page in app.dashboard_pages():
        assert page in EXECUTIVE_PAGE_TITLES, f"missing executive title for page {page}"
        assert EXECUTIVE_PAGE_TITLES[page]


def test_executive_stream_cards_use_display_language_only() -> None:
    import app

    cards = app._executive_card_inputs.__wrapped__(0.0)
    assert len(cards) == 3
    for card in cards:
        for key, value in card.items():
            assert "__" not in str(value), f"{key} leaks raw ID: {value}"
        assert card["badge"] in {"Promote", "Watch", "Monitor"}
        assert card["mape"].endswith("%")
        assert card["readiness"]
        assert card["caveat"]
    # governed numbers come straight from the pack
    fin = pd.read_parquet(DATA / "finalists.parquet").set_index("stream_label")
    for card in cards:
        stored = float(fin.loc[card["stream"], "quarterly_mape"])
        assert card["mape"] == f"{stored:.2f}%"


def test_presentation_layer_is_read_only() -> None:
    src = (ROOT / "model_dashboard" / "presentation.py").read_text(encoding="utf-8")
    assert "to_parquet" not in src
    assert "read_parquet" not in src, "presentation layer must not load data itself"


def test_confidence_badges_read_governed_statuses() -> None:
    import app

    cards = app._executive_card_inputs.__wrapped__(0.0)
    for card in cards:
        badges = dict((dim, (label, color)) for dim, label, color in app._confidence_badges_for(card))
        assert set(badges) == {"Accuracy", "Diagnostics", "Forecast", "Reproducibility"}
        # Diagnostics dimension must mirror the governed Overall verdict
        expected = {"Promote": "Pass", "Watch": "Watch", "Monitor": "Fail items"}[card["badge"]]
        assert badges["Diagnostics"][0] == expected
        # all three streams beat the benchmark, so Accuracy is never Watch here
        assert badges["Accuracy"][0] in {"Strong", "Moderate"}
        for label, _ in badges.values():
            assert "__" not in label and "_" not in label


def test_action_card_copy_is_display_language() -> None:
    """Action-card inputs compose only from display-language card fields."""
    import app

    cards = app._executive_card_inputs.__wrapped__(0.0)
    assert cards
    for card in cards:
        for key in ("stream", "badge", "gain", "readiness", "caveat", "model"):
            assert "__" not in str(card[key])
    # numeric companions exist for the badge rules
    assert all(isinstance(card["mape_value"], float) for card in cards)


def test_forecast_figure_shades_future_region_and_marks_start() -> None:
    import app

    rows = []
    for idx, period in enumerate(["2025Q1", "2025Q2", "2025Q3", "2025Q4"]):
        rows.append({"stream_label": "Light RUC volume", "row_type": "historical_actual",
                     "scenario_name": None, "period": period, "value": 100.0 + idx})
    for idx, period in enumerate(["2026Q1", "2026Q2"]):
        rows.append({"stream_label": "Light RUC volume", "row_type": "future_forecast",
                     "scenario_name": "Base", "period": period, "value": 110.0 + idx})
    fig = app.forecast_builder_figure(pd.DataFrame(rows))
    shapes = list(fig.layout.shapes or [])
    assert any(s.type == "rect" for s in shapes), "future region must be shaded"
    assert any(s.type == "line" for s in shapes), "forecast start marker must be drawn"

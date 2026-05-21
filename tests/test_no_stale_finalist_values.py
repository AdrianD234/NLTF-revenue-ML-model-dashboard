from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"

STALE_QUARTERLY_MAPE = {
    "PED": 5.49,
    "LIGHT_RUC": 11.55,
    "HEAVY_RUC": 12.38,
}


def test_stale_autogluon_values_are_not_current_finalists() -> None:
    finalists = pd.read_csv(CURATED_DIR / "finalist_accuracy.csv")
    for stream, stale_value in STALE_QUARTERLY_MAPE.items():
        rows = finalists[finalists["stream"] == stream]
        assert len(rows) == 1
        current_value = float(rows.iloc[0]["quarterly_mape"])
        assert abs(current_value - stale_value) > 0.50, (
            f"{stream} still appears to use stale quarterly finalist MAPE {stale_value}%"
        )


def test_current_finalist_models_are_static_convex_top18_arbitration_winners() -> None:
    finalists = pd.read_csv(CURATED_DIR / "finalist_accuracy.csv")
    expected_models = {
        "PED__solver_static_convex_top18",
        "LIGHT_RUC__solver_static_convex_top18",
        "HEAVY_RUC__solver_static_convex_top18",
    }
    assert set(finalists["model"]) == expected_models

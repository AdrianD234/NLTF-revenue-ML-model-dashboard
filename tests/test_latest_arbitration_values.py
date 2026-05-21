from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"
ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "PED": {
        "model": "PED__solver_static_convex_top18",
        "quarterly_mape": 2.47358,
        "annual_mape": 2.38709,
        "quarterly_bias_pct": 1.50491,
        "quarterly_display": "2.47%",
        "annual_display": "2.39%",
    },
    "LIGHT_RUC": {
        "model": "LIGHT_RUC__solver_static_convex_top18",
        "quarterly_mape": 9.14755,
        "annual_mape": 5.99950,
        "quarterly_bias_pct": 0.738125,
        "quarterly_display": "9.15%",
        "annual_display": "6.00%",
    },
    "HEAVY_RUC": {
        "model": "HEAVY_RUC__solver_static_convex_top18",
        "quarterly_mape": 3.56092,
        "annual_mape": 3.17141,
        "quarterly_bias_pct": 0.165850,
        "quarterly_display": "3.56%",
        "annual_display": "3.17%",
    },
}


def _finalists() -> pd.DataFrame:
    path = CURATED_DIR / "finalist_accuracy.csv"
    assert path.exists(), f"Missing curated finalist file: {path}"
    return pd.read_csv(path)


def test_latest_arbitration_finalist_values_match_source_of_truth() -> None:
    finalists = _finalists()
    for stream, expected in EXPECTED.items():
        rows = finalists[(finalists["stream"] == stream) & (finalists["model"] == expected["model"])]
        assert len(rows) == 1, f"Expected one latest finalist row for {stream}; found {len(rows)}"
        row = rows.iloc[0]
        for column in ["quarterly_mape", "annual_mape", "quarterly_bias_pct"]:
            assert abs(float(row[column]) - float(expected[column])) < 0.01


def test_latest_arbitration_values_round_to_management_display_values() -> None:
    finalists = _finalists()
    for stream, expected in EXPECTED.items():
        row = finalists.loc[finalists["stream"] == stream].iloc[0]
        assert f"{float(row['quarterly_mape']):.2f}%" == expected["quarterly_display"]
        assert f"{float(row['annual_mape']):.2f}%" == expected["annual_display"]


def test_source_of_truth_lock_matches_curated_finalists() -> None:
    lock_text = (ROOT / "LATEST_RUN_SOURCE_OF_TRUTH.lock.md").read_text(encoding="utf-8")
    finalists = _finalists()
    assert "run_20260520_002339" in lock_text
    for stream, expected in EXPECTED.items():
        assert expected["model"] in lock_text
        assert f"| {stream} | {expected['model']} |" in lock_text
        row = finalists.loc[finalists["stream"] == stream].iloc[0]
        assert f"{float(row['quarterly_mape']):.5f}" in lock_text
        assert f"{float(row['annual_mape']):.5f}" in lock_text

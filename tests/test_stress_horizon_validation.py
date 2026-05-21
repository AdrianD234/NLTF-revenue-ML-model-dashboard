from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"
EXPECTED_BUCKETS = {"1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"}


def _stress() -> pd.DataFrame:
    return pd.read_csv(CURATED_DIR / "stress_horizon.csv")


def test_stress_horizon_has_expected_buckets() -> None:
    assert EXPECTED_BUCKETS.issubset(set(_stress()["stress_bucket"]))


def test_light_ruc_2022_23_watchpoint_visible() -> None:
    stress = _stress()
    row = stress[(stress["stream"] == "LIGHT_RUC") & (stress["stress_bucket"] == "2022-23")]
    assert len(row) == 1
    assert float(row.iloc[0]["mape"]) > 15.0


def test_stress_chart_hover_is_readable() -> None:
    stress = _stress()
    assert not stress["stream_label"].astype(str).str.contains("_", regex=False).any()
    assert not stress["model_short"].astype(str).str.contains("__", regex=False).any()
    assert stress["mape"].map(lambda value: f"{float(value):.2f}%").str.match(r"^\d+\.\d{2}%$").all()

from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"
BAD_TOKENS = ["resid", "residual", "fixedblend", "solver", "convex", "ensemble", "top", "median", "mean", "blend"]


def _schiff() -> pd.DataFrame:
    return pd.read_csv(CURATED_DIR / "schiff_benchmark.csv")


def _all_text(row: pd.Series) -> str:
    return " ".join(str(row.get(column, "")) for column in row.index).lower()


def test_pure_schiff_excludes_residuals() -> None:
    assert not _schiff().apply(lambda row: "resid" in _all_text(row) or "residual" in _all_text(row), axis=1).any()


def test_pure_schiff_excludes_blends() -> None:
    assert not _schiff().apply(lambda row: "blend" in _all_text(row) or "fixedblend" in _all_text(row), axis=1).any()


def test_pure_schiff_excludes_solvers() -> None:
    assert not _schiff().apply(lambda row: "solver" in _all_text(row) or "convex" in _all_text(row), axis=1).any()


def test_schiff_benchmark_page_uses_pure_schiff_only() -> None:
    schiff = _schiff()
    assert len(schiff) == 3
    assert schiff["purity_flag"].astype(str).str.startswith("Pure Schiff").all()
    assert schiff["model"].astype(str).str.lower().str.contains("schiff_ols").all()
    for _, row in schiff.iterrows():
        text = _all_text(row)
        assert not any(token in text for token in BAD_TOKENS)

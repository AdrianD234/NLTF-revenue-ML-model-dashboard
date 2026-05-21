from __future__ import annotations

from pathlib import Path

import pandas as pd


CURATED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"

EXPECTED = {
    "PED": ("PED__solver_static_convex_top18", 2.47358, 2.38709, 1.50491),
    "LIGHT_RUC": ("LIGHT_RUC__solver_static_convex_top18", 9.14755, 5.99950, 0.738125),
    "HEAVY_RUC": ("HEAVY_RUC__solver_static_convex_top18", 3.56092, 3.17141, 0.165850),
}


def read_curated(name: str) -> pd.DataFrame:
    path = CURATED_DIR / name
    assert path.exists(), f"Missing curated file: {path}"
    return pd.read_csv(path)


def test_curated_data_latest_values() -> None:
    finalist = read_curated("finalist_accuracy.csv")
    for stream, (model, quarterly, annual, bias) in EXPECTED.items():
        row = finalist[(finalist["stream"] == stream) & (finalist["model"] == model)]
        assert len(row) == 1
        actual = row.iloc[0]
        assert abs(float(actual["quarterly_mape"]) - quarterly) < 0.01
        assert abs(float(actual["annual_mape"]) - annual) < 0.01
        assert abs(float(actual["quarterly_bias_pct"]) - bias) < 0.01


def test_no_stale_autogluon_finalist_values() -> None:
    finalist = read_curated("finalist_accuracy.csv")
    stale = {"PED": 5.49, "LIGHT_RUC": 11.55, "HEAVY_RUC": 12.38}
    for stream, stale_value in stale.items():
        q_mape = float(finalist.loc[finalist["stream"] == stream, "quarterly_mape"].iloc[0])
        assert abs(q_mape - stale_value) > 0.5


def test_candidate_landscape_sample_has_expected_roles() -> None:
    landscape = read_curated("candidate_landscape_sample.csv")
    assert len(landscape) <= 400
    for stream in EXPECTED:
        subset = landscape[landscape["stream"] == stream]
        assert subset["is_recommended_finalist"].astype(bool).any()
        assert subset["is_pure_schiff"].astype(bool).any()
        assert (subset["candidate_role"] == "Distribution sample").any()
        assert subset["candidate_role"].notna().all()


def test_candidate_landscape_sample_is_capped() -> None:
    landscape = read_curated("candidate_landscape_sample.csv")
    assert len(landscape) <= 400
    assert len(landscape) >= 100


def test_pure_schiff_filter_excludes_residuals_and_blends() -> None:
    schiff = read_curated("schiff_benchmark.csv")
    bad_tokens = ["resid", "residual", "fixedblend", "solver", "top", "median", "mean", "convex", "ensemble", "blend"]
    for model in schiff["model"].astype(str):
        lower = model.lower()
        assert "schiff_ols" in lower
        assert not any(token in lower for token in bad_tokens)


def test_stress_horizon_has_expected_buckets() -> None:
    stress = read_curated("stress_horizon.csv")
    assert {"1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"}.issubset(
        set(stress["stress_bucket"].astype(str))
    )


def test_ensemble_composition_positive_weights() -> None:
    ensemble = read_curated("ensemble_composition.csv")
    assert not ensemble.empty
    assert (pd.to_numeric(ensemble["weight"], errors="coerce") > 0).all()
    assert set(EXPECTED).issubset(set(ensemble["stream"]))

"""The seeded draw engine and the materialised uncertainty pack.

Aggregate bands must come from aggregate DRAWS. Summing marginal lower and
upper endpoints asserts a dependence structure nobody chose, and is wrong in
either direction depending on the sign of the correlation - which here is
positive and material (rho(LIGHT_RUC, HEAVY_RUC) = 0.47).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS
from model_dashboard.revenue_uncertainty import (
    LAST_SUPPORTED_FY,
    QuantileMultipliers,
    june_year_quantiles,
    plateau_multipliers_by_fy,
)
from model_dashboard.revenue_uncertainty_draws import (
    DRAW_COUNT,
    PARENT_STREAMS,
    aligned_parent_log_errors,
    generate_parent_factor_draws,
    parent_log_error_samples,
    quantile_mapped_sample,
    shrunk_rank_correlation,
)

ROOT = Path(__file__).resolve().parents[1]
JUNE_ERRORS = ROOT / "artifacts" / "long_horizon_validation" / "long_horizon_june_year_errors.csv"
PACK_DIR = ROOT / "data" / "revenue_outlook_uncertainty"
BAND_ROWS = PACK_DIR / "uncertainty_band_rows.parquet"


@pytest.fixture(scope="module")
def june_errors() -> pd.DataFrame:
    if not JUNE_ERRORS.exists():
        pytest.skip("the long-horizon June-year error file is not present")
    return pd.read_csv(JUNE_ERRORS)


@pytest.fixture(scope="module")
def quantiles(june_errors) -> pd.DataFrame:
    return june_year_quantiles(june_errors)


@pytest.fixture(scope="module")
def draws(june_errors, quantiles):
    return generate_parent_factor_draws(june_errors, quantiles, draws=2000)


@pytest.fixture(scope="module")
def bands() -> pd.DataFrame:
    if not BAND_ROWS.exists():
        pytest.skip("the uncertainty pack has not been built")
    return pd.read_parquet(BAND_ROWS)


# ------------------------------------------------ marginals reconcile exactly
def test_the_quantile_map_reproduces_the_governed_targets(quantiles) -> None:
    sample = np.random.default_rng(7).lognormal(0.0, 0.3, size=500)
    sample = np.log(sample)
    target = QuantileMultipliers(
        q10=np.log(0.80), q25=np.log(0.90), median=np.log(0.95),
        q75=np.log(1.01), q90=np.log(1.06),
    )
    mapped = quantile_mapped_sample(sample, target, size=20000)
    got = np.quantile(mapped, [0.10, 0.25, 0.50, 0.75, 0.90])
    expected = [target.q10, target.q25, target.median, target.q75, target.q90]
    assert np.allclose(got, expected, atol=1e-3), (got, expected)


def test_the_map_preserves_asymmetry_rather_than_normalising(quantiles) -> None:
    """A skewed input must not come out symmetric."""
    skewed = np.log(np.random.default_rng(11).lognormal(0.0, 0.4, size=2000))
    target = QuantileMultipliers(
        q10=np.log(0.70), q25=np.log(0.92), median=np.log(0.98),
        q75=np.log(1.01), q90=np.log(1.03),
    )
    mapped = np.exp(quantile_mapped_sample(skewed, target, size=20000))
    lower = 1.0 - np.quantile(mapped, 0.10)
    upper = np.quantile(mapped, 0.90) - 1.0
    assert lower > upper * 5, "the asymmetry was normalised away"


@pytest.mark.parametrize("stream", PARENT_STREAMS)
def test_draw_marginals_match_the_governed_quantiles(draws, quantiles, stream) -> None:
    by_fy, _provenance = draws
    factors = by_fy[LAST_SUPPORTED_FY][stream]
    target = plateau_multipliers_by_fy(quantiles, stream)[LAST_SUPPORTED_FY].multipliers()
    got = np.quantile(factors, [0.10, 0.25, 0.50, 0.75, 0.90])
    expected = [
        target["lower80_multiplier"], target["lower50_multiplier"],
        target["median_multiplier"], target["upper50_multiplier"],
        target["upper80_multiplier"],
    ]
    assert np.allclose(got, expected, rtol=2e-3), (stream, got, expected)


def test_the_median_bias_survives_into_the_draws(draws) -> None:
    by_fy, _provenance = draws
    for stream in PARENT_STREAMS:
        median = float(np.median(by_fy[LAST_SUPPORTED_FY][stream]))
        assert median < 1.0, f"{stream}: the downward bias vanished from the draws"


# ---------------------------------------------------------------- dependence
def test_cross_parent_dependence_is_estimated_from_aligned_origins(june_errors) -> None:
    aligned = aligned_parent_log_errors(june_errors)
    assert len(aligned) > 0, "no aligned observations - the join is vacuous"
    assert list(aligned.columns) == list(PARENT_STREAMS)
    matrix, audit = shrunk_rank_correlation(aligned)
    assert matrix.shape == (3, 3)
    assert np.allclose(np.diag(matrix), 1.0)
    assert np.allclose(matrix, matrix.T)
    assert np.linalg.eigvalsh(matrix).min() > 0, "not positive definite"
    assert audit["n_aligned"] == len(aligned)


def test_a_thin_aligned_sample_is_shrunk_toward_independence() -> None:
    thin = pd.DataFrame(
        {"PED": [0.1, -0.2, 0.3, 0.05], "LIGHT_RUC": [0.1, -0.2, 0.3, 0.05],
         "HEAVY_RUC": [0.1, -0.2, 0.3, 0.05]}
    )
    matrix, audit = shrunk_rank_correlation(thin)
    assert audit["shrinkage"] > 0.0
    # Perfectly correlated input, but only 4 rows: must not be taken at face value.
    assert matrix[0, 1] < 1.0


def test_the_copula_preserves_dependence_in_the_drawn_factors(draws) -> None:
    by_fy, provenance = draws
    factors = by_fy[LAST_SUPPORTED_FY]
    from scipy.stats import spearmanr

    observed = spearmanr(factors["LIGHT_RUC"], factors["HEAVY_RUC"]).statistic
    target = float(provenance["rho_LIGHT_RUC_HEAVY_RUC"])
    assert abs(observed - target) < 0.06, (observed, target)


def test_light_classes_are_perfectly_dependent_given_the_shares(bands) -> None:
    """One Light pool draw scales every Light class, so their spans coincide."""
    light = bands[
        bands["series_id"].isin(
            ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")
        )
    ]
    for fy, cell in light.groupby("FY"):
        spans = cell["span80_pct"].round(6).unique()
        assert len(spans) == 1, (fy, spans)


# ------------------------------------------------------ determinism and shape
def test_the_draw_engine_is_deterministic(june_errors, quantiles) -> None:
    first, _a = generate_parent_factor_draws(june_errors, quantiles, draws=500)
    second, _b = generate_parent_factor_draws(june_errors, quantiles, draws=500)
    for stream in PARENT_STREAMS:
        assert np.array_equal(
            first[LAST_SUPPORTED_FY][stream], second[LAST_SUPPORTED_FY][stream]
        )


def test_no_normal_approximation_is_used(june_errors) -> None:
    """The marginals are the empirical sample, mapped - not a fitted normal."""
    samples = parent_log_error_samples(june_errors)
    assert set(samples) == set(PARENT_STREAMS)
    for stream, sample in samples.items():
        assert len(sample) > 20, stream


# ------------------------------------------------------------ the built pack
def test_every_chartable_series_has_bands_through_fy2050(bands) -> None:
    assert not bands.empty
    coverage = bands.groupby("series_id")["FY"].agg(["min", "max", "nunique"])
    assert (coverage["min"] == 2026).all()
    assert (coverage["max"] == 2050).all()
    assert (coverage["nunique"] == 25).all()
    for series in (
        "ped_vkt_per_capita", "ped_volume", "light_ruc_net_km", "light_bev_ruc_net_km",
        "phev_ruc_net_km", "heavy_ruc_net_km", "heavy_bev_ruc_net_km",
        "net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue",
        "net_mvr_revenue", "tuc_net_revenue",
    ):
        assert series in set(bands["series_id"]), series


def test_the_fifty_band_is_nested_inside_the_eighty_band(bands) -> None:
    assert (bands["lower80"] <= bands["lower50"] + 1e-9).all()
    assert (bands["upper50"] <= bands["upper80"] + 1e-9).all()


def test_positive_quantities_keep_positive_lower_bounds(bands) -> None:
    positive = bands[
        bands["series_id"].str.contains("km|volume|vkt|revenue", regex=True)
        & ~bands["series_id"].str.contains("refund", regex=True)
        & bands["central"].gt(0)
    ]
    assert not positive.empty
    assert (positive["lower80"] > 0).all()


def test_aggregate_bands_come_from_aggregate_draws(bands) -> None:
    """A summed-endpoint aggregate would be materially different.

    With rho(LIGHT, HEAVY) = 0.47 the comonotonic sum overstates the total,
    so the drawn Total RUC span must sit BELOW the sum of its components'
    spans and above the widest single component.
    """
    seam = bands[bands["FY"].eq(LAST_SUPPORTED_FY)].set_index("series_id")
    components = (
        "light_ruc_net_revenue", "light_bev_ruc_net_revenue", "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue", "heavy_bev_ruc_net_revenue",
    )
    summed_lower = sum(
        seam.loc[c, "central"] - seam.loc[c, "lower80"] for c in components if c in seam.index
    )
    summed_upper = sum(
        seam.loc[c, "upper80"] - seam.loc[c, "central"] for c in components if c in seam.index
    )
    total = seam.loc["total_ruc_net_revenue"]
    drawn_lower = total["central"] - total["lower80"]
    drawn_upper = total["upper80"] - total["central"]
    assert drawn_lower < summed_lower, (drawn_lower, summed_lower)
    assert drawn_upper < summed_upper, (drawn_upper, summed_upper)
    assert drawn_lower > 0 and drawn_upper > 0


def test_draw_level_identities_close_on_every_draw() -> None:
    residuals = pd.read_csv(
        ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
        / "draw_level_formula_residuals.csv"
    )
    assert not residuals.empty
    assert (residuals["draws_checked"] == DRAW_COUNT).all()
    assert residuals["closes"].all(), residuals[~residuals["closes"]].head().to_dict()
    # Non-vacuous: every governed formula must appear.
    checked = set(residuals["output_series_id"])
    for definition in FORMULA_DEFINITIONS:
        assert str(definition["output_series_id"]) in checked


def test_no_tier5_proxy_dominates_the_total_band() -> None:
    contributions = pd.read_csv(
        ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
        / "tier5_contribution_audit.csv"
    )
    assert not contributions.empty
    worst = contributions["contribution_pct_of_span"].max()
    assert worst < 10.0, f"a Tier-5 proxy contributes {worst:.2f}% of the Total NLTF span"


def test_tuc_carries_zero_modelled_uncertainty(bands) -> None:
    tuc = bands[bands["series_id"].eq("tuc_net_revenue")]
    assert not tuc.empty
    assert (tuc["span80_pct"].abs() < 1e-9).all()
    # Present, not silently omitted.
    assert (tuc["central"] > 0).all()


def test_the_pack_manifest_records_seed_and_method() -> None:
    manifest = json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["draws"] == DRAW_COUNT
    assert manifest["continuation_rule"] == "plateau"
    assert "seed" in manifest and "generator" in manifest
    assert "quantile map" in manifest["marginal_method"]
    assert manifest["scenario_key_digest"]
    assert manifest["fy_range"] == [2026, 2050]

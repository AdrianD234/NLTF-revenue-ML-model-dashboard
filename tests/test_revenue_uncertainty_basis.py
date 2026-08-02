"""The governed June-year uncertainty basis: asymmetry, plateau, evidence states.

The band must carry the observed shape of the error distribution, not a
symmetric approximation of it. These forecasts have a real downward bias - the
median actual/forecast ratio at the FY2030 seam is 0.94-0.97 across every
stream - so collapsing q10/q90 into one width and writing ``central +/- w/2``
would move the band off the evidence entirely.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.revenue_uncertainty import (
    BACKTEST_SUPPORTED,
    EXTENDED_CONDITIONAL,
    INFERRED_LONG_RUN,
    LAST_SUPPORTED_FY,
    QuantileMultipliers,
    evidence_state_for_fy,
    june_year_quantiles,
    plateau_multipliers_by_fy,
    weighted_isotonic,
)

ROOT = Path(__file__).resolve().parents[1]
JUNE_ERRORS = ROOT / "artifacts" / "long_horizon_validation" / "long_horizon_june_year_errors.csv"


@pytest.fixture(scope="module")
def basis() -> pd.DataFrame:
    if not JUNE_ERRORS.exists():
        pytest.skip("the long-horizon June-year error file is not present")
    return june_year_quantiles(pd.read_csv(JUNE_ERRORS))


# ------------------------------------------------------------- asymmetry
def test_an_asymmetric_residual_distribution_produces_an_asymmetric_band() -> None:
    """The headline requirement: shape survives into the band."""
    # A deliberately one-sided distribution: a long lower tail, a short upper.
    multipliers = QuantileMultipliers(
        q10=np.log(0.70), q25=np.log(0.90), median=np.log(0.98),
        q75=np.log(1.02), q90=np.log(1.05),
    )
    applied = multipliers.apply(1000.0)
    assert applied["lower80"] == pytest.approx(700.0)
    assert applied["upper80"] == pytest.approx(1050.0)
    lower_distance = applied["lower80_distance_pct"]
    upper_distance = applied["upper80_distance_pct"]
    assert lower_distance == pytest.approx(30.0)
    assert upper_distance == pytest.approx(5.0)
    assert lower_distance > upper_distance * 5, "the asymmetry was flattened"
    # A symmetric reconstruction would have put both sides at 17.5%.
    symmetric_half = (applied["span80_pct"] / 2.0)
    assert abs(lower_distance - symmetric_half) > 10.0


def test_the_median_bias_is_recorded_and_not_absorbed() -> None:
    multipliers = QuantileMultipliers(
        q10=np.log(0.90), q25=np.log(0.94), median=np.log(0.95),
        q75=np.log(0.97), q90=np.log(0.99),
    )
    applied = multipliers.apply(100.0)
    assert applied["median_multiplier"] == pytest.approx(0.95)
    # A wholly one-sided band is legitimate when the evidence says so.
    assert applied["upper80"] < applied["central"]


def test_the_real_basis_is_asymmetric_at_the_seam(basis) -> None:
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        multipliers = plateau_multipliers_by_fy(basis, stream)[LAST_SUPPORTED_FY]
        applied = multipliers.apply(1.0)
        assert applied["lower80_distance_pct"] != pytest.approx(
            applied["upper80_distance_pct"], rel=0.05
        ), f"{stream}: the seam band came out symmetric, which the evidence is not"
        assert applied["median_multiplier"] < 1.0, (
            f"{stream}: the recorded downward bias disappeared"
        )


# -------------------------------------------------------- basis integrity
def test_the_fifty_band_sits_inside_the_eighty_band(basis) -> None:
    for stream in basis["stream"].unique():
        for fy, multipliers in plateau_multipliers_by_fy(basis, str(stream)).items():
            applied = multipliers.apply(1000.0)
            assert applied["lower80"] <= applied["lower50"] + 1e-9, (stream, fy)
            assert applied["upper50"] <= applied["upper80"] + 1e-9, (stream, fy)
            assert applied["span50_pct"] <= applied["span80_pct"] + 1e-9, (stream, fy)


def test_dispersion_is_monotone_but_bias_is_not_forced(basis) -> None:
    """Smoothing acts on the half-widths, never on the drifting location.

    Running isotonic straight over q10/q90 would drag the median bias into the
    dispersion term; for Light RUC that inflated the FY2030 span by ~9pp of
    pure artefact.
    """
    for stream, cell in basis.groupby("stream"):
        cell = cell.sort_values("june_year_horizon")
        lower_half = -(cell["smooth_q10"] - cell["smooth_median"]).to_numpy()
        upper_half = (cell["smooth_q90"] - cell["smooth_median"]).to_numpy()
        assert np.all(np.diff(lower_half) >= -1e-9), f"{stream}: lower dispersion shrank"
        assert np.all(np.diff(upper_half) >= -1e-9), f"{stream}: upper dispersion shrank"
        # The median is carried through untouched.
        assert np.allclose(cell["smooth_median"], cell["raw_median"])


def test_raw_values_are_preserved_beside_the_smoothed_ones(basis) -> None:
    for name in ("q10", "q25", "median", "q75", "q90"):
        assert f"raw_{name}" in basis.columns
        assert f"smooth_{name}" in basis.columns
    assert "raw_span80_pct" in basis.columns and "smooth_span80_pct" in basis.columns


def test_every_cell_reports_rows_and_independent_origins(basis) -> None:
    assert (basis["n_rows"] > 0).all()
    assert (basis["n_origins"] > 0).all()
    # Rolling-origin rows overlap, so origins must never exceed rows.
    assert (basis["n_origins"] <= basis["n_rows"]).all()


def test_the_bootstrap_is_origin_clustered_and_deterministic(basis) -> None:
    for column in ("boot_q10_p05", "boot_q10_p95", "boot_q90_p05", "boot_q90_p95"):
        assert column in basis.columns
    assert (basis["boot_q10_p05"] <= basis["boot_q10_p95"] + 1e-12).all()
    repeat = june_year_quantiles(pd.read_csv(JUNE_ERRORS))
    pd.testing.assert_frame_equal(
        basis.reset_index(drop=True), repeat.reset_index(drop=True)
    )


# --------------------------------------------------- plateau and labelling
def test_the_plateau_holds_the_seam_constant_to_fy2050(basis) -> None:
    for stream in basis["stream"].unique():
        by_fy = plateau_multipliers_by_fy(basis, str(stream))
        seam = by_fy[LAST_SUPPORTED_FY]
        for fy in range(LAST_SUPPORTED_FY + 1, 2051):
            assert by_fy[fy] == seam, f"{stream}: FY{fy} drifted off the plateau"
        assert 2050 in by_fy and 2026 in by_fy


def test_the_three_evidence_states_map_to_the_agreed_years() -> None:
    assert evidence_state_for_fy(2026) == BACKTEST_SUPPORTED
    assert evidence_state_for_fy(2028) == BACKTEST_SUPPORTED
    assert evidence_state_for_fy(2029) == EXTENDED_CONDITIONAL
    assert evidence_state_for_fy(2030) == EXTENDED_CONDITIONAL
    assert evidence_state_for_fy(2031) == INFERRED_LONG_RUN
    assert evidence_state_for_fy(2050) == INFERRED_LONG_RUN


def test_weighted_isotonic_respects_the_weights() -> None:
    x = np.array([1.0, 2.0, 3.0])
    # A thin final cell dipping must not drag the curve down.
    y = np.array([1.0, 2.0, 1.2])
    heavy = weighted_isotonic(x, y, np.array([10.0, 10.0, 1.0]))
    assert np.all(np.diff(heavy) >= -1e-9)
    assert heavy[-1] >= heavy[-2] - 1e-9

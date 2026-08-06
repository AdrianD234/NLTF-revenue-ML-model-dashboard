"""Seeded draw generation for the Revenue Outlook modelled-uncertainty bands.

Three independent parent shocks - PED, LIGHT_RUC, HEAVY_RUC - are drawn jointly
and then propagated through the governed identities.  Everything else in the
model inherits one of those draws, which is why the aggregate band has to be
computed from aggregate draws rather than by summing marginal endpoints.

Marginals are the committed June-year rolling-origin log errors, quantile-mapped
onto the governed smoothed targets.  The map is monotone and piecewise linear,
pinned at q10/q25/median/q75/q90, so:

* the governed quantiles are reproduced exactly at the knots;
* the empirical asymmetry and the measured median bias survive;
* no normal approximation ever touches the values.

Dependence across parents is a Gaussian copula on a shrunk Spearman rank
correlation.  Rank rather than Pearson, because the marginals are skewed and a
Pearson estimate would be driven by the same tail observations the band exists
to describe.

Conditional on the selected VFM shares, conventional Light, Light BEV and PHEV
are **perfectly dependent**: they all ride one Light-parent draw.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .revenue_uncertainty import (
    QUANTILE_LEVELS,
    QuantileMultipliers,
    plateau_multipliers_by_fy,
)

__all__ = [
    "CORRELATION_MIN_ALIGNED",
    "DRAW_COUNT",
    "DRAW_SEED",
    "PARENT_STREAMS",
    "aligned_parent_log_errors",
    "generate_parent_factor_draws",
    "parent_log_error_samples",
    "quantile_mapped_sample",
    "shrunk_rank_correlation",
]

DRAW_SEED = 20260801
DRAW_COUNT = 10_000
PARENT_STREAMS = ("PED", "LIGHT_RUC", "HEAVY_RUC")
# Full weight on the sample rank correlation at or above this many aligned
# observations; shrunk linearly toward the identity below it.
CORRELATION_MIN_ALIGNED = 12


def _scored_log_errors(june_errors: pd.DataFrame) -> pd.DataFrame:
    frame = june_errors.copy()
    frame = frame[
        frame["cohort"].astype(str).eq("all_available")
        & frame["target_window"].astype(str).eq("all_targets")
    ]
    frame["actual"] = pd.to_numeric(frame["actual"], errors="coerce")
    frame["pred"] = pd.to_numeric(frame["pred"], errors="coerce")
    frame = frame[(frame["actual"] > 0) & (frame["pred"] > 0)].copy()
    frame["log_error"] = np.log(frame["actual"] / frame["pred"])
    return frame


def parent_log_error_samples(june_errors: pd.DataFrame) -> dict[str, np.ndarray]:
    """The empirical log-error SHAPE per parent, pooled over June-year horizons.

    Pooled so the sample is rich enough to carry a tail shape. It supplies
    shape only - the quantile map onto the governed per-FY targets is what
    fixes the level, so pooling cannot leak a short-horizon level into a long
    one.
    """
    frame = _scored_log_errors(june_errors)
    return {
        str(stream): cell["log_error"].to_numpy()
        for stream, cell in frame.groupby("stream")
        if str(stream) in PARENT_STREAMS
    }


def aligned_parent_log_errors(june_errors: pd.DataFrame) -> pd.DataFrame:
    """One row per (origin, june_year), one column per parent stream.

    Only rows scored on the SAME origin and target year can say anything about
    cross-stream dependence.
    """
    frame = _scored_log_errors(june_errors)
    wide = frame.pivot_table(
        index=["origin", "june_year"], columns="stream", values="log_error", aggfunc="mean"
    )
    keep = [stream for stream in PARENT_STREAMS if stream in wide.columns]
    return wide[keep].dropna()


def shrunk_rank_correlation(aligned: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Spearman rank correlation, shrunk toward the identity when thin."""
    streams = list(aligned.columns)
    size = len(streams)
    n_aligned = int(len(aligned))
    if size < 2 or n_aligned < 3:
        return np.eye(max(size, 1)), {
            "n_aligned": n_aligned,
            "shrinkage": 1.0,
            "streams": ",".join(streams),
            "reason": "too few aligned observations; independence assumed",
        }
    raw = aligned.corr(method="spearman").to_numpy()
    weight = min(1.0, n_aligned / float(CORRELATION_MIN_ALIGNED))
    shrunk = weight * raw + (1.0 - weight) * np.eye(size)
    np.fill_diagonal(shrunk, 1.0)
    eigenvalues, eigenvectors = np.linalg.eigh(shrunk)
    if eigenvalues.min() < 1e-10:
        eigenvalues = np.clip(eigenvalues, 1e-10, None)
        shrunk = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
        scale = np.sqrt(np.diag(shrunk))
        shrunk = shrunk / np.outer(scale, scale)
    return shrunk, {
        "n_aligned": n_aligned,
        "shrinkage": round(1.0 - weight, 6),
        "streams": ",".join(streams),
        "reason": (
            "full weight on the sample estimate"
            if weight >= 1.0
            else f"shrunk toward identity: {n_aligned} < {CORRELATION_MIN_ALIGNED} aligned rows"
        ),
    }


def quantile_mapped_sample(
    sample: np.ndarray, target: QuantileMultipliers, *, size: int
) -> np.ndarray:
    """Map an empirical sample onto the governed target quantiles.

    Monotone and piecewise linear, pinned at the five governed knots, with the
    outer segments' slopes used to stretch the tails rather than clip them.
    """
    if len(sample) == 0:
        return np.full(size, float(target.median))
    source = np.quantile(sample, list(QUANTILE_LEVELS))
    goal = np.array([target.q10, target.q25, target.median, target.q75, target.q90])
    if not np.all(np.diff(source) > 0):
        # A degenerate knot sequence cannot define a slope; nudge it apart.
        source = source + np.linspace(0.0, 1e-9, len(source))
    grid = np.quantile(sample, np.linspace(0.0, 1.0, size))
    mapped = np.interp(grid, source, goal)
    lower_slope = (goal[1] - goal[0]) / (source[1] - source[0])
    upper_slope = (goal[-1] - goal[-2]) / (source[-1] - source[-2])
    below = grid < source[0]
    above = grid > source[-1]
    mapped[below] = goal[0] + lower_slope * (grid[below] - source[0])
    mapped[above] = goal[-1] + upper_slope * (grid[above] - source[-1])
    return mapped


def generate_parent_factor_draws(
    june_errors: pd.DataFrame,
    quantiles: pd.DataFrame,
    *,
    draws: int = DRAW_COUNT,
    seed: int = DRAW_SEED,
) -> tuple[dict[int, dict[str, np.ndarray]], dict]:
    """FY -> stream -> multiplicative factor draws, plus a provenance record.

    One draw index means the same joint state for every stream and every FY,
    which is what lets an aggregate be evaluated draw by draw.
    """
    from scipy.stats import norm

    samples = parent_log_error_samples(june_errors)
    aligned = aligned_parent_log_errors(june_errors)
    correlation, correlation_audit = shrunk_rank_correlation(aligned)
    streams = list(aligned.columns) or [s for s in PARENT_STREAMS if s in samples]

    generator = np.random.default_rng(seed)
    normal = generator.multivariate_normal(
        np.zeros(len(streams)), correlation, size=draws, method="cholesky"
    )
    uniforms = norm.cdf(normal)

    by_fy: dict[int, dict[str, np.ndarray]] = {}
    for stream_index, stream in enumerate(streams):
        multipliers = plateau_multipliers_by_fy(quantiles, stream)
        sample = samples.get(stream, np.array([]))
        order = np.argsort(uniforms[:, stream_index])
        for fy, target in multipliers.items():
            mapped = np.sort(quantile_mapped_sample(sample, target, size=draws))
            # Place the sorted marginal at this stream's copula ranks: the
            # marginal stays exact and the dependence is honoured.
            factors = np.empty(draws)
            factors[order] = mapped
            by_fy.setdefault(int(fy), {})[stream] = np.exp(factors)

    provenance = {
        "seed": seed,
        "draws": draws,
        "generator": "numpy.random.default_rng(seed).multivariate_normal(cholesky) + scipy.stats.norm.cdf",
        "marginal_method": "monotone piecewise-linear quantile map of the pooled empirical June-year sample",
        "continuation_rule": "plateau",
        "streams": ",".join(streams),
        **{f"correlation_{key}": value for key, value in correlation_audit.items()},
    }
    for row, stream_a in enumerate(streams):
        for column, stream_b in enumerate(streams):
            if column > row:
                provenance[f"rho_{stream_a}_{stream_b}"] = round(float(correlation[row, column]), 6)
    return by_fy, provenance

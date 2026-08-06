"""The governed June-year uncertainty basis for the Revenue Outlook.

Owner-approved contract:

* **Basis** - the June-year aggregation of the rolling-origin evaluation. The
  chart is a June-year chart, and quarterly errors are not interchangeable with
  annual ones (within-year noise partly cancels), so the quarterly H1-H20 view
  is a diagnostic and a cross-check, never the production band level.
* **Continuation** - ``plateau``: the smoothed June-year H5 quantile
  multipliers are held constant from FY2031 to FY2050. Saturating and
  square-root continuations are audit/stress only.
* **Evidence states** - FY2026-FY2028 ``backtest_supported_conditional``,
  FY2029-FY2030 ``extended_conditional``, FY2031-FY2050 ``inferred_long_run``.
* **Conditional** - the rolling-origin evaluation is ACTUAL-DRIVER: exogenous
  inputs at each target are the observed values. It isolates model degradation
  and understates true forward error, which also carries Treasury-driver
  error. Every label says ``conditional`` for that reason.

Bands are **asymmetric**. The quantile multipliers ``exp(q10)``, ``exp(q25)``,
``exp(q75)``, ``exp(q90)`` are carried separately and applied to the central
path; they are never collapsed into one symmetric width. The median multiplier
is recorded so bias is visible rather than silently absorbed.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd

__all__ = [
    "EVIDENCE_STATES",
    "FINAL_FY",
    "LAST_ACTUAL_FY",
    "LAST_SUPPORTED_FY",
    "QUANTILE_LEVELS",
    "QuantileMultipliers",
    "evidence_state_for_fy",
    "june_year_horizon",
    "june_year_quantiles",
    "plateau_multipliers_by_fy",
    "weighted_isotonic",
]

LAST_ACTUAL_FY = 2025
LAST_SUPPORTED_JUNE_YEAR_HORIZON = 5
LAST_SUPPORTED_FY = LAST_ACTUAL_FY + LAST_SUPPORTED_JUNE_YEAR_HORIZON  # FY2030
FINAL_FY = 2050

BACKTEST_SUPPORTED = "backtest_supported_conditional"
EXTENDED_CONDITIONAL = "extended_conditional"
INFERRED_LONG_RUN = "inferred_long_run"
EVIDENCE_STATES = (BACKTEST_SUPPORTED, EXTENDED_CONDITIONAL, INFERRED_LONG_RUN)

QUANTILE_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)
QUANTILE_NAMES = ("q10", "q25", "median", "q75", "q90")

BOOTSTRAP_SEED = 20260801
BOOTSTRAP_DRAWS = 2000


def june_year_horizon(fy: int) -> int:
    return int(fy) - LAST_ACTUAL_FY


def evidence_state_for_fy(fy: int) -> str:
    """FY2026-28 backtest-supported, FY2029-30 extended, FY2031+ inferred."""
    horizon = june_year_horizon(fy)
    if horizon <= 3:
        return BACKTEST_SUPPORTED
    if horizon <= LAST_SUPPORTED_JUNE_YEAR_HORIZON:
        return EXTENDED_CONDITIONAL
    return INFERRED_LONG_RUN


@dataclasses.dataclass(frozen=True)
class QuantileMultipliers:
    """Asymmetric multipliers applied to a central value.

    ``lower80 = central * exp(q10)`` and so on. Kept as separate sides so the
    observed asymmetry and any median bias survive into the chart instead of
    being averaged away into one width.
    """

    q10: float
    q25: float
    median: float
    q75: float
    q90: float

    def multipliers(self) -> dict[str, float]:
        return {
            "lower80_multiplier": float(np.exp(self.q10)),
            "lower50_multiplier": float(np.exp(self.q25)),
            "median_multiplier": float(np.exp(self.median)),
            "upper50_multiplier": float(np.exp(self.q75)),
            "upper80_multiplier": float(np.exp(self.q90)),
        }

    def apply(self, central: float) -> dict[str, float]:
        """Applied band values, plus the pure multipliers and side distances.

        The applied values are named for what they are (``lower80``), and the
        unscaled ratios keep the ``_multiplier`` suffix, so a caller cannot mix
        a $m value up with a ratio.
        """
        scaled = {
            name.replace("_multiplier", ""): central * value
            for name, value in self.multipliers().items()
        }
        out: dict[str, float] = {**scaled, **self.multipliers()}
        out["central"] = central
        span80 = out["upper80_multiplier"] - out["lower80_multiplier"]
        span50 = out["upper50_multiplier"] - out["lower50_multiplier"]
        out["span80_pct"] = 100.0 * span80
        out["span50_pct"] = 100.0 * span50
        # Distances, so an asymmetric band is auditable side by side.
        out["lower80_distance_pct"] = 100.0 * (1.0 - float(np.exp(self.q10)))
        out["upper80_distance_pct"] = 100.0 * (float(np.exp(self.q90)) - 1.0)
        out["lower50_distance_pct"] = 100.0 * (1.0 - float(np.exp(self.q25)))
        out["upper50_distance_pct"] = 100.0 * (float(np.exp(self.q75)) - 1.0)
        out["asymmetry_ratio_80"] = (
            out["upper80_distance_pct"] / out["lower80_distance_pct"]
            if out["lower80_distance_pct"] not in (0.0,)
            else float("nan")
        )
        return out


def weighted_isotonic(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted monotone non-decreasing fit.

    Applied to the OUTER quantile magnitudes so uncertainty cannot shrink with
    horizon through sampling noise. Cells are weighted by their effective
    origin count, so a thin H5 cell cannot drag the curve.
    """
    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(increasing=True, out_of_bounds="clip")
    return model.fit_transform(x, y, sample_weight=weights)


def _cluster_bootstrap(
    frame: pd.DataFrame, level: float, *, value_column: str, origin_column: str
) -> tuple[float, float, float]:
    """Percentile bootstrap resampling ORIGINS, not rows.

    Rolling-origin rows overlap: one origin contributes several June years, so
    treating rows as independent would understate the sampling uncertainty.
    """
    origins = frame[origin_column].astype(str).to_numpy()
    unique = np.unique(origins)
    if len(unique) < 3:
        return (float("nan"), float("nan"), float("nan"))
    values = frame[value_column].to_numpy()
    by_origin = {origin: values[origins == origin] for origin in unique}
    generator = np.random.default_rng(BOOTSTRAP_SEED)
    draws = np.empty(BOOTSTRAP_DRAWS)
    for index in range(BOOTSTRAP_DRAWS):
        picked = generator.choice(unique, size=len(unique), replace=True)
        pooled = np.concatenate([by_origin[origin] for origin in picked])
        draws[index] = np.quantile(pooled, level)
    return tuple(float(value) for value in np.quantile(draws, [0.05, 0.50, 0.95]))


def june_year_quantiles(
    june_errors: pd.DataFrame,
    *,
    cohort: str = "all_available",
    target_window: str = "all_targets",
    bootstrap: bool = True,
) -> pd.DataFrame:
    """Raw and weighted-isotonic June-year quantiles per stream and horizon.

    Returns one row per (stream, june_year_horizon) with raw quantiles, their
    origin-clustered bootstrap intervals, the smoothed quantiles, and the
    sample and origin counts behind each cell.
    """
    frame = june_errors.copy()
    frame = frame[
        frame["cohort"].astype(str).eq(cohort)
        & frame["target_window"].astype(str).eq(target_window)
    ]
    frame["actual"] = pd.to_numeric(frame["actual"], errors="coerce")
    frame["pred"] = pd.to_numeric(frame["pred"], errors="coerce")
    frame = frame[(frame["actual"] > 0) & (frame["pred"] > 0)].copy()
    frame["log_error"] = np.log(frame["actual"] / frame["pred"])
    frame["june_year_horizon"] = (
        (pd.to_numeric(frame["first_horizon"], errors="coerce") + 3) / 4
    ).round().astype(int)
    frame = frame[
        frame["june_year_horizon"].between(1, LAST_SUPPORTED_JUNE_YEAR_HORIZON)
    ]

    rows: list[dict] = []
    for (stream, horizon), cell in frame.groupby(["stream", "june_year_horizon"]):
        values = cell["log_error"].to_numpy()
        record: dict = {
            "stream": str(stream),
            "june_year_horizon": int(horizon),
            "evidence_state": evidence_state_for_fy(LAST_ACTUAL_FY + int(horizon)),
            "n_rows": int(len(values)),
            "n_origins": int(cell["origin"].astype(str).nunique()),
        }
        for name, level in zip(QUANTILE_NAMES, QUANTILE_LEVELS):
            record[f"raw_{name}"] = float(np.quantile(values, level))
            if bootstrap:
                p05, p50, p95 = _cluster_bootstrap(
                    cell, level, value_column="log_error", origin_column="origin"
                )
                record[f"boot_{name}_p05"] = p05
                record[f"boot_{name}_p50"] = p50
                record[f"boot_{name}_p95"] = p95
        rows.append(record)

    table = pd.DataFrame(rows).sort_values(["stream", "june_year_horizon"])

    # Smooth DISPERSION, not the raw quantiles.
    #
    # A quantile carries both the location (median bias) and the spread. These
    # forecasts have a real downward bias that drifts with horizon, so running
    # isotonic straight over q10/q90 forces the drifting LOCATION to be monotone
    # too. For Light RUC that inflated the FY2030 80% span from a raw 23.1% to
    # 33.1% - not a wider distribution, just a bias being dragged into the
    # dispersion term. Decompose first, smooth the half-widths around the
    # median, then recombine.
    smoothed_frames: list[pd.DataFrame] = []
    for stream, cell in table.groupby("stream"):
        cell = cell.sort_values("june_year_horizon").copy()
        horizons = cell["june_year_horizon"].to_numpy(dtype=float)
        weights = cell["n_origins"].to_numpy(dtype=float)
        median = cell["raw_median"].to_numpy(dtype=float)
        # Bias is not monotone in horizon and is not dispersion: carry it raw.
        cell["smooth_median"] = median
        for name in ("q10", "q25", "q75", "q90"):
            raw = cell[f"raw_{name}"].to_numpy(dtype=float)
            sign = -1.0 if name in ("q10", "q25") else 1.0
            # Half-width on this side of the median, in log space.
            half_width = sign * (raw - median)
            smooth_half = np.maximum(weighted_isotonic(horizons, half_width, weights), 0.0)
            cell[f"smooth_{name}"] = median + sign * smooth_half
        smoothed_frames.append(cell)
    smoothed = pd.concat(smoothed_frames, ignore_index=True)

    for level, lower, upper in (("80", "q10", "q90"), ("50", "q25", "q75")):
        smoothed[f"raw_span{level}_pct"] = 100.0 * (
            np.exp(smoothed[f"raw_{upper}"]) - np.exp(smoothed[f"raw_{lower}"])
        )
        smoothed[f"smooth_span{level}_pct"] = 100.0 * (
            np.exp(smoothed[f"smooth_{upper}"]) - np.exp(smoothed[f"smooth_{lower}"])
        )
    return smoothed


def plateau_multipliers_by_fy(quantiles: pd.DataFrame, stream: str) -> dict[int, QuantileMultipliers]:
    """FY -> multipliers under the approved plateau rule.

    Inside the evidence the smoothed June-year curve governs. From FY2031 the
    smoothed H5 distribution is held constant to FY2050.
    """
    cell = quantiles[quantiles["stream"].astype(str).eq(stream)].set_index("june_year_horizon")
    if cell.empty:
        return {}
    out: dict[int, QuantileMultipliers] = {}
    seam = cell.loc[LAST_SUPPORTED_JUNE_YEAR_HORIZON]
    for fy in range(LAST_ACTUAL_FY + 1, FINAL_FY + 1):
        horizon = june_year_horizon(fy)
        row = cell.loc[horizon] if horizon <= LAST_SUPPORTED_JUNE_YEAR_HORIZON else seam
        out[fy] = QuantileMultipliers(
            q10=float(row["smooth_q10"]),
            q25=float(row["smooth_q25"]),
            median=float(row["smooth_median"]),
            q75=float(row["smooth_q75"]),
            q90=float(row["smooth_q90"]),
        )
    return out

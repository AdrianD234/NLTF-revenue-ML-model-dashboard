"""Present-value utilities for the Revenue Outlook scenario comparison.

Discounting follows the NZTA Monetised Benefits and Costs Manual (MBCM)
schedule by default: 2.0% p.a. for the first 30 years and 1.5% p.a.
thereafter. The dashboard's forecast horizon (FY2026-FY2050, 25 years from
the FY2026 anchor) never reaches the 1.5% leg, but the schedule is
implemented generically so a longer horizon would discount correctly. A
single-rate override supports sensitivity testing against e.g. Treasury
conventions.

Only monetised streams are discounted: a "present-value kilometre" has no
economic meaning, and the MBCM applies discounting to dollar flows only, so
physical quantities (km, litres, VKT per capita) are summarised as
cumulative and average-annual totals instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MBCM_RATE_FIRST = 0.02
MBCM_RATE_AFTER = 0.015
MBCM_SWITCH_YEAR = 30
NPV_ANCHOR_FY = 2026


def mbcm_discount_factors(n_years: int) -> np.ndarray:
    """Discount factors for t = 0..n_years-1 under the MBCM schedule.

    Factor(t) = 1 / ((1+r1)^min(t,30) * (1+r2)^max(t-30, 0)).
    """
    t = np.arange(max(int(n_years), 0))
    first = np.minimum(t, MBCM_SWITCH_YEAR)
    later = np.maximum(t - MBCM_SWITCH_YEAR, 0)
    divisors = np.power(1.0 + MBCM_RATE_FIRST, first) * np.power(1.0 + MBCM_RATE_AFTER, later)
    return 1.0 / divisors


def single_rate_discount_factors(n_years: int, rate: float) -> np.ndarray:
    t = np.arange(max(int(n_years), 0))
    return 1.0 / np.power(1.0 + float(rate), t)


def npv_to_horizon(values_by_fy: pd.Series, *, anchor_fy: int = NPV_ANCHOR_FY, rate: float | None = None) -> float:
    """NPV of an FY-indexed nominal series, discounted to the anchor year.

    ``rate=None`` uses the MBCM schedule; otherwise a flat single rate.
    Years before the anchor are excluded; NaNs are dropped.
    """
    if values_by_fy is None or len(values_by_fy) == 0:
        return float("nan")
    series = pd.Series(values_by_fy).copy()
    series.index = pd.to_numeric(pd.Series(series.index), errors="coerce").to_numpy()
    series = series.dropna()
    series = series[series.index >= anchor_fy]
    if series.empty:
        return float("nan")
    offsets = (series.index - anchor_fy).astype(int)
    horizon = int(offsets.max()) + 1
    factors = mbcm_discount_factors(horizon) if rate is None else single_rate_discount_factors(horizon, rate)
    return float(np.sum(series.to_numpy(dtype=float) * factors[offsets]))


def cumulative_total(values_by_fy: pd.Series) -> float:
    if values_by_fy is None or len(values_by_fy) == 0:
        return float("nan")
    return float(pd.to_numeric(pd.Series(values_by_fy), errors="coerce").dropna().sum())


def average_annual(values_by_fy: pd.Series) -> float:
    if values_by_fy is None or len(values_by_fy) == 0:
        return float("nan")
    clean = pd.to_numeric(pd.Series(values_by_fy), errors="coerce").dropna()
    return float(clean.mean()) if not clean.empty else float("nan")


def horizon_label(values_by_fy: pd.Series) -> str:
    if values_by_fy is None or len(values_by_fy) == 0:
        return ""
    years = pd.to_numeric(pd.Series(pd.Series(values_by_fy).index), errors="coerce").dropna().astype(int)
    if years.empty:
        return ""
    return f"FY{years.min()}–FY{years.max()} ({years.nunique()} years)"


def mbcm_label() -> str:
    return (
        f"NZTA MBCM ({MBCM_RATE_FIRST:.1%} p.a.; {MBCM_RATE_AFTER:.1%} beyond year {MBCM_SWITCH_YEAR})"
    )

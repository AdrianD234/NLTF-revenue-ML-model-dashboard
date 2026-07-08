"""EV/PHEV uptake lever engine grounded in the MoT Vehicle Fleet Model.

The MoT VFM (202405) projects power-type shares of the light-vehicle fleet
from a TCO multinomial-logit registration model plus scrappage-driven fleet
turnover. On the VKT stock level that machinery reduces, to within ~1.5pp
over 2025-2050, to two interpretable curves:

- BEV share of the light RUC pool: a logistic S-curve parameterised by three
  human levers - peak uptake speed (pp/yr), peak adoption year, and the 2050
  share.
- PHEV share: a transition hump - linear rise (pp/yr) from the current share
  to a peak, then exponential decay (%/yr).

Presets are fitted to the vendored VFM 202405 Base/Fast/Slow scenarios
(data/vfm_202405/vfm_vkt_shares.csv, hash-backed to the source workbook) and
to the MBU26 official light-mobility proportions. Conventional light RUC is
the remainder, so scenario totals allocated with these shares can never
produce the terminal-year base/high-population crossing that the legacy
universe-scaled migration subtraction allowed.

The engine is a display-time overlay: governed pack values stay untouched
and overlay rows are tagged (value_status="lever_adjusted").
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np
import pandas as pd

VFM_SOURCE_NOTE = (
    "Share curves are the reduced form of the MoT Vehicle Fleet Model 202405 "
    "(TCO logit registrations + scrappage fleet turnover); presets reproduce "
    "the official Base/Fast/Slow scenario VKT shares within ~1.5pp over "
    "2025-2050 (see data/vfm_202405/)."
)

LEVER_SERIES_KM = {
    "light_ruc_net_km": "conventional",
    "light_bev_ruc_net_km": "bev",
    "phev_ruc_net_km": "phev",
}
LEVER_SERIES_REVENUE = {
    "light_ruc_net_revenue": ("conventional", "conventional_light_rate"),
    "light_bev_ruc_net_revenue": ("bev", "light_bev_rate"),
    "phev_ruc_net_revenue": ("phev", "phev_rate"),
}
# Aggregate june-year revenue series that contain the three light RUC revenue
# components additively (admin fees and refunds are unaffected by the split).
LEVER_AGGREGATE_SERIES = (
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_gross_revenue",
    "total_revenue_net_admin",
    "total_nltf_net_revenue",
)


@dataclass(frozen=True)
class UptakeLevers:
    """Human levers for the light RUC pool power-type split."""

    bev_peak_speed_pp: float  # peak BEV uptake speed, share points per year
    bev_peak_year: float  # year of fastest adoption (logistic midpoint)
    bev_share_2050: float  # BEV share of the light RUC pool in FY2050
    phev_start_share: float  # PHEV share at FY2025
    phev_rise_pp: float  # PHEV linear rise, share points per year
    phev_peak_share: float  # PHEV peak share
    phev_decay_rate: float  # PHEV post-peak exponential decay per year

    def key(self) -> tuple[float, ...]:
        return tuple(round(float(v), 6) for v in asdict(self).values())


EV_UPTAKE_PRESETS: dict[str, UptakeLevers] = {
    # Fitted to MBU26 official light-mobility proportions (max error 1.5pp).
    "MBU26 official shape": UptakeLevers(0.045, 2038.0, 0.82, 0.030, 0.010, 0.140, 0.065),
    # Fitted to MoT VFM 202405 scenarios (max error <=1.5pp each).
    "MoT VFM base": UptakeLevers(0.0425, 2038.0, 0.83, 0.036, 0.011, 0.155, 0.060),
    "MoT VFM fast": UptakeLevers(0.0475, 2036.5, 0.86, 0.039, 0.013, 0.175, 0.065),
    "MoT VFM slow": UptakeLevers(0.0425, 2039.5, 0.78, 0.034, 0.009, 0.135, 0.055),
}
GOVERNED_PACK_OPTION = "Governed pack (MBU26 λ-migration)"
CUSTOM_OPTION = "Custom levers"
EV_UPTAKE_MODE_OPTIONS = (GOVERNED_PACK_OPTION, *EV_UPTAKE_PRESETS.keys(), CUSTOM_OPTION)
DEFAULT_EV_UPTAKE_MODE = GOVERNED_PACK_OPTION


def solve_logistic_from_levers(peak_speed: float, peak_year: float, share_2050: float) -> tuple[float, float]:
    """Return (saturation, steepness) of the logistic implied by the levers.

    The logistic s(t) = smax / (1 + exp(-k (t - t0))) has its maximum slope
    smax*k/4 at t0; bisect on smax so the curve passes through the 2050 share.
    """
    peak_speed = max(float(peak_speed), 1e-4)
    share_2050 = min(max(float(share_2050), 1e-3), 0.999)
    lo, hi = share_2050 + 1e-6, 1.0
    smax = hi
    for _ in range(80):
        smax = (lo + hi) / 2
        k = 4.0 * peak_speed / smax
        s50 = smax / (1.0 + np.exp(-k * (2050.0 - float(peak_year))))
        if s50 > share_2050:
            hi = smax
        else:
            lo = smax
    return smax, 4.0 * peak_speed / smax


def lever_share_curves(june_years: Any, levers: UptakeLevers) -> pd.DataFrame:
    """BEV/PHEV/conventional shares of the light RUC pool for the given years."""
    years = np.asarray(list(june_years), dtype=float)
    smax, k = solve_logistic_from_levers(levers.bev_peak_speed_pp, levers.bev_peak_year, levers.bev_share_2050)
    bev = smax / (1.0 + np.exp(-k * (years - float(levers.bev_peak_year))))
    rise = max(float(levers.phev_rise_pp), 1e-6)
    peak = max(float(levers.phev_peak_share), float(levers.phev_start_share))
    peak_year = 2025.0 + (peak - float(levers.phev_start_share)) / rise
    phev = np.where(
        years <= peak_year,
        np.minimum(float(levers.phev_start_share) + rise * (years - 2025.0), peak),
        peak * np.exp(-float(levers.phev_decay_rate) * (years - peak_year)),
    )
    phev = np.clip(phev, 0.0, None)
    # Conventional is the remainder; guard against lever combinations that
    # exceed the pool and renormalise BEV+PHEV proportionally if they do.
    ev_total = bev + phev
    overflow = ev_total > 0.995
    if overflow.any():
        scale = np.where(overflow, 0.995 / ev_total, 1.0)
        bev = bev * scale
        phev = phev * scale
    conventional = 1.0 - bev - phev
    return pd.DataFrame({"june_year": years.astype(int), "bev": bev, "phev": phev, "conventional": conventional})


def _drift_rate_lookup(drift: pd.DataFrame) -> dict[tuple[str, int], dict[str, float]]:
    """Per (scenario, FY): MBU26 per-km revenue rates for the light RUC classes."""
    if drift is None or drift.empty or "lambda_mode" not in drift.columns:
        return {}
    rows = drift[drift["lambda_mode"].astype(str).eq("optimized")]
    lookup: dict[tuple[str, int], dict[str, float]] = {}
    for record in rows.itertuples():
        fy = pd.to_numeric(pd.Series([record.FY]), errors="coerce").iloc[0]
        if pd.isna(fy):
            continue
        lookup[(str(record.scenario_name), int(fy))] = {
            "conventional_light_rate": float(getattr(record, "conventional_light_rate", float("nan"))),
            "light_bev_rate": float(getattr(record, "light_bev_rate", float("nan"))),
            "phev_rate": float(getattr(record, "phev_rate", float("nan"))),
        }
    return lookup


def _pool_from_chart_rows(data: pd.DataFrame, base_mask: pd.Series, numeric_value: pd.Series) -> float | None:
    """Full light RUC universe = sum of the three displayed km series."""
    total = 0.0
    for series_id in LEVER_SERIES_KM:
        mask = base_mask & data["series_id"].astype(str).eq(series_id)
        if not mask.any() or not numeric_value[mask].notna().any():
            return None
        total += float(numeric_value[mask].iloc[0])
    return total


def apply_uptake_levers_to_chart_rows(
    chart_rows: pd.DataFrame,
    drift_assumptions: pd.DataFrame,
    levers: UptakeLevers,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reallocate the light RUC pool with lever shares (display overlay).

    The pool for each (scenario, FY) is the full displayed light RUC universe
    - the sum of the conventional/BEV/PHEV km series in the pack - so the
    scenario's own total (and therefore population response) is preserved
    exactly; only the power-type split changes. Revenue lines are recomputed
    with the MBU26 per-km rates carried in the drift table and aggregate
    revenue series receive the additive delta. Quarterly rows and historical
    actuals are untouched.
    """
    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame()
    rate_lookup = _drift_rate_lookup(drift_assumptions)
    if not rate_lookup:
        return chart_rows, pd.DataFrame()

    fys = sorted({fy for _, fy in rate_lookup})
    shares = lever_share_curves(fys, levers).set_index("june_year")

    data = chart_rows.copy()
    numeric_value = pd.to_numeric(data.get("value"), errors="coerce")
    june_year = pd.to_numeric(data.get("june_year"), errors="coerce")
    is_june = data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")
    is_forecast = ~data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("historical_actual")

    audit_rows: list[dict[str, Any]] = []
    delta_by_key: dict[tuple[str, int], float] = {}
    for (scenario, fy), rates in rate_lookup.items():
        share_row = shares.loc[fy] if fy in shares.index else None
        if share_row is None:
            continue
        share_values = {
            "conventional": float(share_row["conventional"]),
            "bev": float(share_row["bev"]),
            "phev": float(share_row["phev"]),
        }
        scenario_mask = data.get("scenario_name", pd.Series("", index=data.index)).astype(str).eq(scenario)
        base_mask = is_june & is_forecast & scenario_mask & june_year.eq(fy)
        pool_km = _pool_from_chart_rows(data, base_mask, numeric_value)
        if pool_km is None or pool_km <= 0:
            continue
        revenue_delta = 0.0
        for series_id, component in LEVER_SERIES_KM.items():
            mask = base_mask & data["series_id"].astype(str).eq(series_id)
            if not mask.any():
                continue
            new_km = pool_km * share_values[component]
            data.loc[mask, "value"] = new_km
        for series_id, (component, rate_key) in LEVER_SERIES_REVENUE.items():
            mask = base_mask & data["series_id"].astype(str).eq(series_id)
            if not mask.any() or not np.isfinite(rates[rate_key]):
                continue
            new_revenue = pool_km * share_values[component] * rates[rate_key]
            old_revenue = float(numeric_value[mask].iloc[0]) if numeric_value[mask].notna().any() else 0.0
            revenue_delta += new_revenue - old_revenue
            data.loc[mask, "value"] = new_revenue
        if revenue_delta:
            delta_by_key[(scenario, fy)] = revenue_delta
        audit_rows.append(
            {
                "scenario_name": scenario,
                "june_year": fy,
                "light_ruc_pool_km": pool_km,
                "conventional_share": share_values["conventional"],
                "bev_share": share_values["bev"],
                "phev_share": share_values["phev"],
                "light_revenue_delta_vs_pack": revenue_delta,
            }
        )

    if delta_by_key:
        aggregate_mask = (
            is_june
            & is_forecast
            & data["series_id"].astype(str).isin(LEVER_AGGREGATE_SERIES)
        )
        for index in data.index[aggregate_mask]:
            key = (str(data.at[index, "scenario_name"]), int(june_year.at[index]) if pd.notna(june_year.at[index]) else -1)
            delta = delta_by_key.get(key)
            if delta and pd.notna(numeric_value.at[index]):
                data.at[index, "value"] = float(numeric_value.at[index]) + delta

    touched = (
        is_june
        & is_forecast
        & data["series_id"].astype(str).isin(
            set(LEVER_SERIES_KM) | set(LEVER_SERIES_REVENUE) | set(LEVER_AGGREGATE_SERIES)
        )
    )
    if "value_status" in data.columns:
        data.loc[touched, "value_status"] = "lever_adjusted"
    if "data_scope" in data.columns:
        data.loc[touched, "data_scope"] = "ev_uptake_lever_overlay"
    return data, pd.DataFrame(audit_rows)

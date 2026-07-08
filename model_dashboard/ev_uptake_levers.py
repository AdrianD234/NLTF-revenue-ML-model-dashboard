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
SENSITIVITY_INTERPLAY_NOTE = (
    "These levers reshape power-type composition only; they compose "
    "multiplicatively with the Sensitivities panel, which owns the other two "
    "axes. Fleet efficiency owns petrol intensity (litres/100km): MBU26 "
    "embeds ~1.0% p.a. (Med) and VFM fleet turnover implies ~1.5% p.a. "
    "(High), so pick Med with any preset to reproduce the MBU26 PED volume "
    "path. PT mode shift owns travel demand: the VFM EV scenarios hold total "
    "light VKT fixed (<0.2% spread) and exclude rail entirely, so any "
    "non-Off mode shift is deliberately additional to official assumptions."
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
# PED family adjusted by the petrol-displacement retention curve.
PED_ACTIVITY_SERIES = ("ped_vkt_per_capita", "ped_volume")
PED_REVENUE_SERIES = "gross_ped_revenue"
# Heavy family: the finalist heavy total splits into conventional + BEV.
HEAVY_KM_SERIES = "heavy_ruc_net_km"
HEAVY_REVENUE_SERIES = "heavy_ruc_net_revenue"
# Aggregate june-year revenue series receiving additive deltas. Light RUC
# deltas flow through the RUC rollups, PED deltas through the FED rollups,
# and both meet in the whole-of-NLTF totals. Heavy BEV reallocation is
# rollup-neutral (BEVs pay the same per-km RUC in MBU26).
RUC_AGGREGATE_SERIES = (
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
)
FED_AGGREGATE_SERIES = (
    "gross_fed_revenue",
    "net_fed_revenue",
)
TOTAL_AGGREGATE_SERIES = (
    "total_fed_ruc_net_revenue",
    "total_gross_revenue",
    "total_revenue_net_admin",
    "total_nltf_net_revenue",
)
LEVER_AGGREGATE_SERIES = RUC_AGGREGATE_SERIES + FED_AGGREGATE_SERIES + TOTAL_AGGREGATE_SERIES


@dataclass(frozen=True)
class UptakeLevers:
    """Human levers for the EV transition across the three streams.

    Light RUC pool split (BEV logistic + PHEV hump), PED petrol displacement
    (logistic share of the FY2025 petrol activity displaced to EVs), and the
    heavy BEV share of the heavy RUC pool (logistic; the MoT midpoint sits
    near or beyond 2050 because heavy electrification lags light by ~15y).
    """

    bev_peak_speed_pp: float  # peak BEV uptake speed, share points per year
    bev_peak_year: float  # year of fastest adoption (logistic midpoint)
    bev_share_2050: float  # BEV share of the light RUC pool in FY2050
    phev_start_share: float  # PHEV share at FY2025
    phev_rise_pp: float  # PHEV linear rise, share points per year
    phev_peak_share: float  # PHEV peak share
    phev_decay_rate: float  # PHEV post-peak exponential decay per year
    ped_disp_speed_pp: float  # peak petrol displacement speed, pp per year
    ped_disp_midpoint: float  # year of fastest petrol displacement
    ped_disp_2050: float  # share of FY2025 petrol activity displaced by 2050
    heavy_bev_speed_pp: float  # peak heavy BEV uptake speed, pp per year
    heavy_bev_midpoint: float  # heavy logistic midpoint year
    heavy_bev_share_2050: float  # heavy BEV share of the heavy pool in 2050

    def key(self) -> tuple[float, ...]:
        return tuple(round(float(v), 6) for v in asdict(self).values())


EV_UPTAKE_PRESETS: dict[str, UptakeLevers] = {
    # Fitted to the MoT VFM 202405 scenarios (light shares <=1.5pp, PED share
    # retention <=1.1pp, heavy BEV shares <=0.9pp over 2025-2050). MBU26's
    # official proportions match the VFM base scenario within the same
    # tolerance, so the base preset doubles as the official-shape anchor. All
    # PED levers are activity-only (petrol share of the light universe): the
    # litres/100km intensity path belongs to the Fleet efficiency sensitivity,
    # so the two compose without double counting (MBU26 embeds ~1.0% p.a.
    # intensity gain = the sensitivity's Med level; VFM fleet turnover implies
    # ~1.5% p.a. = High).
    "MoT VFM base": UptakeLevers(
        0.0425, 2038.0, 0.83, 0.036, 0.011, 0.155, 0.060,
        0.0425, 2042.0, 0.78, 0.0175, 2051.0, 0.21,
    ),
    "MoT VFM fast": UptakeLevers(
        0.0475, 2036.5, 0.86, 0.039, 0.013, 0.175, 0.065,
        0.0425, 2040.5, 0.84, 0.025, 2046.0, 0.36,
    ),
    "MoT VFM slow": UptakeLevers(
        0.0425, 2039.5, 0.78, 0.034, 0.009, 0.135, 0.055,
        0.0425, 2043.5, 0.68, 0.010, 2054.0, 0.10,
    ),
}
# Engine sentinel for the unmodified governed-pack allocation. Not offered in
# the UI (the λ-migration split allowed the terminal-year scenario crossing);
# retained so parity tests and diagnostics can request a no-overlay view.
GOVERNED_PACK_OPTION = "Governed pack (MBU26 λ-migration)"
CUSTOM_OPTION = "Custom levers"
EV_UPTAKE_MODE_OPTIONS = (*EV_UPTAKE_PRESETS.keys(), CUSTOM_OPTION)
DEFAULT_EV_UPTAKE_MODE = "MoT VFM base"


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


def ped_retention_curve(june_years: Any, levers: UptakeLevers) -> pd.Series:
    """Fraction of FY2025 petrol activity retained (1 - displacement).

    Normalised so retention(2025) = 1: the lever displaces activity relative
    to the first forecast-era year, phasing in from zero.
    """
    years = np.asarray(list(june_years), dtype=float)
    smax, k = solve_logistic_from_levers(levers.ped_disp_speed_pp, levers.ped_disp_midpoint, levers.ped_disp_2050)
    displacement = smax / (1.0 + np.exp(-k * (years - float(levers.ped_disp_midpoint))))
    base = smax / (1.0 + np.exp(-k * (2025.0 - float(levers.ped_disp_midpoint))))
    retention = (1.0 - displacement) / max(1.0 - base, 1e-9)
    return pd.Series(np.clip(retention, 0.0, 1.0), index=years.astype(int))


def heavy_bev_share_curve(june_years: Any, levers: UptakeLevers) -> pd.Series:
    """Heavy BEV share of the heavy RUC pool, anchored to ~0 at FY2025."""
    years = np.asarray(list(june_years), dtype=float)
    smax, k = solve_logistic_from_levers(levers.heavy_bev_speed_pp, levers.heavy_bev_midpoint, levers.heavy_bev_share_2050)
    share = smax / (1.0 + np.exp(-k * (years - float(levers.heavy_bev_midpoint))))
    base = smax / (1.0 + np.exp(-k * (2025.0 - float(levers.heavy_bev_midpoint))))
    return pd.Series(np.clip(share - base, 0.0, 0.995), index=years.astype(int))


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


def _pool_from_labels(
    labels_for: Any,
    numeric_value: pd.Series,
    scenario: str,
    fy: int,
) -> float | None:
    """Full light RUC universe = sum of the three displayed km series."""
    total = 0.0
    for series_id in LEVER_SERIES_KM:
        labels = labels_for(scenario, fy, series_id)
        if not labels:
            return None
        values = numeric_value.loc[labels]
        if not values.notna().any():
            return None
        total += float(values.iloc[0])
    return total


def apply_uptake_levers_to_chart_rows(
    chart_rows: pd.DataFrame,
    drift_assumptions: pd.DataFrame,
    levers: UptakeLevers,
    *,
    adjust_ped: bool = True,
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

    fys_index = shares.index
    retention = ped_retention_curve(fys_index, levers)
    heavy_share = heavy_bev_share_curve(fys_index, levers)

    # One pass builds (scenario, FY, series) -> row labels for the june-year
    # forecast rows; the per-(scenario, FY) loop below then never recomputes
    # full-frame string masks (the previous approach was O(pairs x rows)).
    series_str = data["series_id"].astype(str)
    scenario_str = data.get("scenario_name", pd.Series("", index=data.index)).astype(str)
    eligible = (is_june & is_forecast).to_numpy()
    fy_values = june_year.to_numpy()
    rows_by_key: dict[tuple[str, int, str], list[Any]] = {}
    for position, label in enumerate(data.index):
        fy_value = fy_values[position]
        if not eligible[position] or pd.isna(fy_value):
            continue
        rows_by_key.setdefault(
            (scenario_str.iat[position], int(fy_value), series_str.iat[position]), []
        ).append(label)

    def _labels_for(scenario: str, fy: int, series_id: str) -> list[Any]:
        return rows_by_key.get((scenario, fy, series_id), [])

    def _scale_series(labels: list[Any], factor: float) -> float:
        """Scale matching rows by factor; return the resulting value delta."""
        delta = 0.0
        for index in labels:
            old = numeric_value.at[index]
            if pd.isna(old):
                continue
            data.at[index, "value"] = float(old) * factor
            delta += float(old) * (factor - 1.0)
        return delta

    audit_rows: list[dict[str, Any]] = []
    ruc_delta: dict[tuple[str, int], float] = {}
    fed_delta: dict[tuple[str, int], float] = {}
    for (scenario, fy), rates in rate_lookup.items():
        share_row = shares.loc[fy] if fy in shares.index else None
        if share_row is None:
            continue
        share_values = {
            "conventional": float(share_row["conventional"]),
            "bev": float(share_row["bev"]),
            "phev": float(share_row["phev"]),
        }
        pool_km = _pool_from_labels(_labels_for, numeric_value, scenario, fy)
        if pool_km is None or pool_km <= 0:
            continue
        light_revenue_delta = 0.0
        for series_id, component in LEVER_SERIES_KM.items():
            labels = _labels_for(scenario, fy, series_id)
            if not labels:
                continue
            data.loc[labels, "value"] = pool_km * share_values[component]
        for series_id, (component, rate_key) in LEVER_SERIES_REVENUE.items():
            labels = _labels_for(scenario, fy, series_id)
            if not labels or not np.isfinite(rates[rate_key]):
                continue
            values = numeric_value.loc[labels]
            new_revenue = pool_km * share_values[component] * rates[rate_key]
            old_revenue = float(values.iloc[0]) if values.notna().any() else 0.0
            light_revenue_delta += new_revenue - old_revenue
            data.loc[labels, "value"] = new_revenue

        # PED petrol displacement: the finalist raw-bridge petrol path keeps
        # activity that the VFM says migrates to EVs. Scale the PED family by
        # the retention curve; the lost excise flows to the FED aggregates.
        ped_revenue_delta = 0.0
        ped_factor = float(retention.get(fy, 1.0))
        if adjust_ped and ped_factor < 1.0:
            for series_id in PED_ACTIVITY_SERIES:
                _scale_series(_labels_for(scenario, fy, series_id), ped_factor)
            ped_revenue_delta = _scale_series(_labels_for(scenario, fy, PED_REVENUE_SERIES), ped_factor)

        # Heavy BEV split: MBU26 charges heavy BEVs the same per-km RUC, so
        # the split moves km/revenue out of the charted conventional heavy
        # lines without changing any rollup total.
        heavy_factor = 1.0 - float(heavy_share.get(fy, 0.0))
        heavy_reallocated = 0.0
        if heavy_factor < 1.0:
            _scale_series(_labels_for(scenario, fy, HEAVY_KM_SERIES), heavy_factor)
            heavy_reallocated = -_scale_series(_labels_for(scenario, fy, HEAVY_REVENUE_SERIES), heavy_factor)

        if light_revenue_delta:
            ruc_delta[(scenario, fy)] = light_revenue_delta
        if ped_revenue_delta:
            fed_delta[(scenario, fy)] = ped_revenue_delta
        audit_rows.append(
            {
                "scenario_name": scenario,
                "june_year": fy,
                "light_ruc_pool_km": pool_km,
                "conventional_share": share_values["conventional"],
                "bev_share": share_values["bev"],
                "phev_share": share_values["phev"],
                "light_revenue_delta_vs_pack": light_revenue_delta,
                "ped_retention": ped_factor if adjust_ped else 1.0,
                "ped_revenue_delta_vs_pack": ped_revenue_delta,
                "heavy_bev_share": 1.0 - heavy_factor,
                "heavy_revenue_reallocated_to_bev": heavy_reallocated,
            }
        )

    if ruc_delta or fed_delta:
        aggregate_mask = is_june & is_forecast & series_str.isin(LEVER_AGGREGATE_SERIES)
        for index in data.index[aggregate_mask]:
            if pd.isna(numeric_value.at[index]):
                continue
            key = (str(data.at[index, "scenario_name"]), int(june_year.at[index]) if pd.notna(june_year.at[index]) else -1)
            series_id = str(data.at[index, "series_id"])
            delta = 0.0
            if series_id in RUC_AGGREGATE_SERIES or series_id in TOTAL_AGGREGATE_SERIES:
                delta += ruc_delta.get(key, 0.0)
            if series_id in FED_AGGREGATE_SERIES or series_id in TOTAL_AGGREGATE_SERIES:
                delta += fed_delta.get(key, 0.0)
            if delta:
                data.at[index, "value"] = float(numeric_value.at[index]) + delta

    touched = (
        is_june
        & is_forecast
        & series_str.isin(
            set(LEVER_SERIES_KM)
            | set(LEVER_SERIES_REVENUE)
            | set(LEVER_AGGREGATE_SERIES)
            | set(PED_ACTIVITY_SERIES)
            | {PED_REVENUE_SERIES, HEAVY_KM_SERIES, HEAVY_REVENUE_SERIES}
        )
    )
    if "value_status" in data.columns:
        data.loc[touched, "value_status"] = "lever_adjusted"
    if "data_scope" in data.columns:
        data.loc[touched, "data_scope"] = "ev_uptake_lever_overlay"
    return data, pd.DataFrame(audit_rows)

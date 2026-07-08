"""Effective rate paths (PED / Light RUC / Heavy RUC) and the 12c FED toggle.

Sources (all committed):
- data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv - PED $/litre
  schedules: historical effective rates plus the 'Current planned path' and
  'No 2027 12c uplift' futures (defined through the legislated window).
- data/revenue_model_source_pack/mbu26_annual_spine/mbu26_official_annual.csv -
  light/heavy RUC $ per km (revenue over km) and the petrol fleet intensity
  (litres per 100 km) used to express PED on a per-1,000 km basis.

Beyond the legislated window the planned PED path comes from the governed
pack itself (gross PED revenue over volume), and the no-uplift path carries
the last legislated wedge (12c from FY2028; 6c in FY2027) forward - i.e. the
alternative stays parallel to the planned schedule.

The '2027 12c FED uplift' toggle reprices PED revenue at display time by the
per-FY rate ratio (volumes unchanged: same litres, cheaper duty), cascading
the delta into the FED and NLTF rollups.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ev_uptake_levers import FED_AGGREGATE_SERIES, TOTAL_AGGREGATE_SERIES
from .revenue_source_pack import REVENUE_LAST_COMPLETE_ACTUAL_FY

FED_UPLIFT_NOTE = (
    "2027 12c FED uplift: the legislated petrol excise increases (+6c/L in "
    "FY2027, +12c/L from FY2028) baked into the Current planned path. "
    "Switching the toggle off reprices PED revenue at the no-uplift schedule "
    "(carried parallel beyond the legislated window); litres and km are "
    "unchanged - this is a pure duty-rate counterfactual."
)
RATE_CHART_NOTE = (
    "Effective rates per 1,000 km. Light and Heavy RUC are MBU26 net revenue "
    "over net km. PED (petrol excise) is converted from $/litre using the "
    "MBU26 petrol fleet intensity, so the line embeds fleet efficiency: the "
    "$/litre schedule rises faster than the per-km line. History is the "
    "actual effective excise; futures follow the selected 12c-uplift setting, "
    "with the alternative path shown dotted."
)

_PLANNED_PATH = "Current planned path"
_NO_UPLIFT_PATH = "No 2027 12c uplift"
_HISTORY_PATH = "Selected rate"


def _fed_rate_paths(repo_root: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo_root / "data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv")
    frame["FY"] = pd.to_numeric(frame["FY"], errors="coerce")
    frame["rate_nzd_per_litre"] = pd.to_numeric(frame["rate_nzd_per_litre"], errors="coerce")
    return frame.dropna(subset=["FY", "rate_nzd_per_litre"])


def _mbu26_spine(repo_root: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo_root / "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_official_annual.csv")
    return frame.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first").apply(
        pd.to_numeric, errors="coerce"
    )


def _pack_planned_ped_rates(chart_rows: pd.DataFrame) -> pd.Series:
    """Planned-path PED $/L implied by the pack (revenue over volume)."""
    if chart_rows is None or chart_rows.empty:
        return pd.Series(dtype=float)
    jy = chart_rows[
        chart_rows.get("time_grain", pd.Series(dtype=str)).astype(str).eq("june_year")
        & chart_rows.get("trace_name", pd.Series(dtype=str)).astype(str).eq("Current finalist Base case")
    ]
    revenue = jy[jy["series_id"].astype(str).eq("gross_ped_revenue")].set_index(
        pd.to_numeric(jy[jy["series_id"].astype(str).eq("gross_ped_revenue")]["june_year"], errors="coerce")
    )["value"]
    volume = jy[jy["series_id"].astype(str).eq("ped_volume")].set_index(
        pd.to_numeric(jy[jy["series_id"].astype(str).eq("ped_volume")]["june_year"], errors="coerce")
    )["value"]
    rate = pd.to_numeric(revenue, errors="coerce") / pd.to_numeric(volume, errors="coerce")
    return rate.dropna()


def ped_rate_schedules(repo_root: Path, chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Per-FY PED $/L: history, planned path and no-uplift path (to 2050)."""
    fed = _fed_rate_paths(repo_root)
    by_path = fed.groupby(["fed_path", "FY"])["rate_nzd_per_litre"].mean()
    history = by_path.get(_HISTORY_PATH, pd.Series(dtype=float))
    planned_src = by_path.get(_PLANNED_PATH, pd.Series(dtype=float))
    no_uplift_src = by_path.get(_NO_UPLIFT_PATH, pd.Series(dtype=float))
    planned_pack = _pack_planned_ped_rates(chart_rows)

    years = sorted(
        set(history.index.astype(int))
        | set(planned_src.index.astype(int))
        | set(planned_pack.index.astype(int))
    )
    rows = []
    last_wedge = 0.0
    for fy in years:
        planned = planned_pack.get(fy, planned_src.get(fy, np.nan))
        if pd.isna(planned):
            planned = planned_src.get(fy, np.nan)
        no_uplift = no_uplift_src.get(fy, np.nan)
        if pd.notna(planned) and pd.notna(no_uplift):
            last_wedge = float(planned) - float(no_uplift)
        elif pd.notna(planned):
            no_uplift = float(planned) - last_wedge
        rows.append(
            {
                "june_year": int(fy),
                # 'Selected rate' extends forward; only complete actual years
                # count as history for display purposes.
                "history": history.get(fy, np.nan) if fy <= REVENUE_LAST_COMPLETE_ACTUAL_FY else np.nan,
                "planned": planned,
                "no_uplift": no_uplift,
            }
        )
    return pd.DataFrame(rows).set_index("june_year")


def fed_uplift_off_factors(repo_root: Path, chart_rows: pd.DataFrame) -> dict[int, float]:
    """Per-FY multiplier applied to PED revenue when the 12c uplift is off."""
    schedules = ped_rate_schedules(repo_root, chart_rows)
    factors: dict[int, float] = {}
    for fy, row in schedules.iterrows():
        planned, no_uplift = row["planned"], row["no_uplift"]
        if pd.notna(planned) and pd.notna(no_uplift) and planned > 0:
            factor = float(no_uplift) / float(planned)
            if abs(factor - 1.0) > 1e-9:
                factors[int(fy)] = factor
    return factors


def rate_paths_frame(repo_root: Path, chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Long frame of effective rates per 1,000 km for the rate chart."""
    spine = _mbu26_spine(repo_root)
    intensity = (spine["ped_volume"] / spine["light_petrol_vkt"] * 100).dropna()
    light = (spine["light_ruc_net_revenue"] / spine["light_ruc_net_km"] * 1000).dropna()
    heavy = (spine["heavy_ruc_net_revenue"] / spine["heavy_ruc_net_km"] * 1000).dropna()
    schedules = ped_rate_schedules(repo_root, chart_rows)

    rows: list[dict[str, Any]] = []
    for fy, value in light.items():
        rows.append({"june_year": int(fy), "series": "Light RUC", "nzd_per_1000km": float(value), "nzd_per_litre": np.nan, "segment": "path"})
    for fy, value in heavy.items():
        rows.append({"june_year": int(fy), "series": "Heavy RUC", "nzd_per_1000km": float(value), "nzd_per_litre": np.nan, "segment": "path"})
    for fy, row in schedules.iterrows():
        lp100 = intensity.get(fy, np.nan)
        if pd.isna(lp100):
            continue
        for column, series, segment in [
            ("history", "PED (petrol excise)", "history"),
            ("planned", "PED (petrol excise)", "planned"),
            ("no_uplift", "PED (petrol excise)", "no_uplift"),
        ]:
            value = row[column]
            if pd.isna(value):
                continue
            rows.append(
                {
                    "june_year": int(fy),
                    "series": series,
                    "nzd_per_1000km": float(value) * float(lp100) * 10.0,
                    "nzd_per_litre": float(value),
                    "segment": segment,
                }
            )
    return pd.DataFrame(rows)


def apply_fed_uplift_off_to_chart_rows(
    chart_rows: pd.DataFrame, factors: dict[int, float]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reprice PED revenue at the no-uplift schedule (display overlay)."""
    if chart_rows is None or chart_rows.empty or not factors:
        return chart_rows, pd.DataFrame()
    data = chart_rows.copy()
    numeric_value = pd.to_numeric(data.get("value"), errors="coerce")
    june_year = pd.to_numeric(data.get("june_year"), errors="coerce")
    is_june = data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")
    is_forecast = ~data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("historical_actual")

    audit_rows: list[dict[str, Any]] = []
    delta_by_key: dict[tuple[str, int], float] = {}
    ped_mask = is_june & is_forecast & data["series_id"].astype(str).eq("gross_ped_revenue")
    for index in data.index[ped_mask]:
        fy = june_year.at[index]
        if pd.isna(fy) or int(fy) not in factors or pd.isna(numeric_value.at[index]):
            continue
        factor = factors[int(fy)]
        old = float(numeric_value.at[index])
        new = old * factor
        data.at[index, "value"] = new
        key = (str(data.at[index, "scenario_name"]), int(fy))
        delta_by_key[key] = delta_by_key.get(key, 0.0) + (new - old)
        audit_rows.append(
            {
                "scenario_name": key[0],
                "june_year": int(fy),
                "rate_factor": factor,
                "ped_revenue_delta": new - old,
            }
        )

    if delta_by_key:
        aggregate_mask = (
            is_june
            & is_forecast
            & data["series_id"].astype(str).isin(set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES))
        )
        for index in data.index[aggregate_mask]:
            if pd.isna(numeric_value.at[index]) or pd.isna(june_year.at[index]):
                continue
            key = (str(data.at[index, "scenario_name"]), int(june_year.at[index]))
            delta = delta_by_key.get(key)
            if delta:
                data.at[index, "value"] = float(numeric_value.at[index]) + delta

    touched = (
        is_june
        & is_forecast
        & data["series_id"].astype(str).isin({"gross_ped_revenue"} | set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES))
        & june_year.isin(list(factors))
    )
    if "value_status" in data.columns:
        data.loc[touched, "value_status"] = "fed_uplift_off"
    if "data_scope" in data.columns:
        data.loc[touched, "data_scope"] = "fed_uplift_counterfactual"
    return data, pd.DataFrame(audit_rows)

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

The '2027 12c FED uplift' policy reprices PED revenue at display time by the
per-FY rate ratio (volumes unchanged: same litres, cheaper duty), cascading
the delta into the FED and NLTF rollups.  A governed six-month-delay scenario
moves only the initial 12c step from 2027Q1 to 2027Q3; later planned increases
retain their published dates.
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
FED_UPLIFT_DELAY_NOTE = (
    "Six-month 12c FED delay: the initial +12c/L step moves from 1 January "
    "2027 to 1 July 2027. Only calendar 2027Q1-Q2 are repriced; the planned "
    "path resumes in 2027Q3. Litres and km are unchanged."
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
_DELAYED_SEGMENT = "delayed_6m"
_DELAYED_QUARTERS = ("2027Q1", "2027Q2")

FED_POLICY_STATE_DELAYED_6M = "delay_6m"
FED_POLICY_STATE_NO_UPLIFT = "no_uplift"
FED_POLICY_METADATA_COLUMNS = (
    "_fed_baseline_value",
    "_fed_annual_delta",
    "_fed_policy",
    "_fed_affected_quarters",
)


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


def _quarter_order(period: Any) -> tuple[int, int]:
    text = str(period or "")
    try:
        year_text, quarter_text = text.split("Q", maxsplit=1)
        return int(year_text), int(quarter_text)
    except (TypeError, ValueError):
        return 0, 0


def ped_quarterly_rate_schedules(repo_root: Path) -> pd.DataFrame:
    """Calendar-quarter PED $/L schedules, including the six-month delay.

    The delayed scenario is deliberately narrow: only 2027Q1-Q2 take the
    no-uplift rate.  From 2027Q3 the published planned path is unchanged.
    """
    fed = _fed_rate_paths(repo_root)
    pivot = fed.pivot_table(
        index=["quarter", "FY"],
        columns="fed_path",
        values="rate_nzd_per_litre",
        aggfunc="mean",
    ).reset_index()
    pivot["quarter"] = pivot["quarter"].astype(str)
    pivot["FY"] = pd.to_numeric(pivot["FY"], errors="coerce")
    pivot = pivot.dropna(subset=["FY"]).copy()
    pivot["FY"] = pivot["FY"].astype(int)
    pivot["history"] = pd.to_numeric(pivot.get(_HISTORY_PATH), errors="coerce")
    pivot["planned"] = pd.to_numeric(pivot.get(_PLANNED_PATH), errors="coerce")
    pivot["no_uplift"] = pd.to_numeric(pivot.get(_NO_UPLIFT_PATH), errors="coerce")
    pivot[_DELAYED_SEGMENT] = pivot["planned"]
    delayed_mask = pivot["quarter"].isin(_DELAYED_QUARTERS)
    pivot.loc[delayed_mask, _DELAYED_SEGMENT] = pivot.loc[delayed_mask, "no_uplift"]
    pivot["_order"] = pivot["quarter"].map(_quarter_order)
    return (
        pivot.sort_values("_order", kind="stable")
        .set_index("quarter")[["FY", "history", "planned", _DELAYED_SEGMENT, "no_uplift"]]
    )


def fed_policy_affected_periods(repo_root: Path, policy_state: str) -> dict[int, tuple[str, ...]]:
    """Fiscal-year map of calendar quarters changed versus planned timing."""
    schedules = ped_quarterly_rate_schedules(repo_root)
    target_column = {
        FED_POLICY_STATE_DELAYED_6M: _DELAYED_SEGMENT,
        FED_POLICY_STATE_NO_UPLIFT: "no_uplift",
    }.get(str(policy_state))
    if not target_column:
        return {}
    planned = pd.to_numeric(schedules["planned"], errors="coerce")
    target = pd.to_numeric(schedules[target_column], errors="coerce")
    changed = schedules[planned.notna() & target.notna() & (planned - target).abs().gt(1e-9)]
    return {
        int(fy): tuple(group.index.astype(str).tolist())
        for fy, group in changed.groupby("FY", sort=True)
    }


def ped_rate_schedules(repo_root: Path, chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Per-FY PED $/L: history, planned, delayed and no-uplift paths."""
    fed = _fed_rate_paths(repo_root)
    by_path = fed.groupby(["fed_path", "FY"])["rate_nzd_per_litre"].mean()
    history = by_path.get(_HISTORY_PATH, pd.Series(dtype=float))
    planned_src = by_path.get(_PLANNED_PATH, pd.Series(dtype=float))
    no_uplift_src = by_path.get(_NO_UPLIFT_PATH, pd.Series(dtype=float))
    planned_pack = _pack_planned_ped_rates(chart_rows)
    quarterly = ped_quarterly_rate_schedules(repo_root)
    delayed_src = quarterly.groupby("FY")[_DELAYED_SEGMENT].mean()
    delayed_years = set(fed_policy_affected_periods(repo_root, FED_POLICY_STATE_DELAYED_6M))

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
        delayed = delayed_src.get(fy, np.nan) if fy in delayed_years else planned
        rows.append(
            {
                "june_year": int(fy),
                # 'Selected rate' extends forward; only complete actual years
                # count as history for display purposes.
                "history": history.get(fy, np.nan) if fy <= REVENUE_LAST_COMPLETE_ACTUAL_FY else np.nan,
                "planned": planned,
                _DELAYED_SEGMENT: delayed,
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


def fed_uplift_delayed_factors(repo_root: Path, chart_rows: pd.DataFrame) -> dict[int, float]:
    """Per-FY PED multiplier for the initial 12c step delayed six months."""
    schedules = ped_rate_schedules(repo_root, chart_rows)
    factors: dict[int, float] = {}
    for fy, row in schedules.iterrows():
        planned, delayed = row["planned"], row[_DELAYED_SEGMENT]
        if pd.notna(planned) and pd.notna(delayed) and planned > 0:
            factor = float(delayed) / float(planned)
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
            (_DELAYED_SEGMENT, "PED (petrol excise)", _DELAYED_SEGMENT),
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


def _default_affected_periods(factors: dict[int, float], policy_state: str) -> dict[int, tuple[str, ...]]:
    """Fallback quarter map for callers that only carry annual factors."""
    years = sorted(int(fy) for fy in factors)
    if not years:
        return {}
    if policy_state == FED_POLICY_STATE_DELAYED_6M:
        return {2027: _DELAYED_QUARTERS} if 2027 in years else {}
    return {
        fy: (_DELAYED_QUARTERS if fy == 2027 else tuple(f"{period}Q{quarter}" for period, quarter in [(fy - 1, 3), (fy - 1, 4), (fy, 1), (fy, 2)]))
        for fy in years
    }


def _policy_row_key(data: pd.DataFrame, index: Any, fy: int) -> tuple[str, str, str, int]:
    return (
        str(data.at[index, "scenario_name"]) if "scenario_name" in data.columns else "",
        str(data.at[index, "trace_name"]) if "trace_name" in data.columns else "",
        str(data.at[index, "fed_path"]) if "fed_path" in data.columns else "",
        int(fy),
    )


def apply_fed_rate_policy_to_chart_rows(
    chart_rows: pd.DataFrame,
    factors: dict[int, float],
    *,
    policy_state: str,
    scenario_roles: set[str] | tuple[str, ...] | None = None,
    affected_periods_by_fy: dict[int, tuple[str, ...]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reprice PED and dependent rollups using an audited display overlay.

    ``scenario_roles`` scopes the counterfactual to selected trace families.
    ``affected_periods_by_fy`` lets quarterly disaggregation localise each
    annual delta to the exact calendar quarters changed by the policy.
    """
    if chart_rows is None or chart_rows.empty or not factors:
        return chart_rows, pd.DataFrame()
    policy_state = str(policy_state)
    if not policy_state:
        raise ValueError("policy_state is required for an audited FED rate overlay")
    affected_periods = affected_periods_by_fy or _default_affected_periods(factors, policy_state)
    data = chart_rows.copy()
    metadata_defaults: dict[str, Any] = {
        "_fed_baseline_value": np.nan,
        "_fed_annual_delta": np.nan,
        "_fed_policy": "",
        "_fed_affected_quarters": "",
    }
    for column, default in metadata_defaults.items():
        if column not in data.columns:
            data[column] = default
    numeric_value = pd.to_numeric(data.get("value"), errors="coerce")
    june_year = pd.to_numeric(data.get("june_year"), errors="coerce")
    is_june = data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")
    is_forecast = ~data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("historical_actual")
    eligible_role = pd.Series(True, index=data.index)
    if scenario_roles is not None:
        allowed_roles = {str(role) for role in scenario_roles}
        eligible_role = data.get("scenario_role", pd.Series("", index=data.index)).astype(str).isin(allowed_roles)

    audit_rows: list[dict[str, Any]] = []
    delta_by_key: dict[tuple[str, str, str, int], float] = {}
    ped_mask = is_june & is_forecast & eligible_role & data["series_id"].astype(str).eq("gross_ped_revenue")
    for index in data.index[ped_mask]:
        fy = june_year.at[index]
        if pd.isna(fy) or int(fy) not in factors or pd.isna(numeric_value.at[index]):
            continue
        factor = factors[int(fy)]
        old = float(numeric_value.at[index])
        new = old * factor
        data.at[index, "value"] = new
        key = _policy_row_key(data, index, int(fy))
        delta_by_key[key] = delta_by_key.get(key, 0.0) + (new - old)
        periods = tuple(affected_periods.get(int(fy), ()))
        data.at[index, "_fed_baseline_value"] = old
        data.at[index, "_fed_annual_delta"] = new - old
        data.at[index, "_fed_policy"] = policy_state
        data.at[index, "_fed_affected_quarters"] = ";".join(periods)
        audit_rows.append(
            {
                "scenario_name": key[0],
                "scenario_role": str(data.at[index, "scenario_role"]) if "scenario_role" in data.columns else "",
                "trace_name": key[1],
                "fed_path": key[2],
                "june_year": int(fy),
                "policy_state": policy_state,
                "rate_factor": factor,
                "baseline_ped_revenue": old,
                "adjusted_ped_revenue": new,
                "ped_revenue_delta": new - old,
                "affected_periods": ";".join(periods),
                "indicator_series_id": "ped_vkt_per_capita",
            }
        )

    if delta_by_key:
        aggregate_mask = (
            is_june
            & is_forecast
            & eligible_role
            & data["series_id"].astype(str).isin(set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES))
        )
        for index in data.index[aggregate_mask]:
            if pd.isna(numeric_value.at[index]) or pd.isna(june_year.at[index]):
                continue
            fy = int(june_year.at[index])
            key = _policy_row_key(data, index, fy)
            delta = delta_by_key.get(key)
            if delta:
                old = float(numeric_value.at[index])
                data.at[index, "value"] = old + delta
                periods = tuple(affected_periods.get(fy, ()))
                data.at[index, "_fed_baseline_value"] = old
                data.at[index, "_fed_annual_delta"] = delta
                data.at[index, "_fed_policy"] = policy_state
                data.at[index, "_fed_affected_quarters"] = ";".join(periods)

    touched = data["_fed_policy"].astype(str).eq(policy_state)
    if "value_status" in data.columns:
        value_status = "fed_uplift_off" if policy_state == FED_POLICY_STATE_NO_UPLIFT else "fed_uplift_delayed_6m"
        data.loc[touched, "value_status"] = value_status
    if "data_scope" in data.columns:
        data_scope = "fed_uplift_counterfactual" if policy_state == FED_POLICY_STATE_NO_UPLIFT else "fed_uplift_delay_counterfactual"
        data.loc[touched, "data_scope"] = data_scope
    return data, pd.DataFrame(audit_rows)


def apply_fed_uplift_delay_to_chart_rows(
    chart_rows: pd.DataFrame,
    factors: dict[int, float],
    *,
    scenario_roles: set[str] | tuple[str, ...] | None = None,
    affected_periods_by_fy: dict[int, tuple[str, ...]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the six-month delay while preserving the source pack."""
    return apply_fed_rate_policy_to_chart_rows(
        chart_rows,
        factors,
        policy_state=FED_POLICY_STATE_DELAYED_6M,
        scenario_roles=scenario_roles,
        affected_periods_by_fy=affected_periods_by_fy,
    )


def apply_fed_uplift_off_to_chart_rows(
    chart_rows: pd.DataFrame,
    factors: dict[int, float],
    *,
    scenario_roles: set[str] | tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backward-compatible no-uplift wrapper around the generic overlay."""
    return apply_fed_rate_policy_to_chart_rows(
        chart_rows,
        factors,
        policy_state=FED_POLICY_STATE_NO_UPLIFT,
        scenario_roles=scenario_roles,
    )

"""Effective rate paths (PED / Light RUC / Heavy RUC) and the 12c FED policy states.

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

The PED policy schedule also governs model-price inputs.  In every affected
quarter the selected-minus-published FED wedge is added to the retail petrol
price input, while the selected/published PED-rate ratio is applied to both
Light and Heavy RUC price inputs and to all five nominal RUC collection-rate
leaves.  Fixed-finalist coefficients therefore own the PED and RUC activity
responses; admin charges and refunds are never scaled.  A governed six-month-
delay scenario moves only the initial 12c step from 2027Q1 to 2027Q3; later
planned increases retain their published dates.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ev_uptake_levers import (
    FED_AGGREGATE_SERIES,
    NATIVE_QUARTERLY_ACTIVITY_SERIES,
    RUC_AGGREGATE_SERIES,
    TOTAL_AGGREGATE_SERIES,
    reconcile_native_quarterly_activity_to_annual,
)
from .fed_policy_states import (
    FED_DEFERRAL_CATCH_UP_NOTE,
    FED_POLICY_SPECS,
    FED_UPLIFT_START_PERIOD,
    PolicyStateError,
    finite_deferral_specs,
    policy_spec,
    quarter_serial,
)
from .light_fleet_allocation import LAST_DECISION_GRADE_ANNUAL_FY
from .revenue_source_pack import REVENUE_LAST_COMPLETE_ACTUAL_FY

FED_POLICY_STATE_PUBLISHED = "published"
FED_UPLIFT_NOTE = (
    "2027 12c FED uplift: the legislated petrol excise increases (+6c/L in "
    "FY2027, +12c/L from FY2028) baked into the Current planned path. "
    "Selecting the no-uplift policy reprices PED and all RUC collection rates at "
    "the no-uplift schedule (carried parallel beyond the legislated window). "
    "The FED wedge is also carried in the PED retail-price input, while the "
    "same PED-rate ratio is applied to real Light/Heavy RUC model inputs, so "
    "governed coefficients determine the resulting volume response."
)
FED_UPLIFT_DELAY_NOTE = (
    "Six-month 12c FED delay: the initial +12c/L step moves from 1 January "
    "2027 to 1 July 2027. The PED retail-price input is 12c/L lower and the "
    "same proportional reduction is applied to Light and Heavy RUC rates and "
    "real RUC model-price inputs in calendar 2027Q1-Q2; the published direct "
    "rate path resumes in 2027Q3. The governed structural demand calibration "
    "is contemporaneous and does not carry the raw recursive replay beyond "
    "that direct window; only explicitly rebuilt model-native lag/lead inputs "
    "can affect their governed quarter."
)
def rate_chart_note(bridge_release: str) -> str:
    """Rate-chart caption naming the bridge vintage actually in use.

    Generated rather than hard-coded so the caption can never drift from the
    vintage the displayed rates were derived from.
    """
    return (
        f"Effective rates per 1,000 km. Light and Heavy RUC start from the "
        f"{bridge_release} bridge-vintage net revenue over net km, then follow "
        "the same proportional policy change as the selected PED path. PED "
        f"(petrol excise) is converted from $/litre using {bridge_release} "
        "petrol-fleet intensity, so that line also embeds fleet efficiency. "
        "The published January-2027 path remains visible as a reference."
    )

_PLANNED_PATH = "Current planned path"
_NO_UPLIFT_PATH = "No 2027 12c uplift"
_HISTORY_PATH = "Selected rate"
_DELAYED_SEGMENT = "delayed_6m"
_DELAYED_QUARTERS = ("2027Q1", "2027Q2")

FED_POLICY_STATE_DELAYED_6M = "delay_6m"
FED_POLICY_STATE_NO_UPLIFT = "no_uplift"
# All eight calculation-layer state ids, and the schedule column that answers
# each. Derived from the canonical registry so a new duration is one registry
# row, never an edit here. The published state maps to the planned column.
_SCHEDULE_COLUMN_BY_STATE = {
    spec.calculation_state_id: spec.schedule_column for spec in FED_POLICY_SPECS
}
_DEFERRAL_SEGMENTS = tuple(spec.schedule_column for spec in finite_deferral_specs())
FED_POLICY_METADATA_COLUMNS = (
    "_fed_baseline_value",
    "_fed_annual_delta",
    "_fed_policy",
    "_fed_affected_quarters",
)
_RUC_REVENUE_LEAVES = (
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_revenue",
)
_POLICY_PAIR_BY_STATE = {
    **{
        spec.calculation_state_id: f"baseline_{spec.pair_state_suffix}"
        for spec in finite_deferral_specs()
    },
    FED_POLICY_STATE_NO_UPLIFT: "baseline_no_uplift",
}


def _target_schedule_column(policy_state: str) -> str | None:
    """Schedule column for a calculation-layer state; None for published.

    Unknown states fail closed: a typo must never quietly produce an empty
    factor map that reads as "no policy change".
    """
    state = str(policy_state)
    try:
        spec = policy_spec(state)
    except PolicyStateError as error:
        raise ValueError(str(error)) from error
    if spec.is_published:
        return None
    return spec.schedule_column
# Beyond the fixed-finalist replay window the only governed policy factor left
# is the scalar rate ratio. It may reprice the leaves the RATE actually
# governs - gross petrol excise, the five nominal RUC collection leaves, and
# the chart-carried RUC aggregates that roll them up - and nothing else.
# Activity (km, VKT per capita, volumes) responds to a price change only
# through the governed elasticities inside the replay; a rate ratio is not an
# elasticity, and non-fuel revenue is not priced by the fuel rate at all.
_RATE_PRICED_LONG_RUN_SERIES = frozenset(
    {"gross_ped_revenue", *_RUC_REVENUE_LEAVES, *RUC_AGGREGATE_SERIES}
)


def _fed_rate_paths(repo_root: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo_root / "data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv")
    frame["FY"] = pd.to_numeric(frame["FY"], errors="coerce")
    frame["rate_nzd_per_litre"] = pd.to_numeric(frame["rate_nzd_per_litre"], errors="coerce")
    return frame.dropna(subset=["FY", "rate_nzd_per_litre"])


def _mbu26_spine(repo_root: Path) -> pd.DataFrame:
    """The frozen MBU26 spine, for the MBU26-ONLY synthetic counterfactual.

    Deliberately vintage-specific: the rate-only counterfactual and its audit
    derive their schedule from the MBU26 published rows and hash that exact
    file into every audit row. Anything describing the CURRENT revenue bridge
    must use ``_bridge_spine`` instead, which follows the bridge-assumption
    vintage the loaded pack was actually built with.
    """
    frame = pd.read_csv(repo_root / _OFFICIAL_SPINE_REL)
    return frame.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first").apply(
        pd.to_numeric, errors="coerce"
    )


def _bridge_spine(repo_root: Path, bridge_vintage_id: str | None = None) -> pd.DataFrame:
    """Official annual rows of the bridge-assumption vintage.

    ``bridge_vintage_id`` should come from the loaded pack manifest so the
    displayed effective rates always describe the vintage that actually
    produced the Current revenue path. It falls back to the registry default
    only when no pack-specific bridge has been supplied.
    """
    from .official_vintage import default_bridge_vintage_id, official_vintage_spine_frame

    vid = str(bridge_vintage_id or default_bridge_vintage_id(repo_root))
    return official_vintage_spine_frame(vid, repo_root=repo_root)


def mbu26_ruc_class_revenue_by_fy(repo_root: Path) -> dict[int, float]:
    """Five-class MBU26 RUC revenue pool before fixed administration.

    The compact chart omits Heavy-BEV revenue, so its visible RUC leaves are
    insufficient for a proportional rate counterfactual.  This source-backed
    pool lets the official comparator reprice all five classes while holding
    RUC administration fixed in the canonical Net RUC formula.

    MBU26-specific by design: it feeds the MBU26-only synthetic counterfactual.
    """

    spine = _mbu26_spine(repo_root)
    missing = [series_id for series_id in _RUC_REVENUE_LEAVES if series_id not in spine.columns]
    if missing:
        raise ValueError("MBU26 RUC class revenue is missing: " + ", ".join(sorted(missing)))
    totals = spine[list(_RUC_REVENUE_LEAVES)].sum(axis=1, min_count=len(_RUC_REVENUE_LEAVES))
    return {
        int(fy): float(value)
        for fy, value in totals.items()
        if pd.notna(fy) and pd.notna(value)
    }


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
    """Calendar-quarter PED $/L schedules for every governed policy state.

    Each finite deferral is deliberately narrow: only the quarters from
    2027Q1 up to (excluding) its deferred start take the no-uplift rate.
    From the deferred start the published planned path is unchanged, so a
    later planned increase retains its original date and the path catches up
    at the start quarter. The six-month column reproduces the original
    governed scenario exactly: only 2027Q1-Q2 take the no-uplift rate.
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
    quarters = set(pivot["quarter"])
    for spec in finite_deferral_specs():
        window = spec.direct_affected_quarters()
        missing = [quarter for quarter in (*window, spec.start_period) if quarter not in quarters]
        if missing:
            raise ValueError(
                f"The governed FED rate schedule cannot express {spec.state_id!r}: "
                "quarters " + ", ".join(missing) + " are absent, so the deferral "
                "cannot rejoin the planned schedule."
            )
        window_mask = pivot["quarter"].isin(window)
        window_planned = pivot.loc[window_mask, "planned"]
        window_no_uplift = pivot.loc[window_mask, "no_uplift"]
        if window_planned.isna().any() or window_no_uplift.isna().any():
            raise ValueError(
                f"The governed FED rate schedule cannot express {spec.state_id!r}: "
                "a planned or no-uplift rate inside its window is non-numeric."
            )
        if window_planned.le(0.0).any():
            raise ValueError(
                f"The governed planned FED rate is non-positive inside the "
                f"{spec.state_id!r} window."
            )
        if window_no_uplift.lt(0.0).any():
            raise ValueError(
                f"The governed no-uplift FED rate is negative inside the "
                f"{spec.state_id!r} window."
            )
        rejoin_planned = pivot.loc[pivot["quarter"].eq(spec.start_period), "planned"]
        if rejoin_planned.isna().any():
            raise ValueError(
                f"The {spec.state_id!r} deferral cannot rejoin the planned schedule: "
                f"no planned rate exists in {spec.start_period}."
            )
        pivot[spec.schedule_column] = pivot["planned"]
        pivot.loc[window_mask, spec.schedule_column] = window_no_uplift
    pivot["_order"] = pivot["quarter"].map(_quarter_order)
    return (
        pivot.sort_values("_order", kind="stable")
        .set_index("quarter")[["FY", "history", "planned", *_DEFERRAL_SEGMENTS, "no_uplift"]]
    )


def fed_policy_affected_periods(repo_root: Path, policy_state: str) -> dict[int, tuple[str, ...]]:
    """Fiscal-year map of calendar quarters changed versus planned timing.

    These are the DIRECT rate-affected quarters: where the selected rate
    differs from planned. The modelled activity response may extend to an
    adjacent quarter only through the explicitly rebuilt Light-price lag and
    Heavy-price lead inputs; that response window is reported separately by
    the policy replay audit, never conflated with this map.
    """
    schedules = ped_quarterly_rate_schedules(repo_root)
    target_column = _target_schedule_column(policy_state)
    if not target_column:
        return {}
    planned = pd.to_numeric(schedules["planned"], errors="coerce")
    target = pd.to_numeric(schedules[target_column], errors="coerce")
    changed = schedules[planned.notna() & target.notna() & (planned - target).abs().gt(1e-9)]
    return {
        int(fy): tuple(group.index.astype(str).tolist())
        for fy, group in changed.groupby("FY", sort=True)
    }


def fed_policy_quarterly_factors(repo_root: Path, policy_state: str) -> dict[str, float]:
    """Selected/published PED-rate multiplier for every governed quarter.

    This is the canonical cross-tax policy signal used for RUC price inputs
    and nominal RUC rates.  It deliberately uses quarter-level FED rates, not
    the annual PED-revenue factor: for the delayed window the exact multiplier
    is ``0.70024 / 0.82024`` in 2027Q1-Q2.
    """

    schedules = ped_quarterly_rate_schedules(repo_root)
    target_column = _target_schedule_column(policy_state)
    if not target_column:
        return {}
    planned = pd.to_numeric(schedules["planned"], errors="coerce")
    target = pd.to_numeric(schedules[target_column], errors="coerce")
    valid = planned.gt(0.0) & target.notna()
    return {
        str(period): float(target.at[period]) / float(planned.at[period])
        for period in schedules.index[valid]
    }


def ped_rate_change_quarterly_factors(
    repo_root: Path,
    rate_change_nzd_per_litre_by_period: Mapping[str, float],
) -> dict[str, float]:
    """Convert any fixed-period PED change into proportional RUC factors.

    Positive values are PED/FED increases and negative values are deferrals
    or subsidies, all expressed in nominal NZD per litre. Each target PED
    rate is divided by the published planned rate for the same calendar
    quarter. The returned factors are the governed signal for Light and
    Heavy RUC model-price inputs and nominal collection rates. Periods omitted
    from the mapping are unchanged.
    """

    if not isinstance(rate_change_nzd_per_litre_by_period, Mapping):
        raise TypeError("rate_change_nzd_per_litre_by_period must be a quarter-to-NZD mapping.")
    schedules = ped_quarterly_rate_schedules(repo_root)
    planned = pd.to_numeric(schedules["planned"], errors="coerce")
    factors: dict[str, float] = {}
    for raw_period, raw_change in rate_change_nzd_per_litre_by_period.items():
        period = str(raw_period)
        if period not in schedules.index:
            raise ValueError(f"PED policy period {period!r} is not in the governed quarterly schedule.")
        change = pd.to_numeric(pd.Series([raw_change]), errors="coerce").iloc[0]
        base_rate = planned.at[period]
        if pd.isna(change) or not np.isfinite(float(change)):
            raise ValueError(f"PED policy change for {period} must be finite and numeric.")
        if pd.isna(base_rate) or float(base_rate) <= 0.0:
            raise ValueError(f"Published PED rate for {period} must be positive.")
        target_rate = float(base_rate) + float(change)
        if target_rate < 0.0:
            raise ValueError(f"PED policy change for {period} would make the target rate negative.")
        factors[period] = target_rate / float(base_rate)
    return factors


def ped_rate_schedules(repo_root: Path, chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Per-FY PED $/L: history, planned, every deferral and the no-uplift path."""
    fed = _fed_rate_paths(repo_root)
    by_path = fed.groupby(["fed_path", "FY"])["rate_nzd_per_litre"].mean()
    history = by_path.get(_HISTORY_PATH, pd.Series(dtype=float))
    planned_src = by_path.get(_PLANNED_PATH, pd.Series(dtype=float))
    no_uplift_src = by_path.get(_NO_UPLIFT_PATH, pd.Series(dtype=float))
    planned_pack = _pack_planned_ped_rates(chart_rows)
    quarterly = ped_quarterly_rate_schedules(repo_root)
    deferral_annual_src = {
        spec.schedule_column: quarterly.groupby("FY")[spec.schedule_column].mean()
        for spec in finite_deferral_specs()
    }
    deferral_years = {
        spec.schedule_column: set(
            fed_policy_affected_periods(repo_root, spec.calculation_state_id)
        )
        for spec in finite_deferral_specs()
    }

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
        row: dict[str, Any] = {
            "june_year": int(fy),
            # 'Selected rate' extends forward; only complete actual years
            # count as history for display purposes.
            "history": history.get(fy, np.nan) if fy <= REVENUE_LAST_COMPLETE_ACTUAL_FY else np.nan,
            "planned": planned,
        }
        for column, annual_src in deferral_annual_src.items():
            row[column] = (
                annual_src.get(fy, np.nan) if fy in deferral_years[column] else planned
            )
        row["no_uplift"] = no_uplift
        rows.append(row)
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


def fed_policy_annual_factors(
    repo_root: Path, chart_rows: pd.DataFrame, policy_state: str
) -> dict[int, float]:
    """Per-FY PED multiplier for any governed policy state versus planned."""
    target_column = _target_schedule_column(policy_state)
    if not target_column:
        return {}
    schedules = ped_rate_schedules(repo_root, chart_rows)
    factors: dict[int, float] = {}
    for fy, row in schedules.iterrows():
        planned, target = row["planned"], row[target_column]
        if pd.notna(planned) and pd.notna(target) and planned > 0:
            factor = float(target) / float(planned)
            if abs(factor - 1.0) > 1e-9:
                factors[int(fy)] = factor
    return factors


def fed_uplift_delayed_factors(repo_root: Path, chart_rows: pd.DataFrame) -> dict[int, float]:
    """Per-FY PED multiplier for the initial 12c step delayed six months."""
    return fed_policy_annual_factors(repo_root, chart_rows, FED_POLICY_STATE_DELAYED_6M)


def rate_paths_frame(
    repo_root: Path,
    chart_rows: pd.DataFrame,
    *,
    bridge_vintage_id: str | None = None,
) -> pd.DataFrame:
    """Long frame of effective rates per 1,000 km for the rate chart.

    The base effective rates come from the BRIDGE-ASSUMPTION vintage, so the
    chart always describes the same vintage that produced the Current revenue
    path. Pass the loaded pack manifest's bridge vintage; omitting it falls
    back to the registry default.
    """
    spine = _bridge_spine(repo_root, bridge_vintage_id)
    intensity = (spine["ped_volume"] / spine["light_petrol_vkt"] * 100).dropna()
    light = (spine["light_ruc_net_revenue"] / spine["light_ruc_net_km"] * 1000).dropna()
    heavy = (spine["heavy_ruc_net_revenue"] / spine["heavy_ruc_net_km"] * 1000).dropna()
    schedules = ped_rate_schedules(repo_root, chart_rows)

    rows: list[dict[str, Any]] = []
    for series_name, path in (("Light RUC", light), ("Heavy RUC", heavy)):
        for fy, value in path.items():
            schedule = schedules.loc[int(fy)] if int(fy) in schedules.index else None
            planned_rate = float(schedule["planned"]) if schedule is not None and pd.notna(schedule["planned"]) else np.nan
            for segment in ("planned", *_DEFERRAL_SEGMENTS, "no_uplift"):
                selected_rate = (
                    float(schedule[segment])
                    if schedule is not None and segment in schedule.index and pd.notna(schedule[segment])
                    else planned_rate
                )
                multiplier = selected_rate / planned_rate if np.isfinite(planned_rate) and planned_rate > 0 else 1.0
                rows.append(
                    {
                        "june_year": int(fy),
                        "series": series_name,
                        "nzd_per_1000km": float(value) * float(multiplier),
                        "nzd_per_litre": np.nan,
                        "segment": segment,
                    }
                )
    for fy, row in schedules.iterrows():
        lp100 = intensity.get(fy, np.nan)
        if pd.isna(lp100):
            continue
        for column, series, segment in [
            ("history", "PED (petrol excise)", "history"),
            ("planned", "PED (petrol excise)", "planned"),
            *(
                (segment_column, "PED (petrol excise)", segment_column)
                for segment_column in _DEFERRAL_SEGMENTS
            ),
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
    """Fallback quarter map for callers that only carry annual factors.

    Every affected fiscal year maps to its quarters from 2027Q1 onward
    (bounded by the deferral window for a finite deferral). FY2027 therefore
    maps to 2027Q1-Q2 only, because its earlier quarters precede the uplift.
    """
    years = sorted(int(fy) for fy in factors)
    if not years:
        return {}
    spec = policy_spec(policy_state)
    uplift_start = quarter_serial(FED_UPLIFT_START_PERIOD)
    window_end = quarter_serial(spec.start_period) if spec.is_finite_deferral else None
    out: dict[int, tuple[str, ...]] = {}
    for fy in years:
        fy_quarters = (
            f"{fy - 1}Q3",
            f"{fy - 1}Q4",
            f"{fy}Q1",
            f"{fy}Q2",
        )
        selected = tuple(
            quarter
            for quarter in fy_quarters
            if quarter_serial(quarter) >= uplift_start
            and (window_end is None or quarter_serial(quarter) < window_end)
        )
        if selected:
            out[fy] = selected
    return out


def _augment_policy_audit(audit: pd.DataFrame, policy_state: str) -> pd.DataFrame:
    """Attach the registry's timing metadata to every policy audit row.

    Additive columns only: existing consumers keep their exact column names.
    ``affected_periods`` remains the (possibly lag/lead-extended) model
    response window each row actually carries;
    ``direct_rate_affected_quarters`` names the direct rate window alone so
    the two are never conflated.
    """
    if audit is None or audit.empty:
        return audit
    spec = policy_spec(policy_state)
    audit = audit.copy()
    audit["policy_label"] = spec.label
    audit["delay_months"] = spec.delay_months
    audit["delay_quarters"] = spec.delay_quarters
    audit["deferred_start_period"] = spec.start_period
    if spec.is_finite_deferral:
        audit["direct_rate_affected_quarters"] = ";".join(spec.direct_affected_quarters())
    elif spec.is_no_uplift:
        audit["direct_rate_affected_quarters"] = "2027Q1_onward"
    else:
        audit["direct_rate_affected_quarters"] = ""
    return audit


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
    policy_pair_factors: pd.DataFrame | None = None,
    ruc_class_revenue_by_fy: dict[int, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply one PED/RUC policy path using an audited display overlay.

    ``scenario_roles`` scopes the counterfactual to selected trace families.
    ``affected_periods_by_fy`` lets quarterly disaggregation localise each
    annual rate delta to the exact calendar quarters changed by the policy.
    When ``policy_pair_factors`` is supplied, fixed-finalist quarterly and
    annual factors also carry the RUC activity response (including lags and
    recursion).  The annual factors come from the full formula-rebuilt bridge,
    so hidden Heavy-BEV revenue and fixed admin/refunds remain correct.
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

    pair_id = _POLICY_PAIR_BY_STATE.get(policy_state)
    pair = pd.DataFrame()
    if pair_id and policy_pair_factors is not None and not policy_pair_factors.empty:
        required_pair_columns = {
            "pair_id",
            "time_grain",
            "period",
            "june_year",
            "series_id",
            "factor",
            "delta",
        }
        missing_pair_columns = required_pair_columns.difference(policy_pair_factors.columns)
        if missing_pair_columns:
            raise ValueError(
                "Policy pair factors are missing columns: " + ", ".join(sorted(missing_pair_columns))
            )
        pair = policy_pair_factors[
            policy_pair_factors["pair_id"].astype(str).eq(pair_id)
        ].copy()
        pair["factor_numeric"] = pd.to_numeric(pair["factor"], errors="coerce")
        pair["fy_numeric"] = pd.to_numeric(pair["june_year"], errors="coerce")
        pair["delta_numeric"] = pd.to_numeric(pair["delta"], errors="coerce")
        if pair.empty or pair["factor_numeric"].isna().any():
            raise ValueError(f"Policy replay pair {pair_id!r} is unavailable or non-numeric.")

    # Current finalist Base/High paths use the direct fixed-finalist replay.
    # The official MBU comparator has no behavioural model and therefore falls
    # through to the rate-only branch below with its volumes fixed.
    current_role = data.get("scenario_role", pd.Series("", index=data.index)).astype(str).isin(
        {"basecase", "comparison"}
    )
    if not pair.empty and bool((eligible_role & current_role).any()):
        quarterly_lookup = {
            (str(row.series_id), str(row.period)): float(row.factor_numeric)
            for row in pair[pair["time_grain"].astype(str).eq("quarterly")].itertuples()
        }
        annual_lookup = {
            (str(row.series_id), int(row.fy_numeric)): float(row.factor_numeric)
            for row in pair[pair["time_grain"].astype(str).eq("june_year")].itertuples()
            if pd.notna(row.fy_numeric)
        }
        activity_periods: dict[tuple[str, int], set[str]] = {}
        for row in pair[pair["time_grain"].astype(str).eq("quarterly")].itertuples():
            if pd.isna(row.fy_numeric) or pd.isna(row.delta_numeric) or abs(float(row.delta_numeric)) <= 1e-9:
                continue
            activity_periods.setdefault((str(row.series_id), int(row.fy_numeric)), set()).add(
                str(row.period)
            )

        def _pair_affected_periods(series_id: str, fy: int | None) -> tuple[str, ...]:
            if fy is None:
                return ()
            drivers: tuple[str, ...] = ()
            if series_id in {
                "ped_vkt_per_capita",
                "light_petrol_vkt",
                "ped_volume",
                "gross_ped_revenue",
            } or series_id in FED_AGGREGATE_SERIES:
                drivers = ("ped_vkt_per_capita",)
            elif series_id.startswith(("light_ruc", "light_bev_ruc", "phev_ruc")):
                drivers = ("light_ruc_net_km",)
            elif series_id.startswith(("heavy_ruc", "heavy_bev_ruc")):
                drivers = ("heavy_ruc_net_km",)
            elif series_id in RUC_AGGREGATE_SERIES:
                drivers = ("light_ruc_net_km", "heavy_ruc_net_km")
            elif series_id in TOTAL_AGGREGATE_SERIES:
                drivers = ("ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km")
            periods = set(affected_periods.get(fy, ()))
            for driver in drivers:
                periods.update(activity_periods.get((driver, fy), set()))
            return tuple(sorted(periods, key=_quarter_order))
        audit_rows: list[dict[str, Any]] = []
        pair_scope = eligible_role & current_role & is_forecast
        aggregate_ids = set(RUC_AGGREGATE_SERIES) | set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
        ped_delta_by_key: dict[tuple[str, str, str, int], float] = {}
        ruc_delta_by_key: dict[tuple[str, str, str, int], float] = {}

        def _record_adjustment(index: Any, new: float, factor: float, basis: str) -> None:
            old = float(numeric_value.at[index])
            fy_value = june_year.at[index]
            fy = int(fy_value) if pd.notna(fy_value) else None
            periods = _pair_affected_periods(str(data.at[index, "series_id"]), fy)
            data.at[index, "value"] = float(new)
            data.at[index, "_fed_baseline_value"] = old
            data.at[index, "_fed_annual_delta"] = float(new) - old
            data.at[index, "_fed_policy"] = policy_state
            data.at[index, "_fed_affected_quarters"] = ";".join(periods)
            audit_rows.append(
                {
                    "scenario_name": str(data.at[index, "scenario_name"]),
                    "scenario_role": str(data.at[index, "scenario_role"]),
                    "trace_name": str(data.at[index, "trace_name"]),
                    "fed_path": str(data.at[index, "fed_path"]),
                    "june_year": fy,
                    "time_grain": str(data.at[index, "time_grain"]),
                    "period": str(data.at[index, "period"]),
                    "series_id": str(data.at[index, "series_id"]),
                    "policy_state": policy_state,
                    "rate_factor": float(factors.get(fy, 1.0)) if fy is not None else 1.0,
                    "combined_model_and_rate_factor": float(factor),
                    "baseline_value": old,
                    "adjusted_value": float(new),
                    "value_delta": float(new) - old,
                    "affected_periods": ";".join(periods),
                    "transformation_basis": basis,
                }
            )

        # Apply direct fixed-finalist factors to activity/revenue leaves. Net
        # RUC is the one chart-carried RUC aggregate that receives its exact
        # full-bridge factor (it includes hidden Heavy-BEV and fixed admin).
        for index in data.index[pair_scope]:
            grain = str(data.at[index, "time_grain"])
            series_id = str(data.at[index, "series_id"])
            fy_value = june_year.at[index]
            if grain == "quarterly":
                factor = quarterly_lookup.get((series_id, str(data.at[index, "period"])), 1.0)
            elif grain == "june_year" and pd.notna(fy_value):
                factor = annual_lookup.get((series_id, int(fy_value)), 1.0)
                if (
                    factor == 1.0
                    and int(fy_value) > LAST_DECISION_GRADE_ANNUAL_FY
                    and series_id in _RATE_PRICED_LONG_RUN_SERIES
                ):
                    # The fixed-finalist pair factors only span the replay's
                    # own scenario window, so beyond it every post-model year
                    # would silently receive 1.0 and the policy lever would
                    # vanish from the long run. A rate change is permanent:
                    # fall back to the governed scalar rate ratio, which
                    # carries the terminal wedge to FY2055 by construction.
                    #
                    # Scoped to the rate-priced series, because ``factors`` is
                    # a RATE ratio. Applied to everything without a pair
                    # factor it also repriced activity and non-fuel revenue:
                    # at the FY2030/FY2031 seam ped_vkt_per_capita jumped from
                    # 1.0058 to 0.8777 - a cheaper pump price cutting VKT by
                    # 12%, the wrong sign - BEV/PHEV km moved against the
                    # "no approved class-specific charge elasticity" contract,
                    # and net_mvr_revenue was scaled by the petrol excise
                    # ratio, which broke ``net_mvr_revenue =
                    # mvr_revenue_net_admin_coo - mvr_refunds`` and made the
                    # aligned detail frames raise on every no-uplift render.
                    factor = float(factors.get(int(fy_value), 1.0))
            else:
                factor = 1.0
            old_value = numeric_value.at[index]
            if pd.isna(old_value) or abs(float(factor) - 1.0) <= 1e-12:
                continue
            if series_id in aggregate_ids and series_id not in RUC_AGGREGATE_SERIES:
                continue
            old = float(old_value)
            new = old * float(factor)
            _record_adjustment(
                index,
                new,
                float(factor),
                "fixed_finalist_policy_replay_leaf_or_net_ruc",
            )
            if grain == "june_year" and pd.notna(fy_value):
                key = _policy_row_key(data, index, int(fy_value))
                if series_id == "gross_ped_revenue":
                    ped_delta_by_key[key] = new - old
                elif series_id == "total_ruc_net_revenue":
                    ruc_delta_by_key[key] = new - old

        # Rebuild FED and whole-of-NLTF chart aggregates additively from the
        # canonical changed leaves. This holds refunds, TUC, MVR and other
        # fixed components unchanged and keeps chart/detail formulas exact.
        formula_scope = pair_scope & is_june & data["series_id"].astype(str).isin(
            set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
        )
        for index in data.index[formula_scope]:
            fy_value = june_year.at[index]
            old_value = numeric_value.at[index]
            if pd.isna(fy_value) or pd.isna(old_value):
                continue
            key = _policy_row_key(data, index, int(fy_value))
            ped_delta = ped_delta_by_key.get(key, 0.0)
            ruc_delta = ruc_delta_by_key.get(key, 0.0)
            series_id = str(data.at[index, "series_id"])
            delta = ped_delta if series_id in FED_AGGREGATE_SERIES else ped_delta + ruc_delta
            if abs(delta) <= 1e-12:
                continue
            old = float(old_value)
            new = old + delta
            _record_adjustment(
                index,
                new,
                new / old if abs(old) > 1e-12 else 1.0,
                "formula_rebuilt_from_ped_and_net_ruc_deltas",
            )

        touched = data["_fed_policy"].astype(str).eq(policy_state)
        policy_spec_for_state = policy_spec(policy_state)
        value_status = policy_spec_for_state.value_status
        data_scope = policy_spec_for_state.data_scope
        if "value_status" in data.columns:
            data.loc[touched, "value_status"] = value_status
        if "data_scope" in data.columns:
            data.loc[touched, "data_scope"] = data_scope

        # The annual pair factors are built from the governed fixed-finalist
        # bridge, while the visible Base/High quarters may already carry a VFM
        # uptake overlay.  Multiplying those differently weighted paths can
        # leave a small annual/quarterly residual even though both replay
        # factor sets are correct.  Reconcile after the policy overlay and
        # before Iran is appended, keeping actual and pre-policy quarters
        # fixed.  Iran's own delta-only reconciler can then inherit an exact
        # Base benchmark without moving its shock timing.
        adjusted_scenarios = {
            str(value)
            for value in data.loc[touched & current_role, "scenario_name"].dropna()
        }
        adjustable_periods_by_key: dict[
            tuple[str, int, str], tuple[str, ...]
        ] = {}
        annual_activity = (
            touched
            & current_role
            & is_june
            & data["series_id"].astype(str).isin(NATIVE_QUARTERLY_ACTIVITY_SERIES)
            & june_year.notna()
        )
        for index in data.index[annual_activity]:
            adjustable_periods_by_key[
                (
                    str(data.at[index, "scenario_name"]),
                    int(june_year.at[index]),
                    str(data.at[index, "series_id"]),
                )
            ] = tuple(
                period
                for period in str(data.at[index, "_fed_affected_quarters"]).split(";")
                if period
            )

        before_reconciliation = pd.to_numeric(data["value"], errors="coerce").copy()
        before_units = data.get(
            "value_unit", pd.Series("", index=data.index)
        ).fillna("").astype(str)
        before_series = data["series_id"].fillna("").astype(str)
        before_grain = data["time_grain"].fillna("").astype(str)
        raw_ruc_quarters = (
            before_grain.eq("quarterly")
            & before_series.isin({"light_ruc_net_km", "heavy_ruc_net_km"})
            & before_units.str.strip().str.casefold().eq("net km")
        )
        before_reconciliation.loc[raw_ruc_quarters] = (
            before_reconciliation.loc[raw_ruc_quarters] / 1_000_000.0
        )
        if adjusted_scenarios:
            reconciliation_status = f"{value_status}_quarterly_reconciled"
            reconciliation_scope = f"{data_scope}_quarterly_annual_reconciliation"
            data = reconcile_native_quarterly_activity_to_annual(
                data,
                scenario_names=adjusted_scenarios,
                adjustable_periods_by_key=adjustable_periods_by_key,
                value_status=reconciliation_status,
                data_scope=reconciliation_scope,
                mark_unchanged=False,
            )

            after_reconciliation = pd.to_numeric(data["value"], errors="coerce")
            reconciliation_changed = (
                data["scenario_name"].astype(str).isin(adjusted_scenarios)
                & data["time_grain"].astype(str).eq("quarterly")
                & data["series_id"].astype(str).isin(NATIVE_QUARTERLY_ACTIVITY_SERIES)
                & before_reconciliation.notna()
                & after_reconciliation.notna()
                & ~np.isclose(
                    before_reconciliation,
                    after_reconciliation,
                    rtol=0.0,
                    atol=1e-12,
                )
            )

            audit_lookup = {
                (
                    str(row.get("scenario_name", "")),
                    str(row.get("trace_name", "")),
                    str(row.get("fed_path", "")),
                    str(row.get("time_grain", "")),
                    str(row.get("period", "")),
                    str(row.get("series_id", "")),
                ): row
                for row in audit_rows
            }
            for index in data.index[reconciliation_changed]:
                fy_value = june_year.at[index]
                if pd.isna(fy_value):
                    continue
                fy = int(fy_value)
                scenario_name = str(data.at[index, "scenario_name"])
                series_id = str(data.at[index, "series_id"])
                annual_key = (scenario_name, fy, series_id)
                # A changed key absent from the policy map is a source-pack
                # unit/annual alignment (not a policy change), so retain its
                # neutral FED metadata while keeping the explicit data-scope
                # provenance assigned above.
                if annual_key not in adjustable_periods_by_key:
                    continue
                baseline = pd.to_numeric(
                    pd.Series([data.at[index, "_fed_baseline_value"]]),
                    errors="coerce",
                ).iloc[0]
                if pd.isna(baseline):
                    baseline = float(before_reconciliation.at[index])
                    data.at[index, "_fed_baseline_value"] = baseline
                final_value = float(after_reconciliation.at[index])
                data.at[index, "_fed_annual_delta"] = final_value - float(baseline)
                data.at[index, "_fed_policy"] = policy_state
                affected = ";".join(adjustable_periods_by_key[annual_key])
                data.at[index, "_fed_affected_quarters"] = affected

                audit_key = (
                    scenario_name,
                    str(data.at[index, "trace_name"]),
                    str(data.at[index, "fed_path"]),
                    "quarterly",
                    str(data.at[index, "period"]),
                    series_id,
                )
                audit_row = audit_lookup.get(audit_key)
                if audit_row is None:
                    audit_row = {
                        "scenario_name": scenario_name,
                        "scenario_role": str(data.at[index, "scenario_role"]),
                        "trace_name": str(data.at[index, "trace_name"]),
                        "fed_path": str(data.at[index, "fed_path"]),
                        "june_year": fy,
                        "time_grain": "quarterly",
                        "period": str(data.at[index, "period"]),
                        "series_id": series_id,
                        "policy_state": policy_state,
                        "rate_factor": float(factors.get(fy, 1.0)),
                        "affected_periods": affected,
                        "transformation_basis": "fixed_finalist_policy_replay_leaf_or_net_ruc",
                    }
                    audit_rows.append(audit_row)
                    audit_lookup[audit_key] = audit_row
                audit_row["combined_model_and_rate_factor"] = (
                    final_value / float(baseline) if abs(float(baseline)) > 1e-12 else 1.0
                )
                audit_row["baseline_value"] = float(baseline)
                audit_row["adjusted_value"] = final_value
                audit_row["value_delta"] = final_value - float(baseline)
                audit_row["quarterly_annual_reconciliation_delta"] = (
                    final_value - float(before_reconciliation.at[index])
                )
        return data, _augment_policy_audit(pd.DataFrame(audit_rows), policy_state)

    audit_rows: list[dict[str, Any]] = []
    ped_delta_by_key: dict[tuple[str, str, str, int], float] = {}
    ruc_delta_by_key: dict[tuple[str, str, str, int], float] = {}
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
        ped_delta_by_key[key] = ped_delta_by_key.get(key, 0.0) + (new - old)
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

    ruc_leaf_mask = (
        is_june
        & is_forecast
        & eligible_role
        & data["series_id"].astype(str).isin(_RUC_REVENUE_LEAVES)
    )
    for index in data.index[ruc_leaf_mask]:
        fy = june_year.at[index]
        if pd.isna(fy) or int(fy) not in factors or pd.isna(numeric_value.at[index]):
            continue
        factor = float(factors[int(fy)])
        old = float(numeric_value.at[index])
        new = old * factor
        data.at[index, "value"] = new
        key = _policy_row_key(data, index, int(fy))
        ruc_delta_by_key[key] = ruc_delta_by_key.get(key, 0.0) + (new - old)
        periods = tuple(affected_periods.get(int(fy), ()))
        data.at[index, "_fed_baseline_value"] = old
        data.at[index, "_fed_annual_delta"] = new - old
        data.at[index, "_fed_policy"] = policy_state
        data.at[index, "_fed_affected_quarters"] = ";".join(periods)

    if ped_delta_by_key or ruc_delta_by_key:
        aggregate_mask = (
            is_june
            & is_forecast
            & eligible_role
            & data["series_id"].astype(str).isin(
                set(RUC_AGGREGATE_SERIES) | set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
            )
        )
        for index in data.index[aggregate_mask]:
            if pd.isna(numeric_value.at[index]) or pd.isna(june_year.at[index]):
                continue
            fy = int(june_year.at[index])
            key = _policy_row_key(data, index, fy)
            series_id = str(data.at[index, "series_id"])
            ped_delta = ped_delta_by_key.get(key, 0.0)
            ruc_delta = ruc_delta_by_key.get(key, 0.0)
            scenario_role = str(data.at[index, "scenario_role"]) if "scenario_role" in data.columns else ""
            if (
                scenario_role == "official_comparator"
                and ruc_class_revenue_by_fy
                and fy in ruc_class_revenue_by_fy
                and fy in factors
            ):
                ruc_delta = float(ruc_class_revenue_by_fy[fy]) * (float(factors[fy]) - 1.0)
            if series_id in RUC_AGGREGATE_SERIES:
                delta = ruc_delta
            elif series_id in FED_AGGREGATE_SERIES:
                delta = ped_delta
            else:
                delta = ped_delta + ruc_delta
            if delta:
                old = float(numeric_value.at[index])
                data.at[index, "value"] = old + delta
                periods = tuple(affected_periods.get(fy, ()))
                data.at[index, "_fed_baseline_value"] = old
                data.at[index, "_fed_annual_delta"] = delta
                data.at[index, "_fed_policy"] = policy_state
                data.at[index, "_fed_affected_quarters"] = ";".join(periods)

    touched = data["_fed_policy"].astype(str).eq(policy_state)
    policy_spec_for_state = policy_spec(policy_state)
    if "value_status" in data.columns:
        data.loc[touched, "value_status"] = policy_spec_for_state.value_status
    if "data_scope" in data.columns:
        data.loc[touched, "data_scope"] = policy_spec_for_state.data_scope
    return data, _augment_policy_audit(pd.DataFrame(audit_rows), policy_state)


def _reject_official_scope(scenario_roles: set[str] | tuple[str, ...] | None, helper: str) -> None:
    """The current-model helpers may not touch official-comparator rows.

    The two scopes are different calculations, not one calculation over two
    role sets. The current model gets a behavioural fixed-finalist replay
    bounded by its own horizon; the official comparator gets a rate-only
    counterfactual with volumes fixed, over the source horizon. Routing an
    official row through here is what let the current-model horizon truncate
    the published comparator, so it fails loudly rather than silently.
    """
    if scenario_roles and OFFICIAL_SCOPE in {str(role) for role in scenario_roles}:
        raise ValueError(
            f"{helper} is a current-model helper and cannot process '{OFFICIAL_SCOPE}' rows. "
            "Use apply_official_comparator_rate_policy_to_chart_rows, which sources its own "
            "schedule from the MBU26 spine and publishes over the official horizon."
        )


def apply_fed_policy_state_to_chart_rows(
    chart_rows: pd.DataFrame,
    factors: dict[int, float],
    *,
    policy_state: str,
    scenario_roles: set[str] | tuple[str, ...] | None = None,
    affected_periods_by_fy: dict[int, tuple[str, ...]] | None = None,
    policy_pair_factors: pd.DataFrame | None = None,
    ruc_class_revenue_by_fy: dict[int, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply any governed non-published policy state to current-model rows.

    The generic entry point behind the six-month and no-uplift wrappers.
    ``policy_state`` is a calculation-layer state id; the published state is
    rejected because it never changes a row, and official-comparator rows are
    rejected because they are a different calculation with their own schedule.
    """
    spec = policy_spec(policy_state)
    if spec.is_published:
        raise ValueError("The published state has no chart-row counterfactual to apply.")
    _reject_official_scope(scenario_roles, "apply_fed_policy_state_to_chart_rows")
    return apply_fed_rate_policy_to_chart_rows(
        chart_rows,
        factors,
        policy_state=spec.calculation_state_id,
        scenario_roles=scenario_roles,
        affected_periods_by_fy=affected_periods_by_fy,
        policy_pair_factors=policy_pair_factors,
        ruc_class_revenue_by_fy=ruc_class_revenue_by_fy,
    )


def apply_fed_uplift_delay_to_chart_rows(
    chart_rows: pd.DataFrame,
    factors: dict[int, float],
    *,
    scenario_roles: set[str] | tuple[str, ...] | None = None,
    affected_periods_by_fy: dict[int, tuple[str, ...]] | None = None,
    policy_pair_factors: pd.DataFrame | None = None,
    ruc_class_revenue_by_fy: dict[int, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the six-month delay while preserving the source pack."""
    _reject_official_scope(scenario_roles, "apply_fed_uplift_delay_to_chart_rows")
    return apply_fed_rate_policy_to_chart_rows(
        chart_rows,
        factors,
        policy_state=FED_POLICY_STATE_DELAYED_6M,
        scenario_roles=scenario_roles,
        affected_periods_by_fy=affected_periods_by_fy,
        policy_pair_factors=policy_pair_factors,
        ruc_class_revenue_by_fy=ruc_class_revenue_by_fy,
    )


def apply_fed_uplift_off_to_chart_rows(
    chart_rows: pd.DataFrame,
    factors: dict[int, float],
    *,
    scenario_roles: set[str] | tuple[str, ...] | None = None,
    policy_pair_factors: pd.DataFrame | None = None,
    ruc_class_revenue_by_fy: dict[int, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Backward-compatible no-uplift wrapper around the generic overlay."""
    _reject_official_scope(scenario_roles, "apply_fed_uplift_off_to_chart_rows")
    return apply_fed_rate_policy_to_chart_rows(
        chart_rows,
        factors,
        policy_state=FED_POLICY_STATE_NO_UPLIFT,
        scenario_roles=scenario_roles,
        policy_pair_factors=policy_pair_factors,
        ruc_class_revenue_by_fy=ruc_class_revenue_by_fy,
    )


# ---------------------------------------------------------------------------
# Official-comparator policy factors
#
# The current-model policy replay is bounded by the supported current-model
# horizon (H20 / FY2030). The MBU26 official comparator is a different scope:
# it has no behavioural replay, receives a rate-only counterfactual with
# official volumes held fixed, and publishes over its own horizon. The two
# must not share one factor map, or the current-model cutoff would silently
# truncate the official comparator.
#
# These factors are derived from the MBU26 spine and the governed rate
# schedules - never from current-model chart rows.
# ---------------------------------------------------------------------------

OFFICIAL_SCOPE = "official_comparator"
CURRENT_MODEL_SCOPE = "current_model"
OFFICIAL_FACTOR_COLUMNS = (
    "scenario_scope",
    "policy_state",
    "june_year",
    "source_rate_nzd_per_litre",
    "target_rate_nzd_per_litre",
    "nominal_wedge_nzd_per_litre",
    "wedge_basis",
    "source_schedule_fy",
    "factor",
    "first_supported_fy",
    "last_supported_fy",
    "source_file",
    "source_sha256",
    "transformation_basis",
)
_OFFICIAL_SPINE_REL = "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_official_annual.csv"


def _sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def governed_no_uplift_wedge_schedule(
    repo_root: Path,
) -> tuple[dict[int, float], float, int, int]:
    """Per-June-year nominal no-uplift wedge, from the governed schedules.

    Returns ``(wedge_by_fy, terminal_wedge, last_source_fy, first_uplift_fy)``.

    The wedge is NOT a single constant. The 12c uplift lands in January 2027,
    which is halfway through FY2027, so the governed annual planned rate for
    FY2027 carries only about half of it:

        FY2026 and earlier   wedge 0.00
        FY2027               wedge 0.06   (two quarters pre-step, two post)
        FY2028 onward        wedge 0.12

    Every directly governed year therefore uses its own source-derived wedge.
    Only years beyond the source schedule carry the terminal wedge forward, so
    the no-uplift path stays parallel to the planned path.
    """
    fed = _fed_rate_paths(repo_root)
    by_path = fed.groupby(["fed_path", "FY"])["rate_nzd_per_litre"].mean()
    planned = by_path.get(_PLANNED_PATH, pd.Series(dtype=float))
    no_uplift = by_path.get(_NO_UPLIFT_PATH, pd.Series(dtype=float))
    shared = sorted(set(planned.index.astype(int)) & set(no_uplift.index.astype(int)))
    if not shared:
        raise ValueError(
            "Governed FED rate schedules carry no year with both a planned and a "
            "no-uplift rate; the nominal wedge cannot be derived."
        )
    wedge_by_fy = {
        int(year): float(planned.loc[year]) - float(no_uplift.loc[year]) for year in shared
    }
    if any(value < -1e-9 for value in wedge_by_fy.values()):
        raise ValueError("Governed no-uplift schedule is above the planned schedule.")
    last_source_fy = int(shared[-1])
    terminal_wedge = wedge_by_fy[last_source_fy]
    if terminal_wedge <= 0:
        raise ValueError(f"Terminal no-uplift wedge is not positive ({terminal_wedge}).")
    first_uplift_fy = next(
        (year for year in shared if wedge_by_fy[year] > 1e-9), last_source_fy
    )
    return wedge_by_fy, terminal_wedge, last_source_fy, int(first_uplift_fy)


def official_comparator_policy_factors(
    repo_root: Path, policy_state: str = FED_POLICY_STATE_NO_UPLIFT
) -> pd.DataFrame:
    """Rate-only MBU26 counterfactual factors over the official horizon.

    ``no_uplift``: carry the final governed per-year wedge where the source
    schedule has one, and the terminal wedge only beyond it, so the comparator stays parallel to the
    planned schedule instead of stopping where the current model stops.

    finite deferrals (``delay_6m`` … ``delay_36m``): identity outside the
    affected fiscal-year window, because a deferral only shifts the timing of
    the initial step; later planned increases retain their published dates.

    Fails closed for a June year whose official published PED rate cannot be
    derived: the policy-adjusted official trace must never silently fall back
    to published values while claiming the policy was applied.
    """
    policy_spec_for_state = policy_spec(policy_state)
    spine = _mbu26_spine(repo_root)
    for column in ("gross_ped_revenue", "ped_volume"):
        if column not in spine.columns:
            raise ValueError(
                f"MBU26 spine is missing {column}; official policy factors cannot be derived."
            )

    wedge_by_fy, terminal_wedge, last_source_fy, uplift_start_fy = (
        governed_no_uplift_wedge_schedule(repo_root)
    )
    delayed_years: set[int] = set()
    delayed_src = pd.Series(dtype=float)
    if policy_spec_for_state.is_finite_deferral:
        delayed_years = set(
            fed_policy_affected_periods(repo_root, policy_spec_for_state.calculation_state_id)
        )
        quarterly = ped_quarterly_rate_schedules(repo_root)
        delayed_src = quarterly.groupby("FY")[policy_spec_for_state.schedule_column].mean()
    fed = _fed_rate_paths(repo_root)
    planned_by_fy = (
        fed[fed["fed_path"].astype(str).eq(_PLANNED_PATH)].groupby("FY")["rate_nzd_per_litre"].mean()
    )
    source_sha = _sha256_of(repo_root / _OFFICIAL_SPINE_REL)

    published = (spine["gross_ped_revenue"] / spine["ped_volume"]).dropna()
    published = published[published > 0]
    if published.empty:
        raise ValueError("No official published PED rate could be derived from the MBU26 spine.")
    first_fy, last_fy = int(published.index.min()), int(published.index.max())

    rows: list[dict[str, Any]] = []
    for fy in sorted(int(value) for value in published.index):
        source_rate = float(published.loc[fy])
        if policy_spec_for_state.is_no_uplift:
            if fy < uplift_start_fy:
                continue  # the uplift does not exist yet, so no counterfactual
            if fy in wedge_by_fy:
                nominal_wedge = wedge_by_fy[fy]
                wedge_basis = "direct_source"
                source_schedule_fy = fy
                basis = (
                    "official published rate = gross_ped_revenue / ped_volume; nominal "
                    f"wedge {nominal_wedge:.6f} taken directly from the governed FY{fy} "
                    "planned-minus-no-uplift schedules"
                )
            else:
                nominal_wedge = terminal_wedge
                wedge_basis = "carried_terminal"
                source_schedule_fy = last_source_fy
                basis = (
                    "official published rate = gross_ped_revenue / ped_volume; terminal "
                    f"wedge {terminal_wedge:.6f} from governed FY{last_source_fy} carried "
                    "forward beyond the source schedule"
                )
            target_rate = source_rate - nominal_wedge
        elif policy_spec_for_state.is_finite_deferral:
            if fy not in delayed_years:
                continue  # identity outside the affected window
            if fy not in set(delayed_src.index.astype(int)) or fy not in set(
                planned_by_fy.index.astype(int)
            ):
                raise ValueError(
                    f"Official delayed policy needs governed planned and delayed rates for "
                    f"FY{fy}; at least one is unavailable. Refusing to fall back to published."
                )
            ratio = float(delayed_src.loc[fy]) / float(planned_by_fy.loc[fy])
            target_rate = source_rate * ratio
            nominal_wedge = source_rate - target_rate
            wedge_basis = "direct_source"
            source_schedule_fy = fy
            basis = "official published rate scaled by the governed delayed/planned rate ratio"
        else:
            continue
        if target_rate <= 0:
            raise ValueError(
                f"Official {policy_state} target rate for FY{fy} is not positive ({target_rate})."
            )
        rows.append(
            {
                "scenario_scope": OFFICIAL_SCOPE,
                "policy_state": policy_state,
                "june_year": fy,
                "source_rate_nzd_per_litre": source_rate,
                "target_rate_nzd_per_litre": target_rate,
                "nominal_wedge_nzd_per_litre": nominal_wedge,
                "wedge_basis": wedge_basis,
                "source_schedule_fy": source_schedule_fy,
                "factor": target_rate / source_rate,
                "first_supported_fy": first_fy,
                "last_supported_fy": last_fy,
                "source_file": _OFFICIAL_SPINE_REL,
                "source_sha256": source_sha,
                "transformation_basis": basis,
            }
        )
    return pd.DataFrame(rows, columns=list(OFFICIAL_FACTOR_COLUMNS))


def official_comparator_factor_map(
    repo_root: Path, policy_state: str = FED_POLICY_STATE_NO_UPLIFT
) -> dict[int, float]:
    """Per-FY multiplier for the official comparator, keyed by June year."""
    frame = official_comparator_policy_factors(repo_root, policy_state)
    return {
        int(record.june_year): float(record.factor)
        for record in frame.itertuples()
        if abs(float(record.factor) - 1.0) > 1e-9
    }


def apply_official_comparator_rate_policy_to_chart_rows(
    chart_rows: pd.DataFrame,
    repo_root: Path,
    *,
    policy_state: str,
    ruc_class_revenue_by_fy: dict[int, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the rate-only MBU26 counterfactual over the official horizon.

    Deliberately does NOT accept a factor dictionary. The official comparator
    sources its own schedule from the MBU26 spine and the governed rate paths,
    so a current-model factor map can never be looked up for an official row -
    which is what allowed the current-model H20 cutoff to truncate the
    published official horizon.

    Official activity, administration and refunds stay fixed; only the rate is
    counterfactual, and all five official RUC class-revenue leaves are
    repriced by the same ratio.

    This synthetic counterfactual is defined for the MBU26 vintage only: its
    factor schedule is derived from the MBU26 spine. Rows belonging to any
    other official vintage (e.g. ``befu26_official``) are never repriced;
    generating a BEFU26 counterfactual requires a separate owner decision.
    """
    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame()
    if str(policy_state) == FED_POLICY_STATE_PUBLISHED:
        return chart_rows, pd.DataFrame()  # published leaves the official vintages unchanged

    factors = official_comparator_factor_map(repo_root, policy_state)
    if not factors:
        return chart_rows, pd.DataFrame()

    engine_input = chart_rows
    untouched_other_officials = pd.DataFrame()
    if "scenario_name" in chart_rows.columns and "scenario_role" in chart_rows.columns:
        role = chart_rows["scenario_role"].fillna("").astype(str)
        scenario = chart_rows["scenario_name"].fillna("").astype(str)
        other_official_mask = role.eq(OFFICIAL_SCOPE) & ~scenario.eq("mbu26_official")
        if other_official_mask.any():
            untouched_other_officials = chart_rows[other_official_mask]
            engine_input = chart_rows[~other_official_mask]

    adjusted, audit = apply_fed_rate_policy_to_chart_rows(
        engine_input,
        factors,
        policy_state=policy_state,
        scenario_roles={OFFICIAL_SCOPE},
        ruc_class_revenue_by_fy=(
            ruc_class_revenue_by_fy
            if ruc_class_revenue_by_fy is not None
            else mbu26_ruc_class_revenue_by_fy(repo_root)
        ),
    )
    if not untouched_other_officials.empty:
        adjusted = pd.concat([adjusted, untouched_other_officials], ignore_index=True, sort=False)
    if not audit.empty:
        audit = audit.copy()
        audit["scenario_scope"] = OFFICIAL_SCOPE
        audit["rate_only_fixed_volumes"] = True
        audit["factor_source"] = "official_comparator_policy_factors"
    return adjusted, audit


# ---------------------------------------------------------------------------
# Official-comparator policy audit
#
# Four audit rows are not enough to review a counterfactual that moves nine
# reported components. Every affected component gets a row per June year,
# including hidden source leaves such as Heavy BEV that never become visible
# chart rows but do change the totals.
# ---------------------------------------------------------------------------

OFFICIAL_POLICY_AUDIT_COLUMNS = (
    "fy",
    "policy_state",
    "component",
    "component_kind",
    "source_series",
    "original_value",
    "source_effective_ped_rate",
    "nominal_wedge_nzd_per_litre",
    "wedge_basis",
    "source_schedule_fy",
    "target_ped_rate",
    "selected_rate_factor",
    "adjusted_value",
    "delta",
    "fixed_volume_status",
    "published_source_residual",
    "closure_residual",
    "source_file",
    "source_sha256",
    "transformation_basis",
)

# component -> (reporting name, source series). Order is the reporting order.
_OFFICIAL_AUDIT_REPRICED = (
    ("gross_ped_revenue", "gross_ped_revenue"),
    ("conventional_light_ruc_revenue", "light_ruc_net_revenue"),
    ("light_bev_revenue", "light_bev_ruc_net_revenue"),
    ("phev_revenue", "phev_ruc_net_revenue"),
    ("heavy_ruc_revenue", "heavy_ruc_net_revenue"),
    ("heavy_bev_revenue", "heavy_bev_ruc_net_revenue"),
)
_OFFICIAL_AUDIT_FIXED = (
    "ruc_admin_revenue",
    "ruc_refunds",
    "fed_refunds",
    "mvr_admin_revenue",
    "mvr_refunds",
    "gross_lpg_revenue",
    "gross_cng_revenue",
    "tuc_net_revenue",
)
_OFFICIAL_AUDIT_AGGREGATES = ("net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue")


def _official_formula_totals(row: pd.Series, ped: float, ruc_leaves: dict[str, float]) -> dict[str, float]:
    """Rebuild the three official totals from leaves and fixed components.

    Run twice per June year - once on published values and once on adjusted
    values - so the published spine's own residual can be separated from the
    policy arithmetic instead of being silently absorbed into it.
    """
    gross_ruc = sum(ruc_leaves.values()) + float(row["ruc_refunds"])
    total_ruc = gross_ruc - float(row["ruc_admin_revenue"]) - float(row["ruc_refunds"])
    gross_fed = ped + float(row["gross_lpg_revenue"]) + float(row["gross_cng_revenue"])
    net_fed = gross_fed - float(row["fed_refunds"])
    gross_mvr = float(row["mr1_revenue"]) + float(row["mr2_revenue"]) + float(row["coo_revenue"])
    total_gross = gross_ruc + gross_fed + gross_mvr + float(row["tuc_net_revenue"])
    total_admin = float(row["ruc_admin_revenue"]) + float(row["mvr_admin_revenue"]) + float(row["coo_revenue"])
    total_refunds = float(row["ruc_refunds"]) + float(row["fed_refunds"]) + float(row["mvr_refunds"])
    return {
        "net_fed_revenue": net_fed,
        "total_ruc_net_revenue": total_ruc,
        "total_nltf_net_revenue": total_gross - total_admin - total_refunds,
    }


def official_comparator_policy_audit_frame(
    repo_root: Path, policy_state: str = FED_POLICY_STATE_NO_UPLIFT
) -> pd.DataFrame:
    """Per-FY, per-component audit of the official rate-only counterfactual.

    Covers all nine affected components plus the fixed rows that must NOT
    move, so "administration and refunds are unchanged" is evidenced rather
    than asserted.

    ``published_source_residual`` carries the MBU26 spine's own formula
    inconsistency where one exists - FY2027 Total RUC is about 0.63 off in the
    published source. It is reported, never corrected: published MBU26 must
    stay unchanged. ``closure_residual`` is the policy arithmetic alone, net of
    that source residual, and must close to 1e-6.
    """
    spine = _mbu26_spine(repo_root)
    factors = official_comparator_policy_factors(repo_root, policy_state)
    if factors.empty:
        return pd.DataFrame(columns=list(OFFICIAL_POLICY_AUDIT_COLUMNS))
    source_sha = _sha256_of(repo_root / _OFFICIAL_SPINE_REL)

    rows: list[dict[str, Any]] = []
    for record in factors.itertuples():
        fy = int(record.june_year)
        if fy not in spine.index:
            continue
        source = spine.loc[fy]
        factor = float(record.factor)
        common = {
            "fy": fy,
            "policy_state": policy_state,
            "source_effective_ped_rate": float(record.source_rate_nzd_per_litre),
            "nominal_wedge_nzd_per_litre": float(record.nominal_wedge_nzd_per_litre),
            "wedge_basis": str(record.wedge_basis),
            "source_schedule_fy": int(record.source_schedule_fy),
            "target_ped_rate": float(record.target_rate_nzd_per_litre),
            "selected_rate_factor": factor,
            "source_file": _OFFICIAL_SPINE_REL,
            "source_sha256": source_sha,
        }

        published_ped = float(source["gross_ped_revenue"])
        adjusted_ped = published_ped * factor
        published_leaves = {series: float(source[series]) for series in _RUC_REVENUE_LEAVES}
        adjusted_leaves = {series: value * factor for series, value in published_leaves.items()}

        for component, series in _OFFICIAL_AUDIT_REPRICED:
            original = float(source[series])
            adjusted = original * factor
            rows.append(
                {
                    **common,
                    "component": component,
                    "component_kind": "repriced_leaf",
                    "source_series": series,
                    "original_value": original,
                    "adjusted_value": adjusted,
                    "delta": adjusted - original,
                    "fixed_volume_status": "volume_fixed_rate_only",
                    "published_source_residual": 0.0,
                    "closure_residual": 0.0,
                    "transformation_basis": (
                        f"{series} x official rate factor {factor:.12f}; official volume held "
                        f"fixed. {record.transformation_basis}"
                    ),
                }
            )

        for series in _OFFICIAL_AUDIT_FIXED:
            original = float(source[series])
            rows.append(
                {
                    **common,
                    "component": series,
                    "component_kind": "fixed",
                    "source_series": series,
                    "original_value": original,
                    "adjusted_value": original,
                    "delta": 0.0,
                    "fixed_volume_status": "fixed_component_not_repriced",
                    "published_source_residual": 0.0,
                    "closure_residual": 0.0,
                    "transformation_basis": (
                        "MBU26 fixed component: administration, refunds and non-PED fuel "
                        "duties are unaffected by a PED rate counterfactual."
                    ),
                }
            )

        published_totals = _official_formula_totals(source, published_ped, published_leaves)
        adjusted_totals = _official_formula_totals(source, adjusted_ped, adjusted_leaves)
        ped_delta = adjusted_ped - published_ped
        ruc_delta = sum(adjusted_leaves.values()) - sum(published_leaves.values())
        expected_delta = {
            "net_fed_revenue": ped_delta,
            "total_ruc_net_revenue": ruc_delta,
            "total_nltf_net_revenue": ped_delta + ruc_delta,
        }
        for component in _OFFICIAL_AUDIT_AGGREGATES:
            published = float(source[component])
            source_residual = published_totals[component] - published
            # The reported value keeps the published source trace and adds only
            # the policy delta, so a source inconsistency is never quietly
            # rebased away by the counterfactual.
            adjusted = published + expected_delta[component]
            closure = (adjusted_totals[component] - source_residual) - adjusted
            rows.append(
                {
                    **common,
                    "component": component,
                    "component_kind": "rebuilt_aggregate",
                    "source_series": component,
                    "original_value": published,
                    "adjusted_value": adjusted,
                    "delta": expected_delta[component],
                    "fixed_volume_status": "volume_fixed_rate_only",
                    "published_source_residual": source_residual,
                    "closure_residual": closure,
                    "transformation_basis": (
                        "rebuilt formulaically from repriced leaves plus fixed MBU26 "
                        "components; published source value preserved and only the policy "
                        "delta added"
                    ),
                }
            )
    return pd.DataFrame(rows, columns=list(OFFICIAL_POLICY_AUDIT_COLUMNS))

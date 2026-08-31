"""Fleetwide FED -> RUC transition overlay (1 January 2028).

Simulates the policy where every fuel excise duty (FED) tax is replaced by
road user charges from 2028Q1: petrol light vehicles stop paying excise at
the pump and are enrolled onto RUC at the full light-vehicle rate, with
compliance leakage on the newly enrolled base only. Two governed leakage
cases are offered, built from the lower and upper ends of NZTA's detailed
compliance evidence:

- ``managed``  - 70% debt recovery on known non-compliance, 9% long-run
  gross known non-compliance, 5% terminal unknown/unrecoverable, $34m
  one-off implementation cost and $16m/yr ongoing collection cost;
- ``stress``   - 50% debt recovery, 12% long-run known non-compliance,
  11% terminal unknown/unrecoverable, $111m one-off and $31m/yr ongoing.

Accounting is quarterly (the transition starts mid-fiscal-year: FY2028 =
2027Q3..2028Q2, so exactly two calendar quarters keep FED and two are on
RUC) and aggregated to the June-year grain the revenue layer uses:

- newly transitioned light-petrol RUC is ``Gq = Kq * Rq / 1000`` where
  ``Kq`` is quarterly light petrol VKT (million km; the governed annual
  ``light_petrol_vkt`` split equally across the year's quarters - a stated
  modelling assumption, not source data) and ``Rq`` is the selected timing
  state's full light-vehicle RUC rate in NZD per 1,000 km (the annual
  rate implied by the already-repriced rows, shaped within the year by the
  governed FED rate staircase so uplifts land at 1 January);
- leakage applies ONLY to the newly enrolled light-petrol base, by
  transition age ``a = 1 + floor((q - 2028Q1) / 4)``;
- FED (gross petrol excise, gross FED and net FED, which nets the fixed
  refund line) is removed from 2028Q1: FY2028 keeps the staircase-weighted
  pre-transition share, later years are zero, so FED refunds cease with
  FED itself;
- PHEVs lose the ~50% discounted RUC rate that compensated for petrol
  excise they no longer pay: their revenue is re-priced to the full
  light-vehicle rate for post-transition quarters (no leakage - they are
  existing enrolled RUC payers);
- travel demand is NOT adjusted: the documents quantify compliance
  leakage and collection costs, not a robust aggregate VKT elasticity to
  swapping pump tax for distance charging, so each scenario's governed
  activity paths are used unchanged;
- one-off and ongoing collection costs are carried as explicit, separately
  audited series and subtracted from Total NLTF only - never buried in the
  RUC aggregates. Ongoing costs escalate at an explicit 2.0%/yr modelling
  assumption (the model carries no governed inflation index).

Applied as a deterministic display-time overlay after the policy-runtime
state is loaded: governed pack bytes are untouched, the materialised 13x13
policy catalogue is not multiplied, and every adjusted row is tagged for
audit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .ev_uptake_levers import (
    FED_AGGREGATE_SERIES,
    RUC_AGGREGATE_SERIES,
    TOTAL_AGGREGATE_SERIES,
)
from .fed_policy_states import policy_spec, quarter_serial

FED_RUC_TRANSITION_OFF = "off"
FED_RUC_TRANSITION_MANAGED = "managed"
FED_RUC_TRANSITION_STRESS = "stress"
FED_RUC_TRANSITION_STATES = (
    FED_RUC_TRANSITION_OFF,
    FED_RUC_TRANSITION_MANAGED,
    FED_RUC_TRANSITION_STRESS,
)
FED_RUC_TRANSITION_LABELS = {
    FED_RUC_TRANSITION_OFF: "No fleetwide transition",
    FED_RUC_TRANSITION_MANAGED: "Fleetwide RUC from 1 Jan 2028 - managed leakage",
    FED_RUC_TRANSITION_STRESS: "Fleetwide RUC from 1 Jan 2028 - leakage stress",
}

TRANSITION_START_PERIOD = "2028Q1"
TRANSITION_START_FY = 2028  # FY2028 = 2027Q3..2028Q2 contains the start
_START_SERIAL = quarter_serial(TRANSITION_START_PERIOD)

FED_RUC_TRANSITION_NOTE = (
    "FED -> RUC transition: from 1 Jan 2028 fuel excise duty is removed "
    "completely and light petrol road use is charged RUC at the selected "
    "timing state's full light-vehicle rate. Compliance leakage applies to "
    "the newly enrolled petrol base only; PHEVs move to the full light RUC "
    "rate once the petrol excise their discount compensated for is gone. "
    "Travel demand is unchanged - the compliance evidence quantifies "
    "leakage and collection cost, not a demand response. Display-time "
    "overlay - the governed pack is unchanged."
)

LIGHT_PETROL_RUC_SERIES = "light_petrol_ruc_net_revenue"
TRANSITION_LEAKAGE_SERIES = "fed_ruc_transition_leakage"
TRANSITION_COLLECTION_COST_SERIES = "fed_ruc_transition_collection_cost"
TRANSITION_ONEOFF_COST_SERIES = "fed_ruc_transition_oneoff_cost"
TRANSITION_SERIES = (
    LIGHT_PETROL_RUC_SERIES,
    TRANSITION_LEAKAGE_SERIES,
    TRANSITION_COLLECTION_COST_SERIES,
    TRANSITION_ONEOFF_COST_SERIES,
)
TRANSITION_SERIES_LABELS = {
    LIGHT_PETROL_RUC_SERIES: "Light petrol RUC revenue",
    TRANSITION_LEAKAGE_SERIES: "RUC transition leakage",
    TRANSITION_COLLECTION_COST_SERIES: "RUC transition collection costs",
    TRANSITION_ONEOFF_COST_SERIES: "RUC transition one-off costs",
}
# Series scaled proportionally with revenue by downstream derived traces
# (persistent downside wedge, high-population re-tether). The cost series are
# deliberately absent: implementation and collection costs do not scale with
# a demand wedge.
TRANSITION_PROPORTIONAL_SERIES = (
    LIGHT_PETROL_RUC_SERIES,
    TRANSITION_LEAKAGE_SERIES,
)

# FED series removed from 2028Q1. ``net_fed_revenue`` nets the fixed official
# refund line, so scaling all three by the same pre-transition share retires
# refunds together with the duty itself.
FED_REMOVED_SERIES = ("gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue")

# The documents' post-transition annual non-road FED estimate, used ONLY as a
# reasonableness reference in the audit - never subtracted from revenue.
NONROAD_FED_REFERENCE_M = 150.0

_EXCLUDED_SCENARIO_ROLES = ("official_comparator", "actual")


class FedRucTransitionError(ValueError):
    """An unknown FED->RUC transition state or unusable input reached the overlay."""


def normalise_fed_ruc_transition_state(value: Any) -> str:
    """Closed-vocabulary read of a transition state. Unknown values fail closed."""
    text = str(value or "").strip().lower()
    if not text:
        return FED_RUC_TRANSITION_OFF
    for state, label in FED_RUC_TRANSITION_LABELS.items():
        if text in (state, label.lower()):
            return state
    raise FedRucTransitionError(
        f"{value!r} is not a FED->RUC transition state; expected one of "
        f"{FED_RUC_TRANSITION_STATES}"
    )


@dataclass(frozen=True)
class FedRucTransitionParams:
    """One governed leakage case. All rates are fractions of gross petrol RUC."""

    debt_recovery_rate: float
    transition_year_recoverable: float
    transition_year_unrecoverable: float
    known_noncompliance_by_age: tuple[float, ...]  # gross, ages 2..7
    long_run_known_noncompliance: float  # gross, age >= 8
    unknown_unrecoverable_age2: float
    unknown_unrecoverable_terminal: float  # reached at age 7, flat after
    one_off_cost_m: float
    ongoing_cost_m_per_year: float
    cost_escalation_rate: float = 0.02  # explicit modelling assumption

    def key(self) -> tuple[float, ...]:
        flat: list[float] = []
        for value in asdict(self).values():
            if isinstance(value, tuple):
                flat.extend(float(v) for v in value)
            else:
                flat.append(float(value))
        return tuple(round(v, 6) for v in flat)


FED_RUC_TRANSITION_PARAMS = {
    FED_RUC_TRANSITION_MANAGED: FedRucTransitionParams(
        debt_recovery_rate=0.70,
        transition_year_recoverable=0.03,
        transition_year_unrecoverable=0.05,
        known_noncompliance_by_age=(0.20, 0.18, 0.16, 0.14, 0.12, 0.10),
        long_run_known_noncompliance=0.09,
        unknown_unrecoverable_age2=0.03,
        unknown_unrecoverable_terminal=0.05,
        one_off_cost_m=34.0,
        ongoing_cost_m_per_year=16.0,
    ),
    FED_RUC_TRANSITION_STRESS: FedRucTransitionParams(
        debt_recovery_rate=0.50,
        transition_year_recoverable=0.03,
        transition_year_unrecoverable=0.05,
        known_noncompliance_by_age=(0.20, 0.18, 0.16, 0.14, 0.12, 0.10),
        long_run_known_noncompliance=0.12,
        unknown_unrecoverable_age2=0.03,
        unknown_unrecoverable_terminal=0.11,
        one_off_cost_m=111.0,
        ongoing_cost_m_per_year=31.0,
    ),
}


def transition_age(period: str) -> int:
    """Transition age of a calendar quarter: 1 within calendar 2028, 2 in 2029, ..."""
    return 1 + (quarter_serial(period) - _START_SERIAL) // 4


def leakage_rate(age: int, params: FedRucTransitionParams) -> float:
    """Net leakage fraction of gross newly-transitioned petrol RUC at an age."""
    if age < 1:
        return 0.0
    unrecovered = 1.0 - params.debt_recovery_rate
    if age == 1:
        return params.transition_year_recoverable * unrecovered + params.transition_year_unrecoverable
    if age <= 1 + len(params.known_noncompliance_by_age):
        known = params.known_noncompliance_by_age[age - 2]
        terminal_age = 1 + len(params.known_noncompliance_by_age)
        span = max(terminal_age - 2, 1)
        unknown = params.unknown_unrecoverable_age2 + (
            params.unknown_unrecoverable_terminal - params.unknown_unrecoverable_age2
        ) * (age - 2) / span
    else:
        known = params.long_run_known_noncompliance
        unknown = params.unknown_unrecoverable_terminal
    return known * unrecovered + unknown


def fiscal_year_quarters(june_year: int) -> tuple[str, str, str, str]:
    """Calendar quarters of a June fiscal year: FY2028 -> 2027Q3..2028Q2."""
    year = int(june_year)
    return (f"{year - 1}Q3", f"{year - 1}Q4", f"{year}Q1", f"{year}Q2")


def _schedule_levels(schedule: pd.DataFrame, policy_state: str) -> pd.Series:
    """Quarterly staircase levels ($/L) of the selected timing state.

    The FED rate schedule carries the exact 1-January step timing of the
    selected state, so it is the governed within-year shape for both the
    pre/post-transition FED split and the RUC rate staircase (RUC rates take
    the staircase proportionally - the rate/rate ratio treatment).
    """
    column = policy_spec(policy_state).schedule_column
    if column not in schedule.columns:
        raise FedRucTransitionError(
            f"rate schedule has no column {column!r} for policy state {policy_state!r}"
        )
    levels = pd.to_numeric(schedule[column], errors="coerce")
    return levels[levels.notna() & (levels > 0)]


def _quarter_weights(levels: pd.Series, quarters: tuple[str, ...]) -> list[float]:
    """Schedule levels for a fiscal year's quarters; equal weights if uncovered."""
    weights = [float(levels.get(q, float("nan"))) for q in quarters]
    if any(not np.isfinite(w) or w <= 0 for w in weights):
        return [1.0] * len(quarters)
    return weights


def apply_fed_ruc_transition_to_chart_rows(
    chart_rows: pd.DataFrame,
    schedule: pd.DataFrame,
    state: str,
    *,
    policy_state: str,
    drift_assumptions: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replace FED with fleetwide RUC from 2028Q1 (display overlay).

    ``chart_rows`` must already carry the selected timing state (the overlay
    runs downstream of the policy-runtime read); ``schedule`` is the governed
    quarterly FED rate schedule (``ped_quarterly_rate_schedules``);
    ``policy_state`` is the current 12c policy state id, used only for the
    within-year staircase shape. Returns the adjusted rows and a quarterly
    audit frame. Official comparator and actual rows are never touched.
    """
    state = normalise_fed_ruc_transition_state(state)
    if state == FED_RUC_TRANSITION_OFF or chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame()
    params = FED_RUC_TRANSITION_PARAMS[state]
    levels = _schedule_levels(schedule, policy_state)

    data = chart_rows.copy()
    numeric_value = pd.to_numeric(data.get("value"), errors="coerce")
    june_year = pd.to_numeric(data.get("june_year"), errors="coerce")
    series_id = data.get("series_id", pd.Series("", index=data.index)).astype(str)
    is_june = data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")
    is_forecast = ~data.get("row_type", pd.Series("", index=data.index)).astype(str).eq(
        "historical_actual"
    )
    role = data.get("scenario_role", pd.Series("", index=data.index)).astype(str)
    eligible = is_june & is_forecast & ~role.isin(_EXCLUDED_SCENARIO_ROLES)

    def _row_value(mask: pd.Series) -> float | None:
        if not mask.any() or not numeric_value[mask].notna().any():
            return None
        return float(numeric_value[mask].iloc[0])

    intensity_lookup = _drift_intensity_lookup(drift_assumptions)

    scenario_col = data.get("scenario_name", pd.Series("", index=data.index)).astype(str)
    scenarios = sorted(scenario_col[eligible].unique())
    fys = sorted(
        int(fy)
        for fy in june_year[eligible].dropna().unique()
        if int(fy) >= TRANSITION_START_FY
    )

    audit_rows: list[dict[str, Any]] = []
    new_rows: list[pd.Series] = []
    # (scenario, fy) -> per-aggregate-series revenue delta in $m
    aggregate_deltas: dict[tuple[str, int], dict[str, float]] = {}

    for scenario in scenarios:
        scenario_mask = eligible & scenario_col.eq(scenario)
        last_intensity: float | None = None
        for fy in fys:
            fy_mask = scenario_mask & june_year.eq(fy)

            def series_value(name: str) -> float | None:
                return _row_value(fy_mask & series_id.eq(name))

            petrol_vkt = series_value("light_petrol_vkt")
            light_rev = series_value("light_ruc_net_revenue")
            light_km = series_value("light_ruc_net_km")
            if (
                petrol_vkt is None
                or light_rev is None
                or light_km is None
                or petrol_vkt <= 0
                or light_rev <= 0
                or light_km <= 0
            ):
                continue

            quarters = fiscal_year_quarters(fy)
            weights = _quarter_weights(levels, quarters)
            total_weight = sum(weights)
            pre_share = (
                sum(w for q, w in zip(quarters, weights) if quarter_serial(q) < _START_SERIAL)
                / total_weight
            )

            annual_rate = light_rev / light_km * 1000.0  # NZD per 1,000 km
            mean_weight = total_weight / len(weights)

            gross_y = leakage_y = collected_y = ongoing_cost_y = 0.0
            for quarter, weight in zip(quarters, weights):
                if quarter_serial(quarter) < _START_SERIAL:
                    continue
                age = transition_age(quarter)
                k_q = petrol_vkt / 4.0
                r_q = annual_rate * weight / mean_weight
                g_q = k_q * r_q / 1000.0
                rate = leakage_rate(age, params)
                leak_q = g_q * rate
                collected_q = g_q - leak_q
                cost_q = (
                    params.ongoing_cost_m_per_year
                    / 4.0
                    * (1.0 + params.cost_escalation_rate) ** (age - 1)
                )
                gross_y += g_q
                leakage_y += leak_q
                collected_y += collected_q
                ongoing_cost_y += cost_q
                audit_rows.append(
                    {
                        "scenario_name": scenario,
                        "june_year": fy,
                        "quarter": quarter,
                        "transition_age": age,
                        "petrol_vkt_million_km": k_q,
                        "light_ruc_rate_per_1000km": r_q,
                        "gross_petrol_ruc_m": g_q,
                        "leakage_rate": rate,
                        "leakage_m": leak_q,
                        "collected_petrol_ruc_m": collected_q,
                        "ongoing_collection_cost_m": cost_q,
                    }
                )
            oneoff_cost_y = params.one_off_cost_m if fy == TRANSITION_START_FY else 0.0

            # PHEVs move to the full light-vehicle rate for post-transition
            # quarters: the discounted rate compensated for petrol excise
            # they no longer pay. Existing enrolled payers - no leakage.
            phev_rev = series_value("phev_ruc_net_revenue")
            phev_km = series_value("phev_ruc_net_km")
            phev_delta = 0.0
            if phev_rev is not None and phev_km is not None and phev_rev > 0 and phev_km > 0:
                phev_rate = phev_rev / phev_km * 1000.0
                if phev_rate > 0:
                    ratio = annual_rate / phev_rate
                    phev_delta = phev_rev * (1.0 - pre_share) * (ratio - 1.0)
                    phev_mask = fy_mask & series_id.eq("phev_ruc_net_revenue")
                    data.loc[phev_mask, "value"] = phev_rev + phev_delta

            # FED removal: keep the staircase-weighted pre-transition share.
            fed_deltas: dict[str, float] = {}
            for fed_series in FED_REMOVED_SERIES:
                mask = fy_mask & series_id.eq(fed_series)
                old = _row_value(mask)
                if old is None:
                    continue
                data.loc[mask, "value"] = old * pre_share
                fed_deltas[fed_series] = old * (pre_share - 1.0)

            fed_gross_delta = fed_deltas.get("gross_fed_revenue", 0.0)
            fed_net_delta = fed_deltas.get("net_fed_revenue", 0.0)
            aggregate_deltas[(scenario, fy)] = {
                "gross_ruc_revenue": gross_y + phev_delta,
                "ruc_revenue_net_admin": collected_y + phev_delta,
                "total_ruc_net_revenue": collected_y + phev_delta,
                "total_fed_ruc_net_revenue": fed_net_delta + collected_y + phev_delta,
                "total_gross_revenue": fed_gross_delta + gross_y + phev_delta,
                "total_revenue_net_admin": fed_net_delta + collected_y + phev_delta,
                "total_nltf_net_revenue": (
                    fed_net_delta + collected_y + phev_delta - ongoing_cost_y - oneoff_cost_y
                ),
            }

            # Audit the non-road FED the zeroing forgoes (never re-subtracted).
            net_fed_old = fed_deltas.get("net_fed_revenue")
            net_fed_old = -net_fed_old / (1.0 - pre_share) if net_fed_old and pre_share < 1 else None
            gross_ped_old = fed_deltas.get("gross_ped_revenue")
            gross_ped_old = (
                -gross_ped_old / (1.0 - pre_share) if gross_ped_old and pre_share < 1 else None
            )
            ped_volume = series_value("ped_volume")
            intensity = intensity_lookup.get((scenario, fy))
            if intensity is not None:
                last_intensity = intensity
            elif last_intensity is not None:
                intensity = last_intensity
            foregone_nonroad = onroad_equiv = None
            if (
                net_fed_old is not None
                and gross_ped_old is not None
                and ped_volume
                and intensity
                and ped_volume > 0
            ):
                implied_ped_rate = gross_ped_old / ped_volume
                onroad_equiv = petrol_vkt * intensity / 100.0 * implied_ped_rate
                foregone_nonroad = net_fed_old - onroad_equiv

            template_mask = fy_mask & series_id.eq("light_ruc_net_revenue")
            template_index = data.index[template_mask]
            if len(template_index):
                template = data.loc[template_index[0]]
                series_values = {
                    LIGHT_PETROL_RUC_SERIES: collected_y,
                    TRANSITION_LEAKAGE_SERIES: leakage_y,
                    TRANSITION_COLLECTION_COST_SERIES: ongoing_cost_y,
                    TRANSITION_ONEOFF_COST_SERIES: oneoff_cost_y,
                }
                formulas = {
                    LIGHT_PETROL_RUC_SERIES: (
                        "light petrol VKT / 4 per quarter * staircase-shaped full "
                        "light RUC rate / 1000, net of age-based leakage"
                    ),
                    TRANSITION_LEAKAGE_SERIES: (
                        "gross newly-transitioned petrol RUC * age-based net leakage rate"
                    ),
                    TRANSITION_COLLECTION_COST_SERIES: (
                        "ongoing collection cost / 4 per post-transition quarter, "
                        "escalated 2.0%/yr (modelling assumption)"
                    ),
                    TRANSITION_ONEOFF_COST_SERIES: (
                        "one-off implementation cost recorded in the transition year"
                    ),
                }
                for new_series, value in series_values.items():
                    if new_series == TRANSITION_ONEOFF_COST_SERIES and value == 0.0:
                        continue
                    row = template.copy()
                    label = TRANSITION_SERIES_LABELS[new_series]
                    row["series_id"] = new_series
                    row["stream"] = new_series
                    row["stream_label"] = label
                    row["series_label"] = label
                    row["value"] = value
                    row["formula"] = formulas[new_series]
                    row["bridge_method"] = formulas[new_series]
                    row["source_basis"] = "FED->RUC transition overlay (" + state + ")"
                    row["value_status"] = "fed_ruc_transition"
                    row["data_scope"] = "fed_ruc_transition_overlay"
                    for cleared in ("official_value", "residual_vs_official"):
                        if cleared in row.index:
                            row[cleared] = None
                    if "canonical_stream_key" in row.index:
                        row["canonical_stream_key"] = new_series.upper()
                    if "canonical_join_key" in row.index:
                        row["canonical_join_key"] = (
                            f"{new_series.upper()}|FY{fy}|{scenario}"
                        )
                    new_rows.append(row)

            audit_rows.append(
                {
                    "scenario_name": scenario,
                    "june_year": fy,
                    "quarter": "FY total",
                    "transition_age": None,
                    "pre_transition_fed_share": pre_share,
                    "gross_petrol_ruc_m": gross_y,
                    "leakage_m": leakage_y,
                    "collected_petrol_ruc_m": collected_y,
                    "phev_full_rate_uplift_m": phev_delta,
                    "fed_removed_net_m": -fed_net_delta,
                    "ongoing_collection_cost_m": ongoing_cost_y,
                    "one_off_cost_m": oneoff_cost_y,
                    "net_nltf_delta_m": aggregate_deltas[(scenario, fy)][
                        "total_nltf_net_revenue"
                    ],
                    "onroad_fed_equivalent_m": onroad_equiv,
                    "foregone_nonroad_fed_m": foregone_nonroad,
                    "nonroad_fed_reference_m": NONROAD_FED_REFERENCE_M,
                }
            )

    if aggregate_deltas:
        aggregate_series = (
            set(FED_AGGREGATE_SERIES) | set(RUC_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
        ) - set(FED_REMOVED_SERIES)
        aggregate_mask = eligible & series_id.isin(aggregate_series)
        for index in data.index[aggregate_mask]:
            if pd.isna(numeric_value.at[index]):
                continue
            fy_value = june_year.at[index]
            key = (str(scenario_col.at[index]), int(fy_value) if pd.notna(fy_value) else -1)
            deltas = aggregate_deltas.get(key)
            if not deltas:
                continue
            delta = deltas.get(str(data.at[index, "series_id"]), 0.0)
            if delta:
                data.at[index, "value"] = float(numeric_value.at[index]) + delta

    touched_series = (
        set(FED_REMOVED_SERIES)
        | {"phev_ruc_net_revenue"}
        | set(FED_AGGREGATE_SERIES)
        | set(RUC_AGGREGATE_SERIES)
        | set(TOTAL_AGGREGATE_SERIES)
    )
    touched = eligible & series_id.isin(touched_series) & june_year.ge(TRANSITION_START_FY)
    if "value_status" in data.columns:
        data.loc[touched, "value_status"] = "fed_ruc_transition"
    if "data_scope" in data.columns:
        data.loc[touched, "data_scope"] = "fed_ruc_transition_overlay"

    if new_rows:
        data = pd.concat([data, pd.DataFrame(new_rows)], ignore_index=True)
    return data, pd.DataFrame(audit_rows)


def fed_ruc_transition_marker_present(chart_rows: pd.DataFrame | None) -> bool:
    """True when chart rows carry the transition overlay's data-scope marker."""
    if chart_rows is None or chart_rows.empty or "data_scope" not in chart_rows.columns:
        return False
    return bool(
        chart_rows["data_scope"].astype(str).eq("fed_ruc_transition_overlay").any()
    )


def apply_fed_ruc_transition_to_quarterly_rows(
    quarterly_rows: pd.DataFrame,
) -> pd.DataFrame:
    """Zero displayed FED quarters from 2028Q1 on current-model traces.

    The quarterly display derives each year's quarters from the FINAL annual
    value using the rate staircase, which does not know the duty stops at
    1 Jan 2028: it would spread FY2028's surviving half-year across all four
    quarters. This re-expresses the transition at quarterly grain - post-
    transition quarters go to zero and the pre-transition quarters are
    rescaled so the fiscal-year sum is preserved exactly. State-independent:
    both leakage cases remove FED identically, so the caller only decides
    WHETHER the transition is active.
    """
    if quarterly_rows is None or quarterly_rows.empty:
        return quarterly_rows
    if "period" not in quarterly_rows.columns or "series_id" not in quarterly_rows.columns:
        return quarterly_rows
    data = quarterly_rows.copy()
    series = data["series_id"].astype(str)
    role = data.get("scenario_role", pd.Series("", index=data.index)).astype(str)
    fed_mask = series.isin(FED_REMOVED_SERIES) & ~role.isin(_EXCLUDED_SCENARIO_ROLES)
    if not fed_mask.any():
        return data

    def _serial(period: Any) -> int | None:
        try:
            return quarter_serial(period)
        except Exception:
            return None

    serials = data["period"].map(_serial)
    post = fed_mask & serials.notna() & (serials >= _START_SERIAL)
    if not post.any():
        return data
    value = pd.to_numeric(data["value"], errors="coerce")
    june_year = pd.to_numeric(data.get("june_year"), errors="coerce")
    scenario = data.get("scenario_name", pd.Series("", index=data.index)).astype(str)

    # Rescale the transition year's surviving quarters so the FY sum holds.
    start_fy_mask = fed_mask & june_year.eq(TRANSITION_START_FY)
    for (scen, sid), group in data[start_fy_mask].groupby([scenario, series]):
        idx = group.index
        pre_idx = idx[~post.loc[idx]]
        post_idx = idx[post.loc[idx]]
        if not len(post_idx):
            continue
        year_total = value.loc[idx].sum()
        pre_total = value.loc[pre_idx].sum()
        if len(pre_idx) and pre_total and np.isfinite(pre_total) and pre_total != 0:
            data.loc[pre_idx, "value"] = value.loc[pre_idx] * (year_total / pre_total)
    data.loc[post, "value"] = 0.0
    if "value_status" in data.columns:
        data.loc[post, "value_status"] = "fed_ruc_transition"
    if "data_scope" in data.columns:
        data.loc[post, "data_scope"] = "fed_ruc_transition_overlay"
    return data


def _drift_intensity_lookup(drift: pd.DataFrame | None) -> dict[tuple[str, int], float]:
    """(scenario, FY) -> petrol litres per 100 km, for the non-road FED audit."""
    if drift is None or drift.empty or "lambda_mode" not in drift.columns:
        return {}
    rows = drift[drift["lambda_mode"].astype(str).eq("optimized")]
    lookup: dict[tuple[str, int], float] = {}
    for record in rows.itertuples():
        fy = pd.to_numeric(pd.Series([record.FY]), errors="coerce").iloc[0]
        intensity = float(getattr(record, "ped_litres_per_100km", float("nan")))
        if pd.isna(fy) or not np.isfinite(intensity) or intensity <= 0:
            continue
        lookup[(str(record.scenario_name), int(fy))] = intensity
    return lookup

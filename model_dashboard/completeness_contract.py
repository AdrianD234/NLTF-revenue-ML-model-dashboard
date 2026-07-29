"""One canonical completeness engine, replacing scattered ad-hoc checks.

Before P1.1 a missing required row could disappear three different ways: a
bare ``continue`` in the annual spine, a silently retained previous value, or a
``drop_duplicates(keep="first")`` that turned an ambiguous duplicate into an
arbitrary winner. None of them left a record, so "the row is not there" and
"the row was never required" looked identical downstream.

This module evaluates every (scenario, role, stage, grain, period, series) cell
against the governed horizon rules and returns a status from a closed
vocabulary. Nothing here guesses: a required cell that cannot be produced
raises ``CompletenessContractError`` carrying enough context to act on.

The horizon rules are the merged P0 contract and are not re-litigated:

  current Light RUC-dependent  quarterly through 2030Q4/H20; FY2030 the last
                               complete annual; FY2031+ withheld
  official comparator          source-backed through its own FY2055 horizon
  raw audit                    may exceed H20, always decision_facing=false,
                               and can never satisfy a decision-facing need
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .light_fleet_allocation import (
    EXTENDED_EVIDENCE_MAX_HORIZON,
    LAST_DECISION_GRADE_ANNUAL_FY,
    quarter_horizon,
)
from .unit_contract import (
    SERIES_CANONICAL_UNITS,
    UnitContractError,
    canonical_unit_for,
)

__all__ = [
    "AVAILABILITY_STATUSES",
    "CompletenessContractError",
    "CompletenessRecord",
    "completeness_matrix",
    "evaluate_cell",
]

# Closed status vocabulary. Anything outside this set is a programming error.
AVAILABLE = "required_and_available"
OPTIONAL_AVAILABLE = "optional_and_available"
WITHHELD_H21 = "intentionally_unavailable_h21_plus"
NOT_APPLICABLE = "not_applicable"
MISSING_SOURCE_INPUT = "missing_source_input"
MISSING_DERIVED_OUTPUT = "missing_derived_output"
DUPLICATE = "duplicate_or_ambiguous"
NON_NUMERIC = "non_numeric"
NON_FINITE = "non_finite"
UNIT_INVALID = "unit_invalid"
FORMULA_INVALID = "formula_invalid"

AVAILABILITY_STATUSES = (
    AVAILABLE,
    OPTIONAL_AVAILABLE,
    WITHHELD_H21,
    NOT_APPLICABLE,
    MISSING_SOURCE_INPUT,
    MISSING_DERIVED_OUTPUT,
    DUPLICATE,
    NON_NUMERIC,
    NON_FINITE,
    UNIT_INVALID,
    FORMULA_INVALID,
)
_FAILURE_STATUSES = frozenset(
    {
        MISSING_SOURCE_INPUT,
        MISSING_DERIVED_OUTPUT,
        DUPLICATE,
        NON_NUMERIC,
        NON_FINITE,
        UNIT_INVALID,
        FORMULA_INVALID,
    }
)

# Series whose availability depends on the Light RUC horizon rule.
LIGHT_RUC_DEPENDENT = frozenset(
    {
        "light_ruc_net_km",
        "light_ruc_net_revenue",
        "light_bev_ruc_net_km",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_km",
        "phev_ruc_net_revenue",
        "current_light_ruc_conventional_modelled_km",
        "gross_ruc_revenue",
        "ruc_revenue_net_admin",
        "total_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
        "total_gross_revenue",
        "total_revenue_net_admin",
        "total_nltf_net_revenue",
    }
)
CURRENT_ROLES = frozenset({"basecase", "comparison"})
OFFICIAL_ROLE = "official_comparator"


class CompletenessContractError(ValueError):
    """A required cell could not be produced. Carries actionable context."""

    def __init__(self, record: "CompletenessRecord"):
        self.record = record
        super().__init__(
            f"{record.status}: scenario={record.scenario!r} role={record.role!r} "
            f"stage={record.stage!r} series={record.series!r} period={record.period!r} "
            f"expected_unit={record.expected_unit!r} actual_unit={record.actual_unit!r} "
            f"horizon_state={record.horizon_state!r} reason={record.reason!r} "
            f"source={record.source!r}"
        )


@dataclass(frozen=True)
class CompletenessRecord:
    scenario: str
    role: str
    stage: str
    time_grain: str
    period: str
    series: str
    horizon_state: str
    status: str
    decision_facing: bool
    expected_unit: str = ""
    actual_unit: str = ""
    reason: str = ""
    source: str = ""
    dependants: str = ""

    @property
    def is_failure(self) -> bool:
        return self.status in _FAILURE_STATUSES


def _horizon_state(time_grain: str, period: str, series: str, role: str) -> str:
    """Where this cell sits relative to the governed horizons."""
    if role == OFFICIAL_ROLE:
        return "official_source_horizon"
    if str(time_grain) == "quarterly":
        try:
            horizon = quarter_horizon(str(period))
        except (ValueError, IndexError, TypeError):
            return "unparseable_period"
        return "within_h20" if horizon <= EXTENDED_EVIDENCE_MAX_HORIZON else "beyond_h20"
    fy = pd.to_numeric(pd.Series([str(period).replace("FY", "")]), errors="coerce").iloc[0]
    if pd.isna(fy):
        return "unparseable_period"
    if str(series) in LIGHT_RUC_DEPENDENT:
        return "within_annual_cutoff" if int(fy) <= LAST_DECISION_GRADE_ANNUAL_FY else "beyond_annual_cutoff"
    return "within_annual_cutoff" if int(fy) <= LAST_DECISION_GRADE_ANNUAL_FY else "beyond_annual_cutoff"


def evaluate_cell(
    *,
    scenario: str,
    role: str,
    stage: str,
    time_grain: str,
    period: str,
    series: str,
    values: pd.Series | None,
    units: pd.Series | None = None,
    decision_facing: bool = True,
    source: str = "",
    raise_on_failure: bool = False,
) -> CompletenessRecord:
    """Classify one cell. ``values`` holds every row matching the key."""
    horizon_state = _horizon_state(time_grain, period, series, role)
    expected_unit = SERIES_CANONICAL_UNITS.get(str(series), "")

    def record(status: str, *, reason: str = "", actual_unit: str = "") -> CompletenessRecord:
        item = CompletenessRecord(
            scenario=str(scenario),
            role=str(role),
            stage=str(stage),
            time_grain=str(time_grain),
            period=str(period),
            series=str(series),
            horizon_state=horizon_state,
            status=status,
            decision_facing=bool(decision_facing),
            expected_unit=expected_unit,
            actual_unit=actual_unit,
            reason=reason,
            source=str(source),
            dependants="light_ruc_dependent_totals" if str(series) in LIGHT_RUC_DEPENDENT else "",
        )
        if raise_on_failure and item.is_failure:
            raise CompletenessContractError(item)
        return item

    # Raw audit evidence is never decision-facing and never satisfies a need.
    if not decision_facing:
        empty = values is None or len(values) == 0
        return record(NOT_APPLICABLE if empty else OPTIONAL_AVAILABLE, reason="raw_audit_layer")

    # H21+ / beyond-cutoff cells are withheld by policy, not missing.
    if horizon_state in {"beyond_h20", "beyond_annual_cutoff"} and role in CURRENT_ROLES:
        if str(series) in LIGHT_RUC_DEPENDENT or horizon_state == "beyond_h20":
            if values is not None and len(values):
                return record(
                    FORMULA_INVALID,
                    reason="a decision-facing value exists beyond the governed horizon",
                )
            return record(WITHHELD_H21, reason="withheld by the governed H20/FY2030 rule")

    if values is None or len(values) == 0:
        return record(MISSING_DERIVED_OUTPUT, reason="no row produced for a required cell")
    if len(values) > 1:
        distinct = pd.to_numeric(values, errors="coerce").dropna().round(9).unique()
        if len(distinct) > 1:
            return record(
                DUPLICATE,
                reason=f"{len(values)} rows with {len(distinct)} distinct values; first-match would be arbitrary",
            )

    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        return record(NON_NUMERIC, reason="value is not numeric")
    if not np.isfinite(numeric.to_numpy()).all():
        return record(NON_FINITE, reason="value is NaN or infinite")

    if units is not None and len(units):
        declared = str(units.iloc[0])
        try:
            canonical = canonical_unit_for(declared, context=f"{series} {period}")
        except UnitContractError as exc:
            return record(UNIT_INVALID, reason=str(exc), actual_unit=declared)
        if expected_unit and canonical != expected_unit:
            return record(
                UNIT_INVALID,
                reason=f"declared {canonical!r} but the series contract requires {expected_unit!r}",
                actual_unit=canonical,
            )
        return record(AVAILABLE, actual_unit=canonical)
    return record(AVAILABLE)


def role_series_inventory(frame: pd.DataFrame) -> dict[str, set[str]]:
    """Which series each ROLE actually carries in a frame.

    Applicability is role-dependent: the current model publishes a
    conventional-anchor series the official comparator has no analogue for, and
    the official side carries light-petrol VKT only in the line reconciliation.
    Requiring every series of every role would report those as missing, which
    is a category error, not a data gap.
    """
    if frame is None or frame.empty:
        return {}
    inventory: dict[str, set[str]] = {}
    for role, group in frame.groupby(frame["scenario_role"].astype(str)):
        inventory[str(role)] = set(group["series_id"].astype(str))
    return inventory


def completeness_matrix(
    frames: dict[str, pd.DataFrame],
    *,
    series_ids: tuple[str, ...],
    scenarios: dict[str, str],
    fys: tuple[int, ...],
    role_inventory: dict[str, set[str]] | None = None,
    raise_on_failure: bool = False,
) -> pd.DataFrame:
    """Evaluate every (scenario, stage, FY, series) annual cell.

    ``frames`` maps a stage label (S0..S4) to that stage's chart rows;
    ``scenarios`` maps scenario_name -> role.
    """
    records: list[CompletenessRecord] = []
    for stage, rows in frames.items():
        if rows is None or rows.empty:
            continue
        annual = rows[rows["time_grain"].astype(str).eq("june_year")]
        for scenario, role in scenarios.items():
            scoped = annual[annual["scenario_role"].astype(str).eq(role)]
            if role in CURRENT_ROLES and "scenario_name" in scoped.columns:
                by_name = scoped[scoped["scenario_name"].astype(str).eq(scenario)]
                if not by_name.empty:
                    scoped = by_name
            for fy in fys:
                at_fy = scoped[pd.to_numeric(scoped["june_year"], errors="coerce").eq(fy)]
                applicable = role_inventory.get(role) if role_inventory else None
                for series in series_ids:
                    if applicable is not None and series not in applicable:
                        records.append(
                            CompletenessRecord(
                                scenario=scenario, role=role, stage=stage,
                                time_grain="june_year", period=f"FY{fy}", series=series,
                                horizon_state=_horizon_state("june_year", f"FY{fy}", series, role),
                                status=NOT_APPLICABLE, decision_facing=True,
                                expected_unit=SERIES_CANONICAL_UNITS.get(series, ""),
                                reason=f"series is not part of the {role} inventory",
                                source=f"{stage} chart rows",
                            )
                        )
                        continue
                    matched = at_fy[at_fy["series_id"].astype(str).eq(series)]
                    records.append(
                        evaluate_cell(
                            scenario=scenario,
                            role=role,
                            stage=stage,
                            time_grain="june_year",
                            period=f"FY{fy}",
                            series=series,
                            values=matched["value"] if len(matched) else None,
                            units=matched["value_unit"] if "value_unit" in matched.columns and len(matched) else None,
                            source=f"{stage} chart rows",
                            raise_on_failure=raise_on_failure,
                        )
                    )
    return pd.DataFrame([record.__dict__ for record in records])

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

Three rules are stricter than the first P1.1 revision, each closing a way a
bad row could still pass:

*Units are mandatory, not merely valid.* Validation used to run only when a
unit was present, so an absent declaration fell through to AVAILABLE. That
inverts the point of a unit contract: supplying no unit was safer than
supplying a wrong one. A required cell without a declaration now fails as
``missing_unit_declaration``.

*Every duplicate canonical key fails.* Identical duplicates used to be treated
as idempotent. They are not safe: downstream code can sum a row twice, take an
arbitrary first match, or diverge later when one copy's non-key fields change,
and an exact duplicate is usually the visible symptom of a join or
materialisation defect. Cardinality for a required cell is exactly one.

*The expected inventory is governed, never observed.* See
``series_inventory_contract``: an inventory derived from the frame under test
cannot detect a series that has vanished entirely.

The horizon rules are the merged P0 contract and are not re-litigated:

  current Light RUC-dependent  quarterly through 2030Q4/H20; FY2030 the last
                               complete annual; FY2031+ withheld
  official comparator          source-backed through its own FY2055 horizon
  raw audit                    may exceed H20, always decision_facing=false,
                               and can never satisfy a decision-facing need
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .light_fleet_allocation import (
    EXTENDED_EVIDENCE_MAX_HORIZON,
    LAST_DECISION_GRADE_ANNUAL_FY,
    quarter_horizon,
)
from .series_inventory_contract import (
    GOVERNED_STAGES,
    REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN,
    required_periods,
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
    "validate_frame_completeness",
]

# Closed status vocabulary. Anything outside this set is a programming error.
AVAILABLE = "required_and_available"
OPTIONAL_AVAILABLE = "optional_and_available"
WITHHELD_H21 = "intentionally_unavailable_h21_plus"
NOT_APPLICABLE = "not_applicable"
MISSING_SOURCE_INPUT = "missing_source_input"
MISSING_DERIVED_OUTPUT = "missing_derived_output"
MISSING_REQUIRED_SERIES = "missing_required_series"
DUPLICATE = "duplicate_or_ambiguous"
NON_NUMERIC = "non_numeric"
NON_FINITE = "non_finite"
UNIT_INVALID = "unit_invalid"
MISSING_UNIT = "missing_unit_declaration"
FORMULA_INVALID = "formula_invalid"

AVAILABILITY_STATUSES = (
    AVAILABLE,
    OPTIONAL_AVAILABLE,
    WITHHELD_H21,
    NOT_APPLICABLE,
    MISSING_SOURCE_INPUT,
    MISSING_DERIVED_OUTPUT,
    MISSING_REQUIRED_SERIES,
    DUPLICATE,
    NON_NUMERIC,
    NON_FINITE,
    UNIT_INVALID,
    MISSING_UNIT,
    FORMULA_INVALID,
)
_FAILURE_STATUSES = frozenset(
    {
        MISSING_SOURCE_INPUT,
        MISSING_DERIVED_OUTPUT,
        MISSING_REQUIRED_SERIES,
        DUPLICATE,
        NON_NUMERIC,
        NON_FINITE,
        UNIT_INVALID,
        MISSING_UNIT,
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
    observed_count: int = 0
    unit_status: str = ""
    value_status: str = ""
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
    return "within_annual_cutoff" if int(fy) <= LAST_DECISION_GRADE_ANNUAL_FY else "beyond_annual_cutoff"


def _declared_unit(units: pd.Series | None) -> str:
    """The declaration, or '' when absent, blank or a null placeholder."""
    if units is None or len(units) == 0:
        return ""
    raw = units.iloc[0]
    if raw is None:
        return ""
    if isinstance(raw, float) and np.isnan(raw):
        return ""
    text = str(raw).strip()
    return "" if text.lower() in {"", "nan", "none", "null"} else text


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
    expected_unit: str | None = None,
    source: str = "",
    raise_on_failure: bool = False,
) -> CompletenessRecord:
    """Classify one cell. ``values`` holds every row matching the key.

    ``expected_unit`` overrides the per-series default, because the canonical
    unit is grain-specific: the km streams publish ``net km`` quarterly and
    ``million km`` annually.
    """
    horizon_state = _horizon_state(time_grain, period, series, role)
    contract_unit = expected_unit if expected_unit is not None else SERIES_CANONICAL_UNITS.get(str(series), "")
    observed = 0 if values is None else len(values)

    def record(
        status: str,
        *,
        reason: str = "",
        actual_unit: str = "",
        unit_status: str = "",
        value_status: str = "",
    ) -> CompletenessRecord:
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
            expected_unit=contract_unit,
            actual_unit=actual_unit,
            observed_count=observed,
            unit_status=unit_status,
            value_status=value_status,
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
                    value_status="present_beyond_horizon",
                )
            return record(WITHHELD_H21, reason="withheld by the governed H20/FY2030 rule")

    if values is None or len(values) == 0:
        return record(
            MISSING_DERIVED_OUTPUT,
            reason="no row produced for a required cell",
            value_status="absent",
        )

    # Cardinality for a required canonical key is exactly one. An identical
    # duplicate is not idempotent: downstream code may sum it twice or select
    # arbitrarily, and it usually signals a join or materialisation defect.
    if observed > 1:
        distinct = pd.to_numeric(values, errors="coerce").dropna().round(9).unique()
        detail = (
            f"{observed} rows with {len(distinct)} distinct values; first-match would be arbitrary"
            if len(distinct) > 1
            else f"{observed} rows with an identical value; cardinality for a required key must be exactly one"
        )
        return record(DUPLICATE, reason=detail, value_status="duplicate_key")

    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        return record(NON_NUMERIC, reason="value is not numeric", value_status="non_numeric")
    if not np.isfinite(numeric.to_numpy()).all():
        return record(NON_FINITE, reason="value is NaN or infinite", value_status="non_finite")

    # A required row must DECLARE a unit. Absence is a failure in its own
    # right, not a reason to skip unit validation.
    declared = _declared_unit(units)
    if not declared:
        return record(
            MISSING_UNIT,
            reason="required row carries no unit declaration; units are mandatory, not optional",
            unit_status="absent",
            value_status="numeric",
        )
    try:
        canonical = canonical_unit_for(declared, context=f"{series} {period}")
    except UnitContractError as exc:
        return record(
            UNIT_INVALID, reason=str(exc), actual_unit=declared,
            unit_status="unknown", value_status="numeric",
        )
    if contract_unit and canonical != contract_unit:
        return record(
            UNIT_INVALID,
            reason=f"declared {canonical!r} but the contract requires {contract_unit!r} at this grain",
            actual_unit=canonical,
            unit_status="incompatible",
            value_status="numeric",
        )
    return record(AVAILABLE, actual_unit=canonical, unit_status="valid", value_status="numeric")


# ------------------------------------------------------------------ matrices
def _scenario_names(frame: pd.DataFrame) -> np.ndarray | None:
    """The scenario discriminator, when the frame carries one.

    ``scenario_name`` is part of the canonical key, not decoration. One role
    can carry several scenarios at once - the S4 runtime frame publishes
    ``current_comparison_1`` alongside three conflict scenarios, all with
    ``scenario_role == "comparison"``. Keying on role alone collapses them and
    reports four legitimate scenarios as a duplicate key.
    """
    if frame is None or frame.empty or "scenario_name" not in frame.columns:
        return None
    return frame["scenario_name"].astype(str).to_numpy()


def _cell_index(frame: pd.DataFrame) -> dict[tuple[str, str, str, str, str], list[int]]:
    """One O(n) pass: (scenario, role, grain, series, period) -> row positions."""
    index: dict[tuple[str, str, str, str, str], list[int]] = {}
    if frame is None or frame.empty:
        return index
    roles = frame["scenario_role"].astype(str).to_numpy()
    grains = frame["time_grain"].astype(str).to_numpy()
    series = frame["series_id"].astype(str).to_numpy()
    periods = frame["period"].astype(str).to_numpy()
    names = _scenario_names(frame)
    for position in range(len(frame)):
        scenario = names[position] if names is not None else roles[position]
        key = (scenario, roles[position], grains[position], series[position], periods[position])
        index.setdefault(key, []).append(position)
    return index


def _series_present(frame: pd.DataFrame, scenario: str, role: str, grain: str) -> set[str]:
    if frame is None or frame.empty:
        return set()
    matches = frame["scenario_role"].astype(str).eq(role) & frame["time_grain"].astype(str).eq(grain)
    if "scenario_name" in frame.columns:
        by_name = matches & frame["scenario_name"].astype(str).eq(scenario)
        # Fall back to the role when the frame does not use this scenario name,
        # so a frame with a single unnamed scenario still evaluates.
        if by_name.any():
            matches = by_name
    return set(frame[matches]["series_id"].astype(str))


def _evaluate_against_contract(
    frame: pd.DataFrame,
    *,
    stage: str,
    scenario_by_role: dict[str, str],
    raise_on_failure: bool,
    source: str,
) -> list[CompletenessRecord]:
    """Evaluate one frame against the governed inventory for ``stage``."""
    records: list[CompletenessRecord] = []
    index = _cell_index(frame)
    has_frame = frame is not None and not frame.empty
    values = frame["value"].to_numpy() if has_frame and "value" in frame.columns else None
    units = frame["value_unit"].to_numpy() if has_frame and "value_unit" in frame.columns else None

    for (contract_stage, role, grain), items in sorted(REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN.items()):
        if contract_stage != stage:
            continue
        scenario = scenario_by_role.get(role, role)
        present = _series_present(frame, scenario, role, grain)
        periods = required_periods(role, grain)
        for item in items:
            if not item.is_required:
                records.append(
                    CompletenessRecord(
                        scenario=scenario, role=role, stage=stage, time_grain=grain,
                        period="", series=item.series_id,
                        horizon_state=item.horizon_rule, status=NOT_APPLICABLE,
                        decision_facing=True, expected_unit=item.canonical_unit,
                        reason=item.dependants or f"{item.requirement} by the governed contract",
                        source=source, dependants=item.dependants,
                    )
                )
                continue
            # A series absent in its entirety is the failure an observed
            # inventory could never see: it would simply stop being expected.
            if periods and item.series_id not in present:
                entry = CompletenessRecord(
                    scenario=scenario, role=role, stage=stage, time_grain=grain,
                    period=f"{periods[0]}..{periods[-1]}", series=item.series_id,
                    horizon_state=item.horizon_rule, status=MISSING_REQUIRED_SERIES,
                    decision_facing=True, expected_unit=item.canonical_unit,
                    observed_count=0, value_status="series_absent",
                    reason=(
                        f"the governed contract requires {item.series_id!r} for role {role!r} at "
                        f"grain {grain!r} over {len(periods)} periods; the frame contains none"
                    ),
                    source=source, dependants=item.dependants,
                )
                if raise_on_failure:
                    raise CompletenessContractError(entry)
                records.append(entry)
                continue
            for period in periods:
                positions = index.get((scenario, role, grain, item.series_id, period), [])
                if not positions and "scenario_name" not in getattr(frame, "columns", []):
                    positions = index.get((role, role, grain, item.series_id, period), [])
                matched_values = (
                    pd.Series([values[position] for position in positions])
                    if positions and values is not None
                    else None
                )
                matched_units = (
                    pd.Series([units[position] for position in positions])
                    if positions and units is not None
                    else None
                )
                records.append(
                    evaluate_cell(
                        scenario=scenario, role=role, stage=stage, time_grain=grain,
                        period=period, series=item.series_id,
                        values=matched_values, units=matched_units,
                        expected_unit=item.canonical_unit,
                        source=source, raise_on_failure=raise_on_failure,
                    )
                )
    return records


def completeness_matrix(
    frames: dict[str, pd.DataFrame],
    *,
    scenario_by_role: dict[str, str] | None = None,
    raise_on_failure: bool = False,
) -> pd.DataFrame:
    """Evaluate every governed cell, quarterly and annual, for every stage.

    ``frames`` maps a stage label to that stage's chart rows. The expected set
    comes from ``series_inventory_contract``, never from ``frames``.
    """
    roles = scenario_by_role or {
        "basecase": "current_basecase",
        "comparison": "current_comparison_1",
        "official_comparator": "mbu26_official",
    }
    records: list[CompletenessRecord] = []
    for stage, rows in frames.items():
        if stage not in GOVERNED_STAGES:
            raise ValueError(f"stage {stage!r} is not in the governed contract {GOVERNED_STAGES}")
        records.extend(
            _evaluate_against_contract(
                rows, stage=stage, scenario_by_role=roles,
                raise_on_failure=raise_on_failure, source=f"{stage} chart rows",
            )
        )
    return pd.DataFrame([record.__dict__ for record in records])


def validate_frame_completeness(
    chart_rows: pd.DataFrame,
    *,
    stage: str = "production",
    context: str = "",
    raise_on_failure: bool = True,
) -> pd.DataFrame:
    """Blocking production gate over one promoted chart-rows frame.

    Called at pack build and at pack load so a malformed required frame cannot
    reach the dashboard merely because the standalone evidence generator was
    not run. Raises ``CompletenessContractError`` on the first failure.
    """
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame()
    needed = {"scenario_role", "time_grain", "series_id", "period", "value"}
    if not needed.issubset(set(chart_rows.columns)):
        return pd.DataFrame()
    records = _evaluate_against_contract(
        chart_rows,
        stage=stage,
        scenario_by_role={
            "basecase": "current_basecase",
            "comparison": "current_comparison_1",
            "official_comparator": "mbu26_official",
        },
        raise_on_failure=raise_on_failure,
        source=context or "production chart rows",
    )
    return pd.DataFrame([record.__dict__ for record in records])

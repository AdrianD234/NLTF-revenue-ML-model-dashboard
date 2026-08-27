"""Source-backed Middle East conflict fuel-price paths for Revenue Outlook.

Low, Medium and High paths clone the governed Base-population
``scenario_input_wide`` rows and apply the committed nominal petrol and diesel
price ratios to the matching real model inputs.  Petrol affects PED only;
diesel affects Light and Heavy RUC activity.  The conflict path never changes a
RUC tax-price input.  Each conflict path and Base are replayed under published,
six-month-delayed and no-uplift FED/RUC policy timing.

Because the fitted finalists are not uniformly monotonic under every compound
shock, every non-Base quarter is structurally anchored to the matching Base
quarter. PED uses the full pump-price ratio. Light and Heavy RUC use one
diesel-plus-RUC running-cost ratio at explicit class fuel intensities and apply
the governed medium retail-diesel elasticity once. Each structural response
replaces the raw fitted value rather than stacking an additional multiplier.
Annual policy bridges apply the selected schedule to nominal PED and RUC
revenue rates before replaying the governed aggregate formulas with
administration and refunds held fixed.

This module does not mutate the committed Revenue Outlook pack.  It is a
runtime scenario layer, and its audit frames retain both the displayed values
and the published FED-path baseline when a FED policy overlay is active.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ev_uptake_levers import FED_AGGREGATE_SERIES, RUC_AGGREGATE_SERIES, TOTAL_AGGREGATE_SERIES
from .conflict_fuel_paths import (
    BASE_POLICY_VARIANT_IDS,
    BASE_SCENARIO_ID,
    CONFLICT_FUEL_SCENARIO_LEVELS,
    CONFLICT_FUEL_SCENARIO_SPECS,
    conflict_policy_variant_name,
    conflict_scenario_name,
    conflict_scenario_note,
    conflict_trace_name,
    load_conflict_fuel_price_paths,
    structural_overlay_scenario_ids,
)
from .conflict_gdp_paths import (
    apply_conflict_gdp_impact,
    apply_conflict_unemployment_impact,
    build_conflict_gdp_paths,
    build_conflict_unemployment_paths,
    conflict_gdp_input_audit,
)
from .forecast_runner import (
    ScenarioInputForecastReplayResult,
    forecast_chart_rows_for_display,
    replay_forecast_from_scenario_inputs,
)
from .unit_contract import display_scale_for
from .mbu26_source_spine import (
    FORMULA_DEFINITIONS,
    current_forecast_annual_from_mbu26,
)
from .fed_policy_states import (
    FED_POLICY_SPECS,
    FED_UPLIFT_START_PERIOD,
    PolicyStateError,
    finite_deferral_specs,
    policy_spec,
    quarter_serial,
)
from .rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    fed_policy_annual_factors,
    fed_uplift_delayed_factors,
    fed_uplift_off_factors,
    ped_quarterly_rate_schedules,
)
from .treasury_macro_paths import (
    apply_treasury_baseline_macro_path,
    apply_treasury_macro_path_to_scenarios,
)


# Backwards-compatible exports point to Medium while app/revenue-outlook
# callers migrate from one runtime trace to the three-scenario registry.
FUEL_PRICE_SCENARIO_NAME = conflict_scenario_name("medium")
FUEL_PRICE_SCENARIO_TRACE_NAME = conflict_trace_name("medium")
FUEL_PRICE_SCENARIO_NOTE = conflict_scenario_note("medium")
IRAN_WAR_SCENARIO_NAME = FUEL_PRICE_SCENARIO_NAME
IRAN_WAR_SCENARIO_TRACE_NAME = FUEL_PRICE_SCENARIO_TRACE_NAME
IRAN_WAR_SCENARIO_NOTE = FUEL_PRICE_SCENARIO_NOTE

# The published paths above remain the backwards-compatible scenario IDs.
# Policy variants are separate replay rows because changing the RUC price
# input affects activity as well as the nominal revenue rate applied later.
# One spec per non-published governed state, in registry display order: the
# six finite deferrals, no-uplift, then the four bespoke rate paths.
_NON_PUBLISHED_POLICY_SPECS = tuple(
    spec for spec in FED_POLICY_SPECS if not spec.is_published
)
BASE_DELAYED_6M_SCENARIO_NAME = BASE_POLICY_VARIANT_IDS["delay_6m"]
BASE_NO_UPLIFT_SCENARIO_NAME = BASE_POLICY_VARIANT_IDS["no_uplift"]
IRAN_WAR_DELAYED_6M_SCENARIO_NAME = conflict_policy_variant_name(
    "medium", FED_POLICY_STATE_DELAYED_6M
)
IRAN_WAR_NO_UPLIFT_SCENARIO_NAME = conflict_policy_variant_name(
    "medium", FED_POLICY_STATE_NO_UPLIFT
)

POLICY_VARIANT_SCENARIO_NAMES = {
    spec.calculation_state_id: {
        "baseline": BASE_POLICY_VARIANT_IDS[spec.calculation_state_id],
        **{
            level: conflict_policy_variant_name(level, spec.calculation_state_id)
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
        },
        "iran": conflict_policy_variant_name("medium", spec.calculation_state_id),
    }
    for spec in _NON_PUBLISHED_POLICY_SPECS
}

# Deprecated numeric constants retained for import compatibility only. Runtime
# conflict inputs are always driven by ``load_conflict_fuel_price_paths``.
FUEL_PRICE_MULTIPLIER = 1.15
RUC_PRICE_MULTIPLIER = 1.0
FUEL_PRICE_SHOCK_PERIODS = (
    "2026Q1",
    "2026Q2",
    "2026Q3",
    "2026Q4",
    "2027Q1",
    "2027Q2",
)
RUC_PRICE_SHOCK_PERIODS: tuple[str, ...] = ()
RUC_PRICE_LAGGED_EFFECT_PERIODS: tuple[str, ...] = ()

BASE_PUBLISHED_SCENARIO_NAME = BASE_SCENARIO_ID
_BASE_SCENARIO_NAME = BASE_PUBLISHED_SCENARIO_NAME
_LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME = (
    "__legacy_current_basecase_macro_shadow"
)
# scenario_name -> public path id. Registry-driven: the finite deferrals use
# the shifted_{m}m suffix family (shifted_6m retains its historic id) and
# no-uplift keeps no_uplift, for the baseline and each conflict family.
POLICY_PATH_IDS: dict[str, str] = {
    _BASE_SCENARIO_NAME: "baseline_published",
    **{
        BASE_POLICY_VARIANT_IDS[_spec.calculation_state_id]: f"baseline_{_spec.path_suffix}"
        for _spec in _NON_PUBLISHED_POLICY_SPECS
    },
}
for _level in CONFLICT_FUEL_SCENARIO_LEVELS:
    POLICY_PATH_IDS[conflict_scenario_name(_level)] = f"{_level}_published"
    for _spec in _NON_PUBLISHED_POLICY_SPECS:
        POLICY_PATH_IDS[
            conflict_policy_variant_name(_level, _spec.calculation_state_id)
        ] = f"{_level}_{_spec.path_suffix}"
_STREAM_PRICE_FIELDS = {
    "PED": "real_petrol_price_cents_per_litre",
    "LIGHT_RUC": "real_diesel_price_cents_per_litre",
    "HEAVY_RUC": "real_diesel_price_cents_per_litre",
}
_STREAM_RUC_PRICE_FIELDS = {
    "LIGHT_RUC": ("real_light_ruc_price_nzd_per_1000km",),
    "HEAVY_RUC": (
        "real_light_ruc_price_nzd_per_1000km",
        "real_heavy_ruc_price_nzd_per_1000km",
    ),
}
_POLICY_GENERALIZED_PRICE_FIELDS = {
    "PED": "real_petrol_price_cents_per_litre",
    "LIGHT_RUC": "real_light_ruc_price_nzd_per_1000km",
    "HEAVY_RUC": "real_heavy_ruc_price_nzd_per_1000km",
}
_POLICY_REFERENCE_SCENARIOS: dict[str, str] = {
    BASE_POLICY_VARIANT_IDS[_spec.calculation_state_id]: _BASE_SCENARIO_NAME
    for _spec in _NON_PUBLISHED_POLICY_SPECS
}
for _level in CONFLICT_FUEL_SCENARIO_LEVELS:
    for _spec in _NON_PUBLISHED_POLICY_SPECS:
        _POLICY_REFERENCE_SCENARIOS[
            conflict_policy_variant_name(_level, _spec.calculation_state_id)
        ] = conflict_scenario_name(_level)
_POLICY_DEMAND_ELASTICITY_LEVEL = "Med"
_POLICY_CALIBRATION_BASIS = "governed_single_generalized_running_cost_elasticity"
_CONFLICT_CALIBRATION_BASIS = _POLICY_CALIBRATION_BASIS
_POLICY_CALIBRATION_NOTE = (
    "PED uses the retail pump-price ratio. Light and Heavy RUC use one combined "
    "diesel-plus-RUC cost per 1,000 km ratio against Base, then apply the governed "
    "retail-diesel demand elasticity once. RUC-only ratios are never raised to the "
    "diesel elasticity independently."
)
_CONFLICT_CALIBRATION_NOTE = (
    "Conflict and policy fuel/RUC inputs are combined into one generalized-cost "
    "ratio against Base. The calibrated value replaces, rather than multiplies, "
    "the raw fixed-finalist replay."
)
# Because the structural overlay replaces the fitted point forecast, the fitted
# ensemble members no longer describe the displayed value.  The displayed value
# is decomposed instead into the exact additive identity
#     R*P*G = R + R*(P-1) + R*(G-1) + R*(P-1)*(G-1)
# where R is the Base reference forecast, P the generalized-price response and
# G the fitted GDP factor.  These four terms sum to the displayed forecast by
# construction and are the only component attribution that may be shown for a
# structural-overlay scenario.
_STRUCTURAL_COMPONENT_LABELS = (
    "STRUCTURAL_REFERENCE_BASE",
    "STRUCTURAL_PRICE_RESPONSE",
    "STRUCTURAL_GDP_RESPONSE",
    "STRUCTURAL_PRICE_GDP_INTERACTION",
)
_STRUCTURAL_COMPONENT_BASIS = "governed_structural_overlay_additive_decomposition"
_CALIBRATION_STATUS_NOT_APPLICABLE = "not_applicable"
_CALIBRATION_STATUS_PASSED = "passed"
_CALIBRATION_STATUS_FAILED = "failed"
_PREDICTIVE_STATUS_NOT_AVAILABLE = "not_available_for_counterfactual_overlay"
_PREDICTIVE_STATUS_RAW_REPLAY = "raw_fitted_replay_backtest_evidence"
_STRUCTURAL_VALIDATION_SCOPE_NOTE = (
    "Structural integrity only: formula identity, calibrated-row coverage, "
    "component closure and economic sign are checked. The counterfactual path "
    "has no observed outcome, so predictive accuracy is not established."
)
_INTERVAL_UNAVAILABLE_STRUCTURAL_OVERLAY = "unavailable_structural_overlay"
_SUPERSEDED_COMPONENT_REASON = (
    "raw_fitted_ensemble_members_superseded_by_structural_overlay; "
    "they describe the pre-overlay forecast layer and must not be displayed as "
    "attribution for the governed scenario forecast"
)
# Closure tolerances for the displayed-forecast invariants.
_STRUCTURAL_CLOSURE_RTOL = 1e-12
_STRUCTURAL_CLOSURE_ATOL = 1e-9
# Calibrated operating-cost weights. The light value is the midpoint of the
# Ministry of Transport's statement that light diesel is 20-30% more efficient
# than its 9.5 L/100 km average petrol vehicle (9.5 * 75% = 7.125). The heavy
# value is the representative large-heavy-vehicle intensity in NZTA Research
# Report 482. These are explicit calibration assumptions because the governed
# scenario pack contains diesel prices and RUC rates but no class fuel intensity.
_RUC_DIESEL_LITRES_PER_100KM = {
    "LIGHT_RUC": 7.125,
    "HEAVY_RUC": 50.0,
}
_RUC_DIESEL_INTENSITY_SOURCE = {
    "LIGHT_RUC": (
        "https://www.transport.govt.nz/about-us/queries/buying-a-light-vehicle"
        "#9.5L_petrol_and_20_to_30pct_diesel_efficiency"
    ),
    "HEAVY_RUC": (
        "https://www.nzta.govt.nz/resources/research/reports/482/docs/482.pdf"
        "#representative_large_heavy_vehicle_50L_per_100km"
    ),
}
_GENERALIZED_RUNNING_COST_FIELD = "diesel_plus_ruc_cost_nzd_per_1000km"
from .light_fleet_allocation import (
    AVAILABILITY_AVAILABLE,
    CONVENTIONAL_ANCHOR_SERIES_ID as _CURRENT_LIGHT_TOTAL_SERIES_ID,
    annual_availability,
    quarterly_availability,
)
_LIGHT_RUC_LAGGED_PRICE_FIELD = "lagged_real_light_ruc_price_nzd_per_1000km"
_HEAVY_RUC_LEAD_PRICE_FIELD = "lead_real_heavy_ruc_price_nzd_per_1000km"
_STREAM_SERIES_IDS = {
    "PED": "ped_vkt_per_capita",
    "LIGHT_RUC": "light_ruc_net_km",
    "HEAVY_RUC": "heavy_ruc_net_km",
}
_RUC_REVENUE_LEAVES = (
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_revenue",
)
_FED_POLICY_COLUMNS = (
    "_fed_baseline_value",
    "_fed_annual_delta",
    "_fed_policy",
    "_fed_affected_quarters",
)
_FUEL_AUDIT_COLUMNS = (
    "scenario_name",
    "scenario_role",
    "trace_name",
    "severity",
    "time_grain",
    "period",
    "june_year",
    "stream",
    "series_id",
    "transformation_basis",
    "factor",
    "baseline_value",
    "adjusted_value",
    "value_delta",
    "quarterly_annual_reconciliation_delta",
    "published_fed_baseline_value",
    "adjusted_published_fed_value",
    "fed_policy_delta",
    "fed_policy",
    "fed_affected_quarters",
    "scenario_note",
)


@dataclass(frozen=True)
class FuelPriceScenarioReplayResult:
    """Fixed-finalist replay plus the input and bridge lineage needed by UI rows."""

    base_scenario_name: str
    treasury_base_inputs: pd.DataFrame
    fuel_scenario_inputs: pd.DataFrame
    policy_scenario_inputs: pd.DataFrame
    replay_inputs: pd.DataFrame
    replay: ScenarioInputForecastReplayResult
    price_only_replay_inputs: pd.DataFrame
    price_only_replay: ScenarioInputForecastReplayResult
    input_audit: pd.DataFrame
    gdp_input_audit: pd.DataFrame
    baseline_macro_quarterly_factors: pd.DataFrame
    baseline_macro_annual_factors: pd.DataFrame
    quarterly_factors: pd.DataFrame
    annual_factors: pd.DataFrame
    annual_bridge: pd.DataFrame
    policy_pair_factors: pd.DataFrame

    @property
    def future_forecasts(self) -> pd.DataFrame:
        return self.replay.future_forecasts

    @property
    def assumptions(self) -> pd.DataFrame:
        return self.replay.assumptions

    @property
    def validation_report(self) -> pd.DataFrame:
        # Backwards-compatible Base-plus-Medium view.  The complete 12-path
        # validation is available via ``policy_validation_report`` (and the
        # underlying ``replay.validation_report``).
        validation = self.replay.validation_report
        if validation is None or validation.empty or "scenario_name" not in validation.columns:
            return validation
        return validation[
            validation["scenario_name"].astype(str).isin(
                [self.base_scenario_name, FUEL_PRICE_SCENARIO_NAME]
            )
        ].reset_index(drop=True)

    @property
    def policy_validation_report(self) -> pd.DataFrame:
        return self.replay.validation_report

    @property
    def structural_component_forecasts(self) -> pd.DataFrame:
        """Additive decomposition that sums exactly to the displayed forecast.

        This is the only component attribution valid for structural-overlay
        scenarios.  Fitted ensemble members for those scenarios describe the
        pre-overlay layer and are held in ``superseded_component_forecasts``.
        """

        return self.replay.structural_component_forecasts

    @property
    def superseded_component_forecasts(self) -> pd.DataFrame:
        """Fitted ensemble members that no longer describe the shown forecast."""

        return self.replay.superseded_component_forecasts

    @property
    def policy_demand_calibration_audit(self) -> pd.DataFrame:
        """Direct policy-price quarters replaced by the governed elasticity."""

        forecasts = self.replay.future_forecasts
        if (
            forecasts is None
            or forecasts.empty
            or "policy_calibration_applied" not in forecasts.columns
        ):
            return pd.DataFrame()
        applied = forecasts["policy_calibration_applied"].fillna(False).astype(bool)
        return forecasts.loc[applied].reset_index(drop=True)


@dataclass(frozen=True)
class TreasuryBaselineMacroReplayResult:
    """Independent Treasury-versus-legacy Base replay used for safe fallback."""

    base_scenario_name: str
    treasury_base_inputs: pd.DataFrame
    replay_inputs: pd.DataFrame
    replay: ScenarioInputForecastReplayResult
    baseline_macro_quarterly_factors: pd.DataFrame
    baseline_macro_annual_factors: pd.DataFrame


def _base_scenario_rows(base_inputs: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    if base_inputs is None or base_inputs.empty:
        raise ValueError("Base scenario_input_wide rows are required.")
    required = {"scenario_name", "role", "stream", "canonical_period"}
    missing = required.difference(base_inputs.columns)
    if missing:
        raise ValueError("scenario_input_wide is missing required columns: " + ", ".join(sorted(missing)))

    source = base_inputs.copy()
    role = source["role"].fillna("").astype(str).str.strip().str.casefold()
    candidates = source.loc[role.eq("basecase"), "scenario_name"].dropna().astype(str).unique().tolist()
    if not candidates and source["scenario_name"].astype(str).eq(_BASE_SCENARIO_NAME).any():
        candidates = [_BASE_SCENARIO_NAME]
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one Basecase scenario; found {len(candidates)}: {candidates}")
    scenario_name = candidates[0]
    rows = source[source["scenario_name"].astype(str).eq(scenario_name)].copy()
    if rows.empty:
        raise ValueError(f"Basecase scenario {scenario_name!r} has no rows.")
    return scenario_name, rows


def _normalise_conflict_level(level: str) -> str:
    if set(CONFLICT_FUEL_SCENARIO_SPECS) != set(CONFLICT_FUEL_SCENARIO_LEVELS):
        raise ValueError(
            "Conflict fuel-price scenario specs must define exactly the registered levels."
        )
    normalised = str(level).strip().casefold()
    if normalised not in CONFLICT_FUEL_SCENARIO_LEVELS:
        raise ValueError(
            f"Unknown conflict fuel-price severity {level!r}; expected one of "
            + ", ".join(CONFLICT_FUEL_SCENARIO_LEVELS)
            + "."
        )
    return normalised


def _conflict_path_rows(
    repo_root: Path | str,
    level: str,
    *,
    scenario_paths: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one validated severity path from the committed scenario config."""

    severity = _normalise_conflict_level(level)
    paths = (
        load_conflict_fuel_price_paths(Path(repo_root))
        if scenario_paths is None
        else scenario_paths.copy()
    )
    required = {
        "period",
        "severity",
        "base_diesel_cpl",
        "scenario_diesel_cpl",
        "diesel_ratio",
        "base_petrol_cpl",
        "scenario_petrol_cpl",
        "petrol_ratio",
        "observation_status",
        "source_note",
        "source_url",
        "source_workbook_cell",
        "source_workbook_sha256",
        "fed_12c_embedded",
    }
    missing = required.difference(paths.columns)
    if missing:
        raise ValueError(
            "Conflict fuel-price paths are missing required columns: "
            + ", ".join(sorted(missing))
        )
    paths = paths[
        paths["severity"].fillna("").astype(str).str.strip().str.casefold().eq(severity)
    ].copy()
    if paths.empty:
        raise ValueError(f"Conflict fuel-price config has no rows for severity {severity!r}.")
    paths["period"] = paths["period"].astype(str)
    if paths["period"].duplicated(keep=False).any():
        duplicates = sorted(paths.loc[paths["period"].duplicated(keep=False), "period"].unique())
        raise ValueError(
            f"Conflict fuel-price config has duplicate {severity} periods: {duplicates}"
        )
    for column in (
        "base_diesel_cpl",
        "scenario_diesel_cpl",
        "diesel_ratio",
        "base_petrol_cpl",
        "scenario_petrol_cpl",
        "petrol_ratio",
    ):
        paths[column] = pd.to_numeric(paths[column], errors="coerce")
        if paths[column].isna().any() or (~np.isfinite(paths[column])).any():
            raise ValueError(
                f"Conflict fuel-price config contains non-numeric {column!r} values "
                f"for severity {severity!r}."
            )
    if paths[["base_diesel_cpl", "scenario_diesel_cpl", "base_petrol_cpl", "scenario_petrol_cpl"]].le(0).any().any():
        raise ValueError("Conflict fuel-price levels must be finite and positive.")
    if paths[["diesel_ratio", "petrol_ratio"]].le(0).any().any():
        raise ValueError("Conflict fuel-price ratios must be finite and positive.")
    expected_diesel = paths["scenario_diesel_cpl"] / paths["base_diesel_cpl"]
    expected_petrol = paths["scenario_petrol_cpl"] / paths["base_petrol_cpl"]
    if not np.allclose(paths["diesel_ratio"], expected_diesel, rtol=1e-10, atol=1e-12):
        raise ValueError("Conflict diesel ratios do not reconcile to scenario/base price levels.")
    if not np.allclose(paths["petrol_ratio"], expected_petrol, rtol=1e-10, atol=1e-12):
        raise ValueError("Conflict petrol ratios do not reconcile to scenario/base price levels.")
    embedded = paths["fed_12c_embedded"].map(
        lambda value: str(value).strip().casefold() in {"1", "true", "yes", "y"}
        if not isinstance(value, (bool, np.bool_))
        else bool(value)
    )
    if embedded.any():
        raise ValueError(
            "Conflict fuel-price paths must exclude the 12c FED uplift; it is composed "
            "separately by the policy toggle."
        )
    paths["severity"] = severity
    return paths.sort_values("period", key=lambda values: values.map(_canonical_quarter_order), kind="stable").reset_index(drop=True)


def build_fuel_price_scenario_inputs(
    base_inputs: pd.DataFrame,
    repo_root: Path | str | None = None,
    *,
    level: str = "medium",
    scenario_paths: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Clone Base and apply one governed petrol/diesel conflict path.

    Nominal scenario/base ratios are applied to the matching real price input,
    preserving the Base deflator.  No RUC tax-price field is changed here.
    """

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    severity = _normalise_conflict_level(level)
    path = _conflict_path_rows(root, severity, scenario_paths=scenario_paths)
    _, scenario = _base_scenario_rows(base_inputs)
    scenario = scenario.copy()
    scenario["scenario_name"] = conflict_scenario_name(severity)
    scenario["role"] = "comparison"
    if "scenario_role" in scenario.columns:
        scenario["scenario_role"] = "comparison"
    scenario["scenario_display_name"] = conflict_trace_name(severity)
    scenario["conflict_fuel_severity"] = severity
    scenario["conflict_fed_12c_embedded"] = False
    if "source_artifact" in scenario.columns:
        scenario["source_artifact"] = (
            "runtime_middle_east_conflict_fuel_scenario:"
            f"{severity}:committed_price_ratio:base_clone"
        )

    period = scenario["canonical_period"].astype(str)
    stream = scenario["stream"].astype(str)
    for stream_name, field in _STREAM_PRICE_FIELDS.items():
        if field not in scenario.columns:
            raise ValueError(f"Base scenario_input_wide is missing required fuel-price field {field!r}.")
        scenario[field] = scenario[field].astype(object)
        ratio_column = "petrol_ratio" if stream_name == "PED" else "diesel_ratio"
        for path_row in path.itertuples(index=False):
            target_period = str(path_row.period)
            mask = stream.eq(stream_name) & period.eq(target_period)
            if int(mask.sum()) != 1:
                raise ValueError(
                    f"Expected one {stream_name} input row for conflict period "
                    f"{target_period!r}; found {int(mask.sum())}."
                )
            value = pd.to_numeric(scenario.loc[mask, field], errors="coerce").iloc[0]
            ratio = float(getattr(path_row, ratio_column))
            if pd.isna(value) or not np.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(
                    f"Conflict fuel path could not transform non-positive/non-numeric "
                    f"{field!r} for {stream_name}/{target_period}."
                )
            scenario.loc[mask, field] = float(value) * ratio

    return scenario.reset_index(drop=True)


def _canonical_quarter_order(period: Any) -> tuple[int, int]:
    text = str(period or "")
    try:
        year, quarter = text.split("Q", maxsplit=1)
        return int(year), int(quarter)
    except (TypeError, ValueError):
        return 0, 0


def _rebuild_light_ruc_price_lag(scenario: pd.DataFrame) -> pd.DataFrame:
    """Rebuild Light-price lags consumed by the Light and Heavy finalists."""

    if _LIGHT_RUC_LAGGED_PRICE_FIELD not in scenario.columns:
        raise ValueError(
            "Scenario inputs are missing required Light RUC lag field "
            f"{_LIGHT_RUC_LAGGED_PRICE_FIELD!r}."
        )
    current_field = "real_light_ruc_price_nzd_per_1000km"
    if current_field not in scenario.columns:
        raise ValueError(f"Scenario inputs are missing required RUC-price field {current_field!r}.")
    out = scenario.copy()
    out[_LIGHT_RUC_LAGGED_PRICE_FIELD] = out[_LIGHT_RUC_LAGGED_PRICE_FIELD].astype(object)
    for stream_name in ("LIGHT_RUC", "HEAVY_RUC"):
        rows = out[out["stream"].astype(str).eq(stream_name)].copy()
        rows["_quarter_order"] = rows["canonical_period"].map(_canonical_quarter_order)
        rows = rows.sort_values("_quarter_order", kind="stable")
        indices = list(rows.index)
        for source_index, target_index in zip(indices, indices[1:], strict=False):
            source_value = pd.to_numeric(
                pd.Series([out.at[source_index, current_field]]), errors="coerce"
            ).iloc[0]
            if pd.isna(source_value):
                source_period = str(out.at[source_index, "canonical_period"])
                raise ValueError(
                    f"{stream_name} current Light RUC price is non-numeric in {source_period}."
                )
            out.at[target_index, _LIGHT_RUC_LAGGED_PRICE_FIELD] = float(source_value)
    return out


def _rebuild_heavy_ruc_price_lead(scenario: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the Heavy finalist's explicit one-quarter Heavy-price lead."""

    current_field = "real_heavy_ruc_price_nzd_per_1000km"
    required = {current_field, _HEAVY_RUC_LEAD_PRICE_FIELD}
    missing = required.difference(scenario.columns)
    if missing:
        raise ValueError(
            "Scenario inputs are missing required Heavy RUC price fields: "
            + ", ".join(sorted(missing))
        )
    out = scenario.copy()
    out[_HEAVY_RUC_LEAD_PRICE_FIELD] = out[_HEAVY_RUC_LEAD_PRICE_FIELD].astype(object)
    heavy = out[out["stream"].astype(str).eq("HEAVY_RUC")].copy()
    heavy["_quarter_order"] = heavy["canonical_period"].map(_canonical_quarter_order)
    heavy = heavy.sort_values("_quarter_order", kind="stable")
    indices = list(heavy.index)
    for target_index, source_index in zip(indices, indices[1:], strict=False):
        source_value = pd.to_numeric(
            pd.Series([out.at[source_index, current_field]]), errors="coerce"
        ).iloc[0]
        if pd.isna(source_value):
            source_period = str(out.at[source_index, "canonical_period"])
            raise ValueError(f"Heavy RUC current price is non-numeric in {source_period}.")
        out.at[target_index, _HEAVY_RUC_LEAD_PRICE_FIELD] = float(source_value)
    return out


def _source_nominal_petrol_path(
    source_inputs: pd.DataFrame,
    repo_root: Path,
) -> dict[str, float]:
    """Return the policy-free nominal pump-price level for each input quarter.

    The committed conflict path is nominal while the finalist input is real.
    The caller first adds the published FED wedge to align this nominal proxy
    with the published-policy real source input, then applies the nominal
    target/source ratio to the real input. This preserves the deflator exactly:
    ``variant_real / base_real == variant_nominal / base_nominal``.

    The committed path ends at 2030Q4. Any later scenario-input quarter is
    extended using its governed +1 c/L quarterly base drift; all conflict
    paths have converged by that boundary.
    """

    paths = load_conflict_fuel_price_paths(repo_root)
    severity_values = (
        source_inputs.get("conflict_fuel_severity", pd.Series(dtype=object))
        .dropna()
        .astype(str)
        .str.strip()
        .str.casefold()
    )
    severity_values = severity_values[severity_values.ne("")].unique().tolist()
    if len(severity_values) > 1:
        raise ValueError(
            "A policy input scenario cannot contain multiple conflict severities."
        )
    if severity_values:
        severity = _normalise_conflict_level(severity_values[0])
        selected = _conflict_path_rows(
            repo_root,
            severity,
            scenario_paths=paths,
        )[["period", "scenario_petrol_cpl"]].rename(
            columns={"scenario_petrol_cpl": "nominal_petrol_cpl"}
        )
    else:
        base = paths[["period", "base_petrol_cpl"]].copy()
        base["base_petrol_cpl"] = pd.to_numeric(
            base["base_petrol_cpl"], errors="coerce"
        )
        spread = base.groupby("period", sort=False)["base_petrol_cpl"].agg(
            lambda values: float(values.max()) - float(values.min())
        )
        if spread.gt(1e-9).any():
            raise ValueError(
                "Conflict config has inconsistent Base nominal petrol levels "
                "across severities."
            )
        selected = (
            base.drop_duplicates("period", keep="first")
            .rename(columns={"base_petrol_cpl": "nominal_petrol_cpl"})
            .copy()
        )

    selected["period"] = selected["period"].astype(str)
    selected["nominal_petrol_cpl"] = pd.to_numeric(
        selected["nominal_petrol_cpl"], errors="coerce"
    )
    if (
        selected["nominal_petrol_cpl"].isna().any()
        or selected["nominal_petrol_cpl"].le(0.0).any()
    ):
        raise ValueError("Nominal petrol path must contain positive numeric levels.")
    selected["_quarter_order"] = selected["period"].map(_canonical_quarter_order)
    selected = selected.sort_values("_quarter_order", kind="stable")
    configured = dict(
        zip(
            selected["period"].astype(str),
            selected["nominal_petrol_cpl"].astype(float),
            strict=True,
        )
    )
    if len(selected) < 2:
        raise ValueError("Nominal petrol path requires at least two configured quarters.")
    last_two = selected.tail(2)
    drift = float(last_two["nominal_petrol_cpl"].iloc[-1]) - float(
        last_two["nominal_petrol_cpl"].iloc[-2]
    )
    if not np.isfinite(drift):
        raise ValueError("Nominal petrol path drift must be finite.")
    last_period = str(selected["period"].iloc[-1])
    last_order = _canonical_quarter_order(last_period)
    last_serial = last_order[0] * 4 + last_order[1] - 1
    last_value = float(selected["nominal_petrol_cpl"].iloc[-1])
    result: dict[str, float] = {}
    for period in source_inputs["canonical_period"].dropna().astype(str).unique():
        if period in configured:
            result[period] = configured[period]
            continue
        year, quarter = _canonical_quarter_order(period)
        serial = year * 4 + quarter - 1
        if year <= 0 or quarter <= 0 or serial <= last_serial:
            raise ValueError(
                f"Nominal petrol path has no governed level for input period {period!r}."
            )
        result[period] = last_value + drift * float(serial - last_serial)
    if any(not np.isfinite(value) or value <= 0.0 for value in result.values()):
        raise ValueError("Extended nominal petrol path must remain finite and positive.")
    return result


def build_ruc_policy_scenario_inputs(
    source_inputs: pd.DataFrame,
    repo_root: Path | str,
    *,
    policy_state: str,
    scenario_name: str,
    scenario_display_name: str | None = None,
    quarterly_policy_factors: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Clone one scenario and apply the FED policy to PED and RUC inputs.

    PED receives the nominal target/published-source pump-price ratio applied
    to its real retail-price input, preserving the implicit deflator. The
    published nominal source equals the policy-free fuel path plus the
    published FED wedge, so the numerator and denominator use the same policy
    basis. This is algebraically the future-uplift decomposition: the target
    pump price equals (published proxy - published future FED uplift) plus the
    selected state's future uplift, so the ongoing +4c/L annual escalation
    already embedded in the published proxy is never double-counted.

    GST convention (explicit, documented decision): the pump-price wedge uses
    the EX-GST FED rates (12/6/4 c/L) directly, matching the revenue
    accounting basis. A GST-inclusive behavioural wedge (x1.15: 13.8/6.9/4.6)
    would be the conceptually stricter retail-price treatment but would
    reprice every deferral state's behavioural response; adopting it is a
    governance decision, not a bug fix, and is deliberately not made here.

    RUC receives the target/published rate multiplier because its
    finalists consume real Light/Heavy RUC price levels. Light-price lags for
    both RUC streams and the Heavy-price lead are rebuilt. Passing conflict
    rows keeps the independent petrol/diesel scenario ratios intact; nominal
    revenue rates are handled later by the annual bridge.
    """

    state = str(policy_state).strip()
    if not state:
        raise ValueError("policy_state must be a non-empty audit label.")
    if source_inputs is None or source_inputs.empty:
        raise ValueError("Exactly one populated source scenario is required.")
    required = {"scenario_name", "stream", "canonical_period"}
    missing = required.difference(source_inputs.columns)
    if missing:
        raise ValueError("Scenario inputs are missing required columns: " + ", ".join(sorted(missing)))
    source_names = source_inputs["scenario_name"].dropna().astype(str).unique().tolist()
    if len(source_names) != 1:
        raise ValueError(f"Expected exactly one source scenario; found {len(source_names)}: {source_names}")

    scenario = source_inputs.copy()
    schedules = ped_quarterly_rate_schedules(Path(repo_root))
    planned = pd.to_numeric(schedules["planned"], errors="coerce")
    no_uplift = pd.to_numeric(schedules["no_uplift"], errors="coerce")
    published_petrol_wedges_cents = ((planned - no_uplift) * 100.0).to_dict()
    if quarterly_policy_factors is None:
        try:
            state_spec = policy_spec(state)
        except PolicyStateError:
            state_spec = None
        if state_spec is None or state_spec.is_published:
            known = ", ".join(
                repr(spec.calculation_state_id) for spec in _NON_PUBLISHED_POLICY_SPECS
            )
            raise ValueError(
                "A custom policy_state requires quarterly_policy_factors; known states are "
                f"{known}."
            )
        schedule_column = state_spec.schedule_column
        target = pd.to_numeric(schedules[schedule_column], errors="coerce")
        valid = planned.notna() & target.notna() & planned.gt(0)
        policy_multipliers = (target[valid] / planned[valid]).to_dict()
        petrol_price_deltas_cents = ((target[valid] - planned[valid]) * 100.0).to_dict()
    else:
        if not isinstance(quarterly_policy_factors, Mapping):
            raise TypeError("quarterly_policy_factors must be a quarter-to-factor mapping.")
        policy_multipliers: dict[str, float] = {}
        petrol_price_deltas_cents: dict[str, float] = {}
        available_periods = set(source_inputs["canonical_period"].dropna().astype(str))
        for raw_period, raw_factor in quarterly_policy_factors.items():
            quarter = str(raw_period)
            factor = pd.to_numeric(pd.Series([raw_factor]), errors="coerce").iloc[0]
            if quarter not in available_periods:
                raise ValueError(f"Custom RUC policy period {quarter!r} is not present in scenario inputs.")
            if pd.isna(factor) or not np.isfinite(float(factor)) or float(factor) < 0.0:
                raise ValueError(f"Custom RUC policy factor for {quarter} must be finite and non-negative.")
            policy_multipliers[quarter] = float(factor)
            planned_rate = pd.to_numeric(pd.Series([planned.get(quarter, np.nan)]), errors="coerce").iloc[0]
            if pd.isna(planned_rate) or not np.isfinite(float(planned_rate)):
                raise ValueError(f"Published PED rate is unavailable for custom policy period {quarter}.")
            petrol_price_deltas_cents[quarter] = float(planned_rate) * (float(factor) - 1.0) * 100.0
    period = scenario["canonical_period"].astype(str)
    stream = scenario["stream"].astype(str)
    if quarterly_policy_factors is None:
        # Fail closed if the governed schedule ever ends before the scenario
        # inputs do: a governed policy state must never silently revert to
        # published pricing in later quarters because the schedule ran out.
        # Custom quarterly_policy_factors deliberately cover subsets, so the
        # guard applies only to schedule-derived states.
        uplift_start_serial = quarter_serial(FED_UPLIFT_START_PERIOD)
        uncovered = sorted(
            {
                quarter
                for quarter in period.unique()
                if quarter_serial(quarter) >= uplift_start_serial
                and quarter not in policy_multipliers
            },
            key=quarter_serial,
        )
        if uncovered:
            raise ValueError(
                "The governed FED schedule does not cover scenario-input quarters "
                + ", ".join(uncovered[:4])
                + (" ..." if len(uncovered) > 4 else "")
                + f" for policy state {state!r}; extend the schedule horizon instead "
                "of letting the policy silently truncate."
            )
    nominal_petrol_path = _source_nominal_petrol_path(
        source_inputs,
        Path(repo_root),
    )

    petrol_field = _STREAM_PRICE_FIELDS["PED"]
    if petrol_field not in scenario.columns:
        raise ValueError(f"Scenario inputs are missing required PED pump-price field {petrol_field!r}.")
    scenario[petrol_field] = scenario[petrol_field].astype(object)
    scenario["policy_source_nominal_petrol_cpl"] = np.nan
    scenario["policy_target_nominal_petrol_cpl"] = np.nan
    scenario["policy_nominal_petrol_ratio"] = np.nan
    scenario["policy_real_petrol_ratio"] = np.nan
    scenario["policy_petrol_wedge_nominal_cpl"] = np.nan
    scenario["policy_free_source_nominal_petrol_cpl"] = np.nan
    scenario["policy_published_fed_wedge_nominal_cpl"] = np.nan
    ped_stream = stream.eq("PED")
    for quarter, delta_cents in petrol_price_deltas_cents.items():
        mask = ped_stream & period.eq(str(quarter))
        if not mask.any():
            continue
        values = pd.to_numeric(scenario.loc[mask, petrol_field], errors="coerce")
        if values.isna().any():
            raise ValueError(
                f"PED policy could not transform non-numeric {petrol_field!r} values in {quarter}."
            )
        policy_free_source_nominal = nominal_petrol_path.get(str(quarter))
        if (
            policy_free_source_nominal is None
            or not np.isfinite(float(policy_free_source_nominal))
            or float(policy_free_source_nominal) <= 0.0
        ):
            raise ValueError(
                f"Policy-free nominal petrol price is unavailable for policy period {quarter}."
            )
        published_wedge = pd.to_numeric(
            pd.Series([published_petrol_wedges_cents.get(str(quarter), np.nan)]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(published_wedge) or not np.isfinite(float(published_wedge)):
            raise ValueError(
                f"Published FED pump-price wedge is unavailable for policy period {quarter}."
            )
        source_nominal = float(policy_free_source_nominal) + float(published_wedge)
        if source_nominal <= 0.0:
            raise ValueError(
                f"Published-policy nominal pump price is non-positive in {quarter}."
            )
        target_nominal = float(source_nominal) + float(delta_cents)
        if target_nominal <= 0.0:
            raise ValueError(
                f"PED policy would make the nominal pump price non-positive in {quarter}."
            )
        nominal_ratio = target_nominal / float(source_nominal)
        adjusted = values.to_numpy(dtype=float) * nominal_ratio
        scenario.loc[mask, petrol_field] = adjusted
        scenario.loc[mask, "policy_source_nominal_petrol_cpl"] = float(
            source_nominal
        )
        scenario.loc[mask, "policy_free_source_nominal_petrol_cpl"] = float(
            policy_free_source_nominal
        )
        scenario.loc[mask, "policy_published_fed_wedge_nominal_cpl"] = float(
            published_wedge
        )
        scenario.loc[mask, "policy_target_nominal_petrol_cpl"] = target_nominal
        scenario.loc[mask, "policy_nominal_petrol_ratio"] = nominal_ratio
        scenario.loc[mask, "policy_real_petrol_ratio"] = (
            adjusted / values.to_numpy(dtype=float)
        )
        scenario.loc[mask, "policy_petrol_wedge_nominal_cpl"] = float(delta_cents)

    for stream_name, fields in _STREAM_RUC_PRICE_FIELDS.items():
        stream_mask = stream.eq(stream_name)
        for field in fields:
            if field not in scenario.columns:
                raise ValueError(f"Scenario inputs are missing required RUC-price field {field!r}.")
            scenario[field] = scenario[field].astype(object)
            for quarter, multiplier in policy_multipliers.items():
                if abs(float(multiplier) - 1.0) <= 1e-12:
                    continue
                mask = stream_mask & period.eq(str(quarter))
                if not mask.any():
                    continue
                values = pd.to_numeric(scenario.loc[mask, field], errors="coerce")
                if values.isna().any():
                    raise ValueError(
                        f"RUC policy could not transform non-numeric {field!r} values in {quarter}."
                    )
                scenario.loc[mask, field] = values.to_numpy(dtype=float) * float(multiplier)

    scenario = _rebuild_light_ruc_price_lag(scenario)
    scenario = _rebuild_heavy_ruc_price_lead(scenario)
    scenario["scenario_name"] = str(scenario_name)
    scenario["role"] = "comparison"
    if "scenario_role" in scenario.columns:
        scenario["scenario_role"] = "comparison"
    if scenario_display_name is None:
        scenario_display_name = str(scenario_name)
    scenario["scenario_display_name"] = str(scenario_display_name)
    scenario["policy_state"] = state
    scenario["policy_path_id"] = POLICY_PATH_IDS.get(str(scenario_name), str(scenario_name))
    if "source_artifact" in scenario.columns:
        scenario["source_artifact"] = (
            scenario["source_artifact"].fillna("").astype(str)
            + f"; runtime_ped_ruc_policy:{state}:nominal_pump_ratio_to_real_and_ruc_target_over_planned"
        ).str.strip("; ")
    return scenario.reset_index(drop=True)


def _governed_policy_demand_elasticities(repo_root: Path) -> pd.DataFrame:
    """Load the medium post-model demand elasticities with source lineage."""

    parquet_path = repo_root / "data" / "current_revenue_outlook" / "sensitivity_seed_inputs.parquet"
    csv_path = parquet_path.with_suffix(".csv")
    # Prefer the compact CSV for clean-cloud portability; it is materialized
    # from the same governed seed frame as the Parquet sibling.
    if csv_path.exists():
        seeds = pd.read_csv(csv_path)
        source_path = csv_path
    elif parquet_path.exists():
        seeds = pd.read_parquet(parquet_path)
        source_path = parquet_path
    else:
        raise FileNotFoundError(
            "The governed sensitivity seed inputs are required for policy-price calibration."
        )
    required = {
        "family",
        "stream",
        "scenario_level",
        "value",
        "cell",
        "workbook_basename",
        "workbook_sha256",
    }
    missing = required.difference(seeds.columns)
    if missing:
        raise ValueError(
            "Sensitivity seed inputs are missing required columns: "
            + ", ".join(sorted(missing))
        )
    selected = seeds[
        seeds["family"].astype(str).eq("demand_elasticity")
        & seeds["scenario_level"].astype(str).eq(_POLICY_DEMAND_ELASTICITY_LEVEL)
        & seeds["stream"].astype(str).isin(_POLICY_GENERALIZED_PRICE_FIELDS)
    ].copy()
    counts = selected.groupby("stream", dropna=False).size()
    invalid_counts = {
        stream: int(counts.get(stream, 0))
        for stream in _POLICY_GENERALIZED_PRICE_FIELDS
        if int(counts.get(stream, 0)) != 1
    }
    if invalid_counts:
        raise ValueError(
            "Expected exactly one governed medium demand elasticity per stream; "
            f"found {invalid_counts}."
        )
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    if (
        selected["value"].isna().any()
        or not np.isfinite(selected["value"].to_numpy(dtype=float)).all()
        or selected["value"].ge(0.0).any()
    ):
        raise ValueError("Governed policy demand elasticities must be finite and negative.")
    selected["source_path"] = str(source_path.relative_to(repo_root)).replace("\\", "/")
    return selected.reset_index(drop=True)


def _apply_governed_policy_demand_calibration(
    replay: ScenarioInputForecastReplayResult,
    *,
    replay_inputs: pd.DataFrame,
    price_only_replay: ScenarioInputForecastReplayResult,
    repo_root: Path,
    base_scenario_name: str = _BASE_SCENARIO_NAME,
) -> ScenarioInputForecastReplayResult:
    """Apply conflict and policy price elasticities once against matched paths.

    Every non-Base path references the same Base quarter. PED uses its complete
    retail pump-price ratio. Light and Heavy RUC use one generalized running
    cost per 1,000 km: diesel fuel cost at the governed class intensity plus
    the class RUC rate. The governed retail-diesel elasticity is then applied
    exactly once to that combined ratio. This avoids treating a full RUC-price
    ratio as if it were a second independent diesel-price shock.
    """

    forecasts = replay.future_forecasts.copy()
    price_only_forecasts = price_only_replay.future_forecasts.copy()
    required_forecast = {"scenario_name", "stream", "target_period", "forecast"}
    missing_forecast = required_forecast.difference(forecasts.columns)
    if missing_forecast:
        raise ValueError(
            "Replay forecasts are missing policy calibration columns: "
            + ", ".join(sorted(missing_forecast))
        )
    missing_price_only_forecast = required_forecast.difference(
        price_only_forecasts.columns
    )
    if missing_price_only_forecast:
        raise ValueError(
            "Price-only replay forecasts are missing policy calibration columns: "
            + ", ".join(sorted(missing_price_only_forecast))
        )
    required_inputs = {"scenario_name", "stream", "canonical_period"}
    missing_inputs = required_inputs.difference(replay_inputs.columns)
    if missing_inputs:
        raise ValueError(
            "Replay inputs are missing policy calibration columns: "
            + ", ".join(sorted(missing_inputs))
        )

    elasticities = _governed_policy_demand_elasticities(repo_root).set_index("stream")
    input_index = replay_inputs.set_index(["scenario_name", "stream", "canonical_period"])
    if not input_index.index.is_unique:
        raise ValueError("Replay inputs contain duplicate policy calibration keys.")
    forecast_keys = ["scenario_name", "stream", "target_period"]
    if forecasts.duplicated(forecast_keys, keep=False).any():
        duplicates = forecasts.loc[
            forecasts.duplicated(forecast_keys, keep=False), forecast_keys
        ].drop_duplicates()
        raise ValueError(
            "Replay forecasts contain duplicate policy calibration keys: "
            + duplicates.astype(str).agg("/".join, axis=1).str.cat(sep=", ")
        )
    forecast_row_lookup = {
        (str(row.scenario_name), str(row.stream), str(row.target_period)): index
        for index, row in forecasts.iterrows()
    }
    raw_forecast_lookup = {
        (str(row.scenario_name), str(row.stream), str(row.target_period)): float(
            pd.to_numeric(pd.Series([row.forecast]), errors="coerce").iloc[0]
        )
        for row in forecasts.itertuples()
        if pd.notna(
            pd.to_numeric(pd.Series([row.forecast]), errors="coerce").iloc[0]
        )
    }
    if price_only_forecasts.duplicated(forecast_keys, keep=False).any():
        duplicates = price_only_forecasts.loc[
            price_only_forecasts.duplicated(forecast_keys, keep=False),
            forecast_keys,
        ].drop_duplicates()
        raise ValueError(
            "Price-only replay forecasts contain duplicate calibration keys: "
            + duplicates.astype(str).agg("/".join, axis=1).str.cat(sep=", ")
        )
    price_only_forecast_lookup = {
        (str(row.scenario_name), str(row.stream), str(row.target_period)): float(
            pd.to_numeric(
                pd.Series([row.forecast]), errors="coerce"
            ).iloc[0]
        )
        for row in price_only_forecasts.itertuples()
        if pd.notna(pd.to_numeric(pd.Series([row.forecast]), errors="coerce").iloc[0])
    }
    conflict_reference_scenarios = {
        conflict_scenario_name(level): base_scenario_name
        for level in CONFLICT_FUEL_SCENARIO_LEVELS
    }
    policy_reference_scenarios = {
        scenario_name: base_scenario_name
        for scenario_name in {
            *_POLICY_REFERENCE_SCENARIOS,
            BASE_DELAYED_6M_SCENARIO_NAME,
            BASE_NO_UPLIFT_SCENARIO_NAME,
        }
    }
    variant_reference_scenarios = {
        **conflict_reference_scenarios,
        **policy_reference_scenarios,
    }

    policy_variant_mask = forecasts["scenario_name"].astype(str).isin(
        policy_reference_scenarios
    )
    demand_target_mask = forecasts["scenario_name"].astype(str).isin(
        {*conflict_reference_scenarios, *policy_reference_scenarios}
    )
    forecasts["demand_raw_forecast"] = np.nan
    forecasts.loc[demand_target_mask, "demand_raw_forecast"] = pd.to_numeric(
        forecasts.loc[demand_target_mask, "forecast"], errors="coerce"
    ).to_numpy(dtype=float)
    forecasts["demand_calibrated_delta"] = np.nan
    forecasts.loc[demand_target_mask, "demand_calibrated_delta"] = 0.0
    forecasts["demand_price_only_raw_forecast"] = np.nan
    forecasts["demand_gdp_input_level_factor"] = 1.0
    forecasts["demand_gdp_model_factor_raw"] = np.nan
    forecasts["demand_gdp_model_factor"] = np.nan
    forecasts["demand_gdp_model_delta"] = np.nan
    forecasts["demand_gdp_factor_source_scenario_name"] = ""
    forecasts["demand_gdp_factor_source_raw_forecast"] = np.nan
    forecasts["demand_gdp_factor_source_price_only_forecast"] = np.nan
    forecasts["demand_gdp_model_basis"] = ""
    forecasts["demand_gdp_sign_guard_applied"] = False
    forecasts["demand_gdp_downside_sign_guard_applied"] = False
    forecasts["demand_gdp_identity_guard_applied"] = False
    # Clipping lineage: the displayed GDP contribution is a governed, guarded
    # quantity wherever a guard binds, not a purely model-estimated response.
    forecasts["demand_gdp_guard_clip_amount"] = np.nan
    forecasts["demand_gdp_guard_reason"] = ""
    forecasts["demand_reference_scenario_name"] = ""
    forecasts["demand_reference_forecast"] = np.nan
    forecasts["demand_generalized_price_field"] = ""
    forecasts["demand_reference_price"] = np.nan
    forecasts["demand_variant_price"] = np.nan
    forecasts["demand_price_ratio"] = np.nan
    forecasts["demand_fuel_price_field"] = ""
    forecasts["demand_reference_fuel_price_cpl"] = np.nan
    forecasts["demand_variant_fuel_price_cpl"] = np.nan
    forecasts["demand_fuel_price_ratio"] = np.nan
    forecasts["demand_reference_fuel_cost_nzd_per_1000km"] = np.nan
    forecasts["demand_variant_fuel_cost_nzd_per_1000km"] = np.nan
    forecasts["demand_ruc_price_field"] = ""
    forecasts["demand_reference_ruc_price_nzd_per_1000km"] = np.nan
    forecasts["demand_variant_ruc_price_nzd_per_1000km"] = np.nan
    forecasts["demand_ruc_price_ratio"] = np.nan
    forecasts["demand_diesel_litres_per_100km"] = np.nan
    forecasts["demand_intensity_source"] = ""
    forecasts["demand_conflict_fuel_component_changed"] = False
    forecasts["demand_policy_price_component_changed"] = False
    forecasts["demand_elasticity"] = np.nan
    forecasts["demand_calibration_applied"] = False
    forecasts["demand_calibration_kind"] = ""
    forecasts["demand_calibration_basis"] = ""
    forecasts["demand_output_layer"] = ""
    forecasts.loc[demand_target_mask, "demand_output_layer"] = "raw_fitted_replay"
    forecasts["demand_calibration_note"] = ""
    forecasts["conflict_calibration_applied"] = False
    forecasts["policy_raw_forecast"] = np.nan
    forecasts.loc[policy_variant_mask, "policy_raw_forecast"] = pd.to_numeric(
        forecasts.loc[policy_variant_mask, "forecast"], errors="coerce"
    ).to_numpy(dtype=float)
    forecasts["policy_calibrated_delta"] = np.nan
    forecasts.loc[policy_variant_mask, "policy_calibrated_delta"] = 0.0
    forecasts["policy_reference_scenario_name"] = ""
    forecasts["policy_reference_forecast"] = np.nan
    forecasts["policy_generalized_price_field"] = ""
    forecasts["policy_reference_price"] = np.nan
    forecasts["policy_variant_price"] = np.nan
    forecasts["policy_price_ratio"] = np.nan
    forecasts["policy_fuel_price_ratio"] = np.nan
    forecasts["policy_ruc_price_ratio"] = np.nan
    forecasts["policy_demand_elasticity"] = np.nan
    forecasts["policy_elasticity_level"] = ""
    forecasts["policy_elasticity_source_cell"] = ""
    forecasts["policy_elasticity_source_path"] = ""
    forecasts["policy_elasticity_source_workbook"] = ""
    forecasts["policy_elasticity_source_sha256"] = ""
    forecasts["policy_calibration_applied"] = False
    forecasts["policy_calibration_basis"] = ""
    forecasts["policy_output_layer"] = ""
    forecasts.loc[policy_variant_mask, "policy_output_layer"] = "raw_fitted_replay"
    forecasts["policy_component_forecasts_basis"] = ""
    forecasts.loc[
        policy_variant_mask, "policy_component_forecasts_basis"
    ] = "raw_fitted_replay_not_reconciled_to_structural_overlay"
    forecasts["policy_calibration_note"] = ""
    forecasts.loc[policy_variant_mask, "policy_calibration_note"] = (
        _POLICY_CALIBRATION_NOTE
    )

    # Per-stream seam: scenario quarters at or before a stream's latest
    # accepted actual are canonical history, never calibrated forecasts.
    from .forecast_runner import quarter_sort_key as _seam_qkey
    from .forecast_runner import stream_latest_accepted_periods as _seam_latest

    try:
        _seam_cutoffs = _seam_latest(None)
    except Exception:
        _seam_cutoffs = {}

    directly_calibrated_rows: list[int] = []
    for variant_name, reference_name in variant_reference_scenarios.items():
        is_policy_variant = variant_name in policy_reference_scenarios
        for stream in _STREAM_PRICE_FIELDS:
            fuel_price_field = _STREAM_PRICE_FIELDS[stream]
            if fuel_price_field not in replay_inputs.columns:
                raise ValueError(
                    f"Replay inputs are missing fuel-price field {fuel_price_field!r}."
                )
            ruc_price_field = (
                _POLICY_GENERALIZED_PRICE_FIELDS[stream]
                if stream in _RUC_DIESEL_LITRES_PER_100KM
                else ""
            )
            if ruc_price_field and ruc_price_field not in replay_inputs.columns:
                raise ValueError(
                    f"Replay inputs are missing RUC-price field {ruc_price_field!r}."
                )
            variant_rows = replay_inputs[
                replay_inputs["scenario_name"].astype(str).eq(variant_name)
                & replay_inputs["stream"].astype(str).eq(stream)
            ]
            for period in variant_rows["canonical_period"].dropna().astype(str):
                _cutoff = _seam_cutoffs.get(str(stream))
                if _cutoff and _seam_qkey(period) <= _seam_qkey(_cutoff):
                    continue
                variant_key = (variant_name, stream, period)
                reference_key = (reference_name, stream, period)
                if (
                    variant_key not in input_index.index
                    or reference_key not in input_index.index
                ):
                    raise ValueError(
                        f"Demand calibration inputs are incomplete for "
                        f"{variant_name}/{stream}/{period}."
                    )

                def numeric_input(key: tuple[str, str, str], field: str) -> float:
                    value = pd.to_numeric(
                        pd.Series([input_index.at[key, field]]), errors="coerce"
                    ).iloc[0]
                    if (
                        pd.isna(value)
                        or not np.isfinite(float(value))
                        or float(value) <= 0.0
                    ):
                        raise ValueError(
                            f"Demand calibration input {field!r} must be finite and "
                            f"positive for {variant_name}/{stream}/{period}."
                        )
                    return float(value)

                reference_fuel_price = numeric_input(
                    reference_key, fuel_price_field
                )
                variant_fuel_price = numeric_input(variant_key, fuel_price_field)
                fuel_price_ratio = variant_fuel_price / reference_fuel_price
                reference_fuel_cost = np.nan
                variant_fuel_cost = np.nan
                reference_ruc_price = np.nan
                variant_ruc_price = np.nan
                ruc_price_ratio = np.nan
                diesel_intensity = np.nan
                intensity_source = ""
                if stream == "PED":
                    generalized_price_field = fuel_price_field
                    reference_price = reference_fuel_price
                    variant_price = variant_fuel_price
                else:
                    diesel_intensity = float(
                        _RUC_DIESEL_LITRES_PER_100KM[stream]
                    )
                    intensity_source = _RUC_DIESEL_INTENSITY_SOURCE[stream]
                    reference_fuel_cost = (
                        reference_fuel_price * diesel_intensity / 10.0
                    )
                    variant_fuel_cost = (
                        variant_fuel_price * diesel_intensity / 10.0
                    )
                    reference_ruc_price = numeric_input(
                        reference_key, ruc_price_field
                    )
                    variant_ruc_price = numeric_input(
                        variant_key, ruc_price_field
                    )
                    ruc_price_ratio = variant_ruc_price / reference_ruc_price
                    generalized_price_field = _GENERALIZED_RUNNING_COST_FIELD
                    reference_price = reference_fuel_cost + reference_ruc_price
                    variant_price = variant_fuel_cost + variant_ruc_price
                price_ratio = variant_price / reference_price

                variant_forecast_key = (variant_name, stream, period)
                reference_forecast_key = (reference_name, stream, period)
                if (
                    variant_forecast_key not in forecast_row_lookup
                    or reference_forecast_key not in forecast_row_lookup
                    or variant_forecast_key not in price_only_forecast_lookup
                ):
                    raise ValueError(
                        f"Matched price/GDP calibration forecasts are incomplete for "
                        f"{variant_name}/{stream}/{period}."
                    )
                row_index = forecast_row_lookup[variant_forecast_key]
                reference_row_index = forecast_row_lookup[reference_forecast_key]
                raw_forecast = pd.to_numeric(
                    pd.Series([forecasts.at[row_index, "demand_raw_forecast"]]),
                    errors="coerce",
                ).iloc[0]
                reference_forecast = pd.to_numeric(
                    pd.Series([forecasts.at[reference_row_index, "forecast"]]),
                    errors="coerce",
                ).iloc[0]
                price_only_raw_forecast = float(
                    price_only_forecast_lookup[variant_forecast_key]
                )
                gdp_factor_source_name = (
                    _POLICY_REFERENCE_SCENARIOS[variant_name]
                    if is_policy_variant
                    else variant_name
                )
                gdp_factor_source_key = (
                    gdp_factor_source_name,
                    stream,
                    period,
                )
                if (
                    gdp_factor_source_key not in raw_forecast_lookup
                    or gdp_factor_source_key not in price_only_forecast_lookup
                ):
                    raise ValueError(
                        f"GDP-factor source forecasts are incomplete for "
                        f"{variant_name}/{stream}/{period} via "
                        f"{gdp_factor_source_name}."
                    )
                gdp_factor_source_raw_forecast = float(
                    raw_forecast_lookup[gdp_factor_source_key]
                )
                gdp_factor_source_price_only_forecast = float(
                    price_only_forecast_lookup[gdp_factor_source_key]
                )
                if (
                    pd.isna(raw_forecast)
                    or pd.isna(reference_forecast)
                    or not np.isfinite(float(raw_forecast))
                    or not np.isfinite(float(reference_forecast))
                    or not np.isfinite(price_only_raw_forecast)
                    or not np.isfinite(gdp_factor_source_raw_forecast)
                    or not np.isfinite(gdp_factor_source_price_only_forecast)
                    or float(raw_forecast) <= 0.0
                    or float(reference_forecast) <= 0.0
                    or price_only_raw_forecast <= 0.0
                    or gdp_factor_source_raw_forecast <= 0.0
                    or gdp_factor_source_price_only_forecast <= 0.0
                ):
                    raise ValueError(
                        f"Demand calibration forecasts must be numeric for "
                        f"{variant_name}/{stream}/{period}."
                    )
                gdp_model_factor_raw = (
                    gdp_factor_source_raw_forecast
                    / gdp_factor_source_price_only_forecast
                )
                if (
                    not np.isfinite(gdp_model_factor_raw)
                    or gdp_model_factor_raw <= 0.0
                ):
                    raise ValueError(
                        f"Matched GDP model factor must be positive for "
                        f"{variant_name}/{stream}/{period}."
                    )
                input_gdp_factor_value = pd.to_numeric(
                    pd.Series(
                        [
                            input_index.at[
                                variant_key, "conflict_gdp_level_factor"
                            ]
                            if "conflict_gdp_level_factor"
                            in replay_inputs.columns
                            else 1.0
                        ]
                    ),
                    errors="coerce",
                ).iloc[0]
                input_gdp_factor = (
                    float(input_gdp_factor_value)
                    if pd.notna(input_gdp_factor_value)
                    and np.isfinite(float(input_gdp_factor_value))
                    else 1.0
                )

                fuel_changed = not np.isclose(
                    fuel_price_ratio, 1.0, rtol=1e-12, atol=1e-12
                )
                conflict_fuel_component_changed = fuel_changed
                policy_price_component_changed = False
                if is_policy_variant:
                    published_source_name = _POLICY_REFERENCE_SCENARIOS[variant_name]
                    published_key = (published_source_name, stream, period)
                    if published_key not in input_index.index:
                        raise ValueError(
                            f"Policy component reference is incomplete for "
                            f"{variant_name}/{stream}/{period}."
                        )
                    published_fuel_price = numeric_input(
                        published_key, fuel_price_field
                    )
                    conflict_fuel_component_changed = not np.isclose(
                        published_fuel_price / reference_fuel_price,
                        1.0,
                        rtol=1e-12,
                        atol=1e-12,
                    )
                    policy_fuel_component_changed = not np.isclose(
                        variant_fuel_price / published_fuel_price,
                        1.0,
                        rtol=1e-12,
                        atol=1e-12,
                    )
                    policy_ruc_component_changed = False
                    if stream != "PED":
                        published_ruc_price = numeric_input(
                            published_key, ruc_price_field
                        )
                        policy_ruc_component_changed = not np.isclose(
                            variant_ruc_price / published_ruc_price,
                            1.0,
                            rtol=1e-12,
                            atol=1e-12,
                        )
                    policy_price_component_changed = bool(
                        policy_fuel_component_changed
                        or policy_ruc_component_changed
                    )
                if (
                    conflict_fuel_component_changed
                    and policy_price_component_changed
                ):
                    calibration_kind = "conflict_and_policy"
                elif conflict_fuel_component_changed:
                    calibration_kind = "conflict"
                elif policy_price_component_changed:
                    calibration_kind = "policy"
                else:
                    calibration_kind = "identity_to_base"
                basis = (
                    _POLICY_CALIBRATION_BASIS
                    if calibration_kind == "policy"
                    else _CONFLICT_CALIBRATION_BASIS
                )
                note = (
                    _POLICY_CALIBRATION_NOTE
                    if calibration_kind == "policy"
                    else _CONFLICT_CALIBRATION_NOTE
                )
                elasticity = float(elasticities.at[stream, "value"])
                gdp_input_is_identity = bool(
                    np.isclose(
                        input_gdp_factor,
                        1.0,
                        rtol=0.0,
                        atol=1e-12,
                    )
                )
                gdp_identity_guard_applied = bool(
                    gdp_input_is_identity
                    and not np.isclose(
                        gdp_model_factor_raw,
                        1.0,
                        rtol=0.0,
                        atol=1e-12,
                    )
                )
                gdp_downside_sign_guard_applied = bool(
                    input_gdp_factor < 1.0 - 1e-12
                    and gdp_model_factor_raw > 1.0
                )
                gdp_sign_guard_applied = bool(
                    gdp_identity_guard_applied
                    or gdp_downside_sign_guard_applied
                )
                if gdp_input_is_identity:
                    gdp_model_factor = 1.0
                elif gdp_downside_sign_guard_applied:
                    gdp_model_factor = min(gdp_model_factor_raw, 1.0)
                else:
                    gdp_model_factor = gdp_model_factor_raw
                calibrated = (
                    float(reference_forecast)
                    * float(np.power(price_ratio, elasticity))
                    * gdp_model_factor
                )
                output_layer = (
                    "governed_structural_identity_to_base"
                    if calibration_kind == "identity_to_base"
                    else "governed_structural_overlay"
                )

                forecasts.at[row_index, "demand_reference_scenario_name"] = (
                    reference_name
                )
                forecasts.at[
                    row_index, "demand_price_only_raw_forecast"
                ] = price_only_raw_forecast
                forecasts.at[
                    row_index, "demand_gdp_input_level_factor"
                ] = input_gdp_factor
                forecasts.at[
                    row_index, "demand_gdp_model_factor_raw"
                ] = gdp_model_factor_raw
                forecasts.at[row_index, "demand_gdp_model_factor"] = (
                    gdp_model_factor
                )
                forecasts.at[row_index, "demand_gdp_model_delta"] = (
                    gdp_factor_source_raw_forecast
                    - gdp_factor_source_price_only_forecast
                )
                forecasts.at[
                    row_index, "demand_gdp_factor_source_scenario_name"
                ] = gdp_factor_source_name
                forecasts.at[
                    row_index, "demand_gdp_factor_source_raw_forecast"
                ] = gdp_factor_source_raw_forecast
                forecasts.at[
                    row_index,
                    "demand_gdp_factor_source_price_only_forecast",
                ] = gdp_factor_source_price_only_forecast
                forecasts.at[row_index, "demand_gdp_model_basis"] = (
                    "published_conflict_family_raw_price_plus_gdp_replay_"
                    "divided_by_matching_published_price_only_replay; "
                    "policy timing never changes the GDP family factor; "
                    "an identity GDP input forces an identity factor and a "
                    "positive response to lower GDP is capped at identity"
                )
                forecasts.at[
                    row_index, "demand_gdp_sign_guard_applied"
                ] = gdp_sign_guard_applied
                forecasts.at[
                    row_index,
                    "demand_gdp_downside_sign_guard_applied",
                ] = gdp_downside_sign_guard_applied
                forecasts.at[
                    row_index,
                    "demand_gdp_identity_guard_applied",
                ] = gdp_identity_guard_applied
                forecasts.at[row_index, "demand_gdp_guard_clip_amount"] = (
                    gdp_model_factor - gdp_model_factor_raw
                )
                forecasts.at[row_index, "demand_gdp_guard_reason"] = (
                    "identity_gdp_input_forces_identity_factor"
                    if gdp_identity_guard_applied
                    else (
                        "positive_response_to_lower_gdp_capped_at_identity"
                        if gdp_downside_sign_guard_applied
                        else ""
                    )
                )
                forecasts.at[row_index, "demand_reference_forecast"] = float(
                    reference_forecast
                )
                forecasts.at[row_index, "demand_generalized_price_field"] = (
                    generalized_price_field
                )
                forecasts.at[row_index, "demand_reference_price"] = float(
                    reference_price
                )
                forecasts.at[row_index, "demand_variant_price"] = float(
                    variant_price
                )
                forecasts.at[row_index, "demand_price_ratio"] = price_ratio
                forecasts.at[row_index, "demand_fuel_price_field"] = fuel_price_field
                forecasts.at[
                    row_index, "demand_reference_fuel_price_cpl"
                ] = reference_fuel_price
                forecasts.at[
                    row_index, "demand_variant_fuel_price_cpl"
                ] = variant_fuel_price
                forecasts.at[row_index, "demand_fuel_price_ratio"] = fuel_price_ratio
                forecasts.at[
                    row_index, "demand_reference_fuel_cost_nzd_per_1000km"
                ] = reference_fuel_cost
                forecasts.at[
                    row_index, "demand_variant_fuel_cost_nzd_per_1000km"
                ] = variant_fuel_cost
                forecasts.at[row_index, "demand_ruc_price_field"] = ruc_price_field
                forecasts.at[
                    row_index, "demand_reference_ruc_price_nzd_per_1000km"
                ] = reference_ruc_price
                forecasts.at[
                    row_index, "demand_variant_ruc_price_nzd_per_1000km"
                ] = variant_ruc_price
                forecasts.at[row_index, "demand_ruc_price_ratio"] = ruc_price_ratio
                forecasts.at[
                    row_index, "demand_diesel_litres_per_100km"
                ] = diesel_intensity
                forecasts.at[row_index, "demand_intensity_source"] = intensity_source
                forecasts.at[
                    row_index, "demand_conflict_fuel_component_changed"
                ] = conflict_fuel_component_changed
                forecasts.at[
                    row_index, "demand_policy_price_component_changed"
                ] = policy_price_component_changed
                forecasts.at[row_index, "demand_elasticity"] = elasticity
                forecasts.at[row_index, "demand_calibration_applied"] = True
                forecasts.at[row_index, "demand_calibration_kind"] = calibration_kind
                forecasts.at[row_index, "demand_calibration_basis"] = basis
                forecasts.at[row_index, "demand_output_layer"] = output_layer
                forecasts.at[row_index, "demand_calibration_note"] = note
                forecasts.at[row_index, "demand_calibrated_delta"] = (
                    calibrated - float(raw_forecast)
                )
                forecasts.at[row_index, "forecast"] = calibrated
                directly_calibrated_rows.append(row_index)
                forecasts.at[row_index, "conflict_calibration_applied"] = bool(
                    conflict_fuel_component_changed
                )

                if not is_policy_variant:
                    continue
                forecasts.at[row_index, "policy_raw_forecast"] = float(raw_forecast)
                forecasts.at[row_index, "policy_reference_scenario_name"] = (
                    reference_name
                )
                forecasts.at[row_index, "policy_reference_forecast"] = float(
                    reference_forecast
                )
                forecasts.at[
                    row_index, "policy_generalized_price_field"
                ] = generalized_price_field
                forecasts.at[row_index, "policy_reference_price"] = float(
                    reference_price
                )
                forecasts.at[row_index, "policy_variant_price"] = float(variant_price)
                forecasts.at[row_index, "policy_price_ratio"] = price_ratio
                forecasts.at[row_index, "policy_fuel_price_ratio"] = fuel_price_ratio
                forecasts.at[row_index, "policy_ruc_price_ratio"] = ruc_price_ratio
                forecasts.at[row_index, "policy_demand_elasticity"] = elasticity
                forecasts.at[
                    row_index, "policy_elasticity_level"
                ] = _POLICY_DEMAND_ELASTICITY_LEVEL
                forecasts.at[row_index, "policy_elasticity_source_cell"] = str(
                    elasticities.at[stream, "cell"]
                )
                forecasts.at[row_index, "policy_elasticity_source_path"] = str(
                    elasticities.at[stream, "source_path"]
                )
                forecasts.at[
                    row_index, "policy_elasticity_source_workbook"
                ] = str(elasticities.at[stream, "workbook_basename"])
                forecasts.at[row_index, "policy_elasticity_source_sha256"] = str(
                    elasticities.at[stream, "workbook_sha256"]
                )
                forecasts.at[row_index, "policy_calibration_applied"] = True
                forecasts.at[
                    row_index, "policy_calibration_basis"
                ] = _POLICY_CALIBRATION_BASIS
                forecasts.at[row_index, "policy_output_layer"] = output_layer
                forecasts.at[row_index, "policy_calibrated_delta"] = (
                    calibrated - float(raw_forecast)
                )

    directly_applied = pd.Series(False, index=forecasts.index)
    structural_components = pd.DataFrame()
    formula_residual_by_scenario: dict[str, float] = {}
    formula_ratio_by_scenario: dict[str, float] = {}
    closure_residual_by_scenario: dict[str, float] = {}
    closure_ratio_by_scenario: dict[str, float] = {}
    sign_breaches_by_scenario: dict[str, int] = {}
    if directly_calibrated_rows:
        directly_applied.loc[directly_calibrated_rows] = True
        applied_rows = forecasts.loc[directly_applied].copy()
        reference = pd.to_numeric(
            applied_rows["demand_reference_forecast"], errors="coerce"
        )
        ratio = pd.to_numeric(applied_rows["demand_price_ratio"], errors="coerce")
        elasticity = pd.to_numeric(applied_rows["demand_elasticity"], errors="coerce")
        gdp_model_factor = pd.to_numeric(
            applied_rows["demand_gdp_model_factor"], errors="coerce"
        )
        price_response = pd.Series(
            np.power(ratio.to_numpy(dtype=float), elasticity.to_numpy(dtype=float)),
            index=applied_rows.index,
        )
        expected = reference * price_response * gdp_model_factor
        final = pd.to_numeric(applied_rows["forecast"], errors="coerce")
        if not np.allclose(
            final,
            expected,
            rtol=_STRUCTURAL_CLOSURE_RTOL,
            atol=_STRUCTURAL_CLOSURE_ATOL,
        ):
            raise ValueError("Demand calibration failed its exact formula invariant.")
        gdp_adjusted_reference = reference * gdp_model_factor
        cheaper = (
            ratio.lt(1.0)
            & elasticity.lt(0.0)
            & gdp_adjusted_reference.gt(0.0)
        )
        dearer = (
            ratio.gt(1.0)
            & elasticity.lt(0.0)
            & gdp_adjusted_reference.gt(0.0)
        )
        sign_breach = (cheaper & final.le(gdp_adjusted_reference)) | (
            dearer & final.ge(gdp_adjusted_reference)
        )
        if sign_breach.any():
            raise ValueError("Demand calibration failed its economic sign invariant.")

        # The displayed forecast is decomposed into terms that sum to it
        # exactly.  This is the only attribution that describes the structural
        # layer; the fitted ensemble members describe the pre-overlay layer.
        scenario_names = applied_rows["scenario_name"].astype(str)
        component_values = {
            "STRUCTURAL_REFERENCE_BASE": reference,
            "STRUCTURAL_PRICE_RESPONSE": reference * (price_response - 1.0),
            "STRUCTURAL_GDP_RESPONSE": reference * (gdp_model_factor - 1.0),
            "STRUCTURAL_PRICE_GDP_INTERACTION": reference
            * (price_response - 1.0)
            * (gdp_model_factor - 1.0),
        }
        gdp_guard_applied = (
            applied_rows["demand_gdp_sign_guard_applied"].fillna(False).astype(bool)
        )
        gdp_guard_reason = applied_rows["demand_gdp_guard_reason"].fillna("").astype(str)
        gdp_clip_amount = pd.to_numeric(
            applied_rows["demand_gdp_guard_clip_amount"], errors="coerce"
        )
        gdp_model_factor_raw = pd.to_numeric(
            applied_rows["demand_gdp_model_factor_raw"], errors="coerce"
        )
        component_frames: list[pd.DataFrame] = []
        for label in _STRUCTURAL_COMPONENT_LABELS:
            values = component_values[label]
            # The GDP term is a governed, guarded quantity wherever a guard
            # binds. Naming it plainly prevents it being read as a purely
            # model-estimated economic response.
            gdp_bearing = label in {
                "STRUCTURAL_GDP_RESPONSE",
                "STRUCTURAL_PRICE_GDP_INTERACTION",
            }
            component_labels = (
                np.where(
                    gdp_guard_applied.to_numpy(),
                    f"{label}__GUARDED",
                    label,
                )
                if gdp_bearing
                else np.repeat(label, len(applied_rows))
            )
            component_frames.append(
                pd.DataFrame(
                    {
                        "scenario_name": scenario_names.to_numpy(),
                        "stream": applied_rows["stream"].astype(str).to_numpy(),
                        "target_period": applied_rows["target_period"]
                        .astype(str)
                        .to_numpy(),
                        "component_label": component_labels,
                        "component_term": label,
                        "component_forecast": values.to_numpy(dtype=float),
                        "final_forecast": final.to_numpy(dtype=float),
                        # These four terms are signed contributions to the final
                        # layer, not fitted model members. They can be negative
                        # and are not standalone forecast levels, so they carry
                        # no model weight.
                        "component_layer": "final_structural_attribution",
                        "component_semantics": "signed_additive_contribution",
                        "source_forecast_layer": "governed_structural_overlay",
                        "raw_model_components_superseded": True,
                        "component_weight": pd.NA,
                        "demand_reference_scenario_name": applied_rows[
                            "demand_reference_scenario_name"
                        ]
                        .astype(str)
                        .to_numpy(),
                        "demand_reference_forecast": reference.to_numpy(dtype=float),
                        "demand_price_ratio": ratio.to_numpy(dtype=float),
                        "demand_elasticity": elasticity.to_numpy(dtype=float),
                        "demand_price_response_factor": price_response.to_numpy(
                            dtype=float
                        ),
                        "demand_gdp_model_factor_raw": gdp_model_factor_raw.to_numpy(
                            dtype=float
                        ),
                        "demand_gdp_model_factor": gdp_model_factor.to_numpy(
                            dtype=float
                        ),
                        "demand_gdp_sign_guard_applied": gdp_guard_applied.to_numpy(),
                        "demand_gdp_guard_clip_amount": gdp_clip_amount.to_numpy(
                            dtype=float
                        ),
                        "demand_gdp_guard_reason": gdp_guard_reason.to_numpy(),
                        "gdp_contribution_is_guarded": (
                            gdp_guard_applied.to_numpy()
                            if gdp_bearing
                            else np.repeat(False, len(applied_rows))
                        ),
                        "component_basis": _STRUCTURAL_COMPONENT_BASIS,
                        "describes_forecast_layer": "governed_structural_overlay",
                    }
                )
            )
        structural_components = pd.concat(
            component_frames, ignore_index=True, sort=False
        )
        closure = (
            structural_components.groupby(
                ["scenario_name", "stream", "target_period"], dropna=False
            )["component_forecast"]
            .sum()
            .rename("component_sum")
            .reset_index()
        )
        closure_keys = pd.DataFrame(
            {
                "scenario_name": scenario_names.to_numpy(),
                "stream": applied_rows["stream"].astype(str).to_numpy(),
                "target_period": applied_rows["target_period"].astype(str).to_numpy(),
                "final_forecast": final.to_numpy(dtype=float),
            }
        )
        closure = closure.merge(
            closure_keys,
            on=["scenario_name", "stream", "target_period"],
            how="outer",
            validate="one_to_one",
        )
        if closure["component_sum"].isna().any() or closure["final_forecast"].isna().any():
            raise ValueError(
                "Structural component decomposition does not cover every "
                "calibrated scenario/stream/quarter."
            )
        closure["closure_residual"] = (
            closure["component_sum"] - closure["final_forecast"]
        ).abs()
        closure_tolerance = _STRUCTURAL_CLOSURE_ATOL + _STRUCTURAL_CLOSURE_RTOL * closure[
            "final_forecast"
        ].abs()
        if closure["closure_residual"].gt(closure_tolerance).any():
            worst = closure.loc[closure["closure_residual"].idxmax()]
            raise ValueError(
                "Structural component decomposition does not sum to the displayed "
                f"forecast for {worst['scenario_name']}/{worst['stream']}/"
                f"{worst['target_period']}: residual "
                f"{float(worst['closure_residual']):.3e}."
            )

        # Residuals are reported in absolute units for readability, but the
        # validity gate uses the same rtol/atol envelope as the invariants
        # above so that a large-magnitude series is not judged more harshly
        # than the check it mirrors.  A ratio of <= 1 means "within tolerance".
        formula_residual = (final - expected).abs()
        formula_tolerance = (
            _STRUCTURAL_CLOSURE_ATOL + _STRUCTURAL_CLOSURE_RTOL * expected.abs()
        )
        formula_residual_by_scenario = (
            formula_residual.groupby(scenario_names).max().to_dict()
        )
        formula_ratio_by_scenario = (
            (formula_residual / formula_tolerance)
            .groupby(scenario_names)
            .max()
            .to_dict()
        )
        closure_residual_by_scenario = (
            closure.groupby("scenario_name")["closure_residual"].max().to_dict()
        )
        closure_ratio_by_scenario = (
            (closure["closure_residual"] / closure_tolerance)
            .groupby(closure["scenario_name"])
            .max()
            .to_dict()
        )
        sign_breaches_by_scenario = (
            sign_breach.astype(int).groupby(scenario_names).sum().to_dict()
        )
    applied = forecasts["demand_calibration_applied"].fillna(False).astype(bool)
    if not applied.loc[demand_target_mask].all():
        raise ValueError(
            "Demand calibration did not reset every non-Base scenario quarter "
            "to the Base-referenced structural formula."
        )

    replay.future_forecasts = forecasts
    replay.structural_component_forecasts = structural_components

    # Fitted ensemble members for overlay scenarios describe the pre-overlay
    # layer.  They are removed from ``component_forecasts`` so no consumer can
    # attribute the displayed forecast to them, and retained separately for audit.
    overlay_scenarios = {*conflict_reference_scenarios, *policy_reference_scenarios}
    if overlay_scenarios != set(structural_overlay_scenario_ids()):
        raise ValueError(
            "Structural-overlay scenarios diverge from the governed registry; "
            "downstream component and interval guards would not cover them all. "
            "Registry-only: "
            + ", ".join(sorted(set(structural_overlay_scenario_ids()) - overlay_scenarios))
            + "; replay-only: "
            + ", ".join(sorted(overlay_scenarios - set(structural_overlay_scenario_ids())))
            + "."
        )
    components = (
        replay.component_forecasts.copy()
        if replay.component_forecasts is not None
        else pd.DataFrame()
    )
    superseded = pd.DataFrame()
    if not components.empty and "scenario_name" in components.columns:
        overlay_mask = components["scenario_name"].astype(str).isin(overlay_scenarios)
        superseded = components.loc[overlay_mask].copy()
        if not superseded.empty:
            superseded["component_forecast_status"] = "superseded_by_structural_overlay"
            superseded["component_forecast_reason"] = _SUPERSEDED_COMPONENT_REASON
            superseded["describes_forecast_layer"] = "raw_fitted_replay_pre_overlay"
        components = components.loc[~overlay_mask].copy()
        components["describes_forecast_layer"] = "raw_fitted_replay"
        replay.component_forecasts = components.reset_index(drop=True)
    replay.superseded_component_forecasts = superseded.reset_index(drop=True)

    validation = replay.validation_report.copy()
    if validation is not None and not validation.empty and "scenario_name" in validation.columns:
        validation_scenarios = validation["scenario_name"].astype(str)
        validation["model_validation_basis"] = np.where(
            validation_scenarios.isin(overlay_scenarios),
            "raw_fitted_replay_before_structural_overlay",
            "raw_fitted_replay",
        )
        validation["component_forecasts_available"] = ~validation_scenarios.isin(
            overlay_scenarios
        )
        validation["component_attribution_basis"] = np.where(
            validation_scenarios.isin(overlay_scenarios),
            _STRUCTURAL_COMPONENT_BASIS,
            "fitted_ensemble_members",
        )
        policy_applied = forecasts["policy_calibration_applied"].fillna(False).astype(bool)
        conflict_applied = forecasts["conflict_calibration_applied"].fillna(False).astype(bool)
        applied_counts = (
            forecasts.loc[policy_applied]
            .groupby("scenario_name", dropna=False)
            .size()
            .to_dict()
        )
        validation["policy_post_calibration_rows"] = (
            validation_scenarios.map(applied_counts).fillna(0).astype(int)
        )
        # Derived from the measured residuals above, never assigned. A scenario
        # with no calibrated rows is not "valid" - it is not applicable.
        validation["policy_post_calibration_formula_residual"] = (
            validation_scenarios.map(formula_residual_by_scenario).astype(float)
        )
        validation["policy_post_calibration_component_closure_residual"] = (
            validation_scenarios.map(closure_residual_by_scenario).astype(float)
        )
        # <= 1.0 means "inside the same rtol/atol envelope as the invariants".
        validation["policy_post_calibration_formula_tolerance_ratio"] = (
            validation_scenarios.map(formula_ratio_by_scenario).astype(float)
        )
        validation["policy_post_calibration_component_closure_tolerance_ratio"] = (
            validation_scenarios.map(closure_ratio_by_scenario).astype(float)
        )
        validation["policy_post_calibration_sign_breaches"] = (
            validation_scenarios.map(sign_breaches_by_scenario).fillna(0).astype(int)
        )
        # A scenario with no calibrated rows has nothing to validate.  Reporting
        # it as False would read as "Base failed validation", so applicability
        # is carried separately and the verdict is NA rather than False.
        applicable = validation["policy_post_calibration_rows"].gt(0)
        checks_pass = (
            validation["policy_post_calibration_formula_tolerance_ratio"].le(1.0)
            & validation[
                "policy_post_calibration_component_closure_tolerance_ratio"
            ].le(1.0)
            & validation["policy_post_calibration_sign_breaches"].eq(0)
        )
        validation["policy_post_calibration_applicable"] = applicable
        validation["policy_post_calibration_status"] = np.where(
            ~applicable,
            _CALIBRATION_STATUS_NOT_APPLICABLE,
            np.where(checks_pass, _CALIBRATION_STATUS_PASSED, _CALIBRATION_STATUS_FAILED),
        )
        validation["policy_post_calibration_valid"] = pd.Series(
            np.where(applicable, checks_pass, pd.NA), index=validation.index, dtype="boolean"
        )

        conflict_counts = (
            forecasts.loc[conflict_applied]
            .groupby("scenario_name", dropna=False)
            .size()
            .to_dict()
        )
        validation["conflict_post_calibration_rows"] = (
            validation_scenarios.map(conflict_counts).fillna(0).astype(int)
        )
        validation["demand_post_calibration_rows"] = (
            validation_scenarios
            .map(forecasts.loc[applied].groupby("scenario_name").size().to_dict())
            .fillna(0)
            .astype(int)
        )

        # Structural integrity is not predictive validation.  These checks prove
        # the overlay is internally consistent; they say nothing about how a
        # counterfactual conflict or policy path would have performed against
        # observed outcomes, because no such outcome exists to score against.
        #
        # It keys on every calibrated row, not the policy subset: a conflict
        # scenario has no policy rows but is still fully overlaid, and reusing
        # the policy verdict would report it as "not applicable".
        structurally_applicable = validation["demand_post_calibration_rows"].gt(0)
        validation["structural_integrity_status"] = np.where(
            ~structurally_applicable,
            _CALIBRATION_STATUS_NOT_APPLICABLE,
            np.where(
                checks_pass, _CALIBRATION_STATUS_PASSED, _CALIBRATION_STATUS_FAILED
            ),
        )
        validation["predictive_validation_status"] = np.where(
            validation_scenarios.isin(overlay_scenarios),
            _PREDICTIVE_STATUS_NOT_AVAILABLE,
            _PREDICTIVE_STATUS_RAW_REPLAY,
        )
        validation["raw_fitted_replay_validation_status"] = _CALIBRATION_STATUS_PASSED
        validation["validation_scope_note"] = np.where(
            validation_scenarios.isin(overlay_scenarios),
            _STRUCTURAL_VALIDATION_SCOPE_NOTE,
            "Fitted replay validated on its own backtest evidence.",
        )
        replay.validation_report = validation
    return replay


def _input_change_audit(
    base_rows: pd.DataFrame,
    scenario_rows: pd.DataFrame,
    base_scenario_name: str,
    *,
    conflict_paths: pd.DataFrame,
) -> pd.DataFrame:
    """Audit every configured petrol/diesel ratio and its model-input value."""

    base = base_rows.set_index(["stream", "canonical_period"])
    scenario = scenario_rows.set_index(["scenario_name", "stream", "canonical_period"])
    rows: list[dict[str, Any]] = []
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        path = _conflict_path_rows(
            Path(__file__).resolve().parents[1],
            level,
            scenario_paths=conflict_paths,
        )
        for path_row in path.itertuples(index=False):
            period = str(path_row.period)
            for stream, field in _STREAM_PRICE_FIELDS.items():
                key = (stream, period)
                scenario_key = (scenario_name, stream, period)
                if key not in base.index or scenario_key not in scenario.index:
                    raise ValueError(
                        f"Conflict input audit is missing {level}/{stream}/{period}."
                    )
                base_value = float(
                    pd.to_numeric(pd.Series([base.at[key, field]]), errors="coerce").iloc[0]
                )
                scenario_value = float(
                    pd.to_numeric(
                        pd.Series([scenario.at[scenario_key, field]]), errors="coerce"
                    ).iloc[0]
                )
                price_kind = "petrol" if stream == "PED" else "diesel"
                configured_ratio = float(getattr(path_row, f"{price_kind}_ratio"))
                multiplier = scenario_value / base_value
                if not np.isclose(multiplier, configured_ratio, rtol=1e-12, atol=1e-12):
                    raise ValueError(
                        f"Conflict input audit ratio mismatch for {level}/{stream}/{period}."
                    )
                rows.append(
                    {
                        "base_scenario_name": base_scenario_name,
                        "scenario_name": scenario_name,
                        "scenario_display_name": conflict_trace_name(level),
                        "severity": level,
                        "stream": stream,
                        "canonical_period": period,
                        "field": field,
                        "shock_component": f"conflict_{price_kind}_price_ratio",
                        "base_value": base_value,
                        "scenario_value": scenario_value,
                        "multiplier": multiplier,
                        "configured_ratio": configured_ratio,
                        "delta": scenario_value - base_value,
                        "input_changed": not np.isclose(
                            scenario_value, base_value, rtol=1e-12, atol=1e-12
                        ),
                        "base_nominal_cpl": float(
                            getattr(path_row, f"base_{price_kind}_cpl")
                        ),
                        "scenario_nominal_cpl": float(
                            getattr(path_row, f"scenario_{price_kind}_cpl")
                        ),
                        "observation_status": str(path_row.observation_status),
                        "source_note": str(path_row.source_note),
                        "source_url": str(path_row.source_url),
                        "source_workbook_cell": str(path_row.source_workbook_cell),
                        "source_workbook_sha256": str(path_row.source_workbook_sha256),
                        "fed_12c_embedded": False,
                        "scenario_note": conflict_scenario_note(level),
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["severity", "stream", "canonical_period"], kind="stable"
    ).reset_index(drop=True)


def _quarterly_factor_audit(
    replay: ScenarioInputForecastReplayResult,
    *,
    base_scenario_name: str,
) -> pd.DataFrame:
    source = replay.future_forecasts.copy()
    required = {"scenario_name", "stream", "target_period", "forecast"}
    missing = required.difference(source.columns)
    if missing:
        raise ValueError("Replay forecasts are missing required columns: " + ", ".join(sorted(missing)))
    source["forecast_numeric"] = pd.to_numeric(source["forecast"], errors="coerce")
    frames: list[pd.DataFrame] = []
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        values = source[
            source["scenario_name"].astype(str).isin([base_scenario_name, scenario_name])
        ].pivot_table(
            index=["stream", "target_period"],
            columns="scenario_name",
            values="forecast_numeric",
            aggfunc="first",
        ).reset_index()
        if base_scenario_name not in values or scenario_name not in values:
            raise ValueError(
                f"Replay did not produce both Base and {level} conflict forecasts."
            )
        values = values.rename(
            columns={
                base_scenario_name: "base_value",
                scenario_name: "scenario_value",
                "target_period": "period",
            }
        ).dropna(subset=["base_value", "scenario_value"])
        if values.empty or (values["base_value"].abs() <= 1e-12).any():
            raise ValueError(
                f"Replay produced empty or zero Base forecasts for {level} factors."
            )
        values["factor"] = values["scenario_value"] / values["base_value"]
        values["delta"] = values["scenario_value"] - values["base_value"]
        values["series_id"] = values["stream"].astype(str).map(_STREAM_SERIES_IDS)
        values["time_grain"] = "quarterly"
        values["scenario_name"] = scenario_name
        values["trace_name"] = conflict_trace_name(level)
        values["severity"] = level
        values["scenario_note"] = conflict_scenario_note(level)
        frames.append(values)
    pivot = pd.concat(frames, ignore_index=True, sort=False)
    return pivot[
        [
            "scenario_name",
            "trace_name",
            "severity",
            "time_grain",
            "period",
            "stream",
            "series_id",
            "base_value",
            "scenario_value",
            "factor",
            "delta",
            "scenario_note",
        ]
    ].sort_values(["severity", "stream", "period"], kind="stable").reset_index(drop=True)


_NON_ICE_RUC_ACTIVITY_REVENUE_PAIRS = {
    "light_bev_ruc_net_km": "light_bev_ruc_net_revenue",
    "phev_ruc_net_km": "phev_ruc_net_revenue",
    "heavy_bev_ruc_net_km": "heavy_bev_ruc_net_revenue",
}


def _isolate_non_ice_annual_activity(
    annual_bridge: pd.DataFrame,
    *,
    base_scenario_name: str,
) -> pd.DataFrame:
    """Keep BEV/PHEV activity fixed while assigning Light demand to ICE.

    The governed Light and Heavy elasticities are explicitly retail-diesel
    elasticities. They therefore move conventional Light/Heavy activity, not
    BEV or PHEV activity. The annual migration bridge can otherwise spread a
    change in the modelled total Light universe across all three Light
    propulsion classes. This repair preserves each scenario's modelled Light
    total, fixes BEV/PHEV activity to Base, assigns the full total delta to
    conventional Light, and retains the Base effective rate until the policy
    repricing layer is applied exactly once.
    """

    if annual_bridge is None or annual_bridge.empty:
        return annual_bridge
    required_columns = {"scenario_name", "series_id", "value"}
    missing = required_columns.difference(annual_bridge.columns)
    if missing:
        raise ValueError(
            "Annual bridge is missing non-ICE isolation columns: "
            + ", ".join(sorted(missing))
        )
    fy_column = "FY" if "FY" in annual_bridge.columns else "june_year"
    if fy_column not in annual_bridge.columns:
        raise ValueError("Annual bridge requires an FY or june_year column.")

    out = annual_bridge.copy()
    out["demand_activity_isolation_basis"] = ""
    out["demand_activity_isolation_applied"] = False
    target_scenarios = set(POLICY_PATH_IDS).difference({base_scenario_name})
    key_columns = [fy_column]
    if "fed_path" in out.columns:
        key_columns.append("fed_path")
    required_series = {
        _CURRENT_LIGHT_TOTAL_SERIES_ID,
        "light_ruc_net_km",
        "light_ruc_net_revenue",
        *_NON_ICE_RUC_ACTIVITY_REVENUE_PAIRS,
        *_NON_ICE_RUC_ACTIVITY_REVENUE_PAIRS.values(),
    }

    base = out[out["scenario_name"].astype(str).eq(base_scenario_name)].copy()
    if base.empty:
        raise ValueError("Annual bridge has no Base rows for non-ICE isolation.")
    base_groups: dict[tuple[Any, ...], dict[str, float]] = {}
    for key, group in base.groupby(key_columns, dropna=False, sort=False):
        key_tuple = key if isinstance(key, tuple) else (key,)
        selected = group[group["series_id"].astype(str).isin(required_series)]
        if selected["series_id"].astype(str).duplicated().any():
            raise ValueError(
                f"Base annual bridge has duplicate non-ICE isolation rows for {key_tuple}."
            )
        values: dict[str, float] = {}
        for _, row in selected.iterrows():
            value = pd.to_numeric(
                pd.Series([row["value"]]), errors="coerce"
            ).iloc[0]
            if pd.isna(value) or not np.isfinite(float(value)):
                raise ValueError(
                    f"Base annual bridge has a non-numeric non-ICE value for "
                    f"{row['series_id']}/{key_tuple}."
                )
            values[str(row["series_id"])] = float(value)
        missing_series = required_series.difference(values)
        if missing_series:
            raise ValueError(
                f"Base annual bridge is missing non-ICE isolation rows for "
                f"{key_tuple}: {sorted(missing_series)}."
            )
        base_groups[key_tuple] = values

    original_totals = out[
        out["scenario_name"].astype(str).isin(target_scenarios)
        & out["series_id"].astype(str).eq(_CURRENT_LIGHT_TOTAL_SERIES_ID)
    ].copy()
    for scenario_name in sorted(target_scenarios):
        scenario_rows = out[out["scenario_name"].astype(str).eq(scenario_name)]
        if scenario_rows.empty:
            raise ValueError(
                f"Annual bridge has no rows for policy path {scenario_name!r}."
            )
        for key, group in scenario_rows.groupby(
            key_columns, dropna=False, sort=False
        ):
            key_tuple = key if isinstance(key, tuple) else (key,)
            if key_tuple not in base_groups:
                raise ValueError(
                    f"Annual bridge has no matched Base non-ICE rows for "
                    f"{scenario_name}/{key_tuple}."
                )
            selected = group[group["series_id"].astype(str).isin(required_series)]
            if selected["series_id"].astype(str).duplicated().any():
                raise ValueError(
                    f"Annual bridge has duplicate non-ICE rows for "
                    f"{scenario_name}/{key_tuple}."
                )
            scenario_indices = {
                str(out.at[index, "series_id"]): index for index in selected.index
            }
            missing_series = required_series.difference(scenario_indices)
            if missing_series:
                raise ValueError(
                    f"Annual bridge is missing non-ICE isolation rows for "
                    f"{scenario_name}/{key_tuple}: {sorted(missing_series)}."
                )
            base_values = base_groups[key_tuple]

            def scenario_value(series_id: str) -> float:
                value = pd.to_numeric(
                    pd.Series([out.at[scenario_indices[series_id], "value"]]),
                    errors="coerce",
                ).iloc[0]
                if pd.isna(value) or not np.isfinite(float(value)):
                    raise ValueError(
                        f"Annual bridge has a non-numeric {series_id} value for "
                        f"{scenario_name}/{key_tuple}."
                    )
                return float(value)

            scenario_total = scenario_value(_CURRENT_LIGHT_TOTAL_SERIES_ID)
            base_total = base_values[_CURRENT_LIGHT_TOTAL_SERIES_ID]
            base_light_km = base_values["light_ruc_net_km"]
            adjusted_light_km = base_light_km + scenario_total - base_total
            if adjusted_light_km <= 0.0:
                raise ValueError(
                    f"Non-ICE isolation made conventional Light activity non-positive "
                    f"for {scenario_name}/{key_tuple}."
                )
            if base_light_km <= 0.0:
                raise ValueError(
                    f"Base conventional Light activity must be positive for {key_tuple}."
                )
            adjusted_light_revenue = (
                adjusted_light_km
                * base_values["light_ruc_net_revenue"]
                / base_light_km
            )
            out.at[scenario_indices["light_ruc_net_km"], "value"] = (
                adjusted_light_km
            )
            out.at[scenario_indices["light_ruc_net_revenue"], "value"] = (
                adjusted_light_revenue
            )
            for (
                activity_series,
                revenue_series,
            ) in _NON_ICE_RUC_ACTIVITY_REVENUE_PAIRS.items():
                out.at[scenario_indices[activity_series], "value"] = base_values[
                    activity_series
                ]
                out.at[scenario_indices[revenue_series], "value"] = base_values[
                    revenue_series
                ]
            affected = selected.index
            out.loc[affected, "demand_activity_isolation_applied"] = True
            out.loc[affected, "demand_activity_isolation_basis"] = (
                "diesel_elasticity_to_conventional_ice_only; "
                "bev_phev_activity_fixed_to_base"
            )

    out = _replay_annual_formula_definitions(out)
    total_keys = [*key_columns, "scenario_name"]
    after_totals = out[
        out["scenario_name"].astype(str).isin(target_scenarios)
        & out["series_id"].astype(str).eq(_CURRENT_LIGHT_TOTAL_SERIES_ID)
    ]
    before = original_totals.set_index(total_keys)["value"].sort_index()
    after = after_totals.set_index(total_keys)["value"].sort_index()
    if not before.index.equals(after.index) or not np.allclose(
        pd.to_numeric(before, errors="coerce"),
        pd.to_numeric(after, errors="coerce"),
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("Non-ICE isolation altered the modelled Light total.")
    return out


def _annual_bridge_and_factors(
    replay: ScenarioInputForecastReplayResult,
    *,
    replay_inputs: pd.DataFrame,
    repo_root: Path,
    base_scenario_name: str,
    latest_actual_period: str | None = None,
    require_conflict_factors: bool = True,
    isolate_non_ice_activity: bool = True,
    bridge_vintage_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    quarterly = forecast_chart_rows_for_display(
        replay.future_forecasts,
        repo_root=repo_root,
        latest_actual_period=latest_actual_period,
    )
    if quarterly.empty:
        raise ValueError("Replay produced no chartable quarterly rows.")
    quarterly["time_grain"] = "quarterly"
    quarterly["metric_type"] = "activity"
    scenario_roles = {
        base_scenario_name: "basecase",
        "historical_actual": "actual",
        _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME: "comparison",
        **{
            conflict_scenario_name(level): "comparison"
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
        },
        **{
            variant_name: "comparison"
            for variant_name in _POLICY_REFERENCE_SCENARIOS
        },
    }
    quarterly["scenario_role"] = (
        quarterly["scenario_name"].astype(str).map(scenario_roles).fillna("")
    )

    # The replay must bridge activity to revenue through the SAME
    # bridge-assumption vintage the committed pack was built with. Reading the
    # MBU26 spine here while the pack carries BEFU26 rates silently mixes
    # vintages and breaks the Current RUC identity by ~1e-3 (Total RUC no
    # longer equals class leaves less administration).
    #
    # ``bridge_vintage_id`` comes from the manifest of the pack being replayed
    # and is authoritative; the registry default is consulted only when no
    # pack-specific bridge was supplied (e.g. building a brand-new pack).
    from .official_vintage import default_bridge_vintage_id, load_official_vintage

    bridge_vid = str(bridge_vintage_id or default_bridge_vintage_id(repo_root))
    bridge_pack = load_official_vintage(bridge_vid, repo_root=repo_root)
    if bridge_pack is None or bridge_pack.official_annual.empty:
        raise ValueError(
            f"The committed {bridge_vid} official annual pack is required to bridge "
            "replay activity into revenue."
        )
    annual = current_forecast_annual_from_mbu26(
        current_outlook_chart_rows=quarterly,
        mbu26_official_annual=bridge_pack.official_annual,
        scenario_input_wide=replay_inputs,
        migration_lambda_reference_scenario=base_scenario_name,
    )
    if annual.empty:
        raise ValueError(
            "The fixed-finalist replay could not be bridged to annual Revenue Outlook rows."
        )
    if isolate_non_ice_activity:
        annual = _isolate_non_ice_annual_activity(
            annual,
            base_scenario_name=base_scenario_name,
        )
    if not require_conflict_factors:
        return annual.reset_index(drop=True), pd.DataFrame()

    values = annual.copy()
    values["value_numeric"] = pd.to_numeric(values["value"], errors="coerce")
    factor_frames: list[pd.DataFrame] = []
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        pivot = values[
            values["scenario_name"].astype(str).isin([base_scenario_name, scenario_name])
        ].pivot_table(
            index=["FY", "series_id"],
            columns="scenario_name",
            values="value_numeric",
            aggfunc="first",
        ).reset_index()
        if base_scenario_name not in pivot or scenario_name not in pivot:
            raise ValueError(
                f"Annual bridge did not produce both Base and {level} conflict rows."
            )
        factors = pivot.rename(
            columns={
                base_scenario_name: "base_value",
                scenario_name: "scenario_value",
                "FY": "june_year",
            }
        ).dropna(subset=["base_value", "scenario_value"])
        factors["factor"] = np.where(
            factors["base_value"].abs() > 1e-12,
            factors["scenario_value"] / factors["base_value"],
            1.0,
        )
        factors["delta"] = factors["scenario_value"] - factors["base_value"]
        factors["period"] = factors["june_year"].astype(int).map(
            lambda value: f"FY{value}"
        )
        factors["time_grain"] = "june_year"
        factors["scenario_name"] = scenario_name
        factors["trace_name"] = conflict_trace_name(level)
        factors["severity"] = level
        factors["scenario_note"] = conflict_scenario_note(level)
        factor_frames.append(factors)
    factors = pd.concat(factor_frames, ignore_index=True, sort=False)
    factors = factors[
        [
            "scenario_name",
            "trace_name",
            "severity",
            "time_grain",
            "period",
            "june_year",
            "series_id",
            "base_value",
            "scenario_value",
            "factor",
            "delta",
            "scenario_note",
        ]
    ].sort_values(
        ["severity", "series_id", "june_year"], kind="stable"
    ).reset_index(drop=True)
    return annual.reset_index(drop=True), factors


def _validate_complete_numeric_replay(
    replay: ScenarioInputForecastReplayResult,
    *,
    replay_inputs: pd.DataFrame,
    scenario_names: tuple[str, ...],
) -> None:
    """Require every governed scenario/stream/quarter before annual bridging."""

    forecasts = replay.future_forecasts
    required_forecast_columns = {"scenario_name", "stream", "target_period", "forecast"}
    if forecasts is None or forecasts.empty or required_forecast_columns.difference(forecasts.columns):
        raise ValueError("Fixed-finalist conflict replay produced no usable forecast rows.")

    # Per-stream seam: scenario quarters at or before a stream's latest
    # accepted actual are covered by canonical history, never re-forecast.
    from .forecast_runner import quarter_sort_key as _qkey
    from .forecast_runner import stream_latest_accepted_periods as _stream_latest

    try:
        accepted_cutoffs = _stream_latest(None)
    except Exception:
        accepted_cutoffs = {}

    problems: list[str] = []
    for scenario_name in scenario_names:
        scenario_inputs = replay_inputs[
            replay_inputs["scenario_name"].astype(str).eq(scenario_name)
        ].copy()
        scenario_forecasts = forecasts[
            forecasts["scenario_name"].astype(str).eq(scenario_name)
        ].copy()
        for stream in _STREAM_SERIES_IDS:
            expected_periods = set(
                scenario_inputs.loc[
                    scenario_inputs["stream"].astype(str).eq(stream), "canonical_period"
                ].dropna().astype(str)
            )
            cutoff = accepted_cutoffs.get(str(stream))
            if cutoff:
                expected_periods = {
                    period for period in expected_periods if _qkey(period) > _qkey(cutoff)
                }
            stream_forecasts = scenario_forecasts[
                scenario_forecasts["stream"].astype(str).eq(stream)
            ].copy()
            numeric = pd.to_numeric(stream_forecasts.get("forecast"), errors="coerce")
            numeric_periods = expected_periods.intersection(
                stream_forecasts.loc[numeric.notna(), "target_period"].dropna().astype(str)
            )
            missing_periods = sorted(expected_periods.difference(numeric_periods))
            if expected_periods and not missing_periods:
                continue

            gap_codes = sorted(
                value
                for value in stream_forecasts.get("gap_code", pd.Series(dtype=object))
                .dropna()
                .astype(str)
                .unique()
                .tolist()
                if value
            )
            reason = ""
            if "gap_reason" in stream_forecasts:
                reasons = [
                    value
                    for value in stream_forecasts["gap_reason"].dropna().astype(str).unique().tolist()
                    if value
                ]
                reason = reasons[0] if reasons else ""
            detail = (
                f"{scenario_name}/{stream}: {len(numeric_periods)} of {len(expected_periods)} "
                "required quarters are numeric"
            )
            if gap_codes:
                detail += f" (gap: {', '.join(gap_codes)})"
            if reason:
                detail += f"; {reason}"
            problems.append(detail)

    if problems:
        raise ValueError(
            "Fixed-finalist conflict replay lacks complete numeric coverage: "
            + " | ".join(problems)
        )


def _normalise_annual_policy_factors(
    annual_fed_policy_factors: dict[str, dict[int, float]],
) -> dict[str, dict[int, float]]:
    """Map app cache keys onto the public rate-path policy state names."""

    aliases: dict[str, str] = {}
    for spec in _NON_PUBLISHED_POLICY_SPECS:
        aliases[spec.state_id] = spec.calculation_state_id
        aliases[spec.calculation_state_id] = spec.calculation_state_id
    normalised: dict[str, dict[int, float]] = {}
    for key, factors in (annual_fed_policy_factors or {}).items():
        state = aliases.get(str(key))
        if state is None:
            continue
        if not isinstance(factors, dict):
            raise TypeError(f"Annual FED policy factors for {key!r} must be a dict keyed by fiscal year.")
        normalised[state] = {
            int(fy): float(factor)
            for fy, factor in factors.items()
            if pd.notna(fy) and pd.notna(factor)
        }
    return normalised


def _replay_annual_formula_definitions(rows: pd.DataFrame) -> pd.DataFrame:
    """Recalculate every governed aggregate while retaining fixed leaves."""

    out = rows.copy()
    fy_column = "FY" if "FY" in out.columns else "june_year"
    if fy_column not in out.columns:
        raise ValueError("Annual bridge requires an FY or june_year column.")
    grouping = ["scenario_name", fy_column]
    if "fed_path" in out.columns:
        grouping.append("fed_path")
    for _, group in out.groupby(grouping, dropna=False, sort=False):
        values = {
            str(out.at[index, "series_id"]): float(value)
            for index in group.index
            if pd.notna(
                value := pd.to_numeric(pd.Series([out.at[index, "value"]]), errors="coerce").iloc[0]
            )
        }
        for formula in FORMULA_DEFINITIONS:
            output = str(formula["output_series_id"])
            terms = tuple(formula["terms"])
            if any(str(series_id) not in values for series_id, _ in terms):
                continue
            calculated = sum(values[str(series_id)] * float(sign) for series_id, sign in terms)
            output_indices = [
                index
                for index in group.index
                if str(out.at[index, "series_id"]) == output
            ]
            if not output_indices:
                continue
            for index in output_indices:
                out.at[index, "value"] = calculated
            values[output] = calculated
    return out


def apply_policy_rate_factors_to_annual_bridge(
    annual_bridge: pd.DataFrame,
    annual_fed_policy_factors: dict[str, dict[int, float]],
    *,
    base_scenario_name: str = _BASE_SCENARIO_NAME,
) -> pd.DataFrame:
    """Append rate-correct policy variants to the full annual bridge.

    ``annual_fed_policy_factors`` accepts the app cache keys ``delayed_6m``
    and ``off`` as well as the public rate-path states ``delay_6m`` and
    ``no_uplift``.  In each policy variant the FED factor reprices gross PED
    and every RUC revenue leaf (conventional, BEV and PHEV).  The governed
    formulas are then replayed in dependency order.  Administration charges
    and refunds are never scaled and therefore remain fixed inputs.
    """

    if annual_bridge is None or annual_bridge.empty:
        return annual_bridge
    required = {"scenario_name", "series_id", "value"}
    missing = required.difference(annual_bridge.columns)
    if missing:
        raise ValueError("Annual bridge is missing required columns: " + ", ".join(sorted(missing)))
    fy_column = "FY" if "FY" in annual_bridge.columns else "june_year"
    if fy_column not in annual_bridge.columns:
        raise ValueError("Annual bridge requires an FY or june_year column.")
    factors_by_state = _normalise_annual_policy_factors(annual_fed_policy_factors)

    variant_names = {
        scenario_name
        for names_by_family in POLICY_VARIANT_SCENARIO_NAMES.values()
        for scenario_name in names_by_family.values()
    }
    original = annual_bridge.copy()
    source = original[
        ~annual_bridge["scenario_name"].astype(str).isin(variant_names)
    ].copy()
    source["policy_path_id"] = source["scenario_name"].astype(str).map(POLICY_PATH_IDS).fillna("")
    source.loc[
        source["scenario_name"].astype(str).eq(base_scenario_name), "policy_path_id"
    ] = "baseline_published"
    published_names = {
        base_scenario_name,
        *(conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS),
    }
    source["policy_state"] = np.where(
        source["scenario_name"].astype(str).isin(published_names), "published", ""
    )
    source["policy_rate_factor"] = 1.0
    base_sources = {
        "baseline": str(base_scenario_name),
        **{
            level: conflict_scenario_name(level)
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
        },
    }
    display_names = {}
    for spec in _NON_PUBLISHED_POLICY_SPECS:
        display_names[BASE_POLICY_VARIANT_IDS[spec.calculation_state_id]] = (
            f"Current finalist Base case ({spec.short_policy_phrase}; PED pump + proportional RUC)"
        )
        for level in CONFLICT_FUEL_SCENARIO_LEVELS:
            display_names[
                conflict_policy_variant_name(level, spec.calculation_state_id)
            ] = f"{conflict_trace_name(level)} ({spec.short_policy_phrase})"
    repriced_leaves = {"gross_ped_revenue", *_RUC_REVENUE_LEAVES}

    # Fiscal year the uplift lands in (2027Q1 -> FY2027), derived rather than
    # written as a literal so the guards below can never drift from the
    # governed start quarter.
    uplift_fy = int(_fiscal_year_from_quarter(FED_UPLIFT_START_PERIOD))

    def _shared_window_years(spec) -> tuple[int, ...]:
        """Fiscal years wholly inside a state's no-uplift-priced window.

        A year is "shared" when every uplift-affected quarter it contains
        carries the no-uplift rate under this state, so its bridge answer is
        common to every state whose window also covers it. The no-uplift
        state shares only FY2027 with the six-month replay - exactly the
        production anchoring - because its later years have no rejoining
        counterpart.
        """
        if spec.is_no_uplift:
            return (uplift_fy,)
        start_serial = quarter_serial(spec.start_period)
        years: list[int] = []
        year = uplift_fy
        while quarter_serial(f"{year}Q2") < start_serial:
            years.append(year)
            year += 1
        return tuple(years)

    def _anchor_source_scenario(family: str, shared_year: int) -> str:
        """The replay whose bridge is authoritative for one shared year.

        FY2027 anchors to the six-month replay: its whole-horizon fleet
        smoothing sees a published FY2028+ path, so its FY2027 is free of
        later-divergence leakage (the production rule). Later shared years
        anchor to the no-uplift replay, whose pricing is identical to every
        deferral still inside its window over those years.
        """
        if shared_year == uplift_fy:
            return POLICY_VARIANT_SCENARIO_NAMES[FED_POLICY_STATE_DELAYED_6M][family]
        return POLICY_VARIANT_SCENARIO_NAMES[FED_POLICY_STATE_NO_UPLIFT][family]

    variants: list[pd.DataFrame] = []
    for state_spec in _NON_PUBLISHED_POLICY_SPECS:
        state = state_spec.calculation_state_id
        if state not in factors_by_state:
            continue
        state_factors = factors_by_state[state]
        for family, source_name in base_sources.items():
            variant_name = POLICY_VARIANT_SCENARIO_NAMES[state][family]
            # Start from the variant's own fixed-finalist replay bridge.  It
            # already contains the activity response to proportionately
            # changed RUC input prices; cloning the published source here
            # would silently discard that modelled response.
            variant = original[original["scenario_name"].astype(str).eq(variant_name)].copy()
            if variant.empty:
                raise ValueError(f"Annual bridge is missing policy replay scenario {variant_name!r}.")

            # The policy input first changes in 2027Q1.  Some annual bridge
            # routines use whole-horizon fleet smoothing, which can otherwise
            # leak a future policy change back into FY2026.  Copy all pre-
            # policy values exactly from the corresponding published replay.
            published = source[source["scenario_name"].astype(str).eq(source_name)].copy()
            identity_columns = [fy_column, "series_id"]
            if "fed_path" in variant.columns and "fed_path" in published.columns:
                identity_columns.append("fed_path")
            published_lookup = (
                published.drop_duplicates(identity_columns, keep="first")
                .set_index(identity_columns)["value"]
                .to_dict()
            )
            variant_fy = pd.to_numeric(variant[fy_column], errors="coerce")
            for index in variant.index[variant_fy.lt(uplift_fy)]:
                key = tuple(variant.at[index, column] for column in identity_columns)
                if key in published_lookup:
                    variant.at[index, "value"] = published_lookup[key]

            # States that share a no-uplift-priced window must carry one
            # shared bridge answer over the years wholly inside it. Whole-
            # horizon fleet smoothing must not let each state's later, post-
            # window divergence leak backwards into a shared year, so those
            # years are anchored to the authoritative shared replay. For the
            # no-uplift state this is exactly the production rule: FY2027 is
            # anchored to the matching six-month replay.
            for shared_year in _shared_window_years(state_spec):
                anchor_name = _anchor_source_scenario(family, shared_year)
                if anchor_name == variant_name:
                    continue  # the six-month replay is its own FY2027 anchor
                anchor = original[
                    original["scenario_name"].astype(str).eq(anchor_name)
                ].copy()
                if anchor.empty:
                    raise ValueError(
                        f"Annual bridge is missing anchor replay scenario {anchor_name!r} "
                        f"for the shared FY{shared_year} window of {variant_name!r}."
                    )
                anchor_lookup = (
                    anchor.drop_duplicates(identity_columns, keep="first")
                    .set_index(identity_columns)["value"]
                    .to_dict()
                )
                for index in variant.index[variant_fy.eq(shared_year)]:
                    key = tuple(variant.at[index, column] for column in identity_columns)
                    if key in anchor_lookup:
                        variant.at[index, "value"] = anchor_lookup[key]

            variant["policy_path_id"] = POLICY_PATH_IDS[variant_name]
            variant["policy_state"] = state
            variant["policy_rate_factor"] = 1.0
            if "trace_name" in variant.columns:
                variant["trace_name"] = display_names[variant_name]
            if "scenario_display_name" in variant.columns:
                variant["scenario_display_name"] = display_names[variant_name]
            fy_numeric = pd.to_numeric(variant[fy_column], errors="coerce")
            series = variant["series_id"].astype(str)
            for fy, factor in state_factors.items():
                mask = fy_numeric.eq(int(fy)) & series.isin(repriced_leaves)
                numeric = pd.to_numeric(variant.loc[mask, "value"], errors="coerce")
                if numeric.isna().any():
                    raise ValueError(
                        f"Policy variant {variant_name!r} contains non-numeric revenue leaves in FY{fy}."
                    )
                variant.loc[mask, "value"] = numeric.to_numpy(dtype=float) * float(factor)
                variant.loc[fy_numeric.eq(int(fy)), "policy_rate_factor"] = float(factor)
            variant = _replay_annual_formula_definitions(variant)
            # Formula replay can introduce sub-cent floating-point noise even
            # when the underlying pre-policy row was copied.  Restore those
            # rows once more so the no-leakage invariant is bit-for-bit exact.
            for index in variant.index[variant_fy.lt(uplift_fy)]:
                key = tuple(variant.at[index, column] for column in identity_columns)
                if key in published_lookup:
                    variant.at[index, "value"] = published_lookup[key]
            variants.append(variant)
    return pd.concat([source, *variants], ignore_index=True, sort=False)


def _fiscal_year_from_quarter(period: Any) -> int | pd.NA:
    year, quarter = _canonical_quarter_order(period)
    if year <= 0 or quarter <= 0:
        return pd.NA
    return year + 1 if quarter >= 3 else year


def build_policy_scenario_pair_factors(
    replay: ScenarioInputForecastReplayResult,
    policy_adjusted_annual_bridge: pd.DataFrame,
    *,
    base_scenario_name: str = _BASE_SCENARIO_NAME,
) -> pd.DataFrame:
    """Build quarterly activity and annual bridge factors for policy pairs."""

    pairs: list[tuple[str, str, str, str, str]] = []
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        pairs.append(
            (
                f"{level}_published",
                conflict_scenario_name(level),
                base_scenario_name,
                "published",
                level,
            )
        )
    # One baseline pair per non-published governed state, registry-driven.
    state_suffix = {
        spec.calculation_state_id: spec.pair_state_suffix
        for spec in _NON_PUBLISHED_POLICY_SPECS
    }
    baseline_variants = {
        spec.calculation_state_id: BASE_POLICY_VARIANT_IDS[spec.calculation_state_id]
        for spec in _NON_PUBLISHED_POLICY_SPECS
    }
    pairs.extend(
        (
            f"baseline_{suffix}",
            baseline_variants[state],
            base_scenario_name,
            state,
            "baseline",
        )
        for state, suffix in state_suffix.items()
    )
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        published_name = conflict_scenario_name(level)
        for state, suffix in state_suffix.items():
            variant_name = conflict_policy_variant_name(level, state)
            pairs.extend(
                [
                    (
                        f"{level}_{suffix}",
                        variant_name,
                        published_name,
                        state,
                        level,
                    ),
                    (
                        f"{level}_vs_baseline_{suffix}",
                        variant_name,
                        baseline_variants[state],
                        state,
                        level,
                    ),
                ]
            )
    # Compatibility pair IDs for the former singular Iran/Medium trace.
    for pair_id, replacement_id in {
        "iran_published": "medium_published",
        "iran_delayed_6m": "medium_delayed_6m",
        "iran_vs_baseline_delayed_6m": "medium_vs_baseline_delayed_6m",
        "iran_no_uplift": "medium_no_uplift",
        "iran_vs_baseline_no_uplift": "medium_vs_baseline_no_uplift",
    }.items():
        replacement = next(pair for pair in pairs if pair[0] == replacement_id)
        pairs.append((pair_id, *replacement[1:]))
    columns = [
        "pair_id",
        "severity",
        "policy_state",
        "time_grain",
        "period",
        "june_year",
        "stream",
        "series_id",
        "numerator_scenario_name",
        "denominator_scenario_name",
        "base_value",
        "scenario_value",
        "factor",
        "delta",
        "transformation_basis",
    ]
    frames: list[pd.DataFrame] = []

    quarterly = replay.future_forecasts.copy()
    quarterly["_value"] = pd.to_numeric(quarterly.get("forecast"), errors="coerce")
    for pair_id, numerator, denominator, state, severity in pairs:
        values = quarterly[
            quarterly["scenario_name"].astype(str).isin([numerator, denominator])
        ].pivot_table(
            index=["stream", "target_period"],
            columns="scenario_name",
            values="_value",
            aggfunc="first",
        ).reset_index()
        if numerator not in values.columns or denominator not in values.columns:
            raise ValueError(f"Quarterly replay is missing one or both scenarios for pair {pair_id!r}.")
        values = values.dropna(subset=[numerator, denominator]).copy()
        values["pair_id"] = pair_id
        values["severity"] = severity
        values["policy_state"] = state
        values["time_grain"] = "quarterly"
        values["period"] = values["target_period"].astype(str)
        values["june_year"] = values["period"].map(_fiscal_year_from_quarter)
        values["series_id"] = values["stream"].astype(str).map(_STREAM_SERIES_IDS)
        values["numerator_scenario_name"] = numerator
        values["denominator_scenario_name"] = denominator
        values["base_value"] = pd.to_numeric(values[denominator], errors="coerce")
        values["scenario_value"] = pd.to_numeric(values[numerator], errors="coerce")
        values["factor"] = np.where(
            values["base_value"].abs() > 1e-12,
            values["scenario_value"] / values["base_value"],
            1.0,
        )
        values["delta"] = values["scenario_value"] - values["base_value"]
        values["transformation_basis"] = "fixed_finalist_quarterly_replay_pair"
        frames.append(values[columns])

    annual = policy_adjusted_annual_bridge.copy()
    annual["_value"] = pd.to_numeric(annual.get("value"), errors="coerce")
    fy_column = "FY" if "FY" in annual.columns else "june_year"
    for pair_id, numerator, denominator, state, severity in pairs:
        values = annual[
            annual["scenario_name"].astype(str).isin([numerator, denominator])
        ].pivot_table(
            index=[fy_column, "series_id"],
            columns="scenario_name",
            values="_value",
            aggfunc="first",
        ).reset_index()
        if numerator not in values.columns or denominator not in values.columns:
            raise ValueError(f"Annual bridge is missing one or both scenarios for pair {pair_id!r}.")
        values = values.dropna(subset=[numerator, denominator]).copy()
        values["pair_id"] = pair_id
        values["severity"] = severity
        values["policy_state"] = state
        values["time_grain"] = "june_year"
        values["june_year"] = pd.to_numeric(values[fy_column], errors="coerce").astype("Int64")
        values["period"] = values["june_year"].map(
            lambda fy: f"FY{int(fy)}" if pd.notna(fy) else ""
        )
        values["stream"] = ""
        values["numerator_scenario_name"] = numerator
        values["denominator_scenario_name"] = denominator
        values["base_value"] = pd.to_numeric(values[denominator], errors="coerce")
        values["scenario_value"] = pd.to_numeric(values[numerator], errors="coerce")
        values["factor"] = np.where(
            values["base_value"].abs() > 1e-12,
            values["scenario_value"] / values["base_value"],
            1.0,
        )
        values["delta"] = values["scenario_value"] - values["base_value"]
        values["transformation_basis"] = "policy_adjusted_annual_bridge_pair"
        frames.append(values[columns])
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=columns)


def _scenario_clone_with_identity(
    rows: pd.DataFrame,
    *,
    scenario_name: str,
    role: str,
    display_name: str,
) -> pd.DataFrame:
    """Clone scenario rows under an internal, explicitly labelled identity."""

    out = rows.copy()
    out["scenario_name"] = str(scenario_name)
    out["role"] = str(role)
    if "scenario_role" in out.columns:
        out["scenario_role"] = str(role)
    out["scenario_display_name"] = str(display_name)
    if "source_artifact" in out.columns:
        out["source_artifact"] = (
            out["source_artifact"].fillna("").astype(str)
            + f"; runtime_macro_shadow:{scenario_name}"
        ).str.strip("; ")
    return out.reset_index(drop=True)


def _baseline_macro_factor_frames(
    price_only_replay: ScenarioInputForecastReplayResult,
    price_only_annual_bridge: pd.DataFrame,
    *,
    base_scenario_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Treasury-Base versus the legacy input path at quarter and FY grain."""

    quarterly_source = price_only_replay.future_forecasts.copy()
    required_quarterly = {
        "scenario_name",
        "stream",
        "target_period",
        "forecast",
    }
    missing = required_quarterly.difference(quarterly_source.columns)
    if missing:
        raise ValueError(
            "Price-only replay cannot build macro factors without columns: "
            + ", ".join(sorted(missing))
        )
    quarterly_source["forecast"] = pd.to_numeric(
        quarterly_source["forecast"], errors="coerce"
    )
    quarterly = quarterly_source[
        quarterly_source["scenario_name"].astype(str).isin(
            [base_scenario_name, _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME]
        )
    ].pivot_table(
        index=["stream", "target_period"],
        columns="scenario_name",
        values="forecast",
        aggfunc="first",
    ).reset_index()
    if (
        base_scenario_name not in quarterly.columns
        or _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME not in quarterly.columns
    ):
        raise ValueError("Price-only replay is missing Treasury or legacy Base rows.")
    quarterly = quarterly.rename(
        columns={
            "target_period": "period",
            _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME: "base_value",
            base_scenario_name: "scenario_value",
        }
    ).dropna(subset=["base_value", "scenario_value"])
    quarterly["series_id"] = quarterly["stream"].astype(str).map(
        _STREAM_SERIES_IDS
    )
    if quarterly["series_id"].isna().any():
        raise ValueError("Treasury macro factors contain an unknown activity stream.")
    quarterly["factor"] = np.where(
        quarterly["base_value"].abs() > 1e-12,
        quarterly["scenario_value"] / quarterly["base_value"],
        1.0,
    )
    quarterly["delta"] = quarterly["scenario_value"] - quarterly["base_value"]
    quarterly["scenario_name"] = base_scenario_name
    quarterly["trace_name"] = "Current finalist Base case"
    quarterly["time_grain"] = "quarterly"
    quarterly["transformation_basis"] = (
        "Treasury_BEFU26_macro_replay_vs_legacy_macro_replay"
    )

    annual_source = price_only_annual_bridge.copy()
    required_annual = {"scenario_name", "FY", "series_id", "value"}
    missing = required_annual.difference(annual_source.columns)
    if missing:
        raise ValueError(
            "Price-only annual bridge cannot build macro factors without columns: "
            + ", ".join(sorted(missing))
        )
    annual_source["value"] = pd.to_numeric(annual_source["value"], errors="coerce")
    annual = annual_source[
        annual_source["scenario_name"].astype(str).isin(
            [base_scenario_name, _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME]
        )
    ].pivot_table(
        index=["FY", "series_id"],
        columns="scenario_name",
        values="value",
        aggfunc="first",
    ).reset_index()
    if (
        base_scenario_name not in annual.columns
        or _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME not in annual.columns
    ):
        raise ValueError(
            "Price-only annual bridge is missing Treasury or legacy Base rows."
        )
    annual = annual.rename(
        columns={
            "FY": "june_year",
            _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME: "base_value",
            base_scenario_name: "scenario_value",
        }
    ).dropna(subset=["base_value", "scenario_value"])
    annual["factor"] = np.where(
        annual["base_value"].abs() > 1e-12,
        annual["scenario_value"] / annual["base_value"],
        1.0,
    )
    annual["delta"] = annual["scenario_value"] - annual["base_value"]
    annual["period"] = pd.to_numeric(
        annual["june_year"], errors="coerce"
    ).astype("Int64").map(
        lambda fy: f"FY{int(fy)}" if pd.notna(fy) else ""
    )
    annual["scenario_name"] = base_scenario_name
    annual["trace_name"] = "Current finalist Base case"
    annual["time_grain"] = "june_year"
    annual["transformation_basis"] = (
        "Treasury_BEFU26_macro_annual_bridge_vs_legacy_macro_annual_bridge"
    )
    return (
        quarterly.reset_index(drop=True),
        annual.reset_index(drop=True),
    )


def run_treasury_baseline_macro_replay(
    base_inputs: pd.DataFrame,
    repo_root: Path | str,
    engine: str = "ensemble",
    *,
    latest_actual_period: str | None = None,
    bridge_vintage_id: str | None = None,
) -> TreasuryBaselineMacroReplayResult:
    """Replay Treasury and legacy Base macro paths without conflict dependencies.

    The dashboard uses this two-scenario replay as a fail-safe source for the
    Treasury baseline overlay.  It deliberately does not load fuel-conflict
    paths or policy variants, so a problem in those optional scenario layers
    cannot silently revert the visible Base case to the legacy GDP path.
    """

    root = Path(repo_root)
    base_scenario_name, legacy_base_rows = _base_scenario_rows(base_inputs)
    treasury_inputs = apply_treasury_baseline_macro_path(base_inputs, root)
    treasury_base_scenario_name, treasury_base_rows = _base_scenario_rows(
        treasury_inputs
    )
    if treasury_base_scenario_name != base_scenario_name:
        raise ValueError("Treasury macro transform changed the Base scenario identity.")

    legacy_shadow_rows = _scenario_clone_with_identity(
        legacy_base_rows,
        scenario_name=_LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME,
        role="comparison",
        display_name="Internal legacy macro Base shadow",
    )
    replay_inputs = pd.concat(
        [treasury_base_rows, legacy_shadow_rows],
        ignore_index=True,
        sort=False,
    )
    replay = replay_forecast_from_scenario_inputs(
        replay_inputs,
        repo_root=root,
        engine=engine,
        latest_actual_period=latest_actual_period,
    )
    replay_scenarios = (
        base_scenario_name,
        _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME,
    )
    _validate_complete_numeric_replay(
        replay,
        replay_inputs=replay_inputs,
        scenario_names=replay_scenarios,
    )
    annual_bridge, _ = _annual_bridge_and_factors(
        replay,
        replay_inputs=replay_inputs,
        repo_root=root,
        base_scenario_name=base_scenario_name,
        latest_actual_period=latest_actual_period,
        require_conflict_factors=False,
        isolate_non_ice_activity=False,
        bridge_vintage_id=bridge_vintage_id,
    )
    quarterly_factors, annual_factors = _baseline_macro_factor_frames(
        replay,
        annual_bridge,
        base_scenario_name=base_scenario_name,
    )
    if quarterly_factors.empty or annual_factors.empty:
        raise ValueError("Independent Treasury baseline replay produced no factors.")
    return TreasuryBaselineMacroReplayResult(
        base_scenario_name=base_scenario_name,
        treasury_base_inputs=treasury_base_rows.reset_index(drop=True),
        replay_inputs=replay_inputs.reset_index(drop=True),
        replay=replay,
        baseline_macro_quarterly_factors=quarterly_factors,
        baseline_macro_annual_factors=annual_factors,
    )


def run_fuel_price_scenario_replay(
    base_inputs: pd.DataFrame,
    repo_root: Path | str,
    engine: str = "ensemble",
    *,
    latest_actual_period: str | None = None,
    bridge_vintage_id: str | None = None,
) -> FuelPriceScenarioReplayResult:
    """Build and score Base plus Low/Medium/High under three policy states."""

    root = Path(repo_root)
    base_scenario_name, legacy_base_rows = _base_scenario_rows(base_inputs)
    treasury_inputs = apply_treasury_baseline_macro_path(base_inputs, root)
    treasury_base_scenario_name, base_rows = _base_scenario_rows(treasury_inputs)
    if treasury_base_scenario_name != base_scenario_name:
        raise ValueError("Treasury macro transform changed the Base scenario identity.")
    conflict_paths = load_conflict_fuel_price_paths(root)
    conflict_gdp_paths = build_conflict_gdp_paths(
        root,
        fuel_paths=conflict_paths,
    )
    price_only_fuel_frames = [
        build_fuel_price_scenario_inputs(
            base_rows,
            root,
            level=level,
            scenario_paths=conflict_paths,
        )
        for level in CONFLICT_FUEL_SCENARIO_LEVELS
    ]
    conflict_unemployment_paths = build_conflict_unemployment_paths(root)
    # Both macro adjustments land on the same input layer: the price-only
    # frames stay untouched so the structural overlay's macro model factor
    # (macro-adjusted replay / price-only replay) captures the GDP and
    # unemployment responses together.
    fuel_frames = [
        apply_conflict_unemployment_impact(
            apply_conflict_gdp_impact(
                price_only_rows,
                severity=level,
                repo_root=root,
                gdp_paths=conflict_gdp_paths,
            ),
            severity=level,
            repo_root=root,
            unemployment_paths=conflict_unemployment_paths,
        )
        for level, price_only_rows in zip(
            CONFLICT_FUEL_SCENARIO_LEVELS,
            price_only_fuel_frames,
            strict=True,
        )
    ]
    fuel_rows = pd.concat(fuel_frames, ignore_index=True, sort=False)
    # One policy-variant replay per non-published governed state, for the
    # baseline and each conflict family, plus the matching price-only macro
    # shadow set. Registry-driven: the six-month and no-uplift scenario names
    # and display strings are unchanged.
    policy_frames = []
    price_only_policy_frames = []
    for state_spec in _NON_PUBLISHED_POLICY_SPECS:
        state = state_spec.calculation_state_id
        phrase = state_spec.short_policy_phrase
        policy_frames.append(
            build_ruc_policy_scenario_inputs(
                base_rows,
                root,
                policy_state=state,
                scenario_name=BASE_POLICY_VARIANT_IDS[state],
                scenario_display_name=(
                    f"Current finalist Base case ({phrase}; PED pump + proportional RUC)"
                ),
            )
        )
        price_only_policy_frames.append(
            build_ruc_policy_scenario_inputs(
                base_rows,
                root,
                policy_state=state,
                scenario_name=BASE_POLICY_VARIANT_IDS[state],
                scenario_display_name=(
                    f"Current finalist Base case ({phrase}; price-only macro shadow)"
                ),
            )
        )
    for level, published_rows in zip(
        CONFLICT_FUEL_SCENARIO_LEVELS, fuel_frames, strict=True
    ):
        for state_spec in _NON_PUBLISHED_POLICY_SPECS:
            state = state_spec.calculation_state_id
            policy_frames.append(
                build_ruc_policy_scenario_inputs(
                    published_rows,
                    root,
                    policy_state=state,
                    scenario_name=conflict_policy_variant_name(level, state),
                    scenario_display_name=(
                        f"{conflict_trace_name(level)} ({state_spec.short_policy_phrase})"
                    ),
                )
            )
    for level, published_rows in zip(
        CONFLICT_FUEL_SCENARIO_LEVELS,
        price_only_fuel_frames,
        strict=True,
    ):
        for state_spec in _NON_PUBLISHED_POLICY_SPECS:
            state = state_spec.calculation_state_id
            price_only_policy_frames.append(
                build_ruc_policy_scenario_inputs(
                    published_rows,
                    root,
                    policy_state=state,
                    scenario_name=conflict_policy_variant_name(level, state),
                    scenario_display_name=(
                        f"{conflict_trace_name(level)} "
                        f"({state_spec.short_policy_phrase}; price-only macro shadow)"
                    ),
                )
            )
    policy_scenario_inputs = pd.concat(
        policy_frames,
        ignore_index=True,
        sort=False,
    )
    replay_inputs = pd.concat(
        [base_rows, fuel_rows, policy_scenario_inputs],
        ignore_index=True,
        sort=False,
    )
    price_only_policy_scenario_inputs = pd.concat(
        price_only_policy_frames,
        ignore_index=True,
        sort=False,
    )
    legacy_shadow_rows = _scenario_clone_with_identity(
        legacy_base_rows,
        scenario_name=_LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME,
        role="comparison",
        display_name="Internal legacy macro Base shadow",
    )
    price_only_replay_inputs = pd.concat(
        [
            base_rows,
            pd.concat(price_only_fuel_frames, ignore_index=True, sort=False),
            price_only_policy_scenario_inputs,
            legacy_shadow_rows,
        ],
        ignore_index=True,
        sort=False,
    )
    replay = replay_forecast_from_scenario_inputs(
        replay_inputs,
        repo_root=root,
        engine=engine,
        latest_actual_period=latest_actual_period,
    )
    price_only_replay = replay_forecast_from_scenario_inputs(
        price_only_replay_inputs,
        repo_root=root,
        engine=engine,
        latest_actual_period=latest_actual_period,
    )
    validation = replay.validation_report.copy()
    if validation.empty or not validation["valid"].fillna(False).all():
        details = validation[[column for column in ["scenario_name", "errors"] if column in validation.columns]].to_dict("records")
        raise ValueError(f"Fixed-finalist conflict fuel-price replay failed validation: {details}")
    price_only_validation = price_only_replay.validation_report.copy()
    if (
        price_only_validation.empty
        or not price_only_validation["valid"].fillna(False).all()
    ):
        details = price_only_validation[
            [
                column
                for column in ["scenario_name", "errors"]
                if column in price_only_validation.columns
            ]
        ].to_dict("records")
        raise ValueError(
            "Fixed-finalist price-only shadow replay failed validation: "
            f"{details}"
        )
    replay_scenario_names = (
        base_scenario_name,
        *(conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS),
        *(
            BASE_POLICY_VARIANT_IDS[spec.calculation_state_id]
            for spec in _NON_PUBLISHED_POLICY_SPECS
        ),
        *(
            conflict_policy_variant_name(level, spec.calculation_state_id)
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
            for spec in _NON_PUBLISHED_POLICY_SPECS
        ),
    )
    _validate_complete_numeric_replay(
        replay,
        replay_inputs=replay_inputs,
        scenario_names=replay_scenario_names,
    )
    _validate_complete_numeric_replay(
        price_only_replay,
        replay_inputs=price_only_replay_inputs,
        scenario_names=(
            *replay_scenario_names,
            _LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME,
        ),
    )
    replay = _apply_governed_policy_demand_calibration(
        replay,
        replay_inputs=replay_inputs,
        price_only_replay=price_only_replay,
        repo_root=root,
        base_scenario_name=base_scenario_name,
    )
    input_audit = _input_change_audit(
        base_rows,
        fuel_rows,
        base_scenario_name,
        conflict_paths=conflict_paths,
    )
    gdp_input_audit = conflict_gdp_input_audit(
        pd.concat(
            [fuel_rows, policy_scenario_inputs],
            ignore_index=True,
            sort=False,
        )
    )
    quarterly_factors = _quarterly_factor_audit(replay, base_scenario_name=base_scenario_name)
    raw_annual_bridge, annual_factors = _annual_bridge_and_factors(
        replay,
        replay_inputs=replay_inputs,
        repo_root=root,
        base_scenario_name=base_scenario_name,
        latest_actual_period=latest_actual_period,
        bridge_vintage_id=bridge_vintage_id,
    )
    price_only_annual_bridge, _ = _annual_bridge_and_factors(
        price_only_replay,
        replay_inputs=price_only_replay_inputs,
        repo_root=root,
        base_scenario_name=base_scenario_name,
        latest_actual_period=latest_actual_period,
        bridge_vintage_id=bridge_vintage_id,
    )
    (
        baseline_macro_quarterly_factors,
        baseline_macro_annual_factors,
    ) = _baseline_macro_factor_frames(
        price_only_replay,
        price_only_annual_bridge,
        base_scenario_name=base_scenario_name,
    )
    rate_factor_rows = raw_annual_bridge.copy()
    if "june_year" not in rate_factor_rows.columns and "FY" in rate_factor_rows.columns:
        rate_factor_rows["june_year"] = pd.to_numeric(rate_factor_rows["FY"], errors="coerce")
    rate_factor_rows["time_grain"] = "june_year"
    rate_factor_rows["trace_name"] = np.where(
        rate_factor_rows["scenario_name"].astype(str).eq(base_scenario_name),
        "Current finalist Base case",
        "runtime policy variant",
    )
    annual_policy_factors = {
        spec.state_id: fed_policy_annual_factors(
            root, rate_factor_rows, spec.calculation_state_id
        )
        for spec in _NON_PUBLISHED_POLICY_SPECS
    }
    annual_bridge = apply_policy_rate_factors_to_annual_bridge(
        raw_annual_bridge,
        annual_policy_factors,
        base_scenario_name=base_scenario_name,
    )
    policy_pair_factors = build_policy_scenario_pair_factors(
        replay,
        annual_bridge,
        base_scenario_name=base_scenario_name,
    )
    return FuelPriceScenarioReplayResult(
        base_scenario_name=base_scenario_name,
        treasury_base_inputs=base_rows,
        fuel_scenario_inputs=fuel_rows,
        policy_scenario_inputs=policy_scenario_inputs,
        replay_inputs=replay_inputs,
        replay=replay,
        price_only_replay_inputs=price_only_replay_inputs,
        price_only_replay=price_only_replay,
        input_audit=input_audit,
        gdp_input_audit=gdp_input_audit,
        baseline_macro_quarterly_factors=baseline_macro_quarterly_factors,
        baseline_macro_annual_factors=baseline_macro_annual_factors,
        quarterly_factors=quarterly_factors,
        annual_factors=annual_factors,
        annual_bridge=annual_bridge,
        policy_pair_factors=policy_pair_factors,
    )


def _factor_frames(replay_or_audit: FuelPriceScenarioReplayResult | pd.DataFrame) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    if isinstance(replay_or_audit, FuelPriceScenarioReplayResult):
        return replay_or_audit.base_scenario_name, replay_or_audit.quarterly_factors, replay_or_audit.annual_factors
    if isinstance(replay_or_audit, pd.DataFrame):
        required = {"time_grain", "series_id", "factor"}
        missing = required.difference(replay_or_audit.columns)
        if missing:
            raise ValueError("Fuel-price factor audit is missing columns: " + ", ".join(sorted(missing)))
        audit = replay_or_audit.copy()
        return (
            _BASE_SCENARIO_NAME,
            audit[audit["time_grain"].astype(str).eq("quarterly")].copy(),
            audit[audit["time_grain"].astype(str).eq("june_year")].copy(),
        )
    raise TypeError("replay_or_audit must be FuelPriceScenarioReplayResult or a factor-audit DataFrame.")


def apply_treasury_macro_to_chart_rows(
    chart_rows: pd.DataFrame,
    replay: (
        DirectTreasuryScenarioReplayResult
        | FuelPriceScenarioReplayResult
        | TreasuryBaselineMacroReplayResult
    ),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply Treasury-versus-legacy macro factors before policy/conflict layers.

    This keeps the committed pack as the visible layout/source skeleton while
    making the replayed Treasury macro path authoritative for every current
    model population path.  MBU26, historical actuals and runtime
    conflict/policy rows are never changed.

    With a ``DirectTreasuryScenarioReplayResult`` every factor is looked up by
    ``(scenario_name, series_id, period)``: each governed scenario carries
    factors from its OWN replay against its own legacy shadow. With one of the
    legacy Base-pair results, factors exist only for the Base scenario, and
    any other current-model row fails closed - transferring a Base-derived
    factor to another scenario is inexact for nonlinear and recursive models
    and was retired in P1.2. Either way a targeted row with no factor raises:
    silently retaining the legacy macro value was the fail-open path.
    """

    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame()
    if not isinstance(
        replay,
        (
            DirectTreasuryScenarioReplayResult,
            FuelPriceScenarioReplayResult,
            TreasuryBaselineMacroReplayResult,
        ),
    ):
        raise TypeError("Treasury macro chart overlay requires a replay result.")
    scenario_aware = isinstance(replay, DirectTreasuryScenarioReplayResult)
    out = chart_rows.copy()
    if "scenario_name" not in out.columns or "value" not in out.columns:
        raise ValueError("Chart rows are missing scenario_name/value for macro overlay.")
    quarterly = replay.baseline_macro_quarterly_factors
    annual = replay.baseline_macro_annual_factors
    if quarterly is None or quarterly.empty or annual is None or annual.empty:
        raise ValueError("Treasury macro replay factors are unavailable.")
    if scenario_aware:
        q_lookup = {
            (str(row.scenario_name), str(row.series_id), str(row.period)): float(row.factor)
            for row in quarterly.itertuples()
            if pd.notna(getattr(row, "factor", np.nan))
        }
        a_lookup = {
            (str(row.scenario_name), str(row.series_id), int(row.june_year)): float(row.factor)
            for row in annual.itertuples()
            if pd.notna(getattr(row, "factor", np.nan))
            and pd.notna(getattr(row, "june_year", np.nan))
        }
    else:
        q_lookup = {
            (replay.base_scenario_name, str(row.series_id), str(row.period)): float(row.factor)
            for row in quarterly.itertuples()
            if pd.notna(getattr(row, "factor", np.nan))
        }
        a_lookup = {
            (replay.base_scenario_name, str(row.series_id), int(row.june_year)): float(row.factor)
            for row in annual.itertuples()
            if pd.notna(getattr(row, "factor", np.nan))
            and pd.notna(getattr(row, "june_year", np.nan))
        }
    scenario_names = out["scenario_name"].fillna("").astype(str)
    if "scenario_role" in out.columns:
        scenario_roles = (
            out["scenario_role"].fillna("").astype(str).str.strip().str.casefold()
        )
        current_model_mask = scenario_roles.isin({"basecase", "comparison"})
    else:
        current_model_mask = scenario_names.eq(replay.base_scenario_name)
    runtime_scenario_names = set(POLICY_PATH_IDS).difference(
        {replay.base_scenario_name}
    )
    runtime_scenario_names.add(_LEGACY_BASE_MACRO_SHADOW_SCENARIO_NAME)
    shadow_mask = scenario_names.str.endswith(_DIRECT_SHADOW_SUFFIX)
    target_mask = (
        current_model_mask
        & ~scenario_names.isin(runtime_scenario_names)
        & ~shadow_mask
    )
    out["_treasury_macro_factor"] = 1.0
    out["_treasury_macro_source_value"] = pd.to_numeric(
        out.get("value"), errors="coerce"
    )
    out["_treasury_macro_basis"] = ""
    audit_rows: list[dict[str, Any]] = []
    audit_by_index: dict[Any, dict[str, Any]] = {}
    for index in out.index[target_mask]:
        row = out.loc[index]
        scenario = str(row.get("scenario_name") or "")
        series_id = str(row.get("series_id") or "")
        period = str(row.get("period") or "")
        grain = str(row.get("time_grain") or "")
        if not scenario_aware and scenario != replay.base_scenario_name:
            raise ValueError(
                "Base-derived Treasury macro factors cannot be applied to "
                f"scenario {scenario!r} ({series_id} {period}): factor transfer "
                "across scenarios is inexact for nonlinear and recursive models. "
                "Use run_direct_treasury_scenario_replay so every governed "
                "scenario carries factors from its own replay."
            )
        factor: float | None = None
        basis = ""
        if grain == "quarterly":
            factor = q_lookup.get((scenario, series_id, period))
            if factor is not None:
                basis = "Treasury_BEFU26_native_quarterly_macro_factor"
        if factor is None:
            fy_value = pd.to_numeric(
                pd.Series([row.get("june_year")]), errors="coerce"
            ).iloc[0]
            if pd.isna(fy_value) and grain == "quarterly":
                fy_value = _fiscal_year_from_quarter(period)
            if pd.notna(fy_value):
                factor = a_lookup.get((scenario, series_id, int(fy_value)))
                if factor is not None:
                    basis = "Treasury_BEFU26_annual_bridge_macro_factor"
        if factor is None and str(row.get("forecast_segment") or "") == "post_model_extrapolation":
            # Post-model rows carry the anchor year's factor forward. This is
            # exact, not approximate: beyond the BEFU26 window the Treasury
            # transform itself reverts to re-anchored original growth, so
            # post_fy = pre_fy x factor_2030 IS anchor-and-growth in
            # post-macro space, and FY2030->FY2031 continuity is automatic.
            fy_value = pd.to_numeric(
                pd.Series([row.get("june_year")]), errors="coerce"
            ).iloc[0]
            if pd.notna(fy_value) and int(fy_value) > 2030:
                factor = a_lookup.get((scenario, series_id, 2030))
                if factor is not None:
                    basis = "Treasury_BEFU26_terminal_annual_factor_carry"
        if factor is None:
            # Silently retaining the legacy macro value was the fail-open
            # path: "no factor" and "factor of exactly 1" were
            # indistinguishable downstream.
            raise ValueError(
                "No Treasury macro factor for a current-model row: "
                f"scenario={scenario!r} series={series_id!r} period={period!r} "
                f"grain={grain!r}. A row the overlay targets must either "
                "receive its scenario's own factor or fail closed."
            )
        source_value = pd.to_numeric(
            pd.Series([out.at[index, "value"]]), errors="coerce"
        ).iloc[0]
        if pd.isna(source_value) or not np.isfinite(float(source_value)):
            raise ValueError(
                "Treasury macro overlay found a non-numeric value on a "
                f"current-model row: scenario={scenario!r} series={series_id!r} "
                f"period={period!r}."
            )
        adjusted = float(source_value) * float(factor)
        out.at[index, "value"] = adjusted
        out.at[index, "_treasury_macro_factor"] = float(factor)
        out.at[index, "_treasury_macro_basis"] = basis
        for metadata_column in ("_fed_baseline_value",):
            if metadata_column not in out.columns:
                continue
            metadata_value = pd.to_numeric(
                pd.Series([out.at[index, metadata_column]]), errors="coerce"
            ).iloc[0]
            if pd.notna(metadata_value):
                out.at[index, metadata_column] = float(metadata_value) * float(
                    factor
                )
        audit_row = {
            "audit_type": "treasury_baseline_macro",
            "scenario_name": str(row.get("scenario_name") or ""),
            "scenario_role": str(row.get("scenario_role") or "basecase"),
            "trace_name": str(
                row.get("trace_name") or "Current finalist Base case"
            ),
            "severity": "",
            "time_grain": grain,
            "period": period,
            "june_year": row.get("june_year"),
            "stream": str(row.get("stream") or ""),
            "series_id": series_id,
            "transformation_basis": basis,
            "factor": float(factor),
            "baseline_value": float(source_value),
            "adjusted_value": adjusted,
            "value_delta": adjusted - float(source_value),
            "scenario_note": (
                "Current model paths use the Treasury BEFU26 real-GDP and "
                "population baseline; price inputs are unchanged."
            ),
        }
        audit_rows.append(audit_row)
        audit_by_index[index] = audit_row

    # Applying independently replayed annual factors to the committed display
    # skeleton can expose sub-dollar/million rounding differences between a
    # governed aggregate and its leaves.  Rebuild the annual formula chain
    # after the macro overlay so the chart and detail tables retain exact
    # accounting identities.  Quarterly model outputs remain untouched.
    annual_mask = target_mask & out.get(
        "time_grain", pd.Series("", index=out.index)
    ).astype(str).eq("june_year")
    grouping = ["scenario_name", "june_year"]
    if "fed_path" in out.columns:
        grouping.append("fed_path")
    if annual_mask.any() and "june_year" not in out.columns:
        raise ValueError(
            "Treasury macro annual formula replay requires june_year."
        )
    annual_groups = (
        out[annual_mask].groupby(grouping, dropna=False, sort=False)
        if annual_mask.any()
        else ()
    )
    for group_key, group in annual_groups:
        group_scenario = str(
            group_key[0] if isinstance(group_key, tuple) else group_key
        )
        series_ids = group["series_id"].fillna("").astype(str)
        if series_ids[series_ids.ne("")].duplicated().any():
            duplicates = sorted(
                series_ids[series_ids.duplicated(keep=False)].unique()
            )
            raise ValueError(
                "Treasury macro formula replay found duplicate annual rows: "
                + ", ".join(duplicates)
            )
        index_by_series = {
            str(out.at[index, "series_id"]): index for index in group.index
        }
        source_values = {
            series_id: float(value)
            for series_id, index in index_by_series.items()
            if pd.notna(
                value := pd.to_numeric(
                    pd.Series(
                        [out.at[index, "_treasury_macro_source_value"]]
                    ),
                    errors="coerce",
                ).iloc[0]
            )
        }
        adjusted_values = {
            series_id: float(value)
            for series_id, index in index_by_series.items()
            if pd.notna(
                value := pd.to_numeric(
                    pd.Series([out.at[index, "value"]]),
                    errors="coerce",
                ).iloc[0]
            )
        }
        group_years = (
            pd.to_numeric(group["june_year"], errors="coerce")
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        def _annual_anchor_delta(series_id: str) -> float | None:
            """Return a present anchor's delta without inventing filtered data."""

            if series_id not in index_by_series:
                return None
            if len(group_years) != 1:
                raise ValueError(
                    "Treasury macro annual anchor coverage requires exactly "
                    f"one fiscal year for {series_id}."
                )
            fy = int(group_years[0])
            factor = a_lookup.get((group_scenario, series_id, fy))
            if factor is None and fy > 2030:
                # Post-model years carry the anchor-year factor forward (see
                # the terminal-carry rule in the row loop above).
                factor = a_lookup.get((group_scenario, series_id, 2030))
            if factor is None or not np.isfinite(float(factor)):
                raise ValueError(
                    "Treasury macro annual anchor factor is missing or "
                    f"non-finite for {series_id}/FY{fy}."
                )
            source_value = source_values.get(series_id)
            adjusted_value = adjusted_values.get(series_id)
            if (
                source_value is None
                or adjusted_value is None
                or not np.isfinite(float(source_value))
                or not np.isfinite(float(adjusted_value))
            ):
                raise ValueError(
                    "Treasury macro annual anchor values are missing or "
                    f"non-finite for {series_id}/FY{fy}."
                )
            return float(adjusted_value) - float(source_value)

        ped_delta = _annual_anchor_delta("gross_ped_revenue")
        ruc_delta = _annual_anchor_delta("total_ruc_net_revenue")
        additive_rollups: dict[str, float] = {}
        if ped_delta is not None:
            additive_rollups.update(
                {
                    series_id: ped_delta
                    for series_id in FED_AGGREGATE_SERIES
                }
            )
        if ruc_delta is not None:
            additive_rollups.update(
                {
                    series_id: ruc_delta
                    for series_id in RUC_AGGREGATE_SERIES
                }
            )
        if ped_delta is not None and ruc_delta is not None:
            additive_rollups.update(
                {
                    series_id: ped_delta + ruc_delta
                    for series_id in TOTAL_AGGREGATE_SERIES
                }
            )
        for series_id, delta in additive_rollups.items():
            output_index = index_by_series.get(series_id)
            source_value = source_values.get(series_id)
            if output_index is None or source_value is None:
                continue
            calculated = source_value + float(delta)
            out.at[output_index, "value"] = calculated
            effective_factor = (
                calculated / source_value if abs(source_value) > 1e-12 else 1.0
            )
            out.at[output_index, "_treasury_macro_factor"] = effective_factor
            out.at[
                output_index, "_treasury_macro_basis"
            ] = "Treasury_BEFU26_annual_additive_rollup_replay"
            if output_index in audit_by_index:
                audit_row = audit_by_index[output_index]
                audit_row["transformation_basis"] = (
                    "Treasury_BEFU26_annual_additive_rollup_replay"
                )
                audit_row["factor"] = effective_factor
                audit_row["adjusted_value"] = calculated
                audit_row["value_delta"] = calculated - source_value
        replay_columns = ["value"]
        if "_fed_baseline_value" in out.columns:
            replay_columns.append("_fed_baseline_value")
        for value_column in replay_columns:
            values = {
                series_id: float(value)
                for series_id, index in index_by_series.items()
                if pd.notna(
                    value := pd.to_numeric(
                        pd.Series([out.at[index, value_column]]),
                        errors="coerce",
                    ).iloc[0]
                )
            }
            for formula in FORMULA_DEFINITIONS:
                output = str(formula["output_series_id"])
                output_index = index_by_series.get(output)
                terms = tuple(formula["terms"])
                if (
                    output_index is None
                    or any(str(series_id) not in values for series_id, _ in terms)
                ):
                    continue
                calculated = sum(
                    values[str(series_id)] * float(sign)
                    for series_id, sign in terms
                )
                out.at[output_index, value_column] = calculated
                values[output] = calculated
                if value_column != "value":
                    continue
                source_value = pd.to_numeric(
                    pd.Series(
                        [out.at[output_index, "_treasury_macro_source_value"]]
                    ),
                    errors="coerce",
                ).iloc[0]
                if pd.notna(source_value) and abs(float(source_value)) > 1e-12:
                    effective_factor = calculated / float(source_value)
                    out.at[
                        output_index, "_treasury_macro_factor"
                    ] = effective_factor
                else:
                    effective_factor = 1.0
                out.at[
                    output_index, "_treasury_macro_basis"
                ] = "Treasury_BEFU26_annual_governed_formula_replay"
                if output_index in audit_by_index:
                    audit_row = audit_by_index[output_index]
                    audit_row["transformation_basis"] = (
                        "Treasury_BEFU26_annual_governed_formula_replay"
                    )
                    audit_row["factor"] = effective_factor
                    audit_row["adjusted_value"] = calculated
                    audit_row["value_delta"] = calculated - float(source_value)
    out["treasury_macro_applied"] = (
        target_mask
        & pd.to_numeric(out["_treasury_macro_factor"], errors="coerce")
        .sub(1.0)
        .abs()
        .gt(1e-12)
    )
    return out, pd.DataFrame(audit_rows)


def _lookup_factor(
    row: pd.Series,
    *,
    quarterly_lookup: dict[tuple[str, str], float],
    annual_lookup: dict[tuple[str, int], float],
) -> tuple[float, str]:
    grain = str(row.get("time_grain") or "")
    series_id = str(row.get("series_id") or "")
    if grain == "quarterly":
        key = (series_id, str(row.get("period") or ""))
        if key in quarterly_lookup:
            return float(quarterly_lookup[key]), "fixed_finalist_quarterly_replay_factor"
    elif grain == "june_year":
        fy = pd.to_numeric(pd.Series([row.get("june_year")]), errors="coerce").iloc[0]
        key = (series_id, int(fy)) if pd.notna(fy) else None
        if key in annual_lookup:
            return float(annual_lookup[key]), "fixed_finalist_annual_bridge_factor"
    return 1.0, "base_value_unchanged"


def _identity_group_key(row: pd.Series) -> tuple[str, str, int | None, str]:
    fy = pd.to_numeric(pd.Series([row.get("june_year")]), errors="coerce").iloc[0]
    return (
        str(row.get("time_grain") or ""),
        str(row.get("period") or ""),
        int(fy) if pd.notna(fy) else None,
        str(row.get("fed_path") or ""),
    )


def _leaf_delta(
    group: pd.DataFrame,
    series_ids: tuple[str, ...],
    *,
    adjusted_column: str,
    baseline_column: str,
) -> float:
    selected = group[group["series_id"].astype(str).isin(series_ids)]
    if selected.empty:
        return 0.0
    adjusted = pd.to_numeric(selected[adjusted_column], errors="coerce")
    baseline = pd.to_numeric(selected[baseline_column], errors="coerce")
    return float((adjusted - baseline).fillna(0.0).sum())


def _fiscal_quarters(june_year: int) -> tuple[str, str, str, str]:
    return (
        f"{june_year - 1}Q3",
        f"{june_year - 1}Q4",
        f"{june_year}Q1",
        f"{june_year}Q2",
    )


def _first_conflict_input_divergence_period(
    replay_or_audit: FuelPriceScenarioReplayResult | pd.DataFrame,
) -> str | None:
    """Return the first quarter where Low/Medium/High fuel inputs differ.

    Observed conflict anchors can be shared by every severity.  Annual bridge
    reconciliation must not use later scenario-specific information to alter
    those shared quarters, so callers use this as the causal allocation floor.
    """

    if not isinstance(replay_or_audit, FuelPriceScenarioReplayResult):
        return None
    audit = replay_or_audit.input_audit
    # Ordered for the same reason as ``conflict_gdp_input_audit``: selecting
    # columns through a set makes the intermediate frame's schema depend on
    # PYTHONHASHSEED.
    required = ("severity", "stream", "canonical_period", "scenario_value")
    if audit is None or audit.empty or not set(required).issubset(audit.columns):
        return None

    work = audit[list(required)].copy()
    work["severity"] = work["severity"].astype(str)
    work["stream"] = work["stream"].astype(str)
    work["canonical_period"] = work["canonical_period"].astype(str)
    work["scenario_value"] = pd.to_numeric(work["scenario_value"], errors="coerce")
    work = work[
        work["severity"].isin(CONFLICT_FUEL_SCENARIO_LEVELS)
        & work["scenario_value"].notna()
    ]
    if work.empty:
        return None

    for period in sorted(
        work["canonical_period"].unique(),
        key=_canonical_quarter_order,
    ):
        period_rows = work[work["canonical_period"].eq(period)]
        for _, values in period_rows.groupby("stream", sort=False):
            by_severity = (
                values.groupby("severity", sort=False)["scenario_value"]
                .first()
                .reindex(CONFLICT_FUEL_SCENARIO_LEVELS)
            )
            if by_severity.isna().any():
                continue
            reference = float(by_severity.iloc[0])
            if not np.allclose(
                by_severity.to_numpy(dtype=float),
                reference,
                rtol=1e-12,
                atol=1e-9,
            ):
                return period
    return None


def _causal_quarter_mask(
    quarters: tuple[str, ...] | list[str],
    causal_floor_period: str | None,
) -> np.ndarray:
    """Allow reconciliation at/after the first severity-specific quarter."""

    if not causal_floor_period:
        return np.ones(len(quarters), dtype=bool)
    floor_order = _canonical_quarter_order(causal_floor_period)
    eligible = np.array(
        [_canonical_quarter_order(period) >= floor_order for period in quarters],
        dtype=bool,
    )
    # Fiscal years wholly before the divergence still need their common annual
    # checkpoint reconciled.  In a crossing or later FY, protect the shared
    # prefix and allocate only to causally eligible quarters.
    return eligible if bool(eligible.any()) else np.ones(len(quarters), dtype=bool)


def _scenario_activity_series(series_id: str) -> str:
    if series_id in {"ped_vkt_per_capita", "ped_volume", "light_petrol_vkt", "gross_ped_revenue"}:
        return "ped_vkt_per_capita"
    if series_id.startswith(("light_ruc", "light_bev_ruc", "phev_ruc", "current_light_ruc")):
        return "light_ruc_net_km"
    if series_id.startswith(("heavy_ruc", "heavy_bev_ruc")):
        return "heavy_ruc_net_km"
    return ""


def _allocate_annual_delta_to_quarters(
    annual_delta: float,
    quarters: tuple[str, str, str, str],
    activity_series_id: str,
    quarterly_delta_lookup: dict[tuple[str, str], float],
    *,
    causal_floor_period: str | None = None,
) -> dict[str, float]:
    """Allocate an annual value delta using signed native replay activity deltas."""

    if abs(annual_delta) <= 1e-12:
        return {period: 0.0 for period in quarters}
    eligible = _causal_quarter_mask(list(quarters), causal_floor_period)
    raw = np.array(
        [quarterly_delta_lookup.get((activity_series_id, period), 0.0) for period in quarters],
        dtype=float,
    )
    raw = np.where(np.isfinite(raw), raw, 0.0)
    raw = np.where(eligible, raw, 0.0)
    denominator = float(raw.sum())
    if abs(denominator) > 1e-12:
        allocated = annual_delta * raw / denominator
    else:
        weights = np.abs(raw)
        if float(weights.sum()) <= 1e-12:
            # This is a defensive fallback only. Governed affected series have
            # native replay deltas for every forecast quarter.
            weights = eligible.astype(float)
        allocated = annual_delta * weights / float(weights.sum())
    # Remove floating accumulation drift so every displayed June year remains
    # an exact benchmark after the quarterly scenario layer is applied.
    residual = annual_delta - float(allocated.sum())
    allocated[int(np.argmax(np.abs(allocated)))] += residual
    return {period: float(value) for period, value in zip(quarters, allocated, strict=True)}


def _attach_quarterly_delta_lineage(
    scenario: pd.DataFrame,
    quarterly_delta_lookup: dict[tuple[str, str], float],
    *,
    quarterly_factor_lookup: dict[tuple[str, str], float] | None = None,
    causal_floor_period: str | None = None,
) -> pd.DataFrame:
    """Attach exact scenario-vs-Base quarterly revenue-delta maps to annual rows."""

    out = scenario.copy()
    out["_fuel_quarterly_value_deltas"] = ""
    out["_fuel_affected_quarters"] = ""
    quarterly_direct_delta_base: dict[tuple[str, str, str], float] = {}
    quarterly_rows = out[out["time_grain"].astype(str).eq("quarterly")]
    for _, row in quarterly_rows.iterrows():
        baseline = pd.to_numeric(
            pd.Series([row.get("_fuel_source_value")]), errors="coerce"
        ).iloc[0]
        adjusted = pd.to_numeric(
            pd.Series([row.get("_fuel_adjusted_value")]), errors="coerce"
        ).iloc[0]
        if pd.isna(baseline) or pd.isna(adjusted):
            continue
        key = (
            str(row.get("fed_path") or ""),
            str(row.get("series_id") or ""),
            str(row.get("period") or ""),
        )
        quarterly_direct_delta_base[key] = (
            float(adjusted) - float(baseline)
        ) * _display_unit_scale(row.get("value_unit"))

    annual_mask = out["time_grain"].astype(str).eq("june_year")
    for _, group in out[annual_mask].groupby("_fuel_identity_key", sort=False):
        fy_value = pd.to_numeric(group.get("june_year"), errors="coerce").dropna()
        if fy_value.empty:
            continue
        quarters = _fiscal_quarters(int(fy_value.iloc[0]))
        maps_by_series: dict[str, dict[str, float]] = {}

        for index, row in group.iterrows():
            series_id = str(row.get("series_id") or "")
            if series_id in set(RUC_AGGREGATE_SERIES) | set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES):
                continue
            baseline = pd.to_numeric(pd.Series([row.get("_fuel_source_value")]), errors="coerce").iloc[0]
            adjusted = pd.to_numeric(pd.Series([row.get("_fuel_adjusted_value")]), errors="coerce").iloc[0]
            if pd.isna(baseline) or pd.isna(adjusted):
                continue
            activity_series = _scenario_activity_series(series_id)
            annual_delta = float(adjusted - baseline)
            annual_scale = _display_unit_scale(row.get("value_unit"))
            direct_keys = [
                (
                    str(row.get("fed_path") or ""),
                    series_id,
                    period,
                )
                for period in quarters
            ]
            if any(key in quarterly_direct_delta_base for key in direct_keys):
                delta_map = {
                    period: float(
                        quarterly_direct_delta_base.get(key, 0.0) / annual_scale
                    )
                    for period, key in zip(quarters, direct_keys, strict=True)
                }
                residual = annual_delta - float(sum(delta_map.values()))
                if abs(residual) > 1e-12:
                    eligible = _causal_quarter_mask(
                        list(quarters),
                        causal_floor_period,
                    )
                    weights = np.array(
                        [
                            abs(
                                quarterly_delta_lookup.get(
                                    (activity_series, period),
                                    0.0,
                                )
                            )
                            if activity_series
                            else 0.0
                            for period in quarters
                        ],
                        dtype=float,
                    )
                    weights = np.where(eligible, weights, 0.0)
                    if float(weights.sum()) <= 1e-12:
                        weights = np.array(
                            [
                                abs(delta_map[period]) if eligible[position] else 0.0
                                for position, period in enumerate(quarters)
                            ],
                            dtype=float,
                        )
                    if float(weights.sum()) <= 1e-12:
                        weights = eligible.astype(float)
                    corrections = residual * weights / float(weights.sum())
                    corrections[int(np.argmax(weights))] += residual - float(
                        corrections.sum()
                    )
                    for position, period in enumerate(quarters):
                        delta_map[period] += float(corrections[position])
                maps_by_series[series_id] = delta_map
            elif activity_series:
                eligible = _causal_quarter_mask(
                    list(quarters),
                    causal_floor_period,
                )
                protected_positions = np.flatnonzero(~eligible)
                if len(protected_positions) and quarterly_factor_lookup is not None:
                    # Revenue chart rows are annual-only, so reconstruct the
                    # shared observed-quarter response from the Base annual
                    # quarter and the native activity factor.  The remaining
                    # annual bridge residual is then allocated only from the
                    # first severity-specific quarter onward.
                    delta_map = {period: 0.0 for period in quarters}
                    base_quarter_value = float(baseline) / float(len(quarters))
                    for position in protected_positions:
                        period = quarters[int(position)]
                        factor = quarterly_factor_lookup.get(
                            (activity_series, period),
                            1.0,
                        )
                        delta_map[period] = base_quarter_value * (float(factor) - 1.0)
                    residual = annual_delta - float(sum(delta_map.values()))
                    weights = np.array(
                        [
                            abs(
                                quarterly_delta_lookup.get(
                                    (activity_series, period),
                                    0.0,
                                )
                            )
                            if eligible[position]
                            else 0.0
                            for position, period in enumerate(quarters)
                        ],
                        dtype=float,
                    )
                    if float(weights.sum()) <= 1e-12:
                        weights = eligible.astype(float)
                    corrections = residual * weights / float(weights.sum())
                    corrections[int(np.argmax(weights))] += residual - float(
                        corrections.sum()
                    )
                    for position, period in enumerate(quarters):
                        delta_map[period] += float(corrections[position])
                    maps_by_series[series_id] = delta_map
                else:
                    maps_by_series[series_id] = _allocate_annual_delta_to_quarters(
                        annual_delta,
                        quarters,
                        activity_series,
                        quarterly_delta_lookup,
                        causal_floor_period=causal_floor_period,
                    )
            else:
                maps_by_series[series_id] = {period: 0.0 for period in quarters}

        ped_map = maps_by_series.get("gross_ped_revenue", {period: 0.0 for period in quarters})
        ruc_map = {
            period: sum(maps_by_series.get(series_id, {}).get(period, 0.0) for series_id in _RUC_REVENUE_LEAVES)
            for period in quarters
        }
        for index, row in group.iterrows():
            series_id = str(row.get("series_id") or "")
            if series_id in RUC_AGGREGATE_SERIES:
                delta_map = dict(ruc_map)
            elif series_id in FED_AGGREGATE_SERIES:
                delta_map = dict(ped_map)
            elif series_id in TOTAL_AGGREGATE_SERIES:
                delta_map = {period: ped_map[period] + ruc_map[period] for period in quarters}
            else:
                delta_map = maps_by_series.get(series_id, {period: 0.0 for period in quarters})

            baseline = pd.to_numeric(pd.Series([row.get("_fuel_source_value")]), errors="coerce").iloc[0]
            adjusted = pd.to_numeric(pd.Series([row.get("_fuel_adjusted_value")]), errors="coerce").iloc[0]
            if pd.notna(baseline) and pd.notna(adjusted):
                annual_delta = float(adjusted - baseline)
                residual = annual_delta - float(sum(delta_map.values()))
                if abs(residual) > 1e-12:
                    eligible = _causal_quarter_mask(
                        list(quarters),
                        causal_floor_period,
                    )
                    eligible_periods = [
                        period
                        for position, period in enumerate(quarters)
                        if eligible[position]
                    ]
                    active = [
                        period
                        for period in eligible_periods
                        if abs(delta_map.get(period, 0.0)) > 1e-12
                    ]
                    target = (
                        max(active, key=lambda period: abs(delta_map[period]))
                        if active
                        else eligible_periods[-1]
                    )
                    delta_map[target] += residual
            out.at[index, "_fuel_quarterly_value_deltas"] = json.dumps(delta_map, sort_keys=True, separators=(",", ":"))
            out.at[index, "_fuel_affected_quarters"] = ";".join(
                period for period in quarters if abs(delta_map.get(period, 0.0)) > 1e-12
            )
    return out


_NATIVE_QUARTERLY_ACTIVITY_SERIES = {
    "ped_vkt_per_capita",
    "light_ruc_net_km",
    "heavy_ruc_net_km",
}


def _display_unit_scale(unit: Any) -> float:
    # Registry-backed: an unknown declaration raises rather than silently
    # returning 1.0, which used to make a typo indistinguishable from an
    # already-unscaled unit. Absent declarations stay unscaled for display.
    if not str(unit or "").strip():
        return 1.0
    return display_scale_for(unit)


def _reconcile_native_activity_quarters_to_annual(
    scenario: pd.DataFrame,
    *,
    causal_floor_period: str | None = None,
) -> pd.DataFrame:
    """Reconcile Base-plus-replay quarters to unchanged annual checkpoints.

    The immutable replay delta is applied first to every adjusted Base
    quarter.  The governed annual bridge remains authoritative, so any small
    difference introduced by rebasing Base is recorded as a separate annual-
    reconciliation layer and allocated only across quarters where the replay
    itself responds.  Pre-conflict quarters therefore stay equal to Base, and
    each registered path retains its own conflict/convergence timing.
    """

    if scenario is None or scenario.empty:
        return scenario
    required = {
        "series_id",
        "time_grain",
        "june_year",
        "fed_path",
        "value_unit",
        "_fuel_source_value",
        "_fuel_adjusted_value",
    }
    if required.difference(scenario.columns):
        return scenario

    out = scenario.copy()
    series = out["series_id"].fillna("").astype(str)
    grain = out["time_grain"].fillna("").astype(str)
    fy = pd.to_numeric(out["june_year"], errors="coerce")
    fed_path = out["fed_path"].fillna("").astype(str)
    units = out["value_unit"].fillna("").astype(str)
    source_value = pd.to_numeric(out["_fuel_source_value"], errors="coerce")
    adjusted_value = pd.to_numeric(out["_fuel_adjusted_value"], errors="coerce")
    annual_mask = grain.eq("june_year") & series.isin(_NATIVE_QUARTERLY_ACTIVITY_SERIES) & fy.notna()
    if "_fuel_quarterly_reconciliation_delta" not in out.columns:
        out["_fuel_quarterly_reconciliation_delta"] = 0.0

    for annual_index in out.index[annual_mask]:
        annual_series = series.at[annual_index]
        annual_fy = int(fy.at[annual_index])
        annual_path = fed_path.at[annual_index]
        quarterly_mask = (
            grain.eq("quarterly")
            & series.eq(annual_series)
            & fy.eq(annual_fy)
            & fed_path.eq(annual_path)
            & source_value.notna()
            & adjusted_value.notna()
        )
        quarterly_indices = list(out.index[quarterly_mask])
        if (
            not quarterly_indices
            or pd.isna(source_value.at[annual_index])
            or pd.isna(adjusted_value.at[annual_index])
        ):
            continue
        quarterly_delta_base = np.array(
            [
                (float(adjusted_value.at[index]) - float(source_value.at[index]))
                * _display_unit_scale(units.at[index])
                for index in quarterly_indices
            ],
            dtype=float,
        )
        annual_scale = _display_unit_scale(units.at[annual_index])
        annual_delta_base = (
            float(adjusted_value.at[annual_index]) - float(source_value.at[annual_index])
        ) * annual_scale
        residual_base = annual_delta_base - float(quarterly_delta_base.sum())
        tolerance = max(1e-7, abs(annual_delta_base) * 1e-13)
        if abs(residual_base) <= tolerance:
            continue

        quarter_periods = [str(out.at[index, "period"]) for index in quarterly_indices]
        eligible_positions = _causal_quarter_mask(
            quarter_periods,
            causal_floor_period,
        )
        active_positions = np.flatnonzero(
            (np.abs(quarterly_delta_base) > 1e-12) & eligible_positions
        )
        if len(active_positions):
            basis = "fixed_finalist_quarterly_replay_delta_plus_annual_reconciliation"
            weights = np.abs(quarterly_delta_base[active_positions])
        else:
            # The governed annual bridge can retain a post-shock composition
            # effect after the native quarterly finalist has returned exactly
            # to Base (for example Light RUC FY2029).  Preserve that annual
            # checkpoint using the adjusted Base within-FY shape and expose it
            # explicitly as annual-bridge-only provenance.
            active_positions = np.flatnonzero(eligible_positions)
            weights = np.array(
                [
                    abs(float(source_value.at[index]) * _display_unit_scale(units.at[index]))
                    for position, index in enumerate(quarterly_indices)
                    if eligible_positions[position]
                ],
                dtype=float,
            )
            if float(weights.sum()) <= 0.0:
                weights = np.ones(len(active_positions), dtype=float)
            basis = "annual_bridge_only_quarterly_reconciliation"
        weights = weights / float(weights.sum())
        corrections = np.zeros(len(quarterly_indices), dtype=float)
        corrections[active_positions] = residual_base * weights
        corrections[active_positions[int(np.argmax(weights))]] += residual_base - float(corrections.sum())

        for position, index in enumerate(quarterly_indices):
            correction_display = corrections[position] / _display_unit_scale(units.at[index])
            if abs(correction_display) <= 0.0:
                continue
            out.at[index, "_fuel_adjusted_value"] = float(out.at[index, "_fuel_adjusted_value"]) + correction_display
            published_adjusted = pd.to_numeric(
                pd.Series([out.at[index, "_fuel_adjusted_published_value"]]), errors="coerce"
            ).iloc[0]
            if pd.notna(published_adjusted):
                out.at[index, "_fuel_adjusted_published_value"] = float(published_adjusted) + correction_display
            out.at[index, "_fuel_quarterly_reconciliation_delta"] = correction_display
            if abs(float(source_value.at[index])) > 1e-12:
                out.at[index, "_fuel_factor"] = (
                    float(out.at[index, "_fuel_adjusted_value"]) / float(source_value.at[index])
                )
            out.at[index, "_fuel_transformation_basis"] = basis

        reconciled_delta_base = sum(
            (float(out.at[index, "_fuel_adjusted_value"]) - float(source_value.at[index]))
            * _display_unit_scale(units.at[index])
            for index in quarterly_indices
        )
        # Raw RUC quarters are O(1e9); 1e-5 km is below their floating-point
        # accumulation noise and only 1e-11 of the displayed million-km unit.
        if not np.isclose(reconciled_delta_base, annual_delta_base, rtol=0.0, atol=max(1e-5, tolerance)):
            raise ValueError(
                "Conflict quarterly activity failed annual reconciliation: "
                f"{annual_series} FY{annual_fy}."
            )
    return out


def _append_one_fuel_price_scenario_to_chart_rows(
    chart_rows: pd.DataFrame,
    replay_or_audit: FuelPriceScenarioReplayResult | pd.DataFrame,
    *,
    level: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append one registered conflict trace to Base-derived chart rows.

    The function is idempotent for the selected severity.
    Quarterly non-aggregate rows inherit the current Base path plus immutable
    fixed-finalist replay deltas, with an explicit reconciliation layer back
    to the unchanged annual-bridge checkpoints. Annual non-aggregate rows
    retain their governed bridge factors. FED, RUC and whole-of-NLTF
    aggregates receive the sum of the affected leaf deltas, keeping fixed
    revenue components unchanged.
    """

    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame(columns=_FUEL_AUDIT_COLUMNS)
    severity = _normalise_conflict_level(level)
    scenario_name = conflict_scenario_name(severity)
    trace_name = conflict_trace_name(severity)
    scenario_note = conflict_scenario_note(severity)
    base_scenario_name, quarterly_factors, annual_factors = _factor_frames(replay_or_audit)
    if "scenario_name" in quarterly_factors.columns:
        quarterly_factors = quarterly_factors[
            quarterly_factors["scenario_name"].astype(str).eq(scenario_name)
        ].copy()
    if "scenario_name" in annual_factors.columns:
        annual_factors = annual_factors[
            annual_factors["scenario_name"].astype(str).eq(scenario_name)
        ].copy()
    # The current-model path is withheld beyond H20, so conflict effects are
    # truncated at the same boundary. Without this the direct quarterly
    # response would run past the last published annual checkpoint and trip
    # the missing-annual-bridge guard below.
    if "period" in quarterly_factors.columns:
        quarterly_factors = quarterly_factors[
            quarterly_factors["period"].astype(str).map(
                lambda period: quarterly_availability(period)[0] == AVAILABILITY_AVAILABLE
            )
        ].copy()
    if quarterly_factors.empty or annual_factors.empty:
        raise ValueError(f"Factor audit has no rows for conflict severity {severity!r}.")
    # Never let a missing annual bridge silently turn a direct quarterly
    # conflict response into an annual factor of 1.0.  For example, an
    # artificially stale actual-quarter cutoff can leave FY2026 without the
    # two pre-horizon quarters needed by the annual bridge.  Failing here is
    # safer than displaying quarterly movement against an unchanged annual
    # checkpoint.
    direct_quarterly = quarterly_factors[
        pd.to_numeric(quarterly_factors.get("delta"), errors="coerce")
        .fillna(0.0)
        .abs()
        .gt(1e-12)
    ]
    direct_fiscal_years = {
        int(fy)
        for fy in direct_quarterly["period"].map(_fiscal_year_from_quarter)
        if pd.notna(fy)
    }
    available_annual_fiscal_years = set(
        pd.to_numeric(annual_factors.get("june_year"), errors="coerce")
        .dropna()
        .astype(int)
    )
    # A June year that the horizon policy deliberately withholds has no annual
    # checkpoint by design, so its absence is not a missing bridge. FY2031 is
    # the live case: 2030Q3 (H19) and 2030Q4 (H20) are published quarterly and
    # carry direct conflict effects, but FY2031 straddles H19-H22 and is never
    # published as an annual total. Only genuinely missing bridges - such as a
    # stale actual-quarter cutoff leaving FY2026 short - must still fail.
    withheld_fiscal_years = {
        fiscal_year
        for fiscal_year in direct_fiscal_years
        if annual_availability(fiscal_year)[0] != AVAILABILITY_AVAILABLE
    }
    missing_direct_fiscal_years = sorted(
        direct_fiscal_years.difference(available_annual_fiscal_years).difference(
            withheld_fiscal_years
        )
    )
    if missing_direct_fiscal_years:
        missing_labels = ", ".join(
            f"FY{fiscal_year}" for fiscal_year in missing_direct_fiscal_years
        )
        raise ValueError(
            f"Conflict severity {severity!r} has direct quarterly effects in "
            f"{missing_labels}, but the selected engine's annual bridge has no "
            "matching factors. Refusing to default those annual factors to 1.0."
        )
    source = chart_rows[
        ~chart_rows["scenario_name"].astype(str).eq(scenario_name)
    ].copy()
    base = source[source["scenario_name"].astype(str).eq(base_scenario_name)].copy()
    if base.empty:
        raise ValueError(f"Chart rows do not contain Base scenario {base_scenario_name!r}.")

    q_lookup = {
        (str(row.series_id), str(row.period)): float(row.factor)
        for row in quarterly_factors.itertuples()
        if pd.notna(getattr(row, "factor", np.nan))
    }
    q_delta_lookup = {
        (str(row.series_id), str(row.period)): float(row.delta)
        for row in quarterly_factors.itertuples()
        if pd.notna(getattr(row, "delta", np.nan))
    }
    a_lookup = {
        (str(row.series_id), int(row.june_year)): float(row.factor)
        for row in annual_factors.itertuples()
        if pd.notna(getattr(row, "factor", np.nan)) and pd.notna(getattr(row, "june_year", np.nan))
    }
    scenario = base.copy()
    current = pd.to_numeric(scenario.get("value"), errors="coerce")
    fed_baseline = pd.to_numeric(scenario.get("_fed_baseline_value", pd.Series(np.nan, index=scenario.index)), errors="coerce")
    fed_policy = scenario.get("_fed_policy", pd.Series("", index=scenario.index)).fillna("").astype(str)
    fed_metadata_active = fed_baseline.notna() | fed_policy.str.len().gt(0)
    published = fed_baseline.where(fed_baseline.notna(), current)

    # When Base has already moved to a different PED/RUC policy path, compare
    # the selected conflict severity with that matching Base replay. This
    # keeps the policy activity response separate from the fuel-price response
    # and avoids composing two independently rounded annual overlays.
    current_pair_id = f"{severity}_published"
    for state_spec in _NON_PUBLISHED_POLICY_SPECS:
        if fed_policy.eq(state_spec.calculation_state_id).any():
            current_pair_id = f"{severity}_vs_baseline_{state_spec.pair_state_suffix}"
            break

    def _pair_lookups(
        pair_id: str,
    ) -> tuple[
        dict[tuple[str, str], float],
        dict[tuple[str, str], float],
        dict[tuple[str, int], float],
    ]:
        if not isinstance(replay_or_audit, FuelPriceScenarioReplayResult):
            return q_lookup, q_delta_lookup, a_lookup
        pair = replay_or_audit.policy_pair_factors
        if pair is None or pair.empty:
            return q_lookup, q_delta_lookup, a_lookup
        selected = pair[pair["pair_id"].astype(str).eq(pair_id)].copy()
        quarterly = selected[selected["time_grain"].astype(str).eq("quarterly")]
        annual = selected[selected["time_grain"].astype(str).eq("june_year")]
        selected_q_factor = {
            (str(row.series_id), str(row.period)): float(row.factor)
            for row in quarterly.itertuples()
            if pd.notna(getattr(row, "factor", np.nan))
        }
        selected_q_delta = {
            (str(row.series_id), str(row.period)): float(row.delta)
            for row in quarterly.itertuples()
            if pd.notna(getattr(row, "delta", np.nan))
        }
        selected_a_factor = {
            (str(row.series_id), int(row.june_year)): float(row.factor)
            for row in annual.itertuples()
            if pd.notna(getattr(row, "factor", np.nan))
            and pd.notna(getattr(row, "june_year", np.nan))
        }
        if not selected_a_factor:
            raise ValueError(f"Policy replay pair {pair_id!r} has no annual factors.")
        return selected_q_factor, selected_q_delta, selected_a_factor

    published_q_lookup, published_q_delta_lookup, published_a_lookup = _pair_lookups(
        f"{severity}_published"
    )
    current_q_lookup, current_q_delta_lookup, current_a_lookup = _pair_lookups(
        current_pair_id
    )

    scenario["_fuel_source_value"] = current
    scenario["_fuel_source_published_value"] = published
    scenario["_fuel_adjusted_value"] = current
    scenario["_fuel_adjusted_published_value"] = published
    scenario["_fuel_factor"] = 1.0
    scenario["_fuel_transformation_basis"] = "base_value_unchanged"
    scenario["_fuel_quarterly_reconciliation_delta"] = 0.0

    aggregate_series = set(RUC_AGGREGATE_SERIES) | set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
    for index, row in scenario.iterrows():
        series_id = str(row.get("series_id") or "")
        grain = str(row.get("time_grain") or "")
        fy_value = pd.to_numeric(pd.Series([row.get("june_year")]), errors="coerce").iloc[0]
        if grain == "june_year" and pd.notna(fy_value):
            current_factor = current_a_lookup.get((series_id, int(fy_value)), 1.0)
            published_factor = published_a_lookup.get((series_id, int(fy_value)), 1.0)
            if pd.notna(current.at[index]):
                scenario.at[index, "_fuel_adjusted_value"] = float(current.at[index]) * float(current_factor)
            if pd.notna(published.at[index]):
                scenario.at[index, "_fuel_adjusted_published_value"] = (
                    float(published.at[index]) * float(published_factor)
                )
            scenario.at[index, "_fuel_factor"] = float(current_factor)
            scenario.at[index, "_fuel_transformation_basis"] = (
                "policy_matched_annual_bridge_factor"
            )
            continue
        if series_id in aggregate_series:
            continue
        factor, basis = _lookup_factor(
            row,
            quarterly_lookup=current_q_lookup,
            annual_lookup=current_a_lookup,
        )
        published_factor, _ = _lookup_factor(
            row,
            quarterly_lookup=published_q_lookup,
            annual_lookup=published_a_lookup,
        )
        delta: float | None = None
        published_delta: float | None = None
        if grain == "quarterly":
            period = str(row.get("period") or "")
            delta = current_q_delta_lookup.get((series_id, period))
            published_delta = published_q_delta_lookup.get((series_id, period))
            if delta is not None:
                # Replay activity deltas are stored in their native base
                # units (raw net km for RUC).  The uptake bridge may already
                # have normalised the displayed quarter to million km.
                delta = float(delta) / _display_unit_scale(row.get("value_unit"))
                basis = "fixed_finalist_quarterly_replay_delta"
            if published_delta is not None:
                published_delta = float(published_delta) / _display_unit_scale(row.get("value_unit"))
        if pd.notna(current.at[index]):
            adjusted = (
                float(current.at[index]) + float(delta)
                if delta is not None
                else float(current.at[index]) * factor
            )
            scenario.at[index, "_fuel_adjusted_value"] = adjusted
            if abs(float(current.at[index])) > 1e-12:
                factor = adjusted / float(current.at[index])
        if pd.notna(published.at[index]):
            scenario.at[index, "_fuel_adjusted_published_value"] = (
                float(published.at[index]) + float(published_delta)
                if published_delta is not None
                else float(published.at[index]) * published_factor
            )
        scenario.at[index, "_fuel_factor"] = factor
        scenario.at[index, "_fuel_transformation_basis"] = basis

    scenario["_fuel_identity_key"] = scenario.apply(_identity_group_key, axis=1)
    for _, group in scenario.groupby("_fuel_identity_key", sort=False):
        ped_current_delta = _leaf_delta(
            group,
            ("gross_ped_revenue",),
            adjusted_column="_fuel_adjusted_value",
            baseline_column="_fuel_source_value",
        )
        ped_published_delta = _leaf_delta(
            group,
            ("gross_ped_revenue",),
            adjusted_column="_fuel_adjusted_published_value",
            baseline_column="_fuel_source_published_value",
        )
        ruc_current_delta = _leaf_delta(
            group,
            _RUC_REVENUE_LEAVES,
            adjusted_column="_fuel_adjusted_value",
            baseline_column="_fuel_source_value",
        )
        ruc_published_delta = _leaf_delta(
            group,
            _RUC_REVENUE_LEAVES,
            adjusted_column="_fuel_adjusted_published_value",
            baseline_column="_fuel_source_published_value",
        )
        net_ruc_current_delta = _leaf_delta(
            group,
            ("total_ruc_net_revenue",),
            adjusted_column="_fuel_adjusted_value",
            baseline_column="_fuel_source_value",
        )
        net_ruc_published_delta = _leaf_delta(
            group,
            ("total_ruc_net_revenue",),
            adjusted_column="_fuel_adjusted_published_value",
            baseline_column="_fuel_source_published_value",
        )
        for index in group.index:
            series_id = str(scenario.at[index, "series_id"])
            is_annual = str(scenario.at[index, "time_grain"]) == "june_year"
            if is_annual and series_id in RUC_AGGREGATE_SERIES:
                # Net RUC already uses the exact full-bridge pair factor,
                # including the hidden Heavy-BEV leaf and fixed admin/refunds.
                continue
            if series_id in RUC_AGGREGATE_SERIES:
                current_delta, published_delta, basis = ruc_current_delta, ruc_published_delta, "additive_ruc_leaf_delta"
            elif series_id in FED_AGGREGATE_SERIES:
                current_delta, published_delta = ped_current_delta, ped_published_delta
                basis = "formula_rebuilt_from_ped_delta"
            elif series_id in TOTAL_AGGREGATE_SERIES:
                if is_annual:
                    current_delta = ped_current_delta + net_ruc_current_delta
                    published_delta = ped_published_delta + net_ruc_published_delta
                    basis = "formula_rebuilt_from_ped_and_net_ruc_deltas"
                else:
                    current_delta = ped_current_delta + ruc_current_delta
                    published_delta = ped_published_delta + ruc_published_delta
                    basis = "additive_ped_and_ruc_leaf_delta"
            else:
                continue
            source_value = scenario.at[index, "_fuel_source_value"]
            source_published = scenario.at[index, "_fuel_source_published_value"]
            if pd.notna(source_value):
                scenario.at[index, "_fuel_adjusted_value"] = float(source_value) + current_delta
            if pd.notna(source_published):
                scenario.at[index, "_fuel_adjusted_published_value"] = float(source_published) + published_delta
            scenario.at[index, "_fuel_transformation_basis"] = basis
            if pd.notna(source_value) and abs(float(source_value)) > 1e-12:
                scenario.at[index, "_fuel_factor"] = float(scenario.at[index, "_fuel_adjusted_value"]) / float(source_value)

    causal_floor_period = _first_conflict_input_divergence_period(replay_or_audit)
    scenario = _reconcile_native_activity_quarters_to_annual(
        scenario,
        causal_floor_period=causal_floor_period,
    )
    scenario = _attach_quarterly_delta_lineage(
        scenario,
        current_q_delta_lookup,
        quarterly_factor_lookup=current_q_lookup,
        causal_floor_period=causal_floor_period,
    )

    scenario["value"] = pd.to_numeric(scenario["_fuel_adjusted_value"], errors="coerce")
    for column in _FED_POLICY_COLUMNS:
        if column not in scenario.columns:
            scenario[column] = np.nan
    scenario.loc[fed_metadata_active, "_fed_baseline_value"] = pd.to_numeric(
        scenario.loc[fed_metadata_active, "_fuel_adjusted_published_value"], errors="coerce"
    )
    scenario.loc[fed_metadata_active, "_fed_annual_delta"] = (
        pd.to_numeric(scenario.loc[fed_metadata_active, "_fuel_adjusted_value"], errors="coerce")
        - pd.to_numeric(scenario.loc[fed_metadata_active, "_fuel_adjusted_published_value"], errors="coerce")
    )

    scenario["scenario_name"] = scenario_name
    scenario["scenario_role"] = "comparison"
    scenario["trace_name"] = trace_name
    if "trace_type" in scenario.columns:
        scenario["trace_type"] = "current finalist conflict fuel-price scenario"
    if "trace_role" in scenario.columns:
        scenario["trace_role"] = "comparison"
    if "trace_source" in scenario.columns:
        scenario["trace_source"] = "fixed-finalist conflict fuel-price replay"
    scenario["fuel_price_scenario"] = True
    scenario["fuel_price_scenario_note"] = scenario_note
    scenario["conflict_fuel_severity"] = severity
    scenario["iran_war_scenario"] = severity == "medium"
    scenario["iran_war_scenario_note"] = scenario_note if severity == "medium" else ""
    scenario["_fuel_baseline_value"] = scenario["_fuel_source_value"]
    scenario["_fuel_value_delta"] = (
        pd.to_numeric(scenario["_fuel_adjusted_value"], errors="coerce")
        - pd.to_numeric(scenario["_fuel_source_value"], errors="coerce")
    )
    if "canonical_scenario_key" in scenario.columns:
        scenario["canonical_scenario_key"] = scenario_name
    if "canonical_join_key" in scenario.columns:
        period_key = scenario.get("canonical_period_key", scenario.get("period", pd.Series("", index=scenario.index))).astype(str)
        stream_key = scenario.get("canonical_stream_key", scenario.get("stream", pd.Series("", index=scenario.index))).astype(str)
        scenario["canonical_join_key"] = stream_key + "|" + period_key + "|" + scenario_name

    audit_rows: list[dict[str, Any]] = []
    for index, row in scenario.iterrows():
        baseline_value = pd.to_numeric(pd.Series([row.get("_fuel_source_value")]), errors="coerce").iloc[0]
        adjusted_value = pd.to_numeric(pd.Series([row.get("_fuel_adjusted_value")]), errors="coerce").iloc[0]
        published_value = pd.to_numeric(pd.Series([row.get("_fuel_source_published_value")]), errors="coerce").iloc[0]
        adjusted_published = pd.to_numeric(pd.Series([row.get("_fuel_adjusted_published_value")]), errors="coerce").iloc[0]
        if pd.isna(baseline_value) or pd.isna(adjusted_value):
            continue
        audit_rows.append(
            {
                "scenario_name": scenario_name,
                "scenario_role": "comparison",
                "trace_name": trace_name,
                "severity": severity,
                "time_grain": str(row.get("time_grain") or ""),
                "period": str(row.get("period") or ""),
                "june_year": row.get("june_year"),
                "stream": str(row.get("stream") or ""),
                "series_id": str(row.get("series_id") or ""),
                "transformation_basis": str(row.get("_fuel_transformation_basis") or ""),
                "factor": float(row.get("_fuel_factor", 1.0)),
                "baseline_value": float(baseline_value),
                "adjusted_value": float(adjusted_value),
                "value_delta": float(adjusted_value - baseline_value),
                "quarterly_annual_reconciliation_delta": float(
                    row.get("_fuel_quarterly_reconciliation_delta", 0.0) or 0.0
                ),
                "published_fed_baseline_value": float(published_value) if pd.notna(published_value) else pd.NA,
                "adjusted_published_fed_value": float(adjusted_published) if pd.notna(adjusted_published) else pd.NA,
                "fed_policy_delta": float(adjusted_value - adjusted_published) if fed_metadata_active.at[index] and pd.notna(adjusted_published) else pd.NA,
                "fed_policy": str(row.get("_fed_policy") or ""),
                "fed_affected_quarters": str(row.get("_fed_affected_quarters") or ""),
                "scenario_note": scenario_note,
            }
        )

    internal_columns = [
        "_fuel_source_value",
        "_fuel_source_published_value",
        "_fuel_adjusted_value",
        "_fuel_adjusted_published_value",
        "_fuel_transformation_basis",
        "_fuel_identity_key",
    ]
    scenario = scenario.drop(columns=internal_columns, errors="ignore")
    combined = pd.concat([source, scenario], ignore_index=True, sort=False)
    return combined, pd.DataFrame(audit_rows, columns=_FUEL_AUDIT_COLUMNS)


def append_fuel_price_scenario_to_chart_rows(
    chart_rows: pd.DataFrame,
    replay_or_audit: FuelPriceScenarioReplayResult | pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append Low, Medium and High traces for the active Base policy state.

    Existing registered traces are removed first, so repeated calls are
    idempotent. A legacy factor DataFrame without scenario IDs remains a
    Medium-only compatibility input.
    """

    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame(columns=_FUEL_AUDIT_COLUMNS)
    registered_names = {
        conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
    }
    combined = chart_rows[
        ~chart_rows["scenario_name"].astype(str).isin(registered_names)
    ].copy()
    if isinstance(replay_or_audit, FuelPriceScenarioReplayResult):
        levels = tuple(CONFLICT_FUEL_SCENARIO_LEVELS)
    else:
        audit_names = (
            set(replay_or_audit["scenario_name"].dropna().astype(str))
            if "scenario_name" in replay_or_audit.columns
            else set()
        )
        levels = tuple(
            level
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
            if conflict_scenario_name(level) in audit_names
        )
        if not levels:
            levels = ("medium",)

    audits: list[pd.DataFrame] = []
    for level in levels:
        combined, audit = _append_one_fuel_price_scenario_to_chart_rows(
            combined,
            replay_or_audit,
            level=level,
        )
        audits.append(audit)
    return (
        combined.reset_index(drop=True),
        pd.concat(audits, ignore_index=True, sort=False)
        if audits
        else pd.DataFrame(columns=_FUEL_AUDIT_COLUMNS),
    )


# --------------------------------------------------------------------------
# P1.2: direct Treasury macro replay for every governed current scenario
# --------------------------------------------------------------------------

_DIRECT_SHADOW_SUFFIX = "__legacy_macro_shadow"


def direct_shadow_scenario_name(scenario_name: str) -> str:
    """The internal legacy-macro shadow identity for one governed scenario."""

    return f"{scenario_name}{_DIRECT_SHADOW_SUFFIX}"


@dataclass(frozen=True)
class DirectTreasuryScenarioReplayResult:
    """Per-scenario Treasury macro replay: every factor is scenario-specific.

    The historical ``TreasuryBaselineMacroReplayResult`` replayed only the
    Base pair and transferred Base-derived factors onto the comparison in
    output space - inexact for nonlinear GBM members and recursive lag
    models. Here every governed current scenario is replayed against its OWN
    legacy shadow, so ``baseline_macro_*_factors`` carry a real
    ``scenario_name`` key and a Base factor can never serve another scenario.
    """

    base_scenario_name: str
    scenario_names: tuple[str, ...]
    replay_inputs: pd.DataFrame
    replay: ScenarioInputForecastReplayResult
    baseline_macro_quarterly_factors: pd.DataFrame
    baseline_macro_annual_factors: pd.DataFrame
    scenario_replay_lineage: pd.DataFrame


def _macro_factor_frames_for_pair(
    replay: ScenarioInputForecastReplayResult,
    annual_bridge: pd.DataFrame,
    *,
    scenario_name: str,
    shadow_name: str,
    trace_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Treasury-vs-legacy factors for ONE scenario against its own shadow."""

    quarterly_source = replay.future_forecasts.copy()
    required_quarterly = {"scenario_name", "stream", "target_period", "forecast"}
    missing = required_quarterly.difference(quarterly_source.columns)
    if missing:
        raise ValueError(
            "Direct replay cannot build macro factors without columns: "
            + ", ".join(sorted(missing))
        )
    quarterly_source["forecast"] = pd.to_numeric(
        quarterly_source["forecast"], errors="coerce"
    )
    quarterly = quarterly_source[
        quarterly_source["scenario_name"].astype(str).isin([scenario_name, shadow_name])
    ].pivot_table(
        index=["stream", "target_period"],
        columns="scenario_name",
        values="forecast",
        aggfunc="first",
    ).reset_index()
    if scenario_name not in quarterly.columns or shadow_name not in quarterly.columns:
        raise ValueError(
            f"Direct replay is missing Treasury or legacy rows for {scenario_name!r}."
        )
    quarterly = quarterly.rename(
        columns={
            "target_period": "period",
            shadow_name: "base_value",
            scenario_name: "scenario_value",
        }
    ).dropna(subset=["base_value", "scenario_value"])
    quarterly["series_id"] = quarterly["stream"].astype(str).map(_STREAM_SERIES_IDS)
    if quarterly["series_id"].isna().any():
        raise ValueError(
            f"Direct replay factors for {scenario_name!r} contain an unknown stream."
        )
    quarterly["factor"] = np.where(
        quarterly["base_value"].abs() > 1e-12,
        quarterly["scenario_value"] / quarterly["base_value"],
        1.0,
    )
    quarterly["delta"] = quarterly["scenario_value"] - quarterly["base_value"]
    quarterly["scenario_name"] = scenario_name
    quarterly["trace_name"] = trace_name
    quarterly["time_grain"] = "quarterly"
    quarterly["transformation_basis"] = (
        "Treasury_BEFU26_scenario_replay_vs_own_legacy_macro_replay"
    )

    annual_source = annual_bridge.copy()
    required_annual = {"scenario_name", "FY", "series_id", "value"}
    missing = required_annual.difference(annual_source.columns)
    if missing:
        raise ValueError(
            "Direct replay annual bridge cannot build macro factors without columns: "
            + ", ".join(sorted(missing))
        )
    annual_source["value"] = pd.to_numeric(annual_source["value"], errors="coerce")
    annual = annual_source[
        annual_source["scenario_name"].astype(str).isin([scenario_name, shadow_name])
    ].pivot_table(
        index=["FY", "series_id"],
        columns="scenario_name",
        values="value",
        aggfunc="first",
    ).reset_index()
    if scenario_name not in annual.columns or shadow_name not in annual.columns:
        raise ValueError(
            f"Direct replay annual bridge is missing rows for {scenario_name!r}."
        )
    annual = annual.rename(
        columns={
            "FY": "june_year",
            shadow_name: "base_value",
            scenario_name: "scenario_value",
        }
    ).dropna(subset=["base_value", "scenario_value"])
    annual["factor"] = np.where(
        annual["base_value"].abs() > 1e-12,
        annual["scenario_value"] / annual["base_value"],
        1.0,
    )
    annual["delta"] = annual["scenario_value"] - annual["base_value"]
    annual["period"] = pd.to_numeric(annual["june_year"], errors="coerce").astype(
        "Int64"
    ).map(lambda fy: f"FY{int(fy)}" if pd.notna(fy) else "")
    annual["scenario_name"] = scenario_name
    annual["trace_name"] = trace_name
    annual["time_grain"] = "june_year"
    annual["transformation_basis"] = (
        "Treasury_BEFU26_scenario_annual_bridge_vs_own_legacy_annual_bridge"
    )
    return quarterly.reset_index(drop=True), annual.reset_index(drop=True)


def run_direct_treasury_scenario_replay(
    scenario_input_wide: pd.DataFrame,
    repo_root: Path | str,
    engine: str = "ensemble",
    *,
    latest_actual_period: str | None = None,
    bridge_vintage_id: str | None = None,
) -> DirectTreasuryScenarioReplayResult:
    """Replay every governed current scenario on its own Treasury inputs.

    For each scenario in ``scenario_input_wide`` this builds a
    Treasury-adjusted variant (input-space adjustment preserving the
    scenario's own differentials; see
    ``apply_treasury_macro_path_to_scenarios``) plus a legacy shadow of the
    scenario's unadjusted rows, replays the fixed promoted models over all of
    them in one pass, and derives per-scenario factor frames. MBU26 official
    rows are never part of this replay.
    """

    root = Path(repo_root)
    base_scenario_name, _ = _base_scenario_rows(scenario_input_wide)
    treasury_all = apply_treasury_macro_path_to_scenarios(scenario_input_wide, root)
    ordered_names = [base_scenario_name] + sorted(
        name
        for name in scenario_input_wide["scenario_name"].dropna().astype(str).unique()
        if name != base_scenario_name
    )
    frames: list[pd.DataFrame] = []
    replay_scenario_names: list[str] = []
    for scenario in ordered_names:
        treasury_rows = treasury_all[
            treasury_all["scenario_name"].astype(str).eq(scenario)
        ].copy()
        legacy_rows = scenario_input_wide[
            scenario_input_wide["scenario_name"].astype(str).eq(scenario)
        ]
        if treasury_rows.empty or legacy_rows.empty:
            raise ValueError(
                f"Scenario {scenario!r} has no input rows; a governed scenario "
                "must fail closed rather than borrow another scenario's replay."
            )
        shadow = _scenario_clone_with_identity(
            legacy_rows,
            scenario_name=direct_shadow_scenario_name(scenario),
            role="comparison",
            display_name=f"Internal legacy macro shadow ({scenario})",
        )
        frames.extend([treasury_rows, shadow])
        replay_scenario_names.extend([scenario, direct_shadow_scenario_name(scenario)])
    replay_inputs = pd.concat(frames, ignore_index=True, sort=False)
    replay = replay_forecast_from_scenario_inputs(
        replay_inputs,
        repo_root=root,
        engine=engine,
        latest_actual_period=latest_actual_period,
    )
    _validate_complete_numeric_replay(
        replay,
        replay_inputs=replay_inputs,
        scenario_names=tuple(replay_scenario_names),
    )
    annual_bridge, _ = _annual_bridge_and_factors(
        replay,
        replay_inputs=replay_inputs,
        repo_root=root,
        base_scenario_name=base_scenario_name,
        latest_actual_period=latest_actual_period,
        require_conflict_factors=False,
        isolate_non_ice_activity=False,
        bridge_vintage_id=bridge_vintage_id,
    )

    quarterly_frames: list[pd.DataFrame] = []
    annual_frames: list[pd.DataFrame] = []
    for scenario in ordered_names:
        trace = (
            "Current finalist Base case"
            if scenario == base_scenario_name
            else f"Current finalist comparison ({scenario})"
        )
        quarterly, annual = _macro_factor_frames_for_pair(
            replay,
            annual_bridge,
            scenario_name=scenario,
            shadow_name=direct_shadow_scenario_name(scenario),
            trace_name=trace,
        )
        if quarterly.empty or annual.empty:
            raise ValueError(
                f"Direct replay produced no factors for {scenario!r}; refusing "
                "to fall back to Base factors."
            )
        quarterly_frames.append(quarterly)
        annual_frames.append(annual)

    quarterly_factors = pd.concat(quarterly_frames, ignore_index=True, sort=False)
    annual_factors = pd.concat(annual_frames, ignore_index=True, sort=False)

    # Factor completeness: every scenario must cover the same quarterly
    # series/period grid as Base. A hole here means a scenario would silently
    # keep its legacy value under the overlay, which is the fail-open path
    # P1.2 exists to remove.
    base_grid = {
        (row.series_id, row.period)
        for row in quarterly_factors[
            quarterly_factors["scenario_name"].eq(base_scenario_name)
        ].itertuples()
    }
    for scenario in ordered_names[1:]:
        grid = {
            (row.series_id, row.period)
            for row in quarterly_factors[
                quarterly_factors["scenario_name"].eq(scenario)
            ].itertuples()
        }
        holes = sorted(base_grid.symmetric_difference(grid))
        if holes:
            raise ValueError(
                f"Scenario {scenario!r} factor grid does not match Base: {holes[:6]}"
            )

    lineage = _direct_replay_lineage(
        replay,
        replay_inputs=replay_inputs,
        scenario_names=tuple(ordered_names),
        base_scenario_name=base_scenario_name,
        engine=engine,
    )
    return DirectTreasuryScenarioReplayResult(
        base_scenario_name=base_scenario_name,
        scenario_names=tuple(ordered_names),
        replay_inputs=replay_inputs.reset_index(drop=True),
        replay=replay,
        baseline_macro_quarterly_factors=quarterly_factors,
        baseline_macro_annual_factors=annual_factors,
        scenario_replay_lineage=lineage,
    )


def _direct_replay_lineage(
    replay: ScenarioInputForecastReplayResult,
    *,
    replay_inputs: pd.DataFrame,
    scenario_names: tuple[str, ...],
    base_scenario_name: str,
    engine: str,
) -> pd.DataFrame:
    """One structured record per scenario/stream/quarter of the direct replay."""

    forecasts = replay.future_forecasts
    rows: list[dict[str, Any]] = []
    input_hash_by_scenario: dict[str, str] = {}
    for scenario in scenario_names:
        scoped = replay_inputs[
            replay_inputs["scenario_name"].astype(str).eq(scenario)
        ]
        hashes = sorted(
            scoped.get("workbook_sha256", pd.Series(dtype=str)).dropna().astype(str).unique()
        )
        input_hash_by_scenario[scenario] = ";".join(hashes)
    driver_columns = ("real_gdp_sa_nzd", "population", "real_gdp_per_capita_nzd")
    for scenario in scenario_names:
        shadow = direct_shadow_scenario_name(scenario)
        treasury = forecasts[forecasts["scenario_name"].astype(str).eq(scenario)]
        legacy = forecasts[forecasts["scenario_name"].astype(str).eq(shadow)]
        legacy_lookup = {
            (str(row.stream), str(row.target_period)): float(row.forecast)
            for row in legacy.itertuples()
            if pd.notna(getattr(row, "forecast", np.nan))
        }
        scenario_inputs = replay_inputs[
            replay_inputs["scenario_name"].astype(str).eq(scenario)
        ]
        shadow_inputs = replay_inputs[
            replay_inputs["scenario_name"].astype(str).eq(shadow)
        ]
        for row in treasury.itertuples():
            stream = str(row.stream)
            period = str(row.target_period)
            raw = legacy_lookup.get((stream, period))
            drivers_changed: list[str] = []
            treasury_quarter = scenario_inputs[
                scenario_inputs["stream"].astype(str).eq(stream)
                & scenario_inputs["canonical_period"].astype(str).eq(period)
            ]
            shadow_quarter = shadow_inputs[
                shadow_inputs["stream"].astype(str).eq(stream)
                & shadow_inputs["canonical_period"].astype(str).eq(period)
            ]
            if len(treasury_quarter) == 1 and len(shadow_quarter) == 1:
                for column in driver_columns:
                    if column not in treasury_quarter.columns:
                        continue
                    after = pd.to_numeric(treasury_quarter[column], errors="coerce").iloc[0]
                    before = pd.to_numeric(shadow_quarter[column], errors="coerce").iloc[0]
                    if pd.notna(after) and pd.notna(before) and not np.isclose(
                        float(after), float(before), rtol=1e-12, atol=0.0
                    ):
                        drivers_changed.append(
                            f"{column}:{float(before):.6g}->{float(after):.6g}"
                        )
            forecast_value = getattr(row, "forecast", np.nan)
            status = "replayed" if pd.notna(forecast_value) else "missing_forecast"
            rows.append(
                {
                    "scenario_name": scenario,
                    "scenario_role": (
                        "basecase" if scenario == base_scenario_name else "comparison"
                    ),
                    "stream": stream,
                    "period": period,
                    "engine": engine,
                    "input_workbook_sha256": input_hash_by_scenario.get(scenario, ""),
                    "drivers_changed": "; ".join(drivers_changed),
                    "raw_model_output": raw,
                    "post_macro_output": (
                        float(forecast_value) if pd.notna(forecast_value) else np.nan
                    ),
                    "replay_status": status,
                    "error_class": "",
                    "error_message": "",
                    "fallback_used": "none",
                }
            )
    return pd.DataFrame(rows)

"""Source-backed Iran-war input shock for the Revenue Outlook.

The scenario clones the governed Base-population ``scenario_input_wide`` rows,
raises real petrol/diesel inputs by 15% and the active real RUC-price inputs by
20% for six calendar quarters, and sends both Base and scenario rows through
the fixed-finalist replay engine.  The Light RUC one-quarter lag is rebuilt
from the shocked level path.  Chart rows are then derived from the Base trace
using exact replay/annual-bridge factors, while revenue aggregates receive the
sum of their affected leaf deltas.

This module does not mutate the committed Revenue Outlook pack.  It is a
runtime scenario layer, and its audit frames retain both the displayed values
and the published FED-path baseline when a FED policy overlay is active.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ev_uptake_levers import FED_AGGREGATE_SERIES, RUC_AGGREGATE_SERIES, TOTAL_AGGREGATE_SERIES
from .forecast_runner import (
    ScenarioInputForecastReplayResult,
    forecast_chart_rows_for_display,
    replay_forecast_from_scenario_inputs,
)
from .mbu26_source_spine import current_forecast_annual_from_mbu26, load_mbu26_annual_spine


IRAN_WAR_SCENARIO_NAME = "current_iran_war_fuel_15pct_ruc_20pct_6q"
IRAN_WAR_SCENARIO_TRACE_NAME = "Current finalist Iran war (+15% fuel, +20% RUC; 6 quarters)"
IRAN_WAR_SCENARIO_NOTE = (
    "Base-population finalist path with real petrol and diesel prices 15% above Base and active real RUC-price "
    "inputs 20% above Base from 2026Q1 through 2027Q2. Direct price levels return to Base from 2027Q3; the "
    "Light RUC one-quarter lag remains elevated in 2027Q3. Governed nominal revenue rates are unchanged, so "
    "RUC revenue moves only through the fixed-finalist activity response. Lagged and nonlinear model effects "
    "can persist or rebound after the direct shock ends."
)

# Backwards-compatible exports retained because the scenario module and its
# cache/UI plumbing pre-date the broader Iran-war definition.
FUEL_PRICE_SCENARIO_NAME = IRAN_WAR_SCENARIO_NAME
FUEL_PRICE_SCENARIO_TRACE_NAME = IRAN_WAR_SCENARIO_TRACE_NAME
FUEL_PRICE_SCENARIO_NOTE = IRAN_WAR_SCENARIO_NOTE

FUEL_PRICE_MULTIPLIER = 1.15
RUC_PRICE_MULTIPLIER = 1.20
FUEL_PRICE_SHOCK_PERIODS = (
    "2026Q1",
    "2026Q2",
    "2026Q3",
    "2026Q4",
    "2027Q1",
    "2027Q2",
)
RUC_PRICE_SHOCK_PERIODS = FUEL_PRICE_SHOCK_PERIODS
RUC_PRICE_LAGGED_EFFECT_PERIODS = (
    "2026Q2",
    "2026Q3",
    "2026Q4",
    "2027Q1",
    "2027Q2",
    "2027Q3",
)

_BASE_SCENARIO_NAME = "current_basecase"
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
_LIGHT_RUC_LAGGED_PRICE_FIELD = "lagged_real_light_ruc_price_nzd_per_1000km"
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
    fuel_scenario_inputs: pd.DataFrame
    replay_inputs: pd.DataFrame
    replay: ScenarioInputForecastReplayResult
    input_audit: pd.DataFrame
    quarterly_factors: pd.DataFrame
    annual_factors: pd.DataFrame
    annual_bridge: pd.DataFrame

    @property
    def future_forecasts(self) -> pd.DataFrame:
        return self.replay.future_forecasts

    @property
    def assumptions(self) -> pd.DataFrame:
        return self.replay.assumptions

    @property
    def validation_report(self) -> pd.DataFrame:
        return self.replay.validation_report


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


def build_fuel_price_scenario_inputs(base_inputs: pd.DataFrame) -> pd.DataFrame:
    """Clone Base and apply the governed six-quarter fuel and RUC price shocks."""

    _, scenario = _base_scenario_rows(base_inputs)
    scenario = scenario.copy()
    scenario["scenario_name"] = FUEL_PRICE_SCENARIO_NAME
    scenario["role"] = "comparison"
    if "scenario_role" in scenario.columns:
        scenario["scenario_role"] = "comparison"
    scenario["scenario_display_name"] = FUEL_PRICE_SCENARIO_TRACE_NAME
    if "source_artifact" in scenario.columns:
        scenario["source_artifact"] = "runtime_iran_war_scenario:base_clone"

    period = scenario["canonical_period"].astype(str)
    stream = scenario["stream"].astype(str)
    shock_period = period.isin(FUEL_PRICE_SHOCK_PERIODS)
    for stream_name, field in _STREAM_PRICE_FIELDS.items():
        if field not in scenario.columns:
            raise ValueError(f"Base scenario_input_wide is missing required fuel-price field {field!r}.")
        # Committed Parquet inputs can use Arrow-backed string columns.  Keep
        # non-target cells byte-for-byte equivalent while allowing the six
        # governed cells to hold numeric scenario values.
        scenario[field] = scenario[field].astype(object)
        mask = shock_period & stream.eq(stream_name)
        values = pd.to_numeric(scenario.loc[mask, field], errors="coerce")
        if len(values) != len(FUEL_PRICE_SHOCK_PERIODS) or values.isna().any():
            raise ValueError(
                f"Expected one numeric {field} value for every shock quarter in stream {stream_name}; "
                f"found {len(values)} rows with {int(values.isna().sum())} non-numeric values."
            )
        scenario.loc[mask, field] = values.to_numpy(dtype=float) * FUEL_PRICE_MULTIPLIER

    for stream_name, fields in _STREAM_RUC_PRICE_FIELDS.items():
        for field in fields:
            if field not in scenario.columns:
                raise ValueError(f"Base scenario_input_wide is missing required RUC-price field {field!r}.")
            scenario[field] = scenario[field].astype(object)
            mask = shock_period & stream.eq(stream_name)
            values = pd.to_numeric(scenario.loc[mask, field], errors="coerce")
            if len(values) != len(RUC_PRICE_SHOCK_PERIODS) or values.isna().any():
                raise ValueError(
                    f"Expected one numeric {field} value for every shock quarter in stream {stream_name}; "
                    f"found {len(values)} rows with {int(values.isna().sum())} non-numeric values."
                )
            scenario.loc[mask, field] = values.to_numpy(dtype=float) * RUC_PRICE_MULTIPLIER

    # The Light finalist consumes both the current real RUC price and an
    # explicit one-quarter lag.  Rebuild that lag from the shocked current
    # path: Q1 retains the pre-shock lag, while the final elevated lag lands in
    # 2027Q3 after direct prices have reverted.  Heavy vNext engineers its own
    # dynamics from direct levels and does not consume the template lag/lead
    # helper fields.
    if _LIGHT_RUC_LAGGED_PRICE_FIELD not in scenario.columns:
        raise ValueError(
            "Base scenario_input_wide is missing required Light RUC lag field "
            f"{_LIGHT_RUC_LAGGED_PRICE_FIELD!r}."
        )
    scenario[_LIGHT_RUC_LAGGED_PRICE_FIELD] = scenario[_LIGHT_RUC_LAGGED_PRICE_FIELD].astype(object)
    for source_period, target_period in zip(RUC_PRICE_SHOCK_PERIODS, RUC_PRICE_LAGGED_EFFECT_PERIODS, strict=True):
        source_mask = stream.eq("LIGHT_RUC") & period.eq(source_period)
        target_mask = stream.eq("LIGHT_RUC") & period.eq(target_period)
        source_value = pd.to_numeric(scenario.loc[source_mask, "real_light_ruc_price_nzd_per_1000km"], errors="coerce")
        if len(source_value) != 1 or source_value.isna().any() or int(target_mask.sum()) != 1:
            raise ValueError(
                "Could not align the Light RUC lagged price path for "
                f"{source_period} -> {target_period}."
            )
        scenario.loc[target_mask, _LIGHT_RUC_LAGGED_PRICE_FIELD] = float(source_value.iloc[0])

    return scenario.reset_index(drop=True)


def _input_change_audit(base_rows: pd.DataFrame, scenario_rows: pd.DataFrame, base_scenario_name: str) -> pd.DataFrame:
    base = base_rows.set_index(["stream", "canonical_period"])
    scenario = scenario_rows.set_index(["stream", "canonical_period"])
    rows: list[dict[str, Any]] = []
    def add_row(stream: str, period: str, field: str, shock_component: str) -> None:
        key = (stream, period)
        base_value = float(pd.to_numeric(pd.Series([base.at[key, field]]), errors="coerce").iloc[0])
        scenario_value = float(pd.to_numeric(pd.Series([scenario.at[key, field]]), errors="coerce").iloc[0])
        rows.append(
            {
                "base_scenario_name": base_scenario_name,
                "scenario_name": FUEL_PRICE_SCENARIO_NAME,
                "scenario_display_name": FUEL_PRICE_SCENARIO_TRACE_NAME,
                "stream": stream,
                "canonical_period": period,
                "field": field,
                "shock_component": shock_component,
                "base_value": base_value,
                "scenario_value": scenario_value,
                "multiplier": scenario_value / base_value,
                "delta": scenario_value - base_value,
                "scenario_note": FUEL_PRICE_SCENARIO_NOTE,
            }
        )

    for stream, field in _STREAM_PRICE_FIELDS.items():
        for period in FUEL_PRICE_SHOCK_PERIODS:
            add_row(stream, period, field, "fuel_price_plus_15pct")
    for stream, fields in _STREAM_RUC_PRICE_FIELDS.items():
        for field in fields:
            for period in RUC_PRICE_SHOCK_PERIODS:
                add_row(stream, period, field, "ruc_price_plus_20pct")
    for period in RUC_PRICE_LAGGED_EFFECT_PERIODS:
        add_row("LIGHT_RUC", period, _LIGHT_RUC_LAGGED_PRICE_FIELD, "light_ruc_one_quarter_lag")
    return pd.DataFrame(rows)


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
    source = source[source["scenario_name"].astype(str).isin([base_scenario_name, FUEL_PRICE_SCENARIO_NAME])].copy()
    pivot = source.pivot_table(
        index=["stream", "target_period"],
        columns="scenario_name",
        values="forecast_numeric",
        aggfunc="first",
    ).reset_index()
    if base_scenario_name not in pivot or FUEL_PRICE_SCENARIO_NAME not in pivot:
        raise ValueError("Replay did not produce both Base and Iran-war scenario forecasts.")
    pivot = pivot.rename(
        columns={
            base_scenario_name: "base_value",
            FUEL_PRICE_SCENARIO_NAME: "scenario_value",
            "target_period": "period",
        }
    )
    pivot = pivot.dropna(subset=["base_value", "scenario_value"]).copy()
    if pivot.empty or (pivot["base_value"].abs() <= 1e-12).any():
        raise ValueError("Replay produced empty or zero Base forecasts, so scenario factors cannot be calculated.")
    pivot["factor"] = pivot["scenario_value"] / pivot["base_value"]
    pivot["delta"] = pivot["scenario_value"] - pivot["base_value"]
    pivot["series_id"] = pivot["stream"].astype(str).map(_STREAM_SERIES_IDS)
    pivot["time_grain"] = "quarterly"
    pivot["scenario_name"] = FUEL_PRICE_SCENARIO_NAME
    pivot["scenario_note"] = FUEL_PRICE_SCENARIO_NOTE
    return pivot[
        [
            "scenario_name",
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
    ].sort_values(["stream", "period"], kind="stable").reset_index(drop=True)


def _annual_bridge_and_factors(
    replay: ScenarioInputForecastReplayResult,
    *,
    replay_inputs: pd.DataFrame,
    repo_root: Path,
    base_scenario_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    quarterly = forecast_chart_rows_for_display(replay.future_forecasts, repo_root=repo_root)
    if quarterly.empty:
        raise ValueError("Replay produced no chartable quarterly rows.")
    quarterly["time_grain"] = "quarterly"
    quarterly["metric_type"] = "activity"
    quarterly["scenario_role"] = quarterly["scenario_name"].astype(str).map(
        {
            base_scenario_name: "basecase",
            FUEL_PRICE_SCENARIO_NAME: "comparison",
            "historical_actual": "actual",
        }
    ).fillna("")

    mbu26 = load_mbu26_annual_spine(repo_root=repo_root)
    if mbu26 is None or mbu26.official_annual.empty:
        raise ValueError("The committed MBU26 annual spine is required to bridge replay activity into revenue.")
    annual = current_forecast_annual_from_mbu26(
        current_outlook_chart_rows=quarterly,
        mbu26_official_annual=mbu26.official_annual,
        scenario_input_wide=replay_inputs,
    )
    if annual.empty:
        raise ValueError("The Iran-war replay could not be bridged to annual Revenue Outlook rows.")

    values = annual[
        annual["scenario_name"].astype(str).isin([base_scenario_name, FUEL_PRICE_SCENARIO_NAME])
    ].copy()
    values["value_numeric"] = pd.to_numeric(values["value"], errors="coerce")
    pivot = values.pivot_table(
        index=["FY", "series_id"],
        columns="scenario_name",
        values="value_numeric",
        aggfunc="first",
    ).reset_index()
    if base_scenario_name not in pivot or FUEL_PRICE_SCENARIO_NAME not in pivot:
        raise ValueError("Annual bridge did not produce both Base and Iran-war scenario rows.")
    factors = pivot.rename(
        columns={base_scenario_name: "base_value", FUEL_PRICE_SCENARIO_NAME: "scenario_value", "FY": "june_year"}
    ).dropna(subset=["base_value", "scenario_value"])
    factors["factor"] = np.where(
        factors["base_value"].abs() > 1e-12,
        factors["scenario_value"] / factors["base_value"],
        1.0,
    )
    factors["delta"] = factors["scenario_value"] - factors["base_value"]
    factors["period"] = factors["june_year"].astype(int).map(lambda value: f"FY{value}")
    factors["time_grain"] = "june_year"
    factors["scenario_name"] = FUEL_PRICE_SCENARIO_NAME
    factors["scenario_note"] = FUEL_PRICE_SCENARIO_NOTE
    factors = factors[
        [
            "scenario_name",
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
    ].sort_values(["series_id", "june_year"], kind="stable").reset_index(drop=True)
    return annual.reset_index(drop=True), factors


def run_fuel_price_scenario_replay(
    base_inputs: pd.DataFrame,
    repo_root: Path | str,
    engine: str = "ensemble",
) -> FuelPriceScenarioReplayResult:
    """Build and score the six-quarter Iran-war scenario with fixed finalists."""

    root = Path(repo_root)
    base_scenario_name, base_rows = _base_scenario_rows(base_inputs)
    fuel_rows = build_fuel_price_scenario_inputs(base_inputs)
    replay_inputs = pd.concat([base_rows, fuel_rows], ignore_index=True, sort=False)
    replay = replay_forecast_from_scenario_inputs(
        replay_inputs,
        repo_root=root,
        engine=engine,
    )
    validation = replay.validation_report.copy()
    if validation.empty or not validation["valid"].fillna(False).all():
        details = validation[[column for column in ["scenario_name", "errors"] if column in validation.columns]].to_dict("records")
        raise ValueError(f"Fixed-finalist Iran-war replay failed validation: {details}")
    input_audit = _input_change_audit(base_rows, fuel_rows, base_scenario_name)
    quarterly_factors = _quarterly_factor_audit(replay, base_scenario_name=base_scenario_name)
    annual_bridge, annual_factors = _annual_bridge_and_factors(
        replay,
        replay_inputs=replay_inputs,
        repo_root=root,
        base_scenario_name=base_scenario_name,
    )
    return FuelPriceScenarioReplayResult(
        base_scenario_name=base_scenario_name,
        fuel_scenario_inputs=fuel_rows,
        replay_inputs=replay_inputs,
        replay=replay,
        input_audit=input_audit,
        quarterly_factors=quarterly_factors,
        annual_factors=annual_factors,
        annual_bridge=annual_bridge,
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
) -> dict[str, float]:
    """Allocate an annual value delta using signed native replay activity deltas."""

    if abs(annual_delta) <= 1e-12:
        return {period: 0.0 for period in quarters}
    raw = np.array(
        [quarterly_delta_lookup.get((activity_series_id, period), 0.0) for period in quarters],
        dtype=float,
    )
    raw = np.where(np.isfinite(raw), raw, 0.0)
    denominator = float(raw.sum())
    if abs(denominator) > 1e-12:
        allocated = annual_delta * raw / denominator
    else:
        weights = np.abs(raw)
        if float(weights.sum()) <= 1e-12:
            # This is a defensive fallback only. Governed affected series have
            # native replay deltas for every forecast quarter.
            weights = np.ones(len(quarters), dtype=float)
        allocated = annual_delta * weights / float(weights.sum())
    # Remove floating accumulation drift so every displayed June year remains
    # an exact benchmark after the quarterly scenario layer is applied.
    residual = annual_delta - float(allocated.sum())
    allocated[int(np.argmax(np.abs(allocated)))] += residual
    return {period: float(value) for period, value in zip(quarters, allocated, strict=True)}


def _attach_quarterly_delta_lineage(
    scenario: pd.DataFrame,
    quarterly_delta_lookup: dict[tuple[str, str], float],
) -> pd.DataFrame:
    """Attach exact scenario-vs-Base quarterly revenue-delta maps to annual rows."""

    out = scenario.copy()
    out["_fuel_quarterly_value_deltas"] = ""
    out["_fuel_affected_quarters"] = ""
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
            if activity_series:
                maps_by_series[series_id] = _allocate_annual_delta_to_quarters(
                    annual_delta,
                    quarters,
                    activity_series,
                    quarterly_delta_lookup,
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
                    active = [period for period, value in delta_map.items() if abs(value) > 1e-12]
                    target = max(active, key=lambda period: abs(delta_map[period])) if active else quarters[-1]
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
    text = str(unit or "").strip().casefold()
    if "billion" in text or text.startswith("$b"):
        return 1_000_000_000.0
    if "million" in text or text.startswith("$m"):
        return 1_000_000.0
    if "thousand" in text or "'000" in text:
        return 1_000.0
    return 1.0


def _reconcile_native_activity_quarters_to_annual(scenario: pd.DataFrame) -> pd.DataFrame:
    """Reconcile Base-plus-replay quarters to unchanged annual checkpoints.

    The immutable replay delta is applied first to every adjusted Base
    quarter.  The governed annual bridge remains authoritative, so any small
    difference introduced by rebasing Base is recorded as a separate annual-
    reconciliation layer and allocated only across quarters where the replay
    itself responds.  Pre-shock quarters therefore stay equal to Base, and
    the six-quarter shock/post-shock timing remains intact.
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

        active_positions = np.flatnonzero(np.abs(quarterly_delta_base) > 1e-12)
        if len(active_positions):
            basis = "fixed_finalist_quarterly_replay_delta_plus_annual_reconciliation"
            weights = np.abs(quarterly_delta_base[active_positions])
        else:
            # The governed annual bridge can retain a post-shock composition
            # effect after the native quarterly finalist has returned exactly
            # to Base (for example Light RUC FY2029).  Preserve that annual
            # checkpoint using the adjusted Base within-FY shape and expose it
            # explicitly as annual-bridge-only provenance.
            active_positions = np.arange(len(quarterly_indices), dtype=int)
            weights = np.array(
                [
                    abs(float(source_value.at[index]) * _display_unit_scale(units.at[index]))
                    for index in quarterly_indices
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
                "Iran-war quarterly activity failed annual reconciliation: "
                f"{annual_series} FY{annual_fy}."
            )
    return out


def append_fuel_price_scenario_to_chart_rows(
    chart_rows: pd.DataFrame,
    replay_or_audit: FuelPriceScenarioReplayResult | pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append a distinct Iran-war trace to Base-derived chart rows.

    The function is idempotent: an existing runtime Iran-war scenario is replaced.
    Quarterly non-aggregate rows inherit the current Base path plus immutable
    fixed-finalist replay deltas, with an explicit reconciliation layer back
    to the unchanged annual-bridge checkpoints. Annual non-aggregate rows
    retain their governed bridge factors. FED, RUC and whole-of-NLTF
    aggregates receive the sum of the affected leaf deltas, keeping fixed
    revenue components unchanged.
    """

    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame(columns=_FUEL_AUDIT_COLUMNS)
    base_scenario_name, quarterly_factors, annual_factors = _factor_frames(replay_or_audit)
    source = chart_rows[~chart_rows["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)].copy()
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
        if series_id in aggregate_series:
            continue
        factor, basis = _lookup_factor(row, quarterly_lookup=q_lookup, annual_lookup=a_lookup)
        grain = str(row.get("time_grain") or "")
        delta: float | None = None
        if grain == "quarterly":
            delta = q_delta_lookup.get((series_id, str(row.get("period") or "")))
            if delta is not None:
                # Replay activity deltas are stored in their native base
                # units (raw net km for RUC).  The uptake bridge may already
                # have normalised the displayed quarter to million km.
                delta = float(delta) / _display_unit_scale(row.get("value_unit"))
                basis = "fixed_finalist_quarterly_replay_delta"
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
                float(published.at[index]) + float(delta)
                if delta is not None
                else float(published.at[index]) * factor
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
        for index in group.index:
            series_id = str(scenario.at[index, "series_id"])
            if series_id in RUC_AGGREGATE_SERIES:
                current_delta, published_delta, basis = ruc_current_delta, ruc_published_delta, "additive_ruc_leaf_delta"
            elif series_id in FED_AGGREGATE_SERIES:
                current_delta, published_delta, basis = ped_current_delta, ped_published_delta, "additive_fed_leaf_delta"
            elif series_id in TOTAL_AGGREGATE_SERIES:
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

    scenario = _reconcile_native_activity_quarters_to_annual(scenario)
    scenario = _attach_quarterly_delta_lineage(scenario, q_delta_lookup)

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

    scenario["scenario_name"] = FUEL_PRICE_SCENARIO_NAME
    scenario["scenario_role"] = "comparison"
    scenario["trace_name"] = FUEL_PRICE_SCENARIO_TRACE_NAME
    if "trace_type" in scenario.columns:
        scenario["trace_type"] = "current finalist Iran war scenario"
    if "trace_role" in scenario.columns:
        scenario["trace_role"] = "comparison"
    if "trace_source" in scenario.columns:
        scenario["trace_source"] = "fixed-finalist Iran-war replay"
    scenario["fuel_price_scenario"] = True
    scenario["fuel_price_scenario_note"] = FUEL_PRICE_SCENARIO_NOTE
    scenario["iran_war_scenario"] = True
    scenario["iran_war_scenario_note"] = FUEL_PRICE_SCENARIO_NOTE
    scenario["_fuel_baseline_value"] = scenario["_fuel_source_value"]
    scenario["_fuel_value_delta"] = (
        pd.to_numeric(scenario["_fuel_adjusted_value"], errors="coerce")
        - pd.to_numeric(scenario["_fuel_source_value"], errors="coerce")
    )
    if "canonical_scenario_key" in scenario.columns:
        scenario["canonical_scenario_key"] = FUEL_PRICE_SCENARIO_NAME
    if "canonical_join_key" in scenario.columns:
        period_key = scenario.get("canonical_period_key", scenario.get("period", pd.Series("", index=scenario.index))).astype(str)
        stream_key = scenario.get("canonical_stream_key", scenario.get("stream", pd.Series("", index=scenario.index))).astype(str)
        scenario["canonical_join_key"] = stream_key + "|" + period_key + "|" + FUEL_PRICE_SCENARIO_NAME

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
                "scenario_name": FUEL_PRICE_SCENARIO_NAME,
                "scenario_role": "comparison",
                "trace_name": FUEL_PRICE_SCENARIO_TRACE_NAME,
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
                "scenario_note": FUEL_PRICE_SCENARIO_NOTE,
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

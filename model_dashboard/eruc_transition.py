"""FED -> e-RUC transition simulator for the light petrol fleet.

Simulates the policy where petrol light vehicles stop paying fuel excise
(PED) and are enrolled onto electronic road user charges. The finalist
Light RUC model was estimated on the diesel light fleet and cannot natively
price the enlarged pool, so the simulator keeps the PED VKT-per-capita
finalist as the *demand* engine for petrol kilometres (driver behaviour does
not change identity with the tax instrument) and swaps the *pricing* layer:

- migrated petrol km leave the excise base (litres x PED rate) and are
  charged at an adjustable e-RUC rate anchored to the MBU26 conventional
  light RUC rate path;
- the pump-price channel stays live: removing excise cuts the fuel cost per
  km while the new e-RUC charge adds a per-km cost, and migrated demand
  responds to the NET change in running cost per km through a fuel-price
  elasticity of VKT (default -0.15, the standard short/medium-run range).

Applied as a display-time overlay after the EV uptake levers: governed pack
bytes are untouched and every adjusted row is tagged for audit.
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

ERUC_NOTE = (
    "e-RUC transition: migrated petrol km leave the excise base and are "
    "charged per km at the e-RUC rate. Demand for migrated km responds to "
    "the net change in running cost per km (excise removed at the pump, "
    "e-RUC added) through the VKT elasticity, so the tax-free pump price "
    "keeps its bearing on light RUC VKT. The Light RUC finalist is not "
    "re-estimated; petrol demand stays on the PED finalist. Display-time "
    "overlay - the governed pack is unchanged."
)

PED_FAMILY_SERIES = ("ped_vkt_per_capita", "ped_volume")
PED_REVENUE_SERIES = "gross_ped_revenue"
LIGHT_KM_SERIES = "light_ruc_net_km"
LIGHT_REVENUE_SERIES = "light_ruc_net_revenue"


@dataclass(frozen=True)
class ErucTransitionLevers:
    start_fy: float = 2027.0  # first June year of enrollment
    phase_in_years: float = 3.0  # linear ramp to full migration
    eruc_rate_ratio: float = 1.0  # e-RUC rate as a multiple of the light RUC rate
    vkt_elasticity: float = -0.15  # VKT response to % change in running cost/km
    pump_price_nzd_per_litre: float = 2.70  # petrol pump price incl. excise

    def key(self) -> tuple[float, ...]:
        return tuple(round(float(v), 6) for v in asdict(self).values())


def migration_share(june_year: float, levers: ErucTransitionLevers) -> float:
    """Share of the petrol fleet enrolled on e-RUC in the given June year."""
    years = max(float(levers.phase_in_years), 1.0)
    return float(np.clip((float(june_year) - float(levers.start_fy) + 1.0) / years, 0.0, 1.0))


def migrated_demand_factor(
    levers: ErucTransitionLevers, *, excise_per_litre: float, litres_per_100km: float, eruc_rate_per_km: float
) -> float:
    """Demand response of migrated km to the net running-cost change.

    cost/km before: pump price x litres/100km / 100 (excise inside the pump
    price). After: tax-free fuel cost plus the e-RUC per-km charge.
    """
    pump = max(float(levers.pump_price_nzd_per_litre), 0.01)
    intensity = max(float(litres_per_100km), 0.01) / 100.0
    cost_before = pump * intensity
    cost_after = max(pump - float(excise_per_litre), 0.0) * intensity + float(eruc_rate_per_km)
    if cost_before <= 0:
        return 1.0
    relative_change = cost_after / cost_before - 1.0
    return float(np.clip(1.0 + float(levers.vkt_elasticity) * relative_change, 0.25, 4.0))


def _drift_ped_lookup(drift: pd.DataFrame) -> dict[tuple[str, int], dict[str, float]]:
    if drift is None or drift.empty or "lambda_mode" not in drift.columns:
        return {}
    rows = drift[drift["lambda_mode"].astype(str).eq("optimized")]
    lookup: dict[tuple[str, int], dict[str, float]] = {}
    for record in rows.itertuples():
        fy = pd.to_numeric(pd.Series([record.FY]), errors="coerce").iloc[0]
        if pd.isna(fy):
            continue
        lookup[(str(record.scenario_name), int(fy))] = {
            "excise_per_litre": float(getattr(record, "ped_rate", float("nan"))),
            "litres_per_100km": float(getattr(record, "ped_litres_per_100km", float("nan"))),
            "light_ruc_rate_per_km": float(getattr(record, "conventional_light_rate", float("nan"))),
        }
    return lookup


def apply_eruc_transition_to_chart_rows(
    chart_rows: pd.DataFrame,
    drift_assumptions: pd.DataFrame,
    levers: ErucTransitionLevers,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Move petrol km from the excise regime onto e-RUC (display overlay)."""
    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame()
    lookup = _drift_ped_lookup(drift_assumptions)
    if not lookup:
        return chart_rows, pd.DataFrame()

    data = chart_rows.copy()
    numeric_value = pd.to_numeric(data.get("value"), errors="coerce")
    june_year = pd.to_numeric(data.get("june_year"), errors="coerce")
    is_june = data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")
    is_forecast = ~data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("historical_actual")

    def _row_value(mask: pd.Series) -> float | None:
        if not mask.any() or not numeric_value[mask].notna().any():
            return None
        return float(numeric_value[mask].iloc[0])

    audit_rows: list[dict[str, Any]] = []
    fed_delta: dict[tuple[str, int], float] = {}
    ruc_delta: dict[tuple[str, int], float] = {}
    for (scenario, fy), rates in lookup.items():
        share = migration_share(fy, levers)
        if share <= 0 or any(not np.isfinite(v) for v in rates.values()):
            continue
        eruc_rate = rates["light_ruc_rate_per_km"] * float(levers.eruc_rate_ratio)
        demand = migrated_demand_factor(
            levers,
            excise_per_litre=rates["excise_per_litre"],
            litres_per_100km=rates["litres_per_100km"],
            eruc_rate_per_km=eruc_rate,
        )
        scenario_mask = data.get("scenario_name", pd.Series("", index=data.index)).astype(str).eq(scenario)
        base_mask = is_june & is_forecast & scenario_mask & june_year.eq(fy)
        volume_mask = base_mask & data["series_id"].astype(str).eq("ped_volume")
        old_volume = _row_value(volume_mask)
        if old_volume is None or old_volume <= 0:
            continue
        intensity = rates["litres_per_100km"] / 100.0
        petrol_km = old_volume / intensity
        km_migrated = petrol_km * share * demand
        km_remaining = petrol_km * (1.0 - share)
        km_total_new = km_remaining + km_migrated
        vkt_factor = km_total_new / petrol_km

        # PED family: volume follows total petrol km (fuel is still burned);
        # the excise base shrinks to the non-migrated share only.
        data.loc[volume_mask, "value"] = km_total_new * intensity
        vktpc_mask = base_mask & data["series_id"].astype(str).eq("ped_vkt_per_capita")
        old_vktpc = _row_value(vktpc_mask)
        if old_vktpc is not None:
            data.loc[vktpc_mask, "value"] = old_vktpc * vkt_factor
        excise_mask = base_mask & data["series_id"].astype(str).eq(PED_REVENUE_SERIES)
        old_excise = _row_value(excise_mask)
        new_excise = km_remaining * intensity * rates["excise_per_litre"]
        if old_excise is not None:
            data.loc[excise_mask, "value"] = new_excise
            fed_delta[(scenario, fy)] = new_excise - old_excise

        # Light RUC pool: migrated petrol km join and pay the e-RUC rate.
        light_km_mask = base_mask & data["series_id"].astype(str).eq(LIGHT_KM_SERIES)
        old_light_km = _row_value(light_km_mask)
        if old_light_km is not None:
            data.loc[light_km_mask, "value"] = old_light_km + km_migrated
        light_rev_mask = base_mask & data["series_id"].astype(str).eq(LIGHT_REVENUE_SERIES)
        old_light_rev = _row_value(light_rev_mask)
        eruc_revenue = km_migrated * eruc_rate
        if old_light_rev is not None:
            data.loc[light_rev_mask, "value"] = old_light_rev + eruc_revenue
            ruc_delta[(scenario, fy)] = eruc_revenue

        audit_rows.append(
            {
                "scenario_name": scenario,
                "june_year": fy,
                "migration_share": share,
                "migrated_demand_factor": demand,
                "petrol_km_million": petrol_km,
                "km_migrated_million": km_migrated,
                "excise_revenue_delta": fed_delta.get((scenario, fy), 0.0),
                "eruc_revenue_gained": eruc_revenue,
                "net_nltf_delta": fed_delta.get((scenario, fy), 0.0) + eruc_revenue,
                "excise_c_per_km": rates["excise_per_litre"] * rates["litres_per_100km"],
                "eruc_c_per_km": eruc_rate * 100.0,
            }
        )

    if fed_delta or ruc_delta:
        aggregate_mask = (
            is_june
            & is_forecast
            & data["series_id"].astype(str).isin(
                set(FED_AGGREGATE_SERIES) | set(RUC_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
            )
        )
        for index in data.index[aggregate_mask]:
            if pd.isna(numeric_value.at[index]):
                continue
            key = (str(data.at[index, "scenario_name"]), int(june_year.at[index]) if pd.notna(june_year.at[index]) else -1)
            series_id = str(data.at[index, "series_id"])
            delta = 0.0
            if series_id in FED_AGGREGATE_SERIES or series_id in TOTAL_AGGREGATE_SERIES:
                delta += fed_delta.get(key, 0.0)
            if series_id in RUC_AGGREGATE_SERIES or series_id in TOTAL_AGGREGATE_SERIES:
                delta += ruc_delta.get(key, 0.0)
            if delta:
                data.at[index, "value"] = float(numeric_value.at[index]) + delta

    touched_series = (
        set(PED_FAMILY_SERIES)
        | {PED_REVENUE_SERIES, LIGHT_KM_SERIES, LIGHT_REVENUE_SERIES}
        | set(FED_AGGREGATE_SERIES)
        | set(RUC_AGGREGATE_SERIES)
        | set(TOTAL_AGGREGATE_SERIES)
    )
    touched = is_june & is_forecast & data["series_id"].astype(str).isin(touched_series) & june_year.ge(levers.start_fy)
    if "value_status" in data.columns:
        data.loc[touched, "value_status"] = "eruc_transition"
    if "data_scope" in data.columns:
        data.loc[touched, "data_scope"] = "eruc_transition_overlay"
    return data, pd.DataFrame(audit_rows)

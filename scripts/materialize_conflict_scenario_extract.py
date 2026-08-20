"""Materialize the governed AR(1) conflict-scenario workbook source tables.

This command deliberately calls the same ``run_fuel_price_scenario_replay``
entry point as the dashboard.  It does not recreate scenario arithmetic in an
export-only code path.  Four deterministic CSVs are written:

* ``conflict_scenario_assumptions.csv`` - nominal source paths and the exact
  real-price and macro model inputs for the 12 exported policy paths;
* ``conflict_scenario_annual_revenue.csv`` - every FY2026-FY2030 annual
  revenue row from the governed replay bridge;
* ``conflict_scenario_annual_activity.csv`` - every FY2026-FY2030 annual
  activity/volume row from the governed replay bridge;
* ``conflict_scenario_validation.csv`` - machine-readable invariant checks.

The source fuel paths are policy-free. Original, delayed and no-uplift 12c FED
and matching RUC policy states are exposed separately; policy changes are
never embedded in the nominal conflict-price CSV.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import pandas as pd

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from model_dashboard.conflict_fuel_paths import (
    CONFLICT_SEVERITIES,
    SOURCE_WORKBOOK_NAME,
    SOURCE_WORKBOOK_SHA256,
    conflict_policy_variant_name,
    conflict_scenario_display_name,
    conflict_scenario_name,
    conflict_scenario_note,
    load_conflict_fuel_price_paths,
)
from model_dashboard.engine import ENGINE_AR1, engine_revenue_outlook_dir
from model_dashboard.ev_uptake_levers import (
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_PRESETS,
    apply_uptake_levers_to_chart_rows,
)
from model_dashboard.conflict_fuel_paths import BASE_POLICY_VARIANT_IDS
from model_dashboard.fuel_price_scenario import (
    BASE_PUBLISHED_SCENARIO_NAME,
    POLICY_PATH_IDS,
    apply_treasury_macro_to_chart_rows,
    append_fuel_price_scenario_to_chart_rows,
    run_direct_treasury_scenario_replay,
    run_fuel_price_scenario_replay,
)
from model_dashboard.mbu26_source_spine import (
    CURRENT_LIGHT_TOTAL_SERIES_ID,
    FORMULA_DEFINITIONS,
    ROW_DEFINITIONS,
)
from model_dashboard.fed_policy_states import FED_POLICY_SPECS
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    FED_POLICY_STATE_PUBLISHED,
    apply_fed_policy_state_to_chart_rows,
    fed_policy_annual_factors,
    mbu26_ruc_class_revenue_by_fy,
)
from model_dashboard.revenue_outlook import (
    PED_BRIDGE_DEFAULT_MODE,
    apply_ped_bridge_mode_layer,
    load_revenue_outlook_pack,
)


START_FY = 2026
END_FY = 2030
# v4: the timing dimension expanded from three states (original, deferred six
# months, off) to eight (original, 6-36 month deferrals in six-month steps,
# off); 32 paths in total. Values on the original twelve paths are unchanged.
EXTRACT_VERSION = "governed-ar1-conflict-scenario-extract-v4"
ASSUMPTIONS_FILENAME = "conflict_scenario_assumptions.csv"
REVENUE_FILENAME = "conflict_scenario_annual_revenue.csv"
ACTIVITY_FILENAME = "conflict_scenario_annual_activity.csv"
VALIDATION_FILENAME = "conflict_scenario_validation.csv"
VALUE_TOLERANCE = 1e-8

# Registry-driven: one label per governed timing state, in display order.
_POLICY_LABELS = {
    spec.calculation_state_id: spec.timing_label for spec in FED_POLICY_SPECS
}
_POLICY_SPEC_BY_CALC_ID = {spec.calculation_state_id: spec for spec in FED_POLICY_SPECS}
_CALC_STATE_ORDER = tuple(spec.calculation_state_id for spec in FED_POLICY_SPECS)
_FORMULA_BY_OUTPUT = {
    str(item["output_series_id"]): str(item["expression"])
    for item in FORMULA_DEFINITIONS
}
_SERIES_METADATA = {
    str(row["series_id"]): {
        "series_label": str(row["display_name"]),
        "section": str(row["section"]),
        "unit": str(row["unit"]),
        "metric_type": str(row["metric_type"]),
        "row_role": str(row["row_role"]),
        "series_order": int(index),
    }
    for index, row in enumerate(ROW_DEFINITIONS)
}
_SERIES_METADATA[CURRENT_LIGHT_TOTAL_SERIES_ID] = {
    "series_label": "Current finalist Light RUC total modelled km",
    "section": "Key volumes",
    "unit": "million km",
    "metric_type": "activity",
    "row_role": "audit_only",
    "series_order": len(_SERIES_METADATA),
}
_SERIES_METADATA["total_fed_ruc_net_revenue"] = {
    "series_label": "Total RUC+PED revenue",
    "section": "Derived totals",
    "unit": "$m nominal ex GST",
    "metric_type": "revenue",
    "row_role": "aggregate",
    "series_order": len(_SERIES_METADATA),
}


@dataclass(frozen=True)
class ExportPath:
    """Stable metadata for one of the 32 requested export paths."""

    family_id: str
    family_order: int
    scenario_id: str
    scenario_label: str
    policy_state: str
    policy_label: str
    policy_path_id: str
    path_order: int
    severity: str

    @property
    def path_label(self) -> str:
        return f"{self.scenario_label} - {self.policy_label}"


def _scenario_id_for(family_severity: str, calculation_state_id: str) -> str:
    """Replay scenario id for one family and calculation-layer policy state."""
    spec = _POLICY_SPEC_BY_CALC_ID[calculation_state_id]
    if not family_severity:  # baseline family
        if spec.is_published:
            return BASE_PUBLISHED_SCENARIO_NAME
        return BASE_POLICY_VARIANT_IDS[calculation_state_id]
    if spec.is_published:
        return conflict_scenario_name(family_severity)
    return conflict_policy_variant_name(family_severity, calculation_state_id)


def _export_paths() -> tuple[ExportPath, ...]:
    """The 32 public paths: four families crossed with eight timing states."""
    paths: list[ExportPath] = []
    family_specs = [
        ("base", 0, "", "Current finalist Base case"),
        *[
            (severity, family_order, severity, conflict_scenario_display_name(severity))
            for family_order, severity in enumerate(CONFLICT_SEVERITIES, start=1)
        ],
    ]
    path_order = 0
    for family_id, family_order, severity, label in family_specs:
        for policy_state in _CALC_STATE_ORDER:
            scenario_id = _scenario_id_for(severity, policy_state)
            paths.append(
                ExportPath(
                    family_id=family_id,
                    family_order=family_order,
                    scenario_id=scenario_id,
                    scenario_label=label,
                    policy_state=policy_state,
                    policy_label=_POLICY_LABELS[policy_state],
                    policy_path_id=POLICY_PATH_IDS[scenario_id],
                    path_order=path_order,
                    severity=severity,
                )
            )
            path_order += 1
    return tuple(paths)


def _repo_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _parse_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _path_metadata_frame(paths: tuple[ExportPath, ...]) -> pd.DataFrame:
    def _registry_metadata(policy_state: str) -> dict[str, Any]:
        spec = _POLICY_SPEC_BY_CALC_ID[policy_state]
        if spec.is_finite_deferral:
            direct = ";".join(spec.direct_affected_quarters())
        elif spec.is_no_uplift:
            direct = "2027Q1_onward"
        else:
            direct = ""
        return {
            "timing_id": spec.timing_id,
            "delay_months": spec.delay_months,
            "delay_quarters": spec.delay_quarters,
            "start_period": spec.start_period,
            "direct_affected_periods": direct,
        }

    return pd.DataFrame(
        [
            {
                "path_id": path.policy_path_id,
                "path_order": path.path_order,
                "path_label": path.path_label,
                "scenario_family_id": path.family_id,
                "scenario_order": path.family_order,
                "scenario_id": path.scenario_id,
                "scenario_label": path.scenario_label,
                "conflict_severity": path.severity or "base",
                "policy_state": path.policy_state,
                "policy_label": path.policy_label,
                **_registry_metadata(path.policy_state),
                "synthetic_status": "current_model_behavioural_replay",
                "status_note": (
                    "Current-model path with the modelled activity response; "
                    "only the initial 12c/L wedge is deferred and later planned "
                    "increases retain their published dates."
                ),
            }
            for path in paths
        ]
    )


def _model_input_path(
    replay_inputs: pd.DataFrame,
    *,
    scenario_id: str,
) -> pd.DataFrame:
    """Return one row per quarter with the exact replay price and macro inputs."""

    source = replay_inputs[
        replay_inputs["scenario_name"].astype(str).eq(str(scenario_id))
    ].copy()
    if source.empty:
        raise ValueError(f"Replay inputs are missing exported scenario {scenario_id!r}.")
    required = {"stream", "canonical_period"}
    missing = required.difference(source.columns)
    if missing:
        raise ValueError(
            "Replay inputs are missing path-key columns: " + ", ".join(sorted(missing))
        )

    field_specs = (
        (
            "model_real_petrol_price_cpl",
            "PED",
            "real_petrol_price_cents_per_litre",
        ),
        (
            "policy_source_nominal_petrol_cpl",
            "PED",
            "policy_source_nominal_petrol_cpl",
        ),
        (
            "policy_target_nominal_petrol_cpl",
            "PED",
            "policy_target_nominal_petrol_cpl",
        ),
        (
            "policy_nominal_petrol_ratio",
            "PED",
            "policy_nominal_petrol_ratio",
        ),
        (
            "policy_real_petrol_ratio",
            "PED",
            "policy_real_petrol_ratio",
        ),
        (
            "policy_petrol_wedge_nominal_cpl",
            "PED",
            "policy_petrol_wedge_nominal_cpl",
        ),
        (
            "model_real_diesel_price_cpl_light_ruc",
            "LIGHT_RUC",
            "real_diesel_price_cents_per_litre",
        ),
        (
            "model_real_diesel_price_cpl_heavy_ruc",
            "HEAVY_RUC",
            "real_diesel_price_cents_per_litre",
        ),
        (
            "model_real_light_ruc_price_nzd_per_1000km",
            "LIGHT_RUC",
            "real_light_ruc_price_nzd_per_1000km",
        ),
        (
            "model_lagged_real_light_ruc_price_nzd_per_1000km",
            "LIGHT_RUC",
            "lagged_real_light_ruc_price_nzd_per_1000km",
        ),
        (
            "model_real_heavy_ruc_price_nzd_per_1000km",
            "HEAVY_RUC",
            "real_heavy_ruc_price_nzd_per_1000km",
        ),
        (
            "model_lead_real_heavy_ruc_price_nzd_per_1000km",
            "HEAVY_RUC",
            "lead_real_heavy_ruc_price_nzd_per_1000km",
        ),
        (
            "model_population",
            "PED",
            "population",
        ),
        (
            "model_real_gdp_per_capita_nzd",
            "PED",
            "real_gdp_per_capita_nzd",
        ),
        (
            "model_real_gdp_sa_nzd_light_ruc",
            "LIGHT_RUC",
            "real_gdp_sa_nzd",
        ),
        (
            "model_real_gdp_sa_nzd_heavy_ruc",
            "HEAVY_RUC",
            "real_gdp_sa_nzd",
        ),
    )
    periods = sorted(source["canonical_period"].dropna().astype(str).unique())
    out = pd.DataFrame({"period": periods})
    for output_column, stream, input_column in field_specs:
        if input_column not in source.columns:
            raise ValueError(
                f"Replay inputs are missing required model input field {input_column!r}."
            )
        values = source[source["stream"].astype(str).eq(stream)][
            ["canonical_period", input_column]
        ].copy()
        if values["canonical_period"].astype(str).duplicated().any():
            raise ValueError(
                f"Replay inputs contain duplicate {scenario_id}/{stream} quarters."
            )
        values = values.rename(
            columns={"canonical_period": "period", input_column: output_column}
        )
        values["period"] = values["period"].astype(str)
        values[output_column] = pd.to_numeric(values[output_column], errors="coerce")
        out = out.merge(values, on="period", how="left", validate="one_to_one")
    required_output_columns = [
        "model_real_petrol_price_cpl",
        "model_real_diesel_price_cpl_light_ruc",
        "model_real_diesel_price_cpl_heavy_ruc",
        "model_real_light_ruc_price_nzd_per_1000km",
        "model_lagged_real_light_ruc_price_nzd_per_1000km",
        "model_real_heavy_ruc_price_nzd_per_1000km",
        "model_lead_real_heavy_ruc_price_nzd_per_1000km",
        "model_population",
        "model_real_gdp_per_capita_nzd",
        "model_real_gdp_sa_nzd_light_ruc",
        "model_real_gdp_sa_nzd_heavy_ruc",
    ]
    if out[required_output_columns].isna().any().any():
        raise ValueError(
            f"Replay inputs contain missing price or macro values for {scenario_id!r}."
        )
    return out


def _assumptions_frame(
    conflict_paths: pd.DataFrame,
    replay_inputs: pd.DataFrame,
    paths: tuple[ExportPath, ...],
    *,
    repo_root: Path,
    pack_dir: Path,
) -> pd.DataFrame:
    """Combine policy-free nominal paths with exact real replay inputs."""

    source = conflict_paths.copy()
    source["period"] = source["period"].astype(str)
    base = source[source["severity"].astype(str).eq(CONFLICT_SEVERITIES[0])].copy()
    base = base.sort_values("period", kind="stable").drop_duplicates("period")
    if base.empty:
        raise ValueError("Conflict scenario source has no nominal Base path.")
    base["severity"] = "base"
    base["scenario_diesel_cpl"] = pd.to_numeric(
        base["base_diesel_cpl"], errors="coerce"
    )
    base["scenario_petrol_cpl"] = pd.to_numeric(
        base["base_petrol_cpl"], errors="coerce"
    )
    base["diesel_ratio"] = 1.0
    base["petrol_ratio"] = 1.0
    base["observation_status"] = "base_reference"
    base["source_note"] = (
        "Governed nominal Base path (+1 c/L per quarter) used as the "
        "denominator for all Low/Medium/High conflict ratios."
    )
    base["source_workbook_cell"] = ""

    path_frames: list[pd.DataFrame] = []
    for path in paths:
        nominal = (
            base.copy()
            if path.family_id == "base"
            else source[source["severity"].astype(str).eq(path.severity)].copy()
        )
        nominal = nominal.sort_values("period", kind="stable")
        nominal = nominal.drop(
            columns=[
                column
                for column in (
                    "path_id",
                    "path_order",
                    "path_label",
                    "scenario_family_id",
                    "scenario_order",
                    "scenario_id",
                    "scenario_label",
                    "scenario_display_name",
                    "conflict_severity",
                    "policy_state",
                    "policy_label",
                )
                if column in nominal.columns
            ]
        )
        model_inputs = _model_input_path(
            replay_inputs,
            scenario_id=path.scenario_id,
        )
        frame = nominal.merge(
            model_inputs,
            on="period",
            how="left",
            validate="one_to_one",
        )
        frame.insert(0, "path_id", path.policy_path_id)
        frame.insert(1, "path_order", path.path_order)
        frame.insert(2, "path_label", path.path_label)
        frame.insert(3, "scenario_family_id", path.family_id)
        frame.insert(4, "scenario_order", path.family_order)
        frame.insert(5, "scenario_id", path.scenario_id)
        frame.insert(6, "scenario_label", path.scenario_label)
        frame.insert(7, "conflict_severity", path.severity or "base")
        frame.insert(8, "policy_state", path.policy_state)
        frame.insert(9, "policy_label", path.policy_label)
        frame["source_engine"] = ENGINE_AR1
        frame["source_pack"] = _repo_relative(repo_root, pack_dir)
        frame["scenario_config_file"] = (
            "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv"
        )
        frame["macro_config_file"] = (
            "data/current_revenue_outlook/treasury_befu26_macro_path.csv"
        )
        frame["conflict_gdp_config_file"] = (
            "data/current_revenue_outlook/conflict_gdp_calibration.csv"
        )
        frame["macro_source_url"] = (
            "https://www.treasury.govt.nz/sites/default/files/2026-05/"
            "befu26-suppinfo-charts-data.xlsx"
        )
        frame["conflict_gdp_source_url"] = (
            "https://www.treasury.govt.nz/sites/default/files/2026-05/"
            "mec-macroecon-scenarios-24-mar-2026.pdf"
        )
        frame["macro_overlay_basis"] = (
            "Treasury BEFU26 quarterly real-GDP path and population anchors; "
            "conflict GDP is a one-way fuel-to-GDP overlay calibrated to "
            "Treasury's 2027Q1 moderate and severe level gaps"
        )
        frame["source_workbook"] = SOURCE_WORKBOOK_NAME
        frame["source_workbook_sha256"] = frame[
            "source_workbook_sha256"
        ].fillna(SOURCE_WORKBOOK_SHA256)
        frame["policy_overlay_basis"] = (
            "12c FED and proportional RUC policy composed downstream; "
            "not embedded in nominal petrol/diesel source path"
        )
        frame["extract_version"] = EXTRACT_VERSION
        path_frames.append(frame)

    out = pd.concat(path_frames, ignore_index=True, sort=False)
    out["fed_12c_embedded"] = out["fed_12c_embedded"].map(_parse_boolean)
    if "policy_uplift_cpl" not in out.columns:
        out["policy_uplift_cpl"] = 0.0
    columns = [
        "path_id",
        "path_order",
        "path_label",
        "scenario_family_id",
        "scenario_order",
        "scenario_id",
        "scenario_label",
        "conflict_severity",
        "policy_state",
        "policy_label",
        "period",
        "base_diesel_cpl",
        "scenario_diesel_cpl",
        "diesel_ratio",
        "base_petrol_cpl",
        "scenario_petrol_cpl",
        "petrol_ratio",
        "model_real_petrol_price_cpl",
        "policy_source_nominal_petrol_cpl",
        "policy_target_nominal_petrol_cpl",
        "policy_nominal_petrol_ratio",
        "policy_real_petrol_ratio",
        "policy_petrol_wedge_nominal_cpl",
        "model_real_diesel_price_cpl_light_ruc",
        "model_real_diesel_price_cpl_heavy_ruc",
        "model_real_light_ruc_price_nzd_per_1000km",
        "model_lagged_real_light_ruc_price_nzd_per_1000km",
        "model_real_heavy_ruc_price_nzd_per_1000km",
        "model_lead_real_heavy_ruc_price_nzd_per_1000km",
        "model_population",
        "model_real_gdp_per_capita_nzd",
        "model_real_gdp_sa_nzd_light_ruc",
        "model_real_gdp_sa_nzd_heavy_ruc",
        "observation_status",
        "source_note",
        "source_url",
        "source_workbook",
        "source_workbook_cell",
        "source_workbook_sha256",
        "fed_12c_embedded",
        "policy_uplift_cpl",
        "policy_overlay_basis",
        "source_engine",
        "source_pack",
        "scenario_config_file",
        "macro_config_file",
        "conflict_gdp_config_file",
        "macro_source_url",
        "conflict_gdp_source_url",
        "macro_overlay_basis",
        "extract_version",
    ]
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out[columns].sort_values(
        ["path_order", "period"], kind="stable"
    ).reset_index(drop=True)


def _dashboard_aligned_annual_bridge(
    replay: Any,
    paths: tuple[ExportPath, ...],
    *,
    repo_root: Path,
    pack_dir: Path,
) -> pd.DataFrame:
    """Build the exact default dashboard-hover rows for all 12 policy paths.

    The standalone replay bridge owns scenario factors and behavioural
    responses. Dashboard levels additionally use the raw PED bridge, Treasury
    macro overlay and default MoT VFM uptake overlay. Applying those layers in
    dashboard order prevents the extract and hover values from drifting apart.
    """

    pack = load_revenue_outlook_pack(pack_dir, repo_root=repo_root)
    bridge = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        include_derived_frames=False,
        include_selected_ped_audit=False,
    )
    # P1.2: the baseline macro overlay requires per-scenario factors; the fuel
    # replay's baseline factors are Base-only and would fail closed on the
    # comparison rows this frame carries.
    input_path = pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    direct_macro = run_direct_treasury_scenario_replay(
        pd.read_parquet(input_path),
        repo_root=repo_root,
        engine=ENGINE_AR1,
    )
    macro_base, _ = apply_treasury_macro_to_chart_rows(
        bridge["chart_rows"], direct_macro
    )
    visible_base, _ = apply_uptake_levers_to_chart_rows(
        macro_base,
        pack.ev_phev_ped_light_drift_assumptions,
        EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE],
        adjust_ped=True,
    )
    factor_maps = {
        state: fed_policy_annual_factors(repo_root, pack.revenue_chart_rows, state)
        for state in _CALC_STATE_ORDER
        if state != FED_POLICY_STATE_PUBLISHED
    }
    ruc_class_revenue = mbu26_ruc_class_revenue_by_fy(repo_root)
    path_lookup = {
        (path.family_id, path.policy_state): path
        for path in paths
    }
    scenario_family = {
        BASE_PUBLISHED_SCENARIO_NAME: "base",
        **{
            conflict_scenario_name(severity): severity
            for severity in CONFLICT_SEVERITIES
        },
    }
    frames: list[pd.DataFrame] = []
    for policy_state in _CALC_STATE_ORDER:
        active = visible_base.copy()
        if policy_state != FED_POLICY_STATE_PUBLISHED:
            active, _ = apply_fed_policy_state_to_chart_rows(
                active,
                factor_maps[policy_state],
                policy_state=policy_state,
                scenario_roles={"basecase", "comparison"},
                policy_pair_factors=replay.policy_pair_factors,
                ruc_class_revenue_by_fy=ruc_class_revenue,
            )
        active, _ = append_fuel_price_scenario_to_chart_rows(active, replay)
        annual = active[
            active["time_grain"].astype(str).eq("june_year")
            & active["scenario_name"].astype(str).isin(scenario_family)
        ].copy()
        annual["FY"] = pd.to_numeric(annual["june_year"], errors="coerce").astype(
            "Int64"
        )
        annual = annual[
            annual["FY"].between(START_FY, END_FY, inclusive="both")
        ].copy()
        annual["scenario_family_id"] = annual["scenario_name"].astype(str).map(
            scenario_family
        )
        annual["scenario_name"] = annual["scenario_family_id"].map(
            lambda family: path_lookup[(str(family), policy_state)].scenario_id
        )
        annual["policy_path_id"] = annual["scenario_family_id"].map(
            lambda family: path_lookup[(str(family), policy_state)].policy_path_id
        )
        annual["policy_state"] = policy_state
        annual["unit"] = annual.get(
            "value_unit", pd.Series("", index=annual.index)
        ).fillna("").astype(str)
        annual["extraction_basis"] = (
            "Default dashboard hover pipeline: raw PED bridge + Treasury BEFU26 "
            "macro + MoT VFM base uptake + fixed-finalist policy/conflict replay factors"
        )
        frames.append(annual)

    visible = pd.concat(frames, ignore_index=True, sort=False)
    full = replay.annual_bridge[
        replay.annual_bridge["scenario_name"].astype(str).isin(
            {path.scenario_id for path in paths}
        )
    ].copy()
    full["FY"] = pd.to_numeric(full["FY"], errors="coerce").astype("Int64")
    full = full[full["FY"].between(START_FY, END_FY, inclusive="both")].copy()
    full["scenario_family_id"] = full["scenario_name"].astype(str).map(
        {path.scenario_id: path.family_id for path in paths}
    )
    full["policy_state"] = full["scenario_name"].astype(str).map(
        {path.scenario_id: path.policy_state for path in paths}
    )
    full["base_source_basis"] = full.get(
        "source_basis", pd.Series("", index=full.index)
    ).fillna("").astype(str)
    full["extraction_basis"] = (
        "Default dashboard hover pipeline: raw PED bridge + Treasury BEFU26 "
        "macro + MoT VFM base uptake + fixed-finalist policy/conflict replay factors"
    )
    full["source_basis"] = full["extraction_basis"]
    visible["base_source_basis"] = visible.get(
        "source_basis", pd.Series("", index=visible.index)
    ).fillna("").astype(str)
    visible["source_basis"] = visible["extraction_basis"]

    key_columns = ["scenario_name", "FY", "series_id"]
    if full.duplicated(key_columns, keep=False).any():
        key_columns.append("fed_path")
    if full.duplicated(key_columns, keep=False).any() or visible.duplicated(
        key_columns, keep=False
    ).any():
        raise ValueError("Dashboard/replay bridge rows are not unique on their annual series keys.")
    full = full.set_index(key_columns, drop=False)
    visible = visible.set_index(key_columns, drop=False)
    shared_index = full.index.intersection(visible.index)
    replacement_columns = [
        column
        for column in visible.columns
        if column in full.columns
        and column
        not in {
            "scenario_name",
            "FY",
            "series_id",
            "fed_path",
        }
    ]
    for column in replacement_columns:
        full.loc[shared_index, column] = visible.loc[shared_index, column].to_numpy()
    missing_visible = visible.loc[visible.index.difference(full.index)].copy()
    out = pd.concat(
        [full.reset_index(drop=True), missing_visible.reset_index(drop=True)],
        ignore_index=True,
        sort=False,
    )

    # Rebuild every governed formula after the visible leaf rows replace the
    # replay bridge levels. This retains the complete MBU26 revenue breakdown
    # while ensuring all net/gross totals equal the dashboard-hover lineage.
    for (_scenario_name, _fy), group_index in out.groupby(
        ["scenario_name", "FY"], sort=False
    ).groups.items():
        indexes = list(group_index)
        values = {
            str(out.at[index, "series_id"]): float(out.at[index, "value"])
            for index in indexes
            if pd.notna(pd.to_numeric(out.at[index, "value"], errors="coerce"))
        }
        for definition in FORMULA_DEFINITIONS:
            output = str(definition["output_series_id"])
            terms = tuple(definition["terms"])
            if not all(str(series_id) in values for series_id, _coefficient in terms):
                continue
            calculated = sum(
                float(coefficient) * values[str(series_id)]
                for series_id, coefficient in terms
            )
            output_indexes = [
                index
                for index in indexes
                if str(out.at[index, "series_id"]) == output
            ]
            if output_indexes:
                for index in output_indexes:
                    out.at[index, "value"] = calculated
            values[output] = calculated

    expected_path_ids = {path.scenario_id for path in paths}
    actual_path_ids = set(out["scenario_name"].dropna().astype(str))
    if actual_path_ids != expected_path_ids:
        missing = sorted(expected_path_ids.difference(actual_path_ids))
        extra = sorted(actual_path_ids.difference(expected_path_ids))
        raise ValueError(
            f"Dashboard-aligned annual bridge path mismatch; missing={missing}, extra={extra}."
        )
    return out


def _annual_export_frame(
    annual_bridge: pd.DataFrame,
    paths: tuple[ExportPath, ...],
    *,
    metric_type: str,
    repo_root: Path,
    pack_dir: Path,
) -> pd.DataFrame:
    """Select all annual bridge rows of one metric type for the 32 paths."""

    if annual_bridge is None or annual_bridge.empty:
        raise ValueError("Governed conflict replay produced no annual bridge rows.")
    required = {"scenario_name", "FY", "series_id", "value", "unit"}
    missing = required.difference(annual_bridge.columns)
    if missing:
        raise ValueError(
            "Annual bridge is missing export columns: " + ", ".join(sorted(missing))
        )
    metadata = _path_metadata_frame(paths)
    exported_ids = set(metadata["scenario_id"].astype(str))
    out = annual_bridge[
        annual_bridge["scenario_name"].astype(str).isin(exported_ids)
    ].copy()
    out["FY"] = pd.to_numeric(out["FY"], errors="coerce").astype("Int64")
    out = out[out["FY"].between(START_FY, END_FY, inclusive="both")].copy()
    out["series_id"] = out["series_id"].astype(str)
    out["metric_type"] = out.get(
        "metric_type", pd.Series("", index=out.index)
    ).fillna("").astype(str)
    fallback_metric = out["series_id"].map(
        lambda value: _SERIES_METADATA.get(value, {}).get("metric_type", "")
    )
    out["metric_type"] = out["metric_type"].where(
        out["metric_type"].str.len().gt(0), fallback_metric
    )
    out = out[out["metric_type"].eq(metric_type)].copy()
    if out.empty:
        raise ValueError(f"Annual bridge has no {metric_type!r} rows to export.")

    out = out.merge(
        metadata,
        left_on="scenario_name",
        right_on="scenario_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_path"),
    )
    if out["path_id"].isna().any():
        raise ValueError("Annual rows could not be mapped to all export path metadata.")
    out["period"] = out["FY"].map(lambda value: f"FY{int(value)}")
    out["series_order"] = out["series_id"].map(
        lambda value: _SERIES_METADATA.get(value, {}).get("series_order", 10_000)
    )
    for target, candidates in {
        "series_label": ("display_name", "line_label", "series_label"),
        "section": ("section",),
        "row_role": ("row_role",),
        "formula": ("formula",),
        "source_basis": ("source_basis",),
        "source_file": ("source_file",),
        "source_cell": ("source_cell",),
        "model_id": ("model_id",),
        "value_status": ("value_status",),
        "fed_path": ("fed_path",),
    }.items():
        if target not in out.columns:
            out[target] = ""
        for candidate in candidates:
            if candidate not in out.columns:
                continue
            candidate_values = out[candidate].fillna("").astype(str)
            out[target] = out[target].fillna("").astype(str).where(
                out[target].fillna("").astype(str).str.len().gt(0),
                candidate_values,
            )
    out["series_label"] = out.apply(
        lambda row: row["series_label"]
        or _SERIES_METADATA.get(str(row["series_id"]), {}).get(
            "series_label", str(row["series_id"])
        ),
        axis=1,
    )
    out["section"] = out.apply(
        lambda row: row["section"]
        or _SERIES_METADATA.get(str(row["series_id"]), {}).get("section", ""),
        axis=1,
    )
    out["row_role"] = out.apply(
        lambda row: row["row_role"]
        or _SERIES_METADATA.get(str(row["series_id"]), {}).get("row_role", ""),
        axis=1,
    )
    out["formula"] = out.apply(
        lambda row: row["formula"]
        or _FORMULA_BY_OUTPUT.get(str(row["series_id"]), ""),
        axis=1,
    )
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    if out["value"].isna().any():
        raise ValueError(f"Annual {metric_type} export contains non-numeric values.")
    out["source_engine"] = ENGINE_AR1
    out["source_pack"] = _repo_relative(repo_root, pack_dir)
    out["scenario_config_file"] = (
        "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv"
    )
    out["macro_config_file"] = (
        "data/current_revenue_outlook/treasury_befu26_macro_path.csv"
    )
    out["conflict_gdp_config_file"] = (
        "data/current_revenue_outlook/conflict_gdp_calibration.csv"
    )
    out["macro_source_url"] = (
        "https://www.treasury.govt.nz/sites/default/files/2026-05/"
        "befu26-suppinfo-charts-data.xlsx"
    )
    out["conflict_gdp_source_url"] = (
        "https://www.treasury.govt.nz/sites/default/files/2026-05/"
        "mec-macroecon-scenarios-24-mar-2026.pdf"
    )
    if "extraction_basis" not in out.columns:
        out["extraction_basis"] = ""
    out["extraction_basis"] = out["extraction_basis"].fillna("").astype(str).where(
        out["extraction_basis"].fillna("").astype(str).str.len().gt(0),
        "FuelPriceScenarioReplayResult.annual_bridge",
    )
    out["scenario_note"] = out["scenario_family_id"].map(
        lambda family: (
            "Current finalist Base case with Treasury BEFU26 macro inputs and "
            "the selected 12c FED/RUC policy."
            if family == "base"
            else (
                f"{conflict_scenario_note(family)} Fuel-price stress also "
                "drives a one-way Treasury-calibrated GDP path; GDP edits do "
                "not feed back into fuel prices."
            )
        )
    )
    out["extract_version"] = EXTRACT_VERSION

    key_columns = ["path_id", "FY", "series_id"]
    if "fed_path" in out.columns and out["fed_path"].fillna("").astype(str).str.len().gt(0).any():
        key_columns.append("fed_path")
    if out.duplicated(key_columns, keep=False).any():
        detail = out.loc[out.duplicated(key_columns, keep=False), key_columns].head(20)
        raise ValueError(
            f"Annual {metric_type} export contains duplicate keys:\n"
            + detail.to_string(index=False)
        )

    columns = [
        "path_id",
        "path_order",
        "path_label",
        "scenario_family_id",
        "scenario_order",
        "scenario_id",
        "scenario_label",
        "conflict_severity",
        "policy_state",
        "policy_label",
        "FY",
        "period",
        "series_id",
        "series_order",
        "series_label",
        "section",
        "row_role",
        "metric_type",
        "value",
        "unit",
        "formula",
        "fed_path",
        "source_basis",
        "base_source_basis",
        "source_file",
        "source_cell",
        "model_id",
        "value_status",
        "scenario_note",
        "source_engine",
        "source_pack",
        "scenario_config_file",
        "macro_config_file",
        "conflict_gdp_config_file",
        "macro_source_url",
        "conflict_gdp_source_url",
        "extraction_basis",
        "extract_version",
    ]
    for column in columns:
        if column not in out.columns:
            out[column] = ""
    return out[columns].sort_values(
        ["path_order", "FY", "series_order", "series_id"], kind="stable"
    ).reset_index(drop=True)


def _annual_values_by_family(
    annual_rows: pd.DataFrame,
    *,
    policy_state: str,
) -> pd.DataFrame:
    selected = annual_rows[
        annual_rows["policy_state"].astype(str).eq(policy_state)
    ].copy()
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    return selected


def _validation_frame(
    *,
    replay: Any,
    assumptions: pd.DataFrame,
    revenue: pd.DataFrame,
    activity: pd.DataFrame,
    paths: tuple[ExportPath, ...],
) -> pd.DataFrame:
    """Build and evaluate the workbook-facing validation contract."""

    checks: list[dict[str, Any]] = []

    def add_check(
        check_id: str,
        *,
        passed: bool,
        observed: Any,
        expected: Any,
        max_abs_error: float | None = None,
        detail: str,
    ) -> None:
        checks.append(
            {
                "check_id": check_id,
                "status": "PASS" if bool(passed) else "FAIL",
                "passed": bool(passed),
                "observed": observed,
                "expected": expected,
                "max_abs_error": max_abs_error,
                "detail": detail,
                "source_engine": ENGINE_AR1,
                "extract_version": EXTRACT_VERSION,
            }
        )

    expected_internal = {
        str(replay.base_scenario_name),
        *(conflict_scenario_name(severity) for severity in CONFLICT_SEVERITIES),
        *(path.scenario_id for path in paths),
    }
    actual_internal = set(replay.replay_inputs["scenario_name"].dropna().astype(str))
    validation_internal = set(
        replay.policy_validation_report["scenario_name"].dropna().astype(str)
    )
    expected_internal_count = 4 * len(_CALC_STATE_ORDER)
    add_check(
        "internal_scenario_count",
        passed=(
            actual_internal == expected_internal
            and validation_internal == expected_internal
            and len(expected_internal) == expected_internal_count
        ),
        observed=(
            f"inputs={len(actual_internal)}; validation={len(validation_internal)}"
        ),
        expected=f"{expected_internal_count} exact Base/published-conflict/policy scenarios",
        detail=(
            "The governed replay contains four original/published paths plus one "
            "variant per family for each of the six deferrals and no-uplift."
        ),
    )

    expected_paths = [path.policy_path_id for path in paths]
    observed_assumption_paths = assumptions["path_id"].drop_duplicates().tolist()
    observed_revenue_paths = revenue["path_id"].drop_duplicates().tolist()
    observed_activity_paths = activity["path_id"].drop_duplicates().tolist()
    add_check(
        "export_path_count_and_order",
        passed=(
            len(expected_paths) == 4 * len(_CALC_STATE_ORDER)
            and observed_assumption_paths == expected_paths
            and observed_revenue_paths == expected_paths
            and observed_activity_paths == expected_paths
        ),
        observed=(
            f"assumptions={len(observed_assumption_paths)}; "
            f"revenue={len(observed_revenue_paths)}; "
            f"activity={len(observed_activity_paths)}"
        ),
        expected=(
            f"{4 * len(_CALC_STATE_ORDER)} paths in Base, Low, Medium, High x "
            "original, the six deferrals, off order"
        ),
        detail="All three export tables share the same stable path IDs and display order.",
    )

    macro = assumptions.copy()
    macro_numeric_columns = [
        "model_population",
        "model_real_gdp_per_capita_nzd",
        "model_real_gdp_sa_nzd_light_ruc",
        "model_real_gdp_sa_nzd_heavy_ruc",
    ]
    for column in macro_numeric_columns:
        macro[column] = pd.to_numeric(macro[column], errors="coerce")
    light_heavy_gdp_error = (
        macro["model_real_gdp_sa_nzd_light_ruc"]
        - macro["model_real_gdp_sa_nzd_heavy_ruc"]
    ).abs().max()
    ped_gdp_identity_error = (
        macro["model_real_gdp_per_capita_nzd"] * macro["model_population"]
        - macro["model_real_gdp_sa_nzd_light_ruc"]
    ).abs().max()
    policy_gdp_range = (
        macro.groupby(["scenario_family_id", "period"], sort=False)[
            "model_real_gdp_sa_nzd_light_ruc"
        ]
        .agg(lambda values: float(values.max() - values.min()))
        .max()
    )
    add_check(
        "treasury_macro_stream_and_policy_identity",
        passed=(
            macro[macro_numeric_columns].notna().all().all()
            and pd.notna(light_heavy_gdp_error)
            and float(light_heavy_gdp_error) <= VALUE_TOLERANCE
            and pd.notna(ped_gdp_identity_error)
            and float(ped_gdp_identity_error) <= 0.01
            and pd.notna(policy_gdp_range)
            and float(policy_gdp_range) <= VALUE_TOLERANCE
        ),
        observed=(
            f"rows={len(macro)}; "
            f"max_light_heavy_gdp_delta_nzd={float(light_heavy_gdp_error):.12g}; "
            f"max_gdp_pc_population_identity_delta_nzd="
            f"{float(ped_gdp_identity_error):.12g}; "
            f"max_policy_state_gdp_range_nzd={float(policy_gdp_range):.12g}"
        ),
        expected=(
            "Light GDP = Heavy GDP; GDP per capita x population = aggregate GDP; "
            "12c policy timing does not alter GDP"
        ),
        max_abs_error=max(
            float(light_heavy_gdp_error),
            float(ped_gdp_identity_error),
            float(policy_gdp_range),
        ),
        detail=(
            "Treasury BEFU26 provides one canonical macro path. PED consumes "
            "GDP per capita while both RUC streams consume the same aggregate GDP."
        ),
    )

    anchor = macro[
        macro["policy_state"].astype(str).eq(FED_POLICY_STATE_PUBLISHED)
        & macro["period"].astype(str).eq("2027Q1")
        & macro["scenario_family_id"].astype(str).isin(["base", "medium", "high"])
    ].drop_duplicates("scenario_family_id")
    anchor_lookup = anchor.set_index("scenario_family_id")[
        "model_real_gdp_sa_nzd_light_ruc"
    ]
    observed_anchor_impacts = {
        severity: (
            float(anchor_lookup.at[severity] / anchor_lookup.at["base"] - 1.0)
            if severity in anchor_lookup.index and "base" in anchor_lookup.index
            else float("nan")
        )
        for severity in ("medium", "high")
    }
    anchor_error = max(
        abs(observed_anchor_impacts["medium"] - (-0.015)),
        abs(observed_anchor_impacts["high"] - (-0.031)),
    )
    add_check(
        "treasury_conflict_gdp_anchor_reconciliation",
        passed=(
            len(anchor_lookup) == 3
            and pd.notna(anchor_error)
            and float(anchor_error) <= 1e-12
        ),
        observed=(
            f"2027Q1 medium={observed_anchor_impacts['medium']:.8%}; "
            f"high={observed_anchor_impacts['high']:.8%}; "
            f"max_abs_error={anchor_error:.12g}"
        ),
        expected="2027Q1 Medium -1.5%; High -3.1% versus Treasury Base",
        max_abs_error=float(anchor_error),
        detail=(
            "The fuel-to-GDP overlay is calibrated to Treasury's published "
            "moderate and severe Middle East conflict GDP level gaps."
        ),
    )

    ped_activity = activity[
        activity["series_id"].astype(str).isin(
            {"light_petrol_vkt", "ped_volume"}
        )
    ].copy()
    ped_activity["FY"] = pd.to_numeric(ped_activity["FY"], errors="coerce")
    ped_activity["value"] = pd.to_numeric(
        ped_activity["value"], errors="coerce"
    )
    ped_wide = ped_activity.pivot_table(
        index=["path_id", "FY"],
        columns="series_id",
        values="value",
        aggfunc="first",
    )
    replay_activity = replay.annual_bridge[
        replay.annual_bridge["policy_path_id"].astype(str).eq(
            "baseline_published"
        )
        & replay.annual_bridge["series_id"].astype(str).isin(
            {"light_petrol_vkt", "ped_volume"}
        )
    ].copy()
    replay_activity["FY"] = pd.to_numeric(
        replay_activity["FY"], errors="coerce"
    )
    replay_activity["value"] = pd.to_numeric(
        replay_activity["value"], errors="coerce"
    )
    replay_wide = replay_activity.pivot_table(
        index="FY",
        columns="series_id",
        values="value",
        aggfunc="first",
    )
    expected_intensity = (
        replay_wide["ped_volume"]
        / replay_wide["light_petrol_vkt"]
        * 100.0
    )
    observed_intensity = (
        ped_wide["ped_volume"]
        / ped_wide["light_petrol_vkt"]
        * 100.0
    )
    intensity_error = (
        observed_intensity
        - ped_wide.index.get_level_values("FY").map(expected_intensity)
    ).abs()
    max_intensity_error = (
        float(intensity_error.max())
        if not intensity_error.empty and intensity_error.notna().any()
        else float("inf")
    )
    add_check(
        "petrol_vkt_ped_litres_intensity_reconciliation",
        passed=(
            len(ped_wide) == len(paths) * (END_FY - START_FY + 1)
            and {"light_petrol_vkt", "ped_volume"}.issubset(ped_wide.columns)
            and ped_wide[["light_petrol_vkt", "ped_volume"]].notna().all().all()
            and ped_wide[["light_petrol_vkt", "ped_volume"]].gt(0.0).all().all()
            and max_intensity_error <= VALUE_TOLERANCE
        ),
        observed=(
            f"path_fy_rows={len(ped_wide)}; "
            f"max_abs_litres_per_100km_error={max_intensity_error:.12g}"
        ),
        expected=(
            "60 path/FY rows whose PED litres divided by light-petrol VKT "
            f"matches the governed Base intensity within {VALUE_TOLERANCE}"
        ),
        max_abs_error=max_intensity_error,
        detail=(
            "The selected raw PED bridge, VFM retention, 12c policy response "
            "and conflict response must scale light-petrol VKT and PED litres "
            "on one common activity lineage."
        ),
    )

    embedded = assumptions["fed_12c_embedded"].map(_parse_boolean)
    source_uplift = pd.to_numeric(
        assumptions.get("policy_uplift_cpl", 0.0), errors="coerce"
    )
    add_check(
        "source_paths_exclude_12c_policy",
        passed=(
            not embedded.any()
            and source_uplift.notna().all()
            and source_uplift.abs().max() <= VALUE_TOLERANCE
        ),
        observed=(
            f"embedded_true={int(embedded.sum())}; "
            f"max_abs_source_uplift_cpl={float(source_uplift.abs().max()):.12g}"
        ),
        expected="0 embedded flags and 0 source-policy c/L",
        max_abs_error=float(source_uplift.abs().max()),
        detail="The 12c FED/RUC policy is composed after the nominal conflict fuel path.",
    )

    lineage = (
        assumptions[
            assumptions["scenario_family_id"].isin(CONFLICT_SEVERITIES)
        ][["scenario_family_id", "period", "observation_status"]]
        .sort_values(["scenario_family_id", "period"], kind="stable")
        .drop_duplicates(["scenario_family_id", "period"], keep="first")
    )
    lineage_status = lineage["observation_status"].fillna("").astype(str).str.casefold()
    q1 = lineage[lineage["period"].astype(str).eq("2026Q1")]
    q2_q3 = lineage[
        lineage["period"].astype(str).isin(["2026Q2", "2026Q3"])
    ]
    prospective = lineage[
        lineage["period"].astype(str).str.match(r"^\d{4}Q[1-4]$", na=False)
        & ~lineage["period"].astype(str).isin(["2026Q1", "2026Q2", "2026Q3"])
    ]
    q1_valid = (
        len(q1) == len(CONFLICT_SEVERITIES)
        and q1["observation_status"].astype(str).str.casefold().eq("mixed").all()
    )
    observed_valid = (
        len(q2_q3) == len(CONFLICT_SEVERITIES) * 2
        and q2_q3["observation_status"].astype(str).str.casefold().eq("observed").all()
    )
    prospective_valid = (
        len(prospective) == len(CONFLICT_SEVERITIES) * 17
        and prospective["observation_status"]
        .astype(str)
        .str.casefold()
        .eq("assumption")
        .all()
    )
    add_check(
        "fuel_path_observation_lineage",
        passed=(
            len(lineage) == len(CONFLICT_SEVERITIES) * 20
            and not lineage_status.eq("").any()
            and q1_valid
            and observed_valid
            and prospective_valid
        ),
        observed=(
            f"unique_rows={len(lineage)}; q1_mixed={int(q1_valid)}; "
            f"q2_q3_observed={int(observed_valid)}; "
            f"prospective_assumption={int(prospective_valid)}"
        ),
        expected=(
            "60 unique severity-quarter rows: Q1 mixed, Q2/Q3 observed, "
            "2026Q4-2030Q4 assumption"
        ),
        detail=(
            "Q1 combines a workbook-sourced diesel anchor with a calibrated "
            "policy-free petrol Base; later observed and prospective quarters "
            "must not be presented with the same evidence status."
        ),
    )

    replay_inputs = replay.replay_inputs.copy()
    ratio_columns = {
        "policy_free_source_nominal_petrol_cpl",
        "policy_published_fed_wedge_nominal_cpl",
        "policy_source_nominal_petrol_cpl",
        "policy_target_nominal_petrol_cpl",
        "policy_nominal_petrol_ratio",
        "policy_real_petrol_ratio",
    }
    if ratio_columns.issubset(replay_inputs.columns):
        ratio_rows = replay_inputs[
            replay_inputs["scenario_name"].astype(str).isin(
                [path.scenario_id for path in paths]
            )
            & replay_inputs["stream"].astype(str).eq("PED")
        ].copy()
        for column in ratio_columns:
            ratio_rows[column] = pd.to_numeric(ratio_rows[column], errors="coerce")
        ratio_rows = ratio_rows[
            ratio_rows["policy_nominal_petrol_ratio"].notna()
            | ratio_rows["policy_real_petrol_ratio"].notna()
        ].copy()
        nominal_real_error = (
            ratio_rows["policy_nominal_petrol_ratio"]
            - ratio_rows["policy_real_petrol_ratio"]
        ).abs()
        target_source_ratio = (
            ratio_rows["policy_target_nominal_petrol_cpl"]
            / ratio_rows["policy_source_nominal_petrol_cpl"]
        )
        target_ratio_error = (
            target_source_ratio - ratio_rows["policy_nominal_petrol_ratio"]
        ).abs()
        published_source_basis_error = (
            ratio_rows["policy_source_nominal_petrol_cpl"]
            - (
                ratio_rows["policy_free_source_nominal_petrol_cpl"]
                + ratio_rows["policy_published_fed_wedge_nominal_cpl"]
            )
        ).abs()
        ratio_max_error = max(
            float(nominal_real_error.max()) if not nominal_real_error.empty else float("inf"),
            float(target_ratio_error.max()) if not target_ratio_error.empty else float("inf"),
            (
                float(published_source_basis_error.max())
                if not published_source_basis_error.empty
                else float("inf")
            ),
        )
        ratio_available = True
        ratio_valid = (
            len(ratio_rows) > 0
            and ratio_rows[list(ratio_columns)].notna().all().all()
            and ratio_rows["policy_source_nominal_petrol_cpl"].gt(0.0).all()
            and ratio_rows["policy_target_nominal_petrol_cpl"].gt(0.0).all()
            and ratio_max_error <= VALUE_TOLERANCE
        )
        ratio_observed = (
            f"rows={len(ratio_rows)}; "
            f"max_abs_published_basis_or_ratio_error={ratio_max_error:.12g}"
        )
    else:
        ratio_available = False
        ratio_valid = True
        ratio_max_error = None
        ratio_observed = "not_available_in_replay_audit"
    add_check(
        "fed_policy_nominal_real_ratio_invariant",
        passed=ratio_valid,
        observed=ratio_observed,
        expected=(
            "published-policy source nominal equals policy-free fuel plus the "
            "published FED wedge, and target/source equals the multiplier "
            "applied to the real PED pump-price input"
            if ratio_available
            else "not applicable when replay audit fields are unavailable"
        ),
        max_abs_error=ratio_max_error,
        detail=(
            "The nominal denominator is aligned to the published-policy real "
            "source before the FED-policy target/source ratio is applied, "
            "preserving the implicit deflator exactly."
        ),
    )

    revenue_values = revenue[
        ["path_id", "FY", "series_id", "value"]
    ].copy()
    revenue_values["value"] = pd.to_numeric(revenue_values["value"], errors="coerce")
    formula_residuals: dict[str, list[float]] = {
        "net_fed_revenue": [],
        "total_ruc_net_revenue": [],
        "net_mvr_revenue": [],
    }
    formula_missing: dict[str, int] = {key: 0 for key in formula_residuals}
    for (_path_id, _fy), group in revenue_values.groupby(
        ["path_id", "FY"], sort=False
    ):
        if group["series_id"].duplicated().any():
            for key in formula_missing:
                formula_missing[key] += 1
            continue
        values = group.set_index("series_id")["value"].to_dict()
        formulas = {
            "net_fed_revenue": (
                values.get("net_fed_revenue"),
                (
                    values.get("gross_fed_revenue")
                    - values.get("fed_refunds")
                    if {
                        "gross_fed_revenue",
                        "fed_refunds",
                    }.issubset(values)
                    else None
                ),
            ),
            "total_ruc_net_revenue": (
                values.get("total_ruc_net_revenue"),
                (
                    values.get("gross_ruc_revenue")
                    - values.get("ruc_admin_revenue")
                    - values.get("ruc_refunds")
                    if {
                        "gross_ruc_revenue",
                        "ruc_admin_revenue",
                        "ruc_refunds",
                    }.issubset(values)
                    else None
                ),
            ),
            "net_mvr_revenue": (
                values.get("net_mvr_revenue"),
                (
                    values.get("mr1_revenue")
                    + values.get("mr2_revenue")
                    - values.get("mvr_admin_revenue")
                    - values.get("mvr_refunds")
                    if {
                        "mr1_revenue",
                        "mr2_revenue",
                        "mvr_admin_revenue",
                        "mvr_refunds",
                    }.issubset(values)
                    else None
                ),
            ),
        }
        for output, (observed, calculated) in formulas.items():
            if observed is None or calculated is None:
                formula_missing[output] += 1
                continue
            formula_residuals[output].append(float(observed) - float(calculated))

    for output, residuals in formula_residuals.items():
        max_error = max((abs(value) for value in residuals), default=float("inf"))
        add_check(
            f"formula_identity_{output}",
            passed=(
                formula_missing[output] == 0
                and len(residuals) == len(paths) * (END_FY - START_FY + 1)
                and max_error <= VALUE_TOLERANCE
            ),
            observed=(
                f"groups={len(residuals)}; missing={formula_missing[output]}; "
                f"max_abs_residual={max_error:.12g}"
            ),
            expected=f"{len(paths) * (END_FY - START_FY + 1)} groups; residual <= {VALUE_TOLERANCE}",
            max_abs_error=max_error,
            detail=_FORMULA_BY_OUTPUT[output],
        )

    annual = pd.concat([revenue, activity], ignore_index=True, sort=False)
    shared_fy2026 = annual[
        annual["scenario_family_id"].astype(str).isin(CONFLICT_SEVERITIES)
        & pd.to_numeric(annual["FY"], errors="coerce").eq(2026)
    ].copy()
    shared_fy2026["value"] = pd.to_numeric(
        shared_fy2026["value"], errors="coerce"
    )
    shared_fy2026_wide = shared_fy2026.pivot_table(
        index=["policy_state", "metric_type", "series_id"],
        columns="scenario_family_id",
        values="value",
        aggfunc="first",
    )
    expected_shared_groups = (
        len(
            annual[
                pd.to_numeric(annual["FY"], errors="coerce").eq(2026)
            ][["metric_type", "series_id"]].drop_duplicates()
        )
        * 3
    )
    shared_fy2026_range = (
        shared_fy2026_wide.max(axis=1) - shared_fy2026_wide.min(axis=1)
    )
    shared_fy2026_max_error = shared_fy2026_range.max()
    add_check(
        "shared_fy2026_conflict_paths_do_not_leak_future_severity",
        passed=(
            len(shared_fy2026_wide) == expected_shared_groups
            and set(CONFLICT_SEVERITIES).issubset(shared_fy2026_wide.columns)
            and shared_fy2026_wide[list(CONFLICT_SEVERITIES)].notna().all().all()
            and pd.notna(shared_fy2026_max_error)
            and float(shared_fy2026_max_error) <= VALUE_TOLERANCE
        ),
        observed=(
            f"groups={len(shared_fy2026_wide)}; "
            f"max_high_medium_low_range={float(shared_fy2026_max_error):.12g}"
            if pd.notna(shared_fy2026_max_error)
            else f"groups={len(shared_fy2026_wide)}; max_high_medium_low_range=missing"
        ),
        expected=(
            f"{expected_shared_groups} FY2026 revenue/activity groups with "
            f"Low = Medium = High within {VALUE_TOLERANCE}"
        ),
        max_abs_error=(
            float(shared_fy2026_max_error)
            if pd.notna(shared_fy2026_max_error)
            else None
        ),
        detail=(
            "All three conflict paths share the same fuel-price and native "
            "activity inputs through FY2026. The raw PED bridge and default "
            "MoT VFM Base overlay are anchored to the same visible Base path, "
            "so future severity differences cannot leak backwards into the "
            "common annual checkpoint."
        ),
    )

    pair_keys = [
        "scenario_family_id",
        "FY",
        "series_id",
        "metric_type",
    ]
    published = _annual_values_by_family(
        annual, policy_state=FED_POLICY_STATE_PUBLISHED
    )[pair_keys + ["value"]].rename(columns={"value": "published_value"})
    off = _annual_values_by_family(
        annual, policy_state=FED_POLICY_STATE_NO_UPLIFT
    )[pair_keys + ["value"]].rename(columns={"value": "off_value"})
    policy_pairs_by_state: dict[str, pd.DataFrame] = {}
    original_pairs_by_state: dict[str, pd.DataFrame] = {}
    for deferral_spec in FED_POLICY_SPECS:
        if not deferral_spec.is_finite_deferral:
            continue
        state = deferral_spec.calculation_state_id
        delayed_values = _annual_values_by_family(annual, policy_state=state)[
            pair_keys + ["value"]
        ].rename(columns={"value": "delayed_value"})
        state_policy_pairs = delayed_values.merge(
            off,
            on=pair_keys,
            how="outer",
            validate="one_to_one",
            indicator=True,
        )
        state_policy_pairs["delta"] = (
            pd.to_numeric(state_policy_pairs["delayed_value"], errors="coerce")
            - pd.to_numeric(state_policy_pairs["off_value"], errors="coerce")
        )
        policy_pairs_by_state[state] = state_policy_pairs
        state_original_pairs = published.merge(
            delayed_values,
            on=pair_keys,
            how="outer",
            validate="one_to_one",
            indicator=True,
        )
        state_original_pairs["delta"] = (
            pd.to_numeric(state_original_pairs["published_value"], errors="coerce")
            - pd.to_numeric(state_original_pairs["delayed_value"], errors="coerce")
        )
        original_pairs_by_state[state] = state_original_pairs
    policy_pairs = policy_pairs_by_state[FED_POLICY_STATE_DELAYED_6M]
    original_pairs = original_pairs_by_state[FED_POLICY_STATE_DELAYED_6M]

    unaffected_activity_series = (
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "heavy_bev_ruc_net_km",
    )
    base_unaffected = activity[
        activity["scenario_family_id"].astype(str).eq("base")
        & activity["series_id"].astype(str).isin(unaffected_activity_series)
    ][["policy_state", "FY", "series_id", "value"]].copy()
    base_unaffected = base_unaffected.rename(columns={"value": "base_value"})
    conflict_unaffected = activity[
        activity["scenario_family_id"].astype(str).isin(CONFLICT_SEVERITIES)
        & activity["series_id"].astype(str).isin(unaffected_activity_series)
    ][
        [
            "scenario_family_id",
            "policy_state",
            "FY",
            "series_id",
            "value",
        ]
    ].copy()
    conflict_unaffected = conflict_unaffected.rename(
        columns={"value": "conflict_value"}
    )
    unaffected = conflict_unaffected.merge(
        base_unaffected,
        on=["policy_state", "FY", "series_id"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    unaffected["delta"] = (
        pd.to_numeric(unaffected["conflict_value"], errors="coerce")
        - pd.to_numeric(unaffected["base_value"], errors="coerce")
    )
    unaffected_max_error = pd.to_numeric(
        unaffected["delta"], errors="coerce"
    ).abs().max()
    add_check(
        "no_mechanical_diesel_spillover_to_electric_activity",
        passed=(
            len(unaffected)
            == len(CONFLICT_SEVERITIES)
            * len(_CALC_STATE_ORDER)
            * (END_FY - START_FY + 1)
            * len(unaffected_activity_series)
            and unaffected["_merge"].eq("both").all()
            and pd.notna(unaffected_max_error)
            and float(unaffected_max_error) <= VALUE_TOLERANCE
        ),
        observed=(
            f"comparisons={len(unaffected)}; "
            f"max_abs_conflict_minus_matched_base={float(unaffected_max_error):.12g}"
            if pd.notna(unaffected_max_error)
            else f"comparisons={len(unaffected)}; max_abs_conflict_minus_matched_base=missing"
        ),
        expected=(
            f"{len(CONFLICT_SEVERITIES) * len(_CALC_STATE_ORDER) * (END_FY - START_FY + 1) * len(unaffected_activity_series)} "
            "Light BEV/PHEV/Heavy BEV annual-km comparisons equal matched "
            f"Base within {VALUE_TOLERANCE}"
        ),
        max_abs_error=(
            float(unaffected_max_error)
            if pd.notna(unaffected_max_error)
            else None
        ),
        detail=(
            "Conflict diesel generalized cost affects conventional Light and "
            "Heavy activity only; electric activity must not inherit a "
            "mechanical diesel multiplier."
        ),
    )

    pre_policy = policy_pairs[policy_pairs["FY"].isin([2026, 2027])]
    pre_error = pd.to_numeric(pre_policy["delta"], errors="coerce").abs().max()
    add_check(
        "fy2026_fy2027_delayed_off_identity",
        passed=(
            not policy_pairs["_merge"].ne("both").any()
            and pd.notna(pre_error)
            and float(pre_error) <= VALUE_TOLERANCE
        ),
        observed=(
            f"rows={len(pre_policy)}; max_abs_delta={float(pre_error):.12g}"
            if pd.notna(pre_error)
            else f"rows={len(pre_policy)}; max_abs_delta=missing"
        ),
        expected=f"all annual delayed/off values equal through FY2027 within {VALUE_TOLERANCE}",
        max_abs_error=float(pre_error) if pd.notna(pre_error) else None,
        detail="The delayed 12c path begins in FY2028; whole-horizon model features must not leak divergence backwards.",
    )

    original_fy2026 = original_pairs[original_pairs["FY"].eq(2026)]
    original_fy2026_error = pd.to_numeric(
        original_fy2026["delta"], errors="coerce"
    ).abs().max()
    add_check(
        "fy2026_original_delayed_identity",
        passed=(
            original_fy2026["_merge"].eq("both").all()
            and pd.notna(original_fy2026_error)
            and float(original_fy2026_error) <= VALUE_TOLERANCE
        ),
        observed=(
            f"rows={len(original_fy2026)}; max_abs_delta={float(original_fy2026_error):.12g}"
            if pd.notna(original_fy2026_error)
            else f"rows={len(original_fy2026)}; max_abs_delta=missing"
        ),
        expected=f"all FY2026 original/delayed values equal within {VALUE_TOLERANCE}",
        max_abs_error=(
            float(original_fy2026_error)
            if pd.notna(original_fy2026_error)
            else None
        ),
        detail="The original 12c step does not begin until January 2027, after FY2026 closes.",
    )

    original_fy2027_tax = original_pairs[
        original_pairs["FY"].eq(2027)
        & original_pairs["series_id"].isin(
            ["net_fed_revenue", "total_ruc_net_revenue"]
        )
    ].copy()
    min_original_fy2027_tax_delta = pd.to_numeric(
        original_fy2027_tax["delta"], errors="coerce"
    ).min()
    add_check(
        "fy2027_original_revenue_exceeds_deferred",
        passed=(
            len(original_fy2027_tax) == 4 * 2
            and original_fy2027_tax["_merge"].eq("both").all()
            and pd.notna(min_original_fy2027_tax_delta)
            and float(min_original_fy2027_tax_delta) > VALUE_TOLERANCE
        ),
        observed=(
            f"rows={len(original_fy2027_tax)}; "
            f"min_original_minus_delayed={float(min_original_fy2027_tax_delta):.12g}"
            if pd.notna(min_original_fy2027_tax_delta)
            else f"rows={len(original_fy2027_tax)}; min_original_minus_delayed=missing"
        ),
        expected="8 FY2027 Net FED/Net RUC rows with original timing strictly above deferred",
        max_abs_error=None,
        detail=(
            "Original timing applies from January through June 2027, inside FY2027. "
            "The deferred path does not begin until 1 July 2027, which is FY2028."
        ),
    )

    original_fy2027_ped_volume = original_pairs[
        original_pairs["FY"].eq(2027)
        & original_pairs["series_id"].eq("ped_volume")
    ].copy()
    max_original_fy2027_volume_delta = pd.to_numeric(
        original_fy2027_ped_volume["delta"], errors="coerce"
    ).max()
    add_check(
        "fy2027_higher_original_pump_price_lowers_ped_volume",
        passed=(
            len(original_fy2027_ped_volume) == 4
            and original_fy2027_ped_volume["_merge"].eq("both").all()
            and pd.notna(max_original_fy2027_volume_delta)
            and float(max_original_fy2027_volume_delta) < -VALUE_TOLERANCE
        ),
        observed=(
            f"rows={len(original_fy2027_ped_volume)}; "
            f"max_original_minus_delayed_volume={float(max_original_fy2027_volume_delta):.12g}"
            if pd.notna(max_original_fy2027_volume_delta)
            else f"rows={len(original_fy2027_ped_volume)}; max_original_minus_delayed_volume=missing"
        ),
        expected="4 FY2027 PED-volume rows with original timing below deferred",
        max_abs_error=None,
        detail="The higher January-June 2027 pump price must reduce PED volume rather than leave it unchanged.",
    )

    resumed_original = original_pairs[
        original_pairs["FY"].between(2028, END_FY, inclusive="both")
    ].copy()
    resumed_original_error = pd.to_numeric(
        resumed_original["delta"], errors="coerce"
    ).abs().max()
    resumed_original_scale = pd.concat(
        [
            pd.to_numeric(
                resumed_original["published_value"], errors="coerce"
            ).abs(),
            pd.to_numeric(
                resumed_original["delayed_value"], errors="coerce"
            ).abs(),
        ],
        axis=1,
    ).max(axis=1)
    resumed_original_relative_error = (
        pd.to_numeric(resumed_original["delta"], errors="coerce").abs()
        / resumed_original_scale.clip(lower=VALUE_TOLERANCE)
    ).max()
    post_rejoin_relative_tolerance = 0.001
    add_check(
        "fy2028_plus_original_delayed_identity",
        passed=(
            not resumed_original.empty
            and resumed_original["_merge"].eq("both").all()
            and pd.notna(resumed_original_error)
            and pd.notna(resumed_original_relative_error)
            and float(resumed_original_relative_error)
            <= post_rejoin_relative_tolerance
        ),
        observed=(
            f"rows={len(resumed_original)}; "
            f"max_abs_delta={float(resumed_original_error):.12g}; "
            f"max_relative_delta={float(resumed_original_relative_error):.12g}"
            if pd.notna(resumed_original_error)
            and pd.notna(resumed_original_relative_error)
            else (
                f"rows={len(resumed_original)}; max_abs_delta=missing; "
                "max_relative_delta=missing"
            )
        ),
        expected=(
            f"all FY2028-FY{END_FY} original/delayed values within "
            f"{post_rejoin_relative_tolerance:.2%} after the input schedules rejoin"
        ),
        max_abs_error=(
            float(resumed_original_error)
            if pd.notna(resumed_original_error)
            else None
        ),
        detail=(
            "The deferred path rejoins the original published rate schedule on "
            "1 July 2027. A tightly bounded residual is allowed because lagged "
            "features preserve genuine path dependence from the preceding six months."
        ),
    )

    post_revenue = policy_pairs[
        policy_pairs["FY"].between(2028, 2030, inclusive="both")
        & policy_pairs["series_id"].isin(
            ["net_fed_revenue", "total_ruc_net_revenue"]
        )
    ].copy()
    min_post_delta = pd.to_numeric(post_revenue["delta"], errors="coerce").min()
    add_check(
        "fy2028_plus_policy_revenue_divergence",
        passed=(
            len(post_revenue) == 4 * 3 * 2
            and post_revenue["_merge"].eq("both").all()
            and pd.notna(min_post_delta)
            and float(min_post_delta) > VALUE_TOLERANCE
        ),
        observed=(
            f"rows={len(post_revenue)}; min_delayed_minus_off={float(min_post_delta):.12g}"
            if pd.notna(min_post_delta)
            else f"rows={len(post_revenue)}; min_delayed_minus_off=missing"
        ),
        expected="24 Net FED/Net RUC rows with delayed revenue strictly above off",
        max_abs_error=None,
        detail="The delayed policy collects the FED/RUC uplift from FY2028 while the off path does not.",
    )

    # The same identity, ordering and rejoin gates for every longer governed
    # deferral, with windows taken from the canonical registry. The six-month
    # checks above are the production-named originals and stay untouched.
    for deferral_spec in FED_POLICY_SPECS:
        if not deferral_spec.is_finite_deferral or deferral_spec.delay_months == 6:
            continue
        state = deferral_spec.calculation_state_id
        timing = deferral_spec.timing_id
        window = deferral_spec.direct_affected_quarters()
        last_window_quarter = window[-1]
        last_window_fy = int(last_window_quarter.split("Q")[0]) + (
            1 if int(last_window_quarter.split("Q")[1]) >= 3 else 0
        )
        start_quarter = deferral_spec.start_period
        shared_last_fy = int(start_quarter.split("Q")[0]) - (
            0 if int(start_quarter.split("Q")[1]) >= 3 else 1
        )
        state_policy_pairs = policy_pairs_by_state[state]
        state_original_pairs = original_pairs_by_state[state]

        shared_rows = state_policy_pairs[
            state_policy_pairs["FY"].between(START_FY, shared_last_fy, inclusive="both")
        ]
        shared_error = pd.to_numeric(shared_rows["delta"], errors="coerce").abs().max()
        add_check(
            f"{timing}_shared_window_delayed_off_identity",
            passed=(
                not state_policy_pairs["_merge"].ne("both").any()
                and pd.notna(shared_error)
                and float(shared_error) <= VALUE_TOLERANCE
            ),
            observed=(
                f"rows={len(shared_rows)}; max_abs_delta={float(shared_error):.12g}"
                if pd.notna(shared_error)
                else f"rows={len(shared_rows)}; max_abs_delta=missing"
            ),
            expected=(
                f"all annual {timing}/off values equal through FY{shared_last_fy} "
                f"within {VALUE_TOLERANCE}"
            ),
            max_abs_error=float(shared_error) if pd.notna(shared_error) else None,
            detail=(
                f"The {timing} path prices exactly like no-uplift until its deferred "
                f"start in {start_quarter}; whole-horizon model features must not "
                "leak the later divergence backwards."
            ),
        )

        state_fy2026 = state_original_pairs[state_original_pairs["FY"].eq(2026)]
        state_fy2026_error = pd.to_numeric(state_fy2026["delta"], errors="coerce").abs().max()
        add_check(
            f"{timing}_fy2026_original_identity",
            passed=(
                state_fy2026["_merge"].eq("both").all()
                and pd.notna(state_fy2026_error)
                and float(state_fy2026_error) <= VALUE_TOLERANCE
            ),
            observed=(
                f"rows={len(state_fy2026)}; max_abs_delta={float(state_fy2026_error):.12g}"
                if pd.notna(state_fy2026_error)
                else f"rows={len(state_fy2026)}; max_abs_delta=missing"
            ),
            expected=f"all FY2026 original/{timing} values equal within {VALUE_TOLERANCE}",
            max_abs_error=float(state_fy2026_error) if pd.notna(state_fy2026_error) else None,
            detail="No deferral changes anything before the 12c step's original January 2027 date.",
        )

        state_fy2027_tax = state_original_pairs[
            state_original_pairs["FY"].eq(2027)
            & state_original_pairs["series_id"].isin(
                ["net_fed_revenue", "total_ruc_net_revenue"]
            )
        ]
        state_min_fy2027 = pd.to_numeric(state_fy2027_tax["delta"], errors="coerce").min()
        add_check(
            f"{timing}_fy2027_original_revenue_exceeds_deferred",
            passed=(
                len(state_fy2027_tax) == 4 * 2
                and state_fy2027_tax["_merge"].eq("both").all()
                and pd.notna(state_min_fy2027)
                and float(state_min_fy2027) > VALUE_TOLERANCE
            ),
            observed=(
                f"rows={len(state_fy2027_tax)}; "
                f"min_original_minus_deferred={float(state_min_fy2027):.12g}"
                if pd.notna(state_min_fy2027)
                else f"rows={len(state_fy2027_tax)}; min_original_minus_deferred=missing"
            ),
            expected=(
                f"8 FY2027 Net FED/Net RUC rows with original timing strictly above {timing}"
            ),
            max_abs_error=None,
            detail=(
                "Every deferral removes the January-June 2027 uplift from FY2027 "
                "while original timing collects it."
            ),
        )

        rejoined = state_original_pairs[
            state_original_pairs["FY"].between(last_window_fy + 1, END_FY, inclusive="both")
        ].copy()
        if not rejoined.empty:
            rejoined_error = pd.to_numeric(rejoined["delta"], errors="coerce").abs().max()
            rejoined_scale = pd.concat(
                [
                    pd.to_numeric(rejoined["published_value"], errors="coerce").abs(),
                    pd.to_numeric(rejoined["delayed_value"], errors="coerce").abs(),
                ],
                axis=1,
            ).max(axis=1)
            rejoined_relative = (
                pd.to_numeric(rejoined["delta"], errors="coerce").abs()
                / rejoined_scale.clip(lower=VALUE_TOLERANCE)
            ).max()
            add_check(
                f"{timing}_rejoined_original_identity",
                passed=(
                    rejoined["_merge"].eq("both").all()
                    and pd.notna(rejoined_relative)
                    and float(rejoined_relative) <= post_rejoin_relative_tolerance
                ),
                observed=(
                    f"rows={len(rejoined)}; max_abs_delta={float(rejoined_error):.12g}; "
                    f"max_relative_delta={float(rejoined_relative):.12g}"
                    if pd.notna(rejoined_error) and pd.notna(rejoined_relative)
                    else f"rows={len(rejoined)}; deltas=missing"
                ),
                expected=(
                    f"all FY{last_window_fy + 1}-FY{END_FY} original/{timing} values within "
                    f"{post_rejoin_relative_tolerance:.2%} after catch-up in {start_quarter}"
                ),
                max_abs_error=float(rejoined_error) if pd.notna(rejoined_error) else None,
                detail=(
                    f"The {timing} path catches up to the published rate in {start_quarter}; "
                    "a tightly bounded residual is allowed because lagged features preserve "
                    "genuine path dependence from the deferral window."
                ),
            )

        state_post_revenue = state_policy_pairs[
            state_policy_pairs["FY"].between(last_window_fy + 1, END_FY, inclusive="both")
            & state_policy_pairs["series_id"].isin(
                ["net_fed_revenue", "total_ruc_net_revenue"]
            )
        ].copy()
        if not state_post_revenue.empty:
            state_min_post = pd.to_numeric(state_post_revenue["delta"], errors="coerce").min()
            add_check(
                f"{timing}_post_window_policy_revenue_divergence",
                passed=(
                    state_post_revenue["_merge"].eq("both").all()
                    and pd.notna(state_min_post)
                    and float(state_min_post) > VALUE_TOLERANCE
                ),
                observed=(
                    f"rows={len(state_post_revenue)}; "
                    f"min_deferred_minus_off={float(state_min_post):.12g}"
                    if pd.notna(state_min_post)
                    else f"rows={len(state_post_revenue)}; min_deferred_minus_off=missing"
                ),
                expected=(
                    f"every FY{last_window_fy + 1}-FY{END_FY} Net FED/Net RUC row with "
                    f"{timing} revenue strictly above off"
                ),
                max_abs_error=None,
                detail=(
                    f"After catching up in {start_quarter}, the {timing} path collects the "
                    "uplift while the off path never does."
                ),
            )

    forecast_source = replay.future_forecasts.copy()
    calibrated_required = {
        "scenario_name",
        "stream",
        "forecast",
        "demand_reference_scenario_name",
        "demand_reference_forecast",
        "demand_generalized_price_field",
        "demand_reference_price",
        "demand_variant_price",
        "demand_price_ratio",
        "demand_raw_forecast",
        "demand_price_only_raw_forecast",
        "demand_gdp_input_level_factor",
        "demand_gdp_model_factor_raw",
        "demand_gdp_model_factor",
        "demand_gdp_factor_source_scenario_name",
        "demand_gdp_factor_source_raw_forecast",
        "demand_gdp_factor_source_price_only_forecast",
        "demand_gdp_sign_guard_applied",
        "demand_gdp_downside_sign_guard_applied",
        "demand_gdp_identity_guard_applied",
        "demand_reference_fuel_cost_nzd_per_1000km",
        "demand_variant_fuel_cost_nzd_per_1000km",
        "demand_reference_ruc_price_nzd_per_1000km",
        "demand_variant_ruc_price_nzd_per_1000km",
        "demand_fuel_price_ratio",
        "demand_ruc_price_ratio",
        "demand_elasticity",
        "demand_calibration_applied",
        "demand_calibration_basis",
        "policy_calibration_applied",
        "policy_generalized_price_field",
        "policy_price_ratio",
        "policy_fuel_price_ratio",
        "policy_ruc_price_ratio",
        "policy_demand_elasticity",
        "policy_calibration_basis",
    }
    calibrated_missing_columns = sorted(
        calibrated_required.difference(forecast_source.columns)
    )
    if calibrated_missing_columns:
        calibrated = pd.DataFrame()
        policy_calibrated = pd.DataFrame()
        calibrated_formula_error = float("inf")
        raw_gdp_ratio_error = float("inf")
        gdp_source_name_valid = False
        identity_guard_valid = False
        downside_guard_valid = False
        combined_guard_valid = False
        sign_guard_valid = False
        generalized_cost_error = float("inf")
        component_audit_error = float("inf")
        compounded_non_equivalent_count = 0
        calibrated_valid = False
    else:
        calibrated = forecast_source[
            forecast_source["stream"].astype(str).isin(
                ["LIGHT_RUC", "HEAVY_RUC"]
            )
            & forecast_source["demand_calibration_applied"]
            .fillna(False)
            .astype(bool)
        ].copy()
        numeric_columns = [
            "forecast",
            "demand_reference_forecast",
            "demand_reference_price",
            "demand_variant_price",
            "demand_price_ratio",
            "demand_raw_forecast",
            "demand_price_only_raw_forecast",
            "demand_gdp_input_level_factor",
            "demand_gdp_model_factor_raw",
            "demand_gdp_model_factor",
            "demand_gdp_factor_source_raw_forecast",
            "demand_gdp_factor_source_price_only_forecast",
            "demand_reference_fuel_cost_nzd_per_1000km",
            "demand_variant_fuel_cost_nzd_per_1000km",
            "demand_reference_ruc_price_nzd_per_1000km",
            "demand_variant_ruc_price_nzd_per_1000km",
            "demand_fuel_price_ratio",
            "demand_ruc_price_ratio",
            "demand_elasticity",
            "policy_price_ratio",
            "policy_fuel_price_ratio",
            "policy_ruc_price_ratio",
            "policy_demand_elasticity",
        ]
        for column in numeric_columns:
            calibrated[column] = pd.to_numeric(
                calibrated[column], errors="coerce"
            )
        single_formula_expected = calibrated[
            "demand_reference_forecast"
        ] * calibrated["demand_price_ratio"].pow(
            calibrated["demand_elasticity"]
        ) * calibrated["demand_gdp_model_factor"]
        calibrated_formula_error = (
            calibrated["forecast"] - single_formula_expected
        ).abs().max()
        raw_gdp_ratio_expected = (
            calibrated["demand_gdp_factor_source_raw_forecast"]
            / calibrated[
                "demand_gdp_factor_source_price_only_forecast"
            ]
        )
        raw_gdp_ratio_error = (
            calibrated["demand_gdp_model_factor_raw"] - raw_gdp_ratio_expected
        ).abs().max()
        expected_gdp_source_by_scenario = {
            path.scenario_id: (
                str(replay.base_scenario_name)
                if path.family_id == "base"
                else conflict_scenario_name(path.severity)
            )
            for path in paths
            if path.policy_state != FED_POLICY_STATE_PUBLISHED
        }
        expected_gdp_source_by_scenario.update(
            {
                conflict_scenario_name(severity): conflict_scenario_name(
                    severity
                )
                for severity in CONFLICT_SEVERITIES
            }
        )
        expected_gdp_sources = (
            calibrated["scenario_name"]
            .astype(str)
            .map(expected_gdp_source_by_scenario)
        )
        gdp_source_name_valid = bool(
            expected_gdp_sources.notna().all()
            and calibrated[
                "demand_gdp_factor_source_scenario_name"
            ]
            .astype(str)
            .eq(expected_gdp_sources)
            .all()
        )
        gdp_input = calibrated["demand_gdp_input_level_factor"]
        gdp_factor_raw = calibrated["demand_gdp_model_factor_raw"]
        gdp_factor = calibrated["demand_gdp_model_factor"]
        identity_input = gdp_input.sub(1.0).abs().le(1e-12)
        expected_identity_guard = (
            identity_input & gdp_factor_raw.sub(1.0).abs().gt(1e-12)
        )
        expected_downside_guard = (
            gdp_input.lt(1.0 - 1e-12) & gdp_factor_raw.gt(1.0)
        )
        identity_guard = (
            calibrated["demand_gdp_identity_guard_applied"]
            .fillna(False)
            .astype(bool)
        )
        downside_guard = (
            calibrated["demand_gdp_downside_sign_guard_applied"]
            .fillna(False)
            .astype(bool)
        )
        combined_guard = (
            calibrated["demand_gdp_sign_guard_applied"].fillna(False).astype(bool)
        )
        identity_guard_valid = bool(
            identity_guard.eq(expected_identity_guard).all()
            and gdp_factor.loc[identity_input]
            .sub(1.0)
            .abs()
            .le(VALUE_TOLERANCE)
            .all()
        )
        downside_guard_valid = bool(
            downside_guard.eq(expected_downside_guard).all()
            and gdp_factor.loc[gdp_input.lt(1.0 - 1e-12)]
            .le(1.0)
            .all()
            and gdp_factor_raw.loc[downside_guard].gt(1.0).all()
            and gdp_factor.loc[downside_guard]
            .sub(1.0)
            .abs()
            .le(VALUE_TOLERANCE)
            .all()
        )
        combined_guard_valid = bool(
            combined_guard.eq(identity_guard | downside_guard).all()
        )
        sign_guard_valid = bool(
            identity_guard_valid
            and downside_guard_valid
            and combined_guard_valid
            and gdp_factor.gt(0.0).all()
        )
        expected_reference_cost = (
            calibrated["demand_reference_fuel_cost_nzd_per_1000km"]
            + calibrated["demand_reference_ruc_price_nzd_per_1000km"]
        )
        expected_variant_cost = (
            calibrated["demand_variant_fuel_cost_nzd_per_1000km"]
            + calibrated["demand_variant_ruc_price_nzd_per_1000km"]
        )
        generalized_cost_error = max(
            float(
                (
                    calibrated["demand_reference_price"]
                    - expected_reference_cost
                )
                .abs()
                .max()
            ),
            float(
                (
                    calibrated["demand_variant_price"]
                    - expected_variant_cost
                )
                .abs()
                .max()
            ),
            float(
                (
                    calibrated["demand_price_ratio"]
                    - expected_variant_cost / expected_reference_cost
                )
                .abs()
                .max()
            ),
        )
        policy_calibrated = calibrated[
            calibrated["policy_calibration_applied"]
            .fillna(False)
            .astype(bool)
        ].copy()
        policy_component_errors = [
            (
                policy_calibrated["policy_price_ratio"]
                - policy_calibrated["demand_price_ratio"]
            )
            .abs()
            .max(),
            (
                policy_calibrated["policy_fuel_price_ratio"]
                - policy_calibrated["demand_fuel_price_ratio"]
            )
            .abs()
            .max(),
            (
                policy_calibrated["policy_ruc_price_ratio"]
                - policy_calibrated["demand_ruc_price_ratio"]
            )
            .abs()
            .max(),
            (
                policy_calibrated["policy_demand_elasticity"]
                - policy_calibrated["demand_elasticity"]
            )
            .abs()
            .max(),
        ]
        numeric_component_errors = [
            float(value) for value in policy_component_errors if pd.notna(value)
        ]
        component_audit_error = max(
            numeric_component_errors, default=float("inf")
        )
        separately_compounded = policy_calibrated[
            "demand_reference_forecast"
        ] * policy_calibrated["policy_fuel_price_ratio"].pow(
            policy_calibrated["policy_demand_elasticity"]
        ) * policy_calibrated["policy_ruc_price_ratio"].pow(
            policy_calibrated["policy_demand_elasticity"]
        ) * policy_calibrated["demand_gdp_model_factor"]
        compounded_non_equivalent_count = int(
            (
                separately_compounded - policy_calibrated["forecast"]
            )
            .abs()
            .gt(VALUE_TOLERANCE)
            .sum()
        )
        generalized_field_valid = calibrated[
            "demand_generalized_price_field"
        ].astype(str).eq(
            "diesel_plus_ruc_cost_nzd_per_1000km"
        ).all()
        calibration_basis_valid = calibrated[
            "demand_calibration_basis"
        ].astype(str).eq(
            "governed_single_generalized_running_cost_elasticity"
        ).all()
        policy_audit_valid = (
            not policy_calibrated.empty
            and policy_calibrated["policy_generalized_price_field"]
            .astype(str)
            .eq("diesel_plus_ruc_cost_nzd_per_1000km")
            .all()
            and policy_calibrated["policy_calibration_basis"]
            .astype(str)
            .eq("governed_single_generalized_running_cost_elasticity")
            .all()
        )
        calibrated_valid = (
            not calibrated.empty
            and calibrated[
                [
                    "forecast",
                    "demand_reference_forecast",
                    "demand_reference_price",
                    "demand_variant_price",
                    "demand_price_ratio",
                    "demand_raw_forecast",
                    "demand_price_only_raw_forecast",
                    "demand_gdp_input_level_factor",
                    "demand_gdp_model_factor_raw",
                    "demand_gdp_model_factor",
                    "demand_gdp_factor_source_raw_forecast",
                    "demand_gdp_factor_source_price_only_forecast",
                ]
            ].notna().all().all()
            and calibrated["demand_reference_scenario_name"]
            .astype(str)
            .eq(str(replay.base_scenario_name))
            .all()
            and gdp_source_name_valid
            and generalized_field_valid
            and calibration_basis_valid
            and policy_audit_valid
            and pd.notna(calibrated_formula_error)
            and float(calibrated_formula_error) <= VALUE_TOLERANCE
            and pd.notna(raw_gdp_ratio_error)
            and float(raw_gdp_ratio_error) <= VALUE_TOLERANCE
            and sign_guard_valid
            and generalized_cost_error <= VALUE_TOLERANCE
            and component_audit_error <= VALUE_TOLERANCE
            and compounded_non_equivalent_count > 0
        )
    add_check(
        "single_generalized_cost_elasticity_conventional_ruc",
        passed=calibrated_valid,
        observed=(
            f"calibrated_rows={len(calibrated)}; "
            f"policy_rows={len(policy_calibrated)}; "
            f"missing_columns={len(calibrated_missing_columns)}; "
            f"max_formula_error={calibrated_formula_error:.12g}; "
            f"max_raw_gdp_ratio_error={raw_gdp_ratio_error:.12g}; "
            f"gdp_source_names_valid={gdp_source_name_valid}; "
            f"gdp_identity_guard_valid={identity_guard_valid}; "
            f"gdp_downside_guard_valid={downside_guard_valid}; "
            f"gdp_combined_guard_valid={combined_guard_valid}; "
            f"max_cost_identity_error={generalized_cost_error:.12g}; "
            f"max_component_audit_error={component_audit_error:.12g}; "
            f"rows_where_separate_compounding_would_differ="
            f"{compounded_non_equivalent_count}"
        ),
        expected=(
            "Every calibrated conventional Light/Heavy row equals Base "
            "reference x (diesel fuel cost + RUC cost ratio)^elasticity once "
            "x the published-family GDP-response factor; "
            "component fuel/RUC ratios are audit-only and are not compounded"
        ),
        max_abs_error=(
            max(
                float(calibrated_formula_error),
                float(raw_gdp_ratio_error),
                float(generalized_cost_error),
                float(component_audit_error),
            )
            if calibrated_valid or not calibrated_missing_columns
            else None
        ),
        detail=(
            "The replay audit exposes the combined cost numerator, denominator, "
            "ratio, one governed elasticity and the published-family price-plus-GDP "
            "versus price-only response. Identity-input and lower-GDP sign guards "
            "are validated separately. A separate fuel-ratio x RUC-ratio elasticity "
            "calculation is intentionally not the output formula."
        ),
    )

    # Test the causal claim at the model's native quarterly grain. Annual
    # totals can legitimately retain dynamic lag/carry after a nominal price
    # path has converged, so annual Low/Medium/High rank is not a direct
    # elasticity invariant. Every quarter with a strictly positive conflict
    # price wedge must, however, have lower matched activity than Base.
    forecast_source["forecast_numeric"] = pd.to_numeric(
        forecast_source["forecast"], errors="coerce"
    )
    forecast_lookup = {
        (str(row.scenario_name), str(row.stream), str(row.target_period)): float(
            row.forecast_numeric
        )
        for row in forecast_source.itertuples(index=False)
        if pd.notna(row.forecast_numeric)
    }
    nominal_paths = (
        assumptions[
            assumptions["scenario_family_id"].isin(CONFLICT_SEVERITIES)
        ]
        .sort_values(["path_order", "period"], kind="stable")
        .drop_duplicates(["scenario_family_id", "period"], keep="first")
    )
    response_deltas: list[float] = []
    missing_direct_rows: list[str] = []
    for row in nominal_paths.itertuples(index=False):
        severity = str(row.scenario_family_id)
        period = str(row.period)
        scenario_id = conflict_scenario_name(severity)
        for stream, ratio in (
            ("PED", float(row.petrol_ratio)),
            ("LIGHT_RUC", float(row.diesel_ratio)),
            ("HEAVY_RUC", float(row.diesel_ratio)),
        ):
            if ratio <= 1.0 + 1e-12:
                continue
            base_key = (str(replay.base_scenario_name), stream, period)
            conflict_key = (scenario_id, stream, period)
            if base_key not in forecast_lookup or conflict_key not in forecast_lookup:
                missing_direct_rows.append(f"{severity}/{stream}/{period}")
                continue
            response_deltas.append(
                forecast_lookup[base_key] - forecast_lookup[conflict_key]
            )
    min_direct_response = min(response_deltas, default=float("-inf"))
    add_check(
        "higher_conflict_prices_lower_direct_activity",
        passed=(
            not missing_direct_rows
            and bool(response_deltas)
            and min_direct_response > VALUE_TOLERANCE
        ),
        observed=(
            f"direct_price_activity_comparisons={len(response_deltas)}; "
            f"missing={len(missing_direct_rows)}; "
            f"min_base_minus_conflict_activity={min_direct_response:.12g}"
        ),
        expected=(
            "Every published conflict quarter with petrol/diesel above Base "
            "has strictly lower matched PED/Light/Heavy activity"
        ),
        max_abs_error=max(0.0, -min_direct_response),
        detail=(
            "PED uses petrol; Light and Heavy RUC use diesel. The comparison "
            "is evaluated at the native quarterly grain before annual dynamic "
            "carry can obscure the direct price response."
        ),
    )

    validation = pd.DataFrame(checks)
    return validation[
        [
            "check_id",
            "status",
            "passed",
            "observed",
            "expected",
            "max_abs_error",
            "detail",
            "source_engine",
            "extract_version",
        ]
    ]


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.12g",
    )


def materialize(repo_root: Path, output_dir: Path) -> dict[str, Path]:
    """Run the governed AR(1) replay, validate it, and write four CSVs."""

    root = repo_root.resolve()
    out_dir = output_dir.resolve()
    pack_dir = root / engine_revenue_outlook_dir(ENGINE_AR1)
    input_path = pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    if not input_path.exists():
        raise FileNotFoundError(f"AR(1) scenario inputs not found: {input_path}")

    scenario_inputs = pd.read_parquet(input_path)
    replay = run_fuel_price_scenario_replay(
        scenario_inputs,
        repo_root=root,
        engine=ENGINE_AR1,
    )
    paths = _export_paths()
    conflict_paths = load_conflict_fuel_price_paths(root)
    assumptions = _assumptions_frame(
        conflict_paths,
        replay.replay_inputs,
        paths,
        repo_root=root,
        pack_dir=pack_dir,
    )
    dashboard_annual_bridge = _dashboard_aligned_annual_bridge(
        replay,
        paths,
        repo_root=root,
        pack_dir=pack_dir,
    )
    revenue = _annual_export_frame(
        dashboard_annual_bridge,
        paths,
        metric_type="revenue",
        repo_root=root,
        pack_dir=pack_dir,
    )
    activity = _annual_export_frame(
        dashboard_annual_bridge,
        paths,
        metric_type="activity",
        repo_root=root,
        pack_dir=pack_dir,
    )
    validation = _validation_frame(
        replay=replay,
        assumptions=assumptions,
        revenue=revenue,
        activity=activity,
        paths=paths,
    )

    outputs = {
        "assumptions": out_dir / ASSUMPTIONS_FILENAME,
        "revenue": out_dir / REVENUE_FILENAME,
        "activity": out_dir / ACTIVITY_FILENAME,
        "validation": out_dir / VALIDATION_FILENAME,
    }
    _write_csv(assumptions, outputs["assumptions"])
    _write_csv(revenue, outputs["revenue"])
    _write_csv(activity, outputs["activity"])
    _write_csv(validation, outputs["validation"])

    failed = validation[~validation["passed"].astype(bool)]
    if not failed.empty:
        detail = "; ".join(
            f"{row.check_id}: {row.observed}"
            for row in failed.itertuples(index=False)
        )
        raise ValueError(
            "Conflict scenario extract validation failed after writing the "
            f"diagnostic summary: {detail}"
        )
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the governed AR(1) Middle East conflict replay and materialize "
            "the deterministic FY2026-FY2030 workbook source CSVs."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to the parent of scripts/).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory that will receive the four deterministic CSV files.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    outputs = materialize(args.repo_root, args.output_dir)
    for key, path in outputs.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

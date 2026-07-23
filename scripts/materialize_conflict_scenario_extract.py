"""Materialize the governed AR(1) conflict-scenario workbook source tables.

This command deliberately calls the same ``run_fuel_price_scenario_replay``
entry point as the dashboard.  It does not recreate scenario arithmetic in an
export-only code path.  Four deterministic CSVs are written:

* ``conflict_scenario_assumptions.csv`` - nominal source paths and the exact
  real-price model inputs for the eight exported policy paths;
* ``conflict_scenario_annual_revenue.csv`` - every FY2026-FY2030 annual
  revenue row from the governed replay bridge;
* ``conflict_scenario_annual_activity.csv`` - every FY2026-FY2030 annual
  activity/volume row from the governed replay bridge;
* ``conflict_scenario_validation.csv`` - machine-readable invariant checks.

The source fuel paths are policy-free.  The delayed/off 12c FED and matching
RUC policy states are composed by the replay and are never embedded in the
nominal conflict-price CSV.
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
from model_dashboard.fuel_price_scenario import (
    BASE_DELAYED_6M_SCENARIO_NAME,
    BASE_NO_UPLIFT_SCENARIO_NAME,
    POLICY_PATH_IDS,
    run_fuel_price_scenario_replay,
)
from model_dashboard.mbu26_source_spine import (
    CURRENT_LIGHT_TOTAL_SERIES_ID,
    FORMULA_DEFINITIONS,
    ROW_DEFINITIONS,
)
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
)


START_FY = 2026
END_FY = 2030
EXTRACT_VERSION = "governed-ar1-conflict-scenario-extract-v1"
ASSUMPTIONS_FILENAME = "conflict_scenario_assumptions.csv"
REVENUE_FILENAME = "conflict_scenario_annual_revenue.csv"
ACTIVITY_FILENAME = "conflict_scenario_annual_activity.csv"
VALIDATION_FILENAME = "conflict_scenario_validation.csv"
VALUE_TOLERANCE = 1e-8

_POLICY_LABELS = {
    FED_POLICY_STATE_DELAYED_6M: "12c deferred six months: from 1 Jul 2027",
    FED_POLICY_STATE_NO_UPLIFT: "12c uplift off",
}
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
    """Stable metadata for one of the eight requested export paths."""

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


def _export_paths() -> tuple[ExportPath, ...]:
    paths: list[ExportPath] = []
    family_specs = [
        (
            "base",
            0,
            "",
            "Current finalist Base case",
            {
                FED_POLICY_STATE_DELAYED_6M: BASE_DELAYED_6M_SCENARIO_NAME,
                FED_POLICY_STATE_NO_UPLIFT: BASE_NO_UPLIFT_SCENARIO_NAME,
            },
        ),
        *[
            (
                severity,
                family_order,
                severity,
                conflict_scenario_display_name(severity),
                {
                    state: conflict_policy_variant_name(severity, state)
                    for state in (
                        FED_POLICY_STATE_DELAYED_6M,
                        FED_POLICY_STATE_NO_UPLIFT,
                    )
                },
            )
            for family_order, severity in enumerate(CONFLICT_SEVERITIES, start=1)
        ],
    ]
    path_order = 0
    for family_id, family_order, severity, label, scenario_by_state in family_specs:
        for policy_state in (
            FED_POLICY_STATE_DELAYED_6M,
            FED_POLICY_STATE_NO_UPLIFT,
        ):
            scenario_id = scenario_by_state[policy_state]
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
            }
            for path in paths
        ]
    )


def _model_input_path(
    replay_inputs: pd.DataFrame,
    *,
    scenario_id: str,
) -> pd.DataFrame:
    """Return one row per quarter with the exact replay price inputs."""

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
    )
    periods = sorted(source["canonical_period"].dropna().astype(str).unique())
    out = pd.DataFrame({"period": periods})
    for output_column, stream, input_column in field_specs:
        if input_column not in source.columns:
            raise ValueError(
                f"Replay inputs are missing required model price field {input_column!r}."
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
    ]
    if out[required_output_columns].isna().any().any():
        raise ValueError(f"Replay inputs contain missing price values for {scenario_id!r}.")
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
        "extract_version",
    ]
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out[columns].sort_values(
        ["path_order", "period"], kind="stable"
    ).reset_index(drop=True)


def _annual_export_frame(
    annual_bridge: pd.DataFrame,
    paths: tuple[ExportPath, ...],
    *,
    metric_type: str,
    repo_root: Path,
    pack_dir: Path,
) -> pd.DataFrame:
    """Select all annual bridge rows of one metric type for eight paths."""

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
    out["extraction_basis"] = (
        "FuelPriceScenarioReplayResult.annual_bridge; same governed replay "
        "entry point used by the dashboard"
    )
    out["scenario_note"] = out["scenario_family_id"].map(
        lambda family: (
            "Current finalist Base case with the selected 12c FED/RUC policy."
            if family == "base"
            else conflict_scenario_note(family)
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
        "source_file",
        "source_cell",
        "model_id",
        "value_status",
        "scenario_note",
        "source_engine",
        "source_pack",
        "scenario_config_file",
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
    add_check(
        "internal_scenario_count",
        passed=(
            actual_internal == expected_internal
            and validation_internal == expected_internal
            and len(expected_internal) == 12
        ),
        observed=(
            f"inputs={len(actual_internal)}; validation={len(validation_internal)}"
        ),
        expected="12 exact Base/published-conflict/policy scenarios",
        detail="The governed replay must contain four published paths and eight delayed/off policy paths.",
    )

    expected_paths = [path.policy_path_id for path in paths]
    observed_assumption_paths = assumptions["path_id"].drop_duplicates().tolist()
    observed_revenue_paths = revenue["path_id"].drop_duplicates().tolist()
    observed_activity_paths = activity["path_id"].drop_duplicates().tolist()
    add_check(
        "export_path_count_and_order",
        passed=(
            len(expected_paths) == 8
            and observed_assumption_paths == expected_paths
            and observed_revenue_paths == expected_paths
            and observed_activity_paths == expected_paths
        ),
        observed=(
            f"assumptions={len(observed_assumption_paths)}; "
            f"revenue={len(observed_revenue_paths)}; "
            f"activity={len(observed_activity_paths)}"
        ),
        expected="8 paths in Base, Low, Medium, High x delayed, off order",
        detail="All three export tables share the same stable path IDs and display order.",
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
        * 2
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
            "activity inputs through FY2026. The optimized EV/PHEV migration "
            "lambda is anchored to Base so future severity differences cannot "
            "leak backwards into the common annual checkpoint."
        ),
    )

    pair_keys = [
        "scenario_family_id",
        "FY",
        "series_id",
        "metric_type",
    ]
    delayed = _annual_values_by_family(
        annual, policy_state=FED_POLICY_STATE_DELAYED_6M
    )[pair_keys + ["value"]].rename(columns={"value": "delayed_value"})
    off = _annual_values_by_family(
        annual, policy_state=FED_POLICY_STATE_NO_UPLIFT
    )[pair_keys + ["value"]].rename(columns={"value": "off_value"})
    policy_pairs = delayed.merge(
        off,
        on=pair_keys,
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    policy_pairs["delta"] = (
        pd.to_numeric(policy_pairs["delayed_value"], errors="coerce")
        - pd.to_numeric(policy_pairs["off_value"], errors="coerce")
    )

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
            * 2
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
            "90 Light BEV/PHEV/Heavy BEV annual-km comparisons equal matched "
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
        )
        calibrated_formula_error = (
            calibrated["forecast"] - single_formula_expected
        ).abs().max()
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
        )
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
            and calibrated[numeric_columns[:12]].notna().all().all()
            and calibrated["demand_reference_scenario_name"]
            .astype(str)
            .eq(str(replay.base_scenario_name))
            .all()
            and generalized_field_valid
            and calibration_basis_valid
            and policy_audit_valid
            and pd.notna(calibrated_formula_error)
            and float(calibrated_formula_error) <= VALUE_TOLERANCE
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
            f"max_cost_identity_error={generalized_cost_error:.12g}; "
            f"max_component_audit_error={component_audit_error:.12g}; "
            f"rows_where_separate_compounding_would_differ="
            f"{compounded_non_equivalent_count}"
        ),
        expected=(
            "Every calibrated conventional Light/Heavy row equals Base "
            "reference x (diesel fuel cost + RUC cost ratio)^elasticity once; "
            "component fuel/RUC ratios are audit-only and are not compounded"
        ),
        max_abs_error=(
            max(
                float(calibrated_formula_error),
                float(generalized_cost_error),
                float(component_audit_error),
            )
            if calibrated_valid or not calibrated_missing_columns
            else None
        ),
        detail=(
            "The replay audit exposes the combined cost numerator, denominator, "
            "ratio and one governed elasticity. A separate fuel-ratio x "
            "RUC-ratio elasticity calculation is intentionally not the output "
            "formula."
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
    revenue = _annual_export_frame(
        replay.annual_bridge,
        paths,
        metric_type="revenue",
        repo_root=root,
        pack_dir=pack_dir,
    )
    activity = _annual_export_frame(
        replay.annual_bridge,
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

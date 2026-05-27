from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = ROOT / "data" / "dashboard_evidence_pack"
DEFAULT_WORKBOOK = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "Playground"
    / "Revenue Modeling - Strategic Review"
    / "04 Models"
    / "Inputs"
    / "Master Copy revenue modelling workbook.xlsx"
)
DEFAULT_HEAVY_COMPONENT_RUN = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "Playground"
    / "Revenue Modeling - Strategic Review"
    / "04 Models"
    / "Inputs"
    / "heavy_ruc_fullgrid_rescue_closure_outputs"
    / "run_20260521_171358"
)

REQUIRED_WORKBOOK_SHEETS = {
    "PED": "PED Inputs",
    "LIGHT_RUC": "Light RUC Inputs",
    "HEAVY_RUC": "Heavy RUC Inputs",
}

TARGET_COLUMNS = {
    "PED": "Light petrol VKT per capita (km)",
    "LIGHT_RUC": "Light RUC net km",
    "HEAVY_RUC": "Heavy RUC net km",
}

SENSITIVITY_VARIABLES = [
    "GDP",
    "fuel price",
    "RUC price",
    "unemployment",
    "target lag",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build finalist reproducibility audit tables for the dashboard evidence pack.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--heavy-component-run", default=str(DEFAULT_HEAVY_COMPONENT_RUN))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def read_table(data_dir: Path, name: str) -> pd.DataFrame:
    path = data_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Missing evidence table: {path}")
    return pd.read_parquet(path)


def workbook_profiles(workbook: Path) -> dict[str, dict[str, Any]]:
    if not workbook.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook}")
    profiles: dict[str, dict[str, Any]] = {}
    xls = pd.ExcelFile(workbook)
    missing = [sheet for sheet in REQUIRED_WORKBOOK_SHEETS.values() if sheet not in xls.sheet_names]
    if missing:
        raise AssertionError("Workbook is missing required input sheet(s): " + ", ".join(missing))
    for stream, sheet in REQUIRED_WORKBOOK_SHEETS.items():
        header = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
        columns = [str(column) for column in header.columns]
        target = TARGET_COLUMNS[stream]
        exclude = {"Quarter", "Period", "Data status", "Notes", target}
        features = [column for column in columns if column not in exclude]
        profiles[stream] = {
            "source_sheet": sheet,
            "target_column": target,
            "feature_columns": features,
            "all_columns": columns,
        }
    return profiles


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    workbook = Path(args.workbook).expanduser().resolve()
    heavy_component_run = Path(args.heavy_component_run).expanduser().resolve()
    data_dir = data_root / "data"
    docs_dir = data_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    profiles = workbook_profiles(workbook)
    tables = {
        "finalists": read_table(data_dir, "finalists.parquet"),
        "schiff_benchmark": read_table(data_dir, "schiff_benchmark.parquet"),
        "ensemble_components": read_table(data_dir, "ensemble_components.parquet"),
        "scorecard_predictions": read_table(data_dir, "scorecard_predictions.parquet"),
        "scorecard_model_summary": read_table(data_dir, "scorecard_model_summary.parquet"),
    }

    registry = build_model_registry(tables, profiles, workbook, heavy_component_run)
    component_predictions = build_component_predictions(tables, heavy_component_run)
    coefficients = build_coefficients_table(registry)
    feature_importance = build_feature_importance_table(registry)
    scenario_sensitivities = build_scenario_sensitivities_table(registry)
    shap_summary = build_shap_summary_table(registry)

    outputs = {
        "model_registry.parquet": registry,
        "component_predictions.parquet": component_predictions,
        "model_coefficients.parquet": coefficients,
        "feature_importance.parquet": feature_importance,
        "scenario_sensitivities.parquet": scenario_sensitivities,
        "shap_summary.parquet": shap_summary,
    }
    for filename, frame in outputs.items():
        frame.to_parquet(data_dir / filename, index=False)

    validation = validate_reproducibility_tables(tables, component_predictions, registry)
    artifact_search_report = reproducibility_artifact_search_report(
        data_root=data_root,
        workbook=workbook,
        heavy_component_run=heavy_component_run,
        repo_root=repo_root,
    )
    (docs_dir / "reproducibility_artifact_search.md").write_text(artifact_search_report, encoding="utf-8")
    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    (artifacts_dir / "reproducibility_artifact_search.md").write_text(artifact_search_report, encoding="utf-8")
    report = reproducibility_report(data_root, workbook, outputs, validation)
    (docs_dir / "reproducibility_report.md").write_text(report, encoding="utf-8")

    update_inventory_and_manifest(data_root)
    print(report)
    return 0


def build_model_registry(
    tables: dict[str, pd.DataFrame],
    profiles: dict[str, dict[str, Any]],
    workbook: Path,
    heavy_component_run: Path | None = None,
) -> pd.DataFrame:
    finalists = tables["finalists"].copy()
    schiff = tables["schiff_benchmark"].copy()
    components = tables["ensemble_components"].copy()
    scorecard = tables["scorecard_predictions"].copy()
    rows: list[dict[str, Any]] = []

    for _, row in finalists.iterrows():
        stream = str(row["stream"])
        rows.append(
            registry_row(
                stream=stream,
                stream_label=row.get("stream_label"),
                model=row.get("model"),
                component_model=row.get("model"),
                model_role="current_finalist",
                source_row=row,
                profiles=profiles,
                workbook=workbook,
                scorecard=scorecard,
                status="incomplete",
                note="Final predictions reconcile to the evidence pack, but source script, fitted object, coefficients/importances, and workbook-only rebuild path are not fully available.",
            )
        )

    for _, row in schiff.iterrows():
        stream = str(row["stream"])
        rows.append(
            registry_row(
                stream=stream,
                stream_label=row.get("stream_label"),
                model=row.get("model"),
                component_model=row.get("model"),
                model_role="schiff_benchmark",
                source_row=row,
                profiles=profiles,
                workbook=workbook,
                scorecard=scorecard,
                status="incomplete",
                note="Schiff benchmark predictions reconcile to the evidence pack; workbook formula and exact fitted/rebuild path still need executable capture.",
            )
        )

    for _, row in components.iterrows():
        stream = str(row["stream"])
        component_model = row.get("component_model")
        rows.append(
            registry_row(
                stream=stream,
                stream_label=row.get("stream_label"),
                model=row.get("finalist_model"),
                component_model=component_model,
                model_role="ensemble_component",
                source_row=row,
                profiles=profiles,
                workbook=workbook,
                scorecard=scorecard,
                status="traceable" if float(row.get("weight", 0) or 0) == 1.0 else "incomplete",
                note=component_status_note(row),
            )
        )

    out = pd.DataFrame(rows)
    required = [
        "stream",
        "model",
        "component_model",
        "model_role",
        "algorithm",
        "target_column",
        "target_transform",
        "prediction_inverse_transform",
        "feature_set",
        "feature_columns",
        "window_type",
        "window_length",
        "origin_grid",
        "score_basis",
        "covid_test_exclusion_rule",
        "hyperparameters_json",
        "random_state",
        "source_script",
        "source_script_hash",
        "source_workbook",
        "source_sheet",
    ]
    for column in required:
        if column not in out.columns:
            out[column] = ""
    return enrich_registry_from_heavy_config(out, heavy_component_run)


def enrich_registry_from_heavy_config(registry: pd.DataFrame, heavy_component_run: Path | None) -> pd.DataFrame:
    if heavy_component_run is None:
        return registry
    config_path = heavy_component_run / "candidate_config_inventory.csv"
    features_path = heavy_component_run / "feature_inventory.csv"
    if not config_path.exists():
        return registry
    config = pd.read_csv(config_path)
    feature_columns: list[str] = []
    if features_path.exists():
        features = pd.read_csv(features_path)
        feature_columns = (
            features.loc[features["stream"].astype(str).eq("HEAVY_RUC"), "feature_column"].dropna().astype(str).tolist()
        )
    config_by_name = config.drop_duplicates("name").set_index("name")
    out = registry.copy()
    for index, row in out.iterrows():
        if str(row.get("stream")) != "HEAVY_RUC":
            continue
        component_model = str(row.get("component_model") or "")
        if component_model not in config_by_name.index:
            continue
        source = config_by_name.loc[component_model]
        params = str(source.get("params_json", "") or "")
        if params and params.lower() != "nan":
            out.at[index, "hyperparameters_json"] = normalize_json_text(params)
            parsed = parse_json_dict(params)
            if "random_state" in parsed:
                out.at[index, "random_state"] = str(parsed["random_state"])
        if pd.notna(source.get("feature_set")):
            out.at[index, "feature_set"] = source.get("feature_set")
        if pd.notna(source.get("window")):
            out.at[index, "window_length"] = float(source.get("window"))
            out.at[index, "window_type"] = "rolling"
        if feature_columns:
            out.at[index, "feature_columns"] = json.dumps(feature_columns, ensure_ascii=False)
        out.at[index, "source_file"] = str(config_path)
    return out


def parse_json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def normalize_json_text(value: str) -> str:
    parsed = parse_json_dict(value)
    if parsed:
        return json.dumps(parsed, sort_keys=True)
    return value


def registry_row(
    *,
    stream: str,
    stream_label: Any,
    model: Any,
    component_model: Any,
    model_role: str,
    source_row: pd.Series,
    profiles: dict[str, dict[str, Any]],
    workbook: Path,
    scorecard: pd.DataFrame,
    status: str,
    note: str,
) -> dict[str, Any]:
    profile = profiles.get(stream, {})
    model_text = str(component_model or model or "")
    score_basis = sorted(scorecard.loc[scorecard["stream"].astype(str).eq(stream), "score_basis"].dropna().astype(str).unique())
    origins = sorted(scorecard.loc[scorecard["stream"].astype(str).eq(stream), "origin"].dropna().astype(str).unique())
    return {
        "stream": stream,
        "stream_label": stream_label,
        "model": model,
        "component_model": component_model,
        "model_role": model_role,
        "algorithm": infer_algorithm(model_text),
        "target_column": profile.get("target_column", ""),
        "target_transform": infer_target_transform(model_text),
        "prediction_inverse_transform": "not documented in current evidence pack",
        "feature_set": source_row.get("feature_set", infer_feature_set(model_text)),
        "feature_columns": json.dumps(profile.get("feature_columns", []), ensure_ascii=False),
        "window_type": infer_window_type(model_text),
        "window_length": infer_window_length(model_text),
        "origin_grid": json.dumps(origins),
        "score_basis": json.dumps(score_basis),
        "covid_test_exclusion_rule": "Paper grid excludes 2020/2021 target periods where score_basis is schiff_paper_horizon_mean.",
        "hyperparameters_json": json.dumps(infer_hyperparameters(model_text), sort_keys=True),
        "random_state": "not available in current evidence pack",
        "source_script": "not available in current evidence pack",
        "source_script_hash": "not available",
        "source_workbook": str(workbook),
        "source_sheet": profile.get("source_sheet", ""),
        "source_dataset": source_row.get("source_dataset", ""),
        "source_file": source_row.get("source_file", ""),
        "component_weight": source_row.get("weight", np.nan),
        "reproducibility_status": status,
        "reproducibility_note": note,
    }


def component_status_note(row: pd.Series) -> str:
    weight = float(row.get("weight", 0) or 0)
    if math.isclose(weight, 1.0, rel_tol=0, abs_tol=1e-9):
        return "Single-component finalist: component_pred is identical to final_pred in component_predictions.parquet; fitted rebuild artifacts remain incomplete."
    return "Multi-component ensemble: component forecast rows are loaded from the Heavy RUC closure output and weighted-sum reconciliation is validated; fitted rebuild artifacts remain incomplete."


def build_component_predictions(tables: dict[str, pd.DataFrame], heavy_component_run: Path | None = None) -> pd.DataFrame:
    predictions = tables["scorecard_predictions"].copy()
    predictions = predictions[predictions["scenario"].astype(str).eq("Finalist")].copy()
    components = tables["ensemble_components"].copy()
    component_forecasts = load_heavy_component_forecasts(heavy_component_run, components) if heavy_component_run else pd.DataFrame()
    rows: list[pd.DataFrame] = []
    key_cols = [
        "stream",
        "stream_label",
        "model",
        "score_basis",
        "origin",
        "target_period",
        "horizon",
        "actual",
        "pred",
    ]
    for _, component in components.sort_values(["stream", "component_rank"]).iterrows():
        finalist_model = str(component["finalist_model"])
        stream = str(component["stream"])
        pred_rows = predictions[
            predictions["stream"].astype(str).eq(stream) & predictions["model"].astype(str).eq(finalist_model)
        ][key_cols].copy()
        if pred_rows.empty:
            continue
        weight = float(component.get("weight", 0) or 0)
        single_component = math.isclose(weight, 1.0, rel_tol=0, abs_tol=1e-9)
        pred_rows = pred_rows.rename(columns={"model": "finalist_model", "pred": "final_pred"})
        pred_rows["component_model"] = component.get("component_model")
        pred_rows["component_weight"] = weight
        pred_rows["component_pred"] = pred_rows["final_pred"] if single_component else np.nan
        pred_rows["component_source_file"] = "scorecard_predictions.parquet" if single_component else pd.NA
        if not single_component and not component_forecasts.empty:
            source = component_forecasts[
                component_forecasts["component_model"].astype(str).eq(str(component.get("component_model")))
            ].copy()
            pred_rows = pred_rows.merge(
                source[
                    [
                        "stream",
                        "component_model",
                        "origin",
                        "target_period",
                        "horizon",
                        "component_pred_loaded",
                        "component_source_file_loaded",
                    ]
                ],
                on=["stream", "component_model", "origin", "target_period", "horizon"],
                how="left",
            )
            pred_rows["component_pred"] = pred_rows["component_pred_loaded"].combine_first(pred_rows["component_pred"])
            pred_rows["component_source_file"] = pred_rows["component_source_file_loaded"].combine_first(
                pred_rows["component_source_file"]
            )
            pred_rows = pred_rows.drop(columns=["component_pred_loaded", "component_source_file_loaded"])
        pred_rows["component_error_pct"] = percentage_error(pred_rows["actual"], pred_rows["component_pred"])
        pred_rows["component_abs_error_pct"] = pred_rows["component_error_pct"].abs()
        pred_rows["weighted_component_pred"] = pred_rows["component_pred"] * weight
        has_loaded_component = pd.to_numeric(pred_rows["component_pred"], errors="coerce").notna().all()
        pred_rows["component_traceability_status"] = (
            "single_component_equals_final_prediction"
            if single_component
            else (
                "component_forecast_loaded_weighted_sum_verified"
                if has_loaded_component
                else "missing_component_forecast_trace"
            )
        )
        pred_rows["source"] = pred_rows["component_source_file"]
        pred_rows["source_basis"] = (
            "single-component identity"
            if single_component
            else (
                "component forecast loaded from Heavy RUC closure output"
                if has_loaded_component
                else "component weight known; component forecast not available"
            )
        )
        rows.append(pred_rows)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    ordered = [
        "stream",
        "stream_label",
        "finalist_model",
        "component_model",
        "score_basis",
        "origin",
        "target_period",
        "horizon",
        "actual",
        "component_pred",
        "component_error_pct",
        "component_abs_error_pct",
        "component_weight",
        "weighted_component_pred",
        "final_pred",
        "component_traceability_status",
        "source",
        "source_basis",
    ]
    return out.reindex(columns=ordered)


def load_heavy_component_forecasts(heavy_component_run: Path | None, components: pd.DataFrame) -> pd.DataFrame:
    if heavy_component_run is None:
        return pd.DataFrame()
    predictions_path = heavy_component_run / "all_quarterly_predictions.csv"
    weights_path = heavy_component_run / "ensemble_weights.csv"
    if not predictions_path.exists() or not weights_path.exists():
        return pd.DataFrame()
    heavy_components = components[
        components["stream"].astype(str).eq("HEAVY_RUC")
        & pd.to_numeric(components["weight"], errors="coerce").lt(1.0)
    ][["component_model"]].copy()
    if heavy_components.empty:
        return pd.DataFrame()
    predictions = pd.read_csv(predictions_path, low_memory=False)
    subset = predictions[predictions["model"].astype(str).isin(set(heavy_components["component_model"].astype(str)))].copy()
    if subset.empty:
        return pd.DataFrame()
    subset = subset.rename(columns={"model": "component_model", "pred": "component_pred_loaded"})
    subset["component_source_file_loaded"] = str(predictions_path)
    return subset[
        [
            "stream",
            "component_model",
            "origin",
            "target_period",
            "horizon",
            "component_pred_loaded",
            "component_source_file_loaded",
        ]
    ]


def build_coefficients_table(registry: pd.DataFrame) -> pd.DataFrame:
    linear = registry[registry["algorithm"].isin(["ElasticNet", "Ridge", "OLS", "Schiff workbook specification"])].copy()
    linear = linear.drop_duplicates(["stream", "component_model"])
    rows = []
    for _, row in linear.iterrows():
        rows.append(
            {
                "stream": row["stream"],
                "model": row["component_model"],
                "origin": pd.NA,
                "component_model": row["component_model"],
                "feature": pd.NA,
                "coefficient": np.nan,
                "intercept": np.nan,
                "standardised_coefficient": np.nan,
                "window_start": pd.NA,
                "window_end": pd.NA,
                "reproducibility_status": "incomplete",
                "notes": "Coefficient artifacts are not present in the current evidence pack or workbook-derived registry.",
                "artifact_search_status": "not_found",
                "artifact_search_basis": "Searched evidence pack, workbook input folder and Heavy RUC closure output for coefficient artifacts; none were found.",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "stream",
            "model",
            "origin",
            "component_model",
            "feature",
            "coefficient",
            "intercept",
            "standardised_coefficient",
            "window_start",
            "window_end",
            "reproducibility_status",
            "notes",
            "artifact_search_status",
            "artifact_search_basis",
        ],
    )


def build_feature_importance_table(registry: pd.DataFrame) -> pd.DataFrame:
    tree = registry[registry["algorithm"].isin(["GradientBoostingRegressor", "GBM/residual tree model"])].copy()
    tree = tree.drop_duplicates(["stream", "component_model"])
    rows = []
    for _, row in tree.iterrows():
        rows.append(
            {
                "stream": row["stream"],
                "model": row["component_model"],
                "origin_or_global": "not available",
                "feature": pd.NA,
                "importance_type": "not available",
                "importance_value": np.nan,
                "rank": np.nan,
                "reproducibility_status": "incomplete",
                "notes": "Feature-importance artifacts are not present in the current evidence pack.",
                "artifact_search_status": "not_found",
                "artifact_search_basis": "Searched evidence pack, workbook input folder and Heavy RUC closure output for GBM importance artifacts; none were found.",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "stream",
            "model",
            "origin_or_global",
            "feature",
            "importance_type",
            "importance_value",
            "rank",
            "reproducibility_status",
            "notes",
            "artifact_search_status",
            "artifact_search_basis",
        ],
    )


def build_scenario_sensitivities_table(registry: pd.DataFrame) -> pd.DataFrame:
    finalists = registry[registry["model_role"].eq("current_finalist")].copy()
    rows = []
    for _, row in finalists.iterrows():
        for variable in SENSITIVITY_VARIABLES:
            rows.append(
                {
                    "stream": row["stream"],
                    "model": row["model"],
                    "scenario_variable": variable,
                    "perturbation": "not computed",
                    "horizon": np.nan,
                    "base_prediction": np.nan,
                    "scenario_prediction": np.nan,
                    "delta": np.nan,
                    "delta_pct": np.nan,
                    "reproducibility_status": "incomplete",
                    "notes": "Scenario sensitivity requires executable model rebuild or fitted model object; neither is present in the current evidence pack.",
                    "artifact_search_status": "not_found",
                    "artifact_search_basis": "Searched evidence pack, workbook input folder and Heavy RUC closure output for precomputed scenario sensitivity artifacts; none were found.",
                }
            )
    return pd.DataFrame(rows)


def build_shap_summary_table(registry: pd.DataFrame) -> pd.DataFrame:
    gbm = registry[registry["algorithm"].isin(["GradientBoostingRegressor", "GBM/residual tree model"])].copy()
    gbm = gbm.drop_duplicates(["stream", "component_model"])
    rows = []
    for _, row in gbm.iterrows():
        rows.append(
            {
                "stream": row["stream"],
                "model": row["component_model"],
                "feature": pd.NA,
                "mean_abs_shap": np.nan,
                "mean_shap": np.nan,
                "rank": np.nan,
                "sample_size": np.nan,
                "reproducibility_status": "incomplete",
                "notes": "SHAP values require fitted GBM artifacts; current evidence pack does not include them.",
                "artifact_search_status": "not_found",
                "artifact_search_basis": "Searched evidence pack, workbook input folder and Heavy RUC closure output for SHAP artifacts; none were found.",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "stream",
            "model",
            "feature",
            "mean_abs_shap",
            "mean_shap",
            "rank",
            "sample_size",
            "reproducibility_status",
            "notes",
            "artifact_search_status",
            "artifact_search_basis",
        ],
    )


def reproducibility_artifact_search_report(
    *,
    data_root: Path,
    workbook: Path,
    heavy_component_run: Path,
    repo_root: Path,
) -> str:
    searched_roots = [
        data_root,
        workbook.parent,
        heavy_component_run,
        repo_root / "scripts",
    ]
    tokens = [
        "coef",
        "coefficient",
        "feature_import",
        "importance",
        "shap",
        "sensitivity",
        "sensitivities",
        "scenario_sensitivity",
        "scenario_sensitivities",
    ]
    generated_audit_outputs = {
        "model_coefficients.parquet",
        "feature_importance.parquet",
        "scenario_sensitivities.parquet",
        "shap_summary.parquet",
        "reproducibility_artifact_search.md",
        "reproducibility_report.md",
    }
    matches: list[Path] = []
    for root in searched_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.name in generated_audit_outputs:
                continue
            if path.is_file() and any(token in path.name.lower() for token in tokens):
                matches.append(path)

    known_traceability_files = [
        heavy_component_run / "all_quarterly_predictions.csv",
        heavy_component_run / "ensemble_weights.csv",
        heavy_component_run / "candidate_config_inventory.csv",
        heavy_component_run / "feature_inventory.csv",
    ]
    known_lines = []
    for path in known_traceability_files:
        status = "found" if path.exists() else "missing"
        known_lines.append(f"- `{path}`: {status}")

    if matches:
        match_lines = [f"- `{path}`" for path in sorted(matches)]
    else:
        match_lines = ["- No coefficient, feature-importance, SHAP or scenario-sensitivity artifact files were found in the searched roots."]

    return "\n".join(
        [
            "# Reproducibility Artifact Search",
            "",
            "This search documents why the coefficient, feature-importance, SHAP and scenario-sensitivity tables remain explicit incomplete states rather than fabricated explainability outputs.",
            "",
            "## Searched Roots",
            "",
            *[f"- `{root}`" for root in searched_roots],
            "",
            "## Search Tokens",
            "",
            "`" + "`, `".join(tokens) + "`",
            "",
            "## Heavy RUC Traceability Files",
            "",
            *known_lines,
            "",
            "## Explainability Artifact Matches",
            "",
            *match_lines,
            "",
            "## Conclusion",
            "",
            "Heavy RUC component forecasts, weights, candidate configuration and feature inventory are available and used for component traceability. Fitted model objects, origin-level coefficients, GBM feature importances, SHAP outputs and executable scenario sensitivity outputs were not found in the current evidence pack inputs, so the corresponding tables are marked `reproducibility_status = incomplete` with `artifact_search_status = not_found`.",
        ]
    )


def validate_reproducibility_tables(
    tables: dict[str, pd.DataFrame], component_predictions: pd.DataFrame, registry: pd.DataFrame
) -> dict[str, Any]:
    scorecard = tables["scorecard_predictions"].copy()
    model_summary = tables["scorecard_model_summary"].copy()
    finalist_scorecard = scorecard[scorecard["scenario"].astype(str).eq("Finalist")].copy()
    keys = ["stream", "score_basis", "origin", "target_period", "horizon", "model"]
    component_keys = ["stream", "score_basis", "origin", "target_period", "horizon", "finalist_model"]
    final_from_components = component_predictions[component_keys + ["final_pred"]].drop_duplicates(component_keys)
    merged = finalist_scorecard.merge(
        final_from_components,
        left_on=keys,
        right_on=component_keys,
        how="left",
        suffixes=("_evidence", "_audit"),
    )
    max_prediction_delta = (pd.to_numeric(merged["pred"], errors="coerce") - pd.to_numeric(merged["final_pred"], errors="coerce")).abs().max()
    mape_rows = []
    for (stream, score_basis), group in finalist_scorecard.groupby(["stream", "score_basis"], dropna=False):
        pooled = pd.to_numeric(group["abs_error_pct"], errors="coerce").mean()
        horizon_mean = pd.to_numeric(group.groupby("horizon")["abs_error_pct"].mean(), errors="coerce").mean()
        summary = model_summary[
            model_summary["stream"].astype(str).eq(str(stream))
            & model_summary["score_basis"].astype(str).eq(str(score_basis))
            & model_summary["scenario"].astype(str).eq("Finalist")
        ]
        summary_pooled = pd.to_numeric(summary.get("quarterly_pooled_mape", pd.Series(dtype=float)), errors="coerce").dropna()
        summary_horizon = pd.to_numeric(summary.get("horizon_mean_mape", pd.Series(dtype=float)), errors="coerce").dropna()
        mape_rows.append(
            {
                "stream": stream,
                "score_basis": score_basis,
                "rebuilt_pooled_mape": pooled,
                "evidence_pooled_mape": float(summary_pooled.iloc[0]) if not summary_pooled.empty else np.nan,
                "pooled_delta": abs(pooled - float(summary_pooled.iloc[0])) if not summary_pooled.empty else np.nan,
                "rebuilt_horizon_mean_mape": horizon_mean,
                "evidence_horizon_mean_mape": float(summary_horizon.iloc[0]) if not summary_horizon.empty else np.nan,
                "horizon_delta": abs(horizon_mean - float(summary_horizon.iloc[0])) if not summary_horizon.empty else np.nan,
            }
        )
    mape_frame = pd.DataFrame(mape_rows)
    heavy = component_predictions[component_predictions["stream"].astype(str).eq("HEAVY_RUC")].copy()
    heavy_weighted = heavy_weighted_sum_reconciliation(heavy)
    return {
        "prediction_row_count": int(len(component_predictions)),
        "model_registry_rows": int(len(registry)),
        "max_prediction_delta": float(max_prediction_delta) if pd.notna(max_prediction_delta) else np.nan,
        "mape_reconciliation": mape_frame,
        "heavy_weighted_sum_status": "verified" if heavy_weighted["verified"] else "incomplete_missing_component_predictions",
        "heavy_weighted_sum_max_delta": heavy_weighted["max_delta"],
        "heavy_weighted_sum_rows": heavy_weighted["grouped_rows"],
        "heavy_missing_component_rows": heavy_weighted["missing_component_rows"],
        "incomplete_registry_rows": int(registry["reproducibility_status"].astype(str).eq("incomplete").sum()),
    }


def heavy_weighted_sum_reconciliation(heavy: pd.DataFrame) -> dict[str, Any]:
    if heavy.empty:
        return {"verified": False, "max_delta": np.nan, "grouped_rows": 0, "missing_component_rows": 0}
    heavy = heavy.copy()
    heavy["component_pred_num"] = pd.to_numeric(heavy["component_pred"], errors="coerce")
    heavy["weighted_component_pred_num"] = pd.to_numeric(heavy["weighted_component_pred"], errors="coerce")
    missing_component_rows = int(heavy["component_pred_num"].isna().sum())
    keys = ["stream", "finalist_model", "score_basis", "origin", "target_period", "horizon"]
    grouped = (
        heavy.groupby(keys, as_index=False)
        .agg(
            weighted_sum=("weighted_component_pred_num", "sum"),
            component_count=("component_model", "nunique"),
            final_pred=("final_pred", "first"),
        )
        .copy()
    )
    delta = (pd.to_numeric(grouped["weighted_sum"], errors="coerce") - pd.to_numeric(grouped["final_pred"], errors="coerce")).abs()
    max_delta = float(delta.max()) if not delta.empty else np.nan
    verified = missing_component_rows == 0 and int(grouped["component_count"].ne(4).sum()) == 0 and max_delta <= 1e-5
    return {
        "verified": bool(verified),
        "max_delta": max_delta,
        "grouped_rows": int(len(grouped)),
        "missing_component_rows": missing_component_rows,
    }


def reproducibility_report(
    data_root: Path,
    workbook: Path,
    outputs: dict[str, pd.DataFrame],
    validation: dict[str, Any],
) -> str:
    mape = validation["mape_reconciliation"]
    mape_lines = [
        "| Stream | Score basis | Rebuilt pooled MAPE | Evidence pooled MAPE | Pooled delta | Rebuilt horizon mean MAPE | Evidence horizon mean MAPE | Horizon delta |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in mape.iterrows():
        mape_lines.append(
            "| {stream} | {score_basis} | {rebuilt_pooled_mape:.6f} | {evidence_pooled_mape:.6f} | {pooled_delta:.6g} | {rebuilt_horizon_mean_mape:.6f} | {evidence_horizon_mean_mape:.6f} | {horizon_delta:.6g} |".format(
                **row.to_dict()
            )
        )
    file_lines = ["| File | Rows | Columns |", "| --- | ---: | ---: |"]
    for filename, frame in outputs.items():
        file_lines.append(f"| data/{filename} | {len(frame)} | {len(frame.columns)} |")
    status = "INCOMPLETE"
    return "\n".join(
        [
            "# Finalist Reproducibility Audit Report",
            "",
            f"Status: **{status}**.",
            "",
            "This pack adds traceability tables for the current finalists, Schiff benchmarks and ensemble components without changing the dashboard design.",
            "",
            f"- Evidence pack: `{data_root}`",
            f"- Workbook: `{workbook}`",
            "- Workbook sheets used: `PED Inputs`, `Light RUC Inputs`, `Heavy RUC Inputs`",
            f"- Built at: `{datetime.now(timezone.utc).isoformat()}`",
            "",
            "## Added Tables",
            "",
            *file_lines,
            "",
            "## Reconciliation",
            "",
            f"- Component prediction rows: {validation['prediction_row_count']:,}",
            f"- Model registry rows: {validation['model_registry_rows']:,}",
            f"- Maximum final-prediction delta versus evidence pack: {validation['max_prediction_delta']:.12g}",
            f"- Heavy RUC weighted-sum status: `{validation['heavy_weighted_sum_status']}`",
            f"- Heavy RUC weighted-sum rows: {validation['heavy_weighted_sum_rows']:,}",
            f"- Heavy RUC weighted-sum max delta: {validation['heavy_weighted_sum_max_delta']:.12g}",
            f"- Heavy RUC missing component rows: {validation['heavy_missing_component_rows']:,}",
            f"- Registry rows marked incomplete: {validation['incomplete_registry_rows']:,}",
            "",
            *mape_lines,
            "",
            "## Current Gaps",
            "",
            "- Heavy RUC component forecast rows are loaded from the closure output and the weighted ensemble sum reconciles to the evidence-pack final predictions, but the fitted component objects are not yet rebuilt from workbook plus registry alone.",
            "- Coefficient artifacts for ElasticNet/Ridge/OLS/Schiff workbook formulas are not present as fitted origin-level tables.",
            "- GBM feature importance and SHAP artifacts are not present as fitted model outputs.",
            "- Scenario sensitivities require executable fitted-model rebuilds and are therefore explicitly marked incomplete.",
            "",
            "Do not claim full finalist reproducibility until every finalist has complete component traceability, fitted-model metadata and score reconciliation from rebuilt predictions.",
        ]
    )


def update_inventory_and_manifest(data_root: Path) -> None:
    data_dir = data_root / "data"
    rows = []
    for path in sorted(data_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        rows.append(
            {
                "file": path.name,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "size_bytes": int(path.stat().st_size),
            }
        )
    inventory = pd.DataFrame(rows)
    inventory.to_csv(data_root / "data_inventory.csv", index=False)
    manifest_path = data_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_counts"] = rows
    manifest.setdefault("important_semantics", {})["reproducibility_audit"] = (
        "Reproducibility tables document finalist/component traceability and explicitly mark incomplete rebuild gaps."
    )
    manifest["reproducibility_audit_created_at"] = datetime.now(timezone.utc).date().isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def infer_algorithm(model: str) -> str:
    upper = model.upper()
    if "GBR" in upper or "GBM" in upper:
        return "GradientBoostingRegressor"
    if "ELASTIC" in upper:
        return "ElasticNet"
    if "RIDGE" in upper:
        return "Ridge"
    if "OLS" in upper:
        return "OLS"
    if "SCHIFF_SPEC_FROM_WORKBOOK" in upper:
        return "Schiff workbook specification"
    if "SOLVER" in upper:
        return "Convex solver ensemble"
    return "not documented"


def infer_target_transform(model: str) -> str:
    upper = model.upper()
    if "LOG" in upper:
        return "log"
    return "not documented in current evidence pack"


def infer_feature_set(model: str) -> str:
    lower = model.lower()
    if "schiff" in lower:
        return "schiff"
    if "dynamic_no_leads" in lower:
        return "dynamic_no_leads"
    if "dynamic" in lower:
        return "dynamic"
    if "hpo" in lower:
        return "hpo_refine"
    return "not documented"


def infer_window_type(model: str) -> str:
    lower = model.lower()
    if "static" in lower:
        return "static"
    if re.search(r"w\d+", lower):
        return "rolling"
    if "dynamic" in lower:
        return "dynamic"
    return "not documented"


def infer_window_length(model: str) -> float:
    match = re.search(r"w(\d+)", model)
    return float(match.group(1)) if match else np.nan


def infer_hyperparameters(model: str) -> dict[str, Any]:
    patterns = {
        "alpha": r"alpha([0-9]+(?:_[0-9]+)?)",
        "l1_ratio": r"l1_ratio([0-9]+(?:_[0-9]+)?)",
        "learning_rate": r"learning_rate([0-9]+(?:_[0-9]+)?)",
        "max_depth": r"max_depth(\d+)",
        "n_estimators": r"n_estimators(\d+)",
        "window": r"w(\d+)",
    }
    params: dict[str, Any] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, model)
        if not match:
            continue
        raw = match.group(1)
        if name in {"max_depth", "n_estimators", "window"}:
            params[name] = int(raw)
        else:
            params[name] = numeric_token(raw)
    return params


def numeric_token(raw: str) -> float:
    if "_" not in raw:
        return float(raw)
    head, tail = raw.split("_", 1)
    return float(f"{head}.{tail}")


def percentage_error(actual: pd.Series, pred: pd.Series) -> pd.Series:
    actual_num = pd.to_numeric(actual, errors="coerce")
    pred_num = pd.to_numeric(pred, errors="coerce")
    return ((pred_num - actual_num) / actual_num.replace(0, np.nan)) * 100.0


if __name__ == "__main__":
    raise SystemExit(main())

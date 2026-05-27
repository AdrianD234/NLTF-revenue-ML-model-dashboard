from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = ROOT / "data" / "dashboard_evidence_pack"

REQUIRED_TABLE_COLUMNS = {
    "model_registry.parquet": [
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
        "reproducibility_status",
    ],
    "component_predictions.parquet": [
        "stream",
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
    ],
    "model_coefficients.parquet": [
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
    "feature_importance.parquet": [
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
    "scenario_sensitivities.parquet": [
        "stream",
        "model",
        "scenario_variable",
        "perturbation",
        "horizon",
        "base_prediction",
        "scenario_prediction",
        "delta",
        "delta_pct",
        "reproducibility_status",
        "notes",
        "artifact_search_status",
        "artifact_search_basis",
    ],
    "shap_summary.parquet": [
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
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate finalist reproducibility audit pack tables.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--require-complete", action="store_true")
    return parser.parse_args()


def validate(data_root: Path, require_complete: bool = False) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    data_dir = data_root / "data"
    tables = {filename: read_required(data_dir, filename, columns) for filename, columns in REQUIRED_TABLE_COLUMNS.items()}
    evidence = {
        "finalists": pd.read_parquet(data_dir / "finalists.parquet"),
        "schiff_benchmark": pd.read_parquet(data_dir / "schiff_benchmark.parquet"),
        "ensemble_components": pd.read_parquet(data_dir / "ensemble_components.parquet"),
        "scorecard_predictions": pd.read_parquet(data_dir / "scorecard_predictions.parquet"),
        "scorecard_model_summary": pd.read_parquet(data_dir / "scorecard_model_summary.parquet"),
    }

    findings: list[dict[str, Any]] = []

    def record(name: str, passed: bool, evidence_text: str) -> None:
        findings.append({"check": name, "status": "PASS" if passed else "FAIL", "evidence": evidence_text})

    registry = tables["model_registry.parquet"]
    component_predictions = tables["component_predictions.parquet"]
    finalist_models = set(evidence["finalists"]["model"].astype(str))
    schiff_models = set(evidence["schiff_benchmark"]["model"].astype(str))
    component_models = set(evidence["ensemble_components"]["component_model"].astype(str))
    record(
        "registry covers finalists, Schiff benchmarks and ensemble components",
        finalist_models.issubset(set(registry["model"].astype(str)))
        and schiff_models.issubset(set(registry["component_model"].astype(str)))
        and component_models.issubset(set(registry["component_model"].astype(str))),
        f"registry_rows={len(registry)}; finalists={len(finalist_models)}; schiff={len(schiff_models)}; components={len(component_models)}",
    )

    required_sheets = {"PED Inputs", "Light RUC Inputs", "Heavy RUC Inputs"}
    record(
        "registry documents required workbook sheets",
        required_sheets.issubset(set(registry["source_sheet"].dropna().astype(str))),
        "source_sheets=" + ", ".join(sorted(set(registry["source_sheet"].dropna().astype(str)))),
    )

    single_components = evidence["ensemble_components"][pd.to_numeric(evidence["ensemble_components"]["weight"], errors="coerce").round(10).eq(1.0)]
    single_rows = component_predictions[
        component_predictions["component_model"].astype(str).isin(set(single_components["component_model"].astype(str)))
    ].copy()
    single_delta = (
        pd.to_numeric(single_rows["component_pred"], errors="coerce") - pd.to_numeric(single_rows["final_pred"], errors="coerce")
    ).abs()
    record(
        "single-component finalists use component_pred equal to final_pred",
        not single_rows.empty and float(single_delta.max()) <= 1e-12,
        f"single_component_rows={len(single_rows)}; max_delta={float(single_delta.max()) if not single_delta.empty else 'missing'}",
    )

    prediction_match = compare_final_predictions(evidence["scorecard_predictions"], component_predictions)
    record(
        "component_predictions final_pred matches scorecard prediction rows",
        prediction_match["missing"] == 0 and prediction_match["max_delta"] <= 1e-12,
        f"matched_rows={prediction_match['matched']}; missing={prediction_match['missing']}; max_delta={prediction_match['max_delta']}",
    )

    mape = mape_reconciliation(evidence["scorecard_predictions"], evidence["scorecard_model_summary"])
    record(
        "recomputed MAPE reconciles to scorecard_model_summary",
        bool((mape["pooled_delta"] <= 1e-9).all() and (mape["horizon_delta"] <= 1e-9).all()),
        f"rows={len(mape)}; max_pooled_delta={mape['pooled_delta'].max()}; max_horizon_delta={mape['horizon_delta'].max()}",
    )

    heavy = component_predictions[component_predictions["stream"].astype(str).eq("HEAVY_RUC")].copy()
    heavy_components = set(heavy["component_model"].astype(str))
    expected_heavy_components = set(
        evidence["ensemble_components"].loc[evidence["ensemble_components"]["stream"].astype(str).eq("HEAVY_RUC"), "component_model"].astype(str)
    )
    heavy_weighted = weighted_sum_reconciliation(heavy)
    record(
        "Heavy RUC component forecasts verify the weighted ensemble sum",
        expected_heavy_components.issubset(heavy_components)
        and heavy_weighted["missing_component_rows"] == 0
        and heavy_weighted["bad_component_count_rows"] == 0
        and heavy_weighted["max_delta"] <= 1e-5,
        "heavy_components={components}; grouped_rows={rows}; max_delta={max_delta}; missing_component_rows={missing}; bad_component_count_rows={bad}".format(
            components=len(heavy_components),
            rows=heavy_weighted["grouped_rows"],
            max_delta=heavy_weighted["max_delta"],
            missing=heavy_weighted["missing_component_rows"],
            bad=heavy_weighted["bad_component_count_rows"],
        ),
    )

    incomplete_count = int(registry["reproducibility_status"].astype(str).eq("incomplete").sum())
    record(
        "full reproducibility is not falsely claimed",
        incomplete_count > 0,
        f"incomplete_registry_rows={incomplete_count}",
    )
    if require_complete:
        record(
            "require-complete mode has no incomplete registry rows",
            incomplete_count == 0,
            f"incomplete_registry_rows={incomplete_count}",
        )

    explained = incomplete_explainability_rows_are_documented(tables)
    record(
        "incomplete explainability rows include artifact-search evidence",
        explained["missing_notes"] == 0 and explained["missing_search_status"] == 0 and explained["missing_search_basis"] == 0,
        "missing_notes={missing_notes}; missing_search_status={missing_search_status}; missing_search_basis={missing_search_basis}".format(
            **explained
        ),
    )

    feature_importance = tables["feature_importance.parquet"]
    feature_duplicate_count = duplicate_count(
        feature_importance,
        ["stream", "model", "origin_or_global", "feature", "importance_type"],
    )
    record(
        "feature_importance placeholder rows are deduplicated by model",
        feature_duplicate_count == 0,
        f"rows={len(feature_importance)}; duplicate_key_rows={feature_duplicate_count}",
    )

    shap_summary = tables["shap_summary.parquet"]
    shap_duplicate_count = duplicate_count(shap_summary, ["stream", "model", "feature"])
    record(
        "shap_summary placeholder rows are deduplicated by model",
        shap_duplicate_count == 0,
        f"rows={len(shap_summary)}; duplicate_key_rows={shap_duplicate_count}",
    )

    artifact_report = data_root / "docs" / "reproducibility_artifact_search.md"
    report_text = artifact_report.read_text(encoding="utf-8") if artifact_report.exists() else ""
    record(
        "artifact search report documents missing fitted explainability outputs",
        artifact_report.exists()
        and "Fitted model objects" in report_text
        and "artifact_search_status = not_found" in report_text
        and "all_quarterly_predictions.csv" in report_text,
        f"path={artifact_report}; exists={artifact_report.exists()}",
    )

    return findings, {**tables, "mape_reconciliation": mape}


def read_required(data_dir: Path, filename: str, required_columns: list[str]) -> pd.DataFrame:
    path = data_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing reproducibility table: {path}")
    frame = pd.read_parquet(path)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise AssertionError(f"{filename} missing required columns: {missing}")
    return frame


def incomplete_explainability_rows_are_documented(tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    missing_notes = 0
    missing_search_status = 0
    missing_search_basis = 0
    for filename in [
        "model_coefficients.parquet",
        "feature_importance.parquet",
        "scenario_sensitivities.parquet",
        "shap_summary.parquet",
    ]:
        frame = tables[filename]
        incomplete = frame[frame["reproducibility_status"].astype(str).eq("incomplete")].copy()
        if incomplete.empty:
            continue
        missing_notes += int(incomplete["notes"].fillna("").astype(str).str.strip().eq("").sum())
        missing_search_status += int(incomplete["artifact_search_status"].fillna("").astype(str).str.strip().eq("").sum())
        missing_search_basis += int(incomplete["artifact_search_basis"].fillna("").astype(str).str.strip().eq("").sum())
    return {
        "missing_notes": missing_notes,
        "missing_search_status": missing_search_status,
        "missing_search_basis": missing_search_basis,
    }


def duplicate_count(frame: pd.DataFrame, columns: list[str]) -> int:
    if frame.empty:
        return 0
    return int(frame.duplicated(columns, keep=False).sum())


def compare_final_predictions(scorecard: pd.DataFrame, component_predictions: pd.DataFrame) -> dict[str, Any]:
    scorecard = scorecard[scorecard["scenario"].astype(str).eq("Finalist")].copy()
    keys = ["stream", "score_basis", "origin", "target_period", "horizon", "model"]
    component_keys = ["stream", "score_basis", "origin", "target_period", "horizon", "finalist_model"]
    audit = component_predictions[component_keys + ["final_pred"]].drop_duplicates(component_keys)
    merged = scorecard.merge(
        audit,
        left_on=keys,
        right_on=component_keys,
        how="left",
    )
    delta = (pd.to_numeric(merged["pred"], errors="coerce") - pd.to_numeric(merged["final_pred"], errors="coerce")).abs()
    return {
        "matched": int(delta.notna().sum()),
        "missing": int(delta.isna().sum()),
        "max_delta": float(delta.max()) if not delta.dropna().empty else np.nan,
    }


def mape_reconciliation(scorecard: pd.DataFrame, model_summary: pd.DataFrame) -> pd.DataFrame:
    finalist = scorecard[scorecard["scenario"].astype(str).eq("Finalist")].copy()
    rows = []
    for (stream, score_basis), group in finalist.groupby(["stream", "score_basis"], dropna=False):
        pooled = pd.to_numeric(group["abs_error_pct"], errors="coerce").mean()
        horizon = pd.to_numeric(group.groupby("horizon")["abs_error_pct"].mean(), errors="coerce").mean()
        summary = model_summary[
            model_summary["stream"].astype(str).eq(str(stream))
            & model_summary["score_basis"].astype(str).eq(str(score_basis))
            & model_summary["scenario"].astype(str).eq("Finalist")
        ]
        evidence_pooled = pd.to_numeric(summary["quarterly_pooled_mape"], errors="coerce").iloc[0]
        evidence_horizon = pd.to_numeric(summary["horizon_mean_mape"], errors="coerce").iloc[0]
        rows.append(
            {
                "stream": stream,
                "score_basis": score_basis,
                "rebuilt_pooled_mape": pooled,
                "evidence_pooled_mape": evidence_pooled,
                "pooled_delta": abs(pooled - evidence_pooled),
                "rebuilt_horizon_mean_mape": horizon,
                "evidence_horizon_mean_mape": evidence_horizon,
                "horizon_delta": abs(horizon - evidence_horizon),
            }
        )
    return pd.DataFrame(rows)


def weighted_sum_reconciliation(heavy: pd.DataFrame) -> dict[str, Any]:
    if heavy.empty:
        return {
            "grouped_rows": 0,
            "max_delta": np.inf,
            "missing_component_rows": 0,
            "bad_component_count_rows": 0,
        }
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
    return {
        "grouped_rows": int(len(grouped)),
        "max_delta": float(delta.max()) if not delta.empty else np.inf,
        "missing_component_rows": missing_component_rows,
        "bad_component_count_rows": int(grouped["component_count"].ne(4).sum()),
    }


def write_reports(findings: list[dict[str, Any]], tables: dict[str, pd.DataFrame], repo_root: Path) -> None:
    artifacts = repo_root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    status = "passed" if all(item["status"] == "PASS" for item in findings) else "failed"
    payload = {"status": status.upper(), "findings": findings}
    (artifacts / "reproducibility_validation_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Reproducibility Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for item in findings:
        lines.append(f"| {item['check']} | {item['status']} | {item['evidence']} |")
    if "mape_reconciliation" in tables:
        lines.extend(["", "## MAPE Reconciliation", ""])
        lines.extend(markdown_table(tables["mape_reconciliation"]))
    (artifacts / "reproducibility_validation_report.md").write_text("\n".join(lines), encoding="utf-8")


def markdown_table(frame: pd.DataFrame) -> list[str]:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.12g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def main() -> int:
    args = parse_args()
    data_root = Path(args.data_root).expanduser().resolve()
    repo_root = Path(args.repo_root).expanduser().resolve()
    findings, tables = validate(data_root, require_complete=args.require_complete)
    write_reports(findings, tables, repo_root)
    passed = all(item["status"] == "PASS" for item in findings)
    print((repo_root / "artifacts" / "reproducibility_validation_report.md").read_text(encoding="utf-8"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

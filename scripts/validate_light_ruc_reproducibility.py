from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.evidence_pack import load_evidence_pack  # noqa: E402
from model_dashboard.light_ruc_reproducibility import (  # noqa: E402
    HEAVY_RUC_REPRO_MODEL,
    HEAVY_RUC_REPRO_ROOT,
    LIGHT_RUC_REPRO_DESCRIPTION,
    LIGHT_RUC_REPRO_MODEL,
    LIGHT_RUC_REPRO_ROOT,
    PED_INNER_HPO_AUDIT_STATUS,
    PED_INNER_HPO_REPRO_ROOT,
    PED_REPRO_DESCRIPTION,
    PED_REPRO_MODEL,
    PED_REPRO_ROOT,
    REQUIRED_PED_INNER_HPO_AUDIT_FILES,
    REQUIRED_HEAVY_RUC_REPRO_FILES,
    REQUIRED_LIGHT_RUC_REPRO_FILES,
    REQUIRED_PED_REPRO_FILES,
    light_ruc_coefficients_view,
    light_ruc_component_trace_view,
    light_ruc_feature_importance_view,
    light_ruc_registry_view,
    light_ruc_replay_summary,
    light_ruc_sensitivity_view,
    light_ruc_training_window_view,
    load_ped_inner_hpo_audit_pack,
    load_reproducibility_pack,
    load_light_ruc_reproducibility_pack,
    ped_inner_hpo_audit_summary,
    ped_inner_hpo_gap_register_view,
    ped_inner_hpo_nested_trace_view,
    ped_inner_hpo_weight_detail_view,
    ped_inner_hpo_weight_source_view,
    reproducibility_coefficients_view,
    reproducibility_component_trace_view,
    reproducibility_ensemble_equation,
    reproducibility_ensemble_weight_view,
    reproducibility_feature_importance_view,
    reproducibility_registry_view,
    reproducibility_replay_summary,
    reproducibility_scorecard_view,
    reproducibility_sensitivity_view,
    reproducibility_stress_view,
    reproducibility_training_window_view,
)


EXPECTED_MAIN_FINALISTS = {
    # vNext finalists promoted 2026-06 (pack v7): pinned main-pack KPI snapshot.
    "PED VKT per capita": {"quarterly_mape": 3.131663200284857, "annual_mape": 1.9468458329074037},
    "Light RUC volume": {"quarterly_mape": 5.363206773795227, "annual_mape": 1.2737736398959618},
    "Heavy RUC volume": {"quarterly_mape": 2.2887157985529626, "annual_mape": 1.6827207898744102},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate auxiliary Light RUC reproducibility audit pack.")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repro-root", default=str(LIGHT_RUC_REPRO_ROOT))
    parser.add_argument("--heavy-repro-root", default=str(HEAVY_RUC_REPRO_ROOT))
    parser.add_argument("--ped-repro-root", default=str(PED_REPRO_ROOT))
    parser.add_argument("--ped-inner-hpo-root", default=str(PED_INNER_HPO_REPRO_ROOT))
    return parser.parse_args()


def validate(
    data_root: str | Path,
    repro_root: str | Path,
    heavy_repro_root: str | Path | None = None,
    ped_repro_root: str | Path | None = None,
    ped_inner_hpo_root: str | Path | None = None,
) -> list[dict[str, str]]:
    pack = load_light_ruc_reproducibility_pack(repro_root)
    heavy_pack = load_reproducibility_pack("Heavy RUC volume", heavy_repro_root or HEAVY_RUC_REPRO_ROOT)
    ped_pack = load_reproducibility_pack("PED VKT per capita", ped_repro_root or PED_REPRO_ROOT)
    ped_inner_hpo_pack = load_ped_inner_hpo_audit_pack(ped_inner_hpo_root or PED_INNER_HPO_REPRO_ROOT)
    findings: list[dict[str, str]] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        findings.append({"check": name, "status": "PASS" if passed else "FAIL", "evidence": evidence})

    root = Path(repro_root)
    record(
        "Required auxiliary audit files exist",
        not pack.missing_files,
        "missing=" + ", ".join(pack.missing_files) if pack.missing_files else f"files={len(REQUIRED_LIGHT_RUC_REPRO_FILES)}",
    )
    disallowed = sorted(path.name for path in root.glob("*") if path.suffix.lower() in {".csv", ".xlsx", ".xls"})
    record(
        "Auxiliary audit copy excludes CSV/XLSX mirrors",
        not disallowed,
        "disallowed=" + ", ".join(disallowed) if disallowed else "No CSV/XLSX mirrors found in auxiliary pack.",
    )

    registry = pack.table("model_registry")
    record(
        "Model registry exists and identifies Light RUC finalist",
        not registry.empty and LIGHT_RUC_REPRO_MODEL in set(registry.get("finalist_model", pd.Series(dtype=str)).astype(str)),
        f"rows={len(registry)}; models={sorted(set(registry.get('finalist_model', pd.Series(dtype=str)).astype(str)))}",
    )
    summary = light_ruc_replay_summary(pack) if pack.available else {}
    record(
        "Exact prediction replay status is documented",
        summary.get("status") == "Exact prediction replay" and summary.get("description") == LIGHT_RUC_REPRO_DESCRIPTION,
        str(summary),
    )
    record(
        "Workbook and source sheet are documented",
        summary.get("workbook") == "Master Copy revenue modelling workbook.xlsx"
        and summary.get("source_sheet") == "Light RUC Inputs",
        f"workbook={summary.get('workbook')}; sheet={summary.get('source_sheet')}",
    )

    if not registry.empty:
        registry_text = registry.fillna("").astype(str).agg(" ".join, axis=1).str.cat(sep=" ")
        record(
            "Recipe and GBM hyperparameters match audit facts",
            "GradientBoostingRegressor residual correction" in registry_text
            and "n_estimators" in registry_text
            and "150" in registry_text
            and "max_depth" in registry_text
            and "learning_rate" in registry_text
            and "0.05" in registry_text
            and "subsample" in registry_text
            and "0.85" in registry_text
            and "random_state" in registry_text
            and "42" in registry_text
            and "36" in registry_text
            and "final_pred = exp(final_log_pred)" in registry_text,
            "Registry recipe, window and hyperparameter fields inspected.",
        )
    else:
        record("Recipe and GBM hyperparameters match audit facts", False, "model_registry.parquet is empty or missing.")

    prediction_comparison = pack.table("evidence_prediction_comparison")
    if not prediction_comparison.empty and "abs_pred_delta" in prediction_comparison.columns:
        max_delta = pd.to_numeric(prediction_comparison["abs_pred_delta"], errors="coerce").max()
    else:
        max_delta = pd.NA
    record(
        "Evidence prediction replay delta is below tolerance",
        pd.notna(max_delta) and float(max_delta) <= 1e-5,
        f"max_abs_pred_delta={max_delta}",
    )

    rebuilt = pack.table("rebuilt_predictions")
    if {"base_log_pred", "residual_log_pred", "pred"}.issubset(rebuilt.columns):
        rebuilt_delta = (
            np.exp(pd.to_numeric(rebuilt["base_log_pred"], errors="coerce") + pd.to_numeric(rebuilt["residual_log_pred"], errors="coerce"))
            - pd.to_numeric(rebuilt["pred"], errors="coerce")
        ).abs()
        rebuilt_max_delta = rebuilt_delta.max()
    else:
        rebuilt_max_delta = pd.NA
    record(
        "Light RUC rebuilt predictions satisfy exp(base log prediction + residual log prediction) equals final prediction",
        pd.notna(rebuilt_max_delta) and float(rebuilt_max_delta) <= 1e-5,
        f"max_abs_delta={rebuilt_max_delta}",
    )

    components = pack.table("component_predictions")
    component_max_delta = pd.NA
    if {"component_model", "component_log_value", "final_pred"}.issubset(components.columns):
        keys = ["score_basis", "grid", "origin", "target_period", "horizon"]
        if set(keys).issubset(components.columns):
            pivot = components.pivot_table(index=keys, columns="component_model", values="component_log_value", aggfunc="first")
            final = components.groupby(keys, dropna=False)["final_pred"].first()
            if {"base_schiff_ols", "residual_gbr"}.issubset(pivot.columns):
                rebuilt_from_components = np.exp(
                    pd.to_numeric(pivot["base_schiff_ols"], errors="coerce")
                    + pd.to_numeric(pivot["residual_gbr"], errors="coerce")
                )
                component_max_delta = (rebuilt_from_components - pd.to_numeric(final, errors="coerce")).abs().max()
    record(
        "Light RUC component trace satisfies exp(base component log + residual component log) equals final prediction",
        pd.notna(component_max_delta) and float(component_max_delta) <= 1e-5,
        f"max_abs_delta={component_max_delta}",
    )

    metrics = pack.table("evidence_metric_comparison")
    record(
        "Metric comparison includes evidence pack and parent run matches",
        not metrics.empty
        and {"dashboard_evidence_pack", "parent_run_light_ruc_schiff_spec_challenger"}.issubset(
            set(metrics.get("reference_source", pd.Series(dtype=str)).astype(str))
        )
        and pd.to_numeric(metrics.get("max_abs_pred_delta", pd.Series(dtype=float)), errors="coerce").max() <= 1e-5,
        f"rows={len(metrics)}",
    )

    feature_importance = pack.table("feature_importance_global")
    sensitivities = pack.table("scenario_sensitivities")
    record(
        "Feature importance rows exist",
        not feature_importance.empty,
        f"rows={len(feature_importance)}",
    )
    record(
        "Scenario sensitivity rows exist",
        not sensitivities.empty,
        f"rows={len(sensitivities)}",
    )
    if not sensitivities.empty:
        scenario_text = sensitivities["scenario_variable"].dropna().astype(str).str.cat(sep=" | ")
        record(
            "Scenario sensitivities include GDP, diesel and RUC price perturbations",
            "GDP" in scenario_text and "diesel" in scenario_text.lower() and "ruc price" in scenario_text.lower(),
            scenario_text[:500],
        )
    else:
        record("Scenario sensitivities include GDP, diesel and RUC price perturbations", False, "scenario_sensitivities is empty.")

    scorecard = pack.table("scorecard_summary")
    expected_metrics = {
        ("current_grid_operational_pooled", "quarterly_mape"): 8.27297248356,
        ("current_grid_operational_pooled", "annual_mape"): 6.774906,
        ("schiff_paper_horizon_mean", "horizon_mean_mape"): 5.3632067738,
        ("schiff_paper_horizon_mean", "quarterly_mape"): 4.79490289762,
        ("schiff_paper_horizon_mean", "annual_mape"): 1.2737736399,
    }
    metric_ok = not scorecard.empty
    metric_evidence: list[str] = []
    if metric_ok:
        indexed = scorecard.set_index("score_basis")
        for (basis, column), expected in expected_metrics.items():
            actual = pd.to_numeric(indexed.loc[basis, column], errors="coerce")
            metric_ok = metric_ok and abs(float(actual) - expected) <= 0.001
            metric_evidence.append(f"{basis}.{column}={float(actual):.6f}")
    record(
        "Replay scorecard metrics match audit facts",
        metric_ok,
        "; ".join(metric_evidence) if metric_evidence else "scorecard_summary is missing.",
    )

    _validate_heavy_pack(heavy_pack, record)
    _validate_ped_pack(ped_pack, record)
    _validate_ped_inner_hpo_pack(ped_inner_hpo_pack, record)

    dashboard = load_evidence_pack(data_root, ROOT)
    recommended = dashboard.data["recommended"].set_index("stream_label")
    main_ok = True
    main_evidence: list[str] = []
    for stream, metrics_expected in EXPECTED_MAIN_FINALISTS.items():
        for column, expected in metrics_expected.items():
            actual = float(recommended.loc[stream, column])
            main_ok = main_ok and abs(actual - expected) <= 1e-9
            main_evidence.append(f"{stream}.{column}={actual:.12f}")
    record(
        "Main dashboard finalist KPIs remain unchanged",
        main_ok,
        "; ".join(main_evidence),
    )

    before_hashes = _chart_source_hashes()
    _ = light_ruc_registry_view(pack)
    _ = light_ruc_component_trace_view(pack)
    _ = light_ruc_feature_importance_view(pack)
    _ = light_ruc_sensitivity_view(pack)
    _ = light_ruc_coefficients_view(pack)
    _ = light_ruc_training_window_view(pack)
    _ = reproducibility_registry_view(heavy_pack)
    _ = reproducibility_component_trace_view(heavy_pack)
    _ = reproducibility_feature_importance_view(heavy_pack)
    _ = reproducibility_sensitivity_view(heavy_pack)
    _ = reproducibility_coefficients_view(heavy_pack)
    _ = reproducibility_training_window_view(heavy_pack)
    _ = reproducibility_ensemble_weight_view(heavy_pack)
    _ = reproducibility_ensemble_equation(heavy_pack)
    _ = reproducibility_registry_view(ped_pack)
    _ = reproducibility_component_trace_view(ped_pack)
    _ = reproducibility_feature_importance_view(ped_pack)
    _ = reproducibility_sensitivity_view(ped_pack)
    _ = reproducibility_coefficients_view(ped_pack)
    _ = reproducibility_training_window_view(ped_pack)
    _ = reproducibility_ensemble_weight_view(ped_pack)
    _ = reproducibility_ensemble_equation(ped_pack)
    _ = reproducibility_scorecard_view(ped_pack)
    _ = reproducibility_stress_view(ped_pack)
    _ = ped_inner_hpo_weight_source_view(ped_inner_hpo_pack)
    _ = ped_inner_hpo_weight_detail_view(ped_inner_hpo_pack)
    _ = ped_inner_hpo_nested_trace_view(ped_inner_hpo_pack)
    _ = ped_inner_hpo_gap_register_view(ped_inner_hpo_pack)
    after_hashes = _chart_source_hashes()
    record(
        "Auxiliary reproducibility views do not alter main chart-source tables",
        bool(before_hashes) and before_hashes == after_hashes,
        f"chart_source_tables={len(before_hashes)}; changed={_changed_hash_names(before_hashes, after_hashes)}",
    )
    auxiliary_refs = _chart_source_auxiliary_references()
    record(
        "Main chart-source tables do not reference auxiliary reproducibility pack files",
        not auxiliary_refs,
        "references=" + ", ".join(auxiliary_refs) if auxiliary_refs else "No auxiliary reproducibility paths found in chart sources.",
    )

    return findings


def _validate_ped_inner_hpo_pack(ped_inner_hpo_pack: object, record: object) -> None:
    root = Path(ped_inner_hpo_pack.root)
    record(
        "PED inner HPO audit required files exist",
        not ped_inner_hpo_pack.missing_files,
        "missing=" + ", ".join(ped_inner_hpo_pack.missing_files)
        if ped_inner_hpo_pack.missing_files
        else f"files={len(REQUIRED_PED_INNER_HPO_AUDIT_FILES)}",
    )
    disallowed = sorted(path.name for path in root.glob("*") if path.suffix.lower() in {".csv", ".xlsx", ".xls"})
    record(
        "PED inner HPO audit copy excludes CSV/XLSX mirrors",
        not disallowed,
        "disallowed=" + ", ".join(disallowed) if disallowed else "No CSV/XLSX mirrors found in PED inner audit pack.",
    )
    registry = ped_inner_hpo_pack.table("model_registry")
    record(
        "PED inner HPO model registry exists",
        root.joinpath("model_registry.parquet").exists() and not registry.empty,
        f"path={root / 'model_registry.parquet'}; rows={len(registry)}",
    )
    summary = ped_inner_hpo_audit_summary(ped_inner_hpo_pack) if ped_inner_hpo_pack.available else {}
    record(
        "PED outer component replay remains exact in inner audit pack",
        summary.get("outer_status") == "Exact component-prediction replay"
        and pd.notna(summary.get("outer_max_abs_delta"))
        and float(summary["outer_max_abs_delta"]) <= 1e-8,
        str(summary),
    )
    prediction_comparison = ped_inner_hpo_pack.table("evidence_prediction_comparison")
    pred_delta = pd.to_numeric(
        prediction_comparison.get("abs_delta_rebuilt_vs_evidence", pd.Series(dtype=float)),
        errors="coerce",
    ).max()
    record(
        "PED inner audit evidence prediction comparison max delta is below 1e-8",
        pd.notna(pred_delta) and float(pred_delta) <= 1e-8,
        f"max_abs_pred_delta={pred_delta}",
    )
    nested_delta = summary.get("inner_max_abs_delta", pd.NA)
    record(
        "PED inner HPO audit is labelled partial when nested replay delta is non-zero",
        summary.get("inner_status") == PED_INNER_HPO_AUDIT_STATUS
        and pd.notna(nested_delta)
        and float(nested_delta) > 1e-5,
        str(summary),
    )
    source_view = ped_inner_hpo_weight_source_view(ped_inner_hpo_pack)
    grouped_ok = False
    if not source_view.empty and {"Source role", "Per-source weight sum"}.issubset(source_view.columns):
        source_sums = source_view.set_index("Source role")["Per-source weight sum"]
        roles = set(source_view["Source role"].astype(str))
        if {"HPO refinement source", "Arbitration lineage/context"}.issubset(roles):
            grouped_ok = (
                abs(float(source_sums.loc["HPO refinement source"]) - 1.0) <= 1e-8
                and abs(float(source_sums.loc["Arbitration lineage/context"]) - 0.4292679798198642) <= 1e-8
            )
    record(
        "PED inner HPO weights are grouped by source_file before summing",
        grouped_ok,
        source_view.to_dict(orient="records") if not source_view.empty else "missing grouped weight source table",
    )
    gaps = ped_inner_hpo_gap_register_view(ped_inner_hpo_pack)
    gap_text = gaps.fillna("").astype(str).agg(" ".join, axis=1).str.cat(sep=" | ") if not gaps.empty else ""
    record(
        "PED inner HPO gap register includes refit and mismatch caveats",
        "feature_level_refit_not_attempted" in gap_text and "inner_weighted_replay_mismatch" in gap_text,
        gap_text,
    )
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    record(
        "PED UI does not label partial inner HPO audit exact",
        PED_INNER_HPO_AUDIT_STATUS in app_text and "Inner HPO/static-solver audit: exact" not in app_text,
        "Inner partial wording inspected in app.py.",
    )


def _validate_ped_pack(ped_pack: object, record: object) -> None:
    root = Path(ped_pack.root)
    record(
        "PED required auxiliary audit files exist",
        not ped_pack.missing_files,
        "missing=" + ", ".join(ped_pack.missing_files) if ped_pack.missing_files else f"files={len(REQUIRED_PED_REPRO_FILES)}",
    )
    disallowed = sorted(path.name for path in root.glob("*") if path.suffix.lower() in {".csv", ".xlsx", ".xls"})
    record(
        "PED auxiliary audit copy excludes CSV/XLSX mirrors",
        not disallowed,
        "disallowed=" + ", ".join(disallowed) if disallowed else "No CSV/XLSX mirrors found in PED auxiliary pack.",
    )
    registry = ped_pack.table("model_registry")
    record(
        "PED model registry exists and identifies the finalist",
        root.joinpath("model_registry.parquet").exists()
        and not registry.empty
        and PED_REPRO_MODEL in set(registry.get("finalist_model", pd.Series(dtype=str)).astype(str)),
        f"path={root / 'model_registry.parquet'}; rows={len(registry)}",
    )
    summary = reproducibility_replay_summary(ped_pack) if ped_pack.available else {}
    record(
        "PED exact component-prediction replay status is documented",
        summary.get("status") in {"Exact component-prediction replay", "Exact weighted-ensemble replay"}
        and summary.get("model") == PED_REPRO_MODEL
        and summary.get("source_sheet") == "PED Inputs"
        and "replay" in str(summary.get("description", "")).lower(),
        str(summary),
    )
    prediction_comparison = ped_pack.table("evidence_prediction_comparison")
    delta_column = "pred_delta_vs_evidence" if "pred_delta_vs_evidence" in prediction_comparison.columns else "max_abs_pred_delta"
    max_delta = pd.to_numeric(
        prediction_comparison.get(delta_column, pd.Series(dtype=float)),
        errors="coerce",
    ).abs().max()
    record(
        "PED evidence prediction replay delta is below 1e-8",
        pd.notna(max_delta) and float(max_delta) <= 1e-8,
        f"max_abs_pred_delta={max_delta}",
    )
    weights = pd.to_numeric(ped_pack.table("component_predictions").get("component_weight", pd.Series(dtype=float)), errors="coerce")
    record(
        "PED component weights are positive and sum to one",
        not weights.empty and (weights.dropna() > 0).all() and abs(float(weights.dropna().drop_duplicates().sum()) - 1.0) <= 1e-6,
        f"unique_weights={sorted(weights.dropna().drop_duplicates().round(6).tolist()) if not weights.dropna().empty else 'missing'}",
    )
    component_delta = _weighted_component_delta(ped_pack.table("component_predictions"))
    record(
        "PED weighted component sum equals final prediction",
        pd.notna(component_delta) and float(component_delta) <= 1e-8,
        f"max_abs_delta={component_delta}",
    )
    scorecard = ped_pack.table("scorecard_summary")
    scorecard = scorecard.copy()
    metric_aliases = {
        "pooled_mape": "quarterly_pooled_mape",
        "bias_pct": "quarterly_bias_pct",
    }
    for canonical, alias in metric_aliases.items():
        if canonical not in scorecard.columns and alias in scorecard.columns:
            scorecard[canonical] = scorecard[alias]
    expected_metrics = {
        ("current_grid_operational_pooled", "pooled_mape"): 2.664135,
        ("current_grid_operational_pooled", "horizon_mean_mape"): 2.733544,
        ("current_grid_operational_pooled", "bias_pct"): 0.798828,
        ("schiff_paper_horizon_mean", "pooled_mape"): 2.626833,
        ("schiff_paper_horizon_mean", "horizon_mean_mape"): 3.131663,
        ("schiff_paper_horizon_mean", "bias_pct"): 1.607586,
    }
    metric_ok = not scorecard.empty
    metric_evidence: list[str] = []
    if metric_ok:
        indexed = scorecard.set_index("score_basis")
        for (basis, column), expected in expected_metrics.items():
            actual = float(pd.to_numeric(indexed.loc[basis, column], errors="coerce"))
            metric_ok = metric_ok and abs(actual - expected) <= 0.001
            metric_evidence.append(f"{basis}.{column}={actual:.6f}")
    annual = ped_pack.table("annual_predictions")
    annual_text = f"annual_rows={len(annual)}"
    record(
        "PED scorecard metrics match audit facts",
        metric_ok,
        "; ".join(metric_evidence) + f"; {annual_text}" if metric_evidence else f"scorecard missing; {annual_text}",
    )
    feature_importance = ped_pack.table("feature_importance_global")
    sensitivities = ped_pack.table("scenario_sensitivities")
    record("PED feature importance rows exist", not feature_importance.empty, f"rows={len(feature_importance)}")
    record("PED scenario sensitivity rows exist", not sensitivities.empty, f"rows={len(sensitivities)}")
    equation = reproducibility_ensemble_equation(ped_pack)
    record(
        "PED ensemble equation exposes both vNext component weights",
        "0.584392*C1" in equation and "0.415608*C2" in equation,
        equation,
    )
    text = "\n".join(
        [
            (ROOT / "app.py").read_text(encoding="utf-8"),
            (ROOT / "model_dashboard" / "light_ruc_reproducibility.py").read_text(encoding="utf-8"),
        ]
    ).lower()
    forbidden = ["full workbook refit reproducibility", "first-principles refit reproducibility"]
    record(
        "PED UI does not claim full workbook refit reproducibility",
        not any(phrase in text for phrase in forbidden) and "inner hpo/static-solver rebuild remains a future audit layer" in text,
        "Required caveat text is present and forbidden full-refit claims are absent.",
    )


def _validate_heavy_pack(heavy_pack: object, record: object) -> None:
    record(
        "Heavy RUC required auxiliary audit files exist",
        not heavy_pack.missing_files,
        "missing=" + ", ".join(heavy_pack.missing_files)
        if heavy_pack.missing_files
        else f"files={len(REQUIRED_HEAVY_RUC_REPRO_FILES)}",
    )
    root = Path(heavy_pack.root)
    disallowed = sorted(path.name for path in root.glob("*") if path.suffix.lower() in {".csv", ".xlsx", ".xls"})
    record(
        "Heavy RUC auxiliary audit copy excludes CSV/XLSX mirrors",
        not disallowed,
        "disallowed=" + ", ".join(disallowed) if disallowed else "No CSV/XLSX mirrors found in Heavy RUC auxiliary pack.",
    )
    registry = heavy_pack.table("model_registry")
    record(
        "Heavy RUC model registry exists and identifies the finalist",
        root.joinpath("model_registry.parquet").exists()
        and not registry.empty
        and HEAVY_RUC_REPRO_MODEL in set(registry.get("finalist_model", pd.Series(dtype=str)).astype(str)),
        f"path={root / 'model_registry.parquet'}; rows={len(registry)}",
    )
    summary = reproducibility_replay_summary(heavy_pack) if heavy_pack.available else {}
    record(
        "Heavy RUC exact weighted-ensemble replay status is documented",
        summary.get("status") == "Exact weighted-ensemble replay"
        and summary.get("model") == HEAVY_RUC_REPRO_MODEL
        and summary.get("source_sheet") == "Heavy RUC Inputs",
        str(summary),
    )
    prediction_comparison = heavy_pack.table("evidence_prediction_comparison")
    max_delta = pd.to_numeric(prediction_comparison.get("max_abs_pred_delta", pd.Series(dtype=float)), errors="coerce").max()
    record(
        "Heavy RUC evidence prediction replay delta is below tolerance",
        pd.notna(max_delta) and float(max_delta) <= 1e-5,
        f"max_abs_pred_delta={max_delta}",
    )
    weights = pd.to_numeric(registry.get("component_weight", pd.Series(dtype=float)), errors="coerce")
    record(
        "Heavy RUC component weights sum to one",
        not weights.empty and abs(float(weights.sum()) - 1.0) <= 1e-6,
        f"weight_sum={float(weights.sum()) if not weights.empty else 'missing'}",
    )
    components = heavy_pack.table("component_predictions")
    weighted_delta = _heavy_weighted_component_delta(components)
    record(
        "Heavy RUC weighted component sum equals final prediction",
        pd.notna(weighted_delta) and float(weighted_delta) <= 1e-5,
        f"max_abs_delta={weighted_delta}",
    )
    feature_importance = heavy_pack.table("feature_importance_global")
    sensitivities = heavy_pack.table("scenario_sensitivities")
    record(
        "Heavy RUC feature importance rows exist",
        not feature_importance.empty,
        f"rows={len(feature_importance)}",
    )
    record(
        "Heavy RUC scenario sensitivity rows exist",
        not sensitivities.empty,
        f"rows={len(sensitivities)}",
    )
    equation = reproducibility_ensemble_equation(heavy_pack)
    record(
        "Heavy RUC ensemble equation exposes all three vNext component weights",
        "0.708904*C1" in equation
        and "0.212188*C2" in equation
        and "0.078908*C3" in equation,
        equation,
    )


def _weighted_component_delta(components: pd.DataFrame) -> float | pd.NA:
    required = {"score_basis", "eval_grid", "origin", "target_period", "horizon", "weighted_component_pred", "final_pred"}
    if components.empty or not required.issubset(components.columns):
        return pd.NA
    keys = ["score_basis", "eval_grid", "origin", "target_period", "horizon"]
    grouped = (
        components.groupby(keys, dropna=False)
        .agg(rebuilt=("weighted_component_pred", "sum"), final_pred=("final_pred", "first"))
        .copy()
    )
    return float((pd.to_numeric(grouped["rebuilt"], errors="coerce") - pd.to_numeric(grouped["final_pred"], errors="coerce")).abs().max())


def _heavy_weighted_component_delta(components: pd.DataFrame) -> float | pd.NA:
    return _weighted_component_delta(components)


def _ped_component_delta(components: pd.DataFrame) -> float | pd.NA:
    required = {"component_pred", "rebuilt_pred"}
    if components.empty or not required.issubset(components.columns):
        return pd.NA
    return float(
        (
            pd.to_numeric(components["component_pred"], errors="coerce")
            - pd.to_numeric(components["rebuilt_pred"], errors="coerce")
        )
        .abs()
        .max()
    )


def _chart_source_hashes() -> dict[str, str]:
    source_dir = ROOT / "artifacts" / "chart_sources"
    if not source_dir.exists():
        return {}
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_dir.glob("*.csv"))
    }


def _changed_hash_names(before: dict[str, str], after: dict[str, str]) -> str:
    names = sorted(set(before) | set(after))
    changed = [name for name in names if before.get(name) != after.get(name)]
    return ", ".join(changed) if changed else "none"


def _chart_source_auxiliary_references() -> list[str]:
    source_dir = ROOT / "artifacts" / "chart_sources"
    if not source_dir.exists():
        return []
    allowed_auxiliary_sources = {
        "reproducibility_component_r2.csv",
        "r2_ladder_summary.csv",
        "r2_training_fit_detail.csv",
        "r2_reproducibility_gap_register.csv",
    }
    references: list[str] = []
    for path in sorted(source_dir.glob("*.csv")):
        if path.name in allowed_auxiliary_sources:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "dashboard_evidence_pack_reproducibility" in text or "light_ruc_exact_reproducibility" in text:
            references.append(path.name)
    return references


def main() -> int:
    args = parse_args()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    findings = validate(args.data_root, args.repro_root, args.heavy_repro_root, args.ped_repro_root, args.ped_inner_hpo_root)
    failed = [row for row in findings if row["status"] != "PASS"]
    status = "passed" if not failed else "failed"
    lines = [
        "# Light RUC Reproducibility Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {row['check']} | {row['status']} | {row['evidence']} |" for row in findings)
    lines.append("")
    report = "\n".join(lines)
    (artifacts / "light_ruc_reproducibility_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

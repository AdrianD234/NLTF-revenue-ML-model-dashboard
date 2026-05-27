from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.evidence_pack import load_evidence_pack  # noqa: E402
from model_dashboard.light_ruc_reproducibility import (  # noqa: E402
    LIGHT_RUC_REPRO_DESCRIPTION,
    LIGHT_RUC_REPRO_MODEL,
    LIGHT_RUC_REPRO_ROOT,
    REQUIRED_LIGHT_RUC_REPRO_FILES,
    light_ruc_replay_summary,
    load_light_ruc_reproducibility_pack,
)


EXPECTED_MAIN_FINALISTS = {
    "PED VKT per capita": {"quarterly_mape": 3.237143790424483, "annual_mape": 2.033293734597686},
    "Light RUC volume": {"quarterly_mape": 5.363206773795227, "annual_mape": 1.2737736398959618},
    "Heavy RUC volume": {"quarterly_mape": 2.8094728159657563, "annual_mape": 2.061102375292297},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate auxiliary Light RUC reproducibility audit pack.")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repro-root", default=str(LIGHT_RUC_REPRO_ROOT))
    return parser.parse_args()


def validate(data_root: str | Path, repro_root: str | Path) -> list[dict[str, str]]:
    pack = load_light_ruc_reproducibility_pack(repro_root)
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

    return findings


def main() -> int:
    args = parse_args()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    findings = validate(args.data_root, args.repro_root)
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

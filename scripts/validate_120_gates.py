from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.chart_sources import CHART_SOURCE_FILES, CORE_COLUMNS  # noqa: E402
from model_dashboard.data.config import DEFAULT_DIAGNOSTIC_DATA_ROOT  # noqa: E402
from model_dashboard.data_loader import load_parquet_dashboard  # noqa: E402
from model_dashboard.labels import STRESS_BUCKET_ORDER  # noqa: E402


EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate extended 120-gate dashboard suite.")
    parser.add_argument("--data-root", default=str(DEFAULT_DIAGNOSTIC_DATA_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def read_text(path: str) -> str:
    target = ROOT / path
    return target.read_text(encoding="utf-8") if target.exists() else ""


def read_source(filename: str) -> pd.DataFrame:
    path = ROOT / "artifacts" / "chart_sources" / filename
    if not path.exists() or path.stat().st_size == 0:
        raise AssertionError(f"Missing or empty chart source table: {filename}")
    return pd.read_csv(path)


def gate_result(gate_id: int, description: str, fn: Callable[[], str]) -> dict[str, str | int]:
    try:
        evidence = fn()
        return {"id": gate_id, "description": description, "status": "PASS", "evidence": evidence}
    except Exception as exc:
        return {"id": gate_id, "description": description, "status": "FAIL", "evidence": str(exc)}


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    artifacts = repo_root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    load_parquet_dashboard(args.data_root, repo_root, allow_csv_preview=False)

    def check_all_chart_sources_exist() -> str:
        missing = []
        for filename in CHART_SOURCE_FILES:
            path = repo_root / "artifacts" / "chart_sources" / filename
            if not path.exists() or path.stat().st_size == 0:
                missing.append(filename)
        if missing:
            raise AssertionError("Missing chart source tables: " + ", ".join(missing))
        return f"{len(CHART_SOURCE_FILES)} chart source tables exist."

    def check_core_columns() -> str:
        offenders = []
        for filename in CHART_SOURCE_FILES:
            table = read_source(filename)
            missing = [column for column in CORE_COLUMNS if column not in table.columns]
            if missing:
                offenders.append(f"{filename}: {', '.join(missing)}")
        if offenders:
            raise AssertionError("; ".join(offenders))
        return "All chart source tables include the core source contract columns."

    def check_ensemble() -> str:
        table = read_source("overview_ensemble_composition.csv")
        expected = {
            "PED VKT per capita": [100.0],
            "Light RUC volume": [33.3333395, 33.3333312, 33.3333293],
            "Heavy RUC volume": [46.9332, 28.1844, 14.4373, 10.4451],
        }
        for stream, weights in expected.items():
            actual = (
                table[table["stream_label"].eq(stream)]
                .sort_values("component_rank")["weight_pct"]
                .astype(float)
                .to_list()
            )
            if len(actual) != len(weights) or any(abs(a - e) > 0.001 for a, e in zip(actual, weights, strict=True)):
                raise AssertionError(f"{stream} weights do not match current Parquet components: {actual}")
        return "Current finalist component weights match ensemble_components_json."

    def check_finalist_values() -> str:
        table = read_source("overview_finalist_forecast_accuracy.csv").set_index(["stream_label", "metric_name"])
        expected = {
            ("PED VKT per capita", "Quarterly MAPE"): 2.473245,
            ("PED VKT per capita", "Annual MAPE"): 2.385625,
            ("Light RUC volume", "Quarterly MAPE"): 9.147545,
            ("Light RUC volume", "Annual MAPE"): 5.999499,
            ("Heavy RUC volume", "Quarterly MAPE"): 3.484368,
            ("Heavy RUC volume", "Annual MAPE"): 3.019980,
        }
        for key, expected_value in expected.items():
            actual = pd.to_numeric(table.loc[key, "metric_value"], errors="coerce")
            if pd.isna(actual) or abs(float(actual) - expected_value) > 0.001:
                raise AssertionError(f"{key} expected {expected_value}, got {actual}")
        return "Finalist accuracy source table reconciles to current Parquet values."

    def check_stress() -> str:
        table = read_source("overview_stress_horizon_checks.csv")
        for stream in EXPECTED_STREAMS:
            buckets = table[table["stream_label"].eq(stream)]["stress_bucket"].tolist()
            if buckets != list(STRESS_BUCKET_ORDER):
                raise AssertionError(f"{stream} stress bucket order is {buckets}")
        heavy = table[table["stream_label"].eq("Heavy RUC volume")].set_index("stress_bucket")
        for bucket in ["2024+", "2022-23"]:
            if pd.notna(pd.to_numeric(heavy.loc[bucket, "metric_value"], errors="coerce")):
                raise AssertionError(f"Heavy RUC {bucket} should remain a gap unless enriched from a valid source.")
        return "Stress aliases coalesce and Heavy RUC missing windows remain explicit gaps."

    def check_full_sample_gain_label() -> str:
        gain = read_source("schiff_paired_or_fullsample_gain.csv")
        text = " ".join(gain["chart_title"].astype(str).unique()) + " " + " ".join(gain["calculation_basis"].astype(str).unique())
        if "Full-sample" not in text or "Paired Gain vs Schiff" in text:
            raise AssertionError(text)
        return "Gain chart is labelled full-sample, not paired."

    def check_light_paired_gain() -> str:
        gain = read_source("schiff_paired_or_fullsample_gain.csv")
        light = gain[gain["stream_label"].eq("Light RUC volume")]
        paired = pd.to_numeric(light["paired_gain_pp"], errors="coerce").dropna()
        full = pd.to_numeric(light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"], errors="coerce").dropna()
        if paired.empty or full.empty or float(paired.iloc[0]) >= 0 or float(full.iloc[0]) <= 0:
            raise AssertionError(f"paired={paired.to_list()}; full={full.to_list()}")
        return "Light RUC paired common-grid gain is negative while full-sample gain is positive and labelled."

    def check_decision_labels() -> str:
        table = read_source("scenario_decision_summary.csv")
        expected = {"Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate"}
        if not expected.issubset(set(table["metric_name"])):
            raise AssertionError("Missing labels: " + ", ".join(sorted(expected - set(table["metric_name"]))))
        return "Decision summary uses explicit full-sample and paired labels."

    def check_horizon_sources() -> str:
        for filename in ["scenario_horizon_comparison.csv", "schiff_benchmark_horizon_profiles.csv"]:
            table = read_source(filename)
            if not EXPECTED_STREAMS.issubset(set(table["stream_label"])):
                raise AssertionError(f"{filename} missing streams.")
            if not {"Finalist", "Schiff"}.issubset(set(table["scenario"])):
                raise AssertionError(f"{filename} missing finalist/Schiff scenarios.")
        return "Scenario and Schiff horizon chart sources include all streams and both benchmark scenarios."

    def check_acf_source() -> str:
        table = read_source("diagnostics_residual_autocorrelation.csv")
        if not EXPECTED_STREAMS.issubset(set(table["stream_label"])):
            raise AssertionError("ACF source table missing streams.")
        if not table["notes"].str.contains("All selected quarterly prediction residuals", regex=False).all():
            raise AssertionError("ACF residual source is not documented on every row.")
        return "ACF chart source table exists and documents residual source."

    def check_r2_label() -> str:
        app_text = read_text("app.py")
        if "Mean calibration R2" not in app_text or "Mean Adjusted R2" in app_text:
            raise AssertionError("R2 KPI is not labelled as calibration R2.")
        return "R2 KPI label matches calibration/MZ source semantics."

    def check_residual_units() -> str:
        text = read_text("model_dashboard/plots.py") + read_text("app.py")
        if "Fitted value, native units" not in text or "Fitted value (m)" in text:
            raise AssertionError("Residual vs fitted x-axis unit label is misleading.")
        return "Residual vs fitted axis uses native-unit wording."

    def check_candidate_count_label() -> str:
        app_text = read_text("app.py")
        if "Plotted candidates" not in app_text or "Candidate Models" in app_text:
            raise AssertionError("Candidate count label is ambiguous.")
        return "Candidate count label identifies plotted/default rows."

    def check_semantic_report() -> str:
        report = read_text("artifacts/semantic_label_validation_report.md")
        if "Status: **passed**" not in report:
            raise AssertionError("Semantic label validation report is missing or failed.")
        return "Semantic label validation report passed."

    def check_chart_source_report() -> str:
        report = read_text("artifacts/chart_source_validation_report.md")
        if "Status: **passed**" not in report:
            raise AssertionError("Chart source validation report is missing or failed.")
        return "Chart source validation report passed."

    def check_visual_report() -> str:
        report = read_text("artifacts/visual_conformance_validation_report.md")
        if "Status: **passed**" not in report:
            raise AssertionError("Visual conformance validation report is missing or failed.")
        return "Visual conformance validation report passed."

    def check_backlog() -> str:
        backlog = read_text("BUG_BACKLOG.md")
        open_items = re.findall(r"- \[ \].*", backlog)
        if open_items:
            raise AssertionError(f"BUG_BACKLOG.md has {len(open_items)} open items.")
        return "BUG_BACKLOG.md has no unchecked items."

    def check_screenshots() -> str:
        required = [
            "final-01-overview.png",
            "final-02-diagnostics.png",
            "final-03-scenario-comparison.png",
            "final-04-schiff-benchmark.png",
            "final-overview.png",
            "final-diagnostics.png",
            "final-scenario-comparison.png",
            "final-schiff-benchmark.png",
        ]
        missing = [name for name in required if not (repo_root / "artifacts" / "screenshots" / name).exists()]
        if missing:
            raise AssertionError("Missing screenshots: " + ", ".join(missing))
        return "All final Playwright and page screenshots exist."

    def check_visual_matrix() -> str:
        matrix = read_text("artifacts/target_vs_current_screenshot_matrix.md")
        pages = ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark"]
        if not all(page in matrix for page in pages) or matrix.count("PASS") < 4:
            raise AssertionError("Target-vs-current matrix does not mark all four pages PASS.")
        return "Target-vs-current matrix marks all four pages PASS."

    def check_hover_terms() -> str:
        report = read_text("artifacts/hover_review.md") + read_text("artifacts/filter_interaction_review.md")
        if "PASS" not in report and "passed" not in report.lower():
            raise AssertionError("Interaction/hover reports do not contain pass evidence.")
        return "Hover and filter review artifacts contain pass evidence."

    def check_existing_100_gates() -> str:
        path = repo_root / "artifacts" / "80_gate_validation_results.json"
        if not path.exists():
            raise AssertionError("Missing existing 100-gate results.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("failed_gates", 1)) != 0 or int(data.get("passed_gates", 0)) < 100:
            raise AssertionError(f"Existing gate summary is not clean: passed={data.get('passed_gates')} failed={data.get('failed_gates')}")
        return "Existing visual/data gate suite reports at least 100 passed and zero failed."

    gates: list[tuple[int, str, Callable[[], str]]] = [
        (101, "Every main chart has a source table.", check_all_chart_sources_exist),
        (102, "Chart source tables include the required source contract columns.", check_core_columns),
        (103, "Overview finalist accuracy source reconciles to current Parquet.", check_finalist_values),
        (104, "Ensemble composition source uses Parquet component weights.", check_ensemble),
        (105, "Stress source coalesces aliases and preserves Heavy RUC gaps.", check_stress),
        (106, "Schiff gain chart is labelled full-sample when showing full-sample gains.", check_full_sample_gain_label),
        (107, "Light RUC paired common-grid weakness is preserved.", check_light_paired_gain),
        (108, "Scenario decision labels separate full-sample gains and paired win rate.", check_decision_labels),
        (109, "Horizon chart sources include all streams and scenarios.", check_horizon_sources),
        (110, "ACF chart source table exists and documents residual source.", check_acf_source),
        (111, "Calibration R2 label matches its source field.", check_r2_label),
        (112, "Residual-vs-fitted axis units are not misleading.", check_residual_units),
        (113, "Candidate count label is precise.", check_candidate_count_label),
        (114, "Chart source validation report passed.", check_chart_source_report),
        (115, "Semantic label validation report passed.", check_semantic_report),
        (116, "Visual conformance validation report passed.", check_visual_report),
        (117, "Final screenshots exist for all four pages.", check_screenshots),
        (118, "Screenshot matrix marks all pages PASS.", check_visual_matrix),
        (119, "Filter and hover evidence is present.", check_hover_terms),
        (120, "Existing 100-gate validation has zero failures and backlog is closed.", lambda: check_existing_100_gates() + " " + check_backlog()),
    ]
    extension_results = [gate_result(gate_id, description, fn) for gate_id, description, fn in gates]
    existing_results_path = repo_root / "artifacts" / "80_gate_validation_results.json"
    existing_results: list[dict[str, str | int]] = []
    if existing_results_path.exists():
        existing_payload = json.loads(existing_results_path.read_text(encoding="utf-8"))
        existing_results = list(existing_payload.get("gates", []))
    else:
        existing_results = [
            {
                "id": 1,
                "description": "Existing 100-gate validation results are available.",
                "status": "FAIL",
                "evidence": "Missing artifacts/80_gate_validation_results.json",
            }
        ]

    results = existing_results + extension_results
    failed = [gate for gate in results if gate["status"] != "PASS"]
    payload = {
        "total_gates": len(results),
        "passed_gates": len(results) - len(failed),
        "failed_gates": len(failed),
        "gates": results,
    }
    (artifacts / "120_gate_validation_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# 120-Gate Extension Validation Report",
        "",
        f"Status: **{'passed' if not failed else 'failed'}**.",
        "",
        f"Passed gates: {payload['passed_gates']} / {payload['total_gates']}",
        "",
        "Gates 1-100 are imported from `artifacts/80_gate_validation_results.json`; gates 101-120 are the chart-source and semantic reconciliation extension.",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {gate['id']}. {gate['description']} | {gate['status']} | {gate['evidence']} |" for gate in results)
    lines.append("")
    (artifacts / "120_gate_validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

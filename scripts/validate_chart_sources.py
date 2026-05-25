from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.chart_sources import CHART_SOURCE_FILES, CORE_COLUMNS  # noqa: E402
from model_dashboard.data_loader import DEFAULT_DIAGNOSTIC_DATA_ROOT, load_parquet_dashboard  # noqa: E402
from model_dashboard.labels import STRESS_BUCKET_ORDER  # noqa: E402


EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dashboard chart source tables.")
    parser.add_argument("--data-root", default=str(DEFAULT_DIAGNOSTIC_DATA_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def read_table(filename: str) -> pd.DataFrame:
    path = CHART_SOURCE_DIR / filename
    if not path.exists():
        raise AssertionError(f"Missing chart source table: {path}")
    if path.stat().st_size == 0:
        raise AssertionError(f"Empty chart source table: {path}")
    return pd.read_csv(path)


def approx(actual: Any, expected: float, tolerance: float = 0.001) -> bool:
    value = pd.to_numeric(actual, errors="coerce")
    return pd.notna(value) and abs(float(value) - expected) <= tolerance


def validate() -> list[tuple[str, str, str]]:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    load_parquet_dashboard(args.data_root, repo_root, allow_csv_preview=False)

    findings: list[tuple[str, str, str]] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        findings.append((name, "PASS" if passed else "FAIL", evidence))

    for filename, (page, chart_id) in CHART_SOURCE_FILES.items():
        try:
            table = read_table(filename)
            missing = [column for column in CORE_COLUMNS if column not in table.columns]
            page_ok = set(table["page"].dropna().astype(str)) == {page}
            id_ok = set(table["chart_id"].dropna().astype(str)) == {chart_id}
            basis_ok = table["calculation_basis"].dropna().astype(str).str.len().gt(0).all()
            record(
                f"{filename} exists and has required columns",
                not missing and page_ok and id_ok and basis_ok,
                f"rows={len(table):,}; missing={missing}; page_ok={page_ok}; chart_id_ok={id_ok}",
            )
        except Exception as exc:
            record(f"{filename} exists and has required columns", False, str(exc))

    ensemble = read_table("overview_ensemble_composition.csv")
    expected_weights = {
        "PED VKT per capita": [100.0],
        "Light RUC volume": [33.3333395, 33.3333312, 33.3333293],
        "Heavy RUC volume": [46.9332, 28.1844, 14.4373, 10.4451],
    }
    ensemble_ok = True
    for stream, weights in expected_weights.items():
        actual = (
            ensemble[ensemble["stream_label"].eq(stream)]
            .sort_values("component_rank")["weight_pct"]
            .astype(float)
            .to_list()
        )
        ensemble_ok = ensemble_ok and len(actual) == len(weights) and all(
            abs(a - e) <= 0.001 for a, e in zip(actual, weights, strict=True)
        )
    demo_fragments = {"57.1", "38.7", "23.2", "21.8", "48.7", "37.7", "13.7"}
    demo_visible = any(fragment in ",".join(ensemble["metric_display"].astype(str)) for fragment in demo_fragments)
    record("Ensemble source uses Parquet component weights", ensemble_ok and not demo_visible, "Expected current finalist component weights were checked.")

    stress = read_table("overview_stress_horizon_checks.csv")
    stress_ok = True
    for stream in EXPECTED_STREAMS:
        stream_rows = stress[stress["stream_label"].eq(stream)]
        stress_ok = stress_ok and stream_rows["stress_bucket"].tolist() == list(STRESS_BUCKET_ORDER)
    for stream in ["PED VKT per capita", "Light RUC volume"]:
        for bucket in STRESS_BUCKET_ORDER:
            row = stress[stress["stream_label"].eq(stream) & stress["stress_bucket"].eq(bucket)]
            stress_ok = stress_ok and not row.empty and pd.to_numeric(row["metric_value"], errors="coerce").notna().any()
    heavy = stress[stress["stream_label"].eq("Heavy RUC volume")].set_index("stress_bucket")
    heavy_core = all(
        pd.notna(pd.to_numeric(heavy.loc[bucket, "metric_value"], errors="coerce"))
        for bucket in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]
    )
    heavy_gaps = all(
        pd.isna(pd.to_numeric(heavy.loc[bucket, "metric_value"], errors="coerce"))
        for bucket in ["2024+", "2022-23"]
    )
    record("Stress chart source coalesces aliases and preserves missing gaps", stress_ok and heavy_core and heavy_gaps, "Six buckets per stream; Heavy RUC policy windows remain gaps.")

    scenario = read_table("scenario_decision_summary.csv")
    scenario_terms = {"Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate"}
    record("Scenario summary labels full-sample gains and paired win rate", scenario_terms.issubset(set(scenario["metric_name"])), "Decision-source metric labels inspected.")

    gain = read_table("schiff_paired_or_fullsample_gain.csv")
    gain_text = " ".join(gain["chart_title"].astype(str).unique()) + " " + " ".join(gain["calculation_basis"].astype(str).unique())
    light_gain = gain[gain["stream_label"].eq("Light RUC volume")]
    light_paired_negative = float(light_gain["paired_gain_pp"].dropna().iloc[0]) < 0
    record(
        "Schiff gain chart is labelled full-sample and preserves Light RUC paired weakness",
        "Full-sample" in gain_text and "Paired Gain vs Schiff" not in gain_text and light_paired_negative,
        f"Light paired gain={float(light_gain['paired_gain_pp'].dropna().iloc[0]):.3f} pp.",
    )

    for filename in ["scenario_horizon_comparison.csv", "schiff_benchmark_horizon_profiles.csv"]:
        table = read_table(filename)
        record(
            f"{filename} includes all streams and scenarios",
            EXPECTED_STREAMS.issubset(set(table["stream_label"])) and {"Finalist", "Schiff"}.issubset(set(table["scenario"])),
            f"streams={sorted(set(table['stream_label'].dropna()))}; scenarios={sorted(set(table['scenario'].dropna()))}",
        )

    acf = read_table("diagnostics_residual_autocorrelation.csv")
    record(
        "ACF source table documents residual source",
        EXPECTED_STREAMS.issubset(set(acf["stream_label"])) and acf["notes"].str.contains("All selected quarterly prediction residuals", regex=False).all(),
        f"rows={len(acf):,}",
    )

    pass_matrix = read_table("diagnostics_pass_matrix.csv")
    record(
        "Diagnostics source labels calibration R2 and Watch/Fail statuses",
        "Calibration R2" in set(pass_matrix["metric_name"]) and "Adjusted R2" not in set(pass_matrix["metric_name"]) and {"Watch", "Fail"}.issubset(set(pass_matrix["pass_status"])),
        f"tests={sorted(set(pass_matrix['metric_name'].dropna()))}",
    )

    residual = read_table("diagnostics_residual_vs_fitted.csv")
    record(
        "Residual vs fitted source uses native-unit calculation basis",
        residual["calculation_basis"].str.contains("native stream units", regex=False).all(),
        f"rows={len(residual):,}",
    )

    return findings


def main() -> int:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    try:
        findings = validate()
    except Exception as exc:
        findings = [("Chart source validation", "FAIL", str(exc))]
    failed = [row for row in findings if row[1] != "PASS"]
    status = "passed" if not failed else "failed"
    lines = [
        "# Chart Source Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {name} | {state} | {evidence} |" for name, state, evidence in findings)
    lines.append("")
    report = "\n".join(lines)
    (artifacts / "chart_source_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

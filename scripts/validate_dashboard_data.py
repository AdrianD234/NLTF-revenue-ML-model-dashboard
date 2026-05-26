from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT  # noqa: E402
from model_dashboard.evidence_pack import REQUIRED_EVIDENCE_TABLES, load_evidence_pack, resolve_evidence_pack_root  # noqa: E402
from model_dashboard.labels import OVERVIEW_STRESS_BUCKET_ORDER, SCHIFF_SPEC_BENCHMARK_LABEL, STRESS_BUCKET_ORDER  # noqa: E402


EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
EXPECTED_FINALISTS = {
    "PED VKT per capita": (3.237144, 2.033294),
    "Light RUC volume": (5.363207, 1.273774),
    "Heavy RUC volume": (2.809473, 2.061102),
}
EXPECTED_FINALIST_MODELS = {
    "Light RUC volume": "dynamic_RESID_GBR_n150_d1_lr0.05_w36",
}
EXPECTED_SCHIFF_SPEC = {
    "PED VKT per capita": (4.674917, 3.585729),
    "Light RUC volume": (8.521397, 2.702000),
    "Heavy RUC volume": (8.761652, 8.879508),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the dashboard evidence-pack data contract.")
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--min-default-candidates", type=int, default=101)
    return parser.parse_args()


def validate() -> tuple[str, list[str]]:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    pack_root = resolve_evidence_pack_root(args.data_root)
    findings: list[str] = []

    missing = [name for name in REQUIRED_EVIDENCE_TABLES if not (pack_root / "data" / name).exists()]
    if missing:
        raise AssertionError("Missing required evidence-pack files: " + ", ".join(missing))
    forbidden_dirs = [pack_root / name for name in ["sources", "tables_csv", "logs", "screenshots"] if (pack_root / name).exists()]
    if forbidden_dirs:
        raise AssertionError("Slim evidence pack contains forbidden raw-output directories: " + ", ".join(str(path) for path in forbidden_dirs))
    oversized = [path for path in pack_root.rglob("*") if path.is_file() and path.stat().st_size > 50 * 1024 * 1024]
    if oversized:
        raise AssertionError("Slim evidence pack contains file(s) above 50 MB: " + ", ".join(str(path) for path in oversized))
    allowed_root_files = {"manifest.json", "README.md", "data_inventory.csv"}
    for path in pack_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(pack_root)
        if rel.parts[0] == "data" and path.suffix == ".parquet":
            continue
        if rel.parts[0] == "docs":
            continue
        if len(rel.parts) == 1 and rel.name in allowed_root_files:
            continue
        raise AssertionError(f"Slim evidence pack contains a non-slim file: {rel}")
    findings.append(f"- [pass] Evidence pack resolved: `{pack_root}`.")
    findings.append("- [pass] Slim evidence pack contains only root metadata, docs, and data/*.parquet files under 50 MB.")
    findings.append(f"- [pass] Required Parquet files present: {len(REQUIRED_EVIDENCE_TABLES)}.")

    loaded = load_evidence_pack(pack_root, repo_root)
    finalists = loaded.data["recommended"]
    for stream, (qtr, annual) in EXPECTED_FINALISTS.items():
        rows = finalists[finalists["stream_label"].eq(stream)]
        if len(rows) != 1:
            raise AssertionError(f"Expected exactly one finalist row for {stream}; found {len(rows)}.")
        row = rows.iloc[0]
        if abs(float(row["quarterly_mape"]) - qtr) > 0.001:
            raise AssertionError(f"{stream} quarterly finalist MAPE does not reconcile.")
        if abs(float(row["annual_mape"]) - annual) > 0.001:
            raise AssertionError(f"{stream} annual finalist MAPE does not reconcile.")
        expected_model = EXPECTED_FINALIST_MODELS.get(stream)
        if expected_model and str(row.get("model")) != expected_model:
            raise AssertionError(f"{stream} finalist model is {row.get('model')}, expected {expected_model}.")
    findings.append("- [pass] Current finalist quarterly and annual MAPE reconcile to the evidence pack.")

    schiff = loaded.data["schiff_df"]
    for stream, (qtr, annual) in EXPECTED_SCHIFF_SPEC.items():
        rows = schiff[schiff["stream_label"].eq(stream)]
        if len(rows) != 1:
            raise AssertionError(f"Expected exactly one Schiff specification benchmark row for {stream}; found {len(rows)}.")
        row = rows.iloc[0]
        if abs(float(row["quarterly_mape"]) - qtr) > 0.001:
            raise AssertionError(f"{stream} Schiff specification quarterly MAPE does not reconcile.")
        if abs(float(row["annual_mape"]) - annual) > 0.001:
            raise AssertionError(f"{stream} Schiff specification annual MAPE does not reconcile.")
    findings.append("- [pass] Schiff specification benchmark quarterly and annual MAPE reconcile to the evidence pack.")

    summary = loaded.data["summary"]
    if len(summary) < args.min_default_candidates:
        raise AssertionError(f"Default candidate frontier has {len(summary):,} rows; expected >100.")
    if "mape_h12" in summary.columns:
        stale_h12 = pd.to_numeric(summary["mape_h12"], errors="coerce").round(2).eq(20.50)
        if stale_h12.any():
            raise AssertionError("Default candidate summary still contains the old Heavy RUC 20.50 H12 Schiff-style value.")
    frontier = pd.read_csv(repo_root / "artifacts" / "chart_sources" / "overview_candidate_search_frontier.csv")
    if not {"Selected finalist", SCHIFF_SPEC_BENCHMARK_LABEL}.issubset(set(frontier["point_type"])):
        raise AssertionError("Candidate frontier source table is missing finalist or Schiff marker rows.")
    frontier_text = frontier.fillna("").astype(str).agg(lambda row: " ".join(row.to_list()), axis=1)
    if frontier_text.str.contains(r"20\.50|20\.499", regex=True).any():
        raise AssertionError("Candidate frontier source table still contains the old Heavy RUC 20.50 H12 Schiff-style value.")
    findings.append(f"- [pass] Candidate frontier default rows: {len(summary):,}.")

    scenario = loaded.data["scenario_comparison"].set_index("stream_label")
    light = scenario.loc["Light RUC volume"]
    if not (float(light["full_sample_qtr_gain_pp"]) > 0 and float(light["full_sample_annual_gain_pp"]) > 0):
        raise AssertionError("Light RUC paper-style quarterly and annual gains are not both preserved.")
    if abs(float(light["full_sample_qtr_gain_pp"]) - 3.158190) > 0.001:
        raise AssertionError("Old Light RUC gain is still present instead of the v4 +3.158 pp paper-style gain.")
    light_rec = finalists[finalists["stream_label"].eq("Light RUC volume")].iloc[0]
    light_schiff = schiff[schiff["stream_label"].eq("Light RUC volume")].iloc[0]
    op_annual_gain = float(light_schiff["operational_annual_mape"]) - float(light_rec["operational_annual_mape"])
    if op_annual_gain >= 0:
        raise AssertionError("Light RUC operational annual watch is not preserved.")
    findings.append("- [pass] Full-sample gain and paired win-rate semantics are separated; Light RUC operational annual watch remains visible.")

    stress = loaded.data["stress"]
    for stream in EXPECTED_STREAMS:
        rows = stress[stress["stream_label"].eq(stream)]
        if rows["stress_bucket"].astype(str).tolist() != list(STRESS_BUCKET_ORDER):
            raise AssertionError(f"Stress bucket order is wrong for {stream}.")
    overview_stress = pd.read_csv(repo_root / "artifacts" / "chart_sources" / "overview_stress_horizon_checks.csv")
    for stream in EXPECTED_STREAMS:
        rows = overview_stress[overview_stress["stream_label"].eq(stream)]
        if rows["stress_bucket"].astype(str).tolist() != list(OVERVIEW_STRESS_BUCKET_ORDER):
            raise AssertionError(f"Overview default stress chart still exposes policy windows for {stream}.")
    findings.append("- [pass] Stress/horizon rows preserve source policy windows, while Overview default shows horizon buckets only.")

    acf = loaded.data["diagnostic_acf"]
    if not EXPECTED_STREAMS.issubset(set(acf["stream_label"])):
        raise AssertionError("Diagnostic ACF table does not cover all streams.")
    if "residual_source" not in acf.columns or acf["residual_source"].dropna().empty:
        raise AssertionError("Diagnostic ACF residual scope is not documented.")
    findings.append("- [pass] Diagnostic ACF residual scope is documented.")

    stale_finalist_strings = {"5.49", "12.38"}
    finalist_text = finalists.to_string()
    offenders = [value for value in stale_finalist_strings if value in finalist_text]
    if offenders:
        raise AssertionError("Stale finalist value(s) found in current finalists: " + ", ".join(offenders))
    findings.append("- [pass] Stale old finalist values are absent from current finalists.")

    return "passed", findings


def main() -> int:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    try:
        status, findings = validate()
        exit_code = 0
    except Exception as exc:
        status = "failed"
        findings = [f"- [fail] {exc}"]
        exit_code = 1
    report = "\n".join(
        [
            "# Data Validation Review",
            "",
            f"Status: **{status}**.",
            "",
            "Default dashboard validation is evidence-pack only; legacy run folders and fixtures are review-only.",
            "",
            *findings,
            "",
        ]
    )
    (artifacts / "data_validation_review.md").write_text(report, encoding="utf-8")
    print(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

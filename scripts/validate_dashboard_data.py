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
from model_dashboard.labels import STRESS_BUCKET_ORDER  # noqa: E402


EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
EXPECTED_FINALISTS = {
    "PED VKT per capita": (2.473245, 2.385625),
    "Light RUC volume": (9.147545, 5.999499),
    "Heavy RUC volume": (3.484368, 3.019980),
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
    findings.append(f"- [pass] Evidence pack resolved: `{pack_root}`.")
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
    findings.append("- [pass] Current finalist quarterly and annual MAPE reconcile to the evidence pack.")

    summary = loaded.data["summary"]
    if len(summary) < args.min_default_candidates:
        raise AssertionError(f"Default candidate frontier has {len(summary):,} rows; expected >100.")
    if not {"Selected finalist", "Schiff benchmark"}.issubset(set(pd.read_csv(repo_root / "artifacts" / "chart_sources" / "overview_candidate_search_frontier.csv")["point_type"])):
        raise AssertionError("Candidate frontier source table is missing finalist or Schiff marker rows.")
    findings.append(f"- [pass] Candidate frontier default rows: {len(summary):,}.")

    scenario = loaded.data["scenario_comparison"].set_index("stream_label")
    light = scenario.loc["Light RUC volume"]
    if not (float(light["full_sample_qtr_gain_pp"]) > 0 and float(light["paired_gain_pp"]) < 0):
        raise AssertionError("Light RUC full-sample gain and paired weakness are not both preserved.")
    findings.append("- [pass] Full-sample gain and paired gain semantics are separated.")

    stress = loaded.data["stress"]
    for stream in EXPECTED_STREAMS:
        rows = stress[stress["stream_label"].eq(stream)]
        if rows["stress_bucket"].astype(str).tolist() != list(STRESS_BUCKET_ORDER):
            raise AssertionError(f"Stress bucket order is wrong for {stream}.")
    findings.append("- [pass] Stress/horizon rows use the required six-bucket order.")

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

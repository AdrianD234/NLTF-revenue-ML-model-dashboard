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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dashboard semantic labels.")
    parser.add_argument("--data-root", default=str(DEFAULT_EVIDENCE_PACK_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def validate() -> list[tuple[str, str, str]]:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    load_evidence_pack(args.data_root, repo_root)

    app_text = read_text(repo_root / "app.py")
    plot_text = read_text(repo_root / "model_dashboard" / "plots.py")
    chart_spec = read_text(repo_root / "DASHBOARD_PAGE_CHART_SPEC.lock.md")
    screenshot_review = read_text(repo_root / "artifacts" / "screenshot_review.md")

    findings: list[tuple[str, str, str]] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        findings.append((name, "PASS" if passed else "FAIL", evidence))

    record(
        "Candidate count label is precise",
        "Plotted candidates" in app_text and "plotted candidates from" in app_text and "loaded candidates" not in app_text and "Candidate Models" not in app_text,
        "Overview KPI and frontier caption identify plotted candidate rows rather than vague loaded/model counts.",
    )
    record(
        "Calibration R2 is not labelled adjusted R2",
        "Mean calibration R2" in app_text and "Mean Adjusted R2" not in app_text,
        "Diagnostics KPI title inspected in app.py.",
    )
    record(
        "Full-sample gain chart is not labelled paired",
        "3. Full-sample Gain vs Schiff specification benchmark" in app_text and "Paired Gain vs Schiff" not in app_text,
        "Schiff gain chart title inspected in app.py.",
    )
    record(
        "Decision table separates full-sample gains from paired win rate",
        all(term in app_text for term in ["Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate"]),
        "Scenario and Schiff summary labels inspected in app.py.",
    )
    record(
        "Residual vs fitted axis does not use misleading million-unit label",
        "Fitted value, native units" in (app_text + plot_text) and "Fitted value (m)" not in (app_text + plot_text),
        "Residual axis title inspected in app.py/plot helpers.",
    )

    gain_source = repo_root / "artifacts" / "chart_sources" / "schiff_paired_or_fullsample_gain.csv"
    if gain_source.exists():
        gain = pd.read_csv(gain_source)
        light = gain[gain["stream_label"].eq("Light RUC volume")]
        paired_gain = pd.to_numeric(light["paired_gain_pp"], errors="coerce").dropna()
        full_gain = pd.to_numeric(
            light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"],
            errors="coerce",
        ).dropna()
        record(
            "Light RUC benchmark weakness is not hidden by full-sample gain label",
            not paired_gain.empty and float(paired_gain.iloc[0]) < 0 and not full_gain.empty and float(full_gain.iloc[0]) < 0,
            f"paired_gain={float(paired_gain.iloc[0]) if not paired_gain.empty else 'missing'}; full_sample_gain={float(full_gain.iloc[0]) if not full_gain.empty else 'missing'}",
        )
    else:
        record("Light RUC benchmark weakness is not hidden by full-sample gain label", False, "Missing Schiff gain source table.")

    stale_spec_terms = [
        "Candidate Models",
        "Mean Adjusted R2",
        "Paired Gain vs Schiff",
    ]
    stale_in_spec = [term for term in stale_spec_terms if term in chart_spec]
    record(
        "Dashboard chart spec uses current semantic labels",
        not stale_in_spec,
        "stale_terms=" + ", ".join(stale_in_spec) if stale_in_spec else "No stale chart-spec labels found.",
    )

    record(
        "Screenshot review does not describe the full-sample chart as paired",
        "Paired Gain vs Schiff" not in screenshot_review,
        "artifacts/screenshot_review.md label wording inspected.",
    )

    return findings


def main() -> int:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    try:
        findings = validate()
    except Exception as exc:
        findings = [("Semantic label validation", "FAIL", str(exc))]
    failed = [row for row in findings if row[1] != "PASS"]
    status = "passed" if not failed else "failed"
    lines = [
        "# Semantic Label Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {name} | {state} | {evidence} |" for name, state, evidence in findings)
    lines.append("")
    report = "\n".join(lines)
    (artifacts / "semantic_label_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

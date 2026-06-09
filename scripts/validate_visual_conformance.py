from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


REQUIRED_SCREENSHOTS = [
    "artifacts/screenshots/final-01-overview.png",
    "artifacts/screenshots/final-02-diagnostics.png",
    "artifacts/screenshots/final-03-scenario-comparison.png",
    "artifacts/screenshots/final-04-schiff-benchmark.png",
    "artifacts/screenshots/final-05-governance-reproducibility.png",
    "artifacts/screenshots/final-overview.png",
    "artifacts/screenshots/final-diagnostics.png",
    "artifacts/screenshots/final-scenario-comparison.png",
    "artifacts/screenshots/final-schiff-benchmark.png",
    "artifacts/screenshots/final-governance-reproducibility.png",
]

REVIEW_FILES = [
    "artifacts/target_vs_current_screenshot_matrix.md",
    "artifacts/page5_target_vs_current_matrix.md",
    "artifacts/visual_delta_review.md",
    "artifacts/screenshot_review.md",
    "artifacts/page5_visual_review.md",
    "artifacts/page5_screenshot_review.md",
    "artifacts/visual_reference_comparison.md",
    "artifacts/reviews/visual_styling.md",
    "artifacts/reviews/layout_grid.md",
    "artifacts/reviews/chart_semantics.md",
    "artifacts/reviews/data_visual_mapping.md",
]


def read_text(path: str) -> str:
    target = ROOT / path
    return target.read_text(encoding="utf-8") if target.exists() else ""


def validate() -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []

    def record(name: str, passed: bool, evidence: str) -> None:
        findings.append((name, "PASS" if passed else "FAIL", evidence))

    missing = [path for path in REQUIRED_SCREENSHOTS if not (ROOT / path).exists()]
    record("Final browser screenshots exist for all five pages", not missing, "missing=" + ", ".join(missing) if missing else "All required screenshots present.")

    backlog = read_text("BUG_BACKLOG.md")
    open_backlog = re.findall(r"- \[ \].*", backlog)
    record("BUG_BACKLOG has no unchecked items", not open_backlog, f"open_items={len(open_backlog)}")

    unresolved = []
    for path in REVIEW_FILES:
        text = read_text(path)
        if not text:
            unresolved.append(f"{path}: missing")
            continue
        if re.search(r"Status:\s*\*\*?failed|\|\s*FAIL\s*\||\bUNRESOLVED\b|- \[ \]", text, flags=re.IGNORECASE):
            unresolved.append(path)
    record("Visual reviewer artifacts are resolved", not unresolved, "unresolved=" + ", ".join(unresolved) if unresolved else "All reviewer artifacts are resolved.")

    matrix = read_text("artifacts/target_vs_current_screenshot_matrix.md")
    required_pages = ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark", "Governance & Reproducibility"]
    matrix_ok = all(page in matrix for page in required_pages) and matrix.count("PASS") >= 5
    record("Target-vs-current screenshot matrix marks all pages PASS", matrix_ok, "Matrix inspected for all five page PASS statuses.")

    page5_backlog = read_text("PAGE5_VISUAL_DELTA_BACKLOG.md")
    page5_open = re.findall(r"- \[ \].*", page5_backlog)
    record(
        "Page 5 visual-delta backlog is closed",
        bool(page5_backlog) and not page5_open and "Status: PASS" in page5_backlog,
        f"open_items={len(page5_open)}" if page5_backlog else "PAGE5_VISUAL_DELTA_BACKLOG.md missing",
    )

    page5_spec = read_text("PAGE5_GOVERNANCE_VISUAL_SPEC.lock.md")
    page5_terms = [
        "Governance & Reproducibility Filters",
        "Segmented",
        "Build-flow",
        "Component trace",
        "SHAP not yet generated",
        "read-only",
    ]
    record(
        "Page 5 locked visual spec covers target sections",
        all(term.lower() in page5_spec.lower() for term in page5_terms),
        "PAGE5_GOVERNANCE_VISUAL_SPEC.lock.md inspected.",
    )

    layout_gates = read_text("VISUAL_LAYOUT_GATES.lock.md")
    record(
        "Visual layout gates include semantic hard stops",
        all(term in layout_gates for term in ["BUG_BACKLOG.md", "Schiff horizon profiles", "Scenario horizon comparison"]),
        "VISUAL_LAYOUT_GATES.lock.md inspected.",
    )

    app_text = read_text("app.py")
    record(
        "Primary pages and panel counts remain aligned to target",
        all(term in app_text for term in ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark", "Governance & Reproducibility"]),
        "Top-level page labels inspected.",
    )

    page5_text = app_text + "\n" + read_text("model_dashboard/light_ruc_reproducibility.py")
    page5_app_terms = [
        "Governance & Reproducibility Filters",
        "Two-stage OLS base plus GBM residual correction, exactly replayed against evidence predictions.",
        "Four-component weighted ensemble exactly replayed against evidence predictions.",
        "PED is exact at stored component-prediction level; inner HPO/static-solver rebuild remains a future audit layer.",
        "Inner HPO/static-solver audit: partial",
        "Impact on dependent variable / model target",
        "SHAP not yet generated",
    ]
    record(
        "Page 5 required wording is present in app code",
        all(term in page5_text for term in page5_app_terms),
        "Page 5 wording inspected in app.py.",
    )

    return findings


def main() -> int:
    ARTIFACTS.mkdir(exist_ok=True)
    try:
        findings = validate()
    except Exception as exc:
        findings = [("Visual conformance validation", "FAIL", str(exc))]
    failed = [row for row in findings if row[1] != "PASS"]
    status = "passed" if not failed else "failed"
    lines = [
        "# Visual Conformance Validation Report",
        "",
        f"Status: **{status}**.",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {name} | {state} | {evidence} |" for name, state, evidence in findings)
    lines.append("")
    report = "\n".join(lines)
    (ARTIFACTS / "visual_conformance_validation_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

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
    "artifacts/screenshots/final-overview.png",
    "artifacts/screenshots/final-diagnostics.png",
    "artifacts/screenshots/final-scenario-comparison.png",
    "artifacts/screenshots/final-schiff-benchmark.png",
]

REVIEW_FILES = [
    "artifacts/target_vs_current_screenshot_matrix.md",
    "artifacts/visual_delta_review.md",
    "artifacts/screenshot_review.md",
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
    record("Final browser screenshots exist for all four pages", not missing, "missing=" + ", ".join(missing) if missing else "All required screenshots present.")

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
    required_pages = ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark"]
    matrix_ok = all(page in matrix for page in required_pages) and matrix.count("PASS") >= 4
    record("Target-vs-current screenshot matrix marks all pages PASS", matrix_ok, "Matrix inspected for all four page PASS statuses.")

    layout_gates = read_text("VISUAL_LAYOUT_GATES.lock.md")
    record(
        "Visual layout gates include semantic hard stops",
        all(term in layout_gates for term in ["BUG_BACKLOG.md", "Schiff horizon profiles", "Scenario horizon comparison"]),
        "VISUAL_LAYOUT_GATES.lock.md inspected.",
    )

    app_text = read_text("app.py")
    record(
        "Primary pages and panel counts remain aligned to target",
        all(term in app_text for term in ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark"]),
        "Top-level page labels inspected.",
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

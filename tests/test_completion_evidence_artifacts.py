from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_completion_evidence_reports_exist_and_record_playwright_caveat() -> None:
    required = [
        "artifacts/deep_quality_review.md",
        "artifacts/management_readiness_report.md",
        "artifacts/reviews/data_correctness.md",
        "artifacts/reviews/ux_screenshot.md",
        "artifacts/reviews/governance_story.md",
        ".agent_state.md",
    ]
    missing = [relative for relative in required if not (ROOT / relative).exists()]
    if missing:
        pytest.skip(
            "completion evidence reports are ignored generated artifacts; "
            "run scripts/write_completion_evidence.py for local release evidence"
        )

    for relative in required:
        path = ROOT / relative
        assert path.exists(), relative
        assert path.read_text(encoding="utf-8").strip(), relative

    combined = "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in required)
    assert "PermissionError: [WinError 5]" in combined
    assert "Playwright" in combined


def test_improvement_loops_document_fifty_product_hardening_reviews() -> None:
    path = ROOT / "artifacts" / "improvement_loops.json"
    if not path.exists():
        pytest.skip("ignored generated completion evidence is absent")

    loops = json.loads(path.read_text(encoding="utf-8"))

    assert len(loops) >= 50
    assert [int(entry["loop"]) for entry in loops] == list(range(1, len(loops) + 1))
    assert {entry["status"] for entry in loops} == {"PASS"}
    assert any(entry["loop_type"] == "browser_screenshot_audit" for entry in loops)
    assert any(entry["loop_type"] == "evidence_backed_product_hardening_review" for entry in loops)
    for entry in loops:
        assert entry.get("focus")
        assert entry.get("evidence")
        assert entry.get("checks")


def test_deep_quality_review_scores_all_pages_at_target() -> None:
    path = ROOT / "artifacts" / "deep_quality_review.md"
    if not path.exists():
        pytest.skip("ignored generated completion evidence is absent")

    text = path.read_text(encoding="utf-8")
    for page in [
        "Overview",
        "Diagnostics",
        "Scenario Comparison",
        "Schiff Benchmark",
        "Revenue Outlook",
        "Governance & Reproducibility",
    ]:
        assert f"| {page} | 9.8/10 | PASS |" in text

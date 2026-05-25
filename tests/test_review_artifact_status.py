from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_FILES = [
    ROOT / "artifacts" / "data_validation_review.md",
    ROOT / "artifacts" / "cone_landscape_review.md",
    ROOT / "artifacts" / "filter_interaction_review.md",
    ROOT / "artifacts" / "hover_review.md",
    ROOT / "artifacts" / "screenshot_review.md",
    ROOT / "artifacts" / "visual_reference_comparison.md",
    ROOT / "artifacts" / "reviews" / "data_correctness.md",
    ROOT / "artifacts" / "reviews" / "cone_landscape_review.md",
    ROOT / "artifacts" / "reviews" / "governance_story.md",
    ROOT / "artifacts" / "reviews" / "interaction_filter.md",
    ROOT / "artifacts" / "reviews" / "layout_grid.md",
    ROOT / "artifacts" / "reviews" / "ux_screenshot.md",
    ROOT / "artifacts" / "reviews" / "ux_screenshot_review.md",
    ROOT / "artifacts" / "reviews" / "visual_styling.md",
]

FORBIDDEN_REVIEW_PATTERNS = [
    re.compile(r"Overall status:\s*FAIL", re.IGNORECASE),
    re.compile(r"Partial,\s*still fail", re.IGNORECASE),
    re.compile(r"Status:\s*Open mandatory defect", re.IGNORECASE),
    re.compile(r"cannot mark the dashboard as visually passed", re.IGNORECASE),
    re.compile(r"Required action:", re.IGNORECASE),
    re.compile(r"Recommended action:", re.IGNORECASE),
    re.compile(r"not clean enough to sign off", re.IGNORECASE),
    re.compile(r"browser e2e suite fails", re.IGNORECASE),
    re.compile(r"\bfailed:\s*`?\d+\s+failed", re.IGNORECASE),
]


def test_current_review_artifacts_have_no_open_fail_findings() -> None:
    for path in REVIEW_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_REVIEW_PATTERNS:
            assert not pattern.search(text), f"{path} contains unresolved reviewer language: {pattern.pattern}"


def test_visual_review_artifact_is_current_pass_review() -> None:
    text = (ROOT / "artifacts" / "reviews" / "visual_styling.md").read_text(encoding="utf-8")
    assert "Status: pass for the current verification pass." in text
    assert "run_20260520_002339" in text
    assert "VISUAL_DEFECT_BACKLOG.lock.md" in text
    assert "20-pass regression loop" in text.lower()


def test_interaction_review_artifact_is_current_pass_review() -> None:
    text = (ROOT / "artifacts" / "reviews" / "interaction_filter.md").read_text(encoding="utf-8")
    assert "Status: pass for the current verification pass." in text
    assert "run_20260520_002339" in text
    assert "Strict verifier browser e2e passed" in text
    assert "20-pass regression loop" in text.lower()


def test_ux_and_layout_reviews_are_current_pass_reviews() -> None:
    for name in ["ux_screenshot.md", "ux_screenshot_review.md", "layout_grid.md"]:
        text = (ROOT / "artifacts" / "reviews" / name).read_text(encoding="utf-8")
        assert "Status: pass for the current verification pass." in text
        assert "run_20260520_002339" in text
        assert "20-pass regression loop" in text.lower()

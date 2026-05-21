from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCKED_BACKLOGS = [
    ROOT / "BUG_BACKLOG.md",
    ROOT / "VISUAL_DEFECT_BACKLOG.lock.md",
    ROOT / "FILTER_AND_HOVER_DEFECTS.lock.md",
    ROOT / "PERF_DEFECT_BACKLOG.lock.md",
]


def test_locked_backlogs_have_no_unchecked_items() -> None:
    for path in LOCKED_BACKLOGS:
        text = path.read_text(encoding="utf-8")
        assert "[ ]" not in text, f"{path} still has unchecked backlog items"


def test_locked_backlogs_name_closure_evidence() -> None:
    for path in LOCKED_BACKLOGS:
        text = path.read_text(encoding="utf-8").lower()
        assert "complete" in text or "closed" in text or "pass" in text, (
            f"{path} should include closure evidence, not only unchecked task text"
        )

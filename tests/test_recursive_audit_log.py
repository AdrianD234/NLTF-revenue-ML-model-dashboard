from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOOP_LOG = ROOT / "artifacts" / "recursive_audit_loops.json"
REQUIRED_FIELDS = {
    "loop",
    "timestamp",
    "defect_targeted",
    "files_changed",
    "tests_added_or_strengthened",
    "data_check_result",
    "browser_check_result",
    "screenshot_evidence",
    "remaining_defects",
}


def test_recursive_audit_entries_are_verified_not_pending() -> None:
    loops = json.loads(LOOP_LOG.read_text(encoding="utf-8"))
    assert loops, "Recursive audit loop log must not be empty"
    assert len(loops) >= 20, "Recursive audit loop log must document at least 20 loops"
    for entry in loops:
        missing = REQUIRED_FIELDS.difference(entry)
        assert not missing, f"Loop {entry.get('loop')} missing fields: {sorted(missing)}"
        data_result = str(entry["data_check_result"]).lower()
        browser_result = str(entry["browser_check_result"]).lower()
        assert "pending" not in data_result
        assert "pending" not in browser_result
        assert "passed" in data_result
        assert "passed" in browser_result


def test_recursive_audit_loop_numbers_are_contiguous() -> None:
    loops = json.loads(LOOP_LOG.read_text(encoding="utf-8"))
    observed = [int(entry["loop"]) for entry in loops]
    assert observed == list(range(1, len(observed) + 1))


def test_recursive_audit_screenshot_evidence_paths_exist() -> None:
    loops = json.loads(LOOP_LOG.read_text(encoding="utf-8"))
    root = LOOP_LOG.parents[1]
    for entry in loops:
        evidence = entry["screenshot_evidence"]
        assert evidence, f"Loop {entry['loop']} has no screenshot evidence paths"
        for relative in evidence:
            path = root / relative
            assert path.exists(), f"Loop {entry['loop']} screenshot evidence is missing: {relative}"

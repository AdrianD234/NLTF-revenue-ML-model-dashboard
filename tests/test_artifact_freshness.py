from __future__ import annotations

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
LATEST_RUN_NAME = "run_20260520_002339"
OLD_BALANCED_RUN_NAME = "run_20260519_085639"
OLD_BALANCED_PARENT = "autogluon_balanced_test"


CURRENT_EVIDENCE_FILES = [
    ROOT / "artifacts" / "management_readiness_report.md",
    ROOT / "artifacts" / "performance_review.md",
    ROOT / "artifacts" / "test_summary.md",
    ROOT / "artifacts" / "data_validation_review.md",
    ROOT / "artifacts" / "reviews" / "data_correctness.md",
    ROOT / ".agent_state.md",
]

CURRENT_DOC_FILES = [
    ROOT / "README.md",
]

CURRENT_PERFORMANCE_FILES = [
    ROOT / "artifacts" / "performance_review.md",
    ROOT / "artifacts" / "performance_improvement_loops.json",
]

CURRENT_PERFORMANCE_BASELINE = ROOT / "artifacts" / "performance_baseline.json"
CURRENT_PERFORMANCE_LATEST = ROOT / "artifacts" / "performance_latest.json"
CURRENT_PERFORMANCE_HISTORY = ROOT / "artifacts" / "performance_history.json"


def test_current_evidence_artifacts_name_latest_arbitration_run() -> None:
    for path in CURRENT_EVIDENCE_FILES:
        text = path.read_text(encoding="utf-8")
        assert LATEST_RUN_NAME in text, f"{path} does not name the latest arbitration run"


def test_current_evidence_artifacts_do_not_claim_old_run_as_current() -> None:
    forbidden_phrases = [
        f"Validation run: `C:\\Users\\Adrian Desilvestro\\OneDrive\\Documents\\Playground\\Revenue Modeling - Strategic Review\\04 Models\\Inputs\\{OLD_BALANCED_PARENT}\\{OLD_BALANCED_RUN_NAME}`",
        f"Configured run: `{OLD_BALANCED_RUN_NAME}`",
        f"Active run: C:\\Users\\Adrian Desilvestro\\OneDrive\\Documents\\Playground\\Revenue Modeling - Strategic Review\\04 Models\\Inputs\\{OLD_BALANCED_PARENT}\\{OLD_BALANCED_RUN_NAME}",
    ]
    for path in CURRENT_EVIDENCE_FILES:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden_phrases:
            assert phrase not in text, f"{path} still claims the old balanced run as current"


def test_screenshot_directory_contains_only_visual_evidence() -> None:
    screenshot_dir = ROOT / "artifacts" / "screenshots"
    non_visual = [
        path.name
        for path in screenshot_dir.iterdir()
        if path.is_file() and path.suffix.lower() not in {".png", ".jpg", ".jpeg"}
    ]
    assert non_visual == [], (
        "Non-image files in artifacts/screenshots can be mistaken for current visual evidence: "
        + ", ".join(non_visual)
    )


def test_public_docs_do_not_name_old_balanced_run_as_validation_run() -> None:
    forbidden = f"used for validation is:\n\n```text\nC:\\Users\\Adrian Desilvestro\\OneDrive\\Documents\\Playground\\Revenue Modeling - Strategic Review\\04 Models\\Inputs\\{OLD_BALANCED_PARENT}\\{OLD_BALANCED_RUN_NAME}"
    for path in CURRENT_DOC_FILES:
        text = path.read_text(encoding="utf-8")
        assert LATEST_RUN_NAME in text, f"{path} does not name the latest arbitration run"
        assert forbidden not in text, f"{path} still presents the older balanced run as the validation run"


def test_performance_evidence_does_not_point_to_old_run() -> None:
    for path in CURRENT_PERFORMANCE_FILES:
        text = path.read_text(encoding="utf-8")
        assert OLD_BALANCED_RUN_NAME not in text, f"{path} still names the old run in active performance evidence"


def test_performance_baseline_uses_latest_arbitration_run() -> None:
    text = CURRENT_PERFORMANCE_BASELINE.read_text(encoding="utf-8")
    assert LATEST_RUN_NAME in text, "performance_baseline.json should describe the current latest-run baseline"
    assert OLD_BALANCED_RUN_NAME not in text, "performance_baseline.json still points at the old balanced run"


def test_latest_performance_measurement_uses_latest_arbitration_run() -> None:
    latest = json.loads(CURRENT_PERFORMANCE_LATEST.read_text(encoding="utf-8"))
    history = json.loads(CURRENT_PERFORMANCE_HISTORY.read_text(encoding="utf-8"))
    assert LATEST_RUN_NAME in latest["run_dir"]
    assert OLD_BALANCED_RUN_NAME not in latest["run_dir"]
    assert history, "performance_history.json must retain at least one benchmark entry"
    assert LATEST_RUN_NAME in history[-1]["run_dir"]
    assert OLD_BALANCED_RUN_NAME not in history[-1]["run_dir"]

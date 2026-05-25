from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generated_artifacts_are_ignored_by_git() -> None:
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "artifacts/**" in ignore_text
    assert "!artifacts/.gitkeep" in ignore_text
    assert "data/**" in ignore_text
    assert "!tests/fixtures/**/*.parquet" in ignore_text


def test_runtime_code_and_verifiers_do_not_hardcode_user_roots() -> None:
    scanned = [
        ROOT / "app.py",
        ROOT / "model_dashboard",
        ROOT / "scripts",
    ]
    allowed = {
        ROOT / "config" / "defaults.py",
        ROOT / ".env.example",
    }
    offenders: list[str] = []
    for base in scanned:
        paths = [base] if base.is_file() else list(base.rglob("*"))
        for path in paths:
            if not path.is_file() or path in allowed or path.suffix.lower() not in {".py", ".ps1"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "C:\\Users\\Adrian" in text or "OneDrive\\Documents\\Playground" in text:
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_agent_state_does_not_claim_completion_during_cleanup_goal() -> None:
    text = (ROOT / ".agent_state.md").read_text(encoding="utf-8")

    assert "Status: IN PROGRESS" in text
    assert "Status: COMPLETE" not in text

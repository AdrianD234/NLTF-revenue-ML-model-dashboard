from __future__ import annotations

from pathlib import Path

from model_dashboard.data.locate import candidate_search_roots, locate_dashboard_file


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


def test_parquet_schema_normalisation_lives_in_data_transforms() -> None:
    loader_text = (ROOT / "model_dashboard" / "data_loader.py").read_text(encoding="utf-8")
    transform_text = (ROOT / "model_dashboard" / "data" / "transforms.py").read_text(encoding="utf-8")

    assert "def normalise_parquet_candidate" not in loader_text
    assert "CORE_PARQUET_COLUMNS = [" not in loader_text
    assert "def normalise_parquet_candidate" in transform_text
    assert "CORE_PARQUET_COLUMNS = [" in transform_text


def test_diagnostic_loading_lives_in_data_diagnostics() -> None:
    loader_text = (ROOT / "model_dashboard" / "data_loader.py").read_text(encoding="utf-8")
    diagnostic_text = (ROOT / "model_dashboard" / "data" / "diagnostics.py").read_text(encoding="utf-8")

    assert "def _load_diagnostic_audit_tables" not in loader_text
    assert "def _diagnostic_frame" not in loader_text
    assert "def build_diagnostic_acf_source_table" not in loader_text
    assert "def load_diagnostic_audit_tables" in diagnostic_text
    assert "def build_diagnostic_frame" in diagnostic_text
    assert "def build_diagnostic_acf_source_table" in diagnostic_text


def test_governed_file_discovery_does_not_use_generated_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    artifact_dir = repo / "artifacts" / "curated_data"
    artifact_dir.mkdir(parents=True)
    artifact_only_name = "stale_generated_artifact_only.csv"
    (artifact_dir / artifact_only_name).write_text("stale,artifact\n", encoding="utf-8")
    (repo / "data").mkdir(parents=True)

    roots = candidate_search_roots(repo / "data", repo)

    assert repo not in roots
    assert locate_dashboard_file(artifact_only_name, roots) is None


def test_agent_state_does_not_claim_completion_during_cleanup_goal() -> None:
    text = (ROOT / ".agent_state.md").read_text(encoding="utf-8")

    assert "Status: IN PROGRESS" in text
    assert "Status: COMPLETE" not in text

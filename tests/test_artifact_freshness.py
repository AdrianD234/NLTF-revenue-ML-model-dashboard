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


def test_parquet_dashboard_orchestration_lives_in_data_parquet_loader() -> None:
    loader_text = (ROOT / "model_dashboard" / "data_loader.py").read_text(encoding="utf-8")
    parquet_loader_text = (ROOT / "model_dashboard" / "data" / "parquet_loader.py").read_text(encoding="utf-8")

    assert "def load_parquet_dashboard" not in loader_text
    assert "def _build_dashboard_frames" not in loader_text
    assert "def _select_current_finalists" not in loader_text
    assert "def _pure_schiff_rows" not in loader_text
    assert "def _stress_frame" not in loader_text
    assert "def _horizon_frame" not in loader_text
    assert "def _ensemble_frame" not in loader_text
    assert "def load_parquet_dashboard" in parquet_loader_text
    assert "def _build_dashboard_frames" in parquet_loader_text
    assert "def _select_current_finalists" in parquet_loader_text
    assert "def _pure_schiff_rows" in parquet_loader_text
    assert "def _stress_frame" in parquet_loader_text
    assert "def _horizon_frame" in parquet_loader_text
    assert "def _ensemble_frame" in parquet_loader_text


def test_legacy_review_loading_lives_in_data_legacy_loader() -> None:
    loader_text = (ROOT / "model_dashboard" / "data_loader.py").read_text(encoding="utf-8")
    legacy_text = (ROOT / "model_dashboard" / "data" / "legacy_loader.py").read_text(encoding="utf-8")

    assert "def load_run" not in loader_text
    assert "def load_curated_run" not in loader_text
    assert "def discover_run_folders" not in loader_text
    assert "def _read_tabular_dataset" not in loader_text
    assert "def load_run" in legacy_text
    assert "def load_curated_run" in legacy_text
    assert "def discover_run_folders" in legacy_text
    assert "def _read_tabular_dataset" in legacy_text
    assert "legacy_run_folder_review" in legacy_text
    assert "Legacy run-folder CSV/XLSX loading is available only for review" in legacy_text


def test_chart_source_builders_live_in_data_chart_sources() -> None:
    old_text = (ROOT / "model_dashboard" / "chart_sources.py").read_text(encoding="utf-8")
    data_text = (ROOT / "model_dashboard" / "data" / "chart_sources.py").read_text(encoding="utf-8")

    assert "def build_chart_source_tables" not in old_text
    assert "def write_chart_source_tables" not in old_text
    assert "def _overview_finalist_accuracy" not in old_text
    assert "def _diagnostics_acf" not in old_text
    assert "def build_chart_source_tables" in data_text
    assert "def write_chart_source_tables" in data_text
    assert "def _overview_finalist_accuracy" in data_text
    assert "def _diagnostics_acf" in data_text
    assert "CHART_SOURCE_FILES = {" in data_text


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


def test_fixture_fallback_does_not_mix_with_explicit_external_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    explicit_root = tmp_path / "external_pack"
    fixture_root = repo / "tests" / "fixtures" / "mini_parquet"
    explicit_root.mkdir(parents=True)
    fixture_root.mkdir(parents=True)
    (fixture_root / "quarterly_predictions_selected.csv").write_text("fixture,row\n", encoding="utf-8")

    roots = candidate_search_roots(explicit_root, repo)

    assert fixture_root not in roots
    assert locate_dashboard_file("quarterly_predictions_selected.csv", roots) is None


def test_agent_state_does_not_claim_completion_during_cleanup_goal() -> None:
    text = (ROOT / ".agent_state.md").read_text(encoding="utf-8")

    assert "Status: IN PROGRESS" in text
    assert "Status: COMPLETE" not in text

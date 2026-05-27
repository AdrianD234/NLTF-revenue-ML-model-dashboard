from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "dashboard_evidence_pack"
MAX_FILE_BYTES = 50 * 1024 * 1024
REQUIRED_RUNTIME_DEPS = {"streamlit", "pandas", "plotly", "pyarrow", "openpyxl", "pillow"}
DEV_ONLY_DEPS = {"pytest", "playwright", "pytest-playwright", "kaleido"}
REQUIRED_PARQUET = {
    "candidate_cone.parquet",
    "finalists.parquet",
    "schiff_benchmark.parquet",
    "ensemble_components.parquet",
    "residual_predictions.parquet",
    "horizon_profiles.parquet",
    "stress_horizon.parquet",
    "scenario_comparison.parquet",
    "diagnostic_tests.parquet",
    "diagnostic_pass_matrix.parquet",
    "diagnostic_acf.parquet",
    "error_distribution.parquet",
    "annual_predictions.parquet",
    "chart_contract.parquet",
}
ALLOWED_PACK_ROOT_FILES = {"manifest.json", "README.md", "data_inventory.csv"}
ALLOWED_REQUIREMENTS_SUFFIXES = {".txt"}
REQUIRED_UI_EXPORTS = {
    "chart_card",
    "dataframe_download",
    "decision_brief",
    "display_table",
    "footer_strip",
    "header",
    "html_chart_card",
    "info_panel",
    "inject_theme",
    "kpi_grid",
    "section_title",
    "warning_panel",
    "filter_summary_grid",
    "gov_kpi_grid",
    "governance_cards",
}


def normalise_requirement(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    for marker in ["==", ">=", "<=", "~=", ">", "<", "[", ";"]:
        if marker in line:
            line = line.split(marker, 1)[0]
    return line.strip().lower().replace("_", "-")


def read_requirements(path: Path) -> set[str]:
    if not path.exists():
        raise AssertionError(f"Missing {path.name}.")
    deps = {dep for dep in (normalise_requirement(line) for line in path.read_text(encoding="utf-8").splitlines()) if dep}
    if not deps:
        raise AssertionError(f"{path.name} is empty.")
    return deps


def git_tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
            check=True,
            capture_output=True,
        )
    except Exception:
        return []
    return [ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def assert_pack_shape() -> None:
    if not PACK_ROOT.exists():
        raise AssertionError(f"Missing evidence pack folder: {PACK_ROOT}")
    if not (PACK_ROOT / "manifest.json").exists():
        raise AssertionError("Evidence pack manifest.json is missing.")
    data_dir = PACK_ROOT / "data"
    if not data_dir.is_dir():
        raise AssertionError("Evidence pack data/ folder is missing.")
    missing = sorted(name for name in REQUIRED_PARQUET if not (data_dir / name).exists())
    if missing:
        raise AssertionError("Evidence pack is missing required Parquet files: " + ", ".join(missing))
    forbidden_dirs = [PACK_ROOT / name for name in ["sources", "tables_csv", "logs", "screenshots"] if (PACK_ROOT / name).exists()]
    if forbidden_dirs:
        raise AssertionError("Evidence pack contains forbidden raw-output directories: " + ", ".join(str(path) for path in forbidden_dirs))
    forbidden_files: list[str] = []
    for path in PACK_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(PACK_ROOT)
        allowed = (
            (len(rel.parts) == 1 and rel.name in ALLOWED_PACK_ROOT_FILES)
            or rel.parts[0] == "docs"
            or (rel.parts[0] == "data" and rel.suffix == ".parquet")
        )
        if not allowed:
            forbidden_files.append(str(rel))
        if path.stat().st_size > MAX_FILE_BYTES:
            forbidden_files.append(f"{rel} exceeds 50 MB")
    if forbidden_files:
        raise AssertionError("Evidence pack contains forbidden files: " + ", ".join(forbidden_files))


def assert_requirements() -> None:
    runtime = read_requirements(ROOT / "requirements.txt")
    missing = REQUIRED_RUNTIME_DEPS - runtime
    dev_leaks = runtime & DEV_ONLY_DEPS
    unexpected = runtime - REQUIRED_RUNTIME_DEPS
    if missing:
        raise AssertionError("requirements.txt is missing runtime dependencies: " + ", ".join(sorted(missing)))
    if dev_leaks:
        raise AssertionError("requirements.txt includes dev-only dependencies: " + ", ".join(sorted(dev_leaks)))
    if unexpected:
        raise AssertionError("requirements.txt contains non-runtime dependencies: " + ", ".join(sorted(unexpected)))
    dev = read_requirements(ROOT / "requirements-dev.txt")
    missing_dev = DEV_ONLY_DEPS - dev
    if missing_dev:
        raise AssertionError("requirements-dev.txt is missing dev dependencies: " + ", ".join(sorted(missing_dev)))


def assert_streamlit_config() -> None:
    config_path = ROOT / ".streamlit" / "config.toml"
    if not config_path.exists():
        return
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    server = config.get("server", {})
    if isinstance(server, dict) and "port" in server:
        raise AssertionError(".streamlit/config.toml must not force [server].port for Streamlit Cloud.")


def assert_default_load_resolves_repo_pack() -> None:
    for name in ["DASHBOARD_EVIDENCE_PACK_ROOT", "STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT"]:
        os.environ.pop(name, None)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from model_dashboard.data.config import DEFAULT_EVIDENCE_PACK_ROOT
    from model_dashboard.evidence_pack import resolve_evidence_pack_root

    expected = (ROOT / "data" / "dashboard_evidence_pack").resolve()
    default_root = (ROOT / DEFAULT_EVIDENCE_PACK_ROOT).resolve()
    resolved = resolve_evidence_pack_root(default_root).resolve()
    if resolved != expected:
        raise AssertionError(f"Default evidence-pack root resolves to {resolved}, expected {expected}.")


def assert_import_surface() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import app
    import model_dashboard.ui as ui

    if not hasattr(app, "main"):
        raise AssertionError("app.py imported, but main() is missing.")
    missing = sorted(name for name in REQUIRED_UI_EXPORTS if not hasattr(ui, name))
    if missing:
        raise AssertionError("model_dashboard.ui is missing exports imported by app.py: " + ", ".join(missing))


def assert_tracked_files() -> None:
    tracked = git_tracked_files()
    if not tracked:
        return
    oversized = [str(path.relative_to(ROOT)) for path in tracked if path.exists() and path.stat().st_size > MAX_FILE_BYTES]
    if oversized:
        raise AssertionError("Tracked files exceed 50 MB: " + ", ".join(oversized))
    forbidden: list[str] = []
    for path in tracked:
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("data/dashboard_evidence_pack/"):
            pack_rel = Path(rel).relative_to("data/dashboard_evidence_pack")
            allowed = (
                (len(pack_rel.parts) == 1 and pack_rel.name in ALLOWED_PACK_ROOT_FILES)
                or pack_rel.parts[0] == "docs"
                or (pack_rel.parts[0] == "data" and pack_rel.suffix == ".parquet")
            )
            if not allowed:
                forbidden.append(rel)
        if "/sources/" in f"/{rel}/" or "/tables_csv/" in f"/{rel}/":
            forbidden.append(rel)
        if rel.startswith("data/dashboard_evidence_pack/") and path.suffix.lower() in {".xlsx", ".xls", ".csv"} and path.name != "data_inventory.csv":
            forbidden.append(rel)
    if forbidden:
        raise AssertionError("Forbidden raw/mirror files are tracked: " + ", ".join(sorted(set(forbidden))))


def validate() -> None:
    if not (ROOT / "app.py").exists():
        raise AssertionError("Missing app.py.")
    assert_requirements()
    assert_import_surface()
    assert_pack_shape()
    assert_streamlit_config()
    assert_default_load_resolves_repo_pack()
    assert_tracked_files()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Streamlit Cloud deployment readiness.")
    parser.parse_args()
    try:
        validate()
    except Exception as exc:
        print(f"Streamlit deploy readiness: FAIL - {exc}")
        return 1
    print("Streamlit deploy readiness: PASS")
    print(f"Repo: {ROOT}")
    print(f"Main file path: {ROOT / 'app.py'}")
    print(f"Bundled evidence pack: {PACK_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

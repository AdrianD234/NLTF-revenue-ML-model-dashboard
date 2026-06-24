from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "dashboard_evidence_pack"
MAX_FILE_BYTES = 50 * 1024 * 1024
REQUIRED_RUNTIME_DEPS = {"streamlit", "pandas", "numpy", "plotly", "pyarrow", "openpyxl", "pillow", "scikit-learn"}
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
REQUIRED_REPRODUCIBILITY_IMPORT_EXPORTS = {
    "PED_INNER_HPO_AUDIT_STATUS",
    "R2_GOVERNANCE_INFO_TEXT",
    "R2_LADDER_NOTE",
    "R2_LADDER_TITLE",
    "R2_TRAINING_FIT_NOTE",
    "load_ped_inner_hpo_audit_pack",
    "ped_inner_hpo_audit_signature",
    "ped_inner_hpo_audit_summary",
    "ped_inner_hpo_gap_register_view",
    "ped_inner_hpo_nested_trace_view",
    "ped_inner_hpo_weight_detail_view",
    "ped_inner_hpo_weight_source_view",
    "reproducibility_coefficients_view",
    "reproducibility_component_trace_view",
    "reproducibility_feature_importance_view",
    "reproducibility_ensemble_equation",
    "reproducibility_ensemble_weight_view",
    "reproducibility_annual_view",
    "reproducibility_horizon_view",
    "reproducibility_pack_signature",
    "reproducibility_registry_view",
    "reproducibility_replay_summary",
    "reproducibility_sensitivity_view",
    "reproducibility_scorecard_view",
    "reproducibility_stress_view",
    "reproducibility_stream_labels",
    "reproducibility_training_window_view",
    "load_reproducibility_pack",
    "plot_reproducibility_feature_importance",
    "plot_reproducibility_sensitivities",
    "diagnostics_r2_summary_frame",
    "reproducibility_component_r2_frame",
    "r2_ladder_summary_frame",
    "r2_ladder_frames",
    "format_r2",
}
REQUIRED_FORECAST_IMPORT_EXPORTS = {
    "FORECAST_BUILDER_NOTE",
    "FORECAST_BUILDER_TITLE",
    "FORECAST_RUNNER_IMPORT_ERROR",
    "TEMPLATE_FILENAME",
    "build_forecast_input_template_bytes",
    "forecast_pack_zip_bytes",
    "quarter_sort_key",
    "run_forecast_workbook",
    "sanitize_scenario_name",
    "scenario_name_from_filename",
    "validate_forecast_workbook",
    "write_forecast_scenario_comparison",
}
R2_LADDER_DEP_FALLBACK_ENV = "NLTF_FORCE_R2_LADDER_DEP_FALLBACK"
EXPECTED_IMPORT_SURFACE_REVISION = "2026-06-24-revenue-source-pack-v1"
REVENUE_SOURCE_PACK_ROOT = ROOT / "data" / "revenue_model_source_pack" / "2026_05_19"
REQUIRED_REVENUE_SOURCE_PACK_FILES = {
    "README.md",
    "MODEL_WORKFLOW.md",
    "manifest.json",
    "series_master.csv",
    "aggregation_rules.csv",
    "front_end_config.json",
    "unresolved_decisions.csv",
    "annual_actuals.csv",
    "annual_model_paths.csv",
    "release_registry.csv",
    "canonical_revenue_long.csv",
    "source_pack_intake_status.csv",
    "path_trace_status.csv",
    "reconciliation_report.csv",
    "source_gap_register.csv",
    "remaining_decisions_handoff.csv",
    "series_role_audit.csv",
    "validation_issues.csv",
    "loader_exports_manifest.json",
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


def assert_revenue_source_pack_shape() -> None:
    if not REVENUE_SOURCE_PACK_ROOT.exists():
        raise AssertionError(f"Missing revenue source pack folder: {REVENUE_SOURCE_PACK_ROOT}")
    missing = sorted(name for name in REQUIRED_REVENUE_SOURCE_PACK_FILES if not (REVENUE_SOURCE_PACK_ROOT / name).exists())
    if missing:
        raise AssertionError("Revenue source pack is missing files: " + ", ".join(missing))
    for path in REVENUE_SOURCE_PACK_ROOT.rglob("*"):
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES:
            raise AssertionError(f"Revenue source pack file exceeds 50 MB: {path}")
    manifest_text = (REVENUE_SOURCE_PACK_ROOT / "manifest.json").read_text(encoding="utf-8")
    loader_text = (REVENUE_SOURCE_PACK_ROOT / "loader_exports_manifest.json").read_text(encoding="utf-8")
    for token in ["C:\\Users", "Downloads", "OneDrive"]:
        if token in manifest_text or token in loader_text:
            raise AssertionError(f"Revenue source pack exposes local path token: {token}")
    manifest = json.loads(manifest_text)
    if manifest.get("raw_workbook", {}).get("sha256") != "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b":
        raise AssertionError("Revenue source pack raw workbook SHA256 is not the governed value.")
    loader_manifest = json.loads(loader_text)
    if loader_manifest.get("validation_status") not in {"passed", "warning"}:
        raise AssertionError("Revenue source pack loader exports are not validation-ready.")


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
    import model_dashboard.forecast_imports as forecast_imports
    import model_dashboard.reproducibility_imports as reproducibility_imports
    import model_dashboard.revenue_source_pack as revenue_source_pack
    import model_dashboard.ui as ui

    if not hasattr(app, "main"):
        raise AssertionError("app.py imported, but main() is missing.")
    revision = getattr(app, "STREAMLIT_IMPORT_SURFACE_REVISION", None)
    if revision != EXPECTED_IMPORT_SURFACE_REVISION:
        raise AssertionError(
            f"app.py import surface revision is {revision!r}, expected {EXPECTED_IMPORT_SURFACE_REVISION!r}."
        )
    missing = sorted(name for name in REQUIRED_UI_EXPORTS if not hasattr(ui, name))
    if missing:
        raise AssertionError("model_dashboard.ui is missing exports imported by app.py: " + ", ".join(missing))
    missing_repro = sorted(name for name in REQUIRED_REPRODUCIBILITY_IMPORT_EXPORTS if not hasattr(reproducibility_imports, name))
    if missing_repro:
        raise AssertionError("model_dashboard.reproducibility_imports is missing app.py exports: " + ", ".join(missing_repro))
    missing_forecast = sorted(name for name in REQUIRED_FORECAST_IMPORT_EXPORTS if not hasattr(forecast_imports, name))
    if missing_forecast:
        raise AssertionError("model_dashboard.forecast_imports is missing app.py exports: " + ", ".join(missing_forecast))
    if not hasattr(revenue_source_pack, "load_revenue_source_pack"):
        raise AssertionError("model_dashboard.revenue_source_pack is missing load_revenue_source_pack.")


def assert_app_uses_cloud_safe_reproducibility_wrapper() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    if "from model_dashboard.r2_ladder import" in app_source:
        raise AssertionError("app.py must import R2 ladder symbols through model_dashboard.reproducibility_imports for Streamlit Cloud.")
    if "from model_dashboard.reproducibility_imports import" not in app_source:
        raise AssertionError("app.py is missing the Streamlit Cloud-safe reproducibility import wrapper.")


def assert_app_uses_cloud_safe_forecast_wrapper() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    if "from model_dashboard.forecast_runner import" in app_source:
        raise AssertionError("app.py must import Forecast Builder symbols through model_dashboard.forecast_imports for Streamlit Cloud.")
    if "from model_dashboard.forecast_imports import" not in app_source:
        raise AssertionError("app.py is missing the Streamlit Cloud-safe Forecast Builder import wrapper.")


def assert_startup_import_subprocess(
    *,
    force_optional_fallback: bool = False,
    force_forecast_fallback: bool = False,
) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("STAGE1_REQUIRE_FRONTEND_INTERACTIONS", None)
    if force_optional_fallback:
        env["NLTF_FORCE_REPRODUCIBILITY_IMPORT_FALLBACK"] = "1"
    else:
        env.pop("NLTF_FORCE_REPRODUCIBILITY_IMPORT_FALLBACK", None)
    if force_forecast_fallback:
        env["NLTF_FORCE_FORECAST_RUNNER_IMPORT_FALLBACK"] = "1"
    else:
        env.pop("NLTF_FORCE_FORECAST_RUNNER_IMPORT_FALLBACK", None)
    code = """
import app
from model_dashboard import forecast_imports as fi
from model_dashboard import reproducibility_imports as ri
from model_dashboard import revenue_source_pack as rsp
from scripts.check_streamlit_deploy_readiness import EXPECTED_IMPORT_SURFACE_REVISION
required = [
    'render_overview',
    'render_diagnostics',
    'render_scenario_comparison',
    'render_schiff_benchmark_page',
    'render_revenue_outlook_page',
    'render_governance_reproducibility_page',
]
missing = [name for name in required if not hasattr(app, name)]
if missing:
    raise SystemExit('missing app startup symbols: ' + ', '.join(missing))
if not hasattr(ri, 'load_reproducibility_pack') or not hasattr(ri, 'diagnostics_r2_summary_frame'):
    raise SystemExit('missing reproducibility/R2 compatibility exports')
if not hasattr(ri, 'r2_ladder_summary_frame') or not hasattr(ri, 'R2_LADDER_TITLE'):
    raise SystemExit('missing R2 ladder compatibility exports')
if not hasattr(fi, 'build_forecast_input_template_bytes') or not hasattr(fi, 'FORECAST_RUNNER_IMPORT_ERROR'):
    raise SystemExit('missing Forecast Builder compatibility exports')
if not hasattr(rsp, 'load_revenue_source_pack') or not hasattr(rsp, 'REVENUE_SOURCE_PACK_DIR'):
    raise SystemExit('missing revenue source pack exports')
if getattr(app, 'STREAMLIT_IMPORT_SURFACE_REVISION', None) != EXPECTED_IMPORT_SURFACE_REVISION:
    raise SystemExit('stale app import surface revision')
print('cloud import ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        modes = []
        if force_optional_fallback:
            modes.append("reproducibility fallback")
        if force_forecast_fallback:
            modes.append("forecast fallback")
        mode = " + ".join(modes) if modes else "normal"
        raise AssertionError(
            f"Streamlit Cloud-style startup import failed in {mode} mode.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def assert_r2_ladder_direct_import_subprocess(*, force_dependency_fallback: bool = False) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if force_dependency_fallback:
        env[R2_LADDER_DEP_FALLBACK_ENV] = "1"
    else:
        env.pop(R2_LADDER_DEP_FALLBACK_ENV, None)
    code = """
from model_dashboard.r2_ladder import R2_LADDER_NOTE, R2_LADDER_TITLE, R2_TRAINING_FIT_NOTE, r2_ladder_summary_frame
import pandas as pd
frame = r2_ladder_summary_frame({'scorecard_predictions': pd.DataFrame()})
if not R2_LADDER_NOTE or not R2_LADDER_TITLE or not R2_TRAINING_FIT_NOTE:
    raise SystemExit('missing R2 ladder text export')
if frame is None:
    raise SystemExit('R2 ladder summary returned None')
print('r2 ladder direct import ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        mode = "dependency fallback" if force_dependency_fallback else "normal"
        raise AssertionError(
            f"Streamlit Cloud-style direct R2 ladder import failed in {mode} mode.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


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
    assert_app_uses_cloud_safe_reproducibility_wrapper()
    assert_app_uses_cloud_safe_forecast_wrapper()
    assert_import_surface()
    assert_startup_import_subprocess(force_optional_fallback=False)
    assert_startup_import_subprocess(force_optional_fallback=True)
    assert_startup_import_subprocess(force_forecast_fallback=True)
    assert_r2_ladder_direct_import_subprocess(force_dependency_fallback=False)
    assert_r2_ladder_direct_import_subprocess(force_dependency_fallback=True)
    assert_pack_shape()
    assert_revenue_source_pack_shape()
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
    print(f"Import surface revision: {EXPECTED_IMPORT_SURFACE_REVISION}")
    print(f"Bundled evidence pack: {PACK_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

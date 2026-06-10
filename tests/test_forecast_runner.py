from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
from openpyxl import load_workbook

from model_dashboard.forecast_runner import (
    DEFAULT_FORECAST_HORIZON_QUARTERS,
    SHEET_BY_STREAM,
    STREAM_COLUMNS,
    STREAM_ORDER,
    TEMPLATE_FILENAME,
    build_forecast_input_template,
    create_completed_sample_workbook,
    forecast_template_filename,
    future_quarters_after,
    latest_known_actual_period,
    run_forecast_workbook,
    scenario_name_from_filename,
    validate_forecast_workbook,
    write_forecast_scenario_comparison,
)


ROOT = Path(__file__).resolve().parents[1]


def _expected_periods(horizon: int) -> list[str]:
    return future_quarters_after(latest_known_actual_period(ROOT), horizon)


def _assert_template_contract(path: Path, horizon: int) -> None:
    wb = load_workbook(path, data_only=False)
    assert wb.sheetnames == ["README", "PED Inputs", "Light RUC Inputs", "Heavy RUC Inputs"]
    expected_periods = _expected_periods(horizon)
    for stream in STREAM_ORDER:
        ws = wb[SHEET_BY_STREAM[stream]]
        headers = [cell.value for cell in ws[1]]
        expected_headers = [column.name for column in STREAM_COLUMNS[stream]]
        assert headers == expected_headers
        assert ws.max_row == horizon + 1
        assert [ws.cell(row=row, column=1).value for row in range(2, horizon + 2)] == expected_periods
        assert all(cell.comment for cell in ws[1] if cell.value)
        assert ws.protection.sheet is True
        formula_headers = [column.name for column in STREAM_COLUMNS[stream] if column.role == "formula"]
        assert {"q2_dummy", "q3_dummy", "q4_dummy", "post_2020_dummy", "trend_index"}.issubset(formula_headers)
        assert any(header.startswith("log_") for header in formula_headers)
        assert any(header.startswith("diff_") for header in formula_headers)
        assert any("interaction" in header for header in formula_headers)
        for header in formula_headers:
            value = ws.cell(row=2, column=headers.index(header) + 1).value
            assert isinstance(value, str) and value.startswith("="), header
            last_value = ws.cell(row=horizon + 1, column=headers.index(header) + 1).value
            assert isinstance(last_value, str) and last_value.startswith("="), header


def test_forecast_template_workbook_contract_for_variable_horizons(tmp_path: Path) -> None:
    one_quarter = tmp_path / forecast_template_filename(quarters=1)
    default_template = tmp_path / forecast_template_filename(quarters=DEFAULT_FORECAST_HORIZON_QUARTERS)
    long_template = tmp_path / forecast_template_filename(end_period="2050Q4")
    build_forecast_input_template(one_quarter, repo_root=ROOT, quarters=1)
    build_forecast_input_template(default_template, repo_root=ROOT)
    build_forecast_input_template(long_template, repo_root=ROOT, end_period="2050Q4")

    _assert_template_contract(one_quarter, 1)
    _assert_template_contract(default_template, DEFAULT_FORECAST_HORIZON_QUARTERS)
    _assert_template_contract(long_template, 100)
    assert forecast_template_filename(quarters=20) == "NLTF_forecast_input_template_20q.xlsx"
    assert forecast_template_filename(end_period="2050q4") == "NLTF_forecast_input_template_to_2050Q4.xlsx"
    for invalid_horizon in [0, -1]:
        try:
            forecast_template_filename(quarters=invalid_horizon)
        except ValueError as exc:
            assert "at least 1 quarter" in str(exc)
        else:
            raise AssertionError(f"Expected invalid horizon {invalid_horizon} to fail.")


def test_committed_forecast_template_exists_and_is_small() -> None:
    path = ROOT / "templates" / TEMPLATE_FILENAME
    assert path.exists()
    assert path.stat().st_size < 1_000_000
    _assert_template_contract(path, DEFAULT_FORECAST_HORIZON_QUARTERS)
    validation = validate_forecast_workbook(path, repo_root=ROOT)
    assert not validation.valid
    assert validation.latest_actual_period == "2025Q4"
    assert validation.forecast_periods == _expected_periods(DEFAULT_FORECAST_HORIZON_QUARTERS)
    assert any("no valid forecast rows" in message for message in validation.errors)


def test_runner_handles_missing_inputs_cleanly(tmp_path: Path) -> None:
    template = tmp_path / TEMPLATE_FILENAME
    build_forecast_input_template(template, repo_root=ROOT)
    result = run_forecast_workbook(template, output_dir=tmp_path / "blank_run", repo_root=ROOT, run_timestamp="blank-run")
    assert result.manifest["validation_status"] == "failed"
    assert result.manifest["forecast_status"] == "validation_failed"
    assert result.manifest["broad_search_run"] is False
    assert result.future_forecasts["forecast_available"].eq(False).all()
    assert result.future_forecasts["forecast"].isna().all()
    assert not result.future_forecasts["forecast"].fillna("").astype(str).isin({"0", "0.0"}).any()
    for name in [
        "future_forecasts.parquet",
        "component_forecasts.parquet",
        "forecast_assumptions.parquet",
        "forecast_capability_report.parquet",
        "forecast_run_manifest.json",
        "forecast_validation_report.md",
        "forecast_capability_report.csv",
    ]:
        assert (result.output_dir / name).exists(), name


def test_model_input_history_pack_is_committed_and_hash_backed() -> None:
    history_dir = ROOT / "data" / "model_input_history"
    manifest_path = history_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_basename"] == "Master Copy revenue modelling workbook.xlsx"
    assert manifest["source_sha256"]
    assert manifest["workbook_full_path_public"] is False
    paths = {
        "PED": history_dir / "ped_inputs.parquet",
        "LIGHT_RUC": history_dir / "light_ruc_inputs.parquet",
        "HEAVY_RUC": history_dir / "heavy_ruc_inputs.parquet",
    }
    for stream, path in paths.items():
        assert path.exists(), stream
        assert path.stat().st_size < 1_000_000
        frame = pd.read_parquet(path)
        assert len(frame) >= 90
        assert {"period", "target", "year", "quarter"}.issubset(frame.columns)
        assert pd.to_numeric(frame["target"], errors="coerce").gt(0).any()


def test_completed_workbook_builds_transforms_and_numeric_light_outputs(tmp_path: Path) -> None:
    workbook = create_completed_sample_workbook(tmp_path / "completed.xlsx", repo_root=ROOT)
    result = run_forecast_workbook(
        workbook,
        output_dir=tmp_path / "sample_run",
        repo_root=ROOT,
        run_timestamp="sample-run",
        scenario_name="basecase",
    )
    assert result.manifest["validation_status"] == "passed"
    assert result.manifest["forecast_status"] == "mixed_numeric_and_governed_gap"
    assert result.manifest["scenario_name"] == "basecase"
    assert result.manifest["workbook_filename"] == "completed.xlsx"
    assert result.manifest["workbook_sha256"]
    assert result.manifest["forecast_horizon_quarters"] == DEFAULT_FORECAST_HORIZON_QUARTERS
    assert result.manifest["forecast_start_period"] == "2026Q1"
    assert result.manifest["forecast_end_period"] == "2030Q4"
    assert result.manifest["numeric_forecast_streams"] == ["LIGHT_RUC"]
    assert result.manifest["governed_gap_streams"] == ["HEAVY_RUC", "PED"]
    assert result.manifest["fixed_finalists_only"] is True
    assert result.manifest["broad_search_run"] is False
    assert result.manifest["evidence_pack_modified"] is False
    assert result.manifest["chart_sources_modified"] is False
    assert len(result.future_forecasts) == DEFAULT_FORECAST_HORIZON_QUARTERS * len(STREAM_ORDER)
    assert result.future_forecasts["scenario_name"].eq("basecase").all()
    assert result.capability_report["scenario_name"].eq("basecase").all()
    assert result.assumptions["scenario_name"].eq("basecase").all()
    light = result.future_forecasts[result.future_forecasts["stream"].eq("LIGHT_RUC")]
    gaps = result.future_forecasts[~result.future_forecasts["stream"].eq("LIGHT_RUC")]
    assert len(light) == DEFAULT_FORECAST_HORIZON_QUARTERS
    assert light["forecast_available"].eq(True).all()
    assert pd.to_numeric(light["forecast"], errors="coerce").notna().all()
    assert (pd.to_numeric(light["forecast"], errors="coerce") > 0).all()
    assert light["availability_status"].eq("numeric_forecast_available").all()
    assert gaps["forecast_available"].eq(False).all()
    assert gaps["forecast"].isna().all()
    assert set(gaps["gap_code"]) == {
        "ped_inner_hpo_static_solver_forward_scorer_missing",
        "heavy_ruc_component_forward_scorers_missing",
    }
    heavy_reason = " ".join(gaps[gaps["stream"].eq("HEAVY_RUC")]["gap_reason"].dropna().astype(str).unique())
    ped_reason = " ".join(gaps[gaps["stream"].eq("PED")]["gap_reason"].dropna().astype(str).unique())
    assert "C1 ElasticNet dynamic no-leads ylag w64" in heavy_reason
    assert "C4 GBM dynamic no-leads ylag w40" in heavy_reason
    assert "inner HPO/static-solver forward scorer" in ped_reason
    light_components = result.component_forecasts[result.component_forecasts["stream"].eq("LIGHT_RUC")]
    assert {"base_schiff_ols", "residual_gbr", "dynamic_RESID_GBR_n150_d1_lr0.05_w36"}.issubset(
        set(light_components["component_model"].astype(str))
    )
    assert pd.to_numeric(light_components["component_forecast"], errors="coerce").notna().all()
    assert (result.future_forecasts["forecast_available"] == result.future_forecasts["stream"].eq("LIGHT_RUC")).all()
    assert result.capability_report.set_index("stream").loc["LIGHT_RUC", "forecast_available"] == True
    assert result.capability_report.set_index("stream").loc["LIGHT_RUC", "numeric_forecast_rows"] == DEFAULT_FORECAST_HORIZON_QUARTERS
    assumptions = result.assumptions
    for column in [
        "q2_dummy",
        "q3_dummy",
        "q4_dummy",
        "post_2020_dummy",
        "trend_index",
        "log_real_gdp",
        "log_real_gdp_per_capita",
        "diff_log_real_gdp",
        "gdp_light_ruc_price_interaction",
        "gdp_heavy_ruc_price_interaction",
    ]:
        assert column in assumptions.columns
    assert assumptions["transform_status"].eq("built_from_template_inputs").all()
    manifest = json.loads((result.output_dir / "forecast_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["broad_search_run"] is False
    assert manifest["output_files"]
    assert (result.output_dir / "forecast_capability_report.csv").exists()


def _clear_required_user_values(path: Path, stream: str, excel_row: int) -> None:
    wb = load_workbook(path)
    ws = wb[SHEET_BY_STREAM[stream]]
    headers = {cell.value: cell.column for cell in ws[1] if cell.value}
    ws.protection.sheet = False
    for column in STREAM_COLUMNS[stream]:
        if column.role == "user" and column.required:
            ws.cell(row=excel_row, column=headers[column.name]).value = None
    ws.protection.sheet = True
    wb.save(path)


def test_validation_accepts_variable_horizons_and_rejects_gaps_or_unequal_periods(tmp_path: Path) -> None:
    one_quarter = create_completed_sample_workbook(tmp_path / "one_quarter.xlsx", repo_root=ROOT, quarters=1)
    validation = validate_forecast_workbook(one_quarter, repo_root=ROOT)
    assert validation.valid
    assert validation.forecast_periods == ["2026Q1"]
    assert len(validation.assumptions) == len(STREAM_ORDER)

    three_quarters = create_completed_sample_workbook(tmp_path / "three_quarters.xlsx", repo_root=ROOT, quarters=3)
    validation = validate_forecast_workbook(three_quarters, repo_root=ROOT, expected_quarters=3)
    assert validation.valid
    assert validation.forecast_periods == ["2026Q1", "2026Q2", "2026Q3"]
    assert len(validation.assumptions) == 3 * len(STREAM_ORDER)

    gapped = create_completed_sample_workbook(tmp_path / "gapped.xlsx", repo_root=ROOT, quarters=3)
    for stream in STREAM_ORDER:
        _clear_required_user_values(gapped, stream, excel_row=3)
    gap_validation = validate_forecast_workbook(gapped, repo_root=ROOT)
    assert not gap_validation.valid
    assert any("continuous from 2026Q1 through 2026Q2 with no gaps" in message for message in gap_validation.errors)

    unequal = create_completed_sample_workbook(tmp_path / "unequal.xlsx", repo_root=ROOT, quarters=3)
    _clear_required_user_values(unequal, "HEAVY_RUC", excel_row=4)
    unequal_validation = validate_forecast_workbook(unequal, repo_root=ROOT)
    assert not unequal_validation.valid
    assert any("same continuous forecast periods across all streams" in message for message in unequal_validation.errors)


def test_filename_suffix_creates_expected_scenario_name() -> None:
    assert scenario_name_from_filename("NLTF_forecast_input_template_basecase.xlsx") == "basecase"
    assert scenario_name_from_filename("NLTF_forecast_input_template_high_fuel.xlsx") == "high_fuel"
    assert scenario_name_from_filename("forecast_input_downside.xlsx") == "downside"
    assert scenario_name_from_filename("completed_upside.xlsx") == "upside"
    assert scenario_name_from_filename("completed.xlsx") == "completed"


def test_cli_runs_variable_horizon_with_scenario_name(tmp_path: Path) -> None:
    workbook = create_completed_sample_workbook(
        tmp_path / "NLTF_forecast_input_template_high_fuel.xlsx",
        repo_root=ROOT,
        quarters=1,
    )
    output_dir = tmp_path / "cli_run"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_forecast_pack.py"),
            str(workbook),
            "--scenario-name",
            "high_fuel",
            "--quarters",
            "1",
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Scenario: high_fuel" in result.stdout
    manifest = json.loads((output_dir / "forecast_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["scenario_name"] == "high_fuel"
    assert manifest["forecast_horizon_quarters"] == 1
    future = pd.read_parquet(output_dir / "future_forecasts.parquet")
    assert len(future) == len(STREAM_ORDER)
    light = future[future["stream"].eq("LIGHT_RUC")]
    assert len(light) == 1
    assert light["forecast_available"].eq(True).all()


def test_scenario_comparison_artifacts(tmp_path: Path) -> None:
    base = create_completed_sample_workbook(tmp_path / "NLTF_forecast_input_template_basecase.xlsx", repo_root=ROOT, quarters=1)
    upside = create_completed_sample_workbook(
        tmp_path / "NLTF_forecast_input_template_upside.xlsx",
        repo_root=ROOT,
        quarters=2,
        value_multiplier=1.02,
    )
    results = [
        run_forecast_workbook(
            base,
            output_dir=tmp_path / "basecase_run",
            repo_root=ROOT,
            run_timestamp="comparison-smoke",
            scenario_name="basecase",
        ),
        run_forecast_workbook(
            upside,
            output_dir=tmp_path / "upside_run",
            repo_root=ROOT,
            run_timestamp="comparison-smoke",
            scenario_name="upside",
        ),
    ]
    comparison = write_forecast_scenario_comparison(
        results,
        output_dir=tmp_path / "comparison",
        repo_root=ROOT,
        run_timestamp="comparison-smoke",
    )
    assert comparison.manifest["scenario_count"] == 2
    assert {row["scenario_name"] for row in comparison.manifest["scenarios"]} == {"basecase", "upside"}
    assert len(comparison.future_forecasts) == sum(len(result.future_forecasts) for result in results)
    assert set(comparison.future_forecasts["scenario_name"]) == {"basecase", "upside"}
    for name in [
        "forecast_scenario_comparison.parquet",
        "forecast_scenario_comparison.csv",
        "forecast_scenario_capability_report.parquet",
        "forecast_scenario_capability_report.csv",
        "forecast_scenario_comparison_manifest.json",
    ]:
        assert (comparison.output_dir / name).exists(), name


def test_forecast_runner_does_not_touch_evidence_pack(tmp_path: Path) -> None:
    evidence_dir = ROOT / "data" / "dashboard_evidence_pack"
    before = {
        path.relative_to(evidence_dir).as_posix(): path.read_bytes()
        for path in evidence_dir.rglob("*")
        if path.is_file()
    }
    workbook = create_completed_sample_workbook(tmp_path / "completed.xlsx", repo_root=ROOT)
    run_forecast_workbook(workbook, output_dir=tmp_path / "sample_run", repo_root=ROOT, run_timestamp="evidence-isolation")
    after = {
        path.relative_to(evidence_dir).as_posix(): path.read_bytes()
        for path in evidence_dir.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_forecast_runner_does_not_touch_chart_sources(tmp_path: Path) -> None:
    chart_dir = ROOT / "artifacts" / "chart_sources"
    before = {
        path.relative_to(chart_dir).as_posix(): path.read_bytes()
        for path in chart_dir.glob("*.csv")
        if path.is_file()
    }
    workbook = create_completed_sample_workbook(tmp_path / "completed.xlsx", repo_root=ROOT)
    run_forecast_workbook(workbook, output_dir=tmp_path / "sample_run", repo_root=ROOT, run_timestamp="chart-isolation")
    after = {
        path.relative_to(chart_dir).as_posix(): path.read_bytes()
        for path in chart_dir.glob("*.csv")
        if path.is_file()
    }
    assert after == before


def test_forecast_run_artifacts_are_repo_ignored() -> None:
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "artifacts/forecast_runs/" in ignore_text
    assert "artifacts/forecast_uploads/" in ignore_text
    assert "!templates/NLTF_forecast_input_template_12q.xlsx" in ignore_text
    assert "!templates/NLTF_forecast_input_template_20q.xlsx" in ignore_text
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True)
    tracked = set(result.stdout.splitlines())
    assert "templates/NLTF_forecast_input_template_20q.xlsx" in tracked
    assert not any(path.startswith("artifacts/forecast_runs/") for path in tracked)
    assert not any(path.startswith("artifacts/forecast_uploads/") for path in tracked)
    tracked_workbooks = {path for path in tracked if path.lower().endswith((".xlsx", ".xls"))}
    assert tracked_workbooks <= {
        "templates/NLTF_forecast_input_template_12q.xlsx",
        "templates/NLTF_forecast_input_template_20q.xlsx",
    }

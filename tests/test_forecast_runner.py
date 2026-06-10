from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from model_dashboard.forecast_runner import (
    FORECAST_HORIZON_QUARTERS,
    SHEET_BY_STREAM,
    STREAM_COLUMNS,
    STREAM_ORDER,
    TEMPLATE_FILENAME,
    build_forecast_input_template,
    create_completed_sample_workbook,
    future_quarters_after,
    latest_known_actual_period,
    run_forecast_workbook,
    validate_forecast_workbook,
)


ROOT = Path(__file__).resolve().parents[1]


def test_forecast_template_workbook_contract(tmp_path: Path) -> None:
    path = tmp_path / TEMPLATE_FILENAME
    build_forecast_input_template(path, repo_root=ROOT)
    wb = load_workbook(path, data_only=False)
    assert wb.sheetnames == ["README", "PED Inputs", "Light RUC Inputs", "Heavy RUC Inputs"]
    expected_periods = future_quarters_after(latest_known_actual_period(ROOT))
    for stream in STREAM_ORDER:
        ws = wb[SHEET_BY_STREAM[stream]]
        headers = [cell.value for cell in ws[1]]
        expected_headers = [column.name for column in STREAM_COLUMNS[stream]]
        assert headers == expected_headers
        assert ws.max_row == FORECAST_HORIZON_QUARTERS + 1
        assert [ws.cell(row=row, column=1).value for row in range(2, 14)] == expected_periods
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


def test_committed_forecast_template_exists_and_is_small() -> None:
    path = ROOT / "templates" / TEMPLATE_FILENAME
    assert path.exists()
    assert path.stat().st_size < 1_000_000
    validation = validate_forecast_workbook(path, repo_root=ROOT)
    assert validation.latest_actual_period == "2025Q4"
    assert validation.forecast_periods == [f"2026Q{q}" for q in range(1, 5)] + [f"2027Q{q}" for q in range(1, 5)] + [
        f"2028Q{q}" for q in range(1, 5)
    ]


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
    result = run_forecast_workbook(workbook, output_dir=tmp_path / "sample_run", repo_root=ROOT, run_timestamp="sample-run")
    assert result.manifest["validation_status"] == "passed"
    assert result.manifest["forecast_status"] == "mixed_numeric_and_governed_gap"
    assert result.manifest["numeric_forecast_streams"] == ["LIGHT_RUC"]
    assert result.manifest["governed_gap_streams"] == ["HEAVY_RUC", "PED"]
    assert result.manifest["fixed_finalists_only"] is True
    assert result.manifest["broad_search_run"] is False
    assert result.manifest["evidence_pack_modified"] is False
    assert result.manifest["chart_sources_modified"] is False
    assert len(result.future_forecasts) == 36
    light = result.future_forecasts[result.future_forecasts["stream"].eq("LIGHT_RUC")]
    gaps = result.future_forecasts[~result.future_forecasts["stream"].eq("LIGHT_RUC")]
    assert len(light) == FORECAST_HORIZON_QUARTERS
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
    assert result.capability_report.set_index("stream").loc["LIGHT_RUC", "numeric_forecast_rows"] == FORECAST_HORIZON_QUARTERS
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

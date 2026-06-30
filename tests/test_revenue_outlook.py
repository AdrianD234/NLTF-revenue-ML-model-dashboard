from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil

import pandas as pd
from openpyxl import load_workbook
import pytest

from model_dashboard.forecast_runner import (
    SHEET_BY_STREAM,
    create_completed_sample_workbook,
    run_forecast_workbook,
    write_forecast_scenario_comparison,
)
from model_dashboard.revenue_outlook import (
    CANONICAL_JOIN_KEY_COLUMNS,
    CURRENT_REVENUE_OUTLOOK_DIR,
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_MBU26_ARCHIVED,
    FAN_SOURCE_SCENARIO_SPREAD,
    FUTURE_RATE_COLUMNS,
    PED_BRIDGE_DEFAULT_MODE,
    PED_EFFICIENCY_BASELINE_SCENARIO_ID,
    REVENUE_OUTLOOK_SCHEMA_VERSION,
    SENSITIVITY_SEED_WORKBOOK_SHA256,
    SOURCE_COMPARISON_OUTPUT_DIR_POLICY,
    apply_ped_bridge_mode_layer,
    apply_revenue_sensitivity_layer,
    apply_ped_efficiency_sensitivity,
    build_revenue_outlook_pack,
    load_revenue_outlook_pack,
    ped_efficiency_adjustment_frame,
    revenue_sensitivity_impact_audit_frame,
    promote_revenue_outlook_pack,
    validate_promotable_comparison,
)


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _max_fy(frame: pd.DataFrame) -> int | None:
    if frame is None or frame.empty:
        return None
    for column in ("FY", "june_year"):
        if column in frame.columns:
            years = pd.to_numeric(frame[column], errors="coerce")
            if years.notna().any():
                return int(years.max())
    for column in ("target_period", "annual_period", "period"):
        if column in frame.columns:
            years = frame[column].astype(str).str.extract(r"FY(\d{4})", expand=False)
            years = pd.to_numeric(years, errors="coerce")
            if years.notna().any():
                return int(years.max())
    return None


def _comparison(tmp_path: Path, *, blank_rates: bool = False, fixture: bool = False):
    base = create_completed_sample_workbook(tmp_path / "NLTF_forecast_input_template_basecase.xlsx", repo_root=ROOT, quarters=4)
    comparison = create_completed_sample_workbook(
        tmp_path / "NLTF_forecast_input_template_high_population.xlsx",
        repo_root=ROOT,
        quarters=4,
        value_multiplier=1.02,
    )
    if blank_rates:
        _blank_nominal_rate_columns(base)
        _blank_nominal_rate_columns(comparison)
    results = [
        run_forecast_workbook(
            base,
            output_dir=tmp_path / "basecase_run",
            repo_root=ROOT,
            run_timestamp="revenue-test",
            scenario_name="basecase",
            scenario_role="basecase",
            is_test_fixture=fixture,
            expected_quarters=4,
        ),
        run_forecast_workbook(
            comparison,
            output_dir=tmp_path / "comparison_run",
            repo_root=ROOT,
            run_timestamp="revenue-test",
            scenario_name="high_population",
            scenario_role="comparison",
            is_test_fixture=fixture,
            expected_quarters=4,
        ),
    ]
    return write_forecast_scenario_comparison(
        results,
        output_dir=tmp_path / "scenario_comparison",
        repo_root=ROOT,
        run_timestamp="revenue-test",
    )


def _blank_nominal_rate_columns(path: Path) -> None:
    workbook = load_workbook(path)
    for stream, (rate_col, source_col, cpi_col) in FUTURE_RATE_COLUMNS.items():
        sheet_name = SHEET_BY_STREAM[stream]
        ws = workbook[sheet_name]
        headers = {cell.value: cell.column for cell in ws[1] if cell.value}
        ws.protection.sheet = False
        for column_name in (rate_col, source_col, cpi_col):
            if column_name not in headers:
                continue
            for row in range(2, ws.max_row + 1):
                ws.cell(row=row, column=headers[column_name]).value = None
        ws.protection.sheet = True
    workbook.save(path)


def test_revenue_outlook_pack_computes_ruc_formula_and_honest_ped_gap(tmp_path: Path) -> None:
    comparison = _comparison(tmp_path)
    pack = promote_revenue_outlook_pack(comparison, repo_root=ROOT, output_dir=tmp_path / "pack", promoted_by="pytest")

    assert pack.manifest["schema_version"] == REVENUE_OUTLOOK_SCHEMA_VERSION
    assert pack.manifest["pack_status"] == "explicitly_promoted_current_outlook"
    assert pack.manifest["source_policy"].startswith("explicit_promoted_pack_or_in_session_reviewed_result_only")
    assert pack.manifest["source_comparison"]["output_dir_policy"] == SOURCE_COMPARISON_OUTPUT_DIR_POLICY
    assert "output_dir" not in pack.manifest["source_comparison"]
    assert all("output_dir" not in scenario for scenario in pack.manifest["source_comparison"]["scenarios"])
    assert pack.manifest["join_key_contract"]["columns"] == CANONICAL_JOIN_KEY_COLUMNS
    assert (pack.output_dir / "manifest.json").exists()
    assert (pack.output_dir / "future_revenue_forecasts.parquet").exists()
    assert load_revenue_outlook_pack(pack.output_dir, repo_root=ROOT) is not None
    scenario_input_manifest = json.loads(
        (pack.output_dir / "scenario_inputs" / "scenario_input_manifest.json").read_text(encoding="utf-8")
    )
    assert str(tmp_path) not in json.dumps(scenario_input_manifest)
    assert "C:\\Users" not in json.dumps(scenario_input_manifest)
    for workbook in scenario_input_manifest["workbooks"]:
        raw_path = Path(workbook["raw_repo_relative_path"])
        assert not raw_path.is_absolute()
        assert (ROOT / raw_path).exists() or (pack.output_dir / raw_path).exists()
        assert "scenario_inputs/raw" in raw_path.as_posix()
    for frame in [pack.future_revenue_forecasts, pack.revenue_bridge_components, pack.revenue_chart_rows]:
        assert set(CANONICAL_JOIN_KEY_COLUMNS).issubset(frame.columns)
        assert frame["canonical_join_key"].astype(str).str.count(r"\|").eq(2).all()
        assert not frame["canonical_join_key"].astype(str).str.contains(r"\|\||^\||\|$").any()

    light = pack.future_revenue_forecasts[
        pack.future_revenue_forecasts["stream"].eq("LIGHT_RUC")
        & pack.future_revenue_forecasts["bridge_status"].eq("available")
    ].copy()
    assert not light.empty
    row = light.iloc[0]
    expected = float(row["activity_forecast"]) / 1000.0 * float(row["rate_value"])
    assert abs(float(row["revenue_forecast_nzd"]) - expected) <= 1e-6
    assert bool(row["forecast_available"])

    ped = pack.future_revenue_forecasts[pack.future_revenue_forecasts["stream"].eq("PED")].copy()
    assert not ped.empty
    assert set(ped["bridge_status"].dropna().unique()) == {"ped_bridge_source_history_missing"}
    assert ped["revenue_forecast_nzd"].isna().all()
    assert not ped["revenue_forecast_nzd"].fillna("").astype(str).isin({"0", "0.0"}).any()

    reconciliations = pack.revenue_bridge_components[
        pack.revenue_bridge_components["component_type"].eq("historical_revenue_reconciliation")
    ].copy()
    assert set(reconciliations["stream"]) == {"LIGHT_RUC", "HEAVY_RUC"}
    deltas = pd.to_numeric(reconciliations["reconciliation_max_abs_delta_nzd"], errors="coerce")
    assert deltas.notna().all()
    assert float(deltas.max()) <= 1e-4


def test_revenue_outlook_missing_rates_are_gaps_not_zeroes(tmp_path: Path) -> None:
    comparison = _comparison(tmp_path, blank_rates=True)
    pack = build_revenue_outlook_pack(comparison, repo_root=ROOT, output_dir=tmp_path / "pack")
    ruc = pack.future_revenue_forecasts[pack.future_revenue_forecasts["stream"].isin(["LIGHT_RUC", "HEAVY_RUC"])].copy()
    assert not ruc.empty
    numeric_activity = pd.to_numeric(ruc["activity_forecast"], errors="coerce").notna()
    assert ruc.loc[numeric_activity, "bridge_status"].isin(["nominal_rate_missing", "activity_forecast_gap"]).all()
    assert ruc["revenue_forecast_nzd"].isna().all()
    assert not ruc["revenue_forecast_nzd"].fillna("").astype(str).isin({"0", "0.0"}).any()


def test_revenue_outlook_blocks_fixture_publication(tmp_path: Path) -> None:
    comparison = _comparison(tmp_path, fixture=True)
    errors = validate_promotable_comparison(comparison)
    assert any("Test fixture scenario cannot be promoted" in message for message in errors)


def test_committed_current_revenue_outlook_pack_is_repo_local_and_hash_backed() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    manifest_path = pack_dir / "manifest.json"
    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "C:\\Users" not in manifest_text
    assert "Downloads" not in manifest_text
    assert "test-output" not in manifest_text
    assert "revenue_outlook_promotion" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == REVENUE_OUTLOOK_SCHEMA_VERSION
    assert manifest["source_comparison"]["output_dir_policy"] == SOURCE_COMPARISON_OUTPUT_DIR_POLICY
    assert "output_dir" not in manifest["source_comparison"]
    assert all("output_dir" not in scenario for scenario in manifest["source_comparison"]["scenarios"])
    assert manifest["join_key_contract"]["columns"] == CANONICAL_JOIN_KEY_COLUMNS
    assert "canonical stream, period and scenario keys" in manifest["join_key_contract"]["rule"]
    assert manifest["repo_relative_output_dir"] == "data/current_revenue_outlook"
    assert manifest["source_hashes"]["model_input_history"]
    assert all(item.get("workbook_sha256") for item in manifest["source_hashes"]["workbooks"])
    assert manifest["mbu26_annual_spine"]["status"] == "mbu26_annual_spine_vendored"
    assert manifest["mbu26_annual_spine"]["source_release"] == "MBU26"
    assert manifest["mbu26_annual_spine"]["workbook_sha256"] == "9aaff21f72c0a10cfa972a29d3c4f716495c79cbd72fc28e8008a65558454e12"
    assert manifest["mbu26_annual_spine"]["sheet"] == "MBU26"
    assert manifest["source_hashes"]["mbu26_annual_spine"]["repo_relative_path"] == "data/revenue_model_source_pack/mbu26_annual_spine"
    assert manifest["revenue_source_pack"]["status"] == "mbu26_annual_spine_vendored"
    assert manifest["revenue_source_pack"]["source_pack_version"] == "MBU26"
    assert manifest["revenue_source_pack"]["raw_workbook_sha256"] == "9aaff21f72c0a10cfa972a29d3c4f716495c79cbd72fc28e8008a65558454e12"
    assert manifest["revenue_source_pack"]["selections"]["release_round"] == "MBU26"
    assert manifest["revenue_source_pack"]["selections"]["series"] == "Total NLTF revenue"
    assert manifest["revenue_source_pack"]["dashboard_default_selections"]["series"] == "Total NLTF revenue"
    assert manifest["revenue_source_pack"]["source_workbook_selections"]["sheet"] == "MBU26"
    assert "MBU26 source spine" in manifest["revenue_source_pack"]["default_selection_policy"]
    assert manifest["revenue_line_reconciliation"]["repo_relative_path"] == "data/current_revenue_outlook/revenue_line_reconciliation.csv"
    assert manifest["revenue_stack_components"]["repo_relative_path"] == "data/current_revenue_outlook/revenue_stack_components.csv"
    assert "aggregates are overlays only" in manifest["revenue_stack_components"]["scope"]
    assert manifest["ev_phev_split_assumptions"]["repo_relative_path"] == "data/current_revenue_outlook/ev_phev_split_assumptions.csv"
    assert manifest["ev_phev_split_assumptions"]["allocation_status"] == "legacy_light_only_comparator_superseded_by_ped_light_migration"
    assert (
        manifest["ev_phev_ped_light_drift_assumptions"]["repo_relative_path"]
        == "data/current_revenue_outlook/ev_phev_ped_light_drift_assumptions.csv"
    )
    assert manifest["ev_phev_ped_light_drift_assumptions"]["default_lambda_mode"] == "optimized"
    assert manifest["ev_phev_ped_light_drift_assumptions"]["runtime_mode"] == "optimized"
    assert float(manifest["ev_phev_ped_light_drift_assumptions"]["lambda_smoothness_penalty"]) > 0
    assert manifest["ped_revenue_bridge_audit"]["repo_relative_path"] == "data/current_revenue_outlook/ped_revenue_bridge_audit.csv"
    assert "raw VKTpc x population" in manifest["ped_revenue_bridge_audit"]["scope"]
    assert manifest["ped_revenue_bridge_audit"]["default_bridge_mode"] == PED_BRIDGE_DEFAULT_MODE
    assert manifest["ped_revenue_bridge_audit"]["population_proxy_warning_rows"] >= 1
    assert manifest["ped_bridge_shape_fit_metrics"]["repo_relative_path"] == "data/current_revenue_outlook/ped_bridge_shape_fit_metrics.csv"
    assert "raw-vs-optimized" in manifest["ped_bridge_shape_fit_metrics"]["scope"]
    assert manifest["ped_bridge_mode_config"]["repo_relative_path"] == "data/current_revenue_outlook/ped_bridge_mode_config.csv"
    assert manifest["ped_bridge_mode_config"]["default_bridge_mode"] == PED_BRIDGE_DEFAULT_MODE
    assert manifest["ped_efficiency_scenarios"]["repo_relative_path"] == "data/current_revenue_outlook/ped_efficiency_scenarios.csv"
    assert manifest["ped_efficiency_scenarios"]["default_scenario_id"] == PED_EFFICIENCY_BASELINE_SCENARIO_ID
    assert manifest["ped_efficiency_scenarios"]["default_runtime_treatment"] == "0pct_no_change"
    assert manifest["sensitivity_seed_inputs"]["repo_relative_path"] == "data/current_revenue_outlook/sensitivity_seed_inputs.csv"
    assert manifest["sensitivity_seed_inputs"]["source_workbook_sha256"] == SENSITIVITY_SEED_WORKBOOK_SHA256
    assert "fleet transition" in manifest["sensitivity_seed_inputs"]["excluded_scope"].lower()
    assert "crude/oil shock" in manifest["sensitivity_seed_inputs"]["excluded_scope"]
    assert manifest["sensitivity_config"]["repo_relative_path"] == "data/current_revenue_outlook/sensitivity_config.csv"
    assert manifest["sensitivity_config"]["default_runtime_treatment"] == "all_off_no_change"
    assert manifest["sensitivity_impact_audit"]["repo_relative_path"] == "data/current_revenue_outlook/sensitivity_impact_audit.csv"
    assert manifest["scenario_role_contract"]["repo_relative_path"] == "data/current_revenue_outlook/scenario_role_contract.csv"
    assert "behavioural intensity metric" in manifest["scenario_role_contract"]["note"]
    assert manifest["scenario_inputs"]["status"] == "available"
    assert manifest["scenario_inputs"]["repo_relative_output_dir"] == "data/current_revenue_outlook/scenario_inputs"
    assert manifest["scenario_inputs"]["schema_version"] == "nltf-scenario-input-materializer-v1"
    assert manifest["scenario_inputs"]["row_counts"] == {
        "scenario_input_cells": 15472,
        "scenario_input_long": 15200,
        "scenario_input_wide": 600,
        "scenario_feature_lineage": 44800,
    }
    assert manifest["scenario_input_delta_audit"]["repo_relative_path"] == (
        "data/current_revenue_outlook/scenario_input_delta_audit.csv"
    )
    assert manifest["scenario_input_delta_audit"]["status"] == "available"
    assert manifest["scenario_input_delta_audit"]["source"] == "scenario_inputs/scenario_input_long.parquet"
    assert "workbook-cell base/comparison deltas" in manifest["scenario_input_delta_audit"]["scope"].lower()
    scenario_input_manifest_path = pack_dir / "scenario_inputs" / "scenario_input_manifest.json"
    assert scenario_input_manifest_path.exists()
    assert manifest["scenario_inputs"]["manifest_sha256"] == _sha256(scenario_input_manifest_path)
    scenario_input_manifest_text = scenario_input_manifest_path.read_text(encoding="utf-8")
    assert "C:\\Users" not in scenario_input_manifest_text
    assert "Downloads" not in scenario_input_manifest_text
    scenario_input_manifest = json.loads(scenario_input_manifest_text)
    assert scenario_input_manifest["source_policy"] == "committed scenario input artifacts only; Streamlit must not load Excel at runtime"
    assert scenario_input_manifest["row_counts"] == manifest["scenario_inputs"]["row_counts"]
    assert len(scenario_input_manifest["workbooks"]) == 2
    sheet_inventory = scenario_input_manifest["sheet_inventory"]
    assert len(sheet_inventory) == 10
    assert {row["sheet"] for row in sheet_inventory} == {
        "README",
        "PED Inputs",
        "Light RUC Inputs",
        "Heavy RUC Inputs",
        "Assumptions",
    }
    assert {row["source_status"] for row in sheet_inventory} == {"all_non_empty_cells_materialized"}
    assert sum(row["materialized_cell_count"] for row in sheet_inventory) == manifest["scenario_inputs"]["row_counts"][
        "scenario_input_cells"
    ]
    assert all(row["materialized_cell_count"] == row["non_empty_cell_count"] for row in sheet_inventory)
    assert all(len(row["materialized_cells_sha256"]) == 64 for row in sheet_inventory)
    assert {workbook["workbook_sha256"] for workbook in scenario_input_manifest["workbooks"]} == {
        "d0644d353ee5a073602186cf7ac5c16e707d5350e16fd037b73a65528067cc6a",
        "6213ce565cf1f4a058a3ea9f1af4d5476a8b0423a4d8747905c3cba128380ce1",
    }
    assert {workbook["raw_status"] for workbook in scenario_input_manifest["workbooks"]} == {
        "copied_repo_local_raw_workbook"
    }
    for workbook in scenario_input_manifest["workbooks"]:
        raw_path = ROOT / workbook["raw_repo_relative_path"]
        assert raw_path.exists()
        assert raw_path.stat().st_size == workbook["size_bytes"]
        assert raw_path.stat().st_size < 50 * 1024 * 1024
        assert _sha256(raw_path) == workbook["workbook_sha256"]
        assert len(workbook["sheet_inventory"]) == workbook["sheet_count"]
        assert sum(row["materialized_cell_count"] for row in workbook["sheet_inventory"]) == workbook[
            "non_empty_cell_count"
        ]
    for output_file, metadata in scenario_input_manifest["output_files"].items():
        assert metadata["sha256"] == _sha256(ROOT / metadata["repo_relative_path"]), output_file
        assert metadata["repo_relative_path"].startswith("data/current_revenue_outlook/scenario_inputs/")
    assert (
        manifest["scenario_feature_lineage"]["repo_relative_path"]
        == "data/current_revenue_outlook/scenario_feature_lineage.csv"
    )
    assert manifest["scenario_feature_lineage"]["source"] == "scenario_inputs/scenario_feature_lineage.parquet"
    assert (
        manifest["scenario_input_replay_mismatch_report"]["repo_relative_path"]
        == "data/current_revenue_outlook/scenario_input_replay_mismatch_report.csv"
    )
    assert manifest["scenario_input_replay_mismatch_report"]["status"] == "passed_no_mismatch"
    assert "raises" in manifest["scenario_input_replay_mismatch_report"]["fail_policy"]
    assert manifest["target_semantics_audit"]["LIGHT_RUC"]["status"] == "business_rule_applied_ped_light_optimized_migration"
    assert "PED/light-petrol activity and total Light RUC" in manifest["data_vintage_manifest_notes"]["light_ruc_target_semantics"]
    assert manifest["revenue_formula_residuals"]["repo_relative_path"] == "data/current_revenue_outlook/revenue_formula_residuals.csv"
    assert manifest["series_alias_audit"]["repo_relative_path"] == "data/current_revenue_outlook/series_alias_audit.csv"
    assert manifest["fan_availability"]["repo_relative_path"] == "data/current_revenue_outlook/fan_availability.csv"
    assert manifest["fan_band_rows"]["repo_relative_path"] == "data/current_revenue_outlook/fan_band_rows.csv"
    assert sorted(manifest["output_hashes"]) == [
        "ev_phev_ped_light_drift_assumptions.csv",
        "ev_phev_ped_light_drift_assumptions.parquet",
        "ev_phev_split_assumptions.csv",
        "ev_phev_split_assumptions.parquet",
        "fan_availability.csv",
        "fan_availability.parquet",
        "fan_band_rows.csv",
        "fan_band_rows.parquet",
        "future_revenue_forecasts.csv",
        "future_revenue_forecasts.parquet",
        "path_trace_status.csv",
        "path_trace_status.parquet",
        "ped_bridge_mode_config.csv",
        "ped_bridge_mode_config.parquet",
        "ped_bridge_shape_fit_metrics.csv",
        "ped_bridge_shape_fit_metrics.parquet",
        "ped_efficiency_scenarios.csv",
        "ped_efficiency_scenarios.parquet",
        "ped_revenue_bridge_audit.csv",
        "ped_revenue_bridge_audit.parquet",
        "revenue_bridge_components.csv",
        "revenue_bridge_components.parquet",
        "revenue_chart_rows.csv",
        "revenue_chart_rows.parquet",
        "revenue_formula_residuals.csv",
        "revenue_formula_residuals.parquet",
        "revenue_line_reconciliation.csv",
        "revenue_line_reconciliation.parquet",
        "revenue_stack_components.csv",
        "revenue_stack_components.parquet",
        "row_reconciliation.csv",
        "row_reconciliation.parquet",
        "runtime_cutoff_audit.csv",
        "runtime_cutoff_audit.parquet",
        "runtime_trace_audit.csv",
        "runtime_trace_audit.parquet",
        "scenario_feature_lineage.csv",
        "scenario_feature_lineage.parquet",
        "scenario_input_delta_audit.csv",
        "scenario_input_delta_audit.parquet",
        "scenario_input_replay_mismatch_report.csv",
        "scenario_input_replay_mismatch_report.parquet",
        "scenario_role_contract.csv",
        "scenario_role_contract.parquet",
        "sensitivity_config.csv",
        "sensitivity_config.parquet",
        "sensitivity_impact_audit.csv",
        "sensitivity_impact_audit.parquet",
        "sensitivity_seed_inputs.csv",
        "sensitivity_seed_inputs.parquet",
        "series_alias_audit.csv",
        "series_alias_audit.parquet",
        "series_trace_contract.csv",
        "series_trace_contract.parquet",
        "trace_source_contract.csv",
        "trace_source_contract.parquet",
    ]
    for filename, metadata in manifest["output_hashes"].items():
        assert metadata["sha256"] == _sha256(pack_dir / filename)
    for filename in ["future_revenue_forecasts.parquet", "revenue_bridge_components.parquet", "revenue_chart_rows.parquet"]:
        frame = pd.read_parquet(pack_dir / filename)
        assert set(CANONICAL_JOIN_KEY_COLUMNS).issubset(frame.columns)
        assert frame["canonical_join_key"].astype(str).str.count(r"\|").eq(2).all()
    for path in pack_dir.iterdir():
        if path.is_file():
            assert path.stat().st_size < 50 * 1024 * 1024


def test_committed_current_revenue_outlook_runtime_contract() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    chart = pd.read_parquet(pack_dir / "revenue_chart_rows.parquet")
    bridge = pd.read_parquet(pack_dir / "revenue_bridge_components.parquet")
    future = pd.read_parquet(pack_dir / "future_revenue_forecasts.parquet")
    audit = pd.read_parquet(pack_dir / "runtime_trace_audit.parquet")
    line_reconciliation = pd.read_parquet(pack_dir / "revenue_line_reconciliation.parquet")
    stack_components = pd.read_parquet(pack_dir / "revenue_stack_components.parquet")
    ev_phev_split = pd.read_parquet(pack_dir / "ev_phev_split_assumptions.parquet")
    ev_phev_drift = pd.read_parquet(pack_dir / "ev_phev_ped_light_drift_assumptions.parquet")
    ped_bridge_audit = pd.read_parquet(pack_dir / "ped_revenue_bridge_audit.parquet")
    ped_bridge_shape_fit = pd.read_parquet(pack_dir / "ped_bridge_shape_fit_metrics.parquet")
    ped_bridge_mode_config = pd.read_parquet(pack_dir / "ped_bridge_mode_config.parquet")
    ped_efficiency_scenarios = pd.read_parquet(pack_dir / "ped_efficiency_scenarios.parquet")
    sensitivity_seed_inputs = pd.read_parquet(pack_dir / "sensitivity_seed_inputs.parquet")
    sensitivity_config = pd.read_parquet(pack_dir / "sensitivity_config.parquet")
    sensitivity_impact_audit = pd.read_parquet(pack_dir / "sensitivity_impact_audit.parquet")
    scenario_role_contract = pd.read_parquet(pack_dir / "scenario_role_contract.parquet")
    residuals = pd.read_parquet(pack_dir / "revenue_formula_residuals.parquet")
    alias_audit = pd.read_parquet(pack_dir / "series_alias_audit.parquet")
    runtime_cutoff_audit = pd.read_parquet(pack_dir / "runtime_cutoff_audit.parquet")
    fan_availability = pd.read_parquet(pack_dir / "fan_availability.parquet")
    fan_bands = pd.read_parquet(pack_dir / "fan_band_rows.parquet")
    scenario_feature_lineage = pd.read_parquet(pack_dir / "scenario_feature_lineage.parquet")
    scenario_input_delta = pd.read_parquet(pack_dir / "scenario_input_delta_audit.parquet")
    scenario_input_replay = pd.read_parquet(pack_dir / "scenario_input_replay_mismatch_report.parquet")
    scenario_input_wide = pd.read_parquet(pack_dir / "scenario_inputs" / "scenario_input_wide.parquet")

    assert manifest["runtime_pack_type"] == "mbu26_actual_current_finalist_official_comparator"
    assert manifest["bridge_status_by_stream"] == {
        "PED": ["available"],
        "LIGHT_RUC": ["available"],
        "HEAVY_RUC": ["available"],
    }
    assert "workbook model" not in json.dumps(manifest).lower()
    assert "annual_model_paths" not in json.dumps(manifest).lower()
    assert "nominal_rate_missing" not in json.dumps(manifest)
    assert "ped_bridge_source_history_missing" not in json.dumps(manifest)
    assert "extrapolated_model_extension" not in json.dumps(manifest)
    assert "extrapolated from FY2046" not in json.dumps(manifest)
    runtime_cutoff_fy = int(manifest["period_rule"]["runtime_cutoff_fy"])
    assert runtime_cutoff_fy == 2050
    assert manifest["runtime_cutoff_audit"]["repo_relative_path"] == "data/current_revenue_outlook/runtime_cutoff_audit.csv"
    assert manifest["runtime_cutoff_audit"]["runtime_cutoff_fy"] == runtime_cutoff_fy
    assert not runtime_cutoff_audit.empty
    assert set(runtime_cutoff_audit["audit_component"].astype(str)) == {
        "current_finalist_base",
        "current_finalist_comparison",
        "mbu26_required_components_rates_splits",
        "runtime_cutoff",
    }
    assert pd.to_numeric(runtime_cutoff_audit["runtime_cutoff_fy"], errors="coerce").eq(runtime_cutoff_fy).all()
    assert "no extrapolated model extension is used" in manifest["data_vintage_manifest_notes"]["runtime_cutoff"].lower()
    assert f"FY{runtime_cutoff_fy}" in manifest["data_vintage_manifest_notes"]["official_horizon_note"]
    assert _max_fy(chart) == runtime_cutoff_fy
    assert _max_fy(line_reconciliation) == runtime_cutoff_fy
    assert _max_fy(stack_components) == runtime_cutoff_fy
    assert _max_fy(fan_bands) == runtime_cutoff_fy
    assert _max_fy(future) == runtime_cutoff_fy
    assert _max_fy(bridge) == runtime_cutoff_fy
    official_source = pd.read_parquet(ROOT / "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_official_annual.parquet")
    assert (_max_fy(official_source) or 0) > runtime_cutoff_fy
    displayed = chart[
        chart["time_grain"].astype(str).eq("june_year")
        & chart["plot_allowed"].astype(str).str.lower().isin(["true", "1"])
    ].copy()
    assert _max_fy(displayed) == runtime_cutoff_fy
    current_line = line_reconciliation[line_reconciliation["source_path"].astype(str).str.startswith("Current finalist")].copy()
    assert _max_fy(current_line) == runtime_cutoff_fy
    runtime_tables = [chart, line_reconciliation, stack_components, audit, fan_bands]
    for frame in runtime_tables:
        assert not frame.astype(str).stack().str.contains("extrapolated_model_extension", regex=False).any()
        assert not frame.astype(str).stack().str.contains("extrapolated from FY2046", regex=False).any()
    assert manifest["target_semantics_audit"]["HEAVY_RUC"]["status"] == "not_reclassified"
    assert manifest["scenario_role_contract"]["repo_relative_path"] == "data/current_revenue_outlook/scenario_role_contract.csv"
    assert not scenario_role_contract.empty
    required_contract_columns = {
        "scenario_name",
        "scenario_role",
        "differing_fields",
        "population_only_flag",
        "behavioural_driver_flag",
        "affected_series",
        "interpretation",
        "display_policy",
        "affects_ped_vktpc_directly",
        "affects_bridge_scaling",
        "stream_differing_fields",
        "ped_vktpc_direct_fields",
        "bridge_scaling_fields",
        "bridge_only_fields",
        "unknown_fields",
    }
    assert required_contract_columns.issubset(scenario_role_contract.columns)
    comparison_ped_contract = scenario_role_contract[
        scenario_role_contract["scenario_name"].astype(str).eq("current_comparison_1")
        & scenario_role_contract["affected_series"].astype(str).eq("ped_vkt_per_capita")
    ].iloc[0]
    assert not bool(comparison_ped_contract["population_only_flag"])
    assert bool(comparison_ped_contract["behavioural_driver_flag"])
    assert comparison_ped_contract["display_policy"] == "keep_trace_relabel_comparison_behavioural_path"
    assert "population__level" in str(comparison_ped_contract["ped_population_feature_fields"])
    assert bool(comparison_ped_contract["affects_ped_vktpc_directly"])
    assert bool(comparison_ped_contract["affects_bridge_scaling"])
    assert "gdp_petrol_interaction" in str(comparison_ped_contract["ped_vktpc_direct_fields"])
    assert "population" in str(comparison_ped_contract["ped_vktpc_direct_fields"])
    assert str(comparison_ped_contract["bridge_scaling_fields"]) == "population"
    assert str(comparison_ped_contract["bridge_only_fields"]) == ""
    assert str(comparison_ped_contract["unknown_fields"]) == ""
    assert pd.to_numeric(comparison_ped_contract["runtime_delta_min"], errors="coerce") < 0
    assert "behavioural intensity metric" in str(comparison_ped_contract["notes"])
    comparison_revenue_contract = scenario_role_contract[
        scenario_role_contract["scenario_name"].astype(str).eq("current_comparison_1")
        & scenario_role_contract["affected_series"].astype(str).eq("gross_ped_revenue")
    ].iloc[0]
    assert comparison_revenue_contract["display_policy"] == "keep_comparison_trace_scale_or_bridge"
    assert comparison_revenue_contract["population_path_policy"] == "scenario_input_population_from_committed_workbook_artifacts"
    assert "population:population/scale" in str(comparison_revenue_contract["field_classification"])
    assert "real_gdp_sa_nzd:macro" in str(comparison_revenue_contract["field_classification"])
    assert "unemployment_rate:macro" in str(comparison_revenue_contract["field_classification"])
    assert "gdp_petrol_interaction:price/rate/policy" in str(comparison_revenue_contract["field_classification"])
    assert "target_lag_1:behavioural" in str(comparison_revenue_contract["field_classification"])
    assert bool(comparison_revenue_contract["affects_ped_vktpc_directly"])
    assert bool(comparison_revenue_contract["affects_bridge_scaling"])
    total_fed_contract = scenario_role_contract[
        scenario_role_contract["scenario_name"].astype(str).eq("current_comparison_1")
        & scenario_role_contract["affected_series"].astype(str).eq("total_fed_ruc_net_revenue")
    ].iloc[0]
    assert bool(total_fed_contract["affects_ped_vktpc_directly"])
    assert bool(total_fed_contract["affects_bridge_scaling"])
    total_ruc_contract = scenario_role_contract[
        scenario_role_contract["scenario_name"].astype(str).eq("current_comparison_1")
        & scenario_role_contract["affected_series"].astype(str).eq("total_ruc_net_revenue")
    ].iloc[0]
    assert not bool(total_ruc_contract["affects_ped_vktpc_directly"])
    assert not bool(total_ruc_contract["affects_bridge_scaling"])
    comparison_categories = {
        part.split(":", 1)[1].strip()
        for text in scenario_role_contract["field_classification"].dropna().astype(str)
        for part in text.split(";")
        if ":" in part
    }
    assert {"population/scale", "macro", "price/rate/policy", "behavioural"}.issubset(comparison_categories)
    assert "scenario_input_wide" in str(comparison_revenue_contract["source_basis"])
    assert not scenario_input_delta.empty
    required_delta_columns = {
        "base_workbook_sha256",
        "comparison_workbook_sha256",
        "base_cell",
        "comparison_cell",
        "canonical_period",
        "canonical_variable",
        "base_value",
        "comparison_value",
        "absolute_delta",
        "pct_delta",
        "field_classification",
        "affects_ped_vktpc_directly",
        "affects_bridge_scaling",
        "source_status",
    }
    assert required_delta_columns.issubset(scenario_input_delta.columns)
    assert set(scenario_input_delta["source_status"].dropna().astype(str)) == {"committed_scenario_input_delta"}
    assert scenario_input_delta["base_workbook_sha256"].astype(str).eq(
        "d0644d353ee5a073602186cf7ac5c16e707d5350e16fd037b73a65528067cc6a"
    ).all()
    assert scenario_input_delta["comparison_workbook_sha256"].astype(str).eq(
        "6213ce565cf1f4a058a3ea9f1af4d5476a8b0423a4d8747905c3cba128380ce1"
    ).all()
    assert scenario_input_delta["base_cell"].astype(str).str.len().gt(0).all()
    assert scenario_input_delta["comparison_cell"].astype(str).str.len().gt(0).all()
    assert {"PED", "LIGHT_RUC", "HEAVY_RUC"}.issubset(set(scenario_input_delta["stream"].astype(str)))
    assert {"population/scale", "macro", "price/rate/policy", "behavioural"}.issubset(
        set(scenario_input_delta["field_classification"].dropna().astype(str))
    )
    ped_population_delta = scenario_input_delta[
        scenario_input_delta["stream"].astype(str).eq("PED")
        & scenario_input_delta["canonical_variable"].astype(str).eq("population")
    ].copy()
    assert not ped_population_delta.empty
    assert ped_population_delta["field_classification"].astype(str).eq("population/scale").all()
    assert ped_population_delta["affects_ped_vktpc_directly"].astype(bool).all()
    assert ped_population_delta["affects_bridge_scaling"].astype(bool).all()
    assert not scenario_input_delta.astype(str).stack().str.contains(r"C:\\Users|Downloads|OneDrive", regex=True).any()
    required_source_split_columns = {
        "vktpc_source_file",
        "vktpc_source_cell",
        "vktpc_source_status",
        "population_source_file",
        "population_source_cell",
        "population_source_status",
    }
    assert required_source_split_columns.issubset(line_reconciliation.columns)
    assert required_source_split_columns.issubset(chart.columns)
    source_split_lines = line_reconciliation[
        line_reconciliation["scenario_name"].astype(str).eq("current_comparison_1")
        & line_reconciliation["series_id"].astype(str).isin(["ped_volume", "gross_ped_revenue"])
    ].copy()
    assert not source_split_lines.empty
    assert source_split_lines["vktpc_source_file"].astype(str).eq("forecast_scenario_comparison.parquet").all()
    assert source_split_lines["vktpc_source_status"].astype(str).eq("current_finalist_model").all()
    assert source_split_lines["vktpc_source_cell"].astype(str).str.len().gt(0).all()
    assert source_split_lines["population_source_file"].astype(str).eq("scenario_inputs/scenario_input_wide.parquet").all()
    assert source_split_lines["population_source_cell"].astype(str).str.contains("scenario_input_wide.parquet:PED:population").all()
    assert source_split_lines["population_source_status"].astype(str).str.startswith("scenario_input_population").all()
    source_split_chart = chart[
        chart["scenario_name"].astype(str).eq("current_comparison_1")
        & chart["series_id"].astype(str).eq("gross_ped_revenue")
    ].copy()
    assert not source_split_chart.empty
    assert source_split_chart["vktpc_source_file"].astype(str).eq("forecast_scenario_comparison.parquet").all()
    assert source_split_chart["population_source_file"].astype(str).eq("scenario_inputs/scenario_input_wide.parquet").all()
    assert not scenario_feature_lineage.empty
    assert set(scenario_feature_lineage["stream"].dropna().astype(str)) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    required_lineage_columns = {
        "lineage_role",
        "feature_source_variables",
        "feature_engineering_basis",
        "feature_lineage_status",
    }
    assert required_lineage_columns.issubset(scenario_feature_lineage.columns)
    assert {"source_variable", "model_feature"}.issubset(
        set(scenario_feature_lineage["lineage_role"].dropna().astype(str))
    )
    source_variable_lineage = scenario_feature_lineage[
        scenario_feature_lineage["lineage_role"].astype(str).eq("source_variable")
    ].copy()
    model_feature_lineage = scenario_feature_lineage[
        scenario_feature_lineage["lineage_role"].astype(str).eq("model_feature")
    ].copy()
    assert set(source_variable_lineage["source_status"].dropna().astype(str)) == {"committed_scenario_input"}
    assert not source_variable_lineage["fallback_flag"].astype(bool).any()
    assert source_variable_lineage["source_artifact"].eq("scenario_inputs/scenario_input_long.parquet").all()
    assert not model_feature_lineage.empty
    assert set(model_feature_lineage["stream"].dropna().astype(str)) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    required_model_features = {
        "LIGHT_RUC": {"diesel_x_ruc_price", "log_real_gdp_lag4"},
        "PED": {"gdp_pc__log", "policy__petrol_abs_change_1_lag4", "target__roll8_mean"},
        "HEAVY_RUC": {"heavy_price__log", "policy__diesel_abs_change_1_lag4", "target__roll8_mean"},
    }
    for stream, expected_features in required_model_features.items():
        features = set(
            model_feature_lineage.loc[model_feature_lineage["stream"].astype(str).eq(stream), "feature_name"].astype(str)
        )
        assert expected_features.issubset(features), stream
    target_lineage = model_feature_lineage[model_feature_lineage["feature_name"].astype(str).str.startswith("target__")]
    assert not target_lineage.empty
    assert target_lineage["fallback_flag"].astype(bool).all()
    assert target_lineage["fallback_reason"].astype(str).str.contains("recursive target-lag", regex=False).all()
    assert scenario_feature_lineage["canonical_variable"].astype(str).str.len().gt(0).all()
    assert set(scenario_input_wide["scenario_name"].dropna().astype(str)) == {
        "current_basecase",
        "current_comparison_1",
    }
    ped_population_inputs = scenario_input_wide[
        scenario_input_wide["stream"].astype(str).eq("PED")
        & scenario_input_wide["population"].fillna("").astype(str).ne("")
    ]
    assert not ped_population_inputs.empty
    assert set(ped_population_inputs["scenario_name"].dropna().astype(str)) == {
        "current_basecase",
        "current_comparison_1",
    }
    assert not scenario_input_replay.empty
    assert set(scenario_input_replay["mismatch_status"].dropna().astype(str)) == {
        "pass",
        "not_applicable",
    }
    assert "mismatch" not in set(scenario_input_replay["mismatch_status"].dropna().astype(str))
    matched_replay = scenario_input_replay[
        scenario_input_replay["scenario_input_status"].astype(str).eq("matched_committed_scenario_input")
    ].copy()
    assert not matched_replay.empty
    assert matched_replay["workbook_sha256"].astype(str).eq(matched_replay["manifest_workbook_sha256"].astype(str)).all()
    assert pd.to_numeric(matched_replay["required_feature_count"], errors="coerce").gt(0).all()
    assert pd.to_numeric(matched_replay["missing_required_feature_count"], errors="coerce").eq(0).all()
    required_replay_columns = {
        "replay_forecast_value",
        "promoted_forecast_value",
        "replay_abs_delta",
        "replay_tolerance",
        "replay_status",
    }
    assert required_replay_columns.issubset(scenario_input_replay.columns)
    assert matched_replay["replay_status"].astype(str).eq("pass").all()
    replay_values = pd.to_numeric(matched_replay["replay_forecast_value"], errors="coerce")
    promoted_values = pd.to_numeric(matched_replay["promoted_forecast_value"], errors="coerce")
    replay_deltas = pd.to_numeric(matched_replay["replay_abs_delta"], errors="coerce")
    replay_tolerances = pd.to_numeric(matched_replay["replay_tolerance"], errors="coerce")
    assert replay_values.notna().all()
    assert promoted_values.notna().all()
    assert replay_deltas.notna().all()
    assert replay_tolerances.notna().all()
    assert replay_tolerances.gt(0).all()
    assert replay_deltas.le(replay_tolerances).all()
    assert "governed_model_extension_not_replayed_from_workbook" not in set(
        scenario_input_replay["scenario_input_status"].dropna().astype(str)
    )
    assert not scenario_input_replay["annual_period"].dropna().astype(str).isin(
        {"FY2051", "FY2052", "FY2053", "FY2054", "FY2055"}
    ).any()
    assert not ev_phev_split.empty
    assert ev_phev_split["used_by_current_finalist"].astype(bool).any()
    current_split = ev_phev_split[ev_phev_split["used_by_current_finalist"].astype(bool)].copy()
    assert set(current_split["allocation_status"].dropna().astype(str)) == {
        "legacy_light_only_comparator_superseded_by_ped_light_migration"
    }
    assert set(current_split["source_path"].dropna().astype(str)) == {
        "Current finalist Base case",
        "Current finalist High population/comparison",
    }
    assert pd.to_numeric(current_split["current_allocation_residual_km"], errors="coerce").abs().max() > 0
    assert not ev_phev_drift.empty
    assert set(ev_phev_drift["lambda_mode"].dropna().astype(str)) == {
        "optimized",
        "fixed_light_only",
        "fixed_ped_only",
        "mbu_ratio",
    }
    required_drift_columns = {
        "smoothed_target_PED_light_petrol_km",
        "smoothed_target_conventional_light_km",
        "smoothed_target_BEV_km",
        "smoothed_target_PHEV_km",
        "smoothed_target_EV_total_km",
        "current_migration_revenue_total",
        "old_light_only_migration_revenue_total",
        "migration_revenue_delta",
    }
    assert required_drift_columns.issubset(ev_phev_drift.columns)
    optimized_drift = ev_phev_drift[
        ev_phev_drift["lambda_mode"].astype(str).eq("optimized")
        & ev_phev_drift["source_path"].astype(str).str.startswith("Current finalist")
    ].copy()
    assert not optimized_drift.empty
    lambda_values = pd.to_numeric(optimized_drift["lambda_value"], errors="coerce")
    lambda_lower = pd.to_numeric(optimized_drift["lambda_lower_bound"], errors="coerce")
    lambda_upper = pd.to_numeric(optimized_drift["lambda_upper_bound"], errors="coerce")
    assert lambda_values.between(0, 1).all()
    assert (lambda_values >= lambda_lower).all()
    assert (lambda_values <= lambda_upper).all()
    assert (
        optimized_drift.sort_values(["source_path", "FY"])
        .groupby("source_path")["lambda_value"]
        .apply(lambda values: pd.to_numeric(values, errors="coerce").diff().diff().abs().max())
        .max()
        < 0.01
    )
    assert pd.to_numeric(optimized_drift["component_sum_residual_km"], errors="coerce").abs().max() <= 1e-6
    for component in [
        "current_PED_light_petrol_km",
        "current_conventional_light_km",
        "current_BEV_km",
        "current_PHEV_km",
    ]:
        assert pd.to_numeric(optimized_drift[component], errors="coerce").ge(0).all()
    for smoothed_col, current_col in {
        "smoothed_target_PED_light_petrol_km": "current_PED_light_petrol_km",
        "smoothed_target_conventional_light_km": "current_conventional_light_km",
        "smoothed_target_BEV_km": "current_BEV_km",
        "smoothed_target_PHEV_km": "current_PHEV_km",
    }.items():
        assert pd.to_numeric(optimized_drift[smoothed_col], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(optimized_drift[current_col], errors="coerce").to_numpy()
        )
    assert pd.to_numeric(optimized_drift["smoothed_target_EV_total_km"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(optimized_drift["smoothed_target_BEV_km"], errors="coerce")
            + pd.to_numeric(optimized_drift["smoothed_target_PHEV_km"], errors="coerce")
        ).to_numpy()
    )
    assert pd.to_numeric(optimized_drift["current_migration_revenue_total"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(optimized_drift["current_PED_revenue"], errors="coerce")
            + pd.to_numeric(optimized_drift["current_light_ruc_net_revenue"], errors="coerce")
            + pd.to_numeric(optimized_drift["current_light_bev_ruc_net_revenue"], errors="coerce")
            + pd.to_numeric(optimized_drift["current_phev_ruc_net_revenue"], errors="coerce")
        ).to_numpy()
    )
    assert pd.to_numeric(optimized_drift["migration_revenue_delta"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(optimized_drift["current_migration_revenue_total"], errors="coerce")
            - pd.to_numeric(optimized_drift["old_light_only_migration_revenue_total"], errors="coerce")
        ).to_numpy()
    )
    assert not ped_bridge_audit.empty
    assert set(ped_bridge_audit["source_path"].dropna().astype(str)) == {
        "Current finalist Base case",
        "Current finalist High population/comparison",
    }
    assert int(pd.to_numeric(ped_bridge_audit["FY"], errors="coerce").min()) == 2026
    assert int(pd.to_numeric(ped_bridge_audit["FY"], errors="coerce").max()) == runtime_cutoff_fy
    required_ped_bridge_columns = {
        "scenario",
        "ped_vktpc_model",
        "ped_vkt_per_capita",
        "scenario_population",
        "population_million",
        "population_source_status",
        "population_fallback_flag",
        "raw_light_petrol_vkt",
        "raw_light_petrol_vkt_million_km",
        "adjusted_light_petrol_vkt_million_km",
        "optimized_light_petrol_vkt",
        "optimized_light_petrol_vkt_million_km",
        "optimization_delta",
        "optimization_delta_million_km",
        "base_litres_per_100km",
        "ped_volume_raw",
        "ped_volume_raw_million_litres",
        "ped_volume_optimized",
        "ped_volume_optimized_million_litres",
        "ped_volume_million_litres",
        "ped_rate",
        "ped_rate_nzd_per_litre",
        "gross_ped_revenue_raw",
        "gross_ped_revenue_raw_million_nzd",
        "gross_ped_revenue_optimized",
        "gross_ped_revenue_optimized_million_nzd",
        "gross_ped_revenue_million_nzd",
        "total_nltf_raw",
        "total_nltf_raw_million_nzd",
        "total_nltf_optimized",
        "total_nltf_optimized_million_nzd",
        "total_nltf_net_revenue_million_nzd",
        "mbu26_light_petrol_vkt_million_km",
        "mbu26_ped_volume_million_litres",
        "mbu26_gross_ped_revenue_million_nzd",
        "vktpc_source_cell",
        "population_source_cell",
        "migration_source_cells",
        "formula",
    }
    assert required_ped_bridge_columns.issubset(ped_bridge_audit.columns)
    assert pd.to_numeric(ped_bridge_audit["population_million"], errors="coerce").gt(0).all()
    assert pd.to_numeric(ped_bridge_audit["base_litres_per_100km"], errors="coerce").gt(0).all()
    assert pd.to_numeric(ped_bridge_audit["ped_volume_million_litres"], errors="coerce").gt(0).all()
    assert pd.to_numeric(ped_bridge_audit["gross_ped_revenue_million_nzd"], errors="coerce").gt(0).all()
    assert pd.to_numeric(ped_bridge_audit["ped_vktpc_model"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(ped_bridge_audit["ped_vkt_per_capita"], errors="coerce").to_numpy()
    )
    assert pd.to_numeric(ped_bridge_audit["raw_light_petrol_vkt"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(ped_bridge_audit["raw_light_petrol_vkt_million_km"], errors="coerce").to_numpy()
    )
    assert pd.to_numeric(ped_bridge_audit["ped_volume_raw"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(ped_bridge_audit["ped_volume_raw_million_litres"], errors="coerce").to_numpy()
    )
    assert pd.to_numeric(ped_bridge_audit["raw_light_petrol_vkt_million_km"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(ped_bridge_audit["ped_vktpc_model"], errors="coerce")
            * pd.to_numeric(ped_bridge_audit["scenario_population"], errors="coerce")
            / 1_000_000.0
        ).to_numpy()
    )
    assert pd.to_numeric(ped_bridge_audit["ped_volume_raw_million_litres"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(ped_bridge_audit["raw_light_petrol_vkt_million_km"], errors="coerce")
            * pd.to_numeric(ped_bridge_audit["base_litres_per_100km"], errors="coerce")
            / 100.0
        ).to_numpy()
    )
    assert pd.to_numeric(ped_bridge_audit["ped_volume_optimized_million_litres"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(ped_bridge_audit["optimized_light_petrol_vkt_million_km"], errors="coerce")
            * pd.to_numeric(ped_bridge_audit["base_litres_per_100km"], errors="coerce")
            / 100.0
        ).to_numpy()
    )
    assert ped_bridge_audit["population_fallback_flag"].fillna(False).astype(bool).any()
    assert ped_bridge_audit.loc[
        ped_bridge_audit["population_fallback_flag"].fillna(False).astype(bool), "population_source_cell"
    ].astype(str).str.contains("population_proxy", regex=False).all()
    assert not ped_bridge_shape_fit.empty
    assert {"raw", "optimized"}.issubset(set(ped_bridge_shape_fit["bridge_variant"].astype(str)))
    base_light_fit = ped_bridge_shape_fit[
        ped_bridge_shape_fit["source_path"].astype(str).eq("Current finalist Base case")
        & ped_bridge_shape_fit["mbu_comparator_series_id"].astype(str).eq("light_petrol_vkt")
    ]
    raw_mae = float(base_light_fit.loc[base_light_fit["bridge_variant"].astype(str).eq("raw"), "mean_abs_error"].iloc[0])
    opt_mae = float(base_light_fit.loc[base_light_fit["bridge_variant"].astype(str).eq("optimized"), "mean_abs_error"].iloc[0])
    assert opt_mae < raw_mae
    assert set(ped_bridge_mode_config["bridge_mode"].astype(str)) == {
        "raw_model",
        "blend_25",
        "blend_50",
        "blend_75",
        PED_BRIDGE_DEFAULT_MODE,
    }
    assert ped_bridge_mode_config.loc[
        ped_bridge_mode_config["bridge_mode"].astype(str).eq(PED_BRIDGE_DEFAULT_MODE), "default_selected"
    ].astype(bool).all()
    assert not ped_efficiency_scenarios.empty
    assert set(ped_efficiency_scenarios["scenario_id"].astype(str)) == {
        PED_EFFICIENCY_BASELINE_SCENARIO_ID,
        "efficiency_0_5pct_pa",
        "efficiency_1_0pct_pa",
        "efficiency_1_5pct_pa",
        "efficiency_2_0pct_pa",
    }
    assert ped_efficiency_scenarios["start_fy"].astype(int).eq(2026).all()
    assert ped_efficiency_scenarios["end_fy"].astype(int).eq(runtime_cutoff_fy).all()
    assert ped_efficiency_scenarios["notes"].astype(str).str.contains("does not change VKTpc forecasts", regex=False).all()
    assert not sensitivity_seed_inputs.empty
    assert set(sensitivity_seed_inputs["family"].astype(str)) == {
        "fleet_efficiency",
        "pt_mode_shift",
        "demand_elasticity",
    }
    assert set(sensitivity_seed_inputs["scenario_level"].astype(str)) == {"Low", "Med", "High"}
    assert sensitivity_seed_inputs["workbook_sha256"].astype(str).eq(SENSITIVITY_SEED_WORKBOOK_SHA256).all()
    assert sensitivity_seed_inputs["sheet"].astype(str).eq("Inputs (TI)").all()
    assert {"C181", "D181", "E181", "C206", "D206", "E206", "C213", "D213", "E213", "C266", "D266", "E266"}.issubset(
        set(sensitivity_seed_inputs["cell"].astype(str))
    )
    assert not sensitivity_seed_inputs.astype(str).stack().str.contains("C:\\Users", regex=False).any()
    assert not sensitivity_seed_inputs.astype(str).stack().str.contains("Downloads", regex=False).any()
    assert not sensitivity_config.empty
    assert set(sensitivity_config["family"].astype(str)) == {
        "fleet_efficiency",
        "pt_mode_shift",
        "demand_elasticity",
    }
    for family in ["fleet_efficiency", "pt_mode_shift", "demand_elasticity"]:
        assert {"Off", "Low", "Med", "High", "Custom"}.issubset(
            set(sensitivity_config.loc[sensitivity_config["family"].astype(str).eq(family), "selection"].astype(str))
        )
    assert sensitivity_config.loc[sensitivity_config["selection"].astype(str).eq("Off"), "default_selected"].astype(bool).all()
    assert not sensitivity_config.astype(str).stack().str.contains("crude-to-pump", case=False, regex=False).any()
    assert not sensitivity_config.astype(str).stack().str.contains("fleet transition target", case=False, regex=False).any()
    assert not sensitivity_impact_audit.empty
    assert set(sensitivity_impact_audit["selected_fleet_efficiency"].astype(str)) == {"Off"}
    assert set(sensitivity_impact_audit["selected_pt_mode_shift"].astype(str)) == {"Off"}
    assert set(sensitivity_impact_audit["selected_demand_elasticity"].astype(str)) == {"Off"}
    assert pd.to_numeric(sensitivity_impact_audit["delta"], errors="coerce").abs().max() == pytest.approx(0.0, abs=0)
    evidence = (
        ev_phev_split[
            pd.to_numeric(ev_phev_split["FY"], errors="coerce").isin([2024, 2025])
            & ev_phev_split["model_input_full_year"].astype(bool)
        ]
        .drop_duplicates("FY")
        .set_index("FY")
    )
    assert set(evidence["target_semantics_status"]) == {"matches_conventional_light_not_total_universe"}
    assert evidence["target_matches_conventional_light"].astype(bool).all()
    assert not evidence["target_matches_total_light_universe"].astype(bool).any()
    assert pd.to_numeric(evidence["target_minus_conventional_light_km"], errors="coerce").abs().max() == pytest.approx(0.0, abs=1e-9)
    assert pd.to_numeric(evidence["target_minus_total_light_universe_km"], errors="coerce").lt(0).all()

    allowed_traces = {
        "Actual",
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
        "Current finalist comparison behavioural path",
    }
    displayed = chart[chart["time_grain"].astype(str).eq("june_year") & chart["plot_allowed"].astype(str).str.lower().isin(["true", "1"])]
    assert set(displayed["trace_name"].dropna().unique()) == allowed_traces
    assert displayed[
        displayed["row_type"].astype(str).eq("historical_actual")
        & pd.to_numeric(displayed["june_year"], errors="coerce").gt(2025)
    ].empty
    dashboard_series = {str(value) for value in displayed["series_id"].dropna().unique()}
    assert dashboard_series == {
        "gross_fed_revenue",
        "gross_ped_revenue",
        "heavy_ruc_net_km",
        "heavy_ruc_net_revenue",
        "light_bev_ruc_net_km",
        "light_bev_ruc_net_revenue",
        "light_ruc_net_km",
        "light_ruc_net_revenue",
        "net_fed_revenue",
        "net_mvr_revenue",
        "ped_volume",
        "ped_vkt_per_capita",
        "phev_ruc_net_km",
        "phev_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
        "total_ruc_net_revenue",
    }
    assert "current_light_ruc_total_modelled_km" not in dashboard_series
    for series_id, series_rows in displayed.groupby("series_id"):
        traces = set(series_rows["trace_name"].dropna().astype(str))
        expected_current_trace = (
            "Current finalist comparison behavioural path"
            if str(series_id) == "ped_vkt_per_capita"
            else "Current finalist High population/comparison"
        )
        expected_traces = {
            "Actual",
            "MBU26 official",
            "Current finalist Base case",
            expected_current_trace,
        }
        assert expected_traces.issubset(traces), series_id
        actual_rows = series_rows[series_rows["trace_name"].astype(str).eq("Actual")]
        official_rows = series_rows[series_rows["trace_name"].astype(str).eq("MBU26 official")]
        assert not actual_rows.empty, series_id
        assert not official_rows.empty, series_id
        assert not actual_rows["source_file"].fillna("").astype(str).str.contains("forecast_scenario|annual_model_paths|selected_dashboard", case=False).any(), series_id
        assert not official_rows["source_file"].fillna("").astype(str).str.contains("forecast_scenario|annual_model_paths|selected_dashboard", case=False).any(), series_id
        official_years = set(pd.to_numeric(official_rows["june_year"], errors="coerce").dropna().astype(int))
        assert {2026, 2027}.issubset(official_years), series_id
        current_rows = series_rows[
            series_rows["trace_name"].astype(str).isin(
                [
                    "Current finalist Base case",
                    expected_current_trace,
                ]
            )
            & pd.to_numeric(series_rows["june_year"], errors="coerce").ge(2026)
        ]
        assert {
            "Current finalist Base case",
            expected_current_trace,
        }.issubset(set(current_rows["trace_name"].dropna().astype(str))), series_id
        assert not current_rows["source_file"].fillna("").astype(str).str.contains("annual_model_paths|selected_dashboard", case=False).any(), series_id
    assert "light_petrol_vkt_per_capita" not in set(chart["series_id"].dropna().astype(str))
    ped_displayed = displayed[displayed["series_id"].astype(str).eq("ped_vkt_per_capita")].copy()
    ped_by_trace = {
        trace: set(pd.to_numeric(group["june_year"], errors="coerce").dropna().astype(int))
        for trace, group in ped_displayed.groupby("trace_name")
    }
    assert 2025 in ped_by_trace["Actual"]
    assert {2026, 2027}.issubset(ped_by_trace["MBU26 official"])
    assert {2026, 2027}.issubset(ped_by_trace["Current finalist Base case"])
    assert "Current finalist High population/comparison" not in ped_by_trace
    assert {2026, 2027}.issubset(ped_by_trace["Current finalist comparison behavioural path"])
    official_ped_fy2026 = ped_displayed[
        ped_displayed["trace_name"].astype(str).eq("MBU26 official")
        & pd.to_numeric(ped_displayed["june_year"], errors="coerce").eq(2026)
    ].iloc[0]
    assert float(official_ped_fy2026["value"]) > 5000
    assert official_ped_fy2026["source_cell"] == "AB17"

    runtime_text = pd.concat(
        [
            chart[["source_file", "source", "model_basis"]].astype(str).stack(),
            bridge[["source", "source_basis", "model_id"]].astype(str).stack(),
            future[["source", "model_id"]].astype(str).stack(),
            stack_components[["source_file", "source_basis", "model_id"]].astype(str).stack(),
            scenario_role_contract.astype(str).stack(),
            scenario_feature_lineage.astype(str).stack(),
            scenario_input_replay.astype(str).stack(),
        ],
        ignore_index=True,
    ).str.cat(sep="\n")
    assert "annual_model_paths.csv" not in runtime_text
    assert "selected_dashboard" not in runtime_text.lower()
    assert "scenario_workbook_population_path_not_committed" not in runtime_text
    assert "source_workbook_cell_delta_unavailable" not in runtime_text
    assert "schiff" not in runtime_text.lower()
    assert "Official comparator: selected MOT/BEFU" not in runtime_text
    assert "Official comparator: rolling BEFU 1Y" not in runtime_text

    current = chart[
        chart["time_grain"].astype(str).eq("june_year")
        & chart["trace_role"].astype(str).eq("in_house_current_finalist")
        & chart["fed_path"].astype(str).eq("Current planned path")
    ].copy()
    fy2026 = current[current["period"].astype(str).eq("FY2026")].set_index(["series_id", "scenario_name"])
    assert fy2026.loc[("gross_ped_revenue", "current_basecase"), "model_id"] == "PED__VNEXT_SOLVED_CONVEX_TOP2"
    assert fy2026.loc[("light_ruc_net_revenue", "current_basecase"), "model_id"] == "dynamic_RESID_GBR_n150_d1_lr0.05_w36"
    assert "dynamic_RESID_GBR_n150_d1_lr0.05_w36" in fy2026.loc[("light_bev_ruc_net_revenue", "current_basecase"), "model_id"]
    assert "PED__VNEXT_SOLVED_CONVEX_TOP2" in fy2026.loc[("light_bev_ruc_net_revenue", "current_basecase"), "model_id"]
    assert "dynamic_RESID_GBR_n150_d1_lr0.05_w36" in fy2026.loc[("phev_ruc_net_revenue", "current_basecase"), "model_id"]
    assert "PED__VNEXT_SOLVED_CONVEX_TOP2" in fy2026.loc[("phev_ruc_net_revenue", "current_basecase"), "model_id"]
    assert fy2026.loc[("heavy_ruc_net_revenue", "current_basecase"), "model_id"] == "HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4"
    assert "PED__VNEXT_SOLVED_CONVEX_TOP2" in fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "model_id"]
    assert fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "data_scope"] == "current_nowcast"
    assert fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "actual_quarters"] == "2025Q3; 2025Q4"
    assert fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "forecast_quarters"] == "2026Q1; 2026Q2"
    assert float(fy2026.loc[("gross_ped_revenue", "current_basecase"), "value"]) == pytest.approx(2052.808602, abs=1e-6)
    assert float(fy2026.loc[("gross_fed_revenue", "current_basecase"), "value"]) == pytest.approx(2094.853764, abs=1e-6)
    assert float(fy2026.loc[("net_fed_revenue", "current_basecase"), "value"]) == pytest.approx(2021.586240, abs=1e-6)
    assert float(fy2026.loc[("light_bev_ruc_net_revenue", "current_basecase"), "value"]) == pytest.approx(80.520128, abs=1e-6)
    assert float(fy2026.loc[("phev_ruc_net_revenue", "current_basecase"), "value"]) == pytest.approx(21.587058, abs=1e-6)
    assert float(fy2026.loc[("total_ruc_net_revenue", "current_basecase"), "value"]) == pytest.approx(2045.963932, abs=1e-6)
    assert float(fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "value"]) == pytest.approx(4510.085443, abs=1e-6)
    assert float(fy2026.loc[("gross_ped_revenue", "current_comparison_1"), "value"]) == pytest.approx(2054.465215, abs=1e-6)
    assert float(fy2026.loc[("total_nltf_net_revenue", "current_comparison_1"), "value"]) == pytest.approx(4513.738498, abs=1e-6)

    anchor = current[current["period"].astype(str).eq("FY2025")].set_index(["series_id", "scenario_name"])
    assert anchor.loc[("total_nltf_net_revenue", "current_basecase"), "data_scope"] == "actual_anchor"
    assert anchor.loc[("total_nltf_net_revenue", "current_basecase"), "source_file"] == "mbu26_annual_spine.csv"

    assert set(bridge["bridge_status"].dropna().astype(str).unique()) == {"available"}
    replacements = bridge[bridge["component_type"].astype(str).eq("replacement_line")]
    replacement_streams = {
        "gross_ped_revenue",
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue",
    }
    assert set(replacements["stream"].unique()) == replacement_streams
    replacement_counts = replacements.groupby(["period", "scenario_name", "fed_path"])["stream"].agg(lambda values: set(values))
    assert replacement_counts.map(lambda values: values == replacement_streams).all()

    assert not audit.empty
    assert {2024, 2025, 2026, 2027}.issubset(set(pd.to_numeric(audit["june_year"], errors="coerce").dropna().astype(int)))
    assert {
        "series_id",
        "trace_name",
        "trace_type",
        "trace_role",
        "trace_source",
        "source_file",
        "source_cell",
        "formula",
        "model_id",
        "replacement_only",
        "actual_quarters",
        "forecast_quarters",
        "anchor_flag",
        "nowcast_flag",
    }.issubset(audit.columns)

    assert set(line_reconciliation["source_path"].dropna().unique()) == {
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
    }
    required_lines = {
        "Light RUC net km",
        "Heavy RUC net km",
        "Light BEV RUC net km",
        "Heavy BEV RUC net km",
        "PHEV RUC net km",
        "PED volume",
        "Light petrol VKT",
        "PED VKT per capita",
        "TUC GTK",
        "Light RUC net revenue",
        "Heavy RUC net revenue",
        "Light BEV RUC net revenue",
        "Heavy BEV RUC net revenue",
        "PHEV RUC net revenue",
        "RUC refunds",
        "Gross RUC",
        "RUC admin",
        "RUC net admin",
        "RUC net admin/refunds",
        "Gross PED",
        "LPG",
        "CNG",
        "Gross FED",
        "FED refunds",
        "Net FED",
        "MR1",
        "MR2",
        "MR13",
        "Gross MVR",
        "MVR admin",
        "MVR net admin & COO",
        "MVR refunds",
        "MVR net admin/refunds/COO",
        "TUC net revenue",
        "Total gross revenues",
        "Total admin fees",
        "Total revenues net of admin fees",
        "Total refunds",
        "Total NLTF revenue",
    }
    for source_path in ["MBU26 official", "Current finalist Base case", "Current finalist High population/comparison"]:
        path_rows = line_reconciliation[line_reconciliation["source_path"].astype(str).eq(source_path)]
        assert required_lines.issubset(set(path_rows["line_label"].astype(str)))
    for source_path in ["Current finalist Base case", "Current finalist High population/comparison"]:
        path_rows = line_reconciliation[line_reconciliation["source_path"].astype(str).eq(source_path)]
        assert "Current finalist Light RUC total modelled km" in set(path_rows["line_label"].astype(str))
    assert "light_petrol_vkt_per_capita" not in set(line_reconciliation["series_id"].dropna().astype(str))

    required_stack_cols = {
        "composition_mode",
        "source_path",
        "FY",
        "section",
        "line_label",
        "series_id",
        "value",
        "signed_contribution",
        "stack_value",
        "stack_total_by_FY",
        "overlay_total_value",
        "overlay_series_id",
        "overlay_label",
        "stack_overlay_residual",
        "stack_overlay_status",
        "unit",
        "row_role",
        "stack_role",
        "formula_role",
        "raw_value",
        "source_file",
        "source_cell",
        "formula",
        "stack_value_clean",
        "clean_stack_value",
        "chart_visible",
        "legend_visible",
        "net_effect_group",
        "clean_stack_total_by_FY",
        "clean_overlay_total_value",
        "clean_overlay_residual",
        "clean_overlay_status",
        "replacement_flag",
        "model_id",
        "quarter_composition",
        "actual_quarters",
        "forecast_quarters",
        "residual_vs_official",
        "stack_balance_residual",
        "formula_residual_status",
    }
    assert required_stack_cols.issubset(stack_components.columns)
    assert list(stack_components["composition_mode"].dropna().astype(str).drop_duplicates()) == [
        "Gross-to-net bridge audit",
        "Gross contribution stack",
    ]
    assert set(stack_components["source_path"].dropna().unique()) == {
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
    }
    required_stack_lines = set(required_lines).difference({"MR13"})
    required_stack_lines.update({"MR13/COO", "RUC refunds gross add-back", "MR13/COO gross add-back"})
    for source_path in ["MBU26 official", "Current finalist Base case", "Current finalist High population/comparison"]:
        path_rows = stack_components[stack_components["source_path"].astype(str).eq(source_path)]
        assert required_stack_lines.issubset(set(path_rows["line_label"].astype(str)))
        assert "Total RUC+PED" in set(path_rows["line_label"].astype(str))
    assert "light_petrol_vkt_per_capita" not in set(stack_components["series_id"].dropna().astype(str))
    aggregate_series = {
        "gross_ruc_revenue",
        "ruc_revenue_net_admin",
        "total_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
        "gross_fed_revenue",
        "net_fed_revenue",
        "gross_mvr_revenue",
        "mvr_revenue_net_admin_coo",
        "net_mvr_revenue",
        "total_gross_revenue",
        "total_admin_fees",
        "total_revenue_net_admin",
        "total_refunds",
        "total_nltf_net_revenue",
    }
    assert set(
        stack_components.loc[
            stack_components["stack_role"].astype(str).eq("aggregate_overlay"),
            "series_id",
        ].astype(str)
    ).issuperset(aggregate_series)
    assert stack_components[
        stack_components["series_id"].astype(str).isin(aggregate_series)
        & stack_components["stack_role"].astype(str).isin(["component_positive", "component_negative", "offset_not_stacked"])
    ].empty
    assert stack_components.loc[
        stack_components["stack_role"].astype(str).eq("aggregate_overlay"),
        "stack_value",
    ].isna().all()
    fy2026_mbu26 = stack_components[
        stack_components["source_path"].astype(str).eq("MBU26 official")
        & stack_components["composition_mode"].astype(str).eq("Gross contribution stack")
        & pd.to_numeric(stack_components["FY"], errors="coerce").eq(2026)
    ]
    assert fy2026_mbu26.set_index("series_id").loc["gross_fed_revenue", "stack_role"] == "aggregate_overlay"
    assert fy2026_mbu26.set_index("series_id").loc["gross_ped_revenue", "stack_role"] == "component_positive"
    assert fy2026_mbu26.set_index("series_id").loc["gross_lpg_revenue", "stack_role"] == "component_positive"
    assert fy2026_mbu26.set_index("series_id").loc["gross_cng_revenue", "stack_role"] == "component_positive"
    assert fy2026_mbu26.set_index("series_id").loc["fed_refunds", "stack_role"] == "audit_context"
    assert fy2026_mbu26.set_index("series_id").loc["ruc_refunds", "stack_role"] == "component_positive"
    assert fy2026_mbu26.set_index("series_id").loc["coo_revenue", "stack_role"] == "component_positive"
    assert "offset_not_stacked" not in set(stack_components["stack_role"].dropna().astype(str))
    negative_rows = stack_components[stack_components["stack_role"].astype(str).eq("component_negative")].copy()
    assert not negative_rows.empty
    assert pd.to_numeric(negative_rows["signed_contribution"], errors="coerce").to_numpy() == pytest.approx(
        -pd.to_numeric(negative_rows["value"], errors="coerce").to_numpy()
    )
    bridge_offsets = stack_components[
        stack_components["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
        & stack_components["series_id"].astype(str).isin(["coo_revenue", "ruc_refunds"])
    ]
    assert set(bridge_offsets["stack_role"].dropna().astype(str)) == {"component_negative"}
    assert pd.to_numeric(bridge_offsets["stack_value"], errors="coerce").to_numpy() == pytest.approx(
        -pd.to_numeric(bridge_offsets["value"], errors="coerce").to_numpy()
    )
    assert pd.to_numeric(bridge_offsets["clean_stack_value"], errors="coerce").to_numpy() == pytest.approx(0.0)
    assert not bridge_offsets["chart_visible"].fillna(True).astype(bool).any()
    assert not bridge_offsets["legend_visible"].fillna(True).astype(bool).any()
    bridge_addbacks = stack_components[
        stack_components["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
        & stack_components["series_id"].astype(str).isin(["coo_gross_mvr_addback", "ruc_refunds_gross_addback"])
    ]
    assert set(bridge_addbacks["stack_role"].dropna().astype(str)) == {"component_positive"}
    assert set(bridge_addbacks["formula_role"].dropna().astype(str)) == {"gross_addback"}
    assert pd.to_numeric(bridge_addbacks["stack_value"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(bridge_addbacks["value"], errors="coerce").to_numpy()
    )
    assert pd.to_numeric(bridge_addbacks["clean_stack_value"], errors="coerce").to_numpy() == pytest.approx(0.0)
    assert not bridge_addbacks["chart_visible"].fillna(True).astype(bool).any()
    assert not bridge_addbacks["legend_visible"].fillna(True).astype(bool).any()
    assert set(
        stack_components.loc[
            stack_components["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
            & stack_components["series_id"].astype(str).isin(["ruc_refunds", "ruc_refunds_gross_addback"]),
            "net_effect_group",
        ].dropna().astype(str)
    ) == {"ruc_refunds_internal_zero_net_pair"}
    assert set(
        stack_components.loc[
            stack_components["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
            & stack_components["series_id"].astype(str).isin(["coo_revenue", "coo_gross_mvr_addback"]),
            "net_effect_group",
        ].dropna().astype(str)
    ) == {"mvr_mr13_coo_internal_zero_net_pair"}
    stack_residuals = stack_components[["source_path", "composition_mode", "FY", "stack_overlay_residual", "stack_overlay_status"]].drop_duplicates()
    assert set(stack_residuals["stack_overlay_status"].dropna().astype(str)) == {"balanced"}
    assert pd.to_numeric(stack_residuals["stack_overlay_residual"], errors="coerce").abs().max() <= 1.0
    component_sums = (
        stack_components[stack_components["stack_role"].isin(["component_positive", "component_negative"])]
        .groupby(["source_path", "composition_mode", "FY"])["stack_value"]
        .sum()
    )
    bridge_totals = stack_components[
        stack_components["composition_mode"].eq("Gross-to-net bridge audit")
        & stack_components["series_id"].eq("total_nltf_net_revenue")
    ].set_index(["source_path", "composition_mode", "FY"])["value"]
    gross_totals = stack_components[
        stack_components["composition_mode"].eq("Gross contribution stack")
        & stack_components["series_id"].eq("total_gross_revenue")
    ].set_index(["source_path", "composition_mode", "FY"])["value"]
    target_totals = pd.concat([bridge_totals, gross_totals])
    diff = pd.to_numeric(component_sums, errors="coerce") - pd.to_numeric(target_totals, errors="coerce")
    assert diff.abs().max() <= 1.0
    clean_component_sums = (
        stack_components[
            stack_components["stack_role"].isin(["component_positive", "component_negative"])
            & stack_components["chart_visible"].fillna(False).astype(bool)
        ]
        .groupby(["source_path", "composition_mode", "FY"])["clean_stack_value"]
        .sum()
    )
    clean_diff = pd.to_numeric(clean_component_sums, errors="coerce") - pd.to_numeric(target_totals, errors="coerce")
    assert clean_diff.abs().max() <= 1.0
    clean_status = stack_components[["source_path", "composition_mode", "FY", "clean_overlay_residual", "clean_overlay_status"]].drop_duplicates()
    assert set(clean_status["clean_overlay_status"].dropna().astype(str)) == {"balanced"}
    assert pd.to_numeric(clean_status["clean_overlay_residual"], errors="coerce").abs().max() <= 1.0
    overlay_targets = stack_components[["composition_mode", "overlay_series_id", "overlay_label"]].drop_duplicates()
    assert set(overlay_targets[overlay_targets["composition_mode"].eq("Gross-to-net bridge audit")]["overlay_series_id"]) == {"total_nltf_net_revenue"}
    assert set(overlay_targets[overlay_targets["composition_mode"].eq("Gross contribution stack")]["overlay_series_id"]) == {"total_gross_revenue"}
    current_stack = stack_components[stack_components["source_path"].astype(str).str.startswith("Current finalist")]
    current_pre_forecast = current_stack[
        pd.to_numeric(current_stack["FY"], errors="coerce").le(2025)
        & current_stack["row_role"].astype(str).isin(["leaf", "deduction", "replacement_line"])
    ]
    assert set(current_pre_forecast["source_file"].dropna().astype(str)) == {"mbu26_annual_spine.csv"}
    assert set(current_pre_forecast["source_basis"].dropna().astype(str)) == {"MBU26 actual anchor"}
    assert not current_pre_forecast["source_file"].astype(str).str.contains("forecast_scenario", case=False).any()
    assert current_pre_forecast["forecast_quarters"].fillna("").astype(str).str.strip().eq("").all()
    current_fy2026_replacements = current_stack[
        pd.to_numeric(current_stack["FY"], errors="coerce").eq(2026)
        & current_stack["replacement_flag"].astype(str).str.lower().isin(["true", "1"])
    ]
    assert set(current_fy2026_replacements["actual_quarters"].dropna().astype(str)) == {"2025Q3; 2025Q4"}
    assert set(current_fy2026_replacements["forecast_quarters"].dropna().astype(str)) == {"2026Q1; 2026Q2"}
    current_replacements = set(
        current_stack.loc[
            current_stack["replacement_flag"].astype(str).str.lower().isin(["true", "1"]),
            "series_id",
        ].astype(str)
    )
    assert current_replacements == replacement_streams
    stack_text = stack_components.astype(str).to_csv(index=False)
    assert "C:\\Users" not in stack_text
    assert "Downloads" not in stack_text
    assert "OneDrive" not in stack_text
    assert ".xlsx" not in stack_text

    assert {
        "source_label",
        "source_series_id",
        "runtime_series_id",
        "dashboard_label",
        "unit",
        "source_row",
        "source_cell",
        "alias_reason",
        "status",
    }.issubset(alias_audit.columns)
    ped_alias = alias_audit[alias_audit["source_series_id"].astype(str).eq("light_petrol_vkt_per_capita")].iloc[0]
    assert ped_alias["runtime_series_id"] == "ped_vkt_per_capita"
    assert ped_alias["dashboard_label"] == "PED VKT per capita"
    assert ped_alias["status"] == "canonical_mapping"

    required_fan_availability_cols = {
        "series_id",
        "series_label",
        "fan_source",
        "available",
        "reason",
        "source_file",
        "model_id",
        "horizon_scope",
        "interpretation",
    }
    required_fan_band_cols = {
        "series_id",
        "fan_source",
        "scenario_name",
        "FY",
        "period",
        "central",
        "lower50",
        "upper50",
        "lower80",
        "upper80",
        "unit",
        "method",
        "source_file",
        "model_id",
    }
    assert required_fan_availability_cols.issubset(fan_availability.columns)
    assert required_fan_band_cols.issubset(fan_bands.columns)
    assert set(fan_availability["series_id"].dropna().astype(str)) == dashboard_series
    for series_id in ["ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"]:
        rows = fan_availability[fan_availability["series_id"].astype(str).eq(series_id)]
        current_row = rows[rows["fan_source"].astype(str).eq(FAN_SOURCE_CURRENT_BACKTEST)].iloc[0]
        assert str(current_row["available"]).lower() in {"true", "1"}
        assert "annual_predictions.parquet" in current_row["source_file"]
        band_rows = fan_bands[
            fan_bands["series_id"].astype(str).eq(series_id)
            & fan_bands["fan_source"].astype(str).eq(FAN_SOURCE_CURRENT_BACKTEST)
        ]
        assert not band_rows.empty
        assert band_rows["method"].astype(str).eq("empirical_current_finalist_annual_backtest_error").all()
    for series_id in ["gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"]:
        current_row = fan_availability[
            fan_availability["series_id"].astype(str).eq(series_id)
            & fan_availability["fan_source"].astype(str).eq(FAN_SOURCE_CURRENT_BACKTEST)
        ].iloc[0]
        assert str(current_row["available"]).lower() in {"true", "1"}
        assert "deterministic" in current_row["interpretation"].lower()
        assert "excludes" in current_row["interpretation"].lower()
    total_nltf_current = fan_availability[
        fan_availability["series_id"].astype(str).eq("total_nltf_net_revenue")
        & fan_availability["fan_source"].astype(str).eq(FAN_SOURCE_CURRENT_BACKTEST)
    ].iloc[0]
    assert str(total_nltf_current["available"]).lower() in {"false", "0"}
    assert "not been propagated" in total_nltf_current["reason"]
    assert fan_bands[
        fan_bands["series_id"].astype(str).eq("total_nltf_net_revenue")
        & fan_bands["fan_source"].astype(str).eq(FAN_SOURCE_CURRENT_BACKTEST)
    ].empty
    assert not fan_bands[fan_bands["fan_source"].astype(str).eq(FAN_SOURCE_SCENARIO_SPREAD)].empty
    assert fan_bands.loc[fan_bands["fan_source"].astype(str).eq(FAN_SOURCE_SCENARIO_SPREAD), "method"].astype(str).eq(
        "scenario_spread_not_probabilistic"
    ).all()
    assert not fan_bands.loc[fan_bands["fan_source"].astype(str).eq(FAN_SOURCE_SCENARIO_SPREAD), "method"].astype(str).str.contains(
        "probability|confidence", case=False
    ).any()
    assert not fan_bands[fan_bands["fan_source"].astype(str).eq(FAN_SOURCE_MBU26_ARCHIVED)].empty
    ped_mbu26 = fan_availability[
        fan_availability["series_id"].astype(str).eq("ped_vkt_per_capita")
        & fan_availability["fan_source"].astype(str).eq(FAN_SOURCE_MBU26_ARCHIVED)
    ].iloc[0]
    assert str(ped_mbu26["available"]).lower() in {"false", "0"}
    assert "not PED VKT per capita" in ped_mbu26["reason"]

    base_lines = line_reconciliation[
        line_reconciliation["source_path"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(2026)
    ].set_index("series_id")
    value = lambda series_id: float(base_lines.loc[series_id, "value"])
    drift_base_2026 = optimized_drift[
        optimized_drift["source_path"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(optimized_drift["FY"], errors="coerce").eq(2026)
    ].iloc[0]
    assert value("current_light_ruc_total_modelled_km") == pytest.approx(
        float(drift_base_2026["current_L_t_total_light_ruc_km"]),
        abs=1e-9,
    )
    assert value("light_ruc_net_km") == pytest.approx(float(drift_base_2026["current_conventional_light_km"]), abs=1e-9)
    assert value("light_bev_ruc_net_km") == pytest.approx(float(drift_base_2026["current_BEV_km"]), abs=1e-9)
    assert value("phev_ruc_net_km") == pytest.approx(float(drift_base_2026["current_PHEV_km"]), abs=1e-9)
    assert value("gross_ped_revenue") == pytest.approx(float(drift_base_2026["current_PED_revenue"]), abs=1e-9)
    assert float(drift_base_2026["component_sum_km"]) == pytest.approx(float(drift_base_2026["current_U_t_light_mobility_km"]), abs=1e-6)
    assert float(drift_base_2026["current_PED_revenue"]) != pytest.approx(float(drift_base_2026["old_light_only_PED_revenue"]), abs=1e-6)
    assert value("gross_fed_revenue") == pytest.approx(value("gross_ped_revenue") + value("gross_lpg_revenue") + value("gross_cng_revenue"), abs=1e-9)
    assert value("net_fed_revenue") == pytest.approx(value("gross_fed_revenue") - value("fed_refunds"), abs=1e-9)
    assert value("gross_ruc_revenue") == pytest.approx(
        value("light_ruc_net_revenue")
        + value("heavy_ruc_net_revenue")
        + value("light_bev_ruc_net_revenue")
        + value("heavy_bev_ruc_net_revenue")
        + value("phev_ruc_net_revenue")
        + value("ruc_refunds"),
        abs=1e-9,
    )
    assert value("total_ruc_net_revenue") == pytest.approx(value("gross_ruc_revenue") - value("ruc_admin_revenue") - value("ruc_refunds"), abs=1e-9)
    assert value("total_nltf_net_revenue") == pytest.approx(value("total_revenue_net_admin") - value("total_refunds"), abs=1e-9)
    assert value("gross_ped_revenue") > 2000
    assert value("total_nltf_net_revenue") > 4500
    for series_id in ["gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"]:
        assert float(fy2026.loc[(series_id, "current_basecase"), "value"]) == pytest.approx(value(series_id), abs=1e-9)

    base_lines_2029 = line_reconciliation[
        line_reconciliation["source_path"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(2029)
    ].set_index("series_id")
    drift_base_2029 = optimized_drift[
        optimized_drift["source_path"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(optimized_drift["FY"], errors="coerce").eq(2029)
    ].iloc[0]
    fixed_light_base_2029 = ev_phev_drift[
        ev_phev_drift["source_path"].astype(str).eq("Current finalist Base case")
        & ev_phev_drift["lambda_mode"].astype(str).eq("fixed_light_only")
        & pd.to_numeric(ev_phev_drift["FY"], errors="coerce").eq(2029)
    ].iloc[0]
    assert float(drift_base_2029["weighted_sse"]) < float(fixed_light_base_2029["weighted_sse"])
    old_2029_migration_bundle = (
        float(drift_base_2029["old_light_only_PED_revenue"])
        + float(drift_base_2029["old_light_only_light_ruc_net_revenue"])
        + float(drift_base_2029["old_light_only_light_bev_ruc_net_revenue"])
        + float(drift_base_2029["old_light_only_phev_ruc_net_revenue"])
    )
    current_2029_migration_bundle = (
        float(drift_base_2029["current_PED_revenue"])
        + float(drift_base_2029["current_light_ruc_net_revenue"])
        + float(drift_base_2029["current_light_bev_ruc_net_revenue"])
        + float(drift_base_2029["current_phev_ruc_net_revenue"])
    )
    current_2029_total_nltf = float(base_lines_2029.loc["total_nltf_net_revenue", "value"])
    light_only_2029_total_nltf = current_2029_total_nltf - current_2029_migration_bundle + old_2029_migration_bundle
    assert current_2029_migration_bundle != pytest.approx(old_2029_migration_bundle, abs=1e-6)
    assert current_2029_total_nltf != pytest.approx(light_only_2029_total_nltf, abs=1e-6)
    assert current_2029_total_nltf - light_only_2029_total_nltf == pytest.approx(
        current_2029_migration_bundle - old_2029_migration_bundle,
        abs=1e-6,
    )

    base_cutoff_line = line_reconciliation[
        line_reconciliation["source_path"].astype(str).eq("Current finalist Base case")
        & line_reconciliation["series_id"].astype(str).eq("current_light_ruc_total_modelled_km")
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").between(2046, runtime_cutoff_fy, inclusive="both")
    ].copy()
    base_cutoff_line["FY_numeric"] = pd.to_numeric(base_cutoff_line["FY"], errors="coerce").astype(int)
    assert set(base_cutoff_line["FY_numeric"]) == set(range(2046, runtime_cutoff_fy + 1))
    assert base_cutoff_line["value_status"].astype(str).ne("extrapolated_model_extension").all()
    assert pd.to_numeric(
        line_reconciliation.loc[
            line_reconciliation["source_path"].astype(str).str.startswith("Current finalist"),
            "FY",
        ],
        errors="coerce",
    ).max() == runtime_cutoff_fy

    current_residuals = residuals[
        residuals["source_path"].astype(str).str.startswith("Current finalist")
        & residuals["output_series_id"].isin(["gross_fed_revenue", "net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"])
    ]
    assert set(current_residuals["status"].dropna().unique()) == {"reconciled"}


def test_ped_bridge_modes_materialize_raw_optimized_and_reconcile() -> None:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None
    audit = pack.ped_revenue_bridge_audit
    assert not audit.empty
    required = {
        "ped_vktpc_model",
        "raw_light_petrol_vkt",
        "raw_light_petrol_vkt_million_km",
        "optimized_light_petrol_vkt",
        "optimized_light_petrol_vkt_million_km",
        "optimization_delta",
        "optimization_delta_million_km",
        "ped_volume_raw",
        "ped_volume_raw_million_litres",
        "ped_volume_optimized",
        "ped_volume_optimized_million_litres",
        "gross_ped_revenue_raw",
        "gross_ped_revenue_raw_million_nzd",
        "gross_ped_revenue_optimized",
        "gross_ped_revenue_optimized_million_nzd",
    }
    assert required.issubset(audit.columns)
    current_base = audit[audit["source_path"].astype(str).eq("Current finalist Base case")].copy()
    assert pd.to_numeric(current_base["optimization_delta_million_km"], errors="coerce").abs().max() > 100
    assert pd.to_numeric(current_base["raw_light_petrol_vkt_million_km"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(current_base["ped_vktpc_model"], errors="coerce")
            * pd.to_numeric(current_base["scenario_population"], errors="coerce")
            / 1_000_000.0
        ).to_numpy()
    )
    assert pd.to_numeric(current_base["ped_volume_raw_million_litres"], errors="coerce").to_numpy() == pytest.approx(
        (
            pd.to_numeric(current_base["raw_light_petrol_vkt_million_km"], errors="coerce")
            * pd.to_numeric(current_base["base_litres_per_100km"], errors="coerce")
            / 100.0
        ).to_numpy()
    )
    assert audit["population_fallback_flag"].fillna(False).astype(bool).any()
    assert not audit.astype(str).stack().str.contains("C:\\Users", regex=False).any()
    assert not audit.astype(str).stack().str.contains("Downloads", regex=False).any()

    default = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
    )
    for key, value_column, original in [
        ("chart_rows", "value", pack.revenue_chart_rows),
        ("line_reconciliation", "value", pack.revenue_line_reconciliation),
        ("revenue_bridge_components", "component_value", pack.revenue_bridge_components),
        ("future_revenue_forecasts", "revenue_forecast_nzd", pack.future_revenue_forecasts),
    ]:
        assert pd.to_numeric(default[key][value_column], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(original[value_column], errors="coerce").to_numpy(),
            abs=0,
        )

    for mode in ["raw_model", "blend_25", "blend_50", "blend_75", PED_BRIDGE_DEFAULT_MODE]:
        result = apply_ped_bridge_mode_layer(
            chart_rows=pack.revenue_chart_rows,
            line_reconciliation=pack.revenue_line_reconciliation,
            bridge_components=pack.revenue_bridge_components,
            future_revenue_forecasts=pack.future_revenue_forecasts,
            ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
            bridge_mode=mode,
        )
        mode_audit = result["ped_revenue_bridge_audit"]
        assert pd.to_numeric(mode_audit["ped_volume_million_litres"], errors="coerce").to_numpy() == pytest.approx(
            (
                pd.to_numeric(mode_audit["adjusted_light_petrol_vkt_million_km"], errors="coerce")
                * pd.to_numeric(mode_audit["base_litres_per_100km"], errors="coerce")
                / 100.0
            ).to_numpy()
        )
        current_residuals = result["revenue_formula_residuals"][
            result["revenue_formula_residuals"]["source_path"].astype(str).str.startswith("Current finalist")
        ]
        assert set(current_residuals["status"].dropna().astype(str)) == {"reconciled"}
        official_original = pack.revenue_chart_rows[
            pack.revenue_chart_rows["trace_role"].astype(str).eq("official_external_comparator")
        ].copy()
        official_adjusted = result["chart_rows"][
            result["chart_rows"]["trace_role"].astype(str).eq("official_external_comparator")
        ].copy()
        assert pd.to_numeric(official_adjusted["value"], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(official_original["value"], errors="coerce").to_numpy(),
            abs=0,
        )


def test_ped_efficiency_sensitivity_noops_baseline_and_reconciles_rollups() -> None:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None

    baseline = apply_ped_efficiency_sensitivity(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        ped_efficiency_scenarios=pack.ped_efficiency_scenarios,
        scenario_id=PED_EFFICIENCY_BASELINE_SCENARIO_ID,
    )
    for key, value_column, original in [
        ("chart_rows", "value", pack.revenue_chart_rows),
        ("line_reconciliation", "value", pack.revenue_line_reconciliation),
        ("revenue_bridge_components", "component_value", pack.revenue_bridge_components),
        ("future_revenue_forecasts", "revenue_forecast_nzd", pack.future_revenue_forecasts),
    ]:
        assert pd.to_numeric(baseline[key][value_column], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(original[value_column], errors="coerce").to_numpy(),
            abs=0,
        )

    sensitivity = apply_ped_efficiency_sensitivity(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        ped_efficiency_scenarios=pack.ped_efficiency_scenarios,
        scenario_id="efficiency_1_0pct_pa",
    )
    adjustment = sensitivity["ped_efficiency_adjustment"]
    assert not adjustment.empty
    assert adjustment["efficiency_label"].astype(str).eq("1.0% p.a.").all()
    assert pd.to_numeric(adjustment["adjusted_litres_per_100km"], errors="coerce").lt(
        pd.to_numeric(adjustment["base_litres_per_100km"], errors="coerce")
    ).all()
    assert pd.to_numeric(adjustment["adjusted_ped_volume_million_litres"], errors="coerce").lt(
        pd.to_numeric(adjustment["baseline_ped_volume_million_litres"], errors="coerce")
    ).all()
    assert pd.to_numeric(adjustment["adjusted_gross_ped_revenue_million_nzd"], errors="coerce").lt(
        pd.to_numeric(adjustment["baseline_gross_ped_revenue_million_nzd"], errors="coerce")
    ).all()
    assert pd.to_numeric(adjustment["total_nltf_net_revenue_delta_million_nzd"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(adjustment["gross_ped_revenue_delta_million_nzd"], errors="coerce").to_numpy()
    )
    current_residuals = sensitivity["revenue_formula_residuals"][
        sensitivity["revenue_formula_residuals"]["source_path"].astype(str).str.startswith("Current finalist")
    ]
    assert set(current_residuals["status"].dropna().astype(str)) == {"reconciled"}

    adjusted_chart = sensitivity["chart_rows"]
    official_original = pack.revenue_chart_rows[
        pack.revenue_chart_rows["trace_role"].astype(str).eq("official_external_comparator")
    ].copy()
    official_adjusted = adjusted_chart[
        adjusted_chart["trace_role"].astype(str).eq("official_external_comparator")
    ].copy()
    assert pd.to_numeric(official_adjusted["value"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(official_original["value"], errors="coerce").to_numpy(),
        abs=0,
    )
    unchanged_ev_phev = pack.revenue_chart_rows[
        pack.revenue_chart_rows["trace_role"].astype(str).eq("in_house_current_finalist")
        & pack.revenue_chart_rows["series_id"].astype(str).isin(
            ["light_bev_ruc_net_km", "phev_ruc_net_km", "light_bev_ruc_net_revenue", "phev_ruc_net_revenue"]
        )
    ].copy()
    adjusted_ev_phev = adjusted_chart.loc[unchanged_ev_phev.index]
    assert pd.to_numeric(adjusted_ev_phev["value"], errors="coerce").to_numpy() == pytest.approx(
        pd.to_numeric(unchanged_ev_phev["value"], errors="coerce").to_numpy(),
        abs=0,
    )


def test_revenue_sensitivity_layer_off_preserves_runtime_values() -> None:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None

    baseline = apply_revenue_sensitivity_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        sensitivity_config=pack.sensitivity_config,
    )
    for key, value_column, original in [
        ("chart_rows", "value", pack.revenue_chart_rows),
        ("line_reconciliation", "value", pack.revenue_line_reconciliation),
        ("revenue_bridge_components", "component_value", pack.revenue_bridge_components),
        ("future_revenue_forecasts", "revenue_forecast_nzd", pack.future_revenue_forecasts),
    ]:
        assert pd.to_numeric(baseline[key][value_column], errors="coerce").to_numpy() == pytest.approx(
            pd.to_numeric(original[value_column], errors="coerce").to_numpy(),
            abs=0,
        )
    assert pd.to_numeric(baseline["sensitivity_impact_audit"]["delta"], errors="coerce").abs().max() == pytest.approx(0.0, abs=0)


def test_revenue_sensitivity_efficiency_lowers_ped_revenue_holding_vkt_fixed() -> None:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None

    sensitivity = apply_revenue_sensitivity_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        sensitivity_config=pack.sensitivity_config,
        fleet_efficiency="Med",
    )
    audit = sensitivity["sensitivity_impact_audit"]
    rows = audit[
        audit["source_path"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(audit["FY"], errors="coerce").eq(2029)
    ].set_index("series_id")
    assert rows.loc["light_petrol_vkt", "adjusted"] == pytest.approx(rows.loc["light_petrol_vkt", "baseline"], abs=0)
    assert rows.loc["ped_vkt_per_capita", "adjusted"] == pytest.approx(rows.loc["ped_vkt_per_capita", "baseline"], abs=0)
    assert rows.loc["ped_volume", "adjusted"] < rows.loc["ped_volume", "baseline"]
    assert rows.loc["gross_ped_revenue", "adjusted"] < rows.loc["gross_ped_revenue", "baseline"]
    assert rows.loc["light_ruc_net_km", "adjusted"] == pytest.approx(rows.loc["light_ruc_net_km", "baseline"], abs=0)
    current_residuals = sensitivity["revenue_formula_residuals"][
        sensitivity["revenue_formula_residuals"]["source_path"].astype(str).str.startswith("Current finalist")
    ]
    assert set(current_residuals["status"].dropna().astype(str)) == {"reconciled"}


def test_revenue_sensitivity_pt_shift_preserves_ev_phev_shares() -> None:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None

    sensitivity = apply_revenue_sensitivity_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        sensitivity_config=pack.sensitivity_config,
        pt_mode_shift="Med",
    )
    audit = sensitivity["sensitivity_impact_audit"]
    rows = audit[
        audit["source_path"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(audit["FY"], errors="coerce").eq(2031)
    ].set_index("series_id")
    expected_factor = (1 - 0.005) ** (2031 - 2030 + 1)
    for series_id in ["light_petrol_vkt", "light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]:
        assert rows.loc[series_id, "adjusted"] == pytest.approx(rows.loc[series_id, "baseline"] * expected_factor)
    baseline_total = rows.loc["light_ruc_net_km", "baseline"] + rows.loc["light_bev_ruc_net_km", "baseline"] + rows.loc["phev_ruc_net_km", "baseline"]
    adjusted_total = rows.loc["light_ruc_net_km", "adjusted"] + rows.loc["light_bev_ruc_net_km", "adjusted"] + rows.loc["phev_ruc_net_km", "adjusted"]
    for series_id in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]:
        assert rows.loc[series_id, "adjusted"] / adjusted_total == pytest.approx(rows.loc[series_id, "baseline"] / baseline_total)
    assert rows.loc["heavy_ruc_net_km", "adjusted"] == pytest.approx(rows.loc["heavy_ruc_net_km", "baseline"], abs=0)


def test_revenue_sensitivity_demand_elasticity_responds_to_cost_ratio() -> None:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None

    lower_cost = apply_revenue_sensitivity_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        sensitivity_config=pack.sensitivity_config,
        demand_elasticity="Med",
        cost_per_km_ratio=0.9,
    )["sensitivity_impact_audit"]
    higher_cost = apply_revenue_sensitivity_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        sensitivity_config=pack.sensitivity_config,
        demand_elasticity="Med",
        cost_per_km_ratio=1.1,
    )["sensitivity_impact_audit"]
    for audit, relation in [(lower_cost, "gt"), (higher_cost, "lt")]:
        rows = audit[
            audit["source_path"].astype(str).eq("Current finalist Base case")
            & pd.to_numeric(audit["FY"], errors="coerce").eq(2029)
        ].set_index("series_id")
        for series_id in ["light_petrol_vkt", "light_ruc_net_km", "heavy_ruc_net_km"]:
            if relation == "gt":
                assert rows.loc[series_id, "adjusted"] > rows.loc[series_id, "baseline"]
            else:
                assert rows.loc[series_id, "adjusted"] < rows.loc[series_id, "baseline"]


def test_current_revenue_outlook_runtime_artifact_hashes_are_frozen() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    expected_hashes = {
        "ev_phev_ped_light_drift_assumptions.csv": "576ae24883099bb2d2c6b8a7f0162598818c23b7b6381e1613a05c64cfbaf672",
        "ev_phev_ped_light_drift_assumptions.parquet": "764b23da0eef478baf5733ebfd43bd2d1fad55880e51a5416a9ce9907e11561f",
        "ev_phev_split_assumptions.csv": "f6d678fde5074dd9ec4aa9ed79f10f3f3d02c1a6d72e07f8c050918bfc9f2928",
        "ev_phev_split_assumptions.parquet": "f1b13a03568eda04ac252d4c303d10918359cbc032405ec959e0616b19c2d4f1",
        "fan_availability.csv": "7d8df7d82b99740228350e6aa13f7d09394a693912c9bb4a52e0fbbf13b734d1",
        "fan_availability.parquet": "bcb70fc357dc6b59378915fbef840d9d30120291eb9d8207ee48eb12f2deb719",
        "fan_band_rows.csv": "97b20948b568a649d51e425136bb97d7d1e0037c1244655d48a4aa26589c00a6",
        "fan_band_rows.parquet": "c77dfc913120f9e8caa6003211ecdb85cc6d3e884512fbf7fbf6e1e12b90be5c",
        "future_revenue_forecasts.csv": "31bc0ab32312cfb37598ca0bcd7db7abbab89d259c6785b3a9787208c9bd2c05",
        "future_revenue_forecasts.parquet": "37fd32d0a1e39facca69504b525f1f3c85491f781832b3befbab2ecba700aba0",
        "manifest.json": "1f78bed4fd8c2862393b1b4a3b31e6d5d9544f9cab2c79e2685c1f1c5682a73f",
        "manifest.md": "0d0ffad81aa2f9ab0e8123a05297aaf2b52d40d1b06f9700f2ca1a53977d0a2d",
        "path_trace_status.csv": "9aee7a4e7003ec6541476ca3e4afef6d8586b6c358e41db1c8e06623e5ffcaa3",
        "path_trace_status.parquet": "e66d860fb7532ee4b92285c1ba023c9f8d9469cfdaaaef819415f7cd87c73757",
        "ped_bridge_mode_config.csv": "a818ddaf9c30efe56b9f11121c39296350dd3db8d7db6d9d9288ccad7f9f521a",
        "ped_bridge_mode_config.parquet": "78047d53c62de45a5536e4b118784dea3e0d7af4493bc62b2102a84a5ab79f1e",
        "ped_bridge_shape_fit_metrics.csv": "bdbe8adc30fc3734d594af6ade207d8f0b5525163630d9fce0c23da03d731eff",
        "ped_bridge_shape_fit_metrics.parquet": "9305e5cc4c3cec76d24246f283145750bc964b15e782e302487cc2e19b6b2693",
        "ped_efficiency_scenarios.csv": "e23f4ad04f3b7b4e18eee7d185b4d2fa8d3d54c0542695d1c8be59cd395788b8",
        "ped_efficiency_scenarios.parquet": "6e4c007d3a675a403303b00d117552464e514f7b3c2050bf33dc7c95c2faf325",
        "ped_revenue_bridge_audit.csv": "6c58b4b529ff8a9dd53a491b4450caa6f0a1d6569d4bd7c0fd6a78c3900479f5",
        "ped_revenue_bridge_audit.parquet": "f5f050069cdf943f3c0c7083a84d0f31cf9c763f902d247b361f416f3823970d",
        "revenue_bridge_components.csv": "7e18771e3b6fdea01215a50537a575860ed4de830973c389d0090863f6302126",
        "revenue_bridge_components.parquet": "a9da6f103797d788bca0c37a0be4e5010ffb851e697e64428248d10ff865e627",
        "revenue_chart_rows.csv": "535f963b843dd17b410d259e39a3ac31a911a3d0d54b9073355c64f9a885c4a3",
        "revenue_chart_rows.parquet": "78904ef79caee77a5daa3df8e990ad9559cac316cb9604f9fc5206b54851f88b",
        "revenue_formula_residuals.csv": "1326a0bf31bf50ade7036c525230be17e13e3876845695339ed7a5c5314c2554",
        "revenue_formula_residuals.parquet": "3f82c12a5a6d177a4b327fe3e5ae6efea3d409deb618921bc989a59e185ebf98",
        "revenue_line_reconciliation.csv": "78805e31eef3213bbab94d3449521db64e0d3fb8b59019c62eeb8915e793aede",
        "revenue_line_reconciliation.parquet": "bc2e3cc1835bbae62d83b98247426a15a6cbe39dceb3bc4ff871f6b658a6ba53",
        "revenue_stack_components.csv": "1a3267aac0c600ba8f6d7ac827b9ba405637f1236740faba56f6b325ac266bee",
        "revenue_stack_components.parquet": "a70f4026d7f016c5ab3a00ce2e0c41d7a5fd2ff6e99b85f87f330415710d45d0",
        "row_reconciliation.csv": "d484f5d75cce88e30ce7bcf5dd70058505cc02e5dff93f457a579f119c2fc7ce",
        "row_reconciliation.parquet": "bf2b638920e4b9b00ca4ac00d4263083258ce0d94625943c4e7b3cdf90493dd7",
        "runtime_cutoff_audit.csv": "39afc7458cba7b1a43063453269659fc6e59a53286774fac3ca77e30efc9813d",
        "runtime_cutoff_audit.parquet": "35ff7136b28f33c4b29a48c5230db6df088775f5a87e868d22b7609e0c3b85a5",
        "runtime_trace_audit.csv": "b9dc3802bb27e70db3516fd2455c04e32778190b1d3a952ba78c5ffde7970798",
        "runtime_trace_audit.parquet": "143083376396702d9f842cee15107fcb969bb0e32acf98ba4517bb51a070b540",
        "scenario_feature_lineage.csv": "b123c97090bd282009225a0ac2cfc36226d20017412f820dfeec6af34411b30d",
        "scenario_feature_lineage.parquet": "488d932eba67a1fdd7db3ce9e1cf5aba4874b72088fb53f3989a68798556a025",
        "scenario_input_delta_audit.csv": "c59457c56e9dbfcad284bcdf731d27616f3da766760c9858ec503d3e045e0f13",
        "scenario_input_delta_audit.parquet": "21cc6951d017817ad989fa54521cf323113e734dae9ce321e4bfbbf99d01e538",
        "scenario_input_replay_mismatch_report.csv": "e0708fdc23aca483311515a8488cee029d5a959d4f351f6fe168f64431617c6a",
        "scenario_input_replay_mismatch_report.parquet": "80f060bef98147de0ef5e20f65e02e9d6716a1900ca9b85c089e4a36f31e5749",
        "scenario_role_contract.csv": "ba40738ba8f23a44d11fecbf3a1b04e8111efed741462b3c1067cd6a710e2a39",
        "scenario_role_contract.parquet": "8129514d4c43e898625f74b029aad23d583cfae9b36491ee955ab0a99593b30b",
        "sensitivity_config.csv": "2067f75d07b12d61d0b845b03bf637f0e335dc7074c45fea5e72b74fc63eda64",
        "sensitivity_config.parquet": "2960b8221b4321aafea87db35ac04454a09f5fb421c2c35eb7abe700bf9e0ee6",
        "sensitivity_impact_audit.csv": "2ab42b16e8556f45dfd4fe3f15542b0e13d12bfda3e5221ba632803441fdaae9",
        "sensitivity_impact_audit.parquet": "eae77be5237c40e7b8a905b32e6eed359bdb99e437856a31e1523776a2cc93b2",
        "sensitivity_seed_inputs.csv": "dd2b9766cd253d08c6e65ca36d463b5178020c636b7edcc197ed52aa23679861",
        "sensitivity_seed_inputs.parquet": "eeda21f1cd4ad85044d8bd2a19b8f7e669f78f8ec1d1f63b403744ad852fe3c4",
        "series_alias_audit.csv": "c0330c9918d7e2f4f972d15e8465537c16d96aca607ef253353612cadd62c56d",
        "series_alias_audit.parquet": "9b376147c912748d5a2429abf524799e348a3711d6af89a4b9d1ec287f558918",
        "series_trace_contract.csv": "2eaf18c4c54fc18a21dd68415c0aea041bd174e8d75285409a4bb83034b60e09",
        "series_trace_contract.parquet": "5706036ec8e179dbc31003e6ab6dcd966d0d02216f8c30d5e4f4c48ba36e9d3f",
        "trace_source_contract.csv": "396a97e28c43adc892c438ce92fe16a847d87b0ad91c6f8ec1334416c85a070a",
        "trace_source_contract.parquet": "17fda181174f117be894a0f638c992b988a418a3dba9c08ee77bdfe78b7c8bd9",
    }
    assert {path.name: _sha256(path) for path in sorted(pack_dir.iterdir()) if path.is_file()} == expected_hashes


def test_revenue_outlook_loader_rejects_hash_mismatched_promoted_pack(tmp_path: Path) -> None:
    pack_copy = tmp_path / "current_revenue_outlook"
    shutil.copytree(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, pack_copy)
    chart_csv = pack_copy / "revenue_chart_rows.csv"
    chart_csv.write_text(chart_csv.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="revenue_chart_rows.csv hash mismatch"):
        load_revenue_outlook_pack(pack_copy, repo_root=ROOT)

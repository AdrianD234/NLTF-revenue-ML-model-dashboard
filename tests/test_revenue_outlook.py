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
    REVENUE_OUTLOOK_SCHEMA_VERSION,
    SOURCE_COMPARISON_OUTPUT_DIR_POLICY,
    build_revenue_outlook_pack,
    load_revenue_outlook_pack,
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
    assert manifest["scenario_role_contract"]["repo_relative_path"] == "data/current_revenue_outlook/scenario_role_contract.csv"
    assert "behavioural intensity metric" in manifest["scenario_role_contract"]["note"]
    assert manifest["scenario_inputs"]["status"] == "available"
    assert manifest["scenario_inputs"]["repo_relative_output_dir"] == "data/current_revenue_outlook/scenario_inputs"
    assert manifest["scenario_inputs"]["schema_version"] == "nltf-scenario-input-materializer-v1"
    assert manifest["scenario_inputs"]["row_counts"] == {
        "scenario_input_cells": 15472,
        "scenario_input_long": 15200,
        "scenario_input_wide": 600,
        "scenario_feature_lineage": 14000,
    }
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
        "runtime_trace_audit.csv",
        "runtime_trace_audit.parquet",
        "scenario_feature_lineage.csv",
        "scenario_feature_lineage.parquet",
        "scenario_input_replay_mismatch_report.csv",
        "scenario_input_replay_mismatch_report.parquet",
        "scenario_role_contract.csv",
        "scenario_role_contract.parquet",
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
    scenario_role_contract = pd.read_parquet(pack_dir / "scenario_role_contract.parquet")
    residuals = pd.read_parquet(pack_dir / "revenue_formula_residuals.parquet")
    alias_audit = pd.read_parquet(pack_dir / "series_alias_audit.parquet")
    fan_availability = pd.read_parquet(pack_dir / "fan_availability.parquet")
    fan_bands = pd.read_parquet(pack_dir / "fan_band_rows.parquet")
    scenario_feature_lineage = pd.read_parquet(pack_dir / "scenario_feature_lineage.parquet")
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
    comparison_categories = {
        part.split(":", 1)[1].strip()
        for text in scenario_role_contract["field_classification"].dropna().astype(str)
        for part in text.split(";")
        if ":" in part
    }
    assert {"population/scale", "macro", "price/rate/policy", "behavioural"}.issubset(comparison_categories)
    assert "scenario_input_wide" in str(comparison_revenue_contract["source_basis"])
    assert not scenario_feature_lineage.empty
    assert set(scenario_feature_lineage["stream"].dropna().astype(str)) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    assert set(scenario_feature_lineage["source_status"].dropna().astype(str)) == {"committed_scenario_input"}
    assert not scenario_feature_lineage["fallback_flag"].astype(bool).any()
    assert scenario_feature_lineage["source_artifact"].eq("scenario_inputs/scenario_input_long.parquet").all()
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
    extension_replay = scenario_input_replay[
        scenario_input_replay["scenario_input_status"].astype(str).eq("governed_model_extension_not_replayed_from_workbook")
    ].copy()
    assert not extension_replay.empty
    assert extension_replay["replay_status"].astype(str).eq("not_applicable").all()
    assert set(extension_replay["annual_period"].dropna().astype(str)) == {
        "FY2051",
        "FY2052",
        "FY2053",
        "FY2054",
        "FY2055",
    }
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

    base_extension = line_reconciliation[
        line_reconciliation["source_path"].astype(str).eq("Current finalist Base case")
        & line_reconciliation["series_id"].astype(str).eq("current_light_ruc_total_modelled_km")
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").between(2046, 2055, inclusive="both")
    ].copy()
    base_extension["FY_numeric"] = pd.to_numeric(base_extension["FY"], errors="coerce").astype(int)
    base_extension = base_extension.set_index("FY_numeric")
    extension_slope = (float(base_extension.loc[2050, "value"]) - float(base_extension.loc[2046, "value"])) / 4.0
    for fy in range(2051, 2056):
        assert str(base_extension.loc[fy, "value_status"]) == "extrapolated_model_extension"
        assert float(base_extension.loc[fy, "value"]) == pytest.approx(float(base_extension.loc[2050, "value"]) + extension_slope * (fy - 2050), abs=1e-9)

    current_residuals = residuals[
        residuals["source_path"].astype(str).str.startswith("Current finalist")
        & residuals["output_series_id"].isin(["gross_fed_revenue", "net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"])
    ]
    assert set(current_residuals["status"].dropna().unique()) == {"reconciled"}


def test_current_revenue_outlook_runtime_artifact_hashes_are_frozen() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    expected_hashes = {
        "ev_phev_ped_light_drift_assumptions.csv": "f0a27b5b2e2cf3844ea1c53ed5097a58f8801d8465ee888da39a82e501343bf3",
        "ev_phev_ped_light_drift_assumptions.parquet": "b3c1b3cc4c07bdc041b9f6d3a0c9e7a8a0a21742890811d94955d66af964d9a2",
        "ev_phev_split_assumptions.csv": "6675ca24b2dc1b57d27e69848b62aa2dbb9cf1db48976e3f54942b6f2c305994",
        "ev_phev_split_assumptions.parquet": "e477a4c63d77717c0e7e13d9453057ca50d7a2a8fd76428a37301c0ed1816b00",
        "fan_availability.csv": "7fde72609437ab85136e9e21c8f8b6ba8dfd9cc2024a73f986ddfac299842e3a",
        "fan_availability.parquet": "65597bfb4c267ee4ffc37907c17df15ec4cd6ade24fc5cd65f0947e4469f0267",
        "fan_band_rows.csv": "c58a2e9d78d959e193162a61ca7e85607d5ab62ff7380270637de7b8657cc907",
        "fan_band_rows.parquet": "e8828c2997785eed41df3cf090b9fdd29b22e9b5e97dd3aabfae924b7fcd86f9",
        "future_revenue_forecasts.csv": "4e6ed9d9a6bc4a631970247ccba54deb4d66fa4664d04a5ebccf5bfa24d61a72",
        "future_revenue_forecasts.parquet": "ca3cf207b7da7ece6386e975f9faeeb124f3247ef0e9c1c3f4455a5c81a2508d",
        "manifest.json": "c55e14ba5b6ea011637fd22b23bca295401d8fa8e3a41b6395396a97847aaa43",
        "manifest.md": "0d0ffad81aa2f9ab0e8123a05297aaf2b52d40d1b06f9700f2ca1a53977d0a2d",
        "path_trace_status.csv": "9aee7a4e7003ec6541476ca3e4afef6d8586b6c358e41db1c8e06623e5ffcaa3",
        "path_trace_status.parquet": "e66d860fb7532ee4b92285c1ba023c9f8d9469cfdaaaef819415f7cd87c73757",
        "revenue_bridge_components.csv": "1d2094bf843ac7408fad130c5b4b7eff516080e18b415b4dc61d06220ff11611",
        "revenue_bridge_components.parquet": "c84ea4ceb6215ce5240cab7cb567d5b7f5dd8a929216be2071114c4ba2e9154f",
        "revenue_chart_rows.csv": "4c824790bf6ea1dcd92bd1ead0e8e62423babcc8bc701e4e9bfc6c070c6951d4",
        "revenue_chart_rows.parquet": "253d67cd7f8d75867673862c44ceb8cd16d10a268cbb8b1e5bfc32bbef0d2a07",
        "revenue_formula_residuals.csv": "288c1f6227d82debba6a7d5c98f86a4c92f4287576ab2c1a6c95b450127fbe8a",
        "revenue_formula_residuals.parquet": "90dd6059bdb07e467a28539ef426267e20e2aace7623d3feb9fca180d9497716",
        "revenue_line_reconciliation.csv": "3139d0c0414ce39cadafc4457d9ac4d6a9814d6ed838ce968a3d0bbfaf5a7b0b",
        "revenue_line_reconciliation.parquet": "b9368c4dbc66890a41b7bcc3c4ae0590632504946d01e2e5a5647b00901474b8",
        "revenue_stack_components.csv": "1cfbacf2a0fd598e509edf18ce2339ad875ec2727953f93d5a22689bcf127033",
        "revenue_stack_components.parquet": "feb44d012cc304a7f6040edf419e19dc85989a8836cf5348b29b9a215eb80c91",
        "row_reconciliation.csv": "d484f5d75cce88e30ce7bcf5dd70058505cc02e5dff93f457a579f119c2fc7ce",
        "row_reconciliation.parquet": "bf2b638920e4b9b00ca4ac00d4263083258ce0d94625943c4e7b3cdf90493dd7",
        "runtime_trace_audit.csv": "45c9513db0fe5fe5485ec28c560e757d36733d2e900c194d2b4be9fd6b91afe9",
        "runtime_trace_audit.parquet": "49465b4692e3f0ff60c51ec26c555883ca4e3337ded988e44017464f06720381",
        "scenario_feature_lineage.csv": "fa75ab6a0e4c4c584af3300dd2e887fff579c64877ed2f9adc470fbfdc475243",
        "scenario_feature_lineage.parquet": "7248e6c3142079b1722fbeb18b57393dd82cd3c127c535e08bee2ce139e1d9ab",
        "scenario_input_replay_mismatch_report.csv": "c68bdaa00afceb33fc093d6ef7a69c32d25be0020a7e7a2af95fe64bc84b0008",
        "scenario_input_replay_mismatch_report.parquet": "85f179c019d728114a11990a791ae6c1d31745359f9dfa59ecb807ef316e95da",
        "scenario_role_contract.csv": "d52930b687d18dc5d3f559433bbe84b0c6b2fde4a90a5b1b6daf4b930ff7c39e",
        "scenario_role_contract.parquet": "35296d1e22ee7eaba708414b167516ede5f31104877c13397ffb9bd709d2e8e2",
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

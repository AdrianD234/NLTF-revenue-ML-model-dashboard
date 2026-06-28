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
    assert manifest["ev_phev_split_assumptions"]["allocation_status"] == "not_applied_target_semantics_mismatch"
    assert manifest["target_semantics_audit"]["LIGHT_RUC"]["status"] == "governed_gap_target_matches_conventional_light_not_total_universe"
    assert "conventional Light target semantics" in manifest["data_vintage_manifest_notes"]["light_ruc_target_semantics"]
    assert manifest["revenue_formula_residuals"]["repo_relative_path"] == "data/current_revenue_outlook/revenue_formula_residuals.csv"
    assert manifest["series_alias_audit"]["repo_relative_path"] == "data/current_revenue_outlook/series_alias_audit.csv"
    assert manifest["fan_availability"]["repo_relative_path"] == "data/current_revenue_outlook/fan_availability.csv"
    assert manifest["fan_band_rows"]["repo_relative_path"] == "data/current_revenue_outlook/fan_band_rows.csv"
    assert sorted(manifest["output_hashes"]) == [
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
    residuals = pd.read_parquet(pack_dir / "revenue_formula_residuals.parquet")
    alias_audit = pd.read_parquet(pack_dir / "series_alias_audit.parquet")
    fan_availability = pd.read_parquet(pack_dir / "fan_availability.parquet")
    fan_bands = pd.read_parquet(pack_dir / "fan_band_rows.parquet")

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
    assert not ev_phev_split.empty
    assert not ev_phev_split["used_by_current_finalist"].astype(bool).any()
    evidence = ev_phev_split[pd.to_numeric(ev_phev_split["FY"], errors="coerce").isin([2024, 2025])].set_index("FY")
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
        "light_ruc_net_km",
        "light_ruc_net_revenue",
        "net_fed_revenue",
        "net_mvr_revenue",
        "ped_vkt_per_capita",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
        "total_ruc_net_revenue",
    }
    for series_id, series_rows in displayed.groupby("series_id"):
        traces = set(series_rows["trace_name"].dropna().astype(str))
        assert allowed_traces.issubset(traces), series_id
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
                    "Current finalist High population/comparison",
                ]
            )
            & pd.to_numeric(series_rows["june_year"], errors="coerce").ge(2026)
        ]
        assert {
            "Current finalist Base case",
            "Current finalist High population/comparison",
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
    assert {2026, 2027}.issubset(ped_by_trace["Current finalist High population/comparison"])
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
        ],
        ignore_index=True,
    ).str.cat(sep="\n")
    assert "annual_model_paths.csv" not in runtime_text
    assert "selected_dashboard" not in runtime_text.lower()
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
    assert fy2026.loc[("heavy_ruc_net_revenue", "current_basecase"), "model_id"] == "HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4"
    assert "PED__VNEXT_SOLVED_CONVEX_TOP2" in fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "model_id"]
    assert fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "data_scope"] == "current_nowcast"
    assert fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "actual_quarters"] == "2025Q3; 2025Q4"
    assert fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "forecast_quarters"] == "2026Q1; 2026Q2"
    assert float(fy2026.loc[("gross_ped_revenue", "current_basecase"), "value"]) == pytest.approx(2143.976348, abs=1e-6)
    assert float(fy2026.loc[("gross_fed_revenue", "current_basecase"), "value"]) == pytest.approx(2186.021511, abs=1e-6)
    assert float(fy2026.loc[("net_fed_revenue", "current_basecase"), "value"]) == pytest.approx(2112.753986, abs=1e-6)
    assert float(fy2026.loc[("total_ruc_net_revenue", "current_basecase"), "value"]) == pytest.approx(2075.883320, abs=1e-6)
    assert float(fy2026.loc[("total_nltf_net_revenue", "current_basecase"), "value"]) == pytest.approx(4631.172578, abs=1e-6)

    anchor = current[current["period"].astype(str).eq("FY2025")].set_index(["series_id", "scenario_name"])
    assert anchor.loc[("total_nltf_net_revenue", "current_basecase"), "data_scope"] == "actual_anchor"
    assert anchor.loc[("total_nltf_net_revenue", "current_basecase"), "source_file"] == "mbu26_annual_spine.csv"

    assert set(bridge["bridge_status"].dropna().astype(str).unique()) == {"available"}
    replacements = bridge[bridge["component_type"].astype(str).eq("replacement_line")]
    assert set(replacements["stream"].unique()) == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}
    replacement_counts = replacements.groupby(["period", "scenario_name", "fed_path"])["stream"].agg(lambda values: set(values))
    assert replacement_counts.map(lambda values: values == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}).all()

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
    assert current_replacements == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}
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

    current_residuals = residuals[
        residuals["source_path"].astype(str).str.startswith("Current finalist")
        & residuals["output_series_id"].isin(["gross_fed_revenue", "net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"])
    ]
    assert set(current_residuals["status"].dropna().unique()) == {"reconciled"}


def test_current_revenue_outlook_runtime_artifact_hashes_are_frozen() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    expected_hashes = {
        "ev_phev_split_assumptions.csv": "0c28171411204ced131deb5c65b716963ec94654c0e4a03af132180c9006b259",
        "ev_phev_split_assumptions.parquet": "955d4382cd4f59b2cc403dac04fae3382fa097e437525a035dc770669ac9d613",
        "fan_availability.csv": "3e248fadf746e62affad42d0ca87a3dd232aaed5ee031e6072e7b2f5bd586248",
        "fan_availability.parquet": "05ca6cd3485e6725e571bb8f0b9a04dbc4396a2c52b15b32320b1b43266afc79",
        "fan_band_rows.csv": "891f79fae6e5e1ec7821e4a7b88d6746da5f24fe48ba3eab260ffdac9429799b",
        "fan_band_rows.parquet": "0da58f6bd9f132d9cd5224a29cadb80afc617ee9bd7f9f0971df885865a2a60c",
        "future_revenue_forecasts.csv": "5a8e4024e960a08308654b862acf00c278d79b9a60c899af9b710dbca9f7a0a7",
        "future_revenue_forecasts.parquet": "674ba0173044702cf0e78ab2e79791baca1879709650b2f2a840871e2d497b21",
        "manifest.json": "7e32321b22eb8ca9116f81fb57978872580c6edacdaf4fb21659d91af3fd73d2",
        "manifest.md": "2842343704e8ba363af30cacefec80b9b5471fbaf25932f37afdd24c046252fc",
        "path_trace_status.csv": "9aee7a4e7003ec6541476ca3e4afef6d8586b6c358e41db1c8e06623e5ffcaa3",
        "path_trace_status.parquet": "e66d860fb7532ee4b92285c1ba023c9f8d9469cfdaaaef819415f7cd87c73757",
        "revenue_bridge_components.csv": "a978206d738eebdf689865e41c56e37e69ebb5600c246b62f92975d959456168",
        "revenue_bridge_components.parquet": "2c6250ad2c5a1ea65fb9a8deb302c9500cec7e62f120900acef190cfc9299c42",
        "revenue_chart_rows.csv": "eda813058e64fdb698b5b6b79ec72e4c86bb50a7e215b9a8416f92efe21e5678",
        "revenue_chart_rows.parquet": "2d1fa28b5cf1791f3bff0893d7dd4797c9f45762f5f3b5517c0670f8ab9f1415",
        "revenue_formula_residuals.csv": "47c4d5f95aea4071be32e512b10428d1dad323202e7e189e0aa4b106e0873f0e",
        "revenue_formula_residuals.parquet": "bae3a888bda46a32876e9bfa20d6c197e008cc56b9025eb713a728ae63eade49",
        "revenue_line_reconciliation.csv": "a491632452529408c40987e651abfa8ec8b3d429590b1e2188fc95bf38f0a9aa",
        "revenue_line_reconciliation.parquet": "55fa0fbbe4a06da65f1295e9c9614a697b5dd569108dbbdc8bfa6842b170681b",
        "revenue_stack_components.csv": "f1d15a9bf2584a583a2ea41066e154d9be0bf715f02e159c331a3caaed13ea4e",
        "revenue_stack_components.parquet": "a650648fb578a39d88cc2436db54d8c137fc7c5e159bfd96b759eb8210c4e901",
        "row_reconciliation.csv": "d484f5d75cce88e30ce7bcf5dd70058505cc02e5dff93f457a579f119c2fc7ce",
        "row_reconciliation.parquet": "bf2b638920e4b9b00ca4ac00d4263083258ce0d94625943c4e7b3cdf90493dd7",
        "runtime_trace_audit.csv": "a72f0dc6e03506ca85596accdc105587c6629c9d7bef65ee1a441a344c4c5a9b",
        "runtime_trace_audit.parquet": "f37e7a5f6893f5bba1df795cecd955e0126c3b5aabff71cb3699a7b291998ef8",
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

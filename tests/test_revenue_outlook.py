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
    assert sorted(manifest["output_hashes"]) == [
        "future_revenue_forecasts.csv",
        "future_revenue_forecasts.parquet",
        "path_trace_status.csv",
        "path_trace_status.parquet",
        "revenue_bridge_components.csv",
        "revenue_bridge_components.parquet",
        "revenue_chart_rows.csv",
        "revenue_chart_rows.parquet",
        "row_reconciliation.csv",
        "row_reconciliation.parquet",
        "runtime_trace_audit.csv",
        "runtime_trace_audit.parquet",
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

    runtime_text = pd.concat(
        [
            chart[["source_file", "source", "model_basis"]].astype(str).stack(),
            bridge[["source", "source_basis", "model_id"]].astype(str).stack(),
            future[["source", "model_id"]].astype(str).stack(),
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


def test_current_revenue_outlook_runtime_artifact_hashes_are_frozen() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    expected_hashes = {
        "future_revenue_forecasts.csv": "82135a315d90563e0750a3598dd8b24ce9f1bc9a0fc36faf9bc0a820e45c8443",
        "future_revenue_forecasts.parquet": "b9027e7604157d0e5eface39ebed2b49d849ce24a5868d5d534f89c248d07872",
        "manifest.json": "336baa3d19176aed86b625e821cb022b2223f20ab9ccb8e552899eb73afa8e9b",
        "manifest.md": "cadedd0c392baa81ec71fb0aa79effabbf5faf5adfc5193fe71090edec310742",
        "path_trace_status.csv": "9aee7a4e7003ec6541476ca3e4afef6d8586b6c358e41db1c8e06623e5ffcaa3",
        "path_trace_status.parquet": "e66d860fb7532ee4b92285c1ba023c9f8d9469cfdaaaef819415f7cd87c73757",
        "revenue_bridge_components.csv": "f1227fd260deb40bd621d124b0a64e623a3c9842472320ecb198ab858f20fee2",
        "revenue_bridge_components.parquet": "d722843c704056e3801a8842509ecc27b5c404083a23452291c8fbbab26839ca",
        "revenue_chart_rows.csv": "84618e9ce0ea8994744140e46a06a9b465ca578cfa84281467a5807fef81a8d8",
        "revenue_chart_rows.parquet": "79b079abfa4589b0a249b12d3fa656a4401fbed238758051ef03f21339e98a43",
        "row_reconciliation.csv": "d484f5d75cce88e30ce7bcf5dd70058505cc02e5dff93f457a579f119c2fc7ce",
        "row_reconciliation.parquet": "bf2b638920e4b9b00ca4ac00d4263083258ce0d94625943c4e7b3cdf90493dd7",
        "runtime_trace_audit.csv": "26071ca6944cb2e4070b128ae8305d9d262708d87125b2d464567ea7c1414fbd",
        "runtime_trace_audit.parquet": "095bdee6de33ce2a0c017cf20082ede1074fbfdf5898353a461f28bd2f117348",
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

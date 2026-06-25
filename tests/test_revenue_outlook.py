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
    assert manifest["revenue_source_pack"]["status"] == "source_pack_vendored"
    assert manifest["revenue_source_pack"]["source_pack_version"] == "2026_05_19"
    assert manifest["revenue_source_pack"]["raw_workbook_sha256"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"
    assert manifest["revenue_source_pack"]["selections"]["release_round"] == "BEFU25"
    assert manifest["revenue_source_pack"]["selections"]["series"] == "Total NLTF revenue"
    assert manifest["revenue_source_pack"]["dashboard_default_selections"]["series"] == "Total NLTF revenue"
    assert manifest["revenue_source_pack"]["source_workbook_selections"]["series"] == "Total RUC+PED revenue"
    assert "legacy Total RUC+PED subtotal" in manifest["revenue_source_pack"]["default_selection_policy"]
    assert sorted(manifest["output_hashes"]) == [
        "future_revenue_forecasts.csv",
        "future_revenue_forecasts.parquet",
        "path_trace_status.csv",
        "path_trace_status.parquet",
        "revenue_bridge_components.csv",
        "revenue_bridge_components.parquet",
        "revenue_chart_rows.csv",
        "revenue_chart_rows.parquet",
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

    assert manifest["runtime_pack_type"] == "source_actual_current_finalist_official_comparator"
    assert manifest["bridge_status_by_stream"] == {
        "PED": ["available"],
        "LIGHT_RUC": ["available"],
        "HEAVY_RUC": ["available"],
    }
    assert "workbook model" not in json.dumps(manifest).lower()
    assert "nominal_rate_missing" not in json.dumps(manifest)
    assert "ped_bridge_source_history_missing" not in json.dumps(manifest)

    allowed_traces = {
        "Actual",
        "Current finalist Base case",
        "Current finalist High population/comparison",
        "Official comparator: selected MOT/BEFU",
        "Official comparator: rolling BEFU 1Y",
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
    assert anchor.loc[("total_nltf_net_revenue", "current_basecase"), "source_file"] == "annual_actuals.csv"

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
        "trace_role",
        "source_file",
        "model_id",
        "actual_quarters",
        "forecast_quarters",
        "anchor_flag",
        "nowcast_flag",
    }.issubset(audit.columns)


def test_current_revenue_outlook_runtime_artifact_hashes_are_frozen() -> None:
    pack_dir = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
    expected_hashes = {
        "future_revenue_forecasts.csv": "f9addbed5a596d18c2c51f0a58cb2098ffca9b861d6654f54c28c0da00d938d8",
        "future_revenue_forecasts.parquet": "7f6955ff3147ce03e85a4166ad773dd94356c226a700e42245de6ddda823463b",
        "manifest.json": "f21fbf248814d83ae43b78c7c4945ccb0cb766390c8000b687d8b0d151d21a00",
        "manifest.md": "298acdfe34495afbf0620266cc4c5f0f27bc5fdf89d6050e4e8ad600b84947dd",
        "path_trace_status.csv": "b0b2b2f01c6977e869a21f620485e686c119b1895d29e1c67d12ce7afb9adfe3",
        "path_trace_status.parquet": "65e91a936ae5033d050469d57fbd09bf049edf62e47baa8b2ea670be7f84d97c",
        "revenue_bridge_components.csv": "132a9a0ff3e302ea73194b14b60cc2b2969e519ae74876db2e3878ac6c8bb2e1",
        "revenue_bridge_components.parquet": "b274052e704dae5da0f141c8f4b1dd11131d5165ee75e1d31a776e0c6729a4b5",
        "revenue_chart_rows.csv": "4d52e18fb2e7414419cb4f53b69e9b4fd09eb5b43c51725ec6f972373d8a57e0",
        "revenue_chart_rows.parquet": "4084a32cae2dd43f663415c24aa460b95f8a8a17010f64e7c2e05194663dcfbc",
        "runtime_trace_audit.csv": "405b142d5da3d2a373b96392c98a19c11003db599799b3c0f0fd64c798ce8016",
        "runtime_trace_audit.parquet": "935a752438f027b97c9b34a12205a67d16d270cab9d8c3aedb146a73b3464a87",
        "series_trace_contract.csv": "bbfe7a0fb06569540ee6ad94f5d6f1b8924af0c0490eeebd053eaee30cdd0d16",
        "series_trace_contract.parquet": "6a1ae2a1abf43a68185f1e61e287ef316367ac32da9e70d8f081d1e49e35c311",
        "trace_source_contract.csv": "3a8b3b66da395cad28c74622c12bb43af1a6e035eb5917e9d9e61e52539a50d5",
        "trace_source_contract.parquet": "282d61fc1487883ed6daa126f0fac4bb7da9ddc88d79cbf1fde1dd15b3c7d34c",
    }
    assert {path.name: _sha256(path) for path in sorted(pack_dir.iterdir()) if path.is_file()} == expected_hashes


def test_revenue_outlook_loader_rejects_hash_mismatched_promoted_pack(tmp_path: Path) -> None:
    pack_copy = tmp_path / "current_revenue_outlook"
    shutil.copytree(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, pack_copy)
    chart_csv = pack_copy / "revenue_chart_rows.csv"
    chart_csv.write_text(chart_csv.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="revenue_chart_rows.csv hash mismatch"):
        load_revenue_outlook_pack(pack_copy, repo_root=ROOT)

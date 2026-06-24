from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from model_dashboard.forecast_runner import (
    SHEET_BY_STREAM,
    create_completed_sample_workbook,
    run_forecast_workbook,
    write_forecast_scenario_comparison,
)
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    FUTURE_RATE_COLUMNS,
    REVENUE_OUTLOOK_SCHEMA_VERSION,
    build_revenue_outlook_pack,
    load_revenue_outlook_pack,
    promote_revenue_outlook_pack,
    validate_promotable_comparison,
)


ROOT = Path(__file__).resolve().parents[1]


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
    assert (pack.output_dir / "manifest.json").exists()
    assert (pack.output_dir / "future_revenue_forecasts.parquet").exists()
    assert load_revenue_outlook_pack(pack.output_dir, repo_root=ROOT) is not None

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
    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == REVENUE_OUTLOOK_SCHEMA_VERSION
    assert manifest["repo_relative_output_dir"] == "data/current_revenue_outlook"
    assert manifest["source_hashes"]["model_input_history"]
    assert all(item.get("workbook_sha256") for item in manifest["source_hashes"]["workbooks"])
    for path in pack_dir.iterdir():
        if path.is_file():
            assert path.stat().st_size < 50 * 1024 * 1024

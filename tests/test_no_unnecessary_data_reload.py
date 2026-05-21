from __future__ import annotations

from pathlib import Path

import pandas as pd

import app
from model_dashboard.data_loader import run_signature


def test_cached_load_run_does_not_reread_csv_for_same_signature(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_20260520_000000"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "stage": "final",
                "stream": "PED",
                "variant": "v1",
                "model": "m1",
                "source_family": "family",
                "quarterly_mape": 1.0,
                "annual_mape": 1.0,
            }
        ]
    ).to_csv(run_dir / "final_summary.csv", index=False)

    read_count = {"csv": 0}
    original = pd.read_csv

    def counting_read_csv(*args, **kwargs):
        read_count["csv"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", counting_read_csv)
    app.cached_load_run.clear()
    signature = run_signature(run_dir)

    app.cached_load_run(str(run_dir), signature, app.LOADER_SCHEMA_VERSION)
    app.cached_load_run(str(run_dir), signature, app.LOADER_SCHEMA_VERSION)

    assert read_count["csv"] == 1


def test_cached_load_run_invalidates_when_signature_changes(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_20260520_000000"
    run_dir.mkdir()
    target = run_dir / "final_summary.csv"
    pd.DataFrame([{"stage": "final", "stream": "PED", "quarterly_mape": 1.0, "annual_mape": 1.0}]).to_csv(target, index=False)

    read_count = {"csv": 0}
    original = pd.read_csv

    def counting_read_csv(*args, **kwargs):
        read_count["csv"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", counting_read_csv)
    app.cached_load_run.clear()

    first_signature = run_signature(run_dir)
    app.cached_load_run(str(run_dir), first_signature, app.LOADER_SCHEMA_VERSION)
    pd.DataFrame(
        [
            {"stage": "final", "stream": "PED", "quarterly_mape": 1.0, "annual_mape": 1.0},
            {"stage": "final", "stream": "HEAVY_RUC", "quarterly_mape": 2.0, "annual_mape": 2.0},
        ]
    ).to_csv(target, index=False)
    app.cached_load_run(str(run_dir), run_signature(run_dir), app.LOADER_SCHEMA_VERSION)

    assert read_count["csv"] == 2


def test_cached_load_run_does_not_reparse_workbook_for_same_signature(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run_20260520_000000"
    run_dir.mkdir()
    workbook = run_dir / "autogluon_final_robust_all_streams_results.xlsx"
    pd.DataFrame(
        [
            {
                "stage": "final",
                "stream": "PED",
                "variant": "v1",
                "model": "m1",
                "source_family": "family",
                "quarterly_mape": 1.0,
                "annual_mape": 1.0,
            }
        ]
    ).to_excel(workbook, sheet_name="final_summary", index=False)

    excel_count = {"open": 0}
    original = pd.ExcelFile

    def counting_excel_file(*args, **kwargs):
        excel_count["open"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "ExcelFile", counting_excel_file)
    app.cached_load_run.clear()
    signature = run_signature(run_dir)

    app.cached_load_run(str(run_dir), signature, app.LOADER_SCHEMA_VERSION)
    app.cached_load_run(str(run_dir), signature, app.LOADER_SCHEMA_VERSION)

    assert excel_count["open"] == 1

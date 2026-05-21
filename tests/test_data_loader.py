from __future__ import annotations

from pathlib import Path

import pandas as pd

from model_dashboard.data_loader import discover_run_folders, load_run
from model_dashboard.labels import IGNORED_RUN_FOLDER_NAMES


def test_missing_files_return_empty_frames(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260101_000000"
    run_dir.mkdir()

    loaded = load_run(run_dir)

    assert loaded.data["summary"].empty
    assert loaded.data["quarterly_predictions"].empty
    assert loaded.data["annual_predictions"].empty
    assert "Summary" in loaded.file_status["Dataset"].tolist()


def test_empty_csv_does_not_crash(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260101_000000"
    run_dir.mkdir()
    (run_dir / "final_summary.csv").write_text("", encoding="utf-8")

    loaded = load_run(run_dir)

    assert loaded.data["summary"].empty


def test_summary_alias_loads_and_normalises_stream(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260101_000000"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "stage": "final",
                "stream": "LIGHT_RUC",
                "variant": "v1",
                "model": "m1",
                "source_family": "family",
                "quarterly_mape": 8.5,
                "annual_mape": 6.0,
            }
        ]
    ).to_csv(run_dir / "all_model_summary.csv", index=False)

    loaded = load_run(run_dir)

    assert len(loaded.data["summary"]) == 1
    assert loaded.data["summary"].iloc[0]["stream_label"] == "Light RUC volume"


def test_quarterly_prediction_alias_loads(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260101_000000"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "stage": "final",
                "stream": "PED",
                "variant": "v1",
                "model": "m1",
                "source_family": "family",
                "forecast_origin": "2023Q4",
                "quarter": "2024Q1",
                "forecast_horizon": 1,
                "target": 100.0,
                "prediction": 104.0,
            }
        ]
    ).to_csv(run_dir / "all_quarterly_predictions.csv", index=False)

    loaded = load_run(run_dir)
    qpred = loaded.data["quarterly_predictions"]

    assert len(qpred) == 1
    assert qpred.iloc[0]["target_period"] == "2024Q1"
    assert qpred.iloc[0]["horizon_bucket"] == "1-4 qtrs"
    assert qpred.iloc[0]["ape"] == 4.0


def test_live_run_folder_is_excluded_from_discovery(tmp_path: Path) -> None:
    live_dir = tmp_path / next(iter(IGNORED_RUN_FOLDER_NAMES))
    live_dir.mkdir()
    pd.DataFrame([{"stage": "final"}]).to_csv(live_dir / "final_summary.csv", index=False)

    discovered = discover_run_folders(tmp_path)

    assert live_dir not in discovered


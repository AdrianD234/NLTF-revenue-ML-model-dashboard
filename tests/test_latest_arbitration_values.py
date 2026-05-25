from __future__ import annotations

from pathlib import Path

import pandas as pd

from model_dashboard.data_loader import load_parquet_dashboard
from tests.fixtures.expected_values import EXPECTED_FIXTURE_FINALISTS


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "mini_parquet"


def test_mini_parquet_finalists_are_selected_from_current_recommended_flags() -> None:
    loaded = load_parquet_dashboard(FIXTURE_ROOT, Path(__file__).resolve().parents[1])
    finalists = loaded.data["recommended"]

    assert len(finalists) == 3
    assert finalists["is_current_recommended"].all()
    for stream, expected in EXPECTED_FIXTURE_FINALISTS.items():
        row = finalists.loc[finalists["stream"] == stream].iloc[0]
        assert float(row["quarterly_mape"]) == expected["quarterly_mape"]
        assert float(row["annual_mape"]) == expected["annual_mape"]


def test_mini_parquet_schiff_rows_are_pure_and_separate_from_finalists() -> None:
    loaded = load_parquet_dashboard(FIXTURE_ROOT, Path(__file__).resolve().parents[1])
    schiff = loaded.data["schiff_df"]

    assert len(schiff) == 3
    assert schiff["is_pure_schiff"].all()
    assert not schiff["is_current_recommended"].any()
    assert not schiff["model"].astype(str).str.contains("resid|blend|solver|ensemble|top|median|mean", case=False, regex=True).any()


def test_mini_parquet_ensemble_weights_come_from_component_json() -> None:
    loaded = load_parquet_dashboard(FIXTURE_ROOT, Path(__file__).resolve().parents[1])
    weights = loaded.data["weights"]

    assert len(weights) == 8
    assert set(weights["source"]) == {"Parquet ensemble_components_json"}
    totals = weights.groupby("stream_label")["weight"].sum().round(6).to_dict()
    assert totals == {
        "Heavy RUC volume": 1.0,
        "Light RUC volume": 1.0,
        "PED VKT per capita": 1.0,
    }


def test_mini_parquet_source_tables_are_generated_from_dashboard_data() -> None:
    loaded = load_parquet_dashboard(FIXTURE_ROOT, Path(__file__).resolve().parents[1])
    source_dir = Path(__file__).resolve().parents[1] / "artifacts" / "chart_sources"
    expected = source_dir / "overview_ensemble_composition.csv"

    assert expected.exists()
    source = pd.read_csv(expected)
    assert len(source) == len(loaded.data["weights"])
    assert set(source["source_column"]) == {"ensemble_components_json.weight"}

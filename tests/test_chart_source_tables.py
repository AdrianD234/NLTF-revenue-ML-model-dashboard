from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.chart_sources import CHART_SOURCE_FILES, CORE_COLUMNS
from model_dashboard.data_loader import DEFAULT_DIAGNOSTIC_AUDIT_ROOT, LoadedRun, load_parquet_dashboard
from model_dashboard.labels import STRESS_BUCKET_ORDER


ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"
EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}


@pytest.fixture(scope="session")
def parquet_dashboard() -> LoadedRun:
    data_root = Path(os.environ.get("MODEL_DIAGNOSTIC_DATA_ROOT", DEFAULT_DIAGNOSTIC_AUDIT_ROOT)).expanduser()
    return load_parquet_dashboard(data_root, ROOT, allow_csv_preview=False)


def chart_source(name: str) -> pd.DataFrame:
    path = CHART_SOURCE_DIR / name
    assert path.exists(), f"Missing chart source table: {path}"
    assert path.stat().st_size > 0, f"Empty chart source table: {path}"
    return pd.read_csv(path)


def test_every_main_chart_exports_a_source_table(parquet_dashboard: LoadedRun) -> None:
    assert CHART_SOURCE_DIR.exists(), "Chart source directory was not written."
    for filename, (page, chart_id) in CHART_SOURCE_FILES.items():
        table = chart_source(filename)
        assert set(CORE_COLUMNS).issubset(table.columns), filename
        assert set(table["page"].dropna()) == {page}, filename
        assert set(table["chart_id"].dropna()) == {chart_id}, filename
        assert table["chart_title"].dropna().astype(str).str.len().gt(0).all(), filename
        assert table["metric_name"].dropna().astype(str).str.len().gt(0).all(), filename
        assert table["calculation_basis"].dropna().astype(str).str.len().gt(0).all(), filename


def test_overview_source_tables_reconcile_to_current_parquet(parquet_dashboard: LoadedRun) -> None:
    accuracy = chart_source("overview_finalist_forecast_accuracy.csv")
    expected_finalists = {
        ("PED VKT per capita", "Quarterly MAPE"): 2.473245,
        ("PED VKT per capita", "Annual MAPE"): 2.385625,
        ("Light RUC volume", "Quarterly MAPE"): 9.147545,
        ("Light RUC volume", "Annual MAPE"): 5.999499,
        ("Heavy RUC volume", "Quarterly MAPE"): 3.484368,
        ("Heavy RUC volume", "Annual MAPE"): 3.019980,
    }
    indexed = accuracy.set_index(["stream_label", "metric_name"])
    for key, expected in expected_finalists.items():
        assert float(indexed.loc[key, "metric_value"]) == pytest.approx(expected, abs=0.0008)

    candidate = chart_source("overview_candidate_search_frontier.csv")
    assert len(candidate) <= 400
    assert {"Selected finalist", "Schiff benchmark"}.issubset(set(candidate["point_type"]))
    assert candidate["calculation_basis"].str.contains("Default curated candidate rows", regex=False).all()


def test_ensemble_chart_source_uses_current_parquet_components(parquet_dashboard: LoadedRun) -> None:
    table = chart_source("overview_ensemble_composition.csv")
    expected = {
        "PED VKT per capita": [100.0],
        "Light RUC volume": [33.3333395, 33.3333312, 33.3333293],
        "Heavy RUC volume": [46.9332, 28.1844, 14.4373, 10.4451],
    }
    for stream, weights in expected.items():
        actual = (
            table[table["stream_label"].eq(stream)]
            .sort_values("component_rank")["weight_pct"]
            .astype(float)
            .to_list()
        )
        assert actual == pytest.approx(weights, abs=0.001)

    stale = {
        "PED VKT per capita": [57.1, 38.7, 4.2],
        "Light RUC volume": [23.2, 21.8, 20.3, 17.2, 11.7, 5.8],
        "Heavy RUC volume": [48.7, 37.7, 13.7],
    }
    for stream, demo_weights in stale.items():
        actual = (
            table[table["stream_label"].eq(stream)]
            .sort_values("component_rank")["weight_pct"]
            .astype(float)
            .round(1)
            .to_list()
        )
        assert actual != demo_weights, f"{stream} still uses stale/demo weights."


def test_stress_chart_source_alias_order_and_missing_gaps(parquet_dashboard: LoadedRun) -> None:
    table = chart_source("overview_stress_horizon_checks.csv")
    for stream in EXPECTED_STREAMS:
        rows = table[table["stream_label"].eq(stream)]
        assert rows["stress_bucket"].tolist() == STRESS_BUCKET_ORDER

    expected_values = {
        ("PED VKT per capita", "1-4 qtrs"): 1.555152,
        ("PED VKT per capita", "5-8 qtrs"): 2.504013,
        ("PED VKT per capita", "9-12 qtrs"): 3.515873,
        ("PED VKT per capita", "2024+"): 0.962366,
        ("PED VKT per capita", "2022-23"): 2.170776,
        ("PED VKT per capita", "Annual"): 2.385625,
        ("Light RUC volume", "1-4 qtrs"): 7.735819,
        ("Light RUC volume", "5-8 qtrs"): 9.486600,
        ("Light RUC volume", "9-12 qtrs"): 10.525990,
        ("Light RUC volume", "2024+"): 6.253350,
        ("Light RUC volume", "2022-23"): 18.785206,
        ("Light RUC volume", "Annual"): 5.999499,
        ("Heavy RUC volume", "1-4 qtrs"): 2.802065,
        ("Heavy RUC volume", "5-8 qtrs"): 3.543246,
        ("Heavy RUC volume", "9-12 qtrs"): 4.268496,
        ("Heavy RUC volume", "Annual"): 3.019980,
    }
    indexed = table.set_index(["stream_label", "stress_bucket"])
    for key, expected in expected_values.items():
        assert float(indexed.loc[key, "metric_value"]) == pytest.approx(expected, abs=0.0008)

    for bucket in ["2024+", "2022-23"]:
        row = indexed.loc[("Heavy RUC volume", bucket)]
        assert pd.isna(pd.to_numeric(row["metric_value"], errors="coerce"))
        assert str(row["value_available"]).lower() == "false"


def test_scenario_and_schiff_source_tables_keep_full_sample_and_paired_separate(
    parquet_dashboard: LoadedRun,
) -> None:
    scenario_gain = chart_source("scenario_improvement_vs_benchmark.csv")
    schiff_gain = chart_source("schiff_paired_or_fullsample_gain.csv")
    assert not scenario_gain["chart_title"].str.contains("Paired Gain vs Schiff", regex=False).any()
    assert scenario_gain["calculation_basis"].str.contains("not paired common-grid gain", regex=False).all()
    assert schiff_gain["chart_title"].str.contains("Full-sample", regex=False).all()
    assert not schiff_gain["chart_title"].str.contains("Paired Gain vs Schiff", regex=False).any()
    assert schiff_gain["calculation_basis"].str.contains("not paired common-grid gain", regex=False).all()

    light = scenario_gain[scenario_gain["stream_label"].eq("Light RUC volume")]
    assert float(light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"].iloc[0]) > 0
    assert float(light["paired_gain_pp"].dropna().iloc[0]) == pytest.approx(-1.159120, abs=0.0008)

    decision = chart_source("scenario_decision_summary.csv")
    assert {
        "Full-sample Qtr Gain",
        "Full-sample Annual Gain",
        "Paired Win Rate",
    }.issubset(set(decision["metric_name"]))
    assert decision["calculation_basis"].str.contains("full-sample MAPE gains", regex=False).all()


def test_horizon_and_diagnostic_source_tables_have_required_semantics(parquet_dashboard: LoadedRun) -> None:
    for filename in ["scenario_horizon_comparison.csv", "schiff_benchmark_horizon_profiles.csv"]:
        table = chart_source(filename)
        assert EXPECTED_STREAMS.issubset(set(table["stream_label"]))
        assert {"Finalist", "Schiff"}.issubset(set(table["scenario"]))

    acf = chart_source("diagnostics_residual_autocorrelation.csv")
    assert EXPECTED_STREAMS.issubset(set(acf["stream_label"]))
    assert acf["notes"].str.contains("All selected quarterly prediction residuals", regex=False).all()

    pass_matrix = chart_source("diagnostics_pass_matrix.csv")
    assert "Calibration R2" in set(pass_matrix["metric_name"])
    assert "Adjusted R2" not in set(pass_matrix["metric_name"])
    assert {"Pass", "Watch", "Fail", "Caution"}.intersection(set(pass_matrix["pass_status"]))

    residual = chart_source("diagnostics_residual_vs_fitted.csv")
    assert residual["calculation_basis"].str.contains("native stream units", regex=False).all()

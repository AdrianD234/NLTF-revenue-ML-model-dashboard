from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.chart_sources import CHART_SOURCE_FILES, CORE_COLUMNS
from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, LoadedRun, load_evidence_pack
from model_dashboard.labels import OVERVIEW_STRESS_BUCKET_ORDER, SCHIFF_SPEC_BENCHMARK_LABEL
from tests.fixtures.expected_values import (
    EXPECTED_ENSEMBLE_WEIGHT_PCT,
    EXPECTED_FINALIST_MAPE,
    EXPECTED_LIGHT_PAIRED_GAIN_PP,
    EXPECTED_STRESS_MAPE,
)


ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"
EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}


@pytest.fixture(scope="session")
def parquet_dashboard() -> LoadedRun:
    data_root = Path(os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT", DEFAULT_EVIDENCE_PACK_ROOT)).expanduser()
    return load_evidence_pack(data_root, ROOT)


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
        assert "score_basis" in table.columns, filename
        assert set(table["score_basis"].dropna().astype(str)) == {"schiff_paper_horizon_mean"}, filename
        assert table["calculation_basis"].dropna().astype(str).str.len().gt(0).all(), filename


def test_overview_source_tables_reconcile_to_current_parquet(parquet_dashboard: LoadedRun) -> None:
    accuracy = chart_source("overview_finalist_forecast_accuracy.csv")
    indexed = accuracy.set_index(["stream_label", "metric_name"])
    for key, expected in EXPECTED_FINALIST_MAPE.items():
        assert float(indexed.loc[key, "metric_value"]) == pytest.approx(expected, abs=0.0008)

    candidate = chart_source("overview_candidate_search_frontier.csv")
    assert len(candidate) <= 400
    assert {"Selected finalist", SCHIFF_SPEC_BENCHMARK_LABEL}.issubset(set(candidate["point_type"]))
    assert candidate["calculation_basis"].str.contains("Default curated candidate rows", regex=False).all()
    row_text = candidate.fillna("").astype(str).agg(lambda row: " ".join(row.to_list()), axis=1)
    assert not row_text.str.contains("20.50|20.499", regex=True).any()


def test_ensemble_chart_source_uses_current_parquet_components(parquet_dashboard: LoadedRun) -> None:
    table = chart_source("overview_ensemble_composition.csv")
    for stream, weights in EXPECTED_ENSEMBLE_WEIGHT_PCT.items():
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
        assert rows["stress_bucket"].tolist() == OVERVIEW_STRESS_BUCKET_ORDER

    indexed = table.set_index(["stream_label", "stress_bucket"])
    for key, expected in EXPECTED_STRESS_MAPE.items():
        if key[1] not in OVERVIEW_STRESS_BUCKET_ORDER:
            continue
        value = pd.to_numeric(indexed.loc[key, "metric_value"], errors="coerce")
        if pd.isna(expected):
            assert pd.isna(value)
        else:
            assert float(value) == pytest.approx(expected, abs=0.0008)

    assert "2024+" not in set(table["stress_bucket"].astype(str))
    assert "2022-23" not in set(table["stress_bucket"].astype(str))


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
    assert float(light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"].iloc[0]) == pytest.approx(3.158190, abs=0.0008)
    assert float(light[light["metric_name"].eq("Full-sample annual gain")]["metric_value"].iloc[0]) == pytest.approx(1.428227, abs=0.0008)
    assert float(light["paired_gain_pp"].dropna().iloc[0]) == pytest.approx(EXPECTED_LIGHT_PAIRED_GAIN_PP, abs=0.0008)

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
    acf_notes = " ".join(acf["notes"].dropna().astype(str))
    assert "All selected quarterly residuals averaged by target period" in acf_notes
    assert not acf.duplicated(["stream_label", "lag"]).any()

    pass_matrix = chart_source("diagnostics_pass_matrix.csv")
    assert "Calibration R2" in set(pass_matrix["metric_name"])
    assert "Adjusted R2" not in set(pass_matrix["metric_name"])
    assert {"Pass", "Watch", "Fail", "Caution"}.intersection(set(pass_matrix["pass_status"]))

    residual = chart_source("diagnostics_residual_vs_fitted.csv")
    assert residual["calculation_basis"].str.contains("native stream units", regex=False).all()

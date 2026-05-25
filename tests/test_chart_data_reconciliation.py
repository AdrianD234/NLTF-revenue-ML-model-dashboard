from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from app import (
    diagnostic_kpi_cards,
    overview_kpi_cards,
    scenario_comparison_frame,
    scenario_horizon_frame,
)
from model_dashboard.data_loader import DEFAULT_DIAGNOSTIC_AUDIT_ROOT, LoadedRun, load_parquet_dashboard
from model_dashboard.metrics import governance_story_summary
from model_dashboard.plots import (
    plot_autocorrelation_diagnostics,
    plot_diagnostic_pass_matrix,
    plot_improvement_vs_benchmark,
    plot_residual_vs_fitted,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}


@pytest.fixture(scope="session")
def parquet_dashboard() -> LoadedRun:
    data_root = Path(os.environ.get("MODEL_DIAGNOSTIC_DATA_ROOT", DEFAULT_DIAGNOSTIC_AUDIT_ROOT)).expanduser()
    return load_parquet_dashboard(data_root, ROOT, allow_csv_preview=False)


def read_source_table(name: str) -> pd.DataFrame:
    path = ARTIFACTS / name
    assert path.exists(), f"Missing source table: {path}"
    assert path.stat().st_size > 0, f"Empty source table: {path}"
    return pd.read_csv(path)


def test_ensemble_composition_uses_parquet_components(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("ensemble_composition_source_table.csv")
    assert set(table["stream_label"]) == EXPECTED_STREAMS
    assert table["source"].astype(str).str.contains("Parquet ensemble_components_json", regex=False).all()

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

    stale_weight_sets = {
        "PED VKT per capita": [57.1, 38.7, 4.2],
        "Light RUC volume": [23.2, 21.8, 20.3, 17.2, 11.7, 5.8],
        "Heavy RUC volume": [48.7, 37.7, 13.7],
    }
    for stream, stale in stale_weight_sets.items():
        rounded = (
            table[table["stream_label"].eq(stream)]
            .sort_values("component_rank")["weight_pct"]
            .astype(float)
            .round(1)
            .to_list()
        )
        assert rounded != stale, f"{stream} still uses stale/demo ensemble weights"

    ped = table[table["stream_label"].eq("PED VKT per capita")].iloc[0]
    assert ped["component_short"] == "hpo::PED | HPO-refine Static solver top-18"


def test_scenario_comparison_source_table_values(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("scenario_comparison_source_table.csv").set_index("stream_label")
    expected = {
        "PED VKT per capita": {
            "scenario_a_quarterly_mape": 2.473245,
            "scenario_b_quarterly_mape": 3.082117,
            "full_sample_qtr_gain_pp": 0.608873,
            "scenario_a_annual_mape": 2.385625,
            "scenario_b_annual_mape": 2.965758,
            "full_sample_annual_gain_pp": 0.580133,
            "paired_win_rate_pct": 63.201320,
        },
        "Light RUC volume": {
            "scenario_a_quarterly_mape": 9.147545,
            "scenario_b_quarterly_mape": 11.546786,
            "full_sample_qtr_gain_pp": 2.399241,
            "scenario_a_annual_mape": 5.999499,
            "scenario_b_annual_mape": 7.843683,
            "full_sample_annual_gain_pp": 1.844184,
            "paired_gain_pp": -1.159120,
            "paired_win_rate_pct": 50.555556,
        },
        "Heavy RUC volume": {
            "scenario_a_quarterly_mape": 3.484368,
            "scenario_b_quarterly_mape": 11.482643,
            "full_sample_qtr_gain_pp": 7.998276,
            "scenario_a_annual_mape": 3.019980,
            "scenario_b_annual_mape": 11.717804,
            "full_sample_annual_gain_pp": 8.697824,
            "paired_win_rate_pct": 64.155251,
        },
    }
    for stream, values in expected.items():
        assert stream in table.index
        for column, value in values.items():
            assert float(table.loc[stream, column]) == pytest.approx(value, abs=0.0008)


def test_scenario_gain_labels_are_full_sample_not_paired(parquet_dashboard: LoadedRun) -> None:
    data = parquet_dashboard.data
    comparison = scenario_comparison_frame(data["recommended"], data["schiff_df"], data["paired_vs_schiff"])
    fig = plot_improvement_vs_benchmark(comparison)

    combined = " ".join(
        [
            str(fig.layout.title.text),
            str(fig.layout.xaxis.title.text),
            " ".join(str(trace.name) for trace in fig.data),
        ]
    )
    assert "Full-sample" in combined
    assert "Paired Gain vs Schiff" not in (ROOT / "app.py").read_text(encoding="utf-8")


def test_light_ruc_paired_gain_is_not_misreported_as_positive(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("scenario_comparison_source_table.csv").set_index("stream_label")
    light = table.loc["Light RUC volume"]
    assert float(light["full_sample_qtr_gain_pp"]) > 0
    assert float(light["paired_gain_pp"]) == pytest.approx(-1.159120, abs=0.0008)
    assert float(light["paired_gain_pp"]) < 0


def test_horizon_source_table_exists(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("horizon_comparison_source_table.csv")
    expected_columns = {"page", "stream_label", "scenario", "horizon", "mape", "source_column", "source"}
    assert expected_columns.issubset(table.columns)


def test_horizon_chart_all_streams_have_source_rows_when_all_streams_selected(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("horizon_comparison_source_table.csv")
    for page in ["Scenario Comparison", "Schiff Benchmark"]:
        page_rows = table[table["page"].eq(page)]
        assert EXPECTED_STREAMS.issubset(set(page_rows["stream_label"]))
        assert set(page_rows["scenario"]).issuperset({"Finalist", "Schiff"})


def test_horizon_chart_does_not_plot_missing_streams_without_source(parquet_dashboard: LoadedRun) -> None:
    plotted = scenario_horizon_frame(parquet_dashboard, parquet_dashboard.data["quarterly_predictions"])
    source = read_source_table("horizon_comparison_source_table.csv")
    source_keys = set(zip(source["stream_label"], source["scenario"], source["horizon"], strict=False))
    plotted_keys = set(zip(plotted["stream_label"], plotted["scenario_role"], plotted["horizon"], strict=False))
    assert plotted_keys.issubset(source_keys)


def test_acf_source_table_exists(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("diagnostic_acf_source_table.csv")
    expected_columns = {"stream_label", "lag", "acf_value", "residual_source", "calculation_method"}
    assert expected_columns.issubset(table.columns)
    assert set(table["stream_label"]) == EXPECTED_STREAMS


def test_acf_chart_uses_documented_residual_source(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("diagnostic_acf_source_table.csv")
    source = set(table["residual_source"].dropna().astype(str))
    assert source == {"All selected quarterly prediction residuals, averaged by target period"}
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "all selected quarterly residuals averaged by target period" in app_text


def test_acf_lag1_matches_source_table(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("diagnostic_acf_source_table.csv")
    lag1 = table[table["lag"].eq(1)].set_index("stream_label")["acf_value"].astype(float)
    fig = plot_autocorrelation_diagnostics(parquet_dashboard.data["quarterly_predictions"])
    for trace in fig.data:
        stream = str(trace.name)
        assert stream in lag1.index
        assert float(trace.y[0]) == pytest.approx(float(lag1.loc[stream]), abs=1e-12)


def test_r2_kpi_label_matches_source_field(parquet_dashboard: LoadedRun) -> None:
    cards = diagnostic_kpi_cards(parquet_dashboard.data["diagnostic_df"])
    titles = [card[0] for card in cards]
    assert "Mean calibration R2" in titles
    assert "Mean Adjusted R2" not in titles


def test_residual_vs_fitted_axis_label_not_misleading(parquet_dashboard: LoadedRun) -> None:
    fig = plot_residual_vs_fitted(parquet_dashboard.data["quarterly_predictions"].head(6_000))
    layout = fig.to_plotly_json()["layout"]
    axis_titles = [
        str(value.get("title", {}).get("text", ""))
        for key, value in layout.items()
        if str(key).startswith("xaxis") and isinstance(value, dict) and value.get("title")
    ]
    assert axis_titles
    assert "Fitted value (m)" not in axis_titles
    assert all(title == "Fitted value, native units" for title in axis_titles if title)


def test_diagnostic_overall_status_does_not_hard_fail_on_normality_only() -> None:
    diagnostics = pd.DataFrame(
        [
            {
                "stream_label": "PED VKT per capita",
                "role": "Our finalist",
                "adj_r2": 0.85,
                "durbin_watson": 2.0,
                "adf_pvalue": 0.01,
                "kpss_pvalue": 0.20,
                "breusch_pagan_pvalue": 0.20,
                "white_pvalue": 0.20,
                "jarque_bera_pvalue": 0.001,
                "cointegration_pvalue": 0.01,
            }
        ]
    )
    fig = plot_diagnostic_pass_matrix(diagnostics)
    headers = list(fig.data[0].header.values)
    overall_idx = headers.index("Overall")
    overall_values = list(fig.data[0].cells.values[overall_idx])
    assert overall_values == ["Watch"]


def test_candidate_count_label_matches_count_source(parquet_dashboard: LoadedRun) -> None:
    data = parquet_dashboard.data
    story = governance_story_summary(data["recommended"], data["paired_vs_schiff"], data["stress"], data["errors"])
    cards = overview_kpi_cards(data["summary"], data["recommended"], story, data["errors"])
    titles = [card[0] for card in cards]
    assert "Plotted candidates" in titles
    assert "Candidate Models" not in titles

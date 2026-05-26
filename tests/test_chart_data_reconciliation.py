from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from app import (
    DEFAULT_ACF_RESIDUAL_SCOPE,
    build_candidate_landscape_frame,
    candidate_frontier_count_context,
    diagnostic_kpi_cards,
    overview_frontier_note,
    overview_kpi_cards,
    scenario_comparison_frame,
    scenario_horizon_frame,
)
from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, LoadedRun, load_evidence_pack
from model_dashboard.metrics import governance_story_summary
from model_dashboard.plots import (
    plot_autocorrelation_diagnostics,
    plot_candidate_landscape,
    plot_diagnostic_pass_matrix,
    plot_improvement_vs_benchmark,
    plot_residual_vs_fitted,
)
from model_dashboard.labels import SCHIFF_SPEC_BENCHMARK_LABEL
from tests.fixtures.expected_values import (
    EXPECTED_ENSEMBLE_WEIGHT_PCT,
    EXPECTED_LIGHT_PAIRED_GAIN_PP,
    EXPECTED_SCENARIO_COMPARISON,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
EXPECTED_STREAMS = {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}


@pytest.fixture(scope="session")
def parquet_dashboard() -> LoadedRun:
    data_root = Path(os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT", DEFAULT_EVIDENCE_PACK_ROOT)).expanduser()
    return load_evidence_pack(data_root, ROOT)


def read_source_table(name: str) -> pd.DataFrame:
    path = ARTIFACTS / name
    assert path.exists(), f"Missing source table: {path}"
    assert path.stat().st_size > 0, f"Empty source table: {path}"
    return pd.read_csv(path)


def test_ensemble_composition_uses_parquet_components(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("ensemble_composition_source_table.csv")
    assert set(table["stream_label"]) == EXPECTED_STREAMS
    assert table["source"].astype(str).str.contains("ensemble_components.parquet", regex=False).all()

    for stream, weights in EXPECTED_ENSEMBLE_WEIGHT_PCT.items():
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
    for stream, values in EXPECTED_SCENARIO_COMPARISON.items():
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
    assert float(light["full_sample_qtr_gain_pp"]) == pytest.approx(3.158190, abs=0.0008)
    assert float(light["full_sample_qtr_gain_pp"]) > 0
    assert float(light["full_sample_annual_gain_pp"]) == pytest.approx(1.428227, abs=0.0008)
    assert float(light["full_sample_annual_gain_pp"]) > 0
    assert float(light["paired_gain_pp"]) == pytest.approx(EXPECTED_LIGHT_PAIRED_GAIN_PP, abs=0.0008)
    assert float(light["paired_gain_pp"]) > 0
    assert light["recommendation"] == "Promote"


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
    assert source == {DEFAULT_ACF_RESIDUAL_SCOPE}
    assert not table.duplicated(["stream_label", "lag"]).any()
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "DEFAULT_ACF_RESIDUAL_SCOPE" in app_text


def test_acf_lag1_matches_source_table(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("diagnostic_acf_source_table.csv")
    fig = plot_autocorrelation_diagnostics(parquet_dashboard.data["quarterly_predictions"], acf_source=table)
    for trace in fig.data:
        stream = str(trace.name)
        source_rows = table[table["stream_label"].eq(stream)].sort_values("lag")
        assert not source_rows.empty
        assert list(trace.x) == source_rows["lag"].tolist()
        assert list(map(float, trace.y)) == pytest.approx(source_rows["acf_value"].astype(float).tolist(), abs=1e-12)


def test_acf_plotted_scope_equals_selected_scope(parquet_dashboard: LoadedRun) -> None:
    table = read_source_table("diagnostic_acf_source_table.csv")
    raw = parquet_dashboard.data["diagnostic_acf"]
    expected = raw[raw["residual_source"].astype(str).eq(DEFAULT_ACF_RESIDUAL_SCOPE)].copy()
    expected["lag"] = pd.to_numeric(expected["lag"], errors="coerce")
    expected["acf_value"] = pd.to_numeric(expected["acf_value"], errors="coerce")
    expected = expected.dropna(subset=["stream_label", "lag", "acf_value"]).sort_values(["stream_label", "lag"])
    actual = table.sort_values(["stream_label", "lag"])
    assert len(actual) == 36
    assert not actual.duplicated(["stream_label", "lag"]).any()
    assert list(actual["stream_label"]) == list(expected["stream_label"])
    assert list(actual["lag"]) == list(expected["lag"])
    assert actual["acf_value"].astype(float).tolist() == pytest.approx(expected["acf_value"].astype(float).tolist(), abs=1e-12)


def test_r2_kpi_label_matches_source_field(parquet_dashboard: LoadedRun) -> None:
    cards = diagnostic_kpi_cards(parquet_dashboard.data["diagnostic_df"])
    titles = [card[0] for card in cards]
    assert "Mean calibration R2" in titles
    assert "Mean Adjusted R2" not in titles


def test_diagnostics_kpi_basis_is_current_finalists_only(parquet_dashboard: LoadedRun) -> None:
    diagnostics = parquet_dashboard.data["diagnostic_df"]
    finalists = diagnostics[diagnostics["role"].astype(str).str.contains("finalist", case=False, na=False)]
    cards = {card[0]: card for card in diagnostic_kpi_cards(diagnostics)}
    expected_dw = pd.to_numeric(finalists["durbin_watson"], errors="coerce").mean()
    expected_r2 = pd.to_numeric(finalists["adj_r2"], errors="coerce").mean()
    assert cards["Mean Durbin-Watson"][1] == f"{expected_dw:.2f}"
    assert cards["Mean calibration R2"][1] == f"{expected_r2:.2f}"
    assert "Current finalists only" in cards["Mean Durbin-Watson"][2]
    assert "Current finalists only" in cards["Mean calibration R2"][2]
    kpi_source = pd.read_csv(ARTIFACTS / "diagnostics_kpi_source_table.csv")
    assert set(kpi_source["basis"]) == {"Current finalist rows only"}


def test_residual_vs_fitted_axis_label_not_misleading(parquet_dashboard: LoadedRun) -> None:
    qpred = parquet_dashboard.data["quarterly_predictions"].head(6_000)
    if qpred.empty:
        status = parquet_dashboard.file_status
        qstatus = status[status["Dataset"].astype(str).eq("Quarterly Predictions Selected")]
        assert not qstatus.empty
        assert qstatus["Found?"].iloc[0] == "No"
        assert "Fitted value (m)" not in (ROOT / "model_dashboard" / "plots.py").read_text(encoding="utf-8")
        return
    fig = plot_residual_vs_fitted(qpred)
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


def test_diagnostic_status_rules_document_core_failure_basis() -> None:
    rules = (ARTIFACTS / "diagnostic_status_rules.md").read_text(encoding="utf-8")
    assert "Overall = Fail when one or more core diagnostics fail" in rules
    assert "Jarque-Bera alone must not force Overall = Fail" in rules


def test_candidate_count_label_matches_count_source(parquet_dashboard: LoadedRun) -> None:
    data = parquet_dashboard.data
    story = governance_story_summary(data["recommended"], data["paired_vs_schiff"], data["stress"], data["errors"])
    context = candidate_frontier_count_context(parquet_dashboard, default_controls(), data["summary"])
    cards = overview_kpi_cards(data["summary"], data["recommended"], story, data["errors"], context)
    titles = [card[0] for card in cards]
    assert "Plotted candidates" in titles
    assert "Candidate Models" not in titles
    assert context["count"] == len(data["summary"]) == 400
    assert context["label"] == "400 plotted candidates from 1,092 curated rows"
    note = overview_frontier_note(data["summary"], context)
    assert note.startswith("Frontier read: All-stream frontier view")
    assert "PED/Heavy use visual frontier samples" in note
    assert "400 plotted candidates from 1,092 curated rows" in note
    assert "Light RUC 196 challenger-search rows" in note
    assert "PED 102 frontier/anchor rows" in note
    assert "Heavy RUC 102 frontier/anchor rows" in note
    assert "3 plotted Schiff specification anchor rows / 3 benchmark streams" in note


def test_candidate_frontier_count_matches_source_table_and_trace_points(parquet_dashboard: LoadedRun) -> None:
    controls = default_controls()
    landscape = build_candidate_landscape_frame(parquet_dashboard, controls, "All-stream frontier view")
    context = candidate_frontier_count_context(parquet_dashboard, controls, landscape)
    source = pd.read_csv(ARTIFACTS / "chart_sources" / "overview_candidate_search_frontier.csv")
    fig = plot_candidate_landscape(landscape)
    rendered_marker_points = sum(len(trace.x) for trace in fig.data if getattr(trace, "mode", "") and "markers" in str(trace.mode))
    assert len(source) == context["count"] == rendered_marker_points == 400
    assert SCHIFF_SPEC_BENCHMARK_LABEL in set(source["point_type"])


def default_controls() -> dict[str, object]:
    return {
        "stage": "all",
        "streams": ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"],
        "source_families": None,
        "variants": None,
        "top_n": 50,
        "show_schiff": True,
        "show_finalists": True,
        "show_screen": True,
        "show_final": True,
        "show_static": True,
        "show_prequential": True,
        "hide_outliers": True,
    }

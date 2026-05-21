from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.benchmark_dashboard import benchmark_backend
from model_dashboard.labels import DEFAULT_INPUT_PARENT, IGNORED_RUN_FOLDER_NAMES
from model_dashboard.labels import _display_model_label_text, _humanize_text, _model_alias_text, display_model_label, humanize_label, model_alias
from model_dashboard.data_loader import curated_manifest_matches, discover_run_folders, load_curated_run, load_run
from model_dashboard.plots import _competitive_landscape_subset, _sample_by_stream, plot_error_distribution


LATEST_ARBITRATION_RUN = Path(
    r"C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339"
)


def test_backend_benchmark_records_core_measurements() -> None:
    assert LATEST_ARBITRATION_RUN.exists(), "Need latest arbitration run folder for performance smoke benchmark."

    result = benchmark_backend(LATEST_ARBITRATION_RUN, repeats=1)
    labels = {item["label"] for item in result["benchmarks"]}

    assert "load_run_uncached" in labels
    assert "summary_generation_prep" in labels
    assert "candidate_landscape_data_prep" in labels
    assert "ensemble_composition_data_prep" in labels
    assert "stress_summary_prep" in labels
    assert "model_inventory_prep" in labels
    assert "run_audit_prep" in labels
    assert "overview_page_render_proxy" in labels
    assert "forecasts_and_errors_render_proxy" in labels
    assert "plot_finalist_accuracy" in labels
    assert "plot_candidate_landscape" in labels
    assert "plot_ensemble_composition" in labels
    assert "plot_stress_checks" in labels
    assert "plot_inventory_family_performance" in labels
    assert "plot_error_distribution_json_bytes" in labels
    assert result["row_counts"]["summary"] > 0
    assert result["row_counts"]["quarterly_predictions"] > 0


def test_backend_core_operations_have_soft_regression_budget() -> None:
    result = benchmark_backend(LATEST_ARBITRATION_RUN, repeats=1)

    by_label = {item["label"]: item for item in result["benchmarks"]}
    assert by_label["load_run_uncached"]["max_sec"] < 30.0
    assert by_label["overview_page_render_proxy"]["max_sec"] < 2.0
    assert by_label["plot_candidate_landscape"]["max_sec"] < 2.0
    assert by_label["plot_ensemble_composition"]["max_sec"] < 2.0
    assert by_label["forecasts_and_errors_render_proxy"]["max_sec"] < 2.0
    assert by_label["plot_stress_checks"]["max_sec"] < 2.0
    assert by_label["plot_inventory_family_performance"]["max_sec"] < 2.0
    assert by_label["run_audit_prep"]["max_sec"] < 2.0
    assert by_label["plot_error_distribution_json_bytes"]["max_sec"] < 5.0
    assert by_label["plot_error_distribution_json_bytes"]["result_value"] < 100_000
    assert by_label["plot_residual_vs_fitted_json_bytes"]["result_value"] < 2_000_000


def test_error_distribution_uses_aggregate_box_statistics() -> None:
    result = benchmark_backend(LATEST_ARBITRATION_RUN, repeats=1)
    curated_dir = Path(__file__).resolve().parents[1] / "artifacts" / "curated_data"
    loaded = (
        load_curated_run(curated_dir, LATEST_ARBITRATION_RUN)
        if curated_manifest_matches(curated_dir, LATEST_ARBITRATION_RUN)
        else load_run(LATEST_ARBITRATION_RUN)
    )

    figure = plot_error_distribution(loaded.data["quarterly_predictions"])

    assert result["row_counts"]["quarterly_predictions"] >= 1_000
    assert result["row_counts"]["quarterly_predictions"] <= 10_000
    assert figure.data
    for trace in figure.data:
        assert getattr(trace, "q1", None) is not None
        assert getattr(trace, "y", None) is None


def test_candidate_landscape_subset_preserves_governance_anchors() -> None:
    rows = []
    for stream in ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]:
        for idx in range(250):
            rows.append(
                {
                    "stream_label": stream,
                    "quarterly_mape": float(idx + 1),
                    "annual_mape": float(250 - idx),
                    "is_finalist": idx == 249,
                    "is_schiff": idx == 248,
                }
            )
    frame = pd.DataFrame(rows)

    subset = _competitive_landscape_subset(frame, max_rows=120)

    assert len(subset) <= 120
    assert int(subset["is_finalist"].sum()) == 3
    assert int(subset["is_schiff"].sum()) == 3


def test_residual_scatter_sampling_is_bounded_and_stream_balanced() -> None:
    frame = pd.DataFrame(
        {
            "stream_label": ["PED VKT per capita"] * 10_000 + ["Light RUC volume"] * 10_000,
            "pred": range(20_000),
            "error_pct": range(20_000),
        }
    )

    sampled = _sample_by_stream(frame, max_rows=1200)

    assert len(sampled) == 1200
    assert sampled["stream_label"].value_counts().to_dict() == {
        "PED VKT per capita": 600,
        "Light RUC volume": 600,
    }


def test_heavy_drilldown_modules_are_lazy_gated() -> None:
    source = Path("app.py").read_text(encoding="utf-8")

    for key in [
        "lazy_diagnostics_inventory",
        "lazy_diagnostics_audit",
        "lazy_scenario_forecast_stress",
        "lazy_schiff_candidate_ensemble",
    ]:
        assert key in source

    assert "Model Inventory is lazy-loaded" in source
    assert "Forecast and stress drilldowns are lazy-loaded" in source


def test_display_table_has_default_row_cap() -> None:
    source = Path("model_dashboard/ui.py").read_text(encoding="utf-8")

    assert "max_rows: int | None = 500" in source
    assert "Showing first" in source


def test_label_formatting_helpers_are_cached() -> None:
    _model_alias_text.cache_clear()
    _humanize_text.cache_clear()
    _display_model_label_text.cache_clear()

    raw = "PED__screen__solver_static_convex_top19"
    for _ in range(5):
        assert model_alias(raw)
        assert humanize_label("quarterly_mape")
        assert display_model_label(raw)

    assert _model_alias_text.cache_info().hits >= 4
    assert _humanize_text.cache_info().hits >= 4
    assert _display_model_label_text.cache_info().hits >= 4

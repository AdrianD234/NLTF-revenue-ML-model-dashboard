from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack
from model_dashboard.r2_metrics import calibration_r2, diagnostics_r2_summary_frame, forecast_r2
from model_dashboard.score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS


ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"


@pytest.fixture(scope="session", autouse=True)
def _write_chart_sources() -> None:
    load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, ROOT)


def test_forecast_r2_uses_sse_over_sst_and_allows_negative_values() -> None:
    assert forecast_r2([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert forecast_r2([1, 2, 3], [3, 2, 1]) == pytest.approx(-3.0)


def test_r2_is_unavailable_when_actual_variance_is_zero() -> None:
    assert pd.isna(forecast_r2([2, 2, 2], [2, 2, 2]))
    assert pd.isna(calibration_r2([2, 2, 2], [1, 2, 3]))


def test_calibration_r2_is_actual_on_forecast_regression() -> None:
    forecasts = [1, 2, 3, 4]
    actuals = [5, 8, 11, 14]
    assert calibration_r2(actuals, forecasts) == pytest.approx(1.0)
    assert forecast_r2(actuals, forecasts) < 0


def test_diagnostics_r2_source_reconciles_to_scorecard_final_predictions() -> None:
    scorecard = pd.read_parquet(ROOT / "data/dashboard_evidence_pack/data/scorecard_predictions.parquet")
    diagnostics = pd.read_parquet(ROOT / "data/dashboard_evidence_pack/data/diagnostic_tests.parquet")
    expected = diagnostics_r2_summary_frame(scorecard, diagnostics).set_index(["stream_label", "score_basis"])
    source = pd.read_csv(CHART_SOURCE_DIR / "diagnostics_r2_summary.csv").set_index(["stream_label", "score_basis"])

    assert {PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS}.issubset(set(source.index.get_level_values("score_basis")))
    for key, row in expected.iterrows():
        assert float(source.loc[key, "forecast_r2"]) == pytest.approx(float(row["forecast_r2"]), abs=1e-12)
        assert float(source.loc[key, "calibration_r2"]) == pytest.approx(float(row["calibration_r2"]), abs=1e-12)
        assert int(source.loc[key, "n_rows"]) == int(row["n_rows"])
        assert source.loc[key, "source_prediction_column"] == row["source_prediction_column"]
        assert source.loc[key, "calibration_r2_source_column"] == row["calibration_r2_source_column"]


def test_heavy_final_r2_uses_weighted_final_predictions_not_component_weights() -> None:
    heavy = pd.read_parquet(ROOT / "data/dashboard_evidence_pack_reproducibility/heavy_ruc/component_predictions.parquet")
    keys = ["score_basis", "eval_grid", "origin", "target_period", "horizon"]
    final_rows = heavy[heavy["score_basis"].eq(OPERATIONAL_SCORE_BASIS)].drop_duplicates(subset=keys, keep="last")
    source = pd.read_csv(CHART_SOURCE_DIR / "reproducibility_component_r2.csv")
    heavy_source = source[
        source["stream_label"].eq("Heavy RUC volume")
        & source["metric_name"].eq("Forecast R2")
        & source["score_basis"].eq(OPERATIONAL_SCORE_BASIS)
    ]

    assert len(heavy_source) == 1
    assert heavy_source["source_prediction_column"].iloc[0] == "final_pred"
    assert float(heavy_source["metric_value"].iloc[0]) == pytest.approx(
        float(forecast_r2(final_rows["actual"], final_rows["final_pred"])),
        abs=1e-12,
    )


def test_light_final_r2_uses_final_predictions_after_log_correction() -> None:
    light = pd.read_parquet(ROOT / "data/dashboard_evidence_pack_reproducibility/light_ruc/component_predictions.parquet")
    keys = ["score_basis", "grid", "origin", "target_period", "horizon"]
    final_rows = light[light["score_basis"].eq(OPERATIONAL_SCORE_BASIS)].drop_duplicates(subset=keys, keep="last")
    source = pd.read_csv(CHART_SOURCE_DIR / "reproducibility_component_r2.csv")
    light_source = source[
        source["stream_label"].eq("Light RUC volume")
        & source["metric_name"].eq("Forecast R2")
        & source["score_basis"].eq(OPERATIONAL_SCORE_BASIS)
    ]

    assert len(light_source) == 1
    assert light_source["source_prediction_column"].iloc[0] == "final_pred"
    assert float(light_source["metric_value"].iloc[0]) == pytest.approx(
        float(forecast_r2(final_rows["actual"], final_rows["final_pred"])),
        abs=1e-12,
    )


def test_r2_source_tables_exist_and_label_metric_types() -> None:
    diagnostics = pd.read_csv(CHART_SOURCE_DIR / "diagnostics_r2_summary.csv")
    reproducibility = pd.read_csv(CHART_SOURCE_DIR / "reproducibility_component_r2.csv")

    assert not diagnostics.empty
    assert not reproducibility.empty
    assert set(diagnostics["metric_name"]) == {"Forecast R2"}
    assert {"Forecast R2", "Component R2"}.issubset(set(reproducibility["metric_name"]))
    assert "calibration_r2_source_column" in diagnostics.columns
    assert diagnostics["calibration_r2_source_column"].dropna().isin({"pred", "calibration_r2", "mz_r2", "adj_r2"}).all()
    assert reproducibility.loc[reproducibility["metric_value"].astype(float).lt(0), "interpretation"].str.contains(
        "Valid but poor fit",
        regex=False,
    ).all()
    assert "in-sample OLS R2" not in (ROOT / "app.py").read_text(encoding="utf-8")

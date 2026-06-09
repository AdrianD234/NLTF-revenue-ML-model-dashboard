from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack
from model_dashboard.score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS


ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"
LIGHT_TRAINING_FIT_DIR = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "light_ruc"


@pytest.fixture(scope="session", autouse=True)
def _write_chart_sources() -> None:
    load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, ROOT)


def read_source(name: str) -> pd.DataFrame:
    path = CHART_SOURCE_DIR / name
    assert path.exists(), f"Missing R2 ladder source: {path}"
    assert path.stat().st_size > 0, f"Empty R2 ladder source: {path}"
    return pd.read_csv(path)


def truthy(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(str).str.casefold().isin({"true", "1", "yes"})


def test_r2_ladder_exports_required_tables_and_labels() -> None:
    for name in [
        "r2_ladder_summary.csv",
        "r2_training_fit_detail.csv",
        "r2_reproducibility_gap_register.csv",
    ]:
        source = read_source(name)
        assert not source.empty
        assert source["r2_type"].dropna().astype(str).str.len().gt(0).all(), name
        assert source["data_scope"].dropna().astype(str).str.len().gt(0).all(), name
        assert {PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS}.issubset(set(source["score_basis"].dropna().astype(str))), name


def test_ladder_summary_keeps_training_calibration_and_forecast_separate() -> None:
    summary = read_source("r2_ladder_summary.csv")
    required = {
        "stream",
        "model",
        "training_fit_r2",
        "calibration_r2",
        "forecast_r2",
        "n_rows",
        "score_basis",
        "availability_status",
        "interpretation",
    }
    assert required.issubset(summary.columns)
    assert set(summary["stream_label"]) == {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}
    light = summary[summary["stream_label"].eq("Light RUC volume")]
    other = summary[~summary["stream_label"].eq("Light RUC volume")]
    assert light["training_fit_r2"].notna().all()
    assert set(light["availability_status"]) == {"available"}
    assert other["training_fit_r2"].isna().all()
    assert other["availability_status"].isin({"partial_missing", "inner_hpo_registry_missing"}).all()
    assert summary["notes"].str.contains("Training-fit R2 is not comparable to forecast R2", regex=False).all()
    assert summary["notes"].str.contains("Training-fit R2 is computed from fitted rows inside the rolling training windows", regex=False).all()


def test_unavailable_training_fit_is_blank_not_zero_and_never_from_validation_rows() -> None:
    detail = read_source("r2_training_fit_detail.csv")
    training = detail[detail["r2_type"].eq("training_fit")]
    assert not training.empty
    unavailable = training[~truthy(training["value_available"])]
    assert not unavailable.empty
    assert unavailable["training_fit_r2"].isna().all()
    assert not unavailable["metric_value"].fillna("").astype(str).isin({"0", "0.0", "0.000"}).any()
    validation_tokens = "component_predictions|scorecard_predictions|rebuilt_predictions|evidence_prediction_comparison"
    available_training = training[truthy(training["value_available"])]
    assert not available_training["source_file"].fillna("").astype(str).str.contains(validation_tokens, regex=True).any()
    assert available_training["source_column"].eq("actual;training_fit_pred").all()
    assert training["data_scope"].isin({"training_window_fitted_rows", "training_window_fitted_rows_missing"}).all()


def test_heavy_light_and_ped_specific_r2_ladder_rules() -> None:
    summary = read_source("r2_ladder_summary.csv")
    detail = read_source("r2_training_fit_detail.csv")
    gaps = read_source("r2_reproducibility_gap_register.csv")

    heavy = summary[summary["stream_label"].eq("Heavy RUC volume")]
    assert set(heavy["training_fit_r2_status"]) == {"partial_missing"}

    ped = summary[summary["stream_label"].eq("PED VKT per capita")]
    assert set(ped["training_fit_r2_status"]) == {"inner_hpo_registry_missing"}
    assert ped["inner_hpo_weights_status"].dropna().str.startswith("available_").all()
    assert ped["nested_replay_status"].dropna().str.startswith("available_").all()

    light = summary[summary["stream_label"].eq("Light RUC volume")]
    assert set(light["training_fit_r2_status"]) == {"available"}

    component_validation = detail[detail["r2_type"].eq("component_validation")]
    assert {"Heavy RUC volume", "Light RUC volume", "PED VKT per capita"}.issubset(set(component_validation["stream_label"]))
    assert component_validation["data_scope"].eq("out_of_sample_component_prediction_rows").all()
    assert component_validation["source_prediction_column"].eq("component_pred").all()

    assert gaps["gap_id"].str.contains("heavy_ruc_c1_c4_training_fit_rows_missing", regex=False).any()
    assert gaps["gap_id"].str.contains("ped_inner_hpo_training_fit_registry_missing", regex=False).any()
    assert not gaps["stream_label"].eq("Light RUC volume").any()


def test_light_training_fit_r2_uses_stage_specific_fitted_rows() -> None:
    summary = read_source("r2_ladder_summary.csv")
    detail = read_source("r2_training_fit_detail.csv")
    light_summary = summary[summary["stream_label"].eq("Light RUC volume")].set_index("score_basis")
    light_detail = detail[
        detail["stream_label"].eq("Light RUC volume")
        & detail["r2_type"].eq("training_fit")
        & truthy(detail["value_available"])
    ].set_index(["score_basis", "training_fit_stage"])

    expected = {
        (OPERATIONAL_SCORE_BASIS, "base_ols"): 0.939752,
        (OPERATIONAL_SCORE_BASIS, "post_gbm_final"): 0.988606,
        (PAPER_SCORE_BASIS, "base_ols"): 0.972393,
        (PAPER_SCORE_BASIS, "post_gbm_final"): 0.994984,
    }
    assert set(light_detail.index) == set(expected)
    for key, value in expected.items():
        assert float(light_detail.loc[key, "training_fit_r2"]) == pytest.approx(value, abs=0.000001)
        assert int(light_detail.loc[key, "n_rows"]) > 0
        assert light_detail.loc[key, "data_scope"] == "training_window_fitted_rows"

    assert float(light_summary.loc[OPERATIONAL_SCORE_BASIS, "training_fit_r2"]) == pytest.approx(0.988606, abs=0.000001)
    assert float(light_summary.loc[PAPER_SCORE_BASIS, "training_fit_r2"]) == pytest.approx(0.994984, abs=0.000001)
    assert set(light_summary["training_fit_stage"]) == {"post_gbm_final"}
    assert light_summary["training_fit_r2"].astype(float).gt(0).all()


def test_light_training_fit_stage_is_not_ignored_or_mixed() -> None:
    detail = read_source("r2_training_fit_detail.csv")
    light = detail[
        detail["stream_label"].eq("Light RUC volume")
        & detail["r2_type"].eq("training_fit")
        & truthy(detail["value_available"])
    ]
    assert set(light["training_fit_stage"]) == {"base_ols", "post_gbm_final"}
    assert not light.duplicated(["score_basis", "training_fit_stage"]).any()
    stage_values = light.pivot(index="score_basis", columns="training_fit_stage", values="training_fit_r2")
    assert (stage_values["post_gbm_final"].astype(float) > stage_values["base_ols"].astype(float)).all()


def test_training_fit_rows_do_not_feed_main_kpi_scenario_or_stress_sources() -> None:
    forbidden_source = "training_fit_predictions"
    protected_sources = [
        "overview_kpi_cards.csv",
        "overview_finalist_forecast_accuracy.csv",
        "overview_stress_horizon_checks.csv",
        "scenario_stream_comparison.csv",
        "scenario_improvement_vs_benchmark.csv",
        "scenario_horizon_comparison.csv",
        "scenario_decision_summary.csv",
        "schiff_vs_finalist_mape.csv",
        "schiff_benchmark_summary.csv",
    ]
    for name in protected_sources:
        source = read_source(name)
        text = source.fillna("").astype(str).agg(" ".join, axis=1).str.cat(sep=" ")
        assert forbidden_source not in text, name


def test_light_training_fit_csv_mirrors_are_not_allowed() -> None:
    forbidden = [
        LIGHT_TRAINING_FIT_DIR / "training_fit_predictions.csv",
        LIGHT_TRAINING_FIT_DIR / "training_fit_r2_summary.csv",
    ]
    assert not any(path.exists() for path in forbidden), [str(path) for path in forbidden if path.exists()]

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack
from model_dashboard.score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS


ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"


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
    assert summary["training_fit_r2"].isna().all()
    assert summary["availability_status"].isin(
        {"fitted_training_rows_missing", "partial_missing", "inner_hpo_registry_missing"}
    ).all()
    assert summary["notes"].str.contains("Training-fit R2 is not comparable to forecast R2", regex=False).all()


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
    assert set(light["training_fit_r2_status"]) == {"fitted_training_rows_missing"}

    component_validation = detail[detail["r2_type"].eq("component_validation")]
    assert {"Heavy RUC volume", "Light RUC volume", "PED VKT per capita"}.issubset(set(component_validation["stream_label"]))
    assert component_validation["data_scope"].eq("out_of_sample_component_prediction_rows").all()
    assert component_validation["source_prediction_column"].eq("component_pred").all()

    assert gaps["gap_id"].str.contains("heavy_ruc_c1_c4_training_fit_rows_missing", regex=False).any()
    assert gaps["gap_id"].str.contains("ped_inner_hpo_training_fit_registry_missing", regex=False).any()

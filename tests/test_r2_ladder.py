from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app import R2_LADDER_HEADER_TOOLTIPS, _r2_ladder_header_html, format_r2_for_ladder_display, r2_ladder_display_table
from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack
from model_dashboard.score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS


ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE_DIR = ROOT / "artifacts" / "chart_sources"
LIGHT_TRAINING_FIT_DIR = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "light_ruc"
HEAVY_TRAINING_FIT_DIR = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc"
PED_TRAINING_FIT_DIR = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "ped"


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
    assert summary["training_fit_r2"].notna().all()
    assert set(summary["availability_status"]) == {"available"}
    assert summary["notes"].str.contains("Training-fit R2 is not comparable to forecast R2", regex=False).all()
    assert summary["notes"].str.contains("Training-fit R2 is computed from fitted rows inside the rolling training windows", regex=False).all()


def test_r2_ladder_display_headers_have_tooltips_and_clean_labels() -> None:
    required_tooltips = {
        "Training-fit R2",
        "Calibration R2",
        "Forecast R2",
        "Score basis",
        "Availability",
    }
    assert required_tooltips.issubset(R2_LADDER_HEADER_TOOLTIPS)
    for label in required_tooltips:
        tooltip = R2_LADDER_HEADER_TOOLTIPS[label]
        assert "_" not in label
        assert "_" not in tooltip
        header = _r2_ladder_header_html(label)
        assert "summary-tooltip-trigger" in header
        assert "role='tooltip'" in header
        assert "?" in header
    assert "in-sample R2" not in R2_LADDER_HEADER_TOOLTIPS["Forecast R2"]
    assert "Operational pooled MAPE" in R2_LADDER_HEADER_TOOLTIPS["Score basis"]
    assert "Schiff paper horizon mean" in R2_LADDER_HEADER_TOOLTIPS["Score basis"]


def test_r2_ladder_display_uses_four_decimals_and_no_false_perfect_ped() -> None:
    loaded = load_evidence_pack(DEFAULT_EVIDENCE_PACK_ROOT, ROOT)
    display = r2_ladder_display_table(loaded)
    assert {
        "Training-fit R2",
        "Calibration R2",
        "Forecast R2",
        "Score basis",
        "Availability",
    }.issubset(display.columns)
    assert not {"training_fit_r2", "calibration_r2", "forecast_r2", "score_basis", "availability_status"} & set(display.columns)
    ped = display[display["Stream"].eq("PED VKT per capita")]
    assert not ped.empty
    assert set(ped["Training-fit R2"]) == {"0.9999", "0.9996"}
    assert not ped["Training-fit R2"].astype(str).str.fullmatch(r"1\.0000?|1\.000").any()
    for column in ["Training-fit R2", "Calibration R2", "Forecast R2"]:
        values = display[column].astype(str)
        numeric_values = values[values.ne("-")]
        assert numeric_values.str.fullmatch(r"-?\d+\.\d{4}").all(), column
    assert set(display["Score basis"]) == {"Paper-style horizon MAPE", "Operational pooled MAPE"}


def test_r2_ladder_display_formatter_never_rounds_sub_one_to_one() -> None:
    assert format_r2_for_ladder_display(0.99999) == "0.9999"
    assert format_r2_for_ladder_display(1.0) == "1.0000"


def test_unavailable_training_fit_is_blank_not_zero_and_never_from_validation_rows() -> None:
    detail = read_source("r2_training_fit_detail.csv")
    training = detail[detail["r2_type"].eq("training_fit")]
    assert not training.empty
    unavailable = training[~truthy(training["value_available"])]
    if not unavailable.empty:
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
    assert set(heavy["training_fit_r2_status"]) == {"available"}
    assert set(heavy["availability_status"]) == {"available"}
    assert set(heavy["training_fit_stage"]) == {"weighted_ensemble_final"}
    assert heavy["training_fit_r2"].astype(float).gt(0.99).all()

    ped = summary[summary["stream_label"].eq("PED VKT per capita")]
    assert set(ped["training_fit_r2_status"]) == {"available"}
    assert set(ped["availability_status"]) == {"available"}
    assert set(ped["training_fit_stage"]) == {"hpo_refine_final_fitted"}
    assert ped["training_fit_r2"].astype(float).gt(0.999).all()
    ped_by_basis = ped.set_index("score_basis")
    assert float(ped_by_basis.loc[OPERATIONAL_SCORE_BASIS, "training_fit_r2"]) == pytest.approx(0.999862, abs=0.000001)
    assert float(ped_by_basis.loc[PAPER_SCORE_BASIS, "training_fit_r2"]) == pytest.approx(0.999563, abs=0.000001)
    assert ped["inner_hpo_weights_status"].dropna().str.startswith("available_").all()
    assert ped["nested_replay_status"].dropna().str.startswith("available_").all()

    light = summary[summary["stream_label"].eq("Light RUC volume")]
    assert set(light["training_fit_r2_status"]) == {"available"}

    component_validation = detail[detail["r2_type"].eq("component_validation")]
    assert {"Heavy RUC volume", "Light RUC volume", "PED VKT per capita"}.issubset(set(component_validation["stream_label"]))
    assert component_validation["data_scope"].eq("out_of_sample_component_prediction_rows").all()
    assert component_validation["source_prediction_column"].eq("component_pred").all()

    assert not gaps["stream_label"].eq("Heavy RUC volume").any()
    ped_gaps = gaps[gaps["stream_label"].eq("PED VKT per capita")]
    assert set(ped_gaps["gap_status"]) == {"closed_by_ped_training_fit_export"}
    assert set(ped_gaps["training_fit_r2_status"]) == {"available"}
    assert not gaps["gap_id"].str.contains("ped_inner_hpo_training_fit_registry_missing", regex=False).any()
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


def test_heavy_training_fit_r2_uses_weighted_fitted_predictions() -> None:
    parquet_path = HEAVY_TRAINING_FIT_DIR / "training_fit_predictions.parquet"
    assert parquet_path.exists()
    rows = pd.read_parquet(parquet_path)
    assert not rows.empty
    assert rows["data_scope"].eq("training_window_fitted_rows").all()
    assert set(rows["sample_role"]) == {"training"}
    assert not rows["source_file"].fillna("").astype(str).str.contains(
        "component_predictions|scorecard_predictions|rebuilt_predictions|evidence_prediction_comparison",
        regex=True,
    ).any()

    weighted = rows[rows["training_fit_stage"].eq("weighted_ensemble_final")]
    components = rows[rows["component_label"].isin({"C1", "C2", "C3", "C4"})]
    assert not weighted.empty
    assert set(components["component_label"]) == {"C1", "C2", "C3", "C4"}

    key = ["score_basis", "origin", "training_period"]
    pred_matrix = components.pivot_table(index=key, columns="component_label", values="training_fit_pred", aggfunc="first")
    weight_map = components.groupby("component_label")["component_weight"].first()
    expected = pred_matrix[["C1", "C2", "C3", "C4"]].mul(weight_map[["C1", "C2", "C3", "C4"]], axis=1).sum(axis=1)
    observed = weighted.set_index(key)["training_fit_pred"].sort_index()
    expected = expected.reindex(observed.index)
    assert expected.notna().all()
    assert (observed - expected).abs().max() == pytest.approx(0.0, abs=0.000001)


def test_heavy_summary_matches_weighted_training_fit_parquet() -> None:
    summary = read_source("r2_ladder_summary.csv")
    heavy_summary = summary[summary["stream_label"].eq("Heavy RUC volume")].set_index("score_basis")
    rows = pd.read_parquet(HEAVY_TRAINING_FIT_DIR / "training_fit_predictions.parquet")
    weighted = rows[rows["training_fit_stage"].eq("weighted_ensemble_final")]
    expected = {}
    for basis, group in weighted.groupby("score_basis"):
        actual = group["actual"].astype(float)
        pred = group["training_fit_pred"].astype(float)
        expected[basis] = 1.0 - float(((actual - pred) ** 2).sum() / ((actual - actual.mean()) ** 2).sum())

    assert set(heavy_summary.index) == set(expected)
    for basis, value in expected.items():
        assert float(heavy_summary.loc[basis, "training_fit_r2"]) == pytest.approx(value, abs=0.000001)
        assert heavy_summary.loc[basis, "training_fit_stage"] == "weighted_ensemble_final"
        assert heavy_summary.loc[basis, "availability_status"] == "available"


def test_ped_training_fit_r2_uses_verified_final_hpo_fitted_rows() -> None:
    parquet_path = PED_TRAINING_FIT_DIR / "training_fit_predictions.parquet"
    assert parquet_path.exists()
    rows = pd.read_parquet(parquet_path)
    assert not rows.empty
    required = {
        "stream",
        "model",
        "component_model",
        "training_fit_stage",
        "score_basis",
        "origin",
        "training_period",
        "window_start",
        "window_end",
        "actual",
        "training_fit_pred",
        "data_scope",
    }
    assert required.issubset(rows.columns)
    assert rows["data_scope"].eq("training_window_fitted_rows").all()
    assert set(rows["sample_role"]) == {"training"}
    assert not rows["source_file"].fillna("").astype(str).str.contains(
        "component_predictions|scorecard_predictions|rebuilt_predictions|evidence_prediction_comparison|quarterly_predictions|annual_predictions",
        regex=True,
    ).any()
    assert not (PED_TRAINING_FIT_DIR / "training_fit_predictions.csv").exists()

    stages = set(rows["training_fit_stage"].astype(str))
    assert {"hpo_refine_final_fitted", "outer_component_fitted", "static_convex_top18_fitted", "preq_convex_top18_fitted"}.issubset(stages)
    assert "PED__diff__GBR_learning_rate0_05_max_depth1_n_estimators650__ylag__w40" in stages

    final = rows[rows["training_fit_stage"].eq("hpo_refine_final_fitted")]
    outer = rows[rows["training_fit_stage"].eq("outer_component_fitted")]
    assert not final.empty
    key = ["score_basis", "origin", "training_period"]
    observed = final.set_index(key)["training_fit_pred"].sort_index()
    expected = outer.set_index(key)["training_fit_pred"].sort_index().reindex(observed.index)
    assert expected.notna().all()
    assert (observed - expected).abs().max() == pytest.approx(0.0, abs=0.000001)

    assert (
        pd.PeriodIndex(final["training_period"], freq="Q").asi8
        <= pd.PeriodIndex(final["origin"], freq="Q").asi8
    ).all()

    summary = read_source("r2_ladder_summary.csv")
    ped_summary = summary[summary["stream_label"].eq("PED VKT per capita")].set_index("score_basis")
    expected_r2 = {}
    for basis, group in final.groupby("score_basis"):
        actual = group["actual"].astype(float)
        pred = group["training_fit_pred"].astype(float)
        expected_r2[basis] = 1.0 - float(((actual - pred) ** 2).sum() / ((actual - actual.mean()) ** 2).sum())
    assert set(ped_summary.index) == set(expected_r2)
    for basis, value in expected_r2.items():
        assert float(ped_summary.loc[basis, "training_fit_r2"]) == pytest.approx(value, abs=0.000001)
        assert ped_summary.loc[basis, "training_fit_stage"] == "hpo_refine_final_fitted"
        assert ped_summary.loc[basis, "availability_status"] == "available"


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


def test_training_fit_csv_mirrors_are_not_allowed() -> None:
    forbidden = [
        LIGHT_TRAINING_FIT_DIR / "training_fit_predictions.csv",
        LIGHT_TRAINING_FIT_DIR / "training_fit_r2_summary.csv",
        HEAVY_TRAINING_FIT_DIR / "training_fit_predictions.csv",
        HEAVY_TRAINING_FIT_DIR / "training_fit_r2_summary.csv",
        PED_TRAINING_FIT_DIR / "training_fit_predictions.csv",
        PED_TRAINING_FIT_DIR / "training_fit_r2_summary.csv",
    ]
    assert not any(path.exists() for path in forbidden), [str(path) for path in forbidden if path.exists()]

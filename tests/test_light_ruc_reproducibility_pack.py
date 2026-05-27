from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.evidence_pack import load_evidence_pack
from model_dashboard.light_ruc_reproducibility import (
    LIGHT_RUC_REPRO_DESCRIPTION,
    LIGHT_RUC_REPRO_MODEL,
    LIGHT_RUC_REPRO_ROOT,
    REQUIRED_LIGHT_RUC_REPRO_FILES,
    light_ruc_component_trace_view,
    light_ruc_feature_importance_view,
    light_ruc_registry_view,
    light_ruc_replay_summary,
    light_ruc_sensitivity_view,
    load_light_ruc_reproducibility_pack,
)
from scripts.validate_light_ruc_reproducibility import validate
from tests.fixtures.expected_values import EXPECTED_FINALIST_MAPE


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "dashboard_evidence_pack"


def test_light_ruc_reproducibility_validator_passes() -> None:
    findings = validate(DATA_ROOT, LIGHT_RUC_REPRO_ROOT)
    assert all(row["status"] == "PASS" for row in findings), findings


def test_light_ruc_reproducibility_copy_contains_only_allowed_files() -> None:
    names = {path.name for path in LIGHT_RUC_REPRO_ROOT.iterdir() if path.is_file()}
    assert set(REQUIRED_LIGHT_RUC_REPRO_FILES).issubset(names)
    assert not {path.name for path in LIGHT_RUC_REPRO_ROOT.glob("*.csv")}
    assert not {path.name for path in LIGHT_RUC_REPRO_ROOT.glob("*.xlsx")}


def test_light_ruc_replay_delta_and_recipe_are_exact() -> None:
    pack = load_light_ruc_reproducibility_pack()
    summary = light_ruc_replay_summary(pack)
    registry = pack.table("model_registry").fillna("").astype(str)
    registry_text = registry.agg(" ".join, axis=1).str.cat(sep=" ")
    evidence = pack.table("evidence_prediction_comparison")
    metric = pack.table("evidence_metric_comparison")

    assert summary["status"] == "Exact prediction replay"
    assert summary["model"] == LIGHT_RUC_REPRO_MODEL
    assert summary["description"] == LIGHT_RUC_REPRO_DESCRIPTION
    assert float(pd.to_numeric(evidence["abs_pred_delta"], errors="coerce").max()) <= 1e-5
    assert float(pd.to_numeric(metric["max_abs_pred_delta"], errors="coerce").max()) == pytest.approx(4.76837158203125e-07)
    assert "OLS base plus GradientBoostingRegressor residual correction" in registry_text
    assert "n_estimators" in registry_text and "150" in registry_text
    assert "max_depth" in registry_text and "1" in registry_text
    assert "learning_rate" in registry_text and "0.05" in registry_text
    assert "subsample" in registry_text and "0.85" in registry_text
    assert "random_state" in registry_text and "42" in registry_text
    assert "final_pred = exp(final_log_pred)" in registry_text


def test_light_ruc_auxiliary_views_have_governance_content() -> None:
    pack = load_light_ruc_reproducibility_pack()
    registry = light_ruc_registry_view(pack)
    component_trace = light_ruc_component_trace_view(pack)
    feature_importance = light_ruc_feature_importance_view(pack)
    sensitivities = light_ruc_sensitivity_view(pack)

    assert not registry.empty
    assert "base_schiff_ols" in set(registry["Base model"])
    assert "residual_gbr" in set(registry["Residual model"])
    assert "n_estimators=150" in registry["Hyperparameters"].iloc[0]
    assert not component_trace.empty
    assert {"Base log prediction", "Residual log prediction", "Final prediction", "Actual"}.issubset(component_trace.columns)
    assert not feature_importance.empty
    assert not sensitivities.empty
    sensitivity_text = sensitivities["scenario_variable"].astype(str).str.cat(sep=" | ")
    assert "GDP" in sensitivity_text
    assert "diesel" in sensitivity_text.lower()
    assert "ruc price" in sensitivity_text.lower()


def test_light_ruc_replay_scorecard_metrics_match_audit_facts() -> None:
    pack = load_light_ruc_reproducibility_pack()
    scorecard = pack.table("scorecard_summary").set_index("score_basis")

    assert float(scorecard.loc["current_grid_operational_pooled", "quarterly_mape"]) == pytest.approx(8.272972, abs=0.000001)
    assert float(scorecard.loc["current_grid_operational_pooled", "annual_mape"]) == pytest.approx(6.774906, abs=0.000001)
    assert float(scorecard.loc["schiff_paper_horizon_mean", "horizon_mean_mape"]) == pytest.approx(5.363207, abs=0.000001)
    assert float(scorecard.loc["schiff_paper_horizon_mean", "quarterly_mape"]) == pytest.approx(4.794903, abs=0.000001)
    assert float(scorecard.loc["schiff_paper_horizon_mean", "annual_mape"]) == pytest.approx(1.273774, abs=0.000001)


def test_main_dashboard_finalist_kpis_unchanged_by_auxiliary_pack() -> None:
    dashboard = load_evidence_pack(DATA_ROOT, ROOT)
    recommended = dashboard.data["recommended"].set_index("stream_label")

    for (stream, metric_name), expected in EXPECTED_FINALIST_MAPE.items():
        column = "quarterly_mape" if metric_name == "Quarterly MAPE" else "annual_mape"
        assert float(recommended.loc[stream, column]) == pytest.approx(expected, abs=0.000001)

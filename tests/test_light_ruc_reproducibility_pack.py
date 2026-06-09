from __future__ import annotations

from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from model_dashboard.evidence_pack import load_evidence_pack
from model_dashboard.light_ruc_reproducibility import (
    PED_INNER_HPO_AUDIT_STATUS,
    PED_INNER_HPO_REPRO_ROOT,
    LIGHT_RUC_REPRO_DESCRIPTION,
    HEAVY_RUC_REPRO_MODEL,
    HEAVY_RUC_REPRO_ROOT,
    LIGHT_RUC_REPRO_MODEL,
    LIGHT_RUC_REPRO_ROOT,
    PED_REPRO_DESCRIPTION,
    PED_REPRO_MODEL,
    PED_REPRO_ROOT,
    REQUIRED_PED_INNER_HPO_AUDIT_FILES,
    REQUIRED_HEAVY_RUC_REPRO_FILES,
    REQUIRED_LIGHT_RUC_REPRO_FILES,
    REQUIRED_PED_REPRO_FILES,
    REPRODUCIBILITY_STREAM_CONFIGS,
    light_ruc_component_trace_view,
    light_ruc_feature_importance_view,
    light_ruc_registry_view,
    light_ruc_replay_summary,
    light_ruc_sensitivity_view,
    load_ped_inner_hpo_audit_pack,
    ped_inner_hpo_audit_summary,
    ped_inner_hpo_gap_register_view,
    ped_inner_hpo_nested_trace_view,
    ped_inner_hpo_public_source_reference,
    ped_inner_hpo_source_artifacts_view,
    ped_inner_hpo_weight_detail_view,
    ped_inner_hpo_weight_source_view,
    reproducibility_component_trace_view,
    reproducibility_ensemble_equation,
    reproducibility_ensemble_weight_view,
    reproducibility_feature_importance_view,
    reproducibility_registry_view,
    reproducibility_replay_summary,
    reproducibility_scorecard_view,
    reproducibility_sensitivity_view,
    load_reproducibility_pack,
    load_light_ruc_reproducibility_pack,
)
from scripts.validate_light_ruc_reproducibility import validate
from tests.fixtures.expected_values import EXPECTED_FINALIST_MAPE


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "dashboard_evidence_pack"


def contains_local_path_token(text: str) -> bool:
    lowered = str(text).casefold()
    return any(token in lowered for token in ["c:\\users", "c:/users", "downloads", "onedrive", "appdata", "adrian~1"])


def test_light_ruc_reproducibility_validator_passes() -> None:
    findings = validate(DATA_ROOT, LIGHT_RUC_REPRO_ROOT)
    assert all(row["status"] == "PASS" for row in findings), findings


def test_light_ruc_reproducibility_copy_contains_only_allowed_files() -> None:
    names = {path.name for path in LIGHT_RUC_REPRO_ROOT.iterdir() if path.is_file()}
    assert set(REQUIRED_LIGHT_RUC_REPRO_FILES).issubset(names)
    assert not {path.name for path in LIGHT_RUC_REPRO_ROOT.glob("*.csv")}
    assert not {path.name for path in LIGHT_RUC_REPRO_ROOT.glob("*.xlsx")}


def test_reproducibility_stream_configs_are_generic() -> None:
    assert {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}.issubset(REPRODUCIBILITY_STREAM_CONFIGS)
    ped = load_reproducibility_pack("PED VKT per capita")
    heavy = load_reproducibility_pack("Heavy RUC volume")
    assert ped.root.name == "ped"
    assert ped.available
    assert not ped.missing_files
    assert heavy.root.name == "heavy_ruc"
    assert heavy.available
    assert not heavy.missing_files


def test_heavy_ruc_reproducibility_copy_contains_only_allowed_files() -> None:
    names = {path.name for path in HEAVY_RUC_REPRO_ROOT.iterdir() if path.is_file()}
    assert set(REQUIRED_HEAVY_RUC_REPRO_FILES).issubset(names)
    assert not {path.name for path in HEAVY_RUC_REPRO_ROOT.glob("*.csv")}
    assert not {path.name for path in HEAVY_RUC_REPRO_ROOT.glob("*.xlsx")}


def test_ped_reproducibility_copy_contains_only_allowed_files() -> None:
    names = {path.name for path in PED_REPRO_ROOT.iterdir() if path.is_file()}
    assert set(REQUIRED_PED_REPRO_FILES).issubset(names)
    assert not {path.name for path in PED_REPRO_ROOT.glob("*.csv")}
    assert not {path.name for path in PED_REPRO_ROOT.glob("*.xlsx")}


def test_ped_inner_hpo_copy_contains_only_allowed_files() -> None:
    names = {path.name for path in PED_INNER_HPO_REPRO_ROOT.iterdir() if path.is_file()}
    assert set(REQUIRED_PED_INNER_HPO_AUDIT_FILES).issubset(names)
    assert not {path.name for path in PED_INNER_HPO_REPRO_ROOT.glob("*.csv")}
    assert not {path.name for path in PED_INNER_HPO_REPRO_ROOT.glob("*.xlsx")}


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


def test_light_ruc_log_components_rebuild_final_prediction() -> None:
    pack = load_light_ruc_reproducibility_pack()
    rebuilt = pack.table("rebuilt_predictions")

    rebuilt_delta = (
        np.exp(pd.to_numeric(rebuilt["base_log_pred"], errors="coerce") + pd.to_numeric(rebuilt["residual_log_pred"], errors="coerce"))
        - pd.to_numeric(rebuilt["pred"], errors="coerce")
    ).abs()
    assert float(rebuilt_delta.max()) <= 1e-5

    components = pack.table("component_predictions")
    keys = ["score_basis", "grid", "origin", "target_period", "horizon"]
    pivot = components.pivot_table(index=keys, columns="component_model", values="component_log_value", aggfunc="first")
    final = components.groupby(keys, dropna=False)["final_pred"].first()
    component_delta = (
        np.exp(pd.to_numeric(pivot["base_schiff_ols"], errors="coerce") + pd.to_numeric(pivot["residual_gbr"], errors="coerce"))
        - pd.to_numeric(final, errors="coerce")
    ).abs()
    assert float(component_delta.max()) <= 1e-5


def test_heavy_ruc_weighted_ensemble_rebuilds_final_prediction() -> None:
    pack = load_reproducibility_pack("Heavy RUC volume")
    summary = reproducibility_replay_summary(pack)
    weights = reproducibility_ensemble_weight_view(pack)
    components = pack.table("component_predictions")
    prediction_comparison = pack.table("evidence_prediction_comparison")

    assert summary["status"] == "Exact weighted-ensemble replay"
    assert summary["model"] == HEAVY_RUC_REPRO_MODEL
    assert summary["source_sheet"] == "Heavy RUC Inputs"
    assert float(pd.to_numeric(prediction_comparison["max_abs_pred_delta"], errors="coerce").max()) <= 1e-5
    assert float(weights["Weight"].sum()) == pytest.approx(1.0, abs=1e-6)
    assert reproducibility_ensemble_equation(pack) == (
        "Prediction = 0.469332*C1 + 0.281844*C2 + 0.144373*C3 + 0.104451*C4"
    )

    keys = ["score_basis", "eval_grid", "origin", "target_period", "horizon"]
    grouped = components.groupby(keys, dropna=False).agg(
        rebuilt=("weighted_component_pred", "sum"),
        final_pred=("final_pred", "first"),
    )
    delta = (pd.to_numeric(grouped["rebuilt"], errors="coerce") - pd.to_numeric(grouped["final_pred"], errors="coerce")).abs()
    assert float(delta.max()) <= 1e-5


def test_ped_component_replay_rebuilds_final_prediction() -> None:
    pack = load_reproducibility_pack("PED VKT per capita")
    summary = reproducibility_replay_summary(pack)
    weights = reproducibility_ensemble_weight_view(pack)
    components = pack.table("component_predictions")
    prediction_comparison = pack.table("evidence_prediction_comparison")

    assert summary["status"] == "Exact component-prediction replay"
    assert summary["model"] == PED_REPRO_MODEL
    assert summary["source_sheet"] == "PED Inputs"
    assert summary["description"] == PED_REPRO_DESCRIPTION
    assert float(pd.to_numeric(prediction_comparison["pred_delta_vs_evidence"], errors="coerce").abs().max()) <= 1e-8
    assert list(weights["Weight"]) == [1.0]
    assert reproducibility_ensemble_equation(pack) == "Prediction = 1.0*C1"

    delta = (
        pd.to_numeric(components["component_pred"], errors="coerce")
        - pd.to_numeric(components["rebuilt_pred"], errors="coerce")
    ).abs()
    assert float(delta.max()) <= 1e-8


def test_ped_inner_hpo_audit_is_partial_and_keeps_outer_replay_exact() -> None:
    pack = load_ped_inner_hpo_audit_pack()
    summary = ped_inner_hpo_audit_summary(pack)
    prediction_comparison = pack.table("evidence_prediction_comparison")

    assert pack.available
    assert not pack.missing_files
    assert PED_INNER_HPO_REPRO_ROOT.joinpath("model_registry.parquet").exists()
    assert summary["outer_status"] == "Exact component-prediction replay"
    assert float(summary["outer_max_abs_delta"]) <= 1e-8
    assert summary["inner_status"] == PED_INNER_HPO_AUDIT_STATUS
    assert float(summary["inner_max_abs_delta"]) > 1e-5
    assert float(pd.to_numeric(prediction_comparison["abs_delta_rebuilt_vs_evidence"], errors="coerce").max()) <= 1e-8


def test_ped_inner_hpo_source_artifacts_are_vendored_and_hash_backed() -> None:
    pack = load_ped_inner_hpo_audit_pack()
    manifest_path = PED_INNER_HPO_REPRO_ROOT / "source_artifacts_manifest.json"
    manifest_md_path = PED_INNER_HPO_REPRO_ROOT / "source_artifacts_manifest.md"
    source_root = PED_INNER_HPO_REPRO_ROOT / "source_artifacts"

    assert "source_artifacts_manifest.json" in REQUIRED_PED_INNER_HPO_AUDIT_FILES
    assert "source_artifacts_manifest.md" in REQUIRED_PED_INNER_HPO_AUDIT_FILES
    assert manifest_path.exists()
    assert manifest_md_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert not contains_local_path_token(manifest_text)

    manifest = json.loads(manifest_text)
    rows = manifest["artifacts"]
    assert rows
    assert manifest["local_paths_included"] is False
    assert "source artifacts vendored in repo" in ped_inner_hpo_audit_summary(pack)["source_artifact_status"]

    required_names = {
        "scripts/stage1_finalist_arbitration.py",
        "hpo_refinement_core_outputs/hpo_refined_ensemble_weights.csv",
        "finalist_arbitration_run_20260520_002339/candidate_config_inventory.csv",
        "finalist_arbitration_run_20260520_002339/ensemble_weights.csv",
    }
    assert required_names.issubset({row["artifact_name"] for row in rows})

    for row in rows:
        repo_path = Path(row["repo_relative_path"])
        path = Path(__file__).resolve().parents[1] / repo_path
        assert path.exists(), row
        assert source_root in path.parents or path == source_root
        assert int(row["size_bytes"]) <= 50 * 1024 * 1024
        assert len(row["sha256"]) == 64
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        assert not contains_local_path_token(row["repo_relative_path"])

    view = ped_inner_hpo_source_artifacts_view(pack)
    assert not view.empty
    assert view["SHA256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all()
    assert not contains_local_path_token(" ".join(view["Repo-relative path"].astype(str)))


def test_ped_inner_hpo_weights_are_grouped_by_source_file() -> None:
    pack = load_ped_inner_hpo_audit_pack()
    source_view = ped_inner_hpo_weight_source_view(pack)
    detail = ped_inner_hpo_weight_detail_view(pack)

    assert set(source_view["Source role"]) == {"HPO refinement source", "Arbitration lineage/context"}
    sums = source_view.set_index("Source role")["Per-source weight sum"]
    assert float(sums.loc["HPO refinement source"]) == pytest.approx(1.0, abs=1e-8)
    assert float(sums.loc["Arbitration lineage/context"]) == pytest.approx(0.4292679798198642, abs=1e-8)
    assert 1.4292679798198642 not in set(float(value) for value in source_view["Per-source weight sum"])
    assert source_view["SHA256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all()
    assert detail["SHA256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all()
    assert not contains_local_path_token(" ".join(source_view["Source file"].astype(str)))
    assert not contains_local_path_token(" ".join(detail["Source file"].astype(str)))
    assert source_view["Source file"].astype(str).str.startswith(
        "data/dashboard_evidence_pack_reproducibility/ped_inner_hpo/source_artifacts/"
    ).all()

    hpo_actual = detail[
        detail["Source role"].eq("HPO refinement source")
        & detail["Interpretation"].eq("Actual HPOREFINE component")
    ]
    assert set(hpo_actual["Inner component model"]) == {
        "PED__solver_static_convex_top18",
        "PED__solver_preq_convex_top18",
        "PED__diff__GBR_learning_rate0_05_max_depth1_n_estimators650__ylag__w40",
    }
    assert float(hpo_actual["Weight within source"].sum()) == pytest.approx(1.0, abs=1e-8)
    arbitration = detail[detail["Source role"].eq("Arbitration lineage/context")]
    assert set(arbitration["Interpretation"]) == {"Lineage/context only unless separately verified"}
    raw_local_reference = r"C:\Users\Adrian Desilvestro\Downloads\stage1_hpo_refinement_core_outputs\hpo_refined_ensemble_weights.csv"
    assert ped_inner_hpo_public_source_reference(pack, raw_local_reference).startswith(
        "data/dashboard_evidence_pack_reproducibility/ped_inner_hpo/source_artifacts/"
    )


def test_ped_inner_hpo_nested_trace_and_gap_register_show_partial_caveat() -> None:
    pack = load_ped_inner_hpo_audit_pack()
    nested = ped_inner_hpo_nested_trace_view(pack)
    gaps = ped_inner_hpo_gap_register_view(pack)

    assert not nested.empty
    assert {
        "Rebuilt inner prediction",
        "Stored outer component prediction",
        "Delta",
        "Abs delta",
        "Max abs inner delta",
    }.issubset(nested.columns)
    assert float(nested["Max abs inner delta"].max()) > 1e-5
    gap_text = gaps.fillna("").astype(str).agg(" ".join, axis=1).str.cat(sep=" | ")
    assert "feature_level_refit_not_attempted" in gap_text
    assert "inner_weighted_replay_mismatch" in gap_text


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


def test_heavy_ruc_auxiliary_views_have_weighted_ensemble_content() -> None:
    pack = load_reproducibility_pack("Heavy RUC volume")
    component_trace = reproducibility_component_trace_view(pack)
    feature_importance = reproducibility_feature_importance_view(pack)
    sensitivities = reproducibility_sensitivity_view(pack)

    assert not component_trace.empty
    assert {"Component", "Weight", "Component prediction", "Weighted contribution", "Final prediction", "Actual"}.issubset(
        component_trace.columns
    )
    assert {"C1", "C2", "C3", "C4"}.issubset(set(component_trace["Component"]))
    assert not feature_importance.empty
    assert set(feature_importance["feature_label"]) == {"C1", "C2", "C3", "C4"}
    assert not sensitivities.empty
    assert "not_available_from_parent_output" in sensitivities["scenario_variable"].astype(str).str.cat(sep=" | ")


def test_ped_auxiliary_views_have_component_replay_content_and_caveat() -> None:
    pack = load_reproducibility_pack("PED VKT per capita")
    registry = reproducibility_registry_view(pack)
    component_trace = reproducibility_component_trace_view(pack)
    feature_importance = reproducibility_feature_importance_view(pack)
    sensitivities = reproducibility_sensitivity_view(pack)
    scorecard = reproducibility_scorecard_view(pack)

    assert not registry.empty
    assert "inner model refit not replayed" in registry["Reproducibility status"].astype(str).str.cat(sep=" | ")
    assert not component_trace.empty
    assert {"Component", "Weight", "Component prediction", "Final prediction", "Actual", "Error (%)"}.issubset(
        component_trace.columns
    )
    assert set(component_trace["Component"]) == {"C1"}
    assert not feature_importance.empty
    assert set(feature_importance["feature_label"]) == {"C1"}
    assert not sensitivities.empty
    assert "Not available from replay-only parent predictions" in sensitivities["scenario_variable"].astype(str).str.cat(sep=" | ")
    assert not scorecard.empty
    assert float(scorecard.loc[scorecard["Score basis"].eq("Operational pooled"), "Pooled MAPE"].iloc[0]) == pytest.approx(
        2.473244, abs=0.000001
    )


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


def test_reproducibility_pack_does_not_modify_main_chart_source_tables() -> None:
    before = _chart_source_hashes()
    assert before, "Expected existing main chart-source tables."

    pack = load_light_ruc_reproducibility_pack()
    ped_pack = load_reproducibility_pack("PED VKT per capita")
    heavy_pack = load_reproducibility_pack("Heavy RUC volume")
    _ = light_ruc_registry_view(pack)
    _ = light_ruc_component_trace_view(pack)
    _ = light_ruc_feature_importance_view(pack)
    _ = light_ruc_sensitivity_view(pack)
    _ = reproducibility_component_trace_view(ped_pack)
    _ = reproducibility_feature_importance_view(ped_pack)
    _ = reproducibility_sensitivity_view(ped_pack)
    _ = reproducibility_scorecard_view(ped_pack)
    _ = reproducibility_component_trace_view(heavy_pack)
    _ = reproducibility_feature_importance_view(heavy_pack)
    _ = reproducibility_sensitivity_view(heavy_pack)

    after = _chart_source_hashes()
    assert after == before


def _chart_source_hashes() -> dict[str, str]:
    source_dir = ROOT / "artifacts" / "chart_sources"
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_dir.glob("*.csv"))
    }

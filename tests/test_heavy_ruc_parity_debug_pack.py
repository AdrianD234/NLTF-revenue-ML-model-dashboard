from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from model_dashboard.forecast_runner import model_capability_gap_register
from model_dashboard.heavy_ruc_forward import evaluate_heavy_ruc_forward_scorer


ROOT = Path(__file__).resolve().parents[1]
DEBUG_DIR = ROOT / "artifacts" / "heavy_ruc_forward_parity_debug"
REQUIRED_FILES = [
    "component_parity_summary.csv",
    "component_parity_rows.csv",
    "worst_rows.csv",
    "feature_matrix_comparison.csv",
    "training_window_comparison.csv",
    "origin_target_coverage_comparison.csv",
    "candidate_config_comparison.csv",
    "input_history_manifest.json",
    "heavy_ruc_parity_diagnosis.md",
    "canonical_history_comparison.csv",
    "canonical_feature_matrix_comparison.csv",
    "canonical_replay_summary.csv",
    "canonical_history_manifest.json",
]
PARITY_AUDIT = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc" / "forward_scorer_parity_audit.json"
C2 = "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64"
C4 = "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40"


def test_heavy_ruc_parity_debug_pack_exports_required_files() -> None:
    for filename in REQUIRED_FILES:
        path = DEBUG_DIR / filename
        assert path.exists(), filename
        assert path.stat().st_size > 0, filename


def test_heavy_ruc_parity_debug_pack_explains_failure() -> None:
    summary = pd.read_csv(DEBUG_DIR / "component_parity_summary.csv")
    assert set(summary["component_label"]) == {"C1", "C2", "C3", "C4"}
    assert summary["parity_status"].eq("failed").all()
    assert summary["missing_rows"].eq(0).all()
    assert summary["matched_rows"].eq(summary["stored_rows"]).all()
    c2 = summary.set_index("component_model").loc[C2]
    assert c2["max_abs_delta"] == summary["max_abs_delta"].max()
    assert c2["max_abs_delta"] > 1e-6

    feature_matrix = pd.read_csv(DEBUG_DIR / "feature_matrix_comparison.csv")
    current = feature_matrix[feature_matrix["case_id"].eq("current_debug_worst")]
    assert not current.empty
    assert current["component_model"].eq(C2).all()
    assert current["comparison_status"].eq("parent_feature_matrix_missing").all()
    assert current["feature_order"].tolist() == list(range(1, len(current) + 1))
    assert {"nominal_gdp_sa_nzd__log", "log_real_heavy_ruc_price__log_lead1"}.issubset(set(current["feature_name"]))

    coverage = pd.read_csv(DEBUG_DIR / "origin_target_coverage_comparison.csv")
    assert coverage["missing_rows"].eq(0).all()

    configs = pd.read_csv(DEBUG_DIR / "candidate_config_comparison.csv")
    assert configs["comparison_status"].eq("matched_locked_spec").all()

    manifest = json.loads((DEBUG_DIR / "input_history_manifest.json").read_text(encoding="utf-8"))
    assert manifest["parent_run_source_data"]["status"] == "missing_from_repo"
    assert manifest["current_repo_history_replay"]["parity_status"] == "failed"
    assert manifest["likely_root_cause"]["input_data_mismatch"] == "likely"
    assert manifest["likely_root_cause"]["missing_parent_run_fitted_estimators"] == "confirmed"

    diagnosis = (DEBUG_DIR / "heavy_ruc_parity_diagnosis.md").read_text(encoding="utf-8")
    assert "Heavy RUC must remain `parity_failed`" in diagnosis
    assert "numeric forward forecasts are not enabled" in diagnosis
    assert "parent-run feature matrix" in diagnosis


def test_heavy_ruc_canonical_history_audit_narrows_but_does_not_close_gap() -> None:
    summary = pd.read_csv(DEBUG_DIR / "canonical_replay_summary.csv")
    candidates = set(summary["history_candidate"])
    assert candidates == {"current_repo_model_input_history", "source_script_stage1_workbook_history"}
    assert summary["missing_rows"].eq(0).all()

    current = summary[summary["history_candidate"].eq("current_repo_model_input_history")]
    source = summary[summary["history_candidate"].eq("source_script_stage1_workbook_history")]
    assert current["max_abs_delta"].max() > source["max_abs_delta"].max()
    assert source.set_index("component_label").loc["C2", "parity_status"] == "passed"
    assert source.set_index("component_label").loc["C3", "parity_status"] == "failed"
    assert source.set_index("component_label").loc["C4", "parity_status"] == "failed"
    assert source.set_index("component_label").loc["C4", "max_abs_delta"] > 1e-6
    assert source[source["row_type"].eq("final_weighted")]["max_abs_delta"].iloc[0] > 1e-6

    manifest = json.loads((DEBUG_DIR / "canonical_history_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_script_workbook_history"]["input_sheet"] == "Stage 1 Inputs"
    assert manifest["source_script_workbook_history"]["engineered_feature_count"] > manifest["current_repo_history"]["engineered_feature_count"]
    assert manifest["history_recovery_status"] == "canonical_source_script_history_recovered_but_component_parity_failed"
    assert manifest["write_history_status"] == "not_written_component_or_final_parity_failed"
    assert manifest["root_cause_assessment"]["schiff_c2_input_path"] == "exact_replay_passed"
    assert manifest["root_cause_assessment"]["target_lagged_gbm_components"] == "failed_replay_for_c3_c4"
    assert manifest["root_cause_assessment"]["fitted_component_estimators"] == "missing_from_parent_run"

    history = pd.read_csv(DEBUG_DIR / "canonical_history_comparison.csv")
    assert not history[
        history["comparison_section"].eq("source_feature_inventory")
        & history["status"].eq("canonical_source_only")
    ].empty

    features = pd.read_csv(DEBUG_DIR / "canonical_feature_matrix_comparison.csv")
    assert not features.empty
    assert features["comparison_status"].eq("parent_feature_matrix_missing").all()


def test_heavy_ruc_audit_keeps_numeric_disabled_while_parity_failed() -> None:
    payload = json.loads(PARITY_AUDIT.read_text(encoding="utf-8"))
    assert payload["parity_status"] != "passed"
    assert payload["max_abs_delta"] > 1e-6
    assert payload["diagnosis"]["debug_pack_path"] == "artifacts/heavy_ruc_forward_parity_debug"
    assert payload["diagnosis"]["parent_run_source_data_status"] == "missing_from_repo"
    assert payload["diagnosis"]["capability_decision"] == "keep_parity_failed"
    assert payload["diagnosis"]["post_canonical_history_replay"]["parity_status"] == "failed"
    assert payload["diagnosis"]["post_canonical_history_replay"]["failing_component"] == C4

    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.capability_status == "parity_failed"
    assert audit.forecast_capability_available is False
    assert audit.max_parity_delta is not None
    assert audit.max_parity_delta > 1e-6
    assert audit.failing_component == C4

    capabilities = model_capability_gap_register(ROOT).set_index("stream")
    assert capabilities.loc["HEAVY_RUC", "capability_status"] == "parity_failed"
    assert capabilities.loc["HEAVY_RUC", "forecast_capability_available"] == False
    assert capabilities.loc["HEAVY_RUC", "max_parity_delta"] > 1e-6
    assert capabilities.loc["LIGHT_RUC", "capability_status"] == "numeric_forecast_available"
    assert capabilities.loc["PED", "capability_status"] == "parity_failed"

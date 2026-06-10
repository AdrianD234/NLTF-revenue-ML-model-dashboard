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
]
PARITY_AUDIT = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc" / "forward_scorer_parity_audit.json"
C2 = "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64"


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


def test_heavy_ruc_audit_keeps_numeric_disabled_while_parity_failed() -> None:
    payload = json.loads(PARITY_AUDIT.read_text(encoding="utf-8"))
    assert payload["parity_status"] != "passed"
    assert payload["max_abs_delta"] > 1e-6
    assert payload["diagnosis"]["debug_pack_path"] == "artifacts/heavy_ruc_forward_parity_debug"
    assert payload["diagnosis"]["parent_run_source_data_status"] == "missing_from_repo"

    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.capability_status == "parity_failed"
    assert audit.forecast_capability_available is False
    assert audit.max_parity_delta is not None
    assert audit.max_parity_delta > 1e-6
    assert audit.failing_component == C2

    capabilities = model_capability_gap_register(ROOT).set_index("stream")
    assert capabilities.loc["HEAVY_RUC", "capability_status"] == "parity_failed"
    assert capabilities.loc["HEAVY_RUC", "forecast_capability_available"] == False
    assert capabilities.loc["HEAVY_RUC", "max_parity_delta"] > 1e-6
    assert capabilities.loc["LIGHT_RUC", "capability_status"] == "numeric_forecast_available"
    assert capabilities.loc["PED", "capability_status"] == "parity_failed"

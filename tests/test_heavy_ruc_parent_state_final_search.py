from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pandas as pd

import app
from model_dashboard.forecast_runner import model_capability_gap_register
from model_dashboard.heavy_ruc_forward import evaluate_heavy_ruc_forward_scorer


ROOT = Path(__file__).resolve().parents[1]
DEBUG_DIR = ROOT / "artifacts" / "heavy_ruc_forward_parity_debug"
REPRO_ROOT = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc"
MANIFEST_PATH = DEBUG_DIR / "parent_state_search_manifest.json"
CANDIDATES_PATH = DEBUG_DIR / "parent_state_candidates.csv"
REPORT_PATH = DEBUG_DIR / "parent_state_search_report.md"
DECISION_PATH = DEBUG_DIR / "final_heavy_forward_capability_decision.md"
PARITY_AUDIT_PATH = REPRO_ROOT / "forward_scorer_parity_audit.json"
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
FINAL_CONCLUSION = (
    "Original parent C3/C4 fitted estimator or feature matrix not retained. "
    "Heavy RUC cannot safely score new assumption rows from repo-local artifacts."
)


def test_final_parent_state_search_outputs_exist_and_are_sanitized() -> None:
    for path in [MANIFEST_PATH, CANDIDATES_PATH, REPORT_PATH, DECISION_PATH]:
        assert path.exists(), path
        assert path.stat().st_size > 0, path

    public_text = "\n".join(
        [
            MANIFEST_PATH.read_text(encoding="utf-8"),
            CANDIDATES_PATH.read_text(encoding="utf-8"),
            REPORT_PATH.read_text(encoding="utf-8"),
            DECISION_PATH.read_text(encoding="utf-8"),
            PARITY_AUDIT_PATH.read_text(encoding="utf-8"),
        ]
    )
    for token in ["C:\\Users", "C:/Users", "Downloads", "OneDrive", "AppData"]:
        assert token not in public_text
    assert FINAL_CONCLUSION in public_text


def test_final_parent_state_search_manifest_records_no_recoverable_parent_state() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["audit_name"] == "heavy_ruc_final_parent_state_recovery"
    assert manifest["recoverable_parent_state_found"] is False
    assert manifest["recoverable_parent_feature_matrix_found"] is False
    assert manifest["parent_forward_state"]["status"] == "not_found"
    assert manifest["parent_feature_matrices"]["status"] == "not_found"
    assert manifest["parity_rerun_status"] == "not_run_no_parent_state_or_exact_matrix_recovered"
    assert manifest["capability_decision"] == "keep_parity_failed"
    assert manifest["final_governed_gap_conclusion"] == FINAL_CONCLUSION
    assert manifest["stored_prediction_replay_status"] == "available_from_stored_parent_component_predictions"
    assert manifest["training_fit_source_refit_status"] == "available_from_source_refit_state_not_parent_fitted_state"
    assert manifest["new_row_forward_scoring_status"] == "unavailable_until_parent_state_parity_passes"


def test_final_parent_state_candidates_are_hash_backed_and_classified() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH, keep_default_na=False)
    assert not candidates.empty
    assert "original_parent_fitted_state" not in set(candidates["artifact_role"])
    assert "exact_parent_feature_matrix" not in set(candidates["artifact_role"])
    assert "source_refit_state_not_parent" in set(candidates["artifact_role"])
    assert "source_refit_feature_matrix_not_parent" in set(candidates["artifact_role"])
    assert "raw_parent_component_forecast_source" in set(candidates["artifact_role"])

    blank_hash = candidates[candidates["sha256"].eq("")]
    assert blank_hash["size_bytes"].gt(MAX_ARTIFACT_BYTES).all()
    assert blank_hash["container_sha256"].ne("").all()
    hashed = candidates[candidates["sha256"].ne("")]
    assert hashed["sha256"].str.fullmatch(r"[0-9a-f]{64}").all()


def test_heavy_ruc_final_search_keeps_numeric_disabled_until_parity_passes() -> None:
    payload = json.loads(PARITY_AUDIT_PATH.read_text(encoding="utf-8"))
    assert payload["capability_status"] == "parity_failed"
    assert payload["capability_decision"] == "keep_parity_failed"
    assert payload["parity_status"] == "failed"
    assert payload["data_scope"].startswith("canonical_source_script_history")
    assert payload["max_abs_delta"] > 1e-6
    assert FINAL_CONCLUSION in payload["missing_feature_or_artifact"]
    assert payload["diagnosis"]["final_parent_state_recovery_status"] == "original_parent_state_not_found"
    assert payload["diagnosis"]["final_parent_state_search"]["recoverable_parent_state_found"] is False
    assert payload["diagnosis"]["final_parent_state_search"]["recoverable_parent_feature_matrix_found"] is False

    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.capability_status == "parity_failed"
    assert audit.forecast_capability_available is False
    assert FINAL_CONCLUSION in audit.gap_reason

    capabilities = model_capability_gap_register(ROOT).set_index("stream")
    assert capabilities.loc["HEAVY_RUC", "capability_status"] == "parity_failed"
    assert capabilities.loc["LIGHT_RUC", "capability_status"] == "numeric_forecast_available"
    assert capabilities.loc["PED", "capability_status"] == "parity_failed"


def test_forecast_builder_heavy_governed_gap_wording_is_precise() -> None:
    heavy_row = pd.Series(
        {
            "stream": "HEAVY_RUC",
            "stream_label": "Heavy RUC volume",
            "gap_code": "heavy_ruc_component_forward_scorers_missing",
            "availability_status": "governed_gap",
        }
    )
    ped_row = pd.Series(
        {
            "stream": "PED",
            "stream_label": "PED VKT per capita",
            "gap_code": "ped_inner_hpo_static_solver_forward_scorer_missing",
            "availability_status": "governed_gap",
        }
    )
    assert app._short_forecast_gap_reason(heavy_row) == app.HEAVY_RUC_FORECAST_GAP_REASON
    assert "exact stored prediction replay is available" in app._short_forecast_gap_reason(heavy_row)
    assert "new-row scoring is unavailable until parent-state parity passes" in app._short_forecast_gap_reason(heavy_row)
    assert app._short_forecast_gap_reason(ped_row) == app.GENERIC_FORECAST_GAP_REASON
    assert app._forecast_builder_governed_gap_annotation("Heavy RUC volume") == (
        "Governed gap: Heavy new-row scoring unavailable until parent-state parity passes"
    )
    assert "not yet verified" not in app._short_forecast_gap_reason(heavy_row)


def test_no_oversized_parent_or_source_artifacts_are_committed() -> None:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True)
    checked_prefixes = (
        "data/dashboard_evidence_pack_reproducibility/heavy_ruc/parent_forward_state/",
        "data/dashboard_evidence_pack_reproducibility/heavy_ruc/parent_feature_matrices/",
        "data/dashboard_evidence_pack_reproducibility/heavy_ruc/source_artifacts/",
    )
    for relative in result.stdout.splitlines():
        if not relative.startswith(checked_prefixes):
            continue
        path = ROOT / relative
        assert path.stat().st_size <= MAX_ARTIFACT_BYTES, relative

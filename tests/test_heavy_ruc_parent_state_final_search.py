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
TRIAGE_CLASSIFICATION_PATH = DEBUG_DIR / "triage_file_classification.csv"
TRIAGE_FINDINGS_PATH = DEBUG_DIR / "triage_parent_state_findings.md"
TRIAGE_PARITY_PATH = DEBUG_DIR / "triage_parity_rerun_summary.csv"
PARITY_AUDIT_PATH = REPRO_ROOT / "forward_scorer_parity_audit.json"
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
FINAL_CONCLUSION = (
    "Original parent C3/C4 fitted estimator or feature matrix not retained. "
    "Heavy RUC cannot safely score new assumption rows from repo-local artifacts."
)
TRIAGE_CONCLUSION = (
    "Triage pack inspected: no original C3/C4 parent fitted estimator or exact parent feature matrix was found."
)


def test_final_parent_state_search_outputs_exist_and_are_sanitized() -> None:
    for path in [
        MANIFEST_PATH,
        CANDIDATES_PATH,
        REPORT_PATH,
        DECISION_PATH,
        TRIAGE_CLASSIFICATION_PATH,
        TRIAGE_FINDINGS_PATH,
        TRIAGE_PARITY_PATH,
    ]:
        assert path.exists(), path
        assert path.stat().st_size > 0, path

    public_text = "\n".join(
        [
            MANIFEST_PATH.read_text(encoding="utf-8"),
            CANDIDATES_PATH.read_text(encoding="utf-8"),
            REPORT_PATH.read_text(encoding="utf-8"),
            DECISION_PATH.read_text(encoding="utf-8"),
            TRIAGE_CLASSIFICATION_PATH.read_text(encoding="utf-8"),
            TRIAGE_FINDINGS_PATH.read_text(encoding="utf-8"),
            TRIAGE_PARITY_PATH.read_text(encoding="utf-8"),
            PARITY_AUDIT_PATH.read_text(encoding="utf-8"),
        ]
    )
    for token in ["C:\\Users", "C:/Users", "Downloads", "OneDrive", "AppData"]:
        assert token not in public_text
    assert FINAL_CONCLUSION in public_text
    assert TRIAGE_CONCLUSION in public_text


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
    assert TRIAGE_CONCLUSION in payload["missing_feature_or_artifact"]
    assert payload["diagnosis"]["final_parent_state_recovery_status"] == "original_parent_state_not_found"
    assert payload["diagnosis"]["final_parent_state_search"]["recoverable_parent_state_found"] is False
    assert payload["diagnosis"]["final_parent_state_search"]["recoverable_parent_feature_matrix_found"] is False
    assert payload["diagnosis"]["triage_recoverable_parent_state_found"] is False
    assert payload["diagnosis"]["triage_recoverable_parent_feature_matrix_found"] is False
    assert payload["diagnosis"]["triage_parity_passed"] is False

    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.capability_status == "parity_failed"
    assert audit.forecast_capability_available is False
    assert TRIAGE_CONCLUSION in audit.gap_reason

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
    assert "stored historical weighted replay and training-fit R2 are available" in app._short_forecast_gap_reason(heavy_row)
    assert "New-row Heavy forecasts require exact C3/C4 parent-state parity" in app._short_forecast_gap_reason(heavy_row)
    assert "current status: governed gap" in app._short_forecast_gap_reason(heavy_row)
    assert app._short_forecast_gap_reason(ped_row) == app.GENERIC_FORECAST_GAP_REASON
    assert app._forecast_builder_governed_gap_annotation("Heavy RUC volume") == (
        "Governed gap: Heavy requires exact C3/C4 parent-state parity"
    )
    assert "not yet verified" not in app._short_forecast_gap_reason(heavy_row)


def test_triage_pack_classification_and_parity_summary_keep_heavy_disabled() -> None:
    classification = pd.read_csv(TRIAGE_CLASSIFICATION_PATH, keep_default_na=False)
    assert not classification.empty
    assert set(classification["classification"]).issubset(
        {
            "original_parent_estimator",
            "parent_feature_matrix",
            "parent_component_predictions",
            "source_refit_state",
            "repo_debug_artifact",
            "irrelevant",
            "too_large/skipped",
        }
    )
    assert "original_parent_estimator" not in set(classification["classification"])
    assert "parent_feature_matrix" not in set(classification["classification"])
    assert "parent_component_predictions" in set(classification["classification"])
    assert "source_refit_state" in set(classification["classification"])
    c3_c4 = classification[classification["target_component_match"].astype(str).str.lower().eq("true")]
    assert not c3_c4.empty
    assert c3_c4["classification"].eq("source_refit_state").all()
    assert c3_c4["notes"].str.contains("not original parent fitted state", case=False, na=False).all()

    parity = pd.read_csv(TRIAGE_PARITY_PATH)
    assert parity["heavy_numeric_enabled"].eq(False).all()
    assert parity["triage_rerun_status"].eq("not_run_no_recovered_parent_state_or_exact_matrix").all()
    failed = parity[pd.to_numeric(parity["max_abs_delta"], errors="coerce").gt(1e-6)]
    assert not failed.empty
    assert {"C3", "C4", "C1_C4_weighted"}.issubset(set(failed["component_label"]))


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

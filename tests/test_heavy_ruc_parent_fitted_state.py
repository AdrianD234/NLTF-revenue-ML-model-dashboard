from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.forecast_runner import model_capability_gap_register
from model_dashboard.heavy_ruc_forward import evaluate_heavy_ruc_forward_scorer


ROOT = Path(__file__).resolve().parents[1]
REPRO_ROOT = ROOT / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc"
DEBUG_DIR = ROOT / "artifacts" / "heavy_ruc_forward_parity_debug"
MANIFEST_PATH = REPRO_ROOT / "forward_state_manifest.json"
PARITY_AUDIT_PATH = REPRO_ROOT / "forward_scorer_parity_audit.json"
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
C3 = "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52"
C4 = "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40"


def test_heavy_ruc_forward_state_manifest_is_hash_backed_and_sanitized() -> None:
    manifest = _read_json(MANIFEST_PATH)
    public_text = MANIFEST_PATH.read_text(encoding="utf-8") + PARITY_AUDIT_PATH.read_text(encoding="utf-8")

    assert manifest["audit_name"] == "heavy_ruc_forward_parent_fitted_state_recovery"
    assert manifest["capability_decision"] == "keep_parity_failed"
    assert manifest["target_lag_recursion"]["documented_policy"] == "recursive_predicted_lags"
    assert "C:\\Users" not in public_text
    assert "Downloads" not in public_text
    assert "OneDrive" not in public_text
    assert "NaN" not in public_text

    artifact_records = manifest["state_export"]["artifact_records"]
    assert artifact_records
    for record in artifact_records:
        path = ROOT / record["repo_relative_path"]
        assert path.exists(), record
        assert path.stat().st_size == record["size_bytes"]
        assert _sha256(path) == record["sha256"]
        assert record["size_bytes"] <= MAX_ARTIFACT_BYTES


def test_heavy_ruc_forward_state_files_are_present_and_small() -> None:
    manifest = _read_json(MANIFEST_PATH)
    state_files = manifest["state_export"]["state_files"]
    present = [record for record in state_files if record["repo_relative_path"]]

    assert manifest["state_export"]["state_file_count"] == len(present) == 168
    assert manifest["state_export"]["oversized_artifacts"] == []
    assert {record["component_label"] for record in present} == {"C1", "C2", "C3", "C4"}
    for record in present:
        path = ROOT / record["repo_relative_path"]
        assert path.exists(), record
        assert path.suffix == ".joblib"
        assert path.stat().st_size <= MAX_ARTIFACT_BYTES
        assert _sha256(path) == record["sha256"]
        assert record["status"] == "joblib_serialized_source_refit_state"
        assert "source-code refit" in record["notes"]


def test_heavy_ruc_forward_feature_matrices_document_target_lag_state() -> None:
    matrix_dir = REPRO_ROOT / "forward_feature_matrices"
    required = {
        "training_feature_matrix.parquet",
        "prediction_feature_rows.parquet",
        "target_lag_state.parquet",
        "feature_column_order.parquet",
    }
    for filename in required:
        assert (matrix_dir / filename).exists(), filename

    feature_order = pd.read_parquet(matrix_dir / "feature_column_order.parquet")
    target_lag_state = pd.read_parquet(matrix_dir / "target_lag_state.parquet")
    prediction_rows = pd.read_parquet(matrix_dir / "prediction_feature_rows.parquet")

    assert {"C1", "C2", "C3", "C4"}.issubset(set(feature_order["component_label"]))
    target_lagged = feature_order[feature_order["component_label"].isin(["C3", "C4"])]
    assert target_lagged["is_target_lag_feature"].any()
    assert set(target_lag_state["component_label"]) == {"C1", "C3", "C4"}
    assert "recursive_predicted_validation_horizon" in " ".join(target_lag_state["source_roles_json"].astype(str))
    assert prediction_rows["target_lag_policy"].str.contains("recursive_predicted_lags", na=False).any()


def test_heavy_ruc_target_lag_recursion_and_fitted_state_gap_are_explicit() -> None:
    recursion = pd.read_csv(DEBUG_DIR / "target_lag_recursion_audit.csv")
    fitted = pd.read_csv(DEBUG_DIR / "c3_c4_fitted_state_audit.csv")
    diagnosis = (DEBUG_DIR / "heavy_ruc_parity_diagnosis.md").read_text(encoding="utf-8")

    assert set(recursion["component_label"]) == {"C3", "C4"}
    assert {"recursive_predicted", "actual_after_each_step", "actual_all_available", "stored_component_after_each_step", "no_update"}.issubset(
        set(recursion["recursion_policy"])
    )
    recursive = recursion[recursion["recursion_policy"].eq("recursive_predicted")].set_index("component_model")
    assert recursive.loc[C3, "max_abs_delta"] == pytest.approx(4113063.8222726583)
    assert recursive.loc[C4, "max_abs_delta"] == pytest.approx(12911117.047347665)
    assert recursive.loc[C3, "horizon_1_max_abs_delta"] > 1e-6
    assert recursive.loc[C4, "horizon_1_max_abs_delta"] > 1e-6

    component_rows = fitted[fitted["row_type"].eq("component")].set_index("component_model")
    assert component_rows.loc[C3, "parity_status"] == "failed"
    assert component_rows.loc[C4, "parity_status"] == "failed"
    assert component_rows.loc[C3, "fitted_state_status"] == "source_refit_exported_parent_fitted_state_missing"
    assert component_rows.loc[C4, "fitted_state_status"] == "source_refit_exported_parent_fitted_state_missing"
    assert "uses recursive predicted target lags" in diagnosis
    assert "not labelled as parent fitted estimators" in diagnosis


def test_heavy_ruc_numeric_remains_disabled_until_all_parity_rows_pass(monkeypatch) -> None:
    # Pin to the legacy governance path: this test documents that the
    # ARCHIVED legacy finalist remains non-forward-scoreable. The vNext
    # finalist capability is covered by test_forward_scorer_governance.
    import model_dashboard.vnext_forward_integration as vfi

    monkeypatch.setattr(vfi, "evaluate_vnext_forward_scorer", lambda root, stream: None)
    manifest = _read_json(MANIFEST_PATH)
    parity_rows = pd.DataFrame(manifest["parity"]["component_and_final_summary"])
    assert (pd.to_numeric(parity_rows["max_abs_delta"], errors="coerce") > 1e-6).any()
    assert manifest["capability_decision"] == "keep_parity_failed"

    audit_payload = _read_json(PARITY_AUDIT_PATH)
    assert audit_payload["parity_status"] == "failed"
    assert audit_payload["diagnosis"]["capability_decision"] == "keep_parity_failed"
    assert audit_payload["diagnosis"]["target_lag_policy"] == "recursive_predicted_lags"

    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.capability_status == "parity_failed"
    assert audit.forecast_capability_available is False
    assert audit.failing_component == C4

    capabilities = model_capability_gap_register(ROOT).set_index("stream")
    assert capabilities.loc["HEAVY_RUC", "capability_status"] == "parity_failed"
    assert capabilities.loc["LIGHT_RUC", "capability_status"] == "numeric_forecast_available"
    assert capabilities.loc["PED", "capability_status"] == "parity_failed"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

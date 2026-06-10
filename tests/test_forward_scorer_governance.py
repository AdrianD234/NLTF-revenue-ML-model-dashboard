from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from model_dashboard.heavy_ruc_forward import HEAVY_RUC_COMPONENTS, evaluate_heavy_ruc_forward_scorer
from model_dashboard.ped_forward import PED_REQUIRED_COMPONENTS, evaluate_ped_forward_scorer


ROOT = Path(__file__).resolve().parents[1]


def test_heavy_ruc_forward_scorer_audit_preserves_governed_gap() -> None:
    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.stream == "HEAVY_RUC"
    assert audit.forecast_capability_available is False
    assert audit.capability_status == "insufficient_artifacts"
    assert audit.gap_code == "heavy_ruc_component_forward_scorers_missing"
    assert audit.parity_status == "not_run_insufficient_artifacts"
    assert audit.stored_replay_max_delta is not None
    assert 0 <= audit.stored_replay_max_delta <= 1e-6
    assert audit.max_parity_delta is None
    assert len(audit.required_components) == 4
    assert audit.required_components == tuple(component["component_model"] for component in HEAVY_RUC_COMPONENTS)
    assert "fitted component coefficients or serialized estimators are unavailable" in audit.gap_reason
    assert "data/dashboard_evidence_pack_reproducibility/heavy_ruc/source_artifacts is absent" in audit.gap_reason
    assert audit.source_artifact_hashes


def test_ped_forward_scorer_audit_preserves_parity_failed_gap() -> None:
    audit = evaluate_ped_forward_scorer(ROOT)
    assert audit.stream == "PED"
    assert audit.forecast_capability_available is False
    assert audit.capability_status == "parity_failed"
    assert audit.gap_code == "ped_inner_hpo_static_solver_forward_scorer_missing"
    assert audit.parity_status == "failed_inner_hpo_replay_delta"
    assert audit.max_parity_delta is not None
    assert audit.max_parity_delta > 1
    assert audit.stored_replay_max_delta == 0.0
    assert audit.required_components == PED_REQUIRED_COMPONENTS
    assert "feature_level_refit_not_attempted" in audit.gap_reason
    assert audit.source_artifact_hashes


def test_forward_scorer_export_scripts_emit_json_records() -> None:
    for script, expected_stream in [
        ("scripts/export_heavy_ruc_forward_scorer.py", "HEAVY_RUC"),
        ("scripts/export_ped_forward_scorer.py", "PED"),
    ]:
        result = subprocess.run(
            [sys.executable, str(ROOT / script), "--repo-root", str(ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["stream"] == expected_stream
        assert payload["forecast_capability_available"] is False
        assert payload["source_artifact_hashes"]


def test_forward_scorer_code_does_not_use_broad_search() -> None:
    forbidden = ["rglob(", "glob(\"**", "glob('**", "os.walk", "Path.home("]
    checked_files = [
        "model_dashboard/forward_scorer_governance.py",
        "model_dashboard/heavy_ruc_forward.py",
        "model_dashboard/ped_forward.py",
        "scripts/export_heavy_ruc_forward_scorer.py",
        "scripts/export_ped_forward_scorer.py",
    ]
    for relative in checked_files:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), relative

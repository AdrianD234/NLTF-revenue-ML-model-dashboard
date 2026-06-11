from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from model_dashboard.heavy_ruc_forward import HEAVY_RUC_COMPONENTS, evaluate_heavy_ruc_forward_scorer
from model_dashboard.ped_forward import PED_REQUIRED_COMPONENTS, evaluate_ped_forward_scorer


ROOT = Path(__file__).resolve().parents[1]
C4 = "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40"


def test_heavy_ruc_vnext_scorer_takes_precedence_when_pack_present() -> None:
    import model_dashboard.vnext_forward_integration as vfi

    if not vfi.vnext_pack_present(ROOT, "HEAVY_RUC"):
        import pytest

        pytest.skip("Heavy RUC vNext pack not present")
    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.stream == "HEAVY_RUC"
    assert audit.model.startswith("HEAVY_RUC__VNEXT")
    assert audit.capability_status in {"numeric_forecast_available", "parity_failed"}
    if audit.capability_status == "numeric_forecast_available":
        assert audit.forecast_capability_available is True
        assert audit.parity_status == "passed"
        assert audit.max_parity_delta is not None and audit.max_parity_delta <= 1e-6
    assert audit.source_artifact_hashes


def test_heavy_ruc_forward_scorer_audit_preserves_governed_gap(monkeypatch) -> None:
    import model_dashboard.vnext_forward_integration as vfi

    monkeypatch.setattr(vfi, "evaluate_vnext_forward_scorer", lambda root, stream: None)
    audit = evaluate_heavy_ruc_forward_scorer(ROOT)
    assert audit.stream == "HEAVY_RUC"
    assert audit.forecast_capability_available is False
    assert audit.capability_status == "parity_failed"
    assert audit.gap_code == "heavy_ruc_component_forward_scorers_missing"
    assert audit.parity_status == "failed_canonical_history_component_replay"
    assert audit.stored_replay_max_delta is not None
    assert 0 <= audit.stored_replay_max_delta <= 1e-6
    assert audit.max_parity_delta is not None
    assert audit.max_parity_delta > 1
    assert audit.failing_component == C4
    assert len(audit.required_components) == 4
    assert audit.required_components == tuple(component["component_model"] for component in HEAVY_RUC_COMPONENTS)
    assert "Source-script Stage 1 workbook history was recovered" in audit.gap_reason
    assert "target-lagged GBM components C3/C4 still exceed parity tolerance" in audit.gap_reason
    assert "parent fitted component estimators" in audit.gap_reason
    assert audit.source_artifact_hashes


def test_heavy_ruc_component_configs_and_weights_match_locked_spec() -> None:
    expected = {
        "C1": (
            "HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64",
            0.469332,
        ),
        "C2": (
            "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64",
            0.281844,
        ),
        "C3": (
            "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52",
            0.144373,
        ),
        "C4": (
            "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40",
            0.104451,
        ),
    }
    observed = {
        component["label"]: (component["component_model"], component["component_weight"])
        for component in HEAVY_RUC_COMPONENTS
    }
    assert observed == expected


def test_ped_vnext_scorer_takes_precedence_when_pack_present() -> None:
    import model_dashboard.vnext_forward_integration as vfi

    if not vfi.vnext_pack_present(ROOT, "PED"):
        import pytest

        pytest.skip("PED vNext pack not present")
    audit = evaluate_ped_forward_scorer(ROOT)
    assert audit.stream == "PED"
    assert audit.model.startswith("PED__VNEXT")
    assert audit.capability_status in {"numeric_forecast_available", "parity_failed"}
    if audit.capability_status == "numeric_forecast_available":
        assert audit.forecast_capability_available is True
        assert audit.parity_status == "passed"
    assert audit.source_artifact_hashes


def test_ped_forward_scorer_audit_preserves_parity_failed_gap(monkeypatch) -> None:
    import model_dashboard.vnext_forward_integration as vfi

    monkeypatch.setattr(vfi, "evaluate_vnext_forward_scorer", lambda root, stream: None)
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
        # With the vNext pack present the capability may be numeric; the
        # payload must agree with the in-process evaluator either way.
        evaluator = {
            "HEAVY_RUC": evaluate_heavy_ruc_forward_scorer,
            "PED": evaluate_ped_forward_scorer,
        }[expected_stream]
        expected_available = bool(evaluator(ROOT).forecast_capability_available)
        assert payload["forecast_capability_available"] is expected_available
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

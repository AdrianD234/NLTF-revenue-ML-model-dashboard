from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from model_dashboard.heavy_ruc_forward import HEAVY_RUC_COMPONENTS, evaluate_heavy_ruc_forward_scorer
from model_dashboard.ped_forward import PED_REQUIRED_COMPONENTS, evaluate_ped_forward_scorer


ROOT = Path(__file__).resolve().parents[1]
C4 = "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40"


def test_heavy_ruc_forward_scorer_audit_preserves_governed_gap() -> None:
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

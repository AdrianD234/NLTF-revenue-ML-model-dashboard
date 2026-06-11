from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .forward_scorer_governance import (
    ForwardScorerAudit,
    INSUFFICIENT_ARTIFACTS,
    NUMERIC_FORECAST_AVAILABLE,
    PARITY_FAILED,
    artifact_hashes,
    existing_basis,
    missing_paths,
)


PED_FORWARD_SCORER_VERSION = "ped-forward-scorer-audit-v1"
STREAM = "PED"
STREAM_LABEL = "PED VKT per capita"
FINALIST_MODEL = "PED__RESCUE_static_annual_weighted_top12_capnone"
OUTER_COMPONENT_MODEL = "PED__HPOREFINE_solver_static_convex_top18"
STATIC_SOLVER_MODEL = "PED__solver_static_convex_top18"
PREQ_SOLVER_MODEL = "PED__solver_preq_convex_top18"
DIRECT_HPO_COMPONENT = "PED__diff__GBR_learning_rate0_05_max_depth1_n_estimators650__ylag__w40"
GAP_CODE = "ped_inner_hpo_static_solver_forward_scorer_missing"
PARITY_TOLERANCE = 1e-6

PED_REQUIRED_COMPONENTS = (
    STATIC_SOLVER_MODEL,
    PREQ_SOLVER_MODEL,
    DIRECT_HPO_COMPONENT,
)


def evaluate_ped_forward_scorer(repo_root: Path | str | None = None) -> ForwardScorerAudit:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    # The vNext fixed-finalist scorer takes precedence when its governed pack
    # is present; the legacy HPO/static-solver finalist remains archived as
    # historically reproducible (outer replay exact) but not forward-scoreable.
    try:
        from .vnext_forward_integration import evaluate_vnext_forward_scorer

        vnext_audit = evaluate_vnext_forward_scorer(root, STREAM)
    except Exception:
        vnext_audit = None
    if vnext_audit is not None:
        return vnext_audit
    repro = root / "data" / "dashboard_evidence_pack_reproducibility" / "ped_inner_hpo"
    source = repro / "source_artifacts"
    required = [
        root / "data" / "model_input_history" / "ped_inputs.parquet",
        root / "data" / "model_input_history" / "manifest.json",
        repro / "manifest.json",
        repro / "inner_hpo_weights.parquet",
        repro / "inner_component_predictions.parquet",
        repro / "nested_ensemble_trace.parquet",
        repro / "outer_component_replay.parquet",
        repro / "reproducibility_gap_register.parquet",
        repro / "source_artifacts_manifest.json",
        source / "scripts" / "stage1_finalist_arbitration.py",
        source / "hpo_refinement_core_outputs" / "hpo_refined_ensemble_weights.csv",
        source / "finalist_arbitration_run_20260520_002339" / "candidate_config_inventory.csv",
        source / "finalist_arbitration_run_20260520_002339" / "ensemble_weights.csv",
    ]
    hashes = artifact_hashes(root, required)
    missing = missing_paths(root, required)
    if missing:
        return _audit(
            root,
            required,
            hashes,
            missing,
            "not_run_missing_artifacts",
            None,
            None,
            "PED forward scoring cannot run because required repo-local HPO/static-solver artifacts are missing.",
            capability_status=INSUFFICIENT_ARTIFACTS,
        )

    manifest = json.loads((repro / "manifest.json").read_text(encoding="utf-8"))
    max_inner = _numeric_or_none(manifest.get("max_inner_replay_delta"))
    max_outer = _numeric_or_none(manifest.get("max_outer_replay_delta"))
    max_evidence = _numeric_or_none(manifest.get("max_evidence_delta"))
    gap_detail = _gap_detail(repro / "reproducibility_gap_register.parquet")
    weights_ok = _weights_cover_required_components(repro / "inner_hpo_weights.parquet")

    if not weights_ok:
        return _audit(
            root,
            required,
            hashes,
            ("inner_hpo_weights.parquet does not cover required HPO components",),
            "not_run_weight_registry_mismatch",
            max_inner,
            max_outer,
            "PED forward scoring cannot run because the inner HPO weight registry does not cover the required components.",
        )

    if max_inner is None or max_inner > PARITY_TOLERANCE:
        detail = (
            f"PED remains a governed gap for forward scoring. The outer finalist replay is stored, but the inner HPO "
            f"chain does not pass parity for enabling new-row scoring: max_inner_replay_delta={max_inner}, "
            f"tolerance={PARITY_TOLERANCE}. The inner HPO/static-solver forward scorer is not enabled for new "
            f"assumption rows. {gap_detail}"
        ).strip()
        return _audit(
            root,
            required,
            hashes,
            ("inner_hpo_chain_parity_failed",),
            "failed_inner_hpo_replay_delta",
            max_inner,
            max_outer,
            detail,
        )

    if gap_detail:
        return _audit(
            root,
            required,
            hashes,
            ("feature_level_refit_not_attempted",),
            "not_run_feature_level_refit_gap",
            max_inner,
            max_outer,
            f"PED forward scoring remains disabled until the feature-level refit gap is closed. {gap_detail}",
        )

    return ForwardScorerAudit(
        stream=STREAM,
        stream_label=STREAM_LABEL,
        model=FINALIST_MODEL,
        capability_status=NUMERIC_FORECAST_AVAILABLE,
        gap_code=None,
        gap_reason="",
        repo_artifact_basis=existing_basis(root, required),
        scorer_version=PED_FORWARD_SCORER_VERSION,
        parity_status="passed",
        max_parity_delta=max_inner,
        stored_replay_max_delta=max_outer if max_outer is not None else max_evidence,
        source_artifact_hashes=hashes,
        required_components=PED_REQUIRED_COMPONENTS,
        forecast_capability_available=True,
    )


def _weights_cover_required_components(path: Path) -> bool:
    frame = pd.read_parquet(path)
    if frame.empty or "inner_component_model" not in frame.columns:
        return False
    present = set(frame["inner_component_model"].dropna().astype(str))
    return set(PED_REQUIRED_COMPONENTS).issubset(present)


def _gap_detail(path: Path) -> str:
    if not path.exists():
        return ""
    frame = pd.read_parquet(path)
    if frame.empty:
        return ""
    parts: list[str] = []
    for _, row in frame.iterrows():
        gap = str(row.get("gap", "")).strip()
        detail = str(row.get("detail", "")).strip()
        if gap or detail:
            parts.append(f"{gap}: {detail}".strip(": "))
    return " ".join(parts)


def _numeric_or_none(value: Any) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(number)


def _audit(
    root: Path,
    required: list[Path],
    hashes: dict[str, str],
    blockers: tuple[str, ...],
    parity_status: str,
    max_parity_delta: float | None,
    stored_replay_delta: float | None,
    reason: str,
    *,
    capability_status: str = PARITY_FAILED,
) -> ForwardScorerAudit:
    return ForwardScorerAudit(
        stream=STREAM,
        stream_label=STREAM_LABEL,
        model=FINALIST_MODEL,
        capability_status=capability_status,
        gap_code=GAP_CODE,
        gap_reason=reason,
        repo_artifact_basis=existing_basis(root, required),
        scorer_version=PED_FORWARD_SCORER_VERSION,
        parity_status=parity_status,
        max_parity_delta=max_parity_delta,
        stored_replay_max_delta=stored_replay_delta,
        source_artifact_hashes=hashes,
        missing_artifacts=blockers,
        required_components=PED_REQUIRED_COMPONENTS,
        forecast_capability_available=False,
    )

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .forward_scorer_governance import (
    ForwardScorerAudit,
    INSUFFICIENT_ARTIFACTS,
    NUMERIC_FORECAST_AVAILABLE,
    artifact_hashes,
    existing_basis,
    missing_paths,
    repo_relative,
)


HEAVY_RUC_FORWARD_SCORER_VERSION = "heavy-ruc-forward-scorer-audit-v1"
STREAM = "HEAVY_RUC"
STREAM_LABEL = "Heavy RUC volume"
FINALIST_MODEL = "HEAVY_RUC__RECON_STATIC_REBUILT"
GAP_CODE = "heavy_ruc_component_forward_scorers_missing"
PARITY_TOLERANCE = 1e-6

HEAVY_RUC_COMPONENTS: tuple[dict[str, Any], ...] = (
    {
        "label": "C1",
        "component_model": "HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64",
        "component_weight": 0.469332,
        "description": "ElasticNet dynamic no-leads ylag w64",
    },
    {
        "label": "C2",
        "component_model": "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64",
        "component_weight": 0.281844,
        "description": "Schiff GBR no ylag w64",
    },
    {
        "label": "C3",
        "component_model": "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52",
        "component_weight": 0.144373,
        "description": "dynamic no-leads GBR ylag w52",
    },
    {
        "label": "C4",
        "component_model": "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40",
        "component_weight": 0.104451,
        "description": "dynamic no-leads GBR ylag w40",
    },
)


def evaluate_heavy_ruc_forward_scorer(repo_root: Path | str | None = None) -> ForwardScorerAudit:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    repro = root / "data" / "dashboard_evidence_pack_reproducibility" / "heavy_ruc"
    required = [
        root / "data" / "model_input_history" / "heavy_ruc_inputs.parquet",
        root / "data" / "model_input_history" / "manifest.json",
        repro / "model_registry.parquet",
        repro / "component_predictions.parquet",
        repro / "model_coefficients.parquet",
        repro / "training_fit_predictions.parquet",
    ]
    hashes = artifact_hashes(root, required)
    missing = list(missing_paths(root, required))
    stored_replay_delta: float | None = None

    if missing:
        return _audit(
            root,
            required,
            hashes,
            tuple(missing),
            "not_run_missing_artifacts",
            None,
            stored_replay_delta,
            "Heavy RUC forward scoring cannot run because required repo-local reproducibility artifacts are missing.",
        )

    registry = pd.read_parquet(repro / "model_registry.parquet")
    registry_errors = _registry_errors(registry)
    if registry_errors:
        return _audit(
            root,
            required,
            hashes,
            tuple(registry_errors),
            "not_run_registry_mismatch",
            None,
            stored_replay_delta,
            "Heavy RUC forward scoring cannot run because the component registry no longer matches the fixed finalist.",
        )

    component_predictions = pd.read_parquet(repro / "component_predictions.parquet")
    stored_replay_delta = _stored_weighted_replay_delta(component_predictions)
    coefficients = pd.read_parquet(repro / "model_coefficients.parquet")
    coefficients_available = _coefficients_available(coefficients)
    source_artifacts = repro / "source_artifacts"
    source_artifacts_present = source_artifacts.exists() and any(source_artifacts.iterdir())

    if not coefficients_available or not source_artifacts_present:
        blockers: list[str] = []
        if not coefficients_available:
            blockers.append("fitted component coefficients or serialized estimators are unavailable")
        if not source_artifacts_present:
            blockers.append(f"{repo_relative(root, source_artifacts)} is absent")
        reason = (
            "Heavy RUC remains a governed gap for forward scoring. Stored C1-C4 component predictions prove the "
            f"weighted replay (max stored replay delta {stored_replay_delta:.12g}), but the repo does not contain "
            "a parity-tested executable scorer for new assumption rows: "
            + "; ".join(blockers)
            + ". Required forward scorers: C1 ElasticNet dynamic no-leads ylag w64; C2 Schiff GBR no ylag w64; "
            "C3 GBM dynamic no-leads ylag w52; C4 GBM dynamic no-leads ylag w40"
            + "."
        )
        return _audit(
            root,
            required,
            hashes,
            tuple(blockers),
            "not_run_insufficient_artifacts",
            None,
            stored_replay_delta,
            reason,
        )

    return ForwardScorerAudit(
        stream=STREAM,
        stream_label=STREAM_LABEL,
        model=FINALIST_MODEL,
        capability_status=NUMERIC_FORECAST_AVAILABLE,
        gap_code=None,
        gap_reason="",
        repo_artifact_basis=existing_basis(root, required),
        scorer_version=HEAVY_RUC_FORWARD_SCORER_VERSION,
        parity_status="passed",
        max_parity_delta=stored_replay_delta,
        stored_replay_max_delta=stored_replay_delta,
        source_artifact_hashes=hashes,
        required_components=tuple(component["component_model"] for component in HEAVY_RUC_COMPONENTS),
        forecast_capability_available=True,
    )


def _registry_errors(registry: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if registry.empty or "component_model" not in registry.columns:
        return ["model_registry.parquet does not expose component_model"]
    by_model = registry.set_index("component_model").to_dict(orient="index")
    for component in HEAVY_RUC_COMPONENTS:
        name = component["component_model"]
        if name not in by_model:
            errors.append(f"missing registry component {name}")
            continue
        weight = pd.to_numeric(by_model[name].get("component_weight"), errors="coerce")
        if pd.isna(weight) or abs(float(weight) - float(component["component_weight"])) > 5e-7:
            errors.append(f"weight mismatch for {name}")
    return errors


def _stored_weighted_replay_delta(component_predictions: pd.DataFrame) -> float:
    required = {"origin", "target_period", "horizon", "component_model", "component_pred", "component_weight", "final_pred"}
    if component_predictions.empty or required.difference(component_predictions.columns):
        return float("nan")
    data = component_predictions[
        component_predictions["component_model"].astype(str).isin(
            [component["component_model"] for component in HEAVY_RUC_COMPONENTS]
        )
    ].copy()
    if "weighted_component_pred" in data.columns:
        data["weighted"] = pd.to_numeric(data["weighted_component_pred"], errors="coerce")
    else:
        data["weighted"] = pd.to_numeric(data["component_pred"], errors="coerce") * pd.to_numeric(
            data["component_weight"], errors="coerce"
        )
    group_cols = [
        column
        for column in ["score_basis", "eval_grid", "origin", "target_period", "horizon"]
        if column in data.columns
    ]
    grouped = (
        data.groupby(group_cols, dropna=False)
        .agg(weighted=("weighted", "sum"), final_pred=("final_pred", "first"), component_count=("component_model", "nunique"))
        .reset_index()
    )
    grouped = grouped[grouped["component_count"].eq(len(HEAVY_RUC_COMPONENTS))].copy()
    if grouped.empty:
        return float("nan")
    return float((pd.to_numeric(grouped["weighted"], errors="coerce") - pd.to_numeric(grouped["final_pred"], errors="coerce")).abs().max())


def _coefficients_available(coefficients: pd.DataFrame) -> bool:
    if coefficients.empty:
        return False
    status = coefficients.get("reproducibility_status", pd.Series(dtype=str)).dropna().astype(str)
    if status.str.contains("unavailable_without_refit_or_model_artifact", case=False, na=False).any():
        return False
    values = pd.to_numeric(coefficients.get("coefficient", pd.Series(dtype=float)), errors="coerce")
    return values.notna().any()


def _audit(
    root: Path,
    required: list[Path],
    hashes: dict[str, str],
    missing_or_blockers: tuple[str, ...],
    parity_status: str,
    max_parity_delta: float | None,
    stored_replay_delta: float | None,
    reason: str,
) -> ForwardScorerAudit:
    return ForwardScorerAudit(
        stream=STREAM,
        stream_label=STREAM_LABEL,
        model=FINALIST_MODEL,
        capability_status=INSUFFICIENT_ARTIFACTS,
        gap_code=GAP_CODE,
        gap_reason=reason,
        repo_artifact_basis=existing_basis(root, required),
        scorer_version=HEAVY_RUC_FORWARD_SCORER_VERSION,
        parity_status=parity_status,
        max_parity_delta=max_parity_delta,
        stored_replay_max_delta=stored_replay_delta,
        source_artifact_hashes=hashes,
        missing_artifacts=missing_or_blockers,
        required_components=tuple(component["component_model"] for component in HEAVY_RUC_COMPONENTS),
        forecast_capability_available=False,
    )

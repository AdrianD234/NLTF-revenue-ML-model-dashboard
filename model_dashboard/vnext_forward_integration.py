"""Forecast Builder integration for the vNext fixed-finalist scorers.

This adapter lets the governed Forecast Builder use the vNext production
scorers for PED and Heavy RUC when (and only when) their parity gates pass.
If the vNext reproducibility packs are absent or any gate fails, callers fall
back to the existing governed-gap behaviour. The legacy finalists and the
historical evidence pack are not modified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .forward_scorer_governance import (
    ForwardScorerAudit,
    NUMERIC_FORECAST_AVAILABLE,
    PARITY_FAILED,
)

VNEXT_INTEGRATION_VERSION = "vnext-forward-integration-v1"

_STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "HEAVY_RUC": "Heavy RUC volume",
}


def _state_dir(root: Path, stream: str) -> Path:
    return root / "data" / "dashboard_evidence_pack_reproducibility" / f"{stream.lower()}_vnext"


def vnext_pack_present(root: Path, stream: str) -> bool:
    sdir = _state_dir(root, stream)
    return (sdir / "fitted_model_manifest.json").exists() and (
        sdir / "forward_scorer_parity_audit.json").exists()


def evaluate_vnext_forward_scorer(root: Path, stream: str) -> ForwardScorerAudit | None:
    """Return a ForwardScorerAudit for the vNext scorer, or None when the
    vNext pack is not present (callers then use legacy governance)."""
    if stream not in _STREAM_LABELS or not vnext_pack_present(root, stream):
        return None
    try:
        from pipeline.vnext_forward import VNEXT_SCORER_VERSION, load_scorer
    except Exception:
        return None
    try:
        scorer = load_scorer(stream)
    except Exception:
        scorer = None
    sdir = _state_dir(root, stream)
    manifest = json.loads((sdir / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    parity = json.loads((sdir / "forward_scorer_parity_audit.json").read_text(encoding="utf-8"))
    hashes = {label: entry["sha256"] for label, entry in manifest.get("production_states", {}).items()}
    basis = "; ".join(
        f"data/dashboard_evidence_pack_reproducibility/{stream.lower()}_vnext/{name}"
        for name in ("fitted_model_manifest.json", "forward_scorer_parity_audit.json",
                     "fitted_state_index.parquet", "training_feature_matrices.parquet"))
    max_delta = max(
        float(parity.get("state_replay_max_abs_delta") or 0.0),
        float(parity.get("recipe_replay_max_abs_delta") or 0.0),
    )
    if scorer is not None and scorer.numeric_enabled:
        return ForwardScorerAudit(
            stream=stream,
            stream_label=_STREAM_LABELS[stream],
            model=manifest["finalist_model"],
            capability_status=NUMERIC_FORECAST_AVAILABLE,
            gap_code=None,
            gap_reason="",
            repo_artifact_basis=basis,
            scorer_version=VNEXT_SCORER_VERSION,
            parity_status=str(parity.get("parity_status")),
            max_parity_delta=max_delta,
            stored_replay_max_delta=float(scorer.runtime_state_gate_delta),
            source_artifact_hashes=hashes,
            required_components=tuple(m["component_model"] for m in manifest["members"]),
            forecast_capability_available=True,
        )
    return ForwardScorerAudit(
        stream=stream,
        stream_label=_STREAM_LABELS[stream],
        model=manifest["finalist_model"],
        capability_status=PARITY_FAILED,
        gap_code=f"{stream.lower()}_vnext_parity_failed",
        gap_reason=("vNext fitted state is present but the parity or runtime state gate failed; "
                    "numeric forecasts are withheld. Rerun 'python -m pipeline.vnext_run finalize'."),
        repo_artifact_basis=basis,
        scorer_version=VNEXT_SCORER_VERSION,
        parity_status=str(parity.get("parity_status")),
        max_parity_delta=max_delta,
        stored_replay_max_delta=(float(scorer.runtime_state_gate_delta) if scorer is not None else None),
        source_artifact_hashes=hashes,
        required_components=tuple(m["component_model"] for m in manifest["members"]),
        forecast_capability_available=False,
    )


def vnext_forward_forecast(validation: Any, repo_root: Path, stream: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score validated workbook assumption rows with the fixed vNext finalist.

    Returns (future_rows, component_rows) shaped for the Forecast Builder.
    Raises on any inconsistency so the caller can fall back to governed gaps.
    """
    from pipeline.vnext_core import load_stream_data, parse_period
    from pipeline.vnext_forward import REQUIRED_USER_COLUMNS, forward_forecast, load_scorer

    scorer = load_scorer(stream)
    if scorer is None or not scorer.numeric_enabled:
        raise RuntimeError(f"{stream}: vNext numeric scorer is not enabled")
    assumptions = validation.assumptions
    sub = assumptions[assumptions["stream"].astype(str).eq(stream)].copy()
    if sub.empty:
        raise ValueError(f"{stream}: no validated assumption rows")
    sub["__period__"] = sub["period"].map(parse_period)
    sub = sub.set_index("__period__").sort_index()
    missing = [c for c in REQUIRED_USER_COLUMNS[stream] if c not in sub.columns]
    if missing:
        raise ValueError(f"{stream}: validated assumptions missing columns {missing}")
    future, components, capability = forward_forecast(stream, sub, scorer)
    if not bool(capability.get("forecast_capability_available")):
        raise RuntimeError(f"{stream}: scorer reported {capability.get('capability_status')}")

    manifest = scorer.manifest
    window_starts = [entry["train_window_start"] for entry in manifest["production_states"].values()]
    window_ends = [entry["train_window_end"] for entry in manifest["production_states"].values()]
    recipe = ("vNext fixed finalist: " +
              "; ".join(f"{m['component_label']} {m['model_kind']} ({m['feature_set']}, "
                        f"w{m['window']}, ylag={m['include_target_lags']}, weight {m['component_weight']:.4f})"
                        for m in manifest["members"]))
    for frame in (future, components):
        frame["source_recipe"] = recipe
        frame["training_window_start"] = min(window_starts)
        frame["training_window_end"] = max(window_ends)
        frame["training_window_rows"] = max(int(e["train_rows"]) for e in manifest["production_states"].values())
    return future, components

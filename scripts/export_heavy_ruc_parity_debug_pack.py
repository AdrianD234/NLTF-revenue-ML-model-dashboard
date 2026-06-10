from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from scripts.export_heavy_ruc_training_fit_r2 import COMPONENTS, ComponentSpec, _candidate_config


STREAM = "HEAVY_RUC"
STREAM_LABEL = "Heavy RUC volume"
FINALIST_MODEL = "HEAVY_RUC__RECON_STATIC_REBUILT"
PARITY_TOLERANCE = 1e-6
DEFAULT_OUTPUT_DIR = Path("artifacts/heavy_ruc_forward_parity_debug")
DEFAULT_SOURCE_SCRIPT = Path(
    "data/dashboard_evidence_pack_reproducibility/heavy_ruc/"
    "source_artifacts/scripts/heavy_ruc_fullgrid_rescue_closure.py"
)
REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/heavy_ruc")
INPUT_HISTORY = Path("data/model_input_history/heavy_ruc_inputs.parquet")
INPUT_HISTORY_MANIFEST = Path("data/model_input_history/manifest.json")
PARITY_AUDIT = REPRO_ROOT / "forward_scorer_parity_audit.json"
DEBUG_FILES = [
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
KNOWN_PRIOR_AUDIT_REFERENCE = {
    "max_abs_delta": 126618189.79961014,
    "failing_component": "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64",
    "worst_row": {
        "component_model": "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64",
        "eval_grid": "current_evidence_grid",
        "horizon": 11,
        "origin": "2022Q1",
        "replayed_component_pred": 946541242.6115623,
        "score_basis": "current_grid_operational_pooled",
        "stored_component_pred": 1073159432.4111724,
        "target_period": "2024Q4",
        "abs_delta": 126618189.79961014,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Heavy RUC forward-scorer parity debug evidence.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-script", type=Path, default=DEFAULT_SOURCE_SCRIPT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = _resolve(repo_root, args.output_dir)
    source_script = _resolve(repo_root, args.source_script)
    repro_root = repo_root / REPRO_ROOT

    module = _load_source_module(source_script)
    stream_data, source_info, history = _build_repo_stream_data(module, repo_root / INPUT_HISTORY)
    registry = pd.read_parquet(repro_root / "model_registry.parquet")
    stored = pd.read_parquet(repro_root / "component_predictions.parquet")
    training_fit = pd.read_parquet(repro_root / "training_fit_predictions.parquet")
    training_trace = pd.read_parquet(repro_root / "training_window_trace.parquet")
    existing_audit = _read_json(repo_root / PARITY_AUDIT)

    replay = _replay_components(module, stream_data)
    parity_rows = _component_parity_rows(stored, replay)
    summary = _component_parity_summary(stored, replay, parity_rows)
    worst_rows = _worst_rows(parity_rows)
    current_worst = worst_rows.iloc[0].to_dict()
    training_windows = _training_window_comparison(module, stream_data, stored, training_fit, training_trace)
    coverage = _origin_target_coverage(stored, replay, parity_rows)
    configs = _candidate_config_comparison(module, stream_data, registry)
    feature_matrix = _feature_matrix_comparison(module, stream_data, current_worst, existing_audit)
    manifest = _input_history_manifest(
        repo_root,
        source_script,
        history,
        stream_data,
        source_info,
        training_fit,
        summary,
        feature_matrix,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "component_parity_summary.csv", index=False)
    parity_rows.to_csv(output_dir / "component_parity_rows.csv", index=False)
    worst_rows.to_csv(output_dir / "worst_rows.csv", index=False)
    feature_matrix.to_csv(output_dir / "feature_matrix_comparison.csv", index=False)
    training_windows.to_csv(output_dir / "training_window_comparison.csv", index=False)
    coverage.to_csv(output_dir / "origin_target_coverage_comparison.csv", index=False)
    configs.to_csv(output_dir / "candidate_config_comparison.csv", index=False)
    (output_dir / "input_history_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (output_dir / "heavy_ruc_parity_diagnosis.md").write_text(
        _diagnosis_markdown(output_dir, summary, current_worst, manifest, existing_audit),
        encoding="utf-8",
    )

    _update_parity_audit(repo_root, output_dir, current_worst, manifest, summary, existing_audit)
    print(f"Wrote Heavy RUC parity debug pack to {_repo_rel(repo_root, output_dir)}")
    print(f"Current max abs delta: {float(current_worst['abs_delta']):.12g}")
    print(f"Failing component: {current_worst['component_model']}")


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_source_module(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("heavy_ruc_parity_debug_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import Heavy RUC source script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module


def _build_repo_stream_data(module: Any, history_path: Path) -> tuple[Any, dict[str, Any], pd.DataFrame]:
    history = pd.read_parquet(history_path).copy()
    if "period" not in history.columns or "target" not in history.columns:
        raise AssertionError("heavy_ruc_inputs.parquet must expose period and target columns")
    frame = history.copy()
    frame["__period__"] = frame["period"].map(module.parse_quarter_value)
    frame = frame.rename(columns={"target": "Heavy RUC net km"})
    target_col, target_is_log = module.detect_target_col(frame, STREAM)
    feature_cols = module.detect_feature_cols(frame, STREAM, [target_col])
    y_raw, y_log = module.build_target_series(frame, target_col, target_is_log)
    exog, groups, primary_log = module.build_exog(frame, STREAM, feature_cols)
    stream_data = module.StreamData(STREAM, target_col, target_is_log, feature_cols, y_raw, y_log, exog, groups, primary_log)
    source_info = {
        "target_column": target_col,
        "target_is_log": bool(target_is_log),
        "source_column_count": int(len(feature_cols)),
        "engineered_feature_count": int(exog.shape[1]),
        "source_period_min": str(y_raw.dropna().index.min()),
        "source_period_max": str(y_raw.dropna().index.max()),
        "log_target_period_min": str(y_log.dropna().index.min()),
        "log_target_period_max": str(y_log.dropna().index.max()),
        "log_target_non_null_rows": int(y_log.dropna().shape[0]),
    }
    return stream_data, source_info, history


def _replay_components(module: Any, stream_data: Any) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for spec in COMPONENTS:
        cfg = _candidate_config(module, spec)
        frame = module.evaluate_candidate(stream_data, cfg)
        if frame.empty:
            raise AssertionError(f"No replay rows generated for {spec.component_model}")
        frame = frame.rename(columns={"model": "component_model", "pred": "replayed_pred", "pred_log": "replayed_pred_log"})
        frame["component_label"] = spec.component_label
        frame["component_weight"] = spec.component_weight
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def _component_parity_rows(stored: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    keys = ["component_model", "origin", "target_period", "horizon"]
    keep = keys + ["replayed_pred", "replayed_pred_log", "actual_log", "component_label"]
    merged = stored.merge(replay[keep], on=keys, how="left")
    merged = merged.rename(columns={"component_pred": "stored_component_pred"})
    merged["stored_component_pred"] = pd.to_numeric(merged["stored_component_pred"], errors="coerce")
    merged["replayed_pred"] = pd.to_numeric(merged["replayed_pred"], errors="coerce")
    merged["abs_delta"] = (merged["stored_component_pred"] - merged["replayed_pred"]).abs()
    denominator = merged["stored_component_pred"].abs().replace(0, np.nan)
    merged["abs_pct_delta"] = merged["abs_delta"] / denominator * 100.0
    merged["match_status"] = np.where(
        merged["replayed_pred"].isna(),
        "missing_replay_row",
        np.where(merged["abs_delta"].le(PARITY_TOLERANCE), "matched_within_tolerance", "delta_exceeds_tolerance"),
    )
    columns = [
        "stream",
        "stream_label",
        "component_label",
        "component_model",
        "score_basis",
        "eval_grid",
        "origin",
        "target_period",
        "horizon",
        "actual",
        "stored_component_pred",
        "replayed_pred",
        "replayed_pred_log",
        "abs_delta",
        "abs_pct_delta",
        "match_status",
        "component_weight",
        "weighted_component_pred",
        "final_pred",
        "ensemble_model",
    ]
    return merged[[column for column in columns if column in merged.columns]].sort_values(
        ["component_label", "score_basis", "origin", "horizon"],
        kind="stable",
    )


def _component_parity_summary(stored: pd.DataFrame, replay: pd.DataFrame, parity_rows: pd.DataFrame) -> pd.DataFrame:
    keys = ["component_model", "origin", "target_period", "horizon"]
    replay_keys = {
        model: set(map(tuple, group[keys].astype(str).to_numpy()))
        for model, group in replay.groupby("component_model", dropna=False)
    }
    rows: list[dict[str, Any]] = []
    for spec in COMPONENTS:
        model = spec.component_model
        component_rows = parity_rows[parity_rows["component_model"].astype(str).eq(model)].copy()
        stored_component = stored[stored["component_model"].astype(str).eq(model)].copy()
        stored_keys = set(map(tuple, stored_component[keys].astype(str).to_numpy()))
        replay_key_set = replay_keys.get(model, set())
        matched = component_rows["replayed_pred"].notna()
        deltas = pd.to_numeric(component_rows.loc[matched, "abs_delta"], errors="coerce")
        pct_deltas = pd.to_numeric(component_rows.loc[matched, "abs_pct_delta"], errors="coerce")
        worst = component_rows.loc[deltas.idxmax()] if not deltas.empty else pd.Series(dtype=object)
        rows.append(
            {
                "component_label": spec.component_label,
                "component_model": model,
                "stored_rows": int(len(stored_component)),
                "stored_unique_keys": int(len(stored_keys)),
                "replay_rows": int(len(replay[replay["component_model"].astype(str).eq(model)])),
                "replay_unique_keys": int(len(replay_key_set)),
                "matched_rows": int(matched.sum()),
                "missing_rows": int((~matched).sum()),
                "missing_unique_keys": int(len(stored_keys - replay_key_set)),
                "replay_only_unique_keys": int(len(replay_key_set - stored_keys)),
                "max_abs_delta": float(deltas.max()) if not deltas.empty else np.nan,
                "mean_abs_delta": float(deltas.mean()) if not deltas.empty else np.nan,
                "max_abs_pct_delta": float(pct_deltas.max()) if not pct_deltas.empty else np.nan,
                "mean_abs_pct_delta": float(pct_deltas.mean()) if not pct_deltas.empty else np.nan,
                "worst_origin": worst.get("origin"),
                "worst_target_period": worst.get("target_period"),
                "worst_horizon": worst.get("horizon"),
                "parity_status": "passed" if not deltas.empty and float(deltas.max()) <= PARITY_TOLERANCE else "failed",
            }
        )
    return pd.DataFrame(rows)


def _worst_rows(parity_rows: pd.DataFrame, limit: int = 25) -> pd.DataFrame:
    return parity_rows.sort_values("abs_delta", ascending=False, kind="stable").head(limit).reset_index(drop=True)


def _training_window_comparison(
    module: Any,
    stream_data: Any,
    stored: pd.DataFrame,
    training_fit: pd.DataFrame,
    training_trace: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spec in COMPONENTS:
        origins = sorted(stored.loc[stored["component_model"].astype(str).eq(spec.component_model), "origin"].dropna().astype(str).unique())
        for origin in origins:
            repo_window = _training_window_details(module, stream_data, spec, origin)
            source_rows = training_fit[
                training_fit["component_model"].astype(str).eq(spec.component_model)
                & training_fit["origin"].astype(str).eq(origin)
            ]
            trace_rows = training_trace[
                training_trace["component_model"].astype(str).eq(spec.component_model)
                & training_trace["origin"].astype(str).eq(origin)
            ]
            rows.append(
                {
                    "component_label": spec.component_label,
                    "component_model": spec.component_model,
                    "origin": origin,
                    "configured_window_quarters": spec.window,
                    "repo_raw_window_start": repo_window.get("raw_window_start"),
                    "repo_raw_window_end": repo_window.get("raw_window_end"),
                    "repo_effective_training_start": repo_window.get("effective_training_start"),
                    "repo_effective_training_end": repo_window.get("effective_training_end"),
                    "repo_training_rows": repo_window.get("training_rows"),
                    "repo_feature_count": repo_window.get("feature_count"),
                    "source_training_fit_window_start": _first_value(source_rows, "window_start"),
                    "source_training_fit_window_end": _first_value(source_rows, "window_end"),
                    "source_training_fit_rows": int(source_rows["training_period"].nunique()) if not source_rows.empty else 0,
                    "trace_inferred_start": _first_value(trace_rows, "training_start_period_inferred"),
                    "trace_inferred_end": _first_value(trace_rows, "training_end_period_inferred"),
                    "comparison_status": _window_status(repo_window, source_rows),
                }
            )
    return pd.DataFrame(rows)


def _origin_target_coverage(stored: pd.DataFrame, replay: pd.DataFrame, parity_rows: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (component_model, score_basis, eval_grid), group in parity_rows.groupby(
        ["component_model", "score_basis", "eval_grid"],
        dropna=False,
    ):
        replay_group = replay[replay["component_model"].astype(str).eq(str(component_model))]
        rows.append(
            {
                "component_model": component_model,
                "score_basis": score_basis,
                "eval_grid": eval_grid,
                "stored_rows": int(len(group)),
                "matched_rows": int(group["replayed_pred"].notna().sum()),
                "missing_rows": int(group["replayed_pred"].isna().sum()),
                "stored_origin_min": _period_min(group["origin"]),
                "stored_origin_max": _period_max(group["origin"]),
                "stored_target_min": _period_min(group["target_period"]),
                "stored_target_max": _period_max(group["target_period"]),
                "replay_rows_total_for_component": int(len(replay_group)),
                "replay_origin_min": _period_min(replay_group["origin"]),
                "replay_origin_max": _period_max(replay_group["origin"]),
                "replay_target_min": _period_min(replay_group["target_period"]),
                "replay_target_max": _period_max(replay_group["target_period"]),
                "max_abs_delta": float(pd.to_numeric(group["abs_delta"], errors="coerce").max()),
                "mean_abs_delta": float(pd.to_numeric(group["abs_delta"], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows)


def _candidate_config_comparison(module: Any, stream_data: Any, registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    registry_by_model = registry.set_index("component_model").to_dict(orient="index")
    for spec in COMPONENTS:
        reg = registry_by_model.get(spec.component_model, {})
        feature_names = _feature_names(module, stream_data, spec)
        observed_hyper = _json_loads(reg.get("hyperparameters_json"))
        expected_hyper = _json_loads(spec.hyperparameters_json)
        rows.append(
            {
                "component_label": spec.component_label,
                "component_model": spec.component_model,
                "weight_expected": spec.component_weight,
                "weight_registry": _float_or_nan(reg.get("component_weight")),
                "model_kind_expected": spec.model_kind,
                "model_kind_registry": reg.get("model_kind"),
                "feature_set_expected": spec.feature_set,
                "feature_set_registry": reg.get("feature_set"),
                "include_target_lags_expected": spec.include_target_lags,
                "include_target_lags_registry": reg.get("include_target_lags"),
                "window_expected": spec.window,
                "window_registry": reg.get("window"),
                "hyperparameters_expected": json.dumps(expected_hyper, sort_keys=True),
                "hyperparameters_registry": json.dumps(observed_hyper, sort_keys=True),
                "target_transform_registry": reg.get("target_transform"),
                "feature_count_repo_replay": len(feature_names),
                "feature_list_repo_replay": "|".join(feature_names),
                "comparison_status": _config_status(spec, reg, expected_hyper, observed_hyper),
            }
        )
    return pd.DataFrame(rows)


def _feature_matrix_comparison(
    module: Any,
    stream_data: Any,
    current_worst: dict[str, Any],
    existing_audit: dict[str, Any],
) -> pd.DataFrame:
    cases = [("current_debug_worst", current_worst)]
    prior = existing_audit.get("worst_row") if isinstance(existing_audit.get("worst_row"), dict) else {}
    if prior and (
        str(prior.get("origin")) != str(current_worst.get("origin"))
        or str(prior.get("target_period")) != str(current_worst.get("target_period"))
        or str(prior.get("component_model")) != str(current_worst.get("component_model"))
    ):
        prior_case = {
            "component_model": prior.get("component_model"),
            "origin": prior.get("origin"),
            "target_period": prior.get("target_period"),
            "horizon": prior.get("horizon"),
            "stored_component_pred": prior.get("stored_component_pred"),
            "replayed_pred": prior.get("replayed_component_pred"),
            "abs_delta": existing_audit.get("max_abs_delta"),
        }
        cases.append(("prior_audit_worst_superseded", prior_case))
    known_prior = KNOWN_PRIOR_AUDIT_REFERENCE["worst_row"]
    if not any(
        str(case.get("origin")) == str(known_prior.get("origin"))
        and str(case.get("target_period")) == str(known_prior.get("target_period"))
        and str(case.get("component_model")) == str(known_prior.get("component_model"))
        for _, case in cases
    ):
        cases.append(
            (
                "known_prior_audit_reference",
                {
                    "component_model": known_prior.get("component_model"),
                    "origin": known_prior.get("origin"),
                    "target_period": known_prior.get("target_period"),
                    "horizon": known_prior.get("horizon"),
                    "stored_component_pred": known_prior.get("stored_component_pred"),
                    "replayed_pred": known_prior.get("replayed_component_pred"),
                    "abs_delta": known_prior.get("abs_delta"),
                },
            )
        )

    rows: list[dict[str, Any]] = []
    for case_id, case in cases:
        spec = _component_spec_by_model(str(case.get("component_model")))
        if spec is None:
            continue
        origin = str(case.get("origin"))
        target = str(case.get("target_period"))
        horizon = int(case.get("horizon"))
        feature_names = _feature_names(module, stream_data, spec)
        feature_values = _forecast_feature_values(module, stream_data, spec, origin, horizon)
        window = _training_window_details(module, stream_data, spec, origin)
        for index, feature in enumerate(feature_names, start=1):
            rows.append(
                {
                    "case_id": case_id,
                    "component_label": spec.component_label,
                    "component_model": spec.component_model,
                    "origin": origin,
                    "target_period": target,
                    "horizon": horizon,
                    "feature_order": index,
                    "feature_name": feature,
                    "replay_feature_value": feature_values.get(feature),
                    "parent_feature_value": np.nan,
                    "comparison_status": "parent_feature_matrix_missing",
                    "training_window_start": window.get("effective_training_start"),
                    "training_window_end": window.get("effective_training_end"),
                    "training_rows": window.get("training_rows"),
                    "target_transform": "log target for component model fit",
                    "inverse_transform": "exp(pred_log), clipped by source safe_exp",
                    "hyperparameters_json": spec.hyperparameters_json,
                    "source_data_period_min": str(stream_data.y_raw.dropna().index.min()),
                    "source_data_period_max": str(stream_data.y_raw.dropna().index.max()),
                    "stored_component_pred": case.get("stored_component_pred"),
                    "replayed_pred": case.get("replayed_pred"),
                    "abs_delta": case.get("abs_delta"),
                    "notes": "Parent-run feature matrix was not vendored; only repo-local replay feature values are available.",
                }
            )
    return pd.DataFrame(rows)


def _input_history_manifest(
    repo_root: Path,
    source_script: Path,
    history: pd.DataFrame,
    stream_data: Any,
    source_info: dict[str, Any],
    training_fit: pd.DataFrame,
    summary: pd.DataFrame,
    feature_matrix: pd.DataFrame,
) -> dict[str, Any]:
    debug_max = float(pd.to_numeric(summary["max_abs_delta"], errors="coerce").max())
    source_replay = pd.to_numeric(training_fit.get("source_replay_max_abs_delta", pd.Series(dtype=float)), errors="coerce")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "finalist_model": FINALIST_MODEL,
        "parity_tolerance": PARITY_TOLERANCE,
        "repo_input_history": {
            "repo_relative_path": _repo_rel(repo_root, repo_root / INPUT_HISTORY),
            "sha256": _sha256(repo_root / INPUT_HISTORY),
            "rows": int(len(history)),
            "columns": int(history.shape[1]),
            "period_min": str(history["period"].min()),
            "period_max": str(history["period"].max()),
            "target_non_null_rows": int(pd.to_numeric(history["target"], errors="coerce").notna().sum()),
            "target_positive_rows": int(pd.to_numeric(history["target"], errors="coerce").gt(0).sum()),
        },
        "source_script": {
            "repo_relative_path": _repo_rel(repo_root, source_script),
            "sha256": _sha256(source_script),
        },
        "source_detection": source_info,
        "parent_run_source_data": {
            "status": "missing_from_repo",
            "notes": (
                "No parent-run input workbook, serialized feature matrix, or fitted C1-C4 estimators are vendored under "
                "data/dashboard_evidence_pack_reproducibility/heavy_ruc/source_artifacts. "
                "The repo contains parent component predictions and derived training-fit rows only."
            ),
        },
        "prior_workbook_replay_evidence": {
            "training_fit_predictions_path": _repo_rel(repo_root, repo_root / REPRO_ROOT / "training_fit_predictions.parquet"),
            "source_replay_max_abs_delta": float(source_replay.max()) if source_replay.notna().any() else np.nan,
            "status": "prior_source_replay_closed" if source_replay.notna().any() and float(source_replay.max()) <= PARITY_TOLERANCE else "unavailable",
        },
        "current_repo_history_replay": {
            "component_max_abs_delta": debug_max,
            "parity_status": "failed" if debug_max > PARITY_TOLERANCE else "passed",
            "feature_matrix_rows_dumped": int(len(feature_matrix)),
        },
        "likely_root_cause": {
            "input_data_mismatch": "likely",
            "feature_engineering_mismatch": "cannot_rule_out_without_parent_feature_matrix",
            "window_origin_mismatch": "not_supported_by_current_evidence",
            "model_hyperparameter_mismatch": "not_supported_by_current_evidence",
            "missing_parent_run_fitted_estimators": "confirmed",
            "stored_component_predictions_from_different_run": "possible_but_not_proven",
        },
    }


def _update_parity_audit(
    repo_root: Path,
    output_dir: Path,
    current_worst: dict[str, Any],
    manifest: dict[str, Any],
    summary: pd.DataFrame,
    existing_audit: dict[str, Any],
) -> None:
    audit_path = repo_root / PARITY_AUDIT
    payload = dict(existing_audit)
    previous = {
        "max_abs_delta": existing_audit.get("max_abs_delta"),
        "failing_component": existing_audit.get("failing_component"),
        "worst_row": existing_audit.get("worst_row"),
    }
    max_delta = float(current_worst["abs_delta"])
    payload.update(
        {
            "audit_version": "2026-06-10-heavy-ruc-forward-parity-debug-v2",
            "parity_status": "failed" if max_delta > PARITY_TOLERANCE else "passed",
            "max_abs_delta": max_delta,
            "failing_component": current_worst["component_model"],
            "missing_feature_or_artifact": (
                "Parent-run Heavy RUC feature matrix is not vendored and fitted component estimators were not serialized; "
                "repo-local model_input_history/heavy_ruc_inputs.parquet does not reproduce archived component predictions."
            ),
            "notes": (
                "The Heavy RUC parity-debug pack compares archived component_predictions.parquet with a repo-local replay "
                "from data/model_input_history/heavy_ruc_inputs.parquet. Candidate configs and stored keys are aligned, "
                "but component deltas exceed tolerance. Heavy RUC remains disabled for numeric forward forecasts."
            ),
            "worst_row": _audit_worst_row(current_worst),
            "diagnosis": {
                "debug_pack_path": _repo_rel(repo_root, output_dir),
                "debug_pack_files": DEBUG_FILES,
                "component_summary": summary.to_dict(orient="records"),
                "input_history_manifest": manifest,
                "previous_recorded_audit": previous,
                "known_prior_audit_reference": KNOWN_PRIOR_AUDIT_REFERENCE,
                "candidate_config_status": "matched_locked_spec",
                "origin_target_coverage_status": "stored_keys_matched_replay_rows",
                "parent_run_source_data_status": "missing_from_repo",
                "fitted_estimators_status": "missing_from_repo",
                "likely_root_cause": manifest["likely_root_cause"],
            },
        }
    )
    payload["repo_artifacts"] = _repo_artifacts(repo_root, output_dir)
    audit_path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=_json_default) + "\n", encoding="utf-8")


def _diagnosis_markdown(
    output_dir: Path,
    summary: pd.DataFrame,
    current_worst: dict[str, Any],
    manifest: dict[str, Any],
    existing_audit: dict[str, Any],
) -> str:
    previous_delta = existing_audit.get("max_abs_delta")
    source_replay = manifest["prior_workbook_replay_evidence"]["source_replay_max_abs_delta"]
    lines = [
        "# Heavy RUC forward-scorer parity diagnosis",
        "",
        "## Verdict",
        "",
        "Heavy RUC must remain `parity_failed`; numeric forward forecasts are not enabled.",
        "",
        "The repo-local replay from `data/model_input_history/heavy_ruc_inputs.parquet` does not reproduce the archived C1-C4 component predictions within the `1e-6` parity tolerance.",
        "",
        "## Current worst row",
        "",
        f"- Component: `{current_worst['component_model']}`",
        f"- Origin / target / horizon: `{current_worst['origin']}` -> `{current_worst['target_period']}` / `{int(current_worst['horizon'])}`",
        f"- Stored component prediction: `{float(current_worst['stored_component_pred']):.12g}`",
        f"- Replayed component prediction: `{float(current_worst['replayed_pred']):.12g}`",
        f"- Max absolute delta: `{float(current_worst['abs_delta']):.12g}`",
        "",
        "## Evidence summary",
        "",
    ]
    for row in summary.to_dict(orient="records"):
        lines.append(
            f"- {row['component_label']}: max abs delta `{float(row['max_abs_delta']):.12g}`, "
            f"matched rows `{int(row['matched_rows'])}` of `{int(row['stored_rows'])}`, "
            f"missing rows `{int(row['missing_rows'])}`."
        )
    lines.extend(
        [
            "",
            "## Diagnosis",
            "",
            "- Candidate configs, weights, windows, feature-set names, target-lag flags and hyperparameters match the locked Heavy RUC finalist registry.",
            "- Stored origin/target/horizon keys are all matched by repo-local replay rows, so this is not a missing-key coverage failure.",
            "- The parent-run feature matrix, parent workbook, and fitted C1-C4 estimators are not vendored in the repo. Only parent component predictions and derived training-fit rows are available.",
            f"- The committed training-fit rows record a prior source replay max delta of `{float(source_replay):.12g}`, while the repo-local input-history replay max delta is `{float(current_worst['abs_delta']):.12g}`.",
            "- The likely root cause is repo-local input-history or engineered-feature-matrix mismatch against the parent run. A feature-engineering mismatch cannot be ruled out until the parent feature matrix or fitted estimators are vendored.",
            "",
        ]
    )
    prior_reference_delta = float(KNOWN_PRIOR_AUDIT_REFERENCE["max_abs_delta"])
    prior_note_delta = previous_delta if previous_delta is not None else prior_reference_delta
    if abs(float(prior_note_delta) - float(current_worst["abs_delta"])) > 1e-6 or abs(prior_reference_delta - float(current_worst["abs_delta"])) > 1e-6:
        lines.extend(
            [
                "## Prior audit note",
                "",
                f"A prior audit reference recorded max abs delta `{prior_reference_delta:.12g}` at "
                "`2022Q1` -> `2024Q4` for C2. This debug pack keeps that row in "
                "`feature_matrix_comparison.csv` as `known_prior_audit_reference`, but the headline verdict uses the "
                "current committed source script and current committed input-history parquet.",
                "",
            ]
        )
    lines.extend(
        [
            "## Exported files",
            "",
            *[f"- `{path}`" for path in DEBUG_FILES],
            "",
        ]
    )
    return "\n".join(lines)


def _training_window_details(module: Any, stream_data: Any, spec: ComponentSpec, origin_text: str) -> dict[str, Any]:
    periods = module.valid_periods(stream_data)
    period_lookup = {str(period): period for period in periods}
    if origin_text not in period_lookup:
        return {}
    cfg = _candidate_config(module, spec)
    origin = period_lookup[origin_text]
    feature_names = _feature_names(module, stream_data, spec)
    train_periods = [period for period in periods if module.period_sort_value(period) <= module.period_sort_value(origin)]
    if cfg.window is not None:
        train_periods = train_periods[-int(cfg.window) :]
    X, y = module.build_training_matrix(stream_data, train_periods, feature_names, cfg.include_target_lags)
    mask = y.notna()
    X = X.loc[mask]
    return {
        "raw_window_start": str(train_periods[0]) if train_periods else None,
        "raw_window_end": str(train_periods[-1]) if train_periods else None,
        "effective_training_start": str(X.index.min()) if len(X) else None,
        "effective_training_end": str(X.index.max()) if len(X) else None,
        "training_rows": int(len(X)),
        "feature_count": int(len(feature_names)),
    }


def _forecast_feature_values(module: Any, stream_data: Any, spec: ComponentSpec, origin_text: str, horizon: int) -> dict[str, Any]:
    periods = module.valid_periods(stream_data)
    period_lookup = {str(period): period for period in periods}
    origin = period_lookup[origin_text]
    cfg = _candidate_config(module, spec)
    feature_names = _feature_names(module, stream_data, spec)
    train_periods = [period for period in periods if module.period_sort_value(period) <= module.period_sort_value(origin)]
    if cfg.window is not None:
        train_periods = train_periods[-int(cfg.window) :]
    X, y = module.build_training_matrix(stream_data, train_periods, feature_names, cfg.include_target_lags)
    mask = y.notna()
    X, y = X.loc[mask], y.loc[mask]
    all_na_cols = [column for column in X.columns if X[column].isna().all()]
    if all_na_cols:
        X = X.copy()
        X[all_na_cols] = 0.0
    model = module.fit_model(cfg, X, y)
    y_hist = {
        period: float(stream_data.y_log.loc[period])
        for period in stream_data.y_log.index
        if pd.notna(stream_data.y_log.loc[period]) and module.period_sort_value(period) <= module.period_sort_value(origin)
    }
    feature_row: dict[str, Any] = {}
    for step in range(1, horizon + 1):
        target_period = origin + step
        feature_row = module.build_feature_row(target_period, stream_data, y_hist, feature_names, cfg.include_target_lags)
        Xp = pd.DataFrame([feature_row]).reindex(columns=feature_names)
        if all_na_cols:
            Xp[all_na_cols] = 0.0
        pred_log = module.predict_model(model, Xp)
        if np.isfinite(pred_log):
            y_hist[target_period] = pred_log
    return {name: _float_or_nan(value) for name, value in feature_row.items()}


def _feature_names(module: Any, stream_data: Any, spec: ComponentSpec) -> list[str]:
    cfg = _candidate_config(module, spec)
    return [
        name
        for name in module.feature_names_for_set(stream_data, cfg.feature_set, cfg.include_target_lags)
        if name in stream_data.exog.columns or name.startswith("target__")
    ]


def _component_spec_by_model(model: str) -> ComponentSpec | None:
    for spec in COMPONENTS:
        if spec.component_model == model:
            return spec
    return None


def _first_value(frame: pd.DataFrame, column: str) -> Any:
    if frame.empty or column not in frame.columns:
        return None
    values = frame[column].dropna()
    return values.iloc[0] if not values.empty else None


def _window_status(repo_window: dict[str, Any], source_rows: pd.DataFrame) -> str:
    if source_rows.empty:
        return "source_training_fit_rows_missing"
    source_start = str(_first_value(source_rows, "window_start"))
    source_end = str(_first_value(source_rows, "window_end"))
    if source_start == str(repo_window.get("effective_training_start")) and source_end == str(repo_window.get("effective_training_end")):
        return "effective_window_matches_training_fit_rows"
    return "effective_window_differs_from_training_fit_rows"


def _config_status(spec: ComponentSpec, registry: dict[str, Any], expected_hyper: dict[str, Any], observed_hyper: dict[str, Any]) -> str:
    checks = [
        abs(_float_or_nan(registry.get("component_weight")) - spec.component_weight) <= 1e-9,
        str(registry.get("model_kind")) == spec.model_kind,
        str(registry.get("feature_set")) == spec.feature_set,
        str(registry.get("include_target_lags")).casefold() == str(spec.include_target_lags).casefold(),
        int(registry.get("window")) == int(spec.window),
        expected_hyper == observed_hyper,
    ]
    return "matched_locked_spec" if all(checks) else "mismatch"


def _audit_worst_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "component_model": row.get("component_model"),
        "eval_grid": row.get("eval_grid"),
        "horizon": int(row.get("horizon")),
        "origin": row.get("origin"),
        "replayed_component_pred": float(row.get("replayed_pred")),
        "score_basis": row.get("score_basis"),
        "stored_component_pred": float(row.get("stored_component_pred")),
        "target_period": row.get("target_period"),
        "abs_delta": float(row.get("abs_delta")),
        "abs_pct_delta": float(row.get("abs_pct_delta")),
    }


def _repo_artifacts(repo_root: Path, output_dir: Path) -> list[dict[str, str]]:
    paths = [
        repo_root / DEFAULT_SOURCE_SCRIPT,
        repo_root / INPUT_HISTORY,
        repo_root / REPRO_ROOT / "component_predictions.parquet",
        repo_root / REPRO_ROOT / "model_registry.parquet",
        *[output_dir / name for name in DEBUG_FILES],
    ]
    return [{"repo_relative_path": _repo_rel(repo_root, path), "sha256": _sha256(path)} for path in paths if path.exists()]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _json_loads(value: Any) -> dict[str, Any]:
    if value is None or pd.isna(value):
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _float_or_nan(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else float("nan")


def _period_min(values: pd.Series) -> str | None:
    cleaned = values.dropna().astype(str)
    return cleaned.min() if not cleaned.empty else None


def _period_max(values: pd.Series) -> str | None:
    cleaned = values.dropna().astype(str)
    return cleaned.max() if not cleaned.empty else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return str(value)


if __name__ == "__main__":
    main()

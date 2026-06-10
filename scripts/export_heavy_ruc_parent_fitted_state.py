from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
import zipfile

import joblib
import numpy as np
import pandas as pd

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from scripts.export_heavy_ruc_training_fit_r2 import COMPONENTS, ComponentSpec, _candidate_config, _load_source_module
from scripts.rebuild_heavy_ruc_canonical_history import (
    PARITY_TOLERANCE,
    _build_workbook_stream_data,
    _json_default,
    _read_json,
    _repo_rel,
    _resolve_workbook,
    _sha256,
)


STREAM = "HEAVY_RUC"
STREAM_LABEL = "Heavy RUC volume"
FINALIST_MODEL = "HEAVY_RUC__RECON_STATIC_REBUILT"
REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/heavy_ruc")
SOURCE_SCRIPT = REPRO_ROOT / "source_artifacts/scripts/heavy_ruc_fullgrid_rescue_closure.py"
PARITY_AUDIT = REPRO_ROOT / "forward_scorer_parity_audit.json"
STATE_MANIFEST = REPRO_ROOT / "forward_state_manifest.json"
STATE_DIR = REPRO_ROOT / "forward_state"
FEATURE_MATRIX_DIR = REPRO_ROOT / "forward_feature_matrices"
DEBUG_DIR = Path("artifacts/heavy_ruc_forward_parity_debug")
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
RECURSION_POLICIES = {
    "recursive_predicted": "Source-code policy: seed y_hist with actuals through origin, then write each finite horizon prediction back before scoring later horizons.",
    "actual_after_each_step": "Counterfactual policy: after each horizon, write the target period actual into y_hist.",
    "actual_all_available": "Counterfactual policy: seed y_hist with all actuals, including future validation periods.",
    "stored_component_after_each_step": "Counterfactual policy: after each horizon, write archived parent component prediction into y_hist.",
    "no_update": "Counterfactual policy: seed y_hist with actuals through origin and never update during the forecast path.",
}
STATE_AUDIT_VERSION = "2026-06-10-heavy-ruc-parent-fitted-state-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Heavy RUC locked-component fitted-state and target-lag parity audits.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-script", type=Path, default=SOURCE_SCRIPT)
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--skip-joblib", action="store_true", help="Export matrix/audit artifacts without serializing fitted estimators.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    repro_root = repo_root / REPRO_ROOT
    source_script = _resolve(repo_root, args.source_script)
    workbook = _resolve_workbook(repo_root, args.workbook, repro_root)
    state_dir = repo_root / STATE_DIR
    matrix_dir = repo_root / FEATURE_MATRIX_DIR
    debug_dir = repo_root / DEBUG_DIR

    _prepare_output_dir(state_dir, suffixes={".joblib"})
    _prepare_output_dir(matrix_dir, suffixes={".parquet"})
    debug_dir.mkdir(parents=True, exist_ok=True)

    module = _load_source_module(source_script)
    raw_workbook = module.load_input_sheet(workbook)
    stream_data, source_info = _build_workbook_stream_data(module, raw_workbook)
    stored = pd.read_parquet(repro_root / "component_predictions.parquet")
    registry = pd.read_parquet(repro_root / "model_registry.parquet")
    existing_audit = _read_json(repo_root / PARITY_AUDIT)

    export = _export_locked_component_state(
        module=module,
        stream_data=stream_data,
        stored=stored,
        repo_root=repo_root,
        state_dir=state_dir,
        matrix_dir=matrix_dir,
        skip_joblib=args.skip_joblib,
    )
    recursion_audit = _target_lag_recursion_audit(module, stream_data, stored)
    fitted_state_audit = _c3_c4_fitted_state_audit(export["prediction_replay_rows"], recursion_audit, stored)

    training_matrix_path = matrix_dir / "training_feature_matrix.parquet"
    prediction_matrix_path = matrix_dir / "prediction_feature_rows.parquet"
    target_lag_path = matrix_dir / "target_lag_state.parquet"
    column_order_path = matrix_dir / "feature_column_order.parquet"
    export["training_feature_matrix"].to_parquet(training_matrix_path, index=False)
    export["prediction_feature_rows"].to_parquet(prediction_matrix_path, index=False)
    export["target_lag_state"].to_parquet(target_lag_path, index=False)
    export["feature_column_order"].to_parquet(column_order_path, index=False)

    recursion_path = debug_dir / "target_lag_recursion_audit.csv"
    fitted_state_path = debug_dir / "c3_c4_fitted_state_audit.csv"
    recursion_audit.to_csv(recursion_path, index=False)
    fitted_state_audit.to_csv(fitted_state_path, index=False)

    manifest = _manifest(
        repo_root=repo_root,
        workbook=workbook,
        source_script=source_script,
        source_info=source_info,
        registry=registry,
        export=export,
        recursion_audit=recursion_audit,
        fitted_state_audit=fitted_state_audit,
        artifact_paths=[
            training_matrix_path,
            prediction_matrix_path,
            target_lag_path,
            column_order_path,
            recursion_path,
            fitted_state_path,
            *export["state_paths"],
        ],
    )
    manifest_path = repo_root / STATE_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(_json_sanitize(manifest), indent=2, sort_keys=False, default=_json_default, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    _update_parity_audit(repo_root, existing_audit, manifest, export["component_parity"], fitted_state_audit)
    _update_diagnosis(debug_dir, manifest, recursion_audit, fitted_state_audit)

    print(f"Wrote Heavy RUC forward state manifest to {_repo_rel(repo_root, manifest_path)}")
    print(f"Serialized state files: {len(export['state_paths'])}")
    print(f"Component/final parity status: {manifest['parity']['overall_status']}")
    print(f"Capability decision: {manifest['capability_decision']}")


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _prepare_output_dir(path: Path, *, suffixes: set[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file() and child.suffix.lower() in suffixes:
            child.unlink()


def _export_locked_component_state(
    *,
    module: Any,
    stream_data: Any,
    stored: pd.DataFrame,
    repo_root: Path,
    state_dir: Path,
    matrix_dir: Path,
    skip_joblib: bool,
) -> dict[str, Any]:
    periods = module.valid_periods(stream_data)
    period_lookup = {str(period): period for period in periods}
    stored_lookup = _stored_lookup(stored)
    origins_by_component = _origins_by_component(stored)

    state_records: list[dict[str, Any]] = []
    training_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    target_lag_rows: list[dict[str, Any]] = []
    feature_order_rows: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []
    state_paths: list[Path] = []

    for spec in COMPONENTS:
        cfg = _candidate_config(module, spec)
        feature_names = _feature_names(module, stream_data, spec)
        if not feature_names:
            raise AssertionError(f"No feature columns resolved for {spec.component_model}")
        feature_order_rows.extend(_feature_order_rows(spec, feature_names))
        component_origins = sorted(
            origins_by_component.get(spec.component_model, set()),
            key=lambda text: module.period_sort_value(period_lookup[text]),
        )
        for origin_text in component_origins:
            origin = period_lookup[origin_text]
            state = _fit_origin_state(module, stream_data, spec, feature_names, origin, periods)
            if state is None:
                state_records.append(_state_record(repo_root, spec, origin_text, None, "fit_failed_or_insufficient_rows", ""))
                continue

            X = state["X"]
            y = state["y"]
            model = state["model"]
            all_na_cols = state["all_na_cols"]
            train_periods = state["train_periods"]
            y_hist = state["y_hist"]
            window_start = str(X.index.min()) if len(X) else None
            window_end = str(X.index.max()) if len(X) else None

            for period, row in X.iterrows():
                training_rows.append(
                    {
                        **_base_row(spec, origin_text),
                        "training_period": str(period),
                        "window_start": window_start,
                        "window_end": window_end,
                        "training_rows": int(len(X)),
                        "feature_column_order_json": json.dumps(feature_names),
                        "actual_log": float(y.loc[period]),
                        "actual": float(stream_data.y_raw.loc[period]),
                        "sample_role": "training",
                        **{name: _float_or_nan(row.get(name)) for name in feature_names},
                    }
                )

            state_path: Path | None = None
            state_status = "joblib_skipped_by_flag"
            state_note = "Use --skip-joblib false to serialize source-refit estimators."
            if not skip_joblib:
                state_path, state_status, state_note = _dump_state(
                    repo_root,
                    state_dir,
                    spec,
                    origin_text,
                    model,
                    feature_names,
                    all_na_cols,
                    train_periods,
                    window_start,
                    window_end,
                )
                if state_path is not None:
                    state_paths.append(state_path)
            state_records.append(_state_record(repo_root, spec, origin_text, state_path, state_status, state_note))

            running_hist = dict(y_hist)
            for horizon in range(1, int(module.MAX_HORIZON) + 1):
                target_period = origin + horizon
                if str(target_period) not in set(stored_lookup.get(spec.component_model, {}).get(origin_text, {})):
                    continue
                raw_feature_row = module.build_feature_row(target_period, stream_data, running_hist, feature_names, cfg.include_target_lags)
                Xp = pd.DataFrame([raw_feature_row]).reindex(columns=feature_names)
                if all_na_cols:
                    Xp.loc[:, all_na_cols] = 0.0
                try:
                    pred_log = module.predict_model(model, Xp)
                except Exception:
                    pred_log = np.nan
                pred = module.safe_exp(pred_log)
                stored_row = stored_lookup[spec.component_model][origin_text][str(target_period)]
                replay_rows.append(
                    {
                        **_base_row(spec, origin_text),
                        "target_period": str(target_period),
                        "horizon": horizon,
                        "stored_component_pred": stored_row["component_pred"],
                        "replayed_component_pred": pred,
                        "replayed_pred_log": pred_log,
                        "abs_delta": _abs_delta(stored_row["component_pred"], pred),
                        "actual": stored_row["actual"],
                        "final_pred": stored_row["final_pred"],
                    }
                )
                prediction_rows.append(
                    {
                        **_base_row(spec, origin_text),
                        "target_period": str(target_period),
                        "horizon": horizon,
                        "window_start": window_start,
                        "window_end": window_end,
                        "training_rows": int(len(X)),
                        "feature_column_order_json": json.dumps(feature_names),
                        "target_lag_policy": "recursive_predicted_lags" if cfg.include_target_lags else "not_applicable_no_target_lags",
                        "stored_component_pred": stored_row["component_pred"],
                        "replayed_component_pred": pred,
                        "abs_delta": _abs_delta(stored_row["component_pred"], pred),
                        "sample_role": "forecast_validation",
                        **{name: _float_or_nan(Xp.iloc[0].get(name)) for name in feature_names},
                    }
                )
                target_lag_rows.extend(_target_lag_rows(module, spec, origin, target_period, horizon, running_hist, feature_names))
                if np.isfinite(pred_log):
                    running_hist[target_period] = float(pred_log)

    replay = pd.DataFrame(replay_rows)
    component_parity = _component_and_final_parity(stored, replay)
    return {
        "state_records": state_records,
        "state_paths": state_paths,
        "training_feature_matrix": pd.DataFrame(training_rows),
        "prediction_feature_rows": pd.DataFrame(prediction_rows),
        "target_lag_state": pd.DataFrame(target_lag_rows),
        "feature_column_order": pd.DataFrame(feature_order_rows),
        "prediction_replay_rows": replay,
        "component_parity": component_parity,
    }


def _feature_names(module: Any, stream_data: Any, spec: ComponentSpec) -> list[str]:
    cfg = _candidate_config(module, spec)
    return [
        name
        for name in module.feature_names_for_set(stream_data, cfg.feature_set, cfg.include_target_lags)
        if name in stream_data.exog.columns or name.startswith("target__")
    ]


def _fit_origin_state(
    module: Any,
    stream_data: Any,
    spec: ComponentSpec,
    feature_names: list[str],
    origin: pd.Period,
    periods: list[pd.Period],
) -> dict[str, Any] | None:
    cfg = _candidate_config(module, spec)
    train_periods = [period for period in periods if module.period_sort_value(period) <= module.period_sort_value(origin)]
    if cfg.window is not None:
        train_periods = train_periods[-int(cfg.window) :]
    if len(train_periods) < cfg.min_train_quarters:
        return None
    X, y = module.build_training_matrix(stream_data, train_periods, feature_names, cfg.include_target_lags)
    mask = y.notna()
    X, y = X.loc[mask], y.loc[mask]
    if len(X) < max(20, int(cfg.min_train_quarters * 0.60)):
        return None
    all_na_cols = [column for column in X.columns if X[column].isna().all()]
    if all_na_cols:
        X = X.copy()
        X.loc[:, all_na_cols] = 0.0
    model = module.fit_model(cfg, X, y)
    y_hist = {
        period: float(stream_data.y_log.loc[period])
        for period in stream_data.y_log.index
        if pd.notna(stream_data.y_log.loc[period]) and module.period_sort_value(period) <= module.period_sort_value(origin)
    }
    return {
        "X": X,
        "y": y,
        "model": model,
        "all_na_cols": all_na_cols,
        "train_periods": train_periods,
        "y_hist": y_hist,
    }


def _dump_state(
    repo_root: Path,
    state_dir: Path,
    spec: ComponentSpec,
    origin_text: str,
    model: Any,
    feature_names: list[str],
    all_na_cols: list[str],
    train_periods: list[pd.Period],
    window_start: str | None,
    window_end: str | None,
) -> tuple[Path | None, str, str]:
    filename = f"{spec.component_label}_{origin_text.replace('Q', 'q')}.joblib"
    path = state_dir / filename
    payload = {
        "artifact_role": "source_refit_locked_component_estimator",
        "component_label": spec.component_label,
        "component_model": spec.component_model,
        "component_weight": spec.component_weight,
        "origin": origin_text,
        "model": model,
        "feature_names": feature_names,
        "all_na_columns_zero_filled": all_na_cols,
        "train_periods": [str(period) for period in train_periods],
        "window_start": window_start,
        "window_end": window_end,
        "target_transform": "log target for fit; level prediction via exp(pred_log)",
        "target_lag_policy": "recursive_predicted_lags" if spec.include_target_lags else "not_applicable_no_target_lags",
    }
    try:
        joblib.dump(payload, path, compress=3)
    except Exception as exc:
        if path.exists():
            path.unlink()
        return None, "joblib_serialization_failed", f"{type(exc).__name__}: {exc}"
    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        path.unlink()
        return None, "joblib_removed_exceeds_50mb", f"serialized file was {size} bytes"
    return path, "joblib_serialized_source_refit_state", "This is a deterministic source-code refit state, not the missing parent-run fitted estimator."


def _state_record(
    repo_root: Path,
    spec: ComponentSpec,
    origin_text: str,
    state_path: Path | None,
    status: str,
    notes: str,
) -> dict[str, Any]:
    size = state_path.stat().st_size if state_path is not None and state_path.exists() else 0
    return {
        "component_label": spec.component_label,
        "component_model": spec.component_model,
        "origin": origin_text,
        "repo_relative_path": _repo_rel(repo_root, state_path) if state_path is not None else "",
        "size_bytes": int(size),
        "sha256": _sha256(state_path) if state_path is not None and state_path.exists() else "",
        "status": status,
        "artifact_role": "source_refit_locked_component_estimator",
        "required_for_replay": True,
        "notes": notes,
    }


def _base_row(spec: ComponentSpec, origin_text: str) -> dict[str, Any]:
    return {
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "model": FINALIST_MODEL,
        "component_label": spec.component_label,
        "component_model": spec.component_model,
        "component_weight": spec.component_weight,
        "origin": origin_text,
        "model_kind": spec.model_kind,
        "feature_set": spec.feature_set,
        "include_target_lags": bool(spec.include_target_lags),
        "window": int(spec.window),
    }


def _feature_order_rows(spec: ComponentSpec, feature_names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "component_label": spec.component_label,
            "component_model": spec.component_model,
            "feature_order": index,
            "feature_name": name,
            "is_target_lag_feature": name.startswith("target__"),
            "target_lag_policy": "recursive_predicted_lags" if spec.include_target_lags else "not_applicable_no_target_lags",
        }
        for index, name in enumerate(feature_names, start=1)
    ]


def _target_lag_rows(
    module: Any,
    spec: ComponentSpec,
    origin: pd.Period,
    target_period: pd.Period,
    horizon: int,
    y_hist: dict[pd.Period, float],
    feature_names: list[str],
) -> list[dict[str, Any]]:
    if not spec.include_target_lags:
        return []
    lag_map = {
        "target__lag1": [target_period - 1],
        "target__lag2": [target_period - 2],
        "target__lag4": [target_period - 4],
        "target__diff1": [target_period - 1, target_period - 2],
        "target__diff4": [target_period - 1, target_period - 5],
        "target__roll4_mean": [target_period - i for i in range(1, 5)],
        "target__roll8_mean": [target_period - i for i in range(1, 9)],
    }
    feature_values = module.target_lag_features(target_period, y_hist)
    rows: list[dict[str, Any]] = []
    for feature_name, source_periods in lag_map.items():
        if feature_name not in feature_names:
            continue
        rows.append(
            {
                **_base_row(spec, str(origin)),
                "target_period": str(target_period),
                "horizon": horizon,
                "feature_name": feature_name,
                "feature_value": _float_or_nan(feature_values.get(feature_name)),
                "source_periods_json": json.dumps([str(period) for period in source_periods]),
                "source_roles_json": json.dumps([_lag_source_role(period, origin) for period in source_periods]),
                "target_lag_policy": "recursive_predicted_lags",
            }
        )
    return rows


def _lag_source_role(period: pd.Period, origin: pd.Period) -> str:
    if period <= origin:
        return "actual_history_through_origin"
    return "recursive_predicted_validation_horizon"


def _target_lag_recursion_audit(module: Any, stream_data: Any, stored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spec in [component for component in COMPONENTS if component.component_label in {"C3", "C4"}]:
        stored_component = stored[stored["component_model"].astype(str).eq(spec.component_model)].copy()
        for policy in RECURSION_POLICIES:
            replay = _replay_component_with_policy(module, stream_data, stored, spec, policy)
            if replay.empty:
                continue
            expanded = _component_parity_rows(stored_component, replay)
            deltas = pd.to_numeric(expanded["abs_delta"], errors="coerce")
            worst = expanded.loc[deltas.idxmax()].to_dict()
            h1 = expanded[expanded["horizon"].eq(1)]
            h2 = expanded[expanded["horizon"].eq(2)]
            h3 = expanded[expanded["horizon"].eq(3)]
            rows.append(
                {
                    "component_label": spec.component_label,
                    "component_model": spec.component_model,
                    "recursion_policy": policy,
                    "policy_description": RECURSION_POLICIES[policy],
                    "rows": int(len(expanded)),
                    "max_abs_delta": float(deltas.max()),
                    "mean_abs_delta": float(deltas.mean()),
                    "horizon_1_max_abs_delta": _max_delta(h1),
                    "horizon_2_max_abs_delta": _max_delta(h2),
                    "horizon_3_max_abs_delta": _max_delta(h3),
                    "worst_origin": worst.get("origin"),
                    "worst_target_period": worst.get("target_period"),
                    "worst_horizon": worst.get("horizon"),
                    "parity_tolerance": PARITY_TOLERANCE,
                    "parity_status": "passed" if float(deltas.max()) <= PARITY_TOLERANCE else "failed",
                    "interpretation": _recursion_interpretation(policy),
                }
            )
    return pd.DataFrame(rows)


def _replay_component_with_policy(
    module: Any,
    stream_data: Any,
    stored: pd.DataFrame,
    spec: ComponentSpec,
    policy: str,
) -> pd.DataFrame:
    periods = module.valid_periods(stream_data)
    period_lookup = {str(period): period for period in periods}
    stored_lookup = _stored_lookup(stored).get(spec.component_model, {})
    cfg = _candidate_config(module, spec)
    feature_names = _feature_names(module, stream_data, spec)
    records: list[dict[str, Any]] = []

    for origin_text in sorted(stored_lookup, key=lambda text: module.period_sort_value(period_lookup[text])):
        origin = period_lookup[origin_text]
        state = _fit_origin_state(module, stream_data, spec, feature_names, origin, periods)
        if state is None:
            continue
        if policy == "actual_all_available":
            y_hist = {
                period: float(stream_data.y_log.loc[period])
                for period in stream_data.y_log.index
                if pd.notna(stream_data.y_log.loc[period])
            }
        else:
            y_hist = dict(state["y_hist"])
        all_na_cols = state["all_na_cols"]
        model = state["model"]

        for horizon in range(1, int(module.MAX_HORIZON) + 1):
            target_period = origin + horizon
            stored_row = stored_lookup[origin_text].get(str(target_period))
            if stored_row is None:
                continue
            feature_row = module.build_feature_row(target_period, stream_data, y_hist, feature_names, cfg.include_target_lags)
            Xp = pd.DataFrame([feature_row]).reindex(columns=feature_names)
            if all_na_cols:
                Xp.loc[:, all_na_cols] = 0.0
            try:
                pred_log = module.predict_model(model, Xp)
            except Exception:
                pred_log = np.nan
            pred = module.safe_exp(pred_log)
            records.append(
                {
                    "component_label": spec.component_label,
                    "component_model": spec.component_model,
                    "origin": origin_text,
                    "target_period": str(target_period),
                    "horizon": horizon,
                    "stored_component_pred": stored_row["component_pred"],
                    "replayed_component_pred": pred,
                    "abs_delta": _abs_delta(stored_row["component_pred"], pred),
                }
            )
            if policy == "recursive_predicted" and np.isfinite(pred_log):
                y_hist[target_period] = float(pred_log)
            elif policy == "actual_after_each_step" and target_period in stream_data.y_log.index and pd.notna(stream_data.y_log.loc[target_period]):
                y_hist[target_period] = float(stream_data.y_log.loc[target_period])
            elif policy == "stored_component_after_each_step" and pd.notna(stored_row["component_pred"]) and float(stored_row["component_pred"]) > 0:
                y_hist[target_period] = float(np.log(float(stored_row["component_pred"])))
            elif policy == "no_update":
                continue
    return pd.DataFrame(records)


def _recursion_interpretation(policy: str) -> str:
    if policy == "recursive_predicted":
        return (
            "Closest executable source-code replay. Remaining non-zero deltas, including horizon-1, indicate fitted-state "
            "or runtime drift beyond target-lag recursion choice."
        )
    return "Counterfactual recursion policy; larger deltas reject this as the parent implementation."


def _c3_c4_fitted_state_audit(recursion_replay: pd.DataFrame, recursion_audit: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    source = _component_parity_rows(stored, recursion_replay)
    source = source[source["component_label"].isin(["C3", "C4"])].copy()
    for spec in [component for component in COMPONENTS if component.component_label in {"C3", "C4"}]:
        component = source[source["component_model"].eq(spec.component_model)]
        if component.empty:
            continue
        deltas = pd.to_numeric(component["abs_delta"], errors="coerce")
        h1 = component[component["horizon"].eq(1)]
        worst = component.loc[deltas.idxmax()].to_dict()
        policy_rows = recursion_audit[recursion_audit["component_model"].eq(spec.component_model)].copy()
        best = policy_rows.sort_values("max_abs_delta", kind="stable").iloc[0].to_dict() if not policy_rows.empty else {}
        rows.append(
            {
                "row_type": "component",
                "component_label": spec.component_label,
                "component_model": spec.component_model,
                "source_refit_rows": int(len(component)),
                "source_refit_max_abs_delta": float(deltas.max()),
                "source_refit_mean_abs_delta": float(deltas.mean()),
                "source_refit_horizon_1_max_abs_delta": _max_delta(h1),
                "worst_origin": worst.get("origin"),
                "worst_target_period": worst.get("target_period"),
                "worst_horizon": worst.get("horizon"),
                "best_recursion_policy": best.get("recursion_policy"),
                "best_recursion_policy_max_abs_delta": best.get("max_abs_delta"),
                "parity_tolerance": PARITY_TOLERANCE,
                "parity_status": "passed" if float(deltas.max()) <= PARITY_TOLERANCE else "failed",
                "fitted_state_status": "source_refit_exported_parent_fitted_state_missing",
                "target_lag_policy": "recursive_predicted_lags",
                "interpretation": (
                    "The source code uses recursive predicted target lags. Horizon-1 deltas remain non-zero, so the "
                    "residual gap cannot be solved by lag recursion choice alone; parent fitted estimators or parent "
                    "feature matrices are still missing."
                ),
            }
        )
    rows.append(_final_weighted_audit_row(stored, recursion_replay))
    return pd.DataFrame(rows)


def _final_weighted_audit_row(stored: pd.DataFrame, recursion_replay: pd.DataFrame) -> dict[str, Any]:
    grouped = _final_weighted_rows(stored, recursion_replay)
    if grouped.empty:
        return {
            "row_type": "final_weighted",
            "component_label": "C1_C4_weighted",
            "component_model": FINALIST_MODEL,
            "parity_status": "failed",
            "fitted_state_status": "source_refit_exported_parent_fitted_state_missing",
            "target_lag_policy": "mixed_recursive_predicted_lags",
        }
    deltas = pd.to_numeric(grouped["abs_delta"], errors="coerce")
    worst = grouped.loc[deltas.idxmax()].to_dict() if not deltas.empty else {}
    return {
        "row_type": "final_weighted",
        "component_label": "C1_C4_weighted",
        "component_model": FINALIST_MODEL,
        "source_refit_rows": int(len(grouped)),
        "source_refit_max_abs_delta": float(deltas.max()) if not deltas.empty else np.nan,
        "source_refit_mean_abs_delta": float(deltas.mean()) if not deltas.empty else np.nan,
        "source_refit_horizon_1_max_abs_delta": _max_delta(grouped[grouped["horizon"].eq(1)]) if "horizon" in grouped.columns else np.nan,
        "worst_origin": worst.get("origin"),
        "worst_target_period": worst.get("target_period"),
        "worst_horizon": worst.get("horizon"),
        "best_recursion_policy": "recursive_predicted",
        "best_recursion_policy_max_abs_delta": np.nan,
        "parity_tolerance": PARITY_TOLERANCE,
        "parity_status": "passed" if not deltas.empty and float(deltas.max()) <= PARITY_TOLERANCE else "failed",
        "fitted_state_status": "source_refit_exported_parent_fitted_state_missing",
        "target_lag_policy": "mixed_recursive_predicted_lags",
        "interpretation": "Final weighted replay remains disabled unless all C1-C4 component replays and the weighted final replay pass.",
    }


def _component_and_final_parity(stored: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    component_rows = _component_parity_rows(stored, replay)
    for spec in COMPONENTS:
        component = component_rows[component_rows["component_model"].eq(spec.component_model)].copy()
        deltas = pd.to_numeric(component["abs_delta"], errors="coerce")
        worst = component.loc[deltas.idxmax()].to_dict() if not deltas.empty else {}
        matched = component["replayed_component_pred"].notna() if "replayed_component_pred" in component.columns else pd.Series(False, index=component.index)
        rows.append(
            {
                "row_type": "component",
                "component_label": spec.component_label,
                "component_model": spec.component_model,
                "matched_rows": int(matched.sum()),
                "stored_rows": int(len(component)),
                "missing_rows": int((~matched).sum()),
                "max_abs_delta": float(deltas.max()) if not deltas.empty else np.nan,
                "mean_abs_delta": float(deltas.mean()) if not deltas.empty else np.nan,
                "worst_origin": worst.get("origin"),
                "worst_target_period": worst.get("target_period"),
                "worst_horizon": worst.get("horizon"),
                "parity_status": "passed" if not deltas.empty and float(deltas.max()) <= PARITY_TOLERANCE else "failed",
            }
        )
    final = _final_weighted_audit_row(stored, replay)
    rows.append(
        {
            "row_type": "final_weighted",
            "component_label": "C1_C4_weighted",
            "component_model": FINALIST_MODEL,
            "matched_rows": final.get("source_refit_rows"),
            "stored_rows": final.get("source_refit_rows"),
            "missing_rows": 0,
            "max_abs_delta": final.get("source_refit_max_abs_delta"),
            "mean_abs_delta": final.get("source_refit_mean_abs_delta"),
            "worst_origin": final.get("worst_origin"),
            "worst_target_period": final.get("worst_target_period"),
            "worst_horizon": final.get("worst_horizon"),
            "parity_status": final.get("parity_status"),
        }
    )
    return pd.DataFrame(rows)


def _component_parity_rows(stored: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    if stored.empty or replay.empty:
        return pd.DataFrame()
    keys = ["component_model", "origin", "target_period", "horizon"]
    replay_cols = [column for column in [*keys, "replayed_component_pred", "replayed_pred_log"] if column in replay.columns]
    replay_unique = replay[replay_cols].drop_duplicates(subset=keys, keep="last")
    merged = stored.merge(replay_unique, on=keys, how="left")
    labels = {spec.component_model: spec.component_label for spec in COMPONENTS}
    if "component_label" not in merged.columns:
        merged["component_label"] = merged["component_model"].map(labels)
    merged["component_pred"] = pd.to_numeric(merged["component_pred"], errors="coerce")
    merged["replayed_component_pred"] = pd.to_numeric(merged["replayed_component_pred"], errors="coerce")
    merged["abs_delta"] = (merged["component_pred"] - merged["replayed_component_pred"]).abs()
    return merged


def _final_weighted_rows(stored: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    parity_rows = _component_parity_rows(stored, replay)
    if parity_rows.empty:
        return pd.DataFrame()
    parity_rows["weighted_replayed"] = pd.to_numeric(parity_rows["replayed_component_pred"], errors="coerce") * pd.to_numeric(
        parity_rows["component_weight"],
        errors="coerce",
    )
    group_cols = [column for column in ["score_basis", "eval_grid", "origin", "target_period", "horizon"] if column in parity_rows.columns]
    grouped = (
        parity_rows.groupby(group_cols, dropna=False)
        .agg(
            replayed_final_pred=("weighted_replayed", "sum"),
            final_pred=("final_pred", "first"),
            component_count=("component_model", "nunique"),
            missing_components=("replayed_component_pred", lambda values: int(pd.isna(values).sum())),
        )
        .reset_index()
    )
    grouped = grouped[grouped["component_count"].eq(len(COMPONENTS))].copy()
    grouped["abs_delta"] = (pd.to_numeric(grouped["final_pred"], errors="coerce") - grouped["replayed_final_pred"]).abs()
    return grouped


def _manifest(
    *,
    repo_root: Path,
    workbook: Path,
    source_script: Path,
    source_info: dict[str, Any],
    registry: pd.DataFrame,
    export: dict[str, Any],
    recursion_audit: pd.DataFrame,
    fitted_state_audit: pd.DataFrame,
    artifact_paths: list[Path],
) -> dict[str, Any]:
    component_parity = export["component_parity"]
    max_delta = float(pd.to_numeric(component_parity["max_abs_delta"], errors="coerce").max())
    overall_passed = bool(component_parity["parity_status"].eq("passed").all() and max_delta <= PARITY_TOLERANCE)
    failing = component_parity.sort_values("max_abs_delta", ascending=False, kind="stable").iloc[0].to_dict()
    artifact_records = _artifact_records(repo_root, artifact_paths)
    oversized = [record for record in artifact_records if int(record["size_bytes"]) > MAX_ARTIFACT_BYTES]
    source_refit_states = export["state_records"]
    parent_search = _parent_run_search(repo_root, registry)
    return {
        "audit_name": "heavy_ruc_forward_parent_fitted_state_recovery",
        "audit_version": STATE_AUDIT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "finalist_model": FINALIST_MODEL,
        "parity_tolerance": PARITY_TOLERANCE,
        "source_script": {
            "repo_relative_path": _repo_rel(repo_root, source_script),
            "sha256": _sha256(source_script),
        },
        "source_script_workbook_history": {
            "workbook_basename": workbook.name,
            "workbook_size_bytes": workbook.stat().st_size,
            "workbook_sha256": _sha256(workbook),
            **source_info,
        },
        "locked_components": [
            {
                "component_label": spec.component_label,
                "component_model": spec.component_model,
                "component_weight": spec.component_weight,
                "model_kind": spec.model_kind,
                "feature_set": spec.feature_set,
                "include_target_lags": spec.include_target_lags,
                "window": spec.window,
                "hyperparameters_json": spec.hyperparameters_json,
            }
            for spec in COMPONENTS
        ],
        "parent_run_search": parent_search,
        "state_export": {
            "state_status": "source_refit_state_exported_parent_state_not_found",
            "state_file_count": int(sum(1 for record in source_refit_states if record["repo_relative_path"])),
            "state_files": source_refit_states,
            "training_feature_matrix": "data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_feature_matrices/training_feature_matrix.parquet",
            "prediction_feature_rows": "data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_feature_matrices/prediction_feature_rows.parquet",
            "target_lag_state": "data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_feature_matrices/target_lag_state.parquet",
            "feature_column_order": "data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_feature_matrices/feature_column_order.parquet",
            "artifact_records": artifact_records,
            "oversized_artifacts": oversized,
        },
        "target_lag_recursion": {
            "documented_policy": "recursive_predicted_lags",
            "source_code_evidence": (
                "heavy_ruc_fullgrid_rescue_closure.evaluate_candidate seeds y_hist with actual log targets through "
                "origin and writes finite pred_log values into y_hist after each forecast horizon."
            ),
            "audit_csv": "artifacts/heavy_ruc_forward_parity_debug/target_lag_recursion_audit.csv",
            "summary": recursion_audit.to_dict(orient="records"),
        },
        "fitted_state_audit": {
            "audit_csv": "artifacts/heavy_ruc_forward_parity_debug/c3_c4_fitted_state_audit.csv",
            "summary": fitted_state_audit.to_dict(orient="records"),
        },
        "parity": {
            "overall_status": "passed" if overall_passed else "failed",
            "component_and_final_summary": component_parity.to_dict(orient="records"),
            "max_abs_delta": max_delta,
            "failing_component": failing.get("component_model"),
            "failing_component_label": failing.get("component_label"),
            "worst_origin": failing.get("worst_origin"),
            "worst_target_period": failing.get("worst_target_period"),
            "worst_horizon": failing.get("worst_horizon"),
        },
        "capability_decision": "numeric_forecast_available" if overall_passed else "keep_parity_failed",
        "governance_gap": (
            "Parent run did not retain fitted C1-C4 estimators or parent feature matrices. Source-refit state and "
            "feature matrices are exported, but C3/C4 and final weighted replay still exceed 1e-6 parity tolerance."
        ),
    }


def _artifact_records(repo_root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    records = []
    for path in sorted({p for p in paths if p is not None and p.exists()}, key=lambda item: _repo_rel(repo_root, item)):
        records.append(
            {
                "repo_relative_path": _repo_rel(repo_root, path),
                "size_bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
                "status": "present",
            }
        )
    return records


def _parent_run_search(repo_root: Path, registry: pd.DataFrame) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for column in ["source_parent_run", "source_workbook"]:
        if column in registry.columns:
            candidates.extend(Path(value) for value in registry[column].dropna().astype(str).unique())
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        candidates.extend(downloads.glob("*heavy*ruc*"))
    candidates.extend((repo_root / "data/dashboard_evidence_pack_reproducibility/heavy_ruc/source_artifacts").rglob("*"))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists() or candidate.is_dir():
            status = "directory_found_no_parent_fitted_state_scan" if candidate.exists() else "not_found"
            rows.append(
                {
                    "artifact_basename": candidate.name,
                    "artifact_role": _artifact_role(candidate),
                    "source_stage": "parent_run_search",
                    "size_bytes": 0,
                    "sha256": "",
                    "status": status,
                    "notes": "Local path intentionally omitted from public manifest.",
                }
            )
            continue
        rows.append(_parent_artifact_record(candidate))
    return rows


def _parent_artifact_record(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    notes = "No serialized C1-C4 fitted estimator or parent feature matrix artifact was found in this source."
    state_like_entries: list[str] = []
    if path.suffix.lower() == ".zip" and size <= MAX_ARTIFACT_BYTES:
        try:
            with zipfile.ZipFile(path) as archive:
                names = [info.filename for info in archive.infolist()]
            state_like_entries = [
                name
                for name in names
                if Path(name).suffix.lower() in {".joblib", ".pkl", ".pickle", ".parquet"}
                and any(token in name.lower() for token in ["state", "fitted", "feature_matrix", "matrix", "component"])
            ][:20]
            if state_like_entries:
                notes = "Potential state-like entries found in zip, but no parent fitted C1-C4 estimator bundle was identifiable."
        except Exception as exc:
            notes = f"Zip inspection failed: {type(exc).__name__}: {exc}"
    return {
        "artifact_basename": path.name,
        "artifact_role": _artifact_role(path),
        "source_stage": "parent_run_search",
        "size_bytes": int(size),
        "sha256": _sha256(path) if size <= MAX_ARTIFACT_BYTES else "",
        "status": _parent_artifact_status(path, state_like_entries),
        "state_like_entries": state_like_entries,
        "notes": notes,
    }


def _artifact_role(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".zip":
        return "parent_run_zip_or_handoff"
    if suffix == ".py":
        return "source_script"
    if suffix in {".xlsx", ".xls"}:
        return "source_workbook"
    if "source_artifacts" in str(path).replace("\\", "/"):
        return "repo_vendored_source_artifact"
    if path.is_dir():
        return "local_parent_run_folder"
    return "local_candidate_artifact"


def _parent_artifact_status(path: Path, state_like_entries: list[str] | None = None) -> str:
    name = path.name.lower()
    if state_like_entries:
        return "found_state_like_entries_not_parent_fitted_c1_c4_bundle"
    if path.suffix.lower() == ".zip" and "fullgrid_rescue_closure" in name:
        return "found_parent_run_zip_predictions_only_no_fitted_state"
    if path.suffix.lower() == ".py":
        return "found_source_script"
    return "found_no_parent_fitted_state"


def _update_parity_audit(
    repo_root: Path,
    existing_audit: dict[str, Any],
    manifest: dict[str, Any],
    component_parity: pd.DataFrame,
    fitted_state_audit: pd.DataFrame,
) -> None:
    audit_path = repo_root / PARITY_AUDIT
    payload = dict(existing_audit)
    failing = component_parity.sort_values("max_abs_delta", ascending=False, kind="stable").iloc[0].to_dict()
    max_delta = float(pd.to_numeric(component_parity["max_abs_delta"], errors="coerce").max())
    passed = manifest["parity"]["overall_status"] == "passed"
    payload.update(
        {
            "audit_name": "heavy_ruc_forward_parent_fitted_state_recovery",
            "audit_version": STATE_AUDIT_VERSION,
            "parity_status": "passed" if passed else "failed",
            "parity_tolerance": PARITY_TOLERANCE,
            "data_scope": "canonical_source_script_history_component_replay_with_source_refit_state_export",
            "max_abs_delta": max_delta,
            "failing_component": None if passed else failing.get("component_model"),
            "missing_feature_or_artifact": (
                "Source-script Stage 1 workbook history was recovered and deterministic source-refit state was exported. "
                "The target-lagged GBM components C3/C4 still exceed parity tolerance; parent fitted component estimators "
                "or parent feature matrices were not retained, and horizon-1 deltas show the residual gap is not "
                "only recursive target-lag handling."
            ),
            "notes": (
                "Heavy RUC remains disabled for numeric forward forecasts until C1-C4 component replay and final "
                "weighted replay all pass the fixed 1e-6 tolerance. The exported state is source-refit provenance, "
                "not proven parent-run fitted state."
            ),
            "worst_row": {
                "component_model": failing.get("component_model"),
                "component_label": failing.get("component_label"),
                "origin": failing.get("worst_origin"),
                "target_period": failing.get("worst_target_period"),
                "horizon": int(failing.get("worst_horizon")) if pd.notna(failing.get("worst_horizon")) else None,
                "abs_delta": max_delta,
                "history_candidate": "source_script_stage1_workbook_history",
            },
        }
    )
    payload["diagnosis"] = {
        **payload.get("diagnosis", {}),
        "forward_state_manifest": "data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_state_manifest.json",
        "target_lag_recursion_audit": "artifacts/heavy_ruc_forward_parity_debug/target_lag_recursion_audit.csv",
        "c3_c4_fitted_state_audit": "artifacts/heavy_ruc_forward_parity_debug/c3_c4_fitted_state_audit.csv",
        "target_lag_policy": "recursive_predicted_lags",
        "source_refit_state_status": "exported_parent_fitted_state_missing",
        "fitted_state_audit_summary": fitted_state_audit.to_dict(orient="records"),
        "forward_state_manifest_summary": {
            "audit_version": manifest["audit_version"],
            "state_file_count": manifest["state_export"]["state_file_count"],
            "parity": manifest["parity"],
            "capability_decision": manifest["capability_decision"],
        },
        "capability_decision": manifest["capability_decision"],
    }
    artifact_paths = [
        repo_root / STATE_MANIFEST,
        repo_root / DEBUG_DIR / "target_lag_recursion_audit.csv",
        repo_root / DEBUG_DIR / "c3_c4_fitted_state_audit.csv",
    ]
    payload["repo_artifacts"] = _merge_repo_artifacts(payload.get("repo_artifacts", []), repo_root, artifact_paths)
    audit_path.write_text(
        json.dumps(_json_sanitize(payload), indent=2, sort_keys=False, default=_json_default, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _merge_repo_artifacts(existing: Any, repo_root: Path, paths: list[Path]) -> list[dict[str, str]]:
    rows = list(existing) if isinstance(existing, list) else []
    by_path = {str(row.get("repo_relative_path")): row for row in rows if isinstance(row, dict)}
    for path in paths:
        if path.exists():
            rel = _repo_rel(repo_root, path)
            by_path[rel] = {"repo_relative_path": rel, "sha256": _sha256(path)}
    return list(by_path.values())


def _update_diagnosis(debug_dir: Path, manifest: dict[str, Any], recursion_audit: pd.DataFrame, fitted_state_audit: pd.DataFrame) -> None:
    path = debug_dir / "heavy_ruc_parity_diagnosis.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Heavy RUC forward-scorer parity diagnosis\n"
    marker = "## Target-lag recursion and fitted-state audit"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    recursive = recursion_audit[recursion_audit["recursion_policy"].eq("recursive_predicted")]
    lines = [
        "",
        marker,
        "",
        "The source-code replay for C3/C4 uses recursive predicted target lags: `y_hist` starts with actual log targets through the origin, then each finite horizon `pred_log` is written back before later horizons are scored.",
        "",
        "### Recursion policy results",
        "",
    ]
    for row in recursion_audit.sort_values(["component_label", "max_abs_delta"], kind="stable").to_dict(orient="records"):
        lines.append(
            f"- {row['component_label']} `{row['recursion_policy']}`: `{row['parity_status']}`, max abs delta `{float(row['max_abs_delta']):.12g}`, horizon-1 max `{float(row['horizon_1_max_abs_delta']):.12g}`."
        )
    lines.extend(
        [
            "",
            "### Fitted-state conclusion",
            "",
        ]
    )
    for row in fitted_state_audit.to_dict(orient="records"):
        if row.get("row_type") != "component":
            continue
        lines.append(
            f"- {row['component_label']}: source-refit state exported, but replay remains `{row['parity_status']}` with max abs delta `{float(row['source_refit_max_abs_delta']):.12g}` and horizon-1 max `{float(row['source_refit_horizon_1_max_abs_delta']):.12g}`."
        )
    final_rows = fitted_state_audit[fitted_state_audit["row_type"].eq("final_weighted")]
    if not final_rows.empty:
        row = final_rows.iloc[0]
        lines.append(
            f"- Final weighted C1-C4 replay remains `{row['parity_status']}` with max abs delta `{float(row['source_refit_max_abs_delta']):.12g}`."
        )
    lines.extend(
        [
            "",
            "### Governance decision",
            "",
            f"- Forward-state manifest: `data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_state_manifest.json`.",
            "- Prediction and training feature matrices are exported under `data/dashboard_evidence_pack_reproducibility/heavy_ruc/forward_feature_matrices/`.",
            "- Serialized `.joblib` files are source-refit estimator states. They are not labelled as parent fitted estimators because parent run fitted state was not retained.",
            f"- Heavy capability decision remains `{manifest['capability_decision']}`.",
            "- Heavy numeric forecasts must stay disabled unless all C1-C4 component rows and the final weighted replay pass `<=1e-6`.",
            "",
        ]
    )
    path.write_text(existing.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")


def _stored_lookup(stored: pd.DataFrame) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    result: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    ordered = stored.sort_values(["component_model", "origin", "target_period", "horizon"], kind="stable")
    for _, row in ordered.iterrows():
        component = str(row["component_model"])
        origin = str(row["origin"])
        target = str(row["target_period"])
        result.setdefault(component, {}).setdefault(origin, {})[target] = row.to_dict()
    return result


def _origins_by_component(stored: pd.DataFrame) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for component_model, group in stored.groupby("component_model", dropna=False):
        result[str(component_model)] = set(group["origin"].dropna().astype(str))
    return result


def _max_delta(frame: pd.DataFrame) -> float:
    if frame.empty or "abs_delta" not in frame.columns:
        return float("nan")
    values = pd.to_numeric(frame["abs_delta"], errors="coerce")
    return float(values.max()) if values.notna().any() else float("nan")


def _abs_delta(left: Any, right: Any) -> float:
    left_num = pd.to_numeric(left, errors="coerce")
    right_num = pd.to_numeric(right, errors="coerce")
    if pd.isna(left_num) or pd.isna(right_num):
        return float("nan")
    return float(abs(float(left_num) - float(right_num)))


def _float_or_nan(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else float("nan")


def _json_sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if value is pd.NA:
        return None
    try:
        if pd.isna(value) and not isinstance(value, (str, bytes)):
            return None
    except (TypeError, ValueError):
        pass
    return value


if __name__ == "__main__":
    main()

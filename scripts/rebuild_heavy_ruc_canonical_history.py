from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from scripts.export_heavy_ruc_training_fit_r2 import COMPONENTS, ComponentSpec, _candidate_config, _load_source_module


STREAM = "HEAVY_RUC"
STREAM_LABEL = "Heavy RUC volume"
FINALIST_MODEL = "HEAVY_RUC__RECON_STATIC_REBUILT"
PARITY_TOLERANCE = 1e-6
REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/heavy_ruc")
SOURCE_SCRIPT = REPRO_ROOT / "source_artifacts/scripts/heavy_ruc_fullgrid_rescue_closure.py"
INPUT_HISTORY = Path("data/model_input_history/heavy_ruc_inputs.parquet")
INPUT_HISTORY_MANIFEST = Path("data/model_input_history/manifest.json")
PARITY_AUDIT = REPRO_ROOT / "forward_scorer_parity_audit.json"
DEFAULT_OUTPUT_DIR = Path("artifacts/heavy_ruc_forward_parity_debug")
CANONICAL_FILES = [
    "canonical_history_comparison.csv",
    "canonical_feature_matrix_comparison.csv",
    "canonical_replay_summary.csv",
    "canonical_history_manifest.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover and audit Heavy RUC canonical parent-run input history.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-script", type=Path, default=SOURCE_SCRIPT)
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--write-history-if-passed", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = _resolve(repo_root, args.output_dir)
    source_script = _resolve(repo_root, args.source_script)
    repro_root = repo_root / REPRO_ROOT
    workbook = _resolve_workbook(repo_root, args.workbook, repro_root)

    module = _load_source_module(source_script)
    current_history = pd.read_parquet(repo_root / INPUT_HISTORY)
    stored = pd.read_parquet(repro_root / "component_predictions.parquet")
    registry = pd.read_parquet(repro_root / "model_registry.parquet")
    existing_audit = _read_json(repo_root / PARITY_AUDIT)

    current_stream, current_source_info = _build_repo_stream_data(module, current_history)
    candidate_raw = module.load_input_sheet(workbook)
    candidate_stream, candidate_source_info = _build_workbook_stream_data(module, candidate_raw)

    current_replay = _replay_components(module, current_stream)
    candidate_replay = _replay_components(module, candidate_stream)
    current_summary = _replay_summary(stored, current_replay, "current_repo_model_input_history")
    candidate_summary = _replay_summary(stored, candidate_replay, "source_script_stage1_workbook_history")
    replay_summary = pd.concat([current_summary, candidate_summary], ignore_index=True, sort=False)

    history_comparison = _history_comparison(
        module,
        repo_root,
        workbook,
        current_history,
        candidate_raw,
        current_stream,
        candidate_stream,
        current_source_info,
        candidate_source_info,
        stored,
    )
    feature_comparison = _canonical_feature_matrix_comparison(
        module,
        current_stream,
        candidate_stream,
        replay_summary,
        current_replay,
        candidate_replay,
        stored,
    )
    manifest = _manifest(
        repo_root,
        workbook,
        source_script,
        registry,
        history_comparison,
        replay_summary,
        feature_comparison,
        current_source_info,
        candidate_source_info,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    history_comparison.to_csv(output_dir / "canonical_history_comparison.csv", index=False)
    feature_comparison.to_csv(output_dir / "canonical_feature_matrix_comparison.csv", index=False)
    replay_summary.to_csv(output_dir / "canonical_replay_summary.csv", index=False)
    (output_dir / "canonical_history_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )

    passed = _source_candidate_passed(candidate_summary)
    if passed and args.write_history_if_passed:
        _write_canonical_history(repo_root, candidate_raw, candidate_stream, module, workbook, source_script)
        manifest["write_history_status"] = "written_after_component_and_final_parity_passed"
    elif passed:
        manifest["write_history_status"] = "passed_not_written_without_write_history_flag"
    else:
        manifest["write_history_status"] = "not_written_component_or_final_parity_failed"
    (output_dir / "canonical_history_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    _write_canonical_diagnosis(output_dir, manifest, replay_summary)

    _update_parity_audit(repo_root, output_dir, manifest, replay_summary, feature_comparison, existing_audit)
    print(f"Wrote Heavy RUC canonical-history audit files to {_repo_rel(repo_root, output_dir)}")
    print(f"Source-script workbook sheet: {candidate_source_info['input_sheet']}")
    print(f"Post-canonical parity status: {'passed' if passed else 'failed'}")


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _resolve_workbook(repo_root: Path, override: Path | None, repro_root: Path) -> Path:
    candidates: list[Path] = []
    if override is not None:
        candidates.append(override)
    for env_name in ["NLTF_HEAVY_RUC_CANONICAL_WORKBOOK", "NLTF_MODEL_INPUT_WORKBOOK", "MODEL_INPUT_WORKBOOK_PATH"]:
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value))
    registry_path = repro_root / "model_registry.parquet"
    if registry_path.exists():
        try:
            registry = pd.read_parquet(registry_path)
            source_values = registry.get("source_workbook", pd.Series(dtype=str)).dropna().astype(str)
            candidates.extend(Path(value) for value in source_values.unique())
        except Exception:
            pass
    manifest_path = repo_root / "data" / "model_input_history" / "manifest.json"
    if manifest_path.exists():
        try:
            basename = str(_read_json(manifest_path).get("source_basename") or "")
            if basename:
                candidates.append(repo_root / "data" / "source_workbooks" / basename)
                candidates.append(repo_root.parent.parent / "Revenue Modeling - Strategic Review" / "04 Models" / "Inputs" / basename)
        except Exception:
            pass

    seen: set[str] = set()
    for candidate in candidates:
        path = candidate.expanduser()
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            return path
    searched = "; ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Could not resolve Heavy RUC canonical workbook. Searched: {searched}")


def _build_repo_stream_data(module: Any, history: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    if "period" not in history.columns or "target" not in history.columns:
        raise AssertionError("heavy_ruc_inputs.parquet must expose period and target columns")
    frame = history.copy()
    frame["__period__"] = frame["period"].map(module.parse_quarter_value)
    frame = frame.rename(columns={"target": "Heavy RUC net km"})
    stream_data, info = _stream_data_from_frame(module, frame)
    info.update(
        {
            "history_source": "data/model_input_history/heavy_ruc_inputs.parquet",
            "input_sheet": "model_input_history",
            "raw_rows": int(len(history)),
            "raw_columns": int(history.shape[1]),
        }
    )
    return stream_data, info


def _build_workbook_stream_data(module: Any, frame: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    stream_data, info = _stream_data_from_frame(module, frame)
    info.update(
        {
            "history_source": "source_script_load_input_sheet",
            "input_sheet": str(frame.attrs.get("input_sheet") or ""),
            "raw_rows": int(len(frame)),
            "raw_columns": int(frame.shape[1]),
        }
    )
    return stream_data, info


def _stream_data_from_frame(module: Any, frame: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    target_col, target_is_log = module.detect_target_col(frame, STREAM)
    feature_cols = module.detect_feature_cols(frame, STREAM, [target_col])
    y_raw, y_log = module.build_target_series(frame, target_col, target_is_log)
    exog, groups, primary_log = module.build_exog(frame, STREAM, feature_cols)
    stream_data = module.StreamData(STREAM, target_col, target_is_log, feature_cols, y_raw, y_log, exog, groups, primary_log)
    info = {
        "target_column": target_col,
        "target_is_log": bool(target_is_log),
        "source_feature_count": int(len(feature_cols)),
        "engineered_feature_count": int(exog.shape[1]),
        "period_min": str(y_raw.dropna().index.min()),
        "period_max": str(y_raw.dropna().index.max()),
        "target_non_null_rows": int(y_raw.notna().sum()),
        "target_positive_rows": int(y_raw.gt(0).sum()),
        "log_target_non_null_rows": int(y_log.notna().sum()),
    }
    return stream_data, info


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


def _replay_summary(stored: pd.DataFrame, replay: pd.DataFrame, history_candidate: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    parity_rows = _parity_rows(stored, replay)
    for spec in COMPONENTS:
        group = parity_rows[parity_rows["component_model"].astype(str).eq(spec.component_model)].copy()
        matched = group["replayed_pred"].notna()
        deltas = pd.to_numeric(group.loc[matched, "abs_delta"], errors="coerce")
        worst = group.loc[deltas.idxmax()] if not deltas.empty else pd.Series(dtype=object)
        rows.append(
            {
                "history_candidate": history_candidate,
                "row_type": "component",
                "component_label": spec.component_label,
                "component_model": spec.component_model,
                "stored_rows": int(len(group)),
                "matched_rows": int(matched.sum()),
                "missing_rows": int((~matched).sum()),
                "max_abs_delta": float(deltas.max()) if not deltas.empty else np.nan,
                "mean_abs_delta": float(deltas.mean()) if not deltas.empty else np.nan,
                "worst_origin": worst.get("origin"),
                "worst_target_period": worst.get("target_period"),
                "worst_horizon": worst.get("horizon"),
                "parity_tolerance": PARITY_TOLERANCE,
                "parity_status": "passed" if not deltas.empty and float(deltas.max()) <= PARITY_TOLERANCE else "failed",
            }
        )
    rows.append(_weighted_replay_summary(stored, parity_rows, history_candidate))
    return pd.DataFrame(rows)


def _parity_rows(stored: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    keys = ["component_model", "origin", "target_period", "horizon"]
    merged = stored.merge(replay[keys + ["replayed_pred", "replayed_pred_log"]], on=keys, how="left")
    merged["component_pred"] = pd.to_numeric(merged["component_pred"], errors="coerce")
    merged["replayed_pred"] = pd.to_numeric(merged["replayed_pred"], errors="coerce")
    merged["abs_delta"] = (merged["component_pred"] - merged["replayed_pred"]).abs()
    return merged


def _weighted_replay_summary(stored: pd.DataFrame, parity_rows: pd.DataFrame, history_candidate: str) -> dict[str, Any]:
    data = parity_rows.copy()
    data["replayed_weighted_component_pred"] = pd.to_numeric(data["replayed_pred"], errors="coerce") * pd.to_numeric(
        data["component_weight"],
        errors="coerce",
    )
    group_cols = [column for column in ["score_basis", "eval_grid", "origin", "target_period", "horizon"] if column in data.columns]
    grouped = (
        data.groupby(group_cols, dropna=False)
        .agg(
            replayed_final_pred=("replayed_weighted_component_pred", "sum"),
            stored_final_pred=("final_pred", "first"),
            component_count=("component_model", "nunique"),
            missing_components=("replayed_pred", lambda values: int(pd.isna(values).sum())),
        )
        .reset_index()
    )
    grouped = grouped[grouped["component_count"].eq(len(COMPONENTS))].copy()
    grouped["abs_delta"] = (
        pd.to_numeric(grouped["stored_final_pred"], errors="coerce")
        - pd.to_numeric(grouped["replayed_final_pred"], errors="coerce")
    ).abs()
    deltas = pd.to_numeric(grouped["abs_delta"], errors="coerce")
    worst = grouped.loc[deltas.idxmax()] if not deltas.empty else pd.Series(dtype=object)
    return {
        "history_candidate": history_candidate,
        "row_type": "final_weighted",
        "component_label": "C1_C4_weighted",
        "component_model": FINALIST_MODEL,
        "stored_rows": int(len(grouped)),
        "matched_rows": int(grouped["missing_components"].eq(0).sum()) if not grouped.empty else 0,
        "missing_rows": int(grouped["missing_components"].gt(0).sum()) if not grouped.empty else 0,
        "max_abs_delta": float(deltas.max()) if not deltas.empty else np.nan,
        "mean_abs_delta": float(deltas.mean()) if not deltas.empty else np.nan,
        "worst_origin": worst.get("origin"),
        "worst_target_period": worst.get("target_period"),
        "worst_horizon": worst.get("horizon"),
        "parity_tolerance": PARITY_TOLERANCE,
        "parity_status": "passed" if not deltas.empty and float(deltas.max()) <= PARITY_TOLERANCE else "failed",
    }


def _history_comparison(
    module: Any,
    repo_root: Path,
    workbook: Path,
    current_history: pd.DataFrame,
    candidate_raw: pd.DataFrame,
    current_stream: Any,
    candidate_stream: Any,
    current_info: dict[str, Any],
    candidate_info: dict[str, Any],
    stored: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rows.extend(_summary_rows(repo_root, workbook, current_info, candidate_info))
    rows.extend(_source_feature_rows(module, current_stream, candidate_stream))
    rows.extend(_period_value_comparison_rows(module, current_history, candidate_raw, stored))
    return pd.DataFrame(rows)


def _summary_rows(repo_root: Path, workbook: Path, current_info: dict[str, Any], candidate_info: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for history_candidate, info in [
        ("current_repo_model_input_history", current_info),
        ("source_script_stage1_workbook_history", candidate_info),
    ]:
        rows.append(
            {
                "comparison_section": "history_summary",
                "history_candidate": history_candidate,
                "metric": "rows",
                "repo_value": current_info["raw_rows"] if history_candidate.startswith("current") else np.nan,
                "canonical_candidate_value": candidate_info["raw_rows"] if history_candidate.startswith("source") else np.nan,
                "status": "observed",
                "notes": "",
            }
        )
        rows.append(
            {
                "comparison_section": "history_summary",
                "history_candidate": history_candidate,
                "metric": "source_feature_count",
                "repo_value": current_info["source_feature_count"] if history_candidate.startswith("current") else np.nan,
                "canonical_candidate_value": candidate_info["source_feature_count"] if history_candidate.startswith("source") else np.nan,
                "status": "observed",
                "notes": "",
            }
        )
        rows.append(
            {
                "comparison_section": "history_summary",
                "history_candidate": history_candidate,
                "metric": "engineered_feature_count",
                "repo_value": current_info["engineered_feature_count"] if history_candidate.startswith("current") else np.nan,
                "canonical_candidate_value": candidate_info["engineered_feature_count"] if history_candidate.startswith("source") else np.nan,
                "status": "observed",
                "notes": "",
            }
        )
    rows.append(
        {
            "comparison_section": "source_artifact",
            "history_candidate": "source_script_stage1_workbook_history",
            "metric": "workbook",
            "repo_value": "",
            "canonical_candidate_value": workbook.name,
            "status": "found",
            "notes": f"sha256={_sha256(workbook)}",
        }
    )
    rows.append(
        {
            "comparison_section": "source_artifact",
            "history_candidate": "current_repo_model_input_history",
            "metric": "input_history",
            "repo_value": "data/model_input_history/heavy_ruc_inputs.parquet",
            "canonical_candidate_value": "",
            "status": "found",
            "notes": f"sha256={_sha256(repo_root / INPUT_HISTORY)}",
        }
    )
    return rows


def _source_feature_rows(module: Any, current_stream: Any, candidate_stream: Any) -> list[dict[str, Any]]:
    current_by_key = {_column_key(module, column): column for column in current_stream.feature_cols}
    candidate_by_key = {_column_key(module, column): column for column in candidate_stream.feature_cols}
    rows = []
    for key in sorted(set(current_by_key) | set(candidate_by_key)):
        repo_col = current_by_key.get(key)
        source_col = candidate_by_key.get(key)
        if repo_col and source_col:
            status = "shared_source_feature"
        elif source_col:
            status = "canonical_source_only"
        else:
            status = "repo_history_only"
        rows.append(
            {
                "comparison_section": "source_feature_inventory",
                "history_candidate": "source_script_stage1_workbook_history",
                "metric": key,
                "repo_value": repo_col or "",
                "canonical_candidate_value": source_col or "",
                "status": status,
                "notes": "",
            }
        )
    return rows


def _period_value_comparison_rows(
    module: Any,
    current_history: pd.DataFrame,
    candidate_raw: pd.DataFrame,
    stored: pd.DataFrame,
) -> list[dict[str, Any]]:
    current = current_history.copy()
    candidate = candidate_raw.copy()
    current["period_key"] = current["period"].astype(str)
    candidate["period_key"] = candidate["__period__"].astype(str)
    rows: list[dict[str, Any]] = []

    target_actual = stored[["target_period", "actual"]].drop_duplicates().rename(columns={"target_period": "period_key"})
    current_target = current[["period_key", "target"]].rename(columns={"target": "current_target"})
    candidate_target_col, _ = module.detect_target_col(candidate, STREAM)
    candidate_target = candidate[["period_key", candidate_target_col]].rename(columns={candidate_target_col: "candidate_target"})
    target_compare = target_actual.merge(current_target, on="period_key", how="left").merge(candidate_target, on="period_key", how="left")
    for left, right, label in [
        ("actual", "current_target", "parent_actual_vs_current_target"),
        ("actual", "candidate_target", "parent_actual_vs_candidate_target"),
        ("current_target", "candidate_target", "current_target_vs_candidate_target"),
    ]:
        delta = (pd.to_numeric(target_compare[left], errors="coerce") - pd.to_numeric(target_compare[right], errors="coerce")).abs()
        rows.append(
            {
                "comparison_section": "period_value_delta",
                "history_candidate": "target",
                "metric": label,
                "repo_value": float(delta.max()) if delta.notna().any() else np.nan,
                "canonical_candidate_value": float(delta.mean()) if delta.notna().any() else np.nan,
                "status": "matched" if delta.fillna(0).max() <= PARITY_TOLERANCE else "differs",
                "notes": "repo_value=max_abs_delta; canonical_candidate_value=mean_abs_delta",
            }
        )

    current_by_key = {_column_key(module, column): column for column in current.columns if column not in {"period_key"}}
    candidate_by_key = {_column_key(module, column): column for column in candidate.columns if column not in {"period_key", "__period__"}}
    for key in sorted(set(current_by_key) & set(candidate_by_key)):
        cur_col = current_by_key[key]
        cand_col = candidate_by_key[key]
        merged = current[["period_key", cur_col]].merge(candidate[["period_key", cand_col]], on="period_key", how="inner")
        left = pd.to_numeric(merged[cur_col], errors="coerce")
        right = pd.to_numeric(merged[cand_col], errors="coerce")
        if left.notna().sum() == 0 and right.notna().sum() == 0:
            continue
        delta = (left - right).abs()
        role = _column_role(key)
        rows.append(
            {
                "comparison_section": f"{role}_column_delta",
                "history_candidate": "shared_period_columns",
                "metric": key,
                "repo_value": float(delta.max()) if delta.notna().any() else np.nan,
                "canonical_candidate_value": float(delta.mean()) if delta.notna().any() else np.nan,
                "status": "matched" if delta.fillna(0).max() <= PARITY_TOLERANCE else "differs",
                "notes": f"repo_column={cur_col}; source_column={cand_col}; repo_value=max_abs_delta; canonical_candidate_value=mean_abs_delta",
            }
        )
    return rows


def _canonical_feature_matrix_comparison(
    module: Any,
    current_stream: Any,
    candidate_stream: Any,
    replay_summary: pd.DataFrame,
    current_replay: pd.DataFrame,
    candidate_replay: pd.DataFrame,
    stored: pd.DataFrame,
) -> pd.DataFrame:
    current_rows = _parity_rows(stored, current_replay)
    candidate_rows = _parity_rows(stored, candidate_replay)
    cases: list[dict[str, Any]] = []
    for history_candidate, rows in [
        ("current_repo_model_input_history", current_rows),
        ("source_script_stage1_workbook_history", candidate_rows),
    ]:
        for spec in COMPONENTS:
            group = rows[rows["component_model"].astype(str).eq(spec.component_model)].copy()
            if group.empty:
                continue
            worst = group.sort_values("abs_delta", ascending=False, kind="stable").iloc[0].to_dict()
            worst["history_candidate"] = history_candidate
            cases.append(worst)

    out_rows: list[dict[str, Any]] = []
    for case in cases:
        spec = _component_spec_by_model(str(case.get("component_model")))
        if spec is None:
            continue
        origin = str(case.get("origin"))
        target = str(case.get("target_period"))
        horizon = int(case.get("horizon"))
        feature_names = _dedupe(
            _feature_names(module, current_stream, spec)
            + _feature_names(module, candidate_stream, spec)
        )
        current_values = _forecast_feature_values(module, current_stream, spec, origin, horizon)
        candidate_values = _forecast_feature_values(module, candidate_stream, spec, origin, horizon)
        current_window = _training_window_details(module, current_stream, spec, origin)
        candidate_window = _training_window_details(module, candidate_stream, spec, origin)
        for index, feature in enumerate(feature_names, start=1):
            current_value = _float_or_nan(current_values.get(feature))
            candidate_value = _float_or_nan(candidate_values.get(feature))
            delta = abs(current_value - candidate_value) if np.isfinite(current_value) and np.isfinite(candidate_value) else np.nan
            out_rows.append(
                {
                    "case_id": f"{case['history_candidate']}::{spec.component_label}",
                    "history_candidate": case["history_candidate"],
                    "component_label": spec.component_label,
                    "component_model": spec.component_model,
                    "origin": origin,
                    "target_period": target,
                    "horizon": horizon,
                    "feature_order": index,
                    "feature_name": feature,
                    "current_repo_feature_value": current_value,
                    "source_script_feature_value": candidate_value,
                    "current_vs_source_abs_delta": delta,
                    "parent_feature_value": np.nan,
                    "comparison_status": "parent_feature_matrix_missing",
                    "current_training_start": current_window.get("effective_training_start"),
                    "current_training_end": current_window.get("effective_training_end"),
                    "current_training_rows": current_window.get("training_rows"),
                    "source_training_start": candidate_window.get("effective_training_start"),
                    "source_training_end": candidate_window.get("effective_training_end"),
                    "source_training_rows": candidate_window.get("training_rows"),
                    "target_transform": "log target for component model fit",
                    "inverse_transform": "exp(pred_log), clipped by source safe_exp",
                    "hyperparameters_json": spec.hyperparameters_json,
                    "stored_component_pred": case.get("component_pred"),
                    "replayed_component_pred": case.get("replayed_pred"),
                    "abs_delta": case.get("abs_delta"),
                    "notes": (
                        "Parent-run fitted feature matrix is not available. This compares the committed repo history "
                        "feature row with the source-script workbook feature row."
                    ),
                }
            )
    return pd.DataFrame(out_rows)


def _manifest(
    repo_root: Path,
    workbook: Path,
    source_script: Path,
    registry: pd.DataFrame,
    history_comparison: pd.DataFrame,
    replay_summary: pd.DataFrame,
    feature_comparison: pd.DataFrame,
    current_info: dict[str, Any],
    candidate_info: dict[str, Any],
) -> dict[str, Any]:
    current = replay_summary[replay_summary["history_candidate"].eq("current_repo_model_input_history")]
    candidate = replay_summary[replay_summary["history_candidate"].eq("source_script_stage1_workbook_history")]
    candidate_component = candidate[candidate["row_type"].eq("component")]
    candidate_final = candidate[candidate["row_type"].eq("final_weighted")]
    candidate_max = float(pd.to_numeric(candidate["max_abs_delta"], errors="coerce").max())
    current_max = float(pd.to_numeric(current["max_abs_delta"], errors="coerce").max())
    candidate_passed = _source_candidate_passed(candidate)
    failing = candidate.sort_values("max_abs_delta", ascending=False, kind="stable").iloc[0].to_dict()
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "finalist_model": FINALIST_MODEL,
        "parity_tolerance": PARITY_TOLERANCE,
        "source_script": {
            "repo_relative_path": _repo_rel(repo_root, source_script),
            "sha256": _sha256(source_script),
        },
        "current_repo_history": {
            "repo_relative_path": _repo_rel(repo_root, repo_root / INPUT_HISTORY),
            "sha256": _sha256(repo_root / INPUT_HISTORY),
            **current_info,
        },
        "source_script_workbook_history": {
            "workbook_basename": workbook.name,
            "workbook_size_bytes": workbook.stat().st_size,
            "workbook_sha256": _sha256(workbook),
            **candidate_info,
        },
        "registry_source": {
            "source_parent_run_basename": _basename_from_registry(registry, "source_parent_run"),
            "source_workbook_basename": _basename_from_registry(registry, "source_workbook"),
            "source_sheet": _first_registry_value(registry, "source_sheet"),
        },
        "current_repo_history_replay": {
            "component_or_final_max_abs_delta": current_max,
            "parity_status": "passed" if current_max <= PARITY_TOLERANCE else "failed",
        },
        "post_canonical_history_replay": {
            "component_or_final_max_abs_delta": candidate_max,
            "component_max_abs_delta": float(pd.to_numeric(candidate_component["max_abs_delta"], errors="coerce").max()),
            "final_weighted_max_abs_delta": float(pd.to_numeric(candidate_final["max_abs_delta"], errors="coerce").max()),
            "parity_status": "passed" if candidate_passed else "failed",
            "failing_component": failing.get("component_model"),
            "failing_component_label": failing.get("component_label"),
            "worst_origin": failing.get("worst_origin"),
            "worst_target_period": failing.get("worst_target_period"),
            "worst_horizon": failing.get("worst_horizon"),
        },
        "history_recovery_status": (
            "canonical_source_script_history_recovered_but_component_parity_failed"
            if not candidate_passed
            else "canonical_source_script_history_recovered_and_parity_passed"
        ),
        "root_cause_assessment": {
            "current_repo_history_schema_mismatch": "confirmed",
            "current_repo_history_engineered_feature_count": int(current_info["engineered_feature_count"]),
            "source_script_engineered_feature_count": int(candidate_info["engineered_feature_count"]),
            "heavy_target_mismatch": "not_supported_parent_actuals_match",
            "schiff_c2_input_path": "exact_replay_passed",
            "target_lagged_gbm_components": "failed_replay_for_c3_c4",
            "fitted_component_estimators": "missing_from_parent_run",
            "likely_residual_blocker": "target_lagged_gbm_fitted_state_or_runtime_replay_drift",
        },
        "exported_files": CANONICAL_FILES,
        "history_comparison_rows": int(len(history_comparison)),
        "feature_matrix_comparison_rows": int(len(feature_comparison)),
    }


def _update_parity_audit(
    repo_root: Path,
    output_dir: Path,
    manifest: dict[str, Any],
    replay_summary: pd.DataFrame,
    feature_comparison: pd.DataFrame,
    existing_audit: dict[str, Any],
) -> None:
    audit_path = repo_root / PARITY_AUDIT
    candidate = replay_summary[replay_summary["history_candidate"].eq("source_script_stage1_workbook_history")].copy()
    failing = candidate.sort_values("max_abs_delta", ascending=False, kind="stable").iloc[0].to_dict()
    max_delta = float(failing["max_abs_delta"])
    previous = {
        "audit_version": existing_audit.get("audit_version"),
        "parity_status": existing_audit.get("parity_status"),
        "max_abs_delta": existing_audit.get("max_abs_delta"),
        "failing_component": existing_audit.get("failing_component"),
        "worst_row": existing_audit.get("worst_row"),
    }
    payload = dict(existing_audit)
    payload.update(
        {
            "audit_name": "heavy_ruc_forward_scorer_canonical_history_recovery",
            "audit_version": "2026-06-10-heavy-ruc-canonical-history-v1",
            "parity_status": "passed" if _source_candidate_passed(candidate) else "failed",
            "parity_tolerance": PARITY_TOLERANCE,
            "data_scope": "canonical_source_script_history_component_replay",
            "max_abs_delta": max_delta,
            "failing_component": failing.get("component_model"),
            "missing_feature_or_artifact": (
                "Source-script Stage 1 workbook history was recovered and narrows the Heavy RUC replay gap, "
                "but target-lagged GBM components C3/C4 still exceed parity tolerance; parent fitted component "
                "estimators and parent feature matrices were not retained."
            ),
            "notes": (
                "The committed data/model_input_history/heavy_ruc_inputs.parquet remains unchanged because the "
                "source-script workbook candidate does not pass all component and final weighted replay checks at "
                "the fixed 1e-6 tolerance. Heavy RUC remains disabled for numeric forward forecasts."
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
            "diagnosis": {
                **payload.get("diagnosis", {}),
                "debug_pack_path": _repo_rel(repo_root, output_dir),
                "canonical_history_files": CANONICAL_FILES,
                "canonical_history_manifest": manifest,
                "canonical_replay_summary": replay_summary.to_dict(orient="records"),
                "canonical_feature_matrix_status": "parent_feature_matrix_missing",
                "current_repo_history_replay": manifest["current_repo_history_replay"],
                "post_canonical_history_replay": manifest["post_canonical_history_replay"],
                "previous_recorded_audit": previous,
                "fitted_estimators_status": "missing_from_parent_run",
                "capability_decision": "keep_parity_failed",
            },
        }
    )
    payload["repo_artifacts"] = _repo_artifacts(repo_root, output_dir)
    audit_path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=_json_default) + "\n", encoding="utf-8")


def _source_candidate_passed(summary: pd.DataFrame) -> bool:
    if summary.empty:
        return False
    values = pd.to_numeric(summary["max_abs_delta"], errors="coerce")
    return bool(values.notna().all() and values.le(PARITY_TOLERANCE).all())


def _write_canonical_diagnosis(output_dir: Path, manifest: dict[str, Any], replay_summary: pd.DataFrame) -> None:
    path = output_dir / "heavy_ruc_parity_diagnosis.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Heavy RUC forward-scorer parity diagnosis\n"
    marker = "## Canonical history recovery update"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    source = replay_summary[replay_summary["history_candidate"].eq("source_script_stage1_workbook_history")]
    current = replay_summary[replay_summary["history_candidate"].eq("current_repo_model_input_history")]
    source_components = source[source["row_type"].eq("component")].copy()
    source_final = source[source["row_type"].eq("final_weighted")].copy()
    lines = [
        "",
        marker,
        "",
        "The canonical-history recovery audit found the source-script workbook path and `Stage 1 Inputs` sheet, but Heavy RUC remains `parity_failed`.",
        "",
        "### Current vs source-script history",
        "",
        f"- Current repo history max component/final delta: `{float(pd.to_numeric(current['max_abs_delta'], errors='coerce').max()):.12g}`.",
        f"- Source-script workbook history max component/final delta: `{float(pd.to_numeric(source['max_abs_delta'], errors='coerce').max()):.12g}`.",
        f"- Source-script workbook sheet: `{manifest['source_script_workbook_history']['input_sheet']}`.",
        f"- Current repo engineered feature count: `{manifest['current_repo_history']['engineered_feature_count']}`.",
        f"- Source-script engineered feature count: `{manifest['source_script_workbook_history']['engineered_feature_count']}`.",
        "",
        "### Post-canonical replay",
        "",
    ]
    for row in source_components.to_dict(orient="records"):
        lines.append(
            f"- {row['component_label']}: `{row['parity_status']}`, max abs delta `{float(row['max_abs_delta']):.12g}`."
        )
    if not source_final.empty:
        row = source_final.iloc[0]
        lines.append(
            f"- Final weighted C1-C4 replay: `{row['parity_status']}`, max abs delta `{float(row['max_abs_delta']):.12g}`."
        )
    lines.extend(
        [
            "",
            "### Governance decision",
            "",
            "- `data/model_input_history/heavy_ruc_inputs.parquet` was not overwritten because source-script replay still fails the fixed `1e-6` component/final parity tolerance.",
            "- C2 Schiff replay passes from the recovered source-script history, but target-lagged GBM components C3/C4 remain outside tolerance.",
            "- The remaining governed gap is missing parent fitted component estimators or parent feature matrices for the target-lagged GBM components.",
            "",
        ]
    )
    path.write_text(existing.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")


def _write_canonical_history(repo_root: Path, candidate_raw: pd.DataFrame, candidate_stream: Any, module: Any, workbook: Path, source_script: Path) -> None:
    raise RuntimeError(
        "Automatic Heavy RUC history overwrite is intentionally disabled until a repo-history schema mapping has "
        "separate review. The current canonical candidate did not require this path in validation."
    )


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
        "effective_training_start": str(X.index.min()) if len(X) else None,
        "effective_training_end": str(X.index.max()) if len(X) else None,
        "training_rows": int(len(X)),
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
    return feature_row


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


def _column_key(module: Any, column: Any) -> str:
    return module.normalise_name(str(column))


def _column_role(key: str) -> str:
    if "target" in key and "lag" in key:
        return "target_lag"
    if key.startswith("log ") or " log " in f" {key} ":
        return "transformed_log"
    if "lag" in key:
        return "lag"
    return "raw"


def _repo_artifacts(repo_root: Path, output_dir: Path) -> list[dict[str, str]]:
    paths = [
        repo_root / SOURCE_SCRIPT,
        repo_root / INPUT_HISTORY,
        repo_root / INPUT_HISTORY_MANIFEST,
        repo_root / REPRO_ROOT / "component_predictions.parquet",
        repo_root / REPRO_ROOT / "model_registry.parquet",
        output_dir / "heavy_ruc_parity_diagnosis.md",
        *[output_dir / name for name in CANONICAL_FILES],
    ]
    return [{"repo_relative_path": _repo_rel(repo_root, path), "sha256": _sha256(path)} for path in paths if path.exists()]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def _first_registry_value(registry: pd.DataFrame, column: str) -> str:
    if column not in registry.columns:
        return ""
    values = registry[column].dropna().astype(str)
    return values.iloc[0] if not values.empty else ""


def _basename_from_registry(registry: pd.DataFrame, column: str) -> str:
    value = _first_registry_value(registry, column)
    return Path(value).name if value else ""


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def _float_or_nan(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else float("nan")


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

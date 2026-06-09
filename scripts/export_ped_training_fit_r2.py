from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STREAM = "PED"
STREAM_LABEL = "PED VKT per capita"
FINALIST_MODEL = "PED__RESCUE_static_annual_weighted_top12_capnone"
OUTER_COMPONENT_MODEL = "PED__HPOREFINE_solver_static_convex_top18"
STATIC_SOLVER_MODEL = "PED__solver_static_convex_top18"
PREQ_SOLVER_MODEL = "PED__solver_preq_convex_top18"
DIRECT_HPO_COMPONENT = "PED__diff__GBR_learning_rate0_05_max_depth1_n_estimators650__ylag__w40"
TRAINING_SCOPE = "training_window_fitted_rows"

DEFAULT_REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/ped")
DEFAULT_INNER_REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/ped_inner_hpo")
DEFAULT_SOURCE_ARTIFACTS_ROOT = DEFAULT_INNER_REPRO_ROOT / "source_artifacts"
DEFAULT_OUTPUT = DEFAULT_REPRO_ROOT / "training_fit_predictions.parquet"


@dataclass(frozen=True)
class ReplayEvidence:
    direct_component_max_delta: float
    static_solver_max_delta: float
    preq_solver_max_delta: float
    hpo_outer_max_delta: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export PED fitted training rows for the R2 ladder.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--source-artifacts-root",
        type=Path,
        default=Path(os.environ.get("PED_HPO_SOURCE_ARTIFACTS_ROOT", str(DEFAULT_SOURCE_ARTIFACTS_ROOT))),
        help="Repo-local PED source artifact root, or PED_HPO_SOURCE_ARTIFACTS_ROOT for development overrides.",
    )
    parser.add_argument("--source-script", type=Path, default=None)
    parser.add_argument("--arbitration-run", type=Path, default=None)
    parser.add_argument("--hpo-weights", type=Path, default=None)
    parser.add_argument("--workbook", type=Path, default=None, help="Optional workbook override for local regeneration.")
    parser.add_argument("--repro-root", type=Path, default=DEFAULT_REPRO_ROOT)
    parser.add_argument("--inner-repro-root", type=Path, default=DEFAULT_INNER_REPRO_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replay-tolerance", type=float, default=1e-4)
    parser.add_argument("--skip-replay-validation", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    repro_root = _resolve(repo_root, args.repro_root)
    inner_root = _resolve(repo_root, args.inner_repro_root)
    output = _resolve(repo_root, args.output)
    source_root = _resolve(repo_root, args.source_artifacts_root)
    source_script = _resolve(repo_root, args.source_script) if args.source_script else source_root / "scripts" / "stage1_finalist_arbitration.py"
    hpo_weights_path = _resolve(repo_root, args.hpo_weights) if args.hpo_weights else source_root / "hpo_refinement_core_outputs" / "hpo_refined_ensemble_weights.csv"
    run_dir = (
        _resolve(repo_root, args.arbitration_run)
        if args.arbitration_run
        else source_root / "finalist_arbitration_run_20260520_002339"
    )

    for path in [source_script, hpo_weights_path, run_dir / "ensemble_weights.csv", run_dir / "candidate_config_inventory.csv"]:
        if not path.exists():
            raise FileNotFoundError(f"Required PED source artifact not found: {path}")

    module = _load_source_module(source_script)
    registry = pd.read_parquet(repro_root / "model_registry.parquet")
    component_predictions = pd.read_parquet(repro_root / "component_predictions.parquet")
    inner_predictions = pd.read_parquet(inner_root / "inner_component_predictions.parquet")
    _assert_registry_matches(registry)

    workbook = _resolve(repo_root, args.workbook) if args.workbook else Path(str(registry["source_workbook"].iloc[0]))
    stream_data = _build_stream_data(module, workbook)
    hpo_weights = _hpo_weights(hpo_weights_path)
    static_weights = _static_weights(run_dir / "ensemble_weights.csv")
    preq_weights = _preq_weights(run_dir / "ensemble_weights.csv")
    candidate_configs = _candidate_configs(module, run_dir / "candidate_config_inventory.csv", static_weights, preq_weights, hpo_weights)

    replay_predictions = _validation_replay_predictions(module, stream_data, candidate_configs)
    if args.skip_replay_validation:
        evidence = ReplayEvidence(np.nan, np.nan, np.nan, np.nan)
    else:
        evidence = _validate_replay_layers(
            replay_predictions,
            inner_predictions,
            component_predictions,
            static_weights,
            preq_weights,
            hpo_weights,
            args.replay_tolerance,
        )

    score_basis_origins = _score_basis_origins(component_predictions)
    base_rows = _component_training_rows(
        module,
        stream_data,
        candidate_configs,
        score_basis_origins,
        source_script,
        evidence,
    )
    static_rows = _weighted_training_rows(
        base_rows,
        static_weights,
        STATIC_SOLVER_MODEL,
        "static_convex_top18_fitted",
        "static_convex_mape",
        evidence.static_solver_max_delta,
    )
    preq_rows = _preq_training_rows(base_rows, preq_weights, evidence.preq_solver_max_delta)
    outer_rows = _hpo_training_rows(base_rows, static_rows, preq_rows, hpo_weights, evidence.hpo_outer_max_delta)
    final_rows = _final_training_rows(outer_rows)
    output_rows = pd.concat([base_rows, static_rows, preq_rows, outer_rows, final_rows], ignore_index=True, sort=False)
    output_rows = output_rows.sort_values(
        ["score_basis", "origin", "training_period", "training_fit_stage", "component_model"],
        kind="stable",
    ).reset_index(drop=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    output_rows.to_parquet(output, index=False)
    print(f"Wrote {len(output_rows):,} PED training-fit rows to {output}")
    print(f"Base component rows: {len(base_rows):,}")
    print(f"Static solver rows: {len(static_rows):,}")
    print(f"Preq solver rows: {len(preq_rows):,}")
    print(f"Outer HPO fitted rows: {len(outer_rows):,}")
    print(f"Final HPO fitted rows: {len(final_rows):,}")
    if np.isfinite(evidence.hpo_outer_max_delta):
        print(f"HPO validation replay max abs delta: {evidence.hpo_outer_max_delta:.12g}")


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_source_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("stage1_finalist_arbitration_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import PED source script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module


def _assert_registry_matches(registry: pd.DataFrame) -> None:
    models = set(registry.get("model", pd.Series(dtype=str)).dropna().astype(str))
    if FINALIST_MODEL not in models or OUTER_COMPONENT_MODEL not in models:
        raise AssertionError(f"PED registry no longer contains the governed finalist chain: {sorted(models)}")


def _build_stream_data(module: Any, workbook: Path) -> Any:
    df = module.load_input_sheet(workbook)
    target_col, target_is_log = module.detect_target_col(df, STREAM)
    feature_cols = module.detect_feature_cols(df, STREAM, [target_col])
    y_raw, y_log = module.build_target_series(df, target_col, target_is_log)
    exog, groups, primary_log = module.build_exog(df, STREAM, feature_cols)
    return module.StreamData(STREAM, target_col, target_is_log, feature_cols, y_raw, y_log, exog, groups, primary_log)


def _hpo_weights(path: Path) -> dict[str, float]:
    frame = pd.read_csv(path)
    data = frame[frame["ensemble"].astype(str).eq(OUTER_COMPONENT_MODEL)].drop_duplicates(["component_model", "weight"])
    expected = {STATIC_SOLVER_MODEL, PREQ_SOLVER_MODEL, DIRECT_HPO_COMPONENT}
    weights = {str(row["component_model"]): float(row["weight"]) for _, row in data.iterrows()}
    if set(weights) != expected:
        raise AssertionError(f"Unexpected PED HPO weights: {weights}")
    if abs(sum(weights.values()) - 1.0) > 1e-5:
        raise AssertionError(f"PED HPO weights do not sum to one: {sum(weights.values())}")
    return weights


def _static_weights(path: Path) -> dict[str, float]:
    frame = pd.read_csv(path)
    data = frame[frame["ensemble"].astype(str).eq(STATIC_SOLVER_MODEL)].drop_duplicates(["component_model", "weight"])
    expected = {
        DIRECT_HPO_COMPONENT,
        "PED__struct__GBR_learning_rate0_08_max_depth1_n_estimators650__noylag__w40",
        "PED__diff__GBRLocal_learning_rate0_055_max_depth1_n_estimators600__ylag__w40",
    }
    weights = {str(row["component_model"]): float(row["weight"]) for _, row in data.iterrows()}
    if set(weights) != expected:
        raise AssertionError(f"Unexpected PED static-solver weights: {weights}")
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise AssertionError(f"PED static-solver weights do not sum to one: {sum(weights.values())}")
    return weights


def _preq_weights(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    data = frame[frame["ensemble"].astype(str).eq(PREQ_SOLVER_MODEL)].drop_duplicates(["origin", "component_model", "weight"])
    if data.empty:
        raise AssertionError("PED preq solver weights are missing")
    sums = data.groupby("origin", dropna=False)["weight"].sum()
    if not np.allclose(sums.to_numpy(dtype=float), 1.0, atol=1e-6):
        raise AssertionError("PED preq solver weights do not sum to one after deduplication")
    return data[["origin", "component_model", "weight"]].copy()


def _candidate_configs(
    module: Any,
    inventory_path: Path,
    static_weights: dict[str, float],
    preq_weights: pd.DataFrame,
    hpo_weights: dict[str, float],
) -> dict[str, Any]:
    required = set(static_weights) | set(preq_weights["component_model"].astype(str)) | {DIRECT_HPO_COMPONENT}
    required |= {component for component in hpo_weights if component not in {STATIC_SOLVER_MODEL, PREQ_SOLVER_MODEL}}
    inventory = pd.read_csv(inventory_path)
    data = inventory[inventory["name"].astype(str).isin(required)].copy()
    missing = sorted(required - set(data["name"].astype(str)))
    if missing:
        raise AssertionError(f"Missing PED candidate configs: {missing}")
    configs: dict[str, Any] = {}
    for _, row in data.iterrows():
        name = str(row["name"])
        window_raw = row["window"]
        window = None if pd.isna(window_raw) else int(float(window_raw))
        configs[name] = module.CandidateConfig(
            stream=STREAM,
            name=name,
            model_kind=str(row["model_kind"]),
            params_json=str(row["params_json"]),
            window=window,
            feature_set=str(row["feature_set"]),
            include_target_lags=bool(row["include_target_lags"]),
            family_tag=str(row["family_tag"]),
        )
    return configs


def _validation_replay_predictions(module: Any, stream_data: Any, configs: dict[str, Any]) -> pd.DataFrame:
    frames = []
    for name, cfg in sorted(configs.items()):
        frame = module.evaluate_candidate(stream_data, cfg)
        if frame.empty:
            raise AssertionError(f"No replay rows generated for {name}")
        frames.append(
            frame[["model", "origin", "target_period", "horizon", "pred"]].rename(
                columns={"model": "component_model", "pred": "component_pred"}
            )
        )
    return pd.concat(frames, ignore_index=True, sort=False)


def _validate_replay_layers(
    replay: pd.DataFrame,
    inner_predictions: pd.DataFrame,
    component_predictions: pd.DataFrame,
    static_weights: dict[str, float],
    preq_weights: pd.DataFrame,
    hpo_weights: dict[str, float],
    tolerance: float,
) -> ReplayEvidence:
    direct_delta = _validate_direct_component(replay, inner_predictions, DIRECT_HPO_COMPONENT, tolerance)
    static_rebuilt = _weighted_validation_predictions(replay, static_weights)
    static_delta = _validate_inner_layer(static_rebuilt, inner_predictions, STATIC_SOLVER_MODEL, "static_solver_pred", tolerance)
    preq_rebuilt = _preq_validation_predictions(replay, preq_weights)
    preq_delta = _validate_inner_layer(preq_rebuilt, inner_predictions, PREQ_SOLVER_MODEL, "preq_solver_pred", tolerance)
    hpo_rebuilt = _hpo_validation_predictions(replay, static_rebuilt, preq_rebuilt, hpo_weights)
    hpo_delta = _validate_hpo_outer_layer(hpo_rebuilt, component_predictions, tolerance)
    return ReplayEvidence(direct_delta, static_delta, preq_delta, hpo_delta)


def _validate_direct_component(replay: pd.DataFrame, inner: pd.DataFrame, component: str, tolerance: float) -> float:
    stored = inner[inner["inner_component_model"].astype(str).eq(component)].copy()
    if stored.empty:
        raise AssertionError(f"Stored direct component predictions missing for {component}")
    merged = stored.merge(
        replay[replay["component_model"].astype(str).eq(component)][["origin", "target_period", "horizon", "component_pred"]],
        on=["origin", "target_period", "horizon"],
        how="left",
    )
    return _assert_delta_within_tolerance(merged["pred"], merged["component_pred"], tolerance, component)


def _validate_inner_layer(rebuilt: pd.DataFrame, inner: pd.DataFrame, component: str, pred_col: str, tolerance: float) -> float:
    stored = inner[inner["inner_component_model"].astype(str).eq(component)].copy()
    if stored.empty:
        raise AssertionError(f"Stored inner-layer predictions missing for {component}")
    merged = stored.merge(rebuilt[["origin", "target_period", "horizon", pred_col]], on=["origin", "target_period", "horizon"], how="left")
    return _assert_delta_within_tolerance(merged["pred"], merged[pred_col], tolerance, component)


def _validate_hpo_outer_layer(rebuilt: pd.DataFrame, component_predictions: pd.DataFrame, tolerance: float) -> float:
    stored = component_predictions[component_predictions["score_basis"].astype(str).eq("current_grid_operational_pooled")].copy()
    merged = stored.merge(
        rebuilt[["origin", "target_period", "horizon", "hpo_outer_pred"]],
        on=["origin", "target_period", "horizon"],
        how="left",
    )
    return _assert_delta_within_tolerance(merged["component_pred"], merged["hpo_outer_pred"], tolerance, OUTER_COMPONENT_MODEL)


def _assert_delta_within_tolerance(actual: Any, pred: Any, tolerance: float, label: str) -> float:
    pair = pd.DataFrame({"actual": pd.to_numeric(pd.Series(actual), errors="coerce"), "pred": pd.to_numeric(pd.Series(pred), errors="coerce")})
    if pair["pred"].isna().any():
        raise AssertionError(f"Replay missing stored validation rows for {label}")
    delta = (pair["actual"] - pair["pred"]).abs()
    max_delta = float(delta.max())
    if max_delta > tolerance:
        raise AssertionError(f"PED replay failed for {label}: max_abs_delta={max_delta:.12g}, tolerance={tolerance:.12g}")
    return max_delta


def _weighted_validation_predictions(replay: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    data = replay[replay["component_model"].astype(str).isin(weights)].copy()
    data["weight"] = data["component_model"].map(weights)
    data["weighted_pred"] = data["component_pred"] * data["weight"]
    return (
        data.groupby(["origin", "target_period", "horizon"], as_index=False)["weighted_pred"]
        .sum()
        .rename(columns={"weighted_pred": "static_solver_pred"})
    )


def _preq_validation_predictions(replay: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    data = replay.merge(weights, on=["origin", "component_model"], how="inner")
    data["weighted_pred"] = data["component_pred"] * data["weight"]
    return (
        data.groupby(["origin", "target_period", "horizon"], as_index=False)["weighted_pred"]
        .sum()
        .rename(columns={"weighted_pred": "preq_solver_pred"})
    )


def _hpo_validation_predictions(
    replay: pd.DataFrame,
    static_rebuilt: pd.DataFrame,
    preq_rebuilt: pd.DataFrame,
    hpo_weights: dict[str, float],
) -> pd.DataFrame:
    direct = replay[replay["component_model"].astype(str).eq(DIRECT_HPO_COMPONENT)][
        ["origin", "target_period", "horizon", "component_pred"]
    ].rename(columns={"component_pred": "direct_component_pred"})
    merged = static_rebuilt.merge(preq_rebuilt, on=["origin", "target_period", "horizon"], how="inner").merge(
        direct, on=["origin", "target_period", "horizon"], how="inner"
    )
    merged["hpo_outer_pred"] = (
        merged["static_solver_pred"] * hpo_weights[STATIC_SOLVER_MODEL]
        + merged["preq_solver_pred"] * hpo_weights[PREQ_SOLVER_MODEL]
        + merged["direct_component_pred"] * hpo_weights[DIRECT_HPO_COMPONENT]
    )
    return merged[["origin", "target_period", "horizon", "hpo_outer_pred"]]


def _score_basis_origins(component_predictions: pd.DataFrame) -> dict[str, list[str]]:
    return {
        str(score_basis): sorted(group["origin"].dropna().astype(str).unique(), key=_origin_sort_key)
        for score_basis, group in component_predictions.groupby("score_basis", dropna=False)
    }


def _component_training_rows(
    module: Any,
    stream_data: Any,
    configs: dict[str, Any],
    score_basis_origins: dict[str, list[str]],
    source_script: Path,
    evidence: ReplayEvidence,
) -> pd.DataFrame:
    periods = module.valid_periods(stream_data)
    period_lookup = {str(period): period for period in periods}
    cache: dict[tuple[str, str], pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for component_model, cfg in sorted(configs.items()):
        feature_names = module.feature_names_for_set(stream_data, cfg.feature_set, cfg.include_target_lags)
        feature_names = [name for name in feature_names if name in stream_data.exog.columns or name.startswith("target__")]
        if not feature_names:
            raise AssertionError(f"No feature names resolved for {component_model}")
        for score_basis, origins in score_basis_origins.items():
            for origin_text in origins:
                cache_key = (component_model, origin_text)
                fitted = cache.get(cache_key)
                if fitted is None:
                    fitted = _fit_component_for_origin(module, stream_data, cfg, feature_names, periods, period_lookup, origin_text)
                    cache[cache_key] = fitted
                for _, row in fitted.iterrows():
                    rows.append(
                        {
                            "stream": STREAM,
                            "stream_label": STREAM_LABEL,
                            "model": FINALIST_MODEL,
                            "component_model": component_model,
                            "component_label": _component_label(component_model),
                            "component_weight": pd.NA,
                            "score_basis": score_basis,
                            "origin": origin_text,
                            "training_period": row["training_period"],
                            "window_start": row["window_start"],
                            "window_end": row["window_end"],
                            "training_fit_stage": component_model,
                            "actual": float(row["actual"]),
                            "training_fit_pred": float(row["training_fit_pred"]),
                            "data_scope": TRAINING_SCOPE,
                            "sample_role": "training",
                            "source_file": source_script.name,
                            "source_column": "actual;training_fit_pred",
                            "source_replay_max_abs_delta": evidence.direct_component_max_delta
                            if component_model == DIRECT_HPO_COMPONENT
                            else pd.NA,
                        }
                    )
    return pd.DataFrame(rows)


def _fit_component_for_origin(
    module: Any,
    stream_data: Any,
    cfg: Any,
    feature_names: list[str],
    periods: list[Any],
    period_lookup: dict[str, Any],
    origin_text: str,
) -> pd.DataFrame:
    if origin_text not in period_lookup:
        raise AssertionError(f"Origin not found in PED workbook periods: {origin_text}")
    origin = period_lookup[origin_text]
    train_periods = [period for period in periods if module.period_sort_value(period) <= module.period_sort_value(origin)]
    if cfg.window is not None:
        train_periods = train_periods[-int(cfg.window) :]
    X, y = module.build_training_matrix(stream_data, train_periods, feature_names, cfg.include_target_lags)
    mask = y.notna()
    X, y = X.loc[mask], y.loc[mask]
    if len(X) < max(20, int(cfg.min_train_quarters * 0.60)):
        raise AssertionError(f"Insufficient training rows for {cfg.name} at {origin_text}")
    all_na_cols = [column for column in X.columns if X[column].isna().all()]
    if all_na_cols:
        X = X.copy()
        X[all_na_cols] = 0.0
    model = module.fit_model(cfg, X, y)
    fitted_log = np.asarray(model.predict(X), dtype=float)
    fitted_level = np.array([module.safe_exp(value) for value in fitted_log], dtype=float)
    return pd.DataFrame(
        {
            "training_period": [str(period) for period in X.index],
            "window_start": str(X.index.min()),
            "window_end": str(X.index.max()),
            "actual": stream_data.y_raw.reindex(X.index).astype(float).to_numpy(),
            "training_fit_pred": fitted_level,
        }
    )


def _weighted_training_rows(
    component_rows: pd.DataFrame,
    weights: dict[str, float],
    component_model: str,
    stage: str,
    label: str,
    replay_delta: float,
) -> pd.DataFrame:
    data = component_rows[component_rows["component_model"].astype(str).isin(weights)].copy()
    data["component_weight"] = data["component_model"].map(weights)
    rows: list[dict[str, Any]] = []
    for (score_basis, origin), group in data.groupby(["score_basis", "origin"], dropna=False):
        index_cols = ["training_period"]
        pred = group.pivot_table(index=index_cols, columns="component_model", values="training_fit_pred", aggfunc="first")
        common = pred.reindex(columns=list(weights)).dropna(axis=0, how="any")
        if common.empty:
            continue
        actual = group.groupby(index_cols, dropna=False)["actual"].first().reindex(common.index)
        windows = group.groupby(index_cols, dropna=False).agg(window_start=("window_start", "max"), window_end=("window_end", "min")).reindex(common.index)
        weighted = common.mul(pd.Series(weights), axis=1).sum(axis=1)
        for training_period, pred_value in weighted.items():
            rows.append(
                _aggregate_row(
                    score_basis,
                    origin,
                    training_period,
                    actual.loc[training_period],
                    pred_value,
                    windows.loc[training_period, "window_start"],
                    windows.loc[training_period, "window_end"],
                    component_model,
                    label,
                    stage,
                    replay_delta,
                    "weighted fitted rows from exact source components",
                )
            )
    return pd.DataFrame(rows)


def _preq_training_rows(component_rows: pd.DataFrame, weights: pd.DataFrame, replay_delta: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (score_basis, origin), group in component_rows.groupby(["score_basis", "origin"], dropna=False):
        origin_weights = weights[weights["origin"].astype(str).eq(str(origin))]
        if origin_weights.empty:
            continue
        weight_map = {str(row["component_model"]): float(row["weight"]) for _, row in origin_weights.iterrows()}
        weighted = _weighted_training_rows(
            group,
            weight_map,
            PREQ_SOLVER_MODEL,
            "preq_convex_top18_fitted",
            "preq_convex_mape",
            replay_delta,
        )
        rows.extend(weighted.to_dict("records"))
    return pd.DataFrame(rows)


def _hpo_training_rows(
    base_rows: pd.DataFrame,
    static_rows: pd.DataFrame,
    preq_rows: pd.DataFrame,
    weights: dict[str, float],
    replay_delta: float,
) -> pd.DataFrame:
    direct = base_rows[base_rows["component_model"].astype(str).eq(DIRECT_HPO_COMPONENT)].copy()
    direct["component_model"] = DIRECT_HPO_COMPONENT
    pieces = [
        static_rows.assign(component_model=STATIC_SOLVER_MODEL),
        preq_rows.assign(component_model=PREQ_SOLVER_MODEL),
        direct,
    ]
    hpo_components = pd.concat(pieces, ignore_index=True, sort=False)
    return _weighted_training_rows(
        hpo_components,
        weights,
        OUTER_COMPONENT_MODEL,
        "outer_component_fitted",
        "outer_hpo_refine_component",
        replay_delta,
    )


def _final_training_rows(outer_rows: pd.DataFrame) -> pd.DataFrame:
    if outer_rows.empty:
        return pd.DataFrame(columns=outer_rows.columns)
    final = outer_rows.copy()
    final["component_model"] = FINALIST_MODEL
    final["component_label"] = "final_ped_hpo_refine"
    final["training_fit_stage"] = "hpo_refine_final_fitted"
    final["component_weight"] = 1.0
    final["calculation_basis"] = "PED finalist is 100 percent of the verified outer HPO component fitted rows."
    return final


def _aggregate_row(
    score_basis: str,
    origin: str,
    training_period: str,
    actual: Any,
    pred: Any,
    window_start: str,
    window_end: str,
    component_model: str,
    component_label: str,
    stage: str,
    replay_delta: float,
    calculation_basis: str,
) -> dict[str, Any]:
    return {
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "model": FINALIST_MODEL,
        "component_model": component_model,
        "component_label": component_label,
        "component_weight": 1.0,
        "score_basis": score_basis,
        "origin": str(origin),
        "training_period": str(training_period),
        "window_start": str(window_start),
        "window_end": str(window_end),
        "training_fit_stage": stage,
        "actual": float(actual),
        "training_fit_pred": float(pred),
        "data_scope": TRAINING_SCOPE,
        "sample_role": "training",
        "source_file": "stage1_finalist_arbitration.py;ensemble_weights.csv;hpo_refined_ensemble_weights.csv",
        "source_column": "actual;training_fit_pred",
        "source_replay_max_abs_delta": replay_delta,
        "calculation_basis": calculation_basis,
    }


def _component_label(component_model: str) -> str:
    if component_model == DIRECT_HPO_COMPONENT:
        return "direct_hpo_diff_gbr"
    if "GBRLocal" in component_model:
        return "preq_or_static_gbrlocal"
    if "__struct__" in component_model:
        return "preq_or_static_struct_gbr"
    return "preq_diff_gbr"


def _origin_sort_key(value: str) -> tuple[int, str]:
    try:
        period = pd.Period(value, freq="Q")
        return (period.year * 4 + period.quarter, value)
    except Exception:
        return (0, value)


if __name__ == "__main__":
    main()

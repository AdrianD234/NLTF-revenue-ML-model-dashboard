from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STREAM = "HEAVY_RUC"
STREAM_LABEL = "Heavy RUC volume"
FINALIST_MODEL = "HEAVY_RUC__RECON_STATIC_REBUILT"
TRAINING_SCOPE = "training_window_fitted_rows"
DEFAULT_SOURCE_SCRIPT = Path.home() / "Downloads" / "heavy_ruc_fullgrid_rescue_closure.py"
DEFAULT_REPRO_ROOT = Path("data/dashboard_evidence_pack_reproducibility/heavy_ruc")
DEFAULT_OUTPUT = DEFAULT_REPRO_ROOT / "training_fit_predictions.parquet"


@dataclass(frozen=True)
class ComponentSpec:
    component_label: str
    component_model: str
    component_weight: float
    model_kind: str
    feature_set: str
    family_tag: str
    include_target_lags: bool
    window: int
    hyperparameters_json: str


COMPONENTS = [
    ComponentSpec(
        component_label="C1",
        component_model="HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64",
        component_weight=0.469332,
        model_kind="elastic_net",
        feature_set="dynamic_no_leads",
        family_tag="Elastic",
        include_target_lags=True,
        window=64,
        hyperparameters_json=json.dumps({"alpha": 0.005, "l1_ratio": 0.2, "max_iter": 50000, "random_state": 42}, sort_keys=True),
    ),
    ComponentSpec(
        component_label="C2",
        component_model="HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64",
        component_weight=0.281844,
        model_kind="gbr",
        feature_set="schiff",
        family_tag="GBR",
        include_target_lags=False,
        window=64,
        hyperparameters_json=json.dumps(
            {
                "learning_rate": 0.06,
                "loss": "squared_error",
                "max_depth": 1,
                "n_estimators": 650,
                "random_state": 42,
                "subsample": 0.85,
            },
            sort_keys=True,
        ),
    ),
    ComponentSpec(
        component_label="C3",
        component_model="HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52",
        component_weight=0.144373,
        model_kind="gbr",
        feature_set="dynamic_no_leads",
        family_tag="GBR",
        include_target_lags=True,
        window=52,
        hyperparameters_json=json.dumps(
            {
                "learning_rate": 0.08,
                "loss": "squared_error",
                "max_depth": 1,
                "n_estimators": 400,
                "random_state": 42,
                "subsample": 0.85,
            },
            sort_keys=True,
        ),
    ),
    ComponentSpec(
        component_label="C4",
        component_model="HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40",
        component_weight=0.104451,
        model_kind="gbr",
        feature_set="dynamic_no_leads",
        family_tag="GBR",
        include_target_lags=True,
        window=40,
        hyperparameters_json=json.dumps(
            {
                "learning_rate": 0.08,
                "loss": "squared_error",
                "max_depth": 1,
                "n_estimators": 150,
                "random_state": 42,
                "subsample": 0.85,
            },
            sort_keys=True,
        ),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Heavy RUC fitted training rows for the R2 ladder.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-script", type=Path, default=DEFAULT_SOURCE_SCRIPT)
    parser.add_argument("--repro-root", type=Path, default=DEFAULT_REPRO_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replay-tolerance", type=float, default=1e-3)
    parser.add_argument("--skip-replay-validation", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    repro_root = _resolve(repo_root, args.repro_root)
    output = _resolve(repo_root, args.output)
    source = args.source_script
    if not source.exists():
        raise FileNotFoundError(f"Heavy RUC source script not found: {source}")

    module = _load_source_module(source)
    registry = pd.read_parquet(repro_root / "model_registry.parquet")
    component_predictions = pd.read_parquet(repro_root / "component_predictions.parquet")
    _assert_registry_matches(registry)

    workbook = Path(str(registry["source_workbook"].iloc[0]))
    stream_data = _build_stream_data(module, workbook)

    if not args.skip_replay_validation:
        replay_max_delta = _validate_component_replay(module, stream_data, component_predictions, args.replay_tolerance)
    else:
        replay_max_delta = np.nan

    score_basis_origins = _score_basis_origins(component_predictions)
    component_rows = _component_training_rows(module, stream_data, score_basis_origins, source, replay_max_delta)
    weighted_rows = _weighted_training_rows(component_rows)
    output_rows = pd.concat([component_rows, weighted_rows], ignore_index=True, sort=False)
    output_rows = output_rows.sort_values(
        ["score_basis", "origin", "training_period", "component_label", "training_fit_stage"],
        kind="stable",
    ).reset_index(drop=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    output_rows.to_parquet(output, index=False)
    print(f"Wrote {len(output_rows):,} Heavy RUC training-fit rows to {output}")
    print(f"Weighted ensemble rows: {len(weighted_rows):,}")
    if np.isfinite(replay_max_delta):
        print(f"Validation replay max abs delta: {replay_max_delta:.12g}")


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_source_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("heavy_ruc_fullgrid_rescue_closure_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import Heavy RUC source script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)
    return module


def _assert_registry_matches(registry: pd.DataFrame) -> None:
    expected = {spec.component_model: spec for spec in COMPONENTS}
    actual = set(registry["component_model"].astype(str))
    if actual != set(expected):
        raise AssertionError(f"Heavy RUC registry components changed: {sorted(actual)}")
    for _, row in registry.iterrows():
        spec = expected[str(row["component_model"])]
        if abs(float(row["component_weight"]) - spec.component_weight) > 1e-9:
            raise AssertionError(f"Component weight changed for {spec.component_model}")
        if str(row["model_kind"]) != spec.model_kind:
            raise AssertionError(f"Model kind changed for {spec.component_model}")
        if str(row["feature_set"]) != spec.feature_set:
            raise AssertionError(f"Feature set changed for {spec.component_model}")
        if str(row["include_target_lags"]).casefold() != str(spec.include_target_lags).casefold():
            raise AssertionError(f"Target-lag flag changed for {spec.component_model}")
        if int(row["window"]) != spec.window:
            raise AssertionError(f"Training window changed for {spec.component_model}")


def _build_stream_data(module: Any, workbook: Path) -> Any:
    df = module.load_input_sheet(workbook)
    target_col, target_is_log = module.detect_target_col(df, STREAM)
    feature_cols = module.detect_feature_cols(df, STREAM, [target_col])
    y_raw, y_log = module.build_target_series(df, target_col, target_is_log)
    exog, groups, primary_log = module.build_exog(df, STREAM, feature_cols)
    return module.StreamData(STREAM, target_col, target_is_log, feature_cols, y_raw, y_log, exog, groups, primary_log)


def _candidate_config(module: Any, spec: ComponentSpec) -> Any:
    return module.CandidateConfig(
        stream=STREAM,
        name=spec.component_model,
        model_kind=spec.model_kind,
        params_json=spec.hyperparameters_json,
        window=spec.window,
        feature_set=spec.feature_set,
        include_target_lags=spec.include_target_lags,
        family_tag=spec.family_tag,
    )


def _validate_component_replay(module: Any, stream_data: Any, stored: pd.DataFrame, tolerance: float) -> float:
    replay_frames = []
    for spec in COMPONENTS:
        cfg = _candidate_config(module, spec)
        frame = module.evaluate_candidate(stream_data, cfg)
        if frame.empty:
            raise AssertionError(f"No replay rows generated for {spec.component_model}")
        replay_frames.append(frame.rename(columns={"model": "component_model", "pred": "replay_pred"}))
    replay = pd.concat(replay_frames, ignore_index=True)
    keys = ["component_model", "origin", "target_period", "horizon"]
    merged = stored.merge(replay[keys + ["replay_pred"]], on=keys, how="left")
    if merged["replay_pred"].isna().any():
        missing = int(merged["replay_pred"].isna().sum())
        raise AssertionError(f"Component replay missing {missing} stored forecast rows")
    delta = (pd.to_numeric(merged["component_pred"], errors="coerce") - pd.to_numeric(merged["replay_pred"], errors="coerce")).abs()
    max_delta = float(delta.max())
    if max_delta > tolerance:
        raise AssertionError(
            "Heavy RUC component replay failed; fitted training rows would not be reproducible "
            f"under this runtime. max_abs_delta={max_delta:.12g}, tolerance={tolerance:.12g}"
        )
    return max_delta


def _score_basis_origins(component_predictions: pd.DataFrame) -> dict[tuple[str, str], set[str]]:
    result: dict[tuple[str, str], set[str]] = {}
    for (score_basis, component_model), group in component_predictions.groupby(["score_basis", "component_model"], dropna=False):
        result[(str(score_basis), str(component_model))] = set(group["origin"].dropna().astype(str))
    return result


def _component_training_rows(
    module: Any,
    stream_data: Any,
    score_basis_origins: dict[tuple[str, str], set[str]],
    source_script: Path,
    replay_max_delta: float,
) -> pd.DataFrame:
    periods = module.valid_periods(stream_data)
    period_lookup = {str(period): period for period in periods}
    rows: list[dict[str, Any]] = []
    for spec in COMPONENTS:
        cfg = _candidate_config(module, spec)
        feature_names = module.feature_names_for_set(stream_data, cfg.feature_set, cfg.include_target_lags)
        feature_names = [name for name in feature_names if name in stream_data.exog.columns or name.startswith("target__")]
        if not feature_names:
            raise AssertionError(f"No feature names resolved for {spec.component_model}")
        for score_basis, origins in _origins_for_component(score_basis_origins, spec.component_model).items():
            for origin_text in sorted(origins, key=lambda text: module.period_sort_value(period_lookup[text])):
                origin = period_lookup[origin_text]
                train_periods = [p for p in periods if module.period_sort_value(p) <= module.period_sort_value(origin)]
                train_periods = train_periods[-spec.window :]
                X, y = module.build_training_matrix(stream_data, train_periods, feature_names, cfg.include_target_lags)
                mask = y.notna()
                X, y = X.loc[mask], y.loc[mask]
                if len(X) < max(20, int(cfg.min_train_quarters * 0.60)):
                    raise AssertionError(f"Insufficient training rows for {spec.component_model} at {origin_text}")
                all_na_cols = [column for column in X.columns if X[column].isna().all()]
                if all_na_cols:
                    X = X.copy()
                    X[all_na_cols] = 0.0
                model = module.fit_model(cfg, X, y)
                fitted_log = _predict_training_log(model, X)
                fitted_level = np.array([module.safe_exp(value) for value in fitted_log], dtype=float)
                for period, actual, fitted in zip(X.index, stream_data.y_raw.reindex(X.index), fitted_level):
                    rows.append(
                        {
                            "stream": STREAM,
                            "stream_label": STREAM_LABEL,
                            "model": FINALIST_MODEL,
                            "component_model": spec.component_model,
                            "component_label": spec.component_label,
                            "component_weight": spec.component_weight,
                            "score_basis": score_basis,
                            "origin": origin_text,
                            "training_period": str(period),
                            "window_start": str(X.index.min()),
                            "window_end": str(X.index.max()),
                            "training_fit_stage": spec.component_model,
                            "actual": float(actual),
                            "training_fit_pred": float(fitted),
                            "data_scope": TRAINING_SCOPE,
                            "sample_role": "training",
                            "source_file": _source_label(source_script),
                            "source_replay_max_abs_delta": replay_max_delta,
                        }
                    )
    return pd.DataFrame(rows)


def _origins_for_component(score_basis_origins: dict[tuple[str, str], set[str]], component_model: str) -> dict[str, set[str]]:
    return {score_basis: origins for (score_basis, model), origins in score_basis_origins.items() if model == component_model}


def _predict_training_log(model: Any, X: pd.DataFrame) -> np.ndarray:
    if isinstance(model, dict) and model.get("kind") == "residual":
        return np.asarray(model["base"].predict(X) + model["resid"].predict(X), dtype=float)
    return np.asarray(model.predict(X), dtype=float)


def _weighted_training_rows(component_rows: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["score_basis", "origin", "training_period"]
    pred = component_rows.pivot_table(index=key_cols, columns="component_model", values="training_fit_pred", aggfunc="first")
    actual = component_rows.groupby(key_cols, dropna=False)["actual"].first()
    windows = component_rows.groupby(key_cols, dropna=False).agg(window_start=("window_start", "max"), window_end=("window_end", "min"))
    required = [spec.component_model for spec in COMPONENTS]
    common = pred.reindex(columns=required).dropna(axis=0, how="any")
    if common.empty:
        return pd.DataFrame(columns=component_rows.columns)
    weights = pd.Series({spec.component_model: spec.component_weight for spec in COMPONENTS})
    weighted = common.mul(weights, axis=1).sum(axis=1)
    out = pd.DataFrame(index=common.index)
    out["stream"] = STREAM
    out["stream_label"] = STREAM_LABEL
    out["model"] = FINALIST_MODEL
    out["component_model"] = "HEAVY_RUC__C1_C4_weighted_training_fit_ensemble"
    out["component_label"] = "weighted_ensemble_final"
    out["component_weight"] = 1.0
    out["window_start"] = windows.reindex(common.index)["window_start"].values
    out["window_end"] = windows.reindex(common.index)["window_end"].values
    out["training_fit_stage"] = "weighted_ensemble_final"
    out["actual"] = actual.reindex(common.index).values
    out["training_fit_pred"] = weighted.values
    out["data_scope"] = TRAINING_SCOPE
    out["sample_role"] = "training"
    out = out.reset_index()
    out["source_file"] = component_rows["source_file"].dropna().iloc[0] if component_rows["source_file"].notna().any() else "heavy_ruc_refit"
    out["source_replay_max_abs_delta"] = component_rows["source_replay_max_abs_delta"].dropna().max()
    return out[component_rows.columns]


def _source_label(path: Path) -> str:
    return path.name


if __name__ == "__main__":
    main()

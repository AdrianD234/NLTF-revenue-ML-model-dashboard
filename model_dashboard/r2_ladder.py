from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

R2_LADDER_DEP_FALLBACK_ENV = "NLTF_FORCE_R2_LADDER_DEP_FALLBACK"


def _force_dependency_fallback() -> bool:
    return os.environ.get(R2_LADDER_DEP_FALLBACK_ENV, "").strip().lower() in {"1", "true", "yes"}


try:
    if _force_dependency_fallback():
        raise ImportError(f"forced fallback via {R2_LADDER_DEP_FALLBACK_ENV}")
    from .r2_metrics import calibration_r2, forecast_r2, format_r2, reproducibility_component_r2_frame
except Exception as exc:
    R2_METRICS_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

    def _numeric_pair(actual: Iterable[Any], forecast: Iterable[Any]) -> pd.DataFrame:
        pair = pd.DataFrame(
            {
                "actual": pd.to_numeric(pd.Series(actual), errors="coerce"),
                "forecast": pd.to_numeric(pd.Series(forecast), errors="coerce"),
            }
        )
        return pair.dropna()

    def forecast_r2(actual: Iterable[Any], forecast: Iterable[Any]) -> float | pd.NA:
        pair = _numeric_pair(actual, forecast)
        if len(pair) < 2:
            return pd.NA
        sst = float(((pair["actual"] - pair["actual"].mean()) ** 2).sum())
        if sst <= 0:
            return pd.NA
        sse = float(((pair["actual"] - pair["forecast"]) ** 2).sum())
        return float(1 - (sse / sst))

    def calibration_r2(actual: Iterable[Any], forecast: Iterable[Any]) -> float | pd.NA:
        pair = _numeric_pair(actual, forecast)
        if len(pair) < 2:
            return pd.NA
        sst = float(((pair["actual"] - pair["actual"].mean()) ** 2).sum())
        forecast_sst = float(((pair["forecast"] - pair["forecast"].mean()) ** 2).sum())
        if sst <= 0 or forecast_sst <= 0:
            return pd.NA
        x = pair["forecast"]
        y = pair["actual"]
        slope = float(((x - x.mean()) * (y - y.mean())).sum() / forecast_sst)
        intercept = float(y.mean() - slope * x.mean())
        fitted = intercept + slope * x
        sse = float(((y - fitted) ** 2).sum())
        return float(1 - (sse / sst))

    def format_r2(value: Any) -> str:
        number = pd.to_numeric(value, errors="coerce")
        return "-" if pd.isna(number) else f"{float(number):.3f}"

    def reproducibility_component_r2_frame(repo_root: Path | str | None = None) -> pd.DataFrame:
        del repo_root
        return pd.DataFrame()
else:
    R2_METRICS_IMPORT_ERROR = None

try:
    if _force_dependency_fallback():
        raise ImportError(f"forced fallback via {R2_LADDER_DEP_FALLBACK_ENV}")
    from .score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS, score_basis_label
except Exception as exc:
    R2_SCORE_BASIS_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
    PAPER_SCORE_BASIS = "schiff_paper_horizon_mean"
    OPERATIONAL_SCORE_BASIS = "current_grid_operational_pooled"
    _FALLBACK_SCORE_BASIS_LABELS = {
        PAPER_SCORE_BASIS: "Paper-style horizon MAPE",
        OPERATIONAL_SCORE_BASIS: "Operational pooled MAPE",
    }

    def score_basis_label(value: Any) -> str:
        return _FALLBACK_SCORE_BASIS_LABELS.get(str(value), _FALLBACK_SCORE_BASIS_LABELS[PAPER_SCORE_BASIS])
else:
    R2_SCORE_BASIS_IMPORT_ERROR = None


R2_LADDER_TITLE = "R2 ladder: training fit vs calibration vs forecast R2"
R2_LADDER_NOTE = (
    "Training-fit R2 is not comparable to forecast R2. High paper-style R2 usually measures in-sample fit, "
    "while forecast R2 measures out-of-sample explanatory power after final model composition."
)
R2_TRAINING_FIT_NOTE = (
    "Training-fit R2 is computed from fitted rows inside the rolling training windows. "
    "It is not an out-of-sample forecast metric."
)

STREAM_ORDER = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
STREAM_TO_KEY = {
    "PED VKT per capita": "ped",
    "Light RUC volume": "light_ruc",
    "Heavy RUC volume": "heavy_ruc",
}
STREAM_TO_CODE = {
    "PED VKT per capita": "PED",
    "Light RUC volume": "LIGHT_RUC",
    "Heavy RUC volume": "HEAVY_RUC",
}
SCORE_BASIS_ORDER = [PAPER_SCORE_BASIS, OPERATIONAL_SCORE_BASIS]

TRAINING_SCOPE = "training_window_fitted_rows"
TRAINING_MISSING_SCOPE = "training_window_fitted_rows_missing"
COMPONENT_SCOPE = "out_of_sample_component_prediction_rows"
FORECAST_SCOPE = "out_of_sample_final_prediction_rows"
CALIBRATION_SCOPE = "actual_on_forecast_validation_regression"
SUMMARY_SCOPE = "mixed_training_calibration_forecast_governance_ladder"

TRAINING_FIT_CANDIDATE_FILENAMES = [
    "training_fit_predictions.parquet",
    "training_fitted_predictions.parquet",
    "fitted_training_predictions.parquet",
    "training_fit_detail.parquet",
]

VALIDATION_FILE_TOKENS = {
    "component_predictions",
    "scorecard_predictions",
    "rebuilt_predictions",
    "evidence_prediction_comparison",
    "quarterly_predictions",
    "annual_predictions",
}


def r2_ladder_summary_frame(data: dict[str, pd.DataFrame], repo_root: Path | str | None = None) -> pd.DataFrame:
    return r2_ladder_frames(data, repo_root=repo_root)["summary"]


def r2_training_fit_detail_frame(data: dict[str, pd.DataFrame], repo_root: Path | str | None = None) -> pd.DataFrame:
    return r2_ladder_frames(data, repo_root=repo_root)["training_fit_detail"]


def r2_reproducibility_gap_register_frame(data: dict[str, pd.DataFrame], repo_root: Path | str | None = None) -> pd.DataFrame:
    return r2_ladder_frames(data, repo_root=repo_root)["gap_register"]


def r2_ladder_frames(data: dict[str, pd.DataFrame], repo_root: Path | str | None = None) -> dict[str, pd.DataFrame]:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    diagnostics = _diagnostics_summary(data)
    reproducibility = reproducibility_component_r2_frame(root)
    training_observed = _training_fit_rows_from_artifacts(root)
    component_detail = _component_validation_rows(reproducibility)
    missing_training = _missing_training_rows(root, diagnostics, reproducibility, training_observed)
    training_detail = pd.concat([training_observed, missing_training, component_detail], ignore_index=True, sort=False)
    gap_register = _gap_register_rows(root, training_observed, training_detail)
    summary = _summary_rows(diagnostics, reproducibility, training_detail, gap_register)
    return {
        "summary": _ordered(summary),
        "training_fit_detail": _ordered(training_detail),
        "gap_register": _ordered(gap_register),
    }


def _diagnostics_summary(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    scorecard = data.get("scorecard_predictions", pd.DataFrame())
    diagnostics = data.get("diagnostic_df", data.get("diagnostic", pd.DataFrame()))
    if scorecard is None or scorecard.empty or {"actual", "pred", "stream_label", "score_basis"}.difference(scorecard.columns):
        return pd.DataFrame()
    source = scorecard.copy()
    if "scenario" in source.columns:
        source = source[source["scenario"].astype(str).str.casefold().eq("finalist")].copy()
    if "valid_for_mape" in source.columns:
        source = source[source["valid_for_mape"].fillna(True).astype(bool)].copy()
    if source.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    group_cols = ["stream", "stream_label", "model", "score_basis"]
    for column in group_cols:
        if column not in source.columns:
            source[column] = pd.NA
    for keys, group in source.groupby(group_cols, dropna=False):
        stream, stream_label, model, score_basis = keys
        forecast_value = forecast_r2(group["actual"], group["pred"])
        calibration_value = _calibration_override(diagnostics, stream_label, score_basis)
        if pd.isna(pd.to_numeric(calibration_value, errors="coerce")):
            calibration_value = calibration_r2(group["actual"], group["pred"])
        rows.append(
            {
                "stream": stream,
                "stream_label": stream_label,
                "model": model,
                "score_basis": score_basis,
                "score_basis_label": score_basis_label(score_basis),
                "forecast_r2": forecast_value,
                "calibration_r2": calibration_value,
                "n_rows": int(len(group)),
                "source_prediction_column": "pred",
                "calibration_r2_source_column": _calibration_source_column(diagnostics),
                "r2_type": "forecast_and_calibration",
                "data_scope": CALIBRATION_SCOPE,
            }
        )
    return pd.DataFrame(rows)


def _training_fit_rows_from_artifacts(repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = repo_root / "data" / "dashboard_evidence_pack_reproducibility"
    if not base.exists():
        return pd.DataFrame()
    for stream_key in ["light_ruc", "heavy_ruc", "ped", "ped_inner_hpo"]:
        stream_root = base / stream_key
        for filename in TRAINING_FIT_CANDIDATE_FILENAMES:
            path = stream_root / filename
            if not path.exists() or _looks_like_validation_file(path):
                continue
            try:
                frame = _read_table(path)
            except Exception:
                continue
            rows.extend(_training_rows_from_frame(frame, path, stream_key))
    return pd.DataFrame(rows)


def _training_rows_from_frame(frame: pd.DataFrame, path: Path, stream_key: str) -> list[dict[str, Any]]:
    if frame is None or frame.empty or not _has_training_scope(frame, path):
        return []
    actual_col = _first_present(frame, ["training_actual", "actual_train", "actual", "y", "target", "actual_log"])
    pred_col = _first_present(
        frame,
        [
            "training_fit_pred",
            "fitted_training_pred",
            "fitted_pred",
            "training_pred",
            "train_pred",
            "fitted",
            "base_fit",
            "post_gbm_fit",
            "pred",
        ],
    )
    if actual_col is None or pred_col is None:
        return []
    data = frame.copy()
    data["stream_label"] = data.get("stream_label", _stream_label_from_key(stream_key))
    data["stream"] = data.get("stream", data["stream_label"].map(lambda value: STREAM_TO_CODE.get(str(value), stream_key.upper())))
    data["score_basis"] = data.get("score_basis", PAPER_SCORE_BASIS)
    data["score_basis_label"] = data["score_basis"].map(score_basis_label)
    data["model"] = data.get("model", data.get("finalist_model", _stream_label_from_key(stream_key)))
    data["component_model"] = data.get("component_model", data.get("inner_component_model", "training_fit_component"))
    data["component_label"] = data.get("component_label", data["component_model"])
    if "training_fit_stage" not in data.columns:
        data["training_fit_stage"] = data["component_model"].astype(str)
    group_cols = [
        "stream",
        "stream_label",
        "model",
        "component_model",
        "component_label",
        "training_fit_stage",
        "score_basis",
        "score_basis_label",
    ]
    rows: list[dict[str, Any]] = []
    for keys, group in data.groupby(group_cols, dropna=False):
        stream, stream_label, model, component_model, component_label, training_fit_stage, score_basis, basis_label = keys
        value = forecast_r2(group[actual_col], group[pred_col])
        n_rows = _usable_pair_count(group[actual_col], group[pred_col])
        rows.append(
            {
                "stream": stream,
                "stream_label": stream_label,
                "model": model,
                "component_model": component_model,
                "component_label": component_label,
                "training_fit_stage": training_fit_stage,
                "score_basis": score_basis,
                "score_basis_label": basis_label,
                "metric_name": "Training-fit R2",
                "metric_value": value,
                "metric_display": format_r2(value),
                "training_fit_r2": value,
                "component_r2": pd.NA,
                "r2_type": "training_fit",
                "data_scope": TRAINING_SCOPE,
                "n_rows": n_rows,
                "source_file": _relative_source_file(path),
                "source_column": f"{actual_col};{pred_col}",
                "source_prediction_column": pred_col,
                "source_actual_column": actual_col,
                "training_fit_r2_status": "available",
                "availability_status": "available",
                "value_available": pd.notna(pd.to_numeric(value, errors="coerce")),
                "interpretation": R2_TRAINING_FIT_NOTE,
                "calculation_basis": "Training-fit R2 computed as 1 - SSE/SST on fitted training rows only.",
                "notes": "This row is never computed from validation forecast rows.",
            }
        )
    return rows


def _missing_training_rows(
    repo_root: Path,
    diagnostics: pd.DataFrame,
    reproducibility: pd.DataFrame,
    observed: pd.DataFrame,
) -> pd.DataFrame:
    observed_keys = set()
    observed_stages_by_stream_basis: dict[tuple[str, str], set[str]] = {}
    if observed is not None and not observed.empty:
        observed_keys = {
            (str(row.get("stream_label")), str(row.get("score_basis")), str(row.get("training_fit_stage", row.get("component_model"))))
            for _, row in observed.iterrows()
        }
        for _, row in observed.iterrows():
            key = (str(row.get("stream_label")), str(row.get("score_basis")))
            observed_stages_by_stream_basis.setdefault(key, set()).add(str(row.get("training_fit_stage", row.get("component_model"))))
    rows: list[dict[str, Any]] = []
    score_bases = _score_bases(diagnostics, reproducibility)
    expected = _expected_training_components(repo_root)
    for stream_label, components in expected.items():
        stream_key = STREAM_TO_KEY[stream_label]
        for basis in score_bases:
            if stream_label == "PED VKT per capita" and _ped_final_training_stage_available(
                observed_stages_by_stream_basis.get((stream_label, str(basis)), set())
            ):
                continue
            for component_model, status, interpretation in components:
                if (stream_label, basis, component_model) in observed_keys:
                    continue
                rows.append(
                    {
                        "stream": STREAM_TO_CODE[stream_label],
                        "stream_label": stream_label,
                        "model": _finalist_model_for_stream(repo_root, stream_key, stream_label),
                        "component_model": component_model,
                        "training_fit_stage": component_model,
                        "score_basis": basis,
                        "score_basis_label": score_basis_label(basis),
                        "metric_name": "Training-fit R2 unavailable",
                        "metric_value": pd.NA,
                        "metric_display": "-",
                        "training_fit_r2": pd.NA,
                        "component_r2": pd.NA,
                        "r2_type": "training_fit",
                        "data_scope": TRAINING_MISSING_SCOPE,
                        "n_rows": 0,
                        "source_file": _training_source_file(repo_root, stream_key),
                        "source_column": "missing_fitted_training_rows",
                        "source_prediction_column": pd.NA,
                        "source_actual_column": pd.NA,
                        "training_fit_r2_status": status,
                        "availability_status": status,
                        "value_available": False,
                        "interpretation": interpretation,
                        "calculation_basis": "No training-fit R2 is calculated because fitted training-row predictions were not found.",
                        "notes": "Unavailable training-fit R2 is left blank rather than coerced to zero.",
                    }
                )
    return pd.DataFrame(rows)


def _component_validation_rows(reproducibility: pd.DataFrame) -> pd.DataFrame:
    if reproducibility is None or reproducibility.empty:
        return pd.DataFrame()
    data = reproducibility[reproducibility["metric_name"].astype(str).eq("Component R2")].copy()
    if data.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        value = row.get("forecast_r2")
        rows.append(
            {
                "stream": row.get("stream"),
                "stream_label": row.get("stream_label"),
                "model": row.get("model"),
                "component_model": row.get("component_model"),
                "component_rank": row.get("component_rank"),
                "score_basis": row.get("score_basis"),
                "score_basis_label": row.get("score_basis_label", score_basis_label(row.get("score_basis"))),
                "metric_name": "Component validation R2",
                "metric_value": value,
                "metric_display": format_r2(value),
                "training_fit_r2": pd.NA,
                "component_r2": value,
                "r2_type": "component_validation",
                "data_scope": COMPONENT_SCOPE,
                "n_rows": row.get("n_rows"),
                "sse": row.get("sse"),
                "sst": row.get("sst"),
                "bias_pct": row.get("bias_pct"),
                "mape": row.get("mape"),
                "source_file": row.get("source_file"),
                "source_column": row.get("source_prediction_column", "component_pred"),
                "source_prediction_column": row.get("source_prediction_column", "component_pred"),
                "training_fit_r2_status": "not_training_fit",
                "availability_status": "available",
                "value_available": pd.notna(pd.to_numeric(value, errors="coerce")),
                "interpretation": row.get("interpretation"),
                "calculation_basis": "Component validation R2 computed from stored out-of-sample component_pred rows.",
                "notes": "Component validation R2 is not training-fit R2.",
            }
        )
    return pd.DataFrame(rows)


def _summary_rows(
    diagnostics: pd.DataFrame,
    reproducibility: pd.DataFrame,
    detail: pd.DataFrame,
    gap_register: pd.DataFrame,
) -> pd.DataFrame:
    score_bases = _score_bases(diagnostics, reproducibility)
    final_rows = _final_forecast_rows(reproducibility)
    rows: list[dict[str, Any]] = []
    for stream_label in STREAM_ORDER:
        for basis in score_bases:
            training = _training_summary_value(detail, stream_label, basis)
            diagnostic = _lookup(diagnostics, stream_label, basis)
            final = _lookup(final_rows, stream_label, basis)
            forecast_value = _first_non_missing(final.get("forecast_r2"), diagnostic.get("forecast_r2"))
            calibration_value = diagnostic.get("calibration_r2")
            status = training.get("training_fit_r2_status") or _stream_missing_status(stream_label)
            availability = training.get("availability_status") or ("available" if training.get("value_available") else status)
            row = {
                "stream_label": stream_label,
                "stream": stream_label,
                "model": _first_non_missing(final.get("model"), diagnostic.get("model"), training.get("model")),
                "score_basis": basis,
                "score_basis_label": score_basis_label(basis),
                "training_fit_r2": training.get("training_fit_r2"),
                "calibration_r2": calibration_value,
                "forecast_r2": forecast_value,
                "n_rows": _first_non_missing(final.get("n_rows"), diagnostic.get("n_rows"), 0),
                "r2_type": "r2_ladder",
                "data_scope": SUMMARY_SCOPE,
                "training_fit_r2_status": status,
                "availability_status": availability,
                "source_prediction_column": _first_non_missing(final.get("source_prediction_column"), diagnostic.get("source_prediction_column")),
                "calibration_r2_source_column": diagnostic.get("calibration_r2_source_column"),
                "metric_name": "R2 ladder summary",
                "metric_value": forecast_value,
                "metric_display": format_r2(forecast_value),
                "value_available": pd.notna(pd.to_numeric(forecast_value, errors="coerce")),
                "interpretation": _summary_interpretation(stream_label, status, forecast_value, calibration_value),
                "calculation_basis": "Training-fit, calibration and forecast R2 are reported as separate governance ladder measures.",
                "notes": f"{R2_TRAINING_FIT_NOTE} {R2_LADDER_NOTE}",
            }
            if stream_label == "PED VKT per capita":
                ped_status = _ped_inner_hpo_status(gap_register)
                row.update(ped_status)
            if training.get("training_fit_stage") is not None:
                row["training_fit_stage"] = training.get("training_fit_stage")
            rows.append(row)
    return pd.DataFrame(rows)


def _gap_register_rows(repo_root: Path, observed: pd.DataFrame, detail: pd.DataFrame) -> pd.DataFrame:
    observed_stage_keys = set()
    observed_stages_by_stream_basis: dict[tuple[str, str], set[str]] = {}
    if observed is not None and not observed.empty:
        observed_stage_keys = {
            (str(row.get("stream_label")), str(row.get("score_basis")), str(row.get("training_fit_stage", row.get("component_model"))))
            for _, row in observed.iterrows()
        }
        for _, row in observed.iterrows():
            key = (str(row.get("stream_label")), str(row.get("score_basis")))
            observed_stages_by_stream_basis.setdefault(key, set()).add(str(row.get("training_fit_stage", row.get("component_model"))))
    rows: list[dict[str, Any]] = []
    expected_gaps = [
        (
            "light_ruc_base_ols_training_fit_rows_missing",
            "Light RUC volume",
            "base_ols",
            "medium",
            "fitted_training_rows_missing",
            "The Light RUC pack contains OLS coefficients and training-window metadata, but no OLS fitted training-row predictions.",
        ),
        (
            "light_ruc_post_gbm_training_fit_rows_missing",
            "Light RUC volume",
            "post_gbm_final",
            "medium",
            "fitted_training_rows_missing",
            "The Light RUC pack contains rebuilt out-of-sample final_pred rows, but no in-sample post-GBM corrected fitted rows.",
        ),
        (
            "ped_inner_hpo_training_fit_registry_missing",
            "PED VKT per capita",
            "PED inner HPO/static-convex components",
            "medium",
            "inner_hpo_registry_missing",
            "PED inner HPO weights and nested replay are available where present, but fitted inner-component training rows were not retained.",
        ),
    ]
    score_bases = sorted(set(detail.get("score_basis", pd.Series(SCORE_BASIS_ORDER)).dropna().astype(str)), key=_basis_sort_key)
    for basis in score_bases:
        heavy_gap = _heavy_training_gap(repo_root, observed_stages_by_stream_basis, basis)
        if heavy_gap is not None:
            rows.append(heavy_gap)
        for gap_id, stream_label, component, severity, status, detail_text in expected_gaps:
            if stream_label == "PED VKT per capita" and _ped_final_training_stage_available(
                observed_stages_by_stream_basis.get((stream_label, str(basis)), set())
            ):
                continue
            if (stream_label, basis, component) in observed_stage_keys:
                continue
            rows.append(
                {
                    "gap_id": gap_id,
                    "stream": STREAM_TO_CODE[stream_label],
                    "stream_label": stream_label,
                    "model": _first_non_missing(_finalist_model_for_stream(repo_root, STREAM_TO_KEY[stream_label], stream_label), stream_label),
                    "component_model": component,
                    "training_fit_stage": component,
                    "score_basis": basis,
                    "score_basis_label": score_basis_label(basis),
                    "r2_type": "training_fit",
                    "data_scope": TRAINING_MISSING_SCOPE,
                    "training_fit_r2_status": status,
                    "availability_status": status,
                    "gap_status": "open_governance_gap",
                    "gap_severity": severity,
                    "gap_detail": detail_text,
                    "metric_name": "Training-fit R2 reproducibility gap",
                    "metric_value": pd.NA,
                    "metric_display": "-",
                    "source_file": _training_source_file(repo_root, STREAM_TO_KEY[stream_label]),
                    "source_column": "missing_fitted_training_rows",
                    "value_available": False,
                    "calculation_basis": "Gap register row; no R2 value is calculated without fitted training-row predictions.",
                    "notes": R2_LADDER_NOTE,
                }
            )
    rows.extend(_ped_inner_hpo_gap_rows(repo_root, score_bases, observed_stages_by_stream_basis))
    return pd.DataFrame(rows)


def _heavy_training_gap(repo_root: Path, observed_stages_by_stream_basis: dict[tuple[str, str], set[str]], basis: str) -> dict[str, Any] | None:
    stages = observed_stages_by_stream_basis.get(("Heavy RUC volume", str(basis)), set())
    if "weighted_ensemble_final" in stages:
        return None
    components = set(_model_registry_components(repo_root, "heavy_ruc"))
    if components and components.issubset(stages):
        gap_id = "heavy_ruc_final_ensemble_training_fit_rows_missing"
        component = "weighted_ensemble_final"
        status = "final_ensemble_training_missing"
        detail_text = (
            "Heavy RUC C1-C4 fitted training rows are available, but aligned weighted-ensemble fitted rows "
            "were not emitted."
        )
    else:
        gap_id = "heavy_ruc_c1_c4_training_fit_rows_missing"
        component = "C1-C4 weighted ensemble components"
        status = "partial_missing"
        detail_text = (
            "Heavy RUC final and component validation R2 are available, but parent C1-C4 fitted training rows "
            "were not emitted."
        )
    return {
        "gap_id": gap_id,
        "stream": "HEAVY_RUC",
        "stream_label": "Heavy RUC volume",
        "model": _first_non_missing(_finalist_model_for_stream(repo_root, "heavy_ruc", "Heavy RUC volume"), "Heavy RUC volume"),
        "component_model": component,
        "training_fit_stage": component,
        "score_basis": basis,
        "score_basis_label": score_basis_label(basis),
        "r2_type": "training_fit",
        "data_scope": TRAINING_MISSING_SCOPE,
        "training_fit_r2_status": status,
        "availability_status": status,
        "gap_status": "open_governance_gap",
        "gap_severity": "medium",
        "gap_detail": detail_text,
        "metric_name": "Training-fit R2 reproducibility gap",
        "metric_value": pd.NA,
        "metric_display": "-",
        "source_file": _training_source_file(repo_root, "heavy_ruc"),
        "source_column": "missing_fitted_training_rows",
        "value_available": False,
        "calculation_basis": "Gap register row; no final ensemble training-fit R2 is calculated without fitted training-row predictions.",
        "notes": R2_LADDER_NOTE,
    }


def _ped_inner_hpo_gap_rows(
    repo_root: Path,
    score_bases: list[str],
    observed_stages_by_stream_basis: dict[tuple[str, str], set[str]],
) -> list[dict[str, Any]]:
    base = repo_root / "data" / "dashboard_evidence_pack_reproducibility" / "ped_inner_hpo"
    gap_path = base / "reproducibility_gap_register.parquet"
    if not gap_path.exists():
        return []
    try:
        gaps = pd.read_parquet(gap_path)
    except Exception:
        return []
    weights_status = _row_count_status(base / "inner_hpo_weights.parquet")
    nested_status = _row_count_status(base / "nested_ensemble_trace.parquet")
    rows: list[dict[str, Any]] = []
    for basis in score_bases:
        final_available = _ped_final_training_stage_available(observed_stages_by_stream_basis.get(("PED VKT per capita", str(basis)), set()))
        for _, gap in gaps.iterrows():
            rows.append(
                {
                    "gap_id": gap.get("gap", "ped_inner_hpo_gap"),
                    "stream": "PED",
                    "stream_label": "PED VKT per capita",
                    "model": _finalist_model_for_stream(repo_root, "ped", "PED VKT per capita"),
                    "component_model": "PED__HPOREFINE_solver_static_convex_top18",
                    "score_basis": basis,
                    "score_basis_label": score_basis_label(basis),
                    "r2_type": "training_fit",
                    "data_scope": TRAINING_SCOPE if final_available else TRAINING_MISSING_SCOPE,
                    "training_fit_r2_status": "available" if final_available else "inner_hpo_registry_missing",
                    "availability_status": "available" if final_available else "inner_hpo_registry_missing",
                    "gap_status": "closed_by_ped_training_fit_export" if final_available else "open_governance_gap",
                    "gap_severity": gap.get("severity", "medium"),
                    "gap_detail": (
                        "The earlier inner-HPO fitted-state gap is closed for the governed PED finalist chain by "
                        "verified fitted rows in ped/training_fit_predictions.parquet."
                        if final_available
                        else gap.get("detail")
                    ),
                    "inner_hpo_weights_status": weights_status,
                    "nested_replay_status": nested_status,
                    "metric_name": "PED inner-HPO fitted-state gap closure" if final_available else "PED inner-HPO fitted-state gap",
                    "metric_value": pd.NA,
                    "metric_display": "-",
                    "source_file": _relative_source_file(gap_path),
                    "source_column": "gap;severity;detail",
                    "value_available": False,
                    "calculation_basis": (
                        "Gap register closure row; the R2 value is reported in the training-fit detail and summary tables."
                        if final_available
                        else "PED inner-HPO audit gap carried forward from the reproducibility pack."
                    ),
                    "notes": (
                        "Verified fitted rows supersede the prior missing fitted-state gap for the current finalist chain."
                        if final_available
                        else "Nested replay and weights do not prove training-fit R2 without fitted training rows."
                    ),
                }
            )
    return rows


def _expected_training_components(repo_root: Path) -> dict[str, list[tuple[str, str, str]]]:
    heavy_components = _model_registry_components(repo_root, "heavy_ruc")
    ped_components = _ped_inner_components(repo_root)
    return {
        "Light RUC volume": [
            (
                "base_ols",
                "fitted_training_rows_missing",
                "Light base OLS training-fit R2 requires fitted training rows, not validation component_pred rows.",
            ),
            (
                "post_gbm_final",
                "fitted_training_rows_missing",
                "Light post-GBM training-fit R2 requires in-sample corrected fitted rows; final_pred validation rows are not used.",
            ),
        ],
        "Heavy RUC volume": [
            (
                component,
                "partial_missing",
                "Heavy component validation R2 exists where component_pred is available, but component training-fit rows are missing.",
            )
            for component in heavy_components
        ],
        "PED VKT per capita": [
            (
                component,
                "inner_hpo_registry_missing",
                "PED inner-HPO replay weights are available where present, but inner component fitted training rows are missing.",
            )
            for component in ped_components
        ],
    }


def _model_registry_components(repo_root: Path, stream_key: str) -> list[str]:
    path = repo_root / "data" / "dashboard_evidence_pack_reproducibility" / stream_key / "model_registry.parquet"
    if not path.exists():
        return [f"{stream_key}_component_training_fit"]
    try:
        registry = pd.read_parquet(path)
    except Exception:
        return [f"{stream_key}_component_training_fit"]
    if "component_model" not in registry.columns:
        return [f"{stream_key}_component_training_fit"]
    values = registry["component_model"].dropna().astype(str).drop_duplicates().tolist()
    return values or [f"{stream_key}_component_training_fit"]


def _ped_inner_components(repo_root: Path) -> list[str]:
    path = repo_root / "data" / "dashboard_evidence_pack_reproducibility" / "ped_inner_hpo" / "inner_component_registry.parquet"
    if not path.exists():
        return ["PED inner HPO/static-convex components"]
    try:
        registry = pd.read_parquet(path)
    except Exception:
        return ["PED inner HPO/static-convex components"]
    if "component_model" not in registry.columns:
        return ["PED inner HPO/static-convex components"]
    values = registry["component_model"].dropna().astype(str).drop_duplicates().tolist()
    return values or ["PED inner HPO/static-convex components"]


def _final_forecast_rows(reproducibility: pd.DataFrame) -> pd.DataFrame:
    if reproducibility is None or reproducibility.empty:
        return pd.DataFrame()
    metric = reproducibility.get("metric_name", pd.Series(dtype=str)).astype(str)
    role = reproducibility.get("component_role", pd.Series(dtype=str)).astype(str)
    return reproducibility[metric.eq("Forecast R2") | role.eq("final_model_composition")].copy()


def _training_summary_value(detail: pd.DataFrame, stream_label: str, score_basis: str) -> dict[str, Any]:
    if detail is None or detail.empty:
        return {"training_fit_r2": pd.NA, "training_fit_r2_status": _stream_missing_status(stream_label), "value_available": False}
    subset = detail[
        detail["stream_label"].astype(str).eq(stream_label)
        & detail["score_basis"].astype(str).eq(str(score_basis))
        & detail["r2_type"].astype(str).eq("training_fit")
    ].copy()
    available = subset[subset["value_available"].fillna(False).astype(bool)] if "value_available" in subset.columns else pd.DataFrame()
    if not available.empty:
        preferred = available.copy()
        if stream_label == "Light RUC volume" and "training_fit_stage" in preferred.columns:
            post_gbm = preferred[preferred["training_fit_stage"].astype(str).eq("post_gbm_final")]
            if not post_gbm.empty:
                preferred = post_gbm
        if stream_label == "Heavy RUC volume" and "training_fit_stage" in preferred.columns:
            weighted = preferred[preferred["training_fit_stage"].astype(str).eq("weighted_ensemble_final")]
            if not weighted.empty:
                preferred = weighted
            else:
                return {
                    "training_fit_r2": pd.NA,
                    "training_fit_r2_status": "final_ensemble_training_missing",
                    "availability_status": "component_training_available",
                    "value_available": False,
                    "model": preferred["model"].dropna().iloc[0] if preferred["model"].notna().any() else pd.NA,
                    "training_fit_stage": "weighted_ensemble_final",
                }
        if stream_label == "PED VKT per capita" and "training_fit_stage" in preferred.columns:
            for stage in ["hpo_refine_final_fitted", "outer_component_fitted"]:
                stage_rows = preferred[preferred["training_fit_stage"].astype(str).eq(stage)]
                if not stage_rows.empty:
                    preferred = stage_rows
                    break
            else:
                return {
                    "training_fit_r2": pd.NA,
                    "training_fit_r2_status": "inner_hpo_registry_missing",
                    "availability_status": "component_training_available",
                    "value_available": False,
                    "model": preferred["model"].dropna().iloc[0] if preferred["model"].notna().any() else pd.NA,
                    "training_fit_stage": "hpo_refine_final_fitted",
                }
        values = pd.to_numeric(preferred["training_fit_r2"], errors="coerce").dropna()
        return {
            "training_fit_r2": float(values.mean()) if not values.empty else pd.NA,
            "training_fit_r2_status": "available",
            "availability_status": "available",
            "value_available": not values.empty,
            "model": preferred["model"].dropna().iloc[0] if preferred["model"].notna().any() else pd.NA,
            "training_fit_stage": preferred["training_fit_stage"].dropna().iloc[0]
            if "training_fit_stage" in preferred.columns and preferred["training_fit_stage"].notna().any()
            else pd.NA,
        }
    if not subset.empty:
        return {
            "training_fit_r2": pd.NA,
            "training_fit_r2_status": subset["training_fit_r2_status"].dropna().astype(str).iloc[0],
            "availability_status": subset["availability_status"].dropna().astype(str).iloc[0]
            if "availability_status" in subset.columns and subset["availability_status"].notna().any()
            else subset["training_fit_r2_status"].dropna().astype(str).iloc[0],
            "value_available": False,
            "model": subset["model"].dropna().iloc[0] if subset["model"].notna().any() else pd.NA,
        }
    return {"training_fit_r2": pd.NA, "training_fit_r2_status": _stream_missing_status(stream_label), "value_available": False}


def _lookup(frame: pd.DataFrame, stream_label: str, score_basis: str) -> dict[str, Any]:
    if frame is None or frame.empty or {"stream_label", "score_basis"}.difference(frame.columns):
        return {}
    subset = frame[frame["stream_label"].astype(str).eq(stream_label) & frame["score_basis"].astype(str).eq(str(score_basis))]
    if subset.empty:
        return {}
    return subset.iloc[0].to_dict()


def _summary_interpretation(stream_label: str, status: str, forecast_value: Any, calibration_value: Any) -> str:
    forecast_display = format_r2(forecast_value)
    calibration_display = format_r2(calibration_value)
    if status == "available":
        return f"Training-fit R2 is available; forecast R2 {forecast_display} and calibration R2 {calibration_display} remain out-of-sample measures."
    if stream_label == "Heavy RUC volume" and status == "final_ensemble_training_missing":
        return f"Component training-fit rows are available, but the weighted final ensemble training-fit R2 is missing; forecast R2 {forecast_display} remains out-of-sample."
    if stream_label == "Light RUC volume":
        return f"Forecast R2 {forecast_display} and calibration R2 {calibration_display} are available; base/post-GBM fitted training rows were not emitted."
    if stream_label == "Heavy RUC volume":
        return f"Forecast R2 {forecast_display} and component validation R2 are available; C1-C4 fitted training rows are partial/missing."
    return f"Forecast R2 {forecast_display} and calibration R2 {calibration_display} are available; PED inner-HPO fitted training registry is missing."


def _stream_missing_status(stream_label: str) -> str:
    if stream_label == "Heavy RUC volume":
        return "partial_missing"
    if stream_label == "PED VKT per capita":
        return "inner_hpo_registry_missing"
    return "fitted_training_rows_missing"


def _ped_final_training_stage_available(stages: set[str]) -> bool:
    return bool({"hpo_refine_final_fitted", "outer_component_fitted"}.intersection(stages))


def _ped_inner_hpo_status(gap_register: pd.DataFrame) -> dict[str, str]:
    ped = gap_register[gap_register["stream_label"].astype(str).eq("PED VKT per capita")] if gap_register is not None and not gap_register.empty else pd.DataFrame()
    return {
        "inner_hpo_weights_status": ped["inner_hpo_weights_status"].dropna().iloc[0] if not ped.empty and ped["inner_hpo_weights_status"].notna().any() else "not_available",
        "nested_replay_status": ped["nested_replay_status"].dropna().iloc[0] if not ped.empty and ped["nested_replay_status"].notna().any() else "not_available",
    }


def _calibration_override(diagnostics: pd.DataFrame, stream_label: Any, score_basis: Any) -> Any:
    if diagnostics is None or diagnostics.empty or "stream_label" not in diagnostics.columns:
        return pd.NA
    calibration_col = _calibration_source_column(diagnostics)
    if not calibration_col:
        return pd.NA
    data = diagnostics.copy()
    if "role" in data.columns:
        data = data[data["role"].astype(str).str.contains("finalist", case=False, na=False)]
    data["default_score_basis"] = data.get("default_score_basis", PAPER_SCORE_BASIS)
    match = data[data["stream_label"].astype(str).eq(str(stream_label)) & data["default_score_basis"].astype(str).eq(str(score_basis))]
    if match.empty:
        return pd.NA
    return pd.to_numeric(match.iloc[0].get(calibration_col), errors="coerce")


def _calibration_source_column(diagnostics: pd.DataFrame) -> str:
    if diagnostics is None or diagnostics.empty:
        return "pred"
    return _first_present(diagnostics, ["calibration_r2", "mz_r2", "adj_r2"]) or "pred"


def _score_bases(diagnostics: pd.DataFrame, reproducibility: pd.DataFrame) -> list[str]:
    values: set[str] = set(SCORE_BASIS_ORDER)
    for frame in [diagnostics, reproducibility]:
        if frame is not None and not frame.empty and "score_basis" in frame.columns:
            values.update(frame["score_basis"].dropna().astype(str))
    return sorted(values, key=_basis_sort_key)


def _basis_sort_key(value: str) -> tuple[int, str]:
    try:
        return (SCORE_BASIS_ORDER.index(value), value)
    except ValueError:
        return (len(SCORE_BASIS_ORDER), value)


def _finalist_model_for_stream(repo_root: Path, stream_key: str, stream_label: str) -> str:
    path = repo_root / "data" / "dashboard_evidence_pack_reproducibility" / stream_key / "model_registry.parquet"
    if path.exists():
        try:
            registry = pd.read_parquet(path)
            for column in ["finalist_model", "model"]:
                if column in registry.columns:
                    values = registry[column].dropna().astype(str)
                    if not values.empty:
                        return values.iloc[0]
        except Exception:
            pass
    return stream_label


def _training_source_file(repo_root: Path, stream_key: str) -> str:
    base = repo_root / "data" / "dashboard_evidence_pack_reproducibility" / stream_key
    candidates = [base / "training_window_trace.parquet", base / "model_registry.parquet"]
    return ";".join(_relative_source_file(path) for path in candidates if path.exists()) or _relative_source_file(base)


def _row_count_status(path: Path) -> str:
    if not path.exists():
        return "not_available"
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return "read_error"
    return f"available_{len(frame)}_rows" if not frame.empty else "empty"


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def _has_training_scope(frame: pd.DataFrame, path: Path) -> bool:
    if _looks_like_validation_file(path):
        return False
    scope_columns = ["data_scope", "sample_role", "row_scope", "split", "scope"]
    for column in scope_columns:
        if column in frame.columns:
            values = frame[column].dropna().astype(str).str.casefold()
            if values.str.contains("validation|forecast|out_of_sample|test", regex=True).any():
                return False
            if values.str.contains("train|fitted|in_sample", regex=True).any():
                return True
    if "is_training" in frame.columns:
        return frame["is_training"].fillna(False).astype(bool).any()
    name = path.stem.casefold()
    return "training" in name and "fit" in name


def _looks_like_validation_file(path: Path) -> bool:
    name = path.stem.casefold()
    return any(token in name for token in VALIDATION_FILE_TOKENS)


def _usable_pair_count(actual: Any, forecast: Any) -> int:
    pair = pd.DataFrame(
        {
            "actual": pd.to_numeric(pd.Series(actual), errors="coerce"),
            "forecast": pd.to_numeric(pd.Series(forecast), errors="coerce"),
        }
    ).dropna()
    return int(len(pair))


def _first_present(frame: pd.DataFrame, columns: list[str]) -> str | None:
    return next((column for column in columns if column in frame.columns), None)


def _first_non_missing(*values: Any) -> Any:
    for value in values:
        if pd.notna(pd.to_numeric(value, errors="coerce")) if isinstance(value, (int, float)) else pd.notna(value):
            return value
    return pd.NA


def _stream_label_from_key(stream_key: str) -> str:
    return {
        "ped": "PED VKT per capita",
        "ped_inner_hpo": "PED VKT per capita",
        "light_ruc": "Light RUC volume",
        "heavy_ruc": "Heavy RUC volume",
    }.get(stream_key, stream_key.replace("_", " ").title())


def _relative_source_file(path: Path) -> str:
    parts = path.parts
    if "data" in parts:
        return str(Path(*parts[parts.index("data") :])).replace("\\", "/")
    return str(path).replace("\\", "/")


def _ordered(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    preferred = [
        "stream",
        "stream_label",
        "model",
        "component_model",
        "component_label",
        "training_fit_stage",
        "score_basis",
        "score_basis_label",
        "r2_type",
        "data_scope",
        "training_fit_r2",
        "calibration_r2",
        "forecast_r2",
        "component_r2",
        "n_rows",
        "availability_status",
        "training_fit_r2_status",
        "inner_hpo_weights_status",
        "nested_replay_status",
        "metric_name",
        "metric_value",
        "metric_display",
        "source_file",
        "source_column",
        "source_prediction_column",
        "calibration_r2_source_column",
        "interpretation",
        "calculation_basis",
        "notes",
    ]
    present = [column for column in preferred if column in frame.columns]
    rest = [column for column in frame.columns if column not in present]
    return frame[present + rest].sort_values(
        [column for column in ["stream_label", "score_basis", "r2_type", "component_model"] if column in frame.columns],
        kind="stable",
    ).reset_index(drop=True)


__all__ = [
    "R2_LADDER_NOTE",
    "R2_LADDER_TITLE",
    "R2_TRAINING_FIT_NOTE",
    "r2_ladder_frames",
    "r2_ladder_summary_frame",
    "r2_reproducibility_gap_register_frame",
    "r2_training_fit_detail_frame",
]

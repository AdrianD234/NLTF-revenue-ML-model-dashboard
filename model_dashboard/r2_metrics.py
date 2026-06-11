from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .score_basis import PAPER_SCORE_BASIS, score_basis_label


R2_UNAVAILABLE_NOTE = "Unavailable: fewer than two usable rows or zero actual variance."


def forecast_r2(actual: Iterable[Any], forecast: Iterable[Any]) -> float | pd.NA:
    """Return net forecast R2: 1 - SSE/SST in native target units."""
    pair = _numeric_pair(actual, forecast)
    if len(pair) < 2:
        return pd.NA
    sst = _sst(pair["actual"])
    if not _positive(sst):
        return pd.NA
    sse = _sse(pair["actual"], pair["forecast"])
    return float(1 - (sse / sst))


def calibration_r2(actual: Iterable[Any], forecast: Iterable[Any]) -> float | pd.NA:
    """Return Mincer-Zarnowitz R2 from actual = a + b * forecast."""
    pair = _numeric_pair(actual, forecast)
    if len(pair) < 2:
        return pd.NA
    sst = _sst(pair["actual"])
    forecast_sst = _sst(pair["forecast"])
    if not _positive(sst) or not _positive(forecast_sst):
        return pd.NA
    x = np.column_stack([np.ones(len(pair)), pair["forecast"].to_numpy(dtype=float)])
    y = pair["actual"].to_numpy(dtype=float)
    intercept, slope = np.linalg.lstsq(x, y, rcond=None)[0]
    fitted = intercept + slope * pair["forecast"].to_numpy(dtype=float)
    return float(1 - (_sse(pair["actual"], fitted) / sst))


def r2_metric_row(
    frame: pd.DataFrame,
    *,
    prediction_col: str,
    actual_col: str = "actual",
    valid_col: str | None = None,
) -> dict[str, Any]:
    pair = _prediction_pair(frame, actual_col=actual_col, prediction_col=prediction_col, valid_col=valid_col)
    if pair.empty:
        return _empty_metric_row()
    sse = _sse(pair["actual"], pair["forecast"])
    sst = _sst(pair["actual"])
    return {
        "forecast_r2": forecast_r2(pair["actual"], pair["forecast"]),
        "calibration_r2": calibration_r2(pair["actual"], pair["forecast"]),
        "n_rows": int(len(pair)),
        "sse": float(sse),
        "sst": float(sst),
        "bias_pct": _bias_pct(pair),
        "mape": _mape(pair),
    }


def grouped_r2_metrics(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    prediction_col: str,
    actual_col: str = "actual",
    valid_col: str | None = None,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    required = set(group_columns + [actual_col, prediction_col])
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for group_key, group in frame.groupby(group_columns, dropna=False):
        key_values = group_key if isinstance(group_key, tuple) else (group_key,)
        row = dict(zip(group_columns, key_values, strict=False))
        row.update(r2_metric_row(group, prediction_col=prediction_col, actual_col=actual_col, valid_col=valid_col))
        row["source_prediction_column"] = prediction_col
        rows.append(row)
    return pd.DataFrame(rows)


def diagnostics_r2_summary_frame(scorecard_predictions: pd.DataFrame, diagnostic_tests: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build the Diagnostics forecast/calibration R2 detail table from final scorecard predictions."""
    if scorecard_predictions is None or scorecard_predictions.empty:
        return pd.DataFrame()
    required = {"actual", "pred", "stream_label", "score_basis"}
    if not required.issubset(scorecard_predictions.columns):
        return pd.DataFrame()
    data = scorecard_predictions.copy()
    if "scenario" in data.columns:
        data = data[data["scenario"].astype(str).str.casefold().eq("finalist")].copy()
    if "valid_for_mape" in data.columns:
        valid = data["valid_for_mape"].fillna(True).astype(bool)
        data = data[valid].copy()
    if data.empty:
        return pd.DataFrame()
    for column in ["stream", "model", "model_short", "horizon_bucket", "eval_grid"]:
        if column not in data.columns:
            data[column] = pd.NA
    data["score_basis_label"] = data["score_basis"].map(score_basis_label)
    group_columns = ["stream", "stream_label", "model", "model_short", "score_basis", "score_basis_label"]
    metrics = grouped_r2_metrics(data, group_columns=group_columns, prediction_col="pred", valid_col=None)
    if metrics.empty:
        return metrics
    metrics = _apply_diagnostic_calibration_overrides(metrics, diagnostic_tests)
    metrics["interpretation"] = metrics["forecast_r2"].map(forecast_r2_interpretation)
    metrics["metric_name"] = "Forecast R2"
    return metrics.sort_values(["stream_label", "score_basis"]).reset_index(drop=True)


def reproducibility_component_r2_frame(repo_root: Path | str | None = None) -> pd.DataFrame:
    """Build final and component R2 rows from auxiliary reproducibility packs."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    base = root / "data" / "dashboard_evidence_pack_reproducibility"
    if not base.exists():
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    # Current-finalist packs only (legacy packs are archived lineage).
    from .governance_constants import CURRENT_REPRO_PACK_DIRS

    current_packs = tuple(CURRENT_REPRO_PACK_DIRS.values())
    for path in sorted(base.glob("*/component_predictions.parquet")):
        stream_key = path.parent.name
        if stream_key not in current_packs:
            continue
        try:
            component_predictions = pd.read_parquet(path)
        except Exception:
            continue
        rows.extend(_final_r2_rows(component_predictions, stream_key, path))
        rows.extend(_component_r2_rows(component_predictions, stream_key, path))
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["interpretation"] = frame["forecast_r2"].map(forecast_r2_interpretation)
    return frame.sort_values(["stream_label", "score_basis", "r2_type", "component_rank", "component_model"]).reset_index(drop=True)


def forecast_r2_interpretation(value: Any) -> str:
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value):
        return R2_UNAVAILABLE_NOTE
    number = float(value)
    if number < 0:
        return "Valid but poor fit: forecast underperforms the stream mean on these rows."
    if number < 0.5:
        return "Valid but weak net fit on these rows."
    if number < 0.8:
        return "Valid moderate net fit on these rows."
    return "Strong net fit on these rows."


def format_r2(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "-" if pd.isna(number) else f"{float(number):.3f}"


def _apply_diagnostic_calibration_overrides(metrics: pd.DataFrame, diagnostic_tests: pd.DataFrame | None) -> pd.DataFrame:
    out = metrics.copy()
    out["calibration_r2_source_column"] = "pred"
    if diagnostic_tests is None or diagnostic_tests.empty:
        return out
    calibration_col = _first_present(diagnostic_tests, ["calibration_r2", "mz_r2", "adj_r2"])
    if calibration_col is None or "stream_label" not in diagnostic_tests.columns:
        return out
    diagnostics = diagnostic_tests.copy()
    if "role" in diagnostics.columns:
        diagnostics = diagnostics[diagnostics["role"].astype(str).str.contains("finalist", case=False, na=False)]
    if diagnostics.empty:
        return out
    diagnostics["default_score_basis"] = diagnostics.get("default_score_basis", PAPER_SCORE_BASIS)
    lookup: dict[tuple[str, str], float] = {}
    for _, row in diagnostics.iterrows():
        value = pd.to_numeric(row.get(calibration_col), errors="coerce")
        if pd.isna(value):
            continue
        lookup[(str(row.get("stream_label")), str(row.get("default_score_basis") or PAPER_SCORE_BASIS))] = float(value)
    if not lookup:
        return out
    for idx, row in out.iterrows():
        key = (str(row.get("stream_label")), str(row.get("score_basis")))
        if key in lookup:
            out.at[idx, "calibration_r2"] = lookup[key]
            out.at[idx, "calibration_r2_source_column"] = calibration_col
    return out


def _final_r2_rows(frame: pd.DataFrame, stream_key: str, source_path: Path) -> list[dict[str, Any]]:
    final_col = _first_present(frame, ["final_pred", "rebuilt_pred", "evidence_pred"])
    if final_col is None:
        return []
    data = _with_common_columns(frame, stream_key).copy()
    if "valid_actual" in data.columns:
        data = data[data["valid_actual"].fillna(True).astype(bool)].copy()
    keys = [
        column
        for column in ["stream", "stream_label", "score_basis", "eval_grid", "grid", "origin", "target_period", "horizon"]
        if column in data.columns
    ]
    data = data.drop_duplicates(subset=keys, keep="last") if keys else data.drop_duplicates()
    if data.empty or {"actual", final_col}.difference(data.columns):
        return []
    group_columns = ["stream", "stream_label", "score_basis", "score_basis_label", "model"]
    metrics = grouped_r2_metrics(data, group_columns=group_columns, prediction_col=final_col)
    rows: list[dict[str, Any]] = []
    for _, row in metrics.iterrows():
        payload = row.to_dict()
        payload.update(
            {
                "metric_name": "Forecast R2",
                "r2_type": "forecast",
                "component_model": pd.NA,
                "component_role": "final_model_composition",
                "component_rank": pd.NA,
                "source_file": _relative_source_file(source_path),
                "source_prediction_column": final_col,
                "calculation_basis": "Forecast R2 computed as 1 - SSE/SST from final predictions after corrections or ensemble weights.",
            }
        )
        rows.append(payload)
    return rows


def _component_r2_rows(frame: pd.DataFrame, stream_key: str, source_path: Path) -> list[dict[str, Any]]:
    if {"actual", "component_pred", "component_model"}.difference(frame.columns):
        return []
    data = _with_common_columns(frame, stream_key).copy()
    if "valid_actual" in data.columns:
        data = data[data["valid_actual"].fillna(True).astype(bool)].copy()
    if data.empty:
        return []
    if stream_key == "light_ruc" and "component_role" in data.columns:
        role = data["component_role"].astype(str)
        data = data[role.isin(["base_level_prediction"])].copy()
    if stream_key == "ped":
        data = data[data["component_rank"].fillna(1).astype(float).eq(1)].copy() if "component_rank" in data.columns else data
    if data.empty:
        return []
    group_columns = ["stream", "stream_label", "score_basis", "score_basis_label", "model", "component_model", "component_role"]
    metrics = grouped_r2_metrics(data, group_columns=group_columns, prediction_col="component_pred")
    ranks = _component_ranks(data)
    rows: list[dict[str, Any]] = []
    for _, row in metrics.iterrows():
        payload = row.to_dict()
        component = str(row.get("component_model", ""))
        payload.update(
            {
                "metric_name": "Component R2",
                "r2_type": "component",
                "component_rank": ranks.get(component, pd.NA),
                "source_file": _relative_source_file(source_path),
                "source_prediction_column": "component_pred",
                "calculation_basis": "Component R2 computed as 1 - SSE/SST from stored component predictions where the component is in target units.",
            }
        )
        rows.append(payload)
    return rows


def _with_common_columns(frame: pd.DataFrame, stream_key: str) -> pd.DataFrame:
    data = frame.copy()
    if "stream_label" not in data.columns:
        data["stream_label"] = _stream_label_from_key(stream_key)
    if "stream" not in data.columns:
        data["stream"] = _stream_from_label(data["stream_label"].iloc[0] if not data.empty else _stream_label_from_key(stream_key))
    if "score_basis" not in data.columns:
        data["score_basis"] = PAPER_SCORE_BASIS
    if "score_basis_label" not in data.columns:
        data["score_basis_label"] = data["score_basis"].map(score_basis_label)
    model_col = _first_present(data, ["ensemble_model", "finalist_model", "model"])
    data["model"] = data[model_col] if model_col else _stream_label_from_key(stream_key)
    if "component_role" not in data.columns:
        data["component_role"] = "component_prediction"
    return data


def _component_ranks(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty or "component_model" not in frame.columns:
        return {}
    data = frame.copy()
    if "component_rank" in data.columns:
        rank_data = data[["component_model", "component_rank"]].dropna().drop_duplicates(subset=["component_model"])
        if not rank_data.empty:
            return {
                str(row["component_model"]): int(float(row["component_rank"]))
                for _, row in rank_data.iterrows()
                if pd.notna(pd.to_numeric(row["component_rank"], errors="coerce"))
            }
    if "component_weight" in data.columns:
        weights = (
            data.groupby("component_model", dropna=False)["component_weight"]
            .mean()
            .sort_values(ascending=False)
            .reset_index()
        )
        return {str(component): idx for idx, component in enumerate(weights["component_model"], start=1)}
    return {str(component): idx for idx, component in enumerate(data["component_model"].drop_duplicates(), start=1)}


def _prediction_pair(frame: pd.DataFrame, *, actual_col: str, prediction_col: str, valid_col: str | None = None) -> pd.DataFrame:
    if frame is None or frame.empty or {actual_col, prediction_col}.difference(frame.columns):
        return pd.DataFrame(columns=["actual", "forecast"])
    data = frame.copy()
    if valid_col and valid_col in data.columns:
        data = data[data[valid_col].fillna(True).astype(bool)].copy()
    return _numeric_pair(data[actual_col], data[prediction_col])


def _numeric_pair(actual: Iterable[Any], forecast: Iterable[Any]) -> pd.DataFrame:
    pair = pd.DataFrame(
        {
            "actual": pd.to_numeric(pd.Series(actual), errors="coerce"),
            "forecast": pd.to_numeric(pd.Series(forecast), errors="coerce"),
        }
    )
    return pair.dropna(subset=["actual", "forecast"]).reset_index(drop=True)


def _empty_metric_row() -> dict[str, Any]:
    return {
        "forecast_r2": pd.NA,
        "calibration_r2": pd.NA,
        "n_rows": 0,
        "sse": pd.NA,
        "sst": pd.NA,
        "bias_pct": pd.NA,
        "mape": pd.NA,
    }


def _sse(actual: Iterable[Any], forecast: Iterable[Any]) -> float:
    actual_series = pd.to_numeric(pd.Series(actual), errors="coerce")
    forecast_series = pd.to_numeric(pd.Series(forecast), errors="coerce")
    return float(((actual_series - forecast_series) ** 2).sum())


def _sst(actual: Iterable[Any]) -> float:
    actual_series = pd.to_numeric(pd.Series(actual), errors="coerce").dropna()
    if actual_series.empty:
        return float("nan")
    return float(((actual_series - actual_series.mean()) ** 2).sum())


def _bias_pct(pair: pd.DataFrame) -> float | pd.NA:
    usable = pair[pair["actual"].ne(0)].copy()
    if usable.empty:
        return pd.NA
    return float(((usable["forecast"] - usable["actual"]) / usable["actual"] * 100).mean())


def _mape(pair: pd.DataFrame) -> float | pd.NA:
    usable = pair[pair["actual"].ne(0)].copy()
    if usable.empty:
        return pd.NA
    return float(((usable["forecast"] - usable["actual"]).abs() / usable["actual"].abs() * 100).mean())


def _positive(value: Any) -> bool:
    number = pd.to_numeric(value, errors="coerce")
    return pd.notna(number) and float(number) > 0


def _first_present(frame: pd.DataFrame, columns: list[str]) -> str | None:
    return next((column for column in columns if column in frame.columns), None)


def _stream_label_from_key(stream_key: str) -> str:
    return {
        "ped": "PED VKT per capita",
        "light_ruc": "Light RUC volume",
        "heavy_ruc": "Heavy RUC volume",
    }.get(stream_key, stream_key.replace("_", " ").title())


def _stream_from_label(label: Any) -> str:
    text = str(label)
    return {
        "PED VKT per capita": "PED",
        "Light RUC volume": "LIGHT_RUC",
        "Heavy RUC volume": "HEAVY_RUC",
    }.get(text, text.upper().replace(" ", "_"))


def _relative_source_file(path: Path) -> str:
    parts = path.parts
    if "data" in parts:
        return str(Path(*parts[parts.index("data") :])).replace("\\", "/")
    return path.name

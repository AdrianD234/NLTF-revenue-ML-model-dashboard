from __future__ import annotations

import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .labels import STRESS_BUCKET_ORDER, STRESS_SLICE_LABELS, is_schiff_text, schiff_class, stream_key, stream_label
from .schema import PREDICTION_COLUMN_ALIASES


KEY_COLUMNS = ["stage", "stream", "variant", "model"]
MODEL_KEY_COLUMN = "_model_key"
MODEL_KEY_SEPARATOR = "\x1f"
PERCENT_COLUMNS = [
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "annual_p90_ape",
    "mape",
    "bias_pct",
    "p90_ape",
    "baseline_mape",
    "challenger_mape",
    "mape_improvement_pct_points",
    "challenger_win_rate",
]


def first_existing(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lower = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        key = candidate.lower()
        if key in lower:
            return lower[key]
    return None


def coerce_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def scale_percent_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in PERCENT_COLUMNS:
        if col not in out.columns:
            continue
        out[col] = pd.to_numeric(out[col], errors="coerce")
        values = out[col].dropna().abs()
        if not values.empty and values.quantile(0.90) <= 1.0:
            out[col] = out[col] * 100.0
    return out


def percent_unit_warnings(df: pd.DataFrame, dataset: str) -> list[str]:
    if df is None or df.empty:
        return []
    warnings: list[str] = []
    for col in PERCENT_COLUMNS:
        if col not in df.columns:
            continue
        values = pd.to_numeric(df[col], errors="coerce").dropna().abs()
        if values.empty:
            continue
        small_share = float((values <= 1.0).mean())
        large_share = float((values > 1.0).mean())
        if small_share > 0.05 and large_share > 0.05:
            warnings.append(
                f"Mixed percent-unit pattern detected in {dataset}.{col}; review whether values are proportions or percentage points."
            )
    return warnings


def add_stream_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "stream" in out.columns:
        out["stream_key"] = out["stream"].map(stream_key)
        out["stream_label"] = out["stream"].map(stream_label)
    else:
        out["stream"] = "Unknown"
        out["stream_key"] = "UNKNOWN"
        out["stream_label"] = "Unknown"
    return out


def add_model_flags(df: pd.DataFrame, recommended: pd.DataFrame | None = None) -> pd.DataFrame:
    out = df.copy()
    out[MODEL_KEY_COLUMN] = model_key_series(out)
    out["schiff_class"] = out.apply(
        lambda row: schiff_class(row.get("model"), row.get("source_family"), row.get("variant")),
        axis=1,
    )
    out["is_schiff"] = out.apply(
        lambda row: is_schiff_text(
            row.get("model"),
            row.get("source_family"),
            row.get("variant"),
            row.get("baseline"),
            row.get("challenger"),
        ),
        axis=1,
    )
    out["is_finalist"] = False
    if recommended is not None and not recommended.empty:
        keys = model_key_set(recommended)
        out["is_finalist"] = out[MODEL_KEY_COLUMN].isin(keys)
    return out


def normalise_summary(df: pd.DataFrame, recommended: pd.DataFrame | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    out = coerce_numeric(out, PERCENT_COLUMNS + [col for col in out.columns if str(col).startswith("mape_h")])
    out = scale_percent_columns(out)
    out = add_stream_fields(out)
    out = add_model_flags(out, recommended)
    return out


def normalise_recommended(df: pd.DataFrame) -> pd.DataFrame:
    return normalise_summary(df, None)


def rename_prediction_columns(df: pd.DataFrame, annual: bool = False) -> pd.DataFrame:
    out = df.copy()
    rename_map = {}
    for standard, aliases in PREDICTION_COLUMN_ALIASES.items():
        existing = first_existing(out, aliases)
        if existing and existing != standard and standard not in out.columns:
            rename_map[existing] = standard
    if rename_map:
        out = out.rename(columns=rename_map)
    if annual and "target_period" not in out.columns and "june_year" in out.columns:
        out["target_period"] = out["june_year"].astype(str)
    return out


def normalise_predictions(df: pd.DataFrame, annual: bool = False) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = rename_prediction_columns(df, annual=annual)
    out = add_stream_fields(out)
    out = coerce_numeric(out, ["actual", "pred", "horizon", "june_year"])
    if "actual" in out.columns and "pred" in out.columns:
        denominator = out["actual"].replace(0, np.nan)
        out["error_pct"] = 100.0 * (out["pred"] - out["actual"]) / denominator
        out["ape"] = out["error_pct"].abs()
    if "horizon" in out.columns:
        out["horizon_bucket"] = out["horizon"].map(horizon_bucket)
    elif not annual:
        out["horizon_bucket"] = "Unknown"
    out = scale_percent_columns(out)
    out[MODEL_KEY_COLUMN] = model_key_series(out)
    return out


def normalise_paired(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out = add_stream_fields(out)
    out = coerce_numeric(
        out,
        ["n_common_pairs", "baseline_mape", "challenger_mape", "mape_improvement_pct_points", "challenger_win_rate"],
    )
    out = scale_percent_columns(out)
    if "baseline" in out.columns:
        out["baseline_schiff_class"] = out["baseline"].map(lambda value: schiff_class(value))
    if "challenger" in out.columns:
        out["challenger_schiff_class"] = out["challenger"].map(lambda value: schiff_class(value))
    return out


def normalise_weights(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = add_stream_fields(df)
    if "weight" in out.columns:
        out["weight"] = pd.to_numeric(out["weight"], errors="coerce")
    if "origin" in out.columns:
        out["origin"] = out["origin"].astype(str).replace({"nan": "", "NaT": "", "<NA>": ""})
    return out


def normalise_stress(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = add_stream_fields(df)
    out = coerce_numeric(out, ["n_pairs", "mape", "bias_pct", "p90_ape"])
    out = scale_percent_columns(out)
    if "stress_slice" in out.columns:
        out["stress_bucket"] = out["stress_slice"].map(lambda value: STRESS_SLICE_LABELS.get(str(value), str(value)))
    elif "stress_bucket" not in out.columns:
        out["stress_bucket"] = "Unknown"
    out["stress_bucket"] = pd.Categorical(
        out["stress_bucket"],
        categories=STRESS_BUCKET_ORDER + ["All qtrs", "Unknown"],
        ordered=True,
    )
    out[MODEL_KEY_COLUMN] = model_key_series(out)
    return out


def row_key(row: pd.Series | dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(col, "")).strip() for col in KEY_COLUMNS)


def model_key_series(df: pd.DataFrame) -> pd.Series:
    """Return stable model keys without row-wise Python callbacks."""
    if df is None or df.empty:
        return pd.Series(dtype=object)
    parts: list[pd.Series] = []
    for col in KEY_COLUMNS:
        if col in df.columns:
            source = df[col]
            if source.isna().any():
                source = source.where(source.notna(), "nan")
            part = source.astype(str).str.strip()
        else:
            part = pd.Series("", index=df.index, dtype=object)
        parts.append(part)
    key = parts[0]
    for part in parts[1:]:
        key = key + MODEL_KEY_SEPARATOR + part
    return key


def model_key_set(df: pd.DataFrame) -> set[str]:
    if df is None or df.empty:
        return set()
    if MODEL_KEY_COLUMN in df.columns:
        return set(df[MODEL_KEY_COLUMN].dropna().astype(str))
    return set(model_key_series(df).dropna().astype(str))


def filter_to_model_keys(df: pd.DataFrame, keys: set[str]) -> pd.DataFrame:
    if df is None or df.empty or not keys:
        return pd.DataFrame() if df is None else df.copy()
    if not all(col in df.columns for col in KEY_COLUMNS) and MODEL_KEY_COLUMN not in df.columns:
        return df.copy()
    series = df[MODEL_KEY_COLUMN].astype(str) if MODEL_KEY_COLUMN in df.columns else model_key_series(df)
    return df[series.isin(keys)].copy()


def best_by_stream(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    sort_cols = [col for col in ["quarterly_mape", "annual_mape", "governance_score"] if col in out.columns]
    if not sort_cols:
        return out.drop_duplicates("stream_label")
    ascending = [True, True, True][: len(sort_cols)]
    return out.sort_values(sort_cols, ascending=ascending).groupby("stream_label", as_index=False).head(1)


def schiff_result_label(gain: Any, win_rate: Any) -> str:
    gain_value = pd.to_numeric(pd.Series([gain]), errors="coerce").iloc[0]
    win_rate_value = pd.to_numeric(pd.Series([win_rate]), errors="coerce").iloc[0]
    if pd.isna(gain_value) or gain_value <= 0:
        return "Does not beat Schiff"
    if pd.notna(win_rate_value) and win_rate_value > 55:
        return "Beats Schiff"
    return "Average gain, mixed wins"


def schiff_result_tone(label: str) -> str:
    if label == "Beats Schiff":
        return "good"
    if label == "Does not beat Schiff":
        return "bad"
    return "mixed"


def governance_story_summary(
    recommended: pd.DataFrame,
    paired: pd.DataFrame,
    stress: pd.DataFrame,
    errors: pd.DataFrame,
) -> pd.DataFrame:
    """Summarise the four management questions by stream using loaded run data."""
    finalists = best_by_stream(recommended)
    if finalists.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for _, finalist in finalists.sort_values("stream_label").iterrows():
        stream = finalist.get("stream_label", "Unknown")
        paired_row, paired_note = _paired_row_for_finalist(paired, finalist)
        stress_row = _worst_stress_row(stress, stream)
        if paired_row is not None:
            schiff_status = schiff_result_label(
                paired_row.get("mape_improvement_pct_points"),
                paired_row.get("challenger_win_rate"),
            )
            gain = paired_row.get("mape_improvement_pct_points")
            win_rate = paired_row.get("challenger_win_rate")
            schiff_summary = _schiff_summary(schiff_status, gain, win_rate)
        else:
            schiff_status = "Not verified"
            gain = float("nan")
            win_rate = float("nan")
            paired_note = "No paired Schiff row"
            schiff_summary = "No paired Schiff comparison is available."

        robustness, robustness_tone = _robustness_label(stress_row)
        warning_count = _error_count_for_stream(errors, stream)
        rows.append(
            {
                "stream_label": stream,
                "winning_model": finalist.get("model", ""),
                "source_family": finalist.get("source_family", ""),
                "variant": finalist.get("variant", ""),
                "quarterly_mape": finalist.get("quarterly_mape"),
                "annual_mape": finalist.get("annual_mape"),
                "schiff_status": schiff_status,
                "schiff_tone": schiff_result_tone(schiff_status),
                "schiff_gain": gain,
                "schiff_win_rate": win_rate,
                "schiff_evidence": paired_note,
                "schiff_summary": schiff_summary,
                "robustness_status": robustness,
                "robustness_tone": robustness_tone,
                "robustness_bucket": "" if stress_row is None else stress_row.get("stress_bucket", ""),
                "robustness_mape": float("nan") if stress_row is None else stress_row.get("mape"),
                "warning_count": warning_count,
                "warning_summary": _warning_summary(errors, warning_count),
                "decision_status": _decision_status(schiff_status, robustness_tone, warning_count),
            }
        )
    return pd.DataFrame(rows)


def _decision_status(schiff_status: str, robustness_tone: str, warning_count: int) -> str:
    if schiff_status == "Does not beat Schiff":
        return "Reject"
    if robustness_tone == "bad":
        return "Watchlist"
    if schiff_status == "Average gain, mixed wins" or warning_count > 0:
        return "Needs Stage 2"
    return "Promote"


def manager_conclusion(story: pd.DataFrame) -> str:
    if story is None or story.empty:
        return "No manager conclusion is available because no recommended finalist rows were loaded."
    beat_count = int((story["schiff_status"] == "Beats Schiff").sum()) if "schiff_status" in story.columns else 0
    mixed = ", ".join(story.loc[story["schiff_status"] != "Beats Schiff", "stream_label"].astype(str)) if "schiff_status" in story.columns else ""
    high_risk = ", ".join(
        story.loc[story["robustness_tone"] == "bad", "stream_label"].astype(str)
    ) if "robustness_tone" in story.columns else ""
    warnings = int(pd.to_numeric(story.get("warning_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    parts = [
        f"{beat_count} of {len(story)} selected stream finalists beat Schiff on the paired comparison rule.",
    ]
    if mixed:
        parts.append(f"Treat {mixed} as a benchmark watch point rather than a clean structural-model win.")
    if high_risk:
        parts.append(f"Stress checks flag {high_risk} as high-risk, so Stage 1 is not an end-to-end forecast-risk sign-off.")
    if warnings:
        parts.append("Logged errors are candidate-search diagnostics; review Run Audit before treating the run as production-ready.")
    parts.append("Use this as model-form evidence for Stage 2 uncertainty testing, not as a final macro/fuel-input forecast assessment.")
    return " ".join(parts)


def stress_readout(stress: pd.DataFrame) -> str:
    if stress is None or stress.empty or not {"stream_label", "stress_bucket", "mape"}.issubset(stress.columns):
        return "Stress read: no stress metrics are available for the selected filters."
    data = stress.dropna(subset=["mape"]).copy()
    if data.empty:
        return "Stress read: stress metrics are present but MAPE values are missing."
    worst = data.sort_values("mape", ascending=False).iloc[0]
    high_risk_streams = sorted(data.loc[pd.to_numeric(data["mape"], errors="coerce") >= 10, "stream_label"].astype(str).unique())
    high_text = ", ".join(high_risk_streams) if high_risk_streams else "none"
    return (
        f"Stress read: worst bucket is {worst['stream_label']} in {worst['stress_bucket']} "
        f"at {float(worst['mape']):.2f}% MAPE. Streams crossing the 10% high-risk guide: {high_text}."
    )


def forecast_error_readout(qpred: pd.DataFrame) -> str:
    if qpred is None or qpred.empty or not {"ape", "error_pct"}.issubset(qpred.columns):
        return "Forecast read: no forecast-error rows are available for the selected view."
    data = qpred.dropna(subset=["ape", "error_pct"]).copy()
    if data.empty:
        return "Forecast read: selected forecast rows have no valid percentage-error values."
    worst = data.sort_values("ape", ascending=False).iloc[0]
    mean_ape = float(pd.to_numeric(data["ape"], errors="coerce").mean())
    bias_value = float(pd.to_numeric(data["error_pct"], errors="coerce").mean())
    target = worst.get("target_period", "selected period")
    horizon = worst.get("horizon", "")
    horizon_text = "" if horizon == "" or pd.isna(horizon) else f", horizon {int(float(horizon))}"
    direction = "over-forecast" if bias_value > 0 else "under-forecast" if bias_value < 0 else "unbiased on average"
    return (
        f"Forecast read: selected rows average {mean_ape:.2f}% absolute error and {direction} "
        f"by {abs(bias_value):.2f}% on average. Largest miss is {float(worst['ape']):.2f}% "
        f"at {target}{horizon_text}."
    )


def inventory_rank_options(summary: pd.DataFrame) -> list[str]:
    candidates = ["quarterly_mape", "annual_mape", "governance_score", "quarterly_bias_pct", "annual_bias_pct"]
    return [col for col in candidates if summary is not None and col in summary.columns]


def classify_error_rows(errors: pd.DataFrame) -> pd.DataFrame:
    if errors is None or errors.empty:
        return pd.DataFrame(columns=["Error type", "Rows"])
    explicit = errors["error"].astype(str).str.lower() if "error" in errors.columns else errors.astype(str).agg(" ".join, axis=1).str.lower()
    patterns = {
        "HyperOpt missing": "hyperopt",
        "Ray root-cause": r"\bray\b",
        "Permission/access": "permission|access denied|denied",
        "Neural model": "neural|deepar|tft|transformer",
        "Empty data": "empty file|empty dataframe|no rows",
    }
    rows = []
    matched = pd.Series(False, index=errors.index)
    for label, pattern in patterns.items():
        mask = explicit.str.contains(pattern, regex=True, na=False)
        rows.append({"Error type": label, "Rows": int(mask.sum())})
        matched = matched | mask
    rows.append({"Error type": "Other", "Rows": int((~matched).sum())})
    return pd.DataFrame(rows)


def _paired_row_for_finalist(paired: pd.DataFrame, finalist: pd.Series) -> tuple[pd.Series | None, str]:
    if paired is None or paired.empty or "stream_label" not in paired.columns:
        return None, "No paired Schiff row"
    stream = finalist.get("stream_label")
    stream_rows = paired[paired["stream_label"] == stream].copy()
    if stream_rows.empty:
        return None, "No paired Schiff row for stream"
    model = str(finalist.get("model", ""))
    if "challenger" in stream_rows.columns:
        exact = stream_rows[stream_rows["challenger"].astype(str) == model]
        if not exact.empty:
            ranked = _sort_paired_rows(exact)
            return ranked.iloc[0], "Finalist paired against Schiff"
    ranked = _sort_paired_rows(stream_rows)
    return ranked.iloc[0], "Best available paired challenger for stream"


def _sort_paired_rows(rows: pd.DataFrame) -> pd.DataFrame:
    sort_cols = [col for col in ["mape_improvement_pct_points", "challenger_win_rate"] if col in rows.columns]
    if not sort_cols:
        return rows
    return rows.sort_values(sort_cols, ascending=[False] * len(sort_cols))


def _schiff_summary(status: str, gain: Any, win_rate: Any) -> str:
    gain_value = pd.to_numeric(pd.Series([gain]), errors="coerce").iloc[0]
    win_value = pd.to_numeric(pd.Series([win_rate]), errors="coerce").iloc[0]
    gain_text = "unknown gain" if pd.isna(gain_value) else f"{gain_value:.2f} pp MAPE gain"
    win_text = "unknown win rate" if pd.isna(win_value) else f"{win_value:.1f}% win rate"
    if status == "Beats Schiff":
        return f"Yes: {gain_text}; {win_text}."
    if status == "Average gain, mixed wins":
        return f"Mixed: {gain_text}, but only {win_text}."
    return f"No: {gain_text}; {win_text}."


def _worst_stress_row(stress: pd.DataFrame, stream: Any) -> pd.Series | None:
    if stress is None or stress.empty or not {"stream_label", "mape"}.issubset(stress.columns):
        return None
    stream_rows = stress[stress["stream_label"] == stream].dropna(subset=["mape"])
    if stream_rows.empty:
        return None
    return stream_rows.sort_values("mape", ascending=False).iloc[0]


def _robustness_label(stress_row: pd.Series | None) -> tuple[str, str]:
    if stress_row is None:
        return "Not verified", "mixed"
    value = pd.to_numeric(pd.Series([stress_row.get("mape")]), errors="coerce").iloc[0]
    bucket = stress_row.get("stress_bucket", "stress bucket")
    if pd.isna(value):
        return "Not verified", "mixed"
    if value <= 5:
        return f"Stable: worst bucket {bucket}", "good"
    if value <= 10:
        return f"Watch: worst bucket {bucket}", "mixed"
    return f"High-risk: worst bucket {bucket}", "bad"


def _error_count_for_stream(errors: pd.DataFrame, stream: Any) -> int:
    if errors is None or errors.empty:
        return 0
    if "stream_label" in errors.columns:
        return int((errors["stream_label"] == stream).sum())
    if "stream" in errors.columns:
        labelled = add_stream_fields(errors)
        return int((labelled["stream_label"] == stream).sum())
    return len(errors)


def _warning_summary(errors: pd.DataFrame, count: int) -> str:
    if count <= 0 or errors is None or errors.empty:
        return "No logged warning rows."
    explicit = errors["error"].astype(str).str.lower() if "error" in errors.columns else errors.astype(str).agg(" ".join, axis=1).str.lower()
    if explicit.str.contains("hyperopt", na=False).all():
        return f"{count:,} candidate-search failures logged; all explicit errors are missing HyperOpt."
    return f"{count:,} logged diagnostic rows; inspect Run Audit for materiality."


def horizon_bucket(value: Any) -> str:
    try:
        horizon = int(float(value))
    except (TypeError, ValueError):
        return "Unknown"
    if 1 <= horizon <= 4:
        return "1-4 qtrs"
    if 5 <= horizon <= 8:
        return "5-8 qtrs"
    if 9 <= horizon <= 12:
        return "9-12 qtrs"
    return "Other"


def period_key(value: Any) -> float:
    text = "" if value is None else str(value).strip()
    match = re.match(r"^(\d{4})\s*Q([1-4])$", text, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 4 + int(match.group(2))
    try:
        return float(text)
    except ValueError:
        return math.nan


def june_year(value: Any) -> float:
    text = "" if value is None else str(value).strip()
    match = re.match(r"^(\d{4})\s*Q([1-4])$", text, re.IGNORECASE)
    if not match:
        return math.nan
    year = int(match.group(1))
    quarter = int(match.group(2))
    return year + 1 if quarter in (3, 4) else year


def mape(series_actual: pd.Series, series_pred: pd.Series) -> float:
    denominator = series_actual.replace(0, np.nan)
    ape = (100.0 * (series_pred - series_actual) / denominator).abs()
    return float(ape.mean())


def bias(series_actual: pd.Series, series_pred: pd.Series) -> float:
    denominator = series_actual.replace(0, np.nan)
    error = 100.0 * (series_pred - series_actual) / denominator
    return float(error.mean())


def p90_ape(series_actual: pd.Series, series_pred: pd.Series) -> float:
    denominator = series_actual.replace(0, np.nan)
    ape = (100.0 * (series_pred - series_actual) / denominator).abs()
    return float(ape.quantile(0.90))


def derive_paired_from_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary is None or summary.empty or "quarterly_mape" not in summary.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (stage, stream), group in summary.groupby(["stage", "stream"], dropna=False):
        schiff = group[group["is_schiff"]].sort_values("quarterly_mape").head(1)
        if schiff.empty:
            continue
        baseline = schiff.iloc[0]
        candidates = group[~group["is_schiff"]].copy()
        for _, candidate in candidates.iterrows():
            rows.append(
                {
                    "stage": stage,
                    "stream": stream,
                    "baseline": baseline.get("model"),
                    "challenger": candidate.get("model"),
                    "n_common_pairs": candidate.get("n_quarterly_pairs"),
                    "baseline_mape": baseline.get("quarterly_mape"),
                    "challenger_mape": candidate.get("quarterly_mape"),
                    "mape_improvement_pct_points": baseline.get("quarterly_mape") - candidate.get("quarterly_mape"),
                    "challenger_win_rate": np.nan,
                }
            )
    return normalise_paired(pd.DataFrame(rows))


def filter_by_common_controls(
    df: pd.DataFrame,
    stage: str = "all",
    streams: list[str] | None = None,
    source_families: list[str] | None = None,
    variants: list[str] | None = None,
    include_schiff: bool = True,
    show_screen: bool = True,
    show_final: bool = True,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if stage and stage != "all" and "stage" in out.columns:
        out = out[out["stage"].astype(str).str.lower() == stage.lower()]
    if streams is not None and "stream_label" in out.columns:
        out = out[out["stream_label"].isin(streams)]
    if source_families is not None and "source_family" in out.columns:
        out = out[out["source_family"].isin(source_families)]
    if variants is not None and "variant" in out.columns:
        out = out[out["variant"].isin(variants)]
    if "stage" in out.columns:
        stage_values = out["stage"].astype(str).str.lower()
        if not show_screen:
            out = out[stage_values != "screen"]
        if not show_final:
            out = out[stage_values != "final"]
    if not include_schiff and "is_schiff" in out.columns:
        out = out[~out["is_schiff"]]
    return out


def final_stress_frame(
    stress: pd.DataFrame,
    qpred: pd.DataFrame,
    annual: pd.DataFrame,
    recommended: pd.DataFrame,
    *,
    include_extra_buckets: bool = False,
) -> pd.DataFrame:
    best = best_by_stream(recommended)
    keys = model_key_set(best)
    if stress is not None and not stress.empty:
        out = stress.copy()
        if keys and (MODEL_KEY_COLUMN in out.columns or all(col in out.columns for col in KEY_COLUMNS)):
            out = filter_to_model_keys(out, keys)
        if not include_extra_buckets:
            out = out[out["stress_bucket"].astype(str).isin(STRESS_BUCKET_ORDER)]
        return out.sort_values(["stream_label", "stress_bucket"])
    return reconstruct_stress_checks(qpred, annual, best)


def reconstruct_stress_checks(qpred: pd.DataFrame, annual: pd.DataFrame, finalists: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = model_key_set(finalists)
    if qpred is not None and not qpred.empty and {"actual", "pred"}.issubset(qpred.columns):
        q = qpred.copy()
        if keys and (MODEL_KEY_COLUMN in q.columns or all(col in q.columns for col in KEY_COLUMNS)):
            q = filter_to_model_keys(q, keys)
        q["_period_key"] = q.get("target_period", pd.Series(index=q.index, dtype=object)).map(period_key)
        slices = {
            "1-4 qtrs": q["horizon_bucket"].eq("1-4 qtrs") if "horizon_bucket" in q.columns else pd.Series(False, index=q.index),
            "5-8 qtrs": q["horizon_bucket"].eq("5-8 qtrs") if "horizon_bucket" in q.columns else pd.Series(False, index=q.index),
            "9-12 qtrs": q["horizon_bucket"].eq("9-12 qtrs") if "horizon_bucket" in q.columns else pd.Series(False, index=q.index),
            "2024+": q["_period_key"].ge(period_key("2024Q1")),
            "2022-23": q["_period_key"].between(period_key("2022Q1"), period_key("2023Q4")),
        }
        for label, mask in slices.items():
            subset = q[mask]
            for _, group in subset.groupby(["stage", "stream", "variant", "model", "stream_label"], dropna=False):
                if group.empty:
                    continue
                rows.append(
                    {
                        "stage": group["stage"].iloc[0] if "stage" in group.columns else "",
                        "stream": group["stream"].iloc[0],
                        "variant": group["variant"].iloc[0] if "variant" in group.columns else "",
                        "model": group["model"].iloc[0] if "model" in group.columns else "",
                        "stream_label": group["stream_label"].iloc[0],
                        "stress_bucket": label,
                        "n_pairs": len(group),
                        "mape": mape(group["actual"], group["pred"]),
                        "bias_pct": bias(group["actual"], group["pred"]),
                        "p90_ape": p90_ape(group["actual"], group["pred"]),
                    }
                )
    if annual is not None and not annual.empty and {"actual", "pred"}.issubset(annual.columns):
        a = annual.copy()
        if keys and (MODEL_KEY_COLUMN in a.columns or all(col in a.columns for col in KEY_COLUMNS)):
            a = filter_to_model_keys(a, keys)
        for _, group in a.groupby(["stage", "stream", "variant", "model", "stream_label"], dropna=False):
            rows.append(
                {
                    "stage": group["stage"].iloc[0] if "stage" in group.columns else "",
                    "stream": group["stream"].iloc[0],
                    "variant": group["variant"].iloc[0] if "variant" in group.columns else "",
                    "model": group["model"].iloc[0] if "model" in group.columns else "",
                    "stream_label": group["stream_label"].iloc[0],
                    "stress_bucket": "Annual",
                    "n_pairs": len(group),
                    "mape": mape(group["actual"], group["pred"]),
                    "bias_pct": bias(group["actual"], group["pred"]),
                    "p90_ape": p90_ape(group["actual"], group["pred"]),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["stress_bucket"] = pd.Categorical(out["stress_bucket"], categories=STRESS_BUCKET_ORDER, ordered=True)
    return add_stream_fields(out).sort_values(["stream_label", "stress_bucket"])

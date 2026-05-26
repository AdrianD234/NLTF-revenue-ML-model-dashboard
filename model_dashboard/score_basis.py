from __future__ import annotations

from typing import Any

import pandas as pd


PAPER_SCORE_BASIS = "schiff_paper_horizon_mean"
OPERATIONAL_SCORE_BASIS = "current_grid_operational_pooled"

PAPER_SCORE_LABEL = "Paper-style horizon MAPE"
OPERATIONAL_SCORE_LABEL = "Operational pooled MAPE"

SCORE_BASIS_LABELS = {
    PAPER_SCORE_BASIS: PAPER_SCORE_LABEL,
    OPERATIONAL_SCORE_BASIS: OPERATIONAL_SCORE_LABEL,
}

SCORE_BASIS_KEYS_BY_LABEL = {label: key for key, label in SCORE_BASIS_LABELS.items()}
SCORE_BASIS_OPTIONS = [PAPER_SCORE_LABEL, OPERATIONAL_SCORE_LABEL]


METRIC_COLUMNS_BY_BASIS = {
    PAPER_SCORE_BASIS: {
        "quarterly_mape": "paper_horizon_mean_mape",
        "annual_mape": "paper_annual_mape",
        "quarterly_bias_pct": "paper_bias_pct",
        "annual_bias_pct": "paper_annual_bias_pct",
        "mape_h09_12": "paper_h09_12_mape",
    },
    OPERATIONAL_SCORE_BASIS: {
        "quarterly_mape": "operational_pooled_mape",
        "annual_mape": "operational_annual_mape",
        "quarterly_bias_pct": "operational_bias_pct",
        "annual_bias_pct": "operational_annual_bias_pct",
        "mape_h09_12": "operational_h09_12_mape",
    },
}


def score_basis_key(value: Any) -> str:
    text = "" if value is None else str(value)
    if text in SCORE_BASIS_LABELS:
        return text
    if text in SCORE_BASIS_KEYS_BY_LABEL:
        return SCORE_BASIS_KEYS_BY_LABEL[text]
    lower = text.lower()
    if "operational" in lower or "pooled" in lower or lower == OPERATIONAL_SCORE_BASIS:
        return OPERATIONAL_SCORE_BASIS
    return PAPER_SCORE_BASIS


def score_basis_label(value: Any) -> str:
    return SCORE_BASIS_LABELS.get(score_basis_key(value), PAPER_SCORE_LABEL)


def score_basis_metric_label(value: Any) -> str:
    key = score_basis_key(value)
    if key == OPERATIONAL_SCORE_BASIS:
        return "Operational pooled MAPE"
    return "Paper-style horizon MAPE"


def score_basis_metric_source(value: Any, metric: str) -> str:
    key = score_basis_key(value)
    return METRIC_COLUMNS_BY_BASIS.get(key, {}).get(metric, metric)


def project_score_basis_frame(frame: pd.DataFrame, basis: Any = PAPER_SCORE_BASIS) -> pd.DataFrame:
    """Return a copy whose standard metric columns reflect the selected basis."""
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    key = score_basis_key(basis)
    out = frame.copy()
    for target, source in METRIC_COLUMNS_BY_BASIS[key].items():
        if source in out.columns:
            out[target] = pd.to_numeric(out[source], errors="coerce")
    out["score_basis"] = key
    out["score_basis_label"] = score_basis_label(key)
    out["quarterly_mape_source_column"] = score_basis_metric_source(key, "quarterly_mape")
    out["annual_mape_source_column"] = score_basis_metric_source(key, "annual_mape")
    out["bias_source_column"] = score_basis_metric_source(key, "quarterly_bias_pct")
    return out


def filter_score_basis_rows(frame: pd.DataFrame, basis: Any = PAPER_SCORE_BASIS) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    key = score_basis_key(basis)
    out = frame.copy()
    if "score_basis" in out.columns:
        out = out[out["score_basis"].astype(str).eq(key)].copy()
    out["score_basis"] = key
    out["score_basis_label"] = score_basis_label(key)
    return out


def project_scenario_comparison_frame(
    comparison: pd.DataFrame,
    basis: Any = PAPER_SCORE_BASIS,
    finalists: pd.DataFrame | None = None,
    schiff: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if comparison is None or comparison.empty:
        return pd.DataFrame()
    key = score_basis_key(basis)
    out = comparison.copy()
    if key == OPERATIONAL_SCORE_BASIS:
        if "operational_finalist_mape" in out.columns:
            out["finalist_quarterly_mape"] = pd.to_numeric(out["operational_finalist_mape"], errors="coerce")
        if "operational_schiff_mape" in out.columns:
            out["schiff_quarterly_mape"] = pd.to_numeric(out["operational_schiff_mape"], errors="coerce")
        if "operational_gain_pp" in out.columns:
            out["quarterly_gain_pp"] = pd.to_numeric(out["operational_gain_pp"], errors="coerce")
            out["full_sample_qtr_gain_pp"] = out["quarterly_gain_pp"]
        if finalists is not None and not finalists.empty:
            finalist_projected = project_score_basis_frame(finalists, key)
            annual_lookup = finalist_projected.set_index("stream_label")["annual_mape"].to_dict()
            out["finalist_annual_mape"] = out["stream_label"].map(annual_lookup)
        if schiff is not None and not schiff.empty:
            schiff_projected = project_score_basis_frame(schiff, key)
            annual_lookup = schiff_projected.set_index("stream_label")["annual_mape"].to_dict()
            out["schiff_annual_mape"] = out["stream_label"].map(annual_lookup)
        if {"schiff_annual_mape", "finalist_annual_mape"}.issubset(out.columns):
            out["annual_gain_pp"] = pd.to_numeric(out["schiff_annual_mape"], errors="coerce") - pd.to_numeric(
                out["finalist_annual_mape"], errors="coerce"
            )
            out["full_sample_annual_gain_pp"] = out["annual_gain_pp"]
    else:
        if "full_sample_qtr_gain_pp" in out.columns:
            out["quarterly_gain_pp"] = pd.to_numeric(out["full_sample_qtr_gain_pp"], errors="coerce")
        if "full_sample_annual_gain_pp" in out.columns:
            out["annual_gain_pp"] = pd.to_numeric(out["full_sample_annual_gain_pp"], errors="coerce")
    if "paired_win_rate_pct" in out.columns:
        out["win_rate"] = out["paired_win_rate_pct"]
    out["score_basis"] = key
    out["score_basis_label"] = score_basis_label(key)
    return out

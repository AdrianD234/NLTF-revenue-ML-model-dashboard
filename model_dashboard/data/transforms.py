"""Parquet schema aliases and dataframe transforms."""

from __future__ import annotations

from typing import Any

import pandas as pd

from model_dashboard.labels import humanize_label, schiff_class, stream_label
from model_dashboard.metrics import add_stream_fields, coerce_numeric, scale_percent_columns


CORE_PARQUET_COLUMNS = [
    "stream",
    "stream_label",
    "model",
    "model_short",
    "source_run",
    "source_file",
    "source_family",
    "model_kind",
    "feature_set",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "annual_p90_ape",
    "mape_h01",
    "mape_h02",
    "mape_h03",
    "mape_h04",
    "mape_h05",
    "mape_h06",
    "mape_h07",
    "mape_h08",
    "mape_h09",
    "mape_h10",
    "mape_h11",
    "mape_h12",
    "mape_h01_04",
    "mape_h05_08",
    "mape_h09_12",
    "stress_1_4_qtrs_mape",
    "stress_5_8_qtrs_mape",
    "stress_9_12_qtrs_mape",
    "performance_rank",
    "performance_percentile",
    "performance_decile",
    "selection_score",
    "candidate_role",
    "include_reason",
    "is_current_recommended",
    "is_pure_schiff",
    "is_pdf_reference",
    "is_frontier",
    "is_top_quarterly",
    "is_top_annual",
    "is_distribution_sample",
    "is_extreme_outlier",
    "plot_default_include",
    "paired_gain_vs_schiff_pp",
    "paired_win_rate",
    "paired_common_pairs",
    "stress_2024_plus_mape",
    "stress_2022_23_mape",
    "stress_annual_mape",
    "durbin_watson",
    "adj_r2",
    "adf_pvalue",
    "kpss_pvalue",
    "breusch_pagan_pvalue",
    "white_pvalue",
    "arch_lm_pvalue",
    "jarque_bera_pvalue",
    "skewness",
    "kurtosis",
    "cointegration_pvalue",
]

COLUMN_ALIASES = {
    "source_run": ["source_run", "run_source", "run_id"],
    "performance_rank": ["performance_rank", "performance_rank_within_stream"],
    "is_current_recommended": ["is_current_recommended", "is_recommended_finalist", "current_recommended"],
    "is_frontier": ["is_frontier", "is_pareto_frontier", "pareto_frontier"],
    "is_distribution_sample": ["is_distribution_sample", "is_curated_cone_sample", "distribution_sample"],
    "paired_gain_vs_schiff_pp": [
        "paired_gain_vs_schiff_pp",
        "paired_improvement_pp",
        "mape_improvement_pp",
        "mape_improvement_pct_points",
    ],
    "paired_win_rate": ["paired_win_rate", "paired_win_rate_pct", "our_win_rate_pct", "challenger_win_rate"],
    "paired_common_pairs": ["paired_common_pairs", "n_common_pairs"],
    "stress_1_4_qtrs_mape": ["stress_1_4_qtrs_mape", "mape_h01_04", "h1_4_mape"],
    "stress_5_8_qtrs_mape": ["stress_5_8_qtrs_mape", "mape_h05_08", "h5_8_mape"],
    "stress_9_12_qtrs_mape": ["stress_9_12_qtrs_mape", "mape_h09_12", "h9_12_mape"],
    "stress_2024_plus_mape": ["stress_2024_plus_mape", "stress_2024plus_mape", "recent_2024_plus_mape"],
    "stress_2022_23_mape": ["stress_2022_23_mape", "policy_2022_23_mape"],
    "stress_annual_mape": ["stress_annual_mape", "annual_mape", "annual_mape_filled"],
    "durbin_watson": ["durbin_watson", "dw", "diag_durbin_watson"],
    "adj_r2": ["adj_r2", "adjusted_r2", "mz_r2", "diag_mz_r2"],
    "adf_pvalue": ["adf_pvalue", "adf_p_resid", "diag_adf_p_resid"],
    "kpss_pvalue": ["kpss_pvalue", "kpss_p_resid", "diag_kpss_p_resid"],
    "breusch_pagan_pvalue": ["breusch_pagan_pvalue", "breusch_pagan_p", "diag_breusch_pagan_p"],
    "white_pvalue": ["white_pvalue", "white_p", "diag_white_p"],
    "arch_lm_pvalue": ["arch_lm_pvalue", "arch_lm_p", "diag_arch_lm_p"],
    "jarque_bera_pvalue": ["jarque_bera_pvalue", "jarque_bera_p", "diag_jarque_bera_p"],
    "skewness": ["skewness", "skew_resid", "diag_skew_resid"],
    "kurtosis": ["kurtosis", "kurtosis_resid", "diag_kurtosis_resid"],
    "cointegration_pvalue": ["cointegration_pvalue", "coint_p_actual_pred", "diag_coint_p_actual_pred"],
}

STRESS_BUCKET_SOURCES = [
    ("1-4 qtrs", ["stress_1_4_qtrs_mape", "mape_h01_04", "h1_4_mape"]),
    ("5-8 qtrs", ["stress_5_8_qtrs_mape", "mape_h05_08", "h5_8_mape"]),
    ("9-12 qtrs", ["stress_9_12_qtrs_mape", "mape_h09_12", "h9_12_mape"]),
    ("2024+", ["stress_2024plus_mape", "recent_2024_plus_mape", "stress_2024_plus_mape"]),
    ("2022-23", ["stress_2022_23_mape", "policy_2022_23_mape"]),
    ("Annual", ["stress_annual_mape", "annual_mape", "annual_mape_filled"]),
]


def normalise_parquet_candidate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    for canonical, aliases in COLUMN_ALIASES.items():
        values = out[canonical] if canonical in out.columns else pd.Series(pd.NA, index=out.index)
        for alias in aliases:
            existing = first_existing_column(out, [alias])
            if existing is not None:
                values = values.combine_first(out[existing])
        out[canonical] = values
    for column in CORE_PARQUET_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    if "stream_label" in out.columns:
        out["stream_label"] = out["stream_label"].where(out["stream_label"].notna(), out["stream"].map(stream_label))
    if "model_short" in out.columns:
        out["model_short"] = out["model_short"].where(out["model_short"].notna(), out["model"].map(humanize_label))
    bool_columns = [
        "is_current_recommended",
        "is_pure_schiff",
        "is_pdf_reference",
        "is_frontier",
        "is_top_quarterly",
        "is_top_annual",
        "is_distribution_sample",
        "is_extreme_outlier",
        "plot_default_include",
    ]
    for column in bool_columns:
        out[column] = out[column].map(_coerce_bool).fillna(False).astype(bool)
    if not out["plot_default_include"].any():
        out["plot_default_include"] = (
            out["is_current_recommended"]
            | out["is_pure_schiff"]
            | out["is_pdf_reference"]
            | out["is_frontier"]
            | out["is_distribution_sample"]
            | out["is_top_quarterly"]
            | out["is_top_annual"]
        )
    if "candidate_role" in out.columns:
        out["candidate_role"] = out["candidate_role"].fillna("Candidate")
    for column in ["stream_label", "model_short", "source_family", "model_kind", "feature_set", "candidate_role", "include_reason"]:
        if column in out.columns:
            out[column] = out[column].map(humanize_label)
    numeric_columns = [
        column
        for column in CORE_PARQUET_COLUMNS
        if column
        not in {
            "stream",
            "stream_label",
            "model",
            "model_short",
            "source_run",
            "source_file",
            "source_family",
            "model_kind",
            "feature_set",
            "candidate_role",
            "include_reason",
        }
        and not column.startswith("is_")
        and column != "plot_default_include"
    ]
    out = coerce_numeric(out, numeric_columns)
    out = scale_percent_columns(out)
    out = add_stream_fields(out)
    out["is_recommended_finalist"] = out["is_current_recommended"]
    out["is_finalist"] = out["is_current_recommended"]
    out["is_schiff"] = out["is_pure_schiff"]
    out["stage"] = "final"
    out["variant"] = out["feature_set"].fillna("curated").map(humanize_label)
    out["schiff_class"] = out.apply(
        lambda row: "Pure Schiff benchmark"
        if bool(row.get("is_pure_schiff"))
        else schiff_class(row.get("model"), row.get("source_family"), row.get("feature_set")),
        axis=1,
    )
    return out


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        hit = lower.get(candidate.lower())
        if hit is not None:
            return hit
    return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "current"}


__all__ = [
    "COLUMN_ALIASES",
    "CORE_PARQUET_COLUMNS",
    "STRESS_BUCKET_SOURCES",
    "first_existing_column",
    "normalise_parquet_candidate",
]

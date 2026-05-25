"""Diagnostic audit-pack loading and derived diagnostic source tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from model_dashboard.metrics import coerce_numeric, period_key

from .locate import locate_dashboard_file


DIAGNOSTIC_NUMERIC_COLUMNS = [
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


def load_diagnostic_audit_tables(roots: list[Path]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], list[str]]:
    tables: dict[str, pd.DataFrame] = {}
    status: list[dict[str, Any]] = []
    warnings: list[str] = []
    workbook = locate_dashboard_file("model_diagnostic_audit_tables.xlsx", roots)
    if workbook is not None:
        try:
            excel = pd.ExcelFile(workbook)
            for sheet in excel.sheet_names:
                key = sheet.strip().lower().replace(" ", "_")
                tables[key] = excel.parse(sheet)
            status.append(_status_row("diagnostic audit workbook", workbook, sum(len(df) for df in tables.values()), len(tables)))
        except Exception as exc:
            warnings.append(f"Could not read diagnostic audit workbook: {exc}")
    for filename in [
        "model_summary_our_vs_schiff.csv",
        "paired_common_forecast_pairs_our_vs_schiff.csv",
        "h1_residual_diagnostics_our_vs_schiff.csv",
        "diagnostic_pass_matrix.csv",
    ]:
        path = locate_dashboard_file(filename, roots)
        if path is None:
            continue
        try:
            key = path.stem
            tables[key] = pd.read_csv(path, low_memory=False)
            status.append(_status_row(key, path, len(tables[key]), len(tables[key].columns)))
        except Exception as exc:
            warnings.append(f"Could not read {filename}: {exc}")
    return tables, status, warnings


def build_diagnostic_frame(candidate: pd.DataFrame, audit_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    roles = candidate[
        candidate.get("is_current_recommended", pd.Series(False, index=candidate.index)).fillna(False).astype(bool)
        | candidate.get("is_pure_schiff", pd.Series(False, index=candidate.index)).fillna(False).astype(bool)
    ].copy()
    if not roles.empty:
        roles["role"] = roles.apply(
            lambda row: "Our finalist" if bool(row.get("is_current_recommended", False)) else "Schiff benchmark",
            axis=1,
        )
    diag = roles[
        [
            col
            for col in [
                "stream",
                "stream_label",
                "model",
                "model_short",
                "role",
                "is_current_recommended",
                "is_pure_schiff",
                *DIAGNOSTIC_NUMERIC_COLUMNS,
            ]
            if col in roles.columns
        ]
    ].copy()
    h1 = audit_tables.get("h1_residual_diagnostics_our_vs_schiff", audit_tables.get("h1_diagnostics", pd.DataFrame()))
    if not h1.empty:
        h1_norm = h1.rename(
            columns={
                "adf_p_resid": "adf_pvalue",
                "kpss_p_resid": "kpss_pvalue",
                "breusch_pagan_p": "breusch_pagan_pvalue",
                "white_p": "white_pvalue",
                "arch_lm_p": "arch_lm_pvalue",
                "jarque_bera_p": "jarque_bera_pvalue",
                "skew_resid": "skewness",
                "kurtosis_resid": "kurtosis",
                "coint_p_actual_pred": "cointegration_pvalue",
                "mz_r2": "adj_r2",
            }
        )
        keep_cols = [col for col in diag.columns if col in h1_norm.columns]
        if keep_cols:
            diag = pd.concat([diag, h1_norm[keep_cols]], ignore_index=True).drop_duplicates(
                subset=[col for col in ["stream", "model"] if col in keep_cols],
                keep="last",
            )
    if "role" not in diag.columns:
        diag["role"] = diag.apply(
            lambda row: "Our finalist" if bool(row.get("is_current_recommended", False)) else "Schiff benchmark",
            axis=1,
        )
    return coerce_numeric(diag, DIAGNOSTIC_NUMERIC_COLUMNS)


def build_diagnostic_acf_source_table(qpred: pd.DataFrame, max_lag: int = 12) -> pd.DataFrame:
    columns = ["stream_label", "lag", "acf_value", "residual_source", "calculation_method"]
    if qpred is None or qpred.empty or not {"error_pct", "stream_label"}.issubset(qpred.columns):
        return pd.DataFrame(columns=columns)
    data = qpred.dropna(subset=["error_pct", "stream_label"]).copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    if "target_period" in data.columns:
        data["_period_key"] = data["target_period"].map(period_key)
        grouped = (
            data.groupby(["stream_label", "target_period", "_period_key"], dropna=False)["error_pct"]
            .mean()
            .reset_index()
            .sort_values(["stream_label", "_period_key"])
        )
    else:
        data["_period_key"] = range(len(data))
        grouped = data.sort_values(["stream_label", "_period_key"])
    rows: list[dict[str, Any]] = []
    for stream, stream_rows in grouped.groupby("stream_label", dropna=False):
        series = pd.to_numeric(stream_rows["error_pct"], errors="coerce").dropna()
        if len(series) < 4:
            continue
        for lag in range(1, max_lag + 1):
            rows.append(
                {
                    "stream_label": stream,
                    "lag": lag,
                    "acf_value": series.autocorr(lag=lag) if len(series) > lag + 1 else pd.NA,
                    "residual_source": "All selected quarterly prediction residuals, averaged by target period",
                    "calculation_method": "pandas Series.autocorr on mean signed forecast error percentage by lag",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _status_row(dataset: str, found: Path, rows: int | None, columns: int | None) -> dict[str, Any]:
    stat = found.stat()
    return {
        "dataset": dataset,
        "found": True,
        "path": str(found),
        "rows": rows,
        "columns": columns,
        "modified": pd.to_datetime(stat.st_mtime, unit="s").isoformat(),
        "size": _format_size(stat.st_size),
    }


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


__all__ = [
    "build_diagnostic_acf_source_table",
    "build_diagnostic_frame",
    "load_diagnostic_audit_tables",
]

from __future__ import annotations

import html
from typing import Any

import pandas as pd

from .labels import STREAM_LABELS


DIAGNOSTIC_TOOLTIP_COPY = {
    "Calibration R2": (
        "Calibration R-squared. Shows how much observed variation in the target series is explained by the "
        "actual-on-forecast validation regression. High calibration R-squared means forecasts track observed "
        "variation after fitting an intercept and slope, but it is not the model's training fit R-squared."
    ),
    "Calibration R²": (
        "Calibration R-squared. Shows how much observed variation in the target series is explained by the "
        "actual-on-forecast validation regression. High calibration R-squared means forecasts track observed "
        "variation after fitting an intercept and slope, but it is not the model's training fit R-squared."
    ),
    "Durbin-Watson": (
        "Durbin-Watson test. Checks whether regression residuals are serially correlated, especially "
        "first-order autocorrelation. A fail suggests errors may be systematically related over time."
    ),
    "ADF": (
        "Augmented Dickey-Fuller test. A unit-root test used to assess whether a series or residuals are "
        "stationary. Passing generally suggests no unit root is detected."
    ),
    "KPSS": (
        "Kwiatkowski-Phillips-Schmidt-Shin test. A stationarity test that complements ADF by treating "
        "stationarity as the null hypothesis. Passing suggests the series is consistent with stationarity."
    ),
    "Breusch-Pagan": (
        "Breusch-Pagan test. Checks whether residual variance changes systematically with fitted values or "
        "predictors. A fail indicates heteroskedasticity, meaning errors may not have constant variance."
    ),
    "White": (
        "White test. A broader heteroskedasticity test that can detect nonlinear variance patterns linked to "
        "predictors. A fail suggests residual variance is unstable."
    ),
    "Jarque-Bera": (
        "Jarque-Bera test. Checks whether residuals have skewness and kurtosis consistent with a normal "
        "distribution. A watch result means residual normality may be imperfect but not necessarily fatal for "
        "forecasting."
    ),
    "Cointegration": (
        "Cointegration test. Checks whether non-stationary variables share a stable long-run relationship. "
        "Passing reduces spurious-regression risk; failing means use caution, especially beyond short-term "
        "forecasting."
    ),
    "Overall": (
        "Overall diagnostic status. Summarises the combined evidence for the stream. Pass means broadly "
        "supported, Watch means acceptable but monitor, and Fail means an important concern needs review."
    ),
}

DIAGNOSTIC_TEST_ORDER = [
    "Calibration R2",
    "Durbin-Watson",
    "ADF",
    "KPSS",
    "Breusch-Pagan",
    "White",
    "Jarque-Bera",
    "Cointegration",
    "Overall",
]


def diagnostic_tooltip(label: str) -> str:
    return DIAGNOSTIC_TOOLTIP_COPY.get(label, DIAGNOSTIC_TOOLTIP_COPY.get(label.replace("R2", "R²"), ""))


def diagnostic_pass_matrix_html(diagnostics: pd.DataFrame) -> str:
    matrix = diagnostic_pass_matrix_frame(diagnostics)
    if matrix.empty:
        return "<div class='diagnostic-matrix-empty'>Diagnostic pass matrix is not available.</div>"
    headers = ["Stream"] + DIAGNOSTIC_TEST_ORDER
    header_html = "".join(_header_cell(label, idx) for idx, label in enumerate(headers))
    body_rows = []
    for row_index, (_, row) in enumerate(matrix.iterrows()):
        cells = [f"<th scope='row'>{html.escape(str(row['Stream']))}</th>"]
        for column_index, label in enumerate(DIAGNOSTIC_TEST_ORDER, start=1):
            status = str(row[label])
            cells.append(_status_cell(label, status, row_index, column_index))
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<div class='diagnostic-tooltip-matrix' role='region' aria-label='Diagnostic pass matrix with test descriptions'>"
        "<table class='diagnostic-pass-matrix'>"
        "<thead><tr>"
        + header_html
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
        "</div>"
    )


def diagnostic_pass_matrix_frame(diagnostics: pd.DataFrame) -> pd.DataFrame:
    if diagnostics is None or diagnostics.empty:
        return pd.DataFrame(columns=["Stream"] + DIAGNOSTIC_TEST_ORDER)
    rows = diagnostics.copy()
    if "role" in rows.columns:
        rows = rows[rows["role"].astype(str).str.contains("finalist", case=False, na=False)]
    if rows.empty:
        return pd.DataFrame(columns=["Stream"] + DIAGNOSTIC_TEST_ORDER)
    if {"diagnostic_test", "pass_status", "stream_label"}.issubset(rows.columns):
        return _long_matrix_frame(rows)
    return _wide_matrix_frame(rows)


def _long_matrix_frame(rows: pd.DataFrame) -> pd.DataFrame:
    stream_order = [
        "PED VKT per capita",
        "Light RUC volume",
        "Heavy RUC volume",
    ]
    observed = [stream for stream in rows["stream_label"].dropna().astype(str).unique() if stream]
    streams = [stream for stream in stream_order if stream in set(observed)]
    streams.extend(sorted(set(observed).difference(streams)))
    pivot = (
        rows.assign(
            diagnostic_test=pd.Categorical(rows["diagnostic_test"].astype(str), categories=DIAGNOSTIC_TEST_ORDER, ordered=True),
            stream_label=pd.Categorical(rows["stream_label"].astype(str), categories=streams, ordered=True),
        )
        .sort_values(["stream_label", "diagnostic_test"])
        .pivot_table(index="stream_label", columns="diagnostic_test", values="pass_status", aggfunc="first", observed=False)
        .reindex(index=streams, columns=DIAGNOSTIC_TEST_ORDER)
        .fillna("Unavailable")
    )
    out = pivot.reset_index().rename(columns={"stream_label": "Stream"})
    return out[["Stream"] + DIAGNOSTIC_TEST_ORDER]


def _wide_matrix_frame(rows: pd.DataFrame) -> pd.DataFrame:
    table_rows: list[dict[str, str]] = []
    tests = [
        ("Calibration R2", "adj_r2", lambda value: pd.notna(value) and float(value) >= 0.70),
        ("Durbin-Watson", "durbin_watson", lambda value: pd.notna(value) and 1.5 <= float(value) <= 2.5),
        ("ADF", "adf_pvalue", lambda value: pd.notna(value) and float(value) < 0.05),
        ("KPSS", "kpss_pvalue", lambda value: pd.notna(value) and float(value) > 0.05),
        ("Breusch-Pagan", "breusch_pagan_pvalue", lambda value: pd.notna(value) and float(value) > 0.05),
        ("White", "white_pvalue", lambda value: pd.notna(value) and float(value) > 0.05),
        ("Jarque-Bera", "jarque_bera_pvalue", lambda value: "Caution" if pd.notna(value) and float(value) <= 0.05 else "Pass"),
        ("Cointegration", "cointegration_pvalue", lambda value: pd.notna(value) and float(value) < 0.05),
    ]
    for _, row in rows.iterrows():
        statuses: dict[str, str] = {}
        for label, column, rule in tests:
            value = pd.to_numeric(row.get(column), errors="coerce")
            if pd.isna(value):
                status = "Unavailable"
            else:
                result = rule(float(value))
                status = result if isinstance(result, str) else "Pass" if result else "Fail"
            statuses[label] = status
        core_labels = {"Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"}
        core_fail = any(statuses.get(label) == "Fail" for label in core_labels)
        non_core_fail = any(status == "Fail" for label, status in statuses.items() if label not in core_labels)
        caution = any(status in {"Caution", "Watch"} for status in statuses.values())
        if core_fail:
            statuses["Overall"] = "Fail"
        elif non_core_fail or caution:
            statuses["Overall"] = "Watch"
        else:
            statuses["Overall"] = "Pass"
        stream = str(row.get("stream_label", row.get("stream", "Stream")))
        table_rows.append({"Stream": STREAM_LABELS.get(stream, stream), **statuses})
    return pd.DataFrame(table_rows, columns=["Stream"] + DIAGNOSTIC_TEST_ORDER)


def _header_cell(label: str, index: int) -> str:
    if label == "Stream":
        return "<th scope='col'>Stream</th>"
    tooltip = diagnostic_tooltip(label)
    tooltip_id = f"diag-tooltip-header-{index}"
    return (
        "<th scope='col'>"
        f"<span class='diag-tooltip-trigger diag-header-tooltip' tabindex='0' aria-describedby='{tooltip_id}'>"
        f"{html.escape(label)} <span class='diag-info' aria-hidden='true'>ⓘ</span>"
        f"<span class='diag-tooltip-text' role='tooltip' id='{tooltip_id}'>{html.escape(tooltip)}</span>"
        "</span></th>"
    )


def _status_cell(label: str, status: str, row_index: int, column_index: int) -> str:
    tooltip = diagnostic_tooltip(label)
    tooltip_id = f"diag-tooltip-cell-{row_index}-{column_index}"
    css = _status_css(status)
    aria = f"{label}: {status}. {tooltip}"
    return (
        f"<td class='{css}'>"
        f"<span class='diag-tooltip-trigger' tabindex='0' aria-label='{html.escape(aria)}' aria-describedby='{tooltip_id}'>"
        f"{html.escape(status)}"
        f"<span class='diag-tooltip-text' role='tooltip' id='{tooltip_id}'>"
        f"<strong>{html.escape(label)}</strong><br>{html.escape(tooltip)}<br><span>Status: {html.escape(status)}</span>"
        "</span></span></td>"
    )


def _status_css(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "pass":
        return "diag-status diag-status-pass"
    if normalized in {"watch", "caution"}:
        return "diag-status diag-status-watch"
    if normalized == "fail":
        return "diag-status diag-status-fail"
    return "diag-status diag-status-unavailable"

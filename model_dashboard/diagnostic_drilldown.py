"""Glass-box drilldown for the Diagnostic Pass Matrix.

Interface/audit feature only: every number shown comes from the governed
``diagnostic_test_detail`` and ``diagnostic_evidence_series`` tables (built by
``scripts/build_diagnostic_drilldown_pack.py``), which are themselves asserted
consistent with the live pass matrix and diagnostic battery. Nothing here
changes model metrics, statuses or evidence-pack calculations.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .governance_constants import EVIDENCE_PACK_DATA, STREAM_LABELS

STATUS_DOT = {"Pass": "\U0001F7E2", "Watch": "\U0001F7E1", "Fail": "\U0001F534"}
STATUS_COLOR = {"Pass": "#15803d", "Watch": "#b45309", "Fail": "#b91c1c"}

TEST_ORDER = ["Calibration R2", "Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan",
              "White", "Jarque-Bera", "Cointegration", "Overall"]

PLAIN_ENGLISH = {
    "Calibration R2": ("Checks whether the forecasts line up with what actually happened, by regressing "
                       "actuals on forecasts (Mincer-Zarnowitz). This is not the in-sample training R2."),
    "Durbin-Watson": ("Checks whether forecast errors are correlated with their own previous values. "
                      "If errors persist over time, the model may be missing a time-series pattern."),
    "ADF": ("Checks whether the forecast-error series is stationary (mean-reverting) using a unit-root "
            "test. Non-stationary errors would mean the model drifts away from reality over time."),
    "KPSS": ("A complementary stationarity check with the opposite starting assumption to ADF: here the "
             "null is that errors ARE stationary. Passing both ADF and KPSS is strong evidence of stability."),
    "Breusch-Pagan": ("Checks whether the size of forecast errors changes systematically with the level of "
                      "the forecast (or over time). If errors balloon at high volumes, risk is understated there."),
    "White": ("A broader heteroscedasticity check than Breusch-Pagan: it also allows curved and interaction "
              "forms of changing error variance."),
    "Jarque-Bera": ("Checks whether forecast errors look normally distributed (no heavy skew or fat tails). "
                    "Advisory only: non-normal errors affect uncertainty bands, not point accuracy."),
    "Cointegration": ("Checks whether forecasts and actuals share a stable long-run relationship - i.e. they "
                      "do not drift apart permanently even if they diverge quarter to quarter."),
    "Overall": ("The stream-level verdict combining all diagnostics under the governed rules: any core test "
                "failing forces Fail; advisory cautions alone produce Watch."),
}

HOW_TO_READ = {
    "Calibration R2": "Higher is better; a slope near 1 and intercept near 0 in the MZ regression indicate well-calibrated forecasts. The F-statistic tests whether the regression carries real signal.",
    "Durbin-Watson": "Values near 2 suggest no major autocorrelation. Much below 2 means errors persist (positive autocorrelation); much above 2 means they alternate. Governed pass band: 1.5-2.5.",
    "ADF": "Small p-values (< 0.05) reject the unit root - errors are stationary, which is what we want.",
    "KPSS": "Here LARGE p-values are good: p >= 0.05 means we cannot reject stationarity. The reported p is clipped to [0.01, 0.10] by the published test tables.",
    "Breusch-Pagan": "Large p-values (> 0.05) mean no significant variance trend. The LM statistic is the headline; the F-variant is reported alongside.",
    "White": "Large p-values (> 0.05) mean no significant heteroscedasticity, including nonlinear forms.",
    "Jarque-Bera": "Large p-values mean errors look normal. Small p-values flag skew or fat tails - shown as Watch, never a standalone Fail.",
    "Cointegration": "Small p-values (< 0.05) reject 'no cointegration': forecasts and actuals are tied together in the long run.",
    "Overall": "Read the checklist below: core tests govern Pass/Fail; Jarque-Bera is advisory and can only downgrade to Watch.",
}


@st.cache_data(show_spinner=False)
def load_drilldown_tables(signature: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    del signature
    detail = pd.read_parquet(EVIDENCE_PACK_DATA / "diagnostic_test_detail.parquet")
    series = pd.read_parquet(EVIDENCE_PACK_DATA / "diagnostic_evidence_series.parquet")
    acf = pd.read_parquet(EVIDENCE_PACK_DATA / "diagnostic_acf.parquet")
    return detail, series, acf


def drilldown_signature() -> float:
    path = EVIDENCE_PACK_DATA / "diagnostic_test_detail.parquet"
    return path.stat().st_mtime if path.exists() else 0.0


def drilldown_available() -> bool:
    return (EVIDENCE_PACK_DATA / "diagnostic_test_detail.parquet").exists() and (
        EVIDENCE_PACK_DATA / "diagnostic_evidence_series.parquet").exists()


def _fmt(value, digits=4) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(v):
        return "-"
    if v != 0 and abs(v) < 10 ** (-digits):
        return f"{v:.2e}"
    return f"{v:.{digits}f}"


def _layout(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(
        height=height, margin={"l": 40, "r": 16, "t": 28, "b": 36},
        font={"family": "Segoe UI, Inter, Arial, sans-serif", "size": 11.5, "color": "#334155"},
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "font": {"size": 10}},
        hovermode="closest",
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.25)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.25)")
    return fig


def _evidence_chart(test: str, s: pd.DataFrame, acf: pd.DataFrame, row: pd.Series) -> go.Figure | None:
    periods = s["target_period"].tolist()
    # Plot the residuals in the units the governed battery actually tests
    # (native units for PED/Heavy, percentage errors for Light RUC). Older
    # cached packs without the column fall back to native residuals.
    if "test_residual" in s.columns:
        resid = s["test_residual"].to_numpy(float)
        resid_units = str(s["test_residual_units"].iloc[0]) if "test_residual_units" in s.columns else "native units"
    else:
        resid = s["residual"].to_numpy(float)
        resid_units = "native units"
    resid_axis = f"Residual, {resid_units}"
    if test == "Calibration R2":
        fig = go.Figure()
        lo = float(min(s["pred"].min(), s["actual"].min()))
        hi = float(max(s["pred"].max(), s["actual"].max()))
        fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="45-degree line",
                                 line={"dash": "dash", "color": "#94a3b8"}))
        fig.add_trace(go.Scatter(x=s["pred"], y=s["mz_fitted"], mode="lines", name="MZ regression fit",
                                 line={"color": "#b45309", "width": 1.6}))
        fig.add_trace(go.Scatter(x=s["pred"], y=s["actual"], mode="markers", name="Quarters (h=1)",
                                 marker={"size": 7, "color": "#0f4c81", "opacity": 0.8},
                                 customdata=np.array(periods),
                                 hovertemplate="<b>%{customdata}</b><br>Forecast: %{x:,.4s}<br>Actual: %{y:,.4s}<extra></extra>"))
        fig.update_xaxes(title_text="Forecast (h=1)")
        fig.update_yaxes(title_text="Actual")
        return _layout(fig, 320)
    if test == "Durbin-Watson":
        fig = go.Figure()
        fig.add_trace(go.Bar(x=periods, y=resid, name="Residual (governed test units)",
                             marker_color=["#0f4c81" if v >= 0 else "#b91c1c" for v in resid]))
        fig.add_hline(y=0, line_color="#64748b", line_width=1)
        fig.update_xaxes(title_text="Target quarter", tickangle=-45, nticks=12)
        fig.update_yaxes(title_text=resid_axis)
        return _layout(fig, 280)
    if test in ("ADF", "KPSS"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=periods, y=resid, mode="lines+markers", name="Residual series",
                                 line={"color": "#0f4c81", "width": 1.6}, marker={"size": 5}))
        roll = pd.Series(resid).rolling(8, min_periods=4).mean()
        fig.add_trace(go.Scatter(x=periods, y=roll, mode="lines", name="Rolling mean (8q)",
                                 line={"color": "#b45309", "dash": "dot", "width": 1.6}))
        fig.add_hline(y=0, line_color="#64748b", line_width=1)
        fig.update_xaxes(title_text="Target quarter", tickangle=-45, nticks=12)
        fig.update_yaxes(title_text=resid_axis)
        return _layout(fig, 280)
    if test in ("Breusch-Pagan", "White"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=s["pred"], y=resid, mode="markers", name="Residual vs fitted",
                                 marker={"size": 7, "color": "#0f4c81", "opacity": 0.8},
                                 customdata=np.array(periods),
                                 hovertemplate="<b>%{customdata}</b><br>Fitted: %{x:,.4s}<br>Residual: %{y:,.4s}<extra></extra>"))
        fig.add_hline(y=0, line_color="#64748b", line_width=1)
        fig.update_xaxes(title_text="Fitted value (h=1 forecast)")
        fig.update_yaxes(title_text=resid_axis)
        return _layout(fig, 300)
    if test == "Jarque-Bera":
        from plotly.subplots import make_subplots

        z = (resid - resid.mean()) / max(resid.std(ddof=1), 1e-12)
        z_sorted = np.sort(z)
        n = len(z_sorted)
        # Standard-normal quantiles for the Q-Q panel (display only). scipy is
        # optional at dashboard runtime; fall back to histogram-only without it.
        try:
            from math import sqrt

            from scipy.special import erfinv

            theo = np.array([sqrt(2) * erfinv(2 * (i + 0.5) / n - 1) for i in range(n)])
        except Exception:
            theo = None
        if theo is not None:
            fig = make_subplots(rows=1, cols=2, subplot_titles=["Residual histogram", "Normal Q-Q plot"])
            fig.add_trace(go.Histogram(x=z, nbinsx=14, name="Standardised residuals",
                                       marker_color="#0f4c81", opacity=0.85), row=1, col=1)
            fig.add_trace(go.Scatter(x=theo, y=z_sorted, mode="markers", name="Quantiles",
                                     marker={"size": 6, "color": "#0f4c81"}), row=1, col=2)
            lim = float(max(abs(theo).max(), abs(z_sorted).max())) * 1.05
            fig.add_trace(go.Scatter(x=[-lim, lim], y=[-lim, lim], mode="lines", name="Normal reference",
                                     line={"dash": "dash", "color": "#94a3b8"}), row=1, col=2)
        else:
            fig = go.Figure()
            fig.add_trace(go.Histogram(x=z, nbinsx=14, name="Standardised residuals",
                                       marker_color="#0f4c81", opacity=0.85))
            fig.update_xaxes(title_text="Standardised residual")
        return _layout(fig, 300)
    if test == "Cointegration":
        eq = s["equilibrium_error"].to_numpy(float)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=periods, y=eq, mode="lines+markers", name="Equilibrium error",
                                 line={"color": "#0f4c81", "width": 1.6}, marker={"size": 5}))
        fig.add_hline(y=0, line_color="#64748b", line_width=1)
        fig.update_xaxes(title_text="Target quarter", tickangle=-45, nticks=12)
        fig.update_yaxes(title_text="Long-run residual (actual - MZ fit)")
        return _layout(fig, 280)
    return None


def _overall_checklist(detail: pd.DataFrame, stream: str) -> pd.DataFrame:
    rows = detail[(detail["stream"] == stream) & (detail["diagnostic_test"] != "Overall")]
    extra = json.loads(detail[(detail["stream"] == stream)
                              & (detail["diagnostic_test"] == "Overall")]["extra_json"].iloc[0])
    core = set(extra.get("core_tests", []))
    out = rows[["diagnostic_test", "pass_status", "p_value", "statistic"]].copy()
    out["role"] = out["diagnostic_test"].map(lambda t: "Core" if t in core else ("Advisory" if t == "Jarque-Bera" else "Context"))
    out["p-value"] = out["p_value"].map(_fmt)
    out["statistic"] = out["statistic"].map(_fmt)
    return out.rename(columns={"diagnostic_test": "Diagnostic", "pass_status": "Status"})[
        ["Diagnostic", "role", "Status", "statistic", "p-value"]].rename(columns={"role": "Role"})


def render_dialog_body(row: pd.Series, detail: pd.DataFrame, series: pd.DataFrame, acf: pd.DataFrame) -> None:
    stream, test, status = row["stream"], row["diagnostic_test"], row["pass_status"]
    color = STATUS_COLOR.get(status, "#334155")
    st.markdown(
        f"<div style='display:flex;gap:10px;align-items:center;margin-bottom:2px'>"
        f"<span style='background:{color};color:white;border-radius:999px;padding:2px 14px;"
        f"font-weight:700;font-size:0.85rem'>{status}</span>"
        f"<span style='font-size:1.05rem;font-weight:700;color:#0f172a'>{test}</span>"
        f"<span style='color:#64748b'>| {row['stream_label']}</span></div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Model: `{row['model']}` | {row['residual_scope']} | n = {int(row['n_rows'])}")

    left, right = st.columns([1.0, 1.25])
    with left:
        st.markdown("**What this test checks**")
        st.write(PLAIN_ENGLISH[test])
        st.markdown("**How to read the result**")
        st.write(HOW_TO_READ[test])
        st.markdown("**Null hypothesis**")
        st.write(row["null_hypothesis"])
        st.markdown("**Governance threshold**")
        st.write(row["threshold_rule"])
        st.markdown("**Does this block model approval?**")
        st.write(row["blocks_approval"])
    with right:
        c1, c2, c3 = st.columns(3)
        c1.metric(str(row["statistic_name"]), _fmt(row["statistic"]))
        c2.metric("p-value", _fmt(row["p_value"]), help=str(row["p_value_name"]))
        if pd.notna(row["f_statistic"]):
            c3.metric("F-statistic", _fmt(row["f_statistic"], 3),
                      help=f"F p-value: {_fmt(row['f_p_value'])}")
        else:
            c3.metric("F-statistic", "n/a", help="This test has no F-variant; F-statistics apply to the regression-based diagnostics (Calibration/MZ, Breusch-Pagan, White).")
        if test == "Overall":
            st.markdown("**Decision checklist**")
            st.dataframe(_overall_checklist(detail, stream), hide_index=True, use_container_width=True)
        else:
            s = series[series["stream"] == stream].sort_values("target_period")
            try:
                fig = _evidence_chart(test, s, acf, row)
            except Exception:
                fig = None
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        extra = json.loads(row["extra_json"]) if row.get("extra_json") else {}
        if extra and test != "Overall":
            st.caption(" | ".join(f"{k.replace('_', ' ')}: {_fmt(v) if isinstance(v, (int, float)) else v}"
                                  for k, v in extra.items()))
    st.divider()
    st.markdown("**Audit trace**")
    st.caption(f"Source: {row['source_dataset']} | Score basis: {row['score_basis']} | "
               f"Provenance: {row['provenance']}")
    st.caption(str(row["provenance_note"]))


def render_diagnostic_drilldown_section() -> None:
    """Clickable glass-box grid + modal, rendered beneath the pass matrix."""
    if not drilldown_available():
        st.caption("Diagnostic drilldown pack not built. Run scripts/build_diagnostic_drilldown_pack.py.")
        return
    detail, series, acf = load_drilldown_tables(drilldown_signature())
    st.markdown("<div style='font-weight:700;color:#0f172a;margin:0.4rem 0 0.1rem'>"
                "Diagnostic drilldown <span style='color:#64748b;font-weight:500'>"
                "- click any test for the glass-box view</span></div>", unsafe_allow_html=True)
    stream_label = st.radio(
        "Drilldown stream", [STREAM_LABELS[s] for s in ("PED", "LIGHT_RUC", "HEAVY_RUC")],
        horizontal=True, key="drilldown_stream", label_visibility="collapsed",
    )
    rows = detail[detail["stream_label"] == stream_label].set_index("diagnostic_test")
    cols = st.columns(3)
    for i, test in enumerate(TEST_ORDER):
        if test not in rows.index:
            continue
        row = rows.loc[test]
        status = str(row["pass_status"])
        with cols[i % 3]:
            if st.button(f"{STATUS_DOT.get(status, '')} {test} - {status}",
                         key=f"drill_{stream_label}_{test}", use_container_width=True):
                st.session_state["selected_diagnostic"] = {"stream_label": stream_label, "test": test}
    selected = st.session_state.get("selected_diagnostic")
    if selected and selected.get("stream_label") == stream_label:
        row = rows.loc[selected["test"]].copy()
        row["diagnostic_test"] = selected["test"]
        if hasattr(st, "dialog"):
            @st.dialog(f"Diagnostic detail - {selected['test']}", width="large")
            def _show() -> None:
                render_dialog_body(row, detail, series, acf)
                if st.button("Close", key="drill_close"):
                    st.session_state.pop("selected_diagnostic", None)
                    st.rerun()
            _show()
            st.session_state.pop("selected_diagnostic", None)
        else:  # older Streamlit fallback
            with st.container(border=True):
                render_dialog_body(row, detail, series, acf)

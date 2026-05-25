from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .labels import (
    METRIC_COLORS,
    STRESS_BUCKET_ORDER,
    STREAM_COLORS,
    display_model_label,
    format_count,
    format_percent,
    format_pp,
    format_weight,
    horizon_label,
    humanize_label,
    model_alias,
    shorten_model_name,
)
from .metrics import best_by_stream, period_key

STREAM_ORDER = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]


def _stream_order_value(value: Any) -> int:
    try:
        return STREAM_ORDER.index(str(value))
    except ValueError:
        return 99


def apply_layout(fig: go.Figure, title: str | None = None, height: int | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        title={"text": title, "x": 0.02, "xanchor": "left"} if title else None,
        font={"family": "Segoe UI, Inter, Arial, sans-serif", "color": "#334155", "size": 13},
        margin={"l": 40, "r": 24, "t": 56 if title else 28, "b": 44},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0.0},
        hovermode="closest",
        height=height,
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(148, 163, 184, 0.22)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(148, 163, 184, 0.22)", zeroline=False)
    return fig


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return apply_layout(fig, height=320)


def _clean_hover_text(value: Any, max_length: int = 110) -> str:
    text = "" if value is None else str(value)
    if not text or text.lower() == "nan":
        return "-"
    return shorten_model_name(text.replace("_", " "), max_length=max_length)


def _safe_series(data: pd.DataFrame, column: str, default: Any = "") -> pd.Series:
    if column in data.columns:
        return data[column]
    return pd.Series([default] * len(data), index=data.index)


def plot_finalist_accuracy(recommended: pd.DataFrame) -> go.Figure:
    finalists = best_by_stream(recommended).copy()
    if finalists.empty or "quarterly_mape" not in finalists.columns:
        return empty_figure("Recommended finalist data is not available.")
    stream_order = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
    finalists["_stream_order"] = finalists["stream_label"].map(
        {stream: idx for idx, stream in enumerate(stream_order)}
    ).fillna(99)
    finalists = finalists.sort_values(["_stream_order", "stream_label"])
    finalists["stream_plot_label"] = finalists["stream_label"].map(_axis_stream_label)
    finalists["_hover_stream"] = finalists["stream_label"].astype(str)
    finalists["_hover_model"] = _safe_series(finalists, "model").map(display_model_label)
    finalists["_hover_full_model"] = _safe_series(finalists, "model").map(_clean_hover_text)
    finalists["_hover_source"] = _safe_series(finalists, "source_family").map(humanize_label)
    finalists["_hover_variant"] = _safe_series(finalists, "variant").map(humanize_label)
    finalists["_hover_quarterly_mape"] = _safe_series(finalists, "quarterly_mape").map(format_percent)
    finalists["_hover_annual_mape"] = _safe_series(finalists, "annual_mape").map(format_percent)
    fig = go.Figure()
    for metric, column in [("Quarterly MAPE", "quarterly_mape"), ("Annual MAPE", "annual_mape")]:
        if column not in finalists.columns:
            continue
        values = finalists[column]
        fig.add_bar(
            name=metric,
            x=finalists["stream_plot_label"],
            y=values,
            marker_color=METRIC_COLORS[metric],
            text=[f"{value:.2f}%" if pd.notna(value) else "" for value in values],
            textposition="outside",
            customdata=finalists[
                [
                    "_hover_stream",
                    "_hover_model",
                    "_hover_full_model",
                    "_hover_source",
                    "_hover_variant",
                    "_hover_quarterly_mape",
                    "_hover_annual_mape",
                ]
            ].fillna("-").to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                f"Bar shown: {metric}<br>"
                "Quarterly MAPE: %{customdata[5]}<br>"
                "Annual MAPE: %{customdata[6]}<br>"
                "Model: %{customdata[1]}<br>"
                "Full model: %{customdata[2]}<br>"
                "Source: %{customdata[3]}<br>"
                "Variant: %{customdata[4]}<extra></extra>"
            ),
        )
    fig.update_layout(barmode="group", yaxis_title="MAPE (%)", xaxis_title="")
    return apply_layout(fig, "Finalist forecast accuracy", height=420)


def plot_candidate_landscape(summary: pd.DataFrame) -> go.Figure:
    required = {"quarterly_mape", "annual_mape", "stream_label"}
    if summary.empty or not required.issubset(summary.columns):
        return empty_figure("Candidate summary needs quarterly and annual MAPE.")
    data = summary.dropna(subset=["quarterly_mape", "annual_mape"]).copy()
    if data.empty:
        return empty_figure("No candidate rows have both quarterly and annual MAPE.")
    full_data = data.copy()
    full_count = len(data)
    if "candidate_role" not in data.columns:
        data = _competitive_landscape_subset(data)
    data["point_type"] = "Candidate"
    if "is_distribution_sample" in data.columns:
        data.loc[data["is_distribution_sample"].astype(bool), "point_type"] = "Distribution sample"
    if "is_frontier" in data.columns:
        data.loc[data["is_frontier"].astype(bool), "point_type"] = "Frontier candidate"
    if "is_pdf_reference" in data.columns:
        data.loc[data["is_pdf_reference"].astype(bool), "point_type"] = "PDF reference"
    if "is_schiff" in data.columns:
        data.loc[data["is_schiff"].astype(bool), "point_type"] = "Schiff benchmark"
    if "is_pure_schiff" in data.columns:
        data.loc[data["is_pure_schiff"].astype(bool), "point_type"] = "Schiff benchmark"
    if "is_finalist" in data.columns:
        data.loc[data["is_finalist"].astype(bool), "point_type"] = "Selected finalist"
    if "is_recommended_finalist" in data.columns:
        data.loc[data["is_recommended_finalist"].astype(bool), "point_type"] = "Selected finalist"
    if "is_current_recommended" in data.columns:
        data.loc[data["is_current_recommended"].astype(bool), "point_type"] = "Selected finalist"
    data["model_short"] = _safe_series(data, "model").map(display_model_label)
    data["_hover_full_model"] = _safe_series(data, "model").map(_clean_hover_text)
    data["_hover_stage"] = _safe_series(data, "stage").map(humanize_label)
    data["_hover_variant"] = _safe_series(data, "variant").map(humanize_label)
    data["_hover_source"] = _safe_series(data, "source_family").map(humanize_label)
    data["_hover_feature"] = _safe_series(data, "feature_set").map(humanize_label)
    data["_hover_role"] = _safe_series(data, "candidate_role", "Candidate").map(humanize_label)
    data["_hover_bias"] = _safe_series(data, "quarterly_bias_pct").map(format_percent)
    data["_hover_score"] = _safe_series(data, "governance_score").map(lambda value: format_count(value) if value != "" else "-")
    data["_hover_schiff_class"] = _safe_series(data, "schiff_class").map(humanize_label)
    symbol_map = {
        "Distribution sample": "circle",
        "Candidate": "circle",
        "Frontier candidate": "circle",
        "PDF reference": "diamond-open",
        "Schiff benchmark": "triangle-up-open",
        "Selected finalist": "star",
    }
    size_map = {
        "Distribution sample": 6,
        "Candidate": 8,
        "Frontier candidate": 10,
        "PDF reference": 13,
        "Schiff benchmark": 14,
        "Selected finalist": 17,
    }
    fig = go.Figure()
    hover_columns = [
        "stream_label",
        "model_short",
        "_hover_full_model",
        "_hover_stage",
        "_hover_variant",
        "_hover_source",
        "_hover_feature",
        "_hover_role",
        "_hover_bias",
        "_hover_score",
        "_hover_schiff_class",
    ]
    hover_template = (
        "<b>%{customdata[1]}</b><br>"
        "Stream: %{customdata[0]}<br>"
        "Model: %{customdata[1]}<br>"
        "Candidate role: %{customdata[7]}<br>"
        "Quarterly MAPE: %{x:.2f}%<br>"
        "Annual MAPE: %{y:.2f}%<br>"
        "Bias: %{customdata[8]}<br>"
        "Stage: %{customdata[3]}<br>"
        "Variant: %{customdata[4]}<br>"
        "Source: %{customdata[5]}<br>"
        "Feature set: %{customdata[6]}<br>"
        "Governance score: %{customdata[9]}<br>"
        "Schiff class: %{customdata[10]}<br>"
        "Full model: %{customdata[2]}<extra></extra>"
    )
    base = data[data["point_type"].isin(["Distribution sample", "Candidate", "Frontier candidate"])].copy()
    base["_stream_order"] = base["stream_label"].map(_stream_order_value)
    for stream, stream_df in base.sort_values(["_stream_order", "quarterly_mape"]).groupby("stream_label", sort=False, dropna=False):
        frontier_mask = stream_df["point_type"].eq("Frontier candidate")
        sizes = np.where(frontier_mask, 9, 6)
        opacities = np.where(frontier_mask, 0.78, 0.48)
        fig.add_trace(
            go.Scatter(
                x=stream_df["quarterly_mape"],
                y=stream_df["annual_mape"],
                mode="markers",
                name=_legend_stream_label(stream),
                legendgroup=str(stream),
                marker={
                    "symbol": "circle",
                    "size": sizes,
                    "color": STREAM_COLORS.get(str(stream), "#64748B"),
                    "opacity": opacities,
                    "line": {"width": 0.7, "color": "rgba(15,23,42,0.25)"},
                },
                customdata=stream_df.reindex(columns=hover_columns).fillna("-").to_numpy(),
                hovertemplate=hover_template,
            )
        )
    special_specs = [
        ("Selected finalist", "Finalist", "star", 18, "#0f172a", 1.4),
        ("Schiff benchmark", "Schiff", "triangle-up-open", 15, "#0f172a", 1.5),
        ("PDF reference", "PDF reference", "diamond-open", 13, "#0f172a", 1.2),
    ]
    for point_type, legend_name, symbol, size, line_color, line_width in special_specs:
        subset = data[data["point_type"].eq(point_type)].copy()
        if subset.empty:
            continue
        subset["_stream_order"] = subset["stream_label"].map(_stream_order_value)
        subset = subset.sort_values(["_stream_order", "quarterly_mape", "annual_mape"])
        fig.add_trace(
            go.Scatter(
                x=subset["quarterly_mape"],
                y=subset["annual_mape"],
                mode="markers",
                name=legend_name,
                legendgroup=legend_name,
                marker={
                    "symbol": symbol,
                    "size": size,
                    "color": [STREAM_COLORS.get(str(stream), "#64748B") for stream in subset["stream_label"]],
                    "opacity": 0.96,
                    "line": {"width": line_width, "color": line_color},
                },
                customdata=subset.reindex(columns=hover_columns).fillna("-").to_numpy(),
                hovertemplate=hover_template,
            )
        )
    frontier = _efficient_frontier(data)
    if len(frontier) >= 2:
        fig.add_trace(
            go.Scatter(
                x=frontier["quarterly_mape"],
                y=frontier["annual_mape"],
                mode="lines",
                name="Efficient frontier",
                line={"color": "#0f172a", "width": 2, "dash": "dot"},
                hoverinfo="skip",
            )
        )
    annotation_rows = []
    for point_type in ["Selected finalist", "Schiff benchmark"]:
        subset = data[data["point_type"] == point_type].sort_values(["stream_label", "quarterly_mape", "annual_mape"])
        if subset.empty:
            continue
        annotation_rows.append(subset.groupby("stream_label", as_index=False).head(1))
    annotated = pd.concat(annotation_rows, ignore_index=True) if annotation_rows else pd.DataFrame()
    for _, row in annotated.head(8).iterrows():
        stream_short = str(row.get("stream_label", "")).replace(" VKT per capita", "").replace(" volume", "")
        fig.add_annotation(
            x=row["quarterly_mape"],
            y=row["annual_mape"],
            text=f"{stream_short} finalist" if row["point_type"] == "Selected finalist" else f"{stream_short} Schiff",
            showarrow=True,
            arrowhead=2,
            ax=18,
            ay=-16,
            font={"size": 10, "color": "#0f172a"},
            bgcolor="rgba(255,255,255,0.82)",
            bordercolor="rgba(15,23,42,0.18)",
        )
    fig.update_layout(xaxis_title="Quarterly MAPE (%)", yaxis_title="Annual MAPE (%)")
    fig = apply_layout(fig, "Candidate search landscape", height=580)
    critical_points = data[data["point_type"].isin(["Schiff benchmark", "Selected finalist"])]
    x_limit = _frontier_axis_limit(full_data["quarterly_mape"], critical_points["quarterly_mape"])
    y_limit = _frontier_axis_limit(full_data["annual_mape"], critical_points["annual_mape"])
    if x_limit is not None:
        fig.update_xaxes(range=[0, x_limit])
    if y_limit is not None:
        fig.update_yaxes(range=[0, y_limit])
    if (
        full_count > len(data)
        or
        (x_limit is not None and data["quarterly_mape"].max() > x_limit)
        or (y_limit is not None and data["annual_mape"].max() > y_limit)
    ):
        fig.add_annotation(
            text=f"Axis focuses on the competitive frontier; plotting {len(data):,} of {full_count:,} candidates with full rows in inventory/downloads.",
            x=0.0,
            y=-0.18,
            xref="paper",
            yref="paper",
            showarrow=False,
            align="left",
            font={"size": 11, "color": "#64748b"},
        )
    fig.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0.0,
            "font": {"size": 10},
        },
        margin={"l": 40, "r": 20, "t": 58, "b": 48},
    )
    return fig


def _competitive_landscape_subset(data: pd.DataFrame, max_rows: int = 420) -> pd.DataFrame:
    """Keep the default candidate chart focused without dropping governance anchors."""
    if len(data) <= max_rows:
        return data.copy()
    keep = pd.Series(False, index=data.index)
    if "is_finalist" in data.columns:
        keep = keep | data["is_finalist"].fillna(False).astype(bool)
    if "is_schiff" in data.columns:
        keep = keep | data["is_schiff"].fillna(False).astype(bool)
    for _, stream_rows in data.groupby("stream_label", dropna=False):
        keep.loc[stream_rows.nsmallest(40, "quarterly_mape").index] = True
        keep.loc[stream_rows.nsmallest(40, "annual_mape").index] = True
        frontier = _efficient_frontier(stream_rows)
        keep.loc[frontier.index.intersection(data.index)] = True
    subset = data[keep].copy()
    if len(subset) > max_rows:
        protected = pd.Series(False, index=subset.index)
        if "is_finalist" in subset.columns:
            protected = protected | subset["is_finalist"].fillna(False).astype(bool)
        if "is_schiff" in subset.columns:
            protected = protected | subset["is_schiff"].fillna(False).astype(bool)
        score = pd.to_numeric(subset["quarterly_mape"], errors="coerce").rank(method="first") + pd.to_numeric(
            subset["annual_mape"], errors="coerce"
        ).rank(method="first")
        chosen = subset[protected]
        remaining_slots = max(max_rows - len(chosen), 0)
        ranked = subset[~protected].assign(_rank_score=score[~protected]).nsmallest(remaining_slots, "_rank_score")
        subset = pd.concat([chosen, ranked.drop(columns=["_rank_score"], errors="ignore")], axis=0)
    return subset.sort_values(["stream_label", "quarterly_mape", "annual_mape"])


def _efficient_frontier(data: pd.DataFrame) -> pd.DataFrame:
    cols = ["quarterly_mape", "annual_mape"]
    if data.empty or not set(cols).issubset(data.columns):
        return pd.DataFrame(columns=cols)
    ordered = data.dropna(subset=cols).sort_values(["quarterly_mape", "annual_mape"]).copy()
    frontier_rows = []
    best_annual = float("inf")
    for _, row in ordered.iterrows():
        annual = float(row["annual_mape"])
        if annual < best_annual:
            frontier_rows.append(row)
            best_annual = annual
    return pd.DataFrame(frontier_rows)


def _frontier_axis_limit(values: pd.Series, anchors: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    anchor_numeric = pd.to_numeric(anchors, errors="coerce").dropna()
    # The curated landscape intentionally keeps a few weak tail candidates for
    # context. Use the dense 90th percentile, plus governance anchors, so those
    # tails do not flatten the optimisation cone by default.
    quantile_cap = numeric.quantile(0.90)
    anchor_cap = anchor_numeric.max() if not anchor_numeric.empty else 0
    cap = max(float(quantile_cap), float(anchor_cap)) * 1.18
    if not pd.notna(cap) or cap <= 0:
        return None
    full_max = numeric.max()
    if full_max <= cap * 1.08:
        return None
    return max(cap, 5.0)


def _legend_stream_label(value: Any) -> str:
    return str(value).replace(" VKT per capita", "").replace(" volume", "")


def _axis_stream_label(value: Any) -> str:
    text = str(value)
    return (
        text.replace("PED VKT per capita", "PED VKT<br>per capita")
        .replace("Light RUC volume", "Light RUC<br>volume")
        .replace("Heavy RUC volume", "Heavy RUC<br>volume")
    )


def plot_schiff_benchmark(summary: pd.DataFrame) -> go.Figure:
    if summary.empty or "is_schiff" not in summary.columns:
        return empty_figure("No Schiff benchmark rows were detected.")
    schiff = summary[summary["is_schiff"]].copy()
    if schiff.empty:
        return empty_figure("No Schiff benchmark rows were detected.")
    schiff = best_by_stream(schiff)
    schiff["_hover_model"] = _safe_series(schiff, "model").map(display_model_label)
    schiff["_hover_full_model"] = _safe_series(schiff, "model").map(_clean_hover_text)
    schiff["_hover_source"] = _safe_series(schiff, "source_family").map(humanize_label)
    fig = go.Figure()
    for metric, column in [("Quarterly MAPE", "quarterly_mape"), ("Annual MAPE", "annual_mape")]:
        if column in schiff.columns:
            fig.add_bar(
                name=metric,
                x=schiff["stream_label"],
                y=schiff[column],
                marker_color=METRIC_COLORS[metric],
                text=[f"{value:.2f}%" if pd.notna(value) else "" for value in schiff[column]],
                textposition="outside",
                customdata=schiff[["_hover_model", "_hover_full_model", "_hover_source"]].fillna("-").to_numpy(),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    f"{metric}: %{{y:.2f}}%<br>"
                    "Model: %{customdata[0]}<br>"
                    "Full model: %{customdata[1]}<br>"
                    "Source: %{customdata[2]}<extra></extra>"
                ),
            )
    fig.update_layout(barmode="group", yaxis_title="MAPE (%)", xaxis_title="")
    return apply_layout(fig, "Schiff structural benchmark: quarterly and annual MAPE", height=420)


def plot_paired_improvement(paired: pd.DataFrame, top_n: int = 30) -> go.Figure:
    if paired.empty or "mape_improvement_pct_points" not in paired.columns:
        return empty_figure("Paired Schiff comparison data is not available.")
    data = paired.dropna(subset=["mape_improvement_pct_points"]).copy()
    if data.empty:
        return empty_figure("Paired comparison rows do not include improvement values.")
    data["challenger_short"] = data["challenger"].map(display_model_label)
    data["_hover_stage"] = _safe_series(data, "stage").map(humanize_label)
    data["_hover_baseline_mape"] = _safe_series(data, "baseline_mape").map(format_percent)
    data["_hover_challenger_mape"] = _safe_series(data, "challenger_mape").map(format_percent)
    data["_hover_gain"] = _safe_series(data, "mape_improvement_pct_points").map(format_pp)
    data["_hover_win_rate"] = _safe_series(data, "challenger_win_rate").map(format_percent)
    data["_hover_pairs"] = _safe_series(data, "n_common_pairs").map(format_count)
    data = data.sort_values("mape_improvement_pct_points", ascending=True).tail(top_n)
    fig = px.bar(
        data,
        x="mape_improvement_pct_points",
        y="challenger_short",
        color="stream_label",
        orientation="h",
        color_discrete_map=STREAM_COLORS,
        labels={"mape_improvement_pct_points": "MAPE gain vs Schiff (percentage points)", "challenger_short": ""},
        custom_data=[
            "stream_label",
            "challenger_short",
            "_hover_stage",
            "_hover_baseline_mape",
            "_hover_challenger_mape",
            "_hover_gain",
            "_hover_win_rate",
            "_hover_pairs",
        ],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[1]}</b><br>"
            "Stream: %{customdata[0]}<br>"
            "Stage: %{customdata[2]}<br>"
            "Schiff MAPE: %{customdata[3]}<br>"
            "Challenger MAPE: %{customdata[4]}<br>"
            "Gain vs Schiff: %{customdata[5]}<br>"
            "Win rate: %{customdata[6]}<br>"
            "Common pairs: %{customdata[7]}<extra></extra>"
        )
    )
    fig.add_vline(x=0, line_width=1, line_color="#64748B")
    return apply_layout(fig, "Paired gain versus Schiff", height=max(420, min(900, 120 + top_n * 22)))


def plot_paired_scatter(paired: pd.DataFrame) -> go.Figure:
    if paired.empty or not {"baseline_mape", "challenger_mape"}.issubset(paired.columns):
        return empty_figure("Paired MAPE columns are not available.")
    data = paired.dropna(subset=["baseline_mape", "challenger_mape"]).copy()
    if data.empty:
        return empty_figure("No paired rows have both baseline and challenger MAPE.")
    data["challenger_short"] = data["challenger"].map(display_model_label)
    data["_hover_stage"] = _safe_series(data, "stage").map(humanize_label)
    data["_hover_baseline"] = _safe_series(data, "baseline").map(display_model_label)
    data["_hover_gain"] = _safe_series(data, "mape_improvement_pct_points").map(format_pp)
    data["_hover_win_rate"] = _safe_series(data, "challenger_win_rate").map(format_percent)
    fig = px.scatter(
        data,
        x="baseline_mape",
        y="challenger_mape",
        color="stream_label",
        color_discrete_map=STREAM_COLORS,
        hover_name="challenger_short",
        custom_data=["stream_label", "challenger_short", "_hover_stage", "_hover_baseline", "_hover_gain", "_hover_win_rate"],
        labels={"baseline_mape": "Schiff MAPE (%)", "challenger_mape": "Challenger MAPE (%)"},
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[1]}</b><br>"
            "Stream: %{customdata[0]}<br>"
            "Stage: %{customdata[2]}<br>"
            "Baseline: %{customdata[3]}<br>"
            "Schiff MAPE: %{x:.2f}%<br>"
            "Challenger MAPE: %{y:.2f}%<br>"
            "Gain vs Schiff: %{customdata[4]}<br>"
            "Win rate: %{customdata[5]}<extra></extra>"
        )
    )
    max_value = max(data["baseline_mape"].max(), data["challenger_mape"].max())
    min_value = min(data["baseline_mape"].min(), data["challenger_mape"].min())
    fig.add_trace(
        go.Scatter(
            x=[min_value, max_value],
            y=[min_value, max_value],
            mode="lines",
            line={"dash": "dash", "color": "#64748B"},
            name="No gain line",
            hoverinfo="skip",
        )
    )
    return apply_layout(fig, "Baseline versus challenger MAPE", height=460)


def plot_ensemble_composition(weights: pd.DataFrame) -> tuple[go.Figure, pd.DataFrame]:
    if weights.empty or "component_model" not in weights.columns:
        return empty_figure("Ensemble weight data is not available."), pd.DataFrame()
    data = weights.copy()
    if "weight" in data.columns and data["weight"].notna().any():
        grouped = (
            data.groupby(["stream_label", "ensemble", "component_model"], dropna=False)["weight"]
            .mean()
            .reset_index()
        )
        if grouped["weight"].sum() <= len(grouped) * 1.5:
            grouped["weight_pct"] = grouped["weight"] * 100.0
        else:
            grouped["weight_pct"] = grouped["weight"]
        if grouped["weight_pct"].abs().gt(1e-6).any():
            grouped = grouped[grouped["weight_pct"].abs().gt(1e-6)]
    else:
        grouped = data.groupby(["stream_label", "ensemble", "component_model"], dropna=False).size().reset_index(name="n")
        grouped["weight_pct"] = grouped.groupby(["stream_label", "ensemble"])["n"].transform(lambda col: 100.0 / len(col))
    if grouped.empty:
        return empty_figure("No non-zero ensemble weights were available."), pd.DataFrame()
    grouped = grouped.sort_values(["stream_label", "weight_pct"], ascending=[True, False])
    grouped["_hover_ensemble"] = _safe_series(grouped, "ensemble").map(display_model_label)
    grouped["_hover_component"] = _safe_series(grouped, "component_model").map(display_model_label)
    grouped["_hover_full_component"] = _safe_series(grouped, "component_model").map(_clean_hover_text)
    grouped["_hover_weight"] = grouped["weight_pct"].map(format_weight)
    grouped["component_label"] = ""
    mapping_rows: list[dict[str, Any]] = []
    for (_, ensemble), group in grouped.groupby(["stream_label", "ensemble"], dropna=False):
        for idx, row_index in enumerate(group.index, start=1):
            label = f"C{idx}"
            grouped.loc[row_index, "component_label"] = label
            mapping_rows.append(
                {
                    "Stream": grouped.loc[row_index, "stream_label"],
                    "Ensemble": ensemble,
                    "Label": label,
                    "Full component model name": grouped.loc[row_index, "component_model"],
                    "Average weight (%)": grouped.loc[row_index, "weight_pct"],
                }
            )
    stream_order = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
    streams = [stream for stream in stream_order if stream in set(grouped["stream_label"].dropna())]
    streams.extend([stream for stream in grouped["stream_label"].dropna().drop_duplicates() if stream not in streams])
    fig = make_subplots(
        rows=1,
        cols=len(streams),
        shared_yaxes=False,
        horizontal_spacing=0.08 if len(streams) > 1 else 0.04,
        subplot_titles=[_legend_stream_label(stream) for stream in streams],
    )
    for col_number, stream in enumerate(streams, start=1):
        stream_data = grouped[grouped["stream_label"] == stream].sort_values("weight_pct", ascending=True)
        x_cap = max(35.0, float(pd.to_numeric(stream_data["weight_pct"], errors="coerce").max()) * 1.22)
        fig.add_trace(
            go.Bar(
                x=stream_data["weight_pct"],
                y=stream_data["component_label"],
                orientation="h",
                marker_color=STREAM_COLORS.get(str(stream), "#64748B"),
                text=stream_data["weight_pct"].map(lambda value: f"{value:.1f}%"),
                textposition="outside",
                cliponaxis=False,
                customdata=stream_data[
                    ["stream_label", "_hover_ensemble", "_hover_component", "_hover_full_component", "_hover_weight"]
                ].fillna("-").to_numpy(),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Stream: %{customdata[0]}<br>"
                    "Weight: %{customdata[4]}<br>"
                    "Ensemble: %{customdata[1]}<br>"
                    "Component: %{customdata[2]}<br>"
                    "Full component: %{customdata[3]}<extra></extra>"
                ),
                name=str(stream),
                showlegend=False,
            ),
            row=1,
            col=col_number,
        )
        fig.update_yaxes(title_text="", row=1, col=col_number)
        fig.update_xaxes(title_text="Weight (%)", range=[0, x_cap], row=1, col=col_number)
    fig.update_layout(showlegend=False)
    height = 390 if len(grouped) <= 10 else max(430, min(620, 260 + 18 * len(grouped)))
    return apply_layout(fig, "Finalist ensemble composition", height=height), pd.DataFrame(mapping_rows)


def plot_weight_over_time(weights: pd.DataFrame, label_mapping: pd.DataFrame) -> go.Figure:
    if weights.empty or "origin" not in weights.columns or "weight" not in weights.columns:
        return empty_figure("Prequential origin weights are not available.")
    data = weights[(weights["origin"].astype(str).str.len() > 0) & weights["weight"].notna()].copy()
    if data.empty or data["origin"].nunique() < 2:
        return empty_figure("No origin-level weight history for the selected ensemble.")
    label_lookup = dict(
        zip(
            label_mapping["Full component model name"],
            label_mapping["Label"],
            strict=False,
        )
    )
    data["component_label"] = data["component_model"].map(label_lookup).fillna(data["component_model"].map(shorten_model_name))
    weight_values = pd.to_numeric(data["weight"], errors="coerce")
    data["_hover_weight_value"] = weight_values * 100.0 if weight_values.max() <= 1.5 else weight_values
    data["_hover_component"] = _safe_series(data, "component_model").map(display_model_label)
    data["_hover_weight"] = data["_hover_weight_value"].map(format_weight)
    data["origin_key"] = data["origin"].map(period_key)
    data = data.sort_values(["component_label", "origin_key"])
    fig = px.line(
        data,
        x="origin",
        y="weight",
        color="component_label",
        markers=True,
        labels={"origin": "Forecast origin", "weight": "Weight"},
        custom_data=["_hover_component", "_hover_weight"],
    )
    fig.update_traces(
        line={"width": 2.1},
        marker={"size": 6},
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Forecast origin: %{x}<br>"
            "Weight: %{customdata[1]}<extra></extra>"
        )
    )
    if data["weight"].max() <= 1.5:
        fig.update_yaxes(tickformat=".0%")
    return apply_layout(fig, "Weight path by forecast origin", height=420)


def plot_actual_vs_predicted(qpred: pd.DataFrame) -> go.Figure:
    if qpred.empty or not {"actual", "pred"}.issubset(qpred.columns):
        return empty_figure("Quarterly prediction rows need actual and predicted values.")
    data = qpred.copy()
    if "target_period" in data.columns:
        data["_period_key"] = data["target_period"].map(period_key)
        data = data.sort_values("_period_key")
        x = data["target_period"]
    else:
        x = list(range(len(data)))
    fig = go.Figure()
    hover_stream = _safe_series(data, "stream_label").astype(str)
    hover_model = _safe_series(data, "model").map(display_model_label)
    hover_horizon = _safe_series(data, "horizon").map(format_count)
    customdata = pd.DataFrame(
        {
            "stream": hover_stream,
            "model": hover_model,
            "horizon": hover_horizon,
        },
        index=data.index,
    ).fillna("-").to_numpy()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=data["actual"],
            mode="lines+markers",
            name="Actual",
            line={"color": "#0f172a"},
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Target period: %{x}<br>"
                "Actual: %{y:,.0f}<br>"
                "Model: %{customdata[1]}<br>"
                "Horizon: %{customdata[2]} quarters<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=data["pred"],
            mode="lines+markers",
            name="Predicted",
            line={"color": "#1f77b4"},
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Target period: %{x}<br>"
                "Predicted: %{y:,.0f}<br>"
                "Model: %{customdata[1]}<br>"
                "Horizon: %{customdata[2]} quarters<extra></extra>"
            ),
        )
    )
    fig.update_layout(xaxis_title="Target period", yaxis_title="Volume / index")
    return apply_layout(fig, "Actual versus predicted held-out forecast", height=460)


def plot_residual_vs_fitted(qpred: pd.DataFrame) -> go.Figure:
    required = {"pred", "error_pct", "stream_label"}
    if qpred.empty or not required.issubset(qpred.columns):
        return empty_figure("Prediction rows need fitted values and percentage errors.")
    data = qpred.dropna(subset=["pred", "error_pct"]).copy()
    if data.empty:
        return empty_figure("No valid residual proxy rows are available.")
    full_count = len(data)
    data = _sample_by_stream(data, max_rows=6000)
    data["pred_native"] = pd.to_numeric(data["pred"], errors="coerce")
    data["_hover_model"] = _safe_series(data, "model").map(display_model_label)
    data["_hover_period"] = _safe_series(data, "target_period").map(_clean_hover_text)
    data["_hover_horizon"] = _safe_series(data, "horizon").map(format_count)
    data["_hover_error"] = data["error_pct"].map(format_percent)
    streams = [stream for stream in STREAM_ORDER if stream in set(data["stream_label"].astype(str))]
    streams.extend(sorted(set(data["stream_label"].astype(str)).difference(streams)))
    fig = make_subplots(rows=1, cols=len(streams), subplot_titles=streams, shared_yaxes=True, horizontal_spacing=0.06)
    for col, stream in enumerate(streams, start=1):
        stream_rows = data[data["stream_label"].astype(str).eq(stream)]
        fig.add_trace(
            go.Scatter(
                x=stream_rows["pred_native"],
                y=stream_rows["error_pct"],
                mode="markers",
                name=stream,
                marker={
                    "color": STREAM_COLORS.get(stream, "#64748B"),
                    "size": 4.5,
                    "opacity": 0.52,
                    "line": {"width": 0},
                },
                customdata=stream_rows[["stream_label", "_hover_period", "_hover_model", "_hover_horizon", "_hover_error"]].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Target period: %{customdata[1]}<br>"
                    "Fitted value: %{x:,.4g} native units<br>"
                    "Forecast error: %{customdata[4]}<br>"
                    "Model: %{customdata[2]}<br>"
                    "Horizon: %{customdata[3]} quarters<extra></extra>"
                ),
                showlegend=False,
            ),
            row=1,
            col=col,
        )
        fig.add_hline(y=0, line_dash="dash", line_color="#64748B", row=1, col=col)
        fig.update_xaxes(title_text="Fitted value, native units", row=1, col=col)
    fig.update_yaxes(title_text="Residual / forecast error (%)", row=1, col=1)
    if full_count > len(data):
        fig.add_annotation(
            text=f"Rendered deterministic sample: {len(data):,} of {full_count:,} residual rows.",
            x=0,
            y=-0.18,
            xref="paper",
            yref="paper",
            showarrow=False,
            align="left",
            font={"size": 11, "color": "#64748b"},
        )
    fig.update_layout(showlegend=False)
    return apply_layout(fig, "Residuals vs fitted by stream", height=360)


def _sample_by_stream(data: pd.DataFrame, max_rows: int = 6000) -> pd.DataFrame:
    if len(data) <= max_rows:
        return data.copy()
    if "stream_label" not in data.columns:
        return data.sample(n=max_rows, random_state=42).sort_index()
    pieces = []
    per_stream = max(1, max_rows // max(1, data["stream_label"].nunique()))
    for _, group in data.groupby("stream_label", dropna=False):
        pieces.append(group.sample(n=min(len(group), per_stream), random_state=42))
    sampled = pd.concat(pieces).sort_index()
    if len(sampled) > max_rows:
        sampled = sampled.sample(n=max_rows, random_state=42).sort_index()
    return sampled


def plot_autocorrelation_diagnostics(
    qpred: pd.DataFrame,
    max_lag: int = 12,
    acf_source: pd.DataFrame | None = None,
) -> go.Figure:
    if acf_source is not None and not acf_source.empty:
        required_source = {"stream_label", "lag", "acf_value", "residual_source"}
        if required_source.issubset(acf_source.columns):
            source = acf_source.dropna(subset=["stream_label", "lag", "acf_value"]).copy()
            if not source.empty:
                fig = go.Figure()
                source["_stream_order"] = source["stream_label"].map(_stream_order_value)
                source = source.sort_values(["_stream_order", "lag"])
                for stream, stream_rows in source.groupby("stream_label", dropna=False):
                    fig.add_bar(
                        x=stream_rows["lag"],
                        y=stream_rows["acf_value"],
                        name=str(stream),
                        marker_color=STREAM_COLORS.get(str(stream), "#1f77b4"),
                        customdata=stream_rows[["stream_label", "residual_source", "calculation_method"]]
                        .fillna("-")
                        .to_numpy(),
                        hovertemplate=(
                            "<b>%{customdata[0]}</b><br>"
                            "Lag: %{x}<br>"
                            "ACF: %{y:.2f}<br>"
                            "Residual source: %{customdata[1]}<br>"
                            "Method: %{customdata[2]}<extra></extra>"
                        ),
                    )
                fig.add_hline(y=0, line_color="#64748B", line_width=1)
                fig.add_hline(y=0.45, line_dash="dash", line_color="#94A3B8", annotation_text="approx. caution band")
                fig.add_hline(y=-0.45, line_dash="dash", line_color="#94A3B8")
                fig.update_layout(
                    barmode="group",
                    xaxis_title="Lag (quarters)",
                    yaxis_title="Residual ACF",
                    yaxis_range=[-1, 1],
                )
                return apply_layout(fig, "Residual ACF by lag", height=360)
    required = {"error_pct", "stream_label"}
    if qpred is None or qpred.empty or not required.issubset(qpred.columns):
        return empty_figure("Prediction rows need signed forecast errors for autocorrelation diagnostics.")
    data = qpred.dropna(subset=["error_pct", "stream_label"]).copy()
    if data.empty:
        return empty_figure("No valid signed forecast-error rows are available.")
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

    fig = go.Figure()
    for stream, stream_rows in grouped.groupby("stream_label", dropna=False):
        series = pd.to_numeric(stream_rows["error_pct"], errors="coerce").dropna()
        if len(series) < 4:
            continue
        lags = list(range(1, max_lag + 1))
        acf_values = [series.autocorr(lag=lag) if len(series) > lag + 1 else None for lag in lags]
        residual_source = "All selected quarterly residuals, averaged by target period"
        fig.add_bar(
            x=lags,
            y=acf_values,
            name=str(stream),
            marker_color=STREAM_COLORS.get(str(stream), "#1f77b4"),
            customdata=[[str(stream), residual_source] for _ in lags],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Lag: %{x}<br>"
                "ACF: %{y:.2f}<br>"
                "Residual source: %{customdata[1]}<extra></extra>"
            ),
        )
    if not fig.data:
        return empty_figure("Not enough residual rows to compute lag autocorrelation.")
    fig.add_hline(y=0, line_color="#64748B", line_width=1)
    fig.add_hline(y=0.45, line_dash="dash", line_color="#94A3B8", annotation_text="approx. caution band")
    fig.add_hline(y=-0.45, line_dash="dash", line_color="#94A3B8")
    fig.update_layout(
        barmode="group",
        xaxis_title="Lag (quarters)",
        yaxis_title="Residual ACF",
        yaxis_range=[-1, 1],
    )
    return apply_layout(fig, "Residual ACF by lag", height=360)


def plot_percent_error_over_time(qpred: pd.DataFrame) -> go.Figure:
    if qpred.empty or "error_pct" not in qpred.columns:
        return empty_figure("Quarterly prediction rows need percentage-error values.")
    data = qpred.dropna(subset=["error_pct"]).copy()
    if data.empty:
        return empty_figure("No valid percentage-error rows are available.")
    if "target_period" in data.columns:
        data["_period_key"] = data["target_period"].map(period_key)
        data = data.sort_values("_period_key")
        x = data["target_period"]
    else:
        x = list(range(len(data)))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=data["error_pct"],
            mode="lines+markers",
            name="Forecast error",
            line={"color": "#ff7f0e"},
            customdata=pd.DataFrame(
                {
                    "stream": _safe_series(data, "stream_label").astype(str),
                    "model": _safe_series(data, "model").map(display_model_label),
                    "horizon": _safe_series(data, "horizon").map(format_count),
                },
                index=data.index,
            ).fillna("-").to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Target period: %{x}<br>"
                "Forecast error: %{y:.2f}%<br>"
                "Model: %{customdata[1]}<br>"
                "Horizon: %{customdata[2]} quarters<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_dash="dash", line_color="#64748B", annotation_text="No bias")
    fig.update_layout(xaxis_title="Target period", yaxis_title="Forecast error (%)")
    return apply_layout(fig, "Forecast percentage error over time", height=360)


def plot_error_distribution(qpred: pd.DataFrame) -> go.Figure:
    if qpred.empty or "ape" not in qpred.columns or "horizon_bucket" not in qpred.columns:
        return empty_figure("Quarterly prediction rows need error and horizon-bucket fields.")
    bucket_order = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs"]
    fig = go.Figure()
    stream_order = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
    observed_streams = [stream for stream in pd.unique(qpred["stream_label"].dropna()) if str(stream)]
    streams = [stream for stream in stream_order if stream in set(observed_streams)]
    streams.extend([stream for stream in observed_streams if stream not in streams])
    if not streams:
        return empty_figure("No stream labels were found for forecast-error distribution.")

    bucket_codes = pd.Categorical(qpred["horizon_bucket"], categories=bucket_order, ordered=True).codes
    stream_codes = pd.Categorical(qpred["stream_label"], categories=streams, ordered=True).codes
    if pd.api.types.is_numeric_dtype(qpred["ape"]):
        ape_values = qpred["ape"].to_numpy(dtype=float, copy=False)
    else:
        ape_values = pd.to_numeric(qpred["ape"], errors="coerce").to_numpy(dtype=float, copy=False)
    valid = (bucket_codes >= 0) & (stream_codes >= 0) & np.isfinite(ape_values)
    if not np.any(valid):
        return empty_figure("No 1-12 quarter forecast errors were found.")

    bucket_colors = {"1-4 qtrs": "#9ecae1", "5-8 qtrs": "#fdd0a2", "9-12 qtrs": "#a1d99b"}

    stat_rows: list[dict[str, Any]] = []
    n_streams = len(streams)
    group_codes = bucket_codes * n_streams + stream_codes
    for bucket_idx, bucket in enumerate(bucket_order):
        for stream_idx, stream in enumerate(streams):
            code = bucket_idx * n_streams + stream_idx
            array = ape_values[valid & (group_codes == code)]
            if array.size == 0:
                continue
            q1, median, q3 = np.percentile(array, [25, 50, 75])
            stat_rows.append(
                {
                    "horizon_bucket": bucket,
                    "stream_label": stream,
                    "q1": q1,
                    "median": median,
                    "q3": q3,
                    "minimum": float(np.nanmin(array)),
                    "maximum": float(np.nanmax(array)),
                    "rows": int(array.size),
                }
            )
    grouped = pd.DataFrame(stat_rows)
    if grouped.empty:
        return empty_figure("No 1-12 quarter forecast errors were found.")
    grouped["iqr"] = grouped["q3"] - grouped["q1"]
    lower_candidate = grouped["q1"] - 1.5 * grouped["iqr"]
    upper_candidate = grouped["q3"] + 1.5 * grouped["iqr"]
    grouped["lower"] = lower_candidate.where(lower_candidate > grouped["minimum"], grouped["minimum"])
    grouped["upper"] = upper_candidate.where(upper_candidate < grouped["maximum"], grouped["maximum"])
    grouped["_stream_order"] = grouped["stream_label"].map({stream: idx for idx, stream in enumerate(streams)})
    grouped["_bucket_order"] = grouped["horizon_bucket"].map({bucket: idx for idx, bucket in enumerate(bucket_order)})
    grouped = grouped.sort_values(["_bucket_order", "_stream_order", "stream_label"])

    for bucket, color in bucket_colors.items():
        bucket_rows = grouped[grouped["horizon_bucket"] == bucket]
        if bucket_rows.empty:
            continue
        x_values: list[str] = []
        q1_values: list[float] = []
        median_values: list[float] = []
        q3_values: list[float] = []
        lower_values: list[float] = []
        upper_values: list[float] = []
        n_values: list[int] = []
        for stream in streams:
            row = bucket_rows.loc[bucket_rows["stream_label"] == stream]
            if row.empty:
                continue
            stats = row.iloc[0]
            x_values.append(str(stream))
            q1_values.append(float(stats["q1"]))
            median_values.append(float(stats["median"]))
            q3_values.append(float(stats["q3"]))
            lower_values.append(float(stats["lower"]))
            upper_values.append(float(stats["upper"]))
            n_values.append(int(stats["rows"]))
        if not x_values:
            continue
        fig.add_trace(
            go.Box(
                name=bucket,
                x=x_values,
                q1=q1_values,
                median=median_values,
                q3=q3_values,
                lowerfence=lower_values,
                upperfence=upper_values,
                boxpoints=False,
                marker_color=color,
                customdata=[[horizon_label(bucket), format_count(n)] for n in n_values],
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Horizon: %{customdata[0]}<br>"
                    "Median APE: %{median:.2f}%<br>"
                    "IQR: %{q1:.2f}% to %{q3:.2f}%<br>"
                    "Whisker: %{lowerfence:.2f}% to %{upperfence:.2f}%<br>"
                    "Rows: %{customdata[1]}<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        boxmode="group",
        yaxis_title="Absolute percentage error (%)",
        xaxis_title="",
        legend_title_text="Horizon",
    )
    return apply_layout(fig, "Distribution of forecast errors by horizon bucket", height=520)


def plot_horizon_mape(qpred: pd.DataFrame) -> go.Figure:
    if qpred.empty or not {"horizon", "ape", "stream_label"}.issubset(qpred.columns):
        return empty_figure("Quarterly prediction rows need horizon and error fields.")
    data = qpred.dropna(subset=["horizon", "ape"]).copy()
    if data.empty:
        return empty_figure("No horizon-level error rows are available.")
    grouped = data.groupby(["stream_label", "horizon"], dropna=False)["ape"].mean().reset_index(name="mape")
    grouped = grouped[grouped["horizon"].between(1, 12)]
    if grouped.empty:
        return empty_figure("No 1-12 quarter horizon rows are available.")
    grouped["_hover_mape"] = grouped["mape"].map(format_percent)
    grouped["_hover_horizon"] = grouped["horizon"].map(lambda value: f"{format_count(value)} quarters")
    fig = px.line(
        grouped,
        x="horizon",
        y="mape",
        color="stream_label",
        markers=True,
        color_discrete_map=STREAM_COLORS,
        labels={"horizon": "Forecast horizon (quarters)", "mape": "MAPE (%)", "stream_label": ""},
        custom_data=["stream_label", "_hover_horizon", "_hover_mape"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Forecast horizon: %{customdata[1]}<br>"
            "MAPE: %{customdata[2]}<extra></extra>"
        )
    )
    return apply_layout(fig, "MAPE by forecast horizon", height=380)


def plot_stress_checks(stress: pd.DataFrame) -> go.Figure:
    if stress.empty or not {"stress_bucket", "mape", "stream_label"}.issubset(stress.columns):
        return empty_figure("Stress and horizon metrics are not available.")
    data = stress.copy()
    data = data[data["stress_bucket"].astype(str).isin(STRESS_BUCKET_ORDER)]
    if data.empty:
        return empty_figure("No recognised stress buckets were available.")
    data["mape"] = pd.to_numeric(data["mape"], errors="coerce")
    data["stress_bucket"] = pd.Categorical(data["stress_bucket"].astype(str), categories=STRESS_BUCKET_ORDER, ordered=True)
    data = data.sort_values(["stream_label", "stress_bucket"])
    data["_hover_bucket"] = data["stress_bucket"].astype(str).map(horizon_label)
    data["_hover_mape"] = data["mape"].map(format_percent)
    data["_hover_model"] = _safe_series(data, "model").map(display_model_label)
    data["_hover_variant"] = _safe_series(data, "variant").map(humanize_label)
    data["_hover_pairs"] = _safe_series(data, "n_pairs").map(format_count)
    fig = px.line(
        data,
        x="stress_bucket",
        y="mape",
        color="stream_label",
        markers=True,
        color_discrete_map=STREAM_COLORS,
        labels={"stress_bucket": "Stress bucket", "mape": "MAPE (%)", "stream_label": ""},
        custom_data=["stream_label", "_hover_bucket", "_hover_mape", "_hover_model", "_hover_variant", "_hover_pairs"],
    )
    fig.update_traces(
        connectgaps=False,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Stress window: %{customdata[1]}<br>"
            "MAPE: %{customdata[2]}<br>"
            "Model: %{customdata[3]}<br>"
            "Variant: %{customdata[4]}<br>"
            "Rows: %{customdata[5]}<extra></extra>"
        )
    )
    fig.add_hline(
        y=10,
        line_dash="dot",
        line_color="#991B1B",
        annotation_text="10% high-risk guide",
        annotation_position="top right",
    )
    visible_max = pd.to_numeric(data["mape"], errors="coerce").dropna().max()
    high_risk_top = max(float(visible_max) * 1.08, 11.0) if pd.notna(visible_max) else 11.0
    fig.add_hrect(
        y0=10,
        y1=high_risk_top,
        line_width=0,
        fillcolor="rgba(220, 38, 38, 0.06)",
        annotation_text="High-risk zone",
        annotation_position="top left",
    )
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=STRESS_BUCKET_ORDER)
    return apply_layout(fig, "Stress and horizon checks for finalist models", height=500)


def plot_scenario_stream_comparison(comparison: pd.DataFrame) -> go.Figure:
    required = {
        "stream_label",
        "finalist_quarterly_mape",
        "schiff_quarterly_mape",
        "finalist_annual_mape",
        "schiff_annual_mape",
    }
    if comparison.empty or not required.issubset(comparison.columns):
        return empty_figure("Scenario comparison needs finalist and Schiff MAPE columns.")
    comparison = comparison.copy()
    comparison["_stream_order"] = comparison["stream_label"].map(_stream_order_value)
    comparison = comparison.sort_values("_stream_order", ascending=False)
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["Quarterly MAPE", "Annual MAPE"],
        shared_yaxes=True,
        horizontal_spacing=0.13,
    )
    metrics = [
        ("finalist_quarterly_mape", "schiff_quarterly_mape", 1),
        ("finalist_annual_mape", "schiff_annual_mape", 2),
    ]
    y = comparison["stream_label"].astype(str)
    for finalist_col, schiff_col, col in metrics:
        fig.add_trace(
            go.Scatter(
                x=comparison[schiff_col],
                y=y,
                mode="markers",
                name="Scenario B" if col == 1 else "Scenario B",
                marker={"color": "#A7C800", "size": 9},
                customdata=comparison[["stream_label"]].to_numpy(),
                hovertemplate="<b>%{customdata[0]}</b><br>Scenario B: %{x:.2f}%<extra></extra>",
                showlegend=col == 1,
            ),
            row=1,
            col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=comparison[finalist_col],
                y=y,
                mode="markers",
                name="Scenario A" if col == 1 else "Scenario A",
                marker={"color": "#002B5C", "size": 9},
                customdata=comparison[["stream_label"]].to_numpy(),
                hovertemplate="<b>%{customdata[0]}</b><br>Scenario A: %{x:.2f}%<extra></extra>",
                showlegend=col == 1,
            ),
            row=1,
            col=col,
        )
        for _, row in comparison.iterrows():
            fig.add_shape(
                type="line",
                x0=row[finalist_col],
                x1=row[schiff_col],
                y0=row["stream_label"],
                y1=row["stream_label"],
                xref=f"x{col}" if col > 1 else "x",
                yref=f"y{col}" if col > 1 else "y",
                line={"color": "#64748B", "width": 1},
            )
        fig.update_xaxes(title_text="MAPE (%)", ticksuffix="%", row=1, col=col)
    for annotation in fig.layout.annotations:
        annotation.y = 1.08
        annotation.font = {"size": 13, "color": "#002B5C"}
    fig = apply_layout(fig, "Scenario A versus Scenario B", height=360)
    fig.update_layout(
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.16, "xanchor": "center", "x": 0.5, "font": {"size": 10}},
        margin={"l": 70, "r": 20, "t": 66, "b": 44},
    )
    return fig


def plot_improvement_vs_benchmark(comparison: pd.DataFrame) -> go.Figure:
    required = {"stream_label", "quarterly_gain_pp", "annual_gain_pp"}
    if comparison.empty or not required.issubset(comparison.columns):
        return empty_figure("Benchmark gain columns are not available.")
    data = comparison.copy()
    fig = go.Figure()
    for label, column, color in [
        ("Full-sample quarterly gain (pp)", "quarterly_gain_pp", "#002B5C"),
        ("Full-sample annual gain (pp)", "annual_gain_pp", "#A7C800"),
    ]:
        fig.add_bar(
            y=data["stream_label"],
            x=data[column],
            orientation="h",
            name=label,
            marker_color=color,
            text=data[column].map(lambda value: format_pp(value)),
            textposition="outside",
            customdata=data[["stream_label"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b><br>" + label + ": %{x:.2f} pp<extra></extra>",
        )
    fig.add_vline(x=0, line_color="#64748B", line_width=1)
    fig.update_layout(barmode="group", xaxis_title="Full-sample gain vs Schiff (percentage points)", yaxis_title="")
    return apply_layout(fig, "Full-sample gain versus Schiff", height=360)


def plot_horizon_comparison(horizon: pd.DataFrame) -> go.Figure:
    required = {"stream_label", "horizon", "mape", "scenario_role"}
    if horizon.empty or not required.issubset(horizon.columns):
        return empty_figure("Horizon comparison data is not available.")
    horizon = horizon.copy()
    horizon["_stream_order"] = horizon["stream_label"].map(_stream_order_value)
    horizon = horizon.sort_values(["_stream_order", "scenario_role", "horizon"])
    streams = [stream for stream in STREAM_ORDER if stream in set(horizon["stream_label"].astype(str))]
    streams.extend(sorted(set(horizon["stream_label"].dropna().astype(str)).difference(streams)))
    if not streams:
        return empty_figure("Horizon comparison has no stream labels.")
    fig = make_subplots(rows=1, cols=len(streams), subplot_titles=[str(stream) for stream in streams], shared_yaxes=True, horizontal_spacing=0.07)
    for col, stream in enumerate(streams, start=1):
        stream_rows = horizon[horizon["stream_label"].astype(str).eq(str(stream))]
        for role, dash in [("Finalist", "solid"), ("Schiff", "dash")]:
            role_rows = stream_rows[stream_rows["scenario_role"].astype(str).str.contains(role, case=False, na=False)]
            if role_rows.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=role_rows["horizon"],
                    y=role_rows["mape"],
                    mode="lines+markers",
                    name=role if col == 1 else role,
                    line={"dash": dash, "color": STREAM_COLORS.get(str(stream), "#002B5C"), "width": 2},
                    marker={"size": 4.5},
                    customdata=role_rows[["stream_label", "scenario_role"]].to_numpy(),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Scenario: %{customdata[1]}<br>"
                        "Horizon: %{x} quarters<br>"
                        "MAPE: %{y:.2f}%<extra></extra>"
                    ),
                    showlegend=col == 1,
                ),
                row=1,
                col=col,
            )
        fig.update_xaxes(title_text="Forecast horizon (quarters)", dtick=3, row=1, col=col)
    fig.update_yaxes(title_text="MAPE (%)", row=1, col=1)
    for annotation in fig.layout.annotations:
        annotation.font = {"size": 12, "color": "#002B5C"}
        annotation.y = 1.08
    fig = apply_layout(fig, "Horizon comparison", height=360)
    fig.update_layout(legend={"orientation": "h", "yanchor": "bottom", "y": 1.16, "xanchor": "center", "x": 0.5, "font": {"size": 10}})
    return fig


def plot_schiff_finalist_mape(comparison: pd.DataFrame) -> go.Figure:
    required = {
        "stream_label",
        "finalist_quarterly_mape",
        "schiff_quarterly_mape",
        "finalist_annual_mape",
        "schiff_annual_mape",
    }
    if comparison.empty or not required.issubset(comparison.columns):
        return empty_figure("Schiff and finalist comparison rows are not available.")
    comparison = comparison.copy()
    comparison["_stream_order"] = comparison["stream_label"].map(_stream_order_value)
    comparison = comparison.sort_values("_stream_order")
    max_value = pd.to_numeric(
        comparison[["finalist_quarterly_mape", "schiff_quarterly_mape", "finalist_annual_mape", "schiff_annual_mape"]].stack(),
        errors="coerce",
    ).max()
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Quarterly MAPE", "Annual MAPE"], shared_yaxes=True, horizontal_spacing=0.10)
    for col, (schiff_col, finalist_col) in enumerate(
        [
            ("schiff_quarterly_mape", "finalist_quarterly_mape"),
            ("schiff_annual_mape", "finalist_annual_mape"),
        ],
        start=1,
    ):
        for label, column, color in [
            ("Schiff (pure)", schiff_col, "#002B5C"),
            ("Finalist (refined)", finalist_col, "#A7C800"),
        ]:
            fig.add_bar(
                x=comparison["stream_label"],
                y=comparison[column],
                name=label,
                marker_color=color,
                text=comparison[column].map(lambda value: format_percent(value)),
                textposition="outside",
                customdata=comparison[["stream_label"]].to_numpy(),
                hovertemplate="<b>%{customdata[0]}</b><br>" + label + ": %{y:.2f}%<extra></extra>",
                showlegend=col == 1,
            )
        fig.update_yaxes(title_text="MAPE (%)", row=1, col=col)
        if pd.notna(max_value):
            fig.update_yaxes(range=[0, float(max_value) * 1.28], row=1, col=col)
    for annotation in fig.layout.annotations:
        annotation.y = 1.08
        annotation.font = {"size": 13, "color": "#002B5C"}
    fig = apply_layout(fig, "Schiff versus finalist MAPE", height=380)
    fig.update_layout(
        barmode="group",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.16, "xanchor": "center", "x": 0.5, "font": {"size": 10}},
        margin={"l": 42, "r": 20, "t": 66, "b": 48},
    )
    return fig


def plot_benchmark_summary_table(comparison: pd.DataFrame) -> go.Figure:
    if comparison.empty:
        return empty_figure("Benchmark summary is not available.")
    display = comparison.copy()
    headers = [
        "Stream",
        "Schiff Qtr",
        "Finalist Qtr",
        "Full-sample Qtr Gain",
        "Schiff Annual",
        "Finalist Annual",
        "Full-sample Annual Gain",
        "Paired Win Rate",
    ]
    values = [
        display["stream_label"].astype(str),
        display["schiff_quarterly_mape"].map(format_percent),
        display["finalist_quarterly_mape"].map(format_percent),
        display["quarterly_gain_pp"].map(format_pp),
        display["schiff_annual_mape"].map(format_percent),
        display["finalist_annual_mape"].map(format_percent),
        display["annual_gain_pp"].map(format_pp),
        display.get("win_rate", pd.Series(["-"] * len(display), index=display.index)).map(format_percent),
    ]
    row_colors = [["#FFFFFF", "#F8FAFC"][idx % 2] for idx in range(len(display))]
    gain_colors = ["#166534" if pd.to_numeric(value, errors="coerce") > 0 else "#991B1B" for value in display["quarterly_gain_pp"]]
    annual_gain_colors = ["#166534" if pd.to_numeric(value, errors="coerce") > 0 else "#991B1B" for value in display["annual_gain_pp"]]
    cell_font_colors = [
        ["#0F172A"] * len(display),
        ["#0F172A"] * len(display),
        ["#0F172A"] * len(display),
        gain_colors,
        ["#0F172A"] * len(display),
        ["#0F172A"] * len(display),
        annual_gain_colors,
        ["#0F172A"] * len(display),
    ]
    fig = go.Figure(
        data=[
            go.Table(
                header={
                    "values": headers,
                    "fill_color": "#EAF2F8",
                    "line_color": "#D7DEE8",
                    "align": "center",
                    "font": {"color": "#002B5C", "size": 12},
                },
                cells={
                    "values": values,
                    "height": 29,
                    "fill_color": [row_colors] * len(headers),
                    "line_color": "#E2E8F0",
                    "align": "center",
                    "font": {"size": 12, "color": cell_font_colors},
                },
            )
        ]
    )
    return apply_layout(fig, "Benchmark summary", height=360)


def plot_decision_summary_table(decisions: pd.DataFrame) -> go.Figure:
    if decisions.empty:
        return empty_figure("Decision summary rows are not available.")
    display = decisions.copy()
    qtr_col = "Full-sample Qtr Gain" if "Full-sample Qtr Gain" in display.columns else "Qtr Gain (pp)"
    annual_col = "Full-sample Annual Gain" if "Full-sample Annual Gain" in display.columns else "Annual Gain (pp)"
    win_col = "Paired Win Rate" if "Paired Win Rate" in display.columns else "Win Rate (%)"
    row_colors = [["#FFFFFF", "#F8FAFC"][idx % 2] for idx in range(len(display))]
    recommendation = display["Recommendation"].astype(str)
    rec_colors = [
        "#166534" if value == "Promote" else "#92400E" if "Watch" in value else "#991B1B"
        for value in recommendation
    ]
    values = [
        display["Stream"].astype(str),
        pd.to_numeric(display[qtr_col], errors="coerce").map(format_pp),
        pd.to_numeric(display[annual_col], errors="coerce").map(format_pp),
        pd.to_numeric(display[win_col], errors="coerce").map(format_percent),
        recommendation,
    ]
    headers = ["Stream", "Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate", "Recommendation"]
    fig = go.Figure(
        data=[
            go.Table(
                columnwidth=[1.35, 0.9, 1.0, 0.9, 1.15],
                header={
                    "values": headers,
                    "fill_color": "#EAF2F8",
                    "line_color": "#D7DEE8",
                    "align": "center",
                    "font": {"color": "#002B5C", "size": 12},
                },
                cells={
                    "values": values,
                    "height": 31,
                    "fill_color": [row_colors] * len(headers),
                    "line_color": "#E2E8F0",
                    "align": "center",
                    "font": {
                        "size": 12,
                        "color": [
                            ["#0F172A"] * len(display),
                            ["#0F172A"] * len(display),
                            ["#0F172A"] * len(display),
                            ["#0F172A"] * len(display),
                            rec_colors,
                        ],
                    },
                },
            )
        ]
    )
    return apply_layout(fig, "Decision summary", height=320)


def plot_diagnostic_pass_matrix(diagnostics: pd.DataFrame) -> go.Figure:
    if diagnostics.empty:
        return empty_figure("Diagnostic pass matrix is not available.")
    rows = diagnostics.copy()
    if "role" in rows.columns:
        rows = rows[rows["role"].astype(str).str.contains("finalist", case=False, na=False)]
    if rows.empty:
        return empty_figure("Finalist diagnostic rows are not available.")
    if {"diagnostic_test", "pass_status", "stream_label"}.issubset(rows.columns):
        return _plot_long_diagnostic_pass_matrix(rows)
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
    headers = ["Stream"] + [label for label, _, _ in tests] + ["Overall"]
    table_rows: list[list[str]] = [[] for _ in headers]
    fill_rows: list[list[str]] = [[] for _ in headers]
    font_rows: list[list[str]] = [[] for _ in headers]

    def status_style(status: str) -> tuple[str, str]:
        if status == "Pass":
            return "#DDF4DD", "#166534"
        if status == "Watch":
            return "#FEF3C7", "#92400E"
        if status == "Caution":
            return "#FEF3C7", "#92400E"
        if status == "Fail":
            return "#FEE2E2", "#991B1B"
        return "#F1F5F9", "#64748B"

    for _, row in rows.iterrows():
        statuses: list[str] = []
        statuses_by_label: dict[str, str] = {}
        table_rows[0].append(str(row.get("stream_label", "Stream")))
        fill_rows[0].append("#FFFFFF")
        font_rows[0].append("#0F172A")
        for idx, (label, column, rule) in enumerate(tests, start=1):
            value = pd.to_numeric(row.get(column), errors="coerce")
            if pd.isna(value):
                status = "Unavailable"
            else:
                result = rule(float(value))
                status = result if isinstance(result, str) else "Pass" if result else "Fail"
            statuses.append(status)
            statuses_by_label[label] = status
            table_rows[idx].append(status)
            fill, font = status_style(status)
            fill_rows[idx].append(fill)
            font_rows[idx].append(font)
        core_labels = {"Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"}
        core_fail = any(statuses_by_label.get(label) == "Fail" for label in core_labels)
        non_core_fail = any(
            status == "Fail" for label, status in statuses_by_label.items() if label not in core_labels
        )
        caution = any(status in {"Caution", "Watch"} for status in statuses)
        if core_fail:
            overall = "Fail"
        elif non_core_fail or caution:
            overall = "Watch"
        else:
            overall = "Pass"
        table_rows[-1].append(overall)
        fill, font = status_style(overall)
        fill_rows[-1].append(fill)
        font_rows[-1].append(font)
    fig = go.Figure(
        data=[
            go.Table(
                header={
                    "values": headers,
                    "fill_color": "#EAF2F8",
                    "line_color": "#D7DEE8",
                    "align": "center",
                    "font": {"color": "#002B5C", "size": 11},
                },
                cells={
                    "values": table_rows,
                    "height": 30,
                    "fill_color": fill_rows,
                    "line_color": "#E2E8F0",
                    "align": "center",
                    "font": {"size": 11, "color": font_rows},
                },
            )
        ]
    )
    fig.add_annotation(
        text="Green = pass, amber = caution, red = fail, grey = unavailable",
        x=0,
        y=-0.08,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="left",
        font={"size": 11, "color": "#64748B"},
    )
    return apply_layout(fig, "Diagnostic pass matrix", height=360)


def _plot_long_diagnostic_pass_matrix(rows: pd.DataFrame) -> go.Figure:
    data = rows.copy()
    test_order = [
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
    stream_order = [stream for stream in STREAM_ORDER if stream in set(data["stream_label"].astype(str))]
    stream_order.extend(sorted(set(data["stream_label"].dropna().astype(str)).difference(stream_order)))
    pivot = (
        data.assign(
            diagnostic_test=pd.Categorical(data["diagnostic_test"].astype(str), categories=test_order, ordered=True),
            stream_label=pd.Categorical(data["stream_label"].astype(str), categories=stream_order, ordered=True),
        )
        .sort_values(["stream_label", "diagnostic_test"])
        .pivot_table(index="stream_label", columns="diagnostic_test", values="pass_status", aggfunc="first", observed=False)
        .reindex(index=stream_order, columns=test_order)
        .fillna("Unavailable")
    )

    def status_style(status: str) -> tuple[str, str]:
        if status == "Pass":
            return "#DDF4DD", "#166534"
        if status in {"Watch", "Caution"}:
            return "#FEF3C7", "#92400E"
        if status == "Fail":
            return "#FEE2E2", "#991B1B"
        return "#F1F5F9", "#64748B"

    headers = ["Stream"] + test_order
    values = [list(pivot.index.astype(str))] + [pivot[column].astype(str).tolist() for column in test_order]
    fill_rows: list[list[str]] = [["#FFFFFF"] * len(pivot)]
    font_rows: list[list[str]] = [["#0F172A"] * len(pivot)]
    for column in test_order:
        fills: list[str] = []
        fonts: list[str] = []
        for status in pivot[column].astype(str):
            fill, font = status_style(status)
            fills.append(fill)
            fonts.append(font)
        fill_rows.append(fills)
        font_rows.append(fonts)
    fig = go.Figure(
        data=[
            go.Table(
                header={
                    "values": headers,
                    "fill_color": "#EAF2F8",
                    "line_color": "#D7DEE8",
                    "align": "center",
                    "font": {"color": "#002B5C", "size": 11},
                },
                cells={
                    "values": values,
                    "height": 30,
                    "fill_color": fill_rows,
                    "line_color": "#E2E8F0",
                    "align": "center",
                    "font": {"size": 11, "color": font_rows},
                },
            )
        ]
    )
    fig.add_annotation(
        text="Green = pass, amber = watch, red = fail, grey = unavailable",
        x=0,
        y=-0.08,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="left",
        font={"size": 11, "color": "#64748B"},
    )
    return apply_layout(fig, "Diagnostic pass matrix", height=360)


def plot_feature_counts(variant_features: pd.DataFrame) -> go.Figure:
    if variant_features.empty or "n_known_covariates" not in variant_features.columns:
        return empty_figure("Variant feature-count data is not available.")
    data = variant_features.copy()
    data["n_known_covariates"] = pd.to_numeric(data["n_known_covariates"], errors="coerce")
    data["_hover_variant"] = _safe_series(data, "variant").map(humanize_label)
    data["_hover_known"] = data["n_known_covariates"].map(format_count)
    data["_hover_structural"] = _safe_series(data, "n_structural_covariates").map(format_count)
    fig = px.bar(
        data.sort_values("n_known_covariates", ascending=False),
        x="variant",
        y="n_known_covariates",
        color="stream_label",
        color_discrete_map=STREAM_COLORS,
        labels={"variant": "Variant", "n_known_covariates": "Known covariates", "stream_label": ""},
        custom_data=["stream_label", "_hover_variant", "_hover_known", "_hover_structural"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Variant: %{customdata[1]}<br>"
            "Known covariates: %{customdata[2]}<br>"
            "Structural covariates: %{customdata[3]}<extra></extra>"
        )
    )
    fig.update_xaxes(tickangle=-35)
    return apply_layout(fig, "Feature count by stream and variant", height=520)


def plot_inventory_family_performance(summary: pd.DataFrame, metric: str = "quarterly_mape") -> go.Figure:
    if summary.empty or metric not in summary.columns or "source_family" not in summary.columns:
        return empty_figure("Inventory performance needs source family and metric columns.")
    data = summary.dropna(subset=[metric]).copy()
    if data.empty:
        return empty_figure("No inventory rows have the selected ranking metric.")
    group_cols = ["stream_label", "source_family"]
    grouped = data.groupby(group_cols, dropna=False)[metric].median().reset_index(name=metric)
    grouped["_hover_family"] = grouped["source_family"].map(humanize_label)
    grouped["_hover_metric"] = grouped[metric].map(format_percent)
    metric_label = humanize_label(metric)
    fig = px.bar(
        grouped.sort_values(metric, ascending=True).head(40),
        x=metric,
        y="source_family",
        color="stream_label",
        orientation="h",
        barmode="group",
        color_discrete_map=STREAM_COLORS,
        labels={metric: f"Median {humanize_label(metric)} (%)", "source_family": "", "stream_label": ""},
        custom_data=["stream_label", "_hover_family", "_hover_metric"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[1]}</b><br>"
            "Stream: %{customdata[0]}<br>"
            f"Median {metric_label}: "
            "%{customdata[2]}<extra></extra>"
        )
    )
    return apply_layout(fig, "Model family performance by stream", height=440)


def plot_schiff_class_mix(summary: pd.DataFrame) -> go.Figure:
    if summary.empty or "schiff_class" not in summary.columns:
        return empty_figure("Schiff class labels are not available.")
    data = summary.groupby(["stream_label", "schiff_class"], dropna=False).size().reset_index(name="Rows")
    if data.empty:
        return empty_figure("No model rows are available for Schiff class mix.")
    data["_hover_class"] = data["schiff_class"].map(humanize_label)
    data["_hover_rows"] = data["Rows"].map(format_count)
    fig = px.bar(
        data,
        x="stream_label",
        y="Rows",
        color="schiff_class",
        labels={"stream_label": "", "schiff_class": "Schiff class"},
        text="Rows",
        custom_data=["stream_label", "_hover_class", "_hover_rows"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Schiff class: %{customdata[1]}<br>"
            "Rows: %{customdata[2]}<extra></extra>"
        )
    )
    fig.update_traces(textposition="inside")
    return apply_layout(fig, "Pure Schiff versus challenger mix", height=360)


def plot_error_types(error_types: pd.DataFrame) -> go.Figure:
    if error_types.empty or not {"Error type", "Rows"}.issubset(error_types.columns):
        return empty_figure("No error diagnostics are available.")
    data = error_types[error_types["Rows"] > 0].sort_values("Rows", ascending=True)
    if data.empty:
        return empty_figure("No non-zero error diagnostics were found.")
    data["_hover_error_type"] = data["Error type"].map(humanize_label)
    data["_hover_rows"] = data["Rows"].map(format_count)
    fig = px.bar(
        data,
        x="Rows",
        y="Error type",
        orientation="h",
        color="Error type",
        color_discrete_sequence=["#0F4C81", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#64748B"],
        text="Rows",
        custom_data=["_hover_error_type", "_hover_rows"],
    )
    fig.update_traces(
        hovertemplate="<b>%{customdata[0]}</b><br>Rows: %{customdata[1]}<extra></extra>"
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(showlegend=False, xaxis_title="Rows", yaxis_title="")
    return apply_layout(fig, "Logged diagnostics by error type", height=320)

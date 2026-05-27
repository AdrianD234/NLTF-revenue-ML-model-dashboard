from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .plots import apply_layout, empty_figure


LIGHT_RUC_REPRO_ROOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "dashboard_evidence_pack_reproducibility"
    / "light_ruc"
)

LIGHT_RUC_REPRO_MODEL = "dynamic_RESID_GBR_n150_d1_lr0.05_w36"
LIGHT_RUC_REPRO_DESCRIPTION = (
    "Two-stage OLS base plus GBM residual correction, exactly replayed against evidence predictions."
)

REQUIRED_LIGHT_RUC_REPRO_FILES = (
    "manifest.json",
    "light_ruc_reproducibility_report.md",
    "parquet_write_status.json",
    "model_registry.parquet",
    "rebuilt_predictions.parquet",
    "component_predictions.parquet",
    "model_coefficients.parquet",
    "feature_importance.parquet",
    "feature_importance_global.parquet",
    "scenario_sensitivities.parquet",
    "future_forecasts.parquet",
    "scorecard_summary.parquet",
    "annual_predictions.parquet",
    "horizon_profiles.parquet",
    "stress_horizon.parquet",
    "training_window_trace.parquet",
    "evidence_prediction_comparison.parquet",
    "evidence_metric_comparison.parquet",
)

SCORE_BASIS_LABELS = {
    "current_grid_operational_pooled": "Operational pooled",
    "schiff_paper_horizon_mean": "Paper-style horizon mean",
}


@dataclass(frozen=True)
class LightRucReproducibilityPack:
    root: Path
    manifest: dict[str, Any]
    tables: dict[str, pd.DataFrame]
    missing_files: tuple[str, ...]

    @property
    def available(self) -> bool:
        registry = self.tables.get("model_registry", pd.DataFrame())
        return not self.missing_files and not registry.empty

    def table(self, name: str) -> pd.DataFrame:
        return self.tables.get(name, pd.DataFrame()).copy()


def light_ruc_repro_signature(root: str | Path | None = None) -> tuple[tuple[str, int, int], ...]:
    """Return a Streamlit cache signature for the auxiliary Light RUC audit pack."""
    pack_root = Path(root).expanduser() if root else LIGHT_RUC_REPRO_ROOT
    signature: list[tuple[str, int, int]] = []
    for name in REQUIRED_LIGHT_RUC_REPRO_FILES:
        path = pack_root / name
        if not path.exists():
            continue
        stat = path.stat()
        signature.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


def load_light_ruc_reproducibility_pack(root: str | Path | None = None) -> LightRucReproducibilityPack:
    """Load the auxiliary Light RUC reproducibility pack without touching main dashboard data."""
    pack_root = Path(root).expanduser() if root else LIGHT_RUC_REPRO_ROOT
    if not pack_root.exists():
        return LightRucReproducibilityPack(
            root=pack_root,
            manifest={},
            tables={},
            missing_files=REQUIRED_LIGHT_RUC_REPRO_FILES,
        )

    missing = tuple(name for name in REQUIRED_LIGHT_RUC_REPRO_FILES if not (pack_root / name).exists())
    manifest = _read_json(pack_root / "manifest.json") if (pack_root / "manifest.json").exists() else {}
    tables: dict[str, pd.DataFrame] = {}
    for name in REQUIRED_LIGHT_RUC_REPRO_FILES:
        if not name.endswith(".parquet"):
            continue
        path = pack_root / name
        if path.exists():
            tables[name.removesuffix(".parquet")] = pd.read_parquet(path)
    return LightRucReproducibilityPack(
        root=pack_root,
        manifest=manifest,
        tables=tables,
        missing_files=missing,
    )


def light_ruc_replay_summary(pack: LightRucReproducibilityPack) -> dict[str, Any]:
    registry = pack.table("model_registry")
    metric = pack.table("evidence_metric_comparison")
    source_workbook = str(pack.manifest.get("source_workbook", ""))
    source_sheet = str(pack.manifest.get("source_sheet", "Light RUC Inputs"))
    model = str(pack.manifest.get("model", LIGHT_RUC_REPRO_MODEL))
    if not registry.empty:
        source_workbook = str(registry["source_workbook"].dropna().astype(str).iloc[0])
        source_sheet = str(registry["source_sheet"].dropna().astype(str).iloc[0])
        model = str(registry["finalist_model"].dropna().astype(str).iloc[0])
    max_delta = pd.to_numeric(metric.get("max_abs_pred_delta", pd.Series(dtype=float)), errors="coerce").max()
    return {
        "status": "Exact prediction replay",
        "model": model,
        "max_abs_pred_delta": max_delta,
        "workbook": Path(source_workbook).name if source_workbook else "Master Copy revenue modelling workbook.xlsx",
        "source_sheet": source_sheet,
        "description": LIGHT_RUC_REPRO_DESCRIPTION,
    }


def light_ruc_registry_view(pack: LightRucReproducibilityPack) -> pd.DataFrame:
    registry = pack.table("model_registry")
    if registry.empty:
        return pd.DataFrame()
    scorecard = pack.table("scorecard_summary")
    score_bases = (
        scorecard["score_basis"].dropna().astype(str).drop_duplicates().tolist()
        if "score_basis" in scorecard.columns
        else ["current_grid_operational_pooled", "schiff_paper_horizon_mean"]
    )
    final = _first_row(registry[registry["model_role"].astype(str).eq("finalist")])
    base = _first_row(registry[registry["component_model"].astype(str).eq("base_schiff_ols")])
    residual = _first_row(registry[registry["component_model"].astype(str).eq("residual_gbr")])
    rows = []
    for score_basis in score_bases:
        rows.append(
            {
                "Target": final.get("target_column", "Light RUC net km"),
                "Base model": base.get("component_model", "base_schiff_ols"),
                "Residual model": residual.get("component_model", "residual_gbr"),
                "Window": f"{final.get('window_length', 36)} quarters",
                "Hyperparameters": _json_summary(residual.get("hyperparameters_json", final.get("hyperparameters_json", ""))),
                "Feature set": final.get("feature_set", "base_schiff_features + dynamic_residual_features"),
                "Score basis": _score_basis_label(score_basis),
            }
        )
    return pd.DataFrame(rows)


def light_ruc_component_trace_view(pack: LightRucReproducibilityPack, limit: int = 240) -> pd.DataFrame:
    components = pack.table("component_predictions")
    if components.empty:
        return pd.DataFrame()
    rows = []
    keys = ["score_basis", "grid", "origin", "target_period", "horizon"]
    for values, group in components.groupby(keys, dropna=False):
        record = dict(zip(keys, values, strict=False))
        base = group[group["component_model"].astype(str).eq("base_schiff_ols")]
        residual = group[group["component_model"].astype(str).eq("residual_gbr")]
        first = group.iloc[0]
        record.update(
            {
                "Score basis": _score_basis_label(record["score_basis"]),
                "Origin": record["origin"],
                "Target period": record["target_period"],
                "Horizon": int(record["horizon"]) if pd.notna(record["horizon"]) else record["horizon"],
                "Actual": first.get("actual"),
                "Base log prediction": _first_value(base, "component_log_value"),
                "Residual log prediction": _first_value(residual, "component_log_value"),
                "Final prediction": first.get("final_pred"),
            }
        )
        rows.append(record)
    return pd.DataFrame(rows).sort_values(["score_basis", "Origin", "Horizon"]).head(limit)


def light_ruc_feature_importance_view(pack: LightRucReproducibilityPack, limit_per_basis: int = 12) -> pd.DataFrame:
    data = pack.table("feature_importance_global")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    view["score_basis_label"] = view["score_basis"].map(_score_basis_label)
    view["importance_value"] = pd.to_numeric(view["importance_value"], errors="coerce")
    view["rank"] = pd.to_numeric(view["rank"], errors="coerce")
    view = view.sort_values(["score_basis", "rank", "importance_value"], ascending=[True, True, False])
    return view.groupby("score_basis", group_keys=False).head(limit_per_basis)


def light_ruc_coefficients_view(pack: LightRucReproducibilityPack, limit: int = 420) -> pd.DataFrame:
    coefficients = pack.table("model_coefficients")
    windows = pack.table("training_window_trace")
    if coefficients.empty:
        return pd.DataFrame()
    view = coefficients.copy()
    join_cols = ["score_basis", "grid", "stream", "stream_label", "model", "origin"]
    if not windows.empty and set(join_cols).issubset(set(view.columns)) and set(join_cols).issubset(set(windows.columns)):
        view = view.merge(windows[join_cols + ["train_start", "train_end", "window_length", "n_train"]], on=join_cols, how="left")
    view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = [
        "Score basis",
        "origin",
        "train_start",
        "train_end",
        "window_length",
        "n_train",
        "feature",
        "coefficient",
        "coefficient_type",
    ]
    keep = [col for col in keep if col in view.columns]
    return view[keep].sort_values([col for col in ["Score basis", "origin", "feature"] if col in keep]).head(limit)


def light_ruc_sensitivity_view(pack: LightRucReproducibilityPack, limit_per_basis: int = 12) -> pd.DataFrame:
    data = pack.table("scenario_sensitivities")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    view["delta_pct"] = pd.to_numeric(view["delta_pct"], errors="coerce")
    grouped = (
        view.groupby(["score_basis", "scenario_variable", "scenario_name", "perturbation"], as_index=False)
        .agg(mean_delta_pct=("delta_pct", "mean"), rows=("delta_pct", "count"))
        .copy()
    )
    grouped["score_basis_label"] = grouped["score_basis"].map(_score_basis_label)
    grouped["abs_delta"] = grouped["mean_delta_pct"].abs()
    grouped = grouped.sort_values(["score_basis", "abs_delta"], ascending=[True, False])
    return grouped.groupby("score_basis", group_keys=False).head(limit_per_basis)


def light_ruc_training_window_view(pack: LightRucReproducibilityPack) -> pd.DataFrame:
    data = pack.table("training_window_trace")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = ["Score basis", "origin", "window_type", "window_length", "train_start", "train_end", "n_train"]
    return view[[col for col in keep if col in view.columns]].sort_values(["Score basis", "origin"])


def plot_light_ruc_feature_importance(data: pd.DataFrame) -> go.Figure:
    if data.empty:
        return empty_figure("Light RUC feature-importance rows are not available.")
    view = data.copy().sort_values("importance_value", ascending=True)
    fig = px.bar(
        view,
        x="importance_value",
        y="feature",
        color="score_basis_label",
        orientation="h",
        barmode="group",
        labels={
            "importance_value": "Mean impurity importance",
            "feature": "Feature",
            "score_basis_label": "Score basis",
        },
        custom_data=["score_basis_label", "rank", "n_origins"],
    )
    fig.update_traces(
        hovertemplate=(
            "Feature: %{y}<br>"
            "Importance: %{x:.4f}<br>"
            "Score basis: %{customdata[0]}<br>"
            "Rank: %{customdata[1]:.0f}<br>"
            "Origins: %{customdata[2]:.0f}<extra></extra>"
        )
    )
    return apply_layout(fig, "Feature importance from residual GBM", height=360)


def plot_light_ruc_sensitivities(data: pd.DataFrame) -> go.Figure:
    if data.empty:
        return empty_figure("Light RUC scenario-sensitivity rows are not available.")
    view = data.copy().sort_values("mean_delta_pct", ascending=True)
    view["label"] = view["scenario_variable"].astype(str) + " | " + view["score_basis_label"].astype(str)
    fig = px.bar(
        view,
        x="mean_delta_pct",
        y="label",
        color="score_basis_label",
        orientation="h",
        labels={
            "mean_delta_pct": "Mean prediction change (%)",
            "label": "Scenario variable",
            "score_basis_label": "Score basis",
        },
        custom_data=["scenario_name", "perturbation", "rows"],
    )
    fig.add_vline(x=0, line_width=1, line_color="#64748B")
    fig.update_traces(
        hovertemplate=(
            "Scenario: %{customdata[0]}<br>"
            "Perturbation: %{customdata[1]}<br>"
            "Mean change: %{x:.2f}%<br>"
            "Rows: %{customdata[2]:.0f}<extra></extra>"
        )
    )
    return apply_layout(fig, "Scenario sensitivities", height=360)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _first_row(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=object)
    return frame.iloc[0]


def _first_value(frame: pd.DataFrame, column: str) -> Any:
    if frame.empty or column not in frame.columns:
        return pd.NA
    return frame[column].iloc[0]


def _json_summary(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text or text.lower() == "nan":
        return "Not applicable"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not parsed:
        return "Not applicable"
    preferred = ["n_estimators", "max_depth", "learning_rate", "subsample", "random_state"]
    parts = [f"{key}={parsed[key]}" for key in preferred if key in parsed]
    parts.extend(f"{key}={value}" for key, value in parsed.items() if key not in preferred)
    return ", ".join(parts)


def _score_basis_label(value: Any) -> str:
    return SCORE_BASIS_LABELS.get(str(value), str(value).replace("_", " ").title())

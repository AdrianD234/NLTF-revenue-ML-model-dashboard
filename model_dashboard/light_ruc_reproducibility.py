from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .plots import apply_layout, empty_figure


REPRODUCIBILITY_BASE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "dashboard_evidence_pack_reproducibility"
)

LIGHT_RUC_REPRO_ROOT = REPRODUCIBILITY_BASE_ROOT / "light_ruc"
LIGHT_RUC_REPRO_MODEL = "dynamic_RESID_GBR_n150_d1_lr0.05_w36"
LIGHT_RUC_REPRO_DESCRIPTION = (
    "Two-stage OLS base plus GBM residual correction, exactly replayed against evidence predictions."
)
PED_REPRO_MODEL = "PED__RESCUE_static_annual_weighted_top12_capnone"
PED_REPRO_DESCRIPTION = (
    "PED finalist exactly replays the stored HPO/static-solver component prediction; "
    "inner HPO/static-solver rebuild remains a future audit layer."
)

COMMON_REQUIRED_REPRO_FILES = (
    "manifest.json",
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


@dataclass(frozen=True)
class ReproducibilityStreamConfig:
    stream_label: str
    stream_key: str
    root: Path
    model: str
    description: str
    report_file: str

    @property
    def required_files(self) -> tuple[str, ...]:
        return ("manifest.json", self.report_file, *COMMON_REQUIRED_REPRO_FILES[1:])


LIGHT_RUC_REPRO_CONFIG = ReproducibilityStreamConfig(
    stream_label="Light RUC volume",
    stream_key="light_ruc",
    root=LIGHT_RUC_REPRO_ROOT,
    model=LIGHT_RUC_REPRO_MODEL,
    description=LIGHT_RUC_REPRO_DESCRIPTION,
    report_file="light_ruc_reproducibility_report.md",
)

REPRODUCIBILITY_STREAM_CONFIGS: dict[str, ReproducibilityStreamConfig] = {
    "PED VKT per capita": ReproducibilityStreamConfig(
        stream_label="PED VKT per capita",
        stream_key="ped",
        root=REPRODUCIBILITY_BASE_ROOT / "ped",
        model=PED_REPRO_MODEL,
        description=PED_REPRO_DESCRIPTION,
        report_file="ped_reproducibility_report.md",
    ),
    LIGHT_RUC_REPRO_CONFIG.stream_label: LIGHT_RUC_REPRO_CONFIG,
    "Heavy RUC volume": ReproducibilityStreamConfig(
        stream_label="Heavy RUC volume",
        stream_key="heavy_ruc",
        root=REPRODUCIBILITY_BASE_ROOT / "heavy_ruc",
        model="HEAVY_RUC__RECON_STATIC_REBUILT",
        description="Four-component weighted ensemble exactly replayed against evidence predictions.",
        report_file="heavy_ruc_reproducibility_report.md",
    ),
}

REQUIRED_LIGHT_RUC_REPRO_FILES = LIGHT_RUC_REPRO_CONFIG.required_files
PED_REPRO_ROOT = REPRODUCIBILITY_STREAM_CONFIGS["PED VKT per capita"].root
REQUIRED_PED_REPRO_FILES = REPRODUCIBILITY_STREAM_CONFIGS["PED VKT per capita"].required_files
HEAVY_RUC_REPRO_ROOT = REPRODUCIBILITY_STREAM_CONFIGS["Heavy RUC volume"].root
HEAVY_RUC_REPRO_MODEL = REPRODUCIBILITY_STREAM_CONFIGS["Heavy RUC volume"].model
REQUIRED_HEAVY_RUC_REPRO_FILES = REPRODUCIBILITY_STREAM_CONFIGS["Heavy RUC volume"].required_files

SCORE_BASIS_LABELS = {
    "current_grid_operational_pooled": "Operational pooled",
    "schiff_paper_horizon_mean": "Paper-style horizon mean",
}


@dataclass(frozen=True)
class ReproducibilityPack:
    stream_label: str
    config: ReproducibilityStreamConfig
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


LightRucReproducibilityPack = ReproducibilityPack


def reproducibility_stream_labels() -> list[str]:
    return list(REPRODUCIBILITY_STREAM_CONFIGS)


def reproducibility_stream_config(stream_label: str) -> ReproducibilityStreamConfig:
    return REPRODUCIBILITY_STREAM_CONFIGS.get(stream_label, LIGHT_RUC_REPRO_CONFIG)


def reproducibility_pack_signature(
    stream_label: str = LIGHT_RUC_REPRO_CONFIG.stream_label,
    root: str | Path | None = None,
) -> tuple[tuple[str, int, int], ...]:
    """Return a Streamlit cache signature for a stream-specific auxiliary audit pack."""
    config = reproducibility_stream_config(stream_label)
    pack_root = Path(root).expanduser() if root else config.root
    signature: list[tuple[str, int, int]] = []
    for name in config.required_files:
        path = pack_root / name
        if not path.exists():
            continue
        stat = path.stat()
        signature.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


def light_ruc_repro_signature(root: str | Path | None = None) -> tuple[tuple[str, int, int], ...]:
    return reproducibility_pack_signature(LIGHT_RUC_REPRO_CONFIG.stream_label, root)


def load_reproducibility_pack(
    stream_label: str = LIGHT_RUC_REPRO_CONFIG.stream_label,
    root: str | Path | None = None,
) -> ReproducibilityPack:
    """Load a stream-specific auxiliary reproducibility pack without touching main dashboard data."""
    config = reproducibility_stream_config(stream_label)
    pack_root = Path(root).expanduser() if root else config.root
    if not pack_root.exists():
        return ReproducibilityPack(
            stream_label=config.stream_label,
            config=config,
            root=pack_root,
            manifest={},
            tables={},
            missing_files=config.required_files,
        )

    missing = tuple(name for name in config.required_files if not (pack_root / name).exists())
    manifest = _read_json(pack_root / "manifest.json") if (pack_root / "manifest.json").exists() else {}
    tables: dict[str, pd.DataFrame] = {}
    for name in config.required_files:
        if not name.endswith(".parquet"):
            continue
        path = pack_root / name
        if path.exists():
            tables[name.removesuffix(".parquet")] = pd.read_parquet(path)
    return ReproducibilityPack(
        stream_label=config.stream_label,
        config=config,
        root=pack_root,
        manifest=manifest,
        tables=tables,
        missing_files=missing,
    )


def load_light_ruc_reproducibility_pack(root: str | Path | None = None) -> LightRucReproducibilityPack:
    return load_reproducibility_pack(LIGHT_RUC_REPRO_CONFIG.stream_label, root)


def reproducibility_replay_summary(pack: ReproducibilityPack) -> dict[str, Any]:
    registry = pack.table("model_registry")
    source_workbook = str(pack.manifest.get("source_workbook", ""))
    source_sheet = str(pack.manifest.get("source_sheet", "Light RUC Inputs"))
    workbook_provenance = pack.manifest.get("workbook_provenance", {})
    if isinstance(workbook_provenance, dict):
        source_workbook = str(workbook_provenance.get("workbook", source_workbook))
        source_sheet = str(workbook_provenance.get("sheet", source_sheet))
    model = str(pack.manifest.get("model", pack.config.model))
    if not registry.empty:
        if "source_workbook" in registry.columns and registry["source_workbook"].notna().any():
            source_workbook = str(registry["source_workbook"].dropna().astype(str).iloc[0])
        if "source_sheet" in registry.columns and registry["source_sheet"].notna().any():
            source_sheet = str(registry["source_sheet"].dropna().astype(str).iloc[0])
        if "finalist_model" in registry.columns and registry["finalist_model"].notna().any():
            model = str(registry["finalist_model"].dropna().astype(str).iloc[0])
        elif "model" in registry.columns and registry["model"].notna().any():
            model = str(registry["model"].dropna().astype(str).iloc[0])
    pred_comparison = pack.table("evidence_prediction_comparison")
    metric = pack.table("evidence_metric_comparison")
    max_delta = _max_abs_delta(pred_comparison, metric)
    if _is_ped_component_pack(pack):
        status = "Exact component-prediction replay"
    elif _is_weighted_ensemble_pack(pack):
        status = "Exact weighted-ensemble replay"
    else:
        status = "Exact prediction replay"
    return {
        "status": status,
        "model": model,
        "max_abs_pred_delta": max_delta,
        "workbook": Path(source_workbook).name if source_workbook else "Master Copy revenue modelling workbook.xlsx",
        "source_sheet": source_sheet,
        "description": pack.config.description,
    }


def light_ruc_replay_summary(pack: LightRucReproducibilityPack) -> dict[str, Any]:
    return reproducibility_replay_summary(pack)


def reproducibility_registry_view(pack: ReproducibilityPack) -> pd.DataFrame:
    registry = pack.table("model_registry")
    if registry.empty:
        return pd.DataFrame()
    if _is_ped_component_pack(pack):
        scorecard = pack.table("scorecard_summary")
        score_bases = (
            scorecard["score_basis"].dropna().astype(str).drop_duplicates().map(_score_basis_label).tolist()
            if "score_basis" in scorecard.columns
            else ["Operational pooled", "Paper-style horizon mean"]
        )
        view = registry.copy()
        view["Score basis"] = ", ".join(score_bases)
        keep = [
            "target",
            "model_role",
            "model",
            "algorithm",
            "Score basis",
            "source_parent_run",
            "reproducibility_status",
        ]
        return view[[col for col in keep if col in view.columns]].rename(
            columns={
                "target": "Target",
                "model_role": "Role",
                "model": "Component model",
                "algorithm": "Algorithm",
                "source_parent_run": "Source run",
                "reproducibility_status": "Reproducibility status",
            }
        )
    if _is_weighted_ensemble_pack(pack):
        view = registry.copy()
        scorecard = pack.table("scorecard_summary")
        score_bases = (
            scorecard["score_basis"].dropna().astype(str).drop_duplicates().map(_score_basis_label).tolist()
            if "score_basis" in scorecard.columns
            else ["Operational pooled", "Paper-style horizon mean"]
        )
        view["Component"] = [f"C{i}" for i in range(1, len(view) + 1)]
        view["Weight"] = pd.to_numeric(view["component_weight"], errors="coerce")
        view["Algorithm"] = view.get("model_kind", pd.Series(dtype=str)).astype(str).map(_algorithm_label)
        view["Window"] = view.get("window", pd.Series(dtype=str)).astype(str).map(lambda value: f"{value} quarters" if value else "")
        view["Hyperparameters"] = view.get("hyperparameters_json", pd.Series(dtype=str)).map(_json_summary)
        view["Score basis"] = ", ".join(score_bases)
        return view[
            [
                "target_column",
                "Component",
                "component_model",
                "Algorithm",
                "Window",
                "Weight",
                "Hyperparameters",
                "Score basis",
            ]
        ].rename(
            columns={
                "target_column": "Target",
                "component_model": "Component model",
            }
        )
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


def light_ruc_registry_view(pack: LightRucReproducibilityPack) -> pd.DataFrame:
    return reproducibility_registry_view(pack)


def reproducibility_component_trace_view(pack: ReproducibilityPack, limit: int = 240) -> pd.DataFrame:
    components = pack.table("component_predictions")
    if components.empty:
        return pd.DataFrame()
    if _is_ped_component_pack(pack):
        view = components.copy()
        view["Component"] = view["component_model"].map(_component_label_map(pack))
        view["Component model"] = view["component_model"].astype(str)
        view["Score basis"] = view["score_basis"].map(_score_basis_label)
        view["Weight"] = pd.to_numeric(view["component_weight"], errors="coerce")
        view["Component prediction"] = pd.to_numeric(view["component_pred"], errors="coerce")
        view["Final prediction"] = pd.to_numeric(view["rebuilt_pred"], errors="coerce")
        view["Actual"] = pd.to_numeric(view["actual"], errors="coerce")
        view["Error (%)"] = ((view["Final prediction"] - view["Actual"]) / view["Actual"]) * 100
        keep = [
            "Score basis",
            "origin",
            "target_period",
            "horizon",
            "Component",
            "Component model",
            "Weight",
            "Component prediction",
            "Final prediction",
            "Actual",
            "Error (%)",
        ]
        return view[[col for col in keep if col in view.columns]].rename(
            columns={
                "origin": "Origin",
                "target_period": "Target period",
                "horizon": "Horizon",
            }
        ).sort_values(["Score basis", "Origin", "Horizon", "Component"]).head(limit)
    if _is_weighted_ensemble_pack(pack):
        view = components.copy()
        view["Component"] = view["component_model"].map(_component_label_map(pack))
        view["Component model"] = view["component_model"].astype(str)
        view["Score basis"] = view["score_basis"].map(_score_basis_label)
        view["Weight"] = pd.to_numeric(view["component_weight"], errors="coerce")
        view["Component prediction"] = pd.to_numeric(view["component_pred"], errors="coerce")
        view["Weighted contribution"] = pd.to_numeric(view["weighted_component_pred"], errors="coerce")
        view["Final prediction"] = pd.to_numeric(view["final_pred"], errors="coerce")
        view["Actual"] = pd.to_numeric(view["actual"], errors="coerce")
        keep = [
            "Score basis",
            "origin",
            "target_period",
            "horizon",
            "Component",
            "Component model",
            "Weight",
            "Component prediction",
            "Weighted contribution",
            "Final prediction",
            "Actual",
        ]
        return view[keep].rename(
            columns={
                "origin": "Origin",
                "target_period": "Target period",
                "horizon": "Horizon",
            }
        ).sort_values(["Score basis", "Origin", "Horizon", "Component"]).head(limit)
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


def light_ruc_component_trace_view(pack: LightRucReproducibilityPack, limit: int = 240) -> pd.DataFrame:
    return reproducibility_component_trace_view(pack, limit)


def reproducibility_feature_importance_view(pack: ReproducibilityPack, limit_per_basis: int = 12) -> pd.DataFrame:
    data = pack.table("feature_importance_global")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    if "score_basis" not in view.columns:
        view["score_basis"] = "ensemble_component_weight"
    view["score_basis_label"] = view["score_basis"].map(_score_basis_label)
    if "importance_value" not in view.columns and "mean_abs_importance" in view.columns:
        view["importance_value"] = view["mean_abs_importance"]
    if "n_origins" not in view.columns:
        view["n_origins"] = 0
    view["n_origins"] = pd.to_numeric(view["n_origins"], errors="coerce").fillna(0)
    view["importance_value"] = pd.to_numeric(view["importance_value"], errors="coerce")
    view["rank"] = pd.to_numeric(view.get("rank", pd.Series(range(1, len(view) + 1))), errors="coerce")
    view["feature_label"] = view["feature"].astype(str).map(lambda value: _component_label_map(pack).get(value, _short_component(value)))
    view = view.sort_values(["score_basis", "rank", "importance_value"], ascending=[True, True, False])
    return view.groupby("score_basis", group_keys=False).head(limit_per_basis)


def light_ruc_feature_importance_view(pack: LightRucReproducibilityPack, limit_per_basis: int = 12) -> pd.DataFrame:
    return reproducibility_feature_importance_view(pack, limit_per_basis)


def reproducibility_coefficients_view(pack: ReproducibilityPack, limit: int = 420) -> pd.DataFrame:
    coefficients = pack.table("model_coefficients")
    windows = pack.table("training_window_trace")
    if coefficients.empty:
        return pd.DataFrame()
    view = coefficients.copy()
    if _is_ped_component_pack(pack):
        keep = [
            "component_model",
            "coefficient_status",
            "feature",
            "coefficient",
            "notes",
        ]
        return view[[col for col in keep if col in view.columns]].rename(
            columns={
                "component_model": "Component model",
                "coefficient_status": "Status",
                "notes": "Notes",
            }
        ).head(limit)
    if _is_weighted_ensemble_pack(pack):
        view["Component"] = view["component_model"].map(_component_label_map(pack))
        keep = [
            "Component",
            "component_model",
            "origin",
            "feature",
            "coefficient",
            "intercept",
            "coefficient_source",
            "reproducibility_status",
        ]
        return view[[col for col in keep if col in view.columns]].rename(
            columns={
                "component_model": "Component model",
                "origin": "Origin",
                "coefficient_source": "Coefficient source",
                "reproducibility_status": "Status",
            }
        ).sort_values([col for col in ["Component", "Origin", "feature"] if col in view.columns]).head(limit)
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


def light_ruc_coefficients_view(pack: LightRucReproducibilityPack, limit: int = 420) -> pd.DataFrame:
    return reproducibility_coefficients_view(pack, limit)


def reproducibility_sensitivity_view(pack: ReproducibilityPack, limit_per_basis: int = 12) -> pd.DataFrame:
    data = pack.table("scenario_sensitivities")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    if "score_basis" not in view.columns:
        view["score_basis"] = "replay_pack"
    if "scenario_name" not in view.columns:
        view["scenario_name"] = view.get("scenario_variable", pd.Series(dtype=str)).astype(str)
    if "delta_pct" not in view.columns:
        view["delta_pct"] = pd.NA
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


def light_ruc_sensitivity_view(pack: LightRucReproducibilityPack, limit_per_basis: int = 12) -> pd.DataFrame:
    return reproducibility_sensitivity_view(pack, limit_per_basis)


def reproducibility_training_window_view(pack: ReproducibilityPack) -> pd.DataFrame:
    data = pack.table("training_window_trace")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    if _is_ped_component_pack(pack):
        keep = ["origin", "window_status", "notes"]
        return view[[col for col in keep if col in view.columns]].rename(
            columns={
                "origin": "Origin",
                "window_status": "Window status",
                "notes": "Notes",
            }
        ).sort_values(["Origin"])
    if _is_weighted_ensemble_pack(pack):
        view["Component"] = view["component_model"].map(_component_label_map(pack))
        keep = [
            "Component",
            "origin",
            "window_quarters",
            "training_start_period_inferred",
            "training_end_period_inferred",
            "note",
        ]
        return view[[col for col in keep if col in view.columns]].rename(
            columns={
                "origin": "Origin",
                "window_quarters": "Window quarters",
                "training_start_period_inferred": "Training start",
                "training_end_period_inferred": "Training end",
                "note": "Note",
            }
        ).sort_values(["Component", "Origin"])
    view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = ["Score basis", "origin", "window_type", "window_length", "train_start", "train_end", "n_train"]
    return view[[col for col in keep if col in view.columns]].sort_values(["Score basis", "origin"])


def light_ruc_training_window_view(pack: LightRucReproducibilityPack) -> pd.DataFrame:
    return reproducibility_training_window_view(pack)


def plot_reproducibility_feature_importance(data: pd.DataFrame, stream_label: str) -> go.Figure:
    if data.empty:
        return empty_figure(f"{stream_label} feature-importance rows are not available.")
    view = data.copy().sort_values("importance_value", ascending=True)
    fig = px.bar(
        view,
        x="importance_value",
        y="feature_label" if "feature_label" in view.columns else "feature",
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
    return apply_layout(fig, "Feature importance / component weight evidence", height=360)


def plot_light_ruc_feature_importance(data: pd.DataFrame) -> go.Figure:
    return plot_reproducibility_feature_importance(data, LIGHT_RUC_REPRO_CONFIG.stream_label)


def plot_reproducibility_sensitivities(data: pd.DataFrame, stream_label: str) -> go.Figure:
    if data.empty:
        return empty_figure(f"{stream_label} scenario-sensitivity rows are not available.")
    if "mean_delta_pct" not in data.columns or not pd.to_numeric(data["mean_delta_pct"], errors="coerce").notna().any():
        note = _first_value(data, "scenario_name")
        message = str(note) if pd.notna(note) else f"{stream_label} scenario sensitivities are not numerically available."
        return empty_figure(message)
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


def plot_light_ruc_sensitivities(data: pd.DataFrame) -> go.Figure:
    return plot_reproducibility_sensitivities(data, LIGHT_RUC_REPRO_CONFIG.stream_label)


def reproducibility_ensemble_weight_view(pack: ReproducibilityPack) -> pd.DataFrame:
    registry = pack.table("model_registry")
    components = pack.table("component_predictions")
    if _is_ped_component_pack(pack) and not components.empty and "component_weight" in components.columns:
        component = _first_row(components.sort_values("component_rank") if "component_rank" in components.columns else components)
        return pd.DataFrame(
            [
                {
                    "Component": "C1",
                    "Component model": component.get("component_model", "PED__HPOREFINE_solver_static_convex_top18"),
                    "Algorithm": "HPO/static-solver component",
                    "Window": "Inherited from HPO component",
                    "Weight": float(component.get("component_weight", 1.0)),
                }
            ]
        )
    if registry.empty or "component_weight" not in registry.columns:
        return pd.DataFrame()
    view = registry.copy()
    view["Component"] = [f"C{i}" for i in range(1, len(view) + 1)]
    view["Weight"] = pd.to_numeric(view["component_weight"], errors="coerce")
    view["Algorithm"] = view.get("model_kind", pd.Series(dtype=str)).astype(str).map(_algorithm_label)
    view["Window"] = view.get("window", pd.Series(dtype=str)).astype(str).map(lambda value: f"{value} quarters" if value else "")
    return view[["Component", "component_model", "Algorithm", "Window", "Weight"]].rename(
        columns={"component_model": "Component model"}
    )


def reproducibility_ensemble_equation(pack: ReproducibilityPack) -> str:
    weights = reproducibility_ensemble_weight_view(pack)
    if weights.empty:
        return ""
    if len(weights) == 1 and abs(float(weights["Weight"].iloc[0]) - 1.0) <= 1e-12:
        return "Prediction = 1.0*C1"
    terms = [f"{row.Weight:.6f}*{row.Component}" for row in weights.itertuples(index=False)]
    return "Prediction = " + " + ".join(terms)


def reproducibility_scorecard_view(pack: ReproducibilityPack) -> pd.DataFrame:
    data = pack.table("scorecard_summary")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = [
        "Score basis",
        "pooled_mape",
        "quarterly_pooled_mape",
        "horizon_mean_mape",
        "annual_mape",
        "bias_pct",
        "quarterly_bias_pct",
        "n_pairs",
        "n_quarterly_pairs",
        "n_origins",
    ]
    keep = [col for col in keep if col in view.columns]
    return view[keep].rename(
        columns={
            "pooled_mape": "Pooled MAPE",
            "quarterly_pooled_mape": "Pooled MAPE",
            "horizon_mean_mape": "Horizon mean MAPE",
            "annual_mape": "Annual MAPE",
            "bias_pct": "Bias (%)",
            "quarterly_bias_pct": "Bias (%)",
            "n_pairs": "Pairs",
            "n_quarterly_pairs": "Pairs",
            "n_origins": "Origins",
        }
    )


def reproducibility_horizon_view(pack: ReproducibilityPack) -> pd.DataFrame:
    data = pack.table("horizon_profiles")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = ["Score basis", "horizon", "mape", "bias_pct", "n"]
    return view[[col for col in keep if col in view.columns]].rename(
        columns={"horizon": "Horizon", "mape": "MAPE", "bias_pct": "Bias (%)", "n": "Rows"}
    )


def reproducibility_annual_view(pack: ReproducibilityPack) -> pd.DataFrame:
    data = pack.table("annual_predictions")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    if "score_basis" in view.columns:
        view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = ["Score basis", "origin", "target_year", "actual", "pred", "ape", "error_pct", "value_available"]
    return view[[col for col in keep if col in view.columns]].rename(
        columns={
            "origin": "Origin",
            "target_year": "Target year",
            "actual": "Actual",
            "pred": "Prediction",
            "ape": "Absolute error (%)",
            "error_pct": "Error (%)",
            "value_available": "Available",
        }
    ).head(240)


def reproducibility_stress_view(pack: ReproducibilityPack) -> pd.DataFrame:
    data = pack.table("stress_horizon")
    if data.empty:
        return pd.DataFrame()
    view = data.copy()
    view["Score basis"] = view["score_basis"].map(_score_basis_label)
    keep = ["Score basis", "stress_bucket", "mape", "bias_pct", "n"]
    return view[[col for col in keep if col in view.columns]].rename(
        columns={"stress_bucket": "Stress bucket", "mape": "MAPE", "bias_pct": "Bias (%)", "n": "Rows"}
    )


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


def _is_ped_component_pack(pack: ReproducibilityPack) -> bool:
    return pack.config.stream_key == "ped"


def _is_weighted_ensemble_pack(pack: ReproducibilityPack) -> bool:
    registry = pack.table("model_registry")
    return "component_weight" in registry.columns and "ensemble_formula" in registry.columns


def _component_label_map(pack: ReproducibilityPack) -> dict[str, str]:
    weights = reproducibility_ensemble_weight_view(pack)
    if weights.empty:
        return {}
    return dict(zip(weights["Component model"].astype(str), weights["Component"].astype(str), strict=False))


def _short_component(value: Any) -> str:
    text = str(value)
    replacements = {
        "PED__HPOREFINE_solver_static_convex_top18": "C1 HPO/static-solver component",
        "HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64": "C1 ElasticNet ylag w64",
        "HEAVY_RUC__schiff__GBR_learning_rate0_06_max_depth1_n_estimators650__noylag__w64": "C2 Schiff GBR no ylag w64",
        "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators400__ylag__w52": "C3 dynamic GBR ylag w52",
        "HEAVY_RUC__dynamic_no_leads__GBR_learning_rate0_08_max_depth1_n_estimators150__ylag__w40": "C4 dynamic GBR ylag w40",
    }
    return replacements.get(text, text)


def _algorithm_label(value: Any) -> str:
    text = str(value).lower()
    if text == "elastic_net":
        return "ElasticNet"
    if text == "gbr":
        return "Gradient Boosting"
    return str(value).replace("_", " ").title()


def _max_abs_delta(*frames: pd.DataFrame) -> Any:
    candidates = [
        "max_abs_pred_delta",
        "max_abs_pred_delta_vs_evidence",
        "pred_delta_vs_evidence",
        "abs_pred_delta",
        "delta_quarterly_pooled_mape",
    ]
    values: list[float] = []
    for frame in frames:
        if frame.empty:
            continue
        for column in candidates:
            if column in frame.columns:
                series = pd.to_numeric(frame[column], errors="coerce").abs().dropna()
                values.extend(float(value) for value in series)
    return max(values) if values else pd.NA


def _optional_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([pd.NA] * len(frame), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")

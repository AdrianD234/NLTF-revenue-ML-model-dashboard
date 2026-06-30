from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Any
import zipfile

_RUNTIME_PYARROW24 = Path(__file__).resolve().parent / ".runtime_pyarrow24"
if _RUNTIME_PYARROW24.exists() and str(_RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_PYARROW24))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from model_dashboard.data_loader import (
    DEFAULT_EVIDENCE_PACK_ROOT,
    LoadedRun,
    curated_manifest_matches,
    curated_signature,
    discover_run_folders,
    evidence_pack_signature,
    load_curated_run,
    load_evidence_pack,
    load_run,
    resolve_evidence_pack_root,
    run_signature,
)
from model_dashboard.data.diagnostics import (
    DEFAULT_ACF_RESIDUAL_SCOPE,
    build_diagnostic_acf_source_table,
    select_diagnostic_acf_scope,
)
from model_dashboard.diagnostic_matrix import diagnostic_pass_matrix_html
from model_dashboard.forecast_imports import (
    BACKTEST_SUPPORTED_MAX_HORIZON,
    FORECAST_BUILDER_NOTE,
    FORECAST_BUILDER_TITLE,
    FORECAST_RUNNER_IMPORT_ERROR,
    HORIZON_SUPPORT_NOTE,
    SCENARIO_ROLE_BASECASE,
    SCENARIO_ROLE_COMPARISON,
    TEMPLATE_FILENAME,
    build_forecast_input_template_bytes,
    forecast_pack_zip_bytes,
    quarter_sort_key,
    resolve_scenario_role,
    run_forecast_workbook,
    sanitize_scenario_name,
    scenario_name_from_filename,
    validate_forecast_workbook,
    write_forecast_scenario_comparison,
)
from model_dashboard.labels import (
    DEFAULT_INPUT_PARENT,
    IGNORED_RUN_FOLDER_NAMES,
    OVERVIEW_STRESS_BUCKET_ORDER,
    SCHIFF_SPEC_BENCHMARK_LABEL,
    STRESS_BUCKET_ORDER,
    TERM_HELP,
    format_count,
    format_percent,
    format_pp,
    is_legacy_schiff_style_text,
    model_alias,
    shorten_model_name,
)
from model_dashboard.reproducibility_imports import (
    PED_INNER_HPO_AUDIT_STATUS,
    R2_GOVERNANCE_INFO_TEXT,
    R2_LADDER_NOTE,
    R2_LADDER_TITLE,
    R2_TRAINING_FIT_NOTE,
    diagnostics_r2_summary_frame,
    format_r2,
    load_ped_inner_hpo_audit_pack,
    ped_inner_hpo_audit_signature,
    ped_inner_hpo_audit_summary,
    ped_inner_hpo_gap_register_view,
    ped_inner_hpo_nested_trace_view,
    ped_inner_hpo_public_source_reference,
    ped_inner_hpo_source_artifacts_view,
    ped_inner_hpo_weight_detail_view,
    ped_inner_hpo_weight_source_view,
    reproducibility_coefficients_view,
    reproducibility_component_trace_view,
    reproducibility_feature_importance_view,
    reproducibility_ensemble_equation,
    reproducibility_ensemble_weight_view,
    reproducibility_annual_view,
    reproducibility_horizon_view,
    reproducibility_pack_signature,
    reproducibility_registry_view,
    reproducibility_replay_summary,
    reproducibility_sensitivity_view,
    reproducibility_scorecard_view,
    reproducibility_stress_view,
    reproducibility_stream_labels,
    reproducibility_training_window_view,
    r2_ladder_summary_frame,
    load_reproducibility_pack,
    plot_reproducibility_feature_importance,
    plot_reproducibility_sensitivities,
    reproducibility_component_r2_frame,
)
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    FAN_SOURCE_AUTO,
    FAN_SOURCE_NONE,
    FAN_SOURCE_OPTIONS,
    FAN_SOURCE_PRIORITY,
    FAN_SOURCE_SCENARIO_SPREAD,
    DEMAND_ELASTICITY_LEVELS,
    FLEET_EFFICIENCY_LEVELS,
    PED_BRIDGE_DEFAULT_MODE,
    PED_BRIDGE_MODE_LABELS,
    PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    PED_EFFICIENCY_BASELINE_SCENARIO_ID,
    PED_EFFICIENCY_DEFAULT_NOTE,
    PT_MODE_SHIFT_LEVELS,
    REVENUE_OUTLOOK_SCHEMA_VERSION,
    REVENUE_OUTLOOK_TITLE,
    REVENUE_STACK_DETAIL_CLEAN,
    REVENUE_STACK_DETAIL_FULL_FORMULA,
    REVENUE_STACK_DETAIL_LEVELS,
    REVENUE_STACK_MODE_BRIDGE,
    REVENUE_STACK_MODE_GROSS,
    REVENUE_STACK_MODES,
    SENSITIVITY_DEFAULT_NOTE,
    SENSITIVITY_LEVELS,
    STREAM_LABELS,
    RevenueOutlookPack,
    apply_ped_bridge_mode_layer,
    apply_revenue_sensitivity_layer,
    apply_ped_efficiency_sensitivity,
    load_revenue_outlook_pack,
    ped_efficiency_scenarios_frame,
    sensitivity_config_frame,
    promote_revenue_outlook_pack,
    revenue_outlook_signature,
    validate_promotable_comparison,
)
from model_dashboard.revenue_source_pack import (
    CURRENT_FINALIST_COMPOSITE_MODEL_ID,
    OPTIONAL_SOURCE_PACK_FILES,
    REQUIRED_SOURCE_PACK_FILES,
    REVENUE_SOURCE_PACK_DIR,
    REVENUE_SOURCE_PACK_RUNTIME_REVISION,
    REVENUE_SOURCE_PACK_SCHEMA_VERSION,
    SOURCE_SERIES_ALIASES,
    RevenueSourcePack,
    control_options,
    current_selection,
    load_revenue_source_pack,
    revenue_source_pack_signature,
)
from model_dashboard.presentation import (
    display_capability,
    render_cloud_preview_toggle,
    display_model,
    header_subtitle,
    is_executive,
    page_display_title,
    render_mode_toggle,
)
from model_dashboard.metrics import (
    best_by_stream,
    classify_error_rows,
    filter_to_model_keys,
    filter_by_common_controls,
    final_stress_frame,
    forecast_error_readout,
    governance_story_summary,
    inventory_rank_options,
    manager_conclusion,
    model_key_set,
    schiff_result_label,
    stress_readout,
)
from model_dashboard.plots import (
    empty_figure,
    plot_actual_vs_predicted,
    plot_autocorrelation_diagnostics,
    plot_candidate_landscape,
    plot_ensemble_composition,
    plot_error_distribution,
    plot_error_types,
    plot_feature_counts,
    plot_finalist_accuracy,
    plot_horizon_mape,
    plot_horizon_comparison,
    plot_improvement_vs_benchmark,
    plot_inventory_family_performance,
    plot_paired_improvement,
    plot_paired_scatter,
    plot_percent_error_over_time,
    plot_residual_vs_fitted,
    plot_benchmark_summary_table,
    plot_decision_summary_table,
    plot_schiff_benchmark,
    plot_schiff_class_mix,
    plot_schiff_finalist_mape,
    plot_scenario_stream_comparison,
    plot_stress_checks,
    plot_weight_over_time,
)
from model_dashboard.schema import INVENTORY_COLUMNS
from model_dashboard.score_basis import (
    PAPER_SCORE_BASIS,
    PAPER_SCORE_LABEL,
    SCORE_BASIS_OPTIONS,
    OPERATIONAL_SCORE_BASIS,
    project_scenario_comparison_frame,
    project_score_basis_frame,
    filter_score_basis_rows,
    score_basis_key,
    score_basis_label,
    score_basis_metric_label,
)
from model_dashboard.ui import (
    chart_card,
    dataframe_download,
    decision_brief,
    display_table,
    header,
    html_chart_card,
    info_panel,
    inject_theme,
    kpi_grid,
    section_title,
    warning_panel,
    filter_summary_grid,
    gov_kpi_grid,
    governance_cards,
)


LOADER_SCHEMA_VERSION = "stage1-governance-loader-v9-parquet-contract-schiff-class"
STREAMLIT_IMPORT_SURFACE_REVISION = "2026-06-25-revenue-source-pack-normalized-source-hashes-v1"
REVENUE_SOURCE_PACK_CACHE_REVISION = REVENUE_SOURCE_PACK_RUNTIME_REVISION
REVENUE_SOURCE_HORIZON_OPTIONS = ["Next 5 FY", "To FY2031", "Full common horizon"]
CURATED_DATA_DIR = Path("artifacts") / "curated_data"
REPRODUCIBILITY_PAGE = "Governance & Reproducibility"
REVENUE_OUTLOOK_PAGE = "Revenue Outlook"
SHOW_GOVERNANCE_PAGE_ENV_VAR = "NLTF_SHOW_GOVERNANCE_PAGE"
STREAMLIT_CLOUD_ENV_MARKERS = ("STREAMLIT_CLOUD", "STREAMLIT_SHARING_MODE", "IS_STREAMLIT_CLOUD")
SOURCE_WORKBOOK_NAME = "Master Copy revenue modelling workbook.xlsx"
SOURCE_WORKBOOK_REPO_PATH = Path("data") / "source_workbooks" / SOURCE_WORKBOOK_NAME
SOURCE_WORKBOOK_ENV_VAR = "REPRODUCIBILITY_SOURCE_WORKBOOK_PATH"
SOURCE_WORKBOOK_MANIFEST_PATH = Path("artifacts") / "source_workbook_manifest.json"
PAGE5_UI_CONTRACT_ROOT = Path("data") / "dashboard_evidence_pack_reproducibility" / "_ui_contract"
HEAVY_RUC_FORECAST_GAP_REASON = (
    "Heavy RUC: stored historical weighted replay and training-fit R2 are available. New-row Heavy forecasts require "
    "exact C3/C4 parent-state parity; current status: governed gap."
)
GENERIC_FORECAST_GAP_REASON = "Repo-local forward scorer is unavailable for this stream. This is not a model failure."
PAGE5_PANEL_CONTRACT_FILES = (
    "reproducibility_panel_contract.parquet",
    "reproducibility_panel_contract.csv",
)
PAGE5_PANEL_CONTRACT_REQUIRED_COLUMNS = (
    "stream",
    "panel",
    "status",
    "display_title",
    "evidence_file",
    "recommendation",
    "missing_message",
    "notes",
)

R2_LADDER_DISPLAY_NOTE = (
    "Training-fit R2, Calibration R2 and Forecast R2 answer different questions. "
    "High training-fit values are not directly comparable with lower out-of-sample forecast values."
)

R2_LADDER_HEADER_TOOLTIPS = {
    "Training-fit R2": (
        "Training-fit R2 measures how closely the model fitted the historical rows inside its own training window. "
        "This is the R2 most similar to the high in-sample R2 often reported in econometric papers. "
        "It is not a forecast test: a model can fit training history extremely well and still make future forecast errors."
    ),
    "Calibration R2": (
        "Calibration R2 measures whether higher forecasts line up with higher actual outcomes across validation rows. "
        "It comes from an actual-on-forecast calibration regression. It differs from Forecast R2 because it checks "
        "alignment of forecast levels with actual levels, rather than direct error around the final prediction."
    ),
    "Forecast R2": (
        "Forecast R2, or net forecast R2, measures how much variation in future actual outcomes is explained by the "
        "final delivered forecast. It is calculated after all model-composition steps are complete: GBM residual "
        "correction for Light RUC, weighted ensemble blending for Heavy RUC, and component replay for PED. "
        "It is out-of-sample, so it is usually much lower than Training-fit R2."
    ),
    "Score basis": (
        "Score basis is the validation lens. Operational pooled MAPE uses the broader current evidence-pack validation "
        "rows and pools all valid forecast errors together. Schiff paper horizon mean follows the paper-style scorecard: "
        "errors are grouped by forecast horizon, 2020-2021 test periods are excluded where applicable, and horizon "
        "results are averaged. The error formula is similar, but the rows and grouping differ."
    ),
    "Availability": (
        "Availability explains whether fitted training-window rows were found. Available means Training-fit R2 can be "
        "computed. Partial or missing means the dashboard can show Forecast R2 and Calibration R2, but deeper "
        "training-fit evidence is incomplete."
    ),
}

R2_LADDER_DISPLAY_COLUMNS = [
    "Stream",
    "Model",
    "Training-fit R2",
    "Calibration R2",
    "Forecast R2",
    "Rows",
    "Score basis",
    "Availability",
    "Interpretation",
]


def render_info_tooltip(label: str, tooltip_text: str, *, css_class: str = "summary-tooltip") -> str:
    """Return a small accessible tooltip without depending on optional UI exports."""
    safe_label = html.escape(label)
    safe_text = html.escape(tooltip_text)
    slug = "".join(char if char.isalnum() else "-" for char in label.lower()).strip("-")
    digest = hashlib.sha1(f"{label}|{tooltip_text}".encode("utf-8")).hexdigest()[:8]
    tooltip_id = f"tooltip-{slug}-{digest}"
    return (
        f"<span class='{css_class}-trigger' tabindex='0' role='button' "
        f"aria-label='{safe_label}: {safe_text}' aria-describedby='{tooltip_id}' title='{safe_text}'>?"
        f"<span class='{css_class}-text' role='tooltip' id='{tooltip_id}'>{safe_text}</span>"
        "</span>"
    )


@st.cache_data(show_spinner=False)
def cached_load_run(run_path: str, signature: tuple[tuple[str, int, int], ...], schema_version: str) -> LoadedRun:
    del signature
    del schema_version
    return load_run(run_path)


@st.cache_data(show_spinner=False)
def cached_load_curated_run(
    curated_path: str,
    run_path: str,
    curated_sig: tuple[tuple[str, int, int], ...],
    run_sig: tuple[tuple[str, int, int], ...],
    schema_version: str,
) -> LoadedRun:
    del curated_sig
    del run_sig
    del schema_version
    return load_curated_run(curated_path, run_path)


@st.cache_data(show_spinner=False, ttl=300)
def cached_discover_run_folders(
    parent_path: str,
    ignored_names: tuple[str, ...],
    parent_signature: tuple[bool, int, int],
) -> tuple[str, ...]:
    del parent_signature
    runs = discover_run_folders(Path(parent_path).expanduser(), set(ignored_names))
    return tuple(str(path) for path in runs)


@st.cache_data(show_spinner=False)
def cached_load_evidence_pack(
    data_root: str,
    repo_root: str,
    pack_sig: tuple[tuple[str, int, int], ...],
    schema_version: str,
) -> LoadedRun:
    del pack_sig
    del schema_version
    return load_evidence_pack(data_root, repo_root)


@st.cache_data(show_spinner=False)
def cached_load_reproducibility_pack(stream_label: str, signature: tuple[tuple[str, int, int], ...]) -> Any:
    del signature
    return load_reproducibility_pack(stream_label)


@st.cache_data(show_spinner=False)
def cached_load_ped_inner_hpo_audit_pack(signature: tuple[tuple[str, int, int], ...]) -> Any:
    del signature
    return load_ped_inner_hpo_audit_pack()


@st.cache_data(show_spinner=False)
def cached_load_revenue_outlook_pack(
    pack_dir: str,
    repo_root: str,
    signature: tuple[tuple[str, int, int], ...],
    schema_version: str,
) -> RevenueOutlookPack | None:
    del signature
    del schema_version
    return load_revenue_outlook_pack(pack_dir, repo_root=repo_root)


@st.cache_data(show_spinner=False)
def cached_load_revenue_source_pack(
    pack_dir: str,
    repo_root: str,
    signature: tuple[tuple[str, int, int], ...],
    schema_version: str,
) -> RevenueSourcePack | None:
    del signature
    del schema_version
    return load_revenue_source_pack(pack_dir, repo_root=repo_root)


def _pack_table(pack: RevenueOutlookPack | None, name: str, fallback: pd.DataFrame | None = None) -> pd.DataFrame:
    if pack is None:
        return pd.DataFrame() if fallback is None else fallback
    value = getattr(pack, name, None)
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame() if fallback is None else fallback


def _normalize_sensitivity_level(value: Any) -> str:
    text = str(value or "Off").strip()
    if text.lower() == "medium":
        return "Med"
    for option in SENSITIVITY_LEVELS:
        if text.lower() == option.lower():
            return option
    return "Off"


def sensitivity_option_label(kind: str, level: str) -> str:
    level = _normalize_sensitivity_level(level)
    if kind == "fleet_efficiency":
        if level == "Off":
            return "Off (0.0% p.a.)"
        if level == "Custom":
            return "Custom"
        value = FLEET_EFFICIENCY_LEVELS.get(level, 0.0) * 100.0
        return f"{level} ({value:.1f}% p.a.)"
    if kind == "pt_mode_shift":
        if level == "Off":
            return "Off (0.0% p.a.)"
        if level == "Custom":
            return "Custom"
        value = PT_MODE_SHIFT_LEVELS.get(level, 0.0) * 100.0
        value_text = f"{value:.2f}".rstrip("0").rstrip(".")
        if "." not in value_text:
            value_text = f"{value:.1f}"
        return f"{level} ({value_text}% p.a. from FY2030)"
    if kind == "demand_elasticity":
        if level == "Off":
            return "Off"
        if level == "Custom":
            return "Custom"
        ped = DEMAND_ELASTICITY_LEVELS.get("PED", {}).get(level, 0.0)
        light = DEMAND_ELASTICITY_LEVELS.get("LIGHT_RUC", {}).get(level, 0.0)
        heavy = DEMAND_ELASTICITY_LEVELS.get("HEAVY_RUC", {}).get(level, 0.0)
        return f"{level}: PED {ped:.3f} / Light RUC {light:.3f} / Heavy RUC {heavy:.3f}"
    return level


def _key_float(value: float | int | None) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.8g}"
    except Exception:
        return ""


def selected_sensitivity_key(
    fleet_efficiency: str,
    pt_mode_shift: str,
    demand_elasticity: str,
    *,
    custom_fleet_efficiency_pct: float | None = None,
    custom_pt_shift_pct: float | None = None,
    custom_ped_elasticity: float | None = None,
    custom_light_elasticity: float | None = None,
    custom_heavy_elasticity: float | None = None,
    cost_per_km_ratio: float | None = None,
) -> tuple[str, str, str, str, str, str, str, str, str]:
    return (
        _normalize_sensitivity_level(fleet_efficiency),
        _normalize_sensitivity_level(pt_mode_shift),
        _normalize_sensitivity_level(demand_elasticity),
        _key_float(custom_fleet_efficiency_pct),
        _key_float(custom_pt_shift_pct),
        _key_float(custom_ped_elasticity),
        _key_float(custom_light_elasticity),
        _key_float(custom_heavy_elasticity),
        _key_float(cost_per_km_ratio),
    )


def is_default_sensitivity(
    fleet_efficiency: str,
    pt_mode_shift: str,
    demand_elasticity: str,
    cost_per_km_ratio: float | None = None,
) -> bool:
    return (
        _normalize_sensitivity_level(fleet_efficiency) == "Off"
        and _normalize_sensitivity_level(pt_mode_shift) == "Off"
        and _normalize_sensitivity_level(demand_elasticity) == "Off"
        and _key_float(cost_per_km_ratio) == ""
    )


def _is_default_sensitivity_key(sensitivity_key: tuple[Any, ...]) -> bool:
    if len(sensitivity_key) < 9:
        return False
    return sensitivity_key[:3] == ("Off", "Off", "Off") and all(str(value or "") == "" for value in sensitivity_key[3:])


def revenue_outlook_lazy_table(label: str, key: str, *, default: bool = False, caption: str | None = None) -> bool:
    show = st.toggle(label, value=default, key=key)
    if caption and not show:
        st.caption(caption)
    return bool(show)


class RevenueOutlookRenderTimer:
    def __init__(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.timings_ms: dict[str, float] = {}
        self._starts: dict[str, float] = {}

    def start(self, label: str) -> None:
        if self.enabled:
            self._starts[label] = perf_counter()

    def stop(self, label: str) -> None:
        if self.enabled and label in self._starts:
            self.timings_ms[label] = round((perf_counter() - self._starts.pop(label)) * 1000.0, 2)


def _revenue_outlook_perf_debug_enabled() -> bool:
    return env_flag("REVENUE_OUTLOOK_PERF_DEBUG") is True


def _render_revenue_outlook_timings(timer: RevenueOutlookRenderTimer) -> None:
    if not timer.enabled or not timer.timings_ms:
        return
    parts = [f"{label}: {value:,.1f} ms" for label, value in timer.timings_ms.items()]
    st.caption("Revenue Outlook render timings (dev): " + "; ".join(parts))


@st.cache_data(show_spinner=False)
def cached_revenue_outlook_selectors(
    signature: tuple[tuple[str, int, int], ...],
    _pack: RevenueOutlookPack,
) -> dict[str, Any]:
    del signature
    chart_rows = _pack_table(_pack, "revenue_chart_rows")
    line_reconciliation = _pack_table(_pack, "revenue_line_reconciliation")
    stack_components = _pack_table(_pack, "revenue_stack_components")
    ped_bridge_mode_config = _pack_table(_pack, "ped_bridge_mode_config")
    return {
        "stream_options": _revenue_outlook_stream_options(chart_rows),
        "fed_path_options": _revenue_outlook_fed_path_options(chart_rows),
        "trace_options": _revenue_outlook_trace_options(chart_rows),
        "fy_options": _revenue_outlook_fy_options(chart_rows),
        "bridge_mode_lookup": _ped_bridge_mode_label_lookup(ped_bridge_mode_config),
        "line_source_options": _revenue_line_source_options(line_reconciliation),
        "line_section_options": _revenue_line_section_options(line_reconciliation),
        "line_fy_bounds": _revenue_line_fy_bounds(line_reconciliation),
        "stack_source_options": _revenue_line_source_options(stack_components),
        "stack_mode_options": _revenue_stack_mode_options(stack_components),
        "stack_section_options": _revenue_line_section_options(stack_components),
        "stack_fy_bounds": _revenue_line_fy_bounds(stack_components),
        "stack_overlay_options": _revenue_stack_overlay_options(stack_components),
        "sensitivity_labels": {
            "fleet_efficiency": {level: sensitivity_option_label("fleet_efficiency", level) for level in SENSITIVITY_LEVELS},
            "pt_mode_shift": {level: sensitivity_option_label("pt_mode_shift", level) for level in SENSITIVITY_LEVELS},
            "demand_elasticity": {level: sensitivity_option_label("demand_elasticity", level) for level in SENSITIVITY_LEVELS},
        },
    }


def _bridge_mode_frames_for_pack(
    pack: RevenueOutlookPack,
    bridge_mode: str,
    *,
    include_derived_frames: bool = True,
) -> dict[str, pd.DataFrame]:
    return apply_ped_bridge_mode_layer(
        chart_rows=_pack_table(pack, "revenue_chart_rows"),
        line_reconciliation=_pack_table(pack, "revenue_line_reconciliation"),
        bridge_components=_pack_table(pack, "revenue_bridge_components"),
        future_revenue_forecasts=_pack_table(pack, "future_revenue_forecasts"),
        ped_revenue_bridge_audit=_pack_table(pack, "ped_revenue_bridge_audit"),
        bridge_mode=bridge_mode,
        include_derived_frames=include_derived_frames,
    )


def _apply_sensitivity_for_key(
    bridge_frames: dict[str, pd.DataFrame],
    sensitivity_config: pd.DataFrame,
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str],
) -> dict[str, pd.DataFrame]:
    fleet_efficiency, pt_mode_shift, demand_elasticity = sensitivity_key[:3]
    custom_fleet = float(sensitivity_key[3]) if sensitivity_key[3] else None
    custom_pt = float(sensitivity_key[4]) if sensitivity_key[4] else None
    custom_ped = float(sensitivity_key[5]) if sensitivity_key[5] else None
    custom_light = float(sensitivity_key[6]) if sensitivity_key[6] else None
    custom_heavy = float(sensitivity_key[7]) if sensitivity_key[7] else None
    cost_ratio = float(sensitivity_key[8]) if sensitivity_key[8] else None
    return apply_revenue_sensitivity_layer(
        chart_rows=bridge_frames["chart_rows"],
        line_reconciliation=bridge_frames["line_reconciliation"],
        bridge_components=bridge_frames["revenue_bridge_components"],
        future_revenue_forecasts=bridge_frames["future_revenue_forecasts"],
        ped_revenue_bridge_audit=bridge_frames["ped_revenue_bridge_audit"],
        sensitivity_config=sensitivity_config,
        fleet_efficiency=fleet_efficiency,
        pt_mode_shift=pt_mode_shift,
        demand_elasticity=demand_elasticity,
        custom_fleet_efficiency_pct=custom_fleet,
        custom_pt_shift_pct=custom_pt,
        custom_ped_elasticity=custom_ped,
        custom_light_elasticity=custom_light,
        custom_heavy_elasticity=custom_heavy,
        cost_per_km_ratio=cost_ratio,
    )


@st.cache_data(show_spinner=False)
def cached_revenue_outlook_view(
    signature: tuple[tuple[str, int, int], ...],
    selected_series: str,
    time_grain: str,
    fed_path: str,
    traces: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> dict[str, Any]:
    del signature
    bridge_frames = _bridge_mode_frames_for_pack(
        _pack,
        bridge_mode,
        include_derived_frames=not _is_default_sensitivity_key(sensitivity_key),
    )
    sensitivity_config = _pack_table(_pack, "sensitivity_config", sensitivity_config_frame())
    if _is_default_sensitivity_key(sensitivity_key):
        sensitivity_frames = {
            "chart_rows": bridge_frames["chart_rows"],
            "line_reconciliation": bridge_frames["line_reconciliation"],
            "revenue_formula_residuals": bridge_frames["revenue_formula_residuals"],
            "revenue_stack_components": bridge_frames["revenue_stack_components"],
            "revenue_bridge_components": bridge_frames["revenue_bridge_components"],
            "future_revenue_forecasts": bridge_frames["future_revenue_forecasts"],
            "sensitivity_impact_audit": pd.DataFrame(),
        }
        sensitivity_fast_path = True
    else:
        sensitivity_frames = _apply_sensitivity_for_key(bridge_frames, sensitivity_config, sensitivity_key)
        sensitivity_fast_path = False

    chart_rows = sensitivity_frames["chart_rows"]
    filtered_rows = _filter_revenue_outlook_rows(
        chart_rows,
        time_grain=time_grain,
        stream_labels=[selected_series],
        fed_paths=[fed_path],
        trace_names=list(traces),
    )
    filtered_bridge = _filter_revenue_bridge_rows(
        sensitivity_frames["revenue_bridge_components"],
        [selected_series],
        _scenario_names_for_traces(chart_rows, list(traces)),
        [fed_path],
    )
    return {
        **sensitivity_frames,
        "filtered_rows": filtered_rows,
        "filtered_bridge": filtered_bridge,
        "gap_summary": _revenue_outlook_gap_summary(filtered_bridge),
        "ped_revenue_bridge_audit": bridge_frames["ped_revenue_bridge_audit"],
        "ped_bridge_mode_impact_audit": bridge_frames["ped_bridge_mode_impact_audit"],
        "sensitivity_fast_path": sensitivity_fast_path,
    }


@st.cache_data(show_spinner=False)
def cached_revenue_outlook_detail_frames(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> dict[str, pd.DataFrame]:
    del signature
    bridge_frames = _bridge_mode_frames_for_pack(_pack, bridge_mode, include_derived_frames=True)
    if _is_default_sensitivity_key(sensitivity_key):
        return {
            **bridge_frames,
            "sensitivity_impact_audit": pd.DataFrame(),
        }
    sensitivity_config = _pack_table(_pack, "sensitivity_config", sensitivity_config_frame())
    sensitivity_frames = _apply_sensitivity_for_key(bridge_frames, sensitivity_config, sensitivity_key)
    return {
        **sensitivity_frames,
        "ped_revenue_bridge_audit": bridge_frames.get("ped_revenue_bridge_audit", pd.DataFrame()),
        "ped_bridge_mode_impact_audit": bridge_frames.get("ped_bridge_mode_impact_audit", pd.DataFrame()),
    }


@st.cache_data(show_spinner=False)
def cached_revenue_outlook_sensitivity_audit(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> pd.DataFrame:
    del signature
    bridge_frames = _bridge_mode_frames_for_pack(_pack, bridge_mode, include_derived_frames=True)
    sensitivity_config = _pack_table(_pack, "sensitivity_config", sensitivity_config_frame())
    return _apply_sensitivity_for_key(bridge_frames, sensitivity_config, sensitivity_key).get("sensitivity_impact_audit", pd.DataFrame())


def directory_signature(path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (False, 0, 0)
    return (path.exists(), int(stat.st_mtime_ns), int(stat.st_size))


def env_flag(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on", "show"}:
        return True
    if normalised in {"0", "false", "no", "off", "hide"}:
        return False
    return None


def is_streamlit_cloud_runtime() -> bool:
    from model_dashboard.presentation import cloud_preview_enabled

    if cloud_preview_enabled():
        return True
    for name in STREAMLIT_CLOUD_ENV_MARKERS:
        marker = env_flag(name)
        if marker is not None:
            return marker
        if os.environ.get(name, "").strip():
            return True
    return Path(__file__).resolve().as_posix().startswith("/mount/src/")


def should_show_governance_page() -> bool:
    override = env_flag(SHOW_GOVERNANCE_PAGE_ENV_VAR)
    if override is not None:
        return override
    return not is_streamlit_cloud_runtime()


def should_show_local_audit_controls() -> bool:
    return not is_streamlit_cloud_runtime()


def dashboard_pages() -> list[str]:
    pages = ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark", REVENUE_OUTLOOK_PAGE]
    if should_show_governance_page():
        pages.append(REPRODUCIBILITY_PAGE)
    return pages


def main() -> None:
    st.set_page_config(page_title="NTLF Revenue Modelling", layout="wide", initial_sidebar_state="collapsed")
    inject_theme()
    inject_global_theme()
    pages = dashboard_pages()
    st.session_state.setdefault("gov_page", "Overview")
    if st.session_state["gov_page"] not in pages:
        st.session_state["gov_page"] = "Overview"
    header_slot = st.empty()
    initial_page = st.session_state["gov_page"]
    initial_index = pages.index(initial_page) + 1
    with header_slot.container():
        header(
            "NTLF Revenue Modelling",
            header_subtitle(),
            page_chip=f"Page {initial_index} of {len(pages)} - {page_display_title(initial_page)}",
        )

    active_path = render_run_sidebar()
    loaded = load_active_run(active_path)
    if loaded is None:
        st.stop()

    for warning in global_warnings(loaded.warnings):
        warning_panel(warning)

    current_page = render_primary_navigation(pages)
    current_index = pages.index(current_page) + 1
    with header_slot.container():
        header(
            "NTLF Revenue Modelling",
            header_subtitle(),
            page_chip=f"Page {current_index} of {len(pages)} - {page_display_title(current_page)}",
        )
    controls = render_filter_sidebar(loaded)
    if current_page not in {REPRODUCIBILITY_PAGE, REVENUE_OUTLOOK_PAGE}:
        controls = render_top_filter_bar(loaded, controls)

    if current_page == "Overview":
        render_overview(loaded, controls)
    elif current_page == "Diagnostics":
        render_diagnostics(loaded, controls)
    elif current_page == "Scenario Comparison":
        render_scenario_comparison(loaded, controls)
    elif current_page == "Schiff Benchmark":
        render_schiff_benchmark_page(loaded, controls)
    elif current_page == REVENUE_OUTLOOK_PAGE:
        render_revenue_outlook_page(loaded)
    else:
        render_governance_reproducibility_page(loaded, controls)

def render_primary_navigation(pages: list[str]) -> str:
    # The analyst-mode toggle lives in the filter strip's More popover; the
    # page radio keeps the full content width (its CSS pulls it into the
    # header band, so nothing else may share this block).
    return st.radio(
        "Governance pages",
        pages,
        horizontal=True,
        key="gov_page",
        label_visibility="collapsed",
        format_func=page_display_title,
    )


def render_run_sidebar() -> str:
    requested_root = Path(
        os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT")
        or os.environ.get("STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT")
        or DEFAULT_EVIDENCE_PACK_ROOT
    ).expanduser()
    data_root = resolve_evidence_pack_root(requested_root)
    st.session_state["active_data_root"] = str(data_root)
    return str(data_root)


def load_active_run(active_path: str) -> LoadedRun | None:
    data_root = Path(active_path).expanduser()
    repo_root = Path(__file__).resolve().parent
    with st.spinner(f"Loading dashboard evidence pack from {data_root}..."):
        try:
            loaded = cached_load_evidence_pack(
                str(data_root),
                str(repo_root),
                evidence_pack_signature(data_root),
                LOADER_SCHEMA_VERSION,
            )
            if loaded.data and any(not frame.empty for frame in loaded.data.values() if isinstance(frame, pd.DataFrame)):
                return loaded
        except Exception as exc:
            warning_panel(f"Dashboard evidence pack could not be loaded: {exc}")

    warning_panel(
        "No governed evidence pack was loaded. Set DASHBOARD_EVIDENCE_PACK_ROOT to the folder containing "
        "manifest.json and data/*.parquet. Legacy run-folder CSV/XLSX outputs are available only through "
        "review utilities, not the main dashboard path."
    )
    return None


def is_schema_diagnostic_warning(text: str) -> bool:
    return "mixed percent-unit pattern" in str(text).lower()


def global_warnings(warnings: tuple[str, ...]) -> list[str]:
    return [warning for warning in warnings if not is_schema_diagnostic_warning(warning)]


def schema_diagnostics(warnings: tuple[str, ...]) -> list[str]:
    return [warning for warning in warnings if is_schema_diagnostic_warning(warning)]


def render_filter_sidebar(loaded: LoadedRun) -> dict[str, Any]:
    summary = loaded.data.get("summary", pd.DataFrame())
    qpred = loaded.data.get("quarterly_predictions", pd.DataFrame())
    base = summary if not summary.empty else qpred

    stage_options = ["all"]
    if "stage" in base.columns:
        stage_options.extend(sorted(str(value) for value in base["stage"].dropna().unique()))
    stage = "all"

    stream_options = sorted(base["stream_label"].dropna().unique()) if "stream_label" in base.columns else []
    streams = stream_options

    source_options = sorted(summary["source_family"].dropna().unique()) if "source_family" in summary.columns else []
    source_families = source_options

    variant_options = sorted(summary["variant"].dropna().unique()) if "variant" in summary.columns else []
    variants = variant_options

    top_n = int(st.session_state.get("advanced_top_n", 50))
    show_schiff = bool(st.session_state.get("advanced_show_schiff", True))
    show_finalists = bool(st.session_state.get("advanced_show_finalists", True))
    show_screen = bool(st.session_state.get("advanced_show_screen", True))
    show_final = bool(st.session_state.get("advanced_show_final", True))
    show_static = bool(st.session_state.get("advanced_show_static", True))
    show_prequential = bool(st.session_state.get("advanced_show_prequential", True))
    hide_outliers = bool(st.session_state.get("advanced_hide_outliers", True))

    return {
        "stage": stage,
        "streams": streams,
        "source_families": source_families,
        "variants": variants,
        "top_n": top_n,
        "show_schiff": show_schiff,
        "show_finalists": show_finalists,
        "show_screen": show_screen,
        "show_final": show_final,
        "show_static": show_static,
        "show_prequential": show_prequential,
        "hide_outliers": hide_outliers,
    }


def render_top_filter_bar(loaded: LoadedRun, controls: dict[str, Any]) -> dict[str, Any]:
    summary = loaded.data.get("summary", pd.DataFrame())
    qpred = loaded.data.get("quarterly_predictions", pd.DataFrame())
    base = summary if not summary.empty else qpred

    stream_options = sorted(base["stream_label"].dropna().astype(str).unique()) if "stream_label" in base.columns else []
    family_options = sorted(summary["source_family"].dropna().astype(str).unique()) if "source_family" in summary.columns else []
    stage_options = sorted(base["stage"].dropna().astype(str).unique()) if "stage" in base.columns else []
    baseline_options = ["Finalist", "Schiff", "Best challenger"]
    horizon_options = ["1-12 qtrs", "1-4 qtrs", "5-8 qtrs", "9-12 qtrs"]
    date_options = ["All", "2022-23", "2024+", "2020-21"]

    defaults = {
        "top_stream": "All",
        "top_family": "All",
        "top_stage": "all",
        "top_horizon": "1-12 qtrs",
        "top_score_basis": PAPER_SCORE_LABEL,
        "advanced_top_n": 50,
        "advanced_show_schiff": True,
        "advanced_show_finalists": True,
        "advanced_show_screen": True,
        "advanced_show_final": True,
        "advanced_show_static": True,
        "advanced_show_prequential": True,
        "advanced_hide_outliers": True,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    valid_defaults = {
        "top_stream": ["All"] + stream_options,
        "top_family": ["All"] + family_options,
        "top_stage": ["all"] + stage_options,
        "top_horizon": horizon_options,
        "top_score_basis": SCORE_BASIS_OPTIONS,
    }
    for key, options in valid_defaults.items():
        if st.session_state.get(key) not in options:
            st.session_state[key] = defaults[key]
    try:
        advanced_top_n = int(st.session_state.get("advanced_top_n", defaults["advanced_top_n"]))
    except (TypeError, ValueError):
        advanced_top_n = defaults["advanced_top_n"]
    advanced_top_n = min(200, max(10, advanced_top_n))
    st.session_state["advanced_top_n"] = int(round(advanced_top_n / 10) * 10)
    for key in [
        "advanced_show_schiff",
        "advanced_show_finalists",
        "advanced_show_screen",
        "advanced_show_final",
        "advanced_show_static",
        "advanced_show_prequential",
        "advanced_hide_outliers",
    ]:
        st.session_state[key] = bool(st.session_state.get(key, defaults[key]))

    with st.container(border=True):
        st.markdown("<div class='filter-title'>Governance filters</div>", unsafe_allow_html=True)
        filter_cols = st.columns([1.05, 1.18, 0.78, 1.05, 1.25, 0.72, 0.48])
        with filter_cols[0]:
            st.selectbox(
                "Stream",
                ["All"] + stream_options,
                key="top_stream",
                format_func=lambda value: "All Streams" if value == "All" else str(value),
            )
        with filter_cols[1]:
            st.selectbox(
                "Model Family",
                ["All"] + family_options,
                key="top_family",
                format_func=lambda value: "All Families" if value == "All" else str(value).replace("_", " "),
            )
        with filter_cols[2]:
            st.selectbox(
                "Stage",
                ["all"] + stage_options,
                key="top_stage",
                format_func=lambda value: "All stages" if value == "all" else str(value).replace("_", " ").title(),
            )
        with filter_cols[3]:
            st.selectbox(
                "Horizon",
                horizon_options,
                key="top_horizon",
                help="Filters the horizon-profile and stress charts to the selected forecast-horizon window.",
                format_func=lambda value: "1-12 Quarters" if value == "1-12 qtrs" else str(value).replace("qtrs", "quarters"),
            )
        with filter_cols[4]:
            st.selectbox(
                "Score Basis",
                SCORE_BASIS_OPTIONS,
                key="top_score_basis",
                help="Default governance reporting uses paper-style horizon MAPE. Operational pooled MAPE is available explicitly for operational scorecard checks.",
            )
        with filter_cols[5]:
            st.button(
                "Reset Filters",
                type="primary",
                use_container_width=True,
                on_click=reset_top_filter_state,
                args=(defaults,),
            )
        with filter_cols[6]:
            with st.popover("More", use_container_width=True):
                render_mode_toggle()
                render_cloud_preview_toggle()
                controls = render_advanced_controls(loaded, controls)

        stream_choice = st.session_state["top_stream"]
        family_choice = st.session_state["top_family"]
        stage_choice = st.session_state["top_stage"]
        score_basis_choice = st.session_state["top_score_basis"]
        horizon_choice = st.session_state["top_horizon"]
        horizon_label = "1-12 Quarters" if horizon_choice == "1-12 qtrs" else str(horizon_choice).replace("qtrs", "quarters")
        filter_items = [
            ("Stream", "All Streams" if stream_choice == "All" else stream_choice),
            ("Model Family", "All Families" if family_choice == "All" else str(family_choice).replace("_", " ")),
            ("Stage", "All stages" if stage_choice == "all" else str(stage_choice).replace("_", " ").title()),
            ("Score Basis", score_basis_choice),
            ("Horizon", horizon_label),
        ]
        active_filter_line = " | ".join(f"{label}: {value}" for label, value in filter_items)

        view_state = {
            "run_folder": str(loaded.run_dir),
            "run_name": Path(str(loaded.run_dir)).name,
            "stream": "All Streams" if stream_choice == "All" else stream_choice,
            "model_family": "All Families" if family_choice == "All" else family_choice,
            "stage": stage_choice,
            "score_basis": score_basis_choice,
            "horizon": horizon_label,
            "top_n": controls.get("top_n"),
            "show_schiff": controls.get("show_schiff"),
            "show_finalists": controls.get("show_finalists"),
            "hide_outliers": controls.get("hide_outliers"),
        }
        st.session_state["last_view_state"] = view_state
    updated = dict(controls)
    updated["stage"] = stage_choice
    updated["streams"] = stream_options if stream_choice == "All" else [stream_choice]
    updated["source_families"] = family_options if family_choice == "All" else [family_choice]
    updated["score_basis"] = score_basis_key(score_basis_choice)
    updated["score_basis_label"] = score_basis_label(score_basis_choice)
    updated["horizon_bucket_filter"] = [] if horizon_choice == "1-12 qtrs" else [horizon_choice]
    return updated


def render_advanced_controls(loaded: LoadedRun, controls: dict[str, Any]) -> dict[str, Any]:
    st.markdown("**Advanced controls**")
    with st.expander("Legacy run-folder review", expanded=False):
        st.caption("Legacy CSV/XLSX run folders are review-only and do not replace the governed Parquet dashboard source.")
        parent_text = st.text_input("Run parent folder", value=str(DEFAULT_INPUT_PARENT), key="run_parent_inline")
        parent_path = Path(parent_text).expanduser()
        refresh_discovery = st.button("Refresh run list", key="refresh_run_list_inline")
        if refresh_discovery:
            st.session_state["discovered_run_paths"] = list(
                cached_discover_run_folders(
                    str(parent_path),
                    tuple(sorted(IGNORED_RUN_FOLDER_NAMES)),
                    directory_signature(parent_path),
                )
            )
        elif "discovered_run_paths" not in st.session_state:
            st.session_state["discovered_run_paths"] = []
        discovered = [Path(path) for path in st.session_state.get("discovered_run_paths", [])]
        if discovered:
            labels = [f"{path.parent.name} / {path.name}" for path in discovered]
            selected_label = st.selectbox("Completed model run", labels, key="completed_run_inline")
            selected_path = discovered[labels.index(selected_label)]
            st.caption(f"Selected for review only: {selected_path}")
        st.text_input("Manual run folder path for review", value="", key="manual_run_inline")

    controls = dict(controls)
    controls["top_n"] = st.slider(
        "Top N candidates",
        min_value=10,
        max_value=200,
        step=10,
        key="advanced_top_n",
    )
    control_cols = st.columns(4)
    with control_cols[0]:
        controls["show_schiff"] = st.toggle(SCHIFF_SPEC_BENCHMARK_LABEL, key="advanced_show_schiff")
        controls["show_finalists"] = st.toggle("Finalists", key="advanced_show_finalists")
    with control_cols[1]:
        controls["show_screen"] = st.toggle("Screen", key="advanced_show_screen")
        controls["show_final"] = st.toggle("Final", key="advanced_show_final")
    with control_cols[2]:
        controls["show_static"] = st.toggle("Static", key="advanced_show_static")
        controls["show_prequential"] = st.toggle("Prequential", key="advanced_show_prequential")
    with control_cols[3]:
        controls["hide_outliers"] = st.toggle(
            "Hide outliers",
            key="advanced_hide_outliers",
        )
    view_state = st.session_state.get("last_view_state", {"run_folder": str(loaded.run_dir)})
    st.download_button(
        "Export current view JSON",
        json.dumps(view_state, indent=2).encode("utf-8"),
        file_name="stage1_current_view_settings.json",
        mime="application/json",
        use_container_width=True,
    )
    with st.expander("File read status", expanded=False):
        display_table(loaded.file_status, height=260)
    return controls


def reset_top_filter_state(defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        st.session_state[key] = value
    for key in [
        "lazy_diagnostics_inventory",
        "lazy_diagnostics_audit",
        "lazy_scenario_forecast_stress",
        "lazy_schiff_candidate_ensemble",
    ]:
        if key in st.session_state:
            del st.session_state[key]


def run_evidence_caption(
    loaded: LoadedRun,
    stage_choice: str,
    family_choice: str = "All",
    family_count: int | None = None,
) -> str:
    status = loaded.file_status
    found = int(status["Found?"].eq("Yes").sum()) if not status.empty and "Found?" in status.columns else 0
    total = len(status)
    if family_choice == "All":
        family_label = f"All {family_count} families" if family_count is not None else "All families"
    else:
        family_label = family_choice
    curated = loaded.data.get("curated_manifest", pd.DataFrame())
    source_label = "Governed Parquet data pack"
    curated_rows = ""
    if not curated.empty and "row_counts" in curated.columns:
        try:
            row_counts = curated.iloc[0].get("row_counts", {})
            if isinstance(row_counts, str):
                row_counts = json.loads(row_counts.replace("'", '"'))
            total_rows = sum(int(value) for value in dict(row_counts).values())
            curated_rows = f" | Curated rows: {format_count(total_rows)}"
        except Exception:
            curated_rows = " | Curated pack loaded"
    return (
        f"Run evidence: {Path(str(loaded.run_dir)).name} | Source: {source_label} | {found}/{total} files loaded{curated_rows} | "
        f"Stage filter: {stage_choice} | Family scope: {family_label} | {run_footer_label(loaded)}"
    )


def run_footer_label(loaded: LoadedRun) -> str:
    pack_label = data_pack_version_label(loaded)
    if loaded.file_status.empty or "Last modified" not in loaded.file_status.columns:
        return f"Data as of: selected run | {pack_label}"
    modified = loaded.file_status.loc[loaded.file_status["Found?"].eq("Yes"), "Last modified"].dropna()
    if modified.empty:
        return f"Data as of: selected run | {pack_label}"
    return f"Data as of: {modified.max()} | {pack_label}"


def data_pack_version_label(loaded: LoadedRun) -> str:
    manifest = loaded.manifest or {}
    schema = str(manifest.get("schema_version") or "unknown-schema")
    created = str(manifest.get("created_at") or "unknown-date")
    resolved_root = str(manifest.get("resolved_root") or loaded.run_dir)
    row_counts = manifest.get("row_counts", {}) if isinstance(manifest, dict) else {}
    candidate_rows = "-"
    if isinstance(row_counts, dict):
        candidate_rows = format_count(int(row_counts.get("candidate_cone", row_counts.get("candidate_cone.parquet", 0)) or 0))
    evidence_hash = str(manifest.get("evidence_hash") or "")[:12]
    hash_text = f" | hash {evidence_hash}" if evidence_hash else ""
    return f"Data pack version: {schema} | created {created} | root {resolved_root} | candidate rows {candidate_rows}{hash_text}"


def common_filter(df: pd.DataFrame, controls: dict[str, Any], include_source_variant: bool = True) -> pd.DataFrame:
    source_families = controls["source_families"] if include_source_variant else None
    variants = controls["variants"] if include_source_variant else None
    out = filter_by_common_controls(
        df,
        stage=controls["stage"],
        streams=controls["streams"],
        source_families=source_families,
        variants=variants,
        include_schiff=controls["show_schiff"],
        show_screen=controls["show_screen"],
        show_final=controls["show_final"],
    )
    if not controls["show_finalists"] and "is_finalist" in out.columns:
        out = out[~out["is_finalist"]]
    if "score_basis" in out.columns and controls.get("score_basis"):
        out = out[out["score_basis"].astype(str).eq(str(controls["score_basis"]))].copy()
    return out


def score_basis_projected(frame: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    return project_score_basis_frame(frame, controls.get("score_basis", PAPER_SCORE_BASIS))


HORIZON_BUCKET_RANGES = {"1-4 qtrs": (1, 4), "5-8 qtrs": (5, 8), "9-12 qtrs": (9, 12)}


def _apply_horizon_bucket_filter(frame: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    """Apply the global Horizon filter. Default (1-12 qtrs) leaves frames untouched."""
    buckets = [b for b in controls.get("horizon_bucket_filter") or [] if b in HORIZON_BUCKET_RANGES]
    if not buckets or frame is None or frame.empty:
        return frame
    if "horizon" in frame.columns:
        lo, hi = HORIZON_BUCKET_RANGES[buckets[0]]
        horizons = pd.to_numeric(frame["horizon"], errors="coerce")
        return frame[horizons.between(lo, hi)].copy()
    if "stress_bucket" in frame.columns:
        keep = set(buckets) | {"Annual"}
        return frame[frame["stress_bucket"].astype(str).isin(keep)].copy()
    return frame


def selected_horizon_frame(loaded: LoadedRun, controls: dict[str, Any]) -> pd.DataFrame:
    source = loaded.data.get("scorecard_horizon_df", pd.DataFrame())
    if source is None or source.empty:
        source = loaded.data.get("horizon_df", pd.DataFrame())
    out = filter_score_basis_rows(source, controls.get("score_basis", PAPER_SCORE_BASIS))
    return _apply_horizon_bucket_filter(out, controls)


def selected_stress_frame(loaded: LoadedRun, controls: dict[str, Any]) -> pd.DataFrame:
    source = loaded.data.get("scorecard_stress_df", pd.DataFrame())
    if source is None or source.empty:
        source = loaded.data.get("stress", pd.DataFrame())
    out = filter_score_basis_rows(source, controls.get("score_basis", PAPER_SCORE_BASIS))
    return _apply_horizon_bucket_filter(out, controls)


def render_overview(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    summary = common_filter(score_basis_projected(loaded.data.get("summary", pd.DataFrame()), controls), controls)
    recommended = common_filter(score_basis_projected(loaded.data.get("recommended", pd.DataFrame()), controls), controls, include_source_variant=False)
    schiff_rows = common_filter(score_basis_projected(loaded.data.get("schiff_df", pd.DataFrame()), controls), controls, include_source_variant=False)
    errors = loaded.data.get("errors", pd.DataFrame())
    best = best_by_stream(recommended)
    raw_qpred = loaded.data.get("quarterly_predictions", pd.DataFrame())
    best_models = set(best["model"].dropna().astype(str)) if not best.empty and "model" in best.columns else set()
    if best_models and "model" in raw_qpred.columns:
        qpred = raw_qpred[raw_qpred["model"].astype(str).isin(best_models)].copy()
    else:
        best_keys = model_key_set(best) if not best.empty else set()
        qpred = filter_to_model_keys(raw_qpred, best_keys) if best_keys else raw_qpred
    qpred = common_filter(qpred, controls, include_source_variant=False)
    stress_frame = overview_stress_frame(loaded, recommended, controls)
    story = governance_story_summary(recommended, loaded.data.get("paired_vs_schiff", pd.DataFrame()), stress_frame, errors)

    st.session_state["candidate_frontier_mode"] = DEFAULT_CANDIDATE_FRONTIER_MODE
    candidate_landscape = build_candidate_landscape_frame(loaded, controls, DEFAULT_CANDIDATE_FRONTIER_MODE)
    candidate_context = candidate_frontier_count_context(loaded, controls, candidate_landscape)
    gov_kpi_grid(overview_kpi_cards(summary, recommended, story, errors, candidate_context, schiff_rows=schiff_rows))
    if is_executive():
        render_executive_stream_cards()
        render_action_card("Overview")
    basis_metric = score_basis_metric_label(controls.get("score_basis", PAPER_SCORE_BASIS))
    accuracy_subtitle = f"{basis_metric} by stream. Lower is better."
    if not best.empty and {"stream_label", "quarterly_mape", "annual_mape"}.issubset(best.columns):
        finalist_read = "; ".join(
            f"{str(row['stream_label']).replace(' VKT per capita', '').replace(' volume', '')}: "
            f"{float(row['quarterly_mape']):.2f}% qtr / {float(row['annual_mape']):.2f}% annual"
            for _, row in best.sort_values("stream_label").iterrows()
            if pd.notna(row.get("quarterly_mape")) and pd.notna(row.get("annual_mape"))
        )
        if finalist_read:
            accuracy_subtitle = f"Current Parquet finalists using {basis_metric}: {finalist_read}. Lower is better."

    if is_executive():
        exec_cols = st.columns([1.0, 1.0])
        with exec_cols[0]:
            chart_card(
                "Finalist Forecast Accuracy",
                accuracy_subtitle,
                compact_figure(plot_finalist_accuracy(recommended), 260),
            )
        with exec_cols[1]:
            chart_card(
                "Stress and Horizon Checks",
                overview_stress_subtitle(controls),
                compact_figure(plot_stress_checks(stress_frame), 260),
                overview_stress_watch_note(stress_frame),
            )
        tech_cols = st.columns([1.0, 1.0])
        with tech_cols[0]:
            landscape = overview_candidate_landscape_frame(loaded, controls)
            candidate_context = candidate_frontier_count_context(loaded, controls, landscape)
            chart_card(
                "Candidate Search Frontier",
                CANDIDATE_FRONTIER_CAPTION,
                compact_figure(plot_candidate_landscape(landscape), 240),
                overview_frontier_note(landscape, candidate_context),
            )
        with tech_cols[1]:
            ensemble_weights = loaded.data.get("weights", pd.DataFrame()).copy()
            fig, mapping = plot_ensemble_composition(ensemble_weights)
            chart_card(
                "Finalist Ensemble Composition",
                "Positive solver weights for each finalist ensemble.",
                compact_figure(fig, 240),
            )
        return

    upper = st.columns([1.0, 1.0])
    with upper[0]:
        chart_card(
            "1. Finalist Forecast Accuracy",
            accuracy_subtitle,
            compact_figure(plot_finalist_accuracy(recommended), 260),
        )
    with upper[1]:
        landscape = overview_candidate_landscape_frame(loaded, controls)
        candidate_context = candidate_frontier_count_context(loaded, controls, landscape)
        chart_card(
            "2. Candidate Search Frontier",
            CANDIDATE_FRONTIER_CAPTION,
            compact_figure(plot_candidate_landscape(landscape), 260),
            overview_frontier_note(landscape, candidate_context),
        )

    lower = st.columns([1.0, 1.0])
    with lower[0]:
        ensemble_weights = loaded.data.get("weights", pd.DataFrame()).copy()
        fig, mapping = plot_ensemble_composition(ensemble_weights)
        chart_card(
            "3. Finalist Ensemble Composition",
            "Positive solver weights for PED VKT per capita, Light RUC volume and Heavy RUC volume finalists.",
            compact_figure(fig, 260),
        )
    with lower[1]:
        chart_card(
            "4. Stress and Horizon Checks",
            overview_stress_subtitle(controls),
            compact_figure(plot_stress_checks(stress_frame), 260),
            overview_stress_watch_note(stress_frame),
        )


@st.cache_data(show_spinner=False)
def _executive_card_inputs(signature: float) -> list[dict[str, str]]:
    """Stream recommendation cards built directly from the governed packs.

    Presentation only: every number is read from finalists.parquet,
    schiff_benchmark.parquet, diagnostic_pass_matrix.parquet and the
    reproducibility parity audits - nothing is recomputed.
    """
    del signature
    from model_dashboard.governance_constants import (
        CURRENT_REPRO_PACK_DIRS,
        EVIDENCE_PACK_DATA,
        REPRODUCIBILITY_BASE,
    )

    pack = EVIDENCE_PACK_DATA
    fin = pd.read_parquet(pack / "finalists.parquet").set_index("stream")
    schiff = pd.read_parquet(pack / "schiff_benchmark.parquet").set_index("stream")
    matrix = pd.read_parquet(pack / "diagnostic_pass_matrix.parquet")
    repro_root = REPRODUCIBILITY_BASE

    cards: list[dict[str, str]] = []
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        if stream not in fin.index:
            continue
        row = fin.loc[stream]
        label = str(row["stream_label"])
        q_mape = float(row["quarterly_mape"])
        gain = ""
        if stream in schiff.index:
            gain_pp = float(schiff.loc[stream, "quarterly_mape"]) - q_mape
            gain = f"{gain_pp:+.2f} pp vs Schiff benchmark"
        m_rows = matrix[(matrix["stream_label"] == label)]
        overall = str(m_rows[m_rows["diagnostic_test"] == "Overall"]["pass_status"].iloc[0]) if len(m_rows) else "Pass"
        badge = {"Pass": "Promote", "Watch": "Watch", "Fail": "Monitor"}.get(overall, "Watch")
        open_items = m_rows[(m_rows["diagnostic_test"] != "Overall") & (m_rows["pass_status"] != "Pass")]
        if open_items.empty:
            caveat = "No open diagnostic watch items."
        else:
            caveat = "Standing monitoring: " + ", ".join(
                f"{t} ({s})" for t, s in zip(open_items["diagnostic_test"], open_items["pass_status"], strict=False))
        readiness = "Historically reproducible"
        sdir = repro_root / CURRENT_REPRO_PACK_DIRS.get(stream, "")
        audit_path = sdir / "forward_scorer_parity_audit.json"
        try:
            if audit_path.exists():
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                readiness = ("Forecast-ready (parity verified)"
                             if str(audit.get("parity_status")) == "passed"
                             else "Forward scorer not verified")
            elif (sdir / "future_forecasts.parquet").exists():
                readiness = "Forecast-ready"
        except Exception:
            pass
        cards.append({
            "stream": label,
            "badge": badge,
            "gain_pp": float(schiff.loc[stream, "quarterly_mape"]) - q_mape if stream in schiff.index else None,
            "mape_value": q_mape,
            "model": display_model(str(row["model"])),
            "mape": f"{q_mape:.2f}%",
            "annual": f"{float(row['annual_mape']):.2f}%",
            "gain": gain,
            "readiness": readiness,
            "caveat": caveat,
        })
    return cards


def render_executive_stream_cards() -> None:
    """Three plain-English recommendation cards under the KPI band."""
    from model_dashboard.presentation import BADGE_COLORS

    from model_dashboard.governance_constants import EVIDENCE_PACK_DATA

    try:
        signature = (EVIDENCE_PACK_DATA / "finalists.parquet").stat().st_mtime
        cards = _executive_card_inputs(signature)
    except Exception:
        return
    if not cards:
        return
    blocks = []
    for card in cards:
        color = BADGE_COLORS.get(card["badge"], "#334155")
        gain_html = (f"<div style='color:#15803d;font-weight:600;font-size:0.8rem;margin-top:2px'>"
                     f"{card['gain']}</div>") if card["gain"] else ""
        blocks.append(
            f"<div style='flex:1 1 260px;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;"
            f"padding:14px 16px;min-width:240px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px'>"
            f"<span style='font-weight:700;color:#0f172a'>{card['stream']}</span>"
            f"<span style='background:{color};color:#fff;border-radius:999px;padding:1px 12px;"
            f"font-size:0.75rem;font-weight:700'>{card['badge']}</span></div>"
            f"<div style='color:#475569;font-size:0.8rem;margin-top:4px'>{card['model']}</div>"
            f"<div style='margin-top:8px;font-size:1.25rem;font-weight:700;color:#0f4c81'>{card['mape']}"
            f"<span style='font-size:0.75rem;color:#64748b;font-weight:500'> quarterly MAPE | "
            f"{card['annual']} annual</span></div>"
            f"{gain_html}"
            f"<div style='color:#334155;font-size:0.8rem;margin-top:6px'>{card['readiness']}</div>"
            f"<div style='color:#64748b;font-size:0.76rem;margin-top:4px'>{card['caveat']}</div>"
            f"</div>"
        )
    st.markdown(
        "<div style='display:flex;gap:12px;flex-wrap:wrap;margin:0.35rem 0 0.6rem'>"
        + "".join(blocks) + "</div>",
        unsafe_allow_html=True,
    )


def _executive_cards_safe() -> list[dict[str, Any]]:
    from model_dashboard.governance_constants import EVIDENCE_PACK_DATA

    try:
        signature = (EVIDENCE_PACK_DATA / "finalists.parquet").stat().st_mtime
        return _executive_card_inputs(signature)
    except Exception:
        return []


def render_action_card(page: str) -> None:
    """One management action card per executive page (presentation only:
    every statement is composed from the governed card inputs)."""
    if not is_executive():
        return
    cards = _executive_cards_safe()
    if not cards:
        return
    by_badge: dict[str, list[str]] = {"Promote": [], "Watch": [], "Monitor": []}
    for card in cards:
        by_badge.setdefault(card["badge"], []).append(card["stream"])
    gains = ", ".join(card["gain"].replace(" vs Schiff benchmark", "") for card in cards if card["gain"])
    watch_items = "; ".join(
        f"{card['stream']}: {card['caveat'].replace('Standing monitoring: ', '')}"
        for card in cards if card["caveat"] != "No open diagnostic watch items.")
    ready = [card["stream"] for card in cards if card["readiness"].startswith("Forecast-ready")]

    if page == "Overview":
        title, tone = "Recommended decision", "#15803d"
        parts = []
        if by_badge["Promote"]:
            parts.append(f"Adopt the recommended models for {', '.join(by_badge['Promote'])}.")
        if by_badge["Watch"]:
            parts.append(f"{', '.join(by_badge['Watch'])} recommended with advisory watch items.")
        if by_badge["Monitor"]:
            parts.append(f"{', '.join(by_badge['Monitor'])} remains usable but carries standing diagnostic "
                         "monitoring items - review them on the Model Confidence page before promotion.")
        parts.append(f"All three finalists beat the Schiff specification benchmark ({gains} quarterly MAPE).")
        body = " ".join(parts)
    elif page == "Diagnostics":
        title, tone = "Governance watch item", "#b45309"
        body = ((f"Open monitoring items - {watch_items}. These are tracked, disclosed and do not "
                 "change any governed status; click any cell below for the glass-box detail.")
                if watch_items else
                "No open diagnostic watch items across the three streams.")
    elif page == "Scenario Comparison":
        title, tone = "Scenario implication", "#0f4c81"
        body = (f"{', '.join(ready) if ready else 'No stream'} can score new assumption workbooks. "
                "Streams without a verified forward scorer return an explicit governed gap - "
                "never a fabricated number - so scenario totals are trustworthy by construction.")
    else:  # Schiff Benchmark
        title, tone = "Audit conclusion", "#0f4c81"
        body = (f"{len(cards)}/3 finalists beat the Schiff specification benchmark under the paper-style "
                f"scorecard ({gains}). The benchmark is replicated from the published workbook and scored "
                "on identical quarters, so the comparison is like-for-like.")
    st.markdown(
        f"<div style='display:flex;gap:10px;align-items:flex-start;background:#ffffff;"
        f"border:1px solid #e2e8f0;border-left:4px solid {tone};border-radius:10px;"
        f"padding:10px 14px;margin:0.3rem 0 0.55rem'>"
        f"<div style='min-width:max-content;font-weight:800;color:{tone};font-size:0.78rem;"
        f"text-transform:uppercase;letter-spacing:0.04em;padding-top:1px'>{title}</div>"
        f"<div style='color:#334155;font-size:0.84rem'>{body}</div></div>",
        unsafe_allow_html=True,
    )


def _confidence_badges_for(card: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(dimension, label, color) triples. Accuracy banding is a presentation
    heuristic and is documented in the caption; all other dimensions read the
    governed statuses directly."""
    gain = card.get("gain_pp")
    mape = card.get("mape_value")
    if gain is not None and mape is not None and gain >= 2.0 and mape < 5.0:
        accuracy = ("Strong", "#15803d")
    elif gain is not None and gain > 0:
        accuracy = ("Moderate", "#0f4c81")
    else:
        accuracy = ("Watch", "#b45309")
    diag = {"Promote": ("Pass", "#15803d"), "Watch": ("Watch", "#b45309"),
            "Monitor": ("Fail items", "#b91c1c")}[card["badge"]]
    readiness_text = card["readiness"]
    if readiness_text.startswith("Forecast-ready"):
        ready = ("Ready", "#15803d")
    elif "not verified" in readiness_text:
        ready = ("Not verified", "#b91c1c")
    else:
        ready = ("Historical only", "#b45309")
    repro = (("Full (parity verified)", "#15803d") if "parity verified" in readiness_text
             else ("Exact replay", "#0f4c81"))
    return [("Accuracy", *accuracy), ("Diagnostics", *diag),
            ("Forecast", *ready), ("Reproducibility", *repro)]


def render_confidence_badges() -> None:
    """Per-stream confidence strip on the Model Confidence page (executive)."""
    cards = _executive_cards_safe()
    if not cards:
        return
    blocks = []
    for card in cards:
        pills = "".join(
            f"<span style='display:inline-flex;align-items:center;gap:5px;margin:2px 8px 2px 0'>"
            f"<span style='color:#64748b;font-size:0.72rem'>{dim}</span>"
            f"<span style='background:{color};color:#fff;border-radius:999px;padding:1px 10px;"
            f"font-size:0.72rem;font-weight:700'>{label}</span></span>"
            for dim, label, color in _confidence_badges_for(card))
        blocks.append(
            f"<div style='flex:1 1 300px;background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;"
            f"padding:8px 12px;min-width:280px'>"
            f"<div style='font-weight:700;color:#0f172a;font-size:0.82rem;margin-bottom:3px'>{card['stream']}</div>"
            f"{pills}</div>")
    st.markdown(
        "<div style='display:flex;gap:10px;flex-wrap:wrap;margin:0.25rem 0 0.2rem'>" + "".join(blocks) + "</div>",
        unsafe_allow_html=True,
    )
    st.caption("Accuracy banding: Strong = beats benchmark by >= 2pp with quarterly MAPE < 5%; Moderate = beats benchmark; "
               "Watch otherwise. Diagnostics, forecast readiness and reproducibility read the governed statuses directly.")


def compact_figure(fig: Any, height: int, showlegend: bool | None = None) -> Any:
    if hasattr(fig, "update_layout"):
        has_subplot_titles = bool(getattr(fig.layout, "annotations", None))
        top_margin = 58 if has_subplot_titles else 18
        # Figures that deliberately place their legend below the plot (e.g. the
        # candidate frontier, to keep the Plotly modebar clear) keep that
        # placement and their bottom margin.
        legend_y = getattr(getattr(fig.layout, "legend", None), "y", None)
        keeps_bottom_legend = legend_y is not None and legend_y < 0
        if keeps_bottom_legend and height <= 340:
            # Too short for a below-axis legend: the chart's own annotations
            # carry the stream identification, so drop the legend cleanly.
            fig.update_layout(showlegend=False)
            keeps_bottom_legend = False
        bottom_margin = 92 if keeps_bottom_legend else 30
        fig.update_layout(title_text="", height=height, margin={"l": 30, "r": 14, "t": top_margin, "b": bottom_margin})
        if not keeps_bottom_legend:
            fig.update_layout(
                legend={
                    "orientation": "h",
                    "yanchor": "bottom",
                    "y": 1.22 if has_subplot_titles else 1.0,
                    "xanchor": "center" if has_subplot_titles else "left",
                    "x": 0.5 if has_subplot_titles else 0.0,
                    "font": {"size": 10},
                }
            )
        if showlegend is not None:
            fig.update_layout(showlegend=showlegend)
        if showlegend is False:
            fig.layout.annotations = ()
    return fig


DEFAULT_CANDIDATE_FRONTIER_MODE = "Balanced all-stream frontier view"
PREVIOUS_CANDIDATE_FRONTIER_MODE = "All-stream frontier view"
LEGACY_CANDIDATE_FRONTIER_MODE = "Curated" + " cone sample"
CANDIDATE_FRONTIER_CAPTION = (
    "Balanced all-stream frontier view; visual frontier samples are anchored to current finalists and Schiff "
    "specification benchmarks and are excluded from governance scoring."
)


def overview_candidate_landscape_frame(loaded: LoadedRun, controls: dict[str, Any]) -> pd.DataFrame:
    st.session_state["candidate_frontier_mode"] = DEFAULT_CANDIDATE_FRONTIER_MODE
    return build_candidate_landscape_frame(loaded, controls, DEFAULT_CANDIDATE_FRONTIER_MODE)


def build_candidate_landscape_frame(loaded: LoadedRun, controls: dict[str, Any], mode: str) -> pd.DataFrame:
    candidate = loaded.data.get("candidate_df", loaded.data.get("summary", pd.DataFrame()))
    summary = loaded.data.get("summary", pd.DataFrame())
    if candidate.empty:
        return summary
    candidate = exclude_legacy_schiff_style_rows(candidate)
    if mode == "Competitive frontier":
        mask = pd.Series(False, index=candidate.index)
        for column in ["is_frontier", "is_current_recommended", "is_pure_schiff", "is_pdf_reference"]:
            if column in candidate.columns:
                mask = mask | candidate[column].fillna(False).astype(bool)
        landscape = candidate[mask].copy()
    elif mode == "Top candidates only":
        mask = pd.Series(False, index=candidate.index)
        for column in ["is_top_quarterly", "is_top_annual", "is_current_recommended", "is_pure_schiff"]:
            if column in candidate.columns:
                mask = mask | candidate[column].fillna(False).astype(bool)
        landscape = candidate[mask].copy()
    elif mode == "Show outliers":
        landscape = candidate.copy()
    else:
        if not summary.empty:
            landscape = summary
        elif "plot_default_include" in candidate.columns:
            landscape = candidate[candidate["plot_default_include"].fillna(False).astype(bool)].copy()
        else:
            landscape = candidate.copy()
    landscape = score_basis_projected(landscape, controls)
    return common_filter(landscape, controls)


def exclude_legacy_schiff_style_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame
    if "is_legacy_schiff_style" in frame.columns:
        return frame[~frame["is_legacy_schiff_style"].fillna(False).astype(bool)].copy()
    model_text = frame.get("model", pd.Series("", index=frame.index)).astype(str)
    role_text = frame.get("candidate_role", pd.Series("", index=frame.index)).astype(str)
    mask = [
        is_legacy_schiff_style_text(model, role)
        for model, role in zip(model_text, role_text, strict=False)
    ]
    return frame[~pd.Series(mask, index=frame.index)].copy()


def candidate_frontier_count_context(
    loaded: LoadedRun,
    controls: dict[str, Any],
    plotted: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Return precise candidate-count context for the KPI and frontier caption."""
    candidate = loaded.data.get("candidate_df", pd.DataFrame())
    if candidate is None or candidate.empty:
        plotted_count = len(plotted) if plotted is not None else 0
        return {
            "count": plotted_count,
            "label": f"{format_count(plotted_count)} filtered plotted candidates",
            "subtext": "filtered plotted candidates",
            "filtered": True,
            "total_curated": 0,
            "default_plotted": plotted_count,
        }
    mask = pd.Series(False, index=candidate.index)
    for column in ["plot_default_include", "is_plot_candidate"]:
        if column in candidate.columns:
            mask = mask | candidate[column].fillna(False).astype(bool)
    default_plotted = candidate[mask].copy() if mask.any() else candidate.copy()
    default_plotted = exclude_legacy_schiff_style_rows(default_plotted)
    default_plotted = score_basis_projected(default_plotted, controls)
    filtered_default = common_filter(default_plotted, controls)
    plotted_frame = plotted if plotted is not None else filtered_default
    plotted_count = len(plotted_frame)
    total_curated = len(candidate)
    is_filtered = plotted_count != len(default_plotted)
    if is_filtered:
        label = f"{format_count(plotted_count)} filtered plotted candidates"
        subtext = "filtered plotted candidates"
    else:
        label = f"{format_count(plotted_count)} plotted candidates from {format_count(total_curated)} curated rows"
        subtext = f"from {format_count(total_curated)} curated rows"
    return {
        "count": plotted_count,
        "label": label,
        "subtext": subtext,
        "filtered": is_filtered,
        "total_curated": total_curated,
        "default_plotted": len(default_plotted),
        "coverage": candidate_frontier_coverage_text(candidate),
    }


def candidate_frontier_coverage_text(candidate: pd.DataFrame) -> str:
    if candidate is None or candidate.empty or "stream_label" not in candidate.columns:
        return "Candidate coverage unavailable."
    mask = pd.Series(False, index=candidate.index)
    for column in ["plot_default_include", "is_plot_candidate"]:
        if column in candidate.columns:
            mask = mask | candidate[column].fillna(False).astype(bool)
    plotted = candidate[mask].copy() if mask.any() else candidate.copy()
    counts = plotted["stream_label"].dropna().astype(str).value_counts().to_dict()
    light = int(counts.get("Light RUC volume", 0))
    ped = int(counts.get("PED VKT per capita", 0))
    heavy = int(counts.get("Heavy RUC volume", 0))
    return f"Coverage: PED {format_count(ped)} frontier rows; Light RUC {format_count(light)} frontier rows; Heavy RUC {format_count(heavy)} frontier rows."


def overview_frontier_note(summary: pd.DataFrame, count_context: dict[str, Any] | None = None) -> str:
    """Return a compact manager note for the Overview candidate landscape."""
    if summary is None or summary.empty:
        return "Frontier read: lower-left is better; no candidate rows are available for this filter."
    schiff_spec = 0
    benchmark_streams = 0
    if "is_pure_schiff" in summary.columns:
        anchor_mask = summary["is_pure_schiff"].fillna(False).astype(bool)
    elif "schiff_class" in summary.columns:
        anchor_mask = summary["schiff_class"].astype(str).eq(SCHIFF_SPEC_BENCHMARK_LABEL)
    else:
        anchor_mask = pd.Series(False, index=summary.index)
    schiff_spec = int(anchor_mask.sum())
    if "stream_label" in summary.columns:
        benchmark_streams = int(summary.loc[anchor_mask, "stream_label"].dropna().nunique())
    suffix = (
        f"; {schiff_spec} plotted Schiff specification anchor rows / {benchmark_streams} benchmark streams"
        if schiff_spec
        else ""
    )
    label = str(count_context.get("label")) if count_context else f"{format_count(len(summary))} plotted candidates"
    coverage = f" {count_context.get('coverage')}" if count_context and count_context.get("coverage") else ""
    return f"Frontier read: {CANDIDATE_FRONTIER_CAPTION} Lower-left is better across {label}{suffix}.{coverage}"


def overview_stress_subtitle(controls: dict[str, Any]) -> str:
    basis = controls.get("score_basis", PAPER_SCORE_BASIS)
    basis_metric = score_basis_metric_label(basis)
    if basis == PAPER_SCORE_BASIS:
        return f"{basis_metric} across forecast horizon buckets only; policy windows are excluded from the default view."
    return f"{basis_metric} across forecast horizon buckets and policy stress windows."


def overview_stress_watch_note(stress_frame: pd.DataFrame) -> str:
    """Return a compact manager note for the Overview stress chart."""
    if stress_frame is None or stress_frame.empty or "mape" not in stress_frame.columns:
        return "Stress watch: no stress rows are available for the selected filters."
    data = stress_frame.copy()
    data["_mape"] = pd.to_numeric(data["mape"], errors="coerce")
    missing_note = ""
    if {"stream_label", "stress_bucket"}.issubset(data.columns):
        heavy_missing = data[
            data["stream_label"].astype(str).eq("Heavy RUC volume")
            & data["stress_bucket"].astype(str).isin(["2024+", "2022-23"])
            & data["_mape"].isna()
        ]
        if not heavy_missing.empty:
            missing_buckets = " / ".join(
                bucket for bucket in ["2024+", "2022-23"] if bucket in set(heavy_missing["stress_bucket"].astype(str))
            )
            missing_note = f" Data not available for Heavy RUC volume {missing_buckets}."
    visible = data.dropna(subset=["_mape"])
    if visible.empty:
        return "Stress watch: no numeric stress MAPE values are available for the selected filters."
    worst = visible.sort_values("_mape", ascending=False).iloc[0]
    stream = str(worst.get("stream_label", worst.get("stream", "selected stream")))
    bucket = str(worst.get("stress_bucket", "selected bucket"))
    return (
        f"Stress watch: weakest visible point is {stream} in {bucket} at {format_percent(float(worst['_mape']))} MAPE."
        f"{missing_note}"
    )


def overview_error_distribution_note(qpred: pd.DataFrame) -> str:
    if qpred is None or qpred.empty:
        return "Error distribution read: no finalist prediction rows are available for the selected filters."
    return (
        f"Error distribution read: central boxplot uses {format_count(len(qpred))} finalist prediction rows; "
        "full tails remain in Forecasts and Errors."
    )


def overview_stress_frame(loaded: LoadedRun, recommended: pd.DataFrame, controls: dict[str, Any] | None = None) -> pd.DataFrame:
    """Return the Overview stress frame for the selected score basis."""
    controls = controls or {"score_basis": PAPER_SCORE_BASIS}
    frame = final_stress_frame(
        selected_stress_frame(loaded, controls),
        loaded.data.get("quarterly_predictions", pd.DataFrame()),
        loaded.data.get("annual_predictions", pd.DataFrame()),
        recommended,
        include_extra_buckets=False,
    )
    if frame.empty or "stress_bucket" not in frame.columns:
        return frame
    reference_buckets = OVERVIEW_STRESS_BUCKET_ORDER if controls.get("score_basis", PAPER_SCORE_BASIS) == PAPER_SCORE_BASIS else STRESS_BUCKET_ORDER
    return frame[frame["stress_bucket"].astype(str).isin(reference_buckets)].copy()


def overview_kpi_cards(
    summary: pd.DataFrame,
    recommended: pd.DataFrame,
    story: pd.DataFrame,
    errors: pd.DataFrame,
    candidate_context: dict[str, Any] | None = None,
    schiff_rows: pd.DataFrame | None = None,
) -> list[tuple[str, str, str, str, str, str]]:
    finalists = best_by_stream(recommended)
    if schiff_rows is not None and not schiff_rows.empty:
        schiff = best_by_stream(schiff_rows)
    else:
        schiff = best_by_stream(summary[summary["is_schiff"]]) if not summary.empty and "is_schiff" in summary.columns else pd.DataFrame()
    finalist_q = float(finalists["quarterly_mape"].mean()) if not finalists.empty and "quarterly_mape" in finalists.columns else float("nan")
    finalist_a = float(finalists["annual_mape"].mean()) if not finalists.empty and "annual_mape" in finalists.columns else float("nan")
    schiff_q = float(schiff["quarterly_mape"].mean()) if not schiff.empty and "quarterly_mape" in schiff.columns else float("nan")
    schiff_a = float(schiff["annual_mape"].mean()) if not schiff.empty and "annual_mape" in schiff.columns else float("nan")
    q_delta = schiff_q - finalist_q if pd.notna(schiff_q) and pd.notna(finalist_q) else float("nan")
    a_delta = schiff_a - finalist_a if pd.notna(schiff_a) and pd.notna(finalist_a) else float("nan")
    beats = int((story.get("schiff_status", pd.Series(dtype=str)) == "Beats Schiff").sum()) if story is not None and not story.empty else 0
    total = len(story) if story is not None else 0
    candidate_count = int(candidate_context.get("count", len(summary))) if candidate_context else len(summary)
    candidate_subtext = str(candidate_context.get("subtext", "default curated cone rows")) if candidate_context else "default curated cone rows"
    return [
        ("Quarterly MAPE", format_percent(finalist_q), f"vs. Schiff specification benchmark {format_percent(schiff_q)}", f"{q_delta:.2f} pp gain" if pd.notna(q_delta) else "-", "good", "Q"),
        ("Annual MAPE", format_percent(finalist_a), f"vs. Schiff specification benchmark {format_percent(schiff_a)}", f"{a_delta:.2f} pp gain" if pd.notna(a_delta) else "-", "good", "A"),
        ("Plotted candidates", format_count(candidate_count), candidate_subtext, f"{format_count(len(recommended))} finalists", "good", "#"),
        (
            "Benchmark Pass",
            f"{beats}/{total}",
            f"{beats}/{total} beat Schiff specification benchmark",
            f"{format_count(len(errors))} logged diagnostics",
            "good" if total and beats == total else "mixed",
            "B",
        ),
    ]


def basic_cards_as_governance_kpis(
    cards: list[tuple[str, str, str]],
    icons: list[str],
    tones: list[str] | None = None,
) -> list[tuple[str, str, str, str, str, str]]:
    rendered: list[tuple[str, str, str, str, str, str]] = []
    tones = tones or ["good"] * len(cards)
    for idx, (title, value, subtext) in enumerate(cards):
        rendered.append(
            (
                title,
                value,
                subtext,
                "",
                tones[idx] if idx < len(tones) else "good",
                icons[idx] if idx < len(icons) else "G",
            )
        )
    return rendered


def diagnostic_calibration_r2_series(diagnostic_df: pd.DataFrame) -> tuple[pd.Series, str]:
    if diagnostic_df is None or diagnostic_df.empty:
        return pd.Series(dtype=float), ""
    for column in ("calibration_r2", "mz_r2", "adj_r2"):
        if column in diagnostic_df.columns:
            values = pd.to_numeric(diagnostic_df[column], errors="coerce")
            if values.notna().any():
                return values, column
    return pd.Series(dtype=float), ""


def diagnostic_kpi_cards(diagnostic_df: pd.DataFrame) -> list[tuple[Any, ...]]:
    finalists = diagnostic_df.copy()
    if "role" in finalists.columns:
        finalists = finalists[finalists["role"].astype(str).str.contains("finalist", case=False, na=False)]
    expected_tests = [
        "durbin_watson",
        "adj_r2",
        "adf_pvalue",
        "kpss_pvalue",
        "breusch_pagan_pvalue",
        "white_pvalue",
        "arch_lm_pvalue",
        "jarque_bera_pvalue",
        "cointegration_pvalue",
    ]
    available = sum(1 for column in expected_tests if column in finalists.columns and finalists[column].notna().any())
    dw = pd.to_numeric(finalists.get("durbin_watson", pd.Series(dtype=float)), errors="coerce").mean()
    calibration_r2_values, calibration_r2_source_column = diagnostic_calibration_r2_series(finalists)
    mean_calibration_r2 = calibration_r2_values.mean()
    bp = pd.to_numeric(finalists.get("breusch_pagan_pvalue", pd.Series(dtype=float)), errors="coerce")
    white = pd.to_numeric(finalists.get("white_pvalue", pd.Series(dtype=float)), errors="coerce")
    pass_mask = (bp > 0.05) | (white > 0.05)
    hetero_pass = int(pass_mask.fillna(False).sum())
    hetero_total = int(max(len(finalists), 0))
    calibration_tooltip = (
        "Calibration R2 is Mincer-Zarnowitz / actual-on-forecast validation R2. "
        "It is not the model's in-sample fit R2. Forecast R2 is reported in the detail panel."
    )
    calibration_subtext = (
        "Current finalists only; Mincer-Zarnowitz calibration"
        + (f" from {calibration_r2_source_column}" if calibration_r2_source_column else "")
    )
    return [
        ("Diagnostics Coverage", f"{available}/9", "diagnostic fields available", "", "good" if available >= 6 else "mixed", "D"),
        ("Mean Durbin-Watson", f"{dw:.2f}" if pd.notna(dw) else "-", "Current finalists only; near 2.0 is ideal", "", "good", "DW"),
        (
            "Mean calibration R2",
            f"{mean_calibration_r2:.2f}" if pd.notna(mean_calibration_r2) else "-",
            calibration_subtext,
            "",
            "good",
            "R2",
            calibration_tooltip,
        ),
        ("Heteroscedasticity Pass", f"{hetero_pass}/{hetero_total}", "Breusch-Pagan or White across streams", "", "good" if hetero_total and hetero_pass == hetero_total else "mixed", "H"),
    ]


def diagnostics_r2_detail_table(loaded: LoadedRun) -> pd.DataFrame:
    scorecard = loaded.data.get("scorecard_predictions", pd.DataFrame())
    diagnostics = loaded.data.get("diagnostic_df", pd.DataFrame())
    summary = diagnostics_r2_summary_frame(scorecard, diagnostics)
    if summary.empty:
        return pd.DataFrame(
            [
                {
                    "stream": "-",
                    "score_basis_label": "-",
                    "forecast_r2": "-",
                    "calibration_r2": "-",
                    "source_prediction_column": "-",
                    "calibration_r2_source_column": "-",
                    "n_rows": 0,
                    "interpretation": "Unavailable: scorecard prediction rows are missing.",
                }
            ]
        )
    table = summary[
        [
            "stream_label",
            "score_basis_label",
            "forecast_r2",
            "calibration_r2",
            "source_prediction_column",
            "calibration_r2_source_column",
            "n_rows",
            "interpretation",
        ]
    ].copy()
    table = table.rename(columns={"stream_label": "stream"})
    table["forecast_r2"] = table["forecast_r2"].map(format_r2)
    table["calibration_r2"] = table["calibration_r2"].map(format_r2)
    table["n_rows"] = pd.to_numeric(table["n_rows"], errors="coerce").fillna(0).astype(int)
    return table


def render_diagnostics_r2_panel(loaded: LoadedRun) -> None:
    with st.expander("Forecast R2 versus calibration R2", expanded=False):
        info_panel(
            f"{R2_GOVERNANCE_INFO_TEXT} "
            "Negative Forecast R2 is valid but indicates poorer fit than the stream mean; "
            "zero actual variance is shown as unavailable."
        )
        display_table(diagnostics_r2_detail_table(loaded), height=230, max_rows=12)


def r2_ladder_display_table(loaded: LoadedRun, selected_stream: str = "All streams") -> pd.DataFrame:
    summary = r2_ladder_summary_frame(loaded.data, Path(__file__).resolve().parent)
    if selected_stream != "All streams" and not summary.empty:
        summary = summary[summary["stream_label"].astype(str).eq(selected_stream)].copy()
    if summary.empty:
        return pd.DataFrame(
            [
                {
                    "Stream": selected_stream,
                    "Model": "-",
                    "Training-fit R2": "-",
                    "Calibration R2": "-",
                    "Forecast R2": "-",
                    "Rows": 0,
                    "Score basis": "-",
                    "Availability": "unavailable",
                    "Interpretation": "R2 ladder source rows are unavailable.",
                }
            ]
        )
    table = summary[
        [
            "stream",
            "model",
            "training_fit_r2",
            "calibration_r2",
            "forecast_r2",
            "n_rows",
            "score_basis",
            "availability_status",
            "interpretation",
        ]
    ].copy()
    for column in ["training_fit_r2", "calibration_r2", "forecast_r2"]:
        table[column] = table[column].map(format_r2_for_ladder_display)
    table["n_rows"] = pd.to_numeric(table["n_rows"], errors="coerce").fillna(0).astype(int)
    table["score_basis"] = table["score_basis"].map(score_basis_label)
    return table.rename(
        columns={
            "stream": "Stream",
            "model": "Model",
            "training_fit_r2": "Training-fit R2",
            "calibration_r2": "Calibration R2",
            "forecast_r2": "Forecast R2",
            "n_rows": "Rows",
            "score_basis": "Score basis",
            "availability_status": "Availability",
            "interpretation": "Interpretation",
        }
    )[R2_LADDER_DISPLAY_COLUMNS]


def format_r2_for_ladder_display(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    value_float = float(number)
    if value_float < 1 and f"{value_float:.4f}" == "1.0000":
        return "0.9999"
    return f"{value_float:.4f}"


def render_r2_ladder_table(table: pd.DataFrame, *, max_rows: int = 12) -> None:
    if table is None or table.empty:
        st.caption("No rows to display.")
        return
    view = table.head(max_rows).copy()
    if len(table) > len(view):
        st.caption(f"Showing first {len(view):,} of {len(table):,} rows.")
    header_html = "".join(
        f"<th data-r2-ladder-header='{_r2_ladder_header_key(column)}'>{_r2_ladder_header_html(column)}</th>"
        for column in R2_LADDER_DISPLAY_COLUMNS
        if column in view.columns
    )
    rows_html = []
    for _, row in view.iterrows():
        cells = []
        for column in R2_LADDER_DISPLAY_COLUMNS:
            if column not in view.columns:
                continue
            text = _short_text(row.get(column, ""), 96 if column in {"Model", "Interpretation"} else 60)
            cells.append(f"<td>{html.escape(str(text))}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        "<div class='r2-ladder-table-wrap'>"
        "<table class='summary-tooltip-table r2-ladder-table'>"
        "<thead><tr>"
        + header_html
        + "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _r2_ladder_header_html(label: str) -> str:
    tooltip = R2_LADDER_HEADER_TOOLTIPS.get(label)
    safe_label = html.escape(label)
    if not tooltip:
        return safe_label
    return safe_label + render_info_tooltip(label, tooltip, css_class="summary-tooltip")


def _r2_ladder_header_key(label: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in label.lower()).strip("-")


def render_r2_ladder_panel(loaded: LoadedRun, selected_stream: str = "All streams", *, expanded: bool = False) -> None:
    with st.expander(R2_LADDER_TITLE, expanded=expanded):
        info_panel(R2_LADDER_DISPLAY_NOTE)
        render_r2_ladder_table(r2_ladder_display_table(loaded, selected_stream), max_rows=12)


def render_diagnostics(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    diagnostic_df = loaded.data.get("diagnostic_df", pd.DataFrame())
    gov_kpi_grid(diagnostic_kpi_cards(diagnostic_df))
    if is_executive():
        render_confidence_badges()
        render_action_card("Diagnostics")
    render_diagnostics_r2_panel(loaded)
    render_r2_ladder_panel(loaded)

    qpred = common_filter(loaded.data.get("quarterly_predictions", pd.DataFrame()), controls, include_source_variant=False)
    diagnostic_qpred = central_error_window(qpred)
    supplied_acf = loaded.data.get("diagnostic_acf", pd.DataFrame())
    if not supplied_acf.empty:
        acf_source = select_diagnostic_acf_scope(supplied_acf, DEFAULT_ACF_RESIDUAL_SCOPE)
        acf_source = common_filter(acf_source, controls, include_source_variant=False)
    else:
        acf_source = build_diagnostic_acf_source_table(qpred, diagnostic_df)
    residual_scope = (
        ", ".join(sorted(acf_source["residual_source"].dropna().astype(str).unique()))
        if not acf_source.empty and "residual_source" in acf_source.columns
        else "selected residuals"
    )
    acf_subtitle = f"Residual ACF by lag using {residual_scope}."
    error_distribution = loaded.data.get("error_distribution", pd.DataFrame())
    error_distribution = (
        common_filter(error_distribution, controls, include_source_variant=False)
        if not error_distribution.empty
        else diagnostic_qpred
    )
    pass_matrix = loaded.data.get("diagnostic_pass_matrix", pd.DataFrame())
    pass_matrix = common_filter(pass_matrix, controls, include_source_variant=False) if not pass_matrix.empty else diagnostic_df
    top = st.columns([1.0, 1.0])
    with top[0]:
        chart_card(
            "1. Residual Autocorrelation by Lag",
            acf_subtitle,
            compact_figure(plot_autocorrelation_diagnostics(qpred, acf_source=acf_source), 260),
        )
    with top[1]:
        chart_card(
            "2. Residual vs Fitted",
            "Residual / forecast error (%) versus fitted value in native stream units.",
            compact_figure(plot_residual_vs_fitted(diagnostic_qpred), 260),
        )

    bottom = st.columns([1.0, 1.0])
    with bottom[0]:
        html_chart_card(
            "3. Diagnostic Pass Matrix",
            "Calibration R2 and key statistical diagnostics by stream.",
            diagnostic_pass_matrix_html(pass_matrix),
            "Green = pass, amber = watch, red = fail, grey = unavailable.",
        )
        # Glass-box drilldown: click any diagnostic for the full statistical
        # detail (statistic, p-value, F-variant, evidence chart, audit trace).
        from model_dashboard.diagnostic_drilldown import render_diagnostic_drilldown_section

        render_diagnostic_drilldown_section()
    with bottom[1]:
        chart_card(
            "4. Error Distribution by Horizon",
            "Absolute percentage error (%) by forecast horizon.",
            compact_figure(plot_error_distribution(error_distribution), 260),
        )


def diagnostics_provenance_note(loaded: LoadedRun) -> str:
    qpred_rows = len(loaded.data.get("quarterly_predictions", pd.DataFrame()))
    feature_rows = len(loaded.data.get("variant_features", pd.DataFrame()))
    return (
        "Diagnostics provenance: this run provides "
        f"{format_count(qpred_rows)} forecast residual rows and {format_count(feature_rows)} feature-count rows. "
        "Classical ADF, Durbin-Watson and Breusch-Pagan files are not supplied, so proxy panels are labelled as equivalents."
    )


def render_reproducibility_detail(stream_label: str) -> None:
    try:
        pack = cached_load_reproducibility_pack(stream_label, reproducibility_pack_signature(stream_label))
    except Exception as exc:
        warning_panel(f"{stream_label} reproducibility audit pack could not be loaded: {exc}")
        return
    if not pack.available:
        missing = ", ".join(pack.missing_files[:8])
        if len(pack.missing_files) > 8:
            missing += ", ..."
        warning_panel(
            f"{stream_label} reproducibility audit pack is not available. "
            f"Expected read-only auxiliary files under `{pack.root}`. Missing: {missing or 'required audit tables'}."
        )
        return

    summary = reproducibility_replay_summary(pack)
    delta = pd.to_numeric(pd.Series([summary.get("max_abs_pred_delta")]), errors="coerce").iloc[0]
    delta_text = f"{delta:.2e}" if pd.notna(delta) else "-"
    kpi_grid(
        [
            ("Replay status", str(summary["status"]), f"max abs prediction delta {delta_text}"),
            ("Model", str(summary["model"]), f"{stream_label} finalist"),
            ("Workbook", str(summary["workbook"]), str(summary["source_sheet"])),
            ("Audit role", "Auxiliary governance", "read-only; not used for main calculations"),
        ]
    )
    info_panel(str(summary["description"]))
    info_panel(
        "SHAP is not supplied by this audit pack and is treated as future optional evidence only. "
        "This panel uses feature importance and scenario sensitivities from the exact replay pack."
    )

    section_title("Registry")
    display_table(reproducibility_registry_view(pack), height=150, max_rows=20)

    weight_view = reproducibility_ensemble_weight_view(pack)
    if not weight_view.empty:
        section_title("Ensemble equation")
        info_panel(reproducibility_ensemble_equation(pack))
        display_table(weight_view, height=190, max_rows=12)

    section_title("Component trace")
    component_trace = reproducibility_component_trace_view(pack)
    component_cols = [
        "Score basis",
        "Origin",
        "Target period",
        "Horizon",
        "Actual",
        "Component",
        "Component prediction",
        "Weighted contribution",
        "Base log prediction",
        "Residual log prediction",
        "Final prediction",
        "Error (%)",
    ]
    component_view = component_trace[[col for col in component_cols if col in component_trace.columns]]
    display_table(component_view, height=320, max_rows=240)

    chart_cols = st.columns(2)
    with chart_cols[0]:
        section_title("Feature importance")
        st.plotly_chart(
            plot_reproducibility_feature_importance(reproducibility_feature_importance_view(pack), stream_label),
            use_container_width=True,
            key=f"{_widget_key(stream_label)}_repro_feature_importance",
        )
    with chart_cols[1]:
        section_title("Scenario sensitivities")
        info_panel("Scenario sensitivities cover GDP, diesel price, RUC price and other perturbations.")
        st.plotly_chart(
            plot_reproducibility_sensitivities(reproducibility_sensitivity_view(pack), stream_label),
            use_container_width=True,
            key=f"{_widget_key(stream_label)}_repro_scenario_sensitivities",
        )

    with st.expander("OLS coefficients by origin/window", expanded=False):
        display_table(reproducibility_coefficients_view(pack), height=420, max_rows=420)

    with st.expander("Scorecard, horizon, annual and stress trace", expanded=False):
        section_title("Scorecard summary")
        display_table(reproducibility_scorecard_view(pack), height=150, max_rows=20)
        section_title("Horizon profile")
        display_table(reproducibility_horizon_view(pack), height=280, max_rows=120)
        section_title("Annual replay")
        display_table(reproducibility_annual_view(pack), height=280, max_rows=240)
        section_title("Stress buckets")
        display_table(reproducibility_stress_view(pack), height=180, max_rows=60)

    with st.expander("Rolling training window trace", expanded=False):
        display_table(reproducibility_training_window_view(pack), height=320, max_rows=200)


def render_revenue_outlook_page(loaded: LoadedRun) -> None:
    del loaded
    repo_root = Path(__file__).resolve().parent
    timer = RevenueOutlookRenderTimer(_revenue_outlook_perf_debug_enabled())
    timer.start("pack load")
    pack_signature = revenue_outlook_signature(repo_root / CURRENT_REVENUE_OUTLOOK_DIR, repo_root)
    pack = st.session_state.get("revenue_outlook_pack")
    if not isinstance(pack, RevenueOutlookPack):
        pack = cached_load_revenue_outlook_pack(
            str(repo_root / CURRENT_REVENUE_OUTLOOK_DIR),
            str(repo_root),
            pack_signature,
            REVENUE_OUTLOOK_SCHEMA_VERSION,
        )
    timer.stop("pack load")

    if pack is None:
        section_title(REVENUE_OUTLOOK_TITLE)
        warning_panel(
            "No explicitly promoted Revenue Outlook pack is available. Use Forecast Builder on the local "
            "Governance & Reproducibility page, review the scenario roles, then promote the comparison. "
            "This page reads only the committed current_revenue_outlook runtime pack and does not scan "
            "latest run folders or publish test fixtures automatically."
        )
        info_panel(
            "Source policy: committed current runtime pack only. Source-pack tables are retained as audit lineage, "
            "not as a second Streamlit chart engine."
        )
        return

    manifest = pack.manifest if pack is not None and isinstance(pack.manifest, dict) else {}
    chart_rows = _pack_table(pack, "revenue_chart_rows")
    fan_availability = _pack_table(pack, "fan_availability")
    fan_band_rows = _pack_table(pack, "fan_band_rows")

    section_title(REVENUE_OUTLOOK_TITLE)
    period_rule = manifest.get("period_rule") if isinstance(manifest, dict) else {}
    runtime_cutoff_fy = (period_rule or {}).get("runtime_cutoff_fy") if isinstance(period_rule, dict) else None

    if chart_rows.empty:
        warning_panel("The promoted Revenue Outlook pack has no chart rows.")
        return

    timer.start("selector metadata")
    selector_options = cached_revenue_outlook_selectors(pack_signature, pack)
    timer.stop("selector metadata")
    stream_options = selector_options["stream_options"]
    default_stream_index = stream_options.index("Total NLTF revenue") if "Total NLTF revenue" in stream_options else 0
    fed_path_options = selector_options["fed_path_options"]
    default_fed_index = fed_path_options.index("Current planned path") if "Current planned path" in fed_path_options else 0
    trace_options = selector_options["trace_options"]
    fy_options = selector_options["fy_options"]
    default_fy_index = fy_options.index("FY2031") if "FY2031" in fy_options else max(len(fy_options) - 1, 0)

    with st.container(border=True):
        st.markdown("<div class='page5-panel-title'>Revenue Outlook controls</div>", unsafe_allow_html=True)
        control_cols = st.columns([0.14, 0.28, 0.18, 0.12, 0.28])
        with control_cols[0]:
            grain_label = st.radio(
                "Time grain",
                ["June-year", "Quarterly"],
                horizontal=True,
                key="revenue_outlook_time_grain",
            )
        with control_cols[1]:
            selected_stream = st.selectbox(
                "Series",
                stream_options,
                index=default_stream_index,
                key="revenue_outlook_stream",
            )
        selected_metric_type = _revenue_outlook_series_metric_type(chart_rows, selected_stream)
        with control_cols[2]:
            if selected_metric_type == "activity":
                selected_fed_path = fed_path_options[default_fed_index] if fed_path_options else ""
                st.markdown("<div class='control-label'>FED path</div>", unsafe_allow_html=True)
                st.caption("Not applicable to activity series.")
            else:
                selected_fed_path = st.selectbox(
                    "FED path",
                    fed_path_options,
                    index=default_fed_index,
                    key="revenue_outlook_fed_path",
                )
        with control_cols[3]:
            selected_fy = st.selectbox(
                "Selected FY",
                fy_options,
                index=default_fy_index,
                key="revenue_outlook_selected_fy",
            )
        with control_cols[4]:
            selected_traces = st.multiselect(
                "Traces",
                trace_options,
                default=trace_options,
                key="revenue_outlook_traces",
            )
        bridge_mode_lookup = selector_options["bridge_mode_lookup"]
        bridge_mode_options = list(bridge_mode_lookup)
        default_bridge_label = next(
            (label for label, mode in bridge_mode_lookup.items() if mode == PED_BRIDGE_DEFAULT_MODE),
            bridge_mode_options[-1] if bridge_mode_options else "Optimized migration bridge",
        )
        if should_show_local_audit_controls() and bridge_mode_options:
            selected_ped_bridge_label = st.selectbox(
                "PED bridge",
                bridge_mode_options,
                index=bridge_mode_options.index(default_bridge_label) if default_bridge_label in bridge_mode_options else 0,
                key="revenue_outlook_ped_bridge_mode",
            )
            selected_ped_bridge_mode = bridge_mode_lookup.get(selected_ped_bridge_label, PED_BRIDGE_DEFAULT_MODE)
        else:
            selected_ped_bridge_label = default_bridge_label
            selected_ped_bridge_mode = PED_BRIDGE_DEFAULT_MODE
    sensitivity_options = list(SENSITIVITY_LEVELS)
    sensitivity_labels = selector_options["sensitivity_labels"]
    with st.container(border=True):
        st.markdown("<div class='page5-panel-title'>Sensitivities</div>", unsafe_allow_html=True)
        sens_cols = st.columns([0.18, 0.18, 0.18, 0.18, 0.28])
        with sens_cols[0]:
            selected_fleet_efficiency = st.selectbox(
                "Fleet efficiency",
                sensitivity_options,
                index=sensitivity_options.index("Off"),
                format_func=lambda level: sensitivity_labels["fleet_efficiency"].get(level, str(level)),
                key="revenue_outlook_sensitivity_fleet_efficiency",
            )
        with sens_cols[1]:
            selected_pt_mode_shift = st.selectbox(
                "PT mode shift",
                sensitivity_options,
                index=sensitivity_options.index("Off"),
                format_func=lambda level: sensitivity_labels["pt_mode_shift"].get(level, str(level)),
                key="revenue_outlook_sensitivity_pt_mode_shift",
            )
        with sens_cols[2]:
            selected_demand_elasticity = st.selectbox(
                "Demand elasticity",
                sensitivity_options,
                index=sensitivity_options.index("Off"),
                format_func=lambda level: sensitivity_labels["demand_elasticity"].get(level, str(level)),
                key="revenue_outlook_sensitivity_demand_elasticity",
            )
        with sens_cols[3]:
            cost_per_km_ratio = None
            if selected_demand_elasticity != "Off":
                cost_per_km_ratio = st.number_input(
                    "Cost/km ratio",
                    min_value=0.01,
                    max_value=5.0,
                    value=1.0,
                    step=0.01,
                    key="revenue_outlook_sensitivity_cost_ratio",
                )
            else:
                st.markdown("<div class='control-label'>Cost/km ratio</div>", unsafe_allow_html=True)
                st.caption("Only used when elasticity is on.")
        with sens_cols[4]:
            custom_fleet_efficiency_pct = None
            custom_pt_shift_pct = None
            custom_ped_elasticity = None
            custom_light_elasticity = None
            custom_heavy_elasticity = None
            if selected_fleet_efficiency == "Custom":
                custom_fleet_efficiency_pct = st.number_input("Custom efficiency % p.a.", min_value=0.0, max_value=10.0, value=1.0, step=0.1)
            if selected_pt_mode_shift == "Custom":
                custom_pt_shift_pct = st.number_input("Custom PT shift % p.a.", min_value=0.0, max_value=10.0, value=0.5, step=0.1)
            if selected_demand_elasticity == "Custom":
                custom_ped_elasticity = st.number_input("Custom PED elasticity", min_value=-2.0, max_value=2.0, value=-0.1, step=0.01)
                custom_light_elasticity = st.number_input("Custom Light RUC elasticity", min_value=-2.0, max_value=2.0, value=-0.1, step=0.01)
                custom_heavy_elasticity = st.number_input("Custom Heavy RUC elasticity", min_value=-2.0, max_value=2.0, value=-0.1, step=0.01)
            if all(value != "Custom" for value in [selected_fleet_efficiency, selected_pt_mode_shift, selected_demand_elasticity]):
                st.caption("Custom inputs appear only when selected.")
        st.caption(SENSITIVITY_DEFAULT_NOTE)

    sensitivity_key = selected_sensitivity_key(
        fleet_efficiency=selected_fleet_efficiency,
        pt_mode_shift=selected_pt_mode_shift,
        demand_elasticity=selected_demand_elasticity,
        custom_fleet_efficiency_pct=custom_fleet_efficiency_pct,
        custom_pt_shift_pct=custom_pt_shift_pct,
        custom_ped_elasticity=custom_ped_elasticity,
        custom_light_elasticity=custom_light_elasticity,
        custom_heavy_elasticity=custom_heavy_elasticity,
        cost_per_km_ratio=cost_per_km_ratio,
    )
    timer.start("sensitivity overlay")
    view = cached_revenue_outlook_view(
        pack_signature,
        selected_stream,
        "june_year" if grain_label == "June-year" else "quarterly",
        selected_fed_path,
        tuple(selected_traces),
        sensitivity_key,
        selected_ped_bridge_mode,
        pack,
    )
    timer.stop("sensitivity overlay")
    chart_rows = view["chart_rows"]
    line_reconciliation = view["line_reconciliation"]
    formula_residuals = view["revenue_formula_residuals"]
    stack_components = view["revenue_stack_components"]
    bridge = view["revenue_bridge_components"]
    future_revenue = view["future_revenue_forecasts"]
    ped_revenue_bridge_audit = view["ped_revenue_bridge_audit"]
    ped_bridge_mode_impact_audit = view["ped_bridge_mode_impact_audit"]
    sensitivity_impact_audit = view["sensitivity_impact_audit"]
    filtered_rows = view["filtered_rows"]
    filtered_bridge = view["filtered_bridge"]
    gap_summary = str(view.get("gap_summary") or "")
    if gap_summary:
        warning_panel(gap_summary)

    primary_cols = st.columns([0.64, 0.36])
    with primary_cols[0]:
        timer.start("main path figure")
        main_path_figure = revenue_outlook_total_path_figure(filtered_rows, selected_series=selected_stream, selected_fy=selected_fy)
        timer.stop("main path figure")
        chart_card(
            "Total path chart",
            "Single selected series from the committed current runtime pack.",
            main_path_figure,
            caption=(
                "Actuals, current finalist base/comparison and official comparator traces are shown only where the runtime pack carries governed rows. "
                f"PED bridge mode: {selected_ped_bridge_label}."
            ),
            notes_as_tooltip=False,
        )
    with primary_cols[1]:
        timer.start("fan figure")
        _render_revenue_outlook_fan_card(
            fan_band_rows,
            fan_availability,
            selected_series=selected_stream,
            selected_fed_path=selected_fed_path,
        )
        timer.stop("fan figure")

    if revenue_outlook_lazy_table(
        "Show scenario role contract",
        "revenue_outlook_show_scenario_role_contract",
        caption="Scenario role audit is loaded only when opened.",
    ):
        timer.start("scenario role audit")
        scenario_role_contract = _pack_table(pack, "scenario_role_contract")
        with st.expander("Scenario role contract", expanded=False):
            if scenario_role_contract.empty:
                warning_panel("Scenario role contract is missing from the committed Revenue Outlook pack.")
            else:
                st.caption(
                    "PED VKT per capita comparison traces are shown only when the committed runtime carries a value-changing "
                    "behavioural path. Revenue and aggregate traces remain visible where the bridge changes totals."
                )
                contract_cols = st.columns([0.82, 0.18])
                with contract_cols[1]:
                    dataframe_download(scenario_role_contract, "Download CSV", "scenario_role_contract.csv")
                display_table(_scenario_role_contract_display_table(scenario_role_contract), height=320, max_rows=160)
        timer.stop("scenario role audit")

    if revenue_outlook_lazy_table(
        "Show runtime cutoff audit",
        "revenue_outlook_show_runtime_cutoff_audit",
        caption="Runtime cutoff audit is loaded only when opened.",
    ):
        timer.start("runtime cutoff audit")
        runtime_cutoff_audit = _pack_table(pack, "runtime_cutoff_audit")
        with st.expander("Runtime cutoff audit", expanded=False):
            info_panel(
                "Revenue Outlook charts and tables stop at the last governed common non-extrapolated horizon across current Base, current comparison and required MBU26 inputs."
            )
            if runtime_cutoff_audit.empty:
                warning_panel("Runtime cutoff audit is missing from the committed Revenue Outlook pack.")
            else:
                cutoff_cols = st.columns([0.82, 0.18])
                with cutoff_cols[1]:
                    dataframe_download(runtime_cutoff_audit, "Download CSV", "runtime_cutoff_audit.csv")
                display_table(runtime_cutoff_audit, height=220, max_rows=20)
        timer.stop("runtime cutoff audit")

    if revenue_outlook_lazy_table(
        "Show sensitivity impact audit",
        "revenue_outlook_show_sensitivity_impact_audit",
        caption="Sensitivity audit is skipped on the default fast path until opened.",
    ):
        timer.start("sensitivity audit")
        if sensitivity_impact_audit.empty:
            sensitivity_impact_audit = cached_revenue_outlook_sensitivity_audit(
                pack_signature,
                sensitivity_key,
                selected_ped_bridge_mode,
                pack,
            )
        sensitivity_seed_inputs = _pack_table(pack, "sensitivity_seed_inputs")
        with st.expander("Sensitivity impact audit", expanded=False):
            info_panel(SENSITIVITY_DEFAULT_NOTE)
            selected_summary = (
                f"Fleet efficiency: {sensitivity_option_label('fleet_efficiency', selected_fleet_efficiency)}; "
                f"PT mode shift: {sensitivity_option_label('pt_mode_shift', selected_pt_mode_shift)}; "
                f"Demand elasticity: {sensitivity_option_label('demand_elasticity', selected_demand_elasticity)}."
            )
            st.caption(
                f"{selected_summary} Current-finalist activity/revenue rows and rollups are recalculated in this view only; MBU26 official rows are unchanged."
            )
            if sensitivity_impact_audit.empty:
                warning_panel("Sensitivity impact audit is unavailable for the selected Revenue Outlook view.")
            else:
                bridge_cols = st.columns([0.74, 0.13, 0.13])
                display_adjustment = sensitivity_impact_audit[
                    pd.to_numeric(sensitivity_impact_audit.get("FY"), errors="coerce").between(2026, 2050, inclusive="both")
                ].copy()
                with bridge_cols[1]:
                    dataframe_download(display_adjustment, "Download CSV", "sensitivity_impact_audit.csv")
                with bridge_cols[2]:
                    if not sensitivity_seed_inputs.empty:
                        dataframe_download(sensitivity_seed_inputs, "Seed CSV", "sensitivity_seed_inputs.csv")
                display_table(_sensitivity_impact_display_table(display_adjustment), height=360, max_rows=300)
        timer.stop("sensitivity audit")

    if revenue_outlook_lazy_table(
        "Show PED bridge diagnostics",
        "revenue_outlook_show_ped_bridge_diagnostics",
        caption="PED bridge diagnostics are loaded only when opened.",
    ):
        timer.start("PED bridge diagnostics")
        detail_frames = cached_revenue_outlook_detail_frames(
            pack_signature,
            sensitivity_key,
            selected_ped_bridge_mode,
            pack,
        )
        ped_revenue_bridge_audit = detail_frames["ped_revenue_bridge_audit"]
        ped_bridge_mode_impact_audit = detail_frames["ped_bridge_mode_impact_audit"]
        ped_bridge_shape_fit_metrics = _pack_table(pack, "ped_bridge_shape_fit_metrics")
        with st.expander("PED bridge diagnostics", expanded=False):
            info_panel(
                "PED VKT per capita is a finalist model output. PED volume and revenue are bridge outputs: raw mode uses "
                "VKTpc x scenario population, while optimized mode applies the PED+Light EV/PHEV migration allocation first."
            )
            st.caption(
                f"Selected bridge mode: {selected_ped_bridge_label}. Default bridge mode is Raw model bridge."
            )
            if ped_revenue_bridge_audit.empty:
                warning_panel("PED bridge diagnostics are missing from the committed Revenue Outlook pack.")
            else:
                fallback_count = int(
                    ped_revenue_bridge_audit.get("population_fallback_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()
                )
                if fallback_count:
                    warning_panel(
                        f"{fallback_count} PED bridge rows use an MBU26 population proxy for at least one quarter. These rows are flagged in the audit table."
                    )
                diag_cols = st.columns([0.62, 0.13, 0.13, 0.12])
                fy_bridge = ped_revenue_bridge_audit[
                    pd.to_numeric(ped_revenue_bridge_audit.get("FY"), errors="coerce").between(2026, 2050, inclusive="both")
                ].copy()
                with diag_cols[1]:
                    dataframe_download(fy_bridge, "Audit CSV", "ped_revenue_bridge_audit.csv")
                with diag_cols[2]:
                    if not ped_bridge_shape_fit_metrics.empty:
                        dataframe_download(ped_bridge_shape_fit_metrics, "Shape CSV", "ped_bridge_shape_fit_metrics.csv")
                with diag_cols[3]:
                    if not ped_bridge_mode_impact_audit.empty:
                        dataframe_download(ped_bridge_mode_impact_audit, "Mode CSV", "ped_bridge_mode_impact_audit.csv")
                display_table(_ped_bridge_diagnostics_display_table(fy_bridge), height=360, max_rows=300)
                if not ped_bridge_shape_fit_metrics.empty:
                    st.markdown("<div class='page5-panel-title'>Shape-fit metrics</div>", unsafe_allow_html=True)
                    display_table(_ped_bridge_shape_fit_display_table(ped_bridge_shape_fit_metrics), height=260, max_rows=80)
                if not ped_bridge_mode_impact_audit.empty:
                    st.markdown("<div class='page5-panel-title'>Selected mode impact</div>", unsafe_allow_html=True)
                    display_table(_ped_bridge_mode_impact_display_table(ped_bridge_mode_impact_audit), height=260, max_rows=160)
        timer.stop("PED bridge diagnostics")

    revenue_kpis = _revenue_outlook_summary_cards(manifest, filtered_rows, future_revenue)
    kpi_grid(revenue_kpis)

    if revenue_outlook_lazy_table(
        "Show Revenue composition over time",
        "revenue_outlook_show_composition",
        caption=(
            "FY range / horizon, Section filter and Aggregate overlays controls are loaded with the chart. "
            "Positive revenue components stack above zero."
        ),
    ):
        timer.start("composition figure")
        detail_frames = cached_revenue_outlook_detail_frames(
            pack_signature,
            sensitivity_key,
            selected_ped_bridge_mode,
            pack,
        )
        stack_components = detail_frames["revenue_stack_components"]
        with st.container(border=True):
            st.markdown("<div class='page5-panel-title'>Revenue composition over time</div>", unsafe_allow_html=True)
            comp_cols = st.columns([0.20, 0.18, 0.17, 0.16, 0.15, 0.14])
            stack_source_options = selector_options["stack_source_options"]
            stack_mode_options = selector_options["stack_mode_options"]
            stack_section_options = selector_options["stack_section_options"]
            stack_fy_min, stack_fy_max = selector_options["stack_fy_bounds"]
            with comp_cols[0]:
                selected_stack_source = st.selectbox(
                    "Source path",
                    stack_source_options,
                    index=0,
                    key="revenue_stack_source_path",
                )
            with comp_cols[1]:
                selected_stack_mode = st.selectbox(
                    "Mode",
                    stack_mode_options,
                    index=0,
                    key="revenue_stack_composition_mode",
                )
            with comp_cols[2]:
                selected_stack_detail_level = st.selectbox(
                    "Detail level",
                    list(REVENUE_STACK_DETAIL_LEVELS),
                    index=0,
                    key="revenue_stack_detail_level",
                )
            with comp_cols[3]:
                selected_stack_fy_range = st.slider(
                    "FY range / horizon",
                    min_value=stack_fy_min,
                    max_value=stack_fy_max,
                    value=(max(stack_fy_min, 2025), min(stack_fy_max, 2035)) if stack_fy_min <= 2025 <= stack_fy_max else (stack_fy_min, min(stack_fy_max, stack_fy_min + 10)),
                    key="revenue_stack_fy_range",
                )
            default_stack_sections = [section for section in ["RUC", "FED", "MVR", "TUC"] if section in stack_section_options]
            with comp_cols[4]:
                selected_stack_sections = st.multiselect(
                    "Section filter",
                    stack_section_options,
                    default=default_stack_sections or stack_section_options,
                    key="revenue_stack_sections",
                )
            stack_overlay_options = selector_options["stack_overlay_options"]
            default_stack_overlays = _revenue_stack_default_overlays(selected_stack_mode, stack_overlay_options)
            with comp_cols[5]:
                selected_stack_overlays = st.multiselect(
                    "Aggregate overlays",
                    stack_overlay_options,
                    default=default_stack_overlays,
                    key=f"revenue_stack_overlays_{selected_stack_mode}_{selected_stack_detail_level}",
                )

            filtered_stack = _filter_revenue_stack_components(
                stack_components,
                source_path=selected_stack_source,
                composition_mode=selected_stack_mode,
                sections=selected_stack_sections,
                fy_range=selected_stack_fy_range,
            )
            chart_stack = filtered_stack
            if selected_stack_overlays:
                overlay_stack = _filter_revenue_stack_components(
                    stack_components,
                    source_path=selected_stack_source,
                    composition_mode=selected_stack_mode,
                    sections=stack_section_options,
                    fy_range=selected_stack_fy_range,
                )
                overlay_stack = overlay_stack[
                    overlay_stack.get("stack_role", pd.Series("", index=overlay_stack.index)).astype(str).eq("aggregate_overlay")
                    & overlay_stack.get("line_label", pd.Series("", index=overlay_stack.index)).astype(str).isin(selected_stack_overlays)
                ].copy()
                if not overlay_stack.empty:
                    chart_stack = pd.concat([filtered_stack, overlay_stack], ignore_index=True, sort=False)
            chart_card(
                "Revenue composition over time",
                "Line-item contributions from revenue_stack_components; aggregate rows are overlays only.",
                revenue_outlook_composition_figure(
                    chart_stack,
                    source_path=selected_stack_source,
                    composition_mode=selected_stack_mode,
                    detail_level=selected_stack_detail_level,
                    overlays=selected_stack_overlays,
                ),
                caption="Clean bridge mode hides internal add-back rows while preserving reconciliation to Total NLTF revenue. Positive revenue components stack above zero; deductions stack below zero. Full formula audit shows internal rows. Gross mode reconciles leaf rows to Total gross revenues. Aggregates are overlays only.",
                notes_as_tooltip=False,
            )
            stack_gap_banner = _revenue_stack_gap_banner(filtered_stack)
            if stack_gap_banner:
                warning_panel(stack_gap_banner)
            table_cols = st.columns([0.82, 0.18])
            with table_cols[1]:
                dataframe_download(filtered_stack, "Download CSV", "revenue_stack_components.csv")
            display_table(_revenue_stack_components_display_table(filtered_stack), height=360, max_rows=720)
        timer.stop("composition figure")

    if revenue_outlook_lazy_table(
        "Show EV/PHEV PED-Light migration audit",
        "revenue_outlook_show_ev_phev_drift_audit",
        caption="EV/PHEV migration audit is loaded only when opened.",
    ):
        timer.start("EV/PHEV migration audit")
        ev_phev_ped_light_drift_assumptions = _pack_table(pack, "ev_phev_ped_light_drift_assumptions")
        with st.expander("EV/PHEV PED-Light migration audit", expanded=False):
            if ev_phev_ped_light_drift_assumptions.empty:
                warning_panel("EV/PHEV migration audit is missing from the committed Revenue Outlook pack.")
            else:
                drift_manifest = (manifest.get("ev_phev_ped_light_drift_assumptions") or {}) if isinstance(manifest, dict) else {}
                mode_values = (
                    ev_phev_ped_light_drift_assumptions.get("lambda_mode", pd.Series(dtype=str))
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )
                mode_labels = {
                    "optimized": "Optimized",
                    "fixed_light_only": "Light-only",
                    "fixed_ped_only": "PED-only",
                    "mbu_ratio": "MBU ratio",
                }
                ordered_modes = [mode for mode in ["optimized", "fixed_light_only", "fixed_ped_only", "mbu_ratio"] if mode in mode_values]
                default_mode = str(drift_manifest.get("default_lambda_mode") or "optimized")
                selected_mode = st.selectbox(
                    "Migration allocation mode",
                    ordered_modes or mode_values,
                    index=(ordered_modes or mode_values).index(default_mode) if default_mode in (ordered_modes or mode_values) else 0,
                    format_func=lambda value: mode_labels.get(str(value), str(value).replace("_", " ").title()),
                    key="revenue_outlook_migration_allocation_mode",
                )
                info_panel(
                    "EV/PHEV uptake is allocated between PED/light-petrol and total Light RUC to match MBU proportions; it is not a new model."
                )
                drift_view = ev_phev_ped_light_drift_assumptions[
                    ev_phev_ped_light_drift_assumptions.get("lambda_mode", pd.Series("", index=ev_phev_ped_light_drift_assumptions.index)).astype(str).eq(str(selected_mode))
                ].copy()
                drift_cols = st.columns([0.82, 0.18])
                with drift_cols[1]:
                    dataframe_download(drift_view, "Download CSV", "ev_phev_ped_light_drift_assumptions.csv")
                display_table(_ev_phev_ped_light_drift_display_table(drift_view), height=340, max_rows=260)
        timer.stop("EV/PHEV migration audit")

    if revenue_outlook_lazy_table(
        "Show EV/PHEV split audit",
        "revenue_outlook_show_ev_phev_split_audit",
        caption="EV/PHEV split audit is loaded only when opened.",
    ):
        timer.start("EV/PHEV split audit")
        ev_phev_split_assumptions = _pack_table(pack, "ev_phev_split_assumptions")
        with st.expander("EV/PHEV split audit", expanded=False):
            if ev_phev_split_assumptions.empty:
                warning_panel("EV/PHEV split audit is missing from the committed Revenue Outlook pack.")
            else:
                target_audit = (manifest.get("target_semantics_audit") or {}).get("LIGHT_RUC", {}) if isinstance(manifest, dict) else {}
                allocation_status = ((manifest.get("ev_phev_split_assumptions") or {}).get("allocation_status") if isinstance(manifest, dict) else "") or ""
                info_panel(
                    "Legacy continuity view: MBU26 Light RUC split/rate rows and old fixed-add-on comparators are retained for governance review."
                )
                st.caption(
                    "The active current-finalist path is the PED-Light migration audit above. BEV/PHEV are not fixed add-ons."
                )
                if target_audit:
                    st.caption(f"Target semantics status: {target_audit.get('status', '')}. Allocation status: {allocation_status}.")
                audit_cols = st.columns([0.82, 0.18])
                with audit_cols[1]:
                    dataframe_download(ev_phev_split_assumptions, "Download CSV", "ev_phev_split_assumptions.csv")
                display_table(_ev_phev_split_assumptions_display_table(ev_phev_split_assumptions), height=320, max_rows=220)
        timer.stop("EV/PHEV split audit")

    if selected_metric_type == "activity":
        st.caption("Revenue component drill-down and selected-FY revenue split are not applicable to activity-volume series.")
    elif revenue_outlook_lazy_table(
        "Show Component drill-down and Selected-FY revenue split",
        "revenue_outlook_show_selected_fy_details",
        caption="Selected-FY component and split charts are built only when opened.",
    ):
        timer.start("selected-FY detail figures")
        selected_fy_number = _selected_fy_to_number(selected_fy)
        try:
            detail_cols = st.columns([0.58, 0.42])
            with detail_cols[0]:
                chart_card(
                    "Component drill-down",
                    "Selected-FY bridge components behind the current finalist revenue composition.",
                    revenue_outlook_component_figure(bridge, selected_fy=selected_fy, selected_fed_path=selected_fed_path),
                    caption="Component rows come from revenue_bridge_components in the committed runtime pack.",
                    notes_as_tooltip=False,
                )
            with detail_cols[1]:
                chart_card(
                    "Selected-FY revenue split",
                    "Net FED, total RUC and MVR share of selected-FY revenue where available.",
                    revenue_outlook_split_figure(bridge, selected_fy=selected_fy, selected_fed_path=selected_fed_path),
                    caption=f"Selected FY: {selected_fy_number or selected_fy}.",
                    notes_as_tooltip=False,
                )
        finally:
            timer.stop("selected-FY detail figures")

    if revenue_outlook_lazy_table(
        "Show revenue line reconciliation",
        "revenue_outlook_show_line_reconciliation",
        caption="Line reconciliation table is built only when opened.",
    ):
        timer.start("reconciliation table")
        detail_frames = cached_revenue_outlook_detail_frames(
            pack_signature,
            sensitivity_key,
            selected_ped_bridge_mode,
            pack,
        )
        line_reconciliation = detail_frames["line_reconciliation"]
        formula_residuals = detail_frames["revenue_formula_residuals"]
        with st.container(border=True):
            st.markdown("<div class='page5-panel-title'>Revenue line reconciliation</div>", unsafe_allow_html=True)
            rec_cols = st.columns([0.35, 0.25, 0.25, 0.15])
            source_options = selector_options["line_source_options"]
            section_options = selector_options["line_section_options"]
            fy_min, fy_max = selector_options["line_fy_bounds"]
            with rec_cols[0]:
                selected_source_paths = st.multiselect(
                    "Source path",
                    source_options,
                    default=source_options,
                    key="revenue_line_reconciliation_source_paths",
                )
            with rec_cols[1]:
                selected_sections = st.multiselect(
                    "Section",
                    section_options,
                    default=section_options,
                    key="revenue_line_reconciliation_sections",
                )
            with rec_cols[2]:
                selected_fy_range = st.slider(
                    "FY range",
                    min_value=fy_min,
                    max_value=fy_max,
                    value=(max(fy_min, 2024), min(fy_max, 2027)) if fy_min <= 2024 <= fy_max else (fy_min, min(fy_max, fy_min + 3)),
                    key="revenue_line_reconciliation_fy_range",
                )
            filtered_reconciliation = _filter_revenue_line_reconciliation(
                line_reconciliation,
                source_paths=selected_source_paths,
                sections=selected_sections,
                fy_range=selected_fy_range,
            )
            with rec_cols[3]:
                dataframe_download(filtered_reconciliation, "Download CSV", "revenue_line_reconciliation.csv")
            gap_banner = _revenue_formula_gap_banner(formula_residuals, selected_source_paths, selected_fy_range)
            if gap_banner:
                warning_panel(gap_banner)
            display_table(_revenue_line_reconciliation_display_table(filtered_reconciliation), height=360, max_rows=520)
        timer.stop("reconciliation table")

    if revenue_outlook_lazy_table(
        "Show series alias audit",
        "revenue_outlook_show_series_alias_audit",
        caption="Alias audit is loaded only when opened.",
    ):
        timer.start("series alias audit")
        alias_audit = _pack_table(pack, "series_alias_audit")
        with st.container(border=True):
            st.markdown("<div class='page5-panel-title'>Series alias audit</div>", unsafe_allow_html=True)
            alias_cols = st.columns([0.82, 0.18])
            with alias_cols[1]:
                dataframe_download(alias_audit, "Download CSV", "series_alias_audit.csv")
            display_table(_revenue_series_alias_audit_display_table(alias_audit), height=260, max_rows=120)
        timer.stop("series alias audit")

    if revenue_outlook_lazy_table(
        "Show Activity and volume outlook",
        "revenue_outlook_show_activity_volume",
        caption="Activity-volume chart is built only when opened.",
    ):
        timer.start("activity figure")
        with st.expander("Activity and volume outlook", expanded=False):
            activity_rows = _filter_revenue_outlook_rows(
                chart_rows,
                time_grain="june_year" if grain_label == "June-year" else "quarterly",
                stream_labels=["PED VKT per capita", "PED volume", "Light RUC net km", "Heavy RUC net km"],
                fed_paths=[selected_fed_path],
                trace_names=selected_traces,
            )
            chart_card(
                "Activity and volume outlook",
                "PED uses VKT per capita; Light and Heavy RUC use net kilometres. Actuals end at FY2025.",
                revenue_outlook_figure(activity_rows, metric_type="activity"),
                caption="Forecast start and H13 markers are shown where numeric reviewed forecasts exist. Units are kept separate by stream.",
                notes_as_tooltip=False,
            )
        timer.stop("activity figure")

    if revenue_outlook_lazy_table(
        "Show Revenue bridge detail",
        "revenue_outlook_show_bridge_detail",
        caption="Revenue bridge detail table is built only when opened.",
    ):
        timer.start("bridge detail table")
        st.markdown("<div class='page5-panel-title'>Revenue bridge detail</div>", unsafe_allow_html=True)
        display_table(_revenue_bridge_display_table(filtered_bridge), height=320, max_rows=240)
        timer.stop("bridge detail table")

    if revenue_outlook_lazy_table(
        "Show Manifest, Source policy and downloads",
        "revenue_outlook_show_manifest_downloads",
        caption="Manifest table and downloads are prepared only when opened.",
    ):
        timer.start("manifest downloads")
        with st.expander("Manifest, source policy and downloads", expanded=False):
            display_table(_revenue_outlook_manifest_table(manifest), height=220, max_rows=80)
            download_cols = st.columns(3)
            with download_cols[0]:
                dataframe_download(future_revenue, "Download future revenue forecasts", "future_revenue_forecasts.csv")
            with download_cols[1]:
                dataframe_download(bridge, "Download revenue bridge components", "revenue_bridge_components.csv")
            with download_cols[2]:
                dataframe_download(chart_rows, "Download revenue chart rows", "revenue_chart_rows.csv")
        timer.stop("manifest downloads")

    _render_revenue_outlook_timings(timer)


def _revenue_source_kpi_cards(source_pack: RevenueSourcePack | None) -> list[tuple[str, str, str | None]]:
    if source_pack is None or source_pack.canonical_long.empty:
        return [("Source pack", "Missing", "data/revenue_model_source_pack/2026_05_19")]
    frame = source_pack.canonical_long
    selected_fy = current_selection(source_pack, "selected_fy", "FY2031")
    cards = [
        ("Source pack", str(source_pack.manifest.get("source_pack_version", "unknown")), source_pack.validation_status),
        ("Total NLTF", _source_value_label(source_pack, "total_nltf_net_revenue", selected_fy), selected_fy),
        ("PED", _source_value_label(source_pack, "gross_ped_revenue", selected_fy), "revenue bridge"),
        ("Light RUC", _source_value_label(source_pack, "light_ruc_net_revenue", selected_fy), "direct model output bridged to revenue"),
        ("Heavy RUC", _source_value_label(source_pack, "heavy_ruc_net_revenue", selected_fy), "direct model output bridged to revenue"),
        ("Uncertainty / MAPE", _source_error_label(frame, selected_fy), "source-pack diagnostic where available"),
    ]
    return cards


def _render_revenue_source_controls(source_pack: RevenueSourcePack | None) -> dict[str, Any]:
    if source_pack is None:
        return {}
    with st.container(border=True):
        st.markdown("<div class='page5-panel-title'>NLTF revenue source controls</div>", unsafe_allow_html=True)
        row1 = st.columns([0.18, 0.26, 0.20, 0.18, 0.18])
        release_options = control_options(source_pack, "release_round", ["BEFU25"])
        series_options = control_options(source_pack, "series", ["Total NLTF revenue"])
        revenue_path_options = control_options(source_pack, "revenue_path", ["Net of admin fees & refunds", "Gross / benchmark actual"])
        scenario_options = control_options(source_pack, "scenario", ["Medium"])
        fed_path_options = control_options(source_pack, "fed_path_scenario", ["Current planned path", "No 2027 12c uplift"])
        with row1[0]:
            release_round = st.selectbox(
                "Release round",
                release_options,
                index=_option_index(release_options, current_selection(source_pack, "release_round", release_options[0])),
                key="revenue_source_release_round",
            )
        with row1[1]:
            series = st.selectbox(
                "Series",
                series_options,
                index=_option_index(series_options, "Total NLTF revenue", fallback=current_selection(source_pack, "series", series_options[0])),
                key="revenue_source_series",
            )
        with row1[2]:
            revenue_path = st.selectbox(
                "Revenue path",
                revenue_path_options,
                index=_option_index(revenue_path_options, current_selection(source_pack, "revenue_path", revenue_path_options[0])),
                key="revenue_source_revenue_path",
            )
        with row1[3]:
            scenario = st.selectbox(
                "Scenario",
                scenario_options,
                index=_option_index(scenario_options, current_selection(source_pack, "scenario", scenario_options[0])),
                key="revenue_source_scenario",
            )
        with row1[4]:
            fed_path = st.selectbox(
                "FED path",
                fed_path_options,
                index=_option_index(fed_path_options, current_selection(source_pack, "fed_path_scenario", fed_path_options[0])),
                key="revenue_source_fed_path",
            )

        row2 = st.columns([0.13, 0.16, 0.16, 0.18, 0.14, 0.12, 0.11])
        view_options = ["June-year", "Quarterly"]
        revenue_basis_options = control_options(source_pack, "revenue_basis", ["Net", "Gross", "Benchmark actual"])
        uncertainty_options = ["MOT release round"]
        fy_options = control_options(source_pack, "selected_fy", ["FY2031"])
        horizon_options = control_options(source_pack, "horizon", REVENUE_SOURCE_HORIZON_OPTIONS)
        top_up_options = control_options(source_pack, "crown_top_up", ["Exclude", "Include"])
        with row2[0]:
            time_grain = st.radio("Time grain", view_options, horizontal=True, key="revenue_source_time_grain")
        with row2[1]:
            st.markdown("<div class='page5-panel-title'>Model basis</div>", unsafe_allow_html=True)
            st.caption("Current finalist ensemble")
            model_basis = "Current finalist ensemble"
        with row2[2]:
            revenue_basis = st.selectbox(
                "Revenue basis",
                revenue_basis_options,
                index=_option_index(
                    revenue_basis_options,
                    current_selection(source_pack, "revenue_basis", revenue_basis_options[0]),
                ),
                key="revenue_source_revenue_basis",
            )
        with row2[3]:
            uncertainty = st.selectbox(
                "Uncertainty source",
                uncertainty_options,
                index=_option_index(uncertainty_options, current_selection(source_pack, "uncertainty_source", uncertainty_options[0])),
                key="revenue_source_uncertainty",
            )
        with row2[4]:
            selected_fy = st.selectbox(
                "Selected FY",
                fy_options,
                index=_option_index(fy_options, current_selection(source_pack, "selected_fy", fy_options[-1])),
                key="revenue_source_selected_fy",
            )
        with row2[5]:
            horizon = st.selectbox(
                "Horizon",
                horizon_options,
                index=_option_index(horizon_options, "To FY2031", fallback=horizon_options[0]),
                key="revenue_source_horizon",
            )
        with row2[6]:
            crown_top_up = st.selectbox(
                "Crown top-up",
                top_up_options,
                index=_option_index(top_up_options, current_selection(source_pack, "crown_top_up", top_up_options[0])),
                key="revenue_source_crown_top_up",
            )
    return {
        "release_round": release_round,
        "series": series,
        "revenue_path": revenue_path,
        "scenario": scenario,
        "fed_path": fed_path,
        "time_grain": time_grain,
        "model_basis": model_basis,
        "revenue_basis": revenue_basis,
        "uncertainty": uncertainty,
        "selected_fy": selected_fy,
        "horizon": horizon,
        "crown_top_up": crown_top_up,
    }


def _render_revenue_source_architecture(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> None:
    controls, applicability_messages = _resolve_revenue_source_control_applicability(source_pack, controls)
    if controls.get("time_grain") == "Quarterly":
        warning_panel("The distilled revenue source pack is annual only. Quarterly display remains available for the promoted Forecast Builder volume pack below.")
    for message in applicability_messages:
        info_panel(message)
    for message in _source_control_gap_messages(source_pack, controls):
        warning_panel(message)
    source_status = (
        f"Source pack version {source_pack.manifest.get('source_pack_version', 'unknown')}; "
        f"raw workbook SHA256 {source_pack.manifest.get('raw_workbook', {}).get('sha256', 'missing')[:12]}...; "
        f"validation status {source_pack.validation_status}."
    )
    info_panel(source_status)
    chart_cols = st.columns(2)
    with chart_cols[0]:
        chart_card(
            "Total path chart",
            "Source actuals, current finalist forecast and official MOT/BEFU comparators from repo-local governed sources.",
            _source_total_path_figure(source_pack, controls),
            caption="Current finalist forecast is the only in-house forecast source. Workbook model paths are offline lineage only and are not plotted.",
            notes_as_tooltip=False,
        )
    with chart_cols[1]:
        chart_card(
            "Uncertainty fan",
            "Displayed only from available governed model paths; no probabilistic residual fan is fabricated.",
            _source_uncertainty_figure(source_pack, controls),
            caption="No workbook model-spread fallback is used; unavailable uncertainty evidence is shown as a governed gap.",
            notes_as_tooltip=False,
        )

    drill_cols = st.columns(2)
    with drill_cols[0]:
        chart_card(
            "Component drill-down",
            "Positive lines and deductions for the selected FY preserve their source signs.",
            _source_component_figure(source_pack, controls),
            caption="Gross, net, deduction and overlay lines are preserved from the normalized source pack.",
            notes_as_tooltip=False,
        )
    with drill_cols[1]:
        chart_card(
            "Selected-FY revenue split",
            "Net FED, total RUC, net MVR and TUC share of selected FY revenue where available.",
            _source_split_figure(source_pack, controls),
            caption="Total RUC+PED is treated as the legacy Net FED + Net RUC subtotal, not the root total.",
            notes_as_tooltip=False,
        )

    source_tables = st.columns(2)
    with source_tables[0]:
        st.markdown("<div class='page5-panel-title'>Hierarchy reconciliation</div>", unsafe_allow_html=True)
        display_table(_source_reconciliation_view(source_pack, controls), height=280, max_rows=120)
    with source_tables[1]:
        st.markdown("<div class='page5-panel-title'>Remaining decisions handoff</div>", unsafe_allow_html=True)
        display_table(_source_remaining_decisions_handoff(source_pack), height=280, max_rows=80)

    with st.expander("Source-pack validation and manifest", expanded=False):
        component_long = _source_component_long_form_view(source_pack, controls)
        component_options = _source_component_long_form_options(component_long)
        selected_components = st.multiselect(
            "Components and deductions",
            component_options,
            default=component_options,
            key="revenue_source_component_filter",
        )
        component_long = _source_component_long_form_view(source_pack, {**controls, "component_filter": selected_components})
        st.caption("Selected component/deduction long form")
        display_table(component_long, height=220, max_rows=160)
        dataframe_download(component_long, "Download selected component/deduction long form", "revenue_component_deduction_long.csv")
        st.caption("Source-pack intake status")
        display_table(_source_intake_status(source_pack), height=180, max_rows=80)
        st.caption("Unresolved revenue decisions")
        display_table(source_pack.unresolved_decisions, height=180, max_rows=80)
        st.caption("Validation issues")
        display_table(source_pack.validation_issues, height=180, max_rows=80)
        st.caption("Required path trace status")
        display_table(_source_path_trace_status_for_controls(source_pack, controls), height=180, max_rows=80)
        st.caption("Displayed trace source contract")
        display_table(getattr(source_pack, "trace_source_contract", pd.DataFrame()), height=180, max_rows=80)
        st.caption("Annual completeness audit")
        annual_completeness = _source_annual_completeness_audit(source_pack)
        display_table(annual_completeness, height=180, max_rows=80)
        st.caption("Hybrid annual replacement-only audit")
        display_table(_source_hybrid_annual_view(source_pack, controls), height=220, max_rows=120)
        st.caption("Source gap register")
        display_table(_source_gap_register_for_controls(source_pack, controls), height=180, max_rows=80)
        st.caption("Series role audit")
        display_table(_source_series_role_audit(source_pack), height=180, max_rows=100)
        st.caption("Series trace contract")
        display_table(getattr(source_pack, "series_trace_contract", pd.DataFrame()), height=220, max_rows=120)
        st.caption("FY2025/FY2026 junction audit")
        display_table(getattr(source_pack, "series_junction_audit", pd.DataFrame()), height=220, max_rows=160)
        st.caption("Loader export manifest")
        display_table(_source_manifest_view(source_pack), height=220, max_rows=80)
        dataframe_download(source_pack.canonical_long, "Download canonical revenue long table", "canonical_revenue_long.csv")
        dataframe_download(annual_completeness, "Download annual completeness audit", "annual_completeness_audit.csv")
        dataframe_download(_source_hybrid_annual_view(source_pack, controls), "Download hybrid annual replacement audit", "hybrid_annual_revenue.csv")


def _resolve_revenue_source_control_applicability(
    source_pack: RevenueSourcePack,
    controls: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    resolved = dict(controls)
    selected_label = str(resolved.get("series") or "Total NLTF revenue").strip()
    contract = _source_trace_contract_for_selection(source_pack, selected_label)
    series_id = str(contract.get("canonical_id") or _selected_series_id(source_pack, selected_label))
    metric_type = str(contract.get("metric_type") or "").strip().lower()
    valid_bases = _source_contract_list(contract.get("valid_bases"))
    valid_controls = set(_source_contract_list(contract.get("valid_controls")))
    messages: list[str] = []

    if metric_type == "activity":
        if str(resolved.get("revenue_path") or "").strip().lower() != "not applicable":
            messages.append(
                f"Control applicability: '{selected_label}' is an activity/volume series, so revenue path, revenue basis, FED path and Crown top-up are ignored for this trace."
            )
        resolved["revenue_path"] = "Not applicable"
        resolved["revenue_basis"] = "Not applicable"
        resolved["fed_path"] = "Not applicable"
        resolved["crown_top_up"] = "Exclude"
        return resolved, messages

    selected_basis = str(resolved.get("revenue_basis") or "").strip()
    selected_basis_key = _source_revenue_basis_key(selected_basis)
    valid_basis_keys = {_source_revenue_basis_key(value) for value in valid_bases}
    valid_basis_keys.discard("")
    if valid_basis_keys and selected_basis_key not in valid_basis_keys:
        preferred = _preferred_source_basis(valid_bases)
        resolved["revenue_basis"] = preferred
        if _source_revenue_basis_key(preferred) == "gross":
            resolved["revenue_path"] = "Gross / benchmark actual"
        elif _source_revenue_basis_key(preferred) == "net":
            resolved["revenue_path"] = "Net of admin fees & refunds"
        messages.append(
            f"Control applicability: '{selected_label}' does not support revenue basis '{selected_basis or 'blank'}'; using '{preferred}' for the source-backed trace."
        )

    if "fed_path" not in valid_controls and str(resolved.get("fed_path") or "").strip() not in {"", "Not applicable"}:
        resolved["fed_path"] = "Not applicable"
        messages.append(f"Control applicability: FED path is not value-changing for '{selected_label}' and is ignored.")
    if "crown_top_up" not in valid_controls and str(resolved.get("crown_top_up") or "").strip().lower() == "include":
        resolved["crown_top_up"] = "Exclude"
        messages.append(f"Control applicability: Crown top-up is not an applicable overlay for '{selected_label}' and has been excluded.")

    if series_id == "gross_ped_revenue" and _source_revenue_basis_key(str(resolved.get("revenue_basis") or "")) == "net":
        resolved["revenue_basis"] = "Gross"
        resolved["revenue_path"] = "Gross / benchmark actual"
        messages.append("Control applicability: PED revenue is gross/nominal ex GST only; Net is not shown as a PED-only basis.")
    return resolved, messages


def _source_trace_contract_for_selection(source_pack: RevenueSourcePack, selected_label: str) -> dict[str, Any]:
    contract = getattr(source_pack, "series_trace_contract", pd.DataFrame())
    if not isinstance(contract, pd.DataFrame) or contract.empty:
        return {}
    series_id = _selected_series_id(source_pack, selected_label)
    rows = contract[
        contract.get("series_option", pd.Series("", index=contract.index)).astype(str).eq(selected_label)
        | contract.get("canonical_id", pd.Series("", index=contract.index)).astype(str).eq(series_id)
        | contract.get("display_name", pd.Series("", index=contract.index)).astype(str).eq(selected_label)
    ].copy()
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _source_contract_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").split(";")
    return [str(item).strip() for item in raw if str(item).strip()]


def _preferred_source_basis(valid_bases: list[str]) -> str:
    for candidate in ["Net", "Gross", "Nominal ex GST"]:
        if candidate in valid_bases:
            return candidate
    return valid_bases[0] if valid_bases else "Net"


def _source_control_gap_messages(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> list[str]:
    gaps = _source_gap_register_for_controls(source_pack, controls)
    if gaps.empty:
        return []
    messages: list[str] = []
    if str(controls.get("crown_top_up", "")).lower() == "include":
        crown = gaps[gaps["gap_id"].eq("crown_top_up_values_missing")]
        if not crown.empty and crown.iloc[0].get("availability_status") == "missing":
            messages.append(str(crown.iloc[0].get("user_visible_message")))
    if str(controls.get("release_round", "")).strip():
        release = gaps[gaps["gap_id"].eq("release_value_table_missing")]
        if not release.empty and release.iloc[0].get("availability_status") == "missing":
            messages.append(str(release.iloc[0].get("user_visible_message")))
    if str(controls.get("fed_path_scenario") or controls.get("fed_path") or "").strip():
        fed_path = gaps[gaps["gap_id"].eq("fed_path_scenario_values_missing")]
        if not fed_path.empty and fed_path.iloc[0].get("availability_status") == "missing":
            messages.append(str(fed_path.iloc[0].get("user_visible_message")))
    basis = gaps[gaps["gap_id"].eq("revenue_basis_selection_unavailable")]
    if not basis.empty and basis.iloc[0].get("availability_status") == "missing":
        messages.append(str(basis.iloc[0].get("user_visible_message")))
    conflict = gaps[gaps["gap_id"].eq("revenue_path_basis_conflict")]
    if not conflict.empty and conflict.iloc[0].get("availability_status") == "selection_conflict":
        messages.append(str(conflict.iloc[0].get("user_visible_message")))
    return messages


def _source_gap_register_for_controls(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    gaps = _source_gap_register(source_pack).copy()
    if gaps.empty or "gap_id" not in gaps.columns:
        return gaps
    if "release_round" in controls:
        release_mask = gaps["gap_id"].eq("release_value_table_missing")
        gaps.loc[release_mask, "current_selection"] = str(controls.get("release_round") or "")
    if "fed_path" in controls or "fed_path_scenario" in controls:
        fed_path_selection = str(controls.get("fed_path_scenario") or controls.get("fed_path") or "")
        fed_path_mask = gaps["gap_id"].eq("fed_path_scenario_values_missing")
        gaps.loc[fed_path_mask, "current_selection"] = fed_path_selection
    if "time_grain" in controls:
        quarterly_mask = gaps["gap_id"].eq("quarterly_source_pack_missing")
        gaps.loc[quarterly_mask, "current_selection"] = str(controls.get("time_grain") or "")
    if "series" in controls:
        ped_mask = gaps["gap_id"].eq("ped_total_vkt_bridge_missing")
        gaps.loc[ped_mask, "current_selection"] = str(controls.get("series") or "")
    if "crown_top_up" in controls:
        selection = str(controls.get("crown_top_up") or "").strip() or "Exclude"
        crown_mask = gaps["gap_id"].eq("crown_top_up_values_missing")
        gaps.loc[crown_mask, "current_selection"] = selection
        missing_crown = crown_mask & gaps["availability_status"].astype(str).str.lower().eq("missing")
        gaps.loc[missing_crown, "runtime_treatment"] = (
            "excluded_by_selection" if selection.lower() == "exclude" else "not_applied_missing_source"
        )
        available_crown = crown_mask & gaps["availability_status"].astype(str).str.lower().eq("available")
        gaps.loc[available_crown, "runtime_treatment"] = (
            "excluded_by_selection" if selection.lower() == "exclude" else "top_up_rows_available"
        )
    basis_gap = _source_revenue_basis_gap_row(source_pack, controls)
    if basis_gap is not None:
        gaps = pd.concat([gaps, pd.DataFrame([basis_gap])], ignore_index=True, sort=False)
    conflict_gap = _source_revenue_path_basis_conflict_row(controls)
    if conflict_gap is not None:
        gaps = pd.concat([gaps, pd.DataFrame([conflict_gap])], ignore_index=True, sort=False)
    return gaps


def _source_gap_register(source_pack: RevenueSourcePack) -> pd.DataFrame:
    gaps = getattr(source_pack, "source_gap_register", None)
    if isinstance(gaps, pd.DataFrame):
        return gaps
    manifest = getattr(source_pack, "manifest", {})
    config = getattr(source_pack, "front_end_config", {})
    frame = getattr(source_pack, "canonical_long", pd.DataFrame())
    selections = config.get("current_selections", {}) if isinstance(config, dict) else {}
    crown_top_up_selection = _selection_value(selections, "crown_top_up", "Exclude")
    has_crown_top_up_rows = bool(frame["series_id"].eq("crown_top_up").any()) if isinstance(frame, pd.DataFrame) and "series_id" in frame.columns else False
    normalized_files = manifest.get("normalized_files", {}) if isinstance(manifest, dict) else {}
    has_release_values = bool(normalized_files.get("release_values.csv")) if isinstance(normalized_files, dict) else False
    has_fed_path_values = (
        any(
            filename in normalized_files
            for filename in ["fed_path_values.csv", "fed_rate_paths.csv", "nominal_ped_fed_rate_paths.csv"]
        )
        if isinstance(normalized_files, dict)
        else False
    )
    has_quarterly_values = (
        bool(frame["time_grain"].astype(str).str.lower().eq("quarterly").any())
        if isinstance(frame, pd.DataFrame) and "time_grain" in frame.columns
        else False
    )
    has_ped_total_vkt = bool(frame["series_id"].eq("ped_total_vkt").any()) if isinstance(frame, pd.DataFrame) and "series_id" in frame.columns else False
    return pd.DataFrame(
        [
            {
                "gap_id": "release_value_table_missing",
                "required_for": "selected MOT/BEFU and rolling BEFU 1Y release paths",
                "availability_status": "available" if has_release_values else "missing",
                "current_selection": _selection_value(selections, "release_round", "BEFU25"),
                "runtime_treatment": "release_values_available" if has_release_values else "registry_only",
                "user_visible_message": (
                    "Selected MOT/BEFU release values are repo-vendored and plotted from release_values.csv."
                    if has_release_values
                    else "Full MOT/BEFU release-value table is unavailable; release selection is registry-only and unresolved differences are reported."
                ),
            },
            {
                "gap_id": "fed_path_scenario_values_missing",
                "required_for": "FED path scenario control and 2027 12c uplift treatment",
                "availability_status": "available" if has_fed_path_values else "missing",
                "current_selection": _selection_value(selections, "fed_path_scenario", "Current planned path"),
                "runtime_treatment": "fed_path_values_available" if has_fed_path_values else "registry_only",
                "user_visible_message": (
                    "FED path scenario values are repo-vendored from fed_rate_paths.csv."
                    if has_fed_path_values
                    else "FED path scenario values are not separately vendored; the FED path control is registry-only and revenue rows are preserved from source paths rather than recalculated."
                ),
            },
            {
                "gap_id": "crown_top_up_values_missing",
                "required_for": "Include Crown top-up roll-up treatment",
                "availability_status": "available" if has_crown_top_up_rows else "missing",
                "current_selection": crown_top_up_selection,
                "runtime_treatment": (
                    "excluded_by_selection"
                    if crown_top_up_selection.lower() == "exclude"
                    else "top_up_rows_available"
                    if has_crown_top_up_rows
                    else "not_applied_missing_source"
                ),
                "user_visible_message": (
                    "Crown top-up rows are repo-vendored; Include/Exclude selection can be applied by the roll-up view."
                    if has_crown_top_up_rows
                    else "Crown top-up Include is not applied because no governed top-up value rows are present in the source pack."
                ),
            },
            {
                "gap_id": "quarterly_source_pack_missing",
                "required_for": "Quarterly Revenue Outlook from source pack",
                "availability_status": "available" if has_quarterly_values else "missing",
                "current_selection": _selection_value(selections, "view", "Annual"),
                "runtime_treatment": "quarterly_available" if has_quarterly_values else "annual_only_source_pack",
                "user_visible_message": (
                    "Quarterly source rows are repo-vendored from quarterly_actuals.csv with June-year mapping."
                    if has_quarterly_values
                    else "The distilled source pack is annual only; quarterly views use promoted Forecast Builder volume packs where available."
                ),
            },
            {
                "gap_id": "ped_total_vkt_bridge_missing",
                "required_for": "PED VKT per capita to total VKT bridge replay",
                "availability_status": "available" if has_ped_total_vkt else "missing",
                "current_selection": _selection_value(selections, "series", "Total NLTF revenue"),
                "runtime_treatment": "bridge_rows_available" if has_ped_total_vkt else "reported_gap",
                "user_visible_message": "PED total VKT bridge rows are absent; PED replacement revenue is reported as a governed gap rather than falling back to workbook model paths.",
            },
        ],
        columns=[
            "gap_id",
            "required_for",
            "availability_status",
            "current_selection",
            "runtime_treatment",
            "user_visible_message",
        ],
    )


def _source_revenue_basis_gap_row(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> dict[str, Any] | None:
    selected_basis = str(controls.get("revenue_basis") or "").strip()
    if not selected_basis:
        return None
    selected_series = str(controls.get("series") or "Total NLTF revenue").strip()
    basis_key = _source_revenue_basis_key(selected_basis)
    if not basis_key:
        return None
    rows = _selected_source_series_frame(source_pack, {"series": selected_series})
    if rows.empty or "revenue_basis" not in rows.columns:
        return None
    revenue_rows = rows[rows["revenue_basis"].astype(str).str.lower().ne("activity")].copy()
    if revenue_rows.empty:
        return None
    available = bool(revenue_rows["revenue_basis"].astype(str).eq(basis_key).any())
    available_labels = sorted(
        {
            _source_revenue_basis_label(value)
            for value in revenue_rows["revenue_basis"].dropna().astype(str)
            if _source_revenue_basis_label(value)
        }
    )
    return {
        "gap_id": "revenue_basis_selection_unavailable",
        "required_for": "Revenue basis control for selected source-pack series",
        "availability_status": "available" if available else "missing",
        "current_selection": f"{selected_series}: {selected_basis}",
        "runtime_treatment": "basis_filter_available" if available else "basis_selection_not_applied_missing_source",
        "user_visible_message": (
            f"Revenue basis '{selected_basis}' is not value-backed for '{selected_series}'. "
            f"Available source-backed bases: {', '.join(available_labels) or 'none'}; "
            "dashboard keeps source-backed rows and reports this gap rather than relabelling values."
        ),
    }


def _source_revenue_path_basis_conflict_row(controls: dict[str, Any]) -> dict[str, Any] | None:
    revenue_path = str(controls.get("revenue_path") or "").strip()
    selected_basis = str(controls.get("revenue_basis") or "").strip()
    if not revenue_path or not selected_basis:
        return None
    path_basis_label = _source_revenue_path_basis_label(revenue_path)
    path_basis_key = _source_revenue_basis_key(path_basis_label)
    selected_basis_key = _source_revenue_basis_key(selected_basis)
    if not path_basis_key or not selected_basis_key or path_basis_key == selected_basis_key:
        return None
    path_basis = _source_revenue_basis_label(path_basis_key)
    basis_label = _source_revenue_basis_label(selected_basis_key)
    return {
        "gap_id": "revenue_path_basis_conflict",
        "required_for": "Consistent Revenue Outlook revenue path and revenue basis controls",
        "availability_status": "selection_conflict",
        "current_selection": f"{revenue_path}: {selected_basis}",
        "runtime_treatment": "explicit_revenue_basis_takes_precedence",
        "user_visible_message": (
            f"Revenue path '{revenue_path}' implies {path_basis}, but revenue basis is '{basis_label}'. "
            "Dashboard filters by the explicit revenue basis and reports this conflict rather than silently relabelling values."
        ),
    }


def _source_intake_status(source_pack: RevenueSourcePack) -> pd.DataFrame:
    status = getattr(source_pack, "intake_status", None)
    if isinstance(status, pd.DataFrame):
        return status
    manifest = getattr(source_pack, "manifest", {})
    root = f"data/revenue_model_source_pack/{manifest.get('source_pack_version', '2026_05_19')}"
    rows: list[dict[str, Any]] = []
    declared: set[str] = {"manifest.json"}
    rows.append(
        {
            "artifact_name": "manifest.json",
            "artifact_role": "source_pack_manifest",
            "repo_relative_path": f"{root}/manifest.json",
            "status": "repo_local_manifest_declared",
            "required_for_runtime": True,
            "required_for_replay": True,
            "size_bytes": "",
            "row_count": "",
            "sha256": "",
            "notes": "Manifest-declared source-pack artifact.",
        }
    )
    for bucket in ("normalized_files", "config_files"):
        payload = manifest.get(bucket, {}) if isinstance(manifest, dict) else {}
        if not isinstance(payload, dict):
            continue
        for filename, meta in payload.items():
            declared.add(str(filename))
            metadata = meta if isinstance(meta, dict) else {}
            rows.append(
                {
                    "artifact_name": str(filename),
                    "artifact_role": str(metadata.get("source_sheet", "config_or_document")),
                    "repo_relative_path": f"{root}/{filename}",
                    "status": "repo_local_manifest_declared",
                    "required_for_runtime": str(filename) in REQUIRED_SOURCE_PACK_FILES or str(filename) in OPTIONAL_SOURCE_PACK_FILES,
                    "required_for_replay": True,
                    "size_bytes": "",
                    "row_count": metadata.get("row_count", ""),
                    "sha256": metadata.get("sha256", ""),
                    "notes": "Manifest-declared source-pack artifact.",
                }
            )
    for filename, role in {
        "release_values.csv": "selected MOT/BEFU and rolling BEFU 1Y release-value paths",
        "forecast_archive.csv": "full workbook forecast archive replay",
        "formula_lineage.csv": "full formula lineage replay",
        "quarterly_actuals.csv": "source-pack quarterly Revenue Outlook",
        "fed_rate_paths.csv": "FED path scenario rate values",
        "mot_error_bands.csv": "MOT archived-error uncertainty bands",
    }.items():
        if filename in declared:
            continue
        rows.append(
            {
                "artifact_name": filename,
                "artifact_role": role,
                "repo_relative_path": f"{root}/{filename}",
                "status": "not_vendored",
                "required_for_runtime": False,
                "required_for_replay": True,
                "size_bytes": "",
                "row_count": "",
                "sha256": "",
                "notes": "Not present in the repo-local normalized pack; dependent dashboard traces remain governed gaps.",
            }
        )
    return pd.DataFrame(rows)


def _source_remaining_decisions_handoff(source_pack: RevenueSourcePack) -> pd.DataFrame:
    handoff = getattr(source_pack, "remaining_decisions_handoff", None)
    if isinstance(handoff, pd.DataFrame):
        return handoff
    decisions = getattr(source_pack, "unresolved_decisions", pd.DataFrame())
    if not isinstance(decisions, pd.DataFrame) or decisions.empty:
        return pd.DataFrame()
    frame = decisions.rename(
        columns={
            "Priority": "priority",
            "Item": "decision_item",
            "Why needed": "why_needed",
            "Recommended resolution": "recommended_resolution",
        }
    ).copy()
    frame["availability_status"] = "open_decision"
    frame["runtime_status"] = "manual_review_required"
    frame["dashboard_treatment"] = "Carry as explicit unresolved governance decision until source evidence is vendored."
    return frame


def _source_series_role_audit(source_pack: RevenueSourcePack) -> pd.DataFrame:
    audit = getattr(source_pack, "series_role_audit", None)
    if isinstance(audit, pd.DataFrame):
        return audit
    frame = getattr(source_pack, "canonical_long", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    columns = [
        "series_id",
        "display_name",
        "forecast_role",
        "bridge_status",
        "revenue_basis",
        "source_status",
    ]
    existing = [column for column in columns if column in frame.columns]
    return frame[existing].drop_duplicates().sort_values(existing, kind="stable").reset_index(drop=True)


def _source_path_trace_status(source_pack: RevenueSourcePack) -> pd.DataFrame:
    status = getattr(source_pack, "path_trace_status", None)
    if isinstance(status, pd.DataFrame):
        return status
    gaps = _source_gap_register(source_pack)
    release_gap = gaps[gaps["gap_id"].eq("release_value_table_missing")] if "gap_id" in gaps.columns else pd.DataFrame()
    release_available = not release_gap.empty and release_gap.iloc[0].get("availability_status") == "available"
    rows = [
        _path_trace_row("actual_benchmark", "Complete annual actuals", True, "source actual rows after completeness audit", ""),
        _path_trace_row("selected_mot_befu_release", "Official comparator: selected MOT/BEFU", release_available, "release-value table", "" if release_available else "release_value_table_missing"),
        _path_trace_row("rolling_befu_1y", "Official comparator: rolling BEFU 1Y", release_available, "release-value table", "" if release_available else "release_value_table_missing"),
        _path_trace_row("current_finalist_forecast", "Current finalist forecast", True, "promoted current finalist quarterly outputs annualized to June years with FY2025 actual anchor", ""),
    ]
    return pd.DataFrame(rows)


def _source_path_trace_status_for_controls(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    status = _source_path_trace_status(source_pack).copy()
    if status.empty:
        return status
    if "current_selection" not in status.columns:
        status["current_selection"] = ""
    if "trace_id" in status.columns and "release_round" in controls:
        release_selection = str(controls.get("release_round") or "")
        release_trace_mask = status["trace_id"].isin(["selected_mot_befu_release", "rolling_befu_1y"])
        status.loc[release_trace_mask, "current_selection"] = release_selection
    return status


def _path_trace_row(trace_id: str, trace_label: str, available: bool, data_scope: str, blocking_gap_id: str) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "trace_label": trace_label,
        "availability_status": "available" if available else "missing",
        "plotted": bool(available),
        "data_scope": data_scope,
        "blocking_gap_id": blocking_gap_id,
        "current_selection": "",
        "user_visible_message": (
            f"{trace_label} is backed by {data_scope}."
            if available
            else f"{trace_label} is unavailable because {blocking_gap_id or 'required source rows are missing'}."
        ),
    }


def _selection_value(selections: dict[str, Any], control_id: str, default: str = "") -> str:
    value = selections.get(control_id, {}).get("current_value") if isinstance(selections.get(control_id, {}), dict) else None
    return str(value) if value else default


def _option_index(options: list[str], preferred: str, *, fallback: str | None = None) -> int:
    if preferred in options:
        return options.index(preferred)
    if fallback in options:
        return options.index(str(fallback))
    return 0


def _source_value_label(source_pack: RevenueSourcePack, series_id: str, selected_fy: str) -> str:
    frame = getattr(source_pack, "hybrid_annual_revenue", pd.DataFrame())
    rows = _source_series_rows(frame, series_id)
    if rows.empty:
        return "-"
    if "period" in rows.columns:
        selected = rows[rows["period"].eq(selected_fy)]
    else:
        fy = _fy_from_label(selected_fy)
        selected = rows[pd.to_numeric(rows.get("FY"), errors="coerce").eq(fy)] if fy is not None else pd.DataFrame()
    row = selected.tail(1)
    if row.empty:
        row = rows.sort_values("FY").tail(1)
    value = row.iloc[0].get("value")
    unit = str(row.iloc[0].get("unit", ""))
    return _source_format_value(value, unit)


def _source_error_label(frame: pd.DataFrame, selected_fy: str) -> str:
    rows = frame[
        frame["source_series_label"].astype(str).str.contains("error", case=False, na=False)
        & frame["period"].eq(selected_fy)
    ].copy()
    if rows.empty:
        rows = frame[frame["source_series_label"].astype(str).str.contains("error", case=False, na=False)].sort_values("FY").tail(1)
    if rows.empty:
        return "gap"
    value = rows.iloc[0].get("value")
    try:
        return f"{float(value):+.1%}"
    except (TypeError, ValueError):
        return "gap"


def _source_total_path_figure(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> go.Figure:
    frame = _selected_source_series_frame(source_pack, controls)
    if frame.empty:
        return empty_figure("Selected revenue series is unavailable in the normalized source pack.")
    fig = go.Figure()
    actual_rows = _source_complete_actual_rows(source_pack, frame)
    forecast_start = _source_forecast_start_fy_from_audit(source_pack)
    trace_specs = [
        ("Actual", actual_rows, "#7A869A", "solid"),
        ("Official comparator: selected MOT/BEFU", _source_forecast_path_rows(source_pack, _source_selected_release_rows(frame, controls)), "#5B677A", "dashdot"),
        ("Official comparator: rolling BEFU 1Y", _source_rolling_befu_1y_rows(frame), "#6B7F2A", "dot"),
        ("Current finalist forecast", _source_current_forecast_path_rows(source_pack, frame, controls), "#00843D", "solid"),
    ]
    axis_title = _source_axis_title(frame)
    for name, rows, color, dash in trace_specs:
        rows = _filter_source_horizon_rows(rows, source_pack, controls)
        rows = _dedupe_path_rows(rows)
        if rows.empty:
            continue
        rows = rows.copy()
        rows = _source_chart_hover_rows(source_pack, rows, axis_title=axis_title)
        fig.add_trace(
            go.Scatter(
                x=rows["FY"],
                y=rows["value"],
                mode="lines+markers",
                name=name,
                line={"color": color, "dash": dash, "width": 2.6},
                marker={"size": 6},
                customdata=rows[
                    [
                        "hover_unit",
                        "period_status",
                        "quarters_present_hover",
                        "source_status_hover",
                        "release_hover",
                        "source_cells_hover",
                        "nowcast_flag_hover",
                    ]
                ].to_numpy(),
                hovertemplate=(
                    "FY%{x}<br>%{y:,.1f} %{customdata[0]}"
                    "<br>Status: %{customdata[1]}"
                    "<br>Quarters: %{customdata[2]}"
                    "<br>Source status: %{customdata[3]}"
                    "<br>Release/path: %{customdata[4]}"
                    "<br>Source cells: %{customdata[5]}"
                    "<br>Nowcast: %{customdata[6]}"
                    "<extra>" + name + "</extra>"
                ),
            )
        )
    _add_missing_source_path_gap_traces(fig, source_pack, controls)
    fy = _selected_fy_number(controls)
    bounds = _source_horizon_bounds(source_pack, controls)
    if forecast_start is not None and _fy_within_bounds(forecast_start, bounds):
        fig.add_vline(
            x=forecast_start,
            line_dash="dash",
            line_color="#B45309",
            annotation_text=f"Forecast start FY{forecast_start}",
            annotation_position="bottom right",
        )
    if fy is not None and _fy_within_bounds(fy, bounds):
        fig.add_vline(x=fy, line_dash="dot", line_color="#102A43", annotation_text=f"Selected FY{fy}", annotation_position="top")
    release_gap = _source_gap_register_for_controls(source_pack, controls)
    release_gap = release_gap[release_gap["gap_id"].eq("release_value_table_missing")] if "gap_id" in release_gap.columns else pd.DataFrame()
    release_available = not release_gap.empty and release_gap.iloc[0].get("availability_status") == "available"
    annotation_text = (
        "Selected MOT/BEFU and rolling BEFU 1Y traces are plotted from repo-vendored release_values.csv where matching source rows exist."
        if release_available
        else "Full MOT/BEFU release-value table is not present in the distilled pack; registry-only release selection is shown as a governance gap."
    )
    fig.add_annotation(
        text=annotation_text,
        xref="paper",
        yref="paper",
        x=0,
        y=1.12,
        showarrow=False,
        align="left",
        font={"size": 11, "color": "#52616B"},
    )
    fig.update_layout(
        margin={"l": 52, "r": 18, "t": 42, "b": 48},
        height=360,
        legend={"orientation": "h", "y": -0.18},
        yaxis_title=axis_title,
        xaxis_title="June year",
        xaxis={"tickmode": "linear", "dtick": 1},
        hovermode="x unified",
    )
    return fig


def _source_annual_completeness_audit(source_pack: RevenueSourcePack) -> pd.DataFrame:
    audit = getattr(source_pack, "annual_completeness_audit", None)
    return audit.copy() if isinstance(audit, pd.DataFrame) else pd.DataFrame()


def _source_actual_base_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "line" not in frame.columns:
        return pd.DataFrame()
    rows = frame[frame["line"].astype(str).isin(["Actual", "Actual / benchmark"])].copy()
    allowed_sources = {"annual_actuals.csv", "quarterly_actuals.csv"}
    preferred = rows[rows.get("source_file", pd.Series("", index=rows.index)).astype(str).isin(allowed_sources)]
    return preferred


def _source_complete_actual_rows(source_pack: RevenueSourcePack, frame: pd.DataFrame) -> pd.DataFrame:
    rows = _source_actual_base_rows(frame)
    audit = _source_annual_completeness_audit(source_pack)
    if rows.empty or audit.empty or "chart_treatment" not in audit.columns:
        return rows
    complete_fys = set(pd.to_numeric(audit.loc[audit["chart_treatment"].eq("complete_actual_line"), "FY"], errors="coerce").dropna().astype(int))
    return rows[pd.to_numeric(rows["FY"], errors="coerce").isin(complete_fys)].copy()


def _source_partial_actual_rows(source_pack: RevenueSourcePack, frame: pd.DataFrame) -> pd.DataFrame:
    rows = _source_actual_base_rows(frame)
    audit = _source_annual_completeness_audit(source_pack)
    if rows.empty or audit.empty or "chart_treatment" not in audit.columns:
        return pd.DataFrame()
    partial_fys = set(
        pd.to_numeric(audit.loc[audit["chart_treatment"].eq("partial_actual_marker_not_connected"), "FY"], errors="coerce")
        .dropna()
        .astype(int)
    )
    return rows[pd.to_numeric(rows["FY"], errors="coerce").isin(partial_fys)].copy()


def _source_forecast_start_fy_from_audit(source_pack: RevenueSourcePack) -> int | None:
    audit = _source_annual_completeness_audit(source_pack)
    if not audit.empty and {"FY", "chart_treatment"}.issubset(audit.columns):
        audit = audit.copy()
        audit["FY"] = pd.to_numeric(audit["FY"], errors="coerce")
        audit = audit.dropna(subset=["FY"])
        complete = audit[audit["chart_treatment"].astype(str).eq("complete_actual_line")]
        last_complete = int(complete["FY"].max()) if not complete.empty else None
        partial = audit[audit["chart_treatment"].astype(str).eq("partial_actual_marker_not_connected")]
        if last_complete is not None:
            partial_after_complete = partial[partial["FY"].gt(last_complete)]
            if not partial_after_complete.empty:
                return int(partial_after_complete["FY"].min())
            forecast_after_complete = audit[
                audit["chart_treatment"].astype(str).eq("forecast_path_only")
                & audit["FY"].gt(last_complete)
            ]
            if not forecast_after_complete.empty:
                return int(forecast_after_complete["FY"].min())
        if not partial.empty:
            return int(partial["FY"].min())
    return _source_forecast_start_fy(source_pack)


def _source_forecast_path_rows(source_pack: RevenueSourcePack, rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "FY" not in rows.columns:
        return rows
    forecast_start = _source_forecast_start_fy_from_audit(source_pack)
    if forecast_start is None:
        return rows
    return rows[pd.to_numeric(rows["FY"], errors="coerce").ge(forecast_start)].copy()


def _source_chart_hover_rows(source_pack: RevenueSourcePack, rows: pd.DataFrame, *, axis_title: str) -> pd.DataFrame:
    out = rows.copy()
    out["hover_unit"] = axis_title
    audit = _source_annual_completeness_audit(source_pack)
    if not audit.empty and "FY" in audit.columns:
        audit_cols = [
            "FY",
            "completeness_status",
            "quarters_present",
            "actual_quarters",
            "forecast_quarters",
            "source_status",
            "source_cells",
            "source_cutoff",
            "nowcast_flag",
        ]
        existing = [column for column in audit_cols if column in audit.columns]
        audit_view = audit[existing].rename(
            columns={
                "source_status": "audit_source_status",
                "source_cells": "audit_source_cells",
                "nowcast_flag": "audit_nowcast_flag",
            }
        )
        out = out.merge(audit_view, on="FY", how="left")
        for column in ["quarters_present", "actual_quarters", "forecast_quarters"]:
            if column not in out.columns:
                preferred = f"{column}_x"
                audit_column = f"{column}_y"
                if preferred in out.columns:
                    out[column] = out[preferred]
                elif audit_column in out.columns:
                    out[column] = out[audit_column]
    for column in [
        "completeness_status",
        "quarters_present",
        "actual_quarters",
        "forecast_quarters",
        "audit_source_status",
        "audit_source_cells",
        "source_cutoff",
        "audit_nowcast_flag",
    ]:
        if column not in out.columns:
            out[column] = ""
    row_source_status = out.get("source_status", pd.Series("", index=out.index)).fillna("").astype(str)
    row_value_status = out.get("value_status", pd.Series("", index=out.index)).fillna("").astype(str)
    row_line = out.get("line", pd.Series("", index=out.index)).fillna("").astype(str)
    row_nowcast_flag = out.get("nowcast_flag", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["period_status"] = out["completeness_status"].fillna("").astype(str)
    out.loc[out["period_status"].eq(""), "period_status"] = row_value_status.where(row_value_status.ne(""), row_line)
    current_status_mask = row_value_status.isin(["Actual anchor", "Current-finalist FY nowcast (2 actual + 2 forecast)", "current_finalist_forecast"])
    out.loc[current_status_mask, "period_status"] = row_value_status[current_status_mask]
    out["quarters_present_hover"] = out["actual_quarters"].fillna("").astype(str)
    out.loc[out["quarters_present_hover"].eq(""), "quarters_present_hover"] = out["quarters_present"].fillna("").astype(str)
    out.loc[out["quarters_present_hover"].eq(""), "quarters_present_hover"] = out["forecast_quarters"].fillna("").astype(str)
    nowcast_status_mask = row_value_status.eq("Current-finalist FY nowcast (2 actual + 2 forecast)")
    nowcast_actuals = out["actual_quarters"].fillna("").astype(str)
    nowcast_forecasts = out["forecast_quarters"].fillna("").astype(str)
    out.loc[nowcast_status_mask, "quarters_present_hover"] = (
        "actual: "
        + nowcast_actuals.where(nowcast_actuals.ne(""), "none")
        + "; forecast: "
        + nowcast_forecasts.where(nowcast_forecasts.ne(""), "none")
    )[nowcast_status_mask]
    out.loc[out["quarters_present_hover"].eq(""), "quarters_present_hover"] = "n/a"
    out["source_status_hover"] = out["audit_source_status"].fillna("").astype(str)
    out.loc[out["source_status_hover"].eq(""), "source_status_hover"] = row_source_status.where(row_source_status.ne(""), row_value_status)
    out.loc[current_status_mask & row_source_status.ne(""), "source_status_hover"] = row_source_status[current_status_mask & row_source_status.ne("")]
    out.loc[out["source_status_hover"].eq(""), "source_status_hover"] = "n/a"
    out["release_hover"] = out.get("release_vintage", pd.Series("", index=out.index)).fillna("").astype(str)
    out.loc[out["release_hover"].eq(""), "release_hover"] = out.get("scenario_name", pd.Series("", index=out.index)).fillna("").astype(str)
    out.loc[out["release_hover"].eq(""), "release_hover"] = out.get("forecast_path", pd.Series("", index=out.index)).fillna("").astype(str)
    out.loc[out["release_hover"].eq(""), "release_hover"] = "n/a"
    row_source_cells = out.get("source_cell", pd.Series("", index=out.index)).fillna("").astype(str)
    actual_period = row_line.isin(["Actual", "Actual / benchmark"])
    out["source_cells_hover"] = row_source_cells
    out.loc[actual_period & out["audit_source_cells"].fillna("").astype(str).ne(""), "source_cells_hover"] = out.loc[
        actual_period & out["audit_source_cells"].fillna("").astype(str).ne(""), "audit_source_cells"
    ].astype(str)
    out.loc[out["source_cells_hover"].eq(""), "source_cells_hover"] = "n/a"
    out["nowcast_flag_hover"] = out["audit_nowcast_flag"].fillna(False).astype(str)
    out.loc[current_status_mask, "nowcast_flag_hover"] = row_nowcast_flag[current_status_mask].astype(str)
    return out


def _add_missing_source_path_gap_traces(fig: go.Figure, source_pack: RevenueSourcePack, controls: dict[str, Any]) -> None:
    status = _source_path_trace_status_for_controls(source_pack, controls)
    if status.empty or "trace_id" not in status.columns:
        return
    gap_styles = {
        "selected_mot_befu_release": ("Official comparator: selected MOT/BEFU", "#5B677A", "dashdot"),
        "rolling_befu_1y": ("Official comparator: rolling BEFU 1Y", "#6B7F2A", "dot"),
    }
    for trace_id, (label, color, dash) in gap_styles.items():
        rows = status[status["trace_id"].eq(trace_id)]
        if rows.empty or rows.iloc[0].get("availability_status") != "missing":
            continue
        selection = str(rows.iloc[0].get("current_selection") or "").strip()
        suffix = f" ({selection} gap)" if selection else " (gap)"
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="lines",
                name=f"{label}{suffix}",
                line={"color": color, "dash": dash, "width": 2.2},
                hoverinfo="skip",
                showlegend=True,
                meta={"governance_gap": str(rows.iloc[0].get("blocking_gap_id") or "")},
            )
        )


def _source_uncertainty_figure(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> go.Figure:
    frame = _filter_source_horizon_rows(_selected_source_series_frame(source_pack, controls), source_pack, controls)
    uncertainty_source = _uncertainty_source_key(controls)
    if uncertainty_source == "mot_release_round":
        release_gap = _source_gap_register_for_controls(source_pack, controls)
        release_gap = release_gap[release_gap["gap_id"].eq("release_value_table_missing")] if "gap_id" in release_gap.columns else pd.DataFrame()
        if release_gap.empty or release_gap.iloc[0].get("availability_status") == "missing":
            return empty_figure(
                "MOT release-round uncertainty requires release-value rows; the distilled source pack carries this as release_value_table_missing."
            )
        mot = _source_mot_uncertainty_rows(source_pack, frame, controls)
        if mot.empty:
            return empty_figure(
                "MOT release-round uncertainty is a governed gap for this selected series: archived horizon-specific error bands are unavailable or below the sample threshold."
            )
        axis_title = _source_axis_title(frame)
        fig = go.Figure()
        for upper, lower, name, color in [
            ("upper80", "lower80", "MOT archived error 80% band", "rgba(0, 43, 92, 0.14)"),
            ("upper50", "lower50", "MOT archived error 50% band", "rgba(0, 132, 61, 0.18)"),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=mot["FY"],
                    y=mot[upper],
                    mode="lines",
                    line={"width": 0},
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=mot["FY"],
                    y=mot[lower],
                    mode="lines",
                    fill="tonexty",
                    fillcolor=color,
                    line={"width": 0},
                    name=name,
                    customdata=mot[["hover_unit", "horizon_label", "sample_size"]].to_numpy(),
                    hovertemplate=(
                        "FY%{x}<br>%{y:,.1f} %{customdata[0]}<br>"
                        "%{customdata[1]}<br>n=%{customdata[2]}<extra>%{fullData.name}</extra>"
                    ),
                )
            )
        fig.add_trace(
            go.Scatter(
                x=mot["FY"],
                y=mot["value"],
                mode="lines+markers",
                name="Official comparator: selected MOT/BEFU",
                line={"color": "#002B5C", "width": 2.8},
                marker={"size": 6},
                customdata=mot[["hover_unit", "horizon_label", "sample_size"]].to_numpy(),
                hovertemplate=(
                    "FY%{x}<br>%{y:,.1f} %{customdata[0]}<br>"
                    "%{customdata[1]}<br>n=%{customdata[2]}<extra>%{fullData.name}</extra>"
                ),
            )
        )
        fig.update_layout(
            margin={"l": 52, "r": 18, "t": 28, "b": 48},
            height=360,
            yaxis_title=axis_title,
            xaxis_title="June year",
            xaxis={"tickmode": "linear", "dtick": 1},
            hovermode="x unified",
        )
        return fig
    return empty_figure("Only MOT release-round uncertainty is available on Revenue Outlook; workbook model-spread fallback has been removed.")


def _source_component_figure(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> go.Figure:
    rows = _source_hybrid_rows_for_controls(source_pack, controls)
    if rows.empty:
        rows = _source_selected_fy_rows(source_pack, controls)
    if rows.empty:
        return empty_figure("Selected FY component rows are unavailable.")
    component_ids = [
        "net_fed_revenue",
        "gross_ped_revenue",
        "total_ruc_net_revenue",
        "light_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "net_mvr_revenue",
        "tuc_net_revenue",
        "fed_refunds",
        "ruc_refunds",
        "mvr_refunds",
        "crown_top_up",
    ]
    plot = rows[rows["series_id"].isin(component_ids)].copy()
    if plot.empty:
        return empty_figure("No selected FY component rows match the governed series registry.")
    if "aggregation_sign" not in plot.columns:
        plot["aggregation_sign"] = plot["series_id"].map(_hybrid_component_sign).fillna(1)
    plot["signed_value"] = pd.to_numeric(plot["value"], errors="coerce") * pd.to_numeric(plot["aggregation_sign"], errors="coerce").fillna(1)
    plot = plot.dropna(subset=["signed_value"])
    plot = plot.drop_duplicates("series_id", keep="last")
    axis_title = _source_axis_title(plot)
    plot["hover_unit"] = axis_title
    fig = go.Figure(
        go.Bar(
            x=plot["display_name"],
            y=plot["signed_value"],
            marker_color=["#B7791F" if value < 0 else "#00843D" for value in plot["signed_value"]],
            customdata=plot[["hover_unit"]].to_numpy(),
            hovertemplate="%{x}<br>%{y:,.1f} %{customdata[0]}<extra></extra>",
        )
    )
    fig.update_layout(
        margin={"l": 52, "r": 18, "t": 28, "b": 96},
        height=360,
        yaxis_title=axis_title,
        xaxis_tickangle=-30,
    )
    return fig


def _source_split_figure(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> go.Figure:
    rows = _source_hybrid_rows_for_controls(source_pack, controls)
    if rows.empty:
        rows = _source_selected_fy_rows(source_pack, controls)
    component_ids = ["net_fed_revenue", "total_ruc_net_revenue", "net_mvr_revenue", "tuc_net_revenue"]
    plot = rows[rows["series_id"].isin(component_ids)].copy()
    plot["value"] = pd.to_numeric(plot["value"], errors="coerce")
    plot = plot.dropna(subset=["value"]).drop_duplicates("series_id", keep="last")
    if plot.empty:
        return empty_figure("Selected FY split is unavailable for this model basis.")
    axis_title = _source_axis_title(plot)
    fig = go.Figure(
        go.Pie(
            labels=plot["display_name"],
            values=plot["value"].clip(lower=0),
            hole=0.45,
            marker={"colors": ["#002B5C", "#00843D", "#008C7E", "#F37021"][: len(plot)]},
            customdata=[[axis_title] for _ in range(len(plot))],
            hovertemplate="%{label}<br>%{value:,.1f} %{customdata[0]}<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(margin={"l": 16, "r": 16, "t": 28, "b": 16}, height=360, showlegend=True)
    return fig


def _source_reconciliation_view(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    report = source_pack.reconciliation_report.copy()
    fy = _selected_fy_number(controls)
    if fy is not None and "FY" in report.columns:
        report = report[report["FY"].eq(fy)]
    if report.empty:
        return pd.DataFrame([{"status": "gap", "message": "No reconciliation rows are available for the selected FY."}])
    cols = [
        "scope",
        "FY",
        "output_series_id",
        "component_status",
        "calculated_value",
        "official_value",
        "difference",
        "missing_inputs",
        "optional_inputs_applied",
    ]
    return report[[col for col in cols if col in report.columns]].reset_index(drop=True)


def _source_hybrid_annual_view(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    out = _source_hybrid_rows_for_controls(source_pack, controls, include_bridge_inputs=True)
    if out.empty:
        return pd.DataFrame([{"status": "gap", "message": "Hybrid annual replacement audit is unavailable."}])
    cols = [
        "FY",
        "fed_path",
        "series_id",
        "display_name",
        "row_role",
        "value",
        "official_value",
        "residual_vs_official",
        "source_basis",
        "source_file",
        "formula",
        "replacement_only",
        "availability_status",
    ]
    return out[[col for col in cols if col in out.columns]].reset_index(drop=True)


def _source_component_long_form_options(frame: pd.DataFrame) -> list[str]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "display_name" not in frame.columns:
        return []
    return sorted(str(value) for value in frame["display_name"].dropna().unique() if str(value).strip())


def _source_component_long_form_view(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    rows = _source_hybrid_rows_for_controls(source_pack, controls, include_bridge_inputs=True)
    if rows.empty:
        return pd.DataFrame([{"status": "gap", "message": "Component/deduction long form is unavailable."}])
    out = rows.copy()
    component_filter = [str(value) for value in controls.get("component_filter", []) or [] if str(value).strip()]
    if component_filter:
        component_ids = set(component_filter)
        component_ids.update(_selected_series_id(source_pack, value) for value in component_filter)
        out = out[
            out["display_name"].astype(str).isin(component_filter)
            | out["series_id"].astype(str).isin(component_ids)
        ].copy()
    if out.empty:
        return pd.DataFrame([{"status": "gap", "message": "No selected components or deductions match the current controls."}])
    out["sign"] = out["series_id"].map(_hybrid_component_sign).fillna(1).astype(int)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out["signed_value"] = out["value"] * out["sign"]
    out["replacement_flag"] = out["replacement_only"].astype(bool) if "replacement_only" in out.columns else False
    out["component_class"] = out["row_role"].map(_component_class_label).fillna("Component")
    out["release_path_provenance"] = out.apply(_component_provenance_label, axis=1)
    cols = [
        "FY",
        "fed_path",
        "series_id",
        "display_name",
        "component_class",
        "row_role",
        "value",
        "sign",
        "signed_value",
        "unit",
        "release_path_provenance",
        "source_basis",
        "source_file",
        "source_status",
        "formula",
        "replacement_flag",
        "availability_status",
        "official_value",
        "residual_vs_official",
    ]
    return out[[col for col in cols if col in out.columns]].sort_values(
        ["FY", "component_class", "display_name"],
        kind="stable",
    ).reset_index(drop=True)


def _source_manifest_view(source_pack: RevenueSourcePack) -> pd.DataFrame:
    manifest = source_pack.manifest
    rows = [
        {"field": "schema_version", "value": manifest.get("schema_version", "")},
        {"field": "source_pack_version", "value": manifest.get("source_pack_version", "")},
        {"field": "raw_workbook_basename", "value": manifest.get("raw_workbook", {}).get("basename", "")},
        {"field": "raw_workbook_sha256", "value": manifest.get("raw_workbook", {}).get("sha256", "")},
        {"field": "distilled_workbook_sha256", "value": manifest.get("distilled_workbook", {}).get("sha256", "")},
        {"field": "source_policy", "value": manifest.get("source_policy", "")},
        {"field": "canonical_rows", "value": str(len(source_pack.canonical_long))},
    ]
    return pd.DataFrame(rows)


def _selected_source_series_frame(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    selected = str(controls.get("series", "Total NLTF revenue"))
    frame = source_pack.canonical_long.copy()
    rows = frame[
        frame["display_name"].eq(selected)
        | frame["source_series_label"].eq(selected)
        | frame["series_id"].eq(_selected_series_id(source_pack, selected))
    ].copy()
    if rows.empty and selected == "Total RUC+PED revenue":
        rows = frame[frame["series_id"].eq("total_fed_ruc_net_revenue")].copy()
    rows = rows[pd.to_numeric(rows["value"], errors="coerce").notna()].copy()
    return _filter_source_rows_by_revenue_basis(rows, controls)


def _filter_source_rows_by_revenue_basis(rows: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    if rows.empty or "revenue_basis" not in rows.columns:
        return rows
    selected_basis = controls.get("revenue_basis") or _source_revenue_path_basis_label(controls.get("revenue_path"))
    basis_key = _source_revenue_basis_key(selected_basis)
    if not basis_key:
        return rows
    basis = rows["revenue_basis"].astype(str)
    revenue_mask = basis.str.lower().ne("activity")
    if not revenue_mask.any():
        return rows
    filtered = rows[revenue_mask & basis.eq(basis_key)].copy()
    return filtered if not filtered.empty else rows


def _source_series_rows(frame: pd.DataFrame, series_id: str) -> pd.DataFrame:
    return frame[frame["series_id"].eq(series_id) & pd.to_numeric(frame["value"], errors="coerce").notna()].copy()


def _source_selected_fy_rows(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    fy = _selected_fy_number(controls)
    frame = source_pack.canonical_long.copy()
    if fy is None:
        return pd.DataFrame()
    frame = frame[frame["FY"].eq(fy)].copy()
    preferred = frame[frame["source_file"].isin(["annual_actuals.csv", "quarterly_actuals.csv", "official_befu25_annual.csv", "release_values.csv"])]
    return preferred.copy()


def _source_hybrid_path_rows(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    hybrid = _source_hybrid_rows_for_controls(source_pack, controls, selected_fy_only=False, apply_horizon=True)
    if hybrid.empty:
        return pd.DataFrame()
    selected = str(controls.get("series", "Total NLTF revenue"))
    series_id = _selected_series_id(source_pack, selected)
    rows = hybrid[hybrid["series_id"].astype(str).eq(series_id)].copy()
    if rows.empty:
        return pd.DataFrame()
    rows["source_file"] = "hybrid_annual_revenue.csv"
    rows["source_cell"] = rows["FY"].astype(str)
    rows["line"] = "Model path"
    rows["model_basis"] = "hybrid_replacement_only"
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    return rows.rename(columns={"display_name": "source_series_label"})


def _source_current_forecast_path_rows(source_pack: RevenueSourcePack, frame: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    current = getattr(source_pack, "current_forecast_annual", pd.DataFrame())
    if not isinstance(current, pd.DataFrame) or current.empty or frame.empty:
        return pd.DataFrame()
    series_ids = set(frame.get("series_id", pd.Series(dtype=str)).dropna().astype(str))
    if not series_ids:
        return pd.DataFrame()
    rows = current[current.get("series_id", pd.Series(dtype=str)).astype(str).isin(series_ids)].copy()
    if rows.empty:
        return pd.DataFrame()
    if "scenario_name" in rows.columns:
        rows = rows[rows["scenario_name"].astype(str).eq("current_basecase")].copy()
    selected_path = _selected_fed_path(controls)
    if "fed_path" in rows.columns and selected_path:
        path_rows = rows[rows["fed_path"].astype(str).eq(selected_path)].copy()
        if not path_rows.empty:
            rows = path_rows
    rows["value"] = pd.to_numeric(rows.get("value"), errors="coerce")
    rows = rows[rows["value"].notna()].copy()
    if rows.empty:
        return pd.DataFrame()
    defaults = {
        "source_file": "data/current_revenue_outlook/revenue_chart_rows.csv",
        "line": "Model path",
        "model_basis": "current_finalist_model",
        "forecast_path": "current_finalist_model",
        "path_status": "current_model_forecast",
        "source_status": "source_backed",
    }
    for column, value in defaults.items():
        if column not in rows.columns:
            rows[column] = value
    return rows.rename(columns={"display_name": "source_series_label"})


def _source_hybrid_rows_for_controls(
    source_pack: RevenueSourcePack,
    controls: dict[str, Any],
    *,
    include_bridge_inputs: bool = False,
    selected_fy_only: bool = True,
    apply_horizon: bool = False,
) -> pd.DataFrame:
    frame = getattr(source_pack, "hybrid_annual_revenue", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    selected_path = _selected_fed_path(controls)
    if selected_path and "fed_path" in out.columns:
        path_rows = out[out["fed_path"].astype(str).eq(selected_path)].copy()
        if path_rows.empty and selected_path != "Selected rate":
            path_rows = out[out["fed_path"].astype(str).eq("Selected rate")].copy()
        if not path_rows.empty:
            out = path_rows
    fy = _selected_fy_number(controls)
    if selected_fy_only and fy is not None and "FY" in out.columns:
        selected = out[out["FY"].eq(fy)].copy()
        if not selected.empty:
            out = selected
    if apply_horizon:
        out = _filter_source_horizon_rows(out, source_pack, controls)
    if not include_bridge_inputs and "row_role" in out.columns:
        out = out[~out["row_role"].astype(str).eq("bridge_input")].copy()
    return _apply_crown_top_up_selection(out, controls)


def _selected_fed_path(controls: dict[str, Any]) -> str:
    return str(controls.get("fed_path_scenario") or controls.get("fed_path") or "Current planned path").strip()


def _apply_crown_top_up_selection(rows: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    if rows.empty or "series_id" not in rows.columns:
        return rows
    out = rows.copy()
    include = str(controls.get("crown_top_up") or "Exclude").strip().lower() == "include"
    crown_mask = out["series_id"].astype(str).eq("crown_top_up")
    if crown_mask.any() and not include:
        out.loc[crown_mask, "value"] = 0.0
        out.loc[crown_mask, "availability_status"] = "excluded_by_selection"
    if include and crown_mask.any():
        for fy, crown_rows in out[crown_mask].groupby("FY", dropna=True):
            top_up = pd.to_numeric(crown_rows["value"], errors="coerce").fillna(0.0).sum()
            total_mask = out["series_id"].astype(str).eq("total_nltf_net_revenue") & out["FY"].eq(fy)
            if not total_mask.any() or top_up == 0:
                continue
            out.loc[total_mask, "value"] = pd.to_numeric(out.loc[total_mask, "value"], errors="coerce") + top_up
            if "formula" in out.columns:
                out.loc[total_mask, "formula"] = out.loc[total_mask, "formula"].astype(str) + " + selected Crown top-up"
            if {"official_value", "residual_vs_official"}.issubset(out.columns):
                official = pd.to_numeric(out.loc[total_mask, "official_value"], errors="coerce")
                value = pd.to_numeric(out.loc[total_mask, "value"], errors="coerce")
                out.loc[total_mask, "residual_vs_official"] = value.to_numpy() - official.to_numpy()
    return out


def _hybrid_component_sign(series_id: Any) -> int:
    return -1 if str(series_id) in {"fed_refunds", "ruc_refunds", "mvr_refunds"} else 1


def _component_class_label(row_role: Any) -> str:
    role = str(row_role or "")
    labels = {
        "bridge_input": "Bridge input",
        "replacement_line": "Replacement line",
        "fixed_mot_component": "Fixed MOT component",
        "fixed_mot_deduction": "Deduction",
        "optional_overlay": "Optional overlay",
        "calculated_rollup": "Calculated roll-up",
    }
    return labels.get(role, "Component")


def _component_provenance_label(row: pd.Series) -> str:
    parts = []
    fed_path = str(row.get("fed_path") or "").strip()
    source_file = str(row.get("source_file") or "").strip()
    source_basis = str(row.get("source_basis") or "").strip()
    if fed_path:
        parts.append(f"FED path: {fed_path}")
    if source_basis:
        parts.append(f"Basis: {source_basis}")
    if source_file:
        parts.append(f"Source: {source_file}")
    return " | ".join(parts)


def _filter_source_horizon_rows(rows: pd.DataFrame, source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    if rows.empty or "FY" not in rows.columns:
        return rows
    lower, upper = _source_horizon_bounds(source_pack, controls)
    fy = pd.to_numeric(rows["FY"], errors="coerce")
    mask = fy.notna()
    if lower is not None:
        mask &= fy.ge(lower)
    if upper is not None:
        mask &= fy.le(upper)
    return rows[mask].copy()


def _source_horizon_bounds(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> tuple[int | None, int | None]:
    selection = str(controls.get("horizon") or "To FY2031").strip()
    common_start, common_end = _source_common_horizon_bounds(source_pack, controls)
    if selection == "Next 5 FY":
        forecast_start = _source_forecast_start_fy(source_pack)
        if forecast_start is None:
            forecast_start = common_start
        if forecast_start is None:
            return common_start, common_end
        upper = forecast_start + 4
        if common_end is not None:
            upper = min(upper, common_end)
        return forecast_start, upper
    if selection == "Full common horizon":
        return common_start, common_end
    upper = 2031
    if common_end is not None:
        upper = min(upper, common_end)
    return None, upper


def _source_common_horizon_bounds(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> tuple[int | None, int | None]:
    frame = getattr(source_pack, "hybrid_annual_revenue", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty or "FY" not in frame.columns:
        return None, None
    rows = frame.copy()
    selected_path = _selected_fed_path(controls)
    if selected_path and "fed_path" in rows.columns:
        path_rows = rows[rows["fed_path"].astype(str).eq(selected_path)].copy()
        if path_rows.empty and selected_path != "Selected rate":
            path_rows = rows[rows["fed_path"].astype(str).eq("Selected rate")].copy()
        if not path_rows.empty:
            rows = path_rows
    required_roles = {"replacement_line", "fixed_mot_component", "fixed_mot_deduction"}
    rows = rows[rows["row_role"].astype(str).isin(required_roles)].copy() if "row_role" in rows.columns else rows
    rows["FY"] = pd.to_numeric(rows["FY"], errors="coerce")
    rows["value"] = pd.to_numeric(rows.get("value"), errors="coerce")
    rows = rows.dropna(subset=["FY", "value"])
    if rows.empty:
        return None, None
    by_series = rows.groupby("series_id")["FY"].agg(["min", "max"])
    return int(by_series["min"].max()), int(by_series["max"].min())


def _source_forecast_start_fy(source_pack: RevenueSourcePack) -> int | None:
    frame = getattr(source_pack, "canonical_long", pd.DataFrame())
    if not isinstance(frame, pd.DataFrame) or frame.empty or "FY" not in frame.columns:
        return None
    rows = frame[frame.get("source_file", pd.Series("", index=frame.index)).astype(str).eq("official_befu25_annual.csv")].copy()
    if rows.empty:
        return None
    status = rows.get("value_status", pd.Series("", index=rows.index)).astype(str).str.lower()
    rows = rows[status.str.contains("forecast", na=False)].copy()
    rows["FY"] = pd.to_numeric(rows["FY"], errors="coerce")
    rows = rows.dropna(subset=["FY"])
    if rows.empty:
        return None
    return int(rows["FY"].min())


def _fy_within_bounds(fy: int, bounds: tuple[int | None, int | None]) -> bool:
    lower, upper = bounds
    if lower is not None and fy < lower:
        return False
    if upper is not None and fy > upper:
        return False
    return True


def _source_selected_release_rows(frame: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    if frame.empty or "source_file" not in frame.columns:
        return pd.DataFrame()
    release_round = str(controls.get("release_round") or "").strip()
    rows = frame[frame["source_file"].eq("release_values.csv")].copy()
    if release_round and "release_vintage" in rows.columns:
        rows = rows[rows["release_vintage"].astype(str).eq(release_round)]
    return rows


def _source_rolling_befu_1y_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "source_file" not in frame.columns:
        return pd.DataFrame()
    rows = frame[frame["source_file"].eq("release_values.csv")].copy()
    if rows.empty:
        return rows
    family = rows["release_family"].astype(str).str.upper() if "release_family" in rows.columns else pd.Series("", index=rows.index)
    horizon = pd.to_numeric(rows["horizon"], errors="coerce") if "horizon" in rows.columns else pd.Series(pd.NA, index=rows.index)
    return rows[family.eq("BEFU") & horizon.eq(1)].copy()


def _source_mot_uncertainty_rows(source_pack: RevenueSourcePack, frame: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    release = _source_selected_release_rows(frame, controls)
    bands = getattr(source_pack, "mot_error_bands", pd.DataFrame())
    if release.empty or not isinstance(bands, pd.DataFrame) or bands.empty:
        return pd.DataFrame()
    labels = {
        str(value).strip()
        for column in ["source_series_label", "display_name"]
        if column in frame.columns
        for value in frame[column].dropna().unique()
        if str(value).strip()
    }
    band_rows = bands[bands["series"].astype(str).isin(labels)].copy() if "series" in bands.columns else pd.DataFrame()
    if band_rows.empty:
        return pd.DataFrame()
    band_rows["horizon_int"] = pd.to_numeric(band_rows.get("horizon_june_years"), errors="coerce")
    band_rows["sample_size"] = pd.to_numeric(band_rows.get("n"), errors="coerce")
    band_rows = band_rows[band_rows["sample_size"].ge(10)]
    release = release.copy()
    release["horizon_int"] = pd.to_numeric(release.get("horizon"), errors="coerce")
    release["value"] = pd.to_numeric(release["value"], errors="coerce")
    release = release.dropna(subset=["FY", "value", "horizon_int"])
    merged = release.merge(band_rows, how="inner", on="horizon_int", suffixes=("", "_band"))
    if merged.empty:
        return pd.DataFrame()
    for column in ["p10", "p25", "p75", "p90"]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged = merged.dropna(subset=["p10", "p25", "p75", "p90"])
    if merged.empty:
        return pd.DataFrame()
    merged["lower80"] = merged["value"] * (1.0 + merged["p10"])
    merged["upper80"] = merged["value"] * (1.0 + merged["p90"])
    merged["lower50"] = merged["value"] * (1.0 + merged["p25"])
    merged["upper50"] = merged["value"] * (1.0 + merged["p75"])
    merged["hover_unit"] = _source_axis_title(frame)
    merged["horizon_label"] = "Horizon " + merged["horizon_int"].astype("Int64").astype(str) + " June-year(s)"
    return _dedupe_path_rows(merged.sort_values(["FY", "horizon_int"], kind="stable"))


def _dedupe_path_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    return rows.sort_values(["FY", "source_file", "source_cell"], kind="stable").drop_duplicates("FY", keep="last")


def _selected_series_id(source_pack: RevenueSourcePack, selected: str) -> str:
    alias = SOURCE_SERIES_ALIASES.get(str(selected or "").strip())
    if alias:
        return alias
    rows = source_pack.series_master[
        source_pack.series_master["Display name"].astype(str).eq(selected)
        | source_pack.series_master["Series ID"].astype(str).eq(selected)
    ]
    if not rows.empty:
        return str(rows.iloc[0]["Series ID"])
    if selected == "Total RUC+PED revenue":
        return "total_fed_ruc_net_revenue"
    if selected == "Total RUC forecast incl EV/PHEV":
        return "total_ruc_net_revenue"
    return selected.lower().replace(" ", "_")


def _source_revenue_basis_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    labels = {
        "net": "net",
        "gross": "gross",
        "admin": "admin",
        "deductions": "deduction",
        "deduction": "deduction",
        "nominal ex gst": "nominal_ex_gst",
    }
    return labels.get(text, "")


def _source_revenue_path_basis_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "gross" in text:
        return "Gross"
    if "net" in text:
        return "Net"
    return ""


def _source_revenue_basis_label(value: Any) -> str:
    text = str(value or "").strip()
    labels = {
        "net": "Net",
        "gross": "Gross",
        "admin": "Admin",
        "deduction": "Deductions",
        "nominal_ex_gst": "Nominal ex GST",
    }
    return labels.get(text, text)


def _uncertainty_source_key(controls: dict[str, Any]) -> str:
    text = str(controls.get("uncertainty") or controls.get("uncertainty_source") or "").strip().lower()
    return "mot_release_round" if "mot" in text or "release" in text else "mot_release_round"


def _selected_fy_number(controls: dict[str, Any]) -> int | None:
    return _fy_from_label(controls.get("selected_fy", ""))


def _fy_from_label(value: Any) -> int | None:
    text = str(value or "").upper().replace("FY", "")
    try:
        return int(text)
    except ValueError:
        return None


def _source_axis_title(frame: pd.DataFrame) -> str:
    units = [str(unit) for unit in frame["unit"].dropna().unique() if str(unit)]
    normalized = {_normalized_source_unit_label(unit) for unit in units}
    normalized = {unit for unit in normalized if unit}
    if len(normalized) == 1:
        return next(iter(normalized))
    return units[0] if len(units) == 1 else "Value"


def _normalized_source_unit_label(unit: str) -> str:
    text = str(unit or "").strip()
    if text in {"$m ex GST", "$m nominal ex GST"}:
        return "$m nominal ex GST"
    return text


def _source_format_value(value: Any, unit: str) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if "$m" in unit:
        return f"${numeric:,.0f}m"
    if "percent" in unit.lower():
        return f"{numeric:.1%}"
    return f"{numeric:,.1f}"


def _revenue_outlook_summary_cards(
    manifest: dict[str, Any],
    chart_rows: pd.DataFrame,
    future_revenue: pd.DataFrame,
) -> list[tuple[str, str, str | None]]:
    source = manifest.get("source_comparison", {}) if isinstance(manifest, dict) else {}
    scenario_rows = manifest.get("scenario_roles", []) if isinstance(manifest, dict) else []
    scenario_count = len(scenario_rows) if isinstance(scenario_rows, list) else 0
    latest_actual = _latest_period(chart_rows, row_type="historical_actual")
    first_forecast = _first_period(chart_rows, row_type="future_forecast")
    fy5_value, fy5_period = _fy5_revenue_value(chart_rows)
    delta_value, delta_period = _comparison_delta_value(chart_rows)
    gap_count = _future_gap_count(future_revenue)
    return [
        (
            "Pack status",
            _pack_status_label(manifest.get("pack_status", "unavailable")),
            _short_timestamp(manifest.get("promotion_time")),
        ),
        ("Scenarios", str(scenario_count), str(source.get("comparison_id", "reviewed comparison"))),
        ("Latest actual", latest_actual or "-", "latest source historical quarter"),
        ("First forecast", first_forecast or "-", "first reviewed scenario quarter"),
        ("FY5 revenue", _format_compact_value(fy5_value, "nominal NZD"), fy5_period or "no revenue bridge value"),
        ("Comparison delta", _format_signed_compact(delta_value), delta_period or f"{gap_count} governed revenue gaps"),
    ]


def _pack_status_label(status: Any) -> str:
    value = str(status or "unavailable")
    labels = {
        "explicitly_promoted_current_outlook": "Promoted",
        "missing": "Missing",
        "unavailable": "Unavailable",
    }
    return labels.get(value, value.replace("_", " ").title())


def _revenue_outlook_stream_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty:
        return []
    label_column = "series_label" if "series_label" in chart_rows.columns else "stream_label"
    if label_column not in chart_rows.columns:
        return []
    preferred = [
        "PED VKT per capita",
        "PED volume",
        "Light RUC net km",
        "Heavy RUC net km",
        "PED revenue",
        "Light RUC revenue",
        "Heavy RUC revenue",
        "Gross FED revenue",
        "Net FED revenue",
        "Total RUC all classes",
        "Net MVR revenue",
        "Total RUC+PED revenue",
        "Total NLTF revenue",
        "Light RUC volume",
        "Heavy RUC volume",
    ]
    data = chart_rows.copy()
    if "plot_allowed" in data.columns:
        data = data[data["plot_allowed"].fillna(True).astype(bool)].copy()
    available = set(data[label_column].dropna().astype(str))
    ordered = [label for label in preferred if label in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


def _revenue_outlook_series_metric_type(chart_rows: pd.DataFrame, selected_series: str) -> str:
    if chart_rows is None or chart_rows.empty:
        return ""
    label_column = "series_label" if "series_label" in chart_rows.columns else "stream_label"
    if label_column not in chart_rows.columns or "metric_type" not in chart_rows.columns:
        return ""
    rows = chart_rows[chart_rows[label_column].astype(str).eq(str(selected_series))].copy()
    return _first_non_empty(rows.get("metric_type", pd.Series(dtype=str)))


def _revenue_outlook_scenario_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty or "scenario_name" not in chart_rows.columns:
        return []
    data = chart_rows[~chart_rows["row_type"].astype(str).eq("historical_actual")].copy()
    if "plot_allowed" in data.columns:
        data = data[data["plot_allowed"].fillna(True).astype(bool)].copy()
    return sorted(data["scenario_name"].dropna().astype(str).unique().tolist())


def _revenue_outlook_trace_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty or "trace_name" not in chart_rows.columns:
        return []
    data = chart_rows.copy()
    if "plot_allowed" in data.columns:
        data = data[data["plot_allowed"].fillna(True).astype(bool)].copy()
    available = set(data["trace_name"].dropna().astype(str))
    preferred = [
        "Actual",
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    ]
    ordered = [trace for trace in preferred if trace in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


def _revenue_outlook_fed_path_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty or "fed_path" not in chart_rows.columns:
        return []
    data = chart_rows.copy()
    if "plot_allowed" in data.columns:
        data = data[data["plot_allowed"].fillna(True).astype(bool)].copy()
    values = [value for value in data["fed_path"].dropna().astype(str).unique().tolist() if value and value.lower() not in {"nan", "befu25"}]
    preferred = ["Current planned path", "No 2027 12c uplift", "Selected rate"]
    ordered = [value for value in preferred if value in values]
    ordered.extend(sorted(set(values).difference(ordered)))
    return ordered


def _revenue_outlook_fy_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty or "june_year" not in chart_rows.columns:
        return []
    years = pd.to_numeric(chart_rows["june_year"], errors="coerce").dropna().astype(int)
    if years.empty:
        return []
    return [f"FY{year}" for year in sorted(years.unique().tolist()) if year >= 2025]


def _scenario_names_for_traces(chart_rows: pd.DataFrame, trace_names: list[str]) -> list[str]:
    if chart_rows is None or chart_rows.empty or not trace_names or "trace_name" not in chart_rows.columns:
        return []
    rows = chart_rows[chart_rows["trace_name"].astype(str).isin(trace_names)].copy()
    if "scenario_name" not in rows.columns:
        return []
    return sorted(rows["scenario_name"].dropna().astype(str).unique().tolist())


def _filter_revenue_outlook_rows(
    chart_rows: pd.DataFrame,
    *,
    time_grain: str,
    stream_labels: list[str],
    fed_paths: list[str],
    scenario_names: list[str] | None = None,
    trace_names: list[str] | None = None,
) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame()
    data = chart_rows.copy()
    data = data[data["time_grain"].astype(str).eq(time_grain)].copy()
    if "plot_allowed" in data.columns:
        data = data[data["plot_allowed"].fillna(True).astype(bool)].copy()
    label_column = "series_label" if "series_label" in data.columns else "stream_label"
    if stream_labels:
        data = data[data[label_column].astype(str).isin(stream_labels)].copy()
    if fed_paths and "fed_path" in data.columns:
        fed_text = data["fed_path"].fillna("").astype(str)
        is_path_sensitive = data.get("trace_role", pd.Series("", index=data.index)).astype(str).eq("in_house_current_finalist")
        data = data[(~is_path_sensitive) | fed_text.isin(fed_paths)].copy()
    if trace_names and "trace_name" in data.columns:
        data = data[data["trace_name"].astype(str).isin(trace_names)].copy()
    if scenario_names:
        is_actual = data["row_type"].astype(str).eq("historical_actual")
        data = data[is_actual | data["scenario_name"].astype(str).isin(scenario_names)].copy()
    data["_period_order"] = data["period"].map(_revenue_period_order)
    return data.sort_values(["stream", "metric_type", "_period_order", "scenario_name"], kind="stable").drop(columns=["_period_order"], errors="ignore")


def _filter_revenue_bridge_rows(
    bridge: pd.DataFrame,
    stream_labels: list[str],
    scenario_names: list[str],
    fed_paths: list[str] | None = None,
) -> pd.DataFrame:
    if bridge is None or bridge.empty:
        return pd.DataFrame()
    data = bridge.copy()
    if stream_labels and "stream_label" in data.columns:
        data = data[data["stream_label"].astype(str).isin(stream_labels)].copy()
    if scenario_names and "scenario_name" in data.columns:
        scenario_text = data["scenario_name"].fillna("").astype(str)
        data = data[scenario_text.eq("") | scenario_text.isin(scenario_names)].copy()
    if fed_paths and "fed_path" in data.columns:
        fed_text = data["fed_path"].fillna("").astype(str)
        data = data[fed_text.eq("") | fed_text.isin(fed_paths)].copy()
    return data


def revenue_outlook_total_path_figure(rows: pd.DataFrame, *, selected_series: str, selected_fy: str) -> go.Figure:
    data = _selected_revenue_outlook_series_rows(rows, selected_series)
    if data.empty:
        return empty_figure("Selected revenue series is unavailable in the committed runtime pack.")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return empty_figure("Selected revenue series has no numeric runtime-pack values.")

    data["_period_order"] = data.get("period", pd.Series(dtype=str)).map(_revenue_period_order)
    data = data.sort_values("_period_order", kind="stable")
    axis_title = _revenue_axis_title(data)
    scenario_colors = _scenario_color_map(data)
    fig = go.Figure()
    trace_styles = {
        "Actual": ("#737373", "solid", 2.4),
        "MBU26 official": ("#00843D", "dash", 2.2),
        "Current finalist Base case": ("#006FAD", "solid", 2.8),
        "Current finalist High population/comparison": ("#E56B2B", "solid", 2.4),
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME: ("#C2410C", "dot", 2.4),
    }
    trace_names = _ordered_runtime_trace_names(data)
    for trace_name in trace_names:
        group = data[data["trace_name"].astype(str).eq(trace_name)].copy()
        if group.empty:
            continue
        group = group.drop_duplicates(["period", "trace_name", "scenario_name", "fed_path"], keep="last")
        group = group.sort_values("_period_order", kind="stable")
        for column in [
            "horizon",
            "horizon_scope",
            "bridge_status",
            "gap_reason",
            "data_scope",
            "value_status",
            "actual_quarters",
            "forecast_quarters",
            "ped_bridge_mode_label",
            "revenue_sensitivity_label",
        ]:
            if column not in group.columns:
                group[column] = ""
        group["horizon_hover"] = group.apply(_revenue_horizon_hover_label, axis=1)
        group["bridge_hover"] = group.apply(_revenue_bridge_hover_label, axis=1)
        group["scope_hover"] = group.apply(_revenue_scope_hover_label, axis=1)
        group["efficiency_hover"] = group.apply(_revenue_efficiency_hover_label, axis=1)
        color, dash, width = trace_styles.get(trace_name, (scenario_colors.get(trace_name, "#006FAD"), "solid", 2.2))
        fig.add_trace(
            go.Scatter(
                x=group["period"],
                y=group["value_numeric"],
                mode="lines+markers",
                name=trace_name,
                line={"color": color, "dash": dash, "width": width},
                marker={"size": 6},
                customdata=group[["horizon_hover", "bridge_hover", "scope_hover", "efficiency_hover"]].to_numpy(),
                hovertemplate=(
                    "%{x}<br>%{y:,.2f}"
                    "<br>%{customdata[0]}%{customdata[1]}%{customdata[2]}%{customdata[3]}"
                    "<extra>" + html.escape(trace_name) + "</extra>"
                ),
            )
        )

    periods = data["period"].dropna().astype(str).drop_duplicates().tolist()
    forecast_period = _revenue_outlook_forecast_start_period(data)
    if forecast_period and forecast_period in periods:
        fig.add_vline(x=forecast_period, line_dash="dash", line_color="#B45309")
        fig.add_annotation(x=forecast_period, y=1.0, yref="paper", text=f"Forecast start {forecast_period}", showarrow=False, yanchor="bottom")
    if selected_fy in periods:
        fig.add_vline(x=selected_fy, line_dash="dot", line_color="#102A43")
    fig.update_xaxes(categoryorder="array", categoryarray=periods, tickangle=-30)
    fig.update_layout(
        height=250,
        margin={"l": 52, "r": 18, "t": 16, "b": 46},
        yaxis_title=axis_title,
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.20, "x": 0.0},
    )
    return fig


def _render_revenue_outlook_fan_card(
    fan_band_rows: pd.DataFrame,
    fan_availability: pd.DataFrame,
    *,
    selected_series: str,
    selected_fed_path: str,
) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='gov-chart-card chart-card'>"
            "<div class='chart-card-title'>Uncertainty fan</div>"
            "<div class='chart-card-subtitle'>Fan source is controlled independently from the main trace selector.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        selected_fan_source = st.selectbox(
            "Fan source",
            list(FAN_SOURCE_OPTIONS),
            index=0,
            key="revenue_outlook_fan_source",
        )
        fig = revenue_outlook_uncertainty_fan_figure(
            fan_band_rows,
            fan_availability=fan_availability,
            selected_series=selected_series,
            fan_source=selected_fan_source,
            selected_fed_path=selected_fed_path,
        )
        st.plotly_chart(fig, use_container_width=True, key="chart_card_uncertainty_fan")
        st.caption(_revenue_outlook_fan_caption(fan_availability, selected_series, selected_fan_source)[:220])


def revenue_outlook_uncertainty_fan_figure(
    fan_band_rows: pd.DataFrame,
    *,
    fan_availability: pd.DataFrame | None = None,
    selected_series: str,
    fan_source: str = FAN_SOURCE_AUTO,
    selected_fed_path: str | None = None,
) -> go.Figure:
    selected_series_id = _revenue_outlook_fan_series_id(fan_availability, selected_series)
    resolved_source = _resolve_revenue_outlook_fan_source(fan_availability, selected_series_id, fan_source)
    if not resolved_source or resolved_source == FAN_SOURCE_NONE:
        return _revenue_outlook_gap_figure(_revenue_outlook_fan_gap_message(fan_availability, selected_series_id, fan_source), height=220)
    if fan_band_rows is None or fan_band_rows.empty:
        return _revenue_outlook_gap_figure(_revenue_outlook_fan_gap_message(fan_availability, selected_series_id, fan_source), height=220)
    data = fan_band_rows[
        fan_band_rows.get("series_id", pd.Series(dtype=str)).astype(str).eq(str(selected_series_id))
        & fan_band_rows.get("fan_source", pd.Series(dtype=str)).astype(str).eq(resolved_source)
    ].copy()
    if selected_fed_path and "fed_path" in data.columns:
        allowed_fed_paths = {"", str(selected_fed_path), "MBU26"}
        data = data[data["fed_path"].fillna("").astype(str).isin(allowed_fed_paths)].copy()
    for column in ["central", "lower50", "upper50", "lower80", "upper80"]:
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    data = data.dropna(subset=["central", "lower50", "upper50", "lower80", "upper80"]).copy()
    if data.empty:
        return _revenue_outlook_gap_figure(_revenue_outlook_fan_gap_message(fan_availability, selected_series_id, fan_source), height=220)
    data["_period_order"] = data.get("period", pd.Series(dtype=str)).map(_revenue_period_order)
    data = data.sort_values(["_period_order", "scenario_name"], kind="stable")
    fig = go.Figure()
    is_scenario_spread = resolved_source == FAN_SOURCE_SCENARIO_SPREAD
    band_specs = (
        [
            ("upper80", "lower80", "Scenario spread outer range (not probabilistic)", "rgba(0, 43, 92, 0.14)"),
            ("upper50", "lower50", "Scenario spread inner range (not probabilistic)", "rgba(0, 132, 61, 0.18)"),
        ]
        if is_scenario_spread
        else [
            ("upper80", "lower80", f"{resolved_source} 80% empirical band", "rgba(0, 43, 92, 0.14)"),
            ("upper50", "lower50", f"{resolved_source} 50% empirical band", "rgba(0, 132, 61, 0.18)"),
        ]
    )
    for upper, lower, name, color in band_specs:
        fig.add_trace(go.Scatter(x=data["period"], y=data[upper], mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip"))
        fig.add_trace(
            go.Scatter(
                x=data["period"],
                y=data[lower],
                mode="lines",
                fill="tonexty",
                fillcolor=color,
                line={"width": 0},
                name=name,
                customdata=data[["method", "source_file"]].to_numpy(),
                hovertemplate="%{x}<br>%{y:,.2f}<br>%{customdata[0]}<br>%{customdata[1]}<extra>%{fullData.name}</extra>",
            )
        )
    central_name = "Current finalist base case" if is_scenario_spread else resolved_source
    fig.add_trace(
        go.Scatter(
            x=data["period"],
            y=data["central"],
            mode="lines+markers",
            name=central_name,
            line={"color": "#006FAD", "width": 2.4},
            marker={"size": 6},
            customdata=data[["unit", "interpretation"]].to_numpy(),
            hovertemplate="%{x}<br>%{y:,.2f} %{customdata[0]}<br>%{customdata[1]}<extra>%{fullData.name}</extra>",
        )
    )
    unit = str(data["unit"].dropna().iloc[0]) if "unit" in data.columns and not data["unit"].dropna().empty else ""
    fig.update_layout(
        height=220,
        margin={"l": 40, "r": 12, "t": 16, "b": 40},
        hovermode="x unified",
        yaxis_title=unit,
        legend={"orientation": "h", "y": -0.24, "x": 0.0},
    )
    return fig


def _revenue_outlook_fan_series_id(fan_availability: pd.DataFrame | None, selected_series: str) -> str:
    selected = str(selected_series or "").strip()
    if fan_availability is None or fan_availability.empty:
        return selected
    series_ids = fan_availability.get("series_id", pd.Series(dtype=str)).dropna().astype(str)
    if selected in set(series_ids):
        return selected
    labels = fan_availability.get("series_label", pd.Series("", index=fan_availability.index)).fillna("").astype(str)
    matches = fan_availability[labels.eq(selected)]
    if not matches.empty:
        return str(matches.iloc[0].get("series_id", selected))
    return selected


def _resolve_revenue_outlook_fan_source(fan_availability: pd.DataFrame | None, selected_series: str, requested_source: str) -> str:
    selected_series = _revenue_outlook_fan_series_id(fan_availability, selected_series)
    requested_source = str(requested_source or FAN_SOURCE_AUTO)
    if requested_source != FAN_SOURCE_AUTO:
        return requested_source if _revenue_outlook_fan_available(fan_availability, selected_series, requested_source) else ""
    if fan_availability is None or fan_availability.empty:
        return ""
    selected = fan_availability[
        fan_availability.get("series_id", pd.Series(dtype=str)).astype(str).eq(str(selected_series))
        & fan_availability.get("available", pd.Series(False, index=fan_availability.index)).astype(str).str.lower().isin(["true", "1"])
    ]
    for source in FAN_SOURCE_PRIORITY:
        if source in set(selected.get("fan_source", pd.Series(dtype=str)).astype(str)):
            return source
    return ""


def _revenue_outlook_fan_available(fan_availability: pd.DataFrame | None, selected_series: str, fan_source: str) -> bool:
    if fan_availability is None or fan_availability.empty:
        return False
    selected_series = _revenue_outlook_fan_series_id(fan_availability, selected_series)
    rows = fan_availability[
        fan_availability.get("series_id", pd.Series(dtype=str)).astype(str).eq(str(selected_series))
        & fan_availability.get("fan_source", pd.Series(dtype=str)).astype(str).eq(str(fan_source))
    ]
    if rows.empty:
        return False
    return str(rows.iloc[0].get("available", "")).lower() in {"true", "1"}


def _revenue_outlook_fan_gap_message(fan_availability: pd.DataFrame | None, selected_series: str, requested_source: str) -> str:
    if fan_availability is None or fan_availability.empty:
        return "Fan availability table is missing from data/current_revenue_outlook; no fan can be drawn."
    selected_series = _revenue_outlook_fan_series_id(fan_availability, selected_series)
    requested_source = str(requested_source or FAN_SOURCE_AUTO)
    selected = fan_availability[fan_availability.get("series_id", pd.Series(dtype=str)).astype(str).eq(str(selected_series))]
    if selected.empty:
        return f"Selected series {selected_series} has no fan availability row in data/current_revenue_outlook/fan_availability.csv."
    if requested_source == FAN_SOURCE_AUTO:
        base_reason = "Auto / best available found no materialized fan source for this series."
    else:
        row = selected[selected.get("fan_source", pd.Series(dtype=str)).astype(str).eq(requested_source)]
        base_reason = str(row.iloc[0].get("reason", "")) if not row.empty else f"{requested_source} has no availability row."
    alternatives = _revenue_outlook_fan_alternatives(selected)
    return f"Fan source: {requested_source}. {base_reason} {alternatives}".strip()


def _revenue_outlook_fan_caption(fan_availability: pd.DataFrame | None, selected_series: str, requested_source: str) -> str:
    if fan_availability is None or fan_availability.empty:
        return "Fan availability table missing; no uncertainty bands are rendered."
    selected_series = _revenue_outlook_fan_series_id(fan_availability, selected_series)
    resolved = _resolve_revenue_outlook_fan_source(fan_availability, selected_series, requested_source)
    selected = fan_availability[fan_availability.get("series_id", pd.Series(dtype=str)).astype(str).eq(str(selected_series))]
    if resolved:
        row = selected[selected.get("fan_source", pd.Series(dtype=str)).astype(str).eq(resolved)]
        reason = str(row.iloc[0].get("reason", "")) if not row.empty else ""
        interpretation = str(row.iloc[0].get("interpretation", "")) if not row.empty else ""
        auto_note = f"Auto resolved to {resolved}. " if str(requested_source) == FAN_SOURCE_AUTO else ""
        return f"{auto_note}{reason} {interpretation}".strip()
    return _revenue_outlook_fan_gap_message(fan_availability, selected_series, requested_source)


def _revenue_outlook_fan_alternatives(selected_availability: pd.DataFrame) -> str:
    if selected_availability is None or selected_availability.empty:
        return "No alternative fan source is listed."
    alternatives = selected_availability[
        selected_availability.get("available", pd.Series(False, index=selected_availability.index)).astype(str).str.lower().isin(["true", "1"])
        & ~selected_availability.get("fan_source", pd.Series(dtype=str)).astype(str).isin([FAN_SOURCE_AUTO])
    ]["fan_source"].dropna().astype(str).unique().tolist()
    if not alternatives:
        return "No alternative fan source is available."
    return "Available alternative fan source(s): " + ", ".join(alternatives) + "."


def _revenue_outlook_gap_figure(message: str, *, height: int) -> go.Figure:
    fig = empty_figure(message)
    fig.update_layout(height=height, margin={"l": 20, "r": 20, "t": 18, "b": 24})
    return fig


def _revenue_outlook_forecast_start_period(rows: pd.DataFrame) -> str:
    if rows is None or rows.empty:
        return ""
    data = rows.copy()
    data["_period_order"] = data.get("period", pd.Series(dtype=str)).map(_revenue_period_order)
    actual_rows = data[data.get("row_type", pd.Series(dtype=str)).astype(str).eq("historical_actual")].copy()
    latest_actual_order = pd.to_numeric(actual_rows.get("_period_order"), errors="coerce").max() if not actual_rows.empty else pd.NA
    current = data[
        data.get("trace_role", pd.Series("", index=data.index)).astype(str).eq("in_house_current_finalist")
        & data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("future_forecast")
        & ~data.get("data_scope", pd.Series("", index=data.index)).astype(str).eq("actual_anchor")
    ].copy()
    if pd.notna(latest_actual_order):
        current = current[pd.to_numeric(current["_period_order"], errors="coerce").gt(float(latest_actual_order))].copy()
    if current.empty:
        return ""
    return str(current.sort_values("_period_order", kind="stable").iloc[0]["period"])


def revenue_outlook_component_figure(bridge: pd.DataFrame, *, selected_fy: str, selected_fed_path: str) -> go.Figure:
    plot = _selected_revenue_bridge_snapshot(bridge, selected_fy=selected_fy, selected_fed_path=selected_fed_path)
    if plot.empty:
        return empty_figure("Selected FY component rows are unavailable in revenue_bridge_components.")
    component_order = [
        "gross_ped_revenue",
        "light_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
    ]
    plot = plot[plot["stream"].astype(str).isin(component_order)].copy()
    if plot.empty:
        return empty_figure("No selected-FY component rows match the governed runtime component registry.")
    plot["_order"] = plot["stream"].astype(str).map({name: index for index, name in enumerate(component_order)})
    plot["component_numeric"] = pd.to_numeric(plot["component_value"], errors="coerce")
    plot = plot.dropna(subset=["component_numeric"]).sort_values("_order", kind="stable")
    fig = go.Figure(
        go.Bar(
            x=plot["stream_label"],
            y=plot["component_numeric"],
            marker_color=["#006FAD" if value >= 0 else "#B45309" for value in plot["component_numeric"]],
            customdata=plot[["component_unit", "component_type", "bridge_status"]].to_numpy(),
            hovertemplate="%{x}<br>%{y:,.1f} %{customdata[0]}<br>%{customdata[1]} - %{customdata[2]}<extra></extra>",
        )
    )
    fig.update_layout(height=360, margin={"l": 52, "r": 18, "t": 28, "b": 104}, yaxis_title=_bridge_axis_title(plot), xaxis_tickangle=-30)
    return fig


def revenue_outlook_split_figure(bridge: pd.DataFrame, *, selected_fy: str, selected_fed_path: str) -> go.Figure:
    plot = _selected_revenue_bridge_snapshot(bridge, selected_fy=selected_fy, selected_fed_path=selected_fed_path)
    split_ids = ["net_fed_revenue", "total_ruc_net_revenue", "net_mvr_revenue"]
    plot = plot[plot["stream"].astype(str).isin(split_ids)].copy() if not plot.empty else pd.DataFrame()
    if plot.empty:
        return empty_figure("Selected-FY split is unavailable in revenue_bridge_components.")
    plot["component_numeric"] = pd.to_numeric(plot["component_value"], errors="coerce")
    plot = plot.dropna(subset=["component_numeric"])
    plot = plot[plot["component_numeric"] > 0].copy()
    if plot.empty:
        return empty_figure("Selected-FY split has no positive numeric component values.")
    plot["_order"] = plot["stream"].astype(str).map({name: index for index, name in enumerate(split_ids)})
    plot = plot.sort_values("_order", kind="stable")
    fig = go.Figure(
        go.Pie(
            labels=plot["stream_label"],
            values=plot["component_numeric"],
            hole=0.45,
            marker={"colors": ["#006FAD", "#00843D", "#6B4E71"][: len(plot)]},
            customdata=plot[["component_unit", "bridge_status"]].to_numpy(),
            hovertemplate="%{label}<br>%{value:,.1f} %{customdata[0]}<br>%{percent}<br>%{customdata[1]}<extra></extra>",
        )
    )
    fig.update_layout(height=360, margin={"l": 12, "r": 12, "t": 28, "b": 16}, showlegend=True)
    return fig


def revenue_outlook_composition_figure(
    stack_components: pd.DataFrame,
    *,
    source_path: str,
    composition_mode: str | None = None,
    detail_level: str = REVENUE_STACK_DETAIL_CLEAN,
    overlays: list[str] | None = None,
) -> go.Figure:
    if stack_components is None or stack_components.empty:
        return empty_figure("Revenue composition rows are unavailable in revenue_stack_components.")
    data = stack_components.copy()
    if "source_path" in data.columns and source_path:
        data = data[data["source_path"].astype(str).eq(str(source_path))].copy()
    if "composition_mode" in data.columns:
        mode = str(composition_mode or REVENUE_STACK_MODE_BRIDGE)
        data = data[data["composition_mode"].astype(str).eq(mode)].copy()
    else:
        mode = str(composition_mode or REVENUE_STACK_MODE_BRIDGE)
    if data.empty:
        return empty_figure("No Revenue composition rows match the selected source path.")

    component_roles = {"component_positive", "component_negative"}
    full_formula_audit = str(detail_level) == REVENUE_STACK_DETAIL_FULL_FORMULA
    component_mask = data.get("stack_role", pd.Series("", index=data.index)).astype(str).isin(component_roles)
    if full_formula_audit:
        plot = data[component_mask].copy()
        stack_value_column = "stack_value"
        status_column = "stack_overlay_status"
    else:
        visibility = data.get("chart_visible", pd.Series(True, index=data.index)).fillna(False).astype(bool)
        plot = data[component_mask & visibility].copy()
        stack_value_column = "clean_stack_value" if "clean_stack_value" in plot.columns else "stack_value_clean"
        if stack_value_column not in plot.columns:
            stack_value_column = "stack_value"
        status_column = "clean_overlay_status"
    plot["stack_value_numeric"] = pd.to_numeric(plot.get(stack_value_column), errors="coerce")
    plot["FY_numeric"] = pd.to_numeric(plot.get("FY"), errors="coerce")
    plot = plot.dropna(subset=["stack_value_numeric", "FY_numeric"])
    if plot.empty:
        return empty_figure("No stackable contribution rows match the selected controls.")
    visible_stack_totals = (
        plot.groupby("FY_numeric", dropna=False)["stack_value_numeric"]
        .sum(min_count=1)
        .rename("visible_stack_total")
        .reset_index()
    )
    visible_stack_lookup = {
        int(row.FY_numeric): float(row.visible_stack_total)
        for row in visible_stack_totals.itertuples(index=False)
        if pd.notna(row.FY_numeric) and pd.notna(row.visible_stack_total)
    }

    fig = go.Figure()
    colors = [
        "#006FAD",
        "#00843D",
        "#6B4E71",
        "#E56B2B",
        "#3B7080",
        "#7A7D00",
        "#6A5ACD",
        "#C44900",
        "#287D8E",
        "#5B6770",
        "#B7791F",
        "#C2410C",
        "#9A3412",
        "#92400E",
    ]
    bridge_mode = mode == REVENUE_STACK_MODE_BRIDGE
    label_cols = ["line_label", "stack_role", "section_order", "line_order"]
    labels = plot[label_cols].drop_duplicates().copy()
    labels["bridge_role_order"] = labels["stack_role"].astype(str).map({"component_negative": 0, "component_positive": 1}).fillna(2).astype(int)
    sort_cols = ["bridge_role_order", "section_order", "line_order", "line_label"] if bridge_mode else ["section_order", "line_order", "line_label"]
    labels = labels.sort_values(sort_cols, kind="stable")
    bridge_running = {fy: 0.0 for fy in sorted(visible_stack_lookup)}
    for index, label_row in labels.reset_index(drop=True).iterrows():
        label = str(label_row["line_label"])
        trace_rows = plot[plot["line_label"].astype(str).eq(label)].sort_values("FY_numeric", kind="stable")
        trace_rows["visible_stack_total"] = trace_rows["FY_numeric"].map(lambda value: visible_stack_lookup.get(int(value), np.nan))
        trace_rows["hover_stack_value"] = trace_rows["stack_value_numeric"]
        custom_cols = ["unit", "visible_stack_total", "hover_stack_value"]
        for column in custom_cols:
            if column not in trace_rows.columns:
                trace_rows[column] = pd.NA
        trace_rows["visible_stack_total"] = pd.to_numeric(trace_rows["visible_stack_total"], errors="coerce")
        values = trace_rows["stack_value_numeric"].tolist()
        bar_kwargs = {}
        if bridge_mode:
            bases: list[float] = []
            for row in trace_rows.itertuples(index=False):
                fy = int(getattr(row, "FY_numeric"))
                value = float(getattr(row, "stack_value_numeric"))
                base = float(bridge_running.get(fy, 0.0))
                bases.append(base)
                bridge_running[fy] = base + value
            bar_kwargs["base"] = bases
        fig.add_trace(
            go.Bar(
                name=label,
                x=trace_rows["FY_numeric"].astype(int),
                y=values,
                marker_color=colors[index % len(colors)],
                customdata=trace_rows[custom_cols].to_numpy(),
                hovertemplate=(
                    "%{fullData.name}: %{customdata[2]:,.1f}; "
                    "FY %{x}<extra></extra>"
                ),
                **bar_kwargs,
            )
        )

    overlay_labels = [str(value) for value in overlays or [] if str(value).strip()]
    overlay_rows = data[
        data.get("stack_role", pd.Series("", index=data.index)).astype(str).eq("aggregate_overlay")
        & data.get("line_label", pd.Series("", index=data.index)).astype(str).isin(overlay_labels)
    ].copy()
    if not overlay_rows.empty:
        overlay_rows["FY_numeric"] = pd.to_numeric(overlay_rows.get("FY"), errors="coerce")
        overlay_rows["value_numeric"] = pd.to_numeric(overlay_rows.get("value"), errors="coerce")
        overlay_rows = overlay_rows.dropna(subset=["FY_numeric", "value_numeric"])
        for label, group in overlay_rows.groupby("line_label", sort=False):
            group = group.sort_values("FY_numeric", kind="stable")
            group["visible_stack_total"] = group["FY_numeric"].map(lambda value: visible_stack_lookup.get(int(value), np.nan))
            group["visible_stack_residual"] = pd.to_numeric(group["visible_stack_total"], errors="coerce") - pd.to_numeric(group["value_numeric"], errors="coerce")
            if status_column in group.columns:
                group = group[group[status_column].astype(str).eq("balanced")].copy()
            group = group[pd.to_numeric(group["visible_stack_residual"], errors="coerce").abs().le(1.0)].copy()
            if group.empty:
                continue
            custom_cols = ["unit", "visible_stack_total"]
            for column in custom_cols:
                if column not in group.columns:
                    group[column] = ""
            fig.add_trace(
                go.Scatter(
                    name=f"{label} overlay",
                    x=group["FY_numeric"].astype(int),
                    y=group["value_numeric"],
                    mode="lines+markers",
                    line={"width": 2.5, "dash": "dot"},
                    marker={"size": 7, "symbol": "diamond"},
                    customdata=group[custom_cols].to_numpy(),
                    hovertemplate=(
                        "%{fullData.name}: %{y:,.1f}; "
                        "FY %{x}<extra></extra>"
                    ),
                )
            )

    axis_title = _revenue_stack_axis_title(plot)
    fig.update_layout(
        barmode="overlay" if bridge_mode else "relative",
        height=460,
        margin={"l": 58, "r": 20, "t": 28, "b": 58},
        yaxis_title=axis_title,
        xaxis_title="June year",
        xaxis={"tickmode": "linear", "dtick": 1},
        yaxis={"zeroline": True, "zerolinewidth": 1.5, "zerolinecolor": "#52616B"},
        legend={"orientation": "h", "y": -0.20, "x": 0, "font": {"size": 10}},
        hovermode="x unified",
    )
    return fig


def _selected_revenue_outlook_series_rows(rows: pd.DataFrame, selected_series: str) -> pd.DataFrame:
    if rows is None or rows.empty:
        return pd.DataFrame()
    label_column = "series_label" if "series_label" in rows.columns else "stream_label"
    if label_column not in rows.columns:
        return pd.DataFrame()
    return rows[rows[label_column].astype(str).eq(str(selected_series))].copy()


def _ordered_runtime_trace_names(rows: pd.DataFrame) -> list[str]:
    if rows is None or rows.empty or "trace_name" not in rows.columns:
        return []
    available = set(rows["trace_name"].dropna().astype(str))
    preferred = [
        "Actual",
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    ]
    ordered = [trace for trace in preferred if trace in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


def _selected_fy_to_number(selected_fy: Any) -> int | None:
    match = re.search(r"(\d{4})", str(selected_fy or ""))
    if not match:
        return None
    return int(match.group(1))


def _selected_revenue_bridge_snapshot(bridge: pd.DataFrame, *, selected_fy: str, selected_fed_path: str) -> pd.DataFrame:
    if bridge is None or bridge.empty:
        return pd.DataFrame()
    data = bridge.copy()
    data = data[data["period"].astype(str).eq(str(selected_fy))].copy()
    if "scenario_name" in data.columns:
        data = data[data["scenario_name"].astype(str).eq("current_basecase")].copy()
    if selected_fed_path and "fed_path" in data.columns:
        data = data[data["fed_path"].astype(str).eq(str(selected_fed_path))].copy()
    return data


def _revenue_axis_title(rows: pd.DataFrame) -> str:
    unit = _first_non_empty(rows.get("value_unit", pd.Series(dtype=str)))
    return unit or "Value"


def _bridge_axis_title(rows: pd.DataFrame) -> str:
    unit = _first_non_empty(rows.get("component_unit", pd.Series(dtype=str)))
    return unit or "Value"


def revenue_outlook_figure(rows: pd.DataFrame, *, metric_type: str) -> go.Figure:
    data = pd.DataFrame() if rows is None else rows.copy()
    data = data[data.get("metric_type", pd.Series(dtype=str)).astype(str).eq(metric_type)].copy()
    streams = _revenue_outlook_stream_options(data)
    if not streams:
        streams = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
    fig = make_subplots(
        rows=1,
        cols=len(streams),
        subplot_titles=[short_stream_label(label) for label in streams],
        shared_yaxes=False,
        horizontal_spacing=0.06,
    )
    scenario_colors = _scenario_color_map(data)
    for col, stream_label in enumerate(streams, start=1):
        label_column = "series_label" if "series_label" in data.columns else "stream_label"
        stream_rows = data[data.get(label_column, pd.Series(dtype=str)).astype(str).eq(stream_label)].copy()
        stream_rows["_period_order"] = stream_rows.get("period", pd.Series(dtype=str)).map(_revenue_period_order)
        stream_rows["value_numeric"] = pd.to_numeric(stream_rows.get("value"), errors="coerce")
        stream_rows = stream_rows.sort_values("_period_order", kind="stable")
        unit = _first_non_empty(stream_rows.get("value_unit", pd.Series(dtype=str))) or ""
        historical = stream_rows[stream_rows["row_type"].astype(str).eq("historical_actual") & stream_rows["value_numeric"].notna()].copy()
        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical["period"],
                    y=historical["value_numeric"],
                    mode="lines",
                    name="Historical actual",
                    legendgroup="historical",
                    showlegend=col == 1,
                    line={"color": "#737373", "width": 2},
                    hovertemplate="%{x}<br>%{y:,.2f}<extra>Historical actual</extra>",
                ),
                row=1,
                col=col,
            )
        future = stream_rows[
            stream_rows["row_type"].astype(str).isin(["future_forecast", "official_comparator"])
            & stream_rows["value_numeric"].notna()
        ].copy()
        last_actual = historical.tail(1)[["period", "value_numeric"]] if not historical.empty else pd.DataFrame()
        group_column = "trace_name" if "trace_name" in future.columns else "scenario_name"
        for scenario, group in future.groupby(group_column, dropna=False):
            scenario_name = str(scenario)
            color = scenario_colors.get(scenario_name, "#006FAD")
            plot_cols = [
                col
                for col in [
                    "period",
                    "value_numeric",
                    "horizon",
                    "horizon_scope",
                    "bridge_status",
                    "gap_reason",
                    "data_scope",
                    "value_status",
                    "actual_quarters",
                    "forecast_quarters",
                    "ped_bridge_mode_label",
                    "revenue_sensitivity_label",
                    "ped_efficiency_label",
                    "adjusted_litres_per_100km",
                ]
                if col in group.columns
            ]
            plot_group = group[plot_cols].copy()
            for column in [
                "horizon",
                "horizon_scope",
                "bridge_status",
                "gap_reason",
                "data_scope",
                "value_status",
                "actual_quarters",
                "forecast_quarters",
                "ped_bridge_mode_label",
                "revenue_sensitivity_label",
                "ped_efficiency_label",
                "adjusted_litres_per_100km",
            ]:
                if column not in plot_group.columns:
                    plot_group[column] = ""
            trace_role = _first_non_empty(group.get("trace_role", pd.Series(dtype=str)))
            if not last_actual.empty and trace_role != "official_external_comparator":
                join_row = last_actual.copy()
                join_row["horizon"] = pd.NA
                join_row["horizon_scope"] = ""
                join_row["bridge_status"] = "historical_actual"
                join_row["gap_reason"] = ""
                join_row["data_scope"] = "latest_actual_join"
                join_row["value_status"] = "Actual join"
                join_row["actual_quarters"] = ""
                join_row["forecast_quarters"] = ""
                plot_group = pd.concat([join_row, plot_group], ignore_index=True, sort=False)
            plot_group["horizon_hover"] = plot_group.apply(_revenue_horizon_hover_label, axis=1)
            plot_group["bridge_hover"] = plot_group.apply(_revenue_bridge_hover_label, axis=1)
            plot_group["scope_hover"] = plot_group.apply(_revenue_scope_hover_label, axis=1)
            plot_group["efficiency_hover"] = plot_group.apply(_revenue_efficiency_hover_label, axis=1)
            label = _scenario_label(scenario_name, group)
            fig.add_trace(
                go.Scatter(
                    x=plot_group["period"],
                    y=plot_group["value_numeric"],
                    mode="lines+markers",
                    name=label,
                    legendgroup=f"scenario-{scenario_name}",
                    showlegend=col == 1,
                    line={"color": color, "width": 2},
                    marker={"size": 6},
                    customdata=plot_group[["horizon_hover", "bridge_hover", "scope_hover", "efficiency_hover"]].to_numpy(),
                    hovertemplate="%{x}<br>%{y:,.2f}<br>%{customdata[0]}%{customdata[1]}%{customdata[2]}%{customdata[3]}<extra>" + html.escape(label) + "</extra>",
                ),
                row=1,
                col=col,
            )
            marker_rows = group[group["horizon"].map(_is_forecast_start_or_h13)].copy()
            if not marker_rows.empty:
                marker_rows["marker_hover"] = marker_rows.apply(_revenue_marker_hover_label, axis=1)
                marker_rows["horizon_hover"] = marker_rows.apply(_revenue_horizon_hover_label, axis=1)
                fig.add_trace(
                    go.Scatter(
                        x=marker_rows["period"],
                        y=marker_rows["value_numeric"],
                        mode="markers",
                        name=f"{label} markers",
                        legendgroup=f"scenario-{scenario_name}",
                        showlegend=False,
                        marker={"color": color, "size": 11, "symbol": "triangle-up-open", "line": {"width": 2}},
                        customdata=marker_rows[["marker_hover", "horizon_hover"]].to_numpy(),
                        hovertemplate="%{x}<br>%{y:,.2f}<br>%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
                    ),
                    row=1,
                    col=col,
                )
        periods = stream_rows["period"].dropna().astype(str).drop_duplicates().tolist()
        fig.update_xaxes(categoryorder="array", categoryarray=periods, tickangle=-35, row=1, col=col)
        fig.update_yaxes(title_text=unit, row=1, col=col, separatethousands=True)
        if stream_rows.empty:
            fig.add_annotation(text="No rows", x=0.5, y=0.5, showarrow=False, row=1, col=col)
    fig.update_layout(
        height=390,
        margin={"l": 40, "r": 18, "t": 46, "b": 64},
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.22, "x": 0.0},
    )
    return fig


def _scenario_color_map(rows: pd.DataFrame) -> dict[str, str]:
    palette = ["#006FAD", "#E56B2B", "#00843D", "#6B4E71", "#C2410C", "#0F766E"]
    trace_palette = {
        "Actual": "#737373",
        "MBU26 official": "#00843D",
        "Current finalist Base case": "#006FAD",
        "Current finalist High population/comparison": "#E56B2B",
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME: "#C2410C",
    }
    output: dict[str, str] = {}
    if rows is None or rows.empty:
        return output
    if "trace_name" in rows.columns:
        for trace_name in rows["trace_name"].dropna().astype(str).unique().tolist():
            if trace_name in trace_palette:
                output[trace_name] = trace_palette[trace_name]
    scenarios = rows[~rows["row_type"].astype(str).eq("historical_actual")].copy()
    scenario_records = (
        scenarios[["scenario_name", "scenario_role"]]
        .dropna(subset=["scenario_name"])
        .astype(str)
        .drop_duplicates()
        .sort_values(["scenario_role", "scenario_name"], kind="stable")
        .to_dict("records")
    )
    for record in scenario_records:
        name = str(record.get("scenario_name") or "").strip()
        if not name:
            continue
        role = str(record.get("scenario_role") or "").strip()
        if role == SCENARIO_ROLE_BASECASE:
            output[name] = palette[0]
        elif role == SCENARIO_ROLE_COMPARISON:
            output[name] = palette[1 + (_scenario_comparison_color_index(name) % (len(palette) - 1))]
        else:
            output[name] = palette[_stable_palette_index(name, len(palette))]
    return output


def _scenario_comparison_color_index(name: str) -> int:
    digits = ""
    for character in reversed(str(name).strip()):
        if character.isdigit():
            digits = character + digits
            continue
        break
    if digits:
        return max(int(digits) - 1, 0)
    return 0


def _stable_palette_index(name: str, palette_size: int) -> int:
    if palette_size <= 0:
        return 0
    return sum(ord(character) for character in str(name)) % palette_size


def _scenario_label(scenario_name: str, rows: pd.DataFrame) -> str:
    trace_name = _first_non_empty(rows.get("trace_name", pd.Series(dtype=str)))
    if trace_name:
        return str(trace_name)
    display_name = _first_non_empty(rows.get("scenario_display_name", pd.Series(dtype=str)))
    label = _human_revenue_code_label(display_name or scenario_name)
    role = _first_non_empty(rows.get("scenario_role", pd.Series(dtype=str)))
    role_label = _human_revenue_code_label(role)
    suffix = f" ({role_label})" if role_label and role_label.lower() != label.lower() else ""
    return f"{label}{suffix}"


def _human_revenue_code_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lookup = {
        "basecase": "Base case",
        "comparison": "Comparison",
        "current_basecase": "Current base case",
        "current_comparison_1": "Current comparison 1",
        "official_selected_mot_befu": "Official selected MOT/BEFU",
        "official_rolling_befu_1y": "Official rolling BEFU 1Y",
        "historical_actual": "Historical actual",
        "historical_activity_available": "Historical activity available",
        "forecast_available": "Forecast available",
        "governed_gap": "Governed gap",
        "available": "Available",
    }
    normalized = text.lower()
    if normalized in lookup:
        return lookup[normalized]
    return re.sub(r"\s+", " ", text.replace("_", " ").replace("-", " ")).strip()


def _is_forecast_start_or_h13(horizon: Any) -> bool:
    try:
        value = int(float(horizon))
    except Exception:
        return False
    return value in {1, BACKTEST_SUPPORTED_MAX_HORIZON + 1}


def _revenue_horizon_hover_label(row: pd.Series) -> str:
    data_scope = str(row.get("data_scope") or "").strip()
    if data_scope in {"actual_anchor", "current_nowcast", "current_forecast", "official_comparator"}:
        return _human_revenue_code_label(str(row.get("value_status") or data_scope))
    try:
        horizon = int(float(row.get("horizon")))
    except Exception:
        return "Latest actual join point"
    scope = str(row.get("horizon_scope") or "").strip()
    if scope == "H1-H12" or 1 <= horizon <= BACKTEST_SUPPORTED_MAX_HORIZON:
        return f"H{horizon}: H1-H12 backtest-supported horizon"
    return f"H{horizon}: H13+ long-range extrapolation"


def _revenue_bridge_hover_label(row: pd.Series) -> str:
    status = str(row.get("bridge_status") or "").strip()
    reason = str(row.get("gap_reason") or "").strip()
    status_label = _human_revenue_code_label(status)
    reason_label = _human_revenue_code_label(reason)
    if reason:
        return f"<br>Bridge status: {html.escape(status_label)} - {html.escape(reason_label)}"
    if status:
        return f"<br>Bridge status: {html.escape(status_label)}"
    return ""


def _revenue_scope_hover_label(row: pd.Series) -> str:
    parts = []
    actual_quarters = str(row.get("actual_quarters") or "").strip()
    forecast_quarters = str(row.get("forecast_quarters") or "").strip()
    if actual_quarters:
        parts.append(f"actual: {html.escape(actual_quarters)}")
    if forecast_quarters:
        parts.append(f"forecast: {html.escape(forecast_quarters)}")
    if not parts:
        return ""
    return "<br>" + "; ".join(parts)


def _revenue_efficiency_hover_label(row: pd.Series) -> str:
    bridge_value = row.get("ped_bridge_mode_label")
    bridge = "" if pd.isna(bridge_value) else str(bridge_value).strip()
    sensitivity_value = row.get("revenue_sensitivity_label")
    sensitivity = "" if pd.isna(sensitivity_value) else str(sensitivity_value).strip()
    label_value = row.get("ped_efficiency_label")
    label = "" if pd.isna(label_value) else str(label_value).strip()
    litres = pd.to_numeric(row.get("adjusted_litres_per_100km"), errors="coerce")
    bridge_text = f"<br>PED bridge: {html.escape(bridge)}" if bridge else ""
    if sensitivity:
        return f"{bridge_text}<br>Sensitivity: {html.escape(sensitivity)}"
    if not label or pd.isna(litres):
        return bridge_text
    return f"{bridge_text}<br>PED fleet efficiency: {html.escape(label)}; adjusted litres/100km: {float(litres):,.2f}"


def _revenue_marker_hover_label(row: pd.Series) -> str:
    try:
        horizon = int(float(row.get("horizon")))
    except Exception:
        return "Forecast marker"
    if horizon == 1:
        return "Forecast start (H1)"
    if horizon == BACKTEST_SUPPORTED_MAX_HORIZON + 1:
        return f"Long-range extrapolation begins (H{horizon})"
    return f"Forecast marker (H{horizon})"


def _revenue_bridge_display_table(bridge: pd.DataFrame) -> pd.DataFrame:
    if bridge is None or bridge.empty:
        return pd.DataFrame()
    view = bridge.copy()
    rename = {
        "scenario_name": "Scenario",
        "scenario_role": "Role",
        "stream_label": "Stream",
        "component_type": "Component",
        "period": "Period",
        "horizon": "Horizon",
        "activity_value": "Activity",
        "activity_unit": "Activity unit",
        "component_value": "Component value",
        "component_unit": "Component unit",
        "rate_value": "Rate",
        "rate_unit": "Rate unit",
        "revenue_nzd": "Revenue NZD",
        "bridge_status": "Bridge status",
        "bridge_method": "Bridge method",
        "gap_reason": "Gap reason",
        "source": "Source",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in ["Activity", "Component value", "Rate", "Revenue NZD"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: _format_compact_value(value, "nominal NZD" if col == "Revenue NZD" else ""))
    return view


def _ped_bridge_mode_label_lookup(mode_config: pd.DataFrame) -> dict[str, str]:
    if mode_config is not None and not mode_config.empty and {"bridge_mode", "display_name"}.issubset(mode_config.columns):
        source = mode_config.copy()
        if "alpha" in source.columns:
            source["_alpha"] = pd.to_numeric(source["alpha"], errors="coerce")
            source = source.sort_values("_alpha", kind="stable")
        lookup = {
            str(row.display_name): str(row.bridge_mode)
            for row in source.itertuples(index=False)
            if str(getattr(row, "display_name", "")).strip() and str(getattr(row, "bridge_mode", "")).strip()
        }
        if lookup:
            return lookup
    ordered_modes = ["raw_model", "blend_25", "blend_50", "blend_75", "optimized_migration"]
    return {
        PED_BRIDGE_MODE_LABELS.get(mode, mode.replace("_", " ").title()): mode
        for mode in ordered_modes
        if mode in PED_BRIDGE_MODE_LABELS or mode == "optimized_migration"
    }


def _ped_bridge_diagnostics_display_table(audit: pd.DataFrame) -> pd.DataFrame:
    if audit is None or audit.empty:
        return pd.DataFrame()
    view = audit.copy()
    rename = {
        "FY": "FY",
        "source_path": "Source path",
        "scenario_name": "Scenario",
        "ped_vkt_per_capita": "PED VKTpc",
        "scenario_population": "Scenario population",
        "population_source_status": "Population status",
        "population_fallback_flag": "Fallback",
        "raw_light_petrol_vkt_million_km": "Raw light-petrol VKT",
        "optimized_light_petrol_vkt_million_km": "Optimized light-petrol VKT",
        "optimization_delta_million_km": "Optimization delta",
        "base_litres_per_100km": "L/100km",
        "ped_volume_raw_million_litres": "Raw PED volume",
        "ped_volume_optimized_million_litres": "Optimized PED volume",
        "ped_rate_nzd_per_litre": "PED rate",
        "gross_ped_revenue_raw_million_nzd": "Raw PED revenue",
        "gross_ped_revenue_optimized_million_nzd": "Optimized PED revenue",
        "total_nltf_raw_million_nzd": "Raw Total NLTF",
        "total_nltf_optimized_million_nzd": "Optimized Total NLTF",
        "mbu26_light_petrol_vkt_million_km": "MBU light-petrol VKT",
        "mbu26_ped_volume_million_litres": "MBU PED volume",
        "mbu26_gross_ped_revenue_million_nzd": "MBU PED revenue",
        "population_warning": "Warning",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    numeric_cols = [
        "PED VKTpc",
        "Scenario population",
        "Raw light-petrol VKT",
        "Optimized light-petrol VKT",
        "Optimization delta",
        "L/100km",
        "Raw PED volume",
        "Optimized PED volume",
        "PED rate",
        "Raw PED revenue",
        "Optimized PED revenue",
        "Raw Total NLTF",
        "Optimized Total NLTF",
        "MBU light-petrol VKT",
        "MBU PED volume",
        "MBU PED revenue",
    ]
    for col in numeric_cols:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: "" if pd.isna(value) else f"{float(value):,.3f}")
    return view


def _ped_bridge_shape_fit_display_table(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics is None or metrics.empty:
        return pd.DataFrame()
    view = metrics.copy()
    rename = {
        "source_path": "Source path",
        "scenario_name": "Scenario",
        "series_id": "Series",
        "bridge_variant": "Variant",
        "mbu_comparator_series_id": "MBU comparator",
        "n_rows": "Rows",
        "correlation_vs_mbu": "Correlation",
        "slope_vs_mbu": "Slope",
        "mean_abs_error": "MAE",
        "rmse": "RMSE",
        "mean_abs_pct_error": "MAPE",
        "shape_anchor_status": "Status",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in ["Correlation", "Slope", "MAE", "RMSE", "MAPE"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: "" if pd.isna(value) else f"{float(value):,.4f}")
    return view


def _ped_bridge_mode_impact_display_table(audit: pd.DataFrame) -> pd.DataFrame:
    if audit is None or audit.empty:
        return pd.DataFrame()
    view = audit.copy()
    rename = {
        "FY": "FY",
        "source_path": "Source path",
        "selected_ped_bridge_label": "Bridge mode",
        "bridge_alpha": "Alpha",
        "series_id": "Series",
        "baseline": "Baseline",
        "adjusted": "Adjusted",
        "delta": "Delta",
        "unit": "Unit",
        "population_source_status": "Population status",
        "gap_reason": "Warning",
        "formula": "Formula",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in ["Alpha", "Baseline", "Adjusted", "Delta"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: "" if pd.isna(value) else f"{float(value):,.4f}")
    return view


def _ped_efficiency_adjustment_display_table(adjustment: pd.DataFrame) -> pd.DataFrame:
    if adjustment is None or adjustment.empty:
        return pd.DataFrame()
    view = adjustment.copy()
    rename = {
        "period": "FY",
        "source_path": "Source path",
        "efficiency_label": "Efficiency",
        "ped_vkt_per_capita": "VKTpc",
        "population_million": "Population (m)",
        "adjusted_light_petrol_vkt_million_km": "Light-petrol VKT (m km)",
        "base_litres_per_100km": "Base L/100km",
        "adjusted_litres_per_100km": "Adjusted L/100km",
        "baseline_ped_volume_million_litres": "Baseline PED volume (m L)",
        "adjusted_ped_volume_million_litres": "Adjusted PED volume (m L)",
        "ped_volume_delta_million_litres": "PED volume delta (m L)",
        "ped_rate_nzd_per_litre": "PED rate ($/L)",
        "baseline_gross_ped_revenue_million_nzd": "Baseline PED revenue ($m)",
        "adjusted_gross_ped_revenue_million_nzd": "Adjusted PED revenue ($m)",
        "gross_ped_revenue_delta_million_nzd": "PED revenue delta ($m)",
        "baseline_total_nltf_net_revenue_million_nzd": "Baseline Total NLTF ($m)",
        "adjusted_total_nltf_net_revenue_million_nzd": "Adjusted Total NLTF ($m)",
        "total_nltf_net_revenue_delta_million_nzd": "Total NLTF delta ($m)",
        "reconciliation_status": "Status",
        "vktpc_source_cell": "VKTpc source",
        "population_source_cell": "Population source",
        "formula": "Formula",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    numeric_cols = [
        "VKTpc",
        "Population (m)",
        "Light-petrol VKT (m km)",
        "Base L/100km",
        "Adjusted L/100km",
        "Baseline PED volume (m L)",
        "Adjusted PED volume (m L)",
        "PED volume delta (m L)",
        "PED rate ($/L)",
        "Baseline PED revenue ($m)",
        "Adjusted PED revenue ($m)",
        "PED revenue delta ($m)",
        "Baseline Total NLTF ($m)",
        "Adjusted Total NLTF ($m)",
        "Total NLTF delta ($m)",
    ]
    for col in numeric_cols:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(
                lambda value: "" if pd.isna(value) else f"{float(value):,.3f}"
            )
    return view


def _sensitivity_impact_display_table(audit: pd.DataFrame) -> pd.DataFrame:
    if audit is None or audit.empty:
        return pd.DataFrame()
    view = audit.copy()
    rename = {
        "FY": "FY",
        "source_path": "Source path",
        "scenario_name": "Scenario",
        "series_id": "Series",
        "baseline": "Baseline",
        "adjusted": "Adjusted",
        "delta": "Delta",
        "unit": "Unit",
        "selected_fleet_efficiency": "Fleet efficiency",
        "selected_pt_mode_shift": "PT mode shift",
        "selected_demand_elasticity": "Demand elasticity",
        "eff_gain": "Efficiency gain",
        "pt_factor": "PT factor",
        "elasticity": "Elasticity",
        "cost_per_km_ratio": "Cost/km ratio",
        "demand_factor": "Demand factor",
        "gap_reason": "Gap reason",
        "formula": "Formula",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in ["Baseline", "Adjusted", "Delta", "Efficiency gain", "PT factor", "Elasticity", "Cost/km ratio", "Demand factor"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(
                lambda value: "" if pd.isna(value) else f"{float(value):,.4f}"
            )
    return view


def _revenue_line_source_options(line_reconciliation: pd.DataFrame) -> list[str]:
    if line_reconciliation is None or line_reconciliation.empty or "source_path" not in line_reconciliation.columns:
        return ["MBU26 official", "Current finalist Base case", "Current finalist High population/comparison"]
    values = [value for value in line_reconciliation["source_path"].dropna().astype(str).unique().tolist() if value]
    preferred = ["MBU26 official", "Current finalist Base case", "Current finalist High population/comparison"]
    ordered = [value for value in preferred if value in values]
    ordered.extend(sorted(set(values).difference(ordered)))
    return ordered or preferred


def _revenue_stack_mode_options(stack_components: pd.DataFrame) -> list[str]:
    preferred = list(REVENUE_STACK_MODES)
    if stack_components is None or stack_components.empty or "composition_mode" not in stack_components.columns:
        return preferred
    values = [value for value in stack_components["composition_mode"].dropna().astype(str).unique().tolist() if value]
    ordered = [value for value in preferred if value in values]
    ordered.extend(sorted(set(values).difference(ordered)))
    return ordered or preferred


def _revenue_stack_axis_title(stack_components: pd.DataFrame) -> str:
    if stack_components is None or stack_components.empty or "unit" not in stack_components.columns:
        return "$m nominal ex GST"
    units = [str(value) for value in stack_components["unit"].dropna().unique().tolist() if str(value).strip()]
    if "$m nominal ex GST" in units:
        return "$m nominal ex GST"
    return units[0] if units else "$m nominal ex GST"


def _revenue_stack_overlay_options(stack_components: pd.DataFrame) -> list[str]:
    preferred = [
        "Gross RUC",
        "RUC net admin",
        "RUC net admin/refunds",
        "Gross FED",
        "Net FED",
        "Gross MVR",
        "MVR net admin & COO",
        "MVR net admin/refunds/COO",
        "Total RUC+PED",
        "Total gross revenues",
        "Total admin fees",
        "Total revenues net of admin fees",
        "Total refunds",
        "Total NLTF revenue",
    ]
    if stack_components is None or stack_components.empty or "stack_role" not in stack_components.columns:
        return preferred
    overlay = stack_components[stack_components["stack_role"].astype(str).eq("aggregate_overlay")].copy()
    if overlay.empty or "line_label" not in overlay.columns:
        return preferred
    values = [str(value) for value in overlay["line_label"].dropna().unique().tolist() if str(value).strip()]
    ordered = [value for value in preferred if value in values]
    ordered.extend(sorted(set(values).difference(ordered)))
    return ordered or preferred


def _revenue_stack_default_overlays(composition_mode: str, overlay_options: list[str]) -> list[str]:
    preferred = "Total gross revenues" if composition_mode == REVENUE_STACK_MODE_GROSS else "Total NLTF revenue"
    return [preferred] if preferred in overlay_options else []


def _filter_revenue_stack_components(
    stack_components: pd.DataFrame,
    *,
    source_path: str,
    composition_mode: str | None = None,
    sections: list[str],
    fy_range: tuple[int, int] | list[int],
) -> pd.DataFrame:
    if stack_components is None or stack_components.empty:
        return pd.DataFrame()
    data = stack_components.copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce").astype("Int64")
    if source_path and "source_path" in data.columns:
        data = data[data["source_path"].astype(str).eq(str(source_path))].copy()
    if composition_mode and "composition_mode" in data.columns:
        data = data[data["composition_mode"].astype(str).eq(str(composition_mode))].copy()
    if sections and "section" in data.columns:
        data = data[data["section"].astype(str).isin(sections)].copy()
    try:
        low, high = int(fy_range[0]), int(fy_range[1])
    except Exception:
        low, high = _revenue_line_fy_bounds(data)
    data = data[data["FY_numeric"].between(low, high, inclusive="both")].copy()
    sort_cols = [
        col
        for col in ["source_path_order", "composition_mode_order", "FY_numeric", "section_order", "line_order", "series_id"]
        if col in data.columns
    ]
    if sort_cols:
        data = data.sort_values(sort_cols, kind="stable")
    return data.drop(columns=["FY_numeric"], errors="ignore")


def _revenue_stack_gap_banner(stack_components: pd.DataFrame) -> str:
    if stack_components is None or stack_components.empty:
        return ""
    status_col = "stack_overlay_status" if "stack_overlay_status" in stack_components.columns else "stack_balance_status"
    residual_col = "stack_overlay_residual" if "stack_overlay_residual" in stack_components.columns else "stack_balance_residual"
    if status_col not in stack_components.columns or residual_col not in stack_components.columns:
        return ""
    cols = [col for col in ["source_path", "composition_mode", "FY", "overlay_label", status_col, residual_col] if col in stack_components.columns]
    status = stack_components[cols].drop_duplicates()
    gaps = status[~status[status_col].astype(str).eq("balanced")].copy()
    if gaps.empty:
        return ""
    gaps[residual_col] = pd.to_numeric(gaps[residual_col], errors="coerce")
    worst = gaps.loc[gaps[residual_col].abs().idxmax()] if gaps[residual_col].notna().any() else gaps.iloc[0]
    return (
        "Composition overlay suppressed where the visible stack does not reconcile to its governed target. "
        f"Largest residual: {worst.get('source_path', '')} {worst.get('composition_mode', '')} FY{worst.get('FY', '')} "
        f"vs {worst.get('overlay_label', 'target')} "
        f"{_format_compact_value(worst.get(residual_col), '$m nominal ex GST')}."
    )


def _revenue_stack_components_display_table(stack_components: pd.DataFrame) -> pd.DataFrame:
    if stack_components is None or stack_components.empty:
        return pd.DataFrame()
    view = stack_components.copy()
    rename = {
        "composition_mode": "Composition mode",
        "section": "Section",
        "line_label": "Line",
        "value": "Value",
        "raw_value": "Raw value",
        "signed_contribution": "Signed contribution",
        "stack_value": "Stack value",
        "stack_value_clean": "Stack value clean",
        "clean_stack_value": "Clean stack value",
        "chart_visible": "Clean chart visible",
        "legend_visible": "Clean legend visible",
        "net_effect_group": "Net effect group",
        "stack_total_by_FY": "Stack total by FY",
        "overlay_total_value": "Overlay total",
        "overlay_label": "Overlay target",
        "stack_overlay_residual": "Overlay residual",
        "stack_overlay_status": "Overlay status",
        "clean_stack_total_by_FY": "Clean stack total by FY",
        "clean_overlay_total_value": "Clean overlay total",
        "clean_overlay_residual": "Clean overlay residual",
        "clean_overlay_status": "Clean overlay status",
        "unit": "Unit",
        "source_path": "Source path",
        "FY": "FY",
        "period": "FY label",
        "row_role": "Row role",
        "stack_role": "Stack role",
        "formula_role": "Formula role",
        "source_file": "Source file",
        "source_cell": "Source cell/formula",
        "formula": "Formula",
        "replacement_flag": "Replacement",
        "model_id": "Model ID",
        "quarter_composition": "Quarter composition",
        "actual_quarters": "Actual quarters",
        "forecast_quarters": "Forecast quarters",
        "residual_vs_official": "Residual vs official",
        "stack_balance_residual": "Stack residual",
        "formula_residual_status": "Formula status",
        "formula_residual": "Formula residual",
        "stack_note": "Stack note",
        "availability_status": "Status",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in [
        "Value",
        "Signed contribution",
        "Stack value",
        "Stack total by FY",
        "Overlay total",
        "Overlay residual",
        "Residual vs official",
        "Stack residual",
        "Formula residual",
    ]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: _format_compact_value(value, ""))
    return view


def _ev_phev_split_assumptions_display_table(split_assumptions: pd.DataFrame) -> pd.DataFrame:
    if split_assumptions is None or split_assumptions.empty:
        return pd.DataFrame()
    view = split_assumptions.copy()
    rename = {
        "FY": "FY",
        "source_path": "Source path",
        "scenario_name": "Scenario",
        "scenario_role": "Scenario role",
        "conventional_light_km": "Conventional Light km",
        "light_bev_km": "Light BEV km",
        "phev_km": "PHEV km",
        "total_light_universe_km": "Total light universe km",
        "conventional_share": "Conventional share",
        "light_bev_share": "Light BEV share",
        "phev_share": "PHEV share",
        "share_sum": "Share sum",
        "current_light_total_modelled_km": "Current Light total km",
        "current_conventional_light_km": "Allocated conventional km",
        "current_light_bev_km": "Allocated Light BEV km",
        "current_phev_km": "Allocated PHEV km",
        "current_allocation_sum_km": "Allocation sum km",
        "current_allocation_residual_km": "Allocation residual km",
        "current_light_ruc_net_revenue": "Current Light revenue",
        "current_light_bev_ruc_net_revenue": "Current Light BEV revenue",
        "current_phev_ruc_net_revenue": "Current PHEV revenue",
        "old_light_ruc_net_revenue_no_allocation": "Old no-allocation Light revenue",
        "old_light_bev_ruc_net_revenue_fixed_mbu": "Old fixed Light BEV revenue",
        "old_phev_ruc_net_revenue_fixed_mbu": "Old fixed PHEV revenue",
        "conventional_light_rate_nzd_per_1000km": "Conventional rate NZD/1000km",
        "light_bev_rate_nzd_per_1000km": "Light BEV rate NZD/1000km",
        "phev_rate_nzd_per_1000km": "PHEV rate NZD/1000km",
        "model_input_target_million_km": "Model target million km",
        "target_minus_conventional_light_km": "Target minus conventional",
        "target_minus_total_light_universe_km": "Target minus universe",
        "target_matches_conventional_light": "Target matches conventional",
        "target_matches_total_light_universe": "Target matches universe",
        "target_semantics_status": "Target semantics",
        "business_rule": "Business rule",
        "allocation_status": "Allocation status",
        "used_by_current_finalist": "Used by current finalist",
        "model_input_quarters": "Model input quarters",
        "source_file": "Source file",
        "conventional_light_source_cell": "Conventional source cell",
        "light_bev_source_cell": "Light BEV source cell",
        "phev_source_cell": "PHEV source cell",
        "notes": "Notes",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in [
        "Conventional Light km",
        "Light BEV km",
        "PHEV km",
        "Total light universe km",
        "Current Light total km",
        "Allocated conventional km",
        "Allocated Light BEV km",
        "Allocated PHEV km",
        "Allocation sum km",
        "Allocation residual km",
        "Current Light revenue",
        "Current Light BEV revenue",
        "Current PHEV revenue",
        "Old no-allocation Light revenue",
        "Old fixed Light BEV revenue",
        "Old fixed PHEV revenue",
        "Conventional rate NZD/1000km",
        "Light BEV rate NZD/1000km",
        "PHEV rate NZD/1000km",
        "Model target million km",
        "Target minus conventional",
        "Target minus universe",
    ]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: _format_compact_value(value, ""))
    for col in ["Conventional share", "Light BEV share", "PHEV share"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(
                lambda value: "" if pd.isna(value) else f"{float(value):.4%}"
            )
    return view


def _scenario_role_contract_display_table(contract: pd.DataFrame) -> pd.DataFrame:
    if contract is None or contract.empty:
        return pd.DataFrame()
    view = contract.copy()
    rename = {
        "scenario_name": "Scenario",
        "scenario_role": "Role",
        "affected_series": "Affected series",
        "differing_fields": "Differing fields",
        "population_only_flag": "Population-only",
        "behavioural_driver_flag": "Behavioural driver",
        "display_policy": "Display policy",
        "interpretation": "Interpretation",
        "field_classification": "Field classification",
        "affects_ped_vktpc_directly": "Affects PED VKTpc",
        "affects_bridge_scaling": "Affects bridge scaling",
        "stream_differing_fields": "Stream differing fields",
        "ped_vktpc_direct_fields": "PED VKTpc direct fields",
        "bridge_scaling_fields": "Bridge scaling fields",
        "bridge_only_fields": "Bridge-only fields",
        "unknown_fields": "Unknown fields",
        "runtime_delta_min": "Runtime delta min",
        "runtime_delta_max": "Runtime delta max",
        "ped_population_feature_present": "PED population feature",
        "ped_population_feature_fields": "PED population fields",
        "vktpc_path_policy": "VKTpc path policy",
        "population_path_policy": "Population path policy",
        "source_basis": "Source basis",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in ["Runtime delta min", "Runtime delta max"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: "" if pd.isna(value) else f"{float(value):,.3f}")
    for col in ["Population-only", "Behavioural driver", "Affects PED VKTpc", "Affects bridge scaling", "PED population feature"]:
        if col in view.columns:
            view[col] = view[col].map(lambda value: "Yes" if str(value).strip().lower() in {"true", "1", "yes"} else "No")
    return view


def _ev_phev_ped_light_drift_display_table(drift_assumptions: pd.DataFrame) -> pd.DataFrame:
    if drift_assumptions is None or drift_assumptions.empty:
        return pd.DataFrame()
    view = drift_assumptions.copy()
    rename = {
        "FY": "FY",
        "source_path": "Source path",
        "scenario_name": "Scenario",
        "scenario_role": "Scenario role",
        "lambda_mode": "Lambda mode",
        "lambda_value": "Lambda",
        "lambda_raw_unconstrained": "Raw lambda",
        "lambda_lower_bound": "Lambda lower",
        "lambda_upper_bound": "Lambda upper",
        "lambda_binding_constraints": "Binding constraints",
        "current_P_t_light_petrol_km": "Current P_t petrol km",
        "current_L_t_total_light_ruc_km": "Current L_t Light RUC km",
        "current_U_t_light_mobility_km": "Current U_t universe km",
        "p_PED": "MBU PED prop",
        "p_Lconv": "MBU conventional prop",
        "p_BEV": "MBU BEV prop",
        "p_PHEV": "MBU PHEV prop",
        "target_PED_light_petrol_km": "Target PED petrol km",
        "target_conventional_light_km": "Target conventional km",
        "target_BEV_km": "Target BEV km",
        "target_PHEV_km": "Target PHEV km",
        "smoothed_target_PED_light_petrol_km": "Smoothed PED petrol km",
        "smoothed_target_conventional_light_km": "Smoothed conventional km",
        "smoothed_target_BEV_km": "Smoothed BEV km",
        "smoothed_target_PHEV_km": "Smoothed PHEV km",
        "smoothed_target_EV_total_km": "Smoothed EV/PHEV km",
        "current_PED_light_petrol_km": "Allocated PED petrol km",
        "current_conventional_light_km": "Allocated conventional km",
        "current_BEV_km": "Allocated BEV km",
        "current_PHEV_km": "Allocated PHEV km",
        "component_sum_residual_km": "Universe residual km",
        "ped_prop_residual": "PED prop residual",
        "lconv_prop_residual": "Light prop residual",
        "bev_prop_residual": "BEV prop residual",
        "phev_prop_residual": "PHEV prop residual",
        "weighted_sse": "Weighted SSE",
        "current_PED_revenue": "Current PED revenue",
        "current_light_ruc_net_revenue": "Current Light revenue",
        "current_light_bev_ruc_net_revenue": "Current BEV revenue",
        "current_phev_ruc_net_revenue": "Current PHEV revenue",
        "old_light_only_PED_revenue": "Old light-only PED revenue",
        "old_light_only_light_ruc_net_revenue": "Old light-only Light revenue",
        "old_light_only_light_bev_ruc_net_revenue": "Old light-only BEV revenue",
        "old_light_only_phev_ruc_net_revenue": "Old light-only PHEV revenue",
        "current_migration_revenue_total": "Current migration revenue total",
        "old_light_only_migration_revenue_total": "Old light-only revenue total",
        "migration_revenue_delta": "Migration revenue delta",
        "assumption_status": "Assumption status",
        "source_cells": "Source cells",
        "notes": "Notes",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in [
        "Current P_t petrol km",
        "Current L_t Light RUC km",
        "Current U_t universe km",
        "Target PED petrol km",
        "Target conventional km",
        "Target BEV km",
        "Target PHEV km",
        "Smoothed PED petrol km",
        "Smoothed conventional km",
        "Smoothed BEV km",
        "Smoothed PHEV km",
        "Smoothed EV/PHEV km",
        "Allocated PED petrol km",
        "Allocated conventional km",
        "Allocated BEV km",
        "Allocated PHEV km",
        "Universe residual km",
        "Weighted SSE",
        "Current PED revenue",
        "Current Light revenue",
        "Current BEV revenue",
        "Current PHEV revenue",
        "Old light-only PED revenue",
        "Old light-only Light revenue",
        "Old light-only BEV revenue",
        "Old light-only PHEV revenue",
        "Current migration revenue total",
        "Old light-only revenue total",
        "Migration revenue delta",
    ]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: _format_compact_value(value, ""))
    for col in [
        "Lambda",
        "Raw lambda",
        "Lambda lower",
        "Lambda upper",
        "MBU PED prop",
        "MBU conventional prop",
        "MBU BEV prop",
        "MBU PHEV prop",
        "PED prop residual",
        "Light prop residual",
        "BEV prop residual",
        "PHEV prop residual",
    ]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
    return view


def _revenue_line_section_options(line_reconciliation: pd.DataFrame) -> list[str]:
    if line_reconciliation is None or line_reconciliation.empty or "section" not in line_reconciliation.columns:
        return ["Key volumes", "RUC", "FED", "MVR", "TUC", "Totals"]
    values = [value for value in line_reconciliation["section"].dropna().astype(str).unique().tolist() if value]
    preferred = ["Key volumes", "RUC", "FED", "MVR", "TUC", "Totals"]
    ordered = [value for value in preferred if value in values]
    ordered.extend(sorted(set(values).difference(ordered)))
    return ordered or preferred


def _revenue_line_fy_bounds(line_reconciliation: pd.DataFrame) -> tuple[int, int]:
    if line_reconciliation is None or line_reconciliation.empty or "FY" not in line_reconciliation.columns:
        return 2024, 2027
    years = pd.to_numeric(line_reconciliation["FY"], errors="coerce").dropna().astype(int)
    if years.empty:
        return 2024, 2027
    return int(years.min()), int(years.max())


def _filter_revenue_line_reconciliation(
    line_reconciliation: pd.DataFrame,
    *,
    source_paths: list[str],
    sections: list[str],
    fy_range: tuple[int, int] | list[int],
) -> pd.DataFrame:
    if line_reconciliation is None or line_reconciliation.empty:
        return pd.DataFrame()
    data = line_reconciliation.copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce").astype("Int64")
    if source_paths and "source_path" in data.columns:
        data = data[data["source_path"].astype(str).isin(source_paths)].copy()
    if sections and "section" in data.columns:
        data = data[data["section"].astype(str).isin(sections)].copy()
    try:
        low, high = int(fy_range[0]), int(fy_range[1])
    except Exception:
        low, high = _revenue_line_fy_bounds(data)
    data = data[data["FY_numeric"].between(low, high, inclusive="both")].copy()
    return data.drop(columns=["FY_numeric"], errors="ignore")


def _revenue_line_reconciliation_display_table(line_reconciliation: pd.DataFrame) -> pd.DataFrame:
    if line_reconciliation is None or line_reconciliation.empty:
        return pd.DataFrame()
    view = line_reconciliation.copy()
    rename = {
        "source_path": "Source path",
        "period": "FY",
        "section": "Section",
        "line_label": "Line",
        "value": "Value",
        "unit": "Unit",
        "row_role": "Row role",
        "source_file": "Source file",
        "source_cell": "Source cell/formula",
        "formula": "Formula",
        "model_id": "Model ID",
        "quarter_composition": "Quarter composition",
        "replacement_flag": "Replacement",
        "residual_vs_official": "Residual vs official",
        "availability_status": "Status",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    if "Value" in view.columns:
        view["Value"] = pd.to_numeric(view["Value"], errors="coerce").map(lambda value: _format_compact_value(value, ""))
    if "Residual vs official" in view.columns:
        view["Residual vs official"] = pd.to_numeric(view["Residual vs official"], errors="coerce").map(lambda value: _format_compact_value(value, ""))
    return view


def _revenue_series_alias_audit_display_table(alias_audit: pd.DataFrame) -> pd.DataFrame:
    if alias_audit is None or alias_audit.empty:
        return pd.DataFrame()
    view = alias_audit.copy()
    rename = {
        "source_label": "Source label",
        "source_series_id": "Source series ID",
        "runtime_series_id": "Runtime series ID",
        "dashboard_label": "Dashboard label",
        "unit": "Unit",
        "source_row": "Source row",
        "source_cell": "Source cell",
        "alias_reason": "Alias reason",
        "status": "Status",
    }
    cols = [col for col in rename if col in view.columns]
    return view[cols].rename(columns=rename)


def _revenue_formula_gap_banner(
    formula_residuals: pd.DataFrame,
    source_paths: list[str],
    fy_range: tuple[int, int] | list[int],
) -> str:
    if formula_residuals is None or formula_residuals.empty:
        return ""
    data = formula_residuals.copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce").astype("Int64")
    if source_paths and "source_path" in data.columns:
        data = data[data["source_path"].astype(str).isin(source_paths)].copy()
    if "source_path" in data.columns:
        data = data[data["source_path"].astype(str).str.startswith("Current finalist")].copy()
    try:
        low, high = int(fy_range[0]), int(fy_range[1])
    except Exception:
        low, high = _revenue_line_fy_bounds(data)
    data = data[data["FY_numeric"].between(low, high, inclusive="both")].copy()
    gaps = data[~data.get("status", pd.Series("", index=data.index)).astype(str).eq("reconciled")].copy()
    if gaps.empty:
        return ""
    first = gaps.iloc[0]
    return (
        "Governed gap: one or more selected revenue aggregates fail formula reconciliation. "
        f"First gap: {first.get('source_path')} {first.get('period')} {first.get('output_label')} "
        f"status={first.get('status')}."
    )


def _revenue_outlook_manifest_table(manifest: dict[str, Any]) -> pd.DataFrame:
    if not isinstance(manifest, dict) or not manifest:
        return pd.DataFrame()
    rows = [
        ("Schema", manifest.get("schema_version")),
        ("Pack status", manifest.get("pack_status")),
        ("Promotion time", manifest.get("promotion_time")),
        ("Source policy", manifest.get("source_policy")),
        ("Output folder", manifest.get("repo_relative_output_dir")),
    ]
    source = manifest.get("source_comparison", {}) if isinstance(manifest.get("source_comparison"), dict) else {}
    rows.append(("Comparison ID", source.get("comparison_id")))
    role_validation = source.get("scenario_role_validation", {})
    if isinstance(role_validation, dict):
        rows.append(("Scenario role validation", role_validation.get("status")))
    source_pack = manifest.get("revenue_source_pack", {})
    if isinstance(source_pack, dict) and source_pack:
        dashboard_defaults = source_pack.get("dashboard_default_selections") or source_pack.get("selections") or {}
        workbook_selections = source_pack.get("source_workbook_selections") or {}
        rows.extend(
            [
                ("Revenue source pack", source_pack.get("source_pack_version")),
                ("Revenue source status", source_pack.get("status")),
                ("Revenue source path", source_pack.get("repo_relative_path")),
                ("Raw workbook SHA256", source_pack.get("raw_workbook_sha256")),
                ("Source pack manifest SHA256", source_pack.get("source_pack_manifest_sha256")),
                ("Dashboard default series", dashboard_defaults.get("series") if isinstance(dashboard_defaults, dict) else ""),
                ("Workbook current series", workbook_selections.get("series") if isinstance(workbook_selections, dict) else ""),
                ("Default selection policy", source_pack.get("default_selection_policy")),
            ]
        )
    bridge_statuses = manifest.get("bridge_status_by_stream", {})
    if isinstance(bridge_statuses, dict):
        for stream, statuses in sorted(bridge_statuses.items()):
            if isinstance(statuses, list):
                status_text = ", ".join(str(status) for status in statuses)
            else:
                status_text = str(statuses)
            rows.append((f"Bridge status: {STREAM_LABELS.get(str(stream), str(stream))}", status_text))
    output_hashes = manifest.get("output_hashes", {})
    if isinstance(output_hashes, dict):
        for filename, metadata in sorted(output_hashes.items()):
            sha = str(metadata.get("sha256", "")) if isinstance(metadata, dict) else ""
            if sha:
                rows.append((f"Output SHA256: {filename}", sha))
    return pd.DataFrame([{"Field": label, "Value": value} for label, value in rows])


def _revenue_outlook_gap_summary(bridge: pd.DataFrame) -> str:
    if bridge is None or bridge.empty or "bridge_status" not in bridge.columns:
        return ""
    statuses = bridge["bridge_status"].fillna("").astype(str)
    gap_rows = bridge[~statuses.isin(["available", ""])].copy()
    if gap_rows.empty:
        return ""
    summary = (
        gap_rows.groupby(["stream_label", "bridge_status"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["stream_label", "bridge_status"], kind="stable")
    )
    parts = [f"{row['stream_label']}: {row['bridge_status']} ({int(row['rows'])} rows)" for _, row in summary.iterrows()]
    return "Revenue bridge governed gaps remain visible: " + "; ".join(parts[:6]) + ("." if len(parts) <= 6 else "; ...")


def _latest_period(rows: pd.DataFrame, *, row_type: str) -> str:
    if rows is None or rows.empty:
        return ""
    data = rows[rows["row_type"].astype(str).eq(row_type)].copy()
    if data.empty:
        return ""
    data["_period_order"] = data["period"].map(_revenue_period_order)
    return str(data.sort_values("_period_order").iloc[-1]["period"])


def _first_period(rows: pd.DataFrame, *, row_type: str) -> str:
    if rows is None or rows.empty:
        return ""
    data = rows[rows["row_type"].astype(str).eq(row_type)].copy()
    if data.empty:
        return ""
    data["_period_order"] = data["period"].map(_revenue_period_order)
    return str(data.sort_values("_period_order").iloc[0]["period"])


def _fy5_revenue_value(rows: pd.DataFrame) -> tuple[Any, str]:
    if rows is None or rows.empty:
        return pd.NA, ""
    data = rows[
        rows["metric_type"].astype(str).eq("revenue")
        & rows["time_grain"].astype(str).eq("june_year")
        & rows["row_type"].astype(str).eq("future_forecast")
    ].copy()
    if "series_id" in data.columns and data["series_id"].astype(str).eq("total_nltf_net_revenue").any():
        data = data[data["series_id"].astype(str).eq("total_nltf_net_revenue")].copy()
    if "fed_path" in data.columns and data["fed_path"].astype(str).eq("Current planned path").any():
        data = data[data["fed_path"].astype(str).eq("Current planned path")].copy()
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return pd.NA, ""
    periods = sorted(data["period"].dropna().astype(str).unique().tolist(), key=_revenue_period_order)
    target_period = periods[min(4, len(periods) - 1)]
    base = data[data.get("scenario_role", pd.Series(dtype=str)).astype(str).eq(SCENARIO_ROLE_BASECASE)]
    chosen = base[base["period"].astype(str).eq(target_period)] if not base.empty else data[data["period"].astype(str).eq(target_period)]
    value = float(chosen["value_numeric"].iloc[0]) if len(chosen) == 1 else (float(chosen["value_numeric"].sum()) if not chosen.empty else pd.NA)
    return value, target_period


def _comparison_delta_value(rows: pd.DataFrame) -> tuple[Any, str]:
    if rows is None or rows.empty:
        return pd.NA, ""
    data = rows[
        rows["metric_type"].astype(str).eq("revenue")
        & rows["time_grain"].astype(str).eq("june_year")
        & rows["row_type"].astype(str).eq("future_forecast")
    ].copy()
    if "series_id" in data.columns and data["series_id"].astype(str).eq("total_nltf_net_revenue").any():
        data = data[data["series_id"].astype(str).eq("total_nltf_net_revenue")].copy()
    if "fed_path" in data.columns and data["fed_path"].astype(str).eq("Current planned path").any():
        data = data[data["fed_path"].astype(str).eq("Current planned path")].copy()
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty or "scenario_role" not in data.columns:
        return pd.NA, ""
    pivot = (
        data.groupby(["period", "scenario_role"], dropna=False)["value_numeric"]
        .sum()
        .unstack("scenario_role")
        .reset_index()
    )
    if SCENARIO_ROLE_BASECASE not in pivot.columns or SCENARIO_ROLE_COMPARISON not in pivot.columns:
        return pd.NA, ""
    pivot["_period_order"] = pivot["period"].map(_revenue_period_order)
    pivot = pivot[pivot[SCENARIO_ROLE_BASECASE].notna() & pivot[SCENARIO_ROLE_COMPARISON].notna()].sort_values("_period_order")
    if pivot.empty:
        return pd.NA, ""
    row = pivot.iloc[-1]
    return float(row[SCENARIO_ROLE_COMPARISON] - row[SCENARIO_ROLE_BASECASE]), str(row["period"])


def _future_gap_count(future_revenue: pd.DataFrame) -> int:
    if future_revenue is None or future_revenue.empty or "bridge_status" not in future_revenue.columns:
        return 0
    statuses = future_revenue["bridge_status"].fillna("").astype(str)
    return int((~statuses.isin(["available", ""])).sum())


def _revenue_period_order(period: Any) -> int:
    text = str(period).strip().upper()
    if text.startswith("FY"):
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) * 4 + 2 if digits else 999999
    return quarter_sort_key(text)


def _format_compact_value(value: Any, unit: str) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    number = float(number)
    prefix = "$" if unit == "nominal NZD" else ""
    abs_value = abs(number)
    if abs_value >= 1_000_000_000:
        return f"{prefix}{number / 1_000_000_000:.2f}b"
    if abs_value >= 1_000_000:
        return f"{prefix}{number / 1_000_000:.1f}m"
    if abs_value >= 1_000:
        return f"{prefix}{number / 1_000:.1f}k"
    return f"{prefix}{number:,.2f}"


def _format_signed_compact(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    sign = "+" if float(number) >= 0 else ""
    return sign + _format_compact_value(number, "nominal NZD")


def _first_non_empty(values: Any) -> str:
    try:
        iterator = values.dropna().astype(str).tolist()
    except Exception:
        iterator = [str(values)] if values is not None else []
    for value in iterator:
        text = str(value).strip()
        if text and text.lower() not in {"nan", "<na>"}:
            return text
    return ""


def _short_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("T", " ").replace("+00:00", " UTC")[:22]


def render_governance_reproducibility_page(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    del controls
    inject_page5_theme()

    pack_labels = reproducibility_stream_labels()
    loaded_packs = {label: _load_reproducibility_pack_safely(label) for label in pack_labels}
    ped_inner_hpo_pack = _load_ped_inner_hpo_pack_safely()
    available_count = sum(1 for pack in loaded_packs.values() if pack is not None and pack.available)
    workbook_manifest = source_workbook_manifest()
    chart_source_count = len(list((Path(__file__).resolve().parent / "artifacts" / "chart_sources").glob("*.csv")))

    selected_stream = render_page5_filter_strip(loaded_packs, workbook_manifest)
    panel_contract = page5_panel_contract_frame()

    render_page5_top_status_cards(
        available_count=available_count,
        total_count=len(pack_labels),
        workbook_manifest=workbook_manifest,
        chart_source_count=chart_source_count,
    )
    render_page5_reproducibility_status_cards(selected_stream, loaded_packs, ped_inner_hpo_pack)

    analytics_pack = page5_analytics_pack(selected_stream, loaded_packs)
    analytics_stream = analytics_pack.stream_label if analytics_pack is not None else "Light RUC volume"

    render_page5_story_row(selected_stream, loaded_packs, ped_inner_hpo_pack)
    render_page5_lower_panels(
        analytics_stream,
        analytics_pack,
        selected_stream,
        loaded,
        loaded_packs,
        workbook_manifest,
        panel_contract,
    )
    render_page5_shap_note()
    render_forecast_builder_section()


def _load_reproducibility_pack_safely(stream_label: str) -> Any | None:
    try:
        return cached_load_reproducibility_pack(stream_label, reproducibility_pack_signature(stream_label))
    except Exception as exc:
        warning_panel(f"{stream_label} reproducibility audit pack could not be loaded: {exc}")
        return None


def _load_ped_inner_hpo_pack_safely() -> Any | None:
    try:
        return cached_load_ped_inner_hpo_audit_pack(ped_inner_hpo_audit_signature())
    except Exception as exc:
        warning_panel(f"PED inner HPO/static-solver audit pack could not be loaded: {exc}")
        return None


def inject_global_theme() -> None:
    """App-wide layout robustness: filter rows wrap instead of crushing on
    narrow screens, navigation wraps cleanly, and cards keep their borders."""
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.1rem; }
        div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 0.45rem; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            min-width: 150px;
            flex: 1 1 150px;
        }
        div[role="radiogroup"] { flex-wrap: wrap; row-gap: 0.3rem; }
        div[data-testid="stPlotlyChart"] { overflow: hidden; border-radius: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_page5_theme() -> None:
    st.markdown(
        """
        <style>
        .page5-filter-shell {
            background:#FFFFFF;
            border:1px solid #D9E2EC;
            border-radius:8px;
            box-shadow:0 8px 20px rgba(15,23,42,0.05);
            margin:0.18rem 0 0.62rem;
            padding:0.56rem 0.72rem 0.68rem;
        }
        .page5-filter-title {
            color:#002B5C;
            font-size:0.68rem;
            font-weight:850;
            letter-spacing:0.03em;
            margin:0 0 0.34rem;
            text-transform:uppercase;
        }
        .page5-mini-card, .page5-status-card, .page5-panel, .page5-flow-step, .page5-download-row {
            background:#FFFFFF;
            border:1px solid #D9E2EC;
            border-radius:8px;
            box-shadow:0 8px 18px rgba(15,23,42,0.045);
        }
        .page5-mini-card {
            min-height:54px;
            padding:0.46rem 0.58rem;
        }
        .page5-mini-kicker, .page5-field-label {
            color:#002B5C;
            font-size:0.72rem;
            font-weight:850;
            line-height:1.2;
        }
        .page5-mini-value {
            color:#102A43;
            font-size:0.72rem;
            font-weight:700;
            line-height:1.25;
            margin-top:0.08rem;
        }
        .page5-mini-sub {
            color:#64748B;
            font-size:0.62rem;
            line-height:1.15;
            margin-top:0.04rem;
        }
        .page5-status-grid, .page5-kpi-grid {
            display:grid;
            gap:0.34rem;
            grid-template-columns:repeat(4,minmax(0,1fr));
            margin:0.32rem 0 0.34rem;
        }
        .page5-status-card {
            min-height:154px;
            padding:0.5rem 0.62rem;
        }
        .page5-status-head {
            align-items:center;
            display:flex;
            gap:0.34rem;
            margin-bottom:0.32rem;
        }
        .page5-status-icon {
            align-items:center;
            background:#00843D;
            border-radius:999px;
            color:#FFFFFF;
            display:flex;
            font-size:0.64rem;
            font-weight:850;
            height:1.2rem;
            justify-content:center;
            width:1.2rem;
        }
        .page5-status-title {
            color:#002B5C;
            font-size:0.78rem;
            font-weight:850;
            line-height:1.1;
        }
        .page5-metric-row {
            display:grid;
            gap:0.38rem;
            grid-template-columns:0.82fr 1.72fr;
            margin:0.08rem 0;
        }
        .page5-metric-label {
            color:#1F3B57;
            font-size:0.6rem;
            font-weight:800;
        }
        .page5-metric-value {
            color:#102A43;
            font-size:0.6rem;
            line-height:1.12;
        }
        .page5-good { color:#00843D; font-weight:850; }
        .page5-watch { color:#B7791F; font-weight:850; }
        .page5-flow-grid {
            align-items:stretch;
            display:grid;
            gap:0.32rem;
            grid-template-columns:repeat(7,minmax(0,1fr));
            margin:0.18rem 0 0.28rem;
        }
        .page5-flow-step {
            min-height:78px;
            padding:0.38rem 0.44rem;
            position:relative;
        }
        .page5-flow-step:not(:last-child)::after {
            color:#64748B;
            content:"\\2192";
            font-size:0.86rem;
            font-weight:850;
            position:absolute;
            right:-0.28rem;
            top:0.42rem;
            z-index:2;
        }
        .page5-flow-number {
            align-items:center;
            background:#002B5C;
            border-radius:999px;
            color:#FFFFFF;
            display:flex;
            font-size:0.54rem;
            font-weight:850;
            height:0.96rem;
            justify-content:center;
            margin-bottom:0.22rem;
            width:0.96rem;
        }
        .page5-flow-title {
            color:#002B5C;
            font-size:0.64rem;
            font-weight:850;
            margin-bottom:0.12rem;
        }
        .page5-flow-copy {
            color:#34495E;
            font-size:0.56rem;
            line-height:1.12;
        }
        .page5-chip-grid {
            display:flex;
            flex-wrap:wrap;
            gap:0.22rem;
            margin:0.18rem 0 0.34rem;
        }
        .page5-chip {
            background:#F3F6FB;
            border:1px solid #D9E2EC;
            border-radius:6px;
            color:#102A43;
            display:inline-flex;
            gap:0.22rem;
            max-width:205px;
            padding:0.22rem 0.32rem;
        }
        .page5-chip-term {
            color:#002B5C;
            font-size:0.56rem;
            font-weight:850;
            white-space:nowrap;
        }
        .page5-chip-def {
            color:#64748B;
            font-size:0.54rem;
            line-height:1.05;
        }
        .page5-panel {
            min-height:220px;
            padding:0.66rem 0.72rem;
        }
        .page5-trace-panel {
            min-height:248px;
        }
        .page5-panel-title {
            color:#002B5C;
            font-size:0.84rem;
            font-weight:850;
            line-height:1.15;
            margin-bottom:0.08rem;
        }
        .page5-panel-sub {
            color:#64748B;
            font-size:0.66rem;
            line-height:1.2;
            margin-bottom:0.42rem;
        }
        .page5-diagram-row {
            align-items:center;
            border-bottom:1px solid #E6EDF5;
            display:grid;
            gap:0.36rem;
            grid-template-columns:92px 1fr;
            padding:0.52rem 0;
        }
        .page5-diagram-row:last-child { border-bottom:0; }
        .page5-diagram-label {
            color:#002B5C;
            font-size:0.76rem;
            font-weight:850;
        }
        .page5-diagram-chain {
            align-items:center;
            display:flex;
            flex-wrap:wrap;
            gap:0.34rem;
        }
        .page5-node {
            background:#F3F6FB;
            border:1px solid #C7D7EA;
            border-radius:6px;
            color:#102A43;
            font-size:0.64rem;
            font-weight:700;
            line-height:1.15;
            min-width:88px;
            padding:0.38rem 0.46rem;
            text-align:center;
        }
        .page5-node.green { background:#EAF7EF; border-color:#B8E0C8; }
        .page5-node.blue { background:#EAF2F8; border-color:#BFD3E6; }
        .page5-node.purple { background:#F1ECF7; border-color:#D8C8EA; }
        .page5-op {
            color:#102A43;
            font-size:1.04rem;
            font-weight:800;
        }
        .page5-download-list {
            display:flex;
            flex-direction:column;
            gap:0.2rem;
            margin-top:0.16rem;
        }
        .page5-download-row {
            align-items:center;
            display:grid;
            gap:0.35rem;
            grid-template-columns:1fr auto;
            padding:0.32rem 0.44rem;
        }
        .page5-caveat-card {
            background:#FFF7ED;
            border:1px solid rgba(234,88,12,0.24);
            border-left:5px solid #F97316;
            border-radius:8px;
            box-shadow:0 8px 18px rgba(15,23,42,0.045);
            min-height:255px;
            padding:0.72rem 0.8rem;
        }
        .page5-caveat-kicker {
            color:#9A3412;
            font-size:0.66rem;
            font-weight:850;
            letter-spacing:0.02em;
            text-transform:uppercase;
        }
        .page5-caveat-title {
            color:#002B5C;
            font-size:0.86rem;
            font-weight:850;
            line-height:1.18;
            margin-top:0.18rem;
        }
        .page5-caveat-copy {
            color:#7C2D12;
            font-size:0.74rem;
            font-weight:650;
            line-height:1.32;
            margin-top:0.62rem;
        }
        .page5-caveat-note {
            background:rgba(255,255,255,0.72);
            border:1px solid rgba(234,88,12,0.18);
            border-radius:7px;
            color:#334155;
            font-size:0.68rem;
            line-height:1.32;
            margin-top:0.7rem;
            padding:0.46rem 0.52rem;
        }
        .page5-download-name {
            color:#102A43;
            font-size:0.68rem;
            font-weight:700;
        }
        .page5-download-size {
            color:#64748B;
            font-size:0.64rem;
        }
        .page5-shap-note {
            align-items:center;
            background:#EAF2F8;
            border:1px solid #D9E2EC;
            border-radius:8px;
            color:#102A43;
            display:flex;
            font-size:0.78rem;
            gap:0.55rem;
            margin:0.42rem 0;
            padding:0.5rem 0.76rem;
        }
        .page5-footer {
            align-items:center;
            background:#002B5C;
            border-radius:8px;
            color:#FFFFFF;
            display:grid;
            gap:0.8rem;
            grid-template-columns:1fr auto auto;
            margin:0.48rem 0 0.18rem;
            padding:0.78rem 0.92rem;
        }
        .page5-footer-main {
            font-size:0.86rem;
            font-weight:750;
        }
        .page5-footer-meta {
            font-size:0.72rem;
            opacity:0.9;
            white-space:nowrap;
        }
        @media (max-width: 1200px) {
            .page5-status-grid, .page5-kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .page5-flow-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .page5-flow-step:not(:last-child)::after { display:none; }
            .page5-footer { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page5_filter_strip(
    loaded_packs: dict[str, Any | None],
    workbook_manifest: dict[str, Any],
) -> str:
    if st.session_state.pop("page5_reset_requested", False):
        for key in ("page5_stream_segment", "page5_pack_selector"):
            st.session_state.pop(key, None)
    stream_map = {
        "All streams": "All streams",
        "PED": "PED VKT per capita",
        "Light RUC": "Light RUC volume",
        "Heavy RUC": "Heavy RUC volume",
    }
    with st.container(border=True):
        st.markdown("<div class='page5-filter-title'>Governance & Reproducibility Filters</div>", unsafe_allow_html=True)
        cols = st.columns([1.45, 0.88, 1.05, 1.0, 0.58, 0.66])
        with cols[0]:
            selected_short = st.segmented_control(
                "Stream",
                list(stream_map),
                default="All streams",
                key="page5_stream_segment",
            )
        with cols[1]:
            st.selectbox(
                "Reproducibility pack",
                ["v1.3.0 (Latest)", "Bundled page pack"],
                key="page5_pack_selector",
                help="Read-only stream replay packs loaded from data/dashboard_evidence_pack_reproducibility.",
            )
        with cols[2]:
            st.markdown(page5_workbook_card_html(workbook_manifest), unsafe_allow_html=True)
        with cols[3]:
            st.markdown(
                page5_mini_card_html(
                    "Read-only",
                    "This page is read-only",
                    "No inputs or edits are permitted",
                    icon="LOCK",
                ),
                unsafe_allow_html=True,
            )
        with cols[4]:
            st.button(
                "Reset Filters",
                key="page5_reset_filters",
                use_container_width=True,
                on_click=lambda: st.session_state.__setitem__("page5_reset_requested", True),
            )
        with cols[5]:
            with st.popover("Exports", use_container_width=True):
                render_page5_download_buttons(
                    stream_map.get(str(selected_short or "All streams"), "All streams"),
                    loaded_packs,
                    workbook_manifest,
                    key_prefix="popover",
                )
    return stream_map.get(str(selected_short or "All streams"), "All streams")


def render_page5_top_status_cards(
    *,
    available_count: int,
    total_count: int,
    workbook_manifest: dict[str, Any],
    chart_source_count: int,
) -> None:
    cards = [
        ("Repro packs loaded", f"{available_count}/{total_count}", "PED, Light RUC and Heavy RUC packs", "read-only", "R"),
        (
            "Workbook provenance",
            "available" if workbook_manifest.get("available") else "missing",
            str(workbook_manifest.get("status_label", "optional source workbook not found")),
            "optional source",
            "W",
        ),
        ("Chart-source isolation", "untouched", f"{chart_source_count} main chart-source CSVs guarded", "no writes", "C"),
        ("Page role", "Audit trail", "explainability only, not scoring input", "read-only", "A"),
    ]
    html_cards = [
        "<div class='page5-mini-card'>"
        f"<div class='page5-mini-kicker'>{html.escape(icon)} &nbsp; {html.escape(title)}</div>"
        f"<div class='page5-mini-value'>{html.escape(value)}</div>"
        f"<div class='page5-mini-sub'>{html.escape(subtext)}</div>"
        f"<div class='page5-good'>{html.escape(delta)}</div>"
        "</div>"
        for title, value, subtext, delta, icon in cards
    ]
    st.markdown("<div class='page5-kpi-grid'>" + "".join(html_cards) + "</div>", unsafe_allow_html=True)


def render_page5_reproducibility_status_cards(
    selected_stream: str,
    loaded_packs: dict[str, Any | None],
    ped_inner_hpo_pack: Any | None,
) -> None:
    labels = list(loaded_packs) if selected_stream == "All streams" else [selected_stream]
    cards = [page5_repro_card_html(label, loaded_packs.get(label), ped_inner_hpo_pack) for label in labels]
    cards.append(
        "<div class='page5-status-card'>"
        "<div class='page5-status-head'><div class='page5-status-icon' style='background:#002B5C;'>DB</div>"
        "<div class='page5-status-title'>Missing data behaviour</div></div>"
        "<div class='page5-metric-value'>When required inputs or model packs are missing, they are shown as a clear missing-data card rather than an error.</div>"
        "<div style='margin-top:1rem;' class='page5-good'>All required packs are present</div>"
        "</div>"
    )
    st.markdown("<div class='page5-status-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def page5_repro_card_html(stream_label: str, pack: Any | None, ped_inner_hpo_pack: Any | None = None) -> str:
    if pack is None or not getattr(pack, "available", False):
        missing = ", ".join(getattr(pack, "missing_files", ())[:5]) if pack is not None else "pack load failed"
        return (
            "<div class='page5-status-card'>"
            "<div class='page5-status-head'><div class='page5-status-icon' style='background:#F37021;'>!</div>"
            f"<div class='page5-status-title'>{html.escape(stream_label)}</div></div>"
            f"<div class='page5-metric-value'>Missing reproducibility pack: {html.escape(missing or 'required audit files missing')}</div>"
            "</div>"
        )
    summary = reproducibility_replay_summary(pack)
    delta = pd.to_numeric(pd.Series([summary.get("max_abs_pred_delta")]), errors="coerce").iloc[0]
    delta_text = "0" if pd.notna(delta) and abs(float(delta)) == 0 else (f"{delta:.2e}" if pd.notna(delta) else "-")
    replay_note = str(summary.get("description") or stream_repro_description(stream_label))
    rows = [
        ("Reproducibility status", str(summary.get("status", "-"))),
        ("Replay note", replay_note),
        ("Model approach", stream_repro_approach(stream_label)),
        ("Model", str(summary.get("model", "-"))),
        ("Max prediction delta", delta_text),
        ("Score basis", "Paper-style horizon MAPE"),
        ("Workbook + sheet", f"{summary.get('workbook', '-')} > {summary.get('source_sheet', '-')}"),
        ("Caveat", stream_repro_caveat(stream_label)),
    ]
    if stream_label == "PED VKT per capita":
        rows.extend(page5_ped_inner_status_rows(ped_inner_hpo_pack))
    return (
        "<div class='page5-status-card'>"
        "<div class='page5-status-head'><div class='page5-status-icon'>OK</div>"
        f"<div class='page5-status-title'>{html.escape(stream_label)}</div></div>"
        + "".join(
            "<div class='page5-metric-row'>"
            f"<div class='page5-metric-label'>{html.escape(label)}</div>"
            f"<div class='page5-metric-value'>{html.escape(value)}</div>"
            "</div>"
            for label, value in rows
        )
        + "</div>"
    )


def page5_ped_inner_status_rows(ped_inner_hpo_pack: Any | None) -> list[tuple[str, str]]:
    if ped_inner_hpo_pack is None or not getattr(ped_inner_hpo_pack, "available", False):
        missing_files = list(getattr(ped_inner_hpo_pack, "missing_files", ())) if ped_inner_hpo_pack is not None else []
        priority_missing = [
            name
            for name in (
                "manifest.json",
                "parquet_write_status.json",
                "model_registry.parquet",
                "source_artifacts_manifest.json",
            )
            if name in missing_files
        ]
        missing = ", ".join(priority_missing or missing_files[:4]) if ped_inner_hpo_pack is not None else "pack load failed"
        return [
            ("Inner audit status", "Missing PED inner HPO/static-solver audit pack"),
            ("Inner audit evidence", missing or "required audit files missing"),
        ]
    summary = ped_inner_hpo_audit_summary(ped_inner_hpo_pack)
    inner_delta = pd.to_numeric(pd.Series([summary.get("inner_max_abs_delta")]), errors="coerce").iloc[0]
    inner_delta_text = f"{inner_delta:.2e}" if pd.notna(inner_delta) else "-"
    return [
        ("Legacy inner audit (archived)", str(summary.get("inner_status", PED_INNER_HPO_AUDIT_STATUS))),
        ("Legacy inner replay delta", inner_delta_text),
    ]


def render_page5_build_flow(selected_stream: str) -> None:
    steps = page5_build_flow_steps(selected_stream)
    cards = []
    for idx, (step, text) in enumerate(steps, start=1):
        cards.append(
            "<div class='page5-flow-step'>"
            f"<div class='page5-flow-number'>{idx}</div>"
            f"<div class='page5-flow-title'>{html.escape(step)}</div>"
            f"<div class='page5-flow-copy'>{html.escape(text)}</div>"
            "</div>"
        )
    st.markdown("<div class='page5-panel-title'>How the model is built</div>", unsafe_allow_html=True)
    st.markdown("<div class='page5-flow-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def render_page5_glossary() -> None:
    glossary = reproducibility_glossary_table()
    chips = []
    for _, row in glossary.iterrows():
        chips.append(
            "<div class='page5-chip'>"
            f"<div class='page5-chip-term'>{html.escape(str(row['Term']))}</div>"
            f"<div class='page5-chip-def'>{html.escape(str(row['Meaning']))}</div>"
            "</div>"
        )
    st.markdown("<div class='page5-panel-title'>Model glossary</div>", unsafe_allow_html=True)
    st.markdown("<div class='page5-chip-grid'>" + "".join(chips) + "</div>", unsafe_allow_html=True)


def render_page5_story_row(
    selected_stream: str,
    loaded_packs: dict[str, Any | None],
    ped_inner_hpo_pack: Any | None = None,
) -> None:
    selected_packs = page5_selected_packs(selected_stream, loaded_packs)
    cols = st.columns([1.28, 0.78, 1.12])
    with cols[0]:
        render_page5_build_flow(selected_stream)
        render_page5_glossary()
    with cols[1]:
        with st.container(border=True):
            st.markdown(
                "<div class='page5-panel-title'>Registry <span class='page5-panel-sub'>(model_registry.parquet)</span></div>",
                unsafe_allow_html=True,
            )
            registry = page5_registry_frame(selected_packs)
            display_table(registry, height=218, max_rows=8)
    with cols[2]:
        st.markdown(
            "<div class='page5-panel page5-trace-panel'>"
            "<div class='page5-panel-title'>Component trace <span class='page5-panel-sub'>(how predictions are composed)</span></div>"
            f"{page5_component_diagram_html(selected_packs)}"
            "</div>",
            unsafe_allow_html=True,
        )
    if selected_stream == "PED VKT per capita":
        render_page5_ped_inner_hpo_audit_panel(ped_inner_hpo_pack)


def render_page5_ped_inner_hpo_audit_panel(ped_inner_hpo_pack: Any | None) -> None:
    st.markdown(
        "<div class='page5-panel-title'>PED inner HPO/static-solver audit</div>"
        "<div class='page5-panel-sub'>Read-only auxiliary governance evidence from ped_inner_hpo.</div>",
        unsafe_allow_html=True,
    )
    if ped_inner_hpo_pack is None or not getattr(ped_inner_hpo_pack, "available", False):
        missing = ", ".join(getattr(ped_inner_hpo_pack, "missing_files", ())[:8]) if ped_inner_hpo_pack is not None else "pack load failed"
        render_page5_missing_panel(
            "PED inner HPO/static-solver audit",
            (
                "Missing PED inner HPO/static-solver audit pack. "
                f"Expected read-only files under data/dashboard_evidence_pack_reproducibility/ped_inner_hpo. "
                f"Missing: {missing or 'required audit tables'}."
            ),
            "PED is exact at stored component-prediction level; inner HPO/static-solver rebuild remains a future audit layer.",
        )
        return

    summary = ped_inner_hpo_audit_summary(ped_inner_hpo_pack)
    outer_delta = pd.to_numeric(pd.Series([summary.get("outer_max_abs_delta")]), errors="coerce").iloc[0]
    inner_delta = pd.to_numeric(pd.Series([summary.get("inner_max_abs_delta")]), errors="coerce").iloc[0]
    outer_delta_text = "0" if pd.notna(outer_delta) and abs(float(outer_delta)) == 0 else (f"{outer_delta:.2e}" if pd.notna(outer_delta) else "-")
    inner_delta_text = f"{inner_delta:.2e}" if pd.notna(inner_delta) else "-"
    kpi_grid(
        [
            ("Main status", str(summary.get("outer_status")), f"max delta {outer_delta_text}"),
            ("Inner audit status", str(summary.get("inner_status")), f"nested max delta {inner_delta_text}"),
            ("Weight sources", f"{summary.get('weight_source_count', 0)} vendored source groups", "HPO and arbitration rows are grouped separately"),
            ("Source artifacts", str(summary.get("source_artifact_status", "source artifacts vendored in repo")), "repo-relative paths and SHA256 hashes"),
            ("Pack role", "Auxiliary governance", "read-only; does not feed main calculations"),
        ]
    )
    info_panel("PED is exact at stored component-prediction level; inner HPO/static-solver rebuild remains a future audit layer.")
    info_panel(str(summary.get("description", "")))
    info_panel(
        "Source artifacts vendored in repo. PED training-fit R2 was reconstructed from repo-vendored "
        "finalist-arbitration source script, HPO refinement weights, and compact arbitration lineage artifacts."
    )

    artifacts = ped_inner_hpo_source_artifacts_view(ped_inner_hpo_pack)
    if not artifacts.empty:
        with st.expander("Source artifacts vendored in repo", expanded=False):
            display_table(artifacts, height=260, max_rows=30)

    cols = st.columns([1.05, 1.25, 0.9])
    with cols[0]:
        section_title("HPO weights grouped by vendored source artifact")
        info_panel("Per-source weight sums are shown separately; HPO refinement rows and arbitration lineage rows are never mixed into one total.")
        display_table(ped_inner_hpo_weight_source_view(ped_inner_hpo_pack), height=210, max_rows=8)
        with st.expander("Weight row detail", expanded=False):
            display_table(ped_inner_hpo_weight_detail_view(ped_inner_hpo_pack), height=260, max_rows=40)
    with cols[1]:
        section_title("Nested trace")
        display_table(ped_inner_hpo_nested_trace_view(ped_inner_hpo_pack), height=310, max_rows=120)
    with cols[2]:
        section_title("Gap register")
        display_table(ped_inner_hpo_gap_register_view(ped_inner_hpo_pack), height=310, max_rows=20)


def render_page5_registry_and_component_trace(selected_stream: str, loaded_packs: dict[str, Any | None]) -> None:
    selected_packs = page5_selected_packs(selected_stream, loaded_packs)
    cols = st.columns([0.72, 1.0])
    with cols[0]:
        with st.container(border=True):
            st.markdown(
                "<div class='page5-panel-title'>Registry <span class='page5-panel-sub'>(model_registry.parquet)</span></div>",
                unsafe_allow_html=True,
            )
            registry = page5_registry_frame(selected_packs)
            display_table(registry, height=258, max_rows=12)
    with cols[1]:
        st.markdown(
            "<div class='page5-panel'>"
            "<div class='page5-panel-title'>Component trace <span class='page5-panel-sub'>(how predictions are composed)</span></div>"
            f"{page5_component_diagram_html(selected_packs)}"
            "</div>",
            unsafe_allow_html=True,
        )


def render_page5_lower_panels(
    analytics_stream: str,
    analytics_pack: Any | None,
    selected_stream: str,
    loaded: LoadedRun,
    loaded_packs: dict[str, Any | None],
    workbook_manifest: dict[str, Any],
    panel_contract: pd.DataFrame,
) -> None:
    if analytics_pack is None:
        warning_panel("No reproducibility pack is available for the lower audit panels.")
        return
    render_page5_r2_panel(selected_stream, loaded)
    lower_cols = st.columns([1.0, 1.0, 1.0, 1.05, 1.05])
    with lower_cols[0]:
        render_page5_importance_or_component_panel(analytics_stream, analytics_pack, panel_contract)
    with lower_cols[1]:
        render_page5_coefficients_panel(analytics_stream, analytics_pack, panel_contract)
    with lower_cols[2]:
        render_page5_sensitivities_panel(analytics_stream, analytics_pack, panel_contract)
    with lower_cols[3]:
        chart_card(
            f"Training window trace ({short_stream_label(analytics_stream)})",
            "Read-only training-window evidence from training_window_trace.parquet.",
            page5_training_window_figure(analytics_pack),
            notes_as_tooltip=False,
        )
    with lower_cols[4]:
        st.markdown(
            "<div class='page5-panel'>"
            "<div class='page5-panel-title'>Exports</div>"
            "<div class='page5-panel-sub'>Current reproducibility pack and provenance exports.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        render_page5_download_buttons(selected_stream, loaded_packs, workbook_manifest, key_prefix="lower")


def render_page5_r2_panel(selected_stream: str, loaded: LoadedRun | None = None) -> None:
    summary = reproducibility_component_r2_frame(Path(__file__).resolve().parent)
    if selected_stream != "All streams" and not summary.empty:
        summary = summary[summary["stream_label"].astype(str).eq(selected_stream)].copy()
    if summary.empty:
        render_page5_missing_panel(
            "Net forecast R2 after final model composition",
            "Reproducibility component prediction rows are unavailable, so net and component R2 cannot be calculated.",
            "Unavailable R2 is not coerced to zero.",
        )
        return
    table = summary.copy()
    table["component_model"] = table["component_model"].fillna("Final model composition")
    table["r2_value"] = table["forecast_r2"].map(format_r2)
    table["n_rows"] = pd.to_numeric(table["n_rows"], errors="coerce").fillna(0).astype(int)
    table = table.rename(
        columns={
            "stream_label": "Stream",
            "score_basis": "Score basis",
            "metric_name": "R2 metric",
            "component_model": "Model or component",
            "r2_value": "R2",
            "source_prediction_column": "Prediction column",
            "n_rows": "Rows",
            "interpretation": "Interpretation",
        }
    )
    display_cols = [
        "Stream",
        "Score basis",
        "R2 metric",
        "Model or component",
        "R2",
        "Rows",
        "Prediction column",
        "Interpretation",
    ]
    st.markdown(
        "<div class='page5-panel-title'>Net forecast R2 after final model composition</div>"
        f"<div class='page5-panel-sub'>{html.escape(R2_GOVERNANCE_INFO_TEXT)} Component R2 is shown where component predictions are in target units.</div>",
        unsafe_allow_html=True,
    )
    display_table(table[[column for column in display_cols if column in table.columns]], height=250, max_rows=24)
    if loaded is not None:
        st.markdown(
            f"<div class='page5-panel-title'>{html.escape(R2_LADDER_TITLE)}</div>"
            f"<div class='page5-panel-sub'>{html.escape(R2_LADDER_DISPLAY_NOTE)}</div>",
            unsafe_allow_html=True,
        )
        render_r2_ladder_table(r2_ladder_display_table(loaded, selected_stream), max_rows=12)


def render_page5_importance_or_component_panel(stream_label: str, pack: Any, panel_contract: pd.DataFrame) -> None:
    state = page5_contract_panel_state(panel_contract, stream_label, "feature_importance")
    status = state.get("status", "")
    title = page5_panel_title(state, stream_label)
    if status == "component_weight_only":
        fig = page5_component_contribution_figure(pack, stream_label)
        if not fig.data:
            render_page5_missing_panel(
                title,
                state.get("missing_message") or "Component contribution evidence is unavailable for this replay pack.",
                page5_deeper_explainability_note(stream_label),
            )
            return
        chart_card(
            title,
            "Component contribution is the share/weight of a model component in the final forecast; it is not variable-level feature importance.",
            fig,
            state.get("notes") or page5_deeper_explainability_note(stream_label),
            notes_as_tooltip=False,
        )
        return
    if status == "available":
        fig = plot_reproducibility_feature_importance(reproducibility_feature_importance_view(pack), stream_label)
        fig.update_layout(height=255, margin=dict(l=8, r=8, t=10, b=28))
        chart_card(
            title,
            "Replay-pack variable-level feature importance where emitted by the fitted model. This is not SHAP.",
            fig,
            state.get("notes") or None,
            notes_as_tooltip=False,
        )
        return
    render_page5_missing_panel(title, page5_missing_panel_message(stream_label, "feature_importance", state), page5_deeper_explainability_note(stream_label))


def render_page5_coefficients_panel(stream_label: str, pack: Any, panel_contract: pd.DataFrame) -> None:
    state = page5_contract_panel_state(panel_contract, stream_label, "coefficients")
    title = page5_panel_title(state, stream_label)
    if state.get("status") == "available":
        chart_card(
            title,
            "Coefficient evidence where the replay pack includes fitted OLS data.",
            page5_coefficients_figure(pack),
            state.get("notes") or None,
            notes_as_tooltip=False,
        )
        return
    render_page5_missing_panel(title, page5_missing_panel_message(stream_label, "coefficients", state), page5_deeper_explainability_note(stream_label))


def render_page5_sensitivities_panel(stream_label: str, pack: Any, panel_contract: pd.DataFrame) -> None:
    state = page5_contract_panel_state(panel_contract, stream_label, "scenario_sensitivities")
    title = page5_panel_title(state, stream_label)
    if state.get("status") == "available":
        fig = plot_reproducibility_sensitivities(reproducibility_sensitivity_view(pack), stream_label)
        fig.update_layout(height=255, margin=dict(l=8, r=8, t=10, b=28))
        chart_card(
            title,
            "Impact on dependent variable / model target.",
            fig,
            state.get("notes") or None,
            notes_as_tooltip=False,
        )
        return
    render_page5_missing_panel(
        title,
        page5_missing_panel_message(stream_label, "scenario_sensitivities", state),
        page5_deeper_explainability_note(stream_label),
    )


def render_page5_missing_panel(title: str, message: str, note: str = "") -> None:
    st.markdown(page5_missing_panel_html(title, message, note), unsafe_allow_html=True)


def page5_missing_panel_html(title: str, message: str, note: str = "") -> str:
    note_html = f"<div class='page5-caveat-note'>{html.escape(note)}</div>" if note else ""
    return (
        "<div class='page5-caveat-card'>"
        "<div class='page5-caveat-kicker'>Governance caveat</div>"
        f"<div class='page5-caveat-title'>{html.escape(title)}</div>"
        f"<div class='page5-caveat-copy'>{html.escape(message)}</div>"
        f"{note_html}"
        "</div>"
    )


def page5_component_contribution_figure(pack: Any, stream_label: str) -> go.Figure:
    weights = reproducibility_ensemble_weight_view(pack)
    if weights.empty or "Weight" not in weights.columns:
        return page5_empty_figure("Component contribution evidence is unavailable.")
    frame = weights.copy()
    frame["weight"] = pd.to_numeric(frame["Weight"], errors="coerce")
    frame = frame.dropna(subset=["weight"])
    if frame.empty:
        return page5_empty_figure("Component contribution evidence is unavailable.")
    frame["weight_pct"] = frame["weight"] * 100
    frame["Component"] = frame.get("Component", pd.Series([f"C{i + 1}" for i in range(len(frame))])).astype(str)
    frame = frame.sort_values("weight_pct", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=frame["weight_pct"],
            y=frame["Component"],
            orientation="h",
            marker_color="#008C82" if stream_label == "Heavy RUC volume" else "#002B5C",
            customdata=frame.get("Component model", pd.Series([""] * len(frame))).astype(str),
            hovertemplate=(
                "Component: %{y}<br>"
                "Contribution weight: %{x:.1f}%<br>"
                "Component model: %{customdata}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=255,
        margin=dict(l=8, r=8, t=10, b=28),
        xaxis_title="Component contribution (%)",
        yaxis_title="",
        showlegend=False,
    )
    return fig


def render_page5_shap_note() -> None:
    st.markdown(
        "<div class='page5-shap-note'><strong>SHAP not yet generated</strong>"
        "<span>SHAP explainability artifacts are not available in this pack.</span></div>",
        unsafe_allow_html=True,
    )


def render_forecast_builder_section() -> None:
    repo_root = Path(__file__).resolve().parent
    with st.expander(FORECAST_BUILDER_TITLE, expanded=False):
        info_panel(FORECAST_BUILDER_NOTE)
        if FORECAST_RUNNER_IMPORT_ERROR:
            warning_panel(
                "Forecast Builder is unavailable in this runtime because optional workbook/forward-scorer imports "
                "did not load. The dashboard evidence pack, KPIs, MAPE/R2, chart sources, finalists, scenarios, "
                "stress tests and diagnostics still render from repo-local artifacts."
            )
            st.caption("Forecast Builder status: optional forecast-runner import unavailable.")
            return
        template_bytes = build_forecast_input_template_bytes(repo_root)
        control_cols = st.columns([0.72, 1.28, 0.7, 0.9])
        with control_cols[0]:
            st.download_button(
                "Download blank 20-quarter template",
                data=template_bytes,
                file_name=TEMPLATE_FILENAME,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="forecast_builder_template_download",
                use_container_width=True,
            )
        with control_cols[1]:
            uploaded_files = st.file_uploader(
                "Upload completed forecast workbooks",
                type=["xlsx"],
                key="forecast_builder_upload",
                accept_multiple_files=True,
                help="Upload one or more completed templates. Uploaded workbooks are not committed and do not alter evidence packs.",
            )
        uploaded_files = uploaded_files or []

        upload_signature = "|".join(
            f"{getattr(uploaded, 'name', 'uploaded.xlsx')}:{hashlib.sha256(uploaded.getvalue()).hexdigest()}"
            for uploaded in uploaded_files
        )
        if st.session_state.get("forecast_builder_upload_hash") != upload_signature:
            st.session_state["forecast_builder_upload_hash"] = upload_signature
            st.session_state.pop("forecast_builder_validations", None)
            st.session_state.pop("forecast_builder_results", None)
            st.session_state.pop("forecast_builder_comparison", None)

        upload_rows: list[dict[str, Any]] = []
        for index, uploaded in enumerate(uploaded_files):
            workbook_bytes = uploaded.getvalue()
            digest = hashlib.sha256(workbook_bytes).hexdigest()
            workbook_filename = getattr(uploaded, "name", f"uploaded_{index + 1}.xlsx")
            scenario_default = scenario_name_from_filename(workbook_filename)
            inferred_role, inferred_role_source = resolve_scenario_role(
                scenario_name=scenario_default,
                workbook_filename=workbook_filename,
            )
            role_options = ["Select role", "Basecase", "Comparison"]
            role_index = (
                1
                if inferred_role == SCENARIO_ROLE_BASECASE
                else 2
                if inferred_role == SCENARIO_ROLE_COMPARISON
                else 0
            )
            scenario_cols = st.columns([0.58, 0.42])
            with scenario_cols[0]:
                scenario_value = st.text_input(
                    f"Scenario name for {workbook_filename}",
                    value=scenario_default,
                    key=f"forecast_builder_scenario_{index}_{digest[:10]}",
                )
            with scenario_cols[1]:
                selected_role_label = st.selectbox(
                    f"Scenario role for {workbook_filename}",
                    role_options,
                    index=role_index,
                    key=f"forecast_builder_scenario_role_{index}_{digest[:10]}",
                    help="Required for scenario comparisons. Upload order is never used to infer base/comparison direction.",
                )
            selected_role = {
                "Basecase": SCENARIO_ROLE_BASECASE,
                "Comparison": SCENARIO_ROLE_COMPARISON,
            }.get(selected_role_label)
            upload_rows.append(
                {
                    "index": index,
                    "uploaded": uploaded,
                    "workbook_bytes": workbook_bytes,
                    "workbook_filename": workbook_filename,
                    "scenario_name": sanitize_scenario_name(scenario_value),
                    "scenario_role": selected_role,
                    "scenario_role_source": "explicit" if selected_role else inferred_role_source,
                    "workbook_sha256": digest,
                }
            )
        role_errors = _forecast_builder_role_errors(upload_rows)
        if role_errors:
            warning_panel("Scenario role validation failed: " + " ".join(role_errors))

        with control_cols[2]:
            validate_clicked = st.button(
                "Validate inputs",
                key="forecast_builder_validate",
                use_container_width=True,
                disabled=not upload_rows or bool(role_errors),
            )
        with control_cols[3]:
            run_clicked = st.button(
                "Calculate forecasts",
                key="forecast_builder_calculate",
                use_container_width=True,
                disabled=not upload_rows or bool(role_errors),
            )

        scenario_names = _unique_scenario_names([row["scenario_name"] for row in upload_rows])
        for row, scenario_name in zip(upload_rows, scenario_names, strict=False):
            row["scenario_name"] = scenario_name

        if validate_clicked:
            st.session_state["forecast_builder_validations"] = [
                {
                    **row,
                    "validation": validate_forecast_workbook(row["workbook_bytes"], repo_root=repo_root),
                }
                for row in upload_rows
            ]
        if run_clicked:
            run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            results = [
                run_forecast_workbook(
                    row["workbook_bytes"],
                    repo_root=repo_root,
                    workbook_filename=row["workbook_filename"],
                    scenario_name=row["scenario_name"],
                    scenario_role=row["scenario_role"],
                    run_timestamp=run_timestamp,
                )
                for row in upload_rows
            ]
            comparison = write_forecast_scenario_comparison(results, repo_root=repo_root, run_timestamp=run_timestamp)
            st.session_state["forecast_builder_results"] = results
            st.session_state["forecast_builder_comparison"] = comparison
            st.session_state["forecast_builder_validations"] = [
                {**row, "validation": result.validation}
                for row, result in zip(upload_rows, results, strict=False)
            ]

        validations = st.session_state.get("forecast_builder_validations")
        if validations:
            st.markdown("<div class='page5-panel-title'>Forecast workbook validation</div>", unsafe_allow_html=True)
            display_table(_forecast_builder_validation_table(validations), height=190, max_rows=60)

        results = st.session_state.get("forecast_builder_results")
        comparison = st.session_state.get("forecast_builder_comparison")
        if results:
            render_forecast_builder_results(results, comparison)
        elif not upload_rows:
            st.caption("Download the blank template, complete the user-entry columns for one or more scenarios, then upload the workbooks here.")


def render_forecast_builder_result(result: Any) -> None:
    render_forecast_builder_results([result], None)


def render_forecast_builder_results(results: list[Any], comparison: Any | None) -> None:
    future_combined = (
        comparison.future_forecasts.copy()
        if comparison is not None and isinstance(getattr(comparison, "future_forecasts", None), pd.DataFrame)
        else pd.concat([result.future_forecasts for result in results], ignore_index=True, sort=False)
    )
    capability_combined = (
        comparison.capability_report.copy()
        if comparison is not None and isinstance(getattr(comparison, "capability_report", None), pd.DataFrame)
        else pd.concat([result.capability_report for result in results], ignore_index=True, sort=False)
    )
    chart_rows_combined = (
        comparison.forecast_chart_rows.copy()
        if comparison is not None and isinstance(getattr(comparison, "forecast_chart_rows", None), pd.DataFrame)
        else _combine_forecast_builder_chart_rows(results)
    )
    component_combined = pd.concat([result.component_forecasts for result in results], ignore_index=True, sort=False)
    statuses = {str(result.manifest.get("forecast_status", "unknown")) for result in results}
    status = statuses.pop() if len(statuses) == 1 else "scenario_comparison"
    validation_status = "passed" if all(result.manifest.get("validation_status") == "passed" for result in results) else "failed"
    kpi_grid(
        [
            ("Validation", validation_status, "completed workbook check"),
            ("Forecast status", status, "available forecast or governed gaps"),
            ("Scenarios", str(len(results)), "uploaded workbook count"),
            ("Broad search", "not run", "fixed finalists only"),
            ("Evidence pack", "unchanged", "forecast run is isolated"),
        ]
    )
    if not capability_combined.empty:
        st.markdown("<div class='page5-panel-title'>Forecast capability by stream</div>", unsafe_allow_html=True)
        display_table(_forecast_builder_capability_table(capability_combined), height=160, max_rows=60)
    stream_options = ["All streams"] + sorted(future_combined["stream_label"].dropna().astype(str).unique().tolist())
    filter_cols = st.columns([0.42, 0.58])
    with filter_cols[0]:
        selected_stream = st.selectbox("Forecast stream", stream_options, key="forecast_builder_stream")
    with filter_cols[1]:
        row_filter = st.radio(
            "Forecast table rows",
            ["All rows", "Numeric forecasts only", "Governed gaps only"],
            horizontal=True,
            key="forecast_builder_row_filter",
        )
    future = future_combined.copy()
    components = component_combined.copy()
    chart_rows = chart_rows_combined.copy()
    if selected_stream != "All streams":
        future = future[future["stream_label"].astype(str).eq(selected_stream)].copy()
        components = components[components["stream_label"].astype(str).eq(selected_stream)].copy()
        chart_rows = chart_rows[chart_rows["stream_label"].astype(str).eq(selected_stream)].copy()

    future_for_table = _filter_forecast_builder_rows(future, row_filter)
    st.markdown("<div class='page5-panel-title'>Forecast table by stream and quarter</div>", unsafe_allow_html=True)
    display_table(_forecast_builder_table(future_for_table), height=240, max_rows=60)
    chart_card(
        "Forecast chart by scenario, stream and quarter",
        "Only streams with numeric forecasts are plotted; governed-gap streams remain visible in the table/capability report.",
        forecast_builder_figure(chart_rows, future),
        notes_as_tooltip=False,
    )
    st.caption("Forecast start marker indicates the first forecast quarter after the latest historical actual. " + HORIZON_SUPPORT_NOTE)
    for note in _forecast_builder_assumption_notes(comparison):
        st.caption(note)
    has_gap_rows = "forecast_available" in future.columns and (~future["forecast_available"].fillna(False).astype(bool)).any()
    has_numeric_forecasts = pd.to_numeric(future_combined.get("forecast"), errors="coerce").notna().any()
    if not has_numeric_forecasts:
        warning_panel("Governed missing-capability gaps were written instead of fake forecasts. " + _forecast_builder_gap_warning(future))
    elif has_gap_rows:
        warning_panel(
            "Numeric fixed-finalist forecasts were produced where repo-reproducible; unsupported streams were kept as governed gaps. "
            + _forecast_builder_gap_warning(future)
        )
    gap_detail = _forecast_builder_gap_detail_table(future)
    if not gap_detail.empty:
        with st.expander("Full governed-gap rationale", expanded=False):
            display_table(gap_detail, height=240, max_rows=80)

    tabs = st.tabs(["Heavy component trace", "Light base/residual trace", "PED component trace"])
    trace_filters = [
        ("HEAVY_RUC", tabs[0]),
        ("LIGHT_RUC", tabs[1]),
        ("PED", tabs[2]),
    ]
    for stream, tab in trace_filters:
        with tab:
            trace = components[components["stream"].astype(str).eq(stream)].copy()
            display_table(_forecast_builder_component_table(trace), height=240, max_rows=80)

    if comparison is not None:
        promotion_errors = validate_promotable_comparison(comparison)
        if promotion_errors:
            warning_panel("Revenue Outlook promotion is disabled: " + " ".join(promotion_errors))
        if st.button(
            "Promote reviewed comparison to Revenue Outlook",
            key="forecast_builder_promote_revenue_outlook",
            use_container_width=False,
            disabled=bool(promotion_errors),
            help="Writes the governed current-outlook pack used by the Revenue Outlook page. Test fixtures are blocked.",
        ):
            pack = promote_revenue_outlook_pack(
                comparison,
                repo_root=Path(__file__).resolve().parent,
                output_dir=Path(__file__).resolve().parent / CURRENT_REVENUE_OUTLOOK_DIR,
            )
            st.session_state["revenue_outlook_pack"] = pack
            st.success("Revenue Outlook promoted from this reviewed comparison. Open the Revenue Outlook page to inspect activity and revenue.")

    st.download_button(
        "Download combined comparison pack",
        data=forecast_pack_zip_bytes(comparison.output_dir if comparison is not None else results[0].output_dir),
        file_name=f"{Path(comparison.output_dir if comparison is not None else results[0].output_dir).name}_forecast_run_pack.zip",
        mime="application/zip",
        key="forecast_builder_comparison_pack_download",
        use_container_width=False,
    )
    for result in results:
        scenario = str(result.manifest.get("scenario_name", "scenario"))
        st.download_button(
            f"Download {scenario} scenario pack",
            data=forecast_pack_zip_bytes(result.output_dir),
            file_name=f"{Path(result.output_dir).name}_forecast_run_pack.zip",
            mime="application/zip",
            key=f"forecast_builder_pack_download_{scenario}",
            use_container_width=False,
        )


def _unique_scenario_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    output: list[str] = []
    for name in names:
        base = sanitize_scenario_name(name)
        count = seen.get(base, 0) + 1
        seen[base] = count
        output.append(base if count == 1 else f"{base}_{count}")
    return output


def _forecast_builder_role_errors(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    errors: list[str] = []
    missing = [str(row.get("workbook_filename", row.get("scenario_name", "uploaded workbook"))) for row in rows if not row.get("scenario_role")]
    if missing:
        errors.append("Choose Basecase or Comparison for: " + ", ".join(missing) + ".")
    base_count = sum(1 for row in rows if row.get("scenario_role") == SCENARIO_ROLE_BASECASE)
    comparison_count = sum(1 for row in rows if row.get("scenario_role") == SCENARIO_ROLE_COMPARISON)
    if base_count != 1:
        errors.append(f"Exactly one uploaded workbook must be marked Basecase; found {base_count}.")
    if comparison_count < 1:
        errors.append("At least one uploaded workbook must be marked Comparison.")
    return errors


def _forecast_builder_assumption_notes(comparison: Any | None) -> list[str]:
    if comparison is None:
        return []
    manifest = getattr(comparison, "manifest", {}) or {}
    summary = manifest.get("scenario_assumption_delta_summary", [])
    if not isinstance(summary, list):
        return []
    notes: list[str] = []
    for record in summary:
        if not isinstance(record, dict):
            continue
        comparison_name = record.get("comparison_scenario", "comparison")
        note = str(record.get("assumption_scope_note") or "").strip()
        if note:
            notes.append(f"{comparison_name}: {note}")
    return notes


def _forecast_builder_validation_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for row in rows:
        validation = row.get("validation")
        scenario_name = row.get("scenario_name", "scenario")
        workbook_filename = row.get("workbook_filename", "")
        if validation is None:
            continue
        report = validation.report_frame()
        for _, message_row in report.iterrows():
            output.append(
                {
                    "Scenario": scenario_name,
                    "Role": row.get("scenario_role") or "unresolved",
                    "Workbook": workbook_filename,
                    "Workbook SHA256": row.get("workbook_sha256"),
                    "Horizon": getattr(validation, "forecast_horizon_quarters", len(getattr(validation, "forecast_periods", []))),
                    "Start": getattr(validation, "forecast_start_period", None),
                    "End": getattr(validation, "forecast_end_period", None),
                    "Severity": message_row.get("severity"),
                    "Message": message_row.get("message"),
                }
            )
    return pd.DataFrame(output)


def _combine_forecast_builder_chart_rows(results: list[Any]) -> pd.DataFrame:
    frames = [
        result.forecast_chart_rows
        for result in results
        if isinstance(getattr(result, "forecast_chart_rows", None), pd.DataFrame)
    ]
    if not frames:
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True, sort=False)
    if rows.empty or "row_type" not in rows.columns:
        return rows
    historical = rows[rows["row_type"].astype(str).eq("historical_actual")].drop_duplicates(
        subset=[column for column in ["row_type", "stream", "period"] if column in rows.columns],
        keep="first",
    )
    future = rows[~rows["row_type"].astype(str).eq("historical_actual")]
    return pd.concat([historical, future], ignore_index=True, sort=False)


def _filter_forecast_builder_rows(frame: pd.DataFrame, row_filter: str) -> pd.DataFrame:
    if frame is None or frame.empty or "forecast_available" not in frame.columns:
        return frame
    available = frame["forecast_available"].fillna(False).astype(bool)
    if row_filter == "Numeric forecasts only":
        return frame[available].copy()
    if row_filter == "Governed gaps only":
        return frame[~available].copy()
    return frame.copy()


def _sort_forecast_builder_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame
    output = frame.copy()
    available = output.get("forecast_available", pd.Series(False, index=output.index)).fillna(False).astype(bool)
    output["_availability_rank"] = np.where(available, 0, 1)
    if "target_period" in output.columns:
        output["_period_key"] = output["target_period"].astype(str).map(_forecast_builder_period_key)
    else:
        output["_period_key"] = range(len(output))
    sort_columns = [column for column in ["_availability_rank", "stream_label", "scenario_name", "_period_key"] if column in output.columns]
    return output.sort_values(sort_columns, kind="stable").drop(columns=["_availability_rank", "_period_key"], errors="ignore")


def _forecast_builder_period_key(value: Any) -> int:
    try:
        return quarter_sort_key(str(value))
    except Exception:
        return 0


def _short_forecast_gap_reason(row: pd.Series) -> str:
    status = str(row.get("availability_status", ""))
    gap_code = str(row.get("gap_code", ""))
    if status == "validation_failed" or gap_code == "input_validation_failed":
        return "Input validation failed."
    if gap_code and gap_code not in {"None", "<NA>", "nan"}:
        stream = str(row.get("stream", ""))
        stream_label = str(row.get("stream_label", ""))
        if gap_code == "heavy_ruc_component_forward_scorers_missing" or stream == "HEAVY_RUC" or stream_label == "Heavy RUC volume":
            return HEAVY_RUC_FORECAST_GAP_REASON
        return GENERIC_FORECAST_GAP_REASON
    return ""


def _forecast_builder_gap_warning(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return GENERIC_FORECAST_GAP_REASON
    gaps = frame[~frame.get("forecast_available", pd.Series(dtype=bool)).fillna(False).astype(bool)].copy()
    if gaps.empty:
        return GENERIC_FORECAST_GAP_REASON
    stream_codes = set(gaps.get("stream", pd.Series(dtype=str)).dropna().astype(str))
    stream_labels = set(gaps.get("stream_label", pd.Series(dtype=str)).dropna().astype(str))
    messages: list[str] = []
    if "HEAVY_RUC" in stream_codes or "Heavy RUC volume" in stream_labels:
        messages.append(HEAVY_RUC_FORECAST_GAP_REASON)
    other_gaps = gaps[
        ~gaps.get("stream", pd.Series(dtype=str)).astype(str).eq("HEAVY_RUC")
        & ~gaps.get("stream_label", pd.Series(dtype=str)).astype(str).eq("Heavy RUC volume")
    ]
    if not other_gaps.empty:
        messages.append(GENERIC_FORECAST_GAP_REASON)
    return " ".join(messages)


def _forecast_builder_gap_detail_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "forecast_available" not in frame.columns:
        return pd.DataFrame()
    gaps = frame[~frame["forecast_available"].fillna(False).astype(bool)].copy()
    if gaps.empty:
        return pd.DataFrame()
    columns = [
        column
        for column in ["scenario_name", "stream_label", "gap_code", "failing_component", "gap_reason"]
        if column in gaps.columns
    ]
    detail = gaps[columns].drop_duplicates().copy()
    return detail.rename(
        columns={
            "scenario_name": "Scenario",
            "stream_label": "Stream",
            "gap_code": "Gap code",
            "failing_component": "Failing component",
            "gap_reason": "Full rationale",
        }
    )


def _forecast_builder_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = _sort_forecast_builder_rows(frame)
    columns = [
        "scenario_name",
        "stream_label",
        "model",
        "target_period",
        "horizon",
        "horizon_support_label",
        "forecast",
        "forecast_available",
        "availability_status",
        "gap_code",
        "gap_reason",
    ]
    table = frame[[column for column in columns if column in frame.columns]].copy()
    if "gap_reason" in table.columns:
        table["gap_reason"] = frame.apply(_short_forecast_gap_reason, axis=1)
    return table.rename(
        columns={
            "scenario_name": "Scenario",
            "stream_label": "Stream",
            "model": "Model",
            "target_period": "Quarter",
            "horizon": "Horizon",
            "horizon_support_label": "Horizon scope",
            "forecast": "Forecast",
            "forecast_available": "Forecast available",
            "availability_status": "Availability",
            "gap_code": "Gap code",
            "gap_reason": "Gap reason",
        }
    )


def _forecast_builder_capability_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = _sort_forecast_builder_rows(frame)
    columns = [
        "scenario_name",
        "stream_label",
        "capability_status",
        "forecast_available",
        "numeric_forecast_rows",
        "governed_gap_rows",
        "scorer_version",
        "parity_status",
        "max_parity_delta",
        "stored_replay_max_delta",
        "failing_component",
        "gap_code",
        "gap_reason",
    ]
    table = frame[[column for column in columns if column in frame.columns]].copy()
    if "gap_reason" in table.columns:
        table["gap_reason"] = frame.apply(_short_forecast_gap_reason, axis=1)
    return table.rename(
        columns={
            "scenario_name": "Scenario",
            "stream_label": "Stream",
            "capability_status": "Capability",
            "forecast_available": "Forecast available",
            "numeric_forecast_rows": "Numeric rows",
            "governed_gap_rows": "Gap rows",
            "scorer_version": "Scorer version",
            "parity_status": "Parity status",
            "max_parity_delta": "Max parity delta",
            "stored_replay_max_delta": "Stored replay delta",
            "failing_component": "Failing component",
            "gap_code": "Gap code",
            "gap_reason": "Gap reason",
        }
    )


def _forecast_builder_component_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = _sort_forecast_builder_rows(frame.rename(columns={"target_period": "target_period"}))
    columns = [
        "scenario_name",
        "stream_label",
        "component_model",
        "component_role",
        "component_weight",
        "target_period",
        "horizon",
        "component_forecast",
        "component_log_value",
        "weighted_component_forecast",
        "availability_status",
        "gap_code",
        "gap_reason",
    ]
    table = frame[[column for column in columns if column in frame.columns]].copy()
    if "gap_reason" in table.columns:
        table["gap_reason"] = frame.apply(_short_forecast_gap_reason, axis=1)
    return table.rename(
        columns={
            "scenario_name": "Scenario",
            "stream_label": "Stream",
            "component_model": "Component",
            "component_role": "Role",
            "component_weight": "Weight",
            "target_period": "Quarter",
            "horizon": "Horizon",
            "component_forecast": "Component forecast",
            "component_log_value": "Component log value",
            "weighted_component_forecast": "Weighted component forecast",
            "availability_status": "Availability",
            "gap_code": "Gap code",
            "gap_reason": "Gap reason",
        }
    )


def forecast_builder_figure(chart_rows: pd.DataFrame, future_rows: pd.DataFrame | None = None) -> go.Figure:
    if chart_rows is None or chart_rows.empty:
        return empty_figure("No forecast chart rows are available.")
    data = chart_rows.copy()
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data["period_key"] = data["period"].astype(str).map(_forecast_builder_period_key)
    data = data.sort_values(["stream_label", "row_type", "scenario_name", "period_key"], kind="stable")
    stream_labels = data["stream_label"].dropna().astype(str).unique().tolist()
    if not stream_labels:
        return empty_figure("No stream rows are available for forecast display.")

    rows = len(stream_labels)
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.075 if rows > 1 else 0.04,
        subplot_titles=stream_labels if rows > 1 else None,
    )
    palette = ["#002B5C", "#008C82", "#7C3AED", "#B45309", "#BE123C", "#475569"]
    dashes = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
    scenario_values = sorted(
        data.loc[data["row_type"].astype(str).eq("future_forecast"), "scenario_name"].dropna().astype(str).unique().tolist()
    )
    scenario_style = {
        scenario: {"color": palette[index % len(palette)], "dash": dashes[index % len(dashes)]}
        for index, scenario in enumerate(scenario_values)
    }
    shown_legend: set[str] = set()
    forecast_start = _forecast_builder_start_period(data)

    for row_index, stream_label in enumerate(stream_labels, start=1):
        stream_data = data[data["stream_label"].astype(str).eq(stream_label)].copy()
        historical = stream_data[stream_data["row_type"].astype(str).eq("historical_actual")].dropna(subset=["value_numeric"])
        if not historical.empty:
            showlegend = "historical_actual" not in shown_legend
            shown_legend.add("historical_actual")
            fig.add_trace(
                go.Scatter(
                    x=historical["period"],
                    y=historical["value_numeric"],
                    mode="lines",
                    name="Historical actual",
                    legendgroup="historical_actual",
                    showlegend=showlegend,
                    line=dict(color="#475569", width=2.2),
                    hovertemplate="Historical actual<br>Quarter: %{x}<br>Value: %{y:,.2f}<extra></extra>",
                ),
                row=row_index,
                col=1,
            )
        future = stream_data[stream_data["row_type"].astype(str).eq("future_forecast")].dropna(subset=["value_numeric"])
        for scenario, group in future.groupby("scenario_name", dropna=False):
            scenario_text = str(scenario)
            style = scenario_style.get(scenario_text, {"color": "#002B5C", "dash": "solid"})
            legend_key = f"forecast_{scenario_text}"
            showlegend = legend_key not in shown_legend
            shown_legend.add(legend_key)
            hover_horizon = group.get("horizon", pd.Series("", index=group.index)).map(_forecast_builder_hover_horizon)
            hover_scope = group.get("horizon_support_label", pd.Series("", index=group.index)).fillna("").astype(str)
            fig.add_trace(
                go.Scatter(
                    x=group["period"],
                    y=group["value_numeric"],
                    mode="lines+markers",
                    name=f"{scenario_text} forecast",
                    legendgroup=legend_key,
                    showlegend=showlegend,
                    line=dict(color=style["color"], dash=style["dash"], width=2.4),
                    marker=dict(size=6),
                    customdata=pd.DataFrame({"horizon": hover_horizon, "scope": hover_scope}),
                    hovertemplate=(
                        f"Scenario: {html.escape(scenario_text)}<br>"
                        "Quarter: %{x}<br>Horizon: %{customdata[0]}<br>"
                        "Scope: %{customdata[1]}<br>Forecast: %{y:,.2f}<extra></extra>"
                    ),
                ),
                row=row_index,
                col=1,
            )
        if forecast_start:
            future_periods = future["period"].astype(str).tolist()
            if future_periods:
                # Shade the forecast window so the future region reads at a glance.
                fig.add_vrect(
                    x0=forecast_start,
                    x1=future_periods[-1],
                    fillcolor="rgba(15, 76, 129, 0.06)",
                    line_width=0,
                    layer="below",
                    row=row_index,
                    col=1,
                )
            fig.add_vline(
                x=forecast_start,
                line_color="#64748B",
                line_dash="dot",
                line_width=1.4,
                row=row_index,
                col=1,
            )
            y_anchor = _forecast_builder_annotation_y(historical, future)
            fig.add_annotation(
                x=forecast_start,
                y=y_anchor,
                text="Forecast start",
                showarrow=True,
                arrowhead=2,
                ax=18,
                ay=-24,
                font=dict(size=10, color="#334155"),
                bgcolor="rgba(255,255,255,0.88)",
                bordercolor="#CBD5E1",
                borderwidth=1,
                row=row_index,
                col=1,
            )
        h13_start = _forecast_builder_long_range_start_period(future)
        if h13_start:
            fig.add_vline(
                x=h13_start,
                line_color="#B45309",
                line_dash="dash",
                line_width=1.3,
                row=row_index,
                col=1,
            )
            y_anchor = _forecast_builder_annotation_y(historical, future)
            fig.add_annotation(
                x=h13_start,
                y=y_anchor,
                text=f"H{BACKTEST_SUPPORTED_MAX_HORIZON + 1} long-range starts",
                showarrow=True,
                arrowhead=2,
                ax=18,
                ay=20,
                font=dict(size=10, color="#92400E"),
                bgcolor="rgba(255,251,235,0.90)",
                bordercolor="#FBBF24",
                borderwidth=1,
                row=row_index,
                col=1,
            )
        if future.empty and _stream_has_governed_gap(future_rows, stream_label):
            y_anchor = _forecast_builder_annotation_y(historical, future)
            x_anchor = historical["period"].iloc[-1] if not historical.empty else forecast_start
            fig.add_annotation(
                x=x_anchor,
                y=y_anchor,
                text=_forecast_builder_governed_gap_annotation(stream_label),
                showarrow=False,
                font=dict(size=11, color="#92400E"),
                bgcolor="rgba(255,247,237,0.94)",
                bordercolor="#FDBA74",
                borderwidth=1,
                row=row_index,
                col=1,
            )
        fig.update_yaxes(title_text="Value", row=row_index, col=1)
        tickvals, ticktext = _forecast_builder_xaxis_ticks(stream_data, forecast_start, h13_start)
        fig.update_xaxes(
            title_text="Quarter" if row_index == rows else "",
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            row=row_index,
            col=1,
        )

    fig.update_layout(
        height=max(360, 235 * rows),
        margin=dict(l=8, r=8, t=34 if rows > 1 else 10, b=34),
        legend_title="Forecast display",
        hovermode="x unified" if rows == 1 else "closest",
    )
    return fig


def _forecast_builder_hover_horizon(value: Any) -> str:
    try:
        return f"H{int(float(value))}"
    except Exception:
        return ""


def _forecast_builder_long_range_start_period(future_rows: pd.DataFrame) -> str | None:
    if future_rows is None or future_rows.empty or "horizon" not in future_rows.columns:
        return None
    future = future_rows.copy()
    future["horizon_numeric"] = pd.to_numeric(future["horizon"], errors="coerce")
    future = future[future["horizon_numeric"].gt(BACKTEST_SUPPORTED_MAX_HORIZON)].copy()
    if future.empty:
        return None
    future["period_key"] = future["period"].astype(str).map(_forecast_builder_period_key)
    future = future.sort_values("period_key", kind="stable")
    return str(future.iloc[0]["period"])


def _forecast_builder_xaxis_ticks(
    stream_rows: pd.DataFrame,
    forecast_start: str | None,
    h13_start: str | None,
) -> tuple[list[str], list[str]]:
    if stream_rows is None or stream_rows.empty or "period" not in stream_rows.columns:
        return [], []
    periods = (
        stream_rows[["period", "period_key"]]
        .dropna(subset=["period"])
        .drop_duplicates(subset=["period"])
        .sort_values("period_key", kind="stable")["period"]
        .astype(str)
        .tolist()
    )
    if not periods:
        return [], []
    forecast_start_key = _forecast_builder_period_key(forecast_start) if forecast_start else None
    h13_key = _forecast_builder_period_key(h13_start) if h13_start else None
    tickvals: list[str] = []
    ticktext: list[str] = []
    for period in periods:
        key = _forecast_builder_period_key(period)
        year, quarter = _forecast_builder_period_parts(period)
        label: str | None = None
        if period == forecast_start or period == h13_start:
            label = period
        elif forecast_start_key is not None and key >= forecast_start_key and (h13_key is None or key < h13_key):
            label = period
        elif quarter == 4 and year:
            label = year
        if label:
            tickvals.append(period)
            ticktext.append(label)
    return tickvals, ticktext


def _forecast_builder_period_parts(value: Any) -> tuple[str | None, int | None]:
    text = str(value or "").strip()
    if len(text) < 6 or text[-2] != "Q":
        return None, None
    year = text[:4]
    quarter_text = text[-1]
    if not year.isdigit() or quarter_text not in {"1", "2", "3", "4"}:
        return None, None
    return year, int(quarter_text)


def _forecast_builder_start_period(chart_rows: pd.DataFrame) -> str | None:
    future = chart_rows[chart_rows["row_type"].astype(str).eq("future_forecast")].copy()
    if future.empty:
        return None
    future["period_key"] = future["period"].astype(str).map(_forecast_builder_period_key)
    future = future.sort_values("period_key")
    return str(future.iloc[0]["period"])


def _forecast_builder_annotation_y(historical: pd.DataFrame, future: pd.DataFrame) -> float:
    values = pd.concat(
        [
            pd.to_numeric(historical.get("value_numeric", pd.Series(dtype=float)), errors="coerce"),
            pd.to_numeric(future.get("value_numeric", pd.Series(dtype=float)), errors="coerce"),
        ],
        ignore_index=True,
    ).dropna()
    if values.empty:
        return 1.0
    return float(values.max())


def _stream_has_governed_gap(future_rows: pd.DataFrame | None, stream_label: str) -> bool:
    if future_rows is None or future_rows.empty or "stream_label" not in future_rows.columns:
        return False
    stream = future_rows[future_rows["stream_label"].astype(str).eq(str(stream_label))]
    if stream.empty or "forecast_available" not in stream.columns:
        return False
    return not stream["forecast_available"].fillna(False).astype(bool).any()


def _forecast_builder_governed_gap_annotation(stream_label: str) -> str:
    if str(stream_label) == "Heavy RUC volume":
        return "Governed gap: Heavy requires exact C3/C4 parent-state parity"
    return "Governed gap: repo-local forward scorer unavailable"


def page5_workbook_card_html(manifest: dict[str, Any]) -> str:
    if manifest.get("available"):
        value = "Source workbook available"
        sub = f"Updated: {str(manifest.get('modified_time', ''))[:16]}"
        icon = "OK"
    else:
        value = "Optional source workbook not found"
        sub = "Parquet packs remain evidence source of truth"
        icon = "WARN"
    return page5_mini_card_html("Workbook availability", value, sub, icon=icon)


def page5_mini_card_html(title: str, value: str, subtext: str, *, icon: str) -> str:
    return (
        "<div class='page5-mini-card'>"
        f"<div class='page5-mini-kicker'>{html.escape(icon)} &nbsp; {html.escape(title)}</div>"
        f"<div class='page5-mini-value'>{html.escape(value)}</div>"
        f"<div class='page5-mini-sub'>{html.escape(subtext)}</div>"
        "</div>"
    )


def page5_selected_packs(selected_stream: str, loaded_packs: dict[str, Any | None]) -> dict[str, Any]:
    candidates = loaded_packs if selected_stream == "All streams" else {selected_stream: loaded_packs.get(selected_stream)}
    return {label: pack for label, pack in candidates.items() if pack is not None and getattr(pack, "available", False)}


def page5_analytics_pack(selected_stream: str, loaded_packs: dict[str, Any | None]) -> Any | None:
    if selected_stream != "All streams":
        pack = loaded_packs.get(selected_stream)
        return pack if pack is not None and getattr(pack, "available", False) else None
    preferred = loaded_packs.get("Light RUC volume")
    if preferred is not None and getattr(preferred, "available", False):
        return preferred
    return next((pack for pack in loaded_packs.values() if pack is not None and getattr(pack, "available", False)), None)


def page5_panel_contract_signature() -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    root = Path(__file__).resolve().parent / PAGE5_UI_CONTRACT_ROOT
    for name in PAGE5_PANEL_CONTRACT_FILES:
        path = root / name
        if path.exists():
            stat = path.stat()
            signature.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(signature)


@st.cache_data(show_spinner=False)
def cached_page5_panel_contract(signature: tuple[tuple[str, int, int], ...]) -> pd.DataFrame:
    del signature
    root = Path(__file__).resolve().parent / PAGE5_UI_CONTRACT_ROOT
    parquet_path = root / "reproducibility_panel_contract.parquet"
    csv_path = root / "reproducibility_panel_contract.csv"
    if parquet_path.exists():
        frame = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        frame = pd.read_csv(csv_path)
    else:
        frame = page5_fallback_panel_contract()
    for column in PAGE5_PANEL_CONTRACT_REQUIRED_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(PAGE5_PANEL_CONTRACT_REQUIRED_COLUMNS)].copy()
    for column in PAGE5_PANEL_CONTRACT_REQUIRED_COLUMNS:
        frame[column] = frame[column].where(frame[column].notna(), "").astype(str).str.strip()
    return frame


def page5_panel_contract_frame() -> pd.DataFrame:
    return cached_page5_panel_contract(page5_panel_contract_signature())


def page5_fallback_panel_contract() -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    panels = ["status_card", "component_trace", "feature_importance", "coefficients", "scenario_sensitivities", "training_window_trace"]
    for stream_label in reproducibility_stream_labels():
        for panel in panels:
            status = "available"
            display_title = panel.replace("_", " ").title()
            missing_message = ""
            notes = ""
            if stream_label == "PED VKT per capita" and panel == "feature_importance":
                status = "component_weight_only"
                display_title = "Component contribution"
                notes = "C1 100% is not a variable importance chart."
            if stream_label == "Heavy RUC volume" and panel == "feature_importance":
                status = "component_weight_only"
                display_title = "Ensemble component contribution"
                notes = "C1-C4 are ensemble component weights, not variable importances."
            if stream_label in {"PED VKT per capita", "Heavy RUC volume"} and panel in {"coefficients", "scenario_sensitivities"}:
                status = "unavailable"
                display_title = "Model coefficients" if panel == "coefficients" else "Scenario sensitivities"
                missing_message = page5_missing_panel_message(stream_label, panel, {})
            rows.append(
                {
                    "stream": stream_label,
                    "panel": panel,
                    "status": status,
                    "display_title": display_title,
                    "evidence_file": "",
                    "recommendation": "",
                    "missing_message": missing_message,
                    "notes": notes,
                }
            )
    return pd.DataFrame(rows)


def page5_contract_panel_state(contract: pd.DataFrame, stream_label: str, panel: str) -> dict[str, str]:
    if contract is None or contract.empty:
        contract = page5_fallback_panel_contract()
    row = contract[
        contract["stream"].astype(str).eq(stream_label)
        & contract["panel"].astype(str).eq(panel)
    ]
    if row.empty:
        fallback = page5_fallback_panel_contract()
        row = fallback[
            fallback["stream"].astype(str).eq(stream_label)
            & fallback["panel"].astype(str).eq(panel)
        ]
    if row.empty:
        return {
            "stream": stream_label,
            "panel": panel,
            "status": "unavailable",
            "display_title": panel.replace("_", " ").title(),
            "missing_message": "Panel contract is unavailable for this stream.",
            "notes": "",
            "evidence_file": "",
            "recommendation": "",
        }
    return {column: str(row.iloc[0].get(column, "") or "") for column in PAGE5_PANEL_CONTRACT_REQUIRED_COLUMNS}


def page5_panel_title(state: dict[str, str], stream_label: str) -> str:
    display_title = state.get("display_title") or state.get("panel", "Panel").replace("_", " ").title()
    return f"{display_title} ({short_stream_label(stream_label)})"


def page5_missing_panel_message(stream_label: str, panel: str, state: dict[str, str]) -> str:
    del panel
    if stream_label == "PED VKT per capita":
        return "Feature-level refit not attempted; inner HPO/static-solver audit remains partial."
    if stream_label == "Heavy RUC volume":
        return "Not emitted by parent component runs; future component-level replay required."
    return state.get("missing_message") or "Panel data was not emitted by this replay pack."


def page5_deeper_explainability_note(stream_label: str) -> str:
    if stream_label == "PED VKT per capita":
        return (
            "What would be needed for deeper explainability? Feature-level refit and exact inner weighted replay "
            "remain future audit layers."
        )
    if stream_label == "Heavy RUC volume":
        return (
            "What would be needed for deeper explainability? Rerun C1-C4 component builders with "
            "coefficients/importances and scenario perturbations."
        )
    return ""


def short_stream_label(stream_label: str) -> str:
    return {
        "PED VKT per capita": "PED",
        "Light RUC volume": "Light RUC",
        "Heavy RUC volume": "Heavy RUC",
    }.get(stream_label, stream_label)


def stream_repro_approach(stream_label: str) -> str:
    return {
        "PED VKT per capita": "Component C1 (100% weight)",
        "Light RUC volume": "Two-stage OLS base plus GBM residual correction",
        "Heavy RUC volume": "Four-component weighted ensemble",
    }.get(stream_label, "Replay pack evidence")


def stream_repro_description(stream_label: str) -> str:
    return {
        "PED VKT per capita": "PED is exact at stored component-prediction level; inner HPO/static-solver rebuild remains a future audit layer.",
        "Light RUC volume": "Two-stage OLS base plus GBM residual correction, exactly replayed against evidence predictions.",
        "Heavy RUC volume": "Four-component weighted ensemble exactly replayed against evidence predictions.",
    }.get(stream_label, "Replay-pack prediction reconstruction.")


def stream_repro_caveat(stream_label: str) -> str:
    return {
        "PED VKT per capita": "Inner HPO/static-solver audit: partial",
        "Light RUC volume": "-",
        "Heavy RUC volume": "-",
    }.get(stream_label, "-")


def page5_build_flow_steps(stream_label: str) -> list[tuple[str, str]]:
    common = [
        ("Target", "Plain-English model target from the governed evidence pack."),
        ("Transform", "Target and features are transformed only as recorded in the replay pack."),
        ("Window", "Rolling or expanding training window retained from source evidence."),
        ("Base model", "Stream-specific base model or stored component prediction."),
        ("Residual / Ensemble", "Residual correction for Light RUC, weighted ensemble for Heavy RUC, C1 replay for PED."),
        ("Final prediction", "Back-transform and combine to reproduce final prediction."),
        ("Score basis", "Paper-style and operational scorecards remain audit evidence only."),
    ]
    if stream_label == "Light RUC volume":
        return [
            ("Target", "Light RUC net kilometres from the governed evidence pack."),
            ("Transform", "Log target used for base and residual replay."),
            ("Window", "36-quarter rolling OLS and residual window."),
            ("Base model", "Schiff-style OLS base prediction on log target."),
            ("Residual / Ensemble", "GBM residual correction added on log scale."),
            ("Final prediction", "exp(base log prediction + residual log prediction) equals final prediction."),
            ("Score basis", "Paper-style horizon MAPE and operational pooled scorecards."),
        ]
    if stream_label == "Heavy RUC volume":
        return [
            ("Target", "Heavy RUC net kilometres from the governed evidence pack."),
            ("Transform", "Component outputs retained in native prediction units."),
            ("Window", "Component windows inferred from replay-pack registry."),
            ("Base model", "Four stored component predictors."),
            ("Residual / Ensemble", "C1*w1 + C2*w2 + C3*w3 + C4*w4."),
            ("Final prediction", "Weighted component contributions sum to final prediction."),
            ("Score basis", "Paper-style horizon MAPE and operational pooled scorecards."),
        ]
    if stream_label == "PED VKT per capita":
        return [
            ("Target", "PED VKT per capita from the governed evidence pack."),
            ("Transform", "Stored parent component predictions are replayed; no refit is claimed."),
            ("Window", "Inherited from the HPO/static-solver parent component."),
            ("Base model", "HPO/static-solver component C1."),
            ("Residual / Ensemble", "Single outer component at 100%; inner HPO audit is partial."),
            ("Final prediction", "The stored component prediction C1 equals the final prediction within tolerance."),
            ("Score basis", "Paper-style horizon MAPE and operational pooled scorecards."),
        ]
    return common


def _short_text(value: Any, limit: int) -> str:
    if value is None:
        text = ""
    else:
        try:
            text = "" if bool(pd.isna(value)) else str(value)
        except (TypeError, ValueError):
            text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}..."


def page5_registry_frame(packs: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    row_limit = 1 if len(packs) > 1 else 4
    for label, pack in packs.items():
        raw = pack.table("model_registry")
        if raw.empty:
            continue
        scorecard = pack.table("scorecard_summary")
        score_basis = "-"
        if "score_basis" in scorecard.columns and scorecard["score_basis"].notna().any():
            score_basis = ", ".join(
                scorecard["score_basis"].dropna().astype(str).drop_duplicates().map(score_basis_label).head(2)
            )
        for _, row in raw.head(row_limit).iterrows():
            rows.append(
                {
                    "Stream": short_stream_label(label),
                    "Target": first_non_empty(row, ["target", "target_column"], default=label),
                    "Algorithm": first_non_empty(row, ["algorithm", "model_role"], default="-"),
                    "Window": page5_window_text(row),
                    "Hyperparameters": first_non_empty(row, ["hyperparameters_json", "Hyperparameters", "feature_columns_json"], default="-"),
                    "Score basis": first_non_empty(row, ["score_basis"], default=score_basis),
                    "Source script/run": page5_public_source_reference(
                        first_non_empty(row, ["source_script", "source_parent_run", "parent_run", "source_run"], default="-")
                    ),
                    "Status": first_non_empty(row, ["reproducibility_status", "reproducibility_level"], default="exact replay"),
                }
            )
    frame = pd.DataFrame(rows)
    for col in frame.columns:
        frame[col] = frame[col].map(lambda value: _short_text(value, 70))
    return frame


def page5_public_source_reference(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text or text == "-":
        return "-"
    try:
        pack = load_ped_inner_hpo_audit_pack()
        return ped_inner_hpo_public_source_reference(pack, text)
    except Exception:
        return _strip_local_source_path(text)


def _strip_local_source_path(value: str) -> str:
    normalised = value.replace("\\", "/")
    if any(token in normalised.lower() for token in ["c:/users", "downloads", "onedrive", "appdata"]):
        return Path(normalised).name or "local source path hidden"
    return value


def first_non_empty(row: pd.Series, columns: list[str], *, default: str = "-") -> str:
    for col in columns:
        if col in row.index and pd.notna(row[col]) and str(row[col]).strip():
            return str(row[col])
    return default


def page5_window_text(row: pd.Series) -> str:
    if "window" in row.index and pd.notna(row["window"]):
        return str(row["window"])
    if "window_length" in row.index and pd.notna(row["window_length"]):
        return f"{row['window_length']} quarters"
    if "window_type" in row.index and pd.notna(row["window_type"]):
        return str(row["window_type"])
    return "-"


def page5_component_diagram_html(packs: dict[str, Any]) -> str:
    diagrams = []
    ordered = ["Light RUC volume", "Heavy RUC volume", "PED VKT per capita"]
    labels = [label for label in ordered if label in packs] + [label for label in packs if label not in ordered]
    for label in labels:
        pack = packs[label]
        diagrams.append(
            "<div class='page5-diagram-row'>"
            f"<div class='page5-diagram-label'>{html.escape(short_stream_label(label))}</div>"
            f"<div class='page5-diagram-chain'>{page5_component_chain_html(label, pack)}</div>"
            "</div>"
        )
    return "".join(diagrams) if diagrams else "<div class='page5-panel-sub'>No component trace pack is available.</div>"


def page5_component_chain_html(stream_label: str, pack: Any) -> str:
    if stream_label == "Light RUC volume":
        return (
            node_html("Base log prediction<br>(OLS on logs)", "blue")
            + op_html("+")
            + node_html("Residual log prediction<br>(GBM)", "green")
            + op_html("&rarr;")
            + node_html("Final prediction<br>= exp(base_log + residual_log)", "blue")
        )
    weights = reproducibility_ensemble_weight_view(pack)
    if stream_label == "Heavy RUC volume" and not weights.empty:
        pieces = []
        for _, row in weights.head(4).iterrows():
            comp = str(row.get("Component", "C?"))
            weight = pd.to_numeric(pd.Series([row.get("Weight")]), errors="coerce").iloc[0]
            weight_text = f"w={weight:.4f}" if pd.notna(weight) else "w=n/a"
            pieces.append(node_html(f"{html.escape(comp)}<br>{html.escape(weight_text)}", "blue"))
        return op_html("+").join(pieces) + op_html("&rarr;") + node_html("Final prediction<br>= sum(Wi x Pi)", "blue")
    if stream_label == "PED VKT per capita":
        return node_html("Component C1<br>(Weight = 100%)", "purple") + op_html("&rarr;") + node_html("Final prediction = C1<br>(100% weight)", "blue")
    return node_html("Component trace unavailable", "blue")


def node_html(text: str, tone: str) -> str:
    return f"<div class='page5-node {html.escape(tone)}'>{text}</div>"


def op_html(text: str) -> str:
    return f"<div class='page5-op'>{text}</div>"


def page5_coefficients_figure(pack: Any) -> go.Figure:
    coeff = reproducibility_coefficients_view(pack)
    if coeff.empty or "coefficient" not in coeff.columns:
        return page5_empty_figure("Coefficient table unavailable for this replay pack.")
    frame = coeff.copy()
    frame["coef"] = pd.to_numeric(frame["coefficient"], errors="coerce")
    frame = frame.dropna(subset=["coef"])
    if frame.empty:
        return page5_empty_figure("Coefficient artifacts were not emitted by the parent run.")
    frame["feature_label"] = frame.get("feature", pd.Series(["feature"] * len(frame))).astype(str).map(lambda value: _short_text(value, 30))
    summary = frame.groupby("feature_label", as_index=False)["coef"].mean().assign(abs_coef=lambda df: df["coef"].abs())
    summary = summary.sort_values("abs_coef", ascending=False).head(6).sort_values("coef")
    fig = go.Figure(
        go.Scatter(
            x=summary["coef"],
            y=summary["feature_label"],
            mode="markers",
            marker=dict(color="#002B5C", size=9),
            hovertemplate="Feature: %{y}<br>Coefficient: %{x:.4f}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_color="#94A3B8", line_dash="dot")
    fig.update_layout(height=255, margin=dict(l=8, r=8, t=10, b=28), xaxis_title="Coefficient", yaxis_title="")
    return fig


def page5_training_window_figure(pack: Any) -> go.Figure:
    trace = reproducibility_training_window_view(pack)
    if trace.empty:
        return page5_empty_figure("Training-window trace is unavailable.")
    frame = trace.copy()
    origin_col = "origin" if "origin" in frame.columns else "Origin"
    y_col = next((col for col in ["n_train", "Window quarters", "window_length"] if col in frame.columns), None)
    if y_col is None:
        frame["row_count"] = range(1, len(frame) + 1)
        y_col = "row_count"
    frame[y_col] = pd.to_numeric(frame[y_col], errors="coerce")
    frame = frame.dropna(subset=[origin_col, y_col]).head(80)
    if frame.empty:
        return page5_empty_figure("Training-window metadata is descriptive only for this pack.")
    fig = go.Figure(
        go.Scatter(
            x=frame[origin_col].astype(str),
            y=frame[y_col],
            mode="lines+markers",
            line=dict(color="#002B5C", width=2),
            marker=dict(size=5),
            hovertemplate="Origin: %{x}<br>Trace value: %{y:.0f}<extra></extra>",
        )
    )
    fig.update_layout(height=255, margin=dict(l=8, r=8, t=10, b=28), xaxis_title="Origin", yaxis_title=str(y_col))
    fig.update_xaxes(nticks=5)
    return fig


def page5_empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False, xref="paper", yref="paper", font=dict(color="#64748B"))
    fig.update_layout(height=255, margin=dict(l=8, r=8, t=10, b=28), xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def render_page5_download_buttons(
    selected_stream: str,
    loaded_packs: dict[str, Any | None],
    workbook_manifest: dict[str, Any],
    *,
    key_prefix: str,
) -> None:
    pack = page5_analytics_pack(selected_stream, loaded_packs)
    st.download_button(
        "workbook/manifest",
        data=json.dumps(workbook_manifest, indent=2).encode("utf-8"),
        file_name="source_workbook_manifest.json",
        mime="application/json",
        use_container_width=True,
        key=f"{key_prefix}_download_source_workbook_manifest",
    )
    if pack is None:
        st.caption("No selected reproducibility pack is available.")
        return
    downloads = [
        ("model_registry.parquet", _csv_bytes(reproducibility_registry_view(pack)), f"{pack.config.stream_key}_model_registry.csv", "text/csv"),
        ("component_trace.parquet", _csv_bytes(reproducibility_component_trace_view(pack, limit=10_000)), f"{pack.config.stream_key}_component_trace.csv", "text/csv"),
        ("feature_importance.csv", _csv_bytes(reproducibility_feature_importance_view(pack)), f"{pack.config.stream_key}_feature_importance.csv", "text/csv"),
        ("scenario_sensitivities.csv", _csv_bytes(reproducibility_sensitivity_view(pack)), f"{pack.config.stream_key}_scenario_sensitivities.csv", "text/csv"),
    ]
    report_path = pack.root / pack.config.report_file
    if report_path.exists():
        downloads.append((pack.config.report_file, report_path.read_bytes(), pack.config.report_file, "text/markdown"))
    downloads.append((f"{pack.config.stream_key}_reproducibility_pack.zip", _pack_zip_bytes(pack), f"{pack.config.stream_key}_reproducibility_pack.zip", "application/zip"))
    for idx, (label, data, filename, mime) in enumerate(downloads):
        st.download_button(
            label,
            data=data,
            file_name=filename,
            mime=mime,
            use_container_width=True,
            key=f"{key_prefix}_download_{pack.config.stream_key}_{idx}",
        )


def source_workbook_manifest() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parent
    repo_path = repo_root / SOURCE_WORKBOOK_REPO_PATH
    candidates: list[tuple[str, Path]] = [("repo_copy", repo_path)]
    configured_path = os.environ.get(SOURCE_WORKBOOK_ENV_VAR, "").strip()
    if configured_path:
        candidates.append(("environment_reference", Path(configured_path).expanduser()))
    candidates.extend(_source_workbook_paths_from_repro_manifests(repo_root))
    selected_label = ""
    selected_path: Path | None = None
    for label, path in candidates:
        if path.exists():
            selected_label = label
            selected_path = path
            break
    if selected_path is None:
        manifest: dict[str, Any] = {
            "available": False,
            "status": "missing",
            "status_label": "workbook not found",
            "repo_path": str(repo_path),
            "configured_env_var": SOURCE_WORKBOOK_ENV_VAR,
            "candidate_paths": [str(path) for _, path in candidates],
            "note": "The workbook is optional; reproducibility page falls back to Parquet replay packs.",
        }
    else:
        stat = selected_path.stat()
        sha256 = hashlib.sha256(selected_path.read_bytes()).hexdigest()
        manifest = {
            "available": True,
            "status": selected_label,
            "status_label": "repo workbook copy" if selected_label == "repo_copy" else "external workbook reference",
            "path": str(selected_path),
            "repo_path": str(repo_path),
            "configured_env_var": SOURCE_WORKBOOK_ENV_VAR,
            "candidate_paths": [str(path) for _, path in candidates],
            "filename": selected_path.name,
            "size_bytes": int(stat.st_size),
            "modified_time": pd.Timestamp(stat.st_mtime, unit="s").isoformat(),
            "sha256": sha256,
            "note": "Manifest only; workbook values are not used to alter dashboard chart-source tables.",
        }
    target = repo_root / SOURCE_WORKBOOK_MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _source_workbook_paths_from_repro_manifests(repo_root: Path) -> list[tuple[str, Path]]:
    root = repo_root / "data" / "dashboard_evidence_pack_reproducibility"
    candidates: list[tuple[str, Path]] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        path_values: list[str] = []
        source_workbook = manifest.get("source_workbook")
        if isinstance(source_workbook, str):
            path_values.append(source_workbook)
        provenance = manifest.get("workbook_provenance")
        if isinstance(provenance, dict):
            workbook = provenance.get("workbook")
            if isinstance(workbook, str):
                path_values.append(workbook)
        for raw_path in path_values:
            path = Path(raw_path).expanduser()
            label = f"repro_manifest_{manifest_path.parent.name}"
            candidates.append((label, path))
    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for label, path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            deduped.append((label, path))
    return deduped


def reproducibility_build_flow_table(stream_label: str) -> pd.DataFrame:
    if stream_label == "All streams":
        rows: list[dict[str, str]] = []
        for label in reproducibility_stream_labels():
            for step, description in page5_build_flow_steps(label):
                rows.append({"Stream": label, "Step": step, "Evidence": description})
        return pd.DataFrame(rows)
    return pd.DataFrame(
        {"Step": step, "Evidence": description}
        for step, description in page5_build_flow_steps(stream_label)
    )


def reproducibility_glossary_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("MAPE", "Mean Absolute Percentage Error; lower means a closer forecast."),
            ("paper-style MAPE", "Average horizon MAPE on the governed paper-style score basis."),
            ("operational MAPE", "Operational pooled MAPE used for cross-checking live model behaviour."),
            ("lag", "A previous-period value used as a model input."),
            ("dummy variable", "A 0/1 indicator that switches an event or period on or off."),
            ("Ridge alpha", "Regularisation strength that shrinks unstable coefficients."),
            ("GBM learning_rate", "How much each boosting tree is allowed to adjust the prediction."),
            ("n_estimators", "Number of trees in the boosted residual model."),
            ("max_depth", "Maximum tree depth; higher values permit more interactions."),
            ("subsample", "Share of rows sampled by each boosting step."),
            ("ensemble weight", "Weight applied to a component model before combining predictions."),
            ("component contribution", "Share or weight of a model component in the final forecast; this is not variable-level feature importance."),
            ("feature importance", "Variable-level contribution inside a fitted model, when the replay pack emits it."),
            ("residual", "The part of actual demand not explained by the base prediction."),
            ("fitted value", "The model prediction on the training or validation row."),
            ("coefficient", "The estimated size and direction of a linear-model relationship."),
            ("Replay pack", "Read-only Parquet files that replay finalist predictions for governance review."),
            ("Component trace", "Row-level path from prediction components to the final prediction."),
            ("Chart-source isolation", "Proof that replay packs do not rewrite main chart-source tables."),
        ],
        columns=["Term", "Meaning"],
    )


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _pack_zip_bytes(pack: Any) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in pack.config.required_files:
            path = pack.root / name
            if path.exists():
                archive.write(path, arcname=f"{pack.config.stream_key}/{name}")
    return buffer.getvalue()


def _widget_key(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")


def central_error_window(qpred: pd.DataFrame, lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    if qpred.empty or "error_pct" not in qpred.columns:
        return qpred
    values = pd.to_numeric(qpred["error_pct"], errors="coerce")
    valid = values.dropna()
    if len(valid) < 20:
        return qpred
    low, high = valid.quantile([lower, upper])
    return qpred[values.between(low, high, inclusive="both")].copy()


def render_scenario_comparison(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    render_action_card("Scenario Comparison")
    recommended = common_filter(score_basis_projected(loaded.data.get("recommended", pd.DataFrame()), controls), controls, include_source_variant=False)
    summary = common_filter(score_basis_projected(loaded.data.get("summary", pd.DataFrame()), controls), controls)
    paired = common_filter(loaded.data.get("paired_vs_schiff", pd.DataFrame()), controls, include_source_variant=False)
    qpred = common_filter(loaded.data.get("quarterly_predictions", pd.DataFrame()), controls, include_source_variant=False)

    # The governed evidence pack carries exactly one comparison: refined
    # finalists versus the Schiff specification benchmark on the FY25 baseline.
    # These are fixed facts of the pack, so they render as a read-only summary
    # (the former "Edit" selectboxes only changed labels, never the data).
    scenario_a = "Refined Finalist Ensemble"
    scenario_b = SCHIFF_SPEC_BENCHMARK_LABEL
    baseline = "Baseline FY25"

    with st.container(border=True):
        filter_summary_grid(
            [
                ("Scenario A", scenario_a),
                ("Scenario B", scenario_b),
                ("Baseline", baseline),
            ]
        )
        st.caption(
            "Fixed governed comparison from the evidence pack. Use the global Score Basis "
            "filter to switch between paper-style and operational scorecards."
        )

    comparison = evidence_scenario_comparison_frame(loaded, controls)
    if comparison.empty:
        comparison = scenario_comparison_frame(recommended, loaded.data.get("schiff_df", summary), paired)
    scenario_stress_frame = selected_stress_frame(loaded, controls)
    story = governance_story_summary(
        recommended,
        paired,
        scenario_stress_frame,
        loaded.data.get("errors", pd.DataFrame()),
    )
    gov_kpi_grid(scenario_kpi_cards(recommended, paired, story, comparison))
    watch_note = light_operational_annual_watch_note(
        loaded.data.get("recommended", pd.DataFrame()),
        loaded.data.get("schiff_df", pd.DataFrame()),
    )

    top = st.columns([1.0, 1.0])
    with top[0]:
        chart_card(
            "1. Stream Comparison: Scenario A vs Scenario B",
            f"{score_basis_metric_label(controls.get('score_basis', PAPER_SCORE_BASIS))} - lower is better.",
            compact_figure(plot_scenario_stream_comparison(comparison), 180),
        )
    with top[1]:
        chart_card(
            "2. Improvement vs Benchmark",
            f"Full-sample {score_basis_metric_label(controls.get('score_basis', PAPER_SCORE_BASIS))} gain in percentage points - positive values favour Scenario A.",
            compact_figure(plot_improvement_vs_benchmark(comparison), 180),
        )

    bottom = st.columns([1.0, 1.0])
    with bottom[0]:
        chart_card(
            "3. Horizon Comparison",
            f"{score_basis_metric_label(controls.get('score_basis', PAPER_SCORE_BASIS))} across forecast horizons.",
            compact_figure(plot_horizon_comparison(scenario_horizon_frame(loaded, qpred, controls)), 220),
        )
    with bottom[1]:
        scenario_decision_summary_panel(comparison, watch_note)


def scenario_kpi_cards(
    recommended: pd.DataFrame,
    paired: pd.DataFrame,
    story: pd.DataFrame,
    comparison: pd.DataFrame | None = None,
) -> list[tuple[str, str, str, str, str, str]]:
    finalists = best_by_stream(recommended)
    q_value = float(finalists["quarterly_mape"].mean()) if not finalists.empty and "quarterly_mape" in finalists.columns else float("nan")
    a_value = float(finalists["annual_mape"].mean()) if not finalists.empty and "annual_mape" in finalists.columns else float("nan")
    if comparison is not None and not comparison.empty and "quarterly_gain_pp" in comparison.columns:
        gain = float(pd.to_numeric(comparison["quarterly_gain_pp"], errors="coerce").mean())
        gain_source = "Full-sample qtr gain"
    else:
        gain = (
            float(pd.to_numeric(paired["mape_improvement_pct_points"], errors="coerce").mean())
            if not paired.empty and "mape_improvement_pct_points" in paired.columns
            else float("nan")
        )
        gain_source = "Common-pair qtr gain"
    win_rate = (
        float(pd.to_numeric(paired["challenger_win_rate"], errors="coerce").mean())
        if not paired.empty and "challenger_win_rate" in paired.columns
        else float("nan")
    )
    beats = int((story.get("schiff_status", pd.Series(dtype=str)) == "Beats Schiff").sum()) if story is not None and not story.empty else 0
    total = len(story) if story is not None else 0
    gain_value = f"{gain:.2f} pp" if pd.notna(gain) else "-"
    gain_delta = "A better" if pd.notna(gain) and gain > 0 else "Benchmark better" if pd.notna(gain) else ""
    return [
        ("Quarterly MAPE", format_percent(q_value), "Scenario A finalist mean", "", "good", "Q"),
        ("Annual MAPE", format_percent(a_value), "Scenario A finalist mean", "", "good", "A"),
        ("Gain vs benchmark", gain_value, f"{gain_source} vs Schiff specification benchmark; {format_percent(win_rate, 1)} paired win", gain_delta, "good" if pd.notna(gain) and gain > 0 else "mixed", "B"),
        ("Decision status", f"{beats}/{total}", "streams beat Schiff specification", "", "good" if total and beats >= 2 else "mixed", "D"),
    ]


def evidence_scenario_comparison_frame(loaded: LoadedRun, controls: dict[str, Any]) -> pd.DataFrame:
    comparison = loaded.data.get("scenario_comparison", pd.DataFrame())
    if comparison is None or comparison.empty:
        return pd.DataFrame()
    data = project_scenario_comparison_frame(
        comparison,
        controls.get("score_basis", PAPER_SCORE_BASIS),
        loaded.data.get("recommended", pd.DataFrame()),
        loaded.data.get("schiff_df", pd.DataFrame()),
    )
    data = common_filter(data, controls, include_source_variant=False).copy()
    rename_map = {
        "full_sample_qtr_gain_pp": "quarterly_gain_pp",
        "full_sample_annual_gain_pp": "annual_gain_pp",
        "paired_win_rate_pct": "win_rate",
    }
    for source, target in rename_map.items():
        if source in data.columns and target not in data.columns:
            data[target] = data[source]
    required = [
        "stream",
        "stream_label",
        "finalist_model",
        "schiff_model",
        "finalist_quarterly_mape",
        "schiff_quarterly_mape",
        "quarterly_gain_pp",
        "finalist_annual_mape",
        "schiff_annual_mape",
        "annual_gain_pp",
        "win_rate",
        "recommendation",
    ]
    for column in required:
        if column not in data.columns:
            data[column] = pd.NA
    return data[required + [column for column in data.columns if column not in required]]


def scenario_comparison_frame(recommended: pd.DataFrame, schiff_rows: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    finalists = best_by_stream(recommended)
    schiff = best_by_stream(schiff_rows[schiff_rows["is_schiff"]]) if "is_schiff" in schiff_rows.columns else best_by_stream(schiff_rows)
    if finalists.empty or schiff.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    paired_by_stream = paired.set_index("stream_label") if not paired.empty and "stream_label" in paired.columns else pd.DataFrame()
    for _, finalist in finalists.iterrows():
        stream = finalist.get("stream")
        stream_schiff = schiff[schiff["stream"].astype(str).eq(str(stream))] if "stream" in schiff.columns else pd.DataFrame()
        if stream_schiff.empty:
            continue
        benchmark = stream_schiff.iloc[0]
        win_rate = pd.NA
        if not paired_by_stream.empty and finalist.get("stream_label") in paired_by_stream.index:
            win_rate = paired_by_stream.loc[finalist.get("stream_label")].get("challenger_win_rate")
        fq = pd.to_numeric(finalist.get("quarterly_mape"), errors="coerce")
        fa = pd.to_numeric(finalist.get("annual_mape"), errors="coerce")
        sq = pd.to_numeric(benchmark.get("quarterly_mape"), errors="coerce")
        sa = pd.to_numeric(benchmark.get("annual_mape"), errors="coerce")
        rows.append(
            {
                "stream": stream,
                "stream_label": finalist.get("stream_label"),
                "finalist_model": finalist.get("model"),
                "schiff_model": benchmark.get("model"),
                "finalist_quarterly_mape": fq,
                "schiff_quarterly_mape": sq,
                "quarterly_gain_pp": sq - fq if pd.notna(sq) and pd.notna(fq) else pd.NA,
                "finalist_annual_mape": fa,
                "schiff_annual_mape": sa,
                "annual_gain_pp": sa - fa if pd.notna(sa) and pd.notna(fa) else pd.NA,
                "win_rate": win_rate,
            }
        )
    return pd.DataFrame(rows)


def scenario_horizon_frame(loaded: LoadedRun, qpred: pd.DataFrame, controls: dict[str, Any] | None = None) -> pd.DataFrame:
    controls = controls or {"score_basis": PAPER_SCORE_BASIS}
    horizon = selected_horizon_frame(loaded, controls)
    required_streams = set(loaded.data.get("recommended", pd.DataFrame()).get("stream_label", pd.Series(dtype=str)).dropna().astype(str))
    if horizon is not None and not horizon.empty:
        existing_streams = set(horizon.get("stream_label", pd.Series(dtype=str)).dropna().astype(str))
        if required_streams and required_streams.issubset(existing_streams):
            return horizon
    if qpred.empty or not {"selected_role", "horizon", "ape", "stream_label"}.issubset(qpred.columns):
        return horizon if horizon is not None else pd.DataFrame()
    data = qpred.copy()
    data["scenario_role"] = data["selected_role"].map(
        lambda value: "Schiff" if "schiff" in str(value).lower() else "Finalist"
    )
    grouped = data.groupby(["stream", "stream_label", "scenario_role", "horizon"], dropna=False)["ape"].mean().reset_index(name="mape")
    grouped = grouped[grouped["horizon"].between(1, 12)].copy()
    if horizon is None or horizon.empty:
        return grouped
    missing_streams = required_streams.difference(existing_streams)
    if not missing_streams:
        return horizon
    supplement = grouped[grouped["stream_label"].astype(str).isin(missing_streams)]
    return pd.concat([horizon, supplement], ignore_index=True)


def light_operational_annual_watch_note(recommended: pd.DataFrame, schiff_df: pd.DataFrame) -> str:
    if recommended.empty or schiff_df.empty:
        return ""
    finalist = recommended[recommended.get("stream_label", pd.Series(dtype=str)).astype(str).eq("Light RUC volume")]
    benchmark = schiff_df[schiff_df.get("stream_label", pd.Series(dtype=str)).astype(str).eq("Light RUC volume")]
    if finalist.empty or benchmark.empty:
        return ""
    finalist_annual = pd.to_numeric(finalist.iloc[0].get("operational_annual_mape"), errors="coerce")
    benchmark_annual = pd.to_numeric(benchmark.iloc[0].get("operational_annual_mape"), errors="coerce")
    finalist_qtr = pd.to_numeric(finalist.iloc[0].get("operational_pooled_mape"), errors="coerce")
    benchmark_qtr = pd.to_numeric(benchmark.iloc[0].get("operational_pooled_mape"), errors="coerce")
    if pd.isna(finalist_annual) or pd.isna(benchmark_annual) or finalist_annual <= benchmark_annual:
        return ""
    qtr_gain = benchmark_qtr - finalist_qtr if pd.notna(finalist_qtr) and pd.notna(benchmark_qtr) else pd.NA
    annual_gap = finalist_annual - benchmark_annual
    qtr_text = f" Operational quarterly gain remains {qtr_gain:.2f} pp." if pd.notna(qtr_gain) else ""
    return (
        "Operational annual watch: Light RUC GBM improves paper-style accuracy, but its operational annual MAPE "
        f"({format_percent(finalist_annual)}) is weaker than the Schiff specification benchmark "
        f"({format_percent(benchmark_annual)}), a {annual_gap:.2f} pp annual gap.{qtr_text}"
    )


SUMMARY_FIELD_TOOLTIPS = {
    "Schiff Spec Qtr": (
        "Quarterly MAPE for the Schiff specification benchmark under the active score basis. Lower is better."
    ),
    "Finalist Qtr": "Quarterly MAPE for the selected finalist under the active score basis. Lower is better.",
    "Full-sample Qtr Gain": (
        "Schiff benchmark quarterly MAPE minus finalist quarterly MAPE, in percentage points. "
        "Positive values mean the finalist has lower error than the Schiff specification benchmark."
    ),
    "Schiff Spec Annual": (
        "Annual MAPE for the Schiff specification benchmark after aggregating quarterly forecasts to annual totals. "
        "Lower is better."
    ),
    "Finalist Annual": (
        "Annual MAPE for the selected finalist after aggregating quarterly forecasts to annual totals. Lower is better."
    ),
    "Full-sample Annual Gain": (
        "Schiff benchmark annual MAPE minus finalist annual MAPE, in percentage points. "
        "Positive values mean the finalist has lower annual error. If this is negative, the stream should be shown "
        "as an annual-watch item."
    ),
    "Paired Win Rate": (
        "The share of matched forecast comparisons where the finalist has lower absolute percentage error than the "
        "Schiff specification benchmark. The comparison uses the same stream, origin, target period and horizon "
        "where possible. A value above 50% means the finalist wins more often than it loses; above roughly 55% is "
        "a stronger governance signal."
    ),
}

RECOMMENDATION_HEADER_TOOLTIP = (
    "Recommendation is based on the combined governance read: paper-style MAPE gain, operational MAPE checks, "
    "annual performance, paired win rate, diagnostics, and known caveats. Promote means the finalist improves the "
    "benchmark on the main score basis and passes the consistency checks. Watch means the model is usable but has "
    "a specific caveat. Needs Stage 2 means the result is not robust enough for full promotion. In short, it weighs "
    "MAPE gain, paired win rate, diagnostics and caveats."
)

RECOMMENDATION_BADGE_TOOLTIPS = {
    "promote": (
        "Promoted because the finalist beats the Schiff specification benchmark on the main scorecard and has "
        "acceptable paired-win and diagnostic evidence."
    ),
    "watch": (
        "Governance watch item. The finalist is useful, but one or more secondary checks needs monitoring."
    ),
    "needs stage 2": (
        "Not fully promoted. Further model refinement or evidence is needed before treating this as the preferred "
        "finalist."
    ),
    "annual watch": (
        "The finalist improves the primary quarterly or paper-style score, but annual aggregation is weaker and "
        "should be monitored."
    ),
}


def _summary_header(label: str) -> str:
    tooltip = SUMMARY_FIELD_TOOLTIPS.get(label)
    if label == "Recommendation":
        tooltip = RECOMMENDATION_HEADER_TOOLTIP
    if not tooltip:
        return html.escape(label)
    return (
        "<span class='summary-header-label'>"
        f"{html.escape(label)}"
        f"{render_info_tooltip(label, tooltip)}"
        "</span>"
    )


def _summary_gain_cell(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    css_class = "summary-gain-positive" if pd.notna(number) and number >= 0 else "summary-gain-negative"
    return f"<span class='{css_class}'>{html.escape(format_pp(value))}</span>"


def _recommendation_badge_tooltip(value: str) -> str:
    lower = value.lower()
    if "annual watch" in lower:
        if "promote" in lower:
            return f"{RECOMMENDATION_BADGE_TOOLTIPS['promote']} {RECOMMENDATION_BADGE_TOOLTIPS['annual watch']}"
        return RECOMMENDATION_BADGE_TOOLTIPS["annual watch"]
    if "needs stage 2" in lower:
        return RECOMMENDATION_BADGE_TOOLTIPS["needs stage 2"]
    if "watch" in lower:
        return RECOMMENDATION_BADGE_TOOLTIPS["watch"]
    if "promote" in lower:
        return RECOMMENDATION_BADGE_TOOLTIPS["promote"]
    return RECOMMENDATION_HEADER_TOOLTIP


def _recommendation_badge(value: Any) -> str:
    text = str(value or "").strip() or "Needs Stage 2"
    lower = text.lower()
    if "needs stage 2" in lower:
        tone = "summary-rec-stage2"
    elif "watch" in lower:
        tone = "summary-rec-watch"
    else:
        tone = "summary-rec-promote"
    tooltip = _recommendation_badge_tooltip(text)
    safe_text = html.escape(text)
    safe_tooltip = html.escape(tooltip)
    return (
        f"<span class='summary-rec-badge {tone}' tabindex='0' title='{safe_tooltip}' "
        f"aria-label='{safe_text}: {safe_tooltip}'>"
        f"{safe_text}"
        f"<span class='summary-tooltip-text' role='tooltip'>{safe_tooltip}</span>"
        "</span>"
    )


def _summary_table_html(headers: list[str], rows: list[list[str]], *, column_widths: list[str] | None = None) -> str:
    colgroup = ""
    if column_widths:
        colgroup = "<colgroup>" + "".join(f"<col style='width:{html.escape(width)}'>" for width in column_widths) + "</colgroup>"
    header_html = "".join(f"<th scope='col'>{_summary_header(label)}</th>" for label in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        "<div class='summary-table-wrap'>"
        "<table class='summary-tooltip-table'>"
        f"{colgroup}<thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody>"
        "</table>"
        "</div>"
    )


def benchmark_summary_table_html(comparison: pd.DataFrame) -> str:
    if comparison.empty:
        return "<div class='summary-table-wrap'><p>Benchmark summary is not available.</p></div>"
    headers = [
        "Stream",
        "Schiff Spec Qtr",
        "Finalist Qtr",
        "Full-sample Qtr Gain",
        "Schiff Spec Annual",
        "Finalist Annual",
        "Full-sample Annual Gain",
        "Paired Win Rate",
    ]
    rows = []
    for _, row in comparison.iterrows():
        rows.append(
            [
                html.escape(str(row.get("stream_label", "-"))),
                html.escape(format_percent(row.get("schiff_quarterly_mape"))),
                html.escape(format_percent(row.get("finalist_quarterly_mape"))),
                _summary_gain_cell(row.get("quarterly_gain_pp")),
                html.escape(format_percent(row.get("schiff_annual_mape"))),
                html.escape(format_percent(row.get("finalist_annual_mape"))),
                _summary_gain_cell(row.get("annual_gain_pp")),
                html.escape(format_percent(row.get("win_rate"))),
            ]
        )
    return _summary_table_html(headers, rows)


def decision_summary_table_html(decisions: pd.DataFrame) -> str:
    if decisions.empty:
        return "<div class='summary-table-wrap'><p>Decision summary rows are not available.</p></div>"
    qtr_col = "Full-sample Qtr Gain" if "Full-sample Qtr Gain" in decisions.columns else "Qtr Gain (pp)"
    annual_col = "Full-sample Annual Gain" if "Full-sample Annual Gain" in decisions.columns else "Annual Gain (pp)"
    win_col = "Paired Win Rate" if "Paired Win Rate" in decisions.columns else "Win Rate (%)"
    headers = ["Stream", "Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate", "Recommendation"]
    rows = []
    for _, row in decisions.iterrows():
        rows.append(
            [
                html.escape(str(row.get("Stream", "-"))),
                _summary_gain_cell(row.get(qtr_col)),
                _summary_gain_cell(row.get(annual_col)),
                html.escape(format_percent(row.get(win_col))),
                _recommendation_badge(row.get("Recommendation")),
            ]
        )
    return _summary_table_html(headers, rows, column_widths=["26%", "18%", "20%", "16%", "20%"])


def scenario_decision_summary_panel(comparison: pd.DataFrame, watch_note: str = "") -> None:
    if comparison.empty:
        chart_card("4. Decision Summary", "Executive view by stream.", empty_figure("Scenario comparison rows are not available."))
        return
    table = comparison.copy()
    def recommendation_label(row: pd.Series) -> str:
        supplied = str(row.get("recommendation", "") or "").strip()
        q_gain = pd.to_numeric(row.get("quarterly_gain_pp"), errors="coerce")
        annual_gain = pd.to_numeric(row.get("annual_gain_pp"), errors="coerce")
        win_rate = pd.to_numeric(row.get("win_rate"), errors="coerce")
        if supplied:
            if supplied == "Promote" and pd.notna(annual_gain) and annual_gain < 0:
                return "Promote - Annual Watch"
            return supplied
        if pd.notna(q_gain) and q_gain > 0 and (pd.isna(win_rate) or win_rate >= 55):
            return "Promote - Annual Watch" if pd.notna(annual_gain) and annual_gain < 0 else "Promote"
        return "Needs Stage 2"

    table["Recommendation"] = table.apply(recommendation_label, axis=1)
    display = table.rename(
        columns={
            "stream_label": "Stream",
            "quarterly_gain_pp": "Full-sample Qtr Gain",
            "annual_gain_pp": "Full-sample Annual Gain",
            "win_rate": "Paired Win Rate",
        }
    )[["Stream", "Full-sample Qtr Gain", "Full-sample Annual Gain", "Paired Win Rate", "Recommendation"]]
    subtitle = (
        "Gains compare full-sample finalist versus the Schiff specification benchmark; "
        "win rate uses common forecast-pair validation."
    )
    if watch_note:
        subtitle = f"{subtitle} {watch_note}"
    html_chart_card(
        "4. Decision Summary",
        subtitle,
        decision_summary_table_html(display),
    )


def scenario_best_paired_by_stream(paired: pd.DataFrame) -> pd.DataFrame:
    if paired.empty or "stream_label" not in paired.columns or "mape_improvement_pct_points" not in paired.columns:
        return paired
    data = paired.copy()
    data["_gain"] = pd.to_numeric(data["mape_improvement_pct_points"], errors="coerce")
    ranked = data.dropna(subset=["_gain"]).sort_values(["stream_label", "_gain"], ascending=[True, False])
    if ranked.empty:
        return paired.head(0)
    return ranked.groupby("stream_label", as_index=False, group_keys=False).head(1).drop(columns=["_gain"])


def scenario_paired_display_rows(paired: pd.DataFrame) -> pd.DataFrame:
    best = scenario_best_paired_by_stream(paired)
    if best.empty or "stream_label" not in best.columns:
        return best
    display = best.copy()
    if "challenger" in display.columns:
        display["challenger"] = display["stream_label"]
    return display


def scenario_model_test_panel(story: pd.DataFrame, paired: pd.DataFrame) -> None:
    with st.container(border=True):
        st.markdown("#### 5. Model & Test Summary")
        st.caption("Stream-level paired evidence and governance status.")
        if story.empty:
            warning_panel("No stream-level governance story is available for the selected filters.")
            return
        best_pairs = scenario_best_paired_by_stream(paired)
        gain_lookup = (
            best_pairs.set_index("stream_label")["mape_improvement_pct_points"].to_dict()
            if not best_pairs.empty and {"stream_label", "mape_improvement_pct_points"}.issubset(best_pairs.columns)
            else {}
        )
        for _, row in story.head(3).iterrows():
            stream = str(row.get("stream_label", "Stream"))
            status = str(row.get("decision_status", "Needs Stage 2"))
            schiff = str(row.get("schiff_status", "Not verified"))
            gain = pd.to_numeric(gain_lookup.get(stream), errors="coerce")
            gain_text = format_percent(float(gain)) if pd.notna(gain) else "n/a"
            st.markdown(f"**{stream}** · {status} · {schiff} · paired gain {gain_text}")


def scenario_decision_lens_panel(
    story: pd.DataFrame,
    scenario_a: str,
    scenario_b: str,
    baseline: str,
    qpred_rows: int = 0,
    stress_rows: int = 0,
) -> None:
    beats = int((story.get("schiff_status", pd.Series(dtype=str)) == "Beats Schiff").sum()) if not story.empty else 0
    total = len(story) if not story.empty else 0
    watch = "Light RUC remains the watch stream before Stage 2." if story.astype(str).apply(lambda col: col.str.contains("Light RUC", case=False, na=False)).any().any() else "Review stress-window warnings before Stage 2 promotion."
    conclusion = scenario_decision_lens_summary(story)
    with st.container(border=True):
        st.markdown("#### 6. Decision Lens")
        st.caption(f"{scenario_a} versus {scenario_b}; baseline: {baseline}.")
        st.markdown(f"**Decision rule:** {scenario_decision_rule_text()}")
        st.markdown(f"**Choose Scenario A when:** paired evidence beats the Schiff specification benchmark in {beats}/{total} streams and annual checks remain credible.")
        st.markdown(f"**Use Scenario B when:** structural interpretability is preferred or a stream does not beat the Schiff specification benchmark.")
        st.markdown(f"**Watch point:** {watch}")
        st.markdown(f"**Management read:** {conclusion}")
        st.markdown(f"**Drilldown:** {scenario_drilldown_note(qpred_rows, stress_rows)}")


def scenario_decision_rule_text() -> str:
    return "positive full-sample MAPE gain plus paired challenger win rate above 55%."


def scenario_drilldown_note(qpred_rows: int, stress_rows: int) -> str:
    return (
        f"Forecast and stress evidence keeps full forecast-error tails across {format_count(qpred_rows)} "
        f"prediction rows and {format_count(stress_rows)} stress rows."
    )


def scenario_decision_lens_summary(story: pd.DataFrame) -> str:
    if story.empty:
        return "Scenario evidence is not available for the selected filters."
    beats = int((story.get("schiff_status", pd.Series(dtype=str)) == "Beats Schiff").sum())
    total = len(story)
    watch_streams = story.loc[story.astype(str).apply(lambda row: row.str.contains("Watch|High-risk|mixed", case=False, na=False).any(), axis=1), "stream_label"] if "stream_label" in story.columns else pd.Series(dtype=str)
    watch = ", ".join(watch_streams.dropna().astype(str).head(2)) if not watch_streams.empty else "no major watch stream"
    return f"{beats}/{total} streams beat the Schiff specification benchmark; treat {watch} as the management watch point before Stage 2."


def render_schiff_benchmark_page(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    render_action_card("Schiff Benchmark")
    summary = common_filter(score_basis_projected(loaded.data.get("summary", pd.DataFrame()), controls), controls)
    paired = common_filter(loaded.data.get("paired_vs_schiff", pd.DataFrame()), controls, include_source_variant=False)
    recommended = common_filter(score_basis_projected(loaded.data.get("recommended", pd.DataFrame()), controls), controls, include_source_variant=False)
    schiff_rows = common_filter(score_basis_projected(loaded.data.get("schiff_df", pd.DataFrame()), controls), controls, include_source_variant=False)
    comparison = evidence_scenario_comparison_frame(loaded, controls)
    if comparison.empty:
        comparison = scenario_comparison_frame(recommended, schiff_rows if not schiff_rows.empty else summary, paired)
    gov_kpi_grid(
        basic_cards_as_governance_kpis(
            schiff_kpi_cards(schiff_rows if not schiff_rows.empty else summary, paired, recommended),
            ["S", "Q", "F", "P"],
            ["good", "mixed", "good", "good"],
        )
    )
    watch_note = light_operational_annual_watch_note(
        loaded.data.get("recommended", pd.DataFrame()),
        loaded.data.get("schiff_df", pd.DataFrame()),
    )

    top = st.columns([1.0, 1.0])
    with top[0]:
        chart_card(
            "1. Schiff vs Finalist MAPE",
            f"Schiff specification benchmark versus refined finalist using {score_basis_metric_label(controls.get('score_basis', PAPER_SCORE_BASIS))}.",
            compact_figure(plot_schiff_finalist_mape(comparison), 260),
        )
    with top[1]:
        chart_card(
            "2. Benchmark Horizon Profiles",
            f"{score_basis_metric_label(controls.get('score_basis', PAPER_SCORE_BASIS))} by forecast horizon.",
            compact_figure(plot_horizon_comparison(scenario_horizon_frame(loaded, loaded.data.get("quarterly_predictions", pd.DataFrame()), controls)), 260),
        )

    bottom = st.columns([1.0, 1.0])
    with bottom[0]:
        chart_card(
            "3. Full-sample Gain vs Schiff specification benchmark",
            f"Full-sample {score_basis_metric_label(controls.get('score_basis', PAPER_SCORE_BASIS))} gain versus the Schiff specification benchmark; positive values favour the refined finalist.",
            compact_figure(plot_improvement_vs_benchmark(comparison), 260),
        )
    with bottom[1]:
        summary_subtitle = "Structural benchmark versus refined finalist performance summary."
        if watch_note:
            summary_subtitle = f"{summary_subtitle} {watch_note}"
        html_chart_card(
            "4. Benchmark Summary",
            summary_subtitle,
            benchmark_summary_table_html(comparison),
        )


def schiff_kpi_cards(summary: pd.DataFrame, paired: pd.DataFrame, recommended: pd.DataFrame) -> list[tuple[str, str, str]]:
    schiff_rows = summary[summary["is_schiff"]] if not summary.empty and "is_schiff" in summary.columns else pd.DataFrame()
    schiff_best = best_by_stream(schiff_rows)
    rec_best = best_by_stream(recommended)
    return [
        (
            "Schiff Specification Streams",
            format_count(schiff_best["stream_label"].nunique()) if "stream_label" in schiff_best.columns else "0",
            "Schiff specification benchmark only",
        ),
        (
            "Best Schiff Specification Qtr MAPE",
            format_percent(schiff_best["quarterly_mape"].min()) if "quarterly_mape" in schiff_best.columns and not schiff_best.empty else "-",
            "lower is better",
        ),
        (
            "Best Finalist Qtr MAPE",
            format_percent(rec_best["quarterly_mape"].min()) if "quarterly_mape" in rec_best.columns and not rec_best.empty else "-",
            "refined finalist set",
        ),
        ("Paired Comparisons", format_count(len(paired)), "Schiff specification common pairs"),
    ]


def schiff_replication_notes_panel(paired: pd.DataFrame) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='gov-chart-card chart-card'>"
            "<div class='chart-card-title'>5. Benchmark Comparison Summary</div>"
            f"<div class='chart-card-subtitle'>{schiff_compact_summary(paired)}</div>"
            "<div class='chart-card-title' style='margin-top:0.45rem;'>6. Paper Replication Notes</div>"
            "<div class='chart-card-subtitle'>Structural benchmark evidence and purity guardrails.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "- **Quarterly vs annual MAPE:** Schiff specification benchmark rows only.\n"
            "- **Cross-validation windows:** rolling-origin Stage 1 forecast rows.\n"
            "- **Benchmark purity:** residual/blend challengers are separated.\n"
            "- **Decision use:** test genuine improvement over the structural model."
        )


def schiff_compact_summary(paired: pd.DataFrame) -> str:
    if paired.empty or "mape_improvement_pct_points" not in paired.columns:
        return "No paired-vs-Schiff specification comparison rows are available in this run."
    data = paired.copy()
    data["_gain"] = pd.to_numeric(data["mape_improvement_pct_points"], errors="coerce")
    data = data.dropna(subset=["_gain"]).sort_values("_gain", ascending=False)
    if data.empty:
        return "Paired-vs-Schiff specification rows are present but no numeric gain column could be read."
    best = data.iloc[0]
    stream = str(best.get("stream_label", "best stream"))
    win = pd.to_numeric(best.get("challenger_win_rate"), errors="coerce")
    win_text = f", {format_percent(float(win), 1)} win rate" if pd.notna(win) else ""
    return f"Best paired challenger: {stream} gains {format_percent(float(best['_gain']))} vs Schiff specification benchmark{win_text}."


def qpred_for_stream(loaded: LoadedRun, controls: dict[str, Any], stream: str) -> pd.DataFrame:
    qpred = common_filter(loaded.data.get("quarterly_predictions", pd.DataFrame()), controls, include_source_variant=False)
    if qpred.empty or "stream_label" not in qpred.columns:
        return qpred
    return qpred[qpred["stream_label"] == stream]


def render_executive_summary(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Executive Summary")
    summary = common_filter(loaded.data.get("summary", pd.DataFrame()), controls)
    recommended = common_filter(loaded.data.get("recommended", pd.DataFrame()), controls, include_source_variant=False)
    qpred = common_filter(loaded.data.get("quarterly_predictions", pd.DataFrame()), controls, include_source_variant=False)
    errors = loaded.data.get("errors", pd.DataFrame())
    best = best_by_stream(recommended)
    stress_frame = final_stress_frame(
        loaded.data.get("stress", pd.DataFrame()),
        loaded.data.get("quarterly_predictions", pd.DataFrame()),
        loaded.data.get("annual_predictions", pd.DataFrame()),
        recommended,
        include_extra_buckets=True,
    )
    story = governance_story_summary(recommended, loaded.data.get("paired_vs_schiff", pd.DataFrame()), stress_frame, errors)

    title, narrative, decision_cards = enterprise_decision_brief(story, loaded)
    decision_brief(title, narrative, decision_cards)

    cards = [
        ("Number of streams", format_count(summary["stream_label"].nunique()) if "stream_label" in summary.columns else "-", "Selected run scope"),
        ("Recommended finalist count", format_count(len(recommended)), "Rows in recommendation file"),
        ("Best PED quarterly MAPE", stream_metric(best, "PED VKT per capita"), "Best finalist row"),
        ("Best Light RUC quarterly MAPE", stream_metric(best, "Light RUC volume"), "Weak-stream watch point"),
        ("Best Heavy RUC quarterly MAPE", stream_metric(best, "Heavy RUC volume"), "Best finalist row"),
        ("Model summary rows", format_count(len(summary)), "Rows in final_summary.csv"),
        ("Quarterly prediction rows", format_count(len(qpred)), "Held-out forecast rows"),
        ("Errors logged", format_count(len(errors)), "Errors CSV rows"),
    ]
    kpi_grid(cards)

    section_title("Management Answer")
    info_panel(
        "The cards below answer the review questions directly: which model won, whether the evidence beats the "
        "Schiff specification benchmark, whether stress checks are stable, and what run warnings need attention."
    )
    info_panel("Manager conclusion: " + manager_conclusion(story))
    governance_cards(story)
    display_decision_status(story)
    warning_panel(data_quality_warning_readout(loaded, story))
    st.download_button(
        "Export management summary",
        management_summary_markdown(loaded, story).encode("utf-8"),
        file_name="stage1_management_summary.md",
        mime="text/markdown",
    )

    st.plotly_chart(plot_finalist_accuracy(recommended), use_container_width=True)

    with st.expander("Plain-language model-selection terms", expanded=False):
        for term, explanation in TERM_HELP.items():
            st.markdown(f"**{term}**: {explanation}")


def enterprise_decision_brief(story: pd.DataFrame, loaded: LoadedRun) -> tuple[str, str, list[tuple[str, str, str]]]:
    if story is None or story.empty:
        return (
            "Stage 1 governance decision needs run evidence",
            "The selected run has not produced enough finalist evidence to form a management decision.",
            [
                ("Readiness", "Evidence gap", "Load a completed run folder"),
                ("Benchmark result", "Not verified", "paired-vs-Schiff data unavailable"),
                ("Watch point", "Run evidence", "review Run Audit"),
                ("Next gate", "Stage 1", "model-form evidence required"),
            ],
        )

    beats = int((story.get("schiff_status", pd.Series(dtype=str)) == "Beats Schiff").sum())
    total = len(story)
    high_risk_streams = story.loc[
        story.get("robustness_tone", pd.Series(dtype=str)) == "bad",
        "stream_label",
    ].astype(str).tolist()
    mixed_streams = story.loc[
        story.get("schiff_status", pd.Series(dtype=str)) != "Beats Schiff",
        "stream_label",
    ].astype(str).tolist()
    decision_counts = story.get("decision_status", pd.Series(dtype=str)).value_counts().to_dict()
    top_decision = ", ".join(f"{label}: {count}" for label, count in sorted(decision_counts.items())) or "No decision labels"
    errors = loaded.data.get("errors", pd.DataFrame())
    diagnostics = len(errors)
    readiness = "Management-ready Stage 1 evidence" if total and beats else "Needs governance review"
    weak_stream = ", ".join(mixed_streams or high_risk_streams) or "No benchmark watch point"
    narrative = (
        f"{beats} of {total} stream finalists beat the Schiff specification benchmark on the paired rule. "
        "Treat this as Stage 1 model-form evidence: it supports the challenger shortlist, while Stage 2 must still "
        "test vintage macro, fuel-price, and policy-input uncertainty."
    )
    cards = [
        ("Readiness", readiness, top_decision),
        ("Benchmark result", f"{beats}/{total} beat Schiff specification benchmark", "Schiff specification comparison rule"),
        ("Watch point", weak_stream, "benchmark or stress caveat"),
        ("Next gate", "Stage 2 uncertainty", f"{diagnostics:,} logged diagnostics in Run Audit"),
    ]
    return "Stage 1 governance decision brief", narrative, cards


def stream_metric(best: pd.DataFrame, stream: str) -> str:
    if best.empty or "stream_label" not in best.columns or "quarterly_mape" not in best.columns:
        return "-"
    rows = best[best["stream_label"] == stream]
    if rows.empty:
        return "-"
    return format_percent(rows.iloc[0]["quarterly_mape"])


def data_quality_warning_readout(loaded: LoadedRun, story: pd.DataFrame) -> str:
    missing = int(loaded.file_status["Found?"].ne("Yes").sum()) if not loaded.file_status.empty and "Found?" in loaded.file_status.columns else 0
    errors = loaded.data.get("errors", pd.DataFrame())
    high_risk = []
    mixed = []
    if story is not None and not story.empty:
        high_risk = story.loc[story.get("robustness_tone", pd.Series(dtype=str)) == "bad", "stream_label"].astype(str).tolist()
        mixed = story.loc[story.get("schiff_status", pd.Series(dtype=str)) != "Beats Schiff", "stream_label"].astype(str).tolist()
    parts = ["Data-quality warning panel:"]
    if missing:
        parts.append(f"{missing} expected datasets are missing or workbook-only.")
    if not errors.empty:
        parts.append(f"{len(errors):,} diagnostic rows are logged; review Run Audit before production use.")
    if mixed:
        parts.append(f"Benchmark watch point: {', '.join(mixed)} does not show a clean Schiff specification benchmark win.")
    if high_risk:
        parts.append(f"Stress watch point: {', '.join(high_risk)} crosses the high-risk guide.")
    if len(parts) == 1:
        parts.append("no material missing-file, diagnostic, benchmark, or stress warnings are active.")
    return " ".join(parts)


def management_summary_markdown(loaded: LoadedRun, story: pd.DataFrame) -> str:
    lines = [
        "# NLTF Stage 1 Management Summary",
        "",
        f"Run folder: `{loaded.run_dir}`",
        "",
        "## Manager Conclusion",
        "",
        manager_conclusion(story),
        "",
        "## Stream Decisions",
        "",
        "| Stream | Decision | Winner | Quarterly MAPE | Annual MAPE | Schiff result | Robustness | Warnings |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    if story is not None and not story.empty:
        for _, row in story.sort_values("stream_label").iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("stream_label", "")),
                        str(row.get("decision_status", "")),
                        model_alias(row.get("winning_model", ""), 58),
                        format_percent(row.get("quarterly_mape")),
                        format_percent(row.get("annual_mape")),
                        str(row.get("schiff_summary", "")),
                        str(row.get("robustness_status", "")),
                        str(row.get("warning_summary", "")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Data Quality",
            "",
            data_quality_warning_readout(loaded, story),
            "",
            "Stage 1 is an actual-driver model-form test. It does not settle vintage macro, fuel-price, or policy-input forecast uncertainty.",
        ]
    )
    return "\n".join(lines)


def render_candidate_landscape(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Candidate Landscape")
    info_panel(
        "This view checks whether the selected finalists sit in the lower-left candidate cluster and whether the Schiff "
        "specification benchmark was actually beaten on quarterly and annual accuracy."
    )
    summary = common_filter(loaded.data.get("summary", pd.DataFrame()), controls)
    if summary.empty:
        warning_panel("final_summary.csv or an equivalent file was not found.")
        return
    if controls["top_n"] and "quarterly_mape" in summary.columns:
        finalists = summary[summary.get("is_finalist", False) == True] if "is_finalist" in summary.columns else pd.DataFrame()
        schiff = summary[summary.get("is_schiff", False) == True] if "is_schiff" in summary.columns else pd.DataFrame()
        top = summary.sort_values("quarterly_mape").head(controls["top_n"])
        summary = pd.concat([top, finalists, schiff], ignore_index=True).drop_duplicates()
    if controls.get("hide_outliers") and {"quarterly_mape", "annual_mape"}.issubset(summary.columns):
        summary = hide_candidate_outliers(summary)
    st.plotly_chart(plot_candidate_landscape(summary), use_container_width=True)
    st.caption(
        "Frontier read: finalists and Schiff specification benchmark markers should sit near the lower-left area where both quarterly and "
        "annual MAPE are low. Out-of-range candidates remain available in the table below."
    )
    export_columns = [
        col
        for col in [
            "stage",
            "stream_label",
            "variant",
            "source_family",
            "schiff_class",
            "model",
            "quarterly_mape",
            "annual_mape",
            "quarterly_bias_pct",
            "annual_bias_pct",
            "governance_score",
        ]
        if col in summary.columns
    ]
    if export_columns:
        dataframe_download(summary[export_columns], "Download candidate landscape rows", "stage1_candidate_landscape_filtered.csv")
    with st.expander("Candidate detail rows", expanded=False):
        display_table(
            summary.head(controls["top_n"])[
                [col for col in ["stage", "stream_label", "variant", "source_family", "model", "quarterly_mape", "annual_mape", "governance_score"] if col in summary.columns]
            ],
            caption="Top candidates after the active filters. Long model names are shortened for review.",
            height=420,
        )


def display_decision_status(story: pd.DataFrame) -> None:
    if story.empty or "decision_status" not in story.columns:
        return
    section_title("Decision status")
    status_cards = []
    for _, row in story.sort_values("stream_label").iterrows():
        status_cards.append(
            (
                f"{row.get('stream_label', 'Unknown')} status",
                str(row.get("decision_status", "Needs Stage 2")),
                f"{row.get('schiff_status', 'Not verified')} | {row.get('robustness_status', 'Not verified')}",
            )
        )
    kpi_grid(status_cards)


def hide_candidate_outliers(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    protected = pd.Series(False, index=summary.index)
    if "is_finalist" in summary.columns:
        protected = protected | summary["is_finalist"].fillna(False).astype(bool)
    if "is_schiff" in summary.columns:
        protected = protected | summary["is_schiff"].fillna(False).astype(bool)
    q_cap = pd.to_numeric(summary["quarterly_mape"], errors="coerce").quantile(0.98)
    a_cap = pd.to_numeric(summary["annual_mape"], errors="coerce").quantile(0.98)
    keep = protected | (
        pd.to_numeric(summary["quarterly_mape"], errors="coerce").le(q_cap)
        & pd.to_numeric(summary["annual_mape"], errors="coerce").le(a_cap)
    )
    return summary[keep].copy()


def render_schiff_comparison(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Schiff Benchmark Comparison")
    paired = common_filter(loaded.data.get("paired_vs_schiff", pd.DataFrame()), controls, include_source_variant=False)
    summary = common_filter(loaded.data.get("summary", pd.DataFrame()), controls)
    recommended = common_filter(loaded.data.get("recommended", pd.DataFrame()), controls, include_source_variant=False)
    if paired.empty:
        warning_panel("paired_vs_schiff.csv is missing and no Schiff comparison could be reconstructed.")
    else:
        display = paired.copy()
        display["Interpretation"] = display.apply(schiff_interpretation, axis=1)
        stress_frame = final_stress_frame(
            loaded.data.get("stress", pd.DataFrame()),
            loaded.data.get("quarterly_predictions", pd.DataFrame()),
            loaded.data.get("annual_predictions", pd.DataFrame()),
            recommended,
            include_extra_buckets=True,
        )
        section_title("Schiff Decision Summary")
        governance_cards(governance_story_summary(recommended, paired, stress_frame, loaded.data.get("errors", pd.DataFrame())))
        rename = {
            "stream_label": "Stream",
            "stage": "Stage",
            "baseline": "Baseline",
            "challenger": "Challenger",
            "baseline_mape": "Baseline MAPE",
            "challenger_mape": "Challenger MAPE",
            "mape_improvement_pct_points": "Gain",
            "challenger_win_rate": "Win rate",
            "n_common_pairs": "Common pairs",
        }
        table_cols = [col for col in rename if col in display.columns] + ["Interpretation"]
        table = display[table_cols].rename(columns=rename)
        if "Baseline" in table.columns:
            table.insert(table.columns.get_loc("Baseline"), "Baseline alias", table["Baseline"].map(model_alias))
        if "Challenger" in table.columns:
            table.insert(table.columns.get_loc("Challenger"), "Challenger alias", table["Challenger"].map(model_alias))
        for col in ["Baseline", "Challenger"]:
            if col in table.columns:
                table[col] = table[col].map(lambda value: shorten_model_name(value, 52))
        with st.expander("Paired comparison detail rows", expanded=False):
            st.caption("Paired model comparisons using common forecast pairs. Table includes Gain, Win rate, and Common pairs.")
            display_table(table, height=420)
        st.plotly_chart(plot_paired_improvement(paired, top_n=controls["top_n"]), use_container_width=True)
        st.plotly_chart(plot_paired_scatter(paired), use_container_width=True)

        best = paired.sort_values("mape_improvement_pct_points", ascending=False).groupby("stream_label", as_index=False).head(1)
        if not best.empty:
            section_title("Stream-Level Best Challenger")
            st.plotly_chart(plot_paired_improvement(best, top_n=len(best)), use_container_width=True)

    st.plotly_chart(plot_schiff_benchmark(summary), use_container_width=True)


def schiff_interpretation(row: pd.Series) -> str:
    return schiff_result_label(row.get("mape_improvement_pct_points"), row.get("challenger_win_rate"))


def render_ensemble_composition(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Ensemble Composition")
    weights = common_filter(loaded.data.get("weights", pd.DataFrame()), controls, include_source_variant=False)
    recommended = common_filter(loaded.data.get("recommended", pd.DataFrame()), controls, include_source_variant=False)
    if weights.empty:
        warning_panel("ensemble_weights.csv was not found or has no readable rows.")
        return
    weights = filter_ensemble_methods(weights, controls)
    composition_mode = st.radio(
        "Composition view",
        ["Recommended finalist composition", "PDF/reference finalist composition", "All ensemble weights"],
        horizontal=True,
    )
    weighted_finalists = recommended_models_with_weights(recommended, weights)
    if composition_mode == "PDF/reference finalist composition":
        weights = reference_ensemble_composition()
        info_panel(
            "PDF/reference finalist composition: this mode reproduces the supplied report figure for visual comparison. "
            "Use Recommended or All weights for selected-run solver evidence."
        )
    elif composition_mode == "Recommended finalist composition" and not recommended.empty and "model" in recommended.columns:
        if weighted_finalists:
            weights = weights[weights["ensemble"].astype(str).isin(weighted_finalists)]
        else:
            info_panel(
                "The recommendation file does not contain ensemble names that match ensemble_weights.csv after the "
                "active filters, so available ensemble weights are shown instead."
            )
    if weights.empty:
        warning_panel("No ensemble weights remain after the selected filters.")
        return

    plot_data = weights.copy()
    best_models = best_weighted_finalist_models(recommended, weights)
    if composition_mode == "Recommended finalist composition" and best_models:
        plot_data = plot_data[plot_data["ensemble"].astype(str).isin(best_models)]
        if plot_data.empty:
            plot_data = weights.copy()
    elif composition_mode == "All ensemble weights":
        stream_options = ["All"] + sorted(plot_data["stream_label"].dropna().unique())
        stream_choice = st.selectbox("Stream", stream_options)
        if stream_choice != "All":
            plot_data = plot_data[plot_data["stream_label"] == stream_choice]
        ensemble_options = sorted(plot_data["ensemble"].dropna().astype(str).unique())
        if ensemble_options:
            ensemble_choice = st.selectbox("Ensemble", ensemble_options)
            plot_data = plot_data[plot_data["ensemble"].astype(str) == ensemble_choice]
    fig, mapping = plot_ensemble_composition(plot_data)
    insight = ensemble_composition_insight(plot_data)
    if insight:
        info_panel(insight)
    info_panel(ensemble_method_readout(plot_data, recommended))
    st.plotly_chart(fig, use_container_width=True)
    if not mapping.empty:
        with st.expander("Component label mapping", expanded=False):
            display_table(mapping, height=360)
        if has_origin_weight_history(plot_data):
            st.plotly_chart(plot_weight_over_time(plot_data, mapping), use_container_width=True)
        else:
            st.caption("No origin-level weight history is available for the selected ensemble view.")


def reference_ensemble_composition() -> pd.DataFrame:
    rows = []
    for stream, weights in {
        "PED VKT per capita": [56.3, 31.1, 8.3, 3.1, 1.2],
        "Light RUC volume": [33.3, 33.3, 33.3],
        "Heavy RUC volume": [55.6, 44.4],
    }.items():
        for idx, weight in enumerate(weights, start=1):
            rows.append(
                {
                    "stage": "reference",
                    "stream_label": stream,
                    "ensemble": f"{stream} PDF/reference finalist composition",
                    "component_model": f"Reference component {idx}",
                    "weight": weight,
                    "method": "PDF/reference figure",
                }
            )
    return pd.DataFrame(rows)


def recommended_models_with_weights(recommended: pd.DataFrame, weights: pd.DataFrame) -> set[str]:
    if recommended.empty or weights.empty or "model" not in recommended.columns or "ensemble" not in weights.columns:
        return set()
    ensembles = set(weights["ensemble"].dropna().astype(str))
    return set(recommended[recommended["model"].astype(str).isin(ensembles)]["model"].astype(str))


def best_weighted_finalist_models(recommended: pd.DataFrame, weights: pd.DataFrame) -> set[str]:
    matched = recommended_models_with_weights(recommended, weights)
    if matched and not recommended.empty:
        candidates = recommended[recommended["model"].astype(str).isin(matched)].copy()
        return set(best_by_stream(candidates).get("model", pd.Series(dtype=str)).astype(str))
    if weights.empty or "ensemble" not in weights.columns:
        return set()
    ranked = ensemble_fallback_scores(weights)
    if ranked.empty:
        return set()
    return set(ranked.groupby("stream_label", as_index=False).head(1)["ensemble"].astype(str))


def ensemble_fallback_scores(weights: pd.DataFrame) -> pd.DataFrame:
    if weights.empty or "ensemble" not in weights.columns:
        return pd.DataFrame(columns=["stream_label", "ensemble", "selection_score", "component_count"])
    data = weights.copy()
    group_cols = ["stream_label", "ensemble"]
    if "weight" in data.columns and data["weight"].notna().any():
        data["_abs_weight"] = pd.to_numeric(data["weight"], errors="coerce").abs().fillna(0)
        if "origin" in data.columns and data["origin"].astype(str).str.len().gt(0).any():
            origin_mass = (
                data.groupby(group_cols + ["origin"], dropna=False)["_abs_weight"]
                .sum()
                .reset_index(name="origin_weight_mass")
            )
            scores = origin_mass.groupby(group_cols, dropna=False)["origin_weight_mass"].mean().reset_index(name="selection_score")
        else:
            scores = data.groupby(group_cols, dropna=False)["_abs_weight"].sum().reset_index(name="selection_score")
    else:
        scores = data.groupby(group_cols, dropna=False).size().reset_index(name="selection_score")
    if "component_model" in data.columns:
        components = data.groupby(group_cols, dropna=False)["component_model"].nunique().reset_index(name="component_count")
        scores = scores.merge(components, on=group_cols, how="left")
    else:
        scores["component_count"] = 0
    return scores.sort_values(
        ["stream_label", "selection_score", "component_count", "ensemble"],
        ascending=[True, False, False, True],
    )


def has_origin_weight_history(weights: pd.DataFrame) -> bool:
    return (
        not weights.empty
        and "origin" in weights.columns
        and "weight" in weights.columns
        and weights["origin"].astype(str).str.len().gt(0).any()
        and weights["origin"].nunique() > 1
    )


def ensemble_composition_insight(weights: pd.DataFrame) -> str:
    if weights.empty or "component_model" not in weights.columns:
        return ""
    data = weights.copy()
    if "weight" in data.columns and data["weight"].notna().any():
        numeric_weight = pd.to_numeric(data["weight"], errors="coerce")
        data = data[numeric_weight.abs().gt(1e-6)]
        if data.empty:
            return ""
    group_cols = [col for col in ["stream_label", "ensemble"] if col in weights.columns]
    if not group_cols:
        return ""
    component_counts = data.groupby(group_cols, dropna=False)["component_model"].nunique()
    if component_counts.empty:
        return ""
    if component_counts.max() == 1:
        streams = ", ".join(sorted(data.get("stream_label", pd.Series(dtype=str)).dropna().astype(str).unique()))
        return (
            "Single-component finalist selection: the selected finalist ensemble resolves to one underlying component "
            f"for {streams}. The 100% bars are therefore data-backed selections, not placeholder weights."
        )
    average_components = component_counts.mean()
    return f"Blended finalist selection: selected ensembles average {average_components:.1f} components per stream."


def ensemble_method_readout(weights: pd.DataFrame, recommended: pd.DataFrame) -> str:
    if weights.empty:
        return "Ensemble method read: no ensemble weights are available."
    method_text = (
        weights.get("method", pd.Series("", index=weights.index)).astype(str)
        + " "
        + weights.get("ensemble", pd.Series("", index=weights.index)).astype(str)
    ).str.lower()
    static_count = int(method_text.str.contains("static|solver_static|fixedblend", regex=True).sum())
    prequential_count = int(method_text.str.contains("prequential", regex=True).sum())
    finalist_models = set(best_by_stream(recommended).get("model", pd.Series(dtype=str)).astype(str)) if not recommended.empty else set()
    static_finalists = [model for model in finalist_models if "static" in model.lower() or "fixedblend" in model.lower()]
    prequential_finalists = [model for model in finalist_models if "prequential" in model.lower()]
    if static_finalists and not prequential_finalists:
        return (
            "Ensemble method read: static solver finalist is present without a matching prequential finalist in the "
            "selected winner set. Treat this as a production-safety watch point."
        )
    return (
        f"Ensemble method read: selected rows include {format_count(static_count)} static/fixed-blend weight rows and "
        f"{format_count(prequential_count)} prequential weight rows."
    )


def filter_ensemble_methods(weights: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    out = weights.copy()
    method_text = (
        out.get("method", pd.Series("", index=out.index)).astype(str)
        + " "
        + out.get("ensemble", pd.Series("", index=out.index)).astype(str)
    ).str.lower()
    if not controls["show_static"]:
        out = out[~method_text.str.contains("static|solver_static|fixedblend", regex=True)]
    if not controls["show_prequential"]:
        out = out[~method_text.str.contains("prequential", regex=True)]
    return out


def render_forecasts_and_errors(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Forecasts and Errors")
    qpred = common_filter(loaded.data.get("quarterly_predictions", pd.DataFrame()), controls, include_source_variant=False)
    recommended = common_filter(loaded.data.get("recommended", pd.DataFrame()), controls, include_source_variant=False)
    if qpred.empty:
        warning_panel("quarterly_predictions.csv or an equivalent file was not found.")
        return

    stream_options = sorted(qpred["stream_label"].dropna().unique()) if "stream_label" in qpred.columns else []
    control_cols = st.columns([1.05, 1.75, 1.05, 1.25])
    with control_cols[0]:
        stream_choice = st.selectbox("Forecast stream", stream_options)
    detail = qpred[qpred["stream_label"] == stream_choice] if stream_options else qpred
    if controls["stage"] != "all" and "stage" in detail.columns:
        detail = detail[detail["stage"].astype(str).str.lower() == controls["stage"].lower()]

    model_options = sorted(detail["model"].dropna().astype(str).unique()) if "model" in detail.columns else []
    finalist_default = default_model_index(model_options, recommended, stream_choice)
    with control_cols[1]:
        model_choice = (
            st.selectbox("Model", model_options, index=finalist_default, format_func=lambda value: model_alias(value, 68))
            if model_options
            else None
        )
    if model_choice:
        detail = detail[detail["model"].astype(str) == model_choice]

    origin_choice = None
    with control_cols[2]:
        if "origin" in detail.columns:
            origins = sorted(detail["origin"].dropna().astype(str).unique())
            origin_choice = st.selectbox("Forecast origin", origins, index=max(len(origins) - 1, 0)) if origins else None
    if origin_choice:
        detail = detail[detail["origin"].astype(str) == origin_choice]

    bucket_options = sorted(detail["horizon_bucket"].dropna().unique()) if "horizon_bucket" in detail.columns else []
    with control_cols[3]:
        default_buckets = controls.get("horizon_bucket_filter") or bucket_options
        buckets = st.multiselect("Horizon bucket", bucket_options, default=[bucket for bucket in default_buckets if bucket in bucket_options])
    if buckets is not None:
        detail = detail[detail["horizon_bucket"].isin(buckets)]

    info_panel(forecast_error_readout(detail))
    st.caption(
        "Error percentage is calculated as 100 x (predicted minus actual) divided by actual. "
        "The box plot below uses the recommended finalist rows where they can be matched."
    )
    st.plotly_chart(plot_actual_vs_predicted(detail), use_container_width=True)
    st.plotly_chart(plot_percent_error_over_time(detail), use_container_width=True)

    best_keys = model_key_set(best_by_stream(recommended)) if not recommended.empty else set()
    box_data = qpred
    if best_keys:
        box_data = filter_to_model_keys(box_data, best_keys)
    st.plotly_chart(plot_error_distribution(box_data), use_container_width=True)
    st.plotly_chart(plot_horizon_mape(box_data), use_container_width=True)


def default_model_index(model_options: list[str], recommended: pd.DataFrame, stream_choice: str) -> int:
    if not model_options or recommended.empty or "model" not in recommended.columns:
        return 0
    stream_recs = recommended[recommended["stream_label"] == stream_choice] if "stream_label" in recommended.columns else recommended
    best = best_by_stream(stream_recs)
    if best.empty:
        return 0
    model = str(best.iloc[0]["model"])
    return model_options.index(model) if model in model_options else 0


def render_stress_checks(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Stress and Horizon Checks")
    recommended = common_filter(loaded.data.get("recommended", pd.DataFrame()), controls, include_source_variant=False)
    stress = loaded.data.get("stress", pd.DataFrame())
    qpred = loaded.data.get("quarterly_predictions", pd.DataFrame())
    annual = loaded.data.get("annual_predictions", pd.DataFrame())
    stress_frame = final_stress_frame(stress, qpred, annual, recommended, include_extra_buckets=True)
    if controls["streams"] and "stream_label" in stress_frame.columns:
        stress_frame = stress_frame[stress_frame["stream_label"].isin(controls["streams"])]
    if controls["stage"] != "all" and "stage" in stress_frame.columns:
        stress_frame = stress_frame[stress_frame["stage"].astype(str).str.lower() == controls["stage"].lower()]
    st.plotly_chart(plot_stress_checks(stress_frame), use_container_width=True)
    info_panel(stress_readout(stress_frame))
    info_panel(
        "Light RUC remains a weak-stream watch point. The 2022-23 RUC discount and purchase-timing period is "
        "difficult to model, so a mixed Schiff specification benchmark result should not be presented as a clean benchmark win. Heavy RUC "
        "can also show high stress-period risk, so this page separates Stage 1 model-form evidence from full "
        "end-to-end forecast uncertainty."
    )


def render_model_inventory(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    section_title("Model Inventory")
    summary = common_filter(loaded.data.get("summary", pd.DataFrame()), controls)
    if summary.empty:
        warning_panel("final_summary.csv or an equivalent candidate summary was not found.")
        return

    rank_options = inventory_rank_options(summary)
    with st.expander("Adjust inventory view", expanded=False):
        filter_col, rank_col = st.columns([2, 1])
        with filter_col:
            model_text = st.text_input("Model contains text", value="")
        with rank_col:
            sort_metric = st.radio("Rank by", rank_options or ["quarterly_mape"], horizontal=True)
    if "sort_metric" not in locals():
        sort_metric = rank_options[0] if rank_options else "quarterly_mape"
    if "model_text" in locals() and model_text and "model" in summary.columns:
        summary = summary[summary["model"].astype(str).str.contains(model_text, case=False, na=False)]

    cards, readout = inventory_summary(summary)
    kpi_grid(cards)
    inventory_insight_cards(readout)
    render_model_detail(loaded, summary)

    if sort_metric in summary.columns:
        summary = summary.sort_values(sort_metric).head(controls["top_n"])

    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.plotly_chart(plot_inventory_family_performance(summary, sort_metric), use_container_width=True)
    with chart_cols[1]:
        st.plotly_chart(plot_schiff_class_mix(summary), use_container_width=True)

    columns = [col for col in INVENTORY_COLUMNS if col in summary.columns]
    inventory = summary[columns].copy()
    if "model" in inventory.columns:
        inventory.insert(inventory.columns.get_loc("model"), "model_alias", inventory["model"].map(model_alias))
    with st.expander("Filtered candidate inventory rows", expanded=False):
        display_table(inventory, caption="Filtered candidate inventory. Use the download for full model names and audit detail.", height=520)
    dataframe_download(inventory, "Download filtered table", "stage1_model_inventory_filtered.csv")

    with st.expander("Supporting summary tables", expanded=False):
        for key, label in [
            ("quarterly_summary", "Quarterly summary"),
            ("annual_summary", "Annual summary"),
            ("leaderboards", "Leaderboards"),
        ]:
            frame = loaded.data.get(key, pd.DataFrame())
            if frame.empty:
                st.caption(f"{label}: not available")
            else:
                st.markdown(f"**{label}**")
                display_table(frame.head(500), height=380)


def inventory_summary(summary: pd.DataFrame) -> tuple[list[tuple[str, str, str]], str]:
    if summary.empty:
        cards = [
            ("Filtered rows", "0", "No candidates match the active filters"),
            ("Streams represented", "0", "No stream coverage in current view"),
            ("Source families", "0", "No model families in current view"),
            ("Variants", "0", "No variants in current view"),
        ]
        return cards, "Inventory read: no candidate rows match the active filters."

    stream_count = int(summary["stream_label"].nunique()) if "stream_label" in summary.columns else 0
    family_count = int(summary["source_family"].nunique()) if "source_family" in summary.columns else 0
    variant_count = int(summary["variant"].nunique()) if "variant" in summary.columns else 0
    q_best = _best_inventory_row(summary, "quarterly_mape")
    a_best = _best_inventory_row(summary, "annual_mape")
    cards = [
        ("Filtered rows", format_count(len(summary)), "Rows after active filters"),
        ("Streams represented", format_count(stream_count), "Coverage in current view"),
        ("Source families", format_count(family_count), "Model families in scope"),
        ("Variants", format_count(variant_count), "Feature/specification variants"),
    ]

    read_parts = []
    if q_best is not None:
        read_parts.append(
            "Quarterly leader: "
            f"{model_alias(q_best.get('model', ''), 58)} for {q_best.get('stream_label', 'unknown stream')} "
            f"({format_percent(q_best.get('quarterly_mape'))})"
        )
    if a_best is not None:
        read_parts.append(
            "Annual leader: "
            f"{model_alias(a_best.get('model', ''), 58)} for {a_best.get('stream_label', 'unknown stream')} "
            f"({format_percent(a_best.get('annual_mape'))})"
        )
    read_parts.append(
        f"Scope: {format_count(family_count)} source families, {format_count(variant_count)} variants."
    )
    return cards, " | ".join(read_parts)


def inventory_insight_cards(readout: str) -> None:
    if not readout:
        return
    parts = [part.strip() for part in readout.split("|") if part.strip()]
    cards = []
    for idx, part in enumerate(parts, start=1):
        title, _, detail = part.partition(":")
        cards.append((title or f"Inventory insight {idx}", detail.strip() or part, "current filters"))
    kpi_grid(cards)


def render_model_detail(loaded: LoadedRun, summary: pd.DataFrame) -> None:
    if summary.empty or "model" not in summary.columns:
        return
    section_title("Model Detail")
    ranked = summary.sort_values("quarterly_mape") if "quarterly_mape" in summary.columns else summary
    model_options = ranked["model"].dropna().astype(str).drop_duplicates().tolist()
    if not model_options:
        st.caption("No model identifiers are available for the current filters.")
        return
    st.caption("Model selector includes every candidate that remains after the current search and ranking filters.")
    selected_model = st.selectbox("Inspect model", model_options, format_func=lambda value: model_alias(value, 76))
    detail = model_detail_summary(loaded, selected_model)
    kpi_grid(detail["cards"])
    info_panel(detail["readout"])


def model_detail_summary(loaded: LoadedRun, model: str) -> dict[str, Any]:
    summary = loaded.data.get("summary", pd.DataFrame())
    rows = summary[summary["model"].astype(str) == str(model)] if not summary.empty and "model" in summary.columns else pd.DataFrame()
    row = rows.sort_values("quarterly_mape").iloc[0] if not rows.empty and "quarterly_mape" in rows.columns else (rows.iloc[0] if not rows.empty else pd.Series(dtype=object))
    stream = row.get("stream_label", "Unknown")
    paired = loaded.data.get("paired_vs_schiff", pd.DataFrame())
    paired_rows = paired[paired["challenger"].astype(str) == str(model)] if not paired.empty and "challenger" in paired.columns else pd.DataFrame()
    stress = loaded.data.get("stress", pd.DataFrame())
    stress_rows = stress[stress["model"].astype(str) == str(model)] if not stress.empty and "model" in stress.columns else pd.DataFrame()
    weights = loaded.data.get("weights", pd.DataFrame())
    component_count = (
        int(weights.loc[weights["ensemble"].astype(str) == str(model), "component_model"].nunique())
        if not weights.empty and {"ensemble", "component_model"}.issubset(weights.columns)
        else 0
    )
    best_pair = paired_rows.sort_values("mape_improvement_pct_points", ascending=False).iloc[0] if not paired_rows.empty else pd.Series(dtype=object)
    worst_stress = stress_rows.dropna(subset=["mape"]).sort_values("mape", ascending=False).iloc[0] if not stress_rows.empty and "mape" in stress_rows.columns else pd.Series(dtype=object)
    cards = [
        ("Stream", str(stream), "Selected model scope"),
        ("Quarterly MAPE", format_percent(row.get("quarterly_mape")), "Model summary value"),
        ("Annual MAPE", format_percent(row.get("annual_mape")), "Model summary value"),
        ("Components", format_count(component_count), "Ensemble members if available"),
    ]
    schiff_text = (
        f"{schiff_result_label(best_pair.get('mape_improvement_pct_points'), best_pair.get('challenger_win_rate'))} "
        f"with {format_percent(best_pair.get('mape_improvement_pct_points'))} gain and "
        f"{format_percent(best_pair.get('challenger_win_rate'), 1)} win rate"
        if not best_pair.empty
        else "no paired Schiff row found"
    )
    stress_text = (
        f"worst loaded stress bucket is {worst_stress.get('stress_bucket')} at {format_percent(worst_stress.get('mape'))} MAPE"
        if not worst_stress.empty
        else "no stress row found"
    )
    return {
        "cards": cards,
        "readout": f"Model detail read: {model_alias(model, 76)} has {schiff_text}; {stress_text}.",
    }


def _best_inventory_row(summary: pd.DataFrame, metric: str) -> pd.Series | None:
    if metric not in summary.columns:
        return None
    ranked = summary.dropna(subset=[metric]).sort_values(metric)
    if ranked.empty:
        return None
    return ranked.iloc[0]


def render_run_audit(loaded: LoadedRun) -> None:
    section_title("Run Health Summary")
    cards, readout = run_health_summary(loaded)
    kpi_grid(cards)
    info_panel(readout)

    diagnostics = schema_diagnostics(loaded.warnings)
    if diagnostics:
        with st.expander("Schema diagnostics", expanded=False):
            info_panel(
                "Technical schema checks are kept in Run Audit so they are available for governance review without "
                "pushing management-page charts below the first viewport."
            )
            for diagnostic in diagnostics:
                st.markdown(f"- {diagnostic}")

    section_title("File Read Status")
    display_table(loaded.file_status, height=360)

    errors = loaded.data.get("errors", pd.DataFrame())
    variant_features = loaded.data.get("variant_features", pd.DataFrame())
    features = loaded.data.get("features", pd.DataFrame())

    section_title("Feature and Run Audit")
    st.plotly_chart(plot_feature_counts(variant_features), use_container_width=True)

    if not variant_features.empty:
        with st.expander("Variant feature counts", expanded=True):
            display_table(variant_features, height=380)
    if not features.empty:
        with st.expander("Feature audit table", expanded=False):
            display_table(features, height=420)

    section_title("Run Health Diagnostics")
    if errors.empty:
        info_panel("No rows were found in errors.csv.")
    else:
        warning_panel(
            "errors.csv is non-empty. Some model-search scripts are designed to log and skip failed candidates rather "
            "than stop the run, so review the flags before treating this as a failed run."
        )
        st.plotly_chart(plot_error_types(classify_error_rows(errors)), use_container_width=True)
        display_table(error_flags(errors), height=220)
        with st.expander("Errors table", expanded=True):
            display_table(errors, height=420)


def run_health_summary(loaded: LoadedRun) -> tuple[list[tuple[str, str, str]], str]:
    status = loaded.file_status.copy()
    errors = loaded.data.get("errors", pd.DataFrame())
    found_count = int(status["Found?"].eq("Yes").sum()) if "Found?" in status.columns else 0
    total_count = len(status)
    missing_count = max(total_count - found_count, 0)
    flags = error_flags(errors)
    flag_lookup = flags.set_index("Flag")["Rows"].to_dict() if not flags.empty else {}
    hyperopt = int(flag_lookup.get("HyperOpt missing", 0))
    ray_root = int(flag_lookup.get("Ray root-cause errors", 0))
    total_errors = int(flag_lookup.get("Total logged errors", len(errors)))
    cards = [
        ("Diagnostic Coverage", f"{found_count}/{total_count}", "Run output datasets found"),
        ("Missing Outputs", format_count(missing_count), "Warnings shown without crashing"),
        ("Logged Diagnostics", format_count(total_errors), "Rows in errors.csv"),
        ("Ray Root Causes", format_count(ray_root), "Explicit error-column matches"),
    ]
    if total_errors and hyperopt == total_errors:
        readout = (
            "Run health read: all explicit logged errors are missing-HyperOpt candidate-search failures. "
            "The run still produced finalist, prediction, stress, and audit outputs; review skipped candidates before production use."
        )
    elif total_errors:
        readout = "Run health read: logged diagnostics are mixed; inspect the error flags and raw errors table before relying on the run."
    else:
        readout = "Run health read: no logged diagnostics were found in errors.csv."
    return cards, readout


def error_flags(errors: pd.DataFrame) -> pd.DataFrame:
    if errors.empty:
        return pd.DataFrame(columns=["Flag", "Rows"])
    text = errors.astype(str).agg(" ".join, axis=1).str.lower()
    explicit_error = errors["error"].astype(str).str.lower() if "error" in errors.columns else text
    flags = {
        "HyperOpt missing": (explicit_error, "hyperopt"),
        "Ray root-cause errors": (explicit_error, "ray"),
        "Ray/Tune traceback mentions": (text, "ray"),
        "Permission errors": (explicit_error, "permission|access denied|denied"),
        "neural-model errors": (explicit_error, "neural|deepar|tft|transformer"),
        "empty files": (explicit_error, "empty file|empty dataframe|no rows"),
    }
    rows = []
    for label, (source, pattern) in flags.items():
        rows.append({"Flag": label, "Rows": int(source.str.contains(pattern, regex=True, na=False).sum())})
    rows.append({"Flag": "Total logged errors", "Rows": len(errors)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()

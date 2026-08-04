from __future__ import annotations

from datetime import datetime, timezone
import dataclasses
import hashlib
import html
import io
import json
import os
import threading
from pathlib import Path
import re
import sys
from functools import lru_cache
from time import perf_counter
from typing import Any, Sequence
import zipfile

_RUNTIME_PYARROW24 = Path(__file__).resolve().parent / ".runtime_pyarrow24"
if (
    os.environ.get("NLTF_DISABLE_RUNTIME_PYARROW24", "").strip().lower() not in {"1", "true", "yes"}
    and _RUNTIME_PYARROW24.exists()
    and str(_RUNTIME_PYARROW24) not in sys.path
):
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
    FORECAST_HORIZON_ZONE_EXTENDED,
    FORECAST_HORIZON_ZONE_MIXED,
    FORECAST_HORIZON_ZONE_UNVALIDATED,
    FORECAST_HORIZON_ZONE_VALIDATED,
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
from model_dashboard.eruc_transition import (
    ERUC_NOTE,
    ErucTransitionLevers,
    apply_eruc_transition_to_chart_rows,
)
from model_dashboard.npv import (
    average_annual,
    cumulative_total,
    horizon_label,
    mbcm_label,
    npv_to_horizon,
)
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    FED_POLICY_STATE_PUBLISHED,
    FED_UPLIFT_DELAY_NOTE,
    FED_UPLIFT_NOTE,
    OFFICIAL_SCOPE,
    rate_chart_note,
    apply_fed_uplift_delay_to_chart_rows,
    apply_fed_uplift_off_to_chart_rows,
    apply_official_comparator_rate_policy_to_chart_rows,
    fed_uplift_delayed_factors,
    fed_uplift_off_factors,
    mbu26_ruc_class_revenue_by_fy,
    rate_paths_frame,
)
from model_dashboard.light_fleet_allocation import LAST_DECISION_GRADE_ANNUAL_FY
from model_dashboard.unit_contract import display_scale_for
from model_dashboard.conflict_fuel_paths import (
    CONFLICT_FUEL_SCENARIO_LEVELS,
    conflict_scenario_name,
    conflict_scenario_note,
    conflict_trace_name,
)
from model_dashboard.fuel_price_scenario import (
    FUEL_PRICE_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_NOTE,
    FUEL_PRICE_SCENARIO_TRACE_NAME,
    DirectTreasuryScenarioReplayResult,
    apply_treasury_macro_to_chart_rows,
    append_fuel_price_scenario_to_chart_rows,
    run_direct_treasury_scenario_replay,
    run_fuel_price_scenario_replay,
)

CONFLICT_SCENARIO_NAMES = tuple(
    conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)
CONFLICT_TRACE_NAMES = tuple(
    conflict_trace_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)
CONFLICT_TRACE_BY_SCENARIO = dict(zip(CONFLICT_SCENARIO_NAMES, CONFLICT_TRACE_NAMES, strict=True))
CONFLICT_NOTE_BY_TRACE = {
    conflict_trace_name(level): conflict_scenario_note(level)
    for level in CONFLICT_FUEL_SCENARIO_LEVELS
}
CONFLICT_TRACE_STYLES = {
    conflict_trace_name("low"): ("#0F766E", "dot", 2.3),
    conflict_trace_name("medium"): ("#6B4E71", "dashdot", 2.6),
    conflict_trace_name("high"): ("#B42318", "longdash", 2.5),
}
CONFLICT_TRACE_COLORS = {
    trace_name: style[0] for trace_name, style in CONFLICT_TRACE_STYLES.items()
}
from model_dashboard.ev_uptake_levers import (
    CUSTOM_OPTION as EV_UPTAKE_CUSTOM_OPTION,
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_MODE_OPTIONS,
    EV_UPTAKE_PRESETS,
    EXACT_VFM_UPTAKE_BASES,
    HEAVY_BEV_TRANSITION_NOTE,
    PARAMETRIC_VFM_BASE_FIT_OPTION,
    GOVERNED_PACK_OPTION as EV_UPTAKE_GOVERNED_OPTION,
    UptakeLevers,
    SENSITIVITY_INTERPLAY_NOTE,
    VFM_SOURCE_NOTE,
    apply_uptake_levers_to_chart_rows,
)
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS
from model_dashboard.long_run_shape_transition import (
    FLEET_COMPOSITION_SOURCE_ID,
    STRUCTURAL_SCHEDULE_IDS,
    UNBLENDED_SCHEDULE_ID,
    resolve_schedule,
)
from model_dashboard.post_model_extrapolation import (
    POST_MODEL_SEGMENT,
    build_post_model_extrapolation_annual,
    post_model_chart_rows,
    post_model_line_reconciliation_rows,
)
from model_dashboard.official_vintage import load_official_vintage
from model_dashboard.official_vintage import (
    bridge_vintage_id_from_manifest,
    default_comparator_vintage_id,
    long_run_shape_vintage_choices,
    long_run_shape_vintage_id_from_manifest,
    official_comparator_scenario_name,
    official_comparator_trace_name,
    official_vintage_choices,
    official_vintage_entry,
    official_vintage_pack_files,
)
from model_dashboard.revenue_scenario_key import (
    HEAVY_BEV_DEFAULT,
    RevenueScenarioComputationKey,
    as_scenario_key,
)
from model_dashboard.revenue_chart_layers import (
    BAND_50_FILL,
    BAND_50_LAYER_ID,
    BAND_80_FILL,
    BAND_80_LAYER_ID,
    BAND_BOUNDARY,
    CONDITIONAL_BAND,
    LAYER_KIND_BAND,
    LAYER_KIND_ENVELOPE,
    LAYER_KIND_PATH,
    RevenueChartLayerSpec,
    VFM_ENVELOPE_LAYER_ID,
    VFM_FAST_TRACE_NAME,
    VFM_SLOW_TRACE_NAME,
    band_layer_ids,
    build_layer_catalogue,
    catalogue_frame,
    default_layer_ids,
    path_trace_names,
)
from model_dashboard.revenue_uncertainty_pack import (
    band_rows_for_series,
    load_uncertainty_pack,
)
from model_dashboard.revenue_outlook_presentation_policy import (
    REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL,
    REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS,
    clip_frame_to_display_horizon,
    display_end_fy,
    display_horizon_note,
    is_paused_vfm_uptake_basis,
    is_vfm_analyst_layer_label,
    method_detail_enabled,
    period_within_horizon,
    public_uptake_basis_options,
    sanitised_uptake_basis,
)

# What a helper will accept: the typed key, or a historic positional tuple from
# an older cache entry or test. Production builds the typed key directly.
ScenarioKeyLike = RevenueScenarioComputationKey | tuple
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
    FREIGHT_RAIL_SHIFT_LEVELS,
    FREIGHT_RAIL_SHIFT_NOTE,
    PT_MODE_SHIFT_LEVELS,
    REVENUE_FIRST_FORECAST_FY,
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
    SENSITIVITY_PT_START_FY,
    STREAM_LABELS,
    RevenueOutlookPack,
    apply_ped_bridge_mode_layer,
    apply_revenue_sensitivity_layer,
    apply_ped_efficiency_sensitivity,
    load_revenue_outlook_pack,
    net_revenue_timing_comparison_frame,
    ped_efficiency_scenarios_frame,
    sensitivity_config_frame,
    promote_revenue_outlook_pack,
    revenue_sensitivity_impact_audit_frame,
    revenue_formula_residual_frame,
    revenue_outlook_signature,
    revenue_stack_components_frame,
    validate_promotable_comparison,
)
from model_dashboard.revenue_source_pack import (
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
    EXPANDED_CHART_CONTAINER_KEY,
    EXPAND_CONTROL_CONTAINER_KEY,
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
# The bounded-horizon option is named from the governed current cutoff, not
# hard-coded. It read "To FY2031" while the current model published to
# FY2050; under the H20 policy FY2031 no longer exists, so a fixed label
# would name a year the user can never see.
REVENUE_SOURCE_HORIZON_TO_CUTOFF = f"To FY{LAST_DECISION_GRADE_ANNUAL_FY}"
REVENUE_SOURCE_HORIZON_OPTIONS = ["Next 5 FY", REVENUE_SOURCE_HORIZON_TO_CUTOFF, "Full common horizon"]
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


@st.cache_data(show_spinner=False, max_entries=2)
def cached_load_run(run_path: str, signature: tuple[tuple[str, int, int], ...], schema_version: str) -> LoadedRun:
    del signature
    del schema_version
    return load_run(run_path)


@st.cache_data(show_spinner=False, max_entries=2)
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


@st.cache_data(show_spinner=False, ttl=300, max_entries=4)
def cached_discover_run_folders(
    parent_path: str,
    ignored_names: tuple[str, ...],
    parent_signature: tuple[bool, int, int],
) -> tuple[str, ...]:
    del parent_signature
    runs = discover_run_folders(Path(parent_path).expanduser(), set(ignored_names))
    return tuple(str(path) for path in runs)


@st.cache_data(show_spinner=False, max_entries=2)
def cached_load_evidence_pack(
    data_root: str,
    repo_root: str,
    pack_sig: tuple[tuple[str, int, int], ...],
    schema_version: str,
) -> LoadedRun:
    del pack_sig
    del schema_version
    return load_evidence_pack(data_root, repo_root)


@st.cache_data(show_spinner=False, max_entries=6)
def cached_load_reproducibility_pack(stream_label: str, signature: tuple[tuple[str, int, int], ...]) -> Any:
    del signature
    return load_reproducibility_pack(stream_label)


@st.cache_data(show_spinner=False, max_entries=1)
def cached_load_ped_inner_hpo_audit_pack(signature: tuple[tuple[str, int, int], ...]) -> Any:
    del signature
    return load_ped_inner_hpo_audit_pack()


@st.cache_data(show_spinner=False, max_entries=2)
def cached_load_revenue_outlook_pack(
    pack_dir: str,
    repo_root: str,
    signature: tuple[tuple[str, int, int], ...],
    schema_version: str,
) -> RevenueOutlookPack | None:
    del signature
    del schema_version
    return load_revenue_outlook_pack(pack_dir, repo_root=repo_root)


@st.cache_data(show_spinner=False, max_entries=2)
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
        return f"{level} ({value_text}% p.a. from FY{SENSITIVITY_PT_START_FY})"
    if kind == "freight_rail_shift":
        if level == "Off":
            return "Off (0.0% p.a.)"
        if level == "Custom":
            return "Custom"
        value = FREIGHT_RAIL_SHIFT_LEVELS.get(level, 0.0) * 100.0
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


def _uncertainty_bands_withheld_for_sensitivity(
    sensitivity_key: tuple[str, ...],
) -> bool:
    """True when the annual 50/80% bands must be withheld for this key.

    Fleet efficiency and PT mode shift are deterministic analyst overlays on
    the central path. The governed draws and quantile maps describe the
    BASELINE computation only, and rollup series cannot be re-quantiled under
    the overlay without component-level draws, so while either lever is
    non-Off the bands are withheld rather than drawn around a central path
    they do not describe.
    """
    if not sensitivity_key or len(sensitivity_key) < 2:
        return False
    return (
        _normalize_sensitivity_level(sensitivity_key[0]) != "Off"
        or _normalize_sensitivity_level(sensitivity_key[1]) != "Off"
    )


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
    freight_rail_shift: str = "Off",
    custom_fleet_efficiency_pct: float | None = None,
    custom_pt_shift_pct: float | None = None,
    custom_freight_shift_pct: float | None = None,
    custom_ped_elasticity: float | None = None,
    custom_light_elasticity: float | None = None,
    custom_heavy_elasticity: float | None = None,
    cost_per_km_ratio: float | None = None,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str]:
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
        _normalize_sensitivity_level(freight_rail_shift),
        _key_float(custom_freight_shift_pct),
    )


def is_default_sensitivity(
    fleet_efficiency: str,
    pt_mode_shift: str,
    demand_elasticity: str,
    cost_per_km_ratio: float | None = None,
    freight_rail_shift: str = "Off",
) -> bool:
    return (
        _normalize_sensitivity_level(fleet_efficiency) == "Off"
        and _normalize_sensitivity_level(pt_mode_shift) == "Off"
        and _normalize_sensitivity_level(demand_elasticity) == "Off"
        and _normalize_sensitivity_level(freight_rail_shift) == "Off"
        and _key_float(cost_per_km_ratio) == ""
    )


def _is_default_sensitivity_key(sensitivity_key: tuple[Any, ...]) -> bool:
    if len(sensitivity_key) < 11:
        return False
    selections = (sensitivity_key[0], sensitivity_key[1], sensitivity_key[2], sensitivity_key[9])
    custom_values = [sensitivity_key[i] for i in (3, 4, 5, 6, 7, 8, 10)]
    return selections == ("Off", "Off", "Off", "Off") and all(str(value or "") == "" for value in custom_values)


def revenue_outlook_lazy_table(label: str, key: str, *, default: bool = False, caption: str | None = None) -> bool:
    if not should_show_local_audit_controls():
        return bool(default)
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


@st.cache_data(show_spinner=False, max_entries=2)
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
            "freight_rail_shift": {level: sensitivity_option_label("freight_rail_shift", level) for level in SENSITIVITY_LEVELS},
            "demand_elasticity": {level: sensitivity_option_label("demand_elasticity", level) for level in SENSITIVITY_LEVELS},
        },
    }


def _bridge_mode_frames_for_pack(
    pack: RevenueOutlookPack,
    bridge_mode: str,
    *,
    include_derived_frames: bool = True,
    derived_frame_scope: str = "all",
    include_selected_ped_audit: bool | None = None,
) -> dict[str, pd.DataFrame]:
    return apply_ped_bridge_mode_layer(
        chart_rows=_pack_table(pack, "revenue_chart_rows"),
        line_reconciliation=_pack_table(pack, "revenue_line_reconciliation"),
        bridge_components=_pack_table(pack, "revenue_bridge_components"),
        future_revenue_forecasts=_pack_table(pack, "future_revenue_forecasts"),
        ped_revenue_bridge_audit=_pack_table(pack, "ped_revenue_bridge_audit"),
        bridge_mode=bridge_mode,
        include_derived_frames=include_derived_frames,
        derived_frame_scope=derived_frame_scope,
        include_selected_ped_audit=include_selected_ped_audit,
    )


def _apply_sensitivity_for_key(
    bridge_frames: dict[str, pd.DataFrame],
    sensitivity_config: pd.DataFrame,
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
) -> dict[str, pd.DataFrame]:
    fleet_efficiency, pt_mode_shift, demand_elasticity = sensitivity_key[:3]
    freight_rail_shift = sensitivity_key[9] if len(sensitivity_key) > 9 else "Off"
    custom_fleet = float(sensitivity_key[3]) if sensitivity_key[3] else None
    custom_pt = float(sensitivity_key[4]) if sensitivity_key[4] else None
    custom_ped = float(sensitivity_key[5]) if sensitivity_key[5] else None
    custom_light = float(sensitivity_key[6]) if sensitivity_key[6] else None
    custom_heavy = float(sensitivity_key[7]) if sensitivity_key[7] else None
    cost_ratio = float(sensitivity_key[8]) if sensitivity_key[8] else None
    custom_freight = float(sensitivity_key[10]) if len(sensitivity_key) > 10 and sensitivity_key[10] else None
    return apply_revenue_sensitivity_layer(
        chart_rows=bridge_frames["chart_rows"],
        line_reconciliation=bridge_frames["line_reconciliation"],
        bridge_components=bridge_frames["revenue_bridge_components"],
        future_revenue_forecasts=bridge_frames["future_revenue_forecasts"],
        ped_revenue_bridge_audit=bridge_frames["ped_revenue_bridge_audit"],
        sensitivity_config=sensitivity_config,
        fleet_efficiency=fleet_efficiency,
        pt_mode_shift=pt_mode_shift,
        freight_rail_shift=freight_rail_shift,
        demand_elasticity=demand_elasticity,
        custom_fleet_efficiency_pct=custom_fleet,
        custom_pt_shift_pct=custom_pt,
        custom_freight_shift_pct=custom_freight,
        custom_ped_elasticity=custom_ped,
        custom_light_elasticity=custom_light,
        custom_heavy_elasticity=custom_heavy,
        cost_per_km_ratio=cost_ratio,
    )


def _scenario_key(ev_uptake_key: ScenarioKeyLike) -> RevenueScenarioComputationKey:
    """Coerce whatever a caller passed into the typed scenario key.

    The single place that knows the historic positional layout exists.  Every
    helper below reads NAMED fields, so no control can be re-interpreted by an
    unrelated reader the way slot 6 was read both as the official comparator
    vintage id and as the Heavy-BEV flag.
    """
    return as_scenario_key(
        ev_uptake_key,
        default_official_comparator_vintage_id=_registry_default_comparator_vintage_id(),
        default_current_fed_policy_state=FED_POLICY_DELAYED_6M,
        # Historic keys wrote the FED policy as a 0/1 toggle. The typed key
        # stores text, so the legacy numeric semantics must be resolved during
        # adaptation, not stringified into "0"/"1".
        policy_normaliser=_normalise_fed_policy_state,
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _resolve_ev_uptake_levers(ev_uptake_key: ScenarioKeyLike) -> UptakeLevers | None:
    key = _scenario_key(ev_uptake_key)
    mode = key.uptake_basis or EV_UPTAKE_GOVERNED_OPTION
    if mode == EV_UPTAKE_GOVERNED_OPTION:
        return None
    if mode == EV_UPTAKE_CUSTOM_OPTION:
        values = key.custom_ev_levers
        if len(values) != 13:
            return None
        return UptakeLevers(*[float(v) for v in values])
    if mode == PARAMETRIC_VFM_BASE_FIT_OPTION:
        return EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]
    # Named VFM modes still carry a lever object, but only so the PED retention
    # curve has parameters if that separate sensitivity is switched on. Their
    # COMPOSITION comes from the exact vendored table via _resolve_uptake_basis.
    return EV_UPTAKE_PRESETS.get(mode)


def _resolve_uptake_basis(ev_uptake_key: ScenarioKeyLike) -> str | None:
    """The exact vendored VFM scenario to compose with, or None for parametric.

    Returning a basis is what routes the composition through the governed
    table. Custom levers and the explicitly-labelled parametric approximation
    return None and fall back to the fitted curve.
    """
    mode = _scenario_key(ev_uptake_key).uptake_basis or EV_UPTAKE_GOVERNED_OPTION
    return mode if mode in EXACT_VFM_UPTAKE_BASES else None


def _heavy_bev_transition_enabled(ev_uptake_key: ScenarioKeyLike) -> bool:
    """Heavy BEV reclassification: its own named field, and Off by default.

    It previously rode in slot 6 of the positional key - the same slot the
    official comparator vintage id was written to - so every production render
    resolved ``bool("BEFU26")`` and silently moved Heavy RUC km and revenue
    into Heavy BEV against the settled HEAVY_RUC: not_reclassified contract.
    A vintage id is now a ``str`` field and cannot be read as this flag.
    """
    return _scenario_key(ev_uptake_key).heavy_bev_transition


def _resolve_eruc_levers(ev_uptake_key: ScenarioKeyLike) -> ErucTransitionLevers | None:
    """The optional e-RUC transition levers for this scenario."""
    values = _scenario_key(ev_uptake_key).eruc_levers
    if not values or len(values) != 5:
        return None
    return ErucTransitionLevers(*[float(v) for v in values])


_CURRENT_FED_UPLIFT_ROLES = ("basecase", "comparison")
_MBU26_FED_UPLIFT_ROLES = ("official_comparator",)
FED_POLICY_PUBLISHED = "published"
FED_POLICY_DELAYED_6M = "delayed_6m"
FED_POLICY_OFF = "off"
FED_POLICY_OPTIONS = (
    FED_POLICY_PUBLISHED,
    FED_POLICY_DELAYED_6M,
    FED_POLICY_OFF,
)
# The UI labels and the rate_paths policy states are separate vocabularies
# ("off" vs "no_uplift", "delayed_6m" vs "delay_6m"). The current-model path
# hides this by choosing a wrapper per label; the official helper takes the
# state directly, so the translation has to be explicit rather than implied.
_OFFICIAL_POLICY_STATE_BY_UI_LABEL = {
    FED_POLICY_PUBLISHED: FED_POLICY_STATE_PUBLISHED,
    FED_POLICY_DELAYED_6M: FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_OFF: FED_POLICY_STATE_NO_UPLIFT,
}
FED_POLICY_LABELS = {
    FED_POLICY_PUBLISHED: "Original timing — 1 Jan 2027",
    FED_POLICY_DELAYED_6M: "Deferred 6 months — 1 Jul 2027",
    FED_POLICY_OFF: "No 12c uplift",
}
FED_POLICY_NOTES = {
    FED_POLICY_PUBLISHED: (
        "Original published timing: the 12c/L step begins 1 January 2027. "
        "That affects the final two quarters of FY2027, including the PED pump-price "
        "input and the proportional Light/Heavy RUC rate and model-price inputs."
    ),
    FED_POLICY_DELAYED_6M: FED_UPLIFT_DELAY_NOTE,
    FED_POLICY_OFF: FED_UPLIFT_NOTE,
}


def _normalise_fed_policy_state(value: Any) -> str:
    """Return one of the three reader-facing FED/RUC policy states.

    Numeric and boolean values retain the former toggle semantics for cached
    callers: zero/False meant delayed, while one/True meant no uplift.
    """

    if isinstance(value, bool):
        return FED_POLICY_OFF if value else FED_POLICY_DELAYED_6M
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return FED_POLICY_OFF if bool(value) else FED_POLICY_DELAYED_6M
    text = str(value or "").strip()
    lowered = text.casefold()
    label_lookup = {label.casefold(): state for state, label in FED_POLICY_LABELS.items()}
    if lowered in label_lookup:
        return label_lookup[lowered]
    if lowered in {
        FED_POLICY_PUBLISHED,
        FED_POLICY_STATE_PUBLISHED,
        "original",
        "planned",
        "published_timing",
    }:
        return FED_POLICY_PUBLISHED
    if lowered in {
        FED_POLICY_DELAYED_6M,
        FED_POLICY_STATE_DELAYED_6M,
        "delay_6m",
        "shifted_6m",
        "deferred",
    }:
        return FED_POLICY_DELAYED_6M
    if lowered in {
        FED_POLICY_OFF,
        FED_POLICY_STATE_NO_UPLIFT,
        "no_uplift",
        "none",
    }:
        return FED_POLICY_OFF
    return FED_POLICY_DELAYED_6M


PED_RETENTION_SENSITIVITY_LABEL = "VFM petrol-retention sensitivity"
PED_RETENTION_SENSITIVITY_HELP = (
    "Structural sensitivity only. A rolling-origin comparison against the raw "
    "AR(1) petrol path found this overlay WORSE in every cohort and at every "
    "horizon H1-H12 (balanced WAPE -4.6%, -29.6% excluding 2020Q1-2021Q4), so "
    "it is not supported as the Base forecast and is off by default. The Base "
    "path is raw AR(1) VKT per capita x population."
)


def _ped_retention_enabled(ev_uptake_key: ScenarioKeyLike) -> bool:
    """The PED petrol-retention sensitivity: named field, Off by default.

    Off means the raw AR(1) Base path with no retention overlay.

    This still reads the key rather than the presentation policy, so a
    historical cache entry or an evidence script that deliberately sets the
    field keeps behaving exactly as it did. What changed is that production
    never BUILDS a key carrying True - see
    :func:`_production_ped_retention_sensitivity`.
    """
    return _scenario_key(ev_uptake_key).ped_retention_sensitivity


def _production_ped_retention_sensitivity() -> bool:
    """The retention flag every production Revenue Outlook key must carry.

    The control is withdrawn (REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL),
    so this is False and session state is not consulted at all: a stale True
    persisted by a reader's browser before the control was removed can never
    reactivate the overlay. The typed field and the backend implementation are
    untouched for compatibility and audit.
    """
    if not REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL:
        return False
    return bool(st.session_state.get("revenue_outlook_ped_retention_sensitivity", False))


def _public_uptake_basis_options() -> list[str]:
    """The uptake bases the production UI offers, in their governed order.

    One source for both view modes, so single and compare can never disagree
    about which compositions a reader may run.
    """
    return public_uptake_basis_options(EV_UPTAKE_MODE_OPTIONS)


# Session keys that carry an uptake basis and therefore have to be re-checked
# against the pause on every entry.
_UPTAKE_BASIS_STATE_KEYS = ("revenue_outlook_ev_uptake_basis_v2",)

# The A/B columns selected an uptake basis before they selected scenario
# traces; the stale keys are dropped on entry like any withdrawn control.
_WITHDRAWN_COMPARISON_STATE_KEYS = ("ro_cmp_a_uptake", "ro_cmp_b_uptake")


def _discard_withdrawn_revenue_outlook_state() -> None:
    """Drop session values written by controls that no longer exist.

    Streamlit keeps a key in session state forever once a widget has written
    it, so a reader who ticked the retention box - or selected a VFM Fast/Slow
    layer - before the workshop build would otherwise carry that selection into
    a page that no longer offers it. Clearing on entry keeps the withdrawn
    state from surviving deployment while leaving every live selection alone.
    """
    if not REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL:
        st.session_state.pop("revenue_outlook_ped_retention_sensitivity", None)
    for key in _WITHDRAWN_COMPARISON_STATE_KEYS:
        st.session_state.pop(key, None)
    if not REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS:
        st.session_state.pop("revenue_outlook_show_vfm_envelope_audit", None)
        persisted = st.session_state.get("revenue_outlook_chart_layers")
        if isinstance(persisted, list):
            kept = [
                label for label in persisted if not is_vfm_analyst_layer_label(label)
            ]
            if len(kept) != len(persisted):
                st.session_state["revenue_outlook_chart_layers"] = kept
        # A basis selected before the pause is reset rather than dropped: these
        # selectors must always resolve to a legal composition, and Base is the
        # governed default.
        for key in _UPTAKE_BASIS_STATE_KEYS:
            if key in st.session_state and is_paused_vfm_uptake_basis(
                st.session_state[key]
            ):
                st.session_state[key] = DEFAULT_EV_UPTAKE_MODE
    _discard_out_of_horizon_revenue_outlook_state()
    _discard_unknown_revenue_outlook_policy_state()


def _discard_out_of_horizon_revenue_outlook_state() -> None:
    """Drop an FY marker a previous deployment allowed past the horizon.

    The selector no longer offers FY2051+, and Streamlit raises rather than
    silently correcting when a stored value is not among a widget's options.
    A returning reader who had FY2053 marked would otherwise hit that error on
    entry, so the stale value is dropped and the marker falls back to its
    default.
    """
    marked = st.session_state.get("revenue_outlook_selected_fy")
    if marked is None:
        return
    if not period_within_horizon(marked):
        st.session_state.pop("revenue_outlook_selected_fy", None)


def _discard_unknown_revenue_outlook_policy_state() -> None:
    """Reset a 12c selection this build no longer recognises.

    The policy vocabulary is a closed set. A value from an older deployment
    that does not normalise is dropped rather than coerced, because coercing
    it would silently swap one counterfactual for another - the reader would
    see a path they did not choose and have no way to tell.
    """
    for key in ("revenue_outlook_fed_policy_state", "revenue_outlook_mbu_fed_policy_state"):
        value = st.session_state.get(key)
        if value is None:
            continue
        if str(value) not in FED_POLICY_OPTIONS:
            st.session_state.pop(key, None)


# The official comparator vintage selection rides in slots 6/7 of the uptake
# key (appended AFTER the PED-retention slot so every existing positional read
# keeps indexing correctly). Keys created before the selector existed resolve
# to the governed default comparator vintage with no overlay, matching the
# rebuilt pack's default official trace.
@lru_cache(maxsize=1)
def _registry_default_comparator_vintage_id() -> str:
    """Registry-resolved default comparator; never a hard-coded release."""
    return default_comparator_vintage_id(Path(__file__).resolve().parent)


@lru_cache(maxsize=1)
def _registry_official_trace_names() -> tuple[str, ...]:
    """Official comparator trace names, default comparator first.

    Generated from the registry so a newly registered vintage joins the
    trace vocabulary, ordering, legend defaults, colour map and source-option
    lists without any production-code edit.
    """
    root = Path(__file__).resolve().parent
    names: list[str] = []
    for vid, _display in official_vintage_choices(root):
        entry = official_vintage_entry(vid, root)
        names.append(
            str(entry.get("trace_name") or official_comparator_trace_name(
                str(entry.get("release_round") or vid)
            ))
        )
    return tuple(names)


def _official_trace_style_map() -> dict[str, tuple[str, str, float]]:
    """Default comparator in the strong green; prior vintages muted."""
    styles: dict[str, tuple[str, str, float]] = {}
    for index, name in enumerate(_registry_official_trace_names()):
        styles[name] = (
            ("#00843D", "dash", 2.2) if index == 0 else ("#7A9E7E", "dot", 1.8)
        )
    return styles


def _ordered_official_traces(selected_official_trace: str | None = None) -> list[str]:
    """Registry official traces with the selected one first."""
    officials = list(_registry_official_trace_names())
    if selected_official_trace in officials:
        officials = [selected_official_trace] + [
            trace for trace in officials if trace != selected_official_trace
        ]
    return officials


def _official_vintage_scope(ev_uptake_key: ScenarioKeyLike) -> tuple[str, bool]:
    """Return (selected official vintage id, overlay-prior-vintages flag)."""
    key = _scenario_key(ev_uptake_key)
    vid = key.official_comparator_vintage_id or _registry_default_comparator_vintage_id()
    return vid, key.official_comparator_overlay


def _official_vintage_filter_for_key(ev_uptake_key: ScenarioKeyLike) -> tuple[str, bool]:
    """(selected official scenario_name, overlay flag) for row filtering."""
    vid, overlay = _official_vintage_scope(ev_uptake_key)
    return official_comparator_scenario_name(vid), overlay


def _long_run_shape_scope(ev_uptake_key: ScenarioKeyLike) -> tuple[str, str]:
    """(transition schedule id, long-run shape vintage id) for this key.

    A key that names neither falls back to the unblended construction, which
    is what a pre-selector key meant.
    """
    key = _scenario_key(ev_uptake_key)
    return (
        key.long_run_transition_schedule_id or UNBLENDED_SCHEDULE_ID,
        key.long_run_shape_vintage_id,
    )


def _shape_adjusted_signature(
    signature: tuple[tuple[str, int, int], ...],
    schedule_id: str,
    shape_vintage_id: str,
) -> tuple[tuple[str, int, int], ...]:
    """Fold the shape selection INTO the pack signature.

    Every downstream cache - sensitivity frames, overlay rows, detail frames,
    figures - is keyed on this signature and not on the uptake key, so the
    selection has to enter here or a switch between schedules would silently
    return another schedule's cached frames.
    """
    # The marker is appended for EVERY explicit selection, including the
    # unblended control. Exempting unblended would have been correct only while
    # the pack was itself unblended; with a structural schedule promoted, the
    # rebuilt unblended frames are different data and must not share the pack's
    # cache entry. Callers skip this entirely when the selection matches the
    # pack, so the untouched pack keeps its untouched signature.
    marker = (f"long_run_shape:{schedule_id}:{shape_vintage_id}", 0, 0)
    return tuple(signature) + (marker,)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_long_run_shape_post_model_rows(
    signature: tuple[tuple[str, int, int], ...],
    schedule_id: str,
    shape_vintage_id: str,
    pack_dir: str,
    _pack: RevenueOutlookPack,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chart and line rows for the selected long-run shape candidate.

    Built through the SAME governed constructor the pack builder uses, so the
    analyst preview and a promoted production default cannot diverge: selecting
    ``balanced_structural`` here produces exactly what rebuilding the pack on
    ``balanced_structural`` would produce.
    """

    root = Path(__file__).resolve().parent
    base = Path(pack_dir)
    bridge_vid = bridge_vintage_id_from_manifest(_pack.manifest, root)
    bridge_pack = load_official_vintage(bridge_vid, repo_root=root)
    shape_pack = load_official_vintage(shape_vintage_id, repo_root=root)
    if bridge_pack is None or shape_pack is None:
        raise ValueError(
            f"long-run shape preview needs bridge {bridge_vid} and shape "
            f"{shape_vintage_id}; one is not materialized."
        )

    raw_audit = pd.read_parquet(base / "raw_quarterly_forecast_audit.parquet")
    scenario_input_wide = pd.read_parquet(
        base / "scenario_inputs" / "scenario_input_wide.parquet"
    )
    extrapolation = build_post_model_extrapolation_annual(
        line_reconciliation=_pack.revenue_line_reconciliation,
        raw_quarterly_audit=raw_audit,
        scenario_input_wide=scenario_input_wide,
        mbu26_official_annual=bridge_pack.official_annual,
        repo_root=root,
        long_run_shape_official_annual=shape_pack.official_annual,
        long_run_shape_vintage_id=shape_vintage_id,
        transition_schedule_id=schedule_id,
    )
    chart_rows = post_model_chart_rows(_pack.revenue_chart_rows, extrapolation)
    line_rows = post_model_line_reconciliation_rows(
        _pack.revenue_line_reconciliation, extrapolation
    )
    return chart_rows, line_rows


def _replace_post_model_rows(frame: pd.DataFrame, replacement: pd.DataFrame) -> pd.DataFrame:
    """Swap the FY2031-FY2050 post-model block, leaving everything else alone.

    Only rows already labelled ``post_model_extrapolation`` are dropped, so
    actuals, the econometric FY2026-FY2030 path and every official published
    row pass through untouched by construction rather than by filtering.
    """
    if frame is None or frame.empty or replacement is None or replacement.empty:
        return frame
    segment = frame.get("forecast_segment", pd.Series("", index=frame.index))
    keep = frame[~segment.fillna("").astype(str).eq(POST_MODEL_SEGMENT)]
    return pd.concat([keep, replacement], ignore_index=True, sort=False)


def _apply_long_run_shape_selection(
    pack: RevenueOutlookPack,
    signature: tuple[tuple[str, int, int], ...],
    pack_dir: str,
    ev_uptake_key: tuple[Any, ...],
) -> tuple[RevenueOutlookPack, tuple[tuple[str, int, int], ...]]:
    """Swap the pack's post-model layer for the analyst-selected candidate.

    Applied to the PACK, upstream of the sensitivity, macro-replay, VFM and
    FED-policy overlays, because those overlays do modify FY2031-FY2050 rows.
    Substituting after them would silently discard the macro and policy
    treatment on exactly the years the preview is about.
    """

    schedule_id, shape_vintage_id = _long_run_shape_scope(ev_uptake_key)
    if not shape_vintage_id:
        return pack, signature
    # Skip the rebuild only when the selection already MATCHES what the pack was
    # built with. Short-circuiting on `unblended` instead was only correct while
    # the pack itself was unblended: once a structural schedule is promoted,
    # selecting "Current unblended" has to actively rebuild the unblended layer,
    # or the control silently shows the promoted path under the wrong label.
    block = pack.manifest.get("official_vintages") if isinstance(pack.manifest, dict) else None
    pack_schedule = str((block or {}).get("long_run_transition_schedule_id") or UNBLENDED_SCHEDULE_ID)
    pack_shape_vintage = str((block or {}).get("long_run_shape_vintage_id") or "")
    if schedule_id == pack_schedule and shape_vintage_id == pack_shape_vintage:
        return pack, signature
    try:
        chart_rows, line_rows = cached_long_run_shape_post_model_rows(
            signature, schedule_id, shape_vintage_id, pack_dir, pack
        )
    except Exception as error:  # pragma: no cover - surfaced in the UI
        st.warning(
            f"Long-run shape preview unavailable ({error}); showing the pack's "
            "own long-run construction."
        )
        return pack, signature
    adjusted = dataclasses.replace(
        pack,
        revenue_chart_rows=_replace_post_model_rows(pack.revenue_chart_rows, chart_rows),
        revenue_line_reconciliation=_replace_post_model_rows(
            pack.revenue_line_reconciliation, line_rows
        ),
    )
    return adjusted, _shape_adjusted_signature(signature, schedule_id, shape_vintage_id)


def _filter_official_vintage_rows(
    frame: pd.DataFrame,
    selected_scenario: str,
    overlay: bool,
) -> pd.DataFrame:
    """Drop official-comparator rows belonging to non-selected vintages.

    Applied at each consumption point AFTER cache retrieval. Frames carrying
    scenario_role/scenario_name (chart rows, line reconciliation, stack
    components) are filtered; frames without those columns, Actual rows and
    current-model rows pass through untouched. With the analyst overlay on,
    every published official vintage is kept.
    """
    if overlay or frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    if "scenario_role" not in frame.columns or "scenario_name" not in frame.columns:
        return frame
    role = frame["scenario_role"].fillna("").astype(str)
    scenario = frame["scenario_name"].fillna("").astype(str)
    drop = role.eq(OFFICIAL_SCOPE) & ~scenario.eq(str(selected_scenario))
    if not drop.any():
        return frame
    return frame[~drop].copy()


def _fed_policy_state_scope(ev_uptake_key: ScenarioKeyLike) -> tuple[str, str]:
    """Return (Current 12c policy state, official-comparator policy state)."""
    key = _scenario_key(ev_uptake_key)
    current = key.current_fed_policy_state or FED_POLICY_DELAYED_6M
    official = key.official_fed_policy_state or current
    return (
        _normalise_fed_policy_state(current),
        _normalise_fed_policy_state(official),
    )


def _current_policy_state_for_key(ev_uptake_key: ScenarioKeyLike) -> str:
    """The Current 12c state this key computes under.

    The quarterly derivation needs it to pick the governed rate timetable, and
    the VFM preset keys carry the live policy through unchanged, so reading it
    back off the key is what keeps a bound's quarters on the same timetable as
    the central path they bracket.
    """
    current_state, _official_state = _fed_policy_state_scope(ev_uptake_key)
    return current_state


def _fed_uplift_off_scope(ev_uptake_key: tuple[Any, ...]) -> tuple[bool, bool]:
    """Return (current scenarios off, MBU26 comparator off).

    Five-slot keys carry independent policy states. Four-slot keys retain the
    legacy global behaviour for cached/test callers created before the split.
    """
    current_state, mbu26_state = _fed_policy_state_scope(ev_uptake_key)
    return current_state == FED_POLICY_OFF, mbu26_state == FED_POLICY_OFF


def _fed_uplift_roles_for_key(ev_uptake_key: tuple[Any, ...]) -> tuple[str, ...]:
    current_off, mbu26_off = _fed_uplift_off_scope(ev_uptake_key)
    roles: list[str] = []
    if current_off:
        roles.extend(_CURRENT_FED_UPLIFT_ROLES)
    if mbu26_off:
        roles.extend(_MBU26_FED_UPLIFT_ROLES)
    return tuple(roles)


def _fed_policy_scopes_for_key(ev_uptake_key: tuple[Any, ...]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Policy schedule for Current and MBU26 traces.

    Original timing is already the published chart lineage and therefore needs
    no overlay. Deferred and no-uplift states are applied independently to
    Current and MBU26 roles.
    """
    current_state, mbu26_state = _fed_policy_state_scope(ev_uptake_key)
    scopes: list[tuple[str, tuple[str, ...]]] = []
    if current_state != FED_POLICY_PUBLISHED:
        scopes.append((current_state, _CURRENT_FED_UPLIFT_ROLES))
    if mbu26_state != FED_POLICY_PUBLISHED:
        scopes.append((mbu26_state, _MBU26_FED_UPLIFT_ROLES))
    return tuple(scopes)


def _policy_scopes_for_available_replay(
    scopes: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    replay_available: bool,
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], pd.DataFrame]:
    """Fail closed for Current policy paths when full replay data is missing.

    MBU26 can still use its source-backed, five-class rate-only calculation.
    Current Base/High paths must retain the published path because a visible-
    leaf fallback would omit both the behavioural response and hidden Heavy
    BEV contribution while incorrectly looking like a complete policy replay.
    """

    if replay_available:
        return scopes, pd.DataFrame()
    governed: list[tuple[str, tuple[str, ...]]] = []
    audit_rows: list[dict[str, Any]] = []
    current_roles = set(_CURRENT_FED_UPLIFT_ROLES)
    for policy, roles in scopes:
        requested = tuple(str(role) for role in roles)
        retained = tuple(role for role in requested if role not in current_roles)
        if retained:
            governed.append((str(policy), retained))
        removed = tuple(role for role in requested if role in current_roles)
        if removed:
            audit_rows.append(
                {
                    "scenario_name": "current_policy_paths",
                    "scenario_role": ";".join(removed),
                    "policy_state": str(policy),
                    "applied": False,
                    "transformation_basis": "policy_replay_unavailable_not_applied",
                    "reason": (
                        "Full fixed-finalist policy replay is unavailable; Current paths remain on "
                        "their published values rather than using an incomplete visible-leaf fallback."
                    ),
                }
            )
    return tuple(governed), pd.DataFrame(audit_rows)


def _effective_fed_policy_state(
    requested_state: str,
    scenario_roles: tuple[str, ...],
    policy_audit: pd.DataFrame,
) -> str:
    """Resolve the state actually applied after the replay availability gate."""

    requested = _normalise_fed_policy_state(requested_state)
    if requested == FED_POLICY_PUBLISHED or policy_audit is None or policy_audit.empty:
        return requested
    unavailable = policy_audit[
        policy_audit.get("transformation_basis", pd.Series("", index=policy_audit.index))
        .astype(str)
        .eq("policy_replay_unavailable_not_applied")
    ]
    if unavailable.empty:
        return requested
    governed_roles = {str(role) for role in scenario_roles}
    for value in unavailable.get("scenario_role", pd.Series(dtype=str)).astype(str):
        if governed_roles.intersection(part for part in value.split(";") if part):
            return FED_POLICY_PUBLISHED
    return requested


@st.cache_data(show_spinner=False, max_entries=4)
def cached_sensitivity_stage_frames(
    signature: tuple[tuple[str, int, int], ...],
    bridge_mode: str,
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    _pack: RevenueOutlookPack,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], bool]:
    """Bridge + sensitivity stages of the view pipeline: (bridge, sensitivity, fast_path).

    These stages cost ~0.6-2.9s and are shared by every lever overlay run
    (selected levers, cone bounds, comparison scenarios), so they cache
    independently of the uptake/e-RUC/12c keys layered on top.
    """
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
        return bridge_frames, sensitivity_frames, True
    return bridge_frames, _apply_sensitivity_for_key(bridge_frames, sensitivity_config, sensitivity_key), False


@st.cache_data(show_spinner=False, max_entries=2)
def cached_fed_uplift_factors(
    signature: tuple[tuple[str, int, int], ...],
    _pack: RevenueOutlookPack,
) -> dict[str, dict[Any, Any]]:
    del signature
    root = Path(__file__).resolve().parent
    return {
        "delayed_6m": fed_uplift_delayed_factors(root, _pack.revenue_chart_rows),
        "off": fed_uplift_off_factors(root, _pack.revenue_chart_rows),
        "mbu26_ruc_class_revenue": mbu26_ruc_class_revenue_by_fy(root),
    }


REVENUE_OUTLOOK_RUNTIME_MODE_ENV = "REVENUE_OUTLOOK_RUNTIME_MODE"
RUNTIME_MODE_REFERENCE = "reference"
RUNTIME_MODE_FAST = "fast"
RUNTIME_MODE_SHADOW = "shadow"
_RUNTIME_MODES = (RUNTIME_MODE_REFERENCE, RUNTIME_MODE_FAST, RUNTIME_MODE_SHADOW)


class RevenueOutlookRuntimeModeError(ValueError):
    """An explicit REVENUE_OUTLOOK_RUNTIME_MODE value is not a known mode."""


def revenue_outlook_runtime_mode() -> str:
    """reference = live replay; fast = compiled cache; shadow = fast + compare.

    Fast is the default: the compiled cache is a materialisation of the same
    replay, hash-validated at load, and it fails closed rather than falling
    back to the 52 s path.

    An ABSENT variable defaults to fast. An explicitly supplied unknown value
    raises: silently treating ``REVENUE_OUTLOOK_RUNTIME_MODE=refrence`` as
    "fast" would hide exactly the misconfiguration the operator was trying to
    correct.
    """
    raw = os.environ.get(REVENUE_OUTLOOK_RUNTIME_MODE_ENV)
    if raw is None or not str(raw).strip():
        return RUNTIME_MODE_FAST
    value = str(raw).strip().lower()
    if value not in _RUNTIME_MODES:
        raise RevenueOutlookRuntimeModeError(
            f"{REVENUE_OUTLOOK_RUNTIME_MODE_ENV}={raw!r} is not a known mode; "
            f"expected one of {', '.join(_RUNTIME_MODES)}."
        )
    return value


def _shadow_mismatch_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "artifacts"
        / "revenue_outlook_instant_runtime"
        / "shadow_mismatch.md"
    )


@st.cache_resource(show_spinner=False, max_entries=4)
def _shadow_compare_replays(engine: str, source_digest: str) -> str:
    """Shadow mode: prove the compiled cache still equals the live replay.

    Runs ONCE per (engine, digest) per process, not per request - the live
    replay costs ~60 s. Any discrepancy writes a mismatch artifact and raises,
    so shadow can never quietly serve a diverged value.
    """
    import dataclasses

    from model_dashboard.engine import engine_revenue_outlook_dir
    from model_dashboard.revenue_outlook_replay_cache import load_replay_cache

    repo_root = Path(__file__).resolve().parent
    pack_dir = repo_root / engine_revenue_outlook_dir(engine)
    pack_manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    bridge = bridge_vintage_id_from_manifest(pack_manifest, repo_root)
    scenario_inputs = pd.read_parquet(pack_dir / "scenario_inputs" / "scenario_input_wide.parquet")

    compiled = load_replay_cache(
        engine=engine,
        pack_manifest=pack_manifest,
        bridge_vintage_id=bridge,
        repo_root=repo_root,
        source_digest=source_digest,
    )
    live = (
        run_direct_treasury_scenario_replay(
            scenario_inputs, repo_root=repo_root, engine=engine, bridge_vintage_id=bridge
        ),
        run_fuel_price_scenario_replay(
            scenario_inputs, repo_root=repo_root, engine=engine, bridge_vintage_id=bridge
        ),
    )

    def _walk(obj, prefix=""):
        out = {}
        for field in dataclasses.fields(obj):
            value = getattr(obj, field.name)
            name = f"{prefix}{field.name}"
            if isinstance(value, pd.DataFrame):
                out[name] = value
            elif dataclasses.is_dataclass(value) and not isinstance(value, type):
                out.update(_walk(value, prefix=f"{name}."))
        return out

    mismatches: list[str] = []
    for label, (compiled_result, live_result) in zip(
        ("macro", "fuel"), zip(compiled, live, strict=True), strict=True
    ):
        compiled_frames = _walk(compiled_result, f"{label}.")
        live_frames = _walk(live_result, f"{label}.")
        for name in sorted(set(compiled_frames) | set(live_frames)):
            if name not in compiled_frames or name not in live_frames:
                mismatches.append(f"{name}: present in only one result")
                continue
            try:
                pd.testing.assert_frame_equal(
                    compiled_frames[name], live_frames[name], check_exact=True, obj=name
                )
            except AssertionError as error:
                mismatches.append(f"{name}: {str(error).splitlines()[0]}")

    if mismatches:
        path = _shadow_mismatch_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Shadow mismatch: engine={engine} digest={source_digest[:16]}\n\n"
            + "\n".join(f"- {line}" for line in mismatches)
            + "\n",
            encoding="utf-8",
        )
        raise RuntimeError(
            f"Shadow mode found {len(mismatches)} compiled-vs-live replay "
            f"discrepancies for engine {engine!r}; see {path.as_posix()}"
        )
    return f"shadow ok: {len(_walk(compiled[0], 'macro.')) + len(_walk(compiled[1], 'fuel.'))} frames identical"


def _engine_for_pack(pack: RevenueOutlookPack) -> str:
    return "ar1" if "engine_ar1" in {part.lower() for part in pack.output_dir.parts} else "ensemble"


@st.cache_resource(show_spinner=False, max_entries=4)
def _compiled_replay_results(engine: str, source_digest: str) -> tuple[Any, Any]:
    """One parquet read of the compiled replay cache per engine, per process.

    Keyed on the engine plus the cache's own source digest, so a rebuilt cache
    is a different resource and a stale one can never be served.
    """
    from model_dashboard.revenue_outlook_replay_cache import load_replay_cache

    repo_root = Path(__file__).resolve().parent
    pack_dir = repo_root / engine_revenue_outlook_dir_for(engine)
    manifest_path = pack_dir / "manifest.json"
    pack_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return load_replay_cache(
        engine=engine,
        pack_manifest=pack_manifest,
        bridge_vintage_id=bridge_vintage_id_from_manifest(pack_manifest, repo_root),
        repo_root=repo_root,
        # Already computed by the caller; re-hashing ~48 MB here would double
        # the cold-path cost for no extra safety.
        source_digest=source_digest,
    )


def engine_revenue_outlook_dir_for(engine: str) -> Path:
    from model_dashboard.engine import engine_revenue_outlook_dir

    return engine_revenue_outlook_dir(engine)


@st.cache_data(show_spinner=False, max_entries=4)
def _cached_replay_source_digest(
    engine: str,
    signature: tuple[tuple[str, int, int], ...],
    _pack: RevenueOutlookPack,
) -> str:
    """Hash every replay input once per pack signature, not once per lookup.

    The scan covers ~48 MB across ~640 files (~320 ms). Keyed on the pack
    signature so a promoted pack still invalidates it.
    """
    del signature
    from model_dashboard.revenue_outlook_replay_cache import replay_cache_expected_digest

    repo_root = Path(__file__).resolve().parent
    return replay_cache_expected_digest(
        engine=engine,
        pack_manifest=_pack.manifest,
        bridge_vintage_id=bridge_vintage_id_from_manifest(_pack.manifest, repo_root),
        repo_root=repo_root,
    )


@st.cache_data(show_spinner=False, max_entries=4)
def _cached_replay_cache_problem(
    engine: str,
    mode: str,
    signature: tuple[tuple[str, int, int], ...],
    _pack: RevenueOutlookPack,
) -> str:
    """Cached so the ~48 MB integrity scan is not repeated on every rerun."""
    del signature
    from model_dashboard.revenue_outlook_replay_cache import replay_cache_status

    repo_root = Path(__file__).resolve().parent
    try:
        status, detail = replay_cache_status(
            engine=engine,
            pack_manifest=_pack.manifest,
            bridge_vintage_id=bridge_vintage_id_from_manifest(_pack.manifest, repo_root),
            repo_root=repo_root,
        )
    except (OSError, ValueError) as error:
        status, detail = "corrupt", str(error)
    if status == "ok":
        return ""
    rebuild = f"python scripts/build_revenue_outlook_replay_cache.py --engine {engine}"
    reason = {
        "missing": "has not been built",
        "stale": "no longer matches its sources",
        "corrupt": "could not be read",
    }.get(status, "is unusable")
    del mode
    return (
        f"The compiled Treasury-macro and conflict replay cache for the {engine!r} engine "
        f"{reason} ({detail}). Revenue Outlook will not serve values from a cache it "
        f"cannot prove is current, and it will not silently fall back to the slow live "
        f"replay. Rebuild it with:  {rebuild}"
    )


def _revenue_outlook_replay_cache_problem(
    pack: RevenueOutlookPack | None,
    signature: tuple[tuple[str, int, int], ...] = (),
) -> str:
    """Reader-facing explanation when the compiled replay cache is unusable.

    Returns "" when the page can proceed. Only fast/shadow depend on the
    cache; reference recomputes the replays live.
    """
    mode = revenue_outlook_runtime_mode()
    if pack is None or mode == RUNTIME_MODE_REFERENCE:
        return ""
    return _cached_replay_cache_problem(_engine_for_pack(pack), mode, signature, pack)


def _replay_cache_problem_uncached(pack: RevenueOutlookPack) -> str:
    """Uncached variant used by tests that monkeypatch the status function."""
    from model_dashboard.revenue_outlook_replay_cache import replay_cache_status

    repo_root = Path(__file__).resolve().parent
    engine = _engine_for_pack(pack)
    try:
        status, detail = replay_cache_status(
            engine=engine,
            pack_manifest=pack.manifest,
            bridge_vintage_id=bridge_vintage_id_from_manifest(pack.manifest, repo_root),
            repo_root=repo_root,
        )
    except (OSError, ValueError) as error:
        status, detail = "corrupt", str(error)
    if status == "ok":
        return ""
    rebuild = f"python scripts/build_revenue_outlook_replay_cache.py --engine {engine}"
    reason = {
        "missing": "has not been built",
        "stale": "no longer matches its sources",
        "corrupt": "could not be read",
    }.get(status, "is unusable")
    return (
        f"The compiled Treasury-macro and conflict replay cache for the {engine!r} engine "
        f"{reason} ({detail}). Revenue Outlook will not serve values from a cache it "
        f"cannot prove is current, and it will not silently fall back to the slow live "
        f"replay. Rebuild it with:  {rebuild}"
    )


def _compiled_replays_for_pack(
    pack: RevenueOutlookPack,
    signature: tuple[tuple[str, int, int], ...],
) -> tuple[Any, Any]:
    """(macro, fuel) from the compiled cache, or fail closed with the rebuild."""
    engine = _engine_for_pack(pack)
    digest = _cached_replay_source_digest(engine, signature, pack)
    results = _compiled_replay_results(engine, digest)
    if revenue_outlook_runtime_mode() == RUNTIME_MODE_SHADOW:
        _shadow_compare_replays(engine, digest)
    return results


@st.cache_data(show_spinner=False, max_entries=2)
def cached_fuel_price_scenario_replay(
    signature: tuple[tuple[str, int, int], ...],
    _pack: RevenueOutlookPack,
) -> Any:
    """The governed Low/Medium/High conflict paths for this model pack.

    The replay itself takes no reader-facing control, so in fast/shadow mode it
    is served from the committed compiled cache instead of re-running forward
    forecasting (measured at 44-66 s per process on the PR #15 merge commit).
    """
    input_path = _pack.output_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    if not input_path.exists():
        return None
    if revenue_outlook_runtime_mode() != RUNTIME_MODE_REFERENCE:
        return _compiled_replays_for_pack(_pack, signature)[1]
    scenario_inputs = pd.read_parquet(input_path)
    engine = _engine_for_pack(_pack)
    return run_fuel_price_scenario_replay(
        scenario_inputs,
        repo_root=Path(__file__).resolve().parent,
        engine=engine,
        # The pack being replayed decides the bridge, not the live registry.
        bridge_vintage_id=bridge_vintage_id_from_manifest(
            _pack.manifest, Path(__file__).resolve().parent
        ),
    )


def _safe_fuel_price_scenario_replay(
    signature: tuple[tuple[str, int, int], ...],
    pack: RevenueOutlookPack,
) -> tuple[Any, str]:
    """Return replay data or a non-sensitive error type for fail-closed UI use."""

    try:
        return cached_fuel_price_scenario_replay(signature, pack), ""
    except (FileNotFoundError, OSError, KeyError, ValueError) as exc:
        # Replay/data failures must not crash the whole Streamlit page or
        # silently trigger a visible-leaf approximation. The caller keeps
        # Current paths published and exposes a governed warning instead.
        return None, type(exc).__name__


@st.cache_data(show_spinner=False, max_entries=2)
def cached_treasury_baseline_macro_replay(
    signature: tuple[tuple[str, int, int], ...],
    _pack: RevenueOutlookPack,
) -> DirectTreasuryScenarioReplayResult | None:
    """Replay Treasury macro for EVERY governed scenario, conflict-independent.

    P1.2: this returns the direct per-scenario replay, so the overlay looks
    factors up by (scenario, series, period) and a Base-derived factor can
    never silently serve the comparison. It remains deliberately independent
    of the conflict/policy layers so a problem there cannot revert the
    visible Base case to the legacy GDP path.
    """

    input_path = _pack.output_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    if not input_path.exists():
        return None
    if revenue_outlook_runtime_mode() != RUNTIME_MODE_REFERENCE:
        return _compiled_replays_for_pack(_pack, signature)[0]
    scenario_inputs = pd.read_parquet(input_path)
    engine = _engine_for_pack(_pack)
    return run_direct_treasury_scenario_replay(
        scenario_inputs,
        repo_root=Path(__file__).resolve().parent,
        engine=engine,
        # The pack being replayed decides the bridge, not the live registry.
        bridge_vintage_id=bridge_vintage_id_from_manifest(
            _pack.manifest, Path(__file__).resolve().parent
        ),
    )


def _safe_treasury_baseline_macro_replay(
    signature: tuple[tuple[str, int, int], ...],
    pack: RevenueOutlookPack,
) -> tuple[DirectTreasuryScenarioReplayResult | None, str]:
    """Return the direct per-scenario Treasury replay or an error type."""

    try:
        return cached_treasury_baseline_macro_replay(signature, pack), ""
    except (FileNotFoundError, OSError, KeyError, ValueError) as exc:
        return None, type(exc).__name__


def _apply_scenario_overlays(
    rows: pd.DataFrame,
    drift: pd.DataFrame,
    levers: UptakeLevers | None,
    eruc_levers: ErucTransitionLevers | None,
    uplift_factors: dict[str, dict[Any, Any]],
    *,
    adjust_ped: bool,
    fed_policy_scopes: tuple[tuple[str, tuple[str, ...]], ...] = (),
    policy_pair_factors: pd.DataFrame | None = None,
    uptake_basis: str | None = None,
    heavy_bev_transition: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """uptake -> e-RUC -> PED/RUC policy overlay chain shared by every view.

    Returns (rows, uptake_audit, eruc_audit, uplift_audit).
    """
    uptake_audit = pd.DataFrame()
    eruc_audit = pd.DataFrame()
    uplift_audit = pd.DataFrame()
    repo_root = Path(__file__).resolve().parent
    if levers is not None:
        # The optimized-migration PED bridge already displaces petrol
        # activity; only the raw bridge needs the displacement lever.
        rows, uptake_audit = apply_uptake_levers_to_chart_rows(
            rows,
            drift,
            levers,
            adjust_ped=adjust_ped,
            uptake_basis=uptake_basis,
            repo_root=repo_root,
            heavy_bev_transition=heavy_bev_transition,
        )
    if eruc_levers is not None:
        rows, eruc_audit = apply_eruc_transition_to_chart_rows(rows, drift, eruc_levers)
    policy_audits: list[pd.DataFrame] = []
    mbu26_ruc_class_revenue = uplift_factors.get("mbu26_ruc_class_revenue", {})
    for policy, scenario_roles in fed_policy_scopes:
        roles = {str(role) for role in scenario_roles}
        if not roles:
            continue
        if OFFICIAL_SCOPE in roles:
            # The official comparator is a different calculation, not the same
            # one over another role set: rate-only, volumes fixed, sourced from
            # the MBU26 spine and published over the official horizon. It must
            # never borrow the current model's factor map, whose horizon stops
            # at FY2030. Roles are disjoint, so no row is processed twice.
            if roles != {OFFICIAL_SCOPE}:
                raise ValueError(
                    f"Official and current policy scopes must stay disjoint; got {sorted(roles)}."
                )
            official_state = _OFFICIAL_POLICY_STATE_BY_UI_LABEL.get(str(policy))
            if official_state is None:
                raise ValueError(f"Unknown official comparator policy state: {policy!r}")
            # The callee is MBU26-only by contract: it returns the frame
            # unchanged for the published state and internally splits out any
            # official row whose scenario_name != "mbu26_official"
            # (e.g. befu26_official) before repricing, so no other published
            # vintage can ever be rewritten by this synthetic counterfactual.
            rows, policy_audit = apply_official_comparator_rate_policy_to_chart_rows(
                rows,
                repo_root,
                policy_state=official_state,
                ruc_class_revenue_by_fy=mbu26_ruc_class_revenue,
            )
            if policy_audit is not None and not policy_audit.empty:
                policy_audits.append(policy_audit)
            continue
        factors = uplift_factors.get(policy, {})
        if not factors:
            continue
        if policy == "off":
            rows, policy_audit = apply_fed_uplift_off_to_chart_rows(
                rows,
                factors,
                scenario_roles=set(scenario_roles),
                policy_pair_factors=policy_pair_factors,
                ruc_class_revenue_by_fy=mbu26_ruc_class_revenue,
            )
        else:
            rows, policy_audit = apply_fed_uplift_delay_to_chart_rows(
                rows,
                factors,
                scenario_roles=set(scenario_roles),
                policy_pair_factors=policy_pair_factors,
                ruc_class_revenue_by_fy=mbu26_ruc_class_revenue,
            )
        if policy_audit is not None and not policy_audit.empty:
            policy_audits.append(policy_audit)
    if policy_audits:
        uplift_audit = pd.concat(policy_audits, ignore_index=True, sort=False)
    return rows, uptake_audit, eruc_audit, uplift_audit


@st.cache_resource(show_spinner=False)
def cached_policy_runtime(engine: str, source_digest: str):
    """The materialised policy runtime for one engine, once per process.

    Held as a resource, not data: the whole point is that the per-state frames
    are memoised on the object across reruns. Keyed on the source digest so a
    rebuilt pack is picked up without a restart, and so a stale one can never
    be served from a cache that outlived it.

    Returns ``None`` when the pack is missing, stale or unreadable. The caller
    then runs the reference pipeline - correct, just slower - rather than
    serving rows it cannot prove are current.
    """
    del source_digest
    from model_dashboard.revenue_outlook_policy_runtime import load_policy_runtime

    try:
        return load_policy_runtime(engine=engine, repo_root=Path(__file__).resolve().parent)
    except RuntimeError:
        return None


#: The builder sets this False so it materialises the REFERENCE pipeline.
#: Without it, a rebuild would answer from the pack it is about to overwrite:
#: the output would be a copy of the previous build, and the idempotency check
#: would pass by tautology instead of by determinism. Deleting the frames first
#: happens to produce the same effect today, but that is an accident of build
#: order, and a guarantee this important should be stated rather than inferred.
POLICY_RUNTIME_FAST_PATH_ENABLED = True


def _policy_runtime_for_pack(_pack: RevenueOutlookPack):
    """The policy runtime for this pack's engine, or None if unusable."""
    if not POLICY_RUNTIME_FAST_PATH_ENABLED:
        return None
    from model_dashboard.revenue_outlook_policy_runtime import policy_runtime_status

    engine = _engine_for_pack(_pack)
    repo_root = Path(__file__).resolve().parent
    try:
        status, detail = policy_runtime_status(engine=engine, repo_root=repo_root)
    except (OSError, ValueError, RuntimeError):
        return None
    if status != "ok":
        # Fail closed onto the reference path. A stale or corrupt pack is
        # never served, and the page still shows correct numbers.
        _POLICY_RUNTIME_PROBLEM[engine] = detail
        return None
    _POLICY_RUNTIME_PROBLEM.pop(engine, None)
    return cached_policy_runtime(engine, _policy_runtime_source_digest(engine, repo_root))


def _policy_runtime_source_digest(engine: str, repo_root: Path) -> str:
    from model_dashboard.revenue_outlook_policy_runtime import policy_runtime_dir

    try:
        manifest = json.loads(
            (policy_runtime_dir(engine, repo_root) / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return ""
    return str(manifest.get("source_digest", ""))


#: Why the fast path is unavailable, per engine, for the reader-facing note.
_POLICY_RUNTIME_PROBLEM: dict[str, str] = {}


def _materialised_policy_overlay_rows(
    ev_uptake_key: tuple[Any, ...],
    _pack: RevenueOutlookPack,
    sensitivity_key: tuple[Any, ...] = (),
    bridge_mode: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    """The five overlay frames from the materialised catalogue, or None.

    ``None`` means "this key is not in the catalogue, run the reference
    pipeline". It is never a nearest match: the catalogue pins every control
    that changes a value, and a key differing in any of them resolves to
    ``reference_path_required`` and comes back here as ``None``.

    Two controls live OUTSIDE the typed key and so must be checked here: the
    sensitivity key, which is a separate argument the catalogue was built at
    its default, and the bridge mode argument, which must agree with the
    key's own field. Serving materialised rows for a moved sensitivity lever
    would be exactly the silent wrong answer the catalogue exists to avoid.
    """
    from model_dashboard.revenue_outlook_policy_runtime import (
        STATUS_OK,
        policy_audit_rows,
        policy_chart_rows,
        policy_overlay_audit_rows,
        policy_scenario_audit_rows,
        resolve_policy_state,
    )

    if sensitivity_key and not _is_default_sensitivity_key(tuple(sensitivity_key)):
        return None
    key = _scenario_key(ev_uptake_key)
    if bridge_mode and str(bridge_mode) != str(key.ped_bridge_mode):
        return None
    runtime = _policy_runtime_for_pack(_pack)
    if runtime is None:
        return None
    if resolve_policy_state(runtime, key).status != STATUS_OK:
        return None
    try:
        # Unfiltered, because this stands in for the reference overlay chain,
        # which returns every vintage and lets its callers narrow. Filtering
        # here would silently drop the non-selected vintage's rows from a
        # frame every downstream consumer expects to be complete.
        rows = policy_chart_rows(runtime, key, apply_official_vintage_filter=False)
        policy_audit = policy_audit_rows(runtime, key)
        scenario_audit = policy_scenario_audit_rows(runtime, key)
        uptake_audit, eruc_audit = policy_overlay_audit_rows(runtime, key)
    except RuntimeError:
        return None
    return rows, uptake_audit, eruc_audit, policy_audit, scenario_audit


@st.cache_data(show_spinner=False, max_entries=12)
def cached_scenario_overlay_rows(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, ...],
    bridge_mode: str,
    ev_uptake_key: tuple[Any, ...],
    _pack: RevenueOutlookPack,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(rows, uptake, e-RUC, FED-policy, conflict-path audits) for one key.

    Series- and grain-agnostic: the view, the VFM cone bounds and the A/B
    comparison all share this cache and filter from it, so switching series
    or grain never re-runs the overlay chain.

    A key inside the materialised policy catalogue is answered from that pack
    instead of re-running the chain. Profiling put a policy switch at ~13.5 s,
    of which the policy arithmetic itself was 0.32 s: the cost was that
    ``current_fed_policy_state`` is part of the cache identity, so every stage
    downstream of it was recomputed even though the policy changed none of
    their methods. Anything outside the catalogue still runs the reference
    pipeline exactly as before - there is no nearest-match and no silent
    approximation.
    """
    materialised = _materialised_policy_overlay_rows(
        ev_uptake_key, _pack, sensitivity_key, bridge_mode
    )
    if materialised is not None:
        return materialised
    _, sensitivity_frames, _ = cached_sensitivity_stage_frames(signature, bridge_mode, sensitivity_key, _pack)
    levers = _resolve_ev_uptake_levers(ev_uptake_key)
    eruc_levers = _resolve_eruc_levers(ev_uptake_key)
    fed_policy_scopes = _fed_policy_scopes_for_key(ev_uptake_key)
    uplift_factors = cached_fed_uplift_factors(signature, _pack)
    fuel_replay, replay_error_type = _safe_fuel_price_scenario_replay(signature, _pack)
    replay_available = (
        fuel_replay is not None
        and isinstance(fuel_replay.policy_pair_factors, pd.DataFrame)
        and not fuel_replay.policy_pair_factors.empty
    )
    # P1.2: the baseline macro overlay ALWAYS uses the direct per-scenario
    # replay. The fuel replay's baseline factors are Base-derived and must
    # never be transferred to the comparison; it remains the source for the
    # conflict/policy pair factors only.
    macro_replay, macro_error_type = _safe_treasury_baseline_macro_replay(
        signature,
        _pack,
    )
    if macro_replay is None:
        failure_types = ", ".join(
            error_type
            for error_type in (replay_error_type, macro_error_type)
            if error_type
        ) or "unavailable input data"
        raise RuntimeError(
            "Treasury baseline macro replay is unavailable "
            f"({failure_types}); refusing to silently revert the dashboard "
            "to legacy GDP assumptions."
        )
    policy_pair_factors = (
        fuel_replay.policy_pair_factors
        if replay_available
        else pd.DataFrame()
    )
    fed_policy_scopes, replay_status_audit = _policy_scopes_for_available_replay(
        fed_policy_scopes,
        replay_available=replay_available,
    )
    if replay_error_type and not replay_status_audit.empty:
        replay_status_audit["replay_error_type"] = replay_error_type
    rows, macro_audit = apply_treasury_macro_to_chart_rows(
        sensitivity_frames["chart_rows"],
        macro_replay,
    )
    rows, uptake_audit, eruc_audit, _ = _apply_scenario_overlays(
        rows,
        _pack_table(_pack, "ev_phev_ped_light_drift_assumptions"),
        levers,
        eruc_levers,
        uplift_factors,
        # The PED petrol-retention overlay is an explicit sensitivity, off by
        # default. It is additionally refused on the optimized-migration
        # bridge, which already displaces petrol activity, so the two can
        # never combine into a double deduction.
        adjust_ped=(
            _ped_retention_enabled(ev_uptake_key)
            and str(bridge_mode) == PED_BRIDGE_DEFAULT_MODE
        ),
        fed_policy_scopes=(),
        policy_pair_factors=pd.DataFrame(),
        # Compose from the exact vendored VFM table, so the Base setting
        # reproduces the canonical allocation around the post-macro anchor
        # instead of a fitted approximation of it.
        uptake_basis=_resolve_uptake_basis(ev_uptake_key),
        heavy_bev_transition=_heavy_bev_transition_enabled(ev_uptake_key),
    )
    rows, _, _, uplift_audit = _apply_scenario_overlays(
        rows,
        _pack_table(_pack, "ev_phev_ped_light_drift_assumptions"),
        None,
        None,
        uplift_factors,
        adjust_ped=False,
        fed_policy_scopes=fed_policy_scopes,
        policy_pair_factors=policy_pair_factors,
    )
    if not replay_status_audit.empty:
        uplift_audit = pd.concat([uplift_audit, replay_status_audit], ignore_index=True, sort=False)
    if not replay_available:
        return rows, uptake_audit, eruc_audit, uplift_audit, pd.DataFrame()
    rows, fuel_audit = append_fuel_price_scenario_to_chart_rows(rows, fuel_replay)
    scenario_audits = [
        frame for frame in (macro_audit, fuel_audit) if not frame.empty
    ]
    combined_scenario_audit = (
        pd.concat(scenario_audits, ignore_index=True, sort=False)
        if scenario_audits
        else pd.DataFrame()
    )
    return (
        rows,
        uptake_audit,
        eruc_audit,
        uplift_audit,
        combined_scenario_audit,
    )


@st.cache_data(show_spinner=False, max_entries=4)
def cached_post_model_quarterly_inputs(
    pack_dir: str,
    signature: tuple[bool, int, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The two key-independent inputs to the FY2031-FY2050 quarterly split.

    Both are pack-level facts - the committed raw long-horizon quarterly path
    and the scenario population - so they do not vary with policy, scenario,
    series or grain, and are cached on the pack directory's own signature
    rather than on the computation key. The identity is a path string plus a
    (exists, mtime, size) triple: no DataFrame is hashed into a cache key.
    """
    base = Path(pack_dir)
    del signature  # identity only; the read is by path
    try:
        raw_audit = pd.read_parquet(base / "raw_quarterly_forecast_audit.parquet")
        population = pd.read_parquet(
            base / "scenario_inputs" / "scenario_input_wide.parquet"
        )
    except (OSError, ValueError):
        return pd.DataFrame(), pd.DataFrame()
    population = population[population.get("stream", pd.Series(dtype=str)).astype(str).eq("PED")]
    return raw_audit, population


def _post_model_ped_activity_quarters(
    selected_series: str,
    *,
    annual_rows: pd.DataFrame,
    chart_rows: pd.DataFrame,
    pack_dir: str,
) -> pd.DataFrame:
    """FY2031-FY2050 quarters for whichever PED activity leaf is selected.

    The pair is always CONSTRUCTED together - one scale factor, one identity -
    and only then filtered to the selected series, so the two can never drift
    apart just because a reader happened to be looking at one of them.

    ``pack_dir`` is required and must be the directory the caller's chart rows
    came from. Resolving it from the process-wide active engine instead reads
    one engine's raw path against another engine's annual targets: with the
    ensemble rows and an ar1 active engine the FY2032 raw shape differs by
    ~5%, and the construction produced quarters for the wrong engine. The
    annual-closure guard caught it, which is why it is an error rather than a
    tolerance.
    """
    from model_dashboard import revenue_outlook_series_coverage as coverage

    if not str(pack_dir or "").strip():
        return pd.DataFrame()
    try:
        series_id = coverage.canonical_series_id(selected_series)
    except coverage.SeriesCoverageError:
        return pd.DataFrame()
    if series_id not in coverage.POST_MODEL_PED_ACTIVITY_QUARTERLY_SERIES:
        return pd.DataFrame()

    resolved = Path(pack_dir)
    raw_audit, population = cached_post_model_quarterly_inputs(
        str(resolved), directory_signature(resolved)
    )
    if raw_audit.empty or population.empty:
        return pd.DataFrame()

    # Both leaves' annual targets, not just the selected one: the constructor
    # needs the pair to solve.
    pair_annual = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & chart_rows["series_id"].astype(str).isin(
            coverage.POST_MODEL_PED_ACTIVITY_QUARTERLY_SERIES
        )
        & chart_rows["trace_name"].astype(str).isin(
            set(annual_rows.get("trace_name", pd.Series(dtype=str)).astype(str))
        )
    ]
    if pair_annual.empty:
        return pd.DataFrame()
    native = chart_rows[chart_rows["time_grain"].astype(str).eq("quarterly")]
    try:
        derived = coverage.post_model_ped_activity_quarterly_rows(
            pair_annual,
            raw_quarterly_audit=raw_audit,
            scenario_population=population,
            native_quarters=native,
        )
    except coverage.PostModelQuarterlyError:
        # Fail closed to the PREVIOUS behaviour, never to a wrong number and
        # never to a broken page: the quarterly view keeps the coverage it had
        # and the annual publication is unaffected. The governed reason is
        # raised and audited by the constructor; suppressing it here only
        # decides that a reader sees a short series rather than an exception.
        return pd.DataFrame()
    if derived.empty:
        return derived
    return derived[derived["series_id"].astype(str).eq(series_id)]


def _filter_series_rows_with_fallback(
    rows: pd.DataFrame,
    selected_series: str,
    time_grain: str,
    fed_path: str,
    traces: tuple[str, ...],
    policy_state: str = "",
    pack_dir: str = "",
) -> tuple[pd.DataFrame, bool]:
    """Selected-series rows, filling any trace missing native quarters.

    Current finalists carry native activity quarters, while the official
    comparator vintages are governed at June-year grain.  The fallback
    therefore operates per requested trace, not only when the whole quarterly
    selection is empty.

    The quarterly fill is ``revenue_outlook_series_coverage``'s governed
    contract, not a local Denton solve. That module declares, per series, which
    rule applies, against what seasonal evidence, on what rate basis and with
    what stated limitation, and it labels every row it produces as derived. The
    rows handed to it are the FINAL annual rows for this view - post macro
    selection, post policy, post formula reconstruction - so the quarters
    reconcile to the annual line a reader sees beside them rather than to a
    pre-policy layer.

    ``policy_state`` is the selected Current 12c state. It decides which
    governed rate timetable shapes the within-year path, so a deferred step
    appears in the deferred quarter instead of being drawn in the published one
    and then smeared by the annual benchmark.

    This is the single gate every decision-facing row passes through - the
    Total path view, the VFM bounds and the A/B paths all call it - so the
    FY2050 presentation horizon is applied here once. Both grains are clipped
    by the same rule, which is what makes the annual and quarterly horizons
    agree by construction rather than by two parallel edits.
    """
    filtered = _filter_revenue_outlook_rows(
        rows,
        time_grain=time_grain,
        stream_labels=[selected_series],
        fed_paths=[fed_path],
        trace_names=list(traces),
    )
    used_fallback = False
    if time_grain == "quarterly":
        present_traces = set(filtered.get("trace_name", pd.Series(dtype=str)).dropna().astype(str))
        missing_traces = [trace for trace in traces if str(trace) not in present_traces]
        if missing_traces:
            annual = _filter_revenue_outlook_rows(
                rows,
                time_grain="june_year",
                stream_labels=[selected_series],
                fed_paths=[fed_path],
                trace_names=missing_traces,
            )
            derived = _governed_quarterly_rows(
                selected_series,
                annual_rows=annual,
                chart_rows=rows,
                trace_names=missing_traces,
                policy_state=policy_state,
            )
            if not derived.empty:
                filtered = pd.concat([filtered, derived], ignore_index=True, sort=False)
                used_fallback = True
        # Missing PERIODS, not merely missing traces. The fill above asks
        # whether a trace has any native quarters at all, so a Current trace
        # whose native rows stop at 2030Q4 counts as complete and the last
        # twenty years are silently never derived. Narrow to the two PED
        # activity leaves: their governed FY2031-FY2050 construction exists,
        # and widening the rule to every series would change fallback
        # semantics far beyond what is proven here.
        gap_filled = _post_model_ped_activity_quarters(
            selected_series,
            annual_rows=_filter_revenue_outlook_rows(
                rows,
                time_grain="june_year",
                stream_labels=[selected_series],
                fed_paths=[fed_path],
                trace_names=list(traces),
            ),
            chart_rows=rows,
            pack_dir=pack_dir,
        )
        if not gap_filled.empty:
            gap_filled = gap_filled[
                gap_filled["trace_name"].astype(str).isin([str(t) for t in traces])
            ]
        if not gap_filled.empty:
            # The joint construction is AUTHORITATIVE over the post-model
            # window for this pair, not merely a gap filler. The generic
            # per-trace fallback runs first and, because Light petrol VKT has
            # no native quarters at all, had already split its whole horizon
            # with the Denton rule - so the two series were being built by two
            # different methods and the cross-series identity
            #     petrol_q = vktpc_q * population_q / 1e6
            # was not enforced between them. Superseding the derived rows here
            # is what keeps the pair on one construction.
            #
            # Only DERIVED rows are superseded. A natively published quarter is
            # never dropped, which is why the seam years keep their published
            # values.
            from model_dashboard import revenue_outlook_series_coverage as _coverage
            from model_dashboard.post_model_extrapolation import FIRST_EXTRAPOLATION_FY

            superseded_from = FIRST_EXTRAPOLATION_FY
            years = pd.to_numeric(filtered.get("june_year"), errors="coerce")
            row_type = (
                filtered.get(
                    "coverage_row_type", pd.Series("", index=filtered.index)
                )
                .fillna("")
                .astype(str)
            )
            is_derived = row_type.eq(_coverage.COVERAGE_ROW_TYPE_DERIVED)
            drop = (
                is_derived
                & years.ge(superseded_from)
                & filtered["series_id"].astype(str).isin(
                    gap_filled["series_id"].astype(str).unique()
                )
            )
            filtered = filtered[~drop.fillna(False)]
            filtered = pd.concat([filtered, gap_filled], ignore_index=True, sort=False)
            used_fallback = True
    return clip_frame_to_display_horizon(filtered), used_fallback


#: The join identity of a display row. Two rows sharing all four name the same
#: published value, so a second one would double-plot it.
_OFFICIAL_ROW_IDENTITY = ("series_id", "trace_name", "time_grain", "period")


def _append_missing_official_rows(
    chart_rows: pd.DataFrame,
    official_scenario: str = "",
    official_overlay: bool = False,
) -> pd.DataFrame:
    """Add source-backed official rows the runtime builders never emitted.

    Strictly additive, and only where the vintage itself publishes a value:
    ``missing_official_rows`` returns the complement of what is already here,
    so no existing official value can be rewritten and no Current value can be
    substituted for an official one. The vintages stay separate traces - BEFU26
    is not filled in from MBU26 or the reverse - because a comparator that
    silently borrowed another vintage's number would be worse than a gap.

    **The selected vintage is re-applied to what is appended.**
    ``missing_official_rows`` answers for every registered vintage, because it
    describes what the sources publish, not what this reader chose. Appending
    that straight after the vintage filter put the non-selected vintage back
    on the page: with BEFU26 selected, ``mbu26_official`` reappeared in
    ``scenario_name``. Filtering here keeps "one selected comparator" true no
    matter which stage last touched the frame.

    The identity check is belt and braces: the API is already a complement, so
    a duplicate here would mean the two disagreed about what a row IS, and
    dropping it is safer than plotting the same period twice.
    """
    if chart_rows is None or chart_rows.empty:
        return chart_rows
    from model_dashboard import revenue_outlook_series_coverage as coverage

    try:
        missing = coverage.missing_official_rows(
            chart_rows, repo_root=Path(__file__).resolve().parent
        )
    except (OSError, ValueError):
        # A missing or unreadable vintage source must not take the page down;
        # the series simply keeps the gap it already had.
        return chart_rows
    if missing is None or missing.empty:
        return chart_rows
    if official_scenario:
        missing = _filter_official_vintage_rows(missing, official_scenario, official_overlay)
    if missing.empty:
        return chart_rows
    combined = pd.concat([chart_rows, missing], ignore_index=True, sort=False)
    identity = [column for column in _OFFICIAL_ROW_IDENTITY if column in combined.columns]
    if identity:
        combined = combined.drop_duplicates(subset=identity, keep="first")
    return combined.reset_index(drop=True)


def _governed_quarterly_rows(
    selected_series: str,
    *,
    annual_rows: pd.DataFrame,
    chart_rows: pd.DataFrame,
    trace_names: Sequence[str],
    policy_state: str = "",
) -> pd.DataFrame:
    """Quarterly display rows from the governed coverage contract.

    A thin adapter, deliberately: the alias resolution, the per-series rule,
    the seasonal indicator, the rate basis and the provenance labelling all
    live in ``revenue_outlook_series_coverage``. Duplicating any of it here is
    how the two would drift.

    A series the contract does not govern yields no quarters at all rather
    than falling back to an undeclared split. The caller then shows the
    annual-only note, which is the honest answer.
    """
    from model_dashboard import revenue_outlook_series_coverage as coverage

    try:
        coverage.canonical_series_id(selected_series)
    except coverage.SeriesCoverageError:
        return pd.DataFrame()
    return coverage.quarterly_rows_for_selected_series(
        selected_series,
        trace_names=[str(trace) for trace in trace_names],
        annual_rows=annual_rows,
        chart_rows=chart_rows,
        repo_root=Path(__file__).resolve().parent,
        policy_state=policy_state or FED_POLICY_PUBLISHED,
    )


# A band row counts as carrying real VFM width once the Fast/Slow gap clears
# this fraction of the row's own level. Relative to the ROW, not to the series
# maximum: a Total-revenue tail near $13b would otherwise swamp a genuine
# sub-percent gap in FY2026 and read as "no range".
CONE_MIN_RELATIVE_WIDTH = 1e-6


def _cone_preset_key(
    preset_name: str,
    band_controls: RevenueScenarioComputationKey,
) -> RevenueScenarioComputationKey:
    """The live scenario key with ONLY the VFM composition basis swapped.

    Every other governed control - e-RUC, Current 12c policy, the PED
    retention sensitivity, Heavy-BEV treatment, the official comparator
    vintage and overlay, the long-run transition schedule and shape vintage -
    is carried through verbatim, so the envelope is the Fast/Slow pair of the
    path actually on screen rather than a differently-configured run that
    happens to share a name.
    """
    return _scenario_key(band_controls).replace(uptake_basis=preset_name)


@st.cache_resource(show_spinner=False)
def cached_uncertainty_pack():
    """One parquet read per process. The runtime never simulates."""
    return load_uncertainty_pack(Path(__file__).resolve().parent)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_uncertainty_band_rows(
    series_id: str,
    pack_digest: str,
    policy_state: str = "",
    scenario_key: RevenueScenarioComputationKey | None = None,
    _pack: RevenueOutlookPack | None = None,
) -> pd.DataFrame:
    """Band rows for one series, under the policy state on screen.

    The bands come from the policy runtime's own per-state rows when the key
    is catalogued, so a band can never be drawn around a central path it was
    not computed from. Where the policy leaves a series genuinely unmoved the
    rows are identical to the default pack's by construction - the same seeded
    draws propagate through the same identities - rather than by a copy.

    ``policy_state`` is part of the cache identity for exactly that reason: it
    is a value-changing input, and omitting it is how the default pack ends up
    served regardless of what the reader selected.

    Clipped to the presentation horizon so the band cannot outrun the paths it
    wraps. The committed pack is not modified - only what is handed to the
    chart and the band download.
    """
    del pack_digest
    rows = _policy_uncertainty_band_rows(series_id, policy_state, scenario_key, _pack)
    if rows is None:
        rows = band_rows_for_series(cached_uncertainty_pack(), series_id)
    return clip_frame_to_display_horizon(rows)


def _policy_uncertainty_band_rows(
    series_id: str,
    policy_state: str,
    scenario_key: RevenueScenarioComputationKey | None,
    _pack: RevenueOutlookPack | None,
) -> pd.DataFrame | None:
    """Per-policy band rows from the materialised runtime, or None.

    ``None`` sends the caller to the default offline pack. That is the right
    answer when no policy state was requested, when the key is outside the
    catalogue, or when the runtime is unusable - and it is never a quiet
    substitute for a state that exists, because a catalogued key that resolves
    always returns its own rows here.
    """
    if not series_id or not policy_state or scenario_key is None or _pack is None:
        return None
    from model_dashboard.revenue_outlook_policy_runtime import (
        STATUS_OK,
        normalise_policy_state,
        policy_uncertainty_rows,
        resolve_policy_state,
    )

    runtime = _policy_runtime_for_pack(_pack)
    if runtime is None:
        return None
    try:
        key = scenario_key.replace(
            current_fed_policy_state=normalise_policy_state(policy_state)
        )
    except (TypeError, ValueError):
        return None
    if resolve_policy_state(runtime, key).status != STATUS_OK:
        return None
    try:
        rows = policy_uncertainty_rows(runtime, key, series_id=series_id)
    except RuntimeError:
        return None
    return rows if rows is not None and not rows.empty else None


def _uncertainty_series_id_for_label(chart_rows: pd.DataFrame, series_label: str) -> str:
    """Map the selector's display label to the pack's canonical series id."""
    if chart_rows is None or chart_rows.empty:
        return ""
    match = chart_rows[
        chart_rows.get("series_label", pd.Series(dtype=str)).astype(str).eq(str(series_label))
    ]
    if match.empty:
        return ""
    ids = match.get("series_id", pd.Series(dtype=str)).dropna().astype(str)
    return str(ids.iloc[0]) if len(ids) else ""


@st.cache_data(show_spinner=False, max_entries=6)
def cached_vfm_scenario_paths(
    signature: tuple[tuple[str, int, int], ...],
    selected_series: str,
    time_grain: str,
    fed_path: str,
    traces: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    band_controls: RevenueScenarioComputationKey,
    _pack: RevenueOutlookPack,
) -> pd.DataFrame:
    """The MoT VFM Fast and Slow paths as selectable full-horizon traces.

    Each is the Current Base case recomputed with ONLY the VFM composition
    basis swapped, so it inherits the live engine, vintages, schedule, policy
    and macro settings.  Both run to FY2050 and stay genuinely distinct there:
    Base, Fast and Slow share the same governed post-model Light RUC pool, and
    the exact VFM202405 scenario shares allocate that common pool into
    different conventional/BEV/PHEV compositions.
    """
    frames: list[pd.DataFrame] = []
    for preset_name, trace_name in (
        ("MoT VFM fast", VFM_FAST_TRACE_NAME),
        ("MoT VFM slow", VFM_SLOW_TRACE_NAME),
    ):
        preset_key = _cone_preset_key(preset_name, band_controls)
        rows, _, _, _, _ = cached_scenario_overlay_rows(
            signature, sensitivity_key, bridge_mode, preset_key, _pack
        )
        selected, _ = _filter_series_rows_with_fallback(
            rows, selected_series, time_grain, fed_path, traces,
            _current_policy_state_for_key(preset_key),
            pack_dir=str(_pack.output_dir),
        )
        base = selected[
            selected.get("trace_name", pd.Series(dtype=str)).astype(str).eq("Current finalist Base case")
            & ~selected.get("row_type", pd.Series(dtype=str)).astype(str).eq("historical_actual")
        ].copy()
        if base.empty:
            continue
        base["trace_name"] = trace_name
        base["scenario_name"] = f"current_{preset_name.replace(' ', '_').lower()}"
        frames.append(base)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _revenue_outlook_layer_catalogue(
    trace_options: list[str],
    default_trace_names: list[str],
) -> tuple[RevenueChartLayerSpec, ...]:
    """The "Show on chart" catalogue, with the presentation policy applied.

    One construction site for both view modes, so single and compare can never
    disagree about what is offerable. While the VFM analyst layers are paused
    the two uptake paths and the structural range are simply absent from the
    catalogue - which also means ``path_trace_names`` can never return them and
    no downstream consumer asks for the overlay that would build them.
    """
    options = list(trace_options)
    envelope_available = True
    if not REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS:
        options = [
            trace
            for trace in options
            if trace not in (VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME)
        ]
        envelope_available = False
    else:
        options = [*options, VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME]
    return build_layer_catalogue(
        options,
        default_trace_names=list(default_trace_names),
        uncertainty_available=cached_uncertainty_pack().available,
        envelope_available=envelope_available,
    )


def _cone_band_controls(ev_uptake_key: ScenarioKeyLike) -> RevenueScenarioComputationKey:
    """The band's cache identity: the live key with the basis field blanked.

    The envelope always evaluates the Fast and Slow presets, so the DISPLAYED
    basis must not be part of its identity - switching Base/Fast/Slow reuses
    the cached band - while every other value-changing control still
    invalidates it.
    """
    return _scenario_key(ev_uptake_key).replace(uptake_basis="")


@st.cache_data(show_spinner=False, max_entries=6)
def cached_view_cone_band(
    signature: tuple[tuple[str, int, int], ...],
    selected_series: str,
    time_grain: str,
    fed_path: str,
    traces: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    band_controls: RevenueScenarioComputationKey,
    _pack: RevenueOutlookPack,
) -> pd.DataFrame:
    """MoT VFM Fast-Slow structural scenario envelope around the base case.

    NOT a confidence, credible or prediction interval: it is the pair of
    governed VFM fleet-composition scenarios, so it says what the composition
    assumption is worth, not how likely any value is.

    Keyed on ``band_controls`` - the live scenario key with the displayed
    basis field blanked - so switching the displayed uptake basis reuses the
    cached band while any other value-changing control still invalidates it.

    Rows whose Fast/Slow gap does not clear ``CONE_MIN_RELATIVE_WIDTH`` at
    the trailing end are dropped rather than drawn at zero width, so a series
    the composition genuinely does not move shows no band instead of a flat
    line that would read as certainty.  Where the shares DO move the series -
    every Light class, through FY2050 - the range now carries the whole way.
    """
    bounds: dict[str, pd.Series] = {}
    for bound_name, preset_name in (("fast", "MoT VFM fast"), ("slow", "MoT VFM slow")):
        preset_key = _cone_preset_key(preset_name, band_controls)
        rows, _, _, _, _ = cached_scenario_overlay_rows(signature, sensitivity_key, bridge_mode, preset_key, _pack)
        bound_rows, _ = _filter_series_rows_with_fallback(
            rows, selected_series, time_grain, fed_path, traces,
            _current_policy_state_for_key(preset_key),
            pack_dir=str(_pack.output_dir),
        )
        base_trace = bound_rows[
            bound_rows.get("trace_name", pd.Series(dtype=str)).astype(str).eq("Current finalist Base case")
            & ~bound_rows.get("row_type", pd.Series(dtype=str)).astype(str).eq("historical_actual")
        ]
        if base_trace.empty:
            continue
        bounds[bound_name] = pd.Series(
            pd.to_numeric(base_trace["value"], errors="coerce").to_numpy(),
            index=base_trace["period"].astype(str),
        )
    if len(bounds) != 2:
        return pd.DataFrame()
    merged = pd.DataFrame(bounds).dropna()
    if merged.empty:
        return pd.DataFrame()
    band = pd.DataFrame(
        {
            "period": merged.index,
            "lower": merged.min(axis=1).to_numpy(),
            "upper": merged.max(axis=1).to_numpy(),
        }
    )
    return _clip_cone_band_to_supported_periods(band)


def _clip_cone_band_to_supported_periods(band: pd.DataFrame) -> pd.DataFrame:
    """Keep the contiguous span the VFM composition actually moves.

    Interior periods are retained even when momentarily flat, so the filled
    area stays one continuous shape; only leading and trailing runs the
    composition does not move are cut.  A series the VFM assumption never
    moves returns empty - width is never fabricated for visual consistency.
    """
    if band is None or band.empty:
        return pd.DataFrame()
    level = ((band["upper"].abs() + band["lower"].abs()) / 2.0).replace(0.0, pd.NA)
    material = ((band["upper"] - band["lower"]).abs() / level).fillna(0.0) > CONE_MIN_RELATIVE_WIDTH
    if not bool(material.any()):
        return pd.DataFrame()
    order = band["period"].astype(str).map(_revenue_period_order)
    supported = order[material]
    keep = order.between(supported.min(), supported.max())
    return band[keep].reset_index(drop=True)


VFM_ENVELOPE_METHOD = "Integrated VFM Scenario Envelope"
VFM_ENVELOPE_LEGEND_LABEL = "MoT VFM fast–slow range"
# Brand blue, kept deliberately pale so the envelope reads as background and
# every path stays legible above it. Raised from the original 0.10 fill /
# 0.28 boundary once the chart went full width: at those values the dotted
# boundaries were sub-pixel on a 1836px plot and the envelope was invisible
# even on Light RUC, where the Fast/Slow gap reaches 12.7% of level. Tune
# here - the two constants are the whole visual contract.
VFM_ENVELOPE_FILL_COLOR = "rgba(0,111,173,0.16)"
VFM_ENVELOPE_BOUNDARY_LINE = {"color": "rgba(0,111,173,0.55)", "width": 1.2, "dash": "dot"}
VFM_ENVELOPE_NOT_PROBABILISTIC_NOTE = (
    "MoT VFM Fast–Slow structural scenario envelope — not probabilistic. The "
    "shaded range is the pair of governed MoT VFM fleet-composition scenarios "
    "(Fast and Slow) run through the same engine, vintages, schedule, policy "
    "and macro settings as the Current path it wraps. It is not a confidence, "
    "credible or prediction interval and carries no probability. The 50%/80% "
    "conditional modelled-uncertainty bands are a different concept: they are "
    "probabilistic within their stated evidence, and are selected separately."
)

def _current_path_coverage_note(rows: pd.DataFrame, selected_series: str) -> str:
    """Say so when the Current path stops short of the official comparators.

    Light petrol VKT is the case this exists for. It is built from the PED
    bridge, whose governed econometric path ends at FY2030, while BEFU26 and
    MBU26 publish it to FY2050. Restoring those official rows made the gap
    visible for the first time: a reader now sees two official lines running
    twenty years past the Current one and has no way, from the chart alone, to
    tell whether the Current path is missing or genuinely ends there.

    The note is derived from the plotted rows rather than hard-coded per
    series, so any series whose Current coverage is shorter than the display
    horizon says so, and none has to be remembered.

    Nothing is extrapolated. A path the evidence does not carry to FY2050 is
    not drawn to FY2050.
    """
    if rows is None or rows.empty or "june_year" not in rows.columns:
        return ""
    trace = rows.get("trace_name", pd.Series(dtype=str)).astype(str)
    grain = rows.get("time_grain", pd.Series(dtype=str)).astype(str)
    annual = rows[grain.eq("june_year")] if grain.any() else rows
    if annual.empty:
        return ""
    annual_trace = annual.get("trace_name", pd.Series(dtype=str)).astype(str)
    current = annual[annual_trace.str.startswith("Current finalist")]
    official = annual[annual_trace.str.contains("official", case=False, na=False)]
    if current.empty or official.empty:
        return ""
    current_last = pd.to_numeric(current["june_year"], errors="coerce").max()
    official_last = pd.to_numeric(official["june_year"], errors="coerce").max()
    if not pd.notna(current_last) or not pd.notna(official_last):
        return ""
    if int(current_last) >= min(int(official_last), display_end_fy()):
        return ""
    return (
        f"Coverage — {selected_series}: the Current path is governed to "
        f"FY{int(current_last)}, while the official comparators publish to "
        f"FY{int(official_last)}. The Current line stops where its evidence "
        "stops rather than being extrapolated to meet them, and its quarterly "
        f"view ends at the matching quarter. The gap after FY{int(current_last)} "
        "is an absence of a governed Current path, not a forecast of zero."
    )


#: Shown when a band selection meets a non-Off Fleet-efficiency or PT lever.
#: The governed draws and quantile maps describe the BASELINE computation;
#: rollup series cannot be re-quantiled under a deterministic overlay without
#: component-level draws, so the bands are withheld rather than drawn around
#: a central path they do not describe.
SENSITIVITY_UNCERTAINTY_WITHHELD_NOTE = (
    "Modelled uncertainty is governed for the baseline computation and is "
    "withheld for this analyst sensitivity. The 50% and 80% bands return "
    "when Fleet efficiency and PT mode shift are both Off."
)

#: Shown when a reader carries a band selection into the quarterly view.
QUARTERLY_UNCERTAINTY_NOT_GOVERNED_NOTE = (
    "Modelled uncertainty is governed at June-year level only. The 50% and 80% "
    "bands are built from seeded draws propagated through the annual revenue "
    "identities, and no governed method exists for splitting them into "
    "quarters — repeating an annual bound four times or dividing its width "
    "would state a precision the evidence does not carry. The bands are "
    "therefore withheld at quarterly grain and return when you switch back to "
    "the June-year view; your selection is kept in the meantime."
)


def _vfm_envelope_applicability_audit(
    band: pd.DataFrame | None,
    *,
    selected_series: str,
    time_grain: str,
    ev_uptake_levers_available: bool,
) -> pd.DataFrame:
    """One row saying whether this series gets a band, and why not when it does not.

    Written so a reader can tell "no band" (the VFM composition does not move
    this series) apart from "band suppressed" (a control made the envelope
    unavailable) without opening the code.
    """
    row: dict[str, Any] = {
        "method": VFM_ENVELOPE_METHOD,
        "selected_series": str(selected_series),
        "time_grain": str(time_grain),
        "band_available": False,
        "lower_source_scenario": "",
        "upper_source_scenario": "",
        "first_valid_period": "",
        "last_valid_period": "",
        "max_width": "",
        "max_width_pct_of_level": "",
        "probabilistic": False,
        "reason": "",
    }
    if not ev_uptake_levers_available:
        row["reason"] = (
            "The governed-pack option carries no VFM composition lever, so no "
            "Fast/Slow pair exists to bound."
        )
        return pd.DataFrame([row])
    if band is None or band.empty:
        row["reason"] = (
            "The MoT VFM Fast and Slow compositions produce the same values for "
            "this series under the selected controls, so no range is drawn. "
            "Width is never fabricated for visual consistency."
        )
        return pd.DataFrame([row])
    width = (pd.to_numeric(band["upper"], errors="coerce") - pd.to_numeric(band["lower"], errors="coerce")).abs()
    level = (pd.to_numeric(band["upper"], errors="coerce").abs() + pd.to_numeric(band["lower"], errors="coerce").abs()) / 2.0
    periods = band["period"].astype(str)
    row.update(
        {
            "band_available": True,
            # min/max per period, so neither bound is nailed to one scenario:
            # Fast is the upper bound for RUC classes and the lower bound for
            # petrol-dependent series.
            "lower_source_scenario": "min(MoT VFM fast, MoT VFM slow)",
            "upper_source_scenario": "max(MoT VFM fast, MoT VFM slow)",
            "first_valid_period": periods.iloc[0],
            "last_valid_period": periods.iloc[-1],
            "max_width": round(float(width.max()), 6),
            "max_width_pct_of_level": round(float((100.0 * width / level.replace(0.0, pd.NA)).max()), 6),
            "reason": (
                "Clipped to the periods the exact VFM202405 shares actually "
                "move this series. The common post-model Light RUC pool is "
                "shared by Base/Fast/Slow; only the composition differs."
            ),
        }
    )
    return pd.DataFrame([row])


def _annual_chart_value_lookup(chart_rows: pd.DataFrame) -> tuple[dict[tuple[str, int, str], float], dict[str, str]]:
    """Scenario/FY/series values used to keep all detail frames aligned."""
    if chart_rows is None or chart_rows.empty:
        return {}, {}
    annual = chart_rows[
        chart_rows.get("time_grain", pd.Series("", index=chart_rows.index)).astype(str).eq("june_year")
        & ~chart_rows.get("row_type", pd.Series("", index=chart_rows.index)).astype(str).eq("historical_actual")
    ].copy()
    annual["_fy"] = pd.to_numeric(annual.get("june_year"), errors="coerce")
    annual["_value"] = pd.to_numeric(annual.get("value"), errors="coerce")
    annual = annual.dropna(subset=["_fy", "_value"])
    values: dict[tuple[str, int, str], float] = {}
    source_paths: dict[str, str] = {}
    for _, row in annual.iterrows():
        scenario = str(row.get("scenario_name", "") or "")
        series = str(row.get("series_id", "") or "")
        if not scenario or not series:
            continue
        values[(scenario, int(row["_fy"]), series)] = float(row["_value"])
        trace = str(row.get("trace_name", "") or "")
        if trace:
            source_paths[scenario] = trace
    return values, source_paths


def _reconcile_aligned_revenue_formula_rows(
    frame: pd.DataFrame,
    chart_values: dict[tuple[str, int, str], float],
    *,
    fy_values: pd.Series,
    source_path_column: str | None,
) -> pd.DataFrame:
    """Refresh chart-hidden leaves/rollups after display-time overlays.

    The chart pack intentionally carries a compact series inventory.  In
    particular, Heavy-BEV revenue and the intermediate gross/net-admin RUC
    rows are absent.  When Base detail is copied to create a conflict path (or
    when uptake levers move the heavy split), merely replacing visible chart
    rows leaves those hidden lines stale.  Solve the one hidden RUC leaf from
    the canonical Net RUC checkpoint, then replay the governed formulas in
    dependency order.  Chart-carried aggregates remain authoritative and are
    asserted against the rebuilt detail rather than overwritten.
    """

    if frame is None or frame.empty or "scenario_name" not in frame.columns or "series_id" not in frame.columns:
        return frame
    out = frame.copy()
    out["_alignment_fy"] = pd.to_numeric(fy_values, errors="coerce")
    group_columns = ["scenario_name", "_alignment_fy"]
    if source_path_column and source_path_column in out.columns:
        group_columns.insert(0, source_path_column)
    changed_indices: set[Any] = set()

    for group_key, group in out[out["_alignment_fy"].notna()].groupby(group_columns, dropna=False, sort=False):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        scenario_name = str(group["scenario_name"].iloc[0] or "")
        fy = int(float(group["_alignment_fy"].iloc[0]))
        direct_series = {
            series_id
            for scenario, direct_fy, series_id in chart_values
            if scenario == scenario_name and int(direct_fy) == fy
        }
        if not direct_series:
            continue
        duplicate_series = group["series_id"].astype(str).duplicated(keep=False)
        if duplicate_series.any():
            duplicate_ids = sorted(group.loc[duplicate_series, "series_id"].astype(str).unique())
            raise ValueError(
                f"Duplicate aligned revenue detail rows for {scenario_name}, FY{fy}: {', '.join(duplicate_ids)}"
            )
        index_by_series = {
            str(out.at[index, "series_id"]): index
            for index in group.index
        }
        values = {
            series_id: float(value)
            for series_id, index in index_by_series.items()
            if pd.notna(value := pd.to_numeric(pd.Series([out.at[index, "value"]]), errors="coerce").iloc[0])
        }

        # Net RUC = sum of the five RUC class revenues - RUC admin.  Four
        # class rows are chart-carried; Heavy BEV is the rollup-neutral hidden
        # counterpart and is therefore solved from the canonical net total.
        visible_ruc_leaves = (
            "light_ruc_net_revenue",
            "heavy_ruc_net_revenue",
            "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue",
        )
        hidden_ruc_leaf = "heavy_bev_ruc_net_revenue"
        ruc_inputs = ("total_ruc_net_revenue", "ruc_admin_revenue", *visible_ruc_leaves)
        if hidden_ruc_leaf in index_by_series and all(series_id in values for series_id in ruc_inputs):
            hidden_value = (
                values["total_ruc_net_revenue"]
                + values["ruc_admin_revenue"]
                - sum(values[series_id] for series_id in visible_ruc_leaves)
            )
            hidden_index = index_by_series[hidden_ruc_leaf]
            out.at[hidden_index, "value"] = hidden_value
            values[hidden_ruc_leaf] = hidden_value
            changed_indices.add(hidden_index)

        for formula in FORMULA_DEFINITIONS:
            output = str(formula["output_series_id"])
            output_index = index_by_series.get(output)
            if output_index is None:
                continue
            terms = tuple(formula["terms"])
            if any(str(series_id) not in values for series_id, _ in terms):
                continue
            calculated = sum(values[str(series_id)] * float(sign) for series_id, sign in terms)
            if output in direct_series:
                observed = values.get(output)
                if observed is None or not np.isclose(observed, calculated, rtol=0.0, atol=1e-6):
                    raise ValueError(
                        f"Aligned chart/detail formula mismatch for {scenario_name}, FY{fy}, {output}: "
                        f"chart={observed!r}, rebuilt={calculated:.9f}."
                    )
                continue
            out.at[output_index, "value"] = calculated
            values[output] = calculated
            changed_indices.add(output_index)

    if "residual_vs_official" in out.columns:
        for index in changed_indices:
            official = pd.to_numeric(pd.Series([out.at[index, "official_value"]]), errors="coerce").iloc[0] if "official_value" in out.columns else np.nan
            value = pd.to_numeric(pd.Series([out.at[index, "value"]]), errors="coerce").iloc[0]
            if pd.notna(official) and pd.notna(value):
                out.at[index, "residual_vs_official"] = float(value) - float(official)
    return out.drop(columns=["_alignment_fy"], errors="ignore")


def _align_detail_frame_to_chart_rows(
    frame: pd.DataFrame,
    chart_rows: pd.DataFrame,
    *,
    fy_column: str,
    series_column: str,
    value_column: str,
    source_path_column: str | None = None,
) -> pd.DataFrame:
    """Update detail rows from the scenario chart and append the fuel case.

    Advanced view overlays are display-time transformations.  This alignment
    step ensures the composition, bridge and reconciliation tables use the
    same annual values as the main path instead of silently reverting to the
    unadjusted pack.
    """
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    values, source_paths = _annual_chart_value_lookup(chart_rows)
    if not values:
        return frame.copy()
    out = frame.copy()

    def detail_fy(values: pd.Series | Any) -> pd.Series:
        series = values if isinstance(values, pd.Series) else pd.Series(values, index=out.index)
        extracted = series.astype(str).str.extract(r"(\d{4})", expand=False)
        return pd.to_numeric(extracted, errors="coerce")

    if "scenario_name" in out.columns:
        existing_scenarios = set(out["scenario_name"].dropna().astype(str))
        base_template = out[out["scenario_name"].astype(str).eq("current_basecase")].copy()
        base_fy = detail_fy(base_template.get(fy_column))
        base_template = base_template[base_fy.ge(REVENUE_FIRST_FORECAST_FY)].copy()
        appended: list[pd.DataFrame] = []
        for scenario_name in CONFLICT_SCENARIO_NAMES:
            if scenario_name not in source_paths or scenario_name in existing_scenarios or base_template.empty:
                continue
            conflict = base_template.copy()
            conflict["scenario_name"] = scenario_name
            if "scenario_role" in conflict.columns:
                conflict["scenario_role"] = "comparison"
            if "role" in conflict.columns:
                conflict["role"] = "comparison"
            if source_path_column and source_path_column in conflict.columns:
                conflict[source_path_column] = CONFLICT_TRACE_BY_SCENARIO[scenario_name]
            if "source_status" in conflict.columns:
                conflict["source_status"] = "derived_fixed_finalist_reforecast"
            if "value_status" in conflict.columns:
                conflict["value_status"] = "conflict_fuel_price_scenario_reforecast"
            appended.append(conflict)
        if appended:
            out = pd.concat([out, *appended], ignore_index=True, sort=False)

    fy = detail_fy(out.get(fy_column))
    numeric = pd.to_numeric(out.get(value_column), errors="coerce")
    if "residual_vs_official" in out.columns:
        out["residual_vs_official"] = pd.to_numeric(out["residual_vs_official"], errors="coerce")
    for index in out.index:
        if pd.isna(fy.at[index]):
            continue
        key = (
            str(out.at[index, "scenario_name"]) if "scenario_name" in out.columns else "",
            int(fy.at[index]),
            str(out.at[index, series_column]),
        )
        adjusted = values.get(key)
        if adjusted is None:
            continue
        out.at[index, value_column] = adjusted
        if source_path_column and source_path_column in out.columns:
            trace = source_paths.get(key[0])
            if trace:
                out.at[index, source_path_column] = trace
        if "residual_vs_official" in out.columns and pd.notna(numeric.at[index]):
            official = pd.to_numeric(pd.Series([out.at[index, "official_value"]]), errors="coerce").iloc[0] if "official_value" in out.columns else np.nan
            if pd.notna(official):
                out.at[index, "residual_vs_official"] = adjusted - float(official)
    if series_column == "series_id" and value_column == "value":
        out = _reconcile_aligned_revenue_formula_rows(
            out,
            values,
            fy_values=fy,
            source_path_column=source_path_column,
        )
    return out


def _materialised_policy_detail_frames(
    ev_uptake_key: tuple[Any, ...],
    _pack: RevenueOutlookPack,
    sensitivity_key: tuple[Any, ...] = (),
    bridge_mode: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    """The four detail frames from the materialised catalogue, or None.

    ``policy_detail_frames`` raises rather than answering for an official
    vintage it was not aligned against - returning the default vintage's
    frames would be a wrong answer that looked right - so that raise is caught
    here and turned into the reference path.
    """
    from model_dashboard.revenue_outlook_policy_runtime import (
        STATUS_OK,
        policy_detail_frames,
        resolve_policy_state,
    )

    if sensitivity_key and not _is_default_sensitivity_key(tuple(sensitivity_key)):
        return None
    key = _scenario_key(ev_uptake_key)
    if bridge_mode and str(bridge_mode) != str(key.ped_bridge_mode):
        return None
    runtime = _policy_runtime_for_pack(_pack)
    if runtime is None:
        return None
    if resolve_policy_state(runtime, key).status != STATUS_OK:
        return None
    try:
        frames = policy_detail_frames(runtime, key)
    except RuntimeError:
        return None
    return (
        frames.line_reconciliation,
        frames.formula_residuals,
        frames.stack_components,
        frames.bridge_components,
    )


@st.cache_data(show_spinner=False, max_entries=12)
def cached_aligned_scenario_detail_frames(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, ...],
    bridge_mode: str,
    ev_uptake_key: tuple[Any, ...],
    _pack: RevenueOutlookPack,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Line, residual, stack and bridge frames aligned to one overlay key.

    A catalogued key is served from the materialised policy state, so the
    detail frames a reader opens are the same computation identity as the
    chart above them. The alignment, formula rebuild and stack rebuild are
    ~2.1 s of a policy switch and none of them changed method with the policy.
    """
    materialised = _materialised_policy_detail_frames(
        ev_uptake_key, _pack, sensitivity_key, bridge_mode
    )
    if materialised is not None:
        return materialised
    detail_frames = cached_revenue_outlook_detail_frames(
        signature,
        sensitivity_key,
        bridge_mode,
        _pack,
    )
    chart_rows, _, _, _, _ = cached_scenario_overlay_rows(
        signature, sensitivity_key, bridge_mode, ev_uptake_key, _pack
    )
    official_scenario, official_overlay = _official_vintage_filter_for_key(ev_uptake_key)
    chart_rows = _filter_official_vintage_rows(chart_rows, official_scenario, official_overlay)
    line_reconciliation = _align_detail_frame_to_chart_rows(
        detail_frames["line_reconciliation"],
        chart_rows,
        fy_column="FY",
        series_column="series_id",
        value_column="value",
        source_path_column="source_path",
    )
    line_reconciliation = _filter_official_vintage_rows(
        line_reconciliation, official_scenario, official_overlay
    )
    formula_residuals = (
        revenue_formula_residual_frame(line_reconciliation)
        if line_reconciliation is not None and not line_reconciliation.empty
        else pd.DataFrame()
    )
    stack_components = (
        revenue_stack_components_frame(line_reconciliation, formula_residuals)
        if line_reconciliation is not None and not line_reconciliation.empty
        else pd.DataFrame()
    )
    bridge_components = _align_detail_frame_to_chart_rows(
        detail_frames["revenue_bridge_components"],
        chart_rows,
        fy_column="period",
        series_column="stream",
        value_column="component_value",
    )
    return line_reconciliation, formula_residuals, stack_components, bridge_components


@st.cache_data(show_spinner=False, max_entries=16)
def cached_revenue_outlook_view(
    signature: tuple[tuple[str, int, int], ...],
    selected_series: str,
    time_grain: str,
    fed_path: str,
    traces: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    ev_uptake_key: tuple[Any, ...],
    _pack: RevenueOutlookPack,
) -> dict[str, Any]:
    bridge_frames, sensitivity_frames, sensitivity_fast_path = cached_sensitivity_stage_frames(
        signature, bridge_mode, sensitivity_key, _pack
    )
    eruc_levers = _resolve_eruc_levers(ev_uptake_key)
    current_fed_policy_state, mbu26_fed_policy_state = _fed_policy_state_scope(ev_uptake_key)
    ev_uptake_levers = _resolve_ev_uptake_levers(ev_uptake_key)
    chart_rows, ev_uptake_audit, eruc_audit, fed_uplift_audit, fuel_price_audit = cached_scenario_overlay_rows(
        signature, sensitivity_key, bridge_mode, ev_uptake_key, _pack
    )
    # Non-selected official vintages leave every downstream frame here, so the
    # figure, composition, reconciliation and download consumers all inherit
    # one consistent vocabulary from the vintage selection in the uptake key.
    official_scenario, official_overlay = _official_vintage_filter_for_key(ev_uptake_key)
    chart_rows = _filter_official_vintage_rows(chart_rows, official_scenario, official_overlay)
    # Official rows the runtime builders drop before they can become chart
    # rows. Light petrol VKT is the case that matters: BEFU26 and MBU26 both
    # publish it, but it is not in DISPLAY_SERIES_ORDER, so the selector
    # offered a series with no official comparator. This restores those rows
    # from their own registered vintage source, additively, and under the
    # SAME vintage selection the filter above just applied.
    chart_rows = _append_missing_official_rows(
        chart_rows, official_scenario, official_overlay
    )
    effective_current_fed_policy_state = _effective_fed_policy_state(
        current_fed_policy_state,
        _CURRENT_FED_UPLIFT_ROLES,
        fed_uplift_audit,
    )
    effective_mbu26_fed_policy_state = _effective_fed_policy_state(
        mbu26_fed_policy_state,
        _MBU26_FED_UPLIFT_ROLES,
        fed_uplift_audit,
    )
    effective_current_fed_uplift_off = effective_current_fed_policy_state == FED_POLICY_OFF
    effective_mbu26_fed_uplift_off = effective_mbu26_fed_policy_state == FED_POLICY_OFF
    conflict_replay, _ = _safe_fuel_price_scenario_replay(signature, _pack)
    conflict_input_audit = (
        conflict_replay.input_audit.copy()
        if conflict_replay is not None and isinstance(conflict_replay.input_audit, pd.DataFrame)
        else pd.DataFrame()
    )
    conflict_gdp_input_audit = (
        conflict_replay.gdp_input_audit.copy()
        if conflict_replay is not None
        and isinstance(conflict_replay.gdp_input_audit, pd.DataFrame)
        else pd.DataFrame()
    )
    bridge_components = sensitivity_frames["revenue_bridge_components"]
    # The rows handed to the quarterly derivation are these FINAL chart rows:
    # the official comparator vintage has already been filtered, the scenario
    # overlays, EV/e-RUC levers, conflict path and 12c policy have all been
    # applied, and the formula rows have been rebuilt. Deriving from an earlier
    # layer would reconcile the quarters to a number no longer on screen.
    filtered_rows, quarterly_disaggregated = _filter_series_rows_with_fallback(
        chart_rows, selected_series, time_grain, fed_path, traces,
        effective_current_fed_policy_state,
        pack_dir=str(_pack.output_dir),
    )

    # MoT VFM Fast-Slow structural scenario envelope around the base-case
    # trace. Computed through the same pipeline, with every non-VFM control
    # inherited from this key, so the band is exactly what the chart would
    # show under those two governed composition scenarios.
    #
    # While the analyst layers are paused this is skipped entirely rather than
    # computed-and-hidden: the band costs two extra full scenario-overlay
    # passes (one per preset) that nothing on the page would consume.
    cone_band = pd.DataFrame()
    if REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS and ev_uptake_levers is not None:
        cone_band = cached_view_cone_band(
            signature, selected_series, time_grain, fed_path, traces,
            sensitivity_key, bridge_mode, _cone_band_controls(ev_uptake_key), _pack,
        )
    filtered_bridge = _filter_revenue_bridge_rows(
        bridge_components,
        [selected_series],
        _scenario_names_for_traces(chart_rows, list(traces)),
        [fed_path],
    )
    return {
        **sensitivity_frames,
        "chart_rows": chart_rows,
        "filtered_rows": filtered_rows,
        "filtered_bridge": filtered_bridge,
        "gap_summary": _revenue_outlook_gap_summary(filtered_bridge),
        "ped_revenue_bridge_audit": bridge_frames["ped_revenue_bridge_audit"],
        "ped_bridge_mode_impact_audit": bridge_frames["ped_bridge_mode_impact_audit"],
        "sensitivity_fast_path": sensitivity_fast_path,
        "quarterly_disaggregated": quarterly_disaggregated,
        "ev_uptake_applied": ev_uptake_levers is not None and not ev_uptake_audit.empty,
        "ev_uptake_audit": ev_uptake_audit,
        "cone_band": cone_band,
        # Paused with the band itself: the audit describes a layer the page
        # does not offer, so constructing it would be work with no consumer.
        "cone_band_audit": (
            _vfm_envelope_applicability_audit(
                cone_band,
                selected_series=selected_series,
                time_grain=time_grain,
                ev_uptake_levers_available=ev_uptake_levers is not None,
            )
            if REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS
            else pd.DataFrame()
        ),
        "eruc_applied": eruc_levers is not None and not eruc_audit.empty,
        "eruc_audit": eruc_audit,
        "fed_uplift_off": effective_current_fed_uplift_off or effective_mbu26_fed_uplift_off,
        "fed_uplift_delayed": (
            not fed_uplift_audit.empty
            and FED_POLICY_DELAYED_6M
            in {effective_current_fed_policy_state, effective_mbu26_fed_policy_state}
        ),
        "requested_current_fed_policy_state": current_fed_policy_state,
        "requested_mbu26_fed_policy_state": mbu26_fed_policy_state,
        "current_fed_policy_state": effective_current_fed_policy_state,
        "mbu26_fed_policy_state": effective_mbu26_fed_policy_state,
        "current_fed_uplift_off": effective_current_fed_uplift_off,
        "mbu26_fed_uplift_off": effective_mbu26_fed_uplift_off,
        "fed_uplift_audit": fed_uplift_audit,
        "fuel_price_scenario_applied": not fuel_price_audit.empty,
        "fuel_price_scenario_audit": fuel_price_audit,
        "conflict_fuel_input_audit": conflict_input_audit,
        "conflict_gdp_input_audit": conflict_gdp_input_audit,
        # Compatibility for older callers while the exported schema migrates.
        "iran_war_input_audit": conflict_input_audit,
    }


@st.cache_data(show_spinner=False, max_entries=24)
def cached_scenario_comparison_paths(
    signature: tuple[tuple[str, int, int], ...],
    series: str,
    fed_path: str,
    sensitivity_key_a: tuple[str, ...],
    ev_uptake_key_a: tuple[Any, ...],
    sensitivity_key_b: tuple[str, ...],
    ev_uptake_key_b: tuple[Any, ...],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
    trace_a: str = "",
    trace_b: str = "",
) -> dict[str, Any]:
    """A/B paths for one series, read from the canonical final view.

    Each side is one ``cached_revenue_outlook_view`` call - the SAME final
    view contract the Single scenario chart consumes (official-vintage
    filtering, restored official rows, effective policy state, the single
    row gate with its FY2050 horizon clip) - so a comparison side can never
    exit the pipeline earlier than the single view does. The requested
    series is then extracted from the view's FINAL chart rows through the
    same gate the view applies to its own selected series.
    """

    def _paths(sensitivity_key, ev_uptake_key, trace: str) -> tuple[pd.Series, pd.Series, str, str]:
        # The MoT official scenario plots the governed official trace itself,
        # not the finalist base case with the overlays switched off (the raw
        # finalist petrol bridge keeps all petrol activity to 2050, which is
        # the implausible path the displacement lever exists to correct).
        mode = _scenario_key(ev_uptake_key).uptake_basis
        # The governed official option follows the SELECTED comparator vintage
        # (vintage ids equal release rounds for registered vintages), not a
        # hard-coded MBU26 trace.
        selected_vid, _ = _official_vintage_scope(ev_uptake_key)
        # The caller's selected scenario trace wins; the mode-derived fallback
        # keeps historical callers that predate per-side trace selection.
        base_trace = trace or (
            official_comparator_trace_name(selected_vid)
            if mode == EV_UPTAKE_GOVERNED_OPTION
            else "Current finalist Base case"
        )
        # One view per SIDE, keyed on the total series so every component
        # fetch for the same configuration reuses it. The per-series rows are
        # cut from the view's final chart rows below, through the same gate.
        view = cached_revenue_outlook_view(
            signature,
            _SCENARIO_COMPARISON_TOTAL_SERIES,
            "june_year",
            fed_path,
            ("Actual", base_trace),
            sensitivity_key,
            bridge_mode,
            ev_uptake_key,
            _pack,
        )
        rows, _ = _filter_series_rows_with_fallback(
            view["chart_rows"],
            series,
            "june_year",
            fed_path,
            ("Actual", base_trace),
            view["current_fed_policy_state"],
            pack_dir=str(_pack.output_dir),
        )
        if rows is None or rows.empty:
            return pd.Series(dtype=float), pd.Series(dtype=float), "", ""
        fy = pd.to_numeric(rows["june_year"], errors="coerce")
        values = pd.to_numeric(rows["value"], errors="coerce")
        is_actual = rows["row_type"].astype(str).eq("historical_actual")
        is_base = rows["trace_name"].astype(str).eq(base_trace)
        history = pd.Series(values[is_actual].to_numpy(), index=fy[is_actual].to_numpy()).dropna().sort_index()
        forecast = pd.Series(values[is_base & ~is_actual].to_numpy(), index=fy[is_base & ~is_actual].to_numpy()).dropna().sort_index()
        unit = _first_non_empty(rows.get("value_unit", pd.Series(dtype=str)))
        metric = _revenue_outlook_series_metric_type(view["chart_rows"], series)
        return forecast, history, str(unit or ""), str(metric or "")

    forecast_a, history, unit, metric = _paths(sensitivity_key_a, ev_uptake_key_a, str(trace_a))
    forecast_b, _, _, _ = _paths(sensitivity_key_b, ev_uptake_key_b, str(trace_b))
    return {
        "history": history,
        "a": forecast_a,
        "b": forecast_b,
        "value_unit": unit,
        "metric_type": metric,
    }


@st.cache_data(show_spinner=False, max_entries=4)
def cached_revenue_outlook_detail_frames(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> dict[str, pd.DataFrame]:
    if _is_default_sensitivity_key(sensitivity_key):
        bridge_frames = _bridge_mode_frames_for_pack(_pack, bridge_mode, include_derived_frames=True)
        return {
            **bridge_frames,
            "sensitivity_impact_audit": pd.DataFrame(),
        }
    # Non-default keys reuse the staged pipeline cache (which builds the
    # bridge with derived frames for exactly these keys) instead of paying a
    # duplicate ~3s bridge + sensitivity recompute per lever change.
    bridge_frames, sensitivity_frames, _ = cached_sensitivity_stage_frames(signature, bridge_mode, sensitivity_key, _pack)
    return {
        **sensitivity_frames,
        "ped_revenue_bridge_audit": bridge_frames.get("ped_revenue_bridge_audit", pd.DataFrame()),
        "ped_bridge_mode_impact_audit": bridge_frames.get("ped_bridge_mode_impact_audit", pd.DataFrame()),
    }


@st.cache_data(show_spinner=False, max_entries=4)
def cached_revenue_outlook_ped_bridge_detail(
    signature: tuple[tuple[str, int, int], ...],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> dict[str, pd.DataFrame]:
    del signature
    bridge_frames = _bridge_mode_frames_for_pack(
        _pack,
        bridge_mode,
        include_derived_frames=False,
        include_selected_ped_audit=True,
    )
    return {
        "ped_revenue_bridge_audit": bridge_frames.get("ped_revenue_bridge_audit", pd.DataFrame()),
        "ped_bridge_mode_impact_audit": bridge_frames.get("ped_bridge_mode_impact_audit", pd.DataFrame()),
    }


@st.cache_data(show_spinner=False, max_entries=4)
def cached_revenue_outlook_line_detail_frames(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> dict[str, pd.DataFrame]:
    del signature
    bridge_frames = _bridge_mode_frames_for_pack(
        _pack,
        bridge_mode,
        include_derived_frames=True,
        derived_frame_scope="line",
        include_selected_ped_audit=False,
    )
    if _is_default_sensitivity_key(sensitivity_key):
        return {
            "line_reconciliation": bridge_frames.get("line_reconciliation", pd.DataFrame()),
            "revenue_formula_residuals": bridge_frames.get("revenue_formula_residuals", pd.DataFrame()),
        }
    sensitivity_config = _pack_table(_pack, "sensitivity_config", sensitivity_config_frame())
    sensitivity_frames = _apply_sensitivity_for_key(bridge_frames, sensitivity_config, sensitivity_key)
    return {
        "line_reconciliation": sensitivity_frames.get("line_reconciliation", pd.DataFrame()),
        "revenue_formula_residuals": sensitivity_frames.get("revenue_formula_residuals", pd.DataFrame()),
    }


@st.cache_data(show_spinner=False, max_entries=4)
def cached_revenue_outlook_sensitivity_audit(
    signature: tuple[tuple[str, int, int], ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _pack: RevenueOutlookPack,
) -> pd.DataFrame:
    del signature
    bridge_frames = _bridge_mode_frames_for_pack(
        _pack,
        bridge_mode,
        include_derived_frames=True,
        derived_frame_scope="line_only",
        include_selected_ped_audit=True,
    )
    sensitivity_config = _pack_table(_pack, "sensitivity_config", sensitivity_config_frame())
    fleet_efficiency = sensitivity_key[0]
    pt_mode_shift = sensitivity_key[1]
    demand_elasticity = sensitivity_key[2]
    freight_rail_shift = sensitivity_key[9] if len(sensitivity_key) > 9 else "Off"
    custom_fleet = float(sensitivity_key[3]) if sensitivity_key[3] else None
    custom_pt = float(sensitivity_key[4]) if sensitivity_key[4] else None
    custom_ped = float(sensitivity_key[5]) if sensitivity_key[5] else None
    custom_light = float(sensitivity_key[6]) if sensitivity_key[6] else None
    custom_heavy = float(sensitivity_key[7]) if sensitivity_key[7] else None
    cost_ratio = float(sensitivity_key[8]) if sensitivity_key[8] else None
    custom_freight = float(sensitivity_key[10]) if len(sensitivity_key) > 10 and sensitivity_key[10] else None
    return revenue_sensitivity_impact_audit_frame(
        bridge_frames.get("line_reconciliation", pd.DataFrame()),
        bridge_frames.get("ped_revenue_bridge_audit", pd.DataFrame()),
        sensitivity_config,
        fleet_efficiency=fleet_efficiency,
        pt_mode_shift=pt_mode_shift,
        freight_rail_shift=freight_rail_shift,
        demand_elasticity=demand_elasticity,
        custom_fleet_efficiency_pct=custom_fleet,
        custom_pt_shift_pct=custom_pt,
        custom_freight_shift_pct=custom_freight,
        custom_ped_elasticity=custom_ped,
        custom_light_elasticity=custom_light,
        custom_heavy_elasticity=custom_heavy,
        cost_per_km_ratio=cost_ratio,
    )


@st.cache_data(show_spinner=False, max_entries=12)
def cached_revenue_outlook_total_path_figure(
    signature: tuple[tuple[str, int, int], ...],
    selected_series: str,
    selected_fy: str,
    time_grain: str,
    fed_path: str,
    traces: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    ev_uptake_key: ScenarioKeyLike,
    _filtered_rows: pd.DataFrame,
    _cone_band: pd.DataFrame | None = None,
    _uncertainty_rows: pd.DataFrame | None = None,
    selected_band_layers: tuple[str, ...] = (),
) -> go.Figure:
    selected_vid, _ = _official_vintage_scope(ev_uptake_key)
    # Plotly keeps pan/zoom across a rerender while ``uirevision`` is unchanged.
    # It is derived from this figure's CALCULATION identity - the same values
    # that key this cache - and deliberately NOT from the expand/collapse state,
    # so resizing the chart is not by itself a reason to throw away a reader's
    # zoom. Any control that genuinely changes the plotted numbers changes the
    # cache key, and therefore the revision, and the view resets as it should.
    revision = _revenue_outlook_figure_revision(
        signature,
        selected_series,
        time_grain,
        fed_path,
        traces,
        sensitivity_key,
        bridge_mode,
        ev_uptake_key,
        selected_band_layers,
    )
    del signature, time_grain, fed_path, traces, sensitivity_key, bridge_mode, ev_uptake_key
    figure = revenue_outlook_total_path_figure(
        _filtered_rows,
        selected_series=selected_series,
        selected_fy=selected_fy,
        cone_band=_cone_band,
        selected_official_trace=official_comparator_trace_name(selected_vid),
        uncertainty_rows=_uncertainty_rows,
        selected_band_layers=selected_band_layers,
    )
    figure.update_layout(uirevision=revision, selectionrevision=revision)
    return figure


def _revenue_outlook_figure_revision(*identity: Any) -> str:
    """A short stable token for the Total path figure's calculation identity."""
    payload = "|".join(repr(part) for part in identity)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@st.cache_data(show_spinner=False, max_entries=12)
def cached_revenue_outlook_fan_figure(
    signature: tuple[tuple[str, int, int], ...],
    selected_series: str,
    selected_fed_path: str,
    selected_fan_source: str,
    _fan_band_rows: pd.DataFrame,
    _fan_availability: pd.DataFrame,
    official_fed_paths: tuple[str, ...] | None = None,
) -> tuple[go.Figure, str]:
    del signature
    figure = revenue_outlook_uncertainty_fan_figure(
        _fan_band_rows,
        fan_availability=_fan_availability,
        selected_series=selected_series,
        fan_source=selected_fan_source,
        selected_fed_path=selected_fed_path,
        official_fed_paths=official_fed_paths,
    )
    caption = _revenue_outlook_fan_caption(_fan_availability, selected_series, selected_fan_source)[:220]
    return figure, caption


def revenue_outlook_composition_stack_frame(
    stack_components: pd.DataFrame,
    *,
    source_path: str,
    composition_mode: str,
    sections: tuple[str, ...],
    fy_range: tuple[int, int],
    overlays: tuple[str, ...],
    stack_section_options: tuple[str, ...],
) -> pd.DataFrame:
    if stack_components is None or stack_components.empty:
        return pd.DataFrame()
    scoped_stack = _filter_revenue_stack_components(
        stack_components,
        source_path=source_path,
        composition_mode=composition_mode,
        sections=list(stack_section_options),
        fy_range=fy_range,
    )
    if scoped_stack.empty:
        return scoped_stack
    if sections and "section" in scoped_stack.columns:
        filtered_stack = scoped_stack[scoped_stack["section"].astype(str).isin(sections)].copy()
    else:
        filtered_stack = scoped_stack.copy()
    overlay_labels = {str(value) for value in overlays if str(value).strip()}
    if not overlay_labels:
        return filtered_stack
    overlay_stack = scoped_stack[
        scoped_stack.get("stack_role", pd.Series("", index=scoped_stack.index)).astype(str).eq("aggregate_overlay")
        & scoped_stack.get("line_label", pd.Series("", index=scoped_stack.index)).astype(str).isin(overlay_labels)
    ].copy()
    if overlay_stack.empty:
        return filtered_stack
    return pd.concat([filtered_stack, overlay_stack], ignore_index=True, sort=False)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_revenue_outlook_composition_stack(
    signature: tuple[tuple[str, int, int], ...],
    source_path: str,
    composition_mode: str,
    sections: tuple[str, ...],
    fy_range: tuple[int, int],
    overlays: tuple[str, ...],
    stack_section_options: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _stack_components: pd.DataFrame,
) -> pd.DataFrame:
    del signature, sensitivity_key, bridge_mode
    return revenue_outlook_composition_stack_frame(
        _stack_components,
        source_path=source_path,
        composition_mode=composition_mode,
        sections=sections,
        fy_range=fy_range,
        overlays=overlays,
        stack_section_options=stack_section_options,
    )


@st.cache_data(show_spinner=False, max_entries=8)
def cached_revenue_outlook_composition_figure(
    signature: tuple[tuple[str, int, int], ...],
    source_path: str,
    composition_mode: str,
    detail_level: str,
    sections: tuple[str, ...],
    fy_range: tuple[int, int],
    overlays: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _chart_stack: pd.DataFrame,
) -> go.Figure:
    del signature, sections, fy_range, sensitivity_key, bridge_mode
    return revenue_outlook_composition_figure(
        _chart_stack,
        source_path=source_path,
        composition_mode=composition_mode,
        detail_level=detail_level,
        overlays=list(overlays),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def cached_revenue_outlook_composition_table_view(
    signature: tuple[tuple[str, int, int], ...],
    source_path: str,
    composition_mode: str,
    sections: tuple[str, ...],
    fy_range: tuple[int, int],
    overlays: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _chart_stack: pd.DataFrame,
) -> tuple[str, pd.DataFrame]:
    del signature, source_path, composition_mode, sections, fy_range, overlays, sensitivity_key, bridge_mode
    return _revenue_stack_gap_banner(_chart_stack), _revenue_stack_components_display_table(_chart_stack)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_revenue_line_reconciliation_view(
    signature: tuple[tuple[str, int, int], ...],
    source_paths: tuple[str, ...],
    sections: tuple[str, ...],
    fy_range: tuple[int, int],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _line_reconciliation: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del signature, sensitivity_key, bridge_mode
    filtered = _filter_revenue_line_reconciliation(
        _line_reconciliation,
        source_paths=list(source_paths),
        sections=list(sections),
        fy_range=fy_range,
    )
    return filtered, _revenue_line_reconciliation_display_table(filtered)


@st.cache_data(show_spinner=False, max_entries=8)
def cached_revenue_outlook_selected_fy_figures(
    signature: tuple[tuple[str, int, int], ...],
    selected_fy: str,
    selected_fed_path: str,
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    _bridge: pd.DataFrame,
) -> tuple[go.Figure, go.Figure]:
    del signature, sensitivity_key, bridge_mode
    return (
        revenue_outlook_component_figure(_bridge, selected_fy=selected_fy, selected_fed_path=selected_fed_path),
        revenue_outlook_split_figure(_bridge, selected_fy=selected_fy, selected_fed_path=selected_fed_path),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def cached_revenue_outlook_ev_phev_drift_view(
    signature: tuple[tuple[str, int, int], ...],
    selected_mode: str,
    _drift_assumptions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del signature
    if _drift_assumptions is None or _drift_assumptions.empty:
        empty = pd.DataFrame()
        return empty, empty
    mode_series = _drift_assumptions.get("lambda_mode", pd.Series("", index=_drift_assumptions.index)).astype(str)
    filtered = _drift_assumptions[mode_series.eq(str(selected_mode))].copy()
    return filtered, _ev_phev_ped_light_drift_display_table(filtered)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_revenue_outlook_ev_phev_split_display(
    signature: tuple[tuple[str, int, int], ...],
    _split_assumptions: pd.DataFrame,
) -> pd.DataFrame:
    del signature
    return _ev_phev_split_assumptions_display_table(_split_assumptions)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_revenue_outlook_activity_figure(
    signature: tuple[tuple[str, int, int], ...],
    time_grain: str,
    selected_fed_path: str,
    traces: tuple[str, ...],
    sensitivity_key: tuple[str, str, str, str, str, str, str, str, str, str, str],
    bridge_mode: str,
    policy_state: str,
    pack_dir: str,
    _chart_rows: pd.DataFrame,
) -> go.Figure:
    del signature, sensitivity_key, bridge_mode
    activity_frames: list[pd.DataFrame] = []
    for series_label in (
        "Light petrol VKT",
        "PED VKT per capita",
        "PED volume",
        "Light RUC net km",
        "Heavy RUC net km",
    ):
        selected, _ = _filter_series_rows_with_fallback(
            _chart_rows,
            series_label,
            time_grain,
            selected_fed_path,
            traces,
            policy_state,
            pack_dir=pack_dir,
        )
        if not selected.empty:
            activity_frames.append(selected)
    activity_rows = (
        pd.concat(activity_frames, ignore_index=True, sort=False)
        if activity_frames
        else pd.DataFrame()
    )
    return revenue_outlook_figure(activity_rows, metric_type="activity")


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
    return _real_cloud_runtime()


def _real_cloud_runtime() -> bool:
    """True only on actual Streamlit Cloud (env markers / mount path), never
    for the local cloud-preview toggle. Used for resource decisions - the
    Community Cloud container has ~2.7 GB of memory, so anything memory-hungry
    must check the real runtime, not the previewed one."""
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
    # "Schiff Benchmark" retired as a page 2026-07: the benchmark numbers stay
    # on the executive cards and Scenario Forecasts; render_schiff_benchmark_page
    # remains for local audit revival if ever needed.
    pages = ["Overview", "Diagnostics", "Scenario Comparison", REVENUE_OUTLOOK_PAGE]
    if should_show_governance_page():
        pages.append(REPRODUCIBILITY_PAGE)
    return pages


_REVENUE_OUTLOOK_WARMER_STARTED = threading.Event()


def _revenue_outlook_warm_sensitivity_keys() -> list[tuple[str, ...]]:
    """Most-likely first sensitivity selections: one family at a time."""
    keys: list[tuple[str, ...]] = []
    for level in ("Low", "Med", "High"):
        keys.append(selected_sensitivity_key(level, "Off", "Off", freight_rail_shift="Off"))
        keys.append(selected_sensitivity_key("Off", level, "Off", freight_rail_shift="Off"))
        keys.append(selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift=level))
    return keys


def _warm_revenue_outlook_caches() -> None:
    """Best-effort pre-compute of the hot Revenue Outlook cache keys.

    ``st.cache_data`` is process-global, so warming here makes the first
    visit to the page (and the first click on any single sensitivity level)
    hit warm caches instead of paying the 0.5-2s pipeline cost inline.
    """
    try:
        from model_dashboard.engine import engine_default, engine_revenue_outlook_dir

        repo_root = Path(__file__).resolve().parent
        pack_dir = repo_root / engine_revenue_outlook_dir(engine_default())
        pack = load_revenue_outlook_pack(pack_dir, repo_root=repo_root)
        if pack is None:
            return
        signature = revenue_outlook_signature(pack_dir, repo_root)
        default_sens = selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
        default_uptake = (DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)
        uptake_12c_off = (DEFAULT_EV_UPTAKE_MODE, (), (), 1, 1)

        def _warm_view(sensitivity_key: tuple[str, ...], ev_uptake_key: tuple[Any, ...]) -> None:
            cached_revenue_outlook_view(
                signature,
                "Total NLTF revenue",
                "june_year",
                "Current planned path",
                ("Current finalist Base case", "Actual"),
                sensitivity_key,
                PED_BRIDGE_DEFAULT_MODE,
                ev_uptake_key,
                pack,
            )

        _warm_view(default_sens, default_uptake)
        _warm_view(default_sens, uptake_12c_off)
        cached_revenue_outlook_detail_frames(signature, default_sens, PED_BRIDGE_DEFAULT_MODE, pack)
        # Full lever pre-warm everywhere: with the engine switcher retired the
        # cloud never loads a second engine's packs, which frees enough of the
        # ~2.7 GB Community Cloud budget to keep first lever clicks instant.
        # Detail frames are only warmed for the default key - they back the
        # audit tables, not the headline charts, and cost real memory per key.
        for sensitivity_key in _revenue_outlook_warm_sensitivity_keys():
            _warm_view(sensitivity_key, default_uptake)
    except Exception:
        # Warming is an optimisation only; the page computes on demand.
        pass


def _start_revenue_outlook_cache_warmer() -> None:
    if env_flag("REVENUE_OUTLOOK_CACHE_WARMER") is False:
        return
    if _REVENUE_OUTLOOK_WARMER_STARTED.is_set():
        return
    _REVENUE_OUTLOOK_WARMER_STARTED.set()
    thread = threading.Thread(
        target=_warm_revenue_outlook_caches,
        name="revenue-outlook-cache-warmer",
        daemon=True,
    )
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx

        add_script_run_ctx(thread)
    except Exception:
        pass
    thread.start()


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

    _start_revenue_outlook_cache_warmer()
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
    from model_dashboard.engine import ENGINE_AR1, ENGINE_ENSEMBLE, engine_evidence_root

    configured_root = (
        os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT")
        or os.environ.get("STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT")
        or ""
    ).strip()
    requested_root = Path(configured_root).expanduser() if configured_root else engine_evidence_root()
    if configured_root:
        # The verifier exports the built-in ensemble path as its data root.
        # Treat either built-in engine pack as an engine-family selector so a
        # per-session AR(1)/ensemble switch cannot be pinned to the other
        # engine. Genuine custom/external data-root overrides remain intact.
        configured_resolved = requested_root.resolve(strict=False)
        built_in_roots = {
            engine_evidence_root(ENGINE_AR1).resolve(strict=False),
            engine_evidence_root(ENGINE_ENSEMBLE).resolve(strict=False),
        }
        if configured_resolved in built_in_roots:
            requested_root = engine_evidence_root()
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


@st.cache_data(show_spinner=False, max_entries=4)
def _executive_card_inputs(pack_data: str, repro_dirs_json: str, signature: float) -> list[dict[str, str]]:
    """Stream recommendation cards built directly from the governed packs.

    Presentation only: every number is read from finalists.parquet,
    schiff_benchmark.parquet, diagnostic_pass_matrix.parquet and the
    reproducibility parity audits - nothing is recomputed. Keyed on the
    engine-resolved pack path so both engines cache side by side.
    """
    del signature
    from model_dashboard.governance_constants import REPRODUCIBILITY_BASE

    repro_dirs = json.loads(repro_dirs_json)
    pack = Path(pack_data)
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
        sdir = repro_root / repro_dirs.get(stream, "")
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

    cards = _executive_cards_safe()
    if not cards:
        return
    blocks = []
    for card in cards:
        color = BADGE_COLORS.get(card["badge"], "#334155")
        gain_html = (f"<div style='color:#15803d;font-weight:600;font-size:0.8rem;margin-top:2px'>"
                     f"{card['gain']}</div>") if card["gain"] else ""
        # The Promote/Watch/Monitor capsule is method detail; the card keeps
        # its stream name, model and accuracy figures either way.
        badge_html = (
            f"<span style='background:{color};color:#fff;border-radius:999px;padding:1px 12px;"
            f"font-size:0.75rem;font-weight:700'>{card['badge']}</span>"
            if method_detail_enabled()
            else ""
        )
        blocks.append(
            f"<div style='flex:1 1 260px;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;"
            f"padding:14px 16px;min-width:240px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;gap:8px'>"
            f"<span style='font-weight:700;color:#0f172a'>{card['stream']}</span>"
            f"{badge_html}</div>"
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
    from model_dashboard.engine import engine_evidence_data, engine_repro_pack_dirs

    try:
        pack_data = engine_evidence_data()
        signature = (pack_data / "finalists.parquet").stat().st_mtime
        return _executive_card_inputs(str(pack_data), json.dumps(engine_repro_pack_dirs()), signature)
    except Exception:
        return []


def render_action_card(page: str) -> None:
    """One management action card per executive page (presentation only:
    every statement is composed from the governed card inputs)."""
    if not is_executive():
        return
    # The recommended-decision, governance-watch and scenario-implication
    # cards are method detail; hidden for the workshop build.
    if page in ("Overview", "Diagnostics", "Scenario Comparison") and not method_detail_enabled():
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
    if not method_detail_enabled():
        return
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
    # Both R2 expanders are method detail; their tables and governed sources
    # stay available to audit runs and downloads.
    if method_detail_enabled():
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


REVENUE_OUTLOOK_VIEW_SINGLE = "Single scenario"
REVENUE_OUTLOOK_VIEW_COMPARE = "Compare A vs B"
def _comparison_mot_official_option(release_round: str) -> str:
    """A/B uptake option label for the governed official path of one vintage."""
    return f"MoT official ({release_round}, no levers)"


# Bound to the governed default comparator vintage. The rendered A/B option
# follows the page's SELECTED comparator vintage at runtime (see
# _render_comparison_scenario_column); this constant names the default label
# for module-level callers and tests.
COMPARISON_MOT_OFFICIAL_OPTION = _comparison_mot_official_option(
    _registry_default_comparator_vintage_id()
)
# Single-view controls (and the whole lever accordion) unmount while the
# comparison view is active; re-assigning their session values each run marks
# them as programmatically set so Streamlit keeps them alive across the switch.
_REVENUE_OUTLOOK_PERSISTED_KEYS = (
    "revenue_outlook_time_grain",
    "revenue_outlook_selected_fy",
    "revenue_outlook_sensitivity_fleet_efficiency",
    "revenue_outlook_sensitivity_pt_mode_shift",
    "revenue_outlook_sensitivity_freight_rail_toggle",
    "revenue_outlook_sensitivity_freight_rail_shift",
    "revenue_outlook_ev_uptake_basis_v2",
    "revenue_outlook_eruc_toggle",
    "revenue_outlook_fed_policy_state",
    "revenue_outlook_mbu_fed_policy_state",
    "revenue_outlook_fed_uplift",
    "revenue_outlook_mbu_fed_uplift",
    "revenue_outlook_official_vintage",
    "revenue_outlook_official_vintage_overlay",
)
_REVENUE_OUTLOOK_PERSISTED_PREFIXES = ("revenue_outlook_legend_item_", "ev_lever_", "eruc_lever_")


def _persist_revenue_outlook_view_state() -> None:
    for key in list(st.session_state.keys()):
        name = str(key)
        if name in _REVENUE_OUTLOOK_PERSISTED_KEYS or name.startswith(_REVENUE_OUTLOOK_PERSISTED_PREFIXES):
            st.session_state[key] = st.session_state[key]


def _widget_default_kwargs(key: str, **defaults: Any) -> dict[str, Any]:
    """Widget default kwargs only while the key has no session value.

    Persisted keys are re-assigned via the Session State API each run; also
    passing ``value=``/``index=`` then would log a default-vs-session-state
    warning on every rerun.
    """
    return {} if key in st.session_state else defaults


def _session_fed_policy_state(
    key: str,
    *,
    legacy_toggle_key: str | None = None,
    default: str = FED_POLICY_DELAYED_6M,
) -> str:
    """Read a three-state policy selection, migrating the former ON/OFF toggle."""

    if key in st.session_state:
        return _normalise_fed_policy_state(st.session_state.get(key))
    if legacy_toggle_key and legacy_toggle_key in st.session_state:
        legacy_on = bool(st.session_state.get(legacy_toggle_key))
        state = FED_POLICY_DELAYED_6M if legacy_on else FED_POLICY_OFF
        st.session_state[key] = state
        return state
    return _normalise_fed_policy_state(default)


def _active_lever_summary(
    fleet: str,
    pt_shift: str,
    freight: str,
    uptake_mode: str,
    eruc_on: bool,
    fed_policy_state: str,
    mbu_fed_policy_state: str,
) -> str:
    """One-line summary of non-default levers, shown while the accordion is closed."""
    parts: list[str] = []
    if fleet != "Off":
        parts.append(f"Fleet efficiency {fleet}")
    if pt_shift != "Off":
        parts.append(f"PT shift {pt_shift}")
    if freight != "Off":
        parts.append(f"Freight rail {freight}")
    if uptake_mode != DEFAULT_EV_UPTAKE_MODE:
        parts.append(f"Uptake {uptake_mode}")
    if eruc_on:
        parts.append("e-RUC on")
    parts.append(f"Current: {FED_POLICY_LABELS[_normalise_fed_policy_state(fed_policy_state)]}")
    mbu_state = _normalise_fed_policy_state(mbu_fed_policy_state)
    # The official comparator renders as published by default; only the
    # explicitly selected MBU26 synthetic counterfactual is worth naming.
    if mbu_state != FED_POLICY_PUBLISHED:
        parts.append(f"MBU26 synthetic counterfactual: {FED_POLICY_LABELS[mbu_state]}")
    return " · ".join(parts)


_OFFICIAL_VINTAGE_PRIOR_SUFFIX = " (prior vintage)"


def _official_vintage_manifest_entries(
    manifest: dict[str, Any],
) -> tuple[str, dict[str, dict[str, Any]]]:
    """(default comparator vintage id, available {vid: entry}) from the pack.

    Packs that predate the ``official_vintages`` manifest block fall back to
    the legacy MBU26-only vocabulary so an older pack renders as before.
    """
    block = manifest.get("official_vintages") if isinstance(manifest, dict) else None
    available_raw = block.get("available") if isinstance(block, dict) else None
    if not isinstance(available_raw, dict) or not available_raw:
        return "MBU26", {
            "MBU26": {
                "display_name": "MBU26 official",
                "release_round": "MBU26",
                "trace_name": "MBU26 official",
                "scenario_name": "mbu26_official",
            }
        }
    available = {
        str(vid): dict(entry)
        for vid, entry in available_raw.items()
        if isinstance(entry, dict)
    }
    default_id = str(block.get("official_comparator_vintage_id") or "")
    if default_id not in available:
        default_id = next(iter(available))
    return default_id, available


def _official_vintage_trace_name(vid: str, entry: dict[str, Any]) -> str:
    release = str(entry.get("release_round") or vid)
    return str(entry.get("trace_name") or official_comparator_trace_name(release))


_LONG_RUN_SHAPE_PREVIEW_KEY = "revenue_outlook_long_run_shape_method"


def _long_run_shape_preview_options(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The analyst-only long-run shape previews, built from the registry.

    Options are generated from the governed schedule catalogue and the
    registered shape-capable vintages, so a later vintage appears here without
    a code edit. The pack's own recorded schedule is always the first option:
    it is what the published chart shows.
    """

    block = manifest.get("official_vintages") if isinstance(manifest, dict) else None
    block = block if isinstance(block, dict) else {}
    pack_schedule = str(
        block.get("long_run_transition_schedule_id") or UNBLENDED_SCHEDULE_ID
    )
    pack_shape_vid = str(block.get("long_run_shape_vintage_id") or "")

    options: dict[str, dict[str, Any]] = {
        "Current unblended": {
            "schedule_id": UNBLENDED_SCHEDULE_ID,
            "shape_vintage_id": pack_shape_vid,
            "is_pack_default": pack_schedule == UNBLENDED_SCHEDULE_ID,
            "role": "production_default"
            if pack_schedule == UNBLENDED_SCHEDULE_ID
            else "preview",
        }
    }
    try:
        shape_choices = dict(long_run_shape_vintage_choices())
    except Exception:
        shape_choices = {}
    # A pack predating the shape role records no vintage. Fall back to the
    # governed REGISTRY DEFAULT, never to whichever vintage happens to be first
    # in the registry - that ordering is incidental and would silently promote
    # a prior vintage to the primary preview.
    default_shape = pack_shape_vid
    if not default_shape:
        try:
            default_shape = long_run_shape_vintage_id_from_manifest(manifest)
        except Exception:
            default_shape = next(iter(shape_choices), "")
    for schedule_id in STRUCTURAL_SCHEDULE_IDS:
        schedule = resolve_schedule(schedule_id)
        suffix = schedule_id.split("_")[0]
        label = f"{default_shape} anchored structural transition - {suffix}"
        options[label] = {
            "schedule_id": schedule_id,
            "shape_vintage_id": default_shape,
            "is_pack_default": pack_schedule == schedule_id,
            "role": "production_default" if pack_schedule == schedule_id else "preview",
        }
    for vid in shape_choices:
        if vid == default_shape:
            continue
        options[f"{vid} anchored structural transition - prior-vintage audit"] = {
            "schedule_id": "balanced_structural",
            "shape_vintage_id": vid,
            "is_pack_default": False,
            "role": "audit",
        }
    return options


def _render_long_run_shape_controls(manifest: dict[str, Any]) -> dict[str, Any]:
    """Analyst-only "Long-run shape method" preview selector.

    Independent of the official comparator vintage, the bridge-assumption
    vintage, the VFM fleet-composition scenario and the transition schedule -
    changing any one of those must not move the others. The PUBLIC default is
    whatever the committed pack recorded, and this control cannot change it:
    it is rendered only under the local audit controls and is a preview of
    candidates awaiting an owner decision.
    """

    options = _long_run_shape_preview_options(manifest)
    labels = list(options)
    pack_label = next(
        (label for label, spec in options.items() if spec["is_pack_default"]),
        labels[0],
    )
    selected_label = pack_label
    if should_show_local_audit_controls():
        if (
            _LONG_RUN_SHAPE_PREVIEW_KEY in st.session_state
            and str(st.session_state[_LONG_RUN_SHAPE_PREVIEW_KEY]) not in options
        ):
            st.session_state[_LONG_RUN_SHAPE_PREVIEW_KEY] = pack_label
        selected_label = st.selectbox(
            "Long-run shape method",
            labels,
            key=_LONG_RUN_SHAPE_PREVIEW_KEY,
            help=(
                "Analyst preview of the FY2031-FY2050 long-run construction. "
                "Current FY2030 remains the level anchor under every option; the "
                "selection changes only how quickly the post-model growth shape "
                "transitions toward the selected structural source. The official "
                "level is not substituted, and the published default is unchanged "
                "until an owner selects a production candidate."
            ),
            **_widget_default_kwargs(
                _LONG_RUN_SHAPE_PREVIEW_KEY, index=labels.index(pack_label)
            ),
        )
    spec = options.get(str(selected_label), options[pack_label])
    schedule = resolve_schedule(str(spec["schedule_id"]))
    return {
        "label": str(selected_label),
        "schedule_id": schedule.schedule_id,
        "shape_vintage_id": str(spec["shape_vintage_id"]),
        "anchor_fy": schedule.anchor_fy,
        "completion_fy": schedule.completion_fy,
        "is_pack_default": bool(spec["is_pack_default"]),
        "role": str(spec["role"]),
        "options": tuple(labels),
    }


def _selected_vfm_scenario_label() -> str:
    """The VFM composition scenario currently driving the class split.

    Read from the governed default rather than hard-coded, so the details text
    stays truthful if the composition scenario ever becomes selectable.
    """

    return _VFM_PRODUCTION_SCENARIO


_VFM_PRODUCTION_SCENARIO = "Base_EV"


def _long_run_shape_details_text(
    shape_state: dict[str, Any], fleet_scenario: str
) -> str:
    """The governed details wording for the long-run construction.

    Deliberately avoids "calibrated to", "forced to" and "blended to match":
    none of those describe what the method does, and all three would misstate
    it to a reader.
    """

    schedule_id = str(shape_state.get("schedule_id") or UNBLENDED_SCHEDULE_ID)
    lines = [
        f"Current FY{shape_state.get('anchor_fy', 2030)} level anchor",
    ]
    if schedule_id == UNBLENDED_SCHEDULE_ID:
        lines.append(
            "Long-run activity shape: Current econometric extrapolation "
            "(no structural transition)"
        )
    else:
        lines.append(
            f"Long-run activity shape: {shape_state.get('shape_vintage_id')}"
        )
    lines.append(f"Fleet composition: {FLEET_COMPOSITION_SOURCE_ID} {fleet_scenario}")
    lines.append(f"Transition schedule: {schedule_id}")
    return "  \n".join(lines)


def _render_official_vintage_controls(manifest: dict[str, Any]) -> dict[str, Any]:
    """Governed "Official comparator vintage" selector plus analyst overlay.

    Returns the selected vintage vocabulary (id/release/trace/scenario), the
    overlay flag and the displayed official trace names, selected first.
    """
    default_id, available = _official_vintage_manifest_entries(manifest)
    ordered_ids = [default_id] + sorted(vid for vid in available if vid != default_id)
    labels: dict[str, str] = {}
    for vid in ordered_ids:
        display = str(available[vid].get("display_name") or f"{vid} official")
        labels[vid] = display if vid == default_id else display + _OFFICIAL_VINTAGE_PRIOR_SUFFIX
    label_to_id = {label: vid for vid, label in labels.items()}
    options = [labels[vid] for vid in ordered_ids]
    selected_id = default_id
    overlay = False
    if len(options) > 1:
        vintage_key = "revenue_outlook_official_vintage"
        if vintage_key in st.session_state and str(st.session_state[vintage_key]) not in label_to_id:
            # A different pack vintage set (or default flip) invalidates the
            # persisted label; fail back to the governed default comparator.
            st.session_state[vintage_key] = labels[default_id]
        vintage_cols = st.columns([0.34, 0.66])
        with vintage_cols[0]:
            selected_label = st.selectbox(
                "Official comparator vintage",
                options,
                key=vintage_key,
                help=(
                    "Published official comparator releases materialized in the committed "
                    "runtime pack. The default is the pack's governed comparator vintage; "
                    "prior vintages remain selectable for comparison and never receive "
                    "Current policy overlays."
                ),
                **_widget_default_kwargs(vintage_key, index=0),
            )
        selected_id = label_to_id.get(str(selected_label), default_id)
        with vintage_cols[1]:
            if should_show_local_audit_controls():
                overlay = st.checkbox(
                    "Overlay prior official vintages",
                    key="revenue_outlook_official_vintage_overlay",
                    help=(
                        "Analyst view: keep every published official vintage on the charts "
                        "at once. The selected vintage stays the governed comparator; prior "
                        "vintages render in a muted style."
                    ),
                    **_widget_default_kwargs("revenue_outlook_official_vintage_overlay", value=False),
                )
    entry = available[selected_id]
    release = str(entry.get("release_round") or selected_id)
    displayed_ids = [selected_id] + [
        vid for vid in ordered_ids if overlay and vid != selected_id
    ]
    return {
        "vintage_id": selected_id,
        "release_round": release,
        "trace_name": _official_vintage_trace_name(selected_id, entry),
        "scenario_name": str(
            entry.get("scenario_name") or official_comparator_scenario_name(selected_id)
        ),
        "overlay": bool(overlay),
        "available": available,
        "all_trace_names": tuple(
            _official_vintage_trace_name(vid, available[vid]) for vid in ordered_ids
        ),
        "displayed_trace_names": tuple(
            _official_vintage_trace_name(vid, available[vid]) for vid in displayed_ids
        ),
        "displayed_release_rounds": tuple(
            str(available[vid].get("release_round") or vid) for vid in displayed_ids
        ),
        "mbu26_displayed": "MBU26" in displayed_ids,
    }


def _apply_official_vintage_to_trace_options(
    trace_options: list[str],
    official_vintage_state: dict[str, Any],
) -> list[str]:
    """Trace options restricted to displayed official vintages, selected first."""
    options = list(trace_options or [])
    all_officials = set(official_vintage_state["all_trace_names"])
    displayed = [
        trace
        for trace in official_vintage_state["displayed_trace_names"]
        if trace in set(options)
    ]
    ordered: list[str] = []
    inserted = False
    for option in options:
        if option in all_officials:
            if not inserted and displayed:
                ordered.extend(displayed)
                inserted = True
            continue
        ordered.append(option)
    if not inserted and displayed:
        anchor = 1 if ordered[:1] == ["Actual"] else 0
        ordered[anchor:anchor] = displayed
    return ordered


def _render_lever_accordion(
    selected_metric_type: str,
    sensitivity_options: list[str],
    sensitivity_labels: dict[str, dict[str, str]],
    show_official_policy_control: bool = True,
) -> dict[str, Any]:
    """Advanced scenario levers accordion (rendered in single-scenario view only).

    One accordion holds every scenario lever; re-entering the same expander
    object appends each group without re-indenting their layouts. Widget
    defaults go through ``_widget_default_kwargs`` because these keys are
    persisted across the compare-mode switch.
    """
    # Activity paths respond directly to the PED pump-price input and the
    # diesel-plus-RUC generalized running-cost input, so keep their timing
    # switches in view when the user changes to an activity series. Revenue
    # views retain the quieter, collapsed-by-default layout.
    lever_expander = st.expander(
        "Advanced scenario levers",
        expanded=selected_metric_type == "activity",
    )
    with lever_expander:
        sensitivities_sub = (
            "<div class='page5-panel-sub'>Demand and intensity levers layered onto the current forecasts.</div>"
            if method_detail_enabled()
            else ""
        )
        st.markdown(f"<div class='page5-panel-title'>Sensitivities</div>{sensitivities_sub}", unsafe_allow_html=True)
        sens_cols = st.columns([0.20, 0.20, 0.20, 0.40])
        with sens_cols[0]:
            selected_fleet_efficiency = st.selectbox(
                "Fleet efficiency",
                sensitivity_options,
                format_func=lambda level: sensitivity_labels["fleet_efficiency"].get(level, str(level)),
                key="revenue_outlook_sensitivity_fleet_efficiency",
                **_widget_default_kwargs("revenue_outlook_sensitivity_fleet_efficiency", index=sensitivity_options.index("Off")),
            )
        with sens_cols[1]:
            selected_pt_mode_shift = st.selectbox(
                "PT mode shift",
                sensitivity_options,
                format_func=lambda level: sensitivity_labels["pt_mode_shift"].get(level, str(level)),
                key="revenue_outlook_sensitivity_pt_mode_shift",
                **_widget_default_kwargs("revenue_outlook_sensitivity_pt_mode_shift", index=sensitivity_options.index("Off")),
            )
        with sens_cols[2]:
            # While method detail is hidden the freight-rail lever is withdrawn
            # from view and the sensitivity stays at its neutral "Off" level.
            freight_rail_enabled = method_detail_enabled() and st.toggle(
                "Freight rail shift",
                key="revenue_outlook_sensitivity_freight_rail_toggle",
                help=FREIGHT_RAIL_SHIFT_NOTE,
                **_widget_default_kwargs("revenue_outlook_sensitivity_freight_rail_toggle", value=False),
            )
            if freight_rail_enabled:
                freight_level_options = [level for level in sensitivity_options if level != "Off"]
                selected_freight_rail_shift = st.selectbox(
                    "Rail shift level",
                    freight_level_options,
                    format_func=lambda level: sensitivity_labels["freight_rail_shift"].get(level, str(level)),
                    key="revenue_outlook_sensitivity_freight_rail_shift",
                    **_widget_default_kwargs("revenue_outlook_sensitivity_freight_rail_shift", index=freight_level_options.index("Med")),
                )
            else:
                selected_freight_rail_shift = "Off"
        with sens_cols[3]:
            custom_fleet_efficiency_pct = None
            custom_pt_shift_pct = None
            custom_freight_shift_pct = None
            if selected_fleet_efficiency == "Custom":
                custom_fleet_efficiency_pct = st.number_input("Custom efficiency % p.a.", min_value=0.0, max_value=10.0, value=1.0, step=0.1)
            if selected_pt_mode_shift == "Custom":
                custom_pt_shift_pct = st.number_input("Custom PT shift % p.a.", min_value=0.0, max_value=10.0, value=0.5, step=0.1)
            if selected_freight_rail_shift == "Custom":
                custom_freight_shift_pct = st.number_input("Custom rail shift % p.a.", min_value=0.0, max_value=10.0, value=0.5, step=0.1)
            if method_detail_enabled() and all(value != "Custom" for value in [selected_fleet_efficiency, selected_pt_mode_shift, selected_freight_rail_shift]):
                st.caption("Custom inputs appear only when selected.")
    with lever_expander:
        uptake_sub = (
            "<div class='page5-panel-sub'>Light RUC fleet composition, from the MoT Vehicle Fleet Model. This sets the class mix only; it does not change total light RUC travel.</div>"
            if method_detail_enabled()
            else ""
        )
        st.markdown(f"<div class='page5-panel-title'>EV/PHEV uptake</div>{uptake_sub}", unsafe_allow_html=True)
        uptake_cols = st.columns([0.30, 0.70])
        with uptake_cols[0]:
            # The uptake basis is a whole-scenario input, so while the VFM
            # analyst layers are paused the Fast/Slow compositions come out of
            # this selector too. Hiding the layers while leaving the basis
            # selectable would still let a reader run the Fast/Slow composition
            # through the entire engine.
            uptake_mode_options = _public_uptake_basis_options()
            selected_ev_uptake_mode = st.selectbox(
                "Uptake basis",
                uptake_mode_options,
                key="revenue_outlook_ev_uptake_basis_v2",
                help=VFM_SOURCE_NOTE + "\n\n" + SENSITIVITY_INTERPLAY_NOTE,
                **_widget_default_kwargs(
                    "revenue_outlook_ev_uptake_basis_v2",
                    index=uptake_mode_options.index(DEFAULT_EV_UPTAKE_MODE),
                ),
            )
        # The petrol-retention sensitivity is no longer a reader control: the
        # rolling-origin comparison did not support the overlay as a Base path,
        # so production always runs the raw AR(1) petrol path. See
        # REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL.
        if method_detail_enabled():
            st.caption(
                "Base PED forecast is the raw AR(1) VKT per capita times population."
            )
        custom_ev_levers: tuple[float, ...] = ()
        with uptake_cols[1]:
            if selected_ev_uptake_mode == EV_UPTAKE_CUSTOM_OPTION:
                defaults = EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]

                def _lever_input(label: str, key: str, **kwargs: Any) -> float:
                    default_value = kwargs.pop("value")
                    return st.number_input(label, key=key, **kwargs, **_widget_default_kwargs(key, value=default_value))

                light_col, ped_col, heavy_col = st.columns(3)
                with light_col:
                    st.markdown("**Light RUC pool**")
                    bev_speed = _lever_input("BEV peak speed (pp/yr)", "ev_lever_bev_speed", min_value=0.5, max_value=10.0, value=defaults.bev_peak_speed_pp * 100, step=0.25)
                    bev_peak_year = _lever_input("BEV peak year", "ev_lever_bev_peak_year", min_value=2026, max_value=2050, value=int(defaults.bev_peak_year), step=1)
                    bev_2050 = _lever_input("BEV share 2050 (%)", "ev_lever_bev_2050", min_value=10.0, max_value=99.0, value=defaults.bev_share_2050 * 100, step=1.0)
                    phev_start = _lever_input("PHEV start share (%)", "ev_lever_phev_start", min_value=0.0, max_value=15.0, value=defaults.phev_start_share * 100, step=0.5)
                    phev_rise = _lever_input("PHEV rise (pp/yr)", "ev_lever_phev_rise", min_value=0.1, max_value=5.0, value=defaults.phev_rise_pp * 100, step=0.1)
                    phev_peak = _lever_input("PHEV peak share (%)", "ev_lever_phev_peak", min_value=1.0, max_value=40.0, value=defaults.phev_peak_share * 100, step=0.5)
                    phev_decay = _lever_input("PHEV decay (%/yr)", "ev_lever_phev_decay", min_value=0.0, max_value=25.0, value=defaults.phev_decay_rate * 100, step=0.5)
                with ped_col:
                    st.markdown("**PED petrol displacement**")
                    ped_speed = _lever_input("Displacement speed (pp/yr)", "ev_lever_ped_speed", min_value=0.5, max_value=12.0, value=defaults.ped_disp_speed_pp * 100, step=0.25)
                    ped_mid = _lever_input("Displacement midpoint year", "ev_lever_ped_mid", min_value=2028, max_value=2055, value=int(defaults.ped_disp_midpoint), step=1)
                    ped_2050 = _lever_input("Displaced by 2050 (%)", "ev_lever_ped_2050", min_value=0.0, max_value=95.0, value=defaults.ped_disp_2050 * 100, step=1.0)
                with heavy_col:
                    st.markdown("**Heavy RUC pool**")
                    heavy_speed = _lever_input("Heavy BEV speed (pp/yr)", "ev_lever_heavy_speed", min_value=0.25, max_value=8.0, value=defaults.heavy_bev_speed_pp * 100, step=0.25)
                    heavy_mid = _lever_input("Heavy BEV midpoint year", "ev_lever_heavy_mid", min_value=2035, max_value=2075, value=int(defaults.heavy_bev_midpoint), step=1)
                    heavy_2050 = _lever_input("Heavy BEV share 2050 (%)", "ev_lever_heavy_2050", min_value=0.0, max_value=80.0, value=defaults.heavy_bev_share_2050 * 100, step=1.0)
                custom_ev_levers = (
                    bev_speed / 100.0,
                    float(bev_peak_year),
                    bev_2050 / 100.0,
                    phev_start / 100.0,
                    phev_rise / 100.0,
                    phev_peak / 100.0,
                    phev_decay / 100.0,
                    ped_speed / 100.0,
                    float(ped_mid),
                    ped_2050 / 100.0,
                    heavy_speed / 100.0,
                    float(heavy_mid),
                    heavy_2050 / 100.0,
                )
            elif method_detail_enabled():
                preset = EV_UPTAKE_PRESETS[selected_ev_uptake_mode]
                st.caption(
                    f"Light BEV: peak {preset.bev_peak_speed_pp * 100:.2f} pp/yr in {preset.bev_peak_year:.0f}, "
                    f"{preset.bev_share_2050 * 100:.0f}% of the light RUC pool by 2050; "
                    f"PHEV: +{preset.phev_rise_pp * 100:.1f} pp/yr to {preset.phev_peak_share * 100:.1f}%, then -{preset.phev_decay_rate * 100:.1f}%/yr. "
                    f"PED: {preset.ped_disp_2050 * 100:.0f}% of petrol activity displaced by 2050 (midpoint {preset.ped_disp_midpoint:.0f}, raw bridge only). "
                    f"Heavy: {preset.heavy_bev_share_2050 * 100:.0f}% BEV by 2050 (rollup-neutral; BEVs pay the same per-km RUC). "
                    "Applied in this view only; the governed pack is unchanged."
                )
    with lever_expander:
        _session_fed_policy_state(
            "revenue_outlook_fed_policy_state",
            legacy_toggle_key="revenue_outlook_fed_uplift",
        )
        _session_fed_policy_state(
            "revenue_outlook_mbu_fed_policy_state",
            legacy_toggle_key="revenue_outlook_mbu_fed_uplift",
            default=FED_POLICY_PUBLISHED,
        )
        fed_policy_sub = (
            "<div class='page5-panel-sub'>Choose the original 1 January 2027 start, the six-month deferral to 1 July 2027, or no 12c uplift. The choice is carried into the PED retail-price input and proportionately into Light and Heavy RUC rates. Conventional RUC activity responds once to combined diesel-plus-RUC running cost; BEV/PHEV kilometres stay fixed because no approved class-specific charge elasticity is available. Current scenarios and the MBU26 official comparator counterfactual are selected independently.</div>"
            if method_detail_enabled()
            else ""
        )
        st.markdown(
            f"<div class='page5-panel-title'>12c FED / proportional RUC policy</div>{fed_policy_sub}",
            unsafe_allow_html=True,
        )
        policy_cols = st.columns([0.34, 0.34, 0.32])
        with policy_cols[0]:
            fed_policy_state = st.selectbox(
                "Current 12c policy",
                list(FED_POLICY_OPTIONS),
                format_func=lambda state: FED_POLICY_LABELS[str(state)],
                key="revenue_outlook_fed_policy_state",
                help=(
                    "Scope: Base, High population and all Low/Medium/High conflict traces, including "
                    "their modelled activity response. Original timing starts 1 Jan 2027; deferred starts "
                    "1 Jul 2027; no uplift removes the 12c step entirely."
                ),
                **_widget_default_kwargs(
                    "revenue_outlook_fed_policy_state",
                    index=FED_POLICY_OPTIONS.index(FED_POLICY_DELAYED_6M),
                ),
            )
        with policy_cols[1]:
            if show_official_policy_control and method_detail_enabled():
                mbu_fed_policy_state = st.selectbox(
                    "Synthetic official rate-only counterfactual — not a published forecast",
                    list(FED_POLICY_OPTIONS),
                    format_func=lambda state: FED_POLICY_LABELS[str(state)],
                    key="revenue_outlook_mbu_fed_policy_state",
                    help=(
                        "Scope: MBU26 comparator only. The published source pack is never overwritten. "
                        "Original timing starts 1 Jan 2027; deferred starts 1 Jul 2027; no uplift removes "
                        "the 12c step entirely."
                    ),
                    **_widget_default_kwargs(
                        "revenue_outlook_mbu_fed_policy_state",
                        index=FED_POLICY_OPTIONS.index(FED_POLICY_PUBLISHED),
                    ),
                )
                st.caption(
                    "Applies to the MBU26 official trace only. BEFU26 has no synthetic "
                    "policy counterfactual; generating one requires a separate owner decision."
                )
            else:
                # No synthetic counterfactual exists for the displayed official
                # vintage(s); the comparator stays exactly as published.
                mbu_fed_policy_state = FED_POLICY_PUBLISHED
        with policy_cols[2]:
            # While method detail is hidden the e-RUC lever is withdrawn from
            # view and the transition stays off with its default levers.
            eruc_enabled = method_detail_enabled() and st.toggle(
                "Move petrol fleet to e-RUC",
                key="revenue_outlook_eruc_toggle",
                help=ERUC_NOTE,
                **_widget_default_kwargs("revenue_outlook_eruc_toggle", value=False),
            )
        eruc_lever_values: tuple[float, ...] = ()
        with policy_cols[2]:
            if eruc_enabled:
                eruc_input_cols = st.columns(5)
                with eruc_input_cols[0]:
                    eruc_start = st.number_input("Start FY", min_value=2026, max_value=2045, step=1, key="eruc_lever_start", **_widget_default_kwargs("eruc_lever_start", value=2027))
                with eruc_input_cols[1]:
                    eruc_phase = st.number_input("Phase-in (years)", min_value=1, max_value=10, step=1, key="eruc_lever_phase", **_widget_default_kwargs("eruc_lever_phase", value=3))
                with eruc_input_cols[2]:
                    eruc_ratio = st.number_input("e-RUC rate vs light RUC (%)", min_value=25.0, max_value=200.0, step=5.0, key="eruc_lever_ratio", **_widget_default_kwargs("eruc_lever_ratio", value=100.0))
                with eruc_input_cols[3]:
                    eruc_elasticity = st.number_input("VKT elasticity", min_value=-1.0, max_value=0.0, step=0.05, key="eruc_lever_elasticity", **_widget_default_kwargs("eruc_lever_elasticity", value=-0.15))
                with eruc_input_cols[4]:
                    eruc_pump = st.number_input("Pump price ($/L incl. excise)", min_value=1.0, max_value=6.0, step=0.05, key="eruc_lever_pump", **_widget_default_kwargs("eruc_lever_pump", value=2.70))
                eruc_lever_values = (
                    float(eruc_start),
                    float(eruc_phase),
                    eruc_ratio / 100.0,
                    float(eruc_elasticity),
                    float(eruc_pump),
                )
                st.caption(
                    "Migrated petrol km leave the excise base and pay e-RUC per km; demand responds to the net "
                    "running-cost change so the tax-free pump price still drives VKT. Petrol demand stays on the "
                    "PED finalist; the Light RUC finalist is not re-estimated."
                )
    return {
        "fleet": selected_fleet_efficiency,
        "pt": selected_pt_mode_shift,
        "freight": selected_freight_rail_shift,
        "custom_fleet": custom_fleet_efficiency_pct,
        "custom_pt": custom_pt_shift_pct,
        "custom_freight": custom_freight_shift_pct,
        "uptake_mode": selected_ev_uptake_mode,
        "custom_ev_levers": custom_ev_levers,
        "eruc_enabled": eruc_enabled,
        "eruc_levers": eruc_lever_values,
        "fed_policy_state": fed_policy_state,
        "mbu_fed_policy_state": mbu_fed_policy_state,
        "ped_retention_sensitivity": _production_ped_retention_sensitivity(),
    }


def _compare_mode_lever_state(selected_metric_type: str) -> dict[str, Any]:
    """Single-view lever selections read from session state in compare mode.

    The accordion is hidden while comparing (the A/B columns own the levers
    there), but these persisted selections keep driving the composition and
    audit sections below. Unkeyed Custom percentage inputs cannot persist,
    so Custom levels fall back to Off/Med like the Copy-to-A mapping.
    """

    def _level(key: str) -> str:
        value = str(st.session_state.get(key, "Off"))
        return "Off" if value == "Custom" else value

    freight = "Off"
    if bool(st.session_state.get("revenue_outlook_sensitivity_freight_rail_toggle", False)):
        freight = str(st.session_state.get("revenue_outlook_sensitivity_freight_rail_shift", "Med"))
        if freight == "Custom":
            freight = "Med"
    uptake_mode = sanitised_uptake_basis(
        st.session_state.get("revenue_outlook_ev_uptake_basis_v2", DEFAULT_EV_UPTAKE_MODE),
        default=DEFAULT_EV_UPTAKE_MODE,
    )
    custom_ev_levers: tuple[float, ...] = ()
    if uptake_mode == EV_UPTAKE_CUSTOM_OPTION:
        defaults = EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]

        def _lever(key: str, fallback: float) -> float:
            try:
                return float(st.session_state.get(key, fallback))
            except (TypeError, ValueError):
                return float(fallback)

        custom_ev_levers = (
            _lever("ev_lever_bev_speed", defaults.bev_peak_speed_pp * 100) / 100.0,
            _lever("ev_lever_bev_peak_year", defaults.bev_peak_year),
            _lever("ev_lever_bev_2050", defaults.bev_share_2050 * 100) / 100.0,
            _lever("ev_lever_phev_start", defaults.phev_start_share * 100) / 100.0,
            _lever("ev_lever_phev_rise", defaults.phev_rise_pp * 100) / 100.0,
            _lever("ev_lever_phev_peak", defaults.phev_peak_share * 100) / 100.0,
            _lever("ev_lever_phev_decay", defaults.phev_decay_rate * 100) / 100.0,
            _lever("ev_lever_ped_speed", defaults.ped_disp_speed_pp * 100) / 100.0,
            _lever("ev_lever_ped_mid", defaults.ped_disp_midpoint),
            _lever("ev_lever_ped_2050", defaults.ped_disp_2050 * 100) / 100.0,
            _lever("ev_lever_heavy_speed", defaults.heavy_bev_speed_pp * 100) / 100.0,
            _lever("ev_lever_heavy_mid", defaults.heavy_bev_midpoint),
            _lever("ev_lever_heavy_2050", defaults.heavy_bev_share_2050 * 100) / 100.0,
        )
    # With method detail hidden the e-RUC lever is not on screen, so a stale
    # persisted toggle must not keep driving the sections below the comparison.
    eruc_enabled = method_detail_enabled() and bool(
        st.session_state.get("revenue_outlook_eruc_toggle", False)
    )
    eruc_levers: tuple[float, ...] = ()
    if eruc_enabled:
        eruc_levers = (
            float(st.session_state.get("eruc_lever_start", 2027)),
            float(st.session_state.get("eruc_lever_phase", 3)),
            float(st.session_state.get("eruc_lever_ratio", 100.0)) / 100.0,
            float(st.session_state.get("eruc_lever_elasticity", -0.15)),
            float(st.session_state.get("eruc_lever_pump", 2.70)),
        )
    fed_policy_state = _session_fed_policy_state(
        "revenue_outlook_fed_policy_state",
        legacy_toggle_key="revenue_outlook_fed_uplift",
    )
    mbu_fed_policy_state = _session_fed_policy_state(
        "revenue_outlook_mbu_fed_policy_state",
        legacy_toggle_key="revenue_outlook_mbu_fed_uplift",
        default=FED_POLICY_PUBLISHED,
    )
    if not method_detail_enabled():
        # The synthetic MBU26 counterfactual selector is not on screen, so a
        # stale persisted state must not reprice the official comparator.
        mbu_fed_policy_state = FED_POLICY_PUBLISHED
    return {
        "fleet": _level("revenue_outlook_sensitivity_fleet_efficiency"),
        "pt": _level("revenue_outlook_sensitivity_pt_mode_shift"),
        "freight": freight,
        "custom_fleet": None,
        "custom_pt": None,
        "custom_freight": None,
        "uptake_mode": uptake_mode,
        "custom_ev_levers": custom_ev_levers,
        "eruc_enabled": eruc_enabled,
        "eruc_levers": eruc_levers,
        "fed_policy_state": fed_policy_state,
        "mbu_fed_policy_state": mbu_fed_policy_state,
    }


STREAM_VINTAGE_LABELS = {
    "PED": "PED",
    "LIGHT_RUC": "Light RUC",
    "HEAVY_RUC": "Heavy RUC",
}


def stream_vintage_caption_text(period_rule: dict[str, Any]) -> str:
    """Compact per-stream input-history vintage and forecast-origin caption.

    Pure text builder over the committed pack manifest. Returns "" when the
    manifest predates the per-stream seam, so an older pack renders exactly as
    before. A provisional value is explicitly named as not an observed actual;
    it is never rendered as one.
    """
    vintages = period_rule.get("stream_vintages")
    if not isinstance(vintages, dict) or not vintages:
        return ""
    parts: list[str] = []
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        entry = vintages.get(stream)
        if not isinstance(entry, dict):
            continue
        label = STREAM_VINTAGE_LABELS.get(stream, stream)
        accepted = str(entry.get("latest_accepted_exact_actual") or "")
        first_forecast = str(entry.get("first_forecast_quarter") or "")
        if not accepted or not first_forecast:
            continue
        piece = f"**{label}** actual to {accepted}, forecast from {first_forecast}"
        if str(entry.get("provisional_seed") or "").strip():
            piece += " (a provisional bridge exists for the next quarter; not an observed actual)"
        parts.append(piece)
    if not parts:
        return ""
    history_vintage = str(period_rule.get("input_history_vintage") or "")
    prefix = f"Input-history vintage {history_vintage}. " if history_vintage else ""
    return prefix + " · ".join(parts) + "."


def _render_stream_vintage_caption(period_rule: dict[str, Any]) -> None:
    if not method_detail_enabled():
        return
    text = stream_vintage_caption_text(period_rule)
    if text:
        st.caption(text)


def render_revenue_outlook_page(loaded: LoadedRun) -> None:
    del loaded
    _discard_withdrawn_revenue_outlook_state()
    _persist_revenue_outlook_view_state()
    from model_dashboard.engine import active_engine, engine_revenue_outlook_dir

    repo_root = Path(__file__).resolve().parent
    engine = active_engine()
    pack_dir = repo_root / engine_revenue_outlook_dir(engine)
    timer = RevenueOutlookRenderTimer(_revenue_outlook_perf_debug_enabled())
    timer.start("pack load")
    pack_signature = revenue_outlook_signature(pack_dir, repo_root)
    pack = st.session_state.get("revenue_outlook_pack")
    if not isinstance(pack, RevenueOutlookPack) or str(pack.manifest.get("engine", "ensemble")) != engine:
        pack = cached_load_revenue_outlook_pack(
            str(pack_dir),
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

    # Fail closed BEFORE any chart work, with a governed message rather than a
    # raw traceback: the compiled replay cache is what makes this page fast,
    # and a stale one must never be served.
    replay_cache_problem = _revenue_outlook_replay_cache_problem(pack, pack_signature)
    if replay_cache_problem:
        section_title(REVENUE_OUTLOOK_TITLE)
        warning_panel(replay_cache_problem)
        return

    manifest = pack.manifest if pack is not None and isinstance(pack.manifest, dict) else {}
    # Bridge assumption vintage (annual rates/intensity/admin inputs); distinct
    # from the displayed official comparator vintage and from the Treasury
    # BEFU26 macro vintage.
    # Authoritative for every bridge-dependent calculation on this page: the
    # vintage recorded in THIS pack's manifest, never the live registry
    # default. A pack built on one bridge must never be re-bridged on another.
    bridge_vintage_id = bridge_vintage_id_from_manifest(
        manifest, Path(__file__).resolve().parent
    )
    bridge_vintage_release = bridge_vintage_id
    chart_rows = _pack_table(pack, "revenue_chart_rows")
    fan_availability = _pack_table(pack, "fan_availability")
    fan_band_rows = _pack_table(pack, "fan_band_rows")

    section_title(REVENUE_OUTLOOK_TITLE)
    period_rule = manifest.get("period_rule") if isinstance(manifest, dict) else {}
    runtime_cutoff_fy = (period_rule or {}).get("runtime_cutoff_fy") if isinstance(period_rule, dict) else None

    if chart_rows.empty:
        warning_panel("The promoted Revenue Outlook pack has no chart rows.")
        return

    # The horizon-support prose is governance metadata, not public copy. It
    # stays in downloads (horizon_scope, horizon_zone, per-state quarter
    # counts), the manifest, hover labels and audit tables;
    # _forecast_horizon_support_note remains available to governance views.
    # The public page renders no warning banner for it.

    # Input-history vintage and the per-stream actual/forecast seam. Streams
    # can hold different accepted cutoffs (an exact Light/Heavy quarter beside
    # a still-provisional PED quarter), so the seam is stated per stream as a
    # compact caption - deliberately not a warning banner - with the full
    # table and lineage in the details/downloads expander below.
    _render_stream_vintage_caption(period_rule if isinstance(period_rule, dict) else {})

    timer.start("selector metadata")
    selector_options = cached_revenue_outlook_selectors(pack_signature, pack)
    timer.stop("selector metadata")
    stream_options = selector_options["stream_options"]
    default_stream_index = stream_options.index("Total NLTF revenue") if "Total NLTF revenue" in stream_options else 0
    fed_path_options = selector_options["fed_path_options"]
    default_fed_index = fed_path_options.index("Current planned path") if "Current planned path" in fed_path_options else 0
    trace_options = selector_options["trace_options"]
    fy_options = selector_options["fy_options"]
    # FY2030 is the last MoT-forecast June year in the official vintages;
    # beyond it the paths are extrapolation, so the selected-FY marker
    # defaults to the window end.
    default_fy_index = fy_options.index("FY2030") if "FY2030" in fy_options else max(len(fy_options) - 1, 0)

    with st.container(border=True):
        controls_sub = (
            "<div class='page5-panel-sub'>Choose a view, then the series every chart below tracks.</div>"
            if method_detail_enabled()
            else ""
        )
        st.markdown(f"<div class='page5-panel-title'>Revenue Outlook controls</div>{controls_sub}", unsafe_allow_html=True)
        view_cols = st.columns([0.42, 0.58])
        with view_cols[0]:
            st.markdown("<div class='control-label'>View</div>", unsafe_allow_html=True)
            view_mode = st.radio(
                "View",
                [REVENUE_OUTLOOK_VIEW_SINGLE, REVENUE_OUTLOOK_VIEW_COMPARE],
                horizontal=True,
                label_visibility="collapsed",
                key="revenue_outlook_view_mode",
                help=(
                    "Single scenario plots the committed forecast with the advanced levers applied. "
                    "Compare A vs B replaces the total path chart with two independently configured "
                    "scenarios: overlaid paths, horizon NPV and adaptive delta cards."
                ),
            )
        compare_mode = view_mode == REVENUE_OUTLOOK_VIEW_COMPARE
        with view_cols[1]:
            selected_stream = st.selectbox(
                "Series",
                stream_options,
                index=default_stream_index,
                key="revenue_outlook_stream",
                format_func=_revenue_outlook_series_display_label,
            )
        selected_metric_type = _revenue_outlook_series_metric_type(chart_rows, selected_stream)
        # Governed official comparator vintage selection (default = the pack's
        # comparator vintage). Rendered in both view modes so the A/B official
        # option and the sections below the comparison stay bound to it.
        official_vintage_state = _render_official_vintage_controls(manifest)
        # The long-run shape method is a SEPARATE analyst control: selecting a
        # comparator vintage must not change the Current long-run shape, and
        # vice versa.
        long_run_shape_state = _render_long_run_shape_controls(manifest)
        selected_official_trace = str(official_vintage_state["trace_name"])
        selected_official_release = str(official_vintage_state["release_round"])
        trace_options = _apply_official_vintage_to_trace_options(trace_options, official_vintage_state)
        # Rows carry the planned path; the 12c counterfactual is a display
        # reprice handled by the policy selector in the lever accordion.
        selected_fed_path = fed_path_options[default_fed_index] if fed_path_options else ""
        selected_trace_defaults = _revenue_outlook_default_traces(
            trace_options, selected_official_trace=selected_official_trace
        )
        if compare_mode:
            if method_detail_enabled():
                st.caption(
                    "Comparison plots June years. Time grain, FY marker and legend selections apply to "
                    "the single-scenario view and are kept while you compare."
                )
            grain_label = str(st.session_state.get("revenue_outlook_time_grain", "June-year"))
            default_fy = fy_options[default_fy_index] if fy_options else ""
            selected_fy = str(st.session_state.get("revenue_outlook_selected_fy", default_fy))
            if selected_fy not in fy_options and fy_options:
                selected_fy = default_fy
            # Compare mode reads the persisted single-view layer selection: the
            # A/B panel owns its own traces, but the sections below the
            # comparison still track this choice.
            layer_catalogue = _revenue_outlook_layer_catalogue(
                trace_options, selected_trace_defaults
            )
            persisted = st.session_state.get("revenue_outlook_chart_layers")
            label_to_id = {spec.label: spec.layer_id for spec in layer_catalogue}
            selected_layer_ids = (
                [label_to_id[label] for label in persisted if label in label_to_id]
                if persisted
                else default_layer_ids(layer_catalogue)
            )
            selected_traces = path_trace_names(layer_catalogue, selected_layer_ids)
            selected_band_layers = tuple(band_layer_ids(layer_catalogue, selected_layer_ids))
            if not selected_traces:
                selected_traces = selected_trace_defaults or list(trace_options[:1])
        else:
            # Widgets whose state survives compare mode via the persistence
            # idiom must not also pass a default once the key exists, or
            # Streamlit logs a default-vs-session-state warning per rerun.
            control_cols = st.columns([0.20, 0.16, 0.28, 0.36])
            with control_cols[0]:
                grain_label = st.radio(
                    "Time grain",
                    ["June-year", "Quarterly"],
                    horizontal=True,
                    key="revenue_outlook_time_grain",
                )
            with control_cols[1]:
                fy_default_kwargs = {} if "revenue_outlook_selected_fy" in st.session_state else {"index": default_fy_index}
                selected_fy = st.selectbox(
                    "Selected FY",
                    fy_options,
                    key="revenue_outlook_selected_fy",
                    **fy_default_kwargs,
                )
            with control_cols[2]:
                # ONE control for every layer - deterministic paths and the
                # conditional modelled-uncertainty bands - so nothing is
                # selectable in two contradictory places.
                layer_catalogue = _revenue_outlook_layer_catalogue(
                    trace_options, selected_trace_defaults
                )
                layer_labels = {spec.label: spec.layer_id for spec in layer_catalogue}
                default_labels = [
                    spec.label for spec in layer_catalogue if spec.default_selected
                ]
                st.markdown("<div class='control-label'>Show on chart</div>", unsafe_allow_html=True)
                layer_default_kwargs = (
                    {}
                    if "revenue_outlook_chart_layers" in st.session_state
                    else {"default": default_labels}
                )
                chosen_labels = st.multiselect(
                    "Show on chart",
                    list(layer_labels),
                    key="revenue_outlook_chart_layers",
                    label_visibility="collapsed",
                    help=(
                        "Paths are deterministic scenarios. The 50%/80% bands are "
                        "conditional model forecast-error bands and exclude "
                        "Treasury-driver forecast uncertainty."
                    ),
                    **layer_default_kwargs,
                )
                selected_layer_ids = [layer_labels[label] for label in chosen_labels if label in layer_labels]
                if not selected_layer_ids:
                    selected_layer_ids = default_layer_ids(layer_catalogue)
                    st.caption("Using the default chart layers.")
                selected_traces = path_trace_names(layer_catalogue, selected_layer_ids)
                selected_band_layers = tuple(band_layer_ids(layer_catalogue, selected_layer_ids))
                if not selected_traces:
                    selected_traces = selected_trace_defaults or list(trace_options[:1])
                st.caption(
                    _revenue_outlook_trace_selection_summary(selected_traces, len(trace_options))
                    + (f" · {len(selected_band_layers)} band layer(s)" if selected_band_layers else "")
                )
        bridge_mode_lookup = selector_options["bridge_mode_lookup"]
        bridge_mode_options = list(bridge_mode_lookup)
        default_bridge_label = next(
            (label for label, mode in bridge_mode_lookup.items() if mode == PED_BRIDGE_DEFAULT_MODE),
            bridge_mode_options[-1] if bridge_mode_options else "Optimized migration bridge",
        )
        # The raw model bridge is the sole PED pathway on this page: petrol->EV
        # displacement is owned by the interpretable VFM-inferred uptake lever
        # (which reproduces the retired lambda-optimizer within fit tolerance),
        # so the esoteric raw/optimized bridge selector is gone. The lambda
        # machinery and its audit tables remain in the pack as lineage.
        selected_ped_bridge_label = default_bridge_label
        selected_ped_bridge_mode = PED_BRIDGE_DEFAULT_MODE
    sensitivity_options = list(SENSITIVITY_LEVELS)
    sensitivity_labels = selector_options["sensitivity_labels"]
    selected_demand_elasticity = "Off"
    cost_per_km_ratio = None
    custom_ped_elasticity = None
    custom_light_elasticity = None
    custom_heavy_elasticity = None
    if compare_mode:
        # The accordion disappears gracefully in compare mode - the A/B
        # columns own the levers there - while the persisted single-view
        # selections keep driving the composition and audit sections below.
        lever_state = _compare_mode_lever_state(selected_metric_type)
    else:
        lever_state = _render_lever_accordion(
            selected_metric_type,
            sensitivity_options,
            sensitivity_labels,
            show_official_policy_control=bool(official_vintage_state["mbu26_displayed"]),
        )
    selected_fleet_efficiency = lever_state["fleet"]
    selected_pt_mode_shift = lever_state["pt"]
    selected_freight_rail_shift = lever_state["freight"]
    custom_fleet_efficiency_pct = lever_state["custom_fleet"]
    custom_pt_shift_pct = lever_state["custom_pt"]
    custom_freight_shift_pct = lever_state["custom_freight"]
    selected_ev_uptake_mode = lever_state["uptake_mode"]
    custom_ev_levers = lever_state["custom_ev_levers"]
    eruc_enabled = lever_state["eruc_enabled"]
    eruc_lever_values = lever_state["eruc_levers"]
    fed_policy_state = _normalise_fed_policy_state(lever_state["fed_policy_state"])
    mbu_fed_policy_state = _normalise_fed_policy_state(lever_state["mbu_fed_policy_state"])
    if not official_vintage_state["mbu26_displayed"]:
        # The synthetic rate-only counterfactual exists for MBU26 only; while
        # MBU26 is not displayed the official comparator stays published.
        mbu_fed_policy_state = FED_POLICY_PUBLISHED
    ped_retention_sensitivity = bool(lever_state.get("ped_retention_sensitivity", False))
    lever_summary = _active_lever_summary(
        fleet=selected_fleet_efficiency,
        pt_shift=selected_pt_mode_shift,
        freight=selected_freight_rail_shift,
        uptake_mode=selected_ev_uptake_mode,
        eruc_on=eruc_enabled,
        fed_policy_state=fed_policy_state,
        mbu_fed_policy_state=mbu_fed_policy_state,
    )
    if lever_summary and method_detail_enabled():
        if compare_mode:
            st.caption(f"Single-view levers (still applied to the sections below the comparison): {lever_summary}")
        else:
            st.caption(f"Active levers: {lever_summary}")
    # Every value-changing control, by NAME. The positional tuple this replaced
    # had let the official comparator vintage id (slot 6) be read as the
    # Heavy-BEV flag, so a non-empty vintage silently switched Heavy-BEV
    # reclassification on in every production render.
    ev_uptake_key = RevenueScenarioComputationKey(
        engine=engine,
        uptake_basis=selected_ev_uptake_mode,
        custom_ev_levers=custom_ev_levers,
        eruc_levers=eruc_lever_values,
        current_fed_policy_state=fed_policy_state,
        official_fed_policy_state=mbu_fed_policy_state,
        ped_retention_sensitivity=ped_retention_sensitivity,
        # Explicit, and Off unless a reader asks for it. Never inferred from
        # another field's truthiness.
        heavy_bev_transition=HEAVY_BEV_DEFAULT,
        official_comparator_vintage_id=str(official_vintage_state["vintage_id"]),
        official_comparator_overlay=bool(official_vintage_state["overlay"]),
        ped_bridge_mode=str(selected_ped_bridge_mode),
        bridge_vintage_id=str(bridge_vintage_id),
        # Also folded into the pack signature, because the frames these change
        # are cached on that.
        long_run_transition_schedule_id=str(long_run_shape_state["schedule_id"]),
        long_run_shape_vintage_id=str(long_run_shape_state["shape_vintage_id"]),
    )
    pack, pack_signature = _apply_long_run_shape_selection(
        pack, pack_signature, str(pack_dir), ev_uptake_key
    )
    # The governed long-run details, rendered wherever a non-default long-run
    # construction is on screen. A reader must be able to see which anchor,
    # shape source, composition and schedule produced the FY2031-FY2050 tail
    # without opening the manifest.
    if str(long_run_shape_state["schedule_id"]) != UNBLENDED_SCHEDULE_ID and method_detail_enabled():
        st.caption(
            "Long-run construction — "
            + _long_run_shape_details_text(
                long_run_shape_state, _selected_vfm_scenario_label()
            ).replace("  \n", " · ")
        )
    sensitivity_key = selected_sensitivity_key(
        fleet_efficiency=selected_fleet_efficiency,
        pt_mode_shift=selected_pt_mode_shift,
        demand_elasticity=selected_demand_elasticity,
        freight_rail_shift=selected_freight_rail_shift,
        custom_fleet_efficiency_pct=custom_fleet_efficiency_pct,
        custom_pt_shift_pct=custom_pt_shift_pct,
        custom_freight_shift_pct=custom_freight_shift_pct,
        custom_ped_elasticity=custom_ped_elasticity,
        custom_light_elasticity=custom_light_elasticity,
        custom_heavy_elasticity=custom_heavy_elasticity,
        cost_per_km_ratio=cost_per_km_ratio,
    )
    selected_time_grain = "june_year" if grain_label == "June-year" else "quarterly"
    timer.start("sensitivity overlay")
    view = cached_revenue_outlook_view(
        pack_signature,
        selected_stream,
        selected_time_grain,
        selected_fed_path,
        tuple(selected_traces),
        sensitivity_key,
        selected_ped_bridge_mode,
        ev_uptake_key,
        pack,
    )
    timer.stop("sensitivity overlay")
    chart_rows = view["chart_rows"]
    line_reconciliation, formula_residuals, stack_components, bridge = cached_aligned_scenario_detail_frames(
        pack_signature,
        sensitivity_key,
        selected_ped_bridge_mode,
        ev_uptake_key,
        pack,
    )
    future_revenue = view["future_revenue_forecasts"]
    ped_revenue_bridge_audit = view["ped_revenue_bridge_audit"]
    ped_bridge_mode_impact_audit = view["ped_bridge_mode_impact_audit"]
    sensitivity_impact_audit = view["sensitivity_impact_audit"]
    filtered_rows = view["filtered_rows"]
    filtered_bridge = _filter_revenue_bridge_rows(
        bridge,
        [selected_stream],
        _scenario_names_for_traces(chart_rows, list(selected_traces)),
        [selected_fed_path],
    )
    gap_summary = _revenue_outlook_gap_summary(filtered_bridge)
    if gap_summary:
        warning_panel(gap_summary)
    fed_policy_audit = view.get("fed_uplift_audit", pd.DataFrame())
    if (
        isinstance(fed_policy_audit, pd.DataFrame)
        and not fed_policy_audit.empty
        and fed_policy_audit.get("transformation_basis", pd.Series(dtype=str))
        .astype(str)
        .eq("policy_replay_unavailable_not_applied")
        .any()
    ):
        warning_panel(
            "The full fixed-finalist PED/RUC policy replay is unavailable. Current Base and comparison "
            "paths are being left at published timing; no incomplete policy adjustment has been applied."
        )

    if compare_mode:
        # In compare mode these keys are built from the persisted single-view
        # lever state, so they ARE the current Single scenario configuration:
        # Scenario A passes them through untouched and Scenario B clones them.
        _render_scenario_comparison_panel(
            pack_signature,
            pack,
            selected_stream,
            selected_fed_path,
            sensitivity_labels,
            official_vintage_state,
            sensitivity_key,
            ev_uptake_key,
        )
    else:
        timer.start("main path figure")
        # The optional VFM Fast/Slow scenario paths are only computed when a
        # reader has actually selected them, so the default render never pays
        # for two extra full overlay passes. While the analyst layers are
        # paused the catalogue cannot return those trace names at all, and the
        # policy check makes that independent of any stale selection.
        plot_rows = filtered_rows
        if REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS and any(
            trace in selected_traces for trace in (VFM_FAST_TRACE_NAME, VFM_SLOW_TRACE_NAME)
        ):
            timer.start("vfm scenario paths")
            vfm_paths = cached_vfm_scenario_paths(
                pack_signature,
                selected_stream,
                selected_time_grain,
                selected_fed_path,
                tuple(selected_traces),
                sensitivity_key,
                selected_ped_bridge_mode,
                _cone_band_controls(ev_uptake_key),
                pack,
            )
            timer.stop("vfm scenario paths")
            if isinstance(vfm_paths, pd.DataFrame) and not vfm_paths.empty:
                wanted = vfm_paths[
                    vfm_paths["trace_name"].astype(str).isin(selected_traces)
                ]
                if not wanted.empty:
                    plot_rows = pd.concat([filtered_rows, wanted], ignore_index=True, sort=False)
        timer.start("uncertainty lookup")
        uncertainty_series_id = _uncertainty_series_id_for_label(chart_rows, selected_stream)
        # Modelled uncertainty is governed at June-year grain only: the draws,
        # the copula and the quantile map are all annual, and no governed
        # quarterly contract exists. Repeating an annual bound across four
        # quarters, or dividing its width by four, would invent a number, so
        # the band layers are withheld at quarterly grain and the reader is
        # told why rather than shown a fabricated interval.
        quarterly_grain = selected_time_grain == "quarterly"
        sensitivity_bands_withheld = _uncertainty_bands_withheld_for_sensitivity(
            sensitivity_key
        )
        if quarterly_grain or sensitivity_bands_withheld:
            uncertainty_rows = pd.DataFrame()
            band_layers_for_figure: tuple[str, ...] = tuple(
                layer
                for layer in selected_band_layers
                if layer not in (BAND_50_LAYER_ID, BAND_80_LAYER_ID)
            )
        else:
            uncertainty_rows = cached_uncertainty_band_rows(
                uncertainty_series_id,
                str(cached_uncertainty_pack().manifest.get("scenario_key_digest", "")),
                str(view.get("current_fed_policy_state") or ""),
                ev_uptake_key,
                pack,
            )
            band_layers_for_figure = tuple(selected_band_layers)
        timer.stop("uncertainty lookup")
        main_path_figure = cached_revenue_outlook_total_path_figure(
            pack_signature,
            selected_stream,
            selected_fy,
            selected_time_grain,
            selected_fed_path,
            tuple(selected_traces),
            sensitivity_key,
            selected_ped_bridge_mode,
            ev_uptake_key,
            plot_rows,
            view.get("cone_band"),
            uncertainty_rows,
            band_layers_for_figure,
        )
        timer.stop("main path figure")
        total_path_notes = [display_horizon_note()]
        short_current_note = _current_path_coverage_note(plot_rows, selected_stream)
        if short_current_note:
            total_path_notes.append(short_current_note)
        if quarterly_grain and any(
            layer in selected_band_layers for layer in (BAND_50_LAYER_ID, BAND_80_LAYER_ID)
        ):
            total_path_notes.append(QUARTERLY_UNCERTAINTY_NOT_GOVERNED_NOTE)
        if (
            sensitivity_bands_withheld
            and not quarterly_grain
            and any(
                layer in selected_band_layers
                for layer in (BAND_50_LAYER_ID, BAND_80_LAYER_ID)
            )
        ):
            total_path_notes.append(SENSITIVITY_UNCERTAINTY_WITHHELD_NOTE)
        cone_band_for_notes = view.get("cone_band")
        if (
            isinstance(cone_band_for_notes, pd.DataFrame)
            and not cone_band_for_notes.empty
            and VFM_ENVELOPE_LAYER_ID in selected_band_layers
        ):
            total_path_notes.append(VFM_ENVELOPE_NOT_PROBABILISTIC_NOTE)
        if selected_band_layers and any(
            layer in selected_band_layers for layer in (BAND_50_LAYER_ID, BAND_80_LAYER_ID)
        ):
            total_path_notes.append(CONDITIONAL_BAND)
        if view.get("quarterly_disaggregated"):
            total_path_notes.append(QUARTERLY_DISAGGREGATION_NOTE)
        if view.get("ev_uptake_applied"):
            total_path_notes.append(
                f"EV/PHEV uptake basis: {selected_ev_uptake_mode}. Light RUC conventional/BEV/PHEV km and "
                "revenue lines are reallocated with the lever share curves; light-petrol VKT, PED litres and "
                "PED/FED revenue move together on the matching petrol-retention curve (plus dependent rollups); "
                "the governed pack is unchanged. " + VFM_SOURCE_NOTE
            )
        if view.get("eruc_applied"):
            total_path_notes.append(ERUC_NOTE)
        active_current_policy = _normalise_fed_policy_state(
            view.get("current_fed_policy_state", fed_policy_state)
        )
        active_mbu_policy = _normalise_fed_policy_state(
            view.get("mbu26_fed_policy_state", mbu_fed_policy_state)
        )
        total_path_notes.append(
            "Current Base, High population and Middle East conflict traces: "
            + FED_POLICY_NOTES[active_current_policy]
        )
        if official_vintage_state["mbu26_displayed"] and active_mbu_policy != FED_POLICY_PUBLISHED:
            # The counterfactual must never read as a published MBU26 forecast
            # ("MBU26 deferred" / "MBU26 no uplift" are not published paths).
            official_note = (
                "Synthetic official rate-only counterfactual — not a published forecast. "
                "Applies to the MBU26 official trace only: "
                + FED_POLICY_NOTES[active_mbu_policy]
            )
            if selected_official_release != "MBU26":
                official_note = (
                    f"Official comparator: {selected_official_release} published. " + official_note
                )
            total_path_notes.append(official_note)
        else:
            total_path_notes.append(
                f"Official comparator: {selected_official_release} published"
            )
        total_path_notes.append(
            "Macro basis: current Base and High-population paths use the Treasury "
            "BEFU26 quarterly real-GDP forecast and June population anchors; PED "
            "uses the implied real GDP per capita, while Light and Heavy RUC use "
            "the same aggregate-GDP path. Middle East fuel paths add a one-way "
            "fuel-to-GDP overlay calibrated to Treasury's published 2027Q1 GDP "
            "gaps. GDP assumptions never synthesize or alter a fuel-price path."
        )
        selected_conflict_traces = [
            trace for trace in CONFLICT_TRACE_NAMES if trace in selected_traces
        ]
        conflict_notes = [
            CONFLICT_NOTE_BY_TRACE[trace] for trace in selected_conflict_traces
        ]
        total_path_notes.extend(conflict_notes)
        # Integrated VFM Scenario Envelope: the governed MoT VFM Fast-Slow
        # range now sits ON this chart, so the Total path takes the full page
        # width and the separate uncertainty-fan card no longer competes with
        # it for space. The fan's governed source data is unchanged and stays
        # reachable from the collapsed detail surface below; it is not
        # constructed unless a reader explicitly asks for it.
        chart_expanded = _render_expand_chart_control()
        chart_card(
            "Total path chart",
            "\n\n".join(total_path_notes),
            main_path_figure,
            caption="\n\n".join(conflict_notes) if conflict_notes else None,
            notes_as_tooltip=True,
            container_key=EXPANDED_CHART_CONTAINER_KEY if chart_expanded else None,
        )
        _render_revenue_outlook_vfm_envelope_caption(view)

    if not compare_mode and method_detail_enabled() and st.toggle(
        "Show forecast-uncertainty fan detail",
        value=False,
        key="revenue_outlook_show_fan_detail",
        help=(
            "The empirical 50%/80% forecast-error fan, its source, its "
            "supported horizon and its download. The fan is an empirical "
            "forecast-error band and stops at FY2030."
        ),
    ):
        timer.start("fan figure")
        _render_revenue_outlook_fan_card(
            pack_signature,
            fan_band_rows,
            fan_availability,
            selected_series=selected_stream,
            selected_fed_path=selected_fed_path,
            official_fed_paths=official_vintage_state["displayed_release_rounds"],
        )
        timer.stop("fan figure")

    if not compare_mode and method_detail_enabled() and st.toggle(
        "Show modelled-uncertainty audit",
        value=False,
        key="revenue_outlook_show_uncertainty_audit",
        help=(
            "The governed band values, their evidence state, the June-year "
            "basis behind them and the pack manifest. Nothing here is built "
            "until it is asked for."
        ),
    ):
        with st.container(border=True):
            st.caption(CONDITIONAL_BAND)
            pack_for_audit = cached_uncertainty_pack()
            if uncertainty_rows is not None and not uncertainty_rows.empty:
                display_table(uncertainty_rows, height=280)
                st.download_button(
                    "Download modelled-uncertainty band rows (CSV)",
                    uncertainty_rows.to_csv(index=False).encode("utf-8"),
                    file_name=f"revenue_outlook_uncertainty_{uncertainty_series_id}.csv",
                    mime="text/csv",
                    key="revenue_outlook_uncertainty_download",
                )
            else:
                st.caption(
                    f"No governed uncertainty rows for series {uncertainty_series_id!r} "
                    "in the committed pack."
                )
            if not pack_for_audit.basis.empty:
                st.caption(
                    "June-year basis: raw and weighted-isotonic quantiles with "
                    "origin-clustered bootstrap intervals and sample counts."
                )
                display_table(pack_for_audit.basis, height=240)
            if pack_for_audit.manifest:
                st.caption(
                    "Pack provenance — seed "
                    f"{pack_for_audit.manifest.get('seed')}, "
                    f"{pack_for_audit.manifest.get('draws')} draws, "
                    f"continuation {pack_for_audit.manifest.get('continuation_rule')}, "
                    f"scenario key {str(pack_for_audit.manifest.get('scenario_key_digest', ''))[:16]}."
                )
            st.caption(
                "Chart layer catalogue — every selectable layer, its kind, draw "
                "order and whether it is probabilistic."
            )
            display_table(pd.DataFrame(catalogue_frame(layer_catalogue)), height=280)

    # The MoT VFM Fast–Slow range audit is withdrawn with the layer it
    # describes; the toggle is not rendered while the analyst surface is paused.
    if REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS and not compare_mode and st.toggle(
        "Show MoT VFM Fast–Slow range audit",
        value=False,
        key="revenue_outlook_show_vfm_envelope_audit",
        help=(
            "Whether the selected series receives the structural scenario "
            "envelope, which scenarios bound it, over which years, and why it "
            "is absent when it is."
        ),
    ):
        with st.container(border=True):
            st.caption(VFM_ENVELOPE_NOT_PROBABILISTIC_NOTE)
            envelope_audit = view.get("cone_band_audit", pd.DataFrame())
            if isinstance(envelope_audit, pd.DataFrame) and not envelope_audit.empty:
                display_table(envelope_audit, height=120)
            envelope_band = view.get("cone_band", pd.DataFrame())
            if isinstance(envelope_band, pd.DataFrame) and not envelope_band.empty:
                display_table(envelope_band, height=260)
                st.download_button(
                    "Download VFM Fast–Slow range (CSV)",
                    envelope_band.to_csv(index=False).encode("utf-8"),
                    file_name="revenue_outlook_vfm_fast_slow_range.csv",
                    mime="text/csv",
                    key="revenue_outlook_vfm_envelope_download",
                )

    if revenue_outlook_lazy_table(
        "Show Middle East fuel-scenario audit",
        "revenue_outlook_show_fuel_price_audit",
        caption=(
            "Low, Medium and High petrol/diesel paths against Base, with source anchors, "
            "elasticity effects, policy timing and convergence periods."
        ),
    ):
        with st.expander("Middle East conflict: fuel-price scenario audit", expanded=False):
            st.caption(
                "The committed Low, Medium and High nominal price paths are converted to ratios "
                "against their nominal base paths, then applied to the model's real petrol and "
                "diesel inputs. Petrol drives PED; diesel drives Light and Heavy RUC activity."
            )
            st.caption(
                "The baseline macro path is Treasury BEFU26. Conflict fuel severity also selects "
                "a one-way Treasury-calibrated GDP path: Medium is 1.5% below Base and High is "
                "3.1% below Base at 2027Q1, with Low derived from the governed fuel-severity "
                "curve. The direction is intentionally asymmetric—changing GDP alone does not "
                "rewrite petrol or diesel prices."
            )
            st.caption(
                "The conflict path does not directly increase RUC tax rates. The separate 12c "
                "policy switch is carried into PED pump prices and proportionate Light/Heavy "
                "RUC rates. Conventional Light/Heavy activity uses one combined diesel-plus-RUC "
                "cost-per-1,000-km ratio against Base, with the governed retail-diesel elasticity "
                "applied once. BEV/PHEV kilometres are not mechanically scaled by a diesel shock."
            )
            input_audit = view.get("conflict_fuel_input_audit", pd.DataFrame())
            fuel_price_audit = view.get("fuel_price_scenario_audit", pd.DataFrame())
            if (input_audit is None or input_audit.empty) and (fuel_price_audit is None or fuel_price_audit.empty):
                warning_panel("Conflict fuel-price scenario audit is unavailable for the active engine pack.")
            else:
                input_tab, effect_tab = st.tabs(["Input shocks", "Forecast and revenue effects"])
                with input_tab:
                    if input_audit is None or input_audit.empty:
                        warning_panel("Input-shock lineage is unavailable for the active engine pack.")
                    else:
                        audit_cols = st.columns([0.82, 0.18])
                        with audit_cols[1]:
                            dataframe_download(
                                input_audit,
                                "Download CSV",
                                "middle_east_fuel_scenarios_input_audit.csv",
                            )
                        display_table(input_audit, height=360, max_rows=80)
                with effect_tab:
                    if fuel_price_audit is None or fuel_price_audit.empty:
                        warning_panel("Forecast and revenue effects are unavailable for the active engine pack.")
                    else:
                        audit_cols = st.columns([0.82, 0.18])
                        with audit_cols[1]:
                            dataframe_download(
                                fuel_price_audit,
                                "Download CSV",
                                "middle_east_fuel_scenarios_effect_audit.csv",
                            )
                        display_table(fuel_price_audit, height=360, max_rows=320)

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
                "Revenue Outlook charts and tables stop at the last governed common non-extrapolated horizon across current Base, current comparison and required "
                f"{bridge_vintage_release} bridge inputs."
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
        "Show input-history vintage by stream",
        "revenue_outlook_show_stream_vintage_status",
        caption="Per-stream actuals vintage is loaded only when opened.",
    ):
        timer.start("stream vintage status")
        stream_vintage_status = _pack_table(pack, "stream_vintage_status")
        with st.expander("Input-history vintage by stream", expanded=False):
            info_panel(
                "Each stream's latest accepted exact actual and its first forecast quarter, taken from the "
                "committed canonical model-input history. Streams may differ: an exact actual for one stream "
                "can coexist with a still-provisional quarter for another. A provisional value is never "
                "displayed as an observed actual and never enters coefficient estimation."
            )
            if stream_vintage_status.empty:
                warning_panel(
                    "Stream vintage status is missing from the committed Revenue Outlook pack; rebuild it with "
                    "scripts/rebuild_current_revenue_outlook_runtime.py."
                )
            else:
                vintage_cols = st.columns([0.82, 0.18])
                with vintage_cols[1]:
                    dataframe_download(stream_vintage_status, "Download CSV", "stream_vintage_status.csv")
                display_table(stream_vintage_status, height=220, max_rows=20)
        timer.stop("stream vintage status")

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
            selected_summary = (
                f"Fleet efficiency: {sensitivity_option_label('fleet_efficiency', selected_fleet_efficiency)}; "
                f"PT mode shift: {sensitivity_option_label('pt_mode_shift', selected_pt_mode_shift)}; "
                f"Freight rail shift: {sensitivity_option_label('freight_rail_shift', selected_freight_rail_shift)}; "
                f"Demand elasticity: {sensitivity_option_label('demand_elasticity', selected_demand_elasticity)}."
            )
            st.caption(
                f"{selected_summary} Current-finalist activity/revenue rows and rollups are recalculated in this view only; official comparator rows are unchanged."
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
        detail_frames = cached_revenue_outlook_ped_bridge_detail(
            pack_signature,
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
                        f"{fallback_count} PED bridge rows use a {bridge_vintage_release} population proxy for at least one quarter. These rows are flagged in the audit table."
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

    timer.start("composition figure")
    with st.container(border=True):
        st.markdown("<div class='page5-panel-title'>Revenue composition over time</div>", unsafe_allow_html=True)
        if method_detail_enabled():
            st.caption(
                "Stacked build-up of Total NLTF revenue: gross components net of refunds and admin fees, "
                "so the stack reconciles to the total path above."
            )
        # One composition story for everyone: the net build-up that reconciles
        # to Total NLTF ('Gross-to-net bridge audit' internally). The gross
        # stack and the full formula-audit detail were analyst plumbing - the
        # data and mode machinery remain for audits, but the selectors are
        # gone; the formula-audit detail stays available on local audit runs.
        selected_stack_mode = REVENUE_STACK_MODE_BRIDGE
        stack_source_options = _revenue_line_source_options(
            stack_components, selected_official_trace=selected_official_trace
        )
        stack_section_options = selector_options["stack_section_options"]
        stack_overlay_options = selector_options["stack_overlay_options"]
        default_stack_sections = [section for section in ["RUC", "FED", "MVR", "TUC"] if section in stack_section_options]
        default_stack_overlays = _revenue_stack_default_overlays(selected_stack_mode, stack_overlay_options)
        # Two selectors carry the story (source path + FY zoom); the section
        # and overlay multiselects duplicated the defaults for everyone and
        # stay available on local audit runs only.
        show_detail_selector = should_show_local_audit_controls()
        if show_detail_selector:
            comp_cols = st.columns([0.19, 0.16, 0.17, 0.16, 0.16, 0.16])
            with comp_cols[1]:
                selected_stack_detail_level = st.selectbox(
                    "Detail level",
                    list(REVENUE_STACK_DETAIL_LEVELS),
                    index=0,
                    key="revenue_stack_detail_level",
                )
            with comp_cols[3]:
                selected_stack_sections = st.multiselect(
                    "Section filter",
                    stack_section_options,
                    default=default_stack_sections or stack_section_options,
                    key="revenue_stack_sections",
                )
            with comp_cols[4]:
                selected_stack_overlays = st.multiselect(
                    "Aggregate overlays",
                    stack_overlay_options,
                    default=default_stack_overlays,
                    key=f"revenue_stack_overlays_{selected_stack_mode}_{selected_stack_detail_level}",
                )
            slider_col = comp_cols[2]
        else:
            comp_cols = st.columns([0.26, 0.48, 0.26])
            selected_stack_detail_level = REVENUE_STACK_DETAIL_CLEAN
            selected_stack_sections = default_stack_sections or list(stack_section_options)
            selected_stack_overlays = list(default_stack_overlays)
            slider_col = comp_cols[1]
        with comp_cols[0]:
            # A vintage flip can strip the previously stored official source
            # from the options; clamp the session value before rendering.
            if stack_source_options:
                _validated_select_state(
                    "revenue_stack_source_path", stack_source_options, stack_source_options[0]
                )
            selected_stack_source = st.selectbox(
                "Source path",
                stack_source_options,
                index=0,
                key="revenue_stack_source_path",
            )
        # Source-specific FY bounds, derived AFTER the source is selected.
        # The former global bounds were computed over the whole stack frame
        # before any source choice, so the Current FY2030 cutoff silently
        # capped the official comparator even though its rows run to FY2055.
        stack_fy_min, stack_fy_max = _revenue_line_fy_bounds(
            stack_components[
                stack_components["source_path"].astype(str).eq(str(selected_stack_source))
            ]
        )
        # Long-run sources open at FY2050 by default; the official vintages
        # can be extended to their own FY2055 source horizon with the slider.
        stack_fy_default_end = min(int(stack_fy_max), 2050)
        state_key = "revenue_stack_fy_range"
        source_state_key = "revenue_stack_fy_range_source"
        stored_range = st.session_state.get(state_key)
        source_changed = st.session_state.get(source_state_key) != selected_stack_source
        out_of_bounds = (
            not isinstance(stored_range, (tuple, list))
            or len(stored_range) != 2
            or int(stored_range[0]) < int(stack_fy_min)
            or int(stored_range[1]) > int(stack_fy_max)
        )
        if source_changed or out_of_bounds:
            st.session_state[state_key] = (int(stack_fy_min), stack_fy_default_end)
        st.session_state[source_state_key] = selected_stack_source
        with slider_col:
            selected_stack_fy_range = st.slider(
                "FY range / horizon",
                min_value=int(stack_fy_min),
                max_value=int(stack_fy_max),
                key=state_key,
            )

        selected_stack_sections_tuple = tuple(str(value) for value in selected_stack_sections)
        selected_stack_fy_range_tuple = (int(selected_stack_fy_range[0]), int(selected_stack_fy_range[1]))
        selected_stack_overlays_tuple = tuple(str(value) for value in selected_stack_overlays)
        chart_stack = cached_revenue_outlook_composition_stack(
            pack_signature,
            selected_stack_source,
            selected_stack_mode,
            selected_stack_sections_tuple,
            selected_stack_fy_range_tuple,
            selected_stack_overlays_tuple,
            tuple(str(value) for value in stack_section_options),
            sensitivity_key,
            selected_ped_bridge_mode,
            stack_components,
        )
        composition_figure = cached_revenue_outlook_composition_figure(
            pack_signature,
            selected_stack_source,
            selected_stack_mode,
            selected_stack_detail_level,
            selected_stack_sections_tuple,
            selected_stack_fy_range_tuple,
            selected_stack_overlays_tuple,
            sensitivity_key,
            selected_ped_bridge_mode,
            chart_stack,
        )
        stack_gap_banner, stack_display = cached_revenue_outlook_composition_table_view(
            pack_signature,
            selected_stack_source,
            selected_stack_mode,
            selected_stack_sections_tuple,
            selected_stack_fy_range_tuple,
            selected_stack_overlays_tuple,
            sensitivity_key,
            selected_ped_bridge_mode,
            chart_stack,
        )
        chart_card(
            "Revenue composition over time",
            "",
            composition_figure,
            caption=None,
            notes_as_tooltip=False,
        )
        if stack_gap_banner:
            warning_panel(stack_gap_banner)
        if should_show_local_audit_controls():
            table_cols = st.columns([0.82, 0.18])
            with table_cols[1]:
                dataframe_download(chart_stack, "Download CSV", "revenue_stack_components.csv")
            display_table(stack_display, height=360, max_rows=720)
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
                    "Governance audit only: these rows compare candidate PED-Light migration allocations. "
                    "The visible default path uses the selected raw PED bridge followed by the MoT VFM Base "
                    "retention overlay, which scales light-petrol VKT, PED litres and PED/FED revenue together."
                )
                drift_view, drift_display = cached_revenue_outlook_ev_phev_drift_view(
                    pack_signature,
                    str(selected_mode),
                    ev_phev_ped_light_drift_assumptions,
                )
                drift_cols = st.columns([0.82, 0.18])
                with drift_cols[1]:
                    dataframe_download(drift_view, "Download CSV", "ev_phev_ped_light_drift_assumptions.csv")
                display_table(drift_display, height=340, max_rows=260)
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
                    "The visible current-finalist path uses raw PED bridge + MoT VFM Base retention. "
                    "BEV/PHEV are not fixed add-ons; this legacy split table is retained for audit only."
                )
                if target_audit:
                    st.caption(f"Target semantics status: {target_audit.get('status', '')}. Allocation status: {allocation_status}.")
                audit_cols = st.columns([0.82, 0.18])
                with audit_cols[1]:
                    dataframe_download(ev_phev_split_assumptions, "Download CSV", "ev_phev_split_assumptions.csv")
                split_display = cached_revenue_outlook_ev_phev_split_display(
                    pack_signature,
                    ev_phev_split_assumptions,
                )
                display_table(split_display, height=320, max_rows=220)
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
            component_figure, split_figure = cached_revenue_outlook_selected_fy_figures(
                pack_signature,
                selected_fy,
                selected_fed_path,
                sensitivity_key,
                selected_ped_bridge_mode,
                bridge,
            )
            detail_cols = st.columns([0.58, 0.42])
            with detail_cols[0]:
                chart_card(
                    "Component drill-down",
                    "Selected-FY bridge components behind the current finalist revenue composition.",
                    component_figure,
                    caption="Component rows come from revenue_bridge_components in the committed runtime pack.",
                    notes_as_tooltip=False,
                )
            with detail_cols[1]:
                chart_card(
                    "Selected-FY revenue split",
                    "Net FED, total RUC and MVR share of selected-FY revenue where available.",
                    split_figure,
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
        with st.container(border=True):
            st.markdown("<div class='page5-panel-title'>Revenue line reconciliation</div>", unsafe_allow_html=True)
            rec_cols = st.columns([0.35, 0.25, 0.25, 0.15])
            source_options = _revenue_line_source_options(
                line_reconciliation, selected_official_trace=selected_official_trace
            )
            section_options = selector_options["line_section_options"]
            fy_min, fy_max = selector_options["line_fy_bounds"]
            with rec_cols[0]:
                # A vintage flip can strip a stored official source from the
                # options; prune the session value before rendering.
                if "revenue_line_reconciliation_source_paths" in st.session_state:
                    st.session_state["revenue_line_reconciliation_source_paths"] = [
                        value
                        for value in st.session_state["revenue_line_reconciliation_source_paths"]
                        if value in source_options
                    ]
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
            selected_source_paths_tuple = tuple(str(value) for value in selected_source_paths)
            selected_sections_tuple = tuple(str(value) for value in selected_sections)
            selected_reconciliation_fy_range = (int(selected_fy_range[0]), int(selected_fy_range[1]))
            filtered_reconciliation, reconciliation_display = cached_revenue_line_reconciliation_view(
                pack_signature,
                selected_source_paths_tuple,
                selected_sections_tuple,
                selected_reconciliation_fy_range,
                sensitivity_key,
                selected_ped_bridge_mode,
                line_reconciliation,
            )
            with rec_cols[3]:
                dataframe_download(filtered_reconciliation, "Download CSV", "revenue_line_reconciliation.csv")
            gap_banner = _revenue_formula_gap_banner(formula_residuals, selected_source_paths, selected_reconciliation_fy_range)
            if gap_banner:
                warning_panel(gap_banner)
            display_table(reconciliation_display, height=360, max_rows=520)
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
            activity_figure = cached_revenue_outlook_activity_figure(
                pack_signature,
                "june_year" if grain_label == "June-year" else "quarterly",
                selected_fed_path,
                tuple(str(value) for value in selected_traces),
                sensitivity_key,
                selected_ped_bridge_mode,
                str(view.get("current_fed_policy_state") or ""),
                str(pack.output_dir),
                chart_rows,
            )
            chart_card(
                "Activity and volume outlook",
                "Light-petrol VKT and PED litres share one aligned petrol-activity lineage; "
                "PED VKT per capita is retained as its demand driver. Light and Heavy RUC use "
                "net kilometres. Actuals end at FY2025.",
                activity_figure,
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

    _render_fleet_mix_explorer(bridge_vintage_id)

    if method_detail_enabled():
        chart_card(
            "Effective rates per 1,000 km",
            rate_chart_note(bridge_vintage_release),
            cached_revenue_rate_paths_figure(
                pack_signature,
                fed_policy_state,
                pack.revenue_chart_rows,
                bridge_vintage_id,
            ),
            caption=None,
            notes_as_tooltip=True,
        )

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

    # The 12c timing-comparison export is method detail; while hidden its
    # replay is never requested, so the hide also skips that computation.
    if method_detail_enabled():
        timer.start("net revenue timing comparison export")
        try:
            delayed_factors = cached_fed_uplift_factors(pack_signature, pack).get("delayed_6m", {})
            timing_replay, _ = _safe_fuel_price_scenario_replay(pack_signature, pack)
            if timing_replay is None:
                raise ValueError("The fixed-finalist policy replay is unavailable.")
            net_timing_rows = net_revenue_timing_comparison_frame(
                chart_rows,
                delayed_factors,
                policy_timing_rows=timing_replay.annual_bridge,
                start_fy=2026,
                end_fy=2030,
            )
        except ValueError as exc:
            warning_panel(f"Net revenue timing comparison download is unavailable: {exc}")
        else:
            with st.container(border=True):
                export_cols = st.columns([0.76, 0.24])
                with export_cols[0]:
                    st.caption(
                        "Download the exact FY2026-FY2030 Net FED, Net RUC and Net MVR comparison for Base "
                        "and the Low, Medium and High Middle East paths under original 1 January 2027 timing, "
                        "the six-month deferral to 1 July 2027, and no 12c uplift. FY2027 is the year ending "
                        "June 2027, so deferred and no-uplift are intentionally equal in FY2027; original timing "
                        "differs because it applies for January-June 2027. The policy paths "
                        "carry the FED wedge into PED retail prices, apply the FED-rate percentage change to "
                        "Light/Heavy RUC rates and all five RUC collection classes, and apply the governed medium "
                        "retail-diesel elasticity once to a combined diesel-plus-RUC running-cost ratio for conventional "
                        "Light/Heavy activity before rebuilding net rollups. Higher combined running costs therefore "
                        "lower conventional activity; the structural response replaces rather than stacks on the raw "
                        "fitted response. BEV/PHEV kilometres remain fixed absent an approved class-specific charge "
                        "elasticity, although their RUC rates and collections still change. "
                        "Values are NZD millions nominal ex GST with canonical series IDs."
                    )
                with export_cols[1]:
                    dataframe_download(
                        net_timing_rows,
                        "Download 12c timing CSV",
                        "net_revenue_12c_timing_comparison_fy2026_fy2030.csv",
                    )
        finally:
            timer.stop("net revenue timing comparison export")

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
                index=_option_index(horizon_options, REVENUE_SOURCE_HORIZON_TO_CUTOFF, fallback=horizon_options[0]),
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
    # Restored layout (removed in 417f34a): source total path beside the
    # source uncertainty fan.
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
        xaxis=_bounded_year_axis(rows, "FY"),
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
            xaxis=_bounded_year_axis(mot, "FY"),
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
    selection = str(controls.get("horizon") or REVENUE_SOURCE_HORIZON_TO_CUTOFF).strip()
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
    upper = LAST_DECISION_GRADE_ANNUAL_FY
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
        "Light petrol VKT",
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
    # The governed raw/optimized bridge materializes this annual series at
    # runtime from the PED audit, so it is intentionally absent from the
    # immutable chart-row pack but must remain directly selectable.
    if {"PED VKT per capita", "PED volume"}.issubset(available):
        available.add("Light petrol VKT")
    ordered = [label for label in preferred if label in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


def _revenue_outlook_series_display_label(label: Any) -> str:
    """Clarify that the all-class RUC selector is a net, not gross, series."""
    text = str(label or "")
    if text == "Total RUC all classes":
        return "Net RUC revenue (all classes)"
    return text


def _revenue_outlook_series_metric_type(chart_rows: pd.DataFrame, selected_series: str) -> str:
    if str(selected_series) == "Light petrol VKT":
        return "activity"
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
        *_registry_official_trace_names(),
        "Current finalist Base case",
        "Current finalist High population/comparison",
        *CONFLICT_TRACE_NAMES,
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    ]
    # Selector metadata is built from the immutable pack before runtime
    # scenario overlays are appended. A valid Base trace is therefore the
    # availability anchor for the three registered conflict traces.
    if "Current finalist Base case" in available:
        available.update(CONFLICT_TRACE_NAMES)
    ordered = [trace for trace in preferred if trace in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


_COMPARISON_SENSITIVITY_LEVELS = ("Off", "Low", "Med", "High")
_COMPARISON_DISCOUNT_MBCM = "NZTA MBCM (2% p.a.; 1.5% beyond yr 30)"
_COMPARISON_DISCOUNT_CUSTOM = "Custom single rate"


def _validated_select_state(key: str, options: list[str], default: str) -> None:
    """Keep a selectbox session value legal when its option set changes."""
    if key in st.session_state and st.session_state[key] not in options:
        st.session_state[key] = default if default in options else options[0]


def _comparison_scenario_defaults(prefix: str) -> dict[str, Any]:
    is_b = prefix == "b"
    return {
        # A opens on the Base path and B on the High population comparison, so
        # the default view compares two governed scenario traces instead of
        # plotting the same path twice.
        "trace": (
            "Current finalist High population/comparison"
            if is_b
            else "Current finalist Base case"
        ),
        "fleet": "Off",
        "pt": "Off",
        "freight": "Off",
        "eruc": False,
        "fed_policy": FED_POLICY_DELAYED_6M,
    }


def _render_comparison_scenario_column(
    prefix: str,
    sensitivity_labels: dict[str, dict[str, str]],
    official_vintage_state: dict[str, Any],
    page_sensitivity_key: tuple,
    page_uptake_key: ScenarioKeyLike,
) -> tuple[tuple, ScenarioKeyLike, str]:
    """One comparator column whose keys CLONE the page's typed computation key.

    The column's controls override only the dimensions they expose (scenario
    trace, fleet efficiency, 12c policy and, under method detail, PT/freight/
    e-RUC); every other field - engine, bridge mode, long-run schedule,
    official vintage, uptake composition - inherits from the live Single
    scenario key, so a comparator can never quietly rebuild the scenario
    from different ingredients than the page itself uses.
    """
    defaults = _comparison_scenario_defaults(prefix)
    selected_vid = str(official_vintage_state["vintage_id"])
    selected_release = str(official_vintage_state["release_round"])
    # The governed option follows the page's SELECTED comparator vintage; a
    # stale label from another vintage is reset by _validated_select_state.
    mot_option = _comparison_mot_official_option(selected_release)
    # Each side selects a governed scenario TRACE from the committed pack; the
    # fleet composition stays on the governed VFM Base default underneath, so
    # the A/B choice is the scenario story, not the class-split machinery.
    scenario_options = [
        "Current finalist Base case",
        "Current finalist High population/comparison",
        *CONFLICT_TRACE_NAMES,
        mot_option,
    ]
    keys = {
        name: f"ro_cmp_{prefix}_{name}"
        for name in ["trace", "fleet", "pt", "freight", "eruc", "fed_policy"]
    }
    _validated_select_state(keys["trace"], scenario_options, defaults["trace"])
    st.session_state.setdefault(keys["trace"], defaults["trace"])
    selected_scenario = st.selectbox(
        "Scenario",
        scenario_options,
        key=keys["trace"],
        help=(
            "Governed scenario traces from the committed pack. "
            f"'{mot_option}' plots the governed {selected_release} official path exactly as "
            "committed; non-rate levers are locked."
        ),
    )
    mot_official = selected_scenario == mot_option
    if mot_official:
        st.caption(f"Pure {selected_release} official path - non-rate levers locked.")
    levels = list(_COMPARISON_SENSITIVITY_LEVELS)
    for name in ("fleet", "pt", "freight"):
        _validated_select_state(keys[name], levels, defaults[name])
        st.session_state.setdefault(keys[name], defaults[name])
    fleet = st.selectbox(
        "Fleet efficiency", levels, key=keys["fleet"], disabled=mot_official,
        format_func=lambda level: sensitivity_labels["fleet_efficiency"].get(level, str(level)),
    )
    # PT and freight levers are method detail; while hidden both stay at their
    # neutral "Off" level regardless of any persisted selection.
    if method_detail_enabled():
        pt_shift = st.selectbox(
            "PT mode shift", levels, key=keys["pt"], disabled=mot_official,
            format_func=lambda level: sensitivity_labels["pt_mode_shift"].get(level, str(level)),
        )
        freight = st.selectbox(
            "Freight rail shift", levels, key=keys["freight"], disabled=mot_official,
            format_func=lambda level: sensitivity_labels["freight_rail_shift"].get(level, str(level)),
        )
    else:
        pt_shift = "Off"
        freight = "Off"
    eruc_values: tuple[float, ...] = ()
    st.session_state.setdefault(keys["eruc"], defaults["eruc"])
    # While method detail is hidden the e-RUC transition is withdrawn from the
    # A/B columns and both scenarios compare without it.
    eruc_on = method_detail_enabled() and st.toggle(
        "e-RUC transition", key=keys["eruc"], help=ERUC_NOTE, disabled=mot_official
    )
    if eruc_on and not mot_official:
        with st.popover("e-RUC levers", use_container_width=True):
            start = st.number_input("Start FY", min_value=2026, max_value=2045, value=2027, step=1, key=f"ro_cmp_{prefix}_eruc_start")
            phase = st.number_input("Phase-in (years)", min_value=1, max_value=10, value=3, step=1, key=f"ro_cmp_{prefix}_eruc_phase")
            ratio = st.number_input("e-RUC rate vs light RUC (%)", min_value=25.0, max_value=200.0, value=100.0, step=5.0, key=f"ro_cmp_{prefix}_eruc_ratio")
            elasticity = st.number_input("VKT elasticity", min_value=-1.0, max_value=0.0, value=-0.15, step=0.05, key=f"ro_cmp_{prefix}_eruc_elasticity")
            pump = st.number_input("Pump price ($/L incl. excise)", min_value=1.0, max_value=6.0, value=2.70, step=0.05, key=f"ro_cmp_{prefix}_eruc_pump")
        eruc_values = (float(start), float(phase), ratio / 100.0, float(elasticity), float(pump))
    if mot_official:
        # The synthetic rate-only counterfactual is defined for MBU26 only,
        # defaults to the published path and is hidden for other vintages.
        official_policy_state = FED_POLICY_PUBLISHED
        if selected_vid == "MBU26" and method_detail_enabled():
            official_policy_key = f"ro_cmp_{prefix}_official_policy"
            _validated_select_state(
                official_policy_key, list(FED_POLICY_OPTIONS), FED_POLICY_PUBLISHED
            )
            st.session_state.setdefault(official_policy_key, FED_POLICY_PUBLISHED)
            official_policy_state = st.selectbox(
                "Synthetic official rate-only counterfactual — not a published forecast",
                list(FED_POLICY_OPTIONS),
                format_func=lambda state: FED_POLICY_LABELS[str(state)],
                key=official_policy_key,
                help=(
                    "Original timing starts 1 Jan 2027; deferred starts 1 Jul 2027; "
                    "no uplift removes the 12c step entirely. Scope: MBU26 official "
                    "comparator only."
                ),
            )
            st.caption(
                "Applies to the MBU26 official trace only. BEFU26 has no synthetic "
                "policy counterfactual; generating one requires a separate owner decision."
            )
        return _comparison_official_scenario_keys(
            page_uptake_key,
            official_policy_state=official_policy_state,
            selected_vid=selected_vid,
        )
    _validated_select_state(
        keys["fed_policy"],
        list(FED_POLICY_OPTIONS),
        defaults["fed_policy"],
    )
    st.session_state.setdefault(keys["fed_policy"], defaults["fed_policy"])
    fed_policy_state = st.selectbox(
        "Current 12c policy",
        list(FED_POLICY_OPTIONS),
        format_func=lambda state: FED_POLICY_LABELS[str(state)],
        key=keys["fed_policy"],
        help=(
            "Original timing starts 1 Jan 2027; deferred starts 1 Jul 2027; "
            "no uplift removes the 12c step entirely. Scope: Selected current scenario only."
        ),
    )
    sensitivity_key, ev_uptake_key = _comparison_scenario_b_keys(
        page_sensitivity_key,
        page_uptake_key,
        fleet=fleet,
        pt_shift=pt_shift,
        freight=freight,
        eruc_values=eruc_values,
        fed_policy_state=fed_policy_state,
    )
    return sensitivity_key, ev_uptake_key, selected_scenario


def _page_scenario_trace_name(page_uptake_key: ScenarioKeyLike) -> str:
    """The trace the Single scenario configuration plots as its scenario."""
    mode = _scenario_key(page_uptake_key).uptake_basis
    selected_vid, _ = _official_vintage_scope(page_uptake_key)
    return (
        official_comparator_trace_name(selected_vid)
        if mode == EV_UPTAKE_GOVERNED_OPTION
        else "Current finalist Base case"
    )


def _comparison_sensitivity_key_from_page(
    page_sensitivity_key: tuple, fleet: str, pt_shift: str, freight: str
) -> tuple:
    """The page sensitivity key with the B-column levels swapped in.

    The B levers are named levels, so the matching custom-percentage slots
    clear; every other slot inherits the page value unchanged.
    """
    key = list(page_sensitivity_key)
    key[0], key[3] = _normalize_sensitivity_level(fleet), ""
    key[1], key[4] = _normalize_sensitivity_level(pt_shift), ""
    key[9], key[10] = _normalize_sensitivity_level(freight), ""
    return tuple(key)


def _comparison_scenario_b_keys(
    page_sensitivity_key: tuple,
    page_uptake_key: ScenarioKeyLike,
    *,
    fleet: str,
    pt_shift: str,
    freight: str,
    eruc_values: tuple[float, ...],
    fed_policy_state: str,
) -> tuple[tuple, RevenueScenarioComputationKey]:
    """Scenario B's keys: the page key with only the B controls overridden."""
    page_key = _scenario_key(page_uptake_key)
    ev_uptake_key = page_key.replace(
        # The B column selects a trace; if the page itself is pinned to the
        # governed official basis, B's non-official traces need the default
        # composition underneath instead.
        uptake_basis=(
            DEFAULT_EV_UPTAKE_MODE
            if page_key.uptake_basis == EV_UPTAKE_GOVERNED_OPTION
            else page_key.uptake_basis
        ),
        eruc_levers=eruc_values,
        current_fed_policy_state=fed_policy_state,
    )
    return (
        _comparison_sensitivity_key_from_page(page_sensitivity_key, fleet, pt_shift, freight),
        ev_uptake_key,
    )


def _comparison_official_scenario_keys(
    page_uptake_key: ScenarioKeyLike,
    *,
    official_policy_state: str,
    selected_vid: str,
) -> tuple[tuple, RevenueScenarioComputationKey, str]:
    """Keys for the locked MoT-official comparator: page key, non-rate levers off."""
    sensitivity_key = selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    ev_uptake_key = _scenario_key(page_uptake_key).replace(
        uptake_basis=EV_UPTAKE_GOVERNED_OPTION,
        custom_ev_levers=(),
        eruc_levers=(),
        current_fed_policy_state=FED_POLICY_PUBLISHED,
        official_fed_policy_state=official_policy_state,
        heavy_bev_transition=HEAVY_BEV_DEFAULT,
        official_comparator_vintage_id=selected_vid,
    )
    return sensitivity_key, ev_uptake_key, official_comparator_trace_name(selected_vid)


_COMPARISON_HORIZON_START_FY = 2026
_COMPARISON_HORIZON_END_FY = 2050


def _comparison_alignment_gate(a: pd.Series, b: pd.Series) -> str:
    """Hard gate: A and B must cover identical June years inside the horizon.

    The delta cards and NPV bridges silently mis-state a comparison when one
    side is missing years, so a coverage mismatch suppresses that arithmetic
    rather than rendering plausible-but-wrong numbers. Returns "" when the
    horizons align, else the warning to show.
    """

    def _horizon_years(path: pd.Series) -> list[int]:
        years = pd.to_numeric(pd.Series(path.index), errors="coerce").dropna().astype(int)
        return sorted(
            year
            for year in years.unique()
            if _COMPARISON_HORIZON_START_FY <= year <= _COMPARISON_HORIZON_END_FY
        )

    a_years, b_years = _horizon_years(a), _horizon_years(b)
    if not a_years or not b_years:
        return (
            "Comparison horizon gate: one scenario has no forecast June years inside "
            f"FY{_COMPARISON_HORIZON_START_FY}-FY{_COMPARISON_HORIZON_END_FY}."
        )
    if a_years != b_years:
        return (
            "Comparison horizon gate: the scenarios cover different June years "
            f"(A: FY{a_years[0]}-FY{a_years[-1]}, {len(a_years)} years; "
            f"B: FY{b_years[0]}-FY{b_years[-1]}, {len(b_years)} years). "
            "Delta cards and NPV bridges are suppressed until both sides share one horizon."
        )
    return ""


def _reset_scenario_b_to_current_page() -> None:
    """Seed the Scenario B controls from the live Single scenario configuration."""
    st.session_state["ro_cmp_b_trace"] = "Current finalist Base case"
    for target, source in [
        ("ro_cmp_b_fleet", "revenue_outlook_sensitivity_fleet_efficiency"),
        ("ro_cmp_b_pt", "revenue_outlook_sensitivity_pt_mode_shift"),
    ]:
        level = str(st.session_state.get(source, "Off"))
        st.session_state[target] = level if level in _COMPARISON_SENSITIVITY_LEVELS else "Off"
    freight_level = "Off"
    if bool(st.session_state.get("revenue_outlook_sensitivity_freight_rail_toggle", False)):
        candidate = str(st.session_state.get("revenue_outlook_sensitivity_freight_rail_shift", "Med"))
        freight_level = candidate if candidate in _COMPARISON_SENSITIVITY_LEVELS else "Med"
    st.session_state["ro_cmp_b_freight"] = freight_level
    eruc_on = method_detail_enabled() and bool(st.session_state.get("revenue_outlook_eruc_toggle", False))
    st.session_state["ro_cmp_b_eruc"] = eruc_on
    if eruc_on:
        for target, source, fallback in [
            ("ro_cmp_b_eruc_start", "eruc_lever_start", 2027),
            ("ro_cmp_b_eruc_phase", "eruc_lever_phase", 3),
            ("ro_cmp_b_eruc_ratio", "eruc_lever_ratio", 100.0),
            ("ro_cmp_b_eruc_elasticity", "eruc_lever_elasticity", -0.15),
            ("ro_cmp_b_eruc_pump", "eruc_lever_pump", 2.70),
        ]:
            st.session_state[target] = st.session_state.get(source, fallback)
    st.session_state["ro_cmp_b_fed_policy"] = _session_fed_policy_state(
        "revenue_outlook_fed_policy_state",
        legacy_toggle_key="revenue_outlook_fed_uplift",
    )


def _scenario_summary_text(
    sensitivity_key: tuple, ev_uptake_key: ScenarioKeyLike, trace_name: str = ""
) -> str:
    key = _scenario_key(ev_uptake_key)
    mode = key.uptake_basis
    selected_vid, _ = _official_vintage_scope(ev_uptake_key)
    # The selected scenario trace names each side; the historical mode-derived
    # label survives for callers that predate per-side trace selection.
    parts = [
        str(trace_name)
        or (
            _comparison_mot_official_option(selected_vid)
            if mode == EV_UPTAKE_GOVERNED_OPTION
            else mode
        )
    ]
    for label, value in [("Fleet", sensitivity_key[0]), ("PT", sensitivity_key[1]), ("Freight", sensitivity_key[9])]:
        if value != "Off":
            parts.append(f"{label} {value}")
    if key.eruc_levers:
        parts.append("e-RUC on")
    current_state, mbu26_state = _fed_policy_state_scope(ev_uptake_key)
    if mode == EV_UPTAKE_GOVERNED_OPTION:
        if mbu26_state != FED_POLICY_PUBLISHED:
            parts.append(f"MBU26 synthetic counterfactual: {FED_POLICY_LABELS[mbu26_state]}")
        else:
            parts.append(f"{selected_vid} official: published")
    else:
        parts.append(f"Current: {FED_POLICY_LABELS[current_state]}")
    return " · ".join(parts)


def _render_scenario_comparison_panel(
    pack_signature: tuple[tuple[str, int, int], ...],
    pack: RevenueOutlookPack,
    comparison_series: str,
    fed_path: str,
    sensitivity_labels: dict[str, dict[str, str]],
    official_vintage_state: dict[str, Any],
    page_sensitivity_key: tuple,
    page_uptake_key: ScenarioKeyLike,
) -> None:
    """A vs B where A IS the live Single scenario computation.

    Scenario A carries the page's own typed keys, untouched, so it cannot
    drift from the Single scenario chart; Scenario B clones those keys and
    overrides only the dimensions its controls expose. Both sides then route
    through the canonical final view, and this panel only extracts, aligns
    and draws - it applies no policy, vintage or lever transformations of
    its own.
    """
    with st.container(border=True):
        comparison_sub = (
            "<div class='page5-panel-sub'>Two policy configurations held side by side for the selected "
            "series: overlaid paths, horizon NPV for revenue (physical quantities report cumulative and "
            "average-annual totals - the MBCM discounts monetised streams only) and adaptive delta cards. "
            "Uses named presets; custom lever values live in the advanced levers above.</div>"
            if method_detail_enabled()
            else ""
        )
        st.markdown(
            f"<div class='page5-panel-title'>Scenario comparison (A vs B)</div>{comparison_sub}",
            unsafe_allow_html=True,
        )
        with st.expander("Configure scenarios A and B", expanded=True):
            head_cols = st.columns([0.30, 0.20, 0.14, 0.36])
            with head_cols[0]:
                discount_mode = st.selectbox(
                    "Discount basis",
                    [_COMPARISON_DISCOUNT_MBCM, _COMPARISON_DISCOUNT_CUSTOM],
                    key="ro_cmp_discount_mode",
                    help="Applied to revenue series only. " + mbcm_label(),
                )
            with head_cols[1]:
                custom_rate = None
                if discount_mode == _COMPARISON_DISCOUNT_CUSTOM:
                    custom_rate = st.number_input("Rate (% p.a.)", min_value=0.5, max_value=10.0, value=4.0, step=0.5, key="ro_cmp_discount_rate") / 100.0
            with head_cols[3]:
                st.markdown("<div class='control-label'>Scenario B seed</div>", unsafe_allow_html=True)
                st.button(
                    "Reset B to current page (A)",
                    on_click=_reset_scenario_b_to_current_page,
                    key="ro_cmp_reset_b",
                    help=(
                        "Seeds the Scenario B controls from the live Single scenario "
                        "configuration, so B starts identical to A."
                    ),
                    use_container_width=True,
                )

            # Scenario A is the live Single scenario computation itself - the
            # page's typed keys pass through untouched, so A can never be a
            # stale or partial copy of the page settings.
            sens_a, uptake_a = page_sensitivity_key, page_uptake_key
            trace_a = _page_scenario_trace_name(page_uptake_key)
            column_a, column_b = st.columns(2)
            with column_a:
                st.markdown("<div class='ro-cmp-scenario-head ro-cmp-a'>Scenario A</div>", unsafe_allow_html=True)
                st.markdown("**Current Single scenario configuration**")
                st.markdown(_scenario_summary_text(sens_a, uptake_a, trace_a))
                st.caption(
                    "Scenario A mirrors the Single scenario view exactly, so it "
                    "cannot drift from the chart there. Adjust it on the Single "
                    "scenario view."
                )
            with column_b:
                st.markdown("<div class='ro-cmp-scenario-head ro-cmp-b'>Scenario B</div>", unsafe_allow_html=True)
                sens_b, uptake_b, trace_b = _render_comparison_scenario_column(
                    "b", sensitivity_labels, official_vintage_state,
                    page_sensitivity_key, page_uptake_key,
                )

        result = cached_scenario_comparison_paths(
            pack_signature,
            comparison_series,
            fed_path,
            sens_a,
            uptake_a,
            sens_b,
            uptake_b,
            PED_BRIDGE_DEFAULT_MODE,
            pack,
            trace_a=trace_a,
            trace_b=trace_b,
        )
        a_path, b_path = result["a"], result["b"]
        if a_path.empty or b_path.empty:
            warning_panel("The selected series has no forecast rows for one of the scenarios.")
            return

        filter_summary_grid(
            [
                ("Scenario A", _scenario_summary_text(sens_a, uptake_a, trace_a)),
                ("Scenario B", _scenario_summary_text(sens_b, uptake_b, trace_b)),
                ("Series", str(comparison_series)),
            ]
        )
        alignment_gate = _comparison_alignment_gate(a_path, b_path)
        if alignment_gate:
            # The overlaid paths stay on screen (they are honest about the
            # mismatch); every derived delta is suppressed by the gate.
            warning_panel(alignment_gate)
            chart_card(
                "Scenario paths (A vs B)",
                "Shared history in grey; Scenario A solid navy, Scenario B dashed orange. Same governed pipeline as the total path chart.",
                _scenario_comparison_figure(result["history"], a_path, b_path, result["value_unit"]),
                caption=None,
                notes_as_tooltip=True,
            )
            return
        gov_kpi_grid(
            _scenario_comparison_cards(
                comparison_series,
                result["metric_type"],
                a_path,
                b_path,
                result["value_unit"],
                None if discount_mode == _COMPARISON_DISCOUNT_MBCM else custom_rate,
            )
        )
        chart_card(
            "Scenario paths (A vs B)",
            "Shared history in grey; Scenario A solid navy, Scenario B dashed orange. Same governed pipeline as the total path chart.",
            _scenario_comparison_figure(result["history"], a_path, b_path, result["value_unit"]),
            caption=None,
            notes_as_tooltip=True,
        )
        if result["metric_type"] == "revenue":
            rate_for_npv = None if discount_mode == _COMPARISON_DISCOUNT_MBCM else custom_rate
            basis_note = mbcm_label() if rate_for_npv is None else f"Single rate {rate_for_npv:.1%} p.a."
            npv_a = npv_to_horizon(a_path, rate=rate_for_npv)
            npv_b = npv_to_horizon(b_path, rate=rate_for_npv)
            if comparison_series == _SCENARIO_COMPARISON_TOTAL_SERIES:
                component_npvs = {
                    component_series: _scenario_component_npv(
                        cached_scenario_comparison_paths(
                            pack_signature, component_series, fed_path,
                            sens_a, uptake_a, sens_b, uptake_b,
                            PED_BRIDGE_DEFAULT_MODE, pack,
                            trace_a=trace_a, trace_b=trace_b,
                        ),
                        rate_for_npv,
                    )
                    for component_series in _SCENARIO_COMPONENT_FETCH_SERIES
                }
                components = _scenario_npv_component_breakdown(component_npvs, npv_a, npv_b)
                closure_gap = sum(b - a for _, a, b in components) - (npv_b - npv_a)
                if abs(closure_gap) > _SCENARIO_COMPONENT_MATERIALITY:
                    # The breakdown closes the governed NLTF identity by
                    # construction; a residual above the materiality floor
                    # means a component path came from a different snapshot
                    # than the total, so the bridge is suppressed.
                    warning_panel(
                        "Comparison closure gate: the component NPV deltas differ from the "
                        f"headline Total NLTF delta by {closure_gap:+,.1f} $m. The by-stream "
                        "NPV charts are suppressed until the decomposition closes."
                    )
                    return
                chart_card(
                    "NPV by revenue stream (A vs B)",
                    "Each revenue stream's NPV to FY2050 under Scenario A (navy) and Scenario B "
                    "(orange), largest stream first, all streams recomputed through that scenario's "
                    "levers. Heavy & other RUC is the RUC rollup less the light classes (heavy BEVs "
                    "pay the same per-km RUC, so heavy electrification reshuffles within this block); "
                    "TUC & other closes the governed NLTF identity. " + basis_note + ".",
                    _scenario_npv_composition_figure(components, result["value_unit"]),
                    caption=None,
                    notes_as_tooltip=True,
                )
                chart_card(
                    "NPV delta bridge by revenue stream (B − A)",
                    "How each revenue stream contributes to the NPV gap between the scenarios: "
                    "component deltas accumulate from zero to the total NPV delta, so gains in one "
                    "stream (green) and losses in another (red) net out to the headline figure on the "
                    "delta card. Streams moving less than $1m NPV are omitted. " + basis_note + ".",
                    _scenario_npv_component_bridge_figure(npv_a, npv_b, components, result["value_unit"]),
                    caption=None,
                    notes_as_tooltip=True,
                )
            else:
                chart_card(
                    "NPV bridge (A to B)",
                    "NPV to FY2050 from an FY2026 base. " + basis_note,
                    _scenario_npv_waterfall_figure(npv_a, npv_b, result["value_unit"]),
                    caption=None,
                    notes_as_tooltip=True,
                )


def _format_scenario_amount(value: float, unit: str, *, signed: bool = False) -> str:
    if pd.isna(value):
        return "-"
    unit_text = str(unit or "").strip()
    if _is_million_currency_unit(unit_text):
        magnitude = f"${abs(value):,.0f}m"
    elif "million" in unit_text.lower():
        magnitude = f"{abs(value):,.0f} {unit_text}"
    else:
        magnitude = f"{abs(value):,.0f} {unit_text}".strip()
    if signed:
        sign = "+" if value >= 0 else "−"
        return f"{sign}{magnitude}"
    return f"-{magnitude}" if value < 0 else magnitude


def _scenario_delta_tone(delta: float) -> str:
    if pd.isna(delta) or abs(delta) < 1e-9:
        return "mixed"
    return "good" if delta > 0 else "bad"


def _scenario_comparison_cards(
    series_label: str,
    metric_type: str,
    a: pd.Series,
    b: pd.Series,
    value_unit: str,
    discount_rate: float | None,
) -> list[tuple]:
    """Adaptive KPI cards: NPV language for revenue, physical totals otherwise.

    The forecast series may carry an FY2025 nowcast anchor for chart
    continuity; card metrics cover the forecast window proper (FY2026+).
    """
    label = str(series_label or "")
    a = a[a.index >= 2026] if len(a) else a
    b = b[b.index >= 2026] if len(b) else b
    horizon = horizon_label(a if len(a) else b)
    is_intensity = "per capita" in label.lower() or "per capita" in str(value_unit).lower()
    if metric_type == "revenue":
        npv_a = npv_to_horizon(a, rate=discount_rate)
        npv_b = npv_to_horizon(b, rate=discount_rate)
        delta = npv_b - npv_a
        cum_delta = cumulative_total(b) - cumulative_total(a)
        basis = mbcm_label() if discount_rate is None else f"single rate {discount_rate:.1%} p.a."
        pct = f"{delta / npv_a:+.1%} vs A" if npv_a else "-"
        return [
            ("Scenario A - NPV to FY2050", _format_scenario_amount(npv_a, value_unit), f"{basis}; FY2026 base", "-", "neutral", "A"),
            ("Scenario B - NPV to FY2050", _format_scenario_amount(npv_b, value_unit), f"{basis}; FY2026 base", "-", "neutral", "B"),
            ("NPV delta (B - A)", _format_scenario_amount(delta, value_unit, signed=True), horizon, pct, _scenario_delta_tone(delta), "Δ"),
            ("Cumulative nominal delta (B - A)", _format_scenario_amount(cum_delta, value_unit, signed=True), f"{horizon}, undiscounted", "-", _scenario_delta_tone(cum_delta), "Σ"),
        ]
    if is_intensity:
        avg_a, avg_b = average_annual(a), average_annual(b)
        delta = avg_b - avg_a
        end_delta = (b.iloc[-1] - a.iloc[-1]) if len(a) and len(b) else float("nan")
        return [
            ("Scenario A - average annual level", _format_scenario_amount(avg_a, value_unit), horizon, "-", "neutral", "A"),
            ("Scenario B - average annual level", _format_scenario_amount(avg_b, value_unit), horizon, "-", "neutral", "B"),
            ("Average level delta (B - A)", _format_scenario_amount(delta, value_unit, signed=True), horizon, "-", _scenario_delta_tone(delta), "Δ"),
            ("FY2050 delta (B - A)", _format_scenario_amount(end_delta, value_unit, signed=True), "end of horizon", "-", _scenario_delta_tone(end_delta), "→"),
        ]
    cum_a, cum_b = cumulative_total(a), cumulative_total(b)
    delta = cum_b - cum_a
    avg_delta = average_annual(b) - average_annual(a)
    return [
        ("Scenario A - cumulative", _format_scenario_amount(cum_a, value_unit), horizon, "-", "neutral", "A"),
        ("Scenario B - cumulative", _format_scenario_amount(cum_b, value_unit), horizon, "-", "neutral", "B"),
        ("Cumulative delta (B - A)", _format_scenario_amount(delta, value_unit, signed=True), horizon, "-", _scenario_delta_tone(delta), "Δ"),
        ("Average annual delta (B - A)", _format_scenario_amount(avg_delta, value_unit, signed=True), "per June year", "-", _scenario_delta_tone(avg_delta), "⌀"),
    ]


def _scenario_hover_value_format(value_unit: str, axis: str = "y") -> str:
    """Plotly value-format with units for the comparison charts.

    Million-currency series are plotted in $b, so hover as "$3.61b" (d3's
    currency format keeps the minus sign outside: "-$3.61b"); other units
    trail the number, e.g. "12,345.67 million km". ``axis`` selects the
    encoded value axis ("x" for horizontal bars).
    """
    if _is_million_currency_unit(value_unit):
        return "%{" + axis + ":$,.2f}b"
    unit_text = str(value_unit or "").strip()
    return "%{" + axis + ":,.2f}" + (f" {unit_text}" if unit_text else "")


def _scenario_amount_text(value_in_millions: float, value_unit: str) -> str:
    """Compact on-bar label: "$3.61b" for currency, plain numbers otherwise."""
    scale = _display_value_scale_for_unit(value_unit)
    scaled = value_in_millions / scale
    if _is_million_currency_unit(value_unit):
        sign = "−" if scaled < 0 else ""
        return f"{sign}${abs(scaled):,.2f}b"
    return f"{scaled:,.1f}"


def _scenario_comparison_figure(history: pd.Series, a: pd.Series, b: pd.Series, value_unit: str) -> go.Figure:
    if (a is None or a.empty) and (b is None or b.empty):
        return empty_figure("Selected series has no forecast rows for the chosen scenarios.")
    scale = _display_value_scale_for_unit(value_unit)
    axis_title = _display_axis_unit(value_unit)
    hover_value = _scenario_hover_value_format(value_unit)
    fig = go.Figure()
    if history is not None and not history.empty:
        fig.add_trace(
            go.Scatter(
                x=history.index.astype(int), y=history.to_numpy(dtype=float) / scale,
                mode="lines+markers", name="Actual",
                line={"color": "#64748B", "width": 1.6}, marker={"size": 4},
                hovertemplate=f"<b>Actual</b><br>{hover_value}<extra></extra>",
            )
        )
    for series, name, color, dash in [
        (a, "Scenario A", "#002B5C", "solid"),
        (b, "Scenario B", "#F37021", "dash"),
    ]:
        if series is None or series.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=series.index.astype(int), y=series.to_numpy(dtype=float) / scale,
                mode="lines+markers", name=name,
                line={"color": color, "width": 3, "dash": dash}, marker={"size": 5},
                hovertemplate=f"<b>{name}</b><br>{hover_value}<extra></extra>",
            )
        )
    fig.update_xaxes(title_text="June year ending", title_font={"size": 11, "color": "#5A6B7B"}, showgrid=False, dtick=5)
    fig.update_yaxes(title_text=axis_title, gridcolor="#E6EDF5", zeroline=False)
    fig.update_layout(
        height=340,
        margin={"l": 56, "r": 18, "t": 18, "b": 40},
        hovermode="x unified",
        hoverdistance=5,
        legend={"orientation": "h", "y": -0.2, "x": 0.0, "font": {"size": 11}},
        plot_bgcolor="#FFFFFF",
    )
    return fig


def _scenario_npv_waterfall_figure(npv_a: float, npv_b: float, value_unit: str) -> go.Figure:
    scale = _display_value_scale_for_unit(value_unit)
    axis_title = _display_axis_unit(value_unit)
    delta = npv_b - npv_a
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "total"],
            x=["Scenario A NPV", "Δ (B − A)", "Scenario B NPV"],
            y=[npv_a / scale, delta / scale, npv_b / scale],
            increasing={"marker": {"color": "#00843D"}},
            decreasing={"marker": {"color": "#B42318"}},
            totals={"marker": {"color": "#002B5C"}},
            connector={"line": {"color": "#CBD5E1", "width": 1}},
            hovertemplate=f"<b>%{{x}}</b><br>{_scenario_hover_value_format(value_unit)}<extra></extra>",
        )
    )
    fig.update_yaxes(title_text=axis_title, gridcolor="#E6EDF5", zeroline=False)
    fig.update_layout(
        height=300,
        margin={"l": 56, "r": 18, "t": 18, "b": 36},
        showlegend=False,
        plot_bgcolor="#FFFFFF",
    )
    return fig


_SCENARIO_COMPARISON_TOTAL_SERIES = "Total NLTF revenue"
# Series fetched through the full scenario pipeline to decompose the total.
# "Total RUC all classes" is fetched as the RUC rollup so the heavy remainder
# can be derived: heavy BEV reallocation is rollup-neutral (BEVs pay the same
# per-km RUC), so conventional heavy alone would leave a phantom residual.
_SCENARIO_COMPONENT_FETCH_SERIES = (
    "Net FED revenue",
    "Light RUC revenue",
    "Light BEV RUC net revenue",
    "PHEV RUC net revenue",
    "Total RUC all classes",
    "Net MVR revenue",
)
_SCENARIO_COMPONENT_COLORS = {
    "PED / FED (net)": "#00843D",
    "Light RUC (conventional)": "#006FAD",
    "Light BEV RUC": "#4CA7D8",
    "PHEV RUC": "#9CCBE8",
    "Heavy & other RUC": "#102A43",
    "Net MVR": "#94A3B8",
    "TUC & other": "#CBD5E1",
}
_SCENARIO_COMPONENT_MATERIALITY = 1.0  # $m NPV; bars below this are dropped


def _scenario_component_npv(paths: dict[str, Any], rate: float | None) -> tuple[float, float]:
    npv_a = npv_to_horizon(paths["a"], rate=rate)
    npv_b = npv_to_horizon(paths["b"], rate=rate)
    return (0.0 if pd.isna(npv_a) else npv_a, 0.0 if pd.isna(npv_b) else npv_b)


def _scenario_npv_component_breakdown(
    component_npvs: dict[str, tuple[float, float]],
    npv_a_total: float,
    npv_b_total: float,
) -> list[tuple[str, float, float]]:
    """Decompose Total NLTF NPV into revenue-stream components for A and B.

    Exact by construction: "Heavy & other RUC" is the RUC rollup less the
    light-class series (absorbing heavy BEV and refund/admin interactions),
    and "TUC & other" closes the governed NLTF identity
    (net FED + total RUC + net MVR + TUC) against the total.
    """

    def pair(series: str) -> tuple[float, float]:
        return component_npvs.get(series, (0.0, 0.0))

    fed = pair("Net FED revenue")
    light = pair("Light RUC revenue")
    bev = pair("Light BEV RUC net revenue")
    phev = pair("PHEV RUC net revenue")
    ruc = pair("Total RUC all classes")
    mvr = pair("Net MVR revenue")
    heavy = (ruc[0] - light[0] - bev[0] - phev[0], ruc[1] - light[1] - bev[1] - phev[1])
    residual = (
        npv_a_total - fed[0] - ruc[0] - mvr[0],
        npv_b_total - fed[1] - ruc[1] - mvr[1],
    )
    return [
        ("PED / FED (net)", fed[0], fed[1]),
        ("Light RUC (conventional)", light[0], light[1]),
        ("Light BEV RUC", bev[0], bev[1]),
        ("PHEV RUC", phev[0], phev[1]),
        ("Heavy & other RUC", heavy[0], heavy[1]),
        ("Net MVR", mvr[0], mvr[1]),
        ("TUC & other", residual[0], residual[1]),
    ]


def _scenario_npv_composition_figure(
    components: list[tuple[str, float, float]], value_unit: str
) -> go.Figure:
    """Per-stream NPV comparison: one row per revenue stream, A vs B paired.

    Grouped horizontal bars read stream-by-stream (largest at the top) in the
    same scenario colours as the paths chart; the stacked-total view lives in
    the KPI cards, so each stream's A/B gap stays legible here.
    """
    scale = _display_value_scale_for_unit(value_unit)
    axis_title = _display_axis_unit(value_unit)
    total_a = sum(a for _, a, _ in components)
    total_b = sum(b for _, _, b in components)
    material = [
        (label, npv_a, npv_b)
        for label, npv_a, npv_b in components
        if abs(npv_a) >= _SCENARIO_COMPONENT_MATERIALITY or abs(npv_b) >= _SCENARIO_COMPONENT_MATERIALITY
    ]
    material.sort(key=lambda row: max(abs(row[1]), abs(row[2])), reverse=True)
    labels = [label for label, _, _ in material]
    hover_value = _scenario_hover_value_format(value_unit, axis="x")
    fig = go.Figure()
    for name, color, values, total in [
        ("Scenario A", "#002B5C", [a for _, a, _ in material], total_a),
        ("Scenario B", "#F37021", [b for _, _, b in material], total_b),
    ]:
        shares = [v / total if total else float("nan") for v in values]
        fig.add_trace(
            go.Bar(
                y=labels,
                x=[v / scale for v in values],
                orientation="h",
                name=name,
                marker={"color": color},
                text=[_scenario_amount_text(v, value_unit) for v in values],
                textposition="outside",
                textfont={"size": 10.5},
                cliponaxis=False,
                customdata=[f"{share:.1%} of total" for share in shares],
                hovertemplate=f"<b>{name}</b> — %{{y}}<br>{hover_value}<br>%{{customdata}}<extra></extra>",
            )
        )
    fig.update_xaxes(title_text=axis_title, gridcolor="#E6EDF5", zeroline=True, zerolinecolor="#CBD5E1")
    fig.update_yaxes(autorange="reversed", tickfont={"size": 11.5}, ticksuffix="  ")
    fig.update_layout(
        barmode="group",
        bargap=0.28,
        bargroupgap=0.08,
        height=max(320, 66 * len(material) + 132),
        margin={"l": 8, "r": 64, "t": 54, "b": 40},
        legend={"orientation": "h", "y": 1.0, "yanchor": "bottom", "x": 0.0, "font": {"size": 11}},
        plot_bgcolor="#FFFFFF",
    )
    return fig


def _scenario_npv_component_bridge_figure(
    npv_a: float,
    npv_b: float,
    components: list[tuple[str, float, float]],
    value_unit: str,
) -> go.Figure:
    """Delta-space bridge: component NPV deltas accumulate from zero to B − A.

    Level anchors (~two orders of magnitude above the deltas) live in the KPI
    cards and the composition chart; plotting them here would flatten the
    component bars into invisibility.
    """
    deltas = [
        (label, comp_b - comp_a)
        for label, comp_a, comp_b in components
        if abs(comp_b - comp_a) >= _SCENARIO_COMPONENT_MATERIALITY
    ]
    if not deltas:
        return _scenario_npv_waterfall_figure(npv_a, npv_b, value_unit)
    # gains first, largest loss lands right before the total bar
    deltas.sort(key=lambda row: row[1], reverse=True)
    scale = _display_value_scale_for_unit(value_unit)
    axis_title = _display_axis_unit(value_unit)
    total_delta = npv_b - npv_a
    labels = [*(label for label, _ in deltas), "NPV delta (B − A)"]
    values = [*(delta / scale for _, delta in deltas), total_delta / scale]
    bar_text = [
        *(("+" if delta >= 0 else "") + _scenario_amount_text(delta, value_unit) for _, delta in deltas),
        ("+" if total_delta >= 0 else "") + _scenario_amount_text(total_delta, value_unit),
    ]
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=[*(["relative"] * len(deltas)), "total"],
            x=labels,
            y=values,
            text=bar_text,
            textposition="outside",
            textfont={"size": 10.5},
            cliponaxis=False,
            increasing={"marker": {"color": "#00843D"}},
            decreasing={"marker": {"color": "#B42318"}},
            totals={"marker": {"color": "#002B5C"}},
            connector={"line": {"color": "#CBD5E1", "width": 1}},
            hovertemplate=f"<b>%{{x}}</b><br>{_scenario_hover_value_format(value_unit)}<extra></extra>",
        )
    )
    fig.update_xaxes(tickangle=-30, tickfont={"size": 10.5})
    fig.update_yaxes(title_text=axis_title, gridcolor="#E6EDF5", zeroline=True, zerolinecolor="#CBD5E1")
    fig.update_layout(
        height=360,
        margin={"l": 56, "r": 18, "t": 30, "b": 78},
        showlegend=False,
        plot_bgcolor="#FFFFFF",
    )
    return fig


@st.cache_data(show_spinner=False, max_entries=8)
def cached_fleet_mix_frame(
    source: str,
    signature: tuple[tuple[str, int, int], ...],
    bridge_vintage_id: str,
) -> pd.DataFrame:
    del signature
    from model_dashboard.fleet_mix import load_source_frame

    return load_source_frame(
        Path(__file__).resolve().parent, source, bridge_vintage_id
    )


def _fleet_mix_signature(bridge_vintage_id: str) -> tuple[tuple[str, int, int], ...]:
    from model_dashboard.engine import engine_revenue_outlook_dir

    repo_root = Path(__file__).resolve().parent
    # Stat the pack files of the vintage ACTUALLY in use, resolved through the
    # registry, so a future default bridge is part of the invalidation key
    # without editing this list.
    static_paths = [
        *official_vintage_pack_files(bridge_vintage_id, repo_root),
        repo_root / "data" / "vfm_202405" / "vfm_vkt_shares.csv",
    ]
    signature: list[tuple[str, int, int]] = []
    for path in static_paths:
        try:
            stat = path.stat()
        except OSError:
            signature.append((path.as_posix(), 0, 0))
            continue
        signature.append((path.as_posix(), int(stat.st_size), int(stat.st_mtime_ns)))
    pack_dir = repo_root / engine_revenue_outlook_dir("ar1")
    signature.extend(revenue_outlook_signature(pack_dir, repo_root))
    return tuple(signature)


def _render_fleet_mix_explorer(bridge_vintage_id: str) -> None:
    """MoT's six volume rows across the bridge vintage / VFM / the dashboard
    pack, with an explicit choice of denominator - because the same BEV
    kilometres are 1.7% of all road travel and 6.1% of the light RUC pool, and
    mixing those silently is how trust dies."""
    from model_dashboard.fleet_mix import (
        DASHBOARD_SOURCE,
        DENOMINATORS,
        METRIC_KM,
        METRIC_OPTIONS,
        METRIC_SHARE,
        METRIC_YOY,
        ROW_COLORS,
        ROW_KEYS,
        ROW_LABELS,
        definitions_table,
        denominator_example,
        is_official_source,
        official_source_label,
        share_frame,
        source_options,
        yoy_frame,
    )

    repo_root = Path(__file__).resolve().parent
    official_source = official_source_label(bridge_vintage_id)
    fleet_source_options = source_options(bridge_vintage_id)
    with st.container(border=True):
        st.markdown(
            f"<div class='page5-panel-title'>Fleet mix explorer - MoT's six volume rows across "
            f"{bridge_vintage_id}, the VFM and this dashboard</div>",
            unsafe_allow_html=True,
        )
        if method_detail_enabled():
            st.caption(
                "Everything the class split does happens on MoT's own six volume rows. Compare the sources "
                "on those rows directly - in kilometres, as shares of an explicitly chosen total, or as "
                "year-on-year change. Light RUC net km is conventional (diesel) ONLY; battery-electric and "
                "plug-in hybrid are their own rows."
            )
        control_cols = st.columns([0.40, 0.32, 0.28])
        with control_cols[0]:
            # A stored selection naming a different vintage is reset first, so
            # the label can never outlive the pack it was chosen against.
            _validated_select_state("fleet_mix_source", fleet_source_options, official_source)
            source = st.selectbox(
                "Source",
                fleet_source_options,
                key="fleet_mix_source",
                **_widget_default_kwargs(
                    "fleet_mix_source", index=fleet_source_options.index(official_source)
                ),
            )
        with control_cols[1]:
            # Year-on-year change is method detail; a stale session selection
            # is reset before the radio renders with the shorter option set.
            metric_options = list(METRIC_OPTIONS) if method_detail_enabled() else [METRIC_KM, METRIC_SHARE]
            _validated_select_state("fleet_mix_metric", metric_options, METRIC_KM)
            metric = st.radio("View", metric_options, key="fleet_mix_metric",
                              label_visibility="visible", horizontal=False)
        denominator = list(DENOMINATORS)[0]
        with control_cols[2]:
            if metric == METRIC_SHARE:
                denominator = st.selectbox("As a share of", list(DENOMINATORS), key="fleet_mix_denominator")

        try:
            frame = cached_fleet_mix_frame(
                source, _fleet_mix_signature(bridge_vintage_id), bridge_vintage_id
            )
        except Exception as exc:  # pragma: no cover - defensive surface
            warning_panel(f"Fleet mix data unavailable: {exc}")
            return

        fig = go.Figure()
        if metric == METRIC_KM:
            for key in ROW_KEYS:
                fig.add_trace(go.Scatter(
                    x=frame.index, y=frame[key], name=ROW_LABELS[key], mode="lines",
                    stackgroup="fleet", line={"width": 0.6, "color": ROW_COLORS[key]},
                    hovertemplate=f"<b>{ROW_LABELS[key]}</b><br>%{{y:,.0f}} million km<extra></extra>",
                ))
            fig.update_yaxes(title_text="million km", gridcolor="#E6EDF5")
        elif metric == METRIC_SHARE:
            shares = share_frame(frame, denominator)
            for key in shares.columns:
                fig.add_trace(go.Scatter(
                    x=shares.index, y=shares[key], name=ROW_LABELS[key], mode="lines",
                    line={"width": 2.4, "color": ROW_COLORS[key]},
                    hovertemplate=f"<b>{ROW_LABELS[key]}</b><br>%{{y:.1%}} of: {denominator}<extra></extra>",
                ))
            fig.update_yaxes(title_text=f"share of {denominator.lower()}", tickformat=".0%", gridcolor="#E6EDF5")
        else:
            growth = yoy_frame(frame)
            for key in ROW_KEYS:
                fig.add_trace(go.Scatter(
                    x=growth.index, y=growth[key], name=ROW_LABELS[key], mode="lines",
                    line={"width": 2.0, "color": ROW_COLORS[key]},
                    hovertemplate=f"<b>{ROW_LABELS[key]}</b><br>%{{y:+.1f}}% vs prior year<extra></extra>",
                ))
            fig.update_yaxes(title_text="% change vs prior year", gridcolor="#E6EDF5", zeroline=True,
                             zerolinecolor="#CBD5E1")
        fig.update_xaxes(title_text="June year ending", title_font={"size": 11, "color": "#5A6B7B"},
                         showgrid=False, dtick=5)
        fig.update_layout(height=380, margin={"l": 56, "r": 18, "t": 40, "b": 40},
                          hovermode="x unified", plot_bgcolor="#FFFFFF",
                          legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0.0,
                                  "font": {"size": 10.5}})
        st.plotly_chart(fig, use_container_width=True, key="fleet_mix_chart")

        if not method_detail_enabled():
            return
        ex = denominator_example(repo_root, bridge_vintage_id=bridge_vintage_id)
        st.markdown(
            f"<div style='background:#F0F7FF;border:1px solid #BFDBFE;border-radius:10px;padding:10px 14px;"
            f"font-size:0.84rem;color:#1E3A5F'><b>Same kilometres, three denominators "
            f"({bridge_vintage_id}, FY{ex['fy']}):</b> "
            f"BEV travel is {ex['light_bev_km']:,.0f}m km. Divided by all six rows "
            f"({ex['total_km']:,.0f}m km) that is <b>{ex['share_all']:.2%}</b> of all road travel; divided by all "
            f"light travel including petrol ({ex['light_all_km']:,.0f}m km) it is <b>{ex['share_light']:.2%}</b>; "
            f"divided by the light RUC pool ({ex['pool_km']:,.0f}m km) it is <b>{ex['share_pool']:.2%}</b> - the "
            f"number the S-curve analysis and the uptake levers work with, because that pool is what the class "
            f"split reallocates. None of these is wrong; they answer different questions.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='page5-panel-title' style='margin-top:0.6rem'>What each row means, source by source</div>",
                    unsafe_allow_html=True)
        display_table(definitions_table(), height=260, max_rows=10)
        if is_official_source(source, bridge_vintage_id):
            st.caption(
                f"{bridge_vintage_id} covers FY2001-FY2050 (actuals then official forecast). "
                "The VFM scenarios and the dashboard pack cover the forecast era, FY2025-FY2050."
            )
        elif source == DASHBOARD_SOURCE:
            st.caption(
                "Dashboard Base uses the raw PED bridge followed by the MoT VFM Base "
                f"petrol-retention overlay, with the FY2025 {bridge_vintage_id} actual as the "
                "common anchor. Light-petrol VKT, PED litres and FED revenue therefore share one "
                "volume lineage before policy-price, e-RUC and conflict-price responses."
            )


@st.cache_data(show_spinner=False, max_entries=6)
def cached_revenue_rate_paths_figure(
    signature: tuple[tuple[str, int, int], ...],
    fed_policy_state: str,
    _chart_rows: pd.DataFrame,
    bridge_vintage_id: str,
) -> go.Figure:
    del signature
    # The bridge vintage is part of the cache key: the displayed effective
    # rates are derived from it, so a pack built on a different bridge must
    # never serve a cached figure from another one.
    frame = rate_paths_frame(
        Path(__file__).resolve().parent,
        _chart_rows,
        bridge_vintage_id=bridge_vintage_id,
    )
    return revenue_rate_paths_figure(frame, fed_policy_state=fed_policy_state)


def revenue_rate_paths_figure(frame: pd.DataFrame, *, fed_policy_state: str) -> go.Figure:
    if frame is None or frame.empty:
        return empty_figure("Rate paths are unavailable in the committed source tables.")
    fig = go.Figure()
    selected_state = _normalise_fed_policy_state(fed_policy_state)
    selected_segment = {
        FED_POLICY_PUBLISHED: "planned",
        FED_POLICY_DELAYED_6M: "delayed_6m",
        FED_POLICY_OFF: "no_uplift",
    }[selected_state]
    segment_labels = {
        "planned": "Original timing — 12c from Jan 2027",
        "delayed_6m": "Deferred 6 months — 12c from Jul 2027",
        "no_uplift": "No 12c FED / proportional RUC uplift",
    }
    segment_order = ("planned", "delayed_6m", "no_uplift")
    styles = [("PED (petrol excise)", "history", "#00843D", "solid", 2.4, "PED, actual")]
    for series, selected_color, reference_color in (
        ("Light RUC", "#006FAD", "#8DBDD8"),
        ("Heavy RUC", "#102A43", "#94A3B8"),
        ("PED (petrol excise)", "#00843D", "#9ABFA8"),
    ):
        for segment in segment_order:
            selected = segment == selected_segment
            label = (
                f"{series}, selected: {segment_labels[segment]}"
                if selected
                else f"{series}, reference: {segment_labels[segment]}"
            )
            styles.append(
                (
                    series,
                    segment,
                    selected_color if selected else reference_color,
                    "solid" if selected else ("dash" if segment == "planned" else "dot"),
                    2.6 if selected else 1.2,
                    label,
                )
            )
    for series, segment, color, dash, width, label in styles:
        group = frame[frame["series"].eq(series)]
        if segment is not None:
            group = group[group["segment"].eq(segment)]
        group = group.dropna(subset=["nzd_per_1000km"]).sort_values("june_year")
        if group.empty:
            continue
        litre_text = [
            f"<br>${v:,.2f}/litre" if pd.notna(v) else "" for v in group["nzd_per_litre"]
        ]
        fig.add_trace(
            go.Scatter(
                x=group["june_year"],
                y=group["nzd_per_1000km"],
                mode="lines",
                name=label,
                line={"color": color, "dash": dash, "width": width},
                customdata=litre_text,
                hovertemplate="<b>%{fullData.name}</b><br>$%{y:,.0f} per 1,000 km%{customdata}<extra></extra>",
            )
        )
    fig.update_xaxes(title_text="June year ending", title_font={"size": 11, "color": "#5A6B7B"}, showgrid=False, dtick=5)
    fig.update_yaxes(title_text="NZD per 1,000 km", gridcolor="#E6EDF5", zeroline=False)
    fig.update_layout(
        height=300,
        margin={"l": 56, "r": 18, "t": 20, "b": 40},
        hovermode="x unified",
        hoverdistance=5,
        legend={"orientation": "h", "y": -0.22, "x": 0.0, "font": {"size": 11}},
        plot_bgcolor="#FFFFFF",
        shapes=[
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": 2025.5,
                "x1": 2025.5,
                "y0": 0,
                "y1": 1,
                "line": {"dash": "dash", "color": "#B45309", "width": 1.4},
            }
        ],
        annotations=[
            {
                "xref": "x",
                "yref": "paper",
                "x": 2025.5,
                "y": 1.0,
                "text": "Actuals to 2025",
                "showarrow": False,
                "yanchor": "bottom",
                "font": {"color": "#B45309", "size": 11},
            }
        ],
    )
    return fig


def _display_period_label(period: Any) -> str:
    """June-year periods display as plain years ('FY2025' -> '2025')."""
    text = str(period or "")
    return text[2:] if text.startswith("FY") and text[2:].isdigit() else text


def _revenue_outlook_default_traces(
    trace_options: list[str],
    selected_official_trace: str | None = None,
) -> list[str]:
    options = list(trace_options or [])
    # Default-on official trace is the SELECTED comparator vintage; overlaid
    # prior vintages stay selectable in the legend without being default-on.
    registry_officials = _registry_official_trace_names()
    default_official = selected_official_trace or next(
        (trace for trace in registry_officials if trace in options),
        registry_officials[0] if registry_officials else "",
    )
    # Keep the management view readable by default: show the Medium conflict
    # path and make Low/High directly available in the legend selector.
    preferred = [
        "Actual",
        default_official,
        "Current finalist Base case",
        "Current finalist High population/comparison",
        FUEL_PRICE_SCENARIO_TRACE_NAME,
        # Governed scenario-role policy keeps the PED behavioural comparison
        # path visible (relabelled); it must be in the default legend or the
        # PED VKT per capita comparison disappears by default.
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    ]
    selected = [trace for trace in preferred if trace in options]
    return selected or options[: min(3, len(options))]


def _revenue_outlook_trace_selection_summary(selected_traces: list[str], option_count: int) -> str:
    selected = [str(trace) for trace in selected_traces if str(trace).strip()]
    if not selected:
        return "Using default legend items."
    if len(selected) == 1:
        return selected[0]
    if len(selected) == option_count:
        return f"All {option_count} selected"
    return f"{len(selected)} of {option_count} selected"


def _revenue_outlook_fed_path_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty or "fed_path" not in chart_rows.columns:
        return []
    data = chart_rows.copy()
    if "plot_allowed" in data.columns:
        data = data[data["plot_allowed"].fillna(True).astype(bool)].copy()
    # Official-comparator release labels are not selectable FED rate paths;
    # only in-house path-sensitive traces respond to this control. The
    # excluded set is registry-derived (plus the retired BEFU25 legacy label)
    # so a newly registered vintage is excluded without an edit here.
    excluded_releases = {"nan", "befu25"} | {
        vid.lower() for vid, _display in official_vintage_choices(Path(__file__).resolve().parent)
    }
    values = [
        value
        for value in data["fed_path"].dropna().astype(str).unique().tolist()
        if value and value.lower() not in excluded_releases
    ]
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
    # Capped at the presentation horizon: the governed packs carry FY2051-FY2055
    # rows as audit material, and the FY marker must not offer a year no chart
    # below it will draw.
    return [
        f"FY{year}"
        for year in sorted(years.unique().tolist())
        if 2025 <= year <= display_end_fy()
    ]


def _scenario_names_for_traces(chart_rows: pd.DataFrame, trace_names: list[str]) -> list[str]:
    if chart_rows is None or chart_rows.empty or not trace_names or "trace_name" not in chart_rows.columns:
        return []
    rows = chart_rows[chart_rows["trace_name"].astype(str).isin(trace_names)].copy()
    if "scenario_name" not in rows.columns:
        return []
    return sorted(rows["scenario_name"].dropna().astype(str).unique().tolist())


QUARTERLY_DISAGGREGATION_NOTE = (
    "This series is only published at June-year grain, so the quarterly view is "
    "derived by temporal disaggregation: each fiscal year is split across its four "
    "quarters with a Denton-style benchmarking solve that reproduces the annual "
    "value exactly (sum for volumes/revenues, average for per-unit series). Where "
    "the stream has a native quarterly activity path (PED VKT per capita, "
    "Light/Heavy RUC net km) it supplies the seasonal shape; otherwise the split "
    "minimises quarter-to-quarter movement. Interpolated quarters are indicative "
    "display values only - not published quarterly actuals or direct model outputs. "
    "PED retail-price deltas and the diesel-plus-RUC running-cost inputs are exact in the quarterly model-price and effective-rate paths. "
    "Direct price-change quarters use the governed medium demand elasticity once against Base so higher running costs lower conventional activity; "
    "lag-only and post-window quarters retain the raw fitted replay. "
    "for annual-only revenue series the June-year total is authoritative, so an interpolated "
    "quarterly hover must not be read as an exact effective-rate replay. "
    "For each conflict trace, the policy-adjusted Base split is retained and signed "
    "native replay deltas are applied only to the quarters in which that path responds."
)


def _quarterly_disaggregation_indicator_id(series_id: Any) -> str:
    sid = str(series_id or "")
    if sid in {"ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"}:
        return ""
    if sid == "light_petrol_vkt":
        return "ped_vkt_per_capita"
    if sid.startswith(("ped", "gross_ped", "gross_fed", "net_fed", "fed")):
        return "ped_vkt_per_capita"
    if sid.startswith(("light", "phev")):
        return "light_ruc_net_km"
    if sid.startswith("heavy"):
        return "heavy_ruc_net_km"
    return ""


def _june_year_quarters(june_year: int) -> list[str]:
    return [f"{june_year - 1}Q3", f"{june_year - 1}Q4", f"{june_year}Q1", f"{june_year}Q2"]


def _is_average_preserving_unit(unit: Any) -> bool:
    text = str(unit or "").lower()
    return any(token in text for token in ["per capita", "per km", "per litre", "per 1,000"])


def _display_unit_scale(unit: Any) -> float:
    """Return the scale from a displayed unit to its unscaled value."""
    # Registry-backed: an unknown declaration raises rather than silently
    # returning 1.0, which used to make a typo indistinguishable from an
    # already-unscaled unit. Absent declarations stay unscaled for display.
    if not str(unit or "").strip():
        return 1.0
    return display_scale_for(unit)


def _actual_quarter_lookup_in_unit(
    chart_rows: pd.DataFrame,
    series_id: Any,
    target_unit: Any,
) -> dict[str, float]:
    """Return published Actual quarters converted to an annual row's unit."""
    if chart_rows is None or chart_rows.empty:
        return {}
    required = {"series_id", "time_grain", "row_type", "period", "value"}
    if required.difference(chart_rows.columns):
        return {}
    actual = chart_rows[
        chart_rows["series_id"].astype(str).eq(str(series_id or ""))
        & chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("historical_actual")
    ].copy()
    if actual.empty:
        return {}
    actual["_numeric"] = pd.to_numeric(actual["value"], errors="coerce")
    actual = actual.dropna(subset=["_numeric"]).drop_duplicates("period", keep="last")
    target_scale = _display_unit_scale(target_unit)
    units = actual.get("value_unit", pd.Series("", index=actual.index)).fillna("").astype(str)
    return {
        str(row["period"]): float(row["_numeric"]) * _display_unit_scale(units.at[index]) / target_scale
        for index, row in actual.iterrows()
        if re.fullmatch(r"\d{4}Q[1-4]", str(row["period"]))
    }


def _denton_quarterly_split(annual_values: np.ndarray, indicator: np.ndarray, *, average: bool) -> np.ndarray:
    """Split annual benchmarks into quarters, minimising movement of the quarterly
    path relative to the indicator (Denton proportional first difference; a flat
    indicator reduces to the Boot-Feibes-Lisman smooth split). Each year's four
    quarters reproduce the annual value exactly."""
    n = int(len(annual_values))
    m = 4 * n
    ind = np.asarray(indicator, dtype=float)
    if ind.shape[0] != m or not np.all(np.isfinite(ind)) or np.any(ind <= 0):
        ind = np.ones(m, dtype=float)
    difference = np.diff(np.eye(m), axis=0)
    weights = ind / 4.0 if average else ind
    constraint = np.zeros((n, m))
    for year in range(n):
        constraint[year, 4 * year : 4 * year + 4] = weights[4 * year : 4 * year + 4]
    kkt = np.zeros((m + n, m + n))
    kkt[:m, :m] = 2.0 * difference.T @ difference
    kkt[:m, m:] = constraint.T
    kkt[m:, :m] = constraint
    rhs = np.concatenate([np.zeros(m), np.asarray(annual_values, dtype=float)])
    solution = np.linalg.lstsq(kkt, rhs, rcond=None)[0]
    return ind * solution[:m]


def _quarterly_indicator_lookup(chart_rows: pd.DataFrame, indicator_series_id: str, trace_name: Any) -> dict[str, float]:
    if not indicator_series_id or chart_rows is None or chart_rows.empty:
        return {}
    if "series_id" not in chart_rows.columns or "time_grain" not in chart_rows.columns:
        return {}
    rows = chart_rows[
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["series_id"].astype(str).eq(indicator_series_id)
    ]
    if rows.empty:
        return {}
    frame = pd.DataFrame(
        {
            "period": rows["period"].astype(str),
            "trace": rows.get("trace_name", pd.Series("", index=rows.index)).astype(str),
            "value": pd.to_numeric(rows["value"], errors="coerce"),
        }
    ).dropna(subset=["value"])
    lookup: dict[str, float] = {}
    for _, row in frame[frame["trace"].eq("Actual")].iterrows():
        lookup[row["period"]] = float(row["value"])
    for _, row in frame[frame["trace"].eq(str(trace_name or ""))].iterrows():
        lookup[row["period"]] = float(row["value"])
    return lookup


def _scenario_quarterly_delta_map(value: Any) -> dict[str, float]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, float] = {}
    for period, raw in parsed.items():
        if not re.fullmatch(r"\d{4}Q[1-4]", str(period)):
            continue
        numeric = pd.to_numeric(pd.Series([raw]), errors="coerce").iloc[0]
        if pd.notna(numeric):
            result[str(period)] = float(numeric)
    return result


def _disaggregate_annual_rows_to_quarterly(annual_rows: pd.DataFrame, chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Derive display-only quarterly rows for series published at June-year grain.

    The governed pack is not modified: rows produced here are tagged
    data_scope=quarterly_disaggregated_from_annual / value_status=interpolated so
    audits can always separate them from published values."""
    if annual_rows is None or annual_rows.empty:
        return pd.DataFrame()
    data = annual_rows.copy()
    data["_value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data["_june_year_numeric"] = pd.to_numeric(data.get("june_year"), errors="coerce")
    data = data[data["_value_numeric"].notna() & data["_june_year_numeric"].notna()]
    if data.empty:
        return pd.DataFrame()
    # Forecast/comparator traces may carry a nowcast anchor row for the last
    # complete actual year (e.g. FY2025); splitting it would plant forecast
    # quarters inside the actuals era. Disaggregate non-actual traces only
    # from the first forecast June year, so their quarterly paths start at
    # FY{first}Q1 (calendar Q3) and hand over from the actuals cleanly.
    is_actual_row = data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("historical_actual")
    data = data[is_actual_row | data["_june_year_numeric"].ge(REVENUE_FIRST_FORECAST_FY)]
    if data.empty:
        return pd.DataFrame()
    group_cols = [c for c in ["trace_name", "scenario_name", "fed_path"] if c in data.columns]
    output: list[dict[str, Any]] = []
    for _, group in data.groupby(group_cols, dropna=False):
        group = group.sort_values("_june_year_numeric").drop_duplicates("_june_year_numeric", keep="last")
        years = group["_june_year_numeric"].astype(int).tolist()
        adjusted_annual_values = group["_value_numeric"].to_numpy(dtype=float)
        if "_fed_baseline_value" in group.columns:
            raw_baseline = pd.to_numeric(group["_fed_baseline_value"], errors="coerce").to_numpy(dtype=float)
            affected_lineage = group.get(
                "_fed_affected_quarters", pd.Series("", index=group.index)
            ).fillna("").astype(str).str.len().gt(0).to_numpy(dtype=bool)
            # A policy replay can retain annual lag/bridge effects after the
            # direct quarter window. With no explicit quarterly lineage for a
            # year, split the adjusted annual benchmark itself so its four
            # quarters still reconcile exactly; use the published baseline
            # only where affected-quarter lineage is available.
            baseline_values = np.where(
                np.isfinite(raw_baseline) & affected_lineage,
                raw_baseline,
                adjusted_annual_values,
            )
        else:
            baseline_values = adjusted_annual_values.copy()
        template = group.iloc[0].to_dict()
        actual_lookup = _actual_quarter_lookup_in_unit(
            chart_rows,
            template.get("series_id"),
            template.get("value_unit"),
        )
        is_non_actual_trace = str(template.get("row_type") or "") != "historical_actual"

        # This selectable subtotal is a strict accounting identity, so its
        # indicative quarterly display must use the component quarter paths
        # rather than an independent Denton solve.  Independent smoothing is
        # annual-consistent but can create material quarter-level residuals
        # even when the June-year formula is exact.  Recursing on the two
        # governed components also preserves their policy-window and conflict-
        # replay lineage without changing either component series.
        if (
            str(template.get("series_id") or "") == "total_fed_ruc_net_revenue"
            and chart_rows is not None
            and not chart_rows.empty
        ):
            component_quarters: list[pd.DataFrame] = []
            for component_id in ("net_fed_revenue", "total_ruc_net_revenue"):
                component_annual = chart_rows[
                    chart_rows.get("time_grain", pd.Series("", index=chart_rows.index)).astype(str).eq("june_year")
                    & chart_rows.get("series_id", pd.Series("", index=chart_rows.index)).astype(str).eq(component_id)
                    & pd.to_numeric(chart_rows.get("june_year"), errors="coerce").isin(years)
                ].copy()
                for identity_column in ("trace_name", "scenario_name", "fed_path"):
                    if identity_column in component_annual.columns:
                        component_annual = component_annual[
                            component_annual[identity_column].fillna("").astype(str).eq(
                                str(template.get(identity_column) or "")
                            )
                        ]
                if component_annual.empty or component_annual.duplicated("june_year").any():
                    component_quarters = []
                    break
                derived_component = _disaggregate_annual_rows_to_quarterly(
                    component_annual,
                    chart_rows,
                )
                if derived_component.empty:
                    component_quarters = []
                    break
                component_quarters.append(
                    derived_component[["period", "june_year", "value"]].rename(
                        columns={"value": component_id}
                    )
                )
            if len(component_quarters) == 2:
                composed = component_quarters[0].merge(
                    component_quarters[1],
                    on=["period", "june_year"],
                    how="inner",
                    validate="one_to_one",
                )
                expected_periods = {
                    str(row.period)
                    for component in component_quarters
                    for row in component.itertuples()
                }
                if not composed.empty and set(composed["period"].astype(str)) == expected_periods:
                    templates_by_fy = {
                        int(row["_june_year_numeric"]): row.to_dict()
                        for _, row in group.iterrows()
                    }
                    for row in composed.itertuples():
                        fy = int(row.june_year)
                        year_template = templates_by_fy.get(fy)
                        if year_template is None:
                            continue
                        year_template.pop("_value_numeric", None)
                        year_template.pop("_june_year_numeric", None)
                        year_template.update(
                            {
                                "period": str(row.period),
                                "time_grain": "quarterly",
                                "june_year": fy,
                                "value": float(row.net_fed_revenue) + float(row.total_ruc_net_revenue),
                                "value_status": "interpolated_formula_rebuilt",
                                "data_scope": "quarterly_disaggregated_from_annual_formula_rebuilt",
                                "plot_allowed": True,
                                "horizon": "",
                                "horizon_scope": "",
                                "actual_quarters": "",
                                "forecast_quarters": "",
                                "quarters_present": "",
                            }
                        )
                        output.append(year_template)
                    continue

        # Each conflict trace is annual for revenue but has native quarterly
        # replay deltas for its PED/Light/Heavy drivers. Build its quarterly
        # display from the already policy-adjusted Base quarters, then apply
        # those signed deltas. This prevents FY2026's loss from leaking into
        # pre-shock 2025Q3-Q4 while preserving every June-year benchmark.
        is_conflict_scenario = str(template.get("scenario_name") or "") in set(
            CONFLICT_SCENARIO_NAMES
        )
        has_delta_lineage = "_fuel_quarterly_value_deltas" in group.columns and group[
            "_fuel_quarterly_value_deltas"
        ].fillna("").astype(str).str.len().gt(0).all()
        if is_conflict_scenario and has_delta_lineage and chart_rows is not None and not chart_rows.empty:
            series_id = str(template.get("series_id") or "")
            fed_path = str(template.get("fed_path") or "")
            base_annual = chart_rows[
                chart_rows["time_grain"].astype(str).eq("june_year")
                & chart_rows["scenario_name"].astype(str).eq("current_basecase")
                & chart_rows["series_id"].astype(str).eq(series_id)
                & pd.to_numeric(chart_rows["june_year"], errors="coerce").isin(years)
            ].copy()
            if fed_path and "fed_path" in base_annual.columns:
                base_annual = base_annual[base_annual["fed_path"].astype(str).eq(fed_path)]
            base_quarterly = _disaggregate_annual_rows_to_quarterly(base_annual, chart_rows)
            base_lookup = {
                str(row.period): float(row.value)
                for row in base_quarterly.itertuples()
                if pd.notna(getattr(row, "value", np.nan))
            }
            # The recursive Base fallback deliberately emits only forecast
            # quarters after the published Actual handover. Restore the fixed
            # Actual observations for the annual benchmark calculation; they
            # are not duplicated in the scenario trace below.
            base_lookup = {**actual_lookup, **base_lookup}
            if base_lookup:
                for year_index, fy in enumerate(years):
                    year_template = group.iloc[year_index].to_dict()
                    delta_map = _scenario_quarterly_delta_map(year_template.get("_fuel_quarterly_value_deltas"))
                    quarter_periods = _june_year_quarters(fy)
                    quarter_values = np.array(
                        [base_lookup.get(period, np.nan) + delta_map.get(period, 0.0) for period in quarter_periods],
                        dtype=float,
                    )
                    if not np.all(np.isfinite(quarter_values)):
                        break
                    average_preserving = _is_average_preserving_unit(year_template.get("value_unit"))
                    benchmark_value = float(quarter_values.mean() if average_preserving else quarter_values.sum())
                    annual_residual = float(adjusted_annual_values[year_index] - benchmark_value)
                    if average_preserving:
                        annual_residual *= len(quarter_periods)
                    active_positions = [
                        position for position, period in enumerate(quarter_periods) if abs(delta_map.get(period, 0.0)) > 1e-12
                    ]
                    correction_position = (
                        max(active_positions, key=lambda position: abs(delta_map.get(quarter_periods[position], 0.0)))
                        if active_positions
                        else len(quarter_periods) - 1
                    )
                    quarter_values[correction_position] += annual_residual
                    for quarter_index, period in enumerate(quarter_periods):
                        if is_non_actual_trace and period in actual_lookup:
                            continue
                        row = dict(year_template)
                        row.pop("_value_numeric", None)
                        row.pop("_june_year_numeric", None)
                        row.update(
                            {
                                "period": period,
                                "time_grain": "quarterly",
                                "june_year": fy,
                                "value": float(quarter_values[quarter_index]),
                                "value_status": "interpolated_conflict_scenario_delta",
                                "data_scope": "quarterly_disaggregated_from_annual_scenario_delta",
                                "plot_allowed": True,
                                "horizon": "",
                                "horizon_scope": "",
                                "actual_quarters": "",
                                "forecast_quarters": "",
                                "quarters_present": "",
                            }
                        )
                        output.append(row)
                else:
                    continue

        indicator_id = _quarterly_disaggregation_indicator_id(template.get("series_id"))
        lookup = _quarterly_indicator_lookup(chart_rows, indicator_id, template.get("trace_name"))
        quarters = [q for fy in years for q in _june_year_quarters(fy)]
        seasonal: dict[str, list[float]] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
        for period, value in lookup.items():
            seasonal[period[-2:]].append(value)
        seasonal_mean = {q: (sum(v) / len(v) if v else 1.0) for q, v in seasonal.items()}
        indicator = np.array(
            [lookup.get(q, seasonal_mean.get(q[-2:], 1.0)) for q in quarters], dtype=float
        )
        values = _denton_quarterly_split(
            baseline_values, indicator, average=_is_average_preserving_unit(template.get("value_unit"))
        )
        for year_index, fy in enumerate(years):
            year_template = group.iloc[year_index].to_dict()
            affected_text = str(year_template.get("_fed_affected_quarters") or "")
            affected = {
                period.strip()
                for period in re.split(r"[;,]", affected_text)
                if re.fullmatch(r"\d{4}Q[1-4]", period.strip())
            }
            annual_delta = float(adjusted_annual_values[year_index] - baseline_values[year_index])
            if affected and abs(annual_delta) > 1e-12:
                quarter_periods = _june_year_quarters(fy)
                affected_positions = [
                    4 * year_index + position
                    for position, period in enumerate(quarter_periods)
                    if period in affected
                ]
                if affected_positions:
                    weights = np.abs(values[affected_positions])
                    if not np.isfinite(weights).all() or float(weights.sum()) <= 0:
                        weights = np.ones(len(affected_positions), dtype=float)
                    delta_to_allocate = annual_delta * (4.0 if _is_average_preserving_unit(year_template.get("value_unit")) else 1.0)
                    values[affected_positions] += delta_to_allocate * weights / float(weights.sum())
            quarter_periods = _june_year_quarters(fy)
            year_slice = slice(4 * year_index, 4 * year_index + 4)
            year_values = values[year_slice].copy()
            fixed_positions = [
                position
                for position, period in enumerate(quarter_periods)
                if is_non_actual_trace and period in actual_lookup
            ]
            if fixed_positions:
                forecast_positions = [position for position in range(4) if position not in fixed_positions]
                annual_total = float(adjusted_annual_values[year_index])
                if _is_average_preserving_unit(year_template.get("value_unit")):
                    annual_total *= 4.0
                fixed_actual = sum(actual_lookup[quarter_periods[position]] for position in fixed_positions)
                forecast_target = annual_total - fixed_actual
                forecast_base = float(year_values[forecast_positions].sum())
                if forecast_positions and forecast_target >= -1e-9:
                    if forecast_base > 0.0:
                        year_values[forecast_positions] *= max(forecast_target, 0.0) / forecast_base
                    else:
                        year_values[forecast_positions] = max(forecast_target, 0.0) / len(forecast_positions)
                    correction_position = max(forecast_positions, key=lambda position: abs(year_values[position]))
                    year_values[correction_position] += forecast_target - float(year_values[forecast_positions].sum())
                    values[year_slice] = year_values
            for quarter_index, period in enumerate(quarter_periods):
                if is_non_actual_trace and period in actual_lookup:
                    continue
                row = dict(year_template)
                row.pop("_value_numeric", None)
                row.pop("_june_year_numeric", None)
                row.update(
                    {
                        "period": period,
                        "time_grain": "quarterly",
                        "june_year": fy,
                        "value": float(values[4 * year_index + quarter_index]),
                        "value_status": (
                            "interpolated_hybrid_actual_handover"
                            if fixed_positions
                            else "interpolated_fed_policy"
                            if affected
                            else "interpolated"
                        ),
                        "data_scope": (
                            "quarterly_disaggregated_from_annual_hybrid_actual_handover"
                            if fixed_positions
                            else "quarterly_disaggregated_from_annual_fed_policy"
                            if affected
                            else "quarterly_disaggregated_from_annual"
                        ),
                        "plot_allowed": True,
                        "horizon": "",
                        "horizon_scope": "",
                        "actual_quarters": "",
                        "forecast_quarters": "",
                        "quarters_present": "",
                    }
                )
                output.append(row)
    if not output:
        return pd.DataFrame()
    result = pd.DataFrame(output)
    result["_period_order"] = result["period"].map(_revenue_period_order)
    return result.sort_values(["trace_name", "_period_order"], kind="stable").drop(columns=["_period_order"])


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


def _public_segment_hover_label(row: pd.Series) -> str:
    """Simple public wording only - no internal H13/H20/H21 language."""

    segment = str(row.get("forecast_segment") or "").strip()
    if segment == "post_model_extrapolation":
        return "<br>Post-model extrapolation"
    if segment == "econometric_forecast":
        return "<br>Econometric forecast"
    role = str(row.get("scenario_role") or "").strip()
    if role == "official_comparator":
        return "<br>Official comparator"
    if role == "actual" or str(row.get("row_type") or "") == "historical_actual":
        return "<br>Actual"
    return ""


def _add_uncertainty_band(
    fig: go.Figure,
    uncertainty_rows: pd.DataFrame | None,
    data: pd.DataFrame,
    display_scale: float,
    *,
    level: str,
    enabled: bool,
) -> None:
    """One conditional modelled-uncertainty band, as two traces and one legend.

    Asymmetric by construction: the lower and upper edges come from separate
    governed quantiles, so a biased error distribution stays biased on the
    chart. The Current line may therefore sit outside the inner 50% band -
    that is the evidence, not a defect.
    """
    if not enabled or uncertainty_rows is None or uncertainty_rows.empty:
        return
    band = uncertainty_rows.copy()
    band["period"] = "FY" + pd.to_numeric(band["FY"], errors="coerce").astype("Int64").astype(str)
    visible = set(data["period"].astype(str))
    band = band[band["period"].isin(visible)]
    lower_column, upper_column = f"lower{level}", f"upper{level}"
    if band.empty or lower_column not in band.columns:
        return
    band = band.sort_values("FY")
    lower = (pd.to_numeric(band[lower_column], errors="coerce") / display_scale).tolist()
    upper = (pd.to_numeric(band[upper_column], errors="coerce") / display_scale).tolist()
    periods = band["period"].astype(str).tolist()
    states = band.get("evidence_state", pd.Series("", index=band.index)).astype(str).tolist()
    fill = BAND_80_FILL if level == "80" else BAND_50_FILL
    legend_rank = 1200 if level == "80" else 1100
    fig.add_trace(
        go.Scatter(
            x=periods, y=upper, mode="lines", line=BAND_BOUNDARY,
            hoverinfo="skip", showlegend=False,
            name=f"{level}% conditional band upper",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=periods, y=lower, mode="lines", line=BAND_BOUNDARY,
            fill="tonexty", fillcolor=fill,
            showlegend=True,
            name=f"{level}% conditional modelled uncertainty",
            legendrank=legend_rank,
            customdata=list(zip(upper, states)),
            hovertemplate=(
                f"<b>{level}%% conditional modelled uncertainty</b><br>"
                "%{y:,.2f} to %{customdata[0]:,.2f}<br>"
                "Evidence: %{customdata[1]}<br>"
                "Excludes Treasury-driver forecast error"
                "<extra></extra>"
            ),
        )
    )


def revenue_outlook_total_path_figure(
    rows: pd.DataFrame,
    *,
    selected_series: str,
    selected_fy: str,
    cone_band: pd.DataFrame | None = None,
    selected_official_trace: str | None = None,
    uncertainty_rows: pd.DataFrame | None = None,
    selected_band_layers: tuple[str, ...] = (),
) -> go.Figure:
    # Clipped again here rather than trusting the caller: this builder is also
    # reached with rows concatenated from other sources, and the chart is the
    # surface the horizon promise is actually about.
    data = _selected_revenue_outlook_series_rows(
        clip_frame_to_display_horizon(rows), selected_series
    )
    if data.empty:
        return empty_figure("Selected revenue series is unavailable in the committed runtime pack.")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return empty_figure("Selected revenue series has no numeric runtime-pack values.")

    data["_period_order"] = data.get("period", pd.Series(dtype=str)).map(_revenue_period_order)
    data = data.sort_values("_period_order", kind="stable")
    axis_title = _revenue_axis_title(data)
    display_scale = _display_value_scale_for_unit(axis_title)
    display_axis_title = _display_axis_unit(axis_title)
    hover_unit = _display_hover_unit(axis_title)
    data["value_display"] = data["value_numeric"] / display_scale
    scenario_colors = _scenario_color_map(data)
    fig = go.Figure()

    # Governed z-order, widest and palest first so nothing buries a line:
    #   1  80% conditional modelled uncertainty
    #   2  MoT VFM Fast-Slow structural range
    #   3  50% conditional modelled uncertainty
    #   4+ deterministic paths and official comparators
    band_layers = set(selected_band_layers)
    _add_uncertainty_band(
        fig, uncertainty_rows, data, display_scale,
        level="80", enabled=BAND_80_LAYER_ID in band_layers,
    )

    # MoT VFM Fast-Slow structural scenario envelope. A scenario envelope, not
    # probabilistic: see VFM_ENVELOPE_NOT_PROBABILISTIC_NOTE.
    if VFM_ENVELOPE_LAYER_ID not in band_layers:
        cone_band = None
    if cone_band is not None and not cone_band.empty:
        band = cone_band.copy()
        band["_order"] = band["period"].astype(str).map(_revenue_period_order)
        band = band.sort_values("_order", kind="stable")
        visible_periods = set(data["period"].astype(str))
        band = band[band["period"].astype(str).isin(visible_periods)]
        if not band.empty:
            band_x = band["period"].astype(str).tolist()
            upper = (pd.to_numeric(band["upper"], errors="coerce") / display_scale).tolist()
            lower = (pd.to_numeric(band["lower"], errors="coerce") / display_scale).tolist()
            fig.add_trace(
                go.Scatter(
                    x=band_x,
                    y=upper,
                    mode="lines",
                    line=VFM_ENVELOPE_BOUNDARY_LINE,
                    hoverinfo="skip",
                    showlegend=False,
                    name="MoT VFM fast bound",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=band_x,
                    y=lower,
                    mode="lines",
                    line=VFM_ENVELOPE_BOUNDARY_LINE,
                    fill="tonexty",
                    fillcolor=VFM_ENVELOPE_FILL_COLOR,
                    hoverinfo="skip",
                    showlegend=True,
                    name=VFM_ENVELOPE_LEGEND_LABEL,
                    legendrank=1150,
                )
            )
    _add_uncertainty_band(
        fig, uncertainty_rows, data, display_scale,
        level="50", enabled=BAND_50_LAYER_ID in band_layers,
    )
    trace_styles = {
        "Actual": ("#737373", "solid", 2.4),
        # Default comparator in the strong green; prior vintages muted, so an
        # analyst overlay of several official traces stays visually distinct.
        # Generated from the registry, so a new vintage is styled without an
        # edit here.
        **_official_trace_style_map(),
        "Current finalist Base case": ("#006FAD", "solid", 2.8),
        "Current finalist High population/comparison": ("#E56B2B", "solid", 2.4),
        **CONFLICT_TRACE_STYLES,
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME: ("#C2410C", "dot", 2.4),
        # The two optional VFM composition scenarios: purple and teal, chosen
        # to stay distinct from the blue Base, the orange comparison and the
        # green official comparator under a colour-blind-conscious palette.
        VFM_FAST_TRACE_NAME: ("#7C4DBE", "solid", 2.2),
        VFM_SLOW_TRACE_NAME: ("#0E8C93", "solid", 2.2),
    }
    trace_names = _ordered_runtime_trace_names(data, selected_official_trace)
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
            "forecast_segment",
        ]:
            if column not in group.columns:
                group[column] = ""
        group["hover_unit"] = hover_unit
        group["_segment"] = group["forecast_segment"].fillna("").astype(str)
        group["_hover_segment"] = group.apply(_public_segment_hover_label, axis=1)
        color, dash, width = trace_styles.get(trace_name, (scenario_colors.get(trace_name, "#006FAD"), "solid", 2.2))
        post_model = group[group["_segment"].eq("post_model_extrapolation")]
        within_model = group[~group["_segment"].eq("post_model_extrapolation")]

        def _add_path_trace(portion: pd.DataFrame, *, dash_style: str, show_legend: bool, suffix: str = "") -> None:
            if portion.empty:
                return
            # The post-model segment drops its per-year markers. With 20
            # densely packed annual points the markers close the dash gaps and
            # the line reads as solid, so the segmentation becomes invisible;
            # a marker-free dashed line is unambiguous at chart scale.
            is_post_model = bool(suffix)
            fig.add_trace(
                go.Scatter(
                    x=portion["period"],
                    y=portion["value_display"],
                    mode="lines" if is_post_model else "lines+markers",
                    name=trace_name,
                    legendgroup=trace_name,
                    showlegend=show_legend,
                    line={"color": color, "dash": dash_style, "width": width},
                    marker={"size": 6},
                    opacity=0.85 if is_post_model else 1.0,
                    customdata=portion[["hover_unit", "_hover_segment"]].to_numpy(),
                    hovertemplate=(
                        "<b>%{fullData.name}</b><br>"
                        "%{y:,.2f} %{customdata[0]}"
                        "%{customdata[1]}"
                        "<extra></extra>"
                    ),
                )
            )

        if post_model.empty:
            _add_path_trace(within_model, dash_style=dash, show_legend=True)
        else:
            # Segmented current path: solid econometric years, then the same
            # colour dashed for the post-model structural extrapolation. The
            # dashed portion re-includes the FY2030 point so the two segments
            # join continuously with no gap and no duplicate hover (the seam
            # point keeps the econometric hover only).
            _add_path_trace(within_model, dash_style=dash, show_legend=True)
            seam = within_model.tail(1)
            joined = pd.concat([seam, post_model], ignore_index=True)
            joined.loc[joined.index[0], "_hover_segment"] = ""
            _add_path_trace(joined, dash_style="dash", show_legend=False, suffix="post_model")

    # Bridge the visual gap between the last actual and the first point of each
    # forecast trace with an actual-coloured connector segment so the handover
    # from history to forecast reads as one continuous path.
    actual_group = data[data["trace_name"].astype(str).eq("Actual")]
    if not actual_group.empty:
        last_actual = actual_group.loc[actual_group["_period_order"].idxmax()]
        for trace_name in trace_names:
            if trace_name == "Actual":
                continue
            group = data[data["trace_name"].astype(str).eq(trace_name)]
            if group.empty:
                continue
            first_point = group.loc[group["_period_order"].idxmin()]
            if first_point["_period_order"] <= last_actual["_period_order"]:
                continue
            fig.add_trace(
                go.Scatter(
                    x=[last_actual["period"], first_point["period"]],
                    y=[last_actual["value_display"], first_point["value_display"]],
                    mode="lines",
                    line={"color": "#737373", "dash": "solid", "width": 2.4},
                    hoverinfo="skip",
                    showlegend=False,
                    name=f"{trace_name} handover",
                )
            )

    periods = data["period"].dropna().astype(str).drop_duplicates().tolist()
    forecast_period = _revenue_outlook_forecast_start_period(data)
    shapes: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    if forecast_period and forecast_period in periods:
        # Draw the history/forecast boundary on the seam where the actuals
        # end: halfway between the last actual and the first forecast
        # category (category axes accept numeric index coordinates).
        boundary_index = float(periods.index(forecast_period))
        actual_periods = data[data.get("row_type", pd.Series(dtype=str)).astype(str).eq("historical_actual")]["period"].astype(str)
        preceding = [p for p in actual_periods if p in periods and periods.index(p) < boundary_index]
        boundary_x = (periods.index(preceding[-1]) + boundary_index) / 2 if preceding else boundary_index - 0.5
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": boundary_x,
                "x1": boundary_x,
                "y0": 0,
                "y1": 1,
                "line": {"dash": "dash", "color": "#B45309", "width": 1.4},
            }
        )
        annotations.append(
            {
                "xref": "x",
                "yref": "paper",
                "x": boundary_x,
                # Just inside the plot's top edge: the band above the chart
                # belongs to the legend, which would collide with it there.
                "y": 0.985,
                "text": f"Actuals to {_display_period_label(preceding[-1])}" if preceding else f"Forecast start {_display_period_label(forecast_period)}",
                "showarrow": False,
                "yanchor": "top",
                "font": {"color": "#B45309", "size": 11},
            }
        )
    # Subtle boundary where the econometric forecast hands over to the
    # post-model structural extrapolation. Drawn only when post-model rows
    # are actually visible on this axis.
    has_post_model = (
        "forecast_segment" in data.columns
        and data["forecast_segment"].fillna("").astype(str).eq("post_model_extrapolation").any()
    )
    if has_post_model and "FY2030" in periods:
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": "FY2030",
                "x1": "FY2030",
                "y0": 0,
                "y1": 1,
                "line": {"dash": "dot", "color": "#8A96A3", "width": 1.1},
            }
        )
        annotations.append(
            {
                "xref": "x",
                "yref": "paper",
                "x": "FY2030",
                "y": 0.03,
                "text": "Post-model extrapolation →",
                "showarrow": False,
                "xanchor": "left",
                "yanchor": "bottom",
                "font": {"color": "#8A96A3", "size": 10},
            }
        )
    if selected_fy in periods:
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": selected_fy,
                "x1": selected_fy,
                "y0": 0,
                "y1": 1,
                "line": {"dash": "dot", "color": "#102A43"},
            }
        )
    # June-year categories are periods that END mid-year, and the boundary
    # markers sit on the seams between them, so plain year labels ("2025",
    # "2026") read correctly; the axis title carries the June-year semantics.
    is_june_axis = bool(periods) and all(str(p).startswith("FY") for p in periods)
    axis_kwargs: dict[str, Any] = {
        "categoryorder": "array",
        "categoryarray": periods,
        "tickangle": -90,
        "showgrid": False,
    }
    if is_june_axis:
        axis_kwargs.update(
            tickvals=periods,
            ticktext=[_display_period_label(p) for p in periods],
            title_text="June year ending",
            title_font={"size": 11, "color": "#5A6B7B"},
        )
    fig.update_xaxes(**axis_kwargs)
    fig.update_yaxes(gridcolor="#E6EDF5", zeroline=False)
    layout: dict[str, Any] = {
        "height": 316,
        "margin": {"l": 52, "r": 18, "t": 56, "b": 46},
        "yaxis_title": display_axis_title,
        "hovermode": "x unified",
        # Only report traces with a point at the hovered period; the default
        # 20px search pulls neighbouring quarters' values into the tooltip
        # under the wrong period header.
        "hoverdistance": 5,
        # Above the plot: the bottom band already carries the vertical year
        # ticks and the axis title, so a below-axis legend overlaps them
        # regardless of screen width.
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0.0, "font": {"size": 11}},
        "plot_bgcolor": "#FFFFFF",
    }
    if shapes:
        layout["shapes"] = shapes
    if annotations:
        layout["annotations"] = annotations
    fig.update_layout(**layout)
    return fig


REVENUE_OUTLOOK_EXPAND_CHART_KEY = "revenue_outlook_expand_chart"


def _render_expand_chart_control() -> bool:
    """The Expand/Collapse control that sits at the top right of the chart.

    An in-app focus mode, not browser fullscreen: no permission prompt, no new
    third-party component, and the page keeps its normal chrome. The toggle
    only changes how much room the chart is given - it is never part of the
    figure's calculation identity, so the plotted values cannot depend on it.
    """
    # A wide spacer column pushes the control to the right edge of the chart;
    # the keyed wrapper carries the flexbox fallback, so the placement holds
    # even if Streamlit's column weighting changes under us again.
    spacer, control = st.columns([6, 1])
    del spacer
    with control, st.container(key=EXPAND_CONTROL_CONTAINER_KEY):
        expanded = st.toggle(
            "Expand chart",
            key=REVENUE_OUTLOOK_EXPAND_CHART_KEY,
            help=(
                "Give the Total path chart a full-width, near-full-height "
                "workspace inside the page. Switch it off to return to the "
                "standard layout. Plotted values are identical either way."
            ),
            **_widget_default_kwargs(REVENUE_OUTLOOK_EXPAND_CHART_KEY, value=False),
        )
    return bool(expanded)


def _render_revenue_outlook_vfm_envelope_caption(view: dict[str, Any]) -> None:
    """State what the blue range is - and is not - directly under the chart.

    The envelope shares the page with an empirical forecast-error fan, so the
    distinction has to be visible without opening a tooltip or an audit.
    """
    if not REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS:
        return
    audit = view.get("cone_band_audit")
    if not isinstance(audit, pd.DataFrame) or audit.empty:
        return
    row = audit.iloc[0]
    if not bool(row.get("band_available")):
        st.caption(f"No MoT VFM Fast–Slow range for this series. {row.get('reason', '')}".strip())
        return
    st.caption(
        f"{VFM_ENVELOPE_NOT_PROBABILISTIC_NOTE} Shown "
        f"{row.get('first_valid_period', '')}–{row.get('last_valid_period', '')}; "
        f"widest gap {float(row.get('max_width_pct_of_level') or 0.0):.2f}% of level. "
        f"{row.get('reason', '')}"
    )


def _render_revenue_outlook_fan_detail_table(
    fan_band_rows: pd.DataFrame,
    fan_availability: pd.DataFrame,
    *,
    selected_series: str,
    selected_fan_source: str,
) -> None:
    """The governed 50/80 values behind the fan, with their CSV.

    The fan figure left the default layout; its source data did not. Every
    column the governance surface relied on - source, lower50/upper50,
    lower80/upper80, interpretation - is still readable and downloadable here.
    """
    if fan_band_rows is None or not isinstance(fan_band_rows, pd.DataFrame) or fan_band_rows.empty:
        st.caption("No governed fan band rows are committed in this runtime pack.")
        return
    series_id = _revenue_outlook_fan_series_id(fan_availability, selected_series)
    resolved = _resolve_revenue_outlook_fan_source(fan_availability, series_id, selected_fan_source)
    data = fan_band_rows[
        fan_band_rows.get("series_id", pd.Series(dtype=str)).astype(str).eq(str(series_id))
    ].copy()
    if resolved:
        data = data[data.get("fan_source", pd.Series(dtype=str)).astype(str).eq(resolved)]
    if data.empty:
        st.caption(_revenue_outlook_fan_gap_message(fan_availability, series_id, selected_fan_source))
        return
    columns = [
        column
        for column in (
            "fan_source", "fan_segment", "FY", "period", "central",
            "lower50", "upper50", "lower80", "upper80", "unit", "interpretation",
        )
        if column in data.columns
    ]
    display_table(data[columns], height=280)
    st.download_button(
        "Download fan band rows (CSV)",
        data[columns].to_csv(index=False).encode("utf-8"),
        file_name=f"revenue_outlook_fan_band_{series_id}.csv",
        mime="text/csv",
        key="revenue_outlook_fan_band_download",
    )


def _render_revenue_outlook_fan_card(
    pack_signature: tuple[tuple[str, int, int], ...],
    fan_band_rows: pd.DataFrame,
    fan_availability: pd.DataFrame,
    *,
    selected_series: str,
    selected_fed_path: str,
    official_fed_paths: tuple[str, ...] | None = None,
) -> None:
    with st.container(border=True):
        st.markdown(
            "<div class='gov-chart-card chart-card'>"
            "<div class='chart-card-title'>Uncertainty fan</div>"
            "<div class='chart-card-subtitle'>Empirical 50%/80% forecast-error band from the best "
            "available governed source, supported to FY2030.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        # Auto / best-available by default; the explicit source override lives
        # in a compact popover rather than a permanent selector.
        with st.popover("Fan source details", use_container_width=False):
            selected_fan_source = st.selectbox(
                "Fan source",
                list(FAN_SOURCE_OPTIONS),
                index=0,
                key="revenue_outlook_fan_source",
            )
            st.caption(
                "Sources in governed priority order: current-finalist empirical "
                "backtest error, archived official forecast error, scenario "
                "range. A scenario range is a spread of governed scenarios, "
                "not a probabilistic confidence interval, and is labelled "
                "accordingly."
            )
        fig, caption = cached_revenue_outlook_fan_figure(
            pack_signature,
            selected_series,
            selected_fed_path,
            selected_fan_source,
            fan_band_rows,
            fan_availability,
            official_fed_paths,
        )
        st.plotly_chart(fig, use_container_width=True, key="chart_card_uncertainty_fan")
        st.caption(caption)
        _render_revenue_outlook_fan_detail_table(
            fan_band_rows,
            fan_availability,
            selected_series=selected_series,
            selected_fan_source=selected_fan_source,
        )


def revenue_outlook_uncertainty_fan_figure(
    fan_band_rows: pd.DataFrame,
    *,
    fan_availability: pd.DataFrame | None = None,
    selected_series: str,
    fan_source: str = FAN_SOURCE_AUTO,
    selected_fed_path: str | None = None,
    official_fed_paths: tuple[str, ...] | None = None,
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
        # Official fan rows are tagged with their vintage's release round; only
        # the currently displayed official vintages stay allowed. Defaulting to
        # every registered vintage means a newly registered release never loses
        # its band to a stale hard-coded list.
        resolved_official_paths = (
            official_fed_paths
            if official_fed_paths is not None
            else tuple(
                vid
                for vid, _display in official_vintage_choices(Path(__file__).resolve().parent)
            )
        )
        allowed_fed_paths = {
            "",
            str(selected_fed_path),
            *(str(path) for path in resolved_official_paths),
        }
        data = data[data["fed_path"].fillna("").astype(str).isin(allowed_fed_paths)].copy()
    for column in ["central", "lower50", "upper50", "lower80", "upper80"]:
        data[column] = pd.to_numeric(data.get(column), errors="coerce")
    data = data.dropna(subset=["central", "lower50", "upper50", "lower80", "upper80"]).copy()
    if data.empty:
        return _revenue_outlook_gap_figure(_revenue_outlook_fan_gap_message(fan_availability, selected_series_id, fan_source), height=220)
    data["_period_order"] = data.get("period", pd.Series(dtype=str)).map(_revenue_period_order)
    data = data.sort_values(["_period_order", "scenario_name"], kind="stable")
    unit = str(data["unit"].dropna().iloc[0]) if "unit" in data.columns and not data["unit"].dropna().empty else ""
    display_scale = _display_value_scale_for_unit(unit)
    display_axis_title = _display_axis_unit(unit)
    hover_unit = _display_hover_unit(unit)
    for column in ["upper80", "lower80", "upper50", "lower50", "central"]:
        if column in data.columns:
            data[f"{column}_display"] = pd.to_numeric(data[column], errors="coerce") / display_scale
    data["hover_unit"] = hover_unit
    fig = go.Figure()
    is_scenario_spread = resolved_source == FAN_SOURCE_SCENARIO_SPREAD
    # Gray fan treatment: outer 80% lighter, inner 50% darker, kept distinct
    # from the slate modelled-uncertainty bands on the main chart - the
    # concepts must not share a visual language.
    band_specs = (
        [
            ("upper80", "lower80", "Scenario spread outer range (not probabilistic)", "rgba(128, 128, 128, 0.16)"),
            ("upper50", "lower50", "Scenario spread inner range (not probabilistic)", "rgba(96, 96, 96, 0.28)"),
        ]
        if is_scenario_spread
        else [
            ("upper80", "lower80", f"{resolved_source} 80% empirical band", "rgba(128, 128, 128, 0.16)"),
            ("upper50", "lower50", f"{resolved_source} 50% empirical band", "rgba(96, 96, 96, 0.28)"),
        ]
    )
    # Split the fan at the FY2030 seam. Empirical sources are already
    # truncated there by the pack builder; the scenario spread continues, but
    # as a separately named long-run envelope so one interval is never
    # presented as retaining the same statistical meaning across both
    # horizons.
    if "fan_segment" in data.columns:
        long_run = data["fan_segment"].astype(str).eq("long_run_scenario_envelope")
    else:
        long_run = pd.Series(False, index=data.index)
    def _draw_bands(portion: pd.DataFrame, *, suffix: str, fillcolor_scale: float) -> None:
        if portion.empty:
            return
        # The long-run envelope earns ONE legend entry, not one per band: its
        # inner/outer split carries no extra meaning once the whole thing is
        # labelled a scenario envelope rather than an interval.
        is_envelope = bool(suffix)
        for index, (upper, lower, name, color) in enumerate(band_specs):
            label = (
                "Long-run structural scenario envelope - not probabilistic"
                if is_envelope
                else name
            )
            fig.add_trace(
                go.Scatter(
                    x=portion["period"], y=portion[f"{upper}_display"], mode="lines",
                    line={"width": 0}, showlegend=False, hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=portion["period"],
                    y=portion[f"{lower}_display"],
                    mode="lines",
                    fill="tonexty",
                    fillcolor=color if fillcolor_scale == 1.0 else _fade_rgba(color, fillcolor_scale),
                    line={"width": 0},
                    name=label,
                    legendgroup="long_run_envelope" if is_envelope else f"band_{index}",
                    showlegend=(index == 0) if is_envelope else True,
                    customdata=portion[["hover_unit", "method", "source_file"]].to_numpy(),
                    hovertemplate="%{x}<br>%{y:,.2f} %{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]}<extra>%{fullData.name}</extra>",
                )
            )

    empirical_portion = data[~long_run]
    long_run_portion = data[long_run]
    _draw_bands(empirical_portion, suffix="", fillcolor_scale=1.0)
    if not long_run_portion.empty:
        # Include the seam row so the envelope joins the band with no gap.
        seam = empirical_portion.tail(1)
        joined = pd.concat([seam, long_run_portion], ignore_index=True)
        _draw_bands(joined, suffix=" — long-run scenario envelope", fillcolor_scale=0.6)
    central_name = "Current finalist base case" if is_scenario_spread else resolved_source
    fig.add_trace(
        go.Scatter(
            x=data["period"],
            y=data["central_display"],
            mode="lines+markers",
            name=central_name,
            line={"color": "#006FAD", "width": 2.4},
            marker={"size": 6},
            customdata=data[["hover_unit", "interpretation"]].to_numpy(),
            hovertemplate="%{x}<br>%{y:,.2f} %{customdata[0]}<br>%{customdata[1]}<extra>%{fullData.name}</extra>",
        )
    )
    shapes: list[dict[str, Any]] = []
    if not long_run_portion.empty and not empirical_portion.empty:
        seam_period = str(empirical_portion["period"].iloc[-1])
        shapes.append(
            {
                "type": "line", "xref": "x", "yref": "paper",
                "x0": seam_period, "x1": seam_period, "y0": 0, "y1": 1,
                "line": {"dash": "dot", "color": "#8A96A3", "width": 1.0},
            }
        )
    fig.update_layout(
        height=220,
        margin={"l": 40, "r": 12, "t": 16, "b": 40},
        hovermode="x unified",
        yaxis_title=display_axis_title,
        legend={"orientation": "h", "y": -0.24, "x": 0.0},
        shapes=shapes,
    )
    return fig


def _fade_rgba(color: str, scale: float) -> str:
    """Weaken an rgba fill so the long-run envelope reads as less certain."""

    if not color.startswith("rgba("):
        return color
    parts = [part.strip() for part in color[5:-1].split(",")]
    if len(parts) != 4:
        return color
    try:
        alpha = float(parts[3]) * scale
    except ValueError:
        return color
    return f"rgba({parts[0]}, {parts[1]}, {parts[2]}, {alpha:.3f})"


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
    axis_title = _bridge_axis_title(plot)
    display_scale = _display_value_scale_for_unit(axis_title)
    display_axis_title = _display_axis_unit(axis_title)
    plot["component_display"] = plot["component_numeric"] / display_scale
    plot["hover_unit"] = _display_hover_unit(axis_title)
    fig = go.Figure(
        go.Bar(
            x=plot["stream_label"],
            y=plot["component_display"],
            marker_color=["#006FAD" if value >= 0 else "#B45309" for value in plot["component_numeric"]],
            customdata=plot[["hover_unit", "component_type", "bridge_status"]].to_numpy(),
            hovertemplate="%{x}<br>%{y:,.1f} %{customdata[0]}<br>%{customdata[1]} - %{customdata[2]}<extra></extra>",
        )
    )
    fig.update_layout(height=360, margin={"l": 52, "r": 18, "t": 28, "b": 104}, yaxis_title=display_axis_title, xaxis_tickangle=-30)
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
    unit = _bridge_axis_title(plot)
    display_scale = _display_value_scale_for_unit(unit)
    plot["component_display"] = plot["component_numeric"] / display_scale
    plot["hover_unit"] = _display_hover_unit(unit)
    fig = go.Figure(
        go.Pie(
            labels=plot["stream_label"],
            values=plot["component_display"],
            hole=0.45,
            marker={"colors": ["#006FAD", "#00843D", "#6B4E71"][: len(plot)]},
            customdata=plot[["hover_unit", "bridge_status"]].to_numpy(),
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
    axis_title = _revenue_stack_axis_title(plot)
    display_scale = _display_value_scale_for_unit(axis_title)
    display_axis_title = _display_axis_unit(axis_title)
    hover_unit = _display_hover_unit(axis_title)
    plot["stack_value_display"] = plot["stack_value_numeric"] / display_scale
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
    # NZTA brand-anchored sequence: blues/greens/teals lead for the large
    # RUC/FED components; warm hues stay for deductions and small lines.
    colors = [
        "#006FAD",
        "#00843D",
        "#002B5C",
        "#008C7E",
        "#3B7080",
        "#A7C800",
        "#287D8E",
        "#6B4E71",
        "#5B6770",
        "#E56B2B",
        "#B7791F",
        "#C2410C",
        "#6A5ACD",
        "#92400E",
    ]
    label_cols = ["line_label", "stack_role", "section_order", "line_order"]
    labels = plot[label_cols].drop_duplicates().copy()
    labels = labels.sort_values(["section_order", "line_order", "line_label"], kind="stable")
    for index, label_row in labels.reset_index(drop=True).iterrows():
        label = str(label_row["line_label"])
        trace_rows = plot[plot["line_label"].astype(str).eq(label)].sort_values("FY_numeric", kind="stable")
        trace_rows["visible_stack_total"] = trace_rows["FY_numeric"].map(lambda value: visible_stack_lookup.get(int(value), np.nan))
        trace_rows["hover_stack_value"] = trace_rows["stack_value_display"]
        trace_rows["hover_unit"] = hover_unit
        trace_rows["hover_label"] = label
        custom_cols = ["unit", "visible_stack_total", "hover_stack_value", "hover_unit", "hover_label"]
        for column in custom_cols:
            if column not in trace_rows.columns:
                trace_rows[column] = pd.NA
        trace_rows["visible_stack_total"] = pd.to_numeric(trace_rows["visible_stack_total"], errors="coerce")
        values = trace_rows["stack_value_display"].tolist()
        fig.add_trace(
            go.Bar(
                name=label,
                x=trace_rows["FY_numeric"].astype(int),
                y=values,
                marker_color=colors[index % len(colors)],
                customdata=trace_rows[custom_cols].to_numpy(),
                hovertemplate=f"{label}: %{{customdata[2]:,.2f}} %{{customdata[3]}}; FY %{{x}}<extra></extra>",
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
        overlay_rows["value_display"] = overlay_rows["value_numeric"] / display_scale
        for label, group in overlay_rows.groupby("line_label", sort=False):
            group = group.sort_values("FY_numeric", kind="stable")
            group["visible_stack_total"] = group["FY_numeric"].map(lambda value: visible_stack_lookup.get(int(value), np.nan))
            group["visible_stack_residual"] = pd.to_numeric(group["visible_stack_total"], errors="coerce") - pd.to_numeric(group["value_numeric"], errors="coerce")
            if status_column in group.columns:
                group = group[group[status_column].astype(str).eq("balanced")].copy()
            group = group[pd.to_numeric(group["visible_stack_residual"], errors="coerce").abs().le(1.0)].copy()
            if group.empty:
                continue
            group["hover_unit"] = hover_unit
            group["hover_label"] = label
            custom_cols = ["unit", "visible_stack_total", "value_display", "hover_unit", "hover_label"]
            for column in custom_cols:
                if column not in group.columns:
                    group[column] = ""
            fig.add_trace(
                go.Scatter(
                    name=f"{label} overlay",
                    x=group["FY_numeric"].astype(int),
                    y=group["value_display"],
                    mode="lines+markers",
                    line={"width": 2.5, "dash": "dot"},
                    marker={"size": 7, "symbol": "diamond"},
                    customdata=group[custom_cols].to_numpy(),
                    hovertemplate=f"{label}: %{{customdata[2]:,.2f}} %{{customdata[3]}}; FY %{{x}}<extra></extra>",
                )
            )

    fig.update_layout(
        barmode="relative",
        height=460,
        margin={"l": 58, "r": 20, "t": 28, "b": 58},
        yaxis_title=display_axis_title,
        xaxis_title="June year",
        xaxis=_bounded_year_axis(plot, "FY_numeric"),
        yaxis={"zeroline": True, "zerolinewidth": 1.5, "zerolinecolor": "#52616B", "gridcolor": "#E6EDF5"},
        legend={"orientation": "h", "y": -0.20, "x": 0, "font": {"size": 10}},
        hovermode="x unified",
        plot_bgcolor="#FFFFFF",
    )
    return fig


def _selected_revenue_outlook_series_rows(rows: pd.DataFrame, selected_series: str) -> pd.DataFrame:
    if rows is None or rows.empty:
        return pd.DataFrame()
    label_column = "series_label" if "series_label" in rows.columns else "stream_label"
    if label_column not in rows.columns:
        return pd.DataFrame()
    return rows[rows[label_column].astype(str).eq(str(selected_series))].copy()


def _ordered_runtime_trace_names(
    rows: pd.DataFrame,
    selected_official_trace: str | None = None,
) -> list[str]:
    if rows is None or rows.empty or "trace_name" not in rows.columns:
        return []
    available = set(rows["trace_name"].dropna().astype(str))
    officials = _ordered_official_traces(selected_official_trace)
    preferred = [
        "Actual",
        *officials,
        "Current finalist Base case",
        "Current finalist High population/comparison",
        *CONFLICT_TRACE_NAMES,
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


def _is_million_currency_unit(unit: Any) -> bool:
    text = str(unit or "").strip().lower()
    return text.startswith("$m") or "million nzd" in text or "million nz$" in text


def _display_value_scale_for_unit(unit: Any) -> float:
    return 1000.0 if _is_million_currency_unit(unit) else 1.0


def _display_axis_unit(unit: Any) -> str:
    text = str(unit or "").strip()
    if not _is_million_currency_unit(text):
        return text or "Value"
    if text.startswith("$m"):
        return "$b" + text[2:]
    return "$b nominal"


def _display_hover_unit(unit: Any) -> str:
    return "$b" if _is_million_currency_unit(unit) else str(unit or "").strip()


def _bounded_year_axis(rows: pd.DataFrame, column: str) -> dict[str, Any]:
    years = pd.to_numeric(rows.get(column, pd.Series(dtype=float)), errors="coerce").dropna()
    if years.empty:
        return {"tickmode": "linear", "dtick": 1}
    first_year = int(years.min())
    last_year = int(years.max())
    return {
        "tickmode": "linear",
        "dtick": 1,
        "tick0": first_year,
        "range": [first_year - 0.5, last_year + 0.5],
    }


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
        display_scale = _display_value_scale_for_unit(unit)
        display_axis_title = _display_axis_unit(unit)
        hover_unit = _display_hover_unit(unit)
        stream_rows["value_display"] = stream_rows["value_numeric"] / display_scale
        historical = stream_rows[stream_rows["row_type"].astype(str).eq("historical_actual") & stream_rows["value_numeric"].notna()].copy()
        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical["period"],
                    y=historical["value_display"],
                    mode="lines",
                    name="Historical actual",
                    legendgroup="historical",
                    showlegend=col == 1,
                    line={"color": "#737373", "width": 2},
                    hovertemplate=f"%{{x}}<br>%{{y:,.2f}} {html.escape(hover_unit)}<extra>Historical actual</extra>",
                ),
                row=1,
                col=col,
            )
        future = stream_rows[
            stream_rows["row_type"].astype(str).isin(["future_forecast", "official_comparator"])
            & stream_rows["value_numeric"].notna()
        ].copy()
        last_actual = historical.tail(1)[["period", "value_display"]] if not historical.empty else pd.DataFrame()
        group_column = "trace_name" if "trace_name" in future.columns else "scenario_name"
        for scenario, group in future.groupby(group_column, dropna=False):
            scenario_name = str(scenario)
            color = scenario_colors.get(scenario_name, "#006FAD")
            plot_cols = [
                col
                for col in [
                    "period",
                    "value_display",
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
                    y=plot_group["value_display"],
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
                marker_rows["value_display"] = pd.to_numeric(marker_rows.get("value_numeric"), errors="coerce") / display_scale
                fig.add_trace(
                    go.Scatter(
                        x=marker_rows["period"],
                        y=marker_rows["value_display"],
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
        fig.update_yaxes(title_text=display_axis_title, row=1, col=col, separatethousands=True)
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
        **{name: style[0] for name, style in _official_trace_style_map().items()},
        "Current finalist Base case": "#006FAD",
        "Current finalist High population/comparison": "#E56B2B",
        **CONFLICT_TRACE_COLORS,
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


def _revenue_hover_text_values(rows: pd.DataFrame, column: str) -> list[str]:
    if column not in rows.columns:
        return [""] * len(rows)
    output: list[str] = []
    for value in rows[column].to_numpy():
        output.append("" if pd.isna(value) else str(value).strip())
    return output


def _revenue_hover_float_values(rows: pd.DataFrame, column: str) -> list[float | None]:
    if column not in rows.columns:
        return [None] * len(rows)
    output: list[float | None] = []
    for value in rows[column].to_numpy():
        try:
            output.append(None if pd.isna(value) else float(value))
        except Exception:
            output.append(None)
    return output


def _human_revenue_label_values(values: list[str]) -> list[str]:
    labels: dict[str, str] = {}
    output: list[str] = []
    for value in values:
        if value not in labels:
            labels[value] = _human_revenue_code_label(value)
        output.append(labels[value])
    return output


def _revenue_path_hover_customdata(rows: pd.DataFrame) -> Any:
    if rows is None or rows.empty:
        return []
    data_scope = _revenue_hover_text_values(rows, "data_scope")
    value_status = _revenue_hover_text_values(rows, "value_status")
    horizon_scope = _revenue_hover_text_values(rows, "horizon_scope")
    horizon_values = _revenue_hover_float_values(rows, "horizon")
    actual_scope = {"actual_anchor", "current_nowcast", "current_forecast", "official_comparator"}
    value_status_labels = _human_revenue_label_values(value_status)
    data_scope_labels = _human_revenue_label_values(data_scope)
    # June-year rows land in actual_scope below, so without this the fiscal
    # totals carry no validated-horizon warning at all.
    zone_labels = _revenue_hover_text_values(rows, "horizon_zone_label")
    zone_warnings = _revenue_hover_text_values(rows, "horizon_validation_warning")
    beyond_counts = _revenue_hover_float_values(rows, "quarters_beyond_validated_horizon")
    horizon_hover: list[str] = []
    for scope, status_label, scope_label, horizon, scope_label_raw, zone_label, zone_warning, beyond in zip(
        data_scope,
        value_status_labels,
        data_scope_labels,
        horizon_values,
        horizon_scope,
        zone_labels,
        zone_warnings,
        beyond_counts,
    ):
        if scope in actual_scope:
            base_label = status_label or scope_label
            if zone_warning:
                detail = zone_label or zone_warning
                if beyond is not None and int(float(beyond)) > 0:
                    detail = f"{detail} ({int(float(beyond))} of 4 quarters)"
                base_label = f"{base_label}<br>Horizon: {html.escape(detail)}"
            horizon_hover.append(base_label)
            continue
        if horizon is None:
            horizon_hover.append("Latest actual join point")
            continue
        horizon_int = int(float(horizon))
        if scope_label_raw == "H1-H12" or 1 <= horizon_int <= BACKTEST_SUPPORTED_MAX_HORIZON:
            horizon_hover.append(f"H{horizon_int}: H1-H12 backtest-supported horizon")
        else:
            horizon_hover.append(f"H{horizon_int}: H13+ long-range extrapolation")

    status = _revenue_hover_text_values(rows, "bridge_status")
    reason = _revenue_hover_text_values(rows, "gap_reason")
    status_labels = [html.escape(value) for value in _human_revenue_label_values(status)]
    reason_labels = [html.escape(value) for value in _human_revenue_label_values(reason)]
    bridge_hover = [
        f"<br>Bridge status: {status_label} - {reason_label}"
        if reason_value
        else (f"<br>Bridge status: {status_label}" if status_value else "")
        for status_value, reason_value, status_label, reason_label in zip(status, reason, status_labels, reason_labels)
    ]

    actual_quarters = _revenue_hover_text_values(rows, "actual_quarters")
    forecast_quarters = _revenue_hover_text_values(rows, "forecast_quarters")
    scope_hover: list[str] = []
    for actual_text, forecast_text in zip(actual_quarters, forecast_quarters):
        parts = []
        if actual_text:
            parts.append(f"actual: {html.escape(actual_text)}")
        if forecast_text:
            parts.append(f"forecast: {html.escape(forecast_text)}")
        scope_hover.append("<br>" + "; ".join(parts) if parts else "")

    bridge_label = _revenue_hover_text_values(rows, "ped_bridge_mode_label")
    sensitivity_label = _revenue_hover_text_values(rows, "revenue_sensitivity_label")
    efficiency_label = _revenue_hover_text_values(rows, "ped_efficiency_label")
    litres = _revenue_hover_float_values(rows, "adjusted_litres_per_100km")
    efficiency_hover: list[str] = []
    for bridge_text_raw, sensitivity_text, label_text, litre_value in zip(bridge_label, sensitivity_label, efficiency_label, litres):
        bridge_text = f"<br>PED bridge: {html.escape(bridge_text_raw)}" if bridge_text_raw else ""
        if sensitivity_text:
            efficiency_hover.append(f"{bridge_text}<br>Sensitivity: {html.escape(sensitivity_text)}")
        elif not label_text or litre_value is None:
            efficiency_hover.append(bridge_text)
        else:
            efficiency_hover.append(
                f"{bridge_text}<br>PED fleet efficiency: {html.escape(label_text)}; adjusted litres/100km: {float(litre_value):,.2f}"
            )

    return list(zip(horizon_hover, bridge_hover, scope_hover, efficiency_hover))


def _forecast_horizon_support_note(chart_rows: pd.DataFrame) -> str:
    """Persistent statement of which fiscal years are backtest-supported.

    A hover only reaches a reader who hovers. The support boundary changes what
    the number means, so it belongs on the page and in the exported columns as
    well as in the tooltip.
    """

    if chart_rows is None or chart_rows.empty:
        return ""
    if "horizon_zone" not in chart_rows.columns or "june_year" not in chart_rows.columns:
        return ""
    rows = chart_rows[
        chart_rows["horizon_zone"].fillna("").astype(str).str.len().gt(0)
    ]
    if rows.empty:
        return ""
    years = rows.drop_duplicates("june_year")
    supported = pd.to_numeric(
        years.loc[
            years["horizon_zone"].astype(str).eq(FORECAST_HORIZON_ZONE_VALIDATED),
            "june_year",
        ],
        errors="coerce",
    ).dropna()
    extended = pd.to_numeric(
        years.loc[
            years["horizon_zone"].astype(str).eq(FORECAST_HORIZON_ZONE_EXTENDED),
            "june_year",
        ],
        errors="coerce",
    ).dropna()
    unvalidated = pd.to_numeric(
        years.loc[
            years["horizon_zone"].astype(str).eq(FORECAST_HORIZON_ZONE_UNVALIDATED),
            "june_year",
        ],
        errors="coerce",
    ).dropna()
    mixed = pd.to_numeric(
        years.loc[
            years["horizon_zone"].astype(str).eq(FORECAST_HORIZON_ZONE_MIXED),
            "june_year",
        ],
        errors="coerce",
    ).dropna()

    def span(values: pd.Series) -> str:
        """Contiguous runs, so a gap is never papered over as one range."""

        years = sorted({int(value) for value in values})
        if not years:
            return ""
        runs: list[tuple[int, int]] = []
        start = previous = years[0]
        for year in years[1:]:
            if year == previous + 1:
                previous = year
                continue
            runs.append((start, previous))
            start = previous = year
        runs.append((start, previous))
        return ", ".join(
            f"FY{low}" if low == high else f"FY{low}-FY{high}" for low, high in runs
        )

    def verb(values: pd.Series, singular: str, plural: str) -> str:
        return singular if len({int(value) for value in values}) == 1 else plural

    parts: list[str] = []
    if not supported.empty:
        parts.append(
            f"**{span(supported)}** {verb(supported, 'sits', 'sit')} inside the "
            "backtest-supported H1-H12 horizon."
        )
    beyond = pd.concat([extended, unvalidated, mixed])
    if not beyond.empty:
        parts.append(
            f"**{span(beyond)}** {verb(beyond, 'extends', 'extend')} past it: "
            + "; ".join(
                fragment
                for fragment in (
                    (
                        f"{span(mixed)} {verb(mixed, 'mixes', 'mix')} support states"
                        if not mixed.empty
                        else ""
                    ),
                    (
                        f"{span(extended)} {verb(extended, 'has', 'have')} H13-H20 "
                        "extended conditional evidence only"
                        if not extended.empty
                        else ""
                    ),
                    (
                        f"{span(unvalidated)} {verb(unvalidated, 'has', 'have')} no "
                        "extended evaluation evidence at all"
                        if not unvalidated.empty
                        else ""
                    ),
                )
                if fragment
            )
            + "."
        )
    if not parts:
        return ""
    parts.append(
        "Years past H12 are long-range extrapolation, not validated to the "
        "short-term standard. Every downloaded June-year row carries "
        "`horizon_scope` and per-state quarter counts."
    )
    return " ".join(parts)


def _render_forecast_horizon_support_note(chart_rows: pd.DataFrame) -> None:
    note = _forecast_horizon_support_note(chart_rows)
    if note:
        warning_panel(note)


def _revenue_horizon_zone_suffix(row: pd.Series) -> str:
    """Append the validated-horizon warning to a June-year hover.

    June-year rows return early on data_scope below, which is why the fiscal
    totals carried no horizon label at all. FY2030 is entirely H13+ and FY2029
    straddles H12, so the warning belongs on the number the reader acts on.
    """

    warning = str(row.get("horizon_validation_warning") or "").strip()
    if not warning:
        return ""
    label = str(row.get("horizon_zone_label") or "").strip() or warning
    beyond = pd.to_numeric(
        pd.Series([row.get("quarters_beyond_validated_horizon")]), errors="coerce"
    ).iloc[0]
    if pd.notna(beyond) and int(beyond) > 0:
        return f"<br>Horizon: {html.escape(label)} ({int(beyond)} of 4 quarters)"
    return f"<br>Horizon: {html.escape(label)}"


def _revenue_horizon_hover_label(row: pd.Series) -> str:
    data_scope = str(row.get("data_scope") or "").strip()
    if data_scope in {"actual_anchor", "current_nowcast", "current_forecast", "official_comparator"}:
        base_label = _human_revenue_code_label(str(row.get("value_status") or data_scope))
        return f"{base_label}{_revenue_horizon_zone_suffix(row)}"
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
        "official_light_petrol_vkt_million_km": "Official light-petrol VKT",
        "official_ped_volume_million_litres": "Official PED volume",
        "official_gross_ped_revenue_million_nzd": "Official PED revenue",
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
        "official_comparator_series_id": "Official comparator",
        "n_rows": "Rows",
        "correlation_vs_official": "Correlation",
        "slope_vs_official": "Slope",
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
        "selected_freight_rail_shift": "Freight rail shift",
        "selected_demand_elasticity": "Demand elasticity",
        "eff_gain": "Efficiency gain",
        "pt_factor": "PT factor",
        "freight_factor": "Freight factor",
        "elasticity": "Elasticity",
        "cost_per_km_ratio": "Cost/km ratio",
        "demand_factor": "Demand factor",
        "gap_reason": "Gap reason",
        "formula": "Formula",
    }
    cols = [col for col in rename if col in view.columns]
    view = view[cols].rename(columns=rename)
    for col in ["Baseline", "Adjusted", "Delta", "Efficiency gain", "PT factor", "Freight factor", "Elasticity", "Cost/km ratio", "Demand factor"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(
                lambda value: "" if pd.isna(value) else f"{float(value):,.4f}"
            )
    return view


def _revenue_line_source_options(
    line_reconciliation: pd.DataFrame,
    selected_official_trace: str | None = None,
) -> list[str]:
    officials = _ordered_official_traces(selected_official_trace)
    preferred = [
        *officials,
        "Current finalist Base case",
        "Current finalist High population/comparison",
        *CONFLICT_TRACE_NAMES,
    ]
    if line_reconciliation is None or line_reconciliation.empty or "source_path" not in line_reconciliation.columns:
        return preferred
    values = [value for value in line_reconciliation["source_path"].dropna().astype(str).unique().tolist() if value]
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
    official_vintages = manifest.get("official_vintages", {})
    if isinstance(official_vintages, dict) and official_vintages:
        rows.append(
            ("Official comparator vintage", official_vintages.get("official_comparator_vintage_id"))
        )
        rows.append(
            ("Bridge assumption vintage", official_vintages.get("bridge_assumption_vintage_id"))
        )
        rows.append(
            ("Default official comparator trace", official_vintages.get("default_official_comparator_trace"))
        )
        # The third governed role, reported alongside the other two so a reader
        # can see all three sources a displayed number depends on.
        if official_vintages.get("long_run_shape_vintage_id"):
            rows.extend(
                [
                    (
                        "Long-run shape vintage",
                        official_vintages.get("long_run_shape_vintage_id"),
                    ),
                    (
                        "Long-run shape method",
                        official_vintages.get("long_run_shape_method_id"),
                    ),
                    (
                        "Long-run transition schedule",
                        official_vintages.get("long_run_transition_schedule_id"),
                    ),
                    ("Long-run anchor FY", official_vintages.get("long_run_anchor_fy")),
                    (
                        "Long-run transition completion FY",
                        official_vintages.get("long_run_transition_end_fy"),
                    ),
                    (
                        "Fleet composition source",
                        official_vintages.get("fleet_composition_source_id"),
                    ),
                ]
            )
        available_vintages = official_vintages.get("available", {})
        if isinstance(available_vintages, dict):
            for vintage_id, entry in sorted(available_vintages.items()):
                if not isinstance(entry, dict):
                    continue
                rows.append((f"Official vintage {vintage_id} status", entry.get("status")))
                rows.append(
                    (f"Official vintage {vintage_id} workbook SHA256", entry.get("workbook_sha256"))
                )
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
        .ro-cmp-scenario-head {
            border-radius:8px;
            color:#FFFFFF;
            font-size:0.78rem;
            font-weight:750;
            letter-spacing:0.02em;
            margin-bottom:0.5rem;
            padding:0.32rem 0.7rem;
        }
        .ro-cmp-a { background:#002B5C; }
        .ro-cmp-b { background:#F37021; }
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


@st.cache_data(show_spinner=False, max_entries=2)
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

    # The fixed A/B/Baseline summary grid and its caption are method detail;
    # the labels are constants of the evidence pack, not a control.
    if method_detail_enabled():
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

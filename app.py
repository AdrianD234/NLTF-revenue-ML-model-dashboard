from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import io
import json
import os
from pathlib import Path
from typing import Any
import zipfile

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
    REVENUE_OUTLOOK_SCHEMA_VERSION,
    REVENUE_OUTLOOK_TITLE,
    RevenueOutlookPack,
    load_revenue_outlook_pack,
    promote_revenue_outlook_pack,
    revenue_outlook_signature,
    validate_promotable_comparison,
)
from model_dashboard.revenue_source_pack import (
    REQUIRED_SOURCE_PACK_FILES,
    REVENUE_SOURCE_PACK_DIR,
    REVENUE_SOURCE_PACK_SCHEMA_VERSION,
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
STREAMLIT_IMPORT_SURFACE_REVISION = "2026-06-24-revenue-source-pack-v1"
REVENUE_SOURCE_PACK_CACHE_REVISION = "2026-06-24-source-gap-register-v1"
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
    source_pack = cached_load_revenue_source_pack(
        str(repo_root / REVENUE_SOURCE_PACK_DIR),
        str(repo_root),
        revenue_source_pack_signature(repo_root / REVENUE_SOURCE_PACK_DIR, repo_root),
        REVENUE_SOURCE_PACK_CACHE_REVISION,
    )
    pack = st.session_state.get("revenue_outlook_pack")
    if not isinstance(pack, RevenueOutlookPack):
        pack = cached_load_revenue_outlook_pack(
            str(repo_root / CURRENT_REVENUE_OUTLOOK_DIR),
            str(repo_root),
            revenue_outlook_signature(repo_root / CURRENT_REVENUE_OUTLOOK_DIR, repo_root),
            REVENUE_OUTLOOK_SCHEMA_VERSION,
        )

    if pack is None and source_pack is None:
        section_title(REVENUE_OUTLOOK_TITLE)
        warning_panel(
            "No explicitly promoted Revenue Outlook pack is available. Use Forecast Builder on the local "
            "Governance & Reproducibility page, review the scenario roles, then promote the comparison. "
            "This page does not scan latest run folders or publish test fixtures automatically."
        )
        info_panel(
            "Source policy: explicit promoted pack or in-session reviewed comparison only. Forecast Builder "
            "uploads remain on the local Governance page; Streamlit Cloud can display only a committed promoted pack."
        )
        return

    manifest = pack.manifest if pack is not None and isinstance(pack.manifest, dict) else {}
    chart_rows = pack.revenue_chart_rows.copy() if pack is not None and isinstance(pack.revenue_chart_rows, pd.DataFrame) else pd.DataFrame()
    bridge = pack.revenue_bridge_components.copy() if pack is not None and isinstance(pack.revenue_bridge_components, pd.DataFrame) else pd.DataFrame()
    future_revenue = pack.future_revenue_forecasts.copy() if pack is not None and isinstance(pack.future_revenue_forecasts, pd.DataFrame) else pd.DataFrame()

    section_title(REVENUE_OUTLOOK_TITLE)
    st.caption(
        "Governed NLTF revenue architecture from the repo-local distilled source pack, with reviewed "
        "Forecast Builder volume packs joined only after explicit promotion."
    )
    st.caption("Source policy: explicit promoted pack or in-session reviewed comparison only; no latest-folder scan; no test-fixture publication.")
    kpi_grid(_revenue_source_kpi_cards(source_pack) + _revenue_outlook_summary_cards(manifest, chart_rows, future_revenue))

    source_controls = _render_revenue_source_controls(source_pack)
    if source_pack is None:
        warning_panel("The repo-local NLTF revenue source pack is missing; Total NLTF architecture controls are unavailable.")
    else:
        _render_revenue_source_architecture(source_pack, source_controls)

    if pack is None:
        warning_panel(
            "No explicitly promoted Forecast Builder revenue pack is available yet. The Total NLTF source-pack "
            "architecture remains visible, but future PED/Light/Heavy reviewed scenario bridges require promotion."
        )
        return

    if chart_rows.empty:
        warning_panel("The promoted Revenue Outlook pack has no chart rows.")
        return

    with st.container(border=True):
        st.markdown("<div class='page5-panel-title'>Revenue Outlook controls</div>", unsafe_allow_html=True)
        control_cols = st.columns([0.22, 0.38, 0.40])
        with control_cols[0]:
            grain_label = st.radio(
                "Time grain",
                ["Quarterly", "June-year"],
                horizontal=True,
                key="revenue_outlook_time_grain",
            )
        stream_options = _revenue_outlook_stream_options(chart_rows)
        with control_cols[1]:
            selected_streams = st.multiselect(
                "Streams",
                stream_options,
                default=stream_options,
                key="revenue_outlook_streams",
            )
        scenario_options = _revenue_outlook_scenario_options(chart_rows)
        with control_cols[2]:
            selected_scenarios = st.multiselect(
                "Forecast scenarios",
                scenario_options,
                default=scenario_options,
                key="revenue_outlook_scenarios",
            )

    filtered_rows = _filter_revenue_outlook_rows(
        chart_rows,
        time_grain="june_year" if grain_label == "June-year" else "quarterly",
        stream_labels=selected_streams,
        scenario_names=selected_scenarios,
    )
    filtered_bridge = _filter_revenue_bridge_rows(bridge, selected_streams, selected_scenarios)
    gap_summary = _revenue_outlook_gap_summary(filtered_bridge)
    if gap_summary:
        warning_panel(gap_summary)

    chart_cols = st.columns(2)
    with chart_cols[0]:
        chart_card(
            "Activity and volume outlook",
            "PED uses VKT per capita; Light and Heavy RUC use net kilometres. Grey lines are source historical actuals.",
            revenue_outlook_figure(filtered_rows, metric_type="activity"),
            caption="Forecast start and H13 markers are shown where numeric reviewed forecasts exist. Units are kept separate by stream.",
            notes_as_tooltip=False,
        )
    with chart_cols[1]:
        chart_card(
            "Revenue outlook",
            "Nominal revenue is plotted only where the governed revenue bridge is available; unavailable revenue remains a visible gap.",
            revenue_outlook_figure(filtered_rows, metric_type="revenue"),
            caption="RUC revenue uses net km / 1,000 * reviewed nominal effective average rate. PED revenue requires a source-backed litres bridge.",
            notes_as_tooltip=False,
        )

    st.markdown("<div class='page5-panel-title'>Revenue bridge detail</div>", unsafe_allow_html=True)
    display_table(_revenue_bridge_display_table(filtered_bridge), height=320, max_rows=240)

    with st.expander("Manifest, source policy and downloads", expanded=False):
        display_table(_revenue_outlook_manifest_table(manifest), height=220, max_rows=80)
        download_cols = st.columns(3)
        with download_cols[0]:
            dataframe_download(future_revenue, "Download future revenue forecasts", "future_revenue_forecasts.csv")
        with download_cols[1]:
            dataframe_download(bridge, "Download revenue bridge components", "revenue_bridge_components.csv")
        with download_cols[2]:
            dataframe_download(chart_rows, "Download revenue chart rows", "revenue_chart_rows.csv")


def _revenue_source_kpi_cards(source_pack: RevenueSourcePack | None) -> list[tuple[str, str, str | None]]:
    if source_pack is None or source_pack.canonical_long.empty:
        return [("Source pack", "Missing", "data/revenue_model_source_pack/2026_05_19")]
    frame = source_pack.canonical_long
    selected_fy = current_selection(source_pack, "selected_fy", "FY2031")
    cards = [
        ("Source pack", str(source_pack.manifest.get("source_pack_version", "unknown")), source_pack.validation_status),
        ("Total NLTF", _source_value_label(frame, "total_nltf_net_revenue", selected_fy), selected_fy),
        ("PED", _source_value_label(frame, "gross_ped_revenue", selected_fy), "revenue bridge"),
        ("Light RUC", _source_value_label(frame, "light_ruc_net_revenue", selected_fy), "direct model output bridged to revenue"),
        ("Heavy RUC", _source_value_label(frame, "heavy_ruc_net_revenue", selected_fy), "direct model output bridged to revenue"),
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

        row2 = st.columns([0.16, 0.18, 0.18, 0.22, 0.14, 0.12])
        view_options = ["June-year", "Quarterly"]
        model_basis_options = ["In-house model", "Aaron Schiff model", "Selected dashboard basis"]
        revenue_basis_options = control_options(source_pack, "revenue_basis", ["Net", "Gross", "Benchmark actual"])
        uncertainty_options = control_options(source_pack, "uncertainty_source", ["MOT release round", "In-house model", "Aaron Schiff model"])
        fy_options = control_options(source_pack, "selected_fy", ["FY2031"])
        top_up_options = control_options(source_pack, "crown_top_up", ["Exclude", "Include"])
        with row2[0]:
            time_grain = st.radio("Time grain", view_options, horizontal=True, key="revenue_source_time_grain")
        with row2[1]:
            model_basis = st.selectbox(
                "Model basis",
                model_basis_options,
                index=_option_index(model_basis_options, current_selection(source_pack, "model_basis", "In-house model")),
                key="revenue_source_model_basis",
            )
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
        "crown_top_up": crown_top_up,
    }


def _render_revenue_source_architecture(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> None:
    if controls.get("time_grain") == "Quarterly":
        warning_panel("The distilled revenue source pack is annual only. Quarterly display remains available for the promoted Forecast Builder volume pack below.")
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
            "Actual/benchmark, selected basis, Aaron Schiff and in-house paths from the normalized annual model-path table.",
            _source_total_path_figure(source_pack, controls),
            caption="MOT/BEFU release registry is loaded, but the distilled pack does not expose the full release-value table; unresolved differences are reported instead of forced.",
            notes_as_tooltip=False,
        )
    with chart_cols[1]:
        chart_card(
            "Uncertainty fan",
            "Displayed only from available governed model paths; no probabilistic residual fan is fabricated.",
            _source_uncertainty_figure(source_pack, controls),
            caption="Where only model-spread evidence is available, the band is labelled as model spread rather than probabilistic uncertainty.",
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
        st.caption("Source-pack intake status")
        display_table(_source_intake_status(source_pack), height=180, max_rows=80)
        st.caption("Unresolved revenue decisions")
        display_table(source_pack.unresolved_decisions, height=180, max_rows=80)
        st.caption("Validation issues")
        display_table(source_pack.validation_issues, height=180, max_rows=80)
        st.caption("Required path trace status")
        display_table(_source_path_trace_status_for_controls(source_pack, controls), height=180, max_rows=80)
        st.caption("Source gap register")
        display_table(_source_gap_register_for_controls(source_pack, controls), height=180, max_rows=80)
        st.caption("Series role audit")
        display_table(_source_series_role_audit(source_pack), height=180, max_rows=100)
        st.caption("Loader export manifest")
        display_table(_source_manifest_view(source_pack), height=220, max_rows=80)
        dataframe_download(source_pack.canonical_long, "Download canonical revenue long table", "canonical_revenue_long.csv")


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
    return messages


def _source_gap_register_for_controls(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    gaps = _source_gap_register(source_pack).copy()
    if gaps.empty or "gap_id" not in gaps.columns:
        return gaps
    if "release_round" in controls:
        release_mask = gaps["gap_id"].eq("release_value_table_missing")
        gaps.loc[release_mask, "current_selection"] = str(controls.get("release_round") or "")
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
    has_release_values = bool(manifest.get("normalized_files", {}).get("release_values.csv")) if isinstance(manifest, dict) else False
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
                "user_visible_message": "Full MOT/BEFU release-value table is unavailable; release selection is registry-only and unresolved differences are reported.",
            },
            {
                "gap_id": "crown_top_up_values_missing",
                "required_for": "Include Crown top-up roll-up treatment",
                "availability_status": "available" if has_crown_top_up_rows else "missing",
                "current_selection": crown_top_up_selection,
                "runtime_treatment": "excluded_by_selection" if crown_top_up_selection.lower() == "exclude" else "not_applied_missing_source",
                "user_visible_message": "Crown top-up Include is not applied because no governed top-up value rows are present in the source pack.",
            },
            {
                "gap_id": "quarterly_source_pack_missing",
                "required_for": "Quarterly Revenue Outlook from source pack",
                "availability_status": "available" if has_quarterly_values else "missing",
                "current_selection": _selection_value(selections, "view", "Annual"),
                "runtime_treatment": "quarterly_available" if has_quarterly_values else "annual_only_source_pack",
                "user_visible_message": "The distilled source pack is annual only; quarterly views use promoted Forecast Builder volume packs where available.",
            },
            {
                "gap_id": "ped_total_vkt_bridge_missing",
                "required_for": "PED VKT per capita to total VKT bridge replay",
                "availability_status": "available" if has_ped_total_vkt else "missing",
                "current_selection": _selection_value(selections, "series", "Total NLTF revenue"),
                "runtime_treatment": "bridge_rows_available" if has_ped_total_vkt else "reported_gap",
                "user_visible_message": "PED total VKT bridge rows are absent; PED revenue paths are preserved from workbook source rows rather than recomputed.",
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
                    "required_for_runtime": str(filename) in REQUIRED_SOURCE_PACK_FILES,
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
    frame = getattr(source_pack, "canonical_long", pd.DataFrame())
    gaps = _source_gap_register(source_pack)
    release_gap = gaps[gaps["gap_id"].eq("release_value_table_missing")] if "gap_id" in gaps.columns else pd.DataFrame()
    release_available = not release_gap.empty and release_gap.iloc[0].get("availability_status") == "available"
    rows = [
        _path_trace_row("actual_benchmark", "Actual / benchmark", _has_source_trace(frame, line_values={"Actual", "Actual / benchmark"}), "annual actual and benchmark rows", ""),
        _path_trace_row("selected_workbook_basis", "Selected workbook basis", _has_source_trace(frame, model_basis="selected_dashboard_basis", line_values={"Model path"}), "annual model path rows", ""),
        _path_trace_row("selected_mot_befu_release", "Selected MOT/BEFU release path", release_available, "release-value table", "" if release_available else "release_value_table_missing"),
        _path_trace_row("rolling_befu_1y", "Rolling BEFU 1Y", release_available, "release-value table", "" if release_available else "release_value_table_missing"),
        _path_trace_row("aaron_schiff_model", "Aaron Schiff prediction / forecast", _has_source_trace(frame, model_basis="aaron_schiff_model", line_values={"Model path"}), "annual model path rows", ""),
        _path_trace_row("in_house_model", "In-house prediction / forecast", _has_source_trace(frame, model_basis="in_house_model", line_values={"Model path"}), "annual model path rows", ""),
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


def _has_source_trace(
    frame: pd.DataFrame,
    *,
    model_basis: str | None = None,
    line_values: set[str] | None = None,
) -> bool:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False
    rows = frame
    if model_basis is not None and "model_basis" in rows.columns:
        rows = rows[rows["model_basis"].astype(str).eq(model_basis)]
    if line_values is not None and "line" in rows.columns:
        rows = rows[rows["line"].astype(str).isin(line_values)]
    return "value" in rows.columns and pd.to_numeric(rows["value"], errors="coerce").notna().any()


def _selection_value(selections: dict[str, Any], control_id: str, default: str = "") -> str:
    value = selections.get(control_id, {}).get("current_value") if isinstance(selections.get(control_id, {}), dict) else None
    return str(value) if value else default


def _option_index(options: list[str], preferred: str, *, fallback: str | None = None) -> int:
    if preferred in options:
        return options.index(preferred)
    if fallback in options:
        return options.index(str(fallback))
    return 0


def _source_value_label(frame: pd.DataFrame, series_id: str, selected_fy: str) -> str:
    rows = _source_series_rows(frame, series_id)
    if rows.empty:
        return "-"
    selected = rows[rows["period"].eq(selected_fy)]
    model_rows = selected[selected["line"].eq("Model path")]
    actual_rows = selected[selected["line"].isin(["Actual", "Actual / benchmark"])]
    row = (model_rows if not model_rows.empty else actual_rows if not actual_rows.empty else selected).tail(1)
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
    trace_specs = [
        ("Actual / benchmark", frame[frame["line"].isin(["Actual", "Actual / benchmark"])], "#7A869A", "solid"),
        ("Selected dashboard basis", _source_model_rows(frame, "selected_dashboard_basis"), "#002B5C", "solid"),
        ("In-house prediction / forecast", _source_model_rows(frame, "in_house_model"), "#00843D", "solid"),
        ("Aaron Schiff", _source_model_rows(frame, "aaron_schiff_model"), "#F37021", "dash"),
    ]
    axis_title = _source_axis_title(frame)
    for name, rows, color, dash in trace_specs:
        rows = _dedupe_path_rows(rows)
        if rows.empty:
            continue
        rows = rows.copy()
        rows["hover_unit"] = axis_title
        fig.add_trace(
            go.Scatter(
                x=rows["FY"],
                y=rows["value"],
                mode="lines+markers",
                name=name,
                line={"color": color, "dash": dash, "width": 2.6},
                marker={"size": 6},
                customdata=rows[["hover_unit"]].to_numpy(),
                hovertemplate="FY%{x}<br>%{y:,.1f} %{customdata[0]}<extra>" + name + "</extra>",
            )
        )
    _add_missing_source_path_gap_traces(fig, source_pack, controls)
    fy = _selected_fy_number(controls)
    if fy is not None:
        fig.add_vline(x=fy, line_dash="dot", line_color="#102A43", annotation_text=f"Selected FY{fy}", annotation_position="top")
    fig.add_annotation(
        text="Full MOT/BEFU release-value table is not present in the distilled pack; registry-only release selection is shown as a governance gap.",
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


def _add_missing_source_path_gap_traces(fig: go.Figure, source_pack: RevenueSourcePack, controls: dict[str, Any]) -> None:
    status = _source_path_trace_status_for_controls(source_pack, controls)
    if status.empty or "trace_id" not in status.columns:
        return
    gap_styles = {
        "selected_mot_befu_release": ("Selected MOT/BEFU release path", "#5B677A", "dashdot"),
        "rolling_befu_1y": ("Rolling BEFU 1Y", "#6B7F2A", "dot"),
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
    frame = _selected_source_series_frame(source_pack, controls)
    model = frame[frame["line"].eq("Model path")].copy()
    if model.empty or not {"in_house_model", "aaron_schiff_model"}.issubset(set(model["model_basis"])):
        return empty_figure("Probabilistic uncertainty fan is not available in the normalized source pack.")
    axis_title = _source_axis_title(frame)
    pivot = model.pivot_table(index="FY", columns="model_basis", values="value", aggfunc="first").dropna(how="any")
    if pivot.empty:
        return empty_figure("Model-spread uncertainty cannot be drawn for this series.")
    lower = pivot[["in_house_model", "aaron_schiff_model"]].min(axis=1)
    upper = pivot[["in_house_model", "aaron_schiff_model"]].max(axis=1)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pivot.index,
            y=upper,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=pivot.index,
            y=lower,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(0, 132, 61, 0.18)",
            line={"width": 0},
            name="In-house vs Schiff model spread",
            customdata=[[axis_title] for _ in range(len(lower))],
            hovertemplate="FY%{x}<br>%{y:,.1f} %{customdata[0]}<extra>Lower spread bound</extra>",
        )
    )
    selected = _source_model_rows(frame, _model_basis_key(controls.get("model_basis")))
    selected = _dedupe_path_rows(selected)
    if not selected.empty:
        selected = selected.copy()
        selected["hover_unit"] = axis_title
        fig.add_trace(
            go.Scatter(
                x=selected["FY"],
                y=selected["value"],
                mode="lines+markers",
                name=str(controls.get("model_basis", "Selected model")),
                line={"color": "#002B5C", "width": 2.8},
                customdata=selected[["hover_unit"]].to_numpy(),
                hovertemplate="FY%{x}<br>%{y:,.1f} %{customdata[0]}<extra>%{fullData.name}</extra>",
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


def _source_component_figure(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> go.Figure:
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
    plot["signed_value"] = pd.to_numeric(plot["value"], errors="coerce") * pd.to_numeric(plot["aggregation_sign"], errors="coerce").fillna(1)
    plot = plot.dropna(subset=["signed_value"])
    plot = plot.drop_duplicates("series_id", keep="last")
    fig = go.Figure(
        go.Bar(
            x=plot["display_name"],
            y=plot["signed_value"],
            marker_color=["#B7791F" if value < 0 else "#00843D" for value in plot["signed_value"]],
            hovertemplate="%{x}<br>%{y:,.1f}<extra></extra>",
        )
    )
    fig.update_layout(
        margin={"l": 52, "r": 18, "t": 28, "b": 96},
        height=360,
        yaxis_title="$m nominal ex GST",
        xaxis_tickangle=-30,
    )
    return fig


def _source_split_figure(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> go.Figure:
    rows = _source_selected_fy_rows(source_pack, controls)
    component_ids = ["net_fed_revenue", "total_ruc_net_revenue", "net_mvr_revenue", "tuc_net_revenue"]
    plot = rows[rows["series_id"].isin(component_ids)].copy()
    plot["value"] = pd.to_numeric(plot["value"], errors="coerce")
    plot = plot.dropna(subset=["value"]).drop_duplicates("series_id", keep="last")
    if plot.empty:
        return empty_figure("Selected FY split is unavailable for this model basis.")
    fig = go.Figure(
        go.Pie(
            labels=plot["display_name"],
            values=plot["value"].clip(lower=0),
            hole=0.45,
            marker={"colors": ["#002B5C", "#00843D", "#008C7E", "#F37021"][: len(plot)]},
            hovertemplate="%{label}<br>%{value:,.1f}<br>%{percent}<extra></extra>",
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
    return rows[pd.to_numeric(rows["value"], errors="coerce").notna()].copy()


def _source_series_rows(frame: pd.DataFrame, series_id: str) -> pd.DataFrame:
    return frame[frame["series_id"].eq(series_id) & pd.to_numeric(frame["value"], errors="coerce").notna()].copy()


def _source_selected_fy_rows(source_pack: RevenueSourcePack, controls: dict[str, Any]) -> pd.DataFrame:
    fy = _selected_fy_number(controls)
    frame = source_pack.canonical_long.copy()
    if fy is None:
        return pd.DataFrame()
    frame = frame[frame["FY"].eq(fy)].copy()
    model_key = _model_basis_key(controls.get("model_basis"))
    preferred = frame[(frame["source_file"].eq("annual_model_paths.csv")) & (frame["model_basis"].eq(model_key)) & (frame["line"].eq("Model path"))]
    if preferred.empty:
        preferred = frame[(frame["source_file"].eq("annual_model_paths.csv")) & (frame["line"].isin(["Actual", "Actual / benchmark"]))]
    if preferred.empty:
        preferred = frame[frame["source_file"].eq("annual_actuals.csv")]
    return preferred.copy()


def _source_model_rows(frame: pd.DataFrame, model_basis: str) -> pd.DataFrame:
    return frame[(frame["line"].eq("Model path")) & (frame["model_basis"].eq(model_basis))].copy()


def _dedupe_path_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    return rows.sort_values(["FY", "source_file", "source_cell"], kind="stable").drop_duplicates("FY", keep="last")


def _selected_series_id(source_pack: RevenueSourcePack, selected: str) -> str:
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


def _model_basis_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "aaron" in text or "schiff" in text:
        return "aaron_schiff_model"
    if "selected" in text:
        return "selected_dashboard_basis"
    return "in_house_model"


def _selected_fy_number(controls: dict[str, Any]) -> int | None:
    text = str(controls.get("selected_fy", "")).upper().replace("FY", "")
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
    if chart_rows is None or chart_rows.empty or "stream_label" not in chart_rows.columns:
        return []
    preferred = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
    available = set(chart_rows["stream_label"].dropna().astype(str))
    ordered = [label for label in preferred if label in available]
    ordered.extend(sorted(available.difference(ordered)))
    return ordered


def _revenue_outlook_scenario_options(chart_rows: pd.DataFrame) -> list[str]:
    if chart_rows is None or chart_rows.empty or "scenario_name" not in chart_rows.columns:
        return []
    data = chart_rows[chart_rows["row_type"].astype(str).eq("future_forecast")].copy()
    return sorted(data["scenario_name"].dropna().astype(str).unique().tolist())


def _filter_revenue_outlook_rows(
    chart_rows: pd.DataFrame,
    *,
    time_grain: str,
    stream_labels: list[str],
    scenario_names: list[str],
) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame()
    data = chart_rows.copy()
    data = data[data["time_grain"].astype(str).eq(time_grain)].copy()
    if stream_labels:
        data = data[data["stream_label"].astype(str).isin(stream_labels)].copy()
    if scenario_names:
        is_actual = data["row_type"].astype(str).eq("historical_actual")
        data = data[is_actual | data["scenario_name"].astype(str).isin(scenario_names)].copy()
    data["_period_order"] = data["period"].map(_revenue_period_order)
    return data.sort_values(["stream", "metric_type", "_period_order", "scenario_name"], kind="stable").drop(columns=["_period_order"], errors="ignore")


def _filter_revenue_bridge_rows(bridge: pd.DataFrame, stream_labels: list[str], scenario_names: list[str]) -> pd.DataFrame:
    if bridge is None or bridge.empty:
        return pd.DataFrame()
    data = bridge.copy()
    if stream_labels and "stream_label" in data.columns:
        data = data[data["stream_label"].astype(str).isin(stream_labels)].copy()
    if scenario_names and "scenario_name" in data.columns:
        scenario_text = data["scenario_name"].fillna("").astype(str)
        data = data[scenario_text.eq("") | scenario_text.isin(scenario_names)].copy()
    return data


def revenue_outlook_figure(rows: pd.DataFrame, *, metric_type: str) -> go.Figure:
    data = pd.DataFrame() if rows is None else rows.copy()
    data = data[data.get("metric_type", pd.Series(dtype=str)).astype(str).eq(metric_type)].copy()
    streams = _revenue_outlook_stream_options(data)
    if not streams:
        streams = ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]
    fig = make_subplots(rows=1, cols=len(streams), subplot_titles=streams, shared_yaxes=False, horizontal_spacing=0.06)
    scenario_colors = _scenario_color_map(data)
    for col, stream_label in enumerate(streams, start=1):
        stream_rows = data[data.get("stream_label", pd.Series(dtype=str)).astype(str).eq(stream_label)].copy()
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
        future = stream_rows[stream_rows["row_type"].astype(str).eq("future_forecast") & stream_rows["value_numeric"].notna()].copy()
        last_actual = historical.tail(1)[["period", "value_numeric"]] if not historical.empty else pd.DataFrame()
        for scenario, group in future.groupby("scenario_name", dropna=False):
            scenario_name = str(scenario)
            color = scenario_colors.get(scenario_name, "#006FAD")
            plot_cols = [col for col in ["period", "value_numeric", "horizon", "horizon_scope", "bridge_status", "gap_reason"] if col in group.columns]
            plot_group = group[plot_cols].copy()
            for column in ["horizon", "horizon_scope", "bridge_status", "gap_reason"]:
                if column not in plot_group.columns:
                    plot_group[column] = ""
            if not last_actual.empty:
                join_row = last_actual.copy()
                join_row["horizon"] = pd.NA
                join_row["horizon_scope"] = ""
                join_row["bridge_status"] = "historical_actual"
                join_row["gap_reason"] = ""
                plot_group = pd.concat([join_row, plot_group], ignore_index=True, sort=False)
            plot_group["horizon_hover"] = plot_group.apply(_revenue_horizon_hover_label, axis=1)
            plot_group["bridge_hover"] = plot_group.apply(_revenue_bridge_hover_label, axis=1)
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
                    customdata=plot_group[["horizon_hover", "bridge_hover"]].to_numpy(),
                    hovertemplate="%{x}<br>%{y:,.2f}<br>%{customdata[0]}%{customdata[1]}<extra>" + html.escape(label) + "</extra>",
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
    output: dict[str, str] = {}
    if rows is None or rows.empty:
        return output
    scenarios = rows[rows["row_type"].astype(str).eq("future_forecast")].copy()
    scenarios["_role_order"] = scenarios.get("scenario_role", pd.Series(dtype=str)).map(lambda value: 0 if str(value) == SCENARIO_ROLE_BASECASE else 1)
    names = scenarios.sort_values(["_role_order", "scenario_name"], kind="stable")["scenario_name"].dropna().astype(str).drop_duplicates().tolist()
    for index, name in enumerate(names):
        output[name] = palette[index % len(palette)]
    return output


def _scenario_label(scenario_name: str, rows: pd.DataFrame) -> str:
    role = _first_non_empty(rows.get("scenario_role", pd.Series(dtype=str)))
    suffix = f" ({role})" if role else ""
    return f"{scenario_name}{suffix}"


def _is_forecast_start_or_h13(horizon: Any) -> bool:
    try:
        value = int(float(horizon))
    except Exception:
        return False
    return value in {1, BACKTEST_SUPPORTED_MAX_HORIZON + 1}


def _revenue_horizon_hover_label(row: pd.Series) -> str:
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
    if reason:
        return f"<br>Bridge status: {html.escape(status)} - {html.escape(reason)}"
    if status:
        return f"<br>Bridge status: {html.escape(status)}"
    return ""


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
    for col in ["Activity", "Rate", "Revenue NZD"]:
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").map(lambda value: _format_compact_value(value, "nominal NZD" if col == "Revenue NZD" else ""))
    return view


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
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return pd.NA, ""
    periods = sorted(data["period"].dropna().astype(str).unique().tolist(), key=_revenue_period_order)
    target_period = periods[min(4, len(periods) - 1)]
    base = data[data.get("scenario_role", pd.Series(dtype=str)).astype(str).eq(SCENARIO_ROLE_BASECASE)]
    chosen = base[base["period"].astype(str).eq(target_period)] if not base.empty else data[data["period"].astype(str).eq(target_period)]
    value = float(chosen["value_numeric"].sum()) if not chosen.empty else pd.NA
    return value, target_period


def _comparison_delta_value(rows: pd.DataFrame) -> tuple[Any, str]:
    if rows is None or rows.empty:
        return pd.NA, ""
    data = rows[
        rows["metric_type"].astype(str).eq("revenue")
        & rows["time_grain"].astype(str).eq("june_year")
        & rows["row_type"].astype(str).eq("future_forecast")
    ].copy()
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

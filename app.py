from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
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
from model_dashboard.labels import (
    DEFAULT_INPUT_PARENT,
    IGNORED_RUN_FOLDER_NAMES,
    OVERVIEW_STRESS_BUCKET_ORDER,
    SCHIFF_SPEC_BENCHMARK_LABEL,
    STRESS_BUCKET_ORDER,
    TERM_HELP,
    format_count,
    format_percent,
    is_legacy_schiff_style_text,
    model_alias,
    shorten_model_name,
)
from model_dashboard.light_ruc_reproducibility import (
    reproducibility_coefficients_view,
    reproducibility_component_trace_view,
    reproducibility_feature_importance_view,
    reproducibility_ensemble_equation,
    reproducibility_ensemble_weight_view,
    reproducibility_pack_signature,
    reproducibility_registry_view,
    reproducibility_replay_summary,
    reproducibility_sensitivity_view,
    reproducibility_stream_labels,
    reproducibility_training_window_view,
    load_reproducibility_pack,
    plot_reproducibility_feature_importance,
    plot_reproducibility_sensitivities,
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
    footer_strip,
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
CURATED_DATA_DIR = Path("artifacts") / "curated_data"


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


def directory_signature(path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (False, 0, 0)
    return (path.exists(), int(stat.st_mtime_ns), int(stat.st_size))


def main() -> None:
    st.set_page_config(page_title="NTLF Revenue Modelling", layout="wide", initial_sidebar_state="collapsed")
    inject_theme()
    pages = ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark"]
    st.session_state.setdefault("gov_page", "Overview")
    if st.session_state["gov_page"] not in pages:
        st.session_state["gov_page"] = "Overview"
    header_slot = st.empty()
    initial_page = st.session_state["gov_page"]
    initial_index = pages.index(initial_page) + 1
    with header_slot.container():
        header(
            "NTLF Revenue Modelling",
            "Transport Revenue Model Testbench | Refined finalist models | actual-driver Stage 1 evidence.",
            page_chip=f"Page {initial_index} of 4 - {initial_page}",
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
            "Transport Revenue Model Testbench | Refined finalist models | actual-driver Stage 1 evidence.",
            page_chip=f"Page {current_index} of 4 - {current_page}",
        )
    controls = render_filter_sidebar(loaded)
    controls = render_top_filter_bar(loaded, controls)

    if current_page == "Overview":
        render_overview(loaded, controls)
    elif current_page == "Diagnostics":
        render_diagnostics(loaded, controls)
    elif current_page == "Scenario Comparison":
        render_scenario_comparison(loaded, controls)
    else:
        render_schiff_benchmark_page(loaded, controls)
    footer_strip("Transport Revenue Model Testbench | Refined Finalist Models", run_footer_label(loaded))


def render_primary_navigation(pages: list[str]) -> str:
    return st.radio(
        "Governance pages",
        pages,
        horizontal=True,
        key="gov_page",
        label_visibility="collapsed",
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
        "top_baseline": "Finalist",
        "top_horizon": "1-12 qtrs",
        "top_score_basis": PAPER_SCORE_LABEL,
        "top_vintage": "Latest",
        "top_date_window": "All",
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
        "top_baseline": baseline_options,
        "top_horizon": horizon_options,
        "top_score_basis": SCORE_BASIS_OPTIONS,
        "top_vintage": ["Latest"],
        "top_date_window": date_options,
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
        filter_cols = st.columns([1.0, 1.12, 0.72, 1.0, 1.15, 0.86, 0.9, 0.94, 0.68, 0.46])
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
                "Baseline",
                baseline_options,
                key="top_baseline",
                format_func=lambda value: {"Finalist": "Refined Finalist", "Schiff": SCHIFF_SPEC_BENCHMARK_LABEL}.get(str(value), str(value)),
            )
        with filter_cols[4]:
            st.selectbox(
                "Horizon",
                horizon_options,
                key="top_horizon",
                format_func=lambda value: "1-12 Quarters" if value == "1-12 qtrs" else str(value).replace("qtrs", "quarters"),
            )
        with filter_cols[5]:
            st.selectbox(
                "Forecast Vintage",
                ["Latest"],
                key="top_vintage",
                help="Stage 1 actual-driver runs use the latest realised-driver evidence; vintage input forecasts are tested later.",
            )
        with filter_cols[6]:
            st.selectbox(
                "Date Window",
                date_options,
                key="top_date_window",
                format_func=lambda value: "All target periods" if value == "All" else str(value),
            )
        with filter_cols[7]:
            st.selectbox(
                "Score Basis",
                SCORE_BASIS_OPTIONS,
                key="top_score_basis",
                help="Default governance reporting uses paper-style horizon MAPE. Operational pooled MAPE is available explicitly for operational scorecard checks.",
            )
        with filter_cols[8]:
            st.button(
                "Reset Filters",
                type="primary",
                use_container_width=True,
                on_click=reset_top_filter_state,
                args=(defaults,),
            )
        with filter_cols[9]:
            with st.popover("More", use_container_width=True):
                controls = render_advanced_controls(loaded, controls)

        stream_choice = st.session_state["top_stream"]
        family_choice = st.session_state["top_family"]
        stage_choice = st.session_state["top_stage"]
        baseline_choice = st.session_state["top_baseline"]
        score_basis_choice = st.session_state["top_score_basis"]
        horizon_choice = st.session_state["top_horizon"]
        vintage_choice = st.session_state["top_vintage"]
        date_choice = st.session_state["top_date_window"]
        baseline_label = {
            "Finalist": "Refined Finalist",
            "Schiff": SCHIFF_SPEC_BENCHMARK_LABEL,
        }.get(str(baseline_choice), str(baseline_choice))
        horizon_label = "1-12 Quarters" if horizon_choice == "1-12 qtrs" else str(horizon_choice).replace("qtrs", "quarters")
        date_label = "All target periods" if date_choice == "All" else str(date_choice)
        filter_items = [
            ("Stream", "All Streams" if stream_choice == "All" else stream_choice),
            ("Model Family", "All Families" if family_choice == "All" else str(family_choice).replace("_", " ")),
            ("Stage", "All stages" if stage_choice == "all" else str(stage_choice).replace("_", " ").title()),
            ("Baseline", baseline_label),
            ("Score Basis", score_basis_choice),
            ("Horizon", horizon_label),
            ("Forecast Vintage", vintage_choice),
            ("Date Window", date_label),
        ]
        active_filter_line = " | ".join(f"{label}: {value}" for label, value in filter_items)

        view_state = {
            "run_folder": str(loaded.run_dir),
            "run_name": Path(str(loaded.run_dir)).name,
            "stream": "All Streams" if stream_choice == "All" else stream_choice,
            "model_family": "All Families" if family_choice == "All" else family_choice,
            "stage": stage_choice,
            "baseline": baseline_label,
            "score_basis": score_basis_choice,
            "horizon": horizon_label,
            "forecast_vintage": vintage_choice,
            "date_window": date_label,
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
    updated["baseline"] = baseline_label
    updated["score_basis"] = score_basis_key(score_basis_choice)
    updated["score_basis_label"] = score_basis_label(score_basis_choice)
    updated["horizon_bucket_filter"] = [] if horizon_choice == "1-12 qtrs" else [horizon_choice]
    updated["date_window"] = "All target periods" if date_choice == "All" else date_choice
    updated["forecast_vintage"] = vintage_choice
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
        "scenario_a_choice",
        "scenario_b_choice",
        "scenario_baseline_choice",
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


def selected_horizon_frame(loaded: LoadedRun, controls: dict[str, Any]) -> pd.DataFrame:
    source = loaded.data.get("scorecard_horizon_df", pd.DataFrame())
    if source is None or source.empty:
        source = loaded.data.get("horizon_df", pd.DataFrame())
    return filter_score_basis_rows(source, controls.get("score_basis", PAPER_SCORE_BASIS))


def selected_stress_frame(loaded: LoadedRun, controls: dict[str, Any]) -> pd.DataFrame:
    source = loaded.data.get("scorecard_stress_df", pd.DataFrame())
    if source is None or source.empty:
        source = loaded.data.get("stress", pd.DataFrame())
    return filter_score_basis_rows(source, controls.get("score_basis", PAPER_SCORE_BASIS))


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

    candidate_mode = st.session_state.get("candidate_frontier_mode", DEFAULT_CANDIDATE_FRONTIER_MODE)
    if candidate_mode == LEGACY_CANDIDATE_FRONTIER_MODE:
        candidate_mode = DEFAULT_CANDIDATE_FRONTIER_MODE
        st.session_state["candidate_frontier_mode"] = candidate_mode
    candidate_landscape = build_candidate_landscape_frame(loaded, controls, candidate_mode)
    candidate_context = candidate_frontier_count_context(loaded, controls, candidate_landscape)
    gov_kpi_grid(overview_kpi_cards(summary, recommended, story, errors, candidate_context, schiff_rows=schiff_rows))
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
        if not mapping.empty:
            st.caption("Component labels are deliberately short for the management view.")
    with lower[1]:
        chart_card(
            "4. Stress and Horizon Checks",
            overview_stress_subtitle(controls),
            compact_figure(plot_stress_checks(stress_frame), 260),
            overview_stress_watch_note(stress_frame),
        )

    with st.expander("Management conclusion and stream decision detail", expanded=False):
        title, narrative, decision_cards = enterprise_decision_brief(story, loaded)
        decision_brief(title, narrative, decision_cards)
        info_panel("Manager conclusion: " + manager_conclusion(story))
        warning_panel(data_quality_warning_readout(loaded, story))
        governance_cards(story)
        display_decision_status(story)


def compact_figure(fig: Any, height: int, showlegend: bool | None = None) -> Any:
    if hasattr(fig, "update_layout"):
        has_subplot_titles = bool(getattr(fig.layout, "annotations", None))
        top_margin = 42 if has_subplot_titles else 18
        fig.update_layout(title_text="", height=height, margin={"l": 30, "r": 14, "t": top_margin, "b": 30})
        fig.update_layout(
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.12 if has_subplot_titles else 1.0,
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
    mode_options = [DEFAULT_CANDIDATE_FRONTIER_MODE, "Competitive frontier", "Top candidates only", "Show outliers"]
    if st.session_state.get("candidate_frontier_mode") in {LEGACY_CANDIDATE_FRONTIER_MODE, PREVIOUS_CANDIDATE_FRONTIER_MODE}:
        st.session_state["candidate_frontier_mode"] = DEFAULT_CANDIDATE_FRONTIER_MODE
    mode = st.selectbox(
        "Candidate frontier mode",
        mode_options,
        key="candidate_frontier_mode",
        label_visibility="collapsed",
    )
    return build_candidate_landscape_frame(loaded, controls, mode)


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


def diagnostic_kpi_cards(diagnostic_df: pd.DataFrame) -> list[tuple[str, str, str, str, str, str]]:
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
    adj_r2 = pd.to_numeric(finalists.get("adj_r2", pd.Series(dtype=float)), errors="coerce").mean()
    bp = pd.to_numeric(finalists.get("breusch_pagan_pvalue", pd.Series(dtype=float)), errors="coerce")
    white = pd.to_numeric(finalists.get("white_pvalue", pd.Series(dtype=float)), errors="coerce")
    pass_mask = (bp > 0.05) | (white > 0.05)
    hetero_pass = int(pass_mask.fillna(False).sum())
    hetero_total = int(max(len(finalists), 0))
    return [
        ("Diagnostics Coverage", f"{available}/9", "diagnostic fields available", "", "good" if available >= 6 else "mixed", "D"),
        ("Mean Durbin-Watson", f"{dw:.2f}" if pd.notna(dw) else "-", "Current finalists only; near 2.0 is ideal", "", "good", "DW"),
        ("Mean calibration R2", f"{adj_r2:.2f}" if pd.notna(adj_r2) else "-", "Current finalists only; Mincer-Zarnowitz calibration", "", "good", "R2"),
        ("Heteroscedasticity Pass", f"{hetero_pass}/{hetero_total}", "Breusch-Pagan or White across streams", "", "good" if hetero_total and hetero_pass == hetero_total else "mixed", "H"),
    ]


def render_diagnostics(loaded: LoadedRun, controls: dict[str, Any]) -> None:
    diagnostic_df = loaded.data.get("diagnostic_df", pd.DataFrame())
    gov_kpi_grid(diagnostic_kpi_cards(diagnostic_df))
    st.markdown(
        f"<div class='run-evidence-compact diagnostics-provenance-strip'>"
        f"{html.escape(diagnostics_provenance_strip(loaded))}</div>",
        unsafe_allow_html=True,
    )

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
        )
    with bottom[1]:
        chart_card(
            "4. Error Distribution by Horizon",
            "Absolute percentage error (%) by forecast horizon.",
            compact_figure(plot_error_distribution(error_distribution), 260),
        )

    with st.expander("Diagnostics governance notes", expanded=False):
        info_panel(diagnostics_provenance_note(loaded))
        info_panel(
            "Diagnostics use Parquet fields where present and diagnostic audit tables as secondary evidence. "
            "Missing residual-test files are shown as governed unavailable states rather than fabricated points."
        )

    with st.expander("Model Explainability / Reproducibility", expanded=False):
        stream_options = reproducibility_stream_labels()
        default_stream = "Light RUC volume" if "Light RUC volume" in stream_options else stream_options[0]
        selected_repro_stream = st.selectbox(
            "Reproducibility stream",
            options=stream_options,
            index=stream_options.index(default_stream),
            key="reproducibility_stream_selector",
        )
        if st.toggle("Load reproducibility detail", value=False, key="lazy_reproducibility_detail"):
            render_reproducibility_detail(str(selected_repro_stream))
        else:
            info_panel(
                "Stream-specific reproducibility evidence is lazy-loaded from auxiliary read-only packs. "
                "These packs do not feed KPI, finalist, scenario, stress, diagnostic or score-basis calculations."
            )

    with st.expander("Model Inventory module", expanded=False):
        if st.toggle("Load Model Inventory module", value=False, key="lazy_diagnostics_inventory"):
            render_model_inventory(loaded, controls)
        else:
            info_panel("Model Inventory is lazy-loaded to keep Diagnostics tab switches fast. Open it when candidate-level detail is needed.")
    with st.expander("Run Audit module", expanded=False):
        if st.toggle("Load Run Audit module", value=False, key="lazy_diagnostics_audit"):
            render_run_audit(loaded)
        else:
            info_panel("Run Audit is lazy-loaded to avoid rebuilding file, feature and error tables during ordinary diagnostics review.")


def diagnostics_provenance_note(loaded: LoadedRun) -> str:
    qpred_rows = len(loaded.data.get("quarterly_predictions", pd.DataFrame()))
    feature_rows = len(loaded.data.get("variant_features", pd.DataFrame()))
    return (
        "Diagnostics provenance: this run provides "
        f"{format_count(qpred_rows)} forecast residual rows and {format_count(feature_rows)} feature-count rows. "
        "Classical ADF, Durbin-Watson and Breusch-Pagan files are not supplied, so proxy panels are labelled as equivalents."
    )


def diagnostics_provenance_strip(loaded: LoadedRun) -> str:
    """Return a compact first-viewport provenance line for Diagnostics."""
    qpred_rows = len(loaded.data.get("quarterly_predictions", pd.DataFrame()))
    feature_rows = len(loaded.data.get("variant_features", pd.DataFrame()))
    return (
        f"Diagnostics evidence: {format_count(qpred_rows)} residual rows | "
        f"{format_count(feature_rows)} feature-count rows | proxy panels shown where classical test files are absent."
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
        "Base log prediction",
        "Residual log prediction",
        "Final prediction",
    ]
    component_view = component_trace[[col for col in component_cols if col in component_trace.columns]]
    display_table(component_view, height=320, max_rows=240)

    chart_cols = st.columns(2)
    with chart_cols[0]:
        section_title("Feature importance")
        st.plotly_chart(
            plot_reproducibility_feature_importance(reproducibility_feature_importance_view(pack), stream_label),
            width="stretch",
            key=f"{_widget_key(stream_label)}_repro_feature_importance",
        )
    with chart_cols[1]:
        section_title("Scenario sensitivities")
        info_panel("Scenario sensitivities cover GDP, diesel price, RUC price and other perturbations.")
        st.plotly_chart(
            plot_reproducibility_sensitivities(reproducibility_sensitivity_view(pack), stream_label),
            width="stretch",
            key=f"{_widget_key(stream_label)}_repro_scenario_sensitivities",
        )

    with st.expander("OLS coefficients by origin/window", expanded=False):
        display_table(reproducibility_coefficients_view(pack), height=420, max_rows=420)

    with st.expander("Rolling training window trace", expanded=False):
        display_table(reproducibility_training_window_view(pack), height=320, max_rows=200)


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
    recommended = common_filter(score_basis_projected(loaded.data.get("recommended", pd.DataFrame()), controls), controls, include_source_variant=False)
    summary = common_filter(score_basis_projected(loaded.data.get("summary", pd.DataFrame()), controls), controls)
    paired = common_filter(loaded.data.get("paired_vs_schiff", pd.DataFrame()), controls, include_source_variant=False)
    qpred = common_filter(loaded.data.get("quarterly_predictions", pd.DataFrame()), controls, include_source_variant=False)

    st.session_state.setdefault("scenario_a_choice", "Refined Finalist Ensemble")
    st.session_state.setdefault("scenario_b_choice", SCHIFF_SPEC_BENCHMARK_LABEL)
    st.session_state.setdefault("scenario_baseline_choice", "Baseline FY25")
    scenario_a = str(st.session_state["scenario_a_choice"])
    scenario_b = str(st.session_state["scenario_b_choice"])
    baseline = str(st.session_state["scenario_baseline_choice"])

    with st.container(border=True):
        scenario_cols = st.columns([1, 0.08])
        with scenario_cols[0]:
            filter_summary_grid(
                [
                    ("Scenario A", scenario_a),
                    ("Scenario B", scenario_b),
                    ("Baseline", baseline),
                ]
            )
        with scenario_cols[1]:
            with st.popover("Edit", use_container_width=True):
                scenario_a = st.selectbox("Scenario A", ["Refined Finalist Ensemble", "Best finalist by stream"], key="scenario_a_choice")
                scenario_b = st.selectbox("Scenario B", [SCHIFF_SPEC_BENCHMARK_LABEL, "Best Schiff specification by stream"], key="scenario_b_choice")
                baseline = st.selectbox("Scenario baseline", ["Baseline FY25", "Latest loaded run"], key="scenario_baseline_choice")

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

    with st.expander("Detailed scenario governance cards", expanded=False):
        governance_cards(story)
        info_panel(
            "Decision Lens: choose the refined finalist when it improves full-sample MAPE, keeps a paired win-rate edge, stays robust across horizon "
            "buckets, and has manageable run warnings. Prefer the Schiff specification benchmark where structural interpretability dominates "
            "or the finalist does not cleanly beat the benchmark."
        )

    with st.expander("Forecast and stress drilldown", expanded=False):
        if st.toggle("Load forecast and stress drilldown", value=False, key="lazy_scenario_forecast_stress"):
            render_forecasts_and_errors(loaded, controls)
            render_stress_checks(loaded, controls)
        else:
            info_panel("Forecast and stress drilldowns are lazy-loaded so Scenario Comparison renders the management view first.")


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
    chart_card(
        "4. Decision Summary",
        subtitle,
        compact_figure(plot_decision_summary_table(display), 240),
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
        f"Forecast and stress drilldown below keeps full forecast-error tails across {format_count(qpred_rows)} "
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
        chart_card(
            "4. Benchmark Summary",
            summary_subtitle,
            compact_figure(plot_benchmark_summary_table(comparison), 260),
        )

    with st.expander("Candidate and ensemble evidence drilldown", expanded=False):
        if st.toggle("Load candidate and ensemble evidence", value=False, key="lazy_schiff_candidate_ensemble"):
            render_candidate_landscape(loaded, controls)
            render_ensemble_composition(loaded, controls)
        else:
            info_panel("Candidate and ensemble evidence is lazy-loaded to keep the Schiff Benchmark page focused and responsive.")


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

    st.plotly_chart(plot_finalist_accuracy(recommended), width="stretch")

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
    st.plotly_chart(plot_candidate_landscape(summary), width="stretch")
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
        st.plotly_chart(plot_paired_improvement(paired, top_n=controls["top_n"]), width="stretch")
        st.plotly_chart(plot_paired_scatter(paired), width="stretch")

        best = paired.sort_values("mape_improvement_pct_points", ascending=False).groupby("stream_label", as_index=False).head(1)
        if not best.empty:
            section_title("Stream-Level Best Challenger")
            st.plotly_chart(plot_paired_improvement(best, top_n=len(best)), width="stretch")

    st.plotly_chart(plot_schiff_benchmark(summary), width="stretch")


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
    st.plotly_chart(fig, width="stretch")
    if not mapping.empty:
        with st.expander("Component label mapping", expanded=False):
            display_table(mapping, height=360)
        if has_origin_weight_history(plot_data):
            st.plotly_chart(plot_weight_over_time(plot_data, mapping), width="stretch")
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
    st.plotly_chart(plot_actual_vs_predicted(detail), width="stretch")
    st.plotly_chart(plot_percent_error_over_time(detail), width="stretch")

    best_keys = model_key_set(best_by_stream(recommended)) if not recommended.empty else set()
    box_data = qpred
    if best_keys:
        box_data = filter_to_model_keys(box_data, best_keys)
    st.plotly_chart(plot_error_distribution(box_data), width="stretch")
    st.plotly_chart(plot_horizon_mape(box_data), width="stretch")


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
    st.plotly_chart(plot_stress_checks(stress_frame), width="stretch")
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
        st.plotly_chart(plot_inventory_family_performance(summary, sort_metric), width="stretch")
    with chart_cols[1]:
        st.plotly_chart(plot_schiff_class_mix(summary), width="stretch")

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
    st.plotly_chart(plot_feature_counts(variant_features), width="stretch")

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
        st.plotly_chart(plot_error_types(classify_error_rows(errors)), width="stretch")
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

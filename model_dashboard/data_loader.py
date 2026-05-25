from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .chart_sources import write_chart_source_tables
from .data.config import (
    DEFAULT_DIAGNOSTIC_AUDIT_ROOT,
    DEFAULT_DIAGNOSTIC_DATA_ROOT,
    DEFAULT_INFORMATION_PACK_ROOT,
    DashboardData,
    PARQUET_CANDIDATE_FILE,
    PARQUET_METADATA_FILE,
    PARQUET_CSV_MIRROR_FILE,
)
from .data.legacy_loader import legacy_review_warning
from .data.locate import candidate_search_roots as governed_candidate_search_roots
from .data.locate import locate_dashboard_file as governed_locate_dashboard_file
from .data.manifest import build_data_source_manifest, write_data_source_manifest
from .labels import IGNORED_RUN_FOLDER_NAMES, STRESS_BUCKET_ORDER, humanize_label, schiff_class, stream_label
from .metrics import (
    add_stream_fields,
    best_by_stream,
    coerce_numeric,
    derive_paired_from_summary,
    normalise_paired,
    normalise_predictions,
    normalise_recommended,
    normalise_stress,
    normalise_summary,
    normalise_weights,
    period_key,
    percent_unit_warnings,
    scale_percent_columns,
)
from .schema import FILE_ALIASES, SHEET_HINTS, WORKBOOK_ALIASES, WORKBOOK_DATASETS


LoadedRun = DashboardData

CORE_PARQUET_COLUMNS = [
    "stream",
    "stream_label",
    "model",
    "model_short",
    "source_run",
    "source_file",
    "source_family",
    "model_kind",
    "feature_set",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "annual_p90_ape",
    "mape_h01",
    "mape_h02",
    "mape_h03",
    "mape_h04",
    "mape_h05",
    "mape_h06",
    "mape_h07",
    "mape_h08",
    "mape_h09",
    "mape_h10",
    "mape_h11",
    "mape_h12",
    "mape_h01_04",
    "mape_h05_08",
    "mape_h09_12",
    "stress_1_4_qtrs_mape",
    "stress_5_8_qtrs_mape",
    "stress_9_12_qtrs_mape",
    "performance_rank",
    "performance_percentile",
    "performance_decile",
    "selection_score",
    "candidate_role",
    "include_reason",
    "is_current_recommended",
    "is_pure_schiff",
    "is_pdf_reference",
    "is_frontier",
    "is_top_quarterly",
    "is_top_annual",
    "is_distribution_sample",
    "is_extreme_outlier",
    "plot_default_include",
    "paired_gain_vs_schiff_pp",
    "paired_win_rate",
    "paired_common_pairs",
    "stress_2024_plus_mape",
    "stress_2022_23_mape",
    "stress_annual_mape",
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

COLUMN_ALIASES = {
    "source_run": ["source_run", "run_source", "run_id"],
    "performance_rank": ["performance_rank", "performance_rank_within_stream"],
    "is_current_recommended": ["is_current_recommended", "is_recommended_finalist", "current_recommended"],
    "is_frontier": ["is_frontier", "is_pareto_frontier", "pareto_frontier"],
    "is_distribution_sample": ["is_distribution_sample", "is_curated_cone_sample", "distribution_sample"],
    "paired_gain_vs_schiff_pp": [
        "paired_gain_vs_schiff_pp",
        "paired_improvement_pp",
        "mape_improvement_pp",
        "mape_improvement_pct_points",
    ],
    "paired_win_rate": ["paired_win_rate", "paired_win_rate_pct", "our_win_rate_pct", "challenger_win_rate"],
    "paired_common_pairs": ["paired_common_pairs", "n_common_pairs"],
    "stress_1_4_qtrs_mape": ["stress_1_4_qtrs_mape", "mape_h01_04", "h1_4_mape"],
    "stress_5_8_qtrs_mape": ["stress_5_8_qtrs_mape", "mape_h05_08", "h5_8_mape"],
    "stress_9_12_qtrs_mape": ["stress_9_12_qtrs_mape", "mape_h09_12", "h9_12_mape"],
    "stress_2024_plus_mape": ["stress_2024_plus_mape", "stress_2024plus_mape", "recent_2024_plus_mape"],
    "stress_2022_23_mape": ["stress_2022_23_mape", "policy_2022_23_mape"],
    "stress_annual_mape": ["stress_annual_mape", "annual_mape", "annual_mape_filled"],
    "durbin_watson": ["durbin_watson", "dw", "diag_durbin_watson"],
    "adj_r2": ["adj_r2", "adjusted_r2", "mz_r2", "diag_mz_r2"],
    "adf_pvalue": ["adf_pvalue", "adf_p_resid", "diag_adf_p_resid"],
    "kpss_pvalue": ["kpss_pvalue", "kpss_p_resid", "diag_kpss_p_resid"],
    "breusch_pagan_pvalue": ["breusch_pagan_pvalue", "breusch_pagan_p", "diag_breusch_pagan_p"],
    "white_pvalue": ["white_pvalue", "white_p", "diag_white_p"],
    "arch_lm_pvalue": ["arch_lm_pvalue", "arch_lm_p", "diag_arch_lm_p"],
    "jarque_bera_pvalue": ["jarque_bera_pvalue", "jarque_bera_p", "diag_jarque_bera_p"],
    "skewness": ["skewness", "skew_resid", "diag_skew_resid"],
    "kurtosis": ["kurtosis", "kurtosis_resid", "diag_kurtosis_resid"],
    "cointegration_pvalue": ["cointegration_pvalue", "coint_p_actual_pred", "diag_coint_p_actual_pred"],
}

STRESS_BUCKET_SOURCES = [
    ("1-4 qtrs", ["stress_1_4_qtrs_mape", "mape_h01_04", "h1_4_mape"]),
    ("5-8 qtrs", ["stress_5_8_qtrs_mape", "mape_h05_08", "h5_8_mape"]),
    ("9-12 qtrs", ["stress_9_12_qtrs_mape", "mape_h09_12", "h9_12_mape"]),
    ("2024+", ["stress_2024plus_mape", "recent_2024_plus_mape", "stress_2024_plus_mape"]),
    ("2022-23", ["stress_2022_23_mape", "policy_2022_23_mape"]),
    ("Annual", ["stress_annual_mape", "annual_mape", "annual_mape_filled"]),
]

STALE_FINALIST_VALUES = {
    "PED": 5.49,
    "LIGHT_RUC": 11.55,
    "HEAVY_RUC": 12.38,
}

CURATED_FILE_MAP = {
    "finalist_accuracy": "finalist_accuracy.csv",
    "candidate_landscape": "candidate_landscape_sample.csv",
    "schiff_benchmark": "schiff_benchmark.csv",
    "pdf_comparison": "pdf_comparison.csv",
    "stress_horizon": "stress_horizon.csv",
    "ensemble_composition": "ensemble_composition.csv",
    "paired_vs_schiff_selected": "paired_vs_schiff_selected.csv",
    "annual_predictions_selected": "annual_predictions_selected.csv",
    "quarterly_predictions_selected": "quarterly_predictions_selected.csv",
}


def discover_run_folders(parent: Path, ignore_names: set[str] | None = None) -> list[Path]:
    ignored = ignore_names or IGNORED_RUN_FOLDER_NAMES
    if not parent.exists():
        return []
    candidates: list[Path] = []
    if parent.is_dir() and parent.name.startswith("run_"):
        candidates.append(parent)
    candidates.extend(path for path in parent.rglob("run_*") if path.is_dir())
    unique = sorted(set(candidates), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return [path for path in unique if path.name not in ignored and run_has_outputs(path)]


def run_has_outputs(run_dir: Path) -> bool:
    if not run_dir.exists() or not run_dir.is_dir():
        return False
    names = {name.lower() for aliases in FILE_ALIASES.values() for name in aliases}
    for child in run_dir.iterdir():
        if child.is_file() and child.name.lower() in names and child.stat().st_size > 0:
            return True
    return False


def run_signature(run_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not run_dir.exists() or not run_dir.is_dir():
        return tuple()
    rows = []
    for child in sorted(run_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.is_file():
            stat = child.stat()
            rows.append((child.name, stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def curated_signature(curated_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not curated_dir.exists() or not curated_dir.is_dir():
        return tuple()
    rows = []
    for child in sorted(curated_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.is_file():
            stat = child.stat()
            rows.append((child.name, stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def parquet_pack_signature(data_root: str | Path, repo_root: str | Path | None = None) -> tuple[tuple[str, int, int], ...]:
    roots = _candidate_search_roots(data_root, repo_root)
    rows: list[tuple[str, int, int]] = []
    for filename in [
        PARQUET_CANDIDATE_FILE,
        PARQUET_METADATA_FILE,
        "model_diagnostic_audit_tables.xlsx",
        "model_diagnostic_audit_report.md",
        "diagnostic_pass_matrix.csv",
        "h1_residual_diagnostics_our_vs_schiff.csv",
        "model_summary_our_vs_schiff.csv",
        "paired_common_forecast_pairs_our_vs_schiff.csv",
    ]:
        found = locate_dashboard_file(filename, roots)
        if found is None:
            continue
        stat = found.stat()
        rows.append((str(found), stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def _candidate_search_roots(data_root: str | Path, repo_root: str | Path | None = None) -> list[Path]:
    return governed_candidate_search_roots(data_root, repo_root)


def locate_dashboard_file(filename: str, roots: list[Path] | tuple[Path, ...]) -> Path | None:
    return governed_locate_dashboard_file(filename, roots)


def curated_manifest_matches(curated_dir: Path, run_dir: str | Path) -> bool:
    manifest_path = curated_dir / "curation_manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    manifest_run = Path(str(manifest.get("run_dir", ""))).expanduser()
    return manifest_run == Path(run_dir).expanduser()


def load_parquet_dashboard(
    data_root: str | Path,
    repo_root: str | Path | None = None,
    *,
    allow_csv_preview: bool = False,
) -> LoadedRun:
    roots = _candidate_search_roots(data_root, repo_root)
    warnings: list[str] = []
    parquet_path = locate_dashboard_file(PARQUET_CANDIDATE_FILE, roots)
    metadata_path = locate_dashboard_file(PARQUET_METADATA_FILE, roots)
    csv_mirror_path = locate_dashboard_file(PARQUET_CSV_MIRROR_FILE, roots)
    diagnostic_paths = {
        filename: path
        for filename in [
            "model_diagnostic_audit_tables.xlsx",
            "model_diagnostic_audit_report.md",
            "diagnostic_pass_matrix.csv",
            "h1_residual_diagnostics_our_vs_schiff.csv",
            "model_summary_our_vs_schiff.csv",
            "paired_common_forecast_pairs_our_vs_schiff.csv",
        ]
        if (path := locate_dashboard_file(filename, roots)) is not None
    }
    repo_path = Path(repo_root).expanduser() if repo_root is not None else Path.cwd()
    if parquet_path is None:
        message = (
            f"{PARQUET_CANDIDATE_FILE} was not found under "
            + "; ".join(str(root) for root in roots)
            + "."
        )
        if not allow_csv_preview:
            raise FileNotFoundError(message)
        warnings.append(message + " Using repository CSV artifacts as a degraded preview only.")
        raw_candidate = _load_csv_preview_candidate(repo_path)
        source_path = repo_path / "artifacts" / "curated_data" / "candidate_landscape_sample.csv"
    else:
        raw_candidate = pd.read_parquet(parquet_path)
        source_path = parquet_path

    source_manifest = build_data_source_manifest(
        requested_data_root=data_root,
        search_roots=roots,
        parquet_path=parquet_path,
        metadata_path=metadata_path,
        csv_mirror_path=csv_mirror_path,
        diagnostic_paths=diagnostic_paths,
        source_mode="parquet" if parquet_path is not None else "legacy_csv_preview",
    )
    write_data_source_manifest(repo_path, source_manifest)
    metadata = _read_json_file(metadata_path) if metadata_path else {}
    candidate = normalise_parquet_candidate(raw_candidate)
    data, status_rows, build_warnings = _build_dashboard_frames(candidate, roots, repo_path, metadata, source_path)
    warnings.extend(build_warnings)
    status = pd.DataFrame(status_rows)
    return LoadedRun(source_path.parent, data, status, tuple(warnings), source_manifest)


def _load_csv_preview_candidate(repo_root: Path) -> pd.DataFrame:
    path = repo_root / "artifacts" / "curated_data" / "candidate_landscape_sample.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def normalise_parquet_candidate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    for canonical, aliases in COLUMN_ALIASES.items():
        values = out[canonical] if canonical in out.columns else pd.Series(pd.NA, index=out.index)
        for alias in aliases:
            existing = first_existing_column(out, [alias])
            if existing is not None:
                values = values.combine_first(out[existing])
        out[canonical] = values
    for column in CORE_PARQUET_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    if "stream_label" in out.columns:
        out["stream_label"] = out["stream_label"].where(out["stream_label"].notna(), out["stream"].map(stream_label))
    if "model_short" in out.columns:
        out["model_short"] = out["model_short"].where(out["model_short"].notna(), out["model"].map(humanize_label))
    bool_columns = [
        "is_current_recommended",
        "is_pure_schiff",
        "is_pdf_reference",
        "is_frontier",
        "is_top_quarterly",
        "is_top_annual",
        "is_distribution_sample",
        "is_extreme_outlier",
        "plot_default_include",
    ]
    for column in bool_columns:
        out[column] = out[column].map(_coerce_bool).fillna(False).astype(bool)
    if not out["plot_default_include"].any():
        out["plot_default_include"] = (
            out["is_current_recommended"]
            | out["is_pure_schiff"]
            | out["is_pdf_reference"]
            | out["is_frontier"]
            | out["is_distribution_sample"]
            | out["is_top_quarterly"]
            | out["is_top_annual"]
        )
    if "candidate_role" in out.columns:
        out["candidate_role"] = out["candidate_role"].fillna("Candidate")
    for column in ["stream_label", "model_short", "source_family", "model_kind", "feature_set", "candidate_role", "include_reason"]:
        if column in out.columns:
            out[column] = out[column].map(humanize_label)
    numeric_columns = [
        column
        for column in CORE_PARQUET_COLUMNS
        if column
        not in {
            "stream",
            "stream_label",
            "model",
            "model_short",
            "source_run",
            "source_file",
            "source_family",
            "model_kind",
            "feature_set",
            "candidate_role",
            "include_reason",
        }
        and not column.startswith("is_")
        and column != "plot_default_include"
    ]
    out = coerce_numeric(out, numeric_columns)
    out = scale_percent_columns(out)
    out = add_stream_fields(out)
    out["is_recommended_finalist"] = out["is_current_recommended"]
    out["is_finalist"] = out["is_current_recommended"]
    out["is_schiff"] = out["is_pure_schiff"]
    out["stage"] = "final"
    out["variant"] = out["feature_set"].fillna("curated").map(humanize_label)
    out["schiff_class"] = out.apply(
        lambda row: "Pure Schiff benchmark"
        if bool(row.get("is_pure_schiff"))
        else schiff_class(row.get("model"), row.get("source_family"), row.get("feature_set")),
        axis=1,
    )
    return out


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        hit = lower.get(candidate.lower())
        if hit is not None:
            return hit
    return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "current"}


def _read_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_dashboard_frames(
    candidate: pd.DataFrame,
    roots: list[Path],
    repo_root: Path,
    metadata: dict[str, Any],
    source_path: Path,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    status_rows = [_status_row("parquet candidate cone", source_path, len(candidate), len(candidate.columns))]
    if candidate.empty:
        warnings.append("Candidate Parquet data is empty.")

    recommended, finalist_warnings = _select_current_finalists(candidate)
    warnings.extend(finalist_warnings)
    schiff = _pure_schiff_rows(candidate)
    pdf_reference = candidate[candidate["is_pdf_reference"]].copy() if "is_pdf_reference" in candidate.columns else pd.DataFrame()
    frontier = candidate[candidate["is_frontier"]].copy() if "is_frontier" in candidate.columns else pd.DataFrame()
    distribution = candidate[candidate["is_distribution_sample"]].copy() if "is_distribution_sample" in candidate.columns else pd.DataFrame()
    default_candidate = candidate[candidate["plot_default_include"]].copy() if "plot_default_include" in candidate.columns else candidate.copy()
    if "is_extreme_outlier" in default_candidate.columns:
        default_candidate = default_candidate[~default_candidate["is_extreme_outlier"].fillna(False).astype(bool)].copy()

    audit_tables, audit_status, audit_warnings = _load_diagnostic_audit_tables(roots)
    status_rows.extend(audit_status)
    warnings.extend(audit_warnings)
    diagnostic = _diagnostic_frame(candidate, audit_tables)
    paired = _paired_frame(recommended, schiff, audit_tables)
    stress = _stress_frame(recommended)
    horizon = _horizon_frame(pd.concat([recommended, schiff], ignore_index=True))
    weights = _ensemble_frame(candidate, repo_root)
    quarterly_predictions = _load_optional_pack_csv(roots, "quarterly_predictions_selected.csv")
    annual_predictions = _load_optional_pack_csv(roots, "annual_predictions_selected.csv")
    if not quarterly_predictions.empty:
        quarterly_predictions = normalise_predictions(quarterly_predictions, annual=False)
    if not annual_predictions.empty:
        annual_predictions = normalise_predictions(annual_predictions, annual=True)
    curated_manifest = pd.DataFrame(
        [
            {
                "created_at": metadata.get("created_at") or metadata.get("generated_at"),
                "source": "Parquet candidate cone" if source_path.name == PARQUET_CANDIDATE_FILE else "CSV preview",
                "parquet_path": str(source_path) if source_path.name == PARQUET_CANDIDATE_FILE else "",
                "metadata_path": str(locate_dashboard_file(PARQUET_METADATA_FILE, roots) or ""),
                "row_counts": {"candidate_rows": len(candidate), "default_candidate_rows": len(default_candidate)},
            }
        ]
    )

    data = {
        "candidate_df": candidate,
        "finalists_df": recommended,
        "schiff_df": schiff,
        "pdf_reference_df": pdf_reference,
        "frontier_df": frontier,
        "distribution_df": distribution,
        "stress_df": stress,
        "horizon_df": horizon,
        "diagnostic_df": diagnostic,
        "ensemble_df": weights,
        "paired_df": paired,
        "recommended": recommended,
        "summary": default_candidate,
        "quarterly_predictions": quarterly_predictions,
        "annual_predictions": annual_predictions,
        "quarterly_summary": pd.DataFrame(),
        "annual_summary": pd.DataFrame(),
        "paired_vs_schiff": paired,
        "stress": stress,
        "weights": weights,
        "features": pd.DataFrame(),
        "variant_features": pd.DataFrame(),
        "leaderboards": pd.DataFrame(),
        "errors": pd.DataFrame(),
        "schiff_benchmark": schiff,
        "pdf_comparison": pdf_reference,
        "curated_manifest": curated_manifest,
        "audit_tables": audit_tables,
    }
    _write_reconciliation_source_tables(repo_root, data)
    return data, status_rows, warnings


def _select_current_finalists(candidate: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    if candidate.empty or "is_current_recommended" not in candidate.columns:
        return pd.DataFrame(), ["No current finalist flag is available in the candidate data."]
    data = candidate[candidate["is_current_recommended"]].copy()
    if data.empty:
        return pd.DataFrame(), ["No rows are flagged as current recommended finalists."]
    chosen_rows = []
    for stream, group in data.groupby("stream", dropna=False):
        ranked = group.copy()
        sort_cols = [col for col in ["current_recommended_rank", "selection_score", "performance_rank"] if col in ranked.columns]
        if len(ranked) > 1:
            warnings.append(
                f"Multiple current recommended finalists found for {stream}; selected the best available rank and kept the ambiguity in the data audit."
            )
        if sort_cols:
            ranked = ranked.sort_values(sort_cols, ascending=True, na_position="last")
        chosen_rows.append(ranked.iloc[[0]])
    finalists = pd.concat(chosen_rows, ignore_index=True) if chosen_rows else pd.DataFrame()
    finalists["is_finalist"] = True
    finalists["is_recommended_finalist"] = True
    finalists["finalist_role"] = "Current recommended finalist"
    return finalists, warnings


def _pure_schiff_rows(candidate: pd.DataFrame) -> pd.DataFrame:
    if candidate.empty or "is_pure_schiff" not in candidate.columns:
        return pd.DataFrame()
    schiff = candidate[candidate["is_pure_schiff"]].copy()
    if schiff.empty:
        return schiff
    bad_pattern = r"(?i)(?:resid|residual|fixedblend|blend|solver|convex|ensemble|top|median|mean|gbm|local)"
    return schiff[~schiff["model"].astype(str).str.contains(bad_pattern, regex=True, na=False)].copy()


def _load_optional_pack_csv(roots: list[Path], filename: str) -> pd.DataFrame:
    path = locate_dashboard_file(filename, roots)
    if path is None:
        return pd.DataFrame()
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def _load_diagnostic_audit_tables(roots: list[Path]) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]], list[str]]:
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


def _diagnostic_frame(candidate: pd.DataFrame, audit_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
    return coerce_numeric(
        diag,
        [
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
        ],
    )


def _paired_frame(
    recommended: pd.DataFrame,
    schiff: pd.DataFrame,
    audit_tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    audit = audit_tables.get("paired_common_forecast_pairs_our_vs_schiff", audit_tables.get("paired_vs_schiff", pd.DataFrame()))
    if not audit.empty:
        out = audit.rename(
            columns={
                "schiff_mape_common": "baseline_mape",
                "our_mape_common": "challenger_mape",
                "mape_improvement_pp": "mape_improvement_pct_points",
                "our_win_rate_pct": "challenger_win_rate",
            }
        ).copy()
        out["baseline"] = "Pure Schiff benchmark"
        out["challenger"] = "Current finalist"
        return normalise_paired(out)
    rows: list[dict[str, Any]] = []
    for _, finalist in recommended.iterrows():
        stream = finalist.get("stream")
        schiff_rows = schiff[schiff["stream"].astype(str).eq(str(stream))] if "stream" in schiff.columns else pd.DataFrame()
        if schiff_rows.empty:
            continue
        benchmark = schiff_rows.sort_values("quarterly_mape").iloc[0]
        rows.append(
            {
                "stream": stream,
                "stream_label": finalist.get("stream_label"),
                "baseline": benchmark.get("model"),
                "challenger": finalist.get("model"),
                "n_common_pairs": finalist.get("paired_common_pairs"),
                "baseline_mape": benchmark.get("quarterly_mape"),
                "challenger_mape": finalist.get("quarterly_mape"),
                "mape_improvement_pct_points": float(benchmark.get("quarterly_mape", 0)) - float(finalist.get("quarterly_mape", 0)),
                "challenger_win_rate": finalist.get("paired_win_rate"),
            }
        )
    return normalise_paired(pd.DataFrame(rows))


def _stress_frame(finalists: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in finalists.iterrows():
        for bucket, columns in STRESS_BUCKET_SOURCES:
            value, source_column = _first_numeric_value(row, columns)
            rows.append(
                {
                    "stage": row.get("stage"),
                    "stream": row.get("stream"),
                    "variant": row.get("variant"),
                    "stream_label": row.get("stream_label"),
                    "model": row.get("model"),
                    "model_short": row.get("model_short"),
                    "stress_bucket": bucket,
                    "mape": value,
                    "stress_type": _stress_type_for_bucket(bucket),
                    "source_column": source_column,
                    "value_available": pd.notna(value),
                }
            )
    return normalise_stress(pd.DataFrame(rows))


def _first_numeric_value(row: pd.Series, columns: list[str]) -> tuple[float, str]:
    for column in columns:
        if column not in row.index:
            continue
        value = pd.to_numeric(row.get(column), errors="coerce")
        if pd.notna(value):
            return float(value), column
    return float("nan"), ""


def _stress_type_for_bucket(bucket: str) -> str:
    if bucket in STRESS_BUCKET_ORDER[:3]:
        return "Horizon bucket"
    if bucket == "Annual":
        return "Annual"
    return "Policy stress"


def _horizon_frame(rows_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if rows_df is None or rows_df.empty:
        return pd.DataFrame()
    for _, row in rows_df.iterrows():
        role = "Finalist" if bool(row.get("is_current_recommended", row.get("is_finalist", False))) else "Schiff"
        for horizon in range(1, 13):
            column = f"mape_h{horizon:02d}"
            value = pd.to_numeric(row.get(column), errors="coerce")
            if pd.isna(value):
                continue
            rows.append(
                {
                    "stream": row.get("stream"),
                    "stream_label": row.get("stream_label"),
                    "model": row.get("model"),
                    "model_short": row.get("model_short"),
                    "scenario": role,
                    "scenario_role": role,
                    "horizon": horizon,
                    "mape": float(value),
                }
            )
    return pd.DataFrame(rows)


def _ensemble_frame(candidate: pd.DataFrame, repo_root: Path) -> pd.DataFrame:
    del repo_root
    if candidate.empty or "ensemble_components_json" not in candidate.columns:
        return pd.DataFrame()
    current = candidate[
        candidate.get("is_current_recommended", pd.Series(False, index=candidate.index)).fillna(False).astype(bool)
    ].copy()
    rows: list[dict[str, Any]] = []
    for _, finalist in current.iterrows():
        components = _parse_ensemble_components(finalist.get("ensemble_components_json"))
        if not components:
            continue
        for rank, component in enumerate(components, start=1):
            weight = pd.to_numeric(component.get("weight"), errors="coerce")
            rows.append(
                {
                    "stream": finalist.get("stream"),
                    "stream_label": finalist.get("stream_label"),
                    "ensemble": finalist.get("model"),
                    "ensemble_short": finalist.get("model_short"),
                    "model_short": finalist.get("model_short"),
                    "component_rank": rank,
                    "component_model": component.get("component_model"),
                    "component_short": component.get("component_short") or humanize_label(component.get("component_model")),
                    "weight": float(weight) if pd.notna(weight) else pd.NA,
                    "method": "Parquet ensemble_components_json",
                    "source": "Parquet ensemble_components_json",
                    "role": "Current recommended finalist component",
                }
            )
    return normalise_weights(pd.DataFrame(rows))


def _parse_ensemble_components(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if value is None or pd.isna(value):
        return []
    try:
        decoded = json.loads(str(value))
    except Exception:
        return []
    return [item for item in decoded if isinstance(item, dict)] if isinstance(decoded, list) else []


def build_ensemble_composition_source_table(weights: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stream_label",
        "model_short",
        "component_rank",
        "component_short",
        "component_model",
        "weight",
        "weight_pct",
        "source",
    ]
    if weights is None or weights.empty:
        return pd.DataFrame(columns=columns)
    out = weights.copy()
    out["weight"] = pd.to_numeric(out.get("weight"), errors="coerce")
    out["weight_pct"] = out["weight"] * 100.0
    if "component_rank" not in out.columns:
        out = out.sort_values(["stream_label", "weight"], ascending=[True, False])
        out["component_rank"] = out.groupby("stream_label", dropna=False).cumcount() + 1
    if "model_short" not in out.columns:
        out["model_short"] = out.get("ensemble_short", pd.Series("", index=out.index))
    if "source" not in out.columns:
        out["source"] = "Parquet ensemble_components_json"
    return out.reindex(columns=columns).sort_values(["stream_label", "component_rank"]).reset_index(drop=True)


def build_scenario_comparison_source_table(
    recommended: pd.DataFrame,
    schiff_rows: pd.DataFrame,
    paired: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "stream_label",
        "scenario_a_model",
        "scenario_b_model",
        "scenario_a_quarterly_mape",
        "scenario_b_quarterly_mape",
        "scenario_a_annual_mape",
        "scenario_b_annual_mape",
        "full_sample_qtr_gain_pp",
        "full_sample_annual_gain_pp",
        "paired_common_pairs",
        "paired_model_mape",
        "paired_schiff_mape",
        "paired_gain_pp",
        "paired_win_rate_pct",
        "recommendation",
    ]
    finalists = best_by_stream(recommended)
    if schiff_rows is None or schiff_rows.empty:
        return pd.DataFrame(columns=columns)
    schiff = best_by_stream(schiff_rows[schiff_rows["is_schiff"]]) if "is_schiff" in schiff_rows.columns else best_by_stream(schiff_rows)
    if finalists.empty or schiff.empty:
        return pd.DataFrame(columns=columns)
    paired_by_stream = paired.set_index("stream_label") if paired is not None and not paired.empty and "stream_label" in paired.columns else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, finalist in finalists.iterrows():
        stream = finalist.get("stream")
        stream_schiff = schiff[schiff["stream"].astype(str).eq(str(stream))] if "stream" in schiff.columns else pd.DataFrame()
        if stream_schiff.empty:
            continue
        benchmark = stream_schiff.iloc[0]
        paired_row = paired_by_stream.loc[finalist.get("stream_label")] if not paired_by_stream.empty and finalist.get("stream_label") in paired_by_stream.index else {}
        if isinstance(paired_row, pd.DataFrame):
            paired_row = paired_row.iloc[0]
        fq = pd.to_numeric(finalist.get("quarterly_mape"), errors="coerce")
        fa = pd.to_numeric(finalist.get("annual_mape"), errors="coerce")
        sq = pd.to_numeric(benchmark.get("quarterly_mape"), errors="coerce")
        sa = pd.to_numeric(benchmark.get("annual_mape"), errors="coerce")
        q_gain = sq - fq if pd.notna(sq) and pd.notna(fq) else pd.NA
        a_gain = sa - fa if pd.notna(sa) and pd.notna(fa) else pd.NA
        paired_gain = pd.to_numeric(getattr(paired_row, "get", lambda _key, _default=None: _default)("mape_improvement_pct_points"), errors="coerce")
        win_rate = pd.to_numeric(getattr(paired_row, "get", lambda _key, _default=None: _default)("challenger_win_rate"), errors="coerce")
        recommendation = "Promote" if pd.notna(q_gain) and q_gain > 0 and pd.notna(a_gain) and a_gain > 0 and (pd.isna(win_rate) or win_rate >= 55) else "Needs Stage 2"
        rows.append(
            {
                "stream_label": finalist.get("stream_label"),
                "scenario_a_model": finalist.get("model"),
                "scenario_b_model": benchmark.get("model"),
                "scenario_a_quarterly_mape": fq,
                "scenario_b_quarterly_mape": sq,
                "scenario_a_annual_mape": fa,
                "scenario_b_annual_mape": sa,
                "full_sample_qtr_gain_pp": q_gain,
                "full_sample_annual_gain_pp": a_gain,
                "paired_common_pairs": getattr(paired_row, "get", lambda _key, _default=None: _default)("n_common_pairs"),
                "paired_model_mape": getattr(paired_row, "get", lambda _key, _default=None: _default)("challenger_mape"),
                "paired_schiff_mape": getattr(paired_row, "get", lambda _key, _default=None: _default)("baseline_mape"),
                "paired_gain_pp": paired_gain,
                "paired_win_rate_pct": win_rate,
                "recommendation": recommendation,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_horizon_comparison_source_table(
    horizon: pd.DataFrame,
    qpred: pd.DataFrame,
    recommended: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["page", "stream_label", "scenario", "horizon", "mape", "source_column", "source"]
    rows: list[dict[str, Any]] = []
    required_streams = set(recommended.get("stream_label", pd.Series(dtype=str)).dropna().astype(str)) if recommended is not None and not recommended.empty else set()
    existing_streams: set[str] = set()
    if horizon is not None and not horizon.empty:
        existing_streams = set(horizon.get("stream_label", pd.Series(dtype=str)).dropna().astype(str))
        for _, row in horizon.iterrows():
            for page in ["Scenario Comparison", "Schiff Benchmark"]:
                rows.append(
                    {
                        "page": page,
                        "stream_label": row.get("stream_label"),
                        "scenario": row.get("scenario_role", row.get("scenario")),
                        "horizon": row.get("horizon"),
                        "mape": row.get("mape"),
                        "source_column": f"mape_h{int(row.get('horizon')):02d}" if pd.notna(pd.to_numeric(row.get("horizon"), errors="coerce")) else "",
                        "source": "Parquet candidate horizon fields",
                    }
                )
    missing_streams = required_streams.difference(existing_streams)
    if missing_streams and qpred is not None and not qpred.empty and {"selected_role", "horizon", "ape", "stream_label"}.issubset(qpred.columns):
        data = qpred.copy()
        data["scenario_role"] = data["selected_role"].map(lambda value: "Schiff" if "schiff" in str(value).lower() else "Finalist")
        grouped = data.groupby(["stream_label", "scenario_role", "horizon"], dropna=False)["ape"].mean().reset_index(name="mape")
        grouped = grouped[grouped["stream_label"].astype(str).isin(missing_streams) & grouped["horizon"].between(1, 12)]
        for _, row in grouped.iterrows():
            for page in ["Scenario Comparison", "Schiff Benchmark"]:
                rows.append(
                    {
                        "page": page,
                        "stream_label": row.get("stream_label"),
                        "scenario": row.get("scenario_role"),
                        "horizon": row.get("horizon"),
                        "mape": row.get("mape"),
                        "source_column": "ape",
                        "source": "quarterly_predictions_selected.csv grouped mean APE",
                    }
                )
    return pd.DataFrame(rows, columns=columns)


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


def _write_reconciliation_source_tables(repo_root: Path, data: dict[str, pd.DataFrame]) -> None:
    artifacts = repo_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    source_tables = {
        "ensemble_composition_source_table.csv": build_ensemble_composition_source_table(data.get("weights", pd.DataFrame())),
        "scenario_comparison_source_table.csv": build_scenario_comparison_source_table(
            data.get("recommended", pd.DataFrame()),
            data.get("schiff_df", data.get("summary", pd.DataFrame())),
            data.get("paired_vs_schiff", pd.DataFrame()),
        ),
        "horizon_comparison_source_table.csv": build_horizon_comparison_source_table(
            data.get("horizon_df", pd.DataFrame()),
            data.get("quarterly_predictions", pd.DataFrame()),
            data.get("recommended", pd.DataFrame()),
        ),
        "diagnostic_acf_source_table.csv": build_diagnostic_acf_source_table(data.get("quarterly_predictions", pd.DataFrame())),
    }
    for filename, frame in source_tables.items():
        frame.to_csv(artifacts / filename, index=False)
    write_chart_source_tables(repo_root, data)


def load_curated_run(
    curated_dir: str | Path,
    run_dir: str | Path,
    data_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
) -> LoadedRun:
    curated_path = Path(curated_dir).expanduser()
    run_path = Path(run_dir).expanduser()
    warnings: list[str] = [legacy_review_warning(run_path)]
    manifest = {
        "source_mode": "legacy_curated_review",
        "requested_data_root": str(Path(data_root).expanduser()) if data_root is not None else "",
        "legacy_run_dir": str(run_path),
        "curated_dir": str(curated_path),
    }
    write_data_source_manifest(artifact_root or Path.cwd(), manifest)
    if not curated_path.exists() or not curated_path.is_dir():
        warnings.append(f"Curated data directory does not exist: {curated_path}")
        return LoadedRun(run_path, {}, _empty_status_frame(), tuple(warnings), manifest)

    if not curated_manifest_matches(curated_path, run_path):
        warnings.append(f"Curated manifest does not match active run folder: {run_path}")

    raw: dict[str, pd.DataFrame] = {}
    status_rows: list[dict[str, Any]] = []
    for dataset, filename in CURATED_FILE_MAP.items():
        path = curated_path / filename
        dataframe = pd.DataFrame()
        warning = None
        if path.exists() and path.stat().st_size > 0:
            try:
                dataframe = pd.read_csv(path, low_memory=False)
            except Exception as exc:  # pragma: no cover - shown in dashboard
                warning = f"Could not read curated {filename}: {exc}"
        if warning:
            warnings.append(warning)
        raw[dataset] = dataframe
        status_rows.append(_status_row(dataset, path if path.exists() else None, len(dataframe) if path.exists() else None, len(dataframe.columns) if path.exists() else None))

    recommended = normalise_recommended(raw.get("finalist_accuracy", pd.DataFrame()))
    if not recommended.empty:
        recommended["is_finalist"] = True
        recommended["is_recommended_finalist"] = True
        recommended["stage"] = "final"
        recommended["variant"] = recommended.get("feature_set", "curated")
        for column in ["source_family", "model_kind", "feature_set", "variant"]:
            if column in recommended.columns:
                recommended[column] = recommended[column].map(humanize_label)

    summary = normalise_summary(raw.get("candidate_landscape", pd.DataFrame()), recommended)
    if not summary.empty:
        if "is_recommended_finalist" in summary.columns:
            summary["is_finalist"] = summary["is_recommended_finalist"].astype(bool)
        if "is_pure_schiff" in summary.columns:
            summary["is_schiff"] = summary["is_pure_schiff"].astype(bool)
        summary["stage"] = "final"
        summary["variant"] = summary.get("feature_set", "curated")

    quarterly = normalise_predictions(raw.get("quarterly_predictions_selected", pd.DataFrame()), annual=False)
    annual = normalise_predictions(raw.get("annual_predictions_selected", pd.DataFrame()), annual=True)
    stress = normalise_stress(raw.get("stress_horizon", pd.DataFrame()))
    weights = normalise_weights(raw.get("ensemble_composition", pd.DataFrame()))

    paired = normalise_paired(raw.get("paired_vs_schiff_selected", pd.DataFrame()))

    data = {
        "recommended": recommended,
        "summary": summary,
        "quarterly_predictions": quarterly,
        "annual_predictions": annual,
        "quarterly_summary": pd.DataFrame(),
        "annual_summary": pd.DataFrame(),
        "paired_vs_schiff": paired,
        "stress": stress,
        "weights": weights,
        "features": pd.DataFrame(),
        "variant_features": pd.DataFrame(),
        "leaderboards": pd.DataFrame(),
        "errors": pd.DataFrame(),
        "schiff_benchmark": add_stream_fields(raw.get("schiff_benchmark", pd.DataFrame())),
        "pdf_comparison": add_stream_fields(raw.get("pdf_comparison", pd.DataFrame())),
        "curated_manifest": pd.DataFrame([_load_manifest_row(curated_path)]),
    }
    status = pd.DataFrame(status_rows)
    return LoadedRun(run_path, data, status, tuple(warnings), manifest)


def _load_manifest_row(curated_dir: Path) -> dict[str, Any]:
    manifest_path = curated_dir / "curation_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    row = dict(manifest)
    row["curated_dir"] = str(curated_dir)
    return row


def load_run(
    run_dir: str | Path,
    data_root: str | Path | None = None,
    artifact_root: str | Path | None = None,
) -> LoadedRun:
    path = Path(run_dir).expanduser()
    warnings: list[str] = [legacy_review_warning(path)]
    manifest = {
        "source_mode": "legacy_run_folder_review",
        "requested_data_root": str(Path(data_root).expanduser()) if data_root is not None else "",
        "legacy_run_dir": str(path),
    }
    write_data_source_manifest(artifact_root or Path.cwd(), manifest)
    if not path.exists() or not path.is_dir():
        warnings.append(f"Run folder does not exist or is not a directory: {path}")
        return LoadedRun(path, {}, _empty_status_frame(), tuple(warnings), manifest)

    raw_data: dict[str, pd.DataFrame] = {}
    status_rows: list[dict[str, Any]] = []
    workbook_cache: dict[Path, pd.ExcelFile] = {}

    files_by_name = {child.name.lower(): child for child in path.iterdir() if child.is_file()}
    for dataset, aliases in FILE_ALIASES.items():
        if dataset not in WORKBOOK_DATASETS:
            found = _find_file(files_by_name, aliases)
            status_rows.append(_status_row(dataset, found, None, None))
            continue

        dataframe, found, warning = _read_tabular_dataset(path, files_by_name, dataset, aliases, workbook_cache)
        if warning:
            warnings.append(warning)
        raw_data[dataset] = dataframe
        status_rows.append(_status_row(dataset, found, len(dataframe) if found else None, len(dataframe.columns) if found else None))

    recommended = normalise_recommended(raw_data.get("recommended", pd.DataFrame()))
    if not recommended.empty:
        recommended["is_finalist"] = True
    summary = normalise_summary(raw_data.get("summary", pd.DataFrame()), recommended)
    if summary.empty and not recommended.empty:
        summary = recommended.copy()
    quarterly = normalise_predictions(raw_data.get("quarterly_predictions", pd.DataFrame()), annual=False)
    annual = normalise_predictions(raw_data.get("annual_predictions", pd.DataFrame()), annual=True)
    paired = normalise_paired(raw_data.get("paired_vs_schiff", pd.DataFrame()))
    if paired.empty:
        paired = derive_paired_from_summary(summary)
    data = {
        "recommended": recommended,
        "summary": summary,
        "quarterly_predictions": quarterly,
        "annual_predictions": annual,
        "quarterly_summary": normalise_summary(raw_data.get("quarterly_summary", pd.DataFrame()), recommended),
        "annual_summary": normalise_summary(raw_data.get("annual_summary", pd.DataFrame()), recommended),
        "paired_vs_schiff": paired,
        "stress": normalise_stress(raw_data.get("stress", pd.DataFrame())),
        "weights": normalise_weights(raw_data.get("weights", pd.DataFrame())),
        "features": add_stream_fields(raw_data.get("features", pd.DataFrame()))
        if not raw_data.get("features", pd.DataFrame()).empty
        else pd.DataFrame(),
        "variant_features": add_stream_fields(raw_data.get("variant_features", pd.DataFrame()))
        if not raw_data.get("variant_features", pd.DataFrame()).empty
        else pd.DataFrame(),
        "leaderboards": add_stream_fields(raw_data.get("leaderboards", pd.DataFrame()))
        if not raw_data.get("leaderboards", pd.DataFrame()).empty and "stream" in raw_data["leaderboards"].columns
        else raw_data.get("leaderboards", pd.DataFrame()),
        "errors": raw_data.get("errors", pd.DataFrame()),
    }

    for dataset, frame in data.items():
        warnings.extend(percent_unit_warnings(frame, dataset))

    status = pd.DataFrame(status_rows)
    return LoadedRun(path, data, status, tuple(warnings), manifest)


def _read_tabular_dataset(
    run_dir: Path,
    files_by_name: dict[str, Path],
    dataset: str,
    aliases: list[str],
    workbook_cache: dict[Path, pd.ExcelFile],
) -> tuple[pd.DataFrame, Path | tuple[Path, str] | None, str | None]:
    found = _find_file(files_by_name, [name for name in aliases if name.lower().endswith(".csv")])
    if found and found.stat().st_size > 0:
        try:
            return pd.read_csv(found, low_memory=False), found, None
        except Exception as exc:  # pragma: no cover - shown in dashboard
            return pd.DataFrame(), found, f"Could not read {found.name}: {exc}"

    workbook_hit = _read_from_workbook(run_dir, files_by_name, dataset, workbook_cache)
    if workbook_hit[0] is not None:
        dataframe, workbook_path, sheet_name, warning = workbook_hit
        return dataframe, (workbook_path, sheet_name), warning
    return pd.DataFrame(), None, None


def _read_from_workbook(
    run_dir: Path,
    files_by_name: dict[str, Path],
    dataset: str,
    workbook_cache: dict[Path, pd.ExcelFile],
) -> tuple[pd.DataFrame | None, Path | None, str | None, str | None]:
    hints = SHEET_HINTS.get(dataset, [])
    if not hints:
        return None, None, None, None
    for workbook_name in WORKBOOK_ALIASES:
        workbook_path = _find_file(files_by_name, [workbook_name])
        if workbook_path is None or workbook_path.stat().st_size == 0:
            continue
        try:
            excel = workbook_cache.get(workbook_path)
            if excel is None:
                excel = pd.ExcelFile(workbook_path)
                workbook_cache[workbook_path] = excel
            sheet_name = _match_sheet(excel.sheet_names, hints)
            if not sheet_name:
                continue
            return excel.parse(sheet_name), workbook_path, sheet_name, None
        except Exception as exc:  # pragma: no cover - shown in dashboard
            return pd.DataFrame(), workbook_path, None, f"Could not read {workbook_path.name}: {exc}"
    return None, None, None, None


def _match_sheet(sheet_names: list[str], hints: list[str]) -> str | None:
    normalised = {_normalise_token(sheet): sheet for sheet in sheet_names}
    for hint in hints:
        token = _normalise_token(hint)
        if token in normalised:
            return normalised[token]
    for hint in hints:
        token = _normalise_token(hint)
        for sheet_token, sheet_name in normalised.items():
            if token in sheet_token:
                return sheet_name
    return None


def _normalise_token(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in str(value)).strip("_")


def _find_file(files_by_name: dict[str, Path], aliases: list[str]) -> Path | None:
    for alias in aliases:
        hit = files_by_name.get(alias.lower())
        if hit is not None:
            return hit
    return None


def _status_row(dataset: str, found: Path | tuple[Path, str] | None, rows: int | None, columns: int | None) -> dict[str, Any]:
    if isinstance(found, tuple):
        path, sheet = found
        file_label = f"{path.name} [{sheet}]"
        stat_path = path
    else:
        file_label = found.name if found is not None else ", ".join(FILE_ALIASES.get(dataset, []))
        stat_path = found
    if stat_path is not None:
        stat = stat_path.stat()
        size = _format_size(stat.st_size)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    else:
        size = "-"
        modified = "-"
    return {
        "Dataset": dataset.replace("_", " ").title(),
        "File": file_label,
        "Found?": "Yes" if found is not None else "No",
        "Rows": f"{rows:,}" if rows is not None else "-",
        "Columns": f"{columns:,}" if columns is not None else "-",
        "Size": size,
        "Last modified": modified,
    }


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _empty_status_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["Dataset", "File", "Found?", "Rows", "Columns", "Size", "Last modified"])

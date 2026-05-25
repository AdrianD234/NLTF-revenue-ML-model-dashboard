from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .chart_sources import write_chart_source_tables
from .config import (
    DashboardData,
    PARQUET_CANDIDATE_FILE,
    PARQUET_CSV_MIRROR_FILE,
    PARQUET_METADATA_FILE,
)
from .diagnostics import (
    build_diagnostic_acf_source_table,
    build_diagnostic_frame,
    load_diagnostic_audit_tables,
)
from .locate import candidate_search_roots, locate_dashboard_file
from .manifest import build_data_source_manifest, write_data_source_manifest
from .transforms import STRESS_BUCKET_SOURCES, normalise_parquet_candidate
from ..labels import SCHIFF_SPEC_BENCHMARK_LABEL, STRESS_BUCKET_ORDER, humanize_label
from ..metrics import (
    add_stream_fields,
    best_by_stream,
    normalise_paired,
    normalise_predictions,
    normalise_stress,
    normalise_weights,
)


LoadedRun = DashboardData


def parquet_pack_signature(data_root: str | Path, repo_root: str | Path | None = None) -> tuple[tuple[str, int, int], ...]:
    roots = candidate_search_roots(data_root, repo_root)
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


def load_parquet_dashboard(
    data_root: str | Path,
    repo_root: str | Path | None = None,
    *,
    allow_csv_preview: bool = False,
) -> LoadedRun:
    roots = candidate_search_roots(data_root, repo_root)
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

    audit_tables, audit_status, audit_warnings = load_diagnostic_audit_tables(roots)
    status_rows.extend(audit_status)
    warnings.extend(audit_warnings)
    diagnostic = build_diagnostic_frame(candidate, audit_tables)
    paired = _paired_frame(recommended, schiff, audit_tables)
    stress = _stress_frame(recommended)
    horizon = _horizon_frame(pd.concat([recommended, schiff], ignore_index=True))
    weights = _ensemble_frame(candidate)
    quarterly_predictions, quarterly_predictions_path = _load_optional_pack_csv(roots, "quarterly_predictions_selected.csv")
    annual_predictions, annual_predictions_path = _load_optional_pack_csv(roots, "annual_predictions_selected.csv")
    status_rows.append(
        _status_row(
            "quarterly predictions selected",
            quarterly_predictions_path,
            len(quarterly_predictions) if quarterly_predictions_path else None,
            len(quarterly_predictions.columns) if quarterly_predictions_path else None,
        )
    )
    status_rows.append(
        _status_row(
            "annual predictions selected",
            annual_predictions_path,
            len(annual_predictions) if annual_predictions_path else None,
            len(annual_predictions.columns) if annual_predictions_path else None,
        )
    )
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


def _load_optional_pack_csv(roots: list[Path], filename: str) -> tuple[pd.DataFrame, Path | None]:
    path = locate_dashboard_file(filename, roots)
    if path is None or not path.exists():
        return pd.DataFrame(), None
    try:
        return pd.read_csv(path, low_memory=False), path
    except Exception:
        return pd.DataFrame(), path


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
        out["baseline"] = SCHIFF_SPEC_BENCHMARK_LABEL
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


def _ensemble_frame(candidate: pd.DataFrame) -> pd.DataFrame:
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
    resolved_streams = {str(row.get("stream_label")) for row in rows if pd.notna(row.get("mape"))}
    unresolved_streams = sorted(required_streams.difference(resolved_streams))
    for stream_label in unresolved_streams:
        for page in ["Scenario Comparison", "Schiff Benchmark"]:
            for scenario in ["Finalist", "Schiff"]:
                rows.append(
                    {
                        "page": page,
                        "stream_label": stream_label,
                        "scenario": scenario,
                        "horizon": pd.NA,
                        "mape": pd.NA,
                        "source_column": "",
                        "source": "Missing: no Parquet horizon fields or selected prediction source available",
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
        "diagnostic_acf_source_table.csv": build_diagnostic_acf_source_table(
            data.get("quarterly_predictions", pd.DataFrame()),
            data.get("diagnostic_df", pd.DataFrame()),
        ),
    }
    for filename, frame in source_tables.items():
        frame.to_csv(artifacts / filename, index=False)
    write_chart_source_tables(repo_root, data)


def _status_row(dataset: str, found: Path | None, rows: int | None, columns: int | None) -> dict[str, Any]:
    if found is not None:
        stat = found.stat()
        file_label = found.name
        size = _format_size(stat.st_size)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    else:
        file_label = dataset
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


__all__ = [
    "LoadedRun",
    "build_ensemble_composition_source_table",
    "build_horizon_comparison_source_table",
    "build_scenario_comparison_source_table",
    "load_parquet_dashboard",
    "parquet_pack_signature",
]

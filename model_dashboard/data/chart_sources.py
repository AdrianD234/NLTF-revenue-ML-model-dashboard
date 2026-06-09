from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import pandas as pd

from ..labels import (
    OVERVIEW_STRESS_BUCKET_ORDER,
    SCHIFF_SPEC_BENCHMARK_LABEL,
    STRESS_BUCKET_ORDER,
    format_count,
    format_percent,
    format_pp,
    humanize_label,
)
from ..metrics import best_by_stream
from ..reproducibility_imports import diagnostics_r2_summary_frame, format_r2, reproducibility_component_r2_frame
from ..score_basis import PAPER_SCORE_BASIS, score_basis_label
from .diagnostics import DEFAULT_ACF_RESIDUAL_SCOPE, select_diagnostic_acf_scope


CORE_COLUMNS = [
    "page",
    "chart_id",
    "chart_title",
    "stream",
    "stream_label",
    "model",
    "model_short",
    "metric_name",
    "metric_value",
    "metric_display",
    "source_column",
    "source_file",
    "score_basis",
    "score_basis_label",
    "calculation_basis",
    "notes",
]

EXTRA_COLUMNS = [
    "horizon",
    "stress_bucket",
    "scenario",
    "scenario_role",
    "component_model",
    "component_short",
    "component_rank",
    "weight",
    "weight_pct",
    "lag",
    "acf_value",
    "diagnostic_test",
    "pass_status",
    "quarterly_mape",
    "annual_mape",
    "fitted",
    "residual_pct",
    "abs_error_pct",
    "horizon_bucket",
    "point_type",
    "frontier_sample_class",
    "frontier_sample_note",
    "x_metric",
    "y_metric",
    "value_available",
    "paired_common_pairs",
    "paired_model_mape",
    "paired_schiff_mape",
    "paired_gain_pp",
    "paired_win_rate_pct",
    "recommendation",
    "r2_type",
    "forecast_r2",
    "calibration_r2",
    "component_r2",
    "n_rows",
    "sse",
    "sst",
    "bias_pct",
    "mape",
    "interpretation",
    "source_prediction_column",
    "calibration_r2_source_column",
]

CHART_SOURCE_FILES = {
    "overview_finalist_forecast_accuracy.csv": ("Overview", "overview_finalist_forecast_accuracy"),
    "overview_candidate_search_frontier.csv": ("Overview", "overview_candidate_search_frontier"),
    "overview_ensemble_composition.csv": ("Overview", "overview_ensemble_composition"),
    "overview_stress_horizon_checks.csv": ("Overview", "overview_stress_horizon_checks"),
    "diagnostics_residual_autocorrelation.csv": ("Diagnostics", "diagnostics_residual_autocorrelation"),
    "diagnostics_residual_vs_fitted.csv": ("Diagnostics", "diagnostics_residual_vs_fitted"),
    "diagnostics_pass_matrix.csv": ("Diagnostics", "diagnostics_pass_matrix"),
    "diagnostics_error_distribution_by_horizon.csv": ("Diagnostics", "diagnostics_error_distribution_by_horizon"),
    "diagnostics_r2_summary.csv": ("Diagnostics", "diagnostics_r2_summary"),
    "scenario_stream_comparison.csv": ("Scenario Comparison", "scenario_stream_comparison"),
    "scenario_improvement_vs_benchmark.csv": ("Scenario Comparison", "scenario_improvement_vs_benchmark"),
    "scenario_horizon_comparison.csv": ("Scenario Comparison", "scenario_horizon_comparison"),
    "scenario_decision_summary.csv": ("Scenario Comparison", "scenario_decision_summary"),
    "schiff_vs_finalist_mape.csv": ("Schiff Benchmark", "schiff_vs_finalist_mape"),
    "schiff_benchmark_horizon_profiles.csv": ("Schiff Benchmark", "schiff_benchmark_horizon_profiles"),
    "schiff_paired_or_fullsample_gain.csv": ("Schiff Benchmark", "schiff_paired_or_fullsample_gain"),
    "schiff_benchmark_summary.csv": ("Schiff Benchmark", "schiff_benchmark_summary"),
    "reproducibility_component_r2.csv": ("Governance & Reproducibility", "reproducibility_component_r2"),
}


def write_chart_source_tables(repo_root: Path, data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Write one auditable source table for every primary dashboard chart."""
    output_dir = repo_root / "artifacts" / "chart_sources"
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = build_chart_source_tables(data, repo_root=repo_root)
    for filename, frame in tables.items():
        _write_csv_atomic(frame, output_dir / filename)
    return tables


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False)
    for attempt in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.25 * (attempt + 1))


def build_chart_source_tables(data: dict[str, pd.DataFrame], repo_root: Path | None = None) -> dict[str, pd.DataFrame]:
    source_file = _source_file_from_manifest(data)
    source_files = _chart_contract_source_files(data, source_file)
    recommended = data.get("recommended", pd.DataFrame())
    summary = data.get("summary", pd.DataFrame())
    weights = data.get("weights", pd.DataFrame())
    stress = data.get("stress", pd.DataFrame())
    diagnostics = data.get("diagnostic_df", data.get("diagnostic", pd.DataFrame()))
    scorecard_predictions = data.get("scorecard_predictions", pd.DataFrame())
    qpred = data.get("quarterly_predictions", pd.DataFrame())
    error_distribution = data.get("error_distribution", pd.DataFrame())
    pass_matrix = data.get("diagnostic_pass_matrix", pd.DataFrame())
    paired = data.get("paired_vs_schiff", pd.DataFrame())
    schiff = data.get("schiff_df", data.get("schiff_benchmark", pd.DataFrame()))
    horizon = data.get("horizon_df", pd.DataFrame())
    comparison = _scenario_comparison_from_pack(data.get("scenario_comparison", pd.DataFrame()))
    if comparison.empty:
        comparison = _scenario_comparison(recommended, schiff if not schiff.empty else summary, paired)
    horizon_source = _horizon_source(horizon, qpred, recommended)
    acf_source = _normalise_direct_acf(data.get("diagnostic_acf", pd.DataFrame()))
    if acf_source.empty:
        acf_source = _acf_source(qpred, diagnostics)
    diagnostic_window = _central_error_window(qpred)
    error_window = error_distribution if error_distribution is not None and not error_distribution.empty else diagnostic_window
    matrix_source = pass_matrix if pass_matrix is not None and not pass_matrix.empty else diagnostics

    return {
        "overview_kpi_cards.csv": _overview_kpi_cards_source(
            recommended,
            schiff,
            f"{source_files['overview_finalist_forecast_accuracy']};{source_files['schiff_vs_finalist_mape']}",
        ),
        "overview_finalist_forecast_accuracy.csv": _overview_finalist_accuracy(recommended, source_files["overview_finalist_forecast_accuracy"]),
        "overview_candidate_search_frontier.csv": _overview_candidate_frontier(summary, source_files["overview_candidate_search_frontier"]),
        "overview_ensemble_composition.csv": _overview_ensemble(weights, source_files["overview_ensemble_composition"]),
        "overview_stress_horizon_checks.csv": _overview_stress(stress, source_files["overview_stress_horizon_checks"]),
        "diagnostics_residual_autocorrelation.csv": _diagnostics_acf(acf_source, source_files["diagnostics_residual_autocorrelation"]),
        "diagnostics_residual_vs_fitted.csv": _diagnostics_residual_vs_fitted(diagnostic_window, source_files["diagnostics_residual_vs_fitted"]),
        "diagnostics_pass_matrix.csv": _diagnostics_pass_matrix(matrix_source, source_files["diagnostics_pass_matrix"]),
        "diagnostics_error_distribution_by_horizon.csv": _diagnostics_error_distribution(error_window, source_files["diagnostics_error_distribution_by_horizon"]),
        "diagnostics_r2_summary.csv": _diagnostics_r2_summary(scorecard_predictions, diagnostics, source_files["diagnostics_r2_summary"]),
        "scenario_stream_comparison.csv": _scenario_stream_comparison_source(comparison, source_files["scenario_stream_comparison"]),
        "scenario_improvement_vs_benchmark.csv": _scenario_gain_source(
            comparison,
            "Scenario Comparison",
            "scenario_improvement_vs_benchmark",
            "2. Improvement vs Benchmark",
            source_files["scenario_improvement_vs_benchmark"],
        ),
        "scenario_horizon_comparison.csv": _horizon_chart_source(
            horizon_source,
            "Scenario Comparison",
            "scenario_horizon_comparison",
            "3. Horizon Comparison",
            source_files["scenario_horizon_comparison"],
        ),
        "scenario_decision_summary.csv": _scenario_decision_source(comparison, source_files["scenario_decision_summary"]),
        "schiff_vs_finalist_mape.csv": _schiff_mape_source(comparison, source_files["schiff_vs_finalist_mape"]),
        "schiff_benchmark_horizon_profiles.csv": _horizon_chart_source(
            horizon_source,
            "Schiff Benchmark",
            "schiff_benchmark_horizon_profiles",
            "2. Benchmark Horizon Profiles",
            source_files["schiff_benchmark_horizon_profiles"],
        ),
        "schiff_paired_or_fullsample_gain.csv": _scenario_gain_source(
            comparison,
            "Schiff Benchmark",
            "schiff_paired_or_fullsample_gain",
            "3. Full-sample Gain vs Schiff specification benchmark",
            source_files["schiff_paired_or_fullsample_gain"],
        ),
        "schiff_benchmark_summary.csv": _schiff_summary_source(comparison, source_files["schiff_benchmark_summary"]),
        "reproducibility_component_r2.csv": _reproducibility_component_r2(repo_root, source_files["reproducibility_component_r2"]),
    }


def _chart_contract_source_files(data: dict[str, pd.DataFrame], default: str) -> dict[str, str]:
    aliases = {
        "overview_finalist_forecast_accuracy": "finalist_forecast_accuracy",
        "overview_candidate_search_frontier": "candidate_search_frontier",
        "overview_ensemble_composition": "finalist_ensemble_composition",
        "overview_stress_horizon_checks": "stress_horizon_checks",
        "diagnostics_residual_autocorrelation": "residual_autocorrelation_by_lag",
        "diagnostics_residual_vs_fitted": "residual_vs_fitted",
        "diagnostics_pass_matrix": "diagnostic_pass_matrix",
        "diagnostics_error_distribution_by_horizon": "error_distribution_by_horizon",
        "diagnostics_r2_summary": "scorecard_predictions",
        "scenario_stream_comparison": "stream_comparison",
        "scenario_improvement_vs_benchmark": "improvement_vs_benchmark",
        "scenario_horizon_comparison": "horizon_comparison",
        "scenario_decision_summary": "decision_summary",
        "schiff_vs_finalist_mape": "schiff_vs_finalist_mape",
        "schiff_benchmark_horizon_profiles": "benchmark_horizon_profiles",
        "schiff_paired_or_fullsample_gain": "fullsample_gain_vs_schiff",
        "schiff_benchmark_summary": "benchmark_summary",
        "reproducibility_component_r2": "component_predictions",
    }
    result = {chart_id: default for _, chart_id in CHART_SOURCE_FILES.values()}
    contract = data.get("chart_contract", pd.DataFrame())
    if contract is None or contract.empty or not {"chart_id", "source_table"}.issubset(contract.columns):
        return result
    lookup = dict(zip(contract["chart_id"].astype(str), contract["source_table"].astype(str), strict=False))
    for chart_id, contract_id in aliases.items():
        result[chart_id] = lookup.get(contract_id, default)
    return result


def _source_file_from_manifest(data: dict[str, pd.DataFrame]) -> str:
    manifest = data.get("curated_manifest", pd.DataFrame())
    if manifest is not None and not manifest.empty:
        for column in ["parquet_path", "source_file", "source"]:
            if column in manifest.columns:
                value = manifest[column].dropna().astype(str)
                if not value.empty and value.iloc[0]:
                    return value.iloc[0]
    return "Parquet candidate cone and diagnostic audit pack"


def _aggregate_row(score_basis: Any = PAPER_SCORE_BASIS) -> dict[str, Any]:
    basis = score_basis if pd.notna(score_basis) else PAPER_SCORE_BASIS
    return {
        "stream": "All Streams",
        "stream_label": "All Streams",
        "model": "Current finalist and Schiff specification benchmark stream means",
        "model_short": "All-stream KPI aggregate",
        "score_basis": basis,
        "score_basis_label": score_basis_label(basis),
    }


def _normalise_direct_acf(acf: pd.DataFrame) -> pd.DataFrame:
    columns = ["stream_label", "lag", "acf_value", "residual_source", "calculation_method", "source_column"]
    if acf is None or acf.empty:
        return pd.DataFrame(columns=columns)
    out = select_diagnostic_acf_scope(acf, DEFAULT_ACF_RESIDUAL_SCOPE)
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out[columns]


def _scenario_comparison_from_pack(comparison: pd.DataFrame) -> pd.DataFrame:
    if comparison is None or comparison.empty:
        return pd.DataFrame()
    out = comparison.copy()
    rename = {
        "full_sample_qtr_gain_pp": "quarterly_gain_pp",
        "full_sample_annual_gain_pp": "annual_gain_pp",
        "paired_win_rate_pct": "paired_win_rate_pct",
    }
    for source, target in rename.items():
        if source in out.columns and target not in out.columns:
            out[target] = out[source]
    if "win_rate" not in out.columns and "paired_win_rate_pct" in out.columns:
        out["win_rate"] = out["paired_win_rate_pct"]
    for column in [
        "stream",
        "stream_label",
        "finalist_model",
        "finalist_model_short",
        "schiff_model",
        "schiff_model_short",
        "finalist_quarterly_mape",
        "schiff_quarterly_mape",
        "quarterly_gain_pp",
        "finalist_annual_mape",
        "schiff_annual_mape",
        "annual_gain_pp",
        "paired_common_pairs",
        "paired_finalist_mape",
        "paired_schiff_mape",
        "paired_gain_pp",
        "paired_win_rate_pct",
        "recommendation",
    ]:
        if column not in out.columns:
            out[column] = pd.NA
    out["paired_model_mape"] = out.get("paired_finalist_mape", pd.Series(pd.NA, index=out.index))
    return out


def _standardize(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in CORE_COLUMNS + EXTRA_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    remaining = [column for column in frame.columns if column not in CORE_COLUMNS + EXTRA_COLUMNS]
    return frame[CORE_COLUMNS + EXTRA_COLUMNS + remaining]


def _row_get(row: Any, key: str, default: Any = pd.NA) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row.get(key, default)
    except AttributeError:
        return default


def _clean_model_short(row: Any) -> Any:
    return _row_get(row, "model_short", _row_get(row, "ensemble_short", pd.NA))


def _base_row(
    page: str,
    chart_id: str,
    chart_title: str,
    row: Any,
    metric_name: str,
    metric_value: Any,
    metric_display: str,
    source_column: str,
    source_file: str,
    calculation_basis: str,
    notes: str = "",
    **extra: Any,
) -> dict[str, Any]:
    basis = _row_get(row, "score_basis", _row_get(row, "default_score_basis", PAPER_SCORE_BASIS))
    payload = {
        "page": page,
        "chart_id": chart_id,
        "chart_title": chart_title,
        "stream": _row_get(row, "stream"),
        "stream_label": _row_get(row, "stream_label"),
        "model": _row_get(row, "model", _row_get(row, "ensemble")),
        "model_short": _clean_model_short(row),
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": metric_display,
        "source_column": source_column,
        "source_file": _row_get(row, "source_file", source_file) or source_file,
        "score_basis": basis,
        "score_basis_label": _row_get(row, "score_basis_label", score_basis_label(basis)),
        "calculation_basis": calculation_basis,
        "notes": notes,
    }
    payload.update(extra)
    return payload


def _num(value: Any) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if pd.notna(number) else float("nan")


def _point_type(row: pd.Series) -> str:
    if bool(_row_get(row, "is_current_recommended", False)) or bool(_row_get(row, "is_recommended_finalist", False)):
        return "Selected finalist"
    if bool(_row_get(row, "is_pure_schiff", False)) or bool(_row_get(row, "is_schiff", False)):
        return SCHIFF_SPEC_BENCHMARK_LABEL
    if bool(_row_get(row, "is_pdf_reference", False)):
        return "PDF reference"
    if bool(_row_get(row, "is_frontier", False)):
        return "Frontier candidate"
    if bool(_row_get(row, "is_distribution_sample", False)):
        return "Distribution sample"
    return "Candidate"


def _overview_kpi_cards_source(recommended: pd.DataFrame, schiff_rows: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    finalists = best_by_stream(recommended)
    schiff = best_by_stream(schiff_rows)
    if finalists.empty:
        return _standardize(rows)

    basis_values = finalists["score_basis"].dropna().astype(str) if "score_basis" in finalists.columns else pd.Series(dtype=str)
    basis = basis_values.iloc[0] if not basis_values.empty else PAPER_SCORE_BASIS
    aggregate = _aggregate_row(basis)

    def add_stream_rows(frame: pd.DataFrame, role: str, source_name: str) -> None:
        for _, row in frame.iterrows():
            for metric_name, column in [("Quarterly MAPE", "quarterly_mape"), ("Annual MAPE", "annual_mape")]:
                value = _num(row.get(column))
                rows.append(
                    _base_row(
                        "Overview",
                        "overview_kpi_cards",
                        "Overview KPI Cards",
                        row,
                        f"{role} {metric_name}",
                        value,
                        format_percent(value),
                        str(_row_get(row, f"{column}_source_column", column)),
                        source_name,
                        f"Stream-level {role.lower()} value used to compute the Overview KPI simple stream mean.",
                        f"{role} stream value; aggregate KPI rows use a simple mean across the three stream rows.",
                    )
                )

    add_stream_rows(finalists, "Finalist", "finalists.parquet")
    add_stream_rows(schiff, "Schiff specification benchmark", "schiff_benchmark.parquet")

    finalist_q = float(finalists["quarterly_mape"].mean()) if "quarterly_mape" in finalists.columns else float("nan")
    finalist_a = float(finalists["annual_mape"].mean()) if "annual_mape" in finalists.columns else float("nan")
    schiff_q = float(schiff["quarterly_mape"].mean()) if not schiff.empty and "quarterly_mape" in schiff.columns else float("nan")
    schiff_a = float(schiff["annual_mape"].mean()) if not schiff.empty and "annual_mape" in schiff.columns else float("nan")
    q_gain = schiff_q - finalist_q if pd.notna(schiff_q) and pd.notna(finalist_q) else float("nan")
    annual_gain = schiff_a - finalist_a if pd.notna(schiff_a) and pd.notna(finalist_a) else float("nan")

    aggregates = [
        ("Finalist quarterly MAPE mean", finalist_q, "quarterly_mape", "finalists.parquet", "Simple stream mean of current finalist quarterly_mape values."),
        ("Schiff specification quarterly MAPE mean", schiff_q, "quarterly_mape", "schiff_benchmark.parquet", "Simple stream mean of Schiff specification quarterly_mape values."),
        ("Quarterly gain vs Schiff specification benchmark", q_gain, "quarterly_mape", source_file, "Schiff specification quarterly mean minus finalist quarterly mean."),
        ("Finalist annual MAPE mean", finalist_a, "annual_mape", "finalists.parquet", "Simple stream mean of current finalist annual_mape values."),
        ("Schiff specification annual MAPE mean", schiff_a, "annual_mape", "schiff_benchmark.parquet", "Simple stream mean of Schiff specification annual_mape values."),
        ("Annual gain vs Schiff specification benchmark", annual_gain, "annual_mape", source_file, "Schiff specification annual mean minus finalist annual mean."),
    ]
    for metric_name, value, source_column, source_name, basis_text in aggregates:
        rows.append(
            _base_row(
                "Overview",
                "overview_kpi_cards",
                "Overview KPI Cards",
                aggregate,
                metric_name,
                value,
                format_pp(value) if "gain" in metric_name.lower() else format_percent(value),
                source_column,
                source_name,
                basis_text,
                "Overview KPI benchmark uses the explicit schiff_benchmark.parquet rows, not candidate-cone challenger rows.",
            )
        )

    return _standardize(rows)


def _overview_finalist_accuracy(recommended: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    finalists = best_by_stream(recommended)
    for _, row in finalists.iterrows():
        for metric_name, column in [("Quarterly MAPE", "quarterly_mape"), ("Annual MAPE", "annual_mape")]:
            value = _num(row.get(column))
            source_column = _row_get(
                row,
                "quarterly_mape_source_column" if column == "quarterly_mape" else "annual_mape_source_column",
                column,
            )
            rows.append(
                _base_row(
                    "Overview",
                    "overview_finalist_forecast_accuracy",
                    "1. Finalist Forecast Accuracy",
                    row,
                    metric_name,
                    value,
                    format_percent(value),
                    str(source_column),
                    source_file,
                    "Current recommended finalist row selected from Parquet is_current_recommended flag and projected to the selected score basis.",
                    quarterly_mape=row.get("quarterly_mape"),
                    annual_mape=row.get("annual_mape"),
                )
            )
    return _standardize(rows)


def _overview_candidate_frontier(summary: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if summary is None or summary.empty:
        return _standardize(rows)
    required = {"quarterly_mape", "annual_mape"}
    if not required.issubset(summary.columns):
        return _standardize(rows)
    data = summary.dropna(subset=["quarterly_mape", "annual_mape"]).copy()
    for _, row in data.iterrows():
        qtr = _num(row.get("quarterly_mape"))
        annual = _num(row.get("annual_mape"))
        role = _point_type(row)
        source_column = (
            f"{_row_get(row, 'quarterly_mape_source_column', 'quarterly_mape')};"
            f"{_row_get(row, 'annual_mape_source_column', 'annual_mape')}"
        )
        rows.append(
            _base_row(
                "Overview",
                "overview_candidate_search_frontier",
                "2. Candidate Search Frontier",
                row,
                "Candidate frontier point",
                qtr,
                f"Qtr {format_percent(qtr)} / Annual {format_percent(annual)}",
                source_column,
                source_file,
                "Default all-stream frontier rows; x and y use the selected score basis.",
                "Balanced all-stream frontier view; visual frontier samples are anchored to current finalists and Schiff specification benchmarks and are excluded from governance scoring.",
                quarterly_mape=qtr,
                annual_mape=annual,
                point_type=role,
                frontier_sample_class=row.get("frontier_sample_class"),
                frontier_sample_note=row.get("frontier_sample_note"),
                x_metric=qtr,
                y_metric=annual,
            )
        )
    return _standardize(rows)


def _overview_ensemble(weights: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if weights is None or weights.empty:
        return _standardize(rows)
    data = weights.copy()
    if "component_rank" not in data.columns:
        data = data.sort_values(["stream_label", "weight"], ascending=[True, False])
        data["component_rank"] = data.groupby("stream_label", dropna=False).cumcount() + 1
    for _, row in data.iterrows():
        weight = _num(row.get("weight"))
        weight_pct = weight * 100 if pd.notna(weight) else float("nan")
        rows.append(
            _base_row(
                "Overview",
                "overview_ensemble_composition",
                "3. Finalist Ensemble Composition",
                row,
                "Component weight",
                weight_pct,
                format_percent(weight_pct, 1),
                "ensemble_components_json.weight",
                source_file,
                "Current finalist component weights parsed from Parquet ensemble_components_json.",
                component_model=row.get("component_model"),
                component_short=row.get("component_short"),
                component_rank=row.get("component_rank"),
                weight=weight,
                weight_pct=weight_pct,
            )
        )
    return _standardize(rows)


def _overview_stress(stress: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if stress is None or stress.empty:
        return _standardize(rows)
    data = stress.copy()
    data = data[data["stress_bucket"].astype(str).isin(OVERVIEW_STRESS_BUCKET_ORDER)].copy()
    data["stress_bucket"] = pd.Categorical(data["stress_bucket"].astype(str), categories=OVERVIEW_STRESS_BUCKET_ORDER, ordered=True)
    for _, row in data.sort_values(["stream_label", "stress_bucket"]).iterrows():
        value = _num(row.get("mape"))
        rows.append(
            _base_row(
                "Overview",
                "overview_stress_horizon_checks",
                "4. Stress and Horizon Checks",
                row,
                "Stress-window MAPE",
                value,
                format_percent(value),
                str(row.get("source_column", "")),
                source_file,
                "Default Overview uses paper-style horizon buckets only; policy windows are excluded from the main line chart.",
                stress_bucket=str(row.get("stress_bucket")),
                value_available=bool(pd.notna(row.get("mape"))),
            )
        )
    return _standardize(rows)


def _acf_source(qpred: pd.DataFrame, diagnostics: pd.DataFrame | None = None, max_lag: int = 12) -> pd.DataFrame:
    columns = ["stream_label", "lag", "acf_value", "residual_source", "calculation_method", "source_column"]
    if qpred is None or qpred.empty or not {"error_pct", "stream_label"}.issubset(qpred.columns):
        return _acf_source_from_diagnostics(diagnostics, columns)
    data = qpred.dropna(subset=["error_pct", "stream_label"]).copy()
    if data.empty:
        return _acf_source_from_diagnostics(diagnostics, columns)
    if "target_period" in data.columns:
        data["_period_key"] = data["target_period"].map(_period_key)
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
                    "source_column": "error_pct",
                }
            )
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return _acf_source_from_diagnostics(diagnostics, columns)
    return frame


def _acf_source_from_diagnostics(diagnostics: pd.DataFrame | None, columns: list[str]) -> pd.DataFrame:
    if diagnostics is None or diagnostics.empty or "acf1_resid" not in diagnostics.columns or "stream_label" not in diagnostics.columns:
        return pd.DataFrame(columns=columns)
    data = diagnostics.copy()
    if "role" in data.columns:
        finalist_rows = data[data["role"].astype(str).str.contains("finalist", case=False, na=False)]
        if not finalist_rows.empty:
            data = finalist_rows
    rows: list[dict[str, Any]] = []
    for _, row in data.dropna(subset=["stream_label"]).iterrows():
        value = pd.to_numeric(row.get("acf1_resid"), errors="coerce")
        if pd.isna(value):
            continue
        rows.append(
            {
                "stream_label": row.get("stream_label"),
                "lag": 1,
                "acf_value": float(value),
                "residual_source": "H1 residual diagnostics from diagnostic audit pack",
                "calculation_method": "Lag 1 residual autocorrelation supplied by H1 residual diagnostics audit table",
                "source_column": "acf1_resid",
            }
        )
    return pd.DataFrame(rows, columns=columns).drop_duplicates(subset=["stream_label", "lag"], keep="last")


def _period_key(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("Q", "-Q")


def _diagnostics_acf(acf: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in acf.iterrows():
        value = _num(row.get("acf_value"))
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_residual_autocorrelation",
                "1. Residual Autocorrelation by Lag",
                row,
                "Residual ACF",
                value,
                f"{value:.3f}" if pd.notna(value) else "-",
                str(row.get("source_column", "error_pct")),
                source_file,
                str(row.get("calculation_method")),
                str(row.get("residual_source")),
                lag=row.get("lag"),
                acf_value=value,
            )
        )
    return _standardize(rows)


def _central_error_window(qpred: pd.DataFrame, lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    if qpred is None or qpred.empty or "error_pct" not in qpred.columns:
        return qpred if qpred is not None else pd.DataFrame()
    values = pd.to_numeric(qpred["error_pct"], errors="coerce")
    valid = values.dropna()
    if len(valid) < 20:
        return qpred
    low, high = valid.quantile([lower, upper])
    return qpred[values.between(low, high, inclusive="both")].copy()


def _horizon_bucket(value: Any) -> str:
    horizon = pd.to_numeric(value, errors="coerce")
    if pd.isna(horizon):
        return "Unknown"
    number = int(horizon)
    if number <= 4:
        return "1-4 qtrs"
    if number <= 8:
        return "5-8 qtrs"
    return "9-12 qtrs"


def _diagnostics_residual_vs_fitted(qpred: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if qpred is None or qpred.empty:
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_residual_vs_fitted",
                "2. Residual vs Fitted",
                {},
                "Missing selected prediction rows",
                pd.NA,
                "-",
                "",
                source_file,
                "Residual vs fitted native stream units are unavailable because selected prediction rows are missing.",
                "Missing: quarterly_predictions_selected.csv was not supplied by the diagnostic audit pack.",
                value_available=False,
            )
        )
        return _standardize(rows)
    for _, row in qpred.iterrows():
        pred = _num(row.get("pred"))
        error = _num(row.get("error_pct"))
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_residual_vs_fitted",
                "2. Residual vs Fitted",
                row,
                "Signed residual percent",
                error,
                format_percent(error),
                "pred;error_pct",
                source_file,
                "Residual / forecast error percent versus fitted value in native stream units after central error-window trimming.",
                fitted=pred,
                residual_pct=error,
            )
        )
    return _standardize(rows)


def _diagnostic_status(label: str, value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "Unavailable"
    if label == "Calibration R2":
        return "Pass" if number >= 0.70 else "Fail"
    if label == "Durbin-Watson":
        return "Pass" if 1.5 <= number <= 2.5 else "Fail"
    if label == "ADF":
        return "Pass" if number < 0.05 else "Fail"
    if label == "KPSS":
        return "Pass" if number > 0.05 else "Fail"
    if label in {"Breusch-Pagan", "White", "Cointegration"}:
        threshold_pass = number < 0.05 if label == "Cointegration" else number > 0.05
        return "Pass" if threshold_pass else "Fail"
    if label == "Jarque-Bera":
        return "Caution" if number <= 0.05 else "Pass"
    return "Unavailable"


def _diagnostics_pass_matrix(diagnostics: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if diagnostics is None or diagnostics.empty:
        return _standardize(rows)
    if {"diagnostic_test", "pass_status"}.issubset(diagnostics.columns):
        for _, row in diagnostics.iterrows():
            rows.append(
                _base_row(
                    "Diagnostics",
                    "diagnostics_pass_matrix",
                    "3. Diagnostic Pass Matrix",
                    row,
                    str(row.get("diagnostic_test")),
                    pd.NA,
                    str(row.get("pass_status")),
                    "pass_status",
                    source_file,
                    "Diagnostic pass matrix supplied by diagnostic_pass_matrix.parquet with Pass / Watch / Fail semantics.",
                    diagnostic_test=row.get("diagnostic_test"),
                    pass_status=row.get("pass_status"),
                    value_available=row.get("value_available", True),
                )
            )
        return _standardize(rows)
    data = diagnostics.copy()
    if "role" in data.columns:
        data = data[data["role"].astype(str).str.contains("finalist", case=False, na=False)]
    tests = [
        ("Calibration R2", "adj_r2"),
        ("Durbin-Watson", "durbin_watson"),
        ("ADF", "adf_pvalue"),
        ("KPSS", "kpss_pvalue"),
        ("Breusch-Pagan", "breusch_pagan_pvalue"),
        ("White", "white_pvalue"),
        ("Jarque-Bera", "jarque_bera_pvalue"),
        ("Cointegration", "cointegration_pvalue"),
    ]
    for _, row in data.iterrows():
        statuses = {label: _diagnostic_status(label, row.get(column)) for label, column in tests}
        core = {"Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"}
        overall = "Fail" if any(statuses[label] == "Fail" for label in core) else "Watch" if any(status in {"Fail", "Caution", "Watch"} for status in statuses.values()) else "Pass"
        for label, column in tests:
            rows.append(
                _base_row(
                    "Diagnostics",
                    "diagnostics_pass_matrix",
                    "3. Diagnostic Pass Matrix",
                    row,
                    label,
                    _num(row.get(column)),
                    statuses[label],
                    column,
                    source_file,
                    "Diagnostic pass matrix uses Pass / Watch / Fail with normality caution not treated as automatic overall fail.",
                    diagnostic_test=label,
                    pass_status=statuses[label],
                )
            )
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_pass_matrix",
                "3. Diagnostic Pass Matrix",
                row,
                "Overall",
                pd.NA,
                overall,
                "derived_overall_status",
                source_file,
                "Overall fails on core diagnostic failures; normality-only concerns are Watch.",
                diagnostic_test="Overall",
                pass_status=overall,
            )
        )
    return _standardize(rows)


def _diagnostics_error_distribution(qpred: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if qpred is None or qpred.empty:
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_error_distribution_by_horizon",
                "4. Error Distribution by Horizon",
                {},
                "Missing selected prediction rows",
                pd.NA,
                "-",
                "",
                source_file,
                "Absolute percentage error by horizon is unavailable because selected prediction rows are missing.",
                "Missing: quarterly_predictions_selected.csv was not supplied by the diagnostic audit pack.",
                value_available=False,
            )
        )
        return _standardize(rows)
    for _, row in qpred.iterrows():
        abs_error = _num(row.get("abs_error_pct", abs(_num(row.get("error_pct")))))
        bucket = _horizon_bucket(row.get("horizon"))
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_error_distribution_by_horizon",
                "4. Error Distribution by Horizon",
                row,
                "Absolute percentage error",
                abs_error,
                format_percent(abs_error),
                "abs_error_pct",
                source_file,
                "Absolute percentage error grouped by stream and horizon bucket after central error-window trimming.",
                horizon=row.get("horizon"),
                horizon_bucket=bucket,
                abs_error_pct=abs_error,
            )
        )
    return _standardize(rows)


def _diagnostics_r2_summary(scorecard_predictions: pd.DataFrame, diagnostics: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    summary = diagnostics_r2_summary_frame(scorecard_predictions, diagnostics)
    if summary.empty:
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_r2_summary",
                "Forecast R2 versus calibration R2",
                {},
                "Forecast R2",
                pd.NA,
                "-",
                "pred",
                "scorecard_predictions.parquet",
                "Forecast R2 is unavailable because scorecard prediction rows are missing.",
                "Calibration R2 is actual-on-forecast validation R2, not in-sample training fit.",
                value_available=False,
                calibration_r2_source_column=pd.NA,
            )
        )
        return _standardize(rows)
    for _, row in summary.iterrows():
        forecast_value = row.get("forecast_r2")
        calibration_value = row.get("calibration_r2")
        calibration_source_column = str(row.get("calibration_r2_source_column", "pred"))
        source_column = "pred" if calibration_source_column == "pred" else f"pred;{calibration_source_column}"
        rows.append(
            _base_row(
                "Diagnostics",
                "diagnostics_r2_summary",
                "Forecast R2 versus calibration R2",
                row,
                "Forecast R2",
                forecast_value,
                format_r2(forecast_value),
                source_column,
                "scorecard_predictions.parquet;diagnostic_tests.parquet",
                "Forecast R2 computed as 1 - SSE/SST from final scorecard predictions in native stream units.",
                "Calibration R2 is actual-on-forecast validation R2 and is reported separately from net forecast R2.",
                r2_type="forecast",
                forecast_r2=forecast_value,
                calibration_r2=calibration_value,
                n_rows=row.get("n_rows"),
                sse=row.get("sse"),
                sst=row.get("sst"),
                bias_pct=row.get("bias_pct"),
                mape=row.get("mape"),
                interpretation=row.get("interpretation"),
                source_prediction_column=row.get("source_prediction_column", "pred"),
                calibration_r2_source_column=calibration_source_column,
                value_available=pd.notna(pd.to_numeric(forecast_value, errors="coerce")),
            )
        )
    return _standardize(rows)


def _reproducibility_component_r2(repo_root: Path | None, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    summary = reproducibility_component_r2_frame(repo_root)
    if summary.empty:
        rows.append(
            _base_row(
                "Governance & Reproducibility",
                "reproducibility_component_r2",
                "Net forecast R2 after final model composition",
                {},
                "Forecast R2",
                pd.NA,
                "-",
                "final_pred",
                "data/dashboard_evidence_pack_reproducibility/*/component_predictions.parquet",
                "Reproducibility component R2 is unavailable because component prediction rows are missing.",
                "If actual variance is zero or rows are insufficient, R2 is unavailable rather than coerced to zero.",
                value_available=False,
            )
        )
        return _standardize(rows)
    for _, row in summary.iterrows():
        metric_name = str(row.get("metric_name", "Forecast R2"))
        metric_value = row.get("forecast_r2")
        component_value = pd.NA
        forecast_value = pd.NA
        if metric_name == "Component R2":
            component_value = metric_value
        else:
            forecast_value = metric_value
        rows.append(
            _base_row(
                "Governance & Reproducibility",
                "reproducibility_component_r2",
                "Net forecast R2 after final model composition",
                row,
                metric_name,
                metric_value,
                format_r2(metric_value),
                str(row.get("source_prediction_column", "final_pred")),
                str(row.get("source_file", source_file)),
                str(row.get("calculation_basis", "Forecast R2 computed as 1 - SSE/SST from stored prediction rows.")),
                "Negative R2 is valid but indicates poorer fit than the stream mean on these rows.",
                r2_type=row.get("r2_type"),
                forecast_r2=forecast_value,
                calibration_r2=row.get("calibration_r2"),
                component_r2=component_value,
                n_rows=row.get("n_rows"),
                sse=row.get("sse"),
                sst=row.get("sst"),
                bias_pct=row.get("bias_pct"),
                mape=row.get("mape"),
                interpretation=row.get("interpretation"),
                component_model=row.get("component_model"),
                component_rank=row.get("component_rank"),
                source_prediction_column=row.get("source_prediction_column"),
                value_available=pd.notna(pd.to_numeric(metric_value, errors="coerce")),
            )
        )
    return _standardize(rows)


def _scenario_comparison(recommended: pd.DataFrame, schiff_rows: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    finalists = best_by_stream(recommended)
    if schiff_rows is None or schiff_rows.empty:
        return pd.DataFrame()
    schiff = best_by_stream(schiff_rows[schiff_rows["is_schiff"]]) if "is_schiff" in schiff_rows.columns else best_by_stream(schiff_rows)
    if finalists.empty or schiff.empty:
        return pd.DataFrame()
    paired_by_stream = paired.set_index("stream_label") if paired is not None and not paired.empty and "stream_label" in paired.columns else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, finalist in finalists.iterrows():
        stream = finalist.get("stream")
        stream_schiff = schiff[schiff["stream"].astype(str).eq(str(stream))] if "stream" in schiff.columns else pd.DataFrame()
        if stream_schiff.empty:
            continue
        benchmark = stream_schiff.iloc[0]
        paired_row: Any = {}
        if not paired_by_stream.empty and finalist.get("stream_label") in paired_by_stream.index:
            paired_row = paired_by_stream.loc[finalist.get("stream_label")]
            if isinstance(paired_row, pd.DataFrame):
                paired_row = paired_row.iloc[0]
        fq = _num(finalist.get("quarterly_mape"))
        fa = _num(finalist.get("annual_mape"))
        sq = _num(benchmark.get("quarterly_mape"))
        sa = _num(benchmark.get("annual_mape"))
        q_gain = sq - fq if pd.notna(sq) and pd.notna(fq) else pd.NA
        a_gain = sa - fa if pd.notna(sa) and pd.notna(fa) else pd.NA
        win_rate = _row_get(paired_row, "challenger_win_rate")
        recommendation = "Promote" if pd.notna(q_gain) and q_gain > 0 and pd.notna(a_gain) and a_gain > 0 and (pd.isna(pd.to_numeric(win_rate, errors="coerce")) or pd.to_numeric(win_rate, errors="coerce") >= 55) else "Needs Stage 2"
        rows.append(
            {
                "stream": stream,
                "stream_label": finalist.get("stream_label"),
                "finalist_model": finalist.get("model"),
                "finalist_model_short": finalist.get("model_short"),
                "schiff_model": benchmark.get("model"),
                "schiff_model_short": benchmark.get("model_short"),
                "finalist_quarterly_mape": fq,
                "schiff_quarterly_mape": sq,
                "quarterly_gain_pp": q_gain,
                "finalist_annual_mape": fa,
                "schiff_annual_mape": sa,
                "annual_gain_pp": a_gain,
                "paired_common_pairs": _row_get(paired_row, "n_common_pairs"),
                "paired_model_mape": _row_get(paired_row, "challenger_mape"),
                "paired_schiff_mape": _row_get(paired_row, "baseline_mape"),
                "paired_gain_pp": _row_get(paired_row, "mape_improvement_pct_points"),
                "paired_win_rate_pct": win_rate,
                "recommendation": recommendation,
            }
        )
    return pd.DataFrame(rows)


def _scenario_stream_comparison_source(comparison: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        for scenario, model_col, metric, value_col in [
            ("Scenario A", "finalist_model", "Quarterly MAPE", "finalist_quarterly_mape"),
            ("Scenario B", "schiff_model", "Quarterly MAPE", "schiff_quarterly_mape"),
            ("Scenario A", "finalist_model", "Annual MAPE", "finalist_annual_mape"),
            ("Scenario B", "schiff_model", "Annual MAPE", "schiff_annual_mape"),
        ]:
            value = _num(row.get(value_col))
            payload = row.to_dict()
            payload["model"] = row.get(model_col)
            rows.append(
                _base_row(
                    "Scenario Comparison",
                    "scenario_stream_comparison",
                    "1. Stream Comparison: Scenario A vs Scenario B",
                    payload,
                    metric,
                    value,
                    format_percent(value),
                    value_col,
                    source_file,
                    "Scenario A current finalist versus Scenario B Schiff specification benchmark full-sample MAPE.",
                    scenario=scenario,
                    scenario_role=scenario,
                )
            )
    return _standardize(rows)


def _scenario_gain_source(
    comparison: pd.DataFrame,
    page: str,
    chart_id: str,
    chart_title: str,
    source_file: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        for metric, column in [
            ("Full-sample quarterly gain", "quarterly_gain_pp"),
            ("Full-sample annual gain", "annual_gain_pp"),
        ]:
            value = _num(row.get(column))
            rows.append(
                _base_row(
                    page,
                    chart_id,
                    chart_title,
                    row,
                    metric,
                    value,
                    format_pp(value),
                    column,
                    source_file,
                    "Full-sample Schiff specification benchmark MAPE minus current finalist MAPE. This is not paired common-grid gain.",
                    paired_common_pairs=row.get("paired_common_pairs"),
                    paired_model_mape=row.get("paired_model_mape"),
                    paired_schiff_mape=row.get("paired_schiff_mape"),
                    paired_gain_pp=row.get("paired_gain_pp"),
                    paired_win_rate_pct=row.get("paired_win_rate_pct"),
                )
            )
    return _standardize(rows)


def _scenario_decision_source(comparison: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        for metric, column, display_func in [
            ("Full-sample Qtr Gain", "quarterly_gain_pp", format_pp),
            ("Full-sample Annual Gain", "annual_gain_pp", format_pp),
            ("Paired Win Rate", "paired_win_rate_pct", format_percent),
        ]:
            value = _num(row.get(column))
            rows.append(
                _base_row(
                    "Scenario Comparison",
                    "scenario_decision_summary",
                    "4. Decision Summary",
                    row,
                    metric,
                    value,
                    display_func(value),
                    column,
                    source_file,
                    "Decision summary combines full-sample MAPE gains with paired common forecast-pair win rate.",
                    paired_common_pairs=row.get("paired_common_pairs"),
                    paired_model_mape=row.get("paired_model_mape"),
                    paired_schiff_mape=row.get("paired_schiff_mape"),
                    paired_gain_pp=row.get("paired_gain_pp"),
                    paired_win_rate_pct=row.get("paired_win_rate_pct"),
                    recommendation=row.get("recommendation"),
                )
            )
    return _standardize(rows)


def _horizon_source(horizon: pd.DataFrame, qpred: pd.DataFrame, recommended: pd.DataFrame) -> pd.DataFrame:
    columns = ["page", "stream_label", "scenario", "horizon", "mape", "source_column", "source"]
    rows: list[dict[str, Any]] = []
    required_streams = set(recommended.get("stream_label", pd.Series(dtype=str)).dropna().astype(str)) if recommended is not None and not recommended.empty else set()
    existing_streams: set[str] = set()
    if horizon is not None and not horizon.empty:
        existing_streams = set(horizon.get("stream_label", pd.Series(dtype=str)).dropna().astype(str))
        for _, row in horizon.iterrows():
            rows.append(
                {
                    "stream": row.get("stream"),
                    "stream_label": row.get("stream_label"),
                    "model": row.get("model"),
                    "model_short": row.get("model_short"),
                    "scenario": row.get("scenario_role", row.get("scenario")),
                    "horizon": row.get("horizon"),
                    "mape": row.get("mape"),
                    "source_column": row.get("source_column", "mape"),
                    "source": row.get("source_file", "horizon_profiles.parquet"),
                }
            )
    missing_streams = required_streams.difference(existing_streams)
    if missing_streams and qpred is not None and not qpred.empty and {"selected_role", "horizon", "ape", "stream_label"}.issubset(qpred.columns):
        data = qpred.copy()
        data["scenario"] = data["selected_role"].map(lambda value: "Schiff" if "schiff" in str(value).lower() else "Finalist")
        grouped = data.groupby(["stream", "stream_label", "scenario", "horizon"], dropna=False)["ape"].mean().reset_index(name="mape")
        grouped = grouped[grouped["stream_label"].astype(str).isin(missing_streams) & grouped["horizon"].between(1, 12)]
        for _, row in grouped.iterrows():
            rows.append(
                {
                    "stream": row.get("stream"),
                    "stream_label": row.get("stream_label"),
                    "model": pd.NA,
                    "model_short": pd.NA,
                    "scenario": row.get("scenario"),
                    "horizon": row.get("horizon"),
                    "mape": row.get("mape"),
                    "source_column": "ape",
                    "source": "quarterly_predictions_selected.csv grouped mean APE",
                }
            )
    resolved_streams = {str(row.get("stream_label")) for row in rows if pd.notna(row.get("mape"))}
    unresolved_streams = sorted(required_streams.difference(resolved_streams))
    for stream_label in unresolved_streams:
        stream_rows = recommended[recommended["stream_label"].astype(str).eq(stream_label)] if recommended is not None and not recommended.empty else pd.DataFrame()
        template = stream_rows.iloc[0] if not stream_rows.empty else {}
        for scenario in ["Finalist", "Schiff"]:
            rows.append(
                {
                    "stream": _row_get(template, "stream"),
                    "stream_label": stream_label,
                    "model": _row_get(template, "model"),
                    "model_short": _row_get(template, "model_short"),
                    "scenario": scenario,
                    "horizon": pd.NA,
                    "mape": pd.NA,
                    "source_column": "",
                    "source": "Missing: no Parquet horizon fields or selected prediction source available",
                }
            )
    return pd.DataFrame(rows, columns=["stream", "stream_label", "model", "model_short"] + columns[2:])


def _horizon_chart_source(
    horizon_source: pd.DataFrame,
    page: str,
    chart_id: str,
    chart_title: str,
    source_file: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if horizon_source is None or horizon_source.empty:
        return _standardize(rows)
    for _, row in horizon_source.iterrows():
        value = _num(row.get("mape"))
        rows.append(
            _base_row(
                page,
                chart_id,
                chart_title,
                row,
                "Horizon MAPE",
                value,
                format_percent(value),
                str(row.get("source_column", "")),
                source_file,
                str(row.get("source", "Horizon MAPE source")),
                horizon=row.get("horizon"),
                scenario=row.get("scenario"),
                scenario_role=row.get("scenario"),
            )
        )
    return _standardize(rows)


def _schiff_mape_source(comparison: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        for scenario, model_col, metric, column in [
            ("Schiff", "schiff_model", "Schiff quarterly MAPE", "schiff_quarterly_mape"),
            ("Finalist", "finalist_model", "Finalist quarterly MAPE", "finalist_quarterly_mape"),
            ("Schiff", "schiff_model", "Schiff annual MAPE", "schiff_annual_mape"),
            ("Finalist", "finalist_model", "Finalist annual MAPE", "finalist_annual_mape"),
        ]:
            value = _num(row.get(column))
            payload = row.to_dict()
            payload["model"] = row.get(model_col)
            rows.append(
                _base_row(
                    "Schiff Benchmark",
                    "schiff_vs_finalist_mape",
                    "1. Schiff vs Finalist MAPE",
                    payload,
                    metric,
                    value,
                    format_percent(value),
                    column,
                    source_file,
                    "Schiff specification benchmark full-sample MAPE compared with current finalist full-sample MAPE.",
                    scenario=scenario,
                    scenario_role=scenario,
                )
            )
    return _standardize(rows)


def _schiff_summary_source(comparison: pd.DataFrame, source_file: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        for metric, column, formatter in [
            ("Schiff Spec Qtr", "schiff_quarterly_mape", format_percent),
            ("Finalist Qtr", "finalist_quarterly_mape", format_percent),
            ("Full-sample Qtr Gain", "quarterly_gain_pp", format_pp),
            ("Schiff Spec Annual", "schiff_annual_mape", format_percent),
            ("Finalist Annual", "finalist_annual_mape", format_percent),
            ("Full-sample Annual Gain", "annual_gain_pp", format_pp),
            ("Paired Win Rate", "paired_win_rate_pct", format_percent),
        ]:
            value = _num(row.get(column))
            rows.append(
                _base_row(
                    "Schiff Benchmark",
                    "schiff_benchmark_summary",
                    "4. Benchmark Summary",
                    row,
                    metric,
                    value,
                    formatter(value),
                    column,
                    source_file,
                    "Benchmark summary labels full-sample gains separately from paired common forecast-pair win rate.",
                    paired_common_pairs=row.get("paired_common_pairs"),
                    paired_model_mape=row.get("paired_model_mape"),
                    paired_schiff_mape=row.get("paired_schiff_mape"),
                    paired_gain_pp=row.get("paired_gain_pp"),
                    paired_win_rate_pct=row.get("paired_win_rate_pct"),
                    recommendation=row.get("recommendation"),
                )
            )
    return _standardize(rows)


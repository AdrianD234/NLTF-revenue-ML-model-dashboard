"""Governed Revenue Outlook pack builder and loader.

The Revenue Outlook page is intentionally fed by an explicit promoted pack or
an in-session reviewed Forecast Builder comparison. It never scans latest run
folders, and it never promotes smoke-test fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np
import pandas as pd

from .forecast_imports import (
    BACKTEST_SUPPORTED_MAX_HORIZON,
    SCENARIO_ROLE_BASECASE,
    SCENARIO_ROLE_COMPARISON,
    quarter_sort_key,
)

if TYPE_CHECKING:
    from .forecast_runner import ForecastScenarioComparisonResult
else:
    ForecastScenarioComparisonResult = Any


CURRENT_REVENUE_OUTLOOK_DIR = Path("data") / "current_revenue_outlook"
MODEL_INPUT_HISTORY_DIR = Path("data") / "model_input_history"
MODEL_INPUT_HISTORY_FILES = {
    "PED": "ped_inputs.parquet",
    "LIGHT_RUC": "light_ruc_inputs.parquet",
    "HEAVY_RUC": "heavy_ruc_inputs.parquet",
}
STREAM_ORDER = ["PED", "LIGHT_RUC", "HEAVY_RUC"]
STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
}
REVENUE_OUTLOOK_SCHEMA_VERSION = "revenue-outlook-pack-v1"
REVENUE_OUTLOOK_TITLE = "Revenue Outlook"

ACTIVITY_UNITS = {
    "PED": "VKT per capita",
    "LIGHT_RUC": "net km",
    "HEAVY_RUC": "net km",
}
REVENUE_UNITS = "nominal NZD"
RATE_UNITS = {
    "PED": "cents/litre",
    "LIGHT_RUC": "NZD/1,000km",
    "HEAVY_RUC": "NZD/1,000km",
}
RUC_HISTORY_COLUMNS = {
    "LIGHT_RUC": ("light_ruc_revenue_nzd", "light_ruc_price_nominal_nzd_per_1000km"),
    "HEAVY_RUC": ("heavy_ruc_revenue_nzd", "heavy_ruc_price_nominal_nzd_per_1000km"),
}
FUTURE_RATE_COLUMNS = {
    "PED": ("ped_base_rate_cents_per_litre", "ped_rate_source", "ped_rate_cpi_basis"),
    "LIGHT_RUC": ("light_ruc_nominal_rate_nzd_per_1000km", "light_ruc_rate_source", "light_ruc_rate_cpi_basis"),
    "HEAVY_RUC": ("heavy_ruc_nominal_rate_nzd_per_1000km", "heavy_ruc_rate_source", "heavy_ruc_rate_cpi_basis"),
}

REVENUE_EQUATIONS = {
    "LIGHT_RUC": "Light RUC revenue = net km / 1,000 * nominal effective average Light RUC rate.",
    "HEAVY_RUC": "Heavy RUC revenue = net km / 1,000 * nominal effective average Heavy RUC rate.",
    "PED": (
        "PED revenue = litres * nominal PED base rate / 100. Litres must come from a source-backed "
        "PED litres bridge, not from the VKT/capita activity model alone."
    ),
}


@dataclass
class RevenueOutlookPack:
    output_dir: Path
    manifest: dict[str, Any]
    future_revenue_forecasts: pd.DataFrame
    revenue_bridge_components: pd.DataFrame
    revenue_chart_rows: pd.DataFrame


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def revenue_outlook_signature(pack_dir: Path | str | None = None, repo_root: Path | str | None = None) -> tuple[tuple[str, int, int], ...]:
    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    base = Path(pack_dir) if pack_dir is not None else root / CURRENT_REVENUE_OUTLOOK_DIR
    paths = [
        base / "manifest.json",
        base / "future_revenue_forecasts.parquet",
        base / "revenue_bridge_components.parquet",
        base / "revenue_chart_rows.parquet",
    ]
    signature: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            signature.append((path.as_posix(), 0, 0))
            continue
        signature.append((path.as_posix(), int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(signature)


def load_revenue_outlook_pack(
    pack_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> RevenueOutlookPack | None:
    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    base = Path(pack_dir) if pack_dir is not None else root / CURRENT_REVENUE_OUTLOOK_DIR
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return RevenueOutlookPack(
        output_dir=base,
        manifest=manifest,
        future_revenue_forecasts=_read_optional_parquet(base / "future_revenue_forecasts.parquet"),
        revenue_bridge_components=_read_optional_parquet(base / "revenue_bridge_components.parquet"),
        revenue_chart_rows=_read_optional_parquet(base / "revenue_chart_rows.parquet"),
    )


def validate_promotable_comparison(comparison: ForecastScenarioComparisonResult) -> list[str]:
    errors: list[str] = []
    manifest = getattr(comparison, "manifest", {}) or {}
    role_validation = manifest.get("scenario_role_validation", {})
    if role_validation.get("status") != "passed":
        errors.append("Scenario role validation must be passed before Revenue Outlook promotion.")
    scenarios = manifest.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        errors.append("Comparison manifest must contain scenario records.")
    for scenario in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(scenario, dict):
            continue
        if scenario.get("is_test_fixture"):
            errors.append(f"Test fixture scenario cannot be promoted: {scenario.get('scenario_name')}.")
        role = scenario.get("scenario_role")
        if role not in {SCENARIO_ROLE_BASECASE, SCENARIO_ROLE_COMPARISON}:
            errors.append(f"Scenario has no resolved promotion role: {scenario.get('scenario_name')}.")
        if not scenario.get("workbook_sha256"):
            errors.append(f"Scenario is missing workbook SHA256: {scenario.get('scenario_name')}.")
    future = getattr(comparison, "future_forecasts", pd.DataFrame())
    if future is None or future.empty:
        errors.append("Comparison has no future forecast rows to promote.")
    elif "forecast_available" in future.columns and not future["forecast_available"].fillna(False).astype(bool).any():
        errors.append("Comparison has no numeric activity forecasts; Revenue Outlook would contain only gaps.")
    return errors


def promote_revenue_outlook_pack(
    comparison: ForecastScenarioComparisonResult,
    *,
    repo_root: Path | str | None = None,
    output_dir: Path | str | None = None,
    promoted_by: str = "streamlit_forecast_builder",
) -> RevenueOutlookPack:
    errors = validate_promotable_comparison(comparison)
    if errors:
        raise ValueError("Revenue Outlook promotion failed: " + " ".join(errors))
    return build_revenue_outlook_pack(
        comparison,
        repo_root=repo_root,
        output_dir=output_dir,
        pack_status="explicitly_promoted_current_outlook",
        promoted_by=promoted_by,
    )


def build_revenue_outlook_pack(
    comparison: ForecastScenarioComparisonResult,
    *,
    repo_root: Path | str | None = None,
    output_dir: Path | str | None = None,
    pack_status: str = "in_session_reviewed_outlook",
    promoted_by: str = "streamlit_session",
) -> RevenueOutlookPack:
    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    base = Path(output_dir) if output_dir is not None else root / CURRENT_REVENUE_OUTLOOK_DIR
    base.mkdir(parents=True, exist_ok=True)

    future = comparison.future_forecasts.copy()
    assumptions = _comparison_assumptions(comparison)
    historical_activity = _historical_activity_rows(root)
    historical_revenue, historical_components = _historical_revenue_rows(root)
    future_revenue = _future_revenue_rows(future, assumptions)
    future_activity = _future_activity_chart_rows(future)
    bridge_components = pd.concat(
        [historical_components, _future_bridge_component_rows(future, assumptions, future_revenue)],
        ignore_index=True,
        sort=False,
    )
    chart_rows = pd.concat(
        [historical_activity, future_activity, historical_revenue, _future_revenue_chart_rows(future_revenue)],
        ignore_index=True,
        sort=False,
    )
    chart_rows = _add_june_year_rows(chart_rows)
    chart_rows = chart_rows.sort_values(
        ["metric_type", "stream", "time_grain", "period_key", "scenario_name"],
        kind="stable",
    ).drop(columns=["period_key"], errors="ignore")

    manifest = _manifest(
        comparison,
        root,
        base,
        future_revenue,
        chart_rows,
        bridge_components,
        pack_status=pack_status,
        promoted_by=promoted_by,
    )
    _write_pack_files(base, manifest, future_revenue, bridge_components, chart_rows)
    return RevenueOutlookPack(base, manifest, future_revenue, bridge_components, chart_rows)


def _read_optional_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _comparison_assumptions(comparison: ForecastScenarioComparisonResult) -> pd.DataFrame:
    frames = [
        result.assumptions
        for result in getattr(comparison, "scenario_results", [])
        if isinstance(getattr(result, "assumptions", None), pd.DataFrame) and not result.assumptions.empty
    ]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _historical_activity_rows(repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stream in STREAM_ORDER:
        path = repo_root / MODEL_INPUT_HISTORY_DIR / MODEL_INPUT_HISTORY_FILES[stream]
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        if {"period", "target"}.difference(frame.columns):
            continue
        data = frame[["period", "target"]].copy()
        data["value"] = pd.to_numeric(data["target"], errors="coerce")
        data = data[data["value"].gt(0)].copy()
        for _, row in data.iterrows():
            period = str(row["period"]).upper()
            rows.append(
                _chart_row(
                    metric_type="activity",
                    row_type="historical_actual",
                    stream=stream,
                    scenario_name="historical_actual",
                    period=period,
                    value=float(row["value"]),
                    value_unit=ACTIVITY_UNITS[stream],
                    source=_repo_relative(repo_root, path),
                    bridge_status="historical_activity_available",
                    bridge_method="source_model_input_history",
                )
            )
    return pd.DataFrame(rows)


def _historical_revenue_rows(repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    chart_rows: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    for stream in ("LIGHT_RUC", "HEAVY_RUC"):
        path = repo_root / MODEL_INPUT_HISTORY_DIR / MODEL_INPUT_HISTORY_FILES[stream]
        revenue_col, nominal_price_col = RUC_HISTORY_COLUMNS[stream]
        if not path.exists():
            components.append(_gap_component(stream, "historical_revenue_source_missing", f"Missing {path.name}."))
            continue
        frame = pd.read_parquet(path)
        required = {"period", "target", revenue_col}
        if required.difference(frame.columns):
            components.append(_gap_component(stream, "historical_revenue_column_missing", f"Missing columns: {sorted(required.difference(frame.columns))}."))
            continue
        data = frame[["period", "target", revenue_col, nominal_price_col if nominal_price_col in frame.columns else revenue_col]].copy()
        data["activity_value"] = pd.to_numeric(data["target"], errors="coerce")
        data["revenue_nzd"] = pd.to_numeric(data[revenue_col], errors="coerce")
        data = data[data["activity_value"].gt(0) & data["revenue_nzd"].ge(0)].copy()
        if data.empty:
            components.append(_gap_component(stream, "historical_revenue_rows_missing", "No positive net-km rows with non-negative revenue."))
            continue
        data["effective_rate_nzd_per_1000km"] = data["revenue_nzd"] * 1000.0 / data["activity_value"]
        data["reconciled_revenue_nzd"] = data["activity_value"] / 1000.0 * data["effective_rate_nzd_per_1000km"]
        data["reconciliation_delta_nzd"] = data["reconciled_revenue_nzd"] - data["revenue_nzd"]
        max_abs_delta = float(data["reconciliation_delta_nzd"].abs().max())
        components.append(
            {
                "stream": stream,
                "stream_label": STREAM_LABELS[stream],
                "component_type": "historical_revenue_reconciliation",
                "period": "all_history",
                "activity_value": pd.NA,
                "activity_unit": ACTIVITY_UNITS[stream],
                "rate_value": pd.NA,
                "rate_unit": RATE_UNITS[stream],
                "revenue_nzd": pd.NA,
                "bridge_status": "available",
                "bridge_method": "historical_effective_rate_reconciliation",
                "equation": REVENUE_EQUATIONS[stream],
                "source": _repo_relative(repo_root, path),
                "reconciliation_max_abs_delta_nzd": max_abs_delta,
                "notes": "Historical source net revenue reconciles by deriving effective average rate as revenue * 1,000 / net km.",
            }
        )
        for _, row in data.iterrows():
            period = str(row["period"]).upper()
            chart_rows.append(
                _chart_row(
                    metric_type="revenue",
                    row_type="historical_actual",
                    stream=stream,
                    scenario_name="historical_actual",
                    period=period,
                    value=float(row["revenue_nzd"]),
                    value_unit=REVENUE_UNITS,
                    source=_repo_relative(repo_root, path),
                    bridge_status="available",
                    bridge_method="historical_effective_rate_reconciliation",
                    rate_value=float(row["effective_rate_nzd_per_1000km"]),
                    rate_unit=RATE_UNITS[stream],
                )
            )
    components.append(
        _gap_component(
            "PED",
            "ped_revenue_history_missing",
            "Committed model_input_history has PED VKT/capita and total VKT, but no PED litres, accrual PED revenue or base-rate history from 2008Q3.",
        )
    )
    return pd.DataFrame(chart_rows), pd.DataFrame(components)


def _future_activity_chart_rows(future: pd.DataFrame) -> pd.DataFrame:
    if future is None or future.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in future.iterrows():
        stream = str(row.get("stream", ""))
        if stream not in ACTIVITY_UNITS:
            continue
        period = str(row.get("target_period", row.get("period", ""))).upper()
        value = pd.to_numeric(row.get("forecast"), errors="coerce")
        rows.append(
            _chart_row(
                metric_type="activity",
                row_type="future_forecast",
                stream=stream,
                scenario_name=str(row.get("scenario_name", "scenario")),
                scenario_role=row.get("scenario_role"),
                period=period,
                horizon=row.get("horizon"),
                value=float(value) if pd.notna(value) else pd.NA,
                value_unit=ACTIVITY_UNITS[stream],
                source="forecast_scenario_comparison.parquet",
                bridge_status=row.get("availability_status", "forecast_available" if pd.notna(value) else "governed_gap"),
                bridge_method="fixed_finalist_activity_forecast",
                forecast_available=bool(row.get("forecast_available")) if pd.notna(row.get("forecast_available")) else False,
                gap_code=row.get("gap_code"),
                gap_reason=row.get("gap_reason"),
            )
        )
    return pd.DataFrame(rows)


def _future_revenue_rows(future: pd.DataFrame, assumptions: pd.DataFrame) -> pd.DataFrame:
    if future is None or future.empty:
        return pd.DataFrame()
    assumption_lookup = _assumption_lookup(assumptions)
    rows: list[dict[str, Any]] = []
    for _, row in future.iterrows():
        stream = str(row.get("stream", ""))
        if stream not in STREAM_ORDER:
            continue
        scenario = str(row.get("scenario_name", "scenario"))
        period = str(row.get("target_period", row.get("period", ""))).upper()
        activity = pd.to_numeric(row.get("forecast"), errors="coerce")
        forecast_available = bool(row.get("forecast_available")) if pd.notna(row.get("forecast_available")) else False
        assumption = assumption_lookup.get((scenario, stream, period), {})
        rate_col, source_col, cpi_col = FUTURE_RATE_COLUMNS[stream]
        rate = pd.to_numeric(assumption.get(rate_col), errors="coerce")
        source = _clean_text(assumption.get(source_col))
        cpi_basis = _clean_text(assumption.get(cpi_col))
        status = "available"
        gap_code = ""
        gap_reason = ""
        revenue = pd.NA
        activity_value = float(activity) if pd.notna(activity) else pd.NA
        if not forecast_available or pd.isna(activity):
            status = "activity_forecast_gap"
            gap_code = str(row.get("gap_code") or "activity_forecast_unavailable")
            gap_reason = str(row.get("gap_reason") or "Activity forecast is unavailable, so revenue is unavailable.")
        elif stream == "PED":
            status = "ped_bridge_source_history_missing"
            gap_code = "ped_litres_revenue_bridge_source_missing"
            gap_reason = (
                "PED VKT/capita forecast is available, but committed sources do not contain the PED litres, "
                "accrual PED revenue and nominal base-rate history needed to estimate the litres bridge."
            )
        elif pd.isna(rate) or float(rate) <= 0:
            status = "nominal_rate_missing"
            gap_code = "future_nominal_rate_missing"
            gap_reason = f"Future {STREAM_LABELS[stream]} revenue requires {rate_col} in the reviewed workbook."
        else:
            revenue = float(activity) / 1000.0 * float(rate)
        rows.append(
            {
                "scenario_name": scenario,
                "scenario_role": row.get("scenario_role"),
                "stream": stream,
                "stream_label": STREAM_LABELS[stream],
                "model": row.get("model"),
                "target_period": period,
                "horizon": row.get("horizon"),
                "horizon_support_status": row.get("horizon_support_status"),
                "horizon_support_label": row.get("horizon_support_label"),
                "backtest_supported_max_horizon": BACKTEST_SUPPORTED_MAX_HORIZON,
                "activity_forecast": activity_value,
                "activity_unit": ACTIVITY_UNITS[stream],
                "rate_value": float(rate) if pd.notna(rate) else pd.NA,
                "rate_unit": RATE_UNITS[stream],
                "rate_source": source,
                "rate_cpi_basis": cpi_basis,
                "revenue_forecast_nzd": revenue,
                "revenue_unit": REVENUE_UNITS,
                "forecast_available": forecast_available and pd.notna(revenue),
                "activity_forecast_available": forecast_available,
                "bridge_status": status,
                "bridge_method": _future_bridge_method(stream),
                "equation": REVENUE_EQUATIONS[stream],
                "gap_code": gap_code,
                "gap_reason": gap_reason,
                "source": "forecast_scenario_comparison.parquet; forecast_assumptions.parquet",
            }
        )
    return pd.DataFrame(rows)


def _future_bridge_component_rows(future: pd.DataFrame, assumptions: pd.DataFrame, future_revenue: pd.DataFrame) -> pd.DataFrame:
    if future_revenue is None or future_revenue.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in future_revenue.iterrows():
        rows.append(
            {
                "scenario_name": row.get("scenario_name"),
                "scenario_role": row.get("scenario_role"),
                "stream": row.get("stream"),
                "stream_label": row.get("stream_label"),
                "component_type": "future_revenue_bridge",
                "period": row.get("target_period"),
                "horizon": row.get("horizon"),
                "activity_value": row.get("activity_forecast"),
                "activity_unit": row.get("activity_unit"),
                "rate_value": row.get("rate_value"),
                "rate_unit": row.get("rate_unit"),
                "rate_source": row.get("rate_source"),
                "rate_cpi_basis": row.get("rate_cpi_basis"),
                "revenue_nzd": row.get("revenue_forecast_nzd"),
                "bridge_status": row.get("bridge_status"),
                "bridge_method": row.get("bridge_method"),
                "equation": row.get("equation"),
                "source": row.get("source"),
                "gap_code": row.get("gap_code"),
                "gap_reason": row.get("gap_reason"),
            }
        )
    return pd.DataFrame(rows)


def _future_revenue_chart_rows(future_revenue: pd.DataFrame) -> pd.DataFrame:
    if future_revenue is None or future_revenue.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in future_revenue.iterrows():
        value = pd.to_numeric(row.get("revenue_forecast_nzd"), errors="coerce")
        rows.append(
            _chart_row(
                metric_type="revenue",
                row_type="future_forecast",
                stream=str(row.get("stream", "")),
                scenario_name=str(row.get("scenario_name", "scenario")),
                scenario_role=row.get("scenario_role"),
                period=str(row.get("target_period", "")).upper(),
                horizon=row.get("horizon"),
                value=float(value) if pd.notna(value) else pd.NA,
                value_unit=REVENUE_UNITS,
                source=str(row.get("source", "")),
                bridge_status=row.get("bridge_status"),
                bridge_method=row.get("bridge_method"),
                forecast_available=bool(row.get("forecast_available")) if pd.notna(row.get("forecast_available")) else False,
                rate_value=row.get("rate_value"),
                rate_unit=row.get("rate_unit"),
                gap_code=row.get("gap_code"),
                gap_reason=row.get("gap_reason"),
            )
        )
    return pd.DataFrame(rows)


def _assumption_lookup(assumptions: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    if assumptions is None or assumptions.empty:
        return {}
    data = assumptions.copy()
    required = {"scenario_name", "stream", "period"}
    if required.difference(data.columns):
        return {}
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for _, row in data.iterrows():
        key = (str(row.get("scenario_name", "scenario")), str(row.get("stream", "")), str(row.get("period", "")).upper())
        lookup[key] = row.to_dict()
    return lookup


def _chart_row(
    *,
    metric_type: str,
    row_type: str,
    stream: str,
    scenario_name: str,
    period: str,
    value: Any,
    value_unit: str,
    source: str,
    bridge_status: Any,
    bridge_method: str,
    scenario_role: Any = None,
    horizon: Any = pd.NA,
    forecast_available: Any = pd.NA,
    rate_value: Any = pd.NA,
    rate_unit: Any = pd.NA,
    gap_code: Any = "",
    gap_reason: Any = "",
) -> dict[str, Any]:
    return {
        "metric_type": metric_type,
        "time_grain": "quarterly",
        "row_type": row_type,
        "scenario_name": scenario_name,
        "scenario_role": scenario_role,
        "stream": stream,
        "stream_label": STREAM_LABELS.get(stream, stream),
        "period": period,
        "target_period": period,
        "june_year": _june_year(period),
        "horizon": horizon,
        "horizon_scope": _horizon_scope(horizon),
        "value": value,
        "value_unit": value_unit,
        "forecast_available": forecast_available,
        "bridge_status": bridge_status,
        "bridge_method": bridge_method,
        "rate_value": rate_value,
        "rate_unit": rate_unit,
        "gap_code": gap_code,
        "gap_reason": gap_reason,
        "source": source,
        "period_key": quarter_sort_key(period),
    }


def _add_june_year_rows(chart_rows: pd.DataFrame) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame() if chart_rows is None else chart_rows
    rows = [chart_rows]
    source = chart_rows.copy()
    source["value_numeric"] = pd.to_numeric(source["value"], errors="coerce")
    source = source[source["value_numeric"].notna()].copy()
    if source.empty:
        return chart_rows
    group_cols = ["metric_type", "row_type", "scenario_name", "scenario_role", "stream", "stream_label", "june_year"]
    annual_rows: list[dict[str, Any]] = []
    for keys, group in source.groupby(group_cols, dropna=False):
        record = dict(zip(group_cols, keys, strict=False))
        stream = str(record["stream"])
        metric_type = str(record["metric_type"])
        if metric_type == "activity" and stream == "PED":
            value = float(group["value_numeric"].mean())
            aggregation_method = "mean_quarterly_vkt_per_capita"
        else:
            value = float(group["value_numeric"].sum())
            aggregation_method = "sum_quarters"
        june_year = int(record["june_year"])
        annual_rows.append(
            {
                **record,
                "time_grain": "june_year",
                "period": f"FY{june_year}",
                "target_period": f"FY{june_year}",
                "horizon": pd.NA,
                "horizon_scope": "june_year_aggregate",
                "value": value,
                "value_unit": first_non_null(group["value_unit"]),
                "forecast_available": bool(group["forecast_available"].fillna(True).astype(bool).all()),
                "bridge_status": first_non_null(group["bridge_status"]),
                "bridge_method": first_non_null(group["bridge_method"]),
                "rate_value": pd.NA,
                "rate_unit": first_non_null(group["rate_unit"]),
                "gap_code": first_non_null(group["gap_code"]),
                "gap_reason": first_non_null(group["gap_reason"]),
                "source": first_non_null(group["source"]),
                "quarter_count": int(len(group)),
                "aggregation_method": aggregation_method,
                "period_key": june_year * 4 + 2,
            }
        )
    if annual_rows:
        rows.append(pd.DataFrame(annual_rows))
    return pd.concat(rows, ignore_index=True, sort=False)


def _manifest(
    comparison: ForecastScenarioComparisonResult,
    repo_root: Path,
    output_dir: Path,
    future_revenue: pd.DataFrame,
    chart_rows: pd.DataFrame,
    bridge_components: pd.DataFrame,
    *,
    pack_status: str,
    promoted_by: str,
) -> dict[str, Any]:
    scenarios = comparison.manifest.get("scenarios", [])
    model_ids = {}
    future = comparison.future_forecasts
    if future is not None and not future.empty:
        for stream, group in future.groupby("stream", dropna=False):
            model_ids[str(stream)] = sorted(group.get("model", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    bridge_status = {}
    if future_revenue is not None and not future_revenue.empty:
        for stream, group in future_revenue.groupby("stream", dropna=False):
            bridge_status[str(stream)] = sorted(group["bridge_status"].dropna().astype(str).unique().tolist())
    return {
        "schema_version": REVENUE_OUTLOOK_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "promotion_time": datetime.now(timezone.utc).isoformat(),
        "pack_status": pack_status,
        "promoted_by": promoted_by,
        "source_policy": "explicit_promoted_pack_or_in_session_reviewed_result_only; no latest-folder scan; no test-fixture publication",
        "source_comparison": {
            "comparison_id": comparison.manifest.get("comparison_id"),
            "scenario_role_validation": comparison.manifest.get("scenario_role_validation"),
            "scenarios": scenarios,
            "output_dir": _repo_relative(repo_root, comparison.output_dir),
        },
        "scenario_roles": [
            {
                "scenario_name": scenario.get("scenario_name"),
                "scenario_role": scenario.get("scenario_role"),
                "workbook_filename": scenario.get("workbook_filename"),
                "workbook_sha256": scenario.get("workbook_sha256"),
            }
            for scenario in scenarios
            if isinstance(scenario, dict)
        ],
        "model_ids": model_ids,
        "units": {
            "activity": ACTIVITY_UNITS,
            "revenue": REVENUE_UNITS,
            "rates": RATE_UNITS,
        },
        "equations": REVENUE_EQUATIONS,
        "rate_provenance": {
            "historical_light_heavy": "data/model_input_history source net revenue; effective average rate = revenue * 1,000 / net km",
            "future_light_heavy": "reviewed workbook nominal effective average RUC rate columns",
            "future_ped": "reviewed workbook PED base-rate column plus source-backed PED litres bridge; currently a governed gap when source litres/history are missing",
        },
        "bridge_status_by_stream": bridge_status,
        "row_counts": {
            "future_revenue_forecasts": int(len(future_revenue)),
            "revenue_bridge_components": int(len(bridge_components)),
            "revenue_chart_rows": int(len(chart_rows)),
        },
        "source_hashes": _source_hashes(repo_root, scenarios),
        "output_files": [
            "future_revenue_forecasts.parquet",
            "future_revenue_forecasts.csv",
            "revenue_bridge_components.parquet",
            "revenue_bridge_components.csv",
            "revenue_chart_rows.parquet",
            "revenue_chart_rows.csv",
            "manifest.json",
            "manifest.md",
        ],
        "repo_relative_output_dir": _repo_relative(repo_root, output_dir),
    }


def _write_pack_files(
    output_dir: Path,
    manifest: dict[str, Any],
    future_revenue: pd.DataFrame,
    bridge_components: pd.DataFrame,
    chart_rows: pd.DataFrame,
) -> None:
    future_revenue.to_parquet(output_dir / "future_revenue_forecasts.parquet", index=False)
    bridge_components.to_parquet(output_dir / "revenue_bridge_components.parquet", index=False)
    chart_rows.to_parquet(output_dir / "revenue_chart_rows.parquet", index=False)
    future_revenue.to_csv(output_dir / "future_revenue_forecasts.csv", index=False)
    bridge_components.to_csv(output_dir / "revenue_bridge_components.csv", index=False)
    chart_rows.to_csv(output_dir / "revenue_chart_rows.csv", index=False)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    (output_dir / "manifest.md").write_text(_manifest_markdown(manifest), encoding="utf-8")


def _manifest_markdown(manifest: dict[str, Any]) -> str:
    scenarios = manifest.get("scenario_roles", [])
    rows = [
        "# Revenue Outlook Manifest",
        "",
        f"- Schema: `{manifest.get('schema_version')}`",
        f"- Status: `{manifest.get('pack_status')}`",
        f"- Promoted: `{manifest.get('promotion_time')}`",
        f"- Output: `{manifest.get('repo_relative_output_dir')}`",
        "",
        "## Equations",
    ]
    for stream, equation in REVENUE_EQUATIONS.items():
        rows.append(f"- {STREAM_LABELS[stream]}: {equation}")
    rows.extend(["", "## Scenario Roles"])
    for scenario in scenarios if isinstance(scenarios, list) else []:
        rows.append(
            f"- `{scenario.get('scenario_name')}`: `{scenario.get('scenario_role')}`, "
            f"workbook `{scenario.get('workbook_filename')}`, SHA256 `{scenario.get('workbook_sha256')}`"
        )
    rows.extend(["", "## Bridge Status"])
    for stream, statuses in (manifest.get("bridge_status_by_stream") or {}).items():
        rows.append(f"- {STREAM_LABELS.get(stream, stream)}: {', '.join(statuses)}")
    return "\n".join(rows) + "\n"


def _source_hashes(repo_root: Path, scenarios: Any) -> dict[str, Any]:
    hashes: dict[str, Any] = {"model_input_history": {}}
    for stream, filename in MODEL_INPUT_HISTORY_FILES.items():
        path = repo_root / MODEL_INPUT_HISTORY_DIR / filename
        if path.exists():
            hashes["model_input_history"][stream] = {
                "repo_relative_path": _repo_relative(repo_root, path),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
    hashes["workbooks"] = [
        {
            "scenario_name": scenario.get("scenario_name"),
            "scenario_role": scenario.get("scenario_role"),
            "workbook_filename": scenario.get("workbook_filename"),
            "workbook_sha256": scenario.get("workbook_sha256"),
        }
        for scenario in scenarios
        if isinstance(scenario, dict)
    ]
    return hashes


def _gap_component(stream: str, code: str, reason: str) -> dict[str, Any]:
    return {
        "stream": stream,
        "stream_label": STREAM_LABELS.get(stream, stream),
        "component_type": "governed_gap",
        "period": pd.NA,
        "activity_value": pd.NA,
        "activity_unit": ACTIVITY_UNITS.get(stream),
        "rate_value": pd.NA,
        "rate_unit": RATE_UNITS.get(stream),
        "revenue_nzd": pd.NA,
        "bridge_status": code,
        "bridge_method": "governed_gap",
        "equation": REVENUE_EQUATIONS.get(stream, ""),
        "source": "",
        "gap_code": code,
        "gap_reason": reason,
    }


def _future_bridge_method(stream: str) -> str:
    if stream in {"LIGHT_RUC", "HEAVY_RUC"}:
        return "activity_forecast_times_reviewed_nominal_effective_rate"
    return "ped_litres_bridge_required"


def _horizon_scope(horizon: Any) -> str:
    try:
        value = int(float(horizon))
    except Exception:
        return ""
    return "H1-H12" if 1 <= value <= BACKTEST_SUPPORTED_MAX_HORIZON else "H13+"


def _june_year(period: Any) -> int:
    text = str(period).strip().upper()
    if "Q" not in text:
        return int(text.replace("FY", "")) if text.replace("FY", "").isdigit() else 0
    year_text, quarter_text = text.split("Q", 1)
    year = int(year_text)
    quarter = int(quarter_text)
    return year if quarter <= 2 else year + 1


def first_non_null(values: Any) -> Any:
    try:
        iterator = values.dropna().tolist()
    except Exception:
        iterator = [values]
    for value in iterator:
        if pd.notna(value) and str(value) != "":
            return value
    return ""


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _repo_relative(root: Path, path: Path | str) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return Path(path).as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

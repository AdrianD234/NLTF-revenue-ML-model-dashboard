"""Governed Revenue Outlook pack builder and loader.

The Revenue Outlook page is intentionally fed by an explicit promoted pack or
an in-session reviewed Forecast Builder comparison. It never scans latest run
folders, and it never promotes smoke-test fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, TYPE_CHECKING

_RUNTIME_PYARROW24 = Path(__file__).resolve().parents[1] / ".runtime_pyarrow24"
if _RUNTIME_PYARROW24.exists() and str(_RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_PYARROW24))

import numpy as np
import pandas as pd

from .forecast_imports import (
    BACKTEST_SUPPORTED_MAX_HORIZON,
    SCENARIO_ROLE_BASECASE,
    SCENARIO_ROLE_COMPARISON,
    quarter_sort_key,
)
from .mbu26_source_spine import (
    MBU26_RELEASE_ROUND,
    MBU26_SCHEMA_VERSION,
    MBU26_SOURCE_PACK_DIR,
    current_forecast_annual_from_mbu26,
    load_mbu26_annual_spine,
    revenue_formula_residual_frame,
    revenue_line_reconciliation_frame,
)
from .revenue_source_pack import (
    CURRENT_FINALIST_COMPOSITE_MODEL_ID,
    CURRENT_FINALIST_MODEL_IDS,
    REVENUE_FIRST_FORECAST_QUARTER,
    REVENUE_LAST_COMPLETE_ACTUAL_FY,
    REVENUE_MODEL_TRAINING_CUTOFF,
    REVENUE_SOURCE_PACK_DIR,
    SOURCE_SERIES_ALIASES,
    load_revenue_source_pack,
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
RUNTIME_REVENUE_OUTLOOK_FILES = (
    "future_revenue_forecasts.parquet",
    "revenue_bridge_components.parquet",
    "revenue_chart_rows.parquet",
    "runtime_trace_audit.parquet",
    "revenue_line_reconciliation.parquet",
    "revenue_formula_residuals.parquet",
    "trace_source_contract.parquet",
    "series_trace_contract.parquet",
    "path_trace_status.parquet",
)
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
CANONICAL_JOIN_KEY_COLUMNS = [
    "canonical_stream_key",
    "canonical_period_key",
    "canonical_scenario_key",
    "canonical_join_key",
]
CANONICAL_JOIN_KEY_CONTRACT = {
    "columns": CANONICAL_JOIN_KEY_COLUMNS,
    "source_columns": {
        "canonical_stream_key": ["stream"],
        "canonical_period_key": ["target_period", "period"],
        "canonical_scenario_key": ["scenario_name", "row_type"],
    },
    "rule": "Forecast Builder volume packs join to Revenue Outlook rows by canonical stream, period and scenario keys; historical rows use historical_actual.",
}
PROMOTED_SCENARIO_MANIFEST_FIELDS = (
    "scenario_name",
    "scenario_role",
    "scenario_role_source",
    "scenario_display_name",
    "is_test_fixture",
    "run_id",
    "workbook_filename",
    "workbook_sha256",
    "forecast_horizon_quarters",
    "forecast_start_period",
    "forecast_end_period",
    "forecast_status",
)
SOURCE_COMPARISON_OUTPUT_DIR_POLICY = (
    "Source run output folders are not published in the promoted runtime manifest; "
    "scenario roles, workbook hashes, and governed output hashes are retained."
)
CURRENT_RUNTIME_POLICY = (
    "Revenue Outlook runtime rows are materialized from repo-local source actuals, "
    "current finalist forecasts and the MBU26 official comparator. Source-pack "
    "tables are retained as audit lineage and are not a second Streamlit chart engine."
)
REVENUE_FIRST_FORECAST_FY = 2026


@dataclass
class RevenueOutlookPack:
    output_dir: Path
    manifest: dict[str, Any]
    future_revenue_forecasts: pd.DataFrame
    revenue_bridge_components: pd.DataFrame
    revenue_chart_rows: pd.DataFrame
    revenue_line_reconciliation: pd.DataFrame = field(default_factory=pd.DataFrame)
    revenue_formula_residuals: pd.DataFrame = field(default_factory=pd.DataFrame)


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
        base / "revenue_line_reconciliation.parquet",
        base / "revenue_formula_residuals.parquet",
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
    hash_errors = _validate_output_hashes(base, manifest)
    if hash_errors:
        raise ValueError("Revenue Outlook promoted pack failed hash validation: " + " ".join(hash_errors))
    return RevenueOutlookPack(
        output_dir=base,
        manifest=manifest,
        future_revenue_forecasts=_read_optional_parquet(base / "future_revenue_forecasts.parquet"),
        revenue_bridge_components=_read_optional_parquet(base / "revenue_bridge_components.parquet"),
        revenue_chart_rows=_read_optional_parquet(base / "revenue_chart_rows.parquet"),
        revenue_line_reconciliation=_read_optional_parquet(base / "revenue_line_reconciliation.parquet"),
        revenue_formula_residuals=_read_optional_parquet(base / "revenue_formula_residuals.parquet"),
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


DISPLAY_SERIES_ORDER = [
    "ped_vkt_per_capita",
    "light_ruc_net_km",
    "heavy_ruc_net_km",
    "gross_ped_revenue",
    "light_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "gross_fed_revenue",
    "net_fed_revenue",
    "total_ruc_net_revenue",
    "net_mvr_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
]


def build_current_revenue_outlook_runtime_pack(
    *,
    repo_root: Path | str | None = None,
    output_dir: Path | str | None = None,
    promoted_by: str = "repo_source_runtime_rebuild",
) -> RevenueOutlookPack:
    """Materialize the committed Revenue Outlook pack from repo-local sources.

    This is the deployment/runtime path. It uses the repo-local MBU26 annual
    source spine plus current-finalist quarterly outputs already promoted into
    ``data/current_revenue_outlook``. The offline workbook is never loaded by
    Streamlit.
    """

    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    base = Path(output_dir) if output_dir is not None else root / CURRENT_REVENUE_OUTLOOK_DIR
    base.mkdir(parents=True, exist_ok=True)

    existing_manifest = _read_existing_manifest(base)
    mbu26_pack = load_mbu26_annual_spine(repo_root=root)
    if mbu26_pack is None:
        raise ValueError(
            "Cannot rebuild current Revenue Outlook runtime pack: "
            f"{MBU26_SOURCE_PACK_DIR.as_posix()} is missing."
        )
    existing_chart_rows = _read_optional_csv(base / "revenue_chart_rows.csv")
    current = current_forecast_annual_from_mbu26(
        current_outlook_chart_rows=existing_chart_rows,
        mbu26_official_annual=mbu26_pack.official_annual,
    )
    if current.empty:
        raise ValueError("Cannot rebuild current Revenue Outlook runtime pack: current finalist annual rows are missing.")
    line_reconciliation = revenue_line_reconciliation_frame(
        mbu26_official_annual=mbu26_pack.official_annual,
        current_forecast_annual=current,
    )
    formula_residuals = revenue_formula_residual_frame(line_reconciliation)

    series_meta = _runtime_series_metadata(mbu26_pack.series_trace_contract)
    quarterly_inputs = _runtime_quarterly_activity_inputs(existing_chart_rows, series_meta)
    actual_rows = _runtime_mbu26_actual_rows(mbu26_pack.official_annual, series_meta)
    current_rows = _runtime_current_rows(current, series_meta)
    mbu26_official_rows = _runtime_mbu26_official_rows(mbu26_pack.official_annual, series_meta)
    chart_rows = pd.concat(
        [quarterly_inputs, actual_rows, current_rows, mbu26_official_rows],
        ignore_index=True,
        sort=False,
    )
    if chart_rows.empty:
        raise ValueError("Cannot rebuild current Revenue Outlook runtime pack: no chart rows were produced.")
    chart_rows = _normalize_runtime_chart_rows(chart_rows)
    chart_rows = _suppress_unreconciled_current_chart_rows(chart_rows, formula_residuals)
    future_revenue = _runtime_future_revenue_forecasts(current, series_meta)
    bridge_components = _runtime_bridge_components(current, series_meta)
    trace_audit = _runtime_trace_audit(chart_rows)

    scenarios = _runtime_scenario_records(existing_manifest, current)
    promotion_time = existing_manifest.get("promotion_time") if isinstance(existing_manifest, dict) else ""
    if not str(promotion_time or "").strip():
        promotion_time = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": REVENUE_OUTLOOK_SCHEMA_VERSION,
        "pack_status": "explicitly_promoted_current_outlook",
        "runtime_pack_type": "mbu26_actual_current_finalist_official_comparator",
        "promotion_time": promotion_time,
        "promoted_by": promoted_by,
        "repo_relative_output_dir": _repo_relative(root, base),
        "source_policy": (
            "committed_current_runtime_pack_only; MBU26 annual source spine is repo-local; "
            "Streamlit does not load the offline workbook or legacy Excel forecast paths"
        ),
        "runtime_policy": CURRENT_RUNTIME_POLICY,
        "allowed_traces": [
            "Actual",
            "MBU26 official",
            "Current finalist Base case",
            "Current finalist High population/comparison",
        ],
        "runtime_source_layers": {
            "A_actuals": "MBU26 annual source rows through last complete FY2025",
            "B_official_comparator": "MBU26 official forecast rows for FY2026+",
            "C_current_finalist_activity": "Promoted quarterly finalist outputs annualized by June year",
            "D_hybrid_current_revenue": "Only PED, Light RUC and Heavy RUC revenue are replaced; all other rows use MBU26 official components.",
        },
        "period_rule": {
            "last_complete_actual_fy": REVENUE_LAST_COMPLETE_ACTUAL_FY,
            "first_forecast_quarter": REVENUE_FIRST_FORECAST_QUARTER,
            "model_training_cutoff": REVENUE_MODEL_TRAINING_CUTOFF,
            "fy2026_nowcast": "2025Q3+2025Q4 source actuals plus 2026Q1+2026Q2 current finalist forecasts",
            "rule": "Actual line ends FY2025; FY2026 actual-to-date rows are nowcast inputs only and are not plotted as actuals.",
        },
        "source_comparison": {
            "comparison_id": (existing_manifest.get("source_comparison") or {}).get("comparison_id", "current_finalist_runtime_rebuild"),
            "output_dir_policy": SOURCE_COMPARISON_OUTPUT_DIR_POLICY,
            "scenario_role_validation": (existing_manifest.get("source_comparison") or {}).get(
                "scenario_role_validation",
                {"status": "passed", "source": "committed runtime rebuild"},
            ),
            "scenarios": scenarios,
        },
        "scenario_roles": scenarios,
        "join_key_contract": CANONICAL_JOIN_KEY_CONTRACT,
        "source_hashes": _runtime_source_hashes(root, scenarios, mbu26_pack),
        "mbu26_annual_spine": _mbu26_annual_spine_metadata(root, mbu26_pack),
        "revenue_source_pack": _mbu26_runtime_source_metadata(root, mbu26_pack),
        "bridge_status_by_stream": {
            "PED": ["available"],
            "LIGHT_RUC": ["available"],
            "HEAVY_RUC": ["available"],
        },
        "equations": {
            "PED": "PED revenue = current finalist VKT/capita * MBU26 population -> total VKT * MBU26 litres/100km * MBU26 gross PED rate.",
            "LIGHT_RUC": "Light RUC revenue = current finalist net km * MBU26 effective Light RUC rate.",
            "HEAVY_RUC": "Heavy RUC revenue = current finalist net km * MBU26 effective Heavy RUC rate.",
            "ROLLUPS": "Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate three replacement lines plus MBU26 fixed components.",
        },
        "rate_provenance": {
            "future_light_heavy": "mbu26_official_annual.csv effective rates joined to current finalist net-km outputs",
            "future_ped": "MBU26 population/intensity/rate joined to current finalist PED VKT/capita",
            "fixed_components": "mbu26_official_annual.csv official rows",
        },
        "trace_audit": {
            "repo_relative_path": _repo_relative(root, base / "runtime_trace_audit.csv"),
            "scope": "Per-series FY2024-FY2027 trace audit with source, role, model ID, scenario, quarter composition and anchor flags.",
        },
        "revenue_line_reconciliation": {
            "repo_relative_path": _repo_relative(root, base / "revenue_line_reconciliation.csv"),
            "scope": "Live table source for MBU26 official and current finalist line-item decomposition.",
            "source_paths": [
                "MBU26 official",
                "Current finalist Base case",
                "Current finalist High population/comparison",
            ],
        },
        "revenue_formula_residuals": {
            "repo_relative_path": _repo_relative(root, base / "revenue_formula_residuals.csv"),
            "scope": "Formula residual checks for RUC, FED, MVR and total rows by source path and FY.",
        },
        "validation_status": "runtime_rebuilt",
    }

    _write_pack_files(
        base,
        manifest,
        future_revenue,
        bridge_components,
        chart_rows,
        extra_frames={
            "runtime_trace_audit": trace_audit,
            "trace_source_contract": mbu26_pack.trace_source_contract,
            "series_trace_contract": mbu26_pack.series_trace_contract,
            "path_trace_status": mbu26_pack.path_trace_status,
            "row_reconciliation": mbu26_pack.row_reconciliation,
            "revenue_line_reconciliation": line_reconciliation,
            "revenue_formula_residuals": formula_residuals,
        },
    )
    return load_revenue_outlook_pack(base, repo_root=root)  # type: ignore[return-value]


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
    future_revenue = _add_canonical_join_keys(future_revenue)
    bridge_components = _add_canonical_join_keys(bridge_components)
    chart_rows = _add_canonical_join_keys(chart_rows)

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


def _read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _read_existing_manifest(pack_dir: Path) -> dict[str, Any]:
    path = pack_dir / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _runtime_series_metadata(series_trace_contract: pd.DataFrame) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    if isinstance(series_trace_contract, pd.DataFrame) and not series_trace_contract.empty:
        for record in series_trace_contract.to_dict("records"):
            series_id = str(record.get("canonical_id") or "").strip()
            if not series_id or series_id in metadata:
                continue
            metadata[series_id] = {
                "display_name": str(record.get("display_name") or record.get("series_option") or series_id).strip(),
                "metric_type": _runtime_metric_type(record.get("metric_type"), record.get("unit")),
                "unit": record.get("unit") or "",
                "availability_status": record.get("availability_status") or "",
                "valid_controls": record.get("valid_controls") or "",
            }
    fallback_labels = {
        "gross_fed_revenue": "Gross FED revenue",
        "total_ruc_net_revenue": "Total RUC all classes",
        "total_fed_ruc_net_revenue": "Total RUC+PED revenue",
        "total_nltf_net_revenue": "Total NLTF revenue",
        "ped_vkt_per_capita": "PED VKT per capita",
        "light_ruc_net_km": "Light RUC net km",
        "heavy_ruc_net_km": "Heavy RUC net km",
    }
    for series_id in DISPLAY_SERIES_ORDER:
        metadata.setdefault(
            series_id,
            {
                "display_name": fallback_labels.get(series_id, series_id.replace("_", " ").title()),
                "metric_type": "activity" if series_id.endswith("_km") or series_id == "ped_vkt_per_capita" else "revenue",
                "unit": "",
                "availability_status": "",
                "valid_controls": "",
            },
        )
    return metadata


def _runtime_metric_type(metric_type: Any, unit: Any = "") -> str:
    text = str(metric_type or "").strip().lower()
    if text in {"activity", "revenue"}:
        return text
    unit_text = str(unit or "").lower()
    if "km" in unit_text or "person" in unit_text:
        return "activity"
    return "revenue"


def _runtime_display_name(series_id: str, series_meta: dict[str, dict[str, Any]], fallback: Any = "") -> str:
    meta = series_meta.get(str(series_id), {})
    label = str(meta.get("display_name") or "").strip()
    if label:
        return label
    text = str(fallback or "").strip()
    return text or str(series_id).replace("_", " ").title()


def _runtime_series_id_from_release_label(label: Any) -> str:
    text = str(label or "").strip()
    return str(SOURCE_SERIES_ALIASES.get(text, "") or "").strip()


def _runtime_quarterly_activity_inputs(chart_rows: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame()
    data = chart_rows[
        chart_rows.get("time_grain", pd.Series(dtype=str)).astype(str).eq("quarterly")
        & chart_rows.get("metric_type", pd.Series(dtype=str)).astype(str).eq("activity")
    ].copy()
    if data.empty:
        return pd.DataFrame()
    stream_to_series = {
        "PED": "ped_vkt_per_capita",
        "LIGHT_RUC": "light_ruc_net_km",
        "HEAVY_RUC": "heavy_ruc_net_km",
    }
    data["series_id"] = data.get("stream", pd.Series("", index=data.index)).astype(str).map(stream_to_series).fillna("")
    data = data[data["series_id"].isin(DISPLAY_SERIES_ORDER)].copy()
    if data.empty:
        return data
    data["series_label"] = data["series_id"].map(lambda value: _runtime_display_name(value, series_meta))
    data["trace_name"] = data.apply(
        lambda row: "Actual" if str(row.get("row_type", "")) == "historical_actual" else _runtime_current_trace_name(row.get("scenario_name"), row.get("scenario_role")),
        axis=1,
    )
    data["trace_type"] = data["trace_name"].map(_runtime_trace_type)
    data["trace_role"] = data.apply(
        lambda row: "source_actual" if str(row.get("row_type", "")) == "historical_actual" else "in_house_current_finalist",
        axis=1,
    )
    data["trace_source"] = data.apply(
        lambda row: "actual_benchmark" if str(row.get("row_type", "")) == "historical_actual" else "current_finalist_forecast",
        axis=1,
    )
    data["data_scope"] = data.apply(
        lambda row: "nowcast_input_actual_not_plotted"
        if str(row.get("row_type", "")) == "historical_actual" and _coerce_int(row.get("june_year")) > REVENUE_LAST_COMPLETE_ACTUAL_FY
        else "quarterly_current_finalist_input",
        axis=1,
    )
    data["plot_allowed"] = ~(
        data.get("row_type", pd.Series("", index=data.index)).astype(str).eq("historical_actual")
        & pd.to_numeric(data.get("june_year"), errors="coerce").gt(REVENUE_LAST_COMPLETE_ACTUAL_FY)
    )
    data["model_id"] = data["series_id"].map(_runtime_model_id)
    data["fed_path"] = "Current planned path"
    data["revenue_basis"] = "not_applicable"
    data["anchor_flag"] = False
    data["nowcast_flag"] = False
    data["source_file"] = data.get("source", "")
    data["source_cell"] = data.apply(
        lambda row: f"data/current_revenue_outlook/revenue_chart_rows.csv:{row.get('scenario_name', '')}:{row.get('period', '')}",
        axis=1,
    )
    data["replacement_only"] = False
    return data


def _runtime_mbu26_actual_rows(official_annual: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    columns = _runtime_chart_columns()
    if official_annual is None or official_annual.empty:
        return pd.DataFrame(columns=columns)
    data = official_annual[
        official_annual.get("series_id", pd.Series(dtype=str)).astype(str).isin(DISPLAY_SERIES_ORDER)
    ].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[
        data["FY_numeric"].le(REVENUE_LAST_COMPLETE_ACTUAL_FY)
        & data["value_numeric"].notna()
        & data.get("period_status", pd.Series("", index=data.index)).astype(str).str.upper().eq("ACTUAL")
    ].copy()
    records: list[dict[str, Any]] = []
    for row in data.itertuples(index=False):
        series_id = str(getattr(row, "series_id", "") or "")
        fy = int(getattr(row, "FY_numeric"))
        quarters = "; ".join(_expected_june_year_quarters(fy))
        records.append(
            _runtime_chart_record(
                series_id=series_id,
                series_meta=series_meta,
                metric_type=_runtime_metric_type(series_meta.get(series_id, {}).get("metric_type"), getattr(row, "unit", "")),
                time_grain="june_year",
                row_type="historical_actual",
                trace_name="Actual",
                trace_type="Actual",
                trace_role="source_actual",
                trace_source="actual_benchmark",
                scenario_name="actual",
                scenario_role="actual",
                period=f"FY{fy}",
                june_year=fy,
                value=getattr(row, "value_numeric"),
                value_unit=getattr(row, "unit", ""),
                source=getattr(row, "source_file", "mbu26_official_annual.csv"),
                source_file=getattr(row, "source_file", "mbu26_official_annual.csv"),
                source_cell=getattr(row, "source_cell", ""),
                source_status=getattr(row, "period_status", "ACTUAL"),
                value_status=getattr(row, "value_status", "actual"),
                data_scope="mbu26_complete_actual_line",
                model_id="",
                actual_quarters=quarters,
                forecast_quarters="",
                quarters_present=quarters,
                anchor_flag=fy == REVENUE_LAST_COMPLETE_ACTUAL_FY,
                nowcast_flag=False,
                formula=getattr(row, "formula", ""),
                source_basis="MBU26 annual source spine",
                row_role=getattr(row, "row_role", ""),
                official_value=getattr(row, "value_numeric"),
                residual_vs_official=0.0,
            )
        )
    return pd.DataFrame.from_records(records, columns=columns)


def _runtime_mbu26_official_rows(official_annual: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    columns = _runtime_chart_columns()
    if official_annual is None or official_annual.empty:
        return pd.DataFrame(columns=columns)
    data = official_annual[
        official_annual.get("series_id", pd.Series(dtype=str)).astype(str).isin(DISPLAY_SERIES_ORDER)
    ].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["FY_numeric"].ge(REVENUE_LAST_COMPLETE_ACTUAL_FY + 1) & data["value_numeric"].notna()].copy()
    data = data[
        ~data.get("period_status", pd.Series("", index=data.index)).astype(str).str.upper().eq("ACTUAL")
    ].copy()
    records: list[dict[str, Any]] = []
    for row in data.itertuples(index=False):
        series_id = str(getattr(row, "series_id", "") or "")
        fy = int(getattr(row, "FY_numeric"))
        records.append(
            _runtime_chart_record(
                series_id=series_id,
                series_meta=series_meta,
                metric_type=_runtime_metric_type(series_meta.get(series_id, {}).get("metric_type"), getattr(row, "unit", "")),
                time_grain="june_year",
                row_type="official_comparator",
                trace_name="MBU26 official",
                trace_type="MBU26 official",
                trace_role="official_external_comparator",
                trace_source="mbu26_official",
                scenario_name="mbu26_official",
                scenario_role="official_comparator",
                period=f"FY{fy}",
                june_year=fy,
                value=getattr(row, "value_numeric"),
                value_unit=getattr(row, "unit", ""),
                source=getattr(row, "source_file", "mbu26_official_annual.csv"),
                source_file=getattr(row, "source_file", "mbu26_official_annual.csv"),
                source_cell=getattr(row, "source_cell", ""),
                source_status=getattr(row, "period_status", ""),
                value_status=getattr(row, "value_status", "official_forecast"),
                data_scope="mbu26_official_forecast",
                model_id="",
                fed_path=MBU26_RELEASE_ROUND,
                revenue_basis=getattr(row, "unit", ""),
                bridge_status="available",
                bridge_method="MBU26 official annual row",
                release_round=MBU26_RELEASE_ROUND,
                anchor_flag=False,
                nowcast_flag=False,
                formula=getattr(row, "formula", ""),
                source_basis="MBU26 official annual",
                row_role=getattr(row, "row_role", ""),
                official_value=getattr(row, "value_numeric"),
                residual_vs_official=0.0,
            )
        )
    return pd.DataFrame.from_records(records, columns=columns)


def _runtime_actual_rows(series_junction_audit: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    columns = _runtime_chart_columns()
    if series_junction_audit is None or series_junction_audit.empty:
        return pd.DataFrame(columns=columns)
    data = series_junction_audit[
        series_junction_audit.get("path", pd.Series(dtype=str)).astype(str).eq("actual_or_actual_to_date")
        & series_junction_audit.get("series_id", pd.Series(dtype=str)).astype(str).isin(DISPLAY_SERIES_ORDER)
    ].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["FY_numeric"].le(REVENUE_LAST_COMPLETE_ACTUAL_FY) & data["value_numeric"].notna()].copy()
    records: list[dict[str, Any]] = []
    for row in data.itertuples(index=False):
        series_id = str(getattr(row, "series_id", "") or "")
        fy = int(getattr(row, "FY_numeric"))
        records.append(
            _runtime_chart_record(
                series_id=series_id,
                series_meta=series_meta,
                metric_type=_runtime_metric_type(series_meta.get(series_id, {}).get("metric_type"), getattr(row, "unit", "")),
                time_grain="june_year",
                row_type="historical_actual",
                trace_name="Actual",
                trace_type="Actual",
                trace_role="source_actual",
                trace_source="actual_benchmark",
                scenario_name="actual",
                scenario_role="actual",
                period=f"FY{fy}",
                june_year=fy,
                value=getattr(row, "value_numeric"),
                value_unit=getattr(row, "unit", ""),
                source=getattr(row, "source_file", "annual_actuals.csv"),
                source_file=getattr(row, "source_file", "annual_actuals.csv"),
                source_cell=getattr(row, "source_cell", ""),
                source_status=getattr(row, "source_status", ""),
                value_status=getattr(row, "value_status", "Actual"),
                data_scope="complete_actual_line",
                model_id="",
                actual_quarters=getattr(row, "actual_quarters", ""),
                forecast_quarters="",
                quarters_present=getattr(row, "quarters_present", ""),
                anchor_flag=fy == REVENUE_LAST_COMPLETE_ACTUAL_FY,
                nowcast_flag=False,
            )
        )
    return pd.DataFrame.from_records(records, columns=columns)


def _runtime_current_rows(current: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    columns = _runtime_chart_columns()
    if current is None or current.empty:
        return pd.DataFrame(columns=columns)
    data = current[current.get("series_id", pd.Series(dtype=str)).astype(str).isin(DISPLAY_SERIES_ORDER)].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["FY_numeric"].ge(REVENUE_LAST_COMPLETE_ACTUAL_FY) & data["value_numeric"].notna()].copy()
    records: list[dict[str, Any]] = []
    for row in data.itertuples(index=False):
        series_id = str(getattr(row, "series_id", "") or "")
        fy = int(getattr(row, "FY_numeric"))
        scenario_name = str(getattr(row, "scenario_name", "") or "")
        scenario_role = str(getattr(row, "scenario_role", "") or "")
        records.append(
            _runtime_chart_record(
                series_id=series_id,
                series_meta=series_meta,
                metric_type=_runtime_metric_type(series_meta.get(series_id, {}).get("metric_type"), getattr(row, "unit", "")),
                time_grain="june_year",
                row_type="future_forecast",
                trace_name=_runtime_current_trace_name(scenario_name, scenario_role),
                trace_type=_runtime_trace_type(_runtime_current_trace_name(scenario_name, scenario_role)),
                trace_role="in_house_current_finalist",
                trace_source="current_finalist_forecast",
                scenario_name=scenario_name,
                scenario_role=scenario_role,
                period=f"FY{fy}",
                june_year=fy,
                value=getattr(row, "value_numeric"),
                value_unit=getattr(row, "unit", ""),
                source=getattr(row, "source_file", ""),
                source_file=getattr(row, "source_file", ""),
                source_cell=getattr(row, "source_cell", ""),
                source_status=getattr(row, "source_status", ""),
                value_status=getattr(row, "value_status", ""),
                data_scope="actual_anchor" if fy == REVENUE_LAST_COMPLETE_ACTUAL_FY else ("current_nowcast" if bool(getattr(row, "nowcast_flag", False)) else "current_forecast"),
                model_id=getattr(row, "model_id", "") or _runtime_model_id(series_id),
                fed_path=getattr(row, "fed_path", ""),
                revenue_basis="not_applicable" if series_meta.get(series_id, {}).get("metric_type") == "activity" else "Net",
                bridge_status="available",
                bridge_method=getattr(row, "formula", "") or getattr(row, "source_basis", ""),
                actual_quarters=getattr(row, "actual_quarters", ""),
                forecast_quarters=getattr(row, "forecast_quarters", ""),
                quarters_present=getattr(row, "quarters_present", ""),
                anchor_flag=fy == REVENUE_LAST_COMPLETE_ACTUAL_FY,
                nowcast_flag=bool(getattr(row, "nowcast_flag", False)),
                formula=getattr(row, "formula", ""),
                source_basis=getattr(row, "source_basis", ""),
                row_role=getattr(row, "row_role", ""),
                replacement_only=bool(getattr(row, "replacement_only", False)),
                official_value=getattr(row, "official_value", pd.NA),
                residual_vs_official=getattr(row, "residual_vs_official", pd.NA),
            )
        )
    return pd.DataFrame.from_records(records, columns=columns)


def _runtime_release_rows(
    release_values: pd.DataFrame,
    series_meta: dict[str, dict[str, Any]],
    *,
    trace_name: str,
    scenario_name: str,
    trace_source: str,
) -> pd.DataFrame:
    columns = _runtime_chart_columns()
    if release_values is None or release_values.empty:
        return pd.DataFrame(columns=columns)
    data = release_values.copy()
    if trace_source == "selected_mot_befu_release":
        data = data[data.get("release_round", pd.Series(dtype=str)).astype(str).eq("BEFU25")].copy()
        data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
        data = data[data["FY_numeric"].between(REVENUE_LAST_COMPLETE_ACTUAL_FY - 1, 2031, inclusive="both")].copy()
    else:
        data = data[
            data.get("release_family", pd.Series(dtype=str)).astype(str).eq("BEFU")
            & pd.to_numeric(data.get("horizon"), errors="coerce").eq(1)
        ].copy()
        data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
        data = data[data["FY_numeric"].between(REVENUE_LAST_COMPLETE_ACTUAL_FY - 6, 2031, inclusive="both")].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["series_id"] = data.get("series", pd.Series(dtype=str)).map(_runtime_series_id_from_release_label)
    data = data[data["series_id"].isin(DISPLAY_SERIES_ORDER)].copy()
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    sort_cols = [col for col in ["series_id", "FY_numeric", "release_year", "release_round"] if col in data.columns]
    data = data.sort_values(sort_cols, kind="stable").drop_duplicates(["series_id", "FY_numeric"], keep="last")
    records: list[dict[str, Any]] = []
    for row in data.itertuples(index=False):
        series_id = str(getattr(row, "series_id", "") or "")
        fy = int(getattr(row, "FY_numeric"))
        records.append(
            _runtime_chart_record(
                series_id=series_id,
                series_meta=series_meta,
                metric_type=_runtime_metric_type(series_meta.get(series_id, {}).get("metric_type"), getattr(row, "unit", "")),
                time_grain="june_year",
                row_type="official_comparator",
                trace_name=trace_name,
                trace_type=_runtime_trace_type(trace_name),
                trace_role="official_external_comparator",
                trace_source=trace_source,
                scenario_name=scenario_name,
                scenario_role="official_comparator",
                period=f"FY{fy}",
                june_year=fy,
                value=getattr(row, "value_numeric"),
                value_unit=getattr(row, "unit", ""),
                source="release_values.csv",
                source_file="release_values.csv",
                source_cell=getattr(row, "source_cell", ""),
                source_status=getattr(row, "value_status", ""),
                value_status=getattr(row, "value_status", ""),
                data_scope="official_comparator",
                model_id="",
                fed_path=getattr(row, "fed_path", "") or "BEFU25",
                revenue_basis=getattr(row, "revenue_basis", ""),
                bridge_status="available",
                bridge_method="official MOT/BEFU release value",
                release_round=getattr(row, "release_round", ""),
                anchor_flag=False,
                nowcast_flag=False,
            )
        )
    return pd.DataFrame.from_records(records, columns=columns)


def _normalize_runtime_chart_rows(chart_rows: pd.DataFrame) -> pd.DataFrame:
    for column in _runtime_chart_columns():
        if column not in chart_rows.columns:
            chart_rows[column] = pd.NA
    chart_rows["june_year"] = pd.to_numeric(chart_rows["june_year"], errors="coerce").astype("Int64")
    chart_rows["value"] = pd.to_numeric(chart_rows["value"], errors="coerce")
    chart_rows["forecast_available"] = chart_rows["value"].notna()
    if "plot_allowed" not in chart_rows.columns:
        chart_rows["plot_allowed"] = True
    chart_rows["plot_allowed"] = chart_rows["plot_allowed"].fillna(True).astype(bool)
    chart_rows["trace_type"] = chart_rows["trace_type"].where(
        chart_rows["trace_type"].astype(str).str.strip().ne(""),
        chart_rows["trace_name"].map(_runtime_trace_type),
    )
    chart_rows["source_cell"] = chart_rows["source_cell"].fillna("").astype(str)
    chart_rows["replacement_only"] = chart_rows["replacement_only"].fillna(False).astype(bool)
    chart_rows = chart_rows[chart_rows["value"].notna()].copy()
    chart_rows["_series_order"] = chart_rows["series_id"].map(lambda value: DISPLAY_SERIES_ORDER.index(value) if value in DISPLAY_SERIES_ORDER else len(DISPLAY_SERIES_ORDER))
    chart_rows["_period_order"] = chart_rows["period"].map(_period_sort_value)
    chart_rows["_trace_order"] = chart_rows["trace_name"].map(_trace_sort_value)
    chart_rows = chart_rows.sort_values(["metric_type", "_series_order", "time_grain", "_period_order", "_trace_order", "scenario_name"], kind="stable")
    chart_rows = chart_rows.drop(columns=["_series_order", "_period_order", "_trace_order"], errors="ignore")
    return _add_canonical_join_keys(chart_rows[_runtime_chart_columns()])


def _suppress_unreconciled_current_chart_rows(chart_rows: pd.DataFrame, formula_residuals: pd.DataFrame) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty or formula_residuals is None or formula_residuals.empty:
        return chart_rows
    residuals = formula_residuals.copy()
    residuals = residuals[
        residuals.get("source_path", pd.Series(dtype=str)).astype(str).str.startswith("Current finalist")
        & ~residuals.get("status", pd.Series(dtype=str)).astype(str).eq("reconciled")
    ].copy()
    if residuals.empty:
        return chart_rows
    blocked = {
        (str(row.source_path), int(row.FY), str(row.output_series_id)): str(row.status)
        for row in residuals.itertuples()
        if pd.notna(row.FY)
    }
    if not blocked:
        return chart_rows
    out = chart_rows.copy()
    for idx, row in out.iterrows():
        if str(row.get("trace_role", "")) != "in_house_current_finalist":
            continue
        key = (str(row.get("trace_name", "")), _coerce_int(row.get("june_year")), str(row.get("series_id", "")))
        status = blocked.get(key)
        if not status:
            continue
        out.at[idx, "plot_allowed"] = False
        out.at[idx, "bridge_status"] = "governed_gap"
        out.at[idx, "gap_code"] = "formula_reconciliation_failed"
        out.at[idx, "gap_reason"] = f"Current-finalist aggregate suppressed because formula residual status is {status}."
    return out


def _runtime_future_revenue_forecasts(current: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    revenue_ids = {
        "gross_ped_revenue",
        "light_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "gross_fed_revenue",
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
    }
    data = current[current.get("series_id", pd.Series(dtype=str)).astype(str).isin(revenue_ids)].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["FY_numeric"].ge(REVENUE_FIRST_FORECAST_FY) & data["value_numeric"].notna()].copy()
    if data.empty:
        return _add_canonical_join_keys(pd.DataFrame())
    out = pd.DataFrame(
        {
            "stream": data["series_id"].astype(str),
            "stream_label": data["series_id"].astype(str).map(lambda value: _runtime_display_name(value, series_meta)),
            "component_type": data.get("row_role", ""),
            "period": data["FY_numeric"].map(lambda value: f"FY{int(value)}"),
            "target_period": data["FY_numeric"].map(lambda value: f"FY{int(value)}"),
            "scenario_name": data.get("scenario_name", ""),
            "scenario_role": data.get("scenario_role", ""),
            "fed_path": data.get("fed_path", ""),
            "revenue_forecast_nzd": data["value_numeric"],
            "revenue_unit": data.get("unit", "$m nominal ex GST"),
            "forecast_available": True,
            "bridge_status": "available",
            "bridge_method": data.get("formula", ""),
            "source": data.get("source_file", ""),
            "model_id": data.get("model_id", ""),
            "value_status": data.get("value_status", ""),
            "actual_quarters": data.get("actual_quarters", ""),
            "forecast_quarters": data.get("forecast_quarters", ""),
            "nowcast_flag": data.get("nowcast_flag", False),
        }
    )
    return _add_canonical_join_keys(out)


def _runtime_bridge_components(current: pd.DataFrame, series_meta: dict[str, dict[str, Any]]) -> pd.DataFrame:
    data = current[current.get("series_id", pd.Series(dtype=str)).astype(str).isin(DISPLAY_SERIES_ORDER)].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return _add_canonical_join_keys(pd.DataFrame())
    out = pd.DataFrame(
        {
            "stream": data["series_id"].astype(str),
            "stream_label": data["series_id"].astype(str).map(lambda value: _runtime_display_name(value, series_meta)),
            "component_type": data.get("row_role", ""),
            "period": data["FY_numeric"].map(lambda value: f"FY{int(value)}"),
            "target_period": data["FY_numeric"].map(lambda value: f"FY{int(value)}"),
            "scenario_name": data.get("scenario_name", ""),
            "scenario_role": data.get("scenario_role", ""),
            "fed_path": data.get("fed_path", ""),
            "component_value": data["value_numeric"],
            "component_unit": data.get("unit", ""),
            "bridge_status": "available",
            "bridge_method": data.get("formula", ""),
            "equation": data.get("formula", ""),
            "source": data.get("source_file", ""),
            "source_basis": data.get("source_basis", ""),
            "model_id": data.get("model_id", ""),
            "official_value": data.get("official_value", pd.NA),
            "residual_vs_official": data.get("residual_vs_official", pd.NA),
            "value_status": data.get("value_status", ""),
            "actual_quarters": data.get("actual_quarters", ""),
            "forecast_quarters": data.get("forecast_quarters", ""),
            "nowcast_flag": data.get("nowcast_flag", False),
        }
    )
    return _add_canonical_join_keys(out)


def _runtime_trace_audit(chart_rows: pd.DataFrame) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame()
    data = chart_rows.copy()
    data = data[data.get("time_grain", pd.Series(dtype=str)).astype(str).eq("june_year")].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("june_year"), errors="coerce")
    data = data[data["FY_numeric"].between(2024, 2027, inclusive="both")].copy()
    columns = [
        "series_id",
        "series_label",
        "trace_name",
        "trace_type",
        "trace_role",
        "trace_source",
        "scenario_name",
        "fed_path",
        "period",
        "june_year",
        "value",
        "value_unit",
        "row_type",
        "data_scope",
        "source_file",
        "source_cell",
        "source_status",
        "formula",
        "model_id",
        "replacement_only",
        "value_status",
        "actual_quarters",
        "forecast_quarters",
        "quarters_present",
        "anchor_flag",
        "nowcast_flag",
        "plot_allowed",
    ]
    for column in columns:
        if column not in data.columns:
            data[column] = pd.NA
    return data[columns].sort_values(["series_id", "june_year", "trace_name", "scenario_name"], kind="stable").reset_index(drop=True)


def _runtime_chart_columns() -> list[str]:
    return [
        "metric_type",
        "time_grain",
        "row_type",
        "trace_name",
        "trace_type",
        "trace_role",
        "trace_source",
        "scenario_name",
        "scenario_role",
        "stream",
        "stream_label",
        "series_id",
        "series_label",
        "period",
        "target_period",
        "june_year",
        "horizon",
        "horizon_scope",
        "value",
        "value_unit",
        "forecast_available",
        "bridge_status",
        "bridge_method",
        "rate_value",
        "rate_unit",
        "gap_code",
        "gap_reason",
        "source",
        "source_file",
        "source_cell",
        "source_status",
        "source_basis",
        "formula",
        "model_id",
        "model_basis",
        "data_scope",
        "value_status",
        "fed_path",
        "revenue_basis",
        "release_round",
        "actual_quarters",
        "forecast_quarters",
        "quarters_present",
        "anchor_flag",
        "nowcast_flag",
        "plot_allowed",
        "row_role",
        "replacement_only",
        "official_value",
        "residual_vs_official",
    ] + CANONICAL_JOIN_KEY_COLUMNS


def _runtime_chart_record(
    *,
    series_id: str,
    series_meta: dict[str, dict[str, Any]],
    metric_type: str,
    time_grain: str,
    row_type: str,
    trace_name: str,
    trace_type: str,
    trace_role: str,
    trace_source: str,
    scenario_name: str,
    scenario_role: str,
    period: str,
    june_year: int,
    value: Any,
    value_unit: Any,
    source: Any,
    source_file: Any,
    source_cell: Any,
    source_status: Any,
    value_status: Any,
    data_scope: str,
    model_id: Any = "",
    fed_path: Any = "",
    revenue_basis: Any = "",
    bridge_status: Any = "available",
    bridge_method: Any = "",
    rate_value: Any = pd.NA,
    rate_unit: Any = "",
    gap_code: Any = "",
    gap_reason: Any = "",
    release_round: Any = "",
    actual_quarters: Any = "",
    forecast_quarters: Any = "",
    quarters_present: Any = "",
    anchor_flag: bool = False,
    nowcast_flag: bool = False,
    plot_allowed: bool = True,
    formula: Any = "",
    source_basis: Any = "",
    row_role: Any = "",
    replacement_only: bool = False,
    official_value: Any = pd.NA,
    residual_vs_official: Any = pd.NA,
) -> dict[str, Any]:
    label = _runtime_display_name(series_id, series_meta)
    return {
        "metric_type": metric_type,
        "time_grain": time_grain,
        "row_type": row_type,
        "trace_name": trace_name,
        "trace_type": trace_type or _runtime_trace_type(trace_name),
        "trace_role": trace_role,
        "trace_source": trace_source,
        "scenario_name": scenario_name,
        "scenario_role": scenario_role,
        "stream": series_id,
        "stream_label": label,
        "series_id": series_id,
        "series_label": label,
        "period": period,
        "target_period": period,
        "june_year": june_year,
        "horizon": "",
        "horizon_scope": "",
        "value": value,
        "value_unit": value_unit,
        "forecast_available": pd.notna(value),
        "bridge_status": bridge_status,
        "bridge_method": bridge_method,
        "rate_value": rate_value,
        "rate_unit": rate_unit,
        "gap_code": gap_code,
        "gap_reason": gap_reason,
        "source": source,
        "source_file": source_file,
        "source_cell": source_cell,
        "source_status": source_status,
        "source_basis": source_basis,
        "formula": formula,
        "model_id": model_id,
        "model_basis": "Current finalist ensemble" if trace_role == "in_house_current_finalist" else "",
        "data_scope": data_scope,
        "value_status": value_status,
        "fed_path": fed_path,
        "revenue_basis": revenue_basis,
        "release_round": release_round,
        "actual_quarters": actual_quarters,
        "forecast_quarters": forecast_quarters,
        "quarters_present": quarters_present,
        "anchor_flag": anchor_flag,
        "nowcast_flag": nowcast_flag,
        "plot_allowed": plot_allowed,
        "row_role": row_role,
        "replacement_only": bool(replacement_only),
        "official_value": official_value,
        "residual_vs_official": residual_vs_official,
    }


def _runtime_current_trace_name(scenario_name: Any, scenario_role: Any) -> str:
    role = str(scenario_role or "").strip().lower()
    name = str(scenario_name or "").strip().lower()
    if role == SCENARIO_ROLE_BASECASE or name == "current_basecase":
        return "Current finalist Base case"
    return "Current finalist High population/comparison"


def _runtime_trace_type(trace_name: Any) -> str:
    name = str(trace_name or "").strip()
    if name == "Actual":
        return "Actual"
    if name == "MBU26 official":
        return "MBU26 official"
    if name == "Current finalist Base case":
        return "current finalist base"
    if name == "Current finalist High population/comparison":
        return "current finalist comparison"
    return name


def _runtime_model_id(series_id: Any) -> str:
    series = str(series_id or "")
    if series in {"ped_vkt_per_capita", "ped_volume", "gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue"}:
        return CURRENT_FINALIST_MODEL_IDS["PED"]
    if series in {"light_ruc_net_km", "light_ruc_net_revenue"}:
        return CURRENT_FINALIST_MODEL_IDS["LIGHT_RUC"]
    if series in {"heavy_ruc_net_km", "heavy_ruc_net_revenue"}:
        return CURRENT_FINALIST_MODEL_IDS["HEAVY_RUC"]
    if series in {"total_ruc_net_revenue", "total_fed_ruc_net_revenue", "total_nltf_net_revenue"}:
        return CURRENT_FINALIST_COMPOSITE_MODEL_ID
    return ""


def _runtime_scenario_records(existing_manifest: dict[str, Any], current: pd.DataFrame) -> list[dict[str, Any]]:
    source = existing_manifest.get("source_comparison") if isinstance(existing_manifest, dict) else {}
    scenarios = source.get("scenarios") if isinstance(source, dict) else None
    if isinstance(scenarios, list) and scenarios:
        return [dict(item) for item in scenarios if isinstance(item, dict)]
    records = []
    for scenario_name, group in current.groupby("scenario_name", dropna=False):
        name = str(scenario_name or "")
        role = first_non_null(group.get("scenario_role", pd.Series(dtype=str))) or ""
        records.append(
            {
                "scenario_name": name,
                "scenario_role": role,
                "scenario_display_name": _runtime_current_trace_name(name, role),
                "is_test_fixture": False,
                "forecast_status": "current finalist runtime rows",
            }
        )
    return records


def _period_sort_value(period: Any) -> int:
    text = str(period or "").upper().replace("FY", "")
    if "Q" in text:
        try:
            year, quarter = text.split("Q", 1)
            return int(year) * 10 + int(quarter)
        except Exception:
            return 0
    try:
        return int(text) * 10
    except Exception:
        return 0


def _trace_sort_value(trace_name: Any) -> int:
    order = {
        "Actual": 0,
        "MBU26 official": 1,
        "Current finalist Base case": 2,
        "Current finalist High population/comparison": 3,
        "Official comparator: selected MOT/BEFU": 4,
        "Official comparator: rolling BEFU 1Y": 5,
    }
    return order.get(str(trace_name or ""), 99)


def _expected_june_year_quarters(fy: int) -> list[str]:
    return [f"{fy - 1}Q3", f"{fy - 1}Q4", f"{fy}Q1", f"{fy}Q2"]


def _coerce_int(value: Any) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except Exception:
        return 0


def _validate_output_hashes(pack_dir: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    output_hashes = manifest.get("output_hashes")
    if not isinstance(output_hashes, dict):
        return ["manifest output_hashes is missing or invalid."]
    for filename in RUNTIME_REVENUE_OUTLOOK_FILES:
        if filename not in output_hashes:
            errors.append(f"{filename} is missing from output_hashes.")
    for filename, metadata in sorted(output_hashes.items()):
        name = str(filename).strip()
        if not name:
            continue
        expected = str(metadata.get("sha256", "")).strip() if isinstance(metadata, dict) else ""
        path = pack_dir / name
        if not path.exists():
            errors.append(f"{name} is missing.")
            continue
        if not expected:
            errors.append(f"{name} has no SHA256 in output_hashes.")
            continue
        actual = _sha256(path)
        if actual != expected:
            errors.append(f"{name} hash mismatch.")
    return errors


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


def _add_canonical_join_keys(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame() if frame is None else frame
    out = frame.copy()
    out["canonical_stream_key"] = out.apply(_canonical_stream_key, axis=1)
    out["canonical_period_key"] = out.apply(_canonical_period_key, axis=1)
    out["canonical_scenario_key"] = out.apply(_canonical_scenario_key, axis=1)
    out["canonical_join_key"] = (
        out["canonical_stream_key"].astype(str)
        + "|"
        + out["canonical_period_key"].astype(str)
        + "|"
        + out["canonical_scenario_key"].astype(str)
    )
    return out


def _canonical_stream_key(row: pd.Series) -> str:
    stream = str(row.get("stream") or "").strip().upper()
    if stream:
        return stream
    label = str(row.get("stream_label") or "").strip()
    for key, stream_label in STREAM_LABELS.items():
        if label == stream_label:
            return key
    return "UNKNOWN_STREAM"


def _canonical_period_key(row: pd.Series) -> str:
    for column in ("target_period", "period"):
        value = row.get(column)
        if pd.notna(value) and str(value).strip():
            return str(value).strip().upper()
    return "ALL_PERIODS"


def _canonical_scenario_key(row: pd.Series) -> str:
    scenario = row.get("scenario_name")
    if pd.notna(scenario) and str(scenario).strip():
        return str(scenario).strip()
    row_type = str(row.get("row_type") or "").strip()
    if row_type == "historical_actual":
        return "historical_actual"
    component_type = str(row.get("component_type") or "").strip()
    if component_type == "historical_revenue_reconciliation":
        return "historical_actual"
    return "all_scenarios"


def _promoted_scenario_manifest_records(scenarios: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scenario in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(scenario, dict):
            continue
        records.append(
            {field: scenario.get(field) for field in PROMOTED_SCENARIO_MANIFEST_FIELDS if field in scenario}
        )
    return records


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
    source_scenarios = comparison.manifest.get("scenarios", [])
    scenarios = _promoted_scenario_manifest_records(source_scenarios)
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
            "output_dir_policy": SOURCE_COMPARISON_OUTPUT_DIR_POLICY,
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
        "join_key_contract": CANONICAL_JOIN_KEY_CONTRACT,
        "revenue_source_pack": _revenue_source_pack_metadata(repo_root),
        "bridge_status_by_stream": bridge_status,
        "row_counts": {
            "future_revenue_forecasts": int(len(future_revenue)),
            "revenue_bridge_components": int(len(bridge_components)),
            "revenue_chart_rows": int(len(chart_rows)),
        },
        "source_hashes": _source_hashes(repo_root, source_scenarios),
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
    *,
    extra_frames: dict[str, pd.DataFrame] | None = None,
) -> None:
    frames = {
        "future_revenue_forecasts": future_revenue,
        "revenue_bridge_components": bridge_components,
        "revenue_chart_rows": chart_rows,
    }
    if extra_frames:
        frames.update(extra_frames)
    for required_stem in [
        "runtime_trace_audit",
        "revenue_line_reconciliation",
        "revenue_formula_residuals",
        "trace_source_contract",
        "series_trace_contract",
        "path_trace_status",
    ]:
        frames.setdefault(required_stem, pd.DataFrame())
    for stem, frame in frames.items():
        output_frame = _prepare_frame_for_output(frame)
        output_frame.to_parquet(output_dir / f"{stem}.parquet", index=False)
        output_frame.to_csv(output_dir / f"{stem}.csv", index=False)
    output_hashes: dict[str, Any] = {}
    for stem in sorted(frames):
        for suffix in ("csv", "parquet"):
            filename = f"{stem}.{suffix}"
            path = output_dir / filename
            output_hashes[filename] = {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
    manifest["output_hashes"] = output_hashes
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output_dir / "manifest.md").write_text(_manifest_markdown(manifest), encoding="utf-8")


def _prepare_frame_for_output(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if output[column].dtype == object:
            output[column] = output[column].where(output[column].notna(), "").astype(str)
    return output


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
    equations = manifest.get("equations") if isinstance(manifest.get("equations"), dict) else REVENUE_EQUATIONS
    for stream, equation in equations.items():
        rows.append(f"- {STREAM_LABELS.get(stream, stream)}: {equation}")
    rows.extend(["", "## Scenario Roles"])
    for scenario in scenarios if isinstance(scenarios, list) else []:
        rows.append(
            f"- `{scenario.get('scenario_name')}`: `{scenario.get('scenario_role')}`, "
            f"workbook `{scenario.get('workbook_filename')}`, SHA256 `{scenario.get('workbook_sha256')}`"
        )
    rows.extend(["", "## Bridge Status"])
    for stream, statuses in (manifest.get("bridge_status_by_stream") or {}).items():
        rows.append(f"- {STREAM_LABELS.get(stream, stream)}: {', '.join(statuses)}")
    join_contract = manifest.get("join_key_contract") or {}
    if join_contract:
        rows.extend(
            [
                "",
                "## Canonical Join Keys",
                f"- Columns: `{', '.join(join_contract.get('columns', []))}`",
                f"- Rule: {join_contract.get('rule')}",
            ]
        )
    source_pack = manifest.get("revenue_source_pack") or {}
    if source_pack:
        dashboard_defaults = source_pack.get("dashboard_default_selections") or source_pack.get("selections") or {}
        source_workbook_selections = source_pack.get("source_workbook_selections") or {}
        rows.extend(
            [
                "",
                "## Revenue Source Pack",
                f"- Version: `{source_pack.get('source_pack_version')}`",
                f"- Raw workbook SHA256: `{source_pack.get('raw_workbook_sha256')}`",
                f"- Manifest SHA256: `{source_pack.get('source_pack_manifest_sha256')}`",
                f"- Status: `{source_pack.get('status')}`",
                f"- Dashboard default series: `{dashboard_defaults.get('series')}`",
                f"- Source workbook current series: `{source_workbook_selections.get('series')}`",
            ]
        )
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


def _runtime_source_hashes(repo_root: Path, scenarios: Any, mbu26_pack: Any) -> dict[str, Any]:
    hashes = _source_hashes(repo_root, scenarios)
    hashes["mbu26_annual_spine"] = {
        "repo_relative_path": _repo_relative(repo_root, mbu26_pack.pack_dir),
        "manifest_sha256": _sha256(mbu26_pack.pack_dir / "manifest.json"),
        "source_release": MBU26_RELEASE_ROUND,
        "schema_version": (mbu26_pack.manifest or {}).get("schema_version", MBU26_SCHEMA_VERSION),
        "workbook_basename": ((mbu26_pack.manifest or {}).get("workbook") or {}).get("basename", ""),
        "workbook_sha256": ((mbu26_pack.manifest or {}).get("workbook") or {}).get("sha256", ""),
        "normalized_files": {
            filename: metadata
            for filename, metadata in ((mbu26_pack.manifest or {}).get("normalized_files") or {}).items()
            if isinstance(metadata, dict)
        },
    }
    return hashes


def _mbu26_annual_spine_metadata(repo_root: Path, mbu26_pack: Any) -> dict[str, Any]:
    manifest = mbu26_pack.manifest or {}
    workbook = manifest.get("workbook") or {}
    return {
        "status": "mbu26_annual_spine_vendored",
        "source_release": MBU26_RELEASE_ROUND,
        "schema_version": manifest.get("schema_version", MBU26_SCHEMA_VERSION),
        "repo_relative_path": _repo_relative(repo_root, mbu26_pack.pack_dir),
        "manifest_sha256": _sha256(mbu26_pack.pack_dir / "manifest.json"),
        "workbook_basename": workbook.get("basename", ""),
        "workbook_sha256": workbook.get("sha256", ""),
        "sheet": workbook.get("sheet", "MBU26"),
        "source_policy": manifest.get(
            "source_policy",
            "MBU26 worksheet only; workbook is offline lineage and is never loaded at Streamlit runtime.",
        ),
        "row_count": manifest.get("row_count") or {},
        "formula_policy": manifest.get("formula_policy", ""),
    }


def _mbu26_runtime_source_metadata(repo_root: Path, mbu26_pack: Any) -> dict[str, Any]:
    manifest = mbu26_pack.manifest or {}
    workbook = manifest.get("workbook") or {}
    defaults = {
        "series": "Total NLTF revenue",
        "release_round": MBU26_RELEASE_ROUND,
        "revenue_path": "Net of admin fees & refunds",
        "scenario": "MBU26 official + current finalist base/comparison",
        "fed_path_scenario": "Current planned path",
        "view": "Annual",
        "model_basis": "Current finalist ensemble",
        "uncertainty_source": "not materialized",
        "selected_fy": "FY2031",
        "crown_top_up": "Exclude",
    }
    return {
        "status": "mbu26_annual_spine_vendored",
        "repo_relative_path": _repo_relative(repo_root, mbu26_pack.pack_dir),
        "source_pack_version": MBU26_RELEASE_ROUND,
        "schema_version": manifest.get("schema_version", MBU26_SCHEMA_VERSION),
        "raw_workbook_basename": workbook.get("basename", ""),
        "raw_workbook_sha256": workbook.get("sha256", ""),
        "source_pack_manifest_sha256": _sha256(mbu26_pack.pack_dir / "manifest.json"),
        "selections": defaults,
        "dashboard_default_selections": defaults,
        "source_workbook_selections": {"release_round": MBU26_RELEASE_ROUND, "sheet": workbook.get("sheet", "MBU26")},
        "default_selection_policy": "Revenue Outlook defaults to Total NLTF revenue from the MBU26 source spine.",
    }


def _revenue_source_pack_metadata(repo_root: Path) -> dict[str, Any]:
    pack_dir = repo_root / REVENUE_SOURCE_PACK_DIR
    manifest_path = pack_dir / "manifest.json"
    front_end_config_path = pack_dir / "front_end_config.json"
    if not manifest_path.exists():
        return {
            "status": "source_pack_missing",
            "repo_relative_path": _repo_relative(repo_root, pack_dir),
        }
    try:
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "source_pack_manifest_unreadable",
            "repo_relative_path": _repo_relative(repo_root, pack_dir),
            "error": str(exc),
        }
    source_workbook_selections: dict[str, Any] = {}
    if front_end_config_path.exists():
        try:
            config = json.loads(front_end_config_path.read_text(encoding="utf-8"))
            source_workbook_selections = {
                key: value.get("current_value")
                for key, value in (config.get("current_selections") or {}).items()
                if isinstance(value, dict)
            }
        except Exception:
            source_workbook_selections = {}
    dashboard_default_selections = _dashboard_default_revenue_selections(source_workbook_selections)
    return {
        "status": "source_pack_vendored",
        "repo_relative_path": _repo_relative(repo_root, pack_dir),
        "source_pack_version": source_manifest.get("source_pack_version"),
        "schema_version": source_manifest.get("schema_version"),
        "raw_workbook_basename": source_manifest.get("raw_workbook", {}).get("basename"),
        "raw_workbook_sha256": source_manifest.get("raw_workbook", {}).get("sha256"),
        "distilled_workbook_basename": source_manifest.get("distilled_workbook", {}).get("basename"),
        "distilled_workbook_sha256": source_manifest.get("distilled_workbook", {}).get("sha256"),
        "source_pack_manifest_sha256": _sha256(manifest_path),
        "selections": dashboard_default_selections,
        "dashboard_default_selections": dashboard_default_selections,
        "source_workbook_selections": source_workbook_selections,
        "default_selection_policy": (
            "Revenue Outlook defaults to Total NLTF revenue even when the source workbook current selection "
            "uses the legacy Total RUC+PED subtotal."
        ),
    }


def _dashboard_default_revenue_selections(source_workbook_selections: dict[str, Any]) -> dict[str, Any]:
    defaults = dict(source_workbook_selections)
    defaults["series"] = "Total NLTF revenue"
    defaults.setdefault("release_round", "BEFU25")
    defaults.setdefault("revenue_path", "Net of admin fees & refunds")
    defaults.setdefault("scenario", "Medium")
    defaults.setdefault("fed_path_scenario", "Current planned path")
    defaults.setdefault("view", "Annual")
    defaults.setdefault("model_basis", "In-house model")
    defaults.setdefault("uncertainty_source", "MOT release round")
    defaults.setdefault("selected_fy", "FY2031")
    defaults.setdefault("crown_top_up", "Exclude")
    return defaults


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

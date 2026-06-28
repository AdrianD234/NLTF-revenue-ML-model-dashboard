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
    CURRENT_LIGHT_TOTAL_SERIES_ID,
    CURRENT_MODEL_EXTENSION_BASE_END_FY,
    CURRENT_MODEL_EXTENSION_BASE_START_FY,
    CURRENT_MODEL_EXTENSION_END_FY,
    CURRENT_MODEL_EXTENSION_START_FY,
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
    "revenue_stack_components.parquet",
    "ev_phev_split_assumptions.parquet",
    "revenue_formula_residuals.parquet",
    "series_alias_audit.parquet",
    "fan_availability.parquet",
    "fan_band_rows.parquet",
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
FAN_SOURCE_AUTO = "Auto / best available"
FAN_SOURCE_MBU26_ARCHIVED = "MBU26 archived forecast error"
FAN_SOURCE_CURRENT_BACKTEST = "Current finalist backtest error"
FAN_SOURCE_SCENARIO_SPREAD = "Scenario spread"
FAN_SOURCE_NONE = "None / governed gap"
FAN_SOURCE_OPTIONS = (
    FAN_SOURCE_AUTO,
    FAN_SOURCE_MBU26_ARCHIVED,
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_SCENARIO_SPREAD,
    FAN_SOURCE_NONE,
)
FAN_SOURCE_PRIORITY = (
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_MBU26_ARCHIVED,
    FAN_SOURCE_SCENARIO_SPREAD,
)

ARCHIVED_ERROR_BAND_LABELS = {
    "gross_ped_revenue": "PED revenue",
    "light_ruc_net_km": "Light RUC net km",
    "light_ruc_net_revenue": "Light RUC revenue",
    "heavy_ruc_net_km": "Heavy RUC net km",
    "heavy_ruc_net_revenue": "Heavy RUC revenue",
    "total_fed_ruc_net_revenue": "Total RUC+PED revenue",
}
CURRENT_BACKTEST_STREAM_MAP = {
    "ped_vkt_per_capita": ("PED", "modelled_activity", "PED finalist backtest residuals mapped directly to PED VKT per capita."),
    "light_ruc_net_km": ("LIGHT_RUC", "modelled_activity", "Light RUC finalist backtest residuals mapped directly to Light RUC net km."),
    "heavy_ruc_net_km": ("HEAVY_RUC", "modelled_activity", "Heavy RUC finalist backtest residuals mapped directly to Heavy RUC net km."),
    "gross_ped_revenue": (
        "PED",
        "partial_model_stream_only",
        "PED model uncertainty applied through the deterministic MBU26 population, intensity and rate bridge; excludes uncertainty in those bridge inputs.",
    ),
    "light_ruc_net_revenue": (
        "LIGHT_RUC",
        "partial_model_stream_only",
        "Light RUC model uncertainty applied through the deterministic MBU26 effective-rate bridge; excludes rate uncertainty.",
    ),
    "heavy_ruc_net_revenue": (
        "HEAVY_RUC",
        "partial_model_stream_only",
        "Heavy RUC model uncertainty applied through the deterministic MBU26 effective-rate bridge; excludes rate uncertainty.",
    ),
}
AGGREGATE_PROPAGATION_GAP_SERIES = {
    "gross_fed_revenue",
    "net_fed_revenue",
    "net_mvr_revenue",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
}

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
REVENUE_STACK_MODE_BRIDGE = "Gross-to-net bridge audit"
REVENUE_STACK_MODE_GROSS = "Gross contribution stack"
REVENUE_STACK_MODES = (REVENUE_STACK_MODE_BRIDGE, REVENUE_STACK_MODE_GROSS)
REVENUE_STACK_DETAIL_CLEAN = "Clean components"
REVENUE_STACK_DETAIL_FULL_FORMULA = "Full formula audit"
REVENUE_STACK_DETAIL_LEVELS = (REVENUE_STACK_DETAIL_CLEAN, REVENUE_STACK_DETAIL_FULL_FORMULA)
REVENUE_STACK_SECTION_ORDER = {
    "Key volumes": 0,
    "RUC": 1,
    "FED": 2,
    "MVR": 3,
    "TUC": 4,
    "Totals": 5,
}
REVENUE_STACK_SERIES_ORDER = {
    series_id: index
    for index, series_id in enumerate(
        [
            "light_ruc_net_km",
            CURRENT_LIGHT_TOTAL_SERIES_ID,
            "heavy_ruc_net_km",
            "light_bev_ruc_net_km",
            "heavy_bev_ruc_net_km",
            "phev_ruc_net_km",
            "ped_volume",
            "light_petrol_vkt",
            "ped_vkt_per_capita",
            "tuc_gtk",
            "light_ruc_net_revenue",
            "heavy_ruc_net_revenue",
            "light_bev_ruc_net_revenue",
            "heavy_bev_ruc_net_revenue",
            "phev_ruc_net_revenue",
            "ruc_refunds",
            "ruc_refunds_gross_addback",
            "gross_ruc_revenue",
            "ruc_admin_revenue",
            "ruc_revenue_net_admin",
            "total_ruc_net_revenue",
            "total_fed_ruc_net_revenue",
            "gross_ped_revenue",
            "gross_lpg_revenue",
            "gross_cng_revenue",
            "gross_fed_revenue",
            "fed_refunds",
            "net_fed_revenue",
            "mr1_revenue",
            "mr2_revenue",
            "coo_revenue",
            "coo_gross_mvr_addback",
            "gross_mvr_revenue",
            "mvr_admin_revenue",
            "mvr_revenue_net_admin_coo",
            "mvr_refunds",
            "net_mvr_revenue",
            "tuc_net_revenue",
            "total_gross_revenue",
            "total_admin_fees",
            "total_revenue_net_admin",
            "total_refunds",
            "total_nltf_net_revenue",
        ]
    )
}
REVENUE_STACK_DEDUCTION_SERIES = {
    "ruc_refunds",
    "ruc_admin_revenue",
    "fed_refunds",
    "coo_revenue",
    "mvr_admin_revenue",
    "mvr_refunds",
}
REVENUE_STACK_GROSS_COMPONENT_SERIES = {
    "light_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "heavy_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "ruc_refunds",
    "gross_ped_revenue",
    "gross_lpg_revenue",
    "gross_cng_revenue",
    "mr1_revenue",
    "mr2_revenue",
    "coo_revenue",
    "tuc_net_revenue",
}
REVENUE_STACK_AGGREGATE_SERIES = {
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "gross_fed_revenue",
    "net_fed_revenue",
    "gross_mvr_revenue",
    "mvr_revenue_net_admin_coo",
    "net_mvr_revenue",
    "total_gross_revenue",
    "total_admin_fees",
    "total_revenue_net_admin",
    "total_refunds",
    "total_nltf_net_revenue",
}
REVENUE_STACK_MODE_TARGET_SERIES = {
    REVENUE_STACK_MODE_BRIDGE: "total_nltf_net_revenue",
    REVENUE_STACK_MODE_GROSS: "total_gross_revenue",
}
REVENUE_STACK_BRIDGE_ADDBACKS = {
    "ruc_refunds": {
        "series_id": "ruc_refunds_gross_addback",
        "line_label": "RUC refunds gross add-back",
        "note": (
            "Gross-to-net bridge add-back: Gross RUC already includes RUC refunds, so this positive row "
            "allows the explicit refund deduction to remain visible without changing Total NLTF revenue."
        ),
    },
    "coo_revenue": {
        "series_id": "coo_gross_mvr_addback",
        "line_label": "MR13/COO gross add-back",
        "note": (
            "Gross-to-net bridge add-back: Gross MVR already includes MR13/COO, so this positive row "
            "allows the explicit MR13/COO deduction to remain visible without changing Total NLTF revenue."
        ),
    },
}
REVENUE_STACK_BRIDGE_INTERNAL_NET_ZERO_SERIES = {
    "ruc_refunds",
    "ruc_refunds_gross_addback",
    "coo_revenue",
    "coo_gross_mvr_addback",
}


@dataclass
class RevenueOutlookPack:
    output_dir: Path
    manifest: dict[str, Any]
    future_revenue_forecasts: pd.DataFrame
    revenue_bridge_components: pd.DataFrame
    revenue_chart_rows: pd.DataFrame
    revenue_line_reconciliation: pd.DataFrame = field(default_factory=pd.DataFrame)
    revenue_stack_components: pd.DataFrame = field(default_factory=pd.DataFrame)
    ev_phev_split_assumptions: pd.DataFrame = field(default_factory=pd.DataFrame)
    revenue_formula_residuals: pd.DataFrame = field(default_factory=pd.DataFrame)
    series_alias_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    fan_availability: pd.DataFrame = field(default_factory=pd.DataFrame)
    fan_band_rows: pd.DataFrame = field(default_factory=pd.DataFrame)


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
        base / "revenue_stack_components.parquet",
        base / "ev_phev_split_assumptions.parquet",
        base / "revenue_formula_residuals.parquet",
        base / "series_alias_audit.parquet",
        base / "fan_availability.parquet",
        base / "fan_band_rows.parquet",
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
        revenue_stack_components=_read_optional_parquet(base / "revenue_stack_components.parquet"),
        ev_phev_split_assumptions=_read_optional_parquet(base / "ev_phev_split_assumptions.parquet"),
        revenue_formula_residuals=_read_optional_parquet(base / "revenue_formula_residuals.parquet"),
        series_alias_audit=_read_optional_parquet(base / "series_alias_audit.parquet"),
        fan_availability=_read_optional_parquet(base / "fan_availability.parquet"),
        fan_band_rows=_read_optional_parquet(base / "fan_band_rows.parquet"),
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
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "heavy_ruc_net_km",
    "gross_ped_revenue",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
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
    stack_components = revenue_stack_components_frame(line_reconciliation, formula_residuals)
    ev_phev_split_assumptions = ev_phev_split_assumptions_frame(
        mbu26_pack.official_annual,
        current_forecast_annual=current,
        repo_root=root,
    )

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
    fan_availability, fan_band_rows = revenue_outlook_fan_tables(chart_rows, repo_root=root)

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
            "E_ev_phev_split_audit": (
                "Current finalist Light RUC is governed as the total light-RUC net-km universe. MBU26 conventional, "
                "Light BEV and PHEV shares allocate that total down before revenue rates are applied."
            ),
            "F_current_model_extension": (
                f"Current-finalist modelled streams extend FY{CURRENT_MODEL_EXTENSION_START_FY}-FY{CURRENT_MODEL_EXTENSION_END_FY} "
                f"using the linear annual gradient from FY{CURRENT_MODEL_EXTENSION_BASE_START_FY}-FY{CURRENT_MODEL_EXTENSION_BASE_END_FY}."
            ),
        },
        "period_rule": {
            "last_complete_actual_fy": REVENUE_LAST_COMPLETE_ACTUAL_FY,
            "first_forecast_quarter": REVENUE_FIRST_FORECAST_QUARTER,
            "model_training_cutoff": REVENUE_MODEL_TRAINING_CUTOFF,
            "fy2026_nowcast": "2025Q3+2025Q4 source actuals plus 2026Q1+2026Q2 current finalist forecasts",
            "rule": "Actual line ends FY2025; FY2026 actual-to-date rows are nowcast inputs only and are not plotted as actuals.",
        },
        "data_vintage_manifest_notes": {
            "light_ruc_target_semantics": (
                "Business rule: current-finalist Light RUC is treated as total light-RUC net km, then allocated "
                "into conventional Light, Light BEV and PHEV using MBU26 annual shares. BEV/PHEV are not added on top."
            )
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
            "LIGHT_RUC": "Light RUC revenue = current finalist total light-RUC net km allocated by MBU26 conventional/Light BEV/PHEV shares, then multiplied by the matching MBU26 effective rates.",
            "HEAVY_RUC": "Heavy RUC revenue = current finalist net km * MBU26 effective Heavy RUC rate.",
            "ROLLUPS": "Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate PED, allocated Light RUC, allocated Light BEV, allocated PHEV and Heavy RUC replacement lines plus MBU26 fixed components.",
        },
        "target_semantics_audit": {
            "LIGHT_RUC": _light_ruc_target_semantics_manifest(ev_phev_split_assumptions),
            "HEAVY_RUC": {
                "status": "not_reclassified",
                "decision": "Heavy BEV remains an MBU26 fixed component in current-finalist paths.",
                "rationale": "No repo-local evidence in this audit proves the Heavy RUC target includes Heavy BEV.",
            },
        },
        "ev_phev_split_assumptions": {
            "repo_relative_path": _repo_relative(root, base / "ev_phev_split_assumptions.csv"),
            "scope": (
                "MBU26 conventional Light, Light BEV and PHEV km/revenue shares and rates, with current-finalist "
                "total Light RUC allocation outputs and old fixed-add-on comparator fields."
            ),
            "allocation_status": _ev_phev_allocation_status(ev_phev_split_assumptions),
        },
        "rate_provenance": {
            "future_light_heavy": "mbu26_official_annual.csv effective rates joined to current finalist net-km outputs",
            "future_ped": "MBU26 population/intensity/rate joined to current finalist PED VKT/capita",
            "fixed_components": "mbu26_official_annual.csv official rows, excluding Light BEV and PHEV in current-finalist paths where they are allocated from current Light RUC total",
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
        "revenue_stack_components": {
            "repo_relative_path": _repo_relative(root, base / "revenue_stack_components.csv"),
            "scope": "Composition-over-time stack rows classified from revenue_line_reconciliation in gross-to-net bridge and gross-contribution modes; aggregates are overlays only and are never stacked.",
            "source": "data/current_revenue_outlook/revenue_line_reconciliation.csv",
            "composition_modes": list(REVENUE_STACK_MODES),
            "balance_rule": "Gross-to-net bridge reconciles displayed stack_value to Total NLTF revenue; gross contribution stack reconciles displayed stack_value to Total gross revenues. Residuals are reported and never forced.",
        },
        "series_alias_audit": {
            "repo_relative_path": _repo_relative(root, base / "series_alias_audit.csv"),
            "scope": "Canonical Revenue Outlook series aliases from source labels/series IDs to dashboard selector IDs.",
        },
        "fan_availability": {
            "repo_relative_path": _repo_relative(root, base / "fan_availability.csv"),
            "scope": "Per-series availability contract for Revenue Outlook fan sources, missing artifacts and interpretation.",
        },
        "fan_band_rows": {
            "repo_relative_path": _repo_relative(root, base / "fan_band_rows.csv"),
            "scope": "Hash-backed fan band rows only where archived-error, current-finalist backtest or scenario-spread evidence exists.",
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
            "series_alias_audit": mbu26_pack.series_alias_audit,
            "path_trace_status": mbu26_pack.path_trace_status,
            "row_reconciliation": mbu26_pack.row_reconciliation,
            "revenue_line_reconciliation": line_reconciliation,
            "revenue_stack_components": stack_components,
            "ev_phev_split_assumptions": ev_phev_split_assumptions,
            "revenue_formula_residuals": formula_residuals,
            "fan_availability": fan_availability,
            "fan_band_rows": fan_band_rows,
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


def ev_phev_split_assumptions_frame(
    mbu26_official_annual: pd.DataFrame,
    *,
    current_forecast_annual: pd.DataFrame | None = None,
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Audit the governed current-Light allocation into conventional, BEV and PHEV rows."""

    columns = [
        "FY",
        "period",
        "source_path",
        "scenario_name",
        "scenario_role",
        "conventional_light_km",
        "light_bev_km",
        "phev_km",
        "total_light_universe_km",
        "conventional_share",
        "light_bev_share",
        "phev_share",
        "share_sum",
        "conventional_light_revenue",
        "light_bev_revenue",
        "phev_revenue",
        "conventional_light_rate_nzd_per_1000km",
        "light_bev_rate_nzd_per_1000km",
        "phev_rate_nzd_per_1000km",
        "conventional_light_source_cell",
        "light_bev_source_cell",
        "phev_source_cell",
        "conventional_light_revenue_source_cell",
        "light_bev_revenue_source_cell",
        "phev_revenue_source_cell",
        "source_formula",
        "source_file",
        "source_status",
        "model_input_target_million_km",
        "model_input_quarters",
        "model_input_full_year",
        "target_minus_conventional_light_km",
        "target_minus_total_light_universe_km",
        "target_matches_conventional_light",
        "target_matches_total_light_universe",
        "target_semantics_status",
        "business_rule",
        "current_light_total_modelled_km",
        "current_conventional_light_km",
        "current_light_bev_km",
        "current_phev_km",
        "current_allocation_sum_km",
        "current_allocation_residual_km",
        "current_light_ruc_net_revenue",
        "current_light_bev_ruc_net_revenue",
        "current_phev_ruc_net_revenue",
        "old_light_ruc_net_revenue_no_allocation",
        "old_light_bev_ruc_net_revenue_fixed_mbu",
        "old_phev_ruc_net_revenue_fixed_mbu",
        "extrapolated_model_extension",
        "allocation_status",
        "used_by_current_finalist",
        "notes",
    ]
    if mbu26_official_annual is None or mbu26_official_annual.empty:
        return pd.DataFrame(columns=columns)

    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    official = mbu26_official_annual.copy()
    official["FY_numeric"] = pd.to_numeric(official.get("FY"), errors="coerce").astype("Int64")
    official["value_numeric"] = pd.to_numeric(official.get("value"), errors="coerce")
    official = official[official["FY_numeric"].notna()].copy()
    records: dict[tuple[int, str], dict[str, Any]] = {}
    for row in official.to_dict("records"):
        series_id = str(row.get("series_id") or "")
        if not series_id:
            continue
        key = (int(row["FY_numeric"]), series_id)
        if key not in records:
            records[key] = row

    target_history = _light_ruc_annual_target_history(root)
    target_lookup = {int(row.FY): row for row in target_history.itertuples()} if not target_history.empty else {}
    current_records: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    current_groups: set[tuple[int, str, str, str]] = set()
    if current_forecast_annual is not None and not current_forecast_annual.empty:
        current = current_forecast_annual.copy()
        current["FY_numeric"] = pd.to_numeric(current.get("FY"), errors="coerce").astype("Int64")
        current["value_numeric"] = pd.to_numeric(current.get("value"), errors="coerce")
        current = current[current["FY_numeric"].notna()].copy()
        for row in current.to_dict("records"):
            fy = int(row["FY_numeric"])
            source_path = str(row.get("source_path") or _current_source_path_label(str(row.get("scenario_name") or ""), str(row.get("scenario_role") or "")))
            scenario_name = str(row.get("scenario_name") or "")
            scenario_role = str(row.get("scenario_role") or "")
            series_id = str(row.get("series_id") or "")
            if not series_id or not source_path.startswith("Current finalist"):
                continue
            current_records[(fy, source_path, scenario_name, series_id)] = row
            current_groups.add((fy, source_path, scenario_name, scenario_role))

    rows: list[dict[str, Any]] = []
    for fy in sorted({key[0] for key in records}):
        conv = _record_value(records, fy, "light_ruc_net_km")
        bev = _record_value(records, fy, "light_bev_ruc_net_km")
        phev = _record_value(records, fy, "phev_ruc_net_km")
        conv_rev = _record_value(records, fy, "light_ruc_net_revenue")
        bev_rev = _record_value(records, fy, "light_bev_ruc_net_revenue")
        phev_rev = _record_value(records, fy, "phev_ruc_net_revenue")
        total = _sum_if_all_present(conv, bev, phev)
        target_row = target_lookup.get(int(fy))
        target = getattr(target_row, "target_million_km", pd.NA) if target_row is not None else pd.NA
        target_quarters = getattr(target_row, "quarters_present", "") if target_row is not None else ""
        full_year = bool(getattr(target_row, "model_input_full_year", False)) if target_row is not None else False
        diff_conventional = _subtract_if_present(target, conv)
        diff_universe = _subtract_if_present(target, total)
        matches_conventional = _values_close(target, conv) if full_year else False
        matches_universe = _values_close(target, total) if full_year else False
        target_status = _light_target_row_status(
            full_year=full_year,
            light_bev_km=bev,
            phev_km=phev,
            matches_conventional=matches_conventional,
            matches_universe=matches_universe,
        )
        conventional_share = _divide_if_present(conv, total)
        light_bev_share = _divide_if_present(bev, total)
        phev_share = _divide_if_present(phev, total)
        share_sum = _sum_if_all_present(conventional_share, light_bev_share, phev_share)
        official_payload = {
            "FY": int(fy),
            "period": f"FY{int(fy)}",
            "conventional_light_km": conv,
            "light_bev_km": bev,
            "phev_km": phev,
            "total_light_universe_km": total,
            "conventional_share": conventional_share,
            "light_bev_share": light_bev_share,
            "phev_share": phev_share,
            "share_sum": share_sum,
            "conventional_light_revenue": conv_rev,
            "light_bev_revenue": bev_rev,
            "phev_revenue": phev_rev,
            "conventional_light_rate_nzd_per_1000km": _rate_per_1000km(conv_rev, conv),
            "light_bev_rate_nzd_per_1000km": _rate_per_1000km(bev_rev, bev),
            "phev_rate_nzd_per_1000km": _rate_per_1000km(phev_rev, phev),
            "conventional_light_source_cell": _record_text(records, fy, "light_ruc_net_km", "source_cell"),
            "light_bev_source_cell": _record_text(records, fy, "light_bev_ruc_net_km", "source_cell"),
            "phev_source_cell": _record_text(records, fy, "phev_ruc_net_km", "source_cell"),
            "conventional_light_revenue_source_cell": _record_text(records, fy, "light_ruc_net_revenue", "source_cell"),
            "light_bev_revenue_source_cell": _record_text(records, fy, "light_bev_ruc_net_revenue", "source_cell"),
            "phev_revenue_source_cell": _record_text(records, fy, "phev_ruc_net_revenue", "source_cell"),
            "source_formula": "; ".join(
                item
                for item in [
                    _record_text(records, fy, "light_ruc_net_km", "formula"),
                    _record_text(records, fy, "light_bev_ruc_net_km", "formula"),
                    _record_text(records, fy, "phev_ruc_net_km", "formula"),
                ]
                if item
            ),
            "source_file": "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_annual_spine.csv",
            "source_status": _record_text(records, fy, "light_ruc_net_km", "period_status"),
            "model_input_target_million_km": target,
            "model_input_quarters": target_quarters,
            "model_input_full_year": full_year,
            "target_minus_conventional_light_km": diff_conventional,
            "target_minus_total_light_universe_km": diff_universe,
            "target_matches_conventional_light": bool(matches_conventional),
            "target_matches_total_light_universe": bool(matches_universe),
            "target_semantics_status": target_status,
            "business_rule": "current_light_ruc_total_allocated_by_mbu26_conventional_bev_phev_shares",
        }
        fy_groups = sorted(group for group in current_groups if group[0] == int(fy))
        if not fy_groups:
            rows.append(
                {
                    **official_payload,
                    "source_path": "",
                    "scenario_name": "",
                    "scenario_role": "",
                    "current_light_total_modelled_km": pd.NA,
                    "current_conventional_light_km": pd.NA,
                    "current_light_bev_km": pd.NA,
                    "current_phev_km": pd.NA,
                    "current_allocation_sum_km": pd.NA,
                    "current_allocation_residual_km": pd.NA,
                    "current_light_ruc_net_revenue": pd.NA,
                    "current_light_bev_ruc_net_revenue": pd.NA,
                    "current_phev_ruc_net_revenue": pd.NA,
                    "old_light_ruc_net_revenue_no_allocation": pd.NA,
                    "old_light_bev_ruc_net_revenue_fixed_mbu": bev_rev,
                    "old_phev_ruc_net_revenue_fixed_mbu": phev_rev,
                    "extrapolated_model_extension": False,
                    "allocation_status": "business_rule_ready_no_current_forecast_row",
                    "used_by_current_finalist": False,
                    "notes": "MBU26 split/rate row is available; no current-finalist Light RUC row exists for this FY/scenario.",
                }
            )
            continue
        for _, source_path, scenario_name, scenario_role in fy_groups:
            key_prefix = (int(fy), source_path, scenario_name)
            total_current = _current_record_value(current_records, key_prefix, CURRENT_LIGHT_TOTAL_SERIES_ID)
            current_conv = _current_record_value(current_records, key_prefix, "light_ruc_net_km")
            current_bev = _current_record_value(current_records, key_prefix, "light_bev_ruc_net_km")
            current_phev = _current_record_value(current_records, key_prefix, "phev_ruc_net_km")
            current_sum = _sum_if_all_present(current_conv, current_bev, current_phev)
            current_residual = _subtract_if_present(total_current, current_sum)
            current_light_revenue = _current_record_value(current_records, key_prefix, "light_ruc_net_revenue")
            current_bev_revenue = _current_record_value(current_records, key_prefix, "light_bev_ruc_net_revenue")
            current_phev_revenue = _current_record_value(current_records, key_prefix, "phev_ruc_net_revenue")
            old_light_revenue = _multiply_if_present(total_current, _divide_if_present(conv_rev, conv))
            status_values = [
                str(current_records.get((*key_prefix, series_id), {}).get("value_status") or "")
                for series_id in [CURRENT_LIGHT_TOTAL_SERIES_ID, "light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]
            ]
            rows.append(
                {
                    **official_payload,
                    "source_path": source_path,
                    "scenario_name": scenario_name,
                    "scenario_role": scenario_role,
                    "current_light_total_modelled_km": total_current,
                    "current_conventional_light_km": current_conv,
                    "current_light_bev_km": current_bev,
                    "current_phev_km": current_phev,
                    "current_allocation_sum_km": current_sum,
                    "current_allocation_residual_km": current_residual,
                    "current_light_ruc_net_revenue": current_light_revenue,
                    "current_light_bev_ruc_net_revenue": current_bev_revenue,
                    "current_phev_ruc_net_revenue": current_phev_revenue,
                    "old_light_ruc_net_revenue_no_allocation": old_light_revenue,
                    "old_light_bev_ruc_net_revenue_fixed_mbu": bev_rev,
                    "old_phev_ruc_net_revenue_fixed_mbu": phev_rev,
                    "extrapolated_model_extension": any(value == "extrapolated_model_extension" for value in status_values),
                    "allocation_status": "business_rule_applied_total_light_universe",
                    "used_by_current_finalist": True,
                    "notes": (
                        "Current finalist Light RUC total modelled km is allocated down by MBU26 conventional, "
                        "Light BEV and PHEV shares. BEV/PHEV are replacement allocations, not fixed add-ons."
                    ),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _light_ruc_annual_target_history(root: Path) -> pd.DataFrame:
    columns = ["FY", "target_million_km", "quarters_present", "model_input_full_year"]
    path = root / MODEL_INPUT_HISTORY_DIR / MODEL_INPUT_HISTORY_FILES["LIGHT_RUC"]
    if not path.exists():
        return pd.DataFrame(columns=columns)
    history = _read_optional_parquet(path)
    if history.empty:
        return pd.DataFrame(columns=columns)
    data = history.copy()
    data["year_numeric"] = pd.to_numeric(data.get("year"), errors="coerce").astype("Int64")
    data["quarter_numeric"] = pd.to_numeric(data.get("quarter"), errors="coerce").astype("Int64")
    data["target_numeric"] = pd.to_numeric(data.get("target"), errors="coerce")
    data = data[data["year_numeric"].notna() & data["quarter_numeric"].notna()].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["FY"] = data["year_numeric"].astype(int) + data["quarter_numeric"].isin([3, 4]).astype(int)
    data["period_text"] = data.get("period", pd.Series("", index=data.index)).astype(str)
    rows: list[dict[str, Any]] = []
    for fy, group in data.groupby("FY", dropna=False):
        targets = pd.to_numeric(group.get("target_numeric"), errors="coerce")
        positive_targets = targets[targets.gt(0)]
        periods = sorted(group["period_text"].dropna().astype(str).tolist(), key=quarter_sort_key)
        full_year = len(group) == 4 and len(positive_targets) == 4
        rows.append(
            {
                "FY": int(fy),
                "target_million_km": float(positive_targets.sum() / 1_000_000.0) if len(positive_targets) else pd.NA,
                "quarters_present": "; ".join(periods),
                "model_input_full_year": bool(full_year),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _light_ruc_target_semantics_manifest(audit: pd.DataFrame) -> dict[str, Any]:
    if audit is None or audit.empty:
        return {
            "status": "business_rule_pending_audit_rows",
            "decision": "Apply the governed total-light allocation when current rows are available.",
            "rationale": "No ev_phev_split_assumptions audit rows were available.",
        }
    applied = audit[
        audit.get("allocation_status", pd.Series("", index=audit.index)).astype(str).eq("business_rule_applied_total_light_universe")
    ].copy()
    evidence = audit[
        audit.get("model_input_full_year", pd.Series(False, index=audit.index)).astype(bool)
        & (
            pd.to_numeric(audit.get("light_bev_km"), errors="coerce").fillna(0).gt(0)
            | pd.to_numeric(audit.get("phev_km"), errors="coerce").fillna(0).gt(0)
        )
    ].copy()
    status_counts = (
        {str(key): int(value) for key, value in evidence["target_semantics_status"].astype(str).value_counts().to_dict().items()}
        if not evidence.empty and "target_semantics_status" in evidence.columns
        else {}
    )
    matches_conventional = int(evidence["target_matches_conventional_light"].astype(bool).sum()) if "target_matches_conventional_light" in evidence.columns else 0
    matches_universe = int(evidence["target_matches_total_light_universe"].astype(bool).sum()) if "target_matches_total_light_universe" in evidence.columns else 0
    years = [int(value) for value in pd.to_numeric(evidence.get("FY", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).tolist()]
    max_universe_residual = pd.to_numeric(evidence.get("target_minus_total_light_universe_km", pd.Series(dtype=float)), errors="coerce").abs().max()
    allocation_years = [int(value) for value in pd.to_numeric(applied.get("FY", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).unique().tolist()]
    return {
        "status": "business_rule_applied_total_light_universe",
        "decision": "Allocate current finalist Light RUC total modelled km into conventional Light, Light BEV and PHEV using MBU26 shares.",
        "evidence_years": years,
        "allocation_years": allocation_years,
        "matches_conventional_light_rows": matches_conventional,
        "matches_total_light_universe_rows": matches_universe,
        "status_counts": status_counts,
        "max_abs_target_minus_total_light_universe_km": float(max_universe_residual) if pd.notna(max_universe_residual) else None,
        "repo_evidence": [
            "data/model_input_history/light_ruc_inputs.parquet",
            "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_annual_spine.csv",
        ],
        "rationale": (
            "The current governed business rule treats Light RUC finalist output as the total light-RUC universe. "
            "The audit preserves prior model-input target evidence and records the allocation rows used by the runtime."
        ),
    }


def _ev_phev_allocation_status(audit: pd.DataFrame) -> str:
    if audit is None or audit.empty or "allocation_status" not in audit.columns:
        return "business_rule_pending_audit_rows"
    statuses = set(audit["allocation_status"].dropna().astype(str))
    if "business_rule_applied_total_light_universe" in statuses:
        return "business_rule_applied_total_light_universe"
    if statuses:
        return sorted(statuses)[0]
    return "business_rule_pending_audit_rows"


def _record_value(records: dict[tuple[int, str], dict[str, Any]], fy: int, series_id: str) -> Any:
    value = records.get((int(fy), series_id), {}).get("value_numeric")
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else pd.NA


def _current_record_value(records: dict[tuple[int, str, str, str], dict[str, Any]], key_prefix: tuple[int, str, str], series_id: str) -> Any:
    value = records.get((*key_prefix, series_id), {}).get("value_numeric")
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else pd.NA


def _record_text(records: dict[tuple[int, str], dict[str, Any]], fy: int, series_id: str, column: str) -> str:
    value = records.get((int(fy), series_id), {}).get(column, "")
    return "" if pd.isna(value) else str(value)


def _sum_if_all_present(*values: Any) -> Any:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    if numeric.isna().any():
        return pd.NA
    return float(numeric.sum())


def _multiply_if_present(left: Any, right: Any) -> Any:
    numeric = pd.to_numeric(pd.Series([left, right]), errors="coerce")
    if numeric.isna().any():
        return pd.NA
    return float(numeric.iloc[0] * numeric.iloc[1])


def _subtract_if_present(left: Any, right: Any) -> Any:
    numeric = pd.to_numeric(pd.Series([left, right]), errors="coerce")
    if numeric.isna().any():
        return pd.NA
    return float(numeric.iloc[0] - numeric.iloc[1])


def _divide_if_present(numerator: Any, denominator: Any) -> Any:
    numeric = pd.to_numeric(pd.Series([numerator, denominator]), errors="coerce")
    if numeric.isna().any() or abs(float(numeric.iloc[1])) < 1e-12:
        return pd.NA
    return float(numeric.iloc[0] / numeric.iloc[1])


def _rate_per_1000km(revenue_million: Any, km_million: Any) -> Any:
    rate = _divide_if_present(revenue_million, km_million)
    return float(rate * 1000.0) if pd.notna(rate) else pd.NA


def _values_close(left: Any, right: Any, *, abs_tol: float = 1e-6, rel_tol: float = 1e-9) -> bool:
    numeric = pd.to_numeric(pd.Series([left, right]), errors="coerce")
    if numeric.isna().any():
        return False
    a = float(numeric.iloc[0])
    b = float(numeric.iloc[1])
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b), 1.0))


def _light_target_row_status(
    *,
    full_year: bool,
    light_bev_km: Any,
    phev_km: Any,
    matches_conventional: bool,
    matches_universe: bool,
) -> str:
    if not full_year:
        return "model_input_full_year_missing"
    ev_total = pd.to_numeric(pd.Series([light_bev_km, phev_km]), errors="coerce").fillna(0).sum()
    if float(ev_total) <= 0:
        return "pre_ev_phev_or_zero_split_overlap"
    if matches_conventional and not matches_universe:
        return "matches_conventional_light_not_total_universe"
    if matches_universe:
        return "matches_total_light_universe"
    return "target_semantics_mismatch_unresolved"


def revenue_stack_components_frame(
    line_reconciliation: pd.DataFrame,
    formula_residuals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Classify committed line-reconciliation rows for composition plotting.

    The returned frame intentionally carries two charting modes over the same
    source values. The bridge mode reconciles displayed gross components,
    add-backs and deductions to Total NLTF revenue; the gross mode stacks only
    leaf rows that reconcile to Total gross revenues. Aggregate rows remain
    table/overlay rows and are never stacked bars.
    """

    base_columns = list(line_reconciliation.columns) if isinstance(line_reconciliation, pd.DataFrame) else []
    audit_columns = [
        "composition_mode",
        "composition_mode_order",
        "stack_role",
        "formula_role",
        "raw_value",
        "signed_contribution",
        "stack_value",
        "stack_value_clean",
        "clean_stack_value",
        "chart_visible",
        "legend_visible",
        "net_effect_group",
        "stack_unit",
        "section_order",
        "line_order",
        "source_path_order",
        "stack_balance_value",
        "stack_balance_residual",
        "stack_balance_status",
        "stack_total_by_FY",
        "overlay_total_value",
        "overlay_series_id",
        "overlay_label",
        "stack_overlay_residual",
        "stack_overlay_status",
        "clean_stack_total_by_FY",
        "clean_overlay_total_value",
        "clean_overlay_residual",
        "clean_overlay_status",
        "stack_note",
        "formula_residual",
        "formula_residual_abs",
        "formula_residual_status",
    ]
    if line_reconciliation is None or line_reconciliation.empty:
        return pd.DataFrame(columns=base_columns + audit_columns)

    base = line_reconciliation.copy()
    for column in ["source_path", "FY", "series_id", "section", "row_role", "unit", "value"]:
        if column not in base.columns:
            base[column] = pd.NA
    base = _append_total_fed_ruc_overlay_rows(base)
    base = _extend_current_stack_actual_history(base)

    base["FY_numeric"] = pd.to_numeric(base["FY"], errors="coerce")
    base["section_order"] = base["section"].astype(str).map(REVENUE_STACK_SECTION_ORDER).fillna(99).astype(int)
    base["line_order"] = base["series_id"].astype(str).map(REVENUE_STACK_SERIES_ORDER).fillna(999).astype(int)
    source_order = {
        "MBU26 official": 0,
        "Current finalist Base case": 1,
        "Current finalist High population/comparison": 2,
    }
    base["source_path_order"] = base["source_path"].astype(str).map(source_order).fillna(99).astype(int)
    base["value_numeric"] = pd.to_numeric(base["value"], errors="coerce")

    frames = [
        _revenue_stack_mode_frame(base, mode=mode, mode_order=order)
        for order, mode in enumerate(REVENUE_STACK_MODES)
    ]
    out = pd.concat(frames, ignore_index=True, sort=False)

    if isinstance(formula_residuals, pd.DataFrame) and not formula_residuals.empty:
        residual_cols = [
            "source_path",
            "FY",
            "output_series_id",
            "residual",
            "residual_abs",
            "status",
        ]
        available = [col for col in residual_cols if col in formula_residuals.columns]
        if {"source_path", "FY", "output_series_id"}.issubset(available):
            residual_view = formula_residuals[available].copy()
            residual_view["FY_numeric"] = pd.to_numeric(residual_view["FY"], errors="coerce")
            residual_view = residual_view.rename(
                columns={
                    "output_series_id": "series_id",
                    "residual": "formula_residual",
                    "residual_abs": "formula_residual_abs",
                    "status": "formula_residual_status",
                }
            ).drop(columns=["FY"], errors="ignore")
            out = out.merge(residual_view, on=["source_path", "FY_numeric", "series_id"], how="left")

    for column in ["formula_residual", "formula_residual_abs", "formula_residual_status"]:
        if column not in out.columns:
            out[column] = pd.NA

    out = out.sort_values(
        ["source_path_order", "composition_mode_order", "FY_numeric", "section_order", "line_order", "series_id"],
        kind="stable",
    )
    return out.drop(columns=["FY_numeric", "value_numeric"], errors="ignore").reset_index(drop=True)


def _extend_current_stack_actual_history(base: pd.DataFrame) -> pd.DataFrame:
    """Copy MBU26 actual line rows into current finalist composition paths.

    Current finalist forecasts only begin in the source reconciliation around
    the actual anchor. Composition charts need a continuous history; the
    historical rows are copied from the repo-local MBU26 actual spine and are
    marked as actual anchors rather than model replacements.
    """

    if base is None or base.empty or {"source_path", "FY"}.difference(base.columns):
        return base

    data = base.copy()
    data["FY_numeric"] = pd.to_numeric(data["FY"], errors="coerce")
    current_sources = [
        "Current finalist Base case",
        "Current finalist High population/comparison",
    ]
    available_current_sources = [source for source in current_sources if data["source_path"].astype(str).eq(source).any()]
    if not available_current_sources:
        return data.drop(columns=["FY_numeric"], errors="ignore")

    actual_rows = data[
        data["source_path"].astype(str).eq("MBU26 official")
        & data["FY_numeric"].le(REVENUE_LAST_COMPLETE_ACTUAL_FY)
    ].copy()
    if actual_rows.empty:
        return data.drop(columns=["FY_numeric"], errors="ignore")

    history_frames: list[pd.DataFrame] = []
    for source_path in available_current_sources:
        source_rows = data[data["source_path"].astype(str).eq(source_path)].copy()
        metadata = source_rows.sort_values("FY_numeric", kind="stable").head(1)
        scenario_name = str(metadata["scenario_name"].iloc[0]) if "scenario_name" in metadata and not metadata.empty else ""
        scenario_role = str(metadata["scenario_role"].iloc[0]) if "scenario_role" in metadata and not metadata.empty else ""
        fed_path = str(metadata["fed_path"].iloc[0]) if "fed_path" in metadata and not metadata.empty else ""

        history = actual_rows.copy()
        history["source_path"] = source_path
        history["scenario_name"] = scenario_name
        history["scenario_role"] = scenario_role
        history["fed_path"] = fed_path
        history["source_basis"] = "MBU26 actual anchor"
        history["model_id"] = ""
        history["replacement_flag"] = False
        history["forecast_quarters"] = ""
        history["value_status"] = "Actual anchor"
        history["residual_vs_official"] = 0.0
        history_frames.append(history)

    future_current = data[
        ~(
            data["source_path"].astype(str).isin(available_current_sources)
            & data["FY_numeric"].le(REVENUE_LAST_COMPLETE_ACTUAL_FY)
        )
    ].copy()
    extended = pd.concat([future_current, *history_frames], ignore_index=True, sort=False)
    return extended.drop(columns=["FY_numeric"], errors="ignore")


def _revenue_stack_mode_frame(base: pd.DataFrame, *, mode: str, mode_order: int) -> pd.DataFrame:
    out = base.copy()
    out["composition_mode"] = mode
    out["composition_mode_order"] = mode_order

    series = out["series_id"].astype(str)
    row_role = out["row_role"].astype(str)
    section = out["section"].astype(str)
    unit = out["unit"].astype(str)
    revenue_unit = unit.eq("$m nominal ex GST")
    aggregate = row_role.isin(["aggregate", "calculated_rollup"]) | series.isin(REVENUE_STACK_AGGREGATE_SERIES)
    gross_component = series.isin(REVENUE_STACK_GROSS_COMPONENT_SERIES) & revenue_unit & ~aggregate
    deduction_component = series.isin(REVENUE_STACK_DEDUCTION_SERIES) & revenue_unit & ~aggregate

    out["stack_role"] = "audit_context"
    out["formula_role"] = "audit_context"
    out.loc[row_role.eq("bridge_input") | section.eq("Key volumes"), "stack_role"] = "activity_context"
    out.loc[row_role.eq("bridge_input") | section.eq("Key volumes"), "formula_role"] = "activity_context"
    out.loc[aggregate, "stack_role"] = "aggregate_overlay"
    out.loc[aggregate, "formula_role"] = "aggregate_overlay"

    if mode == REVENUE_STACK_MODE_GROSS:
        out.loc[gross_component, "stack_role"] = "component_positive"
        out.loc[gross_component, "formula_role"] = "gross_component"
        out.loc[series.eq("ruc_refunds") & revenue_unit & ~aggregate, "formula_role"] = "ruc_gross_refund_component"
        out.loc[series.eq("coo_revenue") & revenue_unit & ~aggregate, "formula_role"] = "mvr_gross_coo_component"
    elif mode == REVENUE_STACK_MODE_BRIDGE:
        bridge_gross_component = gross_component & ~series.isin(REVENUE_STACK_BRIDGE_ADDBACKS)
        out.loc[bridge_gross_component, "stack_role"] = "component_positive"
        out.loc[bridge_gross_component, "formula_role"] = "gross_component"
        out.loc[deduction_component, "stack_role"] = "component_negative"
        out.loc[deduction_component, "formula_role"] = "deduction"
        out.loc[series.eq("coo_revenue") & deduction_component, "formula_role"] = "admin_coo_deduction"
        out.loc[series.eq("ruc_refunds") & deduction_component, "formula_role"] = "refund_deduction"
        addback_rows = _revenue_stack_bridge_addback_rows(out)
        if not addback_rows.empty:
            out = pd.concat([out, addback_rows], ignore_index=True, sort=False)
    else:
        out["stack_note"] = f"Unsupported composition mode: {mode}"

    out["signed_contribution"] = pd.NA
    positive = out["stack_role"].eq("component_positive")
    negative = out["stack_role"].eq("component_negative")
    out.loc[positive, "signed_contribution"] = out.loc[positive, "value_numeric"]
    out.loc[negative, "signed_contribution"] = -out.loc[negative, "value_numeric"]
    out["signed_contribution"] = pd.to_numeric(out["signed_contribution"], errors="coerce")

    out["stack_value"] = pd.NA
    out.loc[positive | negative, "stack_value"] = out.loc[
        positive | negative,
        "signed_contribution",
    ]
    out["stack_value"] = pd.to_numeric(out["stack_value"], errors="coerce")
    out["raw_value"] = out["value_numeric"]
    out["stack_value_clean"] = out["stack_value"]
    out["chart_visible"] = out["stack_role"].isin(["component_positive", "component_negative"])
    out["legend_visible"] = out["chart_visible"]
    out["net_effect_group"] = out["series_id"].astype(str)
    if mode == REVENUE_STACK_MODE_BRIDGE:
        internal_net_zero = out["series_id"].astype(str).isin(REVENUE_STACK_BRIDGE_INTERNAL_NET_ZERO_SERIES)
        out.loc[internal_net_zero, "stack_value_clean"] = 0.0
        out.loc[internal_net_zero, "chart_visible"] = False
        out.loc[internal_net_zero, "legend_visible"] = False
        out.loc[out["series_id"].astype(str).isin(["ruc_refunds", "ruc_refunds_gross_addback"]), "net_effect_group"] = "ruc_refunds_internal_zero_net_pair"
        out.loc[out["series_id"].astype(str).isin(["coo_revenue", "coo_gross_mvr_addback"]), "net_effect_group"] = "mvr_mr13_coo_internal_zero_net_pair"
    out["clean_stack_value"] = pd.to_numeric(out["stack_value_clean"], errors="coerce")
    out["chart_visible"] = out["chart_visible"].fillna(False).astype(bool)
    out["legend_visible"] = out["legend_visible"].fillna(False).astype(bool)
    out["stack_unit"] = out["unit"].where(out["stack_role"].isin(["component_positive", "component_negative"]), "")
    if "stack_note" not in out.columns:
        out["stack_note"] = ""
    out["stack_note"] = out["stack_note"].fillna("").astype(str)
    series = out["series_id"].astype(str)
    out.loc[series.eq("coo_revenue"), "line_label"] = "MR13/COO"
    if mode == REVENUE_STACK_MODE_GROSS:
        out.loc[series.eq("coo_revenue"), "stack_note"] = "MR13/COO is part of MBU26 Gross MVR and therefore part of Total gross revenues."
        out.loc[series.eq("ruc_refunds"), "stack_note"] = "RUC refunds are included in MBU26 Gross RUC and therefore part of Total gross revenues."
    elif mode == REVENUE_STACK_MODE_BRIDGE:
        out.loc[series.eq("coo_revenue"), "stack_note"] = (
            "MR13/COO is present in Gross MVR and Total admin fees; the bridge shows the gross add-back and the signed admin/COO deduction."
        )
        out.loc[series.eq("ruc_refunds"), "stack_note"] = (
            "RUC refunds are present in Gross RUC and Total refunds; the bridge shows the gross add-back and the signed refund deduction."
        )
    out_series = out["series_id"].astype(str)
    for addback in REVENUE_STACK_BRIDGE_ADDBACKS.values():
        out.loc[out_series.eq(str(addback["series_id"])), "stack_note"] = str(addback["note"])

    component_mask = out["stack_role"].isin(["component_positive", "component_negative"])
    stack_totals = (
        out.loc[component_mask]
        .groupby(["source_path", "composition_mode", "FY_numeric"], dropna=False)["stack_value"]
        .sum(min_count=1)
        .rename("stack_total_by_FY")
        .reset_index()
    )
    target_series_id = REVENUE_STACK_MODE_TARGET_SERIES.get(mode, "total_nltf_net_revenue")
    target_rows = out[out["series_id"].astype(str).eq(target_series_id)][
        ["source_path", "composition_mode", "FY_numeric", "series_id", "line_label", "value_numeric"]
    ].rename(
        columns={
            "series_id": "overlay_series_id",
            "line_label": "overlay_label",
            "value_numeric": "overlay_total_value",
        }
    )
    stack_totals = stack_totals.merge(target_rows, on=["source_path", "composition_mode", "FY_numeric"], how="left")
    stack_totals["stack_overlay_residual"] = (
        pd.to_numeric(stack_totals["stack_total_by_FY"], errors="coerce")
        - pd.to_numeric(stack_totals["overlay_total_value"], errors="coerce")
    )
    stack_totals["stack_overlay_status"] = np.where(
        pd.to_numeric(stack_totals["stack_overlay_residual"], errors="coerce").abs().le(1.0),
        "balanced",
        "residual_reported",
    )
    stack_totals["stack_balance_value"] = stack_totals["stack_total_by_FY"]
    stack_totals["stack_balance_residual"] = stack_totals["stack_overlay_residual"]
    stack_totals["stack_balance_status"] = stack_totals["stack_overlay_status"]
    clean_component_mask = component_mask & out["chart_visible"].fillna(False)
    clean_totals = (
        out.loc[clean_component_mask]
        .groupby(["source_path", "composition_mode", "FY_numeric"], dropna=False)["clean_stack_value"]
        .sum(min_count=1)
        .rename("clean_stack_total_by_FY")
        .reset_index()
    )
    clean_totals = clean_totals.merge(
        target_rows.rename(columns={"overlay_total_value": "clean_overlay_total_value"})[
            ["source_path", "composition_mode", "FY_numeric", "clean_overlay_total_value"]
        ],
        on=["source_path", "composition_mode", "FY_numeric"],
        how="left",
    )
    clean_totals["clean_overlay_residual"] = (
        pd.to_numeric(clean_totals["clean_stack_total_by_FY"], errors="coerce")
        - pd.to_numeric(clean_totals["clean_overlay_total_value"], errors="coerce")
    )
    clean_totals["clean_overlay_status"] = np.where(
        pd.to_numeric(clean_totals["clean_overlay_residual"], errors="coerce").abs().le(1.0),
        "balanced",
        "residual_reported",
    )
    out = out.merge(
        stack_totals[
            [
                "source_path",
                "composition_mode",
                "FY_numeric",
                "stack_balance_value",
                "stack_balance_residual",
                "stack_balance_status",
                "stack_total_by_FY",
                "overlay_total_value",
                "overlay_series_id",
                "overlay_label",
                "stack_overlay_residual",
                "stack_overlay_status",
            ]
        ],
        on=["source_path", "composition_mode", "FY_numeric"],
        how="left",
    )
    out = out.merge(
        clean_totals[
            [
                "source_path",
                "composition_mode",
                "FY_numeric",
                "clean_stack_total_by_FY",
                "clean_overlay_total_value",
                "clean_overlay_residual",
                "clean_overlay_status",
            ]
        ],
        on=["source_path", "composition_mode", "FY_numeric"],
        how="left",
    )
    return out


def _revenue_stack_bridge_addback_rows(mode_frame: pd.DataFrame) -> pd.DataFrame:
    addbacks = mode_frame[mode_frame["series_id"].astype(str).isin(REVENUE_STACK_BRIDGE_ADDBACKS)].copy()
    if addbacks.empty:
        return pd.DataFrame(columns=mode_frame.columns)
    addbacks["original_series_id"] = addbacks["series_id"].astype(str)
    addbacks["series_id"] = addbacks["original_series_id"].map(
        {key: value["series_id"] for key, value in REVENUE_STACK_BRIDGE_ADDBACKS.items()}
    )
    addbacks["line_label"] = addbacks["original_series_id"].map(
        {key: value["line_label"] for key, value in REVENUE_STACK_BRIDGE_ADDBACKS.items()}
    )
    addbacks["row_role"] = "bridge_addback"
    addbacks["stack_role"] = "component_positive"
    addbacks["formula_role"] = "gross_addback"
    addbacks["line_order"] = addbacks["series_id"].astype(str).map(REVENUE_STACK_SERIES_ORDER).fillna(998).astype(int)
    addbacks["source_status"] = "derived_bridge_addback"
    addbacks["source_basis"] = "runtime_bridge_audit"
    addbacks["source_cell"] = addbacks["source_cell"].astype(str).where(addbacks["source_cell"].notna(), "")
    addbacks["formula"] = addbacks["original_series_id"].map(
        {key: value["note"] for key, value in REVENUE_STACK_BRIDGE_ADDBACKS.items()}
    )
    addbacks["stack_note"] = addbacks["formula"]
    addbacks["replacement_flag"] = False
    addbacks["residual_vs_official"] = pd.NA
    addbacks["value_numeric"] = pd.to_numeric(addbacks["value_numeric"], errors="coerce")
    addbacks["value"] = addbacks["value_numeric"]
    return addbacks.drop(columns=["original_series_id"], errors="ignore")


def _append_total_fed_ruc_overlay_rows(line_reconciliation: pd.DataFrame) -> pd.DataFrame:
    if line_reconciliation is None or line_reconciliation.empty:
        return pd.DataFrame() if line_reconciliation is None else line_reconciliation
    required = {"source_path", "FY", "series_id", "value"}
    if required.difference(line_reconciliation.columns):
        return line_reconciliation

    rows: list[dict[str, Any]] = []
    for _, group in line_reconciliation.groupby(["source_path", "FY"], dropna=False, sort=False):
        by_series = group.drop_duplicates("series_id", keep="last").set_index("series_id", drop=False)
        if "net_fed_revenue" not in by_series.index or "total_ruc_net_revenue" not in by_series.index:
            continue
        if "total_fed_ruc_net_revenue" in by_series.index:
            continue
        net_fed = pd.to_numeric(pd.Series([by_series.loc["net_fed_revenue", "value"]]), errors="coerce").iloc[0]
        total_ruc = pd.to_numeric(pd.Series([by_series.loc["total_ruc_net_revenue", "value"]]), errors="coerce").iloc[0]
        if pd.isna(net_fed) or pd.isna(total_ruc):
            continue
        template_key = "total_nltf_net_revenue" if "total_nltf_net_revenue" in by_series.index else "net_fed_revenue"
        record = by_series.loc[template_key].to_dict()
        record.update(
            {
                "section": "Totals",
                "line_label": "Total RUC+PED",
                "series_id": "total_fed_ruc_net_revenue",
                "value": float(net_fed) + float(total_ruc),
                "unit": "$m nominal ex GST",
                "row_role": "calculated_rollup",
                "source_file": "revenue_line_reconciliation.csv",
                "source_cell": "net_fed_revenue + total_ruc_net_revenue",
                "formula": "net_fed_revenue + total_ruc_net_revenue",
                "source_status": "derived_dashboard_subtotal",
                "source_basis": "runtime_formula_overlay",
                "residual_vs_official": pd.NA,
                "availability_status": "available",
            }
        )
        rows.append(record)
    if not rows:
        return line_reconciliation
    return pd.concat([line_reconciliation, pd.DataFrame(rows)], ignore_index=True, sort=False)


def revenue_outlook_fan_tables(
    chart_rows: pd.DataFrame,
    *,
    repo_root: Path | str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build source-explicit Revenue Outlook fan availability and band rows."""

    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    series = _fan_display_series_frame(chart_rows)
    band_frames = [
        _mbu26_archived_fan_band_rows(chart_rows, root),
        _current_finalist_backtest_fan_band_rows(chart_rows, root),
        _scenario_spread_fan_band_rows(chart_rows),
    ]
    non_empty_band_frames = [frame for frame in band_frames if frame is not None and not frame.empty]
    if not non_empty_band_frames:
        bands = pd.DataFrame(columns=_fan_band_columns())
    else:
        bands = pd.concat(non_empty_band_frames, ignore_index=True, sort=False)
        bands = bands.reindex(columns=_fan_band_columns())
        bands["_series_order"] = bands["series_id"].map(_series_order_index)
        bands["_source_order"] = bands["fan_source"].map(_fan_source_order_index)
        bands["_fy_order"] = pd.to_numeric(bands["FY"], errors="coerce")
        bands = bands.sort_values(["_series_order", "_source_order", "_fy_order", "period", "scenario_name"], kind="stable").drop(
            columns=["_series_order", "_source_order", "_fy_order"]
        )
    availability = _fan_availability_frame(series, bands)
    return availability, bands


def _fan_band_columns() -> list[str]:
    return [
        "series_id",
        "series_label",
        "fan_source",
        "scenario_name",
        "FY",
        "period",
        "central",
        "p10",
        "p25",
        "p75",
        "p90",
        "lower50",
        "upper50",
        "lower80",
        "upper80",
        "unit",
        "method",
        "source_file",
        "model_id",
        "horizon_scope",
        "interpretation",
        "fed_path",
    ]


def _fan_availability_columns() -> list[str]:
    return [
        "series_id",
        "series_label",
        "fan_source",
        "available",
        "reason",
        "source_file",
        "model_id",
        "horizon_scope",
        "interpretation",
    ]


def _fan_display_series_frame(chart_rows: pd.DataFrame) -> pd.DataFrame:
    columns = ["series_id", "series_label", "unit", "metric_type"]
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame(columns=columns)
    data = chart_rows.copy()
    data = data[
        data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")
        & data.get("plot_allowed", pd.Series(False, index=data.index)).astype(str).str.lower().isin(["true", "1"])
    ].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for series_id, group in data.groupby("series_id", dropna=False):
        if pd.isna(series_id) or not str(series_id).strip():
            continue
        rows.append(
            {
                "series_id": str(series_id),
                "series_label": _first_group_value(group, "series_label") or str(series_id),
                "unit": _first_group_value(group, "value_unit"),
                "metric_type": _first_group_value(group, "metric_type"),
            }
        )
    out = pd.DataFrame(rows, columns=columns)
    if out.empty:
        return out
    out["_series_order"] = out["series_id"].map(_series_order_index)
    return out.sort_values(["_series_order", "series_label"], kind="stable").drop(columns=["_series_order"]).reset_index(drop=True)


def _mbu26_archived_fan_band_rows(chart_rows: pd.DataFrame, root: Path) -> pd.DataFrame:
    bands_path = root / REVENUE_SOURCE_PACK_DIR / "mot_error_bands.csv"
    archived_bands = _read_optional_csv(bands_path)
    if chart_rows is None or chart_rows.empty or archived_bands.empty:
        return pd.DataFrame(columns=_fan_band_columns())
    central_rows = _fan_central_rows(chart_rows, scenario_name="mbu26_official")
    if central_rows.empty:
        return pd.DataFrame(columns=_fan_band_columns())
    archived_bands = archived_bands.copy()
    archived_bands["horizon_june_years"] = pd.to_numeric(archived_bands.get("horizon_june_years"), errors="coerce")
    archived_bands["sample_size"] = pd.to_numeric(archived_bands.get("n"), errors="coerce")
    for column in ["p10", "p25", "p75", "p90"]:
        archived_bands[column] = pd.to_numeric(archived_bands.get(column), errors="coerce")
    archived_bands = archived_bands.dropna(subset=["horizon_june_years", "sample_size", "p10", "p25", "p75", "p90"])
    archived_bands = archived_bands[archived_bands["sample_size"].ge(10)].copy()
    rows: list[dict[str, Any]] = []
    for series_id, source_label in ARCHIVED_ERROR_BAND_LABELS.items():
        selected = central_rows[central_rows["series_id"].astype(str).eq(series_id)].copy()
        source = archived_bands[archived_bands.get("series", pd.Series(dtype=str)).astype(str).eq(source_label)].copy()
        if selected.empty or source.empty:
            continue
        selected["fan_horizon"] = pd.to_numeric(selected["june_year"], errors="coerce") - REVENUE_LAST_COMPLETE_ACTUAL_FY
        merged = selected.merge(source, how="inner", left_on="fan_horizon", right_on="horizon_june_years", suffixes=("", "_band"))
        for _, row in merged.iterrows():
            central = _as_float(row.get("value"))
            if central is None:
                continue
            p10, p25, p75, p90 = (float(row["p10"]), float(row["p25"]), float(row["p75"]), float(row["p90"]))
            rows.append(
                _fan_band_row(
                    row,
                    series_id=series_id,
                    fan_source=FAN_SOURCE_MBU26_ARCHIVED,
                    scenario_name="mbu26_official",
                    central=central,
                    p10=p10,
                    p25=p25,
                    p75=p75,
                    p90=p90,
                    method="mbu26_archived_forecast_error_bands",
                    source_file=f"{_repo_relative(root, bands_path)}; data/current_revenue_outlook/revenue_chart_rows.csv",
                    model_id="MBU26 official comparator",
                    horizon_scope="june_year_horizon_from_fy2025_actual",
                    interpretation="Archived MBU26/MOT forecast-error quantiles by matching source series and June-year horizon.",
                )
            )
    return pd.DataFrame(rows, columns=_fan_band_columns())


def _current_finalist_backtest_fan_band_rows(chart_rows: pd.DataFrame, root: Path) -> pd.DataFrame:
    evidence_path = root / "data" / "dashboard_evidence_pack" / "data" / "annual_predictions.parquet"
    evidence = _read_optional_parquet(evidence_path)
    if chart_rows is None or chart_rows.empty or evidence.empty:
        return pd.DataFrame(columns=_fan_band_columns())
    quantiles = _current_finalist_backtest_quantiles(evidence)
    if quantiles.empty:
        return pd.DataFrame(columns=_fan_band_columns())
    central_rows = _fan_central_rows(chart_rows, scenario_name="current_basecase")
    central_rows = central_rows[pd.to_numeric(central_rows.get("june_year"), errors="coerce").ge(REVENUE_FIRST_FORECAST_FY)].copy()
    rows: list[dict[str, Any]] = []
    for series_id, (stream, _scope, interpretation) in CURRENT_BACKTEST_STREAM_MAP.items():
        stream_q = quantiles[quantiles["stream"].astype(str).eq(stream)]
        selected = central_rows[central_rows["series_id"].astype(str).eq(series_id)].copy()
        if stream_q.empty or selected.empty:
            continue
        q = stream_q.iloc[0]
        for _, row in selected.iterrows():
            central = _as_float(row.get("value"))
            if central is None:
                continue
            p10, p25, p75, p90 = (float(q["p10"]), float(q["p25"]), float(q["p75"]), float(q["p90"]))
            rows.append(
                _fan_band_row(
                    row,
                    series_id=series_id,
                    fan_source=FAN_SOURCE_CURRENT_BACKTEST,
                    scenario_name="current_basecase",
                    central=central,
                    p10=p10,
                    p25=p25,
                    p75=p75,
                    p90=p90,
                    method="empirical_current_finalist_annual_backtest_error",
                    source_file=f"{_repo_relative(root, evidence_path)}; data/current_revenue_outlook/revenue_chart_rows.csv",
                    model_id=str(q.get("model_id") or row.get("model_id") or ""),
                    horizon_scope="annual_backtest_residuals_all_available_origins",
                    interpretation=f"{interpretation} Empirical bands use actual/predicted annual finalist residual ratios; n={int(q['n'])}.",
                )
            )
    return pd.DataFrame(rows, columns=_fan_band_columns())


def _scenario_spread_fan_band_rows(chart_rows: pd.DataFrame) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame(columns=_fan_band_columns())
    base = _fan_central_rows(chart_rows, scenario_name="current_basecase")
    comparison = _fan_central_rows(chart_rows, scenario_name="current_comparison_1")
    base = base[pd.to_numeric(base.get("june_year"), errors="coerce").ge(REVENUE_FIRST_FORECAST_FY)].copy()
    comparison = comparison[pd.to_numeric(comparison.get("june_year"), errors="coerce").ge(REVENUE_FIRST_FORECAST_FY)].copy()
    if base.empty or comparison.empty:
        return pd.DataFrame(columns=_fan_band_columns())
    join_cols = ["series_id", "period", "june_year", "value_unit", "fed_path"]
    left = base[join_cols + ["series_label", "value", "source_file", "model_id"]].copy()
    right = comparison[join_cols + ["value", "source_file", "model_id"]].copy()
    merged = left.merge(right, how="inner", on=join_cols, suffixes=("_base", "_comparison"))
    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        central = _as_float(row.get("value_base"))
        comparison_value = _as_float(row.get("value_comparison"))
        if central is None or comparison_value is None:
            continue
        lower = min(central, comparison_value)
        upper = max(central, comparison_value)
        rows.append(
            {
                "series_id": str(row["series_id"]),
                "series_label": str(row.get("series_label") or row["series_id"]),
                "fan_source": FAN_SOURCE_SCENARIO_SPREAD,
                "scenario_name": "current_basecase_vs_current_comparison_1",
                "FY": _coerce_int(row.get("june_year")),
                "period": str(row.get("period") or f"FY{_coerce_int(row.get('june_year'))}"),
                "central": central,
                "p10": pd.NA,
                "p25": pd.NA,
                "p75": pd.NA,
                "p90": pd.NA,
                "lower50": lower,
                "upper50": upper,
                "lower80": lower,
                "upper80": upper,
                "unit": str(row.get("value_unit") or ""),
                "method": "scenario_spread_not_probabilistic",
                "source_file": _combine_unique_text([row.get("source_file_base"), row.get("source_file_comparison")]),
                "model_id": _combine_unique_text([row.get("model_id_base"), row.get("model_id_comparison")]),
                "horizon_scope": "future_june_year_base_vs_comparison",
                "interpretation": "Base and comparison current-finalist values define a scenario spread; this is not probabilistic uncertainty.",
                "fed_path": str(row.get("fed_path") or ""),
            }
        )
    return pd.DataFrame(rows, columns=_fan_band_columns())


def _fan_availability_frame(series: pd.DataFrame, bands: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, series_row in series.iterrows():
        series_id = str(series_row["series_id"])
        series_label = str(series_row.get("series_label") or series_id)
        available_sources = {
            str(value)
            for value in bands.loc[bands["series_id"].astype(str).eq(series_id), "fan_source"].dropna().unique()
        } if not bands.empty else set()
        for fan_source in FAN_SOURCE_OPTIONS:
            rows.append(_fan_availability_row(series_id, series_label, fan_source, available_sources, bands))
    out = pd.DataFrame(rows, columns=_fan_availability_columns())
    if out.empty:
        return out
    out["_series_order"] = out["series_id"].map(_series_order_index)
    out["_source_order"] = out["fan_source"].map(_fan_source_order_index)
    return out.sort_values(["_series_order", "_source_order"], kind="stable").drop(columns=["_series_order", "_source_order"]).reset_index(drop=True)


def _fan_availability_row(
    series_id: str,
    series_label: str,
    fan_source: str,
    available_sources: set[str],
    bands: pd.DataFrame,
) -> dict[str, Any]:
    if fan_source == FAN_SOURCE_AUTO:
        chosen = next((source for source in FAN_SOURCE_PRIORITY if source in available_sources), "")
        if chosen:
            meta = _fan_band_metadata(series_id, chosen, bands)
            return {
                "series_id": series_id,
                "series_label": series_label,
                "fan_source": fan_source,
                "available": True,
                "reason": f"Auto selects {chosen}, the highest-priority materialized fan source for this series.",
                **meta,
            }
        return _fan_gap_row(series_id, series_label, fan_source, "No fan source has materialized bands for this series; governed gap only.")
    if fan_source == FAN_SOURCE_NONE:
        return _fan_gap_row(series_id, series_label, fan_source, "Fan intentionally disabled; governed gap displayed.", horizon_scope="not_applicable")
    if fan_source in available_sources:
        reason = {
            FAN_SOURCE_MBU26_ARCHIVED: "Archived forecast-error bands and MBU26 official central rows are materialized for this series.",
            FAN_SOURCE_CURRENT_BACKTEST: "Current finalist annual backtest residual evidence is materialized for the mapped model stream.",
            FAN_SOURCE_SCENARIO_SPREAD: "Current finalist base and comparison rows are materialized for this series; scenario spread is not probabilistic uncertainty.",
        }.get(fan_source, "Fan source is materialized for this series.")
        meta = _fan_band_metadata(series_id, fan_source, bands)
        return {
            "series_id": series_id,
            "series_label": series_label,
            "fan_source": fan_source,
            "available": True,
            "reason": reason,
            **meta,
        }
    return _fan_gap_row(series_id, series_label, fan_source, _fan_missing_reason(series_id, series_label, fan_source), horizon_scope=_fan_missing_horizon_scope(fan_source))


def _fan_band_metadata(series_id: str, fan_source: str, bands: pd.DataFrame) -> dict[str, Any]:
    selected = bands[bands["series_id"].astype(str).eq(series_id) & bands["fan_source"].astype(str).eq(fan_source)] if not bands.empty else pd.DataFrame()
    return {
        "source_file": _combine_unique_text(selected.get("source_file", pd.Series(dtype=str)).dropna().unique().tolist()) if not selected.empty else "",
        "model_id": _combine_unique_text(selected.get("model_id", pd.Series(dtype=str)).dropna().unique().tolist()) if not selected.empty else "",
        "horizon_scope": _combine_unique_text(selected.get("horizon_scope", pd.Series(dtype=str)).dropna().unique().tolist()) if not selected.empty else "",
        "interpretation": _combine_unique_text(selected.get("interpretation", pd.Series(dtype=str)).dropna().unique().tolist()) if not selected.empty else "",
    }


def _fan_gap_row(
    series_id: str,
    series_label: str,
    fan_source: str,
    reason: str,
    *,
    horizon_scope: str = "missing_runtime_artifact",
) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "series_label": series_label,
        "fan_source": fan_source,
        "available": False,
        "reason": reason,
        "source_file": "",
        "model_id": "",
        "horizon_scope": horizon_scope,
        "interpretation": reason,
    }


def _fan_missing_reason(series_id: str, series_label: str, fan_source: str) -> str:
    if fan_source == FAN_SOURCE_MBU26_ARCHIVED:
        if series_id == "ped_vkt_per_capita":
            return "MBU26 archived error bands are materialized for PED volume/revenue, not PED VKT per capita; no VKT-per-capita archived band is available."
        if series_id in ARCHIVED_ERROR_BAND_LABELS:
            return f"Archived error-band source exists for {ARCHIVED_ERROR_BAND_LABELS[series_id]}, but no matching horizon/central rows survived materialization."
        return f"No MBU26 archived forecast-error band is materialized for {series_label}."
    if fan_source == FAN_SOURCE_CURRENT_BACKTEST:
        if series_id in AGGREGATE_PROPAGATION_GAP_SERIES:
            return "Current finalist component uncertainty has not been propagated through this aggregate revenue formula, so no aggregate backtest-error fan is shown."
        return f"No mapped current-finalist model-stream residual evidence is available for {series_label}."
    if fan_source == FAN_SOURCE_SCENARIO_SPREAD:
        return "Current finalist base and comparison rows are missing for the selected series/FY horizon, so scenario spread cannot be drawn."
    return "Fan source is unavailable."


def _fan_missing_horizon_scope(fan_source: str) -> str:
    return {
        FAN_SOURCE_MBU26_ARCHIVED: "missing_archived_error_band_by_series_horizon",
        FAN_SOURCE_CURRENT_BACKTEST: "missing_model_stream_or_component_propagation",
        FAN_SOURCE_SCENARIO_SPREAD: "missing_base_comparison_rows",
    }.get(fan_source, "missing_runtime_artifact")


def _fan_central_rows(chart_rows: pd.DataFrame, *, scenario_name: str) -> pd.DataFrame:
    if chart_rows is None or chart_rows.empty:
        return pd.DataFrame()
    data = chart_rows.copy()
    required = {"series_id", "scenario_name", "time_grain", "value", "june_year", "period"}
    if not required.issubset(data.columns):
        return pd.DataFrame()
    data = data[
        data["time_grain"].astype(str).eq("june_year")
        & data["scenario_name"].astype(str).eq(scenario_name)
        & data.get("plot_allowed", pd.Series(True, index=data.index)).astype(str).str.lower().isin(["true", "1"])
    ].copy()
    if "fed_path" not in data.columns:
        data["fed_path"] = ""
    data["fed_path"] = data["fed_path"].fillna("").astype(str)
    data = data[data["fed_path"].isin(["", "Current planned path", "MBU26"])].copy()
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    return data.dropna(subset=["value", "june_year"]).copy()


def _current_finalist_backtest_quantiles(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence is None or evidence.empty:
        return pd.DataFrame(columns=["stream", "n", "p10", "p25", "p75", "p90", "model_id"])
    data = evidence.copy()
    data = data[
        data.get("scenario", pd.Series("", index=data.index)).astype(str).eq("Finalist")
        & data.get("model_class", pd.Series("", index=data.index)).astype(str).eq("Current finalist")
    ].copy()
    if data.empty:
        return pd.DataFrame(columns=["stream", "n", "p10", "p25", "p75", "p90", "model_id"])
    data["actual_numeric"] = pd.to_numeric(data.get("actual"), errors="coerce")
    data["pred_numeric"] = pd.to_numeric(data.get("pred"), errors="coerce")
    data = data[data["actual_numeric"].notna() & data["pred_numeric"].notna() & data["pred_numeric"].ne(0)].copy()
    data["actual_vs_pred_ratio"] = data["actual_numeric"] / data["pred_numeric"] - 1.0
    rows = []
    for stream, group in data.groupby("stream", dropna=False):
        clean = group["actual_vs_pred_ratio"].dropna()
        if len(clean) < 10:
            continue
        rows.append(
            {
                "stream": str(stream),
                "n": int(len(clean)),
                "p10": float(clean.quantile(0.10)),
                "p25": float(clean.quantile(0.25)),
                "p75": float(clean.quantile(0.75)),
                "p90": float(clean.quantile(0.90)),
                "model_id": _combine_unique_text(group.get("model", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()),
            }
        )
    return pd.DataFrame(rows, columns=["stream", "n", "p10", "p25", "p75", "p90", "model_id"])


def _fan_band_row(
    central_row: pd.Series,
    *,
    series_id: str,
    fan_source: str,
    scenario_name: str,
    central: float,
    p10: float,
    p25: float,
    p75: float,
    p90: float,
    method: str,
    source_file: str,
    model_id: str,
    horizon_scope: str,
    interpretation: str,
) -> dict[str, Any]:
    lower80, upper80 = sorted([central * (1.0 + p10), central * (1.0 + p90)])
    lower50, upper50 = sorted([central * (1.0 + p25), central * (1.0 + p75)])
    return {
        "series_id": series_id,
        "series_label": str(central_row.get("series_label") or series_id),
        "fan_source": fan_source,
        "scenario_name": scenario_name,
        "FY": _coerce_int(central_row.get("june_year")),
        "period": str(central_row.get("period") or f"FY{_coerce_int(central_row.get('june_year'))}"),
        "central": central,
        "p10": p10,
        "p25": p25,
        "p75": p75,
        "p90": p90,
        "lower50": lower50,
        "upper50": upper50,
        "lower80": lower80,
        "upper80": upper80,
        "unit": str(central_row.get("value_unit") or ""),
        "method": method,
        "source_file": source_file,
        "model_id": model_id,
        "horizon_scope": horizon_scope,
        "interpretation": interpretation,
        "fed_path": str(central_row.get("fed_path") or ""),
    }


def _series_order_index(series_id: Any) -> int:
    try:
        return DISPLAY_SERIES_ORDER.index(str(series_id))
    except ValueError:
        return len(DISPLAY_SERIES_ORDER) + 1


def _fan_source_order_index(fan_source: Any) -> int:
    try:
        return FAN_SOURCE_OPTIONS.index(str(fan_source))
    except ValueError:
        return len(FAN_SOURCE_OPTIONS) + 1


def _first_group_value(frame: pd.DataFrame, column: str) -> str:
    if column not in frame.columns:
        return ""
    values = [str(value).strip() for value in frame[column].dropna().tolist() if str(value).strip()]
    return values[0] if values else ""


def _combine_unique_text(values: Any) -> str:
    try:
        iterator = list(values)
    except TypeError:
        iterator = [values]
    out: list[str] = []
    for value in iterator:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return "; ".join(out)


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not np.isfinite(number):
        return None
    return number


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
        "light_bev_ruc_net_km": "Light BEV RUC net km",
        "phev_ruc_net_km": "PHEV RUC net km",
        "heavy_ruc_net_km": "Heavy RUC net km",
        "light_bev_ruc_net_revenue": "Light BEV RUC net revenue",
        "phev_ruc_net_revenue": "PHEV RUC net revenue",
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
        value_status = str(getattr(row, "value_status", "") or "")
        data_scope = (
            "actual_anchor"
            if fy == REVENUE_LAST_COMPLETE_ACTUAL_FY
            else "current_model_extension"
            if value_status == "extrapolated_model_extension"
            else "current_nowcast"
            if bool(getattr(row, "nowcast_flag", False))
            else "current_forecast"
        )
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
                value_status=value_status,
                data_scope=data_scope,
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
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
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
            value = float(group["value_numeric"].sum())
            aggregation_method = "sum_quarterly_vkt_per_capita"
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
        "revenue_stack_components",
        "ev_phev_split_assumptions",
        "revenue_formula_residuals",
        "series_alias_audit",
        "fan_availability",
        "fan_band_rows",
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

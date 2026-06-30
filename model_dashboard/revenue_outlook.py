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
import shutil
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
    EV_PHEV_MIGRATION_DEFAULT_MODE,
    EV_PHEV_MIGRATION_SMOOTHNESS_PENALTY,
    MBU26_RELEASE_ROUND,
    MBU26_SCHEMA_VERSION,
    MBU26_SOURCE_PACK_DIR,
    current_forecast_annual_from_mbu26,
    ev_phev_ped_light_migration_assumptions_from_mbu26,
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
from .scenario_inputs import (
    SCENARIO_FEATURE_LINEAGE_STEM,
    SCENARIO_INPUT_DIRNAME,
    SCENARIO_INPUT_MANIFEST,
    SCENARIO_INPUT_CELLS_STEM,
    SCENARIO_INPUT_LONG_STEM,
    SCENARIO_INPUT_WIDE_STEM,
    combine_scenario_input_dirs,
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
    "ev_phev_ped_light_drift_assumptions.parquet",
    "ped_revenue_bridge_audit.parquet",
    "ped_bridge_shape_fit_metrics.parquet",
    "ped_bridge_mode_config.parquet",
    "ped_efficiency_scenarios.parquet",
    "sensitivity_seed_inputs.parquet",
    "sensitivity_config.parquet",
    "sensitivity_impact_audit.parquet",
    "scenario_input_delta_audit.parquet",
    "scenario_input_replay_mismatch_report.parquet",
    "scenario_feature_lineage.parquet",
    "scenario_role_contract.parquet",
    "revenue_formula_residuals.parquet",
    "series_alias_audit.parquet",
    "runtime_cutoff_audit.parquet",
    "fan_availability.parquet",
    "fan_band_rows.parquet",
    "trace_source_contract.parquet",
    "series_trace_contract.parquet",
    "path_trace_status.parquet",
)
PED_COMPARISON_BEHAVIOURAL_TRACE_NAME = "Current finalist comparison behavioural path"
SCENARIO_ROLE_CONTRACT_NOTE = ""
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
PED_EFFICIENCY_BASELINE_SCENARIO_ID = "baseline_0pct"
PED_EFFICIENCY_DEFAULT_NOTE = (
    "Efficiency sensitivity reduces litres per 100km after EV/PHEV migration; it does not change VKTpc forecasts."
)
PED_EFFICIENCY_SCENARIO_SPECS = (
    (PED_EFFICIENCY_BASELINE_SCENARIO_ID, "Baseline 0%", 0.0),
    ("efficiency_0_5pct_pa", "0.5% p.a.", 0.5),
    ("efficiency_1_0pct_pa", "1.0% p.a.", 1.0),
    ("efficiency_1_5pct_pa", "1.5% p.a.", 1.5),
    ("efficiency_2_0pct_pa", "2.0% p.a.", 2.0),
)
SENSITIVITY_SEED_WORKBOOK_BASENAME = "Revenue Model2.1 with fuel calcs.xlsx"
SENSITIVITY_SEED_WORKBOOK_SHA256 = "54ed1cfee4fa533b655575ff41f59ba656f6c53350d52b9b02482bab1d16a3a7"
SENSITIVITY_SEED_SHEET = "Inputs (TI)"
SENSITIVITY_DEFAULT_NOTE = (
    "Post-model overlays; default Off preserves model forecast. Scenario workbook price variables are already "
    "captured by finalist forecasts where supplied."
)
SENSITIVITY_LEVELS = ("Off", "Low", "Med", "High", "Custom")
FLEET_EFFICIENCY_LEVELS = {"Low": 0.005, "Med": 0.010, "High": 0.015}
PT_MODE_SHIFT_LEVELS = {"Low": 0.0025, "Med": 0.005, "High": 0.010}
DEMAND_ELASTICITY_LEVELS = {
    "PED": {"Low": -0.100, "Med": -0.144116582, "High": -0.240},
    "LIGHT_RUC": {"Low": -0.080, "Med": -0.120, "High": -0.200},
    "HEAVY_RUC": {"Low": -0.050, "Med": -0.100, "High": -0.200},
}
SENSITIVITY_FLEET_START_FY = REVENUE_FIRST_FORECAST_FY
SENSITIVITY_PT_START_FY = 2030
SENSITIVITY_LIGHT_ACTIVITY_SERIES = {
    "light_petrol_vkt",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "current_light_ruc_total_modelled_km",
}
SENSITIVITY_REVENUE_SERIES = {
    "gross_ped_revenue",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "heavy_ruc_net_revenue",
}
SENSITIVITY_ROLLUP_SERIES = {
    "gross_ruc_revenue",
    "ruc_revenue_net_admin",
    "total_ruc_net_revenue",
    "gross_fed_revenue",
    "net_fed_revenue",
    "total_gross_revenue",
    "total_revenue_net_admin",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
}
PED_BRIDGE_DEFAULT_MODE = "raw_model"
PED_BRIDGE_OPTIMIZED_MODE = "optimized_migration"
PED_BRIDGE_MODE_SPECS = (
    (
        PED_BRIDGE_DEFAULT_MODE,
        "Raw model bridge",
        0.0,
        "Default: PED volume = raw PED VKTpc x scenario population x litres intensity / 100.",
    ),
    (
        "blend_25",
        "Blend 25%",
        0.25,
        "PED bridge uses raw + 25% x (optimized - raw).",
    ),
    (
        "blend_50",
        "Blend 50%",
        0.50,
        "PED bridge uses raw + 50% x (optimized - raw).",
    ),
    (
        "blend_75",
        "Blend 75%",
        0.75,
        "PED bridge uses raw + 75% x (optimized - raw).",
    ),
    (
        PED_BRIDGE_OPTIMIZED_MODE,
        "Optimized migration bridge",
        1.0,
        "PED/light-petrol VKT after optimized EV/PHEV migration allocation.",
    ),
)
PED_BRIDGE_MODE_IDS = tuple(spec[0] for spec in PED_BRIDGE_MODE_SPECS)
PED_BRIDGE_MODE_LABELS = {spec[0]: spec[1] for spec in PED_BRIDGE_MODE_SPECS}
PED_BRIDGE_MODE_ALPHA = {spec[0]: float(spec[2]) for spec in PED_BRIDGE_MODE_SPECS}
PED_BRIDGE_NOTE = ""
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
    ev_phev_ped_light_drift_assumptions: pd.DataFrame = field(default_factory=pd.DataFrame)
    ped_revenue_bridge_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    ped_bridge_shape_fit_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    ped_bridge_mode_config: pd.DataFrame = field(default_factory=pd.DataFrame)
    ped_efficiency_scenarios: pd.DataFrame = field(default_factory=pd.DataFrame)
    sensitivity_seed_inputs: pd.DataFrame = field(default_factory=pd.DataFrame)
    sensitivity_config: pd.DataFrame = field(default_factory=pd.DataFrame)
    sensitivity_impact_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    scenario_input_delta_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    scenario_input_replay_mismatch_report: pd.DataFrame = field(default_factory=pd.DataFrame)
    scenario_feature_lineage: pd.DataFrame = field(default_factory=pd.DataFrame)
    scenario_role_contract: pd.DataFrame = field(default_factory=pd.DataFrame)
    revenue_formula_residuals: pd.DataFrame = field(default_factory=pd.DataFrame)
    series_alias_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
    runtime_cutoff_audit: pd.DataFrame = field(default_factory=pd.DataFrame)
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
        base / "ev_phev_ped_light_drift_assumptions.parquet",
        base / "ped_revenue_bridge_audit.parquet",
        base / "ped_bridge_shape_fit_metrics.parquet",
        base / "ped_bridge_mode_config.parquet",
        base / "ped_efficiency_scenarios.parquet",
        base / "sensitivity_seed_inputs.parquet",
        base / "sensitivity_config.parquet",
        base / "sensitivity_impact_audit.parquet",
        base / "scenario_input_delta_audit.parquet",
        base / "scenario_input_replay_mismatch_report.parquet",
        base / "scenario_feature_lineage.parquet",
        base / "scenario_role_contract.parquet",
        base / "revenue_formula_residuals.parquet",
        base / "series_alias_audit.parquet",
        base / "runtime_cutoff_audit.parquet",
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
        ev_phev_ped_light_drift_assumptions=_read_optional_parquet(base / "ev_phev_ped_light_drift_assumptions.parquet"),
        ped_revenue_bridge_audit=_read_optional_parquet(base / "ped_revenue_bridge_audit.parquet"),
        ped_bridge_shape_fit_metrics=_read_optional_parquet(base / "ped_bridge_shape_fit_metrics.parquet"),
        ped_bridge_mode_config=_read_optional_parquet(base / "ped_bridge_mode_config.parquet"),
        ped_efficiency_scenarios=_read_optional_parquet(base / "ped_efficiency_scenarios.parquet"),
        sensitivity_seed_inputs=_read_optional_parquet(base / "sensitivity_seed_inputs.parquet"),
        sensitivity_config=_read_optional_parquet(base / "sensitivity_config.parquet"),
        sensitivity_impact_audit=_read_optional_parquet(base / "sensitivity_impact_audit.parquet"),
        scenario_input_delta_audit=_read_optional_parquet(base / "scenario_input_delta_audit.parquet"),
        scenario_input_replay_mismatch_report=_read_optional_parquet(base / "scenario_input_replay_mismatch_report.parquet"),
        scenario_feature_lineage=_read_optional_parquet(base / "scenario_feature_lineage.parquet"),
        scenario_role_contract=_read_optional_parquet(base / "scenario_role_contract.parquet"),
        revenue_formula_residuals=_read_optional_parquet(base / "revenue_formula_residuals.parquet"),
        series_alias_audit=_read_optional_parquet(base / "series_alias_audit.parquet"),
        runtime_cutoff_audit=_read_optional_parquet(base / "runtime_cutoff_audit.parquet"),
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
    "ped_volume",
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

CURRENT_RUNTIME_CUTOFF_REQUIRED_SERIES = (
    "ped_vkt_per_capita",
    "light_ruc_net_km",
    "heavy_ruc_net_km",
    "gross_ped_revenue",
    "light_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "total_nltf_net_revenue",
)
MBU26_RUNTIME_CUTOFF_REQUIRED_SERIES = (
    "light_petrol_vkt",
    "ped_volume",
    "gross_ped_revenue",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "heavy_ruc_net_km",
    "heavy_ruc_net_revenue",
    "total_nltf_net_revenue",
)


def _runtime_cutoff_fy_and_audit(
    current: pd.DataFrame,
    mbu26_official_annual: pd.DataFrame,
) -> tuple[int, pd.DataFrame]:
    current_data = current.copy() if current is not None else pd.DataFrame()
    source_path = current_data.get("source_path", pd.Series("", index=current_data.index)).fillna("").astype(str)
    scenario_role = current_data.get("scenario_role", pd.Series("", index=current_data.index)).fillna("").astype(str)
    base_mask = source_path.eq("Current finalist Base case") | scenario_role.eq(SCENARIO_ROLE_BASECASE)
    comparison_mask = source_path.eq("Current finalist High population/comparison") | scenario_role.eq(SCENARIO_ROLE_COMPARISON)

    base_last = _last_complete_fy_with_required_series(
        current_data,
        CURRENT_RUNTIME_CUTOFF_REQUIRED_SERIES,
        base_mask,
        exclude_extrapolated=True,
    )
    comparison_last = _last_complete_fy_with_required_series(
        current_data,
        CURRENT_RUNTIME_CUTOFF_REQUIRED_SERIES,
        comparison_mask,
        exclude_extrapolated=True,
    )
    mbu26_last = _last_complete_fy_with_required_series(
        mbu26_official_annual,
        MBU26_RUNTIME_CUTOFF_REQUIRED_SERIES,
        None,
        exclude_extrapolated=False,
    )

    components = [
        (
            "current_finalist_base",
            base_last,
            "last FY with non-extrapolated current-finalist Base case rows",
            CURRENT_RUNTIME_CUTOFF_REQUIRED_SERIES,
        ),
        (
            "current_finalist_comparison",
            comparison_last,
            "last FY with non-extrapolated current-finalist comparison rows",
            CURRENT_RUNTIME_CUTOFF_REQUIRED_SERIES,
        ),
        (
            "mbu26_required_components_rates_splits",
            mbu26_last,
            "last FY with required MBU26 fixed components, rates and split assumptions",
            MBU26_RUNTIME_CUTOFF_REQUIRED_SERIES,
        ),
    ]
    missing = [component for component, last_fy, _, _ in components if last_fy is None]
    if missing:
        raise ValueError(
            "Cannot determine Revenue Outlook runtime cutoff; missing governed horizon evidence for "
            + ", ".join(missing)
        )
    cutoff = min(int(last_fy) for _, last_fy, _, _ in components if last_fy is not None)
    official_max = _max_numeric_year(mbu26_official_annual, "FY")
    official_extends = bool(official_max is not None and int(official_max) > cutoff)
    rows = [
        {
            "audit_component": component,
            "runtime_cutoff_fy": cutoff,
            "last_governed_fy": int(last_fy) if last_fy is not None else pd.NA,
            "required_series": "; ".join(required_series),
            "status": "available" if last_fy is not None else "missing",
            "rule": description,
            "notes": "Excludes disabled post-horizon extension rows." if component.startswith("current_finalist") else "Uses repo-local MBU26 official annual spine.",
        }
        for component, last_fy, description, required_series in components
    ]
    rows.append(
        {
            "audit_component": "runtime_cutoff",
            "runtime_cutoff_fy": cutoff,
            "last_governed_fy": cutoff,
            "required_series": "",
            "status": "selected",
            "rule": (
                "runtime_cutoff_fy = min(current Base, current comparison, required MBU26 inputs/rates/splits)"
            ),
            "notes": (
                f"Comparative charts stop at FY{cutoff}."
                if official_extends
                else f"Comparative charts stop at FY{cutoff}."
            ),
        }
    )
    return cutoff, pd.DataFrame(rows)


def _last_complete_fy_with_required_series(
    frame: pd.DataFrame,
    required_series: tuple[str, ...],
    mask: pd.Series | None,
    *,
    exclude_extrapolated: bool,
) -> int | None:
    if frame is None or frame.empty:
        return None
    data = frame.copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    if mask is not None:
        data = data[mask.reindex(data.index, fill_value=False)].copy()
    if exclude_extrapolated:
        data = data[
            ~data.get("value_status", pd.Series("", index=data.index)).fillna("").astype(str).eq("extrapolated_model_extension")
        ].copy()
    data = data[
        data["FY_numeric"].notna()
        & data["value_numeric"].notna()
        & data.get("series_id", pd.Series("", index=data.index)).astype(str).isin(required_series)
    ].copy()
    if data.empty:
        return None
    counts = data.groupby("FY_numeric")["series_id"].nunique()
    complete = counts[counts.ge(len(set(required_series)))]
    if complete.empty:
        return None
    return int(max(complete.index))


def _max_numeric_year(frame: pd.DataFrame, column: str) -> int | None:
    if frame is None or frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.notna().any():
        return int(values.max())
    return None


def _filter_frame_to_runtime_cutoff(frame: pd.DataFrame, runtime_cutoff_fy: int) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame
    out = frame.copy()
    for column in ("FY", "june_year"):
        if column in out.columns:
            years = pd.to_numeric(out[column], errors="coerce")
            if years.notna().any():
                return out[years.isna() | years.le(runtime_cutoff_fy)].copy()
    for column in ("target_period", "annual_period", "period"):
        if column in out.columns:
            years = out[column].astype(str).str.extract(r"FY(\d{4})", expand=False)
            years = pd.to_numeric(years, errors="coerce")
            if years.notna().any():
                return out[years.isna() | years.le(runtime_cutoff_fy)].copy()
    return out


def ped_efficiency_scenarios_frame(
    *,
    start_fy: int = REVENUE_FIRST_FORECAST_FY,
    end_fy: int | None = None,
) -> pd.DataFrame:
    """Governed PED litres-intensity sensitivity options."""

    end = int(end_fy or start_fy)
    rows: list[dict[str, Any]] = []
    for scenario_id, display_name, gain_pct in PED_EFFICIENCY_SCENARIO_SPECS:
        rows.append(
            {
                "scenario_id": scenario_id,
                "display_name": display_name,
                "annual_efficiency_gain_pct": float(gain_pct),
                "start_fy": int(start_fy),
                "end_fy": end,
                "compounding_rule": "base_litres_per_100km * (1 - annual_efficiency_gain_pct/100)^(FY-start_fy+1)",
                "status": "default" if scenario_id == PED_EFFICIENCY_BASELINE_SCENARIO_ID else "available",
                "notes": PED_EFFICIENCY_DEFAULT_NOTE,
            }
        )
    return pd.DataFrame(rows)


def ped_revenue_bridge_audit_frame(
    line_reconciliation: pd.DataFrame,
    ev_phev_ped_light_drift_assumptions: pd.DataFrame,
) -> pd.DataFrame:
    """Expose the current-finalist PED revenue mechanics at FY/source-path grain."""

    columns = [
        "FY",
        "period",
        "source_path",
        "scenario",
        "scenario_name",
        "scenario_role",
        "fed_path",
        "lambda_mode",
        "ped_vktpc_model",
        "ped_vkt_per_capita",
        "scenario_population",
        "scenario_population_million",
        "population_million",
        "population_source",
        "population_source_status",
        "population_fallback_flag",
        "population_warning",
        "raw_light_petrol_vkt",
        "raw_light_petrol_vkt_million_km",
        "adjusted_light_petrol_vkt_million_km",
        "optimized_light_petrol_vkt",
        "optimized_light_petrol_vkt_million_km",
        "optimization_delta",
        "optimization_delta_million_km",
        "base_litres_per_100km",
        "ped_volume_raw",
        "ped_volume_raw_million_litres",
        "ped_volume_optimized",
        "ped_volume_optimized_million_litres",
        "ped_volume_million_litres",
        "ped_rate",
        "ped_rate_nzd_per_litre",
        "gross_ped_revenue_raw",
        "gross_ped_revenue_raw_million_nzd",
        "gross_ped_revenue_optimized",
        "gross_ped_revenue_optimized_million_nzd",
        "gross_ped_revenue_million_nzd",
        "total_nltf_raw",
        "total_nltf_raw_million_nzd",
        "total_nltf_optimized",
        "total_nltf_optimized_million_nzd",
        "total_nltf_net_revenue_million_nzd",
        "mbu26_ped_vkt_per_capita",
        "mbu26_population_proxy",
        "mbu26_light_petrol_vkt_million_km",
        "mbu26_ped_volume_million_litres",
        "mbu26_gross_ped_revenue_million_nzd",
        "mbu26_total_nltf_net_revenue_million_nzd",
        "raw_light_petrol_vkt_residual",
        "ped_volume_raw_residual",
        "ped_volume_optimized_residual",
        "gross_ped_revenue_raw_residual",
        "gross_ped_revenue_optimized_residual",
        "vktpc_unit",
        "population_unit",
        "light_petrol_vkt_unit",
        "litres_intensity_unit",
        "ped_volume_unit",
        "ped_rate_unit",
        "gross_ped_revenue_unit",
        "source_file",
        "vktpc_source_cell",
        "population_source_cell",
        "migration_source_cells",
        "formula",
        "availability_status",
        "notes",
    ]
    if (
        line_reconciliation is None
        or line_reconciliation.empty
        or ev_phev_ped_light_drift_assumptions is None
        or ev_phev_ped_light_drift_assumptions.empty
    ):
        return pd.DataFrame(columns=columns)

    line = line_reconciliation.copy()
    line["FY_numeric"] = pd.to_numeric(line.get("FY"), errors="coerce")
    line["value_numeric"] = pd.to_numeric(line.get("value"), errors="coerce")
    line["series_text"] = line.get("series_id", pd.Series("", index=line.index)).fillna("").astype(str)
    line["source_path_text"] = line.get("source_path", pd.Series("", index=line.index)).fillna("").astype(str)
    line["scenario_text"] = line.get("scenario_name", pd.Series("", index=line.index)).fillna("").astype(str)

    def line_value(source_path: str, fy: int, scenario_name: str, series_id: str, column: str = "value_numeric") -> Any:
        rows = line[
            line["source_path_text"].eq(source_path)
            & line["FY_numeric"].eq(fy)
            & line["scenario_text"].eq(scenario_name)
            & line["series_text"].eq(series_id)
        ]
        if rows.empty:
            return pd.NA
        return rows.iloc[0].get(column, pd.NA)

    def line_text(source_path: str, fy: int, scenario_name: str, series_id: str, column: str) -> str:
        rows = line[
            line["source_path_text"].eq(source_path)
            & line["FY_numeric"].eq(fy)
            & line["scenario_text"].eq(scenario_name)
            & line["series_text"].eq(series_id)
        ]
        if rows.empty:
            return ""
        return str(rows.iloc[0].get(column, "") or "")

    drift = ev_phev_ped_light_drift_assumptions.copy()
    drift["FY_numeric"] = pd.to_numeric(drift.get("FY"), errors="coerce")
    drift = drift[
        drift.get("lambda_mode", pd.Series("", index=drift.index)).fillna("").astype(str).eq(EV_PHEV_MIGRATION_DEFAULT_MODE)
        & drift.get("source_path", pd.Series("", index=drift.index)).fillna("").astype(str).str.startswith("Current finalist")
        & drift["FY_numeric"].ge(REVENUE_FIRST_FORECAST_FY)
        & drift["FY_numeric"].notna()
    ].copy()
    if drift.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for record in drift.to_dict("records"):
        fy = int(record["FY_numeric"])
        source_path = str(record.get("source_path") or "")
        scenario_name = str(record.get("scenario_name") or "")
        scenario_role = str(record.get("scenario_role") or "")
        fed_path = line_text(source_path, fy, scenario_name, "gross_ped_revenue", "fed_path") or "Current planned path"
        ped_vktpc = pd.to_numeric(line_value(source_path, fy, scenario_name, "ped_vkt_per_capita"), errors="coerce")
        raw_light_petrol_vkt = pd.to_numeric(record.get("current_P_t_light_petrol_km"), errors="coerce")
        light_petrol_vkt = pd.to_numeric(record.get("current_PED_light_petrol_km"), errors="coerce")
        base_litres = pd.to_numeric(record.get("ped_litres_per_100km"), errors="coerce")
        ped_rate = pd.to_numeric(record.get("ped_rate"), errors="coerce")
        scenario_population = pd.NA
        if pd.notna(ped_vktpc) and float(ped_vktpc) > 0 and pd.notna(raw_light_petrol_vkt):
            scenario_population = float(raw_light_petrol_vkt) * 1_000_000.0 / float(ped_vktpc)
        population_million = float(scenario_population) / 1_000_000.0 if pd.notna(scenario_population) else pd.NA
        optimization_delta = (
            float(light_petrol_vkt) - float(raw_light_petrol_vkt)
            if pd.notna(light_petrol_vkt) and pd.notna(raw_light_petrol_vkt)
            else pd.NA
        )
        ped_volume_raw = (
            float(raw_light_petrol_vkt) * float(base_litres) / 100.0
            if pd.notna(raw_light_petrol_vkt) and pd.notna(base_litres)
            else pd.NA
        )
        ped_volume_optimized = pd.to_numeric(record.get("current_PED_volume"), errors="coerce")
        gross_ped_raw = (
            float(ped_volume_raw) * float(ped_rate)
            if pd.notna(ped_volume_raw) and pd.notna(ped_rate)
            else pd.NA
        )
        gross_ped_optimized = pd.to_numeric(record.get("current_PED_revenue"), errors="coerce")
        total_nltf_optimized = line_value(source_path, fy, scenario_name, "total_nltf_net_revenue")
        total_nltf_raw = (
            float(total_nltf_optimized) + float(gross_ped_raw) - float(gross_ped_optimized)
            if pd.notna(total_nltf_optimized) and pd.notna(gross_ped_raw) and pd.notna(gross_ped_optimized)
            else pd.NA
        )
        population_source = line_text(source_path, fy, scenario_name, "gross_ped_revenue", "population_source_cell")
        population_source_status = line_text(source_path, fy, scenario_name, "gross_ped_revenue", "population_source_status")
        population_fallback_flag = "population_proxy" in f"{population_source} {population_source_status}".lower()
        population_warning = (
            "warning_current_finalist_uses_mbu26_population_proxy"
            if population_fallback_flag and source_path.startswith("Current finalist")
            else ""
        )
        mbu_ped_vktpc = line_value("MBU26 official", fy, "mbu26_official", "ped_vkt_per_capita")
        mbu_light_petrol_vkt = line_value("MBU26 official", fy, "mbu26_official", "light_petrol_vkt")
        mbu_ped_volume = line_value("MBU26 official", fy, "mbu26_official", "ped_volume")
        mbu_gross_ped = line_value("MBU26 official", fy, "mbu26_official", "gross_ped_revenue")
        mbu_total_nltf = line_value("MBU26 official", fy, "mbu26_official", "total_nltf_net_revenue")
        mbu_population_proxy = (
            float(mbu_light_petrol_vkt) * 1_000_000.0 / float(mbu_ped_vktpc)
            if pd.notna(mbu_light_petrol_vkt) and pd.notna(mbu_ped_vktpc) and float(mbu_ped_vktpc) > 0
            else pd.NA
        )
        rows.append(
            {
                "FY": fy,
                "period": f"FY{fy}",
                "source_path": source_path,
                "scenario": scenario_name,
                "scenario_name": scenario_name,
                "scenario_role": scenario_role,
                "fed_path": fed_path,
                "lambda_mode": str(record.get("lambda_mode") or ""),
                "ped_vktpc_model": ped_vktpc,
                "ped_vkt_per_capita": ped_vktpc,
                "scenario_population": scenario_population,
                "scenario_population_million": population_million,
                "population_million": population_million,
                "population_source": population_source,
                "population_source_status": population_source_status,
                "population_fallback_flag": population_fallback_flag,
                "population_warning": population_warning,
                "raw_light_petrol_vkt": raw_light_petrol_vkt,
                "raw_light_petrol_vkt_million_km": raw_light_petrol_vkt,
                "adjusted_light_petrol_vkt_million_km": light_petrol_vkt,
                "optimized_light_petrol_vkt": light_petrol_vkt,
                "optimized_light_petrol_vkt_million_km": light_petrol_vkt,
                "optimization_delta": optimization_delta,
                "optimization_delta_million_km": optimization_delta,
                "base_litres_per_100km": base_litres,
                "ped_volume_raw": ped_volume_raw,
                "ped_volume_raw_million_litres": ped_volume_raw,
                "ped_volume_optimized": ped_volume_optimized,
                "ped_volume_optimized_million_litres": ped_volume_optimized,
                "ped_volume_million_litres": ped_volume_optimized,
                "ped_rate": ped_rate,
                "ped_rate_nzd_per_litre": ped_rate,
                "gross_ped_revenue_raw": gross_ped_raw,
                "gross_ped_revenue_raw_million_nzd": gross_ped_raw,
                "gross_ped_revenue_optimized": gross_ped_optimized,
                "gross_ped_revenue_optimized_million_nzd": gross_ped_optimized,
                "gross_ped_revenue_million_nzd": gross_ped_optimized,
                "total_nltf_raw": total_nltf_raw,
                "total_nltf_raw_million_nzd": total_nltf_raw,
                "total_nltf_optimized": total_nltf_optimized,
                "total_nltf_optimized_million_nzd": total_nltf_optimized,
                "total_nltf_net_revenue_million_nzd": total_nltf_optimized,
                "mbu26_ped_vkt_per_capita": mbu_ped_vktpc,
                "mbu26_population_proxy": mbu_population_proxy,
                "mbu26_light_petrol_vkt_million_km": mbu_light_petrol_vkt,
                "mbu26_ped_volume_million_litres": mbu_ped_volume,
                "mbu26_gross_ped_revenue_million_nzd": mbu_gross_ped,
                "mbu26_total_nltf_net_revenue_million_nzd": mbu_total_nltf,
                "raw_light_petrol_vkt_residual": (
                    float(raw_light_petrol_vkt) - float(ped_vktpc) * float(scenario_population) / 1_000_000.0
                    if pd.notna(raw_light_petrol_vkt) and pd.notna(ped_vktpc) and pd.notna(scenario_population)
                    else pd.NA
                ),
                "ped_volume_raw_residual": (
                    float(ped_volume_raw) - float(raw_light_petrol_vkt) * float(base_litres) / 100.0
                    if pd.notna(ped_volume_raw) and pd.notna(raw_light_petrol_vkt) and pd.notna(base_litres)
                    else pd.NA
                ),
                "ped_volume_optimized_residual": (
                    float(ped_volume_optimized) - float(light_petrol_vkt) * float(base_litres) / 100.0
                    if pd.notna(ped_volume_optimized) and pd.notna(light_petrol_vkt) and pd.notna(base_litres)
                    else pd.NA
                ),
                "gross_ped_revenue_raw_residual": (
                    float(gross_ped_raw) - float(ped_volume_raw) * float(ped_rate)
                    if pd.notna(gross_ped_raw) and pd.notna(ped_volume_raw) and pd.notna(ped_rate)
                    else pd.NA
                ),
                "gross_ped_revenue_optimized_residual": (
                    float(gross_ped_optimized) - float(ped_volume_optimized) * float(ped_rate)
                    if pd.notna(gross_ped_optimized) and pd.notna(ped_volume_optimized) and pd.notna(ped_rate)
                    else pd.NA
                ),
                "vktpc_unit": line_text(source_path, fy, scenario_name, "ped_vkt_per_capita", "unit") or "km/person",
                "population_unit": "million people",
                "light_petrol_vkt_unit": "million km",
                "litres_intensity_unit": "litres/100km",
                "ped_volume_unit": "million litres",
                "ped_rate_unit": "$/litre",
                "gross_ped_revenue_unit": "$m nominal ex GST",
                "source_file": line_text(source_path, fy, scenario_name, "gross_ped_revenue", "source_file"),
                "vktpc_source_cell": line_text(source_path, fy, scenario_name, "ped_vkt_per_capita", "vktpc_source_cell")
                or line_text(source_path, fy, scenario_name, "ped_vkt_per_capita", "source_cell"),
                "population_source_cell": population_source,
                "migration_source_cells": str(record.get("source_cells") or ""),
                "formula": (
                    "raw_light_petrol_vkt = ped_vkt_per_capita * scenario_population / 1,000,000; "
                    "optimized_light_petrol_vkt = raw_light_petrol_vkt + optimization_delta; "
                    "gross_ped_revenue = selected_light_petrol_vkt * base_litres_per_100km / 100 * ped_rate_nzd_per_litre"
                ),
                "availability_status": population_warning or str(record.get("availability_status") or "available"),
                "notes": (
                    "Raw bridge uses current-finalist PED VKTpc times scenario population. Optimized bridge then "
                    "applies the PED+Light EV/PHEV migration allocation before MBU26 litres intensity and PED rate."
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(["source_path", "FY"], kind="stable").reset_index(drop=True)


def ped_bridge_mode_config_frame() -> pd.DataFrame:
    """Governed PED bridge audit mode registry."""

    return pd.DataFrame(
        [
            {
                "bridge_mode": mode,
                "display_name": label,
                "alpha": alpha,
                "alpha_pct": alpha * 100.0,
                "default_selected": mode == PED_BRIDGE_DEFAULT_MODE,
                "formula": "raw_light_petrol_vkt + alpha * (optimized_light_petrol_vkt - raw_light_petrol_vkt)",
                "runtime_treatment": "default_runtime" if mode == PED_BRIDGE_DEFAULT_MODE else "audit_overlay",
                "notes": notes,
            }
            for mode, label, alpha, notes in PED_BRIDGE_MODE_SPECS
        ]
    )


def ped_bridge_shape_fit_metrics_frame(ped_revenue_bridge_audit: pd.DataFrame) -> pd.DataFrame:
    """Quantify whether optimized PED bridge values are closer to MBU26 shapes."""

    columns = [
        "source_path",
        "scenario_name",
        "scenario_role",
        "series_id",
        "bridge_variant",
        "mbu_comparator_series_id",
        "start_fy",
        "end_fy",
        "n_rows",
        "correlation_vs_mbu",
        "slope_vs_mbu",
        "intercept_vs_mbu",
        "mean_error",
        "mean_abs_error",
        "rmse",
        "mean_abs_pct_error",
        "shape_anchor_status",
        "notes",
    ]
    if ped_revenue_bridge_audit is None or ped_revenue_bridge_audit.empty:
        return pd.DataFrame(columns=columns)

    data = ped_revenue_bridge_audit.copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data = data[data["FY_numeric"].between(2026, 2050, inclusive="both")].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)

    pairs = [
        ("raw_light_petrol_vkt_million_km", "raw_light_petrol_vkt", "mbu26_light_petrol_vkt_million_km", "light_petrol_vkt"),
        (
            "optimized_light_petrol_vkt_million_km",
            "optimized_light_petrol_vkt",
            "mbu26_light_petrol_vkt_million_km",
            "light_petrol_vkt",
        ),
        ("ped_volume_raw_million_litres", "ped_volume_raw", "mbu26_ped_volume_million_litres", "ped_volume"),
        (
            "ped_volume_optimized_million_litres",
            "ped_volume_optimized",
            "mbu26_ped_volume_million_litres",
            "ped_volume",
        ),
        (
            "gross_ped_revenue_raw_million_nzd",
            "gross_ped_revenue_raw",
            "mbu26_gross_ped_revenue_million_nzd",
            "gross_ped_revenue",
        ),
        (
            "gross_ped_revenue_optimized_million_nzd",
            "gross_ped_revenue_optimized",
            "mbu26_gross_ped_revenue_million_nzd",
            "gross_ped_revenue",
        ),
    ]

    rows: list[dict[str, Any]] = []
    for (source_path, scenario_name, scenario_role), group in data.groupby(
        ["source_path", "scenario_name", "scenario_role"], dropna=False, sort=False
    ):
        fit_by_comparator: dict[str, dict[str, float]] = {}
        for value_col, variant, comparator_col, comparator_id in pairs:
            if value_col not in group.columns or comparator_col not in group.columns:
                continue
            value = pd.to_numeric(group[value_col], errors="coerce")
            mbu = pd.to_numeric(group[comparator_col], errors="coerce")
            ok = value.notna() & mbu.notna()
            if not ok.any():
                continue
            x = value[ok].astype(float)
            y = mbu[ok].astype(float)
            if len(x) >= 2 and float(((y - y.mean()) ** 2).sum()) > 0:
                slope = float(((x - x.mean()) * (y - y.mean())).sum() / ((y - y.mean()) ** 2).sum())
                intercept = float(x.mean() - slope * y.mean())
                corr = float(x.corr(y))
            else:
                slope = np.nan
                intercept = np.nan
                corr = np.nan
            error = x - y
            nonzero = y.abs() > 1e-12
            mape = float((error[nonzero].abs() / y[nonzero].abs()).mean()) if nonzero.any() else np.nan
            metrics = {
                "n_rows": int(ok.sum()),
                "correlation_vs_mbu": corr,
                "slope_vs_mbu": slope,
                "intercept_vs_mbu": intercept,
                "mean_error": float(error.mean()),
                "mean_abs_error": float(error.abs().mean()),
                "rmse": float(np.sqrt((error**2).mean())),
                "mean_abs_pct_error": mape,
            }
            fit_by_comparator[variant] = metrics
            status = "shape_fit_reported"
            raw_variant = variant.replace("optimized", "raw")
            if "optimized" in variant and raw_variant in fit_by_comparator:
                raw_mae = fit_by_comparator[raw_variant].get("mean_abs_error", np.nan)
                raw_corr = fit_by_comparator[raw_variant].get("correlation_vs_mbu", np.nan)
                if np.isfinite(raw_mae) and metrics["mean_abs_error"] < raw_mae and (
                    not np.isfinite(raw_corr) or (np.isfinite(corr) and abs(corr) >= abs(raw_corr))
                ):
                    status = "optimized_closer_to_mbu_than_raw"
            rows.append(
                {
                    "source_path": source_path,
                    "scenario_name": scenario_name,
                    "scenario_role": scenario_role,
                    "series_id": variant,
                    "bridge_variant": "optimized" if "optimized" in variant else "raw",
                    "mbu_comparator_series_id": comparator_id,
                    "start_fy": int(group["FY_numeric"].min()),
                    "end_fy": int(group["FY_numeric"].max()),
                    "shape_anchor_status": status,
                    "notes": "FY2026-FY2050 shape fit. Lower error and higher correlation indicate closer alignment to MBU26 shape.",
                    **metrics,
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["source_path", "mbu_comparator_series_id", "bridge_variant", "series_id"],
        kind="stable",
    ).reset_index(drop=True)


def ped_bridge_mode_impact_audit_frame(
    line_reconciliation: pd.DataFrame,
    ped_revenue_bridge_audit: pd.DataFrame,
    bridge_mode: str = PED_BRIDGE_DEFAULT_MODE,
) -> pd.DataFrame:
    """Calculate selected PED bridge-mode deltas for current-finalist rows."""

    columns = [
        "FY",
        "period",
        "source_path",
        "scenario_name",
        "scenario_role",
        "fed_path",
        "selected_ped_bridge_mode",
        "selected_ped_bridge_label",
        "bridge_alpha",
        "stream",
        "series_id",
        "baseline",
        "adjusted",
        "delta",
        "unit",
        "formula",
        "source_cells",
        "population_source_status",
        "population_fallback_flag",
        "gap_reason",
        "status",
        "notes",
    ]
    if line_reconciliation is None or line_reconciliation.empty or ped_revenue_bridge_audit is None or ped_revenue_bridge_audit.empty:
        return pd.DataFrame(columns=columns)

    mode = _normalize_ped_bridge_mode(bridge_mode)
    alpha = PED_BRIDGE_MODE_ALPHA.get(mode, 1.0)
    label = PED_BRIDGE_MODE_LABELS.get(mode, PED_BRIDGE_MODE_LABELS[PED_BRIDGE_DEFAULT_MODE])
    line = line_reconciliation.copy()
    line["FY_numeric"] = pd.to_numeric(line.get("FY"), errors="coerce")
    line["value_numeric"] = pd.to_numeric(line.get("value"), errors="coerce")
    line["source_path_text"] = line.get("source_path", pd.Series("", index=line.index)).fillna("").astype(str)
    line["scenario_text"] = line.get("scenario_name", pd.Series("", index=line.index)).fillna("").astype(str)
    line["series_text"] = line.get("series_id", pd.Series("", index=line.index)).fillna("").astype(str)
    line_units = line.get("unit", pd.Series("", index=line.index))
    value_lookup: dict[tuple[str, int, str, str], float] = {}
    unit_lookup: dict[tuple[str, int, str, str], str] = {}
    for source_path, fy_value, scenario_name, series_id, value_numeric, unit_value in zip(
        line["source_path_text"],
        line["FY_numeric"],
        line["scenario_text"],
        line["series_text"],
        line["value_numeric"],
        line_units,
        strict=False,
    ):
        if pd.isna(fy_value):
            continue
        key = (source_path, int(fy_value), scenario_name, series_id)
        if key not in value_lookup:
            value_lookup[key] = _finite_float(value_numeric, np.nan)
            unit_lookup[key] = str(unit_value or "")

    def value(source_path: str, fy: int, scenario_name: str, series_id: str) -> float:
        return value_lookup.get((source_path, fy, scenario_name, series_id), np.nan)

    def unit(source_path: str, fy: int, scenario_name: str, series_id: str) -> str:
        return unit_lookup.get((source_path, fy, scenario_name, series_id), "")

    rows: list[dict[str, Any]] = []
    audit = ped_revenue_bridge_audit.copy()
    audit["FY_numeric"] = pd.to_numeric(audit.get("FY"), errors="coerce")
    audit = audit[
        audit.get("source_path", pd.Series("", index=audit.index)).fillna("").astype(str).str.startswith("Current finalist")
        & audit["FY_numeric"].ge(REVENUE_FIRST_FORECAST_FY)
    ].copy()
    for record in audit.to_dict("records"):
        if pd.isna(record.get("FY_numeric")):
            continue
        fy = int(record["FY_numeric"])
        source_path = str(record.get("source_path") or "")
        scenario_name = str(record.get("scenario_name") or "")
        scenario_role = str(record.get("scenario_role") or "")
        fed_path = str(record.get("fed_path") or "Current planned path")
        raw_vkt = _finite_float(record.get("raw_light_petrol_vkt_million_km"), np.nan)
        opt_vkt = _finite_float(record.get("optimized_light_petrol_vkt_million_km"), np.nan)
        base_litres = _finite_float(record.get("base_litres_per_100km"), np.nan)
        ped_rate = _finite_float(record.get("ped_rate_nzd_per_litre"), np.nan)
        selected_vkt = raw_vkt + alpha * (opt_vkt - raw_vkt) if np.isfinite(raw_vkt) and np.isfinite(opt_vkt) else np.nan
        selected_volume = selected_vkt * base_litres / 100.0 if np.isfinite(selected_vkt) and np.isfinite(base_litres) else np.nan
        selected_revenue = selected_volume * ped_rate if np.isfinite(selected_volume) and np.isfinite(ped_rate) else np.nan
        ped_delta = selected_revenue - value(source_path, fy, scenario_name, "gross_ped_revenue")
        adjusted = {
            "light_petrol_vkt": selected_vkt,
            "ped_volume": selected_volume,
            "gross_ped_revenue": selected_revenue,
            "gross_fed_revenue": value(source_path, fy, scenario_name, "gross_fed_revenue") + ped_delta,
            "net_fed_revenue": value(source_path, fy, scenario_name, "net_fed_revenue") + ped_delta,
            "total_gross_revenue": value(source_path, fy, scenario_name, "total_gross_revenue") + ped_delta,
            "total_revenue_net_admin": value(source_path, fy, scenario_name, "total_revenue_net_admin") + ped_delta,
            "total_fed_ruc_net_revenue": value(source_path, fy, scenario_name, "total_fed_ruc_net_revenue") + ped_delta,
            "total_nltf_net_revenue": value(source_path, fy, scenario_name, "total_nltf_net_revenue") + ped_delta,
        }
        source_cells = "; ".join(
            part
            for part in [
                str(record.get("vktpc_source_cell") or ""),
                str(record.get("population_source_cell") or ""),
                str(record.get("migration_source_cells") or ""),
            ]
            if part
        )

        def add_row(series_id: str, stream: str, formula: str) -> None:
            baseline = value(source_path, fy, scenario_name, series_id)
            adjusted_value = adjusted.get(series_id, baseline)
            if not np.isfinite(baseline) or not np.isfinite(adjusted_value):
                return
            rows.append(
                {
                    "FY": fy,
                    "period": f"FY{fy}",
                    "source_path": source_path,
                    "scenario_name": scenario_name,
                    "scenario_role": scenario_role,
                    "fed_path": fed_path,
                    "selected_ped_bridge_mode": mode,
                    "selected_ped_bridge_label": label,
                    "bridge_alpha": alpha,
                    "stream": stream,
                    "series_id": series_id,
                    "baseline": baseline,
                    "adjusted": adjusted_value,
                    "delta": adjusted_value - baseline,
                    "unit": unit(source_path, fy, scenario_name, series_id),
                    "formula": formula,
                    "source_cells": source_cells,
                    "population_source_status": str(record.get("population_source_status") or ""),
                    "population_fallback_flag": bool(record.get("population_fallback_flag")),
                    "gap_reason": str(record.get("population_warning") or ""),
                    "status": "warning_population_proxy" if bool(record.get("population_fallback_flag")) else "adjusted",
                    "notes": PED_BRIDGE_NOTE,
                }
            )

        add_row(
            "light_petrol_vkt",
            "PED",
            "selected_light_petrol_vkt = raw_light_petrol_vkt + alpha * optimization_delta",
        )
        add_row("ped_volume", "PED", "selected_light_petrol_vkt * base_litres_per_100km / 100")
        add_row("gross_ped_revenue", "PED", "selected_ped_volume * ped_rate")
        for series_id in [
            "gross_fed_revenue",
            "net_fed_revenue",
            "total_gross_revenue",
            "total_revenue_net_admin",
            "total_fed_ruc_net_revenue",
            "total_nltf_net_revenue",
        ]:
            add_row(series_id, "ROLLUP", f"{series_id} + selected PED revenue delta")
    return pd.DataFrame(rows, columns=columns)


def apply_ped_bridge_mode_layer(
    *,
    chart_rows: pd.DataFrame,
    line_reconciliation: pd.DataFrame,
    bridge_components: pd.DataFrame,
    future_revenue_forecasts: pd.DataFrame,
    ped_revenue_bridge_audit: pd.DataFrame,
    bridge_mode: str = PED_BRIDGE_DEFAULT_MODE,
    include_derived_frames: bool = True,
) -> dict[str, pd.DataFrame]:
    """Apply a PED bridge audit mode to current-finalist copies."""

    impact = ped_bridge_mode_impact_audit_frame(line_reconciliation, ped_revenue_bridge_audit, bridge_mode)
    if include_derived_frames:
        adjusted_line = _apply_ped_bridge_mode_audit_to_frame(
            line_reconciliation,
            impact,
            value_column="value",
            fy_column="FY",
            series_column="series_id",
            source_path_column="source_path",
            scenario_column="scenario_name",
            fed_path_column="fed_path",
        )
        formula_residuals = revenue_formula_residual_frame(adjusted_line) if adjusted_line is not None and not adjusted_line.empty else pd.DataFrame()
        stack_components = revenue_stack_components_frame(adjusted_line, formula_residuals) if adjusted_line is not None and not adjusted_line.empty else pd.DataFrame()
        adjusted_ped_audit = _ped_bridge_audit_for_selected_mode(ped_revenue_bridge_audit, bridge_mode)
    else:
        adjusted_line = pd.DataFrame()
        formula_residuals = pd.DataFrame()
        stack_components = pd.DataFrame()
        adjusted_ped_audit = pd.DataFrame()
    adjusted_chart = _apply_ped_bridge_mode_audit_to_frame(
        chart_rows,
        impact,
        value_column="value",
        fy_column="june_year",
        series_column="series_id",
        source_path_column="trace_name",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
        current_mask_column="trace_role",
    )
    adjusted_bridge = _apply_ped_bridge_mode_audit_to_frame(
        bridge_components,
        impact,
        value_column="component_value",
        fy_column="period",
        series_column="stream",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    adjusted_future = _apply_ped_bridge_mode_audit_to_frame(
        future_revenue_forecasts,
        impact,
        value_column="revenue_forecast_nzd",
        fy_column="period",
        series_column="stream",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    return {
        "chart_rows": adjusted_chart,
        "line_reconciliation": adjusted_line,
        "revenue_formula_residuals": formula_residuals,
        "revenue_stack_components": stack_components,
        "revenue_bridge_components": adjusted_bridge,
        "future_revenue_forecasts": adjusted_future,
        "ped_revenue_bridge_audit": adjusted_ped_audit,
        "ped_bridge_mode_impact_audit": impact,
    }


def _apply_ped_bridge_mode_audit_to_frame(
    frame: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    value_column: str,
    fy_column: str,
    series_column: str,
    source_path_column: str | None = None,
    scenario_column: str | None = None,
    fed_path_column: str | None = None,
    current_mask_column: str | None = None,
) -> pd.DataFrame:
    if frame is None or frame.empty or audit is None or audit.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    out = frame.copy()
    for column in ["ped_bridge_mode_label", "ped_bridge_value_delta", "ped_bridge_population_warning"]:
        if column not in out.columns:
            out[column] = pd.NA
    audit_lookup = audit.copy()
    audit_lookup["FY_numeric"] = pd.to_numeric(audit_lookup.get("FY"), errors="coerce")
    lookup: dict[tuple[str, int, str, str, str], dict[str, Any]] = {}
    for record in audit_lookup.to_dict("records"):
        if pd.isna(record.get("FY_numeric")):
            continue
        lookup[
            (
                str(record.get("source_path") or ""),
                int(record["FY_numeric"]),
                str(record.get("scenario_name") or ""),
                str(record.get("fed_path") or ""),
                str(record.get("series_id") or ""),
            )
        ] = record
    no_source_lookup: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    no_fed_lookup: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    no_source_no_fed_lookup: dict[tuple[int, str, str], dict[str, Any]] = {}
    for (source_path, fy, scenario_name, fed_path, series_id), record in lookup.items():
        no_source_lookup.setdefault((fy, scenario_name, fed_path, series_id), record)
        no_fed_lookup.setdefault((source_path, fy, scenario_name, series_id), record)
        no_source_no_fed_lookup.setdefault((fy, scenario_name, series_id), record)
    out["_ped_bridge_fy"] = out.get(fy_column, pd.Series("", index=out.index)).map(_extract_fy_number)
    candidate_mask = out["_ped_bridge_fy"].notna()
    if current_mask_column:
        current_role = out.get(current_mask_column, pd.Series("", index=out.index)).fillna("").astype(str)
        candidate_mask &= current_role.isin(["", "in_house_current_finalist"])
    candidate_columns = [value_column, "_ped_bridge_fy", series_column]
    for optional_column in [source_path_column, scenario_column, fed_path_column]:
        if optional_column:
            candidate_columns.append(optional_column)
    candidate_columns = list(dict.fromkeys(column for column in candidate_columns if column in out.columns))
    for idx, row in out.loc[candidate_mask, candidate_columns].iterrows():
        fy = row.get("_ped_bridge_fy")
        if pd.isna(fy):
            continue
        series_id = str(row.get(series_column) or "")
        source_path = str(row.get(source_path_column) or "") if source_path_column else ""
        scenario_name = str(row.get(scenario_column) or "") if scenario_column else ""
        fed_path = str(row.get(fed_path_column) or "") if fed_path_column else ""
        record = lookup.get((source_path, int(fy), scenario_name, fed_path, series_id))
        if not record:
            if not source_path and fed_path:
                record = no_source_lookup.get((int(fy), scenario_name, fed_path, series_id))
            elif source_path and not fed_path:
                record = no_fed_lookup.get((source_path, int(fy), scenario_name, series_id))
            elif not source_path and not fed_path:
                record = no_source_no_fed_lookup.get((int(fy), scenario_name, series_id))
        if not record:
            continue
        adjusted_value = _finite_float(record.get("adjusted"), np.nan)
        baseline_value = _finite_float(row.get(value_column), np.nan)
        if not np.isfinite(adjusted_value):
            continue
        out.at[idx, value_column] = adjusted_value
        out.at[idx, "ped_bridge_mode_label"] = _ped_bridge_mode_display_label(record)
        out.at[idx, "ped_bridge_value_delta"] = adjusted_value - baseline_value if np.isfinite(baseline_value) else pd.NA
        out.at[idx, "ped_bridge_population_warning"] = record.get("gap_reason")
    return out.drop(columns=["_ped_bridge_fy"], errors="ignore")


def _ped_bridge_audit_for_selected_mode(ped_revenue_bridge_audit: pd.DataFrame, bridge_mode: str) -> pd.DataFrame:
    if ped_revenue_bridge_audit is None or ped_revenue_bridge_audit.empty:
        return pd.DataFrame() if ped_revenue_bridge_audit is None else ped_revenue_bridge_audit.copy()
    mode = _normalize_ped_bridge_mode(bridge_mode)
    alpha = PED_BRIDGE_MODE_ALPHA.get(mode, 1.0)
    label = PED_BRIDGE_MODE_LABELS.get(mode, PED_BRIDGE_MODE_LABELS[PED_BRIDGE_DEFAULT_MODE])
    out = ped_revenue_bridge_audit.copy()
    raw = pd.to_numeric(out.get("raw_light_petrol_vkt_million_km"), errors="coerce")
    opt = pd.to_numeric(out.get("optimized_light_petrol_vkt_million_km"), errors="coerce")
    base_litres = pd.to_numeric(out.get("base_litres_per_100km"), errors="coerce")
    ped_rate = pd.to_numeric(out.get("ped_rate_nzd_per_litre"), errors="coerce")
    selected_vkt = raw + float(alpha) * (opt - raw)
    selected_volume = selected_vkt * base_litres / 100.0
    selected_revenue = selected_volume * ped_rate
    optimized_revenue = pd.to_numeric(out.get("gross_ped_revenue_optimized_million_nzd"), errors="coerce")
    optimized_total = pd.to_numeric(out.get("total_nltf_optimized_million_nzd"), errors="coerce")
    out["selected_ped_bridge_mode"] = mode
    out["selected_ped_bridge_label"] = label
    out["bridge_alpha"] = float(alpha)
    out["selected_light_petrol_vkt_million_km"] = selected_vkt
    out["selected_ped_volume_million_litres"] = selected_volume
    out["selected_gross_ped_revenue_million_nzd"] = selected_revenue
    out["selected_total_nltf_net_revenue_million_nzd"] = optimized_total + (selected_revenue - optimized_revenue)
    out["adjusted_light_petrol_vkt_million_km"] = selected_vkt
    out["ped_volume_million_litres"] = selected_volume
    out["gross_ped_revenue_million_nzd"] = selected_revenue
    out["total_nltf_net_revenue_million_nzd"] = out["selected_total_nltf_net_revenue_million_nzd"]
    return out


def _normalize_ped_bridge_mode(value: Any) -> str:
    text = str(value or PED_BRIDGE_DEFAULT_MODE).strip()
    for mode in PED_BRIDGE_MODE_IDS:
        if text.lower() == mode.lower() or text.lower() == PED_BRIDGE_MODE_LABELS.get(mode, "").lower():
            return mode
    return PED_BRIDGE_DEFAULT_MODE


def _ped_bridge_mode_display_label(record: dict[str, Any]) -> str:
    label = str(record.get("selected_ped_bridge_label") or PED_BRIDGE_MODE_LABELS[PED_BRIDGE_DEFAULT_MODE])
    alpha = _finite_float(record.get("bridge_alpha"), np.nan)
    delta = _finite_float(record.get("delta"), np.nan)
    parts = [label]
    if np.isfinite(alpha):
        parts.append(f"alpha {alpha:.0%}")
    if np.isfinite(delta) and abs(delta) > 1e-9:
        parts.append(f"delta {delta:+,.2f}")
    warning = str(record.get("gap_reason") or "").strip()
    if warning:
        parts.append(warning)
    return "; ".join(parts)


def ped_efficiency_adjustment_frame(
    ped_revenue_bridge_audit: pd.DataFrame,
    ped_efficiency_scenarios: pd.DataFrame,
    scenario_id: str = PED_EFFICIENCY_BASELINE_SCENARIO_ID,
) -> pd.DataFrame:
    """Calculate before/after PED litres, revenue and rollup deltas for one efficiency option."""

    if ped_revenue_bridge_audit is None or ped_revenue_bridge_audit.empty:
        return pd.DataFrame()
    scenarios = ped_efficiency_scenarios_frame() if ped_efficiency_scenarios is None or ped_efficiency_scenarios.empty else ped_efficiency_scenarios.copy()
    if "scenario_id" not in scenarios.columns:
        scenarios = ped_efficiency_scenarios_frame()
    selected = scenarios[scenarios["scenario_id"].astype(str).eq(str(scenario_id))].copy()
    if selected.empty:
        selected = scenarios[scenarios["scenario_id"].astype(str).eq(PED_EFFICIENCY_BASELINE_SCENARIO_ID)].copy()
    scenario = selected.iloc[0]
    gain_pct = float(pd.to_numeric(scenario.get("annual_efficiency_gain_pct"), errors="coerce") or 0.0)
    gain = max(gain_pct / 100.0, 0.0)
    start_fy = int(pd.to_numeric(scenario.get("start_fy"), errors="coerce") or REVENUE_FIRST_FORECAST_FY)
    end_fy = int(pd.to_numeric(scenario.get("end_fy"), errors="coerce") or start_fy)

    out = ped_revenue_bridge_audit.copy()
    out["FY_numeric"] = pd.to_numeric(out.get("FY"), errors="coerce")
    exponent = (out["FY_numeric"] - start_fy + 1).clip(lower=0, upper=max(end_fy - start_fy + 1, 0))
    multiplier = np.power(max(1.0 - gain, 0.0), exponent.fillna(0))
    base_litres = pd.to_numeric(out.get("base_litres_per_100km"), errors="coerce")
    light_vkt = pd.to_numeric(out.get("adjusted_light_petrol_vkt_million_km"), errors="coerce")
    ped_rate = pd.to_numeric(out.get("ped_rate_nzd_per_litre"), errors="coerce")
    baseline_volume = pd.to_numeric(out.get("ped_volume_million_litres"), errors="coerce")
    baseline_revenue = pd.to_numeric(out.get("gross_ped_revenue_million_nzd"), errors="coerce")
    baseline_total_nltf = pd.to_numeric(out.get("total_nltf_net_revenue_million_nzd"), errors="coerce")

    out["efficiency_scenario_id"] = str(scenario.get("scenario_id") or scenario_id)
    out["efficiency_label"] = str(scenario.get("display_name") or scenario_id)
    out["annual_efficiency_gain_pct"] = gain_pct
    out["efficiency_start_fy"] = start_fy
    out["efficiency_end_fy"] = end_fy
    out["efficiency_multiplier"] = multiplier
    out["adjusted_litres_per_100km"] = (base_litres * multiplier).clip(lower=0)
    out["baseline_ped_volume_million_litres"] = baseline_volume
    out["adjusted_ped_volume_million_litres"] = light_vkt * out["adjusted_litres_per_100km"] / 100.0
    out["ped_volume_delta_million_litres"] = out["adjusted_ped_volume_million_litres"] - baseline_volume
    out["baseline_gross_ped_revenue_million_nzd"] = baseline_revenue
    out["adjusted_gross_ped_revenue_million_nzd"] = out["adjusted_ped_volume_million_litres"] * ped_rate
    out["gross_ped_revenue_delta_million_nzd"] = out["adjusted_gross_ped_revenue_million_nzd"] - baseline_revenue
    out["gross_fed_revenue_delta_million_nzd"] = out["gross_ped_revenue_delta_million_nzd"]
    out["net_fed_revenue_delta_million_nzd"] = out["gross_ped_revenue_delta_million_nzd"]
    out["total_fed_ruc_net_revenue_delta_million_nzd"] = out["gross_ped_revenue_delta_million_nzd"]
    out["total_nltf_net_revenue_delta_million_nzd"] = out["gross_ped_revenue_delta_million_nzd"]
    out["baseline_total_nltf_net_revenue_million_nzd"] = baseline_total_nltf
    out["adjusted_total_nltf_net_revenue_million_nzd"] = baseline_total_nltf + out["total_nltf_net_revenue_delta_million_nzd"]
    out["reconciliation_status"] = np.where(
        pd.to_numeric(out["adjusted_ped_volume_million_litres"], errors="coerce").ge(0)
        & pd.to_numeric(out["adjusted_gross_ped_revenue_million_nzd"], errors="coerce").ge(0),
        "reconciled",
        "negative_component_gap",
    )
    out["sensitivity_note"] = PED_EFFICIENCY_DEFAULT_NOTE
    return out.drop(columns=["FY_numeric"], errors="ignore").reset_index(drop=True)


def apply_ped_efficiency_sensitivity(
    *,
    chart_rows: pd.DataFrame,
    line_reconciliation: pd.DataFrame,
    bridge_components: pd.DataFrame,
    future_revenue_forecasts: pd.DataFrame,
    ped_revenue_bridge_audit: pd.DataFrame,
    ped_efficiency_scenarios: pd.DataFrame,
    scenario_id: str = PED_EFFICIENCY_BASELINE_SCENARIO_ID,
) -> dict[str, pd.DataFrame]:
    """Apply a selected PED litres-intensity sensitivity to current-finalist copies."""

    adjustment = ped_efficiency_adjustment_frame(ped_revenue_bridge_audit, ped_efficiency_scenarios, scenario_id)
    adjusted_line = _apply_ped_efficiency_to_value_frame(
        line_reconciliation,
        adjustment,
        value_column="value",
        fy_column="FY",
        series_column="series_id",
        source_path_column="source_path",
    )
    formula_residuals = revenue_formula_residual_frame(adjusted_line) if not adjusted_line.empty else pd.DataFrame()
    adjusted_stack = revenue_stack_components_frame(adjusted_line, formula_residuals) if not adjusted_line.empty else pd.DataFrame()
    adjusted_chart = _apply_ped_efficiency_to_value_frame(
        chart_rows,
        adjustment,
        value_column="value",
        fy_column="june_year",
        series_column="series_id",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
        current_mask_column="trace_role",
    )
    adjusted_bridge = _apply_ped_efficiency_to_value_frame(
        bridge_components,
        adjustment,
        value_column="component_value",
        fy_column="period",
        series_column="stream",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    adjusted_future = _apply_ped_efficiency_to_value_frame(
        future_revenue_forecasts,
        adjustment,
        value_column="revenue_forecast_nzd",
        fy_column="period",
        series_column="stream",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    return {
        "chart_rows": adjusted_chart,
        "line_reconciliation": adjusted_line,
        "revenue_formula_residuals": formula_residuals,
        "revenue_stack_components": adjusted_stack,
        "revenue_bridge_components": adjusted_bridge,
        "future_revenue_forecasts": adjusted_future,
        "ped_efficiency_adjustment": adjustment,
    }


def _apply_ped_efficiency_to_value_frame(
    frame: pd.DataFrame,
    adjustment: pd.DataFrame,
    *,
    value_column: str,
    fy_column: str,
    series_column: str,
    source_path_column: str | None = None,
    scenario_column: str | None = None,
    fed_path_column: str | None = None,
    current_mask_column: str | None = None,
) -> pd.DataFrame:
    if frame is None or frame.empty or adjustment is None or adjustment.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    out = frame.copy()
    for column in [
        "ped_efficiency_scenario_id",
        "ped_efficiency_label",
        "annual_efficiency_gain_pct",
        "adjusted_litres_per_100km",
        "ped_efficiency_value_delta",
    ]:
        if column not in out.columns:
            out[column] = pd.NA
    if value_column not in out.columns or series_column not in out.columns:
        return out

    adjusted_lookup: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    adjustment = adjustment.copy()
    adjustment["FY_numeric"] = pd.to_numeric(adjustment.get("FY"), errors="coerce")
    for record in adjustment.to_dict("records"):
        if pd.isna(record.get("FY_numeric")):
            continue
        key = (
            str(record.get("source_path") or ""),
            int(record["FY_numeric"]),
            str(record.get("scenario_name") or ""),
            str(record.get("fed_path") or ""),
        )
        adjusted_lookup[key] = record

    out["_eff_fy"] = out.get(fy_column, pd.Series("", index=out.index)).map(_extract_fy_number)
    for idx, row in out.iterrows():
        if current_mask_column and str(row.get(current_mask_column) or "") not in {"", "in_house_current_finalist"}:
            continue
        series_id = str(row.get(series_column) or "")
        if series_id not in {
            "ped_volume",
            "gross_ped_revenue",
            "gross_fed_revenue",
            "net_fed_revenue",
            "total_gross_revenue",
            "total_revenue_net_admin",
            "total_fed_ruc_net_revenue",
            "total_nltf_net_revenue",
        }:
            continue
        fy = out.at[idx, "_eff_fy"]
        if pd.isna(fy):
            continue
        source_path = str(row.get(source_path_column) or row.get("trace_name") or "") if source_path_column else str(row.get("trace_name") or "")
        scenario_name = str(row.get(scenario_column) or row.get("scenario_name") or "") if scenario_column else str(row.get("scenario_name") or "")
        fed_path = str(row.get(fed_path_column) or row.get("fed_path") or "") if fed_path_column else str(row.get("fed_path") or "")
        record = adjusted_lookup.get((source_path, int(fy), scenario_name, fed_path))
        if not record:
            record = next(
                (
                    item
                    for key, item in adjusted_lookup.items()
                    if key[1] == int(fy) and key[2] == scenario_name and (not fed_path or key[3] == fed_path)
                ),
                None,
            )
        if not record:
            continue
        baseline_value = pd.to_numeric(row.get(value_column), errors="coerce")
        if series_id == "ped_volume":
            adjusted_value = record.get("adjusted_ped_volume_million_litres")
        elif series_id == "gross_ped_revenue":
            adjusted_value = record.get("adjusted_gross_ped_revenue_million_nzd")
        else:
            adjusted_value = baseline_value + pd.to_numeric(record.get("gross_ped_revenue_delta_million_nzd"), errors="coerce")
        if pd.isna(adjusted_value):
            continue
        out.at[idx, value_column] = float(adjusted_value)
        out.at[idx, "ped_efficiency_scenario_id"] = str(record.get("efficiency_scenario_id") or "")
        out.at[idx, "ped_efficiency_label"] = str(record.get("efficiency_label") or "")
        out.at[idx, "annual_efficiency_gain_pct"] = record.get("annual_efficiency_gain_pct")
        out.at[idx, "adjusted_litres_per_100km"] = record.get("adjusted_litres_per_100km")
        out.at[idx, "ped_efficiency_value_delta"] = float(adjusted_value) - float(baseline_value) if pd.notna(baseline_value) else pd.NA
    return out.drop(columns=["_eff_fy"], errors="ignore")


def _extract_fy_number(value: Any) -> float:
    text = str(value or "")
    if text.startswith("FY"):
        text = text[2:]
    try:
        return float(text)
    except Exception:
        return np.nan


def sensitivity_seed_inputs_frame() -> pd.DataFrame:
    """Compact repo-vendored seed evidence from Inputs (TI).

    The source workbook is audit evidence only. Streamlit loads this materialized
    table from the runtime pack and never opens the workbook at runtime.
    """

    columns = [
        "workbook_basename",
        "workbook_sha256",
        "sheet",
        "row",
        "cell",
        "label",
        "family",
        "stream",
        "scenario_level",
        "value",
        "unit",
        "note",
        "source_status",
    ]
    rows: list[dict[str, Any]] = []

    def add(row: int, cell: str, label: str, family: str, stream: str, level: str, value: float, unit: str, note: str) -> None:
        rows.append(
            {
                "workbook_basename": SENSITIVITY_SEED_WORKBOOK_BASENAME,
                "workbook_sha256": SENSITIVITY_SEED_WORKBOOK_SHA256,
                "sheet": SENSITIVITY_SEED_SHEET,
                "row": int(row),
                "cell": cell,
                "label": label,
                "family": family,
                "stream": stream,
                "scenario_level": level,
                "value": float(value),
                "unit": unit,
                "note": note,
                "source_status": "repo_vendored_seed_from_inputs_ti",
            }
        )

    for level, cell, value in [("Low", "C181", 0.005), ("Med", "D181", 0.010), ("High", "E181", 0.015)]:
        add(
            181,
            cell,
            "Annual efficiency improvement (Low/Med/High)",
            "fleet_efficiency",
            "PED",
            level,
            value,
            "fraction p.a.",
            "Applied as a post-model litres-intensity overlay after EV/PHEV migration and light-activity overlays.",
        )
    for level, cell, value in [("Low", "C206", 0.0025), ("Med", "D206", 0.005), ("High", "E206", 0.010)]:
        add(
            206,
            cell,
            "Annual shift % to public transport | Petrol (Low/Med/High)",
            "pt_mode_shift",
            "PED_LIGHT_PETROL",
            level,
            value,
            "fraction p.a.",
            "Applied to adjusted PED/light-petrol VKT from FY2030.",
        )
    for level, cell, value in [("Low", "C213", 0.0025), ("Med", "D213", 0.005), ("High", "E213", 0.010)]:
        for stream in ["LIGHT_RUC", "LIGHT_BEV", "PHEV"]:
            add(
                213,
                cell,
                "Annual shift % to public transport | LRUC (Low/Med/High)",
                "pt_mode_shift",
                stream,
                level,
                value,
                "fraction p.a.",
                "Applied equally to conventional Light RUC, Light BEV and PHEV so EV/PHEV shares do not change.",
            )
    for stream, row, cells in [
        ("PED", 266, [("Low", "C266", -0.100), ("Med", "D266", -0.144116582), ("High", "E266", -0.240)]),
        ("LIGHT_RUC", 267, [("Low", "C267", -0.080), ("Med", "D267", -0.120), ("High", "E267", -0.200)]),
        ("HEAVY_RUC", 268, [("Low", "C268", -0.050), ("Med", "D268", -0.100), ("High", "E268", -0.200)]),
    ]:
        for level, cell, value in cells:
            add(
                row,
                cell,
                {
                    "PED": "Petrol light vehicles | VKT elasticity to retail fuel price",
                    "LIGHT_RUC": "Light RUC vehicles | km elasticity to retail diesel price",
                    "HEAVY_RUC": "Heavy RUC vehicles | km elasticity to retail diesel price",
                }[stream],
                "demand_elasticity",
                stream,
                level,
                value,
                "elasticity",
                "Post-model demand overlay only; no oil/crude or pump-price pass-through is built in this runtime pack.",
            )
    return pd.DataFrame(rows, columns=columns)


def sensitivity_config_frame(
    seed_inputs: pd.DataFrame | None = None,
    *,
    end_fy: int | None = None,
) -> pd.DataFrame:
    """Governed low-complexity Revenue Outlook sensitivity controls."""

    seed = sensitivity_seed_inputs_frame() if seed_inputs is None or seed_inputs.empty else seed_inputs.copy()
    cutoff = int(end_fy or REVENUE_FIRST_FORECAST_FY)
    columns = [
        "family",
        "selection",
        "display_name",
        "stream",
        "value",
        "unit",
        "start_fy",
        "end_fy",
        "formula",
        "default_selected",
        "custom_allowed",
        "source_cells",
        "source_workbook_sha256",
        "cost_per_km_ratio_status",
        "notes",
    ]
    rows: list[dict[str, Any]] = []

    def source_cells(family: str, stream: str, selection: str) -> str:
        subset = seed[
            seed.get("family", pd.Series("", index=seed.index)).astype(str).eq(family)
            & seed.get("stream", pd.Series("", index=seed.index)).astype(str).eq(stream)
            & seed.get("scenario_level", pd.Series("", index=seed.index)).astype(str).eq(selection)
        ]
        if subset.empty and stream in {"LIGHT_BEV", "PHEV"}:
            subset = seed[
                seed.get("family", pd.Series("", index=seed.index)).astype(str).eq(family)
                & seed.get("stream", pd.Series("", index=seed.index)).astype(str).eq("LIGHT_RUC")
                & seed.get("scenario_level", pd.Series("", index=seed.index)).astype(str).eq(selection)
            ]
        return "; ".join(subset.get("cell", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())

    def add(
        family: str,
        selection: str,
        display_name: str,
        stream: str,
        value: float,
        unit: str,
        start_fy: int,
        formula: str,
        *,
        default: bool = False,
        custom_allowed: bool = False,
        cost_ratio_status: str = "not_applicable",
        notes: str = "",
    ) -> None:
        rows.append(
            {
                "family": family,
                "selection": selection,
                "display_name": display_name,
                "stream": stream,
                "value": float(value),
                "unit": unit,
                "start_fy": int(start_fy),
                "end_fy": cutoff,
                "formula": formula,
                "default_selected": bool(default),
                "custom_allowed": bool(custom_allowed),
                "source_cells": source_cells(family, stream, selection),
                "source_workbook_sha256": SENSITIVITY_SEED_WORKBOOK_SHA256,
                "cost_per_km_ratio_status": cost_ratio_status,
                "notes": notes or SENSITIVITY_DEFAULT_NOTE,
            }
        )

    add("fleet_efficiency", "Off", "Off", "PED", 0.0, "fraction p.a.", SENSITIVITY_FLEET_START_FY, "no overlay", default=True, custom_allowed=True)
    for selection, value in FLEET_EFFICIENCY_LEVELS.items():
        add(
            "fleet_efficiency",
            selection,
            {"Low": "Low 0.5% p.a.", "Med": "Med 1.0% p.a.", "High": "High 1.5% p.a."}[selection],
            "PED",
            value,
            "fraction p.a.",
            SENSITIVITY_FLEET_START_FY,
            "base_litres_per_100km*(1-eff_gain)^(FY-start_fy+1)",
            custom_allowed=True,
        )
    add(
        "fleet_efficiency",
        "Custom",
        "Custom",
        "PED",
        0.0,
        "fraction p.a.",
        SENSITIVITY_FLEET_START_FY,
        "base_litres_per_100km*(1-custom_eff_gain)^(FY-start_fy+1)",
        custom_allowed=True,
        notes="Custom value is session-only and is not a new model coefficient.",
    )

    for stream in ["PED_LIGHT_PETROL", "LIGHT_RUC", "LIGHT_BEV", "PHEV"]:
        add("pt_mode_shift", "Off", "Off", stream, 0.0, "fraction p.a.", SENSITIVITY_PT_START_FY, "no overlay", default=True, custom_allowed=True)
        for selection, value in PT_MODE_SHIFT_LEVELS.items():
            add(
                "pt_mode_shift",
                selection,
                {"Low": "Low 0.25% p.a.", "Med": "Med 0.5% p.a.", "High": "High 1.0% p.a."}[selection],
                stream,
                value,
                "fraction p.a.",
                SENSITIVITY_PT_START_FY,
                "(1-pt_shift_pct)^(FY-start_fy+1)",
                custom_allowed=True,
                notes="Applied equally across light vehicle components so EV/PHEV shares are unchanged.",
            )
        add(
            "pt_mode_shift",
            "Custom",
            "Custom",
            stream,
            0.0,
            "fraction p.a.",
            SENSITIVITY_PT_START_FY,
            "(1-custom_pt_shift_pct)^(FY-start_fy+1)",
            custom_allowed=True,
            notes="Custom value is session-only and is not a new model coefficient.",
        )

    for stream in ["PED", "LIGHT_RUC", "HEAVY_RUC"]:
        add(
            "demand_elasticity",
            "Off",
            "Off",
            stream,
            0.0,
            "elasticity",
            REVENUE_FIRST_FORECAST_FY,
            "no overlay",
            default=True,
            custom_allowed=True,
            cost_ratio_status="not_applicable",
        )
        for selection, value in DEMAND_ELASTICITY_LEVELS[stream].items():
            add(
                "demand_elasticity",
                selection,
                f"{selection} {value:g}",
                stream,
                value,
                "elasticity",
                REVENUE_FIRST_FORECAST_FY,
                "demand_factor=(cost_per_km_ratio)^elasticity",
                custom_allowed=True,
                cost_ratio_status="custom_required",
                notes="Requires a governed or custom cost/km ratio; no oil/crude pass-through is constructed here.",
            )
        add(
            "demand_elasticity",
            "Custom",
            "Custom",
            stream,
            0.0,
            "elasticity",
            REVENUE_FIRST_FORECAST_FY,
            "demand_factor=(cost_per_km_ratio)^custom_elasticity",
            custom_allowed=True,
            cost_ratio_status="custom_required",
            notes="Custom elasticity and ratio are session-only; no oil/crude pass-through is constructed here.",
        )
    return pd.DataFrame(rows, columns=columns)


def revenue_sensitivity_impact_audit_frame(
    line_reconciliation: pd.DataFrame,
    ped_revenue_bridge_audit: pd.DataFrame,
    sensitivity_config: pd.DataFrame | None = None,
    *,
    fleet_efficiency: str = "Off",
    pt_mode_shift: str = "Off",
    demand_elasticity: str = "Off",
    custom_fleet_efficiency_pct: float | None = None,
    custom_pt_shift_pct: float | None = None,
    custom_elasticity: float | None = None,
    custom_ped_elasticity: float | None = None,
    custom_light_elasticity: float | None = None,
    custom_heavy_elasticity: float | None = None,
    cost_per_km_ratio: float | None = None,
) -> pd.DataFrame:
    """Calculate selected post-model sensitivity impacts at FY/source-path grain."""

    columns = [
        "FY",
        "quarter",
        "period",
        "source_path",
        "scenario_name",
        "scenario_role",
        "fed_path",
        "selected_fleet_efficiency",
        "selected_pt_mode_shift",
        "selected_demand_elasticity",
        "stream",
        "series_id",
        "baseline",
        "adjusted",
        "delta",
        "unit",
        "formula",
        "eff_gain",
        "pt_factor",
        "elasticity",
        "cost_per_km_ratio",
        "demand_factor",
        "source_cells",
        "gap_reason",
        "status",
        "notes",
    ]
    if line_reconciliation is None or line_reconciliation.empty:
        return pd.DataFrame(columns=columns)

    config = sensitivity_config_frame(end_fy=REVENUE_FIRST_FORECAST_FY) if sensitivity_config is None or sensitivity_config.empty else sensitivity_config.copy()
    line = line_reconciliation.copy()
    line["FY_numeric"] = pd.to_numeric(line.get("FY"), errors="coerce")
    line = line[
        line.get("source_path", pd.Series("", index=line.index)).fillna("").astype(str).str.startswith("Current finalist")
        & line["FY_numeric"].ge(REVENUE_FIRST_FORECAST_FY)
    ].copy()
    if line.empty:
        return pd.DataFrame(columns=columns)

    ped_audit = pd.DataFrame() if ped_revenue_bridge_audit is None else ped_revenue_bridge_audit.copy()
    if not ped_audit.empty:
        ped_audit["FY_numeric"] = pd.to_numeric(ped_audit.get("FY"), errors="coerce")

    fleet_selection = _normalize_sensitivity_selection(fleet_efficiency)
    pt_selection = _normalize_sensitivity_selection(pt_mode_shift)
    demand_selection = _normalize_sensitivity_selection(demand_elasticity)
    eff_gain = _sensitivity_config_value(
        config,
        "fleet_efficiency",
        fleet_selection,
        "PED",
        custom_value=(custom_fleet_efficiency_pct / 100.0 if custom_fleet_efficiency_pct is not None else None),
    )
    pt_shift = _sensitivity_config_value(
        config,
        "pt_mode_shift",
        pt_selection,
        "LIGHT_RUC",
        custom_value=(custom_pt_shift_pct / 100.0 if custom_pt_shift_pct is not None else None),
    )
    ratio = _finite_float(cost_per_km_ratio, np.nan)
    demand_ratio_available = demand_selection == "Off" or (np.isfinite(ratio) and ratio > 0)
    if demand_selection == "Off":
        ratio = 1.0

    rows: list[dict[str, Any]] = []
    group_columns = ["source_path", "FY_numeric", "scenario_name", "scenario_role", "fed_path"]
    for keys, group in line.groupby(group_columns, dropna=False, sort=False):
        source_path, fy_value, scenario_name, scenario_role, fed_path = keys
        if pd.isna(fy_value):
            continue
        fy = int(fy_value)
        values = {
            str(row.get("series_id") or ""): row
            for row in group.to_dict("records")
        }

        def value(series_id: str) -> float:
            return _finite_float(values.get(series_id, {}).get("value"), np.nan)

        def unit(series_id: str) -> str:
            return str(values.get(series_id, {}).get("unit") or "")

        def source_cell(series_id: str) -> str:
            return str(values.get(series_id, {}).get("source_cell") or "")

        ped_record = pd.DataFrame()
        if not ped_audit.empty:
            ped_record = ped_audit[
                ped_audit.get("source_path", pd.Series("", index=ped_audit.index)).astype(str).eq(str(source_path))
                & ped_audit["FY_numeric"].eq(fy)
                & ped_audit.get("scenario_name", pd.Series("", index=ped_audit.index)).astype(str).eq(str(scenario_name))
                & ped_audit.get("fed_path", pd.Series("", index=ped_audit.index)).astype(str).eq(str(fed_path))
            ]
        ped_bridge = ped_record.iloc[0].to_dict() if not ped_record.empty else {}
        base_litres = _finite_float(ped_bridge.get("base_litres_per_100km"), np.nan)
        ped_rate = _finite_float(ped_bridge.get("ped_rate_nzd_per_litre"), np.nan)

        pt_exponent = max(fy - SENSITIVITY_PT_START_FY + 1, 0)
        pt_factor = float(np.power(max(1.0 - max(pt_shift, 0.0), 0.0), pt_exponent))
        fleet_exponent = max(fy - SENSITIVITY_FLEET_START_FY + 1, 0)
        litres_multiplier = float(np.power(max(1.0 - max(eff_gain, 0.0), 0.0), fleet_exponent))

        petrol_elasticity = _sensitivity_config_value(
            config,
            "demand_elasticity",
            demand_selection,
            "PED",
            custom_value=custom_ped_elasticity if custom_ped_elasticity is not None else custom_elasticity,
        )
        light_elasticity = _sensitivity_config_value(
            config,
            "demand_elasticity",
            demand_selection,
            "LIGHT_RUC",
            custom_value=custom_light_elasticity if custom_light_elasticity is not None else custom_elasticity,
        )
        heavy_elasticity = _sensitivity_config_value(
            config,
            "demand_elasticity",
            demand_selection,
            "HEAVY_RUC",
            custom_value=custom_heavy_elasticity if custom_heavy_elasticity is not None else custom_elasticity,
        )
        petrol_demand_factor = float(np.power(ratio, petrol_elasticity)) if demand_ratio_available else 1.0
        light_demand_factor = float(np.power(ratio, light_elasticity)) if demand_ratio_available else 1.0
        heavy_demand_factor = float(np.power(ratio, heavy_elasticity)) if demand_ratio_available else 1.0
        demand_gap = "" if demand_ratio_available else "cost_per_km_ratio_missing_custom_required"

        ped_activity_factor = pt_factor * petrol_demand_factor
        light_activity_factor = pt_factor * light_demand_factor
        heavy_activity_factor = heavy_demand_factor

        baseline_light_petrol = value("light_petrol_vkt")
        adjusted_light_petrol = baseline_light_petrol * ped_activity_factor if np.isfinite(baseline_light_petrol) else np.nan
        adjusted_litres = base_litres * litres_multiplier if np.isfinite(base_litres) else np.nan
        adjusted_ped_volume = adjusted_light_petrol * adjusted_litres / 100.0 if np.isfinite(adjusted_light_petrol) and np.isfinite(adjusted_litres) else np.nan
        adjusted_ped_revenue = adjusted_ped_volume * ped_rate if np.isfinite(adjusted_ped_volume) and np.isfinite(ped_rate) else np.nan

        adjusted: dict[str, float] = {}
        adjusted["light_petrol_vkt"] = adjusted_light_petrol
        adjusted["ped_volume"] = adjusted_ped_volume
        adjusted["gross_ped_revenue"] = adjusted_ped_revenue
        adjusted["ped_vkt_per_capita"] = value("ped_vkt_per_capita") * ped_activity_factor if np.isfinite(value("ped_vkt_per_capita")) else np.nan
        for series_id in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km", "current_light_ruc_total_modelled_km"]:
            base_value = value(series_id)
            adjusted[series_id] = base_value * light_activity_factor if np.isfinite(base_value) else np.nan
        for km_id, revenue_id in [
            ("light_ruc_net_km", "light_ruc_net_revenue"),
            ("light_bev_ruc_net_km", "light_bev_ruc_net_revenue"),
            ("phev_ruc_net_km", "phev_ruc_net_revenue"),
        ]:
            base_km = value(km_id)
            base_rev = value(revenue_id)
            rate = base_rev / base_km if np.isfinite(base_rev) and np.isfinite(base_km) and abs(base_km) > 1e-12 else np.nan
            adjusted[revenue_id] = adjusted.get(km_id, np.nan) * rate if np.isfinite(adjusted.get(km_id, np.nan)) and np.isfinite(rate) else np.nan
        for series_id in ["heavy_ruc_net_km"]:
            base_value = value(series_id)
            adjusted[series_id] = base_value * heavy_activity_factor if np.isfinite(base_value) else np.nan
        heavy_rate = value("heavy_ruc_net_revenue") / value("heavy_ruc_net_km") if np.isfinite(value("heavy_ruc_net_revenue")) and np.isfinite(value("heavy_ruc_net_km")) and abs(value("heavy_ruc_net_km")) > 1e-12 else np.nan
        adjusted["heavy_ruc_net_revenue"] = adjusted.get("heavy_ruc_net_km", np.nan) * heavy_rate if np.isfinite(adjusted.get("heavy_ruc_net_km", np.nan)) and np.isfinite(heavy_rate) else np.nan

        ped_delta = _delta(value("gross_ped_revenue"), adjusted.get("gross_ped_revenue"))
        ruc_delta = sum(
            _delta(value(series_id), adjusted.get(series_id))
            for series_id in [
                "light_ruc_net_revenue",
                "light_bev_ruc_net_revenue",
                "phev_ruc_net_revenue",
                "heavy_ruc_net_revenue",
            ]
        )
        adjusted["gross_ruc_revenue"] = value("gross_ruc_revenue") + ruc_delta
        adjusted["ruc_revenue_net_admin"] = value("ruc_revenue_net_admin") + ruc_delta
        adjusted["total_ruc_net_revenue"] = value("total_ruc_net_revenue") + ruc_delta
        adjusted["gross_fed_revenue"] = value("gross_fed_revenue") + ped_delta
        adjusted["net_fed_revenue"] = value("net_fed_revenue") + ped_delta
        adjusted["total_gross_revenue"] = value("total_gross_revenue") + ped_delta + ruc_delta
        adjusted["total_revenue_net_admin"] = value("total_revenue_net_admin") + ped_delta + ruc_delta
        adjusted["total_fed_ruc_net_revenue"] = value("total_fed_ruc_net_revenue") + ped_delta + ruc_delta
        adjusted["total_nltf_net_revenue"] = value("total_nltf_net_revenue") + ped_delta + ruc_delta

        def add_row(series_id: str, stream: str, formula: str, elasticity: float, demand_factor: float, source_cells: str) -> None:
            baseline = value(series_id)
            adjusted_value = adjusted.get(series_id, baseline)
            if not np.isfinite(baseline) or not np.isfinite(adjusted_value):
                return
            rows.append(
                {
                    "FY": fy,
                    "quarter": "",
                    "period": f"FY{fy}",
                    "source_path": str(source_path),
                    "scenario_name": str(scenario_name),
                    "scenario_role": str(scenario_role),
                    "fed_path": str(fed_path),
                    "selected_fleet_efficiency": fleet_selection,
                    "selected_pt_mode_shift": pt_selection,
                    "selected_demand_elasticity": demand_selection,
                    "stream": stream,
                    "series_id": series_id,
                    "baseline": baseline,
                    "adjusted": adjusted_value,
                    "delta": adjusted_value - baseline,
                    "unit": unit(series_id),
                    "formula": formula,
                    "eff_gain": eff_gain,
                    "pt_factor": pt_factor if stream in {"PED", "LIGHT_RUC", "LIGHT_BEV", "PHEV"} else 1.0,
                    "elasticity": elasticity,
                    "cost_per_km_ratio": ratio if demand_selection != "Off" else 1.0,
                    "demand_factor": demand_factor,
                    "source_cells": "; ".join(part for part in [source_cell(series_id), source_cells] if str(part).strip()),
                    "gap_reason": demand_gap,
                    "status": "gap_no_demand_overlay" if demand_gap else "adjusted",
                    "notes": SENSITIVITY_DEFAULT_NOTE,
                }
            )

        fleet_cells = _sensitivity_source_cells(config, "fleet_efficiency", "PED", fleet_selection)
        pt_ped_cells = _sensitivity_source_cells(config, "pt_mode_shift", "PED_LIGHT_PETROL", pt_selection)
        pt_light_cells = _sensitivity_source_cells(config, "pt_mode_shift", "LIGHT_RUC", pt_selection)
        demand_ped_cells = _sensitivity_source_cells(config, "demand_elasticity", "PED", demand_selection)
        demand_light_cells = _sensitivity_source_cells(config, "demand_elasticity", "LIGHT_RUC", demand_selection)
        demand_heavy_cells = _sensitivity_source_cells(config, "demand_elasticity", "HEAVY_RUC", demand_selection)
        add_row("light_petrol_vkt", "PED", "light_petrol_vkt * pt_factor * petrol_demand_factor", petrol_elasticity, petrol_demand_factor, f"{pt_ped_cells}; {demand_ped_cells}")
        add_row("ped_vkt_per_capita", "PED", "ped_vkt_per_capita * pt_factor * petrol_demand_factor", petrol_elasticity, petrol_demand_factor, f"{pt_ped_cells}; {demand_ped_cells}")
        add_row("ped_volume", "PED", "adjusted_light_petrol_vkt * adjusted_litres_per_100km / 100", petrol_elasticity, petrol_demand_factor, f"{pt_ped_cells}; {demand_ped_cells}; {fleet_cells}")
        add_row("gross_ped_revenue", "PED", "adjusted_ped_volume * ped_rate", petrol_elasticity, petrol_demand_factor, f"{pt_ped_cells}; {demand_ped_cells}; {fleet_cells}")
        for series_id in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km", "current_light_ruc_total_modelled_km"]:
            stream = "LIGHT_RUC" if series_id in {"light_ruc_net_km", "current_light_ruc_total_modelled_km"} else ("LIGHT_BEV" if "bev" in series_id else "PHEV")
            add_row(series_id, stream, f"{series_id} * pt_factor * light_demand_factor", light_elasticity, light_demand_factor, f"{pt_light_cells}; {demand_light_cells}")
        for series_id in ["light_ruc_net_revenue", "light_bev_ruc_net_revenue", "phev_ruc_net_revenue"]:
            stream = "LIGHT_RUC" if series_id == "light_ruc_net_revenue" else ("LIGHT_BEV" if "bev" in series_id else "PHEV")
            add_row(series_id, stream, f"{series_id} effective rate applied to adjusted km", light_elasticity, light_demand_factor, f"{pt_light_cells}; {demand_light_cells}")
        add_row("heavy_ruc_net_km", "HEAVY_RUC", "heavy_ruc_net_km * heavy_demand_factor", heavy_elasticity, heavy_demand_factor, demand_heavy_cells)
        add_row("heavy_ruc_net_revenue", "HEAVY_RUC", "heavy_ruc_net_revenue effective rate applied to adjusted km", heavy_elasticity, heavy_demand_factor, demand_heavy_cells)
        for series_id in sorted(SENSITIVITY_ROLLUP_SERIES, key=lambda x: REVENUE_STACK_SERIES_ORDER.get(x, 999)):
            add_row(series_id, "ROLLUP", f"{series_id} + PED/RUC component deltas", 0.0, 1.0, "")

    return pd.DataFrame(rows, columns=columns)


def apply_revenue_sensitivity_layer(
    *,
    chart_rows: pd.DataFrame,
    line_reconciliation: pd.DataFrame,
    bridge_components: pd.DataFrame,
    future_revenue_forecasts: pd.DataFrame,
    ped_revenue_bridge_audit: pd.DataFrame,
    sensitivity_config: pd.DataFrame,
    fleet_efficiency: str = "Off",
    pt_mode_shift: str = "Off",
    demand_elasticity: str = "Off",
    custom_fleet_efficiency_pct: float | None = None,
    custom_pt_shift_pct: float | None = None,
    custom_elasticity: float | None = None,
    custom_ped_elasticity: float | None = None,
    custom_light_elasticity: float | None = None,
    custom_heavy_elasticity: float | None = None,
    cost_per_km_ratio: float | None = None,
) -> dict[str, pd.DataFrame]:
    """Apply governed post-model Revenue Outlook sensitivities to current-finalist copies."""

    audit = revenue_sensitivity_impact_audit_frame(
        line_reconciliation,
        ped_revenue_bridge_audit,
        sensitivity_config,
        fleet_efficiency=fleet_efficiency,
        pt_mode_shift=pt_mode_shift,
        demand_elasticity=demand_elasticity,
        custom_fleet_efficiency_pct=custom_fleet_efficiency_pct,
        custom_pt_shift_pct=custom_pt_shift_pct,
        custom_elasticity=custom_elasticity,
        custom_ped_elasticity=custom_ped_elasticity,
        custom_light_elasticity=custom_light_elasticity,
        custom_heavy_elasticity=custom_heavy_elasticity,
        cost_per_km_ratio=cost_per_km_ratio,
    )
    if _sensitivity_is_off(fleet_efficiency, pt_mode_shift, demand_elasticity):
        adjusted_line = line_reconciliation.copy()
        formula_residuals = revenue_formula_residual_frame(adjusted_line) if adjusted_line is not None and not adjusted_line.empty else pd.DataFrame()
        stack_components = revenue_stack_components_frame(adjusted_line, formula_residuals) if adjusted_line is not None and not adjusted_line.empty else pd.DataFrame()
        return {
            "chart_rows": chart_rows.copy(),
            "line_reconciliation": adjusted_line,
            "revenue_formula_residuals": formula_residuals,
            "revenue_stack_components": stack_components,
            "revenue_bridge_components": bridge_components.copy(),
            "future_revenue_forecasts": future_revenue_forecasts.copy(),
            "sensitivity_impact_audit": audit,
        }

    adjusted_line = _apply_sensitivity_audit_to_frame(
        line_reconciliation,
        audit,
        value_column="value",
        fy_column="FY",
        series_column="series_id",
        source_path_column="source_path",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    formula_residuals = revenue_formula_residual_frame(adjusted_line) if adjusted_line is not None and not adjusted_line.empty else pd.DataFrame()
    adjusted_stack = revenue_stack_components_frame(adjusted_line, formula_residuals) if adjusted_line is not None and not adjusted_line.empty else pd.DataFrame()
    adjusted_chart = _apply_sensitivity_audit_to_frame(
        chart_rows,
        audit,
        value_column="value",
        fy_column="june_year",
        series_column="series_id",
        source_path_column="trace_name",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
        current_mask_column="trace_role",
    )
    adjusted_bridge = _apply_sensitivity_audit_to_frame(
        bridge_components,
        audit,
        value_column="component_value",
        fy_column="period",
        series_column="stream",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    adjusted_future = _apply_sensitivity_audit_to_frame(
        future_revenue_forecasts,
        audit,
        value_column="revenue_forecast_nzd",
        fy_column="period",
        series_column="stream",
        scenario_column="scenario_name",
        fed_path_column="fed_path",
    )
    return {
        "chart_rows": adjusted_chart,
        "line_reconciliation": adjusted_line,
        "revenue_formula_residuals": formula_residuals,
        "revenue_stack_components": adjusted_stack,
        "revenue_bridge_components": adjusted_bridge,
        "future_revenue_forecasts": adjusted_future,
        "sensitivity_impact_audit": audit,
    }


def _apply_sensitivity_audit_to_frame(
    frame: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    value_column: str,
    fy_column: str,
    series_column: str,
    source_path_column: str | None = None,
    scenario_column: str | None = None,
    fed_path_column: str | None = None,
    current_mask_column: str | None = None,
) -> pd.DataFrame:
    if frame is None or frame.empty or audit is None or audit.empty:
        return pd.DataFrame() if frame is None else frame.copy()
    out = frame.copy()
    for column in [
        "revenue_sensitivity_label",
        "revenue_sensitivity_value_delta",
        "pt_factor",
        "demand_factor",
        "adjusted_litres_per_100km",
        "ped_efficiency_label",
    ]:
        if column not in out.columns:
            out[column] = pd.NA
    audit = audit.copy()
    audit["FY_numeric"] = pd.to_numeric(audit.get("FY"), errors="coerce")
    lookup: dict[tuple[str, int, str, str, str], dict[str, Any]] = {}
    for record in audit.to_dict("records"):
        if pd.isna(record.get("FY_numeric")):
            continue
        lookup[
            (
                str(record.get("source_path") or ""),
                int(record["FY_numeric"]),
                str(record.get("scenario_name") or ""),
                str(record.get("fed_path") or ""),
                str(record.get("series_id") or ""),
            )
        ] = record

    out["_sensitivity_fy"] = out.get(fy_column, pd.Series("", index=out.index)).map(_extract_fy_number)
    for idx, row in out.iterrows():
        if current_mask_column and str(row.get(current_mask_column) or "") not in {"", "in_house_current_finalist"}:
            continue
        fy = out.at[idx, "_sensitivity_fy"]
        if pd.isna(fy):
            continue
        series_id = str(row.get(series_column) or "")
        source_path = str(row.get(source_path_column) or "") if source_path_column else ""
        scenario_name = str(row.get(scenario_column) or "") if scenario_column else ""
        fed_path = str(row.get(fed_path_column) or "") if fed_path_column else ""
        record = lookup.get((source_path, int(fy), scenario_name, fed_path, series_id))
        if not record:
            record = next(
                (
                    item
                    for key, item in lookup.items()
                    if key[1] == int(fy)
                    and key[2] == scenario_name
                    and key[4] == series_id
                    and (not fed_path or key[3] == fed_path)
                    and (not source_path or key[0] == source_path)
                ),
                None,
            )
        if not record:
            continue
        adjusted_value = _finite_float(record.get("adjusted"), np.nan)
        baseline_value = _finite_float(row.get(value_column), np.nan)
        if not np.isfinite(adjusted_value):
            continue
        out.at[idx, value_column] = adjusted_value
        out.at[idx, "revenue_sensitivity_label"] = _sensitivity_display_label(record)
        out.at[idx, "revenue_sensitivity_value_delta"] = adjusted_value - baseline_value if np.isfinite(baseline_value) else pd.NA
        out.at[idx, "pt_factor"] = record.get("pt_factor")
        out.at[idx, "demand_factor"] = record.get("demand_factor")
        if series_id in {"ped_volume", "gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue", "total_fed_ruc_net_revenue", "total_nltf_net_revenue"}:
            out.at[idx, "ped_efficiency_label"] = str(record.get("selected_fleet_efficiency") or "")
    return out.drop(columns=["_sensitivity_fy"], errors="ignore")


def _normalize_sensitivity_selection(value: Any) -> str:
    text = str(value or "Off").strip()
    if text.lower() == "medium":
        return "Med"
    for option in SENSITIVITY_LEVELS:
        if text.lower() == option.lower():
            return option
    return "Off"


def _sensitivity_is_off(fleet_efficiency: str, pt_mode_shift: str, demand_elasticity: str) -> bool:
    return (
        _normalize_sensitivity_selection(fleet_efficiency) == "Off"
        and _normalize_sensitivity_selection(pt_mode_shift) == "Off"
        and _normalize_sensitivity_selection(demand_elasticity) == "Off"
    )


def _sensitivity_config_value(
    config: pd.DataFrame,
    family: str,
    selection: str,
    stream: str,
    *,
    custom_value: float | None = None,
) -> float:
    normalized = _normalize_sensitivity_selection(selection)
    if normalized == "Custom":
        return max(_finite_float(custom_value, 0.0), -10.0)
    if normalized == "Off":
        return 0.0
    if config is None or config.empty:
        return 0.0
    rows = config[
        config.get("family", pd.Series("", index=config.index)).astype(str).eq(family)
        & config.get("selection", pd.Series("", index=config.index)).astype(str).eq(normalized)
        & config.get("stream", pd.Series("", index=config.index)).astype(str).eq(stream)
    ]
    if rows.empty and stream in {"LIGHT_BEV", "PHEV"}:
        rows = config[
            config.get("family", pd.Series("", index=config.index)).astype(str).eq(family)
            & config.get("selection", pd.Series("", index=config.index)).astype(str).eq(normalized)
            & config.get("stream", pd.Series("", index=config.index)).astype(str).eq("LIGHT_RUC")
        ]
    if rows.empty:
        return 0.0
    return _finite_float(rows.iloc[0].get("value"), 0.0)


def _sensitivity_source_cells(config: pd.DataFrame, family: str, stream: str, selection: str) -> str:
    normalized = _normalize_sensitivity_selection(selection)
    if normalized in {"Off", "Custom"} or config is None or config.empty:
        return ""
    rows = config[
        config.get("family", pd.Series("", index=config.index)).astype(str).eq(family)
        & config.get("selection", pd.Series("", index=config.index)).astype(str).eq(normalized)
        & config.get("stream", pd.Series("", index=config.index)).astype(str).eq(stream)
    ]
    if rows.empty and stream in {"LIGHT_BEV", "PHEV"}:
        rows = config[
            config.get("family", pd.Series("", index=config.index)).astype(str).eq(family)
            & config.get("selection", pd.Series("", index=config.index)).astype(str).eq(normalized)
            & config.get("stream", pd.Series("", index=config.index)).astype(str).eq("LIGHT_RUC")
        ]
    if rows.empty:
        return ""
    return str(rows.iloc[0].get("source_cells") or "")


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = pd.to_numeric(value, errors="coerce")
    except Exception:
        return default
    if pd.isna(numeric):
        return default
    try:
        return float(numeric)
    except Exception:
        return default


def _delta(baseline: float, adjusted: float | None) -> float:
    if adjusted is None or not np.isfinite(baseline) or not np.isfinite(adjusted):
        return 0.0
    return float(adjusted) - float(baseline)


def _sensitivity_display_label(record: dict[str, Any]) -> str:
    parts = [
        f"Fleet {record.get('selected_fleet_efficiency')}",
        f"PT {record.get('selected_pt_mode_shift')}",
        f"Elasticity {record.get('selected_demand_elasticity')}",
    ]
    return "; ".join(str(part) for part in parts if "Off" not in str(part))


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
    scenario_input_wide = _read_optional_parquet(base / SCENARIO_INPUT_DIRNAME / f"{SCENARIO_INPUT_WIDE_STEM}.parquet")
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
        scenario_input_wide=scenario_input_wide,
    )
    if current.empty:
        raise ValueError("Cannot rebuild current Revenue Outlook runtime pack: current finalist annual rows are missing.")
    runtime_cutoff_fy, runtime_cutoff_audit = _runtime_cutoff_fy_and_audit(current, mbu26_pack.official_annual)
    current = _filter_frame_to_runtime_cutoff(current, runtime_cutoff_fy)
    runtime_official_annual = _filter_frame_to_runtime_cutoff(mbu26_pack.official_annual, runtime_cutoff_fy)
    line_reconciliation = revenue_line_reconciliation_frame(
        mbu26_official_annual=runtime_official_annual,
        current_forecast_annual=current,
    )
    formula_residuals = revenue_formula_residual_frame(line_reconciliation)
    stack_components = revenue_stack_components_frame(line_reconciliation, formula_residuals)
    ev_phev_split_assumptions = ev_phev_split_assumptions_frame(
        runtime_official_annual,
        current_forecast_annual=current,
        repo_root=root,
    )
    ev_phev_ped_light_drift_assumptions = ev_phev_ped_light_migration_assumptions_from_mbu26(
        current_outlook_chart_rows=existing_chart_rows,
        mbu26_official_annual=mbu26_pack.official_annual,
        scenario_input_wide=scenario_input_wide,
        include_disabled_extension_boundary=True,
    )
    ev_phev_ped_light_drift_assumptions = _filter_frame_to_runtime_cutoff(
        ev_phev_ped_light_drift_assumptions,
        runtime_cutoff_fy,
    )
    ped_revenue_bridge_audit = ped_revenue_bridge_audit_frame(
        line_reconciliation,
        ev_phev_ped_light_drift_assumptions,
    )
    ped_bridge_shape_fit_metrics = ped_bridge_shape_fit_metrics_frame(ped_revenue_bridge_audit)
    ped_bridge_mode_config = ped_bridge_mode_config_frame()
    ped_efficiency_scenarios = ped_efficiency_scenarios_frame(end_fy=runtime_cutoff_fy)
    sensitivity_seed_inputs = sensitivity_seed_inputs_frame()
    sensitivity_config = sensitivity_config_frame(sensitivity_seed_inputs, end_fy=runtime_cutoff_fy)
    sensitivity_impact_audit = revenue_sensitivity_impact_audit_frame(
        line_reconciliation,
        ped_revenue_bridge_audit,
        sensitivity_config,
        fleet_efficiency="Off",
        pt_mode_shift="Off",
        demand_elasticity="Off",
    )
    scenarios = _runtime_scenario_records(existing_manifest, current)
    scenario_role_contract = scenario_role_contract_frame(
        current_forecast_annual=current,
        scenarios=scenarios,
        repo_root=root,
    )
    scenario_input_manifest = _current_scenario_input_manifest(base, root)
    scenario_input_long = _read_optional_parquet(
        base / SCENARIO_INPUT_DIRNAME / f"{SCENARIO_INPUT_LONG_STEM}.parquet"
    )
    scenario_input_delta_audit = _scenario_input_delta_audit_from_long(scenario_input_long, scenarios)
    scenario_feature_lineage = _read_optional_parquet(
        base / SCENARIO_INPUT_DIRNAME / f"{SCENARIO_FEATURE_LINEAGE_STEM}.parquet"
    )
    if scenario_feature_lineage.empty:
        scenario_feature_lineage = _read_optional_parquet(base / "scenario_feature_lineage.parquet")
    scenario_input_replay_mismatch_report = _scenario_input_replay_mismatch_report(
        current,
        scenario_input_wide,
        scenario_input_manifest,
        promoted_chart_rows=existing_chart_rows,
        repo_root=root,
    )
    replay_mismatches = scenario_input_replay_mismatch_report[
        scenario_input_replay_mismatch_report.get("mismatch_status", pd.Series("", index=scenario_input_replay_mismatch_report.index))
        .astype(str)
        .eq("mismatch")
    ].copy()
    if not replay_mismatches.empty:
        prepared_report = _prepare_frame_for_output(scenario_input_replay_mismatch_report)
        prepared_report.to_parquet(base / "scenario_input_replay_mismatch_report.parquet", index=False)
        prepared_report.to_csv(base / "scenario_input_replay_mismatch_report.csv", index=False)
        raise ValueError(
            "Committed scenario input replay verification failed; see "
            f"{_repo_relative(root, base / 'scenario_input_replay_mismatch_report.csv')}"
        )

    series_meta = _runtime_series_metadata(mbu26_pack.series_trace_contract)
    quarterly_inputs = _runtime_quarterly_activity_inputs(existing_chart_rows, series_meta, scenario_role_contract=scenario_role_contract)
    actual_rows = _runtime_mbu26_actual_rows(runtime_official_annual, series_meta)
    current_rows = _runtime_current_rows(current, series_meta, scenario_role_contract=scenario_role_contract)
    mbu26_official_rows = _runtime_mbu26_official_rows(runtime_official_annual, series_meta)
    chart_rows = pd.concat(
        [quarterly_inputs, actual_rows, current_rows, mbu26_official_rows],
        ignore_index=True,
        sort=False,
    )
    if chart_rows.empty:
        raise ValueError("Cannot rebuild current Revenue Outlook runtime pack: no chart rows were produced.")
    chart_rows = _normalize_runtime_chart_rows(chart_rows)
    chart_rows = _suppress_unreconciled_current_chart_rows(chart_rows, formula_residuals)
    chart_rows = _filter_frame_to_runtime_cutoff(chart_rows, runtime_cutoff_fy)
    future_revenue = _runtime_future_revenue_forecasts(current, series_meta)
    bridge_components = _runtime_bridge_components(current, series_meta)
    trace_audit = _runtime_trace_audit(chart_rows)
    fan_availability, fan_band_rows = revenue_outlook_fan_tables(chart_rows, repo_root=root)

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
            PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
        ],
        "runtime_source_layers": {
            "A_actuals": "MBU26 annual source rows through last complete FY2025",
            "B_official_comparator": "MBU26 official forecast rows for FY2026+",
            "C_current_finalist_activity": "Promoted quarterly finalist outputs annualized by June year",
            "D_hybrid_current_revenue": "Only PED, Light RUC and Heavy RUC revenue are replaced; all other rows use MBU26 official components.",
            "E_ev_phev_split_audit": (
                "Current finalist Light RUC is governed as a total light-RUC net-km model input. The optimized migration "
                "layer allocates BEV/PHEV uptake between PED/light-petrol and total Light RUC before revenue rates are applied."
            ),
            "F_runtime_cutoff": (
                f"No extrapolated model extension is used in the current Revenue Outlook runtime path; "
                f"current-finalist comparisons stop at FY{runtime_cutoff_fy}."
            ),
        },
        "period_rule": {
            "last_complete_actual_fy": REVENUE_LAST_COMPLETE_ACTUAL_FY,
            "first_forecast_quarter": REVENUE_FIRST_FORECAST_QUARTER,
            "model_training_cutoff": REVENUE_MODEL_TRAINING_CUTOFF,
            "runtime_cutoff_fy": runtime_cutoff_fy,
            "fy2026_nowcast": "2025Q3+2025Q4 source actuals plus 2026Q1+2026Q2 current finalist forecasts",
            "rule": (
                "Actual line ends FY2025; FY2026 actual-to-date rows are nowcast inputs only and are not plotted as actuals. "
                f"Current-finalist comparative charts and runtime calculations stop at FY{runtime_cutoff_fy}, "
                "the last governed common non-extrapolated horizon."
            ),
        },
        "data_vintage_manifest_notes": {
            "runtime_cutoff": (
                f"No extrapolated model extension is used; last displayed/current calculation FY is FY{runtime_cutoff_fy}. "
                "Current-finalist paths stop where governed model and source assumptions stop."
            ),
            "official_horizon_note": (
                f"Comparative charts stop at FY{runtime_cutoff_fy}."
                if _max_numeric_year(mbu26_pack.official_annual, "FY") and int(_max_numeric_year(mbu26_pack.official_annual, "FY") or 0) > runtime_cutoff_fy
                else f"Comparative charts stop at FY{runtime_cutoff_fy}."
            ),
            "light_ruc_target_semantics": (
                "Business rule update: current-finalist Light RUC is treated as total light-RUC net km, while EV/PHEV "
                "migration is sourced from both current PED/light-petrol activity and total Light RUC using an optimized "
                "deterministic bridge calibrated to MBU26 light-mobility proportions. BEV/PHEV are not fixed add-ons."
            ),
            "ev_phev_migration_allocation": (
                "Default lambda_mode is optimized; alternatives are recorded for audit only and do not replace the current "
                "runtime path unless explicitly selected in governance review."
            ),
            "scenario_role_contract": (
                "PED VKT per capita is a behavioural intensity metric. Value-changing comparison PED intensity is labelled "
                "as a behavioural comparison path; aggregate and revenue rows keep comparison traces."
            ),
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
            "EV_PHEV_MIGRATION": "Optimized lambda allocates EV/PHEV uptake between PED/light-petrol and current finalist total Light RUC to match MBU26 light-mobility proportions with a smoothness penalty.",
            "PED": "PED revenue = adjusted PED/light-petrol VKT after optimized EV/PHEV migration * MBU26 litres/100km * MBU26 gross PED rate.",
            "LIGHT_RUC": "Light RUC revenue = optimized conventional Light RUC km after EV/PHEV migration * MBU26 conventional Light effective rate.",
            "HEAVY_RUC": "Heavy RUC revenue = current finalist net km * MBU26 effective Heavy RUC rate.",
            "ROLLUPS": "Gross FED, Net FED, Total RUC, Total RUC+PED and Total NLTF recalculate optimized PED, conventional Light RUC, Light BEV, PHEV and Heavy RUC replacement lines plus MBU26 fixed components.",
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
                "Legacy continuity audit for MBU26 conventional Light, Light BEV and PHEV km/revenue shares and rates, "
                "with old fixed-add-on comparator fields. The active current path is the PED+Light migration audit."
            ),
            "allocation_status": _ev_phev_allocation_status(ev_phev_split_assumptions),
        },
        "ev_phev_ped_light_drift_assumptions": {
            "repo_relative_path": _repo_relative(root, base / "ev_phev_ped_light_drift_assumptions.csv"),
            "scope": (
                "Deterministic EV/PHEV migration bridge over current PED/light-petrol activity and current finalist total Light RUC, "
                "including optimized, Light-only, PED-only and MBU-ratio lambda modes."
            ),
            "default_lambda_mode": EV_PHEV_MIGRATION_DEFAULT_MODE,
            "lambda_smoothness_penalty": EV_PHEV_MIGRATION_SMOOTHNESS_PENALTY,
            "runtime_mode": EV_PHEV_MIGRATION_DEFAULT_MODE,
        },
        "ped_revenue_bridge_audit": {
            "repo_relative_path": _repo_relative(root, base / "ped_revenue_bridge_audit.csv"),
            "scope": (
                "Current-finalist PED bridge decomposition by FY/source path: VKTpc, scenario population, raw VKTpc x population, "
                "optimized EV/PHEV migration VKT, PED volume/revenue, Total NLTF, MBU26 comparators and fallback flags."
            ),
            "status": "available" if not ped_revenue_bridge_audit.empty else "missing",
            "source": "data/current_revenue_outlook/revenue_line_reconciliation.csv; data/current_revenue_outlook/ev_phev_ped_light_drift_assumptions.csv",
            "default_bridge_mode": PED_BRIDGE_DEFAULT_MODE,
            "population_proxy_warning_rows": int(
                ped_revenue_bridge_audit.get("population_fallback_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()
            )
            if not ped_revenue_bridge_audit.empty
            else 0,
        },
        "ped_bridge_shape_fit_metrics": {
            "repo_relative_path": _repo_relative(root, base / "ped_bridge_shape_fit_metrics.csv"),
            "scope": "FY2026-FY2050 raw-vs-optimized PED bridge shape-fit metrics against MBU26 comparators.",
            "status": "available" if not ped_bridge_shape_fit_metrics.empty else "missing",
        },
        "ped_bridge_mode_config": {
            "repo_relative_path": _repo_relative(root, base / "ped_bridge_mode_config.csv"),
            "scope": "Audit bridge modes for raw, blend and optimized PED bridge overlays. Raw is the default runtime mode.",
            "default_bridge_mode": PED_BRIDGE_DEFAULT_MODE,
            "note": PED_BRIDGE_NOTE,
            "status": "available",
        },
        "ped_efficiency_scenarios": {
            "repo_relative_path": _repo_relative(root, base / "ped_efficiency_scenarios.csv"),
            "default_scenario_id": PED_EFFICIENCY_BASELINE_SCENARIO_ID,
            "default_runtime_treatment": "0pct_no_change",
            "scope": "Governed PED fleet-efficiency sensitivity over litres per 100km after EV/PHEV migration.",
            "note": PED_EFFICIENCY_DEFAULT_NOTE,
        },
        "sensitivity_seed_inputs": {
            "repo_relative_path": _repo_relative(root, base / "sensitivity_seed_inputs.csv"),
            "source_workbook_basename": SENSITIVITY_SEED_WORKBOOK_BASENAME,
            "source_workbook_sha256": SENSITIVITY_SEED_WORKBOOK_SHA256,
            "source_sheet": SENSITIVITY_SEED_SHEET,
            "status": "available",
            "scope": "Compact Inputs (TI) seed values for fleet efficiency, PT mode shift and demand elasticity only.",
            "excluded_scope": "Fleet transition, crude/oil shock, crude-to-pump and ETS/margin/tax pass-through are not runtime sensitivities.",
        },
        "sensitivity_config": {
            "repo_relative_path": _repo_relative(root, base / "sensitivity_config.csv"),
            "default_runtime_treatment": "all_off_no_change",
            "selections": list(SENSITIVITY_LEVELS),
            "scope": "Low-complexity post-model Revenue Outlook overlays: fleet efficiency, PT mode shift and optional demand elasticity.",
            "note": SENSITIVITY_DEFAULT_NOTE,
        },
        "sensitivity_impact_audit": {
            "repo_relative_path": _repo_relative(root, base / "sensitivity_impact_audit.csv"),
            "default_runtime_treatment": "all_off_no_change",
            "status": "available" if not sensitivity_impact_audit.empty else "missing",
            "scope": "Default-Off sensitivity audit; runtime UI recalculates selected impacts in memory.",
        },
        "scenario_role_contract": {
            "repo_relative_path": _repo_relative(root, base / "scenario_role_contract.csv"),
            "scope": "Repo-local audit of scenario role semantics, PED population-feature exposure, display policy and runtime deltas.",
            "note": SCENARIO_ROLE_CONTRACT_NOTE,
        },
        "scenario_inputs": scenario_input_manifest,
        "scenario_input_delta_audit": {
            "repo_relative_path": _repo_relative(root, base / "scenario_input_delta_audit.csv"),
            "status": "available" if not scenario_input_delta_audit.empty else "available_no_differences",
            "source": f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_LONG_STEM}.parquet",
            "scope": (
                "Workbook-cell base/comparison deltas derived from committed scenario_input_long artifacts, "
                "including source cells, workbook hashes, scenario roles and variable classifications."
            ),
        },
        "scenario_input_replay_mismatch_report": {
            "repo_relative_path": _repo_relative(root, base / "scenario_input_replay_mismatch_report.csv"),
            "status": "passed_no_mismatch",
            "scope": (
                "Verification that promoted current-finalist activity rows map back to committed scenario-input "
                "quarters and workbook hashes before annual Revenue Outlook rows are emitted."
            ),
            "fail_policy": "If any required scenario-input quarter is missing or hash-mismatched, rebuild writes this report and raises.",
        },
        "scenario_feature_lineage": {
            "repo_relative_path": _repo_relative(root, base / "scenario_feature_lineage.csv"),
            "source": f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_FEATURE_LINEAGE_STEM}.parquet",
            "scope": "Feature-level lineage from committed scenario input artifacts to fixed finalist forecast variables.",
        },
        "rate_provenance": {
            "future_light_heavy": "mbu26_official_annual.csv effective rates joined to current finalist net-km outputs",
            "future_ped": "Scenario-input population where supplied plus MBU26 intensity/rate joined to optimized PED/light-petrol VKT after EV/PHEV migration",
            "fixed_components": "mbu26_official_annual.csv official rows, excluding Light BEV and PHEV in current-finalist paths where they are allocated by the optimized PED+Light migration layer",
        },
        "trace_audit": {
            "repo_relative_path": _repo_relative(root, base / "runtime_trace_audit.csv"),
            "scope": "Per-series FY2024-FY2027 trace audit with source, role, model ID, scenario, quarter composition and anchor flags.",
        },
        "runtime_cutoff_audit": {
            "repo_relative_path": _repo_relative(root, base / "runtime_cutoff_audit.csv"),
            "runtime_cutoff_fy": runtime_cutoff_fy,
            "scope": "Dynamic Revenue Outlook runtime cutoff audit from current Base, current comparison and required MBU26 input horizons.",
            "status": "available",
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
            "ev_phev_ped_light_drift_assumptions": ev_phev_ped_light_drift_assumptions,
            "ped_revenue_bridge_audit": ped_revenue_bridge_audit,
            "ped_bridge_shape_fit_metrics": ped_bridge_shape_fit_metrics,
            "ped_bridge_mode_config": ped_bridge_mode_config,
            "ped_efficiency_scenarios": ped_efficiency_scenarios,
            "sensitivity_seed_inputs": sensitivity_seed_inputs,
            "sensitivity_config": sensitivity_config,
            "sensitivity_impact_audit": sensitivity_impact_audit,
            "scenario_input_delta_audit": scenario_input_delta_audit,
            "scenario_input_replay_mismatch_report": scenario_input_replay_mismatch_report,
            "scenario_feature_lineage": scenario_feature_lineage,
            "scenario_role_contract": scenario_role_contract,
            "revenue_formula_residuals": formula_residuals,
            "runtime_cutoff_audit": runtime_cutoff_audit,
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
    comparison_manifest = getattr(comparison, "manifest", {}) or {}
    scenario_input_manifest = _promote_scenario_inputs_from_comparison(comparison, base, root)
    scenario_input_long = _read_optional_parquet(
        base / SCENARIO_INPUT_DIRNAME / f"{SCENARIO_INPUT_LONG_STEM}.parquet"
    )
    scenario_input_delta_audit = _scenario_input_delta_audit_from_long(
        scenario_input_long,
        comparison_manifest.get("scenarios", []) if isinstance(comparison_manifest, dict) else [],
    )
    scenario_feature_lineage = _read_optional_parquet(
        base / SCENARIO_INPUT_DIRNAME / f"{SCENARIO_FEATURE_LINEAGE_STEM}.parquet"
    )
    scenario_role_contract = scenario_role_contract_frame(
        current_forecast_annual=pd.DataFrame(),
        scenarios=comparison_manifest.get("scenarios", []) if isinstance(comparison_manifest, dict) else [],
        repo_root=root,
    )

    manifest = _manifest(
        comparison,
        root,
        base,
        future_revenue,
        chart_rows,
        bridge_components,
        pack_status=pack_status,
        promoted_by=promoted_by,
        scenario_input_manifest=scenario_input_manifest,
    )
    _write_pack_files(
        base,
        manifest,
        future_revenue,
        bridge_components,
        chart_rows,
        extra_frames={
            "scenario_input_delta_audit": scenario_input_delta_audit,
            "scenario_role_contract": scenario_role_contract,
            "scenario_feature_lineage": scenario_feature_lineage,
        },
    )
    return RevenueOutlookPack(
        base,
        manifest,
        future_revenue,
        bridge_components,
        chart_rows,
        scenario_input_delta_audit=scenario_input_delta_audit,
        scenario_feature_lineage=scenario_feature_lineage,
        scenario_role_contract=scenario_role_contract,
    )


def _promote_scenario_inputs_from_comparison(
    comparison: ForecastScenarioComparisonResult,
    output_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    target = output_dir / SCENARIO_INPUT_DIRNAME
    source = Path(getattr(comparison, "output_dir", "")) / SCENARIO_INPUT_DIRNAME
    if source.exists():
        if target.exists():
            shutil.rmtree(target)
        combine_scenario_input_dirs([source], target, created_by="revenue_outlook_promotion", repo_root=repo_root)
    else:
        source_dirs = [
            Path(result.output_dir) / SCENARIO_INPUT_DIRNAME
            for result in getattr(comparison, "scenario_results", [])
            if (Path(result.output_dir) / SCENARIO_INPUT_DIRNAME).exists()
        ]
        if source_dirs:
            if target.exists():
                shutil.rmtree(target)
            combine_scenario_input_dirs(source_dirs, target, created_by="revenue_outlook_promotion", repo_root=repo_root)
    manifest_path = target / SCENARIO_INPUT_MANIFEST
    if not manifest_path.exists():
        return {
            "status": "missing",
            "repo_relative_output_dir": _repo_relative(repo_root, target),
            "reason": "Scenario input artifacts were unavailable in the reviewed comparison pack.",
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "status": "available",
        "repo_relative_output_dir": _repo_relative(repo_root, target),
        "schema_version": manifest.get("schema_version"),
        "row_counts": manifest.get("row_counts", {}),
        "workbooks": manifest.get("workbooks", []),
        "manifest_sha256": _sha256(manifest_path),
    }


def _read_optional_parquet(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            csv_path = path.with_suffix(".csv")
            if csv_path.exists():
                return pd.read_csv(csv_path)
            raise RuntimeError(
                f"Revenue Outlook runtime table {path.name} could not be read as Parquet and CSV fallback "
                f"{csv_path.name} is missing."
            ) from exc
    csv_path = path.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return pd.DataFrame()


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


def _current_scenario_input_manifest(pack_dir: Path, repo_root: Path) -> dict[str, Any]:
    scenario_dir = pack_dir / SCENARIO_INPUT_DIRNAME
    manifest_path = scenario_dir / SCENARIO_INPUT_MANIFEST
    if not manifest_path.exists():
        return {
            "status": "missing",
            "repo_relative_output_dir": _repo_relative(repo_root, scenario_dir),
            "reason": "Scenario input artifacts have not yet been materialized into the committed runtime pack.",
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "status": "available",
        "repo_relative_output_dir": _repo_relative(repo_root, scenario_dir),
        "schema_version": manifest.get("schema_version"),
        "row_counts": manifest.get("row_counts", {}),
        "workbooks": manifest.get("workbooks", []),
        "manifest_sha256": _sha256(manifest_path),
    }


SCENARIO_INPUT_DELTA_AUDIT_COLUMNS = [
    "base_scenario",
    "base_scenario_role",
    "base_workbook_filename",
    "base_workbook_sha256",
    "base_sheet",
    "base_cell",
    "base_range",
    "base_period",
    "base_canonical_period",
    "base_variable_name",
    "base_canonical_variable",
    "base_value",
    "base_unit",
    "base_value_type",
    "base_source_artifact",
    "base_source_status",
    "comparison_scenario",
    "comparison_scenario_role",
    "comparison_workbook_filename",
    "comparison_workbook_sha256",
    "comparison_is_test_fixture",
    "comparison_sheet",
    "comparison_cell",
    "comparison_range",
    "comparison_period",
    "comparison_canonical_period",
    "comparison_variable_name",
    "comparison_canonical_variable",
    "comparison_value",
    "comparison_unit",
    "comparison_value_type",
    "comparison_source_artifact",
    "comparison_source_status",
    "stream",
    "canonical_variable",
    "variable_name",
    "period",
    "canonical_period",
    "unit",
    "value_type",
    "absolute_delta",
    "pct_delta",
    "field_classification",
    "field_classification_detail",
    "affects_ped_vktpc_directly",
    "affects_bridge_scaling",
    "source_status",
    "notes",
]


def _scenario_input_delta_audit_from_long(
    scenario_input_long: pd.DataFrame,
    scenarios: list[dict[str, Any]],
) -> pd.DataFrame:
    """Compare committed base/comparison workbook cells without loading Excel."""

    if scenario_input_long is None or scenario_input_long.empty:
        return pd.DataFrame(columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)
    required = {
        "scenario_name",
        "role",
        "workbook_filename",
        "workbook_sha256",
        "sheet",
        "stream",
        "cell",
        "range",
        "period",
        "canonical_period",
        "variable_name",
        "canonical_variable",
        "value",
        "unit",
        "value_type",
        "source_status",
        "source_artifact",
    }
    if required.difference(scenario_input_long.columns):
        return pd.DataFrame(columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)

    source = scenario_input_long.copy()
    source["scenario_name"] = source["scenario_name"].fillna("").astype(str)
    source["role"] = source["role"].fillna("").astype(str)
    source["canonical_variable"] = source["canonical_variable"].fillna("").astype(str)
    source = source[source["canonical_variable"].str.len().gt(0)].copy()
    if source.empty:
        return pd.DataFrame(columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)

    scenario_records = [dict(item) for item in scenarios if isinstance(item, dict)]
    role_by_scenario = {
        str(record.get("scenario_name") or ""): str(record.get("scenario_role") or record.get("role") or "")
        for record in scenario_records
    }
    fixture_by_scenario = {
        str(record.get("scenario_name") or ""): bool(record.get("is_test_fixture"))
        for record in scenario_records
    }
    base_names = [
        str(record.get("scenario_name") or "")
        for record in scenario_records
        if str(record.get("scenario_role") or record.get("role") or "").lower() == SCENARIO_ROLE_BASECASE
    ]
    if not base_names:
        base_names = sorted(
            source.loc[source["role"].str.lower().eq(SCENARIO_ROLE_BASECASE), "scenario_name"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )
    if len(base_names) != 1:
        return pd.DataFrame(columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)
    base_scenario = base_names[0]

    comparison_names = [
        str(record.get("scenario_name") or "")
        for record in scenario_records
        if str(record.get("scenario_role") or record.get("role") or "").lower() == SCENARIO_ROLE_COMPARISON
    ]
    if not comparison_names:
        comparison_names = sorted(
            source.loc[source["role"].str.lower().eq(SCENARIO_ROLE_COMPARISON), "scenario_name"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

    key_columns = ["stream", "canonical_period", "canonical_variable"]
    ordered = source.sort_values(["scenario_name", *key_columns, "sheet", "cell"], kind="stable")
    base = ordered[ordered["scenario_name"].eq(base_scenario)].drop_duplicates(key_columns, keep="first").copy()
    if base.empty:
        return pd.DataFrame(columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)

    rows: list[dict[str, Any]] = []
    for comparison_scenario in comparison_names:
        comparison = (
            ordered[ordered["scenario_name"].eq(comparison_scenario)]
            .drop_duplicates(key_columns, keep="first")
            .copy()
        )
        if comparison.empty:
            continue
        merged = base.merge(comparison, on=key_columns, how="inner", suffixes=("_base", "_comparison"))
        for _, record in merged.iterrows():
            base_value = record.get("value_base")
            comparison_value = record.get("value_comparison")
            changed, absolute_delta, pct_delta = _scenario_input_value_delta(base_value, comparison_value)
            if not changed:
                continue
            variable = str(record.get("canonical_variable") or "")
            classification = _classify_scenario_variable(variable)
            stream = str(record.get("stream") or "")
            rows.append(
                {
                    "base_scenario": base_scenario,
                    "base_scenario_role": role_by_scenario.get(base_scenario)
                    or str(record.get("role_base") or SCENARIO_ROLE_BASECASE),
                    "base_workbook_filename": record.get("workbook_filename_base"),
                    "base_workbook_sha256": record.get("workbook_sha256_base"),
                    "base_sheet": record.get("sheet_base"),
                    "base_cell": record.get("cell_base"),
                    "base_range": record.get("range_base"),
                    "base_period": record.get("period_base"),
                    "base_canonical_period": record.get("canonical_period"),
                    "base_variable_name": record.get("variable_name_base"),
                    "base_canonical_variable": variable,
                    "base_value": base_value,
                    "base_unit": record.get("unit_base"),
                    "base_value_type": record.get("value_type_base"),
                    "base_source_artifact": record.get("source_artifact_base"),
                    "base_source_status": record.get("source_status_base"),
                    "comparison_scenario": comparison_scenario,
                    "comparison_scenario_role": role_by_scenario.get(comparison_scenario)
                    or str(record.get("role_comparison") or SCENARIO_ROLE_COMPARISON),
                    "comparison_workbook_filename": record.get("workbook_filename_comparison"),
                    "comparison_workbook_sha256": record.get("workbook_sha256_comparison"),
                    "comparison_is_test_fixture": fixture_by_scenario.get(comparison_scenario, False),
                    "comparison_sheet": record.get("sheet_comparison"),
                    "comparison_cell": record.get("cell_comparison"),
                    "comparison_range": record.get("range_comparison"),
                    "comparison_period": record.get("period_comparison"),
                    "comparison_canonical_period": record.get("canonical_period"),
                    "comparison_variable_name": record.get("variable_name_comparison"),
                    "comparison_canonical_variable": variable,
                    "comparison_value": comparison_value,
                    "comparison_unit": record.get("unit_comparison"),
                    "comparison_value_type": record.get("value_type_comparison"),
                    "comparison_source_artifact": record.get("source_artifact_comparison"),
                    "comparison_source_status": record.get("source_status_comparison"),
                    "stream": stream,
                    "canonical_variable": variable,
                    "variable_name": record.get("variable_name_comparison") or record.get("variable_name_base"),
                    "period": record.get("period_comparison") or record.get("period_base"),
                    "canonical_period": record.get("canonical_period"),
                    "unit": record.get("unit_comparison") or record.get("unit_base"),
                    "value_type": record.get("value_type_comparison") or record.get("value_type_base"),
                    "absolute_delta": absolute_delta,
                    "pct_delta": pct_delta,
                    "field_classification": classification,
                    "field_classification_detail": f"{variable}:{classification}",
                    "affects_ped_vktpc_directly": bool(stream == "PED" and classification != "system/time"),
                    "affects_bridge_scaling": bool(stream == "PED" and _ped_bridge_scaling_fields([variable])),
                    "source_status": "committed_scenario_input_delta",
                    "notes": (
                        "Base/comparison delta from committed scenario_input_long workbook-cell artifacts; "
                        "Streamlit does not load Excel at runtime."
                    ),
                }
            )
    if not rows:
        return pd.DataFrame(columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)
    out = pd.DataFrame(rows, columns=SCENARIO_INPUT_DELTA_AUDIT_COLUMNS)
    return out.sort_values(["comparison_scenario", "stream", "canonical_period", "canonical_variable"], kind="stable").reset_index(drop=True)


def _scenario_input_value_delta(base_value: Any, comparison_value: Any) -> tuple[bool, float | None, float | None]:
    base_numeric = pd.to_numeric(pd.Series([base_value]), errors="coerce").iloc[0]
    comparison_numeric = pd.to_numeric(pd.Series([comparison_value]), errors="coerce").iloc[0]
    base_is_numeric = pd.notna(base_numeric)
    comparison_is_numeric = pd.notna(comparison_numeric)
    if base_is_numeric or comparison_is_numeric:
        if base_is_numeric and comparison_is_numeric:
            absolute_delta = float(comparison_numeric) - float(base_numeric)
            changed = abs(absolute_delta) > 1e-9
            pct_delta = absolute_delta / float(base_numeric) if float(base_numeric) != 0.0 else None
            return changed, absolute_delta if changed else 0.0, pct_delta if changed else 0.0
        return True, None, None
    base_text = "" if pd.isna(base_value) else str(base_value)
    comparison_text = "" if pd.isna(comparison_value) else str(comparison_value)
    return base_text != comparison_text, None, None


SCENARIO_INPUT_REPLAY_REPORT_COLUMNS = [
    "scenario_name",
    "scenario_role",
    "series_id",
    "stream",
    "annual_period",
    "value_status",
    "forecast_quarter",
    "committed_forecast_value",
    "scenario_input_status",
    "mismatch_status",
    "mismatch_reason",
    "workbook_sha256",
    "manifest_workbook_sha256",
    "required_feature_count",
    "missing_required_feature_count",
    "replay_forecast_value",
    "promoted_forecast_value",
    "replay_abs_delta",
    "replay_tolerance",
    "replay_status",
    "replay_reason",
    "source_artifact",
]
SCENARIO_INPUT_REPLAY_ABS_TOLERANCE = 1e-6
SCENARIO_INPUT_REPLAY_REL_TOLERANCE = 1e-12


def _scenario_input_replay_mismatch_report(
    current_forecast_annual: pd.DataFrame,
    scenario_input_wide: pd.DataFrame,
    scenario_input_manifest: dict[str, Any],
    *,
    promoted_chart_rows: pd.DataFrame | None = None,
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Verify promoted current-finalist rows are backed by committed scenario inputs.

    This is a source-variable replay guard, not a model refit. It proves that
    the annualized current-finalist activity rows used by Revenue Outlook can
    be traced to committed scenario-input quarters and workbook hashes.
    """

    if current_forecast_annual is None or current_forecast_annual.empty:
        return pd.DataFrame(columns=SCENARIO_INPUT_REPLAY_REPORT_COLUMNS)
    series_to_stream = {
        "ped_vkt_per_capita": "PED",
        CURRENT_LIGHT_TOTAL_SERIES_ID: "LIGHT_RUC",
        "heavy_ruc_net_km": "HEAVY_RUC",
    }
    required = {
        "scenario_name",
        "role",
        "workbook_sha256",
        "stream",
        "canonical_period",
        "source_artifact",
    }
    input_lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    feature_columns: list[str] = []
    if scenario_input_wide is not None and not scenario_input_wide.empty and not required.difference(scenario_input_wide.columns):
        metadata_columns = {
            "scenario_name",
            "role",
            "workbook_filename",
            "workbook_sha256",
            "stream",
            "sheet",
            "period",
            "canonical_period",
            "source_artifact",
            "year",
            "quarter",
            "horizon",
        }
        feature_columns = [column for column in scenario_input_wide.columns if column not in metadata_columns]
        for row in scenario_input_wide.itertuples(index=False):
            key = (
                str(getattr(row, "scenario_name", "") or ""),
                str(getattr(row, "stream", "") or ""),
                str(getattr(row, "canonical_period", "") or ""),
            )
            if not all(key):
                continue
            row_values = row._asdict()
            feature_count = sum(
                1
                for column in feature_columns
                if column in row_values and pd.notna(row_values[column]) and str(row_values[column]).strip() != ""
            )
            input_lookup[key] = {
                "workbook_sha256": str(row_values.get("workbook_sha256") or ""),
                "source_artifact": str(row_values.get("source_artifact") or ""),
                "required_feature_count": int(feature_count),
            }
    manifest_hash_by_scenario = {
        str(item.get("scenario_name") or ""): str(item.get("workbook_sha256") or "")
        for item in scenario_input_manifest.get("workbooks", [])
        if isinstance(item, dict)
    }
    replay_lookup, replay_validation = _scenario_input_forecast_replay_lookup(scenario_input_wide, repo_root=repo_root)
    promoted_lookup = _promoted_quarterly_forecast_lookup(promoted_chart_rows)
    rows: list[dict[str, Any]] = []
    source = current_forecast_annual.copy()
    source = source[source.get("series_id", pd.Series("", index=source.index)).astype(str).isin(series_to_stream)].copy()
    for row in source.itertuples(index=False):
        scenario_name = str(getattr(row, "scenario_name", "") or "")
        series_id = str(getattr(row, "series_id", "") or "")
        stream = series_to_stream.get(series_id, "")
        value_status = str(getattr(row, "value_status", "") or "")
        annual_period = str(getattr(row, "period", "") or f"FY{_coerce_int(getattr(row, 'FY', 0))}")
        committed_value = getattr(row, "value", pd.NA)
        forecast_quarters = _split_forecast_quarters(str(getattr(row, "forecast_quarters", "") or ""))
        base_record = {
            "scenario_name": scenario_name,
            "scenario_role": str(getattr(row, "scenario_role", "") or ""),
            "series_id": series_id,
            "stream": stream,
            "annual_period": annual_period,
            "value_status": value_status,
            "committed_forecast_value": committed_value,
            "manifest_workbook_sha256": manifest_hash_by_scenario.get(scenario_name, ""),
        }
        if value_status == "extrapolated_model_extension":
            rows.append(
                {
                    **base_record,
                    "forecast_quarter": "",
                    "scenario_input_status": "governed_model_extension_not_replayed_from_workbook",
                    "mismatch_status": "not_applicable",
                    "mismatch_reason": "FY2051-FY2055 extension uses governed annual gradient rather than workbook quarter rows.",
                    "workbook_sha256": "",
                    "required_feature_count": 0,
                    "missing_required_feature_count": 0,
                    "replay_forecast_value": pd.NA,
                    "promoted_forecast_value": pd.NA,
                    "replay_abs_delta": pd.NA,
                    "replay_tolerance": pd.NA,
                    "replay_status": "not_applicable",
                    "replay_reason": "Governed extension is not replayed from workbook quarter rows.",
                    "source_artifact": "current_finalist_model_extension",
                }
            )
            continue
        if not forecast_quarters:
            rows.append(
                {
                    **base_record,
                    "forecast_quarter": "",
                    "scenario_input_status": "actual_anchor_no_workbook_replay_required",
                    "mismatch_status": "not_applicable",
                    "mismatch_reason": "Annual row contains actual-anchor quarters only.",
                    "workbook_sha256": "",
                    "required_feature_count": 0,
                    "missing_required_feature_count": 0,
                    "replay_forecast_value": pd.NA,
                    "promoted_forecast_value": pd.NA,
                    "replay_abs_delta": pd.NA,
                    "replay_tolerance": pd.NA,
                    "replay_status": "not_applicable",
                    "replay_reason": "Actual-anchor row is not a promoted future forecast row.",
                    "source_artifact": "mbu26_actual_anchor",
                }
            )
            continue
        for quarter in forecast_quarters:
            input_row = input_lookup.get((scenario_name, stream, quarter))
            manifest_hash = manifest_hash_by_scenario.get(scenario_name, "")
            if input_row is None:
                rows.append(
                    {
                        **base_record,
                        "forecast_quarter": quarter,
                        "scenario_input_status": "missing_committed_scenario_input",
                        "mismatch_status": "mismatch",
                        "mismatch_reason": "Required promoted forecast quarter is absent from scenario_input_wide.",
                        "workbook_sha256": "",
                        "required_feature_count": len(feature_columns),
                        "missing_required_feature_count": 1,
                        "replay_forecast_value": pd.NA,
                        "promoted_forecast_value": pd.NA,
                        "replay_abs_delta": pd.NA,
                        "replay_tolerance": pd.NA,
                        "replay_status": "not_run_missing_input",
                        "replay_reason": "Replay was skipped because the committed scenario-input quarter row is missing.",
                        "source_artifact": f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_WIDE_STEM}.parquet",
                    }
                )
                continue
            workbook_hash = str(input_row.get("workbook_sha256") or "")
            hash_mismatch = bool(manifest_hash and workbook_hash and manifest_hash != workbook_hash)
            replay = replay_lookup.get((scenario_name, stream, quarter), {})
            promoted_value = promoted_lookup.get((scenario_name, stream, quarter))
            replay_value = replay.get("forecast")
            replay_delta = _abs_delta(replay_value, promoted_value)
            replay_tolerance = _replay_tolerance(replay_value, promoted_value)
            replay_available = bool(replay.get("forecast_available")) and pd.notna(replay_value)
            promoted_available = pd.notna(promoted_value)
            replay_status = "pass"
            replay_reason = ""
            if hash_mismatch:
                replay_status = "not_run_hash_mismatch"
                replay_reason = "Scenario input row workbook hash differs from the manifest workbook hash."
            elif not replay_validation.get(scenario_name, {}).get("valid", False):
                replay_status = "replay_validation_failed"
                replay_reason = str(replay_validation.get(scenario_name, {}).get("errors", ""))
            elif not replay_available:
                replay_status = "missing_replayed_forecast"
                replay_reason = "The fixed-finalist replay did not emit a numeric forecast for this scenario/stream/quarter."
            elif not promoted_available:
                replay_status = "missing_promoted_forecast"
                replay_reason = "The promoted runtime chart rows do not contain this scenario/stream/quarter forecast."
            elif _replay_delta_exceeds_tolerance(replay_delta, replay_tolerance):
                replay_status = "replay_delta_exceeds_tolerance"
                replay_reason = "Replayed committed scenario-input forecast differs from promoted forecast_scenario_comparison row."
            replay_mismatch = replay_status not in {"pass"}
            rows.append(
                {
                    **base_record,
                    "forecast_quarter": quarter,
                    "scenario_input_status": "matched_committed_scenario_input"
                    if not hash_mismatch
                    else "workbook_hash_mismatch",
                    "mismatch_status": "mismatch" if (hash_mismatch or replay_mismatch) else "pass",
                    "mismatch_reason": ""
                    if not (hash_mismatch or replay_mismatch)
                    else (replay_reason or "Scenario input row workbook hash differs from the scenario input manifest workbook hash."),
                    "workbook_sha256": workbook_hash,
                    "required_feature_count": int(input_row.get("required_feature_count") or 0),
                    "missing_required_feature_count": 0 if not (hash_mismatch or replay_mismatch) else 1,
                    "replay_forecast_value": replay_value if pd.notna(replay_value) else pd.NA,
                    "promoted_forecast_value": promoted_value if pd.notna(promoted_value) else pd.NA,
                    "replay_abs_delta": replay_delta if pd.notna(replay_delta) else pd.NA,
                    "replay_tolerance": replay_tolerance if pd.notna(replay_tolerance) else pd.NA,
                    "replay_status": replay_status,
                    "replay_reason": replay_reason,
                    "source_artifact": input_row.get("source_artifact") or f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_WIDE_STEM}.parquet",
                }
            )
    if not rows:
        return pd.DataFrame(columns=SCENARIO_INPUT_REPLAY_REPORT_COLUMNS)
    return pd.DataFrame(rows, columns=SCENARIO_INPUT_REPLAY_REPORT_COLUMNS).sort_values(
        ["scenario_name", "stream", "annual_period", "forecast_quarter"],
        kind="stable",
    )


def _scenario_input_forecast_replay_lookup(
    scenario_input_wide: pd.DataFrame,
    *,
    repo_root: Path | str | None,
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    if scenario_input_wide is None or scenario_input_wide.empty:
        return {}, {}
    from .forecast_runner import replay_forecast_from_scenario_inputs

    replay = replay_forecast_from_scenario_inputs(scenario_input_wide, repo_root=repo_root)
    validation = {
        str(row.scenario_name): {
            "valid": bool(row.valid),
            "errors": str(row.errors or ""),
        }
        for row in replay.validation_report.itertuples(index=False)
    }
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    if replay.future_forecasts.empty:
        return lookup, validation
    for row in replay.future_forecasts.itertuples(index=False):
        key = (
            str(getattr(row, "scenario_name", "") or ""),
            str(getattr(row, "stream", "") or ""),
            str(getattr(row, "target_period", "") or ""),
        )
        if not all(key):
            continue
        lookup[key] = {
            "forecast": pd.to_numeric(pd.Series([getattr(row, "forecast", pd.NA)]), errors="coerce").iloc[0],
            "forecast_available": bool(getattr(row, "forecast_available", False)),
        }
    return lookup, validation


def _promoted_quarterly_forecast_lookup(chart_rows: pd.DataFrame | None) -> dict[tuple[str, str, str], Any]:
    if chart_rows is None or chart_rows.empty:
        return {}
    required = {"scenario_name", "stream", "period", "value", "time_grain", "metric_type", "row_type"}
    if required.difference(chart_rows.columns):
        return {}
    source = chart_rows[
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["metric_type"].astype(str).eq("activity")
        & chart_rows["row_type"].astype(str).eq("future_forecast")
    ].copy()
    lookup: dict[tuple[str, str, str], Any] = {}
    for row in source.itertuples(index=False):
        key = (
            str(getattr(row, "scenario_name", "") or ""),
            str(getattr(row, "stream", "") or ""),
            str(getattr(row, "period", "") or ""),
        )
        if all(key):
            lookup[key] = pd.to_numeric(pd.Series([getattr(row, "value", pd.NA)]), errors="coerce").iloc[0]
    return lookup


def _abs_delta(left: Any, right: Any) -> Any:
    values = pd.to_numeric(pd.Series([left, right]), errors="coerce")
    if values.isna().any():
        return pd.NA
    return abs(float(values.iloc[0]) - float(values.iloc[1]))


def _replay_tolerance(left: Any, right: Any) -> Any:
    values = pd.to_numeric(pd.Series([left, right]), errors="coerce")
    if values.isna().any():
        return pd.NA
    scale = max(abs(float(values.iloc[0])), abs(float(values.iloc[1])), 1.0)
    return max(SCENARIO_INPUT_REPLAY_ABS_TOLERANCE, SCENARIO_INPUT_REPLAY_REL_TOLERANCE * scale)


def _replay_delta_exceeds_tolerance(delta: Any, tolerance: Any) -> bool:
    values = pd.to_numeric(pd.Series([delta, tolerance]), errors="coerce")
    if values.isna().any():
        return False
    return float(values.iloc[0]) > float(values.iloc[1])


def _split_forecast_quarters(value: str) -> list[str]:
    quarters: list[str] = []
    for part in str(value or "").replace(",", ";").split(";"):
        token = part.strip().upper()
        if len(token) == 6 and token[:4].isdigit() and token[4] == "Q" and token[5] in {"1", "2", "3", "4"}:
            quarters.append(token)
    return quarters


SCENARIO_ROLE_CONTRACT_COLUMNS = [
    "scenario_name",
    "scenario_role",
    "differing_fields",
    "population_only_flag",
    "behavioural_driver_flag",
    "affected_series",
    "interpretation",
    "display_policy",
    "field_classification",
    "affects_ped_vktpc_directly",
    "affects_bridge_scaling",
    "stream_differing_fields",
    "ped_vktpc_direct_fields",
    "bridge_scaling_fields",
    "bridge_only_fields",
    "unknown_fields",
    "runtime_delta_min",
    "runtime_delta_max",
    "ped_population_feature_present",
    "ped_population_feature_fields",
    "vktpc_path_policy",
    "population_path_policy",
    "source_basis",
    "notes",
]


def scenario_role_contract_frame(
    *,
    current_forecast_annual: pd.DataFrame,
    scenarios: list[dict[str, Any]],
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Create a repo-local scenario role contract for Revenue Outlook display policy.

    The promoted runtime manifest keeps workbook basenames and hashes, not the
    source workbook paths. This contract therefore uses committed runtime rows
    and repo-local feature evidence. It does not load Excel at dashboard runtime.
    """

    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    ped_feature_fields = _ped_population_feature_fields(root)
    ped_population_feature_present = bool(ped_feature_fields)
    scenario_records = [dict(item) for item in scenarios if isinstance(item, dict)]
    if not scenario_records and isinstance(current_forecast_annual, pd.DataFrame) and not current_forecast_annual.empty:
        scenario_records = _runtime_scenario_records({}, current_forecast_annual)

    base_names = [
        str(item.get("scenario_name") or "")
        for item in scenario_records
        if str(item.get("scenario_role") or "").lower() == SCENARIO_ROLE_BASECASE
    ]
    base_name = base_names[0] if base_names else "current_basecase"
    scenario_input_wide = _read_optional_parquet(
        root / CURRENT_REVENUE_OUTLOOK_DIR / SCENARIO_INPUT_DIRNAME / f"{SCENARIO_INPUT_WIDE_STEM}.parquet"
    )
    differing_inputs = _scenario_input_differing_fields(scenario_input_wide, base_name)
    differing_inputs_by_stream = _scenario_input_differing_fields_by_stream(scenario_input_wide, base_name)
    rows: list[dict[str, Any]] = []
    affected_series = [
        "ped_vkt_per_capita",
        "ped_volume",
        "gross_ped_revenue",
        "light_ruc_net_km",
        "heavy_ruc_net_km",
        "total_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
    ]
    for scenario in scenario_records:
        scenario_name = str(scenario.get("scenario_name") or "")
        scenario_role = str(scenario.get("scenario_role") or "")
        role = scenario_role.lower()
        for series_id in affected_series:
            delta_min, delta_max = _runtime_series_delta_bounds(
                current_forecast_annual,
                base_scenario=base_name,
                comparison_scenario=scenario_name,
                series_id=series_id,
            )
            value_changes = bool(pd.notna(delta_min) and pd.notna(delta_max) and (abs(float(delta_min)) > 1e-9 or abs(float(delta_max)) > 1e-9))
            if role == SCENARIO_ROLE_BASECASE:
                rows.append(
                    _scenario_contract_row(
                        scenario_name=scenario_name,
                        scenario_role=scenario_role,
                        affected_series=series_id,
                        differing_fields="none",
                        population_only_flag=False,
                        behavioural_driver_flag=False,
                        display_policy="basecase_reference",
                        interpretation="Basecase runtime path is the behavioural reference for current finalist Revenue Outlook traces.",
                        field_classification="basecase_reference",
                        affects_ped_vktpc_directly=False,
                        affects_bridge_scaling=False,
                        stream_differing_fields="none",
                        ped_vktpc_direct_fields="",
                        bridge_scaling_fields="",
                        bridge_only_fields="",
                        unknown_fields="",
                        delta_min=delta_min,
                        delta_max=delta_max,
                        ped_population_feature_present=ped_population_feature_present,
                        ped_feature_fields=ped_feature_fields,
                        vktpc_path_policy="basecase_reference_path",
                        population_path_policy="basecase_bridge_population",
                        source_basis="repo-local current Revenue Outlook runtime and PED feature rows",
                        notes=SCENARIO_ROLE_CONTRACT_NOTE,
                    )
                )
                continue

            if series_id == "ped_vkt_per_capita":
                display_policy = "keep_trace_relabel_comparison_behavioural_path" if value_changes else "hide_comparison_intensity_trace"
                scenario_differing_fields = differing_inputs.get(scenario_name, [])
                stream_fields = _stream_differing_fields_for_series(
                    series_id,
                    scenario_name=scenario_name,
                    differing_inputs_by_stream=differing_inputs_by_stream,
                )
                ped_direct_fields = _ped_vktpc_direct_fields(
                    scenario_name,
                    differing_inputs_by_stream=differing_inputs_by_stream,
                )
                bridge_scaling_fields = _ped_bridge_scaling_fields(ped_direct_fields)
                bridge_only_fields = [field for field in bridge_scaling_fields if field not in set(ped_direct_fields)]
                population_only = bool(scenario_differing_fields) and all(
                    _classify_scenario_variable(field) == "population/scale" for field in scenario_differing_fields
                )
                behavioural_driver = value_changes or ped_population_feature_present or any(
                    _classify_scenario_variable(field) == "behavioural" for field in scenario_differing_fields
                )
                rows.append(
                    _scenario_contract_row(
                        scenario_name=scenario_name,
                        scenario_role=scenario_role,
                        affected_series=series_id,
                        differing_fields="; ".join(scenario_differing_fields)
                        or _comparison_differing_fields(
                            scenario,
                            [
                                "runtime_PED_VKT_per_capita_forecast_delta",
                                "PED_feature_population__level_present" if ped_population_feature_present else "PED_population_feature_absent",
                            ],
                        ),
                        population_only_flag=population_only and not value_changes and not ped_population_feature_present,
                        behavioural_driver_flag=behavioural_driver,
                        display_policy=display_policy,
                        interpretation=(
                            "Comparison PED VKT per capita is treated as a behavioural comparison path, not a pure high-population scale path, "
                            "because the committed runtime path changes per-capita values, the workbook changes behavioural inputs, or PED feature evidence includes population exposure."
                            if behavioural_driver
                            else "Comparison does not change the per-capita behavioural path; hide the separate intensity trace and use base VKT per capita."
                        ),
                        field_classification=_scenario_field_classification(scenario_differing_fields),
                        affects_ped_vktpc_directly=bool(ped_direct_fields),
                        affects_bridge_scaling=bool(bridge_scaling_fields),
                        stream_differing_fields="; ".join(stream_fields),
                        ped_vktpc_direct_fields="; ".join(ped_direct_fields),
                        bridge_scaling_fields="; ".join(bridge_scaling_fields),
                        bridge_only_fields="; ".join(bridge_only_fields),
                        unknown_fields="; ".join(_unknown_scenario_fields(scenario_differing_fields)),
                        delta_min=delta_min,
                        delta_max=delta_max,
                        ped_population_feature_present=ped_population_feature_present,
                        ped_feature_fields=ped_feature_fields,
                        vktpc_path_policy="comparison_behavioural_path" if value_changes else "base_behavioural_path",
                        population_path_policy="scenario_input_population_from_committed_workbook_artifacts",
                        source_basis="repo-local runtime chart rows, scenario_input_wide and PED prediction feature rows",
                        notes=SCENARIO_ROLE_CONTRACT_NOTE,
                    )
                )
                continue

            is_ped_bridge = series_id in {
                "ped_volume",
                "gross_ped_revenue",
                "total_fed_ruc_net_revenue",
                "total_nltf_net_revenue",
            }
            scenario_differing_fields = differing_inputs.get(scenario_name, [])
            stream_fields = _stream_differing_fields_for_series(
                series_id,
                scenario_name=scenario_name,
                differing_inputs_by_stream=differing_inputs_by_stream,
            )
            ped_direct_fields = (
                _ped_vktpc_direct_fields(scenario_name, differing_inputs_by_stream=differing_inputs_by_stream)
                if is_ped_bridge
                else []
            )
            bridge_scaling_fields = _ped_bridge_scaling_fields(ped_direct_fields) if is_ped_bridge else []
            bridge_only_fields = [field for field in bridge_scaling_fields if field not in set(ped_direct_fields)]
            rows.append(
                _scenario_contract_row(
                    scenario_name=scenario_name,
                    scenario_role=scenario_role,
                    affected_series=series_id,
                    differing_fields="; ".join(scenario_differing_fields)
                    or _comparison_differing_fields(
                        scenario,
                        [f"runtime_{series_id}_delta" if value_changes else f"runtime_{series_id}_no_material_delta"],
                    ),
                    population_only_flag=False,
                    behavioural_driver_flag=bool(is_ped_bridge and (value_changes or ped_population_feature_present)),
                    display_policy="keep_comparison_trace_scale_or_bridge",
                    interpretation=(
                        "Keep the comparison trace for revenue and aggregate series because bridge composition, population-scale assumptions, "
                        "or modelled activity can change totals even when per-capita intensity is a behavioural metric."
                    ),
                    field_classification=_scenario_field_classification(scenario_differing_fields)
                    or ("aggregate_or_revenue_bridge_delta" if value_changes else "no_material_runtime_delta"),
                    affects_ped_vktpc_directly=bool(ped_direct_fields),
                    affects_bridge_scaling=bool(bridge_scaling_fields),
                    stream_differing_fields="; ".join(stream_fields),
                    ped_vktpc_direct_fields="; ".join(ped_direct_fields),
                    bridge_scaling_fields="; ".join(bridge_scaling_fields),
                    bridge_only_fields="; ".join(bridge_only_fields),
                    unknown_fields="; ".join(_unknown_scenario_fields(scenario_differing_fields)),
                    delta_min=delta_min,
                    delta_max=delta_max,
                    ped_population_feature_present=ped_population_feature_present,
                    ped_feature_fields=ped_feature_fields,
                    vktpc_path_policy="inherits_PED_contract" if is_ped_bridge else "not_applicable",
                    population_path_policy="scenario_input_population_from_committed_workbook_artifacts" if is_ped_bridge else "not_applicable_or_model_output",
                    source_basis="repo-local current Revenue Outlook runtime and scenario_input_wide",
                    notes=SCENARIO_ROLE_CONTRACT_NOTE,
                )
            )

    return pd.DataFrame(rows, columns=SCENARIO_ROLE_CONTRACT_COLUMNS)


def _scenario_input_differing_fields_by_stream(
    scenario_input_wide: pd.DataFrame,
    base_scenario: str,
) -> dict[str, dict[str, list[str]]]:
    if scenario_input_wide is None or scenario_input_wide.empty or "scenario_name" not in scenario_input_wide.columns:
        return {}
    source = scenario_input_wide.copy()
    if "stream" not in source.columns:
        return {}
    output: dict[str, dict[str, list[str]]] = {}
    for stream, group in source.groupby("stream", dropna=False):
        stream_name = str(stream or "")
        stream_differences = _scenario_input_differing_fields(group, base_scenario)
        for scenario_name, fields in stream_differences.items():
            output.setdefault(scenario_name, {})[stream_name] = fields
    return output


def _scenario_input_differing_fields(scenario_input_wide: pd.DataFrame, base_scenario: str) -> dict[str, list[str]]:
    if scenario_input_wide is None or scenario_input_wide.empty or "scenario_name" not in scenario_input_wide.columns:
        return {}
    source = scenario_input_wide.copy()
    keys = [column for column in ["stream", "canonical_period"] if column in source.columns]
    if not keys:
        return {}
    metadata = {
        "scenario_name",
        "role",
        "workbook_filename",
        "workbook_sha256",
        "stream",
        "sheet",
        "period",
        "canonical_period",
        "source_artifact",
    }
    variable_columns = [column for column in source.columns if column not in metadata]
    base = source[source["scenario_name"].astype(str).eq(str(base_scenario))].copy()
    if base.empty:
        return {}
    output: dict[str, list[str]] = {}
    base_subset = base[keys + variable_columns].copy()
    for scenario_name, group in source[~source["scenario_name"].astype(str).eq(str(base_scenario))].groupby("scenario_name", dropna=False):
        compare = group[keys + variable_columns].copy()
        merged = base_subset.merge(compare, on=keys, how="inner", suffixes=("_base", "_comparison"))
        differing: set[str] = set()
        for column in variable_columns:
            base_values = merged.get(f"{column}_base")
            comparison_values = merged.get(f"{column}_comparison")
            if base_values is None or comparison_values is None:
                continue
            base_numeric = pd.to_numeric(base_values, errors="coerce")
            comparison_numeric = pd.to_numeric(comparison_values, errors="coerce")
            numeric_mask = base_numeric.notna() | comparison_numeric.notna()
            numeric_changed = (base_numeric - comparison_numeric).abs().gt(1e-9) & numeric_mask
            text_changed = base_values.fillna("").astype(str).ne(comparison_values.fillna("").astype(str)) & ~numeric_mask
            if bool((numeric_changed | text_changed).any()):
                differing.add(str(column))
        output[str(scenario_name)] = sorted(differing)
    return output


def _stream_differing_fields_for_series(
    series_id: str,
    *,
    scenario_name: str,
    differing_inputs_by_stream: dict[str, dict[str, list[str]]],
) -> list[str]:
    by_stream = differing_inputs_by_stream.get(scenario_name, {})
    if not by_stream:
        return []
    if str(series_id).startswith("ped_") or str(series_id) == "gross_ped_revenue":
        return list(by_stream.get("PED", []))
    if str(series_id).startswith("light_ruc"):
        return list(by_stream.get("LIGHT_RUC", []))
    if str(series_id).startswith("heavy_ruc"):
        return list(by_stream.get("HEAVY_RUC", []))
    merged: set[str] = set()
    for fields in by_stream.values():
        merged.update(fields)
    return sorted(merged)


def _ped_vktpc_direct_fields(
    scenario_name: str,
    *,
    differing_inputs_by_stream: dict[str, dict[str, list[str]]],
) -> list[str]:
    return list(differing_inputs_by_stream.get(scenario_name, {}).get("PED", []))


def _ped_bridge_scaling_fields(ped_fields: list[str]) -> list[str]:
    return [
        field
        for field in ped_fields
        if str(field).lower() in {"population", "population_count", "population__level"}
    ]


def _unknown_scenario_fields(fields: list[str]) -> list[str]:
    return [field for field in fields if _classify_scenario_variable(field) == "unknown"]


def _scenario_field_classification(fields: list[str]) -> str:
    if not fields:
        return ""
    parts = [f"{field}:{_classify_scenario_variable(field)}" for field in fields]
    return "; ".join(parts)


def _classify_scenario_variable(field: str) -> str:
    text = str(field or "").lower()
    if "population" in text:
        return "population/scale"
    if "unemployment" in text:
        return "macro"
    if any(token in text for token in ["price", "rate", "cpi", "ruc", "diesel", "petrol"]):
        return "price/rate/policy"
    if "gdp" in text:
        return "macro"
    if any(token in text for token in ["target_lag"]):
        return "behavioural"
    if any(token in text for token in ["quarter", "year", "horizon", "dummy", "trend"]):
        return "system/time"
    return "unknown"


def _scenario_contract_row(
    *,
    scenario_name: str,
    scenario_role: str,
    affected_series: str,
    differing_fields: str,
    population_only_flag: bool,
    behavioural_driver_flag: bool,
    display_policy: str,
    interpretation: str,
    field_classification: str,
    affects_ped_vktpc_directly: bool,
    affects_bridge_scaling: bool,
    stream_differing_fields: str,
    ped_vktpc_direct_fields: str,
    bridge_scaling_fields: str,
    bridge_only_fields: str,
    unknown_fields: str,
    delta_min: float | None,
    delta_max: float | None,
    ped_population_feature_present: bool,
    ped_feature_fields: list[str],
    vktpc_path_policy: str,
    population_path_policy: str,
    source_basis: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "scenario_name": scenario_name,
        "scenario_role": scenario_role,
        "differing_fields": differing_fields,
        "population_only_flag": bool(population_only_flag),
        "behavioural_driver_flag": bool(behavioural_driver_flag),
        "affected_series": affected_series,
        "interpretation": interpretation,
        "display_policy": display_policy,
        "field_classification": field_classification,
        "affects_ped_vktpc_directly": bool(affects_ped_vktpc_directly),
        "affects_bridge_scaling": bool(affects_bridge_scaling),
        "stream_differing_fields": stream_differing_fields,
        "ped_vktpc_direct_fields": ped_vktpc_direct_fields,
        "bridge_scaling_fields": bridge_scaling_fields,
        "bridge_only_fields": bridge_only_fields,
        "unknown_fields": unknown_fields,
        "runtime_delta_min": delta_min if delta_min is not None else pd.NA,
        "runtime_delta_max": delta_max if delta_max is not None else pd.NA,
        "ped_population_feature_present": bool(ped_population_feature_present),
        "ped_population_feature_fields": "; ".join(ped_feature_fields),
        "vktpc_path_policy": vktpc_path_policy,
        "population_path_policy": population_path_policy,
        "source_basis": source_basis,
        "notes": notes,
    }


def _comparison_differing_fields(scenario: dict[str, Any], fields: list[str]) -> str:
    workbook = str(scenario.get("workbook_filename") or "").strip()
    workbook_hash = str(scenario.get("workbook_sha256") or "").strip()
    values = []
    if workbook:
        values.append(f"workbook_filename={workbook}")
    if workbook_hash:
        values.append(f"workbook_sha256={workbook_hash}")
    values.extend(fields)
    return "; ".join(value for value in values if value)


def _runtime_series_delta_bounds(
    current_forecast_annual: pd.DataFrame,
    *,
    base_scenario: str,
    comparison_scenario: str,
    series_id: str,
) -> tuple[float | None, float | None]:
    if current_forecast_annual is None or current_forecast_annual.empty or base_scenario == comparison_scenario:
        return (None, None)
    required = {"scenario_name", "series_id", "FY", "value"}
    if required.difference(current_forecast_annual.columns):
        return (None, None)
    data = current_forecast_annual[
        current_forecast_annual["series_id"].astype(str).eq(str(series_id))
        & current_forecast_annual["scenario_name"].astype(str).isin([base_scenario, comparison_scenario])
    ].copy()
    if data.empty:
        return (None, None)
    data["FY_numeric"] = pd.to_numeric(data["FY"], errors="coerce")
    data["value_numeric"] = pd.to_numeric(data["value"], errors="coerce")
    pivot = data.pivot_table(index="FY_numeric", columns="scenario_name", values="value_numeric", aggfunc="first")
    if base_scenario not in pivot.columns or comparison_scenario not in pivot.columns:
        return (None, None)
    delta = (pivot[comparison_scenario] - pivot[base_scenario]).dropna()
    if delta.empty:
        return (None, None)
    return (float(delta.min()), float(delta.max()))


def _ped_population_feature_fields(repo_root: Path) -> list[str]:
    candidates = [
        repo_root / "data" / "dashboard_evidence_pack_reproducibility" / "ped_vnext" / "prediction_feature_rows.parquet",
        repo_root / "data" / "dashboard_evidence_pack_reproducibility" / "ped_inner_hpo" / "prediction_feature_rows.parquet",
        repo_root / "data" / "model_input_history" / "ped_inputs.parquet",
    ]
    fields: set[str] = set()
    for path in candidates:
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        for column in frame.columns:
            text = str(column).lower()
            if "population" in text or text in {"pop", "log_population"}:
                fields.add(str(column))
    return sorted(fields)


def ev_phev_split_assumptions_frame(
    mbu26_official_annual: pd.DataFrame,
    *,
    current_forecast_annual: pd.DataFrame | None = None,
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Audit legacy current-Light split evidence and fixed-add-on comparators."""

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
                    "allocation_status": "legacy_light_only_comparator_superseded_by_ped_light_migration",
                    "used_by_current_finalist": True,
                    "notes": (
                        "Legacy Light-only split comparator retained for governance. Active current-finalist "
                        "rows use the PED-Light optimized migration audit."
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
            "decision": "Apply the governed PED-Light optimized migration layer when current rows are available.",
            "rationale": "No ev_phev_split_assumptions audit rows were available.",
        }
    current_rows = audit[audit.get("used_by_current_finalist", pd.Series(False, index=audit.index)).astype(bool)].copy()
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
    allocation_years = [int(value) for value in pd.to_numeric(current_rows.get("FY", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).unique().tolist()]
    return {
        "status": "business_rule_applied_ped_light_optimized_migration",
        "decision": (
            "Allocate EV/PHEV uptake between PED/light-petrol activity and current-finalist total Light RUC "
            "using the optimized migration layer; retain the legacy Light-only split as an audit comparator."
        ),
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
            "The current governed business rule sources EV/PHEV migration from both PED/light-petrol activity "
            "and total Light RUC. The legacy split audit preserves prior model-input target evidence and old "
            "Light-only comparators for review."
        ),
    }


def _ev_phev_allocation_status(audit: pd.DataFrame) -> str:
    if audit is None or audit.empty or "allocation_status" not in audit.columns:
        return "business_rule_pending_audit_rows"
    statuses = set(audit["allocation_status"].dropna().astype(str))
    if "legacy_light_only_comparator_superseded_by_ped_light_migration" in statuses:
        return "legacy_light_only_comparator_superseded_by_ped_light_migration"
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
        "ped_volume": "PED volume",
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
                "metric_type": "activity" if series_id.endswith("_km") or series_id in {"ped_vkt_per_capita", "ped_volume"} else "revenue",
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


def _runtime_quarterly_activity_inputs(
    chart_rows: pd.DataFrame,
    series_meta: dict[str, dict[str, Any]],
    *,
    scenario_role_contract: pd.DataFrame | None = None,
) -> pd.DataFrame:
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
    policy_lookup = _scenario_display_policy_lookup(scenario_role_contract)
    data["trace_name"] = data.apply(
        lambda row: "Actual"
        if str(row.get("row_type", "")) == "historical_actual"
        else _runtime_current_trace_name(
            row.get("scenario_name"),
            row.get("scenario_role"),
            series_id=row.get("series_id"),
            display_policy=policy_lookup.get((str(row.get("scenario_name") or ""), str(row.get("series_id") or ""))),
        ),
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
    hide_policy = data.apply(
        lambda row: policy_lookup.get((str(row.get("scenario_name") or ""), str(row.get("series_id") or ""))) == "hide_comparison_intensity_trace",
        axis=1,
    )
    data.loc[hide_policy, "plot_allowed"] = False
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


def _runtime_current_rows(
    current: pd.DataFrame,
    series_meta: dict[str, dict[str, Any]],
    *,
    scenario_role_contract: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = _runtime_chart_columns()
    if current is None or current.empty:
        return pd.DataFrame(columns=columns)
    data = current[current.get("series_id", pd.Series(dtype=str)).astype(str).isin(DISPLAY_SERIES_ORDER)].copy()
    data["FY_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["FY_numeric"].ge(REVENUE_LAST_COMPLETE_ACTUAL_FY) & data["value_numeric"].notna()].copy()
    policy_lookup = _scenario_display_policy_lookup(scenario_role_contract)
    records: list[dict[str, Any]] = []
    for row in data.itertuples(index=False):
        series_id = str(getattr(row, "series_id", "") or "")
        fy = int(getattr(row, "FY_numeric"))
        scenario_name = str(getattr(row, "scenario_name", "") or "")
        scenario_role = str(getattr(row, "scenario_role", "") or "")
        display_policy = policy_lookup.get((scenario_name, series_id))
        trace_name = _runtime_current_trace_name(
            scenario_name,
            scenario_role,
            series_id=series_id,
            display_policy=display_policy,
        )
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
                trace_name=trace_name,
                trace_type=_runtime_trace_type(trace_name),
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
                plot_allowed=display_policy != "hide_comparison_intensity_trace",
                formula=getattr(row, "formula", ""),
                source_basis=getattr(row, "source_basis", ""),
                vktpc_source_file=getattr(row, "vktpc_source_file", ""),
                vktpc_source_cell=getattr(row, "vktpc_source_cell", ""),
                vktpc_source_status=getattr(row, "vktpc_source_status", ""),
                population_source_file=getattr(row, "population_source_file", ""),
                population_source_cell=getattr(row, "population_source_cell", ""),
                population_source_status=getattr(row, "population_source_status", ""),
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
        "vktpc_source_file",
        "vktpc_source_cell",
        "vktpc_source_status",
        "population_source_file",
        "population_source_cell",
        "population_source_status",
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
    vktpc_source_file: Any = "",
    vktpc_source_cell: Any = "",
    vktpc_source_status: Any = "",
    population_source_file: Any = "",
    population_source_cell: Any = "",
    population_source_status: Any = "",
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
        "vktpc_source_file": vktpc_source_file,
        "vktpc_source_cell": vktpc_source_cell,
        "vktpc_source_status": vktpc_source_status,
        "population_source_file": population_source_file,
        "population_source_cell": population_source_cell,
        "population_source_status": population_source_status,
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


def _scenario_display_policy_lookup(contract: pd.DataFrame | None) -> dict[tuple[str, str], str]:
    if contract is None or contract.empty:
        return {}
    required = {"scenario_name", "affected_series", "display_policy"}
    if required.difference(contract.columns):
        return {}
    lookup: dict[tuple[str, str], str] = {}
    for row in contract.itertuples(index=False):
        scenario_name = str(getattr(row, "scenario_name", "") or "")
        series_id = str(getattr(row, "affected_series", "") or "")
        display_policy = str(getattr(row, "display_policy", "") or "")
        if scenario_name and series_id and display_policy:
            lookup[(scenario_name, series_id)] = display_policy
    return lookup


def _runtime_current_trace_name(
    scenario_name: Any,
    scenario_role: Any,
    *,
    series_id: Any = None,
    display_policy: Any = None,
) -> str:
    role = str(scenario_role or "").strip().lower()
    name = str(scenario_name or "").strip().lower()
    if role == SCENARIO_ROLE_BASECASE or name == "current_basecase":
        return "Current finalist Base case"
    if (
        str(series_id or "") == "ped_vkt_per_capita"
        and str(display_policy or "") == "keep_trace_relabel_comparison_behavioural_path"
    ):
        return PED_COMPARISON_BEHAVIOURAL_TRACE_NAME
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
    if name == PED_COMPARISON_BEHAVIOURAL_TRACE_NAME:
        return "current finalist comparison behavioural"
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
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME: 4,
        "Official comparator: selected MOT/BEFU": 5,
        "Official comparator: rolling BEFU 1Y": 6,
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
    scenario_input_manifest: dict[str, Any] | None = None,
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
        "scenario_inputs": scenario_input_manifest or {
            "status": "missing",
            "repo_relative_output_dir": _repo_relative(repo_root, output_dir / SCENARIO_INPUT_DIRNAME),
        },
        "scenario_input_delta_audit": {
            "repo_relative_path": _repo_relative(repo_root, output_dir / "scenario_input_delta_audit.csv"),
            "source": f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_LONG_STEM}.parquet",
            "scope": (
                "Workbook-cell base/comparison deltas derived from committed scenario_input_long artifacts, "
                "including source cells, workbook hashes, scenario roles and variable classifications."
            ),
        },
        "scenario_feature_lineage": {
            "repo_relative_path": _repo_relative(repo_root, output_dir / "scenario_feature_lineage.csv"),
            "source": f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_FEATURE_LINEAGE_STEM}.parquet",
            "scope": "Feature-level lineage from committed scenario input artifacts to fixed finalist forecast variables.",
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
            "scenario_input_delta_audit.parquet",
            "scenario_input_delta_audit.csv",
            "scenario_feature_lineage.parquet",
            "scenario_feature_lineage.csv",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_CELLS_STEM}.parquet",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_CELLS_STEM}.csv",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_LONG_STEM}.parquet",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_LONG_STEM}.csv",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_WIDE_STEM}.parquet",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_WIDE_STEM}.csv",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_FEATURE_LINEAGE_STEM}.parquet",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_FEATURE_LINEAGE_STEM}.csv",
            f"{SCENARIO_INPUT_DIRNAME}/{SCENARIO_INPUT_MANIFEST}",
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
        "ev_phev_ped_light_drift_assumptions",
        "ped_revenue_bridge_audit",
        "ped_bridge_shape_fit_metrics",
        "ped_bridge_mode_config",
        "ped_efficiency_scenarios",
        "sensitivity_seed_inputs",
        "sensitivity_config",
        "sensitivity_impact_audit",
        "scenario_input_delta_audit",
        "scenario_input_replay_mismatch_report",
        "scenario_feature_lineage",
        "scenario_role_contract",
        "revenue_formula_residuals",
        "series_alias_audit",
        "runtime_cutoff_audit",
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

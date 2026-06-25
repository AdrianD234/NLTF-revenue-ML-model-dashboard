"""Repo-local NLTF revenue source-pack loader and canonical schema.

The normalized source pack is the contract for the Revenue Outlook page. This
module does not load the raw workbook and does not use Excel coordinates as
runtime logic; source cells are lineage metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


REVENUE_SOURCE_PACK_DIR = Path("data") / "revenue_model_source_pack" / "2026_05_19"
CURRENT_REVENUE_OUTLOOK_DIR = Path("data") / "current_revenue_outlook"
REVENUE_SOURCE_PACK_SCHEMA_VERSION = "nltf-revenue-source-pack-v1"
CANONICAL_REVENUE_SCHEMA_VERSION = "nltf-revenue-canonical-long-v2"
REVENUE_SOURCE_PACK_RUNTIME_REVISION = "2026-06-25-normalized-source-row-hashes-v1"
REVENUE_MODEL_TRAINING_CUTOFF = "2025Q4"
REVENUE_FIRST_FORECAST_QUARTER = "2026Q1"
REVENUE_SOURCE_ACTUAL_CUTOFF = "2026Q1"
REVENUE_LAST_COMPLETE_ACTUAL_FY = 2025
REVENUE_PARTIAL_ACTUAL_FY = 2026

REQUIRED_SOURCE_PACK_FILES = (
    "README.md",
    "MODEL_WORKFLOW.md",
    "manifest.json",
    "series_master.csv",
    "aggregation_rules.csv",
    "front_end_config.json",
    "unresolved_decisions.csv",
    "annual_actuals.csv",
    "annual_model_paths.csv",
    "release_registry.csv",
)
OPTIONAL_SOURCE_PACK_FILES = (
    "release_values.csv",
    "forecast_archive.csv",
    "quarterly_actuals.csv",
    "fed_rate_paths.csv",
    "ped_bridge_inputs.csv",
    "mot_error_bands.csv",
    "official_befu25_annual.csv",
)

TOTAL_NLTF_COMPLETENESS_SERIES = (
    "Gross PED exGST",
    "Gross LPG exGST",
    "Gross CNG exGST",
    "FED refunds total exGST",
    "Total RUC all classes exGST",
    "Net MVR revenue exGST",
    "TUC revenue exGST",
)

CORE_ROLLUP_SERIES = {
    "gross_fed_revenue",
    "net_fed_revenue",
    "total_ruc_net_revenue",
    "net_mvr_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
}
HYBRID_REPLACEMENT_SERIES = {
    "gross_ped_revenue",
    "light_ruc_net_revenue",
    "heavy_ruc_net_revenue",
}

# Explicit, reviewed label bindings from the distilled pack. Labels not covered
# here are still preserved with generated IDs and a source_registry_gap status.
SOURCE_SERIES_ALIASES = {
    "Total NLTF revenue": "total_nltf_net_revenue",
    "Total net revenues": "total_nltf_net_revenue",
    "Total RUC+PED revenue": "total_fed_ruc_net_revenue",
    "Total FED+RUC net revenue": "total_fed_ruc_net_revenue",
    "Total RUC forecast incl EV/PHEV": "total_ruc_net_revenue",
    "RUC revenues net of admin fees & refunds": "total_ruc_net_revenue",
    "Net FED revenue": "net_fed_revenue",
    "Gross FED revenue": "gross_fed_revenue",
    "PED revenue": "gross_ped_revenue",
    "Gross PED revenue": "gross_ped_revenue",
    "Gross LPG revenue": "gross_lpg_revenue",
    "Gross CNG revenue": "gross_cng_revenue",
    "FED refunds": "fed_refunds",
    "Light RUC revenue": "light_ruc_net_revenue",
    "Light RUC net revenue": "light_ruc_net_revenue",
    "Light conventional RUC revenue": "light_ruc_net_revenue",
    "Heavy RUC revenue": "heavy_ruc_net_revenue",
    "Heavy RUC net revenue": "heavy_ruc_net_revenue",
    "Heavy conventional RUC revenue": "heavy_ruc_net_revenue",
    "Light BEV RUC net revenue": "light_bev_ruc_net_revenue",
    "Heavy BEV RUC net revenue": "heavy_bev_ruc_net_revenue",
    "PHEV RUC net revenue": "phev_ruc_net_revenue",
    "RUC admin revenue": "ruc_admin_revenue",
    "RUC refunds": "ruc_refunds",
    "Net MVR revenue": "net_mvr_revenue",
    "MVR revenues net of admin fees, refunds & COO": "net_mvr_revenue",
    "MVR revenues net of admin fees & COO": "net_mvr_revenue",
    "MVR admin revenue": "mvr_admin_revenue",
    "MVR refunds": "mvr_refunds",
    "TUC net revenue": "tuc_net_revenue",
    "Crown top-up": "crown_top_up",
    "FED / PED Crown top-up": "crown_top_up",
    "Total top-up": "crown_top_up",
    "Gross PED exGST": "gross_ped_revenue",
    "PED raw actual exGST": "gross_ped_revenue",
    "Gross LPG exGST": "gross_lpg_revenue",
    "Gross CNG exGST": "gross_cng_revenue",
    "FED refunds total exGST": "fed_refunds",
    "RUC refunds exGST": "ruc_refunds",
    "MVR refunds exGST": "mvr_refunds",
    "MR1 & CVL revenue exGST": "mr1_cvl_revenue",
    "MR2 revenue exGST": "mr2_revenue",
    "COO revenue exGST": "coo_revenue",
    "MVR admin revenue exGST": "mvr_admin_revenue",
    "Net MVR revenue exGST": "net_mvr_revenue",
    "PED VKT per capita": "ped_vkt_per_capita",
    "PED volume": "ped_volume",
    "PED/FED rate path": "ped_fed_rate_path",
    "Population count": "population_count",
    "Forecast input population count": "forecast_input_population_count",
    "PED total VKT": "ped_total_vkt",
    "PED source-backed litres": "ped_source_backed_litres",
    "PED litres per 100km": "ped_litres_per_100km",
    "Light RUC net km": "light_ruc_net_km",
    "Heavy RUC net km": "heavy_ruc_net_km",
    "Light BEV RUC net km": "light_bev_ruc_net_km",
    "Heavy BEV RUC net km": "heavy_bev_ruc_net_km",
    "PHEV RUC net km": "phev_ruc_net_km",
}

RUNTIME_DERIVED_BRIDGE_SERIES = {
    "forecast_input_population_count",
    "population_count",
    "ped_fed_rate_path",
    "ped_litres_per_100km",
    "ped_source_backed_litres",
}

REQUIRED_ROLLUP_INPUTS = {
    "gross_fed_revenue": ["gross_ped_revenue", "gross_lpg_revenue", "gross_cng_revenue"],
    "net_fed_revenue": ["gross_fed_revenue", "fed_refunds"],
    "total_ruc_net_revenue": [
        "light_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "heavy_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
    ],
    # Net MVR is not reconstructible from admin/refunds alone. The distilled
    # source preserves the total and partial deduction lines, but not the MR1/CVL,
    # MR2, and COO component rows needed for a governed rollup replay.
    "net_mvr_revenue": ["mr1_cvl_revenue", "mr2_revenue", "coo_revenue", "mvr_admin_revenue", "mvr_refunds"],
    "total_fed_ruc_net_revenue": ["net_fed_revenue", "total_ruc_net_revenue"],
    "total_nltf_net_revenue": ["net_fed_revenue", "total_ruc_net_revenue", "net_mvr_revenue", "tuc_net_revenue"],
}

OPTIONAL_ROLLUP_INPUTS = {
    "net_fed_revenue": ["crown_top_up"],
}

REVENUE_BASIS_LABELS = {
    "net": "Net",
    "gross": "Gross",
    "admin": "Admin",
    "deduction": "Deductions",
    "nominal_ex_gst": "Nominal ex GST",
}
REVENUE_PATH_TO_BASIS = {
    "net of admin fees & refunds": "Net",
    "gross / benchmark actual": "Gross",
}


@dataclass
class RevenueSourcePack:
    pack_dir: Path
    manifest: dict[str, Any]
    series_master: pd.DataFrame
    aggregation_rules: pd.DataFrame
    front_end_config: dict[str, Any]
    unresolved_decisions: pd.DataFrame
    annual_actuals: pd.DataFrame
    annual_model_paths: pd.DataFrame
    release_registry: pd.DataFrame
    release_values: pd.DataFrame
    forecast_archive: pd.DataFrame
    quarterly_actuals: pd.DataFrame
    fed_rate_paths: pd.DataFrame
    ped_bridge_inputs: pd.DataFrame
    mot_error_bands: pd.DataFrame
    official_befu25_annual: pd.DataFrame
    canonical_long: pd.DataFrame
    validation_issues: pd.DataFrame
    reconciliation_report: pd.DataFrame
    source_gap_register: pd.DataFrame
    path_trace_status: pd.DataFrame
    intake_status: pd.DataFrame
    remaining_decisions_handoff: pd.DataFrame
    series_role_audit: pd.DataFrame
    hybrid_annual_revenue: pd.DataFrame
    annual_completeness_audit: pd.DataFrame
    current_forecast_annual: pd.DataFrame
    data_vintage_manifest: dict[str, Any]
    series_trace_contract: pd.DataFrame
    series_junction_audit: pd.DataFrame

    @property
    def validation_status(self) -> str:
        if self.validation_issues.empty:
            return "passed"
        severities = set(self.validation_issues["severity"].astype(str))
        return "failed" if "error" in severities else "warning"


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def revenue_source_pack_signature(
    pack_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> tuple[tuple[str, int, int], ...]:
    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    base = Path(pack_dir) if pack_dir is not None else root / REVENUE_SOURCE_PACK_DIR
    signature_paths = [base / filename for filename in REQUIRED_SOURCE_PACK_FILES]
    manifest_path = base / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        declared_files = _manifest_declared_files(manifest)
        existing = {path.name for path in signature_paths}
        signature_paths.extend(base / filename for filename in declared_files if filename not in existing)
    signature = []
    for path in signature_paths:
        try:
            stat = path.stat()
        except OSError:
            signature.append((path.as_posix(), 0, 0))
        else:
            signature.append((path.as_posix(), int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(signature)


def load_revenue_source_pack(
    pack_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> RevenueSourcePack | None:
    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    base = Path(pack_dir) if pack_dir is not None else root / REVENUE_SOURCE_PACK_DIR
    if not (base / "manifest.json").exists():
        return None
    missing = [filename for filename in REQUIRED_SOURCE_PACK_FILES if not (base / filename).exists()]
    if missing:
        raise FileNotFoundError(f"Revenue source pack is missing required files: {', '.join(missing)}")

    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    series_master = pd.read_csv(base / "series_master.csv")
    aggregation_rules = pd.read_csv(base / "aggregation_rules.csv")
    front_end_config = json.loads((base / "front_end_config.json").read_text(encoding="utf-8"))
    unresolved_decisions = pd.read_csv(base / "unresolved_decisions.csv")
    annual_actuals = pd.read_csv(base / "annual_actuals.csv")
    annual_model_paths = pd.read_csv(base / "annual_model_paths.csv")
    release_registry = pd.read_csv(base / "release_registry.csv")
    release_values = _read_optional_csv(base / "release_values.csv")
    forecast_archive = _read_optional_csv(base / "forecast_archive.csv")
    quarterly_actuals = _read_optional_csv(base / "quarterly_actuals.csv")
    fed_rate_paths = _read_optional_csv(base / "fed_rate_paths.csv")
    ped_bridge_inputs = _read_optional_csv(base / "ped_bridge_inputs.csv")
    mot_error_bands = _read_optional_csv(base / "mot_error_bands.csv")
    official_befu25_annual = _read_optional_csv(base / "official_befu25_annual.csv")
    current_outlook_manifest, current_outlook_chart_rows = _load_current_revenue_outlook(root)
    annual_completeness = annual_completeness_audit_frame(
        quarterly_actuals=quarterly_actuals,
        annual_model_paths=annual_model_paths,
        official_befu25_annual=official_befu25_annual,
    )
    data_vintage = data_vintage_manifest_payload(
        repo_root=root,
        source_pack_dir=base,
        source_pack_manifest=manifest,
        current_outlook_manifest=current_outlook_manifest,
        current_outlook_chart_rows=current_outlook_chart_rows,
        quarterly_actuals=quarterly_actuals,
        annual_completeness=annual_completeness,
    )

    canonical = canonical_revenue_long_frame(
        series_master=series_master,
        annual_actuals=annual_actuals,
        annual_model_paths=annual_model_paths,
        release_values=release_values,
        quarterly_actuals=quarterly_actuals,
        fed_rate_paths=fed_rate_paths,
        ped_bridge_inputs=ped_bridge_inputs,
        official_befu25_annual=official_befu25_annual,
        manifest=manifest,
    )
    reconciliation = revenue_reconciliation_report(canonical)
    gap_register = revenue_source_gap_register(
        manifest=manifest,
        front_end_config=front_end_config,
        canonical_long=canonical,
    )
    current_forecast_annual = current_forecast_annual_frame(
        canonical_long=canonical,
        current_outlook_chart_rows=current_outlook_chart_rows,
        official_befu25_annual=official_befu25_annual,
        fed_rate_paths=fed_rate_paths,
        ped_bridge_inputs=ped_bridge_inputs,
    )
    path_trace_status = revenue_path_trace_status(
        canonical_long=canonical,
        gap_register=gap_register,
        current_forecast_annual=current_forecast_annual,
    )
    intake_status = revenue_source_pack_intake_status(
        pack_dir=base,
        manifest=manifest,
    )
    remaining_decisions = revenue_remaining_decisions_handoff(
        unresolved_decisions=unresolved_decisions,
        gap_register=gap_register,
    )
    validation = validate_revenue_source_pack(
        manifest=manifest,
        pack_dir=base,
        series_master=series_master,
        aggregation_rules=aggregation_rules,
        front_end_config=front_end_config,
        unresolved_decisions=unresolved_decisions,
        remaining_decisions_handoff=remaining_decisions,
        canonical_long=canonical,
    )
    role_audit = revenue_series_role_audit(
        series_master=series_master,
        canonical_long=canonical,
    )
    hybrid_annual = revenue_hybrid_annual_frame(canonical, current_forecast_annual=current_forecast_annual)
    series_trace_contract = series_trace_contract_frame(
        series_master=series_master,
        front_end_config=front_end_config,
        canonical_long=canonical,
        current_forecast_annual=current_forecast_annual,
        data_vintage_manifest=data_vintage,
    )
    series_junction_audit = series_junction_audit_frame(
        series_trace_contract=series_trace_contract,
        canonical_long=canonical,
        current_forecast_annual=current_forecast_annual,
        annual_completeness=annual_completeness,
        data_vintage_manifest=data_vintage,
    )
    return RevenueSourcePack(
        pack_dir=base,
        manifest=manifest,
        series_master=series_master,
        aggregation_rules=aggregation_rules,
        front_end_config=front_end_config,
        unresolved_decisions=unresolved_decisions,
        annual_actuals=annual_actuals,
        annual_model_paths=annual_model_paths,
        release_registry=release_registry,
        release_values=release_values,
        forecast_archive=forecast_archive,
        quarterly_actuals=quarterly_actuals,
        fed_rate_paths=fed_rate_paths,
        ped_bridge_inputs=ped_bridge_inputs,
        mot_error_bands=mot_error_bands,
        official_befu25_annual=official_befu25_annual,
        canonical_long=canonical,
        validation_issues=validation,
        reconciliation_report=reconciliation,
        source_gap_register=gap_register,
        path_trace_status=path_trace_status,
        intake_status=intake_status,
        remaining_decisions_handoff=remaining_decisions,
        series_role_audit=role_audit,
        hybrid_annual_revenue=hybrid_annual,
        annual_completeness_audit=annual_completeness,
        current_forecast_annual=current_forecast_annual,
        data_vintage_manifest=data_vintage,
        series_trace_contract=series_trace_contract,
        series_junction_audit=series_junction_audit,
    )


def _read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _load_current_revenue_outlook(repo_root: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    base = repo_root / CURRENT_REVENUE_OUTLOOK_DIR
    manifest_path = base / "manifest.json"
    chart_path = base / "revenue_chart_rows.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    chart_rows = pd.read_csv(chart_path, low_memory=False) if chart_path.exists() else pd.DataFrame()
    return manifest, chart_rows


def data_vintage_manifest_payload(
    *,
    repo_root: Path,
    source_pack_dir: Path,
    source_pack_manifest: dict[str, Any],
    current_outlook_manifest: dict[str, Any],
    current_outlook_chart_rows: pd.DataFrame,
    quarterly_actuals: pd.DataFrame,
    annual_completeness: pd.DataFrame,
) -> dict[str, Any]:
    scenarios = current_outlook_manifest.get("source_comparison", {}).get("scenarios", [])
    scenario_records = []
    for scenario in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(scenario, dict):
            continue
        scenario_records.append(
            {
                "scenario_name": scenario.get("scenario_name", ""),
                "scenario_role": scenario.get("scenario_role", ""),
                "forecast_start_period": scenario.get("forecast_start_period", ""),
                "forecast_end_period": scenario.get("forecast_end_period", ""),
                "forecast_horizon_quarters": scenario.get("forecast_horizon_quarters", ""),
            }
        )

    output_hashes = current_outlook_manifest.get("output_hashes", {})
    source_pack_hashes = source_pack_manifest.get("normalized_files", {})
    latest_source_actual = REVENUE_SOURCE_ACTUAL_CUTOFF
    if isinstance(quarterly_actuals, pd.DataFrame) and not quarterly_actuals.empty and "quarter" in quarterly_actuals.columns:
        quarter_text = quarterly_actuals["quarter"].dropna().astype(str)
        bounded = quarter_text[quarter_text.map(_quarter_sort_key) <= _quarter_sort_key(REVENUE_SOURCE_ACTUAL_CUTOFF)]
        if not bounded.empty:
            latest_source_actual = max(bounded, key=_quarter_sort_key)
    return {
        "schema_version": "nltf-revenue-data-vintage-v1",
        "repo_relative_source_pack_dir": _repo_relative_path(source_pack_dir, repo_root),
        "repo_relative_current_revenue_outlook_dir": CURRENT_REVENUE_OUTLOOK_DIR.as_posix(),
        "model_training_cutoff": REVENUE_MODEL_TRAINING_CUTOFF,
        "model_refit_cutoff": REVENUE_MODEL_TRAINING_CUTOFF,
        "first_model_forecast_quarter": REVENUE_FIRST_FORECAST_QUARTER,
        "first_model_forecast_fy": f"FY{REVENUE_PARTIAL_ACTUAL_FY}",
        "revenue_source_actual_cutoff": latest_source_actual,
        "last_complete_actual_fy": REVENUE_LAST_COMPLETE_ACTUAL_FY,
        "partial_actual_fy": REVENUE_PARTIAL_ACTUAL_FY,
        "partial_actual_quarters": "2025Q3; 2025Q4; 2026Q1",
        "missing_partial_actual_quarters": "2026Q2",
        "current_outlook_pack_status": current_outlook_manifest.get("pack_status", ""),
        "current_outlook_promotion_time": current_outlook_manifest.get("promotion_time", ""),
        "current_outlook_model_ids": current_outlook_manifest.get("model_ids", {}),
        "current_outlook_scenarios": scenario_records,
        "current_outlook_output_hashes": output_hashes,
        "source_pack_normalized_hashes": {
            filename: metadata.get("sha256", "")
            for filename, metadata in source_pack_hashes.items()
            if isinstance(metadata, dict)
        },
        "annual_completeness_rows": int(len(annual_completeness)) if isinstance(annual_completeness, pd.DataFrame) else 0,
        "current_outlook_chart_rows": int(len(current_outlook_chart_rows)) if isinstance(current_outlook_chart_rows, pd.DataFrame) else 0,
        "policy_note": (
            "Models are trained/refitted through 2025Q4. 2026Q1 is an observation/source actual, "
            "not a model-training row. FY2026 is partial actual-to-date unless explicitly shown as "
            "actual-plus-forecast-to-go nowcast."
        ),
    }


def _repo_relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def canonical_revenue_long_frame(
    *,
    series_master: pd.DataFrame,
    annual_actuals: pd.DataFrame,
    annual_model_paths: pd.DataFrame,
    release_values: pd.DataFrame | None = None,
    quarterly_actuals: pd.DataFrame | None = None,
    fed_rate_paths: pd.DataFrame | None = None,
    ped_bridge_inputs: pd.DataFrame | None = None,
    official_befu25_annual: pd.DataFrame | None = None,
    manifest: dict[str, Any],
) -> pd.DataFrame:
    registry = _registry(series_master)
    rows = []
    source_hash = str(manifest.get("raw_workbook", {}).get("sha256", ""))
    distilled_hash = str(manifest.get("distilled_workbook", {}).get("sha256", ""))
    normalized_hashes = _normalized_file_hashes(manifest)

    for record in annual_actuals.to_dict("records"):
        label = str(record.get("Series", "")).strip()
        fy = _as_int(record.get("FY June"))
        rows.append(
            _canonical_row(
                registry,
                source_label=label,
                period=f"FY{fy}" if fy is not None else "",
                fy=fy,
                group=record.get("Group", ""),
                value=record.get("Value"),
                unit=record.get("Unit", ""),
                line="Actual",
                release_vintage="actual",
                forecast_path="official_actual",
                scenario_name="actual",
                scenario_role="actual",
                model_basis="official_actuals",
                source_file="annual_actuals.csv",
                source_sheet=record.get("Source sheet", ""),
                source_cell=record.get("Source cell", ""),
                normalized_source_sha256=normalized_hashes.get("annual_actuals.csv", ""),
                source_hash_sha256=source_hash,
                distilled_hash_sha256=distilled_hash,
            )
        )

    for record in annual_model_paths.to_dict("records"):
        label = str(record.get("Series", "")).strip()
        fy = _as_int(record.get("FY June"))
        line = str(record.get("Line", "")).strip()
        model_basis = str(record.get("Model basis", "")).strip()
        rows.append(
            _canonical_row(
                registry,
                source_label=label,
                period=f"FY{fy}" if fy is not None else "",
                fy=fy,
                group=record.get("Group", ""),
                value=record.get("Value"),
                unit=record.get("Unit", ""),
                line=line,
                release_vintage=_release_vintage(model_basis, line),
                forecast_path=_forecast_path(model_basis, line),
                scenario_name=_scenario_name(model_basis, line),
                scenario_role=_scenario_role(line),
                model_basis=model_basis,
                source_file="annual_model_paths.csv",
                source_sheet=record.get("Source sheet", ""),
                source_cell=record.get("Source cell", ""),
                normalized_source_sha256=normalized_hashes.get("annual_model_paths.csv", ""),
                source_hash_sha256=source_hash,
                distilled_hash_sha256=distilled_hash,
            )
        )

    if isinstance(release_values, pd.DataFrame) and not release_values.empty:
        for record in release_values.to_dict("records"):
            label = str(record.get("series", "")).strip()
            fy = _as_int(record.get("FY"))
            release_round = str(record.get("release_round", "")).strip()
            rows.append(
                _canonical_row(
                    registry,
                    source_label=label,
                    period=f"FY{fy}" if fy is not None else "",
                    fy=fy,
                    time_grain="june_year",
                    group="MOT release",
                    value=record.get("value"),
                    unit=record.get("unit", ""),
                    line=str(record.get("value_status", "forecast")).strip() or "forecast",
                    release_vintage=release_round,
                    release_family=record.get("release_family", ""),
                    release_year=record.get("release_year", ""),
                    horizon=record.get("horizon", ""),
                    forecast_path=f"mot_release:{release_round}" if release_round else "mot_release",
                    scenario_name=release_round or "MOT release",
                    scenario_role="mot_release",
                    model_basis="mot_release",
                    value_status=record.get("value_status", ""),
                    source_file="release_values.csv",
                    source_sheet=record.get("source_sheet", ""),
                    source_cell=record.get("source_cell", ""),
                    normalized_source_sha256=normalized_hashes.get("release_values.csv", ""),
                    source_hash_sha256=source_hash,
                    distilled_hash_sha256=distilled_hash,
                )
            )

    if isinstance(quarterly_actuals, pd.DataFrame) and not quarterly_actuals.empty:
        for record in quarterly_actuals.to_dict("records"):
            label = str(record.get("series", "")).strip()
            quarter = str(record.get("quarter", "")).strip().upper()
            fy = _as_int(record.get("FY"))
            rows.append(
                _canonical_row(
                    registry,
                    source_label=label,
                    period=quarter,
                    fy=fy,
                    time_grain="quarterly",
                    group="Quarterly actuals",
                    value=record.get("value"),
                    unit=record.get("unit", ""),
                    line=str(record.get("value_status", "actual")).strip() or "actual",
                    release_vintage="actual",
                    forecast_path="official_actual",
                    scenario_name="actual",
                    scenario_role="actual",
                    model_basis="official_actuals",
                    value_status=record.get("value_status", ""),
                    source_file="quarterly_actuals.csv",
                    source_sheet=record.get("source_sheet", ""),
                    source_cell=record.get("source_cell", ""),
                    normalized_source_sha256=normalized_hashes.get("quarterly_actuals.csv", ""),
                    source_hash_sha256=source_hash,
                    distilled_hash_sha256=distilled_hash,
                )
            )

    if isinstance(fed_rate_paths, pd.DataFrame) and not fed_rate_paths.empty:
        for record in fed_rate_paths.to_dict("records"):
            quarter = str(record.get("quarter", "")).strip().upper()
            fy = _as_int(record.get("FY"))
            fed_path = str(record.get("fed_path", "")).strip()
            rows.append(
                _canonical_row(
                    registry,
                    source_label="PED/FED rate path",
                    period=quarter,
                    fy=fy,
                    time_grain="quarterly",
                    group="FED rates",
                    value=record.get("rate_nzd_per_litre"),
                    unit=record.get("unit", "NZD/L"),
                    line="rate_path",
                    release_vintage="rate_path",
                    forecast_path=f"fed_path:{fed_path}" if fed_path else "fed_path",
                    scenario_name=fed_path,
                    scenario_role="fed_path",
                    model_basis="fed_rate_path",
                    value_status=record.get("value_status", ""),
                    source_file="fed_rate_paths.csv",
                    source_sheet=record.get("source_sheet", ""),
                    source_cell=record.get("source_cell", ""),
                    normalized_source_sha256=normalized_hashes.get("fed_rate_paths.csv", ""),
                    source_hash_sha256=source_hash,
                    distilled_hash_sha256=distilled_hash,
                )
            )

    if isinstance(ped_bridge_inputs, pd.DataFrame) and not ped_bridge_inputs.empty:
        for record in ped_bridge_inputs.to_dict("records"):
            label = str(record.get("series", "")).strip()
            period = str(record.get("period", "")).strip()
            fy = _as_int(record.get("FY"))
            time_grain = str(record.get("time_grain", "")).strip() or ("quarterly" if "Q" in period else "june_year")
            rows.append(
                _canonical_row(
                    registry,
                    source_label=label,
                    period=period,
                    fy=fy,
                    time_grain=time_grain,
                    group="PED bridge",
                    value=record.get("value"),
                    unit=record.get("unit", ""),
                    line=str(record.get("value_status", "ped_bridge")).strip() or "ped_bridge",
                    release_vintage="ped_bridge",
                    forecast_path="ped_bridge",
                    scenario_name=record.get("source_basis", "PED bridge"),
                    scenario_role="ped_bridge",
                    model_basis="ped_bridge",
                    value_status=record.get("value_status", ""),
                    source_file="ped_bridge_inputs.csv",
                    source_sheet=record.get("source_sheet", ""),
                    source_cell=record.get("source_cell", ""),
                    normalized_source_sha256=normalized_hashes.get("ped_bridge_inputs.csv", ""),
                    source_hash_sha256=source_hash,
                    distilled_hash_sha256=distilled_hash,
                )
            )

    if isinstance(official_befu25_annual, pd.DataFrame) and not official_befu25_annual.empty:
        for record in official_befu25_annual.to_dict("records"):
            label = str(record.get("series", "")).strip()
            fy = _as_int(record.get("FY"))
            status = str(record.get("status", "")).strip().upper()
            line = "Actual" if status == "ACTUAL" else "Model path"
            rows.append(
                _canonical_row(
                    registry,
                    source_label=label,
                    period=f"FY{fy}" if fy is not None else "",
                    fy=fy,
                    time_grain="june_year",
                    group=record.get("group", "Official BEFU25 annual"),
                    value=record.get("value"),
                    unit=record.get("unit", ""),
                    line=line,
                    release_vintage=record.get("release_round", "BEFU25"),
                    release_family=record.get("release_family", "BEFU"),
                    release_year=record.get("release_year", 2025),
                    horizon=record.get("horizon", ""),
                    forecast_path="mot_release:BEFU25",
                    scenario_name="BEFU25",
                    scenario_role="mot_release",
                    model_basis="selected_mot_release",
                    value_status=record.get("value_status", ""),
                    source_file="official_befu25_annual.csv",
                    source_sheet=record.get("source_sheet", ""),
                    source_cell=record.get("source_cell", ""),
                    normalized_source_sha256=normalized_hashes.get("official_befu25_annual.csv", ""),
                    source_hash_sha256=source_hash,
                    distilled_hash_sha256=distilled_hash,
                )
            )

    frame = pd.DataFrame(rows)
    frame["schema_version"] = CANONICAL_REVENUE_SCHEMA_VERSION
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["FY"] = pd.to_numeric(frame["FY"], errors="coerce").astype("Int64")
    return frame.sort_values(
        [
            "time_grain",
            "FY",
            "source_file",
            "model_basis",
            "forecast_path",
            "line",
            "series_id",
            "source_cell",
        ],
        kind="stable",
    ).reset_index(drop=True)


def annual_completeness_audit_frame(
    *,
    quarterly_actuals: pd.DataFrame,
    annual_model_paths: pd.DataFrame,
    official_befu25_annual: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "FY",
        "expected_quarter_set",
        "quarters_present",
        "actual_quarters",
        "forecast_quarters",
        "coverage_count",
        "completeness_status",
        "source_cutoff",
        "source_cells",
        "source_status",
        "annual_actual_value",
        "annual_actual_source_cell",
        "selected_model_value",
        "selected_model_source_cell",
        "official_befu25_value",
        "official_befu25_status",
        "workbook_formula_cells",
        "missing_formula_cells",
        "chart_treatment",
        "nowcast_flag",
        "notes",
    ]
    fy_values: set[int] = set()
    if isinstance(quarterly_actuals, pd.DataFrame) and not quarterly_actuals.empty and "FY" in quarterly_actuals.columns:
        fy_values.update(int(value) for value in pd.to_numeric(quarterly_actuals["FY"], errors="coerce").dropna().unique())
    if isinstance(annual_model_paths, pd.DataFrame) and not annual_model_paths.empty and "FY June" in annual_model_paths.columns:
        fy_values.update(int(value) for value in pd.to_numeric(annual_model_paths["FY June"], errors="coerce").dropna().unique())
    if isinstance(official_befu25_annual, pd.DataFrame) and not official_befu25_annual.empty and "FY" in official_befu25_annual.columns:
        fy_values.update(int(value) for value in pd.to_numeric(official_befu25_annual["FY"], errors="coerce").dropna().unique())
    rows: list[dict[str, Any]] = []
    quarterly = quarterly_actuals.copy() if isinstance(quarterly_actuals, pd.DataFrame) else pd.DataFrame()
    if not quarterly.empty:
        quarterly["FY_int"] = pd.to_numeric(quarterly.get("FY"), errors="coerce").astype("Int64")
        quarterly["quarter_text"] = quarterly.get("quarter", pd.Series("", index=quarterly.index)).fillna("").astype(str).str.upper()
        quarterly["status_text"] = quarterly.get("value_status", pd.Series("", index=quarterly.index)).fillna("").astype(str).str.lower()
        quarterly = quarterly[quarterly["series"].astype(str).isin(TOTAL_NLTF_COMPLETENESS_SERIES)].copy()
    annual = annual_model_paths.copy() if isinstance(annual_model_paths, pd.DataFrame) else pd.DataFrame()
    official = official_befu25_annual.copy() if isinstance(official_befu25_annual, pd.DataFrame) else pd.DataFrame()
    for fy in sorted(fy_values):
        expected_quarters = _expected_june_year_quarters(fy)
        expected_set = set(expected_quarters)
        fy_quarters = quarterly[quarterly["FY_int"].eq(fy)].copy() if not quarterly.empty else pd.DataFrame()
        quarters_present = sorted(set(fy_quarters["quarter_text"].dropna().astype(str)) & expected_set, key=_quarter_sort_key)
        actual_rows = fy_quarters[fy_quarters["status_text"].str.contains("actual", na=False)].copy() if not fy_quarters.empty else pd.DataFrame()
        forecast_rows = fy_quarters[fy_quarters["status_text"].str.contains("forecast", na=False)].copy() if not fy_quarters.empty else pd.DataFrame()
        actual_sets: list[set[str]] = []
        for series in TOTAL_NLTF_COMPLETENESS_SERIES:
            if actual_rows.empty:
                actual_sets.append(set())
                continue
            series_rows = actual_rows[actual_rows["series"].astype(str).eq(series)]
            actual_sets.append(set(series_rows["quarter_text"].dropna().astype(str)) & expected_set)
        actual_quarters = sorted(set.intersection(*actual_sets) if actual_sets else set(), key=_quarter_sort_key)
        forecast_quarters = (
            sorted(set(forecast_rows["quarter_text"].dropna().astype(str)) & expected_set, key=_quarter_sort_key)
            if not forecast_rows.empty
            else []
        )
        coverage_count = len(actual_quarters)
        selected_actual = _annual_model_total_row(annual, fy, line="Actual")
        selected_model = _annual_model_total_row(annual, fy, line="Model path")
        official_row = _official_befu25_total_row(official, fy)
        official_status = str(official_row.get("status", "") if official_row is not None else "").upper()
        if selected_actual is not None and coverage_count == 4:
            completeness_status = "complete_actual"
            chart_treatment = "complete_actual_line"
        elif selected_actual is not None and coverage_count > 0:
            completeness_status = "partial_actual_to_date"
            chart_treatment = "partial_actual_marker_not_connected"
        elif official_row is not None and "FORECAST" in official_status:
            completeness_status = "forecast_only"
            chart_treatment = "forecast_path_only"
        elif official_row is not None:
            completeness_status = "official_status_actual_without_quarterly_coverage"
            chart_treatment = "not_plotted_as_actual"
        else:
            completeness_status = "no_actual_coverage"
            chart_treatment = "not_plotted_as_actual"
        source_cells = []
        if not actual_rows.empty and actual_quarters:
            source_cells = sorted(
                {
                    str(value).strip()
                    for value in actual_rows[actual_rows["quarter_text"].isin(actual_quarters)]["source_cell"].dropna()
                    if str(value).strip()
                },
                key=_cell_sort_key,
            )
        status_values = sorted({str(value).strip() for value in fy_quarters.get("value_status", pd.Series(dtype=str)).dropna() if str(value).strip()})
        formula_cells = ""
        missing_formula_cells = ""
        notes = ""
        if fy == 2026:
            formula_cells = "AZ163; BA163; BB163"
            missing_formula_cells = "BC163"
            notes = "Workbook FY2026 Actual formula is actual-to-date: AZ163+BA163+BB163; BC163 is the missing fourth quarter."
        rows.append(
            {
                "FY": fy,
                "expected_quarter_set": "; ".join(expected_quarters),
                "quarters_present": "; ".join(quarters_present),
                "actual_quarters": "; ".join(actual_quarters),
                "forecast_quarters": "; ".join(forecast_quarters),
                "coverage_count": coverage_count,
                "completeness_status": completeness_status,
                "source_cutoff": actual_quarters[-1] if actual_quarters else "",
                "source_cells": "; ".join(source_cells),
                "source_status": "; ".join(status_values),
                "annual_actual_value": selected_actual.get("Value") if selected_actual is not None else pd.NA,
                "annual_actual_source_cell": selected_actual.get("Source cell") if selected_actual is not None else "",
                "selected_model_value": selected_model.get("Value") if selected_model is not None else pd.NA,
                "selected_model_source_cell": selected_model.get("Source cell") if selected_model is not None else "",
                "official_befu25_value": official_row.get("value") if official_row is not None else pd.NA,
                "official_befu25_status": official_status,
                "workbook_formula_cells": formula_cells,
                "missing_formula_cells": missing_formula_cells,
                "chart_treatment": chart_treatment,
                "nowcast_flag": False,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def validate_revenue_source_pack(
    *,
    manifest: dict[str, Any],
    pack_dir: Path | None = None,
    series_master: pd.DataFrame,
    aggregation_rules: pd.DataFrame,
    front_end_config: dict[str, Any],
    unresolved_decisions: pd.DataFrame,
    remaining_decisions_handoff: pd.DataFrame | None = None,
    canonical_long: pd.DataFrame,
) -> pd.DataFrame:
    issues: list[dict[str, Any]] = []
    if manifest.get("schema_version") != REVENUE_SOURCE_PACK_SCHEMA_VERSION:
        issues.append(_issue("error", "manifest_schema", "Unexpected revenue source pack schema version."))
    if manifest.get("raw_workbook", {}).get("sha256") != "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b":
        issues.append(_issue("error", "raw_sha256", "Raw workbook SHA256 does not match the governed lineage hash."))
    issues.extend(_manifest_file_hash_issues(manifest, pack_dir))

    required_columns = {
        "period",
        "FY",
        "time_grain",
        "series_id",
        "parent_series_id",
        "value",
        "unit",
        "aggregation_sign",
        "release_vintage",
        "forecast_path",
        "path_status",
        "scenario_name",
        "scenario_role",
        "model_basis",
        "revenue_basis",
        "source_status",
        "bridge_status",
        "source_file",
        "source_cell",
        "normalized_source_sha256",
        "source_hash_sha256",
        "distilled_hash_sha256",
    }
    missing_columns = sorted(required_columns - set(canonical_long.columns))
    if missing_columns:
        issues.append(_issue("error", "canonical_schema", f"Missing canonical columns: {', '.join(missing_columns)}"))

    key_cols = [
        "source_file",
        "source_cell",
        "period",
        "series_id",
        "forecast_path",
        "model_basis",
        "line",
    ]
    if not canonical_long.empty and canonical_long.duplicated(key_cols).any():
        count = int(canonical_long.duplicated(key_cols).sum())
        issues.append(_issue("error", "uniqueness", f"Canonical source rows have {count} duplicate keys."))

    if canonical_long["unit"].fillna("").astype(str).str.strip().eq("").any():
        issues.append(_issue("error", "unit", "One or more canonical rows has no unit."))
    period_text = canonical_long["period"].fillna("").astype(str)
    valid_period = period_text.str.match(r"^FY\d{4}$") | period_text.str.match(r"^\d{4}Q[1-4]$")
    if valid_period.eq(False).any():
        issues.append(_issue("error", "period", "One or more canonical rows has an invalid FY or quarterly period label."))
    if canonical_long["aggregation_sign"].isin([-1, 0, 1]).eq(False).any():
        issues.append(_issue("error", "aggregation_sign", "Aggregation sign must be -1, 0, or +1."))

    registered = set(series_master["Series ID"].astype(str))
    parent_ids = set(series_master["Parent series ID"].dropna().astype(str)) - {""}
    missing_parents = sorted(parent_ids - registered)
    if missing_parents:
        issues.append(_issue("error", "hierarchy", f"Parent series IDs are missing from series_master: {', '.join(missing_parents)}"))

    output_ids = set(aggregation_rules["Output series ID"].astype(str))
    missing_outputs = sorted(output_ids - registered)
    if missing_outputs:
        issues.append(_issue("error", "aggregation_rules", f"Aggregation outputs missing from series_master: {', '.join(missing_outputs)}"))

    controls = front_end_config.get("controls", []) if isinstance(front_end_config, dict) else []
    required_controls = {"release_round", "series", "revenue_path", "scenario", "fed_path_scenario", "view", "model_basis", "uncertainty_source", "selected_fy", "crown_top_up"}
    control_ids = {str(item.get("control_id", "")) for item in controls if isinstance(item, dict)}
    missing_controls = sorted(required_controls - control_ids - set(front_end_config.get("current_selections", {}).keys()))
    if missing_controls:
        issues.append(_issue("warning", "front_end_config", f"Controls not present as selectable controls: {', '.join(missing_controls)}"))
    if "revenue_basis" not in control_ids:
        issues.append(
            _issue(
                "warning",
                "revenue_basis_alias",
                "Revenue basis is derived from normalized revenue_path controls; no separate workbook control is exposed.",
            )
        )

    gaps = canonical_long[canonical_long["source_status"].eq("unregistered_source_series")]["source_series_label"].dropna().unique()
    if len(gaps):
        issues.append(_issue("warning", "series_registry_gap", f"Unregistered source series preserved: {', '.join(sorted(map(str, gaps)))}"))

    if remaining_decisions_handoff is not None and not remaining_decisions_handoff.empty:
        critical_decisions = remaining_decisions_handoff[
            remaining_decisions_handoff["priority"].astype(str).str.lower().eq("critical")
            & ~remaining_decisions_handoff["availability_status"].astype(str).str.lower().isin(["source_backed"])
        ]
    else:
        critical_decisions = unresolved_decisions[unresolved_decisions["Priority"].astype(str).str.lower().eq("critical")]
    if not critical_decisions.empty:
        issues.append(
            _issue(
                "warning",
                "unresolved_critical_decisions",
                f"{len(critical_decisions)} critical revenue decisions remain explicit open gaps.",
            )
        )

    return pd.DataFrame(issues, columns=["severity", "check", "message"])


def revenue_reconciliation_report(canonical_long: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scope, frame in _reconciliation_scopes(canonical_long):
        for fy, fy_frame in frame.groupby("FY", dropna=True):
            values = fy_frame.groupby("series_id", dropna=False)["value"].first().to_dict()
            rows.extend(_rollup_rows(scope, int(fy), values))
    report = pd.DataFrame(rows)
    if report.empty:
        return pd.DataFrame(
            columns=[
                "scope",
                "FY",
                "output_series_id",
                "component_status",
                "calculated_value",
                "official_value",
                "difference",
                "abs_difference",
                "missing_inputs",
                "optional_inputs_applied",
            ]
        )
    report["abs_difference"] = pd.to_numeric(report["difference"], errors="coerce").abs()
    return report.sort_values(["scope", "FY", "output_series_id"], kind="stable").reset_index(drop=True)


def current_forecast_annual_frame(
    *,
    canonical_long: pd.DataFrame,
    current_outlook_chart_rows: pd.DataFrame,
    official_befu25_annual: pd.DataFrame,
    fed_rate_paths: pd.DataFrame,
    ped_bridge_inputs: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "FY",
        "period",
        "fed_path",
        "scenario_name",
        "scenario_role",
        "series_id",
        "display_name",
        "value",
        "unit",
        "row_role",
        "source_basis",
        "source_file",
        "source_cell",
        "source_status",
        "formula",
        "replacement_only",
        "official_value",
        "residual_vs_official",
        "availability_status",
        "line",
        "model_basis",
        "forecast_path",
        "path_status",
        "value_status",
        "quarters_present",
        "actual_quarters",
        "forecast_quarters",
        "nowcast_flag",
    ]
    if current_outlook_chart_rows is None or current_outlook_chart_rows.empty:
        return pd.DataFrame(columns=columns)

    activity = _current_activity_annual_values(current_outlook_chart_rows)
    if activity.empty:
        return pd.DataFrame(columns=columns)
    official = _official_annual_lookup(official_befu25_annual)
    ped_bridge = _ped_bridge_annual_lookup(ped_bridge_inputs)
    fed_rates = _fed_rate_annual_lookup(fed_rate_paths)
    crown_top_up = _crown_top_up_lookup(canonical_long)
    rows: list[dict[str, Any]] = []
    fed_paths = sorted({path for path, _fy in fed_rates}) or ["Selected rate"]
    keys = sorted({(str(row.scenario_name), int(row.FY)) for row in activity.itertuples()})
    for scenario_name, fy in keys:
        activity_values = {
            str(row.series_id): row
            for row in activity[activity["scenario_name"].eq(scenario_name) & activity["FY"].eq(fy)].itertuples()
        }
        required_activity = {"ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"}
        if not required_activity.issubset(activity_values):
            continue
        off = official.get(fy, {})
        bridge = ped_bridge.get(fy, {})
        required_official = {
            "gross_lpg_revenue",
            "gross_cng_revenue",
            "fed_refunds",
            "total_ruc_net_revenue",
            "light_ruc_net_revenue",
            "heavy_ruc_net_revenue",
            "light_ruc_net_km",
            "heavy_ruc_net_km",
            "net_mvr_revenue",
            "tuc_net_revenue",
            "gross_fed_revenue",
            "net_fed_revenue",
            "total_nltf_net_revenue",
        }
        required_bridge = {"population_count", "ped_litres_per_100km"}
        if not required_official.issubset(off) or not required_bridge.issubset(bridge):
            continue

        ped_activity = activity_values["ped_vkt_per_capita"]
        light_activity = activity_values["light_ruc_net_km"]
        heavy_activity = activity_values["heavy_ruc_net_km"]
        scenario_role = str(getattr(ped_activity, "scenario_role", "") or "")
        status = "actual_plus_forecast_to_go_nowcast" if bool(getattr(ped_activity, "nowcast_flag", False)) else "current_model_forecast"
        actual_quarters = str(getattr(ped_activity, "actual_quarters", "") or "")
        forecast_quarters = str(getattr(ped_activity, "forecast_quarters", "") or "")
        quarters_present = str(getattr(ped_activity, "quarters_present", "") or "")
        source_cell = f"current_revenue_outlook:{scenario_name}:FY{fy}"
        ped_vkt_per_capita = float(getattr(ped_activity, "value"))
        light_km_million = float(getattr(light_activity, "value"))
        heavy_km_million = float(getattr(heavy_activity, "value"))
        population_count = float(bridge["population_count"])
        ped_litres_per_100km = float(bridge["ped_litres_per_100km"])
        ped_total_vkt = ped_vkt_per_capita * population_count / 1_000_000.0
        ped_source_litres = ped_total_vkt * ped_litres_per_100km / 100.0
        light_rate = float(off["light_ruc_net_revenue"]) * 1000.0 / float(off["light_ruc_net_km"])
        heavy_rate = float(off["heavy_ruc_net_revenue"]) * 1000.0 / float(off["heavy_ruc_net_km"])
        light_revenue = light_km_million / 1000.0 * light_rate
        heavy_revenue = heavy_km_million / 1000.0 * heavy_rate
        ruc_fixed_residual = float(off["total_ruc_net_revenue"]) - float(off["light_ruc_net_revenue"]) - float(off["heavy_ruc_net_revenue"])
        for fed_path in fed_paths:
            ped_rate = fed_rates.get((fed_path, fy))
            if ped_rate is None:
                continue
            ped_revenue = ped_source_litres * float(ped_rate)
            gross_fed = ped_revenue + float(off["gross_lpg_revenue"]) + float(off["gross_cng_revenue"])
            net_fed = gross_fed - float(off["fed_refunds"])
            total_ruc = light_revenue + heavy_revenue + ruc_fixed_residual
            total_fed_ruc = net_fed + total_ruc
            total_nltf = total_fed_ruc + float(off["net_mvr_revenue"]) + float(off["tuc_net_revenue"])
            top_up = crown_top_up.get(fy, pd.NA)
            common = {
                "FY": fy,
                "period": f"FY{fy}",
                "fed_path": fed_path,
                "scenario_name": scenario_name,
                "scenario_role": scenario_role,
                "quarters_present": quarters_present,
                "actual_quarters": actual_quarters,
                "forecast_quarters": forecast_quarters,
                "nowcast_flag": bool(getattr(ped_activity, "nowcast_flag", False)),
                "value_status": status,
                "source_cell": source_cell,
            }
            rows.extend(
                [
                    _current_annual_row(**common, series_id="ped_vkt_per_capita", display_name="PED VKT per capita", value=ped_vkt_per_capita, unit="km/person", row_role="bridge_input", source_basis="current_finalist_model", source_file="data/current_revenue_outlook/revenue_chart_rows.csv"),
                    _current_annual_row(**common, series_id="population_count", display_name="Population count", value=population_count, unit="persons", row_role="bridge_input", source_basis="ped_bridge", source_file="ped_bridge_inputs.csv"),
                    _current_annual_row(**common, series_id="ped_total_vkt", display_name="Total light petrol VKT", value=ped_total_vkt, unit="million km", row_role="bridge_input", source_basis="current_finalist_model + ped_bridge", source_file="data/current_revenue_outlook/revenue_chart_rows.csv; ped_bridge_inputs.csv", formula="current PED VKT per capita * population / 1,000,000"),
                    _current_annual_row(**common, series_id="ped_litres_per_100km", display_name="PED litres per 100km", value=ped_litres_per_100km, unit="L/100km", row_role="bridge_input", source_basis="ped_bridge", source_file="ped_bridge_inputs.csv"),
                    _current_annual_row(**common, series_id="ped_source_backed_litres", display_name="PED source-backed litres", value=ped_source_litres, unit="million L", row_role="bridge_input", source_basis="current_finalist_model + ped_bridge", source_file="data/current_revenue_outlook/revenue_chart_rows.csv; ped_bridge_inputs.csv", formula="current PED total VKT * source-backed litres intensity / 100"),
                    _current_annual_row(**common, series_id="ped_fed_rate_path", display_name="PED/FED rate path", value=ped_rate, unit="NZD/L", row_role="bridge_input", source_basis=fed_path, source_file="fed_rate_paths.csv"),
                    _current_annual_row(**common, series_id="light_ruc_net_km", display_name="Light RUC net km", value=light_km_million, unit="million km", row_role="bridge_input", source_basis="current_finalist_model", source_file="data/current_revenue_outlook/revenue_chart_rows.csv"),
                    _current_annual_row(**common, series_id="light_ruc_effective_rate", display_name="Light RUC effective rate", value=light_rate, unit="NZD/1,000 km", row_role="bridge_input", source_basis="official_befu25_effective_rate", source_file="official_befu25_annual.csv", formula="official Light RUC net revenue / official Light RUC net km * 1,000"),
                    _current_annual_row(**common, series_id="heavy_ruc_net_km", display_name="Heavy RUC net km", value=heavy_km_million, unit="million km", row_role="bridge_input", source_basis="current_finalist_model", source_file="data/current_revenue_outlook/revenue_chart_rows.csv"),
                    _current_annual_row(**common, series_id="heavy_ruc_effective_rate", display_name="Heavy RUC effective rate", value=heavy_rate, unit="NZD/1,000 km", row_role="bridge_input", source_basis="official_befu25_effective_rate", source_file="official_befu25_annual.csv", formula="official Heavy RUC net revenue / official Heavy RUC net km * 1,000"),
                    _current_annual_row(**common, series_id="gross_ped_revenue", display_name="PED revenue", value=ped_revenue, unit="$m nominal ex GST", row_role="replacement_line", source_basis="current_finalist_model + ped_bridge + fed_rate_path", source_file="data/current_revenue_outlook/revenue_chart_rows.csv; ped_bridge_inputs.csv; fed_rate_paths.csv", formula="current PED VKT/capita forecast * population -> total VKT; litres intensity; FED rate", replacement_only=True, official_value=off["gross_ped_revenue"]),
                    _current_annual_row(**common, series_id="light_ruc_net_revenue", display_name="Light RUC revenue", value=light_revenue, unit="$m nominal ex GST", row_role="replacement_line", source_basis="current_finalist_model + official_effective_rate", source_file="data/current_revenue_outlook/revenue_chart_rows.csv; official_befu25_annual.csv", formula="current Light RUC net km / 1,000 * governed effective Light rate", replacement_only=True, official_value=off["light_ruc_net_revenue"]),
                    _current_annual_row(**common, series_id="heavy_ruc_net_revenue", display_name="Heavy RUC revenue", value=heavy_revenue, unit="$m nominal ex GST", row_role="replacement_line", source_basis="current_finalist_model + official_effective_rate", source_file="data/current_revenue_outlook/revenue_chart_rows.csv; official_befu25_annual.csv", formula="current Heavy RUC net km / 1,000 * governed class-mix Heavy rate", replacement_only=True, official_value=off["heavy_ruc_net_revenue"]),
                    _current_annual_row(**common, series_id="gross_lpg_revenue", display_name="Gross LPG revenue", value=off["gross_lpg_revenue"], unit="$m nominal ex GST", row_role="fixed_mot_component", source_basis="official_befu25_annual", source_file="official_befu25_annual.csv"),
                    _current_annual_row(**common, series_id="gross_cng_revenue", display_name="Gross CNG revenue", value=off["gross_cng_revenue"], unit="$m nominal ex GST", row_role="fixed_mot_component", source_basis="official_befu25_annual", source_file="official_befu25_annual.csv"),
                    _current_annual_row(**common, series_id="fed_refunds", display_name="FED refunds", value=off["fed_refunds"], unit="$m nominal ex GST", row_role="fixed_mot_deduction", source_basis="official_befu25_annual", source_file="official_befu25_annual.csv"),
                    _current_annual_row(**common, series_id="ruc_fixed_residual_net_revenue", display_name="RUC fixed residual", value=ruc_fixed_residual, unit="$m nominal ex GST", row_role="fixed_mot_component", source_basis="official_befu25_annual", source_file="official_befu25_annual.csv", formula="official total RUC - official Light RUC - official Heavy RUC"),
                    _current_annual_row(**common, series_id="net_mvr_revenue", display_name="Net MVR revenue", value=off["net_mvr_revenue"], unit="$m nominal ex GST", row_role="fixed_mot_component", source_basis="official_befu25_annual", source_file="official_befu25_annual.csv"),
                    _current_annual_row(**common, series_id="tuc_net_revenue", display_name="TUC net revenue", value=off["tuc_net_revenue"], unit="$m nominal ex GST", row_role="fixed_mot_component", source_basis="official_befu25_annual", source_file="official_befu25_annual.csv"),
                    _current_annual_row(**common, series_id="crown_top_up", display_name="Crown top-up / temporary fuel relief", value=top_up, unit="$m nominal ex GST", row_role="optional_overlay", source_basis="quarterly_actuals_annual_sum", source_file="quarterly_actuals.csv", formula="sum quarterly Crown top-up rows by June year", availability_status="available" if pd.notna(top_up) else "missing"),
                    _current_annual_row(**common, series_id="gross_fed_revenue", display_name="Gross FED revenue", value=gross_fed, unit="$m nominal ex GST", row_role="calculated_rollup", source_basis="current_hybrid_formula", source_file="current_hybrid_formula", formula="gross_ped_revenue + MOT gross_lpg_revenue + MOT gross_cng_revenue", official_value=off["gross_fed_revenue"]),
                    _current_annual_row(**common, series_id="net_fed_revenue", display_name="Net FED revenue", value=net_fed, unit="$m nominal ex GST", row_role="calculated_rollup", source_basis="current_hybrid_formula", source_file="current_hybrid_formula", formula="gross_fed_revenue - MOT fed_refunds", official_value=off["net_fed_revenue"]),
                    _current_annual_row(**common, series_id="total_ruc_net_revenue", display_name="Total RUC all classes", value=total_ruc, unit="$m nominal ex GST", row_role="calculated_rollup", source_basis="current_hybrid_formula", source_file="current_hybrid_formula", formula="light_ruc_net_revenue + heavy_ruc_net_revenue + MOT fixed RUC residual", official_value=off["total_ruc_net_revenue"]),
                    _current_annual_row(**common, series_id="total_fed_ruc_net_revenue", display_name="Total FED+RUC net revenue", value=total_fed_ruc, unit="$m nominal ex GST", row_role="calculated_rollup", source_basis="current_hybrid_formula", source_file="current_hybrid_formula", formula="net_fed_revenue + total_ruc_net_revenue"),
                    _current_annual_row(**common, series_id="total_nltf_net_revenue", display_name="Total NLTF revenue", value=total_nltf, unit="$m nominal ex GST", row_role="calculated_rollup", source_basis="current_hybrid_formula", source_file="current_hybrid_formula", formula="net_fed_revenue + total_ruc_net_revenue + MOT net_mvr_revenue + MOT tuc_net_revenue", official_value=off["total_nltf_net_revenue"]),
                ]
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame(rows)
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA if column in {"official_value", "residual_vs_official"} else ""
    return out[columns].sort_values(["FY", "scenario_name", "fed_path", "row_role", "series_id"], kind="stable").reset_index(drop=True)


def revenue_hybrid_annual_frame(canonical_long: pd.DataFrame, current_forecast_annual: pd.DataFrame | None = None) -> pd.DataFrame:
    columns = [
        "FY",
        "fed_path",
        "series_id",
        "display_name",
        "value",
        "unit",
        "row_role",
        "source_basis",
        "source_file",
        "source_status",
        "formula",
        "replacement_only",
        "official_value",
        "residual_vs_official",
        "availability_status",
    ]
    if isinstance(current_forecast_annual, pd.DataFrame) and not current_forecast_annual.empty:
        out = current_forecast_annual.copy()
        if "scenario_name" in out.columns:
            out = out[out["scenario_name"].astype(str).eq("current_basecase")].copy()
        for column in columns:
            if column not in out.columns:
                out[column] = pd.NA if column in {"official_value", "residual_vs_official"} else ""
        out["residual_vs_official"] = pd.to_numeric(out["residual_vs_official"], errors="coerce")
        return out[columns].sort_values(["FY", "row_role", "series_id"], kind="stable").reset_index(drop=True)

    columns = [
        "FY",
        "fed_path",
        "series_id",
        "display_name",
        "value",
        "unit",
        "row_role",
        "source_basis",
        "source_file",
        "source_status",
        "formula",
        "replacement_only",
        "official_value",
        "residual_vs_official",
        "availability_status",
    ]
    if canonical_long is None or canonical_long.empty:
        return pd.DataFrame(columns=columns)

    frame = canonical_long.copy()
    frame["value_numeric"] = pd.to_numeric(frame["value"], errors="coerce")
    official = frame[
        frame["source_file"].eq("official_befu25_annual.csv")
        & frame["time_grain"].eq("june_year")
        & frame["value_numeric"].notna()
    ].copy()
    in_house = frame[
        frame["source_file"].eq("annual_model_paths.csv")
        & frame["model_basis"].eq("in_house_model")
        & frame["line"].eq("Model path")
        & frame["value_numeric"].notna()
    ].copy()
    fed_rates = frame[
        frame["source_file"].eq("fed_rate_paths.csv")
        & frame["value_numeric"].notna()
        & frame["FY"].notna()
    ].copy()
    ped_bridge = frame[
        frame["source_file"].eq("ped_bridge_inputs.csv")
        & frame["value_numeric"].notna()
        & frame["FY"].notna()
        & frame["time_grain"].eq("june_year")
    ].copy()
    crown_top_up = frame[
        frame["series_id"].eq("crown_top_up")
        & frame["value_numeric"].notna()
        & frame["FY"].notna()
    ].copy()
    required_official = {
        "gross_lpg_revenue",
        "gross_cng_revenue",
        "fed_refunds",
        "total_ruc_net_revenue",
        "light_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "gross_ped_revenue",
        "net_mvr_revenue",
        "tuc_net_revenue",
        "gross_fed_revenue",
        "net_fed_revenue",
        "total_nltf_net_revenue",
    }
    required_replacements = {
        "ped_volume",
        "light_ruc_net_km",
        "light_ruc_net_revenue",
        "heavy_ruc_net_km",
        "heavy_ruc_net_revenue",
    }
    required_ped_bridge = {
        "population_count",
        "ped_total_vkt",
        "ped_litres_per_100km",
    }
    official_fys = _fys_with_series(official, required_official)
    replacement_fys = _fys_with_series(in_house, required_replacements)
    ped_bridge_fys = _fys_with_series(ped_bridge, required_ped_bridge)
    if fed_rates.empty:
        fed_rate_lookup: dict[tuple[str, int], float] = {}
    else:
        fed_rate_lookup = {
            (str(path), int(fy)): float(rate)
            for (path, fy), rate in fed_rates.groupby(["scenario_name", "FY"], dropna=True)["value_numeric"].mean().items()
            if str(path).strip()
        }
    fed_paths = sorted({path for path, _fy in fed_rate_lookup}) or ["Selected rate"]
    fed_rate_fys = {fy for _path, fy in fed_rate_lookup}
    common_fys = sorted(official_fys & replacement_fys & fed_rate_fys & ped_bridge_fys)
    if crown_top_up.empty:
        top_up_lookup: dict[int, float] = {}
    else:
        crown_top_up = crown_top_up.copy()
        crown_unit = crown_top_up["unit"].astype(str).str.lower()
        dollar_not_million = crown_unit.str.contains(r"\$", regex=True, na=False) & ~crown_unit.str.contains(r"\$m", regex=True, na=False)
        crown_top_up["annual_value_m"] = crown_top_up["value_numeric"].where(~dollar_not_million, crown_top_up["value_numeric"] / 1_000_000.0)
        top_up_lookup = crown_top_up.groupby("FY")["annual_value_m"].sum().to_dict()
    rows: list[dict[str, Any]] = []
    for fy in common_fys:
        off = _value_lookup(official[official["FY"].eq(fy)])
        rep = _value_lookup(in_house[in_house["FY"].eq(fy)])
        bridge = _value_lookup(ped_bridge[ped_bridge["FY"].eq(fy)])
        population_count = bridge["population_count"]
        ped_total_vkt = bridge["ped_total_vkt"]
        ped_litres_per_100km = bridge["ped_litres_per_100km"]
        ped_volume = rep["ped_volume"]
        light_km = rep["light_ruc_net_km"]
        heavy_km = rep["heavy_ruc_net_km"]
        light_rate = rep["light_ruc_net_revenue"] * 1000.0 / light_km
        heavy_rate = rep["heavy_ruc_net_revenue"] * 1000.0 / heavy_km
        light_revenue = light_km / 1000.0 * light_rate
        heavy_revenue = heavy_km / 1000.0 * heavy_rate
        official_total_ruc = off["total_ruc_net_revenue"]
        official_light = off["light_ruc_net_revenue"]
        official_heavy = off["heavy_ruc_net_revenue"]
        ruc_fixed_residual = official_total_ruc - official_light - official_heavy

        for fed_path in fed_paths:
            ped_rate = fed_rate_lookup.get((fed_path, fy))
            if ped_rate is None:
                continue
            ped_revenue = ped_total_vkt * ped_litres_per_100km / 100.0 * ped_rate
            gross_fed = ped_revenue + off["gross_lpg_revenue"] + off["gross_cng_revenue"]
            net_fed = gross_fed - off["fed_refunds"]
            total_ruc = light_revenue + heavy_revenue + ruc_fixed_residual
            total_fed_ruc = net_fed + total_ruc
            total_nltf = total_fed_ruc + off["net_mvr_revenue"] + off["tuc_net_revenue"]
            top_up = top_up_lookup.get(fy, pd.NA)

            rows.extend(
                [
                    _hybrid_row(fy, "ped_volume", ped_volume, "bridge_input", "in_house_model", "annual_model_paths.csv", fed_path=fed_path, unit="million L"),
                    _hybrid_row(fy, "population_count", population_count, "bridge_input", "ped_bridge", "ped_bridge_inputs.csv", fed_path=fed_path, unit="persons"),
                    _hybrid_row(fy, "ped_total_vkt", ped_total_vkt, "bridge_input", "ped_bridge", "ped_bridge_inputs.csv", fed_path=fed_path, unit="million km", formula="PED VKT per capita * population / 1,000,000"),
                    _hybrid_row(fy, "ped_litres_per_100km", ped_litres_per_100km, "bridge_input", "ped_bridge", "ped_bridge_inputs.csv", fed_path=fed_path, unit="L/100km", formula="source-backed PED litres / PED total VKT * 100"),
                    _hybrid_row(fy, "ped_fed_rate_path", ped_rate, "bridge_input", fed_path, "fed_rate_paths.csv", fed_path=fed_path, unit="NZD/L"),
                    _hybrid_row(fy, "light_ruc_net_km", light_km, "bridge_input", "in_house_model", "annual_model_paths.csv", fed_path=fed_path, unit="million km"),
                    _hybrid_row(fy, "light_ruc_effective_rate", light_rate, "bridge_input", "source_derived_effective_rate", "annual_model_paths.csv", fed_path=fed_path, unit="NZD/1,000 km", formula="source Light RUC revenue / source Light RUC net km * 1,000"),
                    _hybrid_row(fy, "heavy_ruc_net_km", heavy_km, "bridge_input", "in_house_model", "annual_model_paths.csv", fed_path=fed_path, unit="million km"),
                    _hybrid_row(fy, "heavy_ruc_effective_rate", heavy_rate, "bridge_input", "source_derived_effective_rate", "annual_model_paths.csv", fed_path=fed_path, unit="NZD/1,000 km", formula="source Heavy RUC revenue / source Heavy RUC net km * 1,000"),
                    _hybrid_row(
                        fy,
                        "gross_ped_revenue",
                        ped_revenue,
                        "replacement_line",
                        "ped_bridge + fed_rate_path",
                        "annual_model_paths.csv; fed_rate_paths.csv; ped_bridge_inputs.csv",
                        fed_path=fed_path,
                        formula="PED VKT per capita * population -> total VKT; source-backed litres intensity -> litres; litres * annual-average FED rate path",
                        replacement_only=True,
                        official_value=off["gross_ped_revenue"],
                    ),
                    _hybrid_row(fy, "light_ruc_net_revenue", light_revenue, "replacement_line", "in_house_model", "annual_model_paths.csv", fed_path=fed_path, formula="Light RUC net km / 1,000 * source-derived nominal effective rate", replacement_only=True, official_value=off["light_ruc_net_revenue"]),
                    _hybrid_row(fy, "heavy_ruc_net_revenue", heavy_revenue, "replacement_line", "in_house_model", "annual_model_paths.csv", fed_path=fed_path, formula="Heavy RUC net km / 1,000 * source-derived nominal effective rate", replacement_only=True, official_value=off["heavy_ruc_net_revenue"]),
                    _hybrid_row(fy, "gross_lpg_revenue", off["gross_lpg_revenue"], "fixed_mot_component", "official_befu25_annual", "official_befu25_annual.csv", fed_path=fed_path),
                    _hybrid_row(fy, "gross_cng_revenue", off["gross_cng_revenue"], "fixed_mot_component", "official_befu25_annual", "official_befu25_annual.csv", fed_path=fed_path),
                    _hybrid_row(fy, "fed_refunds", off["fed_refunds"], "fixed_mot_deduction", "official_befu25_annual", "official_befu25_annual.csv", fed_path=fed_path),
                    _hybrid_row(
                        fy,
                        "ruc_fixed_residual_net_revenue",
                        ruc_fixed_residual,
                        "fixed_mot_component",
                        "official_befu25_annual",
                        "official_befu25_annual.csv",
                        fed_path=fed_path,
                        formula="official_total_ruc_net_revenue - official_light_ruc_net_revenue - official_heavy_ruc_net_revenue",
                    ),
                    _hybrid_row(fy, "net_mvr_revenue", off["net_mvr_revenue"], "fixed_mot_component", "official_befu25_annual", "official_befu25_annual.csv", fed_path=fed_path),
                    _hybrid_row(fy, "tuc_net_revenue", off["tuc_net_revenue"], "fixed_mot_component", "official_befu25_annual", "official_befu25_annual.csv", fed_path=fed_path),
                    _hybrid_row(fy, "crown_top_up", top_up, "optional_overlay", "quarterly_actuals_annual_sum", "quarterly_actuals.csv", fed_path=fed_path, formula="sum quarterly Crown top-up rows by June year", unit="$m nominal ex GST", availability_status="available" if pd.notna(top_up) else "missing"),
                    _hybrid_row(fy, "gross_fed_revenue", gross_fed, "calculated_rollup", "hybrid_formula", "hybrid_formula", fed_path=fed_path, formula="gross_ped_revenue + MOT gross_lpg_revenue + MOT gross_cng_revenue", official_value=off["gross_fed_revenue"]),
                    _hybrid_row(fy, "net_fed_revenue", net_fed, "calculated_rollup", "hybrid_formula", "hybrid_formula", fed_path=fed_path, formula="gross_fed_revenue - MOT fed_refunds", official_value=off["net_fed_revenue"]),
                    _hybrid_row(fy, "total_ruc_net_revenue", total_ruc, "calculated_rollup", "hybrid_formula", "hybrid_formula", fed_path=fed_path, formula="light_ruc_net_revenue + heavy_ruc_net_revenue + MOT fixed RUC residual", official_value=off["total_ruc_net_revenue"]),
                    _hybrid_row(fy, "total_fed_ruc_net_revenue", total_fed_ruc, "calculated_rollup", "hybrid_formula", "hybrid_formula", fed_path=fed_path, formula="net_fed_revenue + total_ruc_net_revenue"),
                    _hybrid_row(fy, "total_nltf_net_revenue", total_nltf, "calculated_rollup", "hybrid_formula", "hybrid_formula", fed_path=fed_path, formula="net_fed_revenue + total_ruc_net_revenue + MOT net_mvr_revenue + MOT tuc_net_revenue", official_value=off["total_nltf_net_revenue"]),
                ]
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    out = pd.DataFrame(rows, columns=columns)
    out["residual_vs_official"] = pd.to_numeric(out["residual_vs_official"], errors="coerce")
    return out.sort_values(["FY", "row_role", "series_id"], kind="stable").reset_index(drop=True)


def _current_activity_annual_values(chart_rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "FY",
        "scenario_name",
        "scenario_role",
        "series_id",
        "value",
        "unit",
        "quarters_present",
        "actual_quarters",
        "forecast_quarters",
        "nowcast_flag",
    ]
    data = chart_rows.copy()
    data = data[
        data.get("time_grain", pd.Series(dtype=str)).astype(str).eq("quarterly")
        & data.get("metric_type", pd.Series(dtype=str)).astype(str).eq("activity")
        & data.get("period", pd.Series(dtype=str)).astype(str).str.match(r"^\d{4}Q[1-4]$", na=False)
    ].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data = data[data["value_numeric"].notna()].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    stream_to_series = {
        "PED": "ped_vkt_per_capita",
        "LIGHT_RUC": "light_ruc_net_km",
        "HEAVY_RUC": "heavy_ruc_net_km",
    }
    data["series_id"] = data.get("stream", pd.Series("", index=data.index)).astype(str).map(stream_to_series)
    data = data[data["series_id"].notna()].copy()
    future = data[data["row_type"].astype(str).eq("future_forecast")].copy()
    historical = data[data["row_type"].astype(str).eq("historical_actual")].copy()
    if future.empty:
        return pd.DataFrame(columns=columns)
    hist_lookup = {
        (str(row.series_id), str(row.period)): row
        for row in historical.itertuples()
    }
    rows: list[dict[str, Any]] = []
    for (scenario_name, series_id), group in future.groupby(["scenario_name", "series_id"], dropna=False):
        scenario_role = _first_text(group, "scenario_role")
        future_lookup = {str(row.period): row for row in group.itertuples()}
        fys = sorted(
            {
                _june_year_from_quarter(str(period))
                for period in list(future_lookup)
                if _june_year_from_quarter(str(period)) is not None
            }
        )
        for fy in fys:
            expected = _expected_june_year_quarters(int(fy))
            values = []
            actual_quarters = []
            forecast_quarters = []
            for quarter in expected:
                row = future_lookup.get(quarter)
                if row is not None:
                    values.append(float(row.value_numeric))
                    forecast_quarters.append(quarter)
                    continue
                hist_row = hist_lookup.get((str(series_id), quarter))
                if hist_row is not None:
                    values.append(float(hist_row.value_numeric))
                    actual_quarters.append(quarter)
            if len(values) != 4:
                continue
            if str(series_id) == "ped_vkt_per_capita":
                annual_value = sum(values) / 4.0
                unit = "km/person"
            else:
                annual_value = sum(values)
                unit_text = _first_text(group, "value_unit")
                unit = "million km"
                if str(unit_text).lower() == "net km" or abs(annual_value) > 10_000_000:
                    annual_value = annual_value / 1_000_000.0
            rows.append(
                {
                    "FY": int(fy),
                    "scenario_name": str(scenario_name),
                    "scenario_role": scenario_role,
                    "series_id": str(series_id),
                    "value": annual_value,
                    "unit": unit,
                    "quarters_present": "; ".join(expected),
                    "actual_quarters": "; ".join(actual_quarters),
                    "forecast_quarters": "; ".join(forecast_quarters),
                    "nowcast_flag": bool(actual_quarters and forecast_quarters),
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values(["FY", "scenario_name", "series_id"], kind="stable").reset_index(drop=True)


def _june_year_from_quarter(period: str) -> int | None:
    year, quarter = _parse_quarter(period)
    if year is None or quarter is None:
        return None
    return year if quarter in {1, 2} else year + 1


def _parse_quarter(period: str) -> tuple[int | None, int | None]:
    match = re.match(r"^(\d{4})Q([1-4])$", str(period or "").upper().strip())
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _official_annual_lookup(official_befu25_annual: pd.DataFrame) -> dict[int, dict[str, float]]:
    if official_befu25_annual is None or official_befu25_annual.empty:
        return {}
    data = official_befu25_annual.copy()
    data["FY_int"] = pd.to_numeric(data.get("FY"), errors="coerce").astype("Int64")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data["series_id"] = data.get("series", pd.Series("", index=data.index)).astype(str).map(SOURCE_SERIES_ALIASES)
    data = data[data["FY_int"].notna() & data["value_numeric"].notna() & data["series_id"].notna()].copy()
    output: dict[int, dict[str, float]] = {}
    for fy, group in data.groupby("FY_int", dropna=True):
        output[int(fy)] = group.groupby("series_id")["value_numeric"].first().to_dict()
    return output


def _ped_bridge_annual_lookup(ped_bridge_inputs: pd.DataFrame) -> dict[int, dict[str, float]]:
    if ped_bridge_inputs is None or ped_bridge_inputs.empty:
        return {}
    data = ped_bridge_inputs.copy()
    data = data[data.get("time_grain", pd.Series("", index=data.index)).astype(str).eq("june_year")].copy()
    data["FY_int"] = pd.to_numeric(data.get("FY"), errors="coerce").astype("Int64")
    data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
    data["series_id"] = data.get("series", pd.Series("", index=data.index)).astype(str).map(SOURCE_SERIES_ALIASES)
    data = data[data["FY_int"].notna() & data["value_numeric"].notna() & data["series_id"].notna()].copy()
    output: dict[int, dict[str, float]] = {}
    for fy, group in data.groupby("FY_int", dropna=True):
        output[int(fy)] = group.groupby("series_id")["value_numeric"].first().to_dict()
    return output


def _fed_rate_annual_lookup(fed_rate_paths: pd.DataFrame) -> dict[tuple[str, int], float]:
    if fed_rate_paths is None or fed_rate_paths.empty:
        return {}
    data = fed_rate_paths.copy()
    data["FY_int"] = pd.to_numeric(data.get("FY"), errors="coerce").astype("Int64")
    data["rate_numeric"] = pd.to_numeric(data.get("rate_nzd_per_litre"), errors="coerce")
    data = data[data["FY_int"].notna() & data["rate_numeric"].notna()].copy()
    output: dict[tuple[str, int], float] = {}
    for (fed_path, fy), rate in data.groupby(["fed_path", "FY_int"], dropna=True)["rate_numeric"].mean().items():
        output[(str(fed_path), int(fy))] = float(rate)
    return output


def _crown_top_up_lookup(canonical_long: pd.DataFrame) -> dict[int, float]:
    if canonical_long is None or canonical_long.empty:
        return {}
    rows = canonical_long[
        canonical_long.get("series_id", pd.Series("", index=canonical_long.index)).astype(str).eq("crown_top_up")
    ].copy()
    if rows.empty:
        return {}
    rows["FY_int"] = pd.to_numeric(rows.get("FY"), errors="coerce").astype("Int64")
    rows["value_numeric"] = pd.to_numeric(rows.get("value"), errors="coerce")
    rows = rows[rows["FY_int"].notna() & rows["value_numeric"].notna()].copy()
    if rows.empty:
        return {}
    return rows.groupby("FY_int")["value_numeric"].sum().to_dict()


def _current_annual_row(
    *,
    FY: int,
    period: str,
    fed_path: str,
    scenario_name: str,
    scenario_role: str,
    series_id: str,
    display_name: str,
    value: Any,
    unit: str,
    row_role: str,
    source_basis: str,
    source_file: str,
    source_cell: str,
    value_status: str,
    quarters_present: str,
    actual_quarters: str,
    forecast_quarters: str,
    nowcast_flag: bool,
    formula: str = "",
    replacement_only: bool = False,
    official_value: Any = pd.NA,
    availability_status: str = "available",
) -> dict[str, Any]:
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    numeric_official = pd.to_numeric(pd.Series([official_value]), errors="coerce").iloc[0]
    residual = float(numeric_value) - float(numeric_official) if pd.notna(numeric_value) and pd.notna(numeric_official) else pd.NA
    return {
        "FY": int(FY),
        "period": period,
        "fed_path": fed_path,
        "scenario_name": scenario_name,
        "scenario_role": scenario_role,
        "series_id": series_id,
        "display_name": display_name,
        "value": numeric_value,
        "unit": unit,
        "row_role": row_role,
        "source_basis": source_basis,
        "source_file": source_file,
        "source_status": "source_backed",
        "formula": formula,
        "replacement_only": bool(replacement_only),
        "official_value": numeric_official if pd.notna(numeric_official) else pd.NA,
        "residual_vs_official": residual,
        "availability_status": availability_status,
        "line": "Model path",
        "model_basis": "current_finalist_model",
        "forecast_path": "current_finalist_model",
        "path_status": "current_model_forecast",
        "value_status": value_status,
        "source_cell": source_cell,
        "quarters_present": quarters_present,
        "actual_quarters": actual_quarters,
        "forecast_quarters": forecast_quarters,
        "nowcast_flag": bool(nowcast_flag),
    }


def revenue_source_gap_register(
    *,
    manifest: dict[str, Any],
    front_end_config: dict[str, Any],
    canonical_long: pd.DataFrame,
) -> pd.DataFrame:
    selections = front_end_config.get("current_selections", {}) if isinstance(front_end_config, dict) else {}
    crown_top_up_selection = _selection_value(selections, "crown_top_up", "Exclude")
    has_crown_top_up_rows = bool(canonical_long["series_id"].eq("crown_top_up").any()) if "series_id" in canonical_long.columns else False
    has_release_values = bool(manifest.get("normalized_files", {}).get("release_values.csv"))
    normalized_files = manifest.get("normalized_files", {}) if isinstance(manifest, dict) else {}
    has_fed_path_values = any(
        str(filename) in normalized_files
        for filename in ["fed_path_values.csv", "fed_rate_paths.csv", "nominal_ped_fed_rate_paths.csv"]
    )
    has_quarterly_values = bool(canonical_long["time_grain"].astype(str).str.lower().eq("quarterly").any()) if "time_grain" in canonical_long.columns else False
    has_ped_total_vkt = bool(canonical_long["series_id"].eq("ped_total_vkt").any()) if "series_id" in canonical_long.columns else False
    rows = [
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
            "user_visible_message": (
                "PED total VKT bridge rows are repo-vendored in ped_bridge_inputs.csv; PED revenue is replayed from "
                "VKT per capita, population, source-backed litres intensity and FED rate path."
                if has_ped_total_vkt
                else "PED total VKT bridge rows are absent; PED revenue is recomputed from source-backed PED volume "
                "and FED rate paths, while the population-to-total-VKT replay remains a governed gap."
            ),
        },
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "gap_id",
            "required_for",
            "availability_status",
            "current_selection",
            "runtime_treatment",
            "user_visible_message",
        ],
    )


def revenue_path_trace_status(
    *,
    canonical_long: pd.DataFrame,
    gap_register: pd.DataFrame,
    current_forecast_annual: pd.DataFrame | None = None,
) -> pd.DataFrame:
    release_gap = _gap_status(gap_register, "release_value_table_missing")
    has_actual = _has_trace_rows(canonical_long, line_values={"Actual", "Actual / benchmark"})
    has_partial_actual = False
    if has_actual and "FY" in canonical_long.columns:
        actual_rows = canonical_long[canonical_long["line"].astype(str).isin(["Actual", "Actual / benchmark"])].copy()
        has_partial_actual = bool(pd.to_numeric(actual_rows.get("FY"), errors="coerce").eq(2026).any())
    has_selected_workbook = _has_trace_rows(canonical_long, model_basis="selected_dashboard_basis", line_values={"Model path"})
    has_current_model = bool(isinstance(current_forecast_annual, pd.DataFrame) and not current_forecast_annual.empty)
    has_legacy_in_house = _has_trace_rows(canonical_long, model_basis="in_house_model", line_values={"Model path"})
    has_schiff = _has_trace_rows(canonical_long, model_basis="aaron_schiff_model", line_values={"Model path"})
    release_available = release_gap.get("availability_status") == "available"
    release_selection = str(release_gap.get("current_selection") or "")
    rows = [
        _trace_status_row(
            "actual_benchmark",
            "Complete annual actuals",
            has_actual,
            "annual actual rows after completeness audit",
            "",
            "official actual or benchmark",
            "Only complete annual actual years are connected as the grey actual line.",
        ),
        _trace_status_row(
            "actual_to_date_marker",
            "Actual to date marker",
            has_partial_actual,
            "partial current-FY annual actual row",
            "",
            "FY2026 actual-to-date",
            "Partial current-FY actuals are plotted as distinct markers and are not joined to the complete actual line.",
        ),
        _trace_status_row(
            "selected_workbook_basis",
            "Legacy workbook selected basis",
            has_selected_workbook,
            "annual model path rows",
            "",
            "source workbook current selection",
            "Workbook-selected annual model path is retained as a legacy benchmark.",
        ),
        _trace_status_row(
            "selected_mot_befu_release",
            "Selected MOT/BEFU release path",
            release_available,
            "release-value table",
            "" if release_available else "release_value_table_missing",
            release_selection,
            (
                "Selected MOT/BEFU release path is plotted from repo-local release_values.csv rows."
                if release_available
                else "Selected MOT/BEFU release path requires release-value rows; registry-only release metadata is not plotted as values."
            ),
        ),
        _trace_status_row(
            "rolling_befu_1y",
            "Rolling BEFU 1Y",
            release_available,
            "release-value table",
            "" if release_available else "release_value_table_missing",
            release_selection,
            (
                "Rolling BEFU 1Y is plotted from true one-year-ahead rows in release_values.csv."
                if release_available
                else "Rolling BEFU 1Y requires historical release-value rows; it is not fabricated from model paths."
            ),
        ),
        _trace_status_row(
            "aaron_schiff_model",
            "Legacy workbook Schiff model",
            has_schiff,
            "annual model path rows",
            "",
            "Aaron Schiff model",
            "Aaron Schiff annual model path is retained as a legacy benchmark.",
        ),
        _trace_status_row(
            "in_house_model",
            "In-house prediction / forecast",
            has_current_model,
            "promoted current finalist quarterly outputs annualized to June years",
            "" if has_current_model else "current_revenue_outlook_missing",
            "current finalist model",
            "Primary in-house trace is plotted from data/current_revenue_outlook current finalist outputs, not annual_model_paths.csv.",
        ),
        _trace_status_row(
            "legacy_in_house_model",
            "Legacy workbook model",
            has_legacy_in_house,
            "annual model path rows",
            "",
            "legacy workbook in-house model",
            "Workbook in-house annual model path is retained only as an optional legacy benchmark.",
        ),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "trace_id",
            "trace_label",
            "availability_status",
            "plotted",
            "data_scope",
            "blocking_gap_id",
            "current_selection",
            "user_visible_message",
        ],
    )


def revenue_source_pack_intake_status(
    *,
    pack_dir: Path,
    manifest: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    source_pack_root = Path("data") / "revenue_model_source_pack" / str(manifest.get("source_pack_version", "2026_05_19"))

    raw_hash = str(manifest.get("raw_workbook", {}).get("sha256", ""))
    rows.append(
        _intake_status_row(
            artifact_name="raw_workbook_lineage",
            artifact_role="lineage_only_not_runtime_loaded",
            repo_relative_path="",
            status="verified_sha256_in_manifest" if raw_hash else "missing_hash",
            required_for_runtime=False,
            required_for_replay=True,
            sha256=raw_hash,
            size_bytes=None,
            row_count=None,
            notes="Raw workbook remains outside Git; Streamlit uses normalized repo-local files only.",
        )
    )

    distilled_hash = str(manifest.get("distilled_workbook", {}).get("sha256", ""))
    rows.append(
        _intake_status_row(
            artifact_name="distilled_workbook_lineage",
            artifact_role="normalized_contract_source",
            repo_relative_path="",
            status="verified_sha256_in_manifest" if distilled_hash else "missing_hash",
            required_for_runtime=False,
            required_for_replay=True,
            sha256=distilled_hash,
            size_bytes=None,
            row_count=None,
            notes="Distilled workbook is lineage only after normalized files are vendored.",
        )
    )

    file_metadata: dict[str, dict[str, Any]] = {}
    for bucket in ("normalized_files", "config_files"):
        payload = manifest.get(bucket, {})
        if isinstance(payload, dict):
            for filename, meta in payload.items():
                file_metadata[str(filename)] = meta if isinstance(meta, dict) else {}

    manifest_path = pack_dir / "manifest.json"
    rows.append(
        _intake_status_row(
            artifact_name="manifest.json",
            artifact_role="source_pack_manifest",
            repo_relative_path=(source_pack_root / "manifest.json").as_posix(),
            status="repo_local_hash_verified" if manifest_path.exists() else "missing_or_hash_mismatch",
            required_for_runtime=True,
            required_for_replay=True,
            sha256=_sha256(manifest_path) if manifest_path.exists() else "",
            size_bytes=manifest_path.stat().st_size if manifest_path.exists() else None,
            row_count=None,
            notes="Source-pack manifest for repo-local normalized files.",
        )
    )

    for filename in sorted(file_metadata):
        path = pack_dir / filename
        meta = file_metadata[filename]
        repo_path = (source_pack_root / filename).as_posix()
        exists = path.exists()
        size = path.stat().st_size if exists else None
        actual_hash = _sha256(path) if exists else ""
        expected_hash = str(meta.get("sha256", ""))
        rows.append(
            _intake_status_row(
                artifact_name=filename,
                artifact_role=str(meta.get("source_sheet", "config_or_document")),
                repo_relative_path=repo_path,
                status="repo_local_hash_verified" if exists and actual_hash == expected_hash else "missing_or_hash_mismatch",
                required_for_runtime=filename in REQUIRED_SOURCE_PACK_FILES or filename in OPTIONAL_SOURCE_PACK_FILES,
                required_for_replay=True,
                sha256=actual_hash or expected_hash,
                size_bytes=size,
                row_count=_nullable_int(meta.get("row_count")),
                notes="Normalized source-pack contract file.",
            )
        )

    declared = set(file_metadata)
    large_artifact_roles = {
        "release_values.csv": "selected MOT/BEFU and rolling BEFU 1Y release-value paths",
        "forecast_archive.csv": "full workbook forecast archive replay",
        "formula_lineage.csv": "full formula lineage replay",
        "quarterly_actuals.csv": "source-pack quarterly Revenue Outlook",
        "fed_rate_paths.csv": "FED path scenario rate values",
        "mot_error_bands.csv": "MOT archived-error uncertainty bands",
        "official_befu25_annual.csv": "Official BEFU25 fixed annual components",
    }
    for filename, role in large_artifact_roles.items():
        if filename in declared:
            continue
        rows.append(
            _intake_status_row(
                artifact_name=filename,
                artifact_role=role,
                repo_relative_path=(source_pack_root / filename).as_posix(),
                status="not_vendored",
                required_for_runtime=False,
                required_for_replay=True,
                sha256="",
                size_bytes=None,
                row_count=None,
                notes="Not present in the repo-local normalized pack; dependent dashboard traces remain governed gaps.",
            )
        )

    return pd.DataFrame(
        rows,
        columns=[
            "artifact_name",
            "artifact_role",
            "repo_relative_path",
            "status",
            "required_for_runtime",
            "required_for_replay",
            "size_bytes",
            "row_count",
            "sha256",
            "notes",
        ],
    )


def revenue_remaining_decisions_handoff(
    *,
    unresolved_decisions: pd.DataFrame,
    gap_register: pd.DataFrame,
) -> pd.DataFrame:
    gap_status = {
        str(record.get("gap_id", "")): str(record.get("availability_status", ""))
        for record in gap_register.to_dict("records")
        if str(record.get("gap_id", "")).strip()
    }
    rows: list[dict[str, Any]] = []
    for record in unresolved_decisions.to_dict("records"):
        item = str(record.get("Item", "")).strip()
        link = _decision_handoff_link(item, gap_status)
        linked_gap_ids = link["linked_gap_ids"]
        linked_statuses = [gap_status.get(gap_id, "not_applicable") for gap_id in linked_gap_ids]
        if linked_statuses and any(status == "missing" for status in linked_statuses):
            availability_status = "open_gap"
        elif linked_statuses:
            availability_status = "source_backed"
        else:
            availability_status = link["availability_status"]
        rows.append(
            {
                "decision_id": _decision_id(item),
                "priority": str(record.get("Priority", "")).strip(),
                "decision_item": item,
                "availability_status": availability_status,
                "linked_gap_ids": "; ".join(linked_gap_ids),
                "linked_artifacts": link["linked_artifacts"],
                "runtime_status": link["runtime_status"],
                "dashboard_treatment": link["dashboard_treatment"],
                "why_needed": str(record.get("Why needed", "")).strip(),
                "recommended_resolution": str(record.get("Recommended resolution", "")).strip(),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "decision_id",
            "priority",
            "decision_item",
            "availability_status",
            "linked_gap_ids",
            "linked_artifacts",
            "runtime_status",
            "dashboard_treatment",
            "why_needed",
            "recommended_resolution",
        ],
    )


def revenue_series_role_audit(
    *,
    series_master: pd.DataFrame,
    canonical_long: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    canonical_groups = {
        str(series_id): group.copy()
        for series_id, group in canonical_long.groupby("series_id", dropna=False)
        if str(series_id).strip()
    }
    registered_ids: set[str] = set()
    for record in series_master.to_dict("records"):
        series_id = str(record.get("Series ID", "")).strip()
        if not series_id:
            continue
        registered_ids.add(series_id)
        role = str(record.get("Forecast role", "")).strip()
        group = canonical_groups.get(series_id, pd.DataFrame())
        rows.append(
            _series_role_audit_row(
                series_id=series_id,
                display_name=str(record.get("Display name", "")).strip(),
                parent_series_id="" if pd.isna(record.get("Parent series ID")) else str(record.get("Parent series ID", "")).strip(),
                unit=str(record.get("Unit", "")).strip(),
                aggregation_sign=_as_sign(record.get("Sign")),
                forecast_role=role,
                dashboard_visible=bool(record.get("Dashboard visible", False)),
                notes=str(record.get("Notes", "")).strip(),
                canonical_rows=group,
            )
        )

    for series_id, group in canonical_groups.items():
        if series_id in registered_ids:
            continue
        display = _first_text(group, "display_name") or _first_text(group, "source_series_label") or series_id
        is_runtime_bridge = series_id in RUNTIME_DERIVED_BRIDGE_SERIES
        rows.append(
            _series_role_audit_row(
                series_id=series_id,
                display_name=display,
                parent_series_id=_first_text(group, "parent_series_id"),
                unit=_first_text(group, "unit"),
                aggregation_sign=_first_int(group, "aggregation_sign", default=1),
                forecast_role="derived_bridge" if is_runtime_bridge else "unregistered_source_line",
                dashboard_visible=False,
                notes=(
                    "Runtime-derived PED bridge input bound by source-pack alias; retained outside the workbook series master."
                    if is_runtime_bridge
                    else "Preserved source line not registered in series_master.csv; retained as a governance gap."
                ),
                canonical_rows=group,
            )
        )

    return pd.DataFrame(
        rows,
        columns=[
            "series_id",
            "display_name",
            "role_category",
            "forecast_role",
            "runtime_treatment",
            "parent_series_id",
            "unit",
            "aggregation_sign",
            "dashboard_visible",
            "canonical_row_count",
            "source_statuses",
            "bridge_statuses",
            "revenue_bases",
            "notes",
        ],
    ).sort_values(["role_category", "series_id"], kind="stable").reset_index(drop=True)


def series_trace_contract_frame(
    *,
    series_master: pd.DataFrame,
    front_end_config: dict[str, Any],
    canonical_long: pd.DataFrame,
    current_forecast_annual: pd.DataFrame,
    data_vintage_manifest: dict[str, Any],
) -> pd.DataFrame:
    registry = _registry(series_master)
    controls = front_end_config.get("controls", []) if isinstance(front_end_config, dict) else []
    series_options: list[str] = []
    for control in controls:
        if isinstance(control, dict) and control.get("control_id") == "series":
            series_options = [str(option) for option in control.get("options", []) if str(option).strip()]
            break
    if not series_options:
        series_options = sorted(canonical_long.get("display_name", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    rows: list[dict[str, Any]] = []
    current_series = set(current_forecast_annual.get("series_id", pd.Series(dtype=str)).dropna().astype(str))
    for option in series_options:
        series_id = _series_id_for_label(option, registry, canonical_long)
        group = canonical_long[canonical_long.get("series_id", pd.Series(dtype=str)).astype(str).eq(series_id)].copy()
        master = series_master[series_master.get("Series ID", pd.Series(dtype=str)).astype(str).eq(series_id)].copy()
        forecast_role = _first_text(master, "Forecast role") or _first_text(group, "forecast_role")
        unit = _first_text(master, "Unit") or _first_text(group, "unit")
        metric_type = _series_metric_type(forecast_role, unit)
        valid_bases = _valid_bases_for_series(series_id, metric_type)
        applicable_controls = _applicable_controls_for_series(series_id, metric_type)
        primary_source = (
            "data/current_revenue_outlook/revenue_chart_rows.csv + governed bridge rows"
            if series_id in current_series
            else _primary_source_for_non_current_series(series_id, group)
        )
        legacy_available = bool(
            not group.empty
            and group.get("source_file", pd.Series("", index=group.index)).astype(str).eq("annual_model_paths.csv").any()
            and group.get("line", pd.Series("", index=group.index)).astype(str).eq("Model path").any()
        )
        rows.append(
            {
                "series_option": option,
                "canonical_id": series_id,
                "display_name": _first_text(master, "Display name") or _first_text(group, "display_name") or option,
                "metric_type": metric_type,
                "unit": unit,
                "valid_bases": "; ".join(valid_bases),
                "valid_controls": "; ".join(applicable_controls),
                "actual_source": "quarterly_actuals.csv actual-status rows; annual_model_paths.csv actual line only after completeness audit",
                "primary_forecast_source": primary_source,
                "optional_legacy_source": "annual_model_paths.csv workbook model paths" if legacy_available else "",
                "bridge": _bridge_contract_for_series(series_id, forecast_role),
                "last_complete_actual_fy": data_vintage_manifest.get("last_complete_actual_fy", REVENUE_LAST_COMPLETE_ACTUAL_FY),
                "first_forecast_fy": data_vintage_manifest.get("first_model_forecast_fy", f"FY{REVENUE_PARTIAL_ACTUAL_FY}"),
                "first_forecast_quarter": data_vintage_manifest.get("first_model_forecast_quarter", REVENUE_FIRST_FORECAST_QUARTER),
                "model_training_cutoff": data_vintage_manifest.get("model_training_cutoff", REVENUE_MODEL_TRAINING_CUTOFF),
                "revenue_actual_cutoff": data_vintage_manifest.get("revenue_source_actual_cutoff", REVENUE_SOURCE_ACTUAL_CUTOFF),
                "horizon": _series_horizon_label(series_id, current_forecast_annual, group),
                "availability_status": "current_model_available" if series_id in current_series else "source_pack_or_legacy_only",
                "interpretation": _series_contract_interpretation(series_id, metric_type),
            }
        )
    return pd.DataFrame(rows).sort_values(["series_option"], kind="stable").reset_index(drop=True)


def series_junction_audit_frame(
    *,
    series_trace_contract: pd.DataFrame,
    canonical_long: pd.DataFrame,
    current_forecast_annual: pd.DataFrame,
    annual_completeness: pd.DataFrame,
    data_vintage_manifest: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    audit_lookup = {
        int(row.FY): row
        for row in annual_completeness.itertuples()
        if pd.notna(getattr(row, "FY", pd.NA))
    }
    series_ids = series_trace_contract["canonical_id"].dropna().astype(str).drop_duplicates().tolist()
    for series_id in series_ids:
        actual_values = _junction_actual_values(canonical_long, series_id)
        current_values = _junction_current_values(current_forecast_annual, series_id)
        legacy_values = _junction_legacy_values(canonical_long, series_id)
        ratio = _last_actual_first_forecast_ratio(actual_values, current_values)
        tolerance = _source_derived_ratio_tolerance(actual_values)
        for fy in range(2024, 2028):
            audit_row = audit_lookup.get(fy)
            rows.append(
                _junction_row(
                    series_id=series_id,
                    path="actual_or_actual_to_date",
                    fy=fy,
                    payload=actual_values.get(fy, {}),
                    audit_row=audit_row,
                    data_vintage_manifest=data_vintage_manifest,
                    ratio=ratio,
                    tolerance=tolerance,
                )
            )
            rows.append(
                _junction_row(
                    series_id=series_id,
                    path="current_finalist_model",
                    fy=fy,
                    payload=current_values.get(fy, {}),
                    audit_row=audit_row,
                    data_vintage_manifest=data_vintage_manifest,
                    ratio=ratio,
                    tolerance=tolerance,
                )
            )
            rows.append(
                _junction_row(
                    series_id=series_id,
                    path="legacy_workbook_in_house_model",
                    fy=fy,
                    payload=legacy_values.get(fy, {}),
                    audit_row=audit_row,
                    data_vintage_manifest=data_vintage_manifest,
                    ratio=ratio,
                    tolerance=tolerance,
                )
            )
    return pd.DataFrame(
        rows,
        columns=[
            "series_id",
            "path",
            "FY",
            "value",
            "unit",
            "source_file",
            "source_status",
            "value_status",
            "quarters_present",
            "actual_quarters",
            "forecast_quarters",
            "model_training_cutoff",
            "revenue_actual_cutoff",
            "last_complete_actual_fy",
            "first_forecast_quarter",
            "last_actual_to_first_forecast_ratio",
            "source_derived_tolerance",
            "discontinuity_flag",
            "nowcast_components",
            "notes",
        ],
    ).sort_values(["series_id", "path", "FY"], kind="stable").reset_index(drop=True)


def control_options(pack: RevenueSourcePack | None, control_id: str, default: list[str]) -> list[str]:
    if pack is None:
        return default
    if control_id == "revenue_basis":
        return _derived_revenue_basis_options(pack.canonical_long, default)
    controls = pack.front_end_config.get("controls", []) if isinstance(pack.front_end_config, dict) else []
    for control in controls:
        if isinstance(control, dict) and control.get("control_id") == control_id:
            options = [str(item) for item in control.get("options", []) if str(item)]
            return options or default
    selection = pack.front_end_config.get("current_selections", {}).get(control_id, {}) if isinstance(pack.front_end_config, dict) else {}
    value = selection.get("current_value") if isinstance(selection, dict) else None
    return [str(value)] if value else default


def current_selection(pack: RevenueSourcePack | None, control_id: str, default: str) -> str:
    if pack is None:
        return default
    selections = pack.front_end_config.get("current_selections", {}) if isinstance(pack.front_end_config, dict) else {}
    if control_id == "revenue_basis":
        revenue_path = _selection_value(selections, "revenue_path", "")
        return REVENUE_PATH_TO_BASIS.get(revenue_path.strip().lower(), default)
    return _selection_value(selections, control_id, default)


def _series_id_for_label(label: str, registry: dict[str, dict[str, Any]], canonical_long: pd.DataFrame) -> str:
    text = str(label or "").strip()
    direct = registry.get(text)
    if direct:
        return str(direct.get("series_id", text))
    alias = SOURCE_SERIES_ALIASES.get(text)
    if alias:
        return alias
    if isinstance(canonical_long, pd.DataFrame) and not canonical_long.empty:
        matches = canonical_long[canonical_long.get("display_name", pd.Series("", index=canonical_long.index)).astype(str).eq(text)]
        if matches.empty:
            matches = canonical_long[canonical_long.get("source_series_label", pd.Series("", index=canonical_long.index)).astype(str).eq(text)]
        if not matches.empty:
            return str(matches.iloc[0].get("series_id"))
    return _slug(text)


def _series_metric_type(forecast_role: str, unit: str) -> str:
    text = f"{forecast_role} {unit}".lower()
    if "activity" in text or "km/person" in text or "million km" in text or text.strip().endswith(" km") or "litres" in text:
        return "activity"
    return "revenue"


def _valid_bases_for_series(series_id: str, metric_type: str) -> list[str]:
    if metric_type == "activity":
        return ["not_applicable"]
    if series_id == "gross_ped_revenue":
        return ["Gross", "Nominal ex GST"]
    if series_id in {"light_ruc_net_revenue", "heavy_ruc_net_revenue", "total_ruc_net_revenue", "net_fed_revenue", "total_fed_ruc_net_revenue", "total_nltf_net_revenue", "net_mvr_revenue", "tuc_net_revenue"}:
        return ["Net", "Nominal ex GST"]
    return ["Gross", "Net", "Nominal ex GST"]


def _applicable_controls_for_series(series_id: str, metric_type: str) -> list[str]:
    controls = ["series", "time_grain", "horizon"]
    if metric_type == "activity":
        return controls
    controls.extend(["revenue_basis"])
    if series_id in {"gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue", "total_fed_ruc_net_revenue", "total_nltf_net_revenue"}:
        controls.append("fed_path")
    if series_id in {"net_fed_revenue", "total_nltf_net_revenue"}:
        controls.append("crown_top_up")
    return controls


def _primary_source_for_non_current_series(series_id: str, group: pd.DataFrame) -> str:
    if not isinstance(group, pd.DataFrame) or group.empty:
        return "not_available"
    source_files = set(group.get("source_file", pd.Series(dtype=str)).dropna().astype(str))
    if "official_befu25_annual.csv" in source_files:
        return "official_befu25_annual.csv selected-MOT fixed row"
    if "release_values.csv" in source_files:
        return "release_values.csv selected MOT/BEFU release path"
    if "quarterly_actuals.csv" in source_files:
        return "quarterly_actuals.csv actual-status rows"
    return "; ".join(sorted(source_files)) or "not_available"


def _bridge_contract_for_series(series_id: str, forecast_role: str) -> str:
    if series_id == "gross_ped_revenue":
        return "PED=current VKT/capita forecast * population -> total VKT * litres/100km * nominal PED rate"
    if series_id == "light_ruc_net_revenue":
        return "Light RUC=current net-km forecast/1,000 * governed effective Light rate"
    if series_id == "heavy_ruc_net_revenue":
        return "Heavy RUC=current net-km forecast/1,000 * governed class-mix Heavy rate"
    if series_id in CORE_ROLLUP_SERIES:
        return "Calculated from current replacement lines plus selected-MOT fixed rows and explicit residual reporting"
    if forecast_role == "econometric_model":
        return "Direct current finalist econometric forecast"
    if forecast_role in {"official_pass_through", "derived_scenario_split", "deduction", "optional_overlay"}:
        return "Selected-MOT/source-pack fixed row; not replaced by current econometric forecast"
    return forecast_role or "source-pack row"


def _series_horizon_label(series_id: str, current_forecast_annual: pd.DataFrame, group: pd.DataFrame) -> str:
    rows = current_forecast_annual[current_forecast_annual.get("series_id", pd.Series(dtype=str)).astype(str).eq(series_id)].copy()
    if rows.empty and isinstance(group, pd.DataFrame) and not group.empty:
        rows = group.copy()
    fy = pd.to_numeric(rows.get("FY"), errors="coerce") if not rows.empty else pd.Series(dtype=float)
    if fy.dropna().empty:
        return "unavailable"
    return f"FY{int(fy.min())}-FY{int(fy.max())}"


def _series_contract_interpretation(series_id: str, metric_type: str) -> str:
    if metric_type == "activity":
        return "Activity and volume rows are not revenue-basis, FED-path or Crown-top-up sensitive."
    if series_id == "gross_ped_revenue":
        return "PED revenue is gross/nominal ex GST only; Net is not a valid PED-only basis."
    if series_id in {"total_nltf_net_revenue", "net_fed_revenue"}:
        return "Total/net rollups expose only controls that affect their governed components."
    return "Revenue trace must state whether it is current finalist, selected MOT, or legacy workbook benchmark."


def _junction_actual_values(canonical_long: pd.DataFrame, series_id: str) -> dict[int, dict[str, Any]]:
    rows = canonical_long[
        canonical_long.get("series_id", pd.Series("", index=canonical_long.index)).astype(str).eq(series_id)
        & canonical_long.get("line", pd.Series("", index=canonical_long.index)).astype(str).isin(["Actual", "Actual / benchmark"])
    ].copy()
    rows["FY_int"] = pd.to_numeric(rows.get("FY"), errors="coerce").astype("Int64")
    rows["value_numeric"] = pd.to_numeric(rows.get("value"), errors="coerce")
    rows = rows[rows["FY_int"].notna() & rows["value_numeric"].notna()].copy()
    output: dict[int, dict[str, Any]] = {}
    for fy, group in rows.groupby("FY_int", dropna=True):
        if int(fy) > REVENUE_PARTIAL_ACTUAL_FY:
            continue
        selected = group[group.get("source_file", pd.Series("", index=group.index)).astype(str).eq("annual_model_paths.csv")]
        if selected.empty:
            selected = group
        row = selected.iloc[0]
        output[int(fy)] = {
            "value": row.get("value"),
            "unit": row.get("unit"),
            "source_file": row.get("source_file"),
            "source_status": row.get("source_status"),
            "value_status": row.get("value_status") or row.get("line"),
        }
    return output


def _junction_current_values(current_forecast_annual: pd.DataFrame, series_id: str) -> dict[int, dict[str, Any]]:
    rows = current_forecast_annual[
        current_forecast_annual.get("series_id", pd.Series(dtype=str)).astype(str).eq(series_id)
        & current_forecast_annual.get("scenario_name", pd.Series(dtype=str)).astype(str).eq("current_basecase")
        & current_forecast_annual.get("fed_path", pd.Series(dtype=str)).astype(str).eq("Current planned path")
    ].copy()
    rows["FY_int"] = pd.to_numeric(rows.get("FY"), errors="coerce").astype("Int64")
    output: dict[int, dict[str, Any]] = {}
    for fy, group in rows.groupby("FY_int", dropna=True):
        row = group.iloc[0]
        output[int(fy)] = row.to_dict()
    return output


def _junction_legacy_values(canonical_long: pd.DataFrame, series_id: str) -> dict[int, dict[str, Any]]:
    rows = canonical_long[
        canonical_long.get("series_id", pd.Series("", index=canonical_long.index)).astype(str).eq(series_id)
        & canonical_long.get("line", pd.Series("", index=canonical_long.index)).astype(str).eq("Model path")
        & canonical_long.get("model_basis", pd.Series("", index=canonical_long.index)).astype(str).eq("in_house_model")
    ].copy()
    rows["FY_int"] = pd.to_numeric(rows.get("FY"), errors="coerce").astype("Int64")
    rows["value_numeric"] = pd.to_numeric(rows.get("value"), errors="coerce")
    rows = rows[rows["FY_int"].notna() & rows["value_numeric"].notna()].copy()
    output: dict[int, dict[str, Any]] = {}
    for fy, group in rows.groupby("FY_int", dropna=True):
        row = group.iloc[0]
        output[int(fy)] = row.to_dict()
    return output


def _last_actual_first_forecast_ratio(actual_values: dict[int, dict[str, Any]], current_values: dict[int, dict[str, Any]]) -> Any:
    actual = actual_values.get(REVENUE_LAST_COMPLETE_ACTUAL_FY, {}).get("value")
    forecast = current_values.get(REVENUE_PARTIAL_ACTUAL_FY, {}).get("value")
    actual_num = pd.to_numeric(pd.Series([actual]), errors="coerce").iloc[0]
    forecast_num = pd.to_numeric(pd.Series([forecast]), errors="coerce").iloc[0]
    if pd.isna(actual_num) or pd.isna(forecast_num) or float(actual_num) == 0.0:
        return pd.NA
    return float(forecast_num) / float(actual_num)


def _source_derived_ratio_tolerance(actual_values: dict[int, dict[str, Any]]) -> float:
    current = pd.to_numeric(pd.Series([actual_values.get(REVENUE_LAST_COMPLETE_ACTUAL_FY, {}).get("value")]), errors="coerce").iloc[0]
    prior = pd.to_numeric(pd.Series([actual_values.get(REVENUE_LAST_COMPLETE_ACTUAL_FY - 1, {}).get("value")]), errors="coerce").iloc[0]
    if pd.isna(current) or pd.isna(prior) or float(prior) == 0.0:
        return 0.25
    observed_change = abs(float(current) / float(prior) - 1.0)
    return max(0.15, min(0.75, observed_change * 2.0))


def _junction_row(
    *,
    series_id: str,
    path: str,
    fy: int,
    payload: dict[str, Any],
    audit_row: Any,
    data_vintage_manifest: dict[str, Any],
    ratio: Any,
    tolerance: float,
) -> dict[str, Any]:
    value = payload.get("value", pd.NA)
    value_num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    completeness_status = str(getattr(audit_row, "completeness_status", "") if audit_row is not None else "")
    audit_actual_quarters = getattr(audit_row, "actual_quarters", "") if audit_row is not None else ""
    audit_forecast_quarters = getattr(audit_row, "forecast_quarters", "") if audit_row is not None else ""
    audit_quarters_present = getattr(audit_row, "quarters_present", "") if audit_row is not None else ""
    actual_quarters = str(payload.get("actual_quarters") or audit_actual_quarters or "")
    forecast_quarters = str(payload.get("forecast_quarters") or audit_forecast_quarters or "")
    quarters_present = str(payload.get("quarters_present") or audit_quarters_present or "")
    ratio_num = pd.to_numeric(pd.Series([ratio]), errors="coerce").iloc[0]
    discontinuity = bool(pd.notna(ratio_num) and abs(float(ratio_num) - 1.0) > tolerance) if path == "current_finalist_model" and fy == REVENUE_PARTIAL_ACTUAL_FY else False
    notes = ""
    if path == "actual_or_actual_to_date" and fy > REVENUE_LAST_COMPLETE_ACTUAL_FY:
        notes = "not connected as complete actual; FY2026 is partial actual-to-date only" if fy == REVENUE_PARTIAL_ACTUAL_FY else "forecast-only year; no actual value shown"
    elif path == "current_finalist_model" and fy == REVENUE_PARTIAL_ACTUAL_FY:
        notes = "actual-plus-forecast-to-go nowcast where source actual quarters and current forecast quarters both exist"
    return {
        "series_id": series_id,
        "path": path,
        "FY": fy,
        "value": value_num if pd.notna(value_num) else pd.NA,
        "unit": payload.get("unit", ""),
        "source_file": payload.get("source_file", ""),
        "source_status": payload.get("source_status", ""),
        "value_status": payload.get("value_status", completeness_status),
        "quarters_present": quarters_present,
        "actual_quarters": actual_quarters,
        "forecast_quarters": forecast_quarters,
        "model_training_cutoff": data_vintage_manifest.get("model_training_cutoff", REVENUE_MODEL_TRAINING_CUTOFF),
        "revenue_actual_cutoff": data_vintage_manifest.get("revenue_source_actual_cutoff", REVENUE_SOURCE_ACTUAL_CUTOFF),
        "last_complete_actual_fy": data_vintage_manifest.get("last_complete_actual_fy", REVENUE_LAST_COMPLETE_ACTUAL_FY),
        "first_forecast_quarter": data_vintage_manifest.get("first_model_forecast_quarter", REVENUE_FIRST_FORECAST_QUARTER),
        "last_actual_to_first_forecast_ratio": ratio,
        "source_derived_tolerance": tolerance,
        "discontinuity_flag": discontinuity,
        "nowcast_components": f"actual: {actual_quarters or 'none'}; forecast: {forecast_quarters or 'none'}",
        "notes": notes,
    }


def _derived_revenue_basis_options(canonical_long: pd.DataFrame, default: list[str]) -> list[str]:
    if canonical_long is None or canonical_long.empty or "revenue_basis" not in canonical_long.columns:
        return default
    values = canonical_long["revenue_basis"].dropna().astype(str).str.strip().unique().tolist()
    labels = [REVENUE_BASIS_LABELS[value] for value in values if value in REVENUE_BASIS_LABELS]
    preferred = ["Net", "Gross", "Admin", "Deductions", "Nominal ex GST"]
    ordered = [label for label in preferred if label in labels]
    return ordered or default


def _selection_value(selections: dict[str, Any], control_id: str, default: str = "") -> str:
    value = selections.get(control_id, {}).get("current_value") if isinstance(selections.get(control_id, {}), dict) else None
    return str(value) if value else default


def _gap_status(gap_register: pd.DataFrame, gap_id: str) -> dict[str, Any]:
    if gap_register.empty or "gap_id" not in gap_register.columns:
        return {}
    rows = gap_register[gap_register["gap_id"].eq(gap_id)]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _has_trace_rows(
    canonical_long: pd.DataFrame,
    *,
    model_basis: str | None = None,
    line_values: set[str] | None = None,
) -> bool:
    if canonical_long.empty:
        return False
    rows = canonical_long.copy()
    if model_basis is not None and "model_basis" in rows.columns:
        rows = rows[rows["model_basis"].astype(str).eq(model_basis)]
    if line_values is not None and "line" in rows.columns:
        rows = rows[rows["line"].astype(str).isin(line_values)]
    if "value" not in rows.columns:
        return False
    return pd.to_numeric(rows["value"], errors="coerce").notna().any()


def _trace_status_row(
    trace_id: str,
    trace_label: str,
    available: bool,
    data_scope: str,
    blocking_gap_id: str,
    current_selection: str,
    message: str,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "trace_label": trace_label,
        "availability_status": "available" if available else "missing",
        "plotted": bool(available),
        "data_scope": data_scope,
        "blocking_gap_id": blocking_gap_id,
        "current_selection": current_selection,
        "user_visible_message": message,
    }


def _expected_june_year_quarters(fy: int) -> list[str]:
    return [f"{fy - 1}Q3", f"{fy - 1}Q4", f"{fy}Q1", f"{fy}Q2"]


def _quarter_sort_key(value: Any) -> tuple[int, int]:
    text = str(value or "").upper().strip()
    match = re.match(r"^(\d{4})Q([1-4])$", text)
    if not match:
        return (9999, 9)
    return (int(match.group(1)), int(match.group(2)))


def _cell_sort_key(value: Any) -> tuple[int, int, str]:
    text = str(value or "").upper().strip()
    match = re.match(r"^([A-Z]+)(\d+)$", text)
    if not match:
        return (999999, 999999, text)
    column = 0
    for char in match.group(1):
        column = column * 26 + (ord(char) - ord("A") + 1)
    return (column, int(match.group(2)), text)


def _annual_model_total_row(frame: pd.DataFrame, fy: int, *, line: str) -> dict[str, Any] | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    rows = frame[
        frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq("Total NLTF revenue")
        & frame.get("Line", pd.Series("", index=frame.index)).astype(str).eq(line)
        & pd.to_numeric(frame.get("FY June"), errors="coerce").eq(fy)
    ].copy()
    if rows.empty:
        return None
    selected = rows[rows.get("Model basis", pd.Series("", index=rows.index)).astype(str).eq("selected_dashboard_basis")]
    if selected.empty:
        selected = rows
    return selected.iloc[0].to_dict()


def _official_befu25_total_row(frame: pd.DataFrame, fy: int) -> dict[str, Any] | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    rows = frame[
        frame.get("series", pd.Series("", index=frame.index)).astype(str).eq("Total net revenues")
        & pd.to_numeric(frame.get("FY"), errors="coerce").eq(fy)
    ].copy()
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def _intake_status_row(
    *,
    artifact_name: str,
    artifact_role: str,
    repo_relative_path: str,
    status: str,
    required_for_runtime: bool,
    required_for_replay: bool,
    size_bytes: int | None,
    row_count: int | None,
    sha256: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "artifact_name": artifact_name,
        "artifact_role": artifact_role,
        "repo_relative_path": repo_relative_path,
        "status": status,
        "required_for_runtime": bool(required_for_runtime),
        "required_for_replay": bool(required_for_replay),
        "size_bytes": size_bytes,
        "row_count": row_count,
        "sha256": sha256,
        "notes": notes,
    }


def _decision_handoff_link(item: str, gap_status: dict[str, str]) -> dict[str, Any]:
    text = item.lower()
    if "ped/fed" in text or ("ped" in text and "rates" in text):
        bridge_available = gap_status.get("ped_total_vkt_bridge_missing") == "available"
        return {
            "linked_gap_ids": ["fed_path_scenario_values_missing", "ped_total_vkt_bridge_missing"],
            "linked_artifacts": (
                "annual_model_paths.csv; fed_rate_paths.csv; ped_bridge_inputs.csv; "
                "hybrid_annual_revenue.csv; source_gap_register.csv"
            ),
            "runtime_status": "fed_rate_path_and_total_vkt_source_backed" if bridge_available else "fed_rate_path_source_backed_total_vkt_gap",
            "dashboard_treatment": (
                "Recompute PED revenue from repo-vendored VKT per capita, population, source-backed litres "
                "intensity and FED rate paths."
                if bridge_available
                else "Recompute PED revenue from repo-vendored PED volume and FED rate paths; keep the missing "
                "population-to-total-VKT replay as an explicit governance gap."
            ),
            "availability_status": "open_gap",
        }
    if "light/heavy ruc" in text or "ruc rates" in text:
        return {
            "linked_gap_ids": ["release_value_table_missing"],
            "linked_artifacts": "annual_model_paths.csv; hybrid_annual_revenue.csv; source_gap_register.csv",
            "runtime_status": "source_derived_effective_rate_replay",
            "dashboard_treatment": (
                "Recompute Light/Heavy RUC revenue from repo-vendored net-km rows and source-derived effective "
                "rates; keep independent nominal rate tables as a provenance limitation."
            ),
            "availability_status": "open_gap",
        }
    if "ped bridge" in text:
        bridge_available = gap_status.get("ped_total_vkt_bridge_missing") == "available"
        return {
            "linked_gap_ids": ["ped_total_vkt_bridge_missing"],
            "linked_artifacts": "ped_bridge_inputs.csv; source_gap_register.csv; hybrid_annual_revenue.csv",
            "runtime_status": "bridge_rows_available" if bridge_available else "bridge_replay_missing",
            "dashboard_treatment": (
                "Use the repo-vendored PED bridge rows for population, total VKT and source-backed litres "
                "intensity; do not infer missing training-history rows from validation forecasts."
                if bridge_available
                else "Report PED bridge as a governance gap; do not infer total VKT or training-history "
                "rows from validation forecasts."
            ),
            "availability_status": "open_gap",
        }
    if "pass-through" in text:
        return {
            "linked_gap_ids": ["release_value_table_missing", "quarterly_source_pack_missing"],
            "linked_artifacts": "release_registry.csv; source_gap_register.csv; pass-through value table not vendored",
            "runtime_status": "official_release_path_missing",
            "dashboard_treatment": (
                "Use explicit source rows where present and show missing release-value paths "
                "instead of fabricating pass-through totals."
            ),
            "availability_status": "open_gap",
        }
    if "gross/net/admin/refund" in text:
        return {
            "linked_gap_ids": ["release_value_table_missing"],
            "linked_artifacts": "aggregation_rules.csv; canonical_revenue_long.csv; source_gap_register.csv",
            "runtime_status": "basis_components_partial",
            "dashboard_treatment": "Keep gross, admin, refunds and net basis as separate governed series where source rows exist.",
            "availability_status": "open_gap" if gap_status.get("release_value_table_missing") == "missing" else "source_backed",
        }
    if "crown top-up" in text:
        return {
            "linked_gap_ids": ["crown_top_up_values_missing"],
            "linked_artifacts": "front_end_config.json; source_gap_register.csv",
            "runtime_status": "policy_overlay_missing_values",
            "dashboard_treatment": "Persist Include/Exclude selection and warn when Include is requested without governed top-up value rows.",
            "availability_status": "open_gap",
        }
    if "h13" in text:
        return {
            "linked_gap_ids": [],
            "linked_artifacts": "forecast horizon labels; current_revenue_outlook manifest",
            "runtime_status": "label_applied",
            "dashboard_treatment": "Label H1-H12 as backtest-supported and H13+ as long-range extrapolation or assumption; no value changes.",
            "availability_status": "label_applied",
        }
    return {
        "linked_gap_ids": [],
        "linked_artifacts": "unresolved_decisions.csv",
        "runtime_status": "manual_review_required",
        "dashboard_treatment": "Carry as explicit unresolved governance decision until source evidence is vendored.",
        "availability_status": "open_decision",
    }


def _decision_id(item: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", item.lower()).strip("_")
    return slug or "unresolved_decision"


def _series_role_audit_row(
    *,
    series_id: str,
    display_name: str,
    parent_series_id: str,
    unit: str,
    aggregation_sign: int,
    forecast_role: str,
    dashboard_visible: bool,
    notes: str,
    canonical_rows: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "display_name": display_name,
        "role_category": _role_category(forecast_role),
        "forecast_role": forecast_role,
        "runtime_treatment": _role_runtime_treatment(forecast_role),
        "parent_series_id": parent_series_id,
        "unit": unit,
        "aggregation_sign": aggregation_sign,
        "dashboard_visible": bool(dashboard_visible),
        "canonical_row_count": int(len(canonical_rows)) if isinstance(canonical_rows, pd.DataFrame) else 0,
        "source_statuses": _joined_unique(canonical_rows, "source_status"),
        "bridge_statuses": _joined_unique(canonical_rows, "bridge_status"),
        "revenue_bases": _joined_unique(canonical_rows, "revenue_basis"),
        "notes": notes,
    }


def _role_category(forecast_role: str) -> str:
    if forecast_role == "econometric_model":
        return "direct_model_output"
    if forecast_role in {"econometric_bridge", "derived_bridge"}:
        return "revenue_bridge"
    if forecast_role == "aggregation":
        return "aggregation"
    if forecast_role == "deduction":
        return "deduction"
    if forecast_role == "optional_overlay":
        return "policy_overlay"
    if forecast_role in {"official_pass_through", "derived_scenario_split"}:
        return "pass_through_or_governed_assumption"
    if forecast_role == "unregistered_source_line":
        return "source_registry_gap"
    return "manual_review"


def _role_runtime_treatment(forecast_role: str) -> str:
    if forecast_role == "econometric_model":
        return "modeled_activity_stream"
    if forecast_role in {"econometric_bridge", "derived_bridge"}:
        return "requires_governed_bridge_inputs"
    if forecast_role == "aggregation":
        return "calculated_from_child_series_when_inputs_exist"
    if forecast_role == "deduction":
        return "preserve_sign_and_subtract_in_rollup"
    if forecast_role == "optional_overlay":
        return "apply_only_with_explicit_policy_selection_and_values"
    if forecast_role in {"official_pass_through", "derived_scenario_split"}:
        return "source_or_assumption_backed_pass_through"
    if forecast_role == "unregistered_source_line":
        return "preserve_as_source_registry_gap"
    return "manual_review_required"


def _joined_unique(frame: pd.DataFrame, column: str) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        return ""
    values = sorted({str(value).strip() for value in frame[column].dropna() if str(value).strip()})
    return "; ".join(values)


def _first_text(frame: pd.DataFrame, column: str) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        return ""
    values = [str(value).strip() for value in frame[column].dropna() if str(value).strip()]
    return values[0] if values else ""


def _first_int(frame: pd.DataFrame, column: str, *, default: int) -> int:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        return default
    value = pd.to_numeric(frame[column], errors="coerce").dropna()
    return int(value.iloc[0]) if not value.empty else default


def _nullable_int(value: Any) -> int | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else int(numeric)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _registry(series_master: pd.DataFrame) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for record in series_master.to_dict("records"):
        series_id = str(record.get("Series ID", "")).strip()
        display = str(record.get("Display name", "")).strip()
        if not series_id:
            continue
        payload = {
            "series_id": series_id,
            "display_name": display,
            "parent_series_id": "" if pd.isna(record.get("Parent series ID")) else str(record.get("Parent series ID", "")).strip(),
            "unit": record.get("Unit", ""),
            "aggregation_sign": _as_sign(record.get("Sign")),
            "forecast_role": record.get("Forecast role", ""),
            "group": record.get("Group", ""),
        }
        records[series_id] = payload
        if display:
            records[display] = payload
    return records


def _canonical_row(registry: dict[str, dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    raw_label = kwargs["source_label"]
    label = "" if pd.isna(raw_label) else str(raw_label).strip()
    direct = registry.get(label)
    alias_id = SOURCE_SERIES_ALIASES.get(label)
    alias = registry.get(alias_id or "") if alias_id else None
    if direct is not None:
        reg = direct
        source_status = "registered"
    elif alias is not None:
        reg = alias
        source_status = "registered_alias"
    elif alias_id:
        reg = {
            "series_id": alias_id,
            "display_name": label,
            "parent_series_id": "",
            "unit": kwargs.get("unit", ""),
            "aggregation_sign": 1,
            "forecast_role": "derived_bridge",
            "group": kwargs.get("group", ""),
        }
        source_status = "registered_alias"
    else:
        generated_id = _slug(label)
        reg = {
            "series_id": generated_id,
            "display_name": label,
            "parent_series_id": "",
            "unit": kwargs.get("unit", ""),
            "aggregation_sign": -1 if "refund" in label.lower() else 1,
            "forecast_role": "unregistered_source_line",
            "group": kwargs.get("group", ""),
        }
        source_status = "unregistered_source_series"

    raw_unit = kwargs.get("unit", "")
    unit = "" if pd.isna(raw_unit) else str(raw_unit).strip()
    raw_line = kwargs.get("line", "")
    line = "" if pd.isna(raw_line) else str(raw_line).strip()
    return {
        "period": kwargs.get("period", ""),
        "FY": kwargs.get("fy"),
        "time_grain": kwargs.get("time_grain", "june_year"),
        "series_id": reg["series_id"],
        "source_series_label": label,
        "display_name": reg.get("display_name") or label,
        "parent_series_id": reg.get("parent_series_id", ""),
        "value": kwargs.get("value"),
        "unit": unit,
        "aggregation_sign": reg.get("aggregation_sign", 1),
        "release_vintage": kwargs.get("release_vintage", ""),
        "release_family": kwargs.get("release_family", ""),
        "release_year": kwargs.get("release_year", ""),
        "horizon": kwargs.get("horizon", ""),
        "forecast_path": kwargs.get("forecast_path", ""),
        "path_status": _path_status(str(kwargs.get("forecast_path", "")), str(kwargs.get("line", ""))),
        "scenario_name": kwargs.get("scenario_name", ""),
        "scenario_role": kwargs.get("scenario_role", ""),
        "model_basis": kwargs.get("model_basis", ""),
        "revenue_basis": _revenue_basis(label, unit),
        "value_status": kwargs.get("value_status", ""),
        "forecast_role": reg.get("forecast_role", ""),
        "line": line,
        "source_status": source_status,
        "bridge_status": _bridge_status(reg.get("forecast_role", ""), source_status, line),
        "source_file": kwargs.get("source_file", ""),
        "source_sheet": kwargs.get("source_sheet", ""),
        "source_cell": kwargs.get("source_cell", ""),
        "normalized_source_sha256": kwargs.get("normalized_source_sha256", ""),
        "source_hash_sha256": kwargs.get("source_hash_sha256", ""),
        "distilled_hash_sha256": kwargs.get("distilled_hash_sha256", ""),
    }


def _reconciliation_scopes(canonical_long: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    scopes = []
    actual = canonical_long[
        canonical_long["source_file"].eq("annual_actuals.csv")
        & canonical_long["unit"].astype(str).str.contains(r"\$m", regex=True, na=False)
    ].copy()
    scopes.append(("official_actuals", actual))
    selected = canonical_long[
        canonical_long["source_file"].eq("annual_model_paths.csv")
        & canonical_long["model_basis"].eq("selected_dashboard_basis")
        & canonical_long["line"].isin(["Actual", "Actual / benchmark", "Model path"])
        & canonical_long["unit"].astype(str).str.contains(r"\$m", regex=True, na=False)
    ].copy()
    scopes.append(("selected_dashboard_basis", selected))
    return scopes


def _rollup_rows(scope: str, fy: int, values: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for output, inputs in REQUIRED_ROLLUP_INPUTS.items():
        missing = [series_id for series_id in inputs if series_id not in values or pd.isna(values.get(series_id))]
        optional_applied = [series_id for series_id in OPTIONAL_ROLLUP_INPUTS.get(output, []) if series_id in values and not pd.isna(values.get(series_id))]
        official = values.get(output)
        if missing:
            status = "partial_missing"
            calculated = pd.NA
            difference = pd.NA
        else:
            calculated = _calculate_rollup(output, values)
            if official is None or pd.isna(official):
                status = "official_row_missing"
                difference = pd.NA
            else:
                status = "reconciled" if abs(float(calculated) - float(official)) <= 0.05 else "difference_reported"
                difference = float(calculated) - float(official)
        rows.append(
            {
                "scope": scope,
                "FY": fy,
                "output_series_id": output,
                "component_status": status,
                "calculated_value": calculated,
                "official_value": official if official is not None else pd.NA,
                "difference": difference,
                "missing_inputs": "; ".join(missing),
                "optional_inputs_applied": "; ".join(optional_applied),
            }
        )
    return rows


def _calculate_rollup(output: str, values: dict[str, Any]) -> float:
    if output == "gross_fed_revenue":
        return float(values["gross_ped_revenue"]) + float(values["gross_lpg_revenue"]) + float(values["gross_cng_revenue"])
    if output == "net_fed_revenue":
        top_up = 0.0 if "crown_top_up" not in values or pd.isna(values.get("crown_top_up")) else float(values["crown_top_up"])
        return float(values["gross_fed_revenue"]) - float(values["fed_refunds"]) + top_up
    if output == "total_ruc_net_revenue":
        return (
            float(values["light_ruc_net_revenue"])
            + float(values["heavy_ruc_net_revenue"])
            + float(values["light_bev_ruc_net_revenue"])
            + float(values["heavy_bev_ruc_net_revenue"])
            + float(values["phev_ruc_net_revenue"])
        )
    if output == "net_mvr_revenue":
        return (
            float(values["mr1_cvl_revenue"])
            + float(values["mr2_revenue"])
            + float(values["coo_revenue"])
            + float(values["mvr_admin_revenue"])
            - float(values["mvr_refunds"])
        )
    if output == "total_fed_ruc_net_revenue":
        return float(values["net_fed_revenue"]) + float(values["total_ruc_net_revenue"])
    if output == "total_nltf_net_revenue":
        return float(values["net_fed_revenue"]) + float(values["total_ruc_net_revenue"]) + float(values["net_mvr_revenue"]) + float(values["tuc_net_revenue"])
    raise KeyError(output)


def _fys_with_series(frame: pd.DataFrame, series_ids: set[str]) -> set[int]:
    if frame.empty:
        return set()
    present = frame[frame["series_id"].isin(series_ids) & frame["value_numeric"].notna()].copy()
    if present.empty:
        return set()
    counts = present.groupby("FY")["series_id"].agg(lambda values: set(values.dropna().astype(str)))
    return {int(fy) for fy, available in counts.items() if series_ids.issubset(available)}


def _value_lookup(frame: pd.DataFrame) -> dict[str, float]:
    values: dict[str, float] = {}
    if frame.empty:
        return values
    ordered = frame.sort_values(["series_id", "source_file", "source_cell"], kind="stable")
    for series_id, group in ordered.groupby("series_id", dropna=False):
        value = pd.to_numeric(group["value_numeric"], errors="coerce").dropna()
        if not value.empty:
            values[str(series_id)] = float(value.iloc[-1])
    return values


def _hybrid_row(
    fy: int,
    series_id: str,
    value: float,
    row_role: str,
    source_basis: str,
    source_file: str,
    *,
    formula: str = "",
    replacement_only: bool = False,
    official_value: float | None = None,
    fed_path: str = "",
    unit: str = "$m nominal ex GST",
    availability_status: str = "available",
) -> dict[str, Any]:
    display_names = {
        "population_count": "Population count",
        "ped_total_vkt": "PED total VKT",
        "ped_litres_per_100km": "PED litres per 100km",
        "ped_volume": "PED volume",
        "ped_fed_rate_path": "PED/FED rate path",
        "light_ruc_net_km": "Light RUC net km",
        "light_ruc_effective_rate": "Light RUC effective rate",
        "heavy_ruc_net_km": "Heavy RUC net km",
        "heavy_ruc_effective_rate": "Heavy RUC effective rate",
        "gross_ped_revenue": "Gross PED revenue",
        "light_ruc_net_revenue": "Light RUC net revenue",
        "heavy_ruc_net_revenue": "Heavy RUC net revenue",
        "gross_lpg_revenue": "Gross LPG revenue",
        "gross_cng_revenue": "Gross CNG revenue",
        "fed_refunds": "FED refunds",
        "ruc_fixed_residual_net_revenue": "MOT fixed RUC rows net residual",
        "net_mvr_revenue": "Net MVR revenue",
        "tuc_net_revenue": "TUC net revenue",
        "gross_fed_revenue": "Gross FED revenue",
        "net_fed_revenue": "Net FED revenue",
        "total_ruc_net_revenue": "Total RUC net revenue",
        "total_fed_ruc_net_revenue": "Total FED+RUC net revenue",
        "total_nltf_net_revenue": "Total NLTF revenue",
    }
    residual = pd.NA
    if official_value is not None and pd.notna(official_value):
        residual = float(value) - float(official_value)
    return {
        "FY": fy,
        "fed_path": fed_path,
        "series_id": series_id,
        "display_name": display_names.get(series_id, series_id),
        "value": value,
        "unit": unit,
        "row_role": row_role,
        "source_basis": source_basis,
        "source_file": source_file,
        "source_status": "source_backed",
        "formula": formula,
        "replacement_only": bool(replacement_only),
        "official_value": official_value if official_value is not None else pd.NA,
        "residual_vs_official": residual,
        "availability_status": availability_status,
    }


def _issue(severity: str, check: str, message: str) -> dict[str, str]:
    return {"severity": severity, "check": check, "message": message}


def _manifest_declared_files(manifest: dict[str, Any]) -> list[str]:
    filenames: set[str] = set()
    for bucket in ("normalized_files", "config_files"):
        payload = manifest.get(bucket, {})
        if isinstance(payload, dict):
            filenames.update(str(filename) for filename in payload if str(filename).strip())
    return sorted(filenames)


def _normalized_file_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    payload = manifest.get("normalized_files", {}) if isinstance(manifest, dict) else {}
    if not isinstance(payload, dict):
        return {}
    hashes: dict[str, str] = {}
    for filename, metadata in payload.items():
        if not isinstance(metadata, dict):
            continue
        expected = str(metadata.get("sha256", "")).strip()
        if expected:
            hashes[str(filename)] = expected
    return hashes


def _manifest_file_hash_issues(manifest: dict[str, Any], pack_dir: Path | None) -> list[dict[str, str]]:
    if pack_dir is None:
        return []
    issues: list[dict[str, str]] = []
    for bucket in ("normalized_files", "config_files"):
        payload = manifest.get(bucket, {})
        if not isinstance(payload, dict):
            issues.append(_issue("error", "source_pack_manifest_files", f"Manifest {bucket} must be an object of file metadata."))
            continue
        for filename, metadata in sorted(payload.items()):
            name = str(filename).strip()
            if not name:
                continue
            expected = str(metadata.get("sha256", "")).strip() if isinstance(metadata, dict) else ""
            path = pack_dir / name
            if not path.exists():
                issues.append(_issue("error", "source_pack_file_missing", f"Manifest-declared source-pack file is missing: {name}."))
                continue
            if not expected:
                issues.append(_issue("error", "source_pack_file_hash", f"Manifest-declared source-pack file has no SHA256: {name}."))
                continue
            actual = _sha256(path)
            if actual != expected:
                issues.append(
                    _issue(
                        "error",
                        "source_pack_file_hash",
                        f"Manifest-declared source-pack file hash mismatch: {name}.",
                    )
                )
    return issues


def _as_int(value: Any) -> int | None:
    try:
        if pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_sign(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 1
    if number < 0:
        return -1
    if number > 0:
        return 1
    return 0


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text or "unknown_series"


def _release_vintage(model_basis: str, line: str) -> str:
    if line in {"Actual", "Actual / benchmark"}:
        return "actual_benchmark"
    return model_basis or "model_path"


def _forecast_path(model_basis: str, line: str) -> str:
    if line in {"Actual", "Actual / benchmark"}:
        return "actual_benchmark"
    return model_basis or "model_path"


def _scenario_name(model_basis: str, line: str) -> str:
    if line in {"Actual", "Actual / benchmark"}:
        return "actual_benchmark"
    return model_basis.replace("_", " ") if model_basis else "model_path"


def _scenario_role(line: str) -> str:
    if line in {"Actual", "Actual / benchmark"}:
        return "actual_benchmark"
    if line == "Error":
        return "diagnostic"
    return "model_path"


def _path_status(forecast_path: str, line: str) -> str:
    if line in {"Actual", "Actual / benchmark", "actual", "benchmark_or_release_value", "policy_overlay_actual"} or forecast_path in {"actual", "actual_benchmark", "official_actual"}:
        return "actual_or_benchmark"
    if forecast_path.startswith("mot_release:") or forecast_path == "mot_release":
        return "selected_mot_release_forecast"
    if forecast_path.startswith("fed_path:") or forecast_path == "fed_path":
        return "fed_path_rate"
    if forecast_path == "selected_dashboard_basis":
        return "selected_workbook_basis"
    if forecast_path == "in_house_prediction":
        return "in_house_prediction_forecast"
    if forecast_path == "aaron_schiff_prediction":
        return "aaron_schiff_prediction_forecast"
    return "other_model_path"


def _revenue_basis(label: str, unit: str) -> str:
    lower = label.lower()
    if "$" not in unit:
        return "activity"
    if "gross" in lower:
        return "gross"
    if "refund" in lower:
        return "deduction"
    if "admin" in lower:
        return "admin"
    if "net" in lower or "total ruc+ped" in lower or "total nltf" in lower:
        return "net"
    return "nominal_ex_gst"


def _bridge_status(forecast_role: str, source_status: str, line: str) -> str:
    if source_status == "unregistered_source_series":
        return "source_registry_gap"
    if line in {"Actual", "Actual / benchmark", "actual", "benchmark_or_release_value", "policy_overlay_actual"}:
        return "source_actual_or_benchmark"
    if line == "rate_path":
        return "rate_path_source"
    if forecast_role in {"econometric_bridge", "derived_bridge"}:
        return "bridge_required"
    if forecast_role in {"official_pass_through", "deduction", "optional_overlay", "derived_scenario_split"}:
        return "pass_through_or_assumption"
    return "aggregation_or_model_path"

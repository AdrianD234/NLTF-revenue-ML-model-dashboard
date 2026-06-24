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
REVENUE_SOURCE_PACK_SCHEMA_VERSION = "nltf-revenue-source-pack-v1"
CANONICAL_REVENUE_SCHEMA_VERSION = "nltf-revenue-canonical-long-v1"
REVENUE_SOURCE_PACK_RUNTIME_REVISION = "2026-06-24-source-gap-register-v1"

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

CORE_ROLLUP_SERIES = {
    "gross_fed_revenue",
    "net_fed_revenue",
    "total_ruc_net_revenue",
    "net_mvr_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
}

# Explicit, reviewed label bindings from the distilled pack. Labels not covered
# here are still preserved with generated IDs and a source_registry_gap status.
SOURCE_SERIES_ALIASES = {
    "Total NLTF revenue": "total_nltf_net_revenue",
    "Total net revenues": "total_nltf_net_revenue",
    "Total RUC+PED revenue": "total_fed_ruc_net_revenue",
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
    "MVR admin revenue": "mvr_admin_revenue",
    "MVR refunds": "mvr_refunds",
    "TUC net revenue": "tuc_net_revenue",
    "PED VKT per capita": "ped_vkt_per_capita",
    "PED volume": "ped_volume",
    "Light RUC net km": "light_ruc_net_km",
    "Heavy RUC net km": "heavy_ruc_net_km",
    "Light BEV RUC net km": "light_bev_ruc_net_km",
    "Heavy BEV RUC net km": "heavy_bev_ruc_net_km",
    "PHEV RUC net km": "phev_ruc_net_km",
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
    canonical_long: pd.DataFrame
    validation_issues: pd.DataFrame
    reconciliation_report: pd.DataFrame
    source_gap_register: pd.DataFrame
    path_trace_status: pd.DataFrame
    intake_status: pd.DataFrame
    remaining_decisions_handoff: pd.DataFrame
    series_role_audit: pd.DataFrame

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
    signature = []
    for filename in REQUIRED_SOURCE_PACK_FILES:
        path = base / filename
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

    canonical = canonical_revenue_long_frame(
        series_master=series_master,
        annual_actuals=annual_actuals,
        annual_model_paths=annual_model_paths,
        manifest=manifest,
    )
    validation = validate_revenue_source_pack(
        manifest=manifest,
        series_master=series_master,
        aggregation_rules=aggregation_rules,
        front_end_config=front_end_config,
        unresolved_decisions=unresolved_decisions,
        canonical_long=canonical,
    )
    reconciliation = revenue_reconciliation_report(canonical)
    gap_register = revenue_source_gap_register(
        manifest=manifest,
        front_end_config=front_end_config,
        canonical_long=canonical,
    )
    path_trace_status = revenue_path_trace_status(
        canonical_long=canonical,
        gap_register=gap_register,
    )
    intake_status = revenue_source_pack_intake_status(
        pack_dir=base,
        manifest=manifest,
    )
    remaining_decisions = revenue_remaining_decisions_handoff(
        unresolved_decisions=unresolved_decisions,
        gap_register=gap_register,
    )
    role_audit = revenue_series_role_audit(
        series_master=series_master,
        canonical_long=canonical,
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
        canonical_long=canonical,
        validation_issues=validation,
        reconciliation_report=reconciliation,
        source_gap_register=gap_register,
        path_trace_status=path_trace_status,
        intake_status=intake_status,
        remaining_decisions_handoff=remaining_decisions,
        series_role_audit=role_audit,
    )


def canonical_revenue_long_frame(
    *,
    series_master: pd.DataFrame,
    annual_actuals: pd.DataFrame,
    annual_model_paths: pd.DataFrame,
    manifest: dict[str, Any],
) -> pd.DataFrame:
    registry = _registry(series_master)
    rows = []
    source_hash = str(manifest.get("raw_workbook", {}).get("sha256", ""))
    distilled_hash = str(manifest.get("distilled_workbook", {}).get("sha256", ""))

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


def validate_revenue_source_pack(
    *,
    manifest: dict[str, Any],
    series_master: pd.DataFrame,
    aggregation_rules: pd.DataFrame,
    front_end_config: dict[str, Any],
    unresolved_decisions: pd.DataFrame,
    canonical_long: pd.DataFrame,
) -> pd.DataFrame:
    issues: list[dict[str, Any]] = []
    if manifest.get("schema_version") != REVENUE_SOURCE_PACK_SCHEMA_VERSION:
        issues.append(_issue("error", "manifest_schema", "Unexpected revenue source pack schema version."))
    if manifest.get("raw_workbook", {}).get("sha256") != "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b":
        issues.append(_issue("error", "raw_sha256", "Raw workbook SHA256 does not match the governed lineage hash."))

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
    if canonical_long["period"].fillna("").astype(str).str.match(r"^FY\d{4}$").eq(False).any():
        issues.append(_issue("error", "period", "One or more canonical rows has an invalid FY period label."))
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

    critical_decisions = unresolved_decisions[unresolved_decisions["Priority"].astype(str).str.lower().eq("critical")]
    if not critical_decisions.empty:
        issues.append(
            _issue(
                "warning",
                "unresolved_critical_decisions",
                f"{len(critical_decisions)} critical revenue decisions remain explicit gaps.",
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
    has_quarterly_values = bool(canonical_long["time_grain"].astype(str).str.lower().eq("quarterly").any()) if "time_grain" in canonical_long.columns else False
    has_ped_total_vkt = bool(canonical_long["series_id"].eq("ped_total_vkt").any()) if "series_id" in canonical_long.columns else False
    rows = [
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
            "runtime_treatment": "excluded_by_selection"
            if crown_top_up_selection.lower() == "exclude"
            else "not_applied_missing_source",
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
) -> pd.DataFrame:
    release_gap = _gap_status(gap_register, "release_value_table_missing")
    has_actual = _has_trace_rows(canonical_long, line_values={"Actual", "Actual / benchmark"})
    has_selected_workbook = _has_trace_rows(canonical_long, model_basis="selected_dashboard_basis", line_values={"Model path"})
    has_in_house = _has_trace_rows(canonical_long, model_basis="in_house_model", line_values={"Model path"})
    has_schiff = _has_trace_rows(canonical_long, model_basis="aaron_schiff_model", line_values={"Model path"})
    release_available = release_gap.get("availability_status") == "available"
    rows = [
        _trace_status_row(
            "actual_benchmark",
            "Actual / benchmark",
            has_actual,
            "annual actual and benchmark rows",
            "",
            "Source actual/benchmark rows are plotted where present.",
        ),
        _trace_status_row(
            "selected_workbook_basis",
            "Selected workbook basis",
            has_selected_workbook,
            "annual model path rows",
            "",
            "Current workbook-selected annual model path is plotted.",
        ),
        _trace_status_row(
            "selected_mot_befu_release",
            "Selected MOT/BEFU release path",
            release_available,
            "release-value table",
            "" if release_available else "release_value_table_missing",
            "Selected MOT/BEFU release path requires release-value rows; registry-only release metadata is not plotted as values.",
        ),
        _trace_status_row(
            "rolling_befu_1y",
            "Rolling BEFU 1Y",
            release_available,
            "release-value table",
            "" if release_available else "release_value_table_missing",
            "Rolling BEFU 1Y requires historical release-value rows; it is not fabricated from model paths.",
        ),
        _trace_status_row(
            "aaron_schiff_model",
            "Aaron Schiff prediction / forecast",
            has_schiff,
            "annual model path rows",
            "",
            "Aaron Schiff annual model path is plotted where source rows exist.",
        ),
        _trace_status_row(
            "in_house_model",
            "In-house prediction / forecast",
            has_in_house,
            "annual model path rows",
            "",
            "In-house annual model path is plotted where source rows exist.",
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
                required_for_runtime=filename in REQUIRED_SOURCE_PACK_FILES,
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
        rows.append(
            _series_role_audit_row(
                series_id=series_id,
                display_name=display,
                parent_series_id=_first_text(group, "parent_series_id"),
                unit=_first_text(group, "unit"),
                aggregation_sign=_first_int(group, "aggregation_sign", default=1),
                forecast_role="unregistered_source_line",
                dashboard_visible=False,
                notes="Preserved source line not registered in series_master.csv; retained as a governance gap.",
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


def control_options(pack: RevenueSourcePack | None, control_id: str, default: list[str]) -> list[str]:
    if pack is None:
        return default
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
    return _selection_value(selections, control_id, default)


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
    message: str,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "trace_label": trace_label,
        "availability_status": "available" if available else "missing",
        "plotted": bool(available),
        "data_scope": data_scope,
        "blocking_gap_id": blocking_gap_id,
        "user_visible_message": message,
    }


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
        return {
            "linked_gap_ids": ["ped_total_vkt_bridge_missing"],
            "linked_artifacts": "annual_model_paths.csv; source_gap_register.csv; nominal PED/FED rate table not vendored",
            "runtime_status": "nominal_rate_path_missing",
            "dashboard_treatment": (
                "Preserve workbook-sourced PED/FED paths; do not refit or bridge future revenue "
                "without governed nominal rate paths."
            ),
            "availability_status": "open_gap",
        }
    if "light/heavy ruc" in text or "ruc rates" in text:
        return {
            "linked_gap_ids": ["release_value_table_missing"],
            "linked_artifacts": "annual_model_paths.csv; source_gap_register.csv; nominal Light/Heavy RUC rate table not vendored",
            "runtime_status": "nominal_rate_path_missing",
            "dashboard_treatment": (
                "Preserve modeled RUC revenue rows; do not recompute from net-km forecasts "
                "without governed effective rate paths."
            ),
            "availability_status": "open_gap",
        }
    if "ped bridge" in text:
        return {
            "linked_gap_ids": ["ped_total_vkt_bridge_missing"],
            "linked_artifacts": "source_gap_register.csv; PED bridge history not vendored",
            "runtime_status": "bridge_replay_missing",
            "dashboard_treatment": (
                "Report PED bridge as a governance gap; do not infer total VKT or training-history "
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
            "runtime_status": "label_required",
            "dashboard_treatment": "Label H1-H12 as backtest-supported and H13+ as long-range extrapolation or assumption; no value changes.",
            "availability_status": "governance_label_required",
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
    label = str(kwargs["source_label"]).strip()
    direct = registry.get(label)
    alias_id = SOURCE_SERIES_ALIASES.get(label)
    alias = registry.get(alias_id or "") if alias_id else None
    if direct is not None:
        reg = direct
        source_status = "registered"
    elif alias is not None:
        reg = alias
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

    unit = str(kwargs.get("unit", "")).strip()
    line = str(kwargs.get("line", "")).strip()
    return {
        "period": kwargs.get("period", ""),
        "FY": kwargs.get("fy"),
        "time_grain": "june_year",
        "series_id": reg["series_id"],
        "source_series_label": label,
        "display_name": reg.get("display_name") or label,
        "parent_series_id": reg.get("parent_series_id", ""),
        "value": kwargs.get("value"),
        "unit": unit,
        "aggregation_sign": reg.get("aggregation_sign", 1),
        "release_vintage": kwargs.get("release_vintage", ""),
        "forecast_path": kwargs.get("forecast_path", ""),
        "path_status": _path_status(str(kwargs.get("forecast_path", "")), str(kwargs.get("line", ""))),
        "scenario_name": kwargs.get("scenario_name", ""),
        "scenario_role": kwargs.get("scenario_role", ""),
        "model_basis": kwargs.get("model_basis", ""),
        "revenue_basis": _revenue_basis(label, unit),
        "forecast_role": reg.get("forecast_role", ""),
        "line": line,
        "source_status": source_status,
        "bridge_status": _bridge_status(reg.get("forecast_role", ""), source_status, line),
        "source_file": kwargs.get("source_file", ""),
        "source_sheet": kwargs.get("source_sheet", ""),
        "source_cell": kwargs.get("source_cell", ""),
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


def _issue(severity: str, check: str, message: str) -> dict[str, str]:
    return {"severity": severity, "check": check, "message": message}


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
    if line in {"Actual", "Actual / benchmark"} or forecast_path in {"actual", "actual_benchmark", "official_actual"}:
        return "actual_or_benchmark"
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
    if line in {"Actual", "Actual / benchmark"}:
        return "source_actual_or_benchmark"
    if forecast_role in {"econometric_bridge", "derived_bridge"}:
        return "bridge_required"
    if forecast_role in {"official_pass_through", "deduction", "optional_overlay", "derived_scenario_split"}:
        return "pass_through_or_assumption"
    return "aggregation_or_model_path"

"""Repo-local NLTF revenue source-pack loader and canonical schema.

The normalized source pack is the contract for the Revenue Outlook page. This
module does not load the raw workbook and does not use Excel coordinates as
runtime logic; source cells are lineage metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


REVENUE_SOURCE_PACK_DIR = Path("data") / "revenue_model_source_pack" / "2026_05_19"
REVENUE_SOURCE_PACK_SCHEMA_VERSION = "nltf-revenue-source-pack-v1"
CANONICAL_REVENUE_SCHEMA_VERSION = "nltf-revenue-canonical-long-v1"

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
            ]
        )
    report["abs_difference"] = pd.to_numeric(report["difference"], errors="coerce").abs()
    return report.sort_values(["scope", "FY", "output_series_id"], kind="stable").reset_index(drop=True)


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
    value = selections.get(control_id, {}).get("current_value") if isinstance(selections.get(control_id, {}), dict) else None
    return str(value) if value else default


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
            }
        )
    return rows


def _calculate_rollup(output: str, values: dict[str, Any]) -> float:
    if output == "gross_fed_revenue":
        return float(values["gross_ped_revenue"]) + float(values["gross_lpg_revenue"]) + float(values["gross_cng_revenue"])
    if output == "net_fed_revenue":
        return float(values["gross_fed_revenue"]) - float(values["fed_refunds"])
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

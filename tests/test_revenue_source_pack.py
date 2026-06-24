from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pandas as pd

from model_dashboard.revenue_source_pack import (
    CANONICAL_REVENUE_SCHEMA_VERSION,
    REQUIRED_SOURCE_PACK_FILES,
    REVENUE_SOURCE_PACK_SCHEMA_VERSION,
    control_options,
    current_selection,
    load_revenue_source_pack,
    revenue_reconciliation_report,
)
from scripts.export_revenue_source_pack_tables import export_tables


ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "revenue_model_source_pack" / "2026_05_19"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rollup_source_row(fy: int, series_id: str, value: float) -> dict[str, object]:
    return {
        "scope": "official_actuals",
        "FY": fy,
        "series_id": series_id,
        "value": value,
        "unit": "$m nominal ex GST",
        "source_file": "annual_actuals.csv",
        "model_basis": "official_actuals",
        "line": "Actual",
    }


def test_revenue_source_pack_required_files_are_repo_local_and_hash_backed() -> None:
    assert PACK_DIR.exists()
    for filename in REQUIRED_SOURCE_PACK_FILES:
        assert (PACK_DIR / filename).exists(), filename

    manifest_text = (PACK_DIR / "manifest.json").read_text(encoding="utf-8")
    assert "C:\\Users" not in manifest_text
    assert "Downloads" not in manifest_text
    assert "OneDrive" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == REVENUE_SOURCE_PACK_SCHEMA_VERSION
    assert manifest["raw_workbook"]["sha256"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"
    assert manifest["raw_workbook"]["status"] == "verified_lineage_only_not_committed"

    for filename, meta in manifest["normalized_files"].items():
        assert (PACK_DIR / filename).stat().st_size < 50 * 1024 * 1024
        assert meta["sha256"] == _sha256(PACK_DIR / filename)
    for filename, meta in manifest["config_files"].items():
        assert (PACK_DIR / filename).stat().st_size < 50 * 1024 * 1024
        assert meta["sha256"] == _sha256(PACK_DIR / filename)


def test_revenue_source_pack_canonical_long_schema_preserves_source_rows() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    frame = pack.canonical_long
    expected_rows = len(pack.annual_actuals) + len(pack.annual_model_paths)
    assert len(frame) == expected_rows
    assert set(frame["schema_version"]) == {CANONICAL_REVENUE_SCHEMA_VERSION}

    required = {
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
    assert required.issubset(frame.columns)
    assert not frame["unit"].astype(str).str.strip().eq("").any()
    assert frame["period"].astype(str).str.match(r"^FY\d{4}$").all()
    assert set(frame["aggregation_sign"].dropna().unique()).issubset({-1, 0, 1})
    assert set(frame["path_status"].dropna().unique()).issubset(
        {"actual_or_benchmark", "selected_workbook_basis", "in_house_prediction_forecast", "aaron_schiff_prediction_forecast", "other_model_path"}
    )
    assert frame.duplicated(["source_file", "source_cell", "period", "series_id", "forecast_path", "model_basis", "line"]).sum() == 0


def test_revenue_source_pack_legacy_total_ruc_ped_is_not_root_total() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    frame = pack.canonical_long
    legacy = frame[frame["source_series_label"].eq("Total RUC+PED revenue")]
    assert not legacy.empty
    assert set(legacy["series_id"]) == {"total_fed_ruc_net_revenue"}

    root = frame[frame["series_id"].eq("total_nltf_net_revenue")]
    assert not root.empty
    assert not root["source_series_label"].eq("Total RUC+PED revenue").any()


def test_revenue_source_pack_rollups_reconcile_where_inputs_exist_and_report_gaps() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    report = pack.reconciliation_report
    assert not report.empty

    gross_fed = report[(report["scope"].eq("official_actuals")) & (report["output_series_id"].eq("gross_fed_revenue"))]
    assert not gross_fed.empty
    assert set(gross_fed["component_status"]) == {"reconciled"}
    assert pd.to_numeric(gross_fed["abs_difference"], errors="coerce").max() <= 0.05

    net_fed = report[(report["scope"].eq("official_actuals")) & (report["output_series_id"].eq("net_fed_revenue"))]
    assert not net_fed.empty
    assert set(net_fed["component_status"]) == {"reconciled"}
    assert pd.to_numeric(net_fed["abs_difference"], errors="coerce").max() <= 0.05

    assert "partial_missing" in set(report["component_status"])
    assert "difference_reported" in set(report["component_status"])
    assert report.loc[report["component_status"].eq("partial_missing"), "missing_inputs"].astype(str).str.len().gt(0).all()
    net_mvr = report[(report["scope"].eq("official_actuals")) & (report["output_series_id"].eq("net_mvr_revenue"))]
    assert not net_mvr.empty
    assert set(net_mvr["component_status"]) == {"partial_missing"}
    assert net_mvr["missing_inputs"].astype(str).str.contains("mr1_cvl_revenue").all()
    assert net_mvr["calculated_value"].isna().all()


def test_revenue_rollup_applies_crown_top_up_only_when_value_exists() -> None:
    frame = pd.DataFrame(
        [
            _rollup_source_row(2024, "gross_fed_revenue", 100.0),
            _rollup_source_row(2024, "fed_refunds", 10.0),
            _rollup_source_row(2024, "net_fed_revenue", 90.0),
            _rollup_source_row(2025, "gross_fed_revenue", 100.0),
            _rollup_source_row(2025, "fed_refunds", 10.0),
            _rollup_source_row(2025, "crown_top_up", 5.0),
            _rollup_source_row(2025, "net_fed_revenue", 95.0),
        ]
    )

    report = revenue_reconciliation_report(frame)
    net_fed = report[report["output_series_id"].eq("net_fed_revenue")].set_index("FY")

    assert net_fed.loc[2024, "component_status"] == "reconciled"
    assert net_fed.loc[2024, "calculated_value"] == 90.0
    assert net_fed.loc[2024, "optional_inputs_applied"] == ""
    assert net_fed.loc[2025, "component_status"] == "reconciled"
    assert net_fed.loc[2025, "calculated_value"] == 95.0
    assert net_fed.loc[2025, "optional_inputs_applied"] == "crown_top_up"


def test_revenue_source_pack_validation_is_warning_not_error_for_known_source_gaps() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    assert pack.validation_status == "warning"
    issues = pack.validation_issues
    assert not issues.empty
    assert "error" not in set(issues["severity"])
    assert {"revenue_basis_alias", "series_registry_gap", "unresolved_critical_decisions"}.issubset(set(issues["check"]))
    assert "front_end_config" not in set(issues["check"])


def test_revenue_basis_control_is_derived_from_normalized_contract_rows() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    options = control_options(pack, "revenue_basis", ["Net", "Gross"])

    assert options[:2] == ["Net", "Gross"]
    assert {"Admin", "Deductions", "Nominal ex GST"}.issubset(set(options))
    assert "activity" not in options
    assert current_selection(pack, "revenue_basis", "Gross") == "Net"
    control_ids = {
        str(item.get("control_id", ""))
        for item in pack.front_end_config.get("controls", [])
        if isinstance(item, dict)
    }
    assert "revenue_basis" not in control_ids


def test_revenue_source_gap_register_exposes_missing_release_and_top_up_inputs() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    gaps = pack.source_gap_register
    assert not gaps.empty
    assert {"gap_id", "availability_status", "runtime_treatment", "user_visible_message"}.issubset(gaps.columns)

    by_id = gaps.set_index("gap_id")
    assert by_id.loc["release_value_table_missing", "availability_status"] == "missing"
    assert by_id.loc["release_value_table_missing", "runtime_treatment"] == "registry_only"
    assert by_id.loc["crown_top_up_values_missing", "availability_status"] == "missing"
    assert by_id.loc["crown_top_up_values_missing", "runtime_treatment"] == "excluded_by_selection"
    assert by_id.loc["quarterly_source_pack_missing", "runtime_treatment"] == "annual_only_source_pack"
    assert by_id["user_visible_message"].astype(str).str.len().gt(20).all()


def test_revenue_remaining_decisions_handoff_links_runtime_gaps_and_is_sanitized() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    handoff = pack.remaining_decisions_handoff
    assert len(handoff) == len(pack.unresolved_decisions) == 7
    assert {
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
    }.issubset(handoff.columns)

    handoff_text = handoff.to_csv(index=False)
    assert "C:\\Users" not in handoff_text
    assert "Downloads" not in handoff_text
    assert "OneDrive" not in handoff_text

    by_id = handoff.set_index("decision_id")
    assert by_id.loc["crown_top_up_policy", "linked_gap_ids"] == "crown_top_up_values_missing"
    assert by_id.loc["crown_top_up_policy", "runtime_status"] == "policy_overlay_missing_values"
    assert by_id.loc["ped_bridge_source_history_and_re_estimation", "linked_gap_ids"] == "ped_total_vkt_bridge_missing"
    assert by_id.loc["h13_treatment", "availability_status"] == "governance_label_required"
    assert by_id.loc["h13_treatment", "linked_gap_ids"] == ""
    assert by_id.loc["h13_treatment", "dashboard_treatment"].lower().find("no value changes") >= 0
    critical = handoff[handoff["priority"].astype(str).str.lower().eq("critical")]
    assert critical["linked_gap_ids"].astype(str).str.len().gt(0).all()
    assert critical["runtime_status"].astype(str).str.len().gt(0).all()


def test_revenue_series_role_audit_makes_model_bridge_and_passthrough_roles_explicit() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    roles = pack.series_role_audit
    assert not roles.empty
    assert {
        "series_id",
        "display_name",
        "role_category",
        "forecast_role",
        "runtime_treatment",
        "canonical_row_count",
        "source_statuses",
        "bridge_statuses",
        "revenue_bases",
    }.issubset(roles.columns)
    roles_text = roles.to_csv(index=False)
    assert "C:\\Users" not in roles_text
    assert "Downloads" not in roles_text
    assert "OneDrive" not in roles_text

    by_id = roles.set_index("series_id")
    for series_id in ["ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"]:
        assert by_id.loc[series_id, "role_category"] == "direct_model_output"
        assert by_id.loc[series_id, "runtime_treatment"] == "modeled_activity_stream"
        assert by_id.loc[series_id, "revenue_bases"] == "activity"

    for series_id in ["gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"]:
        assert by_id.loc[series_id, "role_category"] == "revenue_bridge"
        assert by_id.loc[series_id, "runtime_treatment"] == "requires_governed_bridge_inputs"
        assert "bridge_required" in str(by_id.loc[series_id, "bridge_statuses"])

    assert by_id.loc["gross_lpg_revenue", "role_category"] == "pass_through_or_governed_assumption"
    assert by_id.loc["gross_cng_revenue", "role_category"] == "pass_through_or_governed_assumption"
    assert by_id.loc["tuc_net_revenue", "role_category"] == "pass_through_or_governed_assumption"
    assert by_id.loc["fed_refunds", "role_category"] == "deduction"
    assert by_id.loc["crown_top_up", "role_category"] == "policy_overlay"

    gaps = roles[roles["role_category"].eq("source_registry_gap")]
    assert not gaps.empty
    assert gaps["source_statuses"].astype(str).str.contains("unregistered_source_series").all()
    assert gaps["runtime_treatment"].eq("preserve_as_source_registry_gap").all()


def test_revenue_path_trace_status_marks_missing_release_traces_without_fabrication() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    status = pack.path_trace_status
    assert not status.empty
    assert {
        "trace_id",
        "trace_label",
        "availability_status",
        "plotted",
        "data_scope",
        "blocking_gap_id",
        "current_selection",
        "user_visible_message",
    }.issubset(status.columns)

    by_id = status.set_index("trace_id")
    required_traces = {
        "actual_benchmark",
        "selected_workbook_basis",
        "selected_mot_befu_release",
        "rolling_befu_1y",
        "aaron_schiff_model",
        "in_house_model",
    }
    assert required_traces.issubset(set(by_id.index))

    available = by_id.loc[["actual_benchmark", "selected_workbook_basis", "aaron_schiff_model", "in_house_model"]]
    assert set(available["availability_status"]) == {"available"}
    assert available["plotted"].astype(bool).all()

    missing_release = by_id.loc[["selected_mot_befu_release", "rolling_befu_1y"]]
    assert set(missing_release["availability_status"]) == {"missing"}
    assert not missing_release["plotted"].astype(bool).any()
    assert set(missing_release["blocking_gap_id"]) == {"release_value_table_missing"}
    assert set(missing_release["current_selection"]) == {"BEFU25"}
    assert missing_release["user_visible_message"].astype(str).str.contains("release-value rows", case=False).all()


def test_revenue_source_pack_intake_status_is_hash_backed_and_sanitized() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    intake = pack.intake_status
    assert not intake.empty
    assert {
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
    }.issubset(intake.columns)
    intake_text = intake.to_csv(index=False)
    assert "C:\\Users" not in intake_text
    assert "Downloads" not in intake_text
    assert "OneDrive" not in intake_text

    by_name = intake.set_index("artifact_name")
    for filename in REQUIRED_SOURCE_PACK_FILES:
        assert by_name.loc[filename, "status"] == "repo_local_hash_verified"
        assert str(by_name.loc[filename, "repo_relative_path"]).startswith("data/revenue_model_source_pack/2026_05_19/")
        assert len(str(by_name.loc[filename, "sha256"])) == 64
        assert int(by_name.loc[filename, "size_bytes"]) < 50 * 1024 * 1024

    assert by_name.loc["raw_workbook_lineage", "status"] == "verified_sha256_in_manifest"
    assert by_name.loc["raw_workbook_lineage", "sha256"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"
    for filename in ["release_values.csv", "forecast_archive.csv", "formula_lineage.csv", "quarterly_actuals.csv"]:
        assert by_name.loc[filename, "status"] == "not_vendored"
        assert not bool(by_name.loc[filename, "required_for_runtime"])
        assert bool(by_name.loc[filename, "required_for_replay"])


def test_revenue_source_pack_loader_exports_are_hash_backed() -> None:
    manifest_path = PACK_DIR / "loader_exports_manifest.json"
    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "C:\\Users" not in manifest_text
    assert "Downloads" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == "nltf-revenue-source-pack-loader-exports-v1"
    assert manifest["created_at"] == json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))["created_at"]
    assert manifest["created_at_source"] == "source_pack_manifest_created_at"
    assert manifest["determinism_policy"].startswith("No wall-clock timestamp")
    assert manifest["source_pack_raw_sha256"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"

    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    expected_counts = {
        "canonical_revenue_long.csv": len(pack.canonical_long),
        "source_pack_intake_status.csv": len(pack.intake_status),
        "path_trace_status.csv": len(pack.path_trace_status),
        "reconciliation_report.csv": len(pack.reconciliation_report),
        "source_gap_register.csv": len(pack.source_gap_register),
        "remaining_decisions_handoff.csv": len(pack.remaining_decisions_handoff),
        "series_role_audit.csv": len(pack.series_role_audit),
        "validation_issues.csv": len(pack.validation_issues),
    }
    for filename, meta in manifest["exports"].items():
        path = PACK_DIR / filename
        assert path.exists()
        assert meta["sha256"] == _sha256(path)
        assert meta["row_count"] == expected_counts[filename]


def test_revenue_source_pack_loader_exports_are_deterministic(tmp_path: Path) -> None:
    pack_copy = tmp_path / "source_pack"
    shutil.copytree(PACK_DIR, pack_copy)

    first = export_tables(pack_copy)
    first_manifest_text = (pack_copy / "loader_exports_manifest.json").read_text(encoding="utf-8")
    first_hashes = {
        filename: _sha256(pack_copy / filename)
        for filename in first["exports"]
    }

    second = export_tables(pack_copy)
    second_manifest_text = (pack_copy / "loader_exports_manifest.json").read_text(encoding="utf-8")
    second_hashes = {
        filename: _sha256(pack_copy / filename)
        for filename in second["exports"]
    }

    assert first_manifest_text == second_manifest_text
    assert first_hashes == second_hashes
    assert first["created_at"] == second["created_at"]
    assert first["determinism_policy"] == second["determinism_policy"]

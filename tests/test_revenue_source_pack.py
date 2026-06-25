from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pandas as pd

from model_dashboard.revenue_source_pack import (
    CANONICAL_REVENUE_SCHEMA_VERSION,
    OPTIONAL_SOURCE_PACK_FILES,
    REQUIRED_SOURCE_PACK_FILES,
    REVENUE_SOURCE_PACK_SCHEMA_VERSION,
    control_options,
    current_selection,
    load_revenue_source_pack,
    revenue_reconciliation_report,
    revenue_source_pack_signature,
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


def test_revenue_source_pack_signature_tracks_manifest_declared_files() -> None:
    signature_names = {Path(path).name for path, _, _ in revenue_source_pack_signature(PACK_DIR, ROOT)}

    assert {"current_selections.csv", "formula_errors.csv", "model_coefficients.csv"}.issubset(signature_names)


def test_revenue_source_pack_validation_fails_on_declared_file_hash_mismatch(tmp_path: Path) -> None:
    pack_copy = tmp_path / "source_pack"
    shutil.copytree(PACK_DIR, pack_copy)
    readme = pack_copy / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nTampered for validation test.\n", encoding="utf-8")

    pack = load_revenue_source_pack(pack_dir=pack_copy, repo_root=ROOT)

    assert pack is not None
    assert pack.validation_status == "failed"
    issues = pack.validation_issues
    hash_issues = issues[issues["check"].eq("source_pack_file_hash")]
    assert not hash_issues.empty
    assert hash_issues["message"].astype(str).str.contains("README.md").any()


def test_revenue_source_pack_canonical_long_schema_preserves_source_rows() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    frame = pack.canonical_long
    expected_rows = (
        len(pack.annual_actuals)
        + len(pack.annual_model_paths)
        + len(pack.release_values)
        + len(pack.quarterly_actuals)
        + len(pack.fed_rate_paths)
        + len(pack.ped_bridge_inputs)
        + len(pack.official_befu25_annual)
    )
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
        "release_family",
        "release_year",
        "horizon",
        "forecast_path",
        "path_status",
        "scenario_name",
        "scenario_role",
        "model_basis",
        "revenue_basis",
        "value_status",
        "source_status",
        "bridge_status",
        "source_file",
        "source_cell",
        "normalized_source_sha256",
        "source_hash_sha256",
        "distilled_hash_sha256",
    }
    assert required.issubset(frame.columns)
    assert not frame["unit"].astype(str).str.strip().eq("").any()
    assert (frame["period"].astype(str).str.match(r"^FY\d{4}$") | frame["period"].astype(str).str.match(r"^\d{4}Q[1-4]$")).all()
    assert set(frame["aggregation_sign"].dropna().unique()).issubset({-1, 0, 1})
    expected_source_hashes = {
        filename: meta["sha256"]
        for filename, meta in pack.manifest["normalized_files"].items()
        if filename in {
            "annual_actuals.csv",
            "annual_model_paths.csv",
            "release_values.csv",
            "quarterly_actuals.csv",
            "fed_rate_paths.csv",
            "ped_bridge_inputs.csv",
            "official_befu25_annual.csv",
        }
    }
    actual_source_hashes = (
        frame.groupby("source_file", dropna=False)["normalized_source_sha256"]
        .agg(lambda values: set(values.dropna().astype(str)))
        .to_dict()
    )
    assert actual_source_hashes["annual_actuals.csv"] == {expected_source_hashes["annual_actuals.csv"]}
    assert actual_source_hashes["annual_model_paths.csv"] == {expected_source_hashes["annual_model_paths.csv"]}
    assert actual_source_hashes["release_values.csv"] == {expected_source_hashes["release_values.csv"]}
    assert actual_source_hashes["quarterly_actuals.csv"] == {expected_source_hashes["quarterly_actuals.csv"]}
    assert actual_source_hashes["fed_rate_paths.csv"] == {expected_source_hashes["fed_rate_paths.csv"]}
    assert actual_source_hashes["ped_bridge_inputs.csv"] == {expected_source_hashes["ped_bridge_inputs.csv"]}
    assert actual_source_hashes["official_befu25_annual.csv"] == {expected_source_hashes["official_befu25_annual.csv"]}
    assert set(frame["path_status"].dropna().unique()).issubset(
        {
            "actual_or_benchmark",
            "selected_workbook_basis",
            "in_house_prediction_forecast",
            "aaron_schiff_prediction_forecast",
            "selected_mot_release_forecast",
            "fed_path_rate",
            "other_model_path",
        }
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


def test_quarterly_actuals_use_june_year_mapping_without_partial_year_inference() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    quarters = pack.quarterly_actuals
    gross_ped = quarters[quarters["series"].eq("Gross PED exGST")].copy()
    assert not gross_ped.empty

    fy2025 = sorted(gross_ped.loc[gross_ped["FY"].eq(2025), "quarter"].dropna().astype(str).tolist())
    assert fy2025 == ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    fy2026 = sorted(gross_ped.loc[gross_ped["FY"].eq(2026), "quarter"].dropna().astype(str).tolist())
    assert fy2026 == ["2025Q3", "2025Q4", "2026Q1"]

    canonical_fy2025 = pack.canonical_long[
        pack.canonical_long["source_file"].eq("quarterly_actuals.csv")
        & pack.canonical_long["source_series_label"].eq("Gross PED exGST")
        & pack.canonical_long["FY"].eq(2025)
    ]
    assert sorted(canonical_fy2025["period"].astype(str).tolist()) == fy2025


def test_annual_completeness_audit_keeps_fy2026_actual_to_date_separate_from_forecast() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    audit = pack.annual_completeness_audit.set_index("FY")

    assert audit.loc[2026, "expected_quarter_set"] == "2025Q3; 2025Q4; 2026Q1; 2026Q2"
    assert audit.loc[2026, "actual_quarters"] == "2025Q3; 2025Q4; 2026Q1"
    assert audit.loc[2026, "coverage_count"] == 3
    assert audit.loc[2026, "completeness_status"] == "partial_actual_to_date"
    assert audit.loc[2026, "source_cutoff"] == "2026Q1"
    assert audit.loc[2026, "chart_treatment"] == "partial_actual_marker_not_connected"
    assert audit.loc[2026, "workbook_formula_cells"] == "AZ163; BA163; BB163"
    assert audit.loc[2026, "missing_formula_cells"] == "BC163"
    assert abs(float(audit.loc[2026, "annual_actual_value"]) - 3528.410251053044) <= 1e-9
    assert audit.loc[2026, "annual_actual_source_cell"] == "R27"
    assert abs(float(audit.loc[2026, "selected_model_value"]) - 4709.942174904469) <= 1e-9
    assert audit.loc[2026, "selected_model_source_cell"] == "R26"
    assert abs(float(audit.loc[2026, "official_befu25_value"]) - 4569.88166803382) <= 1e-9
    assert audit.loc[2026, "official_befu25_status"] == "ST_FORECAST"

    assert audit.loc[2024, "expected_quarter_set"] == "2023Q3; 2023Q4; 2024Q1; 2024Q2"
    assert audit.loc[2025, "expected_quarter_set"] == "2024Q3; 2024Q4; 2025Q1; 2025Q2"
    assert audit.loc[2024, "chart_treatment"] == "complete_actual_line"
    assert audit.loc[2025, "chart_treatment"] == "complete_actual_line"
    assert audit.loc[2027, "chart_treatment"] == "forecast_path_only"


def test_rolling_befu_1y_rows_are_true_release_horizon_one_rows() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    release_rows = pack.canonical_long[
        pack.canonical_long["source_file"].eq("release_values.csv")
        & pack.canonical_long["release_family"].astype(str).str.upper().eq("BEFU")
        & pd.to_numeric(pack.canonical_long["horizon"], errors="coerce").eq(1)
    ].copy()

    assert not release_rows.empty
    assert set(pd.to_numeric(release_rows["horizon"], errors="coerce").dropna().astype(int).unique()) == {1}
    assert release_rows["source_file"].eq("release_values.csv").all()


def test_hybrid_annual_revenue_replaces_only_three_lines_and_preserves_mot_fixed_rows() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    hybrid = pack.hybrid_annual_revenue
    assert not hybrid.empty
    assert {"FY", "series_id", "row_role", "source_file", "replacement_only", "value", "residual_vs_official"}.issubset(hybrid.columns)

    replacements = hybrid[hybrid["replacement_only"].astype(bool)]
    assert set(replacements["series_id"]) == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}
    assert set(replacements["row_role"]) == {"replacement_line"}
    replacement_counts = replacements.groupby(["FY", "fed_path", "series_id"], dropna=False).size()
    assert set(replacement_counts.unique()) == {1}
    replacement_matrix = replacements.groupby(["FY", "fed_path"], dropna=False)["series_id"].agg(lambda values: set(values))
    assert replacement_matrix.map(lambda values: values == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}).all()
    non_replacements = hybrid[~hybrid["replacement_only"].astype(bool)]
    assert not set(non_replacements["series_id"]).intersection({"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"})
    replacement_sources = replacements.groupby("series_id")["source_file"].agg(lambda values: set(values))
    assert replacement_sources.loc["gross_ped_revenue"] == {"annual_model_paths.csv; fed_rate_paths.csv; ped_bridge_inputs.csv"}
    assert replacement_sources.loc["light_ruc_net_revenue"] == {"annual_model_paths.csv"}
    assert replacement_sources.loc["heavy_ruc_net_revenue"] == {"annual_model_paths.csv"}
    assert {"Current planned path", "No 2027 12c uplift"}.issubset(set(replacements["fed_path"]))
    assert replacements["formula"].astype(str).str.len().gt(0).all()

    fixed = hybrid[hybrid["row_role"].astype(str).str.startswith("fixed_mot")]
    assert not fixed.empty
    assert set(fixed["source_file"]) == {"official_befu25_annual.csv"}
    assert not set(fixed["series_id"]).intersection({"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"})

    fy = int(hybrid["FY"].min())
    rows = hybrid[hybrid["FY"].eq(fy) & hybrid["fed_path"].eq("Current planned path")].set_index("series_id")
    assert {"population_count", "ped_total_vkt", "ped_litres_per_100km", "ped_fed_rate_path"}.issubset(rows.index)
    ped_expected = rows.loc["ped_total_vkt", "value"] * rows.loc["ped_litres_per_100km", "value"] / 100.0 * rows.loc["ped_fed_rate_path", "value"]
    assert abs(rows.loc["gross_ped_revenue", "value"] - ped_expected) <= 1e-9
    gross_fed_expected = rows.loc["gross_ped_revenue", "value"] + rows.loc["gross_lpg_revenue", "value"] + rows.loc["gross_cng_revenue", "value"]
    net_fed_expected = gross_fed_expected - rows.loc["fed_refunds", "value"]
    ruc_expected = rows.loc["light_ruc_net_revenue", "value"] + rows.loc["heavy_ruc_net_revenue", "value"] + rows.loc["ruc_fixed_residual_net_revenue", "value"]
    total_expected = net_fed_expected + ruc_expected + rows.loc["net_mvr_revenue", "value"] + rows.loc["tuc_net_revenue", "value"]

    assert abs(rows.loc["gross_fed_revenue", "value"] - gross_fed_expected) <= 1e-9
    assert abs(rows.loc["net_fed_revenue", "value"] - net_fed_expected) <= 1e-9
    assert abs(rows.loc["total_ruc_net_revenue", "value"] - ruc_expected) <= 1e-9
    assert abs(rows.loc["total_nltf_net_revenue", "value"] - total_expected) <= 1e-9
    assert pd.notna(rows.loc["total_nltf_net_revenue", "official_value"])
    assert abs(
        rows.loc["total_nltf_net_revenue", "residual_vs_official"]
        - (rows.loc["total_nltf_net_revenue", "value"] - rows.loc["total_nltf_net_revenue", "official_value"])
    ) <= 1e-9

    fy2031 = hybrid[hybrid["FY"].eq(2031) & hybrid["series_id"].eq("gross_ped_revenue")].set_index("fed_path")
    assert fy2031.loc["Current planned path", "value"] > fy2031.loc["No 2027 12c uplift", "value"]


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
    assert {"revenue_basis_alias", "series_registry_gap"}.issubset(set(issues["check"]))
    assert "unresolved_critical_decisions" not in set(issues["check"])
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
    assert by_id.loc["release_value_table_missing", "availability_status"] == "available"
    assert by_id.loc["release_value_table_missing", "runtime_treatment"] == "release_values_available"
    assert by_id.loc["fed_path_scenario_values_missing", "availability_status"] == "available"
    assert by_id.loc["fed_path_scenario_values_missing", "runtime_treatment"] == "fed_path_values_available"
    assert by_id.loc["crown_top_up_values_missing", "availability_status"] == "available"
    assert by_id.loc["crown_top_up_values_missing", "runtime_treatment"] == "excluded_by_selection"
    assert by_id.loc["quarterly_source_pack_missing", "availability_status"] == "available"
    assert by_id.loc["quarterly_source_pack_missing", "runtime_treatment"] == "quarterly_available"
    assert by_id.loc["ped_total_vkt_bridge_missing", "availability_status"] == "available"
    assert by_id.loc["ped_total_vkt_bridge_missing", "runtime_treatment"] == "bridge_rows_available"
    assert "ped_bridge_inputs.csv" in by_id.loc["ped_total_vkt_bridge_missing", "user_visible_message"]
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
    assert by_id.loc["future_nominal_ped_fed_rates_by_scenario", "linked_gap_ids"] == "fed_path_scenario_values_missing; ped_total_vkt_bridge_missing"
    assert by_id.loc["future_nominal_ped_fed_rates_by_scenario", "runtime_status"] == "fed_rate_path_and_total_vkt_source_backed"
    assert "fed_rate_paths.csv" in by_id.loc["future_nominal_ped_fed_rates_by_scenario", "linked_artifacts"]
    assert "ped_bridge_inputs.csv" in by_id.loc["future_nominal_ped_fed_rates_by_scenario", "linked_artifacts"]
    assert by_id.loc["ped_bridge_source_history_and_re_estimation", "linked_gap_ids"] == "ped_total_vkt_bridge_missing"
    assert by_id.loc["ped_bridge_source_history_and_re_estimation", "runtime_status"] == "bridge_rows_available"
    assert by_id.loc["h13_treatment", "availability_status"] == "label_applied"
    assert by_id.loc["h13_treatment", "runtime_status"] == "label_applied"
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
    for series_id in ["population_count", "ped_total_vkt", "ped_litres_per_100km", "ped_source_backed_litres"]:
        assert by_id.loc[series_id, "role_category"] == "revenue_bridge"
        assert by_id.loc[series_id, "runtime_treatment"] == "requires_governed_bridge_inputs"

    gaps = roles[roles["role_category"].eq("source_registry_gap")]
    assert not gaps.empty
    assert gaps["source_statuses"].astype(str).str.contains("unregistered_source_series|registered_alias", regex=True).all()
    assert gaps["runtime_treatment"].eq("preserve_as_source_registry_gap").all()


def test_revenue_path_trace_status_marks_vendored_release_traces_available_without_fabrication() -> None:
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

    release = by_id.loc[["selected_mot_befu_release", "rolling_befu_1y"]]
    assert set(release["availability_status"]) == {"available"}
    assert release["plotted"].astype(bool).all()
    assert set(release["blocking_gap_id"]) == {""}
    assert set(release["current_selection"]) == {"BEFU25"}
    assert release["user_visible_message"].astype(str).str.contains("release_values.csv|one-year-ahead", case=False, regex=True).all()


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
    for filename in REQUIRED_SOURCE_PACK_FILES + OPTIONAL_SOURCE_PACK_FILES:
        assert by_name.loc[filename, "status"] == "repo_local_hash_verified"
        assert str(by_name.loc[filename, "repo_relative_path"]).startswith("data/revenue_model_source_pack/2026_05_19/")
        assert len(str(by_name.loc[filename, "sha256"])) == 64
        assert int(by_name.loc[filename, "size_bytes"]) < 50 * 1024 * 1024
        assert bool(by_name.loc[filename, "required_for_runtime"])

    assert by_name.loc["raw_workbook_lineage", "status"] == "verified_sha256_in_manifest"
    assert by_name.loc["raw_workbook_lineage", "sha256"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"
    assert by_name.loc["formula_lineage.csv", "status"] == "not_vendored"
    assert not bool(by_name.loc["formula_lineage.csv", "required_for_runtime"])
    assert bool(by_name.loc["formula_lineage.csv", "required_for_replay"])


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
    canonical_export = pd.read_csv(PACK_DIR / "canonical_revenue_long.csv")
    assert "normalized_source_sha256" in canonical_export.columns
    for source_file, expected_hash in {
        filename: meta["sha256"]
        for filename, meta in pack.manifest["normalized_files"].items()
        if filename in {
            "annual_actuals.csv",
            "annual_model_paths.csv",
            "release_values.csv",
            "quarterly_actuals.csv",
            "fed_rate_paths.csv",
            "ped_bridge_inputs.csv",
            "official_befu25_annual.csv",
        }
    }.items():
        hashes = set(
            canonical_export.loc[
                canonical_export["source_file"].eq(source_file),
                "normalized_source_sha256",
            ]
            .dropna()
            .astype(str)
        )
        assert hashes == {expected_hash}
    expected_counts = {
        "canonical_revenue_long.csv": len(pack.canonical_long),
        "source_pack_intake_status.csv": len(pack.intake_status),
        "path_trace_status.csv": len(pack.path_trace_status),
        "reconciliation_report.csv": len(pack.reconciliation_report),
        "source_gap_register.csv": len(pack.source_gap_register),
        "remaining_decisions_handoff.csv": len(pack.remaining_decisions_handoff),
        "series_role_audit.csv": len(pack.series_role_audit),
        "hybrid_annual_revenue.csv": len(pack.hybrid_annual_revenue),
        "annual_completeness_audit.csv": len(pack.annual_completeness_audit),
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

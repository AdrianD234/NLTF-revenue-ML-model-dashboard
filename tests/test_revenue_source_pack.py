from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from model_dashboard.revenue_source_pack import (
    CANONICAL_REVENUE_SCHEMA_VERSION,
    REQUIRED_SOURCE_PACK_FILES,
    REVENUE_SOURCE_PACK_SCHEMA_VERSION,
    load_revenue_source_pack,
)


ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "revenue_model_source_pack" / "2026_05_19"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def test_revenue_source_pack_validation_is_warning_not_error_for_known_source_gaps() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    assert pack.validation_status == "warning"
    issues = pack.validation_issues
    assert not issues.empty
    assert "error" not in set(issues["severity"])
    assert {"revenue_basis_alias", "series_registry_gap", "unresolved_critical_decisions"}.issubset(set(issues["check"]))
    assert "front_end_config" not in set(issues["check"])


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


def test_revenue_source_pack_loader_exports_are_hash_backed() -> None:
    manifest_path = PACK_DIR / "loader_exports_manifest.json"
    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert "C:\\Users" not in manifest_text
    assert "Downloads" not in manifest_text
    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == "nltf-revenue-source-pack-loader-exports-v1"
    assert manifest["source_pack_raw_sha256"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"

    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    expected_counts = {
        "canonical_revenue_long.csv": len(pack.canonical_long),
        "reconciliation_report.csv": len(pack.reconciliation_report),
        "source_gap_register.csv": len(pack.source_gap_register),
        "validation_issues.csv": len(pack.validation_issues),
    }
    for filename, meta in manifest["exports"].items():
        path = PACK_DIR / filename
        assert path.exists()
        assert meta["sha256"] == _sha256(path)
        assert meta["row_count"] == expected_counts[filename]

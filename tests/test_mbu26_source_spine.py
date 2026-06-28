from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SPINE_DIR = ROOT / "data" / "revenue_model_source_pack" / "mbu26_annual_spine"
RUNTIME_DIR = ROOT / "data" / "current_revenue_outlook"
WORKBOOK_SHA = "9aaff21f72c0a10cfa972a29d3c4f716495c79cbd72fc28e8008a65558454e12"


def test_mbu26_source_spine_manifest_is_hash_backed_and_repo_local() -> None:
    manifest_path = SPINE_DIR / "manifest.json"
    assert manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    for forbidden in ["C:\\Users", "Downloads", "OneDrive", "annual_model_paths", "selected_dashboard", "Schiff"]:
        assert forbidden not in manifest_text

    manifest = json.loads(manifest_text)
    assert manifest["schema_version"] == "nltf-revenue-mbu26-annual-spine-v1"
    assert manifest["source_release"] == "MBU26"
    assert manifest["repo_relative_output_dir"] == "data/revenue_model_source_pack/mbu26_annual_spine"
    assert manifest["workbook"]["basename"] == "Revenue forecast error, annual view from BEFU 2013-25.xlsx"
    assert manifest["workbook"]["sha256"] == WORKBOOK_SHA
    assert manifest["workbook"]["sheet"] == "MBU26"
    assert "MBU26 worksheet only" in manifest["source_policy"]
    assert set(manifest["normalized_files"]).issuperset(
        {
            "mbu26_annual_spine.csv",
            "mbu26_formula_audit.csv",
            "mbu26_official_annual.csv",
            "row_reconciliation.csv",
            "series_alias_audit.csv",
            "series_trace_contract.csv",
            "trace_source_contract.csv",
            "path_trace_status.csv",
        }
    )
    for filename, metadata in manifest["normalized_files"].items():
        path = SPINE_DIR / filename
        assert path.exists()
        assert metadata["sha256"]
        assert path.stat().st_size == metadata["size_bytes"]
        assert path.stat().st_size < 50 * 1024 * 1024


def test_mbu26_spine_extracts_required_rows_statuses_and_roles() -> None:
    spine = pd.read_csv(SPINE_DIR / "mbu26_annual_spine.csv")
    required_rows = {
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        45,
        46,
        47,
        48,
        49,
        50,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        63,
        66,
        67,
        68,
        69,
        70,
    }
    assert required_rows.issubset(set(pd.to_numeric(spine["source_row"], errors="coerce").dropna().astype(int)))
    assert set(spine["period_status"].dropna().unique()) == {"ACTUAL", "ST_FORECAST", "LT_FORECAST"}
    assert set(spine["row_role"].dropna().unique()).issubset({"leaf", "aggregate", "deduction", "bridge_input"})
    assert spine.loc[pd.to_numeric(spine["FY"], errors="coerce").gt(2025), "period_status"].ne("ACTUAL").all()
    assert not spine["source_cell"].fillna("").astype(str).eq("").any()
    missing = spine[spine["value"].isna()]
    assert set(missing["series_id"].dropna().unique()) <= {"light_petrol_vkt", "ped_vkt_per_capita"}
    assert set(pd.to_numeric(missing["FY"], errors="coerce").dropna().astype(int)) <= {2001, 2002}
    row17 = spine[pd.to_numeric(spine["source_row"], errors="coerce").eq(17)]
    assert set(row17["series_id"].dropna().astype(str).unique()) == {"ped_vkt_per_capita"}
    assert set(row17["source_series_id"].dropna().astype(str).unique()) == {"light_petrol_vkt_per_capita"}
    assert set(row17["display_name"].dropna().astype(str).unique()) == {"PED VKT per capita"}
    assert set(row17["source_label"].dropna().astype(str).unique()) == {"Light petrol VKT per capita (km)"}


def test_mbu26_series_alias_audit_documents_runtime_canonicalization() -> None:
    alias = pd.read_csv(SPINE_DIR / "series_alias_audit.csv")
    required = {
        "source_label",
        "source_series_id",
        "runtime_series_id",
        "dashboard_label",
        "unit",
        "source_row",
        "source_cell",
        "alias_reason",
        "status",
    }
    assert required.issubset(alias.columns)
    ped = alias[alias["source_series_id"].astype(str).eq("light_petrol_vkt_per_capita")].iloc[0]
    assert ped["runtime_series_id"] == "ped_vkt_per_capita"
    assert ped["dashboard_label"] == "PED VKT per capita"
    assert ped["source_row"] == 17
    assert str(ped["source_cell"]).startswith("C17:")
    assert ped["status"] == "canonical_mapping"
    assert {
        "gross_ped_revenue",
        "total_ruc_net_revenue",
        "coo_revenue",
        "mvr_revenue_net_admin_coo",
        "net_mvr_revenue",
        "total_nltf_net_revenue",
    }.issubset(set(alias["runtime_series_id"].astype(str)))


def test_mbu26_formula_audit_and_row_reconciliation_are_explicit() -> None:
    formula = pd.read_csv(SPINE_DIR / "mbu26_formula_audit.csv")
    row_reconciliation = pd.read_csv(SPINE_DIR / "row_reconciliation.csv")
    pd.testing.assert_frame_equal(formula, row_reconciliation)
    assert {"reconciled", "residual_reported"}.issuperset(set(formula["status"].dropna().unique()))
    assert "missing_inputs" not in set(formula["status"].dropna().unique())

    gross_ruc = formula[formula["output_series_id"].eq("gross_ruc_revenue")]
    assert not gross_ruc.empty
    assert gross_ruc["formula"].str.contains("ruc_refunds", regex=False).all()
    residuals = pd.to_numeric(formula["residual_abs"], errors="coerce").fillna(0)
    assert residuals.max() < 1.0

    subtotal = formula[formula["output_series_id"].eq("total_fed_ruc_net_revenue")]
    assert not subtotal.empty
    assert subtotal["formula"].eq("net_fed_revenue + total_ruc_net_revenue").all()


def test_current_runtime_uses_only_allowed_mbu26_trace_contract() -> None:
    chart = pd.read_csv(RUNTIME_DIR / "revenue_chart_rows.csv")
    audit = pd.read_csv(RUNTIME_DIR / "runtime_trace_audit.csv")
    bridge = pd.read_csv(RUNTIME_DIR / "revenue_bridge_components.csv")

    allowed = {"Actual", "MBU26 official", "Current finalist Base case", "Current finalist High population/comparison"}
    displayed = chart[chart["time_grain"].astype(str).eq("june_year")]
    assert set(displayed["trace_name"].dropna().unique()) == allowed
    assert set(displayed["trace_type"].dropna().unique()) == {
        "Actual",
        "MBU26 official",
        "current finalist base",
        "current finalist comparison",
    }
    assert displayed[
        displayed["row_type"].astype(str).eq("historical_actual")
        & pd.to_numeric(displayed["june_year"], errors="coerce").gt(2025)
    ].empty
    assert not displayed["source_cell"].fillna("").astype(str).eq("").any()

    fy2026 = displayed[displayed["period"].astype(str).eq("FY2026")]
    current_fy2026 = fy2026[fy2026["trace_role"].astype(str).eq("in_house_current_finalist")]
    assert set(current_fy2026["actual_quarters"].dropna().astype(str)) == {"2025Q3; 2025Q4"}
    assert set(current_fy2026["forecast_quarters"].dropna().astype(str)) == {"2026Q1; 2026Q2"}

    replacements = bridge[bridge["component_type"].astype(str).eq("replacement_line")]
    assert set(replacements["stream"].dropna().unique()) == {
        "gross_ped_revenue",
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue",
    }
    assert {"trace_type", "source_cell", "formula", "replacement_only"}.issubset(audit.columns)

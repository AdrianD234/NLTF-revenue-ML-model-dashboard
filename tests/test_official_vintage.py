"""Governed contracts for the generic official-vintage framework (BEFU26)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard import official_vintage as ov
from model_dashboard.mbu26_source_spine import ROW_DEFINITIONS, load_mbu26_annual_spine

ROOT = Path(__file__).resolve().parents[1]

BEFU26_WORKBOOK_SHA = "7d6e5b19119ca8b5272ca2205c0735719033d82484ce674cfb595e6f45d085ff"
MBU26_WORKBOOK_SHA = "9aaff21f72c0a10cfa972a29d3c4f716495c79cbd72fc28e8008a65558454e12"

# Published totals plus representative activity/revenue leaves so a shifted
# row mapping cannot pass by matching only the total.
BEFU26_SENTINELS = (
    ("total_nltf_net_revenue", 2026, 4493.65132567772),
    ("total_nltf_net_revenue", 2030, 6442.98776042894),
    ("total_nltf_net_revenue", 2050, 12910.4837029366),
    ("total_nltf_net_revenue", 2055, 14500.4528554998),
    ("light_ruc_net_km", 2026, 12707.9889982716),
    ("ped_volume", 2040, 1920.22768771668),
    ("tuc_gtk", 2026, 8224343155.99),
    ("light_ruc_net_revenue", 2055, 789.484160803912),
    ("gross_ruc_revenue", 2040, 6434.96355570389),
    ("net_fed_revenue", 2026, 2007.89765301342),
    ("gross_mvr_revenue", 2040, 517.956301022337),
    ("tuc_net_revenue", 2026, 17.4060774864124),
)


@pytest.fixture(scope="module")
def registry() -> dict:
    return ov.load_official_vintage_registry(ROOT)


@pytest.fixture(scope="module")
def befu26_pack() -> ov.OfficialVintagePack:
    pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
    assert pack is not None, "BEFU26 pack is not materialized"
    return pack


class TestRegistry:
    def test_registry_is_valid_and_committed(self, registry):
        assert registry["schema_version"] == ov.OFFICIAL_VINTAGE_REGISTRY_SCHEMA_VERSION
        assert ov.validate_official_vintage_registry(registry) == []

    def test_prebu26_is_latest_comparator_and_befu26_remains_bridge(self):
        assert ov.latest_official_vintage_id(ROOT) == "PREBU26"
        assert ov.default_comparator_vintage_id(ROOT) == "PREBU26"
        assert ov.default_bridge_vintage_id(ROOT) == "BEFU26"
        assert ov.default_long_run_shape_vintage_id(ROOT) == "PREBU26"

    def test_mbu26_remains_registered_and_selectable(self, registry):
        entry = ov.official_vintage_entry("MBU26", registry=registry)
        assert entry["available"] is True
        assert entry["is_latest"] is False
        assert entry["is_default_comparator"] is False
        assert entry["is_default_bridge_vintage"] is False
        assert entry["status"] == "superseded_official_vintage_available_for_comparison"
        assert entry["workbook_sha256"] == MBU26_WORKBOOK_SHA
        choices = dict(ov.official_vintage_choices(ROOT))
        assert set(choices) == {"BEFU26", "MBU26", "PREBU26"}
        # Default comparator is listed first for the front-end selector.
        assert ov.official_vintage_choices(ROOT)[0][0] == "PREBU26"

    def test_befu26_entry_pins_workbook_and_horizons(self, registry):
        entry = ov.official_vintage_entry("BEFU26", registry=registry)
        assert entry["workbook_sha256"] == BEFU26_WORKBOOK_SHA
        assert entry["source_workbook"] == "references/BEFU26 revenue forecast.xlsx"
        assert entry["source_sheet"] == "Baseline"
        assert (entry["actual_start_fy"], entry["actual_end_fy"]) == (2001, 2025)
        assert (entry["short_forecast_start_fy"], entry["short_forecast_end_fy"]) == (2026, 2030)
        assert (entry["long_forecast_start_fy"], entry["long_forecast_end_fy"]) == (2031, 2055)
        assert entry["source_horizon_fy"] == 2055

    def test_vendored_workbook_matches_registered_hash(self, registry):
        entry = ov.official_vintage_entry("BEFU26", registry=registry)
        workbook = ROOT / entry["source_workbook"]
        assert workbook.exists(), "governed BEFU26 workbook must be vendored"
        assert ov.sha256(workbook) == BEFU26_WORKBOOK_SHA

    def test_selection_resolution(self):
        assert ov.resolve_official_vintage_selection(None, ROOT) == "PREBU26"
        assert ov.resolve_official_vintage_selection("MBU26", ROOT) == "MBU26"
        with pytest.raises(ov.OfficialVintageError):
            ov.resolve_official_vintage_selection("PREFU99", ROOT)


class TestBefu26Pack:
    def test_manifest_hygiene_and_hashes(self, befu26_pack):
        manifest_text = json.dumps(befu26_pack.manifest)
        for banned in ("C:\\Users", "Downloads", "OneDrive"):
            assert banned not in manifest_text
        workbook = befu26_pack.manifest["workbook"]
        assert workbook["sha256"] == BEFU26_WORKBOOK_SHA
        assert workbook["sheet"] == "Baseline"
        assert befu26_pack.manifest["schema_version"] == ov.OFFICIAL_VINTAGE_PACK_SCHEMA_VERSION
        assert befu26_pack.manifest["sentinels_validated"] == len(BEFU26_SENTINELS)
        assert len(befu26_pack.manifest["normalized_files"]) == 16

    def test_spine_shape_and_period_statuses(self, befu26_pack):
        spine = befu26_pack.annual_spine
        assert len(spine) == 39 * 55
        assert set(spine["period_status"]) == {"ACTUAL", "ST_FORECAST", "LT_FORECAST"}
        actual_years = spine.loc[spine["period_status"] == "ACTUAL", "FY"]
        assert int(actual_years.max()) == 2025
        assert sorted(spine["FY"].unique()) == list(range(2001, 2056))
        assert not spine.duplicated(subset=["series_id", "FY"]).any()
        assert set(spine["source_kind"]) == {"official_source_row"}
        assert set(spine["source_release"]) == {"BEFU26"}

    def test_only_permitted_missing_values(self, befu26_pack):
        spine = befu26_pack.annual_spine.copy()
        values = pd.to_numeric(spine["value"], errors="coerce")
        missing = spine.loc[values.isna(), ["series_id", "FY"]]
        observed = {(row.series_id, int(row.FY)) for row in missing.itertuples()}
        allowed = {
            ("light_petrol_vkt", 2001),
            ("light_petrol_vkt", 2002),
            ("ped_vkt_per_capita", 2001),
            ("ped_vkt_per_capita", 2002),
        }
        assert observed == allowed

    def test_sentinel_values_match_workbook(self, befu26_pack):
        spine = befu26_pack.annual_spine
        values = {
            (str(row.series_id), int(row.FY)): float(row.value)
            for row in spine.itertuples()
            if pd.notna(pd.to_numeric(row.value, errors="coerce"))
        }
        for series_id, fy, expected in BEFU26_SENTINELS:
            assert math.isclose(values[(series_id, fy)], expected, rel_tol=1e-12, abs_tol=1e-9), (
                series_id,
                fy,
            )

    def test_formula_audit_reports_published_residual_without_absorbing_it(self, befu26_pack):
        audit = befu26_pack.formula_audit
        assert set(audit["status"]) <= {"reconciled", "residual_reported"}
        assert not audit["status"].eq("missing_inputs").any()
        residuals = audit[audit["status"] == "residual_reported"]
        # The BEFU26 published source carries a gross-RUC closure residual over
        # FY2027-FY2030 (same defect family as the known MBU26 FY2027 residual).
        # It must stay visible as a published-source residual, never corrected.
        assert set(residuals["output_series_id"]) == {"gross_ruc_revenue"}
        assert sorted(residuals["FY"].astype(int)) == [2027, 2028, 2029, 2030]
        assert math.isclose(
            float(residuals.loc[residuals["FY"].astype(int) == 2027, "residual"].iloc[0]),
            0.627012,
            abs_tol=5e-6,
        )
        assert pd.to_numeric(audit["residual_abs"], errors="coerce").max() < 1.0

    def test_row_reconciliation_matches_formula_audit(self, befu26_pack):
        pd.testing.assert_frame_equal(befu26_pack.row_reconciliation, befu26_pack.formula_audit)

    def test_official_annual_includes_derived_subtotal(self, befu26_pack):
        official = befu26_pack.official_annual
        assert len(official) == 40 * 55
        subtotal = official[official["series_id"] == "total_fed_ruc_net_revenue"]
        assert len(subtotal) == 55
        assert set(subtotal["source_kind"]) == {"official_formula_derived_dashboard_subtotal"}

    def test_trace_contracts_name_befu26(self, befu26_pack):
        trace_names = set(befu26_pack.trace_source_contract["trace_name"])
        assert trace_names == {
            "Actual",
            "BEFU26 official",
            "Current finalist Base case",
            "Current finalist High population/comparison",
        }
        status = befu26_pack.path_trace_status
        assert "befu26_official" in set(status["trace_id"])
        assert set(befu26_pack.series_trace_contract["availability_status"]) == {
            "befu26_current_runtime_available"
        }


class TestCrossVintage:
    def test_mbu26_loads_through_generic_loader_and_matches_legacy(self):
        generic = ov.load_official_vintage("MBU26", repo_root=ROOT)
        legacy = load_mbu26_annual_spine(repo_root=ROOT)
        assert generic is not None and legacy is not None
        pd.testing.assert_frame_equal(generic.annual_spine, legacy.annual_spine)
        pd.testing.assert_frame_equal(generic.official_annual, legacy.official_annual)
        assert generic.source_horizon_fy == 2055

    def test_pack_schemas_are_column_identical_across_vintages(self, befu26_pack):
        mbu = ov.load_official_vintage("MBU26", repo_root=ROOT)
        assert list(befu26_pack.annual_spine.columns) == list(mbu.annual_spine.columns)
        assert list(befu26_pack.official_annual.columns) == list(mbu.official_annual.columns)
        assert list(befu26_pack.formula_audit.columns) == list(mbu.formula_audit.columns)

    def test_canonical_definitions_match_legacy_row_definitions(self):
        assert len(ov.CANONICAL_SERIES_DEFINITIONS) == len(ROW_DEFINITIONS)
        for canonical, legacy in zip(ov.CANONICAL_SERIES_DEFINITIONS, ROW_DEFINITIONS):
            assert canonical["series_id"] == legacy["series_id"]
            assert canonical["display_name"] == legacy["display_name"]
            assert canonical["section"] == legacy["section"]
            assert canonical["unit"] == legacy["unit"]
            assert canonical["metric_type"] == legacy["metric_type"]
            assert canonical["row_role"] == legacy["row_role"]
            assert canonical.get("source_series_id", canonical["series_id"]) == legacy.get(
                "source_series_id", legacy["series_id"]
            )

    def test_befu26_values_differ_from_mbu26_in_forecast_years(self, befu26_pack):
        """Guards against accidentally re-ingesting the MBU26 sheet as BEFU26."""
        mbu = ov.load_official_vintage("MBU26", repo_root=ROOT)

        def total(pack, fy):
            frame = pack.annual_spine
            row = frame[
                (frame["series_id"] == "total_nltf_net_revenue") & (frame["FY"] == fy)
            ]
            return float(pd.to_numeric(row["value"], errors="coerce").iloc[0])

        assert total(befu26_pack, 2030) != pytest.approx(total(mbu, 2030))


class TestGenericRuntimeIndependence:
    def test_official_vintage_module_bans_mbu26_constants(self):
        source = (ROOT / "model_dashboard" / "official_vintage.py").read_text(encoding="utf-8")
        for banned in ("MBU26_SOURCE_PACK_DIR", "MBU26_SHEET_NAME", "MBU26_RELEASE_ROUND"):
            assert banned not in source, (
                f"generic runtime must not depend on {banned}; reach the legacy pack "
                "through its registry entry instead"
            )

    def test_materializer_cli_bans_mbu26_constants(self):
        source = (ROOT / "scripts" / "materialize_official_vintage.py").read_text(encoding="utf-8")
        for banned in ("MBU26_SOURCE_PACK_DIR", "MBU26_SHEET_NAME", "MBU26_RELEASE_ROUND"):
            assert banned not in source

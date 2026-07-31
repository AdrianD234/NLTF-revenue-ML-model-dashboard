"""The two vintage roles must be independently selectable AND safe.

The framework advertises that the official comparator vintage and the
bridge-assumption vintage are separate. That claim is only worth anything if
switching one leaves the other's outputs untouched, and if a pack built on one
bridge is never re-bridged at runtime on another. These tests build the full
2x2 and assert both halves.

Building four runtime packs is not cheap, so the matrix is a module-scoped
fixture built once and shared.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard import official_vintage as ov
from model_dashboard.rate_paths import rate_paths_frame
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    build_current_revenue_outlook_runtime_pack,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACK = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
COMBINATIONS = (
    ("BEFU26", "BEFU26"),
    ("MBU26", "BEFU26"),
    ("BEFU26", "MBU26"),
    ("MBU26", "MBU26"),
)
CURRENT_SCENARIOS = ("current_basecase", "current_comparison_1")


@pytest.fixture(scope="module")
def matrix(tmp_path_factory) -> dict[tuple[str, str], dict[str, object]]:
    base = tmp_path_factory.mktemp("vintage_matrix")
    built: dict[tuple[str, str], dict[str, object]] = {}
    for comparator, bridge in COMBINATIONS:
        staged = base / f"{comparator}_{bridge}"
        shutil.copytree(SOURCE_PACK, staged)
        pack = build_current_revenue_outlook_runtime_pack(
            repo_root=ROOT,
            output_dir=staged,
            engine="ensemble",
            official_comparator_vintage_id=comparator,
            bridge_assumption_vintage_id=bridge,
        )
        built[(comparator, bridge)] = {
            "pack": pack,
            "dir": staged,
            "manifest": json.loads((staged / "manifest.json").read_text(encoding="utf-8")),
            "chart_rows": pack.revenue_chart_rows,
        }
    return built


def _current_rows(chart_rows: pd.DataFrame) -> pd.DataFrame:
    rows = chart_rows[
        chart_rows["scenario_name"].astype(str).isin(CURRENT_SCENARIOS)
        & chart_rows["time_grain"].astype(str).eq("june_year")
    ].copy()
    return rows.sort_values(["scenario_name", "series_id", "june_year"]).reset_index(drop=True)


def _values(chart_rows: pd.DataFrame, scenario: str) -> dict[tuple[str, int], float]:
    rows = chart_rows[
        chart_rows["scenario_name"].astype(str).eq(scenario)
        & chart_rows["time_grain"].astype(str).eq("june_year")
    ]
    return {
        (str(row.series_id), int(float(row.june_year))): float(value)
        for row in rows.itertuples()
        if pd.notna(value := pd.to_numeric(pd.Series([row.value]), errors="coerce").iloc[0])
    }


class TestManifestRecordsBothRoles:
    @pytest.mark.parametrize("comparator,bridge", COMBINATIONS)
    def test_each_combination_records_its_own_roles(self, matrix, comparator, bridge):
        block = matrix[(comparator, bridge)]["manifest"]["official_vintages"]
        assert block["official_comparator_vintage_id"] == comparator
        assert block["bridge_assumption_vintage_id"] == bridge

    @pytest.mark.parametrize("comparator,bridge", COMBINATIONS)
    def test_pack_manifest_is_authoritative_over_the_registry_default(
        self, matrix, comparator, bridge
    ):
        """The whole point: a built pack's bridge outranks the live default."""
        manifest = matrix[(comparator, bridge)]["manifest"]
        assert ov.bridge_vintage_id_from_manifest(manifest, ROOT) == bridge
        assert ov.comparator_vintage_id_from_manifest(manifest, ROOT) == comparator
        # The registry default is BEFU26; the MBU26-bridge packs must not
        # resolve to it.
        if bridge != ov.default_bridge_vintage_id(ROOT):
            assert ov.bridge_vintage_id_from_manifest(manifest, ROOT) != ov.default_bridge_vintage_id(ROOT)


class TestComparatorSwitchLeavesTheBridgeSideAlone:
    @pytest.mark.parametrize("bridge", ["BEFU26", "MBU26"])
    def test_current_rows_are_identical_across_comparators(self, matrix, bridge):
        left = _current_rows(matrix[("BEFU26", bridge)]["chart_rows"])
        right = _current_rows(matrix[("MBU26", bridge)]["chart_rows"])
        pd.testing.assert_frame_equal(left, right)

    @pytest.mark.parametrize("bridge", ["BEFU26", "MBU26"])
    def test_actual_line_is_identical_across_comparators(self, matrix, bridge):
        def actual(key):
            rows = matrix[key]["chart_rows"]
            sel = rows[
                rows["trace_name"].astype(str).eq("Actual")
                & rows["time_grain"].astype(str).eq("june_year")
            ]
            return sel.sort_values(["series_id", "june_year"])["value"].reset_index(drop=True)

        pd.testing.assert_series_equal(
            actual(("BEFU26", bridge)), actual(("MBU26", bridge))
        )

    @pytest.mark.parametrize("bridge", ["BEFU26", "MBU26"])
    def test_rate_paths_follow_the_bridge_not_the_comparator(self, matrix, bridge):
        left = rate_paths_frame(
            ROOT, matrix[("BEFU26", bridge)]["chart_rows"], bridge_vintage_id=bridge
        )
        right = rate_paths_frame(
            ROOT, matrix[("MBU26", bridge)]["chart_rows"], bridge_vintage_id=bridge
        )
        pd.testing.assert_frame_equal(left, right)


class TestBridgeSwitchLeavesTheModelAlone:
    @pytest.mark.parametrize("comparator", ["BEFU26", "MBU26"])
    def test_raw_quarterly_activity_is_unchanged_across_bridges(self, matrix, comparator):
        """Bridge assumptions turn activity into revenue; they never move it."""

        def quarterly(key):
            rows = matrix[key]["chart_rows"]
            sel = rows[
                rows["time_grain"].astype(str).eq("quarterly")
                & rows["scenario_name"].astype(str).isin(CURRENT_SCENARIOS)
            ]
            return (
                sel.sort_values(["scenario_name", "series_id", "period"])["value"]
                .reset_index(drop=True)
            )

        pd.testing.assert_series_equal(
            quarterly((comparator, "BEFU26")), quarterly((comparator, "MBU26"))
        )

    @pytest.mark.parametrize("comparator", ["BEFU26", "MBU26"])
    def test_scenario_inputs_and_fitted_state_hashes_are_unchanged(self, matrix, comparator):
        left = matrix[(comparator, "BEFU26")]["manifest"]
        right = matrix[(comparator, "MBU26")]["manifest"]

        def inputs_without_output_path(manifest: dict) -> dict:
            # The pack's own output directory differs per temp build; every
            # hash-bearing field must not.
            block = dict(manifest["scenario_inputs"])
            block.pop("repo_relative_output_dir", None)
            return block

        assert inputs_without_output_path(left) == inputs_without_output_path(right)
        assert left["source_hashes"]["model_input_history"] == right["source_hashes"]["model_input_history"]
        assert left["source_hashes"]["workbooks"] == right["source_hashes"]["workbooks"]
        assert left["scenario_roles"] == right["scenario_roles"]

    @pytest.mark.parametrize("comparator", ["BEFU26", "MBU26"])
    def test_only_bridge_derived_revenue_moves(self, matrix, comparator):
        befu = _values(matrix[(comparator, "BEFU26")]["chart_rows"], "current_basecase")
        mbu = _values(matrix[(comparator, "MBU26")]["chart_rows"], "current_basecase")
        moved = {
            key for key in set(befu) & set(mbu) if befu[key] != mbu[key]
        }
        assert moved, "changing the bridge vintage must change something"
        # Pure activity series are model output and must not move.
        activity_only = {"light_ruc_net_km", "heavy_ruc_net_km", "ped_vkt_per_capita"}
        moved_activity = {
            key for key in moved if key[0] in activity_only and key[1] > 2025
        }
        assert moved_activity == set(), (
            f"bridge switch moved raw activity series: {sorted(moved_activity)[:5]}"
        )


class TestIdentitiesCloseInEveryCombination:
    @pytest.mark.parametrize("comparator,bridge", COMBINATIONS)
    def test_ruc_fed_and_nltf_identities_close(self, matrix, comparator, bridge):
        line = pd.read_csv(
            matrix[(comparator, bridge)]["dir"] / "revenue_line_reconciliation.csv",
            low_memory=False,
        )
        current = line[line["source_path"].astype(str).eq("Current finalist Base case")]
        wide = current.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first")
        classes = [
            "light_ruc_net_revenue",
            "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue",
            "heavy_ruc_net_revenue",
            "heavy_bev_ruc_net_revenue",
        ]
        for fy in (2026, 2028, 2030):
            ruc = wide.loc[fy, "total_ruc_net_revenue"] - (
                sum(wide.loc[fy, series] for series in classes) - wide.loc[fy, "ruc_admin_revenue"]
            )
            fed = wide.loc[fy, "net_fed_revenue"] - (
                wide.loc[fy, "gross_fed_revenue"] - wide.loc[fy, "fed_refunds"]
            )
            nltf = wide.loc[fy, "total_nltf_net_revenue"] - (
                wide.loc[fy, "total_revenue_net_admin"] - wide.loc[fy, "total_refunds"]
            )
            assert abs(float(ruc)) < 1e-6, f"{comparator}/{bridge} FY{fy} RUC {ruc}"
            assert abs(float(fed)) < 1e-6, f"{comparator}/{bridge} FY{fy} FED {fed}"
            assert abs(float(nltf)) < 1e-6, f"{comparator}/{bridge} FY{fy} NLTF {nltf}"


class TestPublishedRowsStayIdenticalToSource:
    @pytest.mark.parametrize("comparator,bridge", COMBINATIONS)
    def test_official_rows_match_their_source_pack(self, matrix, comparator, bridge):
        chart = matrix[(comparator, bridge)]["chart_rows"]
        for vid in ("BEFU26", "MBU26"):
            scenario = ov.official_comparator_scenario_name(vid)
            displayed = chart[
                chart["scenario_name"].astype(str).eq(scenario)
                & chart["time_grain"].astype(str).eq("june_year")
            ]
            if displayed.empty:
                continue
            spine = ov.official_vintage_spine_frame(vid, ROOT)
            for row in displayed.itertuples():
                value = pd.to_numeric(pd.Series([row.value]), errors="coerce").iloc[0]
                fy = int(float(row.june_year))
                series = str(row.series_id)
                if pd.isna(value) or series not in spine.columns or fy not in spine.index:
                    continue
                source = spine.loc[fy, series]
                if pd.notna(source):
                    assert float(value) == float(source), (
                        f"{comparator}/{bridge} displayed {vid} {series} FY{fy} diverges from source"
                    )

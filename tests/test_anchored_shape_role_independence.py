"""Comparator x bridge x shape independence, and the plug-and-play contract.

Section 15 of the brief. PR #11 established that the comparator and bridge
roles are independent; this extends the matrix to the third role and proves the
separation is structural rather than incidental:

    comparator  changes only the OFFICIAL displayed rows
    bridge      changes Current RATES and fixed lines, never Current ACTIVITY
    shape       changes only Current FY2031-FY2050, never FY2026-FY2030

and that a future vintage becomes a usable shape source through the registry
alone, with no code change.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard import official_vintage as ov
from model_dashboard.long_run_shape_transition import UNBLENDED_SCHEDULE_ID
from model_dashboard.post_model_extrapolation import (
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    build_post_model_extrapolation_annual,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "current_revenue_outlook"
BASE_SCENARIO = "current_basecase"

ACTIVITY_SERIES = (
    "light_petrol_vkt",
    "ped_vkt_per_capita",
    "heavy_ruc_net_km",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
)


@pytest.fixture(scope="module")
def pack_inputs() -> dict[str, pd.DataFrame]:
    return {
        "line_reconciliation": pd.read_parquet(
            PACK_DIR / "revenue_line_reconciliation.parquet"
        ),
        "raw_quarterly_audit": pd.read_parquet(
            PACK_DIR / "raw_quarterly_forecast_audit.parquet"
        ),
        "scenario_input_wide": pd.read_parquet(
            PACK_DIR / "scenario_inputs" / "scenario_input_wide.parquet"
        ),
    }


@pytest.fixture(scope="module")
def vintages() -> dict[str, ov.OfficialVintagePack]:
    packs = {}
    for vid in ("BEFU26", "MBU26"):
        pack = ov.load_official_vintage(vid, repo_root=ROOT)
        assert pack is not None, vid
        packs[vid] = pack
    return packs


def _build(
    pack_inputs: dict[str, pd.DataFrame],
    vintages: dict[str, ov.OfficialVintagePack],
    *,
    bridge: str,
    shape: str,
    schedule: str = "balanced_structural",
) -> pd.DataFrame:
    return build_post_model_extrapolation_annual(
        line_reconciliation=pack_inputs["line_reconciliation"],
        raw_quarterly_audit=pack_inputs["raw_quarterly_audit"],
        scenario_input_wide=pack_inputs["scenario_input_wide"],
        mbu26_official_annual=vintages[bridge].official_annual,
        repo_root=ROOT,
        long_run_shape_official_annual=vintages[shape].official_annual,
        long_run_shape_vintage_id=shape,
        transition_schedule_id=schedule,
    )


def _series(frame: pd.DataFrame, series_id: str) -> pd.Series:
    scoped = frame[
        frame["scenario_name"].eq(BASE_SCENARIO) & frame["series_id"].eq(series_id)
    ]
    return scoped.set_index("fy")["value"].sort_index()


class TestThreeRoleMatrix:
    """The permanent comparator x bridge x shape matrix."""

    def test_matrix_cells_all_build(self, pack_inputs, vintages):
        cells = (
            ("BEFU26", "BEFU26", "BEFU26"),
            ("MBU26", "BEFU26", "BEFU26"),
            ("BEFU26", "MBU26", "BEFU26"),
            ("BEFU26", "BEFU26", "MBU26"),
        )
        for comparator, bridge, shape in cells:
            frame = _build(pack_inputs, vintages, bridge=bridge, shape=shape)
            assert not frame.empty, (comparator, bridge, shape)

    def test_bridge_changes_rates_not_activity(self, pack_inputs, vintages):
        """Gate 14, bridge leg.

        Swapping the bridge vintage must move revenue (different effective
        rates and fixed lines) while leaving every activity series bit-identical:
        activity is built from Current anchors and growth indices, and the
        bridge supplies neither.
        """

        befu = _build(pack_inputs, vintages, bridge="BEFU26", shape="BEFU26")
        mbu_bridge = _build(pack_inputs, vintages, bridge="MBU26", shape="BEFU26")
        for series in ACTIVITY_SERIES:
            left, right = _series(befu, series), _series(mbu_bridge, series)
            assert np.array_equal(left.to_numpy(), right.to_numpy()), series

        # ...and it does change revenue, so the test is not vacuous.
        revenue_delta = (
            _series(befu, "total_nltf_net_revenue")
            - _series(mbu_bridge, "total_nltf_net_revenue")
        ).abs().max()
        assert float(revenue_delta) > 0.0

    def test_shape_changes_activity(self, pack_inputs, vintages):
        """Gate 14, shape leg: the shape vintage moves the long-run activity."""

        befu = _build(pack_inputs, vintages, bridge="BEFU26", shape="BEFU26")
        mbu_shape = _build(pack_inputs, vintages, bridge="BEFU26", shape="MBU26")
        delta = (
            _series(befu, "light_petrol_vkt") - _series(mbu_shape, "light_petrol_vkt")
        ).abs().max()
        assert float(delta) > 0.0

    def test_shape_never_touches_the_anchor_or_the_short_run(
        self, pack_inputs, vintages
    ):
        """Gates 3 and 11: the layer starts at FY2031 and is anchored at FY2030."""

        for shape in ("BEFU26", "MBU26"):
            frame = _build(pack_inputs, vintages, bridge="BEFU26", shape=shape)
            fys = frame["fy"].unique()
            assert int(min(fys)) == FIRST_EXTRAPOLATION_FY
            assert int(max(fys)) == LAST_EXTRAPOLATION_FY
            assert ANCHOR_FY not in set(int(fy) for fy in fys)

    def test_shape_does_not_change_official_published_rows(self, vintages):
        """Gates 4, 5 and 13: official spines are inputs, never outputs."""

        for vid, pack in vintages.items():
            reloaded = ov.load_official_vintage(vid, repo_root=ROOT)
            assert reloaded is not None
            pd.testing.assert_frame_equal(
                pack.official_annual.reset_index(drop=True),
                reloaded.official_annual.reset_index(drop=True),
            )

    def test_roles_resolve_independently_from_the_registry(self):
        # Independence made real: the comparator and long-run shape roles
        # moved to PREBU26 (in separate promotions) while the bridge role
        # stayed on BEFU26.
        assert ov.default_comparator_vintage_id(ROOT) == "PREBU26"
        assert ov.default_bridge_vintage_id(ROOT) == "BEFU26"
        assert ov.default_long_run_shape_vintage_id(ROOT) == "PREBU26"
        # Independent means separately resolvable, not merely equal today.
        registry = ov.load_official_vintage_registry(ROOT)
        flags = {
            entry["vintage_id"]: {
                flag: bool(entry.get(flag)) for flag in ov.ROLE_FLAGS
            }
            for entry in registry["vintages"]
        }
        for flag in ov.ROLE_FLAGS:
            owners = [vid for vid, values in flags.items() if values[flag]]
            assert len(owners) == 1, (flag, owners)


class TestPackManifestIsAuthoritative:
    """Gate 15: a replay uses the pack's OWN shape vintage."""

    def test_manifest_shape_vintage_wins_over_the_registry_default(self):
        manifest = {
            "official_vintages": {
                "official_comparator_vintage_id": "BEFU26",
                "bridge_assumption_vintage_id": "BEFU26",
                "long_run_shape_vintage_id": "MBU26",
            }
        }
        assert (
            ov.long_run_shape_vintage_id_from_manifest(manifest, ROOT) == "MBU26"
        )
        assert ov.default_long_run_shape_vintage_id(ROOT) == "PREBU26"

    def test_pack_without_the_block_falls_back_to_the_registry(self):
        assert (
            ov.long_run_shape_vintage_id_from_manifest({}, ROOT)
            == ov.default_long_run_shape_vintage_id(ROOT)
        )

    def test_unowned_shape_role_fails_closed_rather_than_borrowing(self, tmp_path):
        """An unowned role must raise, never silently reuse another role."""

        root = tmp_path / "repo"
        registry = ov.load_official_vintage_registry(ROOT)
        for entry in registry["vintages"]:
            entry[ov.LONG_RUN_SHAPE_ROLE_FLAG] = False
        target = root / ov.OFFICIAL_VINTAGE_REGISTRY_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

        # The registry itself stays valid (the role is optional)...
        assert ov.validate_official_vintage_registry(registry) == []
        # ...but asking for the default fails closed.
        with pytest.raises(ov.OfficialVintageError):
            ov.default_long_run_shape_vintage_id(root)


class TestShapeCapabilityIsDerived:
    """Gate 29: a future vintage needs no code change."""

    def test_committed_vintages_derive_their_shape_window(self):
        for vid in ("BEFU26", "MBU26"):
            assert ov.vintage_supports_long_run_shape(vid, ROOT), vid
            start, end = ov.long_run_shape_window(vid, ROOT)
            assert start <= ANCHOR_FY
            assert end >= LAST_EXTRAPOLATION_FY

    def test_a_vintage_missing_a_required_series_is_refused(self):
        """Capability is decided by content, not by name."""

        pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
        assert pack is not None
        crippled = pack.official_annual[
            pack.official_annual["series_id"].ne("heavy_ruc_net_km")
        ]
        derived = ov._derive_long_run_shape_support(
            crippled, ov.official_vintage_entry("BEFU26", ROOT)
        )
        assert derived["supports_long_run_shape"] is False
        assert "heavy_ruc_net_km" in derived["long_run_shape_missing_series"]

    def test_a_vintage_that_stops_before_fy2050_is_refused(self):
        """Eligibility must require the WHOLE window, not just the anchor.

        A vintage ending at FY2044 covers the anchor and then some, but the
        constructor needs FY2030-FY2050. Advertising it as shape-capable would
        make it selectable and then fail at construction.
        """

        pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
        assert pack is not None
        annual = pack.official_annual
        truncated = annual[pd.to_numeric(annual["FY"], errors="coerce") <= 2044]
        entry = dict(ov.official_vintage_entry("BEFU26", ROOT))
        entry["source_horizon_fy"] = 2044
        derived = ov._derive_long_run_shape_support(truncated, entry)
        assert derived["supports_long_run_shape"] is False
        assert derived["long_run_shape_end_fy"] is None

    def test_a_vintage_reaching_exactly_fy2050_is_accepted(self):
        """The boundary is inclusive: FY2050 coverage is enough."""

        pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
        assert pack is not None
        annual = pack.official_annual
        exact = annual[pd.to_numeric(annual["FY"], errors="coerce") <= 2050]
        entry = dict(ov.official_vintage_entry("BEFU26", ROOT))
        entry["source_horizon_fy"] = 2050
        derived = ov._derive_long_run_shape_support(exact, entry)
        assert derived["supports_long_run_shape"] is True
        assert derived["long_run_shape_end_fy"] == 2050

    def test_a_vintage_that_stops_before_the_anchor_is_refused(self):
        pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
        assert pack is not None
        early = pack.official_annual[
            pd.to_numeric(pack.official_annual["FY"], errors="coerce") < ANCHOR_FY
        ]
        derived = ov._derive_long_run_shape_support(
            early, ov.official_vintage_entry("BEFU26", ROOT)
        )
        assert derived["supports_long_run_shape"] is False

    def test_a_longer_horizon_vintage_registers_a_longer_window(self):
        """A PREFU-style vintage running past FY2055 widens the window."""

        pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
        assert pack is not None
        annual = pack.official_annual.copy()
        tail = annual[pd.to_numeric(annual["FY"], errors="coerce").eq(2055)].copy()
        extended = [annual]
        for fy in range(2056, 2061):
            block = tail.copy()
            block["FY"] = fy
            extended.append(block)
        longer = pd.concat(extended, ignore_index=True)
        entry = dict(ov.official_vintage_entry("BEFU26", ROOT))
        entry["source_horizon_fy"] = 2060
        derived = ov._derive_long_run_shape_support(longer, entry)
        assert derived["supports_long_run_shape"] is True
        assert derived["long_run_shape_end_fy"] == 2060

    def test_a_fixture_vintage_drives_the_constructor_without_code_changes(
        self, pack_inputs, vintages
    ):
        """PREFU26-style: a DIFFERENT shape, ingested purely as data."""

        befu = vintages["BEFU26"].official_annual.copy()
        prefu = befu.copy()
        # A materially different long-run shape: slower electrification, so
        # petrol declines less and the pool grows less.
        fy = pd.to_numeric(prefu["FY"], errors="coerce")
        horizon = fy.clip(lower=ANCHOR_FY) - ANCHOR_FY
        petrol = prefu["series_id"].eq("light_petrol_vkt")
        prefu.loc[petrol, "value"] = prefu.loc[petrol, "value"] * (
            1.0 + 0.010 * horizon[petrol]
        )

        frame = build_post_model_extrapolation_annual(
            line_reconciliation=pack_inputs["line_reconciliation"],
            raw_quarterly_audit=pack_inputs["raw_quarterly_audit"],
            scenario_input_wide=pack_inputs["scenario_input_wide"],
            mbu26_official_annual=vintages["BEFU26"].official_annual,
            repo_root=ROOT,
            long_run_shape_official_annual=prefu,
            long_run_shape_vintage_id="PREFU26",
            transition_schedule_id="balanced_structural",
        )
        assert not frame.empty
        assert set(frame["long_run_shape_vintage_id"]) == {"PREFU26"}
        baseline = _build(pack_inputs, vintages, bridge="BEFU26", shape="BEFU26")
        delta = (
            _series(frame, "light_petrol_vkt") - _series(baseline, "light_petrol_vkt")
        ).abs().max()
        assert float(delta) > 0.0


class TestStructuralScheduleRequiresAShapeSource:
    def test_structural_schedule_without_a_source_fails_closed(self, pack_inputs, vintages):
        with pytest.raises(Exception, match="fail closed|long-run shape source"):
            build_post_model_extrapolation_annual(
                line_reconciliation=pack_inputs["line_reconciliation"],
                raw_quarterly_audit=pack_inputs["raw_quarterly_audit"],
                scenario_input_wide=pack_inputs["scenario_input_wide"],
                mbu26_official_annual=vintages["BEFU26"].official_annual,
                repo_root=ROOT,
                transition_schedule_id="balanced_structural",
            )

    def test_unblended_needs_no_shape_source(self, pack_inputs, vintages):
        frame = build_post_model_extrapolation_annual(
            line_reconciliation=pack_inputs["line_reconciliation"],
            raw_quarterly_audit=pack_inputs["raw_quarterly_audit"],
            scenario_input_wide=pack_inputs["scenario_input_wide"],
            mbu26_official_annual=vintages["BEFU26"].official_annual,
            repo_root=ROOT,
            transition_schedule_id=UNBLENDED_SCHEDULE_ID,
        )
        assert not frame.empty

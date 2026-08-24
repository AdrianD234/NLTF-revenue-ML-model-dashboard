"""PREBU26 default-comparator acceptance gates.

PREBU26 (the PREFU-round 2026 release) becomes the latest and default official
comparator - the green official line - while BEFU26 keeps the bridge role.
Since the long-run handover promotion PREBU26 also owns the long-run shape
role; the bridge is the only default role left on BEFU26. These tests pin the
whole bounded scope:

- PREBU26 materializes and round-trips exactly (registry hash, sentinels);
- registry roles: PREBU26 latest/default comparator, BEFU26 bridge/shape;
- the PREBU26 source publishes ACTUAL through FY2026;
- the default chart vocabulary leads with "PREBU26 official" in the official
  green styling, with BEFU26 and MBU26 still selectable but not default;
- the visible annual Current forecast begins FY2027 under PREBU26, derived
  from the vintage's actual_end_fy rather than a hard-coded year (BEFU26
  selected restores the FY2026 start and the FY2025 anchor);
- the underlying Current FY2026 model rows survive unchanged for audit;
- every Current value is byte-identical to the pinned pre-change baseline;
- the quarterly view is untouched and PREBU26's FY2026 annual ACTUAL is never
  disaggregated into quarters;
- bridge-method captions keep naming BEFU26;
- Current scenario controls never alter published PREBU26 values.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard import official_vintage as ov
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    load_revenue_outlook_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / CURRENT_REVENUE_OUTLOOK_DIR
BASELINE_DIR = ROOT / "artifacts" / "official_vintage_prebu26"

PREBU26_WORKBOOK_SHA = "f69985432b34271d5868267d78b77ad2c746563788011b445715e4f58a25728b"

# Representative sentinel spot-checks (the registry pins the full set).
PREBU26_SENTINELS = (
    ("total_nltf_net_revenue", 2026, 4491.33665247696),
    ("total_nltf_net_revenue", 2030, 6457.08040779104),
    ("total_nltf_net_revenue", 2050, 12955.4993074031),
    ("net_fed_revenue", 2026, 2022.61171268),
    ("total_ruc_net_revenue", 2026, 2049.28050774696),
    ("ped_vkt_per_capita", 2026, 5965.26362676545),
    ("light_ruc_net_km", 2026, 12489.492147),
    ("tuc_net_revenue", 2026, 17.55237116),
)


@pytest.fixture(scope="module")
def registry():
    return ov.load_official_vintage_registry(ROOT)


@pytest.fixture(scope="module")
def prebu26_pack() -> ov.OfficialVintagePack:
    pack = ov.load_official_vintage("PREBU26", repo_root=ROOT)
    assert pack is not None, "PREBU26 pack is not materialized"
    return pack


@pytest.fixture(scope="module")
def runtime_pack():
    loaded = load_revenue_outlook_pack(PACK_DIR, repo_root=ROOT)
    assert loaded is not None
    return loaded


def _view(pack, vintage_id: str, overlay: bool = False, *, series: str = "Total NLTF revenue"):
    signature = app.revenue_outlook_signature(PACK_DIR, ROOT)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    uptake_key = (
        app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0, False, vintage_id, overlay,
    )
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    return app.cached_revenue_outlook_view(
        signature,
        series,
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        app.PED_BRIDGE_DEFAULT_MODE,
        uptake_key,
        pack,
    )


def _visible_current_annual(frame: pd.DataFrame) -> pd.DataFrame:
    rows = frame[
        frame["time_grain"].astype(str).eq("june_year")
        & frame["trace_role"].astype(str).eq("in_house_current_finalist")
    ].copy()
    if "plot_allowed" in rows.columns:
        rows = rows[rows["plot_allowed"].fillna(True).astype(bool)]
    return rows


class TestRegistryRoles:
    def test_prebu26_is_latest_comparator_and_long_run_shape(self, registry):
        entry = ov.official_vintage_entry("PREBU26", registry=registry)
        assert entry["is_latest"] is True
        assert entry["is_default_comparator"] is True
        assert entry["is_default_bridge_vintage"] is False
        # The long-run shape role moved to PREBU26 with the growth-handover
        # promotion; the bridge role deliberately did not.
        assert entry["is_default_long_run_shape_vintage"] is True
        assert entry["workbook_sha256"] == PREBU26_WORKBOOK_SHA
        assert entry["source_workbook"] == "references/PREBU26.xlsx"
        assert entry["source_sheet"] == "PREBU"

    def test_befu26_keeps_bridge_only(self, registry):
        entry = ov.official_vintage_entry("BEFU26", registry=registry)
        assert entry["is_latest"] is False
        assert entry["is_default_comparator"] is False
        assert entry["is_default_bridge_vintage"] is True
        assert entry["is_default_long_run_shape_vintage"] is False
        assert ov.default_bridge_vintage_id(ROOT) == "BEFU26"
        assert ov.default_long_run_shape_vintage_id(ROOT) == "PREBU26"
        assert ov.default_comparator_vintage_id(ROOT) == "PREBU26"
        assert ov.latest_official_vintage_id(ROOT) == "PREBU26"

    def test_prior_vintages_remain_selectable_not_default(self):
        choices = ov.official_vintage_choices(ROOT)
        assert choices[0][0] == "PREBU26"
        assert {vid for vid, _ in choices} == {"PREBU26", "BEFU26", "MBU26"}

    def test_registry_still_validates_with_one_owner_per_role(self, registry):
        assert ov.validate_official_vintage_registry(registry) == []


class TestPrebu26Pack:
    def test_workbook_hash_and_round_trip(self, prebu26_pack):
        workbook = ROOT / "references" / "PREBU26.xlsx"
        assert workbook.exists(), "governed PREBU26 workbook must be vendored"
        assert ov.sha256(workbook) == PREBU26_WORKBOOK_SHA
        manifest = prebu26_pack.manifest
        assert manifest["workbook"]["sha256"] == PREBU26_WORKBOOK_SHA
        assert manifest["workbook"]["sheet"] == "PREBU"
        assert manifest["sentinels_validated"] == 15
        assert len(manifest["normalized_files"]) == 16

    def test_source_publishes_actual_through_fy2026(self, prebu26_pack, registry):
        spine = prebu26_pack.annual_spine
        actual = spine[spine["period_status"].astype(str).eq("ACTUAL")]
        assert int(pd.to_numeric(actual["FY"]).max()) == 2026
        st_block = spine[spine["period_status"].astype(str).eq("ST_FORECAST")]
        assert int(pd.to_numeric(st_block["FY"]).min()) == 2027
        assert int(pd.to_numeric(st_block["FY"]).max()) == 2031
        lt_block = spine[spine["period_status"].astype(str).eq("LT_FORECAST")]
        assert int(pd.to_numeric(lt_block["FY"]).max()) == 2055
        entry = ov.official_vintage_entry("PREBU26", registry=registry)
        assert (entry["actual_start_fy"], entry["actual_end_fy"]) == (2001, 2026)
        assert (entry["short_forecast_start_fy"], entry["short_forecast_end_fy"]) == (2027, 2031)

    def test_sentinel_values_match_workbook(self, prebu26_pack):
        spine = prebu26_pack.annual_spine
        values = {
            (str(row.series_id), int(row.FY)): float(row.value)
            for row in spine.itertuples()
            if pd.notna(pd.to_numeric(row.value, errors="coerce"))
        }
        for series_id, fy, expected in PREBU26_SENTINELS:
            assert math.isclose(values[(series_id, fy)], expected, rel_tol=1e-12, abs_tol=1e-9), (
                series_id,
                fy,
            )

    def test_published_residuals_reported_never_absorbed(self, prebu26_pack):
        audit = prebu26_pack.formula_audit
        residuals = audit[audit["status"].astype(str).eq("residual_reported")]
        assert set(residuals["output_series_id"]) == {"gross_ruc_revenue"}
        assert sorted(residuals["FY"].astype(int)) == [2027, 2028, 2029, 2030, 2031]


class TestDefaultChartVocabulary:
    def test_prebu26_official_leads_in_the_green_styling(self):
        names = app._registry_official_trace_names()
        assert names[0] == "PREBU26 official"
        styles = app._official_trace_style_map()
        assert styles["PREBU26 official"][0] == "#00843D"
        # Prior vintages are muted, selectable, not default-styled green.
        assert styles["BEFU26 official"][0] != "#00843D"
        assert styles["MBU26 official"][0] != "#00843D"

    def test_default_traces_include_prebu26_official(self, runtime_pack):
        options = app._revenue_outlook_trace_options(runtime_pack.revenue_chart_rows)
        defaults = app._revenue_outlook_default_traces(options)
        assert "PREBU26 official" in defaults
        assert "BEFU26 official" not in defaults
        assert "MBU26 official" not in defaults

    def test_runtime_manifest_names_prebu26_default_comparator(self, runtime_pack):
        block = runtime_pack.manifest["official_vintages"]
        assert block["official_comparator_vintage_id"] == "PREBU26"
        assert block["bridge_assumption_vintage_id"] == "BEFU26"
        assert block["long_run_shape_vintage_id"] == "PREBU26"
        assert block["default_official_comparator_trace"] == "PREBU26 official"
        assert set(block["available"]) == {"PREBU26", "BEFU26", "MBU26"}


class TestAnnualSeam:
    def test_visible_current_forecast_starts_fy2027_under_prebu26(self, runtime_pack):
        view = _view(runtime_pack, "PREBU26")
        visible = _visible_current_annual(view["filtered_rows"])
        assert not visible.empty
        assert int(pd.to_numeric(visible["june_year"]).min()) == 2027

    def test_seam_follows_vintage_metadata_not_a_constant(self, runtime_pack):
        """BEFU26 selected: its own actual_end_fy (2025) governs the seam."""
        view = _view(runtime_pack, "BEFU26")
        visible = _visible_current_annual(view["filtered_rows"])
        years = sorted(pd.to_numeric(visible["june_year"]).astype(int).unique())
        assert years[0] == 2025  # FY2025 actual anchor abuts the BEFU26 seam
        assert 2026 in years  # FY2026 nowcast stays visible under BEFU26
        assert app._official_vintage_actual_end_fy("PREBU26") == 2026
        assert app._official_vintage_actual_end_fy("BEFU26") == 2025

    def test_underlying_current_fy2026_rows_survive_for_audit(self, runtime_pack):
        view = _view(runtime_pack, "PREBU26")
        chart_rows = view["chart_rows"]
        hidden = chart_rows[
            chart_rows["time_grain"].astype(str).eq("june_year")
            & chart_rows["trace_role"].astype(str).eq("in_house_current_finalist")
            & pd.to_numeric(chart_rows["june_year"]).eq(2026)
            & chart_rows["scenario_name"].astype(str).eq("current_basecase")
            & chart_rows["series_id"].astype(str).eq("total_nltf_net_revenue")
        ]
        assert len(hidden) == 1
        assert not bool(hidden["plot_allowed"].iloc[0])
        # Still labelled as model output, never as an actual. (data_scope may
        # carry an overlay stamp; the nowcast flag and value_status are the
        # stable model-output markers.)
        assert bool(hidden["nowcast_flag"].iloc[0])
        assert hidden["value_status"].iloc[0] != "actual"
        # Masked, not moved: the hidden FY2026 value equals the value the SAME
        # computation shows when BEFU26 is selected (where FY2026 is visible).
        befu_view = _view(runtime_pack, "BEFU26")
        befu_rows = befu_view["chart_rows"]
        visible = befu_rows[
            befu_rows["time_grain"].astype(str).eq("june_year")
            & befu_rows["trace_role"].astype(str).eq("in_house_current_finalist")
            & pd.to_numeric(befu_rows["june_year"]).eq(2026)
            & befu_rows["scenario_name"].astype(str).eq("current_basecase")
            & befu_rows["series_id"].astype(str).eq("total_nltf_net_revenue")
        ]
        assert len(visible) == 1
        assert bool(visible["plot_allowed"].iloc[0])
        assert math.isclose(
            float(hidden["value"].iloc[0]), float(visible["value"].iloc[0]), rel_tol=1e-12
        )
        # And the committed pack row itself is untouched: still the published
        # policy value, still labelled a nowcast.
        committed = pd.read_csv(PACK_DIR / "revenue_chart_rows.csv", low_memory=False)
        committed_row = committed[
            committed["time_grain"].astype(str).eq("june_year")
            & pd.to_numeric(committed["june_year"], errors="coerce").eq(2026)
            & committed["scenario_name"].astype(str).eq("current_basecase")
            & committed["series_id"].astype(str).eq("total_nltf_net_revenue")
        ]
        assert len(committed_row) == 1
        assert committed_row["data_scope"].iloc[0] == "current_nowcast"
        assert math.isclose(
            float(committed_row["value"].iloc[0]), 4599.805745017675, rel_tol=1e-12
        )

    def test_prebu26_official_line_covers_fy2026_as_actual(self, runtime_pack):
        view = _view(runtime_pack, "PREBU26")
        official = view["filtered_rows"]
        official = official[
            official["scenario_name"].astype(str).eq("prebu26_official")
            & official["time_grain"].astype(str).eq("june_year")
        ]
        fy2026 = official[pd.to_numeric(official["june_year"]).eq(2026)]
        assert len(fy2026) == 1
        assert fy2026["value_status"].iloc[0] == "actual"
        assert math.isclose(float(fy2026["value"].iloc[0]), 4491.33665247696, rel_tol=1e-12)

    def test_official_selection_never_moves_current_values(self, runtime_pack):
        """Masking is visibility-only: values agree wherever both are visible."""
        prebu = _view(runtime_pack, "PREBU26")
        befu = _view(runtime_pack, "BEFU26")

        def values(view):
            rows = _visible_current_annual(view["filtered_rows"])
            rows = rows[rows["scenario_name"].astype(str).eq("current_basecase")]
            return {
                int(fy): float(value)
                for fy, value in zip(
                    pd.to_numeric(rows["june_year"]), pd.to_numeric(rows["value"])
                )
            }

        prebu_values = values(prebu)
        befu_values = values(befu)
        shared = set(prebu_values) & set(befu_values)
        assert min(shared) == 2027
        for fy in shared:
            assert prebu_values[fy] == befu_values[fy], fy


class TestQuarterlyViewUnchanged:
    def test_quarterly_rows_are_byte_identical_to_the_pinned_baseline(self):
        baseline = pd.read_csv(
            BASELINE_DIR / "pre_bridge_refresh_chart_rows_ensemble.csv", low_memory=False
        )
        current = pd.read_csv(PACK_DIR / "revenue_chart_rows.csv", low_memory=False)
        q_new = current[current["time_grain"].astype(str).eq("quarterly")].reset_index(drop=True)
        q_old = baseline[baseline["time_grain"].astype(str).eq("quarterly")].reset_index(drop=True)
        pd.testing.assert_frame_equal(q_new, q_old, check_dtype=False)

    def test_no_quarterly_prebu26_rows_exist(self, runtime_pack):
        rows = runtime_pack.revenue_chart_rows
        quarterly = rows[rows["time_grain"].astype(str).eq("quarterly")]
        assert not quarterly["scenario_name"].astype(str).eq("prebu26_official").any()

    def test_fy2026_annual_actual_is_never_disaggregated(self, runtime_pack):
        """The quarterly view must not manufacture FY2026 quarters from the
        PREBU26 annual ACTUAL, and must never label such quarters actual."""
        view = _view(runtime_pack, "PREBU26")
        annual = view["chart_rows"]
        official_annual = annual[
            annual["scenario_name"].astype(str).eq("prebu26_official")
        ].copy()
        derived = app._disaggregate_annual_rows_to_quarterly(official_annual, annual)
        if not derived.empty:
            years = pd.to_numeric(derived["june_year"], errors="coerce")
            assert int(years.min()) >= 2027
            assert not derived["value_status"].astype(str).eq("actual").any()


class TestCurrentValuesInvariant:
    @pytest.mark.parametrize(
        "pack_dir,baseline_name",
        [
            (Path("data") / "current_revenue_outlook", "pre_bridge_refresh_chart_rows_ensemble.csv"),
            (
                Path("data") / "engine_ar1" / "current_revenue_outlook",
                "pre_bridge_refresh_chart_rows_ar1.csv",
            ),
        ],
    )
    def test_all_non_prebu26_chart_rows_match_the_pinned_baseline(
        self, pack_dir, baseline_name
    ):
        """Adding PREBU26 roles must not move Current values it does not own.

        The FY2031-FY2050 post-model rows are excluded: PREBU26 legitimately
        owns that layer since the long-run shape role moved to it (the
        one-way growth handover promotion), and the promotion audit
        separately proves ONLY that layer moved. Everything else - actuals,
        the econometric window, the other official spines - must still match
        the baseline frozen before PREBU26 carried any role.
        """
        new = pd.read_csv(ROOT / pack_dir / "revenue_chart_rows.csv", low_memory=False)
        old = pd.read_csv(BASELINE_DIR / baseline_name, low_memory=False)

        def _outside_shape_scope(frame: pd.DataFrame) -> pd.DataFrame:
            scoped = frame[~frame["scenario_name"].astype(str).eq("prebu26_official")]
            segment = scoped.get(
                "forecast_segment", pd.Series("", index=scoped.index)
            )
            return scoped[
                ~segment.fillna("").astype(str).eq("post_model_extrapolation")
            ].reset_index(drop=True)

        pd.testing.assert_frame_equal(
            _outside_shape_scope(new), _outside_shape_scope(old)
        )


class TestBridgeCaptionsStayBefu26:
    def test_rate_chart_note_names_the_bridge_vintage(self):
        from model_dashboard.rate_paths import rate_chart_note

        note = rate_chart_note("BEFU26")
        assert "BEFU26" in note
        assert "PREBU26" not in note

    def test_current_rows_bridge_provenance_stays_befu26(self, runtime_pack):
        """PREBU26 may appear ONLY as the long-run growth-shape source.

        The bridge assumptions - effective rates, fuel intensity, carried
        fixed lines - stay BEFU26, so any provenance string naming PREBU26
        must be a shape-transition formula ("growth shape"), never a rate or
        bridge caption.
        """
        line = runtime_pack.revenue_line_reconciliation
        current = line[line["source_path"].astype(str).eq("Current finalist Base case")]
        offenders = [
            value
            for column in ("bridge_method", "formula", "source_basis", "notes")
            if column in current.columns
            for value in current[column].dropna().astype(str).unique()
            if "PREBU26" in value and "growth shape" not in value
        ]
        assert not offenders, offenders[:3]

    def test_official_vintages_block_keeps_bridge_befu26(self):
        import json

        for pack_dir in (
            ROOT / "data" / "current_revenue_outlook",
            ROOT / "data" / "engine_ar1" / "current_revenue_outlook",
        ):
            manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
            block = manifest["official_vintages"]
            assert block["bridge_assumption_vintage_id"] == "BEFU26"
            # The shape role follows the registry promotion; only the BRIDGE
            # is the invariant this class protects.
            assert block["long_run_shape_vintage_id"] == "PREBU26"


class TestPublishedValuesImmuneToControls:
    def test_scenario_controls_do_not_alter_prebu26_values(self, runtime_pack):
        spine = ov.official_vintage_spine_frame("PREBU26", ROOT)
        signature = app.revenue_outlook_signature(PACK_DIR, ROOT)
        # A deliberately non-default lever mix.
        sensitivity_key = app.selected_sensitivity_key("High", "Med", "Off")
        uptake_key = (
            app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0, False, "PREBU26", False,
        )
        traces = tuple(app._revenue_outlook_trace_options(runtime_pack.revenue_chart_rows))
        view = app.cached_revenue_outlook_view(
            signature,
            "Total NLTF revenue",
            "june_year",
            "Current planned path",
            traces,
            sensitivity_key,
            app.PED_BRIDGE_DEFAULT_MODE,
            uptake_key,
            runtime_pack,
        )
        rows = view["chart_rows"]
        official = rows[
            rows["scenario_name"].astype(str).eq("prebu26_official")
            & rows["time_grain"].astype(str).eq("june_year")
        ]
        assert not official.empty
        for row in official.itertuples():
            fy = int(row.june_year)
            expected = float(spine.loc[fy, str(row.series_id)])
            assert math.isclose(float(row.value), expected, rel_tol=1e-12, abs_tol=1e-9), (
                row.series_id,
                fy,
            )

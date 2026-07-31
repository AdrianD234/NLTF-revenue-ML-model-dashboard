"""The analyst preview must actually change the plotted values.

The earlier front-end suite tested option availability, session keys and
wording, and passed while the selector was a no-op: the state it returned was
never consumed. These tests exercise the real path - key -> signature -> pack
-> overlay chain - and assert on VALUES.

What each selection must do:

    FY2031-FY2050 Current   changes, and differs between schedules
    FY2030 and earlier      identical, bit for bit
    official published rows identical, bit for bit
    Base and comparison     each keep their own FY2030 anchor
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app as dashboard
from model_dashboard.long_run_shape_transition import UNBLENDED_SCHEDULE_ID
from model_dashboard.post_model_extrapolation import (
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    POST_MODEL_SEGMENT,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "current_revenue_outlook"
SHAPE_VINTAGE = "BEFU26"
SCHEDULES = (
    UNBLENDED_SCHEDULE_ID,
    "early_structural",
    "balanced_structural",
    "gradual_structural",
)


@pytest.fixture(scope="module")
def loaded():
    signature = dashboard.revenue_outlook_signature(PACK_DIR, ROOT)
    pack = dashboard.cached_load_revenue_outlook_pack(
        str(PACK_DIR), str(ROOT), signature, dashboard.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    return pack, signature


def _key(schedule_id: str) -> tuple:
    return (
        dashboard.EV_UPTAKE_GOVERNED_OPTION,
        (),
        (),
        dashboard.FED_POLICY_PUBLISHED,
        dashboard.FED_POLICY_PUBLISHED,
        False,
        "BEFU26",
        False,
        schedule_id,
        SHAPE_VINTAGE,
    )


def _rows_for(loaded, schedule_id: str) -> pd.DataFrame:
    """The full overlay output for one schedule, through the real path."""

    pack, signature = loaded
    adjusted_pack, adjusted_signature = dashboard._apply_long_run_shape_selection(
        pack, signature, str(PACK_DIR), _key(schedule_id)
    )
    sensitivity_key = dashboard.selected_sensitivity_key(
        "Off", "Off", "Off", freight_rail_shift="Off"
    )
    rows, *_ = dashboard.cached_scenario_overlay_rows(
        adjusted_signature,
        sensitivity_key,
        dashboard.PED_BRIDGE_DEFAULT_MODE,
        _key(schedule_id),
        adjusted_pack,
    )
    return rows


def _annual(rows: pd.DataFrame, scenario: str, series: str) -> pd.Series:
    scoped = rows[
        rows["scenario_name"].astype(str).eq(scenario)
        & rows["series_id"].astype(str).eq(series)
        & rows["time_grain"].astype(str).eq("june_year")
    ]
    return (
        scoped.set_index(pd.to_numeric(scoped["june_year"], errors="coerce"))["value"]
        .astype(float)
        .sort_index()
    )


@pytest.fixture(scope="module")
def by_schedule(loaded) -> dict[str, pd.DataFrame]:
    return {schedule: _rows_for(loaded, schedule) for schedule in SCHEDULES}


class TestSelectionChangesTheLongRun:
    def test_the_selection_is_not_a_no_op(self, by_schedule):
        """The headline regression: selecting a schedule must move FY2040."""

        values = {
            schedule: float(
                _annual(rows, "current_basecase", "total_nltf_net_revenue").loc[2040]
            )
            for schedule, rows in by_schedule.items()
        }
        assert len(set(round(v, 6) for v in values.values())) == len(SCHEDULES), values

    def test_fy2040_orders_as_the_schedules_predict(self, by_schedule):
        """Slower transition -> closer to the unblended path at FY2040."""

        fy2040 = {
            schedule: float(
                _annual(rows, "current_basecase", "total_nltf_net_revenue").loc[2040]
            )
            for schedule, rows in by_schedule.items()
        }
        assert (
            fy2040["early_structural"]
            < fy2040["balanced_structural"]
            < fy2040["gradual_structural"]
            < fy2040[UNBLENDED_SCHEDULE_ID]
        ), fy2040

    def test_every_long_run_year_is_affected(self, by_schedule):
        """Every published FY2032-FY2050 chart year moves, not just FY2040.

        ``ped_vkt_per_capita`` rather than ``light_petrol_vkt``: the chart
        publishes the former beyond FY2030 and keeps the latter as a hidden
        leaf in the line reconciliation, which is covered separately below.
        FY2031 is excluded because the smoothstep weight is ~0 in the first
        year by design, so a difference there is not required.
        """

        unblended = _annual(
            by_schedule[UNBLENDED_SCHEDULE_ID], "current_basecase", "ped_vkt_per_capita"
        )
        balanced = _annual(
            by_schedule["balanced_structural"], "current_basecase", "ped_vkt_per_capita"
        )
        for fy in range(FIRST_EXTRAPOLATION_FY + 1, LAST_EXTRAPOLATION_FY + 1):
            assert float(unblended.loc[fy]) != float(balanced.loc[fy]), fy


class TestSelectionPreservesEverythingElse:
    @pytest.mark.parametrize("schedule", SCHEDULES)
    def test_fy2030_and_earlier_are_identical(self, by_schedule, schedule):
        """Gate: the anchor and the econometric window never move."""

        reference = by_schedule[UNBLENDED_SCHEDULE_ID]
        candidate = by_schedule[schedule]
        for scenario in ("current_basecase", "current_comparison_1"):
            for series in ("total_nltf_net_revenue", "light_petrol_vkt", "heavy_ruc_net_km"):
                left = _annual(reference, scenario, series)
                right = _annual(candidate, scenario, series)
                short_run = left.index[left.index <= ANCHOR_FY]
                assert np.array_equal(
                    left.loc[short_run].to_numpy(),
                    right.loc[short_run].to_numpy(),
                    equal_nan=True,
                ), (schedule, scenario, series)

    @pytest.mark.parametrize("schedule", SCHEDULES)
    def test_official_published_rows_are_identical(self, by_schedule, schedule):
        reference = by_schedule[UNBLENDED_SCHEDULE_ID]
        candidate = by_schedule[schedule]
        for scenario in ("befu26_official", "mbu26_official"):
            left = _annual(reference, scenario, "total_nltf_net_revenue")
            right = _annual(candidate, scenario, "total_nltf_net_revenue")
            if left.empty:
                continue
            assert np.array_equal(
                left.to_numpy(), right.to_numpy(), equal_nan=True
            ), (schedule, scenario)

    @pytest.mark.parametrize("schedule", SCHEDULES)
    def test_actual_rows_are_identical(self, by_schedule, schedule):
        reference = by_schedule[UNBLENDED_SCHEDULE_ID]
        candidate = by_schedule[schedule]
        for frame, other in ((reference, candidate),):
            left = frame[frame["row_type"].astype(str).eq("historical_actual")]
            right = other[other["row_type"].astype(str).eq("historical_actual")]
            assert len(left) == len(right)
            assert np.array_equal(
                pd.to_numeric(left["value"], errors="coerce").to_numpy(),
                pd.to_numeric(right["value"], errors="coerce").to_numpy(),
                equal_nan=True,
            ), schedule

    @pytest.mark.parametrize("schedule", SCHEDULES)
    def test_only_the_post_model_segment_changes(self, by_schedule, schedule):
        """Nothing outside FY2031-FY2050 post-model rows may move."""

        reference = by_schedule[UNBLENDED_SCHEDULE_ID]
        candidate = by_schedule[schedule]
        keys = ["scenario_name", "series_id", "time_grain", "period"]
        merged = reference.merge(candidate, on=keys, suffixes=("_ref", "_new"))
        assert not merged.empty
        changed = merged[
            (
                pd.to_numeric(merged["value_ref"], errors="coerce")
                - pd.to_numeric(merged["value_new"], errors="coerce")
            ).abs()
            > 1e-9
        ]
        if schedule == UNBLENDED_SCHEDULE_ID:
            assert changed.empty
            return
        segments = changed["forecast_segment_ref"].fillna("").astype(str)
        assert set(segments.unique()) == {POST_MODEL_SEGMENT}, sorted(
            segments.unique()
        )

    @pytest.mark.parametrize("schedule", SCHEDULES)
    def test_each_scenario_keeps_its_own_anchor(self, by_schedule, schedule):
        """Base and comparison anchor on their OWN FY2030, not a shared one."""

        rows = by_schedule[schedule]
        base = float(_annual(rows, "current_basecase", "light_petrol_vkt").loc[ANCHOR_FY])
        comparison = float(
            _annual(rows, "current_comparison_1", "light_petrol_vkt").loc[ANCHOR_FY]
        )
        assert base != comparison
        reference = by_schedule[UNBLENDED_SCHEDULE_ID]
        assert base == float(
            _annual(reference, "current_basecase", "light_petrol_vkt").loc[ANCHOR_FY]
        )
        assert comparison == float(
            _annual(reference, "current_comparison_1", "light_petrol_vkt").loc[ANCHOR_FY]
        )

    def test_comparison_scenario_also_transitions(self, by_schedule):
        """The comparison path is not left on the unblended construction."""

        unblended = _annual(
            by_schedule[UNBLENDED_SCHEDULE_ID],
            "current_comparison_1",
            "total_nltf_net_revenue",
        )
        balanced = _annual(
            by_schedule["balanced_structural"],
            "current_comparison_1",
            "total_nltf_net_revenue",
        )
        assert float(unblended.loc[2040]) != float(balanced.loc[2040])


class TestCacheKeying:
    def test_signature_changes_with_the_schedule(self, loaded):
        _, signature = loaded
        seen = {
            schedule: dashboard._shape_adjusted_signature(
                signature, schedule, SHAPE_VINTAGE
            )
            for schedule in SCHEDULES
        }
        assert len(set(seen.values())) == len(SCHEDULES)

    def test_signature_changes_with_the_shape_vintage(self, loaded):
        _, signature = loaded
        befu = dashboard._shape_adjusted_signature(
            signature, "balanced_structural", "BEFU26"
        )
        mbu = dashboard._shape_adjusted_signature(
            signature, "balanced_structural", "MBU26"
        )
        assert befu != mbu

    def test_unblended_leaves_the_signature_untouched(self, loaded):
        _, signature = loaded
        assert (
            dashboard._shape_adjusted_signature(
                signature, UNBLENDED_SCHEDULE_ID, SHAPE_VINTAGE
            )
            == signature
        )

    def test_scope_reader_defaults_for_a_legacy_eight_tuple(self):
        legacy = (
            dashboard.EV_UPTAKE_GOVERNED_OPTION,
            (),
            (),
            dashboard.FED_POLICY_PUBLISHED,
            dashboard.FED_POLICY_PUBLISHED,
            False,
            "BEFU26",
            False,
        )
        schedule, vintage = dashboard._long_run_shape_scope(legacy)
        assert schedule == UNBLENDED_SCHEDULE_ID
        assert vintage == ""


class TestShapeVintageSelection:
    def test_a_prior_shape_vintage_changes_the_long_run(self, loaded):
        """The MBU26 audit leg must not silently render as BEFU26."""

        pack, signature = loaded
        frames = {}
        for vid in ("BEFU26", "MBU26"):
            key = (
                dashboard.EV_UPTAKE_GOVERNED_OPTION,
                (),
                (),
                dashboard.FED_POLICY_PUBLISHED,
                dashboard.FED_POLICY_PUBLISHED,
                False,
                "BEFU26",
                False,
                "balanced_structural",
                vid,
            )
            adjusted_pack, adjusted_signature = dashboard._apply_long_run_shape_selection(
                pack, signature, str(PACK_DIR), key
            )
            rows, *_ = dashboard.cached_scenario_overlay_rows(
                adjusted_signature,
                dashboard.selected_sensitivity_key(
                    "Off", "Off", "Off", freight_rail_shift="Off"
                ),
                dashboard.PED_BRIDGE_DEFAULT_MODE,
                key,
                adjusted_pack,
            )
            frames[vid] = _annual(rows, "current_basecase", "ped_vkt_per_capita")
        assert float(frames["BEFU26"].loc[2045]) != float(frames["MBU26"].loc[2045])


class TestPropagationIntoDetailFrames:
    """The selection must reach the line table and residuals, not just the chart."""

    @staticmethod
    def _detail(loaded, schedule_id: str):
        pack, signature = loaded
        key = _key(schedule_id)
        adjusted_pack, adjusted_signature = dashboard._apply_long_run_shape_selection(
            pack, signature, str(PACK_DIR), key
        )
        return dashboard.cached_aligned_scenario_detail_frames(
            adjusted_signature,
            dashboard.selected_sensitivity_key(
                "Off", "Off", "Off", freight_rail_shift="Off"
            ),
            dashboard.PED_BRIDGE_DEFAULT_MODE,
            key,
            adjusted_pack,
        )

    @staticmethod
    def _line_value(frame: pd.DataFrame, series: str, fy: int) -> float:
        scoped = frame[
            frame["source_path"].astype(str).eq("Current finalist Base case")
            & frame["series_id"].astype(str).eq(series)
            & pd.to_numeric(frame["FY"], errors="coerce").eq(fy)
        ]
        return float(pd.to_numeric(scoped["value"], errors="coerce").iloc[0])

    def test_hidden_leaf_reaches_the_line_reconciliation(self, loaded):
        """light_petrol_vkt is not on the chart past FY2030; it must still move."""

        unblended, *_ = self._detail(loaded, UNBLENDED_SCHEDULE_ID)
        balanced, *_ = self._detail(loaded, "balanced_structural")
        assert self._line_value(unblended, "light_petrol_vkt", 2040) != pytest.approx(
            self._line_value(balanced, "light_petrol_vkt", 2040), rel=1e-9
        )

    def test_line_reconciliation_short_run_is_untouched(self, loaded):
        unblended, *_ = self._detail(loaded, UNBLENDED_SCHEDULE_ID)
        balanced, *_ = self._detail(loaded, "balanced_structural")
        for fy in (2026, 2028, ANCHOR_FY):
            for series in ("light_petrol_vkt", "total_nltf_net_revenue"):
                assert self._line_value(unblended, series, fy) == self._line_value(
                    balanced, series, fy
                ), (series, fy)

    def test_formula_residuals_still_close_under_the_selection(self, loaded):
        _, residuals, _, _ = self._detail(loaded, "balanced_structural")
        if residuals is None or residuals.empty or "residual" not in residuals.columns:
            pytest.skip("no residual column in this pack")
        long_run = residuals[
            pd.to_numeric(residuals["FY"], errors="coerce") >= FIRST_EXTRAPOLATION_FY
        ]
        worst = pd.to_numeric(long_run["residual"], errors="coerce").abs().max()
        assert float(worst) < 1e-6

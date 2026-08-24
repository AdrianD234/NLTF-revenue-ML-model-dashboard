"""Conflict paths must converge to the SELECTED hybrid path, not the old one.

The governed conflict window runs 2026Q1-2030Q4, entirely inside the
econometric segment. Past it, each Low/Medium/High path is expected to carry no
permanent conflict effect and to sit on the corresponding Base or comparison
path.

That was already true before this branch. What has to be proven now is that
when a structural schedule is active the conflict paths converge to the
**transitioned** Base path rather than silently remaining on the unblended
construction - which is exactly the failure mode a partially wired preview
would produce.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app as dashboard
from model_dashboard.conflict_fuel_paths import EXPECTED_PERIODS
from model_dashboard.long_run_shape_transition import UNBLENDED_SCHEDULE_ID
from model_dashboard.post_model_extrapolation import (
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "data" / "current_revenue_outlook"
CONFLICT_SCENARIOS = ("middle_east_low", "middle_east_medium", "middle_east_high")
# The production construction since the handover promotion: convergence is
# asserted against the governed default the published chart actually shows.
ACTIVE_SCHEDULE = "growth_handover_fy2035"
SHAPE_VINTAGE = "PREBU26"

# The last FY the governed conflict window touches.
CONFLICT_WINDOW_LAST_FY = max(
    int(period[:4]) + (1 if int(period[5]) >= 3 else 0) for period in EXPECTED_PERIODS
)


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


@pytest.fixture(scope="module")
def rows_by_schedule() -> dict[str, pd.DataFrame]:
    signature = dashboard.revenue_outlook_signature(PACK_DIR, ROOT)
    pack = dashboard.cached_load_revenue_outlook_pack(
        str(PACK_DIR), str(ROOT), signature, dashboard.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    out: dict[str, pd.DataFrame] = {}
    for schedule in (UNBLENDED_SCHEDULE_ID, ACTIVE_SCHEDULE):
        key = _key(schedule)
        adjusted_pack, adjusted_signature = dashboard._apply_long_run_shape_selection(
            pack, signature, str(PACK_DIR), key
        )
        frame, *_ = dashboard.cached_scenario_overlay_rows(
            adjusted_signature,
            dashboard.selected_sensitivity_key(
                "Off", "Off", "Off", freight_rail_shift="Off"
            ),
            dashboard.PED_BRIDGE_DEFAULT_MODE,
            key,
            adjusted_pack,
        )
        out[schedule] = frame
    return out


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


class TestConflictWindow:
    def test_the_window_is_the_governed_twenty_quarters(self):
        """Pin the window rather than assume where it lands.

        The fuel-price input path is 20 quarters, 2026Q1-2030Q4. Under the
        repo's June-year convention (Q3/Q4 belong to the next FY) its final
        quarters fall in FY2031, so the input window and the post-model layer
        overlap by one FY. That overlap is precisely why convergence has to be
        asserted on values rather than inferred from the calendar: the tests
        below show the decision-facing conflict effect is already exhausted at
        FY2031, so nothing survives into the transitioned layer.
        """

        assert len(EXPECTED_PERIODS) == 20
        assert EXPECTED_PERIODS[0] == "2026Q1"
        assert EXPECTED_PERIODS[-1] == "2030Q4"
        assert CONFLICT_WINDOW_LAST_FY == FIRST_EXTRAPOLATION_FY

    def test_conflict_paths_are_present_and_differ_inside_the_window(
        self, rows_by_schedule
    ):
        """Non-vacuity: the conflict effect must be real inside the window."""

        rows = rows_by_schedule[ACTIVE_SCHEDULE]
        base = _annual(rows, "current_basecase", "net_fed_revenue")
        for scenario in CONFLICT_SCENARIOS:
            conflict = _annual(rows, scenario, "net_fed_revenue")
            assert not conflict.empty, scenario
            in_window = [
                fy for fy in conflict.index if 2026 <= fy <= CONFLICT_WINDOW_LAST_FY
            ]
            assert in_window, scenario
            deltas = [
                abs(float(conflict.loc[fy]) - float(base.loc[fy])) for fy in in_window
            ]
            assert max(deltas) > 1e-6, (scenario, deltas)


class TestConvergenceAfterTheWindow:
    @pytest.mark.parametrize("scenario", CONFLICT_SCENARIOS)
    @pytest.mark.parametrize("series", ["net_fed_revenue", "total_nltf_net_revenue"])
    def test_conflict_converges_to_the_selected_hybrid_base(
        self, rows_by_schedule, scenario, series
    ):
        """After the window, the conflict path IS the transitioned Base path."""

        rows = rows_by_schedule[ACTIVE_SCHEDULE]
        base = _annual(rows, "current_basecase", series)
        conflict = _annual(rows, scenario, series)
        post_window = [
            fy
            for fy in conflict.index
            if FIRST_EXTRAPOLATION_FY <= fy <= LAST_EXTRAPOLATION_FY
        ]
        assert post_window, (scenario, series)
        for fy in post_window:
            assert float(conflict.loc[fy]) == pytest.approx(
                float(base.loc[fy]), rel=1e-9
            ), (scenario, series, fy)

    @pytest.mark.parametrize("scenario", CONFLICT_SCENARIOS)
    def test_conflict_does_not_converge_to_the_UNBLENDED_path(
        self, rows_by_schedule, scenario
    ):
        """The gate that would catch a partially wired preview.

        If the conflict paths were left on the pack's original long-run
        construction while Base was transitioned, they would match the
        unblended Base instead. They must not.
        """

        active = rows_by_schedule[ACTIVE_SCHEDULE]
        unblended = rows_by_schedule[UNBLENDED_SCHEDULE_ID]
        conflict = _annual(active, scenario, "total_nltf_net_revenue")
        unblended_base = _annual(unblended, "current_basecase", "total_nltf_net_revenue")
        # The two constructions genuinely differ at FY2040, so this comparison
        # is not vacuous.
        active_base = _annual(active, "current_basecase", "total_nltf_net_revenue")
        assert float(active_base.loc[2040]) != float(unblended_base.loc[2040])
        assert float(conflict.loc[2040]) != float(unblended_base.loc[2040]), scenario

    @pytest.mark.parametrize("scenario", CONFLICT_SCENARIOS)
    def test_no_permanent_conflict_wedge_survives(self, rows_by_schedule, scenario):
        """The conflict effect decays to zero, rather than persisting."""

        rows = rows_by_schedule[ACTIVE_SCHEDULE]
        base = _annual(rows, "current_basecase", "total_nltf_net_revenue")
        conflict = _annual(rows, scenario, "total_nltf_net_revenue")
        terminal = abs(
            float(conflict.loc[LAST_EXTRAPOLATION_FY])
            - float(base.loc[LAST_EXTRAPOLATION_FY])
        )
        assert terminal < 1e-6, (scenario, terminal)


class TestPolicyAppliedOnce:
    def test_policy_moves_the_path_once_not_twice(self, rows_by_schedule):
        """A doubled policy overlay would show as ~2x the single-application step.

        Compared against the published-policy state under the SAME schedule, so
        the only thing varying is the policy selection.
        """

        signature = dashboard.revenue_outlook_signature(PACK_DIR, ROOT)
        pack = dashboard.cached_load_revenue_outlook_pack(
            str(PACK_DIR), str(ROOT), signature, dashboard.REVENUE_OUTLOOK_SCHEMA_VERSION
        )
        values: dict[str, pd.Series] = {}
        for policy in (dashboard.FED_POLICY_PUBLISHED, dashboard.FED_POLICY_OFF):
            key = (
                dashboard.EV_UPTAKE_GOVERNED_OPTION,
                (),
                (),
                policy,
                dashboard.FED_POLICY_PUBLISHED,
                False,
                "BEFU26",
                False,
                ACTIVE_SCHEDULE,
                SHAPE_VINTAGE,
            )
            adjusted_pack, adjusted_signature = dashboard._apply_long_run_shape_selection(
                pack, signature, str(PACK_DIR), key
            )
            frame, *_ = dashboard.cached_scenario_overlay_rows(
                adjusted_signature,
                dashboard.selected_sensitivity_key(
                    "Off", "Off", "Off", freight_rail_shift="Off"
                ),
                dashboard.PED_BRIDGE_DEFAULT_MODE,
                key,
                adjusted_pack,
            )
            values[policy] = _annual(frame, "current_basecase", "net_fed_revenue")

        published = values[dashboard.FED_POLICY_PUBLISHED]
        off = values[dashboard.FED_POLICY_OFF]
        step = float(published.loc[2040]) - float(off.loc[2040])
        assert step > 0.0, step
        # The 12c uplift on FY2040 PED litres. A second application would put
        # the step at roughly twice the single-application size; bound it well
        # inside that.
        litres = float(_annual(
            rows_by_schedule[ACTIVE_SCHEDULE], "current_basecase", "ped_volume"
        ).loc[2040])
        single_application = 0.12 * litres
        assert step < 1.5 * single_application, (step, single_application)

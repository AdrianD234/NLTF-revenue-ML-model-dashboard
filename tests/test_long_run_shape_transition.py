"""Gates on the transition weight and the geometric growth-index blend.

Sections 5-7 of the anchored structural shape transition brief. These are the
properties that make the method a transparent governance assumption rather than
a hidden calibration, so they are asserted as equalities wherever the maths
makes an equality available.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_dashboard import long_run_shape_transition as lrst


class TestTransitionWeight:
    def test_weight_is_exactly_zero_at_the_anchor(self):
        """Gate 7. Exact, not approximate: the anchor cannot drift."""

        for schedule_id in lrst.SCHEDULES:
            frame = lrst.transition_weight_frame(schedule_id)
            anchor = frame.loc[frame["fy"].eq(lrst.ANCHOR_FY), "w"]
            assert float(anchor.iloc[0]) == 0.0, schedule_id

    def test_weight_is_exactly_one_at_completion(self):
        """Gate 8."""

        for schedule_id in lrst.STRUCTURAL_SCHEDULE_IDS:
            schedule = lrst.resolve_schedule(schedule_id)
            frame = lrst.transition_weight_frame(schedule_id)
            completion = frame.loc[frame["fy"].eq(schedule.completion_fy), "w"]
            assert float(completion.iloc[0]) == 1.0, schedule_id

    def test_weights_are_monotonic_and_bounded(self):
        """Gate 9."""

        for schedule_id in lrst.SCHEDULES:
            w = lrst.transition_weight_frame(schedule_id)["w"].to_numpy(dtype=float)
            assert w.min() >= 0.0 and w.max() <= 1.0, schedule_id
            assert np.all(np.diff(w) >= -1e-15), schedule_id

    def test_weight_stays_at_one_after_completion(self):
        """A completed transition does not un-complete in later years."""

        frame = lrst.transition_weight_frame("early_structural")
        after = frame[frame["fy"] > 2040]["w"].to_numpy(dtype=float)
        assert after.size > 0
        assert np.allclose(after, 1.0, atol=0.0, rtol=0.0)

    def test_unblended_candidate_is_identically_zero(self):
        frame = lrst.transition_weight_frame(lrst.UNBLENDED_SCHEDULE_ID)
        assert (frame["w"].to_numpy() == 0.0).all()
        assert (frame["model_weight"].to_numpy() == 1.0).all()

    def test_no_discontinuity_in_the_weight_path(self):
        """Smoothstep: the largest year-on-year step stays modest and smooth."""

        for schedule_id in lrst.STRUCTURAL_SCHEDULE_IDS:
            schedule = lrst.resolve_schedule(schedule_id)
            w = lrst.transition_weight_frame(schedule_id)["w"].to_numpy(dtype=float)
            steps = np.diff(w)
            span = schedule.completion_fy - schedule.anchor_fy
            # w'(u) = 6u(1-u) peaks at 1.5, so the per-year step cannot exceed
            # 1.5/span.
            assert steps.max() <= 1.5 / span + 1e-12, schedule_id
            # w''(u) = 6 - 12u peaks at |6|, so the per-year curvature cannot
            # exceed 6/span**2. A kink would break this bound; a smooth curve
            # sampled at unit steps stays comfortably inside it.
            assert np.abs(np.diff(steps)).max() <= 6.0 / span**2 + 1e-12, schedule_id
            # And the curvature changes sign exactly once - accelerate, then
            # decelerate - rather than oscillating.
            curvature = np.diff(steps)
            active = curvature[np.abs(curvature) > 1e-12]
            sign_changes = int(np.sum(np.diff(np.sign(active)) != 0))
            assert sign_changes == 1, (schedule_id, sign_changes)

    def test_the_weight_is_not_stream_specific(self):
        """No hidden per-stream hand tuning: one schedule, one weight path."""

        frame = lrst.transition_weight_frame("balanced_structural")
        assert set(frame.columns) >= {"fy", "candidate_id", "u", "w"}
        assert "series_id" not in frame.columns
        assert "stream" not in frame.columns

    def test_smoothstep_matches_its_closed_form(self):
        schedule = lrst.resolve_schedule("balanced_structural")
        for fy in range(2030, 2051):
            u = min(max((fy - 2030) / (2045 - 2030), 0.0), 1.0)
            expected = 3.0 * u**2 - 2.0 * u**3
            actual = lrst.transition_weight(
                fy, anchor_fy=schedule.anchor_fy, completion_fy=schedule.completion_fy
            )
            assert actual == pytest.approx(expected, abs=1e-15)

    def test_unknown_schedule_fails_closed(self):
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.resolve_schedule("aggressive_structural")

    def test_completion_before_anchor_fails_closed(self):
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.transition_weight(2035, anchor_fy=2030, completion_fy=2025)

    def test_candidates_frame_covers_every_governed_schedule(self):
        frame = lrst.transition_weight_candidates_frame()
        assert set(frame["candidate_id"]) == set(lrst.SCHEDULES)
        for column in (
            "fy",
            "candidate_id",
            "u",
            "w",
            "model_weight",
            "structural_weight",
            "anchor_fy",
            "completion_fy",
            "formula_id",
        ):
            assert column in frame.columns
        assert np.allclose(
            frame["model_weight"] + frame["structural_weight"], 1.0, atol=0.0
        )


class TestGeometricBlend:
    def test_blend_identity_closes(self):
        """Gate 10: the blend is exactly the log-space weighted average."""

        current = np.array([1.0, 0.97, 0.93, 0.88])
        structural = np.array([1.0, 0.99, 0.96, 0.90])
        w = np.array([0.0, 0.25, 0.6, 1.0])
        blended = lrst.geometric_blend_index(current, structural, w)
        expected = current ** (1.0 - w) * structural**w
        assert np.allclose(blended, expected, rtol=0.0, atol=1e-15)

    def test_anchor_is_a_fixed_point_for_every_weight(self):
        """Gate 11. Both indices are 1.0 at the anchor, so the blend is too."""

        for w in np.linspace(0.0, 1.0, 21):
            assert lrst.geometric_blend_index(1.0, 1.0, w) == 1.0

    def test_zero_weight_returns_the_current_index_exactly(self):
        current = np.array([1.0, 0.97, 0.93])
        blended = lrst.geometric_blend_index(current, np.array([1.0, 1.2, 1.4]), 0.0)
        assert np.allclose(blended, current, rtol=0.0, atol=1e-15)

    def test_unit_weight_returns_the_structural_index_exactly(self):
        structural = np.array([1.0, 1.02, 1.05])
        blended = lrst.geometric_blend_index(np.array([1.0, 0.9, 0.8]), structural, 1.0)
        assert np.allclose(blended, structural, rtol=0.0, atol=1e-15)

    def test_blend_is_scale_invariant(self):
        """Rescaling either index rescales the result by the same power.

        This is why the blend operates on indices: it has no opinion about the
        units of the underlying level.
        """

        current = np.array([1.0, 0.95])
        structural = np.array([1.0, 1.05])
        w = 0.4
        base = lrst.geometric_blend_index(current, structural, w)
        scaled = lrst.geometric_blend_index(current * 3.0, structural, w)
        assert np.allclose(scaled, base * 3.0 ** (1.0 - w), rtol=0.0, atol=1e-14)

    def test_completed_transition_adopts_shape_not_level(self):
        """Gates 12 and 13, as an equality.

        With w = 1 the hybrid level is anchor x structural index, so
        hybrid_t / official_t collapses to current_2030 / official_2030 for
        every year. If the constructor ever substituted an official LEVEL the
        observed ratio would move to 1.0 and this residual would blow up.
        """

        current_anchor = 29_787.438
        official = {2030: 32_691.387, 2040: 26_034.734, 2050: 11_722.365}
        for fy in (2040, 2050):
            structural_index = official[fy] / official[2030]
            hybrid_level = current_anchor * structural_index
            identity = lrst.complete_transition_ratio_identity(
                current_anchor=current_anchor,
                structural_level_anchor=official[2030],
                structural_level_fy=official[fy],
                hybrid_level_fy=hybrid_level,
            )
            assert identity["abs_residual"] < 1e-12
            assert identity["observed_ratio"] != pytest.approx(1.0, abs=1e-3)

    @pytest.mark.parametrize(
        "current, structural",
        [(0.0, 1.0), (-1.0, 1.0), (1.0, 0.0), (1.0, -0.5), (np.nan, 1.0), (1.0, np.inf)],
    )
    def test_non_positive_or_non_finite_inputs_fail_closed(self, current, structural):
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.geometric_blend_index(current, structural, 0.5)

    @pytest.mark.parametrize("weight", [-0.01, 1.01, np.nan])
    def test_out_of_range_weight_fails_closed(self, weight):
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.geometric_blend_index(1.0, 1.0, weight)


def _official_annual(values: dict[str, dict[int, float]]) -> pd.DataFrame:
    rows = [
        {"FY": fy, "series_id": series, "value": value}
        for series, by_fy in values.items()
        for fy, value in by_fy.items()
    ]
    return pd.DataFrame(rows)


def _complete_shape_source(first_fy: int = 2030, last_fy: int = 2050) -> pd.DataFrame:
    fys = range(first_fy, last_fy + 1)
    return _official_annual(
        {
            "light_petrol_vkt": {fy: 32_000.0 * 0.97 ** (fy - first_fy) for fy in fys},
            "light_ruc_net_km": {fy: 12_800.0 * 0.98 ** (fy - first_fy) for fy in fys},
            "light_bev_ruc_net_km": {fy: 3_300.0 * 1.09 ** (fy - first_fy) for fy in fys},
            "phev_ruc_net_km": {fy: 1_800.0 * 1.02 ** (fy - first_fy) for fy in fys},
            "heavy_ruc_net_km": {fy: 3_700.0 * 1.001 ** (fy - first_fy) for fy in fys},
        }
    )


class TestStructuralGrowthIndices:
    def test_every_index_is_exactly_one_at_the_anchor(self):
        frame = lrst.structural_growth_indices(
            _complete_shape_source(), vintage_id="FIXTURE"
        ).set_index("fy")
        for column in ("s_light_petrol_vkt", "s_light_ruc_pool", "s_heavy_ruc_net_km"):
            assert float(frame.at[lrst.ANCHOR_FY, column]) == 1.0

    def test_pool_index_uses_the_three_class_sum(self):
        source = _complete_shape_source()
        frame = lrst.structural_growth_indices(source, vintage_id="FIXTURE").set_index("fy")
        wide = source.pivot_table(index="FY", columns="series_id", values="value")
        for fy in (2035, 2050):
            expected_pool = (
                wide.at[fy, "light_ruc_net_km"]
                + wide.at[fy, "light_bev_ruc_net_km"]
                + wide.at[fy, "phev_ruc_net_km"]
            )
            anchor_pool = (
                wide.at[2030, "light_ruc_net_km"]
                + wide.at[2030, "light_bev_ruc_net_km"]
                + wide.at[2030, "phev_ruc_net_km"]
            )
            assert float(frame.at[fy, "s_light_ruc_pool"]) == pytest.approx(
                expected_pool / anchor_pool, abs=1e-12
            )

    def test_missing_series_fails_closed(self):
        source = _complete_shape_source()
        source = source[source["series_id"].ne("heavy_ruc_net_km")]
        with pytest.raises(lrst.LongRunShapeTransitionError, match="heavy_ruc_net_km"):
            lrst.structural_growth_indices(source, vintage_id="FIXTURE")

    def test_incomplete_year_coverage_fails_closed(self):
        source = _complete_shape_source(last_fy=2044)
        with pytest.raises(lrst.LongRunShapeTransitionError, match="does not cover"):
            lrst.structural_growth_indices(source, vintage_id="FIXTURE")

    def test_empty_source_fails_closed(self):
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.structural_growth_indices(pd.DataFrame(), vintage_id="FIXTURE")

    def test_implausible_growth_fails_closed(self):
        source = _complete_shape_source()
        mask = source["series_id"].eq("heavy_ruc_net_km") & source["FY"].eq(2035)
        source.loc[mask, "value"] = source.loc[mask, "value"] * 3.0
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.structural_growth_indices(source, vintage_id="FIXTURE")

    def test_non_positive_level_fails_closed(self):
        source = _complete_shape_source()
        mask = source["series_id"].eq("light_petrol_vkt") & source["FY"].eq(2040)
        source.loc[mask, "value"] = 0.0
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.structural_growth_indices(source, vintage_id="FIXTURE")

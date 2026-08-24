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


class TestScheduleCatalogue:
    """The governed catalogue after the growth-handover promotion.

    Six schedules: the unblended control, three level blends (still governed
    candidates) and two one-way growth handovers, of which the FY2035 handover
    is the production default.
    """

    def test_the_catalogue_carries_six_governed_schedules(self):
        assert set(lrst.SCHEDULES) == {
            lrst.UNBLENDED_SCHEDULE_ID,
            "early_structural",
            "balanced_structural",
            "gradual_structural",
            "growth_handover_fy2035",
            "growth_handover_fy2040",
        }
        assert len(lrst.STRUCTURAL_SCHEDULE_IDS) == 5
        assert lrst.UNBLENDED_SCHEDULE_ID not in lrst.STRUCTURAL_SCHEDULE_IDS

    def test_the_production_default_is_the_fy2035_growth_handover(self):
        assert (
            lrst.PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID == "growth_handover_fy2035"
        )
        schedule = lrst.resolve_schedule(
            lrst.PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID
        )
        assert schedule.is_structural
        assert schedule.is_growth_handover
        assert schedule.anchor_fy == lrst.ANCHOR_FY
        assert schedule.completion_fy == 2035

    def test_blend_kind_partitions_the_catalogue(self):
        for schedule_id, schedule in lrst.SCHEDULES.items():
            if schedule_id in ("growth_handover_fy2035", "growth_handover_fy2040"):
                assert schedule.blend_kind == lrst.GROWTH_HANDOVER_BLEND_KIND
                assert schedule.is_growth_handover
                assert schedule.blend_formula_id == lrst.GROWTH_HANDOVER_FORMULA_ID
            elif schedule_id == lrst.UNBLENDED_SCHEDULE_ID:
                assert not schedule.is_growth_handover
                assert schedule.blend_formula_id == schedule.formula_id
            else:
                assert schedule.blend_kind == lrst.LEVEL_BLEND_KIND
                assert not schedule.is_growth_handover
                assert schedule.blend_formula_id == lrst.LEVEL_BLEND_FORMULA_ID

    def test_handover_completion_years_are_pinned(self):
        assert lrst.resolve_schedule("growth_handover_fy2035").completion_fy == 2035
        assert lrst.resolve_schedule("growth_handover_fy2040").completion_fy == 2040

    def test_catalogue_frame_carries_the_blend_columns(self):
        frame = lrst.schedule_catalogue_frame()
        assert set(frame["candidate_id"]) == set(lrst.SCHEDULES)
        assert "blend_kind" in frame.columns
        assert "blend_formula_id" in frame.columns
        by_id = frame.set_index("candidate_id")
        assert by_id.at[lrst.UNBLENDED_SCHEDULE_ID, "blend_kind"] == "none"
        for schedule_id in ("early_structural", "balanced_structural", "gradual_structural"):
            assert by_id.at[schedule_id, "blend_kind"] == lrst.LEVEL_BLEND_KIND
            assert (
                by_id.at[schedule_id, "blend_formula_id"] == lrst.LEVEL_BLEND_FORMULA_ID
            )
        for schedule_id in ("growth_handover_fy2035", "growth_handover_fy2040"):
            assert by_id.at[schedule_id, "blend_kind"] == lrst.GROWTH_HANDOVER_BLEND_KIND
            assert (
                by_id.at[schedule_id, "blend_formula_id"]
                == lrst.GROWTH_HANDOVER_FORMULA_ID
            )


def _handover_paths(
    *,
    completion_fy: int = 2035,
    current_rate: float = 1.02,
    structural_rate: float = 0.97,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Anchored FY2030-FY2050 index paths with genuinely different growth.

    Current grows, structural declines, so every property asserted below is
    non-vacuous: a pull-back toward the structural curve would be visible.
    """

    fys = np.arange(lrst.ANCHOR_FY, lrst.LAST_TRANSITION_FY + 1)
    horizon = (fys - lrst.ANCHOR_FY).astype(float)
    current = current_rate**horizon
    structural = structural_rate**horizon
    w = np.asarray(
        lrst.transition_weight(
            fys, anchor_fy=lrst.ANCHOR_FY, completion_fy=completion_fy
        ),
        dtype=float,
    )
    return fys, current, structural, w


class TestGrowthHandoverIndex:
    def test_anchor_is_an_exact_fixed_point(self):
        for completion_fy in (2035, 2040):
            _, current, structural, w = _handover_paths(completion_fy=completion_fy)
            hybrid = lrst.growth_handover_index(current, structural, w)
            assert float(hybrid[0]) == 1.0, completion_fy

    def test_recurrence_matches_the_closed_form(self):
        """dlog h_t = (1-w_t) dlog c_t + w_t dlog s_t, integrated from h=1."""

        _, current, structural, w = _handover_paths()
        hybrid = lrst.growth_handover_index(current, structural, w)
        dlog = (1.0 - w[1:]) * np.diff(np.log(current)) + w[1:] * np.diff(
            np.log(structural)
        )
        expected = np.exp(np.concatenate(([0.0], np.cumsum(dlog))))
        expected[0] = 1.0
        assert np.allclose(hybrid, expected, rtol=0.0, atol=1e-15)

    def test_zero_weight_reproduces_the_current_path(self):
        _, current, structural, _ = _handover_paths()
        hybrid = lrst.growth_handover_index(
            current, structural, np.zeros_like(current)
        )
        assert np.allclose(hybrid, current, rtol=1e-12, atol=0.0)

    def test_unit_weight_reproduces_the_structural_path(self):
        _, current, structural, _ = _handover_paths()
        hybrid = lrst.growth_handover_index(current, structural, np.ones_like(current))
        assert np.allclose(hybrid, structural, rtol=1e-12, atol=0.0)

    def test_the_anchor_year_weight_is_unused(self):
        """w_t governs the growth INTO year t; there is no growth into the anchor."""

        _, current, structural, w = _handover_paths()
        perturbed = w.copy()
        perturbed[0] = 1.0
        assert np.array_equal(
            lrst.growth_handover_index(current, structural, w),
            lrst.growth_handover_index(current, structural, perturbed),
        )

    def test_post_completion_growth_equals_structural_growth(self):
        """After completion w == 1, so the hybrid grows at exactly the structural rate."""

        for completion_fy in (2035, 2040):
            fys, current, structural, w = _handover_paths(completion_fy=completion_fy)
            hybrid = lrst.growth_handover_index(current, structural, w)
            after = np.flatnonzero(fys > completion_fy)
            assert after.size > 0
            for i in after:
                assert hybrid[i] / hybrid[i - 1] == pytest.approx(
                    structural[i] / structural[i - 1], rel=1e-13
                ), (completion_fy, int(fys[i]))

    def test_ratio_to_structural_is_constant_at_the_earned_value(self):
        """The one-way, no-pull-back property.

        Post-completion, h_t / s_t is CONSTANT and equal to the ratio earned
        during the handover - NOT the anchor-year ratio (1.0 in index space),
        which is what the level blend enforces by dragging the path back to
        the structural curve.
        """

        fys, current, structural, w = _handover_paths(completion_fy=2035)
        hybrid = lrst.growth_handover_index(current, structural, w)
        ratio = hybrid / structural
        post = ratio[fys >= 2035]
        assert float(np.ptp(post)) < 1e-12
        # Earned during the handover, materially away from the anchor ratio:
        # a level blend would have forced this back to exactly 1.0.
        assert abs(float(post[0]) - 1.0) > 0.05

    def test_handover_ratio_identity_round_trip(self):
        fys, current, structural, w = _handover_paths(completion_fy=2035)
        hybrid = lrst.growth_handover_index(current, structural, w)
        hybrid_anchor_level = 1234.5
        structural_anchor_level = 987.6
        hybrid_level = hybrid_anchor_level * hybrid
        structural_level = structural_anchor_level * structural
        completion = int(np.flatnonzero(fys == 2035)[0])
        for i in np.flatnonzero(fys >= 2035):
            identity = lrst.handover_ratio_identity(
                hybrid_level_completion=float(hybrid_level[completion]),
                structural_level_completion=float(structural_level[completion]),
                structural_level_fy=float(structural_level[i]),
                hybrid_level_fy=float(hybrid_level[i]),
            )
            assert identity["abs_residual"] < 1e-12, int(fys[i])
            assert identity["observed_ratio"] == pytest.approx(
                identity["expected_completion_ratio"], rel=1e-12
            )
        # The constant is the EARNED ratio, not the anchor ratio.
        anchor_ratio = hybrid_anchor_level / structural_anchor_level
        earned = float(hybrid_level[completion] / structural_level[completion])
        assert abs(earned - anchor_ratio) > 0.05 * anchor_ratio

    def test_handover_ratio_identity_fails_closed_on_zero_levels(self):
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.handover_ratio_identity(
                hybrid_level_completion=1.0,
                structural_level_completion=0.0,
                structural_level_fy=1.0,
                hybrid_level_fy=1.0,
            )
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.handover_ratio_identity(
                hybrid_level_completion=1.0,
                structural_level_completion=1.0,
                structural_level_fy=0.0,
                hybrid_level_fy=1.0,
            )

    def test_common_index_equivariance(self):
        """The scale-invariance analogue for a growth-rate handover.

        Multiplying BOTH inputs by one common anchored index multiplies the
        output by that index: the handover has no opinion about growth the two
        sources share, only about where they differ.
        """

        fys, current, structural, w = _handover_paths()
        common = 1.01 ** (fys - lrst.ANCHOR_FY).astype(float)
        base = lrst.growth_handover_index(current, structural, w)
        shifted = lrst.growth_handover_index(current * common, structural * common, w)
        assert np.allclose(shifted, base * common, rtol=1e-12, atol=0.0)

    def test_mismatched_lengths_fail_closed(self):
        _, current, structural, w = _handover_paths()
        with pytest.raises(lrst.LongRunShapeTransitionError, match="equal-length"):
            lrst.growth_handover_index(current, structural[:-1], w[:-1])
        with pytest.raises(lrst.LongRunShapeTransitionError, match="equal-length"):
            lrst.growth_handover_index(current, structural, w[:-1])

    def test_non_1d_inputs_fail_closed(self):
        square = np.ones((2, 2))
        with pytest.raises(lrst.LongRunShapeTransitionError, match="1-D"):
            lrst.growth_handover_index(square, square, np.zeros((2, 2)))

    def test_a_single_element_path_fails_closed(self):
        with pytest.raises(lrst.LongRunShapeTransitionError, match="at least"):
            lrst.growth_handover_index(
                np.array([1.0]), np.array([1.0]), np.array([0.0])
            )

    @pytest.mark.parametrize("bad", [0.0, -0.5, np.nan, np.inf])
    def test_non_positive_or_non_finite_current_fails_closed(self, bad):
        _, current, structural, w = _handover_paths()
        broken = current.copy()
        broken[5] = bad
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.growth_handover_index(broken, structural, w)

    @pytest.mark.parametrize("bad", [0.0, -0.5, np.nan, np.inf])
    def test_non_positive_or_non_finite_structural_fails_closed(self, bad):
        _, current, structural, w = _handover_paths()
        broken = structural.copy()
        broken[5] = bad
        with pytest.raises(lrst.LongRunShapeTransitionError):
            lrst.growth_handover_index(current, broken, w)

    @pytest.mark.parametrize("anchor_value", [1.001, 0.999, 1.0 + 1e-9])
    def test_an_index_not_exactly_one_at_the_anchor_fails_closed(self, anchor_value):
        _, current, structural, w = _handover_paths()
        broken = current.copy()
        broken[0] = anchor_value
        with pytest.raises(lrst.LongRunShapeTransitionError, match="anchor"):
            lrst.growth_handover_index(broken, structural, w)
        broken_structural = structural.copy()
        broken_structural[0] = anchor_value
        with pytest.raises(lrst.LongRunShapeTransitionError, match="anchor"):
            lrst.growth_handover_index(current, broken_structural, w)

    @pytest.mark.parametrize("bad_weight", [-0.01, 1.01, np.nan])
    def test_out_of_range_weight_fails_closed(self, bad_weight):
        _, current, structural, w = _handover_paths()
        broken = w.copy()
        broken[3] = bad_weight
        with pytest.raises(lrst.LongRunShapeTransitionError, match="weight"):
            lrst.growth_handover_index(current, structural, broken)


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

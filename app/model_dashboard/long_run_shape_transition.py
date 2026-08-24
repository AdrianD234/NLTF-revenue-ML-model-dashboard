"""Anchored Structural Shape Transition: the governed FY2031-FY2050 method.

The merged FY2031-FY2050 extrapolator anchors every stream on its own FY2030
econometric level and then carries it forward on a single growth source: the
Current model's own long-horizon path for PED and Heavy RUC, and the vendored
VFM pool index for the Light RUC pool. Nothing in it moves toward the selected
official vintage's long-run shape.

This module supplies that missing transition, and does it without reviving any
of the retired machinery:

- the econometric models still own the short-run level and dynamics, and the
  FY2030 Current level remains the exact, untouched anchor;
- the selected LONG-RUN SHAPE VINTAGE supplies an externally governed long-run
  activity GROWTH SHAPE - never a level;
- VFM202405 still supplies the fleet-transition composition;
- a transparent, monotonic governance weight progressively transfers the
  post-model growth shape from the Current extrapolation to the structural
  source.

Two properties make this defensible rather than a calibration:

1. Only positive growth INDICES are blended, geometrically, in log space. The
   FY2030 anchor is a fixed point of the blend for every weight, so no
   official level is ever substituted into Current.
2. Once the transition completes, ``Current_hybrid_t / Official_t`` is
   constant and equal to ``Current_2030 / Official_2030``. Current adopts the
   official growth SHAPE while keeping its own LEVEL. See
   ``complete_transition_ratio_identity``.

The transition weight is a governance assumption about how reliance moves from
a short-run econometric extrapolation to a structural long-run source. It is
not an estimated elasticity, a model coefficient, or a forecast-probability
weight - and it is emphatically not the retired lambda, which was an
ALLOCATION weight splitting a migration total between petrol VKT and Light RUC.
Lambda stays retired; nothing here restores it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "ANCHOR_FY",
    "FLEET_COMPOSITION_SOURCE_ID",
    "GROWTH_HANDOVER_BLEND_KIND",
    "GROWTH_HANDOVER_FORMULA_ID",
    "LEVEL_BLEND_KIND",
    "LONG_RUN_SHAPE_METHOD_ID",
    "PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID",
    "SCHEDULES",
    "STRUCTURAL_SCHEDULE_IDS",
    "TRANSITION_WEIGHT_FORMULA_ID",
    "UNBLENDED_SCHEDULE_ID",
    "LongRunShapeTransitionError",
    "TransitionSchedule",
    "complete_transition_ratio_identity",
    "geometric_blend_index",
    "growth_handover_index",
    "handover_ratio_identity",
    "resolve_schedule",
    "structural_growth_indices",
    "transition_weight",
    "transition_weight_candidates_frame",
    "transition_weight_frame",
]

# Mirrors post_model_extrapolation; re-declared so this module can be reasoned
# about (and unit-tested) without importing the constructor it feeds.
ANCHOR_FY = 2030
FIRST_TRANSITION_FY = 2031
LAST_TRANSITION_FY = 2050

LONG_RUN_SHAPE_METHOD_ID = "anchored_structural_shape_transition_v1"
FLEET_COMPOSITION_SOURCE_ID = "VFM202405"

TRANSITION_WEIGHT_FORMULA_ID = "cubic_smoothstep_3u2_minus_2u3_v1"
UNBLENDED_WEIGHT_FORMULA_ID = "constant_zero_v1"

# The two governed blend mechanics. LEVEL_BLEND is the original v1 geometric
# blend of level INDICES: log I_hybrid = (1-w) log I_current + w log I_struct.
# Its growth rate carries an extra term dw * (log I_struct - log I_current) -
# a level pull toward the structural curve that re-applies every year while w
# moves, so a Current path that has already crossed the official curve keeps
# getting dragged back toward it and the delta-vs-official can oscillate
# around zero. GROWTH_HANDOVER removes exactly that term: the same weight is
# applied to the two GROWTH RATES instead, the level integrates the blended
# growth once, and once the handover completes the path simply continues on
# the structural growth rate from wherever it is - one-way, no pull-back.
LEVEL_BLEND_KIND = "level_blend"
GROWTH_HANDOVER_BLEND_KIND = "growth_handover"
GROWTH_HANDOVER_FORMULA_ID = "one_way_growth_rate_handover_v1"
LEVEL_BLEND_FORMULA_ID = "geometric_level_index_blend_v1"

UNBLENDED_SCHEDULE_ID = "unblended_current"

# The governed PRODUCTION default. This is the owner decision, recorded in one
# greppable place rather than spread across call sites: every runtime pack is
# built on this schedule unless a caller explicitly asks for another, and the
# analyst preview reads whatever the built pack recorded.
#
# growth_handover_fy2035 hands the post-model growth rate over to the
# structural source across FY2031-FY2035 and then continues on that trajectory.
# It replaced balanced_structural (the level blend completing FY2045) as the
# production default because the level blend's year-by-year pull toward the
# official curve made the cumulative delta versus the official comparator
# oscillate through zero, which mis-stated scenario risk in the long run. The
# level-blend schedules remain governed candidates for the analyst preview.
PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID = "growth_handover_fy2035"

# The official-vintage activity series the structural shape is built from.
# A vintage that does not carry all of these over FY2030-FY2050 cannot serve
# the long-run shape role.
REQUIRED_SHAPE_SERIES: tuple[str, ...] = (
    "light_petrol_vkt",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "heavy_ruc_net_km",
)

# Guards on the STRUCTURAL index, mirroring the constructor's guards on the
# Current index. A blended path cannot be safer than its inputs, so both legs
# are guarded before they are combined.
MAX_ANNUAL_GROWTH_RATE = 0.15
MIN_ANNUAL_GROWTH_RATE = -0.15
MAX_CUMULATIVE_INDEX = 4.0
MIN_CUMULATIVE_INDEX = 0.25


class LongRunShapeTransitionError(ValueError):
    """A governed input for the long-run shape transition is missing or unusable."""


@dataclass(frozen=True)
class TransitionSchedule:
    """One governed transition schedule.

    ``completion_fy is None`` marks the no-transition control, whose weight is
    identically zero. It is a first-class candidate, not the absence of one:
    it is the merged-main behaviour and the baseline every other candidate is
    measured against.
    """

    schedule_id: str
    display_name: str
    anchor_fy: int
    completion_fy: int | None
    description: str
    blend_kind: str = LEVEL_BLEND_KIND

    @property
    def is_structural(self) -> bool:
        return self.completion_fy is not None

    @property
    def is_growth_handover(self) -> bool:
        return self.is_structural and self.blend_kind == GROWTH_HANDOVER_BLEND_KIND

    @property
    def formula_id(self) -> str:
        return (
            TRANSITION_WEIGHT_FORMULA_ID
            if self.is_structural
            else UNBLENDED_WEIGHT_FORMULA_ID
        )

    @property
    def blend_formula_id(self) -> str:
        if not self.is_structural:
            return UNBLENDED_WEIGHT_FORMULA_ID
        return (
            GROWTH_HANDOVER_FORMULA_ID
            if self.is_growth_handover
            else LEVEL_BLEND_FORMULA_ID
        )


SCHEDULES: dict[str, TransitionSchedule] = {
    schedule.schedule_id: schedule
    for schedule in (
        TransitionSchedule(
            schedule_id=UNBLENDED_SCHEDULE_ID,
            display_name="Current unblended",
            anchor_fy=ANCHOR_FY,
            completion_fy=None,
            description=(
                "No structural transition. The Current post-model extrapolation "
                "carries the whole FY2031-FY2050 shape, exactly as merged main "
                "does. The control candidate."
            ),
        ),
        TransitionSchedule(
            schedule_id="early_structural",
            display_name="Early structural transition (complete FY2040)",
            anchor_fy=ANCHOR_FY,
            completion_fy=2040,
            description=(
                "Reliance moves to the structural shape over ten years. The "
                "econometric extrapolation is treated as informative only over "
                "the first decade past the estimation window."
            ),
        ),
        TransitionSchedule(
            schedule_id="balanced_structural",
            display_name="Balanced structural transition (complete FY2045)",
            anchor_fy=ANCHOR_FY,
            completion_fy=2045,
            description=(
                "Reliance moves to the structural shape over fifteen years, "
                "reaching equal weight around FY2037."
            ),
        ),
        TransitionSchedule(
            schedule_id="gradual_structural",
            display_name="Gradual structural transition (complete FY2050)",
            anchor_fy=ANCHOR_FY,
            completion_fy=2050,
            description=(
                "Reliance moves to the structural shape across the whole "
                "post-model horizon, completing only at the final year."
            ),
        ),
        TransitionSchedule(
            schedule_id="growth_handover_fy2035",
            display_name="One-way growth handover (complete FY2035)",
            anchor_fy=ANCHOR_FY,
            completion_fy=2035,
            blend_kind=GROWTH_HANDOVER_BLEND_KIND,
            description=(
                "The post-model GROWTH RATE hands over from the econometric "
                "extrapolation to the structural source across FY2031-FY2035. "
                "After the handover the path continues on the structural growth "
                "trajectory from wherever it is: no level is ever pulled back "
                "toward the official curve, so the delta versus the official "
                "comparator cannot oscillate through zero by construction. The "
                "production default."
            ),
        ),
        TransitionSchedule(
            schedule_id="growth_handover_fy2040",
            display_name="One-way growth handover (complete FY2040)",
            anchor_fy=ANCHOR_FY,
            completion_fy=2040,
            blend_kind=GROWTH_HANDOVER_BLEND_KIND,
            description=(
                "The one-way growth-rate handover spread across a decade: the "
                "econometric growth rate remains informative for longer before "
                "the structural source takes over. Same no-pull-back mechanics "
                "as the FY2035 handover."
            ),
        ),
    )
}

STRUCTURAL_SCHEDULE_IDS: tuple[str, ...] = tuple(
    schedule_id for schedule_id, schedule in SCHEDULES.items() if schedule.is_structural
)


def resolve_schedule(schedule_id: str) -> TransitionSchedule:
    """Look up a governed schedule, failing closed on an unknown id."""

    key = str(schedule_id)
    if key not in SCHEDULES:
        raise LongRunShapeTransitionError(
            f"unknown transition schedule {schedule_id!r}; "
            f"governed schedules: {', '.join(sorted(SCHEDULES))}"
        )
    return SCHEDULES[key]


# ---------------------------------------------------------------------------
# The transition weight
# ---------------------------------------------------------------------------


def transition_weight(
    fy: int | np.ndarray | pd.Series,
    *,
    anchor_fy: int,
    completion_fy: int | None,
) -> float | np.ndarray:
    """Cubic smoothstep from 0 at the anchor to 1 at completion.

        u_t = clamp((t - A) / (T - A), 0, 1)
        w_t = 3*u^2 - 2*u^3

    Chosen over a linear ramp because it has zero slope at both endpoints: the
    blended path leaves the FY2030 anchor and arrives at the structural shape
    without a kink in either place, so the seam is smooth in level AND in
    growth rate. Both endpoint values are exact (u=0 -> 0, u=1 -> 1) rather
    than approached, which is what makes gates 7 and 8 testable as equalities.
    """

    years = np.asarray(fy, dtype=float)
    if completion_fy is None:
        return np.zeros_like(years) if years.ndim else 0.0
    span = float(completion_fy) - float(anchor_fy)
    if span <= 0.0:
        raise LongRunShapeTransitionError(
            f"transition completion FY{completion_fy} must be after anchor FY{anchor_fy}."
        )
    u = np.clip((years - float(anchor_fy)) / span, 0.0, 1.0)
    w = 3.0 * u**2 - 2.0 * u**3
    return w if years.ndim else float(w)


def transition_weight_frame(
    schedule_id: str,
    *,
    first_fy: int = ANCHOR_FY,
    last_fy: int = LAST_TRANSITION_FY,
) -> pd.DataFrame:
    """Per-FY weights for one schedule, with the governance columns."""

    schedule = resolve_schedule(schedule_id)
    fys = np.arange(int(first_fy), int(last_fy) + 1, dtype=int)
    span = (
        float(schedule.completion_fy) - float(schedule.anchor_fy)
        if schedule.is_structural
        else np.nan
    )
    u = (
        np.clip((fys.astype(float) - float(schedule.anchor_fy)) / span, 0.0, 1.0)
        if schedule.is_structural
        else np.zeros_like(fys, dtype=float)
    )
    w = np.asarray(
        transition_weight(
            fys, anchor_fy=schedule.anchor_fy, completion_fy=schedule.completion_fy
        ),
        dtype=float,
    )
    frame = pd.DataFrame(
        {
            "fy": fys,
            "candidate_id": schedule.schedule_id,
            "u": u,
            "w": w,
            "model_weight": 1.0 - w,
            "structural_weight": w,
            "anchor_fy": schedule.anchor_fy,
            "completion_fy": schedule.completion_fy
            if schedule.is_structural
            else pd.NA,
            "formula_id": schedule.formula_id,
        }
    )
    _guard_weight_frame(frame, schedule)
    return frame


def _guard_weight_frame(frame: pd.DataFrame, schedule: TransitionSchedule) -> None:
    """The governed hard gates on a weight path, enforced at construction."""

    w = frame["w"].to_numpy(dtype=float)
    if not np.isfinite(w).all():
        raise LongRunShapeTransitionError(f"{schedule.schedule_id}: non-finite weight.")
    if w.min() < 0.0 or w.max() > 1.0:
        raise LongRunShapeTransitionError(
            f"{schedule.schedule_id}: weight outside [0, 1] "
            f"(min {w.min():.6f}, max {w.max():.6f})."
        )
    if np.any(np.diff(w) < -1e-15):
        raise LongRunShapeTransitionError(
            f"{schedule.schedule_id}: weight is not monotonic non-decreasing."
        )
    anchor_rows = frame.loc[frame["fy"].eq(schedule.anchor_fy), "w"]
    if len(anchor_rows) and float(anchor_rows.iloc[0]) != 0.0:
        raise LongRunShapeTransitionError(
            f"{schedule.schedule_id}: weight at the FY{schedule.anchor_fy} anchor is "
            f"{float(anchor_rows.iloc[0])!r}, must be exactly 0."
        )
    if schedule.is_structural:
        completion_rows = frame.loc[frame["fy"].eq(schedule.completion_fy), "w"]
        if len(completion_rows) and float(completion_rows.iloc[0]) != 1.0:
            raise LongRunShapeTransitionError(
                f"{schedule.schedule_id}: weight at completion FY"
                f"{schedule.completion_fy} is {float(completion_rows.iloc[0])!r}, "
                "must be exactly 1."
            )


def transition_weight_candidates_frame(
    *, first_fy: int = ANCHOR_FY, last_fy: int = LAST_TRANSITION_FY
) -> pd.DataFrame:
    """Every governed candidate schedule in one committed evidence table."""

    return pd.concat(
        [
            transition_weight_frame(schedule_id, first_fy=first_fy, last_fy=last_fy)
            for schedule_id in SCHEDULES
        ],
        ignore_index=True,
    )


# ---------------------------------------------------------------------------
# The structural growth index
# ---------------------------------------------------------------------------


def _shape_series_lookup(official_annual: pd.DataFrame, vintage_id: str) -> pd.DataFrame:
    if official_annual is None or official_annual.empty:
        raise LongRunShapeTransitionError(
            f"long-run shape vintage {vintage_id}: official annual frame is empty."
        )
    wide = official_annual.pivot_table(
        index="FY", columns="series_id", values="value", aggfunc="first"
    )
    missing_series = [s for s in REQUIRED_SHAPE_SERIES if s not in wide.columns]
    if missing_series:
        raise LongRunShapeTransitionError(
            f"long-run shape vintage {vintage_id} does not publish {missing_series}; "
            "it cannot serve the long-run shape role."
        )
    return wide


def structural_growth_indices(
    official_annual: pd.DataFrame,
    *,
    vintage_id: str,
    first_fy: int = ANCHOR_FY,
    last_fy: int = LAST_TRANSITION_FY,
) -> pd.DataFrame:
    """FY2030-normalised long-run growth indices from one official vintage.

    Every index equals exactly 1.0 at the anchor by construction. Levels are
    consumed only as ratios to the vintage's own FY2030 value, which is what
    makes this a SHAPE source rather than a level source.

    Fails closed - never silently borrows another vintage or another
    scenario - on a missing series, incomplete FY2030-FY2050 coverage, a
    non-positive or non-finite value, or a guard breach.
    """

    wide = _shape_series_lookup(official_annual, vintage_id)
    fys = list(range(int(first_fy), int(last_fy) + 1))
    missing_years = [fy for fy in fys if fy not in wide.index]
    if missing_years:
        raise LongRunShapeTransitionError(
            f"long-run shape vintage {vintage_id} does not cover FY{missing_years[:4]}; "
            f"the shape role requires complete FY{first_fy}-FY{last_fy} coverage."
        )

    scoped = wide.loc[fys, list(REQUIRED_SHAPE_SERIES)].apply(
        pd.to_numeric, errors="coerce"
    )
    if scoped.isna().to_numpy().any():
        bad = sorted(
            {
                f"{series}@FY{fy}"
                for fy in fys
                for series in REQUIRED_SHAPE_SERIES
                if pd.isna(scoped.at[fy, series])
            }
        )
        raise LongRunShapeTransitionError(
            f"long-run shape vintage {vintage_id}: non-numeric or missing values at {bad[:4]}."
        )

    pool = (
        scoped["light_ruc_net_km"]
        + scoped["light_bev_ruc_net_km"]
        + scoped["phev_ruc_net_km"]
    )
    levels = {
        "s_light_petrol_vkt": scoped["light_petrol_vkt"],
        "s_light_ruc_pool": pool,
        "s_heavy_ruc_net_km": scoped["heavy_ruc_net_km"],
    }

    frame = pd.DataFrame({"fy": fys}).set_index("fy")
    for column, series in levels.items():
        anchor = float(series.loc[int(first_fy)])
        if not np.isfinite(anchor) or anchor <= 0.0:
            raise LongRunShapeTransitionError(
                f"long-run shape vintage {vintage_id}: {column} FY{first_fy} anchor is "
                f"{anchor!r}; a growth index needs a positive anchor."
            )
        index = series.astype(float) / anchor
        _guard_structural_index(index, label=column, vintage_id=vintage_id)
        frame[column] = index
        frame[column.replace("s_", "s_level_")] = series.astype(float)

    frame["long_run_shape_vintage_id"] = vintage_id
    frame["anchor_fy"] = int(first_fy)
    return frame.reset_index()


def _guard_structural_index(values: pd.Series, *, label: str, vintage_id: str) -> None:
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise LongRunShapeTransitionError(
            f"{vintage_id}: {label} structural index contains a non-finite value."
        )
    if (array <= 0.0).any():
        raise LongRunShapeTransitionError(
            f"{vintage_id}: {label} structural index is non-positive; "
            "a level path cannot invert."
        )
    steps = values.sort_index().pct_change().dropna()
    if len(steps):
        if float(steps.max()) > MAX_ANNUAL_GROWTH_RATE:
            raise LongRunShapeTransitionError(
                f"{vintage_id}: {label} grows {float(steps.max()) * 100:.1f}% in one "
                f"year, above the {MAX_ANNUAL_GROWTH_RATE * 100:.0f}% guard."
            )
        if float(steps.min()) < MIN_ANNUAL_GROWTH_RATE:
            raise LongRunShapeTransitionError(
                f"{vintage_id}: {label} falls {float(steps.min()) * 100:.1f}% in one "
                f"year, below the {MIN_ANNUAL_GROWTH_RATE * 100:.0f}% guard."
            )
    terminal = float(values.sort_index().iloc[-1])
    if terminal > MAX_CUMULATIVE_INDEX or terminal < MIN_CUMULATIVE_INDEX:
        raise LongRunShapeTransitionError(
            f"{vintage_id}: {label} terminal index {terminal:.3f} is outside "
            f"[{MIN_CUMULATIVE_INDEX}, {MAX_CUMULATIVE_INDEX}] - implausible "
            "long-run divergence."
        )


# ---------------------------------------------------------------------------
# The blend
# ---------------------------------------------------------------------------


def geometric_blend_index(
    current_index: float | np.ndarray | pd.Series,
    structural_index: float | np.ndarray | pd.Series,
    weight: float | np.ndarray | pd.Series,
    *,
    context: str = "long-run shape blend",
) -> float | np.ndarray:
    """Blend two positive growth indices in log space.

        log(I_hybrid) = (1 - w) * log(I_current) + w * log(I_structural)

    equivalently ``I_current**(1-w) * I_structural**w``.

    Geometric rather than arithmetic because the objects being combined are
    GROWTH RATIOS, not levels: the log-space average is scale invariant, keeps
    a positive path positive, and blends compound growth rates rather than
    kilometres or dollars. It also makes the FY2030 anchor an exact fixed
    point - both indices are 1.0 there, so ``1**(1-w) * 1**w == 1`` for every
    weight, which is why the anchor cannot drift under any schedule.
    """

    current = np.asarray(current_index, dtype=float)
    structural = np.asarray(structural_index, dtype=float)
    w = np.asarray(weight, dtype=float)

    for array, label in ((current, "current"), (structural, "structural")):
        if not np.isfinite(array).all():
            raise LongRunShapeTransitionError(f"{context}: {label} index is non-finite.")
        if (array <= 0.0).any():
            raise LongRunShapeTransitionError(
                f"{context}: {label} index is non-positive; a geometric blend "
                "requires strictly positive growth indices."
            )
    if not np.isfinite(w).all() or w.min() < 0.0 or w.max() > 1.0:
        raise LongRunShapeTransitionError(f"{context}: weight outside [0, 1] or non-finite.")

    blended = np.exp((1.0 - w) * np.log(current) + w * np.log(structural))
    if not np.isfinite(blended).all():
        raise LongRunShapeTransitionError(f"{context}: blended index is non-finite.")
    return blended if blended.ndim else float(blended)


def growth_handover_index(
    current_index: np.ndarray | pd.Series,
    structural_index: np.ndarray | pd.Series,
    weight: np.ndarray | pd.Series,
    *,
    context: str = "long-run growth handover",
) -> np.ndarray:
    """One-way growth-rate handover between two anchored growth indices.

        dlog(I_hybrid)_t = (1 - w_t) * dlog(I_current)_t + w_t * dlog(I_structural)_t
        I_hybrid_anchor  = 1        (both inputs are 1.0 at the anchor)

    The arrays must be ordered by FY starting AT the anchor year, where both
    indices equal exactly 1.0. Each year's growth is a convex combination of
    the two input growth rates under the same governed weight path the level
    blend uses - but the level integrates that blended growth ONCE. Compare
    the level blend, whose growth rate carries the extra term
    ``dw * (log I_structural - log I_current)``: that term is a pull toward
    the structural LEVEL curve that re-applies while the weight moves, and it
    is what made the delta versus the official comparator oscillate around
    zero. Here the term is absent by construction, so:

    - the FY2030 anchor is an exact fixed point (the first element is 1.0);
    - after the completion year ``w == 1`` and the hybrid grows at exactly the
      structural rate, so ``I_hybrid_t / I_structural_t`` is CONSTANT from the
      completion year onward (see ``handover_ratio_identity``) - the path
      keeps the level it earned during the handover instead of being dragged
      to the anchor-year ratio;
    - the handover is one-way: no future weight change ever revisits a level
      already integrated.
    """

    current = np.asarray(current_index, dtype=float)
    structural = np.asarray(structural_index, dtype=float)
    w = np.asarray(weight, dtype=float)

    if current.ndim != 1 or current.shape != structural.shape or current.shape != w.shape:
        raise LongRunShapeTransitionError(
            f"{context}: handover inputs must be equal-length 1-D arrays."
        )
    if current.size < 2:
        raise LongRunShapeTransitionError(
            f"{context}: a growth handover needs at least the anchor year and one step."
        )
    for array, label in ((current, "current"), (structural, "structural")):
        if not np.isfinite(array).all():
            raise LongRunShapeTransitionError(f"{context}: {label} index is non-finite.")
        if (array <= 0.0).any():
            raise LongRunShapeTransitionError(
                f"{context}: {label} index is non-positive; growth rates need "
                "strictly positive index paths."
            )
        if abs(float(array[0]) - 1.0) > 1e-12:
            raise LongRunShapeTransitionError(
                f"{context}: {label} index is {float(array[0])!r} at the anchor; "
                "a growth handover requires exactly 1.0 there."
            )
    if not np.isfinite(w).all() or w.min() < 0.0 or w.max() > 1.0:
        raise LongRunShapeTransitionError(f"{context}: weight outside [0, 1] or non-finite.")

    dlog_current = np.diff(np.log(current))
    dlog_structural = np.diff(np.log(structural))
    # w_t governs the growth INTO year t, so the anchor-year weight is unused.
    w_step = w[1:]
    dlog_hybrid = (1.0 - w_step) * dlog_current + w_step * dlog_structural
    hybrid = np.exp(np.concatenate(([0.0], np.cumsum(dlog_hybrid))))
    # The anchor is an exact fixed point rather than a rounded one.
    hybrid[0] = 1.0
    if not np.isfinite(hybrid).all() or (hybrid <= 0.0).any():
        raise LongRunShapeTransitionError(f"{context}: handover index is non-finite or non-positive.")
    return hybrid


def handover_ratio_identity(
    *,
    hybrid_level_completion: float,
    structural_level_completion: float,
    structural_level_fy: float,
    hybrid_level_fy: float,
) -> dict[str, float]:
    """Evidence that a completed handover CONTINUES rather than reverts.

    At and after the completion year ``w = 1``, so the hybrid grows at exactly
    the structural rate and

        hybrid_t / structural_t == hybrid_completion / structural_completion

    holds identically for every t at or after completion. The constant is the
    ratio the path EARNED during the handover - not the anchor-year ratio the
    level blend enforces - which is precisely the one-way property: the path
    keeps going from where the handover left it, with no gravity back toward
    the official curve.
    """

    if structural_level_fy == 0.0 or structural_level_completion == 0.0:
        raise LongRunShapeTransitionError(
            "handover ratio identity needs non-zero structural levels at the "
            "completion year and the year under test."
        )
    observed = float(hybrid_level_fy) / float(structural_level_fy)
    expected = float(hybrid_level_completion) / float(structural_level_completion)
    return {
        "observed_ratio": observed,
        "expected_completion_ratio": expected,
        "abs_residual": abs(observed - expected),
    }


def complete_transition_ratio_identity(
    *,
    current_anchor: float,
    structural_level_anchor: float,
    structural_level_fy: float,
    hybrid_level_fy: float,
) -> dict[str, float]:
    """Evidence that a completed transition adopts SHAPE, not LEVEL.

    At and after the completion year ``w = 1``, so the hybrid index equals the
    structural index exactly and

        hybrid_t / official_t == current_2030 / official_2030

    holds identically. Returning both sides plus their difference makes the
    claim a checkable number in the evidence pack rather than a sentence in a
    report: if the constructor ever started substituting official levels, the
    left ratio would move to 1.0 and this residual would blow up.
    """

    if structural_level_fy == 0.0 or structural_level_anchor == 0.0:
        raise LongRunShapeTransitionError(
            "ratio identity needs non-zero official levels at the anchor and the year."
        )
    observed = float(hybrid_level_fy) / float(structural_level_fy)
    expected = float(current_anchor) / float(structural_level_anchor)
    return {
        "observed_ratio": observed,
        "expected_anchor_ratio": expected,
        "abs_residual": abs(observed - expected),
    }


def schedule_catalogue_frame() -> pd.DataFrame:
    """The governed schedule registry as a committed table."""

    return pd.DataFrame(
        [
            {
                "candidate_id": schedule.schedule_id,
                "display_name": schedule.display_name,
                "anchor_fy": schedule.anchor_fy,
                "completion_fy": schedule.completion_fy
                if schedule.is_structural
                else pd.NA,
                "is_structural": schedule.is_structural,
                "blend_kind": schedule.blend_kind if schedule.is_structural else "none",
                "blend_formula_id": schedule.blend_formula_id,
                "formula_id": schedule.formula_id,
                "long_run_shape_method_id": LONG_RUN_SHAPE_METHOD_ID,
                "fleet_composition_source_id": FLEET_COMPOSITION_SOURCE_ID,
                "description": schedule.description,
            }
            for schedule in SCHEDULES.values()
        ]
    )

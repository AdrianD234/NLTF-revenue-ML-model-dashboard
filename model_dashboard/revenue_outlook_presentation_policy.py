"""What the Revenue Outlook page is allowed to SHOW.

One place to answer three presentation questions that were previously spread
across widgets, captions, downloads and figure builders:

``REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS``
    Whether the MoT VFM Fast/Slow analyst surface - the two uptake paths, the
    Fast-Slow structural range, its audit toggle, caption and download - is on
    the public dashboard. Paused for the workshop build, NOT deleted: the
    canonical Fast/Slow source data, ``cached_vfm_scenario_paths``,
    ``cached_view_cone_band`` and their evidence all remain, so restoring the
    feature is a one-constant code change plus its tests.

``REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL``
    Whether the VFM petrol-retention sensitivity is offered as a reader
    control. The typed ``RevenueScenarioComputationKey.ped_retention_sensitivity``
    field and the backend overlay stay for compatibility and audit; with this
    off, production simply never constructs a key that carries ``True``.

``REVENUE_OUTLOOK_DISPLAY_END_FY``
    The last fiscal year any decision-facing surface may display. Governed
    packs still carry FY2051-FY2055 rows as audit material; they must not
    reach the selected view.

``REVENUE_OUTLOOK_ENABLE_METHOD_DETAIL``
    Whether the page's methodological annotations are shown: the active-lever
    and long-run-construction captions, the input-history vintage seam, the
    panel sub-captions inside the lever accordion, the forecast-uncertainty
    fan and modelled-uncertainty audit toggles, the freight-rail and e-RUC
    levers (pinned to their neutral defaults while hidden, in both the
    single-view accordion and the A/B comparison columns), the synthetic
    MBU26 rate-only counterfactual selector (pinned to the published path),
    the effective-rates chart, the 12c timing-comparison export, the
    composition and comparison sub-captions and the fleet-mix explainers.
    Hidden for the workshop build, NOT deleted: everything is a render gate,
    the underlying frames, downloads and governed packs are untouched, so
    restoring the copy is a one-constant code change.

None of these is a user-facing toggle, and none of them changes a modelled
value: every helper here filters or hides, and nothing recomputes.
"""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

__all__ = [
    "REVENUE_OUTLOOK_DISPLAY_END_FY",
    "REVENUE_OUTLOOK_ENABLE_METHOD_DETAIL",
    "REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL",
    "REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS",
    "display_end_fy",
    "method_detail_enabled",
    "display_horizon_note",
    "fiscal_year_of_quarter",
    "is_paused_vfm_uptake_basis",
    "is_vfm_analyst_layer_label",
    "june_year_within_horizon",
    "clip_frame_to_display_horizon",
    "clip_fy_options_to_display_horizon",
    "period_within_horizon",
    "public_uptake_basis_options",
    "sanitised_uptake_basis",
    "terminal_display_quarter",
]

# ---------------------------------------------------------------- feature gates
# Paused for the workshop build. Flip to True (and restore the paused tests in
# tests/test_revenue_outlook_vfm_envelope.py) to bring the analyst surface back.
REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS = False

# The petrol-retention overlay is not supported as the Base path (rolling-origin
# comparison found it worse at every horizon), so it is not offered as a reader
# control. The typed key field survives for audit and historical cache entries.
REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL = False

# Methodological annotations (captions, audit toggles, the effective-rates
# chart, the 12c timing export, the fleet-mix denominator explainer) are hidden
# for the workshop build. Flip to True to bring every annotation back at once;
# each hidden surface is a render gate on this constant and nothing else.
REVENUE_OUTLOOK_ENABLE_METHOD_DETAIL = False


def method_detail_enabled() -> bool:
    return bool(REVENUE_OUTLOOK_ENABLE_METHOD_DETAIL)

# ---------------------------------------------------------------- horizon
REVENUE_OUTLOOK_DISPLAY_END_FY = 2050


def display_end_fy() -> int:
    return int(REVENUE_OUTLOOK_DISPLAY_END_FY)


# The project's fiscal year ends in June, so FY N spans (N-1)Q3, (N-1)Q4, NQ1,
# NQ2. Both halves of that mapping are derived here rather than assumed at the
# call sites, so the terminal quarter follows the constant instead of a guess.
_FISCAL_YEAR_START_QUARTER = 3


def fiscal_quarters_of_june_year(june_year: int) -> tuple[str, str, str, str]:
    """The four calendar quarters that make up one June-ended fiscal year."""
    year = int(june_year)
    return (f"{year - 1}Q3", f"{year - 1}Q4", f"{year}Q1", f"{year}Q2")


def fiscal_year_of_quarter(period: Any) -> int | None:
    """The June-ended fiscal year a ``YYYYQn`` period belongs to.

    Returns ``None`` for anything that is not a quarter label, so callers can
    tell "not a quarter" apart from "a quarter outside the horizon".
    """
    text = str(period or "").strip().upper()
    if "Q" not in text:
        return None
    year_text, _, quarter_text = text.partition("Q")
    try:
        year = int(year_text)
        quarter = int(quarter_text)
    except ValueError:
        return None
    if quarter not in (1, 2, 3, 4):
        return None
    return year + 1 if quarter >= _FISCAL_YEAR_START_QUARTER else year


def terminal_display_quarter() -> str:
    """The last quarter any quarterly surface may show.

    Derived from :func:`fiscal_quarters_of_june_year` so it tracks the horizon
    constant and the June-year convention rather than a hardcoded literal.
    """
    return fiscal_quarters_of_june_year(display_end_fy())[-1]


def june_year_within_horizon(june_year: Any) -> bool:
    number = pd.to_numeric(june_year, errors="coerce")
    if pd.isna(number):
        # A row with no June year is not evidence of a breach; leave the
        # decision to whatever other column the caller filters on.
        return True
    return int(number) <= display_end_fy()


def period_within_horizon(period: Any) -> bool:
    """True when a ``FY2049``/``2049Q3`` style label is inside the horizon."""
    text = str(period or "").strip().upper()
    if not text:
        return True
    if text.startswith("FY"):
        digits = "".join(ch for ch in text if ch.isdigit())
        return june_year_within_horizon(int(digits)) if digits else True
    fy = fiscal_year_of_quarter(text)
    return True if fy is None else fy <= display_end_fy()


def clip_fy_options_to_display_horizon(options: Iterable[str]) -> list[str]:
    return [option for option in options if period_within_horizon(option)]


def clip_frame_to_display_horizon(
    frame: pd.DataFrame | None,
    *,
    june_year_column: str = "june_year",
    period_column: str = "period",
) -> pd.DataFrame:
    """Drop every row belonging to a fiscal year beyond the display horizon.

    Uses the June-year column where the frame has one and falls back to the
    period label otherwise, so annual and quarterly frames are filtered by the
    same rule and cannot disagree about where FY2050 ends. Frames carrying
    neither column are returned untouched - this helper never invents a
    horizon it cannot see.
    """
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    keep = pd.Series(True, index=frame.index)
    if june_year_column in frame.columns:
        years = pd.to_numeric(frame[june_year_column], errors="coerce")
        keep &= years.isna() | (years <= display_end_fy())
    if period_column in frame.columns:
        keep &= frame[period_column].map(period_within_horizon).astype(bool)
    return frame[keep].copy()


def display_horizon_note() -> str:
    return (
        f"Displayed horizon ends FY{display_end_fy()} "
        f"(last quarter {terminal_display_quarter()}). Later fiscal years remain "
        "in the governed source packs as audit material and are not shown here."
    )


# ---------------------------------------------------------------- VFM labels
def _names_a_fast_or_slow_vfm_scenario(text: Any) -> bool:
    """Shared predicate for "this label refers to VFM Fast or VFM Slow".

    Deliberately narrow: the parametric approximation to VFM *Base* also
    mentions VFM and must survive the pause, as must any official comparator
    label.
    """
    value = str(text or "").casefold()
    if "vfm" not in value:
        return False
    return any(token in value for token in ("fast", "slow"))


def is_vfm_analyst_layer_label(label: Any) -> bool:
    """Does this persisted "Show on chart" label name a paused VFM layer?

    Selections saved before the pause must be filtered out silently rather
    than raising, so a returning reader's session keeps working.
    """
    return _names_a_fast_or_slow_vfm_scenario(label)


def is_paused_vfm_uptake_basis(value: Any) -> bool:
    """Is this uptake basis one of the paused Fast/Slow compositions?

    The uptake basis is a whole-scenario input, not a chart layer: leaving it
    selectable would let a reader run the Fast/Slow composition through the
    entire engine even though the layers that displayed it are withdrawn.
    """
    return _names_a_fast_or_slow_vfm_scenario(value)


def public_uptake_basis_options(options: Iterable[str]) -> list[str]:
    """The uptake bases a reader may choose while the pause is in force."""
    if REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS:
        return list(options)
    return [option for option in options if not is_paused_vfm_uptake_basis(option)]


def sanitised_uptake_basis(value: Any, *, default: str) -> str:
    """Fall back to ``default`` when a stored basis is one of the paused pair.

    Session state outlives a deployment, so a reader who had selected VFM Fast
    before the pause must come back on VFM Base rather than silently keep
    running the withdrawn composition.
    """
    if REVENUE_OUTLOOK_ENABLE_VFM_ANALYST_LAYERS:
        return str(value)
    return default if is_paused_vfm_uptake_basis(value) else str(value)

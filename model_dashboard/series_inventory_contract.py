"""The governed inventory of what production MUST publish.

This exists because an inventory derived from the data being checked is
self-masking. If a required series disappears entirely it also disappears from
an observed inventory, so the completeness engine stops expecting it and
reports ``not_applicable`` — the most serious failure mode presenting as the
most benign status. The P1.1 evidence generator originally built its
role/series inventory that way.

Everything here is therefore a static literal or is derived from the governed
horizon constants. Nothing reads a pack. The resolved contract is also written
to a committed artifact so a review can see the full expected set, and
``test_series_inventory_contract.py`` asserts the literal and the artifact
agree — a series cannot remove itself from the expected set by vanishing.

Grain matters for units. ``light_ruc_net_km`` is published as ``net km``
quarterly and ``million km`` annually; ``ped_vkt_per_capita`` is published as
``VKT per capita`` quarterly and ``km/person`` annually. A single canonical
unit per series is therefore wrong, and the annual-only matrix could not see
it. The requirement carries the unit expected at its own grain.
"""

from __future__ import annotations

from dataclasses import dataclass

from .light_fleet_allocation import (
    EXTENDED_EVIDENCE_MAX_HORIZON,
    LAST_DECISION_GRADE_ANNUAL_FY,
    MODEL_TRAINING_CUTOFF_QUARTER,
    quarter_horizon,
)

__all__ = [
    "CONTRACT_VERSION",
    "GOVERNED_STAGES",
    "HISTORICAL_ACTUAL_KNOWN_GAPS",
    "REQUIRED_CURRENT_FYS",
    "REQUIRED_OFFICIAL_FYS",
    "REQUIRED_QUARTERS",
    "REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN",
    "SeriesRequirement",
    "expected_cell_count",
    "required_periods",
    "required_quarters",
    "resolved_contract_rows",
]

CONTRACT_VERSION = "p1_1_governed_series_inventory_v1"

# The gold-path decomposition stages plus the promoted pack itself. Every stage
# publishes the same inventory; the stage axis exists so a stage that stops
# emitting a series is caught rather than averaged away.
GOVERNED_STAGES = ("S0", "S1", "S2", "S3", "S4", "production")

REQUIRED = "required"
OPTIONAL = "optional"
NOT_APPLICABLE = "not_applicable"

# Horizon rules, named so a matrix row states which contract governs it.
RULE_CURRENT_QUARTERLY = "current_quarterly_h1_h20"
RULE_CURRENT_ANNUAL = "current_annual_through_fy2030"
RULE_OFFICIAL_ANNUAL = "official_source_horizon_fy2026_fy2055"

REVENUE_DEPENDANTS = "total_nltf_net_revenue"
KM_DEPENDANTS = "revenue_leaves;total_nltf_net_revenue"


@dataclass(frozen=True)
class SeriesRequirement:
    """One governed expectation. ``canonical_unit`` is grain-specific."""

    series_id: str
    requirement: str
    canonical_unit: str
    horizon_rule: str
    dependants: str = ""

    @property
    def is_required(self) -> bool:
        return self.requirement == REQUIRED


# --------------------------------------------------------------- period sets
def required_quarters() -> tuple[str, ...]:
    """H1..H20 after the governed training cutoff.

    Derived from the governed constants, never from a pack, and asserted to
    map back to horizons 1..20 so a change to the cutoff cannot silently
    shift the required window.
    """
    cut_year, cut_quarter = (
        int(MODEL_TRAINING_CUTOFF_QUARTER[:4]),
        int(MODEL_TRAINING_CUTOFF_QUARTER[5]),
    )
    quarters: list[str] = []
    for step in range(1, EXTENDED_EVIDENCE_MAX_HORIZON + 1):
        index = (cut_quarter - 1) + step
        period = f"{cut_year + index // 4}Q{index % 4 + 1}"
        if quarter_horizon(period) != step:
            raise AssertionError(f"horizon derivation broke at {period}: expected H{step}")
        quarters.append(period)
    return tuple(quarters)


REQUIRED_QUARTERS = required_quarters()
# FY2025 is the anchor year the forecast joins onto; FY2026..FY2030 are the
# decision-grade forecast years. FY2031+ is withheld by the governed rule.
FIRST_CURRENT_ANNUAL_FY = 2025
REQUIRED_CURRENT_FYS = tuple(range(FIRST_CURRENT_ANNUAL_FY, LAST_DECISION_GRADE_ANNUAL_FY + 1))
# The official comparator runs to its own source horizon, not ours.
FIRST_OFFICIAL_FY = 2026
LAST_OFFICIAL_FY = 2055
REQUIRED_OFFICIAL_FYS = tuple(range(FIRST_OFFICIAL_FY, LAST_OFFICIAL_FY + 1))

# --------------------------------------------------------------- series sets
_REVENUE_SERIES = (
    "gross_fed_revenue",
    "gross_ped_revenue",
    "heavy_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "light_ruc_net_revenue",
    "net_fed_revenue",
    "net_mvr_revenue",
    "phev_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
    "total_ruc_net_revenue",
)
_ANNUAL_KM_SERIES = (
    "heavy_ruc_net_km",
    "light_bev_ruc_net_km",
    "light_ruc_net_km",
    "phev_ruc_net_km",
)
# Quarterly publishes native activity only: the three modelled streams.
_QUARTERLY_KM_SERIES = ("heavy_ruc_net_km", "light_ruc_net_km")

_ANNUAL_CONTRACT: tuple[SeriesRequirement, ...] = (
    tuple(
        SeriesRequirement(series, REQUIRED, "million_nzd", RULE_CURRENT_ANNUAL, REVENUE_DEPENDANTS)
        for series in _REVENUE_SERIES
    )
    + tuple(
        SeriesRequirement(series, REQUIRED, "million_km", RULE_CURRENT_ANNUAL, KM_DEPENDANTS)
        for series in _ANNUAL_KM_SERIES
    )
    + (
        SeriesRequirement("ped_vkt_per_capita", REQUIRED, "km_per_person", RULE_CURRENT_ANNUAL, "gross_ped_revenue"),
        SeriesRequirement("ped_volume", REQUIRED, "million_litres", RULE_CURRENT_ANNUAL, "gross_ped_revenue"),
    )
)

# The quarterly km declaration is stage-dependent, and legitimately so. The
# composition overlay between S1 and S2 divides quarterly km by 1e6 and
# relabels in the same step (3_791_499_897 net km -> 3_791.4999 million km),
# which is the unit contract working rather than a defect. Stages at or before
# the conversion publish raw km; stages after it publish millions. The
# promoted pack stores the pre-conversion form. Pinning one unit for all
# stages would either reject production or hide a genuine relabel, so the
# boundary is named here.
QUARTERLY_KM_RAW_STAGES = ("production", "S0", "S1")
QUARTERLY_KM_MILLION_STAGES = ("S2", "S3", "S4")
QUARTERLY_KM_CONVERSION_BOUNDARY = "S1->S2 composition overlay"


def _quarterly_contract(stage: str) -> tuple[SeriesRequirement, ...]:
    unit = "km" if stage in QUARTERLY_KM_RAW_STAGES else "million_km"
    return tuple(
        SeriesRequirement(series, REQUIRED, unit, RULE_CURRENT_QUARTERLY, KM_DEPENDANTS)
        for series in _QUARTERLY_KM_SERIES
    ) + (
        SeriesRequirement(
            "ped_vkt_per_capita", REQUIRED, "km_per_person", RULE_CURRENT_QUARTERLY, "gross_ped_revenue"
        ),
    )


_QUARTERLY_CONTRACT: tuple[SeriesRequirement, ...] = _quarterly_contract("production")

_OFFICIAL_CONTRACT: tuple[SeriesRequirement, ...] = tuple(
    SeriesRequirement(item.series_id, item.requirement, item.canonical_unit, RULE_OFFICIAL_ANNUAL, item.dependants)
    for item in _ANNUAL_CONTRACT
)

# The official comparator publishes no quarterly rows. Stated explicitly so a
# reviewer sees a decision rather than an omission.
_OFFICIAL_QUARTERLY_CONTRACT: tuple[SeriesRequirement, ...] = tuple(
    SeriesRequirement(item.series_id, NOT_APPLICABLE, item.canonical_unit, RULE_OFFICIAL_ANNUAL,
                      "official source supplies no quarterly grain")
    for item in _QUARTERLY_CONTRACT
)

CURRENT_ROLES = ("basecase", "comparison")

# Historical actuals are evidence, not model output, and are bounded by their
# sources. These two cells are absent because the per-capita series needs a
# population denominator that begins FY2003. Enumerated so the gap is a known
# exception rather than an unexplained hole or a silently relaxed rule.
HISTORICAL_ACTUAL_KNOWN_GAPS = (
    ("ped_vkt_per_capita", "FY2001"),
    ("ped_vkt_per_capita", "FY2002"),
)


def _build() -> dict[tuple[str, str, str], tuple[SeriesRequirement, ...]]:
    contract: dict[tuple[str, str, str], tuple[SeriesRequirement, ...]] = {}
    for stage in GOVERNED_STAGES:
        quarterly = _quarterly_contract(stage)
        for role in CURRENT_ROLES:
            contract[(stage, role, "june_year")] = _ANNUAL_CONTRACT
            contract[(stage, role, "quarterly")] = quarterly
        contract[(stage, "official_comparator", "june_year")] = _OFFICIAL_CONTRACT
        contract[(stage, "official_comparator", "quarterly")] = _OFFICIAL_QUARTERLY_CONTRACT
    return contract


REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN = _build()


def required_periods(role: str, grain: str) -> tuple[str, ...]:
    """The governed period set for a role and grain."""
    if str(grain) == "quarterly":
        return REQUIRED_QUARTERS if str(role) in CURRENT_ROLES else ()
    if str(role) == "official_comparator":
        return tuple(f"FY{fy}" for fy in REQUIRED_OFFICIAL_FYS)
    return tuple(f"FY{fy}" for fy in REQUIRED_CURRENT_FYS)


def resolved_contract_rows() -> list[dict[str, object]]:
    """Flatten the contract for the committed artifact and its equality gate."""
    rows: list[dict[str, object]] = []
    for (stage, role, grain), items in sorted(REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN.items()):
        periods = required_periods(role, grain)
        for item in items:
            rows.append(
                {
                    "contract_version": CONTRACT_VERSION,
                    "stage": stage,
                    "scenario_role": role,
                    "time_grain": grain,
                    "series_id": item.series_id,
                    "requirement": item.requirement,
                    "canonical_unit": item.canonical_unit,
                    "horizon_rule": item.horizon_rule,
                    "dependants": item.dependants,
                    "required_period_count": len(periods) if item.is_required else 0,
                    "first_period": periods[0] if periods and item.is_required else "",
                    "last_period": periods[-1] if periods and item.is_required else "",
                }
            )
    return rows


def expected_cell_count() -> int:
    """Total governed required cells across every stage, role and grain."""
    total = 0
    for (stage, role, grain), items in REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN.items():
        total += len(required_periods(role, grain)) * sum(1 for item in items if item.is_required)
    return total

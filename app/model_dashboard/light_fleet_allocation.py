"""The single canonical light-fleet allocation engine.

Every decision-facing consumer - runtime pack construction, Revenue Outlook,
the Fleet Mix explorer, scenario comparison, conflict and policy extracts,
downloads and reconciliation tooling - must allocate light vehicle kilometres
through :func:`allocate_light_fleet`. The formula is defined here once so it
cannot drift between app.py, the pack builders and the extract scripts.

The contract
------------

The Light RUC econometric model estimates **conventional** light RUC
kilometres. Its target is conventional-only in every historical observation,
so its forward output is the conventional class, not a total pool::

    conventional = raw Light RUC model forecast
    base_pool    = conventional / VFM_Base_conventional_share
    BEV          = base_pool * VFM_Base_BEV_share
    PHEV         = base_pool * VFM_Base_PHEV_share

``base_pool`` is the aggregate light RUC activity anchor. Alternative uptake
settings (Fast, Slow, custom) **reallocate that same pool** and never resize
it: a fleet-composition control must not act as an aggregate travel-demand
control. Each scenario derives its own base pool from its own raw conventional
forecast before composition is applied.

VFM Base shares apply immediately from the first forecast year. No seam blend
is used: the FY2025 actual conventional share sits above the whole VFM
Base/Fast/Slow cone, so blending toward it pushes the share vector outside the
cone, and a multi-year blend defers the adjustment into a larger later step.
See artifacts/fleet_allocation_semantics/checkpoint_3_final_design_verdict.md.

The retired lambda transfer
---------------------------

The superseded construction subtracted a migration total from both the petrol
and conventional Light RUC streams::

    light_ruc_net_km = raw modelled - lambda * M          # RETIRED
    light_petrol_vkt = raw PED VKT  - (1 - lambda) * M    # RETIRED

That conserved a "light mobility universe" built from two conventional-only
inputs while allocating it at proportions drawn from a universe that contains
BEV and PHEV kilometres, so the EV classes were funded by reducing both
conventional forecasts. No value produced here may reproduce those levels.

Horizon policy
--------------

Share expansion divides by a conventional share that falls over time, so it
amplifies without bound at long horizons. It is defensible only inside the
supported forecast horizon, and this module fails closed beyond it rather than
publishing a divergent number behind a warning label.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

__all__ = [
    "ALLOCATION_BASIS_ID",
    "AVAILABILITY_AVAILABLE",
    "AVAILABILITY_UNAVAILABLE",
    "CONVENTIONAL_ANCHOR_SERIES_ID",
    "DEPRECATED_TOTAL_SERIES_ID",
    "LAST_DECISION_GRADE_ANNUAL_FY",
    "LAST_DECISION_GRADE_QUARTER",
    "UNAVAILABLE_REASON",
    "VFM_SCENARIO_BY_UPTAKE_BASIS",
    "LightFleetAllocation",
    "allocate_light_fleet",
    "annual_availability",
    "composition_shares",
    "june_year_quarters",
    "quarter_horizon",
    "quarterly_availability",
    "vfm_share_table",
]

ALLOCATION_BASIS_ID = "conventional_anchor_vfm_composition_v1"

# The raw Light RUC model output is the conventional class. The old identifier
# named it as though it were a total pool, which is what invited the defect.
CONVENTIONAL_ANCHOR_SERIES_ID = "current_light_ruc_conventional_modelled_km"
DEPRECATED_TOTAL_SERIES_ID = "current_light_ruc_total_modelled_km"

VFM_DEFAULT_SCENARIO = "Base_EV"
VFM_SCENARIO_BY_UPTAKE_BASIS = {
    "MoT VFM base": "Base_EV",
    "MoT VFM fast": "Fast_EV",
    "MoT VFM slow": "Slow_EV",
}

# Horizon governance. The model training cutoff is 2025Q4, so 2026Q1 is H1 and
# horizon = 4 * (year - 2026) + quarter. H20 is 2030Q4; 2031Q1 is H21.
MODEL_TRAINING_CUTOFF_QUARTER = "2025Q4"
EXTENDED_EVIDENCE_MAX_HORIZON = 20
LAST_DECISION_GRADE_QUARTER = "2030Q4"
# FY2030 = 2029Q3..2030Q2, all within H20. FY2031 straddles H19-H22.
LAST_DECISION_GRADE_ANNUAL_FY = 2030

AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_UNAVAILABLE = "unavailable_pending_structural_light_ruc_bridge"
UNAVAILABLE_REASON = "conventional_anchor_share_expansion_not_defensible_beyond_h20"

SHARE_CLOSURE_TOLERANCE = 1e-9
_CLASS_KEYS = ("conventional", "bev", "phev")


@dataclass(frozen=True)
class LightFleetAllocation:
    """One scenario-year light RUC allocation, with full lineage."""

    june_year: int
    scenario_name: str
    conventional_anchor_km: float
    base_pool_km: float
    conventional_km: float
    light_bev_km: float
    phev_km: float
    conventional_share: float
    light_bev_share: float
    phev_share: float
    base_conventional_share: float
    uptake_basis: str
    vfm_scenario: str
    allocation_basis: str
    source_lineage: str
    availability_status: str
    unavailable_reason: str
    horizon_state: str
    is_actual_anchor: bool
    closure_residual_km: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------- VFM shares


@lru_cache(maxsize=8)
def _vfm_table(repo_root_text: str) -> pd.DataFrame:
    path = Path(repo_root_text) / "data" / "vfm_202405" / "vfm_vkt_shares.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Governed MoT VFM 202405 uptake shares are unavailable: {path}. "
            "Light fleet allocation refuses to fall back to an ungoverned split."
        )
    frame = pd.read_csv(path)
    required = {
        "scenario",
        "june_year",
        "light_ruc_conventional_share",
        "light_ruc_bev_share",
        "light_ruc_phev_share",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"VFM uptake share table is missing columns: {sorted(missing)}")
    return frame


def vfm_share_table(repo_root: Path | str, scenario: str = VFM_DEFAULT_SCENARIO) -> pd.DataFrame:
    """Conventional/BEV/PHEV shares of the light RUC pool, indexed by June year."""
    frame = _vfm_table(str(Path(repo_root).resolve()))
    block = frame[frame["scenario"].astype(str).eq(scenario)]
    if block.empty:
        raise KeyError(f"VFM scenario {scenario!r} is not present in the governed share table.")
    out = block.set_index("june_year")[
        ["light_ruc_conventional_share", "light_ruc_bev_share", "light_ruc_phev_share"]
    ].astype(float)
    out.columns = list(_CLASS_KEYS)
    return out.sort_index()


def composition_shares(
    june_year: int,
    *,
    repo_root: Path | str,
    uptake_basis: str | None = None,
    custom_shares: Mapping[str, float] | None = None,
) -> tuple[dict[str, float], str]:
    """Return the (normalised) selected class shares and the VFM scenario used.

    ``custom_shares`` wins when supplied, so a custom uptake lever can drive
    composition without inventing a new VFM scenario. Everything is normalised
    to sum to exactly one, and refuses non-positive vectors rather than
    silently rescaling a degenerate split.
    """
    if custom_shares is not None:
        raw = {key: float(custom_shares.get(key, 0.0)) for key in _CLASS_KEYS}
        vfm_scenario = "custom_uptake_levers"
    else:
        scenario = VFM_SCENARIO_BY_UPTAKE_BASIS.get(str(uptake_basis or ""), VFM_DEFAULT_SCENARIO)
        table = vfm_share_table(repo_root, scenario)
        if june_year not in table.index:
            raise KeyError(f"VFM scenario {scenario!r} has no shares for FY{june_year}.")
        raw = {key: float(table.loc[june_year, key]) for key in _CLASS_KEYS}
        vfm_scenario = scenario
    total = sum(raw.values())
    if total <= 0.0 or any(value < 0.0 for value in raw.values()):
        raise ValueError(f"Composition shares for FY{june_year} are not a valid split: {raw}")
    return {key: value / total for key, value in raw.items()}, vfm_scenario


# ------------------------------------------------------------ horizon policy


def june_year_quarters(june_year: int) -> tuple[str, ...]:
    """The four calendar quarters of a New Zealand June year."""
    return (
        f"{june_year - 1}Q3",
        f"{june_year - 1}Q4",
        f"{june_year}Q1",
        f"{june_year}Q2",
    )


def quarter_horizon(period: str, cutoff: str = MODEL_TRAINING_CUTOFF_QUARTER) -> int:
    """Forecast horizon in quarters after the training cutoff (H1 = first)."""
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    cut_year, cut_quarter = int(str(cutoff)[:4]), int(str(cutoff)[5])
    return (year - cut_year) * 4 + (quarter - cut_quarter)


def quarterly_availability(period: str) -> tuple[str, str]:
    """(availability_status, unavailable_reason) for one forecast quarter."""
    if quarter_horizon(period) > EXTENDED_EVIDENCE_MAX_HORIZON:
        return AVAILABILITY_UNAVAILABLE, UNAVAILABLE_REASON
    return AVAILABILITY_AVAILABLE, ""


def annual_availability(june_year: int) -> tuple[str, str]:
    """A June year publishes only when all four of its quarters are available.

    FY2030 is the last fully available June year: its quarters are 2029Q3
    (H15) through 2030Q2 (H18). FY2031 straddles H19-H22 and is withheld even
    though two of its quarters are individually inside H20.
    """
    statuses = [quarterly_availability(period)[0] for period in june_year_quarters(june_year)]
    if all(status == AVAILABILITY_AVAILABLE for status in statuses):
        return AVAILABILITY_AVAILABLE, ""
    return AVAILABILITY_UNAVAILABLE, UNAVAILABLE_REASON


def horizon_state(june_year: int, last_actual_fy: int) -> str:
    if june_year <= last_actual_fy:
        return "actual_anchor"
    if june_year <= last_actual_fy + 3:
        return "backtest_supported_h1_h12"
    if june_year <= LAST_DECISION_GRADE_ANNUAL_FY:
        return "extended_conditional_evidence_h13_h20"
    return "unvalidated_extrapolation_h21_plus"


# ------------------------------------------------------------- the allocator


def allocate_light_fleet(
    june_year: int,
    conventional_anchor_km: float | None,
    *,
    repo_root: Path | str,
    scenario_name: str = "",
    uptake_basis: str | None = None,
    custom_shares: Mapping[str, float] | None = None,
    actual_classes: Mapping[str, float] | None = None,
    last_actual_fy: int = 2025,
    source_lineage: str = "",
) -> LightFleetAllocation:
    """Allocate one scenario-year into conventional, BEV and PHEV kilometres.

    ``actual_classes`` short-circuits the construction: an actual June year
    publishes its observed class values untouched, and no share vector is
    applied to it.

    ``base_pool`` is always derived from the **VFM Base** conventional share so
    that selecting Fast, Slow or a custom lever reallocates a fixed pool rather
    than resizing aggregate light RUC travel.
    """
    availability, reason = annual_availability(june_year)
    state = horizon_state(june_year, last_actual_fy)
    is_actual = june_year <= last_actual_fy

    if is_actual and actual_classes is not None:
        conventional = float(actual_classes["conventional"])
        bev = float(actual_classes["bev"])
        phev = float(actual_classes["phev"])
        pool = conventional + bev + phev
        shares = (
            {key: value / pool for key, value in zip(_CLASS_KEYS, (conventional, bev, phev))}
            if pool > 0
            else dict.fromkeys(_CLASS_KEYS, 0.0)
        )
        return LightFleetAllocation(
            june_year=int(june_year),
            scenario_name=str(scenario_name),
            conventional_anchor_km=conventional,
            base_pool_km=pool,
            conventional_km=conventional,
            light_bev_km=bev,
            phev_km=phev,
            conventional_share=shares["conventional"],
            light_bev_share=shares["bev"],
            phev_share=shares["phev"],
            base_conventional_share=shares["conventional"],
            uptake_basis=str(uptake_basis or ""),
            vfm_scenario="actual_anchor",
            allocation_basis=ALLOCATION_BASIS_ID,
            source_lineage=source_lineage or "observed actual class values",
            availability_status=AVAILABILITY_AVAILABLE,
            unavailable_reason="",
            horizon_state=state,
            is_actual_anchor=True,
            closure_residual_km=pool - (conventional + bev + phev),
        )

    if availability != AVAILABILITY_AVAILABLE or conventional_anchor_km is None:
        return LightFleetAllocation(
            june_year=int(june_year),
            scenario_name=str(scenario_name),
            conventional_anchor_km=float("nan")
            if conventional_anchor_km is None
            else float(conventional_anchor_km),
            base_pool_km=float("nan"),
            conventional_km=float("nan"),
            light_bev_km=float("nan"),
            phev_km=float("nan"),
            conventional_share=float("nan"),
            light_bev_share=float("nan"),
            phev_share=float("nan"),
            base_conventional_share=float("nan"),
            uptake_basis=str(uptake_basis or ""),
            vfm_scenario="",
            allocation_basis=ALLOCATION_BASIS_ID,
            source_lineage=source_lineage,
            availability_status=availability
            if availability != AVAILABILITY_AVAILABLE
            else "missing_conventional_anchor",
            unavailable_reason=reason or "missing conventional anchor forecast",
            horizon_state=state,
            is_actual_anchor=False,
            closure_residual_km=float("nan"),
        )

    anchor = float(conventional_anchor_km)
    if anchor <= 0.0:
        raise ValueError(
            f"Conventional Light RUC anchor for FY{june_year} is not positive ({anchor}); "
            "refusing to expand a non-positive anchor into a pool."
        )

    # The base pool is always VFM Base: presets reallocate it, never resize it.
    base_shares, _ = composition_shares(june_year, repo_root=repo_root, uptake_basis=None)
    base_conventional_share = base_shares["conventional"]
    if base_conventional_share <= 0.0:
        raise ValueError(
            f"VFM Base conventional share for FY{june_year} is not positive; "
            "share expansion is undefined."
        )
    base_pool = anchor / base_conventional_share

    selected, vfm_scenario = composition_shares(
        june_year,
        repo_root=repo_root,
        uptake_basis=uptake_basis,
        custom_shares=custom_shares,
    )
    conventional = base_pool * selected["conventional"]
    bev = base_pool * selected["bev"]
    phev = base_pool * selected["phev"]

    return LightFleetAllocation(
        june_year=int(june_year),
        scenario_name=str(scenario_name),
        conventional_anchor_km=anchor,
        base_pool_km=base_pool,
        conventional_km=conventional,
        light_bev_km=bev,
        phev_km=phev,
        conventional_share=selected["conventional"],
        light_bev_share=selected["bev"],
        phev_share=selected["phev"],
        base_conventional_share=base_conventional_share,
        uptake_basis=str(uptake_basis or ""),
        vfm_scenario=vfm_scenario,
        allocation_basis=ALLOCATION_BASIS_ID,
        source_lineage=source_lineage
        or "raw Light RUC conventional model forecast; MoT VFM 202405 uptake shares",
        availability_status=AVAILABILITY_AVAILABLE,
        unavailable_reason="",
        horizon_state=state,
        is_actual_anchor=False,
        closure_residual_km=base_pool - (conventional + bev + phev),
    )


def allocate_many(
    rows: Iterable[Mapping[str, Any]],
    *,
    repo_root: Path | str,
    uptake_basis: str | None = None,
) -> pd.DataFrame:
    """Vectorised convenience wrapper returning one row per allocation."""
    records = [
        allocate_light_fleet(
            int(row["june_year"]),
            row.get("conventional_anchor_km"),
            repo_root=repo_root,
            scenario_name=str(row.get("scenario_name", "")),
            uptake_basis=row.get("uptake_basis", uptake_basis),
            actual_classes=row.get("actual_classes"),
            last_actual_fy=int(row.get("last_actual_fy", 2025)),
            source_lineage=str(row.get("source_lineage", "")),
        ).as_dict()
        for row in rows
    ]
    return pd.DataFrame(records)

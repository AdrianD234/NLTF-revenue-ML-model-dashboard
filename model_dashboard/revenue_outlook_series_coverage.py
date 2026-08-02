"""Series identity, official-row coverage and quarterly display for Revenue Outlook.

Two governance gaps are closed here, and they share one root cause: what the
Revenue Outlook selector OFFERS and what the runtime MATERIALISES are decided
in different places, and they had drifted apart.

**Official coverage.** Every runtime chart-row builder in ``revenue_outlook``
filters on ``DISPLAY_SERIES_ORDER`` before emitting a row. ``light_petrol_vkt``
is not in that list, so its published BEFU26 and MBU26 annual rows - which do
exist, in both vintages, over FY2003-FY2055 - are dropped before they can
become chart rows. The selector offers the series anyway, because
``app._revenue_outlook_stream_options`` adds the label by hand once its two PED
companions are present. The result is a selectable series with no official
comparator line. ``official_rows_for_series`` materialises those rows straight
from the registered vintage packs, in the governed chart-row schema, without
touching the membership list: nothing that publishes today changes.

**Quarterly coverage.** Only three series carry native quarterly rows
(``ped_vkt_per_capita``, ``light_ruc_net_km``, ``heavy_ruc_net_km``), and only
for the current-model traces. Everything else is disaggregated from its June-year
value live, on every Streamlit rerun, by a Denton solve. That derivation was
undeclared - no contract said which series may be split, by what rule, against
what seasonal evidence, or how far. This module declares it:
``QUARTERLY_DISPLAY_CONTRACT`` carries one row per selectable series, and
``derive_quarterly_rows`` is the single governed builder. The derived rows are
labelled ``derived_quarterly_from_governed_annual`` and never presented as
published quarterly data.

Two rules bind every path here:

* the decision-facing display horizon ends at **FY2050**. Official annual
  sources publish to FY2055; those June years and their quarters are withheld
  from display by ``display_horizon_filter``, not by any caller remembering to.
* a derived quarterly year reconciles to its annual anchor **exactly**. The
  Denton solve constrains it and a final residual correction removes the
  floating-point remainder, so ``sum(quarters) == annual`` bit for bit.

Nothing here loads a workbook, and nothing here mutates a governed pack.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .forecast_imports import june_year_quarters
from .light_fleet_allocation import MODEL_TRAINING_CUTOFF_QUARTER
from .official_vintage import (
    load_official_vintage,
    official_comparator_scenario_name,
    official_comparator_trace_name,
    official_vintage_choices,
    official_vintage_entry,
)
from .revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    DISPLAY_SERIES_ORDER,
    REVENUE_FIRST_FORECAST_FY,
    _add_canonical_join_keys,
    _runtime_chart_columns,
    _runtime_chart_record,
)
from .revenue_source_pack import REVENUE_LAST_COMPLETE_ACTUAL_FY
from .unit_contract import display_scale_for

__all__ = [
    "COVERAGE_ROW_TYPE_DERIVED",
    "COVERAGE_ROW_TYPE_NATIVE",
    "COVERAGE_ROW_TYPE_OFFICIAL_ANNUAL",
    "CONTRACT_VERSION",
    "DISPLAY_HORIZON_LAST_FY",
    "DISPLAY_HORIZON_LAST_QUARTER",
    "QUARTERLY_DISPLAY_CONTRACT",
    "QUARTERLY_DISPLAY_PACK_DIR",
    "QuarterlyDisplayContract",
    "QuarterlyDisplayPack",
    "QuarterlyDisplayPackError",
    "QuarterlyDisplayPackMissing",
    "QuarterlyDisplayPackStale",
    "RECONCILIATION_ABS_TOLERANCE",
    "RECONCILIATION_REL_TOLERANCE",
    "SeriesCoverageError",
    "annual_reconciliation_audit",
    "build_quarterly_display_pack",
    "canonical_series_id",
    "clear_caches",
    "contract_for_series",
    "derive_quarterly_rows",
    "display_horizon_filter",
    "governed_policy_step_quarters",
    "interpolate_end_of_period_quarters",
    "load_quarterly_display_pack",
    "missing_official_rows",
    "official_rows_for_series",
    "quarterly_contract_frame",
    "quarterly_coverage_status",
    "quarterly_display_pack_source_digest",
    "quarterly_rows_for_selected_series",
    "selectable_series_ids",
    "series_display_label",
]


class SeriesCoverageError(ValueError):
    """A series, label or grain was requested that the contract does not govern."""


CONTRACT_VERSION = "revenue-outlook-quarterly-display-contract-v1"
PACK_SCHEMA_VERSION = "nltf-revenue-outlook-quarterly-display-v1"
BUILDER_VERSION = "1"

# The decision-facing display horizon. Official annual sources run to FY2055;
# the dashboard stops at FY2050 and no FY2051+ display row may be generated.
DISPLAY_HORIZON_LAST_FY = 2050
DISPLAY_HORIZON_LAST_QUARTER = f"{DISPLAY_HORIZON_LAST_FY}Q2"

QUARTERLY_DISPLAY_PACK_DIR = Path("data") / "revenue_outlook_quarterly_display"
_REBUILD_COMMAND = "python scripts/build_revenue_outlook_quarterly_display_pack.py"

# --------------------------------------------------------------- vocabularies

# How the published ANNUAL number relates to its own four quarters.
ANNUAL_SEMANTICS_SUM = "sum"
ANNUAL_SEMANTICS_MEAN = "mean"
ANNUAL_SEMANTICS_END_OF_PERIOD = "end_of_period"
ANNUAL_SEMANTICS_RATE = "rate"
ANNUAL_SEMANTICS_FIXED = "fixed"
ANNUAL_SEMANTICS = (
    ANNUAL_SEMANTICS_SUM,
    ANNUAL_SEMANTICS_MEAN,
    ANNUAL_SEMANTICS_END_OF_PERIOD,
    ANNUAL_SEMANTICS_RATE,
    ANNUAL_SEMANTICS_FIXED,
)

QUARTERLY_SOURCE_NATIVE = "native"
QUARTERLY_SOURCE_DERIVED = "derived"
QUARTERLY_SOURCE_UNAVAILABLE = "unavailable"
QUARTERLY_SOURCES = (
    QUARTERLY_SOURCE_NATIVE,
    QUARTERLY_SOURCE_DERIVED,
    QUARTERLY_SOURCE_UNAVAILABLE,
)

# Derivation methods. Each names a concrete, reproducible rule - never
# "divide by four", which is only correct for a flow with no seasonality.
METHOD_NATIVE = "native_published_quarterly"
METHOD_DENTON = "denton_proportional_first_difference"
METHOD_IDENTITY = "governed_identity_composition"
METHOD_END_OF_PERIOD = "linear_interpolation_between_annual_anchors"
METHOD_FIXED = "fixed_rule_carried_unchanged"

# Reconciliation rules a DERIVED year must satisfy exactly.
RECONCILE_SUM = "sum_of_quarters_equals_annual"
RECONCILE_MEAN = "mean_of_quarters_equals_annual"
RECONCILE_END_OF_PERIOD = "fiscal_year_end_quarter_equals_annual"
RECONCILE_NATIVE_ONLY = "not_applicable_native_rows_are_published_not_derived"

POSITIVITY_REQUIRED = "non_negative_required"
POSITIVITY_UNCONSTRAINED = "sign_unconstrained"

# Annual closure is a hard constraint, solved by subtraction against
# ``math.fsum`` so the residual is the correctly-rounded double and nothing
# else. Measured over the whole built pack the worst residual is ~1.4 ulp
# (3.1e-16 relative); these bounds sit three orders above that, so a real
# reconciliation break cannot hide inside the tolerance.
RECONCILIATION_ABS_TOLERANCE = 1e-6
RECONCILIATION_REL_TOLERANCE = 1e-12

COVERAGE_ROW_TYPE_NATIVE = "native_quarterly"
COVERAGE_ROW_TYPE_DERIVED = "derived_quarterly_from_governed_annual"
COVERAGE_ROW_TYPE_OFFICIAL_ANNUAL = "official_annual_materialised_from_vintage_source"

EMPIRICAL = "empirical"
DERIVED = "derived"

# Provenance wording for an official comparator whose quarters were derived.
# It must never read as published official quarterly data.
OFFICIAL_DERIVED_PROVENANCE = (
    "derived quarterly presentation from official annual source"
)
CURRENT_DERIVED_PROVENANCE = (
    "derived quarterly presentation from governed current-model annual value"
)
NATIVE_PROVENANCE = "published quarterly value"

# The three native quarterly activity paths. Seasonal shape for everything
# else is borrowed from one of them; a series with no defensible indicator
# gets a flat one, which is the neutral allocation and is declared as such.
NEUTRAL_SEASONAL_BASIS = "neutral_flat_indicator"


@dataclass(frozen=True)
class QuarterlyDisplayContract:
    """How one selectable series may be shown at quarterly grain.

    ``annual_semantics`` describes the published annual number.
    ``annual_reconciliation_rule`` is the constraint the DERIVED quarters must
    satisfy; the two can differ, and where they do the reason is recorded in
    ``limitation`` rather than smoothed over.
    """

    series_id: str
    display_name: str
    unit: str
    quarterly_unit: str
    metric_type: str
    annual_semantics: str
    quarterly_source: str
    derivation_method: str
    seasonal_basis: str
    source_window: str
    annual_reconciliation_rule: str
    positivity_rule: str
    provenance_label: str
    limitation: str

    def __post_init__(self) -> None:
        if self.annual_semantics not in ANNUAL_SEMANTICS:
            raise SeriesCoverageError(
                f"{self.series_id}: unknown annual_semantics {self.annual_semantics!r}"
            )
        if self.quarterly_source not in QUARTERLY_SOURCES:
            raise SeriesCoverageError(
                f"{self.series_id}: unknown quarterly_source {self.quarterly_source!r}"
            )

    @property
    def average_preserving(self) -> bool:
        """Does the annual benchmark constrain the MEAN rather than the sum?"""
        return self.annual_reconciliation_rule == RECONCILE_MEAN


def _flow(
    series_id: str,
    display_name: str,
    unit: str,
    metric_type: str,
    seasonal_basis: str,
    *,
    quarterly_unit: str = "",
    source_window: str = "annual chart rows FY2001-FY2050 (Actual, current model, official comparators)",
    limitation: str = "",
    derivation_method: str = METHOD_DENTON,
) -> QuarterlyDisplayContract:
    """An annual flow whose quarters must sum back to the June-year value."""
    return QuarterlyDisplayContract(
        series_id=series_id,
        display_name=display_name,
        unit=unit,
        quarterly_unit=quarterly_unit or unit,
        metric_type=metric_type,
        annual_semantics=ANNUAL_SEMANTICS_SUM,
        quarterly_source=QUARTERLY_SOURCE_DERIVED,
        derivation_method=derivation_method,
        seasonal_basis=seasonal_basis,
        source_window=source_window,
        annual_reconciliation_rule=RECONCILE_SUM,
        positivity_rule=POSITIVITY_REQUIRED,
        provenance_label=OFFICIAL_DERIVED_PROVENANCE,
        limitation=limitation,
    )


def _native(
    series_id: str,
    display_name: str,
    unit: str,
    quarterly_unit: str,
    metric_type: str,
    annual_semantics: str,
    *,
    source_window: str,
    limitation: str,
) -> QuarterlyDisplayContract:
    """A series with published quarterly rows for at least one trace.

    Native rows are never rewritten. Traces that lack them still fall to the
    derived builder, which is why the reconciliation rule below governs the
    derived case and the native caveat is stated in ``limitation``.
    """
    return QuarterlyDisplayContract(
        series_id=series_id,
        display_name=display_name,
        unit=unit,
        quarterly_unit=quarterly_unit,
        metric_type=metric_type,
        annual_semantics=annual_semantics,
        quarterly_source=QUARTERLY_SOURCE_NATIVE,
        derivation_method=METHOD_NATIVE,
        seasonal_basis=series_id,
        source_window=source_window,
        annual_reconciliation_rule=RECONCILE_SUM,
        positivity_rule=POSITIVITY_REQUIRED,
        provenance_label=NATIVE_PROVENANCE,
        limitation=limitation,
    )


_PED_BASIS = "ped_vkt_per_capita"
_LIGHT_BASIS = "light_ruc_net_km"
_HEAVY_BASIS = "heavy_ruc_net_km"

_NATIVE_WINDOW = "native quarterly rows to 2030Q4; annual rows beyond"
_OFFICIAL_ONLY_LIMITATION = (
    "No native quarterly path exists for any trace; every quarter shown is derived "
    "from the June-year benchmark and is indicative display only."
)

QUARTERLY_DISPLAY_CONTRACT: tuple[QuarterlyDisplayContract, ...] = (
    # -------------------------------------------------------------- activity
    _flow(
        "light_petrol_vkt",
        "Light petrol VKT",
        "million km",
        "activity",
        _PED_BASIS,
        source_window=(
            "official annual FY2003-FY2050 (BEFU26, MBU26); current-model annual from "
            "the selected PED bridge"
        ),
        limitation=(
            "Annual-only in every source. Before this contract the series had no "
            "official annual rows at all, so neither an annual nor a quarterly "
            "official line could draw. " + _OFFICIAL_ONLY_LIMITATION
        ),
    ),
    _native(
        "ped_vkt_per_capita",
        "PED VKT per capita",
        "km/person",
        "VKT per capita",
        "activity",
        ANNUAL_SEMANTICS_RATE,
        source_window="native quarterly actuals from 2002Q1 to 2025Q4; current-model quarters to 2030Q4",
        limitation=(
            "The published annual km/person is annual VKT over mean-year population, "
            "not the sum of four quarterly per-capita figures, so the NATIVE quarters "
            "sum to within 0.07-0.29% of the annual anchor rather than exactly. "
            "Derived quarters, where a trace has none, partition the annual anchor "
            "exactly and are labelled as derived."
        ),
    ),
    _flow(
        "ped_volume",
        "PED volume",
        "million litres",
        "activity",
        _PED_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _native(
        "light_ruc_net_km",
        "Light RUC net km",
        "million km",
        "net km",
        "activity",
        ANNUAL_SEMANTICS_SUM,
        source_window="native quarterly actuals from 2009Q3 to 2025Q4; current-model quarters to 2030Q4",
        limitation=(
            "Quarterly is published in net km and annual in million km; the annual "
            "value is the quarterly sum divided by 1e6 exactly."
        ),
    ),
    _native(
        "heavy_ruc_net_km",
        "Heavy RUC net km",
        "million km",
        "net km",
        "activity",
        ANNUAL_SEMANTICS_SUM,
        source_window="native quarterly actuals from 2009Q3 to 2025Q4; current-model quarters to 2030Q4",
        limitation=(
            "Quarterly is published in net km and annual in million km; the annual "
            "value is the quarterly sum divided by 1e6 exactly."
        ),
    ),
    _flow(
        "light_bev_ruc_net_km",
        "Light BEV RUC net km",
        "million km",
        "activity",
        _LIGHT_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "phev_ruc_net_km",
        "PHEV RUC net km",
        "million km",
        "activity",
        _LIGHT_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    # --------------------------------------------------------------- revenue
    _flow(
        "gross_ped_revenue",
        "PED revenue",
        "$m nominal ex GST",
        "revenue",
        _PED_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "light_ruc_net_revenue",
        "Light RUC revenue",
        "$m nominal ex GST",
        "revenue",
        _LIGHT_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "light_bev_ruc_net_revenue",
        "Light BEV RUC net revenue",
        "$m nominal ex GST",
        "revenue",
        _LIGHT_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "phev_ruc_net_revenue",
        "PHEV RUC net revenue",
        "$m nominal ex GST",
        "revenue",
        _LIGHT_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "heavy_ruc_net_revenue",
        "Heavy RUC revenue",
        "$m nominal ex GST",
        "revenue",
        _HEAVY_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "gross_fed_revenue",
        "Gross FED revenue",
        "$m nominal ex GST",
        "revenue",
        _PED_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "net_fed_revenue",
        "Net FED revenue",
        "$m nominal ex GST",
        "revenue",
        _PED_BASIS,
        limitation=_OFFICIAL_ONLY_LIMITATION,
    ),
    _flow(
        "total_ruc_net_revenue",
        "Total RUC all classes",
        "$m nominal ex GST",
        "revenue",
        NEUTRAL_SEASONAL_BASIS,
        limitation=(
            "A net-of-admin-and-refunds rollup across three RUC classes with no single "
            "governing activity path, so the split uses the neutral flat indicator "
            "(minimum quarter-to-quarter movement subject to exact annual closure). "
            + _OFFICIAL_ONLY_LIMITATION
        ),
    ),
    _flow(
        "net_mvr_revenue",
        "Net MVR revenue",
        "$m nominal ex GST",
        "revenue",
        NEUTRAL_SEASONAL_BASIS,
        limitation=(
            "Registration and licensing revenue has no governed quarterly activity "
            "indicator in the pack, so the neutral flat indicator is used. "
            + _OFFICIAL_ONLY_LIMITATION
        ),
    ),
    _flow(
        "total_fed_ruc_net_revenue",
        "Total RUC+PED revenue",
        "$m nominal ex GST",
        "revenue",
        "net_fed_revenue + total_ruc_net_revenue",
        derivation_method=METHOD_IDENTITY,
        limitation=(
            "A strict accounting identity. Splitting it independently is annual-consistent "
            "but leaves material quarter-level residuals against its own components, so "
            "its quarters are composed from the two governed component paths instead. "
            + _OFFICIAL_ONLY_LIMITATION
        ),
    ),
    _flow(
        "total_nltf_net_revenue",
        "Total NLTF revenue",
        "$m nominal ex GST",
        "revenue",
        NEUTRAL_SEASONAL_BASIS,
        limitation=(
            "The whole-fund total spans FED, RUC, MVR and TUC with no single governing "
            "activity path, so the neutral flat indicator is used. "
            + _OFFICIAL_ONLY_LIMITATION
        ),
    ),
)

_CONTRACT_BY_SERIES: dict[str, QuarterlyDisplayContract] = {
    contract.series_id: contract for contract in QUARTERLY_DISPLAY_CONTRACT
}
if len(_CONTRACT_BY_SERIES) != len(QUARTERLY_DISPLAY_CONTRACT):
    raise SeriesCoverageError("QUARTERLY_DISPLAY_CONTRACT contains a duplicate series_id.")

# The composition identity, kept beside the contract that names it so the two
# cannot drift.
_IDENTITY_COMPONENTS: dict[str, tuple[str, ...]] = {
    "total_fed_ruc_net_revenue": ("net_fed_revenue", "total_ruc_net_revenue"),
}

# --------------------------------------------------------------- identity API

# Display labels the selector may present, mapped back to the canonical id.
# ``Net RUC revenue (all classes)`` is the selector's format_func output for
# ``Total RUC all classes``; both must resolve.
_EXTRA_LABEL_ALIASES: dict[str, str] = {
    "Net RUC revenue (all classes)": "total_ruc_net_revenue",
    "Light petrol VKT (m km)": "light_petrol_vkt",
    "Light petrol VKT per capita": "ped_vkt_per_capita",
    "light_petrol_vkt_per_capita": "ped_vkt_per_capita",
    "PED VKT per capita": "ped_vkt_per_capita",
}


@lru_cache(maxsize=1)
def _label_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for contract in QUARTERLY_DISPLAY_CONTRACT:
        lookup[contract.series_id.casefold()] = contract.series_id
        lookup[contract.display_name.casefold()] = contract.series_id
    for label, series_id in _EXTRA_LABEL_ALIASES.items():
        lookup[label.casefold()] = series_id
    return lookup


def canonical_series_id(value: Any) -> str:
    """Resolve a series id, display label or governed alias to its canonical id.

    Raises rather than returning an empty string: a silent miss here is what
    let a selectable label point at nothing in the first place.
    """
    text = str(value or "").strip()
    if not text:
        raise SeriesCoverageError("canonical_series_id requires a non-empty series id or label.")
    resolved = _label_lookup().get(text.casefold())
    if resolved is None:
        raise SeriesCoverageError(
            f"{text!r} is not a governed Revenue Outlook series id or display label."
        )
    return resolved


def series_display_label(series_id: Any) -> str:
    """The dashboard label for a canonical series id."""
    return contract_for_series(series_id).display_name


def selectable_series_ids() -> tuple[str, ...]:
    """Every series the Revenue Outlook selector may offer, in contract order."""
    return tuple(contract.series_id for contract in QUARTERLY_DISPLAY_CONTRACT)


def contract_for_series(series_id: Any) -> QuarterlyDisplayContract:
    """The quarterly display contract for one series."""
    resolved = canonical_series_id(series_id)
    return _CONTRACT_BY_SERIES[resolved]


def quarterly_contract_frame() -> pd.DataFrame:
    """The full contract as a frame, one row per selectable series."""
    frame = pd.DataFrame([asdict(contract) for contract in QUARTERLY_DISPLAY_CONTRACT])
    frame.insert(0, "contract_version", CONTRACT_VERSION)
    frame["display_horizon_last_fy"] = DISPLAY_HORIZON_LAST_FY
    frame["display_horizon_last_quarter"] = DISPLAY_HORIZON_LAST_QUARTER
    frame["in_display_series_order"] = frame["series_id"].isin(set(DISPLAY_SERIES_ORDER))
    return frame


# ------------------------------------------------------------ horizon governance


def _quarter_parts(period: Any) -> tuple[int, int] | None:
    text = str(period or "").strip().upper()
    if len(text) != 6 or text[4] != "Q":
        return None
    try:
        return int(text[:4]), int(text[5])
    except ValueError:
        return None


def june_year_for_quarter(period: Any) -> int | None:
    """The NZ June year containing a calendar quarter: 2030Q3 sits in FY2031."""
    parts = _quarter_parts(period)
    if parts is None:
        return None
    year, quarter = parts
    if quarter not in (1, 2, 3, 4):
        return None
    return year + 1 if quarter in (3, 4) else year


def display_horizon_filter(
    rows: pd.DataFrame,
    *,
    last_fy: int = DISPLAY_HORIZON_LAST_FY,
) -> pd.DataFrame:
    """Drop every display row beyond the decision-facing horizon.

    Applies to both grains from the same rule: a June-year row is kept when its
    fiscal year is within the horizon, and a quarterly row when the fiscal year
    CONTAINING it is. That second clause is the one that matters - 2050Q3 is a
    FY2051 quarter and must not survive an FY2050 cut on its calendar year.
    """
    if rows is None or rows.empty:
        return pd.DataFrame() if rows is None else rows.copy()
    out = rows.copy()
    period_fy = out.get("period", pd.Series("", index=out.index)).map(june_year_for_quarter)
    june = pd.to_numeric(out.get("june_year"), errors="coerce")
    # A quarterly period is authoritative about its own fiscal year; fall back
    # to the declared june_year only where the period is not a quarter.
    effective = pd.to_numeric(period_fy, errors="coerce").fillna(june)
    return out[effective.notna() & effective.le(float(last_fy))].copy()


def governed_policy_step_quarters(
    repo_root: Path | str | None = None,
    *,
    policy_state: str | None = None,
) -> dict[int, tuple[str, ...]]:
    """The calendar quarters a governed FED policy state actually moves.

    Read from ``rate_paths``, never restated here - a second copy of a policy
    calendar is a second thing to get wrong. A derived quarterly display must
    not shift these: the step keeps its own calendar quarter, and lands in the
    fiscal year the schedule names.
    """
    from .rate_paths import FED_POLICY_STATE_DELAYED_6M, fed_policy_affected_periods

    root = Path(repo_root) if repo_root is not None else _repo_root()
    state = str(policy_state or FED_POLICY_STATE_DELAYED_6M)
    return fed_policy_affected_periods(root, state)


# ---------------------------------------------------- official row materialisation


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _series_meta_for_contract() -> dict[str, dict[str, Any]]:
    """Label/metric metadata in the shape ``_runtime_chart_record`` expects.

    Built from this module's contract rather than from
    ``_runtime_series_metadata``: that helper only knows series inside
    ``DISPLAY_SERIES_ORDER``, so it would title-case ``light_petrol_vkt`` into
    ``Light Petrol Vkt`` and the selector would stop matching the label.
    """
    return {
        contract.series_id: {
            "display_name": contract.display_name,
            "metric_type": contract.metric_type,
            "unit": contract.unit,
            "availability_status": "",
            "valid_controls": "",
        }
        for contract in QUARTERLY_DISPLAY_CONTRACT
    }


def _clean_text(value: Any) -> str:
    """Text that never renders a missing value as the string ``nan``."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _official_source_reference(vintage_id: str, repo_root: Path) -> dict[str, str]:
    """Where a restored value came from, precisely enough to go and check it.

    The official_annual stem differs per pack format (``official_annual`` for
    the generic vintage layout, ``mbu26_official_annual`` for the legacy one),
    so it is read from the registry rather than assumed - a lineage string
    pointing at a file that does not exist is worse than none.
    """
    entry = official_vintage_entry(vintage_id, repo_root=repo_root)
    pack_path = str(entry.get("source_pack_path") or "")
    stem = str((entry.get("file_stems") or {}).get("official_annual") or "official_annual")
    manifest = repo_root / pack_path / "manifest.json"
    return {
        "source_pack_path": pack_path,
        "official_annual_relpath": f"{pack_path}/{stem}.parquet",
        "manifest_sha256": (
            hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else ""
        ),
        "workbook_sha256": str(entry.get("workbook_sha256") or ""),
        "release_round": str(entry.get("release_round") or vintage_id),
        "source_horizon_fy": str(entry.get("source_horizon_fy") or ""),
    }


def official_rows_for_series(
    series_id: Any,
    *,
    vintage_ids: Sequence[str] | None = None,
    repo_root: Path | str | None = None,
    include_actual: bool = True,
    apply_display_horizon: bool = True,
) -> pd.DataFrame:
    """June-year chart rows for one series, straight from the vintage packs.

    The values are the published ones, carried through unchanged in their own
    source unit. Nothing is interpolated, rescaled, copied between vintages or
    extended past a vintage's own source horizon; the only filtering applied is
    the FY2050 display cut.

    ``include_actual`` also emits the ACTUAL-period block from the default
    bridge vintage as the ``Actual`` trace, which is how every other series in
    ``DISPLAY_SERIES_ORDER`` gets its history.
    """
    resolved = canonical_series_id(series_id)
    contract = _CONTRACT_BY_SERIES[resolved]
    root = Path(repo_root) if repo_root is not None else _repo_root()
    choices = [vid for vid, _display in official_vintage_choices(root)]
    wanted = [str(vid) for vid in (vintage_ids if vintage_ids is not None else choices)]
    unknown = [vid for vid in wanted if vid not in choices]
    if unknown:
        raise SeriesCoverageError(f"Unregistered official vintage(s): {', '.join(unknown)}")

    series_meta = _series_meta_for_contract()
    columns = _runtime_chart_columns()
    records: list[dict[str, Any]] = []
    actual_emitted = False

    for vintage_id in wanted:
        pack = load_official_vintage(vintage_id, repo_root=root)
        reference = _official_source_reference(vintage_id, root)
        annual = pack.official_annual
        data = annual[annual.get("series_id", pd.Series(dtype=str)).astype(str).eq(resolved)].copy()
        if data.empty:
            continue
        data["fy_numeric"] = pd.to_numeric(data.get("FY"), errors="coerce")
        data["value_numeric"] = pd.to_numeric(data.get("value"), errors="coerce")
        data = data[data["fy_numeric"].notna() & data["value_numeric"].notna()]
        status = data.get("period_status", pd.Series("", index=data.index)).astype(str).str.upper()

        # The bridge vintage owns the ACTUAL block; emitting it once from each
        # vintage would duplicate an identical history.
        is_bridge = bool(official_vintage_entry(vintage_id, repo_root=root).get("is_default_bridge_vintage"))
        if include_actual and is_bridge and not actual_emitted:
            actual = data[status.eq("ACTUAL") & data["fy_numeric"].le(REVENUE_LAST_COMPLETE_ACTUAL_FY)]
            for row in actual.itertuples(index=False):
                records.append(
                    _official_record(
                        row,
                        contract=contract,
                        series_meta=series_meta,
                        reference=reference,
                        vintage_id=vintage_id,
                        is_actual=True,
                    )
                )
            actual_emitted = bool(len(actual))

        forecast = data[~status.eq("ACTUAL") & data["fy_numeric"].ge(REVENUE_LAST_COMPLETE_ACTUAL_FY + 1)]
        for row in forecast.itertuples(index=False):
            records.append(
                _official_record(
                    row,
                    contract=contract,
                    series_meta=series_meta,
                    reference=reference,
                    vintage_id=vintage_id,
                    is_actual=False,
                )
            )

    frame = pd.DataFrame.from_records(records, columns=columns)
    if frame.empty:
        return frame
    frame = _add_canonical_join_keys(frame)
    frame["coverage_row_type"] = COVERAGE_ROW_TYPE_OFFICIAL_ANNUAL
    frame["empirical_or_derived"] = EMPIRICAL
    frame["contract_version"] = CONTRACT_VERSION
    if apply_display_horizon:
        frame = display_horizon_filter(frame)
    return frame.sort_values(["trace_name", "june_year"], kind="stable").reset_index(drop=True)


def _official_record(
    row: Any,
    *,
    contract: QuarterlyDisplayContract,
    series_meta: dict[str, dict[str, Any]],
    reference: Mapping[str, str],
    vintage_id: str,
    is_actual: bool,
) -> dict[str, Any]:
    fy = int(getattr(row, "fy_numeric"))
    value = float(getattr(row, "value_numeric"))
    unit = _clean_text(getattr(row, "unit", "")) or contract.unit
    source_cell = _clean_text(getattr(row, "source_cell", ""))
    release = reference["release_round"]
    # Lineage carries the exact file, the row it came from and the hash of the
    # pack manifest that governs it, so a restored value can be checked back to
    # source without knowing how this module works.
    lineage = (
        f"{reference['official_annual_relpath']}"
        f"#{contract.series_id}:FY{fy}"
        f"@{reference['manifest_sha256'][:16]}"
    )
    source_file = _clean_text(getattr(row, "source_file", "")) or reference["official_annual_relpath"]
    formula = _clean_text(getattr(row, "formula", ""))
    row_role = _clean_text(getattr(row, "row_role", ""))
    if is_actual:
        return _runtime_chart_record(
            series_id=contract.series_id,
            series_meta=series_meta,
            metric_type=contract.metric_type,
            time_grain="june_year",
            row_type="historical_actual",
            trace_name="Actual",
            trace_type="Actual",
            trace_role="source_actual",
            trace_source="actual_benchmark",
            scenario_name="actual",
            scenario_role="actual",
            period=f"FY{fy}",
            june_year=fy,
            value=value,
            value_unit=unit,
            source=lineage,
            source_file=source_file,
            source_cell=source_cell,
            source_status=_clean_text(getattr(row, "period_status", "")) or "ACTUAL",
            value_status=_clean_text(getattr(row, "value_status", "")) or "actual",
            data_scope="official_vintage_complete_actual_line",
            model_id="",
            anchor_flag=fy == REVENUE_LAST_COMPLETE_ACTUAL_FY,
            nowcast_flag=False,
            formula=formula,
            source_basis=f"{release} annual source spine",
            row_role=row_role,
            official_value=value,
            residual_vs_official=0.0,
        )
    return _runtime_chart_record(
        series_id=contract.series_id,
        series_meta=series_meta,
        metric_type=contract.metric_type,
        time_grain="june_year",
        row_type="official_comparator",
        trace_name=official_comparator_trace_name(release),
        trace_type=official_comparator_trace_name(release),
        trace_role="official_external_comparator",
        trace_source=f"{vintage_id.lower()}_official",
        scenario_name=official_comparator_scenario_name(vintage_id),
        scenario_role="official_comparator",
        period=f"FY{fy}",
        june_year=fy,
        value=value,
        value_unit=unit,
        source=lineage,
        source_file=source_file,
        source_cell=source_cell,
        source_status=_clean_text(getattr(row, "period_status", "")),
        value_status=_clean_text(getattr(row, "value_status", "")) or "official_forecast",
        data_scope="official_forecast",
        model_id="",
        fed_path=release,
        revenue_basis=unit,
        bridge_status="available",
        bridge_method=f"{release} official annual row",
        release_round=release,
        anchor_flag=False,
        nowcast_flag=False,
        formula=formula,
        source_basis=f"{release} official annual",
        row_role=row_role,
        official_value=value,
        residual_vs_official=0.0,
    )


def missing_official_rows(
    chart_rows: pd.DataFrame,
    *,
    series_ids: Sequence[str] | None = None,
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Official rows a chart-row frame is missing, and only those.

    The integration path is ``pd.concat([chart_rows, missing_official_rows(chart_rows)])``:
    every row already present is left untouched, so no published value can move.
    """
    wanted = [canonical_series_id(sid) for sid in (series_ids or selectable_series_ids())]
    if chart_rows is None or chart_rows.empty:
        present: set[tuple[str, str, str]] = set()
    else:
        annual = chart_rows[chart_rows.get("time_grain", pd.Series(dtype=str)).astype(str).eq("june_year")]
        present = {
            (str(row.series_id), str(row.trace_name), str(row.period))
            for row in annual.itertuples(index=False)
        }
    blocks: list[pd.DataFrame] = []
    for series_id in wanted:
        rows = official_rows_for_series(series_id, repo_root=repo_root)
        if rows.empty:
            continue
        keys = list(
            zip(
                rows["series_id"].astype(str),
                rows["trace_name"].astype(str),
                rows["period"].astype(str),
            )
        )
        keep = [key not in present for key in keys]
        block = rows[pd.Series(keep, index=rows.index)]
        if not block.empty:
            blocks.append(block)
    if not blocks:
        return pd.DataFrame(columns=_runtime_chart_columns())
    return pd.concat(blocks, ignore_index=True, sort=False)


# ------------------------------------------------------------ quarterly builders


def _denton_quarterly_split(
    annual_values: np.ndarray,
    indicator: np.ndarray,
    *,
    average: bool,
) -> np.ndarray:
    """Benchmark annual values onto quarters, following an indicator's shape.

    Denton proportional first difference: minimise the movement of the
    quarterly/indicator ratio subject to each year reproducing its benchmark.
    A flat indicator reduces this to the Boot-Feibes-Lisman smooth split, which
    is the neutral allocation this contract names for series with no governed
    seasonal evidence.
    """
    n = int(len(annual_values))
    m = 4 * n
    ind = np.asarray(indicator, dtype=float)
    if ind.shape[0] != m or not np.all(np.isfinite(ind)) or np.any(ind <= 0):
        ind = np.ones(m, dtype=float)
    difference = np.diff(np.eye(m), axis=0)
    weights = ind / 4.0 if average else ind
    constraint = np.zeros((n, m))
    for year in range(n):
        constraint[year, 4 * year : 4 * year + 4] = weights[4 * year : 4 * year + 4]
    kkt = np.zeros((m + n, m + n))
    kkt[:m, :m] = 2.0 * difference.T @ difference
    kkt[:m, m:] = constraint.T
    kkt[m:, :m] = constraint
    rhs = np.concatenate([np.zeros(m), np.asarray(annual_values, dtype=float)])
    solution = np.linalg.lstsq(kkt, rhs, rcond=None)[0]
    return ind * solution[:m]


def interpolate_end_of_period_quarters(
    annual_values: Sequence[float],
    *,
    positive: bool = True,
) -> np.ndarray:
    """Quarters for a level/stock series measured at each June year end.

    A level is not a flow: its quarters are NOT summed. Each fiscal year's
    final quarter (calendar Q2) carries the annual anchor exactly, and the
    three quarters before it are linearly interpolated from the previous
    anchor. The first year has no earlier anchor, so it is held flat rather
    than back-cast from a slope that does not exist.
    """
    values = np.asarray(list(annual_values), dtype=float)
    if values.size == 0:
        return np.zeros(0, dtype=float)
    out = np.empty(4 * values.size, dtype=float)
    for index, anchor in enumerate(values):
        previous = values[index - 1] if index else anchor
        step = (anchor - previous) / 4.0
        for quarter in range(4):
            out[4 * index + quarter] = previous + step * (quarter + 1)
    if positive:
        out = np.clip(out, 0.0, None)
    # The anchor itself is never approximated, including after any clip.
    out[3::4] = values
    return out


def _quarterly_indicator_lookup(
    chart_rows: pd.DataFrame | None,
    indicator_series_id: str,
    trace_name: Any,
) -> dict[str, float]:
    """Native quarterly evidence usable as a seasonal indicator.

    Actual quarters first, then the trace's own quarters where it has them, so
    a current-model trace follows its own modelled seasonality rather than the
    historical average.
    """
    if not indicator_series_id or indicator_series_id == NEUTRAL_SEASONAL_BASIS:
        return {}
    if chart_rows is None or chart_rows.empty:
        return {}
    if {"series_id", "time_grain"}.difference(chart_rows.columns):
        return {}
    rows = chart_rows[
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["series_id"].astype(str).eq(indicator_series_id)
    ]
    if rows.empty:
        return {}
    frame = pd.DataFrame(
        {
            "period": rows["period"].astype(str),
            "trace": rows.get("trace_name", pd.Series("", index=rows.index)).astype(str),
            "value": pd.to_numeric(rows["value"], errors="coerce"),
        }
    ).dropna(subset=["value"])
    lookup = {
        str(row.period): float(row.value)
        for row in frame[frame["trace"].eq("Actual")].itertuples(index=False)
    }
    for row in frame[frame["trace"].eq(str(trace_name or ""))].itertuples(index=False):
        lookup[str(row.period)] = float(row.value)
    return lookup


def _actual_quarter_lookup(
    chart_rows: pd.DataFrame | None,
    series_id: str,
    target_unit: Any,
) -> dict[str, float]:
    """Published Actual quarters for a series, expressed in an annual row's unit."""
    if chart_rows is None or chart_rows.empty:
        return {}
    required = {"series_id", "time_grain", "row_type", "period", "value"}
    if required.difference(chart_rows.columns):
        return {}
    actual = chart_rows[
        chart_rows["series_id"].astype(str).eq(str(series_id))
        & chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("historical_actual")
    ].copy()
    if actual.empty:
        return {}
    actual["_numeric"] = pd.to_numeric(actual["value"], errors="coerce")
    actual = actual.dropna(subset=["_numeric"]).drop_duplicates("period", keep="last")
    target_scale = display_scale_for(target_unit) if str(target_unit or "").strip() else 1.0
    units = actual.get("value_unit", pd.Series("", index=actual.index)).fillna("").astype(str)
    lookup: dict[str, float] = {}
    for index, row in actual.iterrows():
        period = str(row["period"])
        if _quarter_parts(period) is None:
            continue
        unit_text = units.at[index]
        scale = display_scale_for(unit_text) if unit_text.strip() else target_scale
        lookup[period] = float(row["_numeric"]) * scale / target_scale
    return lookup


def _native_quarter_lookup(
    chart_rows: pd.DataFrame | None,
    series_id: str,
    trace_name: Any,
    target_unit: Any,
) -> dict[str, float]:
    """Quarters this (series, trace) already publishes, in the annual row's unit.

    These are fixed points, not candidates for derivation. A June year they
    cover completely produces nothing; a June year they cover partly - the
    FY2031 case, where the governed quarterly horizon stops at 2030Q4 while the
    annual path continues to FY2050 - keeps its published quarters and derives
    only the rest, benchmarked to the annual less the published part.
    """
    if chart_rows is None or chart_rows.empty:
        return {}
    if {"series_id", "time_grain", "trace_name", "period", "value"}.difference(chart_rows.columns):
        return {}
    rows = chart_rows[
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["series_id"].astype(str).eq(str(series_id))
        & chart_rows["trace_name"].astype(str).eq(str(trace_name or ""))
    ].copy()
    if rows.empty:
        return {}
    rows["_numeric"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.dropna(subset=["_numeric"]).drop_duplicates("period", keep="last")
    target_scale = display_scale_for(target_unit) if str(target_unit or "").strip() else 1.0
    units = rows.get("value_unit", pd.Series("", index=rows.index)).fillna("").astype(str)
    lookup: dict[str, float] = {}
    for index, row in rows.iterrows():
        period = str(row["period"])
        if _quarter_parts(period) is None:
            continue
        unit_text = units.at[index]
        scale = display_scale_for(unit_text) if unit_text.strip() else target_scale
        lookup[period] = float(row["_numeric"]) * scale / target_scale
    return lookup


_QUARTERLY_PROVENANCE_COLUMNS = (
    "coverage_row_type",
    "annual_source_period",
    "annual_source_value",
    "derivation_method",
    "seasonal_basis",
    "annual_reconciliation_residual",
    "empirical_or_derived",
    "fixed_actual_quarters",
    "fixed_actual_total",
    "contract_version",
)


def derive_quarterly_rows(
    annual_rows: pd.DataFrame,
    *,
    chart_rows: pd.DataFrame | None = None,
    apply_display_horizon: bool = True,
) -> pd.DataFrame:
    """The governed quarterly builder: annual display rows in, quarters out.

    One rule per series, taken from ``QUARTERLY_DISPLAY_CONTRACT`` - never a
    blanket divide-by-four. Quarters that coincide with a published Actual
    observation are held at the actual value and withheld from the output (the
    Actual trace already draws them); the remaining quarters absorb the whole
    annual benchmark, so the year still closes exactly.

    Pure: it reads ``annual_rows`` and ``chart_rows`` and touches neither.
    """
    empty = pd.DataFrame(columns=list(_runtime_chart_columns()) + list(_QUARTERLY_PROVENANCE_COLUMNS))
    if annual_rows is None or annual_rows.empty:
        return empty
    data = annual_rows.copy()
    data["_value"] = pd.to_numeric(data.get("value"), errors="coerce")
    data["_fy"] = pd.to_numeric(data.get("june_year"), errors="coerce")
    data = data[data["_value"].notna() & data["_fy"].notna()]
    if data.empty:
        return empty

    # A forecast trace may carry a nowcast anchor at the last complete actual
    # year. Splitting it would plant forecast quarters inside the actuals era.
    is_actual_row = data.get("row_type", pd.Series("", index=data.index)).astype(str).eq(
        "historical_actual"
    )
    data = data[is_actual_row | data["_fy"].ge(REVENUE_FIRST_FORECAST_FY)]
    if data.empty:
        return empty

    group_columns = [c for c in ("series_id", "trace_name", "scenario_name", "fed_path") if c in data.columns]
    output: list[dict[str, Any]] = []
    for _key, group in data.groupby(group_columns, dropna=False):
        series_id = str(group["series_id"].iloc[0])
        if series_id not in _CONTRACT_BY_SERIES:
            continue
        output.extend(
            _derive_one_trace(
                group.sort_values("_fy").drop_duplicates("_fy", keep="last"),
                contract=_CONTRACT_BY_SERIES[series_id],
                chart_rows=chart_rows,
                annual_rows=data,
            )
        )
    if not output:
        return empty
    frame = pd.DataFrame(output)
    frame = frame.reindex(columns=[c for c in empty.columns if c in frame.columns] + [
        c for c in frame.columns if c not in empty.columns
    ])
    if apply_display_horizon:
        frame = display_horizon_filter(frame)
    return frame.sort_values(["series_id", "trace_name", "period"], kind="stable").reset_index(drop=True)


def _derive_one_trace(
    group: pd.DataFrame,
    *,
    contract: QuarterlyDisplayContract,
    chart_rows: pd.DataFrame | None,
    annual_rows: pd.DataFrame,
) -> list[dict[str, Any]]:
    template = group.iloc[0].to_dict()
    trace_name = template.get("trace_name")
    is_actual_trace = str(template.get("row_type") or "") == "historical_actual"

    # A series with a native quarterly path keeps its published history as the
    # whole of its history. Back-casting derived quarters over June years the
    # native path simply predates would put invented quarters inside the
    # actuals era, which is a different claim from extending a forecast tail.
    if contract.quarterly_source == QUARTERLY_SOURCE_NATIVE and is_actual_trace:
        return []

    unit = template.get("value_unit") or contract.unit
    # Two sources of fixed quarters: this trace's own published quarters, and
    # the Actual observations any forecast trace must hand over from. Both are
    # held at their published value and withheld from the output.
    fixed_lookup = dict(_native_quarter_lookup(chart_rows, contract.series_id, trace_name, unit))
    if not is_actual_trace:
        for period, value in _actual_quarter_lookup(chart_rows, contract.series_id, unit).items():
            fixed_lookup.setdefault(period, value)

    # A June year every one of whose quarters is already published needs no
    # derivation at all, and including it would only perturb the Denton solve.
    covered = {
        fy
        for fy in group["_fy"].astype(int)
        if all(period in fixed_lookup for period in june_year_quarters(fy))
    }
    group = group[~group["_fy"].astype(int).isin(covered)]
    if group.empty:
        return []
    years = group["_fy"].astype(int).tolist()
    annual_values = group["_value"].to_numpy(dtype=float)

    if contract.derivation_method == METHOD_IDENTITY:
        composed = _compose_identity_quarters(
            group,
            contract=contract,
            chart_rows=chart_rows,
            annual_rows=annual_rows,
        )
        if composed is not None:
            return composed
        # Fall through to the indicator split rather than emitting nothing: a
        # missing component is a coverage gap, not a reason to drop the series.

    lookup = _quarterly_indicator_lookup(chart_rows, contract.seasonal_basis, trace_name)
    quarters = [q for fy in years for q in june_year_quarters(fy)]
    seasonal: dict[str, list[float]] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for period, value in lookup.items():
        seasonal[period[-2:]].append(value)
    seasonal_mean = {key: (sum(values) / len(values) if values else 1.0) for key, values in seasonal.items()}
    indicator = np.array(
        [lookup.get(period, seasonal_mean.get(period[-2:], 1.0)) for period in quarters],
        dtype=float,
    )
    values = _denton_quarterly_split(
        annual_values, indicator, average=contract.average_preserving
    )

    records: list[dict[str, Any]] = []
    for year_index, fy in enumerate(years):
        quarter_periods = list(june_year_quarters(fy))
        year_values = values[4 * year_index : 4 * year_index + 4].copy()
        fixed_positions = [
            position
            for position, period in enumerate(quarter_periods)
            if period in fixed_lookup
        ]
        fixed_values = {p: fixed_lookup[quarter_periods[p]] for p in fixed_positions}
        benchmark = float(annual_values[year_index])
        if contract.average_preserving:
            benchmark *= 4.0
        if fixed_positions:
            # The published quarters are fixed points. Rescale only the
            # derivable quarters so the year still hits its benchmark.
            free_positions = [p for p in range(4) if p not in fixed_positions]
            target = benchmark - math.fsum(fixed_values.values())
            base = float(year_values[free_positions].sum()) if free_positions else 0.0
            if free_positions and target >= -1e-9:
                if base > 0.0:
                    year_values[free_positions] *= max(target, 0.0) / base
                else:
                    year_values[free_positions] = max(target, 0.0) / len(free_positions)
        year_values = _close_exactly(
            year_values,
            benchmark=benchmark,
            fixed_positions=fixed_positions,
            fixed_values=fixed_values,
            non_negative=contract.positivity_rule == POSITIVITY_REQUIRED,
        )
        residual = _closure_residual(
            year_values,
            benchmark=benchmark,
            fixed_values=fixed_values,
        )
        year_template = group.iloc[year_index].to_dict()
        for position, period in enumerate(quarter_periods):
            if position in fixed_positions:
                continue
            records.append(
                _quarterly_record(
                    year_template,
                    contract=contract,
                    period=period,
                    fy=fy,
                    value=float(year_values[position]),
                    annual_value=float(annual_values[year_index]),
                    residual=residual,
                    fixed_quarters=[quarter_periods[p] for p in fixed_positions],
                    fixed_total=math.fsum(fixed_values.values()),
                    method=contract.derivation_method
                    if contract.derivation_method != METHOD_IDENTITY
                    else METHOD_DENTON,
                    seasonal_basis=contract.seasonal_basis
                    if lookup
                    else NEUTRAL_SEASONAL_BASIS,
                )
            )
    return records


def _close_exactly(
    year_values: np.ndarray,
    *,
    benchmark: float,
    fixed_positions: Sequence[int],
    fixed_values: Mapping[int, float],
    non_negative: bool,
) -> np.ndarray:
    """Make one June year hit its benchmark exactly, without going negative.

    Two remainders have to be removed. The Denton constraint is exact in exact
    arithmetic but ``lstsq`` leaves ~1e-9, and the smoothness objective can put
    a quarter below zero where a series is near-zero for years and then takes
    off (the BEV and PHEV histories do exactly that). Clipping fixes the sign
    and breaks the closure, so the two are resolved together: clip, then
    re-spread the shortfall proportionally across the quarters still free to
    move, and repeat until nothing is negative. The final correction uses
    ``math.fsum`` so ``fsum(quarters) == benchmark`` holds bit for bit.
    """
    out = np.asarray(year_values, dtype=float).copy()
    fixed = set(fixed_positions)
    for position, value in fixed_values.items():
        out[position] = float(value)
    free = [position for position in range(len(out)) if position not in fixed]
    if not free:
        return out

    if non_negative and benchmark >= 0.0:
        for _attempt in range(len(free) + 1):
            negative = [position for position in free if out[position] < 0.0]
            if not negative:
                break
            for position in negative:
                out[position] = 0.0
            movable = [position for position in free if out[position] > 0.0]
            shortfall = benchmark - math.fsum(out.tolist())
            if not movable:
                # Every free quarter is pinned at zero: spread the benchmark
                # evenly rather than leaving the year unreconciled.
                for position in free:
                    out[position] = max(shortfall, 0.0) / len(free)
                break
            total = math.fsum(out[position] for position in movable)
            if total <= 0.0:
                break
            for position in movable:
                out[position] += shortfall * (out[position] / total)

    # Solve the last free quarter by subtraction rather than by adding a
    # correction to it: `benchmark - fsum(rest)` is the closest representable
    # value that closes the year, whereas `x += tiny` can round straight back
    # to `x` and leave the residual in place.
    candidates = [position for position in free if not non_negative or out[position] > 0.0] or free
    correction = max(candidates, key=lambda position: abs(out[position]))
    rest = [value for position, value in enumerate(out.tolist()) if position != correction]
    out[correction] = benchmark - math.fsum(rest)
    return out


def _closure_residual(
    year_values: np.ndarray,
    *,
    benchmark: float,
    fixed_values: Mapping[int, float],
) -> float:
    out = np.asarray(year_values, dtype=float).copy()
    for position, value in fixed_values.items():
        out[position] = float(value)
    return float(benchmark - math.fsum(out.tolist()))


def _compose_identity_quarters(
    group: pd.DataFrame,
    *,
    contract: QuarterlyDisplayContract,
    chart_rows: pd.DataFrame | None,
    annual_rows: pd.DataFrame,
) -> list[dict[str, Any]] | None:
    """Quarters for an accounting identity, built from its components.

    An independent split of a subtotal is annual-consistent but can leave
    material quarter-level residuals against its own parts. Recursing on the
    governed components keeps the identity true at every quarter.
    """
    components = _IDENTITY_COMPONENTS.get(contract.series_id, ())
    if not components or chart_rows is None or chart_rows.empty:
        return None
    template = group.iloc[0].to_dict()
    years = group["_fy"].astype(int).tolist()
    per_component: list[pd.DataFrame] = []
    for component_id in components:
        annual = chart_rows[
            chart_rows.get("time_grain", pd.Series("", index=chart_rows.index)).astype(str).eq("june_year")
            & chart_rows.get("series_id", pd.Series("", index=chart_rows.index)).astype(str).eq(component_id)
            & pd.to_numeric(chart_rows.get("june_year"), errors="coerce").isin(years)
        ].copy()
        for column in ("trace_name", "scenario_name", "fed_path"):
            if column in annual.columns:
                annual = annual[annual[column].fillna("").astype(str).eq(str(template.get(column) or ""))]
        if annual.empty or annual.duplicated("june_year").any():
            return None
        derived = derive_quarterly_rows(annual, chart_rows=chart_rows, apply_display_horizon=False)
        if derived.empty:
            return None
        per_component.append(
            derived[["period", "june_year", "value"]].rename(columns={"value": component_id})
        )
    composed = per_component[0]
    for extra in per_component[1:]:
        composed = composed.merge(extra, on=["period", "june_year"], how="inner", validate="one_to_one")
    if composed.empty:
        return None
    templates_by_fy = {int(row["_fy"]): row.to_dict() for _, row in group.iterrows()}
    annual_by_fy = {int(row["_fy"]): float(row["_value"]) for _, row in group.iterrows()}
    records: list[dict[str, Any]] = []
    for fy, year_rows in composed.groupby("june_year", sort=True):
        year_template = templates_by_fy.get(int(fy))
        if year_template is None:
            continue
        total = year_rows[list(components)].sum(axis=1).to_numpy(dtype=float)
        residual = annual_by_fy[int(fy)] - float(total.sum())
        for offset, row in enumerate(year_rows.itertuples(index=False)):
            records.append(
                _quarterly_record(
                    year_template,
                    contract=contract,
                    period=str(row.period),
                    fy=int(fy),
                    value=float(total[offset]),
                    annual_value=annual_by_fy[int(fy)],
                    residual=residual,
                    fixed_quarters=[],
                    fixed_total=0.0,
                    method=METHOD_IDENTITY,
                    seasonal_basis=contract.seasonal_basis,
                )
            )
    return records or None


def _quarterly_record(
    year_template: Mapping[str, Any],
    *,
    contract: QuarterlyDisplayContract,
    period: str,
    fy: int,
    value: float,
    annual_value: float,
    residual: float,
    fixed_quarters: Sequence[str],
    fixed_total: float,
    method: str,
    seasonal_basis: str,
) -> dict[str, Any]:
    row = {key: value_ for key, value_ in year_template.items() if not str(key).startswith("_")}
    is_official = str(row.get("scenario_role") or "") == "official_comparator"
    row.update(
        {
            "period": period,
            "target_period": period,
            "time_grain": "quarterly",
            "june_year": fy,
            "value": float(value),
            "value_unit": contract.quarterly_unit,
            "horizon": "",
            "horizon_scope": "",
            "actual_quarters": "",
            "forecast_quarters": "",
            "quarters_present": "",
            "plot_allowed": True,
            "value_status": "derived_quarterly_display",
            "data_scope": COVERAGE_ROW_TYPE_DERIVED,
            # `row_type` is deliberately INHERITED from the annual row, not
            # overwritten with the derived label. Downstream filters key off it
            # ("historical_actual" is the escape hatch that keeps Actual rows
            # visible under a scenario filter), so clobbering it would make a
            # derived Actual quarter invisible. The derived status is carried by
            # coverage_row_type, empirical_or_derived, data_scope, value_status
            # and source_basis - five markers, none of which a filter depends on.
            "source_basis": (
                OFFICIAL_DERIVED_PROVENANCE if is_official else CURRENT_DERIVED_PROVENANCE
            ),
            "canonical_period_key": period,
            "canonical_join_key": (
                f"{str(row.get('canonical_stream_key') or contract.series_id.upper())}"
                f"|{period}|{str(row.get('scenario_name') or '')}"
            ),
            # provenance
            "coverage_row_type": COVERAGE_ROW_TYPE_DERIVED,
            "annual_source_period": f"FY{fy}",
            "annual_source_value": float(annual_value),
            "derivation_method": method,
            "seasonal_basis": seasonal_basis,
            "annual_reconciliation_residual": float(residual),
            "empirical_or_derived": DERIVED,
            "fixed_actual_quarters": "; ".join(str(q) for q in fixed_quarters),
            "fixed_actual_total": float(fixed_total),
            "contract_version": CONTRACT_VERSION,
        }
    )
    return row


# ------------------------------------------------------------------- the pack


class QuarterlyDisplayPackError(RuntimeError):
    """The materialised quarterly display pack cannot be trusted."""


class QuarterlyDisplayPackMissing(QuarterlyDisplayPackError):
    """No quarterly display pack has been built."""


class QuarterlyDisplayPackStale(QuarterlyDisplayPackError):
    """A pack exists but its sources have moved underneath it."""


@dataclass(frozen=True)
class QuarterlyDisplayPack:
    """One process-lifetime view of the materialised display rows."""

    manifest: dict[str, Any]
    quarterly_rows: pd.DataFrame
    official_annual_rows: pd.DataFrame
    series_contract: pd.DataFrame
    coverage_status: pd.DataFrame

    def rows_for(
        self,
        series_id: Any,
        *,
        trace_names: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Quarterly rows for one series: an index lookup, not a rebuild."""
        resolved = canonical_series_id(series_id)
        rows = self.quarterly_rows
        block = rows[rows["series_id"].astype(str).eq(resolved)]
        if trace_names is not None:
            block = block[block["trace_name"].astype(str).isin([str(t) for t in trace_names])]
        return block.copy()


# Every input the pack is a function of. A change to any of them must
# invalidate it rather than silently serve last week's split.
_PACK_SOURCE_FILES: tuple[str, ...] = (
    "data/current_revenue_outlook/revenue_chart_rows.parquet",
    "data/revenue_model_source_pack/official_vintage_registry.json",
)
_PACK_SOURCE_TREES: tuple[str, ...] = (
    "data/revenue_model_source_pack/official_vintages",
    "data/revenue_model_source_pack/mbu26_annual_spine",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quarterly_display_pack_source_digest(repo_root: Path | str | None = None) -> str:
    """A stable digest over every input the pack is derived from.

    Memoised per process: hashing the official-vintage tree costs ~15 ms, and a
    Streamlit rerun would otherwise pay it on every lookup. Sources do not
    change under a running server; the builder calls ``clear_caches`` so a
    rebuild is picked up immediately, and tests do the same.
    """
    root = Path(repo_root) if repo_root is not None else _repo_root()
    return _source_digest_cached(str(root))


@lru_cache(maxsize=4)
def _source_digest_cached(root_text: str) -> str:
    root = Path(root_text)
    parts: list[str] = [PACK_SCHEMA_VERSION, BUILDER_VERSION, CONTRACT_VERSION]
    for relative in _PACK_SOURCE_FILES:
        path = root / relative
        parts.append(f"{relative}:{_sha256_file(path) if path.is_file() else 'absent'}")
    for relative in _PACK_SOURCE_TREES:
        tree = root / relative
        if not tree.is_dir():
            parts.append(f"{relative}:absent")
            continue
        for path in sorted(tree.rglob("*")):
            if path.is_file():
                parts.append(f"{path.relative_to(root).as_posix()}:{_sha256_file(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _pack_dir(repo_root: Path | str | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    return root / QUARTERLY_DISPLAY_PACK_DIR


@lru_cache(maxsize=4)
def _load_pack_cached(pack_dir_text: str, digest: str) -> QuarterlyDisplayPack:
    pack_dir = Path(pack_dir_text)
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.is_file():
        raise QuarterlyDisplayPackMissing(
            f"No quarterly display pack at {pack_dir}. Build it with: {_REBUILD_COMMAND}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("schema_version")) != PACK_SCHEMA_VERSION:
        raise QuarterlyDisplayPackStale(
            f"Quarterly display pack schema {manifest.get('schema_version')!r} != "
            f"{PACK_SCHEMA_VERSION!r}. Rebuild with: {_REBUILD_COMMAND}"
        )
    if str(manifest.get("source_digest")) != digest:
        raise QuarterlyDisplayPackStale(
            "Quarterly display pack sources have changed since it was built. "
            f"Rebuild with: {_REBUILD_COMMAND}"
        )
    return QuarterlyDisplayPack(
        manifest=manifest,
        quarterly_rows=pd.read_parquet(pack_dir / "quarterly_rows.parquet"),
        official_annual_rows=pd.read_parquet(pack_dir / "official_annual_rows.parquet"),
        series_contract=pd.read_parquet(pack_dir / "series_contract.parquet"),
        coverage_status=pd.read_parquet(pack_dir / "coverage_status.parquet"),
    )


def load_quarterly_display_pack(repo_root: Path | str | None = None) -> QuarterlyDisplayPack:
    """Load the materialised pack once per process, fail-closed if stale."""
    pack_dir = _pack_dir(repo_root)
    return _load_pack_cached(str(pack_dir), quarterly_display_pack_source_digest(repo_root))


def clear_caches() -> None:
    """Drop every memoised view. Tests and the builder call this."""
    _load_pack_cached.cache_clear()
    _source_digest_cached.cache_clear()
    _label_lookup.cache_clear()


# ------------------------------------------------------------------ public API


def quarterly_rows_for_selected_series(
    series_id: Any,
    *,
    trace_names: Sequence[str] | None = None,
    annual_rows: pd.DataFrame | None = None,
    chart_rows: pd.DataFrame | None = None,
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Quarterly display rows for one selected series.

    Serves the materialised pack for the traces it carries - a filter, never a
    live disaggregation - and derives, under the same contract, only the traces
    the pack cannot know about (runtime policy states, conflict paths and any
    other lever-dependent annual rows the caller passes in ``annual_rows``).
    """
    resolved = canonical_series_id(series_id)
    blocks: list[pd.DataFrame] = []
    served: set[str] = set()
    try:
        pack = load_quarterly_display_pack(repo_root)
    except QuarterlyDisplayPackError:
        pack = None
    if pack is not None:
        block = pack.rows_for(resolved, trace_names=trace_names)
        if not block.empty:
            blocks.append(block)
            served = set(block["trace_name"].astype(str))

    if annual_rows is not None and not annual_rows.empty:
        pending = annual_rows[
            annual_rows.get("series_id", pd.Series(dtype=str)).astype(str).eq(resolved)
        ]
        if trace_names is not None:
            pending = pending[
                pending.get("trace_name", pd.Series(dtype=str))
                .astype(str)
                .isin([str(t) for t in trace_names])
            ]
        pending = pending[~pending.get("trace_name", pd.Series(dtype=str)).astype(str).isin(served)]
        if not pending.empty:
            blocks.append(derive_quarterly_rows(pending, chart_rows=chart_rows))

    if not blocks:
        return pd.DataFrame(
            columns=list(_runtime_chart_columns()) + list(_QUARTERLY_PROVENANCE_COLUMNS)
        )
    return display_horizon_filter(
        pd.concat(blocks, ignore_index=True, sort=False)
    ).reset_index(drop=True)


def quarterly_coverage_status(
    chart_rows: pd.DataFrame | None = None,
    *,
    quarterly_rows: pd.DataFrame | None = None,
    official_rows: pd.DataFrame | None = None,
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """The owner-facing coverage table: one row per selectable series.

    Answers, for every series a reader can pick: is there a BEFU26 line, an
    MBU26 line, native quarters, derived quarters; over what window; by what
    method; and what the reader should not over-read.
    """
    root = Path(repo_root) if repo_root is not None else _repo_root()
    if chart_rows is None:
        chart_rows = pd.read_parquet(root / CURRENT_REVENUE_OUTLOOK_DIR / "revenue_chart_rows.parquet")
    if quarterly_rows is None or official_rows is None:
        try:
            pack = load_quarterly_display_pack(root)
        except QuarterlyDisplayPackError:
            pack = None
        if quarterly_rows is None:
            quarterly_rows = pack.quarterly_rows if pack is not None else pd.DataFrame()
        if official_rows is None:
            official_rows = pack.official_annual_rows if pack is not None else pd.DataFrame()

    combined_annual = _concat_non_empty(
        [
            chart_rows[chart_rows.get("time_grain", pd.Series(dtype=str)).astype(str).eq("june_year")]
            if not chart_rows.empty
            else pd.DataFrame(),
            official_rows if official_rows is not None else pd.DataFrame(),
        ]
    )
    native = (
        chart_rows[chart_rows.get("time_grain", pd.Series(dtype=str)).astype(str).eq("quarterly")]
        if not chart_rows.empty
        else pd.DataFrame()
    )

    records: list[dict[str, Any]] = []
    for contract in QUARTERLY_DISPLAY_CONTRACT:
        annual = _series_slice(combined_annual, contract.series_id)
        native_block = _series_slice(native, contract.series_id)
        derived_block = _series_slice(quarterly_rows, contract.series_id)
        derived_periods = sorted(derived_block["period"].astype(str)) if not derived_block.empty else []
        native_periods = sorted(native_block["period"].astype(str)) if not native_block.empty else []
        all_periods = sorted(set(derived_periods) | set(native_periods))
        records.append(
            {
                "series_id": contract.series_id,
                "display_name": contract.display_name,
                "unit": contract.unit,
                "quarterly_unit": contract.quarterly_unit,
                "metric_type": contract.metric_type,
                "annual_semantics": contract.annual_semantics,
                "quarterly_source": contract.quarterly_source,
                "befu26_available": _trace_present(annual, "BEFU26 official"),
                "mbu26_available": _trace_present(annual, "MBU26 official"),
                "actual_available": _trace_present(annual, "Actual"),
                "native_quarterly_available": not native_block.empty,
                "native_quarterly_traces": _joined(native_block, "trace_name"),
                "derived_quarterly_available": not derived_block.empty,
                "derived_quarterly_traces": _joined(derived_block, "trace_name"),
                "first_quarter": all_periods[0] if all_periods else "",
                "last_quarter": all_periods[-1] if all_periods else "",
                "derivation_method": contract.derivation_method,
                "seasonal_basis": contract.seasonal_basis,
                "annual_reconciliation_rule": contract.annual_reconciliation_rule,
                "positivity_rule": contract.positivity_rule,
                "provenance_label": contract.provenance_label,
                "source_window": contract.source_window,
                "limitation": contract.limitation,
                "contract_version": CONTRACT_VERSION,
            }
        )
    return pd.DataFrame.from_records(records)


def annual_reconciliation_audit(quarterly_rows: pd.DataFrame) -> pd.DataFrame:
    """One row per derived (series, trace, June year) with its closure residual.

    Recomputed from the emitted values rather than trusting the residual the
    builder recorded: a builder that miscalculated its own residual would
    otherwise certify itself.
    """
    columns = [
        "series_id",
        "trace_name",
        "scenario_name",
        "june_year",
        "annual_source_value",
        "derived_quarters",
        "fixed_actual_quarters",
        "fixed_actual_total",
        "derived_sum",
        "residual",
        "relative_residual",
        "reconciles",
    ]
    if quarterly_rows is None or quarterly_rows.empty:
        return pd.DataFrame(columns=columns)
    group_columns = [
        column
        for column in ("series_id", "trace_name", "scenario_name", "june_year")
        if column in quarterly_rows.columns
    ]
    records: list[dict[str, Any]] = []
    for key, group in quarterly_rows.groupby(group_columns, dropna=False):
        keys = dict(zip(group_columns, key if isinstance(key, tuple) else (key,)))
        annual = float(pd.to_numeric(group["annual_source_value"], errors="coerce").iloc[0])
        fixed_text = str(group["fixed_actual_quarters"].iloc[0] or "")
        fixed_total = float(pd.to_numeric(group["fixed_actual_total"], errors="coerce").iloc[0])
        derived_sum = math.fsum(pd.to_numeric(group["value"], errors="coerce").tolist())
        # A year closes on its derived quarters PLUS the published ones it had
        # to hand over from. Dropping the second term would make every partial
        # year look broken and every check on it vacuous.
        residual = annual - math.fsum((derived_sum, fixed_total))
        relative = abs(residual) / max(abs(annual), 1e-12)
        records.append(
            {
                **keys,
                "annual_source_value": annual,
                "derived_quarters": int(len(group)),
                "fixed_actual_quarters": fixed_text,
                "fixed_actual_total": fixed_total,
                "derived_sum": derived_sum,
                "residual": residual,
                "relative_residual": relative,
                "reconciles": bool(
                    abs(residual) <= RECONCILIATION_ABS_TOLERANCE
                    or relative <= RECONCILIATION_REL_TOLERANCE
                ),
            }
        )
    return pd.DataFrame.from_records(records, columns=columns)


def _concat_non_empty(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    blocks = [frame for frame in frames if frame is not None and not frame.empty]
    if not blocks:
        return pd.DataFrame()
    return pd.concat(blocks, ignore_index=True, sort=False)


def _series_slice(frame: pd.DataFrame | None, series_id: str) -> pd.DataFrame:
    if frame is None or frame.empty or "series_id" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["series_id"].astype(str).eq(series_id)]


def _trace_present(frame: pd.DataFrame, trace_name: str) -> bool:
    if frame is None or frame.empty or "trace_name" not in frame.columns:
        return False
    return bool(frame["trace_name"].astype(str).eq(trace_name).any())


def _joined(frame: pd.DataFrame, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return "; ".join(sorted(set(frame[column].astype(str))))


# ------------------------------------------------------------------- the build


def build_quarterly_display_pack(
    *,
    repo_root: Path | str | None = None,
    output_dir: Path | str | None = None,
) -> QuarterlyDisplayPack:
    """Materialise the display pack from committed sources.

    Deterministic by construction: the inputs are committed packs, the split is
    a closed-form solve and the rows are sorted before writing, so building
    twice produces byte-identical files.
    """
    root = Path(repo_root) if repo_root is not None else _repo_root()
    pack_dir = Path(output_dir) if output_dir is not None else _pack_dir(root)
    pack_dir.mkdir(parents=True, exist_ok=True)

    chart_rows = pd.read_parquet(root / CURRENT_REVENUE_OUTLOOK_DIR / "revenue_chart_rows.parquet")
    official = missing_official_rows(chart_rows, repo_root=root)
    # The derivation must see the newly materialised official annual rows, or
    # the series this branch restores would still have no quarterly line.
    annual_universe = _concat_non_empty(
        [
            chart_rows[chart_rows["time_grain"].astype(str).eq("june_year")],
            official,
        ]
    )
    annual_universe = display_horizon_filter(annual_universe)
    governed = annual_universe[
        annual_universe["series_id"].astype(str).isin(selectable_series_ids())
    ]
    quarterly = derive_quarterly_rows(governed, chart_rows=chart_rows)

    reconciliation = annual_reconciliation_audit(quarterly)
    unreconciled = reconciliation[~reconciliation["reconciles"].astype(bool)]
    if not unreconciled.empty:
        sample = unreconciled.head(5)[["series_id", "trace_name", "june_year", "residual"]]
        raise QuarterlyDisplayPackError(
            "Derived quarterly rows do not reconcile to their annual anchors:\n"
            f"{sample.to_string(index=False)}"
        )

    contract = quarterly_contract_frame()
    coverage = quarterly_coverage_status(
        chart_rows,
        quarterly_rows=quarterly,
        official_rows=official,
        repo_root=root,
    )

    sort_keys = ["series_id", "trace_name", "scenario_name", "period"]
    quarterly = quarterly.sort_values(
        [key for key in sort_keys if key in quarterly.columns], kind="stable"
    ).reset_index(drop=True)
    official = official.sort_values(
        [key for key in ("series_id", "trace_name", "period") if key in official.columns],
        kind="stable",
    ).reset_index(drop=True)

    manifest = {
        "schema_version": PACK_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "source_digest": quarterly_display_pack_source_digest(root),
        "display_horizon_last_fy": DISPLAY_HORIZON_LAST_FY,
        "display_horizon_last_quarter": DISPLAY_HORIZON_LAST_QUARTER,
        "rebuild_command": _REBUILD_COMMAND,
        "selectable_series": list(selectable_series_ids()),
        "quarterly_rows": int(len(quarterly)),
        "official_annual_rows": int(len(official)),
        "official_series_restored": sorted(set(official["series_id"].astype(str)))
        if not official.empty
        else [],
        "quarterly_traces": sorted(set(quarterly["trace_name"].astype(str)))
        if not quarterly.empty
        else [],
        "reconciled_series_trace_years": int(len(reconciliation)),
        "worst_relative_reconciliation_residual": float(
            pd.to_numeric(reconciliation["relative_residual"], errors="coerce").max()
        )
        if not reconciliation.empty
        else 0.0,
        "notes": (
            "Derived quarterly rows are indicative display values benchmarked to a "
            "governed June-year total. They are not published quarterly actuals and "
            "not direct model outputs. Official-comparator quarters carry the "
            f"provenance label {OFFICIAL_DERIVED_PROVENANCE!r}."
        ),
    }

    _write_frame(quarterly, pack_dir / "quarterly_rows.parquet")
    _write_frame(official, pack_dir / "official_annual_rows.parquet")
    _write_frame(contract, pack_dir / "series_contract.parquet")
    _write_frame(coverage, pack_dir / "coverage_status.parquet")
    _write_frame(reconciliation, pack_dir / "annual_reconciliation_audit.parquet")
    coverage.to_csv(pack_dir / "coverage_status.csv", index=False, lineterminator="\n")
    contract.to_csv(pack_dir / "quarterly_series_contract.csv", index=False, lineterminator="\n")
    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    clear_caches()
    return QuarterlyDisplayPack(
        manifest=manifest,
        quarterly_rows=quarterly,
        official_annual_rows=official,
        series_contract=contract,
        coverage_status=coverage,
    )


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    """Write a frame with every object column normalised to text.

    Chart rows mix ``pd.NA``, ``None`` and floats in the same object column;
    Arrow would either reject that or round-trip it to a different dtype, and
    either outcome breaks byte-idempotence on rebuild.
    """
    out = frame.copy()
    for column in out.columns:
        if out[column].dtype == object:
            out[column] = out[column].map(
                lambda value: "" if value is None or (not isinstance(value, str) and pd.isna(value)) else value
            )
            if not out[column].map(lambda value: isinstance(value, str)).all():
                out[column] = out[column].astype(str)
    out.to_parquet(path, index=False)

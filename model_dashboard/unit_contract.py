"""Canonical unit contract: conversions are driven by declared units only.

The production paths historically inferred scale from magnitude - "divide by a
million if the value looks too big" (``abs(x) > 10_000_000``). That works until
a genuinely large value or a re-based series crosses the threshold, at which
point the wrong rows are silently rescaled by six orders of magnitude. P1.1
replaces every such inference: a conversion happens only because the source row
DECLARES a unit, and an undeclared or unknown unit fails closed.

A second, quieter permissiveness is also closed here. Three copies of a
``_display_unit_scale`` helper substring-matched the declared unit ("million"
in the text -> 1e6) and returned 1.0 for anything unrecognised, so a typo or a
new unit silently became "already unscaled". Scale now resolves through this
registry and raises on an unknown declaration.

The registry is deliberately closed: adding a unit means adding it here, with
its dimension and conversions, in one reviewed place.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CANONICAL_UNITS",
    "DIMENSION_BY_UNIT",
    "SERIES_CANONICAL_UNITS",
    "SOURCE_UNIT_ALIASES",
    "UnitContractError",
    "canonical_unit_for",
    "convert_declared",
    "display_scale_for",
    "unit_registry_frames",
]


class UnitContractError(ValueError):
    """A conversion was requested without a valid declared-unit basis."""


# ---------------------------------------------------------------- canonical
# One identifier per physical meaning-and-scale.
KM_RAW = "km"
KM_MILLION = "million_km"
VKT_PER_CAPITA_KM = "km_per_person"
LITRES_RAW = "litres"
LITRES_MILLION = "million_litres"
LITRES_PER_100KM = "litres_per_100km"
NZD = "nzd"
NZD_MILLION = "million_nzd"
NZD_REAL = "real_nzd"
NZD_REAL_PER_PERSON = "real_nzd_per_person"
NZD_PER_LITRE = "nzd_per_litre"
CENTS_PER_LITRE = "cents_per_litre"
NZD_PER_1000KM = "nzd_per_1000km"
PERSONS = "persons"
PERSONS_MILLION = "million_persons"
SHARE_FRACTION = "share_fraction"
PERCENT = "percent"
PERCENTAGE_POINTS = "percentage_points"
FRACTION_PER_ANNUM = "fraction_per_annum"
FACTOR = "dimensionless_factor"
BOOLEAN_FLAG = "boolean_flag"
TONNE_KM = "tonne_km"
MODEL_TARGET_UNITS = "model_target_units"
LOG_TRANSFORMED = "log_transformed"
SYSTEM = "system_metadata"

# dimension -> conversions are only ever permitted WITHIN a dimension.
DIMENSION_BY_UNIT: dict[str, str] = {
    KM_RAW: "distance",
    KM_MILLION: "distance",
    VKT_PER_CAPITA_KM: "distance_per_person",
    LITRES_RAW: "volume",
    LITRES_MILLION: "volume",
    LITRES_PER_100KM: "volume_per_distance",
    NZD: "currency",
    NZD_MILLION: "currency",
    NZD_REAL: "currency_real",
    NZD_REAL_PER_PERSON: "currency_real_per_person",
    NZD_PER_LITRE: "currency_per_volume",
    CENTS_PER_LITRE: "currency_per_volume",
    NZD_PER_1000KM: "currency_per_distance",
    PERSONS: "population",
    PERSONS_MILLION: "population",
    SHARE_FRACTION: "proportion",
    PERCENT: "proportion",
    PERCENTAGE_POINTS: "proportion_difference",
    FRACTION_PER_ANNUM: "rate_per_time",
    FACTOR: "dimensionless",
    BOOLEAN_FLAG: "dimensionless",
    TONNE_KM: "freight_task",
    MODEL_TARGET_UNITS: "opaque_model_space",
    LOG_TRANSFORMED: "opaque_model_space",
    SYSTEM: "metadata",
}
CANONICAL_UNITS = tuple(DIMENSION_BY_UNIT)

# Every source-unit string that may appear on a governed row. Matching is
# case-insensitive on the stripped string; anything absent fails closed.
SOURCE_UNIT_ALIASES: dict[str, str] = {
    "net km": KM_RAW,
    "km": KM_RAW,
    "million km": KM_MILLION,
    "m km": KM_MILLION,
    "vkt per capita": VKT_PER_CAPITA_KM,
    "km/person": VKT_PER_CAPITA_KM,
    "km/person/fy": VKT_PER_CAPITA_KM,
    "litres": LITRES_RAW,
    "million litres": LITRES_MILLION,
    "million l": LITRES_MILLION,
    "m l": LITRES_MILLION,
    "l/100km": LITRES_PER_100KM,
    "$ nominal ex gst": NZD,
    "$m nominal ex gst": NZD_MILLION,
    "$m ex gst": NZD_MILLION,
    "$m": NZD_MILLION,
    "real nzd": NZD_REAL,
    "real nzd/person": NZD_REAL_PER_PERSON,
    "nzd/l": NZD_PER_LITRE,
    "nzd/litre": NZD_PER_LITRE,
    "cents/litre": CENTS_PER_LITRE,
    "nzd/1,000 km": NZD_PER_1000KM,
    "nzd/1000km": NZD_PER_1000KM,
    "people": PERSONS,
    "persons": PERSONS,
    "million people": PERSONS_MILLION,
    "share": SHARE_FRACTION,
    "fraction": SHARE_FRACTION,
    "percent": PERCENT,
    "percentage points": PERCENTAGE_POINTS,
    "fraction p.a.": FRACTION_PER_ANNUM,
    "elasticity": FACTOR,
    "factor": FACTOR,
    "index": FACTOR,
    "derived interaction": FACTOR,
    "0/1": BOOLEAN_FLAG,
    "tonne-km": TONNE_KM,
    "model target units": MODEL_TARGET_UNITS,
    "log transformed": LOG_TRANSFORMED,
    "system": SYSTEM,
}

# Conversions stored as (operation, operand) so the exact floating-point
# operation of the governed packs survives: they have always DIVIDED raw km by
# 1e6, and x / 1e6 differs from x * 1e-6 in the last ulp. Absent pair = refuse.
_CONVERSIONS: dict[tuple[str, str], tuple[str, float]] = {
    (KM_RAW, KM_MILLION): ("/", 1_000_000.0),
    (KM_MILLION, KM_RAW): ("*", 1_000_000.0),
    (LITRES_RAW, LITRES_MILLION): ("/", 1_000_000.0),
    (LITRES_MILLION, LITRES_RAW): ("*", 1_000_000.0),
    (NZD, NZD_MILLION): ("/", 1_000_000.0),
    (NZD_MILLION, NZD): ("*", 1_000_000.0),
    (PERSONS, PERSONS_MILLION): ("/", 1_000_000.0),
    (PERSONS_MILLION, PERSONS): ("*", 1_000_000.0),
    (CENTS_PER_LITRE, NZD_PER_LITRE): ("/", 100.0),
    (NZD_PER_LITRE, CENTS_PER_LITRE): ("*", 100.0),
    (PERCENT, SHARE_FRACTION): ("/", 100.0),
    (SHARE_FRACTION, PERCENT): ("*", 100.0),
}

# Scale from a DISPLAYED unit to its unscaled base, replacing the substring
# heuristics. Only scaled units carry a factor; everything else is 1.0.
_DISPLAY_SCALE: dict[str, float] = {
    KM_MILLION: 1_000_000.0,
    LITRES_MILLION: 1_000_000.0,
    NZD_MILLION: 1_000_000.0,
    PERSONS_MILLION: 1_000_000.0,
}

# Decision-facing series and the canonical unit each must carry.
SERIES_CANONICAL_UNITS: dict[str, str] = {
    "ped_vkt_per_capita": VKT_PER_CAPITA_KM,
    "ped_volume": LITRES_MILLION,
    "light_petrol_vkt": KM_MILLION,
    "light_ruc_net_km": KM_MILLION,
    "light_bev_ruc_net_km": KM_MILLION,
    "phev_ruc_net_km": KM_MILLION,
    "heavy_ruc_net_km": KM_MILLION,
    "heavy_bev_ruc_net_km": KM_MILLION,
    "current_light_ruc_conventional_modelled_km": KM_MILLION,
    "tuc_gtk": TONNE_KM,
    "gross_ped_revenue": NZD_MILLION,
    "gross_lpg_revenue": NZD_MILLION,
    "gross_cng_revenue": NZD_MILLION,
    "gross_fed_revenue": NZD_MILLION,
    "fed_refunds": NZD_MILLION,
    "net_fed_revenue": NZD_MILLION,
    "light_ruc_net_revenue": NZD_MILLION,
    "light_bev_ruc_net_revenue": NZD_MILLION,
    "phev_ruc_net_revenue": NZD_MILLION,
    "heavy_ruc_net_revenue": NZD_MILLION,
    "heavy_bev_ruc_net_revenue": NZD_MILLION,
    "ruc_refunds": NZD_MILLION,
    "ruc_admin_revenue": NZD_MILLION,
    "gross_ruc_revenue": NZD_MILLION,
    "ruc_revenue_net_admin": NZD_MILLION,
    "total_ruc_net_revenue": NZD_MILLION,
    "mr1_revenue": NZD_MILLION,
    "mr2_revenue": NZD_MILLION,
    "coo_revenue": NZD_MILLION,
    "gross_mvr_revenue": NZD_MILLION,
    "mvr_admin_revenue": NZD_MILLION,
    "mvr_refunds": NZD_MILLION,
    "mvr_revenue_net_admin_coo": NZD_MILLION,
    "net_mvr_revenue": NZD_MILLION,
    "tuc_net_revenue": NZD_MILLION,
    "total_gross_revenue": NZD_MILLION,
    "total_admin_fees": NZD_MILLION,
    "total_revenue_net_admin": NZD_MILLION,
    "total_refunds": NZD_MILLION,
    "total_nltf_net_revenue": NZD_MILLION,
    "total_fed_ruc_net_revenue": NZD_MILLION,
}


def canonical_unit_for(source_unit: object, *, context: str = "") -> str:
    """Resolve a declared source-unit string to its canonical identifier.

    Fails closed on an empty, missing or unknown declaration - the caller may
    not guess from magnitude or from a substring.
    """
    text = str(source_unit or "").strip()
    if not text:
        raise UnitContractError(
            f"Row has no declared unit{f' ({context})' if context else ''}; "
            "magnitude-based inference is prohibited."
        )
    canonical = SOURCE_UNIT_ALIASES.get(text.casefold())
    if canonical is None:
        raise UnitContractError(
            f"Declared unit {text!r} is not in the canonical registry"
            f"{f' ({context})' if context else ''}. Add it to "
            "model_dashboard/unit_contract.py rather than inferring."
        )
    return canonical


@dataclass(frozen=True)
class DeclaredConversion:
    value: float
    source_unit: str
    canonical_source: str
    canonical_target: str
    operation: str
    operand: float

    @property
    def converted(self) -> float:
        if self.operation == "identity":
            return self.value
        if self.operation == "/":
            return self.value / self.operand
        return self.value * self.operand

    @property
    def conversion_factor(self) -> float:
        """Net multiplicative factor, for the registry/audit artifacts."""
        if self.operation == "identity":
            return 1.0
        return 1.0 / self.operand if self.operation == "/" else self.operand


def convert_declared(
    value: float,
    source_unit: object,
    target_canonical: str,
    *,
    context: str = "",
) -> DeclaredConversion:
    """Convert ``value`` to ``target_canonical`` using only its declared unit."""
    canonical_source = canonical_unit_for(source_unit, context=context)
    if target_canonical not in DIMENSION_BY_UNIT:
        raise UnitContractError(f"Unknown target canonical unit {target_canonical!r}.")
    if canonical_source == target_canonical:
        operation, operand = "identity", 1.0
    else:
        if DIMENSION_BY_UNIT[canonical_source] != DIMENSION_BY_UNIT[target_canonical]:
            raise UnitContractError(
                f"Dimensionally incompatible conversion {canonical_source!r} "
                f"({DIMENSION_BY_UNIT[canonical_source]}) -> {target_canonical!r} "
                f"({DIMENSION_BY_UNIT[target_canonical]})"
                f"{f' ({context})' if context else ''}."
            )
        pair = _CONVERSIONS.get((canonical_source, target_canonical))
        if pair is None:
            raise UnitContractError(
                f"No declared conversion from {canonical_source!r} to "
                f"{target_canonical!r}{f' ({context})' if context else ''}; refusing to infer."
            )
        operation, operand = pair
    return DeclaredConversion(
        value=float(value),
        source_unit=str(source_unit).strip(),
        canonical_source=canonical_source,
        canonical_target=target_canonical,
        operation=operation,
        operand=operand,
    )


def display_scale_for(unit: object, *, context: str = "") -> float:
    """Scale from a displayed unit to its unscaled base, by declaration.

    Replaces the three substring copies of ``_display_unit_scale``. An unknown
    declaration raises instead of silently returning 1.0, which previously made
    a typo indistinguishable from an already-unscaled unit.
    """
    canonical = canonical_unit_for(unit, context=context)
    return _DISPLAY_SCALE.get(canonical, 1.0)


def unit_registry_frames():
    """(series, aliases, conversions) frames for the committed artifacts."""
    import pandas as pd

    series_rows = [
        {
            "series_id": series_id,
            "canonical_unit": canonical,
            "dimension": DIMENSION_BY_UNIT[canonical],
            "display_scale_to_base": _DISPLAY_SCALE.get(canonical, 1.0),
            "unit_contract_status": "declared",
        }
        for series_id, canonical in sorted(SERIES_CANONICAL_UNITS.items())
    ]
    alias_rows = [
        {
            "source_unit": alias,
            "canonical_unit": canonical,
            "dimension": DIMENSION_BY_UNIT[canonical],
            "declaration_source": "row value_unit / unit column",
            "conversion_basis": "declared_alias",
        }
        for alias, canonical in sorted(SOURCE_UNIT_ALIASES.items())
    ]
    conversion_rows = [
        {
            "from_unit": source,
            "to_unit": target,
            "dimension": DIMENSION_BY_UNIT[source],
            "operation": operation,
            "operand": operand,
            "conversion_factor": (1.0 / operand if operation == "/" else operand),
            "permitted_direction": "one_way_pair_declared_both_ways"
            if (target, source) in _CONVERSIONS
            else "one_way",
            "lossless": True,
            "conversion_basis": "canonical_registry",
        }
        for (source, target), (operation, operand) in sorted(_CONVERSIONS.items())
    ]
    return (
        pd.DataFrame(series_rows),
        pd.DataFrame(alias_rows),
        pd.DataFrame(conversion_rows),
    )

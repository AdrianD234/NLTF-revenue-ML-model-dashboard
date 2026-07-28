"""Canonical unit contract: conversions are driven by declared units only.

The production paths historically inferred scale from magnitude - "divide by a
million if the value looks too big" (``abs(x) > 10_000_000``). That works until
a genuinely large value or a re-based series crosses the threshold, at which
point the wrong rows are silently rescaled by six orders of magnitude. P1.1
replaces every such inference: a conversion happens only because the source row
DECLARES a unit, and an undeclared or unknown unit fails closed.

The registry is deliberately small and closed: adding a unit means adding it
here, with its conversions, in one reviewed place.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CANONICAL_UNITS",
    "SERIES_CANONICAL_UNITS",
    "SOURCE_UNIT_ALIASES",
    "UnitContractError",
    "canonical_unit_for",
    "convert_declared",
    "unit_registry_frame",
]


class UnitContractError(ValueError):
    """A conversion was requested without a valid declared-unit basis."""


# ---------------------------------------------------------------- canonical
# One identifier per physical meaning-and-scale. These are the only units a
# decision-facing series may carry after normalisation.
KM_RAW = "km"
KM_MILLION = "million_km"
VKT_PER_CAPITA_KM = "km_per_person"
LITRES_MILLION = "million_litres"
NZD_MILLION = "million_nzd"
NZD_PER_LITRE = "nzd_per_litre"
NZD_PER_1000KM = "nzd_per_1000km"
PERSONS = "persons"
PERSONS_MILLION = "million_persons"
SHARE_FRACTION = "share_fraction"
FACTOR = "dimensionless_factor"
TONNE_KM = "tonne_km"

CANONICAL_UNITS = (
    KM_RAW,
    KM_MILLION,
    VKT_PER_CAPITA_KM,
    LITRES_MILLION,
    NZD_MILLION,
    NZD_PER_LITRE,
    NZD_PER_1000KM,
    PERSONS,
    PERSONS_MILLION,
    SHARE_FRACTION,
    FACTOR,
    TONNE_KM,
)

# Every source-unit string that may legitimately appear on a governed row,
# mapped to its canonical identifier. Matching is case-insensitive on the
# stripped string; anything absent here fails closed.
SOURCE_UNIT_ALIASES: dict[str, str] = {
    "net km": KM_RAW,
    "km": KM_RAW,
    "million km": KM_MILLION,
    "m km": KM_MILLION,
    "vkt per capita": VKT_PER_CAPITA_KM,
    "km/person": VKT_PER_CAPITA_KM,
    "million litres": LITRES_MILLION,
    "m l": LITRES_MILLION,
    "$m nominal ex gst": NZD_MILLION,
    "$m": NZD_MILLION,
    "nzd/l": NZD_PER_LITRE,
    "nzd/litre": NZD_PER_LITRE,
    "nzd per 1,000 km": NZD_PER_1000KM,
    "nzd/1000km": NZD_PER_1000KM,
    "people": PERSONS,
    "persons": PERSONS,
    "million people": PERSONS_MILLION,
    "share": SHARE_FRACTION,
    "fraction": SHARE_FRACTION,
    "factor": FACTOR,
    "index": FACTOR,
    "tonne-km": TONNE_KM,
}

# Conversions between canonical units, stored as (operation, operand) so the
# exact floating-point operation of the governed packs is preserved: the packs
# have always DIVIDED raw km by 1e6, and x / 1e6 differs from x * 1e-6 in the
# last ulp. Absent pair = refuse.
_CONVERSIONS: dict[tuple[str, str], tuple[str, float]] = {
    (KM_RAW, KM_MILLION): ("/", 1_000_000.0),
    (KM_MILLION, KM_RAW): ("*", 1_000_000.0),
    (PERSONS, PERSONS_MILLION): ("/", 1_000_000.0),
    (PERSONS_MILLION, PERSONS): ("*", 1_000_000.0),
}

# Decision-facing series and the canonical unit each must carry after
# normalisation. This is the inventory the unit registry artifact reports and
# the completeness tests assert over.
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
    not guess from magnitude.
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
    if target_canonical not in CANONICAL_UNITS:
        raise UnitContractError(f"Unknown target canonical unit {target_canonical!r}.")
    if canonical_source == target_canonical:
        operation, operand = "identity", 1.0
    else:
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


def unit_registry_frame():
    """The unit inventory as a frame, for the committed registry artifact."""
    import pandas as pd

    rows = [
        {
            "series_id": series_id,
            "canonical_unit": canonical,
            "unit_contract_status": "declared",
        }
        for series_id, canonical in sorted(SERIES_CANONICAL_UNITS.items())
    ]
    alias_rows = [
        {
            "source_unit": alias,
            "canonical_unit": canonical,
            "conversion_basis": "declared_alias",
        }
        for alias, canonical in sorted(SOURCE_UNIT_ALIASES.items())
    ]
    conversion_rows = [
        {
            "from_unit": pair[0],
            "to_unit": pair[1],
            "operation": f"{operation} {operand:g}",
            "conversion_factor": (1.0 / operand if operation == "/" else operand),
            "conversion_basis": "canonical_registry",
        }
        for pair, (operation, operand) in sorted(_CONVERSIONS.items())
    ]
    return (
        pd.DataFrame(rows),
        pd.DataFrame(alias_rows),
        pd.DataFrame(conversion_rows),
    )

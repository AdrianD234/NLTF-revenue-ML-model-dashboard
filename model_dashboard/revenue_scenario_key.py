"""The typed identity of one Revenue Outlook computation.

Replaces the positional ``ev_uptake_key`` tuple, whose slots had accumulated
two independent meanings.  Slot 6 was read as the official comparator vintage
id by ``_official_vintage_scope`` and as a Heavy-BEV transition boolean by
``_heavy_bev_transition_enabled``.  Production always writes a non-empty
vintage id there, so ``bool("BEFU26")`` silently switched Heavy-BEV
reclassification ON in every real render, against the settled
``HEAVY_RUC: not_reclassified`` contract.

Every control now has exactly one named field.  A vintage id is a ``str`` and
can never be read as a flag; a flag is a ``bool`` and can never be read as an
id.  Adding a control means adding a field, not appending a slot and hoping no
existing reader shifts.

The key is frozen and hashable, so it can be passed straight to
``st.cache_data``, and it serialises canonically so its digest is stable
across processes and platforms.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from typing import Any

__all__ = [
    "HEAVY_BEV_DEFAULT",
    "RevenueScenarioComputationKey",
    "as_scenario_key",
]

# Heavy-BEV reclassification is a separate, explicit sensitivity. It must be
# opt-in: a LIGHT fleet composition choice must never reclassify Heavy RUC.
HEAVY_BEV_DEFAULT = False

# Legacy positional layout, retained ONLY so historic cache keys and older
# tests can be adapted. Never index production code by these.
_LEGACY_UPTAKE_BASIS = 0
_LEGACY_CUSTOM_EV_LEVERS = 1
_LEGACY_ERUC_LEVERS = 2
_LEGACY_CURRENT_FED_POLICY = 3
_LEGACY_OFFICIAL_FED_POLICY = 4
_LEGACY_PED_RETENTION = 5
# Slot 6 is the collision. In production it holds the official vintage id; in
# pre-vintage-selector test keys it holds the Heavy-BEV flag. They are told
# apart by TYPE, never by position alone.
_LEGACY_SLOT_SIX = 6
_LEGACY_OFFICIAL_OVERLAY = 7
_LEGACY_LONG_RUN_SCHEDULE = 8
_LEGACY_LONG_RUN_SHAPE_VINTAGE = 9


class ScenarioKeyValueError(ValueError):
    """An invalid control value reached the governance key.

    Raised rather than normalised. Silently coercing a bad value would swap
    the scenario identity for a different, valid-looking one - the same class
    of failure as the slot-6 collision, just quieter.
    """


def _as_float_tuple(values: Any, *, field: str) -> tuple[float, ...]:
    """Finite floats only. An unparseable or non-finite entry fails closed."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise ScenarioKeyValueError(
            f"{field}: expected a sequence of numbers, got {type(values).__name__}"
        )
    try:
        iterator = list(values)
    except TypeError as error:
        raise ScenarioKeyValueError(f"{field}: not iterable ({values!r})") from error
    out: list[float] = []
    for index, value in enumerate(iterator):
        if isinstance(value, bool):
            raise ScenarioKeyValueError(f"{field}[{index}]: bool is not a numeric control")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ScenarioKeyValueError(
                f"{field}[{index}]: {value!r} is not numeric"
            ) from error
        if not math.isfinite(number):
            raise ScenarioKeyValueError(f"{field}[{index}]: {value!r} is not finite")
        out.append(number)
    return tuple(out)


def _as_flag(value: Any, *, field: str) -> bool:
    """A real bool only.

    ``bool("False")`` is ``True``, and ``bool("BEFU26")`` is what caused the
    slot-6 defect in the first place. A string or an int here means a caller
    has confused a flag with something else, so say so.
    """
    if isinstance(value, bool):
        return value
    raise ScenarioKeyValueError(
        f"{field}: expected bool, got {type(value).__name__} ({value!r})"
    )


def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_identifier(value: Any, *, field: str) -> str:
    """A text control. Booleans are rejected: a flag is not an id."""
    if isinstance(value, bool):
        raise ScenarioKeyValueError(f"{field}: expected text, got bool ({value!r})")
    return _as_text(value)


@dataclasses.dataclass(frozen=True)
class RevenueScenarioComputationKey:
    """Every value-changing control that identifies one computed scenario.

    Only fields listed here participate in the identity. Display-only choices
    (which traces are ticked, chart layer selection) must NOT be added: they
    would invalidate caches without changing a single value.
    """

    engine: str = ""
    uptake_basis: str = ""
    custom_ev_levers: tuple[float, ...] = ()
    eruc_levers: tuple[float, ...] = ()
    current_fed_policy_state: str = ""
    official_fed_policy_state: str = ""
    ped_retention_sensitivity: bool = False
    heavy_bev_transition: bool = HEAVY_BEV_DEFAULT
    official_comparator_vintage_id: str = ""
    official_comparator_overlay: bool = False
    ped_bridge_mode: str = ""
    bridge_vintage_id: str = ""
    long_run_shape_vintage_id: str = ""
    long_run_transition_schedule_id: str = ""
    macro_scenario_id: str = ""
    conflict_fuel_state: str = ""

    # ------------------------------------------------------------ normalising
    def __post_init__(self) -> None:
        # Coerced through object.__setattr__ because the dataclass is frozen.
        # Normalising here means two keys that mean the same thing hash and
        # serialise the same, whatever shape the caller passed in.
        for name in _TUPLE_FIELDS:
            object.__setattr__(self, name, _as_float_tuple(getattr(self, name), field=name))
        for name in _BOOL_FIELDS:
            object.__setattr__(self, name, _as_flag(getattr(self, name), field=name))
        for name in _TEXT_FIELDS:
            object.__setattr__(self, name, _as_identifier(getattr(self, name), field=name))

    # ------------------------------------------------------------- derivation
    def replace(self, **changes: Any) -> "RevenueScenarioComputationKey":
        """A new key with named fields overridden. No positional surprises."""
        return dataclasses.replace(self, **changes)

    def canonical_mapping(self) -> dict[str, Any]:
        """Field name -> JSON-safe value, in declaration order."""
        mapping: dict[str, Any] = {}
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            mapping[field.name] = list(value) if isinstance(value, tuple) else value
        return mapping

    def serialize(self) -> str:
        """Canonical JSON. Deterministic across processes and platforms."""
        return json.dumps(
            self.canonical_mapping(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    def digest(self) -> str:
        """Stable content hash, safe to embed in a materialised pack."""
        return hashlib.sha256(self.serialize().encode("utf-8")).hexdigest()

    def cache_token(self) -> str:
        """Short digest for cache keys and row labels."""
        return self.digest()[:16]

    # -------------------------------------------------------------- adapters
    @classmethod
    def from_legacy_uptake_tuple(
        cls,
        legacy: tuple[Any, ...] | None,
        *,
        engine: str = "",
        ped_bridge_mode: str = "",
        bridge_vintage_id: str = "",
        macro_scenario_id: str = "",
        conflict_fuel_state: str = "",
        default_official_comparator_vintage_id: str = "",
        default_current_fed_policy_state: str = "",
        policy_normaliser: Any = None,
    ) -> "RevenueScenarioComputationKey":
        """Adapt a historic positional key.

        Slot 6 is disambiguated BY TYPE, which is the whole point: a ``bool``
        there is a pre-vintage-selector test key carrying the Heavy-BEV flag;
        a non-empty ``str`` is a production key carrying the vintage id.
        Neither reading can leak into the other.
        """
        legacy = tuple(legacy or ())

        def slot(index: int, fallback: Any = None) -> Any:
            return legacy[index] if len(legacy) > index else fallback

        slot_six = slot(_LEGACY_SLOT_SIX)
        heavy_bev = HEAVY_BEV_DEFAULT
        vintage_id = default_official_comparator_vintage_id
        if isinstance(slot_six, bool):
            heavy_bev = slot_six
        elif slot_six is not None and _as_text(slot_six):
            vintage_id = _as_text(slot_six)

        current_policy = slot(_LEGACY_CURRENT_FED_POLICY, default_current_fed_policy_state)
        official_policy = slot(_LEGACY_OFFICIAL_FED_POLICY, current_policy)
        # Legacy keys wrote the FED policy as a 0/1 toggle, not a state name.
        # The typed key stores TEXT, so those ints must be resolved to their
        # policy state HERE - stringifying them to "0"/"1" would silently swap
        # a no-uplift counterfactual for the published path. The vocabulary
        # lives in the caller, so it supplies the normaliser.
        for name, value in (
            ("current_fed_policy_state", current_policy),
            ("official_fed_policy_state", official_policy),
        ):
            if value is None or isinstance(value, str):
                continue
            if policy_normaliser is None:
                raise ScenarioKeyValueError(
                    f"{name}: legacy key carries a non-text policy value ({value!r}) "
                    "and no policy_normaliser was supplied. Stringifying it would "
                    'silently swap the policy state for "0"/"1".'
                )
        if policy_normaliser is not None:
            if current_policy is not None and not isinstance(current_policy, str):
                current_policy = policy_normaliser(current_policy)
            if official_policy is not None and not isinstance(official_policy, str):
                official_policy = policy_normaliser(official_policy)
        return cls(
            engine=engine,
            uptake_basis=_as_text(slot(_LEGACY_UPTAKE_BASIS, "")),
            custom_ev_levers=_as_float_tuple(slot(_LEGACY_CUSTOM_EV_LEVERS, ()), field='custom_ev_levers'),
            eruc_levers=_as_float_tuple(slot(_LEGACY_ERUC_LEVERS, ()), field='eruc_levers'),
            current_fed_policy_state=_as_text(current_policy),
            official_fed_policy_state=_as_text(official_policy),
            ped_retention_sensitivity=bool(slot(_LEGACY_PED_RETENTION, False)),
            heavy_bev_transition=heavy_bev,
            official_comparator_vintage_id=vintage_id,
            official_comparator_overlay=bool(slot(_LEGACY_OFFICIAL_OVERLAY, False)),
            ped_bridge_mode=ped_bridge_mode,
            bridge_vintage_id=bridge_vintage_id,
            long_run_shape_vintage_id=_as_text(slot(_LEGACY_LONG_RUN_SHAPE_VINTAGE, "")),
            long_run_transition_schedule_id=_as_text(slot(_LEGACY_LONG_RUN_SCHEDULE, "")),
            macro_scenario_id=macro_scenario_id,
            conflict_fuel_state=conflict_fuel_state,
        )

    def to_legacy_uptake_tuple(self) -> tuple[Any, ...]:
        """The positional shape, for the few un-migrated call sites.

        Slot 6 carries the vintage id, matching what production always wrote.
        The Heavy-BEV flag is deliberately NOT representable here - that
        ambiguity is the defect this class exists to remove - so a round trip
        through this method drops it. Callers that need Heavy-BEV must pass the
        typed key.
        """
        return (
            self.uptake_basis,
            tuple(self.custom_ev_levers),
            tuple(self.eruc_levers),
            self.current_fed_policy_state,
            self.official_fed_policy_state,
            self.ped_retention_sensitivity,
            self.official_comparator_vintage_id,
            self.official_comparator_overlay,
            self.long_run_transition_schedule_id,
            self.long_run_shape_vintage_id,
        )


_BOOL_FIELDS = (
    "ped_retention_sensitivity",
    "heavy_bev_transition",
    "official_comparator_overlay",
)
_TEXT_FIELDS = (
    "engine",
    "uptake_basis",
    "current_fed_policy_state",
    "official_fed_policy_state",
    "official_comparator_vintage_id",
    "ped_bridge_mode",
    "bridge_vintage_id",
    "long_run_shape_vintage_id",
    "long_run_transition_schedule_id",
    "macro_scenario_id",
    "conflict_fuel_state",
)
_TUPLE_FIELDS = ("custom_ev_levers", "eruc_levers")


def as_scenario_key(
    value: "RevenueScenarioComputationKey | tuple[Any, ...] | None",
    **adapter_defaults: Any,
) -> RevenueScenarioComputationKey:
    """Accept either the typed key or a historic tuple; return the typed key.

    The single coercion point for helpers that still receive both shapes, so
    no helper has to know the legacy layout itself.
    """
    if isinstance(value, RevenueScenarioComputationKey):
        return value
    return RevenueScenarioComputationKey.from_legacy_uptake_tuple(value, **adapter_defaults)

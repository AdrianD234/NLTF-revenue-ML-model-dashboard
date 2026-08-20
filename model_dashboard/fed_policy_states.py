"""Canonical registry of the governed 12c/L FED policy timing states.

One frozen spec per state is the single source of truth for calculation-state
IDs, runtime/UI IDs, labels, durations, start dates, schedule columns, path
suffixes, scenario-name suffixes, pair IDs, display order, aliases and notes.
Every other module derives its vocabulary from here, so adding a duration is
one registry row rather than edits in six modules.

The deferral rule generalises the governed six-month scenario exactly:

    before 2027Q1:                          target = planned
    from 2027Q1 up to (excluding) start:    target = no_uplift
    from the deferred start quarter onward: target = planned

Only the initial 12c/L wedge is deferred.  Later planned increases retain
their published dates, so at the selected start date the path catches up to
the published rate; a larger one-quarter increase can occur when catch-up
coincides with another scheduled increase.  That presentation consequence is
deliberate and is documented in :data:`FED_DEFERRAL_CATCH_UP_NOTE`.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

__all__ = [
    "FED_DEFERRAL_CATCH_UP_NOTE",
    "FED_POLICY_SPECS",
    "FED_UPLIFT_START_PERIOD",
    "FedPolicySpec",
    "PolicyStateError",
    "calculation_state_ids",
    "finite_deferral_specs",
    "policy_spec",
    "policy_state_ids",
    "quarter_serial",
    "serial_quarter",
]

FED_UPLIFT_START_PERIOD = "2027Q1"

FED_DEFERRAL_CATCH_UP_NOTE = (
    "Only the initial 12c/L wedge is deferred. Other scheduled increases "
    "retain their published dates. At the selected start date, the path "
    "catches up to the published rate, so a larger one-quarter increase can "
    "occur when catch-up coincides with another scheduled increase."
)


class PolicyStateError(ValueError):
    """An unknown or malformed 12c policy state reached the registry."""


def quarter_serial(period: str) -> int:
    """Total quarter index of a calendar quarter label such as ``2027Q3``."""
    text = str(period or "").strip()
    try:
        year_text, quarter_text = text.split("Q", maxsplit=1)
        year, quarter = int(year_text), int(quarter_text)
    except (TypeError, ValueError) as error:
        raise PolicyStateError(f"{period!r} is not a calendar quarter label") from error
    if not 1 <= quarter <= 4:
        raise PolicyStateError(f"{period!r} is not a calendar quarter label")
    return year * 4 + (quarter - 1)


def serial_quarter(serial: int) -> str:
    """Inverse of :func:`quarter_serial`."""
    year, index = divmod(int(serial), 4)
    return f"{year}Q{index + 1}"


def _start_date_text(start_period: str) -> str:
    year, index = divmod(quarter_serial(start_period), 4)
    month = {0: "1 Jan", 1: "1 Apr", 2: "1 Jul", 3: "1 Oct"}[index]
    return f"{month} {year}"


@dataclass(frozen=True)
class FedPolicySpec:
    """One governed 12c policy timing state.

    ``state_id`` is the runtime/UI identifier (session state, catalogue
    directories, computation keys). ``calculation_state_id`` is the
    calculation-layer identifier used by ``rate_paths`` and the replay
    scenario names. Both are stable text IDs; floating-point years are never
    used for identity.
    """

    state_id: str
    calculation_state_id: str
    label: str
    delay_months: int
    delay_quarters: int
    start_period: str
    display_order: int
    is_published: bool
    is_no_uplift: bool
    note: str

    @property
    def is_finite_deferral(self) -> bool:
        return not self.is_published and not self.is_no_uplift

    @property
    def schedule_column(self) -> str:
        """Column name in the quarterly/annual PED rate schedules."""
        if self.is_published:
            return "planned"
        if self.is_no_uplift:
            return "no_uplift"
        return f"delayed_{self.delay_months}m"

    @property
    def path_suffix(self) -> str:
        """Public scenario-matrix path suffix (``baseline_shifted_6m`` etc.)."""
        if self.is_published:
            return "published"
        if self.is_no_uplift:
            return "no_uplift"
        return f"shifted_{self.delay_months}m"

    @property
    def pair_state_suffix(self) -> str:
        """Fixed-finalist replay pair-id suffix (``baseline_delayed_6m`` etc.)."""
        if self.is_published:
            return "published"
        if self.is_no_uplift:
            return "no_uplift"
        return f"delayed_{self.delay_months}m"

    @property
    def variant_id_suffix(self) -> str:
        """Conflict/base policy-variant scenario-id suffix."""
        if self.is_published:
            raise PolicyStateError("The published state has no policy-variant suffix.")
        if self.is_no_uplift:
            return "12c_no_uplift"
        return f"12c_delay_{self.delay_months}m"

    @property
    def variant_display_name(self) -> str:
        """Reader-facing policy-variant phrase for scenario display names."""
        if self.is_published:
            raise PolicyStateError("The published state has no policy-variant phrase.")
        if self.is_no_uplift:
            return "12c uplift off"
        if self.delay_months == 6:
            return "12c deferred six months"
        return f"12c deferred {self.delay_months} months"

    @property
    def short_policy_phrase(self) -> str:
        """Short phrase used in annual-bridge trace names (``12c delayed 6m``)."""
        if self.is_published:
            raise PolicyStateError("The published state has no policy phrase.")
        if self.is_no_uplift:
            return "12c off"
        return f"12c delayed {self.delay_months}m"

    @property
    def value_status(self) -> str:
        """`value_status` marker written onto policy-touched chart rows."""
        if self.is_published:
            raise PolicyStateError("The published state never touches a chart row.")
        if self.is_no_uplift:
            return "fed_uplift_off"
        return f"fed_uplift_delayed_{self.delay_months}m"

    @property
    def data_scope(self) -> str:
        """`data_scope` marker written onto policy-touched chart rows."""
        if self.is_published:
            raise PolicyStateError("The published state never touches a chart row.")
        if self.is_no_uplift:
            return "fed_uplift_counterfactual"
        # Deliberately duration-free, preserving the six-month production
        # marker byte-for-byte; the duration lives in value_status and
        # _fed_policy.
        return "fed_uplift_delay_counterfactual"

    @property
    def start_date_text(self) -> str:
        if not self.start_period:
            raise PolicyStateError("The no-uplift state has no start date.")
        return _start_date_text(self.start_period)

    def direct_affected_quarters(self) -> tuple[str, ...]:
        """Calendar quarters whose direct rate differs from planned.

        Finite deferrals: ``[2027Q1, start)``. No uplift: unbounded (every
        quarter from 2027Q1), so it is expressed by the caller against the
        governed schedule; this helper raises for it. Published: empty.
        """
        if self.is_published:
            return ()
        if self.is_no_uplift:
            raise PolicyStateError(
                "The no-uplift window is unbounded; derive it from the governed schedule."
            )
        first = quarter_serial(FED_UPLIFT_START_PERIOD)
        last = quarter_serial(self.start_period)
        return tuple(serial_quarter(serial) for serial in range(first, last))


def _deferral_spec(months: int, order: int) -> FedPolicySpec:
    quarters = months // 3
    start = serial_quarter(quarter_serial(FED_UPLIFT_START_PERIOD) + quarters)
    years = months / 12.0
    year_word = "year" if years == 1.0 else "years"
    label = f"Deferred {years:.1f} {year_word} ({months} months) — {_start_date_text(start)}"
    note = (
        f"The initial +12c/L step moves from 1 January 2027 to "
        f"{_start_date_text(start)} ({start}). In calendar quarters "
        f"{FED_UPLIFT_START_PERIOD} up to but excluding {start} the PED "
        "retail-price input carries the no-uplift rate and the same "
        "proportional reduction is applied to Light and Heavy RUC rates and "
        f"real RUC model-price inputs; the published direct rate path resumes "
        f"in {start}. " + FED_DEFERRAL_CATCH_UP_NOTE
    )
    return FedPolicySpec(
        state_id=f"delayed_{months}m",
        calculation_state_id=f"delay_{months}m",
        label=label,
        delay_months=months,
        delay_quarters=quarters,
        start_period=start,
        display_order=order,
        is_published=False,
        is_no_uplift=False,
        note=note,
    )


FED_POLICY_SPECS: tuple[FedPolicySpec, ...] = (
    FedPolicySpec(
        state_id="published",
        calculation_state_id="published",
        label="Original timing — 1 Jan 2027",
        delay_months=0,
        delay_quarters=0,
        start_period=FED_UPLIFT_START_PERIOD,
        display_order=0,
        is_published=True,
        is_no_uplift=False,
        note=(
            "The legislated petrol excise increases (+6c/L in FY2027, +12c/L "
            "from FY2028) baked into the Current planned path apply on their "
            "published dates, beginning 1 January 2027."
        ),
    ),
    *(_deferral_spec(months, order) for order, months in enumerate((6, 12, 18, 24, 30, 36), start=1)),
    FedPolicySpec(
        state_id="off",
        calculation_state_id="no_uplift",
        label="No 12c uplift",
        delay_months=-1,
        delay_quarters=-1,
        start_period="",
        display_order=7,
        is_published=False,
        is_no_uplift=True,
        note=(
            "The 12c uplift is removed entirely: from 2027Q1 onward PED and "
            "all RUC collection rates follow the governed no-uplift schedule, "
            "carried parallel to the planned path beyond the legislated window."
        ),
    ),
)

_SPEC_BY_STATE_ID = MappingProxyType({spec.state_id: spec for spec in FED_POLICY_SPECS})
_SPEC_BY_CALCULATION_ID = MappingProxyType(
    {spec.calculation_state_id: spec for spec in FED_POLICY_SPECS}
)


def _alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for spec in FED_POLICY_SPECS:
        aliases[spec.state_id] = spec.state_id
        aliases[spec.calculation_state_id] = spec.state_id
        if spec.is_finite_deferral:
            aliases[spec.path_suffix] = spec.state_id  # shifted_6m, shifted_12m, ...
            aliases[spec.variant_id_suffix] = spec.state_id  # 12c_delay_6m, ...
    # Historic aliases retained for cache/session/extract compatibility.
    aliases.update(
        {
            "original": "published",
            "planned": "published",
            "published_timing": "published",
            "deferred": "delayed_6m",
            "delay_6m": "delayed_6m",
            "no_uplift": "off",
            "none": "off",
            "12c_off": "off",
            "12c_no_uplift": "off",
        }
    )
    return aliases


_POLICY_STATE_ALIASES = MappingProxyType(_alias_map())


def policy_spec(state: object) -> FedPolicySpec:
    """The spec for any known state ID or alias; raises on anything else.

    Fails closed by contract: defaulting is what turns a typo into a
    silently different published counterfactual.
    """
    if isinstance(state, bool):
        raise PolicyStateError(f"policy state must be text, got bool ({state!r})")
    text = str(state or "").strip().casefold()
    if not text:
        raise PolicyStateError("policy state is required")
    state_id = _POLICY_STATE_ALIASES.get(text)
    if state_id is None:
        raise PolicyStateError(
            f"{state!r} is not a known 12c policy state; expected one of "
            + ", ".join(spec.state_id for spec in FED_POLICY_SPECS)
        )
    return _SPEC_BY_STATE_ID[state_id]


def policy_state_ids() -> tuple[str, ...]:
    """The eight runtime/UI state IDs in display order."""
    return tuple(spec.state_id for spec in FED_POLICY_SPECS)


def calculation_state_ids() -> tuple[str, ...]:
    """The eight calculation-layer state IDs in display order."""
    return tuple(spec.calculation_state_id for spec in FED_POLICY_SPECS)


def finite_deferral_specs() -> tuple[FedPolicySpec, ...]:
    """The six finite deferrals, shortest first."""
    return tuple(spec for spec in FED_POLICY_SPECS if spec.is_finite_deferral)


def _validate_registry() -> None:
    specs = FED_POLICY_SPECS
    if len(specs) != 8:
        raise PolicyStateError(f"Expected exactly 8 policy states, found {len(specs)}.")
    for field in ("state_id", "calculation_state_id", "label", "display_order"):
        values = [getattr(spec, field) for spec in specs]
        if len(set(values)) != len(values):
            raise PolicyStateError(f"Duplicate {field} in the policy-state registry.")
    deferrals = finite_deferral_specs()
    if len(deferrals) != 6:
        raise PolicyStateError(f"Expected exactly 6 finite deferrals, found {len(deferrals)}.")
    if [spec.delay_quarters for spec in deferrals] != [2, 4, 6, 8, 10, 12]:
        raise PolicyStateError("Finite deferral quarters must be exactly 2, 4, 6, 8, 10, 12.")
    starts = [spec.start_period for spec in deferrals]
    if starts != ["2027Q3", "2028Q1", "2028Q3", "2029Q1", "2029Q3", "2030Q1"]:
        raise PolicyStateError(f"Deferred start quarters are wrong: {starts}.")
    if len(set(starts)) != len(starts):
        raise PolicyStateError("Deferred start quarters must be unique.")
    for spec in deferrals:
        window = spec.direct_affected_quarters()
        if len(window) != spec.delay_quarters or window[0] != FED_UPLIFT_START_PERIOD:
            raise PolicyStateError(f"Direct window for {spec.state_id} is malformed: {window}.")


_validate_registry()

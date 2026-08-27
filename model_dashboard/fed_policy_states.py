"""Canonical registry of the governed 12c/L FED policy timing states.

One frozen spec per state is the single source of truth for calculation-state
IDs, runtime/UI IDs, labels, durations, start dates, schedule columns, path
suffixes, scenario-name suffixes, pair IDs, display order, aliases and notes.
Every other module derives its vocabulary from here, so adding a duration is
one registry row rather than edits in six modules.

Two deferral rules coexist, split by duration:

The SIX-MONTH state reproduces the governed six-month scenario exactly -
only the initial 12c/L wedge is deferred:

    before 2027Q1:                          target = planned
    from 2027Q1 up to (excluding) start:    target = no_uplift
    from the deferred start quarter onward: target = planned

Later planned increases retain their published dates, so at 1 Jul 2027 the
path catches up to the published rate.

Every LONGER finite deferral (12-36 months) shifts the ENTIRE legislated
staircase forward by its duration - the initial 12c/L step and every later
scheduled increase move by the same number of calendar quarters:

    before 2027Q1:      target = planned
    from 2027Q1 onward: target = planned shifted by delay_quarters

Because the official staircase keeps rising (+4c/L every calendar year after
2028, with no terminal step), a shifted path never converges back to
published timing: each deferred year leaves the rate 4c/L below original
timing in every later year, and the path can also sit below the no-uplift
counterfactual while a separately scheduled increase is still deferred.
Both rules are documented in :data:`FED_DEFERRAL_CATCH_UP_NOTE`.

A third schedule kind, the BESPOKE STEP PATH, is neither a deferral nor a
shift of the published staircase. It skips the 2027 12c/L uplift entirely
(pricing at the governed no-uplift schedule before its first step) and then
applies its own explicit ex-GST step schedule from a stated start quarter:

    before the first bespoke step: target = no_uplift
    from the first step onward:    target = r0 + cumulative bespoke steps

where ``r0`` is the governed pre-uplift base immediately before the first
step (derived from the schedule, never hard-coded). Bespoke paths carry no
duration semantics: they are excluded from :func:`finite_deferral_specs`
and from duration-ordering and below-published validators (a bespoke path
carries no fixed side of published timing), and their step schedules are
stored explicitly on the spec as :class:`BespokeStepSchedule`.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

__all__ = [
    "BespokeStepSchedule",
    "FED_DEFERRAL_CATCH_UP_NOTE",
    "FED_POLICY_SPECS",
    "FED_UPLIFT_START_PERIOD",
    "FedPolicySpec",
    "PolicyStateError",
    "bespoke_specs",
    "calculation_state_ids",
    "finite_deferral_specs",
    "policy_spec",
    "policy_state_aliases",
    "policy_state_ids",
    "quarter_serial",
    "serial_quarter",
]

FED_UPLIFT_START_PERIOD = "2027Q1"

FED_DEFERRAL_CATCH_UP_NOTE = (
    "The six-month deferral moves only the initial 12c/L wedge: other "
    "scheduled increases retain their published dates and the path catches "
    "up to the published rate at 1 Jul 2027. Every longer deferral shifts "
    "the entire legislated staircase - the initial 12c/L step and every "
    "later scheduled increase move forward by the selected duration. "
    "Because the official staircase adds +4c/L every calendar year with no "
    "terminal step, a shifted path never catches up: each deferred year "
    "leaves the rate 4c/L below original timing in every later year."
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
class BespokeStepSchedule:
    """Explicit ex-GST cents-per-litre step schedule for a bespoke rate path.

    ``initial_steps`` are one-off increments applied at their stated calendar
    quarters, in chronological order. ``recurring_step_nzd_per_litre`` is then
    added at ``recurring_start_period`` and again every
    ``recurring_interval_quarters`` thereafter, indefinitely through the
    governed schedule horizon (there is no terminal step). All amounts are
    incremental NZD/L on top of the governed pre-uplift base ``r0``, which is
    derived from the schedule at build time, never stored here.
    """

    initial_steps: tuple[tuple[str, float], ...]
    recurring_start_period: str
    recurring_interval_quarters: int
    recurring_step_nzd_per_litre: float

    @property
    def first_step_period(self) -> str:
        """The calendar quarter of the first bespoke increment."""
        if self.initial_steps:
            return self.initial_steps[0][0]
        return self.recurring_start_period

    def cumulative_increase(self, period: str) -> float:
        """Total NZD/L above ``r0`` in ``period`` (0.0 before the first step)."""
        serial = quarter_serial(period)
        total = sum(
            step for step_period, step in self.initial_steps
            if quarter_serial(step_period) <= serial
        )
        recurring_serial = quarter_serial(self.recurring_start_period)
        if serial >= recurring_serial:
            occurrences = 1 + (serial - recurring_serial) // self.recurring_interval_quarters
            total += occurrences * self.recurring_step_nzd_per_litre
        return total

    def step_periods(self, horizon_period: str) -> tuple[str, ...]:
        """Every quarter carrying a step, through ``horizon_period`` inclusive."""
        horizon = quarter_serial(horizon_period)
        serials = {
            quarter_serial(step_period)
            for step_period, _ in self.initial_steps
            if quarter_serial(step_period) <= horizon
        }
        recurring_serial = quarter_serial(self.recurring_start_period)
        serials.update(
            range(recurring_serial, horizon + 1, self.recurring_interval_quarters)
        )
        return tuple(serial_quarter(serial) for serial in sorted(serials))


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
    bespoke_schedule: BespokeStepSchedule | None = None

    @property
    def is_bespoke(self) -> bool:
        """Whether the state carries its own explicit step schedule."""
        return self.bespoke_schedule is not None

    @property
    def schedule_kind(self) -> str:
        """Explicit schedule-generation rule identifier for audits and builders."""
        if self.is_published:
            return "published"
        if self.is_no_uplift:
            return "no_uplift"
        if self.is_bespoke:
            return "bespoke_steps"
        return "staircase_shift" if self.delay_months > 6 else "wedge_deferral"

    @property
    def is_finite_deferral(self) -> bool:
        return not self.is_published and not self.is_no_uplift and not self.is_bespoke

    @property
    def is_staircase_shift(self) -> bool:
        """Whether the state shifts the ENTIRE legislated staircase.

        The six-month state keeps the governed catch-up semantics (only the
        initial 12c/L wedge moves); every longer finite deferral moves the
        initial step and every later scheduled increase by its duration.
        """
        return self.is_finite_deferral and self.delay_months > 6

    @property
    def schedule_column(self) -> str:
        """Column name in the quarterly/annual PED rate schedules."""
        if self.is_published:
            return "planned"
        if self.is_no_uplift:
            return "no_uplift"
        if self.is_bespoke:
            return self.state_id
        return f"delayed_{self.delay_months}m"

    @property
    def path_suffix(self) -> str:
        """Public scenario-matrix path suffix (``baseline_shifted_6m`` etc.)."""
        if self.is_published:
            return "published"
        if self.is_no_uplift:
            return "no_uplift"
        if self.is_bespoke:
            return self.state_id
        return f"shifted_{self.delay_months}m"

    @property
    def pair_state_suffix(self) -> str:
        """Fixed-finalist replay pair-id suffix (``baseline_delayed_6m`` etc.)."""
        if self.is_published:
            return "published"
        if self.is_no_uplift:
            return "no_uplift"
        if self.is_bespoke:
            return self.state_id
        return f"delayed_{self.delay_months}m"

    @property
    def variant_id_suffix(self) -> str:
        """Conflict/base policy-variant scenario-id suffix."""
        if self.is_published:
            raise PolicyStateError("The published state has no policy-variant suffix.")
        if self.is_no_uplift:
            return "12c_no_uplift"
        if self.is_bespoke:
            return self.state_id
        return f"12c_delay_{self.delay_months}m"

    @property
    def variant_display_name(self) -> str:
        """Reader-facing policy-variant phrase for scenario display names."""
        if self.is_published:
            raise PolicyStateError("The published state has no policy-variant phrase.")
        if self.is_no_uplift:
            return "12c uplift off"
        if self.is_bespoke:
            return self.label
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
        if self.is_bespoke:
            return self.short_bespoke_phrase
        return f"12c delayed {self.delay_months}m"

    @property
    def short_bespoke_phrase(self) -> str:
        """Compact bespoke phrase (``Option 1 (12c+10c)``), from the label."""
        if not self.is_bespoke:
            raise PolicyStateError(f"{self.state_id!r} is not a bespoke rate path.")
        head = self.label.split("—", maxsplit=1)[0].strip()
        return head or self.state_id

    @property
    def timing_id(self) -> str:
        """Timing identifier used by the public extract (``delayed_6m`` etc.)."""
        if self.is_published:
            return "published"
        if self.is_no_uplift:
            return "no_uplift"
        return self.state_id

    @property
    def timing_label(self) -> str:
        """Reader-facing timing label used by the public extract."""
        if self.is_published:
            return "12c original timing: from 1 Jan 2027"
        if self.is_no_uplift:
            return "12c uplift off"
        if self.is_bespoke:
            return self.label
        if self.delay_months == 6:
            return "12c deferred six months: from 1 Jul 2027"
        return f"12c deferred {self.delay_months} months: from {self.start_date_text}"

    @property
    def value_status(self) -> str:
        """`value_status` marker written onto policy-touched chart rows."""
        if self.is_published:
            raise PolicyStateError("The published state never touches a chart row.")
        if self.is_no_uplift:
            return "fed_uplift_off"
        if self.is_bespoke:
            return f"fed_bespoke_{self.state_id}"
        return f"fed_uplift_delayed_{self.delay_months}m"

    @property
    def data_scope(self) -> str:
        """`data_scope` marker written onto policy-touched chart rows."""
        if self.is_published:
            raise PolicyStateError("The published state never touches a chart row.")
        if self.is_no_uplift:
            return "fed_uplift_counterfactual"
        if self.is_bespoke:
            # Deliberately option-free, mirroring the deferral marker: the
            # option identity lives in value_status and _fed_policy.
            return "fed_bespoke_rate_counterfactual"
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
        """The INITIAL deferral window ``[2027Q1, start)``.

        For the six-month state this is also the complete set of quarters
        whose direct rate differs from planned. For staircase shifts the
        direct-rate difference persists to the schedule horizon (the official
        +4c/L annual step never stops, so the shifted path never converges) -
        that full window depends on the governed schedule, so derive it from
        ``rate_paths.fed_policy_affected_periods``. No uplift: unbounded
        (every quarter from 2027Q1); this helper raises for it.
        Published: empty.
        """
        if self.is_published:
            return ()
        if self.is_no_uplift:
            raise PolicyStateError(
                "The no-uplift window is unbounded; derive it from the governed schedule."
            )
        if self.is_bespoke:
            raise PolicyStateError(
                "A bespoke rate path's direct window depends on where its step "
                "schedule meets the published staircase; derive it from the "
                "governed schedule (rate_paths.fed_policy_affected_periods)."
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
    if months == 6:
        note = (
            f"The initial +12c/L step moves from 1 January 2027 to "
            f"{_start_date_text(start)} ({start}). In calendar quarters "
            f"{FED_UPLIFT_START_PERIOD} up to but excluding {start} the PED "
            "retail-price input carries the no-uplift rate and the same "
            "proportional reduction is applied to Light and Heavy RUC rates and "
            f"real RUC model-price inputs; the published direct rate path resumes "
            f"in {start}. " + FED_DEFERRAL_CATCH_UP_NOTE
        )
    else:
        note = (
            f"The ENTIRE legislated staircase shifts by {months} months: the "
            f"initial +12c/L step moves from 1 January 2027 to "
            f"{_start_date_text(start)} ({start}) and every later scheduled "
            f"increase moves by the same {quarters} calendar quarters, so the "
            "PED retail-price input, the proportional Light and Heavy RUC "
            "rates and real RUC model-price inputs all stay persistently "
            "below original timing - the ongoing +4c/L annual steps shift "
            "too, so the shortfall never closes. "
            + FED_DEFERRAL_CATCH_UP_NOTE
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


def _bespoke_spec(
    state_id: str,
    label: str,
    schedule: BespokeStepSchedule,
    order: int,
    note: str,
) -> FedPolicySpec:
    return FedPolicySpec(
        state_id=state_id,
        calculation_state_id=state_id,
        label=label,
        delay_months=-1,
        delay_quarters=-1,
        start_period=schedule.first_step_period,
        display_order=order,
        is_published=False,
        is_no_uplift=False,
        note=note,
        bespoke_schedule=schedule,
    )


_BESPOKE_TRANSMISSION_NOTE = (
    "Every amount is an incremental EX-GST cents-per-litre increase on the "
    "governed pre-uplift base, derived from the schedule at build time. The "
    "PED retail-price input carries the selected-minus-published wedge and "
    "the same proportional selected/planned signal is applied to Light and "
    "Heavy RUC rates and real RUC model-price inputs; governed coefficients "
    "determine the resulting volume response."
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
        # The wording spells out what the state already implements: no 12c,
        # everything else on schedule (the legislated +6c/L on 1 Jan 2028 and
        # the ongoing +4c/L annual staircase still apply). This label feeds
        # policy_label audit columns inside governed packs, so changing it is
        # a value-changing edit; the previous wording stays an accepted alias.
        label="No 12c uplift — 6c from 1 Jan 2028, then +4c/L annually",
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
    _bespoke_spec(
        "option1_12c_10c_4c",
        "Option 1 — 12c on 1 Jan 2028, 10c on 1 Jan 2029, then +4c annually",
        BespokeStepSchedule(
            initial_steps=(("2028Q1", 0.12), ("2029Q1", 0.10)),
            recurring_start_period="2030Q1",
            recurring_interval_quarters=4,
            recurring_step_nzd_per_litre=0.04,
        ),
        order=8,
        note=(
            "Bespoke rate path: the 2027 12c/L uplift does not occur (the "
            "path prices at the governed no-uplift schedule through calendar "
            "2027), then +12c/L applies on 1 January 2028 and +10c/L on "
            "1 January 2029, followed by +4c/L at every later 1 January "
            "through the governed horizon. From 1 January 2029 the direct "
            "rate equals the published staircase and tracks it thereafter, "
            "so direct rate deltas close at that boundary. "
            + _BESPOKE_TRANSMISSION_NOTE
        ),
    ),
    _bespoke_spec(
        "option2_9c_9c_4c",
        "Option 2 — 9c on 1 Jan 2028, 9c on 1 Jan 2029, then +4c annually",
        BespokeStepSchedule(
            initial_steps=(("2028Q1", 0.09), ("2029Q1", 0.09)),
            recurring_start_period="2030Q1",
            recurring_interval_quarters=4,
            recurring_step_nzd_per_litre=0.04,
        ),
        order=9,
        note=(
            "Bespoke rate path: the 2027 12c/L uplift does not occur (the "
            "path prices at the governed no-uplift schedule through calendar "
            "2027), then +9c/L applies on 1 January 2028 and +9c/L on "
            "1 January 2029, followed by +4c/L at every later 1 January "
            "through the governed horizon. From 1 January 2029 the path "
            "prices exactly like the 12-month full-staircase shift while "
            "sitting 3c/L below that state during calendar 2028. "
            + _BESPOKE_TRANSMISSION_NOTE
        ),
    ),
    _bespoke_spec(
        "option3_4c_semiannual",
        "Option 3 — +4c every six months from 1 Jul 2027 to 1 Jan 2029, then +4c annually",
        BespokeStepSchedule(
            initial_steps=(
                ("2027Q3", 0.04),
                ("2028Q1", 0.04),
                ("2028Q3", 0.04),
                ("2029Q1", 0.04),
            ),
            recurring_start_period="2030Q1",
            recurring_interval_quarters=4,
            recurring_step_nzd_per_litre=0.04,
        ),
        order=10,
        note=(
            "Bespoke rate path: the 2027 12c/L uplift does not occur; "
            "instead a TEMPORARY six-monthly acceleration applies: +4c/L on "
            "1 July 2027, 1 January 2028, 1 July 2028 and 1 January 2029 "
            "(the final six-monthly step - there is deliberately no step on "
            "1 July 2029), then the normal +4c/L at every 1 January resumes "
            "from 1 January 2030 through the governed horizon. Because both "
            "paths then rise by the same annual amount, the path sits a "
            "constant 6c/L below published timing from 2028Q3 onward. "
            + _BESPOKE_TRANSMISSION_NOTE
        ),
    ),
    _bespoke_spec(
        "option4_labour_4c",
        "Option 4 — Labour scenario: 36-month pause, then +4c annually from 1 Jan 2030",
        BespokeStepSchedule(
            initial_steps=(),
            recurring_start_period="2030Q1",
            recurring_interval_quarters=4,
            recurring_step_nzd_per_litre=0.04,
        ),
        order=11,
        note=(
            "Bespoke rate path, a user-defined illustrative scenario rather "
            "than a sourced or officially announced party policy. NOT the "
            "36-month full-staircase deferral: the original +12c/L and "
            "+6c/L increases never land and never catch up. The rate holds "
            "the governed pre-uplift base through 2029Q4, then rises +4c/L "
            "on 1 January 2030 and every later 1 January through the "
            "governed horizon. Published timing reaches r0+26c by 2030Q1 "
            "while this path reaches only r0+4c, and both then add +4c "
            "annually, so the path sits a constant 22c/L below published "
            "timing from 2030Q1 onward. "
            + _BESPOKE_TRANSMISSION_NOTE
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
            # Pre-2026-08 registry label and its interim app-only display
            # override, kept as accepted spellings so any stored label-text
            # selection still resolves instead of falling to the default.
            "no 12c uplift": "off",
            "no 12c uplift — 6c from 1 jan 2028, then +4c/l annually": "off",
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
    """The twelve runtime/UI state IDs in display order."""
    return tuple(spec.state_id for spec in FED_POLICY_SPECS)


def policy_state_aliases() -> dict[str, str]:
    """Every accepted spelling mapped to its runtime/UI state ID."""
    return dict(_POLICY_STATE_ALIASES)


def calculation_state_ids() -> tuple[str, ...]:
    """The twelve calculation-layer state IDs in display order."""
    return tuple(spec.calculation_state_id for spec in FED_POLICY_SPECS)


def finite_deferral_specs() -> tuple[FedPolicySpec, ...]:
    """The six finite deferrals, shortest first (bespoke paths excluded)."""
    return tuple(spec for spec in FED_POLICY_SPECS if spec.is_finite_deferral)


def bespoke_specs() -> tuple[FedPolicySpec, ...]:
    """The four bespoke step-path states, in display order."""
    return tuple(spec for spec in FED_POLICY_SPECS if spec.is_bespoke)


def _validate_registry() -> None:
    specs = FED_POLICY_SPECS
    if len(specs) != 12:
        raise PolicyStateError(f"Expected exactly 12 policy states, found {len(specs)}.")
    for field in ("state_id", "calculation_state_id", "label", "display_order"):
        values = [getattr(spec, field) for spec in specs]
        if len(set(values)) != len(values):
            raise PolicyStateError(f"Duplicate {field} in the policy-state registry.")
    # Derived identity vocabularies must also be collision-free: pair ids,
    # schedule columns and matrix path suffixes each key downstream frames.
    for derived in ("schedule_column", "path_suffix", "pair_state_suffix", "timing_id"):
        values = [getattr(spec, derived) for spec in specs]
        if len(set(values)) != len(values):
            raise PolicyStateError(f"Duplicate derived {derived} in the policy-state registry.")
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
    bespoke = bespoke_specs()
    if len(bespoke) != 4:
        raise PolicyStateError(f"Expected exactly 4 bespoke rate paths, found {len(bespoke)}.")
    for spec in bespoke:
        schedule = spec.bespoke_schedule
        if schedule is None:
            raise PolicyStateError(f"Bespoke state {spec.state_id} has no step schedule.")
        if spec.start_period != schedule.first_step_period:
            raise PolicyStateError(
                f"Bespoke state {spec.state_id} start_period must equal its first step."
            )
        if quarter_serial(schedule.first_step_period) <= quarter_serial(FED_UPLIFT_START_PERIOD):
            raise PolicyStateError(
                f"Bespoke state {spec.state_id} must start after the 12c uplift date."
            )
        step_serials = [quarter_serial(period) for period, _ in schedule.initial_steps]
        if step_serials != sorted(set(step_serials)):
            raise PolicyStateError(
                f"Bespoke state {spec.state_id} initial steps must be strictly chronological."
            )
        if any(step <= 0.0 for _, step in schedule.initial_steps):
            raise PolicyStateError(f"Bespoke state {spec.state_id} steps must be positive.")
        if schedule.recurring_step_nzd_per_litre <= 0.0:
            raise PolicyStateError(f"Bespoke state {spec.state_id} recurring step must be positive.")
        if schedule.recurring_interval_quarters not in (2, 4):
            raise PolicyStateError(
                f"Bespoke state {spec.state_id} recurring interval must be semiannual or annual."
            )
        if step_serials and quarter_serial(schedule.recurring_start_period) <= step_serials[-1]:
            raise PolicyStateError(
                f"Bespoke state {spec.state_id} recurring steps must begin after its initial steps."
            )


_validate_registry()

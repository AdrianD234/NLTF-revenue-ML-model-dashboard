"""Governed Low/Medium/High Middle East conflict fuel-price paths.

The committed CSV is deliberately a policy-free source layer.  It contains
nominal retail pump-price assumptions only; the 12 cent FED path and the
matched RUC policy variants are applied downstream.  Observed 2026 anchors
replace the stale values in the supplied diesel workbook, while its
Medium/High decay shapes remain the auditable source for prospective paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pandas as pd

from .fed_policy_states import FED_POLICY_SPECS


SOURCE_WORKBOOK_NAME = "FF diesel price scenarios (1).xlsx"
SOURCE_WORKBOOK_SHEET = "Diesel Price Forecast"
SOURCE_WORKBOOK_SHA256 = "F7BAE25CF300568954777BB043013D159485E09901BFC210D983E132E31BA6FC"

MBIE_WEEKLY_FUEL_PRICE_URL = (
    "https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/"
    "energy-statistics-and-modelling/energy-statistics/weekly-fuel-price-monitoring"
)
MBIE_VALUE_TABLE_URL = "https://figure.nz/chart/lSYJzICrinllOY7p"
TREASURY_CONFLICT_SCENARIO_URL = (
    "https://www.treasury.govt.nz/sites/default/files/2026-05/"
    "mec-macroecon-scenarios-24-mar-2026.pdf"
)

BASE_DRIFT_CPL_PER_QUARTER = 1.0
PETROL_CONFLICT_PREMIUM_RATIO = 0.60
BASE_DIESEL_2026Q1_CPL = 217.8
OBSERVED_DIESEL_2026Q2_CPL = 326.38
OBSERVED_PETROL_2026Q2_CPL = 325.96
OBSERVED_DIESEL_2026Q3_CPL = 241.9947901918
OBSERVED_PETROL_2026Q3_CPL = 291.3487517497

# The petrol base is solved at the scenario branching point.  With a +1 c/L
# quarterly nominal drift, this makes the 2026Q3 observed petrol premium
# exactly 60% of the observed diesel premium and avoids a hidden level shift
# when the prospective mapping starts in 2026Q4.
BASE_PETROL_2026Q1_CPL = (
    OBSERVED_PETROL_2026Q3_CPL
    - 2 * BASE_DRIFT_CPL_PER_QUARTER
    - PETROL_CONFLICT_PREMIUM_RATIO
    * (
        OBSERVED_DIESEL_2026Q3_CPL
        - (BASE_DIESEL_2026Q1_CPL + 2 * BASE_DRIFT_CPL_PER_QUARTER)
    )
)

EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2026, 2031)
    for quarter in range(1, 5)
)
CONFLICT_SEVERITIES = ("low", "medium", "high")
CONFLICT_SCENARIO_IDS = tuple(f"middle_east_{severity}" for severity in CONFLICT_SEVERITIES)
# Compatibility names used by the replay and UI integration layers.
CONFLICT_FUEL_SCENARIO_LEVELS = CONFLICT_SEVERITIES
CONFLICT_FUEL_PATH_CSV = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "current_revenue_outlook"
    / "conflict_fuel_price_scenarios.csv"
)

REQUIRED_COLUMNS = (
    "period",
    "severity",
    "base_diesel_cpl",
    "scenario_diesel_cpl",
    "diesel_ratio",
    "base_petrol_cpl",
    "scenario_petrol_cpl",
    "petrol_ratio",
    "observation_status",
    "source_note",
    "source_url",
    "source_workbook_cell",
    "source_workbook_sha256",
    "fed_12c_embedded",
)


@dataclass(frozen=True)
class ConflictFuelPathSpec:
    """Stable metadata for a governed conflict severity."""

    severity: str
    scenario_id: str
    display_name: str
    convergence_period: str
    prospective_peak_period: str
    prospective_peak_diesel_cpl: float
    source_workbook_cells: str


SCENARIO_REGISTRY: Mapping[str, ConflictFuelPathSpec] = MappingProxyType(
    {
        # The LOW path is the PUBLIC CENTRAL case: it contains the fuel-price
        # increase that has actually occurred and its short normalisation, so
        # it - not the no-shock technical Base it converges to - is the path
        # presented as "where we are". The scenario_id stays middle_east_low
        # for cache, replay and pack stability; only the reader-facing name
        # carries the role.
        "low": ConflictFuelPathSpec(
            severity="low",
            scenario_id="middle_east_low",
            display_name="Current conditions baseline",
            convergence_period="2027Q1",
            prospective_peak_period="2026Q4",
            prospective_peak_diesel_cpl=231.8973950959,
            source_workbook_cells="Diesel Price Forecast!B5:B7",
        ),
        # MEDIUM is a source-faithful TEMPORARY shock: Treasury's Scenario 2
        # fuel, GDP and unemployment assumptions travel together and recover.
        # It is deliberately NOT the persistent ten-year downside - that risk
        # story has its own scenario (persistent_downside).
        "medium": ConflictFuelPathSpec(
            severity="medium",
            scenario_id="middle_east_medium",
            display_name="Temporary fuel shock (Treasury Medium)",
            convergence_period="2028Q1",
            prospective_peak_period="2026Q4",
            prospective_peak_diesel_cpl=315.0,
            source_workbook_cells="Diesel Price Forecast!C6:C11",
        ),
        "high": ConflictFuelPathSpec(
            severity="high",
            scenario_id="middle_east_high",
            display_name="Middle East conflict: High",
            convergence_period="2030Q4",
            prospective_peak_period="2027Q1",
            prospective_peak_diesel_cpl=385.0,
            source_workbook_cells="Diesel Price Forecast!D6:D22",
        ),
    }
)
CONFLICT_FUEL_SCENARIO_SPECS = SCENARIO_REGISTRY


@dataclass(frozen=True)
class PolicyVariantSpec:
    """Policy overlay that can be paired with any policy-free fuel path."""

    policy_variant: str
    id_suffix: str
    display_name: str


# Derived from the canonical registry: one variant per non-published governed
# state (the six finite deferrals, no-uplift, then the five bespoke rate
# paths), in display order. The six-month and no-uplift entries retain their
# historic ids, suffixes and display names exactly.
POLICY_VARIANT_REGISTRY: Mapping[str, PolicyVariantSpec] = MappingProxyType(
    {
        spec.calculation_state_id: PolicyVariantSpec(
            policy_variant=spec.calculation_state_id,
            id_suffix=spec.variant_id_suffix,
            display_name=spec.variant_display_name,
        )
        for spec in FED_POLICY_SPECS
        if not spec.is_published
    }
)


def _policy_variant_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for spec in FED_POLICY_SPECS:
        if spec.is_published:
            continue
        aliases[spec.calculation_state_id] = spec.calculation_state_id
        aliases[spec.state_id] = spec.calculation_state_id
        aliases[spec.variant_id_suffix] = spec.calculation_state_id
    aliases.update({"off": "no_uplift", "12c_off": "no_uplift"})
    return aliases


_POLICY_VARIANT_ALIASES = MappingProxyType(_policy_variant_aliases())


@dataclass(frozen=True)
class ConflictPolicyVariant:
    """One of the six requested severity-by-policy combinations."""

    severity: str
    fuel_scenario_id: str
    policy_variant: str
    scenario_id: str
    display_name: str


def _normalise_severity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("middle_east_"):
        text = text.removeprefix("middle_east_")
    if text not in SCENARIO_REGISTRY:
        raise KeyError(
            f"Unknown conflict severity {value!r}; expected one of "
            + ", ".join(CONFLICT_SEVERITIES)
        )
    return text


def conflict_scenario_id(severity: Any) -> str:
    """Return the stable scenario ID for a severity or existing scenario ID."""

    return SCENARIO_REGISTRY[_normalise_severity(severity)].scenario_id


def conflict_scenario_display_name(severity: Any) -> str:
    """Return the reader-facing scenario name for a severity or scenario ID."""

    return SCENARIO_REGISTRY[_normalise_severity(severity)].display_name


def conflict_scenario_name(severity: Any) -> str:
    """Compatibility alias for the stable internal scenario ID."""

    return conflict_scenario_id(severity)


def conflict_trace_name(severity: Any) -> str:
    """Compatibility alias for the reader-facing trace label."""

    return conflict_scenario_display_name(severity)


def conflict_scenario_note(severity: Any) -> str:
    """Return a concise governed assumption note for a severity."""

    spec = SCENARIO_REGISTRY[_normalise_severity(severity)]
    if spec.severity == "low":
        shape = (
            "The public central case: it carries the fuel-price increase that "
            "has actually occurred. The observed 2026Q3 premium halves in "
            "2026Q4 and converges to the no-shock technical reference path in "
            "2027Q1; the no-shock Base remains available as a technical and "
            "calibration reference only."
        )
    elif spec.severity == "medium":
        shape = (
            "A temporary Treasury-style shock whose macro assumptions travel "
            "together and recover: the supplied Medium decay shape is rebased "
            "to 315 c/L diesel in 2026Q4 and converges to the nominal Base "
            "path in 2028Q1, with the matching Treasury Scenario 2 GDP and "
            "unemployment paths applied and recovering alongside it."
        )
    else:
        shape = (
            "The supplied High decay shape is rebased to 385 c/L diesel "
            "in 2027Q1 and converges to the nominal Base path in 2030Q4."
        )
    return (
        f"{spec.display_name}. {shape} Petrol uses its own nominal Base path "
        "plus 60% of the prospective diesel conflict premium. The fuel path "
        "contains no 12c FED or matched RUC policy uplift."
    )


def _normalise_policy_variant(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in _POLICY_VARIANT_ALIASES:
        raise KeyError(
            f"Unknown policy variant {value!r}; expected one of "
            + ", ".join(sorted(_POLICY_VARIANT_ALIASES))
        )
    return _POLICY_VARIANT_ALIASES[text]


def conflict_policy_variant(severity: Any, policy_variant: str) -> ConflictPolicyVariant:
    """Build a stable ID/display pair for one fuel path and policy overlay."""

    severity_id = _normalise_severity(severity)
    policy_key = _normalise_policy_variant(policy_variant)
    fuel = SCENARIO_REGISTRY[severity_id]
    policy = POLICY_VARIANT_REGISTRY[policy_key]
    return ConflictPolicyVariant(
        severity=severity_id,
        fuel_scenario_id=fuel.scenario_id,
        policy_variant=policy_key,
        scenario_id=f"{fuel.scenario_id}__{policy.id_suffix}",
        display_name=f"{fuel.display_name} - {policy.display_name}",
    )


def conflict_policy_variant_name(severity: Any, policy_variant: str) -> str:
    """Return the stable scenario ID for a severity/policy combination."""

    return conflict_policy_variant(severity, policy_variant).scenario_id


def all_conflict_policy_variants() -> tuple[ConflictPolicyVariant, ...]:
    """Every Low/Medium/High by non-published-policy combination.

    Registry-driven: three severities crossed with the twelve non-published
    states (six finite deferrals, no-uplift, five bespoke rate paths;
    36 variants).
    """

    return tuple(
        conflict_policy_variant(severity, policy_variant)
        for severity in CONFLICT_SEVERITIES
        for policy_variant in POLICY_VARIANT_REGISTRY
    )


BASE_SCENARIO_ID = "current_basecase"
BASE_POLICY_VARIANT_IDS: Mapping[str, str] = MappingProxyType(
    {
        policy_key: f"{BASE_SCENARIO_ID}_{spec.id_suffix}"
        for policy_key, spec in POLICY_VARIANT_REGISTRY.items()
    }
)


def structural_overlay_scenario_ids() -> frozenset[str]:
    """Scenario IDs whose displayed forecast is the governed structural overlay.

    For these scenarios the fitted point forecast is replaced by
    ``reference x price ratio ^ elasticity x GDP factor``.  Fitted ensemble
    components, model-validation statistics and fitted prediction intervals
    describe the pre-overlay layer and must not be presented as belonging to
    the displayed forecast.  ``BASE_SCENARIO_ID`` is deliberately excluded: it
    is the reference the overlay is built from and is shown unmodified.
    """

    return frozenset(
        {
            *BASE_POLICY_VARIANT_IDS.values(),
            *(conflict_scenario_id(severity) for severity in CONFLICT_SEVERITIES),
            *(variant.scenario_id for variant in all_conflict_policy_variants()),
        }
    )


def _bool_series(series: pd.Series) -> pd.Series:
    parsed = series.map(
        lambda value: value
        if isinstance(value, bool)
        else {"true": True, "false": False}.get(str(value).strip().lower(), pd.NA)
    )
    if parsed.isna().any():
        bad = sorted(series[parsed.isna()].astype(str).unique().tolist())
        raise ValueError("fed_12c_embedded contains non-boolean values: " + ", ".join(bad))
    return parsed.astype(bool)


def _assert_close(
    actual: pd.Series | float,
    expected: pd.Series | float,
    *,
    message: str,
    tolerance: float = 1e-9,
) -> None:
    actual_series = pd.Series(actual, dtype=float).reset_index(drop=True)
    expected_series = pd.Series(expected, dtype=float).reset_index(drop=True)
    if len(expected_series) == 1 and len(actual_series) > 1:
        expected_series = pd.Series([float(expected_series.iloc[0])] * len(actual_series))
    if len(actual_series) != len(expected_series):
        raise ValueError(message)
    if not actual_series.sub(expected_series).abs().le(tolerance).all():
        raise ValueError(message)


def validate_conflict_fuel_paths(frame: pd.DataFrame) -> None:
    """Raise ``ValueError`` when a committed path violates its contract."""

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("Conflict fuel paths are missing columns: " + ", ".join(missing))

    paths = frame.copy()
    paths["period"] = paths["period"].astype(str)
    paths["severity"] = paths["severity"].astype(str).str.lower()
    if set(paths["severity"]) != set(CONFLICT_SEVERITIES):
        raise ValueError("Conflict fuel paths must contain exactly low, medium and high.")
    if paths.duplicated(["severity", "period"]).any():
        raise ValueError("Conflict fuel paths contain duplicate severity-period rows.")

    numeric_columns = (
        "base_diesel_cpl",
        "scenario_diesel_cpl",
        "diesel_ratio",
        "base_petrol_cpl",
        "scenario_petrol_cpl",
        "petrol_ratio",
    )
    for column in numeric_columns:
        paths[column] = pd.to_numeric(paths[column], errors="coerce")
        if paths[column].isna().any():
            raise ValueError(f"Conflict fuel path column {column} must be numeric.")
    if not (paths[list(numeric_columns)] > 0).all().all():
        raise ValueError("All fuel price levels and ratios must be positive.")

    period_order = {period: index for index, period in enumerate(EXPECTED_PERIODS)}
    for severity, group in paths.groupby("severity", sort=False):
        actual_periods = tuple(
            group.assign(_order=group["period"].map(period_order))
            .sort_values("_order", kind="stable")["period"]
            .tolist()
        )
        if actual_periods != EXPECTED_PERIODS:
            raise ValueError(f"{severity} does not contain the exact governed quarter range.")

    if _bool_series(paths["fed_12c_embedded"]).any():
        raise ValueError("Conflict fuel paths must not embed the 12c FED policy uplift.")
    if "policy_uplift_cpl" in paths:
        _assert_close(
            pd.to_numeric(paths["policy_uplift_cpl"], errors="coerce"),
            0.0,
            message="Conflict fuel paths must keep policy_uplift_cpl at zero.",
        )

    if not paths["source_workbook_sha256"].astype(str).str.upper().eq(
        SOURCE_WORKBOOK_SHA256
    ).all():
        raise ValueError("Conflict fuel path workbook hash does not match the governed source.")
    for column in ("source_note", "source_url", "source_workbook_cell"):
        if paths[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(f"Conflict fuel path lineage column {column} must be populated.")

    # The policy-free base path is common to all severities and drifts exactly
    # +1 c/L each quarter.
    for column, start in (
        ("base_diesel_cpl", BASE_DIESEL_2026Q1_CPL),
        ("base_petrol_cpl", BASE_PETROL_2026Q1_CPL),
    ):
        for period, index in period_order.items():
            expected = start + index * BASE_DRIFT_CPL_PER_QUARTER
            _assert_close(
                paths.loc[paths["period"].eq(period), column],
                expected,
                message=f"{column} does not follow the +1 c/L quarterly base path.",
            )

    _assert_close(
        paths["diesel_ratio"],
        paths["scenario_diesel_cpl"] / paths["base_diesel_cpl"],
        message="diesel_ratio does not reconcile to scenario/base.",
    )
    _assert_close(
        paths["petrol_ratio"],
        paths["scenario_petrol_cpl"] / paths["base_petrol_cpl"],
        message="petrol_ratio does not reconcile to scenario/base.",
    )

    observed = {
        "2026Q2": (OBSERVED_DIESEL_2026Q2_CPL, OBSERVED_PETROL_2026Q2_CPL),
        "2026Q3": (OBSERVED_DIESEL_2026Q3_CPL, OBSERVED_PETROL_2026Q3_CPL),
    }
    for period, (diesel, petrol) in observed.items():
        rows = paths[paths["period"].eq(period)]
        _assert_close(
            rows["scenario_diesel_cpl"],
            diesel,
            message=f"The governed diesel anchor for {period} changed.",
        )
        if petrol is not None:
            _assert_close(
                rows["scenario_petrol_cpl"],
                petrol,
                message=f"The governed petrol anchor for {period} changed.",
            )
        if not rows["observation_status"].astype(str).str.lower().eq("observed").all():
            raise ValueError(f"{period} must be marked observed.")
    q1 = paths[paths["period"].eq("2026Q1")]
    _assert_close(
        q1["scenario_diesel_cpl"],
        BASE_DIESEL_2026Q1_CPL,
        message="The governed 2026Q1 diesel workbook anchor changed.",
    )
    if not q1["observation_status"].astype(str).str.lower().eq("mixed").all():
        raise ValueError(
            "2026Q1 must be marked mixed because diesel is workbook-sourced "
            "while petrol is a Q3-calibrated derived base."
        )
    assumed = paths[paths["period"].map(period_order).ge(period_order["2026Q4"])]
    if not assumed["observation_status"].astype(str).str.lower().eq("assumption").all():
        raise ValueError("Prospective conflict fuel rows must be marked assumption.")

    # From the first prospective quarter, petrol receives 60% of the diesel
    # conflict premium.  The Q2/Q3 values remain exact observed overrides.
    expected_petrol = assumed["base_petrol_cpl"] + PETROL_CONFLICT_PREMIUM_RATIO * (
        assumed["scenario_diesel_cpl"] - assumed["base_diesel_cpl"]
    )
    _assert_close(
        assumed["scenario_petrol_cpl"],
        expected_petrol,
        message="Prospective petrol paths must carry 60% of the diesel conflict premium.",
    )

    # Ordering begins after the common observed history.
    for period in EXPECTED_PERIODS[3:]:
        rows = paths[paths["period"].eq(period)].set_index("severity")
        for column in ("scenario_diesel_cpl", "scenario_petrol_cpl"):
            values = rows.loc[list(CONFLICT_SEVERITIES), column].tolist()
            if not (values[0] <= values[1] <= values[2]):
                raise ValueError(f"{column} is not Low <= Medium <= High in {period}.")

    for severity, spec in SCENARIO_REGISTRY.items():
        rows = paths[paths["severity"].eq(severity)].copy()
        rows["_order"] = rows["period"].map(period_order)
        convergence_order = period_order[spec.convergence_period]
        converged = rows[rows["_order"].ge(convergence_order)]
        _assert_close(
            converged["scenario_diesel_cpl"],
            converged["base_diesel_cpl"],
            message=f"{severity} diesel does not converge by {spec.convergence_period}.",
        )
        _assert_close(
            converged["scenario_petrol_cpl"],
            converged["base_petrol_cpl"],
            message=f"{severity} petrol does not converge by {spec.convergence_period}.",
        )
        peak = rows[rows["period"].eq(spec.prospective_peak_period)]
        _assert_close(
            peak["scenario_diesel_cpl"],
            spec.prospective_peak_diesel_cpl,
            message=f"{severity} prospective diesel peak changed.",
        )
        prospective = rows[rows["_order"].ge(period_order["2026Q4"])].copy()
        prospective["_premium"] = (
            prospective["scenario_diesel_cpl"] - prospective["base_diesel_cpl"]
        )
        peak_premium = float(
            peak["scenario_diesel_cpl"].iloc[0] - peak["base_diesel_cpl"].iloc[0]
        )
        if float(prospective["_premium"].max()) > peak_premium + 1e-9:
            raise ValueError(f"{severity} exceeds its governed prospective premium peak.")


def load_conflict_fuel_paths(path: str | Path | None = None) -> pd.DataFrame:
    """Load, validate and deterministically order the committed scenario paths."""

    source = Path(path) if path is not None else CONFLICT_FUEL_PATH_CSV
    frame = pd.read_csv(source)
    validate_conflict_fuel_paths(frame)
    period_order = {period: index for index, period in enumerate(EXPECTED_PERIODS)}
    severity_order = {severity: index for index, severity in enumerate(CONFLICT_SEVERITIES)}
    ordered = frame.assign(
        _severity_order=frame["severity"].astype(str).str.lower().map(severity_order),
        _period_order=frame["period"].astype(str).map(period_order),
    ).sort_values(["_severity_order", "_period_order"], kind="stable")
    return ordered.drop(columns=["_severity_order", "_period_order"]).reset_index(drop=True)


def load_conflict_fuel_price_scenarios(path: str | Path | None = None) -> pd.DataFrame:
    """Descriptive alias retained for dashboard integration call sites."""

    return load_conflict_fuel_paths(path)


def load_conflict_fuel_price_paths(
    repo_root: str | Path | None = None,
) -> pd.DataFrame:
    """Load paths relative to a repository root for replay compatibility."""

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    source = (
        root
        if root.suffix.lower() == ".csv"
        else root
        / "data"
        / "current_revenue_outlook"
        / "conflict_fuel_price_scenarios.csv"
    )
    return load_conflict_fuel_paths(source)

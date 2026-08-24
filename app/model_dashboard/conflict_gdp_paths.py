"""One-way Middle East fuel-shock transmission into real GDP assumptions.

The fuel paths remain the exogenous scenario driver.  A transparent two-quarter
operating-cost stress index is calibrated to the Treasury's published real-GDP
level gaps for its moderate and severe conflict scenarios.  The resulting GDP
factor is applied upstream of the fixed-finalist replay; ordinary GDP changes
never alter petrol, diesel or RUC price inputs.

The Treasury anchors are not treated as fitted elasticities.  They calibrate a
bounded scenario overlay for the three governed conflict paths.  The model's
own GDP coefficients and interactions determine the downstream activity
response when the adjusted inputs are replayed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .conflict_fuel_paths import (
    CONFLICT_FUEL_SCENARIO_LEVELS,
    EXPECTED_PERIODS,
    load_conflict_fuel_price_paths,
)


TREASURY_CONFLICT_GDP_URL = (
    "https://www.treasury.govt.nz/sites/default/files/2026-05/"
    "mec-macroecon-scenarios-24-mar-2026.pdf"
)
CONFLICT_GDP_CALIBRATION_CSV = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "current_revenue_outlook"
    / "conflict_gdp_calibration.csv"
)

# The macro stress index gives domestic petrol the larger weight, while still
# retaining diesel's wider freight and production-cost channel.  A 60:40
# current/lag blend represents the short transmission delay described in the
# Treasury scenario note.  Both assumptions are explicit and tested.
PETROL_PREMIUM_WEIGHT = 0.75
DIESEL_PREMIUM_WEIGHT = 0.25
CURRENT_QUARTER_WEIGHT = 0.60
LAGGED_QUARTER_WEIGHT = 0.40

_GDP_FIELD_BY_STREAM = {
    "PED": "real_gdp_per_capita_nzd",
    "LIGHT_RUC": "real_gdp_sa_nzd",
    "HEAVY_RUC": "real_gdp_sa_nzd",
}
_CALIBRATION_REQUIRED_COLUMNS = (
    "severity",
    "anchor_period",
    "official_real_gdp_level_impact_pct",
    "treasury_scenario",
    "source_document",
    "source_locator",
    "source_url",
    "calibration_status",
)


def load_conflict_gdp_calibration(
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Load and fail-closed validate the two official Treasury anchors."""

    root = (
        Path(repo_root)
        if repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    path = (
        root
        / "data"
        / "current_revenue_outlook"
        / CONFLICT_GDP_CALIBRATION_CSV.name
    )
    if not path.exists():
        raise FileNotFoundError(f"Conflict GDP calibration is missing: {path}")
    frame = pd.read_csv(path)
    missing = set(_CALIBRATION_REQUIRED_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(
            "Conflict GDP calibration is missing columns: "
            + ", ".join(sorted(missing))
        )
    selected = frame.copy()
    selected["severity"] = (
        selected["severity"].fillna("").astype(str).str.strip().str.casefold()
    )
    if set(selected["severity"]) != {"medium", "high"} or len(selected) != 2:
        raise ValueError(
            "Conflict GDP calibration must contain exactly one medium and one high anchor."
        )
    if selected["severity"].duplicated(keep=False).any():
        raise ValueError("Conflict GDP calibration contains duplicate severities.")
    if not selected["anchor_period"].astype(str).eq("2027Q1").all():
        raise ValueError("Conflict GDP anchors must be calibrated at 2027Q1.")
    selected["official_real_gdp_level_impact_pct"] = pd.to_numeric(
        selected["official_real_gdp_level_impact_pct"], errors="coerce"
    )
    expected = {"medium": -1.5, "high": -3.1}
    observed = selected.set_index("severity")[
        "official_real_gdp_level_impact_pct"
    ].to_dict()
    if any(
        key not in observed
        or not np.isclose(float(observed[key]), value, rtol=0.0, atol=1e-12)
        for key, value in expected.items()
    ):
        raise ValueError(
            "Conflict GDP anchors no longer match the Treasury -1.5%/-3.1% level gaps."
        )
    if not selected["source_url"].astype(str).eq(
        TREASURY_CONFLICT_GDP_URL
    ).all():
        raise ValueError("Conflict GDP calibration source URL is not the governed Treasury note.")
    for column in (
        "treasury_scenario",
        "source_document",
        "source_locator",
        "calibration_status",
    ):
        if selected[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(
                f"Conflict GDP calibration lineage column {column!r} must be populated."
            )
    return selected.sort_values("severity", kind="stable").reset_index(drop=True)


def _calibration_coefficients(
    paths: pd.DataFrame,
    calibration: pd.DataFrame,
) -> tuple[float, float]:
    """Solve loss = linear*x + quadratic*x^2 at the two official anchors."""

    anchor_period = "2027Q1"
    anchors = paths[paths["period"].astype(str).eq(anchor_period)].set_index(
        "severity"
    )
    calibration_by_severity = calibration.set_index("severity")
    x_medium = float(anchors.at["medium", "two_quarter_stress_index"])
    x_high = float(anchors.at["high", "two_quarter_stress_index"])
    matrix = np.array(
        [[x_medium, x_medium**2], [x_high, x_high**2]], dtype=float
    )
    targets = np.array(
        [
            -float(
                calibration_by_severity.at[
                    "medium", "official_real_gdp_level_impact_pct"
                ]
            )
            / 100.0,
            -float(
                calibration_by_severity.at[
                    "high", "official_real_gdp_level_impact_pct"
                ]
            )
            / 100.0,
        ],
        dtype=float,
    )
    if (
        not np.isfinite(matrix).all()
        or not np.isfinite(targets).all()
        or abs(float(np.linalg.det(matrix))) <= 1e-12
    ):
        raise ValueError("Conflict GDP calibration anchors do not identify a stable curve.")
    linear, quadratic = np.linalg.solve(matrix, targets)
    if linear < 0.0 or quadratic < 0.0:
        raise ValueError("Conflict GDP calibration produced a non-monotonic loss curve.")
    return float(linear), float(quadratic)


def build_conflict_gdp_paths(
    repo_root: Path | str | None = None,
    *,
    fuel_paths: pd.DataFrame | None = None,
    calibration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Derive quarterly GDP level factors from the governed fuel-price paths."""

    root = (
        Path(repo_root)
        if repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    paths = (
        load_conflict_fuel_price_paths(root)
        if fuel_paths is None
        else fuel_paths.copy()
    )
    anchors = (
        load_conflict_gdp_calibration(root)
        if calibration is None
        else calibration.copy()
    )
    required = {"severity", "period", "petrol_ratio", "diesel_ratio"}
    missing = required.difference(paths.columns)
    if missing:
        raise ValueError(
            "Conflict fuel paths cannot drive GDP without columns: "
            + ", ".join(sorted(missing))
        )
    out = paths[["severity", "period", "petrol_ratio", "diesel_ratio"]].copy()
    out["severity"] = (
        out["severity"].fillna("").astype(str).str.strip().str.casefold()
    )
    out["period"] = out["period"].astype(str)
    for column in ("petrol_ratio", "diesel_ratio"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
        if (
            out[column].isna().any()
            or (~np.isfinite(out[column])).any()
            or out[column].le(0.0).any()
        ):
            raise ValueError(
                f"Conflict GDP transmission requires positive finite {column} values."
            )
    if set(out["severity"]) != set(CONFLICT_FUEL_SCENARIO_LEVELS):
        raise ValueError("Conflict GDP paths require low, medium and high fuel severities.")
    if out.duplicated(["severity", "period"], keep=False).any():
        raise ValueError("Conflict GDP paths contain duplicate severity-period rows.")
    order = {period: position for position, period in enumerate(EXPECTED_PERIODS)}
    frames: list[pd.DataFrame] = []
    for severity in CONFLICT_FUEL_SCENARIO_LEVELS:
        group = out[out["severity"].eq(severity)].copy()
        group["_order"] = group["period"].map(order)
        group = group.sort_values("_order", kind="stable")
        if tuple(group["period"]) != tuple(EXPECTED_PERIODS):
            raise ValueError(
                f"Conflict GDP severity {severity!r} does not have the exact governed quarters."
            )
        group["weighted_current_fuel_premium"] = np.maximum(
            PETROL_PREMIUM_WEIGHT * (group["petrol_ratio"] - 1.0)
            + DIESEL_PREMIUM_WEIGHT * (group["diesel_ratio"] - 1.0),
            0.0,
        )
        group["weighted_lagged_fuel_premium"] = (
            group["weighted_current_fuel_premium"].shift(1).fillna(0.0)
        )
        group["two_quarter_stress_index"] = (
            CURRENT_QUARTER_WEIGHT * group["weighted_current_fuel_premium"]
            + LAGGED_QUARTER_WEIGHT * group["weighted_lagged_fuel_premium"]
        )
        frames.append(group.drop(columns=["_order"]))
    out = pd.concat(frames, ignore_index=True, sort=False)
    linear, quadratic = _calibration_coefficients(out, anchors)
    stress = pd.to_numeric(out["two_quarter_stress_index"], errors="coerce")
    out["real_gdp_level_loss"] = linear * stress + quadratic * stress.pow(2)
    out["real_gdp_level_factor"] = 1.0 - out["real_gdp_level_loss"]
    out["real_gdp_level_impact_pct"] = -100.0 * out["real_gdp_level_loss"]
    out["calibration_linear_coefficient"] = linear
    out["calibration_quadratic_coefficient"] = quadratic
    out["calibration_basis"] = (
        "one_way_fuel_to_gdp; 75pct_petrol_25pct_diesel_premium; "
        "60pct_current_40pct_lag; quadratic_curve_through_Treasury_"
        "Scenario2_-1.5pct_and_Scenario3_-3.1pct_at_2027Q1"
    )
    out["source_url"] = TREASURY_CONFLICT_GDP_URL
    out["source_status"] = np.where(
        out["severity"].isin(["medium", "high"])
        & out["period"].eq("2027Q1"),
        "official_anchor",
        "derived_from_governed_fuel_path",
    )
    out["reverse_fuel_feedback_applied"] = False
    validate_conflict_gdp_paths(out, calibration=anchors)
    return out.sort_values(
        ["severity", "period"],
        key=lambda values: values.map(order)
        if values.name == "period"
        else values.map(
            {severity: index for index, severity in enumerate(CONFLICT_FUEL_SCENARIO_LEVELS)}
        ),
        kind="stable",
    ).reset_index(drop=True)


def validate_conflict_gdp_paths(
    frame: pd.DataFrame,
    *,
    calibration: pd.DataFrame | None = None,
) -> None:
    """Validate factor identity, official anchors, ordering and recovery."""

    required = {
        "severity",
        "period",
        "two_quarter_stress_index",
        "real_gdp_level_loss",
        "real_gdp_level_factor",
        "real_gdp_level_impact_pct",
        "source_url",
        "source_status",
        "reverse_fuel_feedback_applied",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Conflict GDP paths are missing columns: " + ", ".join(sorted(missing))
        )
    out = frame.copy()
    for column in (
        "two_quarter_stress_index",
        "real_gdp_level_loss",
        "real_gdp_level_factor",
        "real_gdp_level_impact_pct",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce")
        if out[column].isna().any() or (~np.isfinite(out[column])).any():
            raise ValueError(f"Conflict GDP path column {column!r} must be finite.")
    if out["real_gdp_level_factor"].le(0.0).any() or out[
        "real_gdp_level_factor"
    ].gt(1.0 + 1e-12).any():
        raise ValueError("Conflict GDP level factors must be in (0, 1].")
    if not np.allclose(
        out["real_gdp_level_factor"],
        1.0 - out["real_gdp_level_loss"],
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("Conflict GDP factor/loss identity failed.")
    if not np.allclose(
        out["real_gdp_level_impact_pct"],
        -100.0 * out["real_gdp_level_loss"],
        rtol=0.0,
        atol=1e-10,
    ):
        raise ValueError("Conflict GDP factor/percentage identity failed.")
    anchors = (
        load_conflict_gdp_calibration()
        if calibration is None
        else calibration.copy()
    )
    expected = anchors.set_index("severity")[
        "official_real_gdp_level_impact_pct"
    ]
    actual = out[out["period"].eq("2027Q1")].set_index("severity")[
        "real_gdp_level_impact_pct"
    ]
    for severity in ("medium", "high"):
        if severity not in actual or not np.isclose(
            float(actual[severity]), float(expected[severity]), rtol=0.0, atol=1e-10
        ):
            raise ValueError(
                f"Conflict GDP {severity} path no longer meets its Treasury anchor."
            )
        severity_rows = out[out["severity"].astype(str).eq(severity)]
        largest_loss_period = str(
            severity_rows.loc[
                severity_rows["real_gdp_level_loss"].idxmax(), "period"
            ]
        )
        if largest_loss_period != "2027Q1":
            raise ValueError(
                f"Conflict GDP {severity} path must have its largest loss at 2027Q1."
            )
    pivot = out.pivot(index="period", columns="severity", values="real_gdp_level_factor")
    if ((pivot["high"] - pivot["medium"]) > 1e-12).any() or (
        (pivot["medium"] - pivot["low"]) > 1e-12
    ).any():
        raise ValueError("Conflict GDP factors violate high <= medium <= low ordering.")
    for severity, recovery_period in (
        ("low", "2027Q2"),
        ("medium", "2028Q2"),
        ("high", None),
    ):
        if recovery_period is None:
            continue
        recovered = out[
            out["severity"].eq(severity) & out["period"].eq(recovery_period)
        ]["real_gdp_level_factor"]
        if len(recovered) != 1 or not np.isclose(
            float(recovered.iloc[0]), 1.0, rtol=0.0, atol=1e-12
        ):
            raise ValueError(
                f"Conflict GDP {severity} path does not recover by {recovery_period}."
            )
    reverse = out["reverse_fuel_feedback_applied"].map(
        lambda value: value
        if isinstance(value, (bool, np.bool_))
        else str(value).strip().casefold() in {"true", "1", "yes"}
    )
    if reverse.any():
        raise ValueError("Conflict GDP paths must not apply reverse GDP-to-fuel feedback.")
    if not out["source_url"].astype(str).eq(TREASURY_CONFLICT_GDP_URL).all():
        raise ValueError("Conflict GDP path source URL is not the Treasury scenario note.")


def apply_conflict_gdp_impact(
    scenario_inputs: pd.DataFrame,
    *,
    severity: str,
    repo_root: Path | str | None = None,
    gdp_paths: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Apply one conflict GDP factor to raw scenario-input level fields only."""

    normalised = str(severity).strip().casefold()
    if normalised not in CONFLICT_FUEL_SCENARIO_LEVELS:
        raise ValueError(
            f"Unknown conflict GDP severity {severity!r}; expected "
            + ", ".join(CONFLICT_FUEL_SCENARIO_LEVELS)
            + "."
        )
    required = {"stream", "canonical_period"}
    missing = required.difference(scenario_inputs.columns)
    if missing:
        raise ValueError(
            "Scenario inputs cannot receive a conflict GDP path without columns: "
            + ", ".join(sorted(missing))
        )
    paths = (
        build_conflict_gdp_paths(repo_root)
        if gdp_paths is None
        else gdp_paths.copy()
    )
    validate_conflict_gdp_paths(paths)
    selected = paths[paths["severity"].astype(str).eq(normalised)].copy()
    if selected.empty:
        raise ValueError(f"Conflict GDP paths have no {normalised!r} rows.")
    factor_by_period = selected.set_index("period")[
        "real_gdp_level_factor"
    ].to_dict()
    impact_by_period = selected.set_index("period")[
        "real_gdp_level_impact_pct"
    ].to_dict()
    stress_by_period = selected.set_index("period")[
        "two_quarter_stress_index"
    ].to_dict()

    out = scenario_inputs.copy()
    period = out["canonical_period"].astype(str)
    stream = out["stream"].astype(str)
    out["conflict_gdp_level_factor"] = period.map(factor_by_period).fillna(1.0)
    out["conflict_gdp_level_impact_pct"] = period.map(impact_by_period).fillna(0.0)
    out["conflict_gdp_stress_index"] = period.map(stress_by_period).fillna(0.0)
    out["conflict_gdp_transmission_basis"] = (
        "Treasury-calibrated one-way fuel-to-GDP level overlay"
    )
    out["conflict_gdp_source_url"] = TREASURY_CONFLICT_GDP_URL
    out["conflict_gdp_reverse_fuel_feedback_applied"] = False
    for stream_name, field in _GDP_FIELD_BY_STREAM.items():
        if field not in out.columns:
            raise ValueError(
                f"Scenario inputs are missing required GDP field {field!r}."
            )
        mask = stream.eq(stream_name)
        values = pd.to_numeric(out.loc[mask, field], errors="coerce")
        factors = pd.to_numeric(
            out.loc[mask, "conflict_gdp_level_factor"], errors="coerce"
        )
        if (
            values.isna().any()
            or factors.isna().any()
            or values.le(0.0).any()
            or factors.le(0.0).any()
        ):
            raise ValueError(
                f"Conflict GDP impact requires positive {field} values and factors."
            )
        adjusted = values.to_numpy(dtype=float) * factors.to_numpy(dtype=float)
        if pd.api.types.is_string_dtype(out[field].dtype):
            out.loc[mask, field] = [
                format(float(value), ".17g") for value in adjusted
            ]
        else:
            out.loc[mask, field] = adjusted
    return out.reset_index(drop=True)


def conflict_gdp_input_audit(
    scenario_inputs: pd.DataFrame,
) -> pd.DataFrame:
    """Return one scenario/stream/quarter audit row for applied GDP factors."""

    # Ordered, not a set: ``list(some_set)`` of strings varies with
    # PYTHONHASHSEED, so a set here gave this audit frame a different column
    # ORDER in every process. The values were always identical, but a frame
    # whose schema is unstable across runs cannot be committed, diffed or
    # replay-compared.
    required = (
        "scenario_name",
        "stream",
        "canonical_period",
        "conflict_gdp_level_factor",
        "conflict_gdp_level_impact_pct",
        "conflict_gdp_stress_index",
        "conflict_gdp_transmission_basis",
        "conflict_gdp_source_url",
        "conflict_gdp_reverse_fuel_feedback_applied",
    )
    missing = set(required).difference(scenario_inputs.columns)
    if missing:
        return pd.DataFrame()
    out = scenario_inputs[list(required)].copy()
    out = out.rename(columns={"canonical_period": "period"})
    out["conflict_gdp_level_factor"] = pd.to_numeric(
        out["conflict_gdp_level_factor"], errors="coerce"
    )
    out["conflict_gdp_level_impact_pct"] = pd.to_numeric(
        out["conflict_gdp_level_impact_pct"], errors="coerce"
    )
    out["conflict_gdp_stress_index"] = pd.to_numeric(
        out["conflict_gdp_stress_index"], errors="coerce"
    )
    return out.sort_values(
        ["scenario_name", "stream", "period"], kind="stable"
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Conflict unemployment channel
#
# The Treasury note's Annex 1 summary table publishes annual (June-quarter)
# unemployment rates for the base case and each conflict scenario.  Scenario 2
# (medium) and Scenario 3 (high) are official anchors; Scenario 1 (low) shows
# no material unemployment response and carries no anchor here.  The gaps are
# applied additively to the raw ``unemployment_rate`` scenario-input field
# (stored as a fraction, so a +0.8pp gap adds 0.008); the fixed-finalist
# replay recomputes ``log_unemployment_rate`` and every unemp__* feature from
# that raw field, so no derived column is ever adjusted directly.
# ---------------------------------------------------------------------------

CONFLICT_UNEMPLOYMENT_CALIBRATION_CSV = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "current_revenue_outlook"
    / "conflict_unemployment_calibration.csv"
)

_UNEMPLOYMENT_CALIBRATION_REQUIRED_COLUMNS = (
    "severity",
    "calendar_year",
    "official_unemployment_rate_pct",
    "base_unemployment_rate_pct",
    "unemployment_gap_pp",
    "treasury_scenario",
    "source_document",
    "source_locator",
    "source_url",
    "calibration_status",
)
_UNEMPLOYMENT_ANCHOR_YEARS = (2026, 2027, 2028)
# Treasury Annex 1 summary table (p.7): unemployment rate, % June quarter.
# Base 5.3/4.7/4.4; Scenario 2 5.4/5.5/4.7; Scenario 3 5.7/6.6/5.4.
_UNEMPLOYMENT_GAP_PP_BY_SEVERITY_YEAR = {
    "medium": {2026: 0.1, 2027: 0.8, 2028: 0.3},
    "high": {2026: 0.4, 2027: 1.9, 2028: 1.0},
}
_UNEMPLOYMENT_GAP_SANITY_BOUND_PP = 3.0
# The Treasury unemployment rates are June-QUARTER point values, so the
# natural anchor quarter for calendar year Y is YQ2.  Quarters at or before
# 2026Q3 are observed common history shared by every severity (the same rule
# the governed fuel paths follow): severity-specific divergence may only
# begin at the first prospective quarter, 2026Q4.  The 2026Q2 anchor
# therefore falls inside observed history; it is recorded in the path frame
# for lineage (``treasury_anchor_gap_pp``) and as the linear-interpolation
# origin, but it is never applied as an adjustment.
_UNEMPLOYMENT_OBSERVED_HISTORY_LAST_PERIOD = "2026Q3"
_UNEMPLOYMENT_ANCHOR_QUARTER = 2
_UNEMPLOYMENT_HOLD_QUARTERS = {"medium": 0, "high": 4}
_UNEMPLOYMENT_TAPER_QUARTERS = 4
_UNEMPLOYMENT_DERIVATION_BASIS = {
    "low": (
        "no_treasury_unemployment_anchor; zero_gap_all_quarters "
        "(Scenario 1 shows no material unemployment response)"
    ),
    "medium": (
        "Treasury_Scenario2_June_quarter_anchors_2026Q2_2027Q2_2028Q2; "
        "observed_common_history_zero_through_2026Q3_with_2026Q2_anchor_"
        "recorded_not_applied; linear_interpolation_between_anchors_from_"
        "2026Q4; linear_taper_to_zero_2028Q3_to_2029Q2"
    ),
    "high": (
        "Treasury_Scenario3_June_quarter_anchors_2026Q2_2027Q2_2028Q2; "
        "observed_common_history_zero_through_2026Q3_with_2026Q2_anchor_"
        "recorded_not_applied; linear_interpolation_between_anchors_from_"
        "2026Q4; hold_2028Q2_gap_through_2029Q2_as_high_GDP_path_has_no_"
        "recovery_in_window; linear_taper_to_zero_2029Q3_to_2030Q2"
    ),
}
_UNEMPLOYMENT_NO_ANCHOR_BASIS = (
    "no_treasury_unemployment_anchor; zero_gap_all_quarters"
)
# Streams whose finalist templates carry the raw ``unemployment_rate`` user
# field (see ``forecast_runner.STREAM_COLUMNS``).  LIGHT_RUC has no
# unemployment input, so its rows are left byte-identical.
_UNEMPLOYMENT_RATE_STREAMS = ("PED", "HEAVY_RUC")


def load_conflict_unemployment_calibration(
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Load and fail-closed validate the Treasury unemployment anchors."""

    root = (
        Path(repo_root)
        if repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    path = (
        root
        / "data"
        / "current_revenue_outlook"
        / CONFLICT_UNEMPLOYMENT_CALIBRATION_CSV.name
    )
    if not path.exists():
        raise FileNotFoundError(
            f"Conflict unemployment calibration is missing: {path}"
        )
    frame = pd.read_csv(path)
    missing = set(_UNEMPLOYMENT_CALIBRATION_REQUIRED_COLUMNS).difference(
        frame.columns
    )
    if missing:
        raise ValueError(
            "Conflict unemployment calibration is missing columns: "
            + ", ".join(sorted(missing))
        )
    selected = frame.copy()
    selected["severity"] = (
        selected["severity"].fillna("").astype(str).str.strip().str.casefold()
    )
    allowed = set(_UNEMPLOYMENT_GAP_PP_BY_SEVERITY_YEAR)
    observed_severities = set(selected["severity"])
    if not observed_severities.issubset(allowed):
        raise ValueError(
            "Conflict unemployment calibration contains unknown severities: "
            + ", ".join(sorted(observed_severities.difference(allowed)))
        )
    if "medium" not in observed_severities:
        raise ValueError(
            "Conflict unemployment calibration must contain the medium "
            "(Scenario 2) anchors."
        )
    selected["calendar_year"] = pd.to_numeric(
        selected["calendar_year"], errors="coerce"
    )
    if selected["calendar_year"].isna().any():
        raise ValueError(
            "Conflict unemployment calibration calendar_year must be numeric."
        )
    selected["calendar_year"] = selected["calendar_year"].astype(int)
    if selected.duplicated(["severity", "calendar_year"], keep=False).any():
        raise ValueError(
            "Conflict unemployment calibration contains duplicate "
            "severity-year rows."
        )
    for severity in sorted(observed_severities):
        years = tuple(
            sorted(
                selected.loc[
                    selected["severity"].eq(severity), "calendar_year"
                ].tolist()
            )
        )
        if years != _UNEMPLOYMENT_ANCHOR_YEARS:
            raise ValueError(
                f"Conflict unemployment {severity} anchors must cover exactly "
                f"{_UNEMPLOYMENT_ANCHOR_YEARS}."
            )
    for column in (
        "official_unemployment_rate_pct",
        "base_unemployment_rate_pct",
        "unemployment_gap_pp",
    ):
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
        if (
            selected[column].isna().any()
            or (~np.isfinite(selected[column])).any()
        ):
            raise ValueError(
                f"Conflict unemployment calibration column {column!r} must be finite."
            )
    if (
        selected["official_unemployment_rate_pct"].le(0.0).any()
        or selected["base_unemployment_rate_pct"].le(0.0).any()
    ):
        raise ValueError(
            "Conflict unemployment calibration rates must be positive."
        )
    if not np.allclose(
        selected["unemployment_gap_pp"],
        selected["official_unemployment_rate_pct"]
        - selected["base_unemployment_rate_pct"],
        rtol=0.0,
        atol=1e-9,
    ):
        raise ValueError(
            "Conflict unemployment gaps must equal official minus base rates."
        )
    for row in selected.itertuples(index=False):
        expected = _UNEMPLOYMENT_GAP_PP_BY_SEVERITY_YEAR[row.severity][
            int(row.calendar_year)
        ]
        if not np.isclose(
            float(row.unemployment_gap_pp), expected, rtol=0.0, atol=1e-12
        ):
            raise ValueError(
                "Conflict unemployment anchors no longer match the Treasury "
                "Annex 1 gaps."
            )
    if (
        selected["unemployment_gap_pp"].lt(0.0).any()
        or selected["unemployment_gap_pp"]
        .gt(_UNEMPLOYMENT_GAP_SANITY_BOUND_PP)
        .any()
    ):
        raise ValueError(
            "Conflict unemployment gaps must be within "
            f"[0, {_UNEMPLOYMENT_GAP_SANITY_BOUND_PP}] percentage points."
        )
    if not selected["source_url"].astype(str).eq(
        TREASURY_CONFLICT_GDP_URL
    ).all():
        raise ValueError(
            "Conflict unemployment calibration source URL is not the governed "
            "Treasury note."
        )
    for column in (
        "treasury_scenario",
        "source_document",
        "source_locator",
        "calibration_status",
    ):
        if selected[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(
                f"Conflict unemployment calibration lineage column {column!r} "
                "must be populated."
            )
    return selected.sort_values(
        ["severity", "calendar_year"], kind="stable"
    ).reset_index(drop=True)


def build_conflict_unemployment_paths(
    repo_root: Path | str | None = None,
    *,
    calibration: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Derive quarterly additive unemployment gaps (pp) per severity.

    The Treasury values are June-quarter points, so each calendar-year anchor
    sits at YQ2.  Quarters at or before 2026Q3 are observed common history and
    carry an exactly-zero gap for every severity; the 2026Q2 anchor is
    recorded for lineage and used as the interpolation origin but never
    applied.  Intermediate quarters interpolate linearly between anchors,
    starting to apply at 2026Q4.  After the last anchor (2028Q2) the medium
    gap tapers linearly to exactly zero by 2029Q2; the high gap is held
    through 2029Q2 (its GDP path has no recovery inside the governed window)
    and tapers linearly to exactly zero by 2030Q2.  Low has no Treasury
    unemployment anchor and carries a zero gap everywhere.
    """

    root = (
        Path(repo_root)
        if repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    anchors = (
        load_conflict_unemployment_calibration(root)
        if calibration is None
        else calibration.copy()
    )
    gaps_by_severity: dict[str, dict[int, float]] = {}
    for row in anchors.itertuples(index=False):
        gaps_by_severity.setdefault(str(row.severity), {})[
            int(row.calendar_year)
        ] = float(row.unemployment_gap_pp)
    order = {period: position for position, period in enumerate(EXPECTED_PERIODS)}
    history_cutoff = order[_UNEMPLOYMENT_OBSERVED_HISTORY_LAST_PERIOD]
    rows: list[dict[str, Any]] = []
    for severity in CONFLICT_FUEL_SCENARIO_LEVELS:
        gaps_by_year = gaps_by_severity.get(severity)
        if severity == "low" or not gaps_by_year:
            basis = (
                _UNEMPLOYMENT_DERIVATION_BASIS["low"]
                if severity == "low"
                else _UNEMPLOYMENT_NO_ANCHOR_BASIS
            )
            for period in EXPECTED_PERIODS:
                rows.append(
                    {
                        "severity": severity,
                        "period": period,
                        "unemployment_gap_pp": 0.0,
                        "treasury_anchor_gap_pp": np.nan,
                        "source_status": "no_official_anchor",
                        "derivation_basis": basis,
                        "source_url": TREASURY_CONFLICT_GDP_URL,
                    }
                )
            continue
        anchor_position_by_gap = sorted(
            (
                order[f"{year}Q{_UNEMPLOYMENT_ANCHOR_QUARTER}"],
                gaps_by_year[year],
            )
            for year in gaps_by_year
        )
        anchor_positions = [position for position, _ in anchor_position_by_gap]
        anchor_gaps = [gap for _, gap in anchor_position_by_gap]
        anchor_gap_by_position = dict(anchor_position_by_gap)
        last_position = anchor_positions[-1]
        last_gap = anchor_gaps[-1]
        hold_end = last_position + _UNEMPLOYMENT_HOLD_QUARTERS[severity]
        taper_end = hold_end + _UNEMPLOYMENT_TAPER_QUARTERS
        for period in EXPECTED_PERIODS:
            position = order[period]
            if position <= last_position:
                raw_gap = float(
                    np.interp(position, anchor_positions, anchor_gaps)
                )
            elif position <= hold_end:
                raw_gap = last_gap
            elif position <= taper_end:
                raw_gap = (
                    last_gap
                    * (taper_end - position)
                    / _UNEMPLOYMENT_TAPER_QUARTERS
                )
            else:
                raw_gap = 0.0
            if position <= history_cutoff:
                # Observed common history: severity-specific divergence must
                # not leak backwards into FY2026 annual totals.
                gap = 0.0
                status = (
                    "official_anchor_not_applied_observed_history"
                    if position in anchor_gap_by_position
                    else "observed_common_history"
                )
            elif position in anchor_gap_by_position:
                gap = anchor_gap_by_position[position]
                status = "official_anchor"
            elif position < last_position:
                gap = raw_gap
                status = "derived_linear_interpolation"
            elif position <= hold_end:
                gap = raw_gap
                status = "derived_recovery_hold"
            elif position <= taper_end:
                gap = raw_gap
                status = "derived_recovery_taper"
            else:
                gap = 0.0
                status = "recovered"
            rows.append(
                {
                    "severity": severity,
                    "period": period,
                    "unemployment_gap_pp": gap,
                    "treasury_anchor_gap_pp": (
                        anchor_gap_by_position[position]
                        if position in anchor_gap_by_position
                        else np.nan
                    ),
                    "source_status": status,
                    "derivation_basis": _UNEMPLOYMENT_DERIVATION_BASIS[
                        severity
                    ],
                    "source_url": TREASURY_CONFLICT_GDP_URL,
                }
            )
    out = pd.DataFrame(rows)
    validate_conflict_unemployment_paths(out, calibration=anchors)
    return out.reset_index(drop=True)


def validate_conflict_unemployment_paths(
    frame: pd.DataFrame,
    *,
    calibration: pd.DataFrame | None = None,
) -> None:
    """Validate anchors, bounds, ordering, history and end-of-window recovery."""

    required = {
        "severity",
        "period",
        "unemployment_gap_pp",
        "treasury_anchor_gap_pp",
        "source_status",
        "derivation_basis",
        "source_url",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "Conflict unemployment paths are missing columns: "
            + ", ".join(sorted(missing))
        )
    out = frame.copy()
    out["severity"] = out["severity"].astype(str)
    out["period"] = out["period"].astype(str)
    out["unemployment_gap_pp"] = pd.to_numeric(
        out["unemployment_gap_pp"], errors="coerce"
    )
    if (
        out["unemployment_gap_pp"].isna().any()
        or (~np.isfinite(out["unemployment_gap_pp"])).any()
    ):
        raise ValueError("Conflict unemployment gaps must be finite.")
    if out["unemployment_gap_pp"].lt(0.0).any():
        raise ValueError("Conflict unemployment gaps must be non-negative.")
    if out["unemployment_gap_pp"].gt(_UNEMPLOYMENT_GAP_SANITY_BOUND_PP).any():
        raise ValueError(
            "Conflict unemployment gaps exceed the "
            f"{_UNEMPLOYMENT_GAP_SANITY_BOUND_PP}pp sanity bound."
        )
    if set(out["severity"]) != set(CONFLICT_FUEL_SCENARIO_LEVELS):
        raise ValueError(
            "Conflict unemployment paths require low, medium and high severities."
        )
    if out.duplicated(["severity", "period"], keep=False).any():
        raise ValueError(
            "Conflict unemployment paths contain duplicate severity-period rows."
        )
    order = {period: position for position, period in enumerate(EXPECTED_PERIODS)}
    for severity in CONFLICT_FUEL_SCENARIO_LEVELS:
        group = out[out["severity"].eq(severity)].copy()
        group["_order"] = group["period"].map(order)
        if group["_order"].isna().any():
            raise ValueError(
                f"Conflict unemployment severity {severity!r} has ungoverned quarters."
            )
        group = group.sort_values("_order", kind="stable")
        if tuple(group["period"]) != tuple(EXPECTED_PERIODS):
            raise ValueError(
                f"Conflict unemployment severity {severity!r} does not have "
                "the exact governed quarters."
            )
    final_period = EXPECTED_PERIODS[-1]
    final_gaps = out[out["period"].eq(final_period)]["unemployment_gap_pp"]
    if not final_gaps.eq(0.0).all():
        raise ValueError(
            "Conflict unemployment gaps must reach exactly zero by "
            f"{final_period}."
        )
    # Observed common history: quarters at or before 2026Q3 are shared by all
    # severities (mirroring the governed fuel-path rule), so severity-specific
    # gaps must be exactly zero there or future path differences would leak
    # backwards into FY2026 annual totals.
    history_positions = [
        period
        for period in EXPECTED_PERIODS
        if order[period] <= order[_UNEMPLOYMENT_OBSERVED_HISTORY_LAST_PERIOD]
    ]
    history_gaps = out[out["period"].isin(history_positions)][
        "unemployment_gap_pp"
    ]
    if not history_gaps.eq(0.0).all():
        raise ValueError(
            "Conflict unemployment gaps must be exactly zero for every "
            f"severity through {_UNEMPLOYMENT_OBSERVED_HISTORY_LAST_PERIOD} "
            "(observed common history)."
        )
    low_gaps = out[out["severity"].eq("low")]["unemployment_gap_pp"]
    if not low_gaps.eq(0.0).all():
        raise ValueError(
            "Conflict unemployment low severity must carry a zero gap everywhere."
        )
    pivot = out.pivot(
        index="period", columns="severity", values="unemployment_gap_pp"
    )
    if ((pivot["medium"] - pivot["high"]) > 1e-12).any() or (
        (pivot["low"] - pivot["medium"]) > 1e-12
    ).any():
        raise ValueError(
            "Conflict unemployment gaps violate high >= medium >= low ordering."
        )
    anchors = (
        load_conflict_unemployment_calibration()
        if calibration is None
        else calibration.copy()
    )
    anchor_values = pd.to_numeric(out["treasury_anchor_gap_pp"], errors="coerce")
    for row in anchors.itertuples(index=False):
        severity = str(row.severity)
        year = int(row.calendar_year)
        expected_gap = float(row.unemployment_gap_pp)
        anchor_period = f"{year}Q{_UNEMPLOYMENT_ANCHOR_QUARTER}"
        anchor_mask = out["severity"].eq(severity) & out["period"].eq(
            anchor_period
        )
        if int(anchor_mask.sum()) != 1:
            raise ValueError(
                f"Conflict unemployment {severity} path is missing its "
                f"{anchor_period} Treasury anchor row."
            )
        recorded = float(anchor_values[anchor_mask].iloc[0])
        if not np.isclose(recorded, expected_gap, rtol=0.0, atol=1e-12):
            raise ValueError(
                f"Conflict unemployment {severity} path no longer records its "
                f"{anchor_period} Treasury anchor."
            )
        applied = float(out.loc[anchor_mask, "unemployment_gap_pp"].iloc[0])
        expected_applied = (
            0.0
            if order[anchor_period]
            <= order[_UNEMPLOYMENT_OBSERVED_HISTORY_LAST_PERIOD]
            else expected_gap
        )
        if not np.isclose(applied, expected_applied, rtol=0.0, atol=1e-12):
            raise ValueError(
                f"Conflict unemployment {severity} path no longer meets its "
                f"{anchor_period} Treasury anchor."
            )
    calibrated_severities = set(anchors["severity"].astype(str))
    for severity in ("medium", "high"):
        if severity in calibrated_severities:
            continue
        uncalibrated = out[out["severity"].eq(severity)]
        if not uncalibrated["unemployment_gap_pp"].eq(0.0).all() or not (
            uncalibrated["source_status"].astype(str).eq("no_official_anchor").all()
        ):
            raise ValueError(
                f"Conflict unemployment {severity} severity has no Treasury "
                "anchor and must carry an explicit zero gap."
            )
    if not out["source_url"].astype(str).eq(TREASURY_CONFLICT_GDP_URL).all():
        raise ValueError(
            "Conflict unemployment path source URL is not the Treasury "
            "scenario note."
        )


def apply_conflict_unemployment_impact(
    scenario_inputs: pd.DataFrame,
    *,
    severity: str,
    repo_root: Path | str | None = None,
    unemployment_paths: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Apply one conflict unemployment gap to the raw unemployment_rate field.

    The gap is additive in percentage points; ``unemployment_rate`` is stored
    as a fraction, so a +0.8pp gap adds 0.008.  Derived fields such as
    ``log_unemployment_rate`` are never touched because the fixed-finalist
    replay recomputes them from the raw field.
    """

    normalised = str(severity).strip().casefold()
    if normalised not in CONFLICT_FUEL_SCENARIO_LEVELS:
        raise ValueError(
            f"Unknown conflict unemployment severity {severity!r}; expected "
            + ", ".join(CONFLICT_FUEL_SCENARIO_LEVELS)
            + "."
        )
    required = {"stream", "canonical_period", "unemployment_rate"}
    missing = required.difference(scenario_inputs.columns)
    if missing:
        raise ValueError(
            "Scenario inputs cannot receive a conflict unemployment path "
            "without columns: " + ", ".join(sorted(missing))
        )
    paths = (
        build_conflict_unemployment_paths(repo_root)
        if unemployment_paths is None
        else unemployment_paths.copy()
    )
    validate_conflict_unemployment_paths(paths)
    selected = paths[paths["severity"].astype(str).eq(normalised)].copy()
    if selected.empty:
        raise ValueError(
            f"Conflict unemployment paths have no {normalised!r} rows."
        )
    gap_by_period = selected.set_index("period")[
        "unemployment_gap_pp"
    ].to_dict()
    basis = str(selected["derivation_basis"].iloc[0])

    out = scenario_inputs.copy()
    period = out["canonical_period"].astype(str)
    stream = out["stream"].astype(str)
    consuming = stream.isin(_UNEMPLOYMENT_RATE_STREAMS)
    # The audit gap is recorded only on rows whose stream actually receives
    # the adjustment, so the audit frame reflects applied changes.
    out["conflict_unemployment_gap_pp"] = np.where(
        consuming, period.map(gap_by_period).fillna(0.0), 0.0
    )
    out["conflict_unemployment_source_url"] = TREASURY_CONFLICT_GDP_URL
    out["conflict_unemployment_basis"] = basis
    field = "unemployment_rate"
    values = pd.to_numeric(out.loc[consuming, field], errors="coerce")
    gaps = pd.to_numeric(
        out.loc[consuming, "conflict_unemployment_gap_pp"], errors="coerce"
    )
    if (
        values.isna().any()
        or gaps.isna().any()
        or values.le(0.0).any()
        or gaps.lt(0.0).any()
    ):
        raise ValueError(
            "Conflict unemployment impact requires positive unemployment "
            "rates and non-negative gaps."
        )
    adjusted = values.to_numpy(dtype=float) + gaps.to_numpy(dtype=float) / 100.0
    if not np.isfinite(adjusted).all() or (adjusted <= 0.0).any():
        raise ValueError(
            "Conflict unemployment impact produced non-positive adjusted rates."
        )
    if pd.api.types.is_string_dtype(out[field].dtype):
        out.loc[consuming, field] = [
            format(float(value), ".17g") for value in adjusted
        ]
    else:
        out.loc[consuming, field] = adjusted
    return out.reset_index(drop=True)


def conflict_unemployment_input_audit(
    scenario_inputs: pd.DataFrame,
) -> pd.DataFrame:
    """Return one scenario/stream/quarter audit row for applied unemployment gaps."""

    # Ordered, not a set, for the same PYTHONHASHSEED schema-stability reason
    # as ``conflict_gdp_input_audit``.
    required = (
        "scenario_name",
        "stream",
        "canonical_period",
        "conflict_unemployment_gap_pp",
        "conflict_unemployment_source_url",
        "conflict_unemployment_basis",
    )
    missing = set(required).difference(scenario_inputs.columns)
    if missing:
        return pd.DataFrame()
    out = scenario_inputs[list(required)].copy()
    out = out.rename(columns={"canonical_period": "period"})
    out["conflict_unemployment_gap_pp"] = pd.to_numeric(
        out["conflict_unemployment_gap_pp"], errors="coerce"
    )
    return out.sort_values(
        ["scenario_name", "stream", "period"], kind="stable"
    ).reset_index(drop=True)

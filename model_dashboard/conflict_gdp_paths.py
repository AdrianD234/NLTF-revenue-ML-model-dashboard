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

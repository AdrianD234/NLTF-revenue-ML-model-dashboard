from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.conflict_fuel_paths import (
    BASE_DIESEL_2026Q1_CPL,
    BASE_DRIFT_CPL_PER_QUARTER,
    BASE_PETROL_2026Q1_CPL,
    CONFLICT_FUEL_SCENARIO_LEVELS,
    CONFLICT_FUEL_SCENARIO_SPECS,
    CONFLICT_SCENARIO_IDS,
    CONFLICT_SEVERITIES,
    EXPECTED_PERIODS,
    OBSERVED_DIESEL_2026Q2_CPL,
    OBSERVED_DIESEL_2026Q3_CPL,
    OBSERVED_PETROL_2026Q2_CPL,
    OBSERVED_PETROL_2026Q3_CPL,
    PETROL_CONFLICT_PREMIUM_RATIO,
    REQUIRED_COLUMNS,
    SCENARIO_REGISTRY,
    SOURCE_WORKBOOK_SHA256,
    all_conflict_policy_variants,
    conflict_policy_variant,
    conflict_policy_variant_name,
    conflict_scenario_name,
    conflict_scenario_note,
    conflict_scenario_display_name,
    conflict_scenario_id,
    conflict_trace_name,
    load_conflict_fuel_paths,
    load_conflict_fuel_price_paths,
    load_conflict_fuel_price_scenarios,
    validate_conflict_fuel_paths,
)


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv"


@pytest.fixture(scope="module")
def paths() -> pd.DataFrame:
    return load_conflict_fuel_paths(CSV_PATH)


def _row(paths: pd.DataFrame, severity: str, period: str) -> pd.Series:
    return paths[
        paths["severity"].astype(str).eq(severity)
        & paths["period"].astype(str).eq(period)
    ].iloc[0]


def test_loader_exposes_contract_registry_and_deterministic_order(
    paths: pd.DataFrame,
) -> None:
    assert set(REQUIRED_COLUMNS).issubset(paths.columns)
    assert len(paths) == len(CONFLICT_SEVERITIES) * len(EXPECTED_PERIODS)
    assert tuple(paths["severity"].drop_duplicates()) == CONFLICT_SEVERITIES
    assert tuple(paths.loc[paths["severity"].eq("low"), "period"]) == EXPECTED_PERIODS
    assert tuple(spec.scenario_id for spec in SCENARIO_REGISTRY.values()) == (
        CONFLICT_SCENARIO_IDS
    )
    assert load_conflict_fuel_price_scenarios(CSV_PATH).equals(paths)


def test_observed_anchors_are_common_and_exact(paths: pd.DataFrame) -> None:
    for severity in CONFLICT_SEVERITIES:
        q1 = _row(paths, severity, "2026Q1")
        q2 = _row(paths, severity, "2026Q2")
        q3 = _row(paths, severity, "2026Q3")
        assert q1["scenario_diesel_cpl"] == pytest.approx(
            BASE_DIESEL_2026Q1_CPL, abs=1e-12
        )
        assert q2["scenario_diesel_cpl"] == pytest.approx(
            OBSERVED_DIESEL_2026Q2_CPL, abs=1e-12
        )
        assert q2["scenario_petrol_cpl"] == pytest.approx(
            OBSERVED_PETROL_2026Q2_CPL, abs=1e-12
        )
        assert q3["scenario_diesel_cpl"] == pytest.approx(
            OBSERVED_DIESEL_2026Q3_CPL, abs=1e-12
        )
        assert q3["scenario_petrol_cpl"] == pytest.approx(
            OBSERVED_PETROL_2026Q3_CPL, abs=1e-12
        )
        assert q1["observation_status"] == "mixed"
        assert {q2["observation_status"], q3["observation_status"]} == {"observed"}


def test_policy_free_base_paths_drift_one_cent_per_quarter(
    paths: pd.DataFrame,
) -> None:
    low = paths[paths["severity"].eq("low")].reset_index(drop=True)
    assert low["base_diesel_cpl"].diff().dropna().eq(
        BASE_DRIFT_CPL_PER_QUARTER
    ).all()
    assert low["base_petrol_cpl"].diff().dropna().eq(
        BASE_DRIFT_CPL_PER_QUARTER
    ).all()
    assert low.iloc[0]["base_petrol_cpl"] == pytest.approx(
        BASE_PETROL_2026Q1_CPL, abs=1e-12
    )

    # The petrol base is solved at the common branch point so the latest
    # observed petrol premium equals 60% of the observed diesel premium.
    q3 = low[low["period"].eq("2026Q3")].iloc[0]
    petrol_premium = q3["scenario_petrol_cpl"] - q3["base_petrol_cpl"]
    diesel_premium = q3["scenario_diesel_cpl"] - q3["base_diesel_cpl"]
    assert petrol_premium == pytest.approx(
        PETROL_CONFLICT_PREMIUM_RATIO * diesel_premium,
        abs=1e-12,
    )


def test_low_medium_high_peaks_shapes_and_convergence(paths: pd.DataFrame) -> None:
    low_q3 = _row(paths, "low", "2026Q3")
    low_q4 = _row(paths, "low", "2026Q4")
    assert (
        low_q4["scenario_diesel_cpl"] - low_q4["base_diesel_cpl"]
    ) == pytest.approx(
        0.5 * (low_q3["scenario_diesel_cpl"] - low_q3["base_diesel_cpl"]),
        abs=1e-12,
    )

    medium_source = {
        "2026Q4": 410.0,
        "2027Q1": 407.0,
        "2027Q2": 400.0,
        "2027Q3": 388.0,
        "2027Q4": 374.0,
        "2028Q1": 358.0,
    }
    medium_peak_premium = (
        _row(paths, "medium", "2026Q4")["scenario_diesel_cpl"]
        - _row(paths, "medium", "2026Q4")["base_diesel_cpl"]
    )
    assert _row(paths, "medium", "2026Q4")["scenario_diesel_cpl"] == pytest.approx(
        315.0, abs=1e-12
    )
    for period, source_value in medium_source.items():
        row = _row(paths, "medium", period)
        actual_fraction = (
            row["scenario_diesel_cpl"] - row["base_diesel_cpl"]
        ) / medium_peak_premium
        expected_fraction = (source_value - 358.0) / (410.0 - 358.0)
        assert actual_fraction == pytest.approx(expected_fraction, abs=1e-12)

    high_source = {
        "2026Q4": 486.0,
        "2027Q1": 492.0,
        "2027Q2": 488.0,
        "2027Q3": 476.0,
        "2027Q4": 462.0,
        "2028Q1": 446.0,
        "2028Q2": 430.0,
        "2028Q3": 418.0,
        "2028Q4": 408.0,
        "2029Q1": 400.0,
        "2029Q2": 394.0,
        "2029Q3": 390.0,
        "2029Q4": 387.0,
        "2030Q1": 384.0,
        "2030Q2": 382.0,
        "2030Q3": 381.0,
        "2030Q4": 380.0,
    }
    high_peak = _row(paths, "high", "2027Q1")
    high_peak_premium = high_peak["scenario_diesel_cpl"] - high_peak["base_diesel_cpl"]
    assert high_peak["scenario_diesel_cpl"] == pytest.approx(385.0, abs=1e-12)
    for period, source_value in high_source.items():
        row = _row(paths, "high", period)
        actual_fraction = (
            row["scenario_diesel_cpl"] - row["base_diesel_cpl"]
        ) / high_peak_premium
        expected_fraction = (source_value - 380.0) / (492.0 - 380.0)
        assert actual_fraction == pytest.approx(expected_fraction, abs=1e-12)

    convergence = {"low": "2027Q1", "medium": "2028Q1", "high": "2030Q4"}
    period_order = {period: index for index, period in enumerate(EXPECTED_PERIODS)}
    for severity, convergence_period in convergence.items():
        rows = paths[
            paths["severity"].eq(severity)
            & paths["period"].map(period_order).ge(period_order[convergence_period])
        ]
        assert rows["scenario_diesel_cpl"].equals(rows["base_diesel_cpl"])
        assert rows["scenario_petrol_cpl"].equals(rows["base_petrol_cpl"])


def test_prospective_petrol_mapping_ordering_and_no_embedded_policy(
    paths: pd.DataFrame,
) -> None:
    period_order = {period: index for index, period in enumerate(EXPECTED_PERIODS)}
    prospective = paths[paths["period"].map(period_order).ge(period_order["2026Q4"])]
    expected_petrol = prospective["base_petrol_cpl"] + PETROL_CONFLICT_PREMIUM_RATIO * (
        prospective["scenario_diesel_cpl"] - prospective["base_diesel_cpl"]
    )
    assert prospective["scenario_petrol_cpl"].to_numpy() == pytest.approx(
        expected_petrol.to_numpy(), abs=1e-12
    )
    assert set(prospective["observation_status"]) == {"assumption"}
    assert not paths["fed_12c_embedded"].astype(bool).any()
    assert paths["policy_uplift_cpl"].eq(0.0).all()
    assert paths["source_workbook_sha256"].eq(SOURCE_WORKBOOK_SHA256).all()
    assert paths["source_url"].str.startswith("https://").all()
    assert paths["source_workbook_cell"].str.startswith("Diesel Price Forecast!").all()

    for period in EXPECTED_PERIODS[3:]:
        rows = paths[paths["period"].eq(period)].set_index("severity")
        for column in ("scenario_diesel_cpl", "scenario_petrol_cpl"):
            low, medium, high = rows.loc[list(CONFLICT_SEVERITIES), column]
            assert low <= medium <= high


def test_scenario_and_policy_variant_helpers_are_stable() -> None:
    assert CONFLICT_FUEL_SCENARIO_LEVELS == CONFLICT_SEVERITIES
    assert tuple(CONFLICT_FUEL_SCENARIO_SPECS) == CONFLICT_SEVERITIES
    assert conflict_scenario_id("low") == "middle_east_low"
    assert conflict_scenario_name("low") == "middle_east_low"
    assert conflict_scenario_id("middle_east_medium") == "middle_east_medium"
    assert conflict_scenario_display_name("high") == "Middle East conflict: High"
    assert conflict_trace_name("high") == "Middle East conflict: High"
    assert "contains no 12c FED" in conflict_scenario_note("medium")
    assert load_conflict_fuel_price_paths(ROOT).equals(
        load_conflict_fuel_paths(CSV_PATH)
    )

    variants = all_conflict_policy_variants()
    assert len(variants) == 6
    assert len({variant.scenario_id for variant in variants}) == 6
    assert {variant.policy_variant for variant in variants} == {"delay_6m", "no_uplift"}
    low_delay = conflict_policy_variant("low", "delay_6m")
    assert low_delay.scenario_id == "middle_east_low__12c_delay_6m"
    assert low_delay.display_name == (
        "Middle East conflict: Low - 12c deferred six months"
    )
    assert (
        conflict_policy_variant_name("low", "delayed_6m")
        == "middle_east_low__12c_delay_6m"
    )
    high_off = conflict_policy_variant("middle_east_high", "no_uplift")
    assert high_off.scenario_id == "middle_east_high__12c_no_uplift"
    assert high_off.display_name == "Middle East conflict: High - 12c uplift off"
    assert (
        conflict_policy_variant_name("middle_east_high", "off")
        == "middle_east_high__12c_no_uplift"
    )


def test_validator_rejects_embedded_policy_and_broken_convergence(
    paths: pd.DataFrame,
) -> None:
    embedded = paths.copy()
    embedded.loc[0, "fed_12c_embedded"] = True
    with pytest.raises(ValueError, match="must not embed"):
        validate_conflict_fuel_paths(embedded)

    broken = paths.copy()
    mask = broken["severity"].eq("medium") & broken["period"].eq("2028Q1")
    broken.loc[mask, "scenario_diesel_cpl"] += 1.0
    broken.loc[mask, "diesel_ratio"] = (
        broken.loc[mask, "scenario_diesel_cpl"] / broken.loc[mask, "base_diesel_cpl"]
    )
    with pytest.raises(ValueError, match="60%|converge"):
        validate_conflict_fuel_paths(broken)

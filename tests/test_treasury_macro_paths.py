from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.treasury_macro_paths import (
    EXPECTED_PERIODS,
    OFFICIAL_JUNE_POPULATION_MILLION,
    OFFICIAL_REAL_GDP_MILLION,
    TREASURY_BEFU26_ANNUAL_AVERAGE_REAL_GDP_GROWTH_PCT,
    TREASURY_BEFU26_SOURCE_SHA256,
    TREASURY_BEFU26_SOURCE_URL,
    TREASURY_PATH_END_PERIOD,
    apply_treasury_baseline_macro_path,
    load_treasury_macro_path,
    validate_treasury_macro_path,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    ROOT
    / "data"
    / "current_revenue_outlook"
    / "scenario_inputs"
    / "scenario_input_wide.csv"
)


@pytest.fixture(scope="module")
def macro_path() -> pd.DataFrame:
    return load_treasury_macro_path(ROOT)


@pytest.fixture(scope="module")
def scenario_inputs() -> pd.DataFrame:
    return pd.read_csv(INPUT_PATH)


def _base_rows(frame: pd.DataFrame, stream: str) -> pd.DataFrame:
    return (
        frame[
            frame["role"].astype(str).eq("basecase")
            & frame["stream"].astype(str).eq(stream)
        ]
        .sort_values("canonical_period", kind="stable")
        .reset_index(drop=True)
    )


def _row(frame: pd.DataFrame, stream: str, period: str) -> pd.Series:
    rows = frame[
        frame["role"].astype(str).eq("basecase")
        & frame["stream"].astype(str).eq(stream)
        & frame["canonical_period"].astype(str).eq(period)
    ]
    assert len(rows) == 1
    return rows.iloc[0]


def test_loader_matches_exact_official_gdp_and_population_contract(
    macro_path: pd.DataFrame,
) -> None:
    assert tuple(macro_path["period"]) == EXPECTED_PERIODS
    assert len(macro_path) == 21
    assert macro_path.set_index("period")[
        "treasury_real_gdp_sa_nzd_million"
    ].to_dict() == OFFICIAL_REAL_GDP_MILLION
    anchors = macro_path[
        macro_path["population_source_status"].eq("official_june_anchor")
    ].set_index("period")["treasury_population_million"].to_dict()
    assert anchors == OFFICIAL_JUNE_POPULATION_MILLION
    assert set(
        macro_path.loc[
            ~macro_path["period"].isin(OFFICIAL_JUNE_POPULATION_MILLION),
            "population_source_status",
        ]
    ) == {"derived_log_linear_interpolation"}
    assert macro_path["source_url"].eq(TREASURY_BEFU26_SOURCE_URL).all()
    assert (
        macro_path["source_workbook_sha256"]
        .str.upper()
        .eq(TREASURY_BEFU26_SOURCE_SHA256)
        .all()
    )
    assert macro_path.iloc[0]["real_gdp_source_cell"] == "Table 1!D21"
    assert macro_path.iloc[-1]["real_gdp_source_cell"] == "Table 1!D41"


def test_intervening_population_is_log_linearly_interpolated(
    macro_path: pd.DataFrame,
) -> None:
    values = macro_path.set_index("period")["treasury_population_million"]
    for year in range(2025, 2030):
        start = OFFICIAL_JUNE_POPULATION_MILLION[f"{year}Q2"]
        end = OFFICIAL_JUNE_POPULATION_MILLION[f"{year + 1}Q2"]
        for offset, period in enumerate(
            (f"{year}Q3", f"{year}Q4", f"{year + 1}Q1"),
            start=1,
        ):
            expected = start * (end / start) ** (offset / 4)
            assert values[period] == pytest.approx(expected, abs=5e-10)


def test_quarterly_levels_reconcile_to_treasury_annual_average_growth() -> None:
    def fiscal_year_average(fy: int) -> float:
        periods = (
            f"{fy - 1}Q3",
            f"{fy - 1}Q4",
            f"{fy}Q1",
            f"{fy}Q2",
        )
        return float(
            np.mean([OFFICIAL_REAL_GDP_MILLION[period] for period in periods])
        )

    # FY2026's published 1.2% annual-average rate needs pre-window FY2025
    # quarters. From FY2027 onward, the committed exact quarterly levels
    # independently reproduce Treasury's rounded headline rates.
    assert TREASURY_BEFU26_ANNUAL_AVERAGE_REAL_GDP_GROWTH_PCT[2026] == 1.2
    for fy in range(2027, 2031):
        actual = 100.0 * (
            fiscal_year_average(fy) / fiscal_year_average(fy - 1) - 1.0
        )
        assert round(actual, 1) == pytest.approx(
            TREASURY_BEFU26_ANNUAL_AVERAGE_REAL_GDP_GROWTH_PCT[fy],
            abs=1e-12,
        )


def test_validator_rejects_tampered_official_or_derived_values(
    macro_path: pd.DataFrame,
) -> None:
    broken_gdp = macro_path.copy()
    broken_gdp.loc[broken_gdp["period"].eq("2028Q2"), "treasury_real_gdp_sa_nzd_million"] += 1
    with pytest.raises(ValueError, match="real-GDP values"):
        validate_treasury_macro_path(broken_gdp)

    broken_population = macro_path.copy()
    broken_population.loc[
        broken_population["period"].eq("2027Q3"), "treasury_population_million"
    ] += 0.001
    with pytest.raises(ValueError, match="population path"):
        validate_treasury_macro_path(broken_population)


def test_transform_imports_treasury_growth_without_changing_2026q1_scale(
    scenario_inputs: pd.DataFrame,
) -> None:
    transformed = apply_treasury_baseline_macro_path(scenario_inputs, ROOT)
    original_anchor = float(
        _row(scenario_inputs, "LIGHT_RUC", "2026Q1")["real_gdp_sa_nzd"]
    )
    transformed_anchor = float(
        _row(transformed, "LIGHT_RUC", "2026Q1")["real_gdp_sa_nzd"]
    )
    assert transformed_anchor == pytest.approx(original_anchor, abs=1e-6)

    expected_2030q2 = (
        original_anchor
        * OFFICIAL_REAL_GDP_MILLION["2030Q2"]
        / OFFICIAL_REAL_GDP_MILLION["2026Q1"]
    )
    for stream in ("LIGHT_RUC", "HEAVY_RUC"):
        actual = float(
            _row(transformed, stream, "2030Q2")["real_gdp_sa_nzd"]
        )
        assert actual == pytest.approx(expected_2030q2, rel=1e-12)


def test_ped_population_and_gdp_per_capita_reconcile_to_common_gdp(
    scenario_inputs: pd.DataFrame,
) -> None:
    transformed = apply_treasury_baseline_macro_path(scenario_inputs, ROOT)
    for period in ("2026Q1", "2026Q2", "2027Q2", "2030Q2"):
        ped = _row(transformed, "PED", period)
        light = _row(transformed, "LIGHT_RUC", period)
        expected_population = (
            load_treasury_macro_path(ROOT)
            .set_index("period")
            .at[period, "treasury_population_million"]
            * 1_000_000
        )
        assert float(ped["population"]) == pytest.approx(
            expected_population, abs=1e-3
        )
        implied_gdp = float(ped["population"]) * float(
            ped["real_gdp_per_capita_nzd"]
        )
        assert implied_gdp == pytest.approx(
            float(light["real_gdp_sa_nzd"]), rel=1e-12
        )


def test_post_2030q2_original_quarterly_growth_is_preserved_and_reanchored(
    scenario_inputs: pd.DataFrame,
) -> None:
    transformed = apply_treasury_baseline_macro_path(scenario_inputs, ROOT)
    for stream, column in (
        ("LIGHT_RUC", "real_gdp_sa_nzd"),
        ("HEAVY_RUC", "real_gdp_sa_nzd"),
        ("PED", "population"),
    ):
        original_end = float(_row(scenario_inputs, stream, TREASURY_PATH_END_PERIOD)[column])
        original_next = float(_row(scenario_inputs, stream, "2030Q3")[column])
        transformed_end = float(_row(transformed, stream, TREASURY_PATH_END_PERIOD)[column])
        transformed_next = float(_row(transformed, stream, "2030Q3")[column])
        assert transformed_next / transformed_end == pytest.approx(
            original_next / original_end, rel=1e-12
        )
        assert (
            _row(transformed, stream, "2030Q3")["treasury_macro_phase"]
            == "reanchored_original_quarterly_growth"
        )


def test_transform_rebuilds_macro_features_and_preserves_price_inputs(
    scenario_inputs: pd.DataFrame,
) -> None:
    transformed = apply_treasury_baseline_macro_path(scenario_inputs, ROOT)
    price_columns = [
        column
        for column in scenario_inputs.columns
        if any(
            token in column.casefold()
            for token in ("price", "rate_cents", "nominal_rate", "ruc_rate", "fed_rate")
        )
        and "interaction" not in column.casefold()
    ]
    pd.testing.assert_frame_equal(
        transformed[price_columns],
        scenario_inputs[price_columns],
        check_dtype=True,
        check_exact=True,
    )

    non_base = ~scenario_inputs["role"].astype(str).eq("basecase")
    pd.testing.assert_frame_equal(
        transformed.loc[non_base, scenario_inputs.columns],
        scenario_inputs.loc[non_base],
        check_dtype=True,
        check_exact=True,
    )

    ped = _row(transformed, "PED", "2028Q2")
    assert float(ped["log_population"]) == pytest.approx(
        np.log(float(ped["population"])), abs=1e-12
    )
    assert float(ped["log_real_gdp_per_capita"]) == pytest.approx(
        np.log(float(ped["real_gdp_per_capita_nzd"])), abs=1e-12
    )
    assert float(ped["gdp_petrol_interaction"]) == pytest.approx(
        np.log(float(ped["real_gdp_per_capita_nzd"]))
        * np.log(float(ped["real_petrol_price_cents_per_litre"])),
        abs=1e-12,
    )

    light = _row(transformed, "LIGHT_RUC", "2028Q2")
    assert float(light["log_real_gdp"]) == pytest.approx(
        np.log(float(light["real_gdp_sa_nzd"])), abs=1e-12
    )
    assert float(light["gdp_light_ruc_price_interaction"]) == pytest.approx(
        np.log(float(light["real_gdp_sa_nzd"]))
        * np.log(float(light["real_light_ruc_price_nzd_per_1000km"])),
        abs=1e-12,
    )

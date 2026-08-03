from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import (
    _denton_quarterly_split,
    _disaggregate_annual_rows_to_quarterly,
    _filter_series_rows_with_fallback,
    _june_year_quarters,
    _quarterly_disaggregation_indicator_id,
)
from model_dashboard.fuel_price_scenario import (
    BASE_DELAYED_6M_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_NAME,
    IRAN_WAR_DELAYED_6M_SCENARIO_NAME,
    append_fuel_price_scenario_to_chart_rows,
    run_fuel_price_scenario_replay,
)
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    apply_fed_uplift_delay_to_chart_rows,
    fed_policy_affected_periods,
    fed_uplift_delayed_factors,
    ped_quarterly_rate_schedules,
)


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_INPUT_PATH = ROOT / "data/current_revenue_outlook/scenario_inputs/scenario_input_wide.parquet"
CHART_PATH = ROOT / "data/current_revenue_outlook/revenue_chart_rows.parquet"


@pytest.fixture(scope="module")
def delayed_policy_materialization() -> dict[str, object]:
    """Real Base/Iran rows after the governed six-month PED/RUC shift."""

    chart_rows = pd.read_parquet(CHART_PATH)
    replay = run_fuel_price_scenario_replay(
        pd.read_parquet(SCENARIO_INPUT_PATH),
        repo_root=ROOT,
        engine="ensemble",
    )
    delayed_rows, policy_audit = apply_fed_uplift_delay_to_chart_rows(
        chart_rows,
        fed_uplift_delayed_factors(ROOT, chart_rows),
        scenario_roles={"basecase", "comparison"},
        affected_periods_by_fy=fed_policy_affected_periods(
            ROOT,
            FED_POLICY_STATE_DELAYED_6M,
        ),
        policy_pair_factors=replay.policy_pair_factors,
    )
    published_rows, _ = append_fuel_price_scenario_to_chart_rows(chart_rows, replay)
    combined_rows, _ = append_fuel_price_scenario_to_chart_rows(delayed_rows, replay)
    return {
        "chart_rows": combined_rows,
        "published_chart_rows": published_rows,
        "replay": replay,
        "policy_audit": policy_audit,
    }


def test_denton_split_preserves_annual_sums_flat_indicator() -> None:
    annual = np.array([400.0, 480.0, 440.0])
    quarters = _denton_quarterly_split(annual, np.ones(12), average=False)
    sums = quarters.reshape(3, 4).sum(axis=1)
    assert np.allclose(sums, annual, atol=1e-6)
    # Smooth split: quarter-to-quarter movement stays modest relative to level.
    assert np.max(np.abs(np.diff(quarters))) < 30.0


def test_denton_split_follows_indicator_seasonality() -> None:
    annual = np.array([400.0, 400.0])
    indicator = np.tile([0.8, 1.2, 0.9, 1.1], 2)
    quarters = _denton_quarterly_split(annual, indicator, average=False)
    assert np.allclose(quarters.reshape(2, 4).sum(axis=1), annual, atol=1e-6)
    # Q2 (indicator 1.2) must exceed Q1 (indicator 0.8) in both years.
    assert quarters[1] > quarters[0]
    assert quarters[5] > quarters[4]


def test_denton_split_average_preserving_for_per_unit_series() -> None:
    annual = np.array([1500.0, 1520.0])
    quarters = _denton_quarterly_split(annual, np.ones(8), average=True)
    means = quarters.reshape(2, 4).mean(axis=1)
    assert np.allclose(means, annual, atol=1e-6)


def test_june_year_quarter_mapping() -> None:
    assert _june_year_quarters(2025) == ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]


def test_indicator_mapping_uses_stream_activity_paths() -> None:
    assert _quarterly_disaggregation_indicator_id("light_petrol_vkt") == "ped_vkt_per_capita"
    assert _quarterly_disaggregation_indicator_id("ped_volume") == "ped_vkt_per_capita"
    assert _quarterly_disaggregation_indicator_id("gross_ped_revenue") == "ped_vkt_per_capita"
    assert _quarterly_disaggregation_indicator_id("light_ruc_revenue") == "light_ruc_net_km"
    assert _quarterly_disaggregation_indicator_id("heavy_ruc_net_revenue") == "heavy_ruc_net_km"
    # Native quarterly series never route through disaggregation.
    assert _quarterly_disaggregation_indicator_id("ped_vkt_per_capita") == ""
    # Aggregates fall back to the smooth split.
    assert _quarterly_disaggregation_indicator_id("total_nltf_net_revenue") == ""


def test_forecast_traces_are_not_disaggregated_into_the_actuals_era() -> None:
    """A finalist nowcast anchor row (FY2025) must not become 2024Q3-2025Q2
    forecast quarters overlapping the actuals; forecast traces start at the
    first forecast June year (FY2026 -> 2025Q3)."""
    rows = []
    for fy, row_type, trace in [
        (2024, "historical_actual", "Actual"),
        (2025, "historical_actual", "Actual"),
        (2025, "future_forecast", "Current finalist Base case"),
        (2026, "future_forecast", "Current finalist Base case"),
    ]:
        rows.append(
            {
                "trace_name": trace,
                "scenario_name": "" if row_type == "historical_actual" else "current_basecase",
                "fed_path": "Current planned path",
                "series_id": "gross_ped_revenue",
                "series_label": "PED revenue",
                "stream": "gross_ped_revenue",
                "stream_label": "PED revenue",
                "row_type": row_type,
                "time_grain": "june_year",
                "period": f"FY{fy}",
                "june_year": fy,
                "value": 2000.0,
                "value_unit": "$m nominal ex GST",
            }
        )
    derived = _disaggregate_annual_rows_to_quarterly(pd.DataFrame(rows), pd.DataFrame())
    forecast = derived[derived["trace_name"].eq("Current finalist Base case")]
    actual = derived[derived["trace_name"].eq("Actual")]
    assert list(forecast["period"]) == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert actual["period"].max() == "2025Q2"
    # no overlap: forecast quarters all come after the last actual quarter
    assert min(forecast["period"]) > actual["period"].max()


def test_disaggregated_rows_are_tagged_and_sum_to_annual() -> None:
    annual_rows = pd.DataFrame(
        [
            {
                "trace_name": "Actual",
                "scenario_name": "",
                "fed_path": "Current planned path",
                "series_id": "total_nltf_net_revenue",
                "series_label": "Total NLTF revenue",
                "stream": "total_nltf_net_revenue",
                "stream_label": "Total NLTF revenue",
                "row_type": "historical_actual",
                "time_grain": "june_year",
                "period": f"FY{fy}",
                "june_year": fy,
                "value": value,
                "value_unit": "$m nominal ex GST",
            }
            for fy, value in [(2023, 4000.0), (2024, 4200.0), (2025, 4400.0)]
        ]
    )
    derived = _disaggregate_annual_rows_to_quarterly(annual_rows, pd.DataFrame())
    assert len(derived) == 12
    assert set(derived["data_scope"]) == {"quarterly_disaggregated_from_annual"}
    assert set(derived["value_status"]) == {"interpolated"}
    assert set(derived["time_grain"]) == {"quarterly"}
    by_fy = derived.groupby("june_year")["value"].sum()
    assert np.allclose(by_fy.loc[[2023, 2024, 2025]], [4000.0, 4200.0, 4400.0], atol=1e-6)
    assert list(derived[derived["june_year"].eq(2023)]["period"]) == ["2022Q3", "2022Q4", "2023Q1", "2023Q2"]


def test_fed_policy_delta_is_allocated_only_to_affected_quarters() -> None:
    annual = pd.DataFrame(
        [
            {
                "trace_name": "Current finalist Base case",
                "scenario_name": "current_basecase",
                "fed_path": "Current planned path",
                "series_id": "gross_ped_revenue",
                "series_label": "PED revenue",
                "stream": "gross_ped_revenue",
                "stream_label": "PED revenue",
                "row_type": "future_forecast",
                "time_grain": "june_year",
                "period": "FY2027",
                "june_year": 2027,
                "value": 380.0,
                "_fed_baseline_value": 400.0,
                "_fed_annual_delta": -20.0,
                "_fed_policy": "delayed_6m",
                "_fed_affected_quarters": "2027Q1;2027Q2",
                "value_unit": "$m nominal ex GST",
            }
        ]
    )
    derived = _disaggregate_annual_rows_to_quarterly(annual, pd.DataFrame()).set_index("period")
    assert derived.loc["2026Q3", "value"] == pytest.approx(100.0)
    assert derived.loc["2026Q4", "value"] == pytest.approx(100.0)
    assert derived.loc["2027Q1", "value"] == pytest.approx(90.0)
    assert derived.loc["2027Q2", "value"] == pytest.approx(90.0)
    assert derived["value"].sum() == pytest.approx(380.0)
    assert set(derived["value_status"]) == {"interpolated_fed_policy"}


def test_quarterly_fallback_fills_mbu_trace_when_current_native_rows_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = pd.read_parquet(root / "data/current_revenue_outlook/revenue_chart_rows.parquet")
    selected, used_fallback = _filter_series_rows_with_fallback(
        rows,
        "Light RUC net km",
        "quarterly",
        "Current planned path",
        ("Current finalist Base case", "MBU26 official"),
    )
    assert used_fallback
    assert set(selected["trace_name"].astype(str)) == {
        "Current finalist Base case",
        "MBU26 official",
    }
    native_base = selected[selected["trace_name"].astype(str).eq("Current finalist Base case")]
    derived_mbu = selected[selected["trace_name"].astype(str).eq("MBU26 official")]
    assert not native_base.empty and not derived_mbu.empty
    assert set(native_base["data_scope"].astype(str)) == {"quarterly_current_finalist_input"}
    # The display path now derives through the governed coverage contract, so
    # the provenance vocabulary is that contract's, not the older ad-hoc one.
    # These two fields are what separate a derived quarter from a published
    # observation in every audit and download, so they are asserted exactly.
    assert set(derived_mbu["data_scope"].astype(str)) == {
        "derived_quarterly_from_governed_annual"
    }
    assert set(derived_mbu["value_status"].astype(str)) == {"derived_quarterly_display"}
    assert set(derived_mbu["coverage_row_type"].astype(str)) == {
        "derived_quarterly_from_governed_annual"
    }
    assert set(derived_mbu["empirical_or_derived"].astype(str)) == {"derived"}
    # An official comparator's derived quarters must never read as published
    # official quarterly data.
    assert set(derived_mbu["source_basis"].astype(str)) == {
        "derived quarterly presentation from official annual source"
    }
    actual = rows[
        rows["series_id"].astype(str).eq("light_ruc_net_km")
        & rows["time_grain"].astype(str).eq("quarterly")
        & rows["row_type"].astype(str).eq("historical_actual")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2026)
    ]
    # Since the 2026Q1 actuals refresh, the accepted Light RUC 2026Q1 actual
    # joins the FY2026 quarterly inventory as history.
    assert set(actual["period"].astype(str)) == {"2025Q3", "2025Q4", "2026Q1"}
    assert not derived_mbu["period"].astype(str).isin(actual["period"].astype(str)).any()
    for fy, group in derived_mbu.groupby(pd.to_numeric(derived_mbu["june_year"], errors="coerce")):
        expected = set(_june_year_quarters(int(fy)))
        if int(fy) == 2026:
            expected -= set(actual["period"].astype(str))
        assert set(group["period"].astype(str)) == expected

    mbu_fy2026 = rows[
        rows["scenario_name"].astype(str).eq("mbu26_official")
        & rows["series_id"].astype(str).eq("light_ruc_net_km")
        & rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(2026)
    ]
    derived_fy2026 = derived_mbu[pd.to_numeric(derived_mbu["june_year"], errors="coerce").eq(2026)]
    hybrid_total_million_km = (
        pd.to_numeric(actual["value"], errors="coerce").sum() / 1_000_000.0
        + pd.to_numeric(derived_fy2026["value"], errors="coerce").sum()
    )
    assert hybrid_total_million_km == pytest.approx(float(mbu_fy2026.iloc[0]["value"]), abs=1e-9)


def test_delayed_base_and_iran_net_revenue_quarters_reconcile_exactly_to_june_years(
    delayed_policy_materialization: dict[str, object],
) -> None:
    """Every displayed revenue year remains an exact four-quarter partition."""

    chart_rows = delayed_policy_materialization["chart_rows"]
    assert isinstance(chart_rows, pd.DataFrame)
    series_ids = (
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
    )
    scenario_names = ("current_basecase", FUEL_PRICE_SCENARIO_NAME)

    for scenario_name in scenario_names:
        for series_id in series_ids:
            annual = chart_rows[
                chart_rows["scenario_name"].astype(str).eq(scenario_name)
                & chart_rows["series_id"].astype(str).eq(series_id)
                & chart_rows["time_grain"].astype(str).eq("june_year")
                & pd.to_numeric(chart_rows["june_year"], errors="coerce").between(2026, 2030)
            ].copy()
            assert len(annual) == 5
            assert not annual.duplicated("june_year").any()

            quarterly = _disaggregate_annual_rows_to_quarterly(annual, chart_rows)
            for annual_row in annual.itertuples():
                fy = int(annual_row.june_year)
                year_quarters = quarterly[
                    pd.to_numeric(quarterly["june_year"], errors="coerce").eq(fy)
                ]
                assert set(year_quarters["period"].astype(str)) == set(_june_year_quarters(fy))
                assert len(year_quarters) == 4
                assert pd.to_numeric(year_quarters["value"], errors="coerce").sum() == pytest.approx(
                    float(annual_row.value),
                    rel=0.0,
                    abs=1e-8,
                )


def test_delayed_base_high_and_iran_native_activity_quarters_reconcile_to_june_years(
    delayed_policy_materialization: dict[str, object],
) -> None:
    """The policy bridge must expose one coherent activity path at both grains."""

    chart_rows = delayed_policy_materialization["chart_rows"]
    published_rows = delayed_policy_materialization["published_chart_rows"]
    policy_audit = delayed_policy_materialization["policy_audit"]
    assert isinstance(chart_rows, pd.DataFrame)
    assert isinstance(published_rows, pd.DataFrame)
    assert isinstance(policy_audit, pd.DataFrame)

    def base_value(row: object) -> float:
        value = float(getattr(row, "value"))
        unit = str(getattr(row, "value_unit", "")).lower()
        return value * (1_000_000.0 if "million" in unit else 1.0)

    scenario_names = (
        "current_basecase",
        "current_comparison_1",
        FUEL_PRICE_SCENARIO_NAME,
    )
    series_ids = (
        "ped_vkt_per_capita",
        "light_ruc_net_km",
        "heavy_ruc_net_km",
    )
    for scenario_name in scenario_names:
        for series_id in series_ids:
            for fy in range(2026, 2031):
                annual = chart_rows[
                    chart_rows["scenario_name"].astype(str).eq(scenario_name)
                    & chart_rows["series_id"].astype(str).eq(series_id)
                    & chart_rows["time_grain"].astype(str).eq("june_year")
                    & pd.to_numeric(chart_rows["june_year"], errors="coerce").eq(fy)
                ]
                scenario_quarters = chart_rows[
                    chart_rows["scenario_name"].astype(str).eq(scenario_name)
                    & chart_rows["series_id"].astype(str).eq(series_id)
                    & chart_rows["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(chart_rows["june_year"], errors="coerce").eq(fy)
                ]
                actual_quarters = chart_rows[
                    chart_rows["row_type"].astype(str).eq("historical_actual")
                    & chart_rows["series_id"].astype(str).eq(series_id)
                    & chart_rows["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(chart_rows["june_year"], errors="coerce").eq(fy)
                ]
                quarters = pd.concat(
                    [actual_quarters, scenario_quarters], ignore_index=True
                )
                assert len(annual) == 1
                assert set(quarters["period"].astype(str)) == set(_june_year_quarters(fy))
                assert not quarters["period"].astype(str).duplicated().any()
                assert sum(base_value(row) for row in quarters.itertuples()) == pytest.approx(
                    base_value(next(annual.itertuples())),
                    rel=0.0,
                    abs=1e-5,
                )

    # FY2026's already-published actual quarters are value-identical in base
    # units; the bridge may only normalise their display unit to million km.
    for series_id in series_ids:
        before = published_rows[
            published_rows["row_type"].astype(str).eq("historical_actual")
            & published_rows["series_id"].astype(str).eq(series_id)
            & published_rows["time_grain"].astype(str).eq("quarterly")
            & pd.to_numeric(published_rows["june_year"], errors="coerce").eq(2026)
        ].sort_values("period")
        after = chart_rows[
            chart_rows["row_type"].astype(str).eq("historical_actual")
            & chart_rows["series_id"].astype(str).eq(series_id)
            & chart_rows["time_grain"].astype(str).eq("quarterly")
            & pd.to_numeric(chart_rows["june_year"], errors="coerce").eq(2026)
        ].sort_values("period")
        assert list(after["period"].astype(str)) == list(before["period"].astype(str))
        assert [base_value(row) for row in after.itertuples()] == pytest.approx(
            [base_value(row) for row in before.itertuples()], abs=1e-5
        )

    # The delayed policy starts in 2027Q1.  The two earlier FY2027 quarters
    # stay exactly on the published Base path; only policy/model-active
    # quarters absorb the annual reconciliation.
    for series_id in series_ids:
        for period in ("2026Q3", "2026Q4"):
            before = published_rows[
                published_rows["scenario_name"].astype(str).eq("current_basecase")
                & published_rows["series_id"].astype(str).eq(series_id)
                & published_rows["period"].astype(str).eq(period)
                & published_rows["time_grain"].astype(str).eq("quarterly")
            ]
            after = chart_rows[
                chart_rows["scenario_name"].astype(str).eq("current_basecase")
                & chart_rows["series_id"].astype(str).eq(series_id)
                & chart_rows["period"].astype(str).eq(period)
                & chart_rows["time_grain"].astype(str).eq("quarterly")
            ]
            assert len(before) == len(after) == 1
            assert base_value(next(after.itertuples())) == pytest.approx(
                base_value(next(before.itertuples())), abs=1e-5
            )

    reconciled = chart_rows[
        chart_rows["scenario_name"].astype(str).isin(
            {"current_basecase", "current_comparison_1"}
        )
        & chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["series_id"].astype(str).isin(series_ids)
        & chart_rows["data_scope"].astype(str).str.endswith(
            "quarterly_annual_reconciliation"
        )
    ]
    assert not reconciled.empty
    assert reconciled["value_status"].astype(str).str.endswith(
        "quarterly_reconciled"
    ).all()
    assert pd.to_numeric(
        policy_audit["quarterly_annual_reconciliation_delta"], errors="coerce"
    ).abs().gt(0).any()

    # The official MBU comparator has no behavioural replay and is untouched.
    mbu_columns = [
        "series_id",
        "time_grain",
        "period",
        "june_year",
        "value",
        "value_unit",
    ]
    before_mbu = published_rows[
        published_rows["scenario_name"].astype(str).eq("mbu26_official")
    ][mbu_columns].reset_index(drop=True)
    after_mbu = chart_rows[
        chart_rows["scenario_name"].astype(str).eq("mbu26_official")
    ][mbu_columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(after_mbu, before_mbu, check_dtype=False)


def test_published_and_delayed_base_and_iran_fed_ruc_subtotals_close_by_year_and_quarter(
    delayed_policy_materialization: dict[str, object],
) -> None:
    """The selectable subtotal is the sum of its canonical net components."""

    series_ids = (
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
    )
    scenario_names = ("current_basecase", FUEL_PRICE_SCENARIO_NAME)
    for materialization_key in ("published_chart_rows", "chart_rows"):
        chart_rows = delayed_policy_materialization[materialization_key]
        assert isinstance(chart_rows, pd.DataFrame)
        for scenario_name in scenario_names:
            annual_components: dict[str, pd.DataFrame] = {}
            quarterly_components: dict[str, pd.DataFrame] = {}
            for series_id in series_ids:
                annual = chart_rows[
                    chart_rows["scenario_name"].astype(str).eq(scenario_name)
                    & chart_rows["series_id"].astype(str).eq(series_id)
                    & chart_rows["time_grain"].astype(str).eq("june_year")
                    & pd.to_numeric(chart_rows["june_year"], errors="coerce").between(2026, 2030)
                ].copy()
                assert len(annual) == 5
                annual_components[series_id] = annual.set_index("june_year")
                quarterly_components[series_id] = _disaggregate_annual_rows_to_quarterly(
                    annual,
                    chart_rows,
                ).set_index("period")

            annual_residual = (
                pd.to_numeric(
                    annual_components["total_fed_ruc_net_revenue"]["value"],
                    errors="coerce",
                )
                - pd.to_numeric(annual_components["net_fed_revenue"]["value"], errors="coerce")
                - pd.to_numeric(
                    annual_components["total_ruc_net_revenue"]["value"],
                    errors="coerce",
                )
            )
            assert annual_residual.abs().max() == pytest.approx(0.0, abs=1e-9)

            quarterly_residual = (
                pd.to_numeric(
                    quarterly_components["total_fed_ruc_net_revenue"]["value"],
                    errors="coerce",
                )
                - pd.to_numeric(
                    quarterly_components["net_fed_revenue"]["value"],
                    errors="coerce",
                )
                - pd.to_numeric(
                    quarterly_components["total_ruc_net_revenue"]["value"],
                    errors="coerce",
                )
            )
            assert quarterly_residual.abs().max() == pytest.approx(0.0, abs=1e-9)
            assert set(
                quarterly_components["total_fed_ruc_net_revenue"]["value_status"].astype(str)
            ) == {"interpolated_formula_rebuilt"}


def test_delayed_policy_direct_window_is_two_quarters_without_raw_recursive_carry(
    delayed_policy_materialization: dict[str, object],
) -> None:
    replay = delayed_policy_materialization["replay"]

    schedules = ped_quarterly_rate_schedules(ROOT)
    changed_rate_quarters = set(
        schedules.index[
            (
                pd.to_numeric(schedules["delayed_6m"], errors="coerce")
                - pd.to_numeric(schedules["planned"], errors="coerce")
            )
            .abs()
            .gt(1e-12)
        ].astype(str)
    )
    assert changed_rate_quarters == {"2027Q1", "2027Q2"}

    source_by_scenario = {
        BASE_DELAYED_6M_SCENARIO_NAME: "current_basecase",
        IRAN_WAR_DELAYED_6M_SCENARIO_NAME: FUEL_PRICE_SCENARIO_NAME,
    }
    replay_inputs = replay.replay_inputs.set_index(
        ["scenario_name", "stream", "canonical_period"]
    ).sort_index()
    direct_fields = {
        "PED": ("real_petrol_price_cents_per_litre",),
        "LIGHT_RUC": ("real_light_ruc_price_nzd_per_1000km",),
        "HEAVY_RUC": (
            "real_light_ruc_price_nzd_per_1000km",
            "real_heavy_ruc_price_nzd_per_1000km",
        ),
    }
    all_periods = sorted(
        replay.replay_inputs["canonical_period"].dropna().astype(str).unique()
    )
    for delayed_name, source_name in source_by_scenario.items():
        for stream, fields in direct_fields.items():
            for field in fields:
                changed_input_quarters = {
                    period
                    for period in all_periods
                    if not np.isclose(
                        float(replay_inputs.at[(delayed_name, stream, period), field]),
                        float(replay_inputs.at[(source_name, stream, period), field]),
                        rtol=0.0,
                        atol=1e-12,
                    )
                }
                assert changed_input_quarters == {"2027Q1", "2027Q2"}

        lag_field = "lagged_real_light_ruc_price_nzd_per_1000km"
        changed_lag_quarters = {
            period
            for period in all_periods
            if not np.isclose(
                float(replay_inputs.at[(delayed_name, "LIGHT_RUC", period), lag_field]),
                float(replay_inputs.at[(source_name, "LIGHT_RUC", period), lag_field]),
                rtol=0.0,
                atol=1e-12,
            )
        }
        assert changed_lag_quarters == {"2027Q2", "2027Q3"}

        forecasts = replay.future_forecasts.set_index(
            ["scenario_name", "stream", "target_period"]
        ).sort_index()
        for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
            for period in ("2027Q1", "2027Q2"):
                assert float(
                    forecasts.at[(delayed_name, stream, period), "forecast"]
                ) > float(forecasts.at[(source_name, stream, period), "forecast"])
                assert bool(
                    forecasts.at[
                        (delayed_name, stream, period),
                        "policy_calibration_applied",
                    ]
                )
        # The lagged diagnostic input correctly records the prior-quarter
        # policy rate, but the delivered calibrated path must not inherit the
        # raw replay's recursive carry after the two-quarter direct window.
        assert float(forecasts.at[(delayed_name, "LIGHT_RUC", "2027Q3"), "forecast"]) == pytest.approx(
            float(forecasts.at[(source_name, "LIGHT_RUC", "2027Q3"), "forecast"]),
            rel=1e-12,
        )

    annual_pairs = replay.policy_pair_factors[
        replay.policy_pair_factors["pair_id"].astype(str).isin(
            ["baseline_delayed_6m", "iran_vs_baseline_delayed_6m"]
        )
        & replay.policy_pair_factors["time_grain"].astype(str).eq("june_year")
        & replay.policy_pair_factors["series_id"].astype(str).eq("total_ruc_net_revenue")
        & pd.to_numeric(replay.policy_pair_factors["june_year"], errors="coerce").between(2028, 2030)
    ]
    assert len(annual_pairs) == 6
    annual_delta = annual_pairs.pivot_table(
        index="pair_id",
        columns="june_year",
        values="delta",
        aggfunc="first",
    ).apply(pd.to_numeric, errors="coerce")
    # The Base policy replay has no delivered carry beyond its direct window.
    assert annual_delta.loc["baseline_delayed_6m"].abs().max() <= 1e-9
    # The legacy-named comparison key represents the Medium conflict path:
    # its fuel premium remains in FY2028, then converges to Base.
    assert abs(float(annual_delta.at["iran_vs_baseline_delayed_6m", 2028])) > 1e-9
    assert annual_delta.loc[
        "iran_vs_baseline_delayed_6m", [2029, 2030]
    ].abs().max() <= 1e-9

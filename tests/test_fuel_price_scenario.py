from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.fuel_price_scenario import (
    FUEL_PRICE_MULTIPLIER,
    FUEL_PRICE_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_TRACE_NAME,
    FUEL_PRICE_SHOCK_PERIODS,
    RUC_PRICE_LAGGED_EFFECT_PERIODS,
    RUC_PRICE_MULTIPLIER,
    RUC_PRICE_SHOCK_PERIODS,
    _validate_complete_numeric_replay,
    append_fuel_price_scenario_to_chart_rows,
    build_fuel_price_scenario_inputs,
    run_fuel_price_scenario_replay,
)
from model_dashboard.forecast_runner import ScenarioInputForecastReplayResult
from model_dashboard.ev_uptake_levers import EV_UPTAKE_PRESETS, apply_uptake_levers_to_chart_rows
from model_dashboard.rate_paths import apply_fed_uplift_delay_to_chart_rows, fed_uplift_delayed_factors


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data/current_revenue_outlook/scenario_inputs/scenario_input_wide.parquet"
CHART_PATH = ROOT / "data/current_revenue_outlook/revenue_chart_rows.parquet"
AR1_INPUT_PATH = ROOT / "data/engine_ar1/current_revenue_outlook/scenario_inputs/scenario_input_wide.parquet"
AR1_CHART_PATH = ROOT / "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.parquet"


@pytest.fixture(scope="module")
def scenario_inputs() -> pd.DataFrame:
    return pd.read_parquet(INPUT_PATH)


@pytest.fixture(scope="module")
def fuel_replay(scenario_inputs):
    return run_fuel_price_scenario_replay(scenario_inputs, repo_root=ROOT, engine="ensemble")


@pytest.fixture(scope="module")
def ar1_fuel_replay():
    return run_fuel_price_scenario_replay(
        pd.read_parquet(AR1_INPUT_PATH),
        repo_root=ROOT,
        engine="ar1",
    )


def _ordered(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["stream", "canonical_period"], kind="stable").reset_index(drop=True)


def _annual(rows: pd.DataFrame, scenario: str, fy: int) -> pd.DataFrame:
    selected = rows[
        rows["scenario_name"].astype(str).eq(scenario)
        & rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ].copy()
    return selected.set_index("series_id")


def test_iran_replay_rejects_partial_numeric_stream_coverage() -> None:
    scenarios = ("current_basecase", FUEL_PRICE_SCENARIO_NAME)
    periods = ("2026Q1", "2026Q2")
    input_rows = [
        {"scenario_name": scenario, "stream": stream, "canonical_period": period}
        for scenario in scenarios
        for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC")
        for period in periods
    ]
    forecast_rows = [
        {
            "scenario_name": scenario,
            "stream": stream,
            "target_period": period,
            "forecast": 1.0 if stream == "LIGHT_RUC" else pd.NA,
            "gap_code": None if stream == "LIGHT_RUC" else f"{stream.lower()}_vnext_parity_failed",
            "gap_reason": "Load gate error: ModuleNotFoundError: No module named '_loss'"
            if stream != "LIGHT_RUC"
            else "",
        }
        for scenario in scenarios
        for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC")
        for period in periods
    ]
    replay = ScenarioInputForecastReplayResult(
        future_forecasts=pd.DataFrame(forecast_rows),
        component_forecasts=pd.DataFrame(),
        assumptions=pd.DataFrame(),
        validation_report=pd.DataFrame(),
    )

    with pytest.raises(ValueError, match="lacks complete numeric coverage") as excinfo:
        _validate_complete_numeric_replay(
            replay,
            replay_inputs=pd.DataFrame(input_rows),
            scenario_names=scenarios,
        )

    message = str(excinfo.value)
    assert "current_basecase/PED: 0 of 2 required quarters are numeric" in message
    assert "current_basecase/HEAVY_RUC: 0 of 2 required quarters are numeric" in message
    assert "No module named '_loss'" in message


def test_run_rejects_partial_replay_before_annual_bridge(
    scenario_inputs: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import model_dashboard.fuel_price_scenario as scenario_module

    def incomplete_replay(replay_inputs, **_kwargs):
        rows = replay_inputs[["scenario_name", "stream", "canonical_period"]].rename(
            columns={"canonical_period": "target_period"}
        )
        rows["forecast"] = np.where(rows["stream"].astype(str).eq("LIGHT_RUC"), 1.0, np.nan)
        rows["gap_code"] = np.where(
            rows["stream"].astype(str).eq("PED"),
            "ped_ar1_parity_failed",
            np.where(
                rows["stream"].astype(str).eq("HEAVY_RUC"),
                "heavy_ruc_vnext_parity_failed",
                "",
            ),
        )
        rows["gap_reason"] = np.where(
            rows["stream"].astype(str).eq("LIGHT_RUC"),
            "",
            "clean-cloud runtime dependency/load gate failed",
        )
        validation = pd.DataFrame(
            {
                "scenario_name": rows["scenario_name"].drop_duplicates().tolist(),
                "valid": True,
                "errors": "",
            }
        )
        return ScenarioInputForecastReplayResult(
            future_forecasts=rows,
            component_forecasts=pd.DataFrame(),
            assumptions=pd.DataFrame(),
            validation_report=validation,
        )

    monkeypatch.setattr(scenario_module, "replay_forecast_from_scenario_inputs", incomplete_replay)
    monkeypatch.setattr(
        scenario_module,
        "_annual_bridge_and_factors",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("annual bridge must not run for an incomplete replay")
        ),
    )

    with pytest.raises(ValueError, match="lacks complete numeric coverage") as excinfo:
        run_fuel_price_scenario_replay(scenario_inputs, repo_root=ROOT, engine="ensemble")

    message = str(excinfo.value)
    assert "current_basecase/PED: 0 of 100 required quarters are numeric" in message
    assert "current_basecase/HEAVY_RUC: 0 of 100 required quarters are numeric" in message
    assert "ped_ar1_parity_failed" in message


def test_build_iran_war_scenario_inputs_changes_only_governed_fuel_and_ruc_drivers(scenario_inputs) -> None:
    base = _ordered(scenario_inputs[scenario_inputs["role"].astype(str).eq("basecase")])
    fuel = _ordered(build_fuel_price_scenario_inputs(scenario_inputs))

    assert len(base) == len(fuel) == 300
    assert set(fuel["scenario_name"].astype(str)) == {FUEL_PRICE_SCENARIO_NAME}
    assert set(fuel["role"].astype(str)) == {"comparison"}
    assert set(fuel["scenario_display_name"].astype(str)) == {FUEL_PRICE_SCENARIO_TRACE_NAME}

    fuel_fields = {
        "PED": "real_petrol_price_cents_per_litre",
        "LIGHT_RUC": "real_diesel_price_cents_per_litre",
        "HEAVY_RUC": "real_diesel_price_cents_per_litre",
    }
    changed_cells: list[tuple[str, str, str]] = []
    for stream, field in fuel_fields.items():
        stream_mask = fuel["stream"].astype(str).eq(stream)
        for period in FUEL_PRICE_SHOCK_PERIODS:
            mask = stream_mask & fuel["canonical_period"].astype(str).eq(period)
            base_value = float(pd.to_numeric(base.loc[mask, field], errors="coerce").iloc[0])
            fuel_value = float(pd.to_numeric(fuel.loc[mask, field], errors="coerce").iloc[0])
            assert fuel_value == pytest.approx(base_value * FUEL_PRICE_MULTIPLIER, rel=1e-12)
            changed_cells.append((stream, period, field))

        outside = stream_mask & ~fuel["canonical_period"].astype(str).isin(FUEL_PRICE_SHOCK_PERIODS)
        np.testing.assert_allclose(
            pd.to_numeric(fuel.loc[outside, field], errors="coerce"),
            pd.to_numeric(base.loc[outside, field], errors="coerce"),
            rtol=0.0,
            atol=0.0,
        )

    ruc_fields = {
        "LIGHT_RUC": ("real_light_ruc_price_nzd_per_1000km",),
        "HEAVY_RUC": (
            "real_light_ruc_price_nzd_per_1000km",
            "real_heavy_ruc_price_nzd_per_1000km",
        ),
    }
    for stream, fields in ruc_fields.items():
        stream_mask = fuel["stream"].astype(str).eq(stream)
        for field in fields:
            for period in RUC_PRICE_SHOCK_PERIODS:
                mask = stream_mask & fuel["canonical_period"].astype(str).eq(period)
                base_value = float(pd.to_numeric(base.loc[mask, field], errors="coerce").iloc[0])
                scenario_value = float(pd.to_numeric(fuel.loc[mask, field], errors="coerce").iloc[0])
                assert scenario_value == pytest.approx(base_value * RUC_PRICE_MULTIPLIER, rel=1e-12)
                changed_cells.append((stream, period, field))
            outside = stream_mask & ~fuel["canonical_period"].astype(str).isin(RUC_PRICE_SHOCK_PERIODS)
            np.testing.assert_allclose(
                pd.to_numeric(fuel.loc[outside, field], errors="coerce"),
                pd.to_numeric(base.loc[outside, field], errors="coerce"),
                rtol=0.0,
                atol=0.0,
            )

    # The explicit Light-price lag follows the shocked current path one
    # quarter later, including the final carry into 2027Q3.
    lag_field = "lagged_real_light_ruc_price_nzd_per_1000km"
    light_mask = fuel["stream"].astype(str).eq("LIGHT_RUC")
    for source_period, target_period in zip(RUC_PRICE_SHOCK_PERIODS, RUC_PRICE_LAGGED_EFFECT_PERIODS, strict=True):
        source_mask = light_mask & fuel["canonical_period"].astype(str).eq(source_period)
        target_mask = light_mask & fuel["canonical_period"].astype(str).eq(target_period)
        assert float(pd.to_numeric(fuel.loc[target_mask, lag_field], errors="coerce").iloc[0]) == pytest.approx(
            float(pd.to_numeric(fuel.loc[source_mask, "real_light_ruc_price_nzd_per_1000km"], errors="coerce").iloc[0]),
            rel=1e-12,
        )
        changed_cells.append(("LIGHT_RUC", target_period, lag_field))
    lag_outside = light_mask & ~fuel["canonical_period"].astype(str).isin(RUC_PRICE_LAGGED_EFFECT_PERIODS)
    np.testing.assert_allclose(
        pd.to_numeric(fuel.loc[lag_outside, lag_field], errors="coerce"),
        pd.to_numeric(base.loc[lag_outside, lag_field], errors="coerce"),
        rtol=0.0,
        atol=0.0,
    )

    assert len(changed_cells) == 42
    assert "light_ruc_nominal_rate_nzd_per_1000km" not in fuel.columns
    assert "heavy_ruc_nominal_rate_nzd_per_1000km" not in fuel.columns

    metadata = {"scenario_name", "role", "scenario_role", "scenario_display_name", "source_artifact"}
    price_fields = set(fuel_fields.values()) | {field for fields in ruc_fields.values() for field in fields} | {lag_field}
    for column in sorted(set(base.columns).intersection(fuel.columns) - metadata - price_fields):
        pd.testing.assert_series_equal(base[column], fuel[column], check_names=False, check_dtype=False)


def test_fixed_finalist_replay_matches_base_and_freezes_fuel_shock_checkpoints(fuel_replay) -> None:
    validation = fuel_replay.validation_report.set_index("scenario_name")
    assert set(validation.index) == {"current_basecase", FUEL_PRICE_SCENARIO_NAME}
    assert validation["valid"].all()
    assert set(validation["forecast_horizon_quarters"].astype(int)) == {100}
    assert set(validation["numeric_forecast_rows"].astype(int)) == {300}

    committed = pd.read_parquet(CHART_PATH)
    committed = committed[
        committed["scenario_name"].astype(str).eq("current_basecase")
        & committed["time_grain"].astype(str).eq("quarterly")
    ][["stream", "period", "value"]].rename(columns={"period": "target_period", "value": "committed"})
    replay_base = fuel_replay.future_forecasts[
        fuel_replay.future_forecasts["scenario_name"].astype(str).eq("current_basecase")
    ][["stream", "target_period", "forecast"]]
    parity = committed.merge(replay_base, on=["stream", "target_period"], how="left", validate="one_to_one")
    assert parity["forecast"].notna().all()
    np.testing.assert_allclose(parity["forecast"], parity["committed"], rtol=1e-12, atol=1e-8)

    expected = {
        ("PED", "2026Q1"): 1514.92355421614,
        ("PED", "2027Q3"): 1518.39284887138,
        ("LIGHT_RUC", "2026Q2"): 2820831871.591721,
        ("LIGHT_RUC", "2027Q3"): 3787073347.4069605,
        ("HEAVY_RUC", "2026Q3"): 967391517.7192788,
        ("HEAVY_RUC", "2027Q4"): 1042288979.404676,
    }
    fuel = fuel_replay.future_forecasts[
        fuel_replay.future_forecasts["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)
    ].set_index(["stream", "target_period"])
    base = fuel_replay.future_forecasts[
        fuel_replay.future_forecasts["scenario_name"].astype(str).eq("current_basecase")
    ].set_index(["stream", "target_period"])
    for key, value in expected.items():
        assert float(fuel.at[key, "forecast"]) == pytest.approx(value, rel=1e-11)
    # Every governed finalist reduces activity in every direct shock quarter.
    # This is the model response to real demand-price inputs; nominal revenue
    # rates are not repriced by the scenario.
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        for period in RUC_PRICE_SHOCK_PERIODS:
            assert float(fuel.at[(stream, period), "forecast"]) < float(base.at[(stream, period), "forecast"])

    # Annual RUC revenue factors exactly equal their associated net-km
    # factors. This is the positive proof that the bridge retains governed
    # nominal rates and changes revenue only through modelled activity.
    annual_factors = fuel_replay.annual_factors.pivot_table(
        index="june_year", columns="series_id", values="factor", aggfunc="first"
    )
    np.testing.assert_allclose(
        annual_factors["light_ruc_net_revenue"],
        annual_factors["light_ruc_net_km"],
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        annual_factors["heavy_ruc_net_revenue"],
        annual_factors["heavy_ruc_net_km"],
        rtol=1e-12,
        atol=1e-12,
    )

    # Direct price levels are back at Base from Q7. The Light explicit lag is
    # still elevated in 2027Q3, and lagged/nonlinear/recursive effects remain.
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        assert float(fuel.at[(stream, "2027Q3"), "forecast"]) != pytest.approx(
            float(base.at[(stream, "2027Q3"), "forecast"]), rel=1e-8
        )
    assert float(fuel.at[("LIGHT_RUC", "2027Q3"), "forecast"]) > float(base.at[("LIGHT_RUC", "2027Q3"), "forecast"])


def test_ar1_pack_replays_base_exactly_and_builds_the_six_quarter_fuel_scenario(ar1_fuel_replay) -> None:
    validation = ar1_fuel_replay.validation_report.set_index("scenario_name")
    assert set(validation.index) == {"current_basecase", FUEL_PRICE_SCENARIO_NAME}
    assert validation["valid"].all()
    assert set(validation["forecast_horizon_quarters"].astype(int)) == {100}
    assert set(validation["numeric_forecast_rows"].astype(int)) == {300}

    input_audit = ar1_fuel_replay.input_audit
    assert len(input_audit) == 42
    assert set(input_audit["canonical_period"].astype(str)) == set(FUEL_PRICE_SHOCK_PERIODS) | {"2027Q3"}
    assert set(input_audit["stream"].astype(str)) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    multiplier = pd.to_numeric(input_audit["multiplier"], errors="coerce")
    assert int(np.isclose(multiplier, FUEL_PRICE_MULTIPLIER).sum()) == 18
    assert int(np.isclose(multiplier, RUC_PRICE_MULTIPLIER).sum()) == 24

    committed = pd.read_parquet(AR1_CHART_PATH)
    committed = committed[
        committed["scenario_name"].astype(str).eq("current_basecase")
        & committed["time_grain"].astype(str).eq("quarterly")
    ][["stream", "period", "value"]].rename(columns={"period": "target_period", "value": "committed"})
    replay_base = ar1_fuel_replay.future_forecasts[
        ar1_fuel_replay.future_forecasts["scenario_name"].astype(str).eq("current_basecase")
    ][["stream", "target_period", "forecast"]]
    parity = committed.merge(replay_base, on=["stream", "target_period"], how="left", validate="one_to_one")
    assert parity["forecast"].notna().all()
    np.testing.assert_allclose(parity["forecast"], parity["committed"], rtol=1e-12, atol=1e-8)

    fuel = ar1_fuel_replay.future_forecasts[
        ar1_fuel_replay.future_forecasts["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)
    ].set_index(["stream", "target_period"])
    base = ar1_fuel_replay.future_forecasts[
        ar1_fuel_replay.future_forecasts["scenario_name"].astype(str).eq("current_basecase")
    ].set_index(["stream", "target_period"])
    # The input shock ends after 2027Q2, but the fixed AR(1) finalist retains
    # the expected dynamic carry-through once inputs return to Base.
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        assert float(fuel.at[(stream, "2027Q3"), "forecast"]) != pytest.approx(
            float(base.at[(stream, "2027Q3"), "forecast"]), rel=1e-8
        )


def test_append_creates_a_distinct_idempotent_trace_with_exact_replay_values_and_annual_bridge(fuel_replay) -> None:
    chart = pd.read_parquet(CHART_PATH)
    combined, audit = append_fuel_price_scenario_to_chart_rows(chart, fuel_replay)
    fuel_rows = combined[combined["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)]
    base_rows = chart[chart["scenario_name"].astype(str).eq("current_basecase")]

    assert len(fuel_rows) == len(base_rows) == 736
    assert set(fuel_rows["trace_name"].astype(str)) == {FUEL_PRICE_SCENARIO_TRACE_NAME}
    assert set(fuel_rows["scenario_role"].astype(str)) == {"comparison"}
    assert not audit.empty
    assert not fuel_rows.duplicated(["time_grain", "series_id", "period", "fed_path"]).any()

    replay_values = fuel_replay.future_forecasts[
        fuel_replay.future_forecasts["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)
    ][["stream", "target_period", "forecast"]]
    quarterly = fuel_rows[fuel_rows["time_grain"].astype(str).eq("quarterly")][
        ["stream", "period", "value", "_fuel_quarterly_reconciliation_delta"]
    ]
    exact = quarterly.merge(
        replay_values,
        left_on=["stream", "period"],
        right_on=["stream", "target_period"],
        how="left",
        validate="one_to_one",
    )
    assert exact["forecast"].notna().all()
    # The fixed-finalist replay is retained exactly as the core quarterly
    # layer. A separately tagged reconciliation layer is needed where the
    # governed annual bridge carries a longer composition effect than the
    # native quarterly finalist (e.g. Light RUC FY2029).
    np.testing.assert_allclose(
        pd.to_numeric(exact["value"], errors="coerce")
        - pd.to_numeric(exact["_fuel_quarterly_reconciliation_delta"], errors="coerce"),
        exact["forecast"],
        rtol=1e-12,
        atol=1e-8,
    )

    annual = _annual(combined, FUEL_PRICE_SCENARIO_NAME, 2027)
    assert float(annual.at["gross_ped_revenue", "value"]) == pytest.approx(2122.161303046585, rel=1e-11)
    assert float(annual.at["total_nltf_net_revenue", "value"]) == pytest.approx(4692.31036907831, rel=1e-11)

    # June-year mapping is explicit: FY2026 contains two direct-shock
    # quarters, FY2027 contains four, and FY2028 contains no direct shock.
    # Revenue falls during the two affected June years, then the fitted Light
    # RUC lag/nonlinear rebound lifts FY2028 above Base.
    for fy in (2026, 2027):
        base_annual = _annual(combined, "current_basecase", fy)
        scenario_annual = _annual(combined, FUEL_PRICE_SCENARIO_NAME, fy)
        assert float(scenario_annual.at["total_ruc_net_revenue", "value"]) < float(
            base_annual.at["total_ruc_net_revenue", "value"]
        )
        assert float(scenario_annual.at["total_nltf_net_revenue", "value"]) < float(
            base_annual.at["total_nltf_net_revenue", "value"]
        )
    base_2028 = _annual(combined, "current_basecase", 2028)
    scenario_2028 = _annual(combined, FUEL_PRICE_SCENARIO_NAME, 2028)
    assert float(scenario_2028.at["total_ruc_net_revenue", "value"]) > float(
        base_2028.at["total_ruc_net_revenue", "value"]
    )
    assert float(scenario_2028.at["total_nltf_net_revenue", "value"]) > float(
        base_2028.at["total_nltf_net_revenue", "value"]
    )

    # The dashboard's quarterly revenue view uses the Denton Base split plus
    # signed native-replay scenario deltas. It must keep the Iran-war trace,
    # leave pre-shock quarters unchanged and reconcile exactly back to every
    # annual total rather than presenting a second quarterly revenue model.
    from app import _disaggregate_annual_rows_to_quarterly

    annual_totals = fuel_rows[
        fuel_rows["time_grain"].astype(str).eq("june_year")
        & fuel_rows["series_id"].astype(str).eq("total_nltf_net_revenue")
        & pd.to_numeric(fuel_rows["june_year"], errors="coerce").isin([2026, 2027, 2028])
    ].copy()
    derived = _disaggregate_annual_rows_to_quarterly(annual_totals, combined)
    assert set(derived["scenario_name"].astype(str)) == {FUEL_PRICE_SCENARIO_NAME}
    assert set(derived["trace_name"].astype(str)) == {FUEL_PRICE_SCENARIO_TRACE_NAME}
    assert set(derived["data_scope"].astype(str)) == {
        "quarterly_disaggregated_from_annual_scenario_delta"
    }
    base_annual_totals = combined[
        combined["scenario_name"].astype(str).eq("current_basecase")
        & combined["time_grain"].astype(str).eq("june_year")
        & combined["series_id"].astype(str).eq("total_nltf_net_revenue")
        & pd.to_numeric(combined["june_year"], errors="coerce").isin([2026, 2027, 2028])
    ].copy()
    base_derived = _disaggregate_annual_rows_to_quarterly(base_annual_totals, combined)
    scenario_quarters = derived.set_index("period")["value"].map(float)
    base_quarters = base_derived.set_index("period")["value"].map(float)
    for period in ("2025Q3", "2025Q4"):
        assert scenario_quarters.loc[period] == pytest.approx(base_quarters.loc[period], abs=1e-9)
    for period in RUC_PRICE_SHOCK_PERIODS:
        assert scenario_quarters.loc[period] < base_quarters.loc[period]
    quarterly_sums = derived.groupby(pd.to_numeric(derived["june_year"], errors="coerce"))["value"].sum()
    annual_values = annual_totals.set_index(pd.to_numeric(annual_totals["june_year"], errors="coerce"))["value"]
    np.testing.assert_allclose(
        quarterly_sums.loc[[2026, 2027, 2028]],
        annual_values.loc[[2026, 2027, 2028]],
        rtol=0.0,
        atol=1e-6,
    )

    twice, _ = append_fuel_price_scenario_to_chart_rows(combined, fuel_replay)
    assert len(twice[twice["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)]) == len(fuel_rows)


def test_iran_trace_inherits_reconciled_uptake_base_plus_fixed_quarterly_deltas(fuel_replay) -> None:
    chart = pd.read_parquet(CHART_PATH)
    drift = pd.read_parquet(ROOT / "data/current_revenue_outlook/ev_phev_ped_light_drift_assumptions.parquet")
    uptake_rows, _ = apply_uptake_levers_to_chart_rows(
        chart,
        drift,
        EV_UPTAKE_PRESETS["MoT VFM base"],
        adjust_ped=True,
    )
    combined, audit = append_fuel_price_scenario_to_chart_rows(uptake_rows, fuel_replay)

    base = combined[
        combined["scenario_name"].astype(str).eq("current_basecase")
        & combined["time_grain"].astype(str).eq("quarterly")
    ][["series_id", "period", "value", "value_unit"]].rename(
        columns={"value": "base_value", "value_unit": "base_unit"}
    )
    iran = combined[
        combined["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)
        & combined["time_grain"].astype(str).eq("quarterly")
    ][["series_id", "period", "value", "value_unit", "_fuel_quarterly_reconciliation_delta"]].rename(
        columns={"value": "iran_value", "value_unit": "iran_unit"}
    )
    replay_delta = fuel_replay.quarterly_factors[["series_id", "period", "delta"]]
    comparison = base.merge(iran, on=["series_id", "period"], validate="one_to_one").merge(
        replay_delta,
        on=["series_id", "period"],
        validate="one_to_one",
    )
    display_scale = np.where(comparison["base_unit"].astype(str).str.contains("million", case=False), 1_000_000.0, 1.0)
    np.testing.assert_allclose(
        pd.to_numeric(comparison["iran_value"], errors="coerce")
        - pd.to_numeric(comparison["base_value"], errors="coerce"),
        pd.to_numeric(comparison["delta"], errors="coerce") / display_scale
        + pd.to_numeric(comparison["_fuel_quarterly_reconciliation_delta"], errors="coerce"),
        rtol=1e-12,
        atol=1e-8,
    )
    assert set(comparison.loc[comparison["series_id"].isin(["light_ruc_net_km", "heavy_ruc_net_km"]), "iran_unit"]) == {
        "million km"
    }

    # The quarterly bridge must not move the governed annual checkpoints.
    annual_factor = fuel_replay.annual_factors.set_index(["series_id", "june_year"])["factor"]
    for series_id in ("ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"):
        for fy in (2026, 2027, 2028, 2030):
            base_annual = _annual(combined, "current_basecase", fy)
            iran_annual = _annual(combined, FUEL_PRICE_SCENARIO_NAME, fy)
            assert float(iran_annual.at[series_id, "value"]) == pytest.approx(
                float(base_annual.at[series_id, "value"]) * float(annual_factor.at[(series_id, fy)]),
                rel=1e-12,
                abs=1e-10,
            )

    # Every visible native-activity June year equals the four fiscal quarters.
    # FY2026 includes two fixed actual quarters plus two forecast/scenario
    # quarters; subsequent years contain four scenario quarters.
    for scenario_name in ("current_basecase", FUEL_PRICE_SCENARIO_NAME):
        for series_id in ("ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"):
            for fy in (2026, 2027, 2028, 2030):
                annual = combined[
                    combined["scenario_name"].astype(str).eq(scenario_name)
                    & combined["series_id"].astype(str).eq(series_id)
                    & combined["time_grain"].astype(str).eq("june_year")
                    & pd.to_numeric(combined["june_year"], errors="coerce").eq(fy)
                ].iloc[0]
                scenario_quarters = combined[
                    combined["scenario_name"].astype(str).eq(scenario_name)
                    & combined["series_id"].astype(str).eq(series_id)
                    & combined["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(combined["june_year"], errors="coerce").eq(fy)
                ]
                actual_quarters = combined[
                    combined["row_type"].astype(str).eq("historical_actual")
                    & combined["series_id"].astype(str).eq(series_id)
                    & combined["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(combined["june_year"], errors="coerce").eq(fy)
                ]
                quarters = pd.concat([actual_quarters, scenario_quarters], ignore_index=True)
                assert quarters["period"].astype(str).nunique() == 4
                annual_scale = 1_000_000.0 if "million" in str(annual["value_unit"]).lower() else 1.0
                quarter_total = sum(
                    float(row.value) * (1_000_000.0 if "million" in str(row.value_unit).lower() else 1.0)
                    for row in quarters.itertuples()
                )
                assert quarter_total == pytest.approx(float(annual["value"]) * annual_scale, rel=0.0, abs=1e-5)

    quarterly_audit = audit[audit["time_grain"].astype(str).eq("quarterly")]
    assert set(quarterly_audit["transformation_basis"].astype(str)).issubset(
        {
            "fixed_finalist_quarterly_replay_delta",
            "fixed_finalist_quarterly_replay_delta_plus_annual_reconciliation",
            "annual_bridge_only_quarterly_reconciliation",
        }
    )
    reconciled_audit = quarterly_audit[
        quarterly_audit["transformation_basis"].astype(str).str.endswith("plus_annual_reconciliation")
    ]
    assert not reconciled_audit.empty
    assert pd.to_numeric(
        reconciled_audit["quarterly_annual_reconciliation_delta"], errors="coerce"
    ).abs().gt(0).all()


def test_revenue_rollups_are_additive_and_fed_policy_baseline_remains_parallel(fuel_replay) -> None:
    chart = pd.read_parquet(CHART_PATH)
    delayed, _ = apply_fed_uplift_delay_to_chart_rows(
        chart,
        fed_uplift_delayed_factors(ROOT, chart),
        scenario_roles={"basecase", "comparison"},
    )
    combined, audit = append_fuel_price_scenario_to_chart_rows(delayed, fuel_replay)

    for fy in (2026, 2027):
        base = _annual(combined, "current_basecase", fy)
        fuel = _annual(combined, FUEL_PRICE_SCENARIO_NAME, fy)

        def delta(series_id: str) -> float:
            return float(fuel.at[series_id, "value"]) - float(base.at[series_id, "value"])

        ped_delta = delta("gross_ped_revenue")
        ruc_delta = sum(
            delta(series_id)
            for series_id in (
                "light_ruc_net_revenue",
                "light_bev_ruc_net_revenue",
                "phev_ruc_net_revenue",
                "heavy_ruc_net_revenue",
            )
        )
        assert delta("gross_fed_revenue") == pytest.approx(ped_delta, abs=1e-9)
        assert delta("net_fed_revenue") == pytest.approx(ped_delta, abs=1e-9)
        assert delta("total_ruc_net_revenue") == pytest.approx(ruc_delta, abs=1e-9)
        assert delta("total_fed_ruc_net_revenue") == pytest.approx(ped_delta + ruc_delta, abs=1e-9)
        assert delta("total_nltf_net_revenue") == pytest.approx(ped_delta + ruc_delta, abs=1e-9)
        assert delta("net_mvr_revenue") == pytest.approx(0.0, abs=1e-12)

    fy2027 = _annual(combined, FUEL_PRICE_SCENARIO_NAME, 2027)
    for series_id in ("gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue", "total_nltf_net_revenue"):
        row = fy2027.loc[series_id]
        assert row["_fed_policy"] == "delay_6m"
        assert row["_fed_affected_quarters"] == "2027Q1;2027Q2"
        assert float(row["value"]) == pytest.approx(
            float(row["_fed_baseline_value"]) + float(row["_fed_annual_delta"]), abs=1e-9
        )

    fuel_fy2027_audit = audit[
        audit["period"].astype(str).eq("FY2027")
        & audit["series_id"].astype(str).eq("total_nltf_net_revenue")
    ].iloc[0]
    assert fuel_fy2027_audit["transformation_basis"] == "additive_ped_and_ruc_leaf_delta"
    assert fuel_fy2027_audit["fed_policy"] == "delay_6m"
    assert float(fuel_fy2027_audit["adjusted_value"]) == pytest.approx(
        float(fuel_fy2027_audit["adjusted_published_fed_value"])
        + float(fuel_fy2027_audit["fed_policy_delta"]),
        abs=1e-9,
    )

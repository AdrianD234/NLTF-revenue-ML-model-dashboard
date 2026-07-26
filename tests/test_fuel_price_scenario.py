from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.fuel_price_scenario import (
    BASE_DELAYED_6M_SCENARIO_NAME,
    BASE_NO_UPLIFT_SCENARIO_NAME,
    BASE_PUBLISHED_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_TRACE_NAME,
    IRAN_WAR_DELAYED_6M_SCENARIO_NAME,
    IRAN_WAR_NO_UPLIFT_SCENARIO_NAME,
    POLICY_PATH_IDS,
    TreasuryBaselineMacroReplayResult,
    _validate_complete_numeric_replay,
    apply_treasury_macro_to_chart_rows,
    append_fuel_price_scenario_to_chart_rows,
    build_fuel_price_scenario_inputs,
    build_ruc_policy_scenario_inputs,
    run_fuel_price_scenario_replay,
    run_treasury_baseline_macro_replay,
)
from model_dashboard.conflict_fuel_paths import (
    CONFLICT_FUEL_SCENARIO_LEVELS,
    conflict_policy_variant_name,
    conflict_scenario_name,
    conflict_trace_name,
    load_conflict_fuel_price_paths,
    structural_overlay_scenario_ids,
)
from model_dashboard.forecast_runner import (
    ScenarioInputForecastReplayResult,
    replay_forecast_from_scenario_inputs,
)
from model_dashboard.ev_uptake_levers import (
    EV_UPTAKE_PRESETS,
    FED_AGGREGATE_SERIES,
    RUC_AGGREGATE_SERIES,
    TOTAL_AGGREGATE_SERIES,
    apply_uptake_levers_to_chart_rows,
)
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    apply_fed_uplift_delay_to_chart_rows,
    fed_policy_affected_periods,
    fed_policy_quarterly_factors,
    fed_uplift_delayed_factors,
    ped_quarterly_rate_schedules,
)


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
    return run_fuel_price_scenario_replay(
        scenario_inputs,
        repo_root=ROOT,
        engine="ensemble",
    )


@pytest.fixture(scope="module")
def ar1_fuel_replay():
    return run_fuel_price_scenario_replay(
        pd.read_parquet(AR1_INPUT_PATH),
        repo_root=ROOT,
        engine="ar1",
    )


@pytest.fixture(scope="module")
def ar1_treasury_macro_replay():
    return run_treasury_baseline_macro_replay(
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


def _scenario_input_index(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.set_index(["stream", "canonical_period"]).sort_index()


def _assert_governed_policy_demand_calibration(replay) -> None:
    expected = {
        "PED": (
            -0.144116582,
            "D266",
            "real_petrol_price_cents_per_litre",
            None,
        ),
        "LIGHT_RUC": (
            -0.12,
            "D267",
            "diesel_plus_ruc_cost_nzd_per_1000km",
            7.125,
        ),
        "HEAVY_RUC": (
            -0.10,
            "D268",
            "diesel_plus_ruc_cost_nzd_per_1000km",
            50.0,
        ),
    }
    raw_forecasts = replay.future_forecasts
    forecasts = raw_forecasts.set_index(
        ["scenario_name", "stream", "target_period"]
    )
    audit = replay.policy_demand_calibration_audit
    assert not audit.empty
    assert set(audit["policy_calibration_basis"].astype(str)) == {
        "governed_single_generalized_running_cost_elasticity"
    }
    target_scenarios = {
        BASE_DELAYED_6M_SCENARIO_NAME,
        BASE_NO_UPLIFT_SCENARIO_NAME,
        *(conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS),
        *(
            conflict_policy_variant_name(level, state)
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
            for state in (
                FED_POLICY_STATE_DELAYED_6M,
                FED_POLICY_STATE_NO_UPLIFT,
            )
        ),
    }
    target_rows = raw_forecasts[
        raw_forecasts["scenario_name"].astype(str).isin(target_scenarios)
    ]
    assert target_rows["demand_calibration_applied"].astype(bool).all()
    assert set(target_rows["demand_reference_scenario_name"].astype(str)) == {
        "current_basecase"
    }
    np.testing.assert_allclose(
        pd.to_numeric(target_rows["forecast"], errors="coerce"),
        pd.to_numeric(
            target_rows["demand_reference_forecast"], errors="coerce"
        )
        * np.power(
            pd.to_numeric(target_rows["demand_price_ratio"], errors="coerce"),
            pd.to_numeric(target_rows["demand_elasticity"], errors="coerce"),
        )
        * pd.to_numeric(
            target_rows["demand_gdp_model_factor"], errors="coerce"
        ),
        rtol=1e-12,
        atol=1e-9,
    )
    gdp_inputs = pd.to_numeric(
        target_rows["demand_gdp_input_level_factor"], errors="coerce"
    )
    gdp_factors = pd.to_numeric(
        target_rows["demand_gdp_model_factor"], errors="coerce"
    )
    identity_gdp = np.isclose(gdp_inputs, 1.0, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(
        gdp_factors.loc[identity_gdp],
        1.0,
        rtol=0.0,
        atol=0.0,
    )
    downside_gdp = gdp_inputs.lt(1.0 - 1e-12)
    assert gdp_factors.loc[downside_gdp].le(1.0).all()

    policy_scenarios = target_scenarios.difference(
        conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
    )
    for scenario_name in policy_scenarios:
        rows = raw_forecasts[
            raw_forecasts["scenario_name"].astype(str).eq(scenario_name)
        ]
        assert rows["policy_calibration_applied"].astype(bool).all()
        assert set(rows["policy_reference_scenario_name"].astype(str)) == {
            "current_basecase"
        }

    for scenario_name in target_scenarios:
        for stream, (
            elasticity,
            source_cell,
            generalized_field,
            diesel_intensity,
        ) in expected.items():
            row = forecasts.loc[(scenario_name, stream, "2027Q1")]
            assert row["demand_generalized_price_field"] == generalized_field
            assert float(row["demand_elasticity"]) == pytest.approx(elasticity)
            if diesel_intensity is None:
                assert pd.isna(row["demand_diesel_litres_per_100km"])
            else:
                assert float(
                    row["demand_diesel_litres_per_100km"]
                ) == pytest.approx(diesel_intensity)
                assert str(row["demand_intensity_source"]).startswith("https://")
                reference_cost = (
                    float(row["demand_reference_fuel_price_cpl"])
                    * diesel_intensity
                    / 10.0
                )
                variant_cost = (
                    float(row["demand_variant_fuel_price_cpl"])
                    * diesel_intensity
                    / 10.0
                )
                assert float(
                    row["demand_reference_fuel_cost_nzd_per_1000km"]
                ) == pytest.approx(reference_cost)
                assert float(
                    row["demand_variant_fuel_cost_nzd_per_1000km"]
                ) == pytest.approx(variant_cost)
                expected_ratio = (
                    variant_cost
                    + float(
                        row[
                            "demand_variant_ruc_price_nzd_per_1000km"
                        ]
                    )
                ) / (
                    reference_cost
                    + float(
                        row[
                            "demand_reference_ruc_price_nzd_per_1000km"
                        ]
                    )
                )
                assert float(row["demand_price_ratio"]) == pytest.approx(
                    expected_ratio, rel=1e-12
                )
            if scenario_name in policy_scenarios:
                assert row["policy_elasticity_source_cell"] == source_cell
                assert row["policy_elasticity_level"] == "Med"
                assert row["policy_elasticity_source_path"].endswith(
                    "sensitivity_seed_inputs.csv"
                )
                assert len(str(row["policy_elasticity_source_sha256"])) == 64

    validation = replay.policy_validation_report.set_index("scenario_name")
    # Only structural-overlay scenarios carry the pre-overlay validation basis.
    # Base is shown unmodified, so labelling it "before structural overlay"
    # would itself be wrong.
    overlay_scenarios = structural_overlay_scenario_ids()
    for scenario_name, basis in validation["model_validation_basis"].astype(str).items():
        expected_basis = (
            "raw_fitted_replay_before_structural_overlay"
            if str(scenario_name) in overlay_scenarios
            else "raw_fitted_replay"
        )
        assert basis == expected_basis, scenario_name
    assert not validation.loc[
        validation.index.astype(str).isin(overlay_scenarios),
        "component_forecasts_available",
    ].any()
    assert validation.loc[
        ~validation.index.astype(str).isin(overlay_scenarios),
        "component_forecasts_available",
    ].all()

    for scenario_name in policy_scenarios:
        expected_rows = len(
            raw_forecasts[
                raw_forecasts["scenario_name"].astype(str).eq(scenario_name)
            ]
        )
        assert (
            int(validation.at[scenario_name, "policy_post_calibration_rows"])
            == expected_rows
        )
        assert bool(validation.at[scenario_name, "policy_post_calibration_valid"])
        # The flag must be derived from measured residuals, not assigned.
        assert (
            float(
                validation.at[
                    scenario_name,
                    "policy_post_calibration_formula_tolerance_ratio",
                ]
            )
            <= 1.0
        )
        assert (
            float(
                validation.at[
                    scenario_name,
                    "policy_post_calibration_component_closure_tolerance_ratio",
                ]
            )
            <= 1.0
        )
        assert (
            int(
                validation.at[scenario_name, "policy_post_calibration_sign_breaches"]
            )
            == 0
        )

    # A scenario that was never calibrated is not "valid" - it is not applicable.
    base_row = validation.loc[BASE_PUBLISHED_SCENARIO_NAME]
    assert int(base_row["policy_post_calibration_rows"]) == 0
    assert not bool(base_row["policy_post_calibration_valid"])

    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        assert int(validation.at[scenario_name, "conflict_post_calibration_rows"]) > 0
        for stream, (
            elasticity,
            _source_cell,
            _generalized_field,
            _diesel_intensity,
        ) in expected.items():
            row = forecasts.loc[(scenario_name, stream, "2026Q4")]
            assert bool(row["conflict_calibration_applied"])
            assert row["demand_calibration_kind"] == "conflict"
            assert float(row["demand_elasticity"]) == pytest.approx(elasticity)
            expected_forecast = float(row["demand_reference_forecast"]) * float(
                row["demand_price_ratio"]
            ) ** float(row["demand_elasticity"]) * float(
                row["demand_gdp_model_factor"]
            )
            assert float(row["forecast"]) == pytest.approx(
                expected_forecast, rel=1e-12, abs=1e-9
            )
            assert float(row["forecast"]) < float(row["demand_reference_forecast"])

    # Conflict plus policy is one Base-referenced generalized-cost shock, not
    # two applications of the same diesel elasticity.
    combined = forecasts.loc[
        (
            conflict_policy_variant_name(
                "medium", FED_POLICY_STATE_DELAYED_6M
            ),
            "LIGHT_RUC",
            "2027Q1",
        )
    ]
    assert combined["demand_calibration_kind"] == "conflict_and_policy"
    actual = float(combined["forecast"])
    base_forecast = float(combined["demand_reference_forecast"])
    elasticity = float(combined["demand_elasticity"])
    sequential_proxy = base_forecast * float(
        combined["demand_fuel_price_ratio"]
    ) ** elasticity * float(combined["demand_ruc_price_ratio"]) ** elasticity
    sequential_proxy *= float(combined["demand_gdp_model_factor"])
    assert actual != pytest.approx(sequential_proxy, rel=1e-6)

    # Lower delayed-policy RUC cost raises activity relative to the matching
    # published conflict path, while diesel itself remains unchanged.
    published = forecasts.loc[
        (conflict_scenario_name("medium"), "LIGHT_RUC", "2027Q1")
    ]
    assert actual > float(published["forecast"])

    replay_inputs = replay.replay_inputs.set_index(
        ["scenario_name", "stream", "canonical_period"]
    ).sort_index()
    policy_sources = {
        BASE_DELAYED_6M_SCENARIO_NAME: "current_basecase",
        BASE_NO_UPLIFT_SCENARIO_NAME: "current_basecase",
    }
    policy_sources.update(
        {
            conflict_policy_variant_name(level, state): conflict_scenario_name(
                level
            )
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
            for state in (
                FED_POLICY_STATE_DELAYED_6M,
                FED_POLICY_STATE_NO_UPLIFT,
            )
        }
    )
    for variant_name, source_name in policy_sources.items():
        variant_rows = raw_forecasts[
            raw_forecasts["scenario_name"].astype(str).eq(variant_name)
        ].set_index(["stream", "target_period"]).sort_index()
        assert set(
            variant_rows[
                "demand_gdp_factor_source_scenario_name"
            ].astype(str)
        ) == {source_name}
        variant_factors = pd.to_numeric(
            variant_rows["demand_gdp_model_factor"], errors="coerce"
        )
        if source_name == "current_basecase":
            np.testing.assert_allclose(
                variant_factors,
                1.0,
                rtol=0.0,
                atol=0.0,
            )
            continue
        source_rows = raw_forecasts[
            raw_forecasts["scenario_name"].astype(str).eq(source_name)
        ].set_index(["stream", "target_period"]).sort_index()
        pd.testing.assert_index_equal(variant_rows.index, source_rows.index)
        np.testing.assert_allclose(
            variant_factors,
            pd.to_numeric(
                source_rows["demand_gdp_model_factor"], errors="coerce"
            ),
            rtol=0.0,
            atol=0.0,
        )

    for variant_name, source_name in policy_sources.items():
        for stream in ("LIGHT_RUC", "HEAVY_RUC"):
            variant = replay_inputs.loc[(variant_name, stream)]
            source = replay_inputs.loc[(source_name, stream)]
            np.testing.assert_allclose(
                pd.to_numeric(
                    variant["real_diesel_price_cents_per_litre"],
                    errors="coerce",
                ),
                pd.to_numeric(
                    source["real_diesel_price_cents_per_litre"],
                    errors="coerce",
                ),
                rtol=0.0,
                atol=0.0,
            )


def test_conflict_replay_rejects_partial_numeric_stream_coverage() -> None:
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


@pytest.mark.parametrize("level", CONFLICT_FUEL_SCENARIO_LEVELS)
def test_build_conflict_scenario_routes_petrol_and_diesel_without_ruc_tax_shock(
    scenario_inputs: pd.DataFrame,
    level: str,
) -> None:
    base = _ordered(scenario_inputs[scenario_inputs["role"].astype(str).eq("basecase")])
    fuel = _ordered(build_fuel_price_scenario_inputs(scenario_inputs, ROOT, level=level))
    path = load_conflict_fuel_price_paths(ROOT)
    path = path[path["severity"].astype(str).eq(level)].set_index("period")

    assert len(base) == len(fuel) == 300
    assert set(fuel["scenario_name"].astype(str)) == {conflict_scenario_name(level)}
    assert set(fuel["scenario_display_name"].astype(str)) == {conflict_trace_name(level)}
    assert set(fuel["conflict_fuel_severity"].astype(str)) == {level}
    assert not fuel["conflict_fed_12c_embedded"].astype(bool).any()

    fuel_fields = {
        "PED": ("real_petrol_price_cents_per_litre", "petrol_ratio"),
        "LIGHT_RUC": ("real_diesel_price_cents_per_litre", "diesel_ratio"),
        "HEAVY_RUC": ("real_diesel_price_cents_per_litre", "diesel_ratio"),
    }
    for stream, (field, ratio_field) in fuel_fields.items():
        for period, path_row in path.iterrows():
            mask = (
                fuel["stream"].astype(str).eq(stream)
                & fuel["canonical_period"].astype(str).eq(str(period))
            )
            base_value = float(pd.to_numeric(base.loc[mask, field], errors="coerce").iloc[0])
            fuel_value = float(pd.to_numeric(fuel.loc[mask, field], errors="coerce").iloc[0])
            assert fuel_value == pytest.approx(
                base_value * float(path_row[ratio_field]), rel=1e-12
            )

    # Conflict fuel prices never mutate RUC tax-price inputs or their derived
    # lag/lead helpers. Those move only when the separate policy overlay runs.
    ruc_price_fields = {
        "real_light_ruc_price_nzd_per_1000km",
        "lagged_real_light_ruc_price_nzd_per_1000km",
        "real_heavy_ruc_price_nzd_per_1000km",
        "lead_real_heavy_ruc_price_nzd_per_1000km",
    }
    for field in ruc_price_fields:
        np.testing.assert_allclose(
            pd.to_numeric(fuel[field], errors="coerce"),
            pd.to_numeric(base[field], errors="coerce"),
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        )

    convergence_period = {
        "low": "2027Q1",
        "medium": "2028Q1",
        "high": "2030Q4",
    }[level]
    converged = path.loc[convergence_period:]
    np.testing.assert_allclose(converged["petrol_ratio"], 1.0, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(converged["diesel_ratio"], 1.0, rtol=0.0, atol=1e-12)


def test_registry_ids_are_unique_and_legacy_alias_points_to_medium() -> None:
    published = [conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS]
    variants = [
        conflict_policy_variant_name(level, state)
        for level in CONFLICT_FUEL_SCENARIO_LEVELS
        for state in (FED_POLICY_STATE_DELAYED_6M, FED_POLICY_STATE_NO_UPLIFT)
    ]
    assert len(set(published)) == 3
    assert len(set(variants)) == 6
    assert set(published).isdisjoint(variants)
    assert FUEL_PRICE_SCENARIO_NAME == conflict_scenario_name("medium")
    assert FUEL_PRICE_SCENARIO_TRACE_NAME == conflict_trace_name("medium")
    assert IRAN_WAR_DELAYED_6M_SCENARIO_NAME == conflict_policy_variant_name(
        "medium", FED_POLICY_STATE_DELAYED_6M
    )
    assert IRAN_WAR_NO_UPLIFT_SCENARIO_NAME == conflict_policy_variant_name(
        "medium", FED_POLICY_STATE_NO_UPLIFT
    )


def test_delayed_policy_updates_ped_pump_price_uses_exact_ruc_ratio_and_rebuilds_light_lag(
    scenario_inputs: pd.DataFrame,
) -> None:
    base = scenario_inputs[scenario_inputs["role"].astype(str).eq("basecase")].copy()
    iran = build_fuel_price_scenario_inputs(scenario_inputs)
    base_delayed = build_ruc_policy_scenario_inputs(
        base,
        ROOT,
        policy_state=FED_POLICY_STATE_DELAYED_6M,
        scenario_name=BASE_DELAYED_6M_SCENARIO_NAME,
    )
    iran_delayed = build_ruc_policy_scenario_inputs(
        iran,
        ROOT,
        policy_state=FED_POLICY_STATE_DELAYED_6M,
        scenario_name=IRAN_WAR_DELAYED_6M_SCENARIO_NAME,
    )

    exact_factor = 0.70024 / 0.82024
    factors = fed_policy_quarterly_factors(ROOT, FED_POLICY_STATE_DELAYED_6M)
    assert factors["2027Q1"] == pytest.approx(exact_factor, rel=1e-15)
    assert factors["2027Q2"] == pytest.approx(exact_factor, rel=1e-15)
    assert all(
        value == pytest.approx(1.0, abs=1e-15)
        for period, value in factors.items()
        if period not in {"2027Q1", "2027Q2"}
    )

    ruc_fields = {
        "LIGHT_RUC": ("real_light_ruc_price_nzd_per_1000km",),
        "HEAVY_RUC": (
            "real_light_ruc_price_nzd_per_1000km",
            "real_heavy_ruc_price_nzd_per_1000km",
        ),
    }
    for source_rows, delayed_rows in ((base, base_delayed), (iran, iran_delayed)):
        source = _scenario_input_index(source_rows)
        delayed = _scenario_input_index(delayed_rows)

        # The fixed PED finalist consumes a real retail-price field. Apply the
        # nominal target/source pump-price ratio so the implicit deflator is
        # preserved; never subtract nominal cents directly from a real field.
        for period in source.loc["PED"].index.astype(str):
            source_real = float(
                source.at[
                    ("PED", period), "real_petrol_price_cents_per_litre"
                ]
            )
            delayed_real = float(
                delayed.at[
                    ("PED", period), "real_petrol_price_cents_per_litre"
                ]
            )
            if period in {"2027Q1", "2027Q2"}:
                source_nominal = float(
                    delayed.at[
                        ("PED", period), "policy_source_nominal_petrol_cpl"
                    ]
                )
                target_nominal = float(
                    delayed.at[
                        ("PED", period), "policy_target_nominal_petrol_cpl"
                    ]
                )
                policy_free_nominal = float(
                    delayed.at[
                        ("PED", period),
                        "policy_free_source_nominal_petrol_cpl",
                    ]
                )
                published_wedge = float(
                    delayed.at[
                        ("PED", period),
                        "policy_published_fed_wedge_nominal_cpl",
                    ]
                )
                assert published_wedge == pytest.approx(12.0, abs=1e-12)
                assert source_nominal == pytest.approx(
                    policy_free_nominal + published_wedge,
                    abs=1e-12,
                )
                assert target_nominal == pytest.approx(
                    policy_free_nominal,
                    abs=1e-12,
                )
                assert float(
                    delayed.at[
                        ("PED", period), "policy_petrol_wedge_nominal_cpl"
                    ]
                ) == pytest.approx(-12.0)
                assert delayed_real / source_real == pytest.approx(
                    target_nominal / source_nominal,
                    rel=1e-12,
                )
                assert float(
                    delayed.at[
                        ("PED", period), "policy_real_petrol_ratio"
                    ]
                ) == pytest.approx(
                    float(
                        delayed.at[
                            ("PED", period), "policy_nominal_petrol_ratio"
                        ]
                    ),
                    rel=1e-12,
                )
            else:
                assert delayed_real == pytest.approx(source_real, abs=1e-12)

        for stream, fields in ruc_fields.items():
            for field in fields:
                for period in source.loc[stream].index.astype(str):
                    source_value = float(pd.to_numeric(pd.Series([source.at[(stream, period), field]]), errors="coerce").iloc[0])
                    delayed_value = float(
                        pd.to_numeric(pd.Series([delayed.at[(stream, period), field]]), errors="coerce").iloc[0]
                    )
                    expected_factor = exact_factor if period in {"2027Q1", "2027Q2"} else 1.0
                    assert delayed_value == pytest.approx(source_value * expected_factor, rel=1e-12)

        # The Light finalist consumes an explicit one-quarter lag.  The two
        # changed current-price quarters must therefore feed Q2 and Q3.
        for source_period, target_period in (("2027Q1", "2027Q2"), ("2027Q2", "2027Q3")):
            assert float(delayed.at[("LIGHT_RUC", target_period), "lagged_real_light_ruc_price_nzd_per_1000km"]) == pytest.approx(
                float(delayed.at[("LIGHT_RUC", source_period), "real_light_ruc_price_nzd_per_1000km"]),
                rel=1e-12,
            )

    # The nominal FED wedge is converted through a target/source ratio after
    # the governed petrol path. The matching RUC policy factor applies only to
    # RUC tax-price inputs; diesel remains the committed conflict curve.
    iran_index = _scenario_input_index(iran)
    iran_delayed_index = _scenario_input_index(iran_delayed)
    for period in ("2027Q1", "2027Q2"):
        real_ratio = float(
            iran_delayed_index.at[
                ("PED", period), "real_petrol_price_cents_per_litre"
            ]
        ) / float(
            iran_index.at[
                ("PED", period), "real_petrol_price_cents_per_litre"
            ]
        )
        nominal_ratio = float(
            iran_delayed_index.at[
                ("PED", period), "policy_target_nominal_petrol_cpl"
            ]
        ) / float(
            iran_delayed_index.at[
                ("PED", period), "policy_source_nominal_petrol_cpl"
            ]
        )
        assert real_ratio == pytest.approx(
            nominal_ratio,
            rel=1e-12,
        )
        for stream in ("LIGHT_RUC", "HEAVY_RUC"):
            assert float(
                iran_delayed_index.at[
                    (stream, period), "real_diesel_price_cents_per_litre"
                ]
            ) == pytest.approx(
                float(
                    iran_index.at[
                        (stream, period), "real_diesel_price_cents_per_litre"
                    ]
                ),
                abs=1e-12,
            )
        for stream, fields in ruc_fields.items():
            for field in fields:
                assert float(iran_delayed_index.at[(stream, period), field]) == pytest.approx(
                    float(iran_index.at[(stream, period), field]) * exact_factor,
                    rel=1e-12,
                )

    # Heavy consumes both a Light-price lag and a Heavy-price lead. Rebuild
    # both from the adjusted current paths, including the anticipatory Q4 lead.
    for source_period, target_period in (("2027Q1", "2027Q2"), ("2027Q2", "2027Q3")):
        assert float(
            iran_delayed_index.at[
                ("HEAVY_RUC", target_period),
                "lagged_real_light_ruc_price_nzd_per_1000km",
            ]
        ) == pytest.approx(
            float(
                iran_delayed_index.at[
                    ("HEAVY_RUC", source_period),
                    "real_light_ruc_price_nzd_per_1000km",
                ]
            ),
            rel=1e-12,
        )
    for target_period, source_period in (("2026Q4", "2027Q1"), ("2027Q1", "2027Q2")):
        assert float(
            iran_delayed_index.at[
                ("HEAVY_RUC", target_period),
                "lead_real_heavy_ruc_price_nzd_per_1000km",
            ]
        ) == pytest.approx(
            float(
                iran_delayed_index.at[
                    ("HEAVY_RUC", source_period),
                    "real_heavy_ruc_price_nzd_per_1000km",
                ]
            ),
            rel=1e-12,
        )

    assert set(base_delayed["policy_path_id"].astype(str)) == {
        POLICY_PATH_IDS[BASE_DELAYED_6M_SCENARIO_NAME]
    }
    assert set(iran_delayed["policy_path_id"].astype(str)) == {
        POLICY_PATH_IDS[IRAN_WAR_DELAYED_6M_SCENARIO_NAME]
    }


def test_custom_fixed_period_ped_policy_factors_apply_to_both_ruc_streams_and_lag(
    scenario_inputs: pd.DataFrame,
) -> None:
    base = scenario_inputs[scenario_inputs["role"].astype(str).eq("basecase")].copy()
    factors = {"2028Q1": 0.90, "2028Q2": 1.10}
    custom = build_ruc_policy_scenario_inputs(
        base,
        ROOT,
        policy_state="temporary_ped_subsidy_then_uplift",
        scenario_name="temporary_ped_subsidy_then_uplift",
        quarterly_policy_factors=factors,
    )
    source = _scenario_input_index(base)
    adjusted = _scenario_input_index(custom)
    planned = pd.to_numeric(ped_quarterly_rate_schedules(ROOT)["planned"], errors="coerce")
    for period in ("2028Q1", "2028Q2", "2028Q3"):
        expected_delta = float(planned.at[period]) * (factors.get(period, 1.0) - 1.0) * 100.0
        source_real = float(
            source.at[("PED", period), "real_petrol_price_cents_per_litre"]
        )
        adjusted_real = float(
            adjusted.at[("PED", period), "real_petrol_price_cents_per_litre"]
        )
        if period in factors:
            source_nominal = float(
                adjusted.at[
                    ("PED", period), "policy_source_nominal_petrol_cpl"
                ]
            )
            target_nominal = float(
                adjusted.at[
                    ("PED", period), "policy_target_nominal_petrol_cpl"
                ]
            )
            assert target_nominal - source_nominal == pytest.approx(
                expected_delta,
                abs=1e-12,
            )
            assert adjusted_real / source_real == pytest.approx(
                target_nominal / source_nominal,
                rel=1e-12,
            )
        else:
            assert adjusted_real == pytest.approx(source_real, abs=0.0)
    fields_by_stream = {
        "LIGHT_RUC": ("real_light_ruc_price_nzd_per_1000km",),
        "HEAVY_RUC": (
            "real_light_ruc_price_nzd_per_1000km",
            "real_heavy_ruc_price_nzd_per_1000km",
        ),
    }
    for stream, fields in fields_by_stream.items():
        for field in fields:
            for period in ("2028Q1", "2028Q2", "2028Q3"):
                expected_factor = factors.get(period, 1.0)
                assert float(adjusted.at[(stream, period), field]) == pytest.approx(
                    float(source.at[(stream, period), field]) * expected_factor,
                    rel=1e-12,
                )
    for source_period, target_period in (("2028Q1", "2028Q2"), ("2028Q2", "2028Q3")):
        assert float(
            adjusted.at[
                ("LIGHT_RUC", target_period),
                "lagged_real_light_ruc_price_nzd_per_1000km",
            ]
        ) == pytest.approx(
            float(
                adjusted.at[
                    ("LIGHT_RUC", source_period),
                    "real_light_ruc_price_nzd_per_1000km",
                ]
            ),
            rel=1e-12,
        )
        assert float(
            adjusted.at[
                ("HEAVY_RUC", target_period),
                "lagged_real_light_ruc_price_nzd_per_1000km",
            ]
        ) == pytest.approx(
            float(
                adjusted.at[
                    ("HEAVY_RUC", source_period),
                    "real_light_ruc_price_nzd_per_1000km",
                ]
            ),
            rel=1e-12,
        )
    for target_period, source_period in (("2027Q4", "2028Q1"), ("2028Q1", "2028Q2")):
        assert float(
            adjusted.at[
                ("HEAVY_RUC", target_period),
                "lead_real_heavy_ruc_price_nzd_per_1000km",
            ]
        ) == pytest.approx(
            float(
                adjusted.at[
                    ("HEAVY_RUC", source_period),
                    "real_heavy_ruc_price_nzd_per_1000km",
                ]
            ),
            rel=1e-12,
        )
    assert set(custom["policy_state"].astype(str)) == {"temporary_ped_subsidy_then_uplift"}

    with pytest.raises(ValueError, match="requires quarterly_policy_factors"):
        build_ruc_policy_scenario_inputs(
            base,
            ROOT,
            policy_state="custom_without_schedule",
            scenario_name="invalid_custom_policy",
        )


def test_fixed_finalist_replay_preserves_base_and_orders_governed_conflict_paths(
    fuel_replay,
    scenario_inputs: pd.DataFrame,
) -> None:
    validation = fuel_replay.policy_validation_report.set_index("scenario_name")
    expected_scenarios = {
        "current_basecase",
        BASE_DELAYED_6M_SCENARIO_NAME,
        BASE_NO_UPLIFT_SCENARIO_NAME,
        *(conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS),
        *(
            conflict_policy_variant_name(level, state)
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
            for state in (FED_POLICY_STATE_DELAYED_6M, FED_POLICY_STATE_NO_UPLIFT)
        ),
    }
    assert set(validation.index) == expected_scenarios
    assert validation["valid"].all()
    assert set(validation["forecast_horizon_quarters"].astype(int)) == {100}
    assert set(validation["numeric_forecast_rows"].astype(int)) == {300}

    base_inputs = fuel_replay.treasury_base_inputs
    control = replay_forecast_from_scenario_inputs(
        base_inputs,
        repo_root=ROOT,
        engine="ensemble",
    ).future_forecasts[["stream", "target_period", "forecast"]]
    replay_base = fuel_replay.future_forecasts[
        fuel_replay.future_forecasts["scenario_name"].astype(str).eq("current_basecase")
    ][["stream", "target_period", "forecast"]]
    parity = control.merge(
        replay_base,
        on=["stream", "target_period"],
        suffixes=("_control", "_registry"),
        validate="one_to_one",
    )
    np.testing.assert_allclose(
        parity["forecast_registry"], parity["forecast_control"], rtol=0.0, atol=0.0
    )
    legacy_control = replay_forecast_from_scenario_inputs(
        scenario_inputs[scenario_inputs["role"].astype(str).eq("basecase")],
        repo_root=ROOT,
        engine="ensemble",
    ).future_forecasts[["stream", "target_period", "forecast"]]
    macro_delta = parity.merge(
        legacy_control,
        on=["stream", "target_period"],
        validate="one_to_one",
    )
    assert (
        pd.to_numeric(macro_delta["forecast_registry"], errors="coerce")
        - pd.to_numeric(macro_delta["forecast"], errors="coerce")
    ).abs().gt(1e-9).any()

    forecasts = fuel_replay.future_forecasts.set_index(
        ["scenario_name", "stream", "target_period"]
    )
    path = load_conflict_fuel_price_paths(ROOT)
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        level_path = path[path["severity"].astype(str).eq(level)].set_index("period")
        for stream, ratio_field in {
            "PED": "petrol_ratio",
            "LIGHT_RUC": "diesel_ratio",
            "HEAVY_RUC": "diesel_ratio",
        }.items():
            for period, row in level_path.iterrows():
                ratio = float(row[ratio_field])
                scenario_value = float(
                    forecasts.at[(scenario_name, stream, period), "forecast"]
                )
                base_value = float(
                    forecasts.at[("current_basecase", stream, period), "forecast"]
                )
                if ratio > 1.0 + 1e-12:
                    assert scenario_value < base_value
                elif np.isclose(ratio, 1.0, rtol=0.0, atol=1e-12):
                    # Once prices converge, only the matched model-native
                    # GDP response (including recursive carryover) remains.
                    gdp_factor = float(
                        forecasts.at[
                            (scenario_name, stream, period),
                            "demand_gdp_model_factor",
                        ]
                    )
                    assert scenario_value == pytest.approx(
                        base_value * gdp_factor, rel=1e-12, abs=1e-9
                    )

    # In the first prospective ordered quarter, higher fuel prices must
    # monotonically lower activity for every stream.
    for stream in ("PED", "LIGHT_RUC", "HEAVY_RUC"):
        ordered = [
            float(forecasts.at[(conflict_scenario_name(level), stream, "2026Q4"), "forecast"])
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
        ]
        assert ordered[0] >= ordered[1] >= ordered[2]

    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        factors = fuel_replay.annual_factors[
            fuel_replay.annual_factors["scenario_name"]
            .astype(str)
            .eq(conflict_scenario_name(level))
        ].pivot_table(
            index="june_year", columns="series_id", values="factor", aggfunc="first"
        )
        np.testing.assert_allclose(
            factors["light_ruc_net_revenue"],
            factors["light_ruc_net_km"],
            rtol=1e-12,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            factors["heavy_ruc_net_revenue"],
            factors["heavy_ruc_net_km"],
            rtol=1e-12,
            atol=1e-12,
        )


def test_policy_replay_builds_twelve_paths_with_formula_closed_net_ruc(
    fuel_replay,
) -> None:
    validation = fuel_replay.policy_validation_report.set_index("scenario_name")
    assert len(validation) == 12
    assert validation["valid"].all()
    assert set(validation["numeric_forecast_rows"].astype(int)) == {300}
    _assert_governed_policy_demand_calibration(fuel_replay)

    family_paths = {
        "baseline": (
            "baseline_published",
            "baseline_shifted_6m",
            "baseline_no_uplift",
        ),
        **{
            level: (
                f"{level}_published",
                f"{level}_shifted_6m",
                f"{level}_no_uplift",
            )
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
        },
    }
    all_paths = {path for paths in family_paths.values() for path in paths}
    bridge = fuel_replay.annual_bridge[
        fuel_replay.annual_bridge["policy_path_id"].astype(str).isin(all_paths)
    ].copy()
    assert set(bridge["policy_path_id"].astype(str)) == all_paths

    expected_pairs = {
        *(f"{level}_published" for level in CONFLICT_FUEL_SCENARIO_LEVELS),
        "baseline_delayed_6m",
        "baseline_no_uplift",
        *(
            pair
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
            for pair in (
                f"{level}_delayed_6m",
                f"{level}_vs_baseline_delayed_6m",
                f"{level}_no_uplift",
                f"{level}_vs_baseline_no_uplift",
            )
        ),
    }
    assert expected_pairs.issubset(
        set(fuel_replay.policy_pair_factors["pair_id"].astype(str))
    )

    replay_quarters = fuel_replay.future_forecasts.set_index(
        ["scenario_name", "stream", "target_period"]
    )
    scenario_families = [
        ("current_basecase", BASE_DELAYED_6M_SCENARIO_NAME),
        *(
            (
                conflict_scenario_name(level),
                conflict_policy_variant_name(level, FED_POLICY_STATE_DELAYED_6M),
            )
            for level in CONFLICT_FUEL_SCENARIO_LEVELS
        ),
    ]
    for published_name, delayed_name in scenario_families:
        for period in ("2027Q1", "2027Q2"):
            assert float(
                replay_quarters.at[(delayed_name, "PED", period), "forecast"]
            ) > float(replay_quarters.at[(published_name, "PED", period), "forecast"])
        published = fuel_replay.future_forecasts[
            fuel_replay.future_forecasts["scenario_name"]
            .astype(str)
            .eq(published_name)
            & fuel_replay.future_forecasts["target_period"]
            .astype(str)
            .ge("2027Q3")
        ].set_index(["stream", "target_period"])["forecast"].sort_index()
        delayed = fuel_replay.future_forecasts[
            fuel_replay.future_forecasts["scenario_name"]
            .astype(str)
            .eq(delayed_name)
            & fuel_replay.future_forecasts["target_period"]
            .astype(str)
            .ge("2027Q3")
        ].set_index(["stream", "target_period"])["forecast"].sort_index()
        pd.testing.assert_index_equal(published.index, delayed.index)
        np.testing.assert_allclose(
            pd.to_numeric(published, errors="coerce"),
            pd.to_numeric(delayed, errors="coerce"),
            rtol=0.0,
            atol=0.0,
        )

    # Policy begins in 2027Q1, so FY2026 remains bit-for-bit published.
    for published_id, delayed_id, _ in family_paths.values():
        published = bridge[
            bridge["policy_path_id"].astype(str).eq(published_id)
            & pd.to_numeric(bridge["FY"], errors="coerce").eq(2026)
        ].set_index(["series_id", "fed_path"])["value"].sort_index()
        delayed = bridge[
            bridge["policy_path_id"].astype(str).eq(delayed_id)
            & pd.to_numeric(bridge["FY"], errors="coerce").eq(2026)
        ].set_index(["series_id", "fed_path"])["value"].sort_index()
        if not published.empty or not delayed.empty:
            pd.testing.assert_index_equal(published.index, delayed.index)
            np.testing.assert_allclose(published, delayed, rtol=0.0, atol=0.0)

    ruc_leaves = (
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "heavy_bev_ruc_net_revenue",
    )
    required = {*ruc_leaves, "ruc_admin_revenue", "total_ruc_net_revenue"}
    available_by_path = {
        path_id: set(
            pd.to_numeric(
                bridge.loc[
                    bridge["policy_path_id"].astype(str).eq(path_id), "FY"
                ],
                errors="coerce",
            )
            .dropna()
            .astype(int)
        )
        for path_id in all_paths
    }
    common_fys = set.intersection(*available_by_path.values()).intersection(
        range(2026, 2031)
    )
    assert common_fys == set(range(2026, 2031))
    for path_id in all_paths:
        for fy in sorted(common_fys):
            rows = bridge[
                bridge["policy_path_id"].astype(str).eq(path_id)
                & pd.to_numeric(bridge["FY"], errors="coerce").eq(fy)
            ].set_index("series_id")
            assert required.issubset(rows.index)
            value = pd.to_numeric(rows["value"], errors="coerce")
            leaves = sum(float(value.at[series_id]) for series_id in ruc_leaves)
            assert float(value.at["total_ruc_net_revenue"]) == pytest.approx(
                leaves - float(value.at["ruc_admin_revenue"]), abs=1e-9
            )

    # Diesel-price elasticities apply to conventional ICE activity only. The
    # annual migration bridge must not leak those volume changes into electric
    # classes. Policy paths then reprice each electric revenue leaf once.
    electric_pairs = {
        "light_bev_ruc_net_km": "light_bev_ruc_net_revenue",
        "phev_ruc_net_km": "phev_ruc_net_revenue",
        "heavy_bev_ruc_net_km": "heavy_bev_ruc_net_revenue",
    }
    for fy in sorted(common_fys):
        base = bridge[
            bridge["policy_path_id"].astype(str).eq("baseline_published")
            & pd.to_numeric(bridge["FY"], errors="coerce").eq(fy)
        ].set_index("series_id")
        for path_id in all_paths:
            rows = bridge[
                bridge["policy_path_id"].astype(str).eq(path_id)
                & pd.to_numeric(bridge["FY"], errors="coerce").eq(fy)
            ].set_index("series_id")
            for activity, revenue in electric_pairs.items():
                assert float(rows.at[activity, "value"]) == pytest.approx(
                    float(base.at[activity, "value"]),
                    rel=0.0,
                    abs=0.0,
                )
                rate_factor = float(rows.at[revenue, "policy_rate_factor"])
                assert float(rows.at[revenue, "value"]) == pytest.approx(
                    float(base.at[revenue, "value"]) * rate_factor,
                    rel=1e-12,
                    abs=1e-9,
                )
            assert (
                float(rows.at["light_ruc_net_km", "value"])
                - float(base.at["light_ruc_net_km", "value"])
            ) == pytest.approx(
                float(
                    rows.at[
                        "current_light_ruc_total_modelled_km", "value"
                    ]
                )
                - float(
                    base.at[
                        "current_light_ruc_total_modelled_km", "value"
                    ]
                ),
                rel=1e-12,
                abs=1e-9,
            )

    # Delayed and off inputs are identical through FY2027, then diverge.
    for _, delayed_id, off_id in family_paths.values():
        for fy in (2026, 2027):
            delayed = bridge[
                bridge["policy_path_id"].astype(str).eq(delayed_id)
                & pd.to_numeric(bridge["FY"], errors="coerce").eq(fy)
            ].set_index(["series_id", "fed_path"])["value"].sort_index()
            off = bridge[
                bridge["policy_path_id"].astype(str).eq(off_id)
                & pd.to_numeric(bridge["FY"], errors="coerce").eq(fy)
            ].set_index(["series_id", "fed_path"])["value"].sort_index()
            pd.testing.assert_index_equal(delayed.index, off.index)
            np.testing.assert_allclose(delayed, off, rtol=0.0, atol=1e-9)


def test_ar1_pack_replays_twelve_paths_and_retains_source_lineage(
    ar1_fuel_replay,
) -> None:
    _assert_governed_policy_demand_calibration(ar1_fuel_replay)
    validation = ar1_fuel_replay.policy_validation_report.set_index("scenario_name")
    assert len(validation) == 12
    assert validation["valid"].all()
    assert set(validation["forecast_horizon_quarters"].astype(int)) == {100}
    assert set(validation["numeric_forecast_rows"].astype(int)) == {300}

    input_audit = ar1_fuel_replay.input_audit
    assert len(input_audit) == 3 * 20 * 3
    assert set(input_audit["severity"].astype(str)) == set(
        CONFLICT_FUEL_SCENARIO_LEVELS
    )
    assert set(input_audit["canonical_period"].astype(str)) == {
        f"{year}Q{quarter}"
        for year in range(2026, 2031)
        for quarter in range(1, 5)
    }
    assert set(input_audit["stream"].astype(str)) == {"PED", "LIGHT_RUC", "HEAVY_RUC"}
    assert not input_audit["fed_12c_embedded"].astype(bool).any()
    assert set(input_audit["field"].astype(str)) == {
        "real_petrol_price_cents_per_litre",
        "real_diesel_price_cents_per_litre",
    }
    np.testing.assert_allclose(
        pd.to_numeric(input_audit["multiplier"], errors="coerce"),
        pd.to_numeric(input_audit["configured_ratio"], errors="coerce"),
        rtol=1e-12,
        atol=1e-12,
    )

    all_paths = set(POLICY_PATH_IDS.values())
    bridge = ar1_fuel_replay.annual_bridge[
        ar1_fuel_replay.annual_bridge["policy_path_id"].astype(str).isin(all_paths)
    ].copy()
    assert set(bridge["policy_path_id"].astype(str)) == all_paths
    ruc_leaves = (
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "heavy_bev_ruc_net_revenue",
    )
    required = {*ruc_leaves, "ruc_admin_revenue", "total_ruc_net_revenue"}
    for path_id in all_paths:
        available_fys = set(
            pd.to_numeric(
                bridge.loc[
                    bridge["policy_path_id"].astype(str).eq(path_id), "FY"
                ],
                errors="coerce",
            )
            .dropna()
            .astype(int)
        )
        assert set(range(2026, 2031)).issubset(available_fys)
        for fy in range(2026, 2031):
            rows = bridge[
                bridge["policy_path_id"].astype(str).eq(path_id)
                & pd.to_numeric(bridge["FY"], errors="coerce").eq(fy)
            ].set_index("series_id")
            assert required.issubset(rows.index)
            value = pd.to_numeric(rows["value"], errors="coerce")
            leaves = sum(float(value.at[series_id]) for series_id in ruc_leaves)
            assert float(value.at["total_ruc_net_revenue"]) == pytest.approx(
                leaves - float(value.at["ruc_admin_revenue"]), abs=1e-9
            )

    ar1_inputs = pd.read_parquet(AR1_INPUT_PATH)
    control = replay_forecast_from_scenario_inputs(
        ar1_fuel_replay.treasury_base_inputs,
        repo_root=ROOT,
        engine="ar1",
    ).future_forecasts[["stream", "target_period", "forecast"]]
    replay_base = ar1_fuel_replay.future_forecasts[
        ar1_fuel_replay.future_forecasts["scenario_name"].astype(str).eq("current_basecase")
    ][["stream", "target_period", "forecast"]]
    parity = control.merge(
        replay_base,
        on=["stream", "target_period"],
        suffixes=("_control", "_registry"),
        validate="one_to_one",
    )
    np.testing.assert_allclose(
        parity["forecast_registry"], parity["forecast_control"], rtol=0.0, atol=0.0
    )


def test_ensemble_append_fails_closed_when_direct_conflict_fy_is_missing(
    fuel_replay,
) -> None:
    chart = pd.read_parquet(CHART_PATH)
    incomplete_factors = pd.concat(
        [
            fuel_replay.quarterly_factors,
            fuel_replay.annual_factors[
                ~pd.to_numeric(
                    fuel_replay.annual_factors["june_year"], errors="coerce"
                ).eq(2026)
            ],
        ],
        ignore_index=True,
        sort=False,
    )
    with pytest.raises(
        ValueError,
        match=r"direct quarterly effects in FY2026.*Refusing to default",
    ):
        append_fuel_price_scenario_to_chart_rows(chart, incomplete_factors)


def test_independent_treasury_macro_replay_builds_factors_without_changing_prices(
    ar1_treasury_macro_replay,
) -> None:
    result = ar1_treasury_macro_replay
    assert isinstance(result, TreasuryBaselineMacroReplayResult)
    assert result.base_scenario_name == "current_basecase"
    assert not result.baseline_macro_quarterly_factors.empty
    assert not result.baseline_macro_annual_factors.empty

    for factors in (
        result.baseline_macro_quarterly_factors,
        result.baseline_macro_annual_factors,
    ):
        numeric = pd.to_numeric(factors["factor"], errors="coerce")
        assert numeric.notna().all()
        assert np.isfinite(numeric).all()
        assert numeric.gt(0).all()
        assert numeric.sub(1.0).abs().gt(1e-9).any()

    original = pd.read_parquet(AR1_INPUT_PATH)
    original = original[
        original["scenario_name"].astype(str).eq(result.base_scenario_name)
    ].copy()
    treasury = result.treasury_base_inputs.copy()
    keys = ["stream", "canonical_period"]
    price_columns = [
        "real_petrol_price_cents_per_litre",
        "real_diesel_price_cents_per_litre",
        "real_light_ruc_price_nzd_per_1000km",
        "real_heavy_ruc_price_nzd_per_1000km",
        "log_real_petrol_price",
        "log_real_diesel_price",
        "log_real_light_ruc_price",
        "log_real_heavy_ruc_price",
    ]
    comparison = original[keys + price_columns].merge(
        treasury[keys + price_columns],
        on=keys,
        how="outer",
        suffixes=("_original", "_treasury"),
        validate="one_to_one",
        indicator=True,
    )
    assert set(comparison["_merge"].astype(str)) == {"both"}
    for column in price_columns:
        np.testing.assert_allclose(
            pd.to_numeric(comparison[f"{column}_treasury"], errors="coerce"),
            pd.to_numeric(comparison[f"{column}_original"], errors="coerce"),
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        )


def _treasury_macro_replay_stub(
    annual_factors: dict[str, float],
) -> TreasuryBaselineMacroReplayResult:
    return TreasuryBaselineMacroReplayResult(
        base_scenario_name="current_basecase",
        treasury_base_inputs=pd.DataFrame(),
        replay_inputs=pd.DataFrame(),
        replay=None,
        baseline_macro_quarterly_factors=pd.DataFrame(
            [
                {
                    "series_id": "ped_vkt_per_capita",
                    "period": "2026Q3",
                    "factor": 1.0,
                }
            ]
        ),
        baseline_macro_annual_factors=pd.DataFrame(
            [
                {
                    "series_id": series_id,
                    "june_year": 2027,
                    "factor": factor,
                }
                for series_id, factor in annual_factors.items()
            ]
        ),
    )


def _compact_macro_annual_rows(
    values_by_scenario: dict[str, dict[str, float]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_name, values in values_by_scenario.items():
        for series_id, value in values.items():
            rows.append(
                {
                    "scenario_name": scenario_name,
                    "scenario_role": (
                        "basecase"
                        if scenario_name == "current_basecase"
                        else "comparison"
                    ),
                    "trace_name": scenario_name,
                    "time_grain": "june_year",
                    "period": "FY2027",
                    "june_year": 2027,
                    "series_id": series_id,
                    "value": value,
                    "fed_path": "published_12c",
                }
            )
    return pd.DataFrame(rows)


def test_treasury_macro_compact_annual_rollups_preserve_hidden_components() -> None:
    source = _compact_macro_annual_rows(
        {
            "current_basecase": {
                "gross_ped_revenue": 100.0,
                "gross_fed_revenue": 115.0,
                "net_fed_revenue": 108.0,
                "gross_ruc_revenue": 215.0,
                "ruc_revenue_net_admin": 210.0,
                "total_ruc_net_revenue": 200.0,
                "total_fed_ruc_net_revenue": 308.0,
                "total_gross_revenue": 390.0,
                "total_revenue_net_admin": 370.0,
                "total_nltf_net_revenue": 360.0,
            },
            "current_comparison_1": {
                "gross_ped_revenue": 120.0,
                "gross_fed_revenue": 135.0,
                "net_fed_revenue": 128.0,
                "gross_ruc_revenue": 265.0,
                "ruc_revenue_net_admin": 260.0,
                "total_ruc_net_revenue": 250.0,
                "total_fed_ruc_net_revenue": 378.0,
                "total_gross_revenue": 460.0,
                "total_revenue_net_admin": 440.0,
                "total_nltf_net_revenue": 430.0,
            },
        }
    )
    factors = {
        series_id: 1.25
        for series_id in source["series_id"].astype(str).unique()
    }
    factors["gross_ped_revenue"] = 1.10
    factors["total_ruc_net_revenue"] = 0.95
    adjusted, audit = apply_treasury_macro_to_chart_rows(
        source,
        _treasury_macro_replay_stub(factors),
    )

    assert not audit.empty
    for scenario_name in ("current_basecase", "current_comparison_1"):
        before = source[
            source["scenario_name"].astype(str).eq(scenario_name)
        ].set_index("series_id")["value"].astype(float)
        after = adjusted[
            adjusted["scenario_name"].astype(str).eq(scenario_name)
        ].set_index("series_id")["value"].astype(float)
        ped_delta = after["gross_ped_revenue"] - before["gross_ped_revenue"]
        ruc_delta = (
            after["total_ruc_net_revenue"]
            - before["total_ruc_net_revenue"]
        )

        for series_id in FED_AGGREGATE_SERIES:
            assert after[series_id] - before[series_id] == pytest.approx(
                ped_delta
            )
        for series_id in RUC_AGGREGATE_SERIES:
            assert after[series_id] - before[series_id] == pytest.approx(
                ruc_delta
            )
        for series_id in TOTAL_AGGREGATE_SERIES:
            assert after[series_id] - before[series_id] == pytest.approx(
                ped_delta + ruc_delta
            )

        assert (
            after["gross_fed_revenue"] - after["gross_ped_revenue"]
        ) == pytest.approx(
            before["gross_fed_revenue"] - before["gross_ped_revenue"]
        )
        assert (
            after["gross_fed_revenue"] - after["net_fed_revenue"]
        ) == pytest.approx(
            before["gross_fed_revenue"] - before["net_fed_revenue"]
        )
        assert (
            after["gross_ruc_revenue"] - after["ruc_revenue_net_admin"]
        ) == pytest.approx(
            before["gross_ruc_revenue"]
            - before["ruc_revenue_net_admin"]
        )
        assert (
            after["ruc_revenue_net_admin"]
            - after["total_ruc_net_revenue"]
        ) == pytest.approx(
            before["ruc_revenue_net_admin"]
            - before["total_ruc_net_revenue"]
        )
        assert after["total_fed_ruc_net_revenue"] == pytest.approx(
            after["net_fed_revenue"] + after["total_ruc_net_revenue"]
        )
        assert (
            after["total_nltf_net_revenue"]
            - after["total_fed_ruc_net_revenue"]
        ) == pytest.approx(
            before["total_nltf_net_revenue"]
            - before["total_fed_ruc_net_revenue"]
        )


def test_treasury_macro_partial_total_keeps_direct_factor_without_ruc_anchor() -> None:
    source = _compact_macro_annual_rows(
        {
            "current_basecase": {
                "gross_ped_revenue": 100.0,
                "total_nltf_net_revenue": 360.0,
            }
        }
    )
    adjusted, _ = apply_treasury_macro_to_chart_rows(
        source,
        _treasury_macro_replay_stub(
            {
                "gross_ped_revenue": 1.10,
                "total_nltf_net_revenue": 1.20,
            }
        ),
    )
    values = adjusted.set_index("series_id")

    assert float(values.at["gross_ped_revenue", "value"]) == pytest.approx(
        110.0
    )
    assert float(values.at["total_nltf_net_revenue", "value"]) == pytest.approx(
        432.0
    )
    assert (
        values.at["total_nltf_net_revenue", "_treasury_macro_basis"]
        == "Treasury_BEFU26_annual_bridge_macro_factor"
    )


@pytest.mark.parametrize(
    "anchor_series",
    ("gross_ped_revenue", "total_ruc_net_revenue"),
)
def test_treasury_macro_present_anchor_without_factor_fails_closed(
    anchor_series: str,
) -> None:
    source = _compact_macro_annual_rows(
        {"current_basecase": {anchor_series: 100.0}}
    )

    with pytest.raises(
        ValueError,
        match=rf"{anchor_series}/FY2027",
    ):
        apply_treasury_macro_to_chart_rows(
            source,
            _treasury_macro_replay_stub({"net_mvr_revenue": 1.0}),
        )


def test_treasury_macro_overlay_updates_current_base_and_comparison_only(
    ar1_treasury_macro_replay,
) -> None:
    source = pd.read_parquet(AR1_CHART_PATH)
    adjusted, audit = apply_treasury_macro_to_chart_rows(
        source, ar1_treasury_macro_replay
    )

    assert not audit.empty
    assert {"current_basecase", "current_comparison_1"}.issubset(
        set(audit["scenario_name"].astype(str))
    )
    current_mask = (
        adjusted["scenario_role"].fillna("").astype(str).isin(
            {"basecase", "comparison"}
        )
        & adjusted["scenario_name"]
        .astype(str)
        .isin({"current_basecase", "current_comparison_1"})
    )
    for scenario_name in ("current_basecase", "current_comparison_1"):
        scenario = adjusted[
            current_mask
            & adjusted["scenario_name"].astype(str).eq(scenario_name)
        ]
        assert not scenario.empty
        assert scenario["treasury_macro_applied"].fillna(False).astype(bool).any()

    protected_mask = (
        source["scenario_role"].fillna("").astype(str).isin(
            {"actual", "official_comparator"}
        )
        | source["scenario_name"]
        .astype(str)
        .isin({"actual", "historical_actual", "mbu26_official"})
    )
    pd.testing.assert_series_equal(
        adjusted.loc[protected_mask, "value"].reset_index(drop=True),
        source.loc[protected_mask, "value"].reset_index(drop=True),
        check_names=False,
        check_dtype=False,
    )
    assert not adjusted.loc[
        protected_mask, "treasury_macro_applied"
    ].fillna(False).astype(bool).any()

    expected_factor = (
        ar1_treasury_macro_replay.baseline_macro_annual_factors[
            ar1_treasury_macro_replay.baseline_macro_annual_factors[
                "series_id"
            ]
            .astype(str)
            .eq("light_ruc_net_km")
            & pd.to_numeric(
                ar1_treasury_macro_replay.baseline_macro_annual_factors[
                    "june_year"
                ],
                errors="coerce",
            ).eq(2030)
        ]["factor"]
        .astype(float)
        .iloc[0]
    )
    for scenario_name in ("current_basecase", "current_comparison_1"):
        selector = (
            source["scenario_name"].astype(str).eq(scenario_name)
            & source["time_grain"].astype(str).eq("june_year")
            & source["series_id"].astype(str).eq("light_ruc_net_km")
            & pd.to_numeric(source["june_year"], errors="coerce").eq(2030)
        )
        assert selector.sum() == 1
        source_value = float(source.loc[selector, "value"].iloc[0])
        adjusted_value = float(adjusted.loc[selector, "value"].iloc[0])
        assert adjusted_value == pytest.approx(
            source_value * expected_factor, rel=1e-12, abs=1e-9
        )


def test_treasury_macro_before_uptake_preserves_quarterly_annual_reconciliation(
    ar1_treasury_macro_replay,
) -> None:
    chart, macro_audit = apply_treasury_macro_to_chart_rows(
        pd.read_parquet(AR1_CHART_PATH), ar1_treasury_macro_replay
    )
    assert not macro_audit.empty
    drift = pd.read_parquet(
        ROOT
        / "data/current_revenue_outlook/ev_phev_ped_light_drift_assumptions.parquet"
    )
    adjusted, uptake_audit = apply_uptake_levers_to_chart_rows(
        chart,
        drift,
        EV_UPTAKE_PRESETS["MoT VFM base"],
        adjust_ped=True,
    )
    assert not uptake_audit.empty

    for scenario_name in ("current_basecase", "current_comparison_1"):
        for series_id in (
            "ped_vkt_per_capita",
            "light_ruc_net_km",
            "heavy_ruc_net_km",
        ):
            for fy in (2027, 2028, 2030):
                annual = adjusted[
                    adjusted["scenario_name"].astype(str).eq(scenario_name)
                    & adjusted["series_id"].astype(str).eq(series_id)
                    & adjusted["time_grain"].astype(str).eq("june_year")
                    & pd.to_numeric(
                        adjusted["june_year"], errors="coerce"
                    ).eq(fy)
                ]
                quarters = adjusted[
                    adjusted["scenario_name"].astype(str).eq(scenario_name)
                    & adjusted["series_id"].astype(str).eq(series_id)
                    & adjusted["time_grain"].astype(str).eq("quarterly")
                    & pd.to_numeric(
                        adjusted["june_year"], errors="coerce"
                    ).eq(fy)
                ]
                assert len(annual) == 1
                assert quarters["period"].astype(str).nunique() == 4
                annual_row = annual.iloc[0]
                annual_scale = (
                    1_000_000.0
                    if "million" in str(annual_row["value_unit"]).lower()
                    else 1.0
                )
                quarter_total = sum(
                    float(row.value)
                    * (
                        1_000_000.0
                        if "million" in str(row.value_unit).lower()
                        else 1.0
                    )
                    for row in quarters.itertuples()
                )
                assert quarter_total == pytest.approx(
                    float(annual_row["value"]) * annual_scale,
                    rel=0.0,
                    abs=1e-5,
                )


def test_append_creates_three_distinct_idempotent_traces_with_exact_replay_values_and_annual_bridge(
    ar1_fuel_replay,
) -> None:
    chart = pd.read_parquet(AR1_CHART_PATH)
    chart, macro_audit = apply_treasury_macro_to_chart_rows(
        chart, ar1_fuel_replay
    )
    assert not macro_audit.empty
    combined, audit = append_fuel_price_scenario_to_chart_rows(chart, ar1_fuel_replay)
    base_rows = chart[chart["scenario_name"].astype(str).eq("current_basecase")]

    assert not audit.empty
    assert set(audit["severity"].astype(str)) == set(CONFLICT_FUEL_SCENARIO_LEVELS)

    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        fuel_rows = combined[combined["scenario_name"].astype(str).eq(scenario_name)]
        assert len(fuel_rows) == len(base_rows) == 736
        assert set(fuel_rows["trace_name"].astype(str)) == {conflict_trace_name(level)}
        assert set(fuel_rows["scenario_role"].astype(str)) == {"comparison"}
        assert set(fuel_rows["conflict_fuel_severity"].astype(str)) == {level}
        assert not fuel_rows.duplicated(
            ["time_grain", "series_id", "period", "fed_path"]
        ).any()

        replay_values = ar1_fuel_replay.future_forecasts[
            ar1_fuel_replay.future_forecasts["scenario_name"].astype(str).eq(
                scenario_name
            )
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
        # The structural elasticity result is the native quarterly layer.
        # A separately tagged reconciliation layer bridges it back to the
        # governed annual checkpoints.
        np.testing.assert_allclose(
            pd.to_numeric(exact["value"], errors="coerce")
            - pd.to_numeric(
                exact["_fuel_quarterly_reconciliation_delta"], errors="coerce"
            ),
            exact["forecast"],
            rtol=1e-12,
            atol=1e-8,
        )

        expected_factors = ar1_fuel_replay.annual_factors[
            ar1_fuel_replay.annual_factors["scenario_name"]
            .astype(str)
            .eq(scenario_name)
        ]
        visible_series = set(
            fuel_rows[fuel_rows["time_grain"].astype(str).eq("june_year")][
                "series_id"
            ].astype(str)
        )
        for fy in range(2026, 2031):
            annual = _annual(combined, scenario_name, fy)
            base_annual = _annual(chart, "current_basecase", fy)
            expected = expected_factors[
                pd.to_numeric(expected_factors["june_year"], errors="coerce").eq(fy)
            ].set_index("series_id")
            direct_factor_series = visible_series.difference(
                set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
            )
            for series_id in direct_factor_series.intersection(expected.index):
                assert float(annual.at[series_id, "value"]) == pytest.approx(
                    float(base_annual.at[series_id, "value"])
                    * float(expected.at[series_id, "factor"]),
                    abs=1e-9,
                )

    twice, _ = append_fuel_price_scenario_to_chart_rows(
        combined, ar1_fuel_replay
    )
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        assert len(twice[twice["scenario_name"].astype(str).eq(scenario_name)]) == len(
            base_rows
        )


def test_conflict_traces_inherit_reconciled_uptake_base_plus_fixed_quarterly_deltas(
    ar1_fuel_replay,
) -> None:
    chart = pd.read_parquet(AR1_CHART_PATH)
    drift = pd.read_parquet(ROOT / "data/current_revenue_outlook/ev_phev_ped_light_drift_assumptions.parquet")
    uptake_rows, _ = apply_uptake_levers_to_chart_rows(
        chart,
        drift,
        EV_UPTAKE_PRESETS["MoT VFM base"],
        adjust_ped=True,
    )
    combined, audit = append_fuel_price_scenario_to_chart_rows(
        uptake_rows, ar1_fuel_replay
    )

    base = combined[
        combined["scenario_name"].astype(str).eq("current_basecase")
        & combined["time_grain"].astype(str).eq("quarterly")
    ][["series_id", "period", "value", "value_unit"]].rename(
        columns={"value": "base_value", "value_unit": "base_unit"}
    )
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        conflict = combined[
            combined["scenario_name"].astype(str).eq(scenario_name)
            & combined["time_grain"].astype(str).eq("quarterly")
        ][
            [
                "series_id",
                "period",
                "value",
                "value_unit",
                "_fuel_quarterly_reconciliation_delta",
            ]
        ].rename(columns={"value": "conflict_value", "value_unit": "conflict_unit"})
        replay_delta = ar1_fuel_replay.quarterly_factors[
            ar1_fuel_replay.quarterly_factors["scenario_name"]
            .astype(str)
            .eq(scenario_name)
        ][["series_id", "period", "delta"]]
        comparison = base.merge(
            conflict, on=["series_id", "period"], validate="one_to_one"
        ).merge(
            replay_delta,
            on=["series_id", "period"],
            validate="one_to_one",
        )
        display_scale = np.where(
            comparison["base_unit"].astype(str).str.contains("million", case=False),
            1_000_000.0,
            1.0,
        )
        np.testing.assert_allclose(
            pd.to_numeric(comparison["conflict_value"], errors="coerce")
            - pd.to_numeric(comparison["base_value"], errors="coerce"),
            pd.to_numeric(comparison["delta"], errors="coerce") / display_scale
            + pd.to_numeric(
                comparison["_fuel_quarterly_reconciliation_delta"], errors="coerce"
            ),
            rtol=1e-12,
            atol=1e-8,
        )
        assert set(
            comparison.loc[
                comparison["series_id"].isin(
                    ["light_ruc_net_km", "heavy_ruc_net_km"]
                ),
                "conflict_unit",
            ]
        ) == {"million km"}

        # The quarterly bridge must not move the governed annual checkpoints.
        annual_factor = ar1_fuel_replay.annual_factors[
            ar1_fuel_replay.annual_factors["scenario_name"]
            .astype(str)
            .eq(scenario_name)
        ].set_index(["series_id", "june_year"])["factor"]
        for series_id in (
            "ped_vkt_per_capita",
            "light_ruc_net_km",
            "heavy_ruc_net_km",
        ):
            for fy in (2026, 2027, 2028, 2030):
                base_annual = _annual(combined, "current_basecase", fy)
                conflict_annual = _annual(combined, scenario_name, fy)
                assert float(
                    conflict_annual.at[series_id, "value"]
                ) == pytest.approx(
                    float(base_annual.at[series_id, "value"])
                    * float(annual_factor.at[(series_id, fy)]),
                    rel=1e-12,
                    abs=1e-10,
                )

    # Every visible native-activity June year equals the four fiscal quarters.
    # FY2026 includes two fixed actual quarters plus two forecast/scenario
    # quarters; subsequent years contain four scenario quarters.
    for scenario_name in (
        "current_basecase",
        *(conflict_scenario_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS),
    ):
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


def test_policy_pair_overlay_matches_formula_rebuilt_base_and_conflict_annual_bridges(
    ar1_fuel_replay,
) -> None:
    source_chart = pd.read_parquet(AR1_CHART_PATH)
    chart, macro_audit = apply_treasury_macro_to_chart_rows(
        source_chart, ar1_fuel_replay
    )
    assert not macro_audit.empty
    delayed, policy_audit = apply_fed_uplift_delay_to_chart_rows(
        chart,
        fed_uplift_delayed_factors(ROOT, chart),
        scenario_roles={"basecase", "comparison"},
        affected_periods_by_fy=fed_policy_affected_periods(ROOT, FED_POLICY_STATE_DELAYED_6M),
        policy_pair_factors=ar1_fuel_replay.policy_pair_factors,
    )
    combined, audit = append_fuel_price_scenario_to_chart_rows(
        delayed, ar1_fuel_replay
    )

    assert not policy_audit.empty
    assert set(policy_audit["transformation_basis"].astype(str)) == {
        "fixed_finalist_policy_replay_leaf_or_net_ruc",
        "formula_rebuilt_from_ped_and_net_ruc_deltas",
    }

    visible_series = set(
        chart[
            chart["scenario_name"].astype(str).eq("current_basecase")
            & chart["time_grain"].astype(str).eq("june_year")
        ]["series_id"].astype(str)
    )
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        scenario_name = conflict_scenario_name(level)
        pair_id = f"{level}_vs_baseline_delayed_6m"
        pair_factors = ar1_fuel_replay.policy_pair_factors[
            ar1_fuel_replay.policy_pair_factors["pair_id"].astype(str).eq(pair_id)
            & ar1_fuel_replay.policy_pair_factors["time_grain"]
            .astype(str)
            .eq("june_year")
        ]
        for fy in range(2026, 2031):
            displayed = _annual(combined, scenario_name, fy)
            base_displayed = _annual(combined, "current_basecase", fy)
            expected = pair_factors[
                pd.to_numeric(pair_factors["june_year"], errors="coerce").eq(fy)
            ].set_index("series_id")
            direct_factor_series = visible_series.difference(
                set(FED_AGGREGATE_SERIES) | set(TOTAL_AGGREGATE_SERIES)
            )
            for series_id in direct_factor_series.intersection(expected.index):
                assert float(displayed.at[series_id, "value"]) == pytest.approx(
                    float(base_displayed.at[series_id, "value"])
                    * float(expected.at[series_id, "factor"]),
                    abs=1e-9,
                )

    base_2027 = _annual(combined, "current_basecase", 2027)
    assert float(base_2027.at["total_ruc_net_revenue", "value"]) < float(
        _annual(source_chart, "current_basecase", 2027).at[
            "total_ruc_net_revenue", "value"
        ]
    )
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        conflict_2027 = _annual(combined, conflict_scenario_name(level), 2027)
        assert float(conflict_2027.at["total_ruc_net_revenue", "value"]) < float(
            base_2027.at["total_ruc_net_revenue", "value"]
        )
        assert float(conflict_2027.at["net_mvr_revenue", "value"]) == pytest.approx(
            float(base_2027.at["net_mvr_revenue", "value"]),
            abs=1e-12,
        )
        for series_id in (
            "gross_ped_revenue",
            "gross_fed_revenue",
            "net_fed_revenue",
            "total_ruc_net_revenue",
        ):
            row = conflict_2027.loc[series_id]
            assert row["_fed_policy"] == FED_POLICY_STATE_DELAYED_6M
            assert row["_fed_affected_quarters"] == "2027Q1;2027Q2"

    annual_audit = audit[
        audit["time_grain"].astype(str).eq("june_year")
        & audit["period"].astype(str).eq("FY2027")
    ]
    assert not annual_audit.empty
    assert set(annual_audit["transformation_basis"].astype(str)) == {
        "policy_matched_annual_bridge_factor",
        "formula_rebuilt_from_ped_delta",
        "formula_rebuilt_from_ped_and_net_ruc_deltas",
    }
    asserted_policies = set(annual_audit["fed_policy"].astype(str)) - {""}
    assert asserted_policies == {FED_POLICY_STATE_DELAYED_6M}


def test_structural_components_sum_exactly_to_the_displayed_forecast(fuel_replay):
    """P0: displayed totals and component attribution must be the same layer."""

    components = fuel_replay.structural_component_forecasts
    assert not components.empty
    overlay_scenarios = structural_overlay_scenario_ids()
    assert set(components["scenario_name"].astype(str)) == set(overlay_scenarios)
    assert set(components["component_label"].astype(str)) == {
        "STRUCTURAL_REFERENCE_BASE",
        "STRUCTURAL_PRICE_RESPONSE",
        "STRUCTURAL_GDP_RESPONSE",
        "STRUCTURAL_PRICE_GDP_INTERACTION",
    }

    keys = ["scenario_name", "stream", "target_period"]
    closure = components.groupby(keys, dropna=False).agg(
        component_sum=("component_forecast", "sum"),
        final_forecast=("final_forecast", "first"),
    )
    np.testing.assert_allclose(
        closure["component_sum"],
        closure["final_forecast"],
        rtol=1e-12,
        atol=1e-9,
    )

    # Every calibrated forecast row is covered - no silent gaps.
    forecasts = fuel_replay.future_forecasts
    calibrated = forecasts[
        forecasts["demand_calibration_applied"].fillna(False).astype(bool)
    ]
    assert len(closure) == len(calibrated)


def test_overlay_scenario_fitted_components_are_suppressed_not_displayed(fuel_replay):
    """P0: fitted ensemble members must not attribute the overlay forecast."""

    overlay_scenarios = structural_overlay_scenario_ids()
    components = fuel_replay.replay.component_forecasts
    if not components.empty and "scenario_name" in components.columns:
        assert not components["scenario_name"].astype(str).isin(overlay_scenarios).any()

    superseded = fuel_replay.superseded_component_forecasts
    if not superseded.empty:
        assert set(superseded["scenario_name"].astype(str)).issubset(overlay_scenarios)
        assert set(superseded["component_forecast_status"].astype(str)) == {
            "superseded_by_structural_overlay"
        }
        assert set(superseded["describes_forecast_layer"].astype(str)) == {
            "raw_fitted_replay_pre_overlay"
        }


def test_post_calibration_valid_is_derived_and_can_be_false(fuel_replay):
    """P0: the flag must reflect measured checks, not be assigned True."""

    validation = fuel_replay.policy_validation_report.set_index("scenario_name")
    flags = validation["policy_post_calibration_valid"].astype(bool)
    rows = validation["policy_post_calibration_rows"].astype(int)

    # Not a constant: uncalibrated scenarios are False, calibrated ones True.
    assert set(flags.unique()) == {True, False}
    assert (flags == rows.gt(0)).all()

    # And it is reproducible from the recorded evidence columns alone.
    recomputed = (
        rows.gt(0)
        & validation["policy_post_calibration_formula_tolerance_ratio"].le(1.0)
        & validation[
            "policy_post_calibration_component_closure_tolerance_ratio"
        ].le(1.0)
        & validation["policy_post_calibration_sign_breaches"].eq(0)
    )
    assert (recomputed == flags).all()


def test_fan_bands_reject_structural_overlay_scenarios():
    """P0: an interval must be generated from the displayed forecast layer."""

    from model_dashboard.revenue_outlook import _assert_no_structural_overlay_fan_bands

    overlay_scenario = sorted(structural_overlay_scenario_ids())[0]
    _assert_no_structural_overlay_fan_bands(
        pd.DataFrame({"scenario_name": ["current_basecase", "mbu26_official"]})
    )
    with pytest.raises(ValueError, match="structural-overlay"):
        _assert_no_structural_overlay_fan_bands(
            pd.DataFrame(
                {
                    "series_id": ["net_fed_revenue"],
                    "fan_source": ["current_finalist_backtest"],
                    "scenario_name": [overlay_scenario],
                }
            )
        )

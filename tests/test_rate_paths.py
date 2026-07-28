from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.light_fleet_allocation import LAST_DECISION_GRADE_ANNUAL_FY
from model_dashboard.rate_paths import (
    FED_POLICY_METADATA_COLUMNS,
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    apply_fed_uplift_delay_to_chart_rows,
    apply_fed_uplift_off_to_chart_rows,
    apply_official_comparator_rate_policy_to_chart_rows,
    fed_policy_affected_periods,
    fed_policy_quarterly_factors,
    fed_uplift_delayed_factors,
    fed_uplift_off_factors,
    mbu26_ruc_class_revenue_by_fy,
    official_comparator_factor_map,
    ped_rate_change_quarterly_factors,
    ped_quarterly_rate_schedules,
    ped_rate_schedules,
    rate_paths_frame,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pack_chart_rows() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv")


def test_ped_schedules_carry_the_legislated_wedge_forward(pack_chart_rows) -> None:
    schedules = ped_rate_schedules(ROOT, pack_chart_rows)
    # legislated window: +6c in FY2027, +12c from FY2028 (pack-implied planned
    # rates carry sub-cent rounding, hence the 2e-3 tolerance)
    assert schedules.loc[2027, "planned"] - schedules.loc[2027, "no_uplift"] == pytest.approx(0.06, abs=2e-3)
    assert schedules.loc[2028, "planned"] - schedules.loc[2028, "no_uplift"] == pytest.approx(0.12, abs=2e-3)
    # Beyond the legislated window the wedge stays parallel, for every year the
    # schedule actually reaches. Pinning FY2040/FY2050 assumed the pre-policy
    # current-model horizon; the schedule now ends with the current
    # decision-facing horizon, while the official comparator keeps its own
    # reach (see test_official_comparator_policy_horizon.py).
    beyond_window = [year for year in schedules.index if int(year) >= 2028]
    assert beyond_window, "the schedule must extend past the legislated step"
    for year in beyond_window:
        assert schedules.loc[year, "planned"] - schedules.loc[year, "no_uplift"] == pytest.approx(
            0.12, abs=2e-3
        ), f"wedge is not parallel in FY{year}"
    # pre-policy years have no wedge
    assert schedules.loc[2026, "planned"] - schedules.loc[2026, "no_uplift"] == pytest.approx(0.0, abs=1e-9)
    # history stops at the last complete actual June year
    assert pd.isna(schedules.loc[2026, "history"])


def test_six_month_delay_moves_only_calendar_2027_q1_q2(pack_chart_rows) -> None:
    quarterly = ped_quarterly_rate_schedules(ROOT)
    changed = quarterly[
        pd.to_numeric(quarterly["planned"], errors="coerce").sub(
            pd.to_numeric(quarterly["delayed_6m"], errors="coerce")
        ).abs().gt(1e-9)
    ]
    assert tuple(changed.index) == ("2027Q1", "2027Q2")
    assert changed["delayed_6m"].tolist() == pytest.approx([0.70024, 0.70024])
    assert changed["planned"].tolist() == pytest.approx([0.82024, 0.82024])
    for quarter in ("2026Q3", "2026Q4", "2027Q3", "2027Q4", "2028Q1", "2028Q2"):
        assert quarterly.loc[quarter, "delayed_6m"] == pytest.approx(quarterly.loc[quarter, "planned"])
    assert fed_policy_affected_periods(ROOT, FED_POLICY_STATE_DELAYED_6M) == {
        2027: ("2027Q1", "2027Q2")
    }
    proportional_factors = fed_policy_quarterly_factors(ROOT, FED_POLICY_STATE_DELAYED_6M)
    exact_factor = 0.70024 / 0.82024
    assert proportional_factors["2027Q1"] == pytest.approx(exact_factor, rel=1e-15)
    assert proportional_factors["2027Q2"] == pytest.approx(exact_factor, rel=1e-15)
    assert proportional_factors["2027Q3"] == pytest.approx(1.0, abs=1e-15)

    annual = ped_rate_schedules(ROOT, pack_chart_rows)
    assert annual.loc[2026, "delayed_6m"] == pytest.approx(annual.loc[2026, "planned"])
    assert annual.loc[2027, "delayed_6m"] == pytest.approx(0.70024)
    # Identity from FY2028 onward, for every year the schedule reaches rather
    # than a single pinned far year.
    for year in [value for value in annual.index if int(value) >= 2028]:
        assert annual.loc[year, "delayed_6m"] == pytest.approx(
            annual.loc[year, "planned"]
        ), f"delayed diverges from planned in FY{year}"


def test_six_month_delay_factor_is_confined_to_fy2027(pack_chart_rows) -> None:
    factors = fed_uplift_delayed_factors(ROOT, pack_chart_rows)
    assert set(factors) == {2027}
    assert factors[2027] == pytest.approx(0.9215585125844958, rel=1e-12)


def test_any_fixed_period_ped_change_maps_to_the_same_proportional_ruc_signal() -> None:
    factors = ped_rate_change_quarterly_factors(
        ROOT,
        {
            "2028Q1": 0.06,
            "2028Q2": -0.10,
        },
    )
    schedules = ped_quarterly_rate_schedules(ROOT)
    assert factors["2028Q1"] == pytest.approx(
        (float(schedules.at["2028Q1", "planned"]) + 0.06)
        / float(schedules.at["2028Q1", "planned"]),
        rel=1e-15,
    )
    assert factors["2028Q2"] == pytest.approx(
        (float(schedules.at["2028Q2", "planned"]) - 0.10)
        / float(schedules.at["2028Q2", "planned"]),
        rel=1e-15,
    )
    assert set(factors) == {"2028Q1", "2028Q2"}

    with pytest.raises(ValueError, match="target rate negative"):
        ped_rate_change_quarterly_factors(ROOT, {"2028Q1": -99.0})


def test_uplift_factors_exist_only_from_fy2027(pack_chart_rows) -> None:
    factors = fed_uplift_off_factors(ROOT, pack_chart_rows)
    assert 2026 not in factors
    assert factors[2027] == pytest.approx(0.70 / 0.76, rel=1e-3)
    assert all(0.8 < f < 1.0 for f in factors.values())
    # The current-model factor map covers the current decision-facing horizon.
    # Reaching FY2050 is exactly what the H20 policy ends for the current
    # model; the official comparator keeps its own source horizon and is
    # pinned separately by
    # test_official_policy_reaches_beyond_the_current_model_horizon.
    assert min(factors) == 2027
    assert max(factors) >= LAST_DECISION_GRADE_ANNUAL_FY


def test_rate_paths_frame_has_three_streams_on_a_per_1000km_basis(pack_chart_rows) -> None:
    frame = rate_paths_frame(ROOT, pack_chart_rows)
    assert set(frame["series"]) == {"Light RUC", "Heavy RUC", "PED (petrol excise)"}
    for series in ("Light RUC", "Heavy RUC"):
        assert set(frame.loc[frame["series"].eq(series), "segment"]) == {
            "planned",
            "delayed_6m",
            "no_uplift",
        }
    at_2030 = frame[frame["june_year"].eq(2030)]
    light = float(
        at_2030[at_2030["series"].eq("Light RUC") & at_2030["segment"].eq("planned")][
            "nzd_per_1000km"
        ].iloc[0]
    )
    heavy = float(
        at_2030[at_2030["series"].eq("Heavy RUC") & at_2030["segment"].eq("planned")][
            "nzd_per_1000km"
        ].iloc[0]
    )
    ped_planned = at_2030[at_2030["series"].str.startswith("PED") & at_2030["segment"].eq("planned")]
    assert heavy > light > 0
    # PED per-1000km = $/L x litres/100km x 10 (FY2030: 0.94 x 8.758 x 10)
    assert float(ped_planned["nzd_per_1000km"].iloc[0]) == pytest.approx(0.9401 * 8.758 * 10, rel=1e-2)
    # history segment present back into the 2010s
    history = frame[frame["segment"].eq("history")]
    assert history["june_year"].min() <= 2014

    schedules = ped_rate_schedules(ROOT, pack_chart_rows)
    for series in ("Light RUC", "Heavy RUC"):
        fy2027 = frame[frame["series"].eq(series) & frame["june_year"].eq(2027)].set_index("segment")
        assert float(fy2027.at["delayed_6m", "nzd_per_1000km"]) / float(
            fy2027.at["planned", "nzd_per_1000km"]
        ) == pytest.approx(
            float(schedules.at[2027, "delayed_6m"]) / float(schedules.at[2027, "planned"]),
            rel=1e-12,
        )
        fy2026 = frame[frame["series"].eq(series) & frame["june_year"].eq(2026)].set_index("segment")
        assert float(fy2026.at["delayed_6m", "nzd_per_1000km"]) == pytest.approx(
            float(fy2026.at["planned", "nzd_per_1000km"]),
            abs=1e-12,
        )


def test_uplift_off_repriced_revenue_cascades_to_rollups(pack_chart_rows) -> None:
    factors = fed_uplift_off_factors(ROOT, pack_chart_rows)
    adjusted, audit = apply_fed_uplift_off_to_chart_rows(pack_chart_rows, factors)
    jy = lambda df, sid, fy: float(
        pd.to_numeric(
            df[
                df["time_grain"].astype(str).eq("june_year")
                & df["series_id"].astype(str).eq(sid)
                & pd.to_numeric(df["june_year"], errors="coerce").eq(fy)
                & df["trace_name"].astype(str).eq("Current finalist Base case")
            ]["value"],
            errors="coerce",
        ).iloc[0]
    )
    # FY2050 was a current-model June year before the H20 policy. The cascade
    # is a per-year identity, so exercise it across every current June year the
    # factor map covers rather than pinning a year that no longer publishes.
    covered = sorted(
        fy
        for fy in factors
        if not pack_chart_rows[
            pack_chart_rows["time_grain"].astype(str).eq("june_year")
            & pack_chart_rows["series_id"].astype(str).eq("gross_ped_revenue")
            & pd.to_numeric(pack_chart_rows["june_year"], errors="coerce").eq(fy)
            & pack_chart_rows["trace_name"].astype(str).eq("Current finalist Base case")
        ].empty
    )
    assert covered, "no current June year is covered by the no-uplift factor map"
    assert max(covered) == LAST_DECISION_GRADE_ANNUAL_FY
    for fy in covered:
        old_ped = jy(pack_chart_rows, "gross_ped_revenue", fy)
        new_ped = jy(adjusted, "gross_ped_revenue", fy)
        assert new_ped == pytest.approx(old_ped * factors[fy])
        ped_delta = new_ped - old_ped
        assert jy(adjusted, "gross_fed_revenue", fy) - jy(pack_chart_rows, "gross_fed_revenue", fy) == pytest.approx(
            ped_delta, rel=1e-9
        )
        ruc_delta = 0.0
        for series_id in (
            "light_ruc_net_revenue",
            "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue",
            "heavy_ruc_net_revenue",
        ):
            old = jy(pack_chart_rows, series_id, fy)
            new = jy(adjusted, series_id, fy)
            assert new == pytest.approx(old * factors[fy], rel=1e-12)
            ruc_delta += new - old
        assert jy(adjusted, "total_ruc_net_revenue", fy) - jy(
            pack_chart_rows, "total_ruc_net_revenue", fy
        ) == pytest.approx(ruc_delta, abs=1e-9)
        assert jy(adjusted, "total_nltf_net_revenue", fy) - jy(
            pack_chart_rows, "total_nltf_net_revenue", fy
        ) == pytest.approx(ped_delta + ruc_delta, abs=1e-9)
    # Activity is untouched in the rate-only comparator fallback.  Current
    # finalist paths use the fixed-finalist replay pair tested separately.
    assert jy(adjusted, "ped_volume", 2030) == pytest.approx(jy(pack_chart_rows, "ped_volume", 2030))
    assert jy(adjusted, "light_ruc_net_km", 2030) == pytest.approx(
        jy(pack_chart_rows, "light_ruc_net_km", 2030)
    )
    # actuals untouched
    actual_old = pack_chart_rows[pack_chart_rows["row_type"].astype(str).eq("historical_actual")]["value"]
    actual_new = adjusted[adjusted["row_type"].astype(str).eq("historical_actual")]["value"]
    pd.testing.assert_series_equal(actual_old.reset_index(drop=True), actual_new.reset_index(drop=True))


def test_uplift_off_can_be_scoped_independently_to_current_or_mbu26(pack_chart_rows) -> None:
    factors = fed_uplift_off_factors(ROOT, pack_chart_rows)

    def value(
        rows: pd.DataFrame,
        trace: str,
        fy: int,
        series_id: str = "total_nltf_net_revenue",
    ) -> float:
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq(series_id)
            & rows["trace_name"].astype(str).eq(trace)
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        ]
        return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])

    current_off, current_audit = apply_fed_uplift_off_to_chart_rows(
        pack_chart_rows, factors, scenario_roles={"basecase", "comparison"}
    )
    # The official comparator is a separate calculation with its own
    # source-derived schedule, not the current-model factor map applied to
    # another role set. Routing it through the current helper is what let the
    # current-model horizon truncate the published comparator.
    with pytest.raises(ValueError, match="current-model helper"):
        apply_fed_uplift_off_to_chart_rows(
            pack_chart_rows, factors, scenario_roles={"official_comparator"}
        )
    mbu_off, mbu_audit = apply_official_comparator_rate_policy_to_chart_rows(
        pack_chart_rows,
        ROOT,
        policy_state=FED_POLICY_STATE_NO_UPLIFT,
        ruc_class_revenue_by_fy=mbu26_ruc_class_revenue_by_fy(ROOT),
    )

    # Each scope moves only its own rows.
    assert value(current_off, "Current finalist Base case", 2030) < value(pack_chart_rows, "Current finalist Base case", 2030)
    assert value(current_off, "MBU26 official", 2030) == pytest.approx(value(pack_chart_rows, "MBU26 official", 2030))
    assert value(mbu_off, "Current finalist Base case", 2030) == pytest.approx(value(pack_chart_rows, "Current finalist Base case", 2030))

    official_factors = official_comparator_factor_map(ROOT, FED_POLICY_STATE_NO_UPLIFT)
    class_pool = mbu26_ruc_class_revenue_by_fy(ROOT)
    expected_mbu = value(pack_chart_rows, "MBU26 official", 2030) + (
        value(pack_chart_rows, "MBU26 official", 2030, "gross_ped_revenue")
        + class_pool[2030]
    ) * (official_factors[2030] - 1.0)
    assert value(mbu_off, "MBU26 official", 2030) == pytest.approx(expected_mbu, abs=1e-9)
    assert set(current_audit["scenario_role"]) <= {"basecase", "comparison"}
    assert set(mbu_audit["scenario_role"]) == {"official_comparator"}


def test_six_month_delay_is_audited_and_reconciles_every_annual_rollup(pack_chart_rows) -> None:
    factors = fed_uplift_delayed_factors(ROOT, pack_chart_rows)
    adjusted, audit = apply_fed_uplift_delay_to_chart_rows(
        pack_chart_rows,
        factors,
        scenario_roles={"basecase", "comparison"},
        affected_periods_by_fy=fed_policy_affected_periods(ROOT, FED_POLICY_STATE_DELAYED_6M),
    )
    ruc_leaves = {
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue",
    }
    touched_series = {
        "gross_ped_revenue",
        *ruc_leaves,
        "gross_fed_revenue",
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
    }
    touched = adjusted[
        adjusted["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(2027)
        & adjusted["scenario_role"].astype(str).isin({"basecase", "comparison"})
        & adjusted["series_id"].astype(str).isin(touched_series)
    ]
    assert not touched.empty
    assert set(FED_POLICY_METADATA_COLUMNS).issubset(adjusted.columns)
    assert set(touched["_fed_policy"]) == {FED_POLICY_STATE_DELAYED_6M}
    assert set(touched["_fed_affected_quarters"]) == {"2027Q1;2027Q2"}
    assert set(touched["value_status"]) == {"fed_uplift_delayed_6m"}
    assert set(touched["data_scope"]) == {"fed_uplift_delay_counterfactual"}
    assert pd.to_numeric(touched["_fed_baseline_value"], errors="coerce").add(
        pd.to_numeric(touched["_fed_annual_delta"], errors="coerce")
    ).to_numpy() == pytest.approx(pd.to_numeric(touched["value"], errors="coerce").to_numpy())

    for _, group in touched.groupby("trace_name"):
        deltas = group.set_index("series_id")["_fed_annual_delta"].map(float)
        ped_delta = float(deltas.at["gross_ped_revenue"])
        ruc_delta = sum(float(deltas.at[series_id]) for series_id in ruc_leaves)
        assert float(deltas.at["gross_fed_revenue"]) == pytest.approx(ped_delta, abs=1e-9)
        assert float(deltas.at["net_fed_revenue"]) == pytest.approx(ped_delta, abs=1e-9)
        assert float(deltas.at["total_ruc_net_revenue"]) == pytest.approx(ruc_delta, abs=1e-9)
        for series_id in (
            "total_fed_ruc_net_revenue",
            "total_nltf_net_revenue",
        ):
            assert float(deltas.at[series_id]) == pytest.approx(ped_delta + ruc_delta, abs=1e-9)

    def value(rows: pd.DataFrame, trace: str, fy: int) -> float:
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["trace_name"].astype(str).eq(trace)
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        ]
        return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])

    def expected_rate_only_total(trace: str, fy: int) -> float:
        repriced = {"gross_ped_revenue", *ruc_leaves}
        source = pack_chart_rows[
            pack_chart_rows["time_grain"].astype(str).eq("june_year")
            & pack_chart_rows["trace_name"].astype(str).eq(trace)
            & pd.to_numeric(pack_chart_rows["june_year"], errors="coerce").eq(fy)
            & pack_chart_rows["series_id"].astype(str).isin(repriced)
        ]
        delta = pd.to_numeric(source["value"], errors="coerce").sum() * (factors[fy] - 1.0)
        return value(pack_chart_rows, trace, fy) + float(delta)

    assert value(adjusted, "Current finalist Base case", 2027) == pytest.approx(
        expected_rate_only_total("Current finalist Base case", 2027), abs=1e-9
    )
    assert value(adjusted, "Current finalist High population/comparison", 2027) == pytest.approx(
        expected_rate_only_total("Current finalist High population/comparison", 2027), abs=1e-9
    )
    assert value(adjusted, "MBU26 official", 2027) == pytest.approx(value(pack_chart_rows, "MBU26 official", 2027))
    assert value(adjusted, "Current finalist Base case", 2028) == pytest.approx(value(pack_chart_rows, "Current finalist Base case", 2028))
    assert set(audit["policy_state"]) == {FED_POLICY_STATE_DELAYED_6M}
    assert set(audit["affected_periods"]) == {"2027Q1;2027Q2"}

    # The official delayed counterfactual is sourced from the governed
    # delayed/planned rate ratio, not from the current-model factor map.
    mbu_adjusted, mbu_audit = apply_official_comparator_rate_policy_to_chart_rows(
        pack_chart_rows,
        ROOT,
        policy_state=FED_POLICY_STATE_DELAYED_6M,
    )
    official_factors = official_comparator_factor_map(ROOT, FED_POLICY_STATE_DELAYED_6M)

    def expected_official_total(fy: int) -> float:
        repriced = {"gross_ped_revenue", *ruc_leaves}
        source = pack_chart_rows[
            pack_chart_rows["time_grain"].astype(str).eq("june_year")
            & pack_chart_rows["trace_name"].astype(str).eq("MBU26 official")
            & pd.to_numeric(pack_chart_rows["june_year"], errors="coerce").eq(fy)
            & pack_chart_rows["series_id"].astype(str).isin(repriced)
        ]
        delta = pd.to_numeric(source["value"], errors="coerce").sum() * (official_factors[fy] - 1.0)
        return value(pack_chart_rows, "MBU26 official", fy) + float(delta)

    assert value(mbu_adjusted, "MBU26 official", 2027) == pytest.approx(
        expected_official_total(2027), abs=1e-9
    )
    # Delayed differs from published in FY2027 only; identity from FY2028 on.
    assert 2027 in official_factors
    assert not any(fy != 2027 for fy in official_factors)
    for fy in (2028, 2030, 2031):
        assert value(mbu_adjusted, "MBU26 official", fy) == pytest.approx(
            value(pack_chart_rows, "MBU26 official", fy), abs=1e-9
        )
    assert value(mbu_adjusted, "Current finalist Base case", 2027) == pytest.approx(
        value(pack_chart_rows, "Current finalist Base case", 2027)
    )
    assert set(mbu_audit["scenario_role"]) == {"official_comparator"}


def test_no_uplift_wrapper_retains_status_and_quarter_metadata(pack_chart_rows) -> None:
    # The wrapper under test is the CURRENT-model one, so it is exercised on a
    # current role. Official rows go through the official helper.
    adjusted, audit = apply_fed_uplift_off_to_chart_rows(
        pack_chart_rows,
        fed_uplift_off_factors(ROOT, pack_chart_rows),
        scenario_roles={"basecase", "comparison"},
    )
    selected = adjusted[
        adjusted["time_grain"].astype(str).eq("june_year")
        & adjusted["series_id"].astype(str).eq("total_nltf_net_revenue")
        & adjusted["trace_name"].astype(str).eq("Current finalist Base case")
        & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(2030)
    ].iloc[0]
    assert selected["_fed_policy"] == FED_POLICY_STATE_NO_UPLIFT
    assert selected["_fed_affected_quarters"] == "2029Q3;2029Q4;2030Q1;2030Q2"
    assert selected["value_status"] == "fed_uplift_off"
    assert selected["data_scope"] == "fed_uplift_counterfactual"
    assert set(audit["policy_state"]) == {FED_POLICY_STATE_NO_UPLIFT}

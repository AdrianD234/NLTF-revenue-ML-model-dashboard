from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.rate_paths import (
    FED_POLICY_METADATA_COLUMNS,
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    apply_fed_uplift_delay_to_chart_rows,
    apply_fed_uplift_off_to_chart_rows,
    fed_policy_affected_periods,
    fed_uplift_delayed_factors,
    fed_uplift_off_factors,
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
    # beyond the window the wedge stays parallel
    assert schedules.loc[2040, "planned"] - schedules.loc[2040, "no_uplift"] == pytest.approx(0.12, abs=2e-3)
    assert schedules.loc[2050, "planned"] - schedules.loc[2050, "no_uplift"] == pytest.approx(0.12, abs=2e-3)
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

    annual = ped_rate_schedules(ROOT, pack_chart_rows)
    assert annual.loc[2026, "delayed_6m"] == pytest.approx(annual.loc[2026, "planned"])
    assert annual.loc[2027, "delayed_6m"] == pytest.approx(0.70024)
    assert annual.loc[2028, "delayed_6m"] == pytest.approx(annual.loc[2028, "planned"])
    assert annual.loc[2050, "delayed_6m"] == pytest.approx(annual.loc[2050, "planned"])


def test_six_month_delay_factor_is_confined_to_fy2027(pack_chart_rows) -> None:
    factors = fed_uplift_delayed_factors(ROOT, pack_chart_rows)
    assert set(factors) == {2027}
    assert factors[2027] == pytest.approx(0.9215585125844958, rel=1e-12)


def test_uplift_factors_exist_only_from_fy2027(pack_chart_rows) -> None:
    factors = fed_uplift_off_factors(ROOT, pack_chart_rows)
    assert 2026 not in factors
    assert factors[2027] == pytest.approx(0.70 / 0.76, rel=1e-3)
    assert all(0.8 < f < 1.0 for f in factors.values())
    assert max(factors) >= 2050


def test_rate_paths_frame_has_three_streams_on_a_per_1000km_basis(pack_chart_rows) -> None:
    frame = rate_paths_frame(ROOT, pack_chart_rows)
    assert set(frame["series"]) == {"Light RUC", "Heavy RUC", "PED (petrol excise)"}
    at_2030 = frame[frame["june_year"].eq(2030)]
    light = float(at_2030[at_2030["series"].eq("Light RUC")]["nzd_per_1000km"].iloc[0])
    heavy = float(at_2030[at_2030["series"].eq("Heavy RUC")]["nzd_per_1000km"].iloc[0])
    ped_planned = at_2030[at_2030["series"].str.startswith("PED") & at_2030["segment"].eq("planned")]
    assert heavy > light > 0
    # PED per-1000km = $/L x litres/100km x 10 (FY2030: 0.94 x 8.758 x 10)
    assert float(ped_planned["nzd_per_1000km"].iloc[0]) == pytest.approx(0.9401 * 8.758 * 10, rel=1e-2)
    # history segment present back into the 2010s
    history = frame[frame["segment"].eq("history")]
    assert history["june_year"].min() <= 2014


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
    for fy in (2030, 2050):
        old_ped = jy(pack_chart_rows, "gross_ped_revenue", fy)
        new_ped = jy(adjusted, "gross_ped_revenue", fy)
        assert new_ped == pytest.approx(old_ped * factors[fy])
        delta = new_ped - old_ped
        assert jy(adjusted, "gross_fed_revenue", fy) - jy(pack_chart_rows, "gross_fed_revenue", fy) == pytest.approx(delta, rel=1e-9)
        assert jy(adjusted, "total_nltf_net_revenue", fy) - jy(pack_chart_rows, "total_nltf_net_revenue", fy) == pytest.approx(delta, rel=1e-9)
    # volumes untouched (pure rate counterfactual)
    assert jy(adjusted, "ped_volume", 2030) == pytest.approx(jy(pack_chart_rows, "ped_volume", 2030))
    # actuals untouched
    actual_old = pack_chart_rows[pack_chart_rows["row_type"].astype(str).eq("historical_actual")]["value"]
    actual_new = adjusted[adjusted["row_type"].astype(str).eq("historical_actual")]["value"]
    pd.testing.assert_series_equal(actual_old.reset_index(drop=True), actual_new.reset_index(drop=True))


def test_uplift_off_can_be_scoped_independently_to_current_or_mbu26(pack_chart_rows) -> None:
    factors = fed_uplift_off_factors(ROOT, pack_chart_rows)

    def value(rows: pd.DataFrame, trace: str, fy: int) -> float:
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["trace_name"].astype(str).eq(trace)
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        ]
        return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])

    current_off, current_audit = apply_fed_uplift_off_to_chart_rows(
        pack_chart_rows, factors, scenario_roles={"basecase", "comparison"}
    )
    mbu_off, mbu_audit = apply_fed_uplift_off_to_chart_rows(
        pack_chart_rows, factors, scenario_roles={"official_comparator"}
    )

    assert value(current_off, "Current finalist Base case", 2030) < value(pack_chart_rows, "Current finalist Base case", 2030)
    assert value(current_off, "MBU26 official", 2030) == pytest.approx(value(pack_chart_rows, "MBU26 official", 2030))
    assert value(mbu_off, "Current finalist Base case", 2030) == pytest.approx(value(pack_chart_rows, "Current finalist Base case", 2030))
    assert value(mbu_off, "MBU26 official", 2030) == pytest.approx(6089.343312, rel=1e-9)
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
    touched_series = {"gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue", "total_fed_ruc_net_revenue", "total_gross_revenue", "total_revenue_net_admin", "total_nltf_net_revenue"}
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
        deltas = pd.to_numeric(group["_fed_annual_delta"], errors="coerce")
        assert deltas.max() == pytest.approx(deltas.min(), abs=1e-9)

    def value(rows: pd.DataFrame, trace: str, fy: int) -> float:
        selected = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
            & rows["trace_name"].astype(str).eq(trace)
            & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
        ]
        return float(pd.to_numeric(selected["value"], errors="coerce").iloc[0])

    assert value(adjusted, "Current finalist Base case", 2027) == pytest.approx(4611.426208301335, rel=1e-12)
    assert value(adjusted, "Current finalist High population/comparison", 2027) == pytest.approx(4631.757532231255, rel=1e-12)
    assert value(adjusted, "MBU26 official", 2027) == pytest.approx(value(pack_chart_rows, "MBU26 official", 2027))
    assert value(adjusted, "Current finalist Base case", 2028) == pytest.approx(value(pack_chart_rows, "Current finalist Base case", 2028))
    assert set(audit["policy_state"]) == {FED_POLICY_STATE_DELAYED_6M}
    assert set(audit["affected_periods"]) == {"2027Q1;2027Q2"}

    mbu_adjusted, mbu_audit = apply_fed_uplift_delay_to_chart_rows(
        pack_chart_rows,
        factors,
        scenario_roles={"official_comparator"},
    )
    assert value(mbu_adjusted, "MBU26 official", 2027) == pytest.approx(4835.639826942325, rel=1e-12)
    assert value(mbu_adjusted, "Current finalist Base case", 2027) == pytest.approx(
        value(pack_chart_rows, "Current finalist Base case", 2027)
    )
    assert set(mbu_audit["scenario_role"]) == {"official_comparator"}


def test_no_uplift_wrapper_retains_status_and_quarter_metadata(pack_chart_rows) -> None:
    adjusted, audit = apply_fed_uplift_off_to_chart_rows(
        pack_chart_rows,
        fed_uplift_off_factors(ROOT, pack_chart_rows),
        scenario_roles={"official_comparator"},
    )
    selected = adjusted[
        adjusted["time_grain"].astype(str).eq("june_year")
        & adjusted["series_id"].astype(str).eq("total_nltf_net_revenue")
        & adjusted["trace_name"].astype(str).eq("MBU26 official")
        & pd.to_numeric(adjusted["june_year"], errors="coerce").eq(2030)
    ].iloc[0]
    assert selected["_fed_policy"] == FED_POLICY_STATE_NO_UPLIFT
    assert selected["_fed_affected_quarters"] == "2029Q3;2029Q4;2030Q1;2030Q2"
    assert selected["value_status"] == "fed_uplift_off"
    assert selected["data_scope"] == "fed_uplift_counterfactual"
    assert set(audit["policy_state"]) == {FED_POLICY_STATE_NO_UPLIFT}

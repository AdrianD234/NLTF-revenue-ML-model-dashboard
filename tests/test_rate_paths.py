from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.rate_paths import (
    apply_fed_uplift_off_to_chart_rows,
    fed_uplift_off_factors,
    ped_rate_schedules,
    rate_paths_frame,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pack_chart_rows() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/current_revenue_outlook/revenue_chart_rows.parquet")


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

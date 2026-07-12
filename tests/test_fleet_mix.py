"""Fleet mix explorer: six-row taxonomy, denominators, source alignment."""
from __future__ import annotations

from pathlib import Path

import pytest

from model_dashboard.fleet_mix import (
    DASHBOARD_SOURCE,
    DENOMINATORS,
    MBU26_SOURCE,
    ROW_KEYS,
    SOURCE_OPTIONS,
    definitions_table,
    denominator_example,
    load_mbu26_frame,
    load_source_frame,
    share_frame,
    yoy_frame,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("source", SOURCE_OPTIONS)
def test_every_source_carries_the_six_rows_over_the_forecast_era(source: str) -> None:
    frame = load_source_frame(ROOT, source)
    assert list(frame.columns) == ROW_KEYS
    for fy in (2025, 2030, 2040, 2050):
        assert fy in frame.index, f"{source} missing FY{fy}"
    forecast = frame.loc[2025:2050]
    assert not forecast.isna().any().any(), f"{source} has gaps in the forecast era"
    assert (forecast >= 0).all().all(), f"{source} has negative volumes"


def test_the_fy2025_denominator_example_matches_the_hand_calc() -> None:
    """The user-verified reconciliation: 821m BEV km is 1.67% of all road
    travel, 1.81% of all light travel and 6.07% of the light RUC pool."""
    ex = denominator_example(ROOT, fy=2025)
    assert ex["total_km"] == pytest.approx(49_216.8, abs=0.5)
    assert ex["light_bev_km"] == pytest.approx(820.6, abs=0.5)
    assert ex["share_all"] == pytest.approx(0.0167, abs=0.0002)
    assert ex["share_light"] == pytest.approx(0.0181, abs=0.0002)
    assert ex["share_pool"] == pytest.approx(0.0607, abs=0.0002)


def test_dashboard_frame_replays_the_committed_pack() -> None:
    import pandas as pd

    frame = load_source_frame(ROOT, DASHBOARD_SOURCE)
    rows = pd.read_csv(ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "revenue_chart_rows.csv")
    annual = rows[(rows["time_grain"] == "june_year") & (rows["scenario_role"] == "basecase")
                  & (rows["row_type"] == "future_forecast")]
    light_2030 = float(annual[(annual["series_id"] == "light_ruc_net_km")
                              & (annual["period"].astype(str).str.contains("2030"))]["value"].iloc[0])
    assert frame.loc[2030, "light_ruc_net_km"] == pytest.approx(light_2030, rel=1e-9)


def test_vfm_base_and_mbu26_agree_at_the_2050_anchor() -> None:
    mbu = load_mbu26_frame(ROOT)
    vfm = load_source_frame(ROOT, "VFM 202405 - Base scenario")
    pool_keys = DENOMINATORS["Light RUC pool (conventional + BEV + PHEV)"]
    mbu_share = mbu.loc[2050, "light_bev_ruc_net_km"] / mbu.loc[2050, pool_keys].sum()
    vfm_share = vfm.loc[2050, "light_bev_ruc_net_km"] / vfm.loc[2050, pool_keys].sum()
    assert abs(mbu_share - vfm_share) < 0.02  # the documented MBU26 = VFM-base anchor


def test_share_frames_sum_to_one_and_yoy_is_finite() -> None:
    import numpy as np

    frame = load_mbu26_frame(ROOT).loc[2025:2050]
    for denominator in DENOMINATORS:
        shares = share_frame(frame, denominator)
        assert np.allclose(shares.sum(axis=1), 1.0, atol=1e-9)
    growth = yoy_frame(frame).iloc[1:]
    # heavy BEV is zero throughout MBU26, so its growth is undefined - all
    # other rows must be finite
    finite_cols = [k for k in ROW_KEYS if k != "heavy_bev_ruc_net_km"]
    assert np.isfinite(growth[finite_cols].to_numpy(dtype=float)).all()


def test_definitions_table_covers_all_six_rows_in_plain_language() -> None:
    table = definitions_table()
    assert len(table) == 6
    assert "diesel" in table.iloc[1]["What it contains"].lower()  # conventional-only caveat
    assert not table.map(lambda v: "__" in str(v)).any().any()

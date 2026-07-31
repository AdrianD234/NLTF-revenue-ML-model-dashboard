from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard.engine import engine_revenue_outlook_dir
from model_dashboard.ev_uptake_levers import (
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_PRESETS,
    apply_uptake_levers_to_chart_rows,
)
from model_dashboard.official_vintage import default_bridge_vintage_id
from model_dashboard.fleet_mix import (
    DASHBOARD_SOURCE,
    DENOMINATORS,
    ROW_KEYS,
    official_source_label,
    source_options,
    definitions_table,
    denominator_example,
    load_dashboard_frame,
    load_mbu26_frame,
    load_source_frame,
    share_frame,
    yoy_frame,
)
from model_dashboard.fuel_price_scenario import (
    apply_treasury_macro_to_chart_rows,
    run_direct_treasury_scenario_replay,
)
from model_dashboard.light_fleet_allocation import LAST_DECISION_GRADE_ANNUAL_FY
from model_dashboard.revenue_outlook import (
    PED_BRIDGE_DEFAULT_MODE,
    apply_ped_bridge_mode_layer,
    load_revenue_outlook_pack,
)


ROOT = Path(__file__).resolve().parents[1]
# The explorer follows the registered default bridge-assumption vintage.
BRIDGE_VINTAGE_ID = default_bridge_vintage_id(ROOT)


@pytest.mark.parametrize("source", source_options(default_bridge_vintage_id(ROOT)))
def test_every_source_carries_the_six_rows_over_its_published_era(
    source: str,
) -> None:
    """External sources run to FY2050; the current model stops at FY2030.

    The current-model Light RUC path is withheld beyond H20 because the
    conventional-anchor share expansion diverges at long horizons, so the
    dashboard source deliberately ends at FY2030 while the official vintage
    and the VFM scenarios continue over their published horizon.
    """
    frame = load_source_frame(ROOT, source, BRIDGE_VINTAGE_ID)
    assert list(frame.columns) == ROW_KEYS
    expected = (
        (2025, 2030)
        if source == DASHBOARD_SOURCE
        else (2025, 2030, 2040, 2050)
    )
    for fy in expected:
        assert fy in frame.index, f"{source} missing FY{fy}"
    if source == DASHBOARD_SOURCE:
        assert frame.index.max() == LAST_DECISION_GRADE_ANNUAL_FY, (
            "the current-model path must stop at the last decision-grade June year"
        )
    forecast = frame.loc[2025:2050]
    assert not forecast.isna().any().any(), f"{source} has gaps in its published era"
    assert (forecast >= 0).all().all(), f"{source} has negative volumes"


def test_the_fy2025_denominator_example_matches_the_hand_calc() -> None:
    """The common actual anchor retains the governed denominator example."""

    ex = denominator_example(ROOT, fy=2025)
    assert ex["total_km"] == pytest.approx(49_216.8, abs=0.5)
    assert ex["light_bev_km"] == pytest.approx(820.6, abs=0.5)
    assert ex["share_all"] == pytest.approx(0.0167, abs=0.0002)
    assert ex["share_light"] == pytest.approx(0.0181, abs=0.0002)
    assert ex["share_pool"] == pytest.approx(0.0607, abs=0.0002)


def test_dashboard_fleet_petrol_vkt_uses_same_lineage_as_ped_litres() -> None:
    dashboard = load_dashboard_frame(ROOT)
    mbu = load_mbu26_frame(ROOT)
    # Litres must come from the SAME bridge-assumption vintage that
    # load_mbu26_frame now resolves through the registry (BEFU26 by default);
    # mixing vintages here would compare against a different official baseline
    # than the one the runtime bridge actually used.
    from model_dashboard.fleet_mix import _spine

    mbu_spine = _spine(ROOT)
    mbu_ped_litres = (
        mbu_spine[
            mbu_spine["source_series_id"].astype(str).eq("ped_volume")
        ]
        .assign(
            FY_numeric=lambda frame: pd.to_numeric(frame["FY"], errors="coerce"),
            value_numeric=lambda frame: pd.to_numeric(frame["value"], errors="coerce"),
        )
        .set_index("FY_numeric")["value_numeric"]
    )
    pack = load_revenue_outlook_pack(
        ROOT / engine_revenue_outlook_dir("ar1"),
        repo_root=ROOT,
    )
    assert pack is not None

    bridge = pack.ped_revenue_bridge_audit[
        pack.ped_revenue_bridge_audit["source_path"]
        .astype(str)
        .eq("Current finalist Base case")
    ].copy()
    bridge["FY_numeric"] = pd.to_numeric(bridge["FY"], errors="coerce")
    bridge = bridge.set_index("FY_numeric")

    for fy in range(2026, 2031):
        petrol = float(dashboard.at[fy, "light_petrol_vkt"])
        ped_litres = float(bridge.at[fy, "ped_volume_raw_million_litres"])
        raw_petrol = float(bridge.at[fy, "raw_light_petrol_vkt_million_km"])
        intensity = ped_litres / raw_petrol

        # The VFM retention overlay scales VKT and litres together, so the
        # governed litres/km intensity is preserved exactly.
        aligned_litres = petrol * intensity
        aligned_petrol_change = petrol / float(mbu.at[fy, "light_petrol_vkt"]) - 1.0
        aligned_litres_change = (
            aligned_litres / float(mbu_ped_litres.at[fy]) - 1.0
        )
        assert aligned_petrol_change == pytest.approx(
            aligned_litres_change,
            abs=1e-12,
        )

    fy2030_change = (
        float(dashboard.at[2030, "light_petrol_vkt"])
        / float(mbu.at[2030, "light_petrol_vkt"])
        - 1.0
    )
    # Treasury's stronger governed baseline narrows the dashboard-versus-
    # official FY2030 gap from the legacy macro path's roughly -7.42%. The
    # expected value moved from -0.0587 when the pack stopped carrying a
    # lambda-reduced PED level, and from -0.0584 to -0.0590 when the bridge
    # baseline moved from MBU26 to BEFU26 (the official petrol-VKT and litres
    # baselines both shifted with the 2026Q1 BEFU26 refresh). The tolerance is
    # unchanged.
    assert fy2030_change == pytest.approx(-0.0590, abs=0.0002)


def test_dashboard_fleet_preserves_light_and_heavy_class_pools() -> None:
    dashboard = load_dashboard_frame(ROOT)
    pack = load_revenue_outlook_pack(
        ROOT / engine_revenue_outlook_dir("ar1"),
        repo_root=ROOT,
    )
    assert pack is not None
    bridge_rows = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        include_derived_frames=False,
        include_selected_ped_audit=False,
    )["chart_rows"]
    scenario_inputs = pd.read_parquet(
        ROOT
        / engine_revenue_outlook_dir("ar1")
        / "scenario_inputs"
        / "scenario_input_wide.parquet"
    )
    macro_replay = run_direct_treasury_scenario_replay(
        scenario_inputs,
        repo_root=ROOT,
        engine="ar1",
    )
    bridge_rows, _ = apply_treasury_macro_to_chart_rows(
        bridge_rows,
        macro_replay,
    )
    _, uptake_audit = apply_uptake_levers_to_chart_rows(
        bridge_rows,
        pack.ev_phev_ped_light_drift_assumptions,
        EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE],
        adjust_ped=True,
    )
    base_audit = uptake_audit[
        uptake_audit["scenario_name"].astype(str).eq("current_basecase")
    ].set_index("june_year")
    bridge_heavy = bridge_rows[
        bridge_rows["scenario_name"].astype(str).eq("current_basecase")
        & bridge_rows["time_grain"].astype(str).eq("june_year")
        & bridge_rows["series_id"].astype(str).eq("heavy_ruc_net_km")
    ].set_index("june_year")["value"]
    for fy in range(2026, LAST_DECISION_GRADE_ANNUAL_FY + 1):
        light_total = dashboard.loc[
            fy,
            ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"],
        ].sum()
        heavy_total = dashboard.loc[
            fy,
            ["heavy_ruc_net_km", "heavy_bev_ruc_net_km"],
        ].sum()
        assert light_total == pytest.approx(
            float(base_audit.at[fy, "light_ruc_pool_km"]),
            abs=1e-8,
        )
        assert heavy_total == pytest.approx(float(bridge_heavy.at[fy]), abs=1e-8)


def test_vfm_base_and_mbu26_agree_at_the_2050_anchor() -> None:
    mbu = load_mbu26_frame(ROOT)
    vfm = load_source_frame(ROOT, "VFM 202405 - Base scenario")
    pool_keys = DENOMINATORS["Light RUC pool (conventional + BEV + PHEV)"]
    mbu_share = mbu.loc[2050, "light_bev_ruc_net_km"] / mbu.loc[
        2050, pool_keys
    ].sum()
    vfm_share = vfm.loc[2050, "light_bev_ruc_net_km"] / vfm.loc[
        2050, pool_keys
    ].sum()
    assert abs(mbu_share - vfm_share) < 0.02


def test_share_frames_sum_to_one_and_yoy_is_finite() -> None:
    frame = load_mbu26_frame(ROOT).loc[2025:2050]
    for denominator in DENOMINATORS:
        shares = share_frame(frame, denominator)
        assert np.allclose(shares.sum(axis=1), 1.0, atol=1e-9)
    growth = yoy_frame(frame).iloc[1:]
    finite_cols = [key for key in ROW_KEYS if key != "heavy_bev_ruc_net_km"]
    assert np.isfinite(growth[finite_cols].to_numpy(dtype=float)).all()


def test_definitions_table_covers_all_six_rows_in_plain_language() -> None:
    table = definitions_table()
    assert len(table) == 6
    assert "diesel" in table.iloc[1]["What it contains"].lower()
    assert not table.map(lambda value: "__" in str(value)).any().any()
    # Source options and the MoT baseline label are generated per bridge
    # vintage, so they follow the registry rather than a hard-coded release.
    assert official_source_label(BRIDGE_VINTAGE_ID) in source_options(BRIDGE_VINTAGE_ID)
    assert DASHBOARD_SOURCE in source_options(BRIDGE_VINTAGE_ID)

"""Runtime semantics of the lambda migration transfer.

The stored AR(1) pack applies a lambda transfer that moves kilometres out of
both the PED petrol stream and the conventional Light RUC stream:

    light_ruc_net_km = raw modelled - lambda * M
    light_petrol_vkt = raw PED VKT  - (1 - lambda) * M

The front end does not display the PED side of that transfer: the default
bridge mode is `raw_model` (alpha 0), which restores the raw PED level, and
the VFM petrol displacement lever is applied only when that bridge is
selected. These tests pin that behaviour so a future change cannot silently
reintroduce a double deduction.

They also pin the finding that no supported runtime step restores the raw
conventional Light RUC forecast, so the decision-facing conventional line and
pool level remain lambda-constructed. That is a live finding, not approved
behaviour: if it is fixed, this test should be updated deliberately.

See artifacts/fleet_allocation_semantics/checkpoint_2_structural_verdict.md.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.engine import engine_revenue_outlook_dir
from model_dashboard.ev_uptake_levers import (
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_PRESETS,
    apply_uptake_levers_to_chart_rows,
)
from model_dashboard.fleet_mix import load_dashboard_frame
from model_dashboard.fuel_price_scenario import (
    apply_treasury_macro_to_chart_rows,
    run_treasury_baseline_macro_replay,
)
from model_dashboard.revenue_outlook import (
    PED_BRIDGE_DEFAULT_MODE,
    apply_ped_bridge_mode_layer,
    load_revenue_outlook_pack,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "current_basecase"
FORECAST_FYS = [2026, 2027, 2028, 2029, 2030]
TOL = 1e-6


def _annual(rows: pd.DataFrame) -> pd.DataFrame:
    sel = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_name"].astype(str).eq(SCENARIO)
        & pd.to_numeric(rows["june_year"], errors="coerce").between(2025, 2030)
    ]
    return sel.pivot_table(
        index="june_year", columns="series_id", values="value", aggfunc="first"
    ).sort_index()


@pytest.fixture(scope="module")
def stages() -> dict:
    pack_dir = ROOT / engine_revenue_outlook_dir("ar1")
    pack = load_revenue_outlook_pack(pack_dir, repo_root=ROOT)
    if pack is None:
        pytest.skip("AR(1) revenue outlook pack is unavailable")
    scenario_input_path = pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    if not scenario_input_path.exists():
        pytest.skip("Treasury macro replay inputs are unavailable")

    bridge = apply_ped_bridge_mode_layer(
        chart_rows=pack.revenue_chart_rows,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        include_derived_frames=False,
        include_selected_ped_audit=False,
    )
    macro = run_treasury_baseline_macro_replay(
        pd.read_parquet(scenario_input_path), repo_root=ROOT, engine="ar1"
    )
    s3, _ = apply_treasury_macro_to_chart_rows(bridge["chart_rows"], macro)
    s4, _ = apply_uptake_levers_to_chart_rows(
        s3,
        pack.ev_phev_ped_light_drift_assumptions,
        EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE],
        adjust_ped=True,
    )

    audit = pd.read_csv(pack_dir / "ped_revenue_bridge_audit.csv")
    audit = audit[audit["scenario_name"].eq(SCENARIO)].set_index("FY")
    split = pd.read_csv(pack_dir / "ev_phev_split_assumptions.csv")
    split = split[split["scenario_name"].eq(SCENARIO)].set_index("FY")
    drift = pd.read_csv(pack_dir / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq(SCENARIO) & drift["lambda_mode"].astype(str).eq("optimized")
    ].set_index("FY")

    return {
        "S1": _annual(pack.revenue_chart_rows),
        "S2": _annual(bridge["chart_rows"]),
        "S3": _annual(s3),
        "S4": _annual(s4),
        "audit": audit,
        "split": split,
        "drift": drift,
    }


def test_default_bridge_mode_is_the_raw_model_with_zero_alpha(stages) -> None:
    """The default runtime bridge must carry none of the optimized migration."""
    config = pd.read_csv(
        ROOT / engine_revenue_outlook_dir("ar1") / "ped_bridge_mode_config.csv"
    ).set_index("bridge_mode")
    assert PED_BRIDGE_DEFAULT_MODE == "raw_model"
    assert float(config.loc[PED_BRIDGE_DEFAULT_MODE, "alpha"]) == 0.0
    assert bool(config.loc[PED_BRIDGE_DEFAULT_MODE, "default_selected"]) is True
    assert str(config.loc[PED_BRIDGE_DEFAULT_MODE, "runtime_treatment"]) == "default_runtime"
    assert str(config.loc["optimized_migration", "runtime_treatment"]) == "audit_overlay"


def test_raw_bridge_restores_the_raw_ped_level(stages) -> None:
    for fy in FORECAST_FYS:
        assert float(stages["S2"].loc[fy, "light_petrol_vkt"]) == pytest.approx(
            float(stages["audit"].loc[fy, "raw_light_petrol_vkt_million_km"]), abs=TOL
        )


def test_the_stage_two_step_equals_exactly_the_lambda_ped_transfer(stages) -> None:
    """S2 - S1 on the PED line must be exactly (1 - lambda) * M."""
    for fy in FORECAST_FYS:
        drift = stages["drift"].loc[fy]
        migration = float(drift["current_BEV_km"]) + float(drift["current_PHEV_km"])
        expected = (1.0 - float(drift["lambda_value"])) * migration
        s1 = float(stages["audit"].loc[fy, "optimized_light_petrol_vkt_million_km"])
        s2 = float(stages["S2"].loc[fy, "light_petrol_vkt"])
        assert s2 - s1 == pytest.approx(expected, abs=TOL)


def test_no_lambda_ped_deduction_survives_the_default_bridge(stages) -> None:
    """The petrol stream must not carry both the lambda and VFM displacements."""
    for fy in FORECAST_FYS:
        raw = float(stages["audit"].loc[fy, "raw_light_petrol_vkt_million_km"])
        assert float(stages["S2"].loc[fy, "light_petrol_vkt"]) == pytest.approx(raw, abs=TOL)
    # And the only PED reduction after the macro stage is the VFM retention,
    # which must be a single factor strictly between 0 and 1.
    for fy in FORECAST_FYS:
        factor = float(stages["S4"].loc[fy, "light_petrol_vkt"]) / float(
            stages["S3"].loc[fy, "light_petrol_vkt"]
        )
        assert 0.8 < factor < 1.0


def test_the_raw_bridge_leaves_the_light_ruc_classes_untouched(stages) -> None:
    for fy in FORECAST_FYS:
        for series in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]:
            assert float(stages["S2"].loc[fy, series]) == pytest.approx(
                float(stages["S1"].loc[fy, series]), abs=TOL
            )


def test_no_runtime_step_restores_the_raw_conventional_light_ruc_forecast(stages) -> None:
    """Live finding: the decision-facing conventional line stays lambda-built.

    If a future change makes the runtime preserve the raw Light RUC model
    output as the conventional class, this test should be updated as a
    deliberate decision rather than relaxed.
    """
    for fy in FORECAST_FYS:
        raw = float(stages["split"].loc[fy, "current_light_total_modelled_km"])
        for stage in ["S1", "S2", "S3", "S4"]:
            assert float(stages[stage].loc[fy, "light_ruc_net_km"]) != pytest.approx(raw, abs=1.0)
    # The gap widens, and at FY2030 the conventional line sits well below the
    # model output while the pool sits well above it.
    raw_2030 = float(stages["split"].loc[2030, "current_light_total_modelled_km"])
    assert float(stages["S4"].loc[2030, "light_ruc_net_km"]) < raw_2030
    pool_2030 = sum(
        float(stages["S4"].loc[2030, series])
        for series in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]
    )
    assert pool_2030 > raw_2030


def test_stage_four_matches_the_supported_fleet_mix_builder(stages) -> None:
    """Our staged construction must equal load_dashboard_frame exactly."""
    dashboard = load_dashboard_frame(ROOT)
    checked = 0
    for series in [
        "light_petrol_vkt",
        "light_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "heavy_ruc_net_km",
    ]:
        if series not in dashboard.columns:
            continue
        for fy in FORECAST_FYS:
            if fy not in dashboard.index:
                continue
            assert float(stages["S4"].loc[fy, series]) == pytest.approx(
                float(dashboard.loc[fy, series]), abs=TOL
            )
            checked += 1
    assert checked >= 20


def test_the_additive_revenue_identity_holds_across_a_stage(stages) -> None:
    """Total NLTF moves by the PED change plus the RUC class change."""
    for fy in FORECAST_FYS:
        delta_ped = float(stages["S4"].loc[fy, "gross_ped_revenue"]) - float(
            stages["S3"].loc[fy, "gross_ped_revenue"]
        )
        delta_ruc = float(stages["S4"].loc[fy, "total_ruc_net_revenue"]) - float(
            stages["S3"].loc[fy, "total_ruc_net_revenue"]
        )
        delta_total = float(stages["S4"].loc[fy, "total_nltf_net_revenue"]) - float(
            stages["S3"].loc[fy, "total_nltf_net_revenue"]
        )
        assert delta_ped + delta_ruc == pytest.approx(delta_total, abs=TOL)


def test_investigation_scripts_write_only_to_their_artifact_directory() -> None:
    """No production file may be written by the checkpoint scripts."""
    for name in [
        "checkpoint2_structural_variants.py",
        "checkpoint2_runtime_parity.py",
    ]:
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert 'OUT = ROOT / "artifacts" / "fleet_allocation_semantics"' in source
        for forbidden in ["to_parquet(", "shutil.", "os.remove", "unlink("]:
            assert forbidden not in source, f"{name} may modify files: {forbidden}"
        # Every CSV write must target the artifact directory.
        for line in source.splitlines():
            if ".to_csv(" in line and "read_csv" not in line:
                assert "OUT /" in line, f"{name} writes outside the artifact dir: {line.strip()}"

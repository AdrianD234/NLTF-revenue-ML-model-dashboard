from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.engine import ENGINE_AR1, engine_revenue_outlook_dir
from model_dashboard.fuel_price_scenario import FUEL_PRICE_SCENARIO_NAME
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS
from model_dashboard.revenue_outlook import (
    NET_REVENUE_COMPARISON_UNIT,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    net_revenue_timing_comparison_frame,
    revenue_outlook_signature,
)
from model_dashboard.revenue_source_pack import SOURCE_SERIES_ALIASES


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def timing_materialization() -> dict[str, object]:
    pack_dir = ROOT / engine_revenue_outlook_dir(ENGINE_AR1)
    pack = load_revenue_outlook_pack(pack_dir, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, ROOT)
    sensitivity_key = app.selected_sensitivity_key(
        "Off",
        "Off",
        "Off",
        freight_rail_shift="Off",
    )
    delayed_key = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)
    chart_rows, _, _, _, _ = app.cached_scenario_overlay_rows(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        delayed_key,
        pack,
    )
    factors = app.cached_fed_uplift_factors(signature, pack)["delayed_6m"]
    comparison = net_revenue_timing_comparison_frame(chart_rows, factors)
    return {
        "pack": pack,
        "signature": signature,
        "sensitivity_key": sensitivity_key,
        "delayed_key": delayed_key,
        "chart_rows": chart_rows,
        "factors": factors,
        "comparison": comparison,
    }


def _value(frame: pd.DataFrame, path_id: str, fy: int, series_id: str) -> float:
    selected = frame[
        frame["path_id"].astype(str).eq(path_id)
        & pd.to_numeric(frame["FY"], errors="coerce").eq(fy)
        & frame["series_id"].astype(str).eq(series_id)
    ]
    assert len(selected) == 1
    return float(selected.iloc[0]["value_million_nzd"])


def test_net_ruc_alias_and_active_net_definitions_are_explicit() -> None:
    assert SOURCE_SERIES_ALIASES["Net RUC revenue"] == "total_ruc_net_revenue"
    assert SOURCE_SERIES_ALIASES["Net RUC revenue (all classes)"] == "total_ruc_net_revenue"
    formulas = {str(row["output_series_id"]): str(row["expression"]) for row in FORMULA_DEFINITIONS}
    assert formulas["net_fed_revenue"] == "gross_fed_revenue - fed_refunds"
    assert formulas["total_ruc_net_revenue"] == "ruc_revenue_net_admin - ruc_refunds"
    assert formulas["net_mvr_revenue"] == "mvr_revenue_net_admin_coo - mvr_refunds"
    assert app._revenue_outlook_series_display_label("Total RUC all classes") == "Net RUC revenue (all classes)"


def test_four_path_net_revenue_matrix_is_complete_unique_and_exact(timing_materialization) -> None:
    comparison = timing_materialization["comparison"]
    assert isinstance(comparison, pd.DataFrame)
    assert len(comparison) == 60
    assert not comparison.duplicated(["path_id", "FY", "series_id"]).any()
    assert set(comparison["path_id"]) == {
        "baseline_published",
        "baseline_shifted_6m",
        "iran_published",
        "iran_shifted_6m",
    }
    assert set(comparison["FY"]) == set(range(2026, 2031))
    assert set(comparison["series_id"]) == {
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
    }
    assert set(comparison["unit"]) == {NET_REVENUE_COMPARISON_UNIT}
    assert comparison["value_million_nzd"].notna().all()

    checkpoints = {
        ("baseline_published", 2027, "net_fed_revenue"): 2123.761306798029,
        ("baseline_shifted_6m", 2027, "net_fed_revenue"): 1954.074047243467,
        ("iran_published", 2027, "net_fed_revenue"): 2085.1080580705056,
        ("iran_shifted_6m", 2027, "net_fed_revenue"): 1918.4528168395254,
        ("baseline_published", 2030, "total_ruc_net_revenue"): 2980.4766656294096,
        ("iran_published", 2030, "total_ruc_net_revenue"): 2986.569426872961,
        ("baseline_published", 2030, "net_mvr_revenue"): 479.8837182888595,
    }
    for key, expected in checkpoints.items():
        assert _value(comparison, *key) == pytest.approx(expected, abs=1e-9)


def test_six_month_shift_changes_only_fy2027_net_fed(timing_materialization) -> None:
    comparison = timing_materialization["comparison"]
    wide = comparison.pivot(
        index=["scenario_id", "FY", "series_id"],
        columns="timing_id",
        values="value_million_nzd",
    )
    wide["delta"] = wide["shifted_6m"] - wide["published"]
    moved = wide[wide["delta"].abs().gt(1e-9)]
    assert set(moved.index.get_level_values("FY")) == {2027}
    assert set(moved.index.get_level_values("series_id")) == {"net_fed_revenue"}
    assert moved.loc[("baseline", 2027, "net_fed_revenue"), "delta"] == pytest.approx(
        -169.687259554562,
        abs=1e-9,
    )
    assert moved.loc[("iran", 2027, "net_fed_revenue"), "delta"] == pytest.approx(
        -166.6552412309802,
        abs=1e-9,
    )


def test_iran_demand_response_lowers_net_ruc_during_shock_and_leaves_mvr_fixed(timing_materialization) -> None:
    comparison = timing_materialization["comparison"]
    for timing_id in ("published", "shifted_6m"):
        for fy in (2026, 2027):
            assert _value(comparison, f"iran_{timing_id}", fy, "total_ruc_net_revenue") < _value(
                comparison,
                f"baseline_{timing_id}",
                fy,
                "total_ruc_net_revenue",
            )
        for fy in range(2026, 2031):
            assert _value(comparison, f"iran_{timing_id}", fy, "net_mvr_revenue") == pytest.approx(
                _value(comparison, f"baseline_{timing_id}", fy, "net_mvr_revenue"),
                abs=1e-12,
            )


def test_comparison_is_independent_of_separate_12c_on_off_widget_state(timing_materialization) -> None:
    pack = timing_materialization["pack"]
    signature = timing_materialization["signature"]
    sensitivity_key = timing_materialization["sensitivity_key"]
    factors = timing_materialization["factors"]
    delayed_comparison = timing_materialization["comparison"]
    no_uplift_key = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 1, 0)
    no_uplift_rows, _, _, _, _ = app.cached_scenario_overlay_rows(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        no_uplift_key,
        pack,
    )
    no_uplift_comparison = net_revenue_timing_comparison_frame(no_uplift_rows, factors)
    pd.testing.assert_frame_equal(
        delayed_comparison.reset_index(drop=True),
        no_uplift_comparison.reset_index(drop=True),
        check_exact=False,
        atol=1e-9,
        rtol=0.0,
    )


def test_aligned_iran_detail_reconciles_net_and_intermediate_rollups(timing_materialization) -> None:
    pack = timing_materialization["pack"]
    signature = timing_materialization["signature"]
    sensitivity_key = timing_materialization["sensitivity_key"]
    delayed_key = timing_materialization["delayed_key"]
    line_reconciliation, residuals, _, _ = app.cached_aligned_scenario_detail_frames(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        delayed_key,
        pack,
    )
    iran = residuals[
        residuals["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)
        & pd.to_numeric(residuals["FY"], errors="coerce").between(2026, 2030, inclusive="both")
        & residuals["output_series_id"].astype(str).isin(
            {
                "gross_ruc_revenue",
                "ruc_revenue_net_admin",
                "total_ruc_net_revenue",
                "net_fed_revenue",
                "net_mvr_revenue",
                "total_nltf_net_revenue",
            }
        )
    ].copy()
    assert len(iran) == 30
    assert iran["status"].eq("reconciled").all()
    assert pd.to_numeric(iran["residual_abs"], errors="coerce").max() <= 1e-6

    rows = line_reconciliation[
        line_reconciliation["scenario_name"].astype(str).eq(FUEL_PRICE_SCENARIO_NAME)
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").between(2026, 2030, inclusive="both")
    ].copy()
    for fy, group in rows.groupby(pd.to_numeric(rows["FY"], errors="coerce")):
        values = group.set_index("series_id")["value"].map(float)
        assert values["total_ruc_net_revenue"] == pytest.approx(
            values["gross_ruc_revenue"] - values["ruc_admin_revenue"] - values["ruc_refunds"],
            abs=1e-9,
        )
        assert values["net_fed_revenue"] == pytest.approx(
            values["gross_fed_revenue"] - values["fed_refunds"],
            abs=1e-9,
        )
        assert values["net_mvr_revenue"] == pytest.approx(
            values["mr1_revenue"]
            + values["mr2_revenue"]
            - values["mvr_admin_revenue"]
            - values["mvr_refunds"],
            abs=1e-9,
        )


def test_revenue_outlook_renderer_keeps_only_the_bottom_net_timing_download() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "net_revenue_12c_timing_comparison_fy2026_fy2030.csv" in source
    assert "Download 12c timing CSV" in source
    assert "Net revenue timing comparison (FY2026-FY2030)" not in source
    assert "_net_revenue_timing_comparison_display_table" not in source
    assert source.index("Download 12c timing CSV") > source.index("Show Manifest, Source policy and downloads")

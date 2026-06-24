from __future__ import annotations

from pathlib import Path

import pandas as pd

from app import (
    _source_gap_register_for_controls,
    _source_path_trace_status_for_controls,
    _source_reconciliation_view,
    revenue_outlook_figure,
)
from model_dashboard.revenue_source_pack import load_revenue_source_pack


ROOT = Path(__file__).resolve().parents[1]


def test_source_gap_register_view_reflects_active_crown_top_up_control() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    view = _source_gap_register_for_controls(
        pack,
        {
            "crown_top_up": "Include",
            "release_round": "BEFU25",
            "time_grain": "June-year",
            "series": "Total NLTF revenue",
        },
    )

    by_id = view.set_index("gap_id")
    assert by_id.loc["crown_top_up_values_missing", "availability_status"] == "missing"
    assert by_id.loc["crown_top_up_values_missing", "current_selection"] == "Include"
    assert by_id.loc["crown_top_up_values_missing", "runtime_treatment"] == "not_applied_missing_source"
    assert "no governed top-up value rows" in by_id.loc["crown_top_up_values_missing", "user_visible_message"]

    pack_by_id = pack.source_gap_register.set_index("gap_id")
    assert pack_by_id.loc["crown_top_up_values_missing", "runtime_treatment"] == "excluded_by_selection"


def test_reconciliation_view_exposes_optional_rollup_inputs() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    view = _source_reconciliation_view(pack, {"selected_fy": "FY2031"})

    assert not view.empty
    assert "optional_inputs_applied" in view.columns


def test_path_trace_status_view_reflects_active_release_selection() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    view = _source_path_trace_status_for_controls(pack, {"release_round": "HYEFU24"})

    by_id = view.set_index("trace_id")
    release_traces = by_id.loc[["selected_mot_befu_release", "rolling_befu_1y"]]
    assert set(release_traces["current_selection"]) == {"HYEFU24"}
    assert set(release_traces["availability_status"]) == {"missing"}
    assert set(release_traces["blocking_gap_id"]) == {"release_value_table_missing"}


def test_revenue_outlook_hover_preserves_horizon_scope_labels() -> None:
    rows = pd.DataFrame(
        [
            {
                "metric_type": "revenue",
                "time_grain": "quarterly",
                "row_type": "historical_actual",
                "scenario_name": "historical_actual",
                "scenario_role": "",
                "stream": "LIGHT_RUC",
                "stream_label": "Light RUC volume",
                "period": "2025Q4",
                "horizon": pd.NA,
                "horizon_scope": "",
                "value": 100.0,
                "value_unit": "nominal NZD",
                "bridge_status": "available",
                "gap_reason": "",
            },
            {
                "metric_type": "revenue",
                "time_grain": "quarterly",
                "row_type": "future_forecast",
                "scenario_name": "basecase",
                "scenario_role": "basecase",
                "stream": "LIGHT_RUC",
                "stream_label": "Light RUC volume",
                "period": "2026Q1",
                "horizon": 1,
                "horizon_scope": "H1-H12",
                "value": 101.0,
                "value_unit": "nominal NZD",
                "bridge_status": "available",
                "gap_reason": "",
            },
            {
                "metric_type": "revenue",
                "time_grain": "quarterly",
                "row_type": "future_forecast",
                "scenario_name": "basecase",
                "scenario_role": "basecase",
                "stream": "LIGHT_RUC",
                "stream_label": "Light RUC volume",
                "period": "2029Q1",
                "horizon": 13,
                "horizon_scope": "H13+",
                "value": 113.0,
                "value_unit": "nominal NZD",
                "bridge_status": "available",
                "gap_reason": "",
            },
        ]
    )

    fig = revenue_outlook_figure(rows, metric_type="revenue")
    forecast_trace = next(trace for trace in fig.data if trace.name == "basecase (basecase)")
    marker_trace = next(trace for trace in fig.data if trace.name == "basecase (basecase) markers")
    forecast_hover = [custom[0] for custom in forecast_trace.customdata]
    marker_hover = [custom[0] for custom in marker_trace.customdata]

    assert any("H1-H12 backtest-supported horizon" in label for label in forecast_hover)
    assert any("H13+ long-range extrapolation" in label for label in forecast_hover)
    assert "Forecast start (H1)" in marker_hover
    assert "Long-range extrapolation begins (H13)" in marker_hover

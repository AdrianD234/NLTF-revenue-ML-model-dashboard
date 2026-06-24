from __future__ import annotations

from pathlib import Path

import pandas as pd

from app import (
    _source_axis_title,
    _source_component_figure,
    _source_control_gap_messages,
    _source_gap_register_for_controls,
    _source_path_trace_status_for_controls,
    _source_reconciliation_view,
    _revenue_outlook_manifest_table,
    _selected_source_series_frame,
    _source_split_figure,
    _source_total_path_figure,
    _source_uncertainty_figure,
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


def test_source_gap_register_reports_unsupported_revenue_basis_selection() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    unavailable = _source_gap_register_for_controls(
        pack,
        {
            "series": "Total NLTF revenue",
            "revenue_basis": "Gross",
        },
    ).set_index("gap_id")

    assert unavailable.loc["revenue_basis_selection_unavailable", "availability_status"] == "missing"
    assert unavailable.loc["revenue_basis_selection_unavailable", "current_selection"] == "Total NLTF revenue: Gross"
    assert unavailable.loc["revenue_basis_selection_unavailable", "runtime_treatment"] == "basis_selection_not_applied_missing_source"
    assert "Available source-backed bases: Net" in unavailable.loc["revenue_basis_selection_unavailable", "user_visible_message"]
    assert any("not value-backed" in message for message in _source_control_gap_messages(pack, {"series": "Total NLTF revenue", "revenue_basis": "Gross"}))

    available = _source_gap_register_for_controls(
        pack,
        {
            "series": "Total NLTF revenue",
            "revenue_basis": "Net",
        },
    ).set_index("gap_id")
    assert available.loc["revenue_basis_selection_unavailable", "availability_status"] == "available"
    assert available.loc["revenue_basis_selection_unavailable", "runtime_treatment"] == "basis_filter_available"


def test_source_gap_register_view_reflects_active_fed_path_control() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    view = _source_gap_register_for_controls(pack, {"fed_path": "No 2027 12c uplift"})

    by_id = view.set_index("gap_id")
    assert by_id.loc["fed_path_scenario_values_missing", "availability_status"] == "missing"
    assert by_id.loc["fed_path_scenario_values_missing", "current_selection"] == "No 2027 12c uplift"
    assert by_id.loc["fed_path_scenario_values_missing", "runtime_treatment"] == "registry_only"
    assert "registry-only" in by_id.loc["fed_path_scenario_values_missing", "user_visible_message"]
    assert any(
        "FED path scenario values are not separately vendored" in message
        for message in _source_control_gap_messages(pack, {"fed_path": "No 2027 12c uplift"})
    )


def test_selected_source_series_applies_value_backed_revenue_basis_without_relabeling() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    path_gross = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_path": "Gross / benchmark actual"})
    assert set(path_gross["revenue_basis"]) == {"gross"}
    assert set(path_gross["source_series_label"]) == {"Gross PED revenue"}

    gross = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_basis": "Gross"})
    assert set(gross["revenue_basis"]) == {"gross"}
    assert set(gross["source_series_label"]) == {"Gross PED revenue"}

    nominal = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_basis": "Nominal ex GST"})
    assert set(nominal["revenue_basis"]) == {"nominal_ex_gst"}
    assert set(nominal["source_series_label"]) == {"PED revenue"}

    unavailable = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_basis": "Net"})
    assert set(unavailable["revenue_basis"]) == {"gross", "nominal_ex_gst"}
    messages = _source_control_gap_messages(pack, {"series": "PED revenue", "revenue_basis": "Net"})
    assert any("not value-backed" in message for message in messages)


def test_source_gap_register_reports_revenue_path_basis_conflicts() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    conflict = _source_gap_register_for_controls(
        pack,
        {
            "series": "Total NLTF revenue",
            "revenue_path": "Gross / benchmark actual",
            "revenue_basis": "Net",
        },
    ).set_index("gap_id")

    assert conflict.loc["revenue_path_basis_conflict", "availability_status"] == "selection_conflict"
    assert conflict.loc["revenue_path_basis_conflict", "runtime_treatment"] == "explicit_revenue_basis_takes_precedence"
    assert "implies Gross" in conflict.loc["revenue_path_basis_conflict", "user_visible_message"]
    assert any(
        "explicit revenue basis" in message
        for message in _source_control_gap_messages(
            pack,
            {
                "series": "Total NLTF revenue",
                "revenue_path": "Gross / benchmark actual",
                "revenue_basis": "Net",
            },
        )
    )

    aligned = _source_gap_register_for_controls(
        pack,
        {
            "series": "Total NLTF revenue",
            "revenue_path": "Net of admin fees & refunds",
            "revenue_basis": "Net",
        },
    )
    assert "revenue_path_basis_conflict" not in set(aligned["gap_id"])


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


def test_total_path_chart_exposes_missing_release_paths_without_values() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    fig = _source_total_path_figure(
        pack,
        {
            "series": "Total NLTF revenue",
            "release_round": "BEFU25",
            "model_basis": "In-house model",
            "selected_fy": "FY2031",
        },
    )

    by_name = {trace.name: trace for trace in fig.data}
    expected_gap_traces = {
        "Selected MOT/BEFU release path (BEFU25 gap)",
        "Rolling BEFU 1Y (BEFU25 gap)",
    }
    assert expected_gap_traces.issubset(set(by_name))
    for name in expected_gap_traces:
        trace = by_name[name]
        assert list(trace.x) == [None]
        assert list(trace.y) == [None]
        assert trace.meta["governance_gap"] == "release_value_table_missing"


def test_revenue_source_charts_use_explicit_units_and_annual_ticks() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    controls = {
        "series": "Total NLTF revenue",
        "release_round": "BEFU25",
        "model_basis": "In-house model",
        "selected_fy": "FY2031",
    }
    frame = pack.canonical_long[pack.canonical_long["series_id"].eq("total_nltf_net_revenue")]

    assert _source_axis_title(frame) == "$m nominal ex GST"

    total_fig = _source_total_path_figure(pack, controls)
    uncertainty_fig = _source_uncertainty_figure(pack, controls)
    component_fig = _source_component_figure(pack, controls)
    split_fig = _source_split_figure(pack, controls)
    for fig in [total_fig, uncertainty_fig]:
        assert fig.layout.yaxis.title.text == "$m nominal ex GST"
        assert fig.layout.xaxis.title.text == "June year"
        assert fig.layout.xaxis.tickmode == "linear"
        assert fig.layout.xaxis.dtick == 1
    assert component_fig.layout.yaxis.title.text == "$m nominal ex GST"

    value_traces = [
        trace
        for trace in total_fig.data
        if getattr(trace, "y", None) is not None and list(trace.y) != [None]
    ]
    assert value_traces
    assert all("$m nominal ex GST" in {row[0] for row in trace.customdata} for trace in value_traces)
    assert "$m nominal ex GST" in {row[0] for row in component_fig.data[0].customdata}
    assert "$m nominal ex GST" in {row[0] for row in split_fig.data[0].customdata}


def test_uncertainty_source_control_does_not_fabricate_mot_release_fan() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    controls = {
        "series": "Total NLTF revenue",
        "release_round": "BEFU25",
        "model_basis": "In-house model",
        "selected_fy": "FY2031",
        "uncertainty": "MOT release round",
    }

    mot_fig = _source_uncertainty_figure(pack, controls)

    assert not mot_fig.data
    assert "release-value rows" in mot_fig.layout.annotations[0].text
    assert "release_value_table_missing" in mot_fig.layout.annotations[0].text

    model_fig = _source_uncertainty_figure(pack, {**controls, "uncertainty": "In-house model"})
    assert model_fig.data
    assert model_fig.layout.yaxis.title.text == "$m nominal ex GST"


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


def test_revenue_outlook_manifest_table_exposes_source_pack_and_bridge_provenance() -> None:
    manifest = {
        "schema_version": "revenue-outlook-pack-v1",
        "pack_status": "explicitly_promoted_current_outlook",
        "promotion_time": "2026-06-24T09:50:46+00:00",
        "source_policy": "explicit promoted pack only",
        "repo_relative_output_dir": "data/current_revenue_outlook",
        "source_comparison": {
            "comparison_id": "current_revenue_outlook_scenario_comparison",
            "scenario_role_validation": {"status": "passed"},
        },
        "revenue_source_pack": {
            "status": "source_pack_vendored",
            "repo_relative_path": "data/revenue_model_source_pack/2026_05_19",
            "source_pack_version": "2026_05_19",
            "raw_workbook_sha256": "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b",
            "source_pack_manifest_sha256": "abc123",
            "dashboard_default_selections": {"series": "Total NLTF revenue"},
            "source_workbook_selections": {"series": "Total RUC+PED revenue"},
            "default_selection_policy": "Revenue Outlook defaults to Total NLTF revenue.",
        },
        "bridge_status_by_stream": {
            "PED": ["ped_bridge_source_history_missing"],
            "LIGHT_RUC": ["nominal_rate_missing"],
        },
        "output_hashes": {
            "future_revenue_forecasts.parquet": {"sha256": "f" * 64},
        },
    }

    view = _revenue_outlook_manifest_table(manifest).set_index("Field")

    assert view.loc["Revenue source pack", "Value"] == "2026_05_19"
    assert view.loc["Raw workbook SHA256", "Value"] == "00c6070694818d27d7c402749354d8175de999894846dce45a4abdd7f5eb3e6b"
    assert view.loc["Dashboard default series", "Value"] == "Total NLTF revenue"
    assert view.loc["Workbook current series", "Value"] == "Total RUC+PED revenue"
    assert view.loc["Bridge status: PED VKT per capita", "Value"] == "ped_bridge_source_history_missing"
    assert view.loc["Bridge status: Light RUC volume", "Value"] == "nominal_rate_missing"
    assert view.loc["Output SHA256: future_revenue_forecasts.parquet", "Value"] == "f" * 64
    assert "C:\\Users" not in view.to_csv()
    assert "Downloads" not in view.to_csv()

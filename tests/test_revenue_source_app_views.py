from __future__ import annotations

from itertools import product
from pathlib import Path

import pandas as pd

from app import (
    REVENUE_SOURCE_HORIZON_OPTIONS,
    REVENUE_SOURCE_PACK_CACHE_REVISION,
    _source_axis_title,
    _source_component_long_form_options,
    _source_component_long_form_view,
    _source_component_figure,
    _source_control_gap_messages,
    _source_gap_register_for_controls,
    _source_hybrid_annual_view,
    _source_horizon_bounds,
    _source_path_trace_status_for_controls,
    _source_reconciliation_view,
    _filter_revenue_outlook_rows,
    _revenue_outlook_manifest_table,
    _resolve_revenue_source_control_applicability,
    _scenario_color_map,
    _selected_source_series_frame,
    _source_split_figure,
    _source_total_path_figure,
    _source_uncertainty_figure,
    revenue_outlook_figure,
    revenue_outlook_composition_figure,
    revenue_outlook_component_figure,
    revenue_outlook_split_figure,
    revenue_outlook_total_path_figure,
    revenue_outlook_uncertainty_fan_figure,
)
from model_dashboard.revenue_outlook import (
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_NONE,
    FAN_SOURCE_SCENARIO_SPREAD,
)
from model_dashboard.revenue_source_pack import REVENUE_SOURCE_PACK_RUNTIME_REVISION, load_revenue_source_pack


ROOT = Path(__file__).resolve().parents[1]


def test_revenue_source_pack_cache_revision_tracks_loader_runtime_revision() -> None:
    assert REVENUE_SOURCE_PACK_CACHE_REVISION == REVENUE_SOURCE_PACK_RUNTIME_REVISION


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
    assert by_id.loc["crown_top_up_values_missing", "availability_status"] == "available"
    assert by_id.loc["crown_top_up_values_missing", "current_selection"] == "Include"
    assert by_id.loc["crown_top_up_values_missing", "runtime_treatment"] == "top_up_rows_available"
    assert "repo-vendored" in by_id.loc["crown_top_up_values_missing", "user_visible_message"]

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
    assert by_id.loc["fed_path_scenario_values_missing", "availability_status"] == "available"
    assert by_id.loc["fed_path_scenario_values_missing", "current_selection"] == "No 2027 12c uplift"
    assert by_id.loc["fed_path_scenario_values_missing", "runtime_treatment"] == "fed_path_values_available"
    assert "fed_rate_paths.csv" in by_id.loc["fed_path_scenario_values_missing", "user_visible_message"]
    assert not _source_control_gap_messages(pack, {"fed_path": "No 2027 12c uplift"})


def test_selected_source_series_applies_value_backed_revenue_basis_without_relabeling() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    path_gross = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_path": "Gross / benchmark actual"})
    assert set(path_gross["revenue_basis"]) == {"gross"}
    assert {"Gross PED revenue", "Gross PED exGST"}.issubset(set(path_gross["source_series_label"]))

    gross = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_basis": "Gross"})
    assert set(gross["revenue_basis"]) == {"gross"}
    assert {"Gross PED revenue", "Gross PED exGST"}.issubset(set(gross["source_series_label"]))

    nominal = _selected_source_series_frame(pack, {"series": "PED revenue", "revenue_basis": "Nominal ex GST"})
    assert set(nominal["revenue_basis"]) == {"nominal_ex_gst"}
    assert {"PED revenue", "PED raw actual exGST"}.issubset(set(nominal["source_series_label"]))

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

    view = _source_reconciliation_view(pack, {"selected_fy": "FY2025"})

    assert not view.empty
    assert "optional_inputs_applied" in view.columns
    assert set(view["scope"]) == {"official_actuals"}


def test_hybrid_annual_view_exposes_replacement_audit_for_selected_fy() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    view = _source_hybrid_annual_view(pack, {"selected_fy": "FY2031"})

    assert not view.empty
    assert set(view["FY"]) == {2031}
    assert {"row_role", "source_file", "residual_vs_official", "replacement_only"}.issubset(view.columns)
    replacements = view[view["replacement_only"].astype(bool)]
    assert set(replacements["series_id"]) == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}
    assert set(replacements["fed_path"]) == {"Current planned path"}
    replacement_sources = replacements.groupby("series_id")["source_file"].agg(lambda values: set(values))
    assert replacement_sources.loc["gross_ped_revenue"] == {
        "data/current_revenue_outlook/revenue_chart_rows.csv; ped_bridge_inputs.csv; fed_rate_paths.csv"
    }
    assert replacement_sources.loc["light_ruc_net_revenue"] == {
        "data/current_revenue_outlook/revenue_chart_rows.csv; official_befu25_annual.csv"
    }
    assert replacement_sources.loc["heavy_ruc_net_revenue"] == {
        "data/current_revenue_outlook/revenue_chart_rows.csv; official_befu25_annual.csv"
    }
    assert {"population_count", "ped_total_vkt", "ped_litres_per_100km"}.issubset(set(view["series_id"]))
    assert view[view["row_role"].eq("calculated_rollup")]["residual_vs_official"].notna().any()

    no_uplift = _source_hybrid_annual_view(
        pack,
        {"selected_fy": "FY2031", "fed_path": "No 2027 12c uplift"},
    )
    current_ped = float(replacements[replacements["series_id"].eq("gross_ped_revenue")]["value"].iloc[0])
    no_uplift_ped = float(no_uplift[no_uplift["series_id"].eq("gross_ped_revenue")]["value"].iloc[0])
    assert no_uplift_ped < current_ped


def test_hybrid_annual_view_applies_crown_top_up_only_when_selected() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    exclude = _source_hybrid_annual_view(pack, {"selected_fy": "FY2026", "crown_top_up": "Exclude"})
    include = _source_hybrid_annual_view(pack, {"selected_fy": "FY2026", "crown_top_up": "Include"})

    excluded_top_up = float(exclude[exclude["series_id"].eq("crown_top_up")]["value"].iloc[0])
    included_top_up = include[include["series_id"].eq("crown_top_up")]["value"].iloc[0]
    excluded_total = float(exclude[exclude["series_id"].eq("total_nltf_net_revenue")]["value"].iloc[0])
    included_total = float(include[include["series_id"].eq("total_nltf_net_revenue")]["value"].iloc[0])

    assert excluded_top_up == 0.0
    assert pd.isna(included_top_up)
    assert included_total == excluded_total
    assert set(include[include["series_id"].eq("crown_top_up")]["availability_status"]) == {"missing"}


def test_revenue_source_horizon_control_limits_path_chart_without_selected_fy_coupling() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    controls = {
        "series": "Total NLTF revenue",
        "release_round": "BEFU25",
        "model_basis": "Current finalist ensemble",
        "selected_fy": "FY2031",
        "horizon": "Next 5 FY",
    }
    fig = _source_total_path_figure(pack, controls)
    lower, upper = _source_horizon_bounds(pack, controls)

    assert REVENUE_SOURCE_HORIZON_OPTIONS == ["Next 5 FY", "To FY2031", "Full common horizon"]
    assert lower is not None and upper is not None
    assert upper - lower == 4
    assert fig.data
    for trace in fig.data:
        xs = [int(x) for x in getattr(trace, "x", []) if x is not None]
        if xs:
            assert min(xs) >= lower
            assert max(xs) <= upper

    audit = _source_hybrid_annual_view(pack, controls)
    assert set(audit["FY"]) == {2031}


def test_component_deduction_long_form_is_selectable_signed_and_download_ready() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    controls = {
        "selected_fy": "FY2031",
        "fed_path": "No 2027 12c uplift",
        "crown_top_up": "Exclude",
    }
    view = _source_component_long_form_view(pack, controls)

    required = {
        "FY",
        "fed_path",
        "series_id",
        "display_name",
        "component_class",
        "value",
        "sign",
        "signed_value",
        "unit",
        "release_path_provenance",
        "source_file",
        "replacement_flag",
        "availability_status",
    }
    assert required.issubset(view.columns)
    assert set(view["FY"]) == {2031}
    assert set(view["fed_path"]) == {"No 2027 12c uplift"}
    assert _source_component_long_form_options(view)

    fed_refunds = view[view["series_id"].eq("fed_refunds")].iloc[0]
    assert fed_refunds["component_class"] == "Deduction"
    assert int(fed_refunds["sign"]) == -1
    assert float(fed_refunds["signed_value"]) == -float(fed_refunds["value"])

    replacements = view[view["replacement_flag"].astype(bool)]
    assert set(replacements["series_id"]) == {"gross_ped_revenue", "light_ruc_net_revenue", "heavy_ruc_net_revenue"}
    assert replacements["release_path_provenance"].astype(str).str.contains("FED path: No 2027 12c uplift").all()
    assert replacements["source_file"].astype(str).str.len().gt(0).all()
    assert view["availability_status"].astype(str).str.len().gt(0).all()
    assert "C:\\Users" not in view.to_csv(index=False)
    assert "Downloads" not in view.to_csv(index=False)
    assert "OneDrive" not in view.to_csv(index=False)

    selected = _source_component_long_form_view(
        pack,
        {**controls, "component_filter": ["FED refunds", "Gross PED revenue"]},
    )
    assert set(selected["series_id"]) == {"fed_refunds", "gross_ped_revenue"}


def test_full_common_horizon_stops_at_last_fixed_or_replacement_row() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    controls = {
        "series": "Total NLTF revenue",
        "release_round": "BEFU25",
        "model_basis": "Current finalist ensemble",
        "horizon": "Full common horizon",
    }
    lower, upper = _source_horizon_bounds(pack, controls)
    fig = _source_total_path_figure(pack, controls)

    assert (lower, upper) == (2025, 2031)
    for trace in fig.data:
        xs = [int(x) for x in getattr(trace, "x", []) if x is not None]
        if xs:
            assert min(xs) >= 2025
            assert max(xs) <= 2031


def test_path_trace_status_view_reflects_active_release_selection() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    view = _source_path_trace_status_for_controls(pack, {"release_round": "HYEFU24"})

    by_id = view.set_index("trace_id")
    release_traces = by_id.loc[["selected_mot_befu_release", "rolling_befu_1y"]]
    assert set(release_traces["current_selection"]) == {"HYEFU24"}
    assert set(release_traces["availability_status"]) == {"available"}
    assert release_traces["plotted"].astype(bool).all()
    assert set(release_traces["blocking_gap_id"]) == {""}


def test_total_path_chart_plots_vendored_release_paths_from_source_rows() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    fig = _source_total_path_figure(
        pack,
        {
            "series": "Total NLTF revenue",
            "release_round": "BEFU25",
            "model_basis": "Current finalist ensemble",
            "selected_fy": "FY2031",
        },
    )

    by_name = {trace.name: trace for trace in fig.data}
    expected_release_traces = {
        "Official comparator: selected MOT/BEFU",
        "Official comparator: rolling BEFU 1Y",
    }
    assert expected_release_traces.issubset(set(by_name))
    for name in expected_release_traces:
        trace = by_name[name]
        assert len([value for value in trace.y if value is not None]) > 0
        assert list(trace.x) != [None]
    assert "Current finalist forecast" in by_name
    assert len([value for value in by_name["Current finalist forecast"].y if value is not None]) > 0
    forbidden = {
        "Hybrid replacement-only outlook",
        "In-house prediction / forecast",
        "Legacy workbook selected basis",
        "Legacy workbook model",
        "Legacy workbook Schiff model",
        "Actual to date (3 of 4 quarters)",
    }
    assert not forbidden.intersection(by_name)
    assert not any(str(name).endswith("(BEFU25 gap)") for name in by_name)


def test_total_path_chart_uses_source_actual_anchor_and_current_finalist_nowcast() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    fig = _source_total_path_figure(
        pack,
        {
            "series": "Total NLTF revenue",
            "release_round": "BEFU25",
            "model_basis": "Current finalist ensemble",
            "selected_fy": "FY2031",
        },
    )
    by_name = {trace.name: trace for trace in fig.data}

    actual = by_name["Actual"]
    assert 2026 not in [int(value) for value in actual.x]
    assert max(int(value) for value in actual.x) == 2025

    assert "Actual to date (3 of 4 quarters)" not in by_name
    assert "In-house prediction / forecast" not in by_name
    assert "Legacy workbook selected basis" not in by_name
    assert min(int(value) for value in by_name["Official comparator: selected MOT/BEFU"].x) == 2026

    current = pack.current_forecast_annual[
        pack.current_forecast_annual["series_id"].eq("total_nltf_net_revenue")
        & pack.current_forecast_annual["scenario_name"].eq("current_basecase")
        & pack.current_forecast_annual["fed_path"].eq("Current planned path")
        & pack.current_forecast_annual["FY"].eq(2026)
    ]
    assert not current.empty
    finalist = by_name["Current finalist forecast"]
    finalist_x = list(map(int, finalist.x))
    assert finalist_x[0] == 2025
    assert finalist_x[1] == 2026
    assert abs(float(finalist.y[0]) - float(actual.y[-1])) <= 1e-9
    first_forecast_idx = finalist_x.index(2026)
    assert abs(float(finalist.y[first_forecast_idx]) - float(current.iloc[0]["value"])) <= 1e-9
    anchor_hover = finalist.customdata[0]
    nowcast_hover = finalist.customdata[first_forecast_idx]
    assert anchor_hover[1] == "Actual anchor"
    assert anchor_hover[5] == "Q41"
    assert nowcast_hover[1] == "Current-finalist FY nowcast (2 actual + 2 forecast)"
    assert nowcast_hover[2] == "actual: 2025Q3; 2025Q4; forecast: 2026Q1; 2026Q2"
    assert nowcast_hover[3] == "source_backed"
    assert nowcast_hover[6] == "True"

    marker_shapes = {(int(shape.x0), shape.line.dash) for shape in fig.layout.shapes}
    assert (2026, "dash") in marker_shapes
    assert (2031, "dot") in marker_shapes


def test_revenue_source_control_applicability_resolves_invalid_series_controls() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None

    activity_controls, activity_messages = _resolve_revenue_source_control_applicability(
        pack,
        {
            "series": "Light RUC net km",
            "revenue_path": "Net of admin fees & refunds",
            "revenue_basis": "Net",
            "fed_path": "No 2027 12c uplift",
            "crown_top_up": "Include",
        },
    )
    assert activity_controls["revenue_basis"] == "Not applicable"
    assert activity_controls["fed_path"] == "Not applicable"
    assert activity_controls["crown_top_up"] == "Exclude"
    assert any("activity/volume series" in message for message in activity_messages)

    ped_controls, ped_messages = _resolve_revenue_source_control_applicability(
        pack,
        {
            "series": "PED revenue",
            "revenue_path": "Net of admin fees & refunds",
            "revenue_basis": "Net",
            "fed_path": "Current planned path",
            "crown_top_up": "Exclude",
        },
    )
    assert ped_controls["revenue_basis"] == "Gross"
    assert ped_controls["revenue_path"] == "Gross / benchmark actual"
    assert any("does not support revenue basis" in message for message in ped_messages)


def test_revenue_source_every_series_valid_control_permutation_has_governed_traces() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    contract = pack.series_trace_contract
    assert not contract.empty

    series_control = [
        control
        for control in pack.front_end_config.get("controls", [])
        if isinstance(control, dict) and control.get("control_id") == "series"
    ][0]
    assert len(contract) == len(series_control["options"])

    for row in contract.to_dict("records"):
        series = str(row["series_option"])
        valid_bases = [value.strip() for value in str(row["valid_bases"]).split(";") if value.strip()]
        valid_controls = {value.strip() for value in str(row["valid_controls"]).split(";") if value.strip()}
        fed_paths = ["Current planned path", "No 2027 12c uplift"] if "fed_path" in valid_controls else ["Current planned path"]
        crown_top_ups = ["Exclude", "Include"] if "crown_top_up" in valid_controls else ["Exclude"]

        for basis, fed_path, crown_top_up, time_grain in product(
            valid_bases,
            fed_paths,
            crown_top_ups,
            ["June-year", "Quarterly"],
        ):
            controls = {
                "series": series,
                "release_round": "BEFU25",
                "model_basis": "Current finalist ensemble",
                "selected_fy": "FY2031",
                "horizon": "To FY2031",
                "revenue_basis": basis,
                "revenue_path": (
                    "Gross / benchmark actual"
                    if basis == "Gross"
                    else "Net of admin fees & refunds"
                    if basis == "Net"
                    else "Not applicable"
                ),
                "fed_path": fed_path,
                "crown_top_up": crown_top_up,
                "time_grain": time_grain,
            }
            resolved, _messages = _resolve_revenue_source_control_applicability(pack, controls)
            frame = _selected_source_series_frame(pack, resolved)
            assert not frame.empty, (series, basis, fed_path, crown_top_up, time_grain)

            fig = _source_total_path_figure(pack, resolved)
            assert fig.data, (series, basis, fed_path, crown_top_up, time_grain)
            names = {trace.name for trace in fig.data}
            assert "Selected dashboard basis" not in names
            assert "Aaron Schiff" not in names
            assert "Actual to date (3 of 4 quarters)" not in names
            assert "Legacy workbook selected basis" not in names
            assert "Legacy workbook model" not in names
            assert "Legacy workbook Schiff model" not in names

            if "Actual" in names:
                actual = next(trace for trace in fig.data if trace.name == "Actual")
                assert max(int(value) for value in actual.x if value is not None) <= 2025
            if "Current finalist forecast" in names:
                current = next(trace for trace in fig.data if trace.name == "Current finalist forecast")
                assert min(int(value) for value in current.x if value is not None) >= 2025
                source_cells = [
                    str(customdata[5])
                    for customdata in current.customdata
                    if customdata is not None and len(customdata) > 5
                ]
                assert source_cells
                assert "annual_model_paths.csv" not in "; ".join(source_cells)
                assert any("current_revenue_outlook" in cell for cell in source_cells if cell != "Q41")

            for trace in fig.data:
                if not getattr(trace, "customdata", None) is None:
                    for customdata in trace.customdata:
                        assert str(customdata[0]).strip()


def test_revenue_source_charts_use_explicit_units_and_annual_ticks() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    controls = {
        "series": "Total NLTF revenue",
        "release_round": "BEFU25",
        "model_basis": "Current finalist ensemble",
        "selected_fy": "FY2031",
    }
    frame = pack.canonical_long[pack.canonical_long["series_id"].eq("total_nltf_net_revenue")]

    assert _source_axis_title(frame) == "$m nominal ex GST"

    total_fig = _source_total_path_figure(pack, controls)
    uncertainty_fig = _source_uncertainty_figure(pack, controls)
    component_fig = _source_component_figure(pack, controls)
    split_fig = _source_split_figure(pack, controls)
    assert total_fig.layout.yaxis.title.text == "$m nominal ex GST"
    assert total_fig.layout.xaxis.title.text == "June year"
    assert total_fig.layout.xaxis.tickmode == "linear"
    assert total_fig.layout.xaxis.dtick == 1
    if uncertainty_fig.data:
        assert uncertainty_fig.layout.yaxis.title.text == "$m nominal ex GST"
        assert uncertainty_fig.layout.xaxis.title.text == "June year"
        assert uncertainty_fig.layout.xaxis.tickmode == "linear"
        assert uncertainty_fig.layout.xaxis.dtick == 1
    else:
        assert uncertainty_fig.layout.annotations
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
        "model_basis": "Current finalist ensemble",
        "selected_fy": "FY2031",
        "uncertainty": "MOT release round",
    }

    mot_fig = _source_uncertainty_figure(pack, controls)

    assert not mot_fig.data
    assert "archived horizon-specific error bands" in mot_fig.layout.annotations[0].text

    removed_fallback = _source_uncertainty_figure(pack, {**controls, "uncertainty": "Removed workbook model spread"})
    assert not removed_fallback.data
    assert "governed gap" in removed_fallback.layout.annotations[0].text or "unavailable" in removed_fallback.layout.annotations[0].text


def test_uncertainty_source_control_uses_mot_archived_error_bands_when_available() -> None:
    pack = load_revenue_source_pack(repo_root=ROOT)
    assert pack is not None
    controls = {
        "series": "Total RUC+PED revenue",
        "release_round": "BEFU25",
        "model_basis": "Current finalist ensemble",
        "selected_fy": "FY2031",
        "uncertainty": "MOT release round",
    }

    mot_fig = _source_uncertainty_figure(pack, controls)

    by_name = {trace.name: trace for trace in mot_fig.data}
    assert {"MOT archived error 80% band", "MOT archived error 50% band", "Official comparator: selected MOT/BEFU"}.issubset(by_name)
    selected = by_name["Official comparator: selected MOT/BEFU"]
    assert len(selected.y) > 0
    assert min(row[2] for row in selected.customdata) >= 10


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
    forecast_trace = next(trace for trace in fig.data if trace.name == "Base case")
    marker_trace = next(trace for trace in fig.data if trace.name == "Base case markers")
    forecast_hover = [custom[0] for custom in forecast_trace.customdata]
    marker_hover = [custom[0] for custom in marker_trace.customdata]

    assert "_" not in forecast_trace.name
    assert any("H1-H12 backtest-supported horizon" in label for label in forecast_hover)
    assert any("H13+ long-range extrapolation" in label for label in forecast_hover)
    assert "Forecast start (H1)" in marker_hover
    assert "Long-range extrapolation begins (H13)" in marker_hover


def test_revenue_outlook_scenario_colors_are_stable_under_filters() -> None:
    rows = pd.DataFrame(
        [
            {
                "row_type": "future_forecast",
                "scenario_name": "current_basecase",
                "scenario_role": "basecase",
            },
            {
                "row_type": "future_forecast",
                "scenario_name": "current_comparison_1",
                "scenario_role": "comparison",
            },
            {
                "row_type": "future_forecast",
                "scenario_name": "current_comparison_2",
                "scenario_role": "comparison",
            },
        ]
    )

    full_map = _scenario_color_map(rows)
    comparison_only = _scenario_color_map(rows[rows["scenario_name"].eq("current_comparison_1")])
    second_comparison_only = _scenario_color_map(rows[rows["scenario_name"].eq("current_comparison_2")])

    assert full_map["current_basecase"] == "#006FAD"
    assert full_map["current_comparison_1"] == "#E56B2B"
    assert full_map["current_comparison_2"] == "#00843D"
    assert comparison_only["current_comparison_1"] == full_map["current_comparison_1"]
    assert second_comparison_only["current_comparison_2"] == full_map["current_comparison_2"]


def test_revenue_outlook_primary_figures_use_runtime_pack_selected_series_only() -> None:
    chart = pd.read_csv(ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.csv")
    bridge = pd.read_csv(ROOT / "data" / "current_revenue_outlook" / "revenue_bridge_components.csv")
    traces = [
        "Actual",
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
    ]

    rows = _filter_revenue_outlook_rows(
        chart,
        time_grain="june_year",
        stream_labels=["Total NLTF revenue"],
        fed_paths=["Current planned path"],
        trace_names=traces,
    )
    total_fig = revenue_outlook_total_path_figure(rows, selected_series="Total NLTF revenue", selected_fy="FY2031")
    trace_names = {str(trace.name) for trace in total_fig.data if trace.name}
    annotation_text = " ".join(str(annotation.text) for annotation in total_fig.layout.annotations or [])

    assert set(traces).issubset(trace_names)
    assert "Forecast start FY2026" in annotation_text
    assert "Current finalist forecast" not in trace_names
    assert not any("Schiff" in name or "selected_dashboard" in name for name in trace_names)
    assert all(
        getattr(trace, "x", None) is None or "FY2031" in list(trace.x)
        for trace in total_fig.data
        if trace.name == "Current finalist Base case"
    )

    fan_availability = pd.read_csv(ROOT / "data/current_revenue_outlook/fan_availability.csv")
    fan_bands = pd.read_csv(ROOT / "data/current_revenue_outlook/fan_band_rows.csv")
    fan_fig = revenue_outlook_uncertainty_fan_figure(
        fan_bands,
        fan_availability=fan_availability,
        selected_series="Total NLTF revenue",
        fan_source=FAN_SOURCE_CURRENT_BACKTEST,
        selected_fed_path="Current planned path",
    )
    fan_text = " ".join(str(annotation.text) for annotation in fan_fig.layout.annotations or [])
    assert "not been propagated" in fan_text

    spread_fig = revenue_outlook_uncertainty_fan_figure(
        fan_bands,
        fan_availability=fan_availability,
        selected_series="Total NLTF revenue",
        fan_source=FAN_SOURCE_SCENARIO_SPREAD,
        selected_fed_path="Current planned path",
    )
    assert spread_fig.data
    assert not any("confidence" in str(trace.name).lower() or "probability" in str(trace.name).lower() for trace in spread_fig.data)

    none_fig = revenue_outlook_uncertainty_fan_figure(
        fan_bands,
        fan_availability=fan_availability,
        selected_series="Total NLTF revenue",
        fan_source=FAN_SOURCE_NONE,
        selected_fed_path="Current planned path",
    )
    none_text = " ".join(str(annotation.text) for annotation in none_fig.layout.annotations or [])
    assert "Fan intentionally disabled" in none_text

    # The fan uses its own source selector and runtime fan tables; narrowing main path traces
    # changes the path chart rows but does not remove the fan bands.
    actual_only_rows = _filter_revenue_outlook_rows(
        chart,
        time_grain="june_year",
        stream_labels=["Total NLTF revenue"],
        fed_paths=["Current planned path"],
        trace_names=["Actual"],
    )
    assert set(actual_only_rows["trace_name"].dropna().astype(str)) == {"Actual"}
    independent_fan = revenue_outlook_uncertainty_fan_figure(
        fan_bands,
        fan_availability=fan_availability,
        selected_series="Total NLTF revenue",
        fan_source=FAN_SOURCE_SCENARIO_SPREAD,
        selected_fed_path="Current planned path",
    )
    assert independent_fan.data

    component_fig = revenue_outlook_component_figure(bridge, selected_fy="FY2031", selected_fed_path="Current planned path")
    split_fig = revenue_outlook_split_figure(bridge, selected_fy="FY2031", selected_fed_path="Current planned path")
    assert component_fig.data
    assert split_fig.data


def test_revenue_outlook_composition_figure_stacks_components_and_overlays_aggregates() -> None:
    stack = pd.read_csv(ROOT / "data/current_revenue_outlook/revenue_stack_components.csv")
    source = "Current finalist Base case"
    view = stack[
        stack["source_path"].astype(str).eq(source)
        & pd.to_numeric(stack["FY"], errors="coerce").between(2026, 2031)
        & stack["section"].astype(str).isin(["RUC", "FED", "MVR", "TUC", "Totals"])
    ].copy()

    fig = revenue_outlook_composition_figure(
        view,
        source_path=source,
        composition_mode="Gross contribution stack",
        overlays=["Total gross revenues"],
    )

    assert fig.data
    bar_names = {str(trace.name) for trace in fig.data if trace.type == "bar"}
    scatter_names = {str(trace.name) for trace in fig.data if trace.type == "scatter"}
    assert "Gross FED" not in bar_names
    assert "Total gross revenues" not in bar_names
    assert "FED refunds" not in bar_names
    assert "RUC refunds" in bar_names
    assert "MR13/COO" in bar_names
    assert "Total gross revenues overlay" in scatter_names
    assert fig.layout.barmode == "relative"
    assert fig.layout.yaxis.title.text == "$m nominal ex GST"
    assert not any("Schiff" in str(trace.name) or "selected_dashboard" in str(trace.name) for trace in fig.data)
    hover_templates = "\n".join(str(trace.hovertemplate) for trace in fig.data)
    assert "stack total" in hover_templates
    assert "source_file" not in hover_templates
    assert "<extra></extra>" in hover_templates
    for raw_identifier in ["source_file", "source_cell", "model_id", "formula", "quarter_composition"]:
        assert raw_identifier not in hover_templates

    bridge_view = stack[
        stack["source_path"].astype(str).eq("MBU26 official")
        & stack["composition_mode"].astype(str).eq("Gross-to-net bridge audit")
        & pd.to_numeric(stack["FY"], errors="coerce").between(2001, 2005)
        & stack["section"].astype(str).isin(["RUC", "FED", "MVR", "TUC", "Totals"])
    ].copy()
    bridge_fig = revenue_outlook_composition_figure(
        bridge_view,
        source_path="MBU26 official",
        composition_mode="Gross-to-net bridge audit",
        overlays=["Total NLTF revenue"],
    )
    bridge_bar_names = {str(trace.name) for trace in bridge_fig.data if trace.type == "bar"}
    bridge_scatter_names = {str(trace.name) for trace in bridge_fig.data if trace.type == "scatter"}
    assert "RUC refunds" in bridge_bar_names
    assert "MR13/COO" in bridge_bar_names
    assert "RUC refunds gross add-back" in bridge_bar_names
    assert "MR13/COO gross add-back" in bridge_bar_names
    assert "Gross RUC" not in bridge_bar_names
    assert "Gross FED" not in bridge_bar_names
    assert "Total NLTF revenue overlay" in bridge_scatter_names
    assert bridge_fig.layout.barmode == "overlay"
    assert any(getattr(trace, "base", None) is not None for trace in bridge_fig.data if trace.type == "bar")
    assert any(min(float(value) for value in trace.y) < 0 for trace in bridge_fig.data if trace.type == "bar")


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

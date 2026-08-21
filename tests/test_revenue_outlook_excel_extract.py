"""Template-matched XLSX forecast extract (BEFU26 layout, FY2001-FY2050).

Contract (owner request, 2026-08): one worksheet per selected scenario path,
rows 1-65 exactly as the reference workbook (row 65 = Total net revenues),
years B:AY ending FY2050, all page levers (Fleet efficiency incl. Custom, PT
mode shift, uptake, 12c policy) reflected in the exported numbers, blanks -
never zeros - where a line item is not governed for a path.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

import app
from model_dashboard.revenue_outlook import (
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_outlook_excel_extract import (
    EXTRACT_LAST_ROW,
    LAST_DATA_COLUMN,
    ROW_SERIES,
    TEMPLATE_RELATIVE_PATH,
    RevenueOutlookExtractError,
    build_revenue_outlook_extract,
    extract_sheet_name,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / TEMPLATE_RELATIVE_PATH

DEFAULT_TRACES = (
    "Actual",
    "PREBU26 official",
    "Current finalist Base case",
    "Current finalist High population/comparison",
)


@pytest.fixture(scope="module")
def extract_context():
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    return pack, signature


def _default_uptake_key():
    return (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)


def _extract(extract_context, traces, sensitivity_key=None):
    pack, signature = extract_context
    key = sensitivity_key or app.selected_sensitivity_key("Off", "Off", "Off")
    return app.cached_revenue_outlook_extract_bytes(
        signature, key, PED_BRIDGE_DEFAULT_MODE, _default_uptake_key(), tuple(traces), pack
    )


def _workbook(result):
    return load_workbook(io.BytesIO(result.workbook_bytes))


def _row_values(worksheet, row):
    return {
        int(worksheet.cell(row=1, column=column).value): worksheet.cell(row=row, column=column).value
        for column in range(2, LAST_DATA_COLUMN + 1)
    }


@pytest.fixture(scope="module")
def default_result(extract_context):
    return _extract(extract_context, DEFAULT_TRACES)


@pytest.fixture(scope="module")
def custom_fleet_result(extract_context):
    key = app.selected_sensitivity_key(
        "Custom", "Off", "Off", custom_fleet_efficiency_pct=10.0
    )
    return _extract(extract_context, DEFAULT_TRACES, key)


@pytest.fixture(scope="module")
def pt_result(extract_context):
    key = app.selected_sensitivity_key("Off", "Med", "Off")
    return _extract(extract_context, DEFAULT_TRACES, key)


# ---------------------------------------------------------------------------
# worksheet inventory and layout
# ---------------------------------------------------------------------------


def test_single_selected_path_creates_one_worksheet(extract_context) -> None:
    result = _extract(extract_context, ("Actual", "Current finalist Base case"))
    assert result.sheet_names == ["Current Base"]
    assert result.exported_traces == ["Current finalist Base case"]


def test_three_selected_paths_create_three_worksheets(default_result) -> None:
    assert default_result.sheet_names == [
        "PREBU26 Official",
        "Current Base",
        "High Population",
    ]
    assert not default_result.skipped_traces


def test_conflict_trace_exports_from_the_aligned_frames(extract_context) -> None:
    result = _extract(
        extract_context,
        ("Current finalist Base case", "Middle East conflict: Medium"),
    )
    assert result.sheet_names == ["Current Base", "Conflict Medium"]


def test_every_sheet_is_a1_ay65_with_no_fy2051_columns(default_result) -> None:
    workbook = _workbook(default_result)
    for name in workbook.sheetnames:
        worksheet = workbook[name]
        assert worksheet.max_row == EXTRACT_LAST_ROW, name
        assert worksheet.max_column == LAST_DATA_COLUMN, name
        assert int(worksheet.cell(row=1, column=LAST_DATA_COLUMN).value) == 2050, name
        assert worksheet.cell(row=1, column=LAST_DATA_COLUMN + 1).value is None, name


def test_row_labels_match_the_reference_template_exactly(default_result) -> None:
    template = load_workbook(TEMPLATE_PATH)["Baseline"]
    expected = [template.cell(row=row, column=1).value for row in range(1, EXTRACT_LAST_ROW + 1)]
    workbook = _workbook(default_result)
    for name in workbook.sheetnames:
        worksheet = workbook[name]
        got = [worksheet.cell(row=row, column=1).value for row in range(1, EXTRACT_LAST_ROW + 1)]
        assert got == expected, name
    assert expected[EXTRACT_LAST_ROW - 1] == "Total net revenues (m $)"


def test_period_row_classifies_actual_st_and_lt_segments(default_result) -> None:
    workbook = _workbook(default_result)
    for name in workbook.sheetnames:
        worksheet = workbook[name]
        for column in range(2, LAST_DATA_COLUMN + 1):
            year = int(worksheet.cell(row=1, column=column).value)
            period = str(worksheet.cell(row=2, column=column).value)
            if year <= 2025:
                assert period == "ACTUAL", (name, year)
            elif year <= 2030:
                assert period == "ST_FORECAST", (name, year)
            else:
                assert period == "LT_FORECAST", (name, year)


def test_no_formula_error_tokens_and_workbook_reopens(default_result) -> None:
    workbook = _workbook(default_result)  # re-open is itself the parse check
    errors = {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NULL!", "#NUM!"}
    for name in workbook.sheetnames:
        for row in workbook[name].iter_rows(values_only=True):
            for value in row:
                assert not (isinstance(value, str) and value.strip() in errors), name
                # No formulas at all: the reference extract is hardcoded values.
                assert not (isinstance(value, str) and value.startswith("=")), name


def test_sheet_names_are_valid_unique_and_readable() -> None:
    taken: set[str] = set()
    first = extract_sheet_name("Current finalist Base case", taken)
    duplicate = extract_sheet_name("Current finalist Base case", taken)
    awkward = extract_sheet_name("A[very]:long/trace*name?" + "x" * 40, taken)
    for name in (first, duplicate, awkward):
        assert 0 < len(name) <= 31
        assert not set(name) & set(':\\/?*[]')
    assert first == "Current Base"
    assert duplicate != first
    assert len({first, duplicate, awkward}) == 3


def test_export_refuses_when_no_trace_resolves(extract_context) -> None:
    pack, _ = extract_context
    with pytest.raises(RevenueOutlookExtractError):
        build_revenue_outlook_extract(
            selected_traces=("Actual",),
            line_reconciliation=pack.revenue_line_reconciliation,
            stack_components=pack.revenue_stack_components,
            pack_stack_components=pack.revenue_stack_components,
            template_path=TEMPLATE_PATH,
        )


# ---------------------------------------------------------------------------
# values: canonical view identity and lever pass-through
# ---------------------------------------------------------------------------


def test_total_net_revenues_match_the_canonical_aligned_view(
    extract_context, default_result
) -> None:
    pack, signature = extract_context
    line, _, _, _ = app.cached_aligned_scenario_detail_frames(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off"),
        PED_BRIDGE_DEFAULT_MODE,
        _default_uptake_key(),
        pack,
    )
    line = line.copy()
    line["fy"] = pd.to_numeric(line["FY"], errors="coerce")
    workbook = _workbook(default_result)
    for sheet, source_path in [
        ("Current Base", "Current finalist Base case"),
        ("PREBU26 Official", "PREBU26 official"),
    ]:
        totals = _row_values(workbook[sheet], EXTRACT_LAST_ROW)
        for fy in (2026, 2030, 2050):
            expected = line[
                line["source_path"].astype(str).eq(source_path)
                & line["series_id"].astype(str).eq("total_nltf_net_revenue")
                & line["fy"].eq(fy)
            ]["value"]
            assert not expected.empty, (sheet, fy)
            assert float(totals[fy]) == pytest.approx(float(expected.iloc[0]), rel=1e-12), (
                sheet,
                fy,
            )


def test_custom_fleet_efficiency_changes_exported_ped_values(
    default_result, custom_fleet_result
) -> None:
    baseline = _row_values(_workbook(default_result)["Current Base"], 10)
    adjusted = _row_values(_workbook(custom_fleet_result)["Current Base"], 10)
    for fy, expected_factor in ((2026, 0.9), (2030, 0.9**5), (2031, 0.9**6), (2050, 0.9**25)):
        assert float(adjusted[fy]) == pytest.approx(
            float(baseline[fy]) * expected_factor, rel=1e-9
        ), fy
    revenue_baseline = _row_values(_workbook(default_result)["Current Base"], 40)
    revenue_adjusted = _row_values(_workbook(custom_fleet_result)["Current Base"], 40)
    assert float(revenue_adjusted[2050]) < float(revenue_baseline[2050])


def test_pt_mode_shift_changes_exported_light_activity(default_result, pt_result) -> None:
    for row in (5, 11):  # Light RUC net km, Light petrol VKT
        baseline = _row_values(_workbook(default_result)["Current Base"], row)
        adjusted = _row_values(_workbook(pt_result)["Current Base"], row)
        for fy, exponent in ((2026, 1), (2030, 5), (2050, 25)):
            assert float(adjusted[fy]) == pytest.approx(
                float(baseline[fy]) * (1 - 0.005) ** exponent, rel=1e-9
            ), (row, fy)
    heavy_baseline = _row_values(_workbook(default_result)["Current Base"], 6)
    heavy_adjusted = _row_values(_workbook(pt_result)["Current Base"], 6)
    for fy in (2026, 2050):
        assert float(heavy_adjusted[fy]) == float(heavy_baseline[fy]), fy


def test_official_sheet_is_not_altered_by_current_only_levers(
    default_result, custom_fleet_result
) -> None:
    baseline_wb = _workbook(default_result)["PREBU26 Official"]
    adjusted_wb = _workbook(custom_fleet_result)["PREBU26 Official"]
    for row in ROW_SERIES:
        assert _row_values(baseline_wb, row) == _row_values(adjusted_wb, row), row


def test_actual_year_history_is_scenario_invariant(default_result) -> None:
    workbook = _workbook(default_result)
    base = workbook["Current Base"]
    high = workbook["High Population"]
    for row in (5, 10, 65):
        base_values = _row_values(base, row)
        high_values = _row_values(high, row)
        for fy in range(2001, 2025):
            assert base_values[fy] == high_values[fy], (row, fy)


def test_percentage_rows_are_year_on_year_changes_of_the_levels(default_result) -> None:
    worksheet = _workbook(default_result)["Current Base"]
    levels = _row_values(worksheet, 5)
    changes = _row_values(worksheet, 16)
    assert changes[2001] is None
    for fy in (2010, 2030, 2050):
        assert float(changes[fy]) == pytest.approx(
            float(levels[fy]) / float(levels[fy - 1]) - 1.0, rel=1e-12
        ), fy


def test_blank_line_items_stay_blank_not_zero(default_result) -> None:
    for sheet, labels in default_result.blank_rows.items():
        assert labels, sheet  # only genuinely blank rows are reported
    workbook = _workbook(default_result)
    # A cell with no governed value must be None, never 0.0-filled: check the
    # per-capita history the template itself leaves blank in FY2001.
    assert workbook["Current Base"].cell(row=12, column=2).value in (None,)


# ---------------------------------------------------------------------------
# page placement
# ---------------------------------------------------------------------------


def test_download_button_belongs_to_the_single_scenario_view() -> None:
    """The extract downloads from Single scenario; compare mode does not offer it."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    at.radio[0].set_value(app.REVENUE_OUTLOOK_PAGE)
    at.run()
    assert not at.exception
    labels = [str(element.proto.label) for element in at.get("download_button")]
    assert "Download forecast extract XLSX" in labels

    compare_radio = next(
        radio for radio in at.radio if app.REVENUE_OUTLOOK_VIEW_COMPARE in list(radio.options)
    )
    compare_radio.set_value(app.REVENUE_OUTLOOK_VIEW_COMPARE)
    at.run()
    assert not at.exception
    labels = [str(element.proto.label) for element in at.get("download_button")]
    assert "Download forecast extract XLSX" not in labels

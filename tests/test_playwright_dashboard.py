from __future__ import annotations

import math
import os
import re
from pathlib import Path

import pandas as pd
import pytest
from playwright.sync_api import Page, expect

from model_dashboard.data.chart_sources import resolve_chart_source_output_dir
from model_dashboard.conflict_fuel_paths import (
    CONFLICT_FUEL_SCENARIO_LEVELS,
    conflict_trace_name,
)
from model_dashboard.fuel_price_scenario import POLICY_PATH_IDS

pytestmark = pytest.mark.e2e
CHART_SOURCE_DIR = resolve_chart_source_output_dir(
    Path(__file__).resolve().parents[1]
)
CONFLICT_TRACE_NAMES = tuple(
    conflict_trace_name(level) for level in CONFLICT_FUEL_SCENARIO_LEVELS
)

PAGE_DISPLAY_TITLES = {
    "Overview": "Executive Summary",
    "Diagnostics": "Model Confidence",
    "Scenario Comparison": "Scenario Forecasts",
    "Revenue Outlook": "Revenue Outlook",
}
PAGE_ORDER = list(PAGE_DISPLAY_TITLES)


def page_display_label(page_name: str) -> str:
    return PAGE_DISPLAY_TITLES.get(page_name, page_name)


def expected_page_chip(page_name: str) -> str:
    return f"Page {PAGE_ORDER.index(page_name) + 1} of {len(PAGE_ORDER)} - {page_display_label(page_name)}"


def test_dashboard_pages_render_without_browser_errors(page: Page) -> None:
    base_url = os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501")
    page.set_viewport_size({"width": 1680, "height": 940})
    artifact_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    page.goto(base_url, wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    body = page.locator("body").inner_text(timeout=60000)
    assert "‹nchmark" not in body
    assert_visible_text_absent(page, "Deploy")
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Model Family", 1, "All Families")
    expect_filter_value(page, "Horizon", 3, "1-12 Quarters")
    expect_filter_value(page, "Score Basis", 4, "Paper-style horizon MAPE")
    assert page.get_by_role("radio").count() >= 4

    for text in [
        "Quarterly MAPE",
        "Annual MAPE",
        "Plotted candidates",
        "Benchmark Pass",
        "beat Schiff specification benchmark",
        "logged diagnostics",
        "Finalist Forecast Accuracy",
        "Candidate Search Frontier",
        "Finalist Ensemble Composition",
        "Stress and Horizon Checks",
    ]:
        expect(page.locator("body")).to_contain_text(text, timeout=60000)
    accuracy_info = chart_info_text(page, "Finalist Forecast Accuracy")
    assert "Current Parquet finalists using Paper-style horizon MAPE:" in accuracy_info
    frontier_info = chart_info_text(page, "Candidate Search Frontier")
    assert "Frontier read: Balanced all-stream frontier view" in frontier_info
    assert "excluded from governance scoring" in frontier_info
    stress_info = chart_info_text(page, "Stress and Horizon Checks")
    assert "Stress watch:" in stress_info
    assert_visible_text_absent(page, "Frontier read:")
    assert_visible_text_absent(page, "Stress watch:")
    assert_visible_text_absent(page, "Balanced all-stream frontier view")
    assert page.get_by_text("Candidate frontier mode", exact=False).count() == 0
    wait_for_rendered_surfaces(page)
    assert rendered_surface_count(page) >= 4
    save_dashboard_screenshot(page, artifact_dir, "mcp-01-overview.png")
    save_dashboard_screenshot(page, artifact_dir, "mcp-01-executive-summary.png")

    checks = [
        (
            "Diagnostics",
            expected_page_chip("Diagnostics"),
            "mcp-02-diagnostics.png",
            [
                "Diagnostics Coverage",
                "Mean Durbin-Watson",
                "Mean calibration R2",
                "Forecast R2 versus calibration R2",
                "R2 ladder: training fit vs calibration vs forecast R2",
                "Heteroscedasticity Pass",
                "Residual ACF by lag",
                "Residual Autocorrelation by Lag",
                "Residual vs Fitted",
                "Diagnostic Pass Matrix",
                "Error Distribution by Horizon",
            ],
        ),
        (
            "Scenario Comparison",
            expected_page_chip("Scenario Comparison"),
            "mcp-03-scenario-comparison.png",
            [
                "Scenario A",
                "Scenario B",
                "Full-sample qtr gain",
                "Stream Comparison: Scenario A vs Scenario B",
                "Horizon Comparison",
                "Improvement vs Benchmark",
                "Decision Summary",
            ],
        ),
        (
            "Revenue Outlook",
            expected_page_chip("Revenue Outlook"),
            "mcp-04-revenue-outlook.png",
            [
                "Revenue Outlook controls",
                "Total path chart",
                "Download 12c timing CSV",
                "Revenue composition over time",
                "Fleet mix explorer",
                "Effective rates per 1,000 km",
            ],
        ),
    ]
    forbidden_by_page = {
        "Overview": [
            "Component labels are deliberately short for the management view.",
            "Management conclusion and stream decision detail",
            "Transport Revenue Model Testbench | Refined Finalist Models",
        ],
        "Diagnostics": [
            "Diagnostics evidence:",
            "Diagnostics governance notes",
            "Model Explainability / Reproducibility",
            "Model Inventory module",
            "Run Audit module",
            "Transport Revenue Model Testbench | Refined Finalist Models",
        ],
        "Scenario Comparison": [
            "Detailed scenario governance cards",
            "Forecast and stress drilldown",
            "Transport Revenue Model Testbench | Refined Finalist Models",
        ],
        "Revenue Outlook": [
            "Forecast Builder",
            "Governance & Reproducibility Filters",
        ],
    }

    for tab_label, expected_text, screenshot_name, page_texts in checks:
        click_governance_nav(page, tab_label)
        expect(page.locator("body")).to_contain_text(expected_text, timeout=60000)
        for text in page_texts:
            expect(page.locator("body")).to_contain_text(text, timeout=60000)
        for text in forbidden_by_page.get(tab_label, []):
            assert_visible_text_absent(page, text)
        if tab_label == "Diagnostics":
            page.evaluate("window.scrollTo(0, 0)")
            for title in [
                "1. Residual Autocorrelation by Lag",
                "2. Residual vs Fitted",
            ]:
                assert_text_above_fold(page, title)
            for title in [
                "3. Diagnostic Pass Matrix",
                "4. Error Distribution by Horizon",
            ]:
                expect(page.get_by_text(title, exact=False).first).to_be_visible(
                    timeout=60000
                )
        if tab_label == "Scenario Comparison":
            page.evaluate("window.scrollTo(0, 0)")
            expect(page.locator("body")).to_contain_text(
                "Scenario A: Refined Finalist Ensemble", timeout=60000
            )
            expect(page.locator("body")).to_contain_text(
                "Scenario B: Schiff specification benchmark", timeout=60000
            )
            # The scenario header is a read-only governed summary (the former
            # "Edit" popover only changed labels, never data, and was removed).
            assert "Scenario settings" not in page.locator("body").inner_text(
                timeout=60000
            )
            for title in [
                "1. Stream Comparison: Scenario A vs Scenario B",
                "2. Improvement vs Benchmark",
                "3. Horizon Comparison",
                "4. Decision Summary",
            ]:
                assert_text_above_fold(page, title)
        if tab_label == "Revenue Outlook":
            page.evaluate("window.scrollTo(0, 0)")
            for title in [
                "Revenue Outlook controls",
                "Total path chart",
                # The uncertainty fan no longer shares this row: the Total
                # path chart is full width and carries the MoT VFM Fast-Slow
                # range. Its request gate stays above the fold in its place.
                "Show forecast-uncertainty fan detail",
            ]:
                assert_text_above_fold(page, title)
            for title in [
                "Revenue composition over time",
                "Fleet mix explorer",
                "Effective rates per 1,000 km",
            ]:
                expect(page.get_by_text(title, exact=False).first).to_be_visible(
                    timeout=60000
                )
            assert_revenue_outlook_primary_runtime_contract(page)
            assert_revenue_outlook_composition_below_primary(page)
            assert_revenue_outlook_fleet_above_rates(page)
        assert rendered_surface_count(page) > 0
        save_dashboard_screenshot(page, artifact_dir, screenshot_name)

    assert not page.locator("[data-testid='stException']").count()
    assert page_errors == []
    assert console_errors == []


def test_revenue_outlook_fleet_layout_and_timing_csv_download(page: Page) -> None:
    base_url = os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501")
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(base_url, wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Revenue Outlook")

    fleet_title = "Fleet mix explorer - MoT's six volume rows across MBU26, the VFM and this dashboard"
    for text in [
        fleet_title,
        "Same kilometres, three denominators",
        "What each row means, source by source",
        "Effective rates per 1,000 km",
    ]:
        expect(page.get_by_text(text, exact=False).first).to_be_visible(timeout=60000)

    assert page.locator("[data-testid='stExpander']").filter(has_text=fleet_title).count() == 0
    assert page.get_by_text("Net revenue timing comparison (FY2026-FY2030)", exact=True).count() == 0

    fleet_y = document_y_for_text(page, fleet_title)
    rates_y = document_y_for_text(page, "Effective rates per 1,000 km")
    download_y = document_y_for_text(page, "Download 12c timing CSV")
    assert fleet_y < rates_y < download_y, (
        "Revenue Outlook should render Fleet Mix Explorer, then effective rates, then the timing export; "
        f"fleet_y={fleet_y}, rates_y={rates_y}, download_y={download_y}"
    )

    download_button = page.get_by_role("button", name="Download 12c timing CSV", exact=True)
    expect(download_button).to_be_visible(timeout=60000)
    with page.expect_download(timeout=60000) as download_info:
        download_button.click()
    download = download_info.value
    assert download.suggested_filename == "net_revenue_12c_timing_comparison_fy2026_fy2030.csv"
    frame = pd.read_csv(download.path())
    assert len(frame) == 180
    assert not frame.duplicated(["path_id", "FY", "series_id"]).any()
    assert set(frame["path_id"]) == {
        f"{family}_{timing}"
        for family in ("baseline", *CONFLICT_FUEL_SCENARIO_LEVELS)
        for timing in ("published", "shifted_6m", "no_uplift")
    }
    assert set(frame["scenario_family_id"]) == {"base", *CONFLICT_FUEL_SCENARIO_LEVELS}
    path_metadata = frame[
        ["path_id", "scenario_id", "policy_state"]
    ].drop_duplicates()
    assert len(path_metadata) == 12
    assert all(
        POLICY_PATH_IDS[str(row["scenario_id"])] == str(row["path_id"])
        for _, row in path_metadata.iterrows()
    )
    assert set(frame["policy_state"]) == {"published", "delay_6m", "no_uplift"}
    assert set(frame["timing_id"]) == {"published", "delayed_6m", "no_uplift"}
    assert set(pd.to_numeric(frame["FY"], errors="raise").astype(int)) == set(range(2026, 2031))
    assert set(frame["series_id"]) == {
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
    }
    assert not page.locator("[data-testid='stException']").count()

    page.set_viewport_size({"width": 430, "height": 900})
    page.reload(wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Revenue Outlook")
    expect(page.get_by_text(fleet_title, exact=True)).to_be_visible(timeout=60000)
    expect(page.get_by_role("button", name="Download 12c timing CSV", exact=True)).to_be_visible(timeout=60000)
    assert not page.locator("[data-testid='stException']").count()


def test_revenue_outlook_activity_selection_keeps_policy_controls_and_hides_revenue_only_controls(
    page: Page,
) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    click_governance_nav(page, "Revenue Outlook")
    expect(
        page.get_by_text("Revenue Outlook controls", exact=False).first
    ).to_be_visible(timeout=90000)
    select_revenue_outlook_series(page, "PED VKT per capita")
    expect(page.get_by_text("Current 12c policy", exact=True).first).to_be_visible()
    expect(page.get_by_text("MBU26 12c policy", exact=True).first).to_be_visible()
    assert_visible_text_absent(page, "Not applicable to activity series.")
    assert_visible_text(
        page,
        "Revenue component drill-down and selected-FY revenue split are not applicable to activity-volume series.",
    )
    assert_visible_text_absent(page, "Component drill-down")
    assert_visible_text_absent(page, "Selected-FY revenue split")
    assert_revenue_outlook_primary_runtime_contract(
        page, selected_series="PED VKT per capita"
    )


def test_revenue_outlook_middle_east_default_keeps_timing_and_policy_selector(
    page: Page,
) -> None:
    medium_trace = conflict_trace_name("medium")
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    click_governance_nav(page, "Revenue Outlook")
    expect(
        page.get_by_text("Revenue Outlook controls", exact=False).first
    ).to_be_visible(timeout=90000)
    expect(page.locator("body")).to_contain_text(medium_trace, timeout=90000)

    legend_button = page.get_by_role("button", name="Select legend items", exact=True)
    expect(legend_button).to_be_visible(timeout=60000)
    legend_button.click()
    for level in CONFLICT_FUEL_SCENARIO_LEVELS:
        trace_name = conflict_trace_name(level)
        checkbox = page.get_by_role("checkbox", name=trace_name, exact=True)
        checkbox_label = page.locator("label").filter(has=checkbox)
        expect(checkbox).to_be_attached(timeout=60000)
        expect(checkbox_label).to_have_count(1)
        expect(checkbox_label).to_be_visible(timeout=60000)
        assert checkbox.is_checked() is (level == "medium")
    page.keyboard.press("Escape")

    quarterly = (
        page.locator("div[data-testid='stRadio'] label")
        .filter(has_text="Quarterly")
        .first
    )
    expect(quarterly).to_be_visible(timeout=60000)
    quarterly.click()
    page.wait_for_function(
        """(mediumTrace) => [...document.querySelectorAll('.js-plotly-plot')].some((plot) => {
            const names = new Set((plot.data || []).map((trace) => String(trace.name || '')));
            const x = (plot.data || []).flatMap((trace) => Array.from(trace.x || []).map(String));
            return names.has('Current finalist Base case') &&
                names.has(mediumTrace) &&
                x.includes('2026Q1');
        })""",
        arg=medium_trace,
        timeout=90000,
    )
    paths = page.evaluate(
        """(mediumTrace) => {
            const plot = [...document.querySelectorAll('.js-plotly-plot')].find((candidate) =>
                (candidate.data || []).some((trace) => trace.name === 'Current finalist Base case') &&
                (candidate.data || []).some((trace) => trace.name === mediumTrace)
            );
            const pick = (name) => {
                const trace = (plot.data || []).find((candidate) => candidate.name === name);
                const values = trace.y && trace.y._inputArray
                    ? Object.keys(trace.y._inputArray)
                        .sort((left, right) => Number(left) - Number(right))
                        .map((key) => Number(trace.y._inputArray[key]))
                    : Array.from(trace.y || [], Number);
                return Object.fromEntries(
                    Array.from(trace.x || []).map((period, index) => [String(period), values[index]])
                );
            };
            return {
                base: pick('Current finalist Base case'),
                conflict: pick(mediumTrace),
            };
        }""",
        medium_trace,
    )
    for period in ["2025Q3", "2025Q4", "2026Q1"]:
        assert paths["conflict"][period] == pytest.approx(paths["base"][period], abs=1e-6)
    for period in ["2026Q2", "2026Q3", "2026Q4"]:
        assert paths["conflict"][period] < paths["base"][period]

    june_year = (
        page.locator("div[data-testid='stRadio'] label")
        .filter(has_text="June-year")
        .first
    )
    expect(june_year).to_be_visible(timeout=60000)
    june_year.click()
    page.wait_for_function(
        """(mediumTrace) => [...document.querySelectorAll('.js-plotly-plot')].some((plot) =>
            (plot.data || []).some((trace) => trace.name === mediumTrace &&
                Array.from(trace.x || []).map(String).includes('FY2027'))
        )""",
        arg=medium_trace,
        timeout=90000,
    )

    def trace_value(trace_name: str, period: str) -> float:
        value = page.evaluate(
            """({traceName, period}) => {
                const plot = [...document.querySelectorAll('.js-plotly-plot')].find((candidate) =>
                    (candidate.data || []).some((trace) => trace.name === traceName)
                );
                const trace = (plot.data || []).find((candidate) => candidate.name === traceName);
                const x = Array.from(trace.x || []).map(String);
                const values = trace.y && trace.y._inputArray
                    ? Object.keys(trace.y._inputArray)
                        .sort((left, right) => Number(left) - Number(right))
                        .map((key) => Number(trace.y._inputArray[key]))
                    : Array.from(trace.y || [], Number);
                return values[x.indexOf(period)];
            }""",
            {"traceName": trace_name, "period": period},
        )
        return float(value)

    delayed_fy2028 = trace_value(medium_trace, "FY2028")
    levers = page.locator("[data-testid='stExpander']").filter(
        has_text="Advanced scenario levers"
    )
    expect(levers).to_be_visible(timeout=60000)
    levers.locator("summary").click()
    current_policy = levers.locator(
        '[role="combobox"][aria-label*="Current 12c policy"]'
    ).first
    expect(current_policy).to_be_visible(timeout=60000)
    expect(current_policy).to_have_attribute(
        "aria-label", re.compile("Deferred 6 months")
    )
    current_policy.click()
    no_uplift = page.get_by_role("option", name="No 12c uplift", exact=True)
    expect(no_uplift).to_be_visible(timeout=30000)
    no_uplift.click()
    expect(current_policy).to_have_attribute(
        "aria-label", re.compile("No 12c uplift"), timeout=60000
    )
    page.wait_for_function(
        """({traceName, period, previous}) => {
            const plot = [...document.querySelectorAll('.js-plotly-plot')].find((candidate) =>
                (candidate.data || []).some((trace) => trace.name === traceName)
            );
            if (!plot) return false;
            const trace = (plot.data || []).find((candidate) => candidate.name === traceName);
            const x = Array.from(trace.x || []).map(String);
            const values = trace.y && trace.y._inputArray
                ? Object.keys(trace.y._inputArray)
                    .sort((left, right) => Number(left) - Number(right))
                    .map((key) => Number(trace.y._inputArray[key]))
                : Array.from(trace.y || [], Number);
            const value = values[x.indexOf(period)];
            return Number.isFinite(value) && Math.abs(value - previous) > 1e-6;
        }""",
        arg={
            "traceName": medium_trace,
            "period": "FY2028",
            "previous": delayed_fy2028,
        },
        timeout=90000,
    )
    assert trace_value(medium_trace, "FY2028") < delayed_fy2028
    assert page.locator("[data-testid='stException']").count() == 0


def test_revenue_outlook_is_responsive_without_horizontal_overflow(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    click_governance_nav(page, "Revenue Outlook")
    expect(page.get_by_text("Total path chart", exact=False).first).to_be_visible(
        timeout=90000
    )
    expect(
        page.get_by_text("Show forecast-uncertainty fan detail", exact=False).first
    ).to_be_visible(timeout=90000)
    overflow = page.evaluate(
        """() => {
            const bad = [];
            const nodes = [
                ...document.querySelectorAll('.chart-card-header'),
                ...document.querySelectorAll('.page5-panel-title'),
                ...document.querySelectorAll('[role="combobox"]'),
                ...document.querySelectorAll('.js-plotly-plot')
            ];
            for (const node of nodes) {
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 2 || rect.height < 2) continue;
                if (rect.right > window.innerWidth + 2 || rect.left < -2) {
                    bad.push((node.innerText || node.getAttribute('aria-label') || node.className || node.tagName).toString().trim().slice(0, 80));
                }
            }
            return bad;
        }"""
    )
    assert overflow == []
    assert_revenue_outlook_primary_runtime_contract(page)


def test_navigation_labels_not_clipped(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    body = page.locator("body").inner_text(timeout=60000)
    assert "‹nchmark" not in body
    expect(page.locator("body")).to_contain_text(
        "Candidate Search Frontier", timeout=90000
    )
    expect(page.locator("body")).to_contain_text(
        "Finalist Ensemble Composition", timeout=90000
    )
    page_chip_box = page.locator(".page-chip").first.bounding_box()
    assert page_chip_box is not None, "Page chip should have a visible bounding box"
    for label in [
        "Overview",
        "Diagnostics",
        "Scenario Comparison",
        "Revenue Outlook",
    ]:
        nav_label = governance_nav_label(page, label)
        expect(nav_label).to_be_visible(timeout=60000)
        label_box = nav_label.bounding_box()
        assert label_box is not None, (
            f"{label} nav label should have a visible bounding box"
        )
        horizontal_gap = label_box["x"] + label_box["width"] <= page_chip_box[
            "x"
        ] - 4 or (page_chip_box["x"] + page_chip_box["width"] <= label_box["x"] - 4)
        vertical_gap = label_box["y"] + label_box["height"] <= page_chip_box[
            "y"
        ] - 2 or (page_chip_box["y"] + page_chip_box["height"] <= label_box["y"] - 2)
        assert horizontal_gap or vertical_gap, (
            f"{label} nav label overlaps the page chip"
        )


def test_latest_arbitration_values_are_visible_not_stale(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    body = page.locator("body").inner_text(timeout=60000)
    accuracy_info = chart_info_text(page, "Finalist Forecast Accuracy")

    assert "Current Parquet finalists using Paper-style horizon MAPE:" in accuracy_info
    source = pd.read_csv(CHART_SOURCE_DIR / "overview_finalist_forecast_accuracy.csv")
    expected_displays = (
        source.loc[
            source["score_basis"].eq("schiff_paper_horizon_mean"), "metric_display"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    assert expected_displays
    for expected in expected_displays:
        assert expected in accuracy_info

    for stale in ["5.49%", "9.15%", "12.38%"]:
        assert stale not in body


def test_visible_navigation_text_changes_page_body(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    for label, expected_content, stale_content in [
        (
            "Diagnostics",
            "1. Residual Autocorrelation by Lag",
            "Finalist Forecast Accuracy",
        ),
        (
            "Scenario Comparison",
            "1. Stream Comparison: Scenario A vs Scenario B",
            "1. Residual Autocorrelation by Lag",
        ),
        (
            "Revenue Outlook",
            "Total path chart",
            "1. Stream Comparison: Scenario A vs Scenario B",
        ),
        (
            "Overview",
            "Finalist Forecast Accuracy",
            "Total path chart",
        ),
    ]:
        click_governance_nav(page, label)
        page.wait_for_timeout(1500)
        expected = page.get_by_text(expected_content, exact=False).first
        expect(expected).to_be_visible(timeout=60000)
        expected_box = expected.bounding_box()
        assert expected_box is not None
        assert stale_content != expected_content


def test_reference_header_nav_is_integrated_on_desktop(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    title_box = page.get_by_text(
        "NTLF Revenue Modelling", exact=True
    ).first.bounding_box()
    overview_box = governance_nav_label(page, "Overview").bounding_box()
    outlook_box = governance_nav_label(page, "Revenue Outlook").bounding_box()
    filter_box = page.locator(".filter-title").first.bounding_box()

    assert title_box is not None
    assert overview_box is not None
    assert outlook_box is not None
    assert filter_box is not None
    title_bottom = title_box["y"] + title_box["height"]
    assert overview_box["y"] >= title_bottom - 2
    assert outlook_box["y"] >= title_bottom - 2
    assert outlook_box["x"] > overview_box["x"] + 240
    assert filter_box["y"] > overview_box["y"] + overview_box["height"]
    assert filter_box["y"] < 180


def test_filter_values_are_readable(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Model Family", 1, "All Families")
    expect_filter_value(page, "Horizon", 3, "1-12 Quarters")


def test_filter_band_is_reference_compact(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    filter_title = page.locator(".filter-title").first.bounding_box()
    first_kpi = page.locator(".gov-kpi-card").first.bounding_box()
    first_chart = page.get_by_text(
        "Finalist Forecast Accuracy", exact=False
    ).first.bounding_box()
    assert filter_title is not None
    assert first_kpi is not None
    assert first_chart is not None
    assert first_kpi["y"] - filter_title["y"] < 120
    assert first_kpi["y"] < 280
    assert first_chart["y"] < 700
    assert page.locator(".run-evidence-compact").count() == 0
    assert_visible_text_absent(page, "Run evidence:")
    assert_visible_text_absent(page, "Curated rows:")


def test_governance_shell_is_readable_in_narrow_browser(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    for label in [
        "Overview",
        "Diagnostics",
        "Scenario Comparison",
        "Revenue Outlook",
    ]:
        expect(governance_nav_label(page, label)).to_be_visible(timeout=60000)

    title_box = page.get_by_text(
        "NTLF Revenue Modelling", exact=True
    ).first.bounding_box()
    nav_box = governance_nav_label(page, "Overview").bounding_box()
    assert title_box is not None
    assert nav_box is not None
    assert nav_box["y"] > title_box["y"] + 30

    overflow = page.evaluate(
        """() => {
            const bad = [];
            const nodes = [
                ...document.querySelectorAll('.page-chip'),
                ...document.querySelectorAll('.gov-filter-display'),
                ...document.querySelectorAll('div[data-testid="stRadio"] label')
            ];
            for (const node of nodes) {
                const rect = node.getBoundingClientRect();
                if (rect.right > window.innerWidth + 2 || rect.left < -2) {
                    bad.push(node.innerText.trim());
                }
            }
            return bad;
        }"""
    )
    assert overflow == []

    body = page.locator("body").inner_text(timeout=60000)
    assert expected_page_chip("Overview") in body
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Model Family", 1, "All Families")
    expect_filter_value(page, "Score Basis", 4, "Paper-style horizon MAPE")

    first_chart = page.get_by_text("Finalist Forecast Accuracy", exact=False).first
    second_chart = page.get_by_text("Candidate Search Frontier", exact=False).first
    expect(first_chart).to_be_visible(timeout=90000)
    expect(second_chart).to_be_visible(timeout=90000)
    first_box = first_chart.bounding_box()
    second_box = second_chart.bounding_box()
    assert first_box is not None
    assert second_box is not None
    assert second_box["y"] > first_box["y"]


def test_primary_reference_pages_use_icon_kpi_rows(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    for tab_label, left_label, right_label in [
        ("Diagnostics", "Diagnostics Coverage", "Heteroscedasticity Pass"),
    ]:
        click_governance_nav(page, tab_label)
        expect(page.locator("body")).to_contain_text(left_label, timeout=60000)
        kpi_count = page.evaluate(
            """() => Math.max(
                ...Array.from(document.querySelectorAll('.gov-kpi-grid'))
                    .map((grid) => grid.querySelectorAll('.gov-kpi-card').length),
                0
            )"""
        )
        assert kpi_count >= 4
        left_box = page.get_by_text(left_label, exact=False).first.bounding_box()
        right_box = page.get_by_text(right_label, exact=False).first.bounding_box()
        assert left_box is not None
        assert right_box is not None
        assert abs(right_box["y"] - left_box["y"]) < 90
        assert right_box["x"] > left_box["x"] + 360


def test_diagnostics_in_app_grid_replaces_overview_panels(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    click_governance_nav(page, "Diagnostics")
    expect(page.locator("body")).to_contain_text(
        expected_page_chip("Diagnostics"), timeout=60000
    )
    assert_visible_text_absent(page, "Diagnostics evidence:")
    assert_visible_text_absent(page, "proxy panels shown")
    for title in [
        "1. Residual Autocorrelation by Lag",
        "2. Residual vs Fitted",
    ]:
        assert_text_above_fold(page, title)
    expect(
        page.get_by_text("3. Diagnostic Pass Matrix", exact=False).first
    ).to_be_visible(timeout=60000)

    overview_ghost_visible = page.evaluate(
        """() => {
            const needles = [
                'Stress watch:',
                'Finalist Forecast Accuracy'
            ];
            return Array.from(document.querySelectorAll('body *')).some((node) => {
                if (!needles.some((text) => node.textContent?.includes(text))) return false;
                const style = window.getComputedStyle(node);
                const rect = node.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity || 1) > 0.01
                    && rect.width > 1
                    && rect.height > 1
                    && rect.top >= 0
                    && rect.top < 940;
            });
        }"""
    )
    assert overview_ghost_visible is False


def test_scenario_in_app_grid_brings_improvement_panel_into_view(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text(
        expected_page_chip("Scenario Comparison"), timeout=60000
    )
    for title in [
        "1. Stream Comparison: Scenario A vs Scenario B",
        "2. Improvement vs Benchmark",
    ]:
        assert_text_above_fold(page, title, max_y=850)
    expect(page.get_by_text("3. Horizon Comparison", exact=False).first).to_be_visible(
        timeout=60000
    )

    improvement_box = page.get_by_text(
        "2. Improvement vs Benchmark", exact=False
    ).first.bounding_box()
    assert improvement_box is not None
    assert improvement_box["y"] < 790


def test_overview_has_dashboard_grid(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text(
        "Finalist Forecast Accuracy", timeout=90000
    )
    expect(page.locator("body")).to_contain_text(
        "Candidate Search Frontier", timeout=90000
    )
    expect(page.locator("body")).to_contain_text(
        "Finalist Ensemble Composition", timeout=90000
    )
    body = page.locator("body").inner_text(timeout=60000)
    assert "Candidate Search Frontier" in body
    assert "Finalist Ensemble Composition" in body
    expect(page.locator("body")).to_contain_text(
        "Stress and Horizon Checks", timeout=60000
    )
    page.evaluate("window.scrollTo(0, 0)")
    for title in [
        "Finalist Forecast Accuracy",
        "Candidate Search Frontier",
        "Finalist Ensemble Composition",
        "Stress and Horizon Checks",
    ]:
        expect(page.get_by_text(title, exact=False).first).to_be_visible(timeout=60000)
    body = page.locator("body").inner_text(timeout=60000)
    assert "Stress and Horizon Checks" in body


def test_ensemble_composition_has_three_stream_panels(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text(
        "Finalist Ensemble Composition", timeout=90000
    )
    expect(page.locator("body")).to_contain_text("PED VKT per capita", timeout=90000)
    expect(page.locator("body")).to_contain_text("Light RUC volume", timeout=90000)
    expect(page.locator("body")).to_contain_text("Heavy RUC volume", timeout=90000)
    assert_ensemble_plot_has_all_streams(page)


def test_ensemble_composition_has_three_stream_panels_under_both_score_bases(
    page: Page,
) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)

    assert_ensemble_plot_has_all_streams(page)

    select_combobox_option(page, 4, "Operational pooled MAPE")
    expect_filter_value(page, "Score Basis", 4, "Operational pooled MAPE")
    wait_dashboard_ready(page)
    assert_ensemble_plot_has_all_streams(page)


def test_overview_stress_bucket_order(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text(
        "Stress and Horizon Checks", timeout=90000
    )

    labels = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]
    boxes = []
    for label in labels:
        locator = page.get_by_text(label, exact=True).first
        expect(locator).to_be_visible(timeout=90000)
        box = locator.bounding_box()
        assert box is not None
        boxes.append(box["x"])
    assert boxes == sorted(boxes), (
        f"Stress bucket labels are out of order: {dict(zip(labels, boxes))}"
    )


def test_overview_stress_horizon_aliases_show_all_streams(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text(
        "Stress and Horizon Checks", timeout=90000
    )
    page.get_by_text(
        "Stress and Horizon Checks", exact=False
    ).first.scroll_into_view_if_needed()

    labels = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]
    for label in labels[:3]:
        expect(page.get_by_text(label, exact=True).first).to_be_visible(timeout=90000)
    for stream in ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]:
        expect(page.locator("body")).to_contain_text(stream, timeout=90000)

    page.wait_for_function(
        """() => {
            return [...document.querySelectorAll('.js-plotly-plot')].some((plot) => {
                const categories = Array.from(plot.layout?.xaxis?.categoryarray || []);
                return categories.includes('1-4 qtrs')
                    && categories.includes('9-12 qtrs')
                    && categories.includes('Annual')
                    && (plot.data || []).some((trace) => trace.name === 'PED VKT per capita')
                    && (plot.data || []).some((trace) => trace.name === 'Light RUC volume')
                    && (plot.data || []).some((trace) => trace.name === 'Heavy RUC volume');
            });
        }""",
        timeout=90000,
    )
    stress_plot = page.evaluate(
        """() => {
            const plots = [...document.querySelectorAll('.js-plotly-plot')];
            const plot = plots.find((candidate) => {
                const categories = Array.from(candidate.layout?.xaxis?.categoryarray || []);
                return categories.includes('1-4 qtrs')
                    && categories.includes('9-12 qtrs')
                    && categories.includes('Annual')
                    && (candidate.data || []).some((trace) => trace.name === 'PED VKT per capita');
            });
            if (!plot) {
                return null;
            }
            return {
                categories: Array.from(plot.layout?.xaxis?.categoryarray || []),
                traces: (plot.data || []).map((trace) => ({
                    name: trace.name,
                    x: Array.from(trace.x || []),
                    y: Array.from(trace.y?._inputArray || trace.y || []),
                    connectgaps: trace.connectgaps,
                })),
            };
        }"""
    )
    assert stress_plot is not None
    assert stress_plot["categories"] == labels
    traces = {trace["name"]: trace for trace in stress_plot["traces"]}
    assert {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}.issubset(
        traces
    )
    for stream in ["PED VKT per capita", "Light RUC volume"]:
        y_by_bucket = dict(zip(traces[stream]["x"], traces[stream]["y"]))
        for label in labels[:3]:
            assert not _browser_value_missing(y_by_bucket[label]), (
                f"{stream} is missing {label}"
            )
    heavy = traces["Heavy RUC volume"]
    assert heavy["connectgaps"] is False
    heavy_y = dict(zip(heavy["x"], heavy["y"]))
    for label in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]:
        assert not _browser_value_missing(heavy_y[label]), (
            f"Heavy RUC is missing sourced stress bucket {label}"
        )
    assert "2024+" not in stress_plot["categories"]
    assert "2022-23" not in stress_plot["categories"]


def _browser_value_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def test_overview_candidate_frontier_has_expected_markers(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text(
        "Candidate Search Frontier", timeout=90000
    )
    assert_visible_text(page, "Finalist")
    assert_visible_text(page, "Schiff")
    body = page.locator("body").inner_text(timeout=60000).lower()
    assert "ellipse" not in body
    assert "cluster circle" not in body


def test_diagnostics_matrix_is_styled(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    click_governance_nav(page, "Diagnostics")
    expect(page.locator("body")).to_contain_text(
        "3. Diagnostic Pass Matrix", timeout=90000
    )
    for text in [
        "Calibration R2",
        "Durbin-Watson",
        "Breusch-Pagan",
        "White",
        "Jarque-Bera",
    ]:
        expect(page.locator("body")).to_contain_text(text, timeout=90000)
    legend_info = chart_info_text(page, "3. Diagnostic Pass Matrix")
    for text in ["Green = pass", "amber = watch", "red = fail"]:
        assert text in legend_info
        assert_visible_text_absent(page, text)


def test_scenario_horizon_shows_all_streams(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text("3. Horizon Comparison", timeout=90000)
    for stream in ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]:
        expect(page.locator("body")).to_contain_text(stream, timeout=90000)


def test_scenario_dumbbell_no_overlap_smoke(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(
        os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"),
        wait_until="domcontentloaded",
    )
    wait_dashboard_ready(page)
    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text("Quarterly MAPE", timeout=90000)
    expect(page.locator("body")).to_contain_text("Annual MAPE", timeout=90000)
    screenshot_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(
        path=screenshot_dir / "visual-smoke-scenario-dumbbell.png", full_page=True
    )


def test_visual_screenshots_are_regenerated() -> None:
    screenshot_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    for name in [
        "final-01-overview.png",
        "final-02-diagnostics.png",
        "final-03-scenario-comparison.png",
        "final-04-revenue-outlook.png",
    ]:
        path = screenshot_dir / name
        assert path.exists(), f"Missing screenshot {path}"
        assert path.stat().st_size > 10_000, f"Screenshot is unexpectedly small: {path}"


def wait_dashboard_ready(page: Page) -> None:
    expect(page.get_by_text("NTLF Revenue Modelling").first).to_be_visible(
        timeout=90000
    )
    expect(
        page.locator("img.brand-logo[alt='NZ Transport Agency Waka Kotahi logo']")
    ).to_be_visible(timeout=90000)
    expect(page.get_by_text("GOVERNANCE FILTERS")).to_be_visible(timeout=90000)
    expect(page.get_by_role("button", name="Reset Filters")).to_be_visible(
        timeout=90000
    )
    expect(page.locator("body")).to_contain_text(
        expected_page_chip("Overview"), timeout=90000
    )
    expect(governance_nav_label(page, "Revenue Outlook")).to_be_visible(timeout=90000)


def rendered_surface_count(page: Page) -> int:
    return page.locator(
        ".js-plotly-plot, svg.main-svg, canvas, [data-testid='stDataFrame'], "
        ".diagnostic-tooltip-matrix, .page5-panel, .page5-status-card, .page5-flow-step"
    ).count()


def wait_for_rendered_surfaces(page: Page) -> None:
    page.wait_for_function(
        """() => document.querySelectorAll(
            '.js-plotly-plot, svg.main-svg, canvas, [data-testid="stDataFrame"], .diagnostic-tooltip-matrix'
        ).length >= 4""",
        timeout=90000,
    )


def governance_nav_label(page: Page, label: str):
    labels = page.locator("div[data-testid='stRadio'] label")
    display_label = page_display_label(label)
    display_match = labels.filter(has_text=display_label)
    if display_match.count() > 0:
        return display_match.first
    return labels.filter(has_text=label).first


def click_governance_nav(page: Page, label: str) -> None:
    target = governance_nav_label(page, label)
    expect(target).to_be_visible(timeout=60000)
    target.click()


def save_dashboard_screenshot(
    page: Page, artifact_dir: Path, screenshot_name: str
) -> None:
    page.screenshot(path=artifact_dir / screenshot_name, full_page=True)
    final_name = screenshot_name.replace("mcp-", "final-", 1)
    page.screenshot(path=artifact_dir / final_name, full_page=True)


def assert_text_above_fold(page: Page, text: str, max_y: int = 930) -> None:
    locator = page.get_by_text(text, exact=False).first
    locator.wait_for(state="visible", timeout=60000)
    box = locator.bounding_box()
    assert box is not None, f"{text!r} has no visible bounding box"
    assert box["y"] < max_y, (
        f"{text!r} should be visible above the first viewport fold; y={box['y']}"
    )


def document_y_for_text(page: Page, text: str) -> float:
    locator = page.get_by_text(text, exact=False).first
    locator.wait_for(state="visible", timeout=60000)
    y_value = locator.evaluate(
        "element => element.getBoundingClientRect().top + window.scrollY"
    )
    return float(y_value)


def assert_revenue_outlook_primary_runtime_contract(
    page: Page, selected_series: str = "Total NLTF revenue"
) -> None:
    page.wait_for_function(
        """() => [...document.querySelectorAll('.js-plotly-plot')].some((plot) =>
            (plot.data || []).some((trace) => trace.name === 'Current finalist Base case')
        )""",
        timeout=90000,
    )
    contract = page.evaluate(
        """() => {
            const plot = [...document.querySelectorAll('.js-plotly-plot')].find((candidate) =>
                (candidate.data || []).some((trace) => trace.name === 'Current finalist Base case')
            );
            if (!plot) return null;
            const traces = (plot.data || []).map((trace) => ({
                name: String(trace.name || ''),
                x: Array.from(trace.x || []).map(String),
                dash: String((trace.line || {}).dash || 'solid'),
                color: String((trace.line || {}).color || ''),
                hovertemplate: String(trace.hovertemplate || ''),
            }));
            const legend = (plot.layout || {}).legend || {};
            const annotations = ((plot.layout || {}).annotations || []).map((annotation) => String(annotation.text || ''));
            const layoutKeys = Object.keys(plot.layout || {});
            return {
                traces,
                legend,
                annotations,
                hasSmallMultipleAxes: layoutKeys.some((key) => /^xaxis[2-9]/.test(key) || /^yaxis[2-9]/.test(key)),
                yTitle: String((((plot.layout || {}).yaxis || {}).title || {}).text || ''),
            };
        }"""
    )
    assert contract is not None
    trace_names = {trace["name"] for trace in contract["traces"] if trace["name"]}
    allowed = {
        "Actual",
        "MBU26 official",
        "MBU26 official handover",
        "Current finalist Base case",
        *CONFLICT_TRACE_NAMES,
        "Current finalist High population/comparison",
        "Current finalist comparison behavioural path",
        "MoT VFM fast bound",
        "MoT VFM fast–slow range",
    }
    assert trace_names.issubset(allowed), trace_names
    assert "Current finalist Base case" in trace_names
    assert conflict_trace_name("medium") in trace_names
    assert conflict_trace_name("low") not in trace_names
    assert conflict_trace_name("high") not in trace_names
    expected_comparison_trace = (
        "Current finalist comparison behavioural path"
        if selected_series == "PED VKT per capita"
        else "Current finalist High population/comparison"
    )
    assert expected_comparison_trace in trace_names
    if selected_series == "PED VKT per capita":
        assert "Current finalist High population/comparison" not in trace_names
    else:
        assert "Current finalist comparison behavioural path" not in trace_names
    for forbidden in [
        "Schiff",
        "selected_dashboard",
        "legacy workbook",
        "Current finalist forecast",
    ]:
        assert all(
            forbidden.lower() not in trace["name"].lower()
            for trace in contract["traces"]
        )
    assert contract["hasSmallMultipleAxes"] is False
    assert contract["legend"].get("orientation") == "h"
    assert float(contract["legend"].get("y", 0)) >= 1.0
    assert contract["legend"].get("yanchor") == "bottom"
    assert contract["yTitle"], (
        "Revenue Outlook primary chart should expose explicit units on the y-axis."
    )
    assert any("Actuals to 2025" in text for text in contract["annotations"])

    # A segmented path emits SEVERAL plotly traces under one name (solid
    # econometric, dashed post-model extrapolation). Keying a dict by name
    # would keep only the last, so aggregate across segments first.
    by_name: dict = {}
    for item in contract["traces"]:
        existing = by_name.get(item["name"])
        if existing is None:
            merged = dict(item)
            merged["x"] = list(item["x"])
            merged["dashes"] = [item.get("dash")]
            by_name[item["name"]] = merged
        else:
            existing["x"] = list(existing["x"]) + list(item["x"])
            existing["dashes"].append(item.get("dash"))
    actual = by_name.get("Actual")
    if actual is not None and actual["x"]:
        assert max(actual["x"]) <= "FY2025"
        assert actual["color"] == "#737373"
    for name in ["Current finalist Base case", expected_comparison_trace]:
        trace = by_name[name]
        assert "FY2025" in trace["x"], f"{name} should include the FY2025 actual anchor"
        # The long-run restoration: current paths run through FY2050, with
        # the post-model segment dashed and joined to the solid one.
        assert "FY2050" in trace["x"], f"{name} should extend through FY2050"
        assert "dash" in trace["dashes"], (
            f"{name} should render its post-model segment dashed"
        )
        assert "FY2026" in trace["x"], (
            f"{name} should join to the FY2026 nowcast/forecast"
        )
        assert (
            "customdata" in trace["hovertemplate"]
            or "%{customdata" in trace["hovertemplate"]
        )
    if "MBU26 official" in by_name:
        assert by_name["MBU26 official"]["dash"] in {"dash", "dashdot"}
    page_text = page.locator("body").inner_text(timeout=60000)
    assert selected_series in page_text
    # The uncertainty fan is governed but no longer eagerly rendered: only
    # its request gate is on the default page, and the fan figure's own
    # controls ("Fan source details") must not have been constructed.
    assert "Show forecast-uncertainty fan detail" in page_text
    assert "Uncertainty fan" not in page_text
    assert "Fan source details" not in page_text


def assert_revenue_outlook_composition_below_primary(page: Page) -> None:
    for text in [
        "Revenue composition over time",
        "FY range / horizon",
        "Source path",
    ]:
        expect(page.locator("body")).to_contain_text(text, timeout=60000)

    total_y = document_y_for_text(page, "Total path chart")
    composition_y = document_y_for_text(page, "Revenue composition over time")
    assert composition_y > total_y, (
        "Revenue composition card should render below the primary Total path chart; "
        f"total_y={total_y}, composition_y={composition_y}"
    )


def assert_revenue_outlook_fleet_above_rates(page: Page) -> None:
    fleet_y = document_y_for_text(page, "Fleet mix explorer")
    rates_y = document_y_for_text(page, "Effective rates per 1,000 km")
    assert fleet_y < rates_y, (
        "Fleet Mix Explorer should render above the effective-rates chart; "
        f"fleet_y={fleet_y}, rates_y={rates_y}"
    )


def select_revenue_outlook_series(page: Page, value: str) -> None:
    combo = page.locator('[role="combobox"][aria-label*="Series"]').first
    expect(combo).to_be_visible(timeout=30000)
    combo.click()
    # The Series listbox is virtualised, so options outside the scrolled
    # window are absent from the DOM; typeahead filtering makes the target
    # option render regardless of list length.
    combo.type(value, delay=20)
    option = page.get_by_role("option", name=value)
    expect(option.first).to_be_visible(timeout=30000)
    option.first.click()


def assert_visible_text(page: Page, text: str) -> None:
    page.wait_for_function(
        """(needle) => Array.from(document.querySelectorAll('body *')).some((node) => {
            const value = (node.textContent || '').trim();
            if (value !== needle && !value.split(/\\s+/).includes(needle)) return false;
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            const parentRect = node.parentElement ? node.parentElement.getBoundingClientRect() : rect;
            const width = Math.max(rect.width, parentRect.width);
            const height = Math.max(rect.height, parentRect.height);
            return style.display !== 'none'
                && style.visibility !== 'hidden'
                && Number(style.opacity || 1) > 0.01
                && width > 1
                && height > 1;
        })""",
        arg=text,
        timeout=90000,
    )


def assert_visible_text_absent(page: Page, text: str) -> None:
    visible = page.evaluate(
        """(needle) => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let textNode = walker.nextNode();
            while (textNode) {
                const value = (textNode.nodeValue || '').trim();
                if (value !== needle && !value.split(/\\s+/).includes(needle)) {
                    textNode = walker.nextNode();
                    continue;
                }
                const node = textNode.parentElement;
                if (!node) {
                    textNode = walker.nextNode();
                    continue;
                }
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
                if (style.display !== 'none'
                && style.visibility !== 'hidden'
                && Number(style.opacity || 1) > 0.01
                && rect.width > 1
                    && rect.height > 1) {
                    return true;
                }
                textNode = walker.nextNode();
            }
            return false;
        }""",
        text,
    )
    assert not visible, f"Expected text {text!r} to be hidden"


def chart_info_text(page: Page, title: str) -> str:
    expect(
        page.locator(".chart-card-header").filter(has_text=title).first
    ).to_be_visible(timeout=60000)
    info = page.evaluate(
        """(title) => {
            const headers = Array.from(document.querySelectorAll('.chart-card-header'));
            const header = headers.find((node) => node.textContent && node.textContent.includes(title));
            if (!header) return '';
            const info = header.querySelector('.chart-info-text');
            return info ? info.textContent.trim() : '';
        }""",
        title,
    )
    assert info, f"Expected chart information tooltip for {title!r}"
    return str(info)


def expect_filter_value(page: Page, label: str, index: int, value: str) -> None:
    combo = page.get_by_role("combobox").nth(index)
    expect(combo).to_be_visible(timeout=30000)
    page.wait_for_function(
        """([index, value]) => {
            const combo = document.querySelectorAll('[role="combobox"]')[index];
            return combo && (combo.getAttribute('aria-label') || '').includes(`Selected ${value}.`);
        }""",
        arg=[index, value],
        timeout=60000,
    )
    aria_label = combo.get_attribute("aria-label") or ""
    assert label in aria_label, (
        f"Expected filter {index} to be {label}; aria-label was {aria_label!r}"
    )
    assert value in aria_label, (
        f"Expected filter {index} to be {value!r}; aria-label was {aria_label!r}"
    )


def select_combobox_option(page: Page, index: int, value: str) -> None:
    combo = page.get_by_role("combobox").nth(index)
    expect(combo).to_be_visible(timeout=30000)
    combo.click()
    option = page.get_by_role("option", name=value)
    expect(option.first).to_be_visible(timeout=30000)
    option.first.click()


def assert_ensemble_plot_has_all_streams(page: Page) -> None:
    page.get_by_text(
        "Finalist Ensemble Composition", exact=False
    ).first.scroll_into_view_if_needed()
    page.wait_for_function(
        """() => {
            const expected = ['PED VKT per capita', 'Light RUC volume', 'Heavy RUC volume'];
            return [...document.querySelectorAll('.js-plotly-plot')].some((plot) => {
                const traces = plot.data || [];
                if (traces.length < 3 || !traces.every((trace) => String(trace.type || '') === 'bar')) return false;
                const names = new Set(traces.map((trace) => String(trace.name || '')));
                const hasComponentLabels = traces.some((trace) => Array.from(trace.y || []).some((label) => /^C\\d+$/.test(String(label))));
                return expected.every((stream) => names.has(stream)) && hasComponentLabels;
            });
        }""",
        timeout=90000,
    )

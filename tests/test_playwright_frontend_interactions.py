from __future__ import annotations

import os
from pathlib import Path
import math
import re

import pandas as pd
import pytest
from playwright.sync_api import Page, expect


SCREENSHOT_DIR = Path("artifacts/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
CHART_SOURCE_DIR = Path("artifacts/chart_sources")

APP_URL = os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501")
TARGET_VIEWPORT = {"width": 2048, "height": 1005}
pytestmark = pytest.mark.skipif(
    os.environ.get("STAGE1_REQUIRE_FRONTEND_INTERACTIONS") != "1",
    reason="frontend interaction hard gate is run by verify_dashboard.ps1 after Streamlit starts",
)

PAGES = [
    ("Overview", "final-overview.png"),
    ("Diagnostics", "final-diagnostics.png"),
    ("Scenario Comparison", "final-scenario-comparison.png"),
    ("Schiff Benchmark", "final-schiff-benchmark.png"),
    ("Governance & Reproducibility", "final-governance-reproducibility.png"),
]

PAGE_PANELS = {
    "Overview": [
        "1. Finalist Forecast Accuracy",
        "2. Candidate Search Frontier",
        "3. Finalist Ensemble Composition",
        "4. Stress and Horizon Checks",
    ],
    "Diagnostics": [
        "Forecast R2 versus calibration R2",
        "1. Residual Autocorrelation by Lag",
        "2. Residual vs Fitted",
        "3. Diagnostic Pass Matrix",
        "4. Error Distribution by Horizon",
    ],
    "Scenario Comparison": [
        "1. Stream Comparison: Scenario A vs Scenario B",
        "2. Improvement vs Benchmark",
        "3. Horizon Comparison",
        "4. Decision Summary",
    ],
    "Schiff Benchmark": [
        "1. Schiff vs Finalist MAPE",
        "2. Benchmark Horizon Profiles",
        "3. Full-sample Gain vs Schiff specification benchmark",
        "4. Benchmark Summary",
    ],
    "Governance & Reproducibility": [
        "Governance & Reproducibility Filters",
        "Repro packs loaded",
        "How the model is built",
        "Model glossary",
        "Registry",
        "Component trace",
        "Net forecast R2 after final model composition",
        "SHAP not yet generated",
    ],
}

FILTER_LABELS = [
    "Stream",
    "Model Family",
    "Stage",
    "Baseline",
    "Horizon",
    "Forecast Vintage",
    "Date Window",
]

RAW_HOVER_TERMS = [
    "quarterly_mape",
    "annual_mape",
    "source_family",
    "model_kind",
    "mape_h01_04",
    "candidate_role",
    "stream_label",
]


def require_frontend_hard_gate() -> None:
    if os.environ.get("STAGE1_REQUIRE_FRONTEND_INTERACTIONS") != "1":
        pytest.skip("frontend interaction hard gate is run by verify_dashboard.ps1 after Streamlit starts")


@pytest.fixture(autouse=True)
def require_frontend_interaction_gate() -> None:
    require_frontend_hard_gate()


def assert_no_streamlit_exception(page: Page) -> None:
    body = page.locator("body").inner_text(timeout=60000)
    assert "Traceback" not in body
    assert "StreamlitAPIException" not in body
    assert "Uncaught app exception" not in body
    assert "stException" not in body


def chart_info_text(page: Page, title: str) -> str:
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


def visible_text_absent(page: Page, text: str) -> bool:
    return not page.evaluate(
        """(needle) => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let textNode = walker.nextNode();
            while (textNode) {
                const value = (textNode.nodeValue || '').trim();
                if (value !== needle && !value.includes(needle)) {
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


def open_dashboard(page: Page) -> None:
    require_frontend_hard_gate()
    page.set_viewport_size(TARGET_VIEWPORT)
    page.goto(APP_URL, wait_until="domcontentloaded")
    expect(page.get_by_text("NTLF Revenue Modelling").first).to_be_visible(timeout=90000)
    expect(page.get_by_text("GOVERNANCE FILTERS")).to_be_visible(timeout=90000)
    expect(page.locator(".js-plotly-plot").first).to_be_visible(timeout=90000)
    assert_no_streamlit_exception(page)


def click_page(page: Page, page_name: str) -> None:
    page.locator("div[data-testid='stRadio'] label").filter(has_text=page_name).first.click()
    expect(page.locator("body")).to_contain_text(page_name, timeout=90000)
    for panel in PAGE_PANELS[page_name]:
        expect(page.locator("body")).to_contain_text(panel, timeout=90000)
    assert_no_streamlit_exception(page)


def primary_combobox(page: Page, index: int):
    combo = page.get_by_role("combobox").nth(index)
    expect(combo).to_be_visible(timeout=30000)
    return combo


def expect_combobox_value(page: Page, index: int, value: str) -> None:
    page.wait_for_function(
        """([index, value]) => {
            const combo = document.querySelectorAll('[role="combobox"]')[index];
            return combo && (combo.getAttribute('aria-label') || '').includes(`Selected ${value}.`);
        }""",
        arg=[index, value],
        timeout=60000,
    )
    aria_label = primary_combobox(page, index).get_attribute("aria-label") or ""
    assert value in aria_label, f"Expected combobox {index} to be {value!r}; aria-label was {aria_label!r}"


def open_combobox(page: Page, index: int) -> None:
    primary_combobox(page, index).click()
    expect(page.get_by_role("option").first).to_be_visible(timeout=10000)


def select_first_non_default_option(page: Page, index: int, blocked: tuple[str, ...]) -> str:
    open_combobox(page, index)
    options = page.get_by_role("option")
    for option_index in range(options.count()):
        option = options.nth(option_index)
        text = option.inner_text(timeout=5000).strip()
        if text and not any(token.lower() in text.lower() for token in blocked):
            option.click()
            expect_combobox_value(page, index, text)
            return text
    raise AssertionError(f"No non-default option found for combobox {index}")


def hover_text(page: Page) -> str:
    page.wait_for_timeout(450)
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.hoverlayer'))
            .map((node) => node.textContent || '')
            .join('\\n')
            .trim()"""
    )


def hover_plotly_chart(page: Page, plot_index: int) -> str:
    plot = page.locator(".js-plotly-plot").nth(plot_index)
    expect(plot).to_be_visible(timeout=60000)
    for selector in [".scatterlayer .trace .points path", ".barlayer .point", ".barlayer path"]:
        points = plot.locator(selector)
        for point_index in range(min(points.count(), 12)):
            point = points.nth(point_index)
            box = point.bounding_box()
            if not box:
                continue
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            text = hover_text(page)
            if text:
                return text
    box = plot.bounding_box()
    assert box is not None, "Plotly plot has no bounding box."
    for x_frac, y_frac in [(0.35, 0.45), (0.50, 0.50), (0.65, 0.55), (0.72, 0.40)]:
        page.mouse.move(box["x"] + box["width"] * x_frac, box["y"] + box["height"] * y_frac)
        text = hover_text(page)
        if text:
            return text
    text = page.evaluate(
        """(plotIndex) => {
            const plot = document.querySelectorAll('.js-plotly-plot')[plotIndex];
            if (!plot || !window.Plotly || !window.Plotly.Fx) return '';
            const traces = plot.data || plot._fullData || [];
            for (let curveNumber = 0; curveNumber < traces.length; curveNumber += 1) {
                const trace = traces[curveNumber];
                const length = (trace.x || trace.y || trace.customdata || []).length || 0;
                if (!length) continue;
                window.Plotly.Fx.hover(plot, [{curveNumber, pointNumber: 0}], ['xy']);
                const text = Array.from(document.querySelectorAll('.hoverlayer'))
                    .map((node) => node.textContent || '')
                    .join('\\n')
                    .trim();
                if (text) return text;
            }
            return '';
        }""",
        plot_index,
    )
    assert text, f"No hover text appeared for Plotly chart {plot_index}"
    return text


def assert_human_hover(text: str) -> None:
    assert text.strip(), "Hover text is empty."
    assert "_" not in text, f"Hover text contains underscores: {text}"
    for raw in RAW_HOVER_TERMS:
        assert raw not in text, f"Hover text contains raw column name {raw}: {text}"
    assert not re.search(r"\d+\.\d{4,}", text), f"Hover has excessive decimals: {text}"


def browser_value_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def test_all_pages_click_render_screenshot_and_console_clean(page: Page) -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "requestfailed",
        lambda req: failed_requests.append(f"{req.resource_type}:{req.url}:{req.failure}"),
    )

    open_dashboard(page)
    for page_name, screenshot_name in PAGES:
        click_page(page, page_name)
        page.screenshot(path=str(SCREENSHOT_DIR / screenshot_name), full_page=True)

    assert page_errors == []
    assert console_errors == []
    assert failed_requests == []


def test_primary_filters_click_change_and_reset(page: Page) -> None:
    open_dashboard(page)
    dropdowns = page.get_by_role("combobox")
    assert dropdowns.count() >= 7, "Expected seven real primary dropdown controls."
    for index, label in enumerate(FILTER_LABELS):
        aria_label = primary_combobox(page, index).get_attribute("aria-label") or ""
        assert label in aria_label, f"Expected filter {index} to be {label}; aria-label was {aria_label!r}"
        open_combobox(page, index)
        assert page.get_by_role("option").count() > 0, f"{label} dropdown did not open an option list."
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)

    before = page.locator("body").inner_text(timeout=60000)
    stream_value = select_first_non_default_option(page, 0, ("All Streams",))
    expect_combobox_value(page, 0, stream_value)
    after_stream = page.locator("body").inner_text(timeout=60000)
    assert before != after_stream

    horizon_value = select_first_non_default_option(page, 4, ("1-12 Quarters",))
    expect_combobox_value(page, 4, horizon_value)
    after_horizon = page.locator("body").inner_text(timeout=60000)
    assert after_stream != after_horizon

    page.get_by_role("button", name="Reset Filters").click()
    expect_combobox_value(page, 0, "All Streams")
    expect_combobox_value(page, 1, "All Families")
    expect_combobox_value(page, 4, "1-12 Quarters")
    assert_no_streamlit_exception(page)


def test_plotly_hovers_are_human_readable_on_all_pages(page: Page) -> None:
    open_dashboard(page)
    hover_targets = [
        ("Overview", 1),
        ("Diagnostics", 0),
        ("Scenario Comparison", 1),
        ("Schiff Benchmark", 0),
    ]
    for page_name, plot_index in hover_targets:
        click_page(page, page_name)
        assert_human_hover(hover_plotly_chart(page, plot_index))


def test_governance_reproducibility_page_stream_selector_and_downloads(page: Page) -> None:
    open_dashboard(page)
    click_page(page, "Governance & Reproducibility")
    body = page.locator("body")
    r2_forecast_text = "Forecast R2 is calculated from final delivered predictions after residual correction or ensemble weighting."
    r2_calibration_text = "Calibration R2 is actual-on-forecast validation R2. Neither is in-sample OLS R2."
    expect(body).to_contain_text("Page 5 of 5 - Governance & Reproducibility", timeout=90000)
    expect(body).to_contain_text("Governance & Reproducibility Filters", timeout=60000)
    expect(body).to_contain_text("PED VKT per capita", timeout=60000)
    expect(body).to_contain_text("Light RUC volume", timeout=60000)
    expect(body).to_contain_text("Heavy RUC volume", timeout=60000)
    expect(body).to_contain_text("workbook/manifest", timeout=60000)

    page.get_by_text("Heavy RUC", exact=True).first.click()
    expect(body).to_contain_text("Exact weighted-ensemble replay", timeout=90000)
    expect(body).to_contain_text("Component trace", timeout=90000)
    expect(body).to_contain_text("Net forecast R2 after final model composition", timeout=90000)
    expect(body).to_contain_text("R2 ladder: training fit vs calibration vs forecast R2", timeout=90000)
    expect(body).to_contain_text("Training-fit R2 is computed from fitted rows inside the rolling training windows", timeout=90000)
    expect(body).to_contain_text("Training-fit R2 is not comparable to forecast R2", timeout=90000)
    expect(body).to_contain_text(r2_forecast_text, timeout=90000)
    expect(body).to_contain_text(r2_calibration_text, timeout=90000)
    expect(body).to_contain_text("Forecast R2", timeout=90000)
    expect(body).to_contain_text("Component R2", timeout=90000)
    expect(body).to_contain_text("final_pred", timeout=90000)
    expect(body).to_contain_text("Ensemble component contribution (Heavy RUC)", timeout=90000)
    expect(body).to_contain_text("Not emitted by parent component runs; future component-level replay required.", timeout=90000)
    expect(body).to_contain_text("Rerun C1-C4 component builders with coefficients/importances and scenario perturbations.", timeout=90000)
    assert page.get_by_text("Feature importance (Heavy RUC)", exact=True).count() == 0
    expect(body).to_contain_text("heavy_ruc_reproducibility_pack.zip", timeout=60000)

    page.get_by_text("Light RUC", exact=True).first.click()
    expect(body).to_contain_text("Exact prediction replay", timeout=90000)
    expect(body).to_contain_text("exp(base log prediction + residual log prediction)", timeout=90000)
    expect(body).to_contain_text("Feature importance (Light RUC)", timeout=90000)
    expect(body).to_contain_text("OLS base coefficients (Light RUC)", timeout=90000)
    expect(body).to_contain_text("Scenario sensitivities (Light RUC)", timeout=90000)
    page.get_by_text("PED", exact=True).first.click()
    expect(body).to_contain_text("PED is exact at stored component-prediction level; inner HPO/static-solver rebuild remains a future audit layer.", timeout=90000)
    expect(body).to_contain_text("Inner HPO/static-solver audit: partial", timeout=90000)
    expect(body).to_contain_text("Component contribution (PED)", timeout=90000)
    expect(body).to_contain_text("Feature-level refit not attempted; inner HPO/static-solver audit remains partial.", timeout=90000)
    expect(body).to_contain_text("Feature-level refit and exact inner weighted replay remain future audit layers.", timeout=90000)
    expect(body).to_contain_text("HPO weights grouped by source_file", timeout=90000)
    expect(body).to_contain_text("Nested trace", timeout=90000)
    expect(body).to_contain_text("Gap register", timeout=90000)
    assert page.get_by_text("Feature importance (PED)", exact=True).count() == 0
    expect(body).to_contain_text("SHAP not yet generated", timeout=60000)
    assert "This Governance & Reproducibility page is read-only" not in body.inner_text(timeout=60000)
    assert_no_streamlit_exception(page)


def test_diagnostic_pass_matrix_tooltips_hover_and_focus(page: Page) -> None:
    open_dashboard(page)
    click_page(page, "Diagnostics")
    r2_forecast_text = "Forecast R2 is calculated from final delivered predictions after residual correction or ensemble weighting."
    r2_calibration_text = "Calibration R2 is actual-on-forecast validation R2. Neither is in-sample OLS R2."

    calibration_kpi = page.locator(".kpi-title").filter(has_text="Mean calibration R2").first
    expect(calibration_kpi).to_be_visible(timeout=90000)
    tooltip_text = calibration_kpi.get_attribute("title")
    assert tooltip_text is not None
    assert "Mincer-Zarnowitz / actual-on-forecast validation R2" in tooltip_text
    assert "Forecast R2 is reported in the detail panel" in tooltip_text
    calibration_kpi.hover()
    page.get_by_text("Forecast R2 versus calibration R2", exact=True).first.click()
    expect(page.locator("body")).to_contain_text(r2_forecast_text, timeout=60000)
    expect(page.locator("body")).to_contain_text(r2_calibration_text, timeout=60000)
    expect(page.locator("body")).to_contain_text("forecast_r2", timeout=60000)
    expect(page.locator("body")).to_contain_text("calibration_r2", timeout=60000)
    expect(page.locator("body")).to_contain_text("Paper-style horizon MAPE", timeout=60000)
    expect(page.locator("body")).to_contain_text("Operational pooled MAPE", timeout=60000)
    expect(page.locator("body")).to_contain_text("source_prediction_column", timeout=60000)
    expect(page.locator("body")).to_contain_text("calibration_r2_source_column", timeout=60000)
    page.get_by_text("R2 ladder: training fit vs calibration vs forecast R2", exact=True).first.click()
    expect(page.locator("body")).to_contain_text("Training-fit R2 is computed from fitted rows inside the rolling training windows", timeout=60000)
    expect(page.locator("body")).to_contain_text("Training-fit R2 is not comparable to forecast R2", timeout=60000)
    expect(page.locator("body")).to_contain_text("training_fit_r2", timeout=60000)
    expect(page.locator("body")).to_contain_text("availability_status", timeout=60000)

    matrix = page.locator(".diagnostic-tooltip-matrix")
    expect(matrix).to_be_visible(timeout=90000)
    assert visible_text_absent(page, "Diagnostics evidence:")
    assert visible_text_absent(page, "Diagnostics governance notes")
    assert visible_text_absent(page, "Model Explainability / Reproducibility")
    assert visible_text_absent(page, "Green = pass")

    adf_header = matrix.locator(".diag-header-tooltip").filter(has_text="ADF").first
    expect(adf_header).to_be_visible(timeout=60000)
    adf_header.hover()
    expect(adf_header.locator(".diag-tooltip-text")).to_be_visible(timeout=10000)
    expect(adf_header.locator(".diag-tooltip-text")).to_contain_text("Augmented Dickey-Fuller test", timeout=10000)

    kpss_header = matrix.locator(".diag-header-tooltip").filter(has_text="KPSS").first
    kpss_header.focus()
    expect(kpss_header.locator(".diag-tooltip-text")).to_be_visible(timeout=10000)
    expect(kpss_header.locator(".diag-tooltip-text")).to_contain_text("Kwiatkowski-Phillips-Schmidt-Shin test", timeout=10000)

    white_cell = matrix.locator("td").filter(has_text=re.compile(r"Pass|Watch|Fail")).nth(5)
    white_trigger = white_cell.locator(".diag-tooltip-trigger")
    white_trigger.focus()
    expect(white_trigger.locator(".diag-tooltip-text")).to_be_visible(timeout=10000)
    expect(white_trigger.locator(".diag-tooltip-text")).to_contain_text("Status:", timeout=10000)
    chart_header = page.locator(".chart-card-header").filter(has_text="3. Diagnostic Pass Matrix").first
    legend_trigger = chart_header.locator(".chart-info-trigger").first
    legend_trigger.hover()
    expect(legend_trigger.locator(".chart-info-text")).to_contain_text("Green = pass", timeout=10000)
    assert_no_streamlit_exception(page)


def test_benchmark_and_decision_summary_tooltips_hover_and_focus(page: Page) -> None:
    open_dashboard(page)
    click_page(page, "Schiff Benchmark")

    benchmark_table = page.locator(".summary-tooltip-table").filter(has_text="Paired Win Rate").first
    expect(benchmark_table).to_be_visible(timeout=90000)
    paired_header = benchmark_table.locator("th").filter(has_text="Paired Win Rate").first
    paired_trigger = paired_header.locator(".summary-tooltip-trigger").first
    paired_trigger.hover()
    expect(paired_trigger.locator(".summary-tooltip-text")).to_be_visible(timeout=10000)
    expect(paired_trigger.locator(".summary-tooltip-text")).to_contain_text(
        "matched forecast comparisons",
        timeout=10000,
    )
    paired_trigger.focus()
    expect(paired_trigger.locator(".summary-tooltip-text")).to_contain_text(
        "same stream, origin, target period and horizon",
        timeout=10000,
    )

    click_page(page, "Scenario Comparison")
    decision_table = page.locator(".summary-tooltip-table").filter(has_text="Recommendation").first
    expect(decision_table).to_be_visible(timeout=90000)
    recommendation_header = decision_table.locator("th").filter(has_text="Recommendation").first
    recommendation_trigger = recommendation_header.locator(".summary-tooltip-trigger").first
    recommendation_trigger.hover()
    expect(recommendation_trigger.locator(".summary-tooltip-text")).to_be_visible(timeout=10000)
    expect(recommendation_trigger.locator(".summary-tooltip-text")).to_contain_text(
        "MAPE gain, paired win rate, diagnostics and caveats",
        timeout=10000,
    )

    promote_badge = decision_table.locator(".summary-rec-badge").filter(has_text="Promote").first
    expect(promote_badge).to_be_visible(timeout=30000)
    promote_badge.focus()
    expect(promote_badge.locator(".summary-tooltip-text")).to_contain_text(
        "Promoted because the finalist beats the Schiff specification benchmark",
        timeout=10000,
    )
    assert_no_streamlit_exception(page)


def test_no_stale_finalist_values_visible(page: Page) -> None:
    open_dashboard(page)
    body = page.locator("body").inner_text(timeout=60000)
    for value in ["5.49%", "9.15%", "12.38%", "+2.40 pp"]:
        assert value not in body, f"Stale finalist value still visible: {value}"


def test_rendered_plotly_trace_data_matches_chart_sources_where_possible(page: Page) -> None:
    open_dashboard(page)

    candidate_source = pd.read_csv(CHART_SOURCE_DIR / "overview_candidate_search_frontier.csv")
    click_page(page, "Overview")
    page.get_by_text("2. Candidate Search Frontier", exact=False).first.scroll_into_view_if_needed()
    expect(page.locator(".js-plotly-plot").nth(1)).to_be_visible(timeout=90000)
    body_text = page.locator("body").inner_text(timeout=60000)
    frontier_info = chart_info_text(page, "2. Candidate Search Frontier")
    assert "400 plotted candidates from 400 curated rows" in frontier_info
    assert "Balanced all-stream frontier view" in frontier_info
    assert "excluded from governance scoring" in frontier_info
    assert visible_text_absent(page, "Balanced all-stream frontier view")
    assert visible_text_absent(page, "Frontier read:")
    assert "Candidate frontier mode" not in body_text
    assert "278 loaded candidates" not in body_text
    candidate_plot = page.evaluate(
        """() => {
            const pointCount = (trace) => {
                if (Number.isFinite(trace._length)) return trace._length;
                if (trace.x && Number.isFinite(trace.x.length)) return trace.x.length;
                return Array.from(trace.x || []).length;
            };
            let bestCount = null;
            for (const plot of document.querySelectorAll('.js-plotly-plot')) {
                const count = (plot._fullData || plot.data || [])
                    .filter((trace) => String(trace.mode || '').includes('markers'))
                    .reduce((total, trace) => total + pointCount(trace), 0);
                if (count > 100 && (bestCount === null || count > bestCount)) {
                    bestCount = count;
                }
            }
            return bestCount;
        }"""
    )
    assert candidate_plot == len(candidate_source)

    stress_source = pd.read_csv(CHART_SOURCE_DIR / "overview_stress_horizon_checks.csv")
    stress_plot = page.evaluate(
        """() => {
            const plot = [...document.querySelectorAll('.js-plotly-plot')].find((candidate) => {
                const categories = Array.from(candidate.layout?.xaxis?.categoryarray || []);
                return categories.includes('1-4 qtrs')
                    && categories.includes('Annual')
                    && !categories.includes('2022-23')
                    && !categories.includes('2024+')
                    && (candidate.data || []).some((trace) => trace.name === 'PED VKT per capita');
            });
            if (!plot) return null;
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
    assert stress_plot is not None, "Could not find rendered Stress and Horizon Plotly chart."
    expected_buckets = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]
    assert stress_plot["categories"] == expected_buckets
    for trace in stress_plot["traces"]:
        if trace["name"] not in {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}:
            continue
        assert trace["connectgaps"] is False
        source_rows = stress_source[stress_source["stream_label"].eq(trace["name"])].set_index("stress_bucket")
        rendered = dict(zip(trace["x"], trace["y"]))
        for bucket in expected_buckets:
            source_value = pd.to_numeric(source_rows.loc[bucket, "metric_value"], errors="coerce")
            rendered_value = rendered[bucket]
            if pd.isna(source_value):
                assert browser_value_missing(rendered_value), f"{trace['name']} {bucket} should render as a gap."
            else:
                assert float(rendered_value) == pytest.approx(float(source_value), abs=0.001)

    click_page(page, "Diagnostics")
    acf_source = pd.read_csv(CHART_SOURCE_DIR / "diagnostics_residual_autocorrelation.csv")
    assert set(acf_source["notes"]) == {"All selected quarterly residuals averaged by target period"}
    assert not acf_source.duplicated(["stream_label", "lag"]).any()
    acf_plot = page.evaluate(
        """() => {
            const plot = [...document.querySelectorAll('.js-plotly-plot')].find((candidate) => {
                const xTitle = candidate.layout?.xaxis?.title?.text || '';
                const yTitle = candidate.layout?.yaxis?.title?.text || '';
                return xTitle.includes('Lag') && yTitle.includes('Residual ACF');
            });
            if (!plot) return null;
            return (plot._fullData || plot.data || []).map((trace) => ({
                name: trace.name,
                x: Array.from(trace.x || []),
                y: Array.from(trace.y?._inputArray || trace.y || []),
            }));
        }"""
    )
    assert acf_plot is not None
    for trace in acf_plot:
        source_rows = acf_source[acf_source["stream_label"].eq(trace["name"])].sort_values("lag")
        if source_rows.empty:
            continue
        assert trace["x"] == source_rows["lag"].astype(int).tolist()
        assert [float(value) for value in trace["y"]] == pytest.approx(source_rows["metric_value"].astype(float).tolist(), abs=0.001)

    click_page(page, "Schiff Benchmark")
    expect(page.locator("body")).to_contain_text("3. Full-sample Gain vs Schiff specification benchmark", timeout=90000)
    assert "Paired Gain vs Schiff" not in page.locator("body").inner_text(timeout=60000)
    schiff_gain = pd.read_csv(CHART_SOURCE_DIR / "schiff_paired_or_fullsample_gain.csv")
    light = schiff_gain[schiff_gain["stream_label"].eq("Light RUC volume")]
    assert float(light[light["metric_name"].eq("Full-sample quarterly gain")]["metric_value"].iloc[0]) == pytest.approx(
        3.158190, abs=0.001
    )
    assert float(light[light["metric_name"].eq("Full-sample annual gain")]["metric_value"].iloc[0]) == pytest.approx(
        1.428227, abs=0.001
    )
    assert float(light["paired_gain_pp"].dropna().iloc[0]) == pytest.approx(2.932205, abs=0.001)

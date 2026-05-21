from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


def test_dashboard_pages_render_without_browser_errors(page: Page) -> None:
    base_url = os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501")
    page.set_viewport_size({"width": 1680, "height": 940})
    artifact_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    page.goto(base_url, wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    body = page.locator("body").inner_text(timeout=60000)
    assert "‹nchmark" not in body
    assert "Schiff Benchmark" in body
    assert "Deploy" not in body
    assert "Stream: All Streams" in body
    assert "Model Family: All Families" in body
    assert "Horizon: 1-12 Quarters" in body
    assert "Forecast Vintage: Latest" in body
    assert "Date Window: All target periods" in body
    assert page.get_by_role("radio").count() >= 4

    for text in [
        "Quarterly MAPE",
        "Annual MAPE",
        "Candidate Models",
        "Governance Score",
        "beat pure Schiff",
        "logged diagnostics",
        "Run evidence:",
        "files loaded",
        "Family scope:",
        "Frontier read: lower-left is better",
        "Stress watch:",
        "Error distribution read:",
        "1. Finalist Forecast Accuracy",
        "2. Candidate Search Landscape",
        "3. Finalist Ensemble Composition",
        "4. Stress and Horizon Checks",
        "Central absolute percentage error",
    ]:
        expect(page.locator("body")).to_contain_text(text, timeout=60000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    expect(page.locator("body")).to_contain_text("5. Distribution of Forecast Error by Horizon Bucket", timeout=60000)
    page.evaluate("window.scrollTo(0, 0)")
    wait_for_rendered_surfaces(page)
    assert rendered_surface_count(page) >= 5
    save_dashboard_screenshot(page, artifact_dir, "mcp-01-overview.png")
    save_dashboard_screenshot(page, artifact_dir, "mcp-01-executive-summary.png")

    checks = [
        (
            "Diagnostics",
            "Page 2 of 4 - Diagnostics",
            "mcp-02-diagnostics.png",
            [
                "Stationarity / Test Matrix",
                "Diagnostic Coverage",
                "Logged Diagnostics",
                "Diagnostics evidence:",
                "Residual ACF bars by lag",
                "Autocorrelation Diagnostics",
                "Heteroscedasticity / Error Diagnostics",
                "Diagnostics Summary Table",
                "Model Inventory module",
                "Run Audit module",
            ],
        ),
        (
            "Scenario Comparison",
            "Page 3 of 4 - Scenario Comparison",
            "mcp-03-scenario-comparison.png",
                [
                    "Scenario A",
                    "Scenario B",
                    "Scenario A vs pure Schiff",
                    "Scenario Accuracy Comparison",
                    "Error by Forecast Horizon",
                    "Improvement vs Benchmark",
                    "Forecast Error Distribution by Scenario",
                    "Central finalist error distribution",
                    "Model & Test Summary",
                    "Decision Lens",
                    "before Stage 2",
                    "win rate above 55%",
                    "full forecast-error tails",
                    "Forecast and stress drilldown",
                ],
        ),
        (
            "Schiff Benchmark",
            "Page 4 of 4 - Schiff Benchmark",
            "mcp-04-schiff-benchmark.png",
            [
                "Schiff Structural Benchmark: Quarterly vs Annual MAPE",
                "Pure-Schiff Streams",
                "structural benchmark only",
                "Paper Replication Notes",
                "Benchmark Comparison Summary",
                "Best paired challenger:",
                "About the Schiff Benchmark",
                "Candidate and ensemble evidence drilldown",
                "pure Schiff",
            ],
        ),
    ]

    for tab_label, expected_text, screenshot_name, page_texts in checks:
        click_governance_nav(page, tab_label)
        expect(page.locator("body")).to_contain_text(expected_text, timeout=60000)
        for text in page_texts:
            expect(page.locator("body")).to_contain_text(text, timeout=60000)
        if tab_label == "Diagnostics":
            page.evaluate("window.scrollTo(0, 0)")
            for title in [
                "1. Stationarity / Test Matrix",
                "2. Autocorrelation Diagnostics",
                "3. Heteroscedasticity / Error Diagnostics",
                "4. Residual vs Fitted Equivalent",
                "5. Residual Normality / Error Distribution",
                "6. Diagnostics Summary Table",
            ]:
                assert_text_above_fold(page, title)
            expect(page.locator("body")).to_contain_text("Residual-style scatter by fitted value", timeout=60000)
        if tab_label == "Scenario Comparison":
            page.evaluate("window.scrollTo(0, 0)")
            expect(page.locator("body")).to_contain_text("Scenario A: Refined Finalist Ensemble", timeout=60000)
            expect(page.locator("body")).to_contain_text("Scenario B: Schiff Structural Benchmark", timeout=60000)
            expect(page.get_by_role("button", name="Edit")).to_be_visible(timeout=60000)
            assert "Scenario settings" not in page.locator("body").inner_text(timeout=60000)
            for title in [
                "1. Scenario Accuracy Comparison",
                "2. Error by Forecast Horizon",
                "3. Improvement vs Benchmark",
                "4. Forecast Error Distribution by Scenario",
                "5. Model & Test Summary",
                "6. Decision Lens",
            ]:
                assert_text_above_fold(page, title)
        if tab_label == "Schiff Benchmark":
            page.evaluate("window.scrollTo(0, 0)")
            for title in [
                "1. Schiff Structural Benchmark: Quarterly vs Annual MAPE",
                "2. Light RUC Cross-Validation Results",
                "3. Heavy RUC Cross-Validation Results",
                "4. PED VKT Cross-Validation Results",
                "6. Paper Replication Notes",
            ]:
                assert_text_above_fold(page, title)
        assert rendered_surface_count(page) > 0
        save_dashboard_screenshot(page, artifact_dir, screenshot_name)
        if screenshot_name == "mcp-04-schiff-benchmark.png":
            save_dashboard_screenshot(page, artifact_dir, "mcp-03-schiff-comparison.png")

    assert not page.locator("[data-testid='stException']").count()
    assert page_errors == []
    assert console_errors == []


def test_navigation_labels_not_clipped(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    body = page.locator("body").inner_text(timeout=60000)
    assert "‹nchmark" not in body
    assert "Schiff Benchmark" in body
    expect(page.locator("body")).to_contain_text("Candidate Search Landscape", timeout=90000)
    expect(page.locator("body")).to_contain_text("Finalist Ensemble Composition", timeout=90000)
    for label in ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark"]:
        expect(governance_nav_label(page, label)).to_be_visible(timeout=60000)


def test_latest_arbitration_values_are_visible_not_stale(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    body = page.locator("body").inner_text(timeout=60000)

    assert "run_20260520_002339" in body
    assert "Source: Latest arbitration run" in body
    for expected in ["2.47%", "2.39%", "9.15%", "6.00%", "3.56%", "3.17%"]:
        assert expected in body

    for stale in ["5.49%", "11.55%", "12.38%"]:
        assert stale not in body


def test_visible_navigation_text_changes_page_body(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    for label, expected_content, stale_content in [
        ("Diagnostics", "1. Stationarity / Test Matrix", "1. Finalist Forecast Accuracy"),
        ("Scenario Comparison", "1. Scenario Accuracy Comparison", "1. Stationarity / Test Matrix"),
        ("Schiff Benchmark", "1. Schiff Structural Benchmark", "1. Scenario Accuracy Comparison"),
        ("Overview", "1. Finalist Forecast Accuracy", "1. Schiff Structural Benchmark"),
    ]:
        target = page.get_by_text(label, exact=True)
        assert target.count() == 1
        target.click()
        expected = page.get_by_text(expected_content, exact=False).first
        expect(expected).to_be_visible(timeout=60000)
        expected_box = expected.bounding_box()
        assert expected_box is not None
        assert expected_box["y"] < 620
        stale_visible = page.evaluate(
            """(text) => {
                return Array.from(document.querySelectorAll('body *')).some((node) => {
                    if (!node.textContent?.includes(text)) return false;
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && Number(style.opacity || 1) > 0.01
                        && rect.width > 1
                        && rect.height > 1
                        && rect.top >= 0
                        && rect.top < 620;
                });
            }""",
            stale_content,
        )
        assert stale_visible is False


def test_reference_header_nav_is_integrated_on_desktop(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    title_box = page.get_by_text("Governance", exact=True).first.bounding_box()
    overview_box = governance_nav_label(page, "Overview").bounding_box()
    benchmark_box = governance_nav_label(page, "Schiff Benchmark").bounding_box()
    filter_box = page.locator(".filter-title").first.bounding_box()

    assert title_box is not None
    assert overview_box is not None
    assert benchmark_box is not None
    assert filter_box is not None
    assert overview_box["y"] < 65
    assert benchmark_box["y"] < 65
    assert benchmark_box["x"] > title_box["x"] + 380
    assert filter_box["y"] < 120


def test_filter_values_are_readable(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    body = page.locator("body").inner_text(timeout=60000)
    assert "Stream: All Streams" in body
    assert "Model Family: All Families" in body
    assert "Horizon: 1-12 Quarters" in body


def test_filter_band_is_reference_compact(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    filter_title = page.locator(".filter-title").first.bounding_box()
    first_kpi = page.locator(".gov-kpi-card").first.bounding_box()
    first_chart = page.get_by_text("1. Finalist Forecast Accuracy", exact=False).first.bounding_box()
    assert filter_title is not None
    assert first_kpi is not None
    assert first_chart is not None
    assert first_kpi["y"] - filter_title["y"] < 120
    assert first_kpi["y"] < 220
    assert first_chart["y"] < 330


def test_governance_shell_is_readable_in_narrow_browser(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    for label in ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark"]:
        expect(governance_nav_label(page, label)).to_be_visible(timeout=60000)

    title_box = page.get_by_text("Governance", exact=True).first.bounding_box()
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
    assert "Page 1 of 4 - Overview" in body
    assert "Stream: All Streams" in body
    assert "Model Family: All Families" in body
    assert "Date Window: All target periods" in body

    first_chart = page.get_by_text("1. Finalist Forecast Accuracy", exact=False).first
    second_chart = page.get_by_text("2. Candidate Search Landscape", exact=False).first
    expect(first_chart).to_be_visible(timeout=90000)
    expect(second_chart).to_be_visible(timeout=90000)
    first_box = first_chart.bounding_box()
    second_box = second_chart.bounding_box()
    assert first_box is not None
    assert second_box is not None
    assert abs(second_box["y"] - first_box["y"]) < 90
    assert second_box["x"] > first_box["x"] + 100


def test_primary_reference_pages_use_icon_kpi_rows(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    for tab_label, left_label, right_label in [
        ("Diagnostics", "Diagnostic Coverage", "Ray Root Causes"),
        ("Schiff Benchmark", "Pure-Schiff Streams", "Paired Comparisons"),
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
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    click_governance_nav(page, "Diagnostics")
    expect(page.locator("body")).to_contain_text("Page 2 of 4 - Diagnostics", timeout=60000)
    expect(page.locator("body")).to_contain_text("Diagnostics evidence:", timeout=60000)
    expect(page.locator("body")).to_contain_text("proxy panels shown", timeout=60000)
    expect(page.locator("body")).to_contain_text("Diagnostic read: residual persistence", timeout=60000)
    for title in [
        "1. Stationarity / Test Matrix",
        "2. Autocorrelation Diagnostics",
        "3. Heteroscedasticity / Error Diagnostics",
    ]:
        assert_text_above_fold(page, title)

    overview_ghost_visible = page.evaluate(
        """() => {
            const needles = [
                '5. Distribution of Forecast Error by Horizon Bucket',
                'Stress watch:',
                'Error distribution read:'
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
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text("Page 3 of 4 - Scenario Comparison", timeout=60000)
    for title in [
        "1. Scenario Accuracy Comparison",
        "2. Error by Forecast Horizon",
        "3. Improvement vs Benchmark",
    ]:
        assert_text_above_fold(page, title, max_y=820)

    improvement_box = page.get_by_text("3. Improvement vs Benchmark", exact=False).first.bounding_box()
    assert improvement_box is not None
    assert improvement_box["y"] < 790


def test_overview_has_dashboard_grid(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("Finalist Forecast Accuracy", timeout=90000)
    expect(page.locator("body")).to_contain_text("Candidate Search Landscape", timeout=90000)
    expect(page.locator("body")).to_contain_text("Finalist Ensemble Composition", timeout=90000)
    body = page.locator("body").inner_text(timeout=60000)
    assert "Candidate Search Landscape" in body
    assert "Finalist Ensemble Composition" in body
    expect(page.locator("body")).to_contain_text("Stress and Horizon Checks", timeout=60000)
    expect(page.locator("body")).to_contain_text("Distribution of Forecast Error", timeout=60000)
    page.evaluate("window.scrollTo(0, 0)")
    for title in [
        "1. Finalist Forecast Accuracy",
        "2. Candidate Search Landscape",
        "3. Finalist Ensemble Composition",
        "4. Stress and Horizon Checks",
        "5. Distribution of Forecast Error by Horizon Bucket",
    ]:
        assert_text_above_fold(page, title)
    body = page.locator("body").inner_text(timeout=60000)
    assert "Stress and Horizon Checks" in body
    assert "Distribution of Forecast Error" in body


def test_ensemble_composition_has_three_stream_panels(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("Finalist Ensemble Composition", timeout=90000)
    expect(page.locator("body")).to_contain_text("PED VKT per capita", timeout=90000)
    expect(page.locator("body")).to_contain_text("Light RUC volume", timeout=90000)
    expect(page.locator("body")).to_contain_text("Heavy RUC volume", timeout=90000)
    page.evaluate("window.scrollTo(0, 760)")
    body = page.locator("body").inner_text(timeout=60000)
    assert "PED VKT per capita" in body
    assert "Light RUC volume" in body
    assert "Heavy RUC volume" in body


def wait_dashboard_ready(page: Page) -> None:
    expect(page.get_by_text("Governance").first).to_be_visible(timeout=90000)
    expect(page.get_by_text("WAKA KOTAHI")).to_be_visible(timeout=90000)
    expect(page.get_by_text("GOVERNANCE FILTERS")).to_be_visible(timeout=90000)
    expect(page.get_by_role("button", name="Reset Filters")).to_be_visible(timeout=90000)
    expect(page.locator("body")).to_contain_text("Page 1 of 4 - Overview", timeout=90000)
    expect(page.locator("body")).to_contain_text("Schiff Benchmark", timeout=90000)


def rendered_surface_count(page: Page) -> int:
    return page.locator(".js-plotly-plot, svg.main-svg, canvas, [data-testid='stDataFrame']").count()


def wait_for_rendered_surfaces(page: Page) -> None:
    page.wait_for_function(
        """() => document.querySelectorAll(
            '.js-plotly-plot, svg.main-svg, canvas, [data-testid="stDataFrame"]'
        ).length >= 5""",
        timeout=90000,
    )


def governance_nav_label(page: Page, label: str):
    return page.locator("div[data-testid='stRadio'] label").filter(has_text=label).first


def click_governance_nav(page: Page, label: str) -> None:
    governance_nav_label(page, label).click()


def save_dashboard_screenshot(page: Page, artifact_dir: Path, screenshot_name: str) -> None:
    page.screenshot(path=artifact_dir / screenshot_name, full_page=True)
    final_name = screenshot_name.replace("mcp-", "final-", 1)
    page.screenshot(path=artifact_dir / final_name, full_page=True)


def assert_text_above_fold(page: Page, text: str, max_y: int = 930) -> None:
    locator = page.get_by_text(text, exact=False).first
    locator.wait_for(state="visible", timeout=60000)
    box = locator.bounding_box()
    assert box is not None, f"{text!r} has no visible bounding box"
    assert box["y"] < max_y, f"{text!r} should be visible above the first viewport fold; y={box['y']}"

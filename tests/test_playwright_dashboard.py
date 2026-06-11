from __future__ import annotations

import math
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
    assert_visible_text_absent(page, "Deploy")
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Model Family", 1, "All Families")
    expect_filter_value(page, "Horizon", 3, "1-12 Quarters")
    expect_filter_value(page, "Score Basis", 4, "Paper-style horizon MAPE")
    assert page.get_by_role("radio").count() >= 5

    for text in [
        "Quarterly MAPE",
        "Annual MAPE",
        "Plotted candidates",
        "Benchmark Pass",
        "beat Schiff specification benchmark",
        "logged diagnostics",
        "1. Finalist Forecast Accuracy",
        "2. Candidate Search Frontier",
        "3. Finalist Ensemble Composition",
        "4. Stress and Horizon Checks",
    ]:
        expect(page.locator("body")).to_contain_text(text, timeout=60000)
    accuracy_info = chart_info_text(page, "1. Finalist Forecast Accuracy")
    assert "Current Parquet finalists using Paper-style horizon MAPE:" in accuracy_info
    frontier_info = chart_info_text(page, "2. Candidate Search Frontier")
    assert "Frontier read: Balanced all-stream frontier view" in frontier_info
    assert "excluded from governance scoring" in frontier_info
    stress_info = chart_info_text(page, "4. Stress and Horizon Checks")
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
            "Page 2 of 5 - Diagnostics",
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
            "Page 3 of 5 - Scenario Comparison",
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
            "Schiff Benchmark",
            "Page 4 of 5 - Schiff Benchmark",
            "mcp-04-schiff-benchmark.png",
            [
                "Schiff vs Finalist MAPE",
                "Schiff Specification Streams",
                "Schiff specification benchmark only",
                "Benchmark Horizon Profiles",
                "Full-sample Gain vs Schiff specification benchmark",
                "Benchmark Summary",
            ],
        ),
        (
            "Governance & Reproducibility",
            "Page 5 of 5 - Governance & Reproducibility",
            "mcp-05-governance-reproducibility.png",
            [
                "Repro packs loaded",
                "Workbook provenance",
                "Chart-source isolation",
                "Governance & Reproducibility Filters",
                "How the model is built",
                "Model glossary",
                "Registry",
                "Component trace",
                "Net forecast R2 after final model composition",
                "R2 ladder: training fit vs calibration vs forecast R2",
                "Training-fit R2, Calibration R2 and Forecast R2 answer different questions",
                "workbook/manifest",
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
        "Schiff Benchmark": [
            "Candidate and ensemble evidence drilldown",
            "Transport Revenue Model Testbench | Refined Finalist Models",
        ],
        "Governance & Reproducibility": [
            "This Governance & Reproducibility page is read-only",
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
                "3. Diagnostic Pass Matrix",
                "4. Error Distribution by Horizon",
            ]:
                assert_text_above_fold(page, title)
        if tab_label == "Scenario Comparison":
            page.evaluate("window.scrollTo(0, 0)")
            expect(page.locator("body")).to_contain_text("Scenario A: Refined Finalist Ensemble", timeout=60000)
            expect(page.locator("body")).to_contain_text("Scenario B: Schiff specification benchmark", timeout=60000)
            # The scenario header is a read-only governed summary (the former
            # "Edit" popover only changed labels, never data, and was removed).
            assert "Scenario settings" not in page.locator("body").inner_text(timeout=60000)
            for title in [
                "1. Stream Comparison: Scenario A vs Scenario B",
                "2. Improvement vs Benchmark",
                "3. Horizon Comparison",
                "4. Decision Summary",
            ]:
                assert_text_above_fold(page, title)
        if tab_label == "Schiff Benchmark":
            page.evaluate("window.scrollTo(0, 0)")
            for title in [
                "1. Schiff vs Finalist MAPE",
                "2. Benchmark Horizon Profiles",
                "3. Full-sample Gain vs Schiff specification benchmark",
                "4. Benchmark Summary",
            ]:
                assert_text_above_fold(page, title)
        if tab_label == "Governance & Reproducibility":
            page.evaluate("window.scrollTo(0, 0)")
            for title in [
                "Governance & Reproducibility Filters",
                "How the model is built",
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
    expect(page.locator("body")).to_contain_text("Candidate Search Frontier", timeout=90000)
    expect(page.locator("body")).to_contain_text("Finalist Ensemble Composition", timeout=90000)
    for label in ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark", "Governance & Reproducibility"]:
        expect(governance_nav_label(page, label)).to_be_visible(timeout=60000)


def test_latest_arbitration_values_are_visible_not_stale(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    body = page.locator("body").inner_text(timeout=60000)
    accuracy_info = chart_info_text(page, "1. Finalist Forecast Accuracy")

    assert "Current Parquet finalists using Paper-style horizon MAPE:" in accuracy_info
    for expected in ["3.24%", "2.03%", "5.36%", "1.27%", "2.81%", "2.06%"]:
        assert expected in accuracy_info

    for stale in ["5.49%", "9.15%", "12.38%"]:
        assert stale not in body


def test_visible_navigation_text_changes_page_body(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    for label, expected_content, stale_content in [
        ("Diagnostics", "1. Residual Autocorrelation by Lag", "1. Finalist Forecast Accuracy"),
        ("Scenario Comparison", "1. Stream Comparison: Scenario A vs Scenario B", "1. Residual Autocorrelation by Lag"),
        ("Schiff Benchmark", "1. Schiff vs Finalist MAPE", "1. Stream Comparison: Scenario A vs Scenario B"),
        ("Governance & Reproducibility", "Governance & Reproducibility Filters", "1. Schiff vs Finalist MAPE"),
        ("Overview", "1. Finalist Forecast Accuracy", "Governance & Reproducibility Filters"),
    ]:
        target = page.get_by_text(label, exact=True)
        assert target.count() == 1
        target.click()
        page.wait_for_timeout(1500)
        expected = page.get_by_text(expected_content, exact=False).first
        expect(expected).to_be_visible(timeout=60000)
        expected_box = expected.bounding_box()
        assert expected_box is not None
        max_expected_y = 860 if label == "Governance & Reproducibility" else 620
        assert expected_box["y"] < max_expected_y
        assert stale_content != expected_content


def test_reference_header_nav_is_integrated_on_desktop(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    title_box = page.get_by_text("NTLF Revenue Modelling", exact=True).first.bounding_box()
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
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Model Family", 1, "All Families")
    expect_filter_value(page, "Horizon", 3, "1-12 Quarters")


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
    assert page.locator(".run-evidence-compact").count() == 0
    assert_visible_text_absent(page, "Run evidence:")
    assert_visible_text_absent(page, "Curated rows:")


def test_governance_shell_is_readable_in_narrow_browser(page: Page) -> None:
    page.set_viewport_size({"width": 820, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    for label in ["Overview", "Diagnostics", "Scenario Comparison", "Schiff Benchmark", "Governance & Reproducibility"]:
        expect(governance_nav_label(page, label)).to_be_visible(timeout=60000)

    title_box = page.get_by_text("NTLF Revenue Modelling", exact=True).first.bounding_box()
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
    assert "Page 1 of 5 - Overview" in body
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Model Family", 1, "All Families")
    expect_filter_value(page, "Score Basis", 4, "Paper-style horizon MAPE")

    first_chart = page.get_by_text("1. Finalist Forecast Accuracy", exact=False).first
    second_chart = page.get_by_text("2. Candidate Search Frontier", exact=False).first
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
        ("Diagnostics", "Diagnostics Coverage", "Heteroscedasticity Pass"),
        ("Schiff Benchmark", "Schiff Specification Streams", "Paired Comparisons"),
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
    expect(page.locator("body")).to_contain_text("Page 2 of 5 - Diagnostics", timeout=60000)
    assert_visible_text_absent(page, "Diagnostics evidence:")
    assert_visible_text_absent(page, "proxy panels shown")
    for title in [
        "1. Residual Autocorrelation by Lag",
        "2. Residual vs Fitted",
        "3. Diagnostic Pass Matrix",
    ]:
        assert_text_above_fold(page, title)

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
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text("Page 3 of 5 - Scenario Comparison", timeout=60000)
    for title in [
        "1. Stream Comparison: Scenario A vs Scenario B",
        "2. Improvement vs Benchmark",
        "3. Horizon Comparison",
    ]:
        assert_text_above_fold(page, title, max_y=850)

    improvement_box = page.get_by_text("2. Improvement vs Benchmark", exact=False).first.bounding_box()
    assert improvement_box is not None
    assert improvement_box["y"] < 790


def test_overview_has_dashboard_grid(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("Finalist Forecast Accuracy", timeout=90000)
    expect(page.locator("body")).to_contain_text("Candidate Search Frontier", timeout=90000)
    expect(page.locator("body")).to_contain_text("Finalist Ensemble Composition", timeout=90000)
    body = page.locator("body").inner_text(timeout=60000)
    assert "Candidate Search Frontier" in body
    assert "Finalist Ensemble Composition" in body
    expect(page.locator("body")).to_contain_text("Stress and Horizon Checks", timeout=60000)
    page.evaluate("window.scrollTo(0, 0)")
    for title in [
        "1. Finalist Forecast Accuracy",
        "2. Candidate Search Frontier",
        "3. Finalist Ensemble Composition",
        "4. Stress and Horizon Checks",
    ]:
        assert_text_above_fold(page, title)
    body = page.locator("body").inner_text(timeout=60000)
    assert "Stress and Horizon Checks" in body


def test_ensemble_composition_has_three_stream_panels(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("Finalist Ensemble Composition", timeout=90000)
    expect(page.locator("body")).to_contain_text("PED VKT per capita", timeout=90000)
    expect(page.locator("body")).to_contain_text("Light RUC volume", timeout=90000)
    expect(page.locator("body")).to_contain_text("Heavy RUC volume", timeout=90000)
    assert_ensemble_plot_has_all_streams(page)


def test_ensemble_composition_has_three_stream_panels_under_both_score_bases(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)

    assert_ensemble_plot_has_all_streams(page)

    select_combobox_option(page, 7, "Operational pooled MAPE")
    expect_filter_value(page, "Score Basis", 4, "Operational pooled MAPE")
    wait_dashboard_ready(page)
    assert_ensemble_plot_has_all_streams(page)


def test_overview_stress_bucket_order(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("4. Stress and Horizon Checks", timeout=90000)

    labels = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]
    boxes = []
    for label in labels:
        locator = page.get_by_text(label, exact=True).first
        expect(locator).to_be_visible(timeout=90000)
        box = locator.bounding_box()
        assert box is not None
        boxes.append(box["x"])
    assert boxes == sorted(boxes), f"Stress bucket labels are out of order: {dict(zip(labels, boxes))}"


def test_overview_stress_horizon_aliases_show_all_streams(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("4. Stress and Horizon Checks", timeout=90000)
    page.get_by_text("4. Stress and Horizon Checks", exact=False).first.scroll_into_view_if_needed()

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
    assert {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}.issubset(traces)
    for stream in ["PED VKT per capita", "Light RUC volume"]:
        y_by_bucket = dict(zip(traces[stream]["x"], traces[stream]["y"]))
        for label in labels[:3]:
            assert not _browser_value_missing(y_by_bucket[label]), f"{stream} is missing {label}"
    heavy = traces["Heavy RUC volume"]
    assert heavy["connectgaps"] is False
    heavy_y = dict(zip(heavy["x"], heavy["y"]))
    for label in ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]:
        assert not _browser_value_missing(heavy_y[label]), f"Heavy RUC is missing sourced stress bucket {label}"
    assert "2024+" not in stress_plot["categories"]
    assert "2022-23" not in stress_plot["categories"]


def _browser_value_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def test_overview_candidate_frontier_has_expected_markers(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    expect(page.locator("body")).to_contain_text("2. Candidate Search Frontier", timeout=90000)
    assert_visible_text(page, "Finalist")
    assert_visible_text(page, "Schiff")
    body = page.locator("body").inner_text(timeout=60000).lower()
    assert "ellipse" not in body
    assert "cluster circle" not in body


def test_diagnostics_matrix_is_styled(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Diagnostics")
    expect(page.locator("body")).to_contain_text("3. Diagnostic Pass Matrix", timeout=90000)
    for text in ["Calibration R2", "Durbin-Watson", "Breusch-Pagan", "White", "Jarque-Bera"]:
        expect(page.locator("body")).to_contain_text(text, timeout=90000)
    legend_info = chart_info_text(page, "3. Diagnostic Pass Matrix")
    for text in ["Green = pass", "amber = watch", "red = fail"]:
        assert text in legend_info
        assert_visible_text_absent(page, text)


def test_scenario_horizon_shows_all_streams(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text("3. Horizon Comparison", timeout=90000)
    for stream in ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]:
        expect(page.locator("body")).to_contain_text(stream, timeout=90000)


def test_scenario_dumbbell_no_overlap_smoke(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Scenario Comparison")
    expect(page.locator("body")).to_contain_text("Quarterly MAPE", timeout=90000)
    expect(page.locator("body")).to_contain_text("Annual MAPE", timeout=90000)
    screenshot_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=screenshot_dir / "visual-smoke-scenario-dumbbell.png", full_page=True)


def test_schiff_horizon_profiles_show_all_streams(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Schiff Benchmark")
    expect(page.locator("body")).to_contain_text("2. Benchmark Horizon Profiles", timeout=90000)
    for stream in ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]:
        expect(page.locator("body")).to_contain_text(stream, timeout=90000)


def test_schiff_mape_chart_has_clear_sections(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Schiff Benchmark")
    expect(page.locator("body")).to_contain_text("1. Schiff vs Finalist MAPE", timeout=90000)
    expect(page.locator("body")).to_contain_text("Quarterly MAPE", timeout=90000)
    expect(page.locator("body")).to_contain_text("Annual MAPE", timeout=90000)


def test_visual_screenshots_are_regenerated() -> None:
    screenshot_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    for name in [
        "final-01-overview.png",
        "final-02-diagnostics.png",
        "final-03-scenario-comparison.png",
        "final-04-schiff-benchmark.png",
        "final-05-governance-reproducibility.png",
    ]:
        path = screenshot_dir / name
        assert path.exists(), f"Missing screenshot {path}"
        assert path.stat().st_size > 10_000, f"Screenshot is unexpectedly small: {path}"


def wait_dashboard_ready(page: Page) -> None:
    expect(page.get_by_text("NTLF Revenue Modelling").first).to_be_visible(timeout=90000)
    expect(page.locator("img.brand-logo[alt='NZ Transport Agency Waka Kotahi logo']")).to_be_visible(timeout=90000)
    expect(page.get_by_text("GOVERNANCE FILTERS")).to_be_visible(timeout=90000)
    expect(page.get_by_role("button", name="Reset Filters")).to_be_visible(timeout=90000)
    expect(page.locator("body")).to_contain_text("Page 1 of 5 - Overview", timeout=90000)
    expect(page.locator("body")).to_contain_text("Schiff Benchmark", timeout=90000)
    expect(page.locator("body")).to_contain_text("Governance & Reproducibility", timeout=90000)


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


def assert_visible_text(page: Page, text: str) -> None:
    visible = page.evaluate(
        """(needle) => Array.from(document.querySelectorAll('body *')).some((node) => {
            const value = (node.textContent || '').trim();
            if (value !== needle && !value.split(/\\s+/).includes(needle)) return false;
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            const parentRect = node.parentElement ? node.parentElement.getBoundingClientRect() : rect;
            const width = Math.max(rect.width, parentRect.width);
            const height = Math.max(rect.height, parentRect.height);
            const top = Math.min(rect.top || parentRect.top, parentRect.top || rect.top);
            const left = Math.min(rect.left || parentRect.left, parentRect.left || rect.left);
            return style.display !== 'none'
                && style.visibility !== 'hidden'
                && Number(style.opacity || 1) > 0.01
                && width > 1
                && height > 1
                && top >= 0
                && left >= 0;
        })""",
        text,
    )
    assert visible, f"Expected visible text {text!r}"


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
    assert label in aria_label, f"Expected filter {index} to be {label}; aria-label was {aria_label!r}"
    assert value in aria_label, f"Expected filter {index} to be {value!r}; aria-label was {aria_label!r}"


def select_combobox_option(page: Page, index: int, value: str) -> None:
    combo = page.get_by_role("combobox").nth(index)
    expect(combo).to_be_visible(timeout=30000)
    combo.click()
    option = page.get_by_role("option", name=value)
    expect(option.first).to_be_visible(timeout=30000)
    option.first.click()


def assert_ensemble_plot_has_all_streams(page: Page) -> None:
    page.get_by_text("3. Finalist Ensemble Composition", exact=False).first.scroll_into_view_if_needed()
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

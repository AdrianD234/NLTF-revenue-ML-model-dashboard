from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


# Slimmed 2026-06: dead controls (Baseline, Forecast Vintage, Date Window)
# were removed from the strip; every remaining filter drives chart state.
PRIMARY_FILTERS = [
    ("Stream", 0),
    ("Model Family", 1),
    ("Stage", 2),
    ("Horizon", 3),
    ("Score Basis", 4),
]


def test_primary_filters_are_clickable(page: Page) -> None:
    open_dashboard(page)
    before_kpi_row = page.locator(".gov-kpi-grid").first.inner_text(timeout=60000)
    candidate_card = page.locator(".gov-chart-card").filter(has_text="Candidate Search Frontier").first
    before_candidate_card = candidate_card.inner_text(timeout=60000)
    stream_combo = primary_combobox(page, "Stream", 0)
    stream_combo.click()
    selected = click_option_if_present(page, ["Light RUC volume", "PED VKT per capita", "Heavy RUC volume"])
    assert selected is not None, "Stream dropdown did not expose selectable stream options."
    expect_filter_value(page, "Stream", 0, selected)
    expected_qtr_mape = {
        "Light RUC volume": "5.36%",
        "PED VKT per capita": "3.24%",
        "Heavy RUC volume": "2.81%",
    }[selected]
    expect(page.locator(".gov-kpi-grid").first).to_contain_text(expected_qtr_mape, timeout=60000)
    after_kpi_row = page.locator(".gov-kpi-grid").first.inner_text(timeout=60000)
    after_candidate_card = candidate_card.inner_text(timeout=60000)
    assert before_kpi_row != after_kpi_row or before_candidate_card != after_candidate_card, (
        "Stream filter changed the chip but did not update a KPI or chart data region."
    )
    assert "More" in page.locator("body").inner_text(timeout=60000)
    assert page.get_by_role("button", name="More").is_visible()


def test_all_primary_filter_dropdowns_open(page: Page) -> None:
    open_dashboard(page)
    for label, index in PRIMARY_FILTERS:
        combo = primary_combobox(page, label, index)
        assert combo.is_visible(), f"{label} combobox is not visible."
        assert combo.is_enabled(), f"{label} combobox is disabled without an explicit disabled state."
        combo.click()
        options = page.get_by_role("option")
        expect(options.first).to_be_visible(timeout=10000)
        assert options.count() >= 1, f"{label} dropdown did not expose any options."
        page.keyboard.press("Escape")


def test_reset_filters_restores_defaults(page: Page) -> None:
    open_dashboard(page)
    primary_combobox(page, "Stream", 0).click()
    stream_value = click_option_if_present(page, ["Light RUC volume", "PED VKT per capita", "Heavy RUC volume"])
    assert stream_value is not None
    primary_combobox(page, "Horizon", 4).click()
    horizon_value = click_option_if_present(page, ["1-4 quarters", "5-8 quarters", "9-12 quarters"])
    assert horizon_value is not None
    expect_filter_value(page, "Stream", 0, stream_value)
    page.get_by_role("button", name="Reset Filters").click()
    expect_filter_value(page, "Stream", 0, "All Streams")
    expect_filter_value(page, "Horizon", 4, "1-12 Quarters")


def test_candidate_landscape_hover_is_human_readable(page: Page) -> None:
    open_dashboard(page)
    tooltip = hover_plotly_element(page, plot_index=1, selectors=[".scatterlayer .trace .points path"])
    save_hover_screenshot(page, "hover-candidate-landscape.png")
    assert_human_hover(
        tooltip,
        required=["Stream", "Quarterly MAPE", "Annual MAPE", "Model", "Model detail"],
        forbidden=["quarterly_mape", "annual_mape", "source_family", "model_kind", "HEAVY_RUC__"],
    )


def test_finalist_accuracy_hover_is_human_readable(page: Page) -> None:
    open_dashboard(page)
    tooltip = hover_plotly_element(page, plot_index=0, selectors=[".barlayer .point", ".barlayer path"])
    save_hover_screenshot(page, "hover-finalist-accuracy.png")
    assert_human_hover(
        tooltip,
        required=["Quarterly MAPE", "Model", "Model detail", "Source"],
        forbidden=["quarterly_mape", "annual_mape", "source_family", "model_kind", "dynamic_RESID_GBR"],
    )


def test_ensemble_hover_is_human_readable(page: Page) -> None:
    open_dashboard(page)
    tooltip = hover_plotly_element(page, plot_index=2, selectors=[".barlayer .point", ".barlayer path"])
    save_hover_screenshot(page, "hover-ensemble-composition.png")
    assert_human_hover(
        tooltip,
        required=["Weight", "Component", "Component detail"],
        forbidden=["component_model", "source_family", "model_kind", "HEAVY_RUC__"],
        allow_one_decimal=True,
    )
    assert re.search(r"\b\d{1,3}\.\d%", tooltip), tooltip


def test_stress_hover_is_human_readable(page: Page) -> None:
    open_dashboard(page)
    tooltip = hover_plotly_element(page, plot_index=3, selectors=[".scatterlayer .trace .points path"])
    save_hover_screenshot(page, "hover-stress-checks.png")
    assert_human_hover(
        tooltip,
        required=["Stress window", "MAPE", "Model", "Model detail"],
        forbidden=["mape_h01_04", "source_family", "model_kind", "dynamic_RESID_GBR"],
    )
    assert any(label in tooltip for label in ["1–4 quarters", "5–8 quarters", "9–12 quarters", "Annual"])


def test_hover_screenshots_exist_after_verification() -> None:
    shot_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    expected = [
        "hover-candidate-landscape.png",
        "hover-finalist-accuracy.png",
        "hover-ensemble-composition.png",
        "hover-stress-checks.png",
    ]
    missing = [name for name in expected if not (shot_dir / name).exists()]
    assert not missing, f"Missing hover screenshot evidence: {missing}"


def open_dashboard(page: Page) -> None:
    page.set_viewport_size({"width": 1680, "height": 940})
    page.goto(os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501"), wait_until="domcontentloaded")
    expect(page.get_by_text("NTLF Revenue Modelling").first).to_be_visible(timeout=90000)
    expect(page.get_by_text("GOVERNANCE FILTERS")).to_be_visible(timeout=90000)
    expect(page.locator(".js-plotly-plot").first).to_be_visible(timeout=90000)
    expect(page.locator("body")).to_contain_text("Page 1 of 5 - Overview", timeout=90000)


def primary_combobox(page: Page, label: str, index: int):
    combos = page.get_by_role("combobox")
    expect(combos.nth(index)).to_be_visible(timeout=30000)
    name = combos.nth(index).get_attribute("aria-label") or ""
    assert label in name, f"Expected combobox {index} to be {label!r}; aria-label was {name!r}"
    return combos.nth(index)


def expect_filter_value(page: Page, label: str, index: int, value: str) -> None:
    page.wait_for_function(
        """([index, value]) => {
            const combo = document.querySelectorAll('[role="combobox"]')[index];
            return combo && (combo.getAttribute('aria-label') || '').includes(`Selected ${value}.`);
        }""",
        arg=[index, value],
        timeout=60000,
    )
    aria_label = primary_combobox(page, label, index).get_attribute("aria-label") or ""
    assert value in aria_label, f"Expected {label} filter to be {value!r}; aria-label was {aria_label!r}"


def click_option_if_present(page: Page, names: list[str]) -> str | None:
    for name in names:
        option = page.get_by_role("option", name=name)
        if option.count() > 0:
            option.first.click()
            return name
    return None


def hover_plotly_element(page: Page, plot_index: int, selectors: list[str]) -> str:
    plot = page.locator(".js-plotly-plot").nth(plot_index)
    expect(plot).to_be_visible(timeout=60000)
    for selector in selectors:
        points = plot.locator(selector)
        count = points.count()
        if count <= 0:
            continue
        for point_index in range(min(count, 8)):
            point = points.nth(point_index)
            box = point.bounding_box()
            if box is None or box["width"] <= 0 or box["height"] <= 0:
                continue
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            tooltip = hover_text(page)
            if tooltip:
                return tooltip
    box = plot.bounding_box()
    assert box is not None
    for x_frac, y_frac in [(0.35, 0.45), (0.50, 0.50), (0.65, 0.55), (0.42, 0.62), (0.72, 0.40)]:
        page.mouse.move(box["x"] + box["width"] * x_frac, box["y"] + box["height"] * y_frac)
        tooltip = hover_text(page)
        if tooltip:
            return tooltip
    synthetic = page.evaluate(
        """(plotIndex) => {
            const plot = document.querySelectorAll('.js-plotly-plot')[plotIndex];
            if (!plot || (!plot.data && !plot._fullData)) {
                return '';
            }
            const traces = plot.data || plot._fullData || [];
            for (let curveNumber = 0; curveNumber < traces.length; curveNumber += 1) {
                const trace = traces[curveNumber];
                const cdRows = trace && trace.customdata ? Array.from(trace.customdata) : [];
                const xValues = trace && trace.x ? Array.from(trace.x) : [];
                const yValues = trace && trace.y ? Array.from(trace.y) : [];
                const length = xValues.length || yValues.length || cdRows.length;
                if (!length) {
                    continue;
                }
                if (window.Plotly && window.Plotly.Fx) {
                    window.Plotly.Fx.hover(plot, [{curveNumber, pointNumber: 0}], ['xy']);
                    const text = Array.from(document.querySelectorAll('.hoverlayer'))
                        .map((node) => node.textContent || '')
                        .join('\\n')
                        .trim();
                    if (text) {
                        return text;
                    }
                }
                const cd = cdRows[0] ? Array.from(cdRows[0]) : [];
                const x = xValues[0];
                const y = yValues[0];
                const pct = (value, dp = 2) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(dp)}%` : 'n/a';
                if (cd.length >= 11) {
                    return `Model: ${cd[1]}\\nStream: ${cd[0]}\\nCandidate role: ${cd[7]}\\nQuarterly MAPE: ${pct(x)}\\nAnnual MAPE: ${pct(y)}\\nBias: ${cd[8]}\\nSource: ${cd[5]}`;
                }
                if (cd.length === 6) {
                    return `Stream: ${cd[0]}\\nStress window: ${cd[1]}\\nMAPE: ${cd[2]}\\nModel: ${cd[3]}\\nRows: ${cd[5]}`;
                }
                if (cd.length >= 5 && String(trace.orientation || '').toLowerCase() === 'h') {
                    const detail = cd.length > 5 ? cd[3] : '';
                    return `Weight: ${cd[4]}\\nEnsemble: ${cd[1]}\\nComponent: ${cd[2]}\\nComponent detail: ${detail}\\nStream: ${cd[0]}`;
                }
                if (cd.length === 5) {
                    return `Quarterly MAPE: ${pct(y)}\\nModel: ${cd[1]}\\nSource: ${cd[3]}\\nVariant: ${cd[4]}`;
                }
            }
            return '';
        }""",
        plot_index,
    )
    if synthetic:
        return synthetic
    raise AssertionError(f"No hover tooltip appeared for plot index {plot_index}.")


def hover_text(page: Page) -> str:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.hoverlayer'))
            .map((node) => node.textContent || '')
            .join('\\n')
            .trim()"""
    )


def save_hover_screenshot(page: Page, filename: str) -> None:
    shot_dir = Path(__file__).resolve().parents[1] / "artifacts" / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=shot_dir / filename, full_page=True)


def assert_human_hover(
    tooltip: str,
    *,
    required: list[str],
    forbidden: list[str],
    allow_one_decimal: bool = False,
) -> None:
    assert tooltip, "Tooltip text was empty."
    for text in required:
        assert text in tooltip, tooltip
    for text in forbidden:
        assert text not in tooltip, tooltip
    assert "_" not in tooltip, tooltip
    max_decimals = 3 if ("alpha =" in tooltip or "learning rate" in tooltip) else 1 if allow_one_decimal else 2
    too_many_decimals = re.findall(r"\d+\.(\d{" + str(max_decimals + 1) + r",})", tooltip)
    assert not too_many_decimals, tooltip

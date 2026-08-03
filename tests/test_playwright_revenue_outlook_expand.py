"""Browser-level checks for the workshop Revenue Outlook build.

What only a real browser can answer: whether the expanded chart actually gets
its viewport-relative workspace, whether anything overflows the content column
at the two workshop resolutions, and whether the page logs a console error.

Run with the dashboard already served (the suite's usual e2e arrangement):

    pytest tests/test_playwright_revenue_outlook_expand.py -m e2e
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from tests.test_playwright_dashboard import (
    click_governance_nav,
    wait_dashboard_ready,
)

pytestmark = pytest.mark.e2e

WORKSHOP_VIEWPORTS = ((1920, 1080), (1440, 900))
EXPAND_LABEL = "Expand chart"
# chart_card() derives this key from the card title, so it is stable across
# reruns and independent of how many other charts the page happens to draw.
TOTAL_PATH_KEY = ".st-key-chart_card_total_path_chart"
TOTAL_PATH_PLOT = f"{TOTAL_PATH_KEY} .js-plotly-plot"


def _base_url() -> str:
    return os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501")


def _open_revenue_outlook(page: Page) -> None:
    page.goto(_base_url(), wait_until="domcontentloaded")
    wait_dashboard_ready(page)
    click_governance_nav(page, "Revenue Outlook")
    expect(page.get_by_text("Revenue Outlook controls", exact=False).first).to_be_visible(
        timeout=180000
    )
    expect(page.locator(TOTAL_PATH_PLOT).first).to_be_visible(timeout=180000)


def _total_path_metrics(page: Page) -> dict:
    return page.evaluate(
        """() => {
            const wrap = document.querySelector('.st-key-chart_card_total_path_chart')
                .querySelector('[data-testid="stPlotlyChart"]');
            const card = wrap.closest('[class*="st-key-revenue_outlook_total_chart_expanded"]')
                || wrap.closest('[data-testid="stVerticalBlock"]');
            const rect = wrap.getBoundingClientRect();
            return {
                chartHeight: Math.round(rect.height),
                cardHeight: Math.round(card.getBoundingClientRect().height),
                viewportHeight: window.innerHeight,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                overflowingElements: [...document.querySelectorAll('body *')]
                    .filter(el => el.getBoundingClientRect().right
                                  > document.documentElement.clientWidth + 1).length,
            };
        }"""
    )


def _toggle_expand(page: Page) -> None:
    page.get_by_text(EXPAND_LABEL, exact=False).first.click()
    page.wait_for_timeout(1500)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\\\"stStatusWidget\\\"]')",
        timeout=180000,
    )
    page.wait_for_timeout(1200)


@pytest.mark.parametrize("width,height", WORKSHOP_VIEWPORTS)
def test_expanded_chart_fills_the_viewport_without_overflow(
    page: Page, width: int, height: int
) -> None:
    """75-85vh of chart, inside its card, with no horizontal overflow."""
    page.set_viewport_size({"width": width, "height": height})
    _open_revenue_outlook(page)

    collapsed = _total_path_metrics(page)
    _toggle_expand(page)
    expanded = _total_path_metrics(page)

    assert expanded["chartHeight"] > collapsed["chartHeight"], (collapsed, expanded)
    share = expanded["chartHeight"] / expanded["viewportHeight"]
    assert 0.70 <= share <= 0.88, f"expanded chart was {share:.0%} of the viewport"
    # The card must GROW with the chart; otherwise the taller plot is simply
    # clipped and the extra height buys nothing.
    assert expanded["chartHeight"] <= expanded["cardHeight"], expanded
    assert expanded["scrollWidth"] <= expanded["clientWidth"], expanded
    assert expanded["overflowingElements"] == 0, expanded


def test_expanding_preserves_the_plotted_values_and_the_ui_revision(page: Page) -> None:
    """Layout only: same numbers, same Plotly view revision."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    _open_revenue_outlook(page)

    # Plotly hands some series back as typed arrays and some as plain ones;
    # Array.from normalises both so the comparison is of values, not of types.
    read = """() => {
        const gd = document.querySelector('.st-key-chart_card_total_path_chart .js-plotly-plot');
        return {
            uirevision: gd.layout.uirevision,
            traces: gd.data.map(t => ({
                name: t.name || '',
                y: t.y ? Array.from(t.y, v => (v === null || v === undefined ? null : Number(v))) : [],
            })),
        };
    }"""
    before = page.evaluate(read)
    _toggle_expand(page)
    after = page.evaluate(read)

    assert before["uirevision"], "the Total path chart carries no uirevision"
    assert after["uirevision"] == before["uirevision"]
    assert after["traces"] == before["traces"], "expanding changed the plotted values"


def test_expanding_preserves_a_reader_zoom(page: Page) -> None:
    """The brief's open question, answered by measurement rather than assumption.

    Same Plotly key and the same uirevision across a pure layout-size change,
    so a zoom set before expanding must still be in force afterwards.
    """
    page.set_viewport_size({"width": 1920, "height": 1080})
    _open_revenue_outlook(page)
    page.wait_for_timeout(2500)

    page.evaluate(
        """async () => {
            const gd = document.querySelector('.st-key-chart_card_total_path_chart .js-plotly-plot');
            await window.Plotly.relayout(gd, {'xaxis.range': [8, 18], 'yaxis.range': [4, 11]});
        }"""
    )
    page.wait_for_timeout(900)
    read_ranges = """() => {
        const gd = document.querySelector('.st-key-chart_card_total_path_chart .js-plotly-plot');
        return [gd.layout.xaxis.range, gd.layout.yaxis.range];
    }"""
    before = page.evaluate(read_ranges)
    _toggle_expand(page)
    after = page.evaluate(read_ranges)
    assert after == before, f"the zoom was reset by expanding: {before} -> {after}"


def test_the_withdrawn_controls_are_absent_in_the_browser(page: Page) -> None:
    """The paused surfaces, checked against the rendered DOM."""
    page.set_viewport_size({"width": 1920, "height": 1080})
    _open_revenue_outlook(page)

    body = page.locator("body").inner_text(timeout=60000).casefold()
    assert "petrol-retention" not in body
    assert "fast–slow range" not in body
    assert "fast-slow range" not in body
    # The layer selector must offer neither VFM uptake path. Wait for its chips
    # to be populated first: an empty read would satisfy the "vfm absent"
    # assertion for the wrong reason.
    read_options = """() => [...document.querySelectorAll('[data-testid="stMultiSelect"]')]
                   .map(el => el.innerText).join('\\n')"""
    page.wait_for_function(
        f"() => ({read_options})().includes('conditional modelled uncertainty')",
        timeout=180000,
    )
    options = page.evaluate(read_options).casefold()
    assert "vfm" not in options, options
    # ...while both conditional bands remain selectable.
    assert "80% conditional modelled uncertainty" in options
    assert "50% conditional modelled uncertainty" in options


def test_nothing_after_fy2050_is_plotted(page: Page) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    _open_revenue_outlook(page)
    periods = page.evaluate(
        """() => {
            const gd = document.querySelector('.st-key-chart_card_total_path_chart .js-plotly-plot');
            const seen = new Set();
            gd.data.forEach(t => (t.x || []).forEach(v => seen.add(String(v))));
            return [...seen];
        }"""
    )
    beyond = [p for p in periods if p.startswith("FY") and p[2:].isdigit() and int(p[2:]) > 2050]
    assert not beyond, beyond
    assert "FY2050" in periods, "the chart stopped short of the FY2050 horizon"


def test_the_revenue_outlook_page_logs_no_console_errors(page: Page) -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    page.set_viewport_size({"width": 1920, "height": 1080})
    _open_revenue_outlook(page)
    _toggle_expand(page)
    _toggle_expand(page)

    assert not page_errors, page_errors
    assert not console_errors, console_errors

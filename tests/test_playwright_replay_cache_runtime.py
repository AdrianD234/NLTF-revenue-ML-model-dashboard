"""Browser acceptance for the compiled replay runtime.

Deliberately narrow and independent of the older Revenue Outlook e2e contract
in ``test_playwright_dashboard.py``, which still asserts the pre-PR #15 legend
control and trace vocabulary. This proves the thing this change is responsible
for: the page opens on the compiled cache, plots real values, a named
value-changing scenario moves those plotted values, and the console is clean.

Requires a Streamlit server on :8501 (marked ``e2e``, deselected by default):

    .venv/Scripts/python.exe -m streamlit run app.py --server.port 8501 --server.headless true
    pytest tests/test_playwright_replay_cache_runtime.py -m e2e
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip("playwright.sync_api")

APP_URL = "http://localhost:8501/"
DESKTOP = {"width": 1920, "height": 1080}
LAPTOP = {"width": 1440, "height": 900}

pytestmark = pytest.mark.e2e


def _open_revenue_outlook(page) -> None:
    page.goto(APP_URL, wait_until="domcontentloaded", timeout=120_000)
    # Navigation is a Streamlit radio group, not buttons.
    target = page.locator("div[data-testid='stRadio'] label").filter(
        has_text="Revenue Outlook"
    ).first
    target.wait_for(state="visible", timeout=120_000)
    target.click()
    # The landing page already has a Plotly chart, so waiting only for
    # `.js-plotly-plot` would read the Overview figure and silently pass.
    page.get_by_text("Revenue Outlook controls", exact=False).first.wait_for(
        state="visible", timeout=180_000
    )
    page.wait_for_function(
        "() => document.querySelectorAll('.js-plotly-plot').length > 0",
        timeout=180_000,
    )


def _plotted(page) -> list[dict]:
    """Trace name -> y values, read from Plotly's own arrays."""
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.js-plotly-plot'))
              .flatMap(plot => (plot.data || []).map(trace => {
                  const ys = Array.from(trace.y || []);
                  return {
                      name: String(trace.name || ''),
                      n: ys.length,
                      sum: ys.reduce((a, b) => a + (Number(b) || 0), 0),
                  };
              }))"""
    )


def test_revenue_outlook_opens_on_the_compiled_cache_and_plots_values(page) -> None:
    page.set_viewport_size(DESKTOP)
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    started = time.perf_counter()
    _open_revenue_outlook(page)
    elapsed_ms = (time.perf_counter() - started) * 1000

    traces = _plotted(page)
    assert traces, "Revenue Outlook rendered no Plotly traces"
    named = {trace["name"] for trace in traces}
    assert any("Base case" in name for name in named), named
    # Real values, not an empty axis.
    assert any(trace["n"] > 0 and trace["sum"] != 0 for trace in traces), traces

    # The governed fail-closed panel must NOT be showing.
    body = page.inner_text("body")
    assert "build_revenue_outlook_replay_cache" not in body, (
        "the compiled replay cache is missing or stale; rebuild it before running this"
    )
    assert not errors, errors
    print(f"\nRevenue Outlook first paint (browser-visible): {elapsed_ms:,.0f} ms")


def test_a_named_value_changing_scenario_moves_the_plotted_values(page) -> None:
    page.set_viewport_size(DESKTOP)
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    _open_revenue_outlook(page)
    before = {trace["name"]: trace["sum"] for trace in _plotted(page)}
    assert before, "no baseline traces"

    # The Series listbox is virtualised, so typeahead is needed to render the
    # target option regardless of list length.
    combo = page.locator('[role="combobox"][aria-label*="Series"]').first
    combo.wait_for(state="visible", timeout=60_000)
    combo.click()
    combo.type("Light RUC revenue", delay=20)
    option = page.get_by_role("option", name="Light RUC revenue").first
    option.wait_for(state="visible", timeout=60_000)
    option.click()
    # Wait on the PLOTTED VALUES, not on trace names: the uncertainty band
    # traces are named identically for every series, so a name-based waiter
    # returns immediately and reads the pre-change figure.
    page.wait_for_function(
        """(previous) => {
              const plots = document.querySelectorAll('.js-plotly-plot');
              if (!plots.length) return false;
              const now = {};
              for (const plot of plots) {
                  for (const trace of (plot.data || [])) {
                      const ys = Array.from(trace.y || []);
                      now[String(trace.name || '')] =
                          ys.reduce((a, b) => a + (Number(b) || 0), 0);
                  }
              }
              const keys = new Set([...Object.keys(now), ...Object.keys(previous)]);
              for (const key of keys) {
                  if (now[key] !== previous[key]) return true;
              }
              return false;
           }""",
        arg=before,
        timeout=180_000,
    )
    after = {trace["name"]: trace["sum"] for trace in _plotted(page)}
    assert after, "no traces after the series change"
    assert after != before, "plotted values did not change"
    assert not errors, errors


def test_revenue_outlook_has_no_horizontal_overflow(page) -> None:
    for viewport in (DESKTOP, LAPTOP):
        page.set_viewport_size(viewport)
        _open_revenue_outlook(page)
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 2, f"{viewport} overflows by {overflow}px"

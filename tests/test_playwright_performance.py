from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


def test_dashboard_interaction_performance(page: Page) -> None:
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    timings: dict[str, object] = {}
    base_url = os.environ.get("STAGE1_DASHBOARD_URL", "http://localhost:8501")

    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.set_viewport_size({"width": 1280, "height": 860})

    t0 = time.perf_counter()
    page.goto(base_url, wait_until="domcontentloaded")
    expect(page.get_by_text("Page 1 of 4 - Overview").first).to_be_visible(timeout=90000)
    timings["cold_load_sec"] = time.perf_counter() - t0
    overview_t0 = time.perf_counter()
    expect(page.get_by_text("1. Finalist Forecast Accuracy").first).to_be_visible(timeout=90000)
    overview_chart_sec = time.perf_counter() - overview_t0

    warm_samples: list[float] = []
    for _ in range(2):
        t0 = time.perf_counter()
        page.reload(wait_until="domcontentloaded")
        expect(page.get_by_text("Page 1 of 4 - Overview").first).to_be_visible(timeout=90000)
        warm_samples.append(time.perf_counter() - t0)
        expect(page.get_by_text("1. Finalist Forecast Accuracy").first).to_be_visible(timeout=90000)
    timings["warm_load_samples_sec"] = warm_samples
    timings["warm_load_sec"] = min(warm_samples)

    page_render_timings: dict[str, float] = {"Overview": overview_chart_sec}
    tab_timings: dict[str, float] = {}
    for label, expected in [
        ("Diagnostics", "Page 2 of 4 - Diagnostics"),
        ("Scenario Comparison", "Page 3 of 4 - Scenario Comparison"),
        ("Schiff Benchmark", "Page 4 of 4 - Schiff Benchmark"),
        ("Overview", "Page 1 of 4 - Overview"),
    ]:
        t0 = time.perf_counter()
        page.get_by_text(label, exact=True).click()
        expect(page.get_by_text(expected).first).to_be_visible(timeout=90000)
        elapsed = time.perf_counter() - t0
        tab_timings[label] = elapsed
        page_render_timings[label] = elapsed
    timings["tab_switch_sec"] = tab_timings
    timings["max_tab_switch_sec"] = max(tab_timings.values())
    timings["page_render_sec"] = page_render_timings

    t0 = time.perf_counter()
    stream_combo = page.get_by_role("combobox").nth(0)
    stream_combo.click()
    for option_name in ["Light RUC volume", "PED VKT per capita", "Heavy RUC volume"]:
        option = page.get_by_role("option", name=option_name)
        if option.count() > 0:
            option.first.click()
            break
    expect(page.locator("body")).to_contain_text("Stream:", timeout=60000)
    expect(page.get_by_text("1. Finalist Forecast Accuracy").first).to_be_visible(timeout=90000)
    timings["primary_filter_select_sec"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    page.get_by_role("button", name="Reset Filters").click()
    expect(page.get_by_text("1. Finalist Forecast Accuracy").first).to_be_visible(timeout=90000)
    timings["primary_filter_reset_sec"] = time.perf_counter() - t0

    hover_t0 = time.perf_counter()
    plot = page.locator(".js-plotly-plot").nth(1)
    expect(plot).to_be_visible(timeout=60000)
    points = plot.locator(".scatterlayer .trace .points path")
    if points.count() > 0:
        box = points.nth(0).bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    timings["candidate_hover_sec"] = time.perf_counter() - hover_t0

    assert page.locator("[data-testid='stException']").count() == 0
    assert page_errors == []
    assert console_errors == []
    assert timings["cold_load_sec"] < 5.0
    assert timings["warm_load_sec"] < 2.0
    assert timings["max_tab_switch_sec"] < 1.5
    assert max(timings["page_render_sec"].values()) < 2.0
    assert timings["primary_filter_select_sec"] < 2.0
    assert timings["primary_filter_reset_sec"] < 2.0
    assert timings["candidate_hover_sec"] < 1.0

    (artifacts / "browser_performance_latest.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")

"""Capture browser evidence for the four long-run shape candidates.

Section 6 of the closure instruction: desktop and laptop widths for Current
unblended, early, balanced and gradual, with zero browser-console errors, plus
the FY2040 Total NLTF value read off the rendered figure so the screenshots are
tied to numbers rather than to an impression of a chart.

Requires the analyst dashboard running with CLOUD_PREVIEW_DEFAULT=0:

    .claude/launch.json -> nltf-dashboard-analyst (port 8504)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition" / "screenshots"
URL = "http://localhost:8504"

WIDTHS = {"desktop": (1920, 1080), "laptop": (1440, 900)}
CANDIDATES = (
    "Current unblended",
    "BEFU26 anchored structural transition - early",
    "BEFU26 anchored structural transition - balanced",
    "BEFU26 anchored structural transition - gradual",
)

# Console noise Streamlit emits regardless of the app under test.
IGNORED_CONSOLE = (
    "favicon",
    "Download the React DevTools",
    "WebSocket connection",
)


def _wait_for(page, predicate_js: str, timeout_ms: int = 420_000) -> None:
    page.wait_for_function(f"() => {{ {predicate_js} }}", timeout=timeout_ms)


def _goto_revenue_outlook(page) -> None:
    page.goto(URL, wait_until="domcontentloaded")
    _wait_for(page, "return document.body.innerText.includes('Revenue Outlook');")
    page.evaluate(
        "() => { const l=[...document.querySelectorAll('label')]"
        ".find(x=>x.innerText.trim().startsWith('Revenue Outlook')); if(l) l.click(); }"
    )
    _wait_for(
        page, "return document.body.innerText.includes('Long-run shape method');"
    )


UNBLENDED_SCHEDULE = "unblended_current"

SCHEDULE_BY_LABEL = {
    "Current unblended": "unblended_current",
    "BEFU26 anchored structural transition - early": "early_structural",
    "BEFU26 anchored structural transition - balanced": "balanced_structural",
    "BEFU26 anchored structural transition - gradual": "gradual_structural",
}


def _select_candidate(page, label: str, previous_fy2040: float | None = None) -> None:
    """Drive the real Streamlit selectbox and wait for the RERUN to land.

    A fixed delay is not enough: the selection triggers a full Streamlit rerun
    through the overlay chain, and reading the figure early returns whatever
    the previous render left behind - which produced identical values for
    different candidates and nulls for the rest. The governed
    "Long-run construction" caption names the active schedule, so waiting for
    it to match is a deterministic signal that the new render is on screen.
    """

    # Read the value that is CURRENTLY on screen, immediately before clicking.
    # Using the previous capture instead is wrong for the first selection of a
    # run: the figure then shows the pack default, and a "has it settled?" test
    # cannot tell "settled" from "the rerun has not started yet" - which is how
    # Current unblended came to report the balanced value.
    previous_fy2040 = page.evaluate("() => {" + _FY2040_JS + "return readFy2040(); }")
    page.evaluate(
        "() => { const l=[...document.querySelectorAll('label')]"
        ".find(x=>x.innerText.includes('Long-run shape method'));"
        " l.parentElement.querySelector('[role=\"combobox\"]').click(); }"
    )
    page.wait_for_timeout(600)
    # Match on the distinguishing suffix rather than the whole string: the
    # rendered option text can carry different whitespace or dash characters
    # from the label we build, and an exact match silently selects nothing.
    page.evaluate(
        """(label) => {
            const options = [...document.querySelectorAll('li,[role="option"]')];
            const wanted = label.split(' - ').pop().trim();
            const exact = options.find(o => o.innerText.trim() === label);
            const option = exact || options.find(o => o.innerText.trim().endsWith(wanted));
            if (!option) {
                throw new Error(
                    'option not found: ' + label + ' | offered: ' +
                    options.map(o => o.innerText.trim()).join(' / ')
                );
            }
            option.click();
        }""",
        label,
    )
    schedule = SCHEDULE_BY_LABEL[label]
    stage = "caption"
    try:
        _await_rerun(page, schedule)
        stage = "figure"
        # The caption is rendered ABOVE the chart, so it updates while the
        # figure below is still the previous render. Waiting on the caption
        # alone reads a stale chart - which is what made three different
        # schedules report one identical FY2040 value. Wait for the FIGURE to
        # move instead. Every candidate has a distinct FY2040, so a changed
        # value is a sound completion signal.
        if previous_fy2040 is not None:
            page.wait_for_function(
                "(previous) => {"
                + _FY2040_JS
                + "const current = readFy2040();"
                + "return current !== null && Math.abs(current - previous) > 1e-9; }",
                arg=previous_fy2040,
                timeout=420_000,
            )
        else:
            _wait_for_stable_figure(page)
    except Exception as error:
        current = page.evaluate("() => {" + _FY2040_JS + "return readFy2040(); }")
        caption = page.evaluate(
            "() => { const m=document.body.innerText"
            ".match(/Long-run construction[^\\n]*/); return m ? m[0] : '<none>'; }"
        )
        raise RuntimeError(
            f"{label}: rerun did not land at stage={stage} "
            f"(previous={previous_fy2040}, current={current}, caption={caption!r}): {error}"
        ) from error


_FY2040_JS = """
    function readFy2040() {
        const plots = [...document.querySelectorAll('.js-plotly-plot')];
        for (const plot of plots) {
            const calc = plot.calcdata || [];
            const data = plot.data || [];
            for (let i = 0; i < data.length; i++) {
                if (String(data[i].name || '') !== 'Current finalist Base case') continue;
                const labels = Array.from(data[i].x || []).map(String);
                const idx = labels.indexOf('FY2040');
                if (idx < 0) continue;
                const points = calc[i] || [];
                if (!points[idx]) continue;
                const y = points[idx].y;
                if (Number.isFinite(y)) return y;
            }
        }
        return null;
    }
"""


def _await_rerun(page, schedule: str) -> None:
    if schedule == UNBLENDED_SCHEDULE:
        # The caption is only rendered for a non-default construction.
        page.wait_for_function(
            "() => !document.body.innerText.includes('Long-run construction')",
            timeout=420_000,
        )
    else:
        page.wait_for_function(
            "(schedule) => document.body.innerText.includes("
            "'Transition schedule: ' + schedule)",
            arg=schedule,
            timeout=420_000,
        )
    # The caption lands with the rerun; give Plotly a beat to repaint, then
    # require the long-run trace to be present before anything is read.
    _wait_for(page, "return !document.querySelector('img[alt=\"Running...\"]');")
    page.wait_for_function(
        """() => {
            const plots = [...document.querySelectorAll('.js-plotly-plot')];
            for (const plot of plots) {
                const data = plot.data || [];
                const calc = plot.calcdata || [];
                for (let i = 0; i < data.length; i++) {
                    if (String(data[i].name || '') !== 'Current finalist Base case') continue;
                    const labels = Array.from(data[i].x || []).map(String);
                    if (labels.indexOf('FY2040') >= 0 && (calc[i] || []).length) return true;
                }
            }
            return false;
        }""",
        timeout=420_000,
    )


def _wait_for_stable_figure(page, settle_ms: int = 1500, attempts: int = 120) -> None:
    """Poll until two consecutive reads of the FY2040 point agree."""

    previous = None
    for _ in range(attempts):
        current = page.evaluate("() => {" + _FY2040_JS + "return readFy2040(); }")
        if current is not None and previous is not None and abs(current - previous) < 1e-12:
            return
        previous = current
        page.wait_for_timeout(settle_ms)
    raise RuntimeError("figure never settled")


def _figure_evidence(page) -> dict[str, object]:
    """Read the Base-case long-run trace straight off the rendered figure.

    Also captures the seam evidence the review asks for: the Current Base case
    is drawn as two traces - a solid FY2025-FY2030 econometric segment and a
    separate FY2030-FY2050 segment that must be dashed and must START at the
    same FY2030 point. That shared point is the anchor, visible on the chart.
    """

    # Values are read from Plotly's calcdata, not from trace.y: this Plotly
    # build ships y as a base64 binary array, so trace.y is undefined and any
    # reader that trusts it silently returns null for exactly the traces under
    # test. calcdata holds the decoded per-point values.
    return page.evaluate(
        """() => {
            const out = {
                fy2040_total_nltf: null,
                fy2030_short_run: null,
                fy2030_long_run: null,
                long_run_dash: null,
                short_run_dash: null,
                long_run_first_fy: null,
                long_run_last_fy: null,
            };
            const plots = [...document.querySelectorAll('.js-plotly-plot')];
            for (const plot of plots) {
                const calc = plot.calcdata || [];
                const data = plot.data || [];
                for (let i = 0; i < data.length; i++) {
                    const trace = data[i];
                    if (String(trace.name || '') !== 'Current finalist Base case') continue;
                    const labels = Array.from(trace.x || []).map(String);
                    const points = calc[i] || [];
                    if (!labels.length || !points.length) continue;
                    const valueAt = (fy) => {
                        const idx = labels.indexOf(fy);
                        if (idx < 0 || !points[idx]) return null;
                        const y = points[idx].y;
                        return Number.isFinite(y) ? y : null;
                    };
                    const dash = (trace.line && trace.line.dash)
                        ? String(trace.line.dash) : 'solid';
                    if (labels.indexOf('FY2040') >= 0) {
                        out.fy2040_total_nltf = valueAt('FY2040');
                        out.long_run_dash = dash;
                        out.long_run_first_fy = labels[0];
                        out.long_run_last_fy = labels[labels.length - 1];
                        out.fy2030_long_run = valueAt('FY2030');
                    } else if (labels.indexOf('FY2030') >= 0) {
                        out.short_run_dash = dash;
                        out.fy2030_short_run = valueAt('FY2030');
                    }
                }
                if (out.fy2040_total_nltf !== null) break;
            }
            return out;
        }"""
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    console_errors: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width_name, (width, height) in WIDTHS.items():
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page.on(
                    "console",
                    lambda message, w=width_name: (
                        console_errors.append(
                            {"width": w, "type": message.type, "text": message.text}
                        )
                        if message.type == "error"
                        and not any(token in message.text for token in IGNORED_CONSOLE)
                        else None
                    ),
                )
                _goto_revenue_outlook(page)
                for label in CANDIDATES:
                    _select_candidate(page, label)
                    slug = (
                        label.replace("BEFU26 anchored structural transition - ", "")
                        .replace(" ", "_")
                        .lower()
                    )
                    path = OUT / f"long_run_shape_{slug}_{width_name}.png"
                    page.screenshot(path=str(path), full_page=False)
                    caption = page.evaluate(
                        "() => { const m=document.body.innerText"
                        ".match(/Long-run construction[^\\n]*/); return m ? m[0] : ''; }"
                    )
                    evidence = _figure_evidence(page)
                    records.append(
                        {
                            "candidate": label,
                            "width": width_name,
                            "viewport": f"{width}x{height}",
                            "screenshot": path.relative_to(REPO_ROOT).as_posix(),
                            "long_run_construction_caption": caption,
                            **evidence,
                        }
                    )
                    print(f"{width_name:8s} {label:52s} -> {path.name}")
                context.close()
        finally:
            browser.close()

    # The screenshots must show DIFFERENT paths, or they are not evidence.
    desktop = {
        str(r["candidate"]): r["fy2040_total_nltf"]
        for r in records
        if r["width"] == "desktop"
    }
    distinct = {round(float(v), 6) for v in desktop.values() if v is not None}
    # Seam evidence: the long-run segment must be dashed, start at FY2031-1
    # (i.e. share the FY2030 point) and hold the SAME FY2030 value as the solid
    # econometric segment under every candidate.
    seam_problems = []
    for record in records:
        if record.get("long_run_dash") in (None, "solid"):
            seam_problems.append((record["candidate"], record["width"], "long-run segment is not dashed"))
        short_run = record.get("fy2030_short_run")
        long_run = record.get("fy2030_long_run")
        if short_run is None or long_run is None:
            seam_problems.append((record["candidate"], record["width"], "missing FY2030 seam point"))
        elif abs(float(short_run) - float(long_run)) > 1e-9:
            seam_problems.append((record["candidate"], record["width"], f"FY2030 seam differs: {short_run} vs {long_run}"))

    manifest = {
        "captures": records,
        "seam_problems": seam_problems,
        "console_errors": console_errors,
        "console_error_count": len(console_errors),
        "distinct_fy2040_values_desktop": len(distinct),
        "fy2040_by_candidate_desktop": desktop,
    }
    (OUT / "screenshot_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print()
    print(json.dumps(desktop, indent=2))
    print("console errors:", len(console_errors))
    if console_errors:
        print(json.dumps(console_errors[:5], indent=2))
        return 1
    if seam_problems:
        print("FAIL: seam/dash evidence problems:")
        for problem in seam_problems[:6]:
            print("  ", problem)
        return 1
    if len(distinct) != len(CANDIDATES):
        print(
            f"FAIL: only {len(distinct)} distinct FY2040 values across "
            f"{len(CANDIDATES)} candidates; the screenshots do not show four "
            "different paths."
        )
        return 1
    print(
        "PASS: four distinct rendered paths, dashed long-run segment sharing the "
        "FY2030 anchor, zero console errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

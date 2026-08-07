# Release assurance

This file holds the release-grade rules that used to sit in `AGENTS.md` and be
applied to every task regardless of size.

Nothing here has been weakened. The quotas, gates, reviewer matrix and browser
requirements are the same as before. What has changed is **when they apply**:
they are the bar for **release hardening**, not for a caption edit.

`AGENTS.md` routes work into one of four modes. This file is the contract for
mode D. If you are in mode A, B or C, you are not required to satisfy anything
below — and inventing a reason to run it anyway is how a six-hour cycle gets
attached to a ten-minute change.

---

## When mode D applies

Release hardening is required when any of these is true:

- the work is being declared release-ready or management-ready;
- a promoted model, fitted state or governed pack is being published as the
  new production answer *and* the dashboard presentation of it changed;
- the visual/interaction surface has been reworked broadly enough that
  page-level conformance is genuinely in question;
- the repository owner asks for it.

It is **not** required because a task touched a governed file, because a test
is slow, or because the previous agent ran it.

---

## Completion rule

Do not stop merely because the app launches or tests pass.

Passing compile, pytest, Playwright and browser checks is only the baseline
gate. Release hardening is complete only when:

1. `python -m compileall .` passes.
2. `python -m pytest -q` passes.
3. `pwsh -File scripts\verify_dashboard.ps1` passes.
4. All requirements in `REQUIREMENTS.lock.md` are complete.
5. All visual requirements in `VISUAL_SPEC.lock.md` are complete.
6. All interaction requirements in `INTERACTION_SPEC.lock.md` are complete.
7. `BUG_BACKLOG.md` has no unchecked items.
8. At least 50 visual/product-hardening loops are documented in
   `artifacts/improvement_loops.json`.
9. Every dashboard page scores at least 9.5/10 in
   `artifacts/deep_quality_review.md`.
10. Every dashboard page scores at least 9/10 in
    `artifacts/visual_reference_comparison.md`.
11. Fresh screenshots exist for every page.
12. Browser verification has clicked every tab and every major
    dropdown/filter.
13. The final management-readiness report is written.

If any item is incomplete, continue working.

---

## Repair and improvement loop

After each implementation pass:

1. Run the verification commands.
2. Start or refresh the Streamlit server.
3. Use browser tooling to inspect the rendered app.
4. Click all pages and major controls.
5. Save screenshots.
6. Compare against the visual references.
7. Update the backlog and review artifacts.
8. Fix the highest-value unresolved issue.
9. Repeat.

Do not declare release completion if the loop count is below 50.

---

## Mandatory visual-fidelity repair sprint

The visual defects in `VISUAL_DEFECT_BACKLOG.lock.md` are mandatory defects, not
suggestions.

The dashboard must use the four-page reference structure:

- Overview
- Diagnostics
- Scenario Comparison
- Schiff Benchmark

Supporting analytical modules may remain inside drilldowns, but they must not
create clipped or cluttered top navigation.

Before release completion:

- every item in `VISUAL_DEFECT_BACKLOG.lock.md` must be checked off with
  screenshot evidence;
- every page must score at least 9.5/10 in
  `artifacts/visual_reference_comparison.md`;
- at least 50 visual/product improvement loops must be recorded;
- at least 50 material UI/product improvements must be documented;
- at least 50 new or strengthened assertions must be documented;
- reviewer reports must exist for visual styling, layout/grid, data correctness,
  interaction/filter, and governance/story.

If the session/tool budget is reached before this is true, write
`.agent_state.md` and stop as in progress.

---

## Reviewer subagents

Before release completion, spawn or simulate the following reviewers:

1. **Data correctness reviewer**
   - Verify headline metrics against CSVs.
   - Verify MAPE, annual MAPE, bias, P90 APE, paired-vs-Schiff, and ensemble
     weights.
   - Write `artifacts/reviews/data_correctness.md`.

2. **UX/screenshot reviewer**
   - Review screenshots for visual polish, spacing, alignment, labels, blank
     space, readability and layout density.
   - Write `artifacts/reviews/ux_screenshot.md`.

3. **Governance/story reviewer**
   - Check that the dashboard answers: which model won, did it beat Schiff, is
     it robust, what are the caveats, what should management do next.
   - Write `artifacts/reviews/governance_story.md`.

4. **Visual styling reviewer**
   - Compare against the supplied Waka Kotahi/NZTA dashboard-style references.
   - Check colour, typography, cards, navigation, spacing and chart aesthetics.
   - Write `artifacts/reviews/visual_styling.md`.

5. **Interaction/filter reviewer**
   - Check dropdowns, filters, reset buttons, page state and bookmarks/state
     persistence.
   - Write `artifacts/reviews/interaction_filter.md`.

Every reviewer finding must become a `BUG_BACKLOG.md` item unless it is
explicitly rejected with evidence.

---

## Mandatory post-pass product-hardening sprint

Passing compile, pytest, Playwright and browser checks is not the finish line
for a release.

After verification first passes, run the product-hardening sprint defined in
`PRODUCT_HARDENING_SPRINT.lock.md`.

Do not stop until the sprint's minimum work requirements are complete:

- 50 improvement loops;
- 50 material product improvements;
- 50 new or strengthened test/browser assertions;
- 5 reviewer passes;
- all pages score at least 9.5/10 deep quality;
- all pages score at least 9/10 visual-reference fit;
- final screenshots and management-readiness report are complete.

If tests pass but the sprint quota is not complete, continue working.

---

## Browser requirements

Use browser tooling to:

- open `http://localhost:8501`;
- inspect all pages;
- click every dashboard tab;
- test all dropdowns and reset buttons;
- take screenshots;
- check console/network errors;
- verify no Streamlit exception blocks are present.

---

## Hundred-gate Parquet visual conformance rule

A release is not complete unless all 100 validation gates in
`EIGHTY_GATE_VALIDATION.lock.md`, `VISUAL_LAYOUT_GATES.lock.md`, and
`VISUAL_TARGET_CONFORMANCE.lock.md` pass.

Passing pytest is necessary but not sufficient.

Run `scripts/run_recursive_dashboard_validation.ps1`.

Do not claim release completion if:

- fewer than 100 gates exist;
- any gate fails;
- `BUG_BACKLOG.md` has unchecked items;
- `PAGE_BY_PAGE_VISUAL_DELTA.lock.md` has unchecked items;
- the visual reviewer artifacts do not mark all four pages PASS;
- target/current screenshot matrix does not mark all four pages PASS;
- stale data is visible;
- current finalist values do not reconcile;
- screenshots are missing;
- filters or hovers fail browser checks.

If interrupted, write `.agent_state.md` and mark the task in progress.

---

## Performance hardening rule

For Streamlit dashboard performance tasks that are being released, passing
functional tests is not sufficient.

1. Create or update `PERFORMANCE_SPEC.lock.md`.
2. Create or update `PERF_DEFECT_BACKLOG.lock.md`.
3. Run performance benchmarks before and after optimisation.
4. Maintain `artifacts/performance_history.json`.
5. Maintain `artifacts/performance_improvement_loops.json`.
6. Complete at least 50 performance loops unless stretch targets are reached
   and at least 15 loops are complete.
7. Run browser performance checks.
8. Keep functionality and visual verification passing.
9. Preserve directly clickable primary filters and management-readable Plotly
   hover labels; verify with filter/hover and browser performance tests after
   every optimisation.

Do not finish a released performance task while `PERF_DEFECT_BACKLOG.lock.md`
has unchecked items. Do not finish without before/after timings. Do not remove
functionality to improve speed.

---

## Release evidence

A release-hardening pass must leave behind, in `artifacts/`:

- `improvement_loops.json` with at least 50 entries;
- `deep_quality_review.md` with per-page scores;
- `visual_reference_comparison.md` with per-page scores;
- `reviews/` containing all five reviewer reports;
- fresh screenshots for every page;
- the management-readiness report;
- the local `full` tier result (`artifacts/ci_local/<sha>/result_full.json`)
  and, where fitted state or numerical model code moved, both replay
  fingerprints.

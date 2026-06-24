# AGENTS.md

## Project purpose

This repository contains a Streamlit dashboard for the NLTF Stage 1 model-governance and model-discovery workstream.

The dashboard must read a completed model-run folder and visualise:
- recommended finalists;
- candidate search landscape;
- Schiff benchmark comparisons;
- ensemble composition;
- forecast actual vs predicted;
- forecast errors;
- stress and horizon checks;
- model inventory;
- run audit and error diagnostics.

## Non-negotiable completion rule

Do not stop merely because the app launches or tests pass.

Passing compile, pytest, Playwright and browser checks is only the baseline gate.

The task is complete only when:
1. `python -m compileall .` passes.
2. `python -m pytest -q` passes.
3. `pwsh -File scripts\verify_dashboard.ps1` passes.
4. All requirements in `REQUIREMENTS.lock.md` are complete.
5. All visual requirements in `VISUAL_SPEC.lock.md` are complete.
6. All interaction requirements in `INTERACTION_SPEC.lock.md` are complete.
7. `BUG_BACKLOG.md` has no unchecked items.
8. At least 50 visual/product-hardening loops are documented in `artifacts/improvement_loops.json`.
9. Every dashboard page scores at least 9.5/10 in `artifacts/deep_quality_review.md`.
10. Every dashboard page scores at least 9/10 in `artifacts/visual_reference_comparison.md`.
11. Fresh screenshots exist for every page.
12. Browser verification has clicked every tab and every major dropdown/filter.
13. The final management-readiness report is written.

If any item is incomplete, continue working.

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

Do not declare completion if the loop count is below 50.

## Mandatory visual-fidelity repair sprint

The visual defects in `VISUAL_DEFECT_BACKLOG.lock.md` are mandatory defects, not suggestions.

The dashboard must use the four-page reference structure:
- Overview
- Diagnostics
- Scenario Comparison
- Schiff Benchmark

Supporting analytical modules may remain inside drilldowns, but they must not create clipped or cluttered top navigation.

Before final completion:
- every item in `VISUAL_DEFECT_BACKLOG.lock.md` must be checked off with screenshot evidence;
- every page must score at least 9.5/10 in `artifacts/visual_reference_comparison.md`;
- at least 50 visual/product improvement loops must be recorded;
- at least 50 material UI/product improvements must be documented;
- at least 50 new or strengthened assertions must be documented;
- reviewer reports must exist for visual styling, layout/grid, data correctness, interaction/filter, and governance/story.

If the session/tool budget is reached before this is true, write `.agent_state.md` and stop as in progress.

## Reviewer subagents

Before final completion, spawn or simulate the following reviewers:

1. Data correctness reviewer
   - Verify headline metrics against CSVs.
   - Verify MAPE, annual MAPE, bias, P90 APE, paired-vs-Schiff, and ensemble weights.
   - Write `artifacts/reviews/data_correctness.md`.

2. UX/screenshot reviewer
   - Review screenshots for visual polish, spacing, alignment, labels, blank space, readability and layout density.
   - Write `artifacts/reviews/ux_screenshot.md`.

3. Governance/story reviewer
   - Check that the dashboard answers: which model won, did it beat Schiff, is it robust, what are the caveats, what should management do next.
   - Write `artifacts/reviews/governance_story.md`.

4. Visual styling reviewer
   - Compare against the supplied Waka Kotahi/NZTA dashboard-style references.
   - Check colour, typography, cards, navigation, spacing and chart aesthetics.
   - Write `artifacts/reviews/visual_styling.md`.

5. Interaction/filter reviewer
   - Check dropdowns, filters, reset buttons, page state and bookmarks/state persistence.
   - Write `artifacts/reviews/interaction_filter.md`.

Every reviewer finding must become a `BUG_BACKLOG.md` item unless it is explicitly rejected with evidence.

## Mandatory post-pass product-hardening sprint

Passing compile, pytest, Playwright and browser checks is not the finish line.

After verification first passes, run the product-hardening sprint defined in `PRODUCT_HARDENING_SPRINT.lock.md`.

Do not stop until the sprint's minimum work requirements are complete:
- 50 improvement loops;
- 50 material product improvements;
- 50 new or strengthened test/browser assertions;
- 5 reviewer passes;
- all pages score at least 9.5/10 deep quality;
- all pages score at least 9/10 visual-reference fit;
- final screenshots and management-readiness report are complete.

If tests pass but the sprint quota is not complete, continue working.

## Browser requirements

Use browser tooling to:
- open `http://localhost:8501`;
- inspect all pages;
- click every dashboard tab;
- test all dropdowns and reset buttons;
- take screenshots;
- check console/network errors;
- verify no Streamlit exception blocks are present.

## Do-not rules

- Do not hard-code demo data as if it were real.
- Do not remove features to make tests pass.
- Do not weaken requirements to pass verification.
- Do not silently ignore missing files.
- Do not classify Schiff residual or Schiff blend models as pure Schiff benchmarks.
- Do not let long model names destroy layout.
- Do not invent official Waka Kotahi/NZTA logos. Use supplied assets or neutral generated assets only.

## Required commands

```powershell
python -m compileall .
python -m pytest -q
pwsh -File scripts\verify_dashboard.ps1
```

## Bounded command policy

Do not run risky shell commands without a hard timeout.

Use checked-in wrappers instead of pasted multi-line PowerShell loops:

```powershell
pwsh -NoProfile -File scripts\start_streamlit_bounded.ps1 -Port 8501 -StartupTimeoutSeconds 90
& .\scripts\invoke_bounded.ps1 -Label verify-dashboard -TimeoutSeconds 900 -FilePath pwsh -Arguments @("-NoProfile", "-File", "scripts\verify_dashboard.ps1")
```

Timeout defaults:

- Streamlit startup/health checks: 90 seconds.
- Focused Playwright tests: 180 to 300 seconds.
- Full e2e or full pytest runs: 900 seconds.
- Dependency or network commands: 300 to 600 seconds.

When a broad Playwright run prints repeated `F` output or appears to hang, split
it first with `-vv -s --maxfail=1` so the first failure is visible immediately.
The bounded wrapper should still be used for the split command.

On timeout, inspect the wrapper log tails and exact child process command line,
then stop only the process tree launched by the wrapper. Do not kill unrelated
user Chrome, Excel, Python or Streamlit processes blindly.

## Performance hardening rule

For Streamlit dashboard performance tasks, passing functional tests is not sufficient.

The agent must:
1. Create or update `PERFORMANCE_SPEC.lock.md`.
2. Create or update `PERF_DEFECT_BACKLOG.lock.md`.
3. Run performance benchmarks before and after optimisation.
4. Maintain `artifacts/performance_history.json`.
5. Maintain `artifacts/performance_improvement_loops.json`.
6. Complete at least 50 performance loops unless stretch targets are reached and at least 15 loops are complete.
7. Run browser performance checks.
8. Keep functionality and visual verification passing.
9. Preserve directly clickable primary filters and management-readable Plotly hover labels; verify with filter/hover and browser performance tests after every optimisation.

Do not finish a performance task while `PERF_DEFECT_BACKLOG.lock.md` has unchecked items.
Do not finish without before/after timings.
Do not remove functionality to improve speed.

## Parquet data-quality rule

For Stage 1 governance dashboard work, the source of truth is the curated Parquet candidate pack resolved from `MODEL_DIAGNOSTIC_DATA_ROOT`, `STAGE1_DASHBOARD_DATA_ROOT`, CLI arguments, or the Streamlit data-root control.

Legacy run-folder CSV/XLSX outputs are review-only. They must not become the main app path or override Parquet-backed finalists.

Before declaring completion:

- write `artifacts/data_source_manifest.json` for the active data root;
- prove the current finalist values reconcile to Parquet `is_current_recommended` rows;
- prove the older AutoGluon balanced-run finalist values are not current latest finalist values;
- prove the candidate landscape is a capped curated cone/frontier sample, not a raw candidate dump;
- prove pure Schiff excludes residuals, blends, solvers, ensembles, top/mean/median variants, and convex solver rows;
- prove primary filters are directly clickable and hovers are management-readable;
- update `artifacts/data_validation_review.md`, `artifacts/cone_landscape_review.md`, `artifacts/filter_interaction_review.md`, reviewer files, and `.agent_state.md`.

Do not mark this sprint complete while `artifacts/recursive_audit_loops.json` has fewer than 20 documented recursive audit loops unless the task is explicitly left as in progress in `.agent_state.md`.

## Hundred-gate Parquet visual conformance rule

This dashboard task is not complete unless all 100 validation gates in `EIGHTY_GATE_VALIDATION.lock.md`, `VISUAL_LAYOUT_GATES.lock.md`, and `VISUAL_TARGET_CONFORMANCE.lock.md` pass.

Passing pytest is necessary but not sufficient.

The agent must run `scripts/run_recursive_dashboard_validation.ps1`.

The agent must not claim completion if:

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

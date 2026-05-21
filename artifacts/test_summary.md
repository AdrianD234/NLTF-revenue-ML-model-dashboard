# Test Summary

Dashboard: NLTF Stage 1 Model Governance Dashboard

Validated URL: `http://localhost:8501`

Validated run folder: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Data Evidence

The validation run loads the verified curated latest-arbitration data pack for all core pages:

| Dataset | Rows |
|---|---:|
| finalist accuracy | 3 |
| candidate landscape sample | 293 |
| pure Schiff benchmark | 3 |
| PDF comparison | 3 |
| stress and horizon | 18 |
| ensemble composition | 12 |
| paired versus Schiff selected | 3 |
| annual predictions selected | 530 |
| quarterly predictions selected | 3,036 |

Latest finalist reconciliation:

- PED VKT per capita: 2.47358% quarterly MAPE, 2.38709% annual MAPE.
- Light RUC volume: 9.14755% quarterly MAPE, 5.99950% annual MAPE.
- Heavy RUC volume: 3.56092% quarterly MAPE, 3.17141% annual MAPE.
- The stale AutoGluon balanced-run finalist values 5.49%, 11.55%, and 12.38% are explicitly rejected by curated-data and browser tests.

## Verification Commands

```powershell
python -m compileall .
python -m pytest -q
pwsh -File scripts\verify_dashboard.ps1
```

Runtime note: this environment runs those commands through the Codex bundled Python path inside `scripts\verify_dashboard.ps1`.

Latest local tests after recursive audit loop 9:

- Runtime compile passed with the bundled Codex Python executable.
- Runtime pytest passed: `115 passed, 29 deselected`.
- Focused artifact-freshness regression passed: `5 passed`.
- Full verifier curated-data checks passed: curated data rebuilt and verified, `115 passed, 29 deselected`; Playwright e2e `28 passed`.
- Full verifier strict sprint gate passed with the latest arbitration run as source of truth.
- Loop 2 added a stale-evidence gate so current management and performance review artifacts cannot name `run_20260519_085639` as the active validation/configured run.
- Loop 3 removed stale non-image console/snapshot/CSV files from `artifacts/screenshots` and added a guard that the screenshot directory contains only visual evidence files.
- Loop 4 updated `README.md` so public run guidance names the latest arbitration run and added a regression assertion that it cannot present the old balanced run as the validation run.
- Loop 5 scrubbed the old balanced run from active performance evidence and added a regression assertion that performance review/log artifacts cannot point to that run.
- Loop 6 moved the README and performance stale-run checks into `scripts/verify_dashboard.ps1` so the strict verifier directly enforces them, not only pytest.
- Loop 7 added direct strict-verifier checks for curated candidate role/cap coverage, pure-Schiff purity, required stress buckets, and positive ensemble weights.
- Loop 8 added a direct strict-verifier gate that rejects non-image artifacts under `artifacts/screenshots`.
- Loop 9 strengthened cone-landscape validation with per-stream frontier, top-candidate cluster, and distribution-sample assertions and added explicit role coverage to `artifacts/cone_landscape_review.md`.
- Loop 10 added recursive-audit log integrity checks so loop entries cannot remain in a pending data/browser verification state. Full compile passed, full pytest passed `117 passed, 29 deselected`, and strict verification passed with curated-data rebuild plus Playwright e2e `28 passed`.
- Loop 11 refreshed `artifacts/reviews/visual_styling.md` from stale fail/open-defect language to a current pass review and added review-artifact status tests. Focused reviewer tests passed `2 passed`; full pytest passed `119 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 12 refreshed `artifacts/reviews/interaction_filter.md` from stale browser-e2e-failing language to a current pass review and expanded review-artifact status tests. Focused reviewer tests passed `3 passed`; full pytest passed `120 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 13 refreshed UX screenshot, UX addendum, and layout/grid reviews from older eight-tab/sidebar-heavy evidence to the current four-page governance shell and added them to the review-artifact status tests. Focused reviewer tests passed `4 passed`; full pytest passed `121 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 14 refreshed `artifacts/performance_baseline.json` from the latest arbitration run using `scripts/benchmark_dashboard.py --refresh-baseline` and added a freshness assertion so the active baseline cannot point at the older balanced run. Focused freshness tests passed `6 passed`; full pytest passed `122 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 15 added freshness assertions for `artifacts/performance_latest.json` and the latest `artifacts/performance_history.json` entry so the active performance tail remains tied to `run_20260520_002339`. Focused freshness tests passed `7 passed`; full pytest passed `123 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 16 added a source-of-truth lock reconciliation test so `LATEST_RUN_SOURCE_OF_TRUTH.lock.md` must match the curated finalist models and values. Focused latest-arbitration tests passed `3 passed`; full pytest passed `124 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 17 added candidate-landscape lock-file assertions for the hard cap, curated cone/frontier modes, and marker-role contract. Focused cone tests passed `8 passed`; full pytest passed `125 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 18 added locked-backlog closure tests across BUG, visual, filter/hover, and performance defect backlogs, and added explicit performance closure evidence. Focused locked-backlog tests passed `2 passed`; full pytest passed `127 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 19 added recursive-audit screenshot-evidence existence checks so loop entries cannot reference missing screenshot files. Focused recursive-log tests passed `3 passed`; full pytest passed `128 passed, 29 deselected`; strict verification passed with Playwright e2e `28 passed`.
- Loop 20 added pytest and strict-verifier gates requiring at least 20 recursive audit loops. Focused recursive-log tests passed `3 passed`; full pytest passed `128 passed, 29 deselected`; strict verification passed with the 20-loop gate active and Playwright e2e `28 passed`.
- Performance verifier passed against the latest arbitration run; the latest performance artifact records `recommended=3`, `summary=293`, `quarterly_predictions=3,036`, `weights=12`.
- Full verifier strict sprint gate passed after 61 visual/product loops were documented.
- Focused filters-and-hovers repair sprint added `tests/test_filter_and_hover.py`; local focused browser run passed `8 passed`.
- Browser checks confirm primary filters are clickable directly without the More button; Stream, Model Family, Stage, Baseline, Horizon, Forecast Vintage, and Date Window all open as real controls.
- Browser checks confirm hover labels are human-readable across Finalist Accuracy, Candidate Landscape, Ensemble Composition, and Stress Checks, with no underscores, raw column names, or excessive decimals.
- Playwright browser QA clicks the four primary governance pages and saves `artifacts/screenshots/final-01-overview.png` through `final-04-schiff-benchmark.png` at a 1680 x 940 management-review viewport. The latest Overview pass also asserts all five numbered Overview modules are above the first viewport fold and that Forecast Vintage / Date Window filter values are readable.
- Desktop header QA now asserts the primary navigation sits in the masthead band to the right of the Governance title, and that the filter band remains compact near the top of the viewport.
- In-app browser QA clicked all four primary governance pages after loop 60 and saved `artifacts/screenshots/iab-loop60-01-overview.png` through `iab-loop60-04-schiff-benchmark.png`; the narrow viewport screenshots verify wrapped page labels, readable filters, non-overlapping navigation, a readable two-column Overview grid, the compact filter evidence strip, the Diagnostics residual ACF lag-bar panel, Diagnostics-specific chart captions with no stale Overview notes, compact icon KPI rows on Diagnostics and Schiff Benchmark, the compact Scenario Comparison `Edit` control, earlier Schiff cross-validation evidence, and page-body content that follows visible nav clicks.
- Browser QA after loop 61 saved `artifacts/screenshots/iab-loop61-01-overview.png` through `iab-loop61-04-schiff-benchmark.png`; the Scenario Comparison capture shows the improvement-vs-benchmark panel starting higher in the in-app viewport.
- Earlier in-app browser QA clicked all 10 analytical modules and saved `artifacts/screenshots/iab-01-overview.png` through `iab-10-run-audit.png`.
- In-app browser console errors: none captured.
- Streamlit exception blocks: none detected.

## Product-Hardening Evidence

- Improvement loops documented: 61.
- Material product improvements documented: at least 50.
- New or strengthened assertions documented: at least 66.
- Reviewer passes written: data correctness, UX/screenshot, governance/story, visual styling, interaction/filter.
- Original spec conformance matrix written.
- Visual reference comparison written.
- Management-readiness report written.

## Browser Verification Coverage

The Playwright e2e test checks:

- no Streamlit exception block;
- no visible Streamlit deployment chrome in the management-review body;
- no page errors;
- no browser console errors;
- Waka Kotahi-style masthead, visible governance filter bar, and run-evidence caption with file and family-scope coverage;
- Reset Filters action and current-view JSON export control;
- primary governance navigation: Overview, Diagnostics, Scenario Comparison, Schiff Benchmark;
- supporting modules: Candidate Landscape, Ensemble Composition, Forecasts and Errors, Stress Checks, Model Inventory, Run Audit;
- Overview report modules for finalist accuracy, candidate landscape, ensemble composition, stress checks, and forecast error distribution;
- Diagnostics test-matrix, autocorrelation, heteroscedasticity/error, residual-proxy, and summary sections;
- Diagnostics browser check now asserts all six numbered diagnostic panels are above the first viewport fold;
- Diagnostics browser check now asserts reference-style Diagnostic Coverage and Logged Diagnostics KPI card labels;
- Diagnostics browser check now asserts the provenance note explaining proxy panels and unavailable classical diagnostics;
- Diagnostics browser check now asserts the compact evidence strip, Diagnostics-specific captions, top diagnostic panels above the fold, and absence of stale Overview captions in the in-app viewport;
- Scenario A/B controls, accuracy comparison, horizon error, improvement vs benchmark, forecast distribution, and decision lens;
- Scenario Comparison browser check now asserts compact Scenario A/B controls and all six numbered panels are above the first viewport fold;
- Scenario Comparison browser check now asserts the first three in-app Scenario panels are above the fold and the Improvement vs Benchmark card starts before y=790;
- Scenario Comparison browser check now asserts the Scenario A versus pure-Schiff KPI copy and percentage-point contrast semantics;
- Scenario Comparison browser check now asserts the positive-gain and 55 percent win-rate decision rule is visible;
- Scenario Comparison browser check now asserts the drilldown cue for full forecast-error tails and stress rows is visible;
- Schiff benchmark MAPE cards, quarterly-vs-annual chart, replication notes, and benchmark comparison summary;
- Schiff Benchmark browser check now asserts the main chart, replication notes, and three stream cross-validation panels are above the first viewport fold;
- Schiff Benchmark browser check now asserts pure-Schiff structural benchmark KPI wording;
- Overview browser check now asserts the Governance Score KPI explicitly says `beat pure Schiff` and `logged diagnostics`;
- Overview browser check now asserts the candidate landscape includes a data-backed frontier readout;
- Overview browser check now asserts the stress panel includes a data-backed weakest visible stress readout;
- Narrow-browser Playwright check now asserts the four primary navigation labels, readable filter values, no shell overflow, and stacked Overview chart cards at an 820px viewport;
- Desktop-header Playwright check now asserts the nav position, right-side masthead placement, and compact filter-band position;
- Diagnostics unit and browser checks now assert the residual ACF-by-lag diagnostic panel;
- Scenario Comparison browser checks now assert the compact `Edit` scenario-control action and absence of the longer crowded label;
- Schiff Benchmark screenshot review now asserts compact notes and earlier cross-validation evidence in the in-app viewport;
- primary navigation browser checks now click visible nav text and assert the correct page body replaces the prior page body;
- Diagnostics and Schiff Benchmark browser checks now assert dense icon KPI rows at the in-app browser width;
- filter-band browser checks now assert the first KPI row and first Overview chart start within reference-density vertical targets;
- candidate export, model detail selector, inventory download, run-audit error diagnostics, and stress/high-risk warnings.
- primary filters clickable coverage: `test_primary_filters_are_clickable`, `test_all_primary_filter_dropdowns_open`, and `test_reset_filters_restores_defaults`;
- hover human-readable coverage: `test_candidate_landscape_hover_is_human_readable`, `test_finalist_accuracy_hover_is_human_readable`, `test_ensemble_hover_is_human_readable`, and `test_stress_hover_is_human_readable`.

Screenshots are saved as `artifacts/screenshots/mcp-*.png`, `artifacts/screenshots/final-*.png`, and `artifacts/screenshots/iab-*.png`.

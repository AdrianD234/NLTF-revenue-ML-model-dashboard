# REQUIREMENTS.lock.md

This file locks the NLTF Stage 1 Model Governance Dashboard scope used for feature-completeness verification.

## Locked Requirements

| ID | Requirement | Acceptance Evidence |
|---|---|---|
| R1 | Select or enter a completed model-run folder, discover `run_*` folders, and exclude live folder `run_20260519_150434`. | Data-loader tests and sidebar browser screenshot. |
| R2 | Load current and older CSV names, plus workbook fallbacks where available. | Alias tests and validation-run data assertions. |
| R3 | Missing or empty files must not crash the app; dependent pages must warn and continue. | Loader tests and browser checks for no Streamlit exception blocks. |
| R4 | Show file-read status with file, found flag, rows, columns, size, and last modified. | Run Audit screenshot and Playwright checks. |
| R5 | Executive Summary must show KPI cards, finalist quarterly/annual MAPE chart, and a management answer for which model won, whether it beat Schiff, robustness, and warnings. | Source-metric tests, browser screenshot, and Playwright text checks. |
| R6 | Candidate Landscape must show quarterly MAPE versus annual MAPE with stream colours, candidate/finalist/Schiff markers, filters, hover data, and no placeholder points. | Plot tests, Playwright checks, and screenshot review. |
| R7 | Schiff Comparison must show paired table, gain chart, baseline-versus-challenger scatter, stream-level interpretation badges, and structural benchmark chart. | Playwright checks, source data assertions, and screenshot review. |
| R8 | Ensemble Composition must show finalist composition with component weights or membership, short C-labels, mapping table, and origin weight path when present. | Plot tests, Playwright checks, and screenshot review. |
| R9 | Forecasts and Errors must show compact controls, actual-versus-predicted series, and absolute percentage error distribution by horizon bucket. | Playwright checks and source data assertions. |
| R10 | Stress Checks must cover 1-4, 5-8, 9-12 quarters, 2024+, 2022-23, and annual buckets with Light RUC commentary. | Stress-bucket tests, chart screenshot, and Playwright checks. |
| R11 | Model Inventory must provide filters, top-N ranking by quarterly/annual MAPE, table, and CSV download. | Browser checks and screenshot evidence. |
| R12 | Run Audit must show feature counts, feature audit, errors table, and error flags for HyperOpt, Ray, permission, neural-model, empty-file, and total logged errors. | Error-flag tests, Run Audit screenshot, and Playwright checks. |
| R13 | Visual style must be professional, readable, and not mostly blank; long model names must be shortened or mapped. | Screenshot review and visual/product review loop. |
| R14 | Closed-loop verification must include compileall, pytest, PowerShell verifier, browser page walkthrough, screenshots, coverage, screenshot review, quality rubric, and backlog closure. | `artifacts/*` evidence files and verifier artifact gates. |
| R15 | Product review must include data correctness, visual/product, and governance/story loops documented after the first full pass. | `artifacts/product_review_loops.md`. |
| R16 | Four primary Waka Kotahi/NZTA-style pages must exist: Overview, Diagnostics, Scenario Comparison, and Schiff Benchmark. | Streamlit smoke and Playwright browser assertions. |
| R17 | Overview must include finalist accuracy, candidate landscape, ensemble composition, stress/horizon, and forecast-error distribution chart modules. | `artifacts/screenshots/final-01-overview.png`; Playwright assertions. |
| R18 | Diagnostics must show run-health cards and available diagnostics, with clear not-available states when source diagnostics are absent. | `artifacts/screenshots/final-02-diagnostics.png`; Playwright assertions. |
| R19 | Scenario Comparison must compare Scenario A and B, using finalist versus Schiff where scenario files are absent. | `artifacts/screenshots/final-03-scenario-comparison.png`; Playwright assertions. |
| R20 | Schiff Benchmark must show benchmark MAPE cards, quarterly-vs-annual chart, cross-validation-style horizon evidence, comparison summary, and Schiff notes. | `artifacts/screenshots/final-04-schiff-benchmark.png`; Playwright assertions. |
| R21 | Main-page filter bar must expose stream, model family, stage, baseline, horizon, vintage, date window, reset, and state export. | `app.py::render_top_filter_bar`; browser assertions; `INTERACTION_SPEC.lock.md`. |
| R22 | Product-hardening sprint must document at least 20 loops, visual reference comparison, five reviewer files, and strict verifier gates. | `artifacts/improvement_loops.json`; `artifacts/visual_reference_comparison.md`; `scripts/verify_dashboard.ps1`. |

## Management Questions

The dashboard must answer these questions without requiring the user to inspect raw CSVs:

1. Which model won for PED, Light RUC, and Heavy RUC?
2. Did the winner beat the Schiff structural benchmark?
3. Is the result robust across quarterly, annual, horizon, and stress checks?
4. What warnings or run-health issues need attention?

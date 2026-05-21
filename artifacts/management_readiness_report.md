# Management Readiness Report

Dashboard: NLTF Stage 1 Model Governance Dashboard

Validation run: `C:\Users\Adrian Desilvestro\OneDrive\Documents\Playground\Revenue Modeling - Strategic Review\04 Models\Inputs\stage1_finalist_arbitration_outputs\run_20260520_002339`

## Readiness Decision

Management-ready for Stage 1 model-form governance review against the latest arbitration run.

The dashboard presents a Waka Kotahi/NZTA-style governance shell, four primary management pages, stream-level decision status, Schiff comparison evidence, stress-window caveats, run-health diagnostics, and exportable current-view settings. It remains correctly framed as Stage 1 actual-driver evidence for Stage 2 uncertainty testing, not final end-to-end forecast sign-off.

The visible headline finalist values reconcile to the latest arbitration curated data pack:

- PED VKT per capita: 2.47% quarterly MAPE and 2.39% annual MAPE.
- Light RUC volume: 9.15% quarterly MAPE and 6.00% annual MAPE.
- Heavy RUC volume: 3.56% quarterly MAPE and 3.17% annual MAPE.

The older balanced-run finalist values 5.49%, 11.55%, and 12.38% are not current finalist values and are treated only as stale-value rejection checks.

## What A Manager Should Conclude

- PED and Heavy RUC show Schiff-beating Stage 1 model-form evidence on the paired comparison rule.
- Light RUC remains a benchmark watch point because its paired win rate is mixed.
- RUC streams remain stress-risk watch points in the 2022-23 policy window.
- Logged errors are candidate-search diagnostics, dominated by missing-HyperOpt rows, and should be reviewed before production promotion.
- The next governance step is Stage 2 uncertainty testing with vintage macro, fuel-price, and policy-input forecast uncertainty.

## Evidence Package

- `artifacts/improvement_loops.json`: at least 61 product-hardening loops.
- `artifacts/recursive_audit_loops.json`: recursive latest-arbitration audit loop evidence; this sprint remains in progress until at least 20 recursive loops are complete or the budget is exhausted.
- `artifacts/product_improvements.md`: at least 50 material product improvements.
- `artifacts/assertion_inventory.md`: at least 66 new or strengthened assertions.
- `artifacts/deep_quality_review.md`: every page scores at least 9.5/10.
- `artifacts/visual_reference_comparison.md`: every page scores at least 9/10 against the supplied visual-reference structure.
- `artifacts/spec_conformance_matrix.md`: original locked spec mapped to evidence.
- `artifacts/reviews/data_correctness.md`: data reviewer pass with metric reconciliation.
- `artifacts/reviews/ux_screenshot.md`: UX reviewer pass.
- `artifacts/reviews/governance_story.md`: governance/story reviewer pass.
- `artifacts/reviews/visual_styling.md`: visual styling reviewer pass.
- `artifacts/reviews/interaction_filter.md`: interaction/filter reviewer pass.
- `artifacts/screenshots/final-01-overview.png` through `final-10-run-audit.png`: Playwright browser evidence.
- `artifacts/screenshots/iab-01-overview.png` through `iab-10-run-audit.png`: in-app browser QA evidence.

## Page Readiness

| Page | Management value | Evidence |
|---|---|---|
| Overview | Gives the enterprise readiness decision and the five key report figures on one management page | final and in-app screenshots; browser assertions |
| Diagnostics | Shows run-health cards, available diagnostics, and governed not-available states | final and in-app screenshots; browser assertions |
| Scenario Comparison | Compares refined finalist versus Schiff when no scenario file exists | scenario controls and decision lens assertions |
| Schiff Benchmark | Separates pure Schiff benchmark evidence from Schiff residual/blend challengers | Schiff-class tests and benchmark screenshot |
| Candidate Landscape | Shows frontier, finalists, Schiff markers, outlier handling, and candidate export | chart tests and browser assertions |
| Ensemble Composition | Shows components, C-label mapping, static/prequential caveat | ensemble tests |
| Forecasts and Errors | Shows selected forecast, percent error, distribution, and horizon drilldown | forecast tests |
| Stress Checks | Shows horizon/stress buckets, 2020-21, 2022-23, 2024+, high-risk band | stress tests |
| Model Inventory | Shows inventory cards, full model detail selector, family performance, Schiff-class mix | inventory tests |
| Run Audit | Shows run health, file status, error types, and feature audit | loader and run-health tests |

## Verification Standard

The verifier blocks completion unless the product-hardening sprint evidence is present, the loop count is at least 20, material improvements and assertions are documented, all deep-quality scores are at least 9.5/10, visual-reference scores are at least 9/10, the backlog is closed, reviewer artifacts exist, screenshots exist, and browser verification passes.

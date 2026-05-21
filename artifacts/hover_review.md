# Hover Review

Focused review for the Filters and Hovers repair sprint, refreshed for the latest arbitration curated-data pass.

| Chart | Before problem | After screenshot | Tooltip text sample | Formatting check | Status |
|---|---|---|---|---|---|
| Finalist Forecast Accuracy | Annual-bar hover did not always include the paired quarterly context. | `artifacts/screenshots/hover-finalist-accuracy.png` | `PED VKT per capita; Quarterly MAPE: 2.47%; Annual MAPE: 2.39%; Model: PED Static Solver; Source: Posthoc Ensemble` | Human labels, two-decimal MAPE, no raw column names, no underscores. | Complete |
| Candidate Search Landscape | Headless hover fallback skipped traces with customdata but no serialised x/y arrays. | `artifacts/screenshots/hover-candidate-landscape.png` | `Stream: Heavy RUC volume; Model: Heavy RUC Static Solver; Candidate role: Recommended finalist; Quarterly MAPE: 3.56%; Annual MAPE: 3.17%; Source: Posthoc Ensemble` | Human stream/model/source labels, two-decimal percentages, no raw `quarterly_mape` or `source_family`. | Complete |
| Ensemble Composition | Hover needed compact weight and component labels. | `artifacts/screenshots/hover-ensemble-composition.png` | `Stream: PED VKT per capita; Weight: 31.1%; Ensemble: PED Static solver; Component: C2` | Weight has one decimal place, short component label is readable, full component mapping is kept in the lookup. | Complete |
| Stress Checks | Hover needed plain horizon/stress labels. | `artifacts/screenshots/hover-stress-checks.png` | `Stress window: 2022-23; MAPE: 18.79%; Model: Light RUC Static solver; Rows: 1` | Horizon label is plain English, MAPE has two decimals, count is whole-number formatted. | Complete |

Browser evidence:

- `tests/test_filter_and_hover.py::test_candidate_landscape_hover_is_human_readable`
- `tests/test_filter_and_hover.py::test_finalist_accuracy_hover_is_human_readable`
- `tests/test_filter_and_hover.py::test_ensemble_hover_is_human_readable`
- `tests/test_filter_and_hover.py::test_stress_hover_is_human_readable`
- `tests/test_hovers_are_readable.py`

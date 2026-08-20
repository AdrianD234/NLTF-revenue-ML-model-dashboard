# Governed 6–36 month 12c/L FED deferral — validation report

Base SHA: `4e17156294a768a3cff79de31b870ccb2c80279f`
Tested SHA: _recorded at the end of this report once final_

## Acceptance gates

| gate | result | evidence |
| --- | --- | --- |
| Registry: exactly 8 states, 6 finite deferrals, quarters {2,4,6,8,10,12}, unique IDs/labels/order/starts, start quarters 2027Q3/2028Q1/2028Q3/2029Q1/2029Q3/2030Q1 | PASS | `tests/test_fed_policy_states.py` (20 tests) |
| Legacy aliases resolve; unknown states fail closed in registry, rate_paths, runtime, series coverage | PASS | same |
| Schedule: direct windows exact per duration; in-window = no-uplift; at/after start = planned; before 2027Q1 = planned | PASS | same |
| Catch-up quarters, incl. coincidence with the 2028Q1 6c and 2029Q1/2030Q1 4c steps | PASS | `test_catch_up_quarters_including_coincident_scheduled_increases` |
| Longer deferral rate never exceeds shorter before catch-up; windows nested | PASS | same file |
| Quarterly factors exact ratios (6m factor = 0.70024/0.82024 exactly) | PASS | same file |
| **Six-month exact equivalence** — schedules, affected periods, factors, PED/RUC input rows, rebuilt lag/lead, raw + calibrated forecasts, annual bridge, chart rows, policy audit, line reconciliation, extract rows, scenario key digests, both engines | **PASS — exact (max_abs_delta 0.0 on all 40 comparisons)** | `six_month_parity.csv`, `scripts/verify_legacy_6m_parity.py` vs `legacy_6m_reference/` captured at the base SHA; base capture reproduces itself bit-for-bit (77/77 frames) and rebuilt replay caches reproduce the committed base caches bit-for-bit on every legacy scenario |
| In-process generic-vs-legacy wrapper equivalence (environment-independent) | PASS | `test_generic_six_month_state_equals_legacy_wrappers` |
| Scenario matrix: 32 unique paths, 480 unique FY2026–FY2030 rows, registry-driven metadata, all families × 8 timings, no missing values, MVR invariant, timing identities | PASS | `tests/test_net_revenue_timing_comparison.py` (9 tests) |
| Official comparator: factors per deferral confined to affected years, factor < 1, rate-only, published rows untouched, cumulative rate-only loss ordered by duration | PASS | `test_official_comparator_factors_for_every_deferral`, `test_official_cumulative_rate_only_revenue_is_ordered_by_duration` |
| Interactions: 18m+PT High+Fleet High; 24m+VFM Fast+e-RUC; 30m+High conflict+High population; 36m+Freight High+PT Med; 6m at defaults; 12m+optimized PED bridge; identical configs identical; 64 unique key digests | PASS (8 tests) | `tests/test_fed_deferral_interactions.py` |
| Interaction evidence matrix (13 combinations × MVR invariance, direct-window ordering, formula closure) | PASS (13/13) | `interaction_test_matrix.csv` |
| e-RUC note: window years after the petrol fleet has fully migrated off excise show deferred == published for Net FED (no wedge remains to defer). Explained, not suppressed. | Documented | `interaction_test_matrix.csv`, test comments |
| Runtime pack: 64 unique states/engine, schema/builder v2, exact live parity at build, exact round-trip, fail-closed stale/corrupt/missing, no nearest-state fallback, 6m state addressable, 8 uncertainty centres | _pending build completion_ | `tests/test_revenue_outlook_policy_runtime.py` |
| UI: 8 labels in order both dropdowns, preserved production default (Deferred 6 months), persistence, catch-up help, A/B independence | _pending AppTest/Playwright run_ | `test_revenue_outlook_renders_every_governed_policy_duration`, `tests/test_playwright_dashboard.py` |
| Clean-room fast/affected(/full) tiers, replay fingerprints | _pending_ | |

## Notes

* Parity methodology: three comparator defects were found and fixed during
  verification (pandas' default `read_csv` float parser and `to_numeric`'s
  arrow string parser are each up to 1 ULP lossy; CSV cannot represent the
  literal string "nan"). After parsing with correctly-rounded Python floats,
  every comparison is exact. No tolerance was introduced or widened anywhere.
* The handoff's "default remains Original timing" conflicts with live
  production (default = Deferred 6 months, asserted by the pre-existing smoke
  test). The production default is preserved; flagged as an owner decision.

# Revenue Outlook pack migration — deterministic Light RUC state

**Migration ID:** `light-ruc-deterministic-state-2026-07`
**Canonical route version:** `promote-then-rebuild-v2`
**Promotion revision:** 2
**Data schema:** unchanged

## What changed

This pack was regenerated using the canonical two-stage route: reviewed
scenario workbooks were promoted from committed source files, and the enriched
runtime pack was then rebuilt with the MBU26 annual spine and historical
actuals.

The effective scenario-input inventory is unchanged from the prior pack. The
former and current materialisation routes contain identical workbook hashes,
scenarios, roles, periods and input rows.

Decision-facing Light RUC forecasts now load the verified, hash-gated promoted
fitted state rather than refitting the residual Gradient Boosting model at
score time. This removes platform-dependent forecast variation. Resulting value
changes are confined to Current Base and comparison Light RUC activity and
their governed downstream revenue and migration formulas. No MBU26, actual or
historical-actual value is changed. **The migration was not selected for
proximity to MBU26.**

## Source-inventory equivalence

The two materialisation routes were proven equivalent, not assumed:

| Field | Prior route | Canonical route |
|---|---|---|
| `scenario_input_cells` | 15,472 | 15,472 |
| `scenario_input_long` | 15,200 | 15,200 |
| `scenario_input_wide` | 600 | 600 |
| `scenario_feature_lineage` | 44,800 | 44,800 |
| Workbook SHA-256, both scenarios | — | identical |
| Scenario names, roles, schema, sheet count | — | identical |

`tests/test_scenario_input_route_equivalence.py` pins this so the two routes
cannot silently diverge in future. The only approved difference is the
descriptive `source_policy` wording.

## Promoted fitted state

| | |
|---|---|
| SHA-256 | `41669526945c546fc66a1e6d327bde3c9077b4fe6f6f4ca24fda3709654a1294` |
| Training window | 2017Q1–2025Q4, 36 rows |
| Archived training-fit replay delta | **0.0** |
| Runtime behaviour | loaded and hash-gated; refitting disabled |

## Value impact, FY2026–FY2030

Maximum movement anywhere in the pack: **0.4123%**, inside the 0.48% platform
envelope. 846 of 2,548 rows changed; structure and keys unchanged.

| Series | FY | Before | After | Δ | Δ% |
|---|---|---:|---:|---:|---:|
| Light RUC net km | 2027 | 12,081.804 | 12,103.058 | +21.254 | +0.176% |
| Light RUC net km | 2030 | 12,818.272 | 12,844.588 | +26.316 | +0.205% |
| Light RUC net revenue | 2027 | 881.153 | 882.703 | +1.550 | +0.176% |
| Light RUC net revenue | 2030 | 1,153.057 | 1,155.424 | +2.367 | +0.205% |
| Total RUC net revenue | 2027 | 2,217.924 | 2,219.584 | +1.660 | +0.075% |
| Total RUC net revenue | 2030 | 3,019.465 | 3,022.159 | +2.693 | +0.089% |
| Net FED revenue | 2026 | 2,021.586 | 2,022.309 | +0.723 | +0.036% |
| Net FED revenue | 2030 | 2,465.755 | 2,467.197 | +1.442 | +0.058% |

Six runtime-contract checkpoints were re-promoted, largest movement 0.0352%.
No numerical tolerance was widened; all remain at 1e-6 absolute.

## Gate evidence

`scripts/light_ruc_repromotion_audit.py` ran as a blocking gate and reported
all stop conditions clear: no key or row-structure change, no MBU26/actual/
historical-actual change, no change outside the Light RUC lineage, maximum
movement inside the envelope, and no sign flips.

## Reproducing

```bash
python scripts/promote_revenue_outlook_from_workbooks.py \
  --basecase "<de-prefixed basecase workbook>" \
  --comparison "<de-prefixed comparison workbook>"
python scripts/rebuild_current_revenue_outlook_runtime.py
python scripts/light_ruc_repromotion_audit.py --candidate data/current_revenue_outlook
```

Raw workbooks must be de-prefixed before promotion; promoting an
already-prefixed file double-prefixes its hash.

# Consultant handoff — governed 6–36 month 12c/L FED deferral scenarios (2026-08-20)

This note extends
[CONSULTANT_HANDOFF_TREASURY_CONFLICT_SCENARIOS_2026-07-25.md](CONSULTANT_HANDOFF_TREASURY_CONFLICT_SCENARIOS_2026-07-25.md),
which introduced the three-state 12c policy selector (Original / Deferred six
months / Off). That document remains the authority for the Treasury macro and
conflict fuel-price transmission; nothing there is rewritten by this feature.

## What changed

The Current 12c policy selector and the MBU26 synthetic official rate-only
counterfactual selector each now expose eight governed timing states:

| state id | calculation id | label | direct window | deferred start |
| --- | --- | --- | --- | --- |
| `published` | `published` | Original timing — 1 Jan 2027 | — | 2027Q1 |
| `delayed_6m` | `delay_6m` | Deferred 0.5 years (6 months) — 1 Jul 2027 | 2027Q1–2027Q2 | 2027Q3 |
| `delayed_12m` | `delay_12m` | Deferred 1.0 year (12 months) — 1 Jan 2028 | 2027Q1–2027Q4 | 2028Q1 |
| `delayed_18m` | `delay_18m` | Deferred 1.5 years (18 months) — 1 Jul 2028 | 2027Q1–2028Q2 | 2028Q3 |
| `delayed_24m` | `delay_24m` | Deferred 2.0 years (24 months) — 1 Jan 2029 | 2027Q1–2028Q4 | 2029Q1 |
| `delayed_30m` | `delay_30m` | Deferred 2.5 years (30 months) — 1 Jul 2029 | 2027Q1–2029Q2 | 2029Q3 |
| `delayed_36m` | `delay_36m` | Deferred 3.0 years (36 months) — 1 Jan 2030 | 2027Q1–2029Q4 | 2030Q1 |
| `off` | `no_uplift` | No 12c uplift | 2027Q1 onward | — |

The rule generalises the governed six-month scenario exactly: within the
direct window the selected rate is the governed no-uplift rate; from the
deferred start the published planned path is unchanged. **Only the initial
12c/L wedge is deferred. Other scheduled increases retain their published
dates. At the selected start date the path catches up to the published rate,
so a larger one-quarter increase can occur when catch-up coincides with
another scheduled increase** (12 months rejoins into the 2028Q1 6c step;
24 and 36 months rejoin into the 2029Q1/2030Q1 4c steps).

## Single source of truth

`model_dashboard/fed_policy_states.py` (the `FedPolicySpec` registry) owns
every state's IDs, labels, durations, start quarters, schedule columns, path
suffixes, scenario-name suffixes, pair IDs, display order, aliases and
notes. All consumers — `rate_paths`, `conflict_fuel_paths`,
`fuel_price_scenario`, `revenue_outlook`, `revenue_outlook_series_coverage`,
the policy runtime, `app.py` and
`scripts/materialize_conflict_scenario_extract.py` — derive their
vocabularies from it. Adding a duration is one registry row.

## Scope and matrix

* Public scenario matrix: Base + Low/Medium/High conflict × eight timing
  states = 32 paths; the FY2026–FY2030 three-series timing extract carries
  480 unique rows. Path IDs extend the existing convention
  (`baseline_shifted_12m`, `low_shifted_18m`, …); the historic
  `*_shifted_6m`, `*_published` and `*_no_uplift` IDs are unchanged.
* The compiled replay cache carries one behavioural policy-variant replay
  per non-published state per family (32 scenarios), plus the matching
  price-only macro shadows.
* The instant policy runtime materialises 8 Current × 8 official = 64 exact
  states per engine (schema/builder version 2); the six-month state keeps
  its historic directory ID. Uncertainty centres are computed for the eight
  Current states only. Fail-closed behaviour is unchanged.
* The official comparator remains a rate-only MBU26 counterfactual with
  volumes fixed, labelled synthetic; published source rows never move.

## Acceptance

The generic `delayed_6m` state is proven numerically identical to the
production six-month answer against a reference captured from the unmodified
base SHA: see `artifacts/fed_deferral_duration/six_month_parity.csv`, the
`legacy_6m_reference/` capture, and the implementation/validation reports in
the same directory.

## Known owner decisions

* The live production default (Deferred 6 months) is preserved; the handoff
  brief's "default remains Original timing" did not match production and the
  default was deliberately left unchanged. Flip
  `FED_POLICY_OPTIONS.index(FED_POLICY_DELAYED_6M)` in `app.py` (and the
  smoke-test expectation) if the Original-timing default is wanted.
* BEFU26 still has no synthetic policy counterfactual.

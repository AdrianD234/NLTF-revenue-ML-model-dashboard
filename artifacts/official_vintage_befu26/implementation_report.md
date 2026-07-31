# BEFU26 official vintage and generic official-vintage framework

Branch `feature/official-vintage-befu26`, from `main` at
`7c015c0a15ea27f0fcf65defdf43acb019cbde5d`.

## What was built

A generic, registry-driven official-forecast-vintage framework, with BEFU26
ingested through it as the latest vintage, the default official comparator and
the default bridge-assumption vintage. MBU26 remains registered, byte-identical
and selectable as the prior vintage.

### Commit sequence

| Commit | Scope |
|---|---|
| `8d1a430` | Generic registry, materializer, loader; BEFU26 pack; ingestion + plug-and-play tests |
| `aae3ec6` | Runtime pack builder generalized to registry-driven vintages |
| `d41d98a` | Current bridge refreshed to BEFU26; reconciliation pack; governed re-freezes |
| `3a1f050` | Front-end official comparator vintage selector and policy immutability |
| `b19bbd9` | Regression and invariance gates |
| `498ce35` | Macro-replay vintage-mix fix; remaining gate closures |
| `5a6ffb5` | Implementation report and browser evidence |
| `6bb08d3` | **Closure amendment**: pack bridge authoritative end to end; rate-chart source fixed; registry-driven runtime; 2x2 role matrix; fail-closed registry; leakage gates |
| `ac0247d` | Closure follow-up: fleet-mix selector call fixed; one AppTest timeout aligned to the module helper |

## Closure amendment (post-review)

Two genuine runtime sourcing defects were found in review and fixed:

1. **The effective-rate chart read MBU26 behind a BEFU26 caption.** The chart
   now derives PED intensity and Light/Heavy RUC effective rates from the
   actual bridge vintage; the caption is generated from that same vintage so
   it cannot drift again. `_mbu26_spine` is reserved for the MBU26-only
   synthetic counterfactual, which legitimately hashes that exact file into
   its audit rows.
2. **The pack's bridge vintage was not authoritative.** The macro replay
   resolved the live registry default rather than the manifest of the pack
   being replayed, so a pack built on MBU26 while the registry defaulted to
   BEFU26 would have been re-bridged on BEFU26. `bridge_vintage_id` is now
   threaded from the pack manifest through the Treasury replays, rate paths,
   fleet mix, PED intensity/RUC rate sourcing and the fleet-mix cache
   signature. The registry default only selects a bridge when constructing a
   NEW pack.

Runtime genericity was completed (trace names, ordering, legend defaults,
colour maps, source options, fleet-mix labels, FED-path exclusions and fan
allowances are all registry-generated; the hard-coded BEFU26 default is gone
and the static gate now catches hard-coded BEFU26 defaults too). The
completeness contract fails closed on registry errors. A bidirectional
leakage gate proves no non-selected vintage reaches charts, composition,
reconciliation or downloads. A permanent 2x2 comparator x bridge matrix
builds all four packs and asserts role independence, identity closure and
published-row immutability.

The replay-parity fingerprint SHA is **unchanged** across the closure
(`6849a6da0fcae038d9e72c0203356b21a7394c28fd312baccba66debeb11cac7`),
confirming no replay value moved.

## Source

- Workbook: `references/BEFU26 revenue forecast.xlsx` (vendored, 51,133 bytes)
- SHA-256: `7d6e5b19119ca8b5272ca2205c0735719033d82484ce674cfb595e6f45d085ff`
  (matches the expected uploaded-copy hash)
- Sheet `Baseline`, used range `A1:BD65`, FY2001-FY2055, no Excel formulas
- ACTUAL FY2001-2025, ST_FORECAST FY2026-2030, LT_FORECAST FY2031-2055

Rows are resolved by **exact label match inside anchored worksheet sections**,
never by absolute row index, so a shifted or renamed layout fails closed. 12
sentinels are pinned (the four published totals plus representative activity
and revenue leaves), so a shifted mapping cannot pass by matching only a total.

## Two vintage roles, separately governed

`official_comparator_vintage_id` and `bridge_assumption_vintage_id` are
distinct runtime fields, both defaulting to BEFU26 and both recorded in each
pack manifest with per-vintage horizons and hashes. An analyst can reproduce
Current on one vintage's bridge against another vintage's published path.

## Headline BEFU26 vs MBU26

Total NLTF net revenue, BEFU26 minus MBU26:

| FY | Delta ($m) |
|---|---|
| 2026 | -69.50 |
| 2027 | -90.24 |
| 2028 | -34.37 |
| 2029 | -6.58 |
| 2030 | +8.62 |
| 2040 | +10.03 |
| 2050 | +0.90 |
| 2055 | +0.00 |

Two published ACTUAL revisions at FY2025: `light_petrol_vkt` -0.492090 m km
and `ped_vkt_per_capita` -0.092884 km.

## Impact of the bridge refresh on Current

Current finalist Base case, Total NLTF, refreshed minus the **pinned**
pre-refresh baseline (never a live regeneration):

| Engine | FY2026-2030 | FY2031-2050 |
|---|---|---|
| ensemble | -35.413 $m | -1.969 $m |
| ar1 | -35.447 $m | -1.968 $m |

Fully attributed row by row in `current_bridge_vintage_impact.csv`. Activity
forecasts, promoted fitted states, exact-VFM composition, policy definitions,
Heavy-BEV neutrality and lambda retirement are all unchanged.

## Published-source residuals (named, quantified, retained)

BEFU26 `gross_ruc_revenue` does not close to its class leaves plus refunds -
the same defect family as the known MBU26 FY2027 residual. Nothing is
force-balanced:

| FY | Residual ($m) |
|---|---|
| 2027 | +0.627012 |
| 2028 | +0.466274 |
| 2029 | +0.362901 |
| 2030 | +0.383247 |

## A real defect this work surfaced

`run_direct_treasury_scenario_replay` bridged replayed activity into revenue
through `load_mbu26_annual_spine` while the committed packs had been rebuilt on
the BEFU26 bridge. The replay re-derived revenue with MBU26 rates and
administration and mixed that against BEFU26-based pack values, breaking the
Current RUC identity (Total RUC no longer equalled class leaves less
administration) by up to 2.5e-3 - invisible on a chart, but caught by the
governed 1e-6 reconciliation gate.

Verified against a `main` worktree: main closes at ~4.5e-13, this branch was at
~2.5e-3 before the fix and ~2.2e-12 after. Two gates now prevent regression.

## Composition-refresh candidate: MATERIAL, and NOT applied

BEFU26's embedded Light-RUC class shares differ from the exact-VFM Base
composition by up to **0.025112** (max |share delta|) across 16 FYs (2025-2044),
exceeding the 0.01 threshold. This is recorded as an **opt-in candidate only**
in `class_share_audit.csv`. The Current composition is unchanged and requires a
separate owner decision.

## Official policy treatment

Published official vintages are immutable by default. The synthetic rate-only
counterfactual is labelled "Synthetic official rate-only counterfactual - not a
published forecast", now defaults to **published** (was delayed six months),
renders only while MBU26 is displayed, and is structurally confined to
`mbu26_official` rows - BEFU26 cannot be repriced by it. "BEFU26 deferred" and
"BEFU26 no uplift" can never be displayed as published forecasts.

## Uncertainty treatment

MBU26 archived forecast-error bands are **not** reused for BEFU26. The
availability contract states this explicitly, and BEFU26 shows the governed
scenario range labelled "not probabilistic" or no official interval.

## Plug-and-play contract

17 fixture tests prove a future vintage ingests with **no code changes**: a
PREFU26-style vintage, a different sheet name, a later horizon (FY2060,
inferred and registered), idempotent re-ingestion, and fail-closed behaviour
for conflicting re-ingestion, missing row, renamed label, changed unit,
duplicate year, unknown Period, missing total, non-numeric value, uncached
formula and sentinel mismatch.

Process for the next vintage: drop the workbook in `references/`, run
`scripts/materialize_official_vintage.py`, review the validation report, set
the flags, rebuild packs, review impact, merge after CI.

## Validation

All results below are for the final commit `ac0247d`.

| Gate | Result |
|---|---|
| compileall | PASS |
| Full local pytest | **1109 passed**, 50 skipped, 45 deselected, 0 failed |
| Role-independence 2x2 matrix | **28/28** |
| Runtime genericity + leakage gates | **19/19** |
| Official-vintage reconciliation | **25/25 checks PASS** |
| Corrected MBU26 reconciliation | PASS (all hierarchies < 1e-6) |
| Official policy audit | PASS |
| Long-run evidence | PASS (0 changed values) |
| Extract validation | **21/21 passed** |
| Deployment readiness | PASS |
| Replay-seed diagnostic | PASS (0 missing supported keys) |
| Windows replay parity fingerprint | written (Linux leg from CI) |
| Streamlit AppTest + engine switcher | 51/51 |
| Browser: console errors | **0** |

Browser evidence in `screenshots/`: BEFU26 is the default official comparator,
the chart legend carries only `BEFU26 official`, MBU26 is selectable as the
prior vintage, the synthetic counterfactual is hidden by default, and the
composition chart defaults to FY2050 while extending to the BEFU26 source
horizon FY2055.

## Governed re-freezes

Every re-pinned value is a downstream consequence of the intended bridge
change, carries its old -> new delta and cause in a comment, and **no tolerance
was widened anywhere**: runtime pack artifact hashes; FY2026 pack-stage
contract values (Total NLTF 4628.169746 -> 4599.805745, -0.613%); trace and
source-path allow-lists; `short_run_baseline.csv` (390 moved values, audited in
`short_run_baseline_refreeze_audit.csv`); the FY2027 delay factor (0.9215585 ->
0.9212658); and the Net FED timing benchmarks (FY2026 2103.643887 ->
2106.194985, +0.121%).

This is the largest single-branch re-freeze in this repo's history and is the
part of the diff most deserving human review.

## Deliberately NOT done (separate owner decisions)

- Exact-VFM composition is **not** replaced with BEFU26 embedded shares
- Synthetic BEFU26 policy counterfactuals are **not** enabled
- MBU26 is **not** deleted
- No P1.3 or other model-development programme was started

## Recommendation

**Hold for review, then merge.** Every gate is green and the work is complete
against the brief. Two things warrant an owner's eye before merge: the volume
of governed re-freezes listed above, and the material composition-refresh
candidate, which is a real decision with numbers behind it rather than a
formality.

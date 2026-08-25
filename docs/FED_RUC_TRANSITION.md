# Fleetwide FED → RUC transition (1 January 2028)

The Revenue Outlook page carries a three-state **FED → RUC transition**
selector (single view and both A/B columns):

1. **No fleetwide transition** (default) — byte-identical to the pre-selector
   dashboard.
2. **Fleetwide RUC from 1 Jan 2028 — managed leakage**
3. **Fleetwide RUC from 1 Jan 2028 — leakage stress**

It models a full single-date switch of the remaining petrol fleet from fuel
excise duty (FED) to road user charges, with compliance leakage on the newly
enrolled base. It is **not** the earlier discounted 50/50 FED–RUC transition
proposal (a different policy involving discounted bulk purchases).

## Policy interpretation

- From 2028Q1: FED (petrol excise, LPG, CNG) is removed completely and FED
  refunds cease with the duty; light petrol road use pays RUC at the selected
  timing state's **full light-vehicle rate**; PHEVs lose the ~50% discounted
  rate that compensated for petrol excise and move to the full light rate;
  diesel, BEV and heavy RUC classes are unchanged; MVR/TUC are unchanged.
- The **12c/6c/+4c timing selector stays independent**: it still sets the
  level and timing of the road-charge staircase; the transition moves only
  the collection channel. Before 2028Q1 nothing changes.
- **No travel-demand response is modelled**: the compliance evidence
  quantifies leakage and collection cost, not a robust aggregate VKT
  elasticity to replacing pump tax with distance charging. Each economic
  scenario's governed activity paths are used unchanged.

## Accounting

Quarterly grain (FY2028 = 2027Q3…2028Q2 contains exactly two FED and two RUC
calendar quarters), aggregated to June years:

```
Gq        = Kq * Rq / 1000            newly transitioned petrol RUC ($m)
Kq        = light_petrol_vkt / 4      million km (equal quarters: assumption)
Rq        = implied full light RUC rate, staircase-shaped within the year
age(q)    = 1 + floor((q - 2028Q1) / 4)
collected = Gq * (1 - leakage_age)
```

| Assumption | Managed | Stress |
|---|---|---|
| Debt recovery on known non-compliance | 70% | 50% |
| Transition-year net leakage | 5.9% | 6.5% |
| Known non-compliance, years 2–7 (gross) | 20→10% | 20→10% |
| Long-run known non-compliance (gross) | 9% | 12% |
| Unknown/unrecoverable, year 2 → terminal | 3% → 5% | 3% → 11% |
| One-off implementation cost | $34m | $111m |
| Ongoing collection cost (escalated 2.0%/yr, stated assumption) | $16m/yr | $31m/yr |

Leakage applies **only** to the newly enrolled petrol base. Costs are carried
as explicit audited series (`fed_ruc_transition_collection_cost`,
`fed_ruc_transition_oneoff_cost`) subtracted from Total NLTF — never buried
in RUC aggregates. The audit expander reports the foregone non-road FED
implied by the zeroing against the documents' ~$150m annual reference; the
reference is never re-subtracted.

## Architecture

`model_dashboard/fed_ruc_transition.py` applies a deterministic overlay at
the END of the overlay chain in `app.cached_scenario_overlay_rows`, AFTER the
materialised policy-runtime state is read. The typed key field
`fed_ruc_transition` is registered in the policy runtime's
`_POST_CACHE_OVERLAY_FIELDS`, so the 8×8 catalogue is neither multiplied nor
invalidated. Derived traces (persistent downside, HighPop re-tether), the A/B
engine, the VFM envelope and the XLSX extract all inherit the transition
because they consume the overlay rows downstream.

Reader-facing consequences while a transition is active:

- 50%/80% model-error bands are **withheld** (they would misread as
  leakage-risk intervals) with a stated note;
- the revenue-composition build-up is withheld with a stated note (its
  hidden Heavy-BEV solve would absorb petrol RUC as a phantom class);
- the A/B by-stream breakdown splits out **Light petrol RUC** and shows
  **RUC transition costs** as their own (negative) component;
- the XLSX extract appends rows 66–69 (petrol RUC, leakage, costs) below the
  pinned row-65 total — the governed template file is untouched and the
  default extract layout is byte-identical;
- official comparator sides (BEFU/MBU/PREBU and the PREBU-deferral
  workbook) are locked to *No fleetwide transition*.

Tests: `tests/test_fed_ruc_transition.py` (acceptance criteria on the
governed catalogue frames plus real-path app tests).

# Governed 6–36 month 12c/L FED deferral scenarios — implementation report

Feature branch: `feature/fed-deferral-duration-dropdown`
Base: `4e17156294a768a3cff79de31b870ccb2c80279f` (origin/main at handoff)

## 1. What the old six-month state did

The production "Deferred 6 months" state was deliberately narrow: calendar
2027Q1 and 2027Q2 take the governed "No 2027 12c uplift" rate
(0.70024 NZD/L) instead of the planned rate (0.82024 NZD/L); from 2027Q3 the
published planned path is unchanged. Later planned increases (the 6c step in
2028Q1, 4c in 2029Q1, 4c in 2030Q1, 4c in 2031Q1) retain their published
dates. The wedge is carried into the PED retail-price input, the same
selected/planned proportional factor is applied to real Light and Heavy RUC
model-price inputs and to all five nominal RUC collection-rate leaves, the
Light-price lag and Heavy-price lead regressors are rebuilt, and the governed
structural demand calibration applies the single generalized running-cost
elasticity once per stream. Administration charges and refunds are never
scaled; MVR never moves.

## 2. Why the entire future staircase is not shifted

The governed rule defers only the initial 12c wedge. Sliding the whole
staircase would change the *published dates* of the later legislated steps,
which is a different policy from the one the six-month scenario was governed
to represent. Generalising the existing rule means: for a deferral of D
quarters, the target rate is `no_uplift` from 2027Q1 up to (but excluding)
`serial(2027Q1) + D`, and `planned` from that start quarter onward.

## 3. How each longer duration is generated

`model_dashboard/fed_policy_states.py` is the single canonical registry:
one frozen `FedPolicySpec` per state (published, six finite deferrals, no
uplift) carrying the runtime/UI ID, calculation-layer ID, label, months,
quarters, start period, display order, schedule column, path suffix, pair
suffix, scenario-name suffixes, value_status/data_scope markers, timing
labels and notes. `rate_paths.ped_quarterly_rate_schedules` builds one
schedule column per finite deferral algorithmically from the same committed
source CSV (`data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv`,
which is not modified), failing closed when a window quarter or the rejoin
quarter is absent or non-numeric. Every downstream vocabulary
(conflict-variant registry, replay scenario names, POLICY_PATH_IDS, pair
IDs, extract metadata, policy-runtime catalogue, app labels and aliases)
derives from the registry, so a new duration is one registry row.

Direct windows: 6m 2027Q1–Q2; 12m 2027Q1–2027Q4; 18m 2027Q1–2028Q2;
24m 2027Q1–2028Q4; 30m 2027Q1–2029Q2; 36m 2027Q1–2029Q4. Deferred starts:
2027Q3, 2028Q1, 2028Q3, 2029Q1, 2029Q3, 2030Q1.

## 4. Why catch-up can coincide with another increase

Because later planned increases retain their published dates, the deferred
path re-joins the *level* of the published staircase at its start quarter.
A 12-month deferral rejoins in 2028Q1, where the separate scheduled 6c
increase also lands: the selected rate jumps 0.70024 → 0.88024 in one
quarter. An 18-month deferral lets the 6c increase occur *inside* its window
on its original date (the no-uplift schedule steps 0.70024 → 0.76024 in
2028Q1) and rejoins at 0.88024 in 2028Q3. The 24- and 36-month deferrals
rejoin where the scheduled 4c increases land (0.92024 in 2029Q1, 0.96024 in
2030Q1). This is the intended consequence of the governed rule and is stated
in the UI help, the extract caption and the registry notes
(`FED_DEFERRAL_CATCH_UP_NOTE`).

## 5. PED pump-price transmission

Unchanged mechanism, parameterised by state. For each direct-window quarter:
`nominal_ratio = (policy_free_nominal + published_wedge + delta_cents) /
(policy_free_nominal + published_wedge)`, applied to the real petrol-price
model input. Numerator and denominator share the published-FED basis, so the
implicit deflator is preserved (`policy_real_petrol_ratio ==
policy_nominal_petrol_ratio`). All lineage fields
(`policy_free_source_nominal_petrol_cpl`,
`policy_published_fed_wedge_nominal_cpl`,
`policy_target_nominal_petrol_cpl`, `policy_nominal_petrol_ratio`, …) are
retained per quarter.

## 6. Light and Heavy RUC proportional rate treatment

Unchanged mechanism: the quarterly `target_rate / planned_rate` factor is
applied to the governed real Light/Heavy RUC price inputs (Heavy rows carry
both class prices because the Heavy finalist consumes the Light price), and
the same policy movement reaches the five nominal RUC collection-rate leaves
through the annual bridge. Administration charges and refunds are never
scaled.

## 7. Light lag and Heavy lead boundary effects

After repricing, `lagged_real_light_ruc_price` and
`lead_real_heavy_ruc_price` are rebuilt from the adjusted level paths — pure
shifts over the sorted quarter index, valid for any window length. The
displayed forecast is contemporaneous (the structural calibration replaces
the raw fitted response quarter by quarter), so any adjacent-quarter movement
can arise only through these explicitly rebuilt model-native inputs; the
audit separates `direct_rate_affected_quarters` from the model-response
window (`affected_periods`) so the two are never conflated.

## 8. Why the generalized-cost elasticity is applied once

PED uses the full retail pump-price ratio. Light and Heavy RUC use one
combined diesel-plus-RUC generalized running-cost ratio per 1,000 km against
Base, then apply the governed retail-diesel demand elasticity once
(PED −0.144116582, Light RUC −0.12, Heavy RUC −0.10, from the governed
sensitivity seed frame — not hard-coded and not changed by this feature).
Raising a RUC-only ratio to the diesel elasticity independently would count
the same behavioural response twice. The calibrated structural forecast
*replaces* the raw fitted price response; the fitted GDP factor remains
separately identifiable (inherited from the published family member so
policy timing can never move it), and the additive component attribution
closes exactly to the displayed forecast.

## 9. Current-model vs official rate-only treatment

Current-model paths receive the fixed-finalist behavioural replay: policy
variants are separate replay scenarios whose activity responds through the
governed calibration. The MBU26 official comparator has no behavioural
model: it receives a rate-only counterfactual with volumes fixed, factors
derived from the MBU26 spine and the governed rate schedules over the
official horizon, labelled "Synthetic official rate-only counterfactual —
not a published forecast". Published official source rows are never
overwritten; BEFU26 has no synthetic counterfactual. The two scopes never
share a factor map.

## 10. Transformation order

Unchanged:
bridge → sensitivity layer (fleet efficiency, PT mode shift, freight rail,
demand-elasticity) → Treasury macro → EV/VFM uptake → e-RUC → FED/RUC policy
timing → conflict scenario transformation → governed annual formulas. The
duration selector composes with every existing value-changing control via
`RevenueScenarioComputationKey.current_fed_policy_state` /
`official_fed_policy_state` (already named text fields; no new positional
slot). Non-default lever combinations continue to use the live/reference
pipeline; the policy-runtime catalogue never gains a lever dimension.

## 11. Runtime materialisation design

The instant policy runtime expands from 3×3=9 to 8×8=64 exact states per
engine (schema 2, builder 2). State directory IDs keep the existing
`{engine}__cur-{state}__off-{state}` form, so the six-month state remains
addressable at its historic ID. POLICY_STATES and the alias table derive
from the registry. Policy-aware uncertainty centres depend on the Current
state only: exactly eight centres per engine are computed, never 64.
Fail-closed behaviour is unchanged: missing/stale/corrupt packs raise with
the rebuild command; any key outside the catalogue resolves to
`reference_path_required`, never to a nearest state.

## 12. Six-month parity result

See `six_month_parity.csv` (generated by
`scripts/verify_legacy_6m_parity.py`) against the committed
`legacy_6m_reference/` captured at the base SHA with the unmodified tree.
The annual-bridge shared-window anchoring generalises the production rule
exactly: FY2027 of every deferral and of no-uplift anchors to the six-month
replay (the production no-uplift rule, unchanged); later fiscal years wholly
inside a longer deferral's window anchor to the no-uplift replay, whose
pricing is identical over those years. The six-month and no-uplift states
are therefore byte-identical to production, and `deferred == no-uplift`
holds exactly through each deferral's window.

## 13. Unresolved economic judgement / owner decisions

* **UI default.** The handoff says "default remains Original timing —
  1 Jan 2027", but the live production default is **Deferred 6 months**
  (also asserted by the existing smoke test, the B-column default and the
  runtime's empty-key fallback). Because the deeper instruction is to change
  no unrelated production behaviour, the live default is preserved
  (`delayed_6m`, now labelled "Deferred 0.5 years (6 months) — 1 Jul 2027").
  Switching the default to Original timing is a one-line change
  (`FED_POLICY_OPTIONS.index(...)` in app.py plus the smoke-test
  expectation) if the owner wants the handoff reading.
* The six-month state's reader-facing label changed from
  "Deferred 6 months — 1 Jul 2027" to the handoff-required
  "Deferred 0.5 years (6 months) — 1 Jul 2027". State IDs, scenario names,
  path IDs and all computed values are unchanged.
* BEFU26 still has no synthetic policy counterfactual (unchanged; a separate
  owner decision, as the existing caption states).

# Q1 2026 actuals refresh and governed model replay — implementation report

Branch: `refresh/actuals-2026q1-and-reforecast` (from main `d7f8b8dea6c4f37df196b980d9fe9e82495952eb`)
Source workbook: `references/NLTF_model_input_sheet_actuals_to_2026Q1_complete1.xlsx`
SHA-256 `be951103cfa0fc4415583044397eea11982c2d83b0679bd97984cb0b0cf305a3`, 162,463 bytes.
Environment: Python 3.13.5, pandas 3.0.3, numpy 2.4.6, openpyxl 3.1.5 (Windows 11; Linux parity via CI replay fingerprint).
Authoritative production engines: PED **AR(1) GLSAR** (`ped_ar1`), Light RUC
`dynamic_RESID_GBR_n150_d1_lr0.05_w36` (`light_ruc_vnext`), Heavy RUC
`HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4` (`heavy_ruc_vnext`).

## What was treated as an actual

| Stream | 2026Q1 value | Status |
|---|---|---|
| Light RUC net km | 3,196,014,020 km (revenue $248,999,340.25; effective rate 77.909339 NZD/1,000 km) | **accepted_exact_actual** (Core Data N77/B77) |
| Heavy RUC net km | 1,039,372,457 km (revenue $334,926,318.92; effective rate 322.238979 NZD/1,000 km) | **accepted_exact_actual** (Core Data O77/C77) |
| Macro (GDP, deflator, population 5,361,300, unemployment 5.3%, CPI base Mar-26, petrol 269.8 / diesel 214.6 c/l) | quarterly official actuals / vintage-preserving transformations | accepted inputs for all streams |

## What remained provisional

The **PED 2026Q1 target (1,355.8193 km/person; petrol-only VKT
7,268,954,111 km)** is an MBU26 annual residual bridge allocated by the exact
Core Gross PED revenue share (`mbu26_residual_core_ped_share`). It is **not**
an independently observed actual. It:

- never entered the canonical fitting target column (`ped_inputs.parquet`
  keeps the 0.0 placeholder at 2026Q1);
- lives only in the governed sidecar
  `data/model_input_history/ped_provisional_bridge.json`
  (`eligible_for_refit: false`, `display_as_observed_actual: false`);
- is used solely as a Candidate-B recursive-history replay seed;
- is surfaced in `stream_vintage_status.csv` and the pack manifests as a
  provisional seed, not as an actual, with no public warning banner.

The Heavy 2026Q1 lead price (318.780337 real NZD/1,000 km) uses the
subsequently observed Q2 Core rate rebased to the Mar-26 CPI base:
**retrospective_history** vintage, recorded in `heavy_lead_vintage_audit.csv`.
The workbook's retrospective completion of the 2025Q4 lead placeholder was
recorded but **not** applied, keeping 2002Q1–2025Q4 value-identical. The
promoted Heavy vNext ensemble uses **no lead features** (governance "no
leads"), so the production replay is identical under retrospective and
real-time lead vintages (`heavy_lead_replay_diagnostic.csv`).

## Replay versus refit

**Replay (production candidate).** The existing promoted fitted states were
scored from the refreshed history with per-stream forecast origins. No
coefficient was re-estimated:

- the `ped_ar1` state was re-minted only to re-freeze
  `input_history_sha256`; beta, rho, last residual, latest actual (2025Q4),
  training window and every training fit are byte-identical
  (`promoted_state_invariance.csv`);
- Light/Heavy promoted state files and hashes are untouched;
- every governed scenario (Base, comparison, conflict severities, policy
  variants) replays directly through the P1.2 per-scenario Treasury path;
  no scenario reuses a Base result (`scenario_replay_lineage.csv`);
- current-policy overlays run once; exact VFM class composition unchanged;
- the FY2031–FY2050 post-model extrapolation rebuilds from the refreshed
  FY2030 anchor and the uncertainty fan re-mints from the new origin during
  the standard pack rebuild.

**Shadow refits (analysis only, `light_heavy_refit_comparison.csv`).** The
exact promoted recipes refit with the accepted Q1 actuals: Light window rolls
to 2017Q2–2026Q1 (max FY2026–30 activity move 1.78%), Heavy members roll one
quarter (max 0.69%). The single extra quarter yields no new out-of-sample
evidence for the challengers (they train on it); the honest new evidence is
the promoted states' h1 accuracy on 2026Q1 — Light APE 5.10–5.24%, Heavy APE
1.78–1.85% (`refit_h1_backtest_evidence.csv`). **No promotion: the promoted
states are retained.** PED refit is blocked (provisional bridge).

**No production coefficient changed.**

## First forecast quarter by stream

| Stream | Latest accepted exact actual | First forecast quarter |
|---|---|---|
| PED (Candidate A, production) | 2025Q4 | 2026Q1 |
| PED (Candidate B, decision-gated) | 2025Q4 exact + 2026Q1 provisional seed | 2026Q2 |
| Light RUC | 2026Q1 | 2026Q2 |
| Heavy RUC | 2026Q1 | 2026Q2 |

The global horizon axis stays anchored at the unchanged model training cutoff
(2025Q4 → 2026Q1 = H1); Light/Heavy publish H2–H20 as forecasts with H1 an
accepted actual, so the H1–H20 supported window and H21+ withholding are
preserved.

## FY2026 mixed actual/forecast construction

FY2026 (June year) per stream: 2025Q3 actual + 2025Q4 actual + 2026Q1
accepted actual (Light/Heavy) or forecast/provisional-seed (PED by
candidate) + 2026Q2 forecast. Pack rows now declare per-stream mixes:
Light/Heavy `Current-finalist FY nowcast (3 actual + 1 forecast)`, PED
`(2 actual + 2 forecast)` under Candidate A. FY2026 is never treated as four
forecast quarters.

## Changed FY2026–FY2030 values (Candidate A production replay)

Activity (`replay_impact_fy.csv`, basecase): Heavy +0.49% FY2026 then decays
(0 by FY2029); Light −1.26% FY2026 / +1.47% FY2027 then 0; PED exactly 0.

Decision-facing revenue (`front_end_impact.csv`, both packs, basecase):

| FY | Total NLTF before ($m) | after ($m) | change |
|---|---|---|---|
| 2026 | 4,626.29 | 4,619.41 | −0.149% |
| 2027 | 4,943.09 | 4,959.51 | +0.332% |
| 2028 | 5,559.17 | 5,559.37 | +0.004% |
| 2029 | 5,959.88 | 5,959.88 | ~0 |
| 2030 | 6,304.29 | 6,304.29 | ~0 |
| **FY2026–30 sum** | **27,392.72** | **27,402.46** | **+$9.7m / +0.036%** |

Largest stream movements: Light RUC revenue ±1.47%, Heavy RUC revenue
+0.49%, Total RUC +0.73%; PED revenue and Net FED 0 under Candidate A.

## Unchanged MBU26 and prior-history checks

- MBU26/official comparator values untouched (hybrid replacement lines only
  recompute where current-model activity feeds them).
- 2002Q1–2025Q4 canonical history value-identical across all three streams
  (`history_cross_check.csv` max relative drift 5.1e-16; the only recorded
  exception is the *unapplied* 2025Q4 lead completion above).
- Policy definitions, exact-VFM composition, lambda retirement, Heavy-BEV
  default-neutrality and the long-run structural methodology unchanged.
- The total historical NLTF actual line was **not** updated from this
  workbook (it lacks the MVR/TUC/refund/admin actual leaves; that update
  waits for the complete governed revenue-source contract).

## Remaining governance decision for PED

Candidate B (provisional replay-only) is fully evidenced but **not**
promoted: PED forecasts from 2026Q2 with the bridge seed pull PED activity
−4.35% in FY2026 and −1.68% in FY2027 (converged by FY2029), a first-order
PED revenue effect of ≈ −$92.8m FY2026 / −$133.6m across FY2026–30. Bridge
sensitivities (`ped_bridge_sensitivity.csv`): an equal Q1/Q2 residual split
would lift the FY2026 PED path +1.72% vs the selected Core-revenue share;
the prior-year seasonal share +2.00%. Activating Candidate B (or a future
exact petrol-only VKT observation via `--ped-mode accepted`, which requires
`--governance-approval`) is an explicit owner decision.

# Q1 2026 actuals refresh — validation report

Gate results for the refresh described in `implementation_report.md`.
Blocking tests live in `tests/test_actuals_refresh_ingestion.py` plus the
pre-existing parity/contract suites; artifact evidence is in this directory.

## Workbook gates — PASS

- SHA-256 matches the governed snapshot (`be951103…f305a3`); size 162,463 B.
- All seven sheets present; main sheet ranges A1:AK98 / A1:AW98 / A1:AL98.
- 97 continuous quarters (2002Q1–2026Q1) per stream; no duplicate
  stream/period keys (`workbook_inventory.json`, `workbook_schema.csv`).
- Sentinel 2026Q1 values match exactly (targets, revenues, effective rates,
  lead, bridge target/VKT/population/unemployment).
- Source map covers every populated model column: 39 PED + 49 Light +
  38 Heavy lineage rows (`source_lineage.csv`).
- Formula inventory captured (`workbook_formula_inventory.csv`); "Q1 2026
  Filled Rows" treated as a presentation duplicate, never ingested.

## History gates — PASS

- 2002Q1–2025Q4 value-identical in all three parquets (max relative drift
  vs the workbook history region 5.1e-16, `history_cross_check.csv`).
- 2026Q1 appended exactly once per stream; quarter sequence continuous.
- `target_lag_1`/`target_lag_4` at 2026Q1 roll exactly from 2025Q4/2025Q1.
- All positive-log fields finite for accepted rows; units declared in
  `canonical_raw_actuals.csv`.
- No forecast value relabelled as history; the PED provisional value never
  enters an estimation sample (fitting target stays 0.0).
- Feature parity of the centrally derived row vs the workbook's
  Excel-computed row: 110 comparisons, max rel diff 3.6e-13
  (`feature_parity.csv`; 4 PED fields suppressed by ped-mode governance).

## Identity gates — PASS

- Light and Heavy `revenue / km × 1,000` identities: zero residual (1e-9).
- GDP nominal × rebasing factor = real (exact); deflator solved consistently
  with official nominal +1.4% and real +1.0% q/q SA.
- PED target = VKT / population (bridge identity, exact in sidecar).
- PED annual residual bridge: 2025Q3+Q4 actual + Q1+Q2 provisional = MBU26
  FY2026 annual, zero residual (`q1_reconciliation.csv`).
- Cross-stream shared diesel price, Light-RUC price and unemployment agree
  across sheets at 2026Q1 (1e-12).
- Quarterly-to-annual reconciliation via the pack build's declared-unit
  annualisation (per-stream actual/forecast quarter mixes on every FY row).

## Governance gates — PASS

- PED provisional excluded from fitting: `ped_ar1` state latest_actual and
  train_window_end remain 2025Q4; AR(1) refit gate reproduces beta/rho and
  every training fit byte-identically.
- PED 2026Q1 never displayed as an observed actual (no historical_actual
  chart row; vintage table labels the seed provisional).
- Light/Heavy 2026Q1 carry accepted_exact_actual status and appear as
  historical actual rows.
- Retrospective Heavy lead clearly labelled (`heavy_lead_vintage_audit.csv`);
  the promoted Heavy state uses no lead features so no look-ahead can reach
  the production replay.
- No future target leakage: recursion seeds are actuals (or the governed
  Candidate-B PED seed, which must postdate the fitted latest actual and is
  enforced positive/never-fitted).
- `--ped-mode accepted` refuses to run without `--governance-approval`.

## Replay gates — PASS

- Promoted states carry no re-estimation (`promoted_state_invariance.csv`),
  stated precisely because one artifact hash did change by design:
  - the **Light and Heavy promoted-state files are unchanged**, byte for byte
    (`light_ruc_production.joblib`, `M1/M2/M3_production.joblib`), and their
    manifest hashes are untouched;
  - the **PED AR(1) state artifact hash intentionally changed**, solely because
    `input_history_sha256` was re-frozen to the refreshed canonical history.
    Its estimated content is byte-identical: `beta`, `rho`, `last_resid`,
    `latest_actual` (2025Q4), `train_window_start`/`_end`, `train_rows` and
    every entry of `training_fit_levels`. The runtime gate that re-derives the
    GLSAR from committed inputs returns delta 0.0.
  Runtime parity gates green (27 AR1/vNext parity tests).
- PED Candidate-A replay is byte-identical to the pre-refresh committed
  vintage (max rel diff 1.5e-16); Heavy 2.3e-15.
- All scenarios replay directly (Base, comparison, conflict low/medium/high,
  policy variants) via the P1.2 per-scenario Treasury path; the committed
  scenario-input replay mismatch gate passes with 0 mismatches; current
  policy applied once.
- Official comparator untouched; forecasts start at the per-stream origin
  (PED 2026Q1, Light/Heavy 2026Q2); replay-seed diagnostic PASS
  (40 patched supported, 0 genuinely missing, 0 reclassified).
- Windows local replay green; Linux parity via the CI replay fingerprint
  matrix (see PR checks).

## Runtime gates — PASS

- Both governed packs rebuilt through the canonical route (ensemble and
  AR(1)); completeness contract green with the new closed-vocabulary states
  (`superseded_by_accepted_actual` pass-state; stale forecast rows at
  accepted quarters are a blocking failure and none exist).
- All revenue leaves close (line reconciliation/formula residual frames
  rebuilt); FY2026–FY2030 impact fully reported (`front_end_impact.csv`).
- FY2031–FY2050 post-model extension rebuilt from the refreshed FY2030
  anchor; uncertainty fan re-minted from the new origin and agrees with the
  downloads (`runtime_pack_diff.csv`).
- No lambda or retired long-run path returned; conflict extract validation
  21/21; GDP sign-guard register regenerated; Streamlit deploy readiness
  PASS.

## Refit gates — PASS

- Light/Heavy challenger states are analysis-only (never written into the
  reproducibility packs; hashes recorded as `shadow_refit_not_promoted`).
- PED refit blocked; no production state changed without explicit promotion.

## Tolerances

No tolerance was widened to make the refresh pass. New checks introduced
their own tolerances (history cross-check 1e-12 rel; feature parity 1e-9;
identities 1e-9; no-op equivalence 1e-12), all tighter than or equal to the
repo's governed 1e-6 parity tolerance.

## Test stack

- `python -m compileall .` — PASS
- **Full local pytest: 977 passed, 0 failed** (50 skipped =
  requires_local_scratch; 41 deselected = e2e per pytest.ini)
- Workbook-ingestion + plug-and-play gates: 30/30 PASS
  (`tests/test_actuals_refresh_ingestion.py`)
- AR(1)/vNext parity: 27/27 PASS
- Replay-seed diagnostic: PASS; sign-guard register: regenerated
- Conflict scenario extract validation: 21/21 PASS
- Long-run evidence generator: PASS (0 short-run values changed vs the
  re-frozen baseline; retired constructor absent)
- Streamlit deploy readiness: PASS; AppTest smoke + engine switcher: 51/51
- Replay parity fingerprint minted locally (Windows); the Linux leg and the
  fresh clean-clone core suite run in the PR's CI checks
- Browser/e2e Playwright phase: deselected by pytest.ini; runs via the
  governed host runner (`scripts/verify_browser_host.ps1`) per AGENTS.md.

## Front-end smoke — PASS (host browser, port 8503)

Run against the rebuilt AR(1)/incumbent packs on the live app. Zero Streamlit
exception blocks; server log clean apart from the pre-existing
`use_container_width` deprecation notices.

The Revenue Outlook page renders this caption in the **default public view**
(a caption, not a warning banner, per the governance rule):

> Input-history vintage 2026Q1. **PED** actual to 2025Q4, forecast from 2026Q1
> (a provisional bridge exists for the next quarter; not an observed actual) ·
> **Light RUC** actual to 2026Q1, forecast from 2026Q2 · **Heavy RUC** actual
> to 2026Q1, forecast from 2026Q2.

That single line discharges the reviewer's first four checks: Light and Heavy
2026Q1 read as accepted actuals, both start forecasting at 2026Q2, PED 2026Q1
remains a forecast, and the provisional bridge is named as provisional rather
than shown as an actual.

The smoke also caught a real gap and it was fixed: the per-stream vintage was
present in the pack and manifest but **not surfaced anywhere in the UI**, so
spec §12's exposure requirement was unmet. The page now carries the caption
above plus an analyst-gated "Input-history vintage by stream" expander with
the `stream_vintage_status` table and its CSV download (lineage points at
`data/model_input_history`, never at the source workbook). Both are now
regression-gated by `tests/test_stream_vintage_exposure.py` (12 gates, both
engines) so the exposure cannot silently regress:

- pack publishes `stream_vintage_status.{csv,parquet}` with the per-stream
  cutoffs and origins;
- manifest `period_rule.stream_vintages` agrees with it;
- the caption text states every stream's seam and never labels PED 2026Q1 an
  actual;
- the caption is silent for a pack predating the seam (older packs render
  unchanged);
- FY2026 mixed-year labels are per stream — Light/Heavy
  `2025Q3; 2025Q4; 2026Q1` + `2026Q2` ("3 actual + 1 forecast"), PED
  `2025Q3; 2025Q4` + `2026Q1; 2026Q2` ("2 actual + 2 forecast"), every FY2026
  row flagged `nowcast_flag`;
- no stale quarterly forecast row survives at a quarter that is now an
  accepted actual, and PED 2026Q1 is absent from historical-actual rows.

Note on the quarterly Total-NLTF chart: its Actual line still hands over at
the FY2025/FY2026 boundary. That is the MBU26 annual-spine handover, which
this PR deliberately does not touch — the total historical NLTF actual line
needs the complete governed MVR/TUC/refund/admin contract, which this workbook
does not carry.

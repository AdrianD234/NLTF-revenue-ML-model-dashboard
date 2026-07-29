# Restoration source audit — long-run presentation and uncertainty fan

Everything being restored was removed deliberately and traceably. This audit
records what was removed, where, why, and what the restoration builds on, so
the change is a reconstruction from governed sources rather than a revert.

## 1. The uncertainty fan

- **Removed by:** commit `417f34a` ("Hide Revenue Outlook uncertainty fan",
  1 Jul 2026). **Last visible at:** `3109748` (its parent) — the visual
  baseline for this restoration.
- **What was removed:** call sites only, in two places in `app.py`:
  1. the primary Revenue Outlook layout — `st.columns([0.64, 0.36])` with the
     Total path chart left and `_render_revenue_outlook_fan_card(...)` right;
  2. the source-architecture page — a two-column layout whose right card
     rendered `_source_uncertainty_figure(...)`.
- **What survived:** the renderers themselves
  (`_render_revenue_outlook_fan_card`, `_source_uncertainty_figure`) and the
  full data path: `fan_band_rows` and `fan_availability` are still built by
  `build_current_revenue_outlook_runtime_pack` (`_mbu26_archived_fan_band_rows`,
  `_current_finalist_backtest_fan_band_rows`, `_scenario_spread_fan_band_rows`),
  written to both governed packs, and loaded by `load_revenue_outlook_pack`.
  Restoration is a reconnection, not a rebuild.
- **Governed fan sources (already implemented, in priority order):**
  current-finalist empirical backtest error; archived official forecast error;
  scenario spread (labelled as a range, never as a probabilistic interval).
- **Tests to flip:** `tests/test_playwright_dashboard.py` and
  `tests/test_streamlit_smoke.py` currently assert the fan is absent
  (changed in `417f34a`); `tests/test_playwright_frontend_interactions.py`
  dropped one interaction.

## 2. Why Current paths stop at FY2030

The P0 horizon governance (merged PR #4) withheld decision-facing Current
values beyond H20/2030Q4 (quarterly) and FY2030 (annual) because the retired
long-run Light RUC construction was shown to be divergent: it divided a
growing conventional forecast by a conventional share approaching zero,
implying a Light RUC pool of ≈185.8 billion km by FY2050 — ≈3.9× the VFM
pool. The withholding was a correct response to a broken constructor, not a
statement that no long-run view should exist.

- The governed constants: `EXTENDED_EVIDENCE_MAX_HORIZON = 20`,
  `LAST_DECISION_GRADE_QUARTER = "2030Q4"`,
  `LAST_DECISION_GRADE_ANNUAL_FY = 2030` (`light_fleet_allocation.py`).
- The raw model outputs never stopped: the committed
  `raw_quarterly_forecast_audit` layer carries H1–H100 (2026Q1–2050Q4) for
  all three streams and both governed scenarios, `decision_facing=false`.
- MBU26 official rows always retained their own FY2055 source horizon.

**This restoration does not reopen P0.** Quarterly emission stays H1–H20.
The FY2031–FY2050 layer is a NEW, separately named construction
(`post_model_extrapolation`) with an explicitly non-divergent Light RUC rule:
anchor at the corrected FY2030 pool, grow by the exact vendored VFM total-pool
index, allocate by exact VFM shares. The vendored table
(`data/vfm_202405/vfm_vkt_shares.csv`) carries absolute per-class million-km
pools through 2050, so the index needs no new source data.

## 3. The public horizon banner

- **Rendered by:** `_render_forecast_horizon_support_note(chart_rows)` at the
  top of the Revenue Outlook page (app.py:4349 at branch point), via
  `warning_panel`.
- **Why it exists:** honest governance prose for the H1–H12 / H13–H20
  distinction, added alongside the P0 horizon work.
- **What changes:** the banner leaves the public page. The metadata it
  narrates (`horizon_scope`, `horizon_zone`, first/last horizon, per-state
  quarter counts, availability status) stays in downloads, hover labels where
  already public-worded, and audit tables. Tests that require the banner flip
  to requiring the metadata without the banner.

## 4. The composition slider FY2030 cap on MBU26

- **Cause:** `cached_revenue_outlook_selectors` computes
  `stack_fy_bounds = _revenue_line_fy_bounds(stack_components)` over the
  WHOLE stack frame, before any source is selected (app.py:707). The slider
  at app.py:4855 then uses those global bounds for every source. Because the
  Current rows stop at FY2030 and dominate the frame's shape, the bound
  inherited by `MBU26 official` is FY2030 despite its rows running to FY2055.
- **Fix shape:** select source first; filter stack components to that source;
  derive min/max FY from the filtered frame; build the slider from those
  bounds; clamp/reset `st.session_state` when the source changes.

## 5. Interaction with the P1.1 completeness contract (this branch must extend it)

P1.1's governed inventory declares Current annual coverage FY2025–FY2030 and
its completeness engine marks a decision-facing Current value beyond the
cutoff as `formula_invalid` ("a value exists beyond the governed horizon").
That gate now runs blocking at pack build and pack load. Adding FY2031–FY2050
decision-facing rows therefore requires extending the governed contract with
a new segment — `post_model_extrapolation`, FY2031–FY2050, its own horizon
rule and value_status — rather than bypassing or weakening the existing
econometric-segment rules. Quarterly rules are untouched.

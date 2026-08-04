# Layer diagnosis — Fleet efficiency / PT mode shift FY2031 reset

Starting SHA `10f4e36edb9c769eaf33b81fc6388af059f261db` (== origin/main at diagnosis time).
Evidence: `baseline_factor_matrix.csv` (both engines, Base case, FY2026/2030/2031/2040/2050).

## Layer map (12 layers, section 2 of the handoff)

| # | Layer | Finding |
|---|-------|---------|
| 1 | Promoted pack | `revenue_line_reconciliation` and `revenue_chart_rows` carry every Current series 2025–2050, post-model rows labelled `forecast_segment == post_model_extrapolation` (FY2031–FY2050, 1600 line rows). Not the break. |
| 2 | PED bridge rows | `ped_revenue_bridge_audit` ends at **FY2030**: `base_litres_per_100km` and `ped_rate_nzd_per_litre` exist only FY2026–FY2030 (2 source paths × 5 FYs). **This is the root cause.** |
| 3 | Sensitivity output | `revenue_sensitivity_impact_audit_frame` (model_dashboard/revenue_outlook.py) computes `adjusted_litres = base_litres_per_100km × factor`. With litres NaN for FY2031+, `ped_volume`/`gross_ped_revenue` audit rows are silently skipped: their audit coverage is 2026–2030 while every activity series reaches 2050. `_delta()` maps the NaN adjusted PED revenue to a **zero** ped_delta, so all FED/NLTF rollups revert to baseline at FY2031 under Fleet-only (ratio exactly 1.0 from FY2031). |
| 4 | EV/PHEV composition | Applied multiplicatively after the sensitivity layer (`cached_scenario_overlay_rows`); preserves whatever ratio the sensitivity produced. Not a break. |
| 5 | Post-model extrapolation | Already inside the pack before the sensitivity layer runs (`_replace_post_model_rows` only swaps candidates). Ordering is NOT the defect — the audit sees FY2050 rows and adjusts activity series through FY2050 already. |
| 6 | Line reconciliation | Adjusted via the same audit; inherits the same 2030 truncation for PED volume/revenue. |
| 7 | Formula residuals | Recomputed from the adjusted line (`revenue_formula_residual_frame`), so they close — around a path that is wrong for FY2031+. |
| 8 | Policy runtime | `_materialised_policy_overlay_rows` returns `None` for any non-default sensitivity key → reference pipeline runs. Cannot serve stale default rows while a lever is active. Not a break. |
| 9 | Canonical view | `cached_revenue_outlook_view` consumes the sensitivity frames directly; no separate FY gate. Inherits the audit truncation. |
| 10 | Quarterly coverage | Native quarters are scaled by the annual adjusted/baseline ratio inside `_apply_sensitivity_audit_to_frame`; derived quarters are built from the FINAL annual rows (`_filter_series_rows_with_fallback`). Inherits the fix automatically once the annual audit reaches FY2050. |
| 11 | Plotly rows | Chart rows patched from the same audit; no chart-only transformation exists. Inherits. |
| 12 | A/B comparison | `cached_scenario_comparison_paths` reads `cached_revenue_outlook_view` per side (commit d874388). Inherits. |

## Proven mechanism of the visible reset

For Fleet efficiency (e.g. Custom 10%):

- FY2026–FY2030: `ped_volume` ratio = 0.9, …, 0.59049 = (1−0.10)^n — exact.
- FY2031–FY2050: **no audit row exists** for `ped_volume`/`gross_ped_revenue`
  (bridge litres/rate NaN), ped_delta = 0.0, so PED volume, PED revenue and all
  revenue rollups return to the unsensitised post-model path. Ratio 1.0 at
  FY2031/FY2040/FY2050 on both engines.

For PT mode shift (Med 0.5%):

- Activity series (`light_petrol_vkt`, `light_ruc_net_km`, `light_bev_ruc_net_km`,
  `phev_ruc_net_km`, `ped_vkt_per_capita`) compound continuously with **no**
  FY2031 seam reset (0.995 at FY2030 → 0.990025 at FY2031 → 0.900087 at FY2050).
- But `ped_volume`/`gross_ped_revenue` hit the same NaN-litres skip, so the PED
  side of the PT effect vanishes at FY2031 while the RUC side continues —
  a half-applied total.
- Start year is FY2030 (`SENSITIVITY_PT_START_FY = 2030`), so FY2026–FY2029
  are untouched (exponent 0). Owner has changed this contract to FY2026.

There is **one** break for the seam (layer 3's dependence on layer 2's FY2030
horizon) plus **one** start-year contract change (PT FY2030 → FY2026). No
chart-only patch, cache-key default, or forecast-segment filter is involved.

## Uncertainty bands (section 6 input)

`cached_uncertainty_band_rows` is keyed on series/policy/uptake key but NOT on
the sensitivity key, so baseline 50/80% bands keep rendering around an adjusted
central path (visible in the reporting screenshot). Rollup series cannot be
transformed exactly without component-level draws, so the honest treatment is
the contract's option 2: withhold annual bands while Fleet/PT is non-Off, with
the governed note.

## Fix architecture (implemented on this branch)

At the single canonical boundary (`revenue_sensitivity_impact_audit_frame`):

1. Where bridge litres/rate are unavailable (FY2031+), derive the
   scenario-specific pre-sensitivity baseline directly from the line rows:
   `baseline_intensity = 100 × ped_volume ÷ light_petrol_vkt`,
   `effective_ped_rate = gross_ped_revenue ÷ ped_volume`.
   Every FY is computed from that FY's own baseline × the cumulative factor —
   never recursively from the previous adjusted year.
2. Factors move to `exp(n · log1p(−r))` with `n(FY) = max(FY − 2025, 0)`.
3. `SENSITIVITY_PT_START_FY` becomes `REVENUE_FIRST_FORECAST_FY` (2026).
4. Post-model provenance stamps (segment, exponent, factor, rates) are added
   to the audit rows.
5. Annual modelled-uncertainty bands are withheld while Fleet/PT is non-Off.

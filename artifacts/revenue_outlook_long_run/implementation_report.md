# Revenue Outlook long-run restoration

## What was restored, and what was deliberately NOT restored

Restored: the Current forecast beyond FY2030, the uncertainty fan, the
source-specific composition horizons, and a clean public page.

NOT restored: the constructor that caused the FY2030 cutoff. The retired
rule divided a growing conventional forecast by a conventional share
approaching zero, implying ~185,800 million km of
Light RUC by FY2050. The replacement is a structural total-pool index:

    pool_fy = corrected_pool_2030 x (VFM_Base_pool_fy / VFM_Base_pool_2030)

allocated by the exact vendored VFM shares. No division by a share
appears anywhere, and a test bans the idiom by pattern.

## Headline results

- Base Total NLTF: FY2030 $6,415.2m -> FY2050 $17,264.7m
- Comparison Total NLTF: FY2030 $6,526.3m -> FY2050 $18,392.0m
- Base Light RUC pool FY2050: 52,461 Mkm (1.093x the VFM pool, 0.282x the retired pathology)
- Short run: 0 values changed across 4612 pre-existing rows
- Seam continuity: worst step 5.45%
- Formula closure: 520 checks, worst residual 3.64e-12

## Uncertainty presentation

The two horizons are not the same kind of object. An empirical 50/80
band is calibrated from realised forecast error; extrapolated past the
model's own forecast it would assert something it cannot support. So:

- empirical sources (backtest error, archived official error) are
  TRUNCATED at FY2030;
- the scenario spread continues, labelled a long-run scenario envelope,
  drawn at reduced opacity behind a seam marker;
- a scenario spread is never called a confidence interval;
- the light-blue MoT VFM fast-slow composition range keeps its own
  colour and meaning, separate from the gray forecast fan.

## Composition horizons

The FY2030 cap on MBU26 had two causes, both fixed:

1. the official line/stack rows were truncated to the CURRENT runtime
   cutoff at pack build; they now run to the official source horizon;
2. the slider bounds were computed over the whole stack frame BEFORE a
   source was chosen; they are now derived after selection, with
   session-state clamping when the source changes.

| source | first FY | last FY |
|---|---|---|
| Current finalist Base case | 2001 | 2050 |
| Current finalist High population/comparison | 2001 | 2050 |
| MBU26 official | 2001 | 2055 |

## Evidence in this directory

- `restoration_source_audit.md` - what was removed, where, and why
- `short_run_unchanged_check.csv` - CSV-vs-CSV exact identity
- `fy2030_fy2031_continuity.csv` - seam steps vs the prior year's step
- `post_model_extrapolation_activity.csv`, `..._revenue.csv`
- `anchor_index_level_audit.csv` - anchor, index and level SEPARATELY,
  with the raw path's own level shown to prove it was not republished
- `light_ruc_long_run_guard.csv` - pool vs the retired pathology
- `formula_reconciliation.csv` - every long-run aggregate closes
- `fan_rendering_audit.csv` - which band claims which basis over which years
- `source_horizon_audit.csv` - per-source horizons, proven independent

## A note on the short-run comparison basis

The identity check is CSV-against-CSV. main's own CSV and parquet
already disagree on 26 annual rows by one ULP (max 1.82e-12, relative
2.2e-16) purely from CSV text precision - a pre-existing serialisation
artifact, not a value difference. Comparing the same serialisation on
both sides keeps the assertion exact instead of tolerance-based.

# Phase 0 preconditions — feature/prebu26-default-official

Recorded: 2026-08-21

## Git state

- Starting main SHA: `bf61160d86499a5d39d9dbef47e85a4b9b563d3d` (merge of PR #34,
  "Add governed 6-36 month 12c/L deferral scenarios")
- `origin/main` == branch base at branch time; working tree clean.
- Branch created: `feature/prebu26-default-official` from `bf61160`.
- The post-merge CI run for PR #34 (run 32416715815) was in progress at branch
  time; no commit is made on this branch until it completes green.

## Source workbook

- Path: `references/PREBU26.xlsx`
- Size: 44,469 bytes
- SHA-256: `f69985432b34271d5868267d78b77ad2c746563788011b445715e4f58a25728b`
- Single worksheet: `PREBU`
- Layout: year header row 1 (`YE June`), Period status row 2, labels in column 1
  (identical to the BEFU26 governed layout).
- Period/status blocks (workbook status row is authoritative):
  - `ACTUAL`: FY2001–FY2026 (26 columns) — annual actuals now run through FY2026.
  - `ST_FORECAST`: FY2027–FY2031 (5 columns)
  - `LT_FORECAST`: FY2032–FY2055 (24 columns)
- Git status at branch time: untracked, ignored by the blanket `*.xlsx` rule; a
  per-file exception (`!references/PREBU26.xlsx`) is added by this branch,
  matching the `references/BEFU26 revenue forecast.xlsx` precedent.
- Naming: the release is officially PREBU26 (a PREFU-round release referred to
  as PREFU26 in some task text; PREBU26 is the governed identifier used
  throughout).

## Scope (non-negotiable)

- PREBU26 becomes `is_latest` and `is_default_comparator` only.
- BEFU26 remains `is_default_bridge_vintage` and
  `is_default_long_run_shape_vintage`; BEFU26 and MBU26 remain registered and
  selectable prior vintages.
- No Current forecast value, fitted model, coefficient, training cutoff,
  scenario path, replay cache or uncertainty value may move.

## Runtime

- Python: 3.13.5 (`.venv\Scripts\python.exe`) for materialization and local
  iteration; governed numerical disagreements are settled in the `ci/`
  container (Python 3.11), per AGENTS.md.

## Pinned pre-bridge-refresh baseline

The bridge-assumption vintage does NOT change on this branch (BEFU26 before and
after), so the pinned baseline is the committed chart rows at the branch base
`bf61160` with bridge BEFU26. Bridge impact against this baseline must be zero
for every matched Current row; this doubles as the invariance gate that no
Current value moved.

- `pre_bridge_refresh_chart_rows_ensemble.csv` SHA-256:
  `eb5176d5ec78d52a603f405d5730b7e6212565b0d98598853b6b226936791749`
- `pre_bridge_refresh_chart_rows_ar1.csv` SHA-256:
  `014899adb0a9def81dd7740f6c84d5b0c155f074eee18e9aab537f6aff69e8df`

## Published source residuals (recorded, not corrected)

PREBU26 `gross_ruc_revenue` fails to close to its class leaves net of refunds
in every ST_FORECAST year — the same published closure-defect family as MBU26
and BEFU26 (which show it over FY2027–FY2030; PREBU26's ST block extends to
FY2031):

- FY2027: +0.619398 $m
- FY2028: +0.472877 $m
- FY2029: +0.368256 $m
- FY2030: +0.389594 $m
- FY2031: +0.431551 $m

Values are retained exactly as supplied; nothing is force-balanced.

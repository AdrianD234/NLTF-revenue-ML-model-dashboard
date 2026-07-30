# Phase 0 preconditions — feature/official-vintage-befu26

Recorded: 2026-07-31

## Git state

- Starting main SHA: `7c015c0a15ea27f0fcf65defdf43acb019cbde5d` (merge of PR #10)
- `origin/main` == local `main` at branch time; working tree clean.
- Ancestor confirmations:
  - PR #9 (Revenue Outlook long-run/fan restoration): merge `d7f8b8d` — ancestor of main.
  - PR #10 (Q1-2026 actuals refresh + governed replay): merge `7c015c0` == HEAD at branch time.
  - P1.1 unit/completeness contracts and P1.2 direct per-scenario Treasury replay are on main
    (artifacts/p1_unit_completeness, artifacts/p1_direct_macro_replay tracked; commits `64675b5`,
    `4a7c6c8`, `cf2ea2d`, `3c67203` all ancestors).
- Branch created: `feature/official-vintage-befu26` from `7c015c0`.

## Source workbook

- Path: `references/BEFU26 revenue forecast.xlsx`
- Size: 51,133 bytes
- SHA-256: `7d6e5b19119ca8b5272ca2205c0735719033d82484ce674cfb595e6f45d085ff`
  (matches the expected uploaded-copy hash exactly)
- Git status at branch time: untracked, ignored by the blanket `*.xlsx` rule in `.gitignore`
  (a per-file exception is added by this branch so the governed source is vendored, matching
  the existing `references/NLTF_model_input_sheet_actuals_to_*.xlsx` precedent).

## Runtime

- Python: 3.13.5 (`.venv\Scripts\python.exe`)
- Platform: Windows 11 Home 10.0.26200

## MBU26 pack baseline hash inventory

`data/revenue_model_source_pack/mbu26_annual_spine/` — SHA-256, size, name captured at branch
time in [mbu26_pack_baseline_hashes.txt](mbu26_pack_baseline_hashes.txt). These files must be
byte-identical at the end of this branch (invariance gate, Phase 13).

# Reproduction of the app-boot write, before any code change

## Method

A disposable clone of `origin/main` at `46d1f87`, outside the branch worktree and
outside the primary checkout. Verified clean: `git status` empty, exactly the
three tracked CSVs on disk, both evidence packs present.

Driven by `scripts/check_app_boot_read_only.py`, which starts a genuine
`streamlit run app.py` server and drives it with a real Chromium session. A
browser is required: Streamlit does not execute the script until a websocket
client connects, so an HTTP GET proves nothing. AppTest was deliberately *not*
used — it runs inside pytest and inherits the `tests/conftest.py` chart-source
redirect, which is exactly what hid this path.

Normal application configuration, nothing suppressed:

- `NLTF_CHART_SOURCE_OUTPUT_DIR` unset (the test-only override)
- `DASHBOARD_ENGINE_DEFAULT` unset, so the app booted on AR(1)
- `REVENUE_OUTLOOK_CACHE_WARMER` unset, so the normal local warmer ran

## Result: reproduced exactly

`git status` went from clean to:

```
 M artifacts/chart_sources/r2_ladder_summary.csv
```

The PED calibration R-squared substitution:

```
0.5591936636031876  ->  0.5803595524485978     (current_grid_operational_pooled)
0.9230110422702978  ->  0.9448430187011027     (schiff_paper_horizon_mean)
```

Chart-source files on disk: **3 before, 22 after**.

## Findings against the questions asked

- **Which files change.** Only `r2_ladder_summary.csv` among the three tracked
  files. `r2_reproducibility_gap_register.csv` and `r2_training_fit_detail.csv`
  were **not** modified. This confirms the operator's observation, and it held
  across two independent runs, one of which also loaded the Revenue Outlook page
  and performed a rerun. Nineteen further CSVs were created; all are gitignored.
- **Does it survive whitespace normalisation.** Yes.
  `git diff --numstat --ignore-all-space` reports `2 2` — two insertions, two
  deletions. A genuine value change, not a line-ending artefact.
- **What triggers it.** Initial app boot alone. The first run failed to click a
  navigation control and still reproduced the defect in full, before any page
  navigation occurred.
- **Engine switching.** The app has no engine selector on this branch:
  `model_dashboard/engine.py:84` defines `render_engine_selector` but `app.py`
  never calls it, so the engine is chosen by `DASHBOARD_ENGINE_DEFAULT`. Engine
  behaviour was therefore exercised by a separate host run with
  `DASHBOARD_ENGINE_DEFAULT=ensemble`.
- **Cache warmer.** Not implicated. The warmer starts after the pack is already
  loaded. The post-fix check was run with the warmer both on and off; the
  warmer-on case is the one that matters and it is green.

The clone was discarded afterwards. The branch worktree was untouched throughout
the reproduction, and nothing incorrect was committed at any point.

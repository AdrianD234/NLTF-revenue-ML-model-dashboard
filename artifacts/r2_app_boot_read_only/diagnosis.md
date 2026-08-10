# Diagnosis: why normal app startup published governed R-squared evidence

## Root cause, in one sentence

`load_evidence_pack` materialised the chart-source tables as an unconditional
side effect, so the act of *reading* an evidence pack was also the act of
*publishing* governed evidence — and the app reads its pack on every cold start,
under the AR(1) default engine, while the committed tables carry the ensemble
identity.

## The three separate facts, kept separate

These were conflated in earlier discussion and are worth stating apart.

1. **Engine identity is real, not drift.** The two R-squared pairs are two valid
   engine identities, reproducible on demand:

   | | operational pooled | paper horizon mean |
   | --- | --- | --- |
   | ensemble (governed) | `0.5591936636031876` | `0.9230110422702978` |
   | AR(1) | `0.5803595524485978` | `0.9448430187011027` |

   Neither is wrong. Neither was changed by this work.

2. **Test writer isolation** was fixed previously: `tests/conftest.py` redirects
   chart-source output to a per-worker, per-pid scratch directory, and the
   governed-tree gate catches leaks. That fix was correct and is untouched.

3. **App-boot governed-file mutation** is what remained, and is what this change
   closes. It was invisible precisely *because* of (2): every test process saw
   the redirect, so no test could observe what a real `streamlit run app.py`
   does. `docs/FOLLOW_UP_PED_R2_DRIFT.md` lines 178-181 recorded the structural
   gap without connecting it to the application path.

## Answers to the traced questions

1. **Which startup function invokes the writer.** `main()` -> `load_active_run`
   -> `cached_load_evidence_pack` -> `load_evidence_pack` ->
   `write_chart_source_tables`. Full chain in `call_graph.md`.
2. **Where in startup.** During evidence-pack loading, before any page is
   constructed. Not the Revenue Outlook cache warmer, not page construction, not
   another startup cache. Confirmed empirically: initial boot alone reproduced
   it, with the warmer both enabled and disabled.
3. **Which engine is active.** `ar1`, because `DASHBOARD_ENGINE_DEFAULT` is
   unset in normal local and deployed operation.
4. **Why AR(1) and not ensemble.** `engine_default()` hard-defaults to `ar1`;
   the canonical tables were promoted from the ensemble pack. Two populations of
   writers shared one destination and last-writer-wins decided the number.
5. **Does the app need the files to render?** No. It recomputes in memory. The
   only read is a file *count* for a status card.
6. **Does the app already hold the values in memory?** Yes —
   `r2_ladder_summary_frame(loaded.data, ...)` at `app.py:5383`. The on-screen
   value is engine-specific and stays engine-specific.
7. **Which command should promote canonical chart sources?** None existed. That
   was the structural hole; `scripts/promote_chart_sources.py` fills it.
8. **Does any non-test consumer expect startup to mutate the tracked files?**
   One did: `tests/test_playwright_dashboard.py` read
   `overview_finalist_forecast_accuracy.csv` from the tracked tree, relying on
   the running server to have written it. That is a test reading the app's
   output, not a product requirement; it now generates what it needs. No
   application feature depends on the write.
9. **Can the deployed Databricks App write these files, and is it useful?** It
   could, and it was not useful — merely incidental. Verified by probing the
   built bundle: startup is now read-only there too.

## Why this is a side-effect removal, not a model revision

No calculation changed. `build_chart_source_tables` and the R-squared
definitions are untouched; only *whether and where* the result is written moved.
The policy-runtime repin proof compared 200 governed frames cell by cell across
both engines and all nine policy states and found zero movement — only
provenance keys changed. See `governed_value_non_movement.csv`.

## Stop conditions checked, none triggered

The dashboard does not require these writes to render; the ensemble definition
is unchanged; no R-squared value was altered; no calibration row or formula
moved; no central forecast or revenue value moved; the uncertainty pack was not
rebuilt; no tolerance or exception was introduced; the fix prevents the write
rather than restoring the file afterwards; the real host-process check is green;
the Databricks app does not need writable governed evidence; the pack rebuild
moved no governed frame; and the writer distinguishes engine identities by
explicit argument, requiring no methodology decision.

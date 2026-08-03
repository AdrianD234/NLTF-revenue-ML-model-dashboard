# Validation — Revenue Outlook workshop release

Everything below was run on the integration branch, on Windows 11, Python
3.13.5, NumPy 2.4.6, pandas 3.0.3. Where a claim is not fully established, it
says so rather than rounding up.

## Targeted suites

| Suite | Result |
|---|---|
| `test_revenue_outlook_policy_runtime.py` (C, incl. `slow` parity) | **52 passed** in 4:26 |
| `test_revenue_outlook_ui_slim_2050.py` (A) + `test_revenue_outlook_series_coverage.py` (B) + integration | **135 passed** in 1:17 |
| `test_revenue_outlook_workshop_integration.py` (new, 37 tests) | included above, all pass |
| `test_revenue_chart_layers.py`, `test_quarterly_disaggregation.py` | 32 passed |

The C suite deserves a note. It initially reported **4 failures**, and they
were real:

`test_every_materialised_state_equals_the_reference_pipeline` computes its
expected value by calling `app.cached_scenario_overlay_rows` — the very
function the integration taught to answer from the pack. The test had become a
comparison of the pack against itself. A `reference_pipeline` fixture now
switches the fast path off for those comparisons, exactly as the builder does.
With the test made honest again it found two defects (a dropped official
vintage, and an emptied EV-uptake audit), both fixed and both described in
`implementation_report.md`. The 52-pass result above is after those fixes.

## Pack rebuilds

Order: replay caches → quarterly display → policy runtime.

| Pack | Action | Idempotency |
|---|---|---|
| Replay cache (ar1, ensemble) | **not rebuilt** | Both governed staleness gates report `ok` against the integrated tree; their digests do not cover `app.py`, so nothing invalidated them. Verified, not assumed. |
| Quarterly display | rebuilt ×2 | byte-identical both times, **and identical to the committed pack** |
| Policy runtime (both engines) | rebuilt ×2, last | **byte-identical across two builds on both engines** |

The policy runtime had to be rebuilt three separate times as defects were
found; the byte-identity claim above is from the final pair, run strictly
sequentially with the source tree frozen.

**B's quarterly pack was deliberately not added to the policy-runtime digest.**
The policy runtime does not consume it. B's *code* is covered transitively
because `revenue_outlook_series_coverage` is hashed into `code_module_hashes`
when imported during the build, which is the real dependency. The application
validates both packs independently.

No governed tolerance was widened anywhere in this PR.

## Preservation

`preservation_matrix.csv` — 274 baseline digests frozen from `main` before the
merges, re-derived from the integrated tree by the same rules.

**270 unchanged. 4 changed.** All four are replay-cache *manifest* entries
(`manifest.json` and `source_digest`, both engines), moved by C's `rate_paths`
edit entering the source digest. The cached frames' own `output_hashes` are
**unchanged** on both engines — the replayed values did not move.

Unchanged, on both engines: Actuals, Current Base, High population/comparison,
conflict paths, BEFU26, MBU26, every pack detail frame, all nine fitted-state
blocks, the Q1-2026 governance metadata, the uncertainty rows and the default
scenario-key digest.

## Other evidence, all passing

| File | Result |
|---|---|
| `quarterly_reconciliation.csv` | 3/3 — 2,093 derived annual groups reconcile, zero negative quarters, terminal quarter within 2050Q2 |
| `quarterly_reconditioning_preservation.csv` | 6/6 — snapshot `decision_facing=false`, `PROHIBITED`, hash-pinned, no production reader in `model_dashboard/*.py` **or `app.py`**, evidence in Parquet |
| `no_uplift_scope_audit.csv` | 17/17 — no activity or non-fuel series is inside the rate-priced scope |
| `session_migration_audit.csv` | 8/8 — retention, VFM audit, three uptake bases, out-of-horizon FY marker and unknown policy state all handled |
| `policy_state_parity.csv` | 18/18 states materialised |
| `policy_band_dependency_audit.csv` | **160/160 "band follows central"** — the set of FYs where a band moves equals the set where its central path moves |
| `official_light_petrol_vkt_audit.csv` | 73 rows: 25 BEFU26, 25 MBU26, 23 Actual, each with lineage to its own vintage file |

## Performance

Measured in a real browser against a locally served build. The first harness
carried a 2.5 s artefact (a status-widget probe that blocks when a rerun is too
fast to paint one); the numbers below are from the corrected harness.

| Metric | main `48a499b` | Integrated | |
|---|---|---|---|
| Cold Revenue Outlook, first plotted values | **47.06 s** | **8.72 s** | 5.4× faster |
| Cold app first paint | 2.31 s | 2.31 s | unchanged |
| Warm navigation p95 | 2.54 s* | 1.12 s | |
| **Policy switch p95** | **41.39 s** | **0.999 s** | |
| no-uplift render | **crashed** | 0.99 s | |
| Annual/quarterly switch p95 | not measurable* | 1.03 s | |
| Expand/collapse p95 | control did not exist | 1.00 s | |
| Console errors | 2 (pre-existing 404) | **0** | |

\* the `main` warm figure carries the same 2.5 s harness artefact and is not
directly comparable; the policy-switch and crash rows are unaffected because
they exceed the artefact by an order of magnitude.

Every warm interaction now sits at ~1.0 s, which is this page's Streamlit rerun
floor — a plain navigation costs the same as a policy switch. Against the
stated targets: the policy switch meets `p95 <= 1.0 s`; navigation (1.12 s),
grain (1.03 s) and expand (1.00 s) sit at or a fraction above it, at the floor
rather than in application work. The critical failure condition — a return to
multi-second policy switching — is not met: **41.4 s → 1.0 s**, and the state
that previously did not render at all now renders in under a second.

Cold server start remains hosting-dependent at 8.7 s for the first Revenue
Outlook plot, reported honestly rather than tuned away.

## Browser acceptance

22/25 at 1920×1080 and 22/25 at 1440×900, plus a dedicated **policy-switch
proof at 7/7** that closes the one check previously recorded as unverified.

The step-12 failure was a harness defect. The reader used `gd.data[i].y`, the
user-supplied trace spec, which can be empty for a drawn trace; the corrected
reader uses `gd.calcdata` and reports that as its source, confirming the values
were there all along. It then proves, on real plotted numbers:

- 3/3 policy-sensitive central paths change under published → no-uplift;
- 4/4 selected 50%/80% bands change with them;
- net MVR is unchanged across the switch (10 traces, 0 moved);
- returning to published restores the original values exactly, for both net MVR
  and Total NLTF;
- zero console errors.

No application value was changed to satisfy the test.

## Series coverage — Light petrol VKT

The question was whether the final annual Current `light_petrol_vkt` rows exist
through FY2050 after the post-model and policy layers. **They do not.** Run
through the integrated annual path under all three policy states, the Current
traces cover **FY2026–FY2030** (n=5) while BEFU26 and MBU26 cover FY2026–FY2050
(n=25). The series is built from the PED bridge, whose governed econometric path
ends at FY2030.

Nothing was invented. The supported cutoff is kept — the Current quarterly
derivation runs 2025Q3–2030Q2, matching its annual anchor exactly, while the
official comparators' quarters run to 2050Q2 — and a **series-specific coverage
note** now states it on the chart: which fiscal year the Current path is
governed to, which fiscal year the officials publish to, that the gap is an
absence of a governed path rather than a forecast of zero, and that the line is
not extrapolated to meet them.

The note is derived from the plotted rows rather than hard-coded per series, so
any series with short Current coverage declares it, and a series whose Current
path reaches the horizon stays silent — tested both ways.

Restoring the official rows is what made this gap visible for the first time: a
reader previously saw no official line at all on this series.

## What was NOT run

Honesty matters more here than a full tick-list:

- **The first complete pytest run was invalid and has been discarded.** It
  reported three failure clusters in the `test_c*` region. The cause was
  contention I created, and the timestamps show it:

  | | |
  |---|---|
  | Policy build pair finished | **17:12:31** |
  | Full suite ran | ~17:44 – **17:54:45** |
  | `artifacts/chart_sources/r2_ladder_summary.csv` written | **17:46:23** |

  The policy builder was **not** running during the suite — it had finished 32
  minutes earlier, so it cannot be the explanation. What *was* running
  concurrently were three `pytest --collect-only` invocations and a
  `pytest tests/test_conflict_fuel_paths.py tests/test_conflict_gdp_paths.py`
  run I used for diagnosis, in the same worktree. `r2_ladder_summary.csv` — a
  file the tests write, and the subject of the known deferred write-isolation
  defect — was rewritten at 17:46:23, in the middle of the full run.

  Two pytest processes sharing one worktree and one artifacts directory is
  sufficient to explain order-dependent failures in modules that pass 12/12
  alone. The run is therefore not evidence of anything and is not quoted as
  such.

  A single isolated run, with no concurrent build, server, edit or second
  pytest, is the only acceptable basis for sign-off.
- **Extract validation 21/21, deployment readiness, replay-seed diagnostic,
  sign-guard rebuild and replay parity were not run** for the same reason.
- **Clean-clone CI on the final SHA has not been observed.** The PR is opened
  as a draft precisely so that gate runs before anyone relies on it.
- The cold measurement is a single sample per configuration, not a p95.

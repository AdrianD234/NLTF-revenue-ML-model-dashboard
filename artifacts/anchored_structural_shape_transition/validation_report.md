# Anchored Structural Shape Transition — validation report

Branch `feature/anchored-structural-shape-transition`, on top of the PR #11
merge `82d2db67459226a9445fa50b7049c7cebc4032be`.

## Results

| Gate | Result |
|---|---|
| compileall (`app.py`, `model_dashboard`, `scripts`, `tests`) | PASS |
| Full local pytest (pre-promotion) | **1215 passed**, 50 skipped, 0 failed |
| Full local pytest (promoted packs) | see closure_pass_report.md |
| New: transition weight and geometric blend | 33/33 |
| New: comparator × bridge × shape independence + plug-and-play | 16/16 |
| New: hard gates | 31/31 |
| New: analyst preview, wording and envelope | 22/22 |
| Existing long-run layer suite | 33/33 |
| Official-vintage suite (PR #11) | 96/96 |
| Streamlit AppTest | **38/38** |
| Extract validation | PASS (all rows) |
| Deployment readiness | PASS |
| Replay-seed diagnostic | PASS — 0 missing supported keys, 0 reclassified |
| GDP sign-guard register | written, no new binding |
| Formula reconciliation, all four candidates | worst residual < 1e-6 |
| Role-independence matrix | 4/4 cells behave as specified |

The first full run had **one failure**, described below. It was a real signal,
not noise, and is fixed.

## The one failure, and why the fix is not a weakening

`tests/test_revenue_outlook_long_run.py::test_no_lambda_or_shrinking_share_division_is_reintroduced`

That gate has four parts. Three passed unchanged:

- no `lambda_` or `migration_lambda` in the constructor;
- no LEVEL divided by a SHARE anywhere;
- `vfm_pool_index` still present.

The fourth pinned a **literal expression**, `pool_anchor * g["vfm_pool_index"]`.
The Light RUC pool is still `anchor × index` and still multiplicative, but the
index is now the hybrid one — which under the default unblended schedule equals
`vfm_pool_index` exactly.

The gate was updated to assert the **property** rather than the literal:

- the pool must still be `pool_anchor * g[...]` with the index either the VFM
  pool index or the hybrid pool index — the multiplicative anchor × index form;
- **new:** the VFM pool index must remain the *Current leg* of the blend
  (`"light_ruc_pool": "vfm_pool_index"`), so a structural source can never
  silently replace the vendored pool path;
- **new:** the blend must go through `geometric_blend_index`, so it cannot
  become additive on levels.

The updated gate was mutation-tested. On a source where the pool is rebuilt as
`conventional_km / vfm_conventional_share`:

| check | retired idiom | sanctioned form |
|---|---|---|
| level ÷ share detector | fires | silent |
| `forecast_level / conventional_share` | fires | — |
| anchor × index present | absent → gate fails | present |
| share renormalisation `/ share_sum` | — | silent (correctly not flagged) |

So the gate still catches exactly what it was written to catch, and now also
catches two things it previously did not. No tolerance was widened anywhere on
this branch.

## Preservation

Verified against the hash-pinned merged-main baseline (22,470 rows, both
engines, frozen before any candidate was computed):

- FY2025 actuals — **bit-identical**
- Current FY2026–FY2030 — **bit-identical** (400 rows per engine)
- BEFU26 published rows — **bit-identical** (2,200 rows)
- MBU26 published rows — **bit-identical** (2,200 rows)
- promoted fitted states — unchanged
- the `unblended_current` candidate vs the frozen post-model layer — max
  **relative** difference **3.1e-16** across 1,600 rows, i.e. one unit in the
  last place of a double

These are exact equalities, not tolerances. Two precision defects had to be
fixed at source to make them so: the baseline is written at `%.17g` and read
with `float_precision="round_trip"`, because pandas loses the last bits in both
directions by default.

## Coverage limits, stated plainly

Three items in the brief's validation stack were **not** run, and I have not
represented them as passing:

- **Windows/Linux replay parity.** The Windows leg is unchanged by this branch
  (no replay value moves under the default schedule — the unblended candidate
  is merged main to 1 ulp), but the Linux leg comes from CI and has not run.
- **Changed-scope Playwright browser tests and the candidate screenshots.** The
  brief asks for desktop and laptop screenshots of all four candidate paths.
  These have not been captured. The analyst selector is covered by 22
  non-visual tests, but no browser evidence exists yet.
- **Fresh clean-clone CI.** Not run locally.

Section 10's per-scenario requirements are verified in the constructor: each
governed scenario carries its own FY2030 anchor and its own Current index, and
both use the same structural index and schedule. The **policy-ordering and
conflict-convergence** requirements are properties of the existing overlay
architecture (pack → raw PED bridge → Treasury macro replay → VFM overlay →
FED policy overlay), which this branch does not alter — the post-model layer is
built inside the pack, upstream of every overlay. I did not add new tests for
the conflict window, so that part of Section 10 rests on the existing
architecture rather than on new evidence.

## Governed re-freezes

After the owner decision, `balanced_structural` is the production default and
both packs were rebuilt.

| item | scope |
|---|---|
| Runtime artifact hashes | **13 of 71** re-pinned, each with old -> new and cause in `runtime_hash_refreeze_audit.csv` |
| Pack rows changed | **840 per engine**, every one a FY2031-FY2050 `post_model_extrapolation` row |
| Actuals, FY2026-FY2030, fitted states, official spines | unchanged |

No tolerance was widened. The 58 untouched pins are themselves evidence that
the promotion reached only what it should.

See `closure_pass_report.md` for the full response to the consultant review.

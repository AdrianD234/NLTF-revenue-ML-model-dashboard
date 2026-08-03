# Integrating the Revenue Outlook workshop release

Three separately validated branches, combined into one workshop-ready page.
This report records what was merged, what had to be written to join them, and
what each decision was weighed against.

## Inputs

| | PR | Branch | Approved head | Branch tip at merge |
|---|---|---|---|---|
| Base | #16 | `main` | `48a499bdfb6a4d85888b3f3c27af970814048e10` | same |
| B | #17 | `fix/revenue-outlook-series-quarterly-coverage` | `ace8297dfbc08a1657a09ec1d037aa8718c46264` | same |
| C | #19 | `performance/revenue-outlook-policy-runtime` | `45a97428d1d35c7d2d39f4dd9111994f55b26c16` | same |
| A | #18 | `workshop/revenue-outlook-ui-slim-2050` | `f5b8493d1b7ea8d05ffb78b2891428554a284f47` | same |

Every branch tip equalled its approved SHA, so no substitution question arose.
The merges name the commits, not the moving branch refs.

## Merge order and conflicts

`B → C → A`, each `--no-ff` against the exact SHA, histories preserved.

**B** merged with no conflicts.

**C** conflicted only on `.gitignore`, and only because both components added a
governed pack exception in the same place. Resolved as a **union**: B's
`data/revenue_outlook_quarterly_display` and C's
`data/revenue_outlook_policy_runtime` exceptions both kept, each with its own
generating-script comment. Neither side was taken wholesale. `pytest.ini`
merged cleanly and retains all three markers including C's `slow`
configuration; the separately deferred legacy e2e suite was not touched.

**A** conflicted on `.gitignore` for the same reason — B's
`artifacts/revenue_outlook_series_coverage` against A's
`artifacts/revenue_outlook_ui_slim_2050` — and was resolved as a union again.
`app.py` merged cleanly, because B and C deliberately never edited it, so A's
version is the sole starting point for the wiring below.

## What had to be written

The components were built to be combined and left the joins to this PR.

### One horizon, not two that agree

A configured `REVENUE_OUTLOOK_DISPLAY_END_FY = 2050`; B wrote `2050` again as
its own literal. They agreed, but only until someone edited one of them. B's
`DISPLAY_HORIZON_LAST_FY` now reads A's constant and derives its terminal
quarter from the June-year convention, so there is a single configured number
and the annual and quarterly cuts move together. A test pins both filters to
the same rows, including the case that matters: `2050Q3` belongs to FY2051 and
must not survive on its calendar year.

### The quarterly path

The display path called an undeclared local Denton solve in `app.py`. It now
calls B's governed contract, which declares per series which rule applies,
against what seasonal evidence, on what rate basis, and with what stated
limitation — and labels every row it emits as derived.

Two things had to be true for that swap to be safe, and neither was free:

**The derivation must see the FINAL annual rows.** The rows handed to it are
the post-macro, post-policy, post-lever, post-formula chart rows, taken after
the official-vintage filter, so the quarters reconcile to the annual line a
reader sees beside them rather than to an earlier layer.

**A trace the caller supplies must beat the offline pack.** B's lookup
originally preferred its materialised pack for any trace it carried. That is
right for Actual and the official comparators, which no Current-side lever
moves, and wrong for the Current traces: the pack was built under one policy
state, and serving it after a reader defers the 12c step would draw quarters
that do not sum to the annual value printed above them. The precedence is now
explicit — supplied traces are derived, the pack fills the gaps.

**The rate timetable must follow the policy.** B resolved the PED/FED
within-year shape from the `planned` column unconditionally. Deriving a
deferred year on the published schedule still reconciles to the annual
benchmark and still draws the step three months early. The API gained a
minimal `policy_state` argument that selects the governed column
`rate_paths.ped_quarterly_rate_schedules` already publishes — a column
selection over the one governed source, not a second copy of the schedule:

| state | 2026Q4 | 2027Q1 | 2027Q2 | 2027Q3 |
|---|---|---|---|---|
| `published` | 0.70024 | **0.82024** | 0.82024 | 0.82024 |
| `delayed_6m` | 0.70024 | 0.70024 | 0.70024 | **0.82024** |
| `off` | 0.70024 | 0.70024 | 0.70024 | 0.70024 |

Under `off` the 12c never appears: the gap against `published` is a constant
0.12 forever, and no 12c-sized step exists anywhere in the no-uplift path.
An unrecognised state raises rather than defaulting to `published`, because
silently drawing the step in the wrong quarter is the failure the argument
exists to prevent.

**The conflict shock keeps its timing.** The removed local path had a special
case that placed the conflict fuel-price shock in its own quarters using delta
lineage, and the concern was that a plain Denton split would smear FY2026's
loss back into pre-shock 2025Q3–Q4. It does not: B's seasonal indicator is the
*trace's own* native quarterly driver, and the conflict trace's PED VKT per
capita differs from Base in exactly the 20 shocked quarters. The shock timing
now arrives through a declared mechanism rather than an ad-hoc one.

**Two selectable labels had no contract.** `Light RUC volume` and
`Heavy RUC volume` are offered by the stream selector but are not the pack's
own `series_label`, so `canonical_series_id` raised for them and they would
have lost their quarterly rule entirely. Both are now aliases in B's table,
which is where alias logic belongs.

### The policy runtime

A catalogued key is answered from C's materialised state instead of re-running
the overlay chain. C's own profiling is the argument: a switch cost ~13.5 s of
which the policy arithmetic was 0.32 s — the cost was that
`current_fed_policy_state` is part of the cache identity, so every stage
downstream was recomputed although the policy changed none of their methods.

Two controls live *outside* the typed key and so are checked at the call site:
the sensitivity key, which is a separate argument the catalogue was built at
its default, and the bridge-mode argument, which must agree with the key's own
field. Without those checks a moved sensitivity lever would be answered with
default-sensitivity rows — precisely the silent wrong answer the catalogue
exists to avoid. Anything outside the catalogue runs the reference pipeline;
there is no nearest match and no approximation.

A **`scenario_audit` frame** was added to the materialised state. The combined
Treasury-macro and conflict audit is policy-dependent (the conflict append runs
under the selected policy), so serving rows from a materialised state while
rebuilding that frame live would either cost the 2.4 s conflict append back or
describe the rows with an audit computed under a different policy.

A **fast-path switch** was added because the builder calls the same page
functions it materialises. Left on, a rebuild would answer from the pack it is
about to overwrite, and the idempotency check would pass by tautology rather
than by determinism. Deleting the frames first happens to produce the same
effect today, but that is an accident of build order. `app.py` now carries
`POLICY_RUNTIME_FAST_PATH_ENABLED`, the builder sets it False, and a test pins
both halves.

### Policy-aware bands

The band lookup carries the policy state in its cache identity and reads the
runtime's per-state rows, so a band cannot be drawn around a central path it
was not computed from. Where a policy leaves a series unmoved the rows are
identical to the default pack's by construction — the same seeded draws through
the same identities — not by a copy.

**Quarterly bands are withheld, not fabricated.** The uncertainty pack is
June-year only: every `period` is `FY####`, the draws, the copula and the
quantile map are all annual, and no governed quarterly method exists.
Repeating an annual bound four times, or dividing its width by four, would
state a precision the evidence does not carry. At quarterly grain the 50%/80%
layers are dropped from the figure and a note explains why; the reader's
selection is kept and the layers return at June-year grain. The suppression is
keyed on the **grain**, not on whether the frame happens to be empty — an
empty-frame check would silently pass a fabricated frame.

### Restored official lines

BEFU26 and MBU26 Light petrol VKT are appended from their own registered
vintage sources, additively and per vintage, after the official-vintage filter.
73 rows are restored (25 BEFU26, 25 MBU26, 23 Actual), FY2003–FY2050, in
`million km`, each carrying lineage to its own vintage file and manifest hash.
No existing value moves and no vintage is filled in from the other.

### Session migration

A's entry-point sanitiser already cleared the withdrawn retention control, the
VFM audit toggle, VFM chart layers and paused uptake bases. Two more cases were
added for readers returning from an older deployment: an FY marker past the new
horizon is **dropped** (Streamlit raises rather than correcting when a stored
value is not among a widget's options), and a 12c selection this build does not
recognise is **dropped rather than coerced** — coercing would swap one
counterfactual for another with no way for the reader to tell.

## Deliberately not done

The `_disaggregate_annual_rows_to_quarterly` helper is retained but is no
longer reachable from any display path; a test asserts that. Removing it would
mean deleting `tests/test_quarterly_disaggregation.py`'s coverage of it, which
is separate work. The `r2_ladder_summary.csv` write-isolation issue, the stale
pre-PR#15 e2e contract, the broader KKT/solver audit, Stage 2 cold-start work,
Fleet Mix Explorer labels and a quarterly uncertainty methodology are all
untouched, as the brief requires.

## Pack rebuild order

1. **Replay caches** — not rebuilt. Both engines' governed staleness gates
   report `ok` against the integrated tree, and their source digests do not
   include `app.py`, so there was nothing to invalidate. Verified, not assumed.
2. **Quarterly-display pack** — rebuilt twice, byte-identical both times and
   identical to the committed pack. The `policy_state` argument defaults to
   `published`, which is what the pack was built under, so the API extension
   moved nothing.
3. **Policy runtime** — rebuilt last, because its digest includes `app.py` and
   the final calculation modules. C's fail-closed gate correctly reported
   `stale: policy calculation code changed: app.py, model_dashboard/ui.py`
   after A's merge, which is the gate working.

**B's quarterly pack was deliberately NOT added to the policy-runtime digest.**
The policy runtime does not consume it: no quarterly path appears in the
builder's source files or trees, and the two packs answer independent
questions. Coupling them because the UI happens to use both would make every
quarterly rebuild invalidate an unrelated pack. B's *code* is covered
transitively — `revenue_outlook_series_coverage` is hashed into
`code_module_hashes` when imported during the build — which is the real
dependency. The application validates both packs independently.

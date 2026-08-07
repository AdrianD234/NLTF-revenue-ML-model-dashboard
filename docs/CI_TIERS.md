# CI tiers — what runs where, and why

## The problem this replaced

The previous workflow ran one suite for every change, on the pull request and
again after merge. Measured on the last clean run (`30906665375`):

| step | time | share of the core job |
| --- | --- | --- |
| **Core test suite (pytest)** | **69m 25s** | **93.6%** |
| Conflict scenario extract | 2m 00s | 2.7% |
| GDP sign-guard register | 1m 36s | 2.2% |
| Dependency install | 32s | 0.7% |
| everything else | < 30s | < 1% |

Dependency installation was never the problem. The suite was.

Over the week to 2026-08-06, across 60 runs:

| | weighted billed minutes | cost |
| --- | --- | --- |
| succeeded | 1,502 (48.7%) | $12.02 |
| **failed** | **1,008 (32.7%)** | **$8.06** |
| **cancelled/superseded** | **577 (18.7%)** | **$4.62** |
| **total** | **3,087** | **$24.70** |

Just over half the spend went to runs that were cancelled or had already failed,
and on 2026-08-06 the account hit its spending limit — jobs stopped starting
with *"recent account payments have failed or your spending limit needs to be
increased"*. This was not a theoretical optimisation.

## Where the 69 minutes actually sit

One clean profiling pass (1,910 executed tests) shows extreme concentration:

| share of runtime | slowest N tests | as % of tests |
| --- | --- | --- |
| 50% | **10** | 0.5% |
| 75% | 59 | 3.1% |
| 90% | 168 | 8.8% |

`tests/test_view_invariant_sweep.py` alone is **29.3%** of the suite.

That number is a module-scoped fixture shared by five tests — pytest charges
fixture setup to whichever test requests it first. It is not duplicated work,
and neither are the next-biggest items, the reference-pipeline comparisons that
`pytest.ini` deliberately keeps in CI because *"a materialisation nobody
compares to its reference is just a cache."*

So the suite is not slow because it repeats itself. It is slow because it does a
large amount of load-bearing computation, concentrated in about ten tests. Full
analysis in `artifacts/ci_optimisation/duplicate_setup_findings.md`.

The consequence for this design: **the saving has to come from not running that
work when the diff cannot reach it**, not from making it cheaper. Making it
cheaper would mean making it prove less.

## The lanes

```
                 ┌──────┐
                 │ plan │  always. scripts/ci_plan.py classifies the diff.
                 └──┬───┘
       ┌────────────┼─────────────┬──────────────┬────────────┐
       ▼            ▼             ▼              ▼            ▼
   ┌──────┐   ┌──────────┐  ┌──────────────┐ ┌────────┐ ┌──────────┐
   │ fast │   │ affected │  │full-assurance│ │ replay │ │deployment│
   └──┬───┘   └────┬─────┘  └──────┬───────┘ └───┬────┘ └────┬─────┘
      └────────────┴───────────────┴─────────────┴───────────┘
                                 ▼
                          ┌─────────────┐
                          │ CI summary  │  always. THE required check.
                          └─────────────┘
```

| lane | when | target |
| --- | --- | --- |
| `plan` | always | < 1 min |
| `fast` | always | ≤ 8 min |
| `affected` | plan says so, and full assurance is not already running | ≤ 15 min |
| `full-assurance` | governed pack, data refresh, fitted state, dependencies, `ci:full` label, dispatch, weekly schedule | ~75 min |
| `replay-parity` | fitted state, numerical model code, or dependency versions moved | ~3 min per platform |
| `deployment` | Databricks bundle or deployment surface changed | ~5 min |
| `summary` | always | < 1 min |

### Why `summary` is the only required check

GitHub leaves a required status check **Pending indefinitely** when the job it
names is skipped by a condition. Marking `full-assurance` required would block
every documentation PR forever.

`summary` runs with `if: always()`, reads what the plan demanded, and fails when
a required lane did not succeed **or did not run**. A lane quietly disappearing
is a failure, not a pass.

### Draft pull requests

Drafts run `plan` + `fast` only. Intermediate pushes on a branch that is still
changing were the largest single source of wasted minutes in the baseline.

To get the planned assurance on a draft:

- mark the PR **ready for review** (the workflow listens for
  `ready_for_review`, which is not in GitHub's default trigger set), or
- apply the **`ci:full`** label, or
- run **workflow_dispatch** with *force_full*.

### Post-merge

Push to `main` runs `plan` + `fast` + `affected` — a genuine check on the merged
tree, without repeating the 74-minute suite the pull request already ran against
the same tree.

This is only sound once `main` is protected. See
[BRANCH_PROTECTION.md](BRANCH_PROTECTION.md); the fallback switch is documented
there.

### Weekly schedule

A Sunday run forces full assurance. It catches drift no diff would predict:
upstream wheel changes, hosted image changes, and any pack that is stale on
`main` for a reason nobody's change introduced.

## The change planner

`scripts/ci_plan.py` reads `ci/change_scopes.yml` and classifies each changed
file into one or more of fourteen scopes. Requirements union across matched
scopes.

```bash
python scripts/ci_plan.py --base origin/main --head HEAD --format human
```

It escalates rather than guesses. Every one of these produces full assurance
plus both replay platforms:

- an unmatched Python file;
- an unmatched data file;
- any unmatched file at all;
- a diff wider than 120 files;
- the classifier failing to read the diff.

`docs_only` is the one scope that lowers cost, and only when **every** changed
file is documentation. One source file in the diff and the cheap lane is gone.
`app.py` is never docs-only or UI-only: it wires the pages to the governed
runtime, so it always pulls in the dashboard integration surface and the
policy-runtime status check.

`tests/test_ci_plan.py` pins all of this, including that every tracked file in
the repository currently classifies — so a new area cannot appear without either
a rule or a deliberate escalation.

## Where the roadmap lands

| work | lane |
| --- | --- |
| Nominal rather than NPV default; scenario titles | `dashboard_ui` / `revenue_outlook_presentation` — fast + affected |
| Treasury 7/8 update; PREFU refresh; new actuals | `data_refresh` — full assurance + both replays |
| PED calibration R² drift | `governance_r2` — targeted, no browser matrix |
| COVID dummy, seasonality, trend interactions | `model_experiment` — **local only** |
| Error bands excluding COVID | `uncertainty` — targeted until promoted |
| Exports/imports, lagged GDP, clean-car discount | `model_experiment` — **local only** |
| Less black-box models | `model_experiment` — **local only** |
| Coefficients through time | research on a promoted finalist |
| Documentation, funding theory | `docs_only` |
| Heavy-RUC consumption, truckometer, e-RUC | `model_experiment` then `data_refresh` |
| Smoothed VKT per capita | `model_experiment` — **local only** |

The rule underneath the table: **candidate generation, model permutations and
retraining run locally. GitHub CI validates only the promoted result, saved
state, manifests, replay and governed packs.**

Otherwise every COVID/seasonality/interaction permutation would consume hosted
minutes to answer a question that is a comparison between candidates on one
machine, not a cross-platform guarantee.

## Governed packs

CI validates committed pack status; it does not rebuild packs.

```bash
python scripts/plan_governed_pack_rebuilds.py
```

reports each of `replay_cache`, `quarterly_display`, `uncertainty`,
`policy_runtime` and `databricks_bundle` as ok / stale / missing / corrupt /
affected, with the reason, the required order and the rebuild command. It reuses
the runtime's own status functions rather than recomputing digests, so there is
exactly one authority on whether a pack is fresh.

Rebuilding belongs in the local promotion workflow (AGENTS.md mode C), where the
result can be inspected before it is committed. A second idempotency build is
only warranted when the builder code or schema changed, determinism is in doubt,
or release assurance asks for it.

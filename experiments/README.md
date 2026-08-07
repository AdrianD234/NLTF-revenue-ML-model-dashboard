# Model experiments

Specification work runs here, locally, and never in GitHub Actions.

The roadmap is a long list of questions — a two-year COVID dummy, COVID trend
and coefficient permutations, dropping seasonality dummies, exports/imports and
lagged GDP, the clean-car discount, explainable challengers, heavy-RUC
consumption variables, smoothed VKT-per-capita variants, error bands that
exclude COVID. Most of those runs will be discarded.

Running them through hosted CI would be the most expensive possible way to
answer them, and would answer the wrong question anyway: what matters is a
comparison between candidates on the *same* machine, not a cross-platform
guarantee. Cross-platform guarantees are for the one candidate that gets
promoted.

**Only a selected finalist enters model-promotion CI.**

## Running one

```bash
python scripts/run_model_experiment.py --config experiments/configs/example.yml
python scripts/run_model_experiment.py --list
python scripts/run_model_experiment.py --compare exp_0001 exp_0002
```

Inside the container, for an environment that matches CI:

```powershell
pwsh -File scripts/ci_local.ps1 -Tier shell
```

## What every experiment records

`scripts/run_model_experiment.py` writes `experiments/results/<id>/result.json`
containing:

- experiment ID and description;
- source SHA, branch, and whether the tree was dirty;
- SHA-256 of every declared input file;
- model stream and the specification changes being tested;
- seed, train window, validation windows;
- the metrics the entry point returned (MAPE, annual MAPE, R² variants,
  diagnostics, coefficients or feature importance — whatever the entry point
  reports);
- runtime;
- a hash of the whole payload;
- `promotion_status`, which starts as `candidate` and is only ever changed by a
  human in a separate commit.

The point of recording a discarded candidate is that it can be reconstructed
later. An experiment whose inputs cannot be identified is an anecdote, and six
months from now "we tried that" will not be checkable.

`--compare` warns when two experiments did not use identical inputs, because
that comparison conflates a specification change with a data change.

## Config contract

```yaml
experiment_id: exp_0001            # required, becomes the results directory
description: Two-year COVID dummy  # required
stream: PED                        # required
seed: 20260807                     # required

entry_point: pipeline.vnext_candidates:run_experiment

specification_changes:
  - Add a COVID dummy spanning 2020Q2..2022Q1
train_window: [2010Q1, 2025Q4]
validation_windows:
  - [2023Q1, 2025Q4]

input_files:                       # hashed, so results tie to data
  - data/model_input_history/light_ruc_inputs.parquet
```

`entry_point` is `module.path:function`. The function receives the config dict
and must return a dict of metrics. It is named by the config rather than
hard-coded because the roadmap's experiments touch different parts of the model;
what is fixed is the contract, not the callable.

## What this must not do

- **Never promote.** Nothing here writes to `data/`, rebuilds a governed pack,
  or touches a manifest. Promotion is a deliberate, separate act under
  AGENTS.md mode C.
- **Never run in CI.** `ci/change_scopes.yml` maps `experiments/**` to the
  `model_experiment` scope, which requires no hosted assurance at all, and
  `tests/test_ci_plan.py` pins that.
- **Never compare across differing inputs** without saying so.

## Promoting a finalist

1. Pick the candidate. Record why, against the recorded metrics of the ones you
   rejected.
2. Set `promotion_status: promoted` in its result, in its own commit.
3. Switch to AGENTS.md **mode C**: promoted-state replay, the full affected
   model suite, governed pack rebuild in dependency order
   (`python scripts/plan_governed_pack_rebuilds.py`), full assurance, and
   cross-platform replay.
4. Open the PR. The planner will classify it as `model_promotion` and demand
   full assurance and both replay platforms — which is the one place that
   expense is worth paying.

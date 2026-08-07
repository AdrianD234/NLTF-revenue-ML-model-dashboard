# AGENTS.md

## Project purpose

This repository contains a Streamlit dashboard for the NLTF Stage 1 model-governance and model-discovery workstream.

The dashboard must read a completed model-run folder and visualise:
- recommended finalists;
- candidate search landscape;
- Schiff benchmark comparisons;
- ensemble composition;
- forecast actual vs predicted;
- forecast errors;
- stress and horizon checks;
- model inventory;
- run audit and error diagnostics.

## Work modes — read this before choosing what to run

This repository used to apply release-grade assurance to every task: the
complete suite, the browser matrix, 50 improvement loops and the 100-gate
conformance run, whatever the change was. That rigor is preserved in full — it
now lives in `docs/RELEASE_ASSURANCE.md` and applies to **mode D**.

Pick the mode that matches the work. If two apply, use the stricter one. If you
cannot tell, run `python scripts/ci_plan.py --base origin/main --head HEAD` and
use what it says: a `high` risk level means mode C or D.

### Mode A — Feature (the default)

Ordinary dashboard, presentation, calculation or documentation work.

Required:
- `python -m compileall -q .`;
- the local fast tier: `pwsh -File scripts/ci_local.ps1 -Tier fast`;
- the tests the change plan selects:
  `pwsh -File scripts/ci_local.ps1 -Tier affected -Base origin/main`;
- one relevant AppTest or browser smoke **where the UI changed**;
- pack status for affected packs:
  `python scripts/plan_governed_pack_rebuilds.py`.

Explicitly **not** required by default:
- the complete suite;
- 50 improvement loops;
- every page;
- Windows replay;
- rebuilding packs the change did not invalidate.

### Mode B — Model experiment

Candidate generation, specification permutations, retraining, feature trials.
This covers COVID dummies and trend interactions, dropping seasonality,
exports/imports and lagged GDP, the clean-car discount, explainable
challengers, heavy-RUC consumption variables and smoothed VKT-per-capita
variants.

Required:
- run locally or in the container, never in GitHub Actions;
- a fixed seed and an explicit configuration under `experiments/configs/`;
- recorded source SHA and input-data hashes;
- candidate metrics and diagnostics written to `experiments/results/`;
- **no promotion** — nothing under `data/` moves in this mode.

GitHub CI validates no model-search permutation. That is deliberate: a
Cartesian sweep of specifications is exactly the work that must not consume
hosted minutes.

Use `python scripts/run_model_experiment.py --config <path>`.

### Mode C — Model promotion

A finalist, fitted state, promoted pack, Treasury/PREFU refresh or new actuals
becomes the production answer.

Required:
- promoted-state replay;
- the full affected model suite;
- governed pack rebuild in dependency order
  (`python scripts/plan_governed_pack_rebuilds.py` gives the order);
- full assurance: `pwsh -File scripts/ci_local.ps1 -Tier full`;
- cross-platform replay where fitted state or numerical model code moved.

### Mode D — Release hardening

Declaring the dashboard release-ready or management-ready.

Required: everything in `docs/RELEASE_ASSURANCE.md`, unchanged.

---

## Where work runs

Candidate generation, model permutations and retraining run **locally**.
GitHub CI validates only the promoted result, saved state, manifests, replay and
governed packs.

The container in `ci/` is the local authority for governed numbers, because it
is the only local environment that matches CI's Python 3.11. The developer
`.venv` on Windows is a different Python and numpy build; it is fine for
iteration and cannot settle a numerical disagreement. See `ci/README.md`.

```powershell
pwsh -File scripts/ci_local.ps1 -Tier fast                       # minutes
pwsh -File scripts/ci_local.ps1 -Tier affected -Base origin/main # planner-selected
pwsh -File scripts/ci_local.ps1 -Tier full                       # complete assurance
pwsh -File scripts/ci_local.ps1 -Tier profile                    # timing evidence
pwsh -File scripts/ci_local.ps1 -Tier replay -Engine ar1         # replay fingerprint
```

Hosted CI is change-aware: `scripts/ci_plan.py` classifies the diff and only the
lanes it requires run. Draft pull requests get the fast lane only — mark the PR
ready for review, or apply the `ci:full` label, when you want the planned
assurance. `docs/CI_TIERS.md` explains the lanes.

## Windows Playwright policy

- Run non-browser verification through the normal bounded sandbox.
- Run pytest-playwright only through an explicitly approved host/outside-sandbox shell.
- WinError 5 during sync_playwright/startup means sandbox named-pipe denial, not missing dependencies or dashboard failure.
- Do not retry inside the sandbox or reinstall Playwright.
- Reuse the healthy Streamlit server and run the browser phase outside the sandbox.
- From Codex on Windows, call `scripts\verify_dashboard.ps1 -SkipBrowser` for the sandbox phase and `scripts\verify_browser_host.ps1 -Python python -Port <port>` only from an approved host/outside-sandbox shell.
- Do not call raw `scripts\verify_dashboard.ps1` expecting it to run browser tests on Windows; the browser phase is intentionally split to avoid sandbox named-pipe hangs.

## Do-not rules

- Do not hard-code demo data as if it were real.
- Do not remove features to make tests pass.
- Do not weaken requirements to pass verification.
- Do not silently ignore missing files.
- Do not classify Schiff residual or Schiff blend models as pure Schiff benchmarks.
- Do not let long model names destroy layout.
- Do not invent official Waka Kotahi/NZTA logos. Use supplied assets or neutral generated assets only.
- Do not rebuild a governed pack because a nearby file changed. Ask
  `scripts/plan_governed_pack_rebuilds.py` which packs are actually stale.
- Do not run a model permutation in GitHub Actions.
- Do not add a test to the suite without giving it a home in
  `ci/change_scopes.yml`; an unclassified file forces full assurance on every
  future change.

## Bounded command policy

Do not run risky shell commands without a hard timeout.

Use checked-in wrappers instead of pasted multi-line PowerShell loops:

```powershell
pwsh -NoProfile -File scripts\start_streamlit_bounded.ps1 -Port 8501 -StartupTimeoutSeconds 90
pwsh -NoProfile -File scripts\restart_streamlit_bounded.ps1 -Port 8501 -StartupTimeoutSeconds 90 -StopTimeoutSeconds 20
& .\scripts\invoke_bounded.ps1 -Label verify-dashboard -TimeoutSeconds 900 -FilePath pwsh -Arguments @("-NoProfile", "-File", "scripts\verify_dashboard.ps1")
& .\scripts\invoke_bounded.ps1 -Label verify-dashboard-non-browser -TimeoutSeconds 900 -FilePath pwsh -Arguments @("-NoProfile", "-File", "scripts\verify_dashboard.ps1", "-SkipBrowser")
```

Timeout defaults:

- Streamlit startup/health checks: 90 seconds.
- Focused Playwright tests: 180 to 300 seconds.
- Full e2e or full pytest runs: 900 seconds.
- Dependency or network commands: 300 to 600 seconds.

When a broad Playwright run prints repeated `F` output or appears to hang, split
it first with `-vv -s --maxfail=1` so the first failure is visible immediately.
The bounded wrapper should still be used for the split command.

On timeout, inspect the wrapper log tails and exact child process command line,
then stop only the process tree launched by the wrapper. Do not kill unrelated
user Chrome, Excel, Python or Streamlit processes blindly.

Do not hand-roll Streamlit restart loops with `Get-NetTCPConnection` polling.
Use `scripts\restart_streamlit_bounded.ps1`; use `-ReuseHealthy` when an
existing healthy server should be kept.

## Parquet data-quality rule

For Stage 1 governance dashboard work, the source of truth is the curated Parquet candidate pack resolved from `MODEL_DIAGNOSTIC_DATA_ROOT`, `STAGE1_DASHBOARD_DATA_ROOT`, CLI arguments, or the Streamlit data-root control.

Legacy run-folder CSV/XLSX outputs are review-only. They must not become the main app path or override Parquet-backed finalists.

Before declaring completion:

- write `artifacts/data_source_manifest.json` for the active data root;
- prove the current finalist values reconcile to Parquet `is_current_recommended` rows;
- prove the older AutoGluon balanced-run finalist values are not current latest finalist values;
- prove the candidate landscape is a capped curated cone/frontier sample, not a raw candidate dump;
- prove pure Schiff excludes residuals, blends, solvers, ensembles, top/mean/median variants, and convex solver rows;
- prove primary filters are directly clickable and hovers are management-readable;
- update `artifacts/data_validation_review.md`, `artifacts/cone_landscape_review.md`, `artifacts/filter_interaction_review.md`, reviewer files, and `.agent_state.md`.

Do not mark this sprint complete while `artifacts/recursive_audit_loops.json` has fewer than 20 documented recursive audit loops unless the task is explicitly left as in progress in `.agent_state.md`.

## Release assurance

The release-grade completion rule, improvement-loop quotas, reviewer matrix,
browser requirements, performance-hardening rule and the 100-gate visual
conformance rule live in `docs/RELEASE_ASSURANCE.md`. They are unchanged and
still mandatory — for mode D.

If interrupted, write `.agent_state.md` and mark the task in progress.

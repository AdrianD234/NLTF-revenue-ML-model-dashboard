# Databricks App runtime bundle — design

## Problem

Databricks Apps rejects any source file over 10 MiB. Deploying the full Git
checkout fails on `.git/objects/pack/*` and on eight tracked files (four
oversized audit CSVs per engine pair, one generated source-pack CSV, one
audit ZIP). Notebook-based copying and manual CSV chunking were temporary
workarounds.

## Settled architecture

`main` stays the complete modelling + governance repository. A deterministic
runtime bundle is generated from it by
[`scripts/build_databricks_app_bundle.py`](../../scripts/build_databricks_app_bundle.py)
under the explicit policy in
[`deployment/databricks_app_bundle_policy.json`](../../deployment/databricks_app_bundle_policy.json),
validated fail-closed by
[`scripts/validate_databricks_app_bundle.py`](../../scripts/validate_databricks_app_bundle.py),
and published by the `Publish Databricks App bundle` workflow to the generated
`databricks-app` branch beneath `app/`. Databricks deploys:

    Branch:           databricks-app
    Source code path: app

so `.git`, tests, docs, deliverables and every oversized audit file stay
outside the app source.

## Validation never touches what it publishes

Rendering the app writes into `artifacts/` — the r2-ladder chart sources are
rewritten on every render. A validator that hashed the bundle and then probed
it in place would leave the publish workflow shipping content that no longer
matched the manifest it had just verified. So the runtime probes run against
disposable copies of the bundle and of the source checkout, the bundle's
structure and manifest hashes are re-verified *after* the probes, and the
checkout's `git status` must come back unchanged.
`tests/test_databricks_app_bundle_contract.py` pins both halves: probes are
proven to run outside the bundle and the checkout, and a deliberately leaky
probe is proven to be caught.

## Classification result (evidence: oversized_file_classification.csv)

- Parquet-first was already the runtime contract: every oversized pack CSV has
  a same-stem Parquet ≤ 275 KiB that the runtime actually reads.
- `canonical_revenue_long.csv` is a generated audit table; the loader computes
  the canonical frame from the normalized source tables. Omitted.
- The candidate-rescue ZIP is development evidence never read by the app.
  Omitted.

## Two narrow code changes were unavoidable

The consultant plan assumed omission alone would work. Runtime tracing showed
two fail-closed guards would have broken the deployed app:

1. **Pack loader** — `load_revenue_outlook_pack` existence-checks every
   `manifest.output_hashes` entry, including the oversized CSV twins, and
   raises on any missing file. Fix: `_parquet_twin_validates`
   (`model_dashboard/revenue_outlook.py`) tolerates a *missing* CSV only when
   its same-stem Parquet is present **and** matches its recorded manifest
   hash. Every file the runtime reads is still integrity-checked; a missing
   or corrupt Parquet remains a hard error. On the full checkout the CSVs are
   present, so behaviour there is unchanged.

2. **Replay-cache digest** — the compiled replay cache hashes the whole
   `data/dashboard_evidence_pack_reproducibility` tree, so the audit ZIP's
   absence would read as `stale` and the Revenue Outlook page would refuse to
   render in default fast mode. Fix: `_SOURCE_TREE_EXCLUSIONS`
   (`model_dashboard/revenue_outlook_replay_cache.py`) excludes the
   `candidate_rescue/` archive directory from the digest; both engine caches
   were rebuilt (`scripts/build_revenue_outlook_replay_cache.py --all`) with
   every materialised frame round-tripping exactly. Because the policy
   runtime chains the replay `source_digest` and hashes the calculation code,
   both policy-runtime packs were repinned
   (`scripts/build_revenue_outlook_policy_runtime.py --all`) — the same
   maintenance as the precedent repin commit. No governed forecast value
   changes; the bundle validator proves value parity against the full
   checkout.

## Deliberate divergences from the consultant brief

- `config/` and `templates/` were to be included "likely"; tracing showed
  `config/` has zero runtime references (excluded) while `templates/` is kept
  (50 KiB, governed template workbooks).
- `scripts/check_streamlit_deploy_readiness.py` is left untouched: it guards
  the full-checkout Streamlit Cloud deployment, whose CSVs all still exist.
  The bundle validator re-implements the bundle-appropriate subset of its
  checks. The no-pyarrow CSV-fallback property cannot hold in the bundle for
  the two swapped tables; on Databricks `pyarrow` is pinned in
  `requirements.txt`, so the Parquet path is guaranteed.
- No Unity Catalog Volume is needed: nothing runtime-required remains over
  9 MiB after the Parquet swaps.

## Size effect

Roughly 117 MiB of oversized files leave the bundle; the largest remaining
bundle file is `data/revenue_model_source_pack/2026_05_19/release_values.csv`
(6.6 MiB), comfortably under the 9 MiB warning line enforced by the builder,
the validator and `tests/test_databricks_app_bundle_contract.py`.

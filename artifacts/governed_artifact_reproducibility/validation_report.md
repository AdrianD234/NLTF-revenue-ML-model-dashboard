# Governed-artifact reproducibility hardening — validation report

Starting main SHA: `ac1895da9a517a0040c363b6077ae37e603ee9a0`.
Branch commits: `ab5f026` (source/tests) → `173f1d9` (uncertainty pack
rebuild) → `2e74a86` (policy repin) → `2bbfe16` (collision-safe atomic
writer) → `a5d90d4` (policy repin 2). Evidence commit follows this report.

## Pack promotion proofs (Windows, the committed-pack platform)

| check | result |
| --- | --- |
| uncertainty build 1 vs build 2 | byte-identical, all 3 files |
| uncertainty manifest | `output_hashes` verified; `source_main_sha=ab5f026`; seed/draws/scenario-key digest unchanged |
| rows moved vs pre-rebuild committed | exactly 20, all `light_petrol_vkt` FY2031–FY2050 |
| implied factor across all six columns | 1.014895960822545, spread 4.4e-16 (rigid) |
| span80/span50/median-multiplier invariance | max deltas 2.8e-14 / 2.1e-14 / 2.2e-16 |
| nesting (50 in 80, central inside 80) | holds on all 1,000 rows |
| FY2030 seam | FY2030 rows byte-stable; relative-width continuity change < 1e-9 |
| policy runtime repin ×2 | provenance-only both times (all 200 frames identical cell-by-cell); 202/202 files byte-identical between consecutive builds |
| planner | every pack `ok`, `--fail-on-stale` green, no caveat |
| Revenue Outlook row parity (light petrol central/50%/80%, FY2030/31/50, published/delayed/no-uplift, both engines) | **identical, worst abs delta 0.0** (`revenue_outlook_row_parity.csv`) |
| governed non-movement vs starting state | 0 unauthorised file movements (`governed_value_non_movement.csv`) |

## Focused test results (Windows venv)

| suite | result |
| --- | --- |
| tests/test_ci_safety_gates.py + test_chart_source_write_isolation.py + band-stability test | 59 passed |
| tests/test_revenue_outlook_policy_runtime.py (full module, incl. the rewritten exactness test and the new centre-source guard) | 53 passed |
| tests/test_r2_engine_identity.py (identity pins + sequential/2-worker/4-worker isolated generation) | 6 passed |

## Mutation checks (each mutation must make its guard fail — all detected)

| mutation | guard that fired |
| --- | --- |
| conftest reverted to plain `setdefault` (shared worker path reintroduced) | `test_isolated_generation_reproduces_the_committed_values[2]` and `[4]` FAILED |
| worker/pid identity removed from the scratch path | `test_the_scratch_destination_is_unique_per_process` FAILED |
| committed pack perturbed out-of-band (central + one bound, +1.0) | planner `status_uncertainty` → stale (output-hash mismatch); `test_delayed_state_reproduces_the_committed_offline_uncertainty_pack` FAILED; `test_the_offline_pack_centre_is_the_published_current_line` FAILED |
| manifest that cannot vouch for its content | `test_uncertainty_content_that_differs_from_its_manifest_is_stale`, `test_uncertainty_manifest_without_output_hashes_is_stale` (hermetic unit tests, passing) |
| hardcoded/perturbed re-centring factor; omitted bound column | no re-centring code exists to mutate — the builder reads the governed centre; the equivalent content mutations are covered by the perturbation row above (one bound column alone trips the exact test) |
| removing a pack from the reproducibility probe | the probe is per-pack parameterised diagnostic tooling; probe composition is driven by the operator/CI invocation, not asserted by a test |

## Clean-room verification at the final SHA (Docker Python 3.11)

Phase A (at `ac1895d`, before the fix): see
`pack_reproducibility_matrix.csv` — the uncertainty 20-row movement was the
only governed-value movement across all four packs; every builder
byte-idempotent in-container.

At the final SHA `a5d90d4`, in fresh disposable clones (`raw_final/`):

**Uncertainty exact reproduction — the branch's central acceptance criterion:**

| check | result |
| --- | --- |
| `uncertainty_band_rows.parquet` committed vs rebuild | max abs diff **7.28e-12**, **0 cells outside the structural contract** — the former 20-row / 508.99-unit movement is gone |
| `june_year_basis.parquet` | max abs diff 6.9e-18 (0 outside contract) |
| build 1 vs build 2 (in-container) | **identical**, all 3 files |
| manifest differences | provenance only: `source_main_sha` (ab5f026 → the probed SHA) and the two `output_hashes` tracking the cross-platform float noise |
| planner status on the committed tree, inside the container | replay_cache ok, quarterly_display ok, **uncertainty ok**, policy_runtime ok, bundle not affected |

The residual 7.28e-12 is the same cross-environment float noise every other
pack shows (committed on Windows/3.13, rebuilt on Linux/3.11); it is ~1e-13
relative, three orders inside the 1e-9 test tolerance, and there are zero
cells outside `atol 1e-9 + rtol 1e-12·|x|`. Same-platform rebuild is
byte-identical (proved on Windows above).

**Phase B R² matrix** (`raw_final/phase_b/matrix.log`):

| configuration | result |
| --- | --- |
| ensemble engine audit | `0.5591936636031876` / `0.9230110422702978` — the committed values |
| AR(1) engine audit | `0.5803595524485978` / `0.9448430187011027` — the incident values |
| sequential writers (64 tests) | committed values; tracked sources byte-identical |
| xdist n=2 load, n=4 load, n=2 loadscope, n=4 loadscope, n=4 loadfile | **every worker directory** carries the committed values; tracked sources byte-identical after each configuration |
| shared destination ×3 (pre-fix world, in scratch) | `test_acf_plotted_scope_equals_selected_scope` **fails** each time (1 failed / 102 passed) — cross-identity contamination made visible; see the honest limitation noted in `r2_parallel_diagnosis.md` |

## Final local acceptance

Frozen SHA: **`e2acd481fb533298fafae66eb81902379dd04fac`**. Every tier ran in
the `nltf-ci:local` Python 3.11 container against a disposable detached
worktree at that commit — never against the working checkout. Preconditions
confirmed first: clean Windows worktree, clean WSL clone, no pytest process,
no pack builder, no Streamlit server, no CI container.

| # | check | result |
| --- | --- | --- |
| 1 | Docker **fast** | exit 0, 3s; compile + smoke + 48 planner tests; tracked files unmutated |
| 2 | Docker **affected** (`--base origin/main`) | exit 0 — the planner classified the branch high risk (governed pack + uncertainty + committed evidence), so the lane escalated to full assurance |
| 3 | Sequential Docker **full** tier, fresh clone of the final SHA | **exit 0, 2,080 tests: 0 failed, 0 errors, 53 skipped**, 2,027 passed; 1,904s test time, 2,024s wall |
| 4 | Conflict extract validation | **21/21 PASS** (`status` and `passed` columns unanimous) |
| 5 | Deployment readiness | **PASS** (`scripts/check_streamlit_deploy_readiness.py`, exit 0) |
| 6 | Governed-tree cleanliness | **2,198 governed files verified unchanged** by the in-container gate, on every exit path |
| 7 | Exact pack reproducibility matrix | all four packs — see the clean-room section above; uncertainty now exact, all builders byte-idempotent |
| 8 | Revenue Outlook row parity | **identical, worst abs delta 0.0** across Light petrol VKT central/50%/80% × FY2030/FY2031/FY2050 × published/delayed/no-uplift × both engines (`revenue_outlook_row_parity.csv`) |

Browser verification was not required: no rendered value changes, and row
parity is independently proven at the value level (item 8), with no chart or
selection logic touched on this branch.

### Proof that no central forecast or revenue value moved

* The policy runtime — the pack the dashboard actually reads — was rebuilt
  twice and proven **provenance-only** both times: all 200 frames identical
  cell by cell, only `source_digest`/`source_main_sha`/`provenance` changed.
* Row parity against the pre-branch SHA is exactly 0.0 for every band value
  checked, in every policy state, on both engines.
* `governed_value_non_movement.csv`: zero unauthorised file movements across
  all four packs versus `starting_state.json`.
* The only governed data that moved is the offline uncertainty pack's 20
  stale `light_petrol_vkt` FY2031–FY2050 rows, which now equal the published
  Current line the dashboard was already drawing — so no number a reader has
  ever seen changed.

### Stop conditions

None of the section-11 stop conditions was hit. In particular: no other pack
moved governed values; the committed R² values are neither wrong nor stale
and were not changed; the re-centring was derived from the authoritative
Current path with no circularity (the builder reads the governed line frame,
not the uncertainty pack); no hardcoded factor and no generic tolerance was
introduced; no test writes to tracked governed artefacts; build 1 and build 2
agree for every pack; and the manifests reference commits that contain the
implementation.

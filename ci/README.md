# Local clean-room CI

The container in this directory is the **local authority for governed model
questions**. It exists because the developer environment on Windows cannot
settle them:

| | this repo's `.venv` | `ci/Dockerfile` | GitHub hosted |
| --- | --- | --- | --- |
| Python | 3.13.5 (Anaconda) | 3.11 (bookworm) | 3.11 |
| streamlit | 1.58.0 | 1.59.0 (pinned) | 1.59.0 (pinned) |
| CPUs | 20 | 20 (host) | **2** |

The forward model is not bit-reproducible across differing Python and numpy
builds, so a number produced by the `.venv` and a number produced by CI can
legitimately disagree without either being wrong. The `.venv` is fine for
iterating. It is not evidence.

## Quick start

```powershell
pwsh -File scripts/ci_local.ps1 -Tier fast
```

```bash
scripts/ci_local.sh --tier fast
```

The first run builds the image (a few minutes, mostly scikit-learn and
statsmodels wheels). Subsequent runs reuse the layer cache and start in seconds,
because dependencies are installed from `requirements*.txt` alone, before any
source is present — editing a module does not reinstall anything.

## What the wrapper guarantees

It never runs against your working checkout. For every invocation it:

1. checks Docker is present and in Linux-container mode (on Windows, delegates
   through `wsl.exe` — Docker Engine in WSL publishes no Windows client);
2. resolves the exact commit you asked for;
3. creates a **disposable self-contained clone** at that commit — a clone, not
   `git worktree add`, because a worktree's `.git` is a *file* pointing outside
   the bind mount, and `ci_plan.py`, the planner tests and the cleanliness gate
   all need a working repository inside the container;
4. verifies the clone is byte-exact against the commit, and refuses to run if
   it is not (this is what `* -text` in `.gitattributes` buys — the check is
   there so a future change to that file cannot silently invalidate results);
5. mounts that copy into the container, running as the invoking user so nothing
   root-owned is left behind;
6. writes everything to `artifacts/ci_local/<sha>/`;
7. snapshots every tracked file plus everything under `data/` beforehand and
   verifies it afterwards, on **every** exit path (an `EXIT` trap, so a failing
   suite and the steps that run after it are covered too);
8. deletes the disposable clone;
9. returns the tier's real exit code — and exits 3 if the run mutated governed
   content while otherwise passing;
10. refuses to start while another local run holds the lock.

Uncommitted work is **not** included. That is deliberate: a governed result has
to name the tree it came from.

## Tiers

| tier | target | what it runs |
| --- | --- | --- |
| `fast` | ≤ 5 min warm | compile, import smoke, planner tests, selected unit tests |
| `affected` | ≤ 15 min | fast, plus the tests `ci_plan.py` selects for your diff |
| `full` | — | the complete clean-clone assurance, step-for-step as hosted CI |
| `profile` | — | timing evidence: `--durations`, JUnit XML, per-file aggregation |
| `replay` | ~2 min | the governed replay fingerprint |
| `pack-status` | seconds | which governed packs are stale, and in what order to rebuild |
| `databricks-bundle` | ~3 min | build and validate the slim runtime bundle |

```powershell
pwsh -File scripts/ci_local.ps1 -Tier affected -Base origin/main
pwsh -File scripts/ci_local.ps1 -Tier full
pwsh -File scripts/ci_local.ps1 -Tier profile
pwsh -File scripts/ci_local.ps1 -Tier replay -Engine ar1
```

The `affected` tier escalates itself to `full` when the change plan says the
diff can move a governed number, and when the planner cannot run at all. It
never silently runs less than the plan demands.

## Threading

The image pins `OMP_NUM_THREADS=1` and friends. The forward model is not
bit-reproducible across differing thread counts, so a container quietly using 20
threads where the hosted runner used 2 would manufacture drift that looks like a
code defect. Raise `CI_THREADS` only for benchmarking, and never treat the
result as governed evidence.

## What this is not

- **Not a replacement for hosted CI.** Hosted CI is the independent check on a
  clean machine that has never seen your working tree. Local Docker is faster
  and closer to hand; it is not independent.
- **Not the Windows replay authority.** The image is Linux. Windows replay
  parity can only be answered by a Windows runner.
- **Not a pack builder.** `pack-status` reports; it does not rebuild. Rebuilding
  is a deliberate act under AGENTS.md mode C, so the result can be inspected
  before it is committed.

## Installing Docker — Engine, not Desktop

**Do not install Docker Desktop for this repository.** Docker Desktop carries a
commercial licensing requirement for government entities and larger
organisations. Docker Engine is Apache-2.0 and carries no such requirement, and
it runs inside the WSL2 Ubuntu distribution this machine already has.

From inside WSL:

```bash
bash ci/install_docker_engine_wsl.sh
```

That installs `docker-ce`, `docker-ce-cli`, `containerd.io`,
`docker-buildx-plugin` and `docker-compose-plugin` from Docker's official Ubuntu
apt repository. It verifies the distribution is a release Docker publishes
packages for, changes nothing on the Windows side, and **deliberately does not**
add your user to the `docker` group — group membership is equivalent to
passwordless root here, which is a decision to take deliberately rather than
inherit from an installer.

It needs `sudo`, which prompts for a password on this machine, so it must be run
by hand.

### Run the container work from the Linux filesystem

Bind-mounting from `/mnt/c` is markedly slower than ext4 under WSL2. Keep a
working copy inside the Linux filesystem:

```bash
mkdir -p ~/nltf-ci && cd ~/nltf-ci
git clone /mnt/c/Users/<you>/Repos/NLTF-revenue-ML-model-dashboard repo
cd repo && git checkout performance/ci-runtime-optimisation
scripts/ci_local.sh --tier fast
```

The Windows checkout is never touched by any of this.

## If Docker is not installed yet

The wrappers fail with an explanation rather than falling back to the `.venv`,
because a silent fallback to a different Python is exactly how a numerical
disagreement gets attributed to the wrong cause.

Until Engine is installed, non-governed iteration in the `.venv` is fine and
hosted CI remains the authority.

## Diagnostic scripts vs permanent tooling

`ci/` contains both. The distinction matters when you are deciding what to trust
and what to delete.

**Permanent — these are the system:**

| script | role |
| --- | --- |
| `Dockerfile`, `compose.yaml`, `entrypoint.sh` | the clean-room image and its tiers |
| `requirements-ci.txt` | pinned CI-only test dependencies |
| `change_scopes.yml` | the change-scope taxonomy `ci_plan.py` reads |
| `install_docker_engine_wsl.sh` | one-time Docker Engine install |
| `phase_d_preflight.sh` | run before any long local tier |

**Diagnostic — written to answer one question, kept as evidence:**

| script | question it answered |
| --- | --- |
| `phase_a_writer_matrix.sh` | do the seven evidence-pack writers produce different chart sources? (no — all identical) |
| `phase_a_r2_values.sh` | do the PED calibration R² values move on a sequential rebuild? (no) |
| `phase_a_diff_detail.sh` | which columns differ after regeneration? (none) |
| `phase_a_byte_diff.sh` | then what does differ? (line endings only) |
| `probe_uncertainty_rebuild_reproducibility.sh` | does an uncertainty rebuild reproduce the committed pack? (**no** — `light_petrol_vkt` FY2031-2050 moves 1.34%) |
| `benchmark_test_parallelism.sh` | is xdist safe to adopt? (no — it moved a governed value) |
| `phase2_docker_parity.sh`, `phase2_affected_scopes.sh`, `phase_d_calc_lane_rebuild.sh` | Phase 2/D acceptance drivers |

The diagnostic scripts are kept rather than deleted because their findings are
cited in `docs/FOLLOW_UP_PED_R2_DRIFT.md` and
`artifacts/ci_optimisation/xdist_benchmark.md`, and a finding whose method
cannot be re-run is an anecdote. `probe_uncertainty_rebuild_reproducibility.sh`
in particular should be re-run against the other three packs — that is the first
open question in the follow-up.

None of them run in CI. None are referenced by the workflow or the tiers.

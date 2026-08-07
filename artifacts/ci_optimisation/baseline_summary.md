# Hosted CI baseline

Everything below is measured from GitHub run metadata, not estimated. Run IDs
are given so each figure can be re-checked.

Collected with `python scripts/collect_hosted_ci_baseline.py <run ids>`.

## Reference run

**Run `30906665375`** — push to `main`, `398b78be9ee6`, success, 2026-08-04.

| step | seconds | share of core job |
| --- | --- | --- |
| **Core test suite (pytest)** | **4,165 (69m 25s)** | **93.6%** |
| Conflict scenario extract validation | 120 (2m 00s) | 2.7% |
| GDP sign-guard binding register | 96 (1m 36s) | 2.2% |
| Install dependencies | 32 | 0.7% |
| Streamlit deployment readiness | 12 | 0.3% |
| Report clean-clone coverage | 9 | 0.2% |
| Checkout | 5 | 0.1% |
| Set up Python | 3 | 0.1% |
| Record resolved environment | 2 | 0.0% |
| Compile all sources | 1 | 0.0% |
| Rebuild curated data | 1 | 0.0% |

Core job wall time **1h 14m 09s**. Replay parity: ubuntu **2m 26s**, windows
**2m 28s** (of which dependency install was 28s and 54s respectively).

**The suite is the cost. Dependency installation is 0.7% of it.** Optimising
installation, caching wheels, or slimming the image would have moved nothing.

## Cost per run

GitHub's `/timing` endpoint returns `total_ms: 0` for this repository, so billed
minutes are reconstructed from job start/completion timestamps under GitHub's
documented rules: each job rounds up to the whole minute, Windows bills at 2× the
Ubuntu rate against both the allowance and the invoice.

| run | event | wall | weighted billed min | cost |
| --- | --- | --- | --- | --- |
| `30906665375` | push→main | 1h 14m 29s | 84 | $0.672 |
| `30906467854` | pull_request | 1h 13m 17s | 83 | $0.664 |
| `30871212625` | pull_request | 1h 13m 19s | 85 | $0.680 |
| `30802931456` | push→main | 1h 09m 58s | 81 | $0.648 |

The first two are **the same change**: `feature/revenue-outlook-xlsx-extract`
tested as a PR, then tested again after merge. One completed change therefore
cost **167 weighted minutes and $1.34** — roughly double the consultant's ~$1
estimate, because Windows bills at 2×.

## Seven-day spend

60 CI runs, 2026-07-31 to 2026-08-06:

| outcome | runs | weighted billed minutes | cost |
| --- | --- | --- | --- |
| success | 22 | 1,502 (48.7%) | $12.02 |
| **failure** | 19 | **1,008 (32.7%)** | $8.06 |
| **cancelled / superseded** | 19 | **577 (18.7%)** | $4.62 |
| **total** | **60** | **3,087** | **$24.70** |

| trigger | runs | weighted billed minutes |
| --- | --- | --- |
| pull_request | 47 | 2,317 (75.1%) |
| push (main) | 13 | 770 (24.9%) |

**51.4% of the spend went to runs that were cancelled or had already failed.**
That is the iteration tax: every intermediate push to an open PR started a
74-minute suite, and `cancel-in-progress` killed it when the next push landed.

At ~440 weighted minutes per day, this pace is ~13,200 minutes and ~$105 per
month of hosted time.

## The billing block

**Run `31130362010`** — push to `main` at `e14654ab`, 2026-08-06T23:15:59Z.
All three jobs failed 5–10 seconds after starting, with no steps executed. The
check annotation reads:

> The job was not started because recent account payments have failed or your
> spending limit needs to be increased.

A later run at 23:33 (`31131492536`, the Databricks bundle publish) succeeded, so
the block was lifted within about 18 minutes. But **CI on the current
`origin/main` tip has never completed**, and the spending ceiling was reached in
practice, not in theory.

This is the strongest single argument for the change: the current design does
not merely cost more than it needs to, it has already stopped working once.

## Where the time cannot come from

- **Not dependency install.** 32 seconds, 0.7%.
- **Not checkout or Python setup.** 8 seconds combined.
- **Not the replay jobs.** ~2.5 minutes each, and they are the cheapest genuine
  cross-platform assurance available.
- **Not the GDP sign-guard or extract steps.** 3.6 minutes combined, and both
  are real gates.

It has to come from three places, in this order:

1. **Not running the suite when the diff cannot reach it.** A documentation
   change and a promoted fitted state currently cost the same.
2. **Not running it twice per completed change.** A `pull_request` workflow
   already tests the synthetic merge result.
3. **Not running it on every intermediate push to an open draft.**

Only after those is it worth attacking the 69 minutes themselves.

## Local comparison

The same suite on this machine (20 logical CPUs) is dramatically faster than on
a 2-CPU hosted runner — see `before_after.csv`. Note the local environment is
Python 3.13 / streamlit 1.58 against CI's 3.11 / 1.59, so the local figure is a
timing observation, not a governed-value comparison. That is precisely the gap
`ci/Dockerfile` closes.

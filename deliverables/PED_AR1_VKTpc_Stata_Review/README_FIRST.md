# PED VKT per capita — AR(1) model review pack

**Open [`ONE_PAGE_MODEL_REVIEW.md`](ONE_PAGE_MODEL_REVIEW.md) first.**

## What this is

The complete specification, estimation data and evidence for the production
model that forecasts **quarterly light petrol VKT per capita** in New Zealand.
Supplied so you can independently assess whether the specification is sound.

Self-contained: no repository access, no Python, no Excel, no absolute paths.

## Reading order

| Order | File | Why |
|---|---|---|
| 1 | `ONE_PAGE_MODEL_REVIEW.md` | equation, sample, headline reliability, what to check first |
| 2 | `PED_AR1_MODEL_SPECIFICATION.md` | full spec, exact regressor order, implementation traps, review questions |
| 3 | `ped_ar1_estimation_data.dta` | the estimation dataset, Stata-ready |
| 4 | `replicate_ped_ar1.do` | independent re-estimation and diagnostics |
| 5 | `ped_ar1_backtest_predictions.csv` | rolling-origin forecast evidence |
| 6 | `ped_ar1_diagnostics.csv` | governed diagnostic battery |

## Running the Stata do-file

```
cd "<extracted folder>"
do replicate_ped_ar1.do
```

Outputs land in `results/`. Uses only built-in commands on the main path; KPSS
is skipped gracefully if the community package is absent.

## Two different things, do not conflate them

**Exact production replication** — the coefficients in
`ped_ar1_production_coefficients.csv` and the fitted values in
`ped_ar1_training_reference.csv` are the authoritative production numbers,
reproduced from the committed fitted state to **1.8e-12**.

**Independent Stata re-estimation** — the do-file estimates the same
specification with Stata's own AR(1)-error routines. It will *not* be
bit-identical to statsmodels GLSAR, and it is not meant to be. It answers a
different question: does the specification hold up under independent scrutiny.

## Horizon support — read before quoting any accuracy number

| Range | Status |
|---|---|
| **H1–H12** | governed backtest-supported range |
| **H13–H20** | extended evidence, thinner samples, not validated to the short-term standard |
| **H21+** | not validated to the short-term standard |

## Scope

This pack covers **PED VKT per capita only**. It does not cover the downstream
population, fleet-migration, fuel-efficiency, PED-volume or revenue bridge that
converts this quantity into fuel excise revenue.

## One caution

The model and data are stable and deterministically reproducible. That
establishes everyone is testing the *same* model. It does **not** establish
that the economic specification is correct — that is the question for you.

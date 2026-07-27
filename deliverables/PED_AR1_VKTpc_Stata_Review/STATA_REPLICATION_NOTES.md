# Stata replication notes

## What will and will not match

| Comparison | Expectation |
|---|---|
| `ped_ar1_training_reference.csv` vs the committed state | **exact** — 1.8e-12 |
| Regenerated transforms vs supplied columns (do-file step 2) | **exact** — asserted |
| Stata `prais` vs production GLSAR coefficients | **close, not identical** |
| Stata `arima ..., ar(1)` vs production | close, different likelihood |
| Stata in-sample `predict` vs production forward path | **different by construction** |

## Why `prais` will not equal statsmodels GLSAR

Both estimate a linear model with AR(1) errors, but they differ in:

- **Iteration.** statsmodels `GLSAR.iterative_fit(maxiter=8)` alternates
  ρ-estimation and GLS until 8 iterations. `prais` iterates to convergence by
  default.
- **ρ estimator.** The do-file passes `rhotype(regress)`; statsmodels uses
  Yule–Walker on the OLS residuals. Other `rhotype()` options will move the
  answer.
- **First-observation treatment.** Prais–Winsten retains observation 1 with the
  √(1−ρ²) transform; Cochrane–Orcutt drops it. With 95 observations this is not
  negligible.

Differences in the third or fourth decimal are expected and are not evidence of
an error. Large sign or magnitude differences would be.

## Coefficient order

Intercept, then: `ln_petrol`, `ln_gdp_pc`, `unemp_rate`, `trend`,
`post2011_trend`, `post2020`, `covid2020`, `q2`, `q3`, `q4`, then
`ln_vktpc_l1`. Preserve this when reproducing `Xβ` by hand.

## Sign convention

Residual is `actual − fitted`, in log space. `last_observed_residual` is
therefore the log-space error at 2025Q4, and it initialises the forward AR
recursion as `u_{t+h} = ρ^h · u_last`.

## Production forecasting differs from `predict`

Stata's in-sample `predict` uses the *realised* lagged dependent variable.
Production forecasting is recursive: after the first step it feeds the model's
own prediction back into `ln_vktpc_l1`, and adds the decaying AR term. To
compare against the production forward path you must replicate that recursion,
not use `predict`.

## Diagnostics: two different residual sets

The governed battery in `ped_ar1_diagnostics.csv` is computed on **horizon-1
rolling-origin forecast residuals** — genuine out-of-sample one-step errors.
The do-file's diagnostics run on **in-sample regression residuals**. Both are
informative; they are not interchangeable, and the out-of-sample set is the
harder test.

With a lagged dependent variable, prefer `estat durbinalt` over Durbin–Watson —
DW is biased toward 2 in dynamic models.

# PED VKT per capita — full model specification

Code-derived from `pipeline/ar1_engine.py`, `pipeline/diaglab_arms.py` and
`pipeline/vnext_core.py`. Coefficients extracted programmatically from
`ar1_fitted_state.json`, not transcribed.

| | |
|---|---|
| Model ID | `PED__DIAGLAB__B__glsar__ylag1__ar1__wexp` |
| Scorer version | `ped-ar1-forward-scorer-v1` |
| Algorithm | `glsar_ar1` (statsmodels GLSAR, `iterative_fit`) |
| GLSAR max iterations | 8 |
| AR order | 1 |
| Estimation window | expanding |
| Training sample | 2002Q2 – 2025Q4, **95 observations** |
| Source SHA-256 | `d1955e01e07c74ad5aff08736cc822cd914cfa2df201e1f7dd8872116219a1f9` |
| Training-fit replay delta | **1.819e-12** |

## Dependent variable

`target` — light petrol VKT per capita, km/person/quarter. Modelled as
`ln(target)`. Inverse transformation is plain `exp(·)`; **no smearing or
other retransformation correction is applied**, so level forecasts are
conditional medians, not conditional means.

## Estimating equation

```
ln(VKTpc_t) = β0
            + β1 ·ln(RealPetrolPrice_t)
            + β2 ·ln(RealGDPpc_t)
            + β3 ·UnemploymentRate_t
            + β4 ·Trend_t
            + β5 ·(Post2011_t × Trend_t)
            + β6 ·Post2020_t
            + β7 ·Covid2020_t
            + β8 ·Q2_t + β9·Q3_t + β10·Q4_t
            + β11·ln(VKTpc_{t-1})
            + u_t

u_t = ρ·u_{t-1} + ε_t
```

## Exact regressor order

The design matrix is intercept, then `features` in stored order, then the
target lag. This order must be preserved when reproducing `Xβ`.

| # | Internal name | Delivered column |
|---|---|---|
| 0 | `intercept` | — |
| 1 | `petrol__log` | `log_real_petrol_price` |
| 2 | `gdp_pc__log` | `log_real_gdp_per_capita` |
| 3 | `unemp__level` | `unemployment_rate` |
| 4 | `time__trend` | `trend` |
| 5 | `time__post2011_trend` | `post2011_trend` |
| 6 | `time__post2020` | `post2020` |
| 7 | `time__covid2020` | `covid2020` |
| 8 | `time__q2` | `q2` |
| 9 | `time__q3` | `q3` |
| 10 | `time__q4` | `q4` |
| 11 | `ylag1` | `log_vkt_per_capita_lag1` |

## Implementation details that are easy to misread

These are the traps. Each is stated because reading the equation alone would
lead a reviewer to the wrong construction.

- **Unemployment enters in LEVEL form from `unemployment_rate`, not the logged
  field.** `log_unemployment_rate` exists in the source and is *not* used.
- **`unemployment_rate` is a decimal fraction, not percentage points.** 2002Q1
  is `0.053`, i.e. 5.3%. The companion column `unemployment_percent` holds
  `5.3`. The coefficient +0.13555 therefore applies per *unit* of fraction: a
  1 percentage-point rise (0.01) implies ≈ +0.00136 log points, ≈ +0.14%.
- **`trend` is a quarter counter from 2000Q1**, where 2000Q1 = 1. It is not
  centred and not scaled.
- **`post2011_trend` activates when `year >= 2011`**, regardless of what the
  name suggests about a mid-year switch, and it is the *product* of the
  indicator and the trend, not a separate slope dummy.
- **`post2020` activates when `year >= 2020`** and stays on thereafter.
- **`covid2020` equals 1 only during calendar 2020**, so it overlaps `post2020`
  for four quarters.
- **Q1 is the omitted seasonal category.**
- **The first estimation row is 2002Q2**, because `ln(VKTpc_{t-1})` requires
  2002Q1. The committed history starts 2002Q1.
- **2026Q1 carries `target = 0` as a placeholder** and is excluded from
  estimation. It is retained in `ped_ar1_source_extract.csv` with
  `is_placeholder = 1` so source lineage stays complete.

## Forward recursion

Production forecasting is **recursive, not static**:

1. `ln(VKTpc_{t-1})` for the first forecast quarter is the last actual; for
   later quarters it is the model's own previous *prediction*.
2. The AR(1) error is carried forward as `u_{t+h} = ρ^h · u_last`, initialised
   from `last_observed_residual = 0.018624780347614056`.
3. The level forecast is `exp(Xβ + u_{t+h})`.

This differs from an in-sample Stata `predict`, which uses realised lags. A
Stata comparison will match in-sample fitted values, not the production
forward path.

## Production coefficients

| Term | Value |
|---|---:|
| intercept | 1.938275116572953 |
| `petrol__log` | −0.06279344810503922 |
| `gdp_pc__log` | 0.19655204192734654 |
| `unemp__level` | 0.1355503881837521 |
| `time__trend` | −0.0011749059854803123 |
| `time__post2011_trend` | −0.00011477746243258543 |
| `time__post2020` | −0.02365551448669101 |
| `time__covid2020` | −0.003595669173199312 |
| `time__q2` | 0.0013817954595498755 |
| `time__q3` | 0.009098327298913411 |
| `time__q4` | 0.01941727119929182 |
| `ylag1` | 0.5341842848473402 |
| **ρ** | **0.5233292750642162** |
| last residual | 0.018624780347614056 |

Full precision in `ped_ar1_production_coefficients.csv`.

## Questions the independent reviewer may wish to test

**Stationarity and cointegration.** ln(VKTpc), ln(petrol price) and ln(GDP pc)
are plausibly I(1). The specification is a levels regression with a lagged
dependent variable and a deterministic trend. Is this a cointegrating
relationship, or a spurious levels regression stabilised by the lag? Consider
ADF/KPSS on each series and Engle–Granger or Johansen on the system.

**Lagged dependent variable.** β11 ≈ 0.534 implies a long-run multiplier of
roughly 1/(1−0.534) ≈ 2.15 on each exogenous coefficient. The implied long-run
petrol-price elasticity is therefore ≈ −0.135 — still low against the
literature. Is the short-run/long-run split credible?

**LDV together with AR(1) errors.** With both present, OLS on the LDV is
inconsistent, which is why GLSAR is used — but ρ ≈ 0.523 and β11 ≈ 0.534 are
close in magnitude. Check identification and whether a simpler ARMA or an
error-correction form fits as well.

**Deterministic trend plus breaks.** Trend, post-2011 slope shift and post-2020
level shift together carry substantial explanatory load. Are the break dates
data-driven or imposed? Test with Bai–Perron or a Chow test at alternative
dates.

**Unemployment sign and form.** The coefficient is **positive**. Standard
priors say weaker labour markets reduce commuting. Test log form, lags,
interaction with the trend, and whether the sign flips once post-2020 controls
are removed.

**Parameter stability.** Recursive or rolling estimates, CUSUM/CUSUMSQ.

**Endogeneity.** Petrol price is plausibly endogenous to demand; GDP per capita
likewise. Consider instruments or at least a Hausman-style discussion.

**Retransformation.** `exp(·)` with no smearing gives a conditional median. For
fiscal forecasting the conditional mean is usually wanted. Test a Duan smearing
factor estimated within-fold.

**Recursive forecast stability.** The forward path feeds its own predictions
back through β11 while the AR term decays as ρ^h. Check whether this converges
sensibly or drifts.

**COVID definitions.** `covid2020` covers calendar 2020 only, while the
disruption arguably extends into 2021. Test alternative windows.

**Horizon degradation.** MAPE roughly quadruples from H1 to H12 and signed bias
turns positive and grows. Is that acceptable for the intended use?

I have set these out neutrally. Several are governed choices in the repository,
but being governed is not evidence that they are right — that is the question
this review exists to answer.

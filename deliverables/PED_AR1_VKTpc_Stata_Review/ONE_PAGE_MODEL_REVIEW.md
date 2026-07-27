# PED VKT per capita — AR(1) model, one-page review brief

## What it forecasts

Quarterly **light petrol vehicle kilometres travelled per capita** in New
Zealand. This single quantity feeds a longer chain — population, fleet
migration, fuel efficiency, litres, then fuel excise revenue. **This pack
covers only the VKT-per-capita equation**, not that downstream bridge.

## The equation, in plain language

Log VKT per capita is explained by log real petrol price, log real GDP per
capita, the unemployment rate, a linear time trend with a post-2011 slope
shift, post-2020 and calendar-2020 level shifts, three seasonal dummies, and
**last quarter's log VKT per capita**. The residuals are themselves modelled as
AR(1) — the error carries over from one quarter to the next.

```
ln(VKTpc_t) = β0 + β1·ln(PetrolPrice_t) + β2·ln(RealGDPpc_t) + β3·UnempRate_t
            + β4·Trend_t + β5·(Post2011_t × Trend_t) + β6·Post2020_t
            + β7·Covid2020_t + β8·Q2_t + β9·Q3_t + β10·Q4_t
            + β11·ln(VKTpc_{t-1}) + u_t,        u_t = ρ·u_{t-1} + ε_t
```

Estimated by GLSAR (feasible GLS with AR(1) errors) in log space on an
expanding window.

## Sample

**95 quarterly observations, 2002Q2 – 2025Q4.** The committed history holds 97
rows (2002Q1–2026Q1); 2002Q1 is consumed creating the first lag, and 2026Q1 is
a zero-target placeholder, not an actual.

## Production coefficients

| Term | Value |
|---|---:|
| intercept | 1.93827512 |
| ln(real petrol price) | **−0.06279345** |
| ln(real GDP per capita) | **+0.19655204** |
| unemployment rate | **+0.13555039** |
| trend | −0.00117491 |
| post-2011 × trend | −0.00011478 |
| post-2020 | −0.02365551 |
| covid-2020 | −0.00359567 |
| Q2 / Q3 / Q4 | +0.00138 / +0.00910 / +0.01942 |
| ln(VKTpc)_{t−1} | **+0.53418428** |
| AR(1) ρ | **+0.52332928** |

## Headline reliability

Rolling-origin, actual-driver evaluation (MAPE):

| Horizon | All origins | Balanced cohort | Excl. 2020–21 |
|---|---:|---:|---:|
| H1 | 1.09% | 0.97% | 0.69% |
| H12 | 4.31% | 4.57% | 2.65% |
| H20 | 5.99% | 5.99% | 4.75% |

Signed error is **positive and rising** with horizon (−0.10% at H1 to +4.31% at
H20) — the model tends to over-predict at long horizons.

**H1–H12 is the governed backtest-supported range. H13–H20 has extended but
weaker evidence. H21+ is not validated to the short-term standard.**

## What I would look at first

1. **Positive unemployment coefficient.** +0.136 on a *decimal fraction* rate,
   so +1pp unemployment implies roughly +0.14% VKT per capita. Higher
   unemployment raising driving is economically counterintuitive. Worth testing
   whether it survives specification changes or is absorbing something else.
2. **Lagged dependent variable plus AR(1) errors.** Both are present. β11 ≈
   0.53 and ρ ≈ 0.52 are similar in magnitude — check identification and whether
   the dynamics are over-parameterised.
3. **Deterministic trend with a break.** Trend, post-2011 slope shift and
   post-2020 level shift together do a lot of work. Test whether the series is
   trend-stationary or difference-stationary.
4. **Log-to-level retransformation.** Forecasts are `exp(·)` with no smearing
   correction, so they are conditional medians rather than means.
5. **Small elasticities.** Petrol-price elasticity of −0.063 is low versus most
   published road-fuel demand estimates. Short-run only, given the lagged
   dependent variable, but worth checking the implied long-run value.

## Caveats

- Governance and deterministic reproduction establish that everyone is testing
  the **same** model. They do **not** establish that the economic specification
  is correct — that is exactly what this review is for.
- Standard errors and p-values are **not stored** in the production state. Any
  inference statistics in this pack were regenerated for the handoff.
- The pack is the specification and evidence for the short-term econometric
  model, **not** validation of it as a free-running forecast to 2050.

## Contact

Prepared from repository `main` at merge commit
`bcdf82b9e9049647b733b2e48c5d03eb5b5f4e85`. Model
`PED__DIAGLAB__B__glsar__ylag1__ar1__wexp`, scorer `ped-ar1-forward-scorer-v1`.

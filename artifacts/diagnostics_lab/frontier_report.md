# Diagnostics Lab — frontier report

**Question**: what do we give up in MAPE to satisfy the Diagnostic Pass Matrix?
**Answer (headline)**: for PED, almost nothing — **+0.09pp of quarterly MAPE buys all six core passes**
(3.22% vs the finalist's 3.13%). For Light RUC the incumbent already passes every core test;
removing its advisory Jarque-Bera Watch as well costs **+2.97pp**, which is a bad trade because the
Watch reflects the COVID shock in the backtest errors, not a specification defect.

All numbers are on the governed protocols: MAPE on the schiff-paper rolling-origin grid
(identical origin/target pairs as the finalists), diagnostics on horizon-1 residuals on the
operational evidence grid with the exact governed test formulations and thresholds
(battery verified to full float precision against `diagnostic_test_detail.parquet`;
see `tests/test_diaglab_battery.py`).

---

## PED VKT per capita (finalist: 3.13% quarterly / 1.95% annual, 4/6 core, Overall **Fail**)

| Candidate | Core | JB | Quarterly MAPE | Δ vs finalist | Annual | DW | LB(8) p |
|---|---|---|---|---|---|---|---|
| **`PED__DIAGLAB__B__glsar__ylag1__ar1__wexp`** (recommended) | **6/6** | Watch | **3.22%** | **+0.09pp** | 2.17% | 1.56 | 0.176 |
| `PED__DIAGLAB__B__glsar__ar1__wexp__core` (MAPE champion) | 5/6 (DW fail) | Watch | **2.90%** | **−0.23pp** | 1.92% | 1.31 | 0.054 |
| `PED__DIAGLAB__D__ecm__dylag1__wexp` | 6/6 | Watch | 3.58% | +0.45pp | 2.56% | 1.91 | 0.042 |
| Finalist `PED__VNEXT_SOLVED_CONVEX_TOP2` | 4/6 (DW, White fail) | Watch | 3.13% | — | 1.95% | 1.04 | 0.003 |

**The recommended spec** is a GLSAR — the classic Prais-Winsten-style AR(1)-error GLS — on the
Schiff-style levels specification (log petrol price, log GDP per capita, unemployment, trend,
post-2011 trend, post-2020 and COVID dummies, quarter seasonals) **plus one lagged log-target term
in the mean**. It is interpretable, fully classical, fits in milliseconds, and its horizon-1
backtest residuals genuinely stop being autocorrelated: Ljung-Box(8) p = 0.176, so the DW pass is
not an artifact of the lagged-dependent-variable bias (recorded per the honesty rule).

**The trade-off curve is remarkably flat at the top**: dropping the y-lag gives the best MAPE seen
anywhere (2.90%, better than the ML ensemble finalist) at the price of the one remaining DW
failure (1.31 vs the 1.5 band). In other words the *entire* diagnostics bill for PED is ~0.3pp of
quarterly MAPE, and you can choose where to spend it.

**Jarque-Bera stays a Watch on every competitive spec** (as it does on the finalist). The heavy
tail is the 2020 lockdown quarters in the backtest window; pulse dummies cannot remove them from
*forecast* errors because the model cannot see the shock at the origin. Specs that do pass JB
(none for PED at competitive MAPE) or come close do so by having larger baseline errors that
drown the outliers — normalising by adding noise, which we reject.

Retired arms: ARX-with-lags-only (White/BP persist, recursion degrades long horizons), SARIMAX
(fixes DW but breaks ADF/cointegration — its h1 errors drift), pulse/WLS-on-winner (degraded
core passes). Full trail in `artifacts/diagnostics_lab/ped/round_*/report.md`.

## Light RUC volume (finalist: 5.36% quarterly / 1.27% annual, 6/6 core, Overall **Watch**)

| Candidate | Core | JB | Quarterly MAPE | Δ vs finalist |
|---|---|---|---|---|
| Recipe replica (`R__light_recipe__w36`) | 6/6 | Watch | 5.42% | +0.05pp (replication check ✓) |
| Recipe + pulse / COVID-downweight / regime-WLS | 6/6 | Watch | 5.42–5.46% | remedies do NOT shed the Watch |
| `A__arx__w36__pulse__base` ("all green") | 6/6 | **Pass** | 8.34% | **+2.97pp** |

**Recommendation: keep the incumbent.** Its only blemish is the advisory JB Watch, which is
COVID-shock kurtosis in the backtest percentage errors — structural to the evaluation window, not
to the specification. The only specs that turn JB green pay ~3pp of quarterly MAPE for the
privilege, and they achieve it by being noisier, not better calibrated.

## Heavy RUC volume (sanity check)

The incumbent ensemble passes everything (Overall Pass); classical single-equation challengers
score 10–13% MAPE. Nothing to do.

---

## Postscript: promoted

The recommended candidate was subsequently productionised as the **"AR(1) model" engine**
(dashboard default, switchable back to the "ML ensemble" incumbent). See
`docs/ALTERNATE_ENGINE.md` for the pack architecture and minting scripts.

## Alternate-engine readiness (Phase B input)

`artifacts/diagnostics_lab/<stream>/winners/` carries, for each shortlisted spec, the full
rolling-origin prediction rows (vNext scorecard schema) and a registry-style summary JSON
(algorithm, features, window, hyperparameters, complete battery statistics and scores). If the
PED GLSAR is adopted as an alternate engine, promotion can proceed from these artifacts without
re-estimation. My steer: the +0.09pp candidate is a genuinely credible alternate engine — same
accuracy class as the finalist, all core diagnostics green, and far simpler to explain; the
decision worth making is whether Overall-Watch (JB advisory) reads better to governance than the
current Overall-Fail.

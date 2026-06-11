# Light RUC diagnostic battery - provenance audit

Generated: 2026-06-11 23:28 UTC
Status: **RECONCILED EXACTLY**

## Question

The glass-box drilldown initially could not reproduce the governed Light RUC
diagnostic battery row from the live replayed predictions (e.g. recomputed
Durbin-Watson 1.9569 vs governed 1.8689; recomputed White p 0.0327 vs
governed 0.1229, which would have implied a status flip). This audit
identifies the exact recipe behind the governed row, per the consultant's
instruction: do not change governed values, do not rebuild the model.

## Finding: exact reconciliation (section A)

The governed Light RUC finalist row is reproduced **exactly**
(all 23 quantities, max absolute delta 3.10e-06) from the
current repo-local replayed predictions under the archived parent-run
convention:

- residual = 100 x (forecast - actual) / actual (signed percentage error);
- Breusch-Pagan / White regressors: constant + fitted value (native units),
  with **no** time-index regressor;
- Ljung-Box at raw lags 4, 8, 12;
- lag-1 residual autocorrelation as the Pearson correlation of the residual
  series with its lag (pandas ``Series.autocorr``);
- kurtosis stored as excess kurtosis (raw - 3);
- ARCH LM with 4 lags, ADF with AIC lag selection, KPSS (level, auto lags,
  p clipped to [0.01, 0.10]) - identical to the v7 convention;
- Mincer-Zarnowitz and Engle-Granger cointegration on native-unit
  actual/forecast pairs - identical to the v7 convention.

The earlier mismatch was therefore a **convention artifact, not data drift**:
the prediction pairs are identical (which is why Mincer-Zarnowitz and
cointegration always matched); only the residual unit and heteroscedasticity
regressor set differed. The recomputed "White p = 0.033 would flip Pass to
Fail" concern is dissolved - under the governed convention the White test
p-value is 0.1229 and the governed Pass status is correct as stored.

## Why the v7-convention recomputation differed (section B)

13 of 23 quantities diverge when the v7 native-unit
convention (residual = actual - forecast; hetero regressors fitted value +
time index; Ljung-Box min(L, n//4)) is applied to the same prediction pairs.
Percentage scaling reweights each quarter's residual by 1/actual, which
changes every distribution- and order-sensitive statistic; adding a
time-index regressor changes the Breusch-Pagan/White auxiliary regressions.
Neither recomputation is "wrong" - they answer slightly different questions -
but the governed row was produced under the parent convention, so that is
the convention the glass-box drilldown now displays for Light RUC.

## Schiff benchmark row (section C)

The governed Light RUC Schiff row was computed from the parent run's
``LIGHT_RUC__SCHIFF_SPEC_FINAL_OLS_EXPANDING`` predictions, which are not
retained anywhere in the repository. The surviving Schiff series
(``LIGHT_RUC__SCHIFF_SPEC_FROM_WORKBOOK``) is a deliberately different
implementation (MAPE 7.55 vs the archived row's 6.04), so the archived
benchmark row cannot be re-derived from repo-local data. This row is
**not** used by the diagnostic pass matrix or the drilldown (both are
finalist-scoped); it is retained as archived benchmark context. If it is
ever surfaced in the UI, it should carry an archived-parent provenance
label.

## Governance outcome

1. **No governed value, status, or evidence-pack calculation was changed.**
2. The drilldown build now recomputes Light RUC under the reconciled parent
   convention and asserts equality to the governed battery at 1e-9, the same
   gate PED and Heavy RUC already pass under the v7 convention.
3. Drilldown provenance for Light RUC is upgraded from
   ``archived_parent_values_governed`` to
   ``verified_exact_match_to_governed_battery``, with the recipe documented
   in the audit trace.
4. No diagnostic battery refresh is required: the governed row is exactly
   reproducible from current data. No model rebuild is warranted on
   diagnostic grounds.

## Reproduce

    python scripts/audit_light_ruc_diagnostic_provenance.py

Full quantity-level table: ``light_ruc_diagnostic_reconciliation.csv``.

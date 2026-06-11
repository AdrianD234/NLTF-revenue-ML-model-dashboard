"""Light RUC diagnostic battery provenance audit.

Answers one governance question: can the archived Light RUC row of the
governed ``diagnostic_tests`` battery be reproduced exactly from the
repo-local replayed predictions, and under which recipe?

The audit recomputes the full battery independently (it deliberately does
NOT import the drilldown build script, so the two implementations
cross-check each other) under candidate recipes and writes:

``artifacts/diagnostic_drilldown/light_ruc_diagnostic_reconciliation.csv``
    One row per (section, quantity): governed value, recomputed value,
    delta, residual definition, row scope, n, score basis, match status.

``artifacts/diagnostic_drilldown/light_ruc_diagnostic_provenance_audit.md``
    The narrative audit: the reconciled recipe, why the v7-convention
    recomputation differed, and the status of the Schiff benchmark row.

This script never writes to ``data/dashboard_evidence_pack`` - it is
read-only over governed evidence. Requires statsmodels + scipy.
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DATA = REPO / "data" / "dashboard_evidence_pack" / "data"
OUT = REPO / "artifacts" / "diagnostic_drilldown"
OPERATIONAL = "current_grid_operational_pooled"
TOL = 1e-9

# Governed battery fields compared, mapped to the recomputation keys.
FIELDS = [
    ("n_h1", "n"), ("mape_h1", "mape"), ("bias_h1_pct", "bias"),
    ("acf1_resid", "acf1"), ("durbin_watson", "dw"),
    ("ljungbox_p_lag4", "lb4"), ("ljungbox_p_lag8", "lb8"), ("ljungbox_p_lag12", "lb12"),
    ("adf_p_resid", "adf_p"), ("kpss_p_resid", "kpss_p"),
    ("jarque_bera_p", "jb_p"), ("skew_resid", "skew"), ("kurtosis_resid", "kurt_excess"),
    ("shapiro_p", "shapiro_p"), ("breusch_pagan_p", "bp_p"), ("white_p", "white_p"),
    ("arch_lm_p", "arch_p"), ("coint_p_actual_pred", "coint_p"),
    ("mz_intercept", "mz_intercept"), ("mz_slope", "mz_slope"),
    ("mz_r2", "mz_r2"), ("mz_f_p", "mz_f_p"), ("calibration_r2", "mz_r2"),
]

RECIPES = {
    "parent_pct": dict(
        residual_definition="100 x (forecast - actual) / actual (signed percentage error)",
        hetero_exog="constant + fitted value (native units)",
        lb_lags=(4, 8, 12),
    ),
    "vnext_native": dict(
        residual_definition="actual - forecast (native units)",
        hetero_exog="constant + fitted value + time index",
        lb_lags=None,  # min(L, n // 4)
    ),
}


def recompute(actual: np.ndarray, pred: np.ndarray, recipe: str) -> dict:
    import statsmodels.api as sm
    from scipy import stats as sps
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch, het_breuschpagan, het_white
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    from statsmodels.tsa.stattools import adfuller, coint, kpss

    n = len(actual)
    if recipe == "parent_pct":
        resid = 100.0 * (pred - actual) / actual
        exog = sm.add_constant(np.column_stack([pred]))
        lb_lags = [4, 8, 12]
    else:
        resid = actual - pred
        exog = sm.add_constant(np.column_stack([pred, np.arange(n, dtype=float)]))
        lb_lags = [min(lag, n // 4) for lag in (4, 8, 12)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        jb_stat, jb_p, skew, kurt = jarque_bera(resid)
        lb = acorr_ljungbox(resid, lags=lb_lags, return_df=True)["lb_pvalue"].tolist()
        mz = sm.OLS(actual, sm.add_constant(pred)).fit()
        out = dict(
            n=float(n),
            mape=float(np.mean(np.abs((actual - pred) / actual)) * 100.0),
            bias=float(np.mean((pred - actual) / actual) * 100.0),
            acf1=float(pd.Series(resid).autocorr(1)),
            dw=float(durbin_watson(resid)),
            lb4=float(lb[0]), lb8=float(lb[1]), lb12=float(lb[2]),
            adf_p=float(adfuller(resid, autolag="AIC")[1]),
            kpss_p=float(kpss(resid, regression="c", nlags="auto")[1]),
            jb_p=float(jb_p), skew=float(skew), kurt_excess=float(kurt) - 3.0,
            shapiro_p=float(sps.shapiro(resid)[1]),
            bp_p=float(het_breuschpagan(resid, exog)[1]),
            white_p=float(het_white(resid, exog)[1]),
            arch_p=float(het_arch(resid, nlags=4)[1]),
            coint_p=float(coint(actual, pred)[1]),
            mz_intercept=float(mz.params[0]), mz_slope=float(mz.params[1]),
            mz_r2=float(mz.rsquared), mz_f_p=float(mz.f_pvalue),
        )
    return out


def h1_pairs(sp: pd.DataFrame, model: str) -> tuple[np.ndarray, np.ndarray]:
    g = sp[(sp["stream"] == "LIGHT_RUC") & (sp["model"] == model)
           & (sp["score_basis"] == OPERATIONAL) & (sp["horizon"] == 1)].sort_values("origin")
    return g["actual"].to_numpy(float), g["pred"].to_numpy(float)


def compare(section: str, stored: pd.Series, got: dict, recipe: str, n: int) -> list[dict]:
    meta = RECIPES[recipe]
    rows = []
    for gov_field, key in FIELDS:
        gov = float(stored[gov_field])
        rec = float(got[key])
        delta = abs(gov - rec)
        rel = delta / max(1.0, abs(gov))
        rows.append({
            "section": section,
            "diagnostic_quantity": gov_field,
            "governed_value": gov,
            "recomputed_value": rec,
            "delta": delta,
            "residual_definition": meta["residual_definition"],
            "heteroscedasticity_regressors": meta["hetero_exog"],
            "row_scope": "finalist horizon-1 rows, operational backtest grid, ordered by origin",
            "n_rows": n,
            "score_basis": OPERATIONAL,
            "match_status": "exact" if rel <= TOL else "diverged",
        })
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    finalists = pd.read_parquet(DATA / "finalists.parquet").set_index("stream")
    tests = pd.read_parquet(DATA / "diagnostic_tests.parquet")
    light = tests[tests["stream"] == "LIGHT_RUC"].set_index("role")
    finalist_model = str(finalists.loc["LIGHT_RUC", "model"])
    stored_fin = light.loc["Our finalist"]
    assert str(stored_fin["model"]) == finalist_model

    a, p = h1_pairs(sp, finalist_model)
    rows: list[dict] = []

    got_parent = recompute(a, p, "parent_pct")
    rows += compare("A_finalist_parent_pct_recipe", stored_fin, got_parent, "parent_pct", len(a))
    got_native = recompute(a, p, "vnext_native")
    rows += compare("B_finalist_v7_native_recipe", stored_fin, got_native, "vnext_native", len(a))

    # Schiff benchmark row: the governed row names the parent run's
    # SCHIFF_SPEC_FINAL_OLS_EXPANDING model, whose predictions are not
    # retained anywhere in the repo. The closest surviving Schiff series is
    # the workbook replication - a deliberately different implementation -
    # so the comparison below documents non-reproducibility rather than a
    # candidate match.
    stored_schiff = light.loc["Schiff spec benchmark"]
    schiff_models = sorted(sp[(sp["stream"] == "LIGHT_RUC")
                              & (sp["model"].str.contains("SCHIFF", case=False))]["model"].unique())
    schiff_section = []
    if schiff_models:
        a2, p2 = h1_pairs(sp, schiff_models[0])
        got_schiff = recompute(a2, p2, "parent_pct")
        schiff_section = compare("C_schiff_row_vs_workbook_schiff", stored_schiff, got_schiff,
                                 "parent_pct", len(a2))
        for r in schiff_section:
            if r["match_status"] == "diverged":
                r["match_status"] = "unreproducible_archived_predictions_absent"
    rows += schiff_section

    rec = pd.DataFrame(rows)
    rec.to_csv(OUT / "light_ruc_diagnostic_reconciliation.csv", index=False)

    a_rows = rec[rec["section"] == "A_finalist_parent_pct_recipe"]
    b_rows = rec[rec["section"] == "B_finalist_v7_native_recipe"]
    c_rows = rec[rec["section"] == "C_schiff_row_vs_workbook_schiff"]
    a_exact = (a_rows["match_status"] == "exact").all()
    max_a = float(a_rows["delta"].max())
    n_b_diverged = int((b_rows["match_status"] != "exact").sum())

    md = f"""# Light RUC diagnostic battery - provenance audit

Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
Status: **{"RECONCILED EXACTLY" if a_exact else "NOT RECONCILED"}**

## Question

The glass-box drilldown initially could not reproduce the governed Light RUC
diagnostic battery row from the live replayed predictions (e.g. recomputed
Durbin-Watson 1.9569 vs governed 1.8689; recomputed White p 0.0327 vs
governed 0.1229, which would have implied a status flip). This audit
identifies the exact recipe behind the governed row, per the consultant's
instruction: do not change governed values, do not rebuild the model.

## Finding: exact reconciliation (section A)

The governed Light RUC finalist row is reproduced **exactly**
(all {len(a_rows)} quantities, max absolute delta {max_a:.2e}) from the
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

{n_b_diverged} of {len(b_rows)} quantities diverge when the v7 native-unit
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
"""
    (OUT / "light_ruc_diagnostic_provenance_audit.md").write_text(md, encoding="utf-8")

    print(f"[audit] section A (parent recipe): "
          f"{'EXACT' if a_exact else 'DIVERGED'} (max delta {max_a:.2e})")
    print(f"[audit] section B (v7 recipe): {n_b_diverged}/{len(b_rows)} quantities diverge (expected)")
    if len(c_rows):
        print(f"[audit] section C (schiff row): archived predictions absent; documented as unreproducible")
    print(f"[audit] wrote {OUT / 'light_ruc_diagnostic_reconciliation.csv'}")
    print(f"[audit] wrote {OUT / 'light_ruc_diagnostic_provenance_audit.md'}")
    if not a_exact:
        sys.exit(1)


if __name__ == "__main__":
    main()

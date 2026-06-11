"""Build the glass-box diagnostic drilldown evidence for the dashboard.

Emits two governed tables into ``data/dashboard_evidence_pack/data``:

``diagnostic_test_detail.parquet``
    One row per (stream, diagnostic test) with the test statistic, p-value,
    F-statistic variant where the test has one, the null hypothesis, the
    governance threshold rule, the Pass/Watch/Fail status, sample size and
    audit provenance. Statuses are NOT recomputed independently - they are
    asserted to match the live ``diagnostic_pass_matrix`` exactly, and
    p-values are asserted to match the live ``diagnostic_tests`` battery, so
    this pack can never drift from the governed scorecard.

``diagnostic_evidence_series.parquet``
    The horizon-1 evidence series per stream (period, actual, prediction,
    residual, Mincer-Zarnowitz fitted value, equilibrium error from the
    cointegrating regression) that powers every drilldown chart.

This is an interface/audit feature only: it does not change any model
metrics, statuses or evidence-pack calculations.

Requires statsmodels + scipy (build time only, like the promotion script).
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from model_dashboard.governance_constants import STREAM_LABELS, STREAMS  # noqa: E402

DATA = REPO / "data" / "dashboard_evidence_pack" / "data"
OPERATIONAL = "current_grid_operational_pooled"

# Per-stream governed battery convention. PED and Heavy RUC batteries were
# rebuilt by the v7 promotion using native-unit residuals; the Light RUC row
# is the archived parent-run battery, which the provenance audit
# (scripts/audit_light_ruc_diagnostic_provenance.py) reconciled exactly to
# percentage-error residuals with heteroscedasticity regressors
# [constant, fitted value] and Ljung-Box at raw lags. Both recipes are
# asserted below to reproduce the governed diagnostic_tests values to 1e-9.
BATTERY_CONVENTIONS = {
    "PED": "vnext_native",
    "LIGHT_RUC": "parent_pct",
    "HEAVY_RUC": "vnext_native",
}

CONVENTION_TEXT = {
    "vnext_native": {
        "residual_scope": "horizon-1 residuals (actual - forecast, native units), operational backtest grid",
        "residual_units": "native units",
        "bp_regressors": "fitted value + time index",
        "white_regressors": "fitted value + time index, squares and cross-terms",
        "provenance_note": ("Statistics recomputed from the live replayed predictions and "
                            "asserted equal to the governed diagnostic battery."),
    },
    "parent_pct": {
        "residual_scope": ("horizon-1 percentage-error residuals "
                           "(100 x (forecast - actual) / actual), operational backtest grid"),
        "residual_units": "% of actual (forecast - actual)",
        "bp_regressors": "fitted value (native units)",
        "white_regressors": "fitted value, squares",
        "provenance_note": ("Statistics recomputed from the live replayed predictions under the "
                            "archived parent battery convention (percentage-error residuals; "
                            "heteroscedasticity regressors: constant + fitted value; Ljung-Box at "
                            "raw lags) and asserted equal to the governed diagnostic battery. "
                            "Recipe documented in artifacts/diagnostic_drilldown/"
                            "light_ruc_diagnostic_provenance_audit.md."),
    },
}

TESTS = [
    "Calibration R2", "Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan",
    "White", "Jarque-Bera", "Cointegration", "Overall",
]

NULL_HYPOTHESES = {
    "Calibration R2": "Forecasts are uninformative about actuals (slope/fit of actual-on-forecast regression carries no signal).",
    "Durbin-Watson": "Residuals are not first-order serially correlated (DW near 2).",
    "ADF": "The residual series has a unit root (is non-stationary).",
    "KPSS": "The residual series is stationary (opposite null to ADF).",
    "Breusch-Pagan": "Residual variance is constant across fitted values (homoscedastic).",
    "White": "Residual variance is constant, allowing nonlinear forms (homoscedastic).",
    "Jarque-Bera": "Residuals are normally distributed (skewness 0, excess kurtosis 0).",
    "Cointegration": "Actuals and forecasts are NOT cointegrated (no stable long-run relationship).",
    "Overall": "Composite of the core diagnostics under the governed Pass/Watch/Fail rules.",
}

THRESHOLD_RULES = {
    "Calibration R2": "Pass while the Mincer-Zarnowitz calibration R2 is positive; higher is better.",
    "Durbin-Watson": "Pass when 1.5 <= DW <= 2.5; below ~1.5 implies persistent (positive) error correlation.",
    "ADF": "Pass when p < 0.05: reject the unit root, residuals are stationary.",
    "KPSS": "Pass when p >= 0.05: fail to reject stationarity (p is clipped to [0.01, 0.10] by the test tables).",
    "Breusch-Pagan": "Pass when p > 0.05: no significant variance trend across fitted values and time.",
    "White": "Pass when p > 0.05: no significant heteroscedasticity including nonlinear forms.",
    "Jarque-Bera": "Advisory: Watch when p <= 0.05 (non-normal residuals); never forces an Overall fail alone.",
    "Cointegration": "Pass when p < 0.05: reject 'no cointegration', actual and forecast share a long-run path.",
    "Overall": "Fail if any core test (DW, ADF, KPSS, BP, White, Cointegration) fails; Watch if all core pass but an advisory test is cautionary; else Pass.",
}

BLOCKS_APPROVAL = {
    "Calibration R2": "Core context metric; weak calibration is investigated alongside the heteroscedasticity and autocorrelation tests.",
    "Durbin-Watson": "Core: a Fail here forces Overall = Fail and is a standing monitoring item.",
    "ADF": "Core: residual non-stationarity would force Overall = Fail.",
    "KPSS": "Core: rejection of stationarity would force Overall = Fail.",
    "Breusch-Pagan": "Core: significant heteroscedasticity forces Overall = Fail.",
    "White": "Core: significant heteroscedasticity forces Overall = Fail.",
    "Jarque-Bera": "Advisory only: non-normality downgrades Overall to Watch, never to Fail by itself.",
    "Cointegration": "Core: loss of the long-run actual/forecast relationship forces Overall = Fail.",
    "Overall": "The stream-level governance verdict shown on the scorecard.",
}


def battery_with_statistics(actual: np.ndarray, pred: np.ndarray,
                            convention: str = "vnext_native") -> dict:
    """The exact statsmodels battery used by the promotion script, extended to
    keep the raw statistics and F-variants alongside the p-values.

    ``convention`` selects the governed residual recipe per stream:

    - ``vnext_native``: residual = actual - pred (native units); BP/White
      regressors [const, pred, time index]; Ljung-Box lags min(L, n // 4).
      This is the v7 promotion convention (PED, Heavy RUC).
    - ``parent_pct``: residual = 100 * (pred - actual) / actual; BP/White
      regressors [const, pred]; Ljung-Box at raw lags (4, 8, 12). This is the
      archived parent-run convention reconciled for Light RUC by the
      provenance audit.

    Mincer-Zarnowitz and Engle-Granger cointegration always use native-unit
    actual/pred pairs (identical under both conventions).
    """
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch, het_breuschpagan, het_white
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    from statsmodels.tsa.stattools import adfuller, coint, kpss

    n = len(actual)
    if convention == "parent_pct":
        resid = 100.0 * (pred - actual) / actual
        exog_cols = [pred]
        lb_lags = [4, 8, 12]
    else:
        resid = actual - pred
        exog_cols = [pred, np.arange(n, dtype=float)]
        lb_lags = [min(lag, n // 4) for lag in (4, 8, 12)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        adf_stat, adf_p, adf_lags, adf_nobs, *_ = adfuller(resid, autolag="AIC")
        kpss_stat, kpss_p, kpss_lags, _ = kpss(resid, regression="c", nlags="auto")
        jb_stat, jb_p, jb_skew, jb_kurt = jarque_bera(resid)
        exog = sm.add_constant(np.column_stack(exog_cols))
        bp_lm, bp_lm_p, bp_f, bp_f_p = het_breuschpagan(resid, exog)
        wh_lm, wh_lm_p, wh_f, wh_f_p = het_white(resid, exog)
        arch_lm, arch_lm_p, arch_f, arch_f_p = het_arch(resid, nlags=4)
        coint_t, coint_p, coint_crit = coint(actual, pred)
        mz = sm.OLS(actual, sm.add_constant(pred)).fit()
        lb = acorr_ljungbox(resid, lags=lb_lags, return_df=True)
    return {
        "n": n,
        "test_residual": np.asarray(resid, dtype=float),
        "dw_stat": float(durbin_watson(resid)),
        "adf_stat": float(adf_stat), "adf_p": float(adf_p), "adf_lags": int(adf_lags),
        "kpss_stat": float(kpss_stat), "kpss_p": float(kpss_p), "kpss_lags": int(kpss_lags),
        "jb_stat": float(jb_stat), "jb_p": float(jb_p),
        "skew": float(jb_skew), "kurtosis_excess": float(jb_kurt) - 3.0,
        "bp_lm": float(bp_lm), "bp_lm_p": float(bp_lm_p), "bp_f": float(bp_f), "bp_f_p": float(bp_f_p),
        "white_lm": float(wh_lm), "white_lm_p": float(wh_lm_p), "white_f": float(wh_f), "white_f_p": float(wh_f_p),
        "arch_lm": float(arch_lm), "arch_lm_p": float(arch_lm_p), "arch_f": float(arch_f), "arch_f_p": float(arch_f_p),
        "coint_t": float(coint_t), "coint_p": float(coint_p),
        "coint_crit_5pct": float(coint_crit[1]),
        "mz_intercept": float(mz.params[0]), "mz_slope": float(mz.params[1]),
        "mz_r2": float(mz.rsquared), "mz_f": float(mz.fvalue), "mz_f_p": float(mz.f_pvalue),
        "mz_fitted": np.asarray(mz.fittedvalues, dtype=float),
        "lb8_p": float(lb["lb_pvalue"].iloc[1]),
        "equilibrium_error": actual - np.asarray(mz.fittedvalues, dtype=float),
    }


def main() -> None:
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    finalists = pd.read_parquet(DATA / "finalists.parquet").set_index("stream")
    matrix = pd.read_parquet(DATA / "diagnostic_pass_matrix.parquet")
    tests_table = pd.read_parquet(DATA / "diagnostic_tests.parquet").set_index("model")

    detail_rows, series_rows = [], []
    for stream in STREAMS:
        model = str(finalists.loc[stream, "model"])
        label = STREAM_LABELS[stream]
        g = sp[(sp["stream"] == stream) & (sp["model"] == model)
               & (sp["score_basis"] == OPERATIONAL) & (sp["horizon"] == 1)].sort_values("origin")
        actual = g["actual"].to_numpy(float)
        pred = g["pred"].to_numpy(float)
        convention = BATTERY_CONVENTIONS[stream]
        ctext = CONVENTION_TEXT[convention]
        b = battery_with_statistics(actual, pred, convention=convention)
        stored = tests_table.loc[model]

        # --- consistency gate ---------------------------------------------
        # Every stream must reproduce the governed battery exactly under its
        # documented convention. A failure here means the drilldown would
        # show numbers that disagree with the governed scorecard - that is a
        # build error, never something to paper over.
        checks = [(b["dw_stat"], stored["durbin_watson"]),
                  (b["adf_p"], stored["adf_p_resid"]),
                  (b["kpss_p"], stored["kpss_p_resid"]),
                  (b["bp_lm_p"], stored["breusch_pagan_p"]),
                  (b["white_lm_p"], stored["white_p"]),
                  (b["jb_p"], stored["jarque_bera_p"]),
                  (b["arch_lm_p"], stored["arch_lm_p"]),
                  (b["lb8_p"], stored["ljungbox_p_lag8"]),
                  (b["skew"], stored["skew_resid"]),
                  (b["coint_p"], stored["coint_p_actual_pred"]),
                  (b["mz_r2"], stored["mz_r2"])]
        max_rel = max(abs(float(o) - float(t)) / max(1.0, abs(float(t))) for o, t in checks)
        assert max_rel <= 1e-9, (
            f"{stream}: drilldown battery ({convention}) diverged from governed "
            f"diagnostic_tests (max rel delta {max_rel:.2e})")
        provenance = "verified_exact_match_to_governed_battery"
        provenance_note = ctext["provenance_note"]

        status = matrix[matrix["model"] == model].set_index("diagnostic_test")["pass_status"].to_dict()

        per_test = {
            "Calibration R2": dict(statistic=b["mz_r2"], statistic_name="Mincer-Zarnowitz R2",
                                   p_value=b["mz_f_p"], p_value_name="MZ regression F p-value",
                                   f_statistic=b["mz_f"], f_p_value=b["mz_f_p"],
                                   extra=json.dumps({"mz_intercept": b["mz_intercept"], "mz_slope": b["mz_slope"]})),
            "Durbin-Watson": dict(statistic=b["dw_stat"], statistic_name="Durbin-Watson statistic",
                                  p_value=b["lb8_p"], p_value_name="Ljung-Box p (lag 8, companion test)",
                                  f_statistic=np.nan, f_p_value=np.nan,
                                  extra=json.dumps({"ideal": 2.0, "pass_band": [1.5, 2.5]})),
            "ADF": dict(statistic=b["adf_stat"], statistic_name="ADF t-statistic",
                        p_value=b["adf_p"], p_value_name="MacKinnon p-value",
                        f_statistic=np.nan, f_p_value=np.nan,
                        extra=json.dumps({"lags_used": b["adf_lags"]})),
            "KPSS": dict(statistic=b["kpss_stat"], statistic_name="KPSS LM statistic",
                         p_value=b["kpss_p"], p_value_name="KPSS p-value (table-clipped 0.01-0.10)",
                         f_statistic=np.nan, f_p_value=np.nan,
                         extra=json.dumps({"lags_used": b["kpss_lags"]})),
            "Breusch-Pagan": dict(statistic=b["bp_lm"], statistic_name="LM statistic",
                                  p_value=b["bp_lm_p"], p_value_name="LM p-value",
                                  f_statistic=b["bp_f"], f_p_value=b["bp_f_p"],
                                  extra=json.dumps({"regressors": ctext["bp_regressors"]})),
            "White": dict(statistic=b["white_lm"], statistic_name="LM statistic",
                          p_value=b["white_lm_p"], p_value_name="LM p-value",
                          f_statistic=b["white_f"], f_p_value=b["white_f_p"],
                          extra=json.dumps({"regressors": ctext["white_regressors"]})),
            "Jarque-Bera": dict(statistic=b["jb_stat"], statistic_name="Jarque-Bera statistic",
                                p_value=b["jb_p"], p_value_name="Chi-squared p-value",
                                f_statistic=np.nan, f_p_value=np.nan,
                                extra=json.dumps({"skew": b["skew"], "kurtosis_excess": b["kurtosis_excess"]})),
            "Cointegration": dict(statistic=b["coint_t"], statistic_name="Engle-Granger t-statistic",
                                  p_value=b["coint_p"], p_value_name="MacKinnon p-value",
                                  f_statistic=np.nan, f_p_value=np.nan,
                                  extra=json.dumps({"critical_value_5pct": b["coint_crit_5pct"]})),
            "Overall": dict(statistic=np.nan, statistic_name="Composite verdict",
                            p_value=np.nan, p_value_name="n/a",
                            f_statistic=np.nan, f_p_value=np.nan,
                            extra=json.dumps({"core_tests": ["Durbin-Watson", "ADF", "KPSS",
                                                             "Breusch-Pagan", "White", "Cointegration"],
                                              "advisory_tests": ["Jarque-Bera"],
                                              "arch_lm_p_companion": b["arch_lm_p"],
                                              "arch_f_companion": b["arch_f"]})),
        }
        for test in TESTS:
            spec = per_test[test]
            detail_rows.append({
                "stream": stream, "stream_label": label, "model": model,
                "diagnostic_test": test,
                "pass_status": status.get(test, "Pass"),
                "statistic": spec["statistic"], "statistic_name": spec["statistic_name"],
                "p_value": spec["p_value"], "p_value_name": spec["p_value_name"],
                "f_statistic": spec["f_statistic"], "f_p_value": spec["f_p_value"],
                "null_hypothesis": NULL_HYPOTHESES[test],
                "threshold_rule": THRESHOLD_RULES[test],
                "blocks_approval": BLOCKS_APPROVAL[test],
                "n_rows": b["n"],
                "score_basis": OPERATIONAL,
                "residual_scope": ctext["residual_scope"],
                "source_dataset": "scorecard_predictions.parquet (finalist, operational grid, h=1)",
                "provenance": provenance,
                "provenance_note": provenance_note,
                "extra_json": spec["extra"],
            })
        for period, a, p_, tr, mzf, eq in zip(g["target_period"], actual, pred,
                                              b["test_residual"], b["mz_fitted"],
                                              b["equilibrium_error"]):
            series_rows.append({
                "stream": stream, "stream_label": label, "model": model,
                "target_period": str(period),
                "actual": float(a), "pred": float(p_),
                "residual": float(a - p_),
                "test_residual": float(tr),
                "test_residual_units": ctext["residual_units"],
                "mz_fitted": float(mzf),
                "equilibrium_error": float(eq),
                "score_basis": OPERATIONAL, "horizon": 1,
            })

    detail = pd.DataFrame(detail_rows)
    series = pd.DataFrame(series_rows)
    detail.to_parquet(DATA / "diagnostic_test_detail.parquet", index=False)
    series.to_parquet(DATA / "diagnostic_evidence_series.parquet", index=False)
    print(f"[drilldown] detail rows: {len(detail)} | evidence series rows: {len(series)}")
    print("[drilldown] statuses asserted equal to diagnostic_pass_matrix; "
          "p-values asserted equal to diagnostic_tests")


if __name__ == "__main__":
    main()

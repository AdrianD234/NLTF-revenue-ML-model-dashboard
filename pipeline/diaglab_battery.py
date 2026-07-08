"""Diagnostics Lab battery: governance-replica residual test suite.

Reproduces the evidence pack's diagnostic battery exactly (verified against
``diagnostic_test_detail.parquet`` / ``diagnostic_tests.parquet`` to full
float precision on the shipped finalist residuals):

- Residual scope is **horizon-1 rolling-origin backtest residuals on the
  operational evidence grid** (``score_basis == current_grid_operational_pooled``).
- Residual basis is per-stream: PED uses native units (actual - pred);
  Light/Heavy RUC use percentage errors (100 x (pred - actual) / actual).
- Heteroskedasticity regressors are per-stream: PED regresses on
  [const, fitted, time index]; the RUC streams on [const, fitted].
- KPSS uses regression="c", nlags="auto" (p clipped to [0.01, 0.10]);
  ADF uses autolag="AIC"; Ljung-Box companion at lags 4/8/12; ARCH LM at 4
  lags; cointegration is Engle-Granger between actual and predicted levels;
  calibration is the Mincer-Zarnowitz regression of actuals on predictions.

Threshold rules (from the governed ``threshold_rule`` column, verbatim):
- Durbin-Watson: pass when 1.5 <= DW <= 2.5 (core)
- ADF: pass when p < 0.05 (core)      - KPSS: pass when p >= 0.05 (core)
- Breusch-Pagan / White: pass when p > 0.05 (core)
- Cointegration: pass when p < 0.05 (core)
- Calibration R2: pass while the MZ calibration R2 is positive (context
  metric - NOT part of the Overall verdict)
- Jarque-Bera: advisory - Watch when p <= 0.05, never forces Overall fail
- Overall: Fail if any of the six core tests fail; Watch if all core pass
  but an advisory flags; Pass otherwise.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

CORE_TESTS = ["Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"]
ADVISORY_TESTS = ["Jarque-Bera"]
DISPLAY_TESTS = ["Calibration R2", *CORE_TESTS[:1], "ADF", "KPSS", "Breusch-Pagan", "White", "Jarque-Bera", "Cointegration"]

DW_PASS_BAND = (1.5, 2.5)
P_ALPHA = 0.05

# Per-stream governed conventions (verified against diagnostic_test_detail).
RESIDUAL_BASIS = {"PED": "native", "LIGHT_RUC": "pct_error", "HEAVY_RUC": "pct_error"}
HET_REGRESSORS = {"PED": "fitted_time", "LIGHT_RUC": "fitted", "HEAVY_RUC": "fitted"}


@dataclass
class BatteryResult:
    stream: str
    n: int
    stats: Dict[str, float] = field(default_factory=dict)
    status: Dict[str, str] = field(default_factory=dict)

    @property
    def core_passes(self) -> int:
        return sum(1 for t in CORE_TESTS if self.status.get(t) == "Pass")

    @property
    def core_failures(self) -> List[str]:
        return [t for t in CORE_TESTS if self.status.get(t) == "Fail"]

    @property
    def overall(self) -> str:
        return self.status.get("Overall", "Unavailable")

    def to_row(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {"n_h1": self.n, "core_passes": self.core_passes, "overall": self.overall}
        row.update({f"stat__{k}": v for k, v in self.stats.items()})
        row.update({f"status__{k.replace(' ', '_')}": v for k, v in self.status.items()})
        return row


def residuals_from_pairs(actual: np.ndarray, pred: np.ndarray, basis: str) -> np.ndarray:
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    if basis == "native":
        return actual - pred
    if basis == "pct_error":
        return 100.0 * (pred - actual) / actual
    raise ValueError(f"Unknown residual basis: {basis}")


def run_battery(
    actual: np.ndarray,
    pred: np.ndarray,
    *,
    stream: str,
    residual_basis: Optional[str] = None,
    het_regressors: Optional[str] = None,
    min_n: int = 20,
) -> BatteryResult:
    """Run the full governed battery on horizon-1 (actual, pred) pairs.

    Pairs must be in target-period order (the shipped grids are sorted by
    target key); order matters for the autocorrelation tests.
    """
    import statsmodels.api as sm
    from scipy import stats as sps
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch, het_breuschpagan, het_white
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    from statsmodels.tsa.stattools import adfuller, coint, kpss

    basis = residual_basis or RESIDUAL_BASIS[stream]
    het_mode = het_regressors or HET_REGRESSORS[stream]

    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ok = np.isfinite(actual) & np.isfinite(pred) & (actual != 0)
    actual, pred = actual[ok], pred[ok]
    result = BatteryResult(stream=stream, n=int(len(actual)))
    if len(actual) < min_n:
        result.status = {t: "Unavailable" for t in [*CORE_TESTS, *ADVISORY_TESTS, "Calibration R2", "Overall"]}
        return result

    resid = residuals_from_pairs(actual, pred, basis)
    fitted = pred
    n = len(resid)
    t_index = np.arange(1, n + 1, dtype=float)
    stats_out: Dict[str, float] = {}
    status: Dict[str, str] = {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        dw = float(durbin_watson(resid))
        lb = acorr_ljungbox(resid, lags=[4, 8, 12], return_df=True)
        stats_out["durbin_watson"] = dw
        stats_out["ljungbox_p_lag4"] = float(lb["lb_pvalue"].iloc[0])
        stats_out["ljungbox_p_lag8"] = float(lb["lb_pvalue"].iloc[1])
        stats_out["ljungbox_p_lag12"] = float(lb["lb_pvalue"].iloc[2])
        status["Durbin-Watson"] = "Pass" if DW_PASS_BAND[0] <= dw <= DW_PASS_BAND[1] else "Fail"

        try:
            adf_stat, adf_p, adf_lags, *_ = adfuller(resid, autolag="AIC")
        except Exception:
            adf_stat, adf_p, adf_lags = float("nan"), float("nan"), -1
        stats_out["adf_stat"] = float(adf_stat)
        stats_out["adf_p_resid"] = float(adf_p)
        stats_out["adf_lags"] = float(adf_lags)
        status["ADF"] = "Pass" if np.isfinite(adf_p) and adf_p < P_ALPHA else "Fail"

        try:
            kpss_stat, kpss_p, kpss_lags, _ = kpss(resid, regression="c", nlags="auto")
        except Exception:
            kpss_stat, kpss_p, kpss_lags = float("nan"), float("nan"), -1
        stats_out["kpss_stat"] = float(kpss_stat)
        stats_out["kpss_p_resid"] = float(kpss_p)
        stats_out["kpss_lags"] = float(kpss_lags)
        status["KPSS"] = "Pass" if np.isfinite(kpss_p) and kpss_p >= P_ALPHA else "Fail"

        jb_stat, jb_p, jb_skew, jb_kurt = jarque_bera(resid)
        stats_out["jarque_bera_stat"] = float(jb_stat)
        stats_out["jarque_bera_p"] = float(jb_p)
        stats_out["skew_resid"] = float(jb_skew)
        stats_out["kurtosis_excess"] = float(jb_kurt) - 3.0
        stats_out["shapiro_p"] = float(sps.shapiro(resid).pvalue)
        status["Jarque-Bera"] = "Pass" if jb_p > P_ALPHA else "Watch"

        het_X = (
            sm.add_constant(np.column_stack([fitted, t_index]))
            if het_mode == "fitted_time"
            else sm.add_constant(np.column_stack([fitted]))
        )
        try:
            bp_lm, bp_p, _, _ = het_breuschpagan(resid, het_X)
        except Exception:
            bp_lm, bp_p = float("nan"), float("nan")
        stats_out["breusch_pagan_stat"] = float(bp_lm)
        stats_out["breusch_pagan_p"] = float(bp_p)
        status["Breusch-Pagan"] = "Pass" if np.isfinite(bp_p) and bp_p > P_ALPHA else "Fail"

        try:
            white_lm, white_p, _, _ = het_white(resid, het_X)
        except Exception:
            white_lm, white_p = float("nan"), float("nan")
        stats_out["white_stat"] = float(white_lm)
        stats_out["white_p"] = float(white_p)
        status["White"] = "Pass" if np.isfinite(white_p) and white_p > P_ALPHA else "Fail"

        try:
            arch = het_arch(resid, nlags=4)
            stats_out["arch_lm_p"] = float(arch[1])
        except Exception:
            stats_out["arch_lm_p"] = float("nan")

        try:
            co_stat, co_p, co_crit = coint(actual, pred, trend="c")
            stats_out["coint_stat"] = float(co_stat)
            stats_out["coint_p_actual_pred"] = float(co_p)
            stats_out["coint_crit_5pct"] = float(co_crit[1])
        except Exception:
            stats_out["coint_stat"] = float("nan")
            stats_out["coint_p_actual_pred"] = float("nan")
            stats_out["coint_crit_5pct"] = float("nan")
        status["Cointegration"] = (
            "Pass" if np.isfinite(stats_out["coint_p_actual_pred"]) and stats_out["coint_p_actual_pred"] < P_ALPHA else "Fail"
        )

        try:
            mz = sm.OLS(actual, sm.add_constant(pred)).fit()
            stats_out["mz_r2"] = float(mz.rsquared)
            stats_out["mz_intercept"] = float(mz.params[0])
            stats_out["mz_slope"] = float(mz.params[1])
            stats_out["mz_f_p"] = float(mz.f_pvalue)
        except Exception:
            stats_out["mz_r2"] = float("nan")
        # Context metric only - positive calibration passes; not in Overall.
        status["Calibration R2"] = (
            "Pass" if np.isfinite(stats_out.get("mz_r2", float("nan"))) and stats_out["mz_r2"] > 0 else "Fail"
        )

    core_fail = any(status.get(t) == "Fail" for t in CORE_TESTS)
    advisory_flag = any(status.get(t) in {"Watch", "Fail"} for t in ADVISORY_TESTS)
    if core_fail:
        status["Overall"] = "Fail"
    elif advisory_flag:
        status["Overall"] = "Watch"
    else:
        status["Overall"] = "Pass"

    result.stats = stats_out
    result.status = status
    return result


def finalist_h1_pairs(repo_root, stream: str, model: str) -> pd.DataFrame:
    """Horizon-1 (actual, pred) pairs on the operational grid, target-ordered."""
    from pathlib import Path

    sp = pd.read_parquet(Path(repo_root) / "data" / "dashboard_evidence_pack" / "data" / "scorecard_predictions.parquet")
    sub = sp[
        sp["stream"].astype(str).eq(stream)
        & sp["model"].astype(str).eq(model)
        & sp["horizon"].eq(1)
        & sp["score_basis"].astype(str).eq("current_grid_operational_pooled")
    ].copy()
    sort_col = "target_key" if "target_key" in sub.columns else "target_period"
    return sub.sort_values(sort_col)[["origin", "target_period", "actual", "pred"]].reset_index(drop=True)


def battery_from_predictions(predictions: pd.DataFrame, stream: str, *, h1_keys: Optional[pd.DataFrame] = None) -> BatteryResult:
    """Battery on a candidate's backtest ``predictions`` frame (vNext schema).

    Restricts to horizon-1 rows; when ``h1_keys`` (origin/target_period frame)
    is given, restricts to exactly those governed pairs first so results are
    comparable with the shipped finalist battery.
    """
    d = predictions[predictions["horizon"].eq(1)].copy()
    if h1_keys is not None and not h1_keys.empty:
        d = d.merge(h1_keys[["origin", "target_period"]].drop_duplicates(), on=["origin", "target_period"], how="inner")
    d = d.sort_values("target_period")
    return run_battery(d["actual"].to_numpy(float), d["pred"].to_numpy(float), stream=stream)

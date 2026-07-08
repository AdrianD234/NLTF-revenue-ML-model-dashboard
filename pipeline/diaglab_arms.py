"""Diagnostics Lab arms: candidate families targeting specific residual pathologies.

Each arm is a family of specifications aimed at one diagnostic failure
mechanism, all honouring the vNext conventions (log target, rolling-origin
backtest with recursive predicted target lags, governed evaluation grids):

- A ``arx``     dynamic OLS with selected target lags        -> Durbin-Watson
- B ``glsar``   GLS with AR(p) errors (Prais-Winsten style)  -> Durbin-Watson
- C ``sarimax`` SARIMAX(p,d,q)(P,D,Q)_4 with exog            -> DW + seasonality
- D ``ecm``     error-correction model on differences        -> DW + cointegration
- E weights     WLS layers (COVID downweight / regime var)   -> White, Breusch-Pagan
- F pulses      auto-detected outlier pulse dummies          -> Jarque-Bera
- G ``vnext``   existing sklearn candidates re-tested        -> baseline ML frontier

E and F are composable layers on the classical arms rather than arms of
their own; the orchestrator composes them onto whichever arm's best
candidate still fails the matching test.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from model_dashboard.forecast_runner import (
    LIGHT_RUC_BASE_FEATURES,
    LIGHT_RUC_RESIDUAL_FEATURES,
    LIGHT_RUC_WINDOW,
)
from pipeline import vnext_core as vc
from pipeline.diaglab_battery import BatteryResult, battery_from_predictions

FINALIST_MODELS = {
    "PED": "PED__VNEXT_SOLVED_CONVEX_TOP2",
    "LIGHT_RUC": "dynamic_RESID_GBR_n150_d1_lr0.05_w36",
    "HEAVY_RUC": "HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4",
}

MIN_TRAIN_ROWS = 24
COVID_PERIODS = {f"{y}Q{q}" for y in (2020, 2021) for q in (1, 2, 3, 4)}
PULSE_Z_THRESHOLD = 3.0
MAX_PULSES = 4

# ---------------------------------------------------------------------------
# Feature registry per stream (explicit, governed-column names only)
# ---------------------------------------------------------------------------
FEATURE_GROUPS: Dict[str, Dict[str, List[str]]] = {
    "PED": {
        "levels": ["petrol__log", "gdp_pc__log", "unemp__level"],
        "trend": ["time__trend", "time__post2011_trend", "time__post2020", "time__covid2020"],
        "seasonal": ["time__q2", "time__q3", "time__q4"],
        "policy": [
            "policy__petrol_log_change_1",
            "policy__petrol_log_change_4",
            "policy__petrol_jump_up_1_lag1",
            "policy__petrol_cut_1_lag1",
        ],
        "diffs": ["petrol__log_diff1", "petrol__log_diff4", "gdp_pc__log_diff1", "gdp_pc__log_diff4"],
    },
    "LIGHT_RUC": {
        "levels": ["log_real_diesel_price", "log_real_light_ruc_price", "log_lagged_real_light_ruc_price", "log_real_gdp"],
        "trend": ["post_2020_dummy", "time_trend"],
        "seasonal": ["q2_dummy", "q3_dummy", "q4_dummy"],
        "policy": ["diesel_x_ruc_price", "gdp_x_post2020", "ruc_x_post2020", "diesel_x_post2020"],
        "diffs": [
            "log_real_diesel_price_diff1",
            "log_real_light_ruc_price_diff1",
            "log_real_gdp_diff1",
            "log_real_diesel_price_lag1",
            "log_real_light_ruc_price_lag1",
            "log_real_gdp_lag1",
        ],
    },
    "HEAVY_RUC": {
        "levels": ["gdp__log", "heavy_price__log", "diesel__log"],
        "trend": ["time__post2020"],
        "seasonal": ["time__q2", "time__q3", "time__q4"],
        "policy": ["policy__heavy_price_log_change_1", "policy__diesel_log_change_1"],
        "diffs": ["gdp__log_diff1", "heavy_price__log_diff1", "diesel__log_diff1"],
    },
}
ECM_LEVEL_FEATURES = {
    "PED": ["petrol__log", "gdp_pc__log", "unemp__level"],
    "LIGHT_RUC": ["log_real_diesel_price", "log_real_light_ruc_price", "log_real_gdp"],
    "HEAVY_RUC": ["gdp__log", "heavy_price__log", "diesel__log"],
}


def feature_bundle(stream: str, groups: Sequence[str]) -> Tuple[str, ...]:
    reg = FEATURE_GROUPS[stream]
    out: List[str] = []
    for g in groups:
        for col in reg[g]:
            if col not in out:
                out.append(col)
    return tuple(out)


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------
@dataclass
class DiagData:
    stream: str
    exog: pd.DataFrame              # engineered features indexed by Period
    y_raw: pd.Series
    y_log: pd.Series
    valid: List[pd.Period]


def load_diag_data(repo_root: Path, stream: str) -> DiagData:
    if stream in ("PED", "HEAVY_RUC"):
        sd = vc.load_stream_data(repo_root, stream)
        exog, y_raw, y_log = sd.exog, sd.y_raw, sd.y_log
    else:
        hist = vc.load_history_frame(repo_root, stream)
        y_raw = pd.to_numeric(hist["target"], errors="coerce").astype(float)
        y_log = pd.Series(np.where(y_raw > 0, np.log(y_raw.where(y_raw > 0)), np.nan), index=y_raw.index)
        numeric = hist.apply(pd.to_numeric, errors="coerce")
        exog = numeric.select_dtypes(include=[np.number]).astype(float)
    valid = sorted(p for p in y_raw.index if pd.notna(y_raw.loc[p]) and y_raw.loc[p] > 0)
    return DiagData(stream=stream, exog=exog, y_raw=y_raw, y_log=y_log, valid=valid)


# ---------------------------------------------------------------------------
# Specification
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DiagSpec:
    stream: str
    arm: str                        # A/B/C/D/G
    kind: str                       # arx | glsar | sarimax | ecm | vnext
    features: Tuple[str, ...]
    window: Optional[int]           # None = expanding
    ylags: Tuple[int, ...] = ()     # log-target lags for arx
    params_json: str = "{}"
    weight_mode: Optional[str] = None   # None | covid_down | regime_var (layer E)
    pulses: bool = False                # layer F
    label: str = ""

    @property
    def params(self) -> Dict[str, Any]:
        return json.loads(self.params_json)

    @property
    def name(self) -> str:
        parts = [self.stream, "DIAGLAB", self.arm, self.kind]
        if self.ylags:
            parts.append("ylag" + "-".join(str(l) for l in self.ylags))
        p = self.params
        if p:
            parts.append("_".join(f"{k}{v}" for k, v in sorted(p.items())).replace(".", "p").replace(" ", ""))
        parts.append(f"w{self.window}" if self.window else "wexp")
        if self.weight_mode:
            parts.append(self.weight_mode)
        if self.pulses:
            parts.append("pulse")
        if self.label:
            parts.append(self.label)
        return "__".join(parts)


def compose_weight(spec: DiagSpec, mode: str) -> DiagSpec:
    return replace(spec, weight_mode=mode)


def compose_pulses(spec: DiagSpec) -> DiagSpec:
    return replace(spec, pulses=True)


# ---------------------------------------------------------------------------
# Design-matrix helpers
# ---------------------------------------------------------------------------
def _train_periods(dd: DiagData, origin: pd.Period, window: Optional[int]) -> List[pd.Period]:
    train = [p for p in dd.valid if p <= origin and pd.notna(dd.y_log.loc[p])]
    if window is not None:
        train = train[-int(window):]
    return train


def _design(dd: DiagData, periods: Sequence[pd.Period], features: Sequence[str],
            ylags: Sequence[int], y_hist: Dict[pd.Period, float]) -> Tuple[np.ndarray, List[pd.Period]]:
    rows, used = [], []
    for p in periods:
        vals = [dd.exog.at[p, c] if (p in dd.exog.index and c in dd.exog.columns) else np.nan for c in features]
        for lag in ylags:
            vals.append(y_hist.get(p - lag, np.nan))
        row = np.asarray(vals, dtype=float)
        if np.all(np.isfinite(row)):
            rows.append(row)
            used.append(p)
    if not rows:
        return np.empty((0, len(features) + len(ylags))), []
    return np.vstack(rows), used


def _row_weights(periods: Sequence[pd.Period], mode: Optional[str],
                 base_resid: Optional[np.ndarray] = None) -> np.ndarray:
    n = len(periods)
    w = np.ones(n)
    if mode == "covid_down":
        for i, p in enumerate(periods):
            if vc.period_str(p) in COVID_PERIODS:
                w[i] = 0.25
    elif mode == "regime_var" and base_resid is not None and len(base_resid) == n:
        post = np.array([p.year >= 2020 for p in periods])
        for mask in (post, ~post):
            if mask.sum() >= 4:
                var = float(np.var(base_resid[mask]))
                if var > 0:
                    w[mask] = 1.0 / var
        w = w / w.mean()
    return w


def _wls_fit(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    Xc = np.column_stack([np.ones(len(X)), X])
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(Xc * sw[:, None], y * sw, rcond=None)
    return beta


def _pulse_columns(periods: Sequence[pd.Period], resid: np.ndarray) -> List[pd.Period]:
    if len(resid) < 8:
        return []
    scale = float(np.std(resid, ddof=1))
    if not np.isfinite(scale) or scale <= 0:
        return []
    z = np.abs(resid) / scale
    order = np.argsort(z)[::-1]
    return [periods[i] for i in order if z[i] > PULSE_Z_THRESHOLD][:MAX_PULSES]


# ---------------------------------------------------------------------------
# Per-kind fit + h-step forecast (all in log space)
# ---------------------------------------------------------------------------
def _forecast_arx(dd: DiagData, spec: DiagSpec, origin: pd.Period, horizons: Sequence[pd.Period]) -> Dict[pd.Period, float]:
    y_hist = {p: float(dd.y_log.loc[p]) for p in dd.y_log.index if pd.notna(dd.y_log.loc[p]) and p <= origin}
    train = _train_periods(dd, origin, spec.window)
    X, used = _design(dd, train, spec.features, spec.ylags, y_hist)
    if len(used) < MIN_TRAIN_ROWS:
        return {}
    y = np.array([y_hist[p] for p in used])

    pulse_periods: List[pd.Period] = []
    weights = np.ones(len(used))
    beta = _wls_fit(X, y, weights)
    resid = y - np.column_stack([np.ones(len(X)), X]) @ beta
    if spec.weight_mode:
        weights = _row_weights(used, spec.weight_mode, base_resid=resid)
    if spec.pulses:
        pulse_periods = _pulse_columns(used, resid)
    if spec.weight_mode or pulse_periods:
        Xp = X
        if pulse_periods:
            pulses = np.zeros((len(used), len(pulse_periods)))
            for j, pp in enumerate(pulse_periods):
                pulses[:, j] = [1.0 if p == pp else 0.0 for p in used]
            Xp = np.column_stack([X, pulses])
        beta = _wls_fit(Xp, y, weights)

    out: Dict[pd.Period, float] = {}
    for tp in horizons:
        vals = [dd.exog.at[tp, c] if (tp in dd.exog.index and c in dd.exog.columns) else np.nan for c in spec.features]
        for lag in spec.ylags:
            vals.append(y_hist.get(tp - lag, np.nan))
        vals += [0.0] * len(pulse_periods)
        row = np.asarray(vals, dtype=float)
        if not np.all(np.isfinite(row)):
            continue
        pred_log = float(beta[0] + row @ beta[1:])
        out[tp] = pred_log
        y_hist[tp] = pred_log
    return out


def _forecast_glsar(dd: DiagData, spec: DiagSpec, origin: pd.Period, horizons: Sequence[pd.Period]) -> Dict[pd.Period, float]:
    import statsmodels.api as sm

    y_hist = {p: float(dd.y_log.loc[p]) for p in dd.y_log.index if pd.notna(dd.y_log.loc[p]) and p <= origin}
    train = _train_periods(dd, origin, spec.window)
    X, used = _design(dd, train, spec.features, spec.ylags, y_hist)
    if len(used) < MIN_TRAIN_ROWS:
        return {}
    y = np.array([y_hist[p] for p in used])
    ar_order = int(spec.params.get("ar", 1))

    pulse_cols: List[pd.Period] = []
    if spec.pulses:
        beta0 = _wls_fit(X, y, np.ones(len(y)))
        resid0 = y - np.column_stack([np.ones(len(X)), X]) @ beta0
        pulse_cols = _pulse_columns(used, resid0)
        if pulse_cols:
            pulses = np.zeros((len(used), len(pulse_cols)))
            for j, pp in enumerate(pulse_cols):
                pulses[:, j] = [1.0 if p == pp else 0.0 for p in used]
            X = np.column_stack([X, pulses])

    Xc = sm.add_constant(X)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model = sm.GLSAR(y, Xc, rho=ar_order)
            res = model.iterative_fit(maxiter=8)
        except Exception:
            return {}
    beta = np.asarray(res.params, dtype=float)
    rho = np.atleast_1d(np.asarray(model.rho, dtype=float))
    raw_resid = y - Xc @ beta

    # AR(p) error propagation: e_{T+h} = sum_i rho_i * e_{T+h-i}.
    err_hist = list(raw_resid[-max(len(rho), 1):])
    out: Dict[pd.Period, float] = {}
    for tp in horizons:
        vals = [dd.exog.at[tp, c] if (tp in dd.exog.index and c in dd.exog.columns) else np.nan for c in spec.features]
        for lag in spec.ylags:
            vals.append(y_hist.get(tp - lag, np.nan))
        vals += [0.0] * len(pulse_cols)
        row = np.asarray(vals, dtype=float)
        if not np.all(np.isfinite(row)):
            continue
        err = float(np.dot(rho, err_hist[-len(rho):][::-1])) if len(err_hist) >= len(rho) else 0.0
        pred_log = float(beta[0] + row @ beta[1:]) + err
        err_hist.append(err)
        y_hist[tp] = pred_log
        out[tp] = pred_log
    return out


def _forecast_sarimax(dd: DiagData, spec: DiagSpec, origin: pd.Period, horizons: Sequence[pd.Period]) -> Dict[pd.Period, float]:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    y_hist = {p: float(dd.y_log.loc[p]) for p in dd.y_log.index if pd.notna(dd.y_log.loc[p]) and p <= origin}
    train = _train_periods(dd, origin, spec.window)
    X, used = _design(dd, train, spec.features, (), y_hist)
    if len(used) < MIN_TRAIN_ROWS:
        return {}
    y = np.array([y_hist[p] for p in used])
    p_ = spec.params
    order = tuple(p_.get("order", (1, 0, 0)))
    seasonal = tuple(p_.get("seasonal", (0, 0, 0, 0)))
    trend = "c" if order[1] == 0 and seasonal[1] == 0 else None

    # Contiguity check: SARIMAX needs an unbroken quarterly index.
    if any((used[i + 1] - used[i]).n != 1 for i in range(len(used) - 1)):
        return {}
    steps_needed = max((tp - used[-1]).n for tp in horizons)
    future = [used[-1] + i for i in range(1, steps_needed + 1)]
    Xf_rows = []
    for tp in future:
        vals = [dd.exog.at[tp, c] if (tp in dd.exog.index and c in dd.exog.columns) else np.nan for c in spec.features]
        Xf_rows.append(vals)
    Xf = np.asarray(Xf_rows, dtype=float)
    if not np.all(np.isfinite(Xf)):
        return {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model = SARIMAX(
                y, exog=X, order=order, seasonal_order=seasonal, trend=trend,
                enforce_stationarity=False, enforce_invertibility=False,
            )
            res = model.fit(disp=0, maxiter=200)
            mean = np.asarray(res.get_forecast(steps=steps_needed, exog=Xf).predicted_mean, dtype=float)
        except Exception:
            return {}
    lookup = {tp: mean[i] for i, tp in enumerate(future)}
    return {tp: float(lookup[tp]) for tp in horizons if tp in lookup and np.isfinite(lookup[tp])}


def _forecast_ecm(dd: DiagData, spec: DiagSpec, origin: pd.Period, horizons: Sequence[pd.Period]) -> Dict[pd.Period, float]:
    y_hist = {p: float(dd.y_log.loc[p]) for p in dd.y_log.index if pd.notna(dd.y_log.loc[p]) and p <= origin}
    train = _train_periods(dd, origin, spec.window)
    levels = ECM_LEVEL_FEATURES[dd.stream]
    seasonal = list(FEATURE_GROUPS[dd.stream]["seasonal"])

    Xl, used = _design(dd, train, levels, (), y_hist)
    if len(used) < MIN_TRAIN_ROWS:
        return {}
    y = np.array([y_hist[p] for p in used])
    gamma = _wls_fit(Xl, y, np.ones(len(y)))
    ect = y - np.column_stack([np.ones(len(Xl)), Xl]) @ gamma
    ect_by_period = {p: float(e) for p, e in zip(used, ect)}

    # Delta regression: dy_t ~ const + dX_t + theta * ect_{t-1} + seasonals
    # (+ dy_{t-1} when the dylag remedy is composed for residual persistence).
    use_dylag = int(spec.params.get("dylag", 0)) > 0
    rows, dys, row_periods = [], [], []
    dy_prev_by_period: Dict[pd.Period, float] = {}
    for i in range(1, len(used)):
        p, prev = used[i], used[i - 1]
        if (p - prev).n != 1:
            continue
        dy_prev_by_period[p] = y[i] - y[i - 1]
    for i in range(1, len(used)):
        p, prev = used[i], used[i - 1]
        if (p - prev).n != 1 or prev not in ect_by_period:
            continue
        if use_dylag and prev not in dy_prev_by_period:
            continue
        dx = Xl[i] - Xl[i - 1]
        seas = [dd.exog.at[p, c] if c in dd.exog.columns else 0.0 for c in seasonal]
        extra = [dy_prev_by_period[prev]] if use_dylag else []
        rows.append(np.concatenate([dx, [ect_by_period[prev]], np.asarray(seas, dtype=float), np.asarray(extra, dtype=float)]))
        dys.append(y[i] - y[i - 1])
        row_periods.append(p)
    if len(rows) < MIN_TRAIN_ROWS:
        return {}
    Xd = np.vstack(rows)
    dy = np.asarray(dys, dtype=float)
    weights = _row_weights(row_periods, spec.weight_mode)
    theta = _wls_fit(Xd, dy, weights)

    out: Dict[pd.Period, float] = {}
    last_p, last_y = used[-1], float(y[-1])
    last_ect = float(ect[-1])
    last_dy = float(y[-1] - y[-2]) if len(y) >= 2 else 0.0
    level_row_prev = Xl[-1]
    current = last_p
    while current < max(horizons):
        nxt = current + 1
        vals = [dd.exog.at[nxt, c] if (nxt in dd.exog.index and c in dd.exog.columns) else np.nan for c in levels]
        level_row = np.asarray(vals, dtype=float)
        if not np.all(np.isfinite(level_row)):
            break
        seas = np.asarray([dd.exog.at[nxt, c] if c in dd.exog.columns else 0.0 for c in seasonal], dtype=float)
        extra = np.asarray([last_dy] if use_dylag else [], dtype=float)
        xrow = np.concatenate([level_row - level_row_prev, [last_ect], seas, extra])
        d_pred = float(theta[0] + xrow @ theta[1:])
        last_y = last_y + d_pred
        last_ect = last_y - float(gamma[0] + level_row @ gamma[1:])
        last_dy = d_pred
        if nxt in set(horizons):
            out[nxt] = last_y
        level_row_prev = level_row
        current = nxt
    return out


def _forecast_light_recipe(dd: DiagData, spec: DiagSpec, origin: pd.Period, horizons: Sequence[pd.Period]) -> Dict[pd.Period, float]:
    """The production Light RUC recipe (OLS base + GBM residual correction,
    rolling window 36) with composable pulse/weight remedies on the OLS base.

    Mirrors ``pipeline/vnext_evidence.py`` / ``model_dashboard/forecast_runner.py``.
    """
    from sklearn.ensemble import GradientBoostingRegressor

    y_hist = {p: float(dd.y_log.loc[p]) for p in dd.y_log.index if pd.notna(dd.y_log.loc[p]) and p <= origin}
    window = spec.window if spec.window is not None else LIGHT_RUC_WINDOW
    train = _train_periods(dd, origin, window)
    Xb, used = _design(dd, train, LIGHT_RUC_BASE_FEATURES, (), y_hist)
    if len(used) < MIN_TRAIN_ROWS:
        return {}
    y = np.array([y_hist[p] for p in used])
    Xr, used_r = _design(dd, used, LIGHT_RUC_RESIDUAL_FEATURES, (), y_hist)
    if used_r != used:
        keep = [i for i, p in enumerate(used) if p in set(used_r)]
        Xb, y = Xb[keep], y[keep]
        used = [used[i] for i in keep]
        if len(used) < MIN_TRAIN_ROWS:
            return {}

    weights = np.ones(len(used))
    beta = _wls_fit(Xb, y, weights)
    base_resid = y - np.column_stack([np.ones(len(Xb)), Xb]) @ beta
    pulse_periods: List[pd.Period] = []
    if spec.weight_mode:
        weights = _row_weights(used, spec.weight_mode, base_resid=base_resid)
    if spec.pulses:
        pulse_periods = _pulse_columns(used, base_resid)
    if spec.weight_mode or pulse_periods:
        Xp = Xb
        if pulse_periods:
            pulses = np.zeros((len(used), len(pulse_periods)))
            for j, pp in enumerate(pulse_periods):
                pulses[:, j] = [1.0 if p == pp else 0.0 for p in used]
            Xp = np.column_stack([Xb, pulses])
        beta = _wls_fit(Xp, y, weights)
        base_resid = y - np.column_stack([np.ones(len(Xp)), Xp]) @ beta

    p_ = spec.params
    gbr = GradientBoostingRegressor(
        n_estimators=int(p_.get("n", 150)),
        max_depth=int(p_.get("depth", 1)),
        learning_rate=float(p_.get("lr", 0.05)),
        random_state=vc.RANDOM_STATE,
    )
    gbr.fit(Xr, base_resid)

    out: Dict[pd.Period, float] = {}
    for tp in horizons:
        base_vals = [dd.exog.at[tp, c] if (tp in dd.exog.index and c in dd.exog.columns) else np.nan for c in LIGHT_RUC_BASE_FEATURES]
        resid_vals = [dd.exog.at[tp, c] if (tp in dd.exog.index and c in dd.exog.columns) else np.nan for c in LIGHT_RUC_RESIDUAL_FEATURES]
        base_row = np.asarray(base_vals + [0.0] * len(pulse_periods), dtype=float)
        resid_row = np.asarray(resid_vals, dtype=float)
        if not (np.all(np.isfinite(base_row)) and np.all(np.isfinite(resid_row))):
            continue
        out[tp] = float(beta[0] + base_row @ beta[1:] + gbr.predict(resid_row.reshape(1, -1))[0])
    return out


_FORECASTERS = {
    "arx": _forecast_arx,
    "glsar": _forecast_glsar,
    "sarimax": _forecast_sarimax,
    "ecm": _forecast_ecm,
    "light_recipe": _forecast_light_recipe,
}


# ---------------------------------------------------------------------------
# Backtest + evaluation
# ---------------------------------------------------------------------------
def backtest_spec(dd: DiagData, spec: DiagSpec, origins: Sequence[pd.Period]) -> pd.DataFrame:
    """Rolling-origin backtest producing the vNext predictions schema."""
    if spec.kind == "vnext":
        sd = vc.load_stream_data(Path(spec.params["repo_root"]), spec.stream)
        vspec = vc.make_spec(
            spec.stream, spec.params["vkind"], spec.params.get("vparams", {}),
            spec.window, spec.params.get("feature_set", "dynamic_no_leads"),
            bool(spec.params.get("ylags_flag", True)), "diaglab_G",
            base_feature_set=spec.params.get("base_feature_set", "schiff"),
        )
        preds = vc.backtest(sd, vspec, origins=list(origins)).predictions
        if not preds.empty:
            preds = preds.assign(model=spec.name)
        return preds

    forecaster = _FORECASTERS[spec.kind]
    tset = set(dd.valid)
    records: List[Dict[str, Any]] = []
    for origin in origins:
        horizons = [origin + h for h in range(1, vc.MAX_HORIZON + 1) if (origin + h) in tset]
        if not horizons:
            continue
        try:
            preds_log = forecaster(dd, spec, origin, horizons)
        except Exception:
            preds_log = {}
        for tp, pred_log in preds_log.items():
            pred = float(np.exp(pred_log)) if np.isfinite(pred_log) and pred_log < 700 else np.nan
            records.append(
                {
                    "stream": spec.stream,
                    "model": spec.name,
                    "origin": vc.period_str(origin),
                    "target_period": vc.period_str(tp),
                    "horizon": int((tp - origin).n),
                    "actual": float(dd.y_raw.loc[tp]),
                    "pred": pred,
                }
            )
    return pd.DataFrame(records)


def evaluate_spec(
    dd: DiagData,
    spec: DiagSpec,
    keysets: Dict[str, pd.DataFrame],
    origins: Sequence[pd.Period],
) -> Optional[Dict[str, Any]]:
    """Backtest + battery + paper-grid scores for one candidate spec."""
    preds = backtest_spec(dd, spec, origins)
    if preds.empty:
        return None
    paper_keys = keysets.get(vc.PAPER_SCORE_BASIS)
    oper_keys = keysets.get(vc.OPERATIONAL_SCORE_BASIS)

    battery: BatteryResult = battery_from_predictions(
        preds, spec.stream, h1_keys=oper_keys[oper_keys["horizon"].eq(1)] if oper_keys is not None and "horizon" in oper_keys.columns else oper_keys
    )
    row: Dict[str, Any] = {
        "stream": spec.stream,
        "model": spec.name,
        "arm": spec.arm,
        "kind": spec.kind,
        "window": str(spec.window) if spec.window is not None else "expanding",
        "ylags": ",".join(str(l) for l in spec.ylags),
        "weight_mode": spec.weight_mode or "",
        "pulses": bool(spec.pulses),
        "params_json": spec.params_json,
        "features_json": json.dumps(list(spec.features)),
    }
    if paper_keys is not None and not paper_keys.empty:
        paper = vc.restrict_to_keys(preds, paper_keys)
        score = vc.score_frame(paper, vc.PAPER_SCORE_BASIS)
        row.update(
            {
                "paper_horizon_mean_mape": score["horizon_mean_mape"],
                "paper_pooled_mape": score["quarterly_pooled_mape"],
                "paper_annual_mape": score["annual_mape"],
                "paper_n_pairs": score["n_quarterly_pairs"],
                "mape_h01_04": score["mape_h01_04"],
                "mape_h05_08": score["mape_h05_08"],
                "mape_h09_12": score["mape_h09_12"],
            }
        )
    row.update(battery.to_row())
    return row

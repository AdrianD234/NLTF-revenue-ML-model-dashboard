"""vNext core engine: deterministic features, rolling-origin backtest, dual scorecards.

Governance properties:
- Canonical input basis is ``data/model_input_history/<stream>_inputs.parquet``
  (schema-equal to the forecast input template, so every feature used here is
  computable for future assumption rows).
- All feature engineering is explicit and registered; no fuzzy schema detection.
- All randomness is fixed (``RANDOM_STATE = 42``); float64 everywhere; fixed
  feature column order.
- Target transform: models fit in log space (y = ln(target)), predictions are
  inverted with exp(). Target-lag features use recursive predicted log targets
  beyond the forecast origin (policy: ``recursive_predicted``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

RANDOM_STATE = 42
MAX_HORIZON = 12
MIN_TRAIN_PERIODS = 40          # counted over valid periods (target non-null)
MIN_USABLE_ROWS = 24            # max(20, int(MIN_TRAIN_PERIODS * 0.60))
PARITY_TOLERANCE_ABS = 1e-6
PARITY_TOLERANCE_REL = 1e-9
TARGET_TRANSFORM = "log"        # y_model = ln(target); inverse = exp
LAG_RECURSION_POLICY = "recursive_predicted"
PAPER_SCORE_BASIS = "schiff_paper_horizon_mean"
OPERATIONAL_SCORE_BASIS = "current_grid_operational_pooled"

STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
}
HISTORY_FILES = {
    "PED": "ped_inputs.parquet",
    "LIGHT_RUC": "light_ruc_inputs.parquet",
    "HEAVY_RUC": "heavy_ruc_inputs.parquet",
}
TARGET_COLUMNS = {
    "PED": "target",
    "LIGHT_RUC": "target",
    "HEAVY_RUC": "target",
}

QFREQ = "Q-DEC"

TARGET_LAG_FEATURE_NAMES = [
    "target__lag1",
    "target__lag2",
    "target__lag4",
    "target__diff1",
    "target__diff4",
    "target__roll4_mean",
    "target__roll8_mean",
]

# ---------------------------------------------------------------------------
# Base series registry: canonical history column -> short engineered base name.
# Every base listed here is computable from the forecast input template
# (user-entry columns plus recomputed transforms), so forward scoring of any
# engineered feature below is guaranteed for future assumption rows.
# ---------------------------------------------------------------------------
BASE_SERIES = {
    "HEAVY_RUC": {
        "gdp": "log_real_gdp",
        "diesel": "log_real_diesel_price",
        "heavy_price": "log_real_heavy_ruc_price",
        "light_price": "log_real_light_ruc_price",
        "unemp": "log_unemployment_rate",
    },
    "PED": {
        "gdp_pc": "log_real_gdp_per_capita",
        "petrol": "log_real_petrol_price",
        "unemp": "log_unemployment_rate",
    },
}
LEVEL_SERIES = {
    "HEAVY_RUC": {
        "gdp_level": "real_gdp_sa_nzd",
        "diesel_level": "real_diesel_price_cents_per_litre",
        "heavy_price_level": "real_heavy_ruc_price_nzd_per_1000km",
        "light_price_level": "real_light_ruc_price_nzd_per_1000km",
        "unemp_level": "unemployment_rate",
    },
    "PED": {
        "gdp_pc_level": "real_gdp_per_capita_nzd",
        "petrol_level": "real_petrol_price_cents_per_litre",
        "unemp_level": "unemployment_rate",
        "population_level": "population",
    },
}
# Price bases that receive policy price-shock signals (no leads: governance).
POLICY_PRICE_BASES = {
    "HEAVY_RUC": ["heavy_price", "diesel"],
    "PED": ["petrol"],
}

TIME_FEATURES = [
    "time__trend",
    "time__trend_sq",
    "time__post2011",
    "time__post2011_trend",
    "time__post2020",
    "time__covid2020",
    "time__q2",
    "time__q3",
    "time__q4",
]

SCHIFF_FEATURES = {
    "HEAVY_RUC": [
        "gdp__log",
        "heavy_price__log",
        "time__q2",
        "time__q3",
        "time__q4",
    ],
    "PED": [
        "petrol__log",
        "gdp_pc__log",
        "unemp__level",
        "time__trend",
        "time__post2011_trend",
        "time__post2020",
        "time__covid2020",
        "time__q2",
        "time__q3",
        "time__q4",
    ],
}


def parse_period(value: Any) -> pd.Period:
    return pd.Period(str(value).strip().upper(), freq=QFREQ)


def period_str(p: pd.Period) -> str:
    return f"{p.year}Q{p.quarter}"


@dataclass
class StreamData:
    stream: str
    history: pd.DataFrame              # canonical rows indexed by Period
    exog: pd.DataFrame                 # engineered features indexed by Period
    y_raw: pd.Series                   # level target indexed by Period
    y_log: pd.Series                   # log target (NaN where target <= 0)
    feature_sets: Dict[str, List[str]]
    latest_actual: pd.Period


def load_history_frame(repo_root: Path, stream: str) -> pd.DataFrame:
    path = Path(repo_root) / "data" / "model_input_history" / HISTORY_FILES[stream]
    df = pd.read_parquet(path)
    df = df.copy()
    df["__period__"] = df["period"].map(parse_period)
    df = df.sort_values("__period__").drop_duplicates("__period__", keep="last")
    df = df.set_index("__period__")
    return df


def engineer_features(frame: pd.DataFrame, stream: str) -> pd.DataFrame:
    """Build the engineered exogenous feature matrix.

    ``frame`` must be indexed by Period and contain the canonical input
    columns (history rows, optionally followed by future assumption rows).
    All transforms are computed on the concatenated frame so future rows can
    reach back into history for lags and diffs.
    """
    idx = frame.index
    exog = pd.DataFrame(index=idx)

    # Level and log bases.
    for short, col in LEVEL_SERIES[stream].items():
        s = pd.to_numeric(frame[col], errors="coerce").astype(float)
        exog[f"{short.replace('_level', '')}__level"] = s
    for short, col in BASE_SERIES[stream].items():
        s = pd.to_numeric(frame[col], errors="coerce").astype(float)
        exog[f"{short}__log"] = s
        for lag in (1, 2, 4):
            exog[f"{short}__log_lag{lag}"] = s.shift(lag)
        for d in (1, 4):
            exog[f"{short}__log_diff{d}"] = s.diff(d)

    # Time features (deterministic functions of the period index).
    years = np.array([p.year for p in idx])
    quarters = np.array([p.quarter for p in idx])
    base = pd.Period("2000Q1", freq=QFREQ)
    trend = np.array([(p - base).n + 1 for p in idx], dtype=float)
    exog["time__trend"] = trend
    exog["time__trend_sq"] = trend ** 2
    exog["time__post2011"] = (years >= 2011).astype(float)
    exog["time__post2011_trend"] = exog["time__post2011"] * trend
    exog["time__post2020"] = (years >= 2020).astype(float)
    exog["time__covid2020"] = ((years == 2020)).astype(float)
    for q in (2, 3, 4):
        exog[f"time__q{q}"] = (quarters == q).astype(float)

    # Policy price-shock signals (no lead features: governance rule).
    for short in POLICY_PRICE_BASES[stream]:
        z = exog[f"{short}__log"]
        exog[f"policy__{short}_log_change_1"] = z.diff(1)
        exog[f"policy__{short}_log_change_4"] = z.diff(4)
        exog[f"policy__{short}_jump_up_1"] = z.diff(1).clip(lower=0.0)
        exog[f"policy__{short}_cut_1"] = (-z.diff(1)).clip(lower=0.0)
        exog[f"policy__{short}_abs_change_1"] = z.diff(1).abs()
        for lag in (1, 2, 4):
            for src in (f"policy__{short}_jump_up_1", f"policy__{short}_cut_1", f"policy__{short}_abs_change_1"):
                exog[f"{src}_lag{lag}"] = exog[src].shift(lag)

    return exog


def build_feature_sets(stream: str, exog_columns: Sequence[str]) -> Dict[str, List[str]]:
    cols = list(exog_columns)
    levels = [c for c in cols if c.endswith("__level")]
    logs = [c for c in cols if c.endswith("__log")]
    log_lags = [c for c in cols if "__log_lag" in c]
    log_diffs = [c for c in cols if "__log_diff" in c]
    time_cols = [c for c in TIME_FEATURES if c in cols]
    policy_cols = [c for c in cols if c.startswith("policy__")]
    schiff = [c for c in SCHIFF_FEATURES[stream] if c in cols]

    sets: Dict[str, List[str]] = {
        "schiff": schiff,
        "static": _dedupe(logs + levels + time_cols),
        "diff": _dedupe(logs + levels + log_diffs + time_cols),
        "dynamic_no_leads": _dedupe(logs + levels + log_diffs + log_lags + time_cols + policy_cols),
    }
    return sets


def _dedupe(seq: Iterable[str]) -> List[str]:
    seen: List[str] = []
    for s in seq:
        if s not in seen:
            seen.append(s)
    return seen


def load_stream_data(repo_root: Path, stream: str) -> StreamData:
    hist = load_history_frame(repo_root, stream)
    exog = engineer_features(hist, stream)
    y_raw = pd.to_numeric(hist[TARGET_COLUMNS[stream]], errors="coerce").astype(float)
    y_log = pd.Series(np.where(y_raw > 0, np.log(y_raw.where(y_raw > 0)), np.nan), index=y_raw.index)
    latest_actual = y_raw[y_raw > 0].index.max()
    return StreamData(
        stream=stream,
        history=hist,
        exog=exog,
        y_raw=y_raw,
        y_log=y_log,
        feature_sets=build_feature_sets(stream, exog.columns),
        latest_actual=latest_actual,
    )


# ---------------------------------------------------------------------------
# Candidate specification and estimators
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateSpec:
    stream: str
    name: str
    model_kind: str                  # ols | ridge | elastic_net | gbr | resid_gbr
    params_json: str                 # estimator hyperparameters (sorted JSON)
    window: Optional[int]            # rolling window in valid periods; None = expanding
    feature_set: str
    include_target_lags: bool
    family_tag: str
    base_feature_set: str = "schiff"  # OLS base features for resid_gbr

    @property
    def params(self) -> Dict[str, Any]:
        return json.loads(self.params_json)


def make_spec(stream: str, kind: str, params: Dict[str, Any], window: Optional[int],
              feature_set: str, ylags: bool, family_tag: str,
              base_feature_set: str = "schiff") -> CandidateSpec:
    pj = json.dumps(dict(sorted(params.items())), sort_keys=True)
    ptxt = "_".join(f"{k}{v}" for k, v in sorted(params.items()) if k not in ("random_state", "max_iter", "loss", "subsample"))
    ptxt = ptxt.replace(".", "p") or "default"
    wtxt = f"w{window}" if window is not None else "wexp"
    ytxt = "ylag" if ylags else "noylag"
    name = f"{stream}__VNEXT__{feature_set}__{kind}_{ptxt}__{ytxt}__{wtxt}"
    return CandidateSpec(stream, name, kind, pj, window, feature_set, ylags, family_tag, base_feature_set)


def make_estimator(kind: str, params: Dict[str, Any]):
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import ElasticNet, LinearRegression, Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if kind == "ols":
        return Pipeline([("model", LinearRegression(**params))])
    if kind == "ridge":
        return Pipeline([("scale", StandardScaler()), ("model", Ridge(**params))])
    if kind == "elastic_net":
        return Pipeline([("scale", StandardScaler()), ("model", ElasticNet(**params))])
    if kind == "gbr":
        return Pipeline([("model", GradientBoostingRegressor(**params))])
    raise ValueError(f"Unknown estimator kind: {kind}")


def target_lag_row(period: pd.Period, y_hist: Dict[pd.Period, float]) -> Dict[str, float]:
    def get(p: pd.Period) -> float:
        v = y_hist.get(p, np.nan)
        return float(v) if np.isfinite(v) else np.nan

    y1, y2, y4, y5 = get(period - 1), get(period - 2), get(period - 4), get(period - 5)
    last4 = np.array([get(period - i) for i in range(1, 5)], dtype=float)
    last8 = np.array([get(period - i) for i in range(1, 9)], dtype=float)
    return {
        "target__lag1": y1,
        "target__lag2": y2,
        "target__lag4": y4,
        "target__diff1": y1 - y2 if np.isfinite(y1) and np.isfinite(y2) else np.nan,
        "target__diff4": y1 - y5 if np.isfinite(y1) and np.isfinite(y5) else np.nan,
        "target__roll4_mean": float(np.nanmean(last4)) if np.isfinite(last4).sum() >= 2 else np.nan,
        "target__roll8_mean": float(np.nanmean(last8)) if np.isfinite(last8).sum() >= 4 else np.nan,
    }


def feature_columns(sd: StreamData, spec: CandidateSpec) -> List[str]:
    cols = list(sd.feature_sets[spec.feature_set])
    if spec.include_target_lags:
        cols += TARGET_LAG_FEATURE_NAMES
    return cols


def build_row(period: pd.Period, exog: pd.DataFrame, y_hist: Dict[pd.Period, float],
              cols: Sequence[str], include_target_lags: bool) -> Dict[str, float]:
    row: Dict[str, float] = {}
    if period in exog.index:
        row.update(exog.loc[period].to_dict())
    if include_target_lags:
        row.update(target_lag_row(period, y_hist))
    return {c: row.get(c, np.nan) for c in cols}


def build_matrix(periods: Sequence[pd.Period], exog: pd.DataFrame, y_log: pd.Series,
                 cols: Sequence[str], include_target_lags: bool) -> Tuple[pd.DataFrame, pd.Series]:
    y_hist = {p: float(y_log.loc[p]) for p in y_log.index if pd.notna(y_log.loc[p])}
    rows, ys, used = [], [], []
    for p in periods:
        if p not in y_log.index or pd.isna(y_log.loc[p]):
            continue
        rows.append(build_row(p, exog, y_hist, cols, include_target_lags))
        ys.append(float(y_log.loc[p]))
        used.append(p)
    X = pd.DataFrame(rows, index=used).reindex(columns=list(cols)).astype(float)
    y = pd.Series(ys, index=used, name="y_log", dtype=float)
    return X, y


@dataclass
class FittedComponent:
    spec: CandidateSpec
    origin: pd.Period
    model: Any                              # estimator or {"base":..., "resid":...}
    feature_cols: List[str]
    base_cols: List[str]
    all_na_cols: List[str]
    base_all_na_cols: List[str]
    X_train: pd.DataFrame
    X_train_base: Optional[pd.DataFrame]
    y_train: pd.Series


def fit_at_origin(sd: StreamData, spec: CandidateSpec, origin: pd.Period) -> Optional[FittedComponent]:
    valid = valid_periods(sd)
    train_periods = [p for p in valid if p <= origin]
    if len(train_periods) < MIN_TRAIN_PERIODS:
        return None
    if spec.window is not None:
        train_periods = train_periods[-int(spec.window):]

    cols = feature_columns(sd, spec)
    X, y = build_matrix(train_periods, sd.exog, sd.y_log, cols, spec.include_target_lags)
    if len(X) < MIN_USABLE_ROWS:
        return None
    all_na = [c for c in X.columns if X[c].isna().all()]
    if all_na:
        X = X.copy()
        X[all_na] = 0.0
    X = X.fillna(0.0)

    base_cols = list(sd.feature_sets[spec.base_feature_set])
    X_base = None
    base_all_na: List[str] = []
    if spec.model_kind == "resid_gbr":
        X_base, _ = build_matrix(train_periods, sd.exog, sd.y_log, base_cols, False)
        X_base = X_base.reindex(index=X.index)
        base_all_na = [c for c in X_base.columns if X_base[c].isna().all()]
        if base_all_na:
            X_base = X_base.copy()
            X_base[base_all_na] = 0.0
        X_base = X_base.fillna(0.0)

    if spec.model_kind == "resid_gbr":
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.linear_model import LinearRegression

        base = LinearRegression()
        base.fit(X_base.to_numpy(dtype=float), y.to_numpy(dtype=float))
        resid = y.to_numpy(dtype=float) - base.predict(X_base.to_numpy(dtype=float))
        rm = GradientBoostingRegressor(**spec.params)
        rm.fit(X.to_numpy(dtype=float), resid)
        model: Any = {"kind": "residual", "base": base, "resid": rm}
    else:
        model = make_estimator(spec.model_kind, spec.params)
        model.fit(X.to_numpy(dtype=float), y.to_numpy(dtype=float))

    return FittedComponent(spec, origin, model, list(X.columns), base_cols, all_na, base_all_na, X, X_base, y)


def predict_one(fc: FittedComponent, row: Dict[str, float], base_row: Optional[Dict[str, float]]) -> float:
    xp = pd.DataFrame([row]).reindex(columns=fc.feature_cols).astype(float)
    if fc.all_na_cols:
        xp[fc.all_na_cols] = 0.0
    xp = xp.fillna(0.0)
    if isinstance(fc.model, dict) and fc.model.get("kind") == "residual":
        xb = pd.DataFrame([base_row]).reindex(columns=fc.base_cols).astype(float)
        if fc.base_all_na_cols:
            xb[fc.base_all_na_cols] = 0.0
        xb = xb.fillna(0.0)
        return float(fc.model["base"].predict(xb.to_numpy(dtype=float))[0]
                     + fc.model["resid"].predict(xp.to_numpy(dtype=float))[0])
    return float(fc.model.predict(xp.to_numpy(dtype=float))[0])


def valid_periods(sd: StreamData) -> List[pd.Period]:
    idx = [p for p in sd.y_raw.index if pd.notna(sd.y_raw.loc[p])]
    return sorted(set(idx).intersection(sd.exog.index))


def positive_target_periods(sd: StreamData) -> List[pd.Period]:
    """Periods eligible as backtest targets: positive actuals only (zero-actual
    rows are excluded from MAPE in the governed evidence pack)."""
    idx = [p for p in sd.y_raw.index if pd.notna(sd.y_raw.loc[p]) and sd.y_raw.loc[p] > 0]
    return sorted(set(idx).intersection(sd.exog.index))


def backtest_origins(sd: StreamData) -> List[pd.Period]:
    valid = valid_periods(sd)
    tset = set(positive_target_periods(sd))
    out = []
    for origin in valid:
        train = [p for p in valid if p <= origin]
        if len(train) >= MIN_TRAIN_PERIODS and any((origin + h) in tset for h in range(1, MAX_HORIZON + 1)):
            out.append(origin)
    return out


@dataclass
class BacktestResult:
    predictions: pd.DataFrame
    states: List[FittedComponent] = field(default_factory=list)
    prediction_rows: Optional[pd.DataFrame] = None       # exact engineered rows used
    base_prediction_rows: Optional[pd.DataFrame] = None  # OLS-base rows for resid_gbr


def backtest(sd: StreamData, spec: CandidateSpec,
             keep_states: bool = False,
             origins: Optional[Sequence[pd.Period]] = None) -> BacktestResult:
    """Rolling-origin backtest with recursive predicted target lags."""
    vset = set(positive_target_periods(sd))
    use_origins = list(origins) if origins is not None else backtest_origins(sd)
    records: List[Dict[str, Any]] = []
    states: List[FittedComponent] = []
    row_records: List[Dict[str, Any]] = []
    base_row_records: List[Dict[str, Any]] = []
    cols = feature_columns(sd, spec)
    base_cols = list(sd.feature_sets[spec.base_feature_set])

    for origin in use_origins:
        fc = fit_at_origin(sd, spec, origin)
        if fc is None:
            continue
        if keep_states:
            states.append(fc)
        y_hist = {p: float(sd.y_log.loc[p]) for p in sd.y_log.index
                  if pd.notna(sd.y_log.loc[p]) and p <= origin}
        for h in range(1, MAX_HORIZON + 1):
            tp = origin + h
            if tp not in vset or pd.isna(sd.y_raw.loc[tp]):
                continue
            row = build_row(tp, sd.exog, y_hist, cols, spec.include_target_lags)
            base_row = build_row(tp, sd.exog, y_hist, base_cols, False) if spec.model_kind == "resid_gbr" else None
            if keep_states:
                row_records.append({"model": spec.name, "origin": period_str(origin),
                                    "target_period": period_str(tp), "horizon": h, **row})
                if base_row is not None:
                    base_row_records.append({"model": spec.name, "origin": period_str(origin),
                                             "target_period": period_str(tp), "horizon": h, **base_row})
            try:
                pred_log = predict_one(fc, row, base_row)
            except Exception:
                pred_log = np.nan
            pred = float(np.exp(pred_log)) if np.isfinite(pred_log) and pred_log < 700 else np.nan
            if np.isfinite(pred_log):
                y_hist[tp] = pred_log
            actual = float(sd.y_raw.loc[tp])
            records.append({
                "stream": spec.stream,
                "model": spec.name,
                "model_kind": spec.model_kind,
                "feature_set": spec.feature_set,
                "family_tag": spec.family_tag,
                "include_target_lags": spec.include_target_lags,
                "window": "expanding" if spec.window is None else int(spec.window),
                "params_json": spec.params_json,
                "origin": period_str(origin),
                "target_period": period_str(tp),
                "horizon": h,
                "actual": actual,
                "pred": pred,
                "pred_log": pred_log,
            })
    return BacktestResult(
        predictions=pd.DataFrame(records),
        states=states,
        prediction_rows=pd.DataFrame(row_records) if row_records else None,
        base_prediction_rows=pd.DataFrame(base_row_records) if base_row_records else None,
    )


# ---------------------------------------------------------------------------
# Evaluation grids and metrics
# ---------------------------------------------------------------------------

def load_eval_keysets(repo_root: Path, stream: str, finalist_model: str) -> Dict[str, pd.DataFrame]:
    """Exact stored (origin, target_period) key grids per score basis, from the
    governed evidence pack. Guarantees comparability with incumbent finalists
    and the Schiff specification benchmark."""
    sp = pd.read_parquet(Path(repo_root) / "data" / "dashboard_evidence_pack" / "data" / "scorecard_predictions.parquet")
    sp = sp[sp["stream"].astype(str).eq(stream)]
    fin = sp[sp["model"].astype(str).eq(finalist_model)]
    out: Dict[str, pd.DataFrame] = {}
    for basis, g in fin.groupby("score_basis"):
        out[str(basis)] = g[["origin", "target_period", "horizon", "actual"]].drop_duplicates(
            subset=["origin", "target_period"]).reset_index(drop=True)
    return out


def load_schiff_predictions(repo_root: Path, stream: str) -> pd.DataFrame:
    sp = pd.read_parquet(Path(repo_root) / "data" / "dashboard_evidence_pack" / "data" / "scorecard_predictions.parquet")
    sp = sp[sp["stream"].astype(str).eq(stream)]
    schiff = sp[sp["model"].astype(str).str.contains("SCHIFF_SPEC_FROM_WORKBOOK")]
    return schiff[["score_basis", "origin", "target_period", "horizon", "actual", "pred"]].rename(
        columns={"pred": "schiff_pred"})


def restrict_to_keys(preds: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    merged = preds.merge(keys[["origin", "target_period"]], on=["origin", "target_period"], how="inner")
    return merged


def mape(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.isfinite(actual) & np.isfinite(pred) & (actual != 0)
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((pred[mask] - actual[mask]) / actual[mask])) * 100.0)


def bias_pct(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.isfinite(actual) & np.isfinite(pred) & (actual != 0)
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean((pred[mask] - actual[mask]) / actual[mask]) * 100.0)


def p90_ape(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.isfinite(actual) & np.isfinite(pred) & (actual != 0)
    if mask.sum() == 0:
        return float("nan")
    return float(np.percentile(np.abs((pred[mask] - actual[mask]) / actual[mask]) * 100.0, 90))


def horizon_mapes(df: pd.DataFrame) -> Dict[int, float]:
    out = {}
    for h in range(1, MAX_HORIZON + 1):
        g = df[df["horizon"] == h]
        out[h] = mape(g["actual"].to_numpy(float), g["pred"].to_numpy(float)) if len(g) else float("nan")
    return out


def annual_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Per (origin, target_year) sums where all 4 quarters of the year are present."""
    d = df.copy()
    d["target_year"] = d["target_period"].str.slice(0, 4).astype(int)
    rows = []
    for (origin, year), g in d.groupby(["origin", "target_year"]):
        if g["target_period"].nunique() == 4 and g["pred"].notna().all():
            rows.append({
                "origin": origin, "target_year": year,
                "annual_actual": float(g["actual"].sum()),
                "annual_pred": float(g["pred"].sum()),
            })
    return pd.DataFrame(rows)


def score_frame(df: pd.DataFrame, basis: str) -> Dict[str, Any]:
    a = df["actual"].to_numpy(float)
    p = df["pred"].to_numpy(float)
    hm = horizon_mapes(df)
    hvals = [v for v in hm.values() if np.isfinite(v)]
    ap = annual_pairs(df)
    out = {
        "score_basis": basis,
        "n_quarterly_pairs": int(df["pred"].notna().sum()),
        "n_origins": int(df["origin"].nunique()),
        "quarterly_pooled_mape": mape(a, p),
        "horizon_mean_mape": float(np.mean(hvals)) if hvals else float("nan"),
        "quarterly_bias_pct": bias_pct(a, p),
        "quarterly_p90_ape": p90_ape(a, p),
        "n_annual_pairs": int(len(ap)),
        "annual_mape": mape(ap["annual_actual"].to_numpy(float), ap["annual_pred"].to_numpy(float)) if len(ap) else float("nan"),
        "annual_bias_pct": bias_pct(ap["annual_actual"].to_numpy(float), ap["annual_pred"].to_numpy(float)) if len(ap) else float("nan"),
        "annual_p90_ape": p90_ape(ap["annual_actual"].to_numpy(float), ap["annual_pred"].to_numpy(float)) if len(ap) else float("nan"),
    }
    for h in range(1, MAX_HORIZON + 1):
        out[f"mape_h{h:02d}"] = hm[h]
    for label, lo, hi in (("mape_h01_04", 1, 4), ("mape_h05_08", 5, 8), ("mape_h09_12", 9, 12)):
        vals = [hm[h] for h in range(lo, hi + 1) if np.isfinite(hm[h])]
        out[label] = float(np.mean(vals)) if vals else float("nan")
    return out


def forecast_r2(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.isfinite(actual) & np.isfinite(pred)
    a, p = actual[mask], pred[mask]
    if len(a) < 2:
        return float("nan")
    sst = float(np.sum((a - a.mean()) ** 2))
    if sst <= 0:
        return float("nan")
    return float(1 - np.sum((a - p) ** 2) / sst)


def calibration_r2(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = np.isfinite(actual) & np.isfinite(pred)
    a, p = actual[mask], pred[mask]
    if len(a) < 2 or np.var(p) <= 0 or np.var(a) <= 0:
        return float("nan")
    x = np.column_stack([np.ones(len(p)), p])
    coef = np.linalg.lstsq(x, a, rcond=None)[0]
    fitted = x @ coef
    return float(1 - np.sum((a - fitted) ** 2) / np.sum((a - a.mean()) ** 2))


def paired_win_rate(preds: pd.DataFrame, schiff: pd.DataFrame, basis: str) -> float:
    s = schiff[schiff["score_basis"].astype(str).eq(basis)]
    m = preds.merge(s[["origin", "target_period", "schiff_pred"]], on=["origin", "target_period"], how="inner")
    m = m[m["pred"].notna() & m["schiff_pred"].notna() & m["actual"].ne(0)]
    if m.empty:
        return float("nan")
    cand = np.abs((m["pred"] - m["actual"]) / m["actual"])
    sch = np.abs((m["schiff_pred"] - m["actual"]) / m["actual"])
    return float((cand < sch).mean() * 100.0)


def stress_buckets(df: pd.DataFrame, basis: str, stream: str) -> pd.DataFrame:
    d = df.copy()
    d["target_year"] = d["target_period"].str.slice(0, 4).astype(int)
    rows = []

    def bucket(label: str, g: pd.DataFrame, annual: bool = False) -> None:
        if annual:
            ap = annual_pairs(g)
            rows.append({"stream": stream, "stream_label": STREAM_LABELS[stream], "score_basis": basis,
                         "stress_bucket": label,
                         "mape": mape(ap["annual_actual"].to_numpy(float), ap["annual_pred"].to_numpy(float)) if len(ap) else float("nan"),
                         "bias_pct": bias_pct(ap["annual_actual"].to_numpy(float), ap["annual_pred"].to_numpy(float)) if len(ap) else float("nan"),
                         "n": int(len(ap))})
        else:
            rows.append({"stream": stream, "stream_label": STREAM_LABELS[stream], "score_basis": basis,
                         "stress_bucket": label,
                         "mape": mape(g["actual"].to_numpy(float), g["pred"].to_numpy(float)) if len(g) else float("nan"),
                         "bias_pct": bias_pct(g["actual"].to_numpy(float), g["pred"].to_numpy(float)) if len(g) else float("nan"),
                         "n": int(g["pred"].notna().sum())})

    bucket("1-4 qtrs", d[d["horizon"].between(1, 4)])
    bucket("5-8 qtrs", d[d["horizon"].between(5, 8)])
    bucket("9-12 qtrs", d[d["horizon"].between(9, 12)])
    bucket("2024+", d[d["target_year"] >= 2024])
    bucket("2022-23", d[d["target_year"].between(2022, 2023)])
    bucket("Annual", d, annual=True)
    return pd.DataFrame(rows)

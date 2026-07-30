"""AR(1) alternate engine for PED: production fit, forward scorer, replay parity.

The engine productionises the Diagnostics Lab winner
``PED__DIAGLAB__B__glsar__ylag1__ar1__wexp`` — a GLSAR (AR(1)-error GLS,
Prais-Winsten style) on the Schiff-style levels specification plus one lagged
log-target term, expanding window, log target. It passes all six core
diagnostic tests on the governed battery at 3.22% paper-grid horizon-mean
MAPE (finalist ensemble: 3.13%, Durbin-Watson + White failures).

Design mirrors the vNext forward scorer contract (``pipeline/vnext_forward``):
- a committed fitted state under
  ``data/dashboard_evidence_pack_reproducibility/ped_ar1/`` with a SHA256
  manifest and a parity audit;
- a runtime replay gate: the state is re-derived from the committed input
  history on every load and must match the stored coefficients and training
  fits to ``PARITY_TOLERANCE_ABS`` before numeric forecasts are emitted;
- forward scoring of assumption rows in the same ``future_forecasts`` /
  ``component_forecasts`` schemas the Forecast Builder and runtime-pack
  replay gate consume.

The model is linear, so the fitted state is plain JSON — no joblib.
"""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pipeline import vnext_core as vc
from pipeline.diaglab_arms import DiagSpec, _design, _train_periods, feature_bundle, load_diag_data
from pipeline.vnext_forward import build_future_canonical_frame

AR1_MODEL_NAME = "PED__DIAGLAB__B__glsar__ylag1__ar1__wexp"
AR1_SCORER_VERSION = "ped-ar1-forward-scorer-v1"
AR1_STATE_FILENAME = "ar1_fitted_state.json"
AR1_REPRO_DIRNAME = "ped_ar1"
PARITY_TOLERANCE_ABS = vc.PARITY_TOLERANCE_ABS
GLSAR_MAX_ITER = 8
YLAGS = (1,)
AR_ORDER = 1


def repro_dir(repo_root: Path | str) -> Path:
    return Path(repo_root) / "data" / "dashboard_evidence_pack_reproducibility" / AR1_REPRO_DIRNAME


def production_spec() -> DiagSpec:
    return DiagSpec(
        stream="PED",
        arm="B",
        kind="glsar",
        features=feature_bundle("PED", ["levels", "trend", "seasonal"]),
        window=None,
        ylags=YLAGS,
        params_json=json.dumps({"ar": AR_ORDER}),
    )


def _input_history_sha256(repo_root: Path | str) -> str:
    path = Path(repo_root) / "data" / "model_input_history" / "ped_inputs.parquet"
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fit_production_state(repo_root: Path | str) -> Dict[str, Any]:
    """Deterministically fit the AR(1) engine on all history to the latest actual."""
    import statsmodels.api as sm

    spec = production_spec()
    dd = load_diag_data(Path(repo_root), "PED")
    origin = dd.valid[-1]
    y_hist = {p: float(dd.y_log.loc[p]) for p in dd.y_log.index if pd.notna(dd.y_log.loc[p]) and p <= origin}
    train = _train_periods(dd, origin, spec.window)
    X, used = _design(dd, train, spec.features, spec.ylags, y_hist)
    if len(used) < 40:
        raise ValueError(f"AR(1) production fit has too few rows: {len(used)}")
    y = np.array([y_hist[p] for p in used])
    Xc = sm.add_constant(X)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = sm.GLSAR(y, Xc, rho=AR_ORDER)
        res = model.iterative_fit(maxiter=GLSAR_MAX_ITER)
    beta = np.asarray(res.params, dtype=float)
    rho = np.atleast_1d(np.asarray(model.rho, dtype=float))
    raw_resid = y - Xc @ beta
    train_fit_levels = {vc.period_str(p): float(np.exp(float(f))) for p, f in zip(used, Xc @ beta)}
    return {
        "model": AR1_MODEL_NAME,
        "scorer_version": AR1_SCORER_VERSION,
        "stream": "PED",
        "algorithm": "glsar_ar1",
        "features": list(spec.features),
        "ylags": list(spec.ylags),
        "ar_order": AR_ORDER,
        "glsar_max_iter": GLSAR_MAX_ITER,
        "beta": [float(v) for v in beta],
        "rho": [float(v) for v in rho],
        "last_resid": float(raw_resid[-1]),
        "latest_actual": vc.period_str(origin),
        "train_window_start": vc.period_str(used[0]),
        "train_window_end": vc.period_str(used[-1]),
        "train_rows": int(len(used)),
        "input_history_sha256": _input_history_sha256(repo_root),
        "training_fit_levels": train_fit_levels,
    }


def state_replay_max_delta(repo_root: Path | str, state: Dict[str, Any]) -> float:
    """Runtime gate: refit from committed inputs, compare betas and train fits."""
    try:
        fresh = fit_production_state(repo_root)
    except Exception:
        return float("inf")
    if fresh["input_history_sha256"] != state.get("input_history_sha256"):
        return float("inf")
    beta_old = np.asarray(state.get("beta", []), dtype=float)
    beta_new = np.asarray(fresh["beta"], dtype=float)
    if beta_old.shape != beta_new.shape:
        return float("inf")
    delta = float(np.max(np.abs(beta_old - beta_new))) if len(beta_old) else float("inf")
    fits_old = state.get("training_fit_levels", {})
    for period, level in fresh["training_fit_levels"].items():
        stored = fits_old.get(period)
        if stored is None:
            return float("inf")
        delta = max(delta, abs(float(stored) - float(level)))
    return delta


def load_state(repo_root: Path | str) -> Optional[Dict[str, Any]]:
    sdir = repro_dir(repo_root)
    manifest_path = sdir / "fitted_model_manifest.json"
    state_path = sdir / AR1_STATE_FILENAME
    if not manifest_path.exists() or not state_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = str(manifest.get("production_states", {}).get("AR1", {}).get("sha256", "")).lower()
    h = hashlib.sha256(state_path.read_bytes()).hexdigest()
    if expected and h != expected:
        raise ValueError(f"ped_ar1 fitted state SHA256 mismatch: expected {expected}, got {h}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def capability_record(repo_root: Path | str) -> Dict[str, Any]:
    """PED forward-capability record for the AR(1) engine (register schema)."""
    sdir = repro_dir(repo_root)
    parity_path = sdir / "forward_scorer_parity_audit.json"
    try:
        state = load_state(repo_root)
    except Exception as exc:
        state = None
        error = f"{type(exc).__name__}: {exc}"
    else:
        error = ""
    if state is None or not parity_path.exists():
        return {
            "stream": "PED",
            "stream_label": vc.STREAM_LABELS["PED"],
            "model": AR1_MODEL_NAME,
            "capability_status": "insufficient_artifacts",
            "gap_code": "ped_ar1_state_missing",
            "gap_reason": (error or "AR(1) fitted state or parity audit missing; run scripts/build_ar1_engine_state.py."),
            "scorer_version": AR1_SCORER_VERSION,
            "parity_status": "not_run",
            "max_parity_delta": None,
            "stored_replay_max_delta": None,
            "failing_component": None,
            "source_artifact_hashes": None,
            "forecast_capability_available": False,
        }
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    gate_delta = state_replay_max_delta(repo_root, state)
    enabled = parity.get("parity_status") == "passed" and gate_delta <= PARITY_TOLERANCE_ABS
    return {
        "stream": "PED",
        "stream_label": vc.STREAM_LABELS["PED"],
        "model": AR1_MODEL_NAME,
        "capability_status": "numeric_forecast_available" if enabled else "parity_failed",
        "gap_code": None if enabled else "ped_ar1_parity_failed",
        "gap_reason": "" if enabled else "AR(1) parity or runtime refit gate failed; numeric forecasts withheld.",
        "scorer_version": AR1_SCORER_VERSION,
        "parity_status": parity.get("parity_status"),
        "max_parity_delta": parity.get("state_replay_max_abs_delta"),
        "stored_replay_max_delta": gate_delta,
        "failing_component": None,
        "source_artifact_hashes": json.dumps({"AR1": hashlib.sha256((repro_dir(repo_root) / AR1_STATE_FILENAME).read_bytes()).hexdigest()}, sort_keys=True),
        "forecast_capability_available": bool(enabled),
    }


def _forward_log_predictions(state: Dict[str, Any], repo_root: Path | str,
                             assumptions: pd.DataFrame,
                             history_seed: Optional[Dict[str, float]] = None) -> Dict[pd.Period, float]:
    """Recursive log-space forecasts for the assumption periods (Period-indexed).

    ``history_seed`` maps period string -> LEVEL for governed recursive-history
    seeds beyond the fitted latest actual (e.g. a provisional PED annual-bridge
    quarter under the Candidate-B replay). Seeds only feed the target-lag
    recursion; they are never fitted on and never emitted as forecasts. The
    AR(1) error recursion is structurally advanced (err_t = rho * err_{t-1})
    across seeded quarters - the seed's own pseudo-residual is deliberately
    NOT conditioned on, because the seed is not an observed actual.
    """
    sd = vc.load_stream_data(Path(repo_root), "PED")
    future_canonical = build_future_canonical_frame(assumptions, "PED")
    needed = sorted(set(vc.LEVEL_SERIES["PED"].values()) | set(vc.BASE_SERIES["PED"].values()))
    hist_canonical = sd.history[needed].copy()
    for c in needed:
        hist_canonical[c] = pd.to_numeric(hist_canonical[c], errors="coerce").astype(float)
    combined = pd.concat([hist_canonical, future_canonical[needed]], axis=0)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    exog_full = vc.engineer_features(combined, "PED")

    latest_actual = vc.parse_period(state["latest_actual"])
    y_hist = {p: float(sd.y_log.loc[p]) for p in sd.y_log.index
              if pd.notna(sd.y_log.loc[p]) and p <= latest_actual}
    seed_quarters = 0
    if history_seed:
        for seed_period, seed_level in history_seed.items():
            sp = vc.parse_period(seed_period)
            if sp <= latest_actual:
                raise ValueError(
                    f"AR(1) history seed {seed_period} does not postdate the fitted latest actual "
                    f"{state['latest_actual']}; refusing to overwrite observed history."
                )
            if not np.isfinite(float(seed_level)) or float(seed_level) <= 0:
                raise ValueError(f"AR(1) history seed {seed_period} must be a positive level.")
            y_hist[sp] = float(np.log(float(seed_level)))
            seed_quarters = max(seed_quarters, (sp - latest_actual).n)
    beta = np.asarray(state["beta"], dtype=float)
    rho = np.asarray(state["rho"], dtype=float)
    features = list(state["features"])
    ylags = [int(v) for v in state["ylags"]]
    err_hist: List[float] = [float(state["last_resid"])]
    first_scored = min(assumptions.index) if len(assumptions.index) else None
    if first_scored is not None:
        # Structurally advance the AR(1) error recursion across any quarters
        # between the fitted origin and the first scored quarter (seeded or
        # otherwise skipped), so err_t remains rho^(t - origin) * last_resid.
        gap = (first_scored - latest_actual).n - 1
        for _ in range(max(0, gap)):
            err_hist.append(float(np.dot(rho, err_hist[-len(rho):][::-1])))

    out: Dict[pd.Period, float] = {}
    for p in sorted(assumptions.index):
        vals = [exog_full.at[p, c] if (p in exog_full.index and c in exog_full.columns) else np.nan for c in features]
        for lag in ylags:
            vals.append(y_hist.get(p - lag, np.nan))
        row = np.asarray(vals, dtype=float)
        if not np.all(np.isfinite(row)):
            raise ValueError(f"AR(1) forward features incomplete at {vc.period_str(p)}")
        err = float(np.dot(rho, err_hist[-len(rho):][::-1]))
        pred_log = float(beta[0] + row @ beta[1:]) + err
        err_hist.append(err)
        y_hist[p] = pred_log
        out[p] = pred_log
    return out


def ar1_forward_forecast(validation: Any, repo_root: Path,
                         history_seed: Optional[Dict[str, float]] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Score validated PED assumption rows with the AR(1) engine.

    Signature and output schemas mirror
    ``model_dashboard.vnext_forward_integration.vnext_forward_forecast``.
    ``history_seed`` is the governed provisional recursive-history seed
    (see ``_forward_log_predictions``).
    """
    capability = capability_record(repo_root)
    if not capability["forecast_capability_available"]:
        raise RuntimeError(f"PED AR(1): {capability['capability_status']}: {capability['gap_reason']}")
    state = load_state(repo_root)
    assert state is not None

    assumptions = validation.assumptions
    sub = assumptions[assumptions["stream"].astype(str).eq("PED")].copy()
    if sub.empty:
        raise ValueError("PED AR(1): no validated assumption rows")
    sub["__period__"] = sub["period"].map(vc.parse_period)
    sub = sub.set_index("__period__").sort_index()

    preds_log = _forward_log_predictions(state, repo_root, sub, history_seed=history_seed)
    periods = sorted(preds_log)
    metadata = {k: capability.get(k) for k in
                ("scorer_version", "source_artifact_hashes", "parity_status",
                 "max_parity_delta", "stored_replay_max_delta", "failing_component",
                 "capability_status")}
    recipe = (
        "AR(1) engine: GLSAR AR(1)-error regression on the Schiff-style levels "
        "specification plus one lagged log target; expanding window; log target."
    )

    future_rows, component_rows = [], []
    for i, p in enumerate(periods):
        level = float(np.exp(preds_log[p]))
        common = {
            "stream": "PED",
            "stream_label": vc.STREAM_LABELS["PED"],
            "model": AR1_MODEL_NAME,
            "target_period": vc.period_str(p),
            "horizon": i + 1,
            "availability_status": "numeric_forecast_available",
            "gap_code": None,
            "gap_reason": "",
            "fixed_finalist_only": True,
            "broad_search_run": False,
            "score_basis": "forward_assumption_workbook",
            **metadata,
        }
        future_rows.append({**common, "forecast": level, "prediction": level, "forecast_available": True})
        component_rows.append({**common, "component_model": AR1_MODEL_NAME, "component_label": "AR1",
                               "component_role": "weighted level component", "component_weight": 1.0,
                               "component_forecast": level, "component_log_value": float(preds_log[p]),
                               "weighted_component_forecast": level, "forecast_available": True})
        component_rows.append({**common, "component_model": AR1_MODEL_NAME, "component_label": "FINAL",
                               "component_role": "final weighted level prediction", "component_weight": 1.0,
                               "component_forecast": level, "component_log_value": float(preds_log[p]),
                               "weighted_component_forecast": level, "forecast_available": True})
    future = pd.DataFrame(future_rows)
    components = pd.DataFrame(component_rows)
    for frame in (future, components):
        frame["source_recipe"] = recipe
        frame["training_window_start"] = state["train_window_start"]
        frame["training_window_end"] = state["train_window_end"]
        frame["training_window_rows"] = int(state["train_rows"])
    return future, components


def write_repro_pack(repo_root: Path | str) -> Path:
    """Mint data/dashboard_evidence_pack_reproducibility/ped_ar1/ from scratch."""
    root = Path(repo_root)
    sdir = repro_dir(root)
    sdir.mkdir(parents=True, exist_ok=True)

    state = fit_production_state(root)
    state_text = json.dumps(state, indent=2, sort_keys=True)
    (sdir / AR1_STATE_FILENAME).write_text(state_text, encoding="utf-8")
    state_sha = hashlib.sha256((sdir / AR1_STATE_FILENAME).read_bytes()).hexdigest()

    gate = state_replay_max_delta(root, state)
    parity = {
        "stream": "PED",
        "finalist_model": AR1_MODEL_NAME,
        "scorer_version": AR1_SCORER_VERSION,
        "parity_status": "passed" if gate <= PARITY_TOLERANCE_ABS else "failed",
        "state_replay_max_abs_delta": gate,
        "recipe_replay_max_abs_delta": gate,
        "tolerance_abs": PARITY_TOLERANCE_ABS,
        "note": (
            "Deterministic linear engine: parity re-fits the GLSAR from the committed "
            "input history and compares coefficients and training fits to the stored state."
        ),
    }
    (sdir / "forward_scorer_parity_audit.json").write_text(json.dumps(parity, indent=2), encoding="utf-8")

    manifest = {
        "stream": "PED",
        "finalist_model": AR1_MODEL_NAME,
        "engine": "ar1",
        "generation": "ar1",
        "scorer_version": AR1_SCORER_VERSION,
        "members": [
            {
                "component_label": "AR1",
                "component_model": AR1_MODEL_NAME,
                "component_weight": 1.0,
                "model_kind": "glsar_ar1",
                "feature_set": "schiff_levels_trend_seasonal",
                "window": "expanding",
                "include_target_lags": True,
            }
        ],
        "production_states": {
            "AR1": {
                "file": AR1_STATE_FILENAME,
                "sha256": state_sha,
                "train_window_start": state["train_window_start"],
                "train_window_end": state["train_window_end"],
                "train_rows": state["train_rows"],
            }
        },
    }
    (sdir / "fitted_model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    coef_rows = [{"stream": "PED", "model": AR1_MODEL_NAME, "term": "const", "coefficient": state["beta"][0], "term_role": "intercept"}]
    names = list(state["features"]) + [f"target__ylag{lag}" for lag in state["ylags"]]
    for name, value in zip(names, state["beta"][1:]):
        coef_rows.append({"stream": "PED", "model": AR1_MODEL_NAME, "term": name, "coefficient": float(value), "term_role": "regressor"})
    for i, r in enumerate(state["rho"], start=1):
        coef_rows.append({"stream": "PED", "model": AR1_MODEL_NAME, "term": f"rho_{i}", "coefficient": float(r), "term_role": "ar_error"})
    pd.DataFrame(coef_rows).to_parquet(sdir / "model_coefficients.parquet", index=False)

    winners = root / "artifacts" / "diagnostics_lab" / "ped" / "winners" / f"{AR1_MODEL_NAME}.predictions.parquet"
    if winners.exists():
        pd.read_parquet(winners).to_parquet(sdir / "validation_predictions.parquet", index=False)
    return sdir

"""vNext pipeline orchestrator.

Stages (run via ``python -m pipeline.vnext_run <stage>``):

    search    backtest the governed candidate grid, write search results
    select    score candidates on both governed keysets, solve convex
              ensembles, pick the vNext finalist per stream
    finalize  refit the finalist with full state saving, run parity gates
    forecast  score future assumption workbook(s) with the fixed finalist
    evidence  emit the unified evidence / reproducibility packs + audit report
    all       run every stage in order

Outputs live under ``artifacts/vnext/`` (run-scoped) and
``data/dashboard_evidence_pack_reproducibility/<stream>_vnext/`` (governed
packs). The historical evidence pack at ``data/dashboard_evidence_pack`` is
never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import PIPELINE_VERSION
from .vnext_candidates import HEAVY_LOCKED_WEIGHTS, candidate_grid, heavy_locked_refit_components
from .vnext_core import (
    LAG_RECURSION_POLICY,
    MAX_HORIZON,
    OPERATIONAL_SCORE_BASIS,
    PAPER_SCORE_BASIS,
    PARITY_TOLERANCE_ABS,
    RANDOM_STATE,
    STREAM_LABELS,
    TARGET_TRANSFORM,
    BacktestResult,
    CandidateSpec,
    StreamData,
    backtest,
    backtest_origins,
    calibration_r2,
    fit_at_origin,
    forecast_r2,
    load_eval_keysets,
    load_schiff_predictions,
    load_stream_data,
    mape,
    paired_win_rate,
    period_str,
    restrict_to_keys,
    score_frame,
    stress_buckets,
)

VNEXT_STREAMS = ["HEAVY_RUC", "PED"]
INCUMBENT_FINALISTS = {
    "PED": "PED__RESCUE_static_annual_weighted_top12_capnone",
    "LIGHT_RUC": "dynamic_RESID_GBR_n150_d1_lr0.05_w36",
    "HEAVY_RUC": "HEAVY_RUC__RECON_STATIC_REBUILT",
}
MAX_ENSEMBLE_COMPONENTS = 4


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def vnext_dir(stream: str) -> Path:
    d = repo_root() / "artifacts" / "vnext" / stream.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_dir(stream: str) -> Path:
    d = repo_root() / "data" / "dashboard_evidence_pack_reproducibility" / f"{stream.lower()}_vnext"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Stage: search
# ---------------------------------------------------------------------------

def stage_search(streams: Sequence[str], time_budget: Optional[float] = None) -> bool:
    """Resumable candidate search. Each candidate's backtest is checkpointed to
    ``search_parts/``; reruns skip completed candidates. Returns True when every
    stream's grid is complete and concatenated."""
    import time

    t0 = time.time()
    all_complete = True
    for stream in streams:
        sd = load_stream_data(repo_root(), stream)
        grid = candidate_grid(stream)
        out = vnext_dir(stream)
        parts = out / "search_parts"
        parts.mkdir(exist_ok=True)
        done = {p.stem for p in parts.glob("*.parquet")}
        todo = [s for s in grid if _safe_name(s.name) not in done]
        print(f"[search] {stream}: {len(grid)} candidates, {len(done)} done, "
              f"{len(todo)} remaining, latest actual {period_str(sd.latest_actual)}")
        for spec in todo:
            if time_budget is not None and time.time() - t0 > time_budget:
                print(f"[search] {stream}: time budget reached, "
                      f"{len(list(parts.glob('*.parquet')))}/{len(grid)} complete; rerun to resume")
                return False
            result = backtest(sd, spec)
            if result.predictions.empty:
                result = BacktestResult(predictions=pd.DataFrame([{"model": spec.name, "empty": True}]))
            result.predictions.to_parquet(parts / f"{_safe_name(spec.name)}.parquet", index=False)
        done_now = {p.stem for p in parts.glob("*.parquet")}
        if {_safe_name(s.name) for s in grid} - done_now:
            all_complete = False
            continue
        frames = [pd.read_parquet(p) for p in sorted(parts.glob("*.parquet"))]
        preds = pd.concat([f for f in frames if "empty" not in f.columns], ignore_index=True)
        preds["window"] = preds["window"].astype(str)
        preds.to_parquet(out / "search_predictions.parquet", index=False)
        meta = {
            "created_at": utcnow(),
            "pipeline_version": PIPELINE_VERSION,
            "stream": stream,
            "n_candidates": len(grid),
            "n_prediction_rows": int(len(preds)),
            "random_state": RANDOM_STATE,
            "python_version": sys.version,
            "platform": platform.platform(),
            "sklearn_version": _sklearn_version(),
            "history_sha256": sha256_file(repo_root() / "data" / "model_input_history" /
                                          f"{stream.lower()}_inputs.parquet"),
        }
        (out / "search_manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[search] {stream}: complete, wrote {len(preds)} prediction rows")
    return all_complete


def _safe_name(name: str) -> str:
    return name.replace("/", "_").replace(".", "p")


def _sklearn_version() -> str:
    import sklearn
    return sklearn.__version__


# ---------------------------------------------------------------------------
# Stage: select
# ---------------------------------------------------------------------------

def candidate_scores(preds: pd.DataFrame, keysets: Dict[str, pd.DataFrame],
                     schiff: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, g in preds.groupby("model", sort=True):
        row: Dict[str, Any] = {"model": model,
                               "family_tag": g["family_tag"].iloc[0],
                               "model_kind": g["model_kind"].iloc[0],
                               "feature_set": g["feature_set"].iloc[0],
                               "include_target_lags": bool(g["include_target_lags"].iloc[0]),
                               "window": g["window"].iloc[0],
                               "params_json": g["params_json"].iloc[0]}
        ok = True
        for basis, keys in keysets.items():
            sub = restrict_to_keys(g, keys)
            if len(sub) < len(keys):
                ok = False
            sc = score_frame(sub, basis)
            prefix = "paper" if basis == PAPER_SCORE_BASIS else "operational"
            row[f"{prefix}_pooled_mape"] = sc["quarterly_pooled_mape"]
            row[f"{prefix}_horizon_mean_mape"] = sc["horizon_mean_mape"]
            row[f"{prefix}_bias_pct"] = sc["quarterly_bias_pct"]
            row[f"{prefix}_annual_mape"] = sc["annual_mape"]
            row[f"{prefix}_n_pairs"] = sc["n_quarterly_pairs"]
            row[f"{prefix}_win_rate_vs_schiff"] = paired_win_rate(sub, schiff, basis)
        row["full_key_coverage"] = ok
        rows.append(row)
    return pd.DataFrame(rows)


def solve_convex_weights(component_preds: List[pd.DataFrame], keys: pd.DataFrame) -> np.ndarray:
    """Deterministic convex weight solve minimising horizon-mean MAPE on the
    paper keyset. Uses SLSQP when scipy is available; otherwise an
    equal-weight fallback (recorded by the caller)."""
    mats = []
    merged: Optional[pd.DataFrame] = None
    for i, cp in enumerate(component_preds):
        sub = restrict_to_keys(cp, keys)[["origin", "target_period", "horizon", "actual", "pred"]]
        sub = sub.rename(columns={"pred": f"pred_{i}"})
        merged = sub if merged is None else merged.merge(
            sub[["origin", "target_period", f"pred_{i}"]], on=["origin", "target_period"], how="inner")
    assert merged is not None and not merged.empty
    P = merged[[f"pred_{i}" for i in range(len(component_preds))]].to_numpy(float)
    a = merged["actual"].to_numpy(float)
    h = merged["horizon"].to_numpy(int)

    def objective(w: np.ndarray) -> float:
        pred = P @ w
        ape = np.abs((pred - a) / a) * 100.0
        vals = [ape[h == hh].mean() for hh in range(1, MAX_HORIZON + 1) if (h == hh).any()]
        return float(np.mean(vals))

    k = P.shape[1]
    w0 = np.full(k, 1.0 / k)
    try:
        from scipy.optimize import minimize

        best = None
        starts = [w0] + [np.eye(k)[i] * 0.7 + (0.3 / k) for i in range(k)]
        for s in starts:
            s = s / s.sum()
            res = minimize(objective, s, method="SLSQP", bounds=[(0.0, 1.0)] * k,
                           constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                           options={"maxiter": 500, "ftol": 1e-10})
            if res.success and (best is None or res.fun < best.fun):
                best = res
        w = best.x if best is not None else w0
    except ImportError:
        w = w0
    w = np.clip(np.round(w, 6), 0.0, None)
    w = w / w.sum()
    return w


def ensemble_predictions(component_preds: List[pd.DataFrame], weights: np.ndarray,
                         name: str, stream: str) -> pd.DataFrame:
    merged: Optional[pd.DataFrame] = None
    for i, cp in enumerate(component_preds):
        sub = cp[["origin", "target_period", "horizon", "actual", "pred"]].rename(columns={"pred": f"pred_{i}"})
        merged = sub if merged is None else merged.merge(
            sub[["origin", "target_period", f"pred_{i}"]], on=["origin", "target_period"], how="inner")
    P = merged[[f"pred_{i}" for i in range(len(component_preds))]].to_numpy(float)
    merged["pred"] = P @ weights
    merged["model"] = name
    merged["stream"] = stream
    return merged[["stream", "model", "origin", "target_period", "horizon", "actual", "pred"]]


def stage_select(streams: Sequence[str]) -> None:
    for stream in streams:
        out = vnext_dir(stream)
        preds = pd.read_parquet(out / "search_predictions.parquet")
        keysets = load_eval_keysets(repo_root(), stream, INCUMBENT_FINALISTS[stream])
        schiff = load_schiff_predictions(repo_root(), stream)
        scores = candidate_scores(preds, keysets, schiff)
        scores = scores.sort_values(["paper_horizon_mean_mape", "operational_pooled_mape", "model"]).reset_index(drop=True)
        scores.to_parquet(out / "search_summary.parquet", index=False)
        print(f"[select] {stream}: top single candidates by paper horizon-mean MAPE:")
        print(scores.head(8)[["model", "paper_horizon_mean_mape", "operational_pooled_mape",
                              "paper_win_rate_vs_schiff"]].to_string(index=False))

        ensembles: List[Dict[str, Any]] = []
        paper_keys = keysets[PAPER_SCORE_BASIS]

        # Heavy locked-weight refit ensemble (archived C1-C4 weights).
        if stream == "HEAVY_RUC":
            locked = heavy_locked_refit_components()
            locked_preds = [preds[preds["model"] == s.name] for s in locked]
            if all(not lp.empty for lp in locked_preds):
                ens = ensemble_predictions(locked_preds, np.array(HEAVY_LOCKED_WEIGHTS),
                                           "HEAVY_RUC__VNEXT_LOCKED_REFIT_ENSEMBLE", stream)
                ensembles.append({"name": "HEAVY_RUC__VNEXT_LOCKED_REFIT_ENSEMBLE",
                                  "members": [s.name for s in locked],
                                  "weights": HEAVY_LOCKED_WEIGHTS,
                                  "weight_solver": "archived_locked_weights",
                                  "preds": ens})

        # Solved-weight convex ensembles over diverse top candidates.
        diverse: List[str] = []
        seen_family: set = set()
        for _, r in scores.iterrows():
            fam = (r["model_kind"], r["feature_set"], r["include_target_lags"])
            if fam in seen_family:
                continue
            seen_family.add(fam)
            diverse.append(r["model"])
            if len(diverse) >= 6:
                break
        for k in (2, 3, MAX_ENSEMBLE_COMPONENTS):
            members = diverse[:k]
            if len(members) < k:
                continue
            comp_preds = [preds[preds["model"] == m] for m in members]
            w = solve_convex_weights(comp_preds, paper_keys)
            # Prune zero-weight members: dead components must not enter the
            # governed registry or the saved-state pack.
            keep = w > 1e-9
            members = [m for m, kept in zip(members, keep) if kept]
            comp_preds = [cp for cp, kept in zip(comp_preds, keep) if kept]
            w = w[keep]
            w = w / w.sum()
            name = f"{stream}__VNEXT_SOLVED_CONVEX_TOP{k}"
            ens = ensemble_predictions(comp_preds, w, name, stream)
            ensembles.append({"name": name, "members": members, "weights": [float(x) for x in w],
                              "weight_solver": "slsqp_paper_horizon_mean_multistart_zero_pruned",
                              "preds": ens})

        # Score ensembles alongside single candidates.
        rows = []
        for e in ensembles:
            row: Dict[str, Any] = {"model": e["name"], "family_tag": "vnext_ensemble",
                                   "model_kind": "convex_ensemble", "feature_set": "ensemble",
                                   "include_target_lags": pd.NA, "window": pd.NA,
                                   "params_json": json.dumps({"members": e["members"], "weights": e["weights"]})}
            for basis, keys in keysets.items():
                sub = restrict_to_keys(e["preds"], keys)
                sc = score_frame(sub, basis)
                prefix = "paper" if basis == PAPER_SCORE_BASIS else "operational"
                row[f"{prefix}_pooled_mape"] = sc["quarterly_pooled_mape"]
                row[f"{prefix}_horizon_mean_mape"] = sc["horizon_mean_mape"]
                row[f"{prefix}_bias_pct"] = sc["quarterly_bias_pct"]
                row[f"{prefix}_annual_mape"] = sc["annual_mape"]
                row[f"{prefix}_n_pairs"] = sc["n_quarterly_pairs"]
                row[f"{prefix}_win_rate_vs_schiff"] = paired_win_rate(sub, schiff, basis)
            row["full_key_coverage"] = True
            rows.append(row)
        leaderboard = pd.concat([scores, pd.DataFrame(rows)], ignore_index=True)
        leaderboard = leaderboard.sort_values(
            ["paper_horizon_mean_mape", "operational_pooled_mape", "model"]).reset_index(drop=True)
        leaderboard.to_parquet(out / "selection_leaderboard.parquet", index=False)

        winner = leaderboard.iloc[0]
        winner_name = str(winner["model"])
        ens_entry = next((e for e in ensembles if e["name"] == winner_name), None)
        selection = {
            "created_at": utcnow(),
            "pipeline_version": PIPELINE_VERSION,
            "stream": stream,
            "selection_basis": "paper_horizon_mean_mape (tie-break operational_pooled_mape, model name)",
            "finalist_model": winner_name,
            "is_ensemble": ens_entry is not None,
            "members": ens_entry["members"] if ens_entry else [winner_name],
            "weights": ens_entry["weights"] if ens_entry else [1.0],
            "weight_solver": ens_entry["weight_solver"] if ens_entry else "single_model",
            "paper_horizon_mean_mape": float(winner["paper_horizon_mean_mape"]),
            "operational_pooled_mape": float(winner["operational_pooled_mape"]),
            "incumbent_model": INCUMBENT_FINALISTS[stream],
            "beats_schiff_paper": bool(winner["paper_win_rate_vs_schiff"] > 50.0),
        }
        (out / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
        print(f"[select] {stream}: finalist = {winner_name} "
              f"(paper {selection['paper_horizon_mean_mape']:.3f}, "
              f"op {selection['operational_pooled_mape']:.3f})")


# ---------------------------------------------------------------------------
# Stage: finalize  (fit-and-save + parity gates)
# ---------------------------------------------------------------------------

def _spec_by_name(stream: str, name: str) -> CandidateSpec:
    for spec in candidate_grid(stream):
        if spec.name == name:
            return spec
    raise KeyError(f"Candidate spec not found: {name}")


def _save_states(stream: str, spec: CandidateSpec, label: str, result: BacktestResult,
                 sdir: Path) -> List[Dict[str, Any]]:
    import joblib

    entries = []
    fs_dir = sdir / "fitted_state"
    fs_dir.mkdir(parents=True, exist_ok=True)
    for fc in result.states:
        fname = f"{label}_{period_str(fc.origin).lower()}.joblib"
        path = fs_dir / fname
        joblib.dump({"model": fc.model, "feature_cols": fc.feature_cols,
                     "base_cols": fc.base_cols, "all_na_cols": fc.all_na_cols,
                     "base_all_na_cols": fc.base_all_na_cols,
                     "spec": {"name": fc.spec.name, "model_kind": fc.spec.model_kind,
                              "params_json": fc.spec.params_json, "window": fc.spec.window,
                              "feature_set": fc.spec.feature_set,
                              "include_target_lags": fc.spec.include_target_lags,
                              "base_feature_set": fc.spec.base_feature_set}},
                    path, compress=3)
        entries.append({"component_label": label, "component_model": spec.name,
                        "origin": period_str(fc.origin), "file": f"fitted_state/{fname}",
                        "sha256": sha256_file(path),
                        "train_rows": int(len(fc.X_train)),
                        "train_window_start": period_str(fc.X_train.index.min()),
                        "train_window_end": period_str(fc.X_train.index.max())})
    return entries


def _training_matrix_frames(label: str, result: BacktestResult) -> Tuple[pd.DataFrame, pd.DataFrame]:
    mats = []
    for fc in result.states:
        m = fc.X_train.copy()
        m.insert(0, "y_log", fc.y_train)
        m.insert(0, "training_period", [period_str(p) for p in fc.X_train.index])
        m.insert(0, "origin", period_str(fc.origin))
        m.insert(0, "component_label", label)
        mats.append(m.reset_index(drop=True))
    train_mat = pd.concat(mats, ignore_index=True)
    rows = result.prediction_rows.copy() if result.prediction_rows is not None else pd.DataFrame()
    if not rows.empty:
        rows.insert(0, "component_label", label)
    return train_mat, rows


def stage_finalize(streams: Sequence[str]) -> None:
    import joblib

    for stream in streams:
        out = vnext_dir(stream)
        sdir = state_dir(stream)
        selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
        sd = load_stream_data(repo_root(), stream)
        members = selection["members"]
        weights = np.array(selection["weights"], dtype=float)
        finalist = selection["finalist_model"]
        print(f"[finalize] {stream}: {finalist} with {len(members)} component(s)")

        search_preds = pd.read_parquet(out / "search_predictions.parquet")
        state_index: List[Dict[str, Any]] = []
        comp_results: Dict[str, BacktestResult] = {}
        train_mats, pred_rows_all, base_rows_all = [], [], []
        production_states: Dict[str, Any] = {}

        for i, mname in enumerate(members):
            spec = _spec_by_name(stream, mname)
            label = f"M{i+1}"
            result = backtest(sd, spec, keep_states=True)
            comp_results[mname] = result

            # Determinism gate: refit must equal the search predictions.
            search_m = search_preds[search_preds["model"] == mname].reset_index(drop=True)
            merged = search_m.merge(result.predictions, on=["origin", "target_period"],
                                    suffixes=("_search", "_refit"))
            delta = (merged["pred_search"] - merged["pred_refit"]).abs().max()
            assert delta <= PARITY_TOLERANCE_ABS, (
                f"{mname}: refit determinism failed, max abs delta {delta}")

            state_index += _save_states(stream, spec, label, result, sdir)
            tm, pr = _training_matrix_frames(label, result)
            train_mats.append(tm)
            if not pr.empty:
                pred_rows_all.append(pr)
            if result.base_prediction_rows is not None:
                br = result.base_prediction_rows.copy()
                br.insert(0, "component_label", label)
                base_rows_all.append(br)

            # Production fit (training window ends at latest actual).
            prod = fit_at_origin(sd, spec, sd.latest_actual)
            assert prod is not None, f"{mname}: production fit failed"
            pf = sdir / "fitted_state" / f"{label}_production.joblib"
            joblib.dump({"model": prod.model, "feature_cols": prod.feature_cols,
                         "base_cols": prod.base_cols, "all_na_cols": prod.all_na_cols,
                         "base_all_na_cols": prod.base_all_na_cols,
                         "spec": {"name": spec.name, "model_kind": spec.model_kind,
                                  "params_json": spec.params_json, "window": spec.window,
                                  "feature_set": spec.feature_set,
                                  "include_target_lags": spec.include_target_lags,
                                  "base_feature_set": spec.base_feature_set}},
                        pf, compress=3)
            production_states[label] = {"component_model": mname, "file": f"fitted_state/{label}_production.joblib",
                                        "sha256": sha256_file(pf),
                                        "train_window_start": period_str(prod.X_train.index.min()),
                                        "train_window_end": period_str(prod.X_train.index.max()),
                                        "train_rows": int(len(prod.X_train))}
            pm = prod.X_train.copy()
            pm.insert(0, "y_log", prod.y_train)
            pm.insert(0, "training_period", [period_str(p) for p in prod.X_train.index])
            pm.insert(0, "origin", "production")
            pm.insert(0, "component_label", label)
            train_mats.append(pm.reset_index(drop=True))

        # Archived validation predictions (components + final weighted).
        comp_frames = []
        for i, mname in enumerate(members):
            f = comp_results[mname].predictions.copy()
            f["component_label"] = f"M{i+1}"
            f["component_weight"] = float(weights[i])
            comp_frames.append(f)
        component_predictions = pd.concat(comp_frames, ignore_index=True)
        component_predictions["window"] = component_predictions["window"].astype(str)
        final_preds = ensemble_predictions([comp_results[m].predictions for m in members],
                                           weights, finalist, stream)
        final_preds["stream_label"] = STREAM_LABELS[stream]

        component_predictions.to_parquet(sdir / "component_validation_predictions.parquet", index=False)
        final_preds.to_parquet(sdir / "validation_predictions.parquet", index=False)
        pd.concat(train_mats, ignore_index=True).to_parquet(sdir / "training_feature_matrices.parquet", index=False)
        if pred_rows_all:
            pd.concat(pred_rows_all, ignore_index=True).to_parquet(sdir / "prediction_feature_rows.parquet", index=False)
        if base_rows_all:
            pd.concat(base_rows_all, ignore_index=True).to_parquet(sdir / "base_prediction_feature_rows.parquet", index=False)
        pd.DataFrame(state_index).to_parquet(sdir / "fitted_state_index.parquet", index=False)

        # Parity gate P1: serialized state replay against archived predictions.
        p1 = _parity_state_replay(stream, sdir, members)
        # Parity gate P2: full deterministic recipe replay from history.
        p2_deltas = []
        for mname in members:
            r2 = backtest(sd, _spec_by_name(stream, mname))
            m = comp_results[mname].predictions.merge(
                r2.predictions, on=["origin", "target_period"], suffixes=("_a", "_b"))
            p2_deltas.append(float((m["pred_a"] - m["pred_b"]).abs().max()))
        p2_max = max(p2_deltas)

        parity = {
            "created_at": utcnow(),
            "pipeline_version": PIPELINE_VERSION,
            "stream": stream,
            "finalist_model": finalist,
            "parity_tolerance": PARITY_TOLERANCE_ABS,
            "state_replay_max_abs_delta": p1,
            "recipe_replay_max_abs_delta": p2_max,
            "parity_status": "passed" if (p1 <= PARITY_TOLERANCE_ABS and p2_max <= PARITY_TOLERANCE_ABS) else "failed",
            "lag_recursion_policy": LAG_RECURSION_POLICY,
            "target_transform": TARGET_TRANSFORM,
            "random_state": RANDOM_STATE,
            "sklearn_version": _sklearn_version(),
            "python_version": sys.version,
            "platform": platform.platform(),
            "note": ("Parity must be re-verified on the scoring host: rerun "
                     "'python -m pipeline.vnext_run finalize' after any environment change."),
        }
        (sdir / "forward_scorer_parity_audit.json").write_text(json.dumps(parity, indent=2), encoding="utf-8")

        manifest = {
            "created_at": utcnow(),
            "pipeline_version": PIPELINE_VERSION,
            "stream": stream,
            "stream_label": STREAM_LABELS[stream],
            "finalist_model": finalist,
            "members": [
                {"component_label": f"M{i+1}", "component_model": m,
                 "component_weight": float(weights[i]),
                 **{k: v for k, v in _spec_by_name(stream, m).__dict__.items() if k != "stream"}}
                for i, m in enumerate(members)
            ],
            "weight_solver": selection["weight_solver"],
            "target_column": "target",
            "target_transform": "y_model = ln(target); prediction = exp(y_model)",
            "lag_recursion_policy": LAG_RECURSION_POLICY,
            "latest_actual": period_str(sd.latest_actual),
            "history_file": f"data/model_input_history/{stream.lower()}_inputs.parquet",
            "history_sha256": sha256_file(repo_root() / "data" / "model_input_history" /
                                          f"{stream.lower()}_inputs.parquet"),
            "production_states": production_states,
            "random_state": RANDOM_STATE,
            "sklearn_version": _sklearn_version(),
            "parity_status": parity["parity_status"],
        }
        (sdir / "fitted_model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        fm_manifest = {
            "created_at": utcnow(),
            "stream": stream,
            "files": {
                name: {"sha256": sha256_file(sdir / name), "rows": int(len(pd.read_parquet(sdir / name)))}
                for name in ["training_feature_matrices.parquet", "prediction_feature_rows.parquet",
                             "component_validation_predictions.parquet", "validation_predictions.parquet"]
                if (sdir / name).exists()
            },
            "feature_column_order_note": "Column order in each parquet is the exact fit/predict order.",
        }
        (sdir / "feature_matrix_manifest.json").write_text(json.dumps(fm_manifest, indent=2), encoding="utf-8")
        print(f"[finalize] {stream}: parity={parity['parity_status']} "
              f"(state replay {p1:.3e}, recipe replay {p2_max:.3e})")


def _parity_state_replay(stream: str, sdir: Path, members: Sequence[str]) -> float:
    """Reload every saved per-origin estimator and replay archived predictions
    from the saved prediction feature rows. Proves serialized state validity."""
    import joblib

    comp = pd.read_parquet(sdir / "component_validation_predictions.parquet")
    rows = pd.read_parquet(sdir / "prediction_feature_rows.parquet") if (sdir / "prediction_feature_rows.parquet").exists() else None
    base_rows = pd.read_parquet(sdir / "base_prediction_feature_rows.parquet") if (sdir / "base_prediction_feature_rows.parquet").exists() else None
    index = pd.read_parquet(sdir / "fitted_state_index.parquet")
    max_delta = 0.0
    for _, entry in index.iterrows():
        bundle = joblib.load(sdir / entry["file"])
        label, origin = entry["component_label"], entry["origin"]
        archived = comp[(comp["component_label"] == label) & (comp["origin"] == origin)]
        if rows is None or archived.empty:
            continue
        rsub = rows[(rows["component_label"] == label) & (rows["origin"] == origin)]
        for _, arow in archived.iterrows():
            rrow = rsub[rsub["target_period"] == arow["target_period"]]
            if rrow.empty:
                continue
            x = rrow.iloc[0][bundle["feature_cols"]].astype(float).to_frame().T
            x = x.fillna(0.0)
            model = bundle["model"]
            if isinstance(model, dict) and model.get("kind") == "residual":
                bsub = base_rows[(base_rows["component_label"] == label) &
                                 (base_rows["origin"] == origin) &
                                 (base_rows["target_period"] == arow["target_period"])]
                xb = bsub.iloc[0][bundle["base_cols"]].astype(float).to_frame().T.fillna(0.0)
                pred_log = float(model["base"].predict(xb.to_numpy(float))[0]
                                 + model["resid"].predict(x.to_numpy(float))[0])
            else:
                pred_log = float(model.predict(x.to_numpy(float))[0])
            pred = float(np.exp(pred_log))
            if np.isfinite(arow["pred"]):
                max_delta = max(max_delta, abs(pred - float(arow["pred"])))
    return max_delta


# ---------------------------------------------------------------------------
# Stage: scorecards
# ---------------------------------------------------------------------------

def stage_scorecards(streams: Sequence[str]) -> None:
    for stream in streams:
        out = vnext_dir(stream)
        sdir = state_dir(stream)
        selection = json.loads((out / "selection.json").read_text(encoding="utf-8"))
        finalist = selection["finalist_model"]
        final_preds = pd.read_parquet(sdir / "validation_predictions.parquet")
        keysets = load_eval_keysets(repo_root(), stream, INCUMBENT_FINALISTS[stream])
        schiff = load_schiff_predictions(repo_root(), stream)

        summary_rows, stress_rows, horizon_rows = [], [], []
        r2_rows = []
        for basis, keys in keysets.items():
            sub = restrict_to_keys(final_preds, keys)
            sc = score_frame(sub, basis)
            sc.update({"stream": stream, "stream_label": STREAM_LABELS[stream], "model": finalist,
                       "eval_grid": "stored_evidence_keyset",
                       "paired_win_rate_vs_schiff": paired_win_rate(sub, schiff, basis),
                       "forecast_r2": forecast_r2(sub["actual"].to_numpy(float), sub["pred"].to_numpy(float)),
                       "calibration_r2": calibration_r2(sub["actual"].to_numpy(float), sub["pred"].to_numpy(float))})
            summary_rows.append(sc)
            stress_rows.append(stress_buckets(sub, basis, stream))
            hp = {"stream": stream, "stream_label": STREAM_LABELS[stream], "model": finalist,
                  "score_basis": basis, "eval_grid": "stored_evidence_keyset"}
            hp.update({f"mape_h{h:02d}": sc[f"mape_h{h:02d}"] for h in range(1, MAX_HORIZON + 1)})
            horizon_rows.append(hp)

        # Training-fit R2 from production matrices.
        tf = _training_fit_frames(stream, sdir)
        if tf is not None:
            tf_pred, tf_summary = tf
            tf_pred.to_parquet(sdir / "training_fit_predictions.parquet", index=False)
            r2_rows = tf_summary

        pd.DataFrame(summary_rows).to_parquet(sdir / "scorecard_summary.parquet", index=False)
        pd.concat(stress_rows, ignore_index=True).to_parquet(sdir / "stress_horizon.parquet", index=False)
        pd.DataFrame(horizon_rows).to_parquet(sdir / "horizon_profiles.parquet", index=False)
        if r2_rows:
            pd.DataFrame(r2_rows).to_parquet(sdir / "training_fit_r2_summary.parquet", index=False)
        print(f"[scorecards] {stream}: paper horizon-mean "
              f"{summary_rows[0]['horizon_mean_mape'] if summary_rows[0]['score_basis'] == PAPER_SCORE_BASIS else summary_rows[1]['horizon_mean_mape']:.3f}")


def _training_fit_frames(stream: str, sdir: Path):
    import joblib

    manifest = json.loads((sdir / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    mats = pd.read_parquet(sdir / "training_feature_matrices.parquet")
    sd = load_stream_data(repo_root(), stream)
    pred_rows, summary = [], []
    weights = {m["component_label"]: m["component_weight"] for m in manifest["members"]}
    fits_by_label: Dict[str, Dict[str, float]] = {}
    actual_by_p: Dict[str, float] = {}
    for m in manifest["members"]:
        label = m["component_label"]
        bundle = joblib.load(sdir / manifest["production_states"][label]["file"])
        g = mats[(mats["component_label"] == label) & (mats["origin"] == "production")]
        X = g[bundle["feature_cols"]].astype(float).fillna(0.0)
        model = bundle["model"]
        if isinstance(model, dict) and model.get("kind") == "residual":
            base_cols = [c for c in bundle["base_cols"] if c in g.columns]
            Xb = g[base_cols].astype(float).fillna(0.0)
            fit_log = model["base"].predict(Xb.to_numpy(float)) + model["resid"].predict(X.to_numpy(float))
        else:
            fit_log = model.predict(X.to_numpy(float))
        fit_level = np.exp(fit_log)
        actual_level = np.exp(g["y_log"].to_numpy(float))
        fits_by_label[label] = {}
        for tp, al, fl, fg in zip(g["training_period"], actual_level, fit_level, fit_log):
            pred_rows.append({"stream": stream, "stream_label": STREAM_LABELS[stream],
                              "model": manifest["finalist_model"], "component_label": label,
                              "component_model": m["component_model"],
                              "component_weight": weights[label],
                              "training_period": tp, "training_fit_stage": "production_window",
                              "actual": float(al), "training_fit_pred": float(fl),
                              "training_fit_pred_log": float(fg)})
            fits_by_label[label][tp] = float(fl)
            actual_by_p[tp] = float(al)
        summary.append({"stream": stream, "stream_label": STREAM_LABELS[stream],
                        "model": manifest["finalist_model"], "component_model": m["component_model"],
                        "training_fit_stage": "production_window",
                        "n_rows": int(len(g)),
                        "training_fit_r2_level": forecast_r2(actual_level, fit_level),
                        "training_fit_r2_log": forecast_r2(g["y_log"].to_numpy(float), np.asarray(fit_log)),
                        "training_fit_mape": mape(actual_level, np.asarray(fit_level))})
    # FINAL weighted fit is only defined where every component window overlaps.
    common = set.intersection(*[set(d) for d in fits_by_label.values()])
    periods = sorted(common)
    a = np.array([actual_by_p[p] for p in periods])
    f = np.array([sum(weights[lbl] * fits_by_label[lbl][p] for lbl in fits_by_label) for p in periods])
    for p, al, fl in zip(periods, a, f):
        pred_rows.append({"stream": stream, "stream_label": STREAM_LABELS[stream],
                          "model": manifest["finalist_model"], "component_label": "FINAL",
                          "component_model": manifest["finalist_model"], "component_weight": 1.0,
                          "training_period": p, "training_fit_stage": "production_window",
                          "actual": float(al), "training_fit_pred": float(fl),
                          "training_fit_pred_log": float(np.log(fl)) if fl > 0 else np.nan})
    summary.append({"stream": stream, "stream_label": STREAM_LABELS[stream],
                    "model": manifest["finalist_model"], "component_model": manifest["finalist_model"],
                    "training_fit_stage": "production_window", "n_rows": int(len(periods)),
                    "training_fit_r2_level": forecast_r2(a, f),
                    "training_fit_r2_log": forecast_r2(np.log(a), np.log(f)),
                    "training_fit_mape": mape(a, f)})
    return pd.DataFrame(pred_rows), summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="NLTF vNext production pipeline")
    parser.add_argument("stage", choices=["search", "select", "finalize", "scorecards",
                                          "forecast", "evidence", "all"])
    parser.add_argument("--stream", choices=VNEXT_STREAMS + ["ALL"], default="ALL")
    parser.add_argument("--workbook", action="append", default=None,
                        help="Completed assumption workbook(s) for the forecast stage")
    parser.add_argument("--time-budget", type=float, default=None,
                        help="Soft time budget in seconds for the search stage (resumable)")
    streams = VNEXT_STREAMS if args.stream == "ALL" else [args.stream]

    if args.stage in ("search", "all"):
        complete = stage_search(streams, time_budget=args.time_budget)
        if not complete:
            print("[search] incomplete; rerun the search stage to resume")
            return
    if args.stage in ("select", "all"):
        stage_select(streams)
    if args.stage in ("finalize", "all"):
        stage_finalize(streams)
    if args.stage in ("scorecards", "all"):
        stage_scorecards(streams)
    if args.stage in ("forecast", "all"):
        from .vnext_forward import stage_forecast
        stage_forecast(streams, args.workbook)
    if args.stage in ("evidence", "all"):
        from .vnext_evidence import stage_evidence
        stage_evidence(streams)


if __name__ == "__main__":
    main()

"""Build the standalone PED AR(1) VKT-per-capita review pack for Stata.

Extraction and documentation only. Nothing in the governed model, fitted state,
runtime packs, checkpoints or dashboard is altered.

Usage::

    python scripts/build_ped_ar1_stata_review_pack.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pipeline.vnext_core as vc  # noqa: E402

OUT = REPO_ROOT / "deliverables" / "PED_AR1_VKTpc_Stata_Review"
STATE_PATH = (
    REPO_ROOT
    / "data"
    / "dashboard_evidence_pack_reproducibility"
    / "ped_ar1"
    / "ar1_fitted_state.json"
)
HISTORY_PATH = REPO_ROOT / "data" / "model_input_history" / "ped_inputs.parquet"
MODEL_ID = "PED__DIAGLAB__B__glsar__ylag1__ar1__wexp"

# Canonical -> Stata name (<=32 chars, unique).
STATA_NAMES = {
    "period": "period",
    "qdate": "qdate",
    "year": "year",
    "quarter": "quarter",
    "vkt_per_capita": "vktpc",
    "log_vkt_per_capita": "ln_vktpc",
    "log_vkt_per_capita_lag1": "ln_vktpc_l1",
    "real_petrol_price_cents_per_litre": "petrol_real_cpl",
    "log_real_petrol_price": "ln_petrol",
    "real_gdp_per_capita_nzd": "gdp_pc_real",
    "log_real_gdp_per_capita": "ln_gdp_pc",
    "unemployment_percent": "unemp_pct",
    "unemployment_rate": "unemp_rate",
    "population": "population_context_only",
    "trend": "trend",
    "post2011": "post2011",
    "post2011_trend": "post2011_trend",
    "post2020": "post2020",
    "covid2020": "covid2020",
    "q2": "q2",
    "q3": "q3",
    "q4": "q4",
    "data_status": "data_status",
    "estimation_sample": "estimation_sample",
    "latest_actual": "latest_actual",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_state() -> dict[str, Any]:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def build_frames(state: dict[str, Any]) -> dict[str, pd.DataFrame]:
    stream_data = vc.load_stream_data(REPO_ROOT, "PED")
    exog = stream_data.exog
    history = pd.read_parquet(HISTORY_PATH)
    history["period"] = history["period"].astype(str)

    idx = exog.index
    frame = pd.DataFrame(index=idx)
    frame["period"] = [str(p) for p in idx]
    frame["year"] = [p.year for p in idx]
    frame["quarter"] = [p.quarter for p in idx]
    frame["vkt_per_capita"] = stream_data.y_raw.reindex(idx).to_numpy(dtype=float)
    frame["log_vkt_per_capita"] = stream_data.y_log.reindex(idx).to_numpy(dtype=float)
    frame["log_vkt_per_capita_lag1"] = frame["log_vkt_per_capita"].shift(1)
    frame["log_real_petrol_price"] = exog["petrol__log"].to_numpy(dtype=float)
    frame["log_real_gdp_per_capita"] = exog["gdp_pc__log"].to_numpy(dtype=float)
    frame["unemployment_rate"] = exog["unemp__level"].to_numpy(dtype=float)
    frame["trend"] = exog["time__trend"].to_numpy(dtype=float)
    frame["post2011"] = exog["time__post2011"].to_numpy(dtype=float)
    frame["post2011_trend"] = exog["time__post2011_trend"].to_numpy(dtype=float)
    frame["post2020"] = exog["time__post2020"].to_numpy(dtype=float)
    frame["covid2020"] = exog["time__covid2020"].to_numpy(dtype=float)
    for q in (2, 3, 4):
        frame[f"q{q}"] = exog[f"time__q{q}"].to_numpy(dtype=float)
    frame["real_petrol_price_cents_per_litre"] = exog["petrol__level"].to_numpy(dtype=float)
    frame["real_gdp_per_capita_nzd"] = exog["gdp_pc__level"].to_numpy(dtype=float)
    frame["population"] = exog["population__level"].to_numpy(dtype=float)

    merge_cols = ["period", "unemployment_percent", "data_status"]
    frame = frame.merge(
        history[[c for c in merge_cols if c in history.columns]],
        on="period", how="left",
    )

    start, end = state["train_window_start"], state["train_window_end"]
    order = {p: i for i, p in enumerate(frame["period"])}
    frame["estimation_sample"] = (
        (frame["period"].map(order) >= order[start])
        & (frame["period"].map(order) <= order[end])
        & frame["vkt_per_capita"].gt(0)
        & frame["log_vkt_per_capita_lag1"].notna()
    ).astype(int)
    frame["latest_actual"] = (frame["period"] == end).astype(int)
    frame["is_placeholder"] = (~frame["vkt_per_capita"].gt(0)).astype(int)
    frame["excluded_reason"] = np.where(
        frame["is_placeholder"].eq(1),
        "zero-target placeholder row; not an actual observation",
        np.where(frame["estimation_sample"].eq(1), "", "outside production estimation window"),
    )
    # Quarterly Stata date: quarters since 1960q1.
    frame["qdate"] = (frame["year"] - 1960) * 4 + (frame["quarter"] - 1)

    source = frame.copy()
    est_cols = [c for c in STATA_NAMES if c in frame.columns]
    estimation = frame.loc[
        frame["period"].map(order) >= order["2002Q1"], est_cols
    ].reset_index(drop=True)
    return {"estimation": estimation, "source": source}


def production_coefficients(state: dict[str, Any]) -> pd.DataFrame:
    names = ["intercept", *state["features"], "log_vkt_per_capita_lag1"]
    beta = list(state["beta"])
    assert len(names) == len(beta), f"{len(names)} names vs {len(beta)} betas"
    rows = [
        {"order": i, "term": n, "role": "regressor" if i else "intercept",
         "value_full_precision": repr(float(b)), "value_rounded": round(float(b), 8)}
        for i, (n, b) in enumerate(zip(names, beta))
    ]
    rows.append({"order": len(rows), "term": "ar1_rho", "role": "AR(1) error coefficient",
                 "value_full_precision": repr(float(state["rho"][0])),
                 "value_rounded": round(float(state["rho"][0]), 8)})
    rows.append({"order": len(rows), "term": "last_observed_residual",
                 "role": "initialises the forward AR recursion",
                 "value_full_precision": repr(float(state["last_resid"])),
                 "value_rounded": round(float(state["last_resid"]), 8)})
    return pd.DataFrame(rows)


def training_reference(state: dict[str, Any], estimation: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    fit = state["training_fit_levels"]
    rows = []
    est = estimation[estimation["estimation_sample"].eq(1)]
    names = state["features"] + ["log_vkt_per_capita_lag1"]
    beta = np.asarray(state["beta"], dtype=float)
    colmap = {
        "petrol__log": "log_real_petrol_price",
        "gdp_pc__log": "log_real_gdp_per_capita",
        "unemp__level": "unemployment_rate",
        "time__trend": "trend",
        "time__post2011_trend": "post2011_trend",
        "time__post2020": "post2020",
        "time__covid2020": "covid2020",
        "time__q2": "q2", "time__q3": "q3", "time__q4": "q4",
        "log_vkt_per_capita_lag1": "log_vkt_per_capita_lag1",
    }
    for _, r in est.iterrows():
        x = np.array([1.0] + [float(r[colmap[n]]) for n in names])
        xb = float(x @ beta)
        committed = fit.get(str(r["period"]))
        rows.append({
            "period": r["period"],
            "actual_level": float(r["vkt_per_capita"]),
            "actual_log": float(r["log_vkt_per_capita"]),
            "xbeta_log": xb,
            "xbeta_level": float(np.exp(xb)),
            "raw_residual_log": float(r["log_vkt_per_capita"]) - xb,
            "committed_training_fit_level": committed,
            "abs_delta_vs_committed": (
                abs(float(np.exp(xb)) - float(committed)) if committed is not None else np.nan
            ),
        })
    out = pd.DataFrame(rows)
    out["lagged_residual_log"] = out["raw_residual_log"].shift(1)
    return out, float(out["abs_delta_vs_committed"].max())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results").mkdir(exist_ok=True)
    state = load_state()

    print("[gate] state hash vs model-input manifest ...")
    hist_sha = sha256(HISTORY_PATH)
    assert hist_sha == state["input_history_sha256"], "history hash mismatch"
    print(f"       ok {hist_sha[:16]}")

    frames = build_frames(state)
    est, src = frames["estimation"], frames["source"]

    n_est = int(est["estimation_sample"].sum())
    assert n_est == state["train_rows"], f"{n_est} estimation rows vs {state['train_rows']}"
    sel = est[est["estimation_sample"].eq(1)]
    assert sel["period"].iloc[0] == state["train_window_start"]
    assert sel["period"].iloc[-1] == state["train_window_end"]
    assert not est[est["period"].eq("2026Q1")]["estimation_sample"].astype(bool).any()
    print(f"[gate] estimation sample {n_est} rows, "
          f"{sel['period'].iloc[0]}-{sel['period'].iloc[-1]}  ok")

    coefs = production_coefficients(state)
    ref, max_delta = training_reference(state, est)
    print(f"[gate] training-fit replay max abs delta: {max_delta:.3e}")

    # Stata-safe rename for the DTA.
    dta = est.rename(columns=STATA_NAMES)
    assert all(len(c) <= 32 for c in dta.columns), "stata name too long"
    assert len(set(dta.columns)) == len(dta.columns), "duplicate stata names"
    required = ["ln_vktpc", "ln_vktpc_l1", "ln_petrol", "ln_gdp_pc", "unemp_rate",
                "trend", "post2011_trend", "post2020", "covid2020", "q2", "q3", "q4"]
    miss = dta[dta["estimation_sample"].eq(1)][required].isna().sum().sum()
    assert miss == 0, f"{miss} missing values in required estimation fields"
    print("[gate] stata names unique/<=32, no missing required values  ok")

    est.to_csv(OUT / "ped_ar1_estimation_data.csv", index=False)
    try:
        dta.to_stata(OUT / "ped_ar1_estimation_data.dta", write_index=False, version=118)
        print("[write] ped_ar1_estimation_data.dta")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] DTA write failed: {exc}")
    src.to_csv(OUT / "ped_ar1_source_extract.csv", index=False)
    coefs.to_csv(OUT / "ped_ar1_production_coefficients.csv", index=False)
    ref.to_csv(OUT / "ped_ar1_training_reference.csv", index=False)

    inventory = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            inventory[str(path.relative_to(OUT)).replace("\\", "/")] = sha256(path)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                            capture_output=True, text=True).stdout.strip()
    lineage = {
        "repository": "AdrianD234/NLTF-revenue-ML-model-dashboard",
        "main_merge_commit": "bcdf82b9e9049647b733b2e48c5d03eb5b5f4e85",
        "extraction_commit": commit,
        "model_id": MODEL_ID,
        "scorer_version": state["scorer_version"],
        "algorithm": state["algorithm"],
        "source_parquet_sha256": hist_sha,
        "fitted_state_sha256": sha256(STATE_PATH),
        "training_fit_replay_max_abs_delta": max_delta,
        "estimation_rows": n_est,
        "estimation_start": sel["period"].iloc[0],
        "estimation_end": sel["period"].iloc[-1],
        "source_extract_rows": int(len(src)),
        "generation_command": "python scripts/build_ped_ar1_stata_review_pack.py",
        "files": inventory,
    }
    (OUT / "lineage_manifest.json").write_text(
        json.dumps(lineage, indent=2), encoding="utf-8")

    print(f"\nestimation rows : {n_est}")
    print(f"source rows     : {len(src)}")
    print(f"replay delta    : {max_delta:.3e}")
    print(f"written to      : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

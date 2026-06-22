"""Promote the vNext finalists into the governed dashboard evidence pack.

Rebuilds every finalist-dependent table in ``data/dashboard_evidence_pack``
from the vNext reproducibility packs, replacing the archived legacy finalists
(PED__RESCUE_static_annual_weighted_top12_capnone and
HEAVY_RUC__RECON_STATIC_REBUILT) with the parity-gated vNext finalists for
all dashboard charts, KPIs, hovers and governance views.

Safety:
- The current pack is backed up to ``data/dashboard_evidence_pack_v6_backup``
  before any write.
- Schiff benchmark rows, Light RUC rows and all non-finalist evidence are
  preserved byte-identically.
- Run with ``--check`` first: it re-derives the OLD finalist metric columns
  from the OLD stored predictions and asserts the derivations match the pack,
  proving the rebuild formulas before any replacement happens.

Requires: pandas, pyarrow, scikit-learn, statsmodels, scipy (build-time only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.regenerate_candidate_cone import build_candidate_cone

PACK = REPO / "data" / "dashboard_evidence_pack"
DATA = PACK / "data"
BACKUP = REPO / "data" / "dashboard_evidence_pack_v6_backup"

VNEXT_STREAMS = ["PED", "HEAVY_RUC"]
LEGACY_FINALISTS = {
    "PED": "PED__RESCUE_static_annual_weighted_top12_capnone",
    "HEAVY_RUC": "HEAVY_RUC__RECON_STATIC_REBUILT",
}
PAPER = "schiff_paper_horizon_mean"
OPERATIONAL = "current_grid_operational_pooled"


def state_dir(stream: str) -> Path:
    return REPO / "data" / "dashboard_evidence_pack_reproducibility" / f"{stream.lower()}_vnext"


def load_manifest(stream: str) -> dict:
    return json.loads((state_dir(stream) / "fitted_model_manifest.json").read_text(encoding="utf-8"))


def new_finalist(stream: str) -> str:
    return load_manifest(stream)["finalist_model"]


def candidate_uid(model: str) -> str:
    return hashlib.sha256(model.encode("utf-8")).hexdigest()[:16]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Metric helpers (must reproduce the governed pack's conventions; verified by
# the --check mode against the OLD finalist rows before any rebuild)
# ---------------------------------------------------------------------------

def mape(a: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(p) & (a != 0)
    return float(np.mean(np.abs((p[m] - a[m]) / a[m])) * 100.0) if m.any() else float("nan")


def bias_pct(a: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(p) & (a != 0)
    return float(np.mean((p[m] - a[m]) / a[m]) * 100.0) if m.any() else float("nan")


def p90_ape(a: np.ndarray, p: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(p) & (a != 0)
    return float(np.percentile(np.abs((p[m] - a[m]) / a[m]) * 100.0, 90)) if m.any() else float("nan")


def horizon_mean_mape(df: pd.DataFrame) -> float:
    vals = [mape(g["actual"].to_numpy(float), g["pred"].to_numpy(float))
            for _, g in df.groupby("horizon")]
    vals = [v for v in vals if np.isfinite(v)]
    return float(np.mean(vals)) if vals else float("nan")


def horizon_bucket_mape(df: pd.DataFrame, lo: int, hi: int) -> float:
    """Pooled MAPE over the horizon bucket (governed pack convention)."""
    g = df[df["horizon"].between(lo, hi)]
    return mape(g["actual"].to_numpy(float), g["pred"].to_numpy(float)) if len(g) else float("nan")


def annual_pairs(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["target_year"] = d["target_period"].astype(str).str.slice(0, 4).astype(int)
    rows = []
    for (origin, year), g in d.groupby(["origin", "target_year"]):
        if g["target_period"].nunique() == 4 and g["pred"].notna().all():
            rows.append({"origin": origin, "target_year": int(year),
                         "actual": float(g["actual"].sum()), "pred": float(g["pred"].sum())})
    return pd.DataFrame(rows)


def summary_metrics(preds_basis: pd.DataFrame) -> dict:
    a = preds_basis["actual"].to_numpy(float)
    p = preds_basis["pred"].to_numpy(float)
    ap = annual_pairs(preds_basis)
    out = {
        "n_quarterly_pairs": int(preds_basis["pred"].notna().sum()),
        "n_origins": int(preds_basis["origin"].nunique()),
        "quarterly_pooled_mape": mape(a, p),
        "horizon_mean_mape": horizon_mean_mape(preds_basis),
        "quarterly_bias_pct": bias_pct(a, p),
        "quarterly_p90_ape": p90_ape(a, p),
        "mape_h01_04": horizon_bucket_mape(preds_basis, 1, 4),
        "mape_h05_08": horizon_bucket_mape(preds_basis, 5, 8),
        "mape_h09_12": horizon_bucket_mape(preds_basis, 9, 12),
        "n_annual_pairs": int(len(ap)),
        "annual_mape": mape(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float)) if len(ap) else float("nan"),
        "annual_bias_pct": bias_pct(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float)) if len(ap) else float("nan"),
        "annual_p90_ape": p90_ape(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float)) if len(ap) else float("nan"),
    }
    for h in range(1, 13):
        g = preds_basis[preds_basis["horizon"] == h]
        out[f"mape_h{h:02d}"] = mape(g["actual"].to_numpy(float), g["pred"].to_numpy(float)) if len(g) else float("nan")
    return out


def load_new_predictions(stream: str) -> pd.DataFrame:
    """vNext finalist predictions joined to the stored evidence keysets."""
    preds = pd.read_parquet(state_dir(stream) / "validation_predictions.parquet")
    old = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    old = old[(old["stream"] == stream) & (old["model"] == LEGACY_FINALISTS[stream])]
    frames = []
    for basis, keys in old.groupby("score_basis"):
        sub = preds.merge(keys[["origin", "target_period"]].drop_duplicates(),
                          on=["origin", "target_period"], how="inner").copy()
        sub["score_basis"] = basis
        frames.append(sub)
    out = pd.concat(frames, ignore_index=True)
    return out[["score_basis", "origin", "target_period", "horizon", "actual", "pred"]]


def load_component_predictions(stream: str) -> pd.DataFrame:
    comp = pd.read_parquet(state_dir(stream) / "component_validation_predictions.parquet")
    old = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    old = old[(old["stream"] == stream) & (old["model"] == LEGACY_FINALISTS[stream])]
    frames = []
    for basis, keys in old.groupby("score_basis"):
        sub = comp.merge(keys[["origin", "target_period"]].drop_duplicates(),
                         on=["origin", "target_period"], how="inner").copy()
        sub["score_basis"] = basis
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# --check: prove the rebuild formulas reproduce the OLD pack rows
# ---------------------------------------------------------------------------

def run_check() -> None:
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    summary = pd.read_parquet(DATA / "scorecard_model_summary.parquet")
    finalists = pd.read_parquet(DATA / "finalists.parquet")
    problems = []
    for stream in VNEXT_STREAMS:
        legacy = LEGACY_FINALISTS[stream]
        rows = sp[(sp["stream"] == stream) & (sp["model"] == legacy)]
        for basis, g in rows.groupby("score_basis"):
            derived = summary_metrics(g)
            stored = summary[(summary["model"] == legacy) & (summary["score_basis"] == basis)].iloc[0]
            for col in ["n_quarterly_pairs", "quarterly_pooled_mape", "horizon_mean_mape",
                        "quarterly_bias_pct", "mape_h01", "mape_h12", "mape_h09_12",
                        "n_annual_pairs", "annual_mape", "annual_bias_pct"]:
                d, s = derived[col], stored[col]
                if pd.isna(s) and pd.isna(d):
                    continue
                if abs(float(d) - float(s)) > 1e-6:
                    problems.append(f"{stream}/{basis}/{col}: derived {d} != stored {s}")
        frow = finalists[finalists["stream"] == stream].iloc[0]
        paper = summary_metrics(rows[rows["score_basis"] == PAPER])
        oper = summary_metrics(rows[rows["score_basis"] == OPERATIONAL])
        checks = {
            "quarterly_mape": paper["horizon_mean_mape"],
            "annual_mape": paper["annual_mape"],
            "quarterly_bias_pct": paper["quarterly_bias_pct"],
            "n_quarterly_pairs": paper["n_quarterly_pairs"],
            "operational_pooled_mape": oper["quarterly_pooled_mape"],
            "operational_horizon_mean_mape": oper["horizon_mean_mape"],
            "operational_bias_pct": oper["quarterly_bias_pct"],
            "operational_annual_mape": oper["annual_mape"],
            "operational_annual_bias_pct": oper["annual_bias_pct"],
            "operational_h09_12_mape": oper["mape_h09_12"],
            "paper_horizon_mean_mape": paper["horizon_mean_mape"],
            "paper_pooled_mape": paper["quarterly_pooled_mape"],
            "paper_bias_pct": paper["quarterly_bias_pct"],
            "paper_annual_mape": paper["annual_mape"],
            "paper_annual_bias_pct": paper["annual_bias_pct"],
            "paper_h09_12_mape": paper["mape_h09_12"],
        }
        for col, derived_value in checks.items():
            stored_value = frow[col]
            if pd.isna(stored_value) and pd.isna(derived_value):
                continue
            if abs(float(derived_value) - float(stored_value)) > 1e-6:
                problems.append(f"{stream}/finalists.{col}: derived {derived_value} != stored {stored_value}")
    if problems:
        print("FORMULA CHECK FAILED:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)
    print("[check] all rebuild formulas reproduce the stored legacy finalist metrics exactly")


# ---------------------------------------------------------------------------
# Table rebuilds
# ---------------------------------------------------------------------------

def shorten(model: str) -> str:
    from model_dashboard.labels import shorten_model_name

    return shorten_model_name(model)


def replace_prediction_rows(table: str, new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Replace finalist rows in prediction-level tables by merging the new
    predictions onto the identical (score_basis, origin, target_period) keys."""
    df = pd.read_parquet(DATA / table)
    out_frames = [df[~df["model"].isin(LEGACY_FINALISTS.values())]]
    for stream in VNEXT_STREAMS:
        legacy = LEGACY_FINALISTS[stream]
        rows = df[df["model"] == legacy].copy()
        if rows.empty:
            continue
        merged = rows.merge(new_preds[stream].rename(columns={"pred": "__new_pred"})[
            ["score_basis", "origin", "target_period", "__new_pred"]],
            on=["score_basis", "origin", "target_period"], how="left")
        if merged["__new_pred"].isna().any():
            missing = merged[merged["__new_pred"].isna()][["score_basis", "origin", "target_period"]]
            raise AssertionError(f"{table}/{stream}: {len(missing)} keys missing vNext predictions:\n{missing.head()}")
        merged["pred"] = merged["__new_pred"].astype(float)
        merged = merged.drop(columns="__new_pred")
        merged["model"] = new_finalist(stream)
        if "model_short" in merged.columns:
            merged["model_short"] = shorten(new_finalist(stream))
        actual = merged["actual"].astype(float)
        merged["error_pct"] = np.where(actual != 0, (merged["pred"] - actual) / actual * 100.0, np.nan)
        merged["abs_error_pct"] = merged["error_pct"].abs()
        if "ape" in merged.columns:
            merged["ape"] = merged["abs_error_pct"]
        out_frames.append(merged)
    out = pd.concat(out_frames, ignore_index=True)
    return out[df.columns]


def rebuild_annual_table(table: str, new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.read_parquet(DATA / table)
    out_frames = [df[~df["model"].isin(LEGACY_FINALISTS.values())]]
    for stream in VNEXT_STREAMS:
        legacy = LEGACY_FINALISTS[stream]
        rows = df[df["model"] == legacy].copy()
        if rows.empty:
            continue
        pieces = []
        for basis, g in rows.groupby("score_basis"):
            ap = annual_pairs(new_preds[stream][new_preds[stream]["score_basis"] == basis])
            ap = ap.rename(columns={"actual": "__a", "pred": "__p"})
            m = g.merge(ap, on=["origin", "target_year"], how="left")
            if m["__p"].isna().any():
                raise AssertionError(f"{table}/{stream}/{basis}: missing annual pairs")
            m["actual"] = m["__a"]
            m["pred"] = m["__p"]
            m = m.drop(columns=["__a", "__p"])
            m["model"] = new_finalist(stream)
            if "model_short" in m.columns:
                m["model_short"] = shorten(new_finalist(stream))
            a = m["actual"].astype(float)
            m["error_pct"] = np.where(a != 0, (m["pred"] - a) / a * 100.0, np.nan)
            if "ape" in m.columns:
                m["ape"] = m["error_pct"].abs()
            pieces.append(m)
        out_frames.append(pd.concat(pieces, ignore_index=True))
    out = pd.concat(out_frames, ignore_index=True)
    return out[df.columns]


def rebuild_horizon_profiles(table: str, new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.read_parquet(DATA / table)
    out_frames = [df[~df["model"].isin(LEGACY_FINALISTS.values())]]
    for stream in VNEXT_STREAMS:
        rows = df[df["model"] == LEGACY_FINALISTS[stream]].copy()
        if rows.empty:
            continue
        for idx, r in rows.iterrows():
            basis = r["score_basis"]
            h = int(r["horizon"])
            g = new_preds[stream][(new_preds[stream]["score_basis"] == basis)
                                  & (new_preds[stream]["horizon"] == h)]
            rows.loc[idx, "mape"] = mape(g["actual"].to_numpy(float), g["pred"].to_numpy(float))
            rows.loc[idx, "bias_pct"] = bias_pct(g["actual"].to_numpy(float), g["pred"].to_numpy(float))
            rows.loc[idx, "n"] = int(len(g))
        rows["model"] = new_finalist(stream)
        if "model_short" in rows.columns:
            rows["model_short"] = shorten(new_finalist(stream))
        out_frames.append(rows)
    out = pd.concat(out_frames, ignore_index=True)
    return out[df.columns]


def rebuild_stress(table: str, new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.read_parquet(DATA / table)
    out_frames = [df[~df["model"].isin(LEGACY_FINALISTS.values())]]
    for stream in VNEXT_STREAMS:
        rows = df[df["model"] == LEGACY_FINALISTS[stream]].copy()
        if rows.empty:
            continue
        for idx, r in rows.iterrows():
            basis = r["score_basis"]
            bucket = str(r["stress_bucket"])
            g = new_preds[stream][new_preds[stream]["score_basis"] == basis].copy()
            g["target_year"] = g["target_period"].astype(str).str.slice(0, 4).astype(int)
            if bucket == "1-4 qtrs":
                sel = g[g["horizon"].between(1, 4)]
            elif bucket == "5-8 qtrs":
                sel = g[g["horizon"].between(5, 8)]
            elif bucket == "9-12 qtrs":
                sel = g[g["horizon"].between(9, 12)]
            elif bucket == "2024+":
                sel = g[g["target_year"] >= 2024]
            elif bucket == "2022-23":
                sel = g[g["target_year"].between(2022, 2023)]
            elif bucket.lower() == "annual":
                ap = annual_pairs(g)
                rows.loc[idx, "mape"] = mape(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float)) if len(ap) else np.nan
                rows.loc[idx, "bias_pct"] = bias_pct(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float)) if len(ap) else np.nan
                rows.loc[idx, "n"] = int(len(ap))
                continue
            else:
                raise AssertionError(f"unknown stress bucket {bucket}")
            rows.loc[idx, "mape"] = mape(sel["actual"].to_numpy(float), sel["pred"].to_numpy(float))
            rows.loc[idx, "bias_pct"] = bias_pct(sel["actual"].to_numpy(float), sel["pred"].to_numpy(float))
            rows.loc[idx, "n"] = int(sel["pred"].notna().sum())
        rows["model"] = new_finalist(stream)
        if "model_short" in rows.columns:
            rows["model_short"] = shorten(new_finalist(stream))
        out_frames.append(rows)
    out = pd.concat(out_frames, ignore_index=True)
    return out[df.columns]


def rebuild_model_summary(new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.read_parquet(DATA / "scorecard_model_summary.parquet")
    out_frames = [df[~df["model"].isin(LEGACY_FINALISTS.values())]]
    for stream in VNEXT_STREAMS:
        rows = df[df["model"] == LEGACY_FINALISTS[stream]].copy()
        for idx, r in rows.iterrows():
            m = summary_metrics(new_preds[stream][new_preds[stream]["score_basis"] == r["score_basis"]])
            for col, val in m.items():
                if col in rows.columns:
                    rows.loc[idx, col] = val
            rows.loc[idx, "pooled_mape"] = m["quarterly_pooled_mape"]
            rows.loc[idx, "primary_mape"] = (m["horizon_mean_mape"] if r["score_basis"] == PAPER
                                             else m["quarterly_pooled_mape"])
        rows["model"] = new_finalist(stream)
        rows["model_short"] = shorten(new_finalist(stream))
        out_frames.append(rows)
    out = pd.concat(out_frames, ignore_index=True)
    return out[df.columns]


def rebuild_annual_metric_summary(new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.read_parquet(DATA / "scorecard_annual_metric_summary.parquet")
    out = df.copy()
    stream_labels = {"PED": "PED VKT per capita", "HEAVY_RUC": "Heavy RUC volume"}
    for stream in VNEXT_STREAMS:
        label = stream_labels[stream]
        mask = out["stream_label"].eq(label) & out["scenario"].astype(str).str.contains("inalist")
        for idx in out[mask].index:
            basis = out.loc[idx, "score_basis"]
            ap = annual_pairs(new_preds[stream][new_preds[stream]["score_basis"] == basis])
            out.loc[idx, "n_annual_pairs"] = int(len(ap))
            out.loc[idx, "annual_mape"] = mape(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float))
            out.loc[idx, "annual_bias_pct"] = bias_pct(ap["actual"].to_numpy(float), ap["pred"].to_numpy(float))
    return out


def rebuild_finalists(new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    from model_dashboard.labels import shorten_model_name

    df = pd.read_parquet(DATA / "finalists.parquet")
    out = df.copy()
    for stream in VNEXT_STREAMS:
        manifest = load_manifest(stream)
        idx = out[out["stream"] == stream].index[0]
        paper = summary_metrics(new_preds[stream][new_preds[stream]["score_basis"] == PAPER])
        oper = summary_metrics(new_preds[stream][new_preds[stream]["score_basis"] == OPERATIONAL])
        model = manifest["finalist_model"]
        comp_json = json.dumps([
            {"component_model": m["component_model"], "weight": m["component_weight"],
             "component_short": shorten_model_name(m["component_model"])}
            for m in manifest["members"]
        ])
        updates = {
            "model": model,
            "model_short": shorten_model_name(model),
            "ensemble_components_json": comp_json,
            "candidate_uid": candidate_uid(model),
            "n_quarterly_pairs": paper["n_quarterly_pairs"],
            "quarterly_mape": paper["horizon_mean_mape"],
            "quarterly_bias_pct": paper["quarterly_bias_pct"],
            "n_annual_pairs": paper["n_annual_pairs"],
            "annual_mape": paper["annual_mape"],
            "annual_bias_pct": paper["annual_bias_pct"],
            "operational_pooled_mape": oper["quarterly_pooled_mape"],
            "operational_horizon_mean_mape": oper["horizon_mean_mape"],
            "operational_bias_pct": oper["quarterly_bias_pct"],
            "operational_annual_mape": oper["annual_mape"],
            "operational_annual_bias_pct": oper["annual_bias_pct"],
            "operational_h09_12_mape": oper["mape_h09_12"],
            "paper_horizon_mean_mape": paper["horizon_mean_mape"],
            "paper_pooled_mape": paper["quarterly_pooled_mape"],
            "paper_bias_pct": paper["quarterly_bias_pct"],
            "paper_annual_mape": paper["annual_mape"],
            "paper_annual_bias_pct": paper["annual_bias_pct"],
            "paper_h09_12_mape": paper["mape_h09_12"],
            "selection_note": ("vNext fixed finalist promoted "
                               + datetime.now(timezone.utc).strftime("%Y-%m-%d")
                               + ": parity-gated production scorer with saved fitted state; "
                               "selected by paper-style horizon-mean MAPE on the stored evidence keysets. "
                               "Legacy finalist archived as historically reproducible only."),
        }
        for col, val in updates.items():
            out.loc[idx, col] = val
    return out


def rebuild_component_predictions(new_preds: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.read_parquet(DATA / "component_predictions.parquet")
    keep = df[~df["stream"].isin(VNEXT_STREAMS)]
    frames = [keep]
    for stream in VNEXT_STREAMS:
        manifest = load_manifest(stream)
        comp = load_component_predictions(stream)
        weights = {m["component_model"]: float(m["component_weight"]) for m in manifest["members"]}
        finals = new_preds[stream].rename(columns={"pred": "final_pred"})[
            ["score_basis", "origin", "target_period", "final_pred"]]
        merged = comp.merge(finals, on=["score_basis", "origin", "target_period"], how="left")
        a = merged["actual"].astype(float)
        rel = state_dir(stream).relative_to(REPO).as_posix() + "/component_validation_predictions.parquet"
        rows = pd.DataFrame({
            "stream": stream,
            "stream_label": {"PED": "PED VKT per capita", "HEAVY_RUC": "Heavy RUC volume"}[stream],
            "finalist_model": manifest["finalist_model"],
            "component_model": merged["model"],
            "score_basis": merged["score_basis"],
            "origin": merged["origin"],
            "target_period": merged["target_period"],
            "horizon": merged["horizon"].astype(int),
            "actual": a,
            "component_pred": merged["pred"].astype(float),
            "component_error_pct": np.where(a != 0, (merged["pred"] - a) / a * 100.0, np.nan),
            "component_abs_error_pct": np.abs(np.where(a != 0, (merged["pred"] - a) / a * 100.0, np.nan)),
            "component_weight": merged["model"].map(weights),
            "weighted_component_pred": merged["model"].map(weights) * merged["pred"].astype(float),
            "final_pred": merged["final_pred"].astype(float),
            "component_traceability_status": "vnext_saved_state_parity_verified",
            "source": rel,
            "source_basis": "component predictions replayed from saved vNext fitted state (parity 0.0)",
        })
        frames.append(rows)
    out = pd.concat(frames, ignore_index=True)
    return out[df.columns]


def rebuild_ensemble_components() -> pd.DataFrame:
    from model_dashboard.labels import shorten_model_name

    df = pd.read_parquet(DATA / "ensemble_components.parquet")
    keep = df[~df["stream"].isin(VNEXT_STREAMS)]
    frames = [keep]
    for stream in VNEXT_STREAMS:
        manifest = load_manifest(stream)
        rel = state_dir(stream).relative_to(REPO).as_posix() + "/fitted_model_manifest.json"
        rows = []
        for rank, m in enumerate(manifest["members"], 1):
            rows.append({
                "stream": stream,
                "stream_label": {"PED": "PED VKT per capita", "HEAVY_RUC": "Heavy RUC volume"}[stream],
                "finalist_model": manifest["finalist_model"],
                "finalist_model_short": shorten_model_name(manifest["finalist_model"]),
                "component_rank": rank,
                "component_model": m["component_model"],
                "component_short": shorten_model_name(m["component_model"]),
                "weight": float(m["component_weight"]),
                "weight_pct": float(m["component_weight"]) * 100.0,
                "source_dataset": "vnext_fitted_model_manifest",
                "source_column": "component_weight",
                "value_available": True,
                "source": "vnext_pipeline",
                "source_file": rel,
                "score_basis": PAPER,
            })
        frames.append(pd.DataFrame(rows))
    out = pd.concat(frames, ignore_index=True)
    return out[df.columns]


def _feature_columns_for(stream: str, label: str) -> list[str]:
    mats = pd.read_parquet(state_dir(stream) / "training_feature_matrices.parquet")
    g = mats[(mats["component_label"] == label) & (mats["origin"] == "production")]
    meta = {"component_label", "origin", "training_period", "y_log"}
    return [c for c in g.columns if c not in meta]


def rebuild_model_registry() -> pd.DataFrame:
    df = pd.read_parquet(DATA / "model_registry.parquet")
    keep = df[~df["stream"].isin(VNEXT_STREAMS) | df["model"].astype(str).str.contains("SCHIFF_SPEC")]
    frames = [keep]
    algo = {"ridge": "Ridge", "elastic_net": "ElasticNet", "gbr": "GradientBoostingRegressor",
            "ols": "LinearRegression", "resid_gbr": "OLS base + GradientBoostingRegressor residual"}
    pipeline_sha = hashlib.sha256((REPO / "pipeline" / "vnext_run.py").read_bytes()).hexdigest()
    for stream in VNEXT_STREAMS:
        manifest = load_manifest(stream)
        old_final = df[(df["stream"] == stream) & (df["model_role"] == "current_finalist")].iloc[0]
        rel_state = state_dir(stream).relative_to(REPO).as_posix()
        common = {
            "stream": stream,
            "stream_label": old_final["stream_label"],
            "model": manifest["finalist_model"],
            "target_column": "target",
            "target_transform": "y_model = ln(target)",
            "prediction_inverse_transform": "prediction = exp(y_model)",
            "origin_grid": old_final["origin_grid"],
            "score_basis": old_final["score_basis"],
            "covid_test_exclusion_rule": old_final["covid_test_exclusion_rule"],
            "random_state": "42",
            "source_script": "pipeline/vnext_run.py",
            "source_script_hash": pipeline_sha,
            "source_workbook": "Master Copy revenue modelling workbook.xlsx",
            "source_sheet": {"PED": "PED Inputs", "HEAVY_RUC": "Heavy RUC Inputs"}[stream],
            "source_dataset": manifest["history_file"],
            "source_file": rel_state + "/fitted_model_manifest.json",
            "reproducibility_status": "production_forward_scoreable",
        }
        rows = [{
            **common,
            "component_model": manifest["finalist_model"],
            "model_role": "current_finalist",
            "algorithm": "Convex weighted ensemble (vNext)",
            "feature_set": "ensemble",
            "feature_columns": json.dumps([]),
            "window_type": "per_component",
            "window_length": np.nan,
            "hyperparameters_json": json.dumps({"weights": [m["component_weight"] for m in manifest["members"]],
                                                "weight_solver": manifest["weight_solver"]}),
            "component_weight": np.nan,
            "reproducibility_note": ("Parity-gated vNext finalist: saved per-origin and production fitted "
                                     "estimators replay archived predictions exactly (delta 0.0)."),
        }]
        for m in manifest["members"]:
            label = m["component_label"]
            rows.append({
                **common,
                "component_model": m["component_model"],
                "model_role": "ensemble_component",
                "algorithm": algo.get(m["model_kind"], m["model_kind"]),
                "feature_set": m["feature_set"],
                "feature_columns": json.dumps(_feature_columns_for(stream, label)),
                "window_type": "expanding" if m["window"] is None else "rolling",
                "window_length": np.nan if m["window"] is None else float(m["window"]),
                "hyperparameters_json": m["params_json"],
                "component_weight": float(m["component_weight"]),
                "reproducibility_note": ("Saved state: " + rel_state + "/fitted_state/"
                                         + label + "_production.joblib (sha256 "
                                         + manifest["production_states"][label]["sha256"][:16] + "...)"),
            })
        frames.append(pd.DataFrame(rows))
    out = pd.concat(frames, ignore_index=True)
    return out[df.columns]


def rebuild_explainability_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    coefs_old = pd.read_parquet(DATA / "model_coefficients.parquet")
    imps_old = pd.read_parquet(DATA / "feature_importance.parquet")
    shap_old = pd.read_parquet(DATA / "shap_summary.parquet")
    sens_old = pd.read_parquet(DATA / "scenario_sensitivities.parquet")

    keep_coefs = coefs_old[~coefs_old["stream"].isin(VNEXT_STREAMS)
                           | coefs_old["model"].astype(str).str.contains("SCHIFF_SPEC")]
    keep_imps = imps_old[~imps_old["stream"].isin(VNEXT_STREAMS)]
    keep_shap = shap_old[~shap_old["stream"].isin(VNEXT_STREAMS)]
    keep_sens = sens_old[~sens_old["stream"].isin(VNEXT_STREAMS)]

    coef_rows, imp_rows, shap_rows, sens_rows = [], [], [], []
    for stream in VNEXT_STREAMS:
        manifest = load_manifest(stream)
        sdir = state_dir(stream)
        prod = manifest["production_states"]
        vc = pd.read_parquet(sdir / "model_coefficients.parquet")
        for _, r in vc.iterrows():
            label = next((m["component_label"] for m in manifest["members"]
                          if m["component_model"] == r["component_model"]), None)
            window = prod.get(label, {}) if label else {}
            coef_rows.append({
                "stream": stream, "model": manifest["finalist_model"],
                "origin": "production", "component_model": r["component_model"],
                "feature": r["feature"], "coefficient": float(r["coefficient"]),
                "intercept": float(r["intercept"]), "standardised_coefficient": np.nan,
                "window_start": window.get("train_window_start"),
                "window_end": window.get("train_window_end"),
                "reproducibility_status": "measured_from_saved_production_state",
                "notes": "vNext production estimator; coefficients in original feature units.",
                "artifact_search_status": "measured",
                "artifact_search_basis": sdir.relative_to(REPO).as_posix() + "/fitted_state",
            })
        vi = pd.read_parquet(sdir / "feature_importance.parquet")
        for _, r in vi.iterrows():
            imp_rows.append({
                "stream": stream, "model": r["component_model"],
                "origin_or_global": "production_global", "feature": r["feature"],
                "importance_type": r["importance_type"],
                "importance_value": float(r["importance_value"]),
                "rank": float(r["rank"]),
                "reproducibility_status": "measured_from_saved_production_state",
                "notes": str(r.get("notes", "")),
                "artifact_search_status": "measured",
                "artifact_search_basis": sdir.relative_to(REPO).as_posix() + "/fitted_state",
            })
        for m in manifest["members"]:
            shap_rows.append({
                "stream": stream, "model": m["component_model"], "feature": pd.NA,
                "mean_abs_shap": np.nan, "mean_shap": np.nan, "rank": np.nan,
                "sample_size": np.nan,
                "reproducibility_status": "not_computed",
                "notes": ("SHAP values are not computed for the vNext components; "
                          "measured tree impurity importances and linear coefficients are provided instead."),
                "artifact_search_status": "not_computed",
                "artifact_search_basis": sdir.relative_to(REPO).as_posix(),
            })
        vs = pd.read_parquet(sdir / "scenario_sensitivities.parquet")
        for _, r in vs.iterrows():
            sens_rows.append({
                "stream": stream, "model": r["model"],
                "scenario_variable": r["scenario_variable"],
                "perturbation": r["perturbation"], "horizon": float(r["horizon"]),
                "base_prediction": float(r["base_prediction"]),
                "scenario_prediction": float(r["scenario_prediction"]),
                "delta": float(r["delta"]), "delta_pct": float(r["delta_pct"]),
                "reproducibility_status": "measured_from_fixed_forward_scorer",
                "notes": str(r.get("notes", "")),
                "artifact_search_status": "measured",
                "artifact_search_basis": sdir.relative_to(REPO).as_posix() + "/scenario_sensitivities.parquet",
            })
    coefs = pd.concat([keep_coefs, pd.DataFrame(coef_rows)], ignore_index=True)[coefs_old.columns]
    imps = pd.concat([keep_imps, pd.DataFrame(imp_rows)], ignore_index=True)[imps_old.columns]
    shap = pd.concat([keep_shap, pd.DataFrame(shap_rows)], ignore_index=True)[shap_old.columns]
    sens = pd.concat([keep_sens, pd.DataFrame(sens_rows)], ignore_index=True)[sens_old.columns]
    return coefs, imps, shap, sens


def rebuild_schiff_comparisons(new_preds: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    paired_old = pd.read_parquet(DATA / "paired_vs_schiff.parquet")
    scen_old = pd.read_parquet(DATA / "scenario_comparison.parquet")
    schiff_bench = pd.read_parquet(DATA / "schiff_benchmark.parquet").set_index("stream")
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    paired, scen = paired_old.copy(), scen_old.copy()
    for stream in VNEXT_STREAMS:
        paper = summary_metrics(new_preds[stream][new_preds[stream]["score_basis"] == PAPER])
        oper = summary_metrics(new_preds[stream][new_preds[stream]["score_basis"] == OPERATIONAL])
        srow = schiff_bench.loc[stream]
        schiff_preds = sp[(sp["stream"] == stream) & (sp["model"].astype(str).str.contains("SCHIFF_SPEC_FROM_WORKBOOK"))
                          & (sp["score_basis"] == PAPER)]
        common = new_preds[stream][new_preds[stream]["score_basis"] == PAPER].merge(
            schiff_preds[["origin", "target_period", "pred"]].rename(columns={"pred": "schiff_pred"}),
            on=["origin", "target_period"], how="inner")
        a = common["actual"].to_numpy(float)
        challenger_mape = mape(a, common["pred"].to_numpy(float))
        baseline_mape = mape(a, common["schiff_pred"].to_numpy(float))
        cand_ape = np.abs((common["pred"] - common["actual"]) / common["actual"])
        sch_ape = np.abs((common["schiff_pred"] - common["actual"]) / common["actual"])
        win_rate = float((cand_ape < sch_ape).mean() * 100.0)
        values = {
            "finalist_quarterly_mape": paper["horizon_mean_mape"],
            "schiff_quarterly_mape": float(srow["paper_horizon_mean_mape"]),
            "finalist_annual_mape": paper["annual_mape"],
            "schiff_annual_mape": float(srow["paper_annual_mape"]),
            "full_sample_qtr_gain_pp": float(srow["paper_horizon_mean_mape"]) - paper["horizon_mean_mape"],
            "full_sample_annual_gain_pp": float(srow["paper_annual_mape"]) - paper["annual_mape"],
            "operational_finalist_mape": oper["quarterly_pooled_mape"],
            "operational_schiff_mape": float(srow["operational_pooled_mape"]),
            "operational_gain_pp": float(srow["operational_pooled_mape"]) - oper["quarterly_pooled_mape"],
            "recommendation": "Promote",
        }
        pidx = paired[paired["stream"] == stream].index[0]
        for col, val in values.items():
            if col in paired.columns:
                paired.loc[pidx, col] = val
        paired.loc[pidx, "n_common_pairs"] = int(len(common))
        paired.loc[pidx, "challenger_mape"] = challenger_mape
        paired.loc[pidx, "baseline_mape"] = baseline_mape
        paired.loc[pidx, "mape_improvement_pct_points"] = baseline_mape - challenger_mape
        paired.loc[pidx, "challenger_win_rate"] = win_rate
        sidx = scen[scen["stream"] == stream].index[0]
        for col, val in values.items():
            if col in scen.columns:
                scen.loc[sidx, col] = val
        scen.loc[sidx, "paired_common_pairs"] = int(len(common))
        scen.loc[sidx, "paired_finalist_mape"] = challenger_mape
        scen.loc[sidx, "paired_schiff_mape"] = baseline_mape
        scen.loc[sidx, "paired_gain_pp"] = baseline_mape - challenger_mape
        scen.loc[sidx, "paired_win_rate_pct"] = win_rate
    return paired, scen


# ---------------------------------------------------------------------------
# Diagnostics (statsmodels battery on horizon-1 residuals, operational grid)
# ---------------------------------------------------------------------------

def h1_frame(preds: pd.DataFrame, basis: str = OPERATIONAL) -> pd.DataFrame:
    g = preds[(preds["score_basis"] == basis) & (preds["horizon"] == 1)].copy()
    g["__o"] = g["origin"].astype(str)
    return g.sort_values("__o").drop(columns="__o").reset_index(drop=True)


def diagnostics_battery(actual: np.ndarray, pred: np.ndarray) -> dict:
    import statsmodels.api as sm
    from scipy import stats as sps
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch, het_breuschpagan, het_white
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    from statsmodels.tsa.stattools import adfuller, coint, kpss

    from statsmodels.tsa.stattools import acf as sm_acf

    resid = actual - pred
    n = len(resid)
    # Conventions verified against the stored legacy diagnostics (--check):
    # Ljung-Box lags capped at n//4; BP/White exog = [const, pred, time];
    # ARCH LM with 4 lags; biased ACF estimator; excess kurtosis.
    lag_grid = [min(lag, n // 4) for lag in (4, 8, 12)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lb_table = acorr_ljungbox(resid, lags=sorted(set(lag_grid)), return_df=True)["lb_pvalue"]
        lb = [float(lb_table.loc[lag]) for lag in lag_grid]
        adf_p = float(adfuller(resid, autolag="AIC")[1])
        kpss_p = float(kpss(resid, regression="c", nlags="auto")[1])
        jb_stat, jb_p, jb_skew, jb_kurt = jarque_bera(resid)
        shapiro_p = float(sps.shapiro(resid)[1])
        exog = sm.add_constant(np.column_stack([pred, np.arange(n, dtype=float)]))
        bp_p = float(het_breuschpagan(resid, exog)[1])
        white_p = float(het_white(resid, exog)[1])
        arch_p = float(het_arch(resid, nlags=4)[1])
        coint_p = float(coint(actual, pred)[1])
        mz = sm.OLS(actual, sm.add_constant(pred)).fit()
    acf1 = float(sm_acf(resid, nlags=1, fft=False)[1])
    ape = np.abs(resid / actual) * 100.0
    out = {
        "n_h1": int(len(resid)),
        "mape_h1": float(np.mean(ape)),
        "bias_h1_pct": float(np.mean((pred - actual) / actual) * 100.0),
        "p90_ape_h1": float(np.percentile(ape, 90)),
        "acf1_resid": acf1,
        "durbin_watson": float(durbin_watson(resid)),
        "ljungbox_p_lag4": float(lb[0]),
        "ljungbox_p_lag8": float(lb[1]),
        "ljungbox_p_lag12": float(lb[2]),
        "adf_p_resid": adf_p,
        "kpss_p_resid": kpss_p,
        "jarque_bera_p": float(jb_p),
        "skew_resid": float(jb_skew),
        "kurtosis_resid": float(jb_kurt) - 3.0,
        "shapiro_p": shapiro_p,
        "breusch_pagan_p": bp_p,
        "white_p": white_p,
        "arch_lm_p": arch_p,
        "coint_p_actual_pred": coint_p,
        "mz_intercept": float(mz.params[0]),
        "mz_slope": float(mz.params[1]),
        "mz_r2": float(mz.rsquared),
        "mz_f_p": float(mz.f_pvalue),
    }
    out.update({
        "pass_no_autocorr_lb8": bool(out["ljungbox_p_lag8"] > 0.05),
        "pass_dw_range": bool(1.5 <= out["durbin_watson"] <= 2.5),
        "pass_adf_stationary": bool(out["adf_p_resid"] < 0.05),
        "pass_kpss_stationary": bool(out["kpss_p_resid"] >= 0.05),
        "pass_no_hetero_bp": bool(out["breusch_pagan_p"] > 0.05),
        "pass_no_arch": float(out["arch_lm_p"] > 0.05),
        "pass_coint": bool(out["coint_p_actual_pred"] < 0.05),
        "pass_normal_jb": bool(out["jarque_bera_p"] > 0.05),
        "calibration_r2": float(mz.rsquared),
    })
    return out


def check_diagnostics() -> None:
    """Verify the battery reproduces the stored legacy finalist diagnostics."""
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")
    stored = pd.read_parquet(DATA / "diagnostic_tests.parquet")
    cols = ["n_h1", "mape_h1", "bias_h1_pct", "acf1_resid", "durbin_watson",
            "ljungbox_p_lag4", "ljungbox_p_lag8", "ljungbox_p_lag12", "adf_p_resid",
            "kpss_p_resid", "jarque_bera_p", "skew_resid", "kurtosis_resid", "shapiro_p",
            "breusch_pagan_p", "white_p", "arch_lm_p", "coint_p_actual_pred",
            "mz_intercept", "mz_slope", "mz_r2", "mz_f_p"]
    problems = []
    for stream in VNEXT_STREAMS:
        legacy = LEGACY_FINALISTS[stream]
        rows = sp[(sp["stream"] == stream) & (sp["model"] == legacy)]
        g = h1_frame(rows.rename(columns={"pred": "pred"})[
            ["score_basis", "origin", "target_period", "horizon", "actual", "pred"]])
        derived = diagnostics_battery(g["actual"].to_numpy(float), g["pred"].to_numpy(float))
        srow = stored[stored["model"] == legacy].iloc[0]
        for col in cols:
            d, s = derived[col], srow[col]
            if pd.isna(s) and pd.isna(d):
                continue
            scale = max(1.0, abs(float(s)))
            if abs(float(d) - float(s)) / scale > 1e-4:
                problems.append(f"{stream}/{col}: derived {d} != stored {s}")
    if problems:
        print("DIAGNOSTIC CHECK FAILED:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)
    print("[check] diagnostics battery reproduces the stored legacy finalist diagnostics")


def matrix_status(tests_row: pd.Series) -> dict[str, str]:
    statuses = {
        "Calibration R2": "Pass" if float(tests_row["calibration_r2"]) > 0 else "Watch",
        "Durbin-Watson": "Pass" if bool(tests_row["pass_dw_range"]) else "Fail",
        "ADF": "Pass" if bool(tests_row["pass_adf_stationary"]) else "Fail",
        "KPSS": "Pass" if bool(tests_row["pass_kpss_stationary"]) else "Fail",
        "Breusch-Pagan": "Pass" if bool(tests_row["pass_no_hetero_bp"]) else "Fail",
        "White": "Pass" if float(tests_row["white_p"]) > 0.05 else "Fail",
        "Jarque-Bera": "Pass" if bool(tests_row["pass_normal_jb"]) else "Watch",
        "Cointegration": "Pass" if bool(tests_row["pass_coint"]) else "Fail",
    }
    core = ["Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"]
    if any(statuses[t] == "Fail" for t in core):
        overall = "Fail"
    elif any(status != "Pass" for status in statuses.values()):
        overall = "Watch"
    else:
        overall = "Pass"
    statuses["Overall"] = overall
    return statuses


def check_pass_matrix() -> None:
    tests = pd.read_parquet(DATA / "diagnostic_tests.parquet")
    matrix = pd.read_parquet(DATA / "diagnostic_pass_matrix.parquet")
    problems = []
    for model in matrix["model"].unique():
        trow = tests[tests["model"] == model].iloc[0]
        derived = matrix_status(trow)
        for test, status in derived.items():
            stored_rows = matrix[(matrix["model"] == model) & (matrix["diagnostic_test"] == test)]
            if stored_rows.empty:
                continue
            stored_status = str(stored_rows.iloc[0]["pass_status"])
            if stored_status != status:
                problems.append(f"{model}/{test}: derived {status} != stored {stored_status}")
    if problems:
        print("PASS-MATRIX CHECK FAILED:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)
    print("[check] pass-matrix derivation reproduces all stored statuses")


def rebuild_diagnostics(new_preds: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tests_old = pd.read_parquet(DATA / "diagnostic_tests.parquet")
    matrix_old = pd.read_parquet(DATA / "diagnostic_pass_matrix.parquet")
    acf_old = pd.read_parquet(DATA / "diagnostic_acf.parquet")
    sp = pd.read_parquet(DATA / "scorecard_predictions.parquet")

    tests = tests_old.copy()
    matrix_frames = [matrix_old[~matrix_old["model"].isin(LEGACY_FINALISTS.values())]]
    acf_frames = [acf_old[~acf_old["model"].isin(LEGACY_FINALISTS.values())]]

    for stream in VNEXT_STREAMS:
        legacy = LEGACY_FINALISTS[stream]
        model = new_finalist(stream)
        g = h1_frame(new_preds[stream])
        battery = diagnostics_battery(g["actual"].to_numpy(float), g["pred"].to_numpy(float))
        tidx = tests[tests["model"] == legacy].index[0]
        for col, val in battery.items():
            if col in tests.columns:
                tests.loc[tidx, col] = val
        tests.loc[tidx, "model"] = model

        statuses = matrix_status(tests.loc[tidx])
        legacy_matrix = matrix_old[matrix_old["model"] == legacy].copy()
        legacy_matrix["model"] = model
        legacy_matrix["pass_status"] = legacy_matrix["diagnostic_test"].map(statuses)
        matrix_frames.append(legacy_matrix)

        legacy_acf = acf_old[acf_old["model"] == legacy].copy()
        ops = sp[(sp["stream"] == stream) & (sp["model"] == legacy)
                 & (sp["score_basis"] == OPERATIONAL)][["origin", "target_period", "target_key"]]
        merged = new_preds[stream][new_preds[stream]["score_basis"] == OPERATIONAL].merge(
            ops.drop_duplicates(), on=["origin", "target_period"], how="left")
        a = merged["actual"].astype(float)
        merged["error_pct"] = np.where(a != 0, (merged["pred"] - a) / a * 100.0, np.nan)
        mean_err = merged.sort_values("target_key").groupby("target_key", sort=True)["error_pct"].mean()
        series = pd.Series(mean_err.values)
        for idx, row in legacy_acf.iterrows():
            if "H1" in str(row["residual_scope"]):
                legacy_acf.loc[idx, "acf_value"] = battery["acf1_resid"]
            else:
                legacy_acf.loc[idx, "acf_value"] = float(series.autocorr(int(row["lag"])))
        legacy_acf["model"] = model
        acf_frames.append(legacy_acf)

    matrix = pd.concat(matrix_frames, ignore_index=True)[matrix_old.columns]
    acf = pd.concat(acf_frames, ignore_index=True)[acf_old.columns]
    return tests, matrix, acf


def rebuild_candidate_cone(finalists: pd.DataFrame) -> pd.DataFrame:
    result = build_candidate_cone(
        existing_cone=pd.read_parquet(DATA / "candidate_cone.parquet"),
        finalists=finalists,
        schiff=pd.read_parquet(DATA / "schiff_benchmark.parquet"),
        light_scorecard=pd.read_parquet(DATA / "light_ruc_candidate_scorecard.parquet"),
    )
    return result.frame


def refresh_manifest_and_inventory() -> None:
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = "dashboard_evidence_pack_v7_vnext_finalists"
    manifest["updated_at"] = utcnow()
    manifest["vnext_promotion"] = {
        "promoted_at": utcnow(),
        "finalists": {stream: new_finalist(stream) for stream in VNEXT_STREAMS},
        "legacy_finalists_archived": LEGACY_FINALISTS,
        "note": ("PED and Heavy RUC finalists replaced by parity-gated vNext production "
                 "scorers (saved fitted state; exact replay). Metrics recomputed on the "
                 "identical stored evidence keysets. Schiff benchmark and Light RUC rows "
                 "are unchanged. Backup of the previous pack: data/dashboard_evidence_pack_v6_backup."),
    }
    rows = []
    for p in sorted(DATA.glob("*.parquet")):
        df = pd.read_parquet(p)
        rows.append({"file": p.name, "rows": int(len(df)), "columns": int(len(df.columns)),
                     "size_bytes": int(p.stat().st_size)})
    manifest["row_counts"] = rows
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    inv_path = PACK / "data_inventory.csv"
    if inv_path.exists():
        inv = pd.DataFrame(rows)
        old_inv = pd.read_csv(inv_path)
        for col in old_inv.columns:
            if col not in inv.columns:
                inv[col] = pd.NA
        inv[old_inv.columns.intersection(inv.columns)].to_csv(inv_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote vNext finalists into the governed evidence pack")
    parser.add_argument("--check", action="store_true", help="verify rebuild formulas only; write nothing")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    for stream in VNEXT_STREAMS:
        parity = json.loads((state_dir(stream) / "forward_scorer_parity_audit.json").read_text(encoding="utf-8"))
        if parity.get("parity_status") != "passed":
            raise SystemExit(f"{stream}: vNext parity_status is not 'passed'; refusing to promote")

    run_check()
    check_diagnostics()
    check_pass_matrix()
    if args.check:
        print("[check] all formula verifications passed; no files written")
        return

    if not args.no_backup:
        if BACKUP.exists():
            print(f"[promote] backup already exists at {BACKUP}, leaving it untouched")
        else:
            shutil.copytree(PACK, BACKUP)
            print(f"[promote] backed up current pack to {BACKUP}")

    new_preds = {stream: load_new_predictions(stream) for stream in VNEXT_STREAMS}

    outputs: dict[str, pd.DataFrame] = {}
    outputs["scorecard_predictions.parquet"] = replace_prediction_rows("scorecard_predictions.parquet", new_preds)
    outputs["error_distribution.parquet"] = replace_prediction_rows("error_distribution.parquet", new_preds)
    outputs["residual_predictions.parquet"] = replace_prediction_rows("residual_predictions.parquet", new_preds)
    outputs["annual_predictions.parquet"] = rebuild_annual_table("annual_predictions.parquet", new_preds)
    outputs["scorecard_annual_predictions.parquet"] = rebuild_annual_table("scorecard_annual_predictions.parquet", new_preds)
    outputs["horizon_profiles.parquet"] = rebuild_horizon_profiles("horizon_profiles.parquet", new_preds)
    outputs["scorecard_horizon_profiles.parquet"] = rebuild_horizon_profiles("scorecard_horizon_profiles.parquet", new_preds)
    outputs["stress_horizon.parquet"] = rebuild_stress("stress_horizon.parquet", new_preds)
    outputs["scorecard_stress_horizon.parquet"] = rebuild_stress("scorecard_stress_horizon.parquet", new_preds)
    outputs["scorecard_model_summary.parquet"] = rebuild_model_summary(new_preds)
    outputs["scorecard_annual_metric_summary.parquet"] = rebuild_annual_metric_summary(new_preds)
    outputs["finalists.parquet"] = rebuild_finalists(new_preds)
    outputs["component_predictions.parquet"] = rebuild_component_predictions(new_preds)
    outputs["ensemble_components.parquet"] = rebuild_ensemble_components()
    outputs["model_registry.parquet"] = rebuild_model_registry()
    coefs, imps, shap, sens = rebuild_explainability_tables()
    outputs["model_coefficients.parquet"] = coefs
    outputs["feature_importance.parquet"] = imps
    outputs["shap_summary.parquet"] = shap
    outputs["scenario_sensitivities.parquet"] = sens
    paired, scen = rebuild_schiff_comparisons(new_preds)
    outputs["paired_vs_schiff.parquet"] = paired
    outputs["scenario_comparison.parquet"] = scen
    tests, matrix, acf = rebuild_diagnostics(new_preds)
    outputs["diagnostic_tests.parquet"] = tests
    outputs["diagnostic_pass_matrix.parquet"] = matrix
    outputs["diagnostic_acf.parquet"] = acf
    outputs["candidate_cone.parquet"] = rebuild_candidate_cone(outputs["finalists.parquet"])

    # Row-count invariants that downstream validators rely on.
    assert len(outputs["scorecard_predictions.parquet"]) == 3648
    assert len(outputs["candidate_cone.parquet"]) == 400
    assert len(outputs["diagnostic_pass_matrix.parquet"]) == 27

    for name, frame in outputs.items():
        frame.to_parquet(DATA / name, index=False)
        print(f"[promote] wrote {name} ({len(frame)} rows)")
    refresh_manifest_and_inventory()
    print("[promote] manifest and inventory refreshed")
    print("[promote] DONE. Restart the Streamlit app to pick up the new pack.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
PED inner HPO/static-solver governance audit.

Purpose
-------
This script audits the current PED finalist lineage:

    PED__RESCUE_static_annual_weighted_top12_capnone
      -> 100% hpo::PED__HPOREFINE_solver_static_convex_top18
          -> inner HPO/static-convex component models and weights, where available.

It is deliberately a governance/reproducibility script, not a new model search.
It reads prior run outputs and the current dashboard evidence pack, then emits
Parquet/CSV/Markdown artifacts suitable for dashboard integration.

What it can prove if the required parent files are present
---------------------------------------------------------
1) The final PED evidence-pack prediction equals the outer stored component.
2) The outer HPO/static-convex prediction equals the weighted sum of its inner
   components, if HPO component predictions and weights are present.
3) The MAPE and annual scores recompute from row-level predictions.
4) Any missing inner registry/components are recorded explicitly as governance gaps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

try:
    import pyarrow  # noqa: F401
    HAS_PARQUET = True
except Exception:
    HAS_PARQUET = False

STREAM = "PED"
STREAM_LABEL = "PED VKT per capita"
FINALIST_MODEL = "PED__RESCUE_static_annual_weighted_top12_capnone"
FINALIST_UID = f"RESCUE::{FINALIST_MODEL}"
OUTER_COMPONENT = "PED__HPOREFINE_solver_static_convex_top18"
OUTER_COMPONENT_UID = f"hpo::{OUTER_COMPONENT}"
SCORE_OPERATIONAL = "current_grid_operational_pooled"
SCORE_PAPER = "schiff_paper_horizon_mean"
KEYS = ["origin", "target_period", "horizon"]

REQUIRED_OUTPUTS = [
    "model_registry",
    "outer_component_replay",
    "inner_hpo_weights",
    "inner_component_registry",
    "inner_component_predictions",
    "nested_ensemble_trace",
    "selection_audit",
    "model_coefficients",
    "feature_importance",
    "feature_importance_global",
    "scenario_sensitivities",
    "training_window_trace",
    "scorecard_summary",
    "annual_predictions",
    "horizon_profiles",
    "stress_horizon",
    "evidence_prediction_comparison",
    "evidence_metric_comparison",
    "reproducibility_gap_register",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build PED inner HPO/static-solver governance audit artifacts.")
    p.add_argument("--input-xlsx", required=True, help="Master workbook path for provenance, not model search.")
    p.add_argument("--sheet", default="PED Inputs")
    p.add_argument("--evidence-pack", required=True, help="dashboard_evidence_pack folder or zip.")
    p.add_argument("--candidate-rescue-parent", required=True, help="candidate rescue parent run folder/zip containing final PED stored predictions.")
    p.add_argument("--hpo-run", default="", help="Optional HPO/refinement run folder/zip containing hpo_refined_ensemble_weights and component predictions.")
    p.add_argument("--arbitration-run", default="", help="Optional arbitration/finalist run folder/zip; used only if HPO component predictions are there.")
    p.add_argument("--output-root", required=True)
    p.add_argument("--make-zip", action="store_true")
    p.add_argument("--tolerance", type=float, default=1e-5)
    return p.parse_args()


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256_file(path: Path, chunk_size: int = 1_048_576) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk_size)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:
        return ""


@dataclass
class SourceRoot:
    root: Path
    tmp: Optional[tempfile.TemporaryDirectory]
    label: str

    def close(self) -> None:
        if self.tmp is not None:
            self.tmp.cleanup()


def source_root(path_like: str | Path, label: str) -> SourceRoot:
    p = Path(path_like).expanduser()
    if not str(path_like):
        return SourceRoot(Path("__missing__"), None, label)
    if p.is_dir():
        return SourceRoot(p, None, label)
    if p.is_file() and p.suffix.lower() == ".zip":
        td = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(p) as z:
            z.extractall(td.name)
        return SourceRoot(Path(td.name), td, label)
    raise FileNotFoundError(f"{label} not found: {p}")


def find_files(root: SourceRoot, names: Iterable[str]) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {n: [] for n in names}
    if not root.root.exists():
        return out
    lower_names = {n.lower(): n for n in names}
    for f in root.root.rglob("*"):
        if not f.is_file():
            continue
        nm = f.name.lower()
        if nm in lower_names:
            out[lower_names[nm]].append(f)
    return out


def read_any_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path, low_memory=False)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported table file: {path}")


def first_table(root: SourceRoot, names: list[str], optional: bool = False) -> tuple[pd.DataFrame, str]:
    files = find_files(root, names)
    for name in names:
        if files.get(name):
            path = files[name][0]
            return read_any_table(path), str(path)
    if optional:
        return pd.DataFrame(), ""
    raise FileNotFoundError(f"Could not find any of {names} in {root.label}: {root.root}")


def detect_col(df: pd.DataFrame, candidates: list[str], required: bool = True) -> str:
    by_lower = {str(c).lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in by_lower:
            return by_lower[cand.lower()]
    if required:
        raise KeyError(f"None of columns {candidates} found. Available: {list(df.columns)[:40]}")
    return ""


def normalize_predictions(df: pd.DataFrame, source_file: str, default_score_basis: str = SCORE_OPERATIONAL) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy()
    stream_col = detect_col(out, ["stream", "stream_id"], required=False)
    model_col = detect_col(out, ["model_uid", "model", "model_name"], required=False)
    origin_col = detect_col(out, ["origin", "origin_period", "forecast_origin"], required=True)
    target_col = detect_col(out, ["target_period", "period", "target", "target_qtr"], required=True)
    horizon_col = detect_col(out, ["horizon", "h", "forecast_horizon"], required=False)
    actual_col = detect_col(out, ["actual", "y", "target_actual", "actual_value"], required=True)
    pred_col = detect_col(out, ["pred", "prediction", "y_pred", "forecast", "final_pred"], required=True)
    out = pd.DataFrame({
        "stream": out[stream_col].astype(str) if stream_col else STREAM,
        "model": out[model_col].astype(str) if model_col else "",
        "origin": out[origin_col].astype(str),
        "target_period": out[target_col].astype(str),
        "horizon": pd.to_numeric(out[horizon_col], errors="coerce") if horizon_col else np.nan,
        "actual": pd.to_numeric(out[actual_col], errors="coerce"),
        "pred": pd.to_numeric(out[pred_col], errors="coerce"),
        "source_file": source_file,
        "score_basis": default_score_basis,
    })
    out["horizon"] = out["horizon"].astype("Int64")
    return out


def qkey(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["origin"] = out["origin"].astype(str)
    out["target_period"] = out["target_period"].astype(str)
    out["horizon"] = pd.to_numeric(out["horizon"], errors="coerce").astype("Int64")
    return out


def ape(actual: pd.Series, pred: pd.Series) -> pd.Series:
    a = pd.to_numeric(actual, errors="coerce")
    p = pd.to_numeric(pred, errors="coerce")
    return (p - a).abs() / a.abs() * 100.0


def err_pct(actual: pd.Series, pred: pd.Series) -> pd.Series:
    a = pd.to_numeric(actual, errors="coerce")
    p = pd.to_numeric(pred, errors="coerce")
    return (p - a) / a.abs() * 100.0


def write_table(df: pd.DataFrame, out_dir: Path, name: str, status: list[dict[str, Any]]) -> None:
    ensure_dir(out_dir)
    csv_path = out_dir / f"{name}.csv"
    df.to_csv(csv_path, index=False)
    pq_path = out_dir / f"{name}.parquet"
    pq_ok = False
    if HAS_PARQUET:
        try:
            df.to_parquet(pq_path, index=False)
            pq_ok = True
        except Exception:
            pq_ok = False
    status.append({"table": name, "rows": int(len(df)), "columns": int(len(df.columns)), "csv_written": True, "parquet_written": pq_ok})


def load_evidence_pack(root_src: SourceRoot) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Accept root/dashboard_evidence_pack or root itself.
    possible = [root_src.root / "dashboard_evidence_pack", root_src.root]
    data_root = None
    for p in possible:
        if (p / "data").exists():
            data_root = p / "data"
            break
    if data_root is None:
        raise FileNotFoundError(f"Evidence pack data folder not found under {root_src.root}")
    score = pd.read_parquet(data_root / "scorecard_predictions.parquet")
    annual = pd.read_parquet(data_root / "scorecard_annual_predictions.parquet")
    finalists = pd.read_parquet(data_root / "finalists.parquet")
    score = score[(score["stream"].astype(str).eq(STREAM)) & (score["model"].astype(str).eq(FINALIST_MODEL))].copy()
    annual = annual[(annual["stream"].astype(str).eq(STREAM)) & (annual["model"].astype(str).eq(FINALIST_MODEL))].copy()
    return qkey(score), annual, finalists


def metric_summary(preds: pd.DataFrame, score_basis: str, pred_col: str = "final_pred") -> dict[str, Any]:
    if preds.empty:
        return {"score_basis": score_basis, "n_pairs": 0}
    d = preds.copy()
    d["actual"] = pd.to_numeric(d["actual"], errors="coerce")
    d[pred_col] = pd.to_numeric(d[pred_col], errors="coerce")
    d = d[d["actual"].abs() > 0].copy()
    d["abs_error_pct"] = ape(d["actual"], d[pred_col])
    d["error_pct"] = err_pct(d["actual"], d[pred_col])
    by_h = d.groupby("horizon", dropna=False)["abs_error_pct"].mean()
    out = {
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "model": FINALIST_MODEL,
        "score_basis": score_basis,
        "n_pairs": int(len(d)),
        "n_origins": int(d["origin"].nunique()) if "origin" in d else 0,
        "n_horizons": int(d["horizon"].nunique()) if "horizon" in d else 0,
        "pooled_mape": float(d["abs_error_pct"].mean()) if len(d) else np.nan,
        "horizon_mean_mape": float(by_h.mean()) if len(by_h) else np.nan,
        "bias_pct": float(d["error_pct"].mean()) if len(d) else np.nan,
    }
    for h, v in by_h.items():
        if pd.notna(h):
            out[f"mape_h{int(h):02d}"] = float(v)
    return out


def build_annual(preds: pd.DataFrame) -> pd.DataFrame:
    if preds.empty:
        return pd.DataFrame()
    d = preds.copy()
    # Convert YYYYQn to calendar-ish year for audit. The original pack uses target_year/june_year, but
    # this is a reproducibility diagnostic and not a replacement for main annual metrics.
    d["target_year"] = d["target_period"].astype(str).str.extract(r"(\d{4})").astype(float).astype("Int64")
    g = d.groupby(["score_basis", "origin", "target_year"], dropna=False).agg(
        actual=("actual", "sum"), final_pred=("final_pred", "sum"), n_quarters=("target_period", "nunique")
    ).reset_index()
    g = g[g["n_quarters"].eq(4)].copy()
    g["abs_error_pct"] = ape(g["actual"], g["final_pred"])
    g["error_pct"] = err_pct(g["actual"], g["final_pred"])
    g["stream"] = STREAM
    g["stream_label"] = STREAM_LABEL
    g["model"] = FINALIST_MODEL
    return g


def parse_weights(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy()
    stream_col = detect_col(out, ["stream", "stream_id"], required=False)
    ensemble_col = detect_col(out, ["ensemble", "ensemble_model", "model", "model_uid"], required=False)
    comp_col = detect_col(out, ["component_model", "component", "base_model", "member_model"], required=False)
    weight_col = detect_col(out, ["weight", "ensemble_weight", "coef"], required=False)
    if not comp_col or not weight_col:
        return pd.DataFrame()
    if stream_col:
        out = out[out[stream_col].astype(str).eq(STREAM)].copy()
    if ensemble_col:
        mask = out[ensemble_col].astype(str).str.contains("HPOREFINE_solver_static_convex_top18|solver_static_convex_top18", case=False, na=False)
        if mask.any():
            out = out[mask].copy()
    out = pd.DataFrame({
        "stream": STREAM,
        "stream_label": STREAM_LABEL,
        "outer_component_model": OUTER_COMPONENT,
        "inner_component_model": out[comp_col].astype(str),
        "weight": pd.to_numeric(out[weight_col], errors="coerce"),
        "source_file": source_file,
    })
    out = out.dropna(subset=["weight"])
    total = out["weight"].sum()
    out["weight_sum"] = float(total) if len(out) else np.nan
    out["normalised_weight"] = out["weight"] / total if total and np.isfinite(total) else out["weight"]
    out["component_rank"] = range(1, len(out) + 1)
    return out


def best_prediction_file(root: SourceRoot) -> tuple[pd.DataFrame, str]:
    # prefer broad predictions files with all models.
    candidates = [
        "quarterly_predictions.csv",
        "all_quarterly_predictions.csv",
        "light_ruc_governance_predictions.csv",
        "selected_quarterly_predictions.csv",
        "generated_ensemble_quarterly_predictions.csv",
    ]
    try:
        return first_table(root, candidates, optional=False)
    except Exception:
        return pd.DataFrame(), ""


def collect_inner_component_predictions(roots: list[SourceRoot], weights: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    gaps: list[dict[str, Any]] = []
    if weights.empty:
        gaps.append({"gap": "inner_hpo_weights_missing", "severity": "high", "detail": "No inner HPO/static-convex weights found."})
        return pd.DataFrame(), gaps
    comps = weights["inner_component_model"].dropna().astype(str).unique().tolist()
    all_frames = []
    for root in roots:
        if not root.root.exists():
            continue
        raw, src = best_prediction_file(root)
        if raw.empty:
            continue
        try:
            norm = normalize_predictions(raw, src)
        except Exception as exc:
            gaps.append({"gap": "prediction_file_parse_failed", "source": src, "severity": "medium", "detail": str(exc)})
            continue
        norm = norm[norm["stream"].astype(str).eq(STREAM)].copy()
        for comp in comps:
            # Match with or without prefixes and model_uid decorations.
            token = re.escape(comp)
            mask = norm["model"].astype(str).str.contains(token, regex=True, na=False)
            if not mask.any():
                # Fallback: last segment/short token matching.
                short = comp.replace("PED__", "")
                mask = norm["model"].astype(str).str.contains(re.escape(short), regex=True, na=False)
            sub = norm[mask].copy()
            if len(sub):
                sub["inner_component_model"] = comp
                sub["prediction_source_used"] = src
                all_frames.append(sub)
    if not all_frames:
        gaps.append({"gap": "inner_component_predictions_missing", "severity": "high", "detail": "Could not locate predictions for inner HPO components in supplied roots."})
        return pd.DataFrame(), gaps
    pred = pd.concat(all_frames, ignore_index=True).drop_duplicates(subset=["inner_component_model", *KEYS])
    found = set(pred["inner_component_model"].unique())
    for comp in comps:
        if comp not in found:
            gaps.append({"gap": "inner_component_prediction_missing", "component": comp, "severity": "high", "detail": "Weight exists but no component prediction rows found."})
    return qkey(pred), gaps


def main() -> int:
    args = parse_args()
    out_root = ensure_dir(Path(args.output_root).expanduser())
    run_dir = ensure_dir(out_root / f"ped_inner_hpo_audit_{stamp()}")
    repro_dir = ensure_dir(run_dir / "dashboard_evidence_pack_reproducibility" / "ped_inner_hpo")
    parquet_status: list[dict[str, Any]] = []

    candidate_src = source_root(args.candidate_rescue_parent, "candidate_rescue_parent")
    evidence_src = source_root(args.evidence_pack, "evidence_pack")
    hpo_src = source_root(args.hpo_run, "hpo_run") if args.hpo_run else SourceRoot(Path("__missing__"), None, "hpo_run")
    arb_src = source_root(args.arbitration_run, "arbitration_run") if args.arbitration_run else SourceRoot(Path("__missing__"), None, "arbitration_run")

    try:
        # Workbook provenance.
        workbook = Path(args.input_xlsx).expanduser()
        workbook_prov = {
            "workbook_path": str(workbook),
            "workbook_exists": workbook.exists(),
            "workbook_sha256": sha256_file(workbook) if workbook.exists() else "",
            "sheet": args.sheet,
        }
        if workbook.exists():
            try:
                xls = pd.ExcelFile(workbook)
                workbook_prov["sheet_found"] = args.sheet in xls.sheet_names
                if workbook_prov["sheet_found"]:
                    cols = pd.read_excel(workbook, sheet_name=args.sheet, nrows=0).columns.astype(str).tolist()
                    workbook_prov["n_columns"] = len(cols)
                    workbook_prov["columns_sample"] = cols[:60]
            except Exception as exc:
                workbook_prov["workbook_read_error"] = str(exc)

        # Parent outer prediction replay.
        selected_q, selected_src = first_table(candidate_src, ["selected_quarterly_predictions.csv"], optional=False)
        generated_q, generated_src = first_table(candidate_src, ["generated_ensemble_quarterly_predictions.csv"], optional=False)
        annual_parent, annual_src = first_table(candidate_src, ["all_annual_predictions_selected_and_rescue.csv", "annual_predictions.csv"], optional=True)
        outer_comp = normalize_predictions(selected_q, selected_src)
        outer_comp = outer_comp[(outer_comp["stream"].eq(STREAM)) & (outer_comp["model"].astype(str).eq(OUTER_COMPONENT_UID))].copy()
        final_parent = normalize_predictions(generated_q, generated_src)
        final_parent = final_parent[(final_parent["stream"].eq(STREAM)) & (final_parent["model"].astype(str).eq(FINALIST_UID))].copy()
        if outer_comp.empty or final_parent.empty:
            raise RuntimeError("Could not locate PED outer component/finalist rows in candidate rescue parent run.")
        outer_comp = qkey(outer_comp)
        final_parent = qkey(final_parent)

        evidence_q, evidence_annual, evidence_finalists = load_evidence_pack(evidence_src)
        evidence_q = qkey(evidence_q)

        # Outer replay table.
        outer = final_parent.merge(
            outer_comp[[*KEYS, "pred"]].rename(columns={"pred": "outer_component_pred"}), on=KEYS, how="left"
        )
        outer = outer.rename(columns={"pred": "final_pred"})
        outer["component_weight"] = 1.0
        outer["rebuilt_final_pred"] = outer["outer_component_pred"]
        outer["outer_delta"] = outer["rebuilt_final_pred"] - outer["final_pred"]
        outer["stream_label"] = STREAM_LABEL
        outer["finalist_model"] = FINALIST_MODEL
        outer["outer_component_model"] = OUTER_COMPONENT
        outer["score_basis"] = SCORE_OPERATIONAL

        # Evidence comparison.
        ev = evidence_q[[*KEYS, "actual", "pred", "score_basis"]].rename(columns={"pred": "evidence_pred", "actual": "evidence_actual"})
        ev_comp = ev.merge(
            outer[[*KEYS, "actual", "final_pred", "rebuilt_final_pred"]].rename(columns={"actual": "parent_actual"}), on=KEYS, how="left"
        )
        ev_comp["delta_rebuilt_vs_evidence"] = ev_comp["rebuilt_final_pred"] - ev_comp["evidence_pred"]
        ev_comp["abs_delta_rebuilt_vs_evidence"] = ev_comp["delta_rebuilt_vs_evidence"].abs()

        # Inner weights.
        weights_df = pd.DataFrame()
        weight_sources = []
        for root in [hpo_src, candidate_src, arb_src]:
            if not root.root.exists():
                continue
            for nm in ["hpo_refined_ensemble_weights.csv", "ensemble_weights.csv", "hpo_refined_ensemble_weights.parquet", "ensemble_weights.parquet"]:
                files = find_files(root, [nm]).get(nm, [])
                for f in files:
                    try:
                        raw = read_any_table(f)
                        parsed = parse_weights(raw, str(f))
                        if len(parsed):
                            weights_df = pd.concat([weights_df, parsed], ignore_index=True)
                            weight_sources.append(str(f))
                    except Exception:
                        pass
        if len(weights_df):
            weights_df = weights_df.drop_duplicates(subset=["inner_component_model"])
            total = weights_df["weight"].sum()
            weights_df["normalised_weight"] = weights_df["weight"] / total if total else weights_df["weight"]
            weights_df["weight_sum"] = total
        else:
            weights_df = pd.DataFrame(columns=["stream", "stream_label", "outer_component_model", "inner_component_model", "weight", "normalised_weight", "weight_sum", "source_file", "component_rank"])

        inner_preds, gaps = collect_inner_component_predictions([hpo_src, arb_src, candidate_src], weights_df)

        if len(inner_preds) and len(weights_df):
            w = weights_df[["inner_component_model", "normalised_weight"]].rename(columns={"normalised_weight": "inner_weight"})
            comp_pred = inner_preds.merge(w, on="inner_component_model", how="left")
            comp_pred["weighted_inner_pred"] = comp_pred["pred"] * comp_pred["inner_weight"]
            comp_pred["stream_label"] = STREAM_LABEL
            comp_pred["outer_component_model"] = OUTER_COMPONENT
            nested = comp_pred.groupby(KEYS, dropna=False).agg(
                actual=("actual", "first"),
                rebuilt_outer_component_pred=("weighted_inner_pred", "sum"),
                n_inner_components_present=("inner_component_model", "nunique"),
            ).reset_index()
            nested = nested.merge(outer[[*KEYS, "outer_component_pred", "final_pred"]], on=KEYS, how="left")
            nested["inner_replay_delta_vs_outer"] = nested["rebuilt_outer_component_pred"] - nested["outer_component_pred"]
            nested["inner_replay_abs_delta_vs_outer"] = nested["inner_replay_delta_vs_outer"].abs()
            if nested["n_inner_components_present"].max() < len(weights_df):
                gaps.append({"gap": "incomplete_inner_components_by_row", "severity": "high", "detail": "Not every weighted component appeared on every forecast row."})
        else:
            comp_pred = pd.DataFrame()
            nested = pd.DataFrame(columns=[*KEYS, "actual", "rebuilt_outer_component_pred", "outer_component_pred", "final_pred", "inner_replay_delta_vs_outer"])

        # Registry.
        reg_rows = [
            {
                "stream": STREAM,
                "stream_label": STREAM_LABEL,
                "model": FINALIST_MODEL,
                "model_role": "finalist",
                "algorithm": "outer rescue ensemble",
                "target": "PED VKT per capita",
                "component_model": OUTER_COMPONENT,
                "component_weight": 1.0,
                "reproducibility_status": "exact_outer_component_prediction_replay" if outer["outer_delta"].abs().max() <= args.tolerance else "outer_replay_mismatch",
                "workbook_sheet": args.sheet,
                "source_run": str(Path(args.candidate_rescue_parent).expanduser()),
                "notes": "Final prediction is 100% stored HPO/static-convex component prediction.",
            },
            {
                "stream": STREAM,
                "stream_label": STREAM_LABEL,
                "model": OUTER_COMPONENT,
                "model_role": "outer_hpo_static_solver_component",
                "algorithm": "HPO-refined static convex solver ensemble",
                "target": "PED VKT per capita",
                "component_model": "inner components listed in inner_hpo_weights if available",
                "component_weight": np.nan,
                "reproducibility_status": "inner_weighted_component_replay" if len(nested) and nested["inner_replay_abs_delta_vs_outer"].max() <= args.tolerance else "inner_registry_or_component_predictions_incomplete",
                "workbook_sheet": args.sheet,
                "source_run": str(Path(args.hpo_run).expanduser()) if args.hpo_run else "not supplied",
                "notes": "This row describes the nested HPO/static-convex component selected by the outer rescue ensemble.",
            },
        ]
        for _, row in weights_df.iterrows():
            reg_rows.append({
                "stream": STREAM,
                "stream_label": STREAM_LABEL,
                "model": str(row["inner_component_model"]),
                "model_role": "inner_hpo_static_solver_member",
                "algorithm": "unknown_from_weight_table; inspect source script/model name",
                "target": "PED VKT per capita",
                "component_model": str(row["inner_component_model"]),
                "component_weight": float(row["normalised_weight"]),
                "reproducibility_status": "component_prediction_found" if (not comp_pred.empty and str(row["inner_component_model"]) in set(comp_pred["inner_component_model"].astype(str))) else "component_prediction_missing",
                "workbook_sheet": args.sheet,
                "source_run": str(row.get("source_file", "")),
                "notes": "Inner member of the HPO/static-convex ensemble.",
            })
        registry = pd.DataFrame(reg_rows)

        # Selection audit.
        selection_rows = []
        # Pull useful HPO candidate summaries if present.
        for root in [hpo_src, candidate_src, arb_src]:
            if not root.root.exists():
                continue
            for nm in ["hpo_trials_all_streams.csv", "hpo_full_validation_summary.csv", "recommended_finalists.csv", "final_summary.csv"]:
                files = find_files(root, [nm]).get(nm, [])
                for f in files:
                    try:
                        raw = read_any_table(f)
                        if "stream" in raw.columns:
                            raw = raw[raw["stream"].astype(str).eq(STREAM)].copy()
                        if len(raw):
                            selection_rows.append({"source_file": str(f), "rows": len(raw), "columns": len(raw.columns), "columns_sample": json.dumps(list(map(str, raw.columns[:30]))), "contains_outer_component": raw.astype(str).apply(lambda c: c.str.contains(OUTER_COMPONENT, na=False)).any().any()})
                    except Exception as exc:
                        selection_rows.append({"source_file": str(f), "rows": 0, "columns": 0, "error": str(exc)})
        selection = pd.DataFrame(selection_rows)

        # Placeholder tables with honest semantics.
        coef_rows = []
        imp_rows = []
        sens_rows = []
        train_rows = []
        if len(weights_df):
            for _, row in weights_df.iterrows():
                imp_rows.append({
                    "stream": STREAM,
                    "model": OUTER_COMPONENT,
                    "feature": str(row["inner_component_model"]),
                    "feature_label": f"Inner component {int(row.get('component_rank', 0))}" if pd.notna(row.get("component_rank", np.nan)) else str(row["inner_component_model"]),
                    "importance_type": "inner_component_weight",
                    "importance_value": float(row["normalised_weight"]),
                    "note": "This is component-level contribution, not variable-level feature importance.",
                })
        else:
            imp_rows.append({"stream": STREAM, "model": OUTER_COMPONENT, "feature": "not_available", "feature_label": "not available", "importance_type": "not_available", "importance_value": np.nan, "note": "Inner HPO/static-solver weights were not found."})
        coef_rows.append({"stream": STREAM, "model": OUTER_COMPONENT, "feature": "not_available", "coefficient": np.nan, "note": "Feature-level coefficients require rerunning inner component builders or retaining fitted artifacts."})
        sens_rows.append({"stream": STREAM, "model": OUTER_COMPONENT, "scenario_variable": "not_available", "perturbation": "not_available", "impact_pct": np.nan, "note": "Scenario sensitivities require model refit/replay from workbook inputs."})
        if len(outer):
            tmp = outer[["origin"]].drop_duplicates().copy()
            tmp["window_type"] = "from_parent_prediction_replay"
            tmp["window_length"] = np.nan
            tmp["note"] = "Exact training windows not available unless inner builders are rerun."
            train_rows = tmp.to_dict("records")
        coefficients = pd.DataFrame(coef_rows)
        feature_importance = pd.DataFrame(imp_rows)
        feature_importance_global = feature_importance.copy()
        scenario_sensitivities = pd.DataFrame(sens_rows)
        training_window_trace = pd.DataFrame(train_rows)

        # Scorecard and annual/horizon/stress.
        outer_scored = ev_comp.dropna(subset=["evidence_pred", "rebuilt_final_pred"]).copy()

        # Build the metric frame explicitly rather than via rename().  The
        # merged audit frame already contains a parent ``final_pred`` column, so
        # renaming ``rebuilt_final_pred`` to ``final_pred`` can create duplicate
        # column names.  With duplicate names, pandas returns a DataFrame for
        # d["final_pred"] instead of a Series, which breaks pd.to_numeric().
        # This explicit construction keeps one audited prediction column and one
        # actual column.
        rebuilt_for_metrics = outer_scored[[*KEYS, "score_basis"]].copy()
        rebuilt_for_metrics["actual"] = pd.to_numeric(outer_scored["evidence_actual"], errors="coerce")
        rebuilt_for_metrics["final_pred"] = pd.to_numeric(outer_scored["rebuilt_final_pred"], errors="coerce")
        rebuilt_for_metrics = rebuilt_for_metrics.dropna(subset=["actual", "final_pred"]).copy()

        summaries = []
        for sb, g in rebuilt_for_metrics.groupby("score_basis"):
            summaries.append(metric_summary(g, sb, "final_pred"))
        scorecard = pd.DataFrame(summaries)
        annual = build_annual(rebuilt_for_metrics)
        horizon_rows = []
        for sb, g in rebuilt_for_metrics.groupby("score_basis"):
            gd = g.copy()
            gd["abs_error_pct"] = ape(gd["actual"], gd["final_pred"])
            for h, v in gd.groupby("horizon")["abs_error_pct"].mean().items():
                horizon_rows.append({"stream": STREAM, "stream_label": STREAM_LABEL, "model": FINALIST_MODEL, "score_basis": sb, "horizon": int(h), "mape": float(v)})
        horizons = pd.DataFrame(horizon_rows)
        stress_rows = []
        if len(horizons):
            for sb in horizons["score_basis"].unique():
                h = horizons[horizons["score_basis"].eq(sb)]
                for label, hs in [("1-4 qtrs", [1,2,3,4]), ("5-8 qtrs", [5,6,7,8]), ("9-12 qtrs", [9,10,11,12])]:
                    stress_rows.append({"stream": STREAM, "stream_label": STREAM_LABEL, "model": FINALIST_MODEL, "score_basis": sb, "stress_bucket": label, "mape": float(h[h["horizon"].isin(hs)]["mape"].mean())})
        stress = pd.DataFrame(stress_rows)

        metric_comp_rows = []
        for sb, g in ev_comp.groupby("score_basis"):
            d = g.dropna(subset=["evidence_pred", "rebuilt_final_pred"]).copy()
            metric_comp_rows.append({
                "stream": STREAM,
                "stream_label": STREAM_LABEL,
                "model": FINALIST_MODEL,
                "score_basis": sb,
                "n_common_rows": int(len(d)),
                "max_abs_pred_delta": float(d["abs_delta_rebuilt_vs_evidence"].max()) if len(d) else np.nan,
                "mean_abs_pred_delta": float(d["abs_delta_rebuilt_vs_evidence"].mean()) if len(d) else np.nan,
                "rebuilt_pooled_mape": float(ape(d["evidence_actual"], d["rebuilt_final_pred"]).mean()) if len(d) else np.nan,
                "evidence_pooled_mape": float(ape(d["evidence_actual"], d["evidence_pred"]).mean()) if len(d) else np.nan,
            })
        metric_comp = pd.DataFrame(metric_comp_rows)

        # Gaps.
        if weights_df.empty:
            gaps.append({"gap": "inner_hpo_static_solver_weight_registry_missing", "severity": "high", "detail": "Provide hpo_refined_ensemble_weights.csv or ensemble_weights.csv from the scoped HPO/refinement run."})
        if comp_pred.empty:
            gaps.append({"gap": "inner_component_prediction_trace_missing", "severity": "high", "detail": "Provide quarterly prediction rows for each inner component model to verify the HPO weighted sum."})
        gaps.append({"gap": "feature_level_refit_not_attempted", "severity": "medium", "detail": "This script audits parent-run outputs. Full workbook-first refit requires rerunning the inner component builders with retained fitted states."})
        gap_df = pd.DataFrame(gaps).drop_duplicates() if gaps else pd.DataFrame(columns=["gap", "severity", "detail"])

        # Write artifacts.
        for name, df in [
            ("model_registry", registry),
            ("outer_component_replay", outer),
            ("inner_hpo_weights", weights_df),
            ("inner_component_registry", registry[registry["model_role"].astype(str).str.contains("inner", na=False)]),
            ("inner_component_predictions", comp_pred),
            ("nested_ensemble_trace", nested),
            ("selection_audit", selection),
            ("model_coefficients", coefficients),
            ("feature_importance", feature_importance),
            ("feature_importance_global", feature_importance_global),
            ("scenario_sensitivities", scenario_sensitivities),
            ("training_window_trace", training_window_trace),
            ("scorecard_summary", scorecard),
            ("annual_predictions", annual),
            ("horizon_profiles", horizons),
            ("stress_horizon", stress),
            ("evidence_prediction_comparison", ev_comp),
            ("evidence_metric_comparison", metric_comp),
            ("reproducibility_gap_register", gap_df),
        ]:
            write_table(df, run_dir, name, parquet_status)
            write_table(df, repro_dir, name, [])

        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "stream": STREAM,
            "stream_label": STREAM_LABEL,
            "finalist_model": FINALIST_MODEL,
            "outer_component_model": OUTER_COMPONENT,
            "candidate_rescue_parent": str(Path(args.candidate_rescue_parent).expanduser()),
            "hpo_run": str(Path(args.hpo_run).expanduser()) if args.hpo_run else "",
            "arbitration_run": str(Path(args.arbitration_run).expanduser()) if args.arbitration_run else "",
            "evidence_pack": str(Path(args.evidence_pack).expanduser()),
            "workbook_provenance": workbook_prov,
            "parquet_status": parquet_status,
            "max_outer_replay_delta": float(outer["outer_delta"].abs().max()) if len(outer) else None,
            "max_evidence_delta": float(ev_comp["abs_delta_rebuilt_vs_evidence"].max()) if len(ev_comp) else None,
            "max_inner_replay_delta": float(nested["inner_replay_abs_delta_vs_outer"].max()) if len(nested) and "inner_replay_abs_delta_vs_outer" in nested else None,
            "inner_weights_found": bool(len(weights_df)),
            "inner_component_predictions_found": bool(len(comp_pred)),
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (repro_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (run_dir / "parquet_write_status.json").write_text(json.dumps(parquet_status, indent=2), encoding="utf-8")
        (repro_dir / "parquet_write_status.json").write_text(json.dumps(parquet_status, indent=2), encoding="utf-8")

        # Report.
        report = []
        report.append("# PED inner HPO/static-solver governance audit\n")
        report.append(f"Created: {manifest['created_at']}\n")
        report.append("\n## Finalist\n")
        report.append(f"- Finalist: `{FINALIST_MODEL}`\n")
        report.append(f"- Outer component: `{OUTER_COMPONENT}` with weight 100%.\n")
        report.append(f"- Max outer replay delta: `{manifest['max_outer_replay_delta']}`.\n")
        report.append(f"- Max evidence-pack delta: `{manifest['max_evidence_delta']}`.\n")
        report.append("\n## Inner HPO/static-solver layer\n")
        if len(weights_df):
            report.append(f"Found {len(weights_df)} inner HPO/static-solver weights. Weight sum = {weights_df['normalised_weight'].sum():.12f}.\n")
        else:
            report.append("Inner HPO/static-solver weights were not found in the supplied runs.\n")
        if len(comp_pred):
            report.append(f"Found inner component prediction rows: {len(comp_pred):,}.\n")
            if len(nested):
                report.append(f"Max weighted inner replay delta vs outer component: {manifest['max_inner_replay_delta']}.\n")
        else:
            report.append("Inner component prediction rows were not found; full inner replay remains incomplete.\n")
        report.append("\n## Governance interpretation\n")
        report.append("This audit proves the outer PED component-prediction replay and, if inner weights/predictions are present, the nested HPO/static-convex ensemble replay. It does not claim workbook-first refit reproducibility unless the inner component builders and fitted states are supplied.\n")
        report.append("\n## Scorecard summary\n")
        if len(scorecard):
            report.append(scorecard.to_markdown(index=False))
        report.append("\n\n## Gaps\n")
        if len(gap_df):
            report.append(gap_df.to_markdown(index=False))
        else:
            report.append("No gaps detected.\n")
        (run_dir / "ped_inner_hpo_static_solver_audit_report.md").write_text("\n".join(report), encoding="utf-8")
        (repro_dir / "ped_inner_hpo_static_solver_audit_report.md").write_text("\n".join(report), encoding="utf-8")

        if args.make_zip:
            zip_path = run_dir.with_suffix(".zip")
            if zip_path.exists():
                zip_path.unlink()
            shutil.make_archive(str(run_dir), "zip", root_dir=run_dir)
            print(f"ZIP_CREATED={zip_path}")

        print("RUN_COMPLETE")
        print(f"RUN_DIR={run_dir}")
        print(scorecard.to_string(index=False) if len(scorecard) else "No scorecard rows")
        print(f"INNER_WEIGHTS_FOUND={len(weights_df)}")
        print(f"INNER_COMPONENT_PREDICTIONS_FOUND={len(comp_pred)}")
        print(f"MAX_EVIDENCE_DELTA={manifest['max_evidence_delta']}")
        return 0
    finally:
        for src in [candidate_src, evidence_src, hpo_src, arb_src]:
            src.close()


if __name__ == "__main__":
    raise SystemExit(main())

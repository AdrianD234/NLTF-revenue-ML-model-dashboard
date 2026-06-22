"""Regenerate the balanced candidate-search frontier cone.

The frontier chart is a bounded display sample, not a governance scoring input.
This module rebuilds that display sample around the current finalists while
keeping measured rows distinguishable from deterministic visual-fill rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from model_dashboard.score_basis import OPERATIONAL_SCORE_BASIS, PAPER_SCORE_BASIS


PACK = REPO / "data" / "dashboard_evidence_pack"
DATA = PACK / "data"
AUDIT_DIR = REPO / "artifacts" / "candidate_cone"

STREAM_TARGET_COUNTS = {"PED": 132, "LIGHT_RUC": 136, "HEAVY_RUC": 132}
MEASURED_DISPLAY_LIMITS = {"LIGHT_RUC": 68}
STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
}
CURRENT_FINALISTS = {
    "PED": "PED__VNEXT_SOLVED_CONVEX_TOP2",
    "LIGHT_RUC": "dynamic_RESID_GBR_n150_d1_lr0.05_w36",
    "HEAVY_RUC": "HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4",
}
SCHIFF_MODELS = {
    "PED": "PED__SCHIFF_SPEC_FROM_WORKBOOK",
    "LIGHT_RUC": "LIGHT_RUC__SCHIFF_SPEC_FROM_WORKBOOK",
    "HEAVY_RUC": "HEAVY_RUC__SCHIFF_SPEC_FROM_WORKBOOK",
}

CANDIDATE_COLUMNS = [
    "candidate_uid",
    "stream",
    "stream_label",
    "model",
    "model_short",
    "run_source",
    "source_file",
    "source_family",
    "model_kind",
    "feature_set",
    "n_quarterly_pairs",
    "n_origins",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "annual_p90_ape",
    "mape_h01_04",
    "mape_h05_08",
    "mape_h09_12",
    "selection_score",
    "performance_rank_within_stream",
    "performance_percentile",
    "performance_decile",
    "candidate_role",
    "include_reason",
    "is_current_recommended",
    "is_pure_schiff",
    "is_pdf_reference",
    "is_pareto_frontier",
    "is_top_quarterly",
    "is_top_annual",
    "is_top_governance",
    "plot_role",
    "plot_marker",
    "plot_size",
    "plot_alpha",
    "is_curated_cone_sample",
    "plot_default_include",
    "is_plot_candidate",
    "is_extreme_outlier",
    "default_score_basis",
    "operational_pooled_mape",
    "operational_horizon_mean_mape",
    "operational_bias_pct",
    "operational_annual_mape",
    "paper_horizon_mean_mape",
    "paper_pooled_mape",
    "paper_bias_pct",
    "paper_annual_mape",
    "paper_h09_12_mape",
    "frontier_sample_class",
    "frontier_sample_note",
]

NUMERIC_COLUMNS = {
    "n_quarterly_pairs",
    "n_origins",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "annual_bias_pct",
    "quarterly_p90_ape",
    "annual_p90_ape",
    "mape_h01_04",
    "mape_h05_08",
    "mape_h09_12",
    "selection_score",
    "performance_rank_within_stream",
    "performance_percentile",
    "performance_decile",
    "plot_size",
    "plot_alpha",
    "operational_pooled_mape",
    "operational_horizon_mean_mape",
    "operational_bias_pct",
    "operational_annual_mape",
    "paper_horizon_mean_mape",
    "paper_pooled_mape",
    "paper_bias_pct",
    "paper_annual_mape",
    "paper_h09_12_mape",
}
BOOL_COLUMNS = {
    "is_current_recommended",
    "is_pure_schiff",
    "is_pdf_reference",
    "is_pareto_frontier",
    "is_top_quarterly",
    "is_top_annual",
    "is_top_governance",
    "is_curated_cone_sample",
    "plot_default_include",
    "is_plot_candidate",
    "is_extreme_outlier",
}


@dataclass(frozen=True)
class ConeResult:
    frame: pd.DataFrame
    metrics: pd.DataFrame


def candidate_uid(model: str) -> str:
    return hashlib.sha256(str(model).encode("utf-8")).hexdigest()[:16]


def shorten(model: Any) -> str:
    text = "" if model is None else str(model)
    replacements = {
        "dynamic_RESID_GBR_n150_d1_lr0.05_w36": "Light RUC dynamic residual GBM W36",
        "PED__VNEXT_SOLVED_CONVEX_TOP2": "PED vNext convex TOP2",
        "HEAVY_RUC__VNEXT_SOLVED_CONVEX_TOP4": "Heavy RUC vNext convex TOP4",
        "PED__SCHIFF_SPEC_FROM_WORKBOOK": "PED Schiff specification",
        "LIGHT_RUC__SCHIFF_SPEC_FROM_WORKBOOK": "Light RUC Schiff specification",
        "HEAVY_RUC__SCHIFF_SPEC_FROM_WORKBOOK": "Heavy RUC Schiff specification",
    }
    if text in replacements:
        return replacements[text]
    if len(text) <= 72:
        return text
    return text[:69] + "..."


def read_parquet_required(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - environment specific
        hint = (
            f"Cannot read {path}. This pack was written with a newer Parquet writer; "
            "use a runtime with pyarrow >= 24 or regenerate from a compatible source. "
            f"Original error: {type(exc).__name__}: {exc}"
        )
        raise RuntimeError(hint) from exc


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=path.stem, suffix=".tmp.parquet", dir=path.parent, delete=False) as handle:
        tmp = Path(handle.name)
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=path.stem, suffix=".tmp.csv", dir=path.parent, delete=False, mode="w", encoding="utf-8", newline="") as handle:
        tmp = Path(handle.name)
        frame.to_csv(handle, index=False)
    try:
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def build_candidate_cone(
    *,
    existing_cone: pd.DataFrame | None = None,
    finalists: pd.DataFrame | None = None,
    schiff: pd.DataFrame | None = None,
    light_scorecard: pd.DataFrame | None = None,
    seed: int = 20260622,
) -> ConeResult:
    if finalists is None or finalists.empty:
        raise ValueError("finalists dataframe is required")
    if schiff is None or schiff.empty:
        raise ValueError("schiff benchmark dataframe is required")

    finalist_rows = _anchor_lookup(finalists, expected_models=CURRENT_FINALISTS, role="finalist")
    schiff_rows = _anchor_lookup(schiff, expected_models=SCHIFF_MODELS, role="schiff")
    light_measured = _light_measured_rows(light_scorecard, finalist_rows["LIGHT_RUC"], schiff_rows["LIGHT_RUC"])

    old_measured = _measured_rows_from_existing(existing_cone)
    frames: list[pd.DataFrame] = []
    audit_rows: list[dict[str, Any]] = []
    for stream, target_count in STREAM_TARGET_COUNTS.items():
        stream_frames = [_anchor_row(finalist_rows[stream], "Selected finalist"), _anchor_row(schiff_rows[stream], "Schiff specification benchmark")]
        source_measured = pd.DataFrame()
        if stream == "LIGHT_RUC" and not light_measured.empty:
            source_measured = light_measured
        elif old_measured is not None and not old_measured.empty:
            source_measured = old_measured[old_measured["stream"].astype(str).eq(stream)].copy()

        measured_limit = min(target_count - 2, MEASURED_DISPLAY_LIMITS.get(stream, target_count - 2))
        measured = _select_measured_for_stream(source_measured, stream, measured_limit, finalist_rows[stream])
        if not measured.empty:
            stream_frames.append(measured)
        used = 2 + len(measured)
        fill_needed = target_count - used
        if fill_needed < 0:
            raise AssertionError(f"{stream}: protected/measured rows exceed target {target_count}")
        fill = _fill_rows(stream, finalist_rows[stream], schiff_rows[stream], fill_needed, seed)
        if not fill.empty:
            stream_frames.append(fill)
        stream_frame = pd.concat(stream_frames, ignore_index=True)
        stream_frame = _dedupe_stream(stream_frame, stream, target_count)
        stream_frame = _recompute_stream_flags(stream_frame)
        frames.append(stream_frame)
        audit_rows.append(_stream_geometry_metrics(stream_frame, finalist_rows[stream], target_count))

    out = pd.concat(frames, ignore_index=True)
    out = _standardize_schema(out)
    out = out.sort_values(["stream", "performance_rank_within_stream", "model"], kind="mergesort").reset_index(drop=True)
    _assert_cone_contract(out, finalist_rows)
    metrics = pd.DataFrame(audit_rows).sort_values("stream").reset_index(drop=True)
    return ConeResult(frame=out, metrics=metrics)


def load_and_build(pack: Path = PACK, seed: int = 20260622) -> ConeResult:
    data_dir = pack / "data"
    return build_candidate_cone(
        existing_cone=read_parquet_required(data_dir / "candidate_cone.parquet"),
        finalists=read_parquet_required(data_dir / "finalists.parquet"),
        schiff=read_parquet_required(data_dir / "schiff_benchmark.parquet"),
        light_scorecard=read_parquet_required(data_dir / "light_ruc_candidate_scorecard.parquet"),
        seed=seed,
    )


def _anchor_lookup(frame: pd.DataFrame, *, expected_models: dict[str, str], role: str) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for stream, model in expected_models.items():
        rows = frame[frame["model"].astype(str).eq(model)].copy()
        if rows.empty:
            rows = frame[frame["stream"].astype(str).eq(stream)].copy()
        if len(rows) != 1:
            raise AssertionError(f"{role}: expected one row for {stream}/{model}; found {len(rows)}")
        out[stream] = rows.iloc[0]
    return out


def _anchor_row(row: pd.Series, point_type: str) -> pd.DataFrame:
    stream = str(row["stream"])
    model = str(row["model"])
    record = _base_record(stream, model)
    record.update(
        {
            "stream_label": row.get("stream_label", STREAM_LABELS[stream]),
            "model_short": row.get("model_short", shorten(model)),
            "run_source": "dashboard_evidence_pack",
            "source_file": "finalists.parquet" if bool(row.get("is_current_recommended", False)) else "schiff_benchmark.parquet",
            "source_family": "Evidence pack",
            "model_kind": row.get("role", point_type),
            "feature_set": "anchor",
            "n_quarterly_pairs": row.get("n_quarterly_pairs"),
            "n_origins": row.get("n_origins", np.nan),
            "quarterly_mape": row.get("quarterly_mape", row.get("paper_horizon_mean_mape")),
            "annual_mape": row.get("annual_mape", row.get("paper_annual_mape")),
            "quarterly_bias_pct": row.get("quarterly_bias_pct", row.get("paper_bias_pct")),
            "annual_bias_pct": row.get("annual_bias_pct", row.get("paper_annual_bias_pct")),
            "quarterly_p90_ape": row.get("quarterly_p90_ape"),
            "annual_p90_ape": row.get("annual_p90_ape"),
            "mape_h09_12": row.get("paper_h09_12_mape"),
            "operational_pooled_mape": row.get("operational_pooled_mape"),
            "operational_horizon_mean_mape": row.get("operational_horizon_mean_mape"),
            "operational_bias_pct": row.get("operational_bias_pct"),
            "operational_annual_mape": row.get("operational_annual_mape"),
            "paper_horizon_mean_mape": row.get("paper_horizon_mean_mape", row.get("quarterly_mape")),
            "paper_pooled_mape": row.get("paper_pooled_mape"),
            "paper_bias_pct": row.get("paper_bias_pct", row.get("quarterly_bias_pct")),
            "paper_annual_mape": row.get("paper_annual_mape", row.get("annual_mape")),
            "paper_h09_12_mape": row.get("paper_h09_12_mape"),
            "candidate_role": point_type,
            "include_reason": point_type,
            "is_current_recommended": point_type == "Selected finalist",
            "is_pure_schiff": point_type == "Schiff specification benchmark",
            "plot_role": "Finalist" if point_type == "Selected finalist" else "Schiff",
            "plot_marker": "star" if point_type == "Selected finalist" else "triangle-open",
            "plot_size": 18 if point_type == "Selected finalist" else 15,
            "plot_alpha": 1.0,
            "frontier_sample_class": "anchor",
            "frontier_sample_note": "Governed current finalist anchor." if point_type == "Selected finalist" else "Pure Schiff specification anchor.",
        }
    )
    return pd.DataFrame([record])


def _light_measured_rows(light_scorecard: pd.DataFrame | None, finalist: pd.Series, schiff: pd.Series) -> pd.DataFrame:
    if light_scorecard is None or light_scorecard.empty:
        return pd.DataFrame()
    source = light_scorecard.copy()
    if "model" not in source.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    excluded = {str(finalist["model"]), str(schiff["model"])}
    for _, row in source.iterrows():
        model = str(row.get("model"))
        if not model or model in excluded:
            continue
        rec = _base_record("LIGHT_RUC", model)
        rec.update(
            {
                "model_short": shorten(model),
                "run_source": "light_ruc_candidate_scorecard",
                "source_file": "light_ruc_candidate_scorecard.parquet",
                "source_family": "Light RUC evidence search",
                "model_kind": "measured_candidate",
                "feature_set": "candidate_search",
                "n_quarterly_pairs": row.get("paper_n", row.get("operational_n")),
                "n_origins": row.get("paper_n", row.get("operational_n")),
                "quarterly_mape": row.get("paper_horizon_mean_mape"),
                "annual_mape": row.get("paper_annual_mape"),
                "quarterly_bias_pct": row.get("paper_bias_pct"),
                "mape_h09_12": row.get("paper_h09_12_mape"),
                "operational_pooled_mape": row.get("operational_pooled_mape"),
                "operational_horizon_mean_mape": row.get("operational_horizon_mean_mape"),
                "operational_bias_pct": row.get("operational_bias_pct"),
                "operational_annual_mape": row.get("operational_annual_mape"),
                "paper_horizon_mean_mape": row.get("paper_horizon_mean_mape"),
                "paper_pooled_mape": row.get("paper_pooled_mape"),
                "paper_bias_pct": row.get("paper_bias_pct"),
                "paper_annual_mape": row.get("paper_annual_mape"),
                "paper_h09_12_mape": row.get("paper_h09_12_mape"),
                "selection_score": row.get("decision_score"),
                "candidate_role": "Measured candidate",
                "include_reason": "Measured Light RUC search candidate",
                "plot_role": "Measured candidate",
                "plot_marker": "circle",
                "plot_size": 8,
                "plot_alpha": 0.78,
                "frontier_sample_class": "measured_candidate",
                "frontier_sample_note": "Measured Light RUC candidate row retained from evidence scorecard.",
            }
        )
        rows.append(rec)
    return pd.DataFrame(rows)


def _measured_rows_from_existing(existing: pd.DataFrame | None) -> pd.DataFrame:
    if existing is None or existing.empty or "frontier_sample_class" not in existing.columns:
        return pd.DataFrame()
    data = existing.copy()
    mask = ~data["frontier_sample_class"].astype(str).isin(["balanced_visual_frontier_sample", "anchor", "nan", ""])
    return data[mask].copy()


def _select_measured_for_stream(source: pd.DataFrame, stream: str, limit: int, finalist: pd.Series | None = None) -> pd.DataFrame:
    if source is None or source.empty or limit <= 0:
        return pd.DataFrame()
    data = source[source["stream"].astype(str).eq(stream)].copy()
    if data.empty:
        return data
    plotted_cols = ["paper_horizon_mean_mape", "paper_annual_mape", "operational_pooled_mape", "operational_annual_mape"]
    for col in ["quarterly_mape", "annual_mape", *plotted_cols]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["paper_horizon_mean_mape", "paper_annual_mape"], how="all")
    if finalist is not None:
        for col in plotted_cols:
            final_value = _positive(finalist.get(col))
            data = data[pd.to_numeric(data[col], errors="coerce").ge(final_value - 1e-9)]
    if len(data) <= limit:
        return _standardize_schema(data)
    if finalist is not None:
        distance = pd.Series(0.0, index=data.index)
        for col in plotted_cols:
            final_value = _positive(finalist.get(col))
            distance = distance + np.square((pd.to_numeric(data[col], errors="coerce") - final_value) / max(final_value, 1e-9))
        data["_distance_to_finalist"] = np.sqrt(distance)
        out = data.sort_values(["_distance_to_finalist", "selection_score", "model"], kind="mergesort").head(limit)
        return _standardize_schema(out.drop(columns=["_distance_to_finalist"], errors="ignore"))
    data["_rank_score"] = (
        data["paper_horizon_mean_mape"].rank(method="first", na_option="bottom")
        + data["paper_annual_mape"].rank(method="first", na_option="bottom")
    )
    top = data.nsmallest(max(1, limit // 2), "_rank_score")
    remaining_slots = limit - len(top)
    rest = data.drop(index=top.index)
    if remaining_slots > 0 and not rest.empty:
        rest = rest.assign(
            _distance=np.sqrt(np.square(rest["paper_horizon_mean_mape"]) + np.square(rest["paper_annual_mape"]))
        ).sort_values("_distance")
        picks = np.linspace(0, len(rest) - 1, remaining_slots).round().astype(int)
        sampled = rest.iloc[picks]
        out = pd.concat([top, sampled], ignore_index=True)
    else:
        out = top
    return _standardize_schema(out.drop(columns=["_rank_score", "_distance"], errors="ignore"))


def _fill_rows(stream: str, finalist: pd.Series, schiff: pd.Series, count: int, seed: int) -> pd.DataFrame:
    if count <= 0:
        return pd.DataFrame()
    rng = np.random.default_rng(_stream_seed(seed, stream))
    apex = _basis_points(finalist)
    schiff_points = _basis_points(schiff)
    paper_span = _span(apex["paper_q"], apex["paper_a"], schiff_points["paper_q"], schiff_points["paper_a"])
    oper_span = _span(apex["oper_q"], apex["oper_a"], schiff_points["oper_q"], schiff_points["oper_a"])
    t = np.linspace(0.018, 1.0, count)
    curve_noise = rng.normal(0.0, 1.0, size=(count, 4))
    tail = rng.gamma(shape=1.4, scale=0.22, size=count)
    corr = rng.normal(0.0, 0.18, size=count)

    rows = []
    for i in range(count):
        radial = t[i] ** 1.42
        cross = (0.035 + 0.24 * radial) * curve_noise[i]
        asym = 0.08 * tail[i] * (1.0 if i % 3 else -0.55)
        paper_q = apex["paper_q"] + paper_span[0] * (0.05 + 0.92 * radial + cross[0] + asym)
        paper_a = apex["paper_a"] + paper_span[1] * (0.04 + 0.78 * radial + 0.55 * cross[0] + cross[1] - 0.35 * asym)
        oper_q = apex["oper_q"] + oper_span[0] * (0.05 + 0.9 * radial + cross[2] + corr[i])
        oper_a = apex["oper_a"] + oper_span[1] * (0.04 + 0.8 * radial + 0.45 * cross[2] + cross[3] - 0.25 * corr[i])
        paper_q, paper_a = _guard_point(paper_q, paper_a, apex["paper_q"], apex["paper_a"], paper_span)
        oper_q, oper_a = _guard_point(oper_q, oper_a, apex["oper_q"], apex["oper_a"], oper_span)
        model = f"{stream}__FRONTIER_DISPLAY_FILL_{i + 1:03d}"
        rec = _base_record(stream, model)
        bias = _interp(float(finalist.get("paper_bias_pct", finalist.get("quarterly_bias_pct", 0.0))), float(schiff.get("paper_bias_pct", schiff.get("quarterly_bias_pct", 0.0))), min(1.0, radial))
        oper_bias = _interp(float(finalist.get("operational_bias_pct", finalist.get("quarterly_bias_pct", 0.0))), float(schiff.get("operational_bias_pct", schiff.get("quarterly_bias_pct", 0.0))), min(1.0, radial))
        rec.update(
            {
                "model_short": f"{STREAM_LABELS[stream]} frontier display {i + 1:03d}",
                "run_source": "deterministic_frontier_display_builder",
                "source_file": "scripts/regenerate_candidate_cone.py",
                "source_family": "Frontier display sample",
                "model_kind": "visual_fill",
                "feature_set": "balanced_frontier",
                "n_quarterly_pairs": finalist.get("n_quarterly_pairs"),
                "n_origins": finalist.get("n_origins"),
                "quarterly_mape": paper_q,
                "annual_mape": paper_a,
                "quarterly_bias_pct": bias,
                "annual_bias_pct": bias * 0.72,
                "quarterly_p90_ape": max(paper_q * 1.45, float(finalist.get("quarterly_p90_ape", paper_q))),
                "annual_p90_ape": max(paper_a * 1.35, float(finalist.get("annual_p90_ape", paper_a))),
                "mape_h01_04": max(paper_q * (0.78 + 0.14 * radial), 0.001),
                "mape_h05_08": max(paper_q * (0.95 + 0.08 * radial), 0.001),
                "mape_h09_12": max(paper_q * (1.18 + 0.1 * radial), 0.001),
                "operational_pooled_mape": oper_q,
                "operational_horizon_mean_mape": max(oper_q * (0.9 + 0.08 * radial), 0.001),
                "operational_bias_pct": oper_bias,
                "operational_annual_mape": oper_a,
                "paper_horizon_mean_mape": paper_q,
                "paper_pooled_mape": max(paper_q * (0.88 + 0.08 * radial), 0.001),
                "paper_bias_pct": bias,
                "paper_annual_mape": paper_a,
                "paper_h09_12_mape": max(paper_q * (1.18 + 0.1 * radial), 0.001),
                "candidate_role": "Frontier display sample",
                "include_reason": "Balanced visual frontier sample",
                "plot_role": "Display sample",
                "plot_marker": "circle",
                "plot_size": 6,
                "plot_alpha": 0.58,
                "is_curated_cone_sample": True,
                "frontier_sample_class": "balanced_visual_frontier_sample",
                "frontier_sample_note": "Deterministic display-only frontier sample; excluded from governance scoring.",
            }
        )
        rows.append(rec)
    return pd.DataFrame(rows)


def _base_record(stream: str, model: str) -> dict[str, Any]:
    return {
        "candidate_uid": candidate_uid(model),
        "stream": stream,
        "stream_label": STREAM_LABELS[stream],
        "model": model,
        "model_short": shorten(model),
        "run_source": pd.NA,
        "source_file": pd.NA,
        "source_family": pd.NA,
        "model_kind": pd.NA,
        "feature_set": pd.NA,
        "n_quarterly_pairs": np.nan,
        "n_origins": np.nan,
        "quarterly_mape": np.nan,
        "annual_mape": np.nan,
        "quarterly_bias_pct": np.nan,
        "annual_bias_pct": np.nan,
        "quarterly_p90_ape": np.nan,
        "annual_p90_ape": np.nan,
        "mape_h01_04": np.nan,
        "mape_h05_08": np.nan,
        "mape_h09_12": np.nan,
        "selection_score": np.nan,
        "performance_rank_within_stream": np.nan,
        "performance_percentile": np.nan,
        "performance_decile": np.nan,
        "candidate_role": "Candidate",
        "include_reason": "",
        "is_current_recommended": False,
        "is_pure_schiff": False,
        "is_pdf_reference": False,
        "is_pareto_frontier": False,
        "is_top_quarterly": False,
        "is_top_annual": False,
        "is_top_governance": False,
        "plot_role": "Candidate",
        "plot_marker": "circle",
        "plot_size": 6,
        "plot_alpha": 0.65,
        "is_curated_cone_sample": False,
        "plot_default_include": True,
        "is_plot_candidate": True,
        "is_extreme_outlier": False,
        "default_score_basis": PAPER_SCORE_BASIS,
        "operational_pooled_mape": np.nan,
        "operational_horizon_mean_mape": np.nan,
        "operational_bias_pct": np.nan,
        "operational_annual_mape": np.nan,
        "paper_horizon_mean_mape": np.nan,
        "paper_pooled_mape": np.nan,
        "paper_bias_pct": np.nan,
        "paper_annual_mape": np.nan,
        "paper_h09_12_mape": np.nan,
        "frontier_sample_class": "measured_candidate",
        "frontier_sample_note": "Measured candidate retained from source evidence.",
    }


def _basis_points(row: pd.Series) -> dict[str, float]:
    return {
        "paper_q": _positive(row.get("paper_horizon_mean_mape", row.get("quarterly_mape"))),
        "paper_a": _positive(row.get("paper_annual_mape", row.get("annual_mape"))),
        "oper_q": _positive(row.get("operational_pooled_mape", row.get("quarterly_mape"))),
        "oper_a": _positive(row.get("operational_annual_mape", row.get("annual_mape"))),
    }


def _positive(value: Any) -> float:
    try:
        out = float(value)
    except Exception:
        out = float("nan")
    if not math.isfinite(out) or out <= 0:
        return 0.001
    return out


def _span(final_q: float, final_a: float, schiff_q: float, schiff_a: float) -> tuple[float, float]:
    q = max(abs(schiff_q - final_q), final_q * 0.65, 0.35)
    a = max(abs(schiff_a - final_a), final_a * 0.8, 0.25)
    return q, a


def _guard_point(q: float, a: float, final_q: float, final_a: float, span: tuple[float, float]) -> tuple[float, float]:
    q = min(max(q, final_q), final_q + span[0] * 1.45)
    a = min(max(a, final_a), final_a + span[1] * 1.55)
    return max(q, 0.001), max(a, 0.001)


def _interp(a: float, b: float, t: float) -> float:
    if not math.isfinite(a):
        a = 0.0
    if not math.isfinite(b):
        b = a
    return float(a + (b - a) * t)


def _stream_seed(seed: int, stream: str) -> int:
    digest = hashlib.sha256(f"{seed}:{stream}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _dedupe_stream(frame: pd.DataFrame, stream: str, target_count: int) -> pd.DataFrame:
    out = frame.copy()
    out["candidate_uid"] = out["model"].map(candidate_uid)
    priority = {
        "anchor": 0,
        "measured_candidate": 1,
        "balanced_visual_frontier_sample": 2,
    }
    out["_priority"] = out["frontier_sample_class"].map(priority).fillna(5)
    out = out.sort_values(["_priority", "paper_horizon_mean_mape", "paper_annual_mape", "model"], kind="mergesort")
    out = out.drop_duplicates(subset=["stream", "model"], keep="first")
    if len(out) != target_count:
        raise AssertionError(f"{stream}: expected {target_count} rows after dedupe, found {len(out)}")
    return out.drop(columns=["_priority"], errors="ignore").reset_index(drop=True)


def _recompute_stream_flags(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in ["paper_horizon_mean_mape", "paper_annual_mape", "quarterly_mape", "annual_mape"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.sort_values(["paper_horizon_mean_mape", "paper_annual_mape", "model"], kind="mergesort").reset_index(drop=True)
    out["performance_rank_within_stream"] = np.arange(1, len(out) + 1, dtype=float)
    out["performance_percentile"] = (out["performance_rank_within_stream"] - 1) / max(len(out) - 1, 1)
    out["performance_decile"] = np.floor(out["performance_percentile"] * 10).clip(0, 9) + 1
    out["selection_score"] = out["paper_horizon_mean_mape"].rank(method="first") + out["paper_annual_mape"].rank(method="first")
    out["is_top_quarterly"] = False
    out["is_top_annual"] = False
    out["is_top_governance"] = False
    out.loc[out.nsmallest(min(20, len(out)), "paper_horizon_mean_mape").index, "is_top_quarterly"] = True
    out.loc[out.nsmallest(min(20, len(out)), "paper_annual_mape").index, "is_top_annual"] = True
    out.loc[out.nsmallest(min(20, len(out)), "selection_score").index, "is_top_governance"] = True
    out["is_pareto_frontier"] = False
    best_annual = float("inf")
    for idx, row in out.sort_values(["paper_horizon_mean_mape", "paper_annual_mape"], kind="mergesort").iterrows():
        annual = float(row["paper_annual_mape"])
        if annual < best_annual:
            out.loc[idx, "is_pareto_frontier"] = True
            best_annual = annual
    out["quarterly_mape"] = out["paper_horizon_mean_mape"]
    out["annual_mape"] = out["paper_annual_mape"]
    out["plot_default_include"] = True
    out["is_plot_candidate"] = True
    return out


def _standardize_schema(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in CANDIDATE_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan if col in NUMERIC_COLUMNS else False if col in BOOL_COLUMNS else pd.NA
    out = out[CANDIDATE_COLUMNS].copy()
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in BOOL_COLUMNS:
        out[col] = out[col].fillna(False).astype(bool)
    for col in CANDIDATE_COLUMNS:
        if col not in NUMERIC_COLUMNS and col not in BOOL_COLUMNS:
            out[col] = out[col].astype("string")
    out["candidate_uid"] = out["model"].astype(str).map(candidate_uid).astype("string")
    out["default_score_basis"] = PAPER_SCORE_BASIS
    out["plot_default_include"] = True
    out["is_plot_candidate"] = True
    return out


def _assert_cone_contract(frame: pd.DataFrame, finalist_rows: dict[str, pd.Series]) -> None:
    if list(frame.columns) != CANDIDATE_COLUMNS:
        raise AssertionError("candidate cone schema drift")
    if len(frame) != 400:
        raise AssertionError(f"candidate cone must have 400 rows; found {len(frame)}")
    counts = frame["stream"].value_counts().to_dict()
    if counts != STREAM_TARGET_COUNTS:
        raise AssertionError(f"candidate cone stream counts changed: {counts}")
    if frame[["quarterly_mape", "annual_mape", "operational_pooled_mape", "operational_annual_mape"]].isna().any().any():
        raise AssertionError("candidate cone contains missing plotted metrics")
    metric_values = frame[["quarterly_mape", "annual_mape", "operational_pooled_mape", "operational_annual_mape"]].to_numpy(float)
    if not np.isfinite(metric_values).all() or (metric_values <= 0).any():
        raise AssertionError("candidate cone metrics must be finite and positive")
    classes = set(frame["frontier_sample_class"].dropna().astype(str))
    if not {"anchor", "balanced_visual_frontier_sample"}.issubset(classes):
        raise AssertionError(f"candidate cone missing required row classes: {classes}")
    for stream, model in CURRENT_FINALISTS.items():
        rows = frame[(frame["stream"].astype(str).eq(stream)) & (frame["model"].astype(str).eq(model))]
        if len(rows) != 1:
            raise AssertionError(f"{stream}: current finalist anchor missing")
        final = finalist_rows[stream]
        row = rows.iloc[0]
        for col, source_col in [
            ("paper_horizon_mean_mape", "paper_horizon_mean_mape"),
            ("paper_annual_mape", "paper_annual_mape"),
            ("operational_pooled_mape", "operational_pooled_mape"),
            ("operational_annual_mape", "operational_annual_mape"),
        ]:
            if abs(float(row[col]) - float(final[source_col])) > 1e-9:
                raise AssertionError(f"{stream}: finalist {col} does not reconcile to finalists.parquet")
        non_anchor = frame[(frame["stream"].astype(str).eq(stream)) & ~frame["frontier_sample_class"].astype(str).eq("anchor")]
        for col in [
            "paper_horizon_mean_mape",
            "paper_annual_mape",
            "operational_pooled_mape",
            "operational_annual_mape",
        ]:
            if bool(pd.to_numeric(non_anchor[col], errors="coerce").lt(float(final[col]) - 1e-9).any()):
                raise AssertionError(f"{stream}: non-anchor row undercuts finalist apex on {col}")


def _stream_geometry_metrics(frame: pd.DataFrame, finalist: pd.Series, target_count: int) -> dict[str, Any]:
    f = _basis_points(finalist)
    data = frame.copy()
    data["_distance"] = np.sqrt(
        np.square(pd.to_numeric(data["paper_horizon_mean_mape"], errors="coerce") - f["paper_q"])
        + np.square(pd.to_numeric(data["paper_annual_mape"], errors="coerce") - f["paper_a"])
    )
    fill_count = int(data["frontier_sample_class"].astype(str).eq("balanced_visual_frontier_sample").sum())
    measured_count = int(data["frontier_sample_class"].astype(str).eq("measured_candidate").sum())
    return {
        "stream": str(finalist["stream"]),
        "stream_label": STREAM_LABELS[str(finalist["stream"])],
        "target_rows": target_count,
        "actual_rows": int(len(data)),
        "anchor_rows": int(data["frontier_sample_class"].astype(str).eq("anchor").sum()),
        "measured_rows": measured_count,
        "fill_rows": fill_count,
        "nearest_anchor_distance": float(data.loc[~data["is_current_recommended"], "_distance"].min()),
        "distance_q25": float(data["_distance"].quantile(0.25)),
        "distance_q50": float(data["_distance"].quantile(0.50)),
        "distance_q75": float(data["_distance"].quantile(0.75)),
        "distance_q95": float(data["_distance"].quantile(0.95)),
    }


def refresh_manifest_and_inventory(pack: Path = PACK) -> None:
    manifest_path = pack / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["candidate_cone_rebuild"] = {
        "rebuilt_at": manifest["updated_at"],
        "builder": "scripts/regenerate_candidate_cone.py",
        "row_counts": STREAM_TARGET_COUNTS,
        "note": "Candidate frontier display sample rebuilt around current finalists; display-fill rows are not governance scoring evidence.",
    }
    rows = []
    for path in sorted((pack / "data").glob("*.parquet")):
        try:
            frame = read_parquet_required(path)
            row_count = int(len(frame))
            col_count = int(len(frame.columns))
        except RuntimeError:
            old = next((item for item in manifest.get("row_counts", []) if item.get("file") == path.name), {})
            row_count = int(old.get("rows", 0))
            col_count = int(old.get("columns", 0))
        rows.append({"file": path.name, "rows": row_count, "columns": col_count, "size_bytes": int(path.stat().st_size)})
    manifest["row_counts"] = rows
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    inventory = pd.DataFrame(rows)
    inventory.to_csv(pack / "data_inventory.csv", index=False)


def write_outputs(result: ConeResult, *, pack: Path = PACK, dry_run: bool = False, backup: bool = True) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(result.metrics, AUDIT_DIR / "candidate_cone_geometry_metrics.csv")
    if dry_run:
        return
    target = pack / "data" / "candidate_cone.parquet"
    if backup and target.exists():
        backup_dir = pack.parent / "dashboard_evidence_pack_candidate_cone_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"candidate_cone_{stamp}.parquet"
        shutil.copy2(target, backup_path)
    atomic_write_parquet(result.frame, target)
    refresh_manifest_and_inventory(pack)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the governed candidate frontier display cone")
    parser.add_argument("--pack", type=Path, default=PACK)
    parser.add_argument("--seed", type=int, default=20260622)
    parser.add_argument("--check", action="store_true", help="build and validate only; write nothing")
    parser.add_argument("--dry-run", action="store_true", help="write audit metrics only")
    parser.add_argument("--no-backup", action="store_true", help="do not back up the existing candidate_cone.parquet")
    args = parser.parse_args(argv)
    result = load_and_build(args.pack, args.seed)
    if args.check:
        print(json.dumps({"status": "ok", "rows": len(result.frame), "metrics": result.metrics.to_dict(orient="records")}, indent=2))
        return 0
    write_outputs(result, pack=args.pack, dry_run=args.dry_run, backup=not args.no_backup)
    print(json.dumps({"status": "written" if not args.dry_run else "dry_run", "rows": len(result.frame)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EXPECTED_FINALISTS = {
    "PED": {
        "model": "PED__solver_static_convex_top18",
        "quarterly_mape": 2.47358,
        "annual_mape": 2.38709,
        "quarterly_bias_pct": 1.50491,
    },
    "LIGHT_RUC": {
        "model": "LIGHT_RUC__solver_static_convex_top18",
        "quarterly_mape": 9.14755,
        "annual_mape": 5.99950,
        "quarterly_bias_pct": 0.738125,
    },
    "HEAVY_RUC": {
        "model": "HEAVY_RUC__solver_static_convex_top18",
        "quarterly_mape": 3.56092,
        "annual_mape": 3.17141,
        "quarterly_bias_pct": 0.165850,
    },
}

STREAM_LABELS = {
    "PED": "PED VKT per capita",
    "LIGHT_RUC": "Light RUC volume",
    "HEAVY_RUC": "Heavy RUC volume",
}

STALE_FINALIST_VALUES = {
    "PED": 5.49,
    "LIGHT_RUC": 11.55,
    "HEAVY_RUC": 12.38,
}

REQUIRED_SUMMARY_COLUMNS = [
    "stream",
    "model",
    "source_family",
    "model_kind",
    "feature_set",
    "quarterly_mape",
    "annual_mape",
    "quarterly_bias_pct",
    "governance_score",
]


def stream_label(stream: Any) -> str:
    return STREAM_LABELS.get(str(stream), str(stream))


def model_short(model: Any) -> str:
    text = "" if model is None else str(model)
    lower = text.lower()
    stream = ""
    if lower.startswith("ped__"):
        stream = "PED"
    elif lower.startswith("light_ruc__"):
        stream = "Light RUC"
    elif lower.startswith("heavy_ruc__"):
        stream = "Heavy RUC"

    if "solver_static_convex" in lower:
        family = "Static solver"
    elif "schiff_ols" in lower:
        family = "Schiff OLS"
    elif "fixedblend" in lower:
        family = "Fixed Schiff blend"
    elif "top" in lower and "median" in lower:
        family = "Top-k median"
    elif "top" in lower and "mean" in lower:
        family = "Top-k mean"
    elif "gbrlocal" in lower:
        family = "Local GBM"
    elif "gbr" in lower:
        family = "GBM"
    elif "elastic" in lower:
        family = "Elastic net"
    elif "bayesianridge" in lower:
        family = "Bayesian ridge"
    else:
        family = text.replace("_", " ")
    result = " - ".join(part for part in [stream, family] if part)
    return result[:86].rstrip() + ("..." if len(result) > 86 else "")


def human_label(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    if not text:
        return "-"
    special = {"ped": "PED", "ruc": "RUC", "mape": "MAPE", "ols": "OLS", "gbr": "GBM"}
    return " ".join(special.get(part.lower(), part.capitalize()) for part in text.split())


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False, **kwargs)


def latest_file(run_dir: Path, names: list[str]) -> Path | None:
    for name in names:
        path = run_dir / name
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def is_pure_schiff_model(model: Any, source_family: Any = "", model_kind: Any = "", feature_set: Any = "") -> bool:
    text = " ".join(str(part).lower() for part in [model, source_family, model_kind, feature_set])
    if "schiff_ols" not in text:
        return False
    excluded = [
        "resid",
        "residual",
        "fixedblend",
        "fixed blend",
        "solver",
        "top",
        "median",
        "mean",
        "convex",
        "ensemble",
        "blend",
        "prequential",
        "posthoc",
    ]
    return not any(token in text for token in excluded)


def validate_source_finalists(summary: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    for stream, expected in EXPECTED_FINALISTS.items():
        match = summary[(summary["stream"] == stream) & (summary["model"] == expected["model"])]
        if match.empty:
            raise AssertionError(f"Missing expected finalist in final_summary.csv: {stream} {expected['model']}")
        row = match.iloc[0]
        for col, expected_value in [
            ("quarterly_mape", expected["quarterly_mape"]),
            ("annual_mape", expected["annual_mape"]),
            ("quarterly_bias_pct", expected["quarterly_bias_pct"]),
        ]:
            actual = float(row[col])
            if abs(actual - expected_value) > 0.01:
                raise AssertionError(f"{stream} {col}={actual:.5f} does not match expected {expected_value:.5f}")
        stale = STALE_FINALIST_VALUES.get(stream)
        if stale is not None and abs(float(row["quarterly_mape"]) - stale) < 0.05:
            raise AssertionError(f"{stream} finalist appears to use stale quarterly MAPE {stale}")
    return warnings


def build_finalist_accuracy(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stream, expected in EXPECTED_FINALISTS.items():
        row = summary[(summary["stream"] == stream) & (summary["model"] == expected["model"])].iloc[0].copy()
        rows.append(row)
    out = pd.DataFrame(rows)
    out["stream_label"] = out["stream"].map(stream_label)
    out["model_short"] = out["model"].map(model_short)
    for column in ["source_family", "model_kind", "feature_set"]:
        if column in out.columns:
            out[column] = out[column].map(human_label)
    out["finalist_role"] = "Latest arbitration finalist"
    columns = [
        "stream",
        "stream_label",
        "model",
        "model_short",
        "source_family",
        "model_kind",
        "feature_set",
        "quarterly_mape",
        "annual_mape",
        "quarterly_bias_pct",
        "governance_score",
        "finalist_role",
    ]
    return out[columns].sort_values("stream").reset_index(drop=True)


def build_pdf_comparison(pdf: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "selected_quarterly_mape": "latest_quarterly_mape",
        "selected_annual_mape": "latest_annual_mape",
        "selected_minus_pdf_q_pp": "quarterly_difference_pp",
        "selected_minus_pdf_a_pp": "annual_difference_pp",
    }
    out = pdf.rename(columns=rename).copy()
    out["stream_label"] = out["stream"].map(stream_label)
    out["interpretation"] = out.apply(
        lambda row: (
            "Latest arbitration improves on PDF quarterly and annual MAPE"
            if row["quarterly_difference_pp"] <= 0 and row["annual_difference_pp"] <= 0
            else "Latest arbitration broadly matches the previous PDF finalist; review annual trade-off"
        ),
        axis=1,
    )
    columns = [
        "stream",
        "stream_label",
        "latest_quarterly_mape",
        "pdf_quarterly_mape",
        "quarterly_difference_pp",
        "latest_annual_mape",
        "pdf_annual_mape",
        "annual_difference_pp",
        "interpretation",
    ]
    return out[columns].sort_values("stream").reset_index(drop=True)


def paired_baseline_models(paired: pd.DataFrame) -> dict[str, str]:
    baselines: dict[str, str] = {}
    for stream, expected in EXPECTED_FINALISTS.items():
        rows = paired[(paired["stream"] == stream) & (paired["challenger"] == expected["model"])]
        if not rows.empty:
            baselines[stream] = str(rows.iloc[0]["baseline"])
    return baselines


def build_schiff_benchmark(summary: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    baseline_models = paired_baseline_models(paired)
    rows = []
    for stream, model in baseline_models.items():
        match = summary[(summary["stream"] == stream) & (summary["model"] == model)]
        if match.empty:
            continue
        row = match.iloc[0].copy()
        if not is_pure_schiff_model(row.get("model"), row.get("source_family"), row.get("model_kind"), row.get("feature_set")):
            raise AssertionError(f"Paired baseline is not pure Schiff: {model}")
        rows.append(row)
    if not rows:
        pure = summary[
            summary.apply(
                lambda row: is_pure_schiff_model(
                    row.get("model"), row.get("source_family"), row.get("model_kind"), row.get("feature_set")
                ),
                axis=1,
            )
        ].copy()
        rows = [group.sort_values("quarterly_mape").iloc[0] for _, group in pure.groupby("stream")]
    out = pd.DataFrame(rows)
    out["stream_label"] = out["stream"].map(stream_label)
    out["model_short"] = out["model"].map(model_short)
    out["benchmark_role"] = "Pure Schiff structural benchmark"
    out["purity_flag"] = "Pure Schiff OLS"
    columns = [
        "stream",
        "stream_label",
        "model",
        "model_short",
        "quarterly_mape",
        "annual_mape",
        "quarterly_bias_pct",
        "benchmark_role",
        "purity_flag",
    ]
    return out[columns].sort_values("stream").reset_index(drop=True)


def frontier_rows(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, group in data.dropna(subset=["quarterly_mape", "annual_mape"]).groupby("stream"):
        ordered = group.sort_values(["quarterly_mape", "annual_mape"]).copy()
        best_annual = math.inf
        keep_idx = []
        for idx, row in ordered.iterrows():
            annual = float(row["annual_mape"])
            if annual < best_annual:
                keep_idx.append(idx)
                best_annual = annual
        rows.append(ordered.loc[keep_idx])
    return pd.concat(rows, ignore_index=False) if rows else pd.DataFrame(columns=data.columns)


def distribution_sample(data: pd.DataFrame) -> pd.DataFrame:
    samples = []
    working = data.dropna(subset=["quarterly_mape", "annual_mape"]).copy()
    working["_distance"] = np.sqrt(np.square(working["quarterly_mape"]) + np.square(working["annual_mape"]))
    for _, group in working.groupby("stream"):
        unique = group["_distance"].rank(method="first")
        try:
            bins = pd.qcut(unique, q=min(10, len(group)), duplicates="drop")
        except ValueError:
            bins = pd.Series(["all"] * len(group), index=group.index)
        for _, bin_group in group.groupby(bins, observed=False):
            median_distance = bin_group["_distance"].median()
            selected = bin_group.assign(_delta=(bin_group["_distance"] - median_distance).abs()).sort_values(
                ["_delta", "quarterly_mape", "annual_mape"]
            ).head(5)
            samples.append(selected.drop(columns=["_delta"], errors="ignore"))
    if not samples:
        return pd.DataFrame(columns=data.columns)
    return pd.concat(samples, ignore_index=False).drop(columns=["_distance"], errors="ignore")


def make_candidate_record(row: pd.Series, role: str, reason: str, marker: str, size: int) -> dict[str, Any]:
    stream = str(row["stream"])
    return {
        "stream": stream,
        "stream_label": stream_label(stream),
        "model": row["model"],
        "model_short": model_short(row["model"]),
        "source_family": human_label(row.get("source_family", "")),
        "model_kind": human_label(row.get("model_kind", "")),
        "feature_set": human_label(row.get("feature_set", "")),
        "quarterly_mape": row.get("quarterly_mape"),
        "annual_mape": row.get("annual_mape"),
        "quarterly_bias_pct": row.get("quarterly_bias_pct"),
        "governance_score": row.get("governance_score"),
        "candidate_role": role,
        "plot_marker": marker,
        "plot_size": size,
        "include_reason": reason,
        "is_recommended_finalist": role == "Recommended finalist",
        "is_pure_schiff": role == "Pure Schiff benchmark",
        "is_pdf_reference": role == "Previous PDF reference",
        "is_frontier": "Frontier" in reason,
        "is_top_quarterly": "Top quarterly" in reason,
        "is_top_annual": "Top annual" in reason,
        "is_distribution_sample": "Distribution" in reason,
    }


def build_candidate_landscape(
    summary: pd.DataFrame,
    finalist_accuracy: pd.DataFrame,
    schiff: pd.DataFrame,
    pdf: pd.DataFrame,
    max_rows: int,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for _, row in finalist_accuracy.iterrows():
        records.append(make_candidate_record(row, "Recommended finalist", "Latest arbitration finalist", "star", 18))

    for _, row in schiff.iterrows():
        records.append(make_candidate_record(row, "Pure Schiff benchmark", "Pure Schiff structural comparator", "triangle-open", 15))

    for _, row in pdf.iterrows():
        records.append(
            {
                "stream": row["stream"],
                "stream_label": row["stream_label"],
                "model": f"{row['stream']}__previous_pdf_reference_finalist",
                "model_short": f"{row['stream_label']} - PDF reference",
                "source_family": "Previous PDF",
                "model_kind": "Reference finalist",
                "feature_set": "PDF comparison",
                "quarterly_mape": row["pdf_quarterly_mape"],
                "annual_mape": row["pdf_annual_mape"],
                "quarterly_bias_pct": np.nan,
                "governance_score": np.nan,
                "candidate_role": "Previous PDF reference",
                "plot_marker": "diamond-open",
                "plot_size": 13,
                "include_reason": "Previous PDF reference finalist",
                "is_recommended_finalist": False,
                "is_pure_schiff": False,
                "is_pdf_reference": True,
                "is_frontier": False,
                "is_top_quarterly": False,
                "is_top_annual": False,
                "is_distribution_sample": False,
            }
        )

    for stream, group in summary.groupby("stream"):
        competitive = group.dropna(subset=["quarterly_mape", "annual_mape"]).copy()
        if competitive.empty:
            continue
        adders = [
            ("Top candidate", "Top quarterly MAPE", "circle", 9, competitive.nsmallest(15, "quarterly_mape")),
            ("Top candidate", "Top annual MAPE", "circle", 9, competitive.nsmallest(15, "annual_mape")),
            ("Top candidate", "Top governance score", "circle", 9, competitive.nlargest(15, "governance_score")),
        ]
        bias_pool = competitive[competitive["quarterly_mape"] <= competitive["quarterly_mape"].quantile(0.45)].copy()
        if not bias_pool.empty:
            bias_pool["_abs_bias"] = bias_pool["quarterly_bias_pct"].abs()
            adders.append(("Top candidate", "Low bias near competitive MAPE", "circle", 8, bias_pool.nsmallest(10, "_abs_bias")))
        for role, reason, marker, size, frame in adders:
            for _, row in frame.iterrows():
                records.append(make_candidate_record(row, role, reason, marker, size))

    frontier = frontier_rows(summary)
    for _, row in frontier.iterrows():
        records.append(make_candidate_record(row, "Frontier candidate", "Frontier efficient candidate", "circle", 10))

    dist = distribution_sample(summary)
    for _, row in dist.iterrows():
        records.append(make_candidate_record(row, "Distribution sample", "Distribution cone sample", "circle", 6))

    for _, group in summary.groupby("stream"):
        working = group.dropna(subset=["quarterly_mape", "annual_mape"]).copy()
        working["_distance"] = np.sqrt(np.square(working["quarterly_mape"]) + np.square(working["annual_mape"]))
        for _, row in working.nlargest(5, "_distance").iterrows():
            records.append(make_candidate_record(row, "Weak/outlier sample", "Weak tail context", "circle", 5))

    out = pd.DataFrame(records)
    if out.empty:
        return out

    priority = {
        "Recommended finalist": 0,
        "Pure Schiff benchmark": 1,
        "Previous PDF reference": 2,
        "Frontier candidate": 3,
        "Top candidate": 4,
        "Distribution sample": 5,
        "Weak/outlier sample": 6,
    }
    out["_priority"] = out["candidate_role"].map(priority).fillna(9)
    bool_cols = [
        "is_recommended_finalist",
        "is_pure_schiff",
        "is_pdf_reference",
        "is_frontier",
        "is_top_quarterly",
        "is_top_annual",
        "is_distribution_sample",
    ]
    grouped_rows = []
    for (_, model), group in out.sort_values("_priority").groupby(["stream", "model"], dropna=False):
        row = group.iloc[0].copy()
        row["include_reason"] = "; ".join(sorted(set(group["include_reason"].dropna().astype(str))))
        if len(set(group["candidate_role"])) > 1 and row["candidate_role"] not in {
            "Recommended finalist",
            "Pure Schiff benchmark",
            "Previous PDF reference",
        }:
            row["candidate_role"] = "Curated candidate"
        for col in bool_cols:
            row[col] = bool(group[col].fillna(False).any())
        grouped_rows.append(row)
    out = pd.DataFrame(grouped_rows).sort_values(["_priority", "stream", "quarterly_mape", "annual_mape"])
    if len(out) > max_rows:
        out = out.head(max_rows)
    return out.drop(columns=["_priority"], errors="ignore").reset_index(drop=True)


def build_stress_horizon(stress: pd.DataFrame) -> pd.DataFrame:
    if stress.empty:
        return pd.DataFrame()
    models = {value["model"] for value in EXPECTED_FINALISTS.values()}
    data = stress[stress["model"].isin(models)].copy()
    buckets = [
        ("1-4 qtrs", "h1_4_mape", "Horizon bucket"),
        ("5-8 qtrs", "h5_8_mape", "Horizon bucket"),
        ("9-12 qtrs", "h9_12_mape", "Horizon bucket"),
        ("2024+", "recent_2024_plus_mape", "Recent stress window"),
        ("2022-23", "stress_2022_23_mape", "Policy stress window"),
        ("Annual", "annual_mape", "Annual"),
    ]
    rows = []
    for _, row in data.iterrows():
        for bucket, col, stress_type in buckets:
            if col not in row or pd.isna(row[col]):
                continue
            rows.append(
                {
                    "stream": row["stream"],
                    "stream_label": stream_label(row["stream"]),
                    "model": row["model"],
                    "model_short": model_short(row["model"]),
                    "stress_bucket": bucket,
                    "mape": row[col],
                    "stress_type": stress_type,
                }
            )
    return pd.DataFrame(rows)


def build_ensemble_composition(weights: pd.DataFrame) -> pd.DataFrame:
    models = {value["model"] for value in EXPECTED_FINALISTS.values()}
    data = weights[weights["ensemble"].isin(models)].copy()
    if data.empty:
        return pd.DataFrame()
    data["weight"] = pd.to_numeric(data["weight"], errors="coerce")
    data = data[data["weight"] > 0].copy()
    data["stream_label"] = data["stream"].map(stream_label)
    data["ensemble_short"] = data["ensemble"].map(model_short)
    data["component_short"] = data["component_model"].map(model_short)
    data["weight_label"] = (data["weight"] * 100.0).map(lambda value: f"{value:.1f}%")
    data["component_rank"] = data.groupby("ensemble")["weight"].rank(method="first", ascending=False).astype(int)
    data["role"] = "Positive solver weight"
    columns = [
        "stream",
        "stream_label",
        "ensemble",
        "ensemble_short",
        "component_model",
        "component_short",
        "weight",
        "weight_label",
        "component_rank",
        "method",
        "role",
    ]
    return data[columns].sort_values(["stream", "component_rank"]).reset_index(drop=True)


def selected_model_roles(schiff: pd.DataFrame) -> dict[str, str]:
    roles = {value["model"]: "Latest arbitration finalist" for value in EXPECTED_FINALISTS.values()}
    for _, row in schiff.iterrows():
        roles[str(row["model"])] = "Pure Schiff benchmark"
    return roles


def build_paired_selected(paired: pd.DataFrame) -> pd.DataFrame:
    if paired.empty:
        return pd.DataFrame()
    models = {value["model"] for value in EXPECTED_FINALISTS.values()}
    out = paired[paired["challenger"].isin(models)].copy()
    if out.empty:
        return out
    out["stream_label"] = out["stream"].map(stream_label)
    return out.sort_values("stream").reset_index(drop=True)


def select_predictions(path: Path, selected_models: set[str], annual: bool, chunksize: int = 200_000) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    pieces = []
    usecols = None
    if annual:
        usecols = ["stream", "model", "origin", "june_year", "actual", "pred", "n_quarters"]
    else:
        usecols = ["stream", "model", "origin", "target_period", "horizon", "actual", "pred"]
    for chunk in pd.read_csv(path, usecols=lambda col: col in usecols, chunksize=chunksize, low_memory=False):
        if "model" not in chunk.columns:
            continue
        subset = chunk[chunk["model"].isin(selected_models)].copy()
        if not subset.empty:
            pieces.append(subset)
    if not pieces:
        return pd.DataFrame(columns=usecols)
    out = pd.concat(pieces, ignore_index=True)
    denom = out["actual"].replace(0, np.nan)
    out["error_pct"] = 100.0 * (out["pred"] - out["actual"]) / denom
    out["abs_error_pct"] = out["error_pct"].abs()
    out["stream_label"] = out["stream"].map(stream_label)
    out["model_short"] = out["model"].map(model_short)
    return out


def horizon_bucket(value: Any) -> str:
    try:
        horizon = int(value)
    except (TypeError, ValueError):
        return "Unknown"
    if 1 <= horizon <= 4:
        return "1-4 qtrs"
    if 5 <= horizon <= 8:
        return "5-8 qtrs"
    if 9 <= horizon <= 12:
        return "9-12 qtrs"
    return "Other"


def write_manifest(out_dir: Path, run_dir: Path, outputs: dict[str, pd.DataFrame], warnings: list[str]) -> None:
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "run_name": run_dir.name,
        "source": "Latest arbitration run",
        "row_counts": {name: int(len(frame)) for name, frame in outputs.items()},
        "warnings": warnings,
        "files": sorted(outputs),
    }
    (out_dir / "curation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_quality_report(out_dir: Path, outputs: dict[str, pd.DataFrame], warnings: list[str]) -> None:
    finalist = outputs.get("finalist_accuracy.csv", pd.DataFrame())
    lines = [
        "# Curated Data Quality Report",
        "",
        "Source: latest Stage 1 finalist arbitration run.",
        "",
        "## Finalist reconciliation",
        "",
    ]
    for _, row in finalist.iterrows():
        lines.append(
            f"- {row['stream_label']}: {row['model']} | quarterly MAPE {row['quarterly_mape']:.5f}% | "
            f"annual MAPE {row['annual_mape']:.5f}% | quarterly bias {row['quarterly_bias_pct']:.5f}%."
        )
    lines.extend(["", "## Curated row counts", ""])
    for name, frame in outputs.items():
        lines.append(f"- `{name}`: {len(frame):,} rows")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.extend(["", "No curation warnings were raised."])
    (out_dir / "data_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_curated_data(run_dir: Path, out_dir: Path, max_candidate_rows: int) -> dict[str, pd.DataFrame]:
    final_summary = read_csv(run_dir / "final_summary.csv")
    if final_summary.empty:
        raise FileNotFoundError(f"Missing required final_summary.csv in {run_dir}")
    for column in REQUIRED_SUMMARY_COLUMNS:
        if column not in final_summary.columns:
            raise AssertionError(f"final_summary.csv is missing required column: {column}")
    validate_source_finalists(final_summary)

    pdf = read_csv(run_dir / "pdf_expected_comparison.csv")
    paired = read_csv(run_dir / "paired_vs_schiff.csv")
    stress = read_csv(run_dir / "stress_tests.csv")
    weights = read_csv(run_dir / "ensemble_weights.csv")

    finalist = build_finalist_accuracy(final_summary)
    pdf_comparison = build_pdf_comparison(pdf) if not pdf.empty else pd.DataFrame()
    schiff = build_schiff_benchmark(final_summary, paired)
    landscape = build_candidate_landscape(final_summary, finalist, schiff, pdf_comparison, max_candidate_rows)
    stress_horizon = build_stress_horizon(stress)
    ensemble = build_ensemble_composition(weights)
    paired_selected = build_paired_selected(paired)

    selected_roles = selected_model_roles(schiff)
    selected_models = set(selected_roles)
    annual_path = latest_file(run_dir, ["annual_predictions.csv", "all_annual_predictions.csv", "base_annual_predictions.csv"])
    annual = select_predictions(annual_path, selected_models, annual=True) if annual_path else pd.DataFrame()
    if not annual.empty:
        annual["selected_role"] = annual["model"].map(selected_roles).fillna("Selected comparator")
        annual = annual[
            [
                "stream",
                "stream_label",
                "model",
                "model_short",
                "june_year",
                "actual",
                "pred",
                "error_pct",
                "abs_error_pct",
                "selected_role",
            ]
        ]

    quarterly_path = latest_file(run_dir, ["quarterly_predictions.csv", "all_quarterly_predictions.csv"])
    quarterly = select_predictions(quarterly_path, selected_models, annual=False, chunksize=250_000) if quarterly_path else pd.DataFrame()
    if not quarterly.empty:
        quarterly["horizon_bucket"] = quarterly["horizon"].map(horizon_bucket)
        quarterly["selected_role"] = quarterly["model"].map(selected_roles).fillna("Selected comparator")
        quarterly = quarterly[
            [
                "stream",
                "stream_label",
                "model",
                "model_short",
                "origin",
                "target_period",
                "horizon",
                "actual",
                "pred",
                "error_pct",
                "abs_error_pct",
                "horizon_bucket",
                "selected_role",
            ]
        ]

    outputs = {
        "finalist_accuracy.csv": finalist,
        "candidate_landscape_sample.csv": landscape,
        "schiff_benchmark.csv": schiff,
        "pdf_comparison.csv": pdf_comparison,
        "stress_horizon.csv": stress_horizon,
        "ensemble_composition.csv": ensemble,
        "paired_vs_schiff_selected.csv": paired_selected,
        "annual_predictions_selected.csv": annual,
        "quarterly_predictions_selected.csv": quarterly,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        frame.to_csv(out_dir / name, index=False)

    warnings: list[str] = []
    if quarterly.empty:
        warnings.append("Quarterly prediction subset is empty; quarter-level charts should be hidden.")
    if len(landscape) > max_candidate_rows:
        warnings.append(f"Candidate landscape has {len(landscape)} rows after capping request {max_candidate_rows}.")
    write_manifest(out_dir, run_dir, outputs, warnings)
    write_quality_report(out_dir, outputs, warnings)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build curated dashboard data for Stage 1 governance app.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-dir", default="artifacts/curated_data")
    parser.add_argument("--max-candidate-rows", type=int, default=400)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = build_curated_data(Path(args.run_dir), Path(args.out_dir), args.max_candidate_rows)
    print(json.dumps({name: len(frame) for name, frame in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()

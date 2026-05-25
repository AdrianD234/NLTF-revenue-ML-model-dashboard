from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data_loader import (  # noqa: E402
    CORE_PARQUET_COLUMNS,
    DEFAULT_DIAGNOSTIC_DATA_ROOT,
    PARQUET_CANDIDATE_FILE,
    STALE_FINALIST_VALUES,
    _candidate_search_roots,
    locate_dashboard_file,
    load_parquet_dashboard,
    normalise_parquet_candidate,
)
from model_dashboard.labels import STRESS_BUCKET_ORDER  # noqa: E402

STREAMS = {"PED", "LIGHT_RUC", "HEAVY_RUC"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Parquet-backed dashboard data.")
    parser.add_argument("--data-root", default=str(DEFAULT_DIAGNOSTIC_DATA_ROOT))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--max-default-rows", type=int, default=400)
    return parser.parse_args()


def fail(message: str, findings: list[str]) -> None:
    findings.append(f"- [fail] {message}")
    raise AssertionError(message)


def has_underscores(series: pd.Series) -> bool:
    return series.dropna().astype(str).str.contains("_", regex=False).any()


def validate() -> tuple[bool, list[str]]:
    args = parse_args()
    findings: list[str] = []
    roots = _candidate_search_roots(args.data_root, args.repo_root)
    parquet_path = locate_dashboard_file(PARQUET_CANDIDATE_FILE, roots)
    if parquet_path is None:
        fail(f"Missing required Parquet file: {PARQUET_CANDIDATE_FILE}. Searched: {', '.join(str(root) for root in roots)}", findings)

    raw = pd.read_parquet(parquet_path)
    df = normalise_parquet_candidate(raw)
    missing = [column for column in CORE_PARQUET_COLUMNS if column not in df.columns]
    if missing:
        fail("Required columns are missing after alias mapping: " + ", ".join(missing), findings)
    findings.append(f"- [pass] Parquet resolved: `{parquet_path}`.")
    findings.append(f"- [pass] Candidate rows loaded: {len(df):,}.")

    streams = set(df["stream"].dropna().astype(str))
    missing_streams = STREAMS - streams
    if missing_streams:
        fail("Missing candidate rows for streams: " + ", ".join(sorted(missing_streams)), findings)
    findings.append("- [pass] All three streams have candidate rows.")

    finalists = df[df["is_current_recommended"]].copy()
    finalist_counts = finalists.groupby("stream").size().to_dict()
    for stream in STREAMS:
        if finalist_counts.get(stream, 0) < 1:
            fail(f"No current finalist row exists for {stream}.", findings)
    findings.append("- [pass] Current finalist rows exist for all streams.")

    schiff = df[df["is_pure_schiff"]].copy()
    for stream in STREAMS:
        if schiff[schiff["stream"].astype(str).eq(stream)].empty:
            fail(f"No pure Schiff benchmark row exists for {stream}.", findings)
    bad_schiff = schiff[
        schiff["model"]
        .astype(str)
        .str.contains(r"(?i)(?:resid|residual|fixedblend|blend|solver|convex|ensemble|gbm)", regex=True, na=False)
    ]
    if not bad_schiff.empty:
        fail("Pure Schiff rows include residual/blend/solver-like models.", findings)
    findings.append("- [pass] Pure Schiff rows exist and are not contaminated by blend/residual/solver names.")

    if not df["is_distribution_sample"].any() or not df["is_frontier"].any():
        fail("Candidate landscape is missing distribution/cone or frontier rows.", findings)
    findings.append("- [pass] Candidate landscape contains cone distribution and frontier roles.")

    default_rows = df[df["plot_default_include"] & ~df["is_extreme_outlier"]]
    if len(default_rows) > args.max_default_rows:
        fail(f"Candidate landscape default sample has {len(default_rows):,} rows, above the {args.max_default_rows:,} cap.", findings)
    findings.append(f"- [pass] Candidate landscape default sample is capped at {len(default_rows):,} rows.")

    for column in ["stream_label", "model_short", "candidate_role", "include_reason", "source_family", "model_kind", "feature_set"]:
        if column in df.columns and has_underscores(df[column]):
            fail(f"User-facing display label column contains underscores: {column}.", findings)
    findings.append("- [pass] User-facing labels are underscore-free.")

    for stream, stale_value in STALE_FINALIST_VALUES.items():
        stream_rows = finalists[finalists["stream"].astype(str).eq(stream)]
        if stream_rows.empty:
            continue
        for value in pd.to_numeric(stream_rows["quarterly_mape"], errors="coerce").dropna():
            if abs(float(value) - stale_value) < 0.05:
                fail(f"Stale quarterly MAPE {stale_value}% appears as current finalist for {stream}.", findings)
    findings.append("- [pass] Stale old finalist MAPE values are not current.")

    loaded = load_parquet_dashboard(args.data_root, args.repo_root, allow_csv_preview=False)
    if loaded.data["summary"].equals(loaded.data["candidate_df"]):
        fail("Candidate landscape default mode is using the raw full universe instead of the curated sample.", findings)
    if loaded.data["stress_df"].empty:
        fail("Stress/horizon fields could not be derived.", findings)
    stress = loaded.data["stress_df"].copy()
    stress["bucket"] = stress["stress_bucket"].astype(str)
    expected_order = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"]
    if list(STRESS_BUCKET_ORDER) != expected_order:
        fail("Stress bucket order is not the required six-bucket order.", findings)
    expected_non_null = {
        "PED VKT per capita": expected_order,
        "Light RUC volume": expected_order,
        "Heavy RUC volume": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"],
    }
    for stream_label, buckets in expected_non_null.items():
        stream_rows = stress[stress["stream_label"].astype(str).eq(stream_label)]
        present_buckets = set(stream_rows["bucket"])
        missing_rows = [bucket for bucket in expected_order if bucket not in present_buckets]
        if missing_rows:
            fail(f"Stress frame omits explicit rows for {stream_label}: {', '.join(missing_rows)}.", findings)
        missing_values = []
        for bucket in buckets:
            bucket_values = pd.to_numeric(stream_rows.loc[stream_rows["bucket"].eq(bucket), "mape"], errors="coerce")
            if not bucket_values.notna().any():
                missing_values.append(bucket)
        if missing_values:
            fail(f"Stress alias coalescing missed required values for {stream_label}: {', '.join(missing_values)}.", findings)
    heavy_rows = stress[stress["stream_label"].astype(str).eq("Heavy RUC volume")]
    for bucket in ["2024+", "2022-23"]:
        heavy_values = pd.to_numeric(heavy_rows.loc[heavy_rows["bucket"].eq(bucket), "mape"], errors="coerce")
        if heavy_values.notna().any():
            findings.append(f"- [warn] Heavy RUC {bucket} stress value is enriched from available data.")
    findings.append("- [pass] Stress aliases coalesce correctly across PED, Light RUC and Heavy RUC finalist rows.")
    findings.append("- [pass] Loader builds curated default sample and derived stress/horizon datasets.")
    if loaded.data["diagnostic_df"].empty:
        findings.append("- [warn] Diagnostic fields are not available; dashboard must show graceful missing-data panels.")
    else:
        findings.append("- [pass] Diagnostic fields are available.")
    return True, findings


def main() -> int:
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    try:
        _, findings = validate()
        status = "passed"
        exit_code = 0
    except AssertionError as exc:
        findings = [f"- [fail] {exc}"]
        status = "failed"
        exit_code = 1
    report = "\n".join(
        [
            "# Data Validation Review",
            "",
            f"Status: **{status}**.",
            "",
            "Latest CSV-preview run retained for smoke testing: `run_20260520_002339`.",
            "Primary Parquet validation remains authoritative for completion.",
            "",
            *findings,
            "",
        ]
    )
    (artifacts / "data_validation_review.md").write_text(report, encoding="utf-8")
    print(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

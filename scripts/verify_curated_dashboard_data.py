from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


EXPECTED = {
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

STALE_Q = {"PED": 5.49, "LIGHT_RUC": 11.55, "HEAVY_RUC": 12.38}
TOLERANCE = 0.01


def read_required(curated_dir: Path, name: str) -> pd.DataFrame:
    path = curated_dir / name
    if not path.exists():
        raise AssertionError(f"Missing curated file: {path}")
    return pd.read_csv(path, low_memory=False)


def assert_latest_values(finalist: pd.DataFrame) -> list[str]:
    lines = []
    for stream, expected in EXPECTED.items():
        rows = finalist[(finalist["stream"] == stream) & (finalist["model"] == expected["model"])]
        if len(rows) != 1:
            raise AssertionError(f"Expected exactly one latest finalist row for {stream}; found {len(rows)}")
        row = rows.iloc[0]
        for column in ["quarterly_mape", "annual_mape", "quarterly_bias_pct"]:
            actual = float(row[column])
            target = float(expected[column])
            if abs(actual - target) > TOLERANCE:
                raise AssertionError(f"{stream} {column}={actual:.5f} does not match {target:.5f}")
        stale = STALE_Q[stream]
        if abs(float(row["quarterly_mape"]) - stale) < 0.05:
            raise AssertionError(f"{stream} latest finalist still shows stale value around {stale}%")
        lines.append(
            f"- {row['stream_label']}: {row['quarterly_mape']:.5f}% quarterly, {row['annual_mape']:.5f}% annual."
        )
    return lines


def assert_landscape(landscape: pd.DataFrame) -> list[str]:
    if len(landscape) > 400:
        raise AssertionError(f"candidate_landscape_sample.csv has {len(landscape)} rows; hard cap is 400")
    required_roles = ["Recommended finalist", "Pure Schiff benchmark", "Distribution sample"]
    lines = [f"- Candidate landscape rows: {len(landscape):,}."]
    for stream in EXPECTED:
        subset = landscape[landscape["stream"] == stream]
        if subset.empty:
            raise AssertionError(f"Candidate landscape missing stream {stream}")
        for role in required_roles:
            if not (subset["candidate_role"] == role).any():
                raise AssertionError(f"Candidate landscape missing {role} for {stream}")
        if not (subset["is_recommended_finalist"].astype(bool)).any():
            raise AssertionError(f"Candidate landscape missing recommended finalist flag for {stream}")
        if not (subset["is_pure_schiff"].astype(bool)).any():
            raise AssertionError(f"Candidate landscape missing pure Schiff flag for {stream}")
        top_like = subset[subset["include_reason"].astype(str).str.contains("Top", case=False, na=False)]
        if len(top_like) < 15 and len(subset) >= 15:
            raise AssertionError(f"Candidate landscape has too few top/near-top candidates for {stream}")
    label_columns = ["stream_label", "model_short", "candidate_role", "include_reason", "source_family", "feature_set"]
    for column in label_columns:
        if column in landscape.columns and landscape[column].astype(str).str.contains("_", regex=False).any():
            raise AssertionError(f"User-facing candidate landscape label column contains underscores: {column}")
    return lines


def assert_schiff(schiff: pd.DataFrame) -> list[str]:
    bad_tokens = ["resid", "residual", "fixedblend", "solver", "top", "median", "mean", "convex", "ensemble", "blend"]
    for _, row in schiff.iterrows():
        text = " ".join(str(row.get(column, "")).lower() for column in schiff.columns)
        if "schiff_ols" not in str(row.get("model", "")).lower():
            raise AssertionError(f"Pure Schiff benchmark row is not SCHIFF_OLS: {row.get('model')}")
        if any(token in text for token in bad_tokens):
            raise AssertionError(f"Pure Schiff benchmark includes residual/blend/solver token: {row.get('model')}")
    for stream in EXPECTED:
        if not (schiff["stream"] == stream).any():
            raise AssertionError(f"Schiff benchmark missing stream {stream}")
    return [f"- Pure Schiff benchmark rows: {len(schiff):,}."]


def assert_stress(stress: pd.DataFrame) -> list[str]:
    expected_buckets = {"1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"}
    buckets = set(stress["stress_bucket"].dropna().astype(str))
    missing = expected_buckets - buckets
    if missing:
        raise AssertionError(f"Stress horizon missing expected buckets: {sorted(missing)}")
    return [f"- Stress buckets: {', '.join(sorted(buckets))}."]


def assert_ensemble(ensemble: pd.DataFrame) -> list[str]:
    if ensemble.empty:
        raise AssertionError("Ensemble composition is empty and no single-component fallback is documented.")
    if (pd.to_numeric(ensemble["weight"], errors="coerce") <= 0).any():
        raise AssertionError("Ensemble composition contains non-positive weights.")
    for stream in EXPECTED:
        if not (ensemble["stream"] == stream).any():
            raise AssertionError(f"Ensemble composition missing stream {stream}")
    return [f"- Positive ensemble weights: {len(ensemble):,}."]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curated-dir", default="artifacts/curated_data")
    args = parser.parse_args()
    curated_dir = Path(args.curated_dir)

    manifest_path = curated_dir / "curation_manifest.json"
    if not manifest_path.exists():
        raise AssertionError(f"Missing curation manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    finalist = read_required(curated_dir, "finalist_accuracy.csv")
    landscape = read_required(curated_dir, "candidate_landscape_sample.csv")
    schiff = read_required(curated_dir, "schiff_benchmark.csv")
    stress = read_required(curated_dir, "stress_horizon.csv")
    ensemble = read_required(curated_dir, "ensemble_composition.csv")

    report_lines = [
        "# Curated Dashboard Data Verification Report",
        "",
        f"Run: `{manifest.get('run_dir', '-')}`",
        "",
        "## Checks",
        "",
    ]
    report_lines.extend(assert_latest_values(finalist))
    report_lines.extend(assert_landscape(landscape))
    report_lines.extend(assert_schiff(schiff))
    report_lines.extend(assert_stress(stress))
    report_lines.extend(assert_ensemble(ensemble))
    report_lines.extend(["", "Status: passed."])

    (curated_dir / "verification_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))


if __name__ == "__main__":
    main()

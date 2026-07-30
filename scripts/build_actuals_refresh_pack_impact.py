"""Front-end / runtime-pack impact of the 2026Q1 actuals refresh.

Diffs the rebuilt runtime packs against the pre-refresh committed vintage
(snapshotted before the seed patch) and writes:

    front_end_impact.csv    decision-facing FY2026-FY2030 revenue/volume moves
    runtime_pack_diff.csv   per-file/per-series diff summary for both packs

Usage:
    python scripts/build_actuals_refresh_pack_impact.py --before <snapshot_dir>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKS = {
    "ensemble": ROOT / "data" / "current_revenue_outlook",
    "ar1": ROOT / "data" / "engine_ar1" / "current_revenue_outlook",
}
PREFIX = {"ensemble": "ens", "ar1": "ar1"}
FOCUS_SERIES = [
    "ped_vkt_per_capita",
    "light_ruc_net_km",
    "heavy_ruc_net_km",
    "gross_ped_revenue",
    "light_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "total_ruc_net_revenue",
    "net_fed_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
]


def _future_revenue(path: Path) -> tuple[pd.DataFrame, list[str]]:
    frame = pd.read_csv(path, low_memory=False)
    frame = frame.rename(columns={"stream": "series_id", "revenue_forecast_nzd": "value"})
    frame["FY"] = pd.to_numeric(
        frame.get("period", pd.Series(dtype=str)).astype(str).str.extract(r"FY(\d{4})")[0],
        errors="coerce",
    )
    keys = [c for c in ("scenario_name", "series_id", "FY", "fed_path", "component_type") if c in frame.columns]
    return frame, keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True, help="Snapshot dir with <prefix>_future_revenue_forecasts.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "actuals_refresh_2026q1")
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    impact_frames = []
    diff_rows = []
    for engine, pack_dir in PACKS.items():
        before_path = args.before / f"{PREFIX[engine]}_future_revenue_forecasts.csv"
        after_path = pack_dir / "future_revenue_forecasts.csv"
        before, keys = _future_revenue(before_path)
        after, _ = _future_revenue(after_path)
        merged = before.merge(after, on=keys, suffixes=("_before", "_after"), how="outer")
        a = pd.to_numeric(merged.get("value_before"), errors="coerce")
        b = pd.to_numeric(merged.get("value_after"), errors="coerce")
        merged["abs_change"] = b - a
        merged["pct_change"] = np.where(a.abs() > 0, (b - a) / a.abs() * 100.0, np.nan)
        merged["engine"] = engine
        focus = merged[
            merged["series_id"].astype(str).isin(FOCUS_SERIES)
            & merged["FY"].between(2026, 2030)
        ][keys + ["value_before", "value_after", "abs_change", "pct_change", "engine"]]
        impact_frames.append(focus)

        summary = (
            merged.assign(abs_pct=merged["pct_change"].abs())
            .groupby("series_id", dropna=False)
            .agg(rows=("abs_pct", "size"), max_abs_pct=("abs_pct", "max"), mean_abs_pct=("abs_pct", "mean"))
            .reset_index()
        )
        summary.insert(0, "engine", engine)
        summary.insert(1, "file", "future_revenue_forecasts.csv")
        diff_rows.append(summary)

        # Fan band envelope drift.
        fan_before = pd.read_csv(args.before / f"{PREFIX[engine]}_fan_band_rows.csv", low_memory=False)
        fan_after = pd.read_csv(pack_dir / "fan_band_rows.csv", low_memory=False)
        fan_keys = [c for c in ("scenario_name", "series_id", "period", "band", "band_label", "quantile", "FY", "june_year") if c in fan_before.columns and c in fan_after.columns]
        fb = fan_before.merge(fan_after, on=fan_keys, suffixes=("_before", "_after"), how="outer")
        for col in ("lower", "upper", "value"):
            cb, ca = f"{col}_before", f"{col}_after"
            if cb in fb.columns and ca in fb.columns:
                x = pd.to_numeric(fb[cb], errors="coerce")
                y = pd.to_numeric(fb[ca], errors="coerce")
                pct = np.where(x.abs() > 0, (y - x).abs() / x.abs() * 100.0, np.nan)
                diff_rows.append(
                    pd.DataFrame(
                        [
                            {
                                "engine": engine,
                                "file": "fan_band_rows.csv",
                                "series_id": f"fan:{col}",
                                "rows": int(np.isfinite(pct).sum()),
                                "max_abs_pct": float(np.nanmax(pct)) if np.isfinite(pct).any() else np.nan,
                                "mean_abs_pct": float(np.nanmean(pct)) if np.isfinite(pct).any() else np.nan,
                            }
                        ]
                    )
                )

    impact = pd.concat(impact_frames, ignore_index=True)
    impact.to_csv(out_dir / "front_end_impact.csv", index=False)
    diff = pd.concat(diff_rows, ignore_index=True)
    diff.to_csv(out_dir / "runtime_pack_diff.csv", index=False)

    headline = impact[
        impact["series_id"].eq("total_nltf_net_revenue")
    ].sort_values(["engine", "scenario_name", "FY"])
    print("TOTAL NLTF impact (FY2026-2030):")
    print(headline[["engine", "scenario_name", "FY", "value_before", "value_after", "pct_change"]].to_string(index=False))
    worst = impact.assign(abs_pct=impact["pct_change"].abs()).groupby("series_id")["abs_pct"].max()
    print()
    print("max |pct| by focus series:")
    print(worst.sort_values(ascending=False).round(4).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

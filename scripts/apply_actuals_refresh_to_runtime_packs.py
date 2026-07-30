"""Apply the 2026Q1 actuals refresh to both governed runtime packs.

Production-candidate operation (Candidate A, strict accepted-actual policy):

1. Patch each pack's committed ``revenue_chart_rows.csv`` seed so the
   quarterly inventory reflects the refreshed canonical history:
   - Light/Heavy quarterly forecast rows for quarters at or before their
     accepted 2026Q1 actuals are removed (superseded by history);
   - the accepted 2026Q1 actuals are appended as ``historical_actual`` rows;
   - the remaining Light/Heavy quarterly forecast values are re-promoted from
     the deterministic per-stream-seam replay of the committed scenario
     inputs (recursive lags now roll from the 2026Q1 actuals);
   - PED rows are untouched (its accepted exact cutoff remains 2025Q4 and its
     replay is byte-identical).
2. Rebuild the incumbent (ensemble) pack through the canonical route, which
   re-runs the replay gate, the MBU26 bridge, current-policy overlays, VFM
   composition, the FY2031-FY2050 post-model extrapolation and the
   uncertainty fan from the new seam.
3. Rebuild the AR(1) pack via its standard minting script.

The old 2026Q1 forecast rows and the diffs are recorded under
``artifacts/actuals_refresh_2026q1/``.

Usage: python scripts/apply_actuals_refresh_to_runtime_packs.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.forecast_runner import (  # noqa: E402
    quarter_sort_key,
    replay_forecast_from_scenario_inputs,
    stream_latest_accepted_periods,
)

INCUMBENT_DIR = ROOT / "data" / "current_revenue_outlook"
STREAM_SERIES = {
    "LIGHT_RUC": "light_ruc_net_km",
    "HEAVY_RUC": "heavy_ruc_net_km",
}
HISTORY_FILES = {
    "LIGHT_RUC": "light_ruc_inputs.parquet",
    "HEAVY_RUC": "heavy_ruc_inputs.parquet",
}


def june_year(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[-1])
    return year if quarter in (1, 2) else year + 1


def patch_seed_chart_rows(out_dir: Path) -> pd.DataFrame:
    """Patch the incumbent seed for the per-stream seam; returns the diff audit."""
    seed_path = INCUMBENT_DIR / "revenue_chart_rows.csv"
    chart_rows = pd.read_csv(seed_path, low_memory=False)
    latest = stream_latest_accepted_periods(ROOT)

    wide = pd.read_parquet(INCUMBENT_DIR / "scenario_inputs" / "scenario_input_wide.parquet")
    replay = replay_forecast_from_scenario_inputs(wide, repo_root=ROOT, engine="ensemble", seam="per_stream")
    report = replay.validation_report
    if not report.empty and not report["valid"].astype(bool).all():
        raise SystemExit(f"Per-stream replay validation failed:\n{report.to_string()}")
    future = replay.future_forecasts
    future = future[future["forecast_available"].astype(bool)]
    forecast_by_key = {
        (str(r.scenario_name), str(r.stream), str(r.target_period)): float(r.forecast)
        for r in future.itertuples(index=False)
    }

    audit_rows: list[dict[str, Any]] = []
    quarterly_forecast_mask = (
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("future_forecast")
        & chart_rows["stream"].astype(str).isin(STREAM_SERIES)
    )

    # 1. Drop superseded forecast quarters (period <= stream's accepted actual).
    superseded_mask = quarterly_forecast_mask & chart_rows.apply(
        lambda row: quarter_sort_key(str(row["period"])) <= quarter_sort_key(latest[str(row["stream"])])
        if quarterly_forecast_mask.loc[row.name]
        else False,
        axis=1,
    )
    for _, row in chart_rows[superseded_mask].iterrows():
        audit_rows.append(
            {
                "action": "removed_superseded_forecast_row",
                "scenario_name": row["scenario_name"],
                "stream": row["stream"],
                "period": row["period"],
                "old_value": row["value"],
                "new_value": np.nan,
                "reason": f"2026Q1 accepted actual supersedes the {row['period']} forecast row.",
            }
        )
    chart_rows = chart_rows[~superseded_mask].copy()

    # 2. Re-promote remaining Light/Heavy quarterly forecast values from the
    #    per-stream-seam replay (recursive lags roll from the Q1 actuals).
    quarterly_forecast_mask = (
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("future_forecast")
        & chart_rows["stream"].astype(str).isin(STREAM_SERIES)
    )
    patched = 0
    missing_replay: list[tuple[str, str, str]] = []
    for idx in chart_rows.index[quarterly_forecast_mask]:
        key = (
            str(chart_rows.at[idx, "scenario_name"]),
            str(chart_rows.at[idx, "stream"]),
            str(chart_rows.at[idx, "period"]),
        )
        if key not in forecast_by_key:
            missing_replay.append(key)
            continue
        old_value = float(chart_rows.at[idx, "value"])
        new_value = forecast_by_key[key]
        if old_value != new_value:
            audit_rows.append(
                {
                    "action": "repromoted_forecast_value",
                    "scenario_name": key[0],
                    "stream": key[1],
                    "period": key[2],
                    "old_value": old_value,
                    "new_value": new_value,
                    "reason": "Deterministic per-stream-seam replay from the refreshed canonical history.",
                }
            )
        chart_rows.at[idx, "value"] = new_value
        patched += 1
    if missing_replay:
        raise SystemExit(f"Replay produced no value for committed rows: {missing_replay[:5]} ...")

    # 3. Append the accepted 2026Q1 actuals as historical rows (template: the
    #    stream's latest committed historical row).
    for stream, series_id in STREAM_SERIES.items():
        hist_rows = chart_rows[
            chart_rows["time_grain"].astype(str).eq("quarterly")
            & chart_rows["row_type"].astype(str).eq("historical_actual")
            & chart_rows["series_id"].astype(str).eq(series_id)
        ]
        if hist_rows.empty:
            raise SystemExit(f"{stream}: no historical_actual template rows in the seed.")
        existing_periods = set(hist_rows["period"].astype(str))
        history = pd.read_parquet(ROOT / "data" / "model_input_history" / HISTORY_FILES[stream])
        targets = pd.to_numeric(history["target"], errors="coerce")
        accepted = history[targets.gt(0)]
        for _, actual in accepted.iterrows():
            period = str(actual["period"])
            if period in existing_periods:
                continue
            if quarter_sort_key(period) > quarter_sort_key(latest[stream]):
                continue
            template = hist_rows.loc[
                hist_rows["period"].astype(str).map(quarter_sort_key).idxmax()
            ].to_dict()
            template.update(
                {
                    "period": period,
                    "target_period": period,
                    "june_year": june_year(period),
                    "value": float(actual["target"]),
                    "source": "data/model_input_history/" + HISTORY_FILES[stream],
                    "source_cell": f"model_input_history:{period}",
                    "canonical_period_key": period,
                    "canonical_join_key": f"{stream}|{period}|historical_actual",
                }
            )
            chart_rows = pd.concat([chart_rows, pd.DataFrame([template])], ignore_index=True)
            audit_rows.append(
                {
                    "action": "appended_historical_actual_row",
                    "scenario_name": template.get("scenario_name", "historical_actual"),
                    "stream": stream,
                    "period": period,
                    "old_value": np.nan,
                    "new_value": float(actual["target"]),
                    "reason": "Accepted exact 2026Q1 actual appended to the quarterly inventory.",
                }
            )

    chart_rows.to_csv(seed_path, index=False)
    audit = pd.DataFrame(audit_rows)
    audit.to_csv(out_dir / "runtime_pack_seed_patch_audit.csv", index=False)
    print(f"seed patched: {patched} forecast values re-promoted, "
          f"{sum(a['action'] == 'removed_superseded_forecast_row' for a in audit_rows)} rows removed, "
          f"{sum(a['action'] == 'appended_historical_actual_row' for a in audit_rows)} actual rows appended")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "actuals_refresh_2026q1")
    parser.add_argument("--skip-ar1", action="store_true")
    args = parser.parse_args()
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    patch_seed_chart_rows(out_dir)

    print("[rebuild] incumbent (ensemble) runtime pack ...", flush=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "rebuild_current_revenue_outlook_runtime.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout[-4000:])
    if result.returncode != 0:
        sys.stderr.write(result.stderr[-8000:])
        return result.returncode

    if not args.skip_ar1:
        print("[rebuild] AR(1) runtime pack ...", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_ar1_runtime_pack.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        sys.stdout.write(result.stdout[-4000:])
        if result.returncode != 0:
            sys.stderr.write(result.stderr[-8000:])
            return result.returncode

    print("RUNTIME_PACKS_REFRESHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

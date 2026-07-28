"""Classify every AR(1) replay-seed key rather than chasing a patched count.

The AR(1) runtime build patches replayed PED quarterly forecasts into a seed
copied from the incumbent pack. When the H20 policy landed, the reported result
moved from "196 patched / 4 missing" to "36 patched / 164 missing". That is a
classification question, not a regression to be undone by restoring rows: the
current-model decision-facing path deliberately stops at H20, so its seed rows
stop with it, while the raw replay evidence keeps its full source horizon.

Every expected key is classified as one of:

  patched_supported              H1-H20, seed row exists, value patched
  intentionally_withheld_h21_plus  H21+, no decision-facing seed row by policy
  genuinely_missing_supported    H1-H20 but no seed row - a real defect
  source_not_required            replay produced a key outside the seed scope

Acceptance: no supported (H1-H20) key may be missing or reclassified as
withheld. Any genuinely missing key is reported individually, never absorbed
into the H21+ count.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.light_fleet_allocation import (  # noqa: E402
    EXTENDED_EVIDENCE_MAX_HORIZON,
    quarter_horizon,
)

OUT = ROOT / "artifacts" / "p0_light_fleet_fix"
OUT.mkdir(parents=True, exist_ok=True)
PACK = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"


def main() -> int:
    from model_dashboard.forecast_runner import replay_forecast_from_scenario_inputs

    scenario_inputs = pd.read_parquet(PACK / "scenario_inputs" / "scenario_input_wide.parquet")
    replay = replay_forecast_from_scenario_inputs(scenario_inputs, repo_root=ROOT, engine="ar1")
    ped = replay.future_forecasts
    ped = ped[ped["stream"].astype(str).eq("PED") & ped["forecast_available"].astype(bool)]

    # The seed is the INCUMBENT pack, which is what build_ar1_runtime_pack.py
    # copies before patching. Reading the AR(1) output instead would classify
    # the wrong frame.
    chart_rows = pd.read_csv(ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.csv")
    seed_mask = (
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("future_forecast")
        & chart_rows["series_id"].astype(str).eq("ped_vkt_per_capita")
    )
    seed_keys = {
        (str(chart_rows.at[idx, "scenario_name"]), str(chart_rows.at[idx, "period"]))
        for idx in chart_rows.index[seed_mask]
    }

    rows = []
    for record in ped.itertuples(index=False):
        scenario = str(getattr(record, "scenario_name", ""))
        period = str(getattr(record, "target_period", ""))
        horizon = quarter_horizon(period)
        supported = horizon <= EXTENDED_EVIDENCE_MAX_HORIZON
        has_seed = (scenario, period) in seed_keys
        if has_seed and supported:
            status, reason = "patched_supported", "H1-H20 seed row present and patched"
        elif not has_seed and not supported:
            status, reason = (
                "intentionally_withheld_h21_plus",
                "beyond H20: withheld from decision-facing output by the horizon policy; "
                "the raw replay value remains available as non-decision-facing audit",
            )
        elif not has_seed and supported:
            status, reason = (
                "genuinely_missing_supported",
                "H1-H20 replay key has no committed seed row - REAL DEFECT",
            )
        else:
            status, reason = (
                "source_not_required",
                "H21+ seed row exists but the decision-facing path does not publish it",
            )
        rows.append(
            {
                "scenario": scenario,
                "stream": "PED",
                "period": period,
                "horizon": horizon,
                "source_row_exists": True,
                "decision_facing_row_exists": has_seed,
                "status": status,
                "reason": reason,
            }
        )
    frame = pd.DataFrame(rows).sort_values(["scenario", "period"])
    frame.to_csv(OUT / "replay_seed_status.csv", index=False)

    counts = frame["status"].value_counts()
    print("=== replay seed status ===")
    print(counts.to_string())
    print(f"\ntotal expected replay keys: {len(frame)}")

    missing = frame[frame["status"].eq("genuinely_missing_supported")]
    print(f"\ngenuinely missing supported (H1-H20) keys: {len(missing)}")
    if not missing.empty:
        print(missing[["scenario", "period", "horizon"]].to_string(index=False))

    supported = frame[frame["horizon"].le(EXTENDED_EVIDENCE_MAX_HORIZON)]
    withheld_supported = supported[supported["status"].eq("intentionally_withheld_h21_plus")]
    print(f"\nsupported keys reclassified as withheld (must be 0): {len(withheld_supported)}")

    ok = missing.empty and withheld_supported.empty
    print("\nPASS" if ok else "\nFAIL: a supported key is missing or misclassified")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

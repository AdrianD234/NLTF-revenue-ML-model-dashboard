"""Mint the AR(1)-engine Revenue Outlook runtime pack under data/engine_ar1/.

Deterministic recipe:
1. Copy the incumbent pack's committed scenario inputs.
2. Replay the AR(1) engine over those inputs and patch the PED quarterly
   activity forecasts into a seed revenue_chart_rows.csv (Light/Heavy rows
   are byte-identical to the incumbent).
3. Run the standard runtime rebuild with engine="ar1" - the MBU26 bridge,
   lambda-migration, traces and manifest output hashes mint exactly as for
   the incumbent pack, and the replay gate verifies the committed PED rows
   against a fresh AR(1) replay.

Usage: python scripts/build_ar1_runtime_pack.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# This CLI mints the AR(1) pack; model-name resolution must follow the AR(1)
# engine so PED rows are stamped with the model that produced their values.
os.environ["DASHBOARD_ENGINE_DEFAULT"] = "ar1"

from model_dashboard.forecast_runner import replay_forecast_from_scenario_inputs  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    build_current_revenue_outlook_runtime_pack,
)
from pipeline.ar1_engine import AR1_MODEL_NAME  # noqa: E402

ALT_DIR = REPO_ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
SOURCE_DIR = REPO_ROOT / CURRENT_REVENUE_OUTLOOK_DIR


def main() -> int:
    ALT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Committed scenario inputs (workbook-hash-anchored) are shared.
    src_inputs = SOURCE_DIR / "scenario_inputs"
    dst_inputs = ALT_DIR / "scenario_inputs"
    if dst_inputs.exists():
        shutil.rmtree(dst_inputs)
    shutil.copytree(src_inputs, dst_inputs)

    # 2. Seed chart rows: incumbent rows with the PED quarterly forecasts
    #    replaced by the AR(1) replay per scenario.
    chart_rows = pd.read_csv(SOURCE_DIR / "revenue_chart_rows.csv")
    scenario_input_wide = pd.read_parquet(src_inputs / "scenario_input_wide.parquet")
    replay = replay_forecast_from_scenario_inputs(scenario_input_wide, repo_root=REPO_ROOT, engine="ar1")
    ped = replay.future_forecasts
    ped = ped[ped["stream"].astype(str).eq("PED") & ped["forecast_available"].astype(bool)]
    if ped.empty:
        raise SystemExit("AR(1) replay produced no PED forecasts; run scripts/build_ar1_engine_state.py first")
    forecast_by_key = {
        (str(row.scenario_name), str(row.target_period)): float(row.forecast)
        for row in ped.itertuples(index=False)
    }

    mask = (
        chart_rows["time_grain"].astype(str).eq("quarterly")
        & chart_rows["row_type"].astype(str).eq("future_forecast")
        & chart_rows["series_id"].astype(str).eq("ped_vkt_per_capita")
    )
    patched = 0
    for idx in chart_rows.index[mask]:
        key = (str(chart_rows.at[idx, "scenario_name"]), str(chart_rows.at[idx, "period"]))
        if key in forecast_by_key:
            chart_rows.at[idx, "value"] = forecast_by_key[key]
            if "model_id" in chart_rows.columns:
                chart_rows.at[idx, "model_id"] = AR1_MODEL_NAME
            patched += 1
    if patched == 0:
        raise SystemExit("No PED quarterly forecast rows were patched; seed schema unexpected")
    expected_keys = set(forecast_by_key)
    patched_keys = {
        (str(chart_rows.at[idx, "scenario_name"]), str(chart_rows.at[idx, "period"]))
        for idx in chart_rows.index[mask]
    }
    missing = expected_keys - patched_keys
    print(f"patched {patched} PED quarterly rows; replay keys without a committed row: {len(missing)}")
    chart_rows.to_csv(ALT_DIR / "revenue_chart_rows.csv", index=False)

    # 3. Standard runtime rebuild with the AR(1) replay gate.
    pack = build_current_revenue_outlook_runtime_pack(
        repo_root=REPO_ROOT,
        output_dir=ALT_DIR,
        promoted_by="ar1_engine_runtime_rebuild",
        engine="ar1",
    )
    print(f"AR1 runtime pack rebuilt: {pack.output_dir}")
    print(f"chart_rows={len(pack.revenue_chart_rows)} bridge_rows={len(pack.revenue_bridge_components)} future_rows={len(pack.future_revenue_forecasts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

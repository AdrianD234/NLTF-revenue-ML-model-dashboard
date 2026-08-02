"""Freeze the pre-amendment PR #15 outputs, so the amendment can be proved bounded.

Run BEFORE touching any VFM post-model calculation. Everything this captures
must be either unchanged afterwards (Current Base, Actuals, High population,
conflict paths, official vintages, PED, Heavy RUC, MVR, TUC, the uncertainty
band rows) or changed only in the ways the amendment authorises (the Light
class allocation from FY2031).

    .venv\\Scripts\\python.exe scripts\\build_vfm_long_run_extension_baseline.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402

OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
ENGINES = (
    ("ensemble", Path(CURRENT_REVENUE_OUTLOOK_DIR)),
    ("ar1", Path("data") / "engine_ar1" / "current_revenue_outlook"),
)
FED = "Current planned path"
TRACES = (
    "Actual", "Current finalist Base case",
    "Current finalist High population/comparison", "BEFU26 official", "MBU26 official",
)
# Everything the amendment must NOT move, plus the Light classes it may.
FROZEN_SERIES = (
    "ped_vkt_per_capita", "ped_volume", "gross_ped_revenue", "net_fed_revenue",
    "heavy_ruc_net_km", "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_km", "heavy_bev_ruc_net_revenue",
    "net_mvr_revenue", "tuc_net_revenue",
    "light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km",
    "light_ruc_net_revenue", "light_bev_ruc_net_revenue", "phev_ruc_net_revenue",
    "total_ruc_net_revenue", "total_fed_ruc_net_revenue", "total_nltf_net_revenue",
)
HASHED_FILES = (
    "data/revenue_outlook_uncertainty/uncertainty_band_rows.parquet",
    "data/revenue_outlook_uncertainty/june_year_basis.parquet",
    "data/revenue_outlook_uncertainty/manifest.json",
    "data/vfm_202405/vfm_vkt_shares.csv",
    "data/vfm_202405/manifest.json",
    "data/current_revenue_outlook/manifest.json",
    "data/current_revenue_outlook/revenue_chart_rows.csv",
    "data/current_revenue_outlook/revenue_line_reconciliation.csv",
    "data/current_revenue_outlook/revenue_stack_components.csv",
    "data/current_revenue_outlook/revenue_formula_residuals.csv",
    "data/engine_ar1/current_revenue_outlook/manifest.json",
    "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv",
)


def production_key(pack) -> RevenueScenarioComputationKey:
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
    return RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id=str(block.get("default_comparator_vintage_id") or "BEFU26"),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for engine, relative in ENGINES:
        directory = ROOT / relative
        if not directory.exists():
            continue
        pack = load_revenue_outlook_pack(directory, repo_root=ROOT)
        signature = revenue_outlook_signature(directory, ROOT)
        key = production_key(pack)
        sensitivity = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")

        for basis in (DEFAULT_EV_UPTAKE_MODE, "MoT VFM fast", "MoT VFM slow"):
            scenario_rows, *_ = app.cached_scenario_overlay_rows(
                signature, sensitivity, PED_BRIDGE_DEFAULT_MODE,
                key.replace(uptake_basis=basis), pack,
            )
            annual = scenario_rows[
                scenario_rows["time_grain"].astype(str).eq("june_year")
            ].copy()
            annual["FY"] = pd.to_numeric(annual["june_year"], errors="coerce")
            annual["numeric"] = pd.to_numeric(annual["value"], errors="coerce")
            annual = annual.dropna(subset=["FY", "numeric"])
            annual = annual[annual["series_id"].astype(str).isin(FROZEN_SERIES)]
            for _index, row in annual.iterrows():
                rows.append(
                    {
                        "engine": engine,
                        "uptake_basis": basis,
                        "scenario_name": str(row["scenario_name"]),
                        "scenario_role": str(row.get("scenario_role", "")),
                        "trace_name": str(row.get("trace_name", "")),
                        "series_id": str(row["series_id"]),
                        "FY": int(row["FY"]),
                        "fed_path": str(row.get("fed_path", "")),
                        "forecast_segment": str(row.get("forecast_segment", "")),
                        "value": float(row["numeric"]),
                    }
                )

    baseline = pd.DataFrame(rows).drop_duplicates(
        subset=["engine", "uptake_basis", "scenario_name", "series_id", "FY", "fed_path"]
    )
    baseline.to_csv(OUT / "pre_vfm_long_run_extension_baseline.csv", index=False)

    hashes = []
    for relative in HASHED_FILES:
        path = ROOT / relative
        hashes.append(
            {
                "path": relative,
                "exists": path.exists(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "",
                "bytes": path.stat().st_size if path.exists() else 0,
            }
        )
    pd.DataFrame(hashes).to_csv(OUT / "pre_vfm_long_run_extension_hashes.csv", index=False)

    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    manifest = {
        "pre_amendment_head": "ac144a40d9eecf32c58533e6a916522fdb3abba5",
        "pr": 15,
        "baseline_rows": int(len(baseline)),
        "engines": [engine for engine, _relative in ENGINES],
        "uptake_bases": [DEFAULT_EV_UPTAKE_MODE, "MoT VFM fast", "MoT VFM slow"],
        "frozen_series": list(FROZEN_SERIES),
        "fy_range": [int(baseline["FY"].min()), int(baseline["FY"].max())],
        "runtime_pack_manifest": {
            key: value
            for key, value in (pack.manifest or {}).items()
            if key in ("period_rule", "official_vintages", "runtime_cutoff", "input_history_vintage")
        },
    }
    (OUT / "pre_vfm_long_run_extension_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )

    print(f"baseline rows: {len(baseline)}  FY {baseline['FY'].min()}-{baseline['FY'].max()}")
    print(f"engines: {sorted(set(baseline['engine']))}")
    print(f"bases:   {sorted(set(baseline['uptake_basis']))}")
    post = baseline[baseline["FY"].ge(2031)]
    light = post[post["series_id"].eq("light_ruc_net_km")]
    spread = light.groupby(["engine", "FY"])["value"].nunique()
    print(
        "\nFY2031+ light_ruc_net_km distinct values across the three bases "
        f"(1 = collapsed): {sorted(set(spread))}"
    )


if __name__ == "__main__":
    main()

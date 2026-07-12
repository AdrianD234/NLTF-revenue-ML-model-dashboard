"""Extract MoT Vehicle Fleet Model (VFM 202405) VKT power-type shares.

Reads the vendored VFM outputs workbook and materializes June-year share
curves used by the EV/PHEV uptake lever engine:

- light RUC pool shares (conventional diesel+diesel hybrid / BEV / PHEV of
  the light vehicles that pay RUC), per EV uptake scenario
- heavy truck BEV VKT share, per scenario
- light petrol pool VKT (petrol + petrol hybrid), per scenario

Calendar years are mapped to June years as FY(t) = mean(calendar t-1, t).
Output: data/vfm_202405/vfm_vkt_shares.csv plus a manifest recording the
workbook sha256 so the derivation is reproducible byte-for-byte.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "data" / "source_workbooks" / "VFM202405_outputs_summary_V3.xlsx"
DOCUMENTATION = ROOT / "data" / "source_workbooks" / "Vehicle-Fleet-Model-Documentation_202405_v7.pdf"
OUTPUT_DIR = ROOT / "data" / "vfm_202405"

RAW_COLUMNS = [
    "scenario", "light_heavy", "electric", "veh_type", "power_type",
    "new_used", "veh_size", "year", "vehicles", "vkt", "fuel_use",
    "kwh_use", "fuel_co2", "electricity_co2",
]
SCENARIOS = ("Base_EV", "Fast_EV", "Slow_EV")
FY_RANGE = range(2025, 2051)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def to_june_year(calendar: pd.Series) -> dict[int, float]:
    return {fy: (calendar.get(fy - 1, float("nan")) + calendar.get(fy, float("nan"))) / 2 for fy in FY_RANGE}


def main() -> None:
    raw = pd.read_excel(WORKBOOK, sheet_name="Raw data (wem202405)", skiprows=2, header=None, names=RAW_COLUMNS)
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce")
    raw["vkt"] = pd.to_numeric(raw["vkt"], errors="coerce")

    rows: list[dict[str, object]] = []
    light = raw[raw["veh_type"].isin(["LPV", "LCV"])]
    trucks = raw[raw["veh_type"].isin(["M Truck", "H Truck"])]
    for scenario in SCENARIOS:
        by_power = light[light["scenario"].eq(scenario)].groupby(["year", "power_type"])["vkt"].sum().unstack(fill_value=0)
        conventional = by_power.get("Diesel", 0) + by_power.get("Hybrid diesel", 0)
        bev = by_power.get("Electric", 0)
        phev = by_power.get("Petrol plug-in", 0)
        petrol = by_power.get("Petrol", 0) + by_power.get("Hybrid petrol", 0)
        pool = conventional + bev + phev
        heavy_by_power = trucks[trucks["scenario"].eq(scenario)].groupby(["year", "power_type"])["vkt"].sum().unstack(fill_value=0)
        heavy_total = heavy_by_power.sum(axis=1)
        heavy_bev = heavy_by_power.get("Electric", 0) / heavy_total

        light_total = light[light["scenario"].eq(scenario)].groupby("year")["vkt"].sum()
        series = {
            "light_ruc_conventional_share": to_june_year(conventional / pool),
            "light_ruc_bev_share": to_june_year(bev / pool),
            "light_ruc_phev_share": to_june_year(phev / pool),
            "heavy_bev_vkt_share": to_june_year(heavy_bev),
            "light_petrol_vkt_million_km": to_june_year(petrol / 1e6),
            "light_petrol_share_of_light_vkt": to_june_year(petrol / light_total),
            # raw class volumes (million km) so downstream views can present
            # MoT's six-row taxonomy in levels, not just pool shares
            "light_ruc_conventional_million_km": to_june_year(conventional / 1e6),
            "light_ruc_bev_million_km": to_june_year(bev / 1e6),
            "light_ruc_phev_million_km": to_june_year(phev / 1e6),
            "heavy_total_million_km": to_june_year(heavy_total / 1e6),
            "heavy_bev_million_km": to_june_year(heavy_by_power.get("Electric", 0) / 1e6),
        }
        for fy in FY_RANGE:
            rows.append({"scenario": scenario, "june_year": fy, **{name: values[fy] for name, values in series.items()}})

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    output_csv = OUTPUT_DIR / "vfm_vkt_shares.csv"
    frame.to_csv(output_csv, index=False, lineterminator="\n", float_format="%.6f")

    manifest = {
        "schema_version": "vfm-uptake-shares-v2",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_workbook": {
            "repo_relative_path": "data/source_workbooks/VFM202405_outputs_summary_V3.xlsx",
            "sha256": sha256(WORKBOOK),
        },
        "source_documentation": {
            "repo_relative_path": "data/source_workbooks/Vehicle-Fleet-Model-Documentation_202405_v7.pdf",
            "sha256": sha256(DOCUMENTATION),
        },
        "derivation": (
            "Light RUC pool = diesel + diesel-hybrid (conventional) + battery-electric (BEV) "
            "+ petrol plug-in (PHEV) VKT for LPV+LCV; shares are of that pool. Heavy BEV share "
            "is electric VKT over all M+H truck VKT. June-year FY(t) = mean(calendar t-1, t)."
        ),
        "output": {
            "repo_relative_path": "data/vfm_202405/vfm_vkt_shares.csv",
            "sha256": sha256(output_csv),
            "rows": int(len(frame)),
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_csv} ({len(frame)} rows) and manifest.json")


if __name__ == "__main__":
    main()

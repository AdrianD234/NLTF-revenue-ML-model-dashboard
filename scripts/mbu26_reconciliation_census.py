"""Workstream A, Phase A1: MBU26 reconciliation census and input availability.

Establishes the exact displayed Current-minus-MBU26 difference for FY2026-FY2030
and determines, series by series, whether a like-for-like common-input
counterfactual can actually be reproduced from committed content.

This phase deliberately does NOT attempt the Shapley driver decomposition. That
requires knowing which MBU26 drivers are recoverable, which is precisely what
this census establishes. Building the decomposition first would mean inventing
the inputs it depends on.

No model, fitted state, governed pack or checkpoint is altered. Read-only.

Engine: AR(1), the authoritative production engine.

Usage::

    python scripts/mbu26_reconciliation_census.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AR1_PACK = REPO_ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
FY_RANGE = (2026, 2030)
CURRENT = "current_basecase"
OFFICIAL = "mbu26_official"

# Series the reconciliation must cover, with how each is produced.
SERIES_CLASSIFICATION = {
    "ped_vkt_per_capita": ("model", "AR(1) PED econometric forecast"),
    "light_petrol_vkt": ("bridge", "PED VKTpc x population x EV/PHEV migration"),
    "ped_volume": ("bridge", "light petrol VKT x MBU26 fuel intensity"),
    "gross_ped_revenue": ("bridge", "PED litres x MBU26 effective rate"),
    "gross_fed_revenue": ("bridge", "gross PED plus fixed LPG/CNG rows"),
    "net_fed_revenue": ("formula", "gross_fed_revenue - fed_refunds"),
    "light_ruc_net_km": ("model+bridge", "Light RUC finalist total pool, class-allocated"),
    "light_bev_ruc_net_km": ("bridge", "EV/PHEV migration allocation from the light pool"),
    "phev_ruc_net_km": ("bridge", "EV/PHEV migration allocation from the light pool"),
    "heavy_ruc_net_km": ("model", "Heavy RUC finalist forecast"),
    "light_ruc_net_revenue": ("bridge", "class km x MBU26 effective class rate"),
    "light_bev_ruc_net_revenue": ("bridge", "class km x MBU26 effective class rate"),
    "phev_ruc_net_revenue": ("bridge", "class km x MBU26 effective class rate"),
    "heavy_ruc_net_revenue": ("bridge", "heavy km x MBU26 effective rate"),
    "total_ruc_net_revenue": ("formula", "ruc_revenue_net_admin - ruc_refunds"),
    "net_mvr_revenue": ("fixed", "inherited from MBU26 unchanged"),
    "total_nltf_net_revenue": ("formula", "sum of governed revenue lines"),
}

# Drivers each stream depends on, and whether an MBU26 vintage is recoverable.
DRIVER_MATRIX = [
    # driver, streams, current source, mbu26 source, reproducible
    ("real GDP", "PED / Light RUC / Heavy RUC",
     "Treasury BEFU26 overlay (committed CSV)",
     "not published in the MBU26 source pack", "no"),
    ("population", "PED (per-capita denominator)",
     "Treasury BEFU26 June anchors, log-linear interpolation",
     "not published in the MBU26 source pack", "no"),
    ("unemployment rate", "PED",
     "scenario input workbook",
     "not published in the MBU26 source pack", "no"),
    ("real petrol price", "PED",
     "scenario input workbook",
     "not published in the MBU26 source pack", "no"),
    ("real diesel price", "Light RUC",
     "scenario input workbook",
     "not published in the MBU26 source pack", "no"),
    ("real Light RUC price", "Light RUC",
     "scenario input workbook",
     "not published in the MBU26 source pack", "no"),
    ("real Heavy RUC price", "Heavy RUC",
     "scenario input workbook",
     "not published in the MBU26 source pack", "no"),
    ("PED effective rate", "PED revenue bridge",
     "inherited from MBU26", "MBU26 official annual (revenue / volume)", "yes"),
    ("class RUC effective rates", "Light/Heavy RUC revenue bridge",
     "inherited from MBU26", "MBU26 official annual (revenue / km)", "yes"),
    ("fuel intensity (litres per km)", "PED volume bridge",
     "inherited from MBU26", "MBU26 official annual (litres / VKT)", "yes"),
    ("EV/PHEV class allocation", "Light RUC class mix",
     "MoT VFM 202405 uptake levers", "MBU26 official class km rows", "yes"),
    ("refunds and admin", "net revenue formulas",
     "inherited from MBU26", "MBU26 official annual", "yes"),
    ("MVR / TUC / LPG / CNG", "fixed revenue rows",
     "inherited from MBU26", "MBU26 official annual", "yes"),
    ("judgemental adjustment", "any",
     "none applied", "unknown; not disclosed in the workbook", "no"),
]


def _june_year_rows(pack: Path) -> pd.DataFrame:
    frame = pd.read_parquet(pack / "revenue_chart_rows.parquet")
    frame = frame[frame["time_grain"].astype(str).eq("june_year")].copy()
    frame["june_year"] = pd.to_numeric(frame["june_year"], errors="coerce")
    return frame[frame["june_year"].between(*FY_RANGE)]


def build_gap(pack: Path) -> pd.DataFrame:
    rows = _june_year_rows(pack)
    cur = rows[rows["scenario_name"].astype(str).eq(CURRENT)]
    off = rows[rows["scenario_name"].astype(str).eq(OFFICIAL)]
    keys = ["series_id", "june_year"]
    merged = cur[keys + ["value", "value_unit"]].merge(
        off[keys + ["value"]], on=keys, how="outer", suffixes=("_current", "_mbu26")
    )
    a = pd.to_numeric(merged["value_current"], errors="coerce")
    b = pd.to_numeric(merged["value_mbu26"], errors="coerce")
    merged["absolute_difference"] = a - b
    merged["percent_difference"] = np.where(
        b.abs() > 0, (a - b) / b.abs() * 100.0, np.nan
    )
    merged["production_class"] = merged["series_id"].map(
        lambda s: SERIES_CLASSIFICATION.get(str(s), ("unclassified", ""))[0]
    )
    merged["how_produced"] = merged["series_id"].map(
        lambda s: SERIES_CLASSIFICATION.get(str(s), ("", "unclassified"))[1]
    )
    merged["common_input_counterfactual"] = np.where(
        merged["production_class"].isin(["fixed", "formula"]),
        "not_required_inherited_or_derived",
        "blocked_mbu26_drivers_unavailable",
    )
    return merged.sort_values(["series_id", "june_year"]).reset_index(drop=True)


def build_driver_matrix() -> pd.DataFrame:
    return pd.DataFrame(
        DRIVER_MATRIX,
        columns=[
            "driver",
            "streams_affected",
            "current_model_source",
            "mbu26_source",
            "mbu26_vintage_reproducible",
        ],
    )


def _md_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    out = frame.copy()
    for c in out.columns:
        out[c] = out[c].map(lambda v: f"{v:,.2f}" if isinstance(v, float) else str(v))
    head = "| " + " | ".join(out.columns) + " |"
    div = "|" + "|".join("---" for _ in out.columns) + "|"
    body = ["| " + " | ".join(r) + " |" for r in out.itertuples(index=False, name=None)]
    return "\n".join([head, div, *body])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "outputs" / "mbu26_reconciliation"
    )
    args = parser.parse_args(argv)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    gap = build_gap(AR1_PACK)
    gap.to_csv(out / "mbu26_gap_by_stream_fy.csv", index=False)

    drivers = build_driver_matrix()
    drivers.to_csv(out / "driver_vintage_matrix.csv", index=False)

    total = gap[gap["series_id"].eq("total_nltf_net_revenue")][
        ["june_year", "value_current", "value_mbu26", "absolute_difference", "percent_difference"]
    ]
    revenue = gap[
        gap["series_id"].isin(
            ["net_fed_revenue", "total_ruc_net_revenue", "net_mvr_revenue", "total_nltf_net_revenue"]
        )
    ]
    by_stream = (
        revenue.groupby("series_id")
        .agg(
            fy2026_diff=("absolute_difference", lambda s: s.iloc[0] if len(s) else np.nan),
            max_abs_diff=("absolute_difference", lambda s: s.abs().max()),
            max_abs_pct=("percent_difference", lambda s: s.abs().max()),
        )
        .reset_index()
    )

    n_blocked = int(gap["common_input_counterfactual"].eq("blocked_mbu26_drivers_unavailable").sum())
    reproducible = int(drivers["mbu26_vintage_reproducible"].eq("yes").sum())

    report = [
        "# MBU26 reconciliation census (Workstream A, Phase A1)",
        "",
        "Engine: AR(1), the authoritative production engine. Base case,",
        "FY2026-FY2030. Read-only: no model, pack or checkpoint was altered.",
        "",
        "## The headline difference",
        "",
        "Total NLTF net revenue, current model minus MBU26 official:",
        "",
        _md_table(total),
        "",
        "## Where the difference sits",
        "",
        _md_table(by_stream),
        "",
        "## Driver availability - the finding that governs everything else",
        "",
        f"Of {len(drivers)} driver families, **{reproducible} are reproducible** for a",
        "common-input counterfactual and the rest are not.",
        "",
        _md_table(drivers),
        "",
        "The reproducible ones are exactly those the current model already",
        "**inherits** from MBU26: effective rates, fuel intensity, class allocation,",
        "refunds, admin and the fixed revenue rows. They cannot explain any of the",
        "difference, because both sides already use identical values for them.",
        "",
        "Every driver that could actually move the two paths apart - GDP,",
        "population, unemployment, petrol, diesel and RUC prices - is **not",
        "published in the MBU26 source pack**. The workbook reports MBU26's",
        "*outputs*, not the assumptions that produced them.",
        "",
        "## What this means for the decomposition",
        "",
        f"{n_blocked} of {len(gap)} series/FY cells cannot support a like-for-like",
        "common-input counterfactual from committed content. The requested",
        "counterfactual C - *current finalist under the fullest reproducible MBU26",
        "driver vintage* - **cannot be constructed** for the drivers that matter.",
        "",
        "That is a finding, not a failure to execute. It means the question",
        "'would the current model still sit below MBU26 on identical drivers?'",
        "cannot be answered from this repository as it stands. Answering it",
        "requires MoT to supply the MBU26 driver assumptions, which are not in",
        "the published workbook.",
        "",
        "## Recommended next step",
        "",
        "The decomposition should therefore be built in two explicitly separated",
        "levels, as follows.",
        "",
        "**Financial decomposition** - which activity and revenue lines account",
        "for the dollar difference. This closes exactly and is fully computable",
        "from committed content. It is the honest deliverable.",
        "",
        "**Causal decomposition** - why MBU26 produced those quantities. This",
        "must carry an explicit `unknown_official_model_inputs_or_judgment`",
        "term. Attempting to attribute the gap to GDP or price assumptions we",
        "cannot observe would be inventing the inputs.",
        "",
        "Do not proceed to a Shapley driver decomposition over unavailable",
        "drivers. Request the MBU26 driver vintage from MoT, or scope the",
        "decomposition to the financial level and label the residual honestly.",
        "",
        "## Series not available at June-year grain",
        "",
        "`light_petrol_vkt` and `current_light_ruc_total_modelled_km` exist in",
        "the MBU26 annual spine and the quarterly bridge but not in the",
        "June-year chart rows for both scenarios, so they are absent from this",
        "census. They are recoverable from the bridge if the financial",
        "decomposition needs them.",
        "",
    ]
    (out / "mbu26_reconciliation_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    print(total.to_string(index=False))
    print()
    print(f"driver families reproducible: {reproducible} / {len(drivers)}")
    print(f"series/FY cells blocked      : {n_blocked} / {len(gap)}")
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Four-layer publication diagnosis for the two PED activity series.

The merged workshop validation concluded that Light petrol VKT "has no Current
path after FY2030" by inspecting the final chart path. That is true of the
*generic persisted* chart rows but not of the rendered view, and it says
nothing about whether governed values exist upstream. This script separates
the four layers that were being conflated, for both target series:

  L1  generic persisted chart rows        data/*/revenue_chart_rows.parquet
  L2  additive view-time rows             cached_scenario_overlay_rows +
                                          _append_missing_official_rows
  L3  governed post-model source          line reconciliation + extrapolation
  L4  final selected/rendered rows        _filter_series_rows_with_fallback

Run:  python scripts/diagnose_ped_activity_publication.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard import revenue_outlook_series_coverage as coverage  # noqa: E402
from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: E402
from model_dashboard.official_vintage import bridge_vintage_id_from_manifest  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    revenue_outlook_signature,
)

TARGETS = ("ped_vkt_per_capita", "light_petrol_vkt")
LABELS = {"ped_vkt_per_capita": "PED VKT per capita", "light_petrol_vkt": "Light petrol VKT"}
ENGINES = ("ensemble", "ar1")
OUT = ROOT / "artifacts" / "revenue_outlook_ped_activity_2050"


def _span(frame: pd.DataFrame, column: str = "june_year") -> str:
    """Non-vacuous span label, or an explicit empty marker."""
    if frame is None or frame.empty:
        return "EMPTY"
    if column == "june_year" and column in frame.columns:
        years = pd.to_numeric(frame[column], errors="coerce").dropna()
        if years.empty:
            return "EMPTY"
        return f"FY{years.min():.0f}..FY{years.max():.0f} (n={len(frame)})"
    periods = frame.get("period", pd.Series(dtype=str)).astype(str)
    periods = periods[periods.ne("")]
    if periods.empty:
        return "EMPTY"
    return f"{periods.min()}..{periods.max()} (n={len(frame)})"


def _overlay_rows(engine: str):
    """The real view-time overlay rows, exactly as the page builds them."""
    pack_dir = ROOT / engine_revenue_outlook_dir(engine)
    signature = revenue_outlook_signature(pack_dir, ROOT)
    pack = app.cached_load_revenue_outlook_pack(
        str(pack_dir), str(ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    block = pack.manifest.get("official_vintages", {})
    key = app.RevenueScenarioComputationKey(
        engine=engine,
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state="published",
        official_fed_policy_state="published",
        ped_bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        bridge_vintage_id=str(bridge_vintage_id_from_manifest(pack.manifest, ROOT) or ""),
        official_comparator_vintage_id=str(
            block.get("default_comparator_vintage_id") or "BEFU26"
        ),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )
    sens = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    rows, *_ = app.cached_scenario_overlay_rows(
        signature, sens, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    official_scenario, official_overlay = app._official_vintage_filter_for_key(key)
    rows = app._filter_official_vintage_rows(rows, official_scenario, official_overlay)
    rows = app._append_missing_official_rows(rows, official_scenario, official_overlay)
    return pack, rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    for engine in ENGINES:
        pack_dir = ROOT / engine_revenue_outlook_dir(engine)

        # ---------------------------------------- L1 generic persisted rows
        persisted = pd.read_parquet(pack_dir / "revenue_chart_rows.parquet")
        # ---------------------------------------- L3 governed source rows
        line = pd.read_parquet(pack_dir / "revenue_line_reconciliation.parquet")
        # ---------------------------------------- L2 view-time overlay rows
        pack, overlay = _overlay_rows(engine)

        for series in TARGETS:
            label = LABELS[series]

            l1 = persisted[persisted["series_id"].astype(str).eq(series)]
            l1_cur = l1[l1["scenario_role"].astype(str).isin(["basecase", "comparison"])]
            l1_ann = l1_cur[l1_cur["time_grain"].astype(str).eq("june_year")]
            l1_qtr = l1_cur[l1_cur["time_grain"].astype(str).eq("quarterly")]

            l2 = overlay[overlay["series_id"].astype(str).eq(series)]
            l2_cur = l2[l2["scenario_role"].astype(str).isin(["basecase", "comparison"])]
            l2_ann = l2_cur[l2_cur["time_grain"].astype(str).eq("june_year")]
            l2_off = l2[l2["scenario_role"].astype(str).eq("official_comparator")]
            l2_act = l2[l2["scenario_role"].astype(str).eq("actual")]

            l3 = line[line["series_id"].astype(str).eq(series)]
            l3_cur = l3[l3["source_path"].astype(str).str.startswith("Current finalist")]
            l3_post = l3_cur[l3_cur.get("forecast_segment", pd.Series("", index=l3_cur.index))
                             .astype(str).eq("post_model_extrapolation")]

            # ------------------------------------ L4 final rendered rows
            l4_ann, _ = app._filter_series_rows_with_fallback(
                overlay, label, "june_year", "Current planned path",
                (app.BASE_TRACE_NAME if hasattr(app, "BASE_TRACE_NAME")
                 else "Current finalist Base case",),
                "published",
                pack_dir=str(pack.output_dir),
            )
            l4_qtr, used_fb = app._filter_series_rows_with_fallback(
                overlay, label, "quarterly", "Current planned path",
                (app.BASE_TRACE_NAME if hasattr(app, "BASE_TRACE_NAME")
                 else "Current finalist Base case",),
                "published",
                pack_dir=str(pack.output_dir),
            )

            records.append(
                {
                    "engine": engine,
                    "series_id": series,
                    "L1_persisted_current_annual": _span(l1_ann),
                    "L1_persisted_current_quarterly": _span(l1_qtr, "period"),
                    "L2_viewtime_current_annual": _span(l2_ann),
                    "L2_viewtime_official": _span(l2_off),
                    "L2_viewtime_actual": _span(l2_act),
                    "L3_line_recon_current": _span(l3_cur, "period"),
                    "L3_post_model_rows": _span(l3_post, "period"),
                    "L4_rendered_annual": _span(l4_ann),
                    "L4_rendered_quarterly": _span(l4_qtr, "period"),
                    "L4_quarterly_used_fallback": bool(used_fb),
                }
            )

    frame = pd.DataFrame(records)
    frame.to_csv(OUT / "publication_layer_coverage.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_colwidth", 40):
        print(frame.to_string(index=False))
    print(f"\nwrote {OUT / 'publication_layer_coverage.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

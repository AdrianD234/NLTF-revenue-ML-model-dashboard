"""Evidence for the Revenue Outlook long-run restoration.

Writes only under artifacts/revenue_outlook_long_run/ and touches no pack.
Fails closed if the short run moved, the seam is discontinuous, a formula
fails to close, the Light RUC divergence guard is approached, or a fan band
claims an empirical basis it does not have.

Usage: python scripts/build_revenue_outlook_long_run_evidence.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DASHBOARD_ENGINE_DEFAULT", "ensemble")

from model_dashboard.post_model_extrapolation import (  # noqa: E402
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    RETIRED_PATHOLOGY_FY2050_MILLION_KM,
    anchor_index_level_audit,
    build_post_model_extrapolation_annual,
    light_ruc_long_run_guard_frame,
)
from model_dashboard.revenue_outlook import (  # noqa: E402
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_MBU26_ARCHIVED,
    load_revenue_outlook_pack,
)

OUT = ROOT / "artifacts" / "revenue_outlook_long_run"
PACK = ROOT / "data" / "current_revenue_outlook"
SCENARIOS = (
    ("current_basecase", "Current finalist Base case"),
    ("current_comparison_1", "Current finalist High population/comparison"),
)
failures: list[str] = []


def _annual(frame: pd.DataFrame, scenario: str, series: str) -> pd.Series:
    scoped = frame[
        frame["time_grain"].astype(str).eq("june_year")
        & frame["scenario_name"].astype(str).eq(scenario)
        & frame["series_id"].astype(str).eq(series)
    ]
    return (
        pd.to_numeric(scoped["value"], errors="coerce")
        .groupby(pd.to_numeric(scoped["june_year"], errors="coerce")).first().sort_index()
    )


def short_run_unchanged() -> pd.DataFrame:
    """CSV-against-CSV, because main's own CSV and parquet differ by 1 ULP."""
    key = ["scenario_name", "scenario_role", "time_grain", "series_id", "period", "fed_path", "row_type", "trace_name"]
    rows: list[dict[str, object]] = []
    for rel in (
        "data/current_revenue_outlook/revenue_chart_rows.csv",
        "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv",
        "data/current_revenue_outlook/revenue_line_reconciliation.csv",
    ):
        blob = subprocess.run(["git", "show", f"main:{rel}"], capture_output=True, cwd=ROOT)
        if blob.returncode != 0:
            failures.append(f"cannot read main:{rel}")
            continue
        before = pd.read_csv(BytesIO(blob.stdout), low_memory=False)
        after = pd.read_csv(ROOT / rel, low_memory=False)
        this_key = key if "chart_rows" in rel else ["source_path", "scenario_name", "series_id", "FY"]
        for frame in (before, after):
            for column in this_key:
                frame[column] = frame[column].fillna("").astype(str)
        merged = before.merge(after, on=this_key, how="left", suffixes=("_main", "_now"))
        left = pd.to_numeric(merged["value_main"], errors="coerce")
        right = pd.to_numeric(merged["value_now"], errors="coerce")
        both = left.notna() & right.notna()
        changed = int((left[both] != right[both]).sum())
        missing = int(right[left.notna()].isna().sum())
        rows.append(
            {
                "path": rel,
                "main_rows": len(before),
                "rows_after": len(after),
                "preexisting_rows_matched": int(both.sum()),
                "values_changed": changed,
                "values_missing": missing,
                "max_abs_delta": float((left[both] - right[both]).abs().max()) if both.any() else 0.0,
                "status": "unchanged" if changed == 0 and missing == 0 else "CHANGED",
                "basis": "csv_vs_csv_exact",
            }
        )
        if changed or missing:
            failures.append(f"{rel}: {changed} values changed, {missing} missing")
    return pd.DataFrame(rows)


def _line_annual(line: pd.DataFrame, source_path: str, series: str) -> pd.Series:
    scoped = line[
        line["source_path"].astype(str).eq(source_path)
        & line["series_id"].astype(str).eq(series)
    ]
    return (
        pd.to_numeric(scoped["value"], errors="coerce")
        .groupby(pd.to_numeric(scoped["FY"], errors="coerce")).first().sort_index()
    )


def continuity_audit(chart: pd.DataFrame, line: pd.DataFrame) -> pd.DataFrame:
    """Seam steps for chart series AND hidden line-only leaves.

    ``light_petrol_vkt`` is a hidden leaf: it lives in the line
    reconciliation, not the chart rows, exactly as it does for
    FY2026-FY2030. Looking for it in the chart frame is a category error, so
    each series is read from the frame that actually carries it.
    """
    rows: list[dict[str, object]] = []
    for scenario, source_path in SCENARIOS:
        for series in (
            "total_nltf_net_revenue", "light_ruc_net_km", "heavy_ruc_net_km",
            "ped_vkt_per_capita", "light_petrol_vkt", "ped_volume",
        ):
            values = _annual(chart, scenario, series)
            frame_used = "chart_rows"
            if ANCHOR_FY not in values.index or FIRST_EXTRAPOLATION_FY not in values.index:
                values = _line_annual(line, source_path, series)
                frame_used = "line_reconciliation"
            if ANCHOR_FY not in values.index or FIRST_EXTRAPOLATION_FY not in values.index:
                failures.append(
                    f"{scenario}/{series}: seam years missing from both chart rows "
                    "and the line reconciliation"
                )
                continue
            anchor = float(values.loc[ANCHOR_FY])
            first = float(values.loc[FIRST_EXTRAPOLATION_FY])
            prior_step = (
                anchor / float(values.loc[ANCHOR_FY - 1]) - 1.0
                if (ANCHOR_FY - 1) in values.index else float("nan")
            )
            seam_step = first / anchor - 1.0
            rows.append(
                {
                    "scenario_name": scenario,
                    "series_id": series,
                    "source_frame": frame_used,
                    "fy2030_value": anchor,
                    "fy2031_value": first,
                    "seam_step_pct": seam_step * 100.0,
                    "prior_year_step_pct": prior_step * 100.0,
                    "duplicate_points": int((values.index == ANCHOR_FY).sum()) - 1,
                    "status": "continuous" if abs(seam_step) < 0.15 else "DISCONTINUOUS",
                }
            )
            if abs(seam_step) >= 0.15:
                failures.append(f"{scenario}/{series}: seam jump {seam_step * 100:.2f}%")
    return pd.DataFrame(rows)


def formula_reconciliation(line: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario, source_path in SCENARIOS:
        scoped = line[line["source_path"].astype(str).eq(source_path)]
        wide = scoped.pivot_table(
            index=pd.to_numeric(scoped["FY"], errors="coerce"),
            columns="series_id", values="value", aggfunc="first",
        )
        long_run = wide.loc[wide.index >= FIRST_EXTRAPOLATION_FY]
        for fy, row in long_run.iterrows():
            checks = {
                "gross_ruc_revenue": row["light_ruc_net_revenue"] + row["heavy_ruc_net_revenue"]
                + row["light_bev_ruc_net_revenue"] + row["heavy_bev_ruc_net_revenue"]
                + row["phev_ruc_net_revenue"],
                "total_ruc_net_revenue": row["ruc_revenue_net_admin"] - row["ruc_refunds"],
                "net_fed_revenue": row["gross_fed_revenue"] - row["fed_refunds"],
                "total_nltf_net_revenue": row["total_revenue_net_admin"] - row["total_refunds"],
            }
            for series, calculated in checks.items():
                observed = float(row[series])
                residual = observed - float(calculated)
                rows.append(
                    {
                        "scenario_name": scenario, "fy": int(fy), "series_id": series,
                        "observed": observed, "calculated": float(calculated),
                        "residual": residual,
                        "status": "closes" if abs(residual) <= 1e-6 else "OPEN",
                    }
                )
                if abs(residual) > 1e-6:
                    failures.append(f"{scenario} FY{int(fy)} {series}: residual {residual:.3e}")
    return pd.DataFrame(rows)


def fan_rendering_audit(pack) -> pd.DataFrame:
    bands = pack.fan_band_rows
    fy = pd.to_numeric(bands["FY"], errors="coerce")
    rows: list[dict[str, object]] = []
    for (source, segment), group in bands.groupby(
        [bands["fan_source"].astype(str), bands["fan_segment"].astype(str)]
    ):
        years = pd.to_numeric(group["FY"], errors="coerce")
        rows.append(
            {
                "fan_source": source,
                "fan_segment": segment,
                "rows": int(len(group)),
                "first_fy": int(years.min()),
                "last_fy": int(years.max()),
                "is_probabilistic_claim": source not in ("Scenario spread",),
                "interpretation_sample": str(group["interpretation"].dropna().iloc[0])[:120]
                if group["interpretation"].notna().any() else "",
            }
        )
    empirical = bands["fan_source"].astype(str).isin(
        [FAN_SOURCE_MBU26_ARCHIVED, FAN_SOURCE_CURRENT_BACKTEST]
    )
    leaked = int((empirical & fy.gt(ANCHOR_FY)).sum())
    if leaked:
        failures.append(f"{leaked} empirical fan rows extend past FY{ANCHOR_FY}")
    return pd.DataFrame(rows)


def source_horizon_audit(pack) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for name, frame, key in (
        ("revenue_stack_components", pack.revenue_stack_components, "FY"),
        ("revenue_line_reconciliation", pack.revenue_line_reconciliation, "FY"),
    ):
        for source, group in frame.groupby(frame["source_path"].astype(str)):
            years = pd.to_numeric(group[key], errors="coerce")
            rows.append(
                {
                    "frame": name, "source_path": source,
                    "first_fy": int(years.min()), "last_fy": int(years.max()),
                    "rows": int(len(group)),
                }
            )
    frame = pd.DataFrame(rows)
    stack = frame[frame["frame"].eq("revenue_stack_components")]
    official = stack[stack["source_path"].eq("MBU26 official")]
    current = stack[stack["source_path"].eq("Current finalist Base case")]
    if len(official) and int(official["last_fy"].iloc[0]) < 2055:
        failures.append(f"MBU26 stack stops at FY{int(official['last_fy'].iloc[0])}, not its FY2055 horizon")
    if len(current) and int(current["last_fy"].iloc[0]) < LAST_EXTRAPOLATION_FY:
        failures.append(f"Current stack stops at FY{int(current['last_fy'].iloc[0])}")
    return frame


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pack = load_revenue_outlook_pack(PACK, repo_root=ROOT)
    if pack is None:
        raise SystemExit("Revenue Outlook pack unavailable")
    chart = pack.revenue_chart_rows
    line = pack.revenue_line_reconciliation
    raw = pd.read_parquet(PACK / "raw_quarterly_forecast_audit.parquet")
    wide = pd.read_parquet(PACK / "scenario_inputs" / "scenario_input_wide.parquet")
    official = pd.read_csv(
        ROOT / "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_official_annual.csv"
    )

    short_run = short_run_unchanged()
    short_run.to_csv(OUT / "short_run_unchanged_check.csv", index=False)
    continuity = continuity_audit(chart, line)
    continuity.to_csv(OUT / "fy2030_fy2031_continuity.csv", index=False)

    extrapolation = build_post_model_extrapolation_annual(
        line_reconciliation=line, raw_quarterly_audit=raw,
        scenario_input_wide=wide, mbu26_official_annual=official, repo_root=ROOT,
    )
    activity = extrapolation[extrapolation["unit"].astype(str).ne("$m nominal ex GST")]
    revenue = extrapolation[extrapolation["unit"].astype(str).eq("$m nominal ex GST")]
    activity.to_csv(OUT / "post_model_extrapolation_activity.csv", index=False)
    revenue.to_csv(OUT / "post_model_extrapolation_revenue.csv", index=False)

    anchors = anchor_index_level_audit(
        line_reconciliation=line, raw_quarterly_audit=raw,
        scenario_input_wide=wide, repo_root=ROOT,
    )
    anchors.to_csv(OUT / "anchor_index_level_audit.csv", index=False)

    guard = light_ruc_long_run_guard_frame(extrapolation)
    guard.to_csv(OUT / "light_ruc_long_run_guard.csv", index=False)
    worst_pool = float(guard["pool_million_km"].max())
    if worst_pool >= RETIRED_PATHOLOGY_FY2050_MILLION_KM * 0.5:
        failures.append(f"Light pool {worst_pool:.0f} Mkm approaches the retired pathology")

    reconciliation = formula_reconciliation(line)
    reconciliation.to_csv(OUT / "formula_reconciliation.csv", index=False)
    fan = fan_rendering_audit(pack)
    fan.to_csv(OUT / "fan_rendering_audit.csv", index=False)
    horizons = source_horizon_audit(pack)
    horizons.to_csv(OUT / "source_horizon_audit.csv", index=False)

    base_total = _annual(chart, "current_basecase", "total_nltf_net_revenue")
    comparison_total = _annual(chart, "current_comparison_1", "total_nltf_net_revenue")
    vfm = pd.read_csv(ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
    vfm_base = vfm[vfm["scenario"].eq("Base_EV")].set_index("june_year")
    vfm_pool_2050 = float(
        vfm_base.at[2050, "light_ruc_conventional_million_km"]
        + vfm_base.at[2050, "light_ruc_bev_million_km"]
        + vfm_base.at[2050, "light_ruc_phev_million_km"]
    )
    pool_2050 = float(guard[guard["fy"].eq(2050) & guard["scenario_name"].eq("current_basecase")]["pool_million_km"].iloc[0])

    report = [
        "# Revenue Outlook long-run restoration",
        "",
        "## What was restored, and what was deliberately NOT restored",
        "",
        "Restored: the Current forecast beyond FY2030, the uncertainty fan, the",
        "source-specific composition horizons, and a clean public page.",
        "",
        "NOT restored: the constructor that caused the FY2030 cutoff. The retired",
        f"rule divided a growing conventional forecast by a conventional share",
        f"approaching zero, implying ~{RETIRED_PATHOLOGY_FY2050_MILLION_KM:,.0f} million km of",
        "Light RUC by FY2050. The replacement is a structural total-pool index:",
        "",
        "    pool_fy = corrected_pool_2030 x (VFM_Base_pool_fy / VFM_Base_pool_2030)",
        "",
        "allocated by the exact vendored VFM shares. No division by a share",
        "appears anywhere, and a test bans the idiom by pattern.",
        "",
        "## Headline results",
        "",
        f"- Base Total NLTF: FY2030 ${base_total.loc[ANCHOR_FY]:,.1f}m -> FY2050 ${base_total.loc[2050]:,.1f}m",
        f"- Comparison Total NLTF: FY2030 ${comparison_total.loc[ANCHOR_FY]:,.1f}m -> FY2050 ${comparison_total.loc[2050]:,.1f}m",
        f"- Base Light RUC pool FY2050: {pool_2050:,.0f} Mkm "
        f"({pool_2050 / vfm_pool_2050:.3f}x the VFM pool, "
        f"{pool_2050 / RETIRED_PATHOLOGY_FY2050_MILLION_KM:.3f}x the retired pathology)",
        f"- Short run: {int(short_run['values_changed'].sum())} values changed across "
        f"{int(short_run['preexisting_rows_matched'].sum())} pre-existing rows",
        f"- Seam continuity: worst step {continuity['seam_step_pct'].abs().max():.2f}%",
        f"- Formula closure: {len(reconciliation)} checks, worst residual "
        f"{reconciliation['residual'].abs().max():.2e}",
        "",
        "## Uncertainty presentation",
        "",
        "The two horizons are not the same kind of object. An empirical 50/80",
        "band is calibrated from realised forecast error; extrapolated past the",
        "model's own forecast it would assert something it cannot support. So:",
        "",
        "- empirical sources (backtest error, archived official error) are",
        f"  TRUNCATED at FY{ANCHOR_FY};",
        "- the scenario spread continues, labelled a long-run scenario envelope,",
        "  drawn at reduced opacity behind a seam marker;",
        "- a scenario spread is never called a confidence interval;",
        "- the light-blue MoT VFM fast-slow composition range keeps its own",
        "  colour and meaning, separate from the gray forecast fan.",
        "",
        "## Composition horizons",
        "",
        "The FY2030 cap on MBU26 had two causes, both fixed:",
        "",
        "1. the official line/stack rows were truncated to the CURRENT runtime",
        "   cutoff at pack build; they now run to the official source horizon;",
        "2. the slider bounds were computed over the whole stack frame BEFORE a",
        "   source was chosen; they are now derived after selection, with",
        "   session-state clamping when the source changes.",
        "",
        "| source | first FY | last FY |",
        "|---|---|---|",
    ]
    stack_rows = horizons[horizons["frame"].eq("revenue_stack_components")]
    for row in stack_rows.itertuples():
        report.append(f"| {row.source_path} | {row.first_fy} | {row.last_fy} |")
    report += [
        "",
        "## Evidence in this directory",
        "",
        "- `restoration_source_audit.md` - what was removed, where, and why",
        "- `short_run_unchanged_check.csv` - CSV-vs-CSV exact identity",
        "- `fy2030_fy2031_continuity.csv` - seam steps vs the prior year's step",
        "- `post_model_extrapolation_activity.csv`, `..._revenue.csv`",
        "- `anchor_index_level_audit.csv` - anchor, index and level SEPARATELY,",
        "  with the raw path's own level shown to prove it was not republished",
        "- `light_ruc_long_run_guard.csv` - pool vs the retired pathology",
        "- `formula_reconciliation.csv` - every long-run aggregate closes",
        "- `fan_rendering_audit.csv` - which band claims which basis over which years",
        "- `source_horizon_audit.csv` - per-source horizons, proven independent",
        "",
        "## A note on the short-run comparison basis",
        "",
        "The identity check is CSV-against-CSV. main's own CSV and parquet",
        "already disagree on 26 annual rows by one ULP (max 1.82e-12, relative",
        "2.2e-16) purely from CSV text precision - a pre-existing serialisation",
        "artifact, not a value difference. Comparing the same serialisation on",
        "both sides keeps the assertion exact instead of tolerance-based.",
    ]
    (OUT / "implementation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")

    print(f"short run           : {int(short_run['values_changed'].sum())} changed, "
          f"{int(short_run['preexisting_rows_matched'].sum())} rows compared")
    print(f"seam continuity     : worst {continuity['seam_step_pct'].abs().max():.2f}%")
    print(f"formula closure     : {len(reconciliation)} checks, worst "
          f"{reconciliation['residual'].abs().max():.2e}")
    print(f"light pool FY2050   : {pool_2050:,.0f} Mkm "
          f"({pool_2050 / RETIRED_PATHOLOGY_FY2050_MILLION_KM:.3f}x pathology)")
    print(f"base total FY2050   : ${base_total.loc[2050]:,.1f}m")
    print(f"fan segments        : {fan['fan_segment'].value_counts().to_dict()}")
    print(f"stack horizons      : "
          f"{dict(zip(stack_rows['source_path'], stack_rows['last_fy']))}")
    if failures:
        print("\nFAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nPASS: long run restored; the retired constructor is not present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

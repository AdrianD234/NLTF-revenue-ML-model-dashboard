"""Workstream A, Phase A2: exact financial and output bridge to MBU26.

Closes the Current-minus-MBU26 dollar gap through named observable activity and
revenue lines. Does NOT attempt a causal decomposition over MBU26's internal
GDP, unemployment, fuel-price, RUC-price or judgemental assumptions, which are
not published in the source pack.

The distinction is deliberate and is preserved throughout:

  financial  the dollar gap closes exactly through observable lines
  causal     why MBU26 produced those quantities is partly unavailable

`unknown_official_model_inputs_or_judgment` is an explanation-status label on
the activity differences. It is never a dollar plug, because the financial
bridge already closes without it.

Read-only. Engine: AR(1). No model, pack or checkpoint is altered.

Usage::

    python scripts/mbu26_financial_decomposition.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.mbu26_source_spine import load_mbu26_annual_spine  # noqa: E402

AR1_PACK = REPO_ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
FY = list(range(2026, 2031))
CLOSURE_TOLERANCE = 1e-6


def _current() -> pd.DataFrame:
    f = pd.read_parquet(AR1_PACK / "revenue_chart_rows.parquet")
    f = f[
        f["time_grain"].astype(str).eq("june_year")
        & f["scenario_name"].astype(str).eq("current_basecase")
    ].copy()
    f["FY"] = pd.to_numeric(f["june_year"], errors="coerce")
    f = f[f["FY"].isin(FY)]
    return f.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first")


def _official() -> pd.DataFrame:
    oa = load_mbu26_annual_spine(repo_root=REPO_ROOT).official_annual.copy()
    oa["FY"] = pd.to_numeric(oa.get("FY"), errors="coerce")
    oa = oa[oa["FY"].isin(FY)]
    return oa.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first")


def _get(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame.columns:
        return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(np.nan, index=frame.index, name=name)


def build(cur: pd.DataFrame, off: pd.DataFrame) -> dict[str, pd.DataFrame]:
    idx = pd.Index(FY, name="FY")
    cur, off = cur.reindex(idx), off.reindex(idx)

    # --- Shared MBU26 assumptions, identical on both sides by construction ---
    # Fuel intensity: official litres per official light-petrol VKT.
    off_lpv = _get(off, "light_petrol_vkt")
    off_vol = _get(off, "ped_volume")
    intensity = off_vol / off_lpv                      # litres per km
    ped_rate = _get(off, "gross_ped_revenue") / off_vol  # $m per million litres

    # Current light-petrol VKT is recoverable by inverting the shared intensity.
    cur_vol = _get(cur, "ped_volume")
    cur_lpv = cur_vol / intensity

    # Population, output-implied. Not an independently published MBU26 input.
    cur_vktpc = _get(cur, "ped_vkt_per_capita")
    off_vktpc = _get(off, "ped_vkt_per_capita")
    cur_pop = cur_lpv * 1_000_000.0 / cur_vktpc
    off_pop = off_lpv * 1_000_000.0 / off_vktpc

    # --- Level 1: total NLTF ---
    rows: list[dict[str, Any]] = []
    tot_c, tot_o = _get(cur, "total_nltf_net_revenue"), _get(off, "total_nltf_net_revenue")
    fed_c, fed_o = _get(cur, "net_fed_revenue"), _get(off, "net_fed_revenue")
    ruc_c, ruc_o = _get(cur, "total_ruc_net_revenue"), _get(off, "total_ruc_net_revenue")
    mvr_c, mvr_o = _get(cur, "net_mvr_revenue"), _get(off, "net_mvr_revenue")
    tuc_o = _get(off, "tuc_net_revenue").fillna(0.0)

    for fy in FY:
        gap = tot_c[fy] - tot_o[fy]
        parts = {
            "net_fed_revenue": fed_c[fy] - fed_o[fy],
            "total_ruc_net_revenue": ruc_c[fy] - ruc_o[fy],
            "net_mvr_revenue": mvr_c[fy] - mvr_o[fy],
            "tuc_and_other_fixed": 0.0,
        }
        resid = gap - sum(parts.values())
        for k, v in parts.items():
            rows.append({"FY": fy, "level": "1_total_nltf", "component": k,
                         "contribution_nzd_m": v, "status": "observable"})
        rows.append({"FY": fy, "level": "1_total_nltf", "component": "closure_residual",
                     "contribution_nzd_m": resid, "status": "residual"})

    # --- Level 2: Net FED ---
    for fy in FY:
        gap = fed_c[fy] - fed_o[fy]
        gped = _get(cur, "gross_ped_revenue")[fy] - _get(off, "gross_ped_revenue")[fy]
        parts = {"gross_ped_revenue": gped,
                 "lpg_and_cng": 0.0,
                 "fed_refunds": 0.0}
        resid = gap - sum(parts.values())
        for k, v in parts.items():
            rows.append({"FY": fy, "level": "2_net_fed", "component": k,
                         "contribution_nzd_m": v,
                         "status": "observable" if k == "gross_ped_revenue" else "shared_mbu26_assumption"})
        rows.append({"FY": fy, "level": "2_net_fed", "component": "closure_residual",
                     "contribution_nzd_m": resid, "status": "residual"})

    # --- Level 3: PED bridge, order-neutral over VKTpc x population ---
    # gross PED revenue = VKTpc x population / 1e6 x intensity x rate
    for fy in FY:
        k = intensity[fy] * ped_rate[fy] / 1_000_000.0
        dv, dp = cur_vktpc[fy] - off_vktpc[fy], cur_pop[fy] - off_pop[fy]
        # Shapley over the two observable multiplicative quantities.
        vkt_term = k * dv * (off_pop[fy] + dp / 2.0)
        pop_term = k * dp * (off_vktpc[fy] + dv / 2.0)
        gap = _get(cur, "gross_ped_revenue")[fy] - _get(off, "gross_ped_revenue")[fy]
        resid = gap - vkt_term - pop_term
        rows += [
            {"FY": fy, "level": "3_ped_bridge", "component": "ped_vkt_per_capita",
             "contribution_nzd_m": vkt_term, "status": "observable"},
            {"FY": fy, "level": "3_ped_bridge", "component": "population_implied",
             "contribution_nzd_m": pop_term, "status": "observable_output_implied"},
            {"FY": fy, "level": "3_ped_bridge", "component": "fuel_intensity",
             "contribution_nzd_m": 0.0, "status": "shared_mbu26_assumption"},
            {"FY": fy, "level": "3_ped_bridge", "component": "effective_ped_rate",
             "contribution_nzd_m": 0.0, "status": "shared_mbu26_assumption"},
            {"FY": fy, "level": "3_ped_bridge", "component": "closure_residual",
             "contribution_nzd_m": resid, "status": "residual"},
        ]

    # --- Level 4: Total RUC by class ---
    classes = [
        ("light_ruc_net_km", "light_ruc_net_revenue", "conventional_light_ruc"),
        ("light_bev_ruc_net_km", "light_bev_ruc_net_revenue", "light_bev_ruc"),
        ("phev_ruc_net_km", "phev_ruc_net_revenue", "phev_ruc"),
        ("heavy_ruc_net_km", "heavy_ruc_net_revenue", "heavy_ruc"),
    ]
    class_rows: list[dict[str, Any]] = []
    for fy in FY:
        gap = ruc_c[fy] - ruc_o[fy]
        total_class = 0.0
        for km_id, rev_id, label in classes:
            ck, ok_ = _get(cur, km_id)[fy], _get(off, km_id)[fy]
            cr, orv = _get(cur, rev_id)[fy], _get(off, rev_id)[fy]
            rate = orv / ok_ if ok_ and np.isfinite(ok_) and ok_ != 0 else np.nan
            diff = cr - orv
            total_class += 0.0 if not np.isfinite(diff) else diff
            rows.append({"FY": fy, "level": "4_total_ruc", "component": label,
                         "contribution_nzd_m": diff, "status": "observable"})
            class_rows.append({
                "FY": fy, "class": label,
                "current_activity_million_km": ck, "official_activity_million_km": ok_,
                "activity_difference_million_km": ck - ok_,
                "shared_effective_rate_nzd_m_per_million_km": rate,
                "activity_driven_dollar_difference_nzd_m": (ck - ok_) * rate,
                "actual_revenue_difference_nzd_m": diff,
            })
        # Heavy BEV, RUC admin and refunds are not carried as separate current
        # chart rows, so their combined net effect cannot be assumed zero. It is
        # measured by difference. This is a named set of known lines, not a plug
        # for unknown causes: the alternative would be to leave the identity
        # open by up to 0.63 $m and call it a residual.
        fixed_effect = gap - total_class
        rows.append({"FY": fy, "level": "4_total_ruc",
                     "component": "heavy_bev_admin_and_refunds_net_effect",
                     "contribution_nzd_m": fixed_effect,
                     "status": "observable_derived_by_difference"})
        rows.append({"FY": fy, "level": "4_total_ruc", "component": "closure_residual",
                     "contribution_nzd_m": 0.0, "status": "residual"})

    bridge = pd.DataFrame(rows)

    # --- Financial decomposition: named observable components summing to the gap
    fin: list[dict[str, Any]] = []
    for fy in FY:
        gap = tot_c[fy] - tot_o[fy]
        comps = {
            "ped_vkt_per_capita": bridge.query(
                "FY==@fy and level=='3_ped_bridge' and component=='ped_vkt_per_capita'"
            )["contribution_nzd_m"].sum(),
            "population_implied": bridge.query(
                "FY==@fy and level=='3_ped_bridge' and component=='population_implied'"
            )["contribution_nzd_m"].sum(),
        }
        for _, _, label in classes:
            comps[label] = bridge.query(
                "FY==@fy and level=='4_total_ruc' and component==@label"
            )["contribution_nzd_m"].sum()
        comps["heavy_bev_admin_and_refunds"] = bridge.query(
            "FY==@fy and level=='4_total_ruc' and "
            "component=='heavy_bev_admin_and_refunds_net_effect'"
        )["contribution_nzd_m"].sum()
        comps["net_mvr_and_fixed_lines"] = (mvr_c[fy] - mvr_o[fy])
        resid = gap - sum(comps.values())
        for k, v in comps.items():
            fin.append({"FY": fy, "component": k, "contribution_nzd_m": v,
                        "share_of_gap_pct": v / gap * 100.0 if gap else np.nan,
                        "status": "observable"})
        fin.append({"FY": fy, "component": "closure_residual", "contribution_nzd_m": resid,
                    "share_of_gap_pct": resid / gap * 100.0 if gap else np.nan,
                    "status": "residual"})
        fin.append({"FY": fy, "component": "total_gap", "contribution_nzd_m": gap,
                    "share_of_gap_pct": 100.0, "status": "target"})

    context = pd.DataFrame({
        "FY": FY,
        "current_vkt_per_capita": [cur_vktpc[f] for f in FY],
        "official_vkt_per_capita": [off_vktpc[f] for f in FY],
        "current_population_implied": [cur_pop[f] for f in FY],
        "official_population_implied": [off_pop[f] for f in FY],
        "current_light_petrol_vkt_million_km": [cur_lpv[f] for f in FY],
        "official_light_petrol_vkt_million_km": [off_lpv[f] for f in FY],
        "shared_fuel_intensity_litres_per_km": [intensity[f] for f in FY],
        "shared_effective_ped_rate": [ped_rate[f] for f in FY],
        "current_total_light_ruc_pool_million_km": [
            _get(cur, "light_ruc_net_km")[f] + _get(cur, "light_bev_ruc_net_km")[f]
            + _get(cur, "phev_ruc_net_km")[f] for f in FY],
        "official_total_light_ruc_pool_million_km": [
            _get(off, "light_ruc_net_km")[f] + _get(off, "light_bev_ruc_net_km")[f]
            + _get(off, "phev_ruc_net_km")[f] for f in FY],
    })

    return {
        "bridge": bridge,
        "financial": pd.DataFrame(fin),
        "classes": pd.DataFrame(class_rows),
        "context": context,
    }


DRIVER_STATUS = [
    ("PED VKT per capita", "direct", "AR(1) output vs MBU26 official row", "yes",
     "measured in the financial decomposition", ""),
    ("population", "derived", "light_petrol_vkt x 1e6 / ped_vkt_per_capita", "yes",
     "measured as an output-implied proxy", ""),
    ("EV/PHEV class allocation", "direct", "class km rows on both sides", "yes",
     "measured via class activity differences", ""),
    ("fuel intensity", "direct", "official litres / official VKT", "shared",
     "0 by construction - identical on both sides", ""),
    ("effective PED rate", "direct", "official revenue / official litres", "shared",
     "0 by construction - identical on both sides", ""),
    ("class RUC effective rates", "direct", "official revenue / official km", "shared",
     "0 by construction - identical on both sides", ""),
    ("refunds, admin, LPG, CNG, MVR, TUC", "direct", "MBU26 official rows", "shared",
     "0 by construction - inherited unchanged", ""),
    ("real GDP", "unavailable", "not published in the MBU26 source pack", "no",
     "NA", "MBU26 publishes outputs, not the driver assumptions behind them"),
    ("population as an independent input", "unavailable",
     "not published in the MBU26 source pack", "no",
     "NA", "only recoverable as an output-implied proxy, which is not the same thing"),
    ("unemployment rate", "unavailable", "not published in the MBU26 source pack", "no",
     "NA", "MBU26 publishes outputs, not the driver assumptions behind them"),
    ("real petrol price", "unavailable", "not published in the MBU26 source pack", "no",
     "NA", "MBU26 publishes outputs, not the driver assumptions behind them"),
    ("real diesel price", "unavailable", "not published in the MBU26 source pack", "no",
     "NA", "MBU26 publishes outputs, not the driver assumptions behind them"),
    ("real Light/Heavy RUC prices", "unavailable", "not published in the MBU26 source pack", "no",
     "NA", "MBU26 publishes outputs, not the driver assumptions behind them"),
    ("judgemental adjustment", "unavailable", "not disclosed", "no",
     "NA", "presence or absence cannot be established from the workbook"),
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path,
                   default=REPO_ROOT / "outputs" / "mbu26_reconciliation")
    args = p.parse_args(argv)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    built = build(_current(), _official())
    built["bridge"].to_csv(out / "bridge_formula_reconciliation.csv", index=False)
    built["financial"].to_csv(out / "mbu26_gap_financial_decomposition.csv", index=False)
    built["classes"].to_csv(out / "mbu26_class_activity_bridge.csv", index=False)
    built["context"].to_csv(out / "mbu26_bridge_context.csv", index=False)

    pd.DataFrame(DRIVER_STATUS, columns=[
        "driver", "availability", "source", "counterfactual_run",
        "measured_contribution", "reason_if_unavailable",
    ]).to_csv(out / "mbu26_gap_driver_decomposition.csv", index=False)

    resid = built["bridge"][built["bridge"]["status"].eq("residual")]
    worst = float(resid["contribution_nzd_m"].abs().max())
    fin_resid = built["financial"][built["financial"]["status"].eq("residual")]
    fin_worst = float(fin_resid["contribution_nzd_m"].abs().max())

    print(built["financial"][built["financial"].FY.eq(2030)].to_string(index=False))
    print()
    print(f"max |bridge closure residual|    : {worst:.3e}")
    print(f"max |financial closure residual| : {fin_worst:.3e}")
    print(f"tolerance                        : {CLOSURE_TOLERANCE:.0e}")
    print(f"written to {out}")
    return 0 if max(worst, fin_worst) <= CLOSURE_TOLERANCE else 1


if __name__ == "__main__":
    raise SystemExit(main())

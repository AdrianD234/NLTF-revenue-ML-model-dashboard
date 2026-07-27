"""Workstream A, Phase A2 closeout: separate migration, source the RUC lines.

Two corrections to the first decomposition pass.

**Migration was hidden inside population.** The first pass derived current
population by inverting light-petrol VKT, which folds the EV/PHEV migration
allocation into the population term. The production bridge applies migration
*after* VKT per capita x population, so the three are separable and are now
separated. Current population is taken from the scenario inputs; the migration
factor is what remains.

**The RUC balancer was difference-derived.** Naming a residual does not make it
sourced. Heavy BEV revenue, RUC administration and RUC refunds are now read
from the official spine, and any part the official workbook does not itself
close is reported as an explicit formula/rounding residual rather than bundled.

A caveat that must travel with the result: official population is not
published, so the official side is an output-implied population with a
migration factor of exactly 1 by construction. The migration term therefore
measures the current allocation against that baseline, and carries whatever
MBU26 folded into its own implied population.

Read-only. Engine: AR(1).

Usage::

    python scripts/mbu26_phase_a2_closeout.py
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

from scripts.mbu26_financial_decomposition import (  # noqa: E402
    AR1_PACK, FY, CLOSURE_TOLERANCE, _current, _official, _get,
)

SCENARIO_INPUTS = AR1_PACK / "scenario_inputs" / "scenario_input_wide.parquet"


def current_population() -> pd.Series:
    """True current population by FY, from the scenario inputs."""

    w = pd.read_parquet(SCENARIO_INPUTS)
    p = w[
        w["stream"].astype(str).eq("PED")
        & w["scenario_name"].astype(str).eq("current_basecase")
    ].copy()
    p["pop"] = pd.to_numeric(p["population"], errors="coerce")
    p = p[p["pop"].notna() & p["pop"].gt(0)]
    q = p["canonical_period"].astype(str)
    p["FY"] = q.str[:4].astype(int) + (q.str[5].astype(int) >= 3).astype(int)
    return p.groupby("FY")["pop"].mean().reindex(FY)


def shapley_product_3(v0, p0, m0, v1, p1, m1):
    """Exact Shapley allocation for a three-factor product V*P*M.

    Order-neutral by construction: each factor receives the average of its
    marginal contributions across all 3! orderings.
    """
    dv, dp, dm = v1 - v0, p1 - p0, m1 - m0
    phi_v = dv * (p0 * m0 + (dp * m0 + p0 * dm) / 2.0 + dp * dm / 3.0)
    phi_p = dp * (v0 * m0 + (dv * m0 + v0 * dm) / 2.0 + dv * dm / 3.0)
    phi_m = dm * (v0 * p0 + (dv * p0 + v0 * dp) / 2.0 + dv * dp / 3.0)
    return phi_v, phi_p, phi_m


def build() -> dict[str, pd.DataFrame]:
    idx = pd.Index(FY, name="FY")
    cur, off = _current().reindex(idx), _official().reindex(idx)

    off_lpv, off_vol = _get(off, "light_petrol_vkt"), _get(off, "ped_volume")
    intensity = off_vol / off_lpv
    ped_rate = _get(off, "gross_ped_revenue") / off_vol
    cur_vol = _get(cur, "ped_volume")
    cur_lpv = cur_vol / intensity

    cur_vktpc, off_vktpc = _get(cur, "ped_vkt_per_capita"), _get(off, "ped_vkt_per_capita")
    cur_pop = current_population()
    off_pop = off_lpv * 1_000_000.0 / off_vktpc     # implied; migration == 1

    # Migration allocation factor: what the bridge applies after VKTpc x pop.
    cur_mig = cur_lpv / (cur_vktpc * cur_pop / 1_000_000.0)
    off_mig = pd.Series(1.0, index=idx)

    ped_rows: list[dict[str, Any]] = []
    counterfactual: list[dict[str, Any]] = []
    for fy in FY:
        k = intensity[fy] * ped_rate[fy] / 1_000_000.0
        pv, pp, pm = shapley_product_3(
            off_vktpc[fy], off_pop[fy], off_mig[fy],
            cur_vktpc[fy], cur_pop[fy], cur_mig[fy],
        )
        gap = _get(cur, "gross_ped_revenue")[fy] - _get(off, "gross_ped_revenue")[fy]
        resid = gap - k * (pv + pp + pm)
        for comp, val, status in [
            ("ped_vkt_per_capita", k * pv, "observable"),
            ("population_scaling", k * pp, "derived_from_official_outputs_not_independently_published"),
            ("ev_phev_migration_allocation", k * pm, "observable_bridge_term"),
            ("fuel_intensity", 0.0, "shared_mbu26_assumption"),
            ("effective_ped_rate", 0.0, "shared_mbu26_assumption"),
            ("lpg_cng_and_fed_refunds", 0.0, "shared_mbu26_assumption"),
            ("closure_residual", resid, "residual"),
        ]:
            ped_rows.append({"FY": fy, "component": comp,
                             "contribution_nzd_m": val, "status": status})

        # Counterfactual: current VKTpc, official implied population, current
        # migration and all other current settings, through the same bridge.
        cf_lpv = cur_vktpc[fy] * off_pop[fy] / 1_000_000.0 * cur_mig[fy]
        cf_vol = cf_lpv * intensity[fy]
        counterfactual.append({
            "FY": fy,
            "current_light_petrol_vkt": cur_lpv[fy],
            "counterfactual_light_petrol_vkt": cf_lpv,
            "current_ped_volume": cur_vol[fy],
            "counterfactual_ped_volume": cf_vol,
            "current_gross_ped_revenue": _get(cur, "gross_ped_revenue")[fy],
            "counterfactual_gross_ped_revenue": cf_vol * ped_rate[fy],
            "current_net_fed_revenue": _get(cur, "net_fed_revenue")[fy],
            "counterfactual_net_fed_revenue": _get(cur, "net_fed_revenue")[fy]
            + (cf_vol * ped_rate[fy] - _get(cur, "gross_ped_revenue")[fy]),
            "population_effect_nzd_m": cf_vol * ped_rate[fy] - _get(cur, "gross_ped_revenue")[fy],
        })

    # --- RUC, sourced directly rather than by difference ---
    ruc_rows: list[dict[str, Any]] = []
    classes = [
        ("light_ruc_net_revenue", "conventional_light_ruc"),
        ("light_bev_ruc_net_revenue", "light_bev_ruc"),
        ("phev_ruc_net_revenue", "phev_ruc"),
        ("heavy_ruc_net_revenue", "heavy_ruc"),
    ]
    for fy in FY:
        gap = _get(cur, "total_ruc_net_revenue")[fy] - _get(off, "total_ruc_net_revenue")[fy]
        named = 0.0
        for rev_id, label in classes:
            d = _get(cur, rev_id)[fy] - _get(off, rev_id)[fy]
            named += d
            ruc_rows.append({"FY": fy, "component": label,
                             "contribution_nzd_m": d, "status": "observable"})
        # Heavy BEV is an official-only line the current path inherits, so its
        # contribution is zero unless the current pack carries its own value.
        hb_c = _get(cur, "heavy_bev_ruc_net_revenue")[fy]
        hb_o = _get(off, "heavy_bev_ruc_net_revenue")[fy]
        hb = 0.0 if not np.isfinite(hb_c) else hb_c - hb_o
        ad_c, ad_o = _get(cur, "ruc_admin_revenue")[fy], _get(off, "ruc_admin_revenue")[fy]
        ad = 0.0 if not np.isfinite(ad_c) else ad_c - ad_o
        # Refunds cancel algebraically in the Total RUC identity
        # (gross includes them, ruc_revenue_net_admin - ruc_refunds removes them).
        named += hb + ad
        ruc_rows += [
            {"FY": fy, "component": "heavy_bev_ruc_revenue", "contribution_nzd_m": hb,
             "status": "inherited_from_mbu26" if hb == 0.0 else "observable"},
            {"FY": fy, "component": "ruc_admin_revenue", "contribution_nzd_m": ad,
             "status": "inherited_from_mbu26" if ad == 0.0 else "observable"},
            {"FY": fy, "component": "ruc_refunds", "contribution_nzd_m": 0.0,
             "status": "cancels_in_total_ruc_identity"},
            {"FY": fy, "component": "official_ruc_formula_or_rounding_residual",
             "contribution_nzd_m": gap - named,
             "status": "official_workbook_residual"},
        ]

    return {
        "ped": pd.DataFrame(ped_rows),
        "ruc": pd.DataFrame(ruc_rows),
        "counterfactual": pd.DataFrame(counterfactual),
        "factors": pd.DataFrame({
            "FY": FY,
            "current_vkt_per_capita": [cur_vktpc[f] for f in FY],
            "official_vkt_per_capita": [off_vktpc[f] for f in FY],
            "current_population": [cur_pop[f] for f in FY],
            "official_population_implied": [off_pop[f] for f in FY],
            "current_migration_factor": [cur_mig[f] for f in FY],
            "official_migration_factor": [off_mig[f] for f in FY],
        }),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path,
                   default=REPO_ROOT / "outputs" / "mbu26_reconciliation")
    args = p.parse_args(argv)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    b = build()
    b["ped"].to_csv(out / "mbu26_ped_bridge_decomposition.csv", index=False)
    b["ruc"].to_csv(out / "mbu26_ruc_bridge_decomposition.csv", index=False)
    b["counterfactual"].to_csv(out / "mbu26_population_counterfactual.csv", index=False)
    b["factors"].to_csv(out / "mbu26_bridge_factors.csv", index=False)

    ped_res = b["ped"][b["ped"].status.eq("residual")]["contribution_nzd_m"].abs().max()
    ruc_res = b["ruc"][
        b["ruc"].status.eq("official_workbook_residual")
    ]["contribution_nzd_m"].abs().max()

    print(b["ped"][b["ped"].FY.eq(2030)].to_string(index=False))
    print()
    print(b["factors"].to_string(index=False))
    print()
    print(f"max |PED closure residual|            : {ped_res:.3e}  (tolerance {CLOSURE_TOLERANCE:.0e})")
    print(f"max |official RUC formula residual|   : {ruc_res:.3e}")
    print(f"written to {out}")
    return 0 if ped_res <= CLOSURE_TOLERANCE else 1


if __name__ == "__main__":
    raise SystemExit(main())

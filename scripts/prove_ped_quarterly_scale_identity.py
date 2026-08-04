"""Prove the single-scale-factor quarterly construction closes on both annuals.

Section 12 of the brief asks whether one common per-fiscal-year scale factor

    scale_fy = target_petrol_fy / sum_q(raw_petrol_q)

also reproduces the governed annual PED VKT per capita target, or whether a
constrained correction is needed. This script answers it from committed data
rather than from the algebra alone.

Writes annual_ped_identity_audit.csv and quarterly_ped_identity_audit.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: E402
from model_dashboard.post_model_extrapolation import (  # noqa: E402
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    POST_MODEL_SEGMENT,
)

OUT = ROOT / "artifacts" / "revenue_outlook_ped_activity_2050"
SCENARIOS = ("current_basecase", "current_comparison_1")
ENGINES = ("ensemble", "ar1")


def _fy_of_quarter(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    return year + 1 if quarter >= 3 else year


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    annual_rows: list[dict[str, object]] = []
    quarter_rows: list[dict[str, object]] = []

    for engine in ENGINES:
        base = ROOT / engine_revenue_outlook_dir(engine)
        raw = pd.read_parquet(base / "raw_quarterly_forecast_audit.parquet")
        pop = pd.read_parquet(
            base / "scenario_inputs" / "scenario_input_wide.parquet"
        )
        line = pd.read_parquet(base / "revenue_line_reconciliation.parquet")

        pop = pop[pop["stream"].astype(str).eq("PED")][
            ["scenario_name", "canonical_period", "population"]
        ].copy()
        pop["population"] = pd.to_numeric(pop["population"], errors="coerce")

        post = line[
            line["forecast_segment"].astype(str).eq(POST_MODEL_SEGMENT)
            & line["series_id"].astype(str).isin(
                ["ped_vkt_per_capita", "light_petrol_vkt"]
            )
        ].copy()
        post["FY"] = pd.to_numeric(post["FY"], errors="coerce")
        post["value"] = pd.to_numeric(post["value"], errors="coerce")
        targets = post.pivot_table(
            index=["scenario_name", "FY"], columns="series_id", values="value",
            aggfunc="first",
        )

        for scenario in SCENARIOS:
            shape = raw[
                raw["scenario_name"].astype(str).eq(scenario)
                & raw["series_id"].astype(str).eq("ped_vkt_per_capita")
            ][["period", "value"]].copy()
            shape["value"] = pd.to_numeric(shape["value"], errors="coerce")
            merged = shape.merge(
                pop[pop["scenario_name"].astype(str).eq(scenario)],
                left_on="period", right_on="canonical_period", how="left",
            )
            if merged["population"].isna().any():
                raise SystemExit(f"{engine}/{scenario}: population gap in raw quarters")
            merged["fy"] = merged["period"].astype(str).map(_fy_of_quarter)
            # raw_petrol_q in million km, matching the annual constructor's unit
            merged["raw_petrol_q"] = merged["value"] * merged["population"] / 1e6

            for fy in range(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY + 1):
                block = merged[merged["fy"].eq(fy)]
                if len(block) != 4:
                    raise SystemExit(
                        f"{engine}/{scenario}/FY{fy}: {len(block)} raw quarters, expected 4"
                    )
                if (scenario, fy) not in targets.index:
                    raise SystemExit(f"{engine}/{scenario}/FY{fy}: no governed target")
                target_petrol = float(targets.at[(scenario, fy), "light_petrol_vkt"])
                target_vktpc = float(targets.at[(scenario, fy), "ped_vkt_per_capita"])

                raw_petrol_sum = float(block["raw_petrol_q"].sum())
                raw_vktpc_sum = float(block["value"].sum())
                scale = target_petrol / raw_petrol_sum

                # The single scale factor, applied to both shapes.
                q_petrol = scale * block["raw_petrol_q"].to_numpy(dtype=float)
                q_vktpc = scale * block["value"].to_numpy(dtype=float)

                petrol_residual = float(q_petrol.sum() - target_petrol)
                vktpc_residual = float(q_vktpc.sum() - target_vktpc)

                annual_rows.append(
                    {
                        "engine": engine,
                        "scenario": scenario,
                        "fy": fy,
                        "target_light_petrol_vkt": target_petrol,
                        "target_ped_vkt_per_capita": target_vktpc,
                        "raw_petrol_sum": raw_petrol_sum,
                        "raw_vktpc_sum": raw_vktpc_sum,
                        "scale_fy": scale,
                        "petrol_sum_residual": petrol_residual,
                        "vktpc_sum_residual": vktpc_residual,
                        "petrol_rel_residual": petrol_residual / abs(target_petrol),
                        "vktpc_rel_residual": vktpc_residual / abs(target_vktpc),
                        "implied_population": raw_petrol_sum * 1e6 / raw_vktpc_sum,
                        "single_scale_closes": bool(
                            abs(vktpc_residual) <= 1e-9 * abs(target_vktpc)
                            and abs(petrol_residual) <= 1e-9 * abs(target_petrol)
                        ),
                        "negative_quarter": bool((q_petrol <= 0).any() or (q_vktpc <= 0).any()),
                    }
                )

                pops = block["population"].to_numpy(dtype=float)
                for period, vp, vv, pp in zip(
                    block["period"].astype(str), q_petrol, q_vktpc, pops
                ):
                    identity = vv * pp / 1e6
                    quarter_rows.append(
                        {
                            "engine": engine,
                            "scenario": scenario,
                            "fy": fy,
                            "period": period,
                            "quarterly_ped_vkt_per_capita": vv,
                            "population": pp,
                            "quarterly_light_petrol_vkt": vp,
                            "recomputed_petrol_from_identity": identity,
                            "identity_residual": vp - identity,
                            "identity_rel_residual": (vp - identity) / abs(vp),
                            "positive": bool(vp > 0 and vv > 0),
                        }
                    )

    annual = pd.DataFrame(annual_rows)
    quarterly = pd.DataFrame(quarter_rows)
    annual.to_csv(OUT / "annual_ped_identity_audit.csv", index=False)
    quarterly.to_csv(OUT / "quarterly_ped_identity_audit.csv", index=False)

    print(f"annual rows   {len(annual)} (expect {len(ENGINES)*len(SCENARIOS)*20})")
    print(f"quarter rows  {len(quarterly)} (expect {len(ENGINES)*len(SCENARIOS)*80})")
    print()
    print("worst |vktpc sum residual| relative :", annual["vktpc_rel_residual"].abs().max())
    print("worst |petrol sum residual| relative:", annual["petrol_rel_residual"].abs().max())
    print("worst |quarterly identity| relative :", quarterly["identity_rel_residual"].abs().max())
    print("single scale closes everywhere      :", bool(annual["single_scale_closes"].all()))
    print("any negative quarter                :", bool(annual["negative_quarter"].any()))
    print("all quarters positive               :", bool(quarterly["positive"].all()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

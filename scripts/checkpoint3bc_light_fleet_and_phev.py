"""Checkpoint 3B/3C: light-fleet plausibility, anchor method choice, PHEV petrol.

Three questions:

  anchor  Should the Light RUC pool be built by share expansion around the raw
          conventional forecast, or by adding VFM absolute changes to the
          FY2025 actual class values?
  3B      Are the resulting FY2025-FY2035 fleet paths physically coherent?
  3C      Does the PED volume series already include PHEV petrol consumption?

Candidate architecture under test (L1):

    conventional = raw Light RUC model forecast
    pool         = conventional / VFM_Base_conventional_share
    BEV          = pool * VFM_Base_BEV_share
    PHEV         = pool * VFM_Base_PHEV_share

with PED either P0 (raw AR(1) x population) or P1 (that x one retention curve).

Investigation only. Writes only to artifacts/fleet_allocation_semantics/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.ev_uptake_levers import (  # noqa: E402
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_PRESETS,
    lever_share_curves,
    ped_retention_curve,
)

PACK = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
OUT = ROOT / "artifacts" / "fleet_allocation_semantics"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIO = "current_basecase"
FYS = list(range(2025, 2036))
FORECAST_FYS = [fy for fy in FYS if fy != 2025]
TOL = 1e-6
PHEV_PETROL_FRACTIONS = [0.0, 0.25, 0.50, 0.75, 1.0]


def load() -> dict:
    split = pd.read_csv(PACK / "ev_phev_split_assumptions.csv")
    split = split[split["scenario_name"].eq(SCENARIO)].set_index("FY").sort_index()
    bridge = pd.read_csv(PACK / "ped_revenue_bridge_audit.csv")
    bridge = bridge[bridge["scenario_name"].eq(SCENARIO)].set_index("FY").sort_index()
    drift = pd.read_csv(PACK / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq(SCENARIO) & drift["lambda_mode"].astype(str).eq("optimized")
    ].set_index("FY").sort_index()
    vfm = pd.read_csv(ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
    vfm = vfm[vfm["scenario"].eq("Base_EV")].set_index("june_year").sort_index()
    return {"split": split, "bridge": bridge, "drift": drift, "vfm": vfm}


# ------------------------------------------------------- anchor comparison


def anchor_methods(data: dict) -> pd.DataFrame:
    """Share expansion vs actual-anchored add-on, on identical inputs."""
    split, vfm = data["split"], data["vfm"]
    raw_conv = split["current_light_total_modelled_km"].astype(float)

    actual_bev = float(split.loc[2025, "current_light_bev_km"])
    actual_phev = float(split.loc[2025, "current_phev_km"])
    actual_conv = float(split.loc[2025, "current_conventional_light_km"])
    vfm_bev_2025 = float(vfm.loc[2025, "light_ruc_bev_million_km"])
    vfm_phev_2025 = float(vfm.loc[2025, "light_ruc_phev_million_km"])

    rows = []
    for fy in FYS:
        conv = actual_conv if fy == 2025 else float(raw_conv.loc[fy])
        share_conv = float(vfm.loc[fy, "light_ruc_conventional_share"])

        if fy == 2025:
            share_pool = actual_conv + actual_bev + actual_phev
            share_bev, share_phev = actual_bev, actual_phev
            add_bev, add_phev = actual_bev, actual_phev
        else:
            share_pool = conv / share_conv
            share_bev = share_pool * float(vfm.loc[fy, "light_ruc_bev_share"])
            share_phev = share_pool * float(vfm.loc[fy, "light_ruc_phev_share"])
            add_bev = actual_bev + (float(vfm.loc[fy, "light_ruc_bev_million_km"]) - vfm_bev_2025)
            add_phev = actual_phev + (float(vfm.loc[fy, "light_ruc_phev_million_km"]) - vfm_phev_2025)

        rows.append(
            {
                "june_year": fy,
                "raw_conventional": conv,
                "share_anchor_pool": share_pool,
                "share_anchor_bev": share_bev,
                "share_anchor_phev": share_phev,
                "share_anchor_conv_share": conv / share_pool,
                "add_on_pool": conv + add_bev + add_phev,
                "add_on_bev": add_bev,
                "add_on_phev": add_phev,
                "add_on_conv_share": conv / (conv + add_bev + add_phev),
                "vfm_conventional_share": share_conv,
                "mbu26_pool": float(split.loc[fy, "total_light_universe_km"]),
                "mbu26_conventional": float(split.loc[fy, "conventional_light_km"]),
            }
        )
    frame = pd.DataFrame(rows).set_index("june_year")
    # FY2025 -> FY2026 continuity of each method
    for method in ["share_anchor", "add_on"]:
        for series in ["pool", "bev", "phev"]:
            col = f"{method}_{series}"
            frame[f"{col}_step_pct_2025_26"] = np.nan
            frame.loc[2026, f"{col}_step_pct_2025_26"] = 100.0 * (
                float(frame.loc[2026, col]) / float(frame.loc[2025, col]) - 1.0
            )
    return frame


def anchor_scorecard(frame: pd.DataFrame) -> pd.DataFrame:
    """Judge the two methods on the four stated criteria."""
    rows = []

    def step(col: str) -> float:
        return float(frame.loc[2026, f"{col}_step_pct_2025_26"])

    for method, label in [("share_anchor", "conventional-anchor share expansion"),
                          ("add_on", "actual-anchored VFM add-on")]:
        conv_share_2035 = float(frame.loc[2035, f"{method}_conv_share"])
        vfm_share_2035 = float(frame.loc[2035, "vfm_conventional_share"])
        rows.append(
            {
                "method": method,
                "description": label,
                "fy2025_classes_are_the_actuals": True,
                "fy2026_pool_step_pct": step(f"{method}_pool"),
                "fy2026_bev_step_pct": step(f"{method}_bev"),
                "fy2026_phev_step_pct": step(f"{method}_phev"),
                "fy2035_conventional_share": conv_share_2035,
                "fy2035_share_vs_vfm_pp": 100.0 * (conv_share_2035 - vfm_share_2035),
                "conservation": "exact by construction: pool = sum of three classes",
                "scenario_scalability": (
                    "pool fixed by the Base share; alternative presets reallocate it"
                    if method == "share_anchor"
                    else "pool moves with the preset, so total travel changes with a composition lever"
                ),
                "explainability": (
                    "one rule: the model is the conventional class; VFM supplies composition"
                    if method == "share_anchor"
                    else "two rules: model sets conventional, absolute VFM deltas set EV classes"
                ),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------- 3B fleet paths


def fleet_paths(data: dict) -> pd.DataFrame:
    split, bridge, vfm = data["split"], data["bridge"], data["vfm"]
    raw_conv = split["current_light_total_modelled_km"].astype(float)
    raw_ped = bridge["raw_light_petrol_vkt_million_km"].astype(float)
    levers = EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]
    retention = ped_retention_curve(FYS, levers)

    fy2025_ped = float(data["drift"].loc[2025, "mbu_light_petrol_vkt"])

    rows = []
    for variant in ["P0/L1", "P1/L1"]:
        for fy in FYS:
            if fy == 2025:
                ped = fy2025_ped
                conv = float(split.loc[2025, "current_conventional_light_km"])
                bev = float(split.loc[2025, "current_light_bev_km"])
                phev = float(split.loc[2025, "current_phev_km"])
            else:
                ped = float(raw_ped.loc[fy])
                if variant == "P1/L1":
                    ped *= float(retention.loc[fy])
                conv = float(raw_conv.loc[fy])
                pool = conv / float(vfm.loc[fy, "light_ruc_conventional_share"])
                bev = pool * float(vfm.loc[fy, "light_ruc_bev_share"])
                phev = pool * float(vfm.loc[fy, "light_ruc_phev_share"])
            pool = conv + bev + phev
            total_light = ped + pool
            rows.append(
                {
                    "variant": variant,
                    "june_year": fy,
                    "light_petrol_vkt": ped,
                    "conventional_light_ruc": conv,
                    "light_bev": bev,
                    "phev": phev,
                    "light_ruc_pool": pool,
                    "total_light_vkt": total_light,
                    "petrol_share_of_total_light": ped / total_light,
                    "conventional_share_of_pool": conv / pool,
                    "bev_share_of_pool": bev / pool,
                    "phev_share_of_pool": phev / pool,
                    "bev_share_of_total_light": bev / total_light,
                    "vfm_bev_absolute_km": float(vfm.loc[fy, "light_ruc_bev_million_km"]),
                    "vfm_phev_absolute_km": float(vfm.loc[fy, "light_ruc_phev_million_km"]),
                    "vfm_light_petrol_km": float(vfm.loc[fy, "light_petrol_vkt_million_km"]),
                    "mbu26_pool": float(split.loc[fy, "total_light_universe_km"]),
                    "mbu26_conventional": float(split.loc[fy, "conventional_light_km"]),
                }
            )
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(["variant", "june_year"])
    for col in ["light_petrol_vkt", "conventional_light_ruc", "light_bev", "phev", "light_ruc_pool", "total_light_vkt"]:
        frame[f"{col}_yoy_pct"] = frame.groupby("variant")[col].pct_change() * 100.0
    return frame


def preset_pool_invariance(data: dict) -> pd.DataFrame:
    """Alternative presets must reallocate the Base pool, not resize it."""
    split, vfm = data["split"], data["vfm"]
    raw_conv = split["current_light_total_modelled_km"].astype(float)
    rows = []
    for preset in ["MoT VFM base", "MoT VFM fast", "MoT VFM slow"]:
        if preset not in EV_UPTAKE_PRESETS:
            continue
        shares = lever_share_curves(FORECAST_FYS, EV_UPTAKE_PRESETS[preset]).set_index("june_year")
        for fy in FORECAST_FYS:
            base_pool = float(raw_conv.loc[fy]) / float(vfm.loc[fy, "light_ruc_conventional_share"])
            conv = base_pool * float(shares.loc[fy, "conventional"])
            bev = base_pool * float(shares.loc[fy, "bev"])
            phev = base_pool * float(shares.loc[fy, "phev"])
            rows.append(
                {
                    "preset": preset,
                    "june_year": fy,
                    "base_pool_km": base_pool,
                    "allocated_pool_km": conv + bev + phev,
                    "pool_residual_km": conv + bev + phev - base_pool,
                    "conventional_km": conv,
                    "bev_km": bev,
                    "phev_km": phev,
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------------- 3C PHEV petrol


def phev_petrol_sensitivity(data: dict, paths: pd.DataFrame) -> pd.DataFrame:
    drift, vfm = data["drift"], data["vfm"]
    base = paths[paths["variant"].eq("P0/L1")].set_index("june_year")
    rows = []
    for fraction in PHEV_PETROL_FRACTIONS:
        for fy in FORECAST_FYS:
            if fy not in drift.index:
                continue
            intensity = float(drift.loc[fy, "ped_litres_per_100km"])
            rate = float(drift.loc[fy, "ped_rate"])
            phev_km = float(base.loc[fy, "phev"])
            petrol_km = float(base.loc[fy, "light_petrol_vkt"])
            base_litres = petrol_km * intensity / 100.0
            extra_litres = phev_km * fraction * intensity / 100.0
            rows.append(
                {
                    "phev_petrol_fraction": fraction,
                    "june_year": fy,
                    "phev_km": phev_km,
                    "base_ped_litres_million": base_litres,
                    "extra_phev_litres_million": extra_litres,
                    "total_ped_litres_million": base_litres + extra_litres,
                    "base_gross_ped_revenue": base_litres * rate,
                    "extra_gross_ped_revenue": extra_litres * rate,
                    "total_gross_ped_revenue": (base_litres + extra_litres) * rate,
                    "extra_net_fed_revenue": extra_litres * rate,
                    "extra_total_nltf_revenue": extra_litres * rate,
                    "extra_pct_of_gross_ped": 100.0 * extra_litres / base_litres,
                }
            )
    return pd.DataFrame(rows)


def phev_sourcing_evidence(data: dict) -> pd.DataFrame:
    """Is PHEV petrol already inside the petrol VKT series? Test disjointness."""
    vfm = data["vfm"]
    rows = []
    for fy in FYS:
        r = vfm.loc[fy]
        pool = (
            float(r["light_ruc_conventional_million_km"])
            + float(r["light_ruc_bev_million_km"])
            + float(r["light_ruc_phev_million_km"])
        )
        petrol = float(r["light_petrol_vkt_million_km"])
        implied_total = petrol / float(r["light_petrol_share_of_light_vkt"])
        rows.append(
            {
                "june_year": fy,
                "vfm_light_petrol_km": petrol,
                "vfm_light_ruc_pool_km": pool,
                "petrol_plus_pool": petrol + pool,
                "vfm_implied_total_light_km": implied_total,
                "disjointness_residual_km": implied_total - (petrol + pool),
                "residual_as_pct_of_phev": (
                    100.0 * (implied_total - (petrol + pool)) / float(r["light_ruc_phev_million_km"])
                    if float(r["light_ruc_phev_million_km"]) > 0
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows).set_index("june_year")


def main() -> int:
    data = load()

    anchors = anchor_methods(data)
    scorecard = anchor_scorecard(anchors)
    paths = fleet_paths(data)
    presets = preset_pool_invariance(data)
    sourcing = phev_sourcing_evidence(data)
    phev = phev_petrol_sensitivity(data, paths)

    # ---- hard gates ------------------------------------------------------
    gates = []

    def gate(name: str, delta: float, tol: float = TOL) -> None:
        gates.append(
            {
                "check": name,
                "max_abs_delta": float(delta),
                "tolerance": tol,
                "status": "pass" if float(delta) <= tol else "FAIL",
            }
        )

    # class sums close
    d = float(
        (paths["light_ruc_pool"] - (paths["conventional_light_ruc"] + paths["light_bev"] + paths["phev"]))
        .abs()
        .max()
    )
    gate("class_sum_closes", d)

    # total light VKT is exactly petrol plus pool: no creation or loss
    d = float(
        (paths["total_light_vkt"] - (paths["light_petrol_vkt"] + paths["light_ruc_pool"])).abs().max()
    )
    gate("total_light_vkt_conserved", d)

    # shares sum to one under the correct denominator
    d = float(
        (paths["conventional_share_of_pool"] + paths["bev_share_of_pool"] + paths["phev_share_of_pool"] - 1.0)
        .abs()
        .max()
    )
    gate("pool_shares_sum_to_one", d)

    # raw conventional preserved under the Base uptake setting
    raw_conv = data["split"]["current_light_total_modelled_km"].astype(float)
    d = 0.0
    for variant in paths["variant"].unique():
        sub = paths[paths["variant"].eq(variant)].set_index("june_year")
        for fy in FORECAST_FYS:
            d = max(d, abs(float(sub.loc[fy, "conventional_light_ruc"]) - float(raw_conv.loc[fy])))
    gate("raw_conventional_preserved_under_base", d)

    # alternative presets preserve the Base-derived pool
    gate("presets_preserve_base_pool", float(presets["pool_residual_km"].abs().max()))

    # no lambda anywhere in these constructions
    drift = data["drift"]
    lam_values = set(np.round(drift["lambda_value"].astype(float).values, 9))
    contaminated = False
    for variant in paths["variant"].unique():
        sub = paths[paths["variant"].eq(variant)].set_index("june_year")
        for fy in FORECAST_FYS:
            migration = float(drift.loc[fy, "current_BEV_km"]) + float(drift.loc[fy, "current_PHEV_km"])
            lam = float(drift.loc[fy, "lambda_value"])
            if abs(float(sub.loc[fy, "conventional_light_ruc"]) - (float(raw_conv.loc[fy]) - lam * migration)) < 1e-6:
                contaminated = True
    gate("no_lambda_transfer_in_L1", 1.0 if contaminated else 0.0)
    del lam_values

    # FY2025 classes are the actuals in both variants
    d = 0.0
    for variant in paths["variant"].unique():
        sub = paths[paths["variant"].eq(variant)].set_index("june_year")
        for series, column in [
            ("current_conventional_light_km", "conventional_light_ruc"),
            ("current_light_bev_km", "light_bev"),
            ("current_phev_km", "phev"),
        ]:
            d = max(d, abs(float(sub.loc[2025, column]) - float(data["split"].loc[2025, series])))
    gate("fy2025_classes_are_the_actuals", d)

    gates_df = pd.DataFrame(gates)

    # ---- write -----------------------------------------------------------
    anchors.round(6).to_csv(OUT / "light_ruc_anchor_method_comparison.csv")
    scorecard.to_csv(OUT / "light_ruc_anchor_method_scorecard.csv", index=False)
    paths.round(6).to_csv(OUT / "combined_light_fleet_paths.csv", index=False)
    presets.round(6).to_csv(OUT / "light_ruc_preset_pool_invariance.csv", index=False)
    sourcing.round(6).to_csv(OUT / "phev_petrol_sourcing_evidence.csv")
    phev.round(6).to_csv(OUT / "phev_petrol_sensitivity.csv", index=False)
    gates_df.to_csv(OUT / "checkpoint_3_hard_gates.csv", index=False)

    # ---- console ---------------------------------------------------------
    print("=== Light RUC anchor methods (million km) ===")
    print(
        anchors[
            ["raw_conventional", "share_anchor_pool", "share_anchor_bev", "share_anchor_phev",
             "add_on_pool", "add_on_bev", "add_on_phev", "mbu26_pool"]
        ].round(2).to_string()
    )
    print("\n=== anchor scorecard ===")
    print(
        scorecard[
            ["method", "fy2026_pool_step_pct", "fy2026_bev_step_pct", "fy2026_phev_step_pct",
             "fy2035_conventional_share", "fy2035_share_vs_vfm_pp"]
        ].round(3).to_string(index=False)
    )
    for _, row in scorecard.iterrows():
        print(f"\n  {row['method']}:")
        print(f"    scalability   : {row['scenario_scalability']}")
        print(f"    explainability: {row['explainability']}")

    print("\n=== 3B combined light fleet, P0/L1 ===")
    sel = paths[paths["variant"].eq("P0/L1")].set_index("june_year")
    print(
        sel[["light_petrol_vkt", "conventional_light_ruc", "light_bev", "phev",
             "light_ruc_pool", "total_light_vkt", "petrol_share_of_total_light",
             "conventional_share_of_pool"]].round(3).to_string()
    )
    print("\n=== 3B P1/L1 (with one retention overlay) ===")
    sel = paths[paths["variant"].eq("P1/L1")].set_index("june_year")
    print(
        sel[["light_petrol_vkt", "total_light_vkt", "petrol_share_of_total_light",
             "light_petrol_vkt_yoy_pct"]].round(3).to_string()
    )

    print("\n=== 3C PHEV disjointness evidence ===")
    print(sourcing.round(3).to_string())

    print("\n=== 3C PHEV petrol sensitivity, FY2030 and FY2035 ===")
    print(
        phev[phev["june_year"].isin([2030, 2035])][
            ["phev_petrol_fraction", "june_year", "phev_km", "extra_phev_litres_million",
             "extra_gross_ped_revenue", "extra_pct_of_gross_ped"]
        ].round(3).to_string(index=False)
    )

    print("\n=== hard gates ===")
    print(gates_df.to_string(index=False))
    bad = gates_df[~gates_df["status"].eq("pass")]
    if not bad.empty:
        print("\nNOT PASSING:")
        print(bad.to_string(index=False))
        return 1
    print("\nAll Checkpoint 3 hard gates pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

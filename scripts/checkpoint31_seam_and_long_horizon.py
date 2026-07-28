"""Checkpoint 3.1B/3.1C: the actual/forecast seam, and the H21+ guard.

Every method here preserves the raw Light RUC model forecast exactly as the
conventional class. They differ only in how the class *share vector* moves from
the FY2025 actual shares to the VFM Base shares.

    blended_share_t = (1 - w_t) * FY2025_actual_share + w_t * VFM_share_t
    (normalised to sum to one)

    pool_t = raw_conventional_t / blended_conventional_share_t
    BEV_t  = pool_t * blended_BEV_share_t
    PHEV_t = pool_t * blended_PHEV_share_t

  A  immediate      w = 1 from FY2026
  B  two-year       w = 0, 0.5, 1
  C  three-year     w = 0, 1/3, 2/3, 1
  D  actual-anchored absolute add-on (no share blending)

3.1C then runs A, B and C to FY2050 against explicit watch/fail thresholds.

Investigation only. Writes only to artifacts/fleet_allocation_semantics/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.ev_uptake_levers import EV_UPTAKE_PRESETS, lever_share_curves  # noqa: E402

PACK = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
OUT = ROOT / "artifacts" / "fleet_allocation_semantics"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIO = "current_basecase"
ANCHOR_FY = 2025
SEAM_FYS = list(range(2025, 2036))
LONG_FYS = list(range(2025, 2051))
TOL = 1e-6

# Horizon governance: training cutoff 2025Q4, so FY2026 starts at H1.
VALIDATED_MAX_FY = 2028  # H1-H12
EXTENDED_MAX_FY = 2030  # H13-H20

SEAM_WEIGHTS = {
    "A_immediate": {2025: 0.0},  # everything after FY2025 is 1.0
    "B_two_year": {2025: 0.0, 2026: 0.5},
    "C_three_year": {2025: 0.0, 2026: 1.0 / 3.0, 2027: 2.0 / 3.0},
}

# 3.1C thresholds
POOL_GROWTH_WATCH_PCT = 6.0  # annual pool growth above this is a watch
POOL_GROWTH_FAIL_PCT = 10.0
CONV_SHARE_FLOOR_WATCH = 0.20  # dividing by a small share amplifies
CONV_SHARE_FLOOR_FAIL = 0.10
VFM_RATIO_WATCH = 1.25
VFM_RATIO_FAIL = 1.50


def load() -> dict:
    split = pd.read_csv(PACK / "ev_phev_split_assumptions.csv")
    base = split[split["scenario_name"].eq(SCENARIO)].set_index("FY").sort_index()
    official = split[split["scenario_name"].isna()].set_index("FY").sort_index()
    drift = pd.read_csv(PACK / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq(SCENARIO) & drift["lambda_mode"].astype(str).eq("optimized")
    ].set_index("FY").sort_index()
    bridge = pd.read_csv(PACK / "ped_revenue_bridge_audit.csv")
    bridge = bridge[bridge["scenario_name"].eq(SCENARIO)].set_index("FY").sort_index()
    vfm = pd.read_csv(ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
    return {
        "split": base,
        "official_split": official,
        "drift": drift,
        "bridge": bridge,
        "vfm": {
            name: frame.set_index("june_year").sort_index()
            for name, frame in vfm.groupby("scenario")
        },
    }


def horizon_state(fy: int) -> str:
    if fy <= ANCHOR_FY:
        return "actual_anchor"
    if fy <= VALIDATED_MAX_FY:
        return "backtest_supported_h1_h12"
    if fy <= EXTENDED_MAX_FY:
        return "extended_conditional_evidence_h13_h20"
    return "unvalidated_extrapolation_h21_plus"


def actual_shares(split: pd.DataFrame) -> dict[str, float]:
    conv = float(split.loc[ANCHOR_FY, "current_conventional_light_km"])
    bev = float(split.loc[ANCHOR_FY, "current_light_bev_km"])
    phev = float(split.loc[ANCHOR_FY, "current_phev_km"])
    pool = conv + bev + phev
    return {"conventional": conv / pool, "bev": bev / pool, "phev": phev / pool}


def blended_shares(
    method: str, fy: int, anchor: dict[str, float], vfm: pd.DataFrame
) -> tuple[dict[str, float], float]:
    weight = 1.0 if fy > max(SEAM_WEIGHTS[method]) else SEAM_WEIGHTS[method][fy]
    target = {
        "conventional": float(vfm.loc[fy, "light_ruc_conventional_share"]),
        "bev": float(vfm.loc[fy, "light_ruc_bev_share"]),
        "phev": float(vfm.loc[fy, "light_ruc_phev_share"]),
    }
    raw = {key: (1.0 - weight) * anchor[key] + weight * target[key] for key in target}
    total = sum(raw.values())
    return {key: value / total for key, value in raw.items()}, weight


def build_paths(data: dict) -> pd.DataFrame:
    split, vfm_base = data["split"], data["vfm"]["Base_EV"]
    raw_conv = split["current_light_total_modelled_km"].astype(float)
    anchor = actual_shares(split)
    a_conv = float(split.loc[ANCHOR_FY, "current_conventional_light_km"])
    a_bev = float(split.loc[ANCHOR_FY, "current_light_bev_km"])
    a_phev = float(split.loc[ANCHOR_FY, "current_phev_km"])
    vfm_bev_anchor = float(vfm_base.loc[ANCHOR_FY, "light_ruc_bev_million_km"])
    vfm_phev_anchor = float(vfm_base.loc[ANCHOR_FY, "light_ruc_phev_million_km"])

    rows = []
    for method in [*SEAM_WEIGHTS, "D_actual_anchored_add_on"]:
        for fy in LONG_FYS:
            conv = a_conv if fy == ANCHOR_FY else float(raw_conv.loc[fy])
            if fy == ANCHOR_FY:
                bev, phev, weight = a_bev, a_phev, 0.0
                shares = anchor
            elif method == "D_actual_anchored_add_on":
                weight = np.nan
                bev = a_bev + (float(vfm_base.loc[fy, "light_ruc_bev_million_km"]) - vfm_bev_anchor)
                phev = a_phev + (float(vfm_base.loc[fy, "light_ruc_phev_million_km"]) - vfm_phev_anchor)
                pool_tmp = conv + bev + phev
                shares = {
                    "conventional": conv / pool_tmp,
                    "bev": bev / pool_tmp,
                    "phev": phev / pool_tmp,
                }
            else:
                shares, weight = blended_shares(method, fy, anchor, vfm_base)
                pool = conv / shares["conventional"]
                bev = pool * shares["bev"]
                phev = pool * shares["phev"]
            pool = conv + bev + phev
            rows.append(
                {
                    "method": method,
                    "june_year": fy,
                    "seam_weight": weight,
                    "raw_conventional": conv,
                    "conventional": conv,
                    "bev": bev,
                    "phev": phev,
                    "pool": pool,
                    "conventional_share": shares["conventional"],
                    "bev_share": shares["bev"],
                    "phev_share": shares["phev"],
                    "vfm_base_conventional_share": float(vfm_base.loc[fy, "light_ruc_conventional_share"]),
                    "vfm_base_bev_share": float(vfm_base.loc[fy, "light_ruc_bev_share"]),
                    "vfm_base_pool": (
                        float(vfm_base.loc[fy, "light_ruc_conventional_million_km"])
                        + float(vfm_base.loc[fy, "light_ruc_bev_million_km"])
                        + float(vfm_base.loc[fy, "light_ruc_phev_million_km"])
                    ),
                    "horizon_state": horizon_state(fy),
                }
            )
    frame = pd.DataFrame(rows).sort_values(["method", "june_year"])
    for col in ["bev", "phev", "pool", "conventional"]:
        frame[f"{col}_yoy_pct"] = frame.groupby("method")[col].pct_change() * 100.0
    frame["pool_vs_vfm_base_ratio"] = frame["pool"] / frame["vfm_base_pool"]
    frame["conventional_share_gap_pp"] = 100.0 * (
        frame["conventional_share"] - frame["vfm_base_conventional_share"]
    )
    return frame


def in_vfm_cone(data: dict, frame: pd.DataFrame) -> pd.DataFrame:
    """Is each method's conventional share inside the VFM Fast/Slow cone?"""
    fast = data["vfm"]["Fast_EV"]["light_ruc_conventional_share"]
    slow = data["vfm"]["Slow_EV"]["light_ruc_conventional_share"]
    out = frame.copy()
    out["vfm_fast_conventional_share"] = out["june_year"].map(fast)
    out["vfm_slow_conventional_share"] = out["june_year"].map(slow)
    lower = np.minimum(out["vfm_fast_conventional_share"], out["vfm_slow_conventional_share"])
    upper = np.maximum(out["vfm_fast_conventional_share"], out["vfm_slow_conventional_share"])
    out["inside_vfm_cone"] = out["conventional_share"].between(lower - 1e-12, upper + 1e-12)
    return out


def seam_scorecard(data: dict, frame: pd.DataFrame) -> pd.DataFrame:
    split = data["split"]
    official = data["official_split"]
    # Observed FY2024 -> FY2025 growth, for a plausibility reference point.
    obs = {}
    if 2024 in official.index:
        obs = {
            "observed_fy2024_fy2025_bev_growth_pct": 100.0
            * (float(split.loc[2025, "current_light_bev_km"]) / float(official.loc[2024, "light_bev_km"]) - 1.0),
            "observed_fy2024_fy2025_phev_growth_pct": 100.0
            * (float(split.loc[2025, "current_phev_km"]) / float(official.loc[2024, "phev_km"]) - 1.0),
            "observed_fy2024_fy2025_pool_growth_pct": 100.0
            * (
                (float(split.loc[2025, "current_conventional_light_km"])
                 + float(split.loc[2025, "current_light_bev_km"])
                 + float(split.loc[2025, "current_phev_km"]))
                / float(official.loc[2024, "total_light_universe_km"])
                - 1.0
            ),
        }

    rows = []
    for method, sub in frame.groupby("method"):
        sub = sub.set_index("june_year")
        reached = [
            fy
            for fy in SEAM_FYS
            if fy > ANCHOR_FY and abs(float(sub.loc[fy, "conventional_share_gap_pp"])) < 1e-9
        ]
        rows.append(
            {
                "method": method,
                "fy2025_conventional_closes": abs(
                    float(sub.loc[2025, "conventional"])
                    - float(split.loc[2025, "current_conventional_light_km"])
                )
                < TOL,
                "fy2025_bev_closes": abs(
                    float(sub.loc[2025, "bev"]) - float(split.loc[2025, "current_light_bev_km"])
                )
                < TOL,
                "fy2026_bev_growth_pct": float(sub.loc[2026, "bev_yoy_pct"]),
                "fy2027_bev_growth_pct": float(sub.loc[2027, "bev_yoy_pct"]),
                "fy2026_phev_growth_pct": float(sub.loc[2026, "phev_yoy_pct"]),
                "fy2027_phev_growth_pct": float(sub.loc[2027, "phev_yoy_pct"]),
                "fy2026_pool_growth_pct": float(sub.loc[2026, "pool_yoy_pct"]),
                "fy2026_conventional_share_move_pp": 100.0
                * (float(sub.loc[2026, "conventional_share"]) - float(sub.loc[2025, "conventional_share"])),
                "vfm_base_shares_reached_by_fy": (min(reached) if reached else None),
                "fy2030_pool": float(sub.loc[2030, "pool"]),
                "fy2030_pool_vs_vfm_ratio": float(sub.loc[2030, "pool_vs_vfm_base_ratio"]),
                **obs,
            }
        )
    return pd.DataFrame(rows)


def long_horizon_guard(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method, sub in frame.groupby("method"):
        sub = sub.set_index("june_year")
        for fy in LONG_FYS:
            pool_growth = float(sub.loc[fy, "pool_yoy_pct"]) if fy > ANCHOR_FY else np.nan
            conv_share = float(sub.loc[fy, "conventional_share"])
            ratio = float(sub.loc[fy, "pool_vs_vfm_base_ratio"])
            flags = []
            if float(sub.loc[fy, "bev"]) < 0 or float(sub.loc[fy, "phev"]) < 0:
                flags.append("FAIL:negative_class")
            if not np.isnan(pool_growth):
                if pool_growth >= POOL_GROWTH_FAIL_PCT:
                    flags.append("FAIL:pool_growth")
                elif pool_growth >= POOL_GROWTH_WATCH_PCT:
                    flags.append("WATCH:pool_growth")
            if conv_share <= CONV_SHARE_FLOOR_FAIL:
                flags.append("FAIL:conventional_share_floor")
            elif conv_share <= CONV_SHARE_FLOOR_WATCH:
                flags.append("WATCH:conventional_share_floor")
            if ratio >= VFM_RATIO_FAIL:
                flags.append("FAIL:vfm_divergence")
            elif ratio >= VFM_RATIO_WATCH:
                flags.append("WATCH:vfm_divergence")
            rows.append(
                {
                    "method": method,
                    "june_year": fy,
                    "horizon_state": sub.loc[fy, "horizon_state"],
                    "raw_conventional": float(sub.loc[fy, "conventional"]),
                    "conventional_share": conv_share,
                    "pool": float(sub.loc[fy, "pool"]),
                    "bev": float(sub.loc[fy, "bev"]),
                    "phev": float(sub.loc[fy, "phev"]),
                    "pool_yoy_pct": pool_growth,
                    "pool_vs_vfm_base_ratio": ratio,
                    "flags": ";".join(flags),
                    "worst_flag": (
                        "FAIL" if any(f.startswith("FAIL") for f in flags)
                        else ("WATCH" if flags else "ok")
                    ),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    data = load()
    paths = build_paths(data)
    paths = in_vfm_cone(data, paths)
    scorecard = seam_scorecard(data, paths)
    guard = long_horizon_guard(paths)

    # ---- gates -----------------------------------------------------------
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

    raw_conv = data["split"]["current_light_total_modelled_km"].astype(float)
    worst = 0.0
    for method, sub in paths.groupby("method"):
        sub = sub.set_index("june_year")
        for fy in LONG_FYS:
            if fy == ANCHOR_FY:
                continue
            worst = max(worst, abs(float(sub.loc[fy, "conventional"]) - float(raw_conv.loc[fy])))
    gate("raw_conventional_preserved_under_every_seam_method", worst)

    gate(
        "share_vector_closes_to_one",
        float((paths["conventional_share"] + paths["bev_share"] + paths["phev_share"] - 1.0).abs().max()),
    )
    gate(
        "pool_equals_class_sum",
        float((paths["pool"] - (paths["conventional"] + paths["bev"] + paths["phev"])).abs().max()),
    )

    # No lambda value may reproduce any candidate conventional level.
    drift = data["drift"]
    worst_lam = 0.0
    for method, sub in paths.groupby("method"):
        sub = sub.set_index("june_year")
        for fy in LONG_FYS:
            if fy not in drift.index or fy == ANCHOR_FY:
                continue
            migration = float(drift.loc[fy, "current_BEV_km"]) + float(drift.loc[fy, "current_PHEV_km"])
            lam_level = float(raw_conv.loc[fy]) - float(drift.loc[fy, "lambda_value"]) * migration
            if abs(float(sub.loc[fy, "conventional"]) - lam_level) < 1e-6:
                worst_lam = 1.0
    gate("no_lambda_level_in_any_candidate_path", worst_lam)

    # Preset pool invariance under the chosen construction.
    vfm_base = data["vfm"]["Base_EV"]
    anchor = actual_shares(data["split"])
    worst_preset = 0.0
    for preset in EV_UPTAKE_PRESETS:
        shares = lever_share_curves([fy for fy in SEAM_FYS if fy > ANCHOR_FY], EV_UPTAKE_PRESETS[preset])
        shares = shares.set_index("june_year")
        for fy in SEAM_FYS:
            if fy == ANCHOR_FY:
                continue
            base_shares, _ = blended_shares("B_two_year", fy, anchor, vfm_base)
            base_pool = float(raw_conv.loc[fy]) / base_shares["conventional"]
            allocated = base_pool * (
                float(shares.loc[fy, "conventional"])
                + float(shares.loc[fy, "bev"])
                + float(shares.loc[fy, "phev"])
            )
            worst_preset = max(worst_preset, abs(allocated - base_pool))
    gate("presets_preserve_the_base_pool", worst_preset)

    gates_df = pd.DataFrame(gates)

    # ---- write -----------------------------------------------------------
    paths.round(6).to_csv(OUT / "light_ruc_seam_method_paths.csv", index=False)
    scorecard.round(4).to_csv(OUT / "light_ruc_seam_scorecard.csv", index=False)
    guard.round(6).to_csv(OUT / "light_ruc_long_horizon_guard.csv", index=False)
    gates_df.to_csv(OUT / "checkpoint_31_hard_gates.csv", index=False)

    # ---- console ---------------------------------------------------------
    print("=== 3.1B seam scorecard ===")
    print(
        scorecard[
            ["method", "fy2025_bev_closes", "fy2026_bev_growth_pct", "fy2027_bev_growth_pct",
             "fy2026_phev_growth_pct", "fy2026_pool_growth_pct", "fy2026_conventional_share_move_pp",
             "vfm_base_shares_reached_by_fy", "fy2030_pool"]
        ].round(2).to_string(index=False)
    )
    if "observed_fy2024_fy2025_bev_growth_pct" in scorecard.columns:
        row = scorecard.iloc[0]
        print(
            f"\nObserved FY2024->FY2025 actuals: BEV {row['observed_fy2024_fy2025_bev_growth_pct']:.1f}%, "
            f"PHEV {row['observed_fy2024_fy2025_phev_growth_pct']:.1f}%, "
            f"pool {row['observed_fy2024_fy2025_pool_growth_pct']:.1f}%"
        )

    print("\n=== VFM cone membership, conventional share ===")
    cone = paths[paths["june_year"].isin([2026, 2027, 2028, 2030])]
    print(
        cone.pivot_table(index="june_year", columns="method", values="inside_vfm_cone", aggfunc="first").to_string()
    )

    print("\n=== 3.1C long-horizon guard, worst flag by method and horizon state ===")
    summary = (
        guard.groupby(["method", "horizon_state"])["worst_flag"]
        .apply(lambda s: "FAIL" if (s == "FAIL").any() else ("WATCH" if (s == "WATCH").any() else "ok"))
        .unstack()
    )
    print(summary.to_string())

    print("\n=== 3.1C first FAIL year by method ===")
    for method, sub in guard.groupby("method"):
        fails = sub[sub["worst_flag"].eq("FAIL")]
        first = int(fails["june_year"].min()) if not fails.empty else None
        reason = fails.iloc[0]["flags"] if not fails.empty else "none"
        print(f"  {method}: first FAIL FY{first}  ({reason})" if first else f"  {method}: no FAIL to FY2050")

    print("\n=== 3.1C two-year method, selected years ===")
    sel = guard[guard["method"].eq("B_two_year")].set_index("june_year")
    print(
        sel.loc[[2026, 2028, 2030, 2035, 2040, 2045, 2050],
                ["horizon_state", "raw_conventional", "conventional_share", "pool",
                 "pool_yoy_pct", "pool_vs_vfm_base_ratio", "worst_flag"]].round(3).to_string()
    )

    print("\n=== gates ===")
    print(gates_df.to_string(index=False))
    bad = gates_df[~gates_df["status"].eq("pass")]
    if not bad.empty:
        print("\nNOT PASSING:")
        print(bad.to_string(index=False))
        return 1
    print("\nAll Checkpoint 3.1 hard gates pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

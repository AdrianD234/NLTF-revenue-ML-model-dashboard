"""Attribute the pack-to-front-end delta to the stage that actually causes it.

The gold-path gate previously compared the corrected pack directly against the
final front-end value. That comparison spans three legitimate transformations -
Treasury macro replay, fleet composition and the FED/RUC policy response - so it
cannot say which one moved a number, and it wrongly implies the final value
should equal the pre-macro pack value.

Stages reported per June year:

    S0  corrected pack (pre-macro)
    S1  after Treasury macro replay, before fleet composition
    S2  canonical allocation using the EXACT vendored VFM Base share table,
        rebuilt around the S1 conventional anchor
    S3  the current parametric "MoT VFM base" overlay actually shipped today
    S4  after the FED/RUC policy response

Isolated effects:

    macro          S1 - S0
    exact_vs_fit   S3 - S2   (the defect: fitted curve vs vendored table)
    composition    S3 - S1   (total effect of the shipped composition stage)
    policy         S4 - S3

Usage: python scripts/decompose_gold_path_stages.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DASHBOARD_ENGINE_DEFAULT", "ar1")

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.fuel_price_scenario import apply_treasury_macro_to_chart_rows  # noqa: E402
from model_dashboard.light_fleet_allocation import composition_shares  # noqa: E402
from model_dashboard.mbu26_source_spine import LIGHT_FLEET_BASE_UPTAKE_BASIS  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
)

OUT = ROOT / "artifacts" / "p0_light_fleet_fix"
PACK_DIR = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
FYS = (2026, 2027, 2028, 2030)
CLASSES = {
    "conventional": "light_ruc_net_km",
    "bev": "light_bev_ruc_net_km",
    "phev": "phev_ruc_net_km",
}
SIGNATURE: tuple[tuple[str, int, int], ...] = ()


def _value(rows: pd.DataFrame, role: str, series: str, fy: int) -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


def _classes(rows: pd.DataFrame, role: str, fy: int) -> dict[str, float]:
    out = {name: _value(rows, role, series, fy) for name, series in CLASSES.items()}
    out["pool"] = sum(value for value in out.values() if value == value)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pack = load_revenue_outlook_pack(PACK_DIR, repo_root=ROOT)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")

    # S0: corrected pack, sensitivity Off.
    _bridge, sensitivity_frames, _fast = app.cached_sensitivity_stage_frames(
        SIGNATURE, PED_BRIDGE_DEFAULT_MODE, sensitivity_key, pack
    )
    s0 = sensitivity_frames["chart_rows"]

    # S1: Treasury macro replay only.
    macro_replay, macro_error = app._safe_treasury_baseline_macro_replay(SIGNATURE, pack)
    fuel_replay, _ = app._safe_fuel_price_scenario_replay(SIGNATURE, pack)
    if fuel_replay is not None and not fuel_replay.policy_pair_factors.empty:
        macro_replay = fuel_replay
    if macro_replay is None:
        raise SystemExit(f"Treasury macro replay unavailable ({macro_error})")
    s1, _macro_audit = apply_treasury_macro_to_chart_rows(s0, macro_replay)

    # S3: the shipped composition stage (parametric "MoT VFM base"), no policy.
    default_key = (DEFAULT_EV_UPTAKE_MODE, (), (), app.FED_POLICY_PUBLISHED, app.FED_POLICY_PUBLISHED, False)
    s3, _uptake_audit, _eruc_audit, _ = app._apply_scenario_overlays(
        s1.copy(),
        app._pack_table(pack, "ev_phev_ped_light_drift_assumptions"),
        app._resolve_ev_uptake_levers(default_key),
        app._resolve_eruc_levers(default_key),
        app.cached_fed_uplift_factors(SIGNATURE, pack),
        adjust_ped=False,
        fed_policy_scopes=(),
    )

    # S4: full default front end (current delayed policy, MBU26 published).
    s4_key = (DEFAULT_EV_UPTAKE_MODE, (), (), app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED, False)
    s4, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, s4_key, pack
    )

    records: list[dict[str, object]] = []
    for role in ("basecase", "comparison"):
        for fy in FYS:
            stage0 = _classes(s0, role, fy)
            stage1 = _classes(s1, role, fy)
            stage3 = _classes(s3, role, fy)
            stage4 = _classes(s4, role, fy)

            # S2: canonical exact-VFM allocation rebuilt around the S1 anchor.
            shares, vfm_scenario = composition_shares(
                fy, repo_root=ROOT, uptake_basis=LIGHT_FLEET_BASE_UPTAKE_BASIS
            )
            anchor = stage1["conventional"]
            base_pool = anchor / shares["conventional"]
            stage2 = {
                "conventional": anchor,
                "bev": base_pool * shares["bev"],
                "phev": base_pool * shares["phev"],
            }
            stage2["pool"] = sum(stage2.values())

            for name in ("conventional", "bev", "phev", "pool"):
                records.append(
                    {
                        "scenario_role": role,
                        "fy": fy,
                        "class": name,
                        "S0_pack": stage0[name],
                        "S1_post_macro": stage1[name],
                        "S2_canonical_exact_vfm": stage2[name],
                        "S3_parametric_overlay": stage3[name],
                        "S4_post_policy": stage4[name],
                        "macro_effect": stage1[name] - stage0[name],
                        "exact_vs_fitted": stage3[name] - stage2[name],
                        "composition_effect": stage3[name] - stage1[name],
                        "policy_effect": stage4[name] - stage3[name],
                        "vfm_scenario": vfm_scenario,
                        "exact_base_conventional_share": shares["conventional"],
                        "exact_base_bev_share": shares["bev"],
                        "exact_base_phev_share": shares["phev"],
                    }
                )

    frame = pd.DataFrame(records)
    frame.to_csv(OUT / "gold_path_stage_decomposition.csv", index=False)

    pd.set_option("display.width", 250)
    base = frame[frame["scenario_role"].eq("basecase")]
    for name in ("conventional", "bev", "phev", "pool"):
        subset = base[base["class"].eq(name)].set_index("fy")
        print(f"\n=== {name} (current_basecase, million km) ===")
        print(
            subset[
                [
                    "S0_pack",
                    "S1_post_macro",
                    "S2_canonical_exact_vfm",
                    "S3_parametric_overlay",
                    "S4_post_policy",
                    "macro_effect",
                    "exact_vs_fitted",
                    "composition_effect",
                    "policy_effect",
                ]
            ].to_string(float_format=lambda value: f"{value:,.3f}")
        )

    print("\n=== attribution of the pack -> front-end delta (basecase) ===")
    for name in ("conventional", "pool"):
        subset = base[base["class"].eq(name)].set_index("fy")
        print(f"\n{name}:")
        for fy in FYS:
            row = subset.loc[fy]
            total = float(row["S4_post_policy"]) - float(row["S0_pack"])
            print(
                f"  FY{fy}: total {total:10.3f} = macro {float(row['macro_effect']):10.3f}"
                f" + composition {float(row['composition_effect']):10.3f}"
                f" + policy {float(row['policy_effect']):10.3f}"
                f"   [of which exact-vs-fitted {float(row['exact_vs_fitted']):10.3f}]"
            )

    print(f"\nwrote {OUT / 'gold_path_stage_decomposition.csv'} ({len(frame)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

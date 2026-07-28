"""Attribute the pack-to-front-end delta to the stage that actually causes it.

The original gold-path gate compared the corrected pack directly against the
final front-end value. That comparison spans three legitimate transformations -
Treasury macro replay, fleet composition and the FED/RUC policy response - so it
cannot say which one moved a number, and it wrongly implies the final value
should equal the pre-macro pack value.

Stages per June year:

    S0  corrected pack (pre-macro)
    S1  after Treasury macro replay, before any composition
    S2  canonical composition: EXACT vendored VFM Base shares rebuilt around
        the S1 conventional anchor. This is what the default now ships.
    S3  after the selected optional composition sensitivities (none by
        default, so S3 == S2 on the default path)
    S4  after the FED/RUC policy response

``S3_alt_parametric_fit`` records what the retired fitted "MoT VFM base" curve
produced, so the size of the correction stays visible rather than disappearing
once the default is fixed.

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
from model_dashboard.ev_uptake_levers import (  # noqa: E402
    DEFAULT_EV_UPTAKE_MODE,
    PARAMETRIC_VFM_BASE_FIT_OPTION,
)
from model_dashboard.fuel_price_scenario import apply_treasury_macro_to_chart_rows  # noqa: E402
from model_dashboard.light_fleet_allocation import composition_shares  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
)

OUT = ROOT / "artifacts" / "p0_light_fleet_fix"
PACK_DIR = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
FYS = (2026, 2027, 2028, 2030)
ROLES = ("basecase", "comparison")
SIGNATURE: tuple[tuple[str, int, int], ...] = ()

# Light classes are summed into the pool; everything else is reported flat.
LIGHT_CLASSES = {
    "light_conventional_km": "light_ruc_net_km",
    "light_bev_km": "light_bev_ruc_net_km",
    "light_phev_km": "phev_ruc_net_km",
}
OTHER_SERIES = {
    "heavy_conventional_km": "heavy_ruc_net_km",
    "heavy_conventional_revenue": "heavy_ruc_net_revenue",
    "light_petrol_vkt": "light_petrol_vkt",
    "net_fed_revenue": "net_fed_revenue",
    "total_ruc_net_revenue": "total_ruc_net_revenue",
    "total_nltf_net_revenue": "total_nltf_net_revenue",
}
# Heavy BEV never becomes a chart row: it is a hidden fixed MBU26 leaf carried
# in the line reconciliation. It still belongs in this audit, because "Heavy
# BEV km stay fixed" is precisely the contract the default overlay was
# breaking from the other side.
HIDDEN_FIXED_SERIES = {
    "heavy_bev_km": "heavy_bev_ruc_net_km",
    "heavy_bev_revenue": "heavy_bev_ruc_net_revenue",
}


def _value(rows: pd.DataFrame, series: str, fy: int, role: str) -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


def _hidden_leaf(line_reconciliation: pd.DataFrame, series: str, fy: int, role: str) -> float:
    source_path = "Current finalist Base case" if role == "basecase" else "Current finalist High population/comparison"
    selected = line_reconciliation[
        line_reconciliation["series_id"].astype(str).eq(series)
        & line_reconciliation["source_path"].astype(str).eq(source_path)
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


def _measures(rows: pd.DataFrame, fy: int, role: str, line_reconciliation: pd.DataFrame) -> dict[str, float]:
    out = {name: _value(rows, series, fy, role) for name, series in LIGHT_CLASSES.items()}
    out["light_pool_km"] = sum(value for value in out.values() if value == value)
    for name, series in OTHER_SERIES.items():
        out[name] = _value(rows, series, fy, role)
    for name, series in HIDDEN_FIXED_SERIES.items():
        out[name] = _hidden_leaf(line_reconciliation, series, fy, role)
    return out


def _compose(rows: pd.DataFrame, pack, mode: str) -> pd.DataFrame:
    key = (mode, (), (), app.FED_POLICY_PUBLISHED, app.FED_POLICY_PUBLISHED, False, False)
    out, *_ = app._apply_scenario_overlays(
        rows.copy(),
        app._pack_table(pack, "ev_phev_ped_light_drift_assumptions"),
        app._resolve_ev_uptake_levers(key),
        app._resolve_eruc_levers(key),
        app.cached_fed_uplift_factors(SIGNATURE, pack),
        adjust_ped=False,
        fed_policy_scopes=(),
        uptake_basis=app._resolve_uptake_basis(key),
        heavy_bev_transition=app._heavy_bev_transition_enabled(key),
    )
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pack = load_revenue_outlook_pack(PACK_DIR, repo_root=ROOT)
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")

    _bridge, frames, _fast = app.cached_sensitivity_stage_frames(
        SIGNATURE, PED_BRIDGE_DEFAULT_MODE, sensitivity_key, pack
    )
    s0 = frames["chart_rows"]

    macro_replay, macro_error = app._safe_treasury_baseline_macro_replay(SIGNATURE, pack)
    fuel_replay, _ = app._safe_fuel_price_scenario_replay(SIGNATURE, pack)
    if fuel_replay is not None and not fuel_replay.policy_pair_factors.empty:
        macro_replay = fuel_replay
    if macro_replay is None:
        raise SystemExit(f"Treasury macro replay unavailable ({macro_error})")
    s1, _macro_audit = apply_treasury_macro_to_chart_rows(s0, macro_replay)

    s2 = _compose(s1, pack, DEFAULT_EV_UPTAKE_MODE)
    s3 = s2  # no optional composition sensitivity is selected by default
    s3_alt = _compose(s1, pack, PARAMETRIC_VFM_BASE_FIT_OPTION)

    s4_key = (
        DEFAULT_EV_UPTAKE_MODE, (), (), app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED, False, False,
    )
    s4, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, s4_key, pack
    )

    records: list[dict[str, object]] = []
    for role in ROLES:
        for fy in FYS:
            stages = {name: _measures(rows, fy, role, pack.revenue_line_reconciliation) for name, rows in
                      (("S0", s0), ("S1", s1), ("S2", s2), ("S3", s3), ("S3_alt", s3_alt), ("S4", s4))}
            shares, vfm_scenario = composition_shares(
                fy, repo_root=ROOT, uptake_basis=DEFAULT_EV_UPTAKE_MODE
            )
            for measure in stages["S0"]:
                records.append(
                    {
                        "scenario_role": role,
                        "fy": fy,
                        "measure": measure,
                        "S0_pack": stages["S0"][measure],
                        "S1_post_macro": stages["S1"][measure],
                        "S2_canonical_exact_vfm": stages["S2"][measure],
                        "S3_selected_sensitivities": stages["S3"][measure],
                        "S3_alt_parametric_fit": stages["S3_alt"][measure],
                        "S4_post_policy": stages["S4"][measure],
                        "macro_effect": stages["S1"][measure] - stages["S0"][measure],
                        "canonical_composition_effect": stages["S2"][measure] - stages["S1"][measure],
                        "optional_composition_effect": stages["S3"][measure] - stages["S2"][measure],
                        "retired_fit_vs_canonical": stages["S3_alt"][measure] - stages["S2"][measure],
                        "policy_effect": stages["S4"][measure] - stages["S3"][measure],
                        "vfm_scenario": vfm_scenario,
                        "exact_base_conventional_share": shares["conventional"],
                        "exact_base_bev_share": shares["bev"],
                        "exact_base_phev_share": shares["phev"],
                    }
                )

    frame = pd.DataFrame(records)
    frame.to_csv(OUT / "gold_path_stage_decomposition.csv", index=False)

    pd.set_option("display.width", 260)
    base = frame[frame["scenario_role"].eq("basecase")]
    columns = [
        "S0_pack",
        "S1_post_macro",
        "S2_canonical_exact_vfm",
        "S4_post_policy",
        "macro_effect",
        "canonical_composition_effect",
        "retired_fit_vs_canonical",
        "policy_effect",
    ]
    for measure in (
        "light_conventional_km",
        "light_pool_km",
        "heavy_conventional_km",
        "heavy_bev_km",
        "total_ruc_net_revenue",
        "total_nltf_net_revenue",
    ):
        subset = base[base["measure"].eq(measure)].set_index("fy")
        print(f"\n=== {measure} (current_basecase) ===")
        print(subset[columns].to_string(float_format=lambda value: f"{value:,.3f}"))

    failures: list[str] = []
    for role in ROLES:
        rows = frame[frame["scenario_role"].eq(role)].set_index(["measure", "fy"])
        for fy in FYS:
            if abs(float(rows.loc[("light_conventional_km", fy), "canonical_composition_effect"])) > 1e-6:
                failures.append(f"{role} FY{fy}: canonical composition moved the conventional anchor")
            for measure in ("heavy_conventional_km", "heavy_bev_km", "heavy_conventional_revenue"):
                if abs(float(rows.loc[(measure, fy), "canonical_composition_effect"])) > 1e-9:
                    failures.append(f"{role} FY{fy}: composition reclassified {measure}")
            if abs(float(rows.loc[("light_petrol_vkt", fy), "canonical_composition_effect"])) > 1e-9:
                failures.append(f"{role} FY{fy}: composition moved PED activity (retention must be Off)")

    print(f"\nwrote {OUT / 'gold_path_stage_decomposition.csv'} ({len(frame)} rows)")
    if failures:
        print("\nFAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nPASS: default composition is neutral for Light anchor, Heavy and PED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

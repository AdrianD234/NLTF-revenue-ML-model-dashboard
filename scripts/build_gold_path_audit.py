"""Gold-path end-to-end audit through the real application functions.

Not a hand-built approximation: this drives the same cached_* entry points the
Streamlit views call, with the default front-end settings, so what it reports
is what a user sees.

The gates are stated PER STAGE. An earlier version compared the corrected pack
directly against the final front-end value, which spans Treasury macro, fleet
composition and the FED/RUC policy response at once, and so wrongly required
the final value to equal the pre-macro pack value.

    S0  corrected pack (pre-macro)
    S1  after Treasury macro replay
    S2  canonical exact-VFM Base composition around the S1 anchor
    S3  after selected optional composition sensitivities (none by default)
    S4  after the FED/RUC policy response

Usage: python scripts/build_gold_path_audit.py
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
    EXACT_VFM_UPTAKE_BASES,
)
from model_dashboard.fuel_price_scenario import apply_treasury_macro_to_chart_rows  # noqa: E402
from model_dashboard.light_fleet_allocation import (  # noqa: E402
    LAST_DECISION_GRADE_ANNUAL_FY,
    composition_shares,
)
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
)

OUT = ROOT / "artifacts" / "p0_light_fleet_fix"
PACK_DIR = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
FYS = (2026, 2027, 2028, 2030)
ROLES = ("basecase", "comparison")
TOL = 1e-6
SIGNATURE: tuple[tuple[str, int, int], ...] = ()

MEASURES = {
    "light_petrol_vkt": "light_petrol_vkt",
    "light_ruc_conventional_km": "light_ruc_net_km",
    "light_bev_km": "light_bev_ruc_net_km",
    "phev_km": "phev_ruc_net_km",
    "heavy_ruc_conventional_km": "heavy_ruc_net_km",
    "net_fed_revenue": "net_fed_revenue",
    "total_ruc_net_revenue": "total_ruc_net_revenue",
    "total_nltf_net_revenue": "total_nltf_net_revenue",
}
LIGHT_POOL = ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")


def _value(rows: pd.DataFrame, series: str, fy: int, role: str) -> float:
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq(role)
        & rows["series_id"].astype(str).eq(series)
        & pd.to_numeric(rows["june_year"], errors="coerce").eq(fy)
    ]
    values = pd.to_numeric(selected["value"], errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else float("nan")


def _pool(rows: pd.DataFrame, fy: int, role: str) -> float:
    return sum(_value(rows, series, fy, role) for series in LIGHT_POOL)


def _key(mode: str, current_policy: str, mbu_policy: str, *, retention: bool = False, heavy: bool = False):
    return (mode, (), (), current_policy, mbu_policy, retention, heavy)


def _compose(rows: pd.DataFrame, pack, key) -> pd.DataFrame:
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
    failures: list[str] = []

    _bridge, frames, _fast = app.cached_sensitivity_stage_frames(
        SIGNATURE, PED_BRIDGE_DEFAULT_MODE, sensitivity_key, pack
    )
    s0 = frames["chart_rows"]

    # P1.2: the overlay requires per-scenario factors; the fuel result's
    # baseline factors are Base-only and would fail closed on the comparison.
    macro_replay, macro_error = app._safe_treasury_baseline_macro_replay(SIGNATURE, pack)
    if macro_replay is None:
        raise SystemExit(f"Treasury macro replay unavailable ({macro_error})")
    s1, _ = apply_treasury_macro_to_chart_rows(s0, macro_replay)

    default_key = _key(DEFAULT_EV_UPTAKE_MODE, app.FED_POLICY_PUBLISHED, app.FED_POLICY_PUBLISHED)
    s2 = _compose(s1, pack, default_key)
    s3 = _compose(s1, pack, default_key)  # no optional sensitivity selected
    s4_key = _key(DEFAULT_EV_UPTAKE_MODE, app.FED_POLICY_DELAYED_6M, app.FED_POLICY_PUBLISHED)
    s4, *_ = app.cached_scenario_overlay_rows(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, s4_key, pack
    )

    records: list[dict[str, object]] = []
    for role in ROLES:
        for fy in FYS:
            shares, _ = composition_shares(fy, repo_root=ROOT, uptake_basis=DEFAULT_EV_UPTAKE_MODE)
            for label, series in MEASURES.items():
                records.append(
                    {
                        "scenario_role": role,
                        "fy": fy,
                        "measure": label,
                        "S0_pack": _value(s0, series, fy, role),
                        "S1_post_macro": _value(s1, series, fy, role),
                        "S2_canonical_exact_vfm": _value(s2, series, fy, role),
                        "S3_selected_sensitivities": _value(s3, series, fy, role),
                        "S4_post_policy": _value(s4, series, fy, role),
                    }
                )
            records.append(
                {
                    "scenario_role": role,
                    "fy": fy,
                    "measure": "light_ruc_pool_km",
                    "S0_pack": _pool(s0, fy, role),
                    "S1_post_macro": _pool(s1, fy, role),
                    "S2_canonical_exact_vfm": _pool(s2, fy, role),
                    "S3_selected_sensitivities": _pool(s3, fy, role),
                    "S4_post_policy": _pool(s4, fy, role),
                }
            )

            # ---- hard default gates, per stage --------------------------
            if abs(_value(s2, "light_ruc_net_km", fy, role) - _value(s1, "light_ruc_net_km", fy, role)) > TOL:
                failures.append(f"{role} FY{fy}: S2 Light conventional != S1 anchor")
            if abs(_pool(s2, fy, role) - _value(s2, "light_ruc_net_km", fy, role) / shares["conventional"]) > TOL:
                failures.append(f"{role} FY{fy}: S2 pool != conventional / exact Base conventional share")
            for series in LIGHT_POOL + ("heavy_ruc_net_km", "heavy_ruc_net_revenue", "light_petrol_vkt"):
                if abs(_value(s3, series, fy, role) - _value(s2, series, fy, role)) > TOL:
                    failures.append(f"{role} FY{fy}: S3 != S2 for {series} with no sensitivity selected")
            for series in ("heavy_ruc_net_km", "heavy_ruc_net_revenue"):
                if abs(_value(s2, series, fy, role) - _value(s1, series, fy, role)) > TOL:
                    failures.append(f"{role} FY{fy}: composition moved {series}")
            if abs(_value(s2, "light_petrol_vkt", fy, role) - _value(s1, "light_petrol_vkt", fy, role)) > TOL:
                failures.append(f"{role} FY{fy}: composition moved PED activity (retention must be Off)")
            for series in ("light_bev_ruc_net_km", "phev_ruc_net_km"):
                if abs(_value(s4, series, fy, role) - _value(s3, series, fy, role)) > TOL:
                    failures.append(f"{role} FY{fy}: policy moved {series}")

    # Policy applied exactly once: the delayed response lands in FY2027 only.
    for role in ROLES:
        moved = [
            fy
            for fy in FYS
            if abs(_value(s4, "light_ruc_net_km", fy, role) - _value(s3, "light_ruc_net_km", fy, role)) > TOL
        ]
        if moved != [2027]:
            failures.append(f"{role}: delayed policy moved conventional in {moved}, expected [2027]")

    # Horizon contracts survive the exact-share tables, which run to FY2050.
    current_annual = s4[
        s4["time_grain"].astype(str).eq("june_year") & s4["scenario_role"].astype(str).isin(ROLES)
    ]
    last_current = int(pd.to_numeric(current_annual["june_year"], errors="coerce").max())
    if last_current != LAST_DECISION_GRADE_ANNUAL_FY:
        failures.append(f"current annual reaches FY{last_current}, expected FY{LAST_DECISION_GRADE_ANNUAL_FY}")
    official_annual = s4[s4["scenario_role"].astype(str).eq("official_comparator")]
    last_official = int(pd.to_numeric(official_annual["june_year"], errors="coerce").max())
    if last_official <= LAST_DECISION_GRADE_ANNUAL_FY:
        failures.append(f"official comparator stops at FY{last_official}")

    # Alternative composition modes preserve each scenario's own Base pool.
    for mode in EXACT_VFM_UPTAKE_BASES:
        alt = _compose(s1, pack, _key(mode, app.FED_POLICY_PUBLISHED, app.FED_POLICY_PUBLISHED))
        for role in ROLES:
            for fy in FYS:
                if abs(_pool(alt, fy, role) - _pool(s2, fy, role)) > TOL:
                    failures.append(f"{mode} resized the {role} FY{fy} Base pool")

    # Chart and line reconciliation agree on the final default output.
    line, _residuals, stack, _bridge = app.cached_aligned_scenario_detail_frames(
        SIGNATURE, sensitivity_key, PED_BRIDGE_DEFAULT_MODE, s4_key, pack
    )
    for fy in FYS:
        chart_value = _value(s4, "total_nltf_net_revenue", fy, "basecase")
        matched = line[
            line["FY"].astype("Int64").eq(fy)
            & line["series_id"].astype(str).eq("total_nltf_net_revenue")
            & line["source_path"].astype(str).str.contains("Base", case=False, na=False)
        ]
        values = pd.to_numeric(matched["value"], errors="coerce").dropna()
        if not len(values) or abs(float(values.iloc[0]) - chart_value) > TOL:
            failures.append(f"FY{fy}: chart and line reconciliation disagree")

    audit = pd.DataFrame(records)
    audit.to_csv(OUT / "gold_path_audit.csv", index=False)

    pd.set_option("display.width", 240)
    print(f"gold path audit rows: {len(audit)} -> {OUT / 'gold_path_audit.csv'}")
    for role in ROLES:
        subset = audit[audit["scenario_role"].eq(role)]
        print(f"\n=== {role}: final displayed values (S4, current delayed / MBU26 published) ===")
        print(
            subset.pivot_table(index="measure", columns="fy", values="S4_post_policy", sort=False).to_string(
                float_format=lambda value: f"{value:,.3f}"
            )
        )
    print(f"\nlast current annual FY : {last_current}")
    print(f"last official annual FY: {last_official}")
    print(f"stack rows             : {len(stack)}")

    if failures:
        print("\nFAIL")
        for item in dict.fromkeys(failures):
            print(f"  - {item}")
        return 1
    print("\nPASS: every gold-path stage gate holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

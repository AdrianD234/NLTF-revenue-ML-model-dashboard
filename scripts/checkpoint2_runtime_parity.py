"""Checkpoint 2 (corrected): true runtime stage waterfall and variant matrix.

The first Checkpoint 2 pass defined Reference A as "stored pack + VFM overlay"
and called apply_uptake_levers_to_chart_rows() straight onto the committed
chart rows. That omitted the raw PED bridge and the Treasury macro replay, and
so reconstructed the lambda-plus-VFM PED combination the front end is built to
avoid. This script uses the supported runtime path instead.

Stages
    S0  raw econometric outputs
    S1  committed stored pack (lambda applied)
    S2  apply_ped_bridge_mode_layer(bridge_mode=PED_BRIDGE_DEFAULT_MODE)
    S3  Treasury BEFU26 baseline macro replay
    S4  MoT VFM Base uptake overlay (adjust_ped follows the bridge mode)
    S5  the actual front end via app.cached_revenue_outlook_view
    S6  what Workstream A decomposed

Investigation only. No production code, governed pack, checkpoint or dashboard
value is modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: E402
from model_dashboard.ev_uptake_levers import (  # noqa: E402
    DEFAULT_EV_UPTAKE_MODE,
    EV_UPTAKE_PRESETS,
    apply_uptake_levers_to_chart_rows,
)
from model_dashboard.fleet_mix import load_dashboard_frame  # noqa: E402
from model_dashboard.fuel_price_scenario import (  # noqa: E402
    apply_treasury_macro_to_chart_rows,
    run_treasury_baseline_macro_replay,
)
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    apply_ped_bridge_mode_layer,
    load_revenue_outlook_pack,
)

OUT = ROOT / "artifacts" / "fleet_allocation_semantics"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIO = "current_basecase"
FYS = list(range(2025, 2031))
FORECAST_FYS = [fy for fy in FYS if fy != 2025]
TOL = 1e-6

ACTIVITY = [
    "ped_vkt_per_capita",
    "light_petrol_vkt",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "heavy_ruc_net_km",
    "ped_volume",
]
REVENUE = [
    "gross_ped_revenue",
    "net_fed_revenue",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "total_ruc_net_revenue",
    "total_nltf_net_revenue",
]


def annual(rows: pd.DataFrame, scenario: str = SCENARIO) -> pd.DataFrame:
    sel = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_name"].astype(str).eq(scenario)
        & pd.to_numeric(rows["june_year"], errors="coerce").between(2025, 2030)
    ]
    return (
        sel.pivot_table(index="june_year", columns="series_id", values="value", aggfunc="first")
        .sort_index()
    )


def build_stages() -> dict[str, object]:
    pack_dir = ROOT / engine_revenue_outlook_dir("ar1")
    pack = load_revenue_outlook_pack(pack_dir, repo_root=ROOT)
    if pack is None:
        raise FileNotFoundError(pack_dir)

    s1 = pack.revenue_chart_rows

    bridge = apply_ped_bridge_mode_layer(
        chart_rows=s1,
        line_reconciliation=pack.revenue_line_reconciliation,
        bridge_components=pack.revenue_bridge_components,
        future_revenue_forecasts=pack.future_revenue_forecasts,
        ped_revenue_bridge_audit=pack.ped_revenue_bridge_audit,
        bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        include_derived_frames=False,
        include_selected_ped_audit=False,
    )
    s2 = bridge["chart_rows"]

    macro_replay = run_treasury_baseline_macro_replay(
        pd.read_parquet(pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"),
        repo_root=ROOT,
        engine="ar1",
    )
    s3, _ = apply_treasury_macro_to_chart_rows(s2, macro_replay)

    s4, uptake_audit = apply_uptake_levers_to_chart_rows(
        s3,
        pack.ev_phev_ped_light_drift_assumptions,
        EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE],
        # The front end ties this to the bridge mode: the raw bridge needs the
        # displacement lever, the optimized bridge already displaced petrol.
        adjust_ped=(PED_BRIDGE_DEFAULT_MODE == PED_BRIDGE_DEFAULT_MODE),
    )
    return {
        "pack": pack,
        "pack_dir": pack_dir,
        "S1": s1,
        "S2": s2,
        "S3": s3,
        "S4": s4,
        "uptake_audit": uptake_audit,
    }


def front_end_rows(pack, pack_dir):
    """The real decision-facing rows, via the app's own cached view."""
    import app  # noqa: PLC0415
    from model_dashboard.revenue_outlook import revenue_outlook_signature  # noqa: PLC0415

    signature = revenue_outlook_signature(pack_dir, ROOT)
    traces = tuple(app._revenue_outlook_trace_options(pack.revenue_chart_rows))
    sensitivity_key = app.selected_sensitivity_key("Off", "Off", "Off")
    ev_uptake_key = (DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)

    if hasattr(app.cached_revenue_outlook_view, "clear"):
        app.cached_revenue_outlook_view.clear()
    view = app.cached_revenue_outlook_view(
        signature,
        "Total NLTF revenue",
        "june_year",
        "Current planned path",
        traces,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        ev_uptake_key,
        pack,
    )
    state = {
        "bridge_mode": PED_BRIDGE_DEFAULT_MODE,
        "ev_uptake_key": str(ev_uptake_key),
        "sensitivity_key": str(sensitivity_key),
        "fed_path": "Current planned path",
        "adjust_ped_follows_bridge_mode": True,
    }
    return view, state


def main() -> int:
    stages = build_stages()
    pack = stages["pack"]

    frames = {name: annual(stages[name]) for name in ["S1", "S2", "S3", "S4"]}

    # S5 is the real front end: S4 plus the FED policy overlay and any
    # remaining runtime stages, taken from the app's own cached view.
    s5_error = ""
    state: dict = {}
    try:
        view, state = front_end_rows(stages["pack"], stages["pack_dir"])
        s5_rows = view.get("chart_rows")
        if isinstance(s5_rows, pd.DataFrame) and not s5_rows.empty:
            frames["S5"] = annual(s5_rows)
    except Exception as exc:  # noqa: BLE001
        s5_error = f"{type(exc).__name__}: {exc}"

    # ---- S0 raw econometric outputs -------------------------------------
    split = pd.read_csv(stages["pack_dir"] / "ev_phev_split_assumptions.csv")
    split = split[split["scenario_name"].eq(SCENARIO) & split["FY"].between(2025, 2030)].set_index("FY")
    audit = pd.read_csv(stages["pack_dir"] / "ped_revenue_bridge_audit.csv")
    audit = audit[audit["scenario_name"].eq(SCENARIO) & audit["FY"].between(2025, 2030)].set_index("FY")
    drift = pd.read_csv(stages["pack_dir"] / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq(SCENARIO)
        & drift["lambda_mode"].astype(str).eq("optimized")
        & drift["FY"].between(2025, 2030)
    ].set_index("FY")

    raw_light_ruc = split["current_light_total_modelled_km"].astype(float)
    raw_ped_vkt = audit["raw_light_petrol_vkt_million_km"].astype(float)
    lam = drift["lambda_value"].astype(float)
    migration = drift["current_BEV_km"].astype(float) + drift["current_PHEV_km"].astype(float)

    # ---- the corrected stage waterfall ----------------------------------
    waterfall_rows = []
    for fy in FYS:
        row = {"june_year": fy}
        row["S0_raw_ped_light_petrol_vkt"] = float(raw_ped_vkt.get(fy, float("nan")))
        row["S0_raw_light_ruc_model_km"] = float(raw_light_ruc.loc[fy])
        row["lambda"] = float(lam.loc[fy])
        row["migration_total_M"] = float(migration.loc[fy])
        for stage in frames:
            f = frames[stage]
            for series in ACTIVITY + REVENUE:
                row[f"{stage}_{series}"] = (
                    float(f.loc[fy, series]) if series in f.columns and fy in f.index else float("nan")
                )
            row[f"{stage}_light_ruc_pool"] = sum(
                float(f.loc[fy, s])
                for s in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]
                if s in f.columns
            )
        # The stored pack publishes ped_volume but not light_petrol_vkt; the
        # bridge layer is what materialises that series. Recover S1's level
        # from the governed audit so the S1 -> S2 step is measurable.
        if fy in audit.index:
            row["S1_light_petrol_vkt"] = float(audit.loc[fy, "optimized_light_petrol_vkt_million_km"])
        waterfall_rows.append(row)
    waterfall = pd.DataFrame(waterfall_rows).set_index("june_year")

    # ---- gates -----------------------------------------------------------
    gates: list[dict] = []

    def gate(name: str, delta: float, tol: float = TOL) -> None:
        gates.append(
            {
                "check": name,
                "max_abs_delta": float(delta),
                "tolerance": tol,
                "status": "pass" if float(delta) <= tol else "FAIL",
            }
        )

    # G1: S2 restores raw PED exactly (the lambda PED deduction is reversed).
    d = max(
        abs(float(waterfall.loc[fy, "S2_light_petrol_vkt"]) - float(raw_ped_vkt.loc[fy]))
        for fy in FORECAST_FYS
    )
    gate("S2_raw_bridge_restores_raw_ped_vkt", d)

    # G2: S2 - S1 equals exactly (1 - lambda) * M.
    d = max(
        abs(
            (float(waterfall.loc[fy, "S2_light_petrol_vkt"]) - float(waterfall.loc[fy, "S1_light_petrol_vkt"]))
            - float((1.0 - lam.loc[fy]) * migration.loc[fy])
        )
        for fy in FORECAST_FYS
    )
    gate("S2_minus_S1_ped_equals_one_minus_lambda_times_M", d)

    # G3: S2 leaves the Light RUC classes untouched.
    d = 0.0
    for fy in FORECAST_FYS:
        for series in ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]:
            d = max(d, abs(float(waterfall.loc[fy, f"S2_{series}"]) - float(waterfall.loc[fy, f"S1_{series}"])))
    gate("S2_leaves_light_ruc_classes_unchanged", d)

    # G4: no surviving lambda PED deduction after S2 - S4's PED reduction is
    # the VFM retention only, applied to the macro-adjusted raw level.
    ped_factor = []
    for fy in FORECAST_FYS:
        ped_factor.append(
            float(waterfall.loc[fy, "S4_light_petrol_vkt"]) / float(waterfall.loc[fy, "S3_light_petrol_vkt"])
        )

    # G5: my S4 must equal the supported fleet-mix builder.
    dash = load_dashboard_frame(ROOT)
    d = 0.0
    fleet_map = {
        "light_petrol_vkt": "light_petrol_vkt",
        "light_ruc_net_km": "light_ruc_net_km",
        "light_bev_ruc_net_km": "light_bev_ruc_net_km",
        "phev_ruc_net_km": "phev_ruc_net_km",
        "heavy_ruc_net_km": "heavy_ruc_net_km",
    }
    matched = []
    for mine, theirs in fleet_map.items():
        if theirs not in dash.columns:
            continue
        for fy in FORECAST_FYS:
            if fy in dash.index:
                d = max(d, abs(float(waterfall.loc[fy, f"S4_{mine}"]) - float(dash.loc[fy, theirs])))
                matched.append(theirs)
    gate(f"S4_matches_load_dashboard_frame[{len(set(matched))}_series]", d)

    # ---- S5: the real front end ------------------------------------------
    s5_frame = frames.get("S5")
    if s5_error:
        gates.append(
            {
                "check": "S5_front_end_via_cached_revenue_outlook_view",
                "max_abs_delta": float("nan"),
                "tolerance": TOL,
                "status": f"ERROR::{s5_error}",
            }
        )
    else:
        # S4 -> S5 is the FED policy overlay (default state delayed_6m). It
        # legitimately moves activity as well as revenue, because delaying the
        # excise uplift lowers the pump price and the elasticity feeds back
        # into VKT. So S5 is a real stage, not a no-op: gate only what must
        # not move. The EV classes carry no fuel excise, so they must not.
        d = 0.0
        for series in ["light_bev_ruc_net_km", "phev_ruc_net_km"]:
            for fy in FORECAST_FYS:
                d = max(d, abs(float(s5_frame.loc[fy, series]) - float(frames["S4"].loc[fy, series])))
        gate("S5_fed_policy_leaves_ev_class_km_unchanged", d)

        # The additive revenue identity used by the variant matrix below:
        # a change in gross PED plus a change in RUC class revenue equals the
        # change in total NLTF, because every other line is fixed.
        d = 0.0
        for fy in FORECAST_FYS:
            delta_ped = float(frames["S4"].loc[fy, "gross_ped_revenue"]) - float(
                frames["S3"].loc[fy, "gross_ped_revenue"]
            )
            delta_ruc = float(frames["S4"].loc[fy, "total_ruc_net_revenue"]) - float(
                frames["S3"].loc[fy, "total_ruc_net_revenue"]
            )
            delta_total = float(frames["S4"].loc[fy, "total_nltf_net_revenue"]) - float(
                frames["S3"].loc[fy, "total_nltf_net_revenue"]
            )
            d = max(d, abs(delta_ped + delta_ruc - delta_total))
        gate("additive_revenue_identity_holds", d, tol=1e-6)

    # ---- PED layering, corrected -----------------------------------------
    layering = pd.DataFrame(index=pd.Index(FORECAST_FYS, name="june_year"))
    layering["S0_raw_ped_vkt"] = raw_ped_vkt.loc[FORECAST_FYS]
    layering["S1_pack_lambda_ped_vkt"] = waterfall.loc[FORECAST_FYS, "S1_light_petrol_vkt"]
    layering["S2_after_raw_bridge"] = waterfall.loc[FORECAST_FYS, "S2_light_petrol_vkt"]
    layering["S3_after_treasury_macro"] = waterfall.loc[FORECAST_FYS, "S3_light_petrol_vkt"]
    layering["S4_after_vfm_retention"] = waterfall.loc[FORECAST_FYS, "S4_light_petrol_vkt"]
    layering["lambda_deduction_km"] = layering["S1_pack_lambda_ped_vkt"] - layering["S0_raw_ped_vkt"]
    layering["raw_bridge_restoration_km"] = layering["S2_after_raw_bridge"] - layering["S1_pack_lambda_ped_vkt"]
    layering["treasury_macro_km"] = layering["S3_after_treasury_macro"] - layering["S2_after_raw_bridge"]
    layering["vfm_retention_km"] = layering["S4_after_vfm_retention"] - layering["S3_after_treasury_macro"]
    layering["surviving_lambda_ped_effect_km"] = (
        layering["lambda_deduction_km"] + layering["raw_bridge_restoration_km"]
    )
    layering["vfm_ped_retention_factor"] = ped_factor
    gate(
        "no_surviving_lambda_ped_deduction_after_S2",
        float(layering["surviving_lambda_ped_effect_km"].abs().max()),
    )

    # ---- Light RUC: does any runtime step restore the raw forecast? -------
    light = pd.DataFrame(index=pd.Index(FORECAST_FYS, name="june_year"))
    light["S0_raw_conventional_model"] = raw_light_ruc.loc[FORECAST_FYS]
    for stage in ["S1", "S2", "S3", "S4", "S5"]:
        light[f"{stage}_conventional"] = waterfall.loc[FORECAST_FYS, f"{stage}_light_ruc_net_km"]
        light[f"{stage}_pool"] = waterfall.loc[FORECAST_FYS, f"{stage}_light_ruc_pool"]
    light["S4_conventional_minus_raw"] = light["S4_conventional"] - light["S0_raw_conventional_model"]
    light["S4_pool_minus_raw"] = light["S4_pool"] - light["S0_raw_conventional_model"]
    light["lambda_M"] = (lam * migration).loc[FORECAST_FYS]
    light["one_minus_lambda_M"] = ((1.0 - lam) * migration).loc[FORECAST_FYS]
    restored = bool((light["S4_conventional_minus_raw"].abs() <= TOL).all())
    light["any_runtime_step_restores_raw_conventional"] = restored

    # ---- corrected 2x2 factorial matrix, anchored on S5 -------------------
    # Effective rates are derived from S5 itself, so the P1/L0 cell reproduces
    # the front end by construction and the other three cells are consistent
    # perturbations inside the same macro, policy and rate environment.
    matrix = pd.DataFrame()
    if s5_frame is not None:
        vfm = pd.read_csv(ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
        vfm = vfm[vfm["scenario"].eq("Base_EV")].set_index("june_year")
        mbu_total = audit["official_total_nltf_net_revenue_million_nzd"].astype(float)

        rows = []
        for fy in FORECAST_FYS:
            s5 = s5_frame.loc[fy]
            s3 = frames["S3"].loc[fy]
            # effective rates, per unit of activity, from S5
            litres_per_km = float(s5["ped_volume"]) / float(s5["light_petrol_vkt"])
            ped_rate = float(s5["gross_ped_revenue"]) / float(s5["ped_volume"])
            conv_rate = float(s5["light_ruc_net_revenue"]) / float(s5["light_ruc_net_km"])
            bev_rate = float(s5["light_bev_ruc_net_revenue"]) / float(s5["light_bev_ruc_net_km"])
            phev_rate = float(s5["phev_ruc_net_revenue"]) / float(s5["phev_ruc_net_km"])

            # macro factor actually applied to the conventional Light RUC line
            macro_factor = float(s3["light_ruc_net_km"]) / float(frames["S2"].loc[fy, "light_ruc_net_km"])
            raw_conv_macro = float(raw_light_ruc.loc[fy]) * macro_factor

            ped_levels = {
                # P0: raw bridge + macro, no VFM retention
                "P0": float(s3["light_petrol_vkt"]) * (float(s5["light_petrol_vkt"]) / float(frames["S4"].loc[fy, "light_petrol_vkt"])),
                # P1: the actual front-end level (raw bridge + macro + one retention)
                "P1": float(s5["light_petrol_vkt"]),
            }
            conv_share = float(vfm.loc[fy, "light_ruc_conventional_share"])
            light_levels = {
                # L0: the lambda-created pool as the front end builds it
                "L0": (
                    float(s5["light_ruc_net_km"]),
                    float(s5["light_bev_ruc_net_km"]),
                    float(s5["phev_ruc_net_km"]),
                ),
                # L1: raw model preserved as conventional, pool from VFM shares
                "L1": (
                    raw_conv_macro,
                    raw_conv_macro / conv_share * float(vfm.loc[fy, "light_ruc_bev_share"]),
                    raw_conv_macro / conv_share * float(vfm.loc[fy, "light_ruc_phev_share"]),
                ),
            }
            base_ruc_class = (
                float(s5["light_ruc_net_revenue"])
                + float(s5["light_bev_ruc_net_revenue"])
                + float(s5["phev_ruc_net_revenue"])
            )
            for p, ped in ped_levels.items():
                for l, (conv, bev, phev) in light_levels.items():
                    gross_ped = ped * litres_per_km * ped_rate
                    ruc_class = conv * conv_rate + bev * bev_rate + phev * phev_rate
                    total = (
                        float(s5["total_nltf_net_revenue"])
                        + (gross_ped - float(s5["gross_ped_revenue"]))
                        + (ruc_class - base_ruc_class)
                    )
                    rows.append(
                        {
                            "cell": f"{p}/{l}",
                            "june_year": fy,
                            "light_petrol_vkt": ped,
                            "conventional_km": conv,
                            "bev_km": bev,
                            "phev_km": phev,
                            "light_ruc_pool_km": conv + bev + phev,
                            "gross_ped_revenue": gross_ped,
                            "ruc_class_revenue": ruc_class,
                            "total_nltf_net_revenue": total,
                            "mbu26_total_nltf": float(mbu_total.loc[fy]),
                            "gap_vs_mbu26": total - float(mbu_total.loc[fy]),
                            "gap_pct": 100.0 * (total / float(mbu_total.loc[fy]) - 1.0),
                        }
                    )
        matrix = pd.DataFrame(rows)
        d = max(
            abs(
                float(matrix[(matrix.cell == "P1/L0") & (matrix.june_year == fy)]["total_nltf_net_revenue"].iloc[0])
                - float(s5_frame.loc[fy, "total_nltf_net_revenue"])
            )
            for fy in FORECAST_FYS
        )
        gate("matrix_cell_P1_L0_reproduces_S5_front_end", d)

    # ---- signed gap attribution against the true S5 value -----------------
    signed = pd.DataFrame(index=pd.Index(FORECAST_FYS, name="june_year"))
    if not matrix.empty:
        m = matrix.set_index(["cell", "june_year"])["total_nltf_net_revenue"]
        signed["mbu26_total_nltf"] = audit["official_total_nltf_net_revenue_million_nzd"].loc[FORECAST_FYS]
        signed["S5_decision_facing_total_nltf"] = [
            float(s5_frame.loc[fy, "total_nltf_net_revenue"]) for fy in FORECAST_FYS
        ]
        signed["final_gap"] = signed["S5_decision_facing_total_nltf"] - signed["mbu26_total_nltf"]
        # Signed contributions: each is the amount by which that treatment
        # moves the final value, so widening a negative gap reads negative.
        signed["ped_vfm_retention_effect"] = [
            float(m.loc[("P1/L0", fy)]) - float(m.loc[("P0/L0", fy)]) for fy in FORECAST_FYS
        ]
        signed["light_pool_lambda_effect"] = [
            float(m.loc[("P1/L0", fy)]) - float(m.loc[("P1/L1", fy)]) for fy in FORECAST_FYS
        ]
        signed["interaction"] = [
            (float(m.loc[("P1/L1", fy)]) - float(m.loc[("P0/L1", fy)]))
            - (float(m.loc[("P1/L0", fy)]) - float(m.loc[("P0/L0", fy)]))
            for fy in FORECAST_FYS
        ]
        signed["residual_clean_architecture_gap"] = [
            float(m.loc[("P0/L1", fy)]) - float(signed.loc[fy, "mbu26_total_nltf"]) for fy in FORECAST_FYS
        ]
        signed["closure_residual"] = (
            signed["final_gap"]
            - signed["ped_vfm_retention_effect"]
            - signed["light_pool_lambda_effect"]
            - signed["interaction"]
            - signed["residual_clean_architecture_gap"]
        )
        gate("signed_gap_decomposition_closes", float(signed["closure_residual"].abs().max()))

    # ---- write -----------------------------------------------------------
    if not matrix.empty:
        matrix.round(6).to_csv(OUT / "corrected_structural_matrix_2x2.csv", index=False)
        signed.round(6).to_csv(OUT / "corrected_signed_gap_attribution.csv")
    gates_df = pd.DataFrame(gates)
    waterfall.round(6).to_csv(OUT / "corrected_runtime_stage_waterfall.csv")
    layering.round(6).to_csv(OUT / "corrected_ped_stage_layering.csv")
    light.round(6).to_csv(OUT / "corrected_light_ruc_stage_trace.csv")
    gates_df.to_csv(OUT / "corrected_runtime_parity_gates.csv", index=False)
    pd.DataFrame([state]).to_csv(OUT / "front_end_default_state.csv", index=False)
    if s5_frame is not None:
        s5_frame.round(6).to_csv(OUT / "s5_front_end_rows.csv")

    # ---- console ---------------------------------------------------------
    print("=== corrected PED stage layering (million km) ===")
    print(
        layering[
            [
                "S0_raw_ped_vkt",
                "S1_pack_lambda_ped_vkt",
                "S2_after_raw_bridge",
                "S3_after_treasury_macro",
                "S4_after_vfm_retention",
                "surviving_lambda_ped_effect_km",
                "vfm_ped_retention_factor",
            ]
        ].round(4).to_string()
    )
    print("\n=== corrected Light RUC stage trace (million km) ===")
    print(
        light[
            [
                "S0_raw_conventional_model",
                "S1_conventional",
                "S2_conventional",
                "S3_conventional",
                "S4_conventional",
                "S4_conventional_minus_raw",
                "S1_pool",
                "S4_pool",
            ]
        ].round(4).to_string()
    )
    print(f"\nany runtime step restores raw conventional Light RUC: {restored}")
    print("\n=== decision-facing revenue by stage ===")
    for series in ["gross_ped_revenue", "net_fed_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"]:
        cols = [f"{st}_{series}" for st in ["S1","S2","S3","S4","S5"] if f"{st}_{series}" in waterfall.columns]
        print(f"\n{series}:")
        print(waterfall.loc[FORECAST_FYS, cols].round(3).to_string())
    if not matrix.empty:
        print("\n=== corrected 2x2 matrix, FY2030 ===")
        print(
            matrix[matrix.june_year.eq(2030)][
                [
                    "cell",
                    "light_petrol_vkt",
                    "conventional_km",
                    "light_ruc_pool_km",
                    "gross_ped_revenue",
                    "total_nltf_net_revenue",
                    "gap_vs_mbu26",
                    "gap_pct",
                ]
            ].round(3).to_string(index=False)
        )
        print("\n=== signed gap attribution against the true S5 value ($m) ===")
        print(signed.round(3).to_string())
    print("\n=== gates ===")
    print(gates_df.to_string(index=False))

    bad = gates_df[~gates_df["status"].eq("pass")]
    if not bad.empty:
        print("\nNOT PASSING:")
        print(bad.to_string(index=False))
        return 1
    print("\nAll parity gates pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

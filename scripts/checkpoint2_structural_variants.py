"""Checkpoint 2: runtime stage waterfall and structural variant matrix.

Investigation only. Reads governed packs; writes evidence to
artifacts/fleet_allocation_semantics/. No production code, governed pack,
checkpoint or dashboard value is modified.

Stages
    S0  raw econometric outputs (replay-verified scenario inputs)
    S1  committed AR(1) pack (lambda migration already applied)
    S2  raw PED bridge (vktpc x population -> litres -> revenue)
    S3  Treasury macro / rate + intensity path (MBU26 official rows)
    S4  MoT VFM 202405 uptake overlay (runtime display overlay)
    S5  front end (decision-facing values)
    S6  what Workstream A decomposed

Variants
    A  final decision-facing path (S1 + S4)
    B  stored pack before the VFM overlay (S1)
    C  semantic clean anchor: raw PED passthrough + raw Light RUC as the
       conventional anchor, pool inferred from VFM Base shares
    D  isolate PED: raw PED passthrough, current Light RUC treatment
    E  isolate Light RUC: current PED treatment, Variant C Light RUC method
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
    apply_uptake_levers_to_chart_rows,
)

PACK = ROOT / "data" / "engine_ar1" / "current_revenue_outlook"
OUT = ROOT / "artifacts" / "fleet_allocation_semantics"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIO = "current_basecase"
FYS = list(range(2025, 2031))
FORECAST_FYS = [fy for fy in FYS if fy != 2025]
CLOSURE_TOL = 1e-6

# Revenue lines taken unchanged from the official spine in every variant.
FIXED_LINES = [
    "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_revenue",
    "ruc_refunds",
    "ruc_admin_revenue",
    "gross_lpg_revenue",
    "gross_cng_revenue",
    "fed_refunds",
    "mr1_revenue",
    "mr2_revenue",
    "coo_revenue",
    "mvr_admin_revenue",
    "mvr_refunds",
    "tuc_net_revenue",
]


def load_inputs() -> dict[str, pd.DataFrame]:
    drift = pd.read_csv(PACK / "ev_phev_ped_light_drift_assumptions.csv")
    drift = drift[
        drift["scenario_name"].eq(SCENARIO)
        & drift["lambda_mode"].astype(str).eq("optimized")
        & drift["FY"].between(2025, 2030)
    ].set_index("FY").sort_index()

    bridge = pd.read_csv(PACK / "ped_revenue_bridge_audit.csv")
    bridge = bridge[
        bridge["scenario_name"].eq(SCENARIO) & bridge["FY"].between(2025, 2030)
    ].set_index("FY").sort_index()

    split = pd.read_csv(PACK / "ev_phev_split_assumptions.csv")
    split = split[
        split["scenario_name"].eq(SCENARIO) & split["FY"].between(2025, 2030)
    ].set_index("FY").sort_index()

    lines = pd.read_csv(PACK / "revenue_line_reconciliation.csv")
    lines = lines[lines["scenario_name"].eq(SCENARIO) & lines["FY"].between(2025, 2030)]
    fixed = lines.pivot_table(
        index="FY", columns="series_id", values="value", aggfunc="first"
    ).sort_index()

    chart = pd.read_csv(PACK / "revenue_chart_rows.csv")

    vfm = pd.read_csv(ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv")
    vfm = vfm[vfm["scenario"].eq("Base_EV")].set_index("june_year").sort_index()

    replay = pd.read_csv(PACK / "scenario_input_replay_mismatch_report.csv")
    replay = replay[
        replay["scenario_name"].eq(SCENARIO)
        & replay["series_id"].eq("current_light_ruc_total_modelled_km")
    ]

    return {
        "drift": drift,
        "bridge": bridge,
        "split": split,
        "fixed": fixed,
        "chart": chart,
        "vfm": vfm,
        "replay": replay,
    }


# ---------------------------------------------------------------- revenue identity


def revenue_from_activity(
    fy: int,
    *,
    light_petrol_vkt: float,
    conventional_km: float,
    bev_km: float,
    phev_km: float,
    drift: pd.DataFrame,
    fixed: pd.DataFrame,
) -> dict[str, float]:
    """The governed revenue identity, applied to a variant's activity levels.

    Rates, intensity, refunds, admin and every non-light line come from the
    official spine and are identical across variants; only the four activity
    levels differ.
    """
    d = drift.loc[fy]
    f = fixed.loc[fy]

    ped_volume = light_petrol_vkt * float(d["ped_litres_per_100km"]) / 100.0
    gross_ped = ped_volume * float(d["ped_rate"])
    gross_fed = gross_ped + float(f["gross_lpg_revenue"]) + float(f["gross_cng_revenue"])
    net_fed = gross_fed - float(f["fed_refunds"])

    light_rev = conventional_km * float(d["conventional_light_rate"])
    bev_rev = bev_km * float(d["light_bev_rate"])
    phev_rev = phev_km * float(d["phev_rate"])

    gross_ruc = (
        light_rev
        + float(f["heavy_ruc_net_revenue"])
        + bev_rev
        + float(f["heavy_bev_ruc_net_revenue"])
        + phev_rev
        + float(f["ruc_refunds"])
    )
    ruc_net_admin = gross_ruc - float(f["ruc_admin_revenue"])
    total_ruc = ruc_net_admin - float(f["ruc_refunds"])

    gross_mvr = float(f["mr1_revenue"]) + float(f["mr2_revenue"]) + float(f["coo_revenue"])
    net_mvr = float(f["mr1_revenue"]) + float(f["mr2_revenue"]) - float(f["mvr_admin_revenue"])
    net_mvr -= float(f["mvr_refunds"])

    total_gross = gross_ruc + gross_fed + gross_mvr + float(f["tuc_net_revenue"])
    total_admin = (
        float(f["ruc_admin_revenue"]) + float(f["mvr_admin_revenue"]) + float(f["coo_revenue"])
    )
    total_net_admin = total_gross - total_admin
    total_refunds = float(f["ruc_refunds"]) + float(f["fed_refunds"]) + float(f["mvr_refunds"])
    total_nltf = total_net_admin - total_refunds

    return {
        "light_petrol_vkt_million_km": light_petrol_vkt,
        "light_ruc_net_km": conventional_km,
        "light_bev_ruc_net_km": bev_km,
        "phev_ruc_net_km": phev_km,
        "light_ruc_pool_km": conventional_km + bev_km + phev_km,
        "ped_volume_million_litres": ped_volume,
        "gross_ped_revenue": gross_ped,
        "gross_fed_revenue": gross_fed,
        "net_fed_revenue": net_fed,
        "light_ruc_net_revenue": light_rev,
        "light_bev_ruc_net_revenue": bev_rev,
        "phev_ruc_net_revenue": phev_rev,
        "light_ruc_class_revenue": light_rev + bev_rev + phev_rev,
        "gross_ruc_revenue": gross_ruc,
        "total_ruc_net_revenue": total_ruc,
        "net_mvr_revenue": net_mvr,
        "total_nltf_net_revenue": total_nltf,
    }


# ---------------------------------------------------------------- reference A


def reference_a(chart: pd.DataFrame) -> pd.DataFrame:
    """Final decision-facing path: stored pack plus the default VFM overlay."""
    drift_all = pd.read_csv(PACK / "ev_phev_ped_light_drift_assumptions.csv")
    levers = EV_UPTAKE_PRESETS[DEFAULT_EV_UPTAKE_MODE]
    adjusted, audit = apply_uptake_levers_to_chart_rows(
        chart, drift_all, levers, adjust_ped=True
    )
    rows = adjusted[
        adjusted["time_grain"].eq("june_year")
        & adjusted["scenario_name"].eq(SCENARIO)
        & adjusted["june_year"].between(2025, 2030)
    ]
    frame = rows.pivot_table(
        index="june_year", columns="series_id", values="value", aggfunc="first"
    ).sort_index()
    return frame, audit


# ---------------------------------------------------------------- main


def main() -> int:
    data = load_inputs()
    drift, bridge, split = data["drift"], data["bridge"], data["split"]
    fixed, vfm = data["fixed"], data["vfm"]

    # ---- S0: raw econometric outputs, replay-verified -------------------
    raw_light_ruc = split["current_light_total_modelled_km"].astype(float)
    raw_ped_vkt = bridge["raw_light_petrol_vkt_million_km"].astype(float)

    replay_annual = (
        data["replay"]
        .assign(fy=lambda f: f["annual_period"].str.replace("FY", "", regex=False).astype(int))
        .groupby("fy")["committed_forecast_value"]
        .first()
    )
    for fy in FORECAST_FYS:
        assert abs(float(replay_annual.loc[fy]) - float(raw_light_ruc.loc[fy])) < 1e-9, fy
    replay_status = set(
        data["replay"][data["replay"]["replay_status"].notna()]["replay_status"]
    )

    # ---- the lambda transfer identity ----------------------------------
    lam = drift["lambda_value"].astype(float)
    migration = drift["current_BEV_km"].astype(float) + drift["current_PHEV_km"].astype(float)
    waterfall = pd.DataFrame(index=pd.Index(FYS, name="june_year"))
    waterfall["S0_raw_light_ruc_model_km"] = raw_light_ruc
    waterfall["S0_raw_ped_light_petrol_vkt_km"] = raw_ped_vkt
    waterfall["S1_lambda_value"] = lam
    waterfall["S1_migration_total_km"] = migration
    waterfall["S1_taken_from_light_ruc_km"] = lam * migration
    waterfall["S1_taken_from_ped_km"] = (1.0 - lam) * migration
    waterfall["S1_pack_conventional_km"] = split["current_conventional_light_km"].astype(float)
    waterfall["S1_pack_bev_km"] = split["current_light_bev_km"].astype(float)
    waterfall["S1_pack_phev_km"] = split["current_phev_km"].astype(float)
    waterfall["S1_pack_class_sum_km"] = split["current_allocation_sum_km"].astype(float)
    waterfall["S1_pack_ped_light_petrol_vkt_km"] = bridge[
        "optimized_light_petrol_vkt_million_km"
    ].astype(float)
    waterfall["conventional_minus_raw_km"] = (
        waterfall["S1_pack_conventional_km"] - waterfall["S0_raw_light_ruc_model_km"]
    )
    waterfall["class_sum_minus_raw_km"] = (
        waterfall["S1_pack_class_sum_km"] - waterfall["S0_raw_light_ruc_model_km"]
    )
    waterfall["ped_minus_raw_km"] = (
        waterfall["S1_pack_ped_light_petrol_vkt_km"] - waterfall["S0_raw_ped_light_petrol_vkt_km"]
    )
    waterfall["universe_U_t_km"] = drift["current_U_t_light_mobility_km"].astype(float)
    waterfall["mbu26_universe_km"] = drift["mbu_total_light_mobility_km"].astype(float)
    waterfall["mbu26_universe_ev_phev_km"] = (
        drift["mbu_light_bev_km"].astype(float) + drift["mbu_phev_km"].astype(float)
    )
    waterfall["mbu26_conventional_km"] = split["conventional_light_km"].astype(float)
    waterfall["mbu26_pool_km"] = split["total_light_universe_km"].astype(float)

    # ---- variants ------------------------------------------------------
    vfm_conv = vfm["light_ruc_conventional_share"].astype(float)
    vfm_bev = vfm["light_ruc_bev_share"].astype(float)
    vfm_phev = vfm["light_ruc_phev_share"].astype(float)

    def clean_light_ruc(fy: int) -> tuple[float, float, float]:
        """Conventional-anchor expansion: pool = raw_conventional / VFM share."""
        conv = float(raw_light_ruc.loc[fy])
        pool = conv / float(vfm_conv.loc[fy])
        return conv, pool * float(vfm_bev.loc[fy]), pool * float(vfm_phev.loc[fy])

    def pack_light_ruc(fy: int) -> tuple[float, float, float]:
        return (
            float(split["current_conventional_light_km"].loc[fy]),
            float(split["current_light_bev_km"].loc[fy]),
            float(split["current_phev_km"].loc[fy]),
        )

    definitions = [
        ("B_stored_pack", "raw PED minus (1-lambda)M", "raw Light RUC minus lambda*M; BEV/PHEV = M x MBU26 shares"),
        ("C_semantic_clean_anchor", "raw AR(1) vktpc x population, no migration transfer", "raw model = conventional anchor; pool = conventional / VFM Base share"),
        ("D_isolate_ped", "raw AR(1) vktpc x population, no migration transfer", "unchanged: stored pack lambda allocation"),
        ("E_isolate_light_ruc", "unchanged: stored pack lambda allocation", "raw model = conventional anchor; pool = conventional / VFM Base share"),
    ]

    records: list[dict] = []
    for name, _, _ in definitions:
        for fy in FYS:
            if fy == 2025:
                # Hard test 1: the FY2025 actual anchor is never re-allocated.
                # The PED bridge audit starts at FY2026; FY2025 light-petrol VKT
                # is the MBU26 actual carried in the drift table.
                conv = float(split["current_conventional_light_km"].loc[2025])
                bev = float(split["current_light_bev_km"].loc[2025])
                phev = float(split["current_phev_km"].loc[2025])
                ped = float(drift["mbu_light_petrol_vkt"].loc[2025])
            else:
                if name == "B_stored_pack":
                    ped = float(bridge["optimized_light_petrol_vkt_million_km"].loc[fy])
                    conv, bev, phev = pack_light_ruc(fy)
                elif name == "C_semantic_clean_anchor":
                    ped = float(raw_ped_vkt.loc[fy])
                    conv, bev, phev = clean_light_ruc(fy)
                elif name == "D_isolate_ped":
                    ped = float(raw_ped_vkt.loc[fy])
                    conv, bev, phev = pack_light_ruc(fy)
                else:  # E
                    ped = float(bridge["optimized_light_petrol_vkt_million_km"].loc[fy])
                    conv, bev, phev = clean_light_ruc(fy)
            row = revenue_from_activity(
                fy,
                light_petrol_vkt=ped,
                conventional_km=conv,
                bev_km=bev,
                phev_km=phev,
                drift=drift,
                fixed=fixed,
            )
            row["variant"] = name
            row["june_year"] = fy
            records.append(row)

    variants = pd.DataFrame(records)

    # MBU26 comparator
    index = pd.Index(FYS, name="june_year")
    mbu = pd.DataFrame(
        {
            "mbu26_total_nltf": bridge["official_total_nltf_net_revenue_million_nzd"].astype(float).reindex(index),
            "mbu26_gross_ped": bridge["official_gross_ped_revenue_million_nzd"].astype(float).reindex(index),
            "mbu26_light_petrol_vkt": bridge["official_light_petrol_vkt_million_km"].astype(float).reindex(index),
            "mbu26_conventional_km": split["conventional_light_km"].astype(float).reindex(index),
            "mbu26_pool_km": split["total_light_universe_km"].astype(float).reindex(index),
        }
    ).reset_index()
    variants = variants.merge(mbu, on="june_year", how="left")
    variants["total_nltf_gap_vs_mbu26"] = (
        variants["total_nltf_net_revenue"] - variants["mbu26_total_nltf"]
    )
    variants["total_nltf_gap_pct"] = 100.0 * variants["total_nltf_gap_vs_mbu26"] / variants["mbu26_total_nltf"]
    variants["gross_ped_gap_pct"] = 100.0 * (
        variants["gross_ped_revenue"] - variants["mbu26_gross_ped"]
    ) / variants["mbu26_gross_ped"]

    # ---- reference A: reproduce the front end ---------------------------
    ref_a, uptake_audit = reference_a(data["chart"])

    pack_front = (
        data["chart"][
            data["chart"]["time_grain"].eq("june_year")
            & data["chart"]["scenario_name"].eq(SCENARIO)
            & data["chart"]["june_year"].between(2025, 2030)
        ]
        .pivot_table(index="june_year", columns="series_id", values="value", aggfunc="first")
        .sort_index()
    )

    # Hard gate 1: variant B must equal the stored pack front end exactly.
    b = variants[variants["variant"].eq("B_stored_pack")].set_index("june_year").sort_index()
    gate_rows = []
    for series in [
        "light_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
        "gross_ped_revenue",
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "total_nltf_net_revenue",
    ]:
        delta = (b[series] - pack_front[series]).abs().max()
        gate_rows.append(
            {
                "check": f"variant_B_reproduces_stored_pack::{series}",
                "max_abs_delta": float(delta),
                "tolerance": CLOSURE_TOL,
                "status": "pass" if float(delta) <= CLOSURE_TOL else "FAIL",
            }
        )

    # Conservation and preservation tests
    for name in ["C_semantic_clean_anchor", "E_isolate_light_ruc"]:
        sub = variants[variants["variant"].eq(name)].set_index("june_year")
        delta = max(
            abs(float(sub.loc[fy, "light_ruc_net_km"]) - float(raw_light_ruc.loc[fy]))
            for fy in FORECAST_FYS
        )
        gate_rows.append(
            {
                "check": f"raw_conventional_preserved::{name}",
                "max_abs_delta": delta,
                "tolerance": CLOSURE_TOL,
                "status": "pass" if delta <= CLOSURE_TOL else "FAIL",
            }
        )

    # Every variant's PED level must be exactly the one its definition claims:
    # the raw model output where the definition says "no migration transfer",
    # and the stored pack level where it says "unchanged". A variant that
    # silently inherited a lambda transfer would fail here.
    ped_expectation = {
        "C_semantic_clean_anchor": ("raw_no_transfer", raw_ped_vkt),
        "D_isolate_ped": ("raw_no_transfer", raw_ped_vkt),
        "E_isolate_light_ruc": (
            "stored_pack_lambda",
            bridge["optimized_light_petrol_vkt_million_km"].astype(float),
        ),
    }
    for name, (kind, expected) in ped_expectation.items():
        sub = variants[variants["variant"].eq(name)].set_index("june_year")
        worst = max(
            abs(float(sub.loc[fy, "light_petrol_vkt_million_km"]) - float(expected.loc[fy]))
            for fy in FORECAST_FYS
        )
        gate_rows.append(
            {
                "check": f"ped_level_matches_definition::{name}::{kind}",
                "max_abs_delta": worst,
                "tolerance": CLOSURE_TOL,
                "status": "pass" if worst <= CLOSURE_TOL else "FAIL",
            }
        )

    # C and E must not inherit the lambda PED deduction at all: their PED level
    # must differ from the stored pack by exactly (1-lambda)*M where they claim
    # the raw path, and must equal it where they claim the pack path.
    c_sub = variants[variants["variant"].eq("C_semantic_clean_anchor")].set_index("june_year")
    worst_transfer = max(
        abs(
            (float(c_sub.loc[fy, "light_petrol_vkt_million_km"])
             - float(bridge["optimized_light_petrol_vkt_million_km"].loc[fy]))
            - float((1.0 - lam.loc[fy]) * migration.loc[fy])
        )
        for fy in FORECAST_FYS
    )
    gate_rows.append(
        {
            "check": "variant_C_removes_exactly_the_lambda_ped_transfer",
            "max_abs_delta": worst_transfer,
            "tolerance": CLOSURE_TOL,
            "status": "pass" if worst_transfer <= CLOSURE_TOL else "FAIL",
        }
    )

    # Class sums close
    conservation = []
    for name in variants["variant"].unique():
        sub = variants[variants["variant"].eq(name)].set_index("june_year")
        for fy in FYS:
            total = (
                float(sub.loc[fy, "light_ruc_net_km"])
                + float(sub.loc[fy, "light_bev_ruc_net_km"])
                + float(sub.loc[fy, "phev_ruc_net_km"])
            )
            conservation.append(
                {
                    "variant": name,
                    "june_year": fy,
                    "class_sum_km": total,
                    "reported_pool_km": float(sub.loc[fy, "light_ruc_pool_km"]),
                    "residual_km": total - float(sub.loc[fy, "light_ruc_pool_km"]),
                    "raw_model_km": float(raw_light_ruc.loc[fy]),
                    "pool_minus_raw_model_km": float(sub.loc[fy, "light_ruc_pool_km"])
                    - float(raw_light_ruc.loc[fy]),
                }
            )
    conservation_df = pd.DataFrame(conservation)
    worst_res = conservation_df["residual_km"].abs().max()
    gate_rows.append(
        {
            "check": "physical_class_sum_closes",
            "max_abs_delta": float(worst_res),
            "tolerance": CLOSURE_TOL,
            "status": "pass" if float(worst_res) <= CLOSURE_TOL else "FAIL",
        }
    )

    # FY2025 actual classes unchanged across variants
    fy25 = variants[variants["june_year"].eq(2025)]
    spread = float(
        fy25.groupby("variant")[["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]]
        .first()
        .std()
        .max()
    )
    gate_rows.append(
        {
            "check": "fy2025_actual_classes_unchanged_across_variants",
            "max_abs_delta": 0.0 if np.isnan(spread) else spread,
            "tolerance": CLOSURE_TOL,
            "status": "pass" if (np.isnan(spread) or spread <= CLOSURE_TOL) else "FAIL",
        }
    )

    gates = pd.DataFrame(gate_rows)

    # ---- revenue identity audit ----------------------------------------
    identity = []
    for name in variants["variant"].unique():
        sub = variants[variants["variant"].eq(name)].set_index("june_year")
        for fy in FYS:
            f = fixed.loc[fy]
            recomputed = (
                float(sub.loc[fy, "gross_ruc_revenue"])
                + float(sub.loc[fy, "gross_fed_revenue"])
                + float(f["mr1_revenue"]) + float(f["mr2_revenue"]) + float(f["coo_revenue"])
                + float(f["tuc_net_revenue"])
                - float(f["ruc_admin_revenue"]) - float(f["mvr_admin_revenue"]) - float(f["coo_revenue"])
                - float(f["ruc_refunds"]) - float(f["fed_refunds"]) - float(f["mvr_refunds"])
            )
            identity.append(
                {
                    "variant": name,
                    "june_year": fy,
                    "reported_total_nltf": float(sub.loc[fy, "total_nltf_net_revenue"]),
                    "recomputed_total_nltf": recomputed,
                    "residual": float(sub.loc[fy, "total_nltf_net_revenue"]) - recomputed,
                }
            )
    identity_df = pd.DataFrame(identity)
    worst_identity = identity_df["residual"].abs().max()
    gates = pd.concat(
        [
            gates,
            pd.DataFrame(
                [
                    {
                        "check": "revenue_identity_closes",
                        "max_abs_delta": float(worst_identity),
                        "tolerance": CLOSURE_TOL,
                        "status": "pass" if float(worst_identity) <= CLOSURE_TOL else "FAIL",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    # ---- falsification / structural diagnostic --------------------------
    diag = pd.DataFrame(index=pd.Index(FORECAST_FYS, name="june_year"))
    diag["raw_model_vs_mbu26_conventional_pct"] = 100.0 * (
        raw_light_ruc.loc[FORECAST_FYS] / split["conventional_light_km"].loc[FORECAST_FYS] - 1.0
    )
    diag["pack_conventional_vs_mbu26_pct"] = 100.0 * (
        split["current_conventional_light_km"].loc[FORECAST_FYS]
        / split["conventional_light_km"].loc[FORECAST_FYS]
        - 1.0
    )
    implied_pool = raw_light_ruc.loc[FORECAST_FYS] / vfm_conv.loc[FORECAST_FYS]
    diag["vfm_anchor_pool_vs_mbu26_pool_pct"] = 100.0 * (
        implied_pool / split["total_light_universe_km"].loc[FORECAST_FYS] - 1.0
    )
    diag["pack_pool_vs_mbu26_pool_pct"] = 100.0 * (
        split["current_allocation_sum_km"].loc[FORECAST_FYS]
        / split["total_light_universe_km"].loc[FORECAST_FYS]
        - 1.0
    )
    diag["raw_ped_vs_mbu26_pct"] = 100.0 * (
        raw_ped_vkt.loc[FORECAST_FYS]
        / bridge["official_light_petrol_vkt_million_km"].loc[FORECAST_FYS]
        - 1.0
    )
    diag["raw_gross_ped_rev_vs_mbu26_pct"] = 100.0 * (
        bridge["gross_ped_revenue_raw_million_nzd"].loc[FORECAST_FYS]
        / bridge["official_gross_ped_revenue_million_nzd"].loc[FORECAST_FYS]
        - 1.0
    )
    diag["optimized_gross_ped_rev_vs_mbu26_pct"] = 100.0 * (
        bridge["gross_ped_revenue_optimized_million_nzd"].loc[FORECAST_FYS]
        / bridge["official_gross_ped_revenue_million_nzd"].loc[FORECAST_FYS]
        - 1.0
    )

    # ---- FY2025 anchor and FY2025 -> FY2026 continuity -------------------
    continuity = []
    for name in variants["variant"].unique():
        sub = variants[variants["variant"].eq(name)].set_index("june_year")
        for series in ["light_ruc_net_km", "light_petrol_vkt_million_km", "light_ruc_pool_km"]:
            continuity.append(
                {
                    "variant": name,
                    "series": series,
                    "fy2025": float(sub.loc[2025, series]),
                    "fy2026": float(sub.loc[2026, series]),
                    "step_pct": 100.0 * (float(sub.loc[2026, series]) / float(sub.loc[2025, series]) - 1.0),
                }
            )
    continuity_df = pd.DataFrame(continuity)

    # ---- Reference A: does the VFM overlay preserve the lambda pool? -----
    ref_rows = []
    for fy in FORECAST_FYS:
        pack_pool = float(
            pack_front.loc[fy, ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]].sum()
        )
        a_pool = float(
            ref_a.loc[fy, ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]].sum()
        )
        ref_rows.append(
            {
                "june_year": fy,
                "S1_pack_pool_km": pack_pool,
                "S4_reference_a_pool_km": a_pool,
                "pool_change_km": a_pool - pack_pool,
                "S1_pack_conventional_km": float(pack_front.loc[fy, "light_ruc_net_km"]),
                "S4_reference_a_conventional_km": float(ref_a.loc[fy, "light_ruc_net_km"]),
                "S1_pack_gross_ped": float(pack_front.loc[fy, "gross_ped_revenue"]),
                "S4_reference_a_gross_ped": float(ref_a.loc[fy, "gross_ped_revenue"]),
                "S1_pack_total_nltf": float(pack_front.loc[fy, "total_nltf_net_revenue"]),
                "S4_reference_a_total_nltf": float(ref_a.loc[fy, "total_nltf_net_revenue"]),
                "raw_model_km": float(raw_light_ruc.loc[fy]),
            }
        )
    ref_df = pd.DataFrame(ref_rows).set_index("june_year")
    worst_pool = ref_df["pool_change_km"].abs().max()
    gates = pd.concat(
        [
            gates,
            pd.DataFrame(
                [
                    {
                        "check": "vfm_overlay_preserves_the_lambda_created_pool_level",
                        "max_abs_delta": float(worst_pool),
                        "tolerance": CLOSURE_TOL,
                        "status": "pass" if float(worst_pool) <= CLOSURE_TOL else "FAIL",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    # ---- FY gap attribution ---------------------------------------------
    pivot = variants.pivot_table(
        index="june_year", columns="variant", values="total_nltf_net_revenue", aggfunc="first"
    )
    attribution = pd.DataFrame(index=pd.Index(FORECAST_FYS, name="june_year"))
    attribution["mbu26_total_nltf"] = mbu.set_index("june_year")["mbu26_total_nltf"].loc[FORECAST_FYS]
    attribution["current_total_nltf"] = pivot["B_stored_pack"].loc[FORECAST_FYS]
    attribution["total_gap"] = attribution["current_total_nltf"] - attribution["mbu26_total_nltf"]
    attribution["from_ped_post_model_reduction"] = (
        pivot["D_isolate_ped"].loc[FORECAST_FYS] - pivot["B_stored_pack"].loc[FORECAST_FYS]
    )
    attribution["from_light_ruc_post_model_allocation"] = (
        pivot["E_isolate_light_ruc"].loc[FORECAST_FYS] - pivot["B_stored_pack"].loc[FORECAST_FYS]
    )
    attribution["residual_underlying_econometrics_and_other"] = (
        pivot["C_semantic_clean_anchor"].loc[FORECAST_FYS] - attribution["mbu26_total_nltf"]
    )
    attribution["interaction"] = (
        attribution["total_gap"]
        + attribution["from_ped_post_model_reduction"]
        + attribution["from_light_ruc_post_model_allocation"]
        - attribution["residual_underlying_econometrics_and_other"]
    ) * -1.0 + (
        attribution["total_gap"]
        + attribution["from_ped_post_model_reduction"]
        + attribution["from_light_ruc_post_model_allocation"]
        - attribution["residual_underlying_econometrics_and_other"]
    )
    attribution["interaction"] = (
        pivot["C_semantic_clean_anchor"].loc[FORECAST_FYS]
        - pivot["B_stored_pack"].loc[FORECAST_FYS]
        - attribution["from_ped_post_model_reduction"]
        - attribution["from_light_ruc_post_model_allocation"]
    )

    # ---- PED layering: how many times is petrol activity displaced? ------
    layering = pd.DataFrame(index=pd.Index(FORECAST_FYS, name="june_year"))
    layering["L0_raw_model_gross_ped"] = bridge["gross_ped_revenue_raw_million_nzd"].loc[FORECAST_FYS]
    layering["L1_after_lambda_migration"] = bridge["gross_ped_revenue_optimized_million_nzd"].loc[FORECAST_FYS]
    layering["L2_after_vfm_retention_overlay"] = ref_df["S4_reference_a_gross_ped"]
    layering["mbu26_gross_ped"] = bridge["official_gross_ped_revenue_million_nzd"].loc[FORECAST_FYS]
    for level in ["L0_raw_model_gross_ped", "L1_after_lambda_migration", "L2_after_vfm_retention_overlay"]:
        layering[f"{level}_vs_mbu26_pct"] = 100.0 * (
            layering[level] / layering["mbu26_gross_ped"] - 1.0
        )
    layering["lambda_deduction_million_nzd"] = (
        layering["L1_after_lambda_migration"] - layering["L0_raw_model_gross_ped"]
    )
    layering["vfm_retention_deduction_million_nzd"] = (
        layering["L2_after_vfm_retention_overlay"] - layering["L1_after_lambda_migration"]
    )

    # ---- runtime consumer map -------------------------------------------
    # Which stage each decision-facing series is created at, and whether the
    # value a consumer reads has already been through the lambda transfer.
    lines_raw = pd.read_csv(PACK / "revenue_line_reconciliation.csv")
    roles = (
        lines_raw[lines_raw["scenario_name"].eq(SCENARIO) & lines_raw["FY"].eq(2030)]
        .set_index("series_id")[["row_role", "formula", "section"]]
    )
    consumer_rows = []
    for series, stage, consumer, lam_applied in [
        ("current_light_ruc_total_modelled_km", "S0", "audit only; not read by any revenue line", False),
        ("light_ruc_net_km", "S1", "light_ruc_net_revenue; VFM overlay pool; front end", True),
        ("light_bev_ruc_net_km", "S1", "light_bev_ruc_net_revenue; VFM overlay pool; front end", True),
        ("phev_ruc_net_km", "S1", "phev_ruc_net_revenue; VFM overlay pool; front end", True),
        ("light_petrol_vkt", "S1", "ped_volume -> gross_ped_revenue; VFM PED retention overlay", True),
        ("ped_volume", "S2", "gross_ped_revenue", True),
        ("gross_ped_revenue", "S2", "gross_fed_revenue -> net_fed_revenue -> total_nltf", True),
        ("heavy_ruc_net_km", "S1", "heavy_ruc_net_revenue", False),
        ("total_ruc_net_revenue", "S5", "front end", True),
        ("total_nltf_net_revenue", "S5", "front end; Workstream A decomposition", True),
    ]:
        consumer_rows.append(
            {
                "series_id": series,
                "stage_created": stage,
                "row_role": str(roles["row_role"].get(series, "")),
                "pack_formula": str(roles["formula"].get(series, "")),
                "lambda_applied_to_this_level": lam_applied,
                "downstream_consumers": consumer,
            }
        )
    pd.DataFrame(consumer_rows).to_csv(OUT / "runtime_consumer_map.csv", index=False)

    # ---- write ----------------------------------------------------------
    layering.round(4).to_csv(OUT / "ped_displacement_layering.csv")
    ref_df.round(6).to_csv(OUT / "reference_a_vs_stored_pack.csv")
    attribution.round(4).to_csv(OUT / "fy_gap_attribution.csv")
    waterfall.round(6).to_csv(OUT / "runtime_stage_waterfall.csv")
    variants.round(6).to_csv(OUT / "structural_variant_results_fy.csv", index=False)
    pd.DataFrame(
        [{"variant": n, "ped_treatment": p, "light_ruc_treatment": l} for n, p, l in definitions]
    ).to_csv(OUT / "structural_variant_definitions.csv", index=False)
    conservation_df.round(9).to_csv(OUT / "conservation_audit.csv", index=False)
    identity_df.round(9).to_csv(OUT / "revenue_identity_audit.csv", index=False)
    gates.to_csv(OUT / "checkpoint_2_hard_gates.csv", index=False)
    diag.round(4).to_csv(OUT / "compact_falsification_metrics.csv")
    continuity_df.round(6).to_csv(OUT / "actual_anchor_and_continuity.csv", index=False)
    ref_a.round(6).to_csv(OUT / "reference_a_front_end_with_vfm_overlay.csv")

    # ---- console --------------------------------------------------------
    print("=== S0 raw Light RUC model forecast (replay statuses:", replay_status, ") ===")
    print(raw_light_ruc.loc[FORECAST_FYS].to_string())
    print("\n=== lambda transfer identity ===")
    cols = [
        "S0_raw_light_ruc_model_km",
        "S1_lambda_value",
        "S1_migration_total_km",
        "S1_taken_from_light_ruc_km",
        "S1_taken_from_ped_km",
        "S1_pack_conventional_km",
        "S1_pack_class_sum_km",
        "conventional_minus_raw_km",
        "class_sum_minus_raw_km",
        "ped_minus_raw_km",
    ]
    print(waterfall.loc[FORECAST_FYS, cols].round(3).to_string())
    print("\n=== universe construction ===")
    print(
        waterfall.loc[
            FORECAST_FYS,
            ["universe_U_t_km", "mbu26_universe_km", "mbu26_universe_ev_phev_km"],
        ].round(3).to_string()
    )
    print("\n=== hard gates ===")
    print(gates.to_string(index=False))
    print("\n=== FY2030 variant comparison ===")
    print(
        variants[variants["june_year"].eq(2030)][
            [
                "variant",
                "light_petrol_vkt_million_km",
                "light_ruc_net_km",
                "light_ruc_pool_km",
                "gross_ped_revenue",
                "total_ruc_net_revenue",
                "total_nltf_net_revenue",
                "total_nltf_gap_vs_mbu26",
                "total_nltf_gap_pct",
            ]
        ].round(3).to_string(index=False)
    )
    print("\n=== falsification / structural diagnostic (%) ===")
    print(diag.round(2).to_string())
    print("\n=== Reference A (S4 VFM overlay) vs stored pack (S1) ===")
    print(
        ref_df[
            [
                "raw_model_km",
                "S1_pack_conventional_km",
                "S4_reference_a_conventional_km",
                "S1_pack_pool_km",
                "S4_reference_a_pool_km",
                "pool_change_km",
                "S4_reference_a_total_nltf",
            ]
        ].round(4).to_string()
    )
    print("\n=== FY total NLTF gap attribution ($m vs MBU26) ===")
    print(attribution.round(2).to_string())
    print("\n=== PED displacement layering (gross PED revenue, $m) ===")
    print(
        layering[
            [
                "L0_raw_model_gross_ped",
                "L1_after_lambda_migration",
                "L2_after_vfm_retention_overlay",
                "mbu26_gross_ped",
                "L0_raw_model_gross_ped_vs_mbu26_pct",
                "L1_after_lambda_migration_vs_mbu26_pct",
                "L2_after_vfm_retention_overlay_vs_mbu26_pct",
            ]
        ].round(2).to_string()
    )

    failed = gates[gates["status"].eq("FAIL")]
    if not failed.empty:
        print("\nFAILED GATES:")
        print(failed.to_string(index=False))
        return 1
    print("\nAll hard gates pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

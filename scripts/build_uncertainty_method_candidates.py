"""Gate B (corrected): June-year band basis, asymmetric, origin-bootstrapped.

Corrections applied to the previous pass, all six of which the owner raised:

1. The production candidate table is now generated from the JUNE-YEAR
   distributions in ``long_horizon_june_year_errors.csv``.  It previously read
   the quarterly isotonic H20 curve while the narrative claimed a June-year
   basis - materially wrong for Light RUC (33.37% vs the June-year 23.11%).
   The quarterly H1-H20 view is retained as a diagnostic, a cross-check on the
   annual shape, and the source for the audit-only saturating and square-root
   cases.
2. Bands are no longer forced symmetric.  ``central * exp(q10 .. q90)`` is
   carried per side, with the median multiplier recorded separately so bias is
   visible.
3. June-year quantiles now carry deterministic bootstrap intervals resampled
   by ORIGIN, because overlapping rolling-origin rows are not independent.
4. Light RUC evidence is labelled as the CONVENTIONAL anchor, not the pool.
5. The indicative aggregate bracket aggregates leaves sharing one parent shock
   before any independence assumption is applied.
6. The four proxy leaves are resolved explicitly against committed sources.

    .venv\\Scripts\\python.exe scripts\\build_uncertainty_method_candidates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    REVENUE_SOURCE_PACK_DIR,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402
from model_dashboard.revenue_uncertainty import (  # noqa: E402
    FINAL_FY,
    LAST_ACTUAL_FY,
    LAST_SUPPORTED_FY,
    QuantileMultipliers,
    evidence_state_for_fy,
    june_year_quantiles,
    plateau_multipliers_by_fy,
)

LONG_HORIZON = ROOT / "artifacts" / "long_horizon_validation"
OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
REPORT_FYS = (2027, 2030, 2031, 2040, 2050)

# series_id, display, kind, tier, parent shock, derivation
SERIES_CONTRACT = (
    ("ped_vkt_per_capita", "PED VKT per capita", "activity", 1, "PED",
     "direct rolling-origin evidence for the PED finalist target"),
    ("ped_volume", "PED volume", "activity", 3, "PED",
     "uncertain PED activity through the governed PED bridge"),
    ("light_ruc_net_km", "Light RUC net km", "activity", 3, "LIGHT_RUC",
     "governed Light pool scaled by ONE conventional-anchor model-error factor, "
     "then allocated through the selected exact VFM shares"),
    ("light_bev_ruc_net_km", "Light BEV RUC net km", "activity", 3, "LIGHT_RUC",
     "same scaled Light pool x selected exact VFM BEV share; perfectly "
     "dependent on the other Light classes given the shares"),
    ("phev_ruc_net_km", "PHEV RUC net km", "activity", 3, "LIGHT_RUC",
     "same scaled Light pool x selected exact VFM PHEV share"),
    ("heavy_ruc_net_km", "Heavy RUC net km", "activity", 1, "HEAVY_RUC",
     "direct rolling-origin evidence for the Heavy RUC finalist target"),
    ("heavy_bev_ruc_net_km", "Heavy BEV RUC net km", "activity", 5, "HEAVY_RUC_PROXY",
     "Tier-5 proxy: the Heavy RUC relative error factor, applied identically to "
     "Heavy-BEV km and revenue so the effective-rate identity closes"),
    ("gross_ped_revenue", "PED revenue", "revenue", 3, "PED",
     "uncertain PED volume x governed FED rate"),
    ("gross_fed_revenue", "Gross FED revenue", "revenue", 3, "PED",
     "FORMULA_DEFINITIONS from uncertain PED/LPG/CNG leaves"),
    ("net_fed_revenue", "Net FED revenue", "revenue", 3, "PED",
     "FORMULA_DEFINITIONS: gross_fed_revenue - fed_refunds"),
    ("light_ruc_net_revenue", "Light RUC revenue", "revenue", 3, "LIGHT_RUC",
     "uncertain conventional Light km x governed class rate"),
    ("light_bev_ruc_net_revenue", "Light BEV RUC net revenue", "revenue", 3, "LIGHT_RUC",
     "uncertain Light BEV km x governed class rate"),
    ("phev_ruc_net_revenue", "PHEV RUC net revenue", "revenue", 3, "LIGHT_RUC",
     "uncertain PHEV km x governed class rate"),
    ("heavy_ruc_net_revenue", "Heavy RUC revenue", "revenue", 3, "HEAVY_RUC",
     "uncertain Heavy km x governed class rate"),
    ("heavy_bev_ruc_net_revenue", "Heavy BEV RUC net revenue", "revenue", 5, "HEAVY_RUC_PROXY",
     "same Tier-5 Heavy proxy factor as Heavy-BEV km"),
    ("total_ruc_net_revenue", "Total RUC all classes", "revenue", 3, "",
     "draw-level FORMULA_DEFINITIONS rollup of every RUC class"),
    ("total_fed_ruc_net_revenue", "Total RUC+PED revenue", "revenue", 3, "",
     "FORMULA_DEFINITIONS: net_fed_revenue + total_ruc_net_revenue"),
    ("total_nltf_net_revenue", "Total NLTF revenue", "revenue", 3, "",
     "draw-level FORMULA_DEFINITIONS rollup of every stream"),
    ("net_mvr_revenue", "Net MVR revenue", "revenue", 5, "MVR_PROXY",
     "Tier-5 proxy calibrated on the observed BEFU26-vs-MBU26 vintage revision"),
    ("tuc_net_revenue", "TUC net revenue", "revenue", 5, "TUC_FIXED",
     "governed fixed administrative component; identical across vintages"),
)

# Parent shocks that are genuinely independent of one another. Everything else
# inherits one of these, which is exactly why the aggregate bracket has to
# group before it assumes anything.
INDEPENDENT_PARENTS = ("PED", "LIGHT_RUC", "HEAVY_RUC")


def production_key() -> RevenueScenarioComputationKey:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    block = pack.manifest.get("official_vintages", {})
    return RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id=str(block.get("default_comparator_vintage_id") or "BEFU26"),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )


def central_values() -> pd.DataFrame:
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    rows, *_ = app.cached_scenario_overlay_rows(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        production_key(),
        pack,
    )
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_role"].astype(str).eq("basecase")
    ].copy()
    selected["FY"] = pd.to_numeric(selected["june_year"], errors="coerce")
    selected["central"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "central"])
    return (
        selected.groupby(["series_id", "FY"], as_index=False)["central"].first().astype({"FY": int})
    )


def mvr_proxy_multipliers() -> QuantileMultipliers:
    """Calibrated on the observed vintage revision, not an arbitrary percentage.

    MVR is a near-fixed administrative component: the BEFU26 and MBU26 vintages
    agree exactly in 24 of 25 forecast June years, with one year differing by
    7.64% in log terms. p10/p90 of that revision is therefore 0, which would
    give a zero band. A zero band on a real revenue line is not conservative,
    so the FULL observed revision range is adopted as the 80% span and half of
    it as the 50% span - documented, series-specific and deliberately wider
    than the measured quantiles.
    """
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    frame = pack.revenue_line_reconciliation.copy()
    frame["FY"] = pd.to_numeric(frame["FY"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    selected = frame[
        frame["series_id"].astype(str).eq("net_mvr_revenue")
        & frame["FY"].between(LAST_ACTUAL_FY + 1, FINAL_FY)
    ]
    pivot = selected.pivot_table(index="FY", columns="source_path", values="value", aggfunc="first")
    if "BEFU26 official" not in pivot or "MBU26 official" not in pivot:
        half = 0.02
    else:
        revision = np.log(pivot["MBU26 official"] / pivot["BEFU26 official"]).dropna()
        half = float(revision.abs().max()) if len(revision) else 0.02
    return QuantileMultipliers(q10=-half, q25=-half / 2.0, median=0.0, q75=half / 2.0, q90=half)


def tuc_proxy_multipliers() -> QuantileMultipliers:
    """A governed fixed component. Identical in every vintage and every FY.

    Recorded as zero modelled uncertainty rather than given an invented band:
    TUC is set administratively, not forecast by a model, so a probabilistic
    band around it would be asserting something no evidence supports. The
    limitation is carried in the contract so a reader is not misled into
    thinking the Total NLTF band covers it.
    """
    return QuantileMultipliers(q10=0.0, q25=0.0, median=0.0, q75=0.0, q90=0.0)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    june_errors = pd.read_csv(LONG_HORIZON / "long_horizon_june_year_errors.csv")
    quantiles = june_year_quantiles(june_errors)
    quantiles.to_csv(OUT / "june_year_uncertainty_basis.csv", index=False)

    # ---------------------------------------------- production candidate table
    proxy_multipliers = {
        "MVR_PROXY": mvr_proxy_multipliers(),
        "TUC_FIXED": tuc_proxy_multipliers(),
    }
    plateau: dict[str, dict[int, QuantileMultipliers]] = {}
    for stream in sorted(quantiles["stream"].unique()):
        plateau[str(stream)] = plateau_multipliers_by_fy(quantiles, str(stream))
    plateau["HEAVY_RUC_PROXY"] = plateau["HEAVY_RUC"]
    for name, multipliers in proxy_multipliers.items():
        plateau[name] = {fy: multipliers for fy in range(LAST_ACTUAL_FY + 1, FINAL_FY + 1)}

    candidate_rows: list[dict] = []
    for stream, by_fy in plateau.items():
        for fy, multipliers in by_fy.items():
            applied = multipliers.apply(1.0)
            candidate_rows.append(
                {
                    "stream": stream,
                    "candidate": "plateau",
                    "production_default": stream in plateau,
                    "FY": fy,
                    "june_year_horizon": fy - LAST_ACTUAL_FY,
                    "evidence_state": evidence_state_for_fy(fy),
                    "lower80_multiplier": applied["lower80_multiplier"],
                    "lower50_multiplier": applied["lower50_multiplier"],
                    "median_multiplier": applied["median_multiplier"],
                    "upper50_multiplier": applied["upper50_multiplier"],
                    "upper80_multiplier": applied["upper80_multiplier"],
                    "span80_pct": applied["span80_pct"],
                    "span50_pct": applied["span50_pct"],
                    "lower80_distance_pct": applied["lower80_distance_pct"],
                    "upper80_distance_pct": applied["upper80_distance_pct"],
                    "asymmetry_ratio_80": applied["asymmetry_ratio_80"],
                }
            )
    candidates = pd.DataFrame(candidate_rows)
    candidates.to_csv(OUT / "long_run_method_candidates.csv", index=False)

    # ------------------------------------------------------- example bands
    central = central_values()
    contract = pd.DataFrame(
        SERIES_CONTRACT,
        columns=["series_id", "display_name", "kind", "tier", "parent_shock", "derivation"],
    )
    example_rows: list[dict] = []
    for _index, series in contract.iterrows():
        parent = str(series["parent_shock"])
        if parent not in plateau:
            continue
        for fy in REPORT_FYS:
            match = central[
                central["series_id"].eq(series["series_id"]) & central["FY"].eq(fy)
            ]
            if match.empty:
                continue
            value = float(match["central"].iloc[0])
            applied = plateau[parent][fy].apply(value)
            example_rows.append(
                {
                    "series_id": series["series_id"],
                    "display_name": series["display_name"],
                    "tier": int(series["tier"]),
                    "parent_shock": parent,
                    "FY": fy,
                    "evidence_state": evidence_state_for_fy(fy),
                    "central": value,
                    "lower80": applied["lower80"],
                    "lower50": applied["lower50"],
                    "upper50": applied["upper50"],
                    "upper80": applied["upper80"],
                    "span80_pct": applied["span80_pct"],
                    "span50_pct": applied["span50_pct"],
                    "lower80_distance_pct": applied["lower80_distance_pct"],
                    "upper80_distance_pct": applied["upper80_distance_pct"],
                    "asymmetry_ratio_80": applied["asymmetry_ratio_80"],
                }
            )

    # ------------------------------------ indicative aggregate bracket, fixed
    # Leaves sharing ONE parent shock are summed first (perfect dependence,
    # which is what they actually are), and only the independent parent
    # factors are then combined under the two bracketing assumptions.
    aggregate_parts = {
        "total_ruc_net_revenue": (
            "light_ruc_net_revenue", "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue", "heavy_ruc_net_revenue",
            "heavy_bev_ruc_net_revenue",
        ),
        "total_fed_ruc_net_revenue": (
            "net_fed_revenue", "light_ruc_net_revenue", "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue", "heavy_ruc_net_revenue", "heavy_bev_ruc_net_revenue",
        ),
        "total_nltf_net_revenue": (
            "net_fed_revenue", "light_ruc_net_revenue", "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue", "heavy_ruc_net_revenue", "heavy_bev_ruc_net_revenue",
            "net_mvr_revenue", "tuc_net_revenue",
        ),
    }
    parent_of = {row["series_id"]: str(row["parent_shock"]) for _i, row in contract.iterrows()}
    for aggregate, parts in aggregate_parts.items():
        for fy in REPORT_FYS:
            total = central[central["series_id"].eq(aggregate) & central["FY"].eq(fy)]
            if total.empty:
                continue
            total_value = float(total["central"].iloc[0])
            # Step 1: perfectly dependent inside each parent shock.
            per_parent_lower: dict[str, float] = {}
            per_parent_upper: dict[str, float] = {}
            for part in parts:
                parent = parent_of.get(part, "")
                if parent not in plateau:
                    continue
                match = central[central["series_id"].eq(part) & central["FY"].eq(fy)]
                if match.empty:
                    continue
                part_value = float(match["central"].iloc[0])
                applied = plateau[parent][fy].apply(part_value)
                # Proxy parents ride their own factor but are treated as
                # sharing the parent they proxy, which is the conservative
                # reading for Heavy BEV.
                bucket = "HEAVY_RUC" if parent == "HEAVY_RUC_PROXY" else parent
                per_parent_lower[bucket] = per_parent_lower.get(bucket, 0.0) + (
                    part_value - applied["lower80"]
                )
                per_parent_upper[bucket] = per_parent_upper.get(bucket, 0.0) + (
                    applied["upper80"] - part_value
                )
            if not per_parent_lower:
                continue
            # Step 2: bracket ACROSS independent parents only.
            lower_terms = np.array(list(per_parent_lower.values()))
            upper_terms = np.array(list(per_parent_upper.values()))
            for basis, lower_half, upper_half in (
                (
                    "indicative_independent_across_parents",
                    float(np.sqrt(np.sum(lower_terms**2))),
                    float(np.sqrt(np.sum(upper_terms**2))),
                ),
                (
                    "indicative_comonotonic_across_parents",
                    float(lower_terms.sum()),
                    float(upper_terms.sum()),
                ),
            ):
                example_rows.append(
                    {
                        "series_id": aggregate,
                        "display_name": f"{aggregate} ({basis})",
                        "tier": 3,
                        "parent_shock": basis,
                        "FY": fy,
                        "evidence_state": evidence_state_for_fy(fy),
                        "central": total_value,
                        "lower80": total_value - lower_half,
                        "lower50": np.nan,
                        "upper50": np.nan,
                        "upper80": total_value + upper_half,
                        "span80_pct": 100.0 * (lower_half + upper_half) / total_value,
                        "span50_pct": np.nan,
                        "lower80_distance_pct": 100.0 * lower_half / total_value,
                        "upper80_distance_pct": 100.0 * upper_half / total_value,
                        "asymmetry_ratio_80": upper_half / lower_half if lower_half else np.nan,
                    }
                )

    examples = pd.DataFrame(example_rows)
    examples.to_csv(OUT / "uncertainty_design_examples.csv", index=False)

    # -------------------------------------------------- series-tier contract
    seam = quantiles[quantiles["june_year_horizon"].eq(5)].set_index("stream")
    contract["direct_evidence_source"] = contract["parent_shock"].map(
        lambda parent: {
            "PED": "long_horizon_june_year_errors.csv (rolling origin, JY H1-H5)",
            "LIGHT_RUC": "long_horizon_june_year_errors.csv - CONVENTIONAL Light RUC anchor",
            "HEAVY_RUC": "long_horizon_june_year_errors.csv (rolling origin, JY H1-H5)",
            "HEAVY_RUC_PROXY": "Tier-5 proxy: the Heavy RUC relative error factor",
            "MVR_PROXY": "Tier-5 proxy: BEFU26 vs MBU26 vintage revision, FY2026-FY2050",
            "TUC_FIXED": "governed fixed administrative component; no model error",
        }.get(parent, "derived by draw-level propagation from an uncertain parent")
    )
    contract["calibration_period"] = contract["parent_shock"].map(
        lambda parent: "origins 2012Q1-2025Q4 (rolling origin)"
        if parent in INDEPENDENT_PARENTS or parent == "HEAVY_RUC_PROXY"
        else "FY2026-FY2050 committed vintages"
        if parent == "MVR_PROXY"
        else ""
    )
    contract["sample_size"] = contract["parent_shock"].map(
        lambda parent: int(seam.loc[parent, "n_rows"])
        if parent in seam.index
        else int(seam.loc["HEAVY_RUC", "n_rows"])
        if parent == "HEAVY_RUC_PROXY"
        else 25
        if parent == "MVR_PROXY"
        else 0
    )
    contract["n_origins"] = contract["parent_shock"].map(
        lambda parent: int(seam.loc[parent, "n_origins"])
        if parent in seam.index
        else int(seam.loc["HEAVY_RUC", "n_origins"])
        if parent == "HEAVY_RUC_PROXY"
        else 0
    )
    contract["fy2030_span80_pct"] = contract["parent_shock"].map(
        lambda parent: round(plateau[parent][LAST_SUPPORTED_FY].apply(1.0)["span80_pct"], 4)
        if parent in plateau
        else np.nan
    )
    contract["fy2050_span80_pct"] = contract["parent_shock"].map(
        lambda parent: round(plateau[parent][FINAL_FY].apply(1.0)["span80_pct"], 4)
        if parent in plateau
        else np.nan
    )
    contract["proxy_flag"] = contract["tier"].ge(4)
    contract["owner_approved"] = contract["parent_shock"].map(
        lambda parent: "pending" if parent in ("MVR_PROXY", "TUC_FIXED", "HEAVY_RUC_PROXY") else "n/a"
    )
    contract["limitation"] = contract.apply(
        lambda row: (
            "Governed fixed component; ZERO modelled uncertainty, so the Total NLTF band does not cover it."
            if row["parent_shock"] == "TUC_FIXED"
            else "Vintage-revision proxy, not forecast error; deliberately wider than the measured quantiles."
            if row["parent_shock"] == "MVR_PROXY"
            else "Tier-5 proxy borrowed from the Heavy RUC factor; applied identically to km and revenue."
            if row["parent_shock"] == "HEAVY_RUC_PROXY"
            else "CONDITIONAL model uncertainty: actual-driver evidence, excludes Treasury-driver forecast error."
        ),
        axis=1,
    )
    contract.to_csv(OUT / "uncertainty_series_contract_draft.csv", index=False)

    # ------------------------------------------------------------- reporting
    print("=== June-year basis, seam (JY H5 = FY2030) ===")
    print(
        quantiles[quantiles["june_year_horizon"].eq(5)][
            ["stream", "n_rows", "n_origins", "raw_span80_pct", "smooth_span80_pct",
             "raw_span50_pct", "smooth_span50_pct"]
        ].round(3).to_string(index=False)
    )
    print("\n=== raw vs smoothed 80% span by June-year horizon ===")
    print(
        quantiles.pivot_table(
            index="stream", columns="june_year_horizon", values="smooth_span80_pct"
        ).round(2).to_string()
    )
    print("\n=== asymmetry at the seam (80%) ===")
    seam_rows = candidates[candidates["FY"].eq(LAST_SUPPORTED_FY)]
    print(
        seam_rows[["stream", "lower80_distance_pct", "upper80_distance_pct",
                   "asymmetry_ratio_80", "median_multiplier"]].round(4).to_string(index=False)
    )
    print("\n=== bootstrap (origin-clustered) on the seam q10/q90 ===")
    print(
        quantiles[quantiles["june_year_horizon"].eq(5)][
            ["stream", "n_origins", "raw_q10", "boot_q10_p05", "boot_q10_p95",
             "raw_q90", "boot_q90_p05", "boot_q90_p95"]
        ].round(4).to_string(index=False)
    )
    print("\n=== indicative Total NLTF 80% span (%) ===")
    total = examples[examples["series_id"].eq("total_nltf_net_revenue")]
    print(
        total.pivot_table(index="parent_shock", columns="FY", values="span80_pct")
        .round(2).to_string()
    )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

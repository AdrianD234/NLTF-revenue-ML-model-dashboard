"""Evidence for the VFM long-run composition extension.

Independent by construction: expected class values are

    frozen common pool  x  canonical source share

computed straight from ``data/vfm_202405/vfm_vkt_shares.csv``, never by calling
the allocation helper under test. Formula expectations come from
``FORMULA_DEFINITIONS``, not a copied identity dictionary.

    .venv\\Scripts\\python.exe scripts\\build_vfm_long_run_extension_evidence.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.light_fleet_allocation import (  # noqa: E402
    VFM_SCENARIO_BY_UPTAKE_BASIS,
)
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402

OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
SHARE_SOURCE = ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv"
SHARE_MANIFEST = ROOT / "data" / "vfm_202405" / "manifest.json"
ENGINES = (
    ("ensemble", Path(CURRENT_REVENUE_OUTLOOK_DIR)),
    ("ar1", Path("data") / "engine_ar1" / "current_revenue_outlook"),
)
BASES = (DEFAULT_EV_UPTAKE_MODE, "MoT VFM fast", "MoT VFM slow")
REPORT_FYS = (2030, 2031, 2040, 2050)
CLASS_KM = {
    "conventional": "light_ruc_net_km",
    "bev": "light_bev_ruc_net_km",
    "phev": "phev_ruc_net_km",
}
CLASS_REVENUE = {
    "conventional": "light_ruc_net_revenue",
    "bev": "light_bev_ruc_net_revenue",
    "phev": "phev_ruc_net_revenue",
}
UNCHANGED_SERIES = (
    "ped_vkt_per_capita", "ped_volume", "gross_ped_revenue", "net_fed_revenue",
    "heavy_ruc_net_km", "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_km", "heavy_bev_ruc_net_revenue",
    "net_mvr_revenue", "tuc_net_revenue",
)
TOLERANCE = 1e-6


def production_key(pack) -> RevenueScenarioComputationKey:
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
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


def scenario_values(pack, signature, key) -> pd.Series:
    rows, *_ = app.cached_scenario_overlay_rows(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        key,
        pack,
    )
    selected = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_name"].astype(str).eq("current_basecase")
    ].copy()
    selected["FY"] = pd.to_numeric(selected["june_year"], errors="coerce")
    selected["numeric"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "numeric"])
    return selected.groupby(["series_id", "FY"])["numeric"].first()


def line_values(pack, signature, key) -> pd.Series:
    """Line-reconciliation values: the frame carrying every formula leaf."""
    line, _residuals, _stack, _bridge = app.cached_aligned_scenario_detail_frames(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        key,
        pack,
    )
    selected = line[line["scenario_name"].astype(str).eq("current_basecase")].copy()
    selected["FY"] = pd.to_numeric(selected["FY"], errors="coerce")
    selected["numeric"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "numeric"])
    return selected.groupby(["series_id", "FY"])["numeric"].first()


def canonical_shares() -> pd.DataFrame:
    """The governed source, read directly. No helper under test involved."""
    frame = pd.read_csv(SHARE_SOURCE)
    frame = frame.rename(
        columns={
            "light_ruc_conventional_share": "conventional",
            "light_ruc_bev_share": "bev",
            "light_ruc_phev_share": "phev",
        }
    )
    return frame[["scenario", "june_year", "conventional", "bev", "phev"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shares = canonical_shares()

    # ------------------------------------------------- source contract
    source_rows: list[dict] = []
    for basis in BASES:
        scenario = VFM_SCENARIO_BY_UPTAKE_BASIS[basis]
        cell = shares[shares["scenario"].astype(str).eq(scenario)]
        covered = set(cell["june_year"].astype(int))
        required = set(range(2030, 2051))
        source_rows.append(
            {
                "uptake_basis": basis,
                "vfm_scenario": scenario,
                "first_fy": int(cell["june_year"].min()),
                "last_fy": int(cell["june_year"].max()),
                "rows": int(len(cell)),
                "covers_fy2030_fy2050": required.issubset(covered),
                "missing_fys": sorted(required - covered),
                "all_finite": bool(np.isfinite(cell[["conventional", "bev", "phev"]].to_numpy()).all()),
                "all_non_negative": bool((cell[["conventional", "bev", "phev"]] >= 0).all().all()),
                "max_abs_sum_minus_one": float(
                    (cell[["conventional", "bev", "phev"]].sum(axis=1) - 1.0).abs().max()
                ),
            }
        )
    source = pd.DataFrame(source_rows)
    source.to_csv(OUT / "vfm_long_run_share_source.csv", index=False)
    assert source["covers_fy2030_fy2050"].all(), "a VFM scenario is missing FY2030-FY2050"
    assert source["all_finite"].all() and source["all_non_negative"].all()
    assert source["max_abs_sum_minus_one"].max() < 1e-5, "shares do not sum to one"

    (OUT / "vfm_long_run_share_source_manifest.json").write_text(
        json.dumps(
            {
                "source_path": str(SHARE_SOURCE.relative_to(ROOT)).replace("\\", "/"),
                "source_sha256": hashlib.sha256(SHARE_SOURCE.read_bytes()).hexdigest(),
                "upstream_manifest": json.loads(SHARE_MANIFEST.read_text(encoding="utf-8")),
                "scenario_by_uptake_basis": {
                    basis: VFM_SCENARIO_BY_UPTAKE_BASIS[basis] for basis in BASES
                },
                "classes": list(CLASS_KM),
                "runtime_excel_access": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    pool_rows: list[dict] = []
    allocation_rows: list[dict] = []
    revenue_rows: list[dict] = []
    formula_rows: list[dict] = []
    preservation_rows: list[dict] = []

    for engine, relative in ENGINES:
        directory = ROOT / relative
        if not directory.exists():
            continue
        pack = load_revenue_outlook_pack(directory, repo_root=ROOT)
        signature = revenue_outlook_signature(directory, ROOT)
        key = production_key(pack)
        by_basis = {
            basis: scenario_values(pack, signature, key.replace(uptake_basis=basis))
            for basis in BASES
        }
        line_by_basis = {
            basis: line_values(pack, signature, key.replace(uptake_basis=basis))
            for basis in BASES
        }

        for fy in REPORT_FYS:
            pools = {
                basis: sum(float(values.get((series, fy), np.nan)) for series in CLASS_KM.values())
                for basis, values in by_basis.items()
            }
            reference = pools[DEFAULT_EV_UPTAKE_MODE]
            pool_rows.append(
                {
                    "engine": engine,
                    "FY": fy,
                    **{f"pool_{basis.split()[-1]}": value for basis, value in pools.items()},
                    "max_abs_pool_difference": max(abs(value - reference) for value in pools.values()),
                    "pool_invariant": max(abs(value - reference) for value in pools.values()) <= TOLERANCE,
                }
            )

            for basis in BASES:
                scenario = VFM_SCENARIO_BY_UPTAKE_BASIS[basis]
                share_row = shares[
                    shares["scenario"].astype(str).eq(scenario)
                    & shares["june_year"].astype(int).eq(fy)
                ]
                if share_row.empty:
                    continue
                raw = {name: float(share_row[name].iloc[0]) for name in CLASS_KM}
                total = sum(raw.values())
                normalised = {name: value / total for name, value in raw.items()}
                for component, km_series in CLASS_KM.items():
                    observed = float(by_basis[basis].get((km_series, fy), np.nan))
                    # INDEPENDENT expectation: frozen common pool x source share.
                    expected = reference * normalised[component]
                    allocation_rows.append(
                        {
                            "engine": engine,
                            "uptake_basis": basis,
                            "vfm_scenario": scenario,
                            "FY": fy,
                            "component": component,
                            "series_id": km_series,
                            "source_share": raw[component],
                            "normalised_share": normalised[component],
                            "common_pool_km": reference,
                            "expected_km": expected,
                            "observed_km": observed,
                            "abs_difference": abs(observed - expected),
                            "matches": abs(observed - expected) <= max(TOLERANCE, abs(expected) * 1e-9),
                        }
                    )
                    revenue_series = CLASS_REVENUE[component]
                    revenue_rows.append(
                        {
                            "engine": engine,
                            "uptake_basis": basis,
                            "FY": fy,
                            "component": component,
                            "series_id": revenue_series,
                            "km": observed,
                            "revenue": float(by_basis[basis].get((revenue_series, fy), np.nan)),
                            "implied_rate": (
                                float(by_basis[basis].get((revenue_series, fy), np.nan)) / observed
                                if observed
                                else np.nan
                            ),
                        }
                    )

            # Formula closure straight from FORMULA_DEFINITIONS, against the
            # line-reconciliation spine: chart rows carry only the plotted
            # series and can close exactly one identity.
            for basis in BASES:
                values = line_by_basis[basis]
                for definition in FORMULA_DEFINITIONS:
                    output = str(definition["output_series_id"])
                    observed = values.get((output, fy))
                    if observed is None:
                        continue
                    total = 0.0
                    complete = True
                    for term, sign in definition["terms"]:
                        component = values.get((str(term), fy))
                        if component is None:
                            complete = False
                            break
                        total += float(sign) * float(component)
                    if not complete:
                        continue
                    formula_rows.append(
                        {
                            "engine": engine,
                            "uptake_basis": basis,
                            "FY": fy,
                            "output_series_id": output,
                            "expression": definition["expression"],
                            "observed": float(observed),
                            "recomputed": total,
                            "residual": abs(float(observed) - total),
                            "closes": abs(float(observed) - total) <= TOLERANCE,
                        }
                    )

            # Streams the amendment must not touch.
            for series in UNCHANGED_SERIES:
                base_value = by_basis[DEFAULT_EV_UPTAKE_MODE].get((series, fy))
                if base_value is None:
                    continue
                worst = max(
                    abs(float(by_basis[basis].get((series, fy), base_value)) - float(base_value))
                    for basis in BASES
                )
                preservation_rows.append(
                    {
                        "engine": engine,
                        "FY": fy,
                        "series_id": series,
                        "base_value": float(base_value),
                        "max_abs_difference_across_bases": worst,
                        "unchanged": worst <= TOLERANCE,
                    }
                )

    pool = pd.DataFrame(pool_rows)
    pool.to_csv(OUT / "vfm_long_run_pool_invariance.csv", index=False)
    allocation = pd.DataFrame(allocation_rows)
    allocation.to_csv(OUT / "vfm_long_run_class_allocation.csv", index=False)
    revenue = pd.DataFrame(revenue_rows)
    revenue.to_csv(OUT / "vfm_long_run_revenue_impact.csv", index=False)
    formulas = pd.DataFrame(formula_rows)
    formulas.to_csv(OUT / "vfm_long_run_formula_reconciliation.csv", index=False)
    preservation = pd.DataFrame(preservation_rows)
    preservation.to_csv(OUT / "vfm_long_run_preservation_audit.csv", index=False)

    assert not allocation.empty and not pool.empty and not formulas.empty, "vacuous evidence"
    print(f"pool rows {len(pool)} | allocation {len(allocation)} | formulas {len(formulas)}")
    print(f"\npool invariant on every row: {bool(pool['pool_invariant'].all())}")
    print(f"allocation matches source share on every row: {bool(allocation['matches'].all())}")
    print(f"formula identities close: {bool(formulas['closes'].all())}")
    print(f"unchanged streams stayed unchanged: {bool(preservation['unchanged'].all())}")

    print("\n=== FY2050 class allocation, ensemble ===")
    view = allocation[allocation["engine"].eq("ensemble") & allocation["FY"].eq(2050)]
    print(
        view[["uptake_basis", "component", "normalised_share", "expected_km", "observed_km"]]
        .round(4).to_string(index=False)
    )

    print("\n=== Fast-Slow spread by series ===")
    for engine, relative in ENGINES:
        directory = ROOT / relative
        if not directory.exists():
            continue
        pack = load_revenue_outlook_pack(directory, repo_root=ROOT)
        signature = revenue_outlook_signature(directory, ROOT)
        key = production_key(pack)
        fast = scenario_values(pack, signature, key.replace(uptake_basis="MoT VFM fast"))
        slow = scenario_values(pack, signature, key.replace(uptake_basis="MoT VFM slow"))
        base = scenario_values(pack, signature, key)
        for series in (
            "light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km",
            "light_ruc_net_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue",
        ):
            spreads = []
            for fy in (2031, 2040, 2050):
                a, b = fast.get((series, fy)), slow.get((series, fy))
                c = base.get((series, fy))
                if a is None or b is None or not c:
                    continue
                spreads.append(f"FY{fy} {100*abs(a-b)/abs(c):.3f}%")
            print(f"  {engine:<9}{series:<26}{'  '.join(spreads)}")

    if not (
        pool["pool_invariant"].all()
        and allocation["matches"].all()
        and formulas["closes"].all()
        and preservation["unchanged"].all()
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

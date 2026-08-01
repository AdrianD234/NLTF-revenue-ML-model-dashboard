"""Evidence for the ev_uptake_key slot-6 collision and its corrected values.

The positional key let ONE slot mean two things:

    _official_vintage_scope        read slot 6 as the official comparator
                                   vintage id, e.g. "BEFU26";
    _heavy_bev_transition_enabled  read slot 6 as a Heavy-BEV transition flag.

Production always wrote a non-empty vintage id there, so ``bool("BEFU26")``
silently switched Heavy-BEV reclassification ON in every real render, against
the settled ``HEAVY_RUC: not_reclassified`` contract.

This script reconstructs both readings from the SAME committed packs and
reports every value the correction moves, so the movement can be checked
against the Heavy-BEV-dependent identities and nothing else.

    .venv\\Scripts\\python.exe scripts\\build_scenario_key_collision_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import (  # noqa: E402
    RevenueScenarioComputationKey,
)

OUT = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
ENGINES = (
    ("ensemble", Path(CURRENT_REVENUE_OUTLOOK_DIR)),
    ("ar1", Path("data") / "engine_ar1" / "current_revenue_outlook"),
)
# Series that legitimately depend on the Heavy-BEV reclassification, directly
# or through a governed rollup identity. Anything OUTSIDE this set moving is a
# finding, not a correction.
HEAVY_BEV_DEPENDENT = {
    "heavy_ruc_net_km",
    "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_km",
    "heavy_bev_ruc_net_revenue",
    "total_ruc_net_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
}
TOLERANCE = 1e-9


def sensitivity_key() -> tuple:
    return app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")


def corrected_key(vintage: str = "BEFU26") -> RevenueScenarioComputationKey:
    """What production builds NOW: Heavy-BEV is its own field and is Off."""
    return RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        ped_retention_sensitivity=False,
        heavy_bev_transition=False,
        official_comparator_vintage_id=vintage,
        long_run_transition_schedule_id="balanced_structural",
        long_run_shape_vintage_id="BEFU26",
    )


def pre_fix_key(vintage: str = "BEFU26") -> RevenueScenarioComputationKey:
    """What the collision actually produced: bool(vintage id) -> True."""
    return corrected_key(vintage).replace(heavy_bev_transition=bool(vintage))


def annual_values(pack, signature, key) -> pd.DataFrame:
    rows, *_ = app.cached_scenario_overlay_rows(
        signature, sensitivity_key(), PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    selected = rows[rows["time_grain"].astype(str).eq("june_year")].copy()
    selected["fy"] = pd.to_numeric(selected.get("june_year"), errors="coerce")
    selected["numeric"] = pd.to_numeric(selected.get("value"), errors="coerce")
    selected = selected.dropna(subset=["fy", "numeric"])
    return selected.groupby(
        ["scenario_name", "scenario_role", "series_id", "fy", "fed_path"], dropna=False
    )["numeric"].first()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    collision_rows = [
        {
            "finding": "slot_6_dual_meaning",
            "slot": 6,
            "reader_a": "_official_vintage_scope -> official comparator vintage id (str)",
            "reader_b": "_heavy_bev_transition_enabled -> Heavy BEV transition (bool)",
            "production_value_written": "BEFU26",
            "reader_b_resolves_to": bool("BEFU26"),
            "documented_default": False,
            "contract_breached": "HEAVY_RUC: not_reclassified",
            "detected_by_existing_tests": False,
            "why_not_detected": (
                "tests/test_canonical_base_composition.py::_key builds a 7-slot key "
                "with the Heavy-BEV flag in slot 6 and no vintage id - a key shape "
                "production never produces."
            ),
            "correction": (
                "RevenueScenarioComputationKey.heavy_bev_transition is its own bool "
                "field defaulting False; official_comparator_vintage_id is its own "
                "str field and can never be read as a flag."
            ),
        }
    ]
    # The typed key must make the old reading unreachable.
    typed = corrected_key()
    collision_rows.append(
        {
            "finding": "post_fix_resolution",
            "slot": "n/a (named fields)",
            "reader_a": f"official_comparator_vintage_id={typed.official_comparator_vintage_id!r}",
            "reader_b": f"heavy_bev_transition={typed.heavy_bev_transition!r}",
            "production_value_written": typed.official_comparator_vintage_id,
            "reader_b_resolves_to": typed.heavy_bev_transition,
            "documented_default": False,
            "contract_breached": "",
            "detected_by_existing_tests": True,
            "why_not_detected": "",
            "correction": "resolved",
        }
    )
    pd.DataFrame(collision_rows).to_csv(OUT / "scenario_key_collision_audit.csv", index=False)

    corrections: list[pd.DataFrame] = []
    for engine, relative in ENGINES:
        directory = ROOT / relative
        if not directory.exists():
            continue
        pack = load_revenue_outlook_pack(directory, repo_root=ROOT)
        signature = revenue_outlook_signature(directory, ROOT)
        before = annual_values(pack, signature, pre_fix_key())
        after = annual_values(pack, signature, corrected_key())
        common = before.index.intersection(after.index)
        assert len(common), f"{engine}: no comparable rows"
        delta = (after.loc[common] - before.loc[common]).abs()
        moved = delta[delta > TOLERANCE].index
        frame = pd.DataFrame(
            {
                "engine": engine,
                "scenario_name": [i[0] for i in moved],
                "scenario_role": [i[1] for i in moved],
                "series_id": [i[2] for i in moved],
                "FY": [int(i[3]) for i in moved],
                "fed_path": [i[4] for i in moved],
                "old_value": before.loc[moved].to_numpy(),
                "corrected_value": after.loc[moved].to_numpy(),
            }
        )
        frame["absolute_delta"] = frame["corrected_value"] - frame["old_value"]
        frame["percentage_delta"] = 100.0 * frame["absolute_delta"] / frame["old_value"].replace(0.0, pd.NA)
        frame["reason"] = (
            "Heavy BEV reclassification was switched on by bool(official vintage id) "
            "in slot 6; the corrected key leaves it Off."
        )
        frame["classification"] = frame["series_id"].map(
            lambda series: "expected" if str(series) in HEAVY_BEV_DEPENDENT else "UNEXPECTED"
        )
        corrections.append(frame)

    audit = pd.concat(corrections, ignore_index=True) if corrections else pd.DataFrame()
    audit.to_csv(OUT / "central_value_correction_audit.csv", index=False)

    # Does the Heavy-BEV overlay propagate into the governed rollups the way
    # the LIGHT composition overlay does? Measured, not assumed.
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    base = annual_values(pack, signature, corrected_key())
    heavy_on = annual_values(pack, signature, corrected_key().replace(heavy_bev_transition=True))
    light_fast = annual_values(pack, signature, corrected_key().replace(uptake_basis="MoT VFM fast"))

    def at(series_map, series_id: str, fy: int = 2030) -> float:
        selected = series_map[
            (series_map.index.get_level_values("scenario_role") == "basecase")
            & (series_map.index.get_level_values("series_id") == series_id)
            & (series_map.index.get_level_values("fy") == float(fy))
        ]
        return float(selected.iloc[0]) if len(selected) else float("nan")

    propagation = []
    for series_id in (
        "heavy_ruc_net_km",
        "heavy_ruc_net_revenue",
        "light_ruc_net_revenue",
        "total_ruc_net_revenue",
        "total_fed_ruc_net_revenue",
        "total_nltf_net_revenue",
    ):
        propagation.append(
            {
                "series_id": series_id,
                "FY": 2030,
                "base_value": at(base, series_id),
                "delta_heavy_bev_transition_on": at(heavy_on, series_id) - at(base, series_id),
                "delta_vfm_fast_light_composition": at(light_fast, series_id) - at(base, series_id),
            }
        )
    propagation_frame = pd.DataFrame(propagation)
    propagation_frame["heavy_overlay_reaches_rollup"] = (
        propagation_frame["delta_heavy_bev_transition_on"].abs() > TOLERANCE
    )
    propagation_frame["light_overlay_reaches_rollup"] = (
        propagation_frame["delta_vfm_fast_light_composition"].abs() > TOLERANCE
    )
    propagation_frame.to_csv(OUT / "heavy_bev_rollup_propagation_audit.csv", index=False)
    print("\nrollup propagation at FY2030 (basecase):")
    print(propagation_frame.to_string(index=False))

    if audit.empty:
        print("no value movement from the correction")
        return
    print(f"{len(audit)} rows moved across {audit['engine'].nunique()} engine(s)")
    print(audit.groupby(["engine", "series_id"]).size().to_string())
    unexpected = audit[audit["classification"].eq("UNEXPECTED")]
    if not unexpected.empty:
        print("\nUNEXPECTED movement outside the Heavy-BEV-dependent identities:")
        print(unexpected[["engine", "series_id", "FY", "percentage_delta"]].to_string(index=False))
        raise SystemExit(1)
    print("\nall movement is inside the Heavy-BEV-dependent activity and revenue identities")


if __name__ == "__main__":
    main()

"""Emit the complete official-comparator policy audit.

Every affected official component gets a row per June year and policy state,
including hidden source leaves such as Heavy BEV that never become visible
chart rows but do move the totals. The earlier four-row audit could not
evidence any of the hard gates below.

Usage: python scripts/build_official_policy_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.rate_paths import (  # noqa: E402
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
    FED_POLICY_STATE_PUBLISHED,
    official_comparator_policy_audit_frame,
)

OUT = ROOT / "artifacts" / "p0_light_fleet_fix"
CLOSURE_TOL = 1e-6
RUC_CLASS_LEAVES = {
    "conventional_light_ruc_revenue",
    "light_bev_revenue",
    "phev_revenue",
    "heavy_ruc_revenue",
    "heavy_bev_revenue",
}
REQUIRED_COMPONENTS = RUC_CLASS_LEAVES | {
    "gross_ped_revenue",
    "net_fed_revenue",
    "total_ruc_net_revenue",
    "total_nltf_net_revenue",
}
FIXED_COMPONENTS = {"ruc_admin_revenue", "ruc_refunds", "fed_refunds", "mvr_admin_revenue", "mvr_refunds"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = [
        official_comparator_policy_audit_frame(ROOT, state)
        for state in (FED_POLICY_STATE_NO_UPLIFT, FED_POLICY_STATE_DELAYED_6M)
    ]
    audit = pd.concat(frames, ignore_index=True).sort_values(
        ["policy_state", "fy", "component"], kind="stable"
    )
    audit.to_csv(OUT / "official_policy_audit.csv", index=False)

    no_uplift = audit[audit["policy_state"].eq(FED_POLICY_STATE_NO_UPLIFT)]
    delayed = audit[audit["policy_state"].eq(FED_POLICY_STATE_DELAYED_6M)]

    failures: list[str] = []

    # Gate: published leaves MBU26 untouched.
    published = official_comparator_policy_audit_frame(ROOT, FED_POLICY_STATE_PUBLISHED)
    if not published.empty:
        failures.append(f"published state produced {len(published)} adjustment rows; must produce none")

    # Gate: delayed differs only in FY2027.
    delayed_years = sorted(set(delayed["fy"].astype(int)))
    if delayed_years != [2027]:
        failures.append(f"delayed policy touches {delayed_years}; must touch FY2027 only")

    # Gate: no-uplift covers every official FY through the source cutoff.
    no_uplift_years = set(no_uplift["fy"].astype(int))
    expected_years = set(range(min(no_uplift_years), max(no_uplift_years) + 1))
    if no_uplift_years != expected_years:
        failures.append(f"no-uplift has gaps: {sorted(expected_years - no_uplift_years)}")

    # Gate: all five RUC class leaves are included, plus every required component.
    for state, frame in (("no_uplift", no_uplift), ("delay_6m", delayed)):
        missing = REQUIRED_COMPONENTS - set(frame["component"].astype(str))
        if missing:
            failures.append(f"{state} audit is missing components: {sorted(missing)}")

    # Gate: administration and refunds do not change.
    fixed = audit[audit["component"].isin(FIXED_COMPONENTS)]
    if fixed.empty:
        failures.append("no fixed administration/refund rows were audited")
    elif float(fixed["delta"].abs().max()) != 0.0:
        failures.append(f"fixed components moved by up to {float(fixed['delta'].abs().max())}")

    # Gate: the three totals close within 1e-6.
    worst = float(audit["closure_residual"].abs().max())
    if worst > CLOSURE_TOL:
        failures.append(f"closure residual {worst} exceeds {CLOSURE_TOL}")

    # Gate: the FY2027 wedge is 6c and FY2028+ is 12c.
    for fy, expected in ((2027, 0.06), (2028, 0.12)):
        rows = no_uplift[no_uplift["fy"].eq(fy)]
        if rows.empty:
            failures.append(f"no-uplift has no FY{fy} row")
            continue
        wedge = float(rows["nominal_wedge_nzd_per_litre"].iloc[0])
        if abs(wedge - expected) > 2e-3:
            failures.append(f"FY{fy} no-uplift wedge is {wedge}, expected ~{expected}")

    print(f"official policy audit rows: {len(audit)} -> {OUT / 'official_policy_audit.csv'}")
    print(f"  no-uplift FY range      : {min(no_uplift_years)}-{max(no_uplift_years)}")
    print(f"  delayed FY range        : {delayed_years}")
    print(f"  components per FY       : {audit['component'].nunique()}")
    print(f"  max |closure residual|  : {worst:.3e}")
    source_residual = float(audit["published_source_residual"].abs().max())
    print(f"  max |published source residual| (reported, NOT corrected): {source_residual:.6f}")

    if failures:
        print("\nFAIL")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nPASS: every official policy gate holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

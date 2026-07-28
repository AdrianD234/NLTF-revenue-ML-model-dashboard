"""FY2025-FY2030 before/after impact of the light-fleet allocation correction.

"Before" is the lambda-allocated production pack at the investigation head
commit; "after" is the working tree. Both are read from committed artifacts,
so the audit is reproducible and does not re-run either engine.

The audited Checkpoint 3 candidate P0/L1 is the expected structural reference.
This is not a calibration target - MBU26 proximity decides nothing - but if
the implemented Base path does not reproduce the audited candidate under the
same macro, rate and policy states, that is a defect and the script says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_dashboard.light_fleet_allocation import (  # noqa: E402
    ALLOCATION_BASIS_ID,
    LAST_DECISION_GRADE_ANNUAL_FY,
)

OUT = ROOT / "artifacts" / "fleet_allocation_semantics"
OUT.mkdir(parents=True, exist_ok=True)

# Committed, hash-pinned snapshot of the pre-correction pack. Not a Git object:
# a shallow CI checkout may not contain the investigation head commit.
LEGACY_SNAPSHOT = OUT / "legacy_investigation_snapshot"
SCENARIO = "current_basecase"
FYS = list(range(2025, LAST_DECISION_GRADE_ANNUAL_FY + 1))
PACK_REL = "data/engine_ar1/current_revenue_outlook"

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
    "gross_fed_revenue",
    "net_fed_revenue",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
    "total_ruc_net_revenue",
    "total_nltf_net_revenue",
]


def _legacy(path: str) -> pd.DataFrame:
    """Read a pre-correction pack table from the hash-pinned legacy snapshot."""
    import hashlib
    import json

    name = path.rsplit("/", 1)[-1]
    manifest = json.loads((LEGACY_SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["file"] == name)
    target = LEGACY_SNAPSHOT / name
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"Legacy snapshot {name} has changed: expected {entry['sha256']}, found {digest}.")
    return pd.read_csv(target)


def _annual(frame: pd.DataFrame, scenario: str = SCENARIO) -> pd.DataFrame:
    sel = frame[
        frame["scenario_name"].astype(str).eq(scenario)
        & frame["FY"].between(min(FYS), max(FYS))
    ]
    return sel.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first").sort_index()


def main() -> int:
    before = _annual(_legacy(f"{PACK_REL}/revenue_line_reconciliation.csv"))
    after = _annual(pd.read_csv(ROOT / PACK_REL / "revenue_line_reconciliation.csv"))
    official = _legacy(f"{PACK_REL}/revenue_line_reconciliation.csv")
    official = _annual(official, "mbu26_official")

    rows = []
    for series in ACTIVITY + REVENUE:
        for fy in FYS:
            old = float(before.loc[fy, series]) if series in before.columns and fy in before.index else float("nan")
            new = float(after.loc[fy, series]) if series in after.columns and fy in after.index else float("nan")
            mbu = float(official.loc[fy, series]) if series in official.columns and fy in official.index else float("nan")
            rows.append(
                {
                    "series_id": series,
                    "kind": "activity" if series in ACTIVITY else "revenue",
                    "FY": fy,
                    "old_lambda_production": old,
                    "corrected_production": new,
                    "mbu26_official": mbu,
                    "absolute_change": new - old,
                    "percent_change": (100.0 * (new / old - 1.0)) if old else float("nan"),
                    "corrected_vs_mbu26_pct": (100.0 * (new / mbu - 1.0)) if mbu else float("nan"),
                    "old_vs_mbu26_pct": (100.0 * (old / mbu - 1.0)) if mbu else float("nan"),
                    "allocation_basis": ALLOCATION_BASIS_ID,
                }
            )
    impact = pd.DataFrame(rows)

    # ---- lineage: formula text before and after -------------------------
    before_lines = _legacy(f"{PACK_REL}/revenue_line_reconciliation.csv")
    after_lines = pd.read_csv(ROOT / PACK_REL / "revenue_line_reconciliation.csv")

    def _formulas(frame: pd.DataFrame) -> dict[str, str]:
        sel = frame[frame["scenario_name"].astype(str).eq(SCENARIO) & frame["FY"].eq(2030)]
        return {
            str(record.series_id): str(getattr(record, "formula", "") or "")
            for record in sel.itertuples()
        }

    old_f, new_f = _formulas(before_lines), _formulas(after_lines)
    lineage = pd.DataFrame(
        [
            {
                "series_id": key,
                "old_formula": old_f.get(key, ""),
                "new_formula": new_f.get(key, ""),
                "changed": old_f.get(key, "") != new_f.get(key, ""),
            }
            for key in sorted(set(old_f) | set(new_f))
        ]
    )

    # ---- does the corrected Base path reproduce the audited candidate? ---
    audited_path = OUT / "combined_light_fleet_paths.csv"
    reference_rows = []
    if audited_path.exists():
        audited = pd.read_csv(audited_path)
        audited = audited[audited["variant"].eq("P0/L1")].set_index("june_year")
        for fy in FYS:
            if fy not in audited.index:
                continue
            for series, column in [
                ("light_ruc_net_km", "conventional_light_ruc"),
                ("light_bev_ruc_net_km", "light_bev"),
                ("phev_ruc_net_km", "phev"),
                ("light_petrol_vkt", "light_petrol_vkt"),
            ]:
                implemented = (
                    float(after.loc[fy, series]) if series in after.columns and fy in after.index else float("nan")
                )
                expected = float(audited.loc[fy, column])
                reference_rows.append(
                    {
                        "FY": fy,
                        "series_id": series,
                        "implemented": implemented,
                        "audited_p0_l1_candidate": expected,
                        "abs_delta": abs(implemented - expected),
                        "matches": bool(abs(implemented - expected) <= 1e-4),
                    }
                )
    reference = pd.DataFrame(reference_rows)

    # ---- actuals and official rows must be untouched ---------------------
    unchanged_rows = []
    for scenario in ["mbu26_official"]:
        old_frame = _annual(before_lines, scenario)
        new_frame = _annual(after_lines, scenario)
        shared = sorted(set(old_frame.columns) & set(new_frame.columns))
        worst = 0.0
        for series in shared:
            for fy in FYS:
                if fy in old_frame.index and fy in new_frame.index:
                    a = float(old_frame.loc[fy, series])
                    b = float(new_frame.loc[fy, series])
                    if pd.notna(a) and pd.notna(b):
                        worst = max(worst, abs(a - b))
        unchanged_rows.append({"scenario": scenario, "series_checked": len(shared), "max_abs_delta": worst})
    # FY2025 actual anchor across the current scenario
    fy25 = 0.0
    for series in ACTIVITY + REVENUE:
        if series in before.columns and series in after.columns and 2025 in before.index and 2025 in after.index:
            a, b = float(before.loc[2025, series]), float(after.loc[2025, series])
            if pd.notna(a) and pd.notna(b):
                fy25 = max(fy25, abs(a - b))
    unchanged_rows.append({"scenario": "current_basecase_FY2025_actual_anchor", "series_checked": len(ACTIVITY + REVENUE), "max_abs_delta": fy25})
    unchanged = pd.DataFrame(unchanged_rows)

    impact.round(6).to_csv(OUT / "production_impact_audit.csv", index=False)
    lineage.to_csv(OUT / "production_impact_lineage.csv", index=False)
    if not reference.empty:
        reference.round(9).to_csv(OUT / "production_impact_vs_audited_candidate.csv", index=False)
    unchanged.round(12).to_csv(OUT / "production_impact_unchanged_checks.csv", index=False)

    print("=== headline FY2026-FY2030 ===")
    head = impact[impact["series_id"].isin(["light_ruc_net_km", "light_petrol_vkt", "gross_ped_revenue", "total_ruc_net_revenue", "total_nltf_net_revenue"]) & impact["FY"].gt(2025)]
    print(
        head.pivot_table(index="FY", columns="series_id", values=["old_lambda_production", "corrected_production"]).round(2).to_string()
    )
    print("\n=== total NLTF ===")
    total = impact[impact["series_id"].eq("total_nltf_net_revenue")]
    print(total[["FY", "old_lambda_production", "corrected_production", "mbu26_official", "absolute_change", "percent_change", "old_vs_mbu26_pct", "corrected_vs_mbu26_pct"]].round(2).to_string(index=False))

    print("\n=== unchanged checks ===")
    print(unchanged.to_string(index=False))

    if not reference.empty:
        mismatches = reference[~reference["matches"]]
        print(f"\n=== vs audited P0/L1 candidate: {len(reference) - len(mismatches)}/{len(reference)} match ===")
        if not mismatches.empty:
            print(mismatches.to_string(index=False))
            print("\nIMPLEMENTED BASE PATH DOES NOT REPRODUCE THE AUDITED CANDIDATE.")
            return 1

    if float(unchanged["max_abs_delta"].max()) > 1e-9:
        print("\nOFFICIAL OR ACTUAL VALUES CHANGED.")
        return 1
    print("\nActuals and MBU26 official rows are unchanged; Base path reproduces the audited candidate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

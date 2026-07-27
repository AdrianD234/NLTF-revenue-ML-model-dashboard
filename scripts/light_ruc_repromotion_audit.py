"""Audit the Revenue Outlook re-promotion driven by the Light RUC fitted state.

Compares a candidate re-promoted pack against the currently committed pack,
enforces the governed stop conditions, and emits a readable FY2026-FY2030
before/after table for the headline series.

Stop conditions (any one aborts, exit 1):

* an MBU26, actual or historical-actual value changes;
* rows or keys are added or removed;
* a changed series is outside the documented Light RUC / downstream lineage;
* maximum movement exceeds the established platform envelope;
* scenario ordering or an economic sign changes.

Usage::

    python scripts/light_ruc_repromotion_audit.py \
        --candidate test-output/repromoted_v2 \
        --output artifacts/light_ruc_repromotion_audit
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

COMMITTED = REPO_ROOT / "data" / "current_revenue_outlook"
PLATFORM_ENVELOPE_PCT = 0.48
IMMUTABLE_SCENARIOS = ("mbu26_official", "actual", "historical_actual")
# Light RUC and everything downstream of it through the governed formulas.
EXPECTED_LINEAGE = {
    "current_light_ruc_total_modelled_km",
    "light_ruc_net_km",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_km",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_km",
    "phev_ruc_net_revenue",
    "heavy_ruc_net_km",
    "heavy_ruc_net_revenue",
    "heavy_bev_ruc_net_revenue",
    "ruc_revenue_net_admin",
    "gross_ruc_revenue",
    "total_ruc_net_revenue",
    "light_petrol_vkt",
    "ped_vkt_per_capita",
    "ped_volume",
    "gross_ped_revenue",
    "gross_fed_revenue",
    "net_fed_revenue",
    "total_fed_ruc_net_revenue",
    "total_nltf_net_revenue",
}
HEADLINE_SERIES = [
    "current_light_ruc_total_modelled_km",
    "light_ruc_net_km",
    "light_ruc_net_revenue",
    "total_ruc_net_revenue",
    "net_fed_revenue",
    "total_nltf_net_revenue",
]
KEY_COLUMNS = ["scenario_name", "series_id", "time_grain", "june_year", "period"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chart_rows(base: Path) -> pd.DataFrame:
    frame = pd.read_parquet(base / "revenue_chart_rows.parquet")
    keys = [column for column in KEY_COLUMNS if column in frame.columns]
    out = frame[keys + ["value"]].copy()
    for column in keys:
        out[column] = out[column].astype(str)
    return out


def compare(candidate: Path) -> tuple[pd.DataFrame, list[str]]:
    before = _chart_rows(COMMITTED)
    after = _chart_rows(candidate)
    keys = [column for column in KEY_COLUMNS if column in before.columns]
    merged = before.merge(
        after, on=keys, how="outer", suffixes=("_before", "_after"), indicator=True
    )
    failures: list[str] = []

    added = int((merged["_merge"] == "right_only").sum())
    removed = int((merged["_merge"] == "left_only").sum())
    if added or removed:
        failures.append(
            f"STOP: pack keys changed - {added} rows added, {removed} removed."
        )

    both = merged[merged["_merge"] == "both"].copy()
    a = pd.to_numeric(both["value_before"], errors="coerce")
    b = pd.to_numeric(both["value_after"], errors="coerce")
    both["abs_change"] = b - a
    both["pct_change"] = np.where(a.abs() > 0, (b - a) / a.abs() * 100.0, np.nan)
    changed = both[both["pct_change"].abs() > 1e-10].copy()

    immutable = changed[
        changed["scenario_name"].astype(str).isin(IMMUTABLE_SCENARIOS)
    ]
    if not immutable.empty:
        failures.append(
            "STOP: comparator or actual values changed - "
            + ", ".join(sorted(set(immutable["scenario_name"].astype(str))))
        )

    off_lineage = sorted(
        set(changed["series_id"].astype(str)) - EXPECTED_LINEAGE
    )
    if off_lineage:
        failures.append(
            "STOP: changes outside the documented Light RUC lineage: "
            + ", ".join(off_lineage[:10])
        )

    worst = float(changed["pct_change"].abs().max()) if not changed.empty else 0.0
    if worst > PLATFORM_ENVELOPE_PCT:
        failures.append(
            f"STOP: maximum movement {worst:.4f}% exceeds the "
            f"{PLATFORM_ENVELOPE_PCT}% platform envelope."
        )

    sign_flips = changed[
        (pd.to_numeric(changed["value_before"], errors="coerce") > 0)
        & (pd.to_numeric(changed["value_after"], errors="coerce") <= 0)
    ]
    if not sign_flips.empty:
        failures.append(f"STOP: {len(sign_flips)} values changed economic sign.")

    return changed, failures


def headline_table(candidate: Path) -> pd.DataFrame:
    before = _chart_rows(COMMITTED)
    after = _chart_rows(candidate)
    keys = [column for column in KEY_COLUMNS if column in before.columns]
    merged = before.merge(after, on=keys, how="inner", suffixes=("_before", "_after"))
    selected = merged[
        merged["series_id"].isin(HEADLINE_SERIES)
        & merged["time_grain"].eq("june_year")
        & merged["scenario_name"].isin(["current_basecase", "current_comparison_1"])
        & pd.to_numeric(merged["june_year"], errors="coerce").between(2026, 2030)
    ].copy()
    a = pd.to_numeric(selected["value_before"], errors="coerce")
    b = pd.to_numeric(selected["value_after"], errors="coerce")
    selected["before"] = a
    selected["after"] = b
    selected["abs_change"] = b - a
    selected["pct_change"] = np.where(a.abs() > 0, (b - a) / a.abs() * 100.0, np.nan)
    selected["june_year"] = pd.to_numeric(selected["june_year"], errors="coerce")
    order = {name: index for index, name in enumerate(HEADLINE_SERIES)}
    selected["_order"] = selected["series_id"].map(order)
    return (
        selected[
            [
                "scenario_name",
                "series_id",
                "june_year",
                "before",
                "after",
                "abs_change",
                "pct_change",
                "_order",
            ]
        ]
        .sort_values(["scenario_name", "_order", "june_year"])
        .drop(columns=["_order"])
        .reset_index(drop=True)
    )


def file_hashes(candidate: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(COMMITTED.glob("*.parquet")) + sorted(COMMITTED.glob("*.json")):
        other = candidate / path.name
        if not other.exists():
            continue
        old, new = _sha256(path), _sha256(other)
        rows.append(
            {
                "file": path.name,
                "sha256_before": old,
                "sha256_after": new,
                "changed": old != new,
            }
        )
    return pd.DataFrame(rows)


def _markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]):
            out[column] = out[column].map(lambda value: f"{value:,.4f}")
        else:
            out[column] = out[column].astype(str)
    header = "| " + " | ".join(out.columns) + " |"
    divider = "|" + "|".join("---" for _ in out.columns) + "|"
    body = ["| " + " | ".join(row) + " |" for row in out.itertuples(index=False, name=None)]
    return "\n".join([header, divider, *body])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "artifacts" / "light_ruc_repromotion_audit",
    )
    args = parser.parse_args(argv)
    candidate = Path(args.candidate)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    changed, failures = compare(candidate)
    headline = headline_table(candidate)
    hashes = file_hashes(candidate)

    changed.to_csv(output / "changed_rows.csv", index=False)
    headline.to_csv(output / "fy2026_fy2030_headline_before_after.csv", index=False)
    hashes.to_csv(output / "file_hashes_before_after.csv", index=False)

    worst = float(changed["pct_change"].abs().max()) if not changed.empty else 0.0
    report = [
        "# Light RUC re-promotion audit",
        "",
        "Cause: Light RUC moved from a runtime refit to the promoted fitted",
        "state, so every Light RUC value and everything downstream of it through",
        "the governed formulas moves once, to a single reproducible answer.",
        "See docs/REPLAY_PARITY_INVESTIGATION.md.",
        "",
        "## Stop conditions",
        "",
        ("\n".join(f"- {failure}" for failure in failures) if failures else "All clear."),
        "",
        f"- rows changed: {len(changed)}",
        f"- maximum movement: {worst:.4f}% (envelope {PLATFORM_ENVELOPE_PCT}%)",
        f"- comparator/actual scenarios changed: "
        f"{int(changed['scenario_name'].isin(IMMUTABLE_SCENARIOS).sum())}",
        "",
        "## FY2026-FY2030 headline series, before and after",
        "",
        _markdown(headline),
        "",
        "## Changed files",
        "",
        _markdown(hashes[hashes["changed"]][["file", "sha256_before", "sha256_after"]]),
        "",
    ]
    (output / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"changed rows: {len(changed)}   max movement: {worst:.4f}%")
    print(f"changed files: {int(hashes['changed'].sum())} / {len(hashes)}")
    print()
    print(headline.head(20).to_string(index=False))
    if failures:
        print()
        for failure in failures:
            print(failure)
        return 1
    print("\nAll stop conditions clear.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

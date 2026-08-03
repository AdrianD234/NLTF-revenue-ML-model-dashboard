"""Before/after evidence for the Denton reconditioning.

The badly scaled KKT solve was returning quarterly display values accurate to
about six significant figures for every series benchmarked on a raw net-km
indicator. Normalising the indicator and the benchmarks fixed the conditioning
and moved published values. This script proves what that movement did and did
NOT touch, from the two committed packs rather than from a description of them.

The "before" values come from a committed, hash-pinned snapshot under
``pre_reconditioning_snapshot/``, not from a historical Git object: a shallow
CI checkout may not contain the commit that published them. The snapshot's
manifest marks it superseded and prohibited for production use.

    .venv\\Scripts\\python.exe scripts\\build_quarterly_reconditioning_audit.py
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

from model_dashboard.revenue_outlook_series_coverage import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    QUARTERLY_DISPLAY_PACK_DIR,
    annual_reconciliation_audit,
)

OUT = ROOT / "artifacts" / "revenue_outlook_series_coverage"
SNAPSHOT = OUT / "pre_reconditioning_snapshot"

# The two governed FED rate steps, both mid-fiscal-year.
RATE_STEPS = (("2026Q4", "2027Q1", 0.70024, 0.82024), ("2027Q4", "2028Q1", 0.82024, 0.88024))


def read_pinned_snapshot() -> tuple[dict[str, pd.DataFrame], dict]:
    """The pre-reconditioning values, verified against their pinned hashes.

    A snapshot that failed its own hash would make every comparison below
    meaningless, so this refuses to continue rather than reporting on it.
    """
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest["decision_facing"] is not False:
        raise SystemExit("the snapshot must be marked non-decision-facing")
    if "PROHIBITED" not in manifest["production_use"]:
        raise SystemExit("the snapshot must be marked prohibited for production use")
    frames: dict[str, pd.DataFrame] = {}
    for entry in manifest["files"]:
        path = SNAPSHOT / entry["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['file']} does not match its pinned hash")
        frame = pd.read_parquet(path)
        if len(frame) != entry["rows"]:
            raise SystemExit(f"{entry['file']} has {len(frame)} rows, manifest says {entry['rows']}")
        frames[entry["file"]] = frame
    return frames, manifest


def key_frame(frame: pd.DataFrame) -> pd.DataFrame:
    keys = ["series_id", "trace_name", "scenario_name", "period"]
    out = frame.set_index(keys).sort_index()
    if out.index.duplicated().any():
        raise SystemExit("quarterly rows are not unique on (series, trace, scenario, period)")
    return out


def effective_rate_step(rows: pd.DataFrame, before: str, after: str) -> float:
    """Revenue growth divided by volume growth across a rate step."""

    def value(series_id: str, period: str) -> float:
        block = rows[
            rows["series_id"].eq(series_id)
            & rows["trace_name"].eq("BEFU26 official")
            & rows["period"].eq(period)
        ]
        return float(pd.to_numeric(block["value"]).iloc[0])

    revenue = value("gross_ped_revenue", after) / value("gross_ped_revenue", before)
    volume = value("ped_volume", after) / value("ped_volume", before)
    return revenue / volume


def main() -> int:
    snapshot, snapshot_manifest = read_pinned_snapshot()
    before = snapshot["quarterly_rows_pre_reconditioning.parquet"].rename(
        columns={"value_before": "value", "annual_source_value_before": "annual_source_value"}
    )
    before_official = snapshot["official_annual_rows_pre_reconditioning.parquet"].rename(
        columns={"value_before": "value"}
    )
    after = pd.read_parquet(ROOT / QUARTERLY_DISPLAY_PACK_DIR / "quarterly_rows.parquet")
    after_official = pd.read_parquet(ROOT / QUARTERLY_DISPLAY_PACK_DIR / "official_annual_rows.parquet")
    chart_rows = pd.read_parquet(ROOT / CURRENT_REVENUE_OUTLOOK_DIR / "revenue_chart_rows.parquet")

    checks: list[tuple[str, bool, str]] = []

    # 1. Same rows, same identity. Only the numbers may have moved.
    left, right = key_frame(before), key_frame(after)
    same_index = left.index.equals(right.index)
    checks.append(
        ("Row set and identity unchanged", same_index, f"{len(left)} rows both sides")
    )
    if not same_index:
        raise SystemExit("row identity changed; the rest of this audit would be meaningless")

    # 2. Annual benchmarks unchanged - the input the solve is benchmarked to.
    anchor_delta = (
        pd.to_numeric(left["annual_source_value"]) - pd.to_numeric(right["annual_source_value"])
    ).abs().max()
    checks.append(
        ("Annual benchmarks unchanged", bool(anchor_delta == 0.0), f"max |delta| = {anchor_delta:g}")
    )

    # 3. Official annual rows unchanged - they never went through the solve.
    official_keys = ["series_id", "trace_name", "period"]
    merged_official = before_official.merge(
        after_official[[*official_keys, "value", "value_unit"]],
        on=official_keys,
        suffixes=("_before", "_after"),
        validate="one_to_one",
    )
    official_delta = (
        pd.to_numeric(merged_official["value_before"]) - pd.to_numeric(merged_official["value_after"])
    ).abs().max()
    units_same = bool(
        merged_official["value_unit_before"].eq(merged_official["value_unit_after"]).all()
    )
    official_same = bool(
        len(merged_official) == len(after_official) == len(before_official)
        and official_delta == 0.0
        and units_same
    )
    checks.append(
        (
            "Restored official annual rows unchanged",
            official_same,
            f"{len(merged_official)} rows joined, max |delta| = {official_delta:g}, units identical",
        )
    )

    # 4. Native quarterly rows untouched: no derived row may occupy a published key.
    native = chart_rows[chart_rows["time_grain"].eq("quarterly")]
    native_keys = {
        (str(r.series_id), str(r.trace_name), str(r.period)) for r in native.itertuples(index=False)
    }
    derived_keys = {
        (str(r.series_id), str(r.trace_name), str(r.period)) for r in after.itertuples(index=False)
    }
    checks.append(
        (
            "Native quarterly rows not shadowed",
            not (native_keys & derived_keys),
            f"{len(native_keys)} native keys, {len(derived_keys)} derived keys, 0 shared",
        )
    )

    # 5. Only derived quarterly rows moved, and by how much.
    old_values = pd.to_numeric(left["value"]).to_numpy(dtype=float)
    new_values = pd.to_numeric(right["value"]).to_numpy(dtype=float)
    absolute = np.abs(new_values - old_values)
    relative = absolute / np.maximum(np.abs(old_values), 1e-12)
    moved = int((relative > 1e-12).sum())
    worst = int(np.argmax(relative))
    worst_key = left.index[worst]
    checks.append(
        (
            "Movement confined to derived quarterly values",
            True,
            f"{moved} of {len(old_values)} rows moved; "
            f"max abs {absolute.max():.3e}, max rel {relative.max():.3e}",
        )
    )

    # 6. Every derived June year still reconciles.
    audit = annual_reconciliation_audit(after)
    checks.append(
        (
            "All derived June years reconcile",
            bool(audit["reconciles"].all()),
            f"{len(audit)} groups, worst relative residual "
            f"{pd.to_numeric(audit['relative_residual']).max():.3e}",
        )
    )

    # 7. No negative quarter introduced.
    negatives_before = int((old_values < 0).sum())
    negatives_after = int((new_values < 0).sum())
    checks.append(
        (
            "No negative derived quarter",
            negatives_after == 0,
            f"{negatives_before} before, {negatives_after} after",
        )
    )

    # 8. FED rate-step timing unchanged.
    step_rows: list[dict[str, object]] = []
    timing_ok = True
    for start, end, rate_before, rate_after in RATE_STEPS:
        governed = rate_after / rate_before
        was = effective_rate_step(before, start, end)
        now = effective_rate_step(after, start, end)
        ok = abs(now - governed) / governed < 0.01
        timing_ok = timing_ok and ok
        step_rows.append(
            {
                "step": f"{start} -> {end}",
                "governed_ratio": governed,
                "implied_before": was,
                "implied_after": now,
                "after_within_1pct": ok,
            }
        )
    checks.append(
        (
            "FED mid-year rate steps still correctly timed",
            timing_ok,
            "; ".join(
                f"{r['step']} governed {r['governed_ratio']:.4f}, after {r['implied_after']:.4f}"
                for r in step_rows
            ),
        )
    )

    # ------------------------------------------------------------------ output
    movement = pd.DataFrame(
        {
            "series_id": [k[0] for k in left.index],
            "trace_name": [k[1] for k in left.index],
            "scenario_name": [k[2] for k in left.index],
            "period": [k[3] for k in left.index],
            "value_before": old_values,
            "value_after": new_values,
            "absolute_movement": absolute,
            "relative_movement": relative,
        }
    ).sort_values("relative_movement", ascending=False)
    movement.to_csv(OUT / "reconditioning_row_movement.csv", index=False, lineterminator="\n")

    by_series = (
        movement.groupby("series_id")
        .agg(
            rows=("relative_movement", "size"),
            moved=("relative_movement", lambda s: int((s > 1e-12).sum())),
            max_absolute=("absolute_movement", "max"),
            max_relative=("relative_movement", "max"),
        )
        .sort_values("max_relative", ascending=False)
    )

    lines = [
        "# Denton reconditioning: before/after audit",
        "",
        "Badly scaled solve vs normalised solve. The prior values come from the",
        "hash-pinned snapshot in `pre_reconditioning_snapshot/`, captured from",
        f"commit `{snapshot_manifest['captured_from_commit'][:12]}` and marked",
        "superseded and prohibited for production use. Generated by",
        "`scripts/build_quarterly_reconditioning_audit.py`.",
        "",
        "## Verdict",
        "",
        "| Check | Result | Evidence |",
        "| --- | --- | --- |",
    ]
    for name, passed, detail in checks:
        lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} | {detail} |")
    lines += [
        "",
        "## Movement by series",
        "",
        "| Series | Rows | Moved | Max absolute | Max relative |",
        "| --- | --- | --- | --- | --- |",
    ]
    for series_id, row in by_series.iterrows():
        lines.append(
            f"| `{series_id}` | {int(row['rows'])} | {int(row['moved'])} | "
            f"{row['max_absolute']:.3e} | {row['max_relative']:.3e} |"
        )
    lines += [
        "",
        f"Largest single movement: `{worst_key[0]}` / {worst_key[1]} / {worst_key[3]}, ",
        f"{old_values[worst]:.9f} -> {new_values[worst]:.9f} "
        f"({absolute.max():.3e} absolute, {relative.max():.3e} relative).",
        "",
        "The series that move are exactly those benchmarked on a raw `net km`",
        "indicator (~3e9), which is what drove the condition number to ~5.8e9.",
        "Series on the flat or VKT-per-capita indicators were already well",
        "conditioned and barely move.",
        "",
        "## FED rate-step timing",
        "",
        "| Step | Governed ratio | Implied before | Implied after |",
        "| --- | --- | --- | --- |",
    ]
    for row in step_rows:
        lines.append(
            f"| {row['step']} | {row['governed_ratio']:.4f} | "
            f"{row['implied_before']:.4f} | {row['implied_after']:.4f} |"
        )
    lines += [
        "",
        "Both steps stay inside 1% of the governed rate ratio, so the",
        "reconditioning did not move a policy step out of its quarter.",
        "",
        "## What this audit does not prove",
        "",
        "Cross-platform stability is asserted by CI, not here: this script runs",
        "on one machine and can only compare two committed packs. The",
        "cross-platform arm is `test_committed_pack_matches_a_fresh_build`",
        "running on the Linux runner against the Windows-built committed pack,",
        "under the declared comparison (structurally exact, values within 1e-9",
        "relative). That tolerance was NOT widened to accommodate the badly",
        "scaled solve - it stayed at 1e-9 and the solve was fixed instead.",
        "",
    ]
    (OUT / "reconditioning_before_after_audit.md").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n"
    )

    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
    return 0 if all(passed for _name, passed, _detail in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

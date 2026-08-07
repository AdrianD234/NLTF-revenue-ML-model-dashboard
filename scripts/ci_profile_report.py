"""Turn one profiling run into the evidence that decides what to optimise.

Reads the JUnit XML a `profile` tier run produced and aggregates it by test, by
file and by marker, then reports the minimum set of tests responsible for 50%,
75% and 90% of total runtime.

That last number is the one that matters. If 90% of a 70-minute suite lives in
fifteen tests, splitting the suite across parallel jobs is the wrong move — it
would raise total billed minutes while barely moving wall time. Fixing those
fifteen is the right move.

Usage:
    python scripts/ci_profile_report.py --junit artifacts/ci_optimisation/profile_junit.xml
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

# Tests whose cost is structural rather than incidental. Each is a different
# remedy, so they are inventoried separately rather than lumped into "slow".
APP_TEST_PATTERN = re.compile(r"AppTest|streamlit_app|app_test", re.IGNORECASE)
REFERENCE_PIPELINE_PATTERN = re.compile(
    r"reference|vnext|pipeline|replay|rebuild|materiali[sz]", re.IGNORECASE
)


def parse_junit(path: pathlib.Path) -> list[dict]:
    root = ET.parse(path).getroot()
    cases = []
    for case in root.iter("testcase"):
        classname = case.get("classname", "")
        name = case.get("name", "")
        time = float(case.get("time", "0") or 0)
        skipped = case.find("skipped") is not None
        failed = case.find("failure") is not None or case.find("error") is not None
        # pytest writes classname as a dotted path. For a module-level test that
        # is the module itself ("tests.test_npv"); for a class-based test the
        # class is appended ("tests.test_npv.TestThing"). Dropping the last
        # component unconditionally would attribute every module-level test to a
        # phantom "tests.py" - which is most of this suite.
        parts = classname.split(".")
        if len(parts) > 1 and parts[-1][:1].isupper():
            parts = parts[:-1]  # trailing component is a class, not the module
        file_guess = "/".join(parts)
        if file_guess and not file_guess.endswith(".py"):
            file_guess = file_guess + ".py"
        cases.append(
            {
                "file": file_guess or "unknown",
                "classname": classname,
                "test": name,
                "nodeid": f"{file_guess}::{name}",
                "seconds": time,
                "skipped": skipped,
                "failed": failed,
            }
        )
    return cases


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def cumulative_threshold(sorted_seconds: list[float], total: float, share: float) -> int:
    """How many of the slowest tests it takes to reach `share` of total time."""
    if total <= 0:
        return 0
    running = 0.0
    for index, value in enumerate(sorted_seconds, start=1):
        running += value
        if running >= share * total:
            return index
    return len(sorted_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=pathlib.Path, required=True)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("artifacts/ci_optimisation"),
    )
    args = parser.parse_args(argv)

    if not args.junit.exists():
        print(f"No JUnit XML at {args.junit}", file=sys.stderr)
        return 1

    cases = parse_junit(args.junit)
    executed = [c for c in cases if not c["skipped"]]
    total = sum(c["seconds"] for c in executed)

    # --- slowest tests -------------------------------------------------------
    by_time = sorted(executed, key=lambda c: -c["seconds"])
    write_csv(
        args.output / "slowest_tests.csv",
        [
            {
                "rank": i,
                "seconds": round(c["seconds"], 3),
                "share_pct": round(100 * c["seconds"] / total, 3) if total else 0,
                "file": c["file"],
                "test": c["test"],
            }
            for i, c in enumerate(by_time[:300], start=1)
        ],
    )

    # --- by file -------------------------------------------------------------
    per_file: dict[str, list[float]] = collections.defaultdict(list)
    for case in executed:
        per_file[case["file"]].append(case["seconds"])
    file_rows = sorted(
        (
            {
                "file": name,
                "tests": len(times),
                "total_seconds": round(sum(times), 2),
                "share_pct": round(100 * sum(times) / total, 3) if total else 0,
                "mean_seconds": round(sum(times) / len(times), 3),
                "max_seconds": round(max(times), 3),
            }
            for name, times in per_file.items()
        ),
        key=lambda r: -r["total_seconds"],
    )
    write_csv(args.output / "duration_by_file.csv", file_rows)

    # --- by marker (inferred; markers are not in JUnit output) ---------------
    marker_rows = []
    for label, pattern in (
        ("apptest_like", APP_TEST_PATTERN),
        ("reference_pipeline_like", REFERENCE_PIPELINE_PATTERN),
    ):
        matched = [c for c in executed if pattern.search(c["nodeid"])]
        marker_rows.append(
            {
                "marker": label,
                "tests": len(matched),
                "total_seconds": round(sum(c["seconds"] for c in matched), 2),
                "share_pct": round(
                    100 * sum(c["seconds"] for c in matched) / total, 2
                ) if total else 0,
            }
        )
    marker_rows.append(
        {
            "marker": "skipped",
            "tests": len([c for c in cases if c["skipped"]]),
            "total_seconds": 0.0,
            "share_pct": 0.0,
        }
    )
    marker_rows.append(
        {
            "marker": "all_executed",
            "tests": len(executed),
            "total_seconds": round(total, 2),
            "share_pct": 100.0,
        }
    )
    write_csv(args.output / "duration_by_marker.csv", marker_rows)

    # --- structural inventories ---------------------------------------------
    write_csv(
        args.output / "app_test_inventory.csv",
        [
            {"file": c["file"], "test": c["test"], "seconds": round(c["seconds"], 3)}
            for c in sorted(
                (c for c in executed if APP_TEST_PATTERN.search(c["nodeid"])),
                key=lambda c: -c["seconds"],
            )
        ],
    )
    write_csv(
        args.output / "reference_pipeline_inventory.csv",
        [
            {"file": c["file"], "test": c["test"], "seconds": round(c["seconds"], 3)}
            for c in sorted(
                (c for c in executed if REFERENCE_PIPELINE_PATTERN.search(c["nodeid"])),
                key=lambda c: -c["seconds"],
            )
        ],
    )

    # --- concentration -------------------------------------------------------
    seconds_sorted = [c["seconds"] for c in by_time]
    concentration = {
        share: cumulative_threshold(seconds_sorted, total, share)
        for share in (0.5, 0.75, 0.9)
    }

    lines = [
        "# Test-suite profile",
        "",
        f"- executed tests: **{len(executed)}**  (skipped {len(cases) - len(executed)})",
        f"- failures/errors: **{sum(1 for c in executed if c['failed'])}**",
        f"- total measured test time: **{total / 60:.1f} min** ({total:.0f}s)",
        "",
        "## Concentration",
        "",
        "| share of runtime | slowest N tests | as % of all executed tests |",
        "| --- | --- | --- |",
    ]
    for share, count in concentration.items():
        lines.append(
            f"| {int(share * 100)}% | {count} | {100 * count / len(executed):.1f}% |"
            if executed
            else f"| {int(share * 100)}% | {count} | - |"
        )
    lines += [
        "",
        "## Slowest files",
        "",
        "| file | tests | total | share |",
        "| --- | --- | --- | --- |",
    ]
    for row in file_rows[:20]:
        lines.append(
            f"| `{row['file']}` | {row['tests']} | {row['total_seconds']:.0f}s "
            f"| {row['share_pct']:.1f}% |"
        )
    lines += ["", "## Slowest individual tests", "",
              "| seconds | file | test |", "| --- | --- | --- |"]
    for case in by_time[:30]:
        lines.append(f"| {case['seconds']:.1f} | `{case['file']}` | `{case['test']}` |")

    (args.output / "profile_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines[:40]))
    print(f"\nWrote CSV evidence and profile_summary.md to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

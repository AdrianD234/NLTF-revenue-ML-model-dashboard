"""Track what CI actually costs, so the optimisation can be checked rather than believed.

Two things are easy to get wrong when splitting a suite into conditional jobs:

  * wall-clock time improves while total billed minutes get worse, because more
    jobs each pay their own setup;
  * a lane silently stops running, and the suite looks faster because it is
    doing less.

This script records both, per run, so either is visible. It reads GitHub run
metadata via ``gh`` and appends to CSV histories rather than overwriting them.

Usage:
    python scripts/report_ci_performance.py --recent 20
    python scripts/report_ci_performance.py --run-id 30906665375
    python scripts/report_ci_performance.py --recent 20 --summary
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import subprocess
import sys
from datetime import datetime

REPO = "AdrianD234/NLTF-revenue-ML-model-dashboard"
DEFAULT_OUT = pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "ci_optimisation"

RUNNER_RATES_USD = {"UBUNTU": 0.008, "WINDOWS": 0.016, "MACOS": 0.08}
RUNNER_MULTIPLIERS = {"UBUNTU": 1, "WINDOWS": 2, "MACOS": 10}


def gh_json(args: list[str]) -> object:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def runner_class(labels: list[str], name: str) -> str:
    blob = " ".join(labels).lower() + " " + name.lower()
    if "windows" in blob:
        return "WINDOWS"
    if "macos" in blob:
        return "MACOS"
    return "UBUNTU"


def collect_run(run_id: str) -> dict:
    run = gh_json(["api", f"repos/{REPO}/actions/runs/{run_id}"])
    jobs = gh_json(["api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"])["jobs"]

    created = parse_ts(run["created_at"])
    updated = parse_ts(run["updated_at"])

    job_rows = []
    billed_weighted = 0.0
    cost = 0.0
    slowest_steps: list[tuple[float, str]] = []

    for job in jobs:
        started, completed = parse_ts(job.get("started_at")), parse_ts(job.get("completed_at"))
        if not started or not completed:
            # A job that never started (skipped, or refused for billing) costs
            # nothing but must still be recorded, or "lane stopped running" would
            # look identical to "lane was fast".
            job_rows.append({"name": job["name"], "conclusion": job["conclusion"],
                             "seconds": 0.0, "billed_minutes": 0, "runner": "none"})
            continue
        seconds = (completed - started).total_seconds()
        klass = runner_class(job.get("labels") or [], job["name"])
        billed = max(1, math.ceil(seconds / 60.0))
        billed_weighted += billed * RUNNER_MULTIPLIERS[klass]
        cost += billed * RUNNER_RATES_USD[klass]
        job_rows.append({"name": job["name"], "conclusion": job["conclusion"],
                         "seconds": round(seconds, 1), "billed_minutes": billed,
                         "runner": klass})
        for step in job.get("steps") or []:
            s_start, s_end = parse_ts(step.get("started_at")), parse_ts(step.get("completed_at"))
            if s_start and s_end:
                slowest_steps.append(((s_end - s_start).total_seconds(),
                                      f"{job['name']} / {step['name']}"))

    slowest_steps.sort(reverse=True)

    return {
        "run_id": str(run_id),
        "workflow": run["name"],
        "event": run["event"],
        "branch": run["head_branch"],
        "head_sha": run["head_sha"],
        "conclusion": run["conclusion"],
        "created_at": run["created_at"],
        "wall_seconds": round((updated - created).total_seconds(), 1),
        "billed_minutes_weighted": billed_weighted,
        "cost_usd": round(cost, 4),
        "jobs": job_rows,
        "jobs_requested": len(job_rows),
        "jobs_skipped": sum(1 for j in job_rows if j["conclusion"] == "skipped"),
        "jobs_that_never_started": sum(1 for j in job_rows if j["runner"] == "none"),
        "was_cancelled": run["conclusion"] == "cancelled",
        "slowest_steps": [{"seconds": round(s, 1), "step": n} for s, n in slowest_steps[:15]],
    }


def append_csv(path: pathlib.Path, rows: list[dict], key: str) -> None:
    """Append, skipping rows already recorded, so re-running is harmless."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            existing = {row[key] for row in csv.DictReader(handle) if key in row}
    fresh = [row for row in rows if str(row[key]) not in existing]
    if not fresh:
        return
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        if write_header:
            writer.writeheader()
        writer.writerows(fresh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", default=[],
                        help="specific run ID (repeatable)")
    parser.add_argument("--recent", type=int, default=0,
                        help="collect the N most recent CI runs")
    parser.add_argument("--workflow", default="ci.yml")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", action="store_true",
                        help="print an aggregate over what was collected")
    args = parser.parse_args(argv)

    run_ids = list(args.run_id)
    if args.recent:
        listed = gh_json([
            "run", "list", "--workflow", args.workflow,
            "--limit", str(args.recent), "--json", "databaseId",
        ])
        run_ids.extend(str(item["databaseId"]) for item in listed)
    if not run_ids:
        parser.error("pass --run-id or --recent")

    runs = [collect_run(run_id) for run_id in dict.fromkeys(run_ids)]

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest_run.json").write_text(
        json.dumps(runs[0], indent=2), encoding="utf-8"
    )

    append_csv(
        args.output / "hosted_minutes_history.csv",
        [
            {
                "run_id": r["run_id"], "created_at": r["created_at"], "event": r["event"],
                "branch": r["branch"], "conclusion": r["conclusion"],
                "wall_seconds": r["wall_seconds"],
                "billed_minutes_weighted": r["billed_minutes_weighted"],
                "jobs_requested": r["jobs_requested"], "jobs_skipped": r["jobs_skipped"],
                "jobs_that_never_started": r["jobs_that_never_started"],
            }
            for r in runs
        ],
        key="run_id",
    )
    append_csv(
        args.output / "cost_history.csv",
        [
            {"run_id": r["run_id"], "created_at": r["created_at"],
             "conclusion": r["conclusion"], "cost_usd": r["cost_usd"],
             "billed_minutes_weighted": r["billed_minutes_weighted"]}
            for r in runs
        ],
        key="run_id",
    )
    append_csv(
        args.output / "test_duration_history.csv",
        [
            {"run_id": r["run_id"], "created_at": r["created_at"],
             "step": s["step"], "seconds": s["seconds"]}
            for r in runs for s in r["slowest_steps"][:5]
        ],
        key="run_id",
    )
    append_csv(
        args.output / "scope_history.csv",
        [
            {"run_id": r["run_id"], "created_at": r["created_at"], "event": r["event"],
             "jobs_run": ";".join(
                 j["name"] for j in r["jobs"] if j["conclusion"] not in ("skipped",)),
             "jobs_skipped": ";".join(
                 j["name"] for j in r["jobs"] if j["conclusion"] == "skipped")}
            for r in runs
        ],
        key="run_id",
    )

    print(f"Recorded {len(runs)} run(s) to {args.output}")

    if args.summary:
        total_min = sum(r["billed_minutes_weighted"] for r in runs)
        total_usd = sum(r["cost_usd"] for r in runs)
        wasted = sum(
            r["billed_minutes_weighted"] for r in runs
            if r["conclusion"] in ("cancelled", "failure")
        )
        print()
        print(f"runs                    : {len(runs)}")
        print(f"weighted billed minutes : {total_min:,.0f}")
        print(f"estimated cost          : ${total_usd:,.2f}")
        if total_min:
            print(f"spent on cancelled/failed: {wasted:,.0f} min ({100*wasted/total_min:.1f}%)")
        print(f"mean wall time          : {sum(r['wall_seconds'] for r in runs)/len(runs)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())

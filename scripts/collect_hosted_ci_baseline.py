"""Collect the hosted GitHub Actions baseline this optimisation is measured against.

The billable-minute figures GitHub's own ``/timing`` endpoint returns are zero
for this repository, so billed minutes are reconstructed here from job start and
completion timestamps under GitHub's documented rules: each job is rounded up to
the next whole minute and multiplied by the runner's per-minute rate.

Nothing here rebuilds a pack or runs a test. It reads run metadata via ``gh`` and
writes the CSV evidence the optimisation is judged against.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

REPO = "AdrianD234/NLTF-revenue-ML-model-dashboard"

# Per-minute USD rates for GitHub-hosted standard runners on private
# repositories, and the multiplier GitHub applies against the included-minutes
# allowance. Ubuntu is the base rate; Windows costs twice as much.
RUNNER_RATES_USD = {
    "UBUNTU": 0.008,
    "WINDOWS": 0.016,
    "MACOS": 0.08,
}
RUNNER_MULTIPLIERS = {"UBUNTU": 1, "WINDOWS": 2, "MACOS": 10}


def gh_api(path: str) -> dict:
    # Deliberately unpaginated: a run has one metadata object, and the jobs
    # endpoint is asked for a full page. --paginate would concatenate several
    # top-level JSON objects, which is not parseable as one document.
    separator = "&" if "?" in path else "?"
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/{path}{separator}per_page=100"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def runner_class(labels: list[str], job_name: str) -> str:
    blob = " ".join(labels).lower() + " " + job_name.lower()
    if "windows" in blob:
        return "WINDOWS"
    if "macos" in blob or "mac-" in blob:
        return "MACOS"
    return "UBUNTU"


def collect(run_ids: list[str], out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    run_rows: list[dict] = []
    step_rows: list[dict] = []
    cost_rows: list[dict] = []

    for run_id in run_ids:
        run = gh_api(f"actions/runs/{run_id}")
        jobs = gh_api(f"actions/runs/{run_id}/jobs")["jobs"]

        run_created = parse_ts(run["created_at"])
        run_updated = parse_ts(run["updated_at"])
        run_wall_s = (run_updated - run_created).total_seconds()

        run_billed_minutes = 0.0
        run_cost_usd = 0.0

        for job in jobs:
            started = parse_ts(job.get("started_at"))
            completed = parse_ts(job.get("completed_at"))
            if started is None or completed is None:
                continue
            job_wall_s = (completed - started).total_seconds()
            klass = runner_class(job.get("labels") or [], job["name"])
            # GitHub rounds each job up to the whole minute before billing.
            billed_minutes = max(1, math.ceil(job_wall_s / 60.0))
            weighted = billed_minutes * RUNNER_MULTIPLIERS[klass]
            cost = billed_minutes * RUNNER_RATES_USD[klass]
            run_billed_minutes += weighted
            run_cost_usd += cost

            run_rows.append(
                {
                    "run_id": run_id,
                    "workflow": run["name"],
                    "event": run["event"],
                    "branch": run["head_branch"],
                    "head_sha": run["head_sha"][:12],
                    "run_conclusion": run["conclusion"],
                    "job_name": job["name"],
                    "job_conclusion": job["conclusion"],
                    "runner_class": klass,
                    "job_wall_seconds": round(job_wall_s, 1),
                    "job_wall_hms": hms(job_wall_s),
                    "billed_minutes_raw": billed_minutes,
                    "billed_minutes_weighted": weighted,
                    "job_cost_usd": round(cost, 4),
                }
            )

            for step in job.get("steps") or []:
                s_start = parse_ts(step.get("started_at"))
                s_end = parse_ts(step.get("completed_at"))
                if s_start is None or s_end is None:
                    continue
                dur = (s_end - s_start).total_seconds()
                step_rows.append(
                    {
                        "run_id": run_id,
                        "job_name": job["name"],
                        "step_number": step["number"],
                        "step_name": step["name"],
                        "conclusion": step["conclusion"],
                        "seconds": round(dur, 1),
                        "hms": hms(dur),
                        "share_of_job_pct": round(100 * dur / job_wall_s, 1)
                        if job_wall_s
                        else 0.0,
                    }
                )

        cost_rows.append(
            {
                "run_id": run_id,
                "workflow": run["name"],
                "event": run["event"],
                "branch": run["head_branch"],
                "head_sha": run["head_sha"][:12],
                "conclusion": run["conclusion"],
                "created_at": run["created_at"],
                "run_wall_seconds": round(run_wall_s, 1),
                "run_wall_hms": hms(run_wall_s),
                "billed_minutes_weighted": run_billed_minutes,
                "run_cost_usd": round(run_cost_usd, 4),
            }
        )

    write_csv(out_dir / "hosted_baseline.csv", run_rows)
    write_csv(out_dir / "hosted_step_timings.csv", step_rows)
    write_csv(out_dir / "baseline_cost_model.csv", cost_rows)
    print(f"wrote {len(run_rows)} job rows, {len(step_rows)} step rows to {out_dir}")


def hms(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 3600:d}h{(seconds % 3600) // 60:02d}m{seconds % 60:02d}s"


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", nargs="+", help="GitHub Actions run IDs")
    parser.add_argument(
        "--output",
        default="artifacts/ci_optimisation",
        help="directory for the CSV evidence",
    )
    args = parser.parse_args()
    collect(args.run_ids, pathlib.Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())

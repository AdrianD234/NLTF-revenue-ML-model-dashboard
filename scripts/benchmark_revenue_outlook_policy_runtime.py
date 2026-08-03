"""Policy-switch cost through the materialised runtime, against the targets.

Three numbers, measured separately because they answer different questions:

``resource load``
    Cold: opening the pack once per process. Paid once, not per switch.

``pure policy-state lookup``
    ``resolve_policy_state`` + the frames for that state. Target p95 <= 100 ms.

``policy switch API``
    The same, plus the selected-series/grain filtering a chart actually needs,
    plus the matching band rows. Target p95 <= 200 ms.

Samples are taken over the full switch cycle rather than one cache hit: the
FIRST touch of a state pays the parquet read and every later touch does not,
and a benchmark that only reported the warm number would be measuring the
memoisation rather than the design.

    python scripts/benchmark_revenue_outlook_policy_runtime.py --repeats 3
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVIDENCE_DIR = REPO_ROOT / "artifacts" / "revenue_outlook_policy_runtime"
ENGINES = ("ar1", "ensemble")
LOOKUP_TARGET_MS = 100.0
SWITCH_TARGET_MS = 200.0
BROWSER_TARGET_MS = 500.0

# The cycle a reader actually performs, including the return to a state they
# already visited.
SWITCH_CYCLE = ("published", "delayed_6m", "off", "published", "delayed_6m")


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _worker(engine: str) -> dict:
    import logging
    import os

    os.environ["REVENUE_OUTLOOK_CACHE_WARMER"] = "0"
    logging.getLogger("streamlit").setLevel(logging.ERROR)

    import app  # noqa: PLC0415
    from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: PLC0415
    from model_dashboard.official_vintage import (  # noqa: PLC0415
        bridge_vintage_id_from_manifest,
    )
    from model_dashboard.revenue_outlook import (  # noqa: PLC0415
        PED_BRIDGE_DEFAULT_MODE,
        revenue_outlook_signature,
    )
    from model_dashboard.revenue_outlook_policy_runtime import (  # noqa: PLC0415
        load_policy_runtime,
        policy_chart_rows,
        policy_detail_frames,
        policy_uncertainty_rows,
        resolve_policy_state,
    )
    from model_dashboard.revenue_scenario_key import (  # noqa: PLC0415
        RevenueScenarioComputationKey,
    )

    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(engine)
    signature = revenue_outlook_signature(pack_dir, REPO_ROOT)
    pack = app.cached_load_revenue_outlook_pack(
        str(pack_dir), str(REPO_ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}

    def key_for(policy: str):
        return RevenueScenarioComputationKey(
            engine=engine,
            uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
            current_fed_policy_state=policy,
            official_fed_policy_state=app.FED_POLICY_PUBLISHED,
            # The key the PAGE builds, not a convenient subset: benchmarking a
            # key the catalogue would refuse measures nothing a reader does.
            ped_bridge_mode=PED_BRIDGE_DEFAULT_MODE,
            bridge_vintage_id=str(bridge_vintage_id_from_manifest(pack.manifest, REPO_ROOT) or ""),
            official_comparator_vintage_id=str(
                block.get("default_comparator_vintage_id") or "BEFU26"
            ),
            long_run_transition_schedule_id=str(
                block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
            ),
            long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
        )

    started = time.perf_counter()
    runtime = load_policy_runtime(engine=engine, repo_root=REPO_ROOT)
    resource_load_ms = (time.perf_counter() - started) * 1000.0

    lookup_ms: list[float] = []
    switch_ms: list[float] = []
    first_selection_ms: list[float] = []
    repeat_selection_ms: list[float] = []
    seen: set[str] = set()

    for _round in range(6):
        for policy in SWITCH_CYCLE:
            key = key_for(policy)

            mark = time.perf_counter()
            resolution = resolve_policy_state(runtime, key)
            if not resolution.ok:
                # A refused key would otherwise be timed as a very fast
                # "lookup" and reported as meeting the target.
                raise SystemExit(
                    f"[{engine}] the benchmark key resolved to "
                    f"{resolution.status}: {resolution.detail}"
                )
            rows = runtime.frame(resolution.state_id, "chart_rows")
            elapsed = (time.perf_counter() - mark) * 1000.0
            lookup_ms.append(elapsed)

            mark = time.perf_counter()
            policy_chart_rows(
                runtime, key, series_id="total_nltf_net_revenue", time_grain="june_year"
            )
            policy_detail_frames(runtime, key)
            policy_uncertainty_rows(runtime, key, series_id="total_nltf_net_revenue")
            switch_elapsed = (time.perf_counter() - mark) * 1000.0
            switch_ms.append(switch_elapsed)

            total = elapsed + switch_elapsed
            if policy in seen:
                repeat_selection_ms.append(total)
            else:
                first_selection_ms.append(total)
                seen.add(policy)
            del rows

    manifest = runtime.manifest
    try:
        import tracemalloc

        tracemalloc.start()
        for policy in ("published", "delayed_6m", "off"):
            policy_chart_rows(runtime, key_for(policy))
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_kb = peak / 1024.0
    except Exception:
        peak_kb = float("nan")

    pack_bytes = sum(
        path.stat().st_size
        for path in (REPO_ROOT / "data" / "revenue_outlook_policy_runtime" / engine).rglob("*")
        if path.is_file()
    )
    return {
        "engine": engine,
        "resource_load_ms": resource_load_ms,
        "lookup_ms": lookup_ms,
        "switch_ms": switch_ms,
        "first_selection_ms": first_selection_ms,
        "repeat_selection_ms": repeat_selection_ms,
        "state_count": int(manifest.get("state_count", 0)),
        "row_count": int(manifest.get("row_count", 0)),
        "band_rows": int(manifest.get("uncertainty_band_rows", 0)),
        "pack_bytes": pack_bytes,
        "peak_kb": peak_kb,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=ENGINES)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    if args.worker:
        if not args.engine:
            parser.error("--worker requires --engine")
        print("@@RESULT@@" + json.dumps(_worker(args.engine)))
        return 0

    records: list[dict] = []
    for engine in ENGINES:
        for index in range(args.repeats):
            print(f"  {engine} run {index + 1}/{args.repeats} ...", flush=True)
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--engine", engine, "--worker"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            line = next(
                line for line in completed.stdout.splitlines() if line.startswith("@@RESULT@@")
            )
            records.append(json.loads(line[len("@@RESULT@@") :]))

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    rows = ["engine,metric,median_ms,p95_ms,max_ms,samples,target_ms,meets_target"]
    summary: list[str] = []
    for engine in ENGINES:
        matching = [record for record in records if record["engine"] == engine]
        if not matching:
            continue
        for metric, target in (
            ("lookup_ms", LOOKUP_TARGET_MS),
            ("switch_ms", SWITCH_TARGET_MS),
            ("first_selection_ms", BROWSER_TARGET_MS),
            ("repeat_selection_ms", BROWSER_TARGET_MS),
        ):
            values = [value for record in matching for value in record[metric]]
            p95 = _percentile(values, 0.95)
            rows.append(
                f"{engine},{metric},{statistics.median(values):.2f},{p95:.2f},"
                f"{max(values):.2f},{len(values)},{target:.0f},{str(p95 <= target).lower()}"
            )
        loads = [record["resource_load_ms"] for record in matching]
        rows.append(
            f"{engine},cold_resource_load_ms,{statistics.median(loads):.2f},"
            f"{_percentile(loads, 0.95):.2f},{max(loads):.2f},{len(loads)},,"
        )
        first = matching[0]
        summary.append(
            f"{engine}: {first['state_count']} states, {first['row_count']:,} rows, "
            f"{first['band_rows']:,} band rows, {first['pack_bytes'] / 1024:,.0f} KB on disk, "
            f"peak {first['peak_kb']:,.0f} KB resident for all three policy states"
        )
    (EVIDENCE_DIR / "policy_runtime_benchmark.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    (EVIDENCE_DIR / "policy_runtime_benchmark_raw.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    print("\n".join(rows))
    print("\n" + "\n".join(summary))
    print(f"\nwrote {(EVIDENCE_DIR / 'policy_runtime_benchmark.csv').as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

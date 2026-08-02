"""Fresh-process Revenue Outlook stage timings, reference vs fast.

Each measurement runs in its OWN interpreter, because the costs that matter
here - imports, the first pack read, the first replay - are paid once per
process and are invisible to an in-process warm loop.

    python scripts/benchmark_revenue_outlook_instant_runtime.py --repeats 3
    python scripts/benchmark_revenue_outlook_instant_runtime.py --mode fast --engine ar1

The second form is the worker the driver spawns; it prints one JSON record.
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

EVIDENCE_DIR = REPO_ROOT / "artifacts" / "revenue_outlook_instant_runtime"
ENGINES = ("ar1", "ensemble")
MODES = ("reference", "fast")


def _run_worker(mode: str, engine: str) -> dict:
    """One fresh interpreter, one cold Revenue Outlook computation path."""
    import logging
    import os

    os.environ["REVENUE_OUTLOOK_RUNTIME_MODE"] = mode
    os.environ["REVENUE_OUTLOOK_CACHE_WARMER"] = "0"
    logging.getLogger("streamlit").setLevel(logging.ERROR)

    stages: list[tuple[str, float]] = []

    started = time.perf_counter()
    import app  # noqa: PLC0415

    stages.append(("import app.py", (time.perf_counter() - started) * 1000))

    from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: PLC0415
    from model_dashboard.revenue_outlook import (  # noqa: PLC0415
        PED_BRIDGE_DEFAULT_MODE,
        revenue_outlook_signature,
    )
    from model_dashboard.revenue_scenario_key import (  # noqa: PLC0415
        RevenueScenarioComputationKey,
    )

    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(engine)

    def stage(label, function):
        mark = time.perf_counter()
        value = function()
        stages.append((label, (time.perf_counter() - mark) * 1000))
        return value

    signature = stage("pack signature", lambda: revenue_outlook_signature(pack_dir, REPO_ROOT))
    pack = stage(
        "pack load",
        lambda: app.cached_load_revenue_outlook_pack(
            str(pack_dir), str(REPO_ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
        ),
    )
    stage("selector metadata", lambda: app.cached_revenue_outlook_selectors(signature, pack))

    sensitivity = app.selected_sensitivity_key("Off", "Off", "Off")
    key = RevenueScenarioComputationKey()

    stage("fed uplift factors", lambda: app.cached_fed_uplift_factors(signature, pack))
    stage(
        "treasury macro replay",
        lambda: app.cached_treasury_baseline_macro_replay(signature, pack),
    )
    stage(
        "conflict/fuel replay",
        lambda: app.cached_fuel_price_scenario_replay(signature, pack),
    )
    stage(
        "sensitivity stage frames",
        lambda: app.cached_sensitivity_stage_frames(
            signature, PED_BRIDGE_DEFAULT_MODE, sensitivity, pack
        ),
    )
    stage(
        "scenario overlay rows",
        lambda: app.cached_scenario_overlay_rows(
            signature, sensitivity, PED_BRIDGE_DEFAULT_MODE, key, pack
        ),
    )
    stage(
        "revenue outlook view (cold)",
        lambda: app.cached_revenue_outlook_view(
            signature,
            "Total NLTF revenue",
            "June-year",
            "Current planned path",
            ("Current Base",),
            sensitivity,
            PED_BRIDGE_DEFAULT_MODE,
            key,
            pack,
        ),
    )

    # Warm re-entry: what a cached rerun of the same view costs.
    warm: list[float] = []
    for _ in range(20):
        mark = time.perf_counter()
        app.cached_revenue_outlook_view(
            signature,
            "Total NLTF revenue",
            "June-year",
            "Current planned path",
            ("Current Base",),
            sensitivity,
            PED_BRIDGE_DEFAULT_MODE,
            key,
            pack,
        )
        warm.append((time.perf_counter() - mark) * 1000)

    return {
        "mode": mode,
        "engine": engine,
        "stages": stages,
        "cold_total_ms": sum(value for _, value in stages),
        "warm_view_median_ms": statistics.median(warm),
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--engine", choices=ENGINES)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--modes", nargs="*", default=list(MODES))
    args = parser.parse_args()

    if args.mode and args.engine:
        print("@@RESULT@@" + json.dumps(_run_worker(args.mode, args.engine)))
        return 0

    records: list[dict] = []
    for mode in args.modes:
        # The reference path costs ~70 s per run; one sample per engine is
        # enough to size the baseline, and it is stated as such.
        repeats = 1 if mode == "reference" else args.repeats
        for engine in ENGINES:
            for index in range(repeats):
                print(f"  {mode}/{engine} run {index + 1}/{repeats} ...", flush=True)
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--mode",
                        mode,
                        "--engine",
                        engine,
                    ],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                line = next(
                    line
                    for line in completed.stdout.splitlines()
                    if line.startswith("@@RESULT@@")
                )
                records.append(json.loads(line[len("@@RESULT@@") :]))

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    stage_rows = ["mode,engine,stage,median_ms,min_ms,max_ms,samples"]
    stage_names = [name for name, _ in records[0]["stages"]]
    for mode in {record["mode"] for record in records}:
        for engine in ENGINES:
            matching = [
                record
                for record in records
                if record["mode"] == mode and record["engine"] == engine
            ]
            if not matching:
                continue
            for name in stage_names:
                values = [
                    dict(record["stages"])[name] for record in matching if name in dict(record["stages"])
                ]
                stage_rows.append(
                    f'{mode},{engine},"{name}",{statistics.median(values):.1f},'
                    f"{min(values):.1f},{max(values):.1f},{len(values)}"
                )
    (EVIDENCE_DIR / "stage_timings.csv").write_text("\n".join(stage_rows) + "\n", encoding="utf-8")

    summary_rows = [
        "engine,metric,reference_ms,fast_ms,improvement_ratio,samples_reference,samples_fast"
    ]
    for engine in ENGINES:
        reference = [r for r in records if r["mode"] == "reference" and r["engine"] == engine]
        fast = [r for r in records if r["mode"] == "fast" and r["engine"] == engine]
        if not reference or not fast:
            continue
        for metric in ("cold_total_ms", "warm_view_median_ms"):
            ref_value = statistics.median([r[metric] for r in reference])
            fast_value = statistics.median([r[metric] for r in fast])
            ratio = (ref_value / fast_value) if fast_value else float("inf")
            summary_rows.append(
                f"{engine},{metric},{ref_value:.1f},{fast_value:.1f},{ratio:.1f},"
                f"{len(reference)},{len(fast)}"
            )
        fast_totals = [r["cold_total_ms"] for r in fast]
        summary_rows.append(
            f"{engine},cold_total_ms_p95_fast,,{_percentile(fast_totals, 0.95):.1f},,,{len(fast_totals)}"
        )
    (EVIDENCE_DIR / "performance_before_after.csv").write_text(
        "\n".join(summary_rows) + "\n", encoding="utf-8"
    )

    print("\n" + "\n".join(summary_rows))
    print(f"\nwrote {EVIDENCE_DIR.relative_to(REPO_ROOT).as_posix()}/stage_timings.csv")
    print(f"wrote {EVIDENCE_DIR.relative_to(REPO_ROOT).as_posix()}/performance_before_after.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

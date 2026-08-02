"""Compile the Treasury-macro and conflict/fuel replay results for an engine.

Both replays are pure functions of the promoted pack and the governed model
state - they take no reader-facing control - yet they cost ~52 s on the first
Revenue Outlook render of every process because they load joblib fitted state
and re-run forward forecasting.  This script runs them once, offline, and
commits the exact frames the runtime reconstructs.

    python scripts/build_revenue_outlook_replay_cache.py --engine ar1
    python scripts/build_revenue_outlook_replay_cache.py --all

The build refuses to publish unless every frame round-trips exactly, so a
serialisation that would move a value fails here rather than in the dashboard.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from model_dashboard.engine import ENGINE_AR1, ENGINE_ENSEMBLE, engine_revenue_outlook_dir  # noqa: E402
from model_dashboard.fuel_price_scenario import (  # noqa: E402
    run_direct_treasury_scenario_replay,
    run_fuel_price_scenario_replay,
)
from model_dashboard.official_vintage import bridge_vintage_id_from_manifest  # noqa: E402
from model_dashboard.revenue_outlook import load_revenue_outlook_pack  # noqa: E402
from model_dashboard.revenue_outlook_replay_cache import (  # noqa: E402
    build_replay_cache,
    load_replay_cache,
    replay_cache_dir,
)


def _walk_frames(obj: object, prefix: str = "") -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        name = f"{prefix}{field.name}"
        if isinstance(value, pd.DataFrame):
            frames[name] = value
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            frames.update(_walk_frames(value, prefix=f"{name}."))
    return frames


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _verify_round_trip(engine: str, manifest: dict, expected: dict[str, pd.DataFrame]) -> list[str]:
    """Reload the committed cache and compare every frame exactly."""
    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(engine)
    pack = load_revenue_outlook_pack(pack_dir, REPO_ROOT)
    macro, fuel = load_replay_cache(
        engine=engine,
        pack_manifest=pack.manifest,
        bridge_vintage_id=manifest["bridge_vintage_id"] or None,
        repo_root=REPO_ROOT,
    )
    reloaded = {
        **{f"macro.{k}": v for k, v in _walk_frames(macro).items()},
        **{f"fuel.{k}": v for k, v in _walk_frames(fuel).items()},
    }
    problems: list[str] = []
    if set(reloaded) != set(expected):
        problems.append(
            f"frame set differs: missing={sorted(set(expected) - set(reloaded))} "
            f"extra={sorted(set(reloaded) - set(expected))}"
        )
    for name in sorted(set(expected) & set(reloaded)):
        try:
            pd.testing.assert_frame_equal(expected[name], reloaded[name], check_exact=True)
        except AssertionError as error:
            problems.append(f"{name}: {str(error).splitlines()[0]}")
    return problems


def build_engine(engine: str, *, source_sha: str) -> dict:
    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(engine)
    print(f"[{engine}] pack: {pack_dir.relative_to(REPO_ROOT).as_posix()}", flush=True)
    pack = load_revenue_outlook_pack(pack_dir, REPO_ROOT)
    if pack is None:
        raise SystemExit(f"No promoted Revenue Outlook pack for engine {engine!r} at {pack_dir}")

    input_path = pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    if not input_path.exists():
        raise SystemExit(f"Missing scenario inputs for engine {engine!r}: {input_path}")
    scenario_inputs = pd.read_parquet(input_path)
    bridge_vintage_id = bridge_vintage_id_from_manifest(pack.manifest, REPO_ROOT)

    started = time.perf_counter()
    macro = run_direct_treasury_scenario_replay(
        scenario_inputs, repo_root=REPO_ROOT, engine=engine, bridge_vintage_id=bridge_vintage_id
    )
    macro_seconds = time.perf_counter() - started
    print(f"[{engine}] direct Treasury macro replay: {macro_seconds:,.1f} s", flush=True)

    started = time.perf_counter()
    fuel = run_fuel_price_scenario_replay(
        scenario_inputs, repo_root=REPO_ROOT, engine=engine, bridge_vintage_id=bridge_vintage_id
    )
    fuel_seconds = time.perf_counter() - started
    print(f"[{engine}] conflict/fuel price replay:   {fuel_seconds:,.1f} s", flush=True)

    manifest = build_replay_cache(
        macro,
        fuel,
        engine=engine,
        pack_manifest=pack.manifest,
        bridge_vintage_id=bridge_vintage_id,
        repo_root=REPO_ROOT,
        source_main_sha=source_sha,
    )
    # Deliberately NOT in the manifest: wall-clock timings would make two
    # rebuilds from identical sources produce different bytes, which is the
    # property the invalidation gate depends on. They are reported here and
    # recorded in the performance evidence instead.
    reference_seconds = {
        "direct_treasury_macro_replay": round(macro_seconds, 3),
        "fuel_price_scenario_replay": round(fuel_seconds, 3),
    }

    expected = {
        **{f"macro.{k}": v for k, v in _walk_frames(macro).items()},
        **{f"fuel.{k}": v for k, v in _walk_frames(fuel).items()},
    }
    problems = _verify_round_trip(engine, manifest, expected)
    if problems:
        print(f"[{engine}] ROUND-TRIP FAILED - refusing to publish:", flush=True)
        for problem in problems:
            print(f"    {problem}", flush=True)
        raise SystemExit(1)

    target = replay_cache_dir(engine, REPO_ROOT)
    print(
        f"[{engine}] reference replay cost avoided per process: "
        f"{sum(reference_seconds.values()):,.1f} s",
        flush=True,
    )
    print(
        f"[{engine}] wrote {manifest['frame_count']} frames, {manifest['row_count']:,} rows, "
        f"{manifest['bytes_on_disk'] / 1024:,.0f} KB -> {target.relative_to(REPO_ROOT).as_posix()}",
        flush=True,
    )
    print(f"[{engine}] round-trip verified exactly on all {len(expected)} frames", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=[ENGINE_AR1, ENGINE_ENSEMBLE])
    parser.add_argument("--all", action="store_true", help="build every engine")
    args = parser.parse_args()
    if not args.engine and not args.all:
        parser.error("pass --engine or --all")

    engines = [ENGINE_AR1, ENGINE_ENSEMBLE] if args.all else [args.engine]
    source_sha = _git_head()
    for engine in engines:
        build_engine(engine, source_sha=source_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

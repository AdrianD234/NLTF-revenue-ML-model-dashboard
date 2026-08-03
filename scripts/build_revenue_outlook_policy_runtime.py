"""Materialise the named 12c policy states so switching one is a lookup.

Profiling (``scripts/profile_revenue_outlook_policy_toggle.py``) measured the
first selection of each policy state at ~13.5 s per process, of which the
policy arithmetic is 0.33 s; the rest is every stage downstream of the
computation key being invalidated with it.  Both policy controls are
drop-downs over three states, so this script runs the reference pipeline once
per named state, offline, and commits exactly what the runtime reads back.

    python scripts/build_revenue_outlook_policy_runtime.py --all
    python scripts/build_revenue_outlook_policy_runtime.py --engine ar1

Nine states per engine (three Current x three official comparator), NOT a
Cartesian cube: every other value-changing control is pinned at the governed
default the promoted pack recorded, and the runtime refuses any key that
differs rather than serving the nearest cached state.

The build refuses to publish unless every frame round-trips exactly and every
materialised state equals the reference pipeline it came from.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import app  # noqa: E402
from model_dashboard.engine import ENGINE_AR1, ENGINE_ENSEMBLE, engine_revenue_outlook_dir  # noqa: E402
from model_dashboard.official_vintage import (  # noqa: E402
    bridge_vintage_id_from_manifest,
    default_comparator_vintage_id,
)
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    revenue_outlook_signature,
)
from model_dashboard.revenue_outlook_policy_runtime import (  # noqa: E402
    BUILDER_VERSION,
    FRAME_NAMES,
    POLICY_RUNTIME_SCHEMA_VERSION,
    POLICY_STATES,
    VFM_FAST_BASIS,
    VFM_SLOW_BASIS,
    _PINNED_FIELDS,
    load_policy_runtime,
    policy_calculation_code_modules,
    policy_runtime_dir,
    policy_runtime_source_digest,
    policy_runtime_source_files,
    state_id_for,
    upstream_manifests,
)
from model_dashboard.revenue_outlook_replay_cache import (  # noqa: E402
    _decode_frame,
    _encode_frame,
    _sha256_file,
    build_environment,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402
from model_dashboard.revenue_uncertainty import (  # noqa: E402
    FINAL_FY,
    LAST_ACTUAL_FY,
    QuantileMultipliers,
    june_year_quantiles,
)
from model_dashboard.revenue_uncertainty_draws import (  # noqa: E402
    DRAW_COUNT,
    generate_parent_factor_draws,
)
from model_dashboard.revenue_uncertainty_policy import (  # noqa: E402
    band_dependency_rows,
    band_rows_for_policy_state,
    mvr_proxy_factor,
)

LONG_HORIZON = REPO_ROOT / "artifacts" / "long_horizon_validation"
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "revenue_outlook_policy_runtime"
ENGINES = (ENGINE_AR1, ENGINE_ENSEMBLE)

# Which activity leaf each revenue leaf is priced on. Used only by the band
# dependency audit, to tell "the rate moved" apart from "the volume moved".
ACTIVITY_OF = {
    "gross_ped_revenue": "ped_volume",
    "light_ruc_net_revenue": "light_ruc_net_km",
    "light_bev_ruc_net_revenue": "light_bev_ruc_net_km",
    "phev_ruc_net_revenue": "phev_ruc_net_km",
    "heavy_ruc_net_revenue": "heavy_ruc_net_km",
    "heavy_bev_ruc_net_revenue": "heavy_bev_ruc_net_km",
}
RATE_PRICED = frozenset(ACTIVITY_OF)
# Activity leaves are their own driver: a change in one of these is a modelled
# demand response, not movement inherited through an identity.
ACTIVITY_LEAVES = frozenset(
    {
        "ped_vkt_per_capita",
        "ped_volume",
        "light_petrol_vkt",
        "current_light_ruc_conventional_modelled_km",
        *ACTIVITY_OF.values(),
    }
)

DEFAULT_SENSITIVITY = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")


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


def governed_key(pack, engine: str, current_state: str, official_state: str):
    """The production key for one named policy state.

    Every non-policy field comes from the promoted pack's own manifest, so the
    materialised catalogue is pinned to what the committed pack actually
    records rather than to a constant that could drift away from it.
    """
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
    return RevenueScenarioComputationKey(
        engine=engine,
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=current_state,
        official_fed_policy_state=official_state,
        # Both identity-only: no reader indexes them, the bridge mode reaches
        # the pipeline as its own argument and the bridge vintage comes from
        # the pack manifest. They are set anyway because the PAGE sets them,
        # and a catalogue pinned at "" would refuse every key the page builds
        # - a fast path nothing can ever hit.
        ped_bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        bridge_vintage_id=str(bridge_vintage_id_from_manifest(pack.manifest, REPO_ROOT) or ""),
        # The pack's own recorded comparator, under the key the manifest
        # actually uses. Falling through to the registry default would let the
        # catalogue drift away from the pack it was built from.
        official_comparator_vintage_id=str(
            block.get("official_comparator_vintage_id")
            or default_comparator_vintage_id(REPO_ROOT)
        ),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )


def reference_state_frames(pack, signature, key) -> dict[str, pd.DataFrame]:
    """Run the reference pipeline for one key and collect every frame."""
    chart_rows, _uptake, _eruc, policy_audit, scenario_audit = app.cached_scenario_overlay_rows(
        signature, DEFAULT_SENSITIVITY, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    line, residuals, stack, bridge = app.cached_aligned_scenario_detail_frames(
        signature, DEFAULT_SENSITIVITY, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    # Exactly what `cached_view_cone_band` runs: the same overlay chain with
    # ONLY the composition basis swapped, every other control - including this
    # policy state - carried through verbatim.
    vfm: dict[str, pd.DataFrame] = {}
    for name, basis in (
        ("vfm_fast_chart_rows", VFM_FAST_BASIS),
        ("vfm_slow_chart_rows", VFM_SLOW_BASIS),
    ):
        preset_rows, _u, _e, _p, _s = app.cached_scenario_overlay_rows(
            signature,
            DEFAULT_SENSITIVITY,
            PED_BRIDGE_DEFAULT_MODE,
            key.replace(uptake_basis=basis),
            pack,
        )
        vfm[name] = preset_rows
    return {
        "chart_rows": chart_rows,
        "line_reconciliation": line,
        "formula_residuals": residuals,
        "stack_components": stack,
        "bridge_components": bridge,
        "policy_audit": policy_audit if isinstance(policy_audit, pd.DataFrame) else pd.DataFrame(),
        "scenario_audit": (
            scenario_audit if isinstance(scenario_audit, pd.DataFrame) else pd.DataFrame()
        ),
        **vfm,
    }


def central_leaf_values(line: pd.DataFrame) -> dict[tuple[str, int], float]:
    """Governed central values per (series, FY) for the Current base case.

    Exactly the extraction the committed offline uncertainty pack uses, so a
    policy state whose central path is unchanged reproduces that pack's rows
    rather than merely resembling them.
    """
    selected = line[line["scenario_name"].astype(str).eq("current_basecase")].copy()
    selected["FY"] = pd.to_numeric(selected["FY"], errors="coerce")
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "value"])
    out: dict[tuple[str, int], float] = {}
    for _index, row in selected.iterrows():
        out.setdefault((str(row["series_id"]), int(row["FY"])), float(row["value"]))
    return out


def mvr_multipliers(pack) -> QuantileMultipliers:
    """The committed BEFU26-vs-MBU26 revision range. Never called empirical."""
    frame = pack.revenue_line_reconciliation.copy()
    frame["FY"] = pd.to_numeric(frame["FY"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    selected = frame[
        frame["series_id"].astype(str).eq("net_mvr_revenue")
        & frame["FY"].between(LAST_ACTUAL_FY + 1, FINAL_FY)
    ]
    pivot = selected.pivot_table(index="FY", columns="source_path", values="value", aggfunc="first")
    half = 0.02
    if "BEFU26 official" in pivot and "MBU26 official" in pivot:
        revision = np.log(pivot["MBU26 official"] / pivot["BEFU26 official"]).dropna()
        if len(revision):
            half = float(revision.abs().max())
    return QuantileMultipliers(q10=-half, q25=-half / 2.0, median=0.0, q75=half / 2.0, q90=half)


def build_engine(engine: str, *, source_sha: str) -> dict:
    pack_dir = REPO_ROOT / engine_revenue_outlook_dir(engine)
    print(f"[{engine}] pack: {pack_dir.relative_to(REPO_ROOT).as_posix()}", flush=True)
    signature = revenue_outlook_signature(pack_dir, REPO_ROOT)
    pack = app.cached_load_revenue_outlook_pack(
        str(pack_dir), str(REPO_ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    if pack is None:
        raise SystemExit(f"No promoted Revenue Outlook pack for engine {engine!r} at {pack_dir}")

    target = policy_runtime_dir(engine, REPO_ROOT)
    frames_root = target / "frames"
    if frames_root.exists():
        for stale in sorted(frames_root.rglob("*.parquet")):
            stale.unlink()
    frames_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ the states
    states: list[dict] = []
    reference_seconds = 0.0
    central_by_policy: dict[str, dict[tuple[str, int], float]] = {}
    for current_state in POLICY_STATES:
        for official_state in POLICY_STATES:
            key = governed_key(pack, engine, current_state, official_state)
            state_id = state_id_for(engine, current_state, official_state)
            started = time.perf_counter()
            frames = reference_state_frames(pack, signature, key)
            elapsed = time.perf_counter() - started
            reference_seconds += elapsed

            # The uncertainty centre is a property of the CURRENT policy only:
            # the official comparator is a separate published vintage and the
            # band is around Current Base, never around a comparator trace.
            if official_state == "published":
                central_by_policy[current_state] = central_leaf_values(
                    frames["line_reconciliation"]
                )

            state_dir = frames_root / state_id
            state_dir.mkdir(parents=True, exist_ok=True)
            frame_meta: dict[str, dict] = {}
            rows_written = 0
            problems: list[str] = []
            for name in FRAME_NAMES:
                encoded, meta = _encode_frame(frames[name])
                path = state_dir / f"{name}.parquet"
                encoded.to_parquet(path, index=False, compression="zstd")
                meta["file"] = f"{name}.parquet"
                meta["sha256"] = _sha256_file(path)
                frame_meta[name] = meta
                rows_written += int(len(frames[name]))
                # Verified HERE, against the reference frame still in hand,
                # rather than by re-running the pipeline at the end. Three
                # overlay keys per state (base + the two VFM presets) exceed
                # the 12-entry Streamlit cache, so a second pass would evict
                # and recompute everything it was meant to check cheaply.
                try:
                    pd.testing.assert_frame_equal(
                        frames[name], _decode_frame(pd.read_parquet(path), meta), check_exact=True
                    )
                except AssertionError as error:
                    problems.append(f"{state_id}/{name}: {str(error).splitlines()[0]}")
            if problems:
                print(f"[{engine}] ROUND-TRIP FAILED - refusing to publish:", flush=True)
                for problem in problems:
                    print(f"    {problem}", flush=True)
                raise SystemExit(1)
            del frames
            states.append(
                {
                    "state_id": state_id,
                    "engine": engine,
                    "current_fed_policy_state": current_state,
                    "official_fed_policy_state": official_state,
                    "scenario_key_digest": key.digest(),
                    "scenario_key": key.canonical_mapping(),
                    "frames": frame_meta,
                    "row_count": rows_written,
                    # Deliberately NOT recorded: a wall-clock timing would make
                    # two rebuilds from identical sources produce different
                    # bytes, and byte-idempotence is the property the
                    # invalidation gate depends on. Reported on stdout and in
                    # the performance evidence instead.
                }
            )
            print(
                f"[{engine}] {state_id}: {rows_written:,} rows "
                f"(reference {elapsed:,.1f} s)",
                flush=True,
            )

    # --------------------------------------------------- policy-aware bands
    june_errors = pd.read_csv(LONG_HORIZON / "long_horizon_june_year_errors.csv")
    quantiles = june_year_quantiles(june_errors)
    parent_draws, draw_provenance = generate_parent_factor_draws(june_errors, quantiles)
    mvr_factor = mvr_proxy_factor(mvr_multipliers(pack))

    band_rows: list[dict] = []
    residual_rows: list[dict] = []
    for current_state, central in central_by_policy.items():
        key = governed_key(pack, engine, current_state, "published")
        bands, residuals = band_rows_for_policy_state(
            central=central,
            parent_draws=parent_draws,
            mvr_factor=mvr_factor,
            first_fy=LAST_ACTUAL_FY + 1,
            final_fy=FINAL_FY,
            engine=engine,
            policy_state=current_state,
            scenario_key_digest=key.cache_token(),
            extra_keys={
                "bridge_vintage_id": str(
                    (pack.manifest.get("official_vintages", {}) or {}).get("bridge_vintage_id", "")
                ),
                "long_run_transition_schedule_id": key.long_run_transition_schedule_id,
                "long_run_shape_vintage_id": key.long_run_shape_vintage_id,
            },
            draws=DRAW_COUNT,
        )
        band_rows.extend(bands)
        residual_rows.extend(residuals)

    bands = pd.DataFrame(band_rows)
    residuals = pd.DataFrame(residual_rows)
    if bands.empty or residuals.empty:
        # An empty band set means the central extraction found nothing, which
        # would publish a policy pack with no uncertainty at all. Fail here.
        raise SystemExit(
            f"[{engine}] no policy-aware band rows were produced; refusing to publish."
        )
    failures = residuals[~residuals["closes"]]
    if not failures.empty:
        print(f"[{engine}] DRAW-LEVEL IDENTITY FAILURES - refusing to publish:", flush=True)
        print(failures.nlargest(5, "max_abs_residual").to_string(index=False), flush=True)
        raise SystemExit(1)

    nested = bands[(bands["lower50"] < bands["lower80"]) | (bands["upper50"] > bands["upper80"])]
    if not nested.empty:
        print(f"[{engine}] 50% band escapes the 80% band on {len(nested)} rows.", flush=True)
        raise SystemExit(1)

    bands_path = target / "uncertainty_band_rows.parquet"
    bands.to_parquet(bands_path, index=False, compression="zstd")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    dependency = band_dependency_rows(
        central_by_policy,
        engine=engine,
        reference_state="published",
        activity_of=ACTIVITY_OF,
        rate_priced=RATE_PRICED,
        activity_leaves=ACTIVITY_LEAVES,
    )
    dependency.to_csv(
        EVIDENCE_DIR / f"policy_band_dependency_audit_{engine}.csv", index=False
    )
    residuals.to_csv(
        EVIDENCE_DIR / f"policy_draw_level_formula_residuals_{engine}.csv", index=False
    )

    # ------------------------------------------------------------- manifest
    pack_manifest, replay_manifest, uncertainty_manifest = upstream_manifests(engine, REPO_ROOT)
    if not replay_manifest:
        raise SystemExit(
            f"No compiled replay cache manifest for engine {engine!r}. Build it first with: "
            f"python scripts/build_revenue_outlook_replay_cache.py --engine {engine}"
        )
    code_module_hashes = policy_calculation_code_modules(REPO_ROOT)
    source_file_hashes = policy_runtime_source_files(REPO_ROOT)
    digest, provenance = policy_runtime_source_digest(
        engine=engine,
        pack_manifest=pack_manifest,
        replay_manifest=replay_manifest,
        uncertainty_manifest=uncertainty_manifest,
        repo_root=REPO_ROOT,
        code_module_hashes=code_module_hashes,
        source_file_hashes=source_file_hashes,
    )

    pinned_key = governed_key(pack, engine, "published", "published")
    pinned_key_vintage = pinned_key.official_comparator_vintage_id
    manifest = {
        "schema_version": POLICY_RUNTIME_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        # Recorded, deliberately NOT hashed: a different interpreter must not
        # force a rebuild, but a parity gate needs to know whether it is
        # comparing on the machine that produced these floats.
        "build_environment": build_environment(),
        "engine": engine,
        "source_digest": digest,
        "source_main_sha": source_sha,
        "pinned_key_fields": {
            field: pinned_key.canonical_mapping()[field] for field in _PINNED_FIELDS
        },
        # The chart rows carry every vintage and are filtered on read. The
        # ALIGNED detail frames are not: they were built against this vintage,
        # so the runtime has to refuse any other rather than filter one that
        # is already filtered.
        "detail_frame_vintage_scope": {
            "vintage_id": pinned_key_vintage,
            "overlay": False,
        },
        "states": states,
        "state_count": len(states),
        "row_count": sum(int(state["row_count"]) for state in states),
        "bytes_on_disk": sum(
            (frames_root / state["state_id"] / str(meta["file"])).stat().st_size
            for state in states
            for meta in state["frames"].values()
        ),
        "uncertainty_sha256": _sha256_file(bands_path),
        "uncertainty_band_rows": int(len(bands)),
        "uncertainty_series": int(bands["series_id"].nunique()),
        "uncertainty_provenance": draw_provenance,
        "provenance": provenance,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )

    # The frames were already compared to the reference as each was written.
    # This second pass re-reads them THROUGH the runtime, so the manifest, the
    # hash validation and the decode path are exercised as a reader would.
    problems = verify_through_runtime(engine, states)
    if problems:
        print(f"[{engine}] RUNTIME LOAD FAILED - refusing to publish:", flush=True)
        for problem in problems:
            print(f"    {problem}", flush=True)
        raise SystemExit(1)

    print(
        f"[{engine}] {manifest['state_count']} states, {manifest['row_count']:,} rows, "
        f"{manifest['bytes_on_disk'] / 1024:,.0f} KB + "
        f"{bands_path.stat().st_size / 1024:,.0f} KB bands "
        f"-> {target.relative_to(REPO_ROOT).as_posix()}",
        flush=True,
    )
    print(
        f"[{engine}] reference cost avoided per process: {reference_seconds:,.1f} s "
        f"across {len(states)} states",
        flush=True,
    )
    print(f"[{engine}] round-trip verified exactly on all {len(states) * len(FRAME_NAMES)} frames")
    return manifest


def verify_through_runtime(engine: str, states: list[dict]) -> list[str]:
    """Load the committed pack the way the runtime will, and read every frame.

    Deliberately not a second reference run: the values were already compared
    to the reference frame in hand as each was written. What this proves is
    that the manifest, the hash gate and the decode path work end to end, so a
    pack that verifies here cannot fail on first read in the dashboard.
    """
    problems: list[str] = []
    try:
        runtime = load_policy_runtime(engine=engine, repo_root=REPO_ROOT)
    except Exception as error:  # noqa: BLE001 - report, do not publish
        return [f"load_policy_runtime failed: {type(error).__name__}: {error}"]
    for state in states:
        state_id = str(state["state_id"])
        for name in FRAME_NAMES:
            try:
                frame = runtime.frame(state_id, name)
            except Exception as error:  # noqa: BLE001
                problems.append(f"{state_id}/{name}: {type(error).__name__}: {error}")
                continue
            if frame is None:
                problems.append(f"{state_id}/{name}: decoded to None")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=list(ENGINES))
    parser.add_argument("--all", action="store_true", help="build every engine")
    args = parser.parse_args()
    if not args.engine and not args.all:
        parser.error("pass --engine or --all")

    engines = list(ENGINES) if args.all else [args.engine]
    source_sha = _git_head()
    for engine in engines:
        build_engine(engine, source_sha=source_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

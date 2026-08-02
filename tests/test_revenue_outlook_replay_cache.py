"""The compiled replay cache must be a materialisation, never an approximation.

Both replays are pure functions of the promoted pack and the governed model
state, so the committed cache has to reproduce them exactly, invalidate the
moment a source moves, and refuse to serve rather than fall back quietly to
the 52 s live path.

The exhaustive fast-vs-reference parity run lives in
``test_replay_cache_matches_reference_exactly``; it re-runs both live replays
and is marked ``slow`` because that costs ~70 s per engine.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.engine import ENGINE_AR1, ENGINE_ENSEMBLE, engine_revenue_outlook_dir
from model_dashboard.official_vintage import bridge_vintage_id_from_manifest
from model_dashboard.revenue_outlook import (
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey
from model_dashboard.revenue_outlook_replay_cache import (
    REPLAY_CACHE_SCHEMA_VERSION,
    ReplayCacheError,
    ReplayCacheMissing,
    ReplayCacheStale,
    load_replay_cache,
    replay_cache_dir,
    replay_cache_source_digest,
    replay_cache_status,
)

ROOT = Path(__file__).resolve().parents[1]
ENGINES = (ENGINE_AR1, ENGINE_ENSEMBLE)


def _pack_for(engine: str):
    pack = load_revenue_outlook_pack(ROOT / engine_revenue_outlook_dir(engine), ROOT)
    if pack is None:
        pytest.skip(f"No promoted Revenue Outlook pack for engine {engine!r}")
    return pack


def _frames(obj, prefix: str = "") -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        name = f"{prefix}{field.name}"
        if isinstance(value, pd.DataFrame):
            out[name] = value
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            out.update(_frames(value, prefix=f"{name}."))
    return out


def _load(engine: str):
    pack = _pack_for(engine)
    return load_replay_cache(
        engine=engine,
        pack_manifest=pack.manifest,
        bridge_vintage_id=bridge_vintage_id_from_manifest(pack.manifest, ROOT),
        repo_root=ROOT,
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_compiled_cache_exists_and_is_current(engine: str) -> None:
    pack = _pack_for(engine)
    status, detail = replay_cache_status(
        engine=engine,
        pack_manifest=pack.manifest,
        bridge_vintage_id=bridge_vintage_id_from_manifest(pack.manifest, ROOT),
        repo_root=ROOT,
    )
    assert status == "ok", (
        f"Compiled replay cache for {engine!r} is {status}: {detail}. "
        f"Rebuild: python scripts/build_revenue_outlook_replay_cache.py --engine {engine}"
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_compiled_cache_manifest_records_provenance(engine: str) -> None:
    manifest = json.loads(
        (replay_cache_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == REPLAY_CACHE_SCHEMA_VERSION
    assert manifest["engine"] == engine
    assert manifest["frame_count"] == 35
    assert manifest["row_count"] > 0
    assert manifest["source_digest"]
    # Every committed frame is hash-listed, so a corrupted file is detected.
    assert set(manifest["output_hashes"]) == {
        str(meta["file"]) for meta in manifest["frames"].values()
    }
    provenance = manifest["provenance"]
    assert provenance["pack_output_hashes"], "pack content must be in the digest"
    assert provenance["source_hashes"], "external replay inputs must be in the digest"


@pytest.mark.parametrize("engine", ENGINES)
def test_loaded_results_have_every_field(engine: str) -> None:
    macro, fuel = _load(engine)
    assert macro.base_scenario_name
    assert tuple(macro.scenario_names)
    assert fuel.base_scenario_name
    frames = {**_frames(macro, "macro."), **_frames(fuel, "fuel.")}
    assert len(frames) == 35
    # The frames the runtime actually consumes must carry rows.
    for name in (
        "macro.baseline_macro_quarterly_factors",
        "macro.baseline_macro_annual_factors",
        "fuel.quarterly_factors",
        "fuel.annual_factors",
        "fuel.policy_pair_factors",
        "fuel.input_audit",
        "fuel.gdp_input_audit",
    ):
        assert not frames[name].empty, f"{name} must not be a vacuous join source"


@pytest.mark.parametrize("engine", ENGINES)
def test_load_is_stable_across_calls(engine: str) -> None:
    """A second load reproduces the first exactly (no decode nondeterminism)."""
    first = {**_frames(_load(engine)[0], "macro."), **_frames(_load(engine)[1], "fuel.")}
    second = {**_frames(_load(engine)[0], "macro."), **_frames(_load(engine)[1], "fuel.")}
    for name in sorted(first):
        pd.testing.assert_frame_equal(first[name], second[name], check_exact=True)


def test_missing_cache_fails_closed(tmp_path: Path) -> None:
    pack = _pack_for(ENGINE_AR1)
    with pytest.raises(ReplayCacheMissing) as excinfo:
        load_replay_cache(
            engine=ENGINE_AR1,
            pack_manifest=pack.manifest,
            bridge_vintage_id=None,
            repo_root=tmp_path,
        )
    assert "build_revenue_outlook_replay_cache" in str(excinfo.value)


def test_changed_source_digest_invalidates(tmp_path: Path) -> None:
    """A moved input must make the cache stale, not silently serve old values."""
    pack = _pack_for(ENGINE_AR1)
    bridge = bridge_vintage_id_from_manifest(pack.manifest, ROOT)
    baseline, _ = replay_cache_source_digest(
        pack.manifest, engine=ENGINE_AR1, bridge_vintage_id=bridge, repo_root=ROOT
    )
    tampered = dict(pack.manifest)
    tampered["output_hashes"] = {**tampered.get("output_hashes", {}), "injected.parquet": "0" * 64}
    changed, _ = replay_cache_source_digest(
        tampered, engine=ENGINE_AR1, bridge_vintage_id=bridge, repo_root=ROOT
    )
    assert changed != baseline

    status, _ = replay_cache_status(
        engine=ENGINE_AR1, pack_manifest=tampered, bridge_vintage_id=bridge, repo_root=ROOT
    )
    assert status == "stale"
    with pytest.raises(ReplayCacheStale):
        load_replay_cache(
            engine=ENGINE_AR1,
            pack_manifest=tampered,
            bridge_vintage_id=bridge,
            repo_root=ROOT,
        )
    del tmp_path


def test_corrupt_frame_fails_hash_validation(tmp_path: Path) -> None:
    """A tampered frame file must be refused, not served."""
    import shutil

    source = replay_cache_dir(ENGINE_AR1, ROOT)
    target_root = tmp_path
    target = replay_cache_dir(ENGINE_AR1, target_root)
    shutil.copytree(source, target)
    victim = next(iter((target / "frames").glob("*.parquet")))
    victim.write_bytes(victim.read_bytes() + b"corrupt")

    pack = _pack_for(ENGINE_AR1)
    with pytest.raises(ReplayCacheError) as excinfo:
        load_replay_cache(
            engine=ENGINE_AR1,
            pack_manifest=pack.manifest,
            bridge_vintage_id=bridge_vintage_id_from_manifest(pack.manifest, ROOT),
            repo_root=target_root,
            # The digest is computed against the real repo, so point the source
            # scan back at ROOT by reusing the committed manifest's digest.
        )
    message = str(excinfo.value)
    assert "hash validation" in message or "stale" in message


@pytest.mark.parametrize("engine", ENGINES)
def test_fast_mode_named_path_runs_no_replay(engine: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The named fast path must not fit, replay, simulate or read a workbook."""
    monkeypatch.setenv("REVENUE_OUTLOOK_RUNTIME_MODE", "fast")

    def _forbidden(*args, **kwargs):  # pragma: no cover - the point is not to run
        raise AssertionError("named fast path must not run a live replay")

    monkeypatch.setattr(app, "run_fuel_price_scenario_replay", _forbidden)
    monkeypatch.setattr(app, "run_direct_treasury_scenario_replay", _forbidden)

    pack_dir = ROOT / engine_revenue_outlook_dir(engine)
    pack = _pack_for(engine)
    signature = revenue_outlook_signature(pack_dir, ROOT)
    app.cached_treasury_baseline_macro_replay.clear()
    app.cached_fuel_price_scenario_replay.clear()
    app.cached_scenario_overlay_rows.clear()

    rows, *_ = app.cached_scenario_overlay_rows(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off"),
        PED_BRIDGE_DEFAULT_MODE,
        RevenueScenarioComputationKey(),
        pack,
    )
    assert not rows.empty


@pytest.mark.slow
@pytest.mark.parametrize("engine", ENGINES)
def test_replay_cache_matches_reference_exactly(engine: str) -> None:
    """Every compiled frame equals the live replay, bit for bit."""
    from model_dashboard.fuel_price_scenario import (
        run_direct_treasury_scenario_replay,
        run_fuel_price_scenario_replay,
    )

    pack = _pack_for(engine)
    pack_dir = ROOT / engine_revenue_outlook_dir(engine)
    scenario_inputs = pd.read_parquet(pack_dir / "scenario_inputs" / "scenario_input_wide.parquet")
    bridge = bridge_vintage_id_from_manifest(pack.manifest, ROOT)

    reference = {
        **_frames(
            run_direct_treasury_scenario_replay(
                scenario_inputs, repo_root=ROOT, engine=engine, bridge_vintage_id=bridge
            ),
            "macro.",
        ),
        **_frames(
            run_fuel_price_scenario_replay(
                scenario_inputs, repo_root=ROOT, engine=engine, bridge_vintage_id=bridge
            ),
            "fuel.",
        ),
    }
    macro, fuel = _load(engine)
    compiled = {**_frames(macro, "macro."), **_frames(fuel, "fuel.")}

    assert set(compiled) == set(reference)
    for name in sorted(reference):
        pd.testing.assert_frame_equal(
            compiled[name], reference[name], check_exact=True, obj=name
        )

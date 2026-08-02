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
    """A tampered frame must be refused BY HASH VALIDATION specifically.

    The copied tree lives under a temp root whose source scan would differ, so
    the committed manifest's own digest and code-module hashes are reused here.
    Without that the load would be rejected as stale for an unrelated reason
    and this test would prove nothing about frame integrity.
    """
    import shutil

    source = replay_cache_dir(ENGINE_AR1, ROOT)
    target = replay_cache_dir(ENGINE_AR1, tmp_path)
    shutil.copytree(source, target)

    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    valid_digest = str(manifest["source_digest"])
    # Point the recorded code-module hashes at the real repo copies so the
    # code-change check passes and execution reaches frame hashing.
    manifest["provenance"]["code_module_hashes"] = {
        name: value
        for name, value in manifest["provenance"]["code_module_hashes"].items()
    }
    for name in list(manifest["provenance"]["code_module_hashes"]):
        shutil.copytree(
            ROOT / Path(name).parent,
            tmp_path / Path(name).parent,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    victim = target / "frames" / "fuel.annual_factors.parquet"
    victim.write_bytes(victim.read_bytes() + b"corrupt")

    pack = _pack_for(ENGINE_AR1)
    with pytest.raises(ReplayCacheError) as excinfo:
        load_replay_cache(
            engine=ENGINE_AR1,
            pack_manifest=pack.manifest,
            bridge_vintage_id=bridge_vintage_id_from_manifest(pack.manifest, ROOT),
            repo_root=tmp_path,
            source_digest=valid_digest,
        )
    message = str(excinfo.value)
    assert "failed hash validation" in message, message
    assert "fuel.annual_factors" in message, message


@pytest.mark.parametrize("engine", ENGINES)
def test_calculation_code_is_hashed_into_the_digest(engine: str) -> None:
    """A replay-logic edit must invalidate the cache on its own.

    BUILDER_VERSION is manually bumped and will be forgotten; the modules that
    actually compute the replay must therefore be part of the digest.
    """
    manifest = json.loads(
        (replay_cache_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    recorded = manifest["provenance"]["code_module_hashes"]
    assert recorded, "the calculation code must be in the digest"
    # The modules that actually compute both replays have to be covered.
    for required in (
        "model_dashboard/fuel_price_scenario.py",
        "model_dashboard/forecast_runner.py",
        "model_dashboard/conflict_gdp_paths.py",
        "model_dashboard/mbu26_source_spine.py",
        "pipeline/vnext_forward.py",
    ):
        assert required in recorded, f"{required} must be hashed into the replay digest"
    assert manifest["code_module_count"] == len(recorded)


def test_edited_replay_code_makes_the_cache_stale(tmp_path: Path) -> None:
    """Editing a replay module alone - no data, no version bump - goes stale."""
    import shutil

    engine = ENGINE_AR1
    shutil.copytree(replay_cache_dir(engine, ROOT), replay_cache_dir(engine, tmp_path))
    manifest_path = replay_cache_dir(engine, tmp_path) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Recreate the recorded modules under the temp root, then edit one of them
    # exactly as a developer would - without touching any data file.
    for name in manifest["provenance"]["code_module_hashes"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    edited = tmp_path / "model_dashboard" / "fuel_price_scenario.py"
    edited.write_text(
        edited.read_text(encoding="utf-8") + "\n# behaviour change\n", encoding="utf-8"
    )

    pack = _pack_for(engine)
    status, detail = replay_cache_status(
        engine=engine,
        pack_manifest=pack.manifest,
        bridge_vintage_id=bridge_vintage_id_from_manifest(pack.manifest, ROOT),
        repo_root=tmp_path,
    )
    assert status == "stale", (status, detail)
    assert "calculation code changed" in detail
    assert "fuel_price_scenario.py" in detail


def test_runtime_mode_governance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent defaults to fast; an explicit unknown value fails loudly."""
    monkeypatch.delenv(app.REVENUE_OUTLOOK_RUNTIME_MODE_ENV, raising=False)
    assert app.revenue_outlook_runtime_mode() == app.RUNTIME_MODE_FAST

    monkeypatch.setenv(app.REVENUE_OUTLOOK_RUNTIME_MODE_ENV, "")
    assert app.revenue_outlook_runtime_mode() == app.RUNTIME_MODE_FAST

    for mode in (app.RUNTIME_MODE_REFERENCE, app.RUNTIME_MODE_FAST, app.RUNTIME_MODE_SHADOW):
        monkeypatch.setenv(app.REVENUE_OUTLOOK_RUNTIME_MODE_ENV, mode.upper())
        assert app.revenue_outlook_runtime_mode() == mode

    monkeypatch.setenv(app.REVENUE_OUTLOOK_RUNTIME_MODE_ENV, "refrence")
    with pytest.raises(app.RevenueOutlookRuntimeModeError) as excinfo:
        app.revenue_outlook_runtime_mode()
    assert "refrence" in str(excinfo.value)


def test_missing_cache_produces_a_governed_page_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stale/missing cache explains itself and names the rebuild command."""
    monkeypatch.setenv(app.REVENUE_OUTLOOK_RUNTIME_MODE_ENV, "fast")
    pack = _pack_for(ENGINE_AR1)

    def _missing(**kwargs):
        del kwargs
        return "missing", "no compiled replay cache at <path>"

    monkeypatch.setattr(
        "model_dashboard.revenue_outlook_replay_cache.replay_cache_status", _missing
    )
    message = app._replay_cache_problem_uncached(pack)
    assert "build_revenue_outlook_replay_cache" in message
    assert "will not silently fall back" in message
    del tmp_path


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

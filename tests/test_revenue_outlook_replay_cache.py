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

import numpy as np
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
    build_environment,
    load_replay_cache,
    matches_build_environment,
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


@pytest.mark.parametrize("engine", ENGINES)
def test_digest_ignores_untracked_working_tree_files(engine: str) -> None:
    """An untracked local file must not change the digest.

    The regression this pins: the digest used to be computed by walking the
    source trees on disk, so a developer's untracked scratch output entered it.
    The committed cache then verified locally and read as STALE on a clean
    clone - which is exactly how CI failed on eac7e8c.
    """
    from model_dashboard.revenue_outlook_replay_cache import replay_source_file_hashes

    recorded = replay_source_file_hashes(ROOT, engine)
    scratch = (
        ROOT
        / "data"
        / "dashboard_evidence_pack_reproducibility"
        / "light_ruc"
        / "__untracked_digest_probe__.json"
    )
    scratch.write_text("{}", encoding="utf-8")
    try:
        assert replay_source_file_hashes(ROOT, engine) == recorded, (
            "an untracked file changed the replay source digest"
        )
    finally:
        scratch.unlink(missing_ok=True)


@pytest.mark.parametrize("engine", ENGINES)
def test_recorded_inputs_are_all_committed(engine: str) -> None:
    """Every path in the digest must exist in a clean clone."""
    import subprocess

    manifest = json.loads(
        (replay_cache_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    recorded = set(manifest["provenance"]["source_hashes"]) | set(
        manifest["provenance"]["code_module_hashes"]
    )
    tracked = set(
        subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.split("\n")
    )
    untracked = sorted(name for name in recorded if name and name not in tracked)
    assert not untracked, (
        "these digest inputs are not committed, so a clean clone will read the "
        f"cache as stale: {untracked[:10]}"
    )


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


# The cross-environment bound is the owner-approved PRESENTATION tolerance
# from the FY2050 long-run sensitivity handoff (2026-08): 1e-4 absolute in
# published display units - materially invisible on every dashboard surface
# ($m -> $100; million km -> 100 km; million litres -> 100 litres) - plus the
# repo's governed rel_tol=1e-9 so very large raw-unit values keep only a
# proportional allowance. The previous bound reused the formula-closure
# tolerance (abs_tol=1e-6), which CI showed is runner-marginal for the raw
# forward outputs: the same byte-identical cache measured 9.5e-07 worst-case
# drift on one runner and 6.104e-05 on another (fuel future_forecasts
# demand_calibrated_delta and the calibration closure-ratio columns), so the
# gate flapped on runner draw rather than on any real change.
#
# Note this is a statement about the MODEL, not about the cache: the affected
# frames include future_forecasts and component_forecasts, the raw forward
# outputs. The forward computation is reproducible across environments only
# to within this noise, not bit-for-bit. The serialisation itself remains
# exact and is gated separately, with no escape hatch, wherever the cache was
# built - only the cross-environment comparison carries this tolerance, and
# the repo's formula-closure and accounting gates are unchanged.
_CROSS_ENVIRONMENT_RTOL = 1e-9
_CROSS_ENVIRONMENT_ATOL = 1e-4
# No cap on how many frames may drift. The governed tolerance above is the
# gate; a count threshold adds nothing it does not already cover, and every
# time I guessed one from partial CI output it was wrong - 7 violations under a
# tighter bound turned out to be 17 frames drifting under the governed one. The
# full list is printed instead, so drift is visible and reviewable in the log.
# Measured baseline on 317c15b: 17 of 35 frames, 7.28e-12 to 9.54e-07 absolute.


def _worst_deviation(left: pd.DataFrame, right: pd.DataFrame) -> tuple[float, float, str]:
    """(max abs, max excess over the numpy tolerance, description).

    The second value is the amount by which the worst cell EXCEEDS
    ``atol + rtol*|reference|``; <= 0 means every cell is inside the bound.
    """
    import numpy as np

    worst_abs = 0.0
    worst_excess = -float("inf")
    where = "identical"
    for column in left.columns:
        if column not in right.columns:
            continue
        a = pd.to_numeric(left[column], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
        b = pd.to_numeric(right[column], errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
        if a.shape != b.shape:
            return float("inf"), float("inf"), f"{column}: shape {a.shape} vs {b.shape}"
        both = ~(np.isnan(a) | np.isnan(b))
        if not both.any():
            continue
        absolute = np.abs(a[both] - b[both])
        allowed = _CROSS_ENVIRONMENT_ATOL + _CROSS_ENVIRONMENT_RTOL * np.abs(b[both])
        excess = absolute - allowed
        worst_abs = max(worst_abs, float(absolute.max()))
        if float(excess.max()) > worst_excess:
            worst_excess = float(excess.max())
            index = int(np.argmax(excess))
            where = f"{column}: {a[both][index]!r} vs {b[both][index]!r}"
    return worst_abs, worst_excess, where


def test_cross_environment_bound_accepts_summation_noise_and_rejects_real_changes() -> None:
    """The bound must absorb 1e-11 residues and still catch a real change.

    Exercised directly because the branch it guards only runs when the cache
    was built under a different interpreter than the test - never on the
    machine that built it. The first version of this metric divided by |a| and
    so scored a 6.9e-11 residue against a reference of 0.0 as a 100% relative
    difference; that case is pinned below.
    """
    reference = pd.DataFrame(
        {"value": [0.0, 133.49257672, 8016352797.0, -2894.27382723066]}
    )

    # Summation noise at the scale CI actually produces, including the
    # near-zero cell that the old |a-b|/|a| metric scored as 100% different.
    noisy = pd.DataFrame(
        {
            "value": [
                6.912e-11,
                133.49257672000002,
                8016352797.0,
                -2894.27382723066 + 5e-11,
            ]
        }
    )
    _, worst_excess, where = _worst_deviation(noisy, reference)
    assert worst_excess <= 0.0, f"summation noise must be inside the bound ({where})"

    # The magnitudes CI actually reports: 9.537e-07 absolute on ~8e6 (the
    # case that failed on 320109f) and, on another runner draw against the
    # SAME byte-identical cache, 6.104e-05 on demand_calibrated_delta plus
    # 2.576e-06 on a calibration closure-ratio column (the case that failed
    # the b65fff3 run under the old abs_tol=1e-6 bound).
    observed = pd.DataFrame(
        {"value": [8345000.0, 3981300101.8991847, 13.05, 0.0001596450754676242]}
    )
    drifted = pd.DataFrame(
        {
            "value": [
                8345000.0 + 9.537e-07,
                np.nextafter(3981300101.8991847, np.inf),
                13.05 + 6.104e-05,
                0.00016222203087487924,
            ]
        }
    )
    _, worst_excess, where = _worst_deviation(drifted, observed)
    assert worst_excess <= 0.0, (
        f"the cross-environment drift CI measures must be inside the bound ({where})"
    )

    # A real change must still fail: a tenth of a display unit on a small
    # value (1e-3 >> atol=1e-4) and $20 on ~8e9 (>> atol + rtol*8e9 ~ 8.1).
    for index, changed_value in ((3, -2894.27282723066), (2, 8016352797.0 + 20.0)):
        changed = reference.copy()
        changed.loc[index, "value"] = changed_value
        _, worst_excess, where = _worst_deviation(changed, reference)
        assert worst_excess > 0.0, f"a real change was absorbed by the bound ({where})"


@pytest.mark.slow
@pytest.mark.parametrize("engine", ENGINES)
def test_replay_cache_matches_reference_exactly(engine: str) -> None:
    """Every compiled frame equals the live replay.

    Exactly, when this process is the one that built the cache - that is the
    gate on the serialisation, and it has no escape hatch.

    Elsewhere, to within the owner-approved presentation tolerance (1e-4 in
    published display units; see _CROSS_ENVIRONMENT_ATOL). Some frames differ
    across interpreter/library versions - the measured worst case varies by
    runner from 9.537e-07 to 6.104e-05 absolute against the same
    byte-identical cache. They include future_forecasts and
    component_forecasts - the raw forward outputs - so this is the MODEL not
    being bit-reproducible across environments, not the cache.
    """
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

    manifest = json.loads(
        (replay_cache_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    same_environment = matches_build_environment(manifest)

    inexact: list[str] = []
    violations: list[str] = []
    for name in sorted(reference):
        try:
            pd.testing.assert_frame_equal(
                compiled[name], reference[name], check_exact=True, obj=name
            )
        except AssertionError:
            if same_environment:
                # No escape hatch where the cache was built: this is the gate
                # proving the serialisation is lossless.
                raise
            worst_abs, worst_excess, where = _worst_deviation(compiled[name], reference[name])
            if worst_excess > 0.0:
                # Collect rather than raise: failing on the first frame reports
                # one number per CI run, which is how the bound got set from a
                # partial view twice already.
                violations.append(
                    f"{name}: max_abs={worst_abs:.3e} exceeds bound by "
                    f"{worst_excess:.3e} ({where})"
                )
            else:
                inexact.append(f"{name} (max_abs={worst_abs:.2e})")

    if inexact:
        # Visible, never silent: a reader of the CI log sees exactly which
        # frames drifted and by how much, even though the run passes.
        print(
            f"\n{len(inexact)} of {len(reference)} frames are environment-dependent "
            f"(built by {manifest.get('build_environment')}, running under "
            f"{build_environment()}); all within the governed closure tolerance:\n  "
            + "\n  ".join(inexact)
        )
    assert not violations, (
        f"{len(violations)} frame(s) exceed the governed closure tolerance across "
        f"environments (built by {manifest.get('build_environment')}, running under "
        f"{build_environment()}):\n  " + "\n  ".join(violations)
    )

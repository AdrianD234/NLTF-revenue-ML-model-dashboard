"""The materialised policy states must be a materialisation, never a guess.

Three properties carry the whole design, and each has a test that would fail
loudly if it stopped holding:

1. Every materialised state EQUALS the reference pipeline. A fast path that is
   merely close is a fast path that publishes wrong governed numbers.
2. A key outside the catalogue gets the reference path, never the nearest
   cached state. Approximation is the failure mode this module exists to
   prevent.
3. A band belongs to the policy state it was computed under - and where the
   policy leaves a series genuinely untouched, the band is IDENTICAL, because
   the same draws propagate through the same identities.

The exhaustive state-by-state parity run is marked ``slow``: it re-runs the
reference pipeline for all nine states per engine at ~7 s each.
"""
from __future__ import annotations

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
    revenue_outlook_signature,
)
from model_dashboard.revenue_outlook_policy_runtime import (
    FRAME_NAMES,
    POLICY_RUNTIME_SCHEMA_VERSION,
    POLICY_STATES,
    PolicyRuntimeError,
    PolicyRuntimeStale,
    STATUS_OK,
    STATUS_REFERENCE_REQUIRED,
    VFM_FAST_BASIS,
    VFM_SLOW_BASIS,
    load_policy_runtime,
    normalise_policy_state,
    policy_calculation_code_modules,
    policy_chart_rows,
    policy_detail_frames,
    policy_runtime_dir,
    policy_runtime_status,
    policy_uncertainty_rows,
    policy_vfm_scenario_rows,
    resolve_policy_state,
    state_id_for,
    upstream_manifests,
)
from model_dashboard.revenue_outlook_replay_cache import matches_build_environment
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey
from model_dashboard.revenue_uncertainty_policy import REPORTED_SERIES

ROOT = Path(__file__).resolve().parents[1]
ENGINES = (ENGINE_AR1, ENGINE_ENSEMBLE)
SENSITIVITY = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")


def _reference_parity(
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    obj: str,
    same_environment: bool,
    violations: list[str],
) -> None:
    """Compare a materialised frame to a LIVE reference run.

    Exactly, on the machine that built the pack - that is the gate on the
    materialisation, and it has no escape hatch.

    Elsewhere, to within the repo's governed closure tolerance. The forward
    model is not bit-reproducible across interpreter and library versions:
    PR #16 established that, and a live Linux reference reproduces cells of
    ``fuel.replay.future_forecasts`` at float32 precision where the Windows
    build produced float64. Asserting exact equality against a re-run on a
    machine that did not build the pack tests the environment, not the pack.

    The bound is imported from ``test_revenue_outlook_replay_cache`` rather
    than restated, because it is a governance artefact whose own comment
    records being set from a partial view twice. Two copies would drift.
    """
    try:
        pd.testing.assert_frame_equal(expected, actual, check_exact=True, obj=obj)
        return
    except AssertionError:
        if same_environment:
            raise
    from test_revenue_outlook_replay_cache import _worst_deviation

    worst_abs, worst_excess, where = _worst_deviation(actual, expected)
    if worst_excess > 0.0:
        # Collected rather than raised, so one CI run reports every frame that
        # drifted instead of only the first.
        violations.append(
            f"{obj}: max_abs={worst_abs:.3e} exceeds bound by {worst_excess:.3e} ({where})"
        )


def _built_here(engine: str) -> bool:
    """True when this process is the one that produced the materialised pack."""
    manifest = json.loads(
        (policy_runtime_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    return matches_build_environment(manifest)


# ---------------------------------------------------------------- fixtures


def _pack_and_signature(engine: str):
    pack_dir = ROOT / engine_revenue_outlook_dir(engine)
    signature = revenue_outlook_signature(pack_dir, ROOT)
    pack = app.cached_load_revenue_outlook_pack(
        str(pack_dir), str(ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    return pack, signature


def _governed_key(pack, engine: str, current_state: str, official_state: str):
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
    return RevenueScenarioComputationKey(
        engine=engine,
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=current_state,
        official_fed_policy_state=official_state,
        ped_bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        bridge_vintage_id=str(bridge_vintage_id_from_manifest(pack.manifest, ROOT) or ""),
        official_comparator_vintage_id=str(
            block.get("default_comparator_vintage_id") or "BEFU26"
        ),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )


@pytest.fixture(scope="module")
def runtimes():
    return {engine: load_policy_runtime(engine=engine, repo_root=ROOT) for engine in ENGINES}


@pytest.fixture
def reference_pipeline():
    """Make ``app.cached_scenario_overlay_rows`` mean the REFERENCE again.

    The integrated page answers a catalogued key from this pack, so a test
    that calls the page's own entry point to compute its "expected" value
    would be comparing the pack against itself and passing by tautology.
    Switching the fast path off is exactly what the builder does, and it is
    what makes these comparisons a parity check rather than a file read.

    The Streamlit caches are cleared on the way in and out because entries
    computed under one setting must not leak into the other.
    """
    original = app.POLICY_RUNTIME_FAST_PATH_ENABLED
    app.cached_scenario_overlay_rows.clear()
    app.cached_aligned_scenario_detail_frames.clear()
    app.POLICY_RUNTIME_FAST_PATH_ENABLED = False
    try:
        yield
    finally:
        app.POLICY_RUNTIME_FAST_PATH_ENABLED = original
        app.cached_scenario_overlay_rows.clear()
        app.cached_aligned_scenario_detail_frames.clear()


# -------------------------------------------------------------- catalogue


@pytest.mark.parametrize("engine", ENGINES)
def test_catalogue_covers_every_named_policy_pair(runtimes, engine):
    """Both engines carry all nine named states - no engine is a special case."""
    runtime = runtimes[engine]
    expected = {
        state_id_for(engine, current, official)
        for current in POLICY_STATES
        for official in POLICY_STATES
    }
    assert set(runtime.state_ids) == expected


def test_no_uplift_spelling_variants_resolve_to_one_state():
    """``off`` and ``no_uplift`` name the same counterfactual.

    A runtime that accepted only one spelling would fail closed on a naming
    difference between the UI layer and the calculation layer rather than on a
    real difference in what was requested.
    """
    assert normalise_policy_state("no_uplift") == normalise_policy_state("off")
    assert normalise_policy_state("delay_6m") == normalise_policy_state("delayed_6m")
    with pytest.raises(PolicyRuntimeError):
        normalise_policy_state("delayed_12m")


# ------------------------------------------------------------- exactness


@pytest.mark.slow
@pytest.mark.parametrize("engine", ENGINES)
def test_every_materialised_state_equals_the_reference_pipeline(runtimes, engine, reference_pipeline):
    """The whole contract, checked frame by frame on all nine states."""
    runtime = runtimes[engine]
    pack, signature = _pack_and_signature(engine)
    same_environment = _built_here(engine)
    violations: list[str] = []
    for current in POLICY_STATES:
        for official in POLICY_STATES:
            key = _governed_key(pack, engine, current, official)
            state_id = state_id_for(engine, current, official)
            (
                chart_rows,
                uptake_audit,
                eruc_audit,
                policy_audit,
                scenario_audit,
            ) = app.cached_scenario_overlay_rows(
                signature, SENSITIVITY, PED_BRIDGE_DEFAULT_MODE, key, pack
            )
            line, residuals, stack, bridge = app.cached_aligned_scenario_detail_frames(
                signature, SENSITIVITY, PED_BRIDGE_DEFAULT_MODE, key, pack
            )
            expected = {
                "chart_rows": chart_rows,
                "line_reconciliation": line,
                "formula_residuals": residuals,
                "stack_components": stack,
                "bridge_components": bridge,
                "policy_audit": policy_audit,
                # All three are frames the page reads back off this pack when
                # it stands in for the overlay chain, so all three have to
                # equal what that chain returns. The uptake audit is the one
                # that caught a real defect: it is NOT empty at the catalogue's
                # pinned default, and substituting an empty frame for it would
                # have switched off the page's EV-uptake audit surface.
                "scenario_audit": scenario_audit,
                "uptake_audit": uptake_audit,
                "eruc_audit": eruc_audit,
            }
            for frame_name, basis in (
                ("vfm_fast_chart_rows", VFM_FAST_BASIS),
                ("vfm_slow_chart_rows", VFM_SLOW_BASIS),
            ):
                preset_rows, _pu, _pe, _pp, _ps = app.cached_scenario_overlay_rows(
                    signature,
                    SENSITIVITY,
                    PED_BRIDGE_DEFAULT_MODE,
                    key.replace(uptake_basis=basis),
                    pack,
                )
                expected[frame_name] = preset_rows
            # Every frame the pack claims to carry, so adding one to
            # FRAME_NAMES without materialising it fails here rather than
            # surfacing as a missing download months later.
            assert set(expected) == set(FRAME_NAMES)
            for name in FRAME_NAMES:
                _reference_parity(
                    expected[name],
                    runtime.frame(state_id, name),
                    obj=f"{state_id}/{name}",
                    same_environment=same_environment,
                    violations=violations,
                )
    assert not violations, (
        f"{len(violations)} frame(s) exceed the governed closure tolerance:\n  "
        + "\n  ".join(violations)
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_published_default_rows_are_preserved_exactly(runtimes, engine, reference_pipeline):
    """The published default is what the page shows before anyone touches it."""
    runtime = runtimes[engine]
    pack, signature = _pack_and_signature(engine)
    key = _governed_key(pack, engine, "published", "published")
    chart_rows, _u, _e, _p, _s = app.cached_scenario_overlay_rows(
        signature, SENSITIVITY, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    violations: list[str] = []
    _reference_parity(
        chart_rows,
        runtime.frame(state_id_for(engine, "published", "published"), "chart_rows"),
        obj="published default chart_rows",
        same_environment=_built_here(engine),
        violations=violations,
    )
    assert not violations, "\n  ".join(violations)


@pytest.mark.parametrize("engine", ENGINES)
def test_actuals_and_official_rows_never_move_with_the_current_policy(runtimes, engine):
    """Selecting a Current counterfactual must not touch published history.

    Actual rows are measured outturn and official rows are a separate
    published vintage; neither is a forecast the Current policy can reprice.
    """
    runtime = runtimes[engine]
    baseline = runtime.frame(state_id_for(engine, "published", "published"), "chart_rows")
    for current in POLICY_STATES:
        candidate = runtime.frame(state_id_for(engine, current, "published"), "chart_rows")
        for role in ("actual", "official_comparator"):
            left = baseline[baseline["scenario_role"].astype(str).eq(role)]
            right = candidate[candidate["scenario_role"].astype(str).eq(role)]
            pd.testing.assert_series_equal(
                pd.to_numeric(left["value"], errors="coerce").reset_index(drop=True),
                pd.to_numeric(right["value"], errors="coerce").reset_index(drop=True),
                check_exact=True,
                check_names=False,
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_current_and_official_policies_stay_disjoint(runtimes, engine):
    """Changing the official comparator policy must not move Current rows.

    The two scopes are different calculations over disjoint role sets. If one
    ever leaked into the other, a reader changing the synthetic comparator
    would silently move the published Base forecast.
    """
    runtime = runtimes[engine]
    baseline = runtime.frame(state_id_for(engine, "delayed_6m", "published"), "chart_rows")
    current_roles = baseline["scenario_role"].astype(str).isin({"basecase", "comparison"})
    for official in POLICY_STATES:
        candidate = runtime.frame(state_id_for(engine, "delayed_6m", official), "chart_rows")
        mask = candidate["scenario_role"].astype(str).isin({"basecase", "comparison"})
        pd.testing.assert_series_equal(
            pd.to_numeric(baseline.loc[current_roles, "value"], errors="coerce").reset_index(
                drop=True
            ),
            pd.to_numeric(candidate.loc[mask, "value"], errors="coerce").reset_index(drop=True),
            check_exact=True,
            check_names=False,
        )


@pytest.mark.parametrize("engine", ENGINES)
def test_policy_applies_exactly_once(runtimes, engine):
    """One policy state, one adjustment per row.

    The audit records one row per adjusted (scenario, trace, path, grain,
    period, series). A duplicate there is a row that was repriced twice, which
    compounds the rate change instead of applying it.
    """
    runtime = runtimes[engine]
    for current in POLICY_STATES:
        audit = runtime.frame(state_id_for(engine, current, "published"), "policy_audit")
        if audit.empty:
            # The published state IS the source pack: no counterfactual runs.
            assert current == "published"
            continue
        columns = [
            column
            for column in (
                "scenario_name",
                "trace_name",
                "fed_path",
                "time_grain",
                "period",
                "series_id",
            )
            if column in audit.columns
        ]
        adjustments = audit.dropna(subset=["series_id"]) if "series_id" in audit else audit
        duplicated = adjustments.duplicated(subset=columns, keep=False)
        assert not duplicated.any(), (
            f"{current}: {int(duplicated.sum())} rows were adjusted more than once: "
            f"{adjustments.loc[duplicated, columns].head().to_dict('records')}"
        )


@pytest.mark.parametrize("engine", ENGINES)
def test_no_uplift_never_reprices_activity_or_non_fuel_revenue(runtimes, engine):
    """The scalar rate ratio is a RATE, and may only move rate-priced revenue.

    Regression for the FY2030/FY2031 seam defect: the beyond-replay-window
    fallback applied the petrol excise ratio to everything without a pair
    factor, so ped_vkt_per_capita fell 12% when the pump price fell (the wrong
    sign), BEV/PHEV km moved despite the no-class-elasticity contract, and
    net_mvr_revenue was scaled by the fuel rate - which broke its identity and
    made every no-uplift render raise.
    """
    runtime = runtimes[engine]
    published = runtime.frame(state_id_for(engine, "published", "published"), "chart_rows")
    no_uplift = runtime.frame(state_id_for(engine, "off", "published"), "chart_rows")

    def annual(frame):
        selected = frame[
            frame["time_grain"].astype(str).eq("june_year")
            & frame["scenario_name"].astype(str).eq("current_basecase")
        ]
        return selected.set_index(["period", "series_id"])["value"].astype(float)

    left, right = annual(published), annual(no_uplift)
    common = left.index.intersection(right.index)
    ratio = right[common] / left[common]
    for series in ("net_mvr_revenue", "light_bev_ruc_net_km", "phev_ruc_net_km"):
        moved = {
            period: float(value)
            for (period, series_id), value in ratio.items()
            if series_id == series and not np.isclose(value, 1.0, rtol=0.0, atol=1e-9)
        }
        assert not moved, f"{series} was repriced by the no-uplift policy: {moved}"

    # Activity may respond inside the fixed-finalist replay window, and must
    # never respond with the wrong sign: removing an excise increase makes
    # driving cheaper, so VKT can only go up.
    for (period, series_id), value in ratio.items():
        if series_id != "ped_vkt_per_capita":
            continue
        assert value >= 1.0 - 1e-9, (
            f"ped_vkt_per_capita fell to {value:.6f}x in {period} under no uplift; "
            "a cheaper pump price cannot reduce travel"
        )


@pytest.mark.parametrize("engine", ENGINES)
def test_formula_identities_close_on_every_materialised_state(runtimes, engine):
    """A materialised state that does not close is a state nobody may publish."""
    runtime = runtimes[engine]
    for current in POLICY_STATES:
        for official in POLICY_STATES:
            residuals = runtime.frame(
                state_id_for(engine, current, official), "formula_residuals"
            )
            if residuals.empty or "residual" not in residuals.columns:
                continue
            worst = pd.to_numeric(residuals["residual"], errors="coerce").abs().max()
            assert worst <= 1e-6, f"{current}/{official}: worst residual {worst:.3e}"


# ------------------------------------------------------- fail-closed policy


@pytest.mark.parametrize("engine", ENGINES)
def test_unsupported_custom_combination_refuses_to_use_a_named_cache(runtimes, engine):
    """A control outside the catalogue gets the reference path, not a guess."""
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    for field, value in (
        ("uptake_basis", "MoT VFM fast"),
        ("custom_ev_levers", (0.02, 2035.0, 0.8)),
        ("eruc_levers", (2027.0, 3.0, 1.0, -0.15, 2.7)),
        ("ped_retention_sensitivity", True),
        ("heavy_bev_transition", True),
        ("long_run_transition_schedule_id", app.UNBLENDED_SCHEDULE_ID),
        ("long_run_shape_vintage_id", "MBU26"),
        ("ped_bridge_mode", "optimized_migration"),
        ("bridge_vintage_id", "MBU26"),
    ):
        key = _governed_key(pack, engine, "delayed_6m", "published").replace(**{field: value})
        resolution = resolve_policy_state(runtime, key)
        assert resolution.status == STATUS_REFERENCE_REQUIRED, (
            f"{field}={value!r} was served from the named cache; it is a different computation"
        )
        assert field in resolution.detail
        with pytest.raises(PolicyRuntimeError):
            policy_chart_rows(runtime, key)


def test_a_different_engine_is_never_served_from_this_runtime(runtimes):
    """Two engines are two pack families, not one with a label."""
    runtime = runtimes[ENGINE_AR1]
    pack, _signature = _pack_and_signature(ENGINE_AR1)
    key = _governed_key(pack, ENGINE_ENSEMBLE, "delayed_6m", "published")
    resolution = resolve_policy_state(runtime, key)
    assert resolution.status == STATUS_REFERENCE_REQUIRED
    assert "engine" in resolution.detail


@pytest.mark.parametrize("engine", ENGINES)
def test_stale_pack_fails_closed_with_the_rebuild_command(tmp_path, engine):
    """A moved input must stop the pack, not quietly age inside it."""
    pack_manifest, replay_manifest, uncertainty_manifest = upstream_manifests(engine, ROOT)
    status, _detail = policy_runtime_status(
        engine=engine,
        pack_manifest=pack_manifest,
        replay_manifest=replay_manifest,
        uncertainty_manifest=uncertainty_manifest,
        repo_root=ROOT,
    )
    assert status == "ok"

    # A different upstream replay digest is exactly what a replay rebuild
    # produces, and it must invalidate every state computed on top of it.
    status, detail = policy_runtime_status(
        engine=engine,
        pack_manifest=pack_manifest,
        replay_manifest={**replay_manifest, "source_digest": "0" * 64},
        uncertainty_manifest=uncertainty_manifest,
        repo_root=ROOT,
        source_digest="0" * 64,
    )
    assert status == "stale"

    with pytest.raises(PolicyRuntimeStale) as error:
        load_policy_runtime(engine=engine, repo_root=ROOT, source_digest="0" * 64)
    assert "scripts/build_revenue_outlook_policy_runtime.py" in str(error.value)


@pytest.mark.parametrize("engine", ENGINES)
def test_app_py_is_in_the_invalidation_digest(engine):
    """The overlay chain lives in app.py, so app.py must be able to stale it.

    Inherited PR #16 hashing covers ``model_dashboard``/``pipeline`` only. The
    frames materialised here are produced by app.py's overlay chain, so an
    edit there has to fail the pack closed.
    """
    modules = policy_calculation_code_modules(ROOT)
    assert "app.py" in modules and modules["app.py"] != "absent"
    manifest = json.loads(
        (policy_runtime_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    recorded = manifest["provenance"]["code_module_hashes"]
    assert "app.py" in recorded
    assert recorded["app.py"] == modules["app.py"]


@pytest.mark.parametrize("engine", ENGINES)
def test_manifest_records_the_pinned_controls_it_is_valid_for(engine):
    """The pack must SAY what it pinned, or nothing can check it later."""
    manifest = json.loads(
        (policy_runtime_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == POLICY_RUNTIME_SCHEMA_VERSION
    pinned = manifest["pinned_key_fields"]
    # The two policy controls are what the catalogue VARIES over, so pinning
    # either of them would be a contradiction.
    assert "current_fed_policy_state" not in pinned
    assert "official_fed_policy_state" not in pinned
    assert pinned["uptake_basis"] == app.DEFAULT_EV_UPTAKE_MODE
    assert pinned["ped_retention_sensitivity"] is False
    # The page always sets these two, so a catalogue that pinned them empty
    # would refuse every key the page builds and the fast path would be dead
    # code that still passed its own tests.
    assert pinned["ped_bridge_mode"] == PED_BRIDGE_DEFAULT_MODE
    assert pinned["bridge_vintage_id"]


@pytest.mark.parametrize("engine", ENGINES)
def test_catalogue_pins_match_the_key_the_page_actually_builds(engine):
    """Every pinned field must equal what app.py writes at its defaults.

    This is the test that would have caught the catalogue being pinned at
    ``ped_bridge_mode=""`` while the page writes ``"raw_model"``: the runtime
    was correct, the states were exact, and not one real selection could have
    resolved to them.
    """
    manifest = json.loads(
        (policy_runtime_dir(engine, ROOT) / "manifest.json").read_text(encoding="utf-8")
    )
    pack, _signature = _pack_and_signature(engine)
    block = pack.manifest.get("official_vintages", {})
    page_defaults = {
        "uptake_basis": app.DEFAULT_EV_UPTAKE_MODE,
        "custom_ev_levers": [],
        "eruc_levers": [],
        "ped_retention_sensitivity": False,
        "heavy_bev_transition": False,
        "ped_bridge_mode": PED_BRIDGE_DEFAULT_MODE,
        "bridge_vintage_id": str(bridge_vintage_id_from_manifest(pack.manifest, ROOT) or ""),
        "long_run_transition_schedule_id": str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        "long_run_shape_vintage_id": str(block.get("long_run_shape_vintage_id") or ""),
        "macro_scenario_id": "",
        "conflict_fuel_state": "",
    }
    assert manifest["pinned_key_fields"] == page_defaults


# ------------------------------------------------------ display-only filters


@pytest.mark.parametrize("engine", ENGINES)
def test_series_and_grain_selection_never_changes_a_value(runtimes, engine):
    """Display filters select from the materialised rows; they never compute."""
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    key = _governed_key(pack, engine, "delayed_6m", "published")
    everything = policy_chart_rows(runtime, key)
    narrowed = policy_chart_rows(
        runtime, key, series_id="total_nltf_net_revenue", time_grain="june_year"
    )
    reference = everything[
        everything["series_id"].astype(str).eq("total_nltf_net_revenue")
        & everything["time_grain"].astype(str).eq("june_year")
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(reference, narrowed, check_exact=True)


@pytest.mark.parametrize("engine", ENGINES)
def test_detail_frames_refuse_a_vintage_they_were_not_aligned_against(runtimes, engine):
    """The aligned detail frames bake the vintage in; they cannot be filtered.

    ``cached_aligned_scenario_detail_frames`` filters the chart rows BEFORE
    aligning, so the line reconciliation, residuals and stack differ by
    vintage (5,080 / 7,221 / 9,362 line rows at default / MBU26 / overlay).
    Handing back the default vintage's frames for an MBU26 request would be a
    wrong answer that looked like a right one.
    """
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    key = _governed_key(pack, engine, "delayed_6m", "published")

    built_vintage, built_overlay = runtime.detail_vintage_scope()
    assert built_vintage == key.official_comparator_vintage_id
    assert built_overlay is False
    assert policy_detail_frames(runtime, key).line_reconciliation is not None

    other = "MBU26" if built_vintage != "MBU26" else "BEFU26"
    for variant in (
        key.replace(official_comparator_vintage_id=other),
        key.replace(official_comparator_overlay=True),
    ):
        with pytest.raises(PolicyRuntimeError) as error:
            policy_detail_frames(runtime, variant)
        assert "detail frames were built at official vintage" in str(error.value)
        # The chart rows DO carry every vintage, so they stay available.
        assert not policy_chart_rows(runtime, variant).empty


@pytest.mark.parametrize("engine", ENGINES)
def test_official_vintage_selection_is_a_post_cache_row_filter(runtimes, engine):
    """Selecting a vintage drops rows; it never recomputes one."""
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    key = _governed_key(pack, engine, "delayed_6m", "published")
    filtered = policy_chart_rows(runtime, key)
    overlaid = policy_chart_rows(runtime, key.replace(official_comparator_overlay=True))
    assert len(overlaid) >= len(filtered)
    kept = overlaid[
        overlaid["scenario_name"].astype(str).eq(
            f"{key.official_comparator_vintage_id.lower()}_official"
        )
    ]
    shown = filtered[filtered["scenario_role"].astype(str).eq("official_comparator")]
    pd.testing.assert_series_equal(
        pd.to_numeric(kept["value"], errors="coerce").reset_index(drop=True),
        pd.to_numeric(shown["value"], errors="coerce").reset_index(drop=True),
        check_exact=True,
        check_names=False,
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_vfm_envelope_inherits_the_selected_policy_state(runtimes, engine):
    """The Fast/Slow envelope must be the pair of the path ON SCREEN.

    It is the same overlay chain with only the composition basis swapped, so
    if it were served from a fixed policy state the range would be drawn
    around a Base path the reader is not looking at.
    """
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)

    def base_path(rows):
        selected = rows[
            rows["trace_name"].astype(str).eq("Current finalist Base case")
            & rows["time_grain"].astype(str).eq("june_year")
            & ~rows["row_type"].astype(str).eq("historical_actual")
            & rows["series_id"].astype(str).eq("total_nltf_net_revenue")
        ]
        return pd.to_numeric(selected["value"], errors="coerce").to_numpy()

    published = base_path(
        policy_vfm_scenario_rows(
            runtime, _governed_key(pack, engine, "published", "published"), "fast"
        )
    )
    no_uplift = base_path(
        policy_vfm_scenario_rows(runtime, _governed_key(pack, engine, "off", "published"), "fast")
    )
    assert len(published) and len(no_uplift)
    assert not np.allclose(published, no_uplift), (
        "the VFM Fast bound is identical under published and no-uplift; it is not "
        "inheriting the policy state"
    )
    with pytest.raises(PolicyRuntimeError):
        policy_vfm_scenario_rows(
            runtime, _governed_key(pack, engine, "published", "published"), "middle"
        )


@pytest.mark.slow
@pytest.mark.parametrize("engine", ENGINES)
def test_vfm_envelope_frames_equal_the_reference_preset_run(runtimes, engine, reference_pipeline):
    """Materialised Fast/Slow rows equal the preset overlay run exactly."""
    runtime = runtimes[engine]
    pack, signature = _pack_and_signature(engine)
    key = _governed_key(pack, engine, "delayed_6m", "published")
    same_environment = _built_here(engine)
    violations: list[str] = []
    for bound, basis in (("fast", VFM_FAST_BASIS), ("slow", VFM_SLOW_BASIS)):
        expected, _u, _e, _p, _s = app.cached_scenario_overlay_rows(
            signature,
            SENSITIVITY,
            PED_BRIDGE_DEFAULT_MODE,
            key.replace(uptake_basis=basis),
            pack,
        )
        _reference_parity(
            expected,
            runtime.frame(
                state_id_for(engine, "delayed_6m", "published"),
                f"vfm_{bound}_chart_rows",
            ),
            obj=f"vfm_{bound}_chart_rows",
            same_environment=same_environment,
            violations=violations,
        )
    assert not violations, "\n  ".join(violations)


# --------------------------------------------------------- policy-aware bands


@pytest.mark.parametrize("engine", ENGINES)
def test_bands_exist_for_every_policy_state_and_stay_nested(runtimes, engine):
    """50% inside 80%, on every row of every state."""
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    for current in POLICY_STATES:
        key = _governed_key(pack, engine, current, "published")
        rows = policy_uncertainty_rows(runtime, key)
        assert not rows.empty, f"no band rows for {current}"
        assert set(rows["policy_state"].astype(str)) == {current}
        assert (rows["lower80"] <= rows["lower50"] + 1e-9).all()
        assert (rows["upper50"] <= rows["upper80"] + 1e-9).all()


@pytest.mark.parametrize("engine", ENGINES)
def test_bands_move_where_the_policy_moves_the_series(runtimes, engine):
    """A band is a distribution AROUND a central path. If the path moves, it moves."""
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    published = policy_uncertainty_rows(
        runtime, _governed_key(pack, engine, "published", "published")
    ).set_index(["series_id", "FY"])
    no_uplift = policy_uncertainty_rows(
        runtime, _governed_key(pack, engine, "off", "published")
    ).set_index(["series_id", "FY"])

    moved = 0
    for index in published.index.intersection(no_uplift.index):
        left, right = published.loc[index], no_uplift.loc[index]
        if np.isclose(left["central"], right["central"], rtol=0.0, atol=1e-9):
            # The rule that matters: an unchanged central path MUST leave the
            # bounds unchanged. Anything else means the band drifted away from
            # the series it describes.
            for column in ("lower80", "lower50", "upper50", "upper80"):
                assert np.isclose(left[column], right[column], rtol=0.0, atol=1e-9), (
                    f"{index}: central is unchanged but {column} moved "
                    f"{left[column]!r} -> {right[column]!r}"
                )
        else:
            moved += 1
            assert not np.isclose(
                left["upper80"], right["upper80"], rtol=0.0, atol=1e-9
            ), f"{index}: central moved but upper80 did not"
    assert moved > 0, "no series moved under the no-uplift policy; the audit is not testing anything"


@pytest.mark.parametrize("engine", ENGINES)
def test_vkt_per_capita_band_is_invariant_where_the_series_is_invariant(runtimes, engine):
    """The handoff's rule, stated as a test.

    A reader changing a policy control elsewhere must not see VKT per capita
    bounds move in years where the policy does not touch VKT per capita.
    """
    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    published = policy_uncertainty_rows(
        runtime, _governed_key(pack, engine, "published", "published"), series_id="ped_vkt_per_capita"
    ).set_index("FY")
    no_uplift = policy_uncertainty_rows(
        runtime, _governed_key(pack, engine, "off", "published"), series_id="ped_vkt_per_capita"
    ).set_index("FY")
    invariant = [
        fy
        for fy in published.index.intersection(no_uplift.index)
        if np.isclose(published.loc[fy, "central"], no_uplift.loc[fy, "central"], atol=1e-9)
    ]
    assert invariant, "expected VKT per capita to be policy-invariant in the long run"
    for fy in invariant:
        for column in ("lower80", "lower50", "upper50", "upper80"):
            assert np.isclose(
                published.loc[fy, column], no_uplift.loc[fy, column], rtol=0.0, atol=1e-9
            )


@pytest.mark.parametrize("engine", ENGINES)
def test_band_rows_are_keyed_so_a_state_can_never_borrow_another(runtimes, engine):
    """Engine, policy state, series and FY together identify one band row."""
    runtime = runtimes[engine]
    rows = runtime.uncertainty_rows
    for column in (
        "engine",
        "policy_state",
        "series_id",
        "FY",
        "bridge_vintage_id",
        "long_run_transition_schedule_id",
        "long_run_shape_vintage_id",
    ):
        assert column in rows.columns, f"band rows are not keyed by {column}"
    assert not rows.duplicated(subset=["engine", "policy_state", "series_id", "FY"]).any()


def test_delayed_state_reproduces_the_committed_offline_uncertainty_pack():
    """The production state's bands must be the committed pack, exactly.

    The committed pack is built at (ensemble, delayed_6m). Reproducing its
    values from the policy-aware propagation proves the methodology is
    genuinely unchanged - same draws, same copula, same quantile map, same
    seam, same plateau - and that only the centre is policy-dependent.

    EVERY row is held to exact reproduction. A governed rigid-rescale
    exception used to sit here for Light petrol VKT FY2031-FY2050: the
    committed pack predated the published long-run Current line (the Treasury
    macro restatement, commits 159e68e..0481372), so its long-run band was
    drawn around a pre-overlay centre that never appeared on the chart, and
    the runtime re-centred it by one rigid factor. The governed-artifact
    reproducibility follow-up rebuilt the pack onto the published Current
    line, so the exception is retired: a reappearing rigid rescale - or any
    other movement - now fails, because it would mean the committed pack has
    drifted off the published central path again.
    """
    committed = pd.read_parquet(
        ROOT / "data" / "revenue_outlook_uncertainty" / "uncertainty_band_rows.parquet"
    )
    runtime = load_policy_runtime(engine=ENGINE_ENSEMBLE, repo_root=ROOT)
    pack, _signature = _pack_and_signature(ENGINE_ENSEMBLE)
    produced = policy_uncertainty_rows(
        runtime, _governed_key(pack, ENGINE_ENSEMBLE, "delayed_6m", "published")
    )

    left = committed.set_index(["series_id", "FY"]).sort_index()
    right = produced.set_index(["series_id", "FY"]).sort_index()
    # Every committed row must be reproduced - a subset would let the pack
    # drop series and still pass.
    missing = left.index.difference(right.index)
    assert missing.empty, f"the policy pack does not reproduce {len(missing)} committed rows"
    shared = left.index.intersection(right.index)
    assert len(shared) >= 1000, f"only {len(shared)} shared band rows; the comparison is vacuous"
    columns = ("central", "lower80", "lower50", "draw_median", "upper50", "upper80")
    for column in columns:
        np.testing.assert_allclose(
            left.loc[shared, column].to_numpy(dtype=float),
            right.loc[shared, column].to_numpy(dtype=float),
            rtol=0.0,
            atol=1e-9,
            err_msg=f"{column} drifted from the committed offline uncertainty pack",
        )


def test_the_offline_pack_centre_is_the_published_current_line():
    """Every offline band row is centred on the published Current base path.

    This is the permanent guard for the incident the reproducibility
    follow-up closed: the offline pack once carried a Light petrol VKT
    FY2031-FY2050 centre that never appeared on the chart, because the pack
    was built before the long-run Current line was published, and nothing
    compared the two afterwards. Here the committed offline centre is held to
    the committed policy runtime's aligned line reconciliation for the same
    (ensemble, delayed_6m) state - the path the dashboard actually draws - so
    a pack that drifts off the published central path reads as a failure, not
    as a plausible band around an invisible centre.
    """
    committed = pd.read_parquet(
        ROOT / "data" / "revenue_outlook_uncertainty" / "uncertainty_band_rows.parquet"
    )
    runtime = load_policy_runtime(engine=ENGINE_ENSEMBLE, repo_root=ROOT)
    pack, _signature = _pack_and_signature(ENGINE_ENSEMBLE)
    frames = policy_detail_frames(
        runtime, _governed_key(pack, ENGINE_ENSEMBLE, "delayed_6m", "published")
    )
    line = frames.line_reconciliation
    base = line[line["scenario_name"].astype(str).eq("current_basecase")].copy()
    base["FY"] = pd.to_numeric(base["FY"], errors="coerce")
    base["value"] = pd.to_numeric(base["value"], errors="coerce")
    base = base.dropna(subset=["FY", "value"])
    published: dict[tuple[str, int], float] = {}
    for _, row in base.iterrows():
        published.setdefault((str(row["series_id"]), int(row["FY"])), float(row["value"]))

    checked = 0
    light_petrol_long_run = 0
    for _, row in committed.iterrows():
        key = (str(row["series_id"]), int(row["FY"]))
        expected = published.get(key)
        if expected is None:
            continue
        checked += 1
        if key[0] == "light_petrol_vkt" and key[1] >= 2031:
            light_petrol_long_run += 1
        assert float(row["central"]) == pytest.approx(expected, rel=0.0, abs=1e-9), (
            f"offline centre for {key} is {float(row['central'])}, but the "
            f"published Current line carries {expected}; the pack has drifted "
            "off the published central path"
        )
    assert checked >= 500, f"only {checked} rows covered; the comparison is vacuous"
    assert light_petrol_long_run == 20, (
        "the Light petrol VKT FY2031-FY2050 rows - the ones this guard exists "
        f"for - were not all covered ({light_petrol_long_run}/20)"
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_reported_series_are_the_governed_inventory(runtimes, engine):
    """Every chartable leaf and every governed aggregate carries a band."""
    runtime = runtimes[engine]
    present = set(runtime.uncertainty_rows["series_id"].astype(str))
    missing = [series for series in REPORTED_SERIES if series not in present]
    # A leaf absent from the central extraction has no band by construction;
    # the governed aggregates must all be there.
    assert "total_nltf_net_revenue" in present
    assert "total_ruc_net_revenue" in present
    assert "net_fed_revenue" in present
    assert len(missing) < len(REPORTED_SERIES) / 2


def test_cross_environment_gate_absorbs_model_drift_and_catches_real_changes():
    """Exercise the non-build-environment branch of ``_reference_parity``.

    That branch only runs where the pack was NOT built, so it never executes
    on the machine that produced it - which is exactly how an escape hatch
    ends up quietly absorbing a real difference. Pinned directly instead.

    The bound is the repo's governed one, so this pins what it does rather
    than what would be convenient. It absorbs summation-scale residues.
    """
    reference = pd.DataFrame({"value": [13.01761507987976, 0.0, 8016352797.0, -2894.27382723066]})

    drifted = pd.DataFrame({"value": [13.0176150798797, 6.9e-11, 8016352797.0 + 1e-4, -2894.27382723071]})
    violations: list[str] = []
    _reference_parity(
        reference, drifted, obj="drift", same_environment=False, violations=violations
    )
    assert not violations, f"the governed bound rejected summation-scale noise: {violations}"

    # A real change must still be caught, and must NOT be caught by the
    # exactness path - it has to fail the BOUND.
    changed = pd.DataFrame({"value": [13.01761507987976, 0.0, 8016352797.0 + 20.0, -2894.2738]})
    violations = []
    _reference_parity(
        reference, changed, obj="real", same_environment=False, violations=violations
    )
    assert violations, "a real change was absorbed by the cross-environment bound"

    # On the machine that built the pack there is no bound at all.
    with pytest.raises(AssertionError):
        _reference_parity(
            reference, drifted, obj="drift", same_environment=True, violations=[]
        )

    # The float32/float64 split a live Linux replay actually produces IS now
    # absorbed: 13.017618179321289 (a float32 grid point) against the
    # float64-precise 13.01761507987976 is 3.1e-06 apart - 3.1 litres on ~13
    # million. The previous pin made widening the bound visible rather than
    # silent, and the owner decision it demanded has been made: the FY2050
    # long-run sensitivity handoff (2026-08, applied in eebc688 / PR #22)
    # moved _CROSS_ENVIRONMENT_ATOL to the 1e-4 display-unit presentation
    # tolerance precisely so runner-dependent model drift of this magnitude
    # stops failing CI. This block now pins the authorised behaviour.
    float32_drift = pd.DataFrame(
        {"value": [13.017618179321289, 0.0, 8016352797.0, -2894.27382723066]}
    )
    violations = []
    _reference_parity(
        reference, float32_drift, obj="float32", same_environment=False, violations=violations
    )
    assert not violations, (
        "the owner-approved presentation tolerance (1e-4 display units) must "
        f"absorb the float32 model drift: {violations}"
    )


# ------------------------------------------------------------- no live work


@pytest.mark.parametrize("engine", ENGINES)
def test_cache_hit_runs_no_replay_or_simulation(monkeypatch, runtimes, engine):
    """The fast path must not reach the replay, the fitter or the draws.

    Poisoning every expensive entry point is stricter than timing it: a call
    that should never happen raises instead of merely being slow.
    """
    import model_dashboard.fuel_price_scenario as fuel
    import model_dashboard.revenue_uncertainty_draws as draws

    def explode(*_args, **_kwargs):
        raise AssertionError("the policy fast path ran live work")

    monkeypatch.setattr(fuel, "run_fuel_price_scenario_replay", explode)
    monkeypatch.setattr(fuel, "run_direct_treasury_scenario_replay", explode)
    monkeypatch.setattr(draws, "generate_parent_factor_draws", explode)

    runtime = runtimes[engine]
    pack, _signature = _pack_and_signature(engine)
    for current in POLICY_STATES:
        key = _governed_key(pack, engine, current, "published")
        assert resolve_policy_state(runtime, key).status == STATUS_OK
        assert not policy_chart_rows(runtime, key).empty
        frames = policy_detail_frames(runtime, key)
        assert not frames.line_reconciliation.empty
        assert not policy_uncertainty_rows(runtime, key).empty
        assert not policy_vfm_scenario_rows(runtime, key, "fast").empty
        assert not policy_vfm_scenario_rows(runtime, key, "slow").empty

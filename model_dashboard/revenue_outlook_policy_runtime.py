"""Instant switching between the three named 12c FED/RUC policy states.

Profiling the reference path (``artifacts/revenue_outlook_policy_runtime/
policy_toggle_profile_before.csv``) found the first selection of each policy
state costs ~13.5 s per process, and that the policy arithmetic is almost none
of it: applying the policy factors is 0.33 s.  The other ~13.2 s is the macro
overlay, the VFM Fast/Slow envelope, the conflict append, the detail alignment
and the formula/stack rebuild - work that is re-run only because
``current_fed_policy_state`` is a field of the
``RevenueScenarioComputationKey`` those caches are keyed on, so every stage
downstream of it is invalidated too.

The policy states are FINITE.  There are three Current states and three
official-comparator states, and both controls are drop-downs.  So the outputs
are materialised offline, once, and the runtime does a catalogue lookup and a
parquet read.

Deliberately NOT a scenario cube.  The catalogue is keyed on the two policy
dimensions and the engine, and every other value-changing control is pinned to
the governed default the promoted pack recorded.  A key that differs anywhere
else resolves to ``reference_path_required`` - never to "the nearest cached
state", which is how a fast path silently starts publishing the wrong
counterfactual.

Fail-closed by contract: a missing, stale or corrupt pack raises with the
rebuild command rather than serving superseded numbers.

READ-ONLY FRAMES.  Every frame returned here is the process-wide memoised
object, not a copy: that is what keeps a repeat selection in the tens of
milliseconds the targets ask for.  Callers must treat them as immutable and
derive (filter, assign to a new frame) rather than mutate in place.  Mutating
one would corrupt every later reader in the process, and nothing downstream
would report it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .official_vintage import official_comparator_scenario_name
from .revenue_outlook_replay_cache import (
    _decode_frame,
    _hash_recorded_paths,
    _sha256_file,
    _tracked_tree_files,
    replay_calculation_code_modules,
)
from .revenue_scenario_key import RevenueScenarioComputationKey, as_scenario_key

__all__ = [
    "POLICY_RUNTIME_SCHEMA_VERSION",
    "POLICY_STATES",
    "PolicyDetailFrames",
    "PolicyRuntime",
    "PolicyRuntimeError",
    "PolicyRuntimeMissing",
    "PolicyRuntimeStale",
    "PolicyStateResolution",
    "STATUS_OK",
    "STATUS_REFERENCE_REQUIRED",
    "filter_official_vintage_rows",
    "load_policy_runtime",
    "policy_audit_rows",
    "policy_calculation_code_modules",
    "normalise_policy_state",
    "policy_chart_rows",
    "policy_detail_frames",
    "policy_runtime_dir",
    "policy_runtime_source_digest",
    "policy_runtime_status",
    "policy_uncertainty_rows",
    "policy_vfm_scenario_rows",
    "resolve_policy_state",
    "state_id_for",
]

POLICY_RUNTIME_SCHEMA_VERSION = "1"
BUILDER_VERSION = "1"

_PACK_ROOT = Path("data") / "revenue_outlook_policy_runtime"
_REBUILD_COMMAND = "python scripts/build_revenue_outlook_policy_runtime.py --all"

# The reader-facing vocabulary, matching app.py's FED_POLICY_* ids exactly.
# ``off`` is the app's id for the no-uplift counterfactual; ``no_uplift`` is
# the governed calculation-layer id for the same state, and the handoff's
# name for it. Both resolve here, because a runtime that accepted only one of
# them would fail closed on a spelling rather than on a real difference.
POLICY_PUBLISHED = "published"
POLICY_DELAYED_6M = "delayed_6m"
POLICY_NO_UPLIFT = "off"
POLICY_STATES = (POLICY_PUBLISHED, POLICY_DELAYED_6M, POLICY_NO_UPLIFT)

_POLICY_ALIASES = {
    "published": POLICY_PUBLISHED,
    "original": POLICY_PUBLISHED,
    "planned": POLICY_PUBLISHED,
    "published_timing": POLICY_PUBLISHED,
    "delayed_6m": POLICY_DELAYED_6M,
    "delay_6m": POLICY_DELAYED_6M,
    "shifted_6m": POLICY_DELAYED_6M,
    "deferred": POLICY_DELAYED_6M,
    "off": POLICY_NO_UPLIFT,
    "no_uplift": POLICY_NO_UPLIFT,
    "none": POLICY_NO_UPLIFT,
}

STATUS_OK = "ok"
STATUS_REFERENCE_REQUIRED = "reference_path_required"

# The frames one materialised state carries. Named here rather than globbed so
# a frame that failed to build is a hard error at load, not a silently absent
# download or audit table.
FRAME_NAMES = (
    "chart_rows",
    "line_reconciliation",
    "formula_residuals",
    "stack_components",
    "bridge_components",
    "policy_audit",
    # The MoT VFM Fast/Slow envelope is the same overlay chain run under two
    # fixed composition presets, and it inherits the live policy state, so a
    # policy switch pays for it twice more. Profiling put it at roughly half
    # the switch cost. The presets are fixed rather than free parameters, so
    # they are two more materialised frames, not a new catalogue dimension -
    # everything the envelope does after this point is a display filter.
    "vfm_fast_chart_rows",
    "vfm_slow_chart_rows",
)

VFM_FAST_BASIS = "MoT VFM fast"
VFM_SLOW_BASIS = "MoT VFM slow"
_VFM_FRAME_BY_BOUND = {
    "fast": "vfm_fast_chart_rows",
    "slow": "vfm_slow_chart_rows",
}

# Fields of the computation key that the materialised catalogue VARIES over.
_CATALOGUE_FIELDS = (
    "engine",
    "current_fed_policy_state",
    "official_fed_policy_state",
)
# Fields applied as an exact filter AFTER the cached rows are read, so they
# must not multiply the catalogue. For CHART ROWS this is exactly true: the
# overlay chain computes every vintage's rows and the selection only decides
# which are shown.
#
# It is NOT true of the detail frames. ``cached_aligned_scenario_detail_frames``
# filters the chart rows FIRST and then aligns, so the line reconciliation,
# the residuals and the stack are all built against the selected vintage -
# 5,080 line rows at the default vintage, 7,221 at MBU26, 9,362 with the
# analyst overlay on. Those are different computations wearing the same name.
# The materialised detail frames therefore carry the scope they were built at,
# and ``policy_detail_frames`` refuses a different one instead of silently
# handing back the default vintage's rows.
_POST_CACHE_OVERLAY_FIELDS = (
    "official_comparator_vintage_id",
    "official_comparator_overlay",
)
# Everything else must match the governed default the pack was built at. These
# are the fields whose value the catalogue PINS; a different value is a
# different computation and gets the reference path.
_PINNED_FIELDS = tuple(
    field.name
    for field in dataclasses.fields(RevenueScenarioComputationKey)
    if field.name not in _CATALOGUE_FIELDS and field.name not in _POST_CACHE_OVERLAY_FIELDS
)

# Non-pack inputs whose content can move a materialised policy state. Hashed
# by content, never by mtime, so a clean clone and a working tree agree.
_SOURCE_FILES: tuple[str, ...] = (
    "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv",
    "data/current_revenue_outlook/conflict_gdp_calibration.csv",
    "data/current_revenue_outlook/treasury_befu26_macro_path.csv",
    "data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv",
    "data/revenue_outlook_uncertainty/manifest.json",
    "data/vfm_202405/vfm_vkt_shares.csv",
    "artifacts/long_horizon_validation/long_horizon_june_year_errors.csv",
)
_SOURCE_TREES: tuple[str, ...] = (
    "data/revenue_model_source_pack/official_vintages",
    "data/revenue_model_source_pack/mbu26_annual_spine",
)


class PolicyRuntimeError(RuntimeError):
    """Base class: the materialised policy runtime cannot be trusted."""


class PolicyRuntimeMissing(PolicyRuntimeError):
    """No materialised policy runtime exists for this engine."""


class PolicyRuntimeStale(PolicyRuntimeError):
    """A pack exists but its inputs have moved underneath it."""


def normalise_policy_state(value: Any) -> str:
    """One of the three named states, or raise.

    Deliberately raises on an unknown value instead of defaulting. Defaulting
    is what turns a typo into a silently different published counterfactual.
    """
    if isinstance(value, bool):
        raise PolicyRuntimeError(f"policy state must be text, got bool ({value!r})")
    text = str(value or "").strip().casefold()
    if not text:
        raise PolicyRuntimeError("policy state is required")
    state = _POLICY_ALIASES.get(text)
    if state is None:
        raise PolicyRuntimeError(
            f"{value!r} is not a known 12c policy state; expected one of "
            + ", ".join(POLICY_STATES)
        )
    return state


def state_id_for(engine: str, current_state: str, official_state: str) -> str:
    """The catalogue's stable directory name for one materialised state."""
    return (
        f"{str(engine).strip().lower()}"
        f"__cur-{normalise_policy_state(current_state)}"
        f"__off-{normalise_policy_state(official_state)}"
    )


def policy_runtime_dir(engine: str, repo_root: Path) -> Path:
    return Path(repo_root) / _PACK_ROOT / str(engine).strip().lower()


# ---------------------------------------------------------------------------
# source digest
# ---------------------------------------------------------------------------


def policy_calculation_code_modules(repo_root: Path) -> dict[str, str]:
    """Every source file that can change a materialised policy state.

    The repo-local calculation modules PLUS ``app.py``. The replay cache could
    stop at ``model_dashboard``/``pipeline``, because the two replays live
    there. This pack cannot: the overlay chain that produces every materialised
    state - the macro overlay, the uptake allocation, the policy scopes, the
    conflict append, the detail alignment - lives in ``app.py``. Leaving it out
    would let an edit to that chain pass the digest, and the pack would serve
    superseded rows indefinitely, which is the one failure the digest exists to
    prevent.
    """
    modules = dict(replay_calculation_code_modules(repo_root))
    app_path = Path(repo_root) / "app.py"
    modules["app.py"] = _sha256_file(app_path) if app_path.exists() else "absent"
    return dict(sorted(modules.items()))


def policy_runtime_source_files(repo_root: Path) -> dict[str, str]:
    """Every committed non-pack policy input, path -> sha256."""
    hashes: dict[str, str] = {}
    for relative in _SOURCE_FILES:
        path = Path(repo_root) / relative
        hashes[relative] = _sha256_file(path) if path.exists() else "absent"
    for tree in _SOURCE_TREES:
        for relative in _tracked_tree_files(tree, Path(repo_root)):
            path = Path(repo_root) / relative
            hashes[relative] = _sha256_file(path) if path.exists() else "absent"
    return dict(sorted(hashes.items()))


def policy_runtime_source_digest(
    *,
    engine: str,
    pack_manifest: dict[str, Any],
    replay_manifest: dict[str, Any],
    uncertainty_manifest: dict[str, Any],
    repo_root: Path,
    code_module_hashes: dict[str, str] | None = None,
    source_file_hashes: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """(digest, provenance) over every input that can move a policy state.

    Chains the two upstream materialisations rather than re-deriving them: the
    promoted pack's own per-file hash map and the PR #16 replay cache's source
    digest. If either is rebuilt, this digest changes, so a policy state can
    never outlive the replay it was computed from.
    """
    provenance: dict[str, Any] = {
        "schema_version": POLICY_RUNTIME_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "engine": str(engine).strip().lower(),
        "code_module_hashes": dict(code_module_hashes or {}),
        "pack_output_hashes": pack_manifest.get("output_hashes", {}),
        "pack_schema_version": pack_manifest.get("schema_version", ""),
        # The whole PR #16 cache in one value: its digest already covers the
        # fitted state, the conflict configuration and the replay code.
        "replay_source_digest": replay_manifest.get("source_digest", ""),
        "replay_output_hashes": replay_manifest.get("output_hashes", {}),
        "uncertainty_scenario_key_digest": uncertainty_manifest.get("scenario_key_digest", ""),
        "uncertainty_seed": uncertainty_manifest.get("seed", ""),
        "uncertainty_draws": uncertainty_manifest.get("draws", ""),
    }
    provenance["source_hashes"] = dict(
        source_file_hashes
        if source_file_hashes is not None
        else policy_runtime_source_files(repo_root)
    )
    payload = json.dumps(provenance, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), provenance


def policy_runtime_expected_digest(
    *,
    engine: str,
    pack_manifest: dict[str, Any],
    replay_manifest: dict[str, Any],
    uncertainty_manifest: dict[str, Any],
    repo_root: Path,
) -> str:
    """The digest the committed pack SHOULD carry given today's sources."""
    manifest_path = policy_runtime_dir(engine, repo_root) / "manifest.json"
    recorded_code: dict[str, str] = {}
    recorded_sources: dict[str, str] = {}
    if manifest_path.exists():
        try:
            provenance = json.loads(manifest_path.read_text(encoding="utf-8")).get(
                "provenance", {}
            )
            recorded_code = dict(provenance.get("code_module_hashes", {}))
            recorded_sources = dict(provenance.get("source_hashes", {}))
        except (OSError, json.JSONDecodeError):
            recorded_code, recorded_sources = {}, {}
    digest, _ = policy_runtime_source_digest(
        engine=engine,
        pack_manifest=pack_manifest,
        replay_manifest=replay_manifest,
        uncertainty_manifest=uncertainty_manifest,
        repo_root=repo_root,
        code_module_hashes=(
            _hash_recorded_paths(repo_root, recorded_code)
            if recorded_code
            else policy_calculation_code_modules(repo_root)
        ),
        source_file_hashes=(
            _hash_recorded_paths(repo_root, recorded_sources)
            if recorded_sources
            else policy_runtime_source_files(repo_root)
        ),
    )
    return digest


def policy_runtime_status(
    *,
    engine: str,
    repo_root: Path,
    pack_manifest: dict[str, Any] | None = None,
    replay_manifest: dict[str, Any] | None = None,
    uncertainty_manifest: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> tuple[str, str]:
    """('ok'|'missing'|'stale'|'corrupt', detail) without reading any frame.

    The three upstream manifests are read for the caller when not supplied, so
    a status check is one call. Pass them explicitly to check a hypothetical -
    which is how the stale-pack tests prove the gate actually fires.
    """
    if pack_manifest is None or replay_manifest is None or uncertainty_manifest is None:
        read_pack, read_replay, read_uncertainty = upstream_manifests(engine, Path(repo_root))
        pack_manifest = read_pack if pack_manifest is None else pack_manifest
        replay_manifest = read_replay if replay_manifest is None else replay_manifest
        uncertainty_manifest = (
            read_uncertainty if uncertainty_manifest is None else uncertainty_manifest
        )
    target = policy_runtime_dir(engine, repo_root)
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        return "missing", f"no materialised policy runtime at {target.as_posix()}"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return "corrupt", f"unreadable manifest: {error}"
    if str(manifest.get("schema_version")) != POLICY_RUNTIME_SCHEMA_VERSION:
        return "stale", (
            f"schema {manifest.get('schema_version')!r} != {POLICY_RUNTIME_SCHEMA_VERSION!r}"
        )
    if source_digest is None:
        provenance = dict(manifest.get("provenance", {}))
        recorded_code = dict(provenance.get("code_module_hashes", {}))
        if not recorded_code:
            return "stale", (
                "pack predates calculation-code hashing and cannot prove the "
                "policy overlay logic is unchanged"
            )
        # Re-hash exactly the paths the pack RECORDED. A fresh tree walk would
        # make the digest depend on untracked working-tree files, so the pack
        # would verify locally and read as stale in CI.
        current_code = _hash_recorded_paths(repo_root, recorded_code)
        if current_code != recorded_code:
            changed = sorted(
                name for name, value in current_code.items() if recorded_code.get(name) != value
            )
            return "stale", (
                "policy calculation code changed: "
                + ", ".join(changed[:5])
                + (f" (+{len(changed) - 5} more)" if len(changed) > 5 else "")
            )
        recorded_sources = dict(provenance.get("source_hashes", {}))
        current_sources = _hash_recorded_paths(repo_root, recorded_sources)
        if current_sources != recorded_sources:
            changed = sorted(
                name
                for name, value in current_sources.items()
                if recorded_sources.get(name) != value
            )
            return "stale", (
                "policy inputs changed: "
                + ", ".join(changed[:5])
                + (f" (+{len(changed) - 5} more)" if len(changed) > 5 else "")
            )
        source_digest, _ = policy_runtime_source_digest(
            engine=engine,
            pack_manifest=pack_manifest,
            replay_manifest=replay_manifest,
            uncertainty_manifest=uncertainty_manifest,
            repo_root=repo_root,
            code_module_hashes=current_code,
            source_file_hashes=current_sources,
        )
    if str(manifest.get("source_digest")) != source_digest:
        return "stale", (
            "the promoted pack, the compiled replay cache or the uncertainty "
            "inputs changed since the policy runtime was built"
        )
    return "ok", ""


# ---------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PolicyStateResolution:
    """What the catalogue can serve for one requested key.

    ``status`` is ``ok`` only when an EXACT materialised state exists. There is
    no partial or approximate outcome: ``reference_path_required`` names the
    field that took the key outside the catalogue so the caller can say why.
    """

    status: str
    state_id: str = ""
    engine: str = ""
    current_policy_state: str = ""
    official_policy_state: str = ""
    detail: str = ""
    official_comparator_vintage_id: str = ""
    official_comparator_overlay: bool = False

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


@dataclasses.dataclass(frozen=True)
class PolicyDetailFrames:
    """The aligned detail surfaces one policy state carries.

    Read-only, like everything else this module hands out: these are the
    memoised frames, not copies.
    """

    line_reconciliation: pd.DataFrame
    formula_residuals: pd.DataFrame
    stack_components: pd.DataFrame
    bridge_components: pd.DataFrame


class PolicyRuntime:
    """One engine's materialised policy states, lazily read and memoised.

    Holding the decoded frames per state is what makes a repeated selection a
    dict lookup rather than a parquet read. The catalogue is tiny (three
    Current states x three official states), so the whole engine fits in
    memory without a bound.
    """

    def __init__(
        self,
        *,
        engine: str,
        manifest: dict[str, Any],
        directory: Path,
        verify_hashes: bool,
        uncertainty_rows: pd.DataFrame,
    ) -> None:
        self.engine = str(engine).strip().lower()
        self.manifest = manifest
        self.directory = directory
        self.verify_hashes = verify_hashes
        self.uncertainty_rows = uncertainty_rows
        self._frames: dict[tuple[str, str], pd.DataFrame] = {}
        self._states: dict[str, dict[str, Any]] = {
            str(state["state_id"]): state for state in manifest.get("states", [])
        }
        self._pinned: dict[str, Any] = dict(manifest.get("pinned_key_fields", {}))

    # ------------------------------------------------------------- catalogue
    @property
    def state_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._states))

    def computation_catalogue(self) -> pd.DataFrame:
        """One row per materialised state, with its full key digest."""
        return pd.DataFrame(list(self._states.values()))

    def pinned_key_fields(self) -> dict[str, Any]:
        return dict(self._pinned)

    def detail_vintage_scope(self) -> tuple[str, bool]:
        """(vintage id, overlay) the aligned detail frames were built at."""
        scope = dict(self.manifest.get("detail_frame_vintage_scope", {}))
        return str(scope.get("vintage_id", "")), bool(scope.get("overlay", False))

    # ----------------------------------------------------------------- read
    def frame(self, state_id: str, name: str) -> pd.DataFrame:
        if name not in FRAME_NAMES:
            raise PolicyRuntimeError(f"{name!r} is not a materialised policy frame")
        cached = self._frames.get((state_id, name))
        if cached is not None:
            return cached
        state = self._states.get(state_id)
        if state is None:
            raise PolicyRuntimeError(
                f"Policy state {state_id!r} is not in the catalogue for engine {self.engine!r}."
            )
        meta = dict(state["frames"][name])
        path = self.directory / "frames" / state_id / str(meta["file"])
        if not path.exists():
            raise PolicyRuntimeError(
                f"Policy frame {name!r} for {state_id!r} is missing from "
                f"{path.parent.as_posix()}. Rebuild: {_REBUILD_COMMAND}"
            )
        if self.verify_hashes:
            expected = str(meta.get("sha256", ""))
            if expected and _sha256_file(path) != expected:
                raise PolicyRuntimeError(
                    f"Policy frame {name!r} for {state_id!r} failed hash validation. "
                    f"Rebuild: {_REBUILD_COMMAND}"
                )
        decoded = _decode_frame(pd.read_parquet(path), meta)
        self._frames[(state_id, name)] = decoded
        return decoded


def _pack_paths(engine: str, repo_root: Path) -> tuple[Path, Path]:
    from .engine import engine_revenue_outlook_dir

    pack_dir = Path(repo_root) / engine_revenue_outlook_dir(engine)
    return pack_dir, Path(repo_root) / "data" / "revenue_outlook_replay_cache" / engine


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def upstream_manifests(engine: str, repo_root: Path) -> tuple[dict, dict, dict]:
    """(promoted pack, compiled replay cache, uncertainty pack) manifests."""
    pack_dir, replay_dir = _pack_paths(engine, repo_root)
    return (
        _read_json(pack_dir / "manifest.json"),
        _read_json(replay_dir / "manifest.json"),
        _read_json(Path(repo_root) / "data" / "revenue_outlook_uncertainty" / "manifest.json"),
    )


def load_policy_runtime(
    *,
    engine: str,
    repo_root: Path | str,
    verify_hashes: bool = True,
    source_digest: str | None = None,
) -> PolicyRuntime:
    """The materialised policy states for one engine, or fail closed."""
    repo_root = Path(repo_root)
    engine = str(engine).strip().lower()
    pack_manifest, replay_manifest, uncertainty_manifest = upstream_manifests(engine, repo_root)
    status, detail = policy_runtime_status(
        engine=engine,
        pack_manifest=pack_manifest,
        replay_manifest=replay_manifest,
        uncertainty_manifest=uncertainty_manifest,
        repo_root=repo_root,
        source_digest=source_digest,
    )
    if status == "missing":
        raise PolicyRuntimeMissing(f"{detail}. Rebuild it with: {_REBUILD_COMMAND}")
    if status == "stale":
        raise PolicyRuntimeStale(
            f"Materialised Revenue Outlook policy runtime for engine {engine!r} is stale "
            f"({detail}). Rebuild it with: {_REBUILD_COMMAND}"
        )
    if status != "ok":
        raise PolicyRuntimeError(
            f"Policy runtime for engine {engine!r} is unusable ({detail}). "
            f"Rebuild: {_REBUILD_COMMAND}"
        )

    directory = policy_runtime_dir(engine, repo_root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    bands_path = directory / "uncertainty_band_rows.parquet"
    if not bands_path.exists():
        raise PolicyRuntimeError(
            f"Policy-aware uncertainty rows are missing from {directory.as_posix()}. "
            f"Rebuild: {_REBUILD_COMMAND}"
        )
    if verify_hashes:
        expected = str(manifest.get("uncertainty_sha256", ""))
        if expected and _sha256_file(bands_path) != expected:
            raise PolicyRuntimeError(
                f"Policy-aware uncertainty rows failed hash validation. Rebuild: {_REBUILD_COMMAND}"
            )
    return PolicyRuntime(
        engine=engine,
        manifest=manifest,
        directory=directory,
        verify_hashes=verify_hashes,
        uncertainty_rows=pd.read_parquet(bands_path),
    )


def resolve_policy_state(
    runtime: PolicyRuntime,
    key: RevenueScenarioComputationKey | tuple[Any, ...] | None,
    *,
    engine: str | None = None,
) -> PolicyStateResolution:
    """Which materialised state (if any) answers this key exactly.

    Never approximates. A control outside the catalogue returns
    ``reference_path_required`` naming the field that differs, so the caller
    reports a governed reason rather than a wrong number.
    """
    typed = as_scenario_key(key)
    engine = str(engine or typed.engine or runtime.engine).strip().lower()
    if engine != runtime.engine:
        return PolicyStateResolution(
            status=STATUS_REFERENCE_REQUIRED,
            detail=(
                f"engine {engine!r} is not the engine this runtime was loaded for "
                f"({runtime.engine!r})"
            ),
        )

    try:
        current_state = normalise_policy_state(typed.current_fed_policy_state or POLICY_DELAYED_6M)
        official_state = normalise_policy_state(
            typed.official_fed_policy_state or POLICY_PUBLISHED
        )
    except PolicyRuntimeError as error:
        return PolicyStateResolution(status=STATUS_REFERENCE_REQUIRED, detail=str(error))

    pinned = runtime.pinned_key_fields()
    for field in _PINNED_FIELDS:
        if field == "engine":
            continue
        if field not in pinned:
            # A control exists that the pack never recorded a pin for, so it
            # cannot say whether the materialised states are valid under it.
            # Say so, rather than treating "unrecorded" as "matches".
            return PolicyStateResolution(
                status=STATUS_REFERENCE_REQUIRED,
                detail=(
                    f"the materialised pack records no pinned value for {field!r}; it "
                    "predates that control and cannot be shown to be valid under it"
                ),
            )
        expected = pinned.get(field)
        actual = getattr(typed, field)
        if isinstance(expected, list):
            expected = tuple(expected)
        if isinstance(actual, tuple):
            actual = tuple(float(value) for value in actual)
            expected = tuple(float(value) for value in expected or ())
        if actual != expected:
            return PolicyStateResolution(
                status=STATUS_REFERENCE_REQUIRED,
                detail=(
                    f"{field}={actual!r} is outside the materialised catalogue, which is "
                    f"pinned at {expected!r}; the reference pipeline owns this combination"
                ),
            )

    state_id = state_id_for(engine, current_state, official_state)
    if state_id not in runtime.state_ids:
        return PolicyStateResolution(
            status=STATUS_REFERENCE_REQUIRED,
            detail=f"no materialised state {state_id!r} in the catalogue",
        )
    return PolicyStateResolution(
        status=STATUS_OK,
        state_id=state_id,
        engine=engine,
        current_policy_state=current_state,
        official_policy_state=official_state,
        official_comparator_vintage_id=typed.official_comparator_vintage_id,
        official_comparator_overlay=typed.official_comparator_overlay,
    )


def _require(resolution: PolicyStateResolution) -> None:
    if not resolution.ok:
        raise PolicyRuntimeError(
            "No materialised policy state for this key: " + (resolution.detail or "unknown reason")
        )


def filter_official_vintage_rows(
    frame: pd.DataFrame, selected_vintage_id: str, overlay: bool
) -> pd.DataFrame:
    """Drop official-comparator rows belonging to non-selected vintages.

    The exact post-cache row filter for the selected official vintage: a row
    selection over already-computed values, so it stays out of the catalogue.
    Including it would multiply the materialised states to express a choice
    that changes which rows are SHOWN, not what any of them equal.

    Mirrors ``app._filter_official_vintage_rows`` exactly, including the
    overlay case (keep every published vintage) and the pass-through for
    frames that carry no scenario columns. Reimplemented rather than imported
    because ``app`` pulls in the whole Streamlit runtime, and a calculation
    module must not depend on the UI to filter a frame.
    """
    from .rate_paths import OFFICIAL_SCOPE

    if overlay or frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    if "scenario_role" not in frame.columns or "scenario_name" not in frame.columns:
        return frame
    selected_scenario = official_comparator_scenario_name(selected_vintage_id)
    role = frame["scenario_role"].fillna("").astype(str)
    scenario = frame["scenario_name"].fillna("").astype(str)
    drop = role.eq(OFFICIAL_SCOPE) & ~scenario.eq(str(selected_scenario))
    if not drop.any():
        return frame
    return frame[~drop].copy()


def _apply_official_vintage_filter(
    frame: pd.DataFrame, resolution: PolicyStateResolution
) -> pd.DataFrame:
    return filter_official_vintage_rows(
        frame,
        resolution.official_comparator_vintage_id,
        resolution.official_comparator_overlay,
    )


def policy_chart_rows(
    runtime: PolicyRuntime,
    key: RevenueScenarioComputationKey | tuple[Any, ...] | None,
    *,
    series_id: str | None = None,
    time_grain: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """The chart rows for one policy state, optionally narrowed for display.

    The narrowing arguments are display-only: they select from the same
    materialised rows and never change a value, which is why they are not part
    of the catalogue key.
    """
    resolution = resolve_policy_state(runtime, key)
    _require(resolution)
    rows = _apply_official_vintage_filter(
        runtime.frame(resolution.state_id, "chart_rows"), resolution
    )
    if series_id:
        rows = rows[rows["series_id"].astype(str).eq(str(series_id))]
    if time_grain:
        rows = rows[rows["time_grain"].astype(str).eq(str(time_grain))]
    if scenario_names:
        rows = rows[rows["scenario_name"].astype(str).isin({str(n) for n in scenario_names})]
    return rows.reset_index(drop=True) if (series_id or time_grain or scenario_names) else rows


def policy_detail_frames(
    runtime: PolicyRuntime,
    key: RevenueScenarioComputationKey | tuple[Any, ...] | None,
) -> PolicyDetailFrames:
    """Line, residual, stack and bridge frames for one policy state.

    Unlike the chart rows, these are built AGAINST a chosen official vintage,
    so the selection is baked in rather than filterable afterwards. A request
    for a different vintage or the analyst overlay raises instead of returning
    the default vintage's frames, which would be a wrong answer that looked
    like a right one.
    """
    resolution = resolve_policy_state(runtime, key)
    _require(resolution)
    built_vintage, built_overlay = runtime.detail_vintage_scope()
    if (
        resolution.official_comparator_vintage_id != built_vintage
        or bool(resolution.official_comparator_overlay) != built_overlay
    ):
        raise PolicyRuntimeError(
            "No materialised policy state for this key: the aligned detail frames were "
            f"built at official vintage {built_vintage!r} (overlay={built_overlay}), and "
            f"{resolution.official_comparator_vintage_id!r} "
            f"(overlay={bool(resolution.official_comparator_overlay)}) is a different "
            "alignment, not a filter of the same one; the reference pipeline owns it"
        )
    return PolicyDetailFrames(
        line_reconciliation=runtime.frame(resolution.state_id, "line_reconciliation"),
        formula_residuals=runtime.frame(resolution.state_id, "formula_residuals"),
        stack_components=runtime.frame(resolution.state_id, "stack_components"),
        bridge_components=runtime.frame(resolution.state_id, "bridge_components"),
    )


def policy_audit_rows(
    runtime: PolicyRuntime,
    key: RevenueScenarioComputationKey | tuple[Any, ...] | None,
) -> pd.DataFrame:
    """The FED/RUC policy audit rows recorded when this state was applied."""
    resolution = resolve_policy_state(runtime, key)
    _require(resolution)
    return runtime.frame(resolution.state_id, "policy_audit")


def policy_vfm_scenario_rows(
    runtime: PolicyRuntime,
    key: RevenueScenarioComputationKey | tuple[Any, ...] | None,
    bound: str,
) -> pd.DataFrame:
    """The Fast or Slow VFM composition rows under THIS policy state.

    The structural envelope is a pair of governed composition scenarios, not
    an interval, and it inherits every non-VFM control from the live key -
    including the policy. Serving it from the wrong policy state would draw a
    range around a path that is not on screen.
    """
    resolution = resolve_policy_state(runtime, key)
    _require(resolution)
    name = _VFM_FRAME_BY_BOUND.get(str(bound).strip().lower())
    if name is None:
        raise PolicyRuntimeError(
            f"{bound!r} is not a VFM envelope bound; expected 'fast' or 'slow'"
        )
    return _apply_official_vintage_filter(runtime.frame(resolution.state_id, name), resolution)


def policy_uncertainty_rows(
    runtime: PolicyRuntime,
    key: RevenueScenarioComputationKey | tuple[Any, ...] | None,
    *,
    series_id: str | None = None,
) -> pd.DataFrame:
    """The 50%/80% band rows computed under THIS policy state.

    Keyed on the policy state, so a band can never be shown around a central
    path it was not computed from. Where the policy leaves a series genuinely
    unchanged the rows are identical to the published state's by construction,
    not by a copy - the same draws propagate through the same identities.
    """
    resolution = resolve_policy_state(runtime, key)
    _require(resolution)
    rows = runtime.uncertainty_rows
    selected = rows[
        rows["engine"].astype(str).eq(resolution.engine)
        & rows["policy_state"].astype(str).eq(resolution.current_policy_state)
    ]
    if series_id:
        selected = selected[selected["series_id"].astype(str).eq(str(series_id))]
    if selected.empty:
        return selected.reset_index(drop=True)
    return selected.sort_values(["series_id", "FY"]).reset_index(drop=True)
